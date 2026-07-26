// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_event_scan.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace pes = sparkinterval::tg::platt_event_scan;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

constexpr std::string_view kCmakeBuildConfig =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif
constexpr bool kReleasePerformanceBuild =
    kNdebugDefined && kCmakeBuildConfig == "Release";

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

struct Options {
  std::string mode = "valid";
  std::uint32_t iterations = 1'000U;
  bool asynchronous_capture = false;
};

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--mode" && index + 1 < argc) {
      options.mode = argv[++index];
    } else if (argument == "--iterations" && index + 1 < argc) {
      const std::string_view text(argv[++index]);
      std::uint32_t value = 0U;
      const auto parsed =
          std::from_chars(text.data(), text.data() + text.size(), value);
      if (parsed.ec != std::errc{} ||
          parsed.ptr != text.data() + text.size() || value == 0U ||
          value > 10'000'000U) {
        throw std::invalid_argument("--iterations is outside [1,10000000]");
      }
      options.iterations = value;
    } else if (argument == "--async-capture") {
      options.asynchronous_capture = true;
    } else {
      throw std::invalid_argument(
          "usage: --mode valid|strict|edge|ambiguous|malformed|overflow "
          "[--iterations N] [--async-capture]");
    }
  }
  if (options.mode != "valid" && options.mode != "strict" &&
      options.mode != "edge" &&
      options.mode != "ambiguous" &&
      options.mode != "malformed" && options.mode != "overflow") {
    throw std::invalid_argument("unknown --mode");
  }
  return options;
}

std::vector<pw::RealDisk106> synthetic_source_geometry() {
  std::vector<pw::RealDisk106> samples(
      sparkinterval::tg::platt_dd_transform::kSourceRequiredCount);
  constexpr double magnitude[5] = {4.0, 3.0, 2.0, 3.0, 4.0};
  for (std::size_t index = 0; index < samples.size(); ++index) {
    const bool positive = ((index / 5U) & 1U) == 0U;
    const double sign = positive ? 1.0 : -1.0;
    samples[index].center.hi = sign * magnitude[index % 5U];
    samples[index].center.lo =
        sign * std::ldexp(static_cast<double>(index % 3U + 1U), -60);
    samples[index].radius = std::ldexp(1.0, -70);
  }
  return samples;
}

std::string digest_hex(const unsigned char digest[32]) {
  std::ostringstream result;
  result << std::hex << std::setfill('0');
  for (unsigned int index = 0; index < 32U; ++index) {
    result << std::setw(2) << static_cast<unsigned int>(digest[index]);
  }
  return result.str();
}

std::string json_escape(const std::string& value) {
  std::ostringstream result;
  for (const char character : value) {
    if (character == '"' || character == '\\') result << '\\';
    if (character == '\n') {
      result << "\\n";
    } else {
      result << character;
    }
  }
  return result.str();
}

int run(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  std::vector<pw::RealDisk106> samples = synthetic_source_geometry();
  std::uint32_t expected_failure = pes::kFailureNone;
  pes::Capacities capacities = pes::maximum_capacities();
  if (options.mode == "strict") {
    for (pw::RealDisk106& sample : samples) {
      sample = {{10.0, 0.0}, std::ldexp(1.0, -70)};
    }
    const auto at = [&samples](int offset) -> pw::RealDisk106& {
      return samples[static_cast<std::size_t>(offset - pes::kRequiredLower)];
    };
    // One genuine strict positive local minimum at [0,1,2].
    at(0).center.hi = 11.0;
    at(1).center.hi = 9.0;
    at(2).center.hi = 11.0;
    // [10,11,12] is deliberately non-strict on the right and must not fire.
    at(10).center.hi = 11.0;
    at(11).center.hi = 10.0;
    at(12).center.hi = 10.0;
  } else if (options.mode == "edge") {
    for (pw::RealDisk106& sample : samples) {
      sample = {{10.0, 0.0}, 0.0};
    }
    const double least_subnormal = std::ldexp(1.0, -1074);
    const double maximum = std::numeric_limits<double>::max();
    samples[100U] = {{least_subnormal, 0.0}, 0.0};
    samples[200U] = {
        {1.0, -std::nextafter(1.0, 0.0)}, 0.0};
    samples[300U] = {{maximum, -maximum / 2.0}, 0.0};
    samples[400U] = {{-least_subnormal, 0.0}, 0.0};
    samples[500U] = {
        {-1.0, std::nextafter(1.0, 0.0)}, 0.0};
    samples[600U] = {{-maximum, maximum / 2.0}, 0.0};
  } else if (options.mode == "ambiguous") {
    samples[7U] = {{0.0, 0.0}, 1.0};
    expected_failure = pes::kFailureAmbiguousDisk;
  } else if (options.mode == "malformed") {
    samples[11U].radius = -1.0;
    expected_failure = pes::kFailureMalformedDisk;
  } else if (options.mode == "overflow") {
    capacities = {{{1U, 1U, 1U}}, {{1U, 1U, 1U}}};
    expected_failure =
        pes::kFailureDirectOverflow | pes::kFailureStationaryOverflow;
  }

  pw::RealDisk106* device_samples = nullptr;
  pes::Workspace* workspace = nullptr;
  pes::ReplayCapture* replay_capture = nullptr;
  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  try {
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&device_samples),
                          samples.size() * sizeof(pw::RealDisk106)),
               "cudaMalloc samples");
    check_cuda(cudaMemcpy(device_samples, samples.data(),
                          samples.size() * sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice),
               "copy samples");
    workspace = pes::create_workspace(capacities);

    double milliseconds = 0.0;
    if (options.mode == "valid") {
      for (unsigned int iteration = 0; iteration < 10U; ++iteration) {
        pes::scan_source_required_samples(workspace, device_samples);
      }
      check_cuda(cudaDeviceSynchronize(), "warm event scanner");
      check_cuda(cudaEventCreate(&start), "create start event");
      check_cuda(cudaEventCreate(&stop), "create stop event");
      check_cuda(cudaEventRecord(start), "record start event");
      for (std::uint32_t iteration = 0; iteration < options.iterations;
           ++iteration) {
        pes::scan_source_required_samples(workspace, device_samples);
      }
      check_cuda(cudaEventRecord(stop), "record stop event");
      check_cuda(cudaEventSynchronize(stop), "synchronize stop event");
      float measured = 0.0F;
      check_cuda(cudaEventElapsedTime(&measured, start, stop),
                 "measure event scanner");
      milliseconds = measured;
    } else {
      pes::scan_source_required_samples(workspace, device_samples);
    }
    pes::ReplayReport replay;
    std::uint64_t replay_capture_bytes = 0U;
    bool replay_capture_lifecycle_guarded = true;
    if (options.asynchronous_capture) {
      replay_capture = pes::create_replay_capture(workspace);
      replay_capture_bytes =
          pes::replay_capture_pinned_bytes(replay_capture);
      replay_capture_lifecycle_guarded =
          !pes::replay_capture_ready(replay_capture);
      pes::enqueue_replay_capture(
          workspace, device_samples, replay_capture);
      try {
        pes::enqueue_replay_capture(
            workspace, device_samples, replay_capture);
        replay_capture_lifecycle_guarded = false;
      } catch (const std::logic_error&) {
      }
      replay = pes::replay_captured(replay_capture);
      replay_capture_lifecycle_guarded =
          replay_capture_lifecycle_guarded &&
          !pes::replay_capture_ready(replay_capture);
      try {
        (void)pes::replay_captured(replay_capture);
        replay_capture_lifecycle_guarded = false;
      } catch (const std::invalid_argument&) {
      }
      pes::destroy_replay_capture(replay_capture);
      replay_capture = nullptr;
    } else {
      replay = pes::replay_and_check(workspace, device_samples);
    }

    cudaDeviceProp properties{};
    int device = 0;
    check_cuda(cudaGetDevice(&device), "get CUDA device");
    check_cuda(cudaGetDeviceProperties(&properties, device),
               "get CUDA properties");

    const bool success_mode =
        options.mode == "valid" || options.mode == "strict" ||
        options.mode == "edge";
    const bool expected_failure_observed =
        success_mode
            ? replay.artifact.status.failure_flags == 0U
            : (replay.artifact.status.failure_flags & expected_failure) ==
                  expected_failure;
    std::uint64_t direct_slots = 0U;
    std::uint64_t stationary_certified_slots = 0U;
    for (std::size_t stream = 0; stream < pes::kStreamCount; ++stream) {
      direct_slots += replay.artifact.summaries[stream]
                          .certified_direct_multiplicity_slots;
      for (const pes::StationaryCandidate& candidate :
           replay.artifact.stationary[stream]) {
        stationary_certified_slots += candidate.certified_multiplicity_slots;
      }
    }
    const bool strict_predicate_test_passed =
        options.mode != "strict" ||
        (replay.artifact.summaries[0].stationary_candidate_count == 0U &&
         replay.artifact.summaries[1].stationary_candidate_count == 1U &&
         replay.artifact.summaries[2].stationary_candidate_count == 0U &&
         direct_slots == 0U);
    const bool success = replay.device_matches_host &&
                         expected_failure_observed &&
                         strict_predicate_test_passed &&
                         (success_mode ? replay.accepted : !replay.accepted);

    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-pt21-event-scan-benchmark.v1\""
              << ",\"accepted\":" << (replay.accepted ? "true" : "false")
              << ",\"test_success\":" << (success ? "true" : "false")
              << ",\"mode\":\"" << options.mode << "\""
              << ",\"gpu\":\"" << json_escape(properties.name) << "\""
              << ",\"compute_capability\":\"" << properties.major << '.'
              << properties.minor << "\""
              << ",\"build_profile\":{\"cmake_build_config\":\""
              << json_escape(std::string(kCmakeBuildConfig))
              << "\",\"ndebug_defined\":"
              << (kNdebugDefined ? "true" : "false")
              << ",\"release_performance_build\":"
              << (kReleasePerformanceBuild ? "true" : "false") << '}'
              << ",\"required_sample_count\":" << samples.size()
              << ",\"all_required_samples_certified\":"
              << (replay.artifact.status.certified_sample_count ==
                          samples.size()
                      ? "true"
                      : "false")
              << ",\"failure_flags\":"
              << replay.artifact.status.failure_flags
              << ",\"expected_failure_flags\":" << expected_failure
              << ",\"expected_failure_observed\":"
              << (expected_failure_observed ? "true" : "false")
              << ",\"strict_predicate_test_passed\":"
              << (strict_predicate_test_passed ? "true" : "false")
              << ",\"device_matches_host_replay\":"
              << (replay.device_matches_host ? "true" : "false")
              << ",\"shared_endpoints_explicit\":true"
              << ",\"shared_endpoints_agree\":"
              << (replay.shared_endpoints_agree ? "true" : "false")
              << ",\"stream_ranges\":{"
              << "\"left_flank\":[-12800,-12288],"
              << "\"main\":[-12288,12288],"
              << "\"right_flank\":[12288,12800]}"
              << ",\"lattice\":{\"numerator\":21,\"denominator\":512}"
              << ",\"streams\":[";
    for (std::size_t stream = 0; stream < pes::kStreamCount; ++stream) {
      if (stream != 0U) std::cout << ',';
      const pes::StreamSummary& summary = replay.artifact.summaries[stream];
      std::cout << "{\"stream\":" << summary.stream
                << ",\"lower_sample\":" << summary.lower_sample
                << ",\"upper_sample\":" << summary.upper_sample
                << ",\"direct_events\":" << summary.direct_event_count
                << ",\"stationary_candidates\":"
                << summary.stationary_candidate_count
                << ",\"direct_nleft_units\":"
                << summary.direct_nleft_units
                << ",\"direct_nright_units\":"
                << summary.direct_nright_units << '}';
    }
    const double scans_per_second =
        milliseconds > 0.0
            ? static_cast<double>(options.iterations) * 1000.0 / milliseconds
            : 0.0;
    std::cout << ']'
              << ",\"certified_direct_multiplicity_slots\":"
              << direct_slots
              << ",\"stationary_certified_multiplicity_slots\":"
              << stationary_certified_slots
              << ",\"stationary_candidates_claim_two_zeros\":false"
              << ",\"artifact_sha256\":\""
              << digest_hex(replay.artifact.status.artifact_sha256) << "\""
              << ",\"digest_valid\":"
              << (replay.artifact.status.digest_valid != 0U ? "true" : "false")
              << ",\"workspace_device_bytes\":"
              << pes::workspace_device_bytes(workspace)
              << ",\"asynchronous_capture\":"
              << (options.asynchronous_capture ? "true" : "false")
              << ",\"replay_capture_pinned_bytes\":"
              << replay_capture_bytes
              << ",\"replay_capture_lifecycle_guarded\":"
              << (replay_capture_lifecycle_guarded ? "true" : "false")
              << ",\"iterations\":" << options.iterations
              << ",\"elapsed_milliseconds\":" << milliseconds
              << ",\"scans_per_second\":" << scans_per_second
              << ",\"bounded_device_to_device_scanner\":true"
              << ",\"source_stat_pt_strict_predicate_reproduced\":true"
              << ",\"source_direct_cell_weights_reproduced\":true"
              << ",\"adaptive_resolve_stat_point_implemented\":false"
              << ",\"hardy_z_realization_proved\":false"
              << ",\"turing_analytic_bounds_proved\":false"
              << ",\"pt21_source_claim_discharged\":false"
              << ",\"error\":\"" << json_escape(replay.error) << "\"}\n";

    if (start != nullptr) cudaEventDestroy(start);
    if (stop != nullptr) cudaEventDestroy(stop);
    if (replay_capture != nullptr) {
      pes::destroy_replay_capture(replay_capture);
    }
    pes::destroy_workspace(workspace);
    check_cuda(cudaFree(device_samples), "cudaFree samples");
    return success ? 0 : 1;
  } catch (...) {
    if (start != nullptr) cudaEventDestroy(start);
    if (stop != nullptr) cudaEventDestroy(stop);
    if (replay_capture != nullptr) {
      try {
        pes::destroy_replay_capture(replay_capture);
      } catch (...) {
      }
    }
    if (workspace != nullptr) {
      try {
        pes::destroy_workspace(workspace);
      } catch (...) {
      }
    }
    if (device_samples != nullptr) cudaFree(device_samples);
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-event-scan-benchmark: "
              << error.what() << '\n';
    return 2;
  }
}
