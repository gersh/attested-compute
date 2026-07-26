# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Checked source transformation for the GoldbachGPU word-owner cutoff.

The hardened GoldbachGPU sieve gives one CUDA thread exclusive ownership of
each 64-bit output word for a fixed prefix of odd primes.  Larger primes are
handled by the global-atomic tail kernel.  Moving the cutoff is semantics
preserving only when both the compile-time calls and the runtime tail offset
move together.

This module performs exactly that paired rewrite.  It first checks that the
input source lists every prime, once and in increasing order, through the
declared cutoff.  It then rewrites only the cutoff literal and that list and
checks the result again.  It deliberately does not update any reviewed source
identity or production admission: benchmark candidates are diagnostic build
inputs until a selected source patch is separately reviewed and pinned.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


class GoldbachWordOwnerOptimizerError(RuntimeError):
    """The source is not in the reviewed word-owner form."""


_LIMIT_RE = re.compile(
    r"(?m)^(?P<prefix>\s*static const uint64_t "
    r"WORD_OWNER_SIEVE_LIMIT = )(?P<limit>[0-9]+)(?P<suffix>;\s*)$"
)
_CLEAR_RE = re.compile(
    r"(?m)^(?P<indent>\s*)clear_small_prime_from_word<"
    r"(?P<prime>[0-9]+)>\(word_low, word\);\s*$"
)
_FUNCTION_START = "__global__ void initialize_small_prime_words_kernel("
_FUNCTION_END = "    segment_bits[word_index] = word;"


def primes_through(limit: int) -> tuple[int, ...]:
    """Return the odd primes at most ``limit`` by an exact integer sieve."""

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise GoldbachWordOwnerOptimizerError("cutoff must be an integer")
    if limit < 3:
        raise GoldbachWordOwnerOptimizerError("cutoff must be at least 3")
    composite = bytearray(limit + 1)
    for prime in range(2, int(limit**0.5) + 1):
        if composite[prime]:
            continue
        composite[prime * prime : limit + 1 : prime] = b"\x01" * (
            (limit - prime * prime) // prime + 1
        )
    return tuple(
        value
        for value in range(3, limit + 1, 2)
        if composite[value] == 0
    )


@dataclass(frozen=True)
class WordOwnerSource:
    """The checked cutoff and compile-time prime calls in one source."""

    cutoff: int
    primes: tuple[int, ...]
    clear_indent: str


def _word_owner_region(source: str) -> tuple[int, int]:
    start = source.find(_FUNCTION_START)
    if start < 0:
        raise GoldbachWordOwnerOptimizerError(
            "word-owner initialization kernel is missing"
        )
    end_marker = source.find(_FUNCTION_END, start)
    if end_marker < 0:
        raise GoldbachWordOwnerOptimizerError(
            "word-owner initialization kernel terminator is missing"
        )
    end = end_marker + len(_FUNCTION_END)
    if source.find(_FUNCTION_START, start + 1) >= 0:
        raise GoldbachWordOwnerOptimizerError(
            "multiple word-owner initialization kernels found"
        )
    return start, end


def inspect_word_owner_source(source: str) -> WordOwnerSource:
    """Fail closed unless ``source`` has the exact reviewed prime-prefix form."""

    limits = list(_LIMIT_RE.finditer(source))
    if len(limits) != 1:
        raise GoldbachWordOwnerOptimizerError(
            "expected exactly one WORD_OWNER_SIEVE_LIMIT declaration"
        )
    cutoff = int(limits[0].group("limit"))
    start, end = _word_owner_region(source)
    calls = list(_CLEAR_RE.finditer(source[start:end]))
    if not calls:
        raise GoldbachWordOwnerOptimizerError(
            "word-owner initialization kernel has no prime calls"
        )
    indents = {match.group("indent") for match in calls}
    if len(indents) != 1:
        raise GoldbachWordOwnerOptimizerError(
            "word-owner prime calls do not use one indentation"
        )
    listed = tuple(int(match.group("prime")) for match in calls)
    expected = primes_through(cutoff)
    if listed != expected:
        raise GoldbachWordOwnerOptimizerError(
            "word-owner calls are not exactly the increasing odd primes "
            f"through the declared cutoff {cutoff}"
        )
    return WordOwnerSource(
        cutoff=cutoff,
        primes=listed,
        clear_indent=next(iter(indents)),
    )


def rewrite_word_owner_cutoff(source: str, cutoff: int) -> str:
    """Return the unique source rewrite for a new word-owner cutoff.

    Only two source regions may change:

    * ``WORD_OWNER_SIEVE_LIMIT``; and
    * the compile-time ``clear_small_prime_from_word<P>`` call list.
    """

    inspected = inspect_word_owner_source(source)
    replacement_primes = primes_through(cutoff)
    start, end = _word_owner_region(source)
    region = source[start:end]
    calls = list(_CLEAR_RE.finditer(region))
    first = calls[0].start()
    last = calls[-1].end()
    call_lines = "\n".join(
        f"{inspected.clear_indent}clear_small_prime_from_word<{prime}>"
        "(word_low, word);"
        for prime in replacement_primes
    )
    rewritten_region = region[:first] + call_lines + region[last:]
    rewritten = source[:start] + rewritten_region + source[end:]
    rewritten, replacements = _LIMIT_RE.subn(
        lambda match: (
            match.group("prefix") + str(cutoff) + match.group("suffix")
        ),
        rewritten,
    )
    if replacements != 1:
        raise GoldbachWordOwnerOptimizerError(
            "cutoff declaration rewrite was not unique"
        )
    checked = inspect_word_owner_source(rewritten)
    if checked.cutoff != cutoff or checked.primes != replacement_primes:
        raise GoldbachWordOwnerOptimizerError(
            "rewritten source failed its postcondition"
        )

    # Rewriting to the current cutoff must be byte-for-byte idempotent.  This
    # catches whitespace or region-selection drift before it can pollute an
    # A/B benchmark.
    if cutoff == inspected.cutoff and rewritten != source:
        raise GoldbachWordOwnerOptimizerError(
            "same-cutoff rewrite is not byte-for-byte idempotent"
        )
    return rewritten


__all__ = [
    "GoldbachWordOwnerOptimizerError",
    "WordOwnerSource",
    "inspect_word_owner_source",
    "primes_through",
    "rewrite_word_owner_cutoff",
]
