#include "tg_workload_benchmark.h"

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include <cstdint>

namespace {

constexpr std::uint64_t kScale = 1000000000000000000ULL;

__host__ __device__ std::uint64_t work_item(std::uint64_t index) {
  const std::uint64_t n = index + 1;
  const std::uint64_t quotient = kScale / n;
  const std::uint64_t remainder = kScale - quotient * n;
#if defined(__CUDA_ARCH__)
  const std::uint64_t product_high = __umul64hi(n, n ^ quotient);
#else
  const unsigned __int128 product =
      static_cast<unsigned __int128>(n) * (n ^ quotient);
  const std::uint64_t product_high = static_cast<std::uint64_t>(product >> 64);
#endif
  std::uint64_t mixed = quotient ^ (remainder << 1) ^ product_high;
  mixed ^= n * 0x9e3779b97f4a7c15ULL;
  mixed ^= mixed >> 29;
  mixed *= 0xbf58476d1ce4e5b9ULL;
  return mixed ^ (mixed >> 31);
}

__global__ void tg_workload_kernel(std::uint64_t start,
                                   std::uint64_t count,
                                   std::uint64_t* output) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < count) {
    output[index] = work_item(start + index);
  }
}

}  // namespace

std::uint64_t tg_workload_reference(std::uint64_t index) {
  return work_item(index);
}

cudaError_t launch_tg_workload_benchmark(std::uint64_t start,
                                         std::uint64_t count,
                                         std::uint64_t* output,
                                         cudaStream_t stream) {
  constexpr unsigned threads = 256;
  const std::uint64_t blocks64 = (count + threads - 1) / threads;
  if (blocks64 > 0x7fffffffULL) return cudaErrorInvalidConfiguration;
  tg_workload_kernel<<<static_cast<unsigned>(blocks64), threads, 0, stream>>>(
      start, count, output);
  return cudaGetLastError();
}
