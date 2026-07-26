# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Checked prototype rewrite for a warp-per-prime Goldbach sieve tier.

After the race-free word-owner prefix, the original hardened source gives one
CUDA thread to each remaining prime.  The first few thousand tail primes then
have long marking loops but too few threads to fill the GPU once the larger
primes finish.  This prototype gives one complete warp to each prime through a
second cutoff; its 32 lanes mark disjoint terms of the same arithmetic
progression.  Larger primes retain the reviewed one-thread-per-prime kernel.

The rewrite is deliberately diagnostic.  It does not mutate a reviewed patch,
source identity, executable pin, or production admission.
"""

from __future__ import annotations

from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
    inspect_word_owner_source,
)


class GoldbachWarpTailOptimizerError(RuntimeError):
    """The source cannot receive the unique reviewed prototype rewrite."""


_CONSTANT_MARKER = (
    "static const uint64_t WORD_OWNER_SIEVE_LIMIT = {owner};\n"
)
_KERNEL_MARKER = """\
// Race-free full-segment sieve.  One CUDA thread owns one odd prime and
// clears all of that prime's multiples across the q interval.  Different
"""
_WARP_KERNEL_NAME = "sieve_segment_warp_per_prime_kernel"

_ORIGINAL_LAUNCH = """\
            uint64_t remaining_sieve_prime_count =
                sieve_prime_count > word_sieved_prime_count
                    ? sieve_prime_count - word_sieved_prime_count
                    : 0;
            uint32_t sieve_blocks = (uint32_t)(
                (remaining_sieve_prime_count + THREADS_PER_BLOCK - 1)
                / THREADS_PER_BLOCK);
            if (remaining_sieve_prime_count != 0) {
                sieve_segment_kernel<<<
                    sieve_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    q_low, q_high,
                    d_small_primes + word_sieved_prime_count,
                    remaining_sieve_prime_count, d_seg_bits);
                CUDA_CHECK(cudaGetLastError());
            }
"""

_WARP_KERNEL = """\
// Load-balance the longest remaining prime-owner progressions.  One complete
// warp owns one prime; lane `l` marks progression terms congruent to `l`
// modulo 32.  Lanes of the same warp therefore never mark the same composite.
__global__ void sieve_segment_warp_per_prime_kernel(
    uint64_t        q_low,
    uint64_t        q_high,
    const uint64_t* __restrict__ d_small_primes,
    uint64_t        small_prime_count,
    uint64_t*       __restrict__ d_seg_bits)
{
    uint64_t global_thread =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    uint64_t warp_index = global_thread / 32;
    uint32_t lane = threadIdx.x & 31;
    if (warp_index >= small_prime_count) return;
    uint64_t p = d_small_primes[warp_index];
    if (p < 3 || p > q_high / p) return;

    // ceil(q_low / p) * p without q_low + p - 1 overflow.
    uint64_t quotient = q_low / p;
    if (q_low % p != 0) ++quotient;
    if (quotient > q_high / p) return;
    uint64_t first = quotient * p;
    if ((first & 1) == 0) {
        if (first > q_high - p) return;
        first += p;
    }

    uint64_t p_squared = p * p; // p <= floor(sqrt(q_high))
    if (first < p_squared) first = p_squared;
    if (first > q_high) return;

    uint64_t step = 2 * p;
    uint64_t lane_offset = step * static_cast<uint64_t>(lane);
    if (lane_offset > q_high - first) return;
    uint64_t warp_step = step * 32;
    for (uint64_t composite = first + lane_offset;;) {
        uint64_t bit = (composite - q_low) / 2;
        atomicAnd(
            reinterpret_cast<unsigned long long*>(&d_seg_bits[bit / 64]),
            ~(1ULL << (bit % 64)));
        if (warp_step > q_high - composite) break;
        composite += warp_step;
    }
}

"""

_TIERED_LAUNCH = """\
            uint64_t warp_sieved_prime_count = std::upper_bound(
                small_primes.begin(), small_primes.end(),
                std::min<uint64_t>(
                    sieve_limit, WARP_PARALLEL_SIEVE_LIMIT))
                - small_primes.begin();
            uint64_t warp_parallel_prime_count =
                warp_sieved_prime_count > word_sieved_prime_count
                    ? warp_sieved_prime_count - word_sieved_prime_count
                    : 0;
            uint64_t warp_parallel_threads =
                warp_parallel_prime_count * 32;
            uint32_t warp_parallel_blocks = static_cast<uint32_t>(
                (warp_parallel_threads + THREADS_PER_BLOCK - 1)
                / THREADS_PER_BLOCK);
            if (warp_parallel_prime_count != 0) {
                sieve_segment_warp_per_prime_kernel<<<
                    warp_parallel_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    q_low, q_high,
                    d_small_primes + word_sieved_prime_count,
                    warp_parallel_prime_count, d_seg_bits);
                CUDA_CHECK(cudaGetLastError());
            }

            uint64_t remaining_sieve_prime_count =
                sieve_prime_count > warp_sieved_prime_count
                    ? sieve_prime_count - warp_sieved_prime_count
                    : 0;
            uint32_t sieve_blocks = static_cast<uint32_t>(
                (remaining_sieve_prime_count + THREADS_PER_BLOCK - 1)
                / THREADS_PER_BLOCK);
            if (remaining_sieve_prime_count != 0) {
                sieve_segment_kernel<<<
                    sieve_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    q_low, q_high,
                    d_small_primes + warp_sieved_prime_count,
                    remaining_sieve_prime_count, d_seg_bits);
                CUDA_CHECK(cudaGetLastError());
            }
"""


def rewrite_warp_parallel_tail(source: str, warp_limit: int) -> str:
    """Insert the unique warp-per-prime tier through ``warp_limit``."""

    inspected = inspect_word_owner_source(source)
    if isinstance(warp_limit, bool) or not isinstance(warp_limit, int):
        raise GoldbachWarpTailOptimizerError("warp cutoff must be an integer")
    if warp_limit <= inspected.cutoff:
        raise GoldbachWarpTailOptimizerError(
            "warp cutoff must be greater than the word-owner cutoff"
        )
    if warp_limit > 1_000_000:
        raise GoldbachWarpTailOptimizerError(
            "diagnostic warp cutoff must not exceed 1000000"
        )
    if (
        _WARP_KERNEL_NAME in source
        or "WARP_PARALLEL_SIEVE_LIMIT" in source
    ):
        raise GoldbachWarpTailOptimizerError(
            "source already contains a warp-parallel sieve tier"
        )

    constant_marker = _CONSTANT_MARKER.format(owner=inspected.cutoff)
    if source.count(constant_marker) != 1:
        raise GoldbachWarpTailOptimizerError(
            "word-owner constant insertion point is not unique"
        )
    rewritten = source.replace(
        constant_marker,
        constant_marker
        + "static const uint64_t WARP_PARALLEL_SIEVE_LIMIT = "
        + f"{warp_limit};\n",
        1,
    )
    if rewritten.count(_KERNEL_MARKER) != 1:
        raise GoldbachWarpTailOptimizerError(
            "atomic kernel insertion point is not unique"
        )
    rewritten = rewritten.replace(
        _KERNEL_MARKER, _WARP_KERNEL + _KERNEL_MARKER, 1
    )
    if rewritten.count(_ORIGINAL_LAUNCH) != 1:
        raise GoldbachWarpTailOptimizerError(
            "reviewed atomic launch block is not unique"
        )
    rewritten = rewritten.replace(_ORIGINAL_LAUNCH, _TIERED_LAUNCH, 1)

    # The word-owner prefix itself must remain byte-for-byte valid.
    post = inspect_word_owner_source(rewritten)
    if post != inspected:
        raise GoldbachWarpTailOptimizerError(
            "warp-tier rewrite changed the word-owner prefix"
        )
    required = (
        f"WARP_PARALLEL_SIEVE_LIMIT = {warp_limit};",
        "__global__ void " + _WARP_KERNEL_NAME,
        "warp_parallel_prime_count * 32",
        "d_small_primes + warp_sieved_prime_count",
        "if (warp_step > q_high - composite) break;",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachWarpTailOptimizerError(
            "warp-tier rewrite failed its source postcondition"
        )
    return rewritten


__all__ = [
    "GoldbachWarpTailOptimizerError",
    "rewrite_warp_parallel_tail",
]
