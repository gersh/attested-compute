// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"

#include <cstddef>
#include <cstdint>
#include <limits>

#include <cuda_runtime.h>

namespace {

constexpr unsigned int kThreadsPerBlock = 256;
constexpr std::size_t kMaximumGridX = 0x7fffffffULL;

__device__ __forceinline__ void atomic_multiply_exact_divisor(
    std::uint64_t* destination, std::uint32_t prime) {
  auto* target = reinterpret_cast<unsigned long long*>(destination);
  unsigned long long observed = atomicCAS(target, 0ULL, 0ULL);
  for (;;) {
    const unsigned long long assumed = observed;
    // Every intermediate product is a product of distinct divisors of n, so
    // it divides n and cannot overflow the supported source range.
    const unsigned long long desired =
        assumed * static_cast<unsigned long long>(prime);
    observed = atomicCAS(target, assumed, desired);
    if (observed == assumed) return;
  }
}

__global__ void initialize_mobius_support(TgMobiusSupport* outputs,
                                           std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  outputs[index].base_prime_product = 1;
  outputs[index].distinct_base_prime_count = 0;
  outputs[index].squareful = 0;
  outputs[index].mobius = 0;
  outputs[index].reserved = 0;
}

__device__ __forceinline__ void mark_one_multiple(
    std::uint64_t lower, std::uint64_t offset, std::uint64_t prime,
    TgMobiusSupport* outputs) {
  TgMobiusSupport* record = &outputs[offset];
  atomicAdd(&record->distinct_base_prime_count, 1U);
  atomic_multiply_exact_divisor(&record->base_prime_product,
                                static_cast<std::uint32_t>(prime));
  const std::uint64_t number = lower + offset;
  if ((number / prime) % prime == 0) atomicExch(&record->squareful, 1U);
}

// Small primes have many multiples.  One block owns each such prime and its
// threads partition the multiples, avoiding a serial p=2 bottleneck.
__global__ void mark_dense_prime_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, TgMobiusSupport* outputs) {
  const std::uint64_t prime = base_primes[blockIdx.x];
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count; offset += stride) {
    mark_one_multiple(lower, offset, prime, outputs);
  }
}

// Large primes have fewer than one block's worth of multiples.  One thread
// per prime avoids launching hundreds of idle threads for each sparse row.
__global__ void mark_sparse_prime_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count, TgMobiusSupport* outputs) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  for (std::uint64_t offset = first_offset; offset < count; offset += prime) {
    mark_one_multiple(lower, offset, prime, outputs);
  }
}

__global__ void finalize_mobius_support(std::uint64_t lower,
                                        std::size_t count,
                                        TgMobiusSupport* outputs) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t number = lower + index;
  TgMobiusSupport* record = &outputs[index];
  if (record->squareful != 0) {
    record->mobius = 0;
    record->reserved = 0;
    return;
  }
  const std::uint64_t residual = number / record->base_prime_product;
  const std::uint32_t omega = record->distinct_base_prime_count +
                              static_cast<std::uint32_t>(residual > 1);
  record->mobius = (omega & 1U) == 0 ? 1 : -1;
  record->reserved = 0;
}

cudaError_t check_launch() { return cudaGetLastError(); }

}  // namespace

cudaError_t launch_tg_mobius_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusSupport* outputs, cudaStream_t stream) {
  if (lower == 0 || count == 0 || outputs == nullptr ||
      (base_prime_count != 0 && base_primes == nullptr) ||
      dense_prime_count > base_prime_count) {
    return cudaErrorInvalidValue;
  }
  if (count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t output_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  const std::size_t sparse_prime_count = base_prime_count - dense_prime_count;
  const std::size_t sparse_blocks =
      sparse_prime_count == 0
          ? 0
          : 1 + (sparse_prime_count - 1) / kThreadsPerBlock;
  if (output_blocks > kMaximumGridX || dense_prime_count > kMaximumGridX ||
      sparse_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }

  initialize_mobius_support<<<static_cast<unsigned int>(output_blocks),
                              kThreadsPerBlock, 0, stream>>>(outputs, count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  if (dense_prime_count != 0) {
    mark_dense_prime_support<<<static_cast<unsigned int>(dense_prime_count),
                               kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, outputs);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (sparse_prime_count != 0) {
    mark_sparse_prime_support<<<static_cast<unsigned int>(sparse_blocks),
                                kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, dense_prime_count, base_prime_count,
        outputs);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  finalize_mobius_support<<<static_cast<unsigned int>(output_blocks),
                            kThreadsPerBlock, 0, stream>>>(lower, count,
                                                           outputs);
  return check_launch();
}
