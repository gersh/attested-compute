// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                 \
                               cudaGetErrorString(status_));                  \
    }                                                                        \
  } while (0)

std::uint64_t fnv1a(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  std::uint64_t value = 1'469'598'103'934'665'603ULL;
  for (std::size_t index = 0; index < size; ++index) {
    value ^= bytes[index];
    value *= 1'099'511'628'211ULL;
  }
  return value;
}

std::uint64_t bits(double value) {
  std::uint64_t result = 0U;
  static_assert(sizeof(result) == sizeof(value));
  std::memcpy(&result, &value, sizeof(result));
  return result;
}

bool canonical_malformed(pw::RealDisk106 value) {
  return bits(value.center.hi) == 0U && bits(value.center.lo) == 0U &&
         bits(value.radius) == 0x7ff0000000000000ULL;
}

struct Forgery {
  const char* name;
  std::uint32_t roster_position_quarters;
  pw::ComplexDisk106 value;
};

std::array<Forgery, 5> forgeries() {
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double infinity = std::numeric_limits<double>::infinity();
  const double negative_least_subnormal =
      -std::numeric_limits<double>::denorm_min();
  return {{
      {"negative-minsubnormal-radius",
       4U,
       {{0.0, 0.0}, {0.0, 0.0}, negative_least_subnormal}},
      {"nan-center", 0U, {{nan, 0.0}, {0.0, 0.0}, 0.0}},
      {"infinite-center",
       2U,
       {{0.0, 0.0}, {0.0, infinity}, 0.0}},
      {"nan-radius", 1U, {{0.0, 0.0}, {0.0, 0.0}, nan}},
      {"infinite-radius",
       3U,
       {{0.0, 0.0}, {0.0, 0.0}, infinity}},
  }};
}

void run_transform(bool tile, pdt::Workspace* workspace,
                   const pw::ComplexDisk106* gamma,
                   const pw::ComplexDisk106* skn, cudaStream_t stream) {
  if (tile) {
    pdt::run_source_window_tile9_qualification(
        workspace, gamma, skn, stream);
  } else {
    pdt::run_source_window(workspace, gamma, skn, stream);
  }
}

std::uint32_t input_failure_flags(pdt::Workspace* workspace) {
  std::uint32_t result = 0U;
  CUDA_CHECK(cudaMemcpy(
      &result, pdt::device_input_failure_flags_qualification(workspace),
      sizeof(result), cudaMemcpyDeviceToHost));
  return result;
}

std::vector<pw::RealDisk106> download_samples(pdt::Workspace* workspace) {
  std::vector<pw::RealDisk106> result(pdt::kSourceSampleCount);
  CUDA_CHECK(cudaMemcpy(result.data(), pdt::device_samples(workspace),
                        result.size() * sizeof(pw::RealDisk106),
                        cudaMemcpyDeviceToHost));
  return result;
}

void verify_forgery(
    bool tile, bool gamma_input, const Forgery& forgery,
    pdt::Workspace* transform, pes::Workspace* scanner,
    pw::ComplexDisk106* gamma, pw::ComplexDisk106* skn,
    cudaStream_t stream) {
  constexpr std::uint64_t skn_count =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  pw::ComplexDisk106* const target = gamma_input ? gamma : skn;
  const std::uint64_t target_count =
      gamma_input ? pw::kBucketCount : skn_count;
  const std::uint64_t target_index =
      (target_count - 1U) * forgery.roster_position_quarters / 4U;
  const std::uint32_t expected_flag =
      gamma_input ? pdt::kQualificationInputFailureGamma
                  : pdt::kQualificationInputFailureSkn;
  const pw::ComplexDisk106 zero{};

  CUDA_CHECK(cudaMemcpyAsync(target + target_index, &forgery.value,
                             sizeof(forgery.value), cudaMemcpyHostToDevice,
                             stream));
  run_transform(tile, transform, gamma, skn, stream);
  pes::scan_source_required_samples(
      scanner, pdt::device_required_samples(transform), stream);
  const pes::ReplayReport replay = pes::replay_and_check(
      scanner, pdt::device_required_samples(transform), stream);

  const std::uint32_t actual_flag = input_failure_flags(transform);
  if (actual_flag != expected_flag) {
    throw std::runtime_error(
        std::string(tile ? "tile9 " : "ordinary ") +
        (gamma_input ? "Gamma " : "S_k ") + forgery.name +
        " produced the wrong validation bit");
  }
  const std::vector<pw::RealDisk106> samples = download_samples(transform);
  if (!std::all_of(samples.begin(), samples.end(), canonical_malformed)) {
    throw std::runtime_error(
        std::string(tile ? "tile9 " : "ordinary ") +
        (gamma_input ? "Gamma " : "S_k ") + forgery.name +
        " did not poison every final sample canonically");
  }
  if (replay.accepted || !replay.device_matches_host ||
      replay.artifact.status.failure_flags != pes::kFailureMalformedDisk ||
      replay.artifact.status.certified_sample_count != 0U ||
      replay.artifact.status.digest_valid != 0U) {
    throw std::runtime_error(
        std::string(tile ? "tile9 " : "ordinary ") +
        (gamma_input ? "Gamma " : "S_k ") + forgery.name +
        " did not fail closed at the event scanner");
  }

  CUDA_CHECK(cudaMemcpy(target + target_index, &zero, sizeof(zero),
                        cudaMemcpyHostToDevice));
}

int run() {
  constexpr std::uint64_t skn_count =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  pw::ComplexDisk106* gamma = nullptr;
  pw::ComplexDisk106* skn = nullptr;
  pdt::Workspace* transform = nullptr;
  pes::Workspace* scanner = nullptr;
  cudaStream_t stream = nullptr;
  try {
    CUDA_CHECK(cudaMalloc(&gamma,
                          pw::kBucketCount * sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMalloc(&skn,
                          skn_count * sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMemset(gamma, 0,
                          pw::kBucketCount * sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMemset(skn, 0,
                          skn_count * sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    transform = pdt::create_source_workspace();
    scanner = pes::create_workspace();

    std::array<std::vector<pw::RealDisk106>, 2> valid_outputs;
    for (std::uint32_t path = 0U; path < 2U; ++path) {
      run_transform(path == 1U, transform, gamma, skn, stream);
      CUDA_CHECK(cudaStreamSynchronize(stream));
      if (input_failure_flags(transform) !=
          pdt::kQualificationInputFailureNone) {
        throw std::runtime_error(
            "valid zero input raised a transform validation bit");
      }
      valid_outputs[path] = download_samples(transform);
    }
    if (std::memcmp(valid_outputs[0].data(), valid_outputs[1].data(),
                    valid_outputs[0].size() * sizeof(pw::RealDisk106)) != 0) {
      throw std::runtime_error(
          "ordinary and tile9 valid zero-input bytes differ");
    }

    std::vector<pw::RealDisk106> required(
        valid_outputs[0].begin() + pdt::kSourceRequiredBegin,
        valid_outputs[0].begin() + pdt::kSourceRequiredEnd + 1U);
    bool finite = true;
    double maximum_radius = 0.0;
    for (const pw::RealDisk106 value : required) {
      finite = finite && std::isfinite(value.center.hi) &&
               std::isfinite(value.center.lo) &&
               std::isfinite(value.radius) && value.radius >= 0.0;
      maximum_radius = std::max(maximum_radius, value.radius);
    }
    if (!finite) {
      throw std::runtime_error("valid zero input emitted an invalid disk");
    }
    const std::uint64_t digest =
        fnv1a(required.data(), required.size() * sizeof(pw::RealDisk106));

    std::uint32_t forgery_cases = 0U;
    for (std::uint32_t path = 0U; path < 2U; ++path) {
      for (std::uint32_t input = 0U; input < 2U; ++input) {
        for (const Forgery& forgery : forgeries()) {
          verify_forgery(path == 1U, input == 0U, forgery, transform,
                         scanner, gamma, skn, stream);
          ++forgery_cases;
        }
      }
    }
    CUDA_CHECK(cudaStreamSynchronize(stream));
    if (forgery_cases != 20U) {
      throw std::runtime_error("transform forgery roster is incomplete");
    }

    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-dd-transform-api-smoke.v2\""
              << ",\"accepted\":true"
              << ",\"source_geometry\":true"
              << ",\"device_to_device_api\":true"
              << ",\"required_sample_count\":" << required.size()
              << ",\"workspace_device_bytes\":"
              << pdt::workspace_device_bytes(transform)
              << ",\"all_required_disks_finite\":true"
              << ",\"maximum_required_radius\":" << maximum_radius
              << ",\"required_output_fnv1a64\":\"" << std::hex
              << std::setw(16) << std::setfill('0') << digest << std::dec
              << "\""
              << ",\"synthetic_zero_input_only\":true"
              << ",\"valid_input_failure_flags_zero\":true"
              << ",\"valid_ordinary_tile9_byte_identical\":true"
              << ",\"forgery_cases\":" << forgery_cases
              << ",\"ordinary_forgery_cases\":10"
              << ",\"tile9_forgery_cases\":10"
              << ",\"gamma_failure_bits_exact\":true"
              << ",\"skn_failure_bits_exact\":true"
              << ",\"canonical_malformed_output_complete\":true"
              << ",\"event_scanner_fail_closed_complete\":true"
              << ",\"physical_trace_refinement_proved\":false"
              << ",\"pt21_source_claim_discharged\":false}\n";

    CUDA_CHECK(cudaStreamSynchronize(stream));
    pes::destroy_workspace(scanner);
    scanner = nullptr;
    pdt::destroy_workspace(transform);
    transform = nullptr;
    CUDA_CHECK(cudaFree(gamma));
    gamma = nullptr;
    CUDA_CHECK(cudaFree(skn));
    skn = nullptr;
    CUDA_CHECK(cudaStreamDestroy(stream));
    stream = nullptr;
    return 0;
  } catch (...) {
    if (stream != nullptr) cudaStreamSynchronize(stream);
    if (scanner != nullptr) {
      try {
        pes::destroy_workspace(scanner);
      } catch (...) {
      }
    }
    if (transform != nullptr) {
      try {
        pdt::destroy_workspace(transform);
      } catch (...) {
      }
    }
    if (gamma != nullptr) cudaFree(gamma);
    if (skn != nullptr) cudaFree(skn);
    if (stream != nullptr) cudaStreamDestroy(stream);
    throw;
  }
}

}  // namespace

int main() {
  try {
    return run();
  } catch (const std::exception& error) {
    std::cerr << "{\"schema\":\"sparkinterval.tg.platt-dd-transform-api-smoke.v2\""
              << ",\"accepted\":false,\"error\":\"" << error.what()
              << "\",\"pt21_source_claim_discharged\":false}\n";
    return 2;
  }
}
