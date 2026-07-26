# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed audit of the surviving Oliveira e Silva Goldbach summary.

The archived author-site table is useful historical evidence.  It is not the
27 GB per-shard corpus described in the paper, and checking its aggregate
counts cannot independently replay the computation.  This module therefore
keeps identity/internal-consistency acceptance separate from receipt
eligibility and from the binary-Goldbach proposition.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable


BINARY_LIMIT = 4_000_000_000_000_000_000
BINARY_EVEN_COUNT = 1_999_999_999_999_999_999
PUBLIC_SUMMARY_ORIGINAL_URL = "https://sweet.ua.pt/tos/goldbach/t0.txt.gz"
PUBLIC_SUMMARY_ARCHIVE_URL = (
    "https://web.archive.org/web/20160119111827id_/"
    "http://sweet.ua.pt/tos/goldbach/t0.txt.gz"
)
PUBLIC_SUMMARY_ARCHIVE_TIMESTAMP = "20160119111827"
PUBLIC_SUMMARY_ARCHIVE_SHA1_BASE32 = "OJ22U62I6YI2UVRCI7SATJPJZMVW5YH5"
PUBLIC_SUMMARY_GZIP_SHA256 = (
    "fa5e73f253154342e2d13ad095f32bab4a1670c517baaf9b3da42751f8010fce"
)
PUBLIC_SUMMARY_GZIP_SIZE = 24_812
PUBLIC_SUMMARY_RAW_SHA256 = (
    "c3030137b247f6895bb003b413ac33285456d7821e680e1ec653b3de364c60ed"
)
PUBLIC_SUMMARY_RAW_SIZE = 81_850
PUBLIC_SUMMARY_LAST_PRIME = 9_781
PUBLIC_SUMMARY_PRIME_ROWS = 1_206
PUBLIC_SUMMARY_POSITIVE_ROWS = 1_101
PUBLIC_SUMMARY_ZERO_ROWS = 105
PUBLIC_SUMMARY_MAX_FIRST_OCCURRENCE = 3_893_009_227_433_420_582

_ROW_RE = re.compile(
    r"^\s*(?P<prime_index>\d+)\s+"
    r"(?P<prime>\d+)(?P<prime_record>\*)?\s+"
    r"(?P<first>\?|\d+)(?P<first_record>\*)?\s+"
    r"(?P<count>\d+)(?:\s+(?P<finder>.*))?$"
)


class HistoricalGoldbachArtifactError(ValueError):
    """The historical artifact is malformed, unpinned, or inconsistent."""


@dataclass(frozen=True)
class SummaryRow:
    prime_index: int
    prime: int
    first_occurrence: int | None
    count: int
    prime_record: bool
    first_record: bool


@dataclass(frozen=True)
class SummaryAudit:
    compressed_sha256: str
    uncompressed_sha256: str
    archive_sha1_base32: str
    unique_prime_rows: int
    positive_count_rows: int
    zero_count_rows: int
    largest_prime: int
    largest_first_occurrence: int
    total_partition_count: int
    tested_even_count: int
    checked_partition_witnesses: int

    def as_json(self) -> dict[str, Any]:
        return {
            "accepted": True,
            "artifact_kind": "oeshp.goldbach-author-summary.v1",
            "classification": (
                "pinned_archived_author_summary_identity_and_"
                "internal_consistency_only"
            ),
            "original_url": PUBLIC_SUMMARY_ORIGINAL_URL,
            "archive_url": PUBLIC_SUMMARY_ARCHIVE_URL,
            "archive_timestamp": PUBLIC_SUMMARY_ARCHIVE_TIMESTAMP,
            "compressed_sha256": self.compressed_sha256,
            "uncompressed_sha256": self.uncompressed_sha256,
            "archive_sha1_base32": self.archive_sha1_base32,
            "binary_limit_reported": BINARY_LIMIT,
            "unique_prime_rows": self.unique_prime_rows,
            "positive_count_rows": self.positive_count_rows,
            "zero_count_rows": self.zero_count_rows,
            "largest_prime": self.largest_prime,
            "largest_first_occurrence": self.largest_first_occurrence,
            "total_partition_count": self.total_partition_count,
            "tested_even_count": self.tested_even_count,
            "checked_partition_witnesses": self.checked_partition_witnesses,
            "aggregate_count_matches_all_evens": (
                self.total_partition_count == self.tested_even_count
            ),
            "full_27gb_shard_corpus_present": False,
            "historical_execution_independently_replayed": False,
            "independently_proves_binary_goldbach": False,
            "receipt_eligible": False,
            "source_scale_completed": False,
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HistoricalGoldbachArtifactError(message)


def _is_prime_u64(value: int) -> bool:
    """Deterministic Miller--Rabin for integers below ``2^64``."""

    if isinstance(value, bool) or not isinstance(value, int):
        return False
    if value < 2 or value >= 1 << 64:
        return False
    for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if value % prime == 0:
            return value == prime
    odd_part = value - 1
    power = 0
    while odd_part % 2 == 0:
        odd_part //= 2
        power += 1
    for base in (2, 325, 9_375, 28_178, 450_775, 9_780_504, 1_795_265_022):
        if base % value == 0:
            continue
        witness = pow(base, odd_part, value)
        if witness in (1, value - 1):
            continue
        for _ in range(power - 1):
            witness = witness * witness % value
            if witness == value - 1:
                break
        else:
            return False
    return True


def _primes_through(limit: int) -> list[int]:
    return [value for value in range(2, limit + 1) if _is_prime_u64(value)]


def parse_summary_rows(text: str) -> list[SummaryRow]:
    """Parse every data row, retaining the table's record markers."""

    rows: list[SummaryRow] = []
    for line in text.splitlines():
        match = _ROW_RE.fullmatch(line)
        if match is None:
            continue
        first_text = match.group("first")
        rows.append(
            SummaryRow(
                prime_index=int(match.group("prime_index")),
                prime=int(match.group("prime")),
                first_occurrence=(
                    None if first_text == "?" else int(first_text)
                ),
                count=int(match.group("count")),
                prime_record=match.group("prime_record") is not None,
                first_record=match.group("first_record") is not None,
            )
        )
    _require(rows, "summary contains no data rows")
    return rows


def audit_summary_rows(
    rows: Iterable[SummaryRow],
    *,
    binary_limit: int,
    expected_last_prime: int,
) -> dict[str, int]:
    """Check row arithmetic without elevating aggregates to execution proof."""

    _require(
        binary_limit >= 4 and binary_limit % 2 == 0,
        "binary limit must be an even integer at least four",
    )
    by_prime: dict[int, SummaryRow] = {}
    for row in rows:
        _require(row.count >= 0, "negative summary count")
        prior = by_prime.get(row.prime)
        if prior is not None:
            _require(
                (
                    prior.prime_index,
                    prior.first_occurrence,
                    prior.count,
                    prior.prime_record,
                )
                == (
                    row.prime_index,
                    row.first_occurrence,
                    row.count,
                    row.prime_record,
                ),
                f"conflicting duplicate row for prime {row.prime}",
            )
            # The author table repeats the first unresolved row once: in the
            # record-holder section with ``?*`` and in the zero-count appendix
            # with ``?``.  Only that marker is permitted to differ.
            _require(
                prior.first_occurrence is None and prior.count == 0,
                f"duplicate positive row for prime {row.prime}",
            )
            continue
        by_prime[row.prime] = row

    expected_primes = _primes_through(expected_last_prime)
    _require(
        sorted(by_prime) == expected_primes,
        "summary rows are not exactly the consecutive primes through the endpoint",
    )
    _require(
        len(expected_primes) == by_prime[expected_last_prime].prime_index,
        "last pi(p) index does not match the independent prime enumeration",
    )
    for index, prime in enumerate(expected_primes, start=1):
        _require(
            by_prime[prime].prime_index == index,
            f"wrong pi(p) index for prime {prime}",
        )

    first_occurrences: set[int] = set()
    positive = 0
    zero = 0
    for prime in expected_primes:
        row = by_prime[prime]
        _require(
            (row.first_occurrence is None) == (row.count == 0),
            f"first-occurrence/count mismatch for prime {prime}",
        )
        if row.first_occurrence is None:
            zero += 1
            continue
        positive += 1
        first = row.first_occurrence
        _require(
            4 <= first <= binary_limit and first % 2 == 0,
            f"first occurrence for prime {prime} is outside the even domain",
        )
        _require(
            prime <= first - prime and _is_prime_u64(first - prime),
            f"reported first occurrence for {prime} is not a prime partition",
        )
        _require(
            all(
                not _is_prime_u64(first - smaller)
                for smaller in expected_primes
                if smaller < prime
            ),
            f"reported partition for {prime} has a smaller prime summand",
        )
        _require(
            first not in first_occurrences,
            "two primes claim the same first-occurrence even integer",
        )
        first_occurrences.add(first)

    tested_even_count = (binary_limit - 4) // 2 + 1
    total = sum(row.count for row in by_prime.values())
    _require(
        total == tested_even_count,
        "partition-count aggregate does not equal the number of tested evens",
    )
    return {
        "unique_prime_rows": len(by_prime),
        "positive_count_rows": positive,
        "zero_count_rows": zero,
        "largest_prime": max(by_prime),
        "largest_first_occurrence": max(first_occurrences),
        "total_partition_count": total,
        "tested_even_count": tested_even_count,
        "checked_partition_witnesses": positive,
    }


def _read_regular_file_once(path: Path) -> bytes:
    if path.is_symlink():
        raise HistoricalGoldbachArtifactError("summary path must not be a symlink")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HistoricalGoldbachArtifactError(
            f"cannot open historical summary: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), "summary must be a regular file")
        _require(
            metadata.st_size == PUBLIC_SUMMARY_GZIP_SIZE,
            "summary compressed size differs from the archive capture",
        )
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            _require(chunk != b"", "summary ended before its recorded size")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(
            os.read(descriptor, 1) == b"",
            "summary grew while it was being captured",
        )
        return b"".join(chunks)
    except OSError as error:
        raise HistoricalGoldbachArtifactError(
            f"cannot read historical summary: {error}"
        ) from error
    finally:
        os.close(descriptor)


def audit_public_summary(path: Path) -> SummaryAudit:
    """Audit the exact archived author-site ``t0.txt.gz`` capture."""

    compressed = _read_regular_file_once(path)
    compressed_sha256 = hashlib.sha256(compressed).hexdigest()
    _require(
        compressed_sha256 == PUBLIC_SUMMARY_GZIP_SHA256,
        "summary SHA-256 differs from the pinned archive capture",
    )
    archive_sha1_base32 = base64.b32encode(
        hashlib.sha1(compressed, usedforsecurity=False).digest()
    ).decode("ascii")
    _require(
        archive_sha1_base32 == PUBLIC_SUMMARY_ARCHIVE_SHA1_BASE32,
        "summary SHA-1 differs from the Internet Archive CDX digest",
    )
    try:
        raw = gzip.decompress(compressed)
    except (EOFError, OSError) as error:
        raise HistoricalGoldbachArtifactError(
            f"cannot decompress historical summary: {error}"
        ) from error
    _require(
        len(raw) == PUBLIC_SUMMARY_RAW_SIZE,
        "summary uncompressed size differs from the pinned capture",
    )
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    _require(
        raw_sha256 == PUBLIC_SUMMARY_RAW_SHA256,
        "summary uncompressed SHA-256 mismatch",
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HistoricalGoldbachArtifactError(
            "historical summary is not strict UTF-8"
        ) from error
    for required in (
        "# Test interval ---------- [4,4d18]",
        "# Double test interval --- [4,4d17]",
        "# Last update made on April 7, 2012",
        "# EOF",
    ):
        _require(required in text, f"summary omits required line: {required}")

    metrics = audit_summary_rows(
        parse_summary_rows(text),
        binary_limit=BINARY_LIMIT,
        expected_last_prime=PUBLIC_SUMMARY_LAST_PRIME,
    )
    expected_metrics = {
        "unique_prime_rows": PUBLIC_SUMMARY_PRIME_ROWS,
        "positive_count_rows": PUBLIC_SUMMARY_POSITIVE_ROWS,
        "zero_count_rows": PUBLIC_SUMMARY_ZERO_ROWS,
        "largest_prime": PUBLIC_SUMMARY_LAST_PRIME,
        "largest_first_occurrence": PUBLIC_SUMMARY_MAX_FIRST_OCCURRENCE,
        "total_partition_count": BINARY_EVEN_COUNT,
        "tested_even_count": BINARY_EVEN_COUNT,
        "checked_partition_witnesses": PUBLIC_SUMMARY_POSITIVE_ROWS,
    }
    _require(metrics == expected_metrics, "summary metrics differ from the pin")
    return SummaryAudit(
        compressed_sha256=compressed_sha256,
        uncompressed_sha256=raw_sha256,
        archive_sha1_base32=archive_sha1_base32,
        **metrics,
    )


def canonical_audit_bytes(audit: SummaryAudit) -> bytes:
    """Canonical non-receipt audit record for retention beside a run bundle."""

    return (
        json.dumps(
            audit.as_json(),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
