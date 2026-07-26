// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only two-slot pipeline for ordinary PT21 source windows.
//
// Every logical block is synthesized, accumulated, transformed, scanned, and
// independently replayed at its own ordinary center.  The optimization only
// overlaps the ordered accumulator producer for b+1 with the transform
// consumer for b.  A separate one-stream execution is retained and every
// required sample and compact event artifact is compared byte-for-byte.
//
// This executable emits no PT21 production artifact and discharges no atom.

#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pgd = sparkinterval::tg::platt_gamma_dd_gpu;
namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
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

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

constexpr std::uint32_t kPipelineSlots = 2U;
constexpr std::uint64_t kMaximumQualificationBlocks = 64U;
constexpr std::uint64_t kOutputCells =
    static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
constexpr std::uint64_t kOneOutputRowBytes =
    kOutputCells * sizeof(pw::ComplexDisk106);
constexpr std::uint64_t kOneGammaRowBytes =
    static_cast<std::uint64_t>(pw::kBucketCount) *
    sizeof(pw::ComplexDisk106);

struct Options {
  std::string stream_path;
  std::optional<sparkinterval::Sha256Digest> expected_stream_sha256;
  std::uint32_t reanchor_blocks = 2U;
};

struct AuthenticatedInput {
  std::uint64_t first_block = 0U;
  sparkinterval::Sha256Digest stream_sha256{};
  std::vector<pg2::Record> records;
};

struct RunResult {
  std::vector<pes::ReplayReport> reports;
  double gpu_wall_seconds = 0.0;
  std::uint64_t accumulator_bytes = 0U;
  std::uint64_t transform_bytes = 0U;
  std::uint64_t scanner_bytes = 0U;
};

std::uint64_t parse_unsigned(std::string_view text, const char* label) {
  if (text.empty() || text.front() == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  std::uint64_t value = 0U;
  const auto parsed =
      std::from_chars(text.data(), text.data() + text.size(), value);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != text.data() + text.size()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return value;
}

unsigned char parse_hex_byte(char high, char low) {
  auto nibble = [](char value) -> unsigned int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
    throw std::runtime_error("stream SHA-256 is not hexadecimal");
  };
  return static_cast<unsigned char>((nibble(high) << 4U) | nibble(low));
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error(
        "expected stream SHA-256 must have 64 hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = parse_hex_byte(text[2U * index], text[2U * index + 1U]);
  }
  return result;
}

std::string hex_digest(const sparkinterval::Sha256Digest& digest) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result(64U, '0');
  for (std::size_t index = 0U; index < digest.size(); ++index) {
    result[2U * index] = digits[digest[index] >> 4U];
    result[2U * index + 1U] = digits[digest[index] & 15U];
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  if (argc < 3) {
    throw std::runtime_error(
        "usage: pt21-recentered-pipeline STREAM "
        "--expected-stream-sha256=HEX [--reanchor-blocks=N]");
  }
  Options result;
  result.stream_path = argv[1];
  for (int index = 2; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument.starts_with("--expected-stream-sha256=")) {
      if (result.expected_stream_sha256.has_value()) {
        throw std::runtime_error("expected stream SHA-256 is duplicated");
      }
      result.expected_stream_sha256 = parse_sha256(
          argument.substr(std::string_view("--expected-stream-sha256=").size()));
    } else if (argument.starts_with("--reanchor-blocks=")) {
      const std::uint64_t parsed = parse_unsigned(
          argument.substr(std::string_view("--reanchor-blocks=").size()),
          "reanchor blocks");
      if (parsed == 0U || parsed > (1U << 24U)) {
        throw std::runtime_error("reanchor blocks is outside range");
      }
      result.reanchor_blocks = static_cast<std::uint32_t>(parsed);
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (!result.expected_stream_sha256.has_value()) {
    throw std::runtime_error("expected stream SHA-256 is required");
  }
  return result;
}

void require_target_device() {
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties.major != 9 || properties.minor != 0 ||
      std::string_view(properties.name).find("H100") ==
          std::string_view::npos) {
    throw std::runtime_error(
        "strict qualification target requires an NVIDIA H100 sm_90");
  }
#endif
}

AuthenticatedInput read_input(const Options& options) {
  std::ifstream input(options.stream_path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor V2 stream");
  pg2::Reader reader(input, std::nullopt, std::nullopt,
                     options.expected_stream_sha256);
  AuthenticatedInput result;
  result.first_block = reader.header().first_block;
  const std::uint64_t count = reader.header().block_count;
  if (count < 4U || count > kMaximumQualificationBlocks) {
    throw std::runtime_error(
        "pipeline qualification requires 4..64 authenticated blocks");
  }
  result.records.reserve(static_cast<std::size_t>(count));
  pg2::AuthenticatedChunk chunk;
  while (reader.next(chunk)) {
    result.records.insert(result.records.end(), chunk.records.begin(),
                          chunk.records.end());
  }
  if (!reader.complete() || result.records.size() != count) {
    throw std::runtime_error("Gamma Taylor V2 reader accepted only a prefix");
  }
  result.stream_sha256 = reader.stream_sha256();
  return result;
}

struct Resources {
  pda::Workspace* accumulator = nullptr;
  pdt::Workspace* transform = nullptr;
  pes::Workspace* scanner = nullptr;
  pg2::Record* device_records = nullptr;
  pw::ComplexDisk106* device_gamma = nullptr;
  cudaStream_t producer = nullptr;
  cudaStream_t consumer = nullptr;
  std::array<cudaEvent_t, kPipelineSlots> ready{};
  std::array<cudaEvent_t, kPipelineSlots> consumed{};
  std::vector<pes::ReplayCapture*> captures;

  Resources() = default;
  Resources(const Resources&) = delete;
  Resources& operator=(const Resources&) = delete;

  ~Resources() {
    // Fail-closed exception cleanup: asynchronous capture copies target
    // pinned buffers owned by ReplayCapture.  Drain both streams before any
    // capture or device allocation can be released.  Destructors cannot
    // report CUDA cleanup errors, but synchronization still prevents a
    // use-after-free on every host-side throw path.
    if (producer != nullptr) cudaStreamSynchronize(producer);
    if (consumer != nullptr && consumer != producer) {
      cudaStreamSynchronize(consumer);
    }
    for (pes::ReplayCapture* capture : captures) {
      try {
        pes::destroy_replay_capture(capture);
      } catch (...) {
      }
    }
    for (cudaEvent_t event : consumed) {
      if (event != nullptr) cudaEventDestroy(event);
    }
    for (cudaEvent_t event : ready) {
      if (event != nullptr) cudaEventDestroy(event);
    }
    if (consumer != nullptr && consumer != producer) {
      cudaStreamDestroy(consumer);
    }
    if (producer != nullptr) cudaStreamDestroy(producer);
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_records != nullptr) cudaFree(device_records);
    try {
      pes::destroy_workspace(scanner);
    } catch (...) {
    }
    try {
      pdt::destroy_workspace(transform);
    } catch (...) {
    }
    try {
      pda::destroy_workspace(accumulator);
    } catch (...) {
    }
  }
};

void create_resources(const AuthenticatedInput& input,
                      std::uint32_t reanchor_blocks,
                      bool pipelined, Resources* resources) {
  if (resources == nullptr) {
    throw std::runtime_error("resource output is null");
  }
  const std::uint64_t count = input.records.size();
  if (pipelined) {
    resources->accumulator =
        pda::create_source_workspace_with_output_slots_qualification(
            input.first_block, count, reanchor_blocks, kPipelineSlots);
  } else {
    resources->accumulator = pda::create_source_workspace(
        input.first_block, count, reanchor_blocks);
  }
  resources->transform = pdt::create_source_workspace();
  resources->scanner = pes::create_workspace();
  const std::uint32_t slots = pipelined ? kPipelineSlots : 1U;
  CUDA_CHECK(cudaMalloc(&resources->device_records,
                        slots * sizeof(pg2::Record)));
  CUDA_CHECK(cudaMalloc(&resources->device_gamma,
                        static_cast<std::uint64_t>(slots) *
                            pw::kBucketCount *
                            sizeof(pw::ComplexDisk106)));
  CUDA_CHECK(cudaStreamCreateWithFlags(&resources->producer,
                                       cudaStreamNonBlocking));
  if (pipelined) {
    CUDA_CHECK(cudaStreamCreateWithFlags(&resources->consumer,
                                         cudaStreamNonBlocking));
    for (std::uint32_t slot = 0U; slot < kPipelineSlots; ++slot) {
      CUDA_CHECK(cudaEventCreateWithFlags(&resources->ready[slot],
                                          cudaEventDisableTiming));
      CUDA_CHECK(cudaEventCreateWithFlags(&resources->consumed[slot],
                                          cudaEventDisableTiming));
    }
  } else {
    resources->consumer = resources->producer;
  }
  resources->captures.reserve(input.records.size());
  for (std::size_t index = 0U; index < input.records.size(); ++index) {
    resources->captures.push_back(
        pes::create_replay_capture(resources->scanner));
  }
}

RunResult run_sequential(const AuthenticatedInput& input,
                         std::uint32_t reanchor_blocks) {
  Resources resources;
  create_resources(input, reanchor_blocks, false, &resources);
  RunResult result;
  result.accumulator_bytes =
      pda::workspace_device_bytes(resources.accumulator);
  result.transform_bytes = pdt::workspace_device_bytes(resources.transform);
  result.scanner_bytes = pes::workspace_device_bytes(resources.scanner);
  const auto started = std::chrono::steady_clock::now();
  for (std::size_t index = 0U; index < input.records.size(); ++index) {
    const std::uint64_t logical_block = input.first_block + index;
    CUDA_CHECK(cudaMemcpyAsync(resources.device_records,
                               &input.records[index], sizeof(pg2::Record),
                               cudaMemcpyHostToDevice, resources.producer));
    pgd::launch_synthesize(
        resources.device_records,
        {resources.device_gamma, 1U, pw::kBucketCount, logical_block},
        resources.producer);
    const pda::SourceWindowView view =
        pda::run_next_source_window(resources.accumulator,
                                    resources.producer);
    if (view.logical_block != logical_block) {
      throw std::runtime_error("sequential accumulator block differs");
    }
    pdt::run_source_window(resources.transform, resources.device_gamma,
                           view.device_skn_rows, resources.producer);
    const pw::RealDisk106* samples =
        pdt::device_required_samples(resources.transform);
    pes::scan_source_required_samples(resources.scanner, samples,
                                      resources.producer);
    pes::enqueue_replay_capture(resources.scanner, samples,
                                resources.captures[index],
                                resources.producer);
  }
  CUDA_CHECK(cudaStreamSynchronize(resources.producer));
  result.gpu_wall_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();
  result.reports.reserve(input.records.size());
  for (pes::ReplayCapture* capture : resources.captures) {
    result.reports.push_back(pes::replay_captured(capture));
  }
  return result;
}

RunResult run_pipelined(const AuthenticatedInput& input,
                        std::uint32_t reanchor_blocks) {
  Resources resources;
  create_resources(input, reanchor_blocks, true, &resources);
  if (pda::output_slot_count(resources.accumulator) != kPipelineSlots) {
    throw std::runtime_error("pipeline accumulator slot count differs");
  }
  RunResult result;
  result.accumulator_bytes =
      pda::workspace_device_bytes(resources.accumulator);
  result.transform_bytes = pdt::workspace_device_bytes(resources.transform);
  result.scanner_bytes = pes::workspace_device_bytes(resources.scanner);
  const auto started = std::chrono::steady_clock::now();
  for (std::size_t index = 0U; index < input.records.size(); ++index) {
    const std::uint32_t slot =
        static_cast<std::uint32_t>(index % kPipelineSlots);
    const std::uint64_t logical_block = input.first_block + index;
    if (index >= kPipelineSlots) {
      CUDA_CHECK(cudaStreamWaitEvent(resources.producer,
                                     resources.consumed[slot], 0U));
    }
    pg2::Record* const record = resources.device_records + slot;
    pw::ComplexDisk106* const gamma =
        resources.device_gamma +
        static_cast<std::uint64_t>(slot) * pw::kBucketCount;
    CUDA_CHECK(cudaMemcpyAsync(record, &input.records[index],
                               sizeof(pg2::Record), cudaMemcpyHostToDevice,
                               resources.producer));
    pgd::launch_synthesize(
        record, {gamma, 1U, pw::kBucketCount, logical_block},
        resources.producer);
    const pda::SourceWindowView view =
        pda::run_next_source_window_to_slot_qualification(
            resources.accumulator, resources.producer, slot);
    if (view.logical_block != logical_block) {
      throw std::runtime_error("pipeline accumulator block differs");
    }
    CUDA_CHECK(cudaEventRecord(resources.ready[slot], resources.producer));
    CUDA_CHECK(cudaStreamWaitEvent(resources.consumer,
                                   resources.ready[slot], 0U));
    pdt::run_source_window(resources.transform, gamma,
                           view.device_skn_rows, resources.consumer);
    // All transform kernels that read gamma or the accumulator row precede
    // this event.  Scanner/capture work below reads only transform outputs.
    CUDA_CHECK(cudaEventRecord(resources.consumed[slot],
                               resources.consumer));
    const pw::RealDisk106* samples =
        pdt::device_required_samples(resources.transform);
    pes::scan_source_required_samples(resources.scanner, samples,
                                      resources.consumer);
    pes::enqueue_replay_capture(resources.scanner, samples,
                                resources.captures[index],
                                resources.consumer);
  }
  CUDA_CHECK(cudaStreamSynchronize(resources.producer));
  CUDA_CHECK(cudaStreamSynchronize(resources.consumer));
  result.gpu_wall_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();
  result.reports.reserve(input.records.size());
  for (pes::ReplayCapture* capture : resources.captures) {
    result.reports.push_back(pes::replay_captured(capture));
  }
  return result;
}

template <typename T>
bool vector_bytes_equal(const std::vector<T>& first,
                        const std::vector<T>& second) {
  return first.size() == second.size() &&
         (first.empty() ||
          std::memcmp(first.data(), second.data(),
                      first.size() * sizeof(T)) == 0);
}

bool artifact_bytes_equal(const pes::HostArtifact& first,
                          const pes::HostArtifact& second) {
  if (std::memcmp(&first.status, &second.status,
                  sizeof(first.status)) != 0 ||
      std::memcmp(first.summaries.data(), second.summaries.data(),
                  sizeof(first.summaries)) != 0) {
    return false;
  }
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    if (!vector_bytes_equal(first.direct[stream], second.direct[stream]) ||
        !vector_bytes_equal(first.stationary[stream],
                            second.stationary[stream])) {
      return false;
    }
  }
  return true;
}

struct Comparison {
  std::uint64_t sample_mismatch_blocks = 0U;
  std::uint64_t artifact_mismatch_blocks = 0U;
  std::uint64_t replay_failure_blocks = 0U;
  std::uint64_t first_blocks = 0U;
  std::uint64_t interior_blocks = 0U;
  std::uint64_t reanchor_blocks = 0U;
  std::uint64_t terminal_blocks = 0U;
};

Comparison compare(const RunResult& sequential, const RunResult& pipelined,
                   std::uint32_t reanchor_blocks) {
  if (sequential.reports.size() != pipelined.reports.size()) {
    throw std::runtime_error("pipeline result cardinality differs");
  }
  Comparison result;
  for (std::size_t index = 0U; index < sequential.reports.size(); ++index) {
    const pes::ReplayReport& first = sequential.reports[index];
    const pes::ReplayReport& second = pipelined.reports[index];
    if (!first.accepted || !first.device_matches_host ||
        !second.accepted || !second.device_matches_host) {
      ++result.replay_failure_blocks;
    }
    if (!vector_bytes_equal(first.required_samples,
                            second.required_samples)) {
      ++result.sample_mismatch_blocks;
    }
    if (!artifact_bytes_equal(first.artifact, second.artifact)) {
      ++result.artifact_mismatch_blocks;
    }
    if (index == 0U) ++result.first_blocks;
    if (index + 1U == sequential.reports.size()) {
      ++result.terminal_blocks;
    }
    if (index != 0U && index % reanchor_blocks == 0U) {
      ++result.reanchor_blocks;
    } else if (index != 0U && index + 1U != sequential.reports.size()) {
      ++result.interior_blocks;
    }
  }
  return result;
}

int run(const Options& options) {
  require_target_device();
  const AuthenticatedInput input = read_input(options);
  const RunResult sequential =
      run_sequential(input, options.reanchor_blocks);
  const RunResult pipelined =
      run_pipelined(input, options.reanchor_blocks);
  const Comparison comparison =
      compare(sequential, pipelined, options.reanchor_blocks);
  if (pipelined.accumulator_bytes < sequential.accumulator_bytes ||
      pipelined.accumulator_bytes - sequential.accumulator_bytes !=
          kOneOutputRowBytes) {
    throw std::runtime_error(
        "two-slot accumulator allocation delta differs from one output row");
  }
  const bool categories_complete =
      comparison.first_blocks != 0U &&
      comparison.interior_blocks != 0U &&
      comparison.reanchor_blocks != 0U &&
      comparison.terminal_blocks != 0U;
  const bool accepted =
      categories_complete && comparison.sample_mismatch_blocks == 0U &&
      comparison.artifact_mismatch_blocks == 0U &&
      comparison.replay_failure_blocks == 0U;
  const double speedup =
      sequential.gpu_wall_seconds / pipelined.gpu_wall_seconds;
  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.pt21-recentered-pipeline-qualification.v1\""
            << ",\"accepted\":" << (accepted ? "true" : "false")
            << ",\"qualification_only\":true"
            << ",\"build_profile\":{\"cmake_build_config\":\""
            << kCmakeBuildConfig << "\",\"ndebug_defined\":"
            << (kNdebugDefined ? "true" : "false")
            << ",\"release_performance_build\":"
            << (kReleasePerformanceBuild ? "true" : "false") << '}'
            << ",\"stream_sha256\":\""
            << hex_digest(input.stream_sha256) << "\""
            << ",\"first_block\":" << input.first_block
            << ",\"block_count\":" << input.records.size()
            << ",\"reanchor_blocks\":" << options.reanchor_blocks
            << ",\"pipeline_slots\":2"
            << ",\"ordinary_center_per_logical_block\":true"
            << ",\"shifted_view_reuse\":false"
            << ",\"sequential_gpu_wall_seconds\":"
            << sequential.gpu_wall_seconds
            << ",\"pipelined_gpu_wall_seconds\":"
            << pipelined.gpu_wall_seconds
            << ",\"measured_speedup\":" << speedup
            << ",\"sequential_accumulator_bytes\":"
            << sequential.accumulator_bytes
            << ",\"pipelined_accumulator_bytes\":"
            << pipelined.accumulator_bytes
            << ",\"extra_accumulator_output_bytes\":"
            << (pipelined.accumulator_bytes -
                sequential.accumulator_bytes)
            << ",\"extra_gamma_row_bytes\":" << kOneGammaRowBytes
            << ",\"transform_workspace_bytes\":"
            << sequential.transform_bytes
            << ",\"scanner_workspace_bytes\":"
            << sequential.scanner_bytes
            << ",\"sample_mismatch_blocks\":"
            << comparison.sample_mismatch_blocks
            << ",\"artifact_mismatch_blocks\":"
            << comparison.artifact_mismatch_blocks
            << ",\"replay_failure_blocks\":"
            << comparison.replay_failure_blocks
            << ",\"first_category_blocks\":"
            << comparison.first_blocks
            << ",\"interior_category_blocks\":"
            << comparison.interior_blocks
            << ",\"reanchor_category_blocks\":"
            << comparison.reanchor_blocks
            << ",\"terminal_category_blocks\":"
            << comparison.terminal_blocks
            << ",\"byte_identical_required_samples\":"
            << (comparison.sample_mismatch_blocks == 0U ? "true" : "false")
            << ",\"byte_identical_event_artifacts\":"
            << (comparison.artifact_mismatch_blocks == 0U ? "true" : "false")
            << ",\"independent_fixed_integer_replay_complete\":"
            << (comparison.replay_failure_blocks == 0U ? "true" : "false")
            << ",\"categories_complete\":"
            << (categories_complete ? "true" : "false")
            << ",\"production_worker_changed\":false"
            << ",\"production_ready\":false"
            << ",\"pt21_atom_discharged\":false}\n";
  return accepted ? 0 : 3;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr
        << "{\"schema\":\"sparkinterval.tg.pt21-recentered-pipeline-qualification.v1\""
        << ",\"accepted\":false,\"qualification_only\":true"
        << ",\"error\":\"" << error.what() << "\""
        << ",\"production_ready\":false"
        << ",\"pt21_atom_discharged\":false}\n";
    return 2;
  }
}
