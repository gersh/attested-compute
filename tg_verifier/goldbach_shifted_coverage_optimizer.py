# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Checked prototype rewrite for word-wise Goldbach phase-1 coverage.

The prepared source already stores primality of the odd q window as packed
64-bit words.  This rewrite replaces 64 independent per-even searches by one
thread that ORs shifted q words for 64 consecutive evens.  Low segments whose
first output word cannot align every odd p retain the original kernel.

This is a diagnostic transformation only.  It does not alter the reviewed
hardening patch or any production identity.
"""

from __future__ import annotations

from tg_verifier.goldbach_word_owner_optimizer import (
    inspect_word_owner_source,
)


class GoldbachShiftedCoverageOptimizerError(RuntimeError):
    """The source cannot receive the unique shifted-coverage rewrite."""


_KERNEL_NAME = "shifted_or_phase1_coverage_kernel"
_KERNEL_MARKER = """\
// -------------------------------------------------------
// Phase 1 Kernel: GPU Goldbach Verification
// -------------------------------------------------------
"""
_KERNEL_SOURCE = """\
__device__ __forceinline__ uint64_t extract_shifted_prime_word(
    const uint64_t* __restrict__ q_words, uint64_t first_bit)
{
    uint64_t word_index = first_bit / 64;
    uint32_t shift = static_cast<uint32_t>(first_bit % 64);
    uint64_t low = q_words[word_index] >> shift;
    if (shift == 0) return low;
    return low | (q_words[word_index + 1] << (64 - shift));
}

// One thread owns 64 consecutive evens.  For every supplied odd prime p,
// base_offsets[p] satisfies
//
//   seg_even_start = q_low + p + 2 * base_offsets[p].
//
// Thus shifted source bit i proves
// seg_even_start + 2*i = p + (q_low + 2*(base_offset+i)).
__global__ void shifted_or_phase1_coverage_kernel(
    const uint64_t* __restrict__ q_words,
    const uint64_t* __restrict__ base_offsets,
    uint64_t offset_count,
    uint64_t output_word_count,
    uint64_t final_live_mask,
    uint64_t* __restrict__ coverage_words)
{
    uint64_t word =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (word >= output_word_count) return;
    uint64_t live_mask =
        word + 1 == output_word_count ? final_live_mask : ~0ULL;
    uint64_t covered = 0;
    for (uint64_t index = 0; index < offset_count; ++index) {
        uint64_t first_bit = base_offsets[index] + 64 * word;
        covered |= extract_shifted_prime_word(q_words, first_bit);
        if ((covered & live_mask) == live_mask) break;
    }
    coverage_words[word] = covered;
}

__global__ void expand_coverage_words_kernel(
    const uint64_t* __restrict__ coverage_words,
    uint64_t even_count,
    uint8_t* __restrict__ verified)
{
    uint64_t index =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index >= even_count) return;
    verified[index] = static_cast<uint8_t>(
        (coverage_words[index / 64] >> (index % 64)) & 1ULL);
}

"""

_DECLARATIONS = """\
        uint64_t* d_seg_bits = nullptr;
        uint8_t*  d_verified = nullptr;
        uint64_t* d_p_batch  = nullptr;
"""
_NEW_DECLARATIONS = """\
        uint64_t* d_seg_bits = nullptr;
        uint64_t* d_coverage_words = nullptr;
        uint8_t*  d_verified = nullptr;
        uint64_t* d_p_batch  = nullptr;
"""
_ALLOCATIONS = """\
        CUDA_CHECK(cudaMalloc(&d_seg_bits, seg_bytes));
        CUDA_CHECK(cudaMalloc(&d_verified, SEG_SIZE));
"""
_NEW_ALLOCATIONS = """\
        CUDA_CHECK(cudaMalloc(&d_seg_bits, seg_bytes + sizeof(uint64_t)));
        uint64_t max_coverage_words = (SEG_SIZE + 63) / 64;
        CUDA_CHECK(cudaMalloc(
            &d_coverage_words, max_coverage_words * sizeof(uint64_t)));
        CUDA_CHECK(cudaMalloc(&d_verified, SEG_SIZE));
"""
_INITIALIZER_LAUNCH = """\
            initialize_small_prime_words_kernel<<<
                word_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                q_low, segment_words, d_seg_bits);
            CUDA_CHECK(cudaGetLastError());
"""
_NEW_INITIALIZER_LAUNCH = _INITIALIZER_LAUNCH + """\
            // Unaligned extraction from the last live q word may load one
            // carry word.  It is explicit zero padding, never candidate data.
            CUDA_CHECK(cudaMemsetAsync(
                d_seg_bits + segment_words, 0, sizeof(uint64_t), stream));
"""
_PHASE1 = """\
            // B. Phase 1 Verification Batches
            CUDA_CHECK(cudaMemsetAsync(d_verified, 0, seg_even_count, stream));
            uint32_t blocks = (uint32_t)((seg_even_count + THREADS_PER_BLOCK - 1) / THREADS_PER_BLOCK);

            for (uint64_t bi = 0; bi < gpu_primes.size(); bi += P_BATCH) {
                uint64_t bsize = std::min(P_BATCH, (uint64_t)gpu_primes.size() - bi);
                CUDA_CHECK(cudaMemcpyAsync(d_p_batch, gpu_primes.data() + bi, bsize * sizeof(uint64_t), cudaMemcpyHostToDevice, stream));

                goldbach_phase1_kernel<<<blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_small, small_high, d_seg_bits, q_low, q_high,
                    seg_start, seg_even_count, d_p_batch, bsize, d_verified);
                CUDA_CHECK(cudaGetLastError());
            }
"""
_NEW_PHASE1 = """\
            // B. Phase 1 verification.  The initial low segment retains the
            // original per-even kernel because its first word precedes some
            // nonnegative odd-prime alignments.
            uint32_t blocks = (uint32_t)(
                (seg_even_count + THREADS_PER_BLOCK - 1)
                / THREADS_PER_BLOCK);
            bool shifted_alignment_available = seg_start >= q_low;
            uint64_t alignment_span =
                shifted_alignment_available ? seg_start - q_low : 0;
            std::vector<uint64_t> phase1_offsets;
            phase1_offsets.reserve(gpu_primes.size());
            for (uint64_t p : gpu_primes) {
                if (p == 2) continue;
                if (p > alignment_span) {
                    shifted_alignment_available = false;
                    break;
                }
                uint64_t difference = alignment_span - p;
                if ((difference & 1) != 0) {
                    shifted_alignment_available = false;
                    break;
                }
                phase1_offsets.push_back(difference / 2);
            }
            if (phase1_offsets.empty() ||
                phase1_offsets.size() > P_BATCH) {
                shifted_alignment_available = false;
            }

            if (!shifted_alignment_available) {
                CUDA_CHECK(cudaMemsetAsync(
                    d_verified, 0, seg_even_count, stream));
                for (uint64_t bi = 0; bi < gpu_primes.size(); bi += P_BATCH) {
                    uint64_t bsize = std::min(
                        P_BATCH, (uint64_t)gpu_primes.size() - bi);
                    CUDA_CHECK(cudaMemcpyAsync(
                        d_p_batch, gpu_primes.data() + bi,
                        bsize * sizeof(uint64_t),
                        cudaMemcpyHostToDevice, stream));
                    goldbach_phase1_kernel<<<
                        blocks, THREADS_PER_BLOCK, 0, stream>>>(
                        d_small, small_high, d_seg_bits, q_low, q_high,
                        seg_start, seg_even_count,
                        d_p_batch, bsize, d_verified);
                    CUDA_CHECK(cudaGetLastError());
                }
            } else {
                CUDA_CHECK(cudaMemcpyAsync(
                    d_p_batch, phase1_offsets.data(),
                    phase1_offsets.size() * sizeof(uint64_t),
                    cudaMemcpyHostToDevice, stream));
                uint64_t coverage_word_count =
                    (seg_even_count + 63) / 64;
                uint32_t coverage_blocks = static_cast<uint32_t>(
                    (coverage_word_count + THREADS_PER_BLOCK - 1)
                    / THREADS_PER_BLOCK);
                uint64_t live_remainder = seg_even_count % 64;
                uint64_t final_live_mask =
                    live_remainder == 0
                        ? ~0ULL
                        : (1ULL << live_remainder) - 1;
                shifted_or_phase1_coverage_kernel<<<
                    coverage_blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_seg_bits, d_p_batch, phase1_offsets.size(),
                    coverage_word_count, final_live_mask,
                    d_coverage_words);
                CUDA_CHECK(cudaGetLastError());
                expand_coverage_words_kernel<<<
                    blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_coverage_words, seg_even_count, d_verified);
                CUDA_CHECK(cudaGetLastError());
            }
"""
_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_seg_bits));
        CUDA_CHECK(cudaFree(d_verified));
"""
_NEW_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_seg_bits));
        CUDA_CHECK(cudaFree(d_coverage_words));
        CUDA_CHECK(cudaFree(d_verified));
"""
_MEMORY = """\
    uint64_t verified_bytes = SEG_SIZE;
    uint64_t p_batch_bytes  = P_BATCH * sizeof(uint64_t);
"""
_NEW_MEMORY = """\
    uint64_t verified_bytes = SEG_SIZE;
    uint64_t coverage_bytes = ((SEG_SIZE + 63) / 64) * sizeof(uint64_t);
    uint64_t p_batch_bytes  = P_BATCH * sizeof(uint64_t);
"""
_TOTAL = """\
    uint64_t total_required = verified_bytes + p_batch_bytes + seg_bytes + small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_NEW_TOTAL = """\
    uint64_t total_required =
        verified_bytes + coverage_bytes + p_batch_bytes + seg_bytes +
        sizeof(uint64_t) + small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_GRID_VALIDATION = """\
    // Validate CUDA Grid Sizes
    uint64_t blocks = (SEG_SIZE + THREADS_PER_BLOCK - 1) / THREADS_PER_BLOCK;
"""
_NEW_GRID_VALIDATION = """\
    // Both byte and packed missing-result counters are uint32_t.  Refuse a
    // segment whose exact missing-bit count could wrap to zero.
    if (SEG_SIZE > UINT32_MAX) {
        std::cerr
            << "[!] ERROR: Segment size exceeds the exact uint32_t "
            << "unverified-count range.\\n";
        std::exit(1);
    }

    // Validate CUDA Grid Sizes
    uint64_t blocks =
        (SEG_SIZE + THREADS_PER_BLOCK - 1) / THREADS_PER_BLOCK;
"""


def _replace_once(source: str, old: str, new: str, what: str) -> str:
    if source.count(old) != 1:
        raise GoldbachShiftedCoverageOptimizerError(
            f"{what} insertion point is not unique"
        )
    return source.replace(old, new, 1)


def rewrite_shifted_phase1(source: str) -> str:
    """Return the unique word-wise phase-1 diagnostic source."""

    inspect_word_owner_source(source)
    if _KERNEL_NAME in source or "d_coverage_words" in source:
        raise GoldbachShiftedCoverageOptimizerError(
            "source already contains shifted phase-1 coverage"
        )
    rewritten = _replace_once(
        source, _KERNEL_MARKER, _KERNEL_SOURCE + _KERNEL_MARKER, "kernel"
    )
    for old, new, what in (
        (_DECLARATIONS, _NEW_DECLARATIONS, "allocation declaration"),
        (_ALLOCATIONS, _NEW_ALLOCATIONS, "allocation"),
        (_INITIALIZER_LAUNCH, _NEW_INITIALIZER_LAUNCH, "padding"),
        (_PHASE1, _NEW_PHASE1, "phase-1"),
        (_CLEANUP, _NEW_CLEANUP, "cleanup"),
        (_MEMORY, _NEW_MEMORY, "memory accounting"),
        (_TOTAL, _NEW_TOTAL, "total memory accounting"),
        (
            _GRID_VALIDATION,
            _NEW_GRID_VALIDATION,
            "unverified-count range guard",
        ),
    ):
        rewritten = _replace_once(rewritten, old, new, what)
    inspect_word_owner_source(rewritten)
    required = (
        "__global__ void " + _KERNEL_NAME,
        "seg_even_start = q_low + p + 2 * base_offsets[p]",
        "d_seg_bits + segment_words",
        "expand_coverage_words_kernel<<<",
        "coverage_bytes",
        "Segment size exceeds the exact uint32_t",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachShiftedCoverageOptimizerError(
            "shifted phase-1 rewrite failed its postcondition"
        )
    return rewritten


_PACKED_COUNT_KERNEL_NAME = "count_uncovered_coverage_words_kernel"
_PACKED_COUNT_KERNEL = """\
// Count missing live coverage bits without first expanding one byte per even.
// The final word's dead lanes are excluded before popcount.
__global__ void count_uncovered_coverage_words_kernel(
    const uint64_t* __restrict__ coverage_words,
    uint64_t coverage_word_count,
    uint64_t final_live_mask,
    uint32_t* __restrict__ unverified_count)
{
    uint64_t word =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (word >= coverage_word_count) return;
    uint64_t live_mask =
        word + 1 == coverage_word_count ? final_live_mask : ~0ULL;
    uint64_t missing = (~coverage_words[word]) & live_mask;
    if (missing != 0) {
        atomicAdd(
            unverified_count,
            static_cast<uint32_t>(__popcll(missing)));
    }
}

"""
_SHIFTED_EXPANSION = """\
                expand_coverage_words_kernel<<<
                    blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_coverage_words, seg_even_count, d_verified);
                CUDA_CHECK(cudaGetLastError());
"""
_DEFERRED_EXPANSION = """\
                // Byte expansion is deferred until the exceptional CPU
                // fallback path.  The ordinary success path stays packed.
"""
_COUNT_UNVERIFIED = """\
            // C. Count Unverified
            uint32_t unverified_count = 0;
            CUDA_CHECK(cudaMemsetAsync(d_unverified_count, 0, sizeof(uint32_t), stream));

            uint32_t count_blocks = (uint32_t)((seg_even_count + 255) / 256);
            count_unverified_kernel<<<count_blocks, 256, 0, stream>>>(d_verified, seg_even_count, d_unverified_count);
            CUDA_CHECK(cudaMemcpyAsync(&unverified_count, d_unverified_count, sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
            CUDA_CHECK(cudaStreamSynchronize(stream));
"""
_PACKED_COUNT_UNVERIFIED = """\
            // C. Count unverified outputs.  Shifted high segments stay
            // packed; the original low-boundary path retains byte counting.
            uint32_t unverified_count = 0;
            CUDA_CHECK(cudaMemsetAsync(
                d_unverified_count, 0, sizeof(uint32_t), stream));
            if (shifted_alignment_available) {
                uint64_t result_word_count =
                    (seg_even_count + 63) / 64;
                uint64_t result_remainder = seg_even_count % 64;
                uint64_t result_final_live_mask =
                    result_remainder == 0
                        ? ~0ULL
                        : (1ULL << result_remainder) - 1;
                uint32_t result_count_blocks = static_cast<uint32_t>(
                    (result_word_count + 255) / 256);
                count_uncovered_coverage_words_kernel<<<
                    result_count_blocks, 256, 0, stream>>>(
                    d_coverage_words, result_word_count,
                    result_final_live_mask, d_unverified_count);
            } else {
                uint32_t count_blocks =
                    (uint32_t)((seg_even_count + 255) / 256);
                count_unverified_kernel<<<count_blocks, 256, 0, stream>>>(
                    d_verified, seg_even_count, d_unverified_count);
            }
            CUDA_CHECK(cudaGetLastError());
            CUDA_CHECK(cudaMemcpyAsync(
                &unverified_count, d_unverified_count, sizeof(uint32_t),
                cudaMemcpyDeviceToHost, stream));
            CUDA_CHECK(cudaStreamSynchronize(stream));
"""
_CPU_FALLBACK = """\
            if (unverified_count > 0) {
                std::vector<uint8_t> verified(seg_even_count);
                CUDA_CHECK(cudaMemcpy(verified.data(), d_verified, seg_even_count, cudaMemcpyDeviceToHost));
"""
_PACKED_CPU_FALLBACK = """\
            if (unverified_count > 0) {
                if (shifted_alignment_available) {
                    // Materialize bytes only for the exceptional CPU replay.
                    expand_coverage_words_kernel<<<
                        blocks, THREADS_PER_BLOCK, 0, stream>>>(
                        d_coverage_words, seg_even_count, d_verified);
                    CUDA_CHECK(cudaGetLastError());
                }
                std::vector<uint8_t> verified(seg_even_count);
                CUDA_CHECK(cudaMemcpy(verified.data(), d_verified, seg_even_count, cudaMemcpyDeviceToHost));
"""


def rewrite_packed_shifted_unverified_count(source: str) -> str:
    """Count missing shifted results in packed form on the success path.

    ``source`` must already be the ordinary (not dual-execution crosscheck)
    output of :func:`rewrite_shifted_phase1`.
    """

    inspect_word_owner_source(source)
    if _KERNEL_NAME not in source or "d_coverage_words" not in source:
        raise GoldbachShiftedCoverageOptimizerError(
            "packed counting requires shifted phase-1 coverage"
        )
    if (
        _PACKED_COUNT_KERNEL_NAME in source
        or "compare_phase1_verified_kernel" in source
    ):
        raise GoldbachShiftedCoverageOptimizerError(
            "source already contains packed counting or crosscheck logic"
        )
    rewritten = _replace_once(
        source,
        _KERNEL_MARKER,
        _PACKED_COUNT_KERNEL + _KERNEL_MARKER,
        "packed-count kernel",
    )
    for old, new, what in (
        (
            _SHIFTED_EXPANSION,
            _DEFERRED_EXPANSION,
            "deferred byte expansion",
        ),
        (
            _COUNT_UNVERIFIED,
            _PACKED_COUNT_UNVERIFIED,
            "packed unverified count",
        ),
        (
            _CPU_FALLBACK,
            _PACKED_CPU_FALLBACK,
            "fallback byte expansion",
        ),
    ):
        rewritten = _replace_once(rewritten, old, new, what)
    required = (
        "__global__ void " + _PACKED_COUNT_KERNEL_NAME,
        "(~coverage_words[word]) & live_mask",
        "__popcll(missing)",
        "if (shifted_alignment_available) {",
        "Materialize bytes only for the exceptional CPU replay.",
    )
    forbidden = (
        "d_coverage_words, seg_even_count, d_verified);\n"
        "                CUDA_CHECK(cudaGetLastError());\n"
        "            }\n\n            // C. Count Unverified",
    )
    if not all(text in rewritten for text in required) or any(
        text in rewritten for text in forbidden
    ):
        raise GoldbachShiftedCoverageOptimizerError(
            "packed shifted-count rewrite failed its postcondition"
        )
    inspect_word_owner_source(rewritten)
    return rewritten


_COMPARE_KERNEL = """\
__global__ void compare_phase1_verified_kernel(
    const uint8_t* __restrict__ original_verified,
    const uint8_t* __restrict__ shifted_verified,
    uint64_t even_count,
    uint32_t* __restrict__ mismatch_count)
{
    uint64_t index =
        static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (index >= even_count) return;
    if (original_verified[index] != shifted_verified[index]) {
        atomicAdd(mismatch_count, 1u);
    }
}

"""


def rewrite_shifted_phase1_crosscheck(source: str) -> str:
    """Run original and shifted phase 1 and compare every live result bit."""

    rewritten = rewrite_shifted_phase1(source)
    rewritten = _replace_once(
        rewritten,
        _KERNEL_MARKER,
        _COMPARE_KERNEL + _KERNEL_MARKER,
        "crosscheck kernel",
    )
    rewritten = _replace_once(
        rewritten,
        _NEW_DECLARATIONS,
        _NEW_DECLARATIONS.replace(
            "        uint8_t*  d_verified = nullptr;\n",
            "        uint8_t*  d_verified = nullptr;\n"
            "        uint8_t*  d_shifted_verified = nullptr;\n",
        ),
        "crosscheck declaration",
    )
    rewritten = _replace_once(
        rewritten,
        _NEW_ALLOCATIONS,
        _NEW_ALLOCATIONS.replace(
            "        CUDA_CHECK(cudaMalloc(&d_verified, SEG_SIZE));\n",
            "        CUDA_CHECK(cudaMalloc(&d_verified, SEG_SIZE));\n"
            "        CUDA_CHECK(cudaMalloc(&d_shifted_verified, SEG_SIZE));\n",
        ),
        "crosscheck allocation",
    )
    rewritten = _replace_once(
        rewritten,
        _NEW_MEMORY,
        _NEW_MEMORY.replace(
            "    uint64_t coverage_bytes",
            "    uint64_t shifted_verified_bytes = SEG_SIZE;\n"
            "    uint64_t coverage_bytes",
        ),
        "crosscheck memory accounting",
    )
    rewritten = _replace_once(
        rewritten,
        _NEW_TOTAL,
        _NEW_TOTAL.replace(
            "verified_bytes + coverage_bytes",
            "verified_bytes + shifted_verified_bytes + coverage_bytes",
        ),
        "crosscheck total memory accounting",
    )
    rewritten = _replace_once(
        rewritten,
        _NEW_CLEANUP,
        _NEW_CLEANUP.replace(
            "        CUDA_CHECK(cudaFree(d_verified));\n",
            "        CUDA_CHECK(cudaFree(d_verified));\n"
            "        CUDA_CHECK(cudaFree(d_shifted_verified));\n",
        ),
        "crosscheck cleanup",
    )

    shifted_branch = """\
            } else {
                CUDA_CHECK(cudaMemcpyAsync(
                    d_p_batch, phase1_offsets.data(),
"""
    original_prefix = """\
            } else {
                // Diagnostic only: compute the original result independently
                // before running the shifted-word implementation.
                CUDA_CHECK(cudaMemsetAsync(
                    d_verified, 0, seg_even_count, stream));
                for (uint64_t bi = 0; bi < gpu_primes.size(); bi += P_BATCH) {
                    uint64_t bsize = std::min(
                        P_BATCH, (uint64_t)gpu_primes.size() - bi);
                    CUDA_CHECK(cudaMemcpyAsync(
                        d_p_batch, gpu_primes.data() + bi,
                        bsize * sizeof(uint64_t),
                        cudaMemcpyHostToDevice, stream));
                    goldbach_phase1_kernel<<<
                        blocks, THREADS_PER_BLOCK, 0, stream>>>(
                        d_small, small_high, d_seg_bits, q_low, q_high,
                        seg_start, seg_even_count,
                        d_p_batch, bsize, d_verified);
                    CUDA_CHECK(cudaGetLastError());
                }
                CUDA_CHECK(cudaMemcpyAsync(
                    d_p_batch, phase1_offsets.data(),
"""
    rewritten = _replace_once(
        rewritten, shifted_branch, original_prefix, "crosscheck original phase"
    )
    expansion = """\
                expand_coverage_words_kernel<<<
                    blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_coverage_words, seg_even_count, d_verified);
                CUDA_CHECK(cudaGetLastError());
"""
    comparison = """\
                expand_coverage_words_kernel<<<
                    blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_coverage_words, seg_even_count, d_shifted_verified);
                CUDA_CHECK(cudaGetLastError());
                CUDA_CHECK(cudaMemsetAsync(
                    d_unverified_count, 0, sizeof(uint32_t), stream));
                compare_phase1_verified_kernel<<<
                    blocks, THREADS_PER_BLOCK, 0, stream>>>(
                    d_verified, d_shifted_verified, seg_even_count,
                    d_unverified_count);
                CUDA_CHECK(cudaGetLastError());
                uint32_t phase1_mismatch_count = 0;
                CUDA_CHECK(cudaMemcpyAsync(
                    &phase1_mismatch_count, d_unverified_count,
                    sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
                CUDA_CHECK(cudaStreamSynchronize(stream));
                if (phase1_mismatch_count != 0) {
                    throw std::runtime_error(
                        "shifted phase 1 differs from original phase 1");
                }
"""
    rewritten = _replace_once(
        rewritten, expansion, comparison, "crosscheck comparison"
    )
    required = (
        "__global__ void compare_phase1_verified_kernel",
        "d_shifted_verified",
        "phase1_mismatch_count",
        "shifted phase 1 differs from original phase 1",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachShiftedCoverageOptimizerError(
            "crosscheck rewrite failed its postcondition"
        )
    return rewritten


_PACKED_CROSSCHECK_DECLARATION = """\
        uint32_t* d_unverified_count = nullptr;
"""
_NEW_PACKED_CROSSCHECK_DECLARATION = """\
        uint32_t* d_unverified_count = nullptr;
        uint32_t* d_packed_unverified_count = nullptr;
"""
_PACKED_CROSSCHECK_ALLOCATION = """\
        CUDA_CHECK(cudaMalloc(&d_unverified_count, sizeof(uint32_t)));
"""
_NEW_PACKED_CROSSCHECK_ALLOCATION = """\
        CUDA_CHECK(cudaMalloc(&d_unverified_count, sizeof(uint32_t)));
        CUDA_CHECK(cudaMalloc(
            &d_packed_unverified_count, sizeof(uint32_t)));
"""
_PACKED_CROSSCHECK_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_unverified_count));
"""
_NEW_PACKED_CROSSCHECK_CLEANUP = """\
        CUDA_CHECK(cudaFree(d_unverified_count));
        CUDA_CHECK(cudaFree(d_packed_unverified_count));
"""
_PACKED_CROSSCHECK_TOTAL = """\
        sizeof(uint64_t) + small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_NEW_PACKED_CROSSCHECK_TOTAL = """\
        sizeof(uint64_t) + 2 * sizeof(uint32_t) +
        small_bytes + VRAM_SAFETY_MARGIN_BYTES;
"""
_DUAL_COUNT_CROSSCHECK = """\
            // C. Independently compare byte-expanded and packed missing-bit
            // counts.  The low-boundary path has no shifted coverage words.
            uint32_t unverified_count = 0;
            uint32_t packed_unverified_count = 0;
            CUDA_CHECK(cudaMemsetAsync(
                d_unverified_count, 0, sizeof(uint32_t), stream));
            CUDA_CHECK(cudaMemsetAsync(
                d_packed_unverified_count, 0,
                sizeof(uint32_t), stream));

            uint32_t count_blocks =
                (uint32_t)((seg_even_count + 255) / 256);
            count_unverified_kernel<<<count_blocks, 256, 0, stream>>>(
                d_verified, seg_even_count, d_unverified_count);
            CUDA_CHECK(cudaGetLastError());
            if (shifted_alignment_available) {
                uint64_t result_word_count =
                    (seg_even_count + 63) / 64;
                uint64_t result_remainder = seg_even_count % 64;
                uint64_t result_final_live_mask =
                    result_remainder == 0
                        ? ~0ULL
                        : (1ULL << result_remainder) - 1;
                uint32_t result_count_blocks = static_cast<uint32_t>(
                    (result_word_count + 255) / 256);
                count_uncovered_coverage_words_kernel<<<
                    result_count_blocks, 256, 0, stream>>>(
                    d_coverage_words, result_word_count,
                    result_final_live_mask,
                    d_packed_unverified_count);
                CUDA_CHECK(cudaGetLastError());
            }
            CUDA_CHECK(cudaMemcpyAsync(
                &unverified_count, d_unverified_count,
                sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
            CUDA_CHECK(cudaMemcpyAsync(
                &packed_unverified_count, d_packed_unverified_count,
                sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
            CUDA_CHECK(cudaStreamSynchronize(stream));
            if (shifted_alignment_available &&
                packed_unverified_count != unverified_count) {
                throw std::runtime_error(
                    "packed missing-bit count differs from byte count");
            }
"""


def rewrite_packed_count_crosscheck(source: str) -> str:
    """Add an every-segment packed-count comparison to a dual phase-1 source."""

    inspect_word_owner_source(source)
    if (
        "compare_phase1_verified_kernel" not in source
        or "d_shifted_verified" not in source
    ):
        raise GoldbachShiftedCoverageOptimizerError(
            "packed-count crosscheck requires dual phase-1 execution"
        )
    if (
        _PACKED_COUNT_KERNEL_NAME in source
        or "d_packed_unverified_count" in source
    ):
        raise GoldbachShiftedCoverageOptimizerError(
            "source already contains a packed-count crosscheck"
        )
    rewritten = _replace_once(
        source,
        _KERNEL_MARKER,
        _PACKED_COUNT_KERNEL + _KERNEL_MARKER,
        "packed-count crosscheck kernel",
    )
    for old, new, what in (
        (
            _PACKED_CROSSCHECK_DECLARATION,
            _NEW_PACKED_CROSSCHECK_DECLARATION,
            "packed-count crosscheck declaration",
        ),
        (
            _PACKED_CROSSCHECK_ALLOCATION,
            _NEW_PACKED_CROSSCHECK_ALLOCATION,
            "packed-count crosscheck allocation",
        ),
        (
            _COUNT_UNVERIFIED,
            _DUAL_COUNT_CROSSCHECK,
            "dual missing-bit count",
        ),
        (
            _PACKED_CROSSCHECK_CLEANUP,
            _NEW_PACKED_CROSSCHECK_CLEANUP,
            "packed-count crosscheck cleanup",
        ),
        (
            _PACKED_CROSSCHECK_TOTAL,
            _NEW_PACKED_CROSSCHECK_TOTAL,
            "packed-count crosscheck memory accounting",
        ),
    ):
        rewritten = _replace_once(rewritten, old, new, what)
    required = (
        "__global__ void " + _PACKED_COUNT_KERNEL_NAME,
        "d_packed_unverified_count",
        "packed_unverified_count != unverified_count",
        "packed missing-bit count differs from byte count",
        "2 * sizeof(uint32_t)",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachShiftedCoverageOptimizerError(
            "packed-count crosscheck rewrite failed its postcondition"
        )
    inspect_word_owner_source(rewritten)
    return rewritten


__all__ = [
    "GoldbachShiftedCoverageOptimizerError",
    "rewrite_packed_count_crosscheck",
    "rewrite_packed_shifted_unverified_count",
    "rewrite_shifted_phase1",
    "rewrite_shifted_phase1_crosscheck",
]
