# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable certificates for the Helfgott--Platt prime-ladder campaign.

The range files in this module retain every ladder rung.  A successful ladder
check is deliberately *conditional* on a separately replayed verification of
binary Goldbach through ``4 * 10**18``.  Neither a hash nor a ladder receipt is
treated as evidence for that prerequisite.

The production constants are those of arXiv:1305.3062v2: ``n = 52``, range
width ``2**54 * 10**9``, 492700 ranges, endpoint tolerance ``2 * 10**18``,
and ladder step bound ``4 * 10**18``.
"""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import BinaryIO, Iterable, Iterator, Mapping, Sequence

from .campaign_io import CampaignIOError, advisory_lock
from .goldbach import is_prime_bounded, jacobi_symbol


ATOM_ID = "helfgott-platt-theorem-4-1"
SCHEMA = "tg_goldbach_ladder_campaign_v1"
RANGE_KIND = "tg_goldbach_ladder_range_v1"
RECEIPT_KIND = "tg_goldbach_ladder_receipt_v1"
POCKLINGTON_KIND = "tg_pocklington_certificate_v1"
BINARY_REQUEST_KIND = "tg_binary_goldbach_request_v1"
BINARY_RESULT_KIND = "tg_binary_goldbach_result_v1"
GENERAL_REQUEST_KIND = "tg_general_prime_request_v1"
GENERAL_RESULT_KIND = "tg_general_prime_result_v1"
INDEPENDENT_SCHEMA = "tg_goldbach_ladder_parallel_campaign_v1"
INDEPENDENT_RECEIPT_KIND = "tg_goldbach_ladder_range_receipt_v1"
INDEPENDENT_AGGREGATE_KIND = "tg_goldbach_ladder_parallel_aggregate_v1"
COMBINED_GPU_RESULT_KIND = "tg_goldbach_gpu_plus_ladder_result_v1"
OPTIMIZED_COMBINED_GPU_RESULT_KIND = (
    "tg_goldbach_optimized_gpu_plus_ladder_result_v1"
)
WORKER_GROUP_RESULT_KIND = "tg_goldbach_ladder_worker_group_result_v1"

PROTH_EXPONENT = 52
PROTH_POWER = 1 << PROTH_EXPONENT
SOURCE_RANGE_WIDTH = (1 << 54) * 10**9
SOURCE_RANGE_COUNT = 492_700
SOURCE_ENDPOINT = SOURCE_RANGE_COUNT * SOURCE_RANGE_WIDTH
SOURCE_MAXIMUM_GAP = 4 * 10**18
SOURCE_ENDPOINT_TOLERANCE = 2 * 10**18
SOURCE_BINARY_FIRST_EVEN = 4
SOURCE_BINARY_LAST_EVEN = 4 * 10**18
SOURCE_PROTH_WITNESSES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)
SOURCE_SIEVE_BOUND = 16_000

# Distinct production schedule used when the analytic proof is closed from
# 10^27 onward.  These constants do not replace or weaken the historical
# Helfgott--Platt schedule above; ``CampaignParameters.validate`` treats each
# profile as an immutable, exact tuple.
ANALYTIC_10POW27_MODE = "analytic_10pow27"
ANALYTIC_10POW27_ATOM_ID = "ternary-goldbach-finite-below-10pow27"
ANALYTIC_10POW27_TARGET = 10**27
ANALYTIC_10POW27_PROTH_EXPONENT = 45
ANALYTIC_10POW27_RANGE_WIDTH = (1 << 47) * 10**9
ANALYTIC_10POW27_RANGE_COUNT = 7_106
ANALYTIC_10POW27_ENDPOINT = (
    ANALYTIC_10POW27_RANGE_WIDTH * ANALYTIC_10POW27_RANGE_COUNT
)
ANALYTIC_10POW27_MAXIMUM_GAP = 31_250_000_000_000_000
ANALYTIC_10POW27_ENDPOINT_TOLERANCE = 15_625_000_000_000_000
ANALYTIC_10POW27_BINARY_FIRST_EVEN = 4
ANALYTIC_10POW27_BINARY_LAST_EVEN = ANALYTIC_10POW27_MAXIMUM_GAP

MAGIC = b"TGGLRNG1"
TAG_DIRECT64 = 0
TAG_PROTH52 = 1
TAG_POCKLINGTON = 2
TAG_EXTERNAL = 3
# Tag 1 remains permanently reserved for historical fixed-n=52 artifacts.
# Parameterized campaigns use a distinct tag whose exponent is committed by
# the campaign manifest, so their evidence is never mislabeled ``proth52``.
TAG_PROTH = 4
ZERO_HASH = "0" * 64
MAX_HEADER_BYTES = 1 << 20
MAX_VARINT_BYTES = 32

_RANGE_RECEIPT_DOMAIN = b"tg/goldbach-ladder/range-receipt/v1\x00"
_RANGE_MERKLE_LEAF_DOMAIN = b"tg/goldbach-ladder/merkle-leaf/v1\x00"
_RANGE_MERKLE_NODE_DOMAIN = b"tg/goldbach-ladder/merkle-node/v1\x00"
_RANGE_MERKLE_ODD_DOMAIN = b"tg/goldbach-ladder/merkle-odd/v1\x00"
_RANGE_AGGREGATE_DOMAIN = b"tg/goldbach-ladder/aggregate/v1\x00"
_COMBINED_GPU_DOMAIN = b"tg/goldbach-ladder/combined-gpu/v1\x00"
_OPTIMIZED_COMBINED_GPU_DOMAIN = (
    b"tg/goldbach-ladder/combined-optimized-gpu/v1\x00"
)
_RECEIPT_FILENAME_RE = re.compile(r"^receipt-([0-9]{6})\.json$")


class CampaignError(RuntimeError):
    """A malformed, incomplete, or unsupported campaign."""


def campaign_atom_id(parameters: "CampaignParameters") -> str:
    """Return the semantic campaign identity committed by range artifacts."""

    return (
        ANALYTIC_10POW27_ATOM_ID
        if parameters.mode == ANALYTIC_10POW27_MODE
        else ATOM_ID
    )


def _plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read_canonical_json(path: Path) -> object:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"invalid JSON: {path}") from exc
    if raw != canonical_json_bytes(value):
        raise CampaignError(f"JSON is not canonical: {path}")
    return value


def _decimal(value: object, field: str) -> int:
    if not isinstance(value, str) or not value or not value.isascii():
        raise CampaignError(f"{field} must be a canonical decimal string")
    if not value.isdigit() or (len(value) > 1 and value[0] == "0"):
        raise CampaignError(f"{field} must be a canonical decimal string")
    return int(value)


def _hex_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CampaignError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _write_varint(stream: BinaryIO, value: int) -> None:
    if not _plain_int(value) or value < 0:
        raise CampaignError("varint must be a nonnegative integer")
    while value >= 0x80:
        stream.write(bytes(((value & 0x7F) | 0x80,)))
        value >>= 7
    stream.write(bytes((value,)))


def _read_varint(stream: BinaryIO) -> int:
    value = 0
    for shift in range(0, 7 * MAX_VARINT_BYTES, 7):
        byte = stream.read(1)
        if len(byte) != 1:
            raise CampaignError("truncated varint")
        octet = byte[0]
        value |= (octet & 0x7F) << shift
        if octet < 0x80:
            if shift and octet == 0:
                raise CampaignError("non-canonical varint")
            return value
    raise CampaignError("oversized varint")


@dataclass(frozen=True)
class CampaignParameters:
    """A source or explicitly bounded-test schedule."""

    range_width: int = SOURCE_RANGE_WIDTH
    range_count: int = SOURCE_RANGE_COUNT
    maximum_gap: int = SOURCE_MAXIMUM_GAP
    endpoint_tolerance: int = SOURCE_ENDPOINT_TOLERANCE
    binary_first_even: int = SOURCE_BINARY_FIRST_EVEN
    binary_last_even: int = SOURCE_BINARY_LAST_EVEN
    proth_exponent: int = PROTH_EXPONENT
    seed_prime: int = 3
    mode: str = "full_source"

    @property
    def endpoint(self) -> int:
        return self.range_width * self.range_count

    def validate(self) -> None:
        values = (
            self.range_width,
            self.range_count,
            self.maximum_gap,
            self.endpoint_tolerance,
            self.binary_first_even,
            self.binary_last_even,
            self.proth_exponent,
            self.seed_prime,
        )
        if not all(_plain_int(value) and value > 0 for value in values):
            raise CampaignError("campaign parameters must be positive integers")
        if self.endpoint_tolerance * 2 != self.maximum_gap:
            raise CampaignError("endpoint tolerance must be half the ladder bound")
        if self.binary_first_even != 4 or self.binary_first_even % 2:
            raise CampaignError("binary prerequisite must begin at even integer 4")
        if self.binary_last_even != self.maximum_gap:
            raise CampaignError("binary endpoint and ladder bound must agree")
        if not is_prime_bounded(self.seed_prime) or self.seed_prime % 2 == 0:
            raise CampaignError("seed must be an odd, directly checked prime")
        if self.mode not in ("full_source", "bounded_test", ANALYTIC_10POW27_MODE):
            raise CampaignError("unknown campaign mode")
        if self.mode == "full_source" and self != CampaignParameters():
            raise CampaignError("full_source parameters must equal the paper constants")
        if self.mode == ANALYTIC_10POW27_MODE and (
            self.range_width != ANALYTIC_10POW27_RANGE_WIDTH
            or self.range_count != ANALYTIC_10POW27_RANGE_COUNT
            or self.maximum_gap != ANALYTIC_10POW27_MAXIMUM_GAP
            or self.endpoint_tolerance != ANALYTIC_10POW27_ENDPOINT_TOLERANCE
            or self.binary_first_even != ANALYTIC_10POW27_BINARY_FIRST_EVEN
            or self.binary_last_even != ANALYTIC_10POW27_BINARY_LAST_EVEN
            or self.proth_exponent != ANALYTIC_10POW27_PROTH_EXPONENT
            or self.seed_prime != 3
        ):
            raise CampaignError(
                "analytic_10pow27 parameters must equal the reviewed production constants"
            )

    def to_json(self) -> dict[str, object]:
        self.validate()
        return {
            "binary_first_even": str(self.binary_first_even),
            "binary_last_even": str(self.binary_last_even),
            "endpoint": str(self.endpoint),
            "endpoint_tolerance": str(self.endpoint_tolerance),
            "maximum_gap": str(self.maximum_gap),
            "mode": self.mode,
            "proth_exponent": self.proth_exponent,
            "range_count": self.range_count,
            "range_width": str(self.range_width),
            "seed_prime": str(self.seed_prime),
        }

    @staticmethod
    def from_json(root: object) -> "CampaignParameters":
        if not isinstance(root, dict):
            raise CampaignError("parameters must be an object")
        expected = {
            "binary_first_even", "binary_last_even", "endpoint",
            "endpoint_tolerance", "maximum_gap", "mode", "proth_exponent",
            "range_count", "range_width", "seed_prime",
        }
        if set(root) != expected:
            raise CampaignError("parameter field set mismatch")
        mode = root["mode"]
        if not isinstance(mode, str):
            raise CampaignError("mode must be a string")
        exponent = root["proth_exponent"]
        count = root["range_count"]
        if not _plain_int(exponent) or not _plain_int(count):
            raise CampaignError("integer parameter type mismatch")
        result = CampaignParameters(
            range_width=_decimal(root["range_width"], "range_width"),
            range_count=count,
            maximum_gap=_decimal(root["maximum_gap"], "maximum_gap"),
            endpoint_tolerance=_decimal(root["endpoint_tolerance"], "endpoint_tolerance"),
            binary_first_even=_decimal(root["binary_first_even"], "binary_first_even"),
            binary_last_even=_decimal(root["binary_last_even"], "binary_last_even"),
            proth_exponent=exponent,
            seed_prime=_decimal(root["seed_prime"], "seed_prime"),
            mode=mode,
        )
        result.validate()
        if _decimal(root["endpoint"], "endpoint") != result.endpoint:
            raise CampaignError("endpoint does not equal range_count * range_width")
        return result


def analytic_10pow27_parameters() -> CampaignParameters:
    """Return the immutable lowered finite campaign profile."""

    result = CampaignParameters(
        range_width=ANALYTIC_10POW27_RANGE_WIDTH,
        range_count=ANALYTIC_10POW27_RANGE_COUNT,
        maximum_gap=ANALYTIC_10POW27_MAXIMUM_GAP,
        endpoint_tolerance=ANALYTIC_10POW27_ENDPOINT_TOLERANCE,
        binary_first_even=ANALYTIC_10POW27_BINARY_FIRST_EVEN,
        binary_last_even=ANALYTIC_10POW27_BINARY_LAST_EVEN,
        proth_exponent=ANALYTIC_10POW27_PROTH_EXPONENT,
        seed_prime=3,
        mode=ANALYTIC_10POW27_MODE,
    )
    result.validate()
    return result


@dataclass(frozen=True)
class Rung:
    number: int
    certificate_kind: str
    witness: int | None = None
    certificate_sha256: str | None = None


def _prime_factor_proved(factor: object, depth: int) -> tuple[int, int, int]:
    if not isinstance(factor, dict) or set(factor) not in (
        {"exponent", "prime", "witness"},
        {"certificate", "exponent", "prime", "witness"},
    ):
        raise CampaignError("invalid Pocklington factor entry")
    prime = _decimal(factor["prime"], "factor.prime")
    exponent = factor["exponent"]
    witness = _decimal(factor["witness"], "factor.witness")
    if not _plain_int(exponent) or exponent <= 0:
        raise CampaignError("factor exponent must be positive")
    if prime <= (1 << 64) - 1:
        if "certificate" in factor or not is_prime_bounded(prime):
            raise CampaignError("invalid directly checked Pocklington factor")
    else:
        if "certificate" not in factor:
            raise CampaignError("large factor lacks recursive certificate")
        if not check_pocklington_object(factor["certificate"], expected=prime, depth=depth + 1):
            raise CampaignError("recursive Pocklington certificate failed")
    return prime, exponent, witness


def check_pocklington_object(root: object, *, expected: int | None = None, depth: int = 0) -> bool:
    """Check a recursive Pocklington certificate with exact integer arithmetic."""

    try:
        if depth > 32 or not isinstance(root, dict):
            return False
        if set(root) != {"cofactor", "factors", "kind", "number"}:
            return False
        if root["kind"] != POCKLINGTON_KIND or not isinstance(root["factors"], list):
            return False
        number = _decimal(root["number"], "number")
        cofactor = _decimal(root["cofactor"], "cofactor")
        if expected is not None and number != expected:
            return False
        if number <= (1 << 64) - 1:
            return False  # small primes belong in a direct rung/factor leaf
        if number <= 2 or number % 2 == 0 or cofactor <= 0:
            return False
        known = 1
        previous = 1
        checked: list[tuple[int, int, int]] = []
        for factor in root["factors"]:
            prime, exponent, witness = _prime_factor_proved(factor, depth)
            if prime <= previous:
                return False
            previous = prime
            known *= prime**exponent
            checked.append((prime, exponent, witness))
        if not checked or known * cofactor != number - 1 or known * known <= number:
            return False
        for prime, _exponent, witness in checked:
            if not 1 < witness < number:
                return False
            if pow(witness, number - 1, number) != 1:
                return False
            if math.gcd(pow(witness, (number - 1) // prime, number) - 1, number) != 1:
                return False
        return True
    except (CampaignError, OverflowError, ValueError):
        return False


def check_pocklington_file(path: Path, number: int, digest: str) -> bool:
    try:
        if sha256_file(path) != digest:
            return False
        return check_pocklington_object(_read_canonical_json(path), expected=number)
    except (CampaignError, OSError):
        return False


def _probable_prime_filter(number: int) -> bool:
    """One-sided composite filter; acceptance is always by Pocklington later."""

    if number < 2 or number % 2 == 0:
        return number == 2
    for prime in SOURCE_PROTH_WITNESSES + (31, 37, 41, 43, 47):
        if number == prime:
            return True
        if number % prime == 0:
            return False
    odd_part = number - 1
    shift = 0
    while odd_part % 2 == 0:
        odd_part //= 2
        shift += 1
    for base in (2, 3, 5, 7, 11, 13, 17):
        residue = pow(base, odd_part, number)
        if residue in (1, number - 1):
            continue
        for _ in range(shift - 1):
            residue = residue * residue % number
            if residue == number - 1:
                break
        else:
            return False
    return True


def _next_u64_prime(start: int) -> int:
    candidate = max(2, start)
    if candidate == 2:
        return 2
    candidate |= 1
    while candidate <= (1 << 64) - 1:
        if is_prime_bounded(candidate):
            return candidate
        candidate += 2
    raise CampaignError("Pocklington grid factor exceeded the 64-bit proof domain")


def _pocklington_witness(number: int, factor: int, search_limit: int) -> int | None:
    for witness in range(2, min(number, search_limit + 2)):
        if pow(witness, number - 1, number) != 1:
            continue
        if math.gcd(pow(witness, (number - 1) // factor, number) - 1, number) == 1:
            return witness
    return None


def find_general_pocklington(
    lower_exclusive: int,
    upper_exclusive: int,
    *,
    known_power: int = 20,
    witness_search_limit: int = 10_000,
    factor_prime_attempts: int = 0,
) -> tuple[Rung, dict[str, object]]:
    """Construct a checked general-form prime on a dense Pocklington grid.

    Set ``F = 2^known_power * r`` with a directly proved 64-bit prime ``r``
    and ``F^2 > upper_exclusive``.  Candidates ``N = j F + 1`` therefore have
    enough known factorization of ``N-1`` for Pocklington's theorem.  Miller--
    Rabin is only a rejection filter: this function returns solely after the
    exact built-in certificate checker accepts the result.

    ``factor_prime_attempts=0`` means no producer-side attempt cap.  A caller
    may retain the external ECPP plugin as a liveness fallback; it is never
    needed for the soundness of an accepted Pocklington result.
    """

    if (
        not all(_plain_int(value) for value in (lower_exclusive, upper_exclusive,
                                                known_power, witness_search_limit,
                                                factor_prime_attempts))
        or lower_exclusive < 2
        or upper_exclusive <= lower_exclusive + 1
        or known_power < 1
        or witness_search_limit < 1
        or factor_prime_attempts < 0
    ):
        raise CampaignError("invalid general Pocklington search parameters")
    power = 1 << known_power
    root = math.isqrt(upper_exclusive)
    r = _next_u64_prime(root // power + 1)
    attempts = 0
    while factor_prime_attempts == 0 or attempts < factor_prime_attempts:
        known = power * r
        if known * known <= upper_exclusive:
            r = _next_u64_prime(r + 1)
            continue
        minimum_j = (lower_exclusive - 1) // known + 1
        maximum_j = (upper_exclusive - 2) // known
        for cofactor in range(maximum_j, minimum_j - 1, -1):
            number = cofactor * known + 1
            if number <= (1 << 64) - 1:
                if is_prime_bounded(number):
                    return Rung(number, "direct64"), {}
                continue
            if not _probable_prime_filter(number):
                continue
            witness_two = _pocklington_witness(number, 2, witness_search_limit)
            if witness_two is None:
                continue
            witness_r = _pocklington_witness(number, r, witness_search_limit)
            if witness_r is None:
                continue
            certificate: dict[str, object] = {
                "cofactor": str(cofactor),
                "factors": [
                    {"exponent": known_power, "prime": "2", "witness": str(witness_two)},
                    {"exponent": 1, "prime": str(r), "witness": str(witness_r)},
                ],
                "kind": POCKLINGTON_KIND,
                "number": str(number),
            }
            if check_pocklington_object(certificate, expected=number):
                raw = canonical_json_bytes(certificate)
                digest = hashlib.sha256(raw).hexdigest()
                return Rung(number, "pocklington", certificate_sha256=digest), certificate
        attempts += 1
        r = _next_u64_prime(r + 1)
    raise CampaignError("bounded Pocklington-grid search found no certified prime")


def check_proth(number: int, witness: int, proth_exponent: int) -> bool:
    """Check ``number = k*2^proth_exponent+1`` by Proth's theorem.

    The exponent is part of the surrounding campaign manifest.  Keeping it an
    explicit checker input prevents an ``n=45`` record from being reported as
    historical ``n=52`` evidence.
    """

    if (
        not _plain_int(number)
        or not _plain_int(witness)
        or not _plain_int(proth_exponent)
        or not 1 <= proth_exponent <= 63
    ):
        return False
    if witness not in SOURCE_PROTH_WITNESSES or number <= 2:
        return False
    proth_power = 1 << proth_exponent
    quotient, remainder = divmod(number - 1, proth_power)
    if remainder or quotient <= 0 or quotient >= proth_power:
        return False
    # The source does not require k odd.  Proth's theorem applies after moving
    # all factors of two from k into the exponent; its inequality is preserved.
    if jacobi_symbol(witness, number) != -1:
        return False
    return pow(witness, (number - 1) // 2, number) == number - 1


def check_source_proth(number: int, witness: int) -> bool:
    """Backward-compatible checker for the paper's fixed-``n=52`` records."""

    return check_proth(number, witness, PROTH_EXPONENT)


def find_proth(
    lower_exclusive: int, upper_exclusive: int, proth_exponent: int
) -> Rung | None:
    """Find the largest accepted fixed-exponent Proth prime in one step."""

    if not _plain_int(proth_exponent) or not 1 <= proth_exponent <= 63:
        raise CampaignError("Proth exponent must lie in [1,63]")
    if upper_exclusive <= lower_exclusive + 1:
        return None
    proth_power = 1 << proth_exponent
    k = (upper_exclusive - 2) // proth_power
    k0 = (lower_exclusive - 1) // proth_power
    while k > k0 and k > 0:
        number = k * proth_power + 1
        for witness in SOURCE_PROTH_WITNESSES:
            if jacobi_symbol(witness, number) == -1:
                if pow(witness, (number - 1) // 2, number) == number - 1:
                    kind = "proth52" if proth_exponent == PROTH_EXPONENT else "proth"
                    return Rung(number, kind, witness=witness)
                break
        k -= 1
    return None


def find_source_proth(lower_exclusive: int, upper_exclusive: int) -> Rung | None:
    """Find the largest source-form Proth prime in one ladder step.

    This exact Python implementation is a correctness/reference producer.  A
    production implementation may replace its search, but range replay still
    checks the returned witness here.
    """

    return find_proth(lower_exclusive, upper_exclusive, PROTH_EXPONENT)


def _encode_rung(stream: BinaryIO, rung: Rung, previous: int) -> None:
    if not _plain_int(rung.number) or rung.number < previous:
        raise CampaignError("rungs must be nondecreasing from the header base")
    tags = {"direct64": TAG_DIRECT64, "proth52": TAG_PROTH52,
            "proth": TAG_PROTH,
            "pocklington": TAG_POCKLINGTON, "external": TAG_EXTERNAL}
    try:
        tag = tags[rung.certificate_kind]
    except KeyError as exc:
        raise CampaignError("unsupported rung certificate kind") from exc
    stream.write(bytes((tag,)))
    _write_varint(stream, rung.number - previous)
    if tag in (TAG_PROTH52, TAG_PROTH):
        if rung.witness is None:
            raise CampaignError("Proth rung lacks witness")
        _write_varint(stream, rung.witness)
    elif tag in (TAG_POCKLINGTON, TAG_EXTERNAL):
        digest = _hex_digest(rung.certificate_sha256, "certificate_sha256")
        stream.write(bytes.fromhex(digest))


def _decode_rung(stream: BinaryIO, previous: int) -> Rung:
    raw_tag = stream.read(1)
    if len(raw_tag) != 1:
        raise CampaignError("truncated rung tag")
    tag = raw_tag[0]
    number = previous + _read_varint(stream)
    if tag == TAG_DIRECT64:
        return Rung(number, "direct64")
    if tag == TAG_PROTH52:
        return Rung(number, "proth52", witness=_read_varint(stream))
    if tag == TAG_PROTH:
        return Rung(number, "proth", witness=_read_varint(stream))
    if tag in (TAG_POCKLINGTON, TAG_EXTERNAL):
        digest = stream.read(32)
        if len(digest) != 32:
            raise CampaignError("truncated certificate digest")
        return Rung(number, "pocklington" if tag == TAG_POCKLINGTON else "external",
                    certificate_sha256=digest.hex())
    raise CampaignError("unknown rung tag")


def range_filename(index: int) -> str:
    return f"range-{index:06d}.tggl"


def write_range_file(
    path: Path,
    *,
    parameters: CampaignParameters,
    index: int,
    previous_range_sha256: str,
    rungs: Iterable[Rung],
) -> str:
    """Atomically write one compact, streaming ladder range."""

    parameters.validate()
    if not 0 <= index < parameters.range_count:
        raise CampaignError("range index outside campaign")
    _hex_digest(previous_range_sha256, "previous_range_sha256")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, spool_name = tempfile.mkstemp(prefix=".rungs.", dir=path.parent)
    count = 0
    first: Rung | None = None
    last_number = 0
    try:
        with os.fdopen(fd, "wb") as spool:
            for rung in rungs:
                if first is None:
                    first = rung
                    last_number = rung.number
                    _encode_rung(spool, rung, rung.number)
                else:
                    if rung.number <= last_number:
                        raise CampaignError("range rungs are not strictly increasing")
                    _encode_rung(spool, rung, last_number)
                    last_number = rung.number
                count += 1
            spool.flush()
            os.fsync(spool.fileno())
        if first is None:
            raise CampaignError("range must contain at least one rung")
        left = index * parameters.range_width
        right = (index + 1) * parameters.range_width
        header = {
            "atom_id": campaign_atom_id(parameters),
            "base_prime": str(first.number),
            "index": index,
            "kind": RANGE_KIND,
            "left": str(left),
            "parameters_sha256": hashlib.sha256(canonical_json_bytes(parameters.to_json())).hexdigest(),
            "previous_range_sha256": previous_range_sha256,
            "record_count": count,
            "right": str(right),
            "schema": SCHEMA,
        }
        header_bytes = canonical_json_bytes(header)
        if len(header_bytes) > MAX_HEADER_BYTES:
            raise CampaignError("range header is oversized")
        final_fd, final_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(final_fd, "wb") as output, open(spool_name, "rb") as spool:
                output.write(MAGIC)
                _write_varint(output, len(header_bytes))
                output.write(header_bytes)
                shutil.copyfileobj(spool, output, 1 << 20)
                output.flush()
                os.fsync(output.fileno())
            os.replace(final_name, path)
        except BaseException:
            try:
                os.unlink(final_name)
            except FileNotFoundError:
                pass
            raise
        return sha256_file(path)
    finally:
        try:
            os.unlink(spool_name)
        except FileNotFoundError:
            pass


def _run_external_prime_checker(
    checker: Path, certificate: Path, rung: Rung
) -> None:
    checker_hash = sha256_file(checker)
    completed = subprocess.run(
        [str(checker), "--number", str(rung.number), "--certificate", str(certificate),
         "--certificate-sha256", rung.certificate_sha256 or ""],
        check=False, capture_output=True, timeout=3600,
    )
    if completed.returncode != 0 or completed.stderr:
        raise CampaignError("external general-prime checker failed")
    try:
        result = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError("external general-prime checker returned invalid JSON") from exc
    expected = {
        "certificate_sha256": rung.certificate_sha256,
        "checker_sha256": checker_hash,
        "kind": GENERAL_RESULT_KIND,
        "number": str(rung.number),
        "prime": True,
    }
    if completed.stdout != canonical_json_bytes(result) or result != expected:
        raise CampaignError("external general-prime result is not exactly bound")


def check_rung(
    rung: Rung,
    artifact_directory: Path,
    external_prime_checker: Path | None,
    *,
    proth_exponent: int = PROTH_EXPONENT,
) -> None:
    if rung.certificate_kind == "direct64":
        if not is_prime_bounded(rung.number):
            raise CampaignError("direct rung is not a checked 64-bit prime")
    elif rung.certificate_kind == "proth52":
        if (
            proth_exponent != PROTH_EXPONENT
            or rung.witness is None
            or not check_source_proth(rung.number, rung.witness)
        ):
            raise CampaignError("Proth certificate failed")
    elif rung.certificate_kind == "proth":
        if (
            proth_exponent == PROTH_EXPONENT
            or rung.witness is None
            or not check_proth(rung.number, rung.witness, proth_exponent)
        ):
            raise CampaignError("parameterized Proth certificate failed")
    elif rung.certificate_kind in ("pocklington", "external"):
        digest = _hex_digest(rung.certificate_sha256, "certificate_sha256")
        certificate = artifact_directory / digest
        if not certificate.is_file() or sha256_file(certificate) != digest:
            raise CampaignError("general-prime certificate artifact is absent or changed")
        if rung.certificate_kind == "pocklington":
            if not check_pocklington_file(certificate, rung.number, digest):
                raise CampaignError("Pocklington certificate failed")
        else:
            if external_prime_checker is None:
                raise CampaignError("external prime rung requires --general-prime-checker")
            _run_external_prime_checker(external_prime_checker, certificate, rung)
    else:
        raise CampaignError("unknown rung certificate kind")


@dataclass(frozen=True)
class VerifiedRange:
    index: int
    sha256: str
    first: Rung
    last: Rung
    record_count: int
    covered_through: int
    maximum_observed_gap: int
    evidence_counts: tuple[tuple[str, int], ...]
    general_certificate_sha256s: tuple[str, ...]


def verify_range_file(
    path: Path,
    *,
    parameters: CampaignParameters,
    expected_index: int,
    expected_previous_sha256: str,
    artifact_directory: Path,
    external_prime_checker: Path | None = None,
) -> VerifiedRange:
    """Replay every rung and every exact spacing condition in one range."""

    parameter_hash = hashlib.sha256(canonical_json_bytes(parameters.to_json())).hexdigest()
    with path.open("rb") as stream:
        if stream.read(len(MAGIC)) != MAGIC:
            raise CampaignError("bad range magic")
        header_length = _read_varint(stream)
        if header_length > MAX_HEADER_BYTES:
            raise CampaignError("oversized range header")
        header_bytes = stream.read(header_length)
        try:
            header = json.loads(header_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError("invalid range header") from exc
        if header_bytes != canonical_json_bytes(header):
            raise CampaignError("non-canonical range header")
        if not isinstance(header, dict):
            raise CampaignError("range header is not an object")
        expected_keys = {"atom_id", "base_prime", "index", "kind", "left",
                         "parameters_sha256", "previous_range_sha256", "record_count",
                         "right", "schema"}
        if set(header) != expected_keys:
            raise CampaignError("range header field set mismatch")
        if (
            header["kind"] != RANGE_KIND
            or header["schema"] != SCHEMA
            or header["atom_id"] != campaign_atom_id(parameters)
        ):
            raise CampaignError("range identity mismatch")
        if header["index"] != expected_index or header["previous_range_sha256"] != expected_previous_sha256:
            raise CampaignError("range order or hash chain mismatch")
        if header["parameters_sha256"] != parameter_hash:
            raise CampaignError("range parameter hash mismatch")
        left = expected_index * parameters.range_width
        right = (expected_index + 1) * parameters.range_width
        if _decimal(header["left"], "left") != left or _decimal(header["right"], "right") != right:
            raise CampaignError("range schedule mismatch")
        count = header["record_count"]
        if not _plain_int(count) or count <= 0:
            raise CampaignError("invalid record count")
        base = _decimal(header["base_prime"], "base_prime")
        first_rung: Rung | None = None
        last_rung: Rung | None = None
        covered_through = 0
        maximum_observed_gap = 0
        evidence_counts = {
            "direct64": 0,
            "external": 0,
            "pocklington": 0,
            "proth": 0,
            "proth52": 0,
        }
        general_certificates: set[str] = set()
        previous = base
        for ordinal in range(count):
            rung = _decode_rung(stream, previous)
            if ordinal == 0:
                if rung.number != base:
                    raise CampaignError("first rung does not equal header base")
            elif rung.number <= previous:
                raise CampaignError("rungs are not strictly increasing")
            check_rung(
                rung,
                artifact_directory,
                external_prime_checker,
                proth_exponent=parameters.proth_exponent,
            )
            evidence_counts[rung.certificate_kind] += 1
            if rung.certificate_sha256 is not None:
                general_certificates.add(rung.certificate_sha256)
            if ordinal and rung.number - previous > parameters.maximum_gap:
                raise CampaignError("ladder gap exceeds the source bound")
            if ordinal:
                maximum_observed_gap = max(
                    maximum_observed_gap, rung.number - previous
                )
            start = rung.number + parameters.binary_first_even
            if ordinal and start > covered_through + 2:
                raise CampaignError("range ladder leaves an uncovered odd target")
            covered_through = max(
                covered_through, rung.number + parameters.binary_last_even
            )
            if first_rung is None:
                first_rung = rung
            last_rung = rung
            previous = rung.number
        if stream.read(1):
            raise CampaignError("trailing range bytes")
    if first_rung is None or last_rung is None:
        raise CampaignError("range unexpectedly has no rungs")
    if abs(first_rung.number - left) > parameters.endpoint_tolerance:
        raise CampaignError("first rung is outside source endpoint tolerance")
    if abs(last_rung.number - right) > parameters.endpoint_tolerance:
        raise CampaignError("last rung is outside source endpoint tolerance")
    return VerifiedRange(
        expected_index, sha256_file(path), first_rung, last_rung, count,
        covered_through, maximum_observed_gap,
        tuple(sorted(evidence_counts.items())),
        tuple(sorted(general_certificates)),
    )


def manifest_for(parameters: CampaignParameters) -> dict[str, object]:
    return {
        "atom_id": campaign_atom_id(parameters),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "kind": "tg_goldbach_ladder_manifest_v1",
        "parameters": parameters.to_json(),
        "primality_source_sha256": sha256_file(
            Path(__file__).resolve().with_name("goldbach.py")
        ),
        "primary_source": "https://arxiv.org/abs/1305.3062v2",
        "schema": SCHEMA,
    }


def initialize_campaign(directory: Path, parameters: CampaignParameters = CampaignParameters()) -> None:
    parameters.validate()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ranges").mkdir(exist_ok=True)
    (directory / "certificates").mkdir(exist_ok=True)
    # The source-shaped campaign has no predecessor dependency between ranges.
    # Keep it in separate directories so legacy serial-chain artifacts can
    # never be mistaken for independently produced range receipts.
    (directory / "independent-ranges").mkdir(exist_ok=True)
    (directory / "independent-receipts").mkdir(exist_ok=True)
    manifest = directory / "manifest.json"
    value = manifest_for(parameters)
    if manifest.exists():
        if _read_canonical_json(manifest) != value:
            raise CampaignError("existing campaign manifest differs")
    else:
        _atomic_bytes(manifest, canonical_json_bytes(value))


def load_campaign(directory: Path) -> CampaignParameters:
    root = _read_canonical_json(directory / "manifest.json")
    if not isinstance(root, dict) or root.get("kind") != "tg_goldbach_ladder_manifest_v1":
        raise CampaignError("wrong campaign manifest kind")
    if set(root) != {
        "atom_id",
        "implementation_sha256",
        "kind",
        "parameters",
        "primality_source_sha256",
        "primary_source",
        "schema",
    }:
        raise CampaignError("manifest field set mismatch")
    parameters = CampaignParameters.from_json(root["parameters"])
    if root["atom_id"] != campaign_atom_id(parameters) or root["schema"] != SCHEMA:
        raise CampaignError("manifest identity mismatch")
    if root["primary_source"] != "https://arxiv.org/abs/1305.3062v2":
        raise CampaignError("primary source locator mismatch")
    if root != manifest_for(parameters):
        raise CampaignError("campaign implementation source identity changed")
    return parameters


@dataclass(frozen=True)
class ReplayState:
    parameters: CampaignParameters
    completed_ranges: int
    previous_sha256: str
    last_rung: Rung
    total_records: int
    covered_through: int


def replay_campaign(
    directory: Path, *, external_prime_checker: Path | None = None
) -> ReplayState:
    """Recheck all contiguous files from the immutable root; ignore checkpoints."""

    parameters = load_campaign(directory)
    previous_hash = ZERO_HASH
    previous_rung: Rung | None = None
    total = 0
    covered = parameters.seed_prime + parameters.maximum_gap
    completed = 0
    for index in range(parameters.range_count):
        path = directory / "ranges" / range_filename(index)
        if not path.exists():
            break
        result = verify_range_file(
            path, parameters=parameters, expected_index=index,
            expected_previous_sha256=previous_hash,
            artifact_directory=directory / "certificates",
            external_prime_checker=external_prime_checker,
        )
        if previous_rung is None:
            if result.first.number != parameters.seed_prime:
                raise CampaignError("campaign does not start at the seed prime")
        elif result.first != previous_rung:
            raise CampaignError("adjacent ranges do not duplicate the boundary rung")
        if result.first.number + parameters.binary_first_even > covered + 2:
            raise CampaignError("prime ladder leaves an uncovered odd target")
        covered = max(covered, result.covered_through)
        previous_rung = result.last
        previous_hash = result.sha256
        total += result.record_count if completed == 0 else result.record_count - 1
        completed += 1
    if previous_rung is None:
        previous_rung = Rung(parameters.seed_prime, "direct64")
        total = 1
        covered = parameters.seed_prime + parameters.binary_last_even
    # Any later file after the first gap is a fork/truncation, not resumable state.
    for index in range(completed + 1, parameters.range_count):
        if (directory / "ranges" / range_filename(index)).exists():
            raise CampaignError("non-contiguous range files")
    return ReplayState(parameters, completed, previous_hash, previous_rung, total, covered)


def advance_replay_state(
    directory: Path,
    state: ReplayState,
    *,
    external_prime_checker: Path | None = None,
) -> ReplayState:
    """Verify the single file immediately after an already replayed prefix."""

    index = state.completed_ranges
    if index >= state.parameters.range_count:
        raise CampaignError("campaign is already complete")
    result = verify_range_file(
        directory / "ranges" / range_filename(index),
        parameters=state.parameters,
        expected_index=index,
        expected_previous_sha256=state.previous_sha256,
        artifact_directory=directory / "certificates",
        external_prime_checker=external_prime_checker,
    )
    if result.first != state.last_rung:
        raise CampaignError("new range does not duplicate the boundary rung")
    covered = state.covered_through
    if result.first.number + state.parameters.binary_first_even > covered + 2:
        raise CampaignError("prime ladder leaves an uncovered odd target")
    covered = max(covered, result.covered_through)
    return ReplayState(
        state.parameters,
        index + 1,
        result.sha256,
        result.last,
        state.total_records + result.record_count - 1,
        covered,
    )


def import_certificate(directory: Path, source: Path) -> str:
    digest = sha256_file(source)
    destination = directory / "certificates" / digest
    if not destination.exists():
        _atomic_bytes(destination, source.read_bytes())
    elif sha256_file(destination) != digest:
        raise CampaignError("certificate store collision")
    return digest


def independent_range_filename(index: int) -> str:
    return f"range-{index:06d}.tggl"


def independent_receipt_filename(index: int) -> str:
    return f"receipt-{index:06d}.json"


def _campaign_constant_record(parameters: CampaignParameters) -> dict[str, object]:
    """Exact manifest constants repeated in every auditable receipt.

    The legacy JSON field containing this object is still named
    ``source_constants`` for byte-level compatibility with historical n=52
    receipts.  Its values always come from the validated campaign profile.
    """

    return {
        "binary_first_even": str(parameters.binary_first_even),
        "binary_last_even": str(parameters.binary_last_even),
        "endpoint": str(parameters.endpoint),
        "endpoint_tolerance": str(parameters.endpoint_tolerance),
        "maximum_gap": str(parameters.maximum_gap),
        "proth_exponent": parameters.proth_exponent,
        "proth_witnesses": list(SOURCE_PROTH_WITNESSES),
        "range_count": parameters.range_count,
        "range_width": str(parameters.range_width),
        "seed_prime": str(parameters.seed_prime),
        "sieve_bound_exclusive": SOURCE_SIEVE_BOUND,
    }


def _domain_hash(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + canonical_json_bytes(value)).hexdigest()


def _rung_json(rung: Rung) -> dict[str, object]:
    result: dict[str, object] = {
        "certificate_kind": rung.certificate_kind,
        "number": str(rung.number),
    }
    if rung.witness is not None:
        result["witness"] = rung.witness
    if rung.certificate_sha256 is not None:
        result["certificate_sha256"] = rung.certificate_sha256
    return result


def _write_immutable_json(path: Path, value: object) -> str:
    raw = canonical_json_bytes(value)
    lock = path.with_name(f".{path.name}.lock")
    try:
        with advisory_lock(lock):
            if path.exists():
                if path.read_bytes() != raw:
                    raise CampaignError(
                        f"immutable receipt already exists with different bytes: {path}"
                    )
            else:
                _atomic_bytes(path, raw)
    except CampaignIOError as exc:
        raise CampaignError(str(exc)) from exc
    return hashlib.sha256(raw).hexdigest()


def _install_immutable_range(temporary: Path, destination: Path) -> str:
    """Install a large range atomically without loading it into memory."""

    digest = sha256_file(temporary)
    lock = destination.with_name(f".{destination.name}.lock")
    try:
        with advisory_lock(lock):
            if destination.exists():
                if sha256_file(destination) != digest:
                    raise CampaignError(
                        f"immutable range already exists with different bytes: {destination}"
                    )
                temporary.unlink()
            else:
                os.replace(temporary, destination)
    except CampaignIOError as exc:
        raise CampaignError(str(exc)) from exc
    return digest


def _independent_receipt_core(
    directory: Path, parameters: CampaignParameters, result: VerifiedRange
) -> dict[str, object]:
    left = result.index * parameters.range_width
    right = (result.index + 1) * parameters.range_width
    counts = dict(result.evidence_counts)
    return {
        "atom_id": campaign_atom_id(parameters),
        "classification": parameters.mode,
        "coverage": {
            "first_odd": str(result.first.number + parameters.binary_first_even),
            "last_odd": str(result.covered_through),
        },
        "endpoint_tolerance": str(parameters.endpoint_tolerance),
        "evidence": {
            "direct64_count": counts["direct64"],
            "external_count": counts["external"],
            "general_prime_certificate_sha256s": list(
                result.general_certificate_sha256s
            ),
            "pocklington_count": counts["pocklington"],
            **(
                {"proth52_count": counts["proth52"]}
                if parameters.proth_exponent == PROTH_EXPONENT
                else {"proth_count": counts["proth"]}
            ),
        },
        "execution_attested": False,
        "first_rung": _rung_json(result.first),
        "index": result.index,
        "kind": INDEPENDENT_RECEIPT_KIND,
        "last_rung": _rung_json(result.last),
        "lean_atom_discharged": False,
        "left": str(left),
        "manifest_sha256": sha256_file(directory / "manifest.json"),
        "maximum_gap": str(parameters.maximum_gap),
        "maximum_observed_gap": str(result.maximum_observed_gap),
        "parameters_sha256": hashlib.sha256(
            canonical_json_bytes(parameters.to_json())
        ).hexdigest(),
        "range_file": independent_range_filename(result.index),
        "range_file_sha256": result.sha256,
        "record_count": result.record_count,
        "right": str(right),
        "schema": INDEPENDENT_SCHEMA,
        "source_constants": _campaign_constant_record(parameters),
    }


def verify_independent_range(
    directory: Path,
    index: int,
    *,
    external_prime_checker: Path | None = None,
) -> tuple[VerifiedRange, dict[str, object]]:
    """Replay one range without reading or trusting any other range."""

    parameters = load_campaign(directory)
    if not _plain_int(index) or not 0 <= index < parameters.range_count:
        raise CampaignError("independent range index outside campaign")
    result = verify_range_file(
        directory / "independent-ranges" / independent_range_filename(index),
        parameters=parameters,
        expected_index=index,
        # An all-zero predecessor is an explicit assertion that this range is
        # independently scheduled, not the tip of the legacy serial chain.
        expected_previous_sha256=ZERO_HASH,
        artifact_directory=directory / "certificates",
        external_prime_checker=external_prime_checker,
    )
    core = _independent_receipt_core(directory, parameters, result)
    receipt = dict(core)
    receipt["receipt_sha256"] = _domain_hash(_RANGE_RECEIPT_DOMAIN, core)
    return result, receipt


def emit_independent_receipt(
    directory: Path,
    index: int,
    *,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Replay one independent range and immutably retain its exact receipt."""

    _result, receipt = verify_independent_range(
        directory, index, external_prime_checker=external_prime_checker
    )
    _write_immutable_json(
        directory / "independent-receipts" / independent_receipt_filename(index),
        receipt,
    )
    return receipt


def _largest_direct_prime(lower_exclusive: int, upper_exclusive: int) -> Rung | None:
    if upper_exclusive <= lower_exclusive + 1:
        return None
    candidate = upper_exclusive - 1
    if candidate == 2 and lower_exclusive < 2:
        return Rung(2, "direct64")
    candidate |= 1
    if candidate >= upper_exclusive:
        candidate -= 2
    while candidate > lower_exclusive:
        if candidate <= (1 << 64) - 1 and is_prime_bounded(candidate):
            return Rung(candidate, "direct64")
        candidate -= 2
    return None


def _store_builtin_pocklington(
    directory: Path, rung: Rung, certificate: Mapping[str, object]
) -> None:
    raw = canonical_json_bytes(certificate)
    digest = hashlib.sha256(raw).hexdigest()
    if rung.certificate_sha256 != digest:
        raise CampaignError("generated Pocklington digest mismatch")
    destination = directory / "certificates" / digest
    if destination.exists():
        if destination.read_bytes() != raw:
            raise CampaignError("content-addressed certificate collision")
    else:
        _atomic_bytes(destination, raw)


def _produce_certified_prime(
    directory: Path,
    parameters: CampaignParameters,
    lower_exclusive: int,
    upper_exclusive: int,
    *,
    general_prime_producer: Path | None,
    external_prime_checker: Path | None,
    builtin_pocklington: bool,
) -> Rung:
    candidate = find_proth(
        lower_exclusive, upper_exclusive, parameters.proth_exponent
    )
    if candidate is not None:
        return candidate
    # Tiny bounded fixtures cannot contain n=52 Proth numbers.  Directly
    # checked 64-bit leaves give the same exact proof contract without ever
    # entering a production full_source range.
    if parameters.mode == "bounded_test" and upper_exclusive <= (1 << 64):
        direct = _largest_direct_prime(lower_exclusive, upper_exclusive)
        if direct is not None:
            return direct
    if builtin_pocklington:
        try:
            candidate, certificate = find_general_pocklington(
                lower_exclusive, upper_exclusive, factor_prime_attempts=256
            )
        except CampaignError:
            candidate = None
        else:
            _store_builtin_pocklington(directory, candidate, certificate)
            check_rung(
                candidate,
                directory / "certificates",
                external_prime_checker,
                proth_exponent=parameters.proth_exponent,
            )
            return candidate
    if general_prime_producer is None:
        raise CampaignError(
            "no source-form Proth prime was found; production needs "
            "--builtin-pocklington or --general-prime-producer"
        )
    return request_general_prime(
        general_prime_producer,
        directory=directory,
        lower_exclusive=lower_exclusive,
        upper_exclusive=upper_exclusive,
        external_prime_checker=external_prime_checker,
    )


def _produce_boundary_rung(
    directory: Path,
    parameters: CampaignParameters,
    boundary_index: int,
    *,
    general_prime_producer: Path | None,
    external_prime_checker: Path | None,
    builtin_pocklington: bool,
) -> Rung:
    if boundary_index == 0:
        return Rung(parameters.seed_prime, "direct64")
    nominal = boundary_index * parameters.range_width
    lower = max(1, nominal - parameters.endpoint_tolerance - 1)
    upper = nominal + parameters.endpoint_tolerance + 1
    return _produce_certified_prime(
        directory,
        parameters,
        lower,
        upper,
        general_prime_producer=general_prime_producer,
        external_prime_checker=external_prime_checker,
        builtin_pocklington=builtin_pocklington,
    )


def produce_independent_range(
    directory: Path,
    index: int,
    *,
    general_prime_producer: Path | None = None,
    external_prime_checker: Path | None = None,
    builtin_pocklington: bool = True,
) -> dict[str, object]:
    """Produce and immediately replay one formulaically fixed source range.

    No predecessor file is read.  This is the worker entry point intended for
    a 492,700-element array job.
    """

    parameters = load_campaign(directory)
    if not _plain_int(index) or not 0 <= index < parameters.range_count:
        raise CampaignError("independent range index outside campaign")
    destination = (
        directory / "independent-ranges" / independent_range_filename(index)
    )
    if destination.exists():
        return emit_independent_receipt(
            directory, index, external_prime_checker=external_prime_checker
        )
    first = _produce_boundary_rung(
        directory,
        parameters,
        index,
        general_prime_producer=general_prime_producer,
        external_prime_checker=external_prime_checker,
        builtin_pocklington=builtin_pocklington,
    )
    last = _produce_boundary_rung(
        directory,
        parameters,
        index + 1,
        general_prime_producer=general_prime_producer,
        external_prime_checker=external_prime_checker,
        builtin_pocklington=builtin_pocklington,
    )
    if last.number <= first.number:
        raise CampaignError("formulaic boundary primes are not increasing")

    def rungs() -> Iterator[Rung]:
        current = first
        yield current
        # The exact covered intervals are [p+first_even,p+last_even].  Merely
        # meeting the paper's nominal prime-gap ceiling can leave one odd
        # integer between intervals at equality, so production uses the
        # strongest formula that makes interval adjacency automatic.
        coverage_step = (
            parameters.binary_last_even - parameters.binary_first_even + 2
        )
        while last.number - current.number > coverage_step:
            candidate = _produce_certified_prime(
                directory,
                parameters,
                current.number,
                current.number + coverage_step + 1,
                general_prime_producer=general_prime_producer,
                external_prime_checker=external_prime_checker,
                builtin_pocklington=builtin_pocklington,
            )
            if not current.number < candidate.number <= current.number + coverage_step:
                raise CampaignError("range producer did not advance within the gap bound")
            if candidate.number >= last.number:
                raise CampaignError("interior producer crossed the fixed right boundary")
            current = candidate
            yield current
        yield last

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.worker.", dir=destination.parent
    )
    os.close(temporary_fd)
    os.unlink(temporary_name)
    temporary = Path(temporary_name)
    try:
        write_range_file(
            temporary,
            parameters=parameters,
            index=index,
            previous_range_sha256=ZERO_HASH,
            rungs=rungs(),
        )
        _install_immutable_range(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return emit_independent_receipt(
        directory, index, external_prime_checker=external_prime_checker
    )


def independent_group_bounds(
    range_count: int, group_index: int, group_count: int
) -> tuple[int, int]:
    """Balanced deterministic half-open assignment for scheduler groups."""

    if (
        not all(_plain_int(value) for value in (range_count, group_index, group_count))
        or range_count <= 0
        or group_count <= 0
        or group_count > range_count
        or not 0 <= group_index < group_count
    ):
        raise CampaignError("invalid independent worker-group schedule")
    quotient, remainder = divmod(range_count, group_count)
    lower = group_index * quotient + min(group_index, remainder)
    upper = lower + quotient + (1 if group_index < remainder else 0)
    return lower, upper


def _independent_group_worker(arguments: tuple[object, ...]) -> dict[str, object]:
    (
        directory,
        index,
        general_prime_producer,
        external_prime_checker,
        builtin_pocklington,
    ) = arguments
    return produce_independent_range(
        Path(str(directory)),
        int(index),
        general_prime_producer=(
            None if general_prime_producer is None else Path(str(general_prime_producer))
        ),
        external_prime_checker=(
            None if external_prime_checker is None else Path(str(external_prime_checker))
        ),
        builtin_pocklington=bool(builtin_pocklington),
    )


def produce_independent_group(
    directory: Path,
    *,
    group_index: int,
    group_count: int,
    local_workers: int = 1,
    general_prime_producer: Path | None = None,
    external_prime_checker: Path | None = None,
    builtin_pocklington: bool = True,
    summary_path: Path | None = None,
) -> dict[str, object]:
    """Run one bounded local worker pool over a formulaic range-index group."""

    parameters = load_campaign(directory)
    lower, upper = independent_group_bounds(
        parameters.range_count, group_index, group_count
    )
    if not _plain_int(local_workers) or not 1 <= local_workers <= 256:
        raise CampaignError("local_workers must lie in [1,256]")
    arguments = [
        (
            str(directory),
            index,
            None if general_prime_producer is None else str(general_prime_producer),
            None if external_prime_checker is None else str(external_prime_checker),
            builtin_pocklington,
        )
        for index in range(lower, upper)
    ]
    by_index: dict[int, dict[str, object]] = {}
    if local_workers == 1:
        for argument in arguments:
            receipt = _independent_group_worker(argument)
            by_index[int(receipt["index"])] = receipt
    else:
        with ProcessPoolExecutor(max_workers=local_workers) as pool:
            futures = {
                pool.submit(_independent_group_worker, argument): int(argument[1])
                for argument in arguments
            }
            for future in as_completed(futures):
                receipt = future.result()
                by_index[int(receipt["index"])] = receipt
    expected = set(range(lower, upper))
    if set(by_index) != expected:
        raise CampaignError("worker group did not emit its exact formulaic index set")
    receipt_hashes = [str(by_index[index]["receipt_sha256"]) for index in range(lower, upper)]
    result: dict[str, object] = {
        "classification": parameters.mode,
        "first_range_index": lower,
        "group_count": group_count,
        "group_index": group_index,
        "kind": WORKER_GROUP_RESULT_KIND,
        "last_range_index": upper - 1,
        "local_workers": local_workers,
        "range_count": upper - lower,
        "range_receipt_sha256s": receipt_hashes,
        "schema": INDEPENDENT_SCHEMA,
    }
    if summary_path is not None:
        _write_immutable_json(summary_path, result)
    return result


def independent_receipt_paths(directory: Path) -> tuple[Path, ...]:
    receipt_directory = directory / "independent-receipts"
    if not receipt_directory.is_dir():
        raise CampaignError("independent receipt directory does not exist")
    indexed: dict[int, Path] = {}
    for path in receipt_directory.glob("receipt-*.json"):
        match = _RECEIPT_FILENAME_RE.fullmatch(path.name)
        if match is None:
            raise CampaignError(f"malformed independent receipt name: {path.name}")
        index = int(match.group(1))
        if index in indexed:
            raise CampaignError(f"duplicate independent receipt index {index}")
        indexed[index] = path
    return tuple(indexed[index] for index in sorted(indexed))


def load_independent_receipt(
    directory: Path,
    index: int,
    *,
    external_prime_checker: Path | None = None,
) -> tuple[VerifiedRange, dict[str, object]]:
    path = directory / "independent-receipts" / independent_receipt_filename(index)
    value = _read_canonical_json(path)
    result, expected = verify_independent_range(
        directory, index, external_prime_checker=external_prime_checker
    )
    if value != expected:
        raise CampaignError(f"range receipt {index} differs from exact replay")
    return result, expected


def _range_receipt_merkle_root(receipt_sha256s: Sequence[str]) -> str:
    if not receipt_sha256s:
        raise CampaignError("cannot commit an empty range receipt sequence")
    level = [
        hashlib.sha256(
            _RANGE_MERKLE_LEAF_DOMAIN
            + bytes.fromhex(_hex_digest(digest, "receipt_sha256"))
        ).digest()
        for digest in receipt_sha256s
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(
                hashlib.sha256(_RANGE_MERKLE_ODD_DOMAIN + level[-1]).digest()
            )
        level = [
            hashlib.sha256(
                _RANGE_MERKLE_NODE_DOMAIN + level[index] + level[index + 1]
            ).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def reduce_independent_campaign(
    directory: Path,
    *,
    aggregate_path: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Ordered, fail-closed reduction of all independently checked ranges."""

    parameters = load_campaign(directory)
    paths = independent_receipt_paths(directory)
    if len(paths) != parameters.range_count:
        raise CampaignError(
            "independent receipt set is incomplete: expected "
            f"{parameters.range_count}, found {len(paths)}"
        )
    expected_names = {
        independent_receipt_filename(index) for index in range(parameters.range_count)
    }
    actual_names = {path.name for path in paths}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        raise CampaignError(f"independent receipt indices have a gap: {missing[:8]}")

    receipt_hashes: list[str] = []
    covered_through = 0
    previous_last: Rung | None = None
    maximum_cross_range_gap = 0
    maximum_within_range_gap = 0
    total_records = 0
    total_general_certificates = 0
    for index in range(parameters.range_count):
        result, receipt = load_independent_receipt(
            directory, index, external_prime_checker=external_prime_checker
        )
        if index == 0:
            if result.first.number != parameters.seed_prime:
                raise CampaignError("first independent range does not start at seed prime")
        else:
            assert previous_last is not None
            forward_gap = max(0, result.first.number - previous_last.number)
            if forward_gap > parameters.maximum_gap:
                raise CampaignError("adjacent range endpoints exceed the ladder gap")
            maximum_cross_range_gap = max(maximum_cross_range_gap, forward_gap)
        first_covered = result.first.number + parameters.binary_first_even
        if index and first_covered > covered_through + 2:
            raise CampaignError("ordered range reduction leaves an uncovered odd target")
        covered_through = max(covered_through, result.covered_through)
        previous_last = result.last
        maximum_within_range_gap = max(
            maximum_within_range_gap, result.maximum_observed_gap
        )
        total_records += result.record_count
        total_general_certificates += len(result.general_certificate_sha256s)
        receipt_hashes.append(str(receipt["receipt_sha256"]))

    if previous_last is None:
        raise CampaignError("ordered range reduction is empty")
    last_odd = parameters.endpoint if parameters.endpoint % 2 else parameters.endpoint - 1
    if covered_through < last_odd:
        raise CampaignError("ordered ranges do not cover the configured endpoint")
    core: dict[str, object] = {
        "atom_id": campaign_atom_id(parameters),
        "binary_goldbach_prerequisite_satisfied": False,
        "classification": parameters.mode,
        "coverage": {
            "first_odd": str(parameters.seed_prime + parameters.binary_first_even),
            "last_odd": str(last_odd),
        },
        "execution_attested": False,
        "kind": INDEPENDENT_AGGREGATE_KIND,
        "lean_atom_discharged": False,
        "manifest_sha256": sha256_file(directory / "manifest.json"),
        "maximum_cross_range_forward_gap": str(maximum_cross_range_gap),
        "maximum_within_range_gap": str(maximum_within_range_gap),
        "parameters_sha256": hashlib.sha256(
            canonical_json_bytes(parameters.to_json())
        ).hexdigest(),
        "range_count": parameters.range_count,
        "range_receipt_merkle_root_sha256": _range_receipt_merkle_root(
            receipt_hashes
        ),
        "range_receipt_sha256s": receipt_hashes,
        "schema": INDEPENDENT_SCHEMA,
        "source_constants": _campaign_constant_record(parameters),
        "total_general_prime_certificates": total_general_certificates,
        "total_ladder_records": str(total_records),
        "verification_note": (
            "This aggregate proves only the independently replayed prime "
            "ladder. The separate binary-Goldbach computation is still required."
        ),
    }
    aggregate = dict(core)
    aggregate["aggregate_sha256"] = _domain_hash(_RANGE_AGGREGATE_DOMAIN, core)
    if aggregate_path is not None:
        _write_immutable_json(aggregate_path, aggregate)
    return aggregate


def validate_independent_aggregate(
    directory: Path,
    value: object,
    *,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    expected = reduce_independent_campaign(
        directory, external_prime_checker=external_prime_checker
    )
    if value != expected:
        raise CampaignError("ladder aggregate differs from exact ordered reduction")
    return expected


def _combine_with_binary_goldbach(
    directory: Path,
    *,
    ladder_aggregate_path: Path,
    binary_plan_path: Path,
    binary_receipts_directory: Path,
    binary_aggregate_path: Path,
    output_path: Path | None = None,
    external_prime_checker: Path | None = None,
    optimized_source: bool,
) -> dict[str, object]:
    """Replay two independent aggregates with one exact binary algorithm.

    The GoldbachGPU aggregate is deliberately validated first.  Its success is
    only the binary prerequisite; it is never accepted as evidence for even a
    single ladder prime.
    """

    from .campaign_io import load_json
    from .goldbach_gpu_campaign import (
        GoldbachGPUCampaignError,
        OPTIMIZED_PRODUCTION_ALGORITHM,
        PRODUCTION_ALGORITHM,
        load_plan as load_binary_plan,
        load_receipt as load_binary_receipt,
        make_optimized_production_plan,
        make_production_plan,
        receipt_paths as binary_receipt_paths,
        source_identity_for_algorithm,
        validate_aggregate as validate_binary_aggregate,
    )

    try:
        binary_plan = load_binary_plan(binary_plan_path)
        expected_binary_plan = (
            make_optimized_production_plan(
                executable_sha256=binary_plan.executable_sha256
            )
            if optimized_source
            else make_production_plan(
                executable_sha256=binary_plan.executable_sha256
            )
        )
        expected_algorithm = (
            OPTIMIZED_PRODUCTION_ALGORITHM
            if optimized_source
            else PRODUCTION_ALGORITHM
        )
        if (
            binary_plan != expected_binary_plan
            or binary_plan.algorithm != expected_algorithm
        ):
            raise CampaignError(
                "binary-Goldbach plan is not the exact "
                f"{'optimized' if optimized_source else 'hardened'} "
                "historical profile"
            )
        binary_receipts = [
            load_binary_receipt(path, plan=binary_plan)
            for path in binary_receipt_paths(binary_receipts_directory)
        ]
        binary_value = load_json(binary_aggregate_path, require_canonical=True)
        binary = validate_binary_aggregate(
            binary_value, plan=binary_plan, receipts=binary_receipts
        )
    except (GoldbachGPUCampaignError, CampaignIOError) as exc:
        profile = "optimized" if optimized_source else "hardened"
        raise CampaignError(
            f"{profile} binary-Goldbach aggregate failed: {exc}"
        ) from exc
    if (
        not binary_plan.production
        or not binary["production_campaign_complete"]
        or not binary["coverage_structurally_complete"]
        or binary["domain"]
        != {
            "even_start_inclusive": SOURCE_BINARY_FIRST_EVEN,
            "even_limit_inclusive": SOURCE_BINARY_LAST_EVEN,
            "even_count": (SOURCE_BINARY_LAST_EVEN - SOURCE_BINARY_FIRST_EVEN) // 2
            + 1,
        }
    ):
        raise CampaignError("binary-Goldbach aggregate is not the exact source domain")

    ladder_value = _read_canonical_json(ladder_aggregate_path)
    ladder = validate_independent_aggregate(
        directory,
        ladder_value,
        external_prime_checker=external_prime_checker,
    )
    parameters = load_campaign(directory)
    if parameters.mode != "full_source":
        raise CampaignError("bounded ladder aggregate cannot enter the source reduction")
    binary_record: dict[str, object] = {
        "aggregate_sha256": binary["aggregate_sha256"],
        "domain": binary["domain"],
        "receipt_merkle_root_sha256": binary[
            "receipt_merkle_root_sha256"
        ],
    }
    if optimized_source:
        # The v1 registered route is pinned to the hardened source.  The
        # optimized result therefore uses a different kind/hash domain and
        # explicitly retains its plan and source identities.
        binary_record.update(
            {
                "algorithm": binary_plan.algorithm,
                "plan_sha256": binary_plan.plan_sha256,
                "source_identity_sha256": (
                    source_identity_for_algorithm(binary_plan.algorithm)
                ),
            }
        )
    core: dict[str, object] = {
        "atom_id": ATOM_ID,
        "binary_goldbach": binary_record,
        "binary_receipt_proves_prime_ladder": False,
        "classification": (
            "full_source_optimized_external_computations_replayed_"
            "unattested_not_registered"
            if optimized_source
            else "full_source_external_computations_replayed"
        ),
        "coverage": {
            "first_odd": "7",
            "last_odd": str(SOURCE_ENDPOINT - 1),
        },
        "execution_attested": False,
        "independent_computations_replayed": [
            "binary_goldbach_through_4e18",
            "helfgott_platt_prime_ladder",
        ],
        "kind": (
            OPTIMIZED_COMBINED_GPU_RESULT_KIND
            if optimized_source
            else COMBINED_GPU_RESULT_KIND
        ),
        "lean_atom_discharged": False,
        "prime_ladder": {
            "aggregate_sha256": ladder["aggregate_sha256"],
            "range_receipt_merkle_root_sha256": ladder[
                "range_receipt_merkle_root_sha256"
            ],
            "range_count": ladder["range_count"],
        },
        "schema": INDEPENDENT_SCHEMA,
        "source_constants": _campaign_constant_record(parameters),
    }
    combined = dict(core)
    combined["combined_sha256"] = _domain_hash(
        (
            _OPTIMIZED_COMBINED_GPU_DOMAIN
            if optimized_source
            else _COMBINED_GPU_DOMAIN
        ),
        core,
    )
    if output_path is not None:
        _write_immutable_json(output_path, combined)
    return combined


def combine_with_hardened_binary_goldbach(
    directory: Path,
    *,
    ladder_aggregate_path: Path,
    binary_plan_path: Path,
    binary_receipts_directory: Path,
    binary_aggregate_path: Path,
    output_path: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Replay the exact registered-v1 hardened binary and ladder profiles."""

    return _combine_with_binary_goldbach(
        directory,
        ladder_aggregate_path=ladder_aggregate_path,
        binary_plan_path=binary_plan_path,
        binary_receipts_directory=binary_receipts_directory,
        binary_aggregate_path=binary_aggregate_path,
        output_path=output_path,
        external_prime_checker=external_prime_checker,
        optimized_source=False,
    )


def combine_with_optimized_binary_goldbach(
    directory: Path,
    *,
    ladder_aggregate_path: Path,
    binary_plan_path: Path,
    binary_receipts_directory: Path,
    binary_aggregate_path: Path,
    output_path: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Replay the exact optimized binary route and historical ladder.

    Its result is deliberately domain-separated from the registered-v1
    finalizer and cannot be substituted for that finalizer's input.
    """

    return _combine_with_binary_goldbach(
        directory,
        ladder_aggregate_path=ladder_aggregate_path,
        binary_plan_path=binary_plan_path,
        binary_receipts_directory=binary_receipts_directory,
        binary_aggregate_path=binary_aggregate_path,
        output_path=output_path,
        external_prime_checker=external_prime_checker,
        optimized_source=True,
    )


def benchmark_source_height(sample_steps: int = 5_000) -> dict[str, object]:
    """Benchmark a bounded prefix at the top source height.

    This deliberately does not write a receipt: it is performance evidence,
    never mathematical evidence for an omitted range suffix.
    """

    if not _plain_int(sample_steps) or sample_steps <= 0:
        raise CampaignError("benchmark sample_steps must be positive")
    current = SOURCE_ENDPOINT - SOURCE_RANGE_WIDTH
    rungs: list[Rung] = []
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    for ordinal in range(sample_steps):
        rung = find_source_proth(
            current, current + SOURCE_MAXIMUM_GAP - 1
        )
        if rung is None:
            raise CampaignError(
                f"source-height benchmark needs a general prime at step {ordinal}"
            )
        rungs.append(rung)
        current = rung.number
    producer_wall = time.perf_counter() - wall_start
    producer_cpu = time.process_time() - cpu_start
    replay_start = time.perf_counter()
    for rung in rungs:
        if rung.witness is None or not check_source_proth(rung.number, rung.witness):
            raise CampaignError("source-height benchmark replay failed")
    replay_wall = time.perf_counter() - replay_start
    combined_wall = producer_wall + replay_wall
    minimum_records = (
        SOURCE_RANGE_WIDTH + SOURCE_MAXIMUM_GAP - 1
    ) // SOURCE_MAXIMUM_GAP
    projected_range_seconds = minimum_records * combined_wall / sample_steps
    projected_total_core_hours = (
        projected_range_seconds * SOURCE_RANGE_COUNT / 3600
    )
    return {
        "benchmark_only_not_a_certificate": True,
        "combined_steps_per_second": f"{sample_steps / combined_wall:.6f}",
        "minimum_records_per_source_range": minimum_records,
        "producer_cpu_seconds": f"{producer_cpu:.6f}",
        "producer_wall_seconds": f"{producer_wall:.6f}",
        "projected_minimum_total_core_hours": f"{projected_total_core_hours:.3f}",
        "projected_seconds_per_source_range_at_sample_rate": (
            f"{projected_range_seconds:.3f}"
        ),
        "replay_wall_seconds": f"{replay_wall:.6f}",
        "sample_height_start": str(SOURCE_ENDPOINT - SOURCE_RANGE_WIDTH),
        "sample_steps": sample_steps,
        "schema": "tg_goldbach_ladder_source_height_benchmark_v1",
    }


def request_general_prime(
    producer: Path,
    *,
    directory: Path,
    lower_exclusive: int,
    upper_exclusive: int,
    external_prime_checker: Path | None,
) -> Rung:
    """Call the fixed general-prime producer protocol and validate its proof."""

    request = {
        "kind": GENERAL_REQUEST_KIND,
        "lower_exclusive": str(lower_exclusive),
        "upper_exclusive": str(upper_exclusive),
    }
    with tempfile.TemporaryDirectory(prefix="tg-general-prime-") as temporary:
        request_path = Path(temporary) / "request.json"
        output_path = Path(temporary) / "result.json"
        request_path.write_bytes(canonical_json_bytes(request))
        completed = subprocess.run(
            [str(producer), "--request", str(request_path), "--output", str(output_path)],
            check=False, capture_output=True, timeout=24 * 3600,
        )
        if completed.returncode != 0 or completed.stdout or completed.stderr:
            raise CampaignError("general-prime producer failed or wrote console output")
        result = _read_canonical_json(output_path)
        if not isinstance(result, dict) or set(result) != {"certificate_kind", "certificate_path", "kind", "number"}:
            raise CampaignError("general-prime producer result field mismatch")
        if result["kind"] != GENERAL_RESULT_KIND or result["certificate_kind"] not in ("pocklington", "external"):
            raise CampaignError("unsupported general-prime producer result")
        number = _decimal(result["number"], "number")
        if not lower_exclusive < number < upper_exclusive:
            raise CampaignError("general-prime result is outside requested interval")
        certificate_path = Path(result["certificate_path"])
        if not certificate_path.is_absolute() or not certificate_path.is_file():
            raise CampaignError("producer certificate_path must name an existing absolute file")
        digest = import_certificate(directory, certificate_path)
        rung = Rung(number, result["certificate_kind"], certificate_sha256=digest)
        check_rung(rung, directory / "certificates", external_prime_checker)
        return rung


def produce_next_range(
    directory: Path,
    *,
    state: ReplayState,
    general_prime_producer: Path | None,
    external_prime_checker: Path | None,
    builtin_pocklington: bool = False,
) -> str:
    """Produce one source-scheduled range, streaming its selected rungs."""

    index = state.completed_ranges
    if index >= state.parameters.range_count:
        raise CampaignError("campaign is already complete")
    right = (index + 1) * state.parameters.range_width
    target = right - state.parameters.endpoint_tolerance

    def selected() -> Iterator[Rung]:
        current = state.last_rung
        yield current
        while current.number < target:
            upper = current.number + state.parameters.maximum_gap
            candidate = find_proth(
                current.number, upper, state.parameters.proth_exponent
            )
            if candidate is None:
                if builtin_pocklington:
                    try:
                        candidate, certificate = find_general_pocklington(
                            current.number, upper, factor_prime_attempts=256
                        )
                    except CampaignError:
                        if general_prime_producer is None:
                            raise CampaignError(
                                "bounded built-in Pocklington search found no rung; "
                                "resume with --general-prime-producer for a liveness fallback"
                            ) from None
                        candidate = request_general_prime(
                            general_prime_producer, directory=directory,
                            lower_exclusive=current.number, upper_exclusive=upper,
                            external_prime_checker=external_prime_checker,
                        )
                    else:
                        if candidate.certificate_kind == "pocklington":
                            raw = canonical_json_bytes(certificate)
                            digest = hashlib.sha256(raw).hexdigest()
                            if digest != candidate.certificate_sha256:
                                raise CampaignError("generated Pocklington digest mismatch")
                            _atomic_bytes(directory / "certificates" / digest, raw)
                            check_rung(
                                candidate, directory / "certificates",
                                external_prime_checker,
                                proth_exponent=state.parameters.proth_exponent,
                            )
                elif general_prime_producer is None:
                    raise CampaignError(
                        "no source-form Proth prime in this step; a validated "
                        "--builtin-pocklington or --general-prime-producer is required"
                    )
                else:
                    candidate = request_general_prime(
                        general_prime_producer, directory=directory,
                        lower_exclusive=current.number, upper_exclusive=upper,
                        external_prime_checker=external_prime_checker,
                    )
            if not current.number < candidate.number < upper:
                raise CampaignError("producer did not advance within the ladder bound")
            current = candidate
            yield current

    destination = directory / "ranges" / range_filename(index)
    return write_range_file(
        destination, parameters=state.parameters, index=index,
        previous_range_sha256=state.previous_sha256, rungs=selected(),
    )


def check_binary_prerequisite(checker: Path, artifact: Path) -> dict[str, object]:
    """Replay, rather than merely cite, the external binary-Goldbach boundary."""

    artifact_hash = sha256_file(artifact)
    checker_hash = sha256_file(checker)
    request = {
        "artifact_sha256": artifact_hash,
        "every_even": True,
        "first_even": str(SOURCE_BINARY_FIRST_EVEN),
        "kind": BINARY_REQUEST_KIND,
        "last_even": str(SOURCE_BINARY_LAST_EVEN),
    }
    with tempfile.TemporaryDirectory(prefix="tg-binary-goldbach-") as temporary:
        request_path = Path(temporary) / "request.json"
        request_path.write_bytes(canonical_json_bytes(request))
        completed = subprocess.run(
            [str(checker), "--request", str(request_path), "--artifact", str(artifact)],
            check=False, capture_output=True, timeout=7 * 24 * 3600,
        )
    if completed.returncode != 0 or completed.stderr:
        raise CampaignError("binary-Goldbach prerequisite checker failed")
    try:
        result = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError("binary-Goldbach checker returned invalid JSON") from exc
    expected = {
        "artifact_sha256": artifact_hash,
        "checker_sha256": checker_hash,
        "every_even": True,
        "first_even": str(SOURCE_BINARY_FIRST_EVEN),
        "kind": BINARY_RESULT_KIND,
        "last_even": str(SOURCE_BINARY_LAST_EVEN),
        "verified": True,
    }
    if completed.stdout != canonical_json_bytes(result) or result != expected:
        raise CampaignError("binary-Goldbach result is not exactly bound to the claim")
    return result


def verify_complete_campaign(
    directory: Path,
    *,
    binary_checker: Path | None = None,
    binary_artifact: Path | None = None,
    binary_campaign: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Return a full receipt only after both independent computations replay."""

    state = replay_campaign(directory, external_prime_checker=external_prime_checker)
    if state.parameters.mode != "full_source":
        raise CampaignError("bounded-test campaigns can never produce a full receipt")
    if state.completed_ranges != SOURCE_RANGE_COUNT:
        raise CampaignError("prime-ladder campaign is incomplete")
    last_odd = SOURCE_ENDPOINT if SOURCE_ENDPOINT % 2 else SOURCE_ENDPOINT - 1
    if state.covered_through < last_odd:
        raise CampaignError("ladder does not cover the source theorem endpoint")
    if binary_campaign is not None:
        if binary_checker is not None or binary_artifact is not None:
            raise CampaignError("choose either in-repo binary campaign or external replay")
        from .binary_goldbach_campaign import (  # local import avoids a cycle
            BinaryGoldbachError,
            verify_complete as verify_binary_campaign,
        )
        try:
            binary = verify_binary_campaign(binary_campaign)
        except BinaryGoldbachError as exc:
            raise CampaignError(f"binary-Goldbach campaign failed: {exc}") from exc
    else:
        if binary_checker is None or binary_artifact is None:
            raise CampaignError(
                "verification requires --binary-campaign or both external binary inputs"
            )
        binary = check_binary_prerequisite(binary_checker, binary_artifact)
    receipt = {
        "atom_id": ATOM_ID,
        "binary_goldbach": binary,
        "coverage": {"first_odd": "7", "last_odd": str(last_odd)},
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "kind": RECEIPT_KIND,
        "last_range_sha256": state.previous_sha256,
        "lean_atom_discharged": False,
        "manifest_sha256": sha256_file(directory / "manifest.json"),
        "primality_source_sha256": sha256_file(
            Path(__file__).resolve().with_name("goldbach.py")
        ),
        "range_count": state.completed_ranges,
        "schema": SCHEMA,
        "total_unique_ladder_rungs": str(state.total_records),
        "verification_class": "full_source_external_computation_replayed",
    }
    _atomic_bytes(directory / "receipt.json", canonical_json_bytes(receipt))
    return receipt


__all__ = (
    "ANALYTIC_10POW27_ATOM_ID", "ANALYTIC_10POW27_BINARY_LAST_EVEN",
    "ANALYTIC_10POW27_ENDPOINT",
    "ANALYTIC_10POW27_ENDPOINT_TOLERANCE", "ANALYTIC_10POW27_MAXIMUM_GAP",
    "ANALYTIC_10POW27_MODE", "ANALYTIC_10POW27_PROTH_EXPONENT",
    "ANALYTIC_10POW27_RANGE_COUNT", "ANALYTIC_10POW27_RANGE_WIDTH",
    "ANALYTIC_10POW27_TARGET", "ATOM_ID", "CampaignError",
    "CampaignParameters", "ReplayState", "Rung", "campaign_atom_id",
    "SOURCE_ENDPOINT", "SOURCE_MAXIMUM_GAP", "SOURCE_RANGE_COUNT",
    "SOURCE_RANGE_WIDTH", "advance_replay_state", "analytic_10pow27_parameters",
    "benchmark_source_height", "check_binary_prerequisite",
    "check_pocklington_object", "check_proth", "check_source_proth",
    "combine_with_hardened_binary_goldbach",
    "combine_with_optimized_binary_goldbach", "emit_independent_receipt",
    "find_general_pocklington", "find_proth", "find_source_proth",
    "independent_range_filename",
    "independent_group_bounds", "independent_receipt_filename",
    "independent_receipt_paths",
    "initialize_campaign", "load_campaign", "load_independent_receipt",
    "produce_independent_group", "produce_independent_range",
    "produce_next_range", "range_filename",
    "reduce_independent_campaign", "replay_campaign",
    "validate_independent_aggregate", "verify_complete_campaign",
    "verify_independent_range", "verify_range_file", "write_range_file",
)
