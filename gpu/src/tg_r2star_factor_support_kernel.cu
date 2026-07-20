// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_r2star_factor_support.h"

#include <cstddef>
#include <cstdint>
#include <limits>

#include <cuda_runtime.h>

namespace {

constexpr std::uint64_t kEmptyPrime = 0xffffffffffffffffULL;
constexpr unsigned int kThreadsPerBlock = 256;
constexpr std::size_t kMaximumGridX = 0x7fffffffULL;

__device__ __forceinline__ void insert_small_prime(
    TgR2StarFactorSupport* record, std::uint32_t prime) {
  // atomicMin linearizes insertion into the two-smallest set independently of
  // the order in which prime blocks reach this record.
  const auto prime64 = static_cast<unsigned long long>(prime);
  const std::uint64_t previous_first = atomicMin(
      reinterpret_cast<unsigned long long*>(&record->first_prime), prime64);
  if (previous_first == kEmptyPrime) return;
  const std::uint64_t second_candidate =
      prime < previous_first ? previous_first : prime;
  atomicMin(reinterpret_cast<unsigned long long*>(&record->second_prime),
            static_cast<unsigned long long>(second_candidate));
}

__global__ void initialize_factor_support(TgR2StarFactorSupport* outputs,
                                          std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  outputs[index].first_prime = kEmptyPrime;
  outputs[index].second_prime = kEmptyPrime;
  outputs[index].distinct_prime_factor_count = 0;
  outputs[index].reserved = 0;
}

// Each block owns one base prime.  Its threads partition that prime's
// multiples in the requested segment, so the factor count is incremented
// exactly once per distinct base prime.
__global__ void mark_base_prime_multiples(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgR2StarFactorSupport* outputs) {
  const std::uint32_t prime = base_primes[blockIdx.x];
  if (prime < 2) return;
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count; offset += stride) {
    TgR2StarFactorSupport* record = &outputs[offset];
    atomicAdd(&record->distinct_prime_factor_count, 1U);
    insert_small_prime(record, prime);
  }
}

__global__ void finalize_factor_support(std::uint64_t lower,
                                        std::size_t count,
                                        TgR2StarFactorSupport* outputs) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;

  const std::uint64_t number = lower + index;
  TgR2StarFactorSupport* record = &outputs[index];
  std::uint32_t base_count = record->distinct_prime_factor_count;
  std::uint64_t first = record->first_prime;
  std::uint64_t second = record->second_prime;

  if (number < 2) {
    record->first_prime = 0;
    record->second_prime = 0;
    record->distinct_prime_factor_count = 0;
    record->reserved = 0;
    return;
  }

  if (base_count >= 3) {
    record->first_prime = first;
    record->second_prime = second;
    record->distinct_prime_factor_count = 3;
    record->reserved = 0;
    return;
  }

  std::uint64_t remaining = number;
  if (base_count >= 1) {
    while (remaining % first == 0) remaining /= first;
  }
  if (base_count >= 2) {
    while (remaining % second == 0) remaining /= second;
  }

  if (remaining > 1) {
    const std::uint64_t residual = remaining;
    if (base_count == 0) {
      first = residual;
    } else if (base_count == 1) {
      second = residual;
    }
    ++base_count;
  }

  record->first_prime = base_count >= 1 ? first : 0;
  record->second_prime = base_count >= 2 ? second : 0;
  record->distinct_prime_factor_count = base_count >= 3 ? 3 : base_count;
  record->reserved = 0;
}

cudaError_t check_launch() {
  return cudaGetLastError();
}

}  // namespace

cudaError_t launch_tg_r2star_factor_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    TgR2StarFactorSupport* outputs, cudaStream_t stream) {
  if (lower == 0 || count == 0 || outputs == nullptr ||
      (base_prime_count != 0 && base_primes == nullptr)) {
    return cudaErrorInvalidValue;
  }
  if (count - 1 > std::numeric_limits<std::uint64_t>::max() - lower ||
      base_prime_count > kMaximumGridX) {
    return cudaErrorInvalidValue;
  }
  const std::size_t block_count =
      (count + kThreadsPerBlock - 1) / kThreadsPerBlock;
  if (block_count > kMaximumGridX) return cudaErrorInvalidConfiguration;

  initialize_factor_support<<<static_cast<unsigned int>(block_count),
                              kThreadsPerBlock, 0, stream>>>(outputs, count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;

  if (base_prime_count != 0) {
    mark_base_prime_multiples<<<static_cast<unsigned int>(base_prime_count),
                                kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, outputs);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }

  finalize_factor_support<<<static_cast<unsigned int>(block_count),
                            kThreadsPerBlock, 0, stream>>>(lower, count,
                                                           outputs);
  return check_launch();
}
