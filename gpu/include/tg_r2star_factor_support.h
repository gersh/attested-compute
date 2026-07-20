// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

// A compact description of the distinct-prime-factor support of one integer.
// distinct_prime_factor_count is min(omega(n), 3).  When the count is one or
// two, first_prime and second_prime contain the factors in increasing order.
// A count of three means "at least three"; only the two smallest factors are
// retained.  The record for n = 1 is all zero.
struct alignas(8) TgR2StarFactorSupport {
  std::uint64_t first_prime;
  std::uint64_t second_prime;
  std::uint32_t distinct_prime_factor_count;
  std::uint32_t reserved;
};

static_assert(sizeof(TgR2StarFactorSupport) == 24);

// Produce factor-support records for n in [lower, lower + count).  The caller
// must provide, once each and in increasing order, every prime not exceeding
// floor(sqrt(lower + count - 1)).  The public runner constructs that list with
// an exact host sieve and independently validates every returned record.
cudaError_t launch_tg_r2star_factor_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    TgR2StarFactorSupport* outputs, cudaStream_t stream = nullptr);
