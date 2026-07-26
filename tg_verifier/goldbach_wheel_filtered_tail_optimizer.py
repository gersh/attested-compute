# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Checked diagnostic wheel filter for redundant Goldbach sieve atomics.

The packed word initializer already clears multiples of every odd prime
through 2039.  Consequently, when a tail prime ``p > 2039`` marks ``p*k``,
the global atomic clear is redundant whenever ``k`` is divisible by one of
3, 5, 7, 11, or 13.  This rewrite tracks ``k`` alongside each progression and
issues atomics only for residues coprime to ``15015``.
"""

from __future__ import annotations

from tg_verifier.goldbach_word_owner_optimizer import inspect_word_owner_source


class GoldbachWheelFilteredTailOptimizerError(RuntimeError):
    """The source cannot receive the unique reviewed wheel-filter rewrite."""


_WARP_MARKER = """\
// Load-balance the longest remaining prime-owner progressions.  One complete
"""
_FILTER_PRIMES = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)
_FILTER_LIMITS = (13, 19, 31, 47)
_HELPER_PREFIX = """\
// The word-owner prefix has already cleared every multiple of these primes.
// A later p*k clear is useful only when k survives the selected wheel.
static constexpr uint64_t COFACTOR_FILTER_LIMIT = {filter_limit};
__device__ __forceinline__ bool cofactor_survives_word_owner_wheel(
    uint64_t cofactor)
{
    uint32_t residue = static_cast<uint32_t>(cofactor % 15015ULL);
    return residue % 3U != 0U && residue % 5U != 0U &&
           residue % 7U != 0U && residue % 11U != 0U &&
           residue % 13U != 0U{extra_conditions};
}

"""


def _helper_for_limit(filter_limit: int) -> str:
    if (
        isinstance(filter_limit, bool)
        or not isinstance(filter_limit, int)
        or filter_limit not in _FILTER_LIMITS
    ):
        raise GoldbachWheelFilteredTailOptimizerError(
            "cofactor filter limit must be one of 13, 19, 31, or 47"
        )
    extras = [
        prime for prime in _FILTER_PRIMES if 13 < prime <= filter_limit
    ]
    extra_conditions = "".join(
        f" &&\n           cofactor % {prime}U != 0U" for prime in extras
    )
    return _HELPER_PREFIX.replace(
        "{filter_limit}", str(filter_limit)
    ).replace("{extra_conditions}", extra_conditions)
_ODD_ADJUST = """\
    if ((first & 1) == 0) {
        if (first > q_high - p) return;
        first += p;
    }
"""
_NEW_ODD_ADJUST = """\
    if ((first & 1) == 0) {
        if (first > q_high - p) return;
        first += p;
        ++quotient;
    }
"""
_SQUARE_GUARD = """\
    uint64_t p_squared = p * p; // p <= floor(sqrt(q_high))
    if (first < p_squared) first = p_squared;
    if (first > q_high) return;
"""
_NEW_SQUARE_GUARD = """\
    uint64_t p_squared = p * p; // p <= floor(sqrt(q_high))
    if (first < p_squared) {
        first = p_squared;
        quotient = p;
    }
    if (first > q_high) return;
"""
_WARP_LANE = """\
    uint64_t step = 2 * p;
    uint64_t lane_offset = step * static_cast<uint64_t>(lane);
    if (lane_offset > q_high - first) return;
    uint64_t warp_step = step * 32;
"""
_NEW_WARP_LANE = """\
    uint64_t step = 2 * p;
    uint64_t lane_offset = step * static_cast<uint64_t>(lane);
    if (lane_offset > q_high - first) return;
    uint64_t cofactor =
        quotient + 2 * static_cast<uint64_t>(lane);
    uint64_t warp_step = step * 32;
"""
_ATOMIC_CLEAR = """\
        atomicAnd(
            reinterpret_cast<unsigned long long*>(&d_seg_bits[bit / 64]),
            ~(1ULL << (bit % 64)));
"""
_FILTERED_CLEAR = """\
        if (cofactor_survives_word_owner_wheel(cofactor)) {
            atomicAnd(
                reinterpret_cast<unsigned long long*>(
                    &d_seg_bits[bit / 64]),
                ~(1ULL << (bit % 64)));
        }
"""
_WARP_INCREMENT = """\
        if (warp_step > q_high - composite) break;
        composite += warp_step;
"""
_NEW_WARP_INCREMENT = """\
        if (warp_step > q_high - composite) break;
        composite += warp_step;
        cofactor += 64;
"""
_TAIL_LOOP = """\
    uint64_t step = 2 * p;
    for (uint64_t composite = first;; composite += step) {
        uint64_t bit = (composite - q_low) / 2;
        atomicAnd(
            reinterpret_cast<unsigned long long*>(&d_seg_bits[bit / 64]),
            ~(1ULL << (bit % 64)));
        if (composite > q_high - step) break;
    }
"""
_NEW_TAIL_LOOP = """\
    uint64_t step = 2 * p;
    uint64_t cofactor = quotient;
    for (uint64_t composite = first;;) {
        uint64_t bit = (composite - q_low) / 2;
        if (cofactor_survives_word_owner_wheel(cofactor)) {
            atomicAnd(
                reinterpret_cast<unsigned long long*>(
                    &d_seg_bits[bit / 64]),
                ~(1ULL << (bit % 64)));
        }
        if (step > q_high - composite) break;
        composite += step;
        cofactor += 2;
    }
"""


def _replace_count(
    source: str, old: str, new: str, count: int, what: str
) -> str:
    actual = source.count(old)
    if actual != count:
        raise GoldbachWheelFilteredTailOptimizerError(
            f"{what} expected {count} insertion points, found {actual}"
        )
    return source.replace(old, new)


def rewrite_wheel_filtered_sieve(
    source: str, filter_limit: int = 13
) -> str:
    """Skip atomics for cofactors already cleared by the word-owner wheel."""

    inspected = inspect_word_owner_source(source)
    helper = _helper_for_limit(filter_limit)
    if inspected.cutoff < filter_limit:
        raise GoldbachWheelFilteredTailOptimizerError(
            "word-owner cutoff must include every cofactor filter prime"
        )
    if (
        "cofactor_survives_word_owner_wheel" in source
        or "cofactor += 64" in source
    ):
        raise GoldbachWheelFilteredTailOptimizerError(
            "source already contains the wheel-filtered sieve"
        )
    if source.count(_WARP_MARKER) != 1:
        raise GoldbachWheelFilteredTailOptimizerError(
            "warp helper insertion point is not unique"
        )
    rewritten = source.replace(_WARP_MARKER, helper + _WARP_MARKER, 1)
    rewritten = _replace_count(
        rewritten, _ODD_ADJUST, _NEW_ODD_ADJUST, 2, "odd adjustment"
    )
    rewritten = _replace_count(
        rewritten, _SQUARE_GUARD, _NEW_SQUARE_GUARD, 2, "square guard"
    )
    rewritten = _replace_count(
        rewritten, _WARP_LANE, _NEW_WARP_LANE, 1, "warp cofactor"
    )
    # Rewrite the tail as a unit first; one atomic site remains in the warp.
    rewritten = _replace_count(
        rewritten, _TAIL_LOOP, _NEW_TAIL_LOOP, 1, "tail loop"
    )
    rewritten = _replace_count(
        rewritten, _ATOMIC_CLEAR, _FILTERED_CLEAR, 1, "warp atomic"
    )
    rewritten = _replace_count(
        rewritten,
        _WARP_INCREMENT,
        _NEW_WARP_INCREMENT,
        1,
        "warp cofactor increment",
    )
    inspect_word_owner_source(rewritten)
    required = (
        "cofactor % 15015ULL",
        f"COFACTOR_FILTER_LIMIT = {filter_limit};",
        "cofactor += 64",
        "cofactor += 2",
        "quotient = p;",
        "cofactor_survives_word_owner_wheel(cofactor)",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachWheelFilteredTailOptimizerError(
            "wheel-filter rewrite failed its source postcondition"
        )
    return rewritten


_TAIL_END_MARKER = """\
__device__ __forceinline__ uint64_t extract_shifted_prime_word(
"""
_OLD_WARP_LAUNCH = """\
                sieve_segment_warp_per_prime_kernel<<<
                    warp_parallel_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    q_low, q_high,
                    d_small_primes + word_sieved_prime_count,
                    warp_parallel_prime_count, d_seg_bits);
"""
_OLD_TAIL_LAUNCH = """\
                sieve_segment_kernel<<<
                    sieve_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    q_low, q_high,
                    d_small_primes + warp_sieved_prime_count,
                    remaining_sieve_prime_count, d_seg_bits);
"""
_COMPARE_KERNEL = """\
__global__ void compare_sieve_words_kernel(
    const uint64_t* __restrict__ reference_words,
    const uint64_t* __restrict__ candidate_words,
    uint64_t word_count,
    uint32_t* __restrict__ mismatch_count)
{
    uint64_t index =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index < word_count &&
        reference_words[index] != candidate_words[index]) {
        atomicAdd(mismatch_count, 1U);
    }
}

"""
_DECLARATION = "        uint64_t* d_seg_bits = nullptr;\n"
_REFERENCE_DECLARATION = (
    _DECLARATION + "        uint64_t* d_reference_seg_bits = nullptr;\n"
)
_ALLOCATION = (
    "        CUDA_CHECK(cudaMalloc(&d_seg_bits, "
    "seg_bytes + sizeof(uint64_t)));\n"
)
_REFERENCE_ALLOCATION = _ALLOCATION + """\
        CUDA_CHECK(cudaMalloc(
            &d_reference_seg_bits, seg_bytes + sizeof(uint64_t)));
"""
_INITIALIZE = """\
            initialize_small_prime_words_kernel<<<
                word_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                q_low, segment_words, d_seg_bits);
            CUDA_CHECK(cudaGetLastError());
            // Unaligned extraction from the last live q word may load one
            // carry word.  It is explicit zero padding, never candidate data.
            CUDA_CHECK(cudaMemsetAsync(
                d_seg_bits + segment_words, 0, sizeof(uint64_t), stream));
"""
_REFERENCE_INITIALIZE = _INITIALIZE + """\
            initialize_small_prime_words_kernel<<<
                word_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                q_low, segment_words, d_reference_seg_bits);
            CUDA_CHECK(cudaGetLastError());
            CUDA_CHECK(cudaMemsetAsync(
                d_reference_seg_bits + segment_words, 0,
                sizeof(uint64_t), stream));
"""
_REFERENCE_WARP_LAUNCH = _OLD_WARP_LAUNCH.replace(
    "sieve_segment_warp_per_prime_kernel",
    "reference_sieve_segment_warp_per_prime_kernel",
).replace("d_seg_bits);", "d_reference_seg_bits);")
_REFERENCE_TAIL_LAUNCH = _OLD_TAIL_LAUNCH.replace(
    "sieve_segment_kernel", "reference_sieve_segment_kernel"
).replace("d_seg_bits);", "d_reference_seg_bits);")
_PHASE_MARKER = """\

            // B. Phase 1 verification.  The initial low segment retains the
"""
_COMPARE_LAUNCH = """\

            CUDA_CHECK(cudaMemsetAsync(
                d_unverified_count, 0, sizeof(uint32_t), stream));
            compare_sieve_words_kernel<<<
                word_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                d_reference_seg_bits, d_seg_bits, segment_words,
                d_unverified_count);
            CUDA_CHECK(cudaGetLastError());
            uint32_t sieve_word_mismatch_count = 0;
            CUDA_CHECK(cudaMemcpyAsync(
                &sieve_word_mismatch_count, d_unverified_count,
                sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
            CUDA_CHECK(cudaStreamSynchronize(stream));
            if (sieve_word_mismatch_count != 0) {
                throw std::runtime_error(
                    "wheel-filtered sieve differs from unfiltered sieve");
            }

            // B. Phase 1 verification.  The initial low segment retains the
"""
_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_seg_bits));
        CUDA_CHECK(cudaFree(d_coverage_words));
"""
_REFERENCE_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_seg_bits));
        CUDA_CHECK(cudaFree(d_reference_seg_bits));
        CUDA_CHECK(cudaFree(d_coverage_words));
"""
_TOTAL = """\
        verified_bytes + coverage_bytes + p_batch_bytes + seg_bytes +
        sizeof(uint64_t) + small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_REFERENCE_TOTAL = """\
        verified_bytes + coverage_bytes + p_batch_bytes + 2 * seg_bytes +
        2 * sizeof(uint64_t) + small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_PACKED_PHASE_CROSSCHECK_TOTAL = """\
        verified_bytes + shifted_verified_bytes + coverage_bytes + p_batch_bytes + seg_bytes +
        sizeof(uint64_t) + 2 * sizeof(uint32_t) +
        small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_REFERENCE_PACKED_PHASE_CROSSCHECK_TOTAL = """\
        verified_bytes + shifted_verified_bytes + coverage_bytes + p_batch_bytes +
        2 * seg_bytes + 2 * sizeof(uint64_t) + 2 * sizeof(uint32_t) +
        small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""


def rewrite_wheel_filtered_sieve_crosscheck(
    source: str, filter_limit: int = 13
) -> str:
    """Run the unfiltered and filtered real sieve and compare every word."""

    if source.count(_WARP_MARKER) != 1 or source.count(_TAIL_END_MARKER) != 1:
        raise GoldbachWheelFilteredTailOptimizerError(
            "reference kernel extraction points are not unique"
        )
    kernel_start = source.index(_WARP_MARKER)
    kernel_end = source.index(_TAIL_END_MARKER)
    if kernel_start >= kernel_end:
        raise GoldbachWheelFilteredTailOptimizerError(
            "reference kernel range is malformed"
        )
    reference_kernels = source[kernel_start:kernel_end]
    reference_kernels = reference_kernels.replace(
        "sieve_segment_warp_per_prime_kernel",
        "reference_sieve_segment_warp_per_prime_kernel",
    ).replace(
        "sieve_segment_kernel", "reference_sieve_segment_kernel"
    )
    helper = _helper_for_limit(filter_limit)
    rewritten = rewrite_wheel_filtered_sieve(source, filter_limit)
    if rewritten.count(helper) != 1:
        raise GoldbachWheelFilteredTailOptimizerError(
            "crosscheck kernel insertion point is not unique"
        )
    rewritten = rewritten.replace(
        helper, reference_kernels + _COMPARE_KERNEL + helper, 1
    )
    if rewritten.count(_TOTAL) == 1:
        total_rewrite = (_TOTAL, _REFERENCE_TOTAL)
    elif rewritten.count(_PACKED_PHASE_CROSSCHECK_TOTAL) == 1:
        total_rewrite = (
            _PACKED_PHASE_CROSSCHECK_TOTAL,
            _REFERENCE_PACKED_PHASE_CROSSCHECK_TOTAL,
        )
    else:
        raise GoldbachWheelFilteredTailOptimizerError(
            "reference memory accounting insertion point is not unique"
        )
    for old, new, count, what in (
        (
            _DECLARATION,
            _REFERENCE_DECLARATION,
            1,
            "reference declaration",
        ),
        (
            _ALLOCATION,
            _REFERENCE_ALLOCATION,
            1,
            "reference allocation",
        ),
        (
            _INITIALIZE,
            _REFERENCE_INITIALIZE,
            1,
            "reference initialization",
        ),
        (
            _OLD_WARP_LAUNCH,
            _OLD_WARP_LAUNCH
            + "                CUDA_CHECK(cudaGetLastError());\n"
            + _REFERENCE_WARP_LAUNCH,
            1,
            "reference warp launch",
        ),
        (
            _OLD_TAIL_LAUNCH,
            _OLD_TAIL_LAUNCH
            + "                CUDA_CHECK(cudaGetLastError());\n"
            + _REFERENCE_TAIL_LAUNCH,
            1,
            "reference tail launch",
        ),
        (_PHASE_MARKER, _COMPARE_LAUNCH, 1, "word comparison"),
        (_CLEANUP, _REFERENCE_CLEANUP, 1, "reference cleanup"),
        (
            total_rewrite[0],
            total_rewrite[1],
            1,
            "reference memory accounting",
        ),
    ):
        rewritten = _replace_count(rewritten, old, new, count, what)
    required = (
        "__global__ void compare_sieve_words_kernel",
        "reference_sieve_segment_warp_per_prime_kernel<<<",
        "reference_sieve_segment_kernel<<<",
        "d_reference_seg_bits, d_seg_bits, segment_words",
        "wheel-filtered sieve differs from unfiltered sieve",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachWheelFilteredTailOptimizerError(
            "wheel-filter crosscheck failed its source postcondition"
        )
    return rewritten


__all__ = [
    "GoldbachWheelFilteredTailOptimizerError",
    "rewrite_wheel_filtered_sieve",
    "rewrite_wheel_filtered_sieve_crosscheck",
]
