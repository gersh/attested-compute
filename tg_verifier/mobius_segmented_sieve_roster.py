# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Packed artifact mirror for the Lean segmented-sieve roster checker.

This module generates and audits the two flat production artifacts:

* one little-endian ``uint16`` factor code for every integer 2..bound;
* the ascending little-endian ``uint32`` roster of the zero-code survivors.

It mirrors ``MobiusSegmentedSieveRoster.lean``.  The Lean theorem is the
source-level soundness authority; this NumPy implementation is an optimized
artifact tool and is not, by itself, a compiler-refinement proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Iterator

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - exercised on minimal hosts
    raise RuntimeError(
        "mobius segmented-sieve artifacts require NumPy"
    ) from exc


PRODUCTION_BOUND = 100_000_000
PRODUCTION_ROSTER_COUNT = 5_761_455
PRODUCTION_ROSTER_SHA256 = (
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5"
)
PRODUCTION_FACTOR_CODE_SHA256 = (
    "eaafd263fbe58295ace90426d011fff1e745d4d3a86884ca3f6a27698b62c5a9"
)
DEFAULT_CHUNK_ROWS = 4_000_000

U16_LE = np.dtype("<u2")
U32_LE = np.dtype("<u4")
U64 = np.dtype("u8")


@dataclass(frozen=True)
class VerificationReport:
    bound: int
    base_bound: int
    base_prime_count: int
    factor_code_count: int
    factor_code_bytes: int
    factor_code_sha256: str
    roster_count: int
    roster_bytes: int
    roster_sha256: str
    witness_cells: int
    strike_cells: int


def _require_bound(bound: int) -> None:
    if bound < 2:
        raise ValueError("bound must be at least 2")
    if math.isqrt(bound) > np.iinfo(U16_LE).max:
        raise ValueError("square-root base primes do not fit uint16")
    if bound > np.iinfo(U32_LE).max:
        raise ValueError("roster entries do not fit uint32")


def base_primes_through(bound: int) -> list[int]:
    """Return the exact ascending prime list through a small base bound."""

    if bound < 2:
        return []
    sieve = bytearray(b"\x01") * (bound + 1)
    sieve[0:2] = b"\x00\x00"
    for prime in range(2, math.isqrt(bound) + 1):
        if sieve[prime]:
            start = prime * prime
            sieve[start::prime] = b"\x00" * (
                (bound - start) // prime + 1
            )
    return [number for number, flag in enumerate(sieve) if flag]


def _sha256_file(path: Path, chunk_bytes: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def _chunks(count: int, chunk_rows: int) -> Iterator[tuple[int, int]]:
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    for lower in range(0, count, chunk_rows):
        yield lower, min(count, lower + chunk_rows)


def generate(
    bound: int,
    factor_code_path: Path,
    roster_path: Path,
    *,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> VerificationReport:
    """Generate both canonical artifacts and run the full independent audit."""

    _require_bound(bound)
    base_bound = math.isqrt(bound)
    base_primes = base_primes_through(base_bound)
    factor_code_path.parent.mkdir(parents=True, exist_ok=True)
    roster_path.parent.mkdir(parents=True, exist_ok=True)

    code_count = bound - 1
    codes = np.memmap(
        factor_code_path, dtype=U16_LE, mode="w+", shape=(code_count,)
    )
    codes[:] = 0
    for prime in base_primes:
        codes[prime * prime - 2 :: prime] = prime
    codes.flush()

    with roster_path.open("wb") as stream:
        for lower, upper in _chunks(code_count, chunk_rows):
            block = np.asarray(codes[lower:upper])
            survivors = np.flatnonzero(block == 0).astype(U64, copy=False)
            survivors += lower + 2
            stream.write(survivors.astype(U32_LE, copy=False).tobytes())

    del codes
    return verify(
        bound,
        factor_code_path,
        roster_path,
        chunk_rows=chunk_rows,
    )


def verify(
    bound: int,
    factor_code_path: Path,
    roster_path: Path,
    *,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
    require_production_identity: bool = False,
) -> VerificationReport:
    """Audit the exact two directions used by the Lean soundness theorem."""

    _require_bound(bound)
    base_bound = math.isqrt(bound)
    base_primes = base_primes_through(base_bound)
    code_count = bound - 1
    expected_code_bytes = code_count * U16_LE.itemsize
    if factor_code_path.stat().st_size != expected_code_bytes:
        raise ValueError("factor-code artifact has the wrong byte length")
    if roster_path.stat().st_size % U32_LE.itemsize:
        raise ValueError("roster artifact is not a whole u32le stream")

    codes = np.memmap(
        factor_code_path, dtype=U16_LE, mode="r", shape=(code_count,)
    )
    roster_count = roster_path.stat().st_size // U32_LE.itemsize
    roster = np.memmap(
        roster_path, dtype=U32_LE, mode="r", shape=(roster_count,)
    )
    is_base_prime = np.zeros(base_bound + 1, dtype=np.bool_)
    is_base_prime[np.asarray(base_primes, dtype=np.intp)] = True

    # Witness direction: every nonzero code is an actual proper base-prime
    # divisor of the represented number.  This is one division per marked
    # integer, never one division per candidate/base-prime pair.
    roster_cursor = 0
    for lower, upper in _chunks(code_count, chunk_rows):
        code_block = np.asarray(codes[lower:upper], dtype=U64)
        marked = code_block != 0
        marked_codes = code_block[marked]
        if marked_codes.size:
            if int(marked_codes.max()) > base_bound:
                raise ValueError("factor code exceeds the checked base bound")
            if not bool(np.all(is_base_prime[marked_codes.astype(np.intp)])):
                raise ValueError("factor code is not in the base-prime roster")
            numbers = np.arange(
                lower + 2, upper + 2, dtype=U64
            )[marked]
            if not bool(np.all(marked_codes < numbers)):
                raise ValueError("factor code is not a proper divisor")
            if not bool(np.all(numbers % marked_codes == 0)):
                raise ValueError("factor code does not divide its number")

        survivors = np.flatnonzero(~marked).astype(U64, copy=False)
        survivors += lower + 2
        next_cursor = roster_cursor + int(survivors.size)
        if next_cursor > roster_count:
            raise ValueError("roster omits sieve survivors")
        if not np.array_equal(
            roster[roster_cursor:next_cursor],
            survivors.astype(U32_LE, copy=False),
        ):
            raise ValueError("roster is not the ascending survivor list")
        roster_cursor = next_cursor

    if roster_cursor != roster_count:
        raise ValueError("roster contains extra entries")

    # Coverage direction: all p*q with p checked prime and q >= p are marked.
    strike_cells = 0
    for prime in base_primes:
        progression = codes[prime * prime - 2 :: prime]
        strike_cells += int(progression.size)
        if bool(np.any(progression == 0)):
            raise ValueError(f"missing sieve strike for base prime {prime}")

    factor_digest = _sha256_file(factor_code_path)
    roster_digest = _sha256_file(roster_path)
    if require_production_identity:
        if bound != PRODUCTION_BOUND:
            raise ValueError("production identity requires bound 100000000")
        if roster_count != PRODUCTION_ROSTER_COUNT:
            raise ValueError("production roster count changed")
        if factor_digest != PRODUCTION_FACTOR_CODE_SHA256:
            raise ValueError("production factor-code digest changed")
        if roster_digest != PRODUCTION_ROSTER_SHA256:
            raise ValueError("production roster digest changed")

    return VerificationReport(
        bound=bound,
        base_bound=base_bound,
        base_prime_count=len(base_primes),
        factor_code_count=code_count,
        factor_code_bytes=expected_code_bytes,
        factor_code_sha256=factor_digest,
        roster_count=roster_count,
        roster_bytes=roster_path.stat().st_size,
        roster_sha256=roster_digest,
        witness_cells=code_count,
        strike_cells=strike_cells,
    )


def report_dict(report: VerificationReport) -> dict[str, int | str]:
    return asdict(report)
