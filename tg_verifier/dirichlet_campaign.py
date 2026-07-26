# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable source-range scheduler for Platt's Dirichlet-GRH computation.

The module owns the finite, exact part of the computation: primitive-character
enumeration, the parity-dependent source heights, compact chunk scheduling,
hash-linked resume, and artifact replay.  The analytic zero isolation and
Turing/argument-principle proof are deliberately behind a pinned executable
protocol.  A successful receipt is therefore an *external checker assertion*,
not a Lean proof and not an in-repository implementation of Turing's method.

The paper-computation profile has one immutable domain: every primitive
Dirichlet character of conductor ``2 <= q <= 400000``.  It contains exactly
the paper's 29,565,923,837 L-functions.  Platt treats ``q = 1`` separately as
Riemann zeta; covering the literal Lean quantifier at ``q = 1`` is therefore a
separate zeta-campaign prerequisite.  Moduli congruent to two modulo four
correctly contribute no primitive characters.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable, NoReturn, Sequence


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
LEAN_NAME = (
    "MathExtras.Helfgott.MajorArcsStart."
    "platt_theorem_7_1_dirichlet_verification_source"
)
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
SOURCE_MIN_Q = 2
SOURCE_MAX_Q = 400_000
FULL_SOURCE_CHARACTER_COUNT = 29_565_923_837

CHARACTER_ALGORITHM = "primitive-dirichlet-character-crt-unrank-v1"
HEIGHT_ALGORITHM = "platt-theorem-7.1-parity-height-exact-rational-v1"
CAMPAIGN_ALGORITHM = "platt-dirichlet-theorem-7.1-external-campaign-v1"
SCHEDULE_ENCODING = "q:primitive_count:height_numerator:height_denominator\\n-v1"

PLAN_SCHEMA = "sparkinterval.tg.dirichlet_campaign.plan.v1"
REQUEST_SCHEMA = "sparkinterval.tg.dirichlet_campaign.request.v1"
RESULT_SCHEMA = "sparkinterval.tg.dirichlet_campaign.external_result.v1"
CHECKER_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_campaign.external_checker_receipt.v2"
)
CHUNK_SCHEMA = "sparkinterval.tg.dirichlet_campaign.chunk.v1"
FINAL_SCHEMA = "sparkinterval.tg.dirichlet_campaign.final.v1"

PRODUCER_PROTOCOL = "sparkinterval.dirichlet-grh-producer.v1"
CHECKER_PROTOCOL = "sparkinterval.dirichlet-grh-checker.v1"
ZERO_SHA256 = "0" * 64
PLAN_NAME = "campaign.json"
FINAL_NAME = "final.json"
CHUNK_PREFIX = "chunk-"
CHUNK_DIGITS = 8
MAX_CONTROL_BYTES = 32 * 1024 * 1024


class DirichletCampaignError(RuntimeError):
    """A campaign configuration, external result, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCampaignError(message)


def canonical_json_bytes(value: object) -> bytes:
    """Canonical ASCII JSON used for every control-file commitment."""

    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
                size += len(block)
    except OSError as error:
        raise DirichletCampaignError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest(), size


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON constant is forbidden: {value}")


def _reject_float(value: str) -> NoReturn:
    _fail(f"JSON floating-point values are forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_canonical_json(path: Path, *, max_bytes: int = MAX_CONTROL_BYTES) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DirichletCampaignError(f"cannot read {path}: {error}") from error
    if len(raw) > max_bytes:
        _fail(f"control file exceeds {max_bytes} bytes: {path}")
    try:
        value = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletCampaignError(f"invalid JSON in {path}: {error}") from error
    if canonical_json_bytes(value) != raw:
        _fail(f"JSON is not in canonical encoding: {path}")
    return value


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _integer(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str):
        _fail(f"{name} must be a string")
    return value


def _boolean(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        _fail(f"{name} must be Boolean")
    return value


def _digest(name: str, value: object) -> str:
    value = _text(name, value)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _expect_keys(name: str, value: object, expected: Iterable[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    expected_set = set(expected)
    actual = set(value)
    if actual != expected_set:
        _fail(
            f"{name} keys differ: missing={sorted(expected_set - actual)}, "
            f"extra={sorted(actual - expected_set)}"
        )
    return value


def _fraction_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _smallest_prime_factors(limit: int) -> list[int]:
    spf = list(range(limit + 1))
    if limit >= 1:
        spf[1] = 1
    for prime in range(2, int(limit**0.5) + 1):
        if spf[prime] != prime:
            continue
        for multiple in range(prime * prime, limit + 1, prime):
            if spf[multiple] == multiple:
                spf[multiple] = prime
    return spf


def factor_prime_powers(q: int, spf: Sequence[int] | None = None) -> tuple[tuple[int, int], ...]:
    """Return the exact prime-power factorization in increasing-prime order."""

    _integer("q", q, minimum=1)
    if q == 1:
        return ()
    if spf is None:
        spf = _smallest_prime_factors(q)
    if len(spf) <= q:
        _fail("smallest-prime-factor table does not cover q")
    remainder = q
    result: list[tuple[int, int]] = []
    while remainder > 1:
        prime = spf[remainder]
        exponent = 0
        while remainder % prime == 0:
            remainder //= prime
            exponent += 1
        result.append((prime, exponent))
    return tuple(result)


def local_primitive_character_count(prime: int, exponent: int) -> int:
    """Number of characters with conductor exactly ``prime**exponent``."""

    _integer("prime", prime, minimum=2)
    _integer("exponent", exponent, minimum=1)
    if prime == 2:
        if exponent == 1:
            return 0
        if exponent == 2:
            return 1
        return 1 << (exponent - 2)
    if exponent == 1:
        return prime - 2
    return prime ** (exponent - 2) * (prime - 1) ** 2


def primitive_character_count(q: int, spf: Sequence[int] | None = None) -> int:
    """Number of primitive complex Dirichlet characters of conductor ``q``."""

    if q == 1:
        return 1
    count = 1
    for prime, exponent in factor_prime_powers(q, spf):
        count *= local_primitive_character_count(prime, exponent)
    return count


def source_height(q: int) -> Fraction:
    """The exact parity-sensitive height in Platt, Theorem 7.1."""

    _integer("q", q, minimum=1)
    additive = 75_000_000 if q % 2 == 0 else 37_500_000
    numerator = max(100_000_000, 200 * q + additive)
    return Fraction(numerator, q)


def _least_primitive_root(
    modulus: int, prime: int, spf: Sequence[int] | None = None
) -> int:
    """Return the least primitive root of an odd prime power."""

    order = modulus - modulus // prime
    prime_divisors = [p for p, _ in factor_prime_powers(order, spf)]
    for candidate in range(2, modulus):
        if all(pow(candidate, order // divisor, modulus) != 1 for divisor in prime_divisors):
            return candidate
    _fail(f"no primitive root found modulo {modulus}")


def _local_model(
    prime: int, exponent: int, spf: Sequence[int] | None = None
) -> dict[str, Any]:
    modulus = prime**exponent
    if prime != 2:
        order = prime ** (exponent - 1) * (prime - 1)
        condition = "1<=k<=p-2" if exponent == 1 else "0<=k<order and p does not divide k"
        return {
            "prime": prime,
            "exponent": exponent,
            "modulus": modulus,
            "group_model": "cyclic_primitive_root",
            "generators": [_least_primitive_root(modulus, prime, spf)],
            "orders": [order],
            "primitive_exponent_condition": condition,
            "primitive_count": local_primitive_character_count(prime, exponent),
        }
    if exponent == 1:
        return {
            "prime": 2,
            "exponent": 1,
            "modulus": 2,
            "group_model": "trivial",
            "generators": [],
            "orders": [],
            "primitive_exponent_condition": "none",
            "primitive_count": 0,
        }
    if exponent == 2:
        return {
            "prime": 2,
            "exponent": 2,
            "modulus": 4,
            "group_model": "cyclic_generator_3",
            "generators": [3],
            "orders": [2],
            "primitive_exponent_condition": "k=1",
            "primitive_count": 1,
        }
    return {
        "prime": 2,
        "exponent": exponent,
        "modulus": modulus,
        "group_model": "sign_generator_minus_one_times_cyclic_generator_5",
        "generators": [modulus - 1, 5],
        "orders": [2, 1 << (exponent - 2)],
        "primitive_exponent_condition": "a in {0,1} and b odd",
        "primitive_count": 1 << (exponent - 2),
    }


def _unrank_local(prime: int, exponent: int, ordinal: int) -> tuple[int, ...]:
    count = local_primitive_character_count(prime, exponent)
    if not 0 <= ordinal < count:
        _fail("local primitive-character ordinal is out of range")
    if prime != 2:
        if exponent == 1:
            return (ordinal + 1,)
        # Ascending values in [0, phi(p^e)) not divisible by p.
        block, offset = divmod(ordinal, prime - 1)
        return (block * prime + offset + 1,)
    if exponent == 2:
        return (1,)
    per_sign = 1 << (exponent - 3)
    sign_exponent, cyclic_ordinal = divmod(ordinal, per_sign)
    return (sign_exponent, 2 * cyclic_ordinal + 1)


def _crt_pair(value: int, modulus: int, residue: int, local_modulus: int) -> tuple[int, int]:
    """Combine two coprime congruences with exact integer arithmetic."""

    step = ((residue - value) * pow(modulus, -1, local_modulus)) % local_modulus
    combined_modulus = modulus * local_modulus
    return (value + modulus * step) % combined_modulus, combined_modulus


def primitive_character_descriptor(
    q: int, ordinal: int, spf: Sequence[int] | None = None
) -> dict[str, Any]:
    """Unrank one canonical primitive character without a residue table."""

    if spf is None:
        spf = _smallest_prime_factors(q)
    count = primitive_character_count(q, spf)
    _integer("ordinal", ordinal, minimum=0)
    if ordinal >= count:
        _fail(f"character ordinal {ordinal} is outside [0,{count}) for q={q}")
    if q == 1:
        return {
            "q": 1,
            "ordinal": 0,
            "character_model": "unique_primitive_character_modulus_one",
            "local_exponents": [],
            "conrey_number": 1,
            "parity": 0,
        }

    factors = factor_prime_powers(q, spf)
    radices = [local_primitive_character_count(p, e) for p, e in factors]
    local_ordinals = [0] * len(radices)
    remainder = ordinal
    for index in range(len(radices) - 1, -1, -1):
        remainder, local_ordinals[index] = divmod(remainder, radices[index])
    if remainder:
        _fail("mixed-radix character unranking failed")

    local_exponents: list[dict[str, Any]] = []
    parity = 0
    conrey_number = 0
    conrey_modulus = 1
    for (prime, exponent), local_ordinal in zip(factors, local_ordinals):
        exponents = _unrank_local(prime, exponent, local_ordinal)
        local_modulus = prime**exponent
        if prime == 2:
            parity ^= exponents[0]
            if exponent == 2:
                local_number = pow(3, exponents[0], local_modulus)
            else:
                local_number = (
                    pow(local_modulus - 1, exponents[0], local_modulus)
                    * pow(5, exponents[1], local_modulus)
                ) % local_modulus
        else:
            parity ^= exponents[0] & 1
            generator = _least_primitive_root(local_modulus, prime, spf)
            local_number = pow(generator, exponents[0], local_modulus)
        conrey_number, conrey_modulus = _crt_pair(
            conrey_number, conrey_modulus, local_number, local_modulus
        )
        local_exponents.append(
            {
                "prime": prime,
                "exponent": exponent,
                "ordinal": local_ordinal,
                "exponents": list(exponents),
            }
        )
    return {
        "q": q,
        "ordinal": ordinal,
        "character_model": CHARACTER_ALGORITHM,
        "local_exponents": local_exponents,
        "conrey_number": conrey_number,
        "parity": parity,
    }


@dataclass(frozen=True)
class ScheduleIndex:
    q_start: int
    q_stop: int
    counts: tuple[int, ...]
    prefix: tuple[int, ...]
    total_characters: int
    nonzero_moduli: int
    schedule_sha256: str
    spf: tuple[int, ...]

    @classmethod
    def build(cls, q_start: int, q_stop: int) -> "ScheduleIndex":
        _integer("q_start", q_start, minimum=1)
        _integer("q_stop", q_stop, minimum=q_start)
        if q_stop > SOURCE_MAX_Q:
            _fail(f"q_stop exceeds the source endpoint {SOURCE_MAX_Q}")
        spf = _smallest_prime_factors(q_stop)
        counts: list[int] = []
        prefix = [0]
        digest = hashlib.sha256()
        nonzero = 0
        for q in range(q_start, q_stop + 1):
            count = primitive_character_count(q, spf)
            height = source_height(q)
            counts.append(count)
            prefix.append(prefix[-1] + count)
            nonzero += int(count != 0)
            digest.update(
                f"{q}:{count}:{height.numerator}:{height.denominator}\n".encode(
                    "ascii"
                )
            )
        result = cls(
            q_start=q_start,
            q_stop=q_stop,
            counts=tuple(counts),
            prefix=tuple(prefix),
            total_characters=prefix[-1],
            nonzero_moduli=nonzero,
            schedule_sha256=digest.hexdigest(),
            spf=tuple(spf),
        )
        if q_start == SOURCE_MIN_Q and q_stop == SOURCE_MAX_Q:
            if result.total_characters != FULL_SOURCE_CHARACTER_COUNT:
                _fail("full-source primitive-character count invariant failed")
        return result

    def segments(self, cursor: int, count: int) -> list[dict[str, Any]]:
        _integer("cursor", cursor, minimum=0)
        _integer("count", count, minimum=1)
        if cursor + count > self.total_characters:
            _fail("requested compact task range exceeds the schedule")
        result: list[dict[str, Any]] = []
        stop_cursor = cursor + count
        while cursor < stop_cursor:
            index = bisect_right(self.prefix, cursor) - 1
            if index < 0 or index >= len(self.counts):
                _fail("cannot locate schedule cursor")
            q = self.q_start + index
            local_start = cursor - self.prefix[index]
            take = min(stop_cursor - cursor, self.counts[index] - local_start)
            if take <= 0:
                _fail("schedule cursor landed in an empty modulus")
            height = source_height(q)
            factors = factor_prime_powers(q, self.spf)
            result.append(
                {
                    "q": q,
                    "modulus_parity": "even" if q % 2 == 0 else "odd",
                    "character_ordinal_start": local_start,
                    "character_ordinal_stop": local_start + take,
                    "primitive_character_count_for_q": self.counts[index],
                    "absolute_height": _fraction_json(height),
                    "closed_symmetric_ordinate_range": {
                        "lower": _fraction_json(-height),
                        "upper": _fraction_json(height),
                    },
                    "local_models": [_local_model(p, e, self.spf) for p, e in factors],
                }
            )
            cursor += take
        return result


def make_request(
    plan: dict[str, Any], schedule: ScheduleIndex, ordinal: int, cursor: int
) -> dict[str, Any]:
    remaining = schedule.total_characters - cursor
    if remaining <= 0:
        _fail("campaign is already complete")
    task_count = min(plan["characters_per_chunk"], remaining)
    segments = schedule.segments(cursor, task_count)
    compact_hash = sha256_bytes(canonical_json_bytes(segments))
    return {
        "kind": REQUEST_SCHEMA,
        "schema_version": 1,
        "atom_id": ATOM_ID,
        "campaign_algorithm": CAMPAIGN_ALGORITHM,
        "character_algorithm": CHARACTER_ALGORITHM,
        "height_algorithm": HEIGHT_ALGORITHM,
        "plan_sha256": plan["plan_sha256"],
        "chunk_ordinal": ordinal,
        "global_character_start": cursor,
        "global_character_stop": cursor + task_count,
        "character_count": task_count,
        "segment_count": len(segments),
        "compact_task_set_sha256": compact_hash,
        "segments": segments,
        "analytic_obligation": {
            "critical_strip": {"real_lower": "0", "real_upper": "1"},
            "height_endpoint": "closed_absolute_value",
            "zero_counting": "multiplicity_preserving",
            "conclusion": "every_nontrivial_zero_has_real_part_one_half",
        },
    }


def _copy_executable(source: Path, destination: Path) -> tuple[str, int]:
    source = source.resolve()
    try:
        mode = source.stat().st_mode
    except OSError as error:
        raise DirichletCampaignError(f"cannot stat executable {source}: {error}") from error
    if not stat.S_ISREG(mode) or not os.access(source, os.X_OK):
        _fail(f"backend must be an executable regular file: {source}")
    shutil.copy2(source, destination)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR)
    return sha256_file(destination)


def _protocol_version(executable: Path, expected: str) -> None:
    command = [str(executable), "protocol-version"]
    try:
        with executable.open("rb") as source:
            first_line = source.readline(256)
    except OSError as error:
        raise DirichletCampaignError(f"cannot inspect backend {executable}: {error}") from error
    if first_line.startswith(b"#!") and b"python" in first_line.lower():
        command.insert(0, sys.executable)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DirichletCampaignError(
            f"cannot query backend protocol for {executable}: {error}"
        ) from error
    if completed.returncode != 0 or completed.stdout != (expected + "\n").encode("ascii"):
        _fail(
            f"{executable} does not implement {expected}; "
            f"exit={completed.returncode}, stdout={completed.stdout!r}"
        )


def _plan_body(
    *,
    mode: str,
    q_start: int,
    q_stop: int,
    characters_per_chunk: int,
    schedule: ScheduleIndex,
    producer_sha256: str,
    producer_size: int,
    checker_sha256: str,
    checker_size: int,
    implementation_sha256: str,
) -> dict[str, Any]:
    return {
        "kind": PLAN_SCHEMA,
        "schema_version": 1,
        "classification": (
            "external_analytic_checker_boundary_not_lean_axiom_discharge"
        ),
        "atom_id": ATOM_ID,
        "lean_name": LEAN_NAME,
        "source": SOURCE_URL,
        "mode": mode,
        "q_start": q_start,
        "q_stop": q_stop,
        "source_max_q": SOURCE_MAX_Q,
        "paper_computation_min_q": SOURCE_MIN_Q,
        "characters_per_chunk": characters_per_chunk,
        "total_primitive_characters": schedule.total_characters,
        "nonzero_character_moduli": schedule.nonzero_moduli,
        "schedule_encoding": SCHEDULE_ENCODING,
        "schedule_sha256": schedule.schedule_sha256,
        "campaign_algorithm": CAMPAIGN_ALGORITHM,
        "character_algorithm": CHARACTER_ALGORITHM,
        "height_algorithm": HEIGHT_ALGORITHM,
        "producer": {
            "path": "artifacts/producer",
            "sha256": producer_sha256,
            "size": producer_size,
            "protocol": PRODUCER_PROTOCOL,
        },
        "checker": {
            "path": "artifacts/checker",
            "sha256": checker_sha256,
            "size": checker_size,
            "protocol": CHECKER_PROTOCOL,
            "bytes_distinct_from_producer": producer_sha256 != checker_sha256,
        },
        "scheduler_implementation": {
            "path": "artifacts/dirichlet_campaign.py",
            "sha256": implementation_sha256,
        },
        "external_checker_contract": {
            "rigorous_analytic_function_enclosures": "required",
            "critical_strip_boundary_zero_free": "required",
            "multiplicity_preserving_turing_or_argument_principle_count": "required",
            "symmetric_closed_height_coverage": "required",
            "primitive_character_mapping": "required",
        },
        "separate_q1_zeta_requirement": {
            "q": 1,
            "absolute_height": {"numerator": 100_000_000, "denominator": 1},
            "reason": "Platt treats conductor one as Riemann zeta separately",
            "candidate_stronger_atom": "platt-trudgian-rh-3e12",
        },
        "lean_atom_discharged": False,
    }


def initialize_campaign(
    root: Path,
    *,
    producer: Path,
    checker: Path,
    characters_per_chunk: int = 1_000_000,
    mode: str = "full_source",
    q_start: int = SOURCE_MIN_Q,
    q_stop: int = SOURCE_MAX_Q,
) -> dict[str, Any]:
    """Create an immutable campaign and pin both external executables."""

    if mode not in {"full_source", "bounded_sample"}:
        _fail("mode must be full_source or bounded_sample")
    _integer("characters_per_chunk", characters_per_chunk, minimum=1)
    if characters_per_chunk > 100_000_000:
        _fail("characters_per_chunk exceeds the control-plane safety limit")
    if mode == "full_source" and (
        q_start != SOURCE_MIN_Q or q_stop != SOURCE_MAX_Q
    ):
        _fail("full_source mode requires the exact paper-computation q range [2,400000]")
    schedule = ScheduleIndex.build(q_start, q_stop)

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        _fail(f"campaign directory must initially be empty: {root}")
    artifacts = root / "artifacts"
    artifacts.mkdir()
    producer_sha, producer_size = _copy_executable(producer, artifacts / "producer")
    checker_sha, checker_size = _copy_executable(checker, artifacts / "checker")
    _protocol_version(artifacts / "producer", PRODUCER_PROTOCOL)
    _protocol_version(artifacts / "checker", CHECKER_PROTOCOL)

    implementation = Path(__file__).resolve()
    shutil.copy2(implementation, artifacts / "dirichlet_campaign.py")
    implementation_sha, _ = sha256_file(artifacts / "dirichlet_campaign.py")
    body = _plan_body(
        mode=mode,
        q_start=q_start,
        q_stop=q_stop,
        characters_per_chunk=characters_per_chunk,
        schedule=schedule,
        producer_sha256=producer_sha,
        producer_size=producer_size,
        checker_sha256=checker_sha,
        checker_size=checker_size,
        implementation_sha256=implementation_sha,
    )
    plan_hash = sha256_bytes(canonical_json_bytes(body))
    plan = {**body, "plan_sha256": plan_hash}
    atomic_write(root / PLAN_NAME, canonical_json_bytes(plan))
    (root / "chunks").mkdir()
    return plan


def _validate_plan(root: Path) -> tuple[dict[str, Any], ScheduleIndex]:
    plan = load_canonical_json(root / PLAN_NAME)
    if not isinstance(plan, dict):
        _fail("campaign plan must be an object")
    plan_hash = _digest("plan_sha256", plan.get("plan_sha256"))
    body = dict(plan)
    del body["plan_sha256"]
    if sha256_bytes(canonical_json_bytes(body)) != plan_hash:
        _fail("campaign plan hash mismatch")
    if plan.get("kind") != PLAN_SCHEMA or plan.get("schema_version") != 1:
        _fail("unsupported campaign plan schema")
    if plan.get("atom_id") != ATOM_ID:
        _fail("campaign plan names the wrong atom")
    if plan.get("campaign_algorithm") != CAMPAIGN_ALGORITHM:
        _fail("campaign algorithm mismatch")
    if plan.get("character_algorithm") != CHARACTER_ALGORITHM:
        _fail("character enumeration algorithm mismatch")
    if plan.get("height_algorithm") != HEIGHT_ALGORITHM:
        _fail("source-height algorithm mismatch")
    if plan.get("paper_computation_min_q") != SOURCE_MIN_Q:
        _fail("paper-computation lower endpoint mismatch")
    if plan.get("source_max_q") != SOURCE_MAX_Q:
        _fail("source upper endpoint mismatch")
    characters_per_chunk = _integer(
        "characters_per_chunk", plan.get("characters_per_chunk"), minimum=1
    )
    if characters_per_chunk > 100_000_000:
        _fail("characters_per_chunk exceeds the safety limit")
    if plan.get("lean_atom_discharged") is not False:
        _fail("campaign plan must not claim to discharge the Lean atom")
    mode = plan.get("mode")
    if mode not in {"full_source", "bounded_sample"}:
        _fail("invalid campaign mode")
    q_start = _integer("q_start", plan.get("q_start"), minimum=1)
    q_stop = _integer("q_stop", plan.get("q_stop"), minimum=q_start)
    if mode == "full_source" and (
        q_start != SOURCE_MIN_Q or q_stop != SOURCE_MAX_Q
    ):
        _fail("full-source campaign domain was narrowed")
    schedule = ScheduleIndex.build(q_start, q_stop)
    if plan.get("total_primitive_characters") != schedule.total_characters:
        _fail("campaign total-character count mismatch")
    if plan.get("schedule_sha256") != schedule.schedule_sha256:
        _fail("campaign schedule commitment mismatch")
    if plan.get("separate_q1_zeta_requirement") != {
        "q": 1,
        "absolute_height": {"numerator": 100_000_000, "denominator": 1},
        "reason": "Platt treats conductor one as Riemann zeta separately",
        "candidate_stronger_atom": "platt-trudgian-rh-3e12",
    }:
        _fail("separate q=1 zeta requirement mismatch")
    for name in ("producer", "checker"):
        record = plan.get(name)
        if not isinstance(record, dict):
            _fail(f"missing {name} record")
        expected_relative = f"artifacts/{name}"
        if _text(f"{name}.path", record.get("path")) != expected_relative:
            _fail(f"pinned {name} path is not canonical")
        expected_protocol = (
            PRODUCER_PROTOCOL if name == "producer" else CHECKER_PROTOCOL
        )
        if record.get("protocol") != expected_protocol:
            _fail(f"pinned {name} protocol mismatch")
        path = root / expected_relative
        digest, size = sha256_file(path)
        if digest != _digest(f"{name}.sha256", record.get("sha256")):
            _fail(f"pinned {name} digest mismatch")
        if size != _integer(f"{name}.size", record.get("size"), minimum=0):
            _fail(f"pinned {name} size mismatch")
    expected_byte_distinction = (
        plan["producer"]["sha256"] != plan["checker"]["sha256"]
    )
    if (
        plan["checker"].get("bytes_distinct_from_producer")
        is not expected_byte_distinction
    ):
        _fail("checker byte-distinction flag does not match the pinned hashes")
    implementation_record = plan.get("scheduler_implementation")
    if not isinstance(implementation_record, dict):
        _fail("missing scheduler implementation record")
    implementation_path = root / _text(
        "scheduler_implementation.path", implementation_record.get("path")
    )
    implementation_sha, _ = sha256_file(implementation_path)
    if implementation_sha != _digest(
        "scheduler_implementation.sha256", implementation_record.get("sha256")
    ):
        _fail("pinned scheduler implementation digest mismatch")
    return plan, schedule


def _safe_artifact_path(root: Path, relative: object) -> Path:
    relative = _text("artifact.path", relative)
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        _fail(f"unsafe artifact path: {relative!r}")
    unresolved = root / candidate
    current = root.resolve()
    for component in candidate.parts:
        current = current / component
        if current.is_symlink():
            _fail(f"artifact path traverses a symbolic link: {relative!r}")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        _fail(f"artifact escapes its root: {relative!r}")
    if not resolved.is_file():
        _fail(f"artifact is not a regular file: {relative!r}")
    return resolved


def _validate_result(
    result: object, request: dict[str, Any], payload_root: Path
) -> dict[str, Any]:
    result = _expect_keys(
        "result",
        result,
        {
            "kind",
            "schema_version",
            "producer_algorithm_id",
            "producer_version",
            "request_sha256",
            "compact_task_set_sha256",
            "character_count",
            "segment_count",
            "completed",
            "output_artifacts",
        },
    )
    if result["kind"] != RESULT_SCHEMA or result["schema_version"] != 1:
        _fail("unsupported external producer result schema")
    request_hash = sha256_bytes(canonical_json_bytes(request))
    if _digest("result.request_sha256", result["request_sha256"]) != request_hash:
        _fail("external result is not bound to the exact request")
    if result["compact_task_set_sha256"] != request["compact_task_set_sha256"]:
        _fail("external result compact task set mismatch")
    if result["character_count"] != request["character_count"]:
        _fail("external result character count mismatch")
    if result["segment_count"] != request["segment_count"]:
        _fail("external result segment count mismatch")
    if _boolean("result.completed", result["completed"]) is not True:
        _fail("external producer did not complete the request")
    _text("producer_algorithm_id", result["producer_algorithm_id"])
    _text("producer_version", result["producer_version"])
    artifacts = result["output_artifacts"]
    if not isinstance(artifacts, list):
        _fail("result.output_artifacts must be a list")
    previous = ""
    for index, artifact in enumerate(artifacts):
        artifact = _expect_keys(
            f"artifact[{index}]", artifact, {"path", "sha256", "size", "media_type"}
        )
        relative = _text(f"artifact[{index}].path", artifact["path"])
        if relative <= previous:
            _fail("output artifact paths must be unique and strictly sorted")
        previous = relative
        path = _safe_artifact_path(payload_root, relative)
        digest, size = sha256_file(path)
        if digest != _digest(f"artifact[{index}].sha256", artifact["sha256"]):
            _fail(f"output artifact digest mismatch: {relative}")
        if size != _integer(f"artifact[{index}].size", artifact["size"], minimum=0):
            _fail(f"output artifact size mismatch: {relative}")
        _text(f"artifact[{index}].media_type", artifact["media_type"])
    return result


CHECKER_TRUE_FIELDS = (
    "accepted",
    "all_requested_characters_covered",
    "primitive_character_mapping_checked",
    "source_height_exact",
    "closed_symmetric_height_covered",
    "analytic_function_enclosures_rigorous",
    "critical_strip_boundary_zero_free",
    "turing_or_argument_principle_count_complete",
    "zero_multiplicities_preserved",
    "all_nontrivial_zeros_on_critical_line",
)


def _validate_checker_receipt(
    receipt: object,
    request: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    receipt = _expect_keys(
        "checker receipt",
        receipt,
        {
            "kind",
            "schema_version",
            "checker_algorithm_id",
            "checker_version",
            "request_sha256",
            "result_sha256",
            "compact_task_set_sha256",
            "character_count",
            "segment_count",
            *CHECKER_TRUE_FIELDS,
        },
    )
    if receipt["kind"] != CHECKER_RECEIPT_SCHEMA or receipt["schema_version"] != 1:
        _fail("unsupported external checker receipt schema")
    if receipt["request_sha256"] != sha256_bytes(canonical_json_bytes(request)):
        _fail("checker receipt request digest mismatch")
    if receipt["result_sha256"] != sha256_bytes(canonical_json_bytes(result)):
        _fail("checker receipt result digest mismatch")
    if receipt["compact_task_set_sha256"] != request["compact_task_set_sha256"]:
        _fail("checker receipt compact task set mismatch")
    if receipt["character_count"] != request["character_count"]:
        _fail("checker receipt character count mismatch")
    if receipt["segment_count"] != request["segment_count"]:
        _fail("checker receipt segment count mismatch")
    _text("checker_algorithm_id", receipt["checker_algorithm_id"])
    _text("checker_version", receipt["checker_version"])
    for field in CHECKER_TRUE_FIELDS:
        if _boolean(f"checker receipt.{field}", receipt[field]) is not True:
            _fail(f"external checker did not establish {field}")
    return receipt


def _chunk_directories(root: Path) -> list[Path]:
    chunks = root / "chunks"
    if not chunks.is_dir():
        _fail("campaign chunks directory is missing")
    result = sorted(path for path in chunks.iterdir() if path.is_dir())
    expected_names = [f"{CHUNK_PREFIX}{i:0{CHUNK_DIGITS}d}" for i in range(len(result))]
    if [path.name for path in result] != expected_names:
        _fail("chunk directory sequence contains a gap or unexpected directory")
    return result


def _expected_request(
    plan: dict[str, Any], schedule: ScheduleIndex, ordinal: int, cursor: int
) -> dict[str, Any]:
    request = make_request(plan, schedule, ordinal, cursor)
    return request


def _validate_chunk(
    directory: Path,
    plan: dict[str, Any],
    schedule: ScheduleIndex,
    expected_ordinal: int,
    expected_cursor: int,
    previous_chain_sha256: str,
) -> tuple[int, str, dict[str, Any]]:
    request = load_canonical_json(directory / "request.json")
    expected = _expected_request(plan, schedule, expected_ordinal, expected_cursor)
    if request != expected:
        _fail(f"chunk {expected_ordinal} request differs from canonical schedule")
    result = _validate_result(
        load_canonical_json(directory / "result.json"), request, directory / "payload"
    )
    receipt = _validate_checker_receipt(
        load_canonical_json(directory / "checker-receipt.json"), request, result
    )
    record = load_canonical_json(directory / "chunk.json")
    if not isinstance(record, dict) or record.get("kind") != CHUNK_SCHEMA:
        _fail(f"chunk {expected_ordinal} has an invalid chain record")
    chain_hash = _digest("chunk.chain_sha256", record.get("chain_sha256"))
    body = dict(record)
    del body["chain_sha256"]
    expected_body = {
        "kind": CHUNK_SCHEMA,
        "schema_version": 1,
        "chunk_ordinal": expected_ordinal,
        "global_character_start": expected_cursor,
        "global_character_stop": request["global_character_stop"],
        "character_count": request["character_count"],
        "segment_count": request["segment_count"],
        "previous_chain_sha256": previous_chain_sha256,
        "request_sha256": sha256_bytes(canonical_json_bytes(request)),
        "result_sha256": sha256_bytes(canonical_json_bytes(result)),
        "checker_receipt_sha256": sha256_bytes(canonical_json_bytes(receipt)),
    }
    if body != expected_body:
        _fail(f"chunk {expected_ordinal} chain record mismatch")
    if sha256_bytes(canonical_json_bytes(body)) != chain_hash:
        _fail(f"chunk {expected_ordinal} chain digest mismatch")
    return request["global_character_stop"], chain_hash, receipt


def verify_campaign(root: Path, *, require_complete: bool = False) -> dict[str, Any]:
    """Replay the finite schedule and every retained hash-linked artifact."""

    root = root.resolve()
    plan, schedule = _validate_plan(root)
    cursor = 0
    chain = ZERO_SHA256
    chunks = _chunk_directories(root)
    checker_algorithms: set[str] = set()
    for ordinal, directory in enumerate(chunks):
        cursor, chain, receipt = _validate_chunk(
            directory, plan, schedule, ordinal, cursor, chain
        )
        checker_algorithms.add(receipt["checker_algorithm_id"])
    complete = cursor == schedule.total_characters
    if require_complete and not complete:
        _fail(
            f"campaign is incomplete: {cursor}/{schedule.total_characters} characters"
        )
    final_present = (root / FINAL_NAME).exists()
    if final_present:
        final = load_canonical_json(root / FINAL_NAME)
        if not complete:
            _fail("final receipt exists for an incomplete campaign")
        expected_final_body = {
            "kind": FINAL_SCHEMA,
            "schema_version": 1,
            "classification": "full_external_checker_assertion_not_lean_proof",
            "atom_id": ATOM_ID,
            "plan_sha256": plan["plan_sha256"],
            "mode": plan["mode"],
            "q_start": plan["q_start"],
            "q_stop": plan["q_stop"],
            "characters_covered": cursor,
            "chunks": len(chunks),
            "terminal_chain_sha256": chain,
            "schedule_sha256": schedule.schedule_sha256,
            "coverage_class": (
                "full_source_external_checker_asserted"
                if plan["mode"] == "full_source"
                else "bounded_sample_external_checker_asserted"
            ),
            "external_checker_algorithms": sorted(checker_algorithms),
            "external_checker_bytes_distinct_from_producer": plan["checker"][
                "bytes_distinct_from_producer"
            ],
            "internally_implemented_turing_or_argument_principle": False,
            "lean_atom_discharged": False,
        }
        if final != expected_final_body:
            _fail("final receipt differs from the replayed campaign")
    return {
        "accepted": True,
        "classification": (
            "external_checker_asserted_complete_campaign"
            if complete
            else "external_checker_asserted_partial_campaign"
        ),
        "mode": plan["mode"],
        "q_start": plan["q_start"],
        "q_stop": plan["q_stop"],
        "characters_covered": cursor,
        "characters_total": schedule.total_characters,
        "chunks": len(chunks),
        "complete": complete,
        "terminal_chain_sha256": chain,
        "final_present": final_present,
        "external_checker_bytes_distinct_from_producer": plan["checker"][
            "bytes_distinct_from_producer"
        ],
        "internally_implemented_turing_or_argument_principle": False,
        "lean_atom_discharged": False,
    }


def _run_external(
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int | None,
) -> None:
    executable = Path(command[0])
    try:
        with executable.open("rb") as source:
            first_line = source.readline(256)
    except OSError as error:
        raise DirichletCampaignError(f"cannot inspect backend {executable}: {error}") from error
    if first_line.startswith(b"#!") and b"python" in first_line.lower():
        command = [sys.executable, *command]
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = subprocess.run(
                command,
                check=False,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                env=environment,
            )
    except (OSError, subprocess.SubprocessError) as error:
        raise DirichletCampaignError(f"external command failed to run: {error}") from error
    if completed.returncode != 0:
        _fail(f"external command exited with status {completed.returncode}: {command[0]}")


def _produce_one(
    root: Path,
    plan: dict[str, Any],
    schedule: ScheduleIndex,
    ordinal: int,
    cursor: int,
    previous_chain_sha256: str,
    timeout: int | None,
) -> tuple[int, str]:
    request = make_request(plan, schedule, ordinal, cursor)
    staging_parent = root / ".staging"
    staging_parent.mkdir(exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"chunk-{ordinal:08d}-", dir=staging_parent))
    try:
        payload = temporary / "payload"
        payload.mkdir()
        request_path = temporary / "request.json"
        result_path = temporary / "result.json"
        receipt_path = temporary / "checker-receipt.json"
        atomic_write(request_path, canonical_json_bytes(request))
        producer = root / plan["producer"]["path"]
        checker = root / plan["checker"]["path"]
        _run_external(
            [
                str(producer),
                "produce",
                "--request",
                str(request_path),
                "--output",
                str(result_path),
                "--artifact-root",
                str(payload),
            ],
            temporary / "producer.stdout",
            temporary / "producer.stderr",
            timeout,
        )
        result = _validate_result(load_canonical_json(result_path), request, payload)
        _run_external(
            [
                str(checker),
                "verify",
                "--request",
                str(request_path),
                "--result",
                str(result_path),
                "--artifact-root",
                str(payload),
                "--receipt",
                str(receipt_path),
            ],
            temporary / "checker.stdout",
            temporary / "checker.stderr",
            timeout,
        )
        receipt = _validate_checker_receipt(load_canonical_json(receipt_path), request, result)
        body = {
            "kind": CHUNK_SCHEMA,
            "schema_version": 1,
            "chunk_ordinal": ordinal,
            "global_character_start": cursor,
            "global_character_stop": request["global_character_stop"],
            "character_count": request["character_count"],
            "segment_count": request["segment_count"],
            "previous_chain_sha256": previous_chain_sha256,
            "request_sha256": sha256_bytes(canonical_json_bytes(request)),
            "result_sha256": sha256_bytes(canonical_json_bytes(result)),
            "checker_receipt_sha256": sha256_bytes(canonical_json_bytes(receipt)),
        }
        chain = sha256_bytes(canonical_json_bytes(body))
        atomic_write(
            temporary / "chunk.json",
            canonical_json_bytes({**body, "chain_sha256": chain}),
        )
        destination = root / "chunks" / f"{CHUNK_PREFIX}{ordinal:0{CHUNK_DIGITS}d}"
        if destination.exists():
            _fail(f"destination chunk already exists: {destination}")
        os.replace(temporary, destination)
        return request["global_character_stop"], chain
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run_campaign(
    root: Path, *, max_chunks: int | None = None, timeout: int | None = None
) -> dict[str, Any]:
    """Resume production after replaying the complete retained prefix."""

    if max_chunks is not None:
        _integer("max_chunks", max_chunks, minimum=1)
    if timeout is not None:
        _integer("timeout", timeout, minimum=1)
    root = root.resolve()
    lock_path = root / ".campaign.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = verify_campaign(root)
        plan, schedule = _validate_plan(root)
        cursor = state["characters_covered"]
        chain = state["terminal_chain_sha256"]
        ordinal = state["chunks"]
        produced = 0
        while cursor < schedule.total_characters:
            if max_chunks is not None and produced >= max_chunks:
                break
            cursor, chain = _produce_one(
                root, plan, schedule, ordinal, cursor, chain, timeout
            )
            ordinal += 1
            produced += 1
        return verify_campaign(root)


def finalize_campaign(root: Path) -> dict[str, Any]:
    """Emit a full or bounded receipt after a complete exact replay."""

    root = root.resolve()
    state = verify_campaign(root, require_complete=True)
    plan, schedule = _validate_plan(root)
    checker_algorithms: set[str] = set()
    for directory in _chunk_directories(root):
        receipt = load_canonical_json(directory / "checker-receipt.json")
        checker_algorithms.add(receipt["checker_algorithm_id"])
    final = {
        "kind": FINAL_SCHEMA,
        "schema_version": 1,
        "classification": "full_external_checker_assertion_not_lean_proof",
        "atom_id": ATOM_ID,
        "plan_sha256": plan["plan_sha256"],
        "mode": plan["mode"],
        "q_start": plan["q_start"],
        "q_stop": plan["q_stop"],
        "characters_covered": state["characters_covered"],
        "chunks": state["chunks"],
        "terminal_chain_sha256": state["terminal_chain_sha256"],
        "schedule_sha256": schedule.schedule_sha256,
        "coverage_class": (
            "full_source_external_checker_asserted"
            if plan["mode"] == "full_source"
            else "bounded_sample_external_checker_asserted"
        ),
        "external_checker_algorithms": sorted(checker_algorithms),
        "external_checker_bytes_distinct_from_producer": plan["checker"][
            "bytes_distinct_from_producer"
        ],
        "internally_implemented_turing_or_argument_principle": False,
        "lean_atom_discharged": False,
    }
    atomic_write(root / FINAL_NAME, canonical_json_bytes(final))
    verify_campaign(root, require_complete=True)
    return final


def rerun_external_checkers(root: Path, *, timeout: int | None = None) -> dict[str, Any]:
    """Freshly rerun the pinned checker on every retained producer result."""

    root = root.resolve()
    plan, _ = _validate_plan(root)
    checker = root / plan["checker"]["path"]
    checked = 0
    for directory in _chunk_directories(root):
        temporary_receipt = directory / ".checker-receipt.replay.json"
        temporary_stdout = directory / ".checker-replay.stdout"
        temporary_stderr = directory / ".checker-replay.stderr"
        try:
            _run_external(
                [
                    str(checker),
                    "verify",
                    "--request",
                    str(directory / "request.json"),
                    "--result",
                    str(directory / "result.json"),
                    "--artifact-root",
                    str(directory / "payload"),
                    "--receipt",
                    str(temporary_receipt),
                ],
                temporary_stdout,
                temporary_stderr,
                timeout,
            )
            fresh = load_canonical_json(temporary_receipt)
            retained = load_canonical_json(directory / "checker-receipt.json")
            if fresh != retained:
                _fail(f"fresh checker receipt differs for {directory.name}")
            checked += 1
        finally:
            for path in (temporary_receipt, temporary_stdout, temporary_stderr):
                path.unlink(missing_ok=True)
    state = verify_campaign(root)
    return {
        **state,
        "fresh_external_checker_replays": checked,
        "fresh_checker_replay_performed": True,
    }


def capability_report() -> dict[str, Any]:
    """Describe the honest readiness boundary without requiring a backend."""

    schedule = ScheduleIndex.build(SOURCE_MIN_Q, SOURCE_MAX_Q)
    return {
        "atom_id": ATOM_ID,
        "paper_computation_domain": {
            "q_start": SOURCE_MIN_Q,
            "q_stop": SOURCE_MAX_Q,
        },
        "total_primitive_characters": schedule.total_characters,
        "nonzero_character_moduli": schedule.nonzero_moduli,
        "schedule_sha256": schedule.schedule_sha256,
        "exact_primitive_character_scheduler": True,
        "exact_source_height_scheduler": True,
        "gap_free_resumable_campaign": True,
        "pinned_external_producer_protocol": PRODUCER_PROTOCOL,
        "pinned_external_checker_protocol": CHECKER_PROTOCOL,
        # This key means a single conforming source producer for the campaign
        # protocol, not merely the presence of its arithmetic components.
        "in_repository_fast_platt_lattice_fft_backend": False,
        "in_repository_optimized_platt_components": True,
        "in_repository_conditional_large_q_taylor_stage": True,
        "conditional_large_q_taylor_stage": {
            "algorithm": "platt-dirichlet-large-q-lattice-taylor-stage-v1",
            "paper_parameters": {"D": 2048, "N": 15, "columns": 16},
            "source_plan": "tools/tg_dirichlet_lattice_stage.py plan",
            "certified_lattice_seed_generator_present": True,
            "unit_group_fft_present": True,
            "small_q_gaussian_dft_present": True,
            "completed_value_and_sinc_arithmetic_present": True,
            "turing_arithmetic_present_but_production_accept_false": True,
            "external_atom_discharged": False,
        },
        "optimized_component_capabilities": {
            "lattice_certificates": "tools/tg_dirichlet_lattice_certificates.py capability",
            "lattice_taylor": "tools/tg_dirichlet_lattice_stage.py plan",
            "t_major_lattice_cache": "tools/tg_dirichlet_lattice_cache.py capability",
            "fused_large_q_batch": "tools/tg_dirichlet_largeq_batch.py capability",
            "certified_recovery_seeds": "tools/tg_dirichlet_recovery_seeds.py capability",
            "residue_composition": "tools/tg_dirichlet_residue_composition.py capability",
            "all_character_fft": "tools/tg_dirichlet_allchars_stage.py capability",
            "small_q": "tools/tg_dirichlet_booker_smallq.py capability",
            "small_q_certified_disk_engine": "platt-booker-smallq-certified-disk-dft-v2",
            "small_q_semantic_sign_reducer": (
                "tools/tg_dirichlet_booker_smallq_semantic_reducer.py"
            ),
            "postprocess": "tools/tg_dirichlet_postprocess.py capability",
            "persistent_completed_l_consumer": "tools/tg_dirichlet_stream_zero_consumer.py capability",
            "scalable_root_numbers": "tools/tg_dirichlet_root_number_stage.py capability",
            "source_root_catalog": "tools/tg_dirichlet_root_catalog.py capability",
            "persistent_large_q_pipeline": "tools/tg_dirichlet_largeq_pipeline.py capability",
            "typed_fft_pipeline_bundle": "tools/tg_dirichlet_fft_pipeline_bundle.py capability",
            "t_major_typed_bundle_adapter": "tools/tg_dirichlet_tmajor_adapter.py capability",
            "t_major_row_resident_cuda_block": (
                "tools/tg_dirichlet_tmajor_cuda_block.py capability"
            ),
            "source_t_major_supervisor": "tools/tg_dirichlet_source_supervisor.py capability",
            "direct_zero_closure": "tools/tg_dirichlet_zero_closure.py capability",
            "persistent_source_composition_ready": True,
            "scalable_root_number_artifact_ready": True,
            "full_recovery_seed_artifact_and_replay_implemented": True,
            "seeded_fused_large_q_service_implemented": True,
            "seeded_large_q_logical_input_bytes": 5_180_404_381_680_112,
            "t_major_unique_lattice_payload_bytes": 134_205_145_088,
            "former_t_major_descriptor_repeated_input_bytes": (
                41_413_846_139_376
            ),
            "t_major_compact_total_input_bytes": 286_556_459_000,
            "t_major_compact_input_including_recovery_seeds": (
                339_564_685_336
            ),
            "direct_t_major_input_reduction_ratio_from_former_model": (
                41_413_846_139_376 / 286_556_459_000
            ),
            "t_major_lattice_cache_contract_ready": True,
            "t_major_lattice_replay_repacker_ready": True,
            "source_root_catalog_contract_ready": True,
            "source_root_catalog_generated_and_audited": False,
            "source_t_major_supervisor_plan_ready": True,
            "source_t_major_supervisor_executable": False,
            "row_resident_t_major_cuda_component_executable": True,
            "direct_MPFR_factor_and_exact_tail_source_ready": True,
            "typed_fft_receipt_bundle_ready": True,
            "t_major_typed_bundle_admission_adapter_ready": True,
            "typed_bundle_lattice_payload_to_cache_row_binding_ready": True,
            "typed_fft_receipt_bundle_integrated_into_t_major_lane": False,
            "t_major_zero_state_import_export_ready": False,
            "recovery_seed_width_usefulness_source_wide_ready": False,
            # The exact cache and schedule now exist, but this combined flag
            # remains false until the CUDA service consumes them in a
            # source-wide run.
            "hurwitz_lattice_cache_and_broadcast_ready": False,
            "certified_box_producer_and_source_io_ready": False,
            "small_q_semantic_time_tail_sign_reducer_ready": True,
            "small_q_semantic_reducer_cuda_fused": False,
            "small_q_semantic_reducer_source_scale_measured": False,
            "small_q_source_seed_and_width_boundary_ready": False,
            "production_closed_optimized_campaign_ready": False,
            "uniform_interpolation_proof_ready": False,
            "turing_normalization_and_phase_resolved": False,
        },
        "in_repository_compact_fused_selected_character_stage": True,
        "compact_fused_selected_character_stage": {
            "algorithm": "platt-dirichlet-fused-character-block-v1",
            "capability": "tools/tg_dirichlet_fused_stage.py capability",
            "canonical_crt_unit_residues_generated_on_device": True,
            "per_residue_request_or_result_files": False,
            "independent_exact_dyadic_replay": True,
            "selected_character_direct_complexity": "O(K * phi(q))",
            "all_character_bluestein_interval_fft_present_elsewhere": True,
            "production_role": "sparse audit, exception recomputation, and FFT KAT oracle",
            "external_atom_discharged": False,
        },
        "in_repository_rigorous_argument_principle_reference_backend": True,
        "reference_backend": "tools/tg_dirichlet_flint_backend.py",
        "reference_backend_accepts_full_source_requests": True,
        "reference_backend_source_scale_benchmarked": False,
        "full_source_algorithm_wired_but_unscaled": True,
        "default_reference_resource_ceiling_may_require_operator_increase": True,
        "python_flint_runtime_closure_pinned_by_campaign": False,
        "separate_q1_zeta_requirement": {
            "absolute_height": {"numerator": 100_000_000, "denominator": 1},
            "candidate_stronger_atom": "platt-trudgian-rh-3e12",
        },
        "in_repository_moderate_height_evaluator": "tools/run_grh_poc.py",
        "single_source_command": [
            "{python-flint-python}",
            "{repository}/tools/tg_dirichlet_campaign.py",
            "source",
            "{workspace}",
            "--q1-zeta-final",
            "{completed-platt-trudgian-zeta-final.json}",
        ],
        "current_numeric_turing_sanity_accepted_as_completeness": False,
        "lean_atom_discharged": False,
    }
