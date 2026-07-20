// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

// Exact integer support for a segmented Moebius computation.  The product
// and count refer to the distinct supplied base primes which divide n.
// squareful is one exactly when some supplied p has p^2 | n.  When the caller
// supplies every prime through sqrt(segment upper), mobius is the mathematical
// Moebius value of n.
struct alignas(8) TgMobiusSupport {
  std::uint64_t base_prime_product;
  std::uint32_t distinct_base_prime_count;
  std::uint32_t squareful;
  std::int32_t mobius;
  std::uint32_t reserved;
};

static_assert(sizeof(TgMobiusSupport) == 24);

// Produce exact support records for n in [lower, lower + count).  base_primes
// must contain, exactly once and in increasing order, every prime not greater
// than floor(sqrt(lower + count - 1)).  The public runner constructs that list
// with an exact host sieve and independently recomputes every output record.
cudaError_t launch_tg_mobius_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusSupport* outputs, cudaStream_t stream = nullptr);
