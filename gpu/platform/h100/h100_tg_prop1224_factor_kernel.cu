// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_prop1224_factor.hpp"

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::prop1224 {
namespace {

constexpr std::uint64_t kDenseRows = 3'299'999'999ULL;
constexpr std::uint64_t kFirstExtensionQ = 3'300'000'060ULL;
constexpr std::uint64_t kExtensionDivisor = 210ULL;

__device__ std::uint64_t qAtRank(std::uint64_t rank) {
  if (rank < kDenseRows) return rank + 1;
  return kFirstExtensionQ + (rank - kDenseRows) * kExtensionDivisor;
}

__global__ void replayKernel(const FactorRecord* records,
                             std::uint32_t* outputFlags,
                             std::uint64_t rankLower, std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const FactorRecord& record = records[index];
  std::uint32_t flags = 0;
  const std::uint64_t expectedQ = qAtRank(rankLower + index);
  if (record.q == expectedQ) flags |= kSchedulerMatches;

  bool sorted = record.factor_count <= kPackedFactorCapacity;
  bool positiveExponents = sorted;
  bool unusedZero = sorted;
  bool productValid = sorted;
  std::uint64_t product = 1;
  std::uint64_t phi = record.q;
  std::uint64_t previous = 0;
  for (std::size_t position = 0; position < kPackedFactorCapacity; ++position) {
    const std::uint64_t prime = record.prime[position];
    const std::uint8_t exponent = record.exponent[position];
    if (position >= record.factor_count) {
      if (prime != 0 || exponent != 0) unusedZero = false;
      continue;
    }
    if (prime < 2 || prime <= previous) sorted = false;
    if (exponent == 0) positiveExponents = false;
    previous = prime;
    if (prime == 0 || record.q % prime != 0) productValid = false;
    if (prime != 0) phi -= phi / prime;
    for (std::uint8_t power = 0; power < exponent; ++power) {
      if (prime == 0 || product > UINT64_MAX / prime) {
        productValid = false;
      } else {
        product *= prime;
      }
    }
  }
  if (sorted) flags |= kFactorsStrictlyIncreasing;
  if (positiveExponents) flags |= kExponentsPositive;
  if (unusedZero) flags |= kUnusedSlotsZero;
  if (productValid && product == record.q) flags |= kProductMatches;
  if (record.phi == phi) flags |= kPhiMatches;
  outputFlags[index] = flags;
}

}  // namespace

cudaError_t launchProp1224FactorReplay(
    const FactorRecord* deviceRecords, std::uint32_t* deviceOutputFlags,
    std::uint64_t rankLower, std::size_t count, cudaStream_t stream) {
  if (count == 0) return cudaSuccess;
  constexpr unsigned threads = 256;
  const std::size_t blocks = (count + threads - 1) / threads;
  if (blocks > static_cast<std::size_t>(UINT32_MAX)) {
    return cudaErrorInvalidConfiguration;
  }
  replayKernel<<<static_cast<unsigned>(blocks), threads, 0, stream>>>(
      deviceRecords, deviceOutputFlags, rankLower, count);
  return cudaGetLastError();
}

}  // namespace sparkinterval::tg::prop1224
