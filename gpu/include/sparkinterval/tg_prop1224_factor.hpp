// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

namespace sparkinterval::tg::prop1224 {

constexpr std::size_t kPackedFactorCapacity = 16;

// Packed complete factorization supplied by the exact segmented CPU stage.
// The GPU is a high-throughput structural replay, not the primality authority:
// every accepted campaign leaf must still replay factor primality against the
// deterministic CPU Eratosthenes table before using this record in a proof.
struct FactorRecord {
  std::uint64_t q;
  std::uint64_t phi;
  std::uint64_t prime[kPackedFactorCapacity];
  std::uint8_t exponent[kPackedFactorCapacity];
  std::uint8_t factor_count;
  std::uint8_t reserved[7];
};

enum FactorReplayFlag : std::uint32_t {
  kSchedulerMatches = 1U << 0,
  kFactorsStrictlyIncreasing = 1U << 1,
  kExponentsPositive = 1U << 2,
  kProductMatches = 1U << 3,
  kPhiMatches = 1U << 4,
  kUnusedSlotsZero = 1U << 5,
};

constexpr std::uint32_t kAllStructuralReplayFlags =
    kSchedulerMatches | kFactorsStrictlyIncreasing | kExponentsPositive |
    kProductMatches | kPhiMatches | kUnusedSlotsZero;

// Launch one record per source q rank.  rank_lower + count must not exceed
// 3,389,047,618; the host caller owns that fail-closed range check.  CUDA
// launch/runtime failures are returned normally.  A record is structurally
// accepted exactly when output_flags[i] == kAllStructuralReplayFlags.
cudaError_t launchProp1224FactorReplay(
    const FactorRecord* device_records, std::uint32_t* device_output_flags,
    std::uint64_t rank_lower, std::size_t count, cudaStream_t stream);

}  // namespace sparkinterval::tg::prop1224
