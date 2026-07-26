// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT
//
// Qualification-only PT21 source-accumulator schedule benchmark.  This
// executable never emits a production receipt and never changes the default
// accumulator archive.

#include "sparkinterval/tg_platt_dd_accumulator.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <bit>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pw = sparkinterval::tg::platt_windowed;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                 \
                               cudaGetErrorString(status_));                  \
    }                                                                        \
  } while (0)

constexpr std::uint64_t kOutputCells =
    static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
constexpr std::uint64_t kOutputBytes =
    kOutputCells * sizeof(pw::ComplexDisk106);

struct Candidate {
  const char* label;
  pda::QualificationSchedule schedule;
  std::uint32_t value_load_rounds;
};

double median(std::vector<float> values) {
  std::sort(values.begin(), values.end());
  const std::size_t middle = values.size() / 2U;
  if ((values.size() & 1U) != 0U) return values[middle];
  return 0.5 * (values[middle - 1U] + values[middle]);
}

float time_one(pda::Workspace* workspace, cudaStream_t stream,
               pda::QualificationSchedule schedule, cudaEvent_t start,
               cudaEvent_t stop) {
  CUDA_CHECK(cudaEventRecord(start, stream));
  static_cast<void>(pda::rerun_last_source_window_qualification(
      workspace, stream, 1U, schedule));
  CUDA_CHECK(cudaEventRecord(stop, stream));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&milliseconds, start, stop));
  return milliseconds;
}

std::uint64_t fnv1a64(const std::vector<pw::ComplexDisk106>& values) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = reinterpret_cast<const unsigned char*>(values.data());
  for (std::uint64_t index = 0U; index < kOutputBytes; ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

int run(std::uint32_t repetitions) {
  cudaStream_t stream{};
  cudaEvent_t start{};
  cudaEvent_t stop{};
  pda::Workspace* workspace = nullptr;
  try {
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    workspace =
        pda::create_source_workspace_with_output_slots_qualification(
            0U, 1U, 256U, 2U);
    const pda::SourceWindowView baseline =
        pda::run_next_source_window_to_slot_qualification(
            workspace, stream, 0U);
    CUDA_CHECK(cudaStreamSynchronize(stream));

    std::vector<pw::ComplexDisk106> baseline_values(kOutputCells);
    std::vector<pw::ComplexDisk106> candidate_values(kOutputCells);
    CUDA_CHECK(cudaMemcpy(baseline_values.data(), baseline.device_skn_rows,
                          kOutputBytes, cudaMemcpyDeviceToHost));

    std::vector<std::uint32_t> offsets(pw::kBucketCount + 1U);
    CUDA_CHECK(cudaMemcpy(
        offsets.data(),
        pda::device_bucket_offsets_qualification(workspace),
        offsets.size() * sizeof(std::uint32_t), cudaMemcpyDeviceToHost));
    std::uint32_t maximum_bucket_terms = 0U;
    std::uint64_t total_bucket_chunks = 0U;
    for (std::uint32_t bucket = 0U; bucket < pw::kBucketCount; ++bucket) {
      const std::uint32_t count = offsets[bucket + 1U] - offsets[bucket];
      maximum_bucket_terms = std::max(maximum_bucket_terms, count);
      total_bucket_chunks += (count + 31U) / 32U;
    }

    constexpr Candidate candidates[] = {
        {"warp12", pda::QualificationSchedule::kWarp12, 23U},
        {"warp16", pda::QualificationSchedule::kWarp16, 23U},
        {"warp24", pda::QualificationSchedule::kWarp24, 23U},
        {"shared8", pda::QualificationSchedule::kShared8, 3U},
        {"shared12", pda::QualificationSchedule::kShared12, 2U},
        {"precomputed-l1-warp8",
         pda::QualificationSchedule::kPrecomputedL1Warp8, 23U},
        {"precomputed-l1-power-abs-warp8",
         pda::QualificationSchedule::kPrecomputedL1PowerAbsWarp8, 23U},
    };
    std::vector<float> baseline_times;
    baseline_times.reserve(repetitions * std::size(candidates));
    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.pt21-accumulator-"
                 "schedule-benchmark.v1\""
              << ",\"qualification_only\":true"
              << ",\"production_default_changed\":false"
              << ",\"logical_block\":" << baseline.logical_block
              << ",\"output_cells\":" << kOutputCells
              << ",\"output_bytes\":" << kOutputBytes
              << ",\"active_buckets\":"
              << pda::active_bucket_count_qualification(workspace)
              << ",\"maximum_bucket_terms\":" << maximum_bucket_terms
              << ",\"total_bucket_chunks\":" << total_bucket_chunks
              << ",\"repetitions\":" << repetitions
              << ",\"baseline_fnv1a64\":\"" << std::hex
              << std::setw(16) << std::setfill('0')
              << fnv1a64(baseline_values) << std::dec
              << std::setfill(' ') << "\",\"candidates\":[";
    bool first = true;
    for (const Candidate candidate : candidates) {
      static_cast<void>(pda::rerun_last_source_window_qualification(
          workspace, stream, 1U, candidate.schedule));
      CUDA_CHECK(cudaStreamSynchronize(stream));
      const pda::SourceWindowView candidate_view =
          pda::rerun_last_source_window_qualification(
              workspace, stream, 1U, candidate.schedule);
      CUDA_CHECK(cudaStreamSynchronize(stream));
      CUDA_CHECK(cudaMemcpy(candidate_values.data(),
                            candidate_view.device_skn_rows, kOutputBytes,
                            cudaMemcpyDeviceToHost));
      std::uint64_t mismatched_bytes = 0U;
      const auto* baseline_bytes =
          reinterpret_cast<const unsigned char*>(baseline_values.data());
      const auto* candidate_bytes =
          reinterpret_cast<const unsigned char*>(candidate_values.data());
      for (std::uint64_t index = 0U; index < kOutputBytes; ++index) {
        mismatched_bytes += baseline_bytes[index] != candidate_bytes[index];
      }

      std::vector<float> candidate_times;
      candidate_times.reserve(repetitions);
      std::vector<float> paired_baseline_times;
      paired_baseline_times.reserve(repetitions);
      for (std::uint32_t repetition = 0U; repetition < repetitions;
           ++repetition) {
        const float baseline_ms = time_one(
            workspace, stream, pda::QualificationSchedule::kBaseline8,
            start, stop);
        const float candidate_ms =
            time_one(workspace, stream, candidate.schedule, start, stop);
        paired_baseline_times.push_back(baseline_ms);
        baseline_times.push_back(baseline_ms);
        candidate_times.push_back(candidate_ms);
      }
      const double baseline_median = median(paired_baseline_times);
      const double candidate_median = median(candidate_times);
      const pda::QualificationKernelResources resources =
          pda::qualification_kernel_resources(candidate.schedule);
      if (!first) std::cout << ',';
      first = false;
      std::cout
          << "{\"label\":\"" << candidate.label << "\""
          << ",\"exact_byte_identity\":"
          << (mismatched_bytes == 0U ? "true" : "false")
          << ",\"mismatched_bytes\":" << mismatched_bytes
          << ",\"value_load_rounds_per_bucket\":"
          << candidate.value_load_rounds
          << ",\"paired_baseline_median_ms\":" << baseline_median
          << ",\"candidate_median_ms\":" << candidate_median
          << ",\"speedup\":"
          << baseline_median / candidate_median
          << ",\"resources\":{\"registers_per_thread\":"
          << resources.registers_per_thread
          << ",\"static_shared_bytes\":"
          << resources.static_shared_bytes
          << ",\"local_bytes_per_thread\":"
          << resources.local_bytes_per_thread
          << ",\"maximum_threads_per_block\":"
          << resources.maximum_threads_per_block
          << ",\"active_blocks_per_multiprocessor\":"
          << resources.active_blocks_per_multiprocessor
          << ",\"threads_per_block\":"
          << resources.threads_per_block << "}}";
    }
    std::cout << "],\"accepted\":true}\n";
    pda::destroy_workspace(workspace);
    workspace = nullptr;
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaStreamDestroy(stream));
    return 0;
  } catch (...) {
    if (workspace != nullptr) pda::destroy_workspace(workspace);
    if (stop != nullptr) cudaEventDestroy(stop);
    if (start != nullptr) cudaEventDestroy(start);
    if (stream != nullptr) cudaStreamDestroy(stream);
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::uint32_t repetitions = 5U;
    if (argc == 2) {
      const std::string argument(argv[1]);
      constexpr const char prefix[] = "--repetitions=";
      if (argument.rfind(prefix, 0U) != 0U) {
        throw std::runtime_error("expected --repetitions=N");
      }
      repetitions = static_cast<std::uint32_t>(
          std::stoul(argument.substr(sizeof(prefix) - 1U)));
      if (repetitions == 0U || repetitions > 20U) {
        throw std::runtime_error("repetitions must be in 1..20");
      }
    } else if (argc != 1) {
      throw std::runtime_error("expected at most one option");
    }
    return run(repetitions);
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-pt21-accumulator-schedule-"
                 "benchmark: "
              << error.what() << '\n';
    return 2;
  }
}
