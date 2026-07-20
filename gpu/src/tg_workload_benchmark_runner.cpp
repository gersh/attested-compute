#include "tg_workload_benchmark.h"

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string_view>

#include <cuda_runtime_api.h>

namespace {

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  std::cerr << operation << " failed: " << cudaGetErrorString(status) << '\n';
  std::exit(2);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) fail_cuda(operation, status);
}

bool parse_u64(std::string_view text, std::uint64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

}  // namespace

int main(int argc, char** argv) {
  std::uint64_t count = 1ULL << 24;
  std::uint64_t repetitions = 10;
  for (int i = 1; i < argc; ++i) {
    const std::string_view argument(argv[i]);
    if (argument == "--count" && i + 1 < argc) {
      if (!parse_u64(argv[++i], &count)) {
        std::cerr << "invalid --count\n";
        return 2;
      }
    } else if (argument == "--repetitions" && i + 1 < argc) {
      if (!parse_u64(argv[++i], &repetitions)) {
        std::cerr << "invalid --repetitions\n";
        return 2;
      }
    } else {
      std::cerr << "unknown or incomplete argument: " << argument << '\n';
      return 2;
    }
  }
  if (count == 0 || repetitions == 0 ||
      count > std::numeric_limits<std::size_t>::max() / sizeof(std::uint64_t)) {
    std::cerr << "count and repetitions must be positive and allocation-safe\n";
    return 2;
  }

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count < 1) {
    std::cerr << "no CUDA device found\n";
    return 3;
  }
  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties", cudaGetDeviceProperties(&properties, 0));

  std::uint64_t* output = nullptr;
  const std::size_t bytes = static_cast<std::size_t>(count) * sizeof(*output);
  check_cuda("cudaMalloc", cudaMalloc(reinterpret_cast<void**>(&output), bytes));

  for (int warmup = 0; warmup < 3; ++warmup) {
    check_cuda("warmup launch", launch_tg_workload_benchmark(0, count, output, 0));
  }
  check_cuda("warmup synchronize", cudaDeviceSynchronize());

  cudaEvent_t start{};
  cudaEvent_t stop{};
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  for (std::uint64_t repeat = 0; repeat < repetitions; ++repeat) {
    check_cuda("benchmark launch",
               launch_tg_workload_benchmark(repeat * count, count, output, 0));
  }
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float elapsed_milliseconds = 0;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&elapsed_milliseconds, start, stop));

  std::uint64_t first = 0;
  std::uint64_t last = 0;
  check_cuda("copy first", cudaMemcpy(&first, output, sizeof(first), cudaMemcpyDeviceToHost));
  check_cuda("copy last",
             cudaMemcpy(&last, output + count - 1, sizeof(last), cudaMemcpyDeviceToHost));
  const std::uint64_t final_start = (repetitions - 1) * count;
  const bool endpoint_check =
      first == tg_workload_reference(final_start) &&
      last == tg_workload_reference(final_start + count - 1);

  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  check_cuda("cudaFree", cudaFree(output));

  const double seconds = static_cast<double>(elapsed_milliseconds) / 1000.0;
  const long double items =
      static_cast<long double>(count) * static_cast<long double>(repetitions);
  const long double rate = items / seconds;
  const long double write_bandwidth = rate * sizeof(std::uint64_t);
  std::cout << std::setprecision(17)
            << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"benchmark\": \"tg_integer_work_item_microbenchmark\",\n"
            << "  \"classification\": \"planning_microbenchmark_not_verification\",\n"
            << "  \"device_name\": \"" << properties.name << "\",\n"
            << "  \"compute_capability\": \"" << properties.major << '.'
            << properties.minor << "\",\n"
            << "  \"count_per_repetition\": " << count << ",\n"
            << "  \"repetitions\": " << repetitions << ",\n"
            << "  \"kernel_milliseconds\": " << elapsed_milliseconds << ",\n"
            << "  \"work_items_per_second\": " << static_cast<double>(rate) << ",\n"
            << "  \"minimum_output_bytes_per_second\": "
            << static_cast<double>(write_bandwidth) << ",\n"
            << "  \"endpoint_check\": " << (endpoint_check ? "true" : "false")
            << ",\n"
            << "  \"proves_any_external_atom\": false\n"
            << "}\n";
  return endpoint_check ? 0 : 4;
}
