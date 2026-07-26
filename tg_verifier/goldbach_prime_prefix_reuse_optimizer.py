# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Checked GoldbachGPU rewrite that reuses an existing prime-table prefix.

The optimized Goldbach candidate first builds ``small_primes`` by scanning a
``PrimeBitset`` through ``small_high``.  At the source-height workload,
``small_high`` is larger than the separate 100,000,000 phase-2 sieve bound.
The original program nevertheless runs a second sieve to construct
``cpu_primes``.  This rewrite takes the already sorted prefix instead.

If ``small_high`` is below the phase-2 bound, the original generator is used
unchanged.  A diagnostic variant additionally regenerates the reference
vector and compares every element before any GPU work.  Neither variant
changes a production registration or trust claim.
"""

from __future__ import annotations

import hashlib


class GoldbachPrimePrefixReuseError(RuntimeError):
    """The source cannot receive the unique reviewed prefix-reuse rewrite."""


V1_OPTIMIZED_SOURCE_SHA256 = (
    "2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c"
)
V1_OPTIMIZED_SOURCE_BYTES = 71_853
V2_ALGORITHM_CANDIDATE_ID = (
    "sparkinterval.goldbach-10pow27-wheel47-warp32749-"
    "shifted-packed-prime-prefix-reuse.v2"
)

_ORIGINAL = """\
    std::cout << "Pre-generating CPU primes up to " << PHASE2_SIEVE_LIMIT << "...\\n";
    std::vector<uint64_t> cpu_primes = generate_cpu_primes(PHASE2_SIEVE_LIMIT);
"""

_REUSED = """\
    std::vector<uint64_t> cpu_primes;
    if (small_high >= PHASE2_SIEVE_LIMIT) {
        // `small_primes` is the ascending scan of the already completed
        // PrimeBitset.  Its bounded prefix is exactly the independent
        // phase-2 prime table, without a second sieve.
        auto cpu_prime_end = std::upper_bound(
            small_primes.begin(), small_primes.end(),
            PHASE2_SIEVE_LIMIT);
        cpu_primes.assign(small_primes.begin(), cpu_prime_end);
        std::cout
            << "Reusing CPU-prime prefix through "
            << PHASE2_SIEVE_LIMIT << "...\\n";
    } else {
        std::cout
            << "Pre-generating CPU primes up to "
            << PHASE2_SIEVE_LIMIT << "...\\n";
        cpu_primes = generate_cpu_primes(PHASE2_SIEVE_LIMIT);
    }
"""

_CROSSCHECK = _REUSED + """\
    // Bounded diagnostic only: compare the complete ordered vector, not just
    // its size, endpoints, or a digest.
    std::vector<uint64_t> reference_cpu_primes =
        generate_cpu_primes(PHASE2_SIEVE_LIMIT);
    if (cpu_primes != reference_cpu_primes) {
        throw std::runtime_error(
            "reused CPU-prime prefix differs from independent sieve");
    }
    std::cout
        << "CPU-prime prefix exact-vector crosscheck: "
        << cpu_primes.size() << " entries matched.\\n";
"""


def _validate_v1_source(source: str) -> None:
    encoded = source.encode("utf-8")
    if (
        len(encoded) != V1_OPTIMIZED_SOURCE_BYTES
        or hashlib.sha256(encoded).hexdigest()
        != V1_OPTIMIZED_SOURCE_SHA256
    ):
        raise GoldbachPrimePrefixReuseError(
            "input is not the exact qualified v1 optimized goldbach.cu"
        )
    if source.count(_ORIGINAL) != 1:
        raise GoldbachPrimePrefixReuseError(
            "phase-2 prime-table construction is not unique"
        )
    if (
        "Reusing CPU-prime prefix through " in source
        or "CPU-prime prefix exact-vector crosscheck: " in source
    ):
        raise GoldbachPrimePrefixReuseError(
            "source already contains the prefix-reuse optimization"
        )


def rewrite_prime_prefix_reuse(source: str) -> str:
    """Reuse the exact ordered prefix when the existing table is large enough."""

    _validate_v1_source(source)
    rewritten = source.replace(_ORIGINAL, _REUSED, 1)
    required = (
        "small_high >= PHASE2_SIEVE_LIMIT",
        "std::upper_bound(",
        "cpu_primes.assign(small_primes.begin(), cpu_prime_end);",
        "cpu_primes = generate_cpu_primes(PHASE2_SIEVE_LIMIT);",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachPrimePrefixReuseError(
            "prefix-reuse rewrite failed its source postcondition"
        )
    return rewritten


def rewrite_prime_prefix_reuse_crosscheck(source: str) -> str:
    """Generate a diagnostic that requires element-for-element vector equality."""

    _validate_v1_source(source)
    rewritten = source.replace(_ORIGINAL, _CROSSCHECK, 1)
    required = (
        "cpu_primes != reference_cpu_primes",
        "reused CPU-prime prefix differs from independent sieve",
        "CPU-prime prefix exact-vector crosscheck: ",
    )
    if not all(text in rewritten for text in required):
        raise GoldbachPrimePrefixReuseError(
            "prefix-reuse crosscheck failed its source postcondition"
        )
    return rewritten


__all__ = [
    "GoldbachPrimePrefixReuseError",
    "V1_OPTIMIZED_SOURCE_BYTES",
    "V1_OPTIMIZED_SOURCE_SHA256",
    "V2_ALGORITHM_CANDIDATE_ID",
    "rewrite_prime_prefix_reuse",
    "rewrite_prime_prefix_reuse_crosscheck",
]
