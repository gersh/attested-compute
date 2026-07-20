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
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import BinaryIO, Iterable, Iterator, Mapping, Sequence

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

MAGIC = b"TGGLRNG1"
TAG_DIRECT64 = 0
TAG_PROTH52 = 1
TAG_POCKLINGTON = 2
TAG_EXTERNAL = 3
ZERO_HASH = "0" * 64
MAX_HEADER_BYTES = 1 << 20
MAX_VARINT_BYTES = 32


class CampaignError(RuntimeError):
    """A malformed, incomplete, or unsupported campaign."""


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
        if self.mode not in ("full_source", "bounded_test"):
            raise CampaignError("unknown campaign mode")
        if self.mode == "full_source" and self != CampaignParameters():
            raise CampaignError("full_source parameters must equal the paper constants")

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


def check_source_proth(number: int, witness: int) -> bool:
    """Check the paper's fixed-``n=52`` Proth representation exactly."""

    if not _plain_int(number) or not _plain_int(witness):
        return False
    if witness not in SOURCE_PROTH_WITNESSES or number <= 2:
        return False
    quotient, remainder = divmod(number - 1, PROTH_POWER)
    if remainder or quotient <= 0 or quotient >= PROTH_POWER:
        return False
    # The source does not require k odd.  Proth's theorem applies after moving
    # all factors of two from k into the exponent; its inequality is preserved.
    if jacobi_symbol(witness, number) != -1:
        return False
    return pow(witness, (number - 1) // 2, number) == number - 1


def find_source_proth(lower_exclusive: int, upper_exclusive: int) -> Rung | None:
    """Find the largest source-form Proth prime in one ladder step.

    This exact Python implementation is a correctness/reference producer.  A
    production implementation may replace its search, but range replay still
    checks the returned witness here.
    """

    if upper_exclusive <= lower_exclusive + 1:
        return None
    k = (upper_exclusive - 2) // PROTH_POWER
    k0 = (lower_exclusive - 1) // PROTH_POWER
    while k > k0 and k > 0:
        number = k * PROTH_POWER + 1
        for witness in SOURCE_PROTH_WITNESSES:
            if jacobi_symbol(witness, number) == -1:
                if pow(witness, (number - 1) // 2, number) == number - 1:
                    return Rung(number, "proth52", witness=witness)
                break
        k -= 1
    return None


def _encode_rung(stream: BinaryIO, rung: Rung, previous: int) -> None:
    if not _plain_int(rung.number) or rung.number < previous:
        raise CampaignError("rungs must be nondecreasing from the header base")
    tags = {"direct64": TAG_DIRECT64, "proth52": TAG_PROTH52,
            "pocklington": TAG_POCKLINGTON, "external": TAG_EXTERNAL}
    try:
        tag = tags[rung.certificate_kind]
    except KeyError as exc:
        raise CampaignError("unsupported rung certificate kind") from exc
    stream.write(bytes((tag,)))
    _write_varint(stream, rung.number - previous)
    if tag == TAG_PROTH52:
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
            "atom_id": ATOM_ID,
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
    rung: Rung, artifact_directory: Path, external_prime_checker: Path | None
) -> None:
    if rung.certificate_kind == "direct64":
        if not is_prime_bounded(rung.number):
            raise CampaignError("direct rung is not a checked 64-bit prime")
    elif rung.certificate_kind == "proth52":
        if rung.witness is None or not check_source_proth(rung.number, rung.witness):
            raise CampaignError("Proth certificate failed")
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
        if header["kind"] != RANGE_KIND or header["schema"] != SCHEMA or header["atom_id"] != ATOM_ID:
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
        previous = base
        for ordinal in range(count):
            rung = _decode_rung(stream, previous)
            if ordinal == 0:
                if rung.number != base:
                    raise CampaignError("first rung does not equal header base")
            elif rung.number <= previous:
                raise CampaignError("rungs are not strictly increasing")
            check_rung(rung, artifact_directory, external_prime_checker)
            if ordinal and rung.number - previous > parameters.maximum_gap:
                raise CampaignError("ladder gap exceeds the source bound")
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
        covered_through,
    )


def manifest_for(parameters: CampaignParameters) -> dict[str, object]:
    return {
        "atom_id": ATOM_ID,
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
    if root["atom_id"] != ATOM_ID or root["schema"] != SCHEMA:
        raise CampaignError("manifest identity mismatch")
    if root["primary_source"] != "https://arxiv.org/abs/1305.3062v2":
        raise CampaignError("primary source locator mismatch")
    parameters = CampaignParameters.from_json(root["parameters"])
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
            candidate = find_source_proth(current.number, upper)
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
    "ATOM_ID", "CampaignError", "CampaignParameters", "ReplayState", "Rung",
    "SOURCE_ENDPOINT", "SOURCE_MAXIMUM_GAP", "SOURCE_RANGE_COUNT",
    "SOURCE_RANGE_WIDTH", "advance_replay_state", "check_binary_prerequisite", "check_pocklington_object",
    "check_source_proth", "find_source_proth", "initialize_campaign",
    "find_general_pocklington", "load_campaign", "produce_next_range", "range_filename", "replay_campaign",
    "verify_complete_campaign", "verify_range_file", "write_range_file",
)
