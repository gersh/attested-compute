# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable FLINT/Arb campaigns for the two Riemann-zeta trust atoms.

Origin notice
-------------
The pinned-version checks, exact Arb endpoint extraction, interval digest, and
finite completeness argument were adapted from the project-owned
``claude_math/ext/ch25_certificates/scripts/verify_flint_head.py`` at commit
``667f873bcfdf3f3d7bd4f835a25ee5a9ad5e20ce``.  This module generalizes that
one-shot height-20,000 replay into bounded-memory, hash-linked batches.

This remains an *external* analytic computation.  A successful campaign
depends on the reviewed FLINT implementation and its host toolchain; it does
not prove that FLINT realizes Mathlib's ``riemannZeta`` and does not discharge
a Lean axiom.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, NoReturn, Protocol, Sequence


AUTHOR = "Gershon Bialer"
EXPECTED_PYTHON_FLINT = "0.9.0"
EXPECTED_FLINT = "3.6.0"
EXPECTED_FLINT_RELEASE = 30_600

PLAN_SCHEMA = "sparkinterval.tg.zeta_zero_campaign.plan.v1"
CHUNK_SCHEMA = "sparkinterval.tg.zeta_zero_campaign.chunk.v1"
FINAL_SCHEMA = "sparkinterval.tg.zeta_zero_campaign.final.v1"
ALGORITHM = "flint-zeta-nzeros-and-indexed-critical-line-isolation-v1"
PLAN_FILENAME = "campaign.json"
FINAL_FILENAME = "final.json"
CHUNK_PREFIX = "chunk-"
CHUNK_DIGITS = 12
MAX_JSON_BYTES = 8 * 1024 * 1024
MIN_PRECISION_BITS = 80
MAX_PRECISION_BITS = 16_384
MAX_BATCH_SIZE = 10_000_000
IMPLEMENTATION_SOURCE = Path(__file__).resolve()
Q128_SCALE = 1 << 128
PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256 = (
    "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7"
)
PLATT_HEAD_ALL_Q128_ROWS_SHA256 = (
    "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca"
)

FLINT_DOCS_URL = (
    "https://flintlib.org/doc/acb_dirichlet.html#riemann-zeta-function-zeros"
)
FLINT_SOURCE_URL = (
    "https://github.com/flintlib/flint/tree/v3.6.0/src/acb_dirichlet"
)
CH25_URL = "https://arxiv.org/abs/2512.15709v1"
PLATT_TRUDGIAN_URL = "https://doi.org/10.1112/blms.12460"


class ZetaCampaignError(RuntimeError):
    """A zeta campaign configuration, computation, or artifact failed closed."""


def _fail(message: str) -> NoReturn:
    raise ZetaCampaignError(message)


@dataclass(frozen=True)
class CampaignProfile:
    """Immutable source parameters for one named external atom."""

    name: str
    atom_id: str
    lean_name: str
    height: int
    expected_zero_count: int
    reciprocal_strict_upper_bound: Fraction | None
    source: str


PLATT_HEAD_2E4 = CampaignProfile(
    name="platt-head-2e4",
    atom_id="platt-head-2e4",
    lean_name=(
        "AnalyticNT.ChebyshevPsi."
        "finite_check_platt_zero_enumeration_2e4_source"
    ),
    height=20_000,
    expected_zero_count=22_491,
    reciprocal_strict_upper_bound=Fraction(257_983, 50_000),
    source=CH25_URL,
)

PLATT_TRUDGIAN_RH_3E12 = CampaignProfile(
    name="platt-trudgian-rh-3e12",
    atom_id="platt-trudgian-rh-3e12",
    lean_name=(
        "AnalyticNT.ChebyshevPsi."
        "finite_check_platt_trudgian_rh_zeta_3e12"
    ),
    # This is the exact source cutoff, not the rounded name of the atom.
    height=3_000_175_332_800,
    # The count reported by the source campaign.  A new campaign accepts it
    # only after a fresh exact arb.zeta_nzeros(height) call returns this value.
    expected_zero_count=12_363_153_437_138,
    reciprocal_strict_upper_bound=None,
    source=PLATT_TRUDGIAN_URL,
)

PROFILES = {
    profile.name: profile
    for profile in (PLATT_HEAD_2E4, PLATT_TRUDGIAN_RH_3E12)
}


@dataclass(frozen=True)
class IsolatedOrdinate:
    """Exact rational endpoints of one positive critical-line zero ball."""

    lower: Fraction
    upper: Fraction


@dataclass(frozen=True)
class Q128CellRecord:
    """One exact retained source row in the shared Lean Q128 format."""

    index: int
    lower: int
    upper: int
    reciprocal_upper: int


class ZetaBackend(Protocol):
    """Small injectable boundary used by tests and the pinned FLINT backend."""

    def version_record(self) -> dict[str, object]: ...

    def exact_zero_count(self, height: int, precision_bits: int) -> int: ...

    def isolate_ordinates(
        self, first_index: int, count: int, precision_bits: int
    ) -> Sequence[IsolatedOrdinate]: ...


def _int(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        _fail(f"{name} must be a Boolean")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str):
        _fail(f"{name} must be a string")
    return value


def _digest(name: str, value: object) -> str:
    value = _text(name, value)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _expect_keys(name: str, value: object, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    expected = set(keys)
    actual = set(value)
    if actual != expected:
        _fail(
            f"{name} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _rational_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _rational(name: str, value: object) -> Fraction:
    document = _expect_keys(name, value, {"numerator", "denominator"})
    numerator = _int(f"{name}.numerator", document["numerator"])
    denominator = _int(f"{name}.denominator", document["denominator"], minimum=1)
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        _fail(f"{name} is not in canonical lowest terms")
    return result


def _optional_rational(name: str, value: object) -> Fraction | None:
    if value is None:
        return None
    return _rational(name, value)


def canonical_json_bytes(value: object) -> bytes:
    """Return the campaign's canonical compact ASCII JSON plus final newline."""

    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def implementation_source_sha256() -> str:
    """Hash the exact reusable producer/checker source stored in the plan."""

    try:
        raw = IMPLEMENTATION_SOURCE.read_bytes()
    except OSError as error:
        raise ZetaCampaignError(
            f"cannot capture implementation source {IMPLEMENTATION_SOURCE}: {error}"
        ) from error
    return sha256_bytes(raw)


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON constant is forbidden: {value}")


def _reject_float(value: str) -> NoReturn:
    _fail(f"JSON floating-point number is forbidden: {value}")


def _parse_int(value: str) -> int:
    if len(value.lstrip("-")) > 100:
        _fail("JSON integer exceeds the local digit limit")
    return int(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def parse_canonical_json(raw: bytes, *, label: str) -> dict[str, Any]:
    """Parse bounded canonical JSON while rejecting floats and duplicate keys."""

    if type(raw) is not bytes:
        _fail(f"{label} must be supplied as bytes")
    if len(raw) > MAX_JSON_BYTES:
        _fail(f"{label} exceeds the {MAX_JSON_BYTES}-byte local limit")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ZetaCampaignError(f"{label} is not ASCII") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_int,
        )
    except ZetaCampaignError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise ZetaCampaignError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        _fail(f"{label} root must be an object")
    if canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical compact JSON with one final newline")
    return value


def read_bounded(path: str | Path, *, label: str) -> bytes:
    artifact = Path(path)
    try:
        with artifact.open("rb") as source:
            raw = source.read(MAX_JSON_BYTES + 1)
    except OSError as error:
        raise ZetaCampaignError(f"cannot read {label} {artifact}: {error}") from error
    if len(raw) > MAX_JSON_BYTES:
        _fail(f"{label} exceeds the {MAX_JSON_BYTES}-byte local limit")
    return raw


def write_once(path: Path, raw: bytes) -> None:
    """Atomically install immutable bytes, accepting an identical existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = read_bounded(path, label=path.name)
            if existing != raw:
                _fail(f"refusing to replace nonidentical immutable artifact {path}")
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def chunk_filename(chunk_index: int) -> str:
    chunk_index = _int("chunk_index", chunk_index, minimum=0)
    return f"{CHUNK_PREFIX}{chunk_index:0{CHUNK_DIGITS}d}.json"


class FlintZetaBackend:
    """Pinned python-flint 0.9.0 / FLINT 3.6.0 implementation boundary."""

    def __init__(self) -> None:
        try:
            module = importlib.import_module("flint")
            self._acb = module.acb
            self._arb = module.arb
            self._ctx = module.ctx
            self._fmpq = module.fmpq
        except (ImportError, AttributeError) as error:
            raise ZetaCampaignError(
                "python-flint==0.9.0 (bundling FLINT 3.6.0) is required"
            ) from error
        python_version = str(module.__version__)
        flint_version = str(module.__FLINT_VERSION__)
        flint_release = int(module.__FLINT_RELEASE__)
        if python_version != EXPECTED_PYTHON_FLINT:
            _fail(
                "python-flint version mismatch: expected "
                f"{EXPECTED_PYTHON_FLINT}, got {python_version}"
            )
        if flint_version != EXPECTED_FLINT or flint_release != EXPECTED_FLINT_RELEASE:
            _fail(
                "FLINT version mismatch: expected 3.6.0 release 30600, got "
                f"{flint_version} release {flint_release}"
            )
        self._versions = {
            "python_flint": python_version,
            "flint": flint_version,
            "flint_release": flint_release,
        }

    def version_record(self) -> dict[str, object]:
        return dict(self._versions)

    def _configure(self, precision_bits: int) -> None:
        precision_bits = _int(
            "precision_bits", precision_bits, minimum=MIN_PRECISION_BITS
        )
        if precision_bits > MAX_PRECISION_BITS:
            _fail(f"precision_bits must be at most {MAX_PRECISION_BITS}")
        self._ctx.prec = precision_bits
        # Fixed for reproducibility.  Scale-out should distribute immutable
        # campaign directories or replay chunks, not mutate FLINT's global ctx.
        self._ctx.threads = 1

    @staticmethod
    def _endpoint(value: Any, *, label: str) -> Fraction:
        if not value.is_finite() or not value.is_exact():
            _fail(f"{label} is not an exact finite Arb endpoint")
        rational = value.fmpq()
        return Fraction(int(rational.numerator), int(rational.denominator))

    def exact_zero_count(self, height: int, precision_bits: int) -> int:
        height = _int("height", height, minimum=1)
        self._configure(precision_bits)
        count_ball = self._arb(self._fmpq(height, 1)).zeta_nzeros()
        if not count_ball.is_finite() or not count_ball.is_exact():
            _fail("arb.zeta_nzeros(height) did not return an exact finite integer")
        count = count_ball.unique_fmpz()
        if count is None:
            _fail("arb.zeta_nzeros(height) did not have a unique integer value")
        result = int(count)
        if result < 0:
            _fail("arb.zeta_nzeros(height) returned a negative count")
        return result

    def isolate_ordinates(
        self, first_index: int, count: int, precision_bits: int
    ) -> Sequence[IsolatedOrdinate]:
        first_index = _int("first_index", first_index, minimum=1)
        count = _int("count", count, minimum=1)
        if count > MAX_BATCH_SIZE:
            _fail(f"count must be at most {MAX_BATCH_SIZE}")
        self._configure(precision_bits)
        zeros = self._acb.zeta_zeros(first_index, count)
        if len(zeros) != count:
            _fail(f"acb.zeta_zeros returned {len(zeros)} records, expected {count}")
        half = self._fmpq(1, 2)
        result: list[IsolatedOrdinate] = []
        for offset, zero in enumerate(zeros):
            index = first_index + offset
            if not zero.is_finite():
                _fail(f"zero {index} is not a finite Acb ball")
            if not zero.real.is_exact() or zero.real.fmpq() != half:
                _fail(f"zero {index} is not rigorously fixed on Re(s) = 1/2")
            lower = self._endpoint(zero.imag.lower(), label=f"zero {index} lower")
            upper = self._endpoint(zero.imag.upper(), label=f"zero {index} upper")
            if lower <= 0:
                _fail(f"zero {index} ordinate is not strictly positive")
            if upper < lower:
                _fail(f"zero {index} has reversed ordinate endpoints")
            result.append(IsolatedOrdinate(lower, upper))
        return result


def _profile_claim(profile: CampaignProfile) -> dict[str, object]:
    return {
        "atom_id": profile.atom_id,
        "lean_name": profile.lean_name,
        "height": profile.height,
        "expected_zero_count": profile.expected_zero_count,
        "reciprocal_strict_upper_bound": (
            None
            if profile.reciprocal_strict_upper_bound is None
            else _rational_json(profile.reciprocal_strict_upper_bound)
        ),
        "source": profile.source,
    }


def create_plan(
    profile: CampaignProfile,
    *,
    batch_size: int = 4_096,
    precision_bits: int = 96,
    backend: ZetaBackend | None = None,
) -> dict[str, object]:
    """Compute the exact all-zero count and create an immutable campaign plan."""

    batch_size = _int("batch_size", batch_size, minimum=1)
    if batch_size > MAX_BATCH_SIZE:
        _fail(f"batch_size must be at most {MAX_BATCH_SIZE}")
    precision_bits = _int("precision_bits", precision_bits, minimum=MIN_PRECISION_BITS)
    if precision_bits > MAX_PRECISION_BITS:
        _fail(f"precision_bits must be at most {MAX_PRECISION_BITS}")
    if profile.height < 1 or profile.expected_zero_count < 0:
        _fail("profile height/count is invalid")
    runtime = backend if backend is not None else FlintZetaBackend()
    versions = runtime.version_record()
    count = runtime.exact_zero_count(profile.height, precision_bits)
    if count != profile.expected_zero_count:
        _fail(
            f"exact zeta_nzeros({profile.height}) returned {count}, "
            f"but profile {profile.name} requires {profile.expected_zero_count}"
        )
    total_records = count + 1
    chunks = (total_records + batch_size - 1) // batch_size
    return {
        "schema": PLAN_SCHEMA,
        "author": AUTHOR,
        "algorithm": ALGORITHM,
        "profile": profile.name,
        "claim": _profile_claim(profile),
        "configuration": {
            "precision_bits": precision_bits,
            "flint_threads": 1,
            "batch_size": batch_size,
        },
        "versions": versions,
        "plan": {
            "exact_multiplicity_count": count,
            "first_isolation_index": 1,
            "last_included_index": count,
            "first_excluded_index": count + 1,
            "total_isolation_records": total_records,
            "chunk_count": chunks,
        },
        "provenance": {
            "flint_documentation": FLINT_DOCS_URL,
            "flint_3_6_source": FLINT_SOURCE_URL,
            "python_flint_requirement": "python-flint==0.9.0",
            "flint_requirement": "FLINT==3.6.0",
            "adapted_source_commit": (
                "667f873bcfdf3f3d7bd4f835a25ee5a9ad5e20ce"
            ),
            "implementation": "tg_verifier/zeta_zero_campaign.py",
            "implementation_source_sha256": implementation_source_sha256(),
        },
        "trust_boundary": {
            "classification": "external_flint_analytic_computation",
            "flint_semantics_trusted": True,
            "lean_realization_proved": False,
            "lean_atom_discharged": False,
        },
    }


def _validate_versions(value: object) -> dict[str, object]:
    versions = _expect_keys(
        "versions", value, {"python_flint", "flint", "flint_release"}
    )
    if _text("versions.python_flint", versions["python_flint"]) != EXPECTED_PYTHON_FLINT:
        _fail("plan has the wrong python-flint version")
    if _text("versions.flint", versions["flint"]) != EXPECTED_FLINT:
        _fail("plan has the wrong FLINT version")
    if _int("versions.flint_release", versions["flint_release"]) != EXPECTED_FLINT_RELEASE:
        _fail("plan has the wrong FLINT release")
    return versions


def validate_plan(document: object) -> dict[str, Any]:
    plan_doc = _expect_keys(
        "campaign plan",
        document,
        {
            "schema",
            "author",
            "algorithm",
            "profile",
            "claim",
            "configuration",
            "versions",
            "plan",
            "provenance",
            "trust_boundary",
        },
    )
    if _text("schema", plan_doc["schema"]) != PLAN_SCHEMA:
        _fail("campaign plan schema mismatch")
    if _text("author", plan_doc["author"]) != AUTHOR:
        _fail("campaign plan author mismatch")
    if _text("algorithm", plan_doc["algorithm"]) != ALGORITHM:
        _fail("campaign algorithm mismatch")
    profile_name = _text("profile", plan_doc["profile"])
    if profile_name not in PROFILES:
        _fail(f"unknown immutable campaign profile {profile_name!r}")
    profile = PROFILES[profile_name]
    claim = _expect_keys(
        "claim",
        plan_doc["claim"],
        {
            "atom_id",
            "lean_name",
            "height",
            "expected_zero_count",
            "reciprocal_strict_upper_bound",
            "source",
        },
    )
    if claim != _profile_claim(profile):
        _fail("campaign claim does not exactly match its named profile")
    configuration = _expect_keys(
        "configuration",
        plan_doc["configuration"],
        {"precision_bits", "flint_threads", "batch_size"},
    )
    precision_bits = _int(
        "configuration.precision_bits",
        configuration["precision_bits"],
        minimum=MIN_PRECISION_BITS,
    )
    if precision_bits > MAX_PRECISION_BITS:
        _fail("configuration.precision_bits exceeds the supported maximum")
    if _int("configuration.flint_threads", configuration["flint_threads"]) != 1:
        _fail("configuration.flint_threads must equal 1")
    batch_size = _int(
        "configuration.batch_size", configuration["batch_size"], minimum=1
    )
    if batch_size > MAX_BATCH_SIZE:
        _fail("configuration.batch_size exceeds the supported maximum")
    _validate_versions(plan_doc["versions"])
    plan = _expect_keys(
        "plan",
        plan_doc["plan"],
        {
            "exact_multiplicity_count",
            "first_isolation_index",
            "last_included_index",
            "first_excluded_index",
            "total_isolation_records",
            "chunk_count",
        },
    )
    count = _int("plan.exact_multiplicity_count", plan["exact_multiplicity_count"], minimum=0)
    if count != profile.expected_zero_count:
        _fail("plan exact count differs from the profile expected count")
    if _int("plan.first_isolation_index", plan["first_isolation_index"]) != 1:
        _fail("plan must start isolation at index 1")
    if _int("plan.last_included_index", plan["last_included_index"], minimum=0) != count:
        _fail("plan last included index mismatch")
    if _int("plan.first_excluded_index", plan["first_excluded_index"], minimum=1) != count + 1:
        _fail("plan first excluded index mismatch")
    if (
        _int(
            "plan.total_isolation_records",
            plan["total_isolation_records"],
            minimum=1,
        )
        != count + 1
    ):
        _fail("plan total isolation count mismatch")
    expected_chunks = (count + 1 + batch_size - 1) // batch_size
    if _int("plan.chunk_count", plan["chunk_count"], minimum=1) != expected_chunks:
        _fail("plan chunk count mismatch")
    provenance = _expect_keys(
        "provenance",
        plan_doc["provenance"],
        {
            "flint_documentation",
            "flint_3_6_source",
            "python_flint_requirement",
            "flint_requirement",
            "adapted_source_commit",
            "implementation",
            "implementation_source_sha256",
        },
    )
    if (
        provenance["flint_documentation"] != FLINT_DOCS_URL
        or provenance["flint_3_6_source"] != FLINT_SOURCE_URL
        or provenance["python_flint_requirement"] != "python-flint==0.9.0"
        or provenance["flint_requirement"] != "FLINT==3.6.0"
        or provenance["adapted_source_commit"]
        != "667f873bcfdf3f3d7bd4f835a25ee5a9ad5e20ce"
        or provenance["implementation"] != "tg_verifier/zeta_zero_campaign.py"
    ):
        _fail("campaign provenance is not the pinned record")
    _digest(
        "provenance.implementation_source_sha256",
        provenance["implementation_source_sha256"],
    )
    trust = _expect_keys(
        "trust_boundary",
        plan_doc["trust_boundary"],
        {
            "classification",
            "flint_semantics_trusted",
            "lean_realization_proved",
            "lean_atom_discharged",
        },
    )
    if trust != {
        "classification": "external_flint_analytic_computation",
        "flint_semantics_trusted": True,
        "lean_realization_proved": False,
        "lean_atom_discharged": False,
    }:
        _fail("campaign trust boundary was altered")
    return plan_doc


def require_current_implementation(plan: dict[str, Any]) -> None:
    expected = _digest(
        "provenance.implementation_source_sha256",
        plan["provenance"]["implementation_source_sha256"],
    )
    actual = implementation_source_sha256()
    if actual != expected:
        _fail(
            "current zeta campaign implementation differs from the source "
            f"pinned by campaign.json: expected {expected}, got {actual}"
        )


def load_plan(directory: str | Path) -> tuple[dict[str, Any], bytes, str]:
    path = Path(directory) / PLAN_FILENAME
    raw = read_bounded(path, label="campaign plan")
    document = validate_plan(parse_canonical_json(raw, label="campaign plan"))
    return document, raw, sha256_bytes(raw)


def initialize_campaign(
    directory: str | Path,
    profile: CampaignProfile,
    *,
    batch_size: int = 4_096,
    precision_bits: int = 96,
    backend: ZetaBackend | None = None,
) -> dict[str, object]:
    document = create_plan(
        profile,
        batch_size=batch_size,
        precision_bits=precision_bits,
        backend=backend,
    )
    raw = canonical_json_bytes(document)
    path = Path(directory) / PLAN_FILENAME
    write_once(path, raw)
    return {
        "accepted": True,
        "classification": "external_flint_campaign_initialized",
        "campaign": str(path),
        "campaign_sha256": sha256_bytes(raw),
        "profile": profile.name,
        "exact_multiplicity_count": profile.expected_zero_count,
        "chunk_count": document["plan"]["chunk_count"],
        "lean_atom_discharged": False,
    }


def _chunk_range(plan: dict[str, Any], chunk_index: int) -> tuple[int, int]:
    chunk_index = _int("chunk_index", chunk_index, minimum=0)
    chunk_count = int(plan["plan"]["chunk_count"])
    if chunk_index >= chunk_count:
        _fail(f"chunk_index {chunk_index} is outside [0, {chunk_count})")
    batch_size = int(plan["configuration"]["batch_size"])
    total = int(plan["plan"]["total_isolation_records"])
    first = 1 + chunk_index * batch_size
    last = min(total, first + batch_size - 1)
    return first, last


def _interval_json(interval: IsolatedOrdinate) -> dict[str, object]:
    return {
        "lower": _rational_json(interval.lower),
        "upper": _rational_json(interval.upper),
    }


def _update_interval_digest(
    digest: Any, index: int, interval: IsolatedOrdinate
) -> None:
    record = (
        f"{index}:{interval.lower.numerator}/{interval.lower.denominator}:"
        f"{interval.upper.numerator}/{interval.upper.denominator}\n"
    )
    digest.update(record.encode("ascii"))


def _floor_fraction(value: Fraction) -> int:
    return value.numerator // value.denominator


def _ceil_fraction(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def q128_cell_from_interval(index: int, interval: IsolatedOrdinate) -> Q128CellRecord:
    """Round one rigorous ordinate interval into the committed Lean cell."""

    index = _int("Q128 cell index", index, minimum=1)
    if not isinstance(interval, IsolatedOrdinate):
        _fail("Q128 cell interval has the wrong type")
    if interval.lower <= 0 or interval.upper < interval.lower:
        _fail("Q128 cell interval is not positive and ordered")
    lower = _floor_fraction(interval.lower * Q128_SCALE)
    upper = _ceil_fraction(interval.upper * Q128_SCALE)
    if lower <= 0 or upper < lower:
        _fail("Q128 outward rounding produced an invalid cell")
    reciprocal_upper = _ceil_fraction(Fraction(Q128_SCALE * Q128_SCALE, lower))
    if Q128_SCALE * Q128_SCALE > reciprocal_upper * lower:
        _fail("Q128 reciprocal cross-product failed")
    return Q128CellRecord(index, lower, upper, reciprocal_upper)


def create_chunk(
    plan: dict[str, Any],
    campaign_sha256: str,
    chunk_index: int,
    previous_artifact_sha256: str,
    *,
    backend: ZetaBackend | None = None,
) -> dict[str, object]:
    """Freshly isolate one deterministic index batch with pinned FLINT."""

    plan = validate_plan(plan)
    require_current_implementation(plan)
    campaign_sha256 = _digest("campaign_sha256", campaign_sha256)
    previous_artifact_sha256 = _digest(
        "previous_artifact_sha256", previous_artifact_sha256
    )
    first, last = _chunk_range(plan, chunk_index)
    runtime = backend if backend is not None else FlintZetaBackend()
    if runtime.version_record() != plan["versions"]:
        _fail("runtime FLINT versions differ from the campaign plan")
    ordinates = runtime.isolate_ordinates(
        first,
        last - first + 1,
        int(plan["configuration"]["precision_bits"]),
    )
    if len(ordinates) != last - first + 1:
        _fail("zeta backend returned the wrong number of ordinate intervals")

    previous_upper: Fraction | None = None
    minimum_gap: Fraction | None = None
    minimum_gap_after: int | None = None
    interval_digest = hashlib.sha256()
    included_count = 0
    reciprocal_lower = Fraction(0)
    reciprocal_upper = Fraction(0)
    last_included_interval: IsolatedOrdinate | None = None
    first_excluded_interval: IsolatedOrdinate | None = None
    last_included_index = int(plan["plan"]["last_included_index"])
    first_excluded_index = int(plan["plan"]["first_excluded_index"])
    reciprocal_scale = 1 << int(plan["configuration"]["precision_bits"])
    # The finite head is small enough to retain every exact interval preimage.
    # The 3e12 campaign deliberately remains digest-only: retaining trillions
    # of rows would defeat its bounded-storage design.
    retained_intervals: list[dict[str, object]] | None = (
        [] if plan["profile"] == PLATT_HEAD_2E4.name else None
    )

    for offset, interval in enumerate(ordinates):
        index = first + offset
        if not isinstance(interval, IsolatedOrdinate):
            _fail(f"backend record {index} has the wrong type")
        if interval.lower <= 0 or interval.upper < interval.lower:
            _fail(f"backend record {index} is not a positive ordered interval")
        if previous_upper is not None:
            if not previous_upper < interval.lower:
                _fail(f"ordinate intervals {index - 1} and {index} overlap")
            gap = interval.lower - previous_upper
            if minimum_gap is None or gap < minimum_gap:
                minimum_gap = gap
                minimum_gap_after = index - 1
        _update_interval_digest(interval_digest, index, interval)
        if retained_intervals is not None:
            retained_intervals.append(
                {"index": index, **_interval_json(interval)}
            )
        previous_upper = interval.upper
        if index <= last_included_index:
            included_count += 1
            reciprocal_lower += Fraction(
                _floor_fraction(Fraction(reciprocal_scale, 1) / interval.upper),
                reciprocal_scale,
            )
            reciprocal_upper += Fraction(
                _ceil_fraction(Fraction(reciprocal_scale, 1) / interval.lower),
                reciprocal_scale,
            )
            if index == last_included_index:
                last_included_interval = interval
        if index == first_excluded_index:
            first_excluded_interval = interval

    return {
        "schema": CHUNK_SCHEMA,
        "author": AUTHOR,
        "algorithm": ALGORITHM,
        "profile": plan["profile"],
        "campaign_sha256": campaign_sha256,
        "previous_artifact_sha256": previous_artifact_sha256,
        "chunk_index": chunk_index,
        "first_index": first,
        "last_index": last,
        "record_count": len(ordinates),
        "first_ordinate": _interval_json(ordinates[0]),
        "last_ordinate": _interval_json(ordinates[-1]),
        "last_included_ordinate": (
            None
            if last_included_interval is None
            else _interval_json(last_included_interval)
        ),
        "first_excluded_ordinate": (
            None
            if first_excluded_interval is None
            else _interval_json(first_excluded_interval)
        ),
        "ordinate_intervals_sha256": interval_digest.hexdigest(),
        "retained_ordinate_intervals": retained_intervals,
        "all_records_finite": True,
        "all_real_parts_exactly_one_half": True,
        "all_ordinates_strictly_positive": True,
        "all_consecutive_intervals_strictly_disjoint": True,
        "minimum_internal_gap": (
            None if minimum_gap is None else _rational_json(minimum_gap)
        ),
        "minimum_internal_gap_after_index": minimum_gap_after,
        "reciprocal_sum": {
            "included_terms": included_count,
            "lower": _rational_json(reciprocal_lower),
            "upper": _rational_json(reciprocal_upper),
            "derivation": (
                "per-term outward floor/ceil at denominator 2^precision_bits: "
                "floor(2^p/ordinate_upper)/2^p <= 1/gamma <= "
                "ceil(2^p/ordinate_lower)/2^p"
            ),
        },
        "trust_boundary": {
            "fresh_flint_replay_performed": True,
            "flint_semantics_trusted": True,
            "lean_realization_proved": False,
            "lean_atom_discharged": False,
        },
    }


def _parse_interval(name: str, value: object) -> IsolatedOrdinate:
    document = _expect_keys(name, value, {"lower", "upper"})
    lower = _rational(f"{name}.lower", document["lower"])
    upper = _rational(f"{name}.upper", document["upper"])
    if lower <= 0 or upper < lower:
        _fail(f"{name} is not a positive ordered interval")
    return IsolatedOrdinate(lower, upper)


@dataclass(frozen=True)
class ValidatedChunk:
    document: dict[str, Any]
    raw: bytes
    sha256: str
    first: IsolatedOrdinate
    last: IsolatedOrdinate
    last_included: IsolatedOrdinate | None
    first_excluded: IsolatedOrdinate | None
    reciprocal_lower: Fraction
    reciprocal_upper: Fraction
    included_terms: int


@dataclass(frozen=True)
class ChunkScan:
    """Constant-memory aggregate of one validated contiguous chunk prefix."""

    chunks_complete: int
    chain_tip_sha256: str
    included_terms: int
    reciprocal_lower: Fraction
    reciprocal_upper: Fraction
    last_included: IsolatedOrdinate | None
    first_excluded: IsolatedOrdinate | None
    selected_chunk: ValidatedChunk | None
    selected_previous_sha256: str | None


def validate_chunk(
    document: object,
    raw: bytes,
    plan: dict[str, Any],
    campaign_sha256: str,
    chunk_index: int,
    previous_artifact_sha256: str,
) -> ValidatedChunk:
    plan = validate_plan(plan)
    chunk = _expect_keys(
        f"chunk {chunk_index}",
        document,
        {
            "schema",
            "author",
            "algorithm",
            "profile",
            "campaign_sha256",
            "previous_artifact_sha256",
            "chunk_index",
            "first_index",
            "last_index",
            "record_count",
            "first_ordinate",
            "last_ordinate",
            "last_included_ordinate",
            "first_excluded_ordinate",
            "ordinate_intervals_sha256",
            "retained_ordinate_intervals",
            "all_records_finite",
            "all_real_parts_exactly_one_half",
            "all_ordinates_strictly_positive",
            "all_consecutive_intervals_strictly_disjoint",
            "minimum_internal_gap",
            "minimum_internal_gap_after_index",
            "reciprocal_sum",
            "trust_boundary",
        },
    )
    if _text("chunk.schema", chunk["schema"]) != CHUNK_SCHEMA:
        _fail(f"chunk {chunk_index} schema mismatch")
    if _text("chunk.author", chunk["author"]) != AUTHOR:
        _fail(f"chunk {chunk_index} author mismatch")
    if _text("chunk.algorithm", chunk["algorithm"]) != ALGORITHM:
        _fail(f"chunk {chunk_index} algorithm mismatch")
    if _text("chunk.profile", chunk["profile"]) != plan["profile"]:
        _fail(f"chunk {chunk_index} profile mismatch")
    if _digest("chunk.campaign_sha256", chunk["campaign_sha256"]) != campaign_sha256:
        _fail(f"chunk {chunk_index} campaign hash mismatch")
    if (
        _digest("chunk.previous_artifact_sha256", chunk["previous_artifact_sha256"])
        != previous_artifact_sha256
    ):
        _fail(f"chunk {chunk_index} predecessor hash mismatch")
    if _int("chunk.chunk_index", chunk["chunk_index"], minimum=0) != chunk_index:
        _fail(f"chunk {chunk_index} stores the wrong index")
    first_index, last_index = _chunk_range(plan, chunk_index)
    if _int("chunk.first_index", chunk["first_index"], minimum=1) != first_index:
        _fail(f"chunk {chunk_index} first index mismatch")
    if _int("chunk.last_index", chunk["last_index"], minimum=1) != last_index:
        _fail(f"chunk {chunk_index} last index mismatch")
    count = last_index - first_index + 1
    if _int("chunk.record_count", chunk["record_count"], minimum=1) != count:
        _fail(f"chunk {chunk_index} record count mismatch")
    first = _parse_interval("chunk.first_ordinate", chunk["first_ordinate"])
    last = _parse_interval("chunk.last_ordinate", chunk["last_ordinate"])
    last_included = (
        None
        if chunk["last_included_ordinate"] is None
        else _parse_interval(
            "chunk.last_included_ordinate", chunk["last_included_ordinate"]
        )
    )
    first_excluded = (
        None
        if chunk["first_excluded_ordinate"] is None
        else _parse_interval(
            "chunk.first_excluded_ordinate", chunk["first_excluded_ordinate"]
        )
    )
    interval_digest = _digest(
        "chunk.ordinate_intervals_sha256", chunk["ordinate_intervals_sha256"]
    )
    retained = chunk["retained_ordinate_intervals"]
    if plan["profile"] == PLATT_HEAD_2E4.name:
        if not isinstance(retained, list) or len(retained) != count:
            _fail(f"chunk {chunk_index} must retain every Platt-head interval")
        replay_digest = hashlib.sha256()
        replay_previous: Fraction | None = None
        replay_minimum_gap: Fraction | None = None
        replay_minimum_after: int | None = None
        replay_intervals: list[IsolatedOrdinate] = []
        for offset, raw_row in enumerate(retained):
            row = _expect_keys(
                f"chunk {chunk_index}.retained[{offset}]",
                raw_row,
                {"index", "lower", "upper"},
            )
            expected_index = first_index + offset
            if _int(
                f"chunk {chunk_index}.retained[{offset}].index",
                row["index"],
                minimum=1,
            ) != expected_index:
                _fail(f"chunk {chunk_index} retained interval index mismatch")
            interval = _parse_interval(
                f"chunk {chunk_index}.retained[{offset}]",
                {"lower": row["lower"], "upper": row["upper"]},
            )
            if replay_previous is not None:
                if not replay_previous < interval.lower:
                    _fail(f"chunk {chunk_index} retained intervals overlap")
                gap = interval.lower - replay_previous
                if replay_minimum_gap is None or gap < replay_minimum_gap:
                    replay_minimum_gap = gap
                    replay_minimum_after = expected_index - 1
            replay_previous = interval.upper
            replay_intervals.append(interval)
            _update_interval_digest(replay_digest, expected_index, interval)
        if replay_digest.hexdigest() != interval_digest:
            _fail(f"chunk {chunk_index} retained interval digest mismatch")
        if replay_intervals[0] != first or replay_intervals[-1] != last:
            _fail(f"chunk {chunk_index} retained endpoints mismatch")
    elif retained is not None:
        _fail("the source-height campaign must not retain trillions of intervals")
    for key in (
        "all_records_finite",
        "all_real_parts_exactly_one_half",
        "all_ordinates_strictly_positive",
        "all_consecutive_intervals_strictly_disjoint",
    ):
        if not _bool(f"chunk.{key}", chunk[key]):
            _fail(f"chunk {chunk_index} does not certify {key}")
    minimum_gap = _optional_rational("chunk.minimum_internal_gap", chunk["minimum_internal_gap"])
    minimum_after = chunk["minimum_internal_gap_after_index"]
    if count == 1:
        if minimum_gap is not None or minimum_after is not None:
            _fail(f"singleton chunk {chunk_index} must not store an internal gap")
    else:
        if minimum_gap is None or minimum_gap <= 0:
            _fail(f"chunk {chunk_index} must store a positive internal gap")
        after = _int("chunk.minimum_internal_gap_after_index", minimum_after, minimum=first_index)
        if after >= last_index:
            _fail(f"chunk {chunk_index} minimum-gap index is out of range")
        if plan["profile"] == PLATT_HEAD_2E4.name and (
            minimum_gap != replay_minimum_gap or after != replay_minimum_after
        ):
            _fail(f"chunk {chunk_index} retained minimum-gap summary mismatch")
    expected_last_included_present = (
        first_index <= int(plan["plan"]["last_included_index"]) <= last_index
    )
    expected_first_excluded_present = (
        first_index <= int(plan["plan"]["first_excluded_index"]) <= last_index
    )
    if (last_included is not None) != expected_last_included_present:
        _fail(f"chunk {chunk_index} last-included marker presence mismatch")
    if (first_excluded is not None) != expected_first_excluded_present:
        _fail(f"chunk {chunk_index} first-excluded marker presence mismatch")
    if expected_first_excluded_present and first_excluded != last:
        _fail("the first excluded zero must be the campaign's final interval")
    reciprocal = _expect_keys(
        "chunk.reciprocal_sum",
        chunk["reciprocal_sum"],
        {"included_terms", "lower", "upper", "derivation"},
    )
    included_terms = _int(
        "chunk.reciprocal_sum.included_terms", reciprocal["included_terms"], minimum=0
    )
    expected_included = max(
        0, min(last_index, int(plan["plan"]["last_included_index"])) - first_index + 1
    )
    if included_terms != expected_included:
        _fail(f"chunk {chunk_index} included reciprocal term count mismatch")
    reciprocal_lower = _rational("chunk.reciprocal_sum.lower", reciprocal["lower"])
    reciprocal_upper = _rational("chunk.reciprocal_sum.upper", reciprocal["upper"])
    if reciprocal_lower < 0 or reciprocal_upper < reciprocal_lower:
        _fail(f"chunk {chunk_index} has an invalid reciprocal enclosure")
    if _text("chunk.reciprocal_sum.derivation", reciprocal["derivation"]) != (
        "per-term outward floor/ceil at denominator 2^precision_bits: "
        "floor(2^p/ordinate_upper)/2^p <= 1/gamma <= "
        "ceil(2^p/ordinate_lower)/2^p"
    ):
        _fail(f"chunk {chunk_index} reciprocal derivation mismatch")
    trust = _expect_keys(
        "chunk.trust_boundary",
        chunk["trust_boundary"],
        {
            "fresh_flint_replay_performed",
            "flint_semantics_trusted",
            "lean_realization_proved",
            "lean_atom_discharged",
        },
    )
    if trust != {
        "fresh_flint_replay_performed": True,
        "flint_semantics_trusted": True,
        "lean_realization_proved": False,
        "lean_atom_discharged": False,
    }:
        _fail(f"chunk {chunk_index} trust boundary was altered")
    return ValidatedChunk(
        document=chunk,
        raw=raw,
        sha256=sha256_bytes(raw),
        first=first,
        last=last,
        last_included=last_included,
        first_excluded=first_excluded,
        reciprocal_lower=reciprocal_lower,
        reciprocal_upper=reciprocal_upper,
        included_terms=included_terms,
    )


def _discover_chunk_prefix(
    directory: Path, chunk_count: int, *, allow_prefix: bool
) -> int:
    """Validate chunk filenames and return the prefix length in O(1) memory."""

    actual_count = 0
    minimum_index: int | None = None
    maximum_index: int | None = None
    try:
        entries = os.scandir(directory)
    except OSError as error:
        raise ZetaCampaignError(f"cannot scan campaign directory {directory}: {error}") from error
    with entries:
        for entry in entries:
            name = entry.name
            if not name.startswith(CHUNK_PREFIX) or not name.endswith(".json"):
                continue
            if not entry.is_file():
                continue
            suffix = name[len(CHUNK_PREFIX) : -len(".json")]
            if not suffix.isascii() or not suffix.isdigit():
                _fail(f"campaign contains malformed chunk filename {name!r}")
            index = int(suffix)
            if name != chunk_filename(index) or index >= chunk_count:
                _fail(f"campaign contains out-of-range chunk filename {name!r}")
            actual_count += 1
            minimum_index = index if minimum_index is None else min(minimum_index, index)
            maximum_index = index if maximum_index is None else max(maximum_index, index)
    if actual_count:
        # Canonical filenames are injective. Therefore count k, minimum zero,
        # and maximum k-1 prove that every index in the prefix is present.
        if minimum_index != 0 or maximum_index != actual_count - 1:
            _fail("campaign chunk files are not one contiguous prefix")
    if not allow_prefix and actual_count != chunk_count:
        _fail(f"campaign has {actual_count} of {chunk_count} required chunks")
    return actual_count


def scan_validated_chunks(
    directory: str | Path,
    plan: dict[str, Any],
    campaign_sha256: str,
    *,
    allow_prefix: bool,
    selected_index: int | None = None,
) -> ChunkScan:
    """Validate and aggregate a chain without retaining all chunk documents."""

    root = Path(directory)
    chunk_count = int(plan["plan"]["chunk_count"])
    prefix_length = _discover_chunk_prefix(
        root, chunk_count, allow_prefix=allow_prefix
    )
    if selected_index is not None:
        selected_index = _int("selected_index", selected_index, minimum=0)
        if selected_index >= prefix_length:
            _fail(f"retained chunk {selected_index} is absent or follows a chain gap")
    previous_hash = campaign_sha256
    previous_last: IsolatedOrdinate | None = None
    included_terms = 0
    reciprocal_lower = Fraction(0)
    reciprocal_upper = Fraction(0)
    last_included: IsolatedOrdinate | None = None
    first_excluded: IsolatedOrdinate | None = None
    selected_chunk: ValidatedChunk | None = None
    selected_previous: str | None = None
    for index in range(prefix_length):
        path = root / chunk_filename(index)
        raw = read_bounded(path, label=f"chunk {index}")
        document = parse_canonical_json(raw, label=f"chunk {index}")
        chunk = validate_chunk(
            document, raw, plan, campaign_sha256, index, previous_hash
        )
        if previous_last is not None and not previous_last.upper < chunk.first.lower:
            _fail(f"chunk boundary {index - 1}/{index} is not strictly disjoint")
        included_terms += chunk.included_terms
        reciprocal_lower += chunk.reciprocal_lower
        reciprocal_upper += chunk.reciprocal_upper
        if chunk.last_included is not None:
            if last_included is not None:
                _fail("campaign contains multiple last-included markers")
            last_included = chunk.last_included
        if chunk.first_excluded is not None:
            if first_excluded is not None:
                _fail("campaign contains multiple first-excluded markers")
            first_excluded = chunk.first_excluded
        if index == selected_index:
            selected_chunk = chunk
            selected_previous = previous_hash
        previous_last = chunk.last
        previous_hash = chunk.sha256
    return ChunkScan(
        chunks_complete=prefix_length,
        chain_tip_sha256=previous_hash,
        included_terms=included_terms,
        reciprocal_lower=reciprocal_lower,
        reciprocal_upper=reciprocal_upper,
        last_included=last_included,
        first_excluded=first_excluded,
        selected_chunk=selected_chunk,
        selected_previous_sha256=selected_previous,
    )


def replay_plan_count(
    plan: dict[str, Any], *, backend: ZetaBackend | None = None
) -> int:
    plan = validate_plan(plan)
    require_current_implementation(plan)
    runtime = backend if backend is not None else FlintZetaBackend()
    if runtime.version_record() != plan["versions"]:
        _fail("runtime FLINT versions differ from the campaign plan")
    count = runtime.exact_zero_count(
        int(plan["claim"]["height"]),
        int(plan["configuration"]["precision_bits"]),
    )
    if count != int(plan["plan"]["exact_multiplicity_count"]):
        _fail("fresh zeta_nzeros result differs from the immutable campaign plan")
    return count


def replay_chunk(
    directory: str | Path,
    chunk_index: int,
    *,
    backend: ZetaBackend | None = None,
) -> dict[str, object]:
    """Freshly recompute a retained chunk and require byte-for-byte equality."""

    root = Path(directory)
    plan, _plan_raw, campaign_hash = load_plan(root)
    chunk_index = _int("chunk_index", chunk_index, minimum=0)
    scan = scan_validated_chunks(
        root,
        plan,
        campaign_hash,
        allow_prefix=True,
        selected_index=chunk_index,
    )
    retained = scan.selected_chunk
    previous_hash = scan.selected_previous_sha256
    if retained is None or previous_hash is None:
        _fail("internal selected-chunk scan did not retain the requested chunk")
    fresh = create_chunk(
        plan,
        campaign_hash,
        chunk_index,
        previous_hash,
        backend=backend,
    )
    fresh_raw = canonical_json_bytes(fresh)
    if fresh_raw != retained.raw:
        _fail(f"fresh FLINT replay differs from retained chunk {chunk_index}")
    return {
        "accepted": True,
        "classification": "fresh_external_flint_chunk_replay",
        "profile": plan["profile"],
        "chunk_index": chunk_index,
        "chunk_sha256": sha256_bytes(fresh_raw),
        "records_recomputed": fresh["record_count"],
        "lean_atom_discharged": False,
    }


def run_campaign(
    directory: str | Path,
    *,
    max_chunks: int | None = None,
    replay_count: bool = True,
    backend: ZetaBackend | None = None,
) -> dict[str, object]:
    """Resume a prefix campaign, atomically committing each completed batch."""

    root = Path(directory)
    plan, _plan_raw, campaign_hash = load_plan(root)
    runtime = backend if backend is not None else FlintZetaBackend()
    if replay_count:
        replay_plan_count(plan, backend=runtime)
    existing = scan_validated_chunks(
        root, plan, campaign_hash, allow_prefix=True
    )
    chunk_count = int(plan["plan"]["chunk_count"])
    remaining = chunk_count - existing.chunks_complete
    if max_chunks is None:
        to_run = remaining
    else:
        max_chunks = _int("max_chunks", max_chunks, minimum=0)
        to_run = min(remaining, max_chunks)
    previous_hash = existing.chain_tip_sha256
    completed = existing.chunks_complete
    for chunk_index in range(completed, completed + to_run):
        chunk = create_chunk(
            plan,
            campaign_hash,
            chunk_index,
            previous_hash,
            backend=runtime,
        )
        raw = canonical_json_bytes(chunk)
        write_once(root / chunk_filename(chunk_index), raw)
        previous_hash = sha256_bytes(raw)
    completed += to_run
    return {
        "accepted": True,
        "classification": (
            "complete_external_flint_campaign_ready_to_finalize"
            if completed == chunk_count
            else "partial_resumable_external_flint_campaign"
        ),
        "profile": plan["profile"],
        "exact_count_replayed": replay_count,
        "chunks_present_before_run": existing.chunks_complete,
        "chunks_computed_this_run": to_run,
        "chunks_complete": completed,
        "chunks_total": chunk_count,
        "chain_tip_sha256": previous_hash,
        "complete": completed == chunk_count,
        "lean_atom_discharged": False,
    }


def _final_document(
    plan: dict[str, Any], campaign_hash: str, scan: ChunkScan
) -> dict[str, object]:
    count = int(plan["plan"]["exact_multiplicity_count"])
    height = int(plan["claim"]["height"])
    if scan.chunks_complete != int(plan["plan"]["chunk_count"]):
        _fail("cannot finalize an incomplete campaign")
    included_terms = scan.included_terms
    if included_terms != count:
        _fail("campaign reciprocal term coverage differs from the exact count")
    if count == 0:
        if scan.last_included is not None:
            _fail("zero-count campaign unexpectedly has a last included ordinate")
        last_included = None
    else:
        if scan.last_included is None:
            _fail("campaign must contain exactly one last-included marker")
        last_included = scan.last_included
        if last_included.upper > height:
            _fail("last included zero is not certified at or below the height")
    if scan.first_excluded is None:
        _fail("campaign must contain exactly one first-excluded marker")
    first_excluded = scan.first_excluded
    if first_excluded.lower <= height:
        _fail("first excluded zero is not certified strictly above the height")

    reciprocal_lower = scan.reciprocal_lower
    reciprocal_upper = scan.reciprocal_upper
    target = _optional_rational(
        "claim.reciprocal_strict_upper_bound",
        plan["claim"]["reciprocal_strict_upper_bound"],
    )
    target_proved: bool | None
    margin: Fraction | None
    if target is None:
        target_proved = None
        margin = None
    else:
        target_proved = reciprocal_upper < target
        if not target_proved:
            _fail("global reciprocal upper endpoint does not satisfy the profile bound")
        margin = target - reciprocal_upper

    return {
        "schema": FINAL_SCHEMA,
        "author": AUTHOR,
        "algorithm": ALGORITHM,
        "profile": plan["profile"],
        "campaign_sha256": campaign_hash,
        "chunk_count": scan.chunks_complete,
        "chain_tip_sha256": scan.chain_tip_sha256,
        "claim": plan["claim"],
        "result": {
            "exact_multiplicity_count": count,
            "isolated_critical_line_records_below_height": count,
            "extra_bracketing_record_index": count + 1,
            "all_real_parts_exactly_one_half": True,
            "all_ordinate_intervals_strictly_positive_and_disjoint": True,
            "last_included_ordinate": (
                None if last_included is None else _interval_json(last_included)
            ),
            "last_included_upper_at_most_height": count == 0 or last_included is not None,
            "first_excluded_ordinate": _interval_json(first_excluded),
            "height_strictly_below_first_excluded_lower": True,
            "all_zeros_through_height_on_critical_line": True,
            "all_included_zeros_simple": True,
            "reciprocal_sum": {
                "terms": included_terms,
                "lower": _rational_json(reciprocal_lower),
                "upper": _rational_json(reciprocal_upper),
                "strict_target": (
                    None if target is None else _rational_json(target)
                ),
                "strict_target_proved": target_proved,
                "certified_margin_lower": (
                    None if margin is None else _rational_json(margin)
                ),
            },
        },
        "completeness_and_multiplicity_argument": (
            "arb.zeta_nzeros(height) gives the exact number N of all nontrivial "
            "zeros with 0 < Im(rho) <= height, counted with multiplicity. The N "
            "strictly disjoint critical-line isolations below the cutoff account "
            "for at least N multiplicity units. Equality forces each isolation "
            "to have multiplicity one and leaves no additional on-line or off-line "
            "zero below the cutoff. Isolation N+1 lies strictly above the cutoff."
        ),
        "trust_boundary": {
            "classification": "retained_complete_external_flint_analytic_evidence",
            "structural_final_verifier_recomputes_flint": False,
            "each_chunk_has_fresh_replay_command": True,
            "flint_semantics_trusted": True,
            "lean_realization_proved": False,
            "lean_atom_discharged": False,
        },
    }


def finalize_campaign(directory: str | Path) -> dict[str, object]:
    root = Path(directory)
    plan, _plan_raw, campaign_hash = load_plan(root)
    scan = scan_validated_chunks(root, plan, campaign_hash, allow_prefix=False)
    final = _final_document(plan, campaign_hash, scan)
    raw = canonical_json_bytes(final)
    write_once(root / FINAL_FILENAME, raw)
    return {
        "accepted": True,
        "classification": "complete_external_artifact_finalized_not_fresh_flint_replay",
        "profile": plan["profile"],
        "final_sha256": sha256_bytes(raw),
        "exact_multiplicity_count": plan["plan"]["exact_multiplicity_count"],
        "chunks": scan.chunks_complete,
        "all_zeros_through_height_on_critical_line": True,
        "lean_atom_discharged": False,
    }


def verify_campaign(
    directory: str | Path, *, require_complete: bool = False
) -> dict[str, object]:
    """Structurally verify a partial prefix or a completed external campaign."""

    root = Path(directory)
    plan, _plan_raw, campaign_hash = load_plan(root)
    scan = scan_validated_chunks(
        root, plan, campaign_hash, allow_prefix=not require_complete
    )
    chunk_count = int(plan["plan"]["chunk_count"])
    complete = scan.chunks_complete == chunk_count
    final_path = root / FINAL_FILENAME
    final_present = final_path.exists()
    final_sha: str | None = None
    if final_present:
        if not complete:
            _fail("final artifact exists for an incomplete campaign")
        retained_raw = read_bounded(final_path, label="final artifact")
        retained = parse_canonical_json(retained_raw, label="final artifact")
        expected = _final_document(plan, campaign_hash, scan)
        if retained != expected:
            _fail("final artifact does not match the checked campaign chain")
        final_sha = sha256_bytes(retained_raw)
    elif require_complete:
        _fail("complete verification requires final.json")
    return {
        "accepted": True,
        "classification": (
            "complete_external_artifact_structure_not_fresh_flint_replay"
            if final_present
            else "partial_external_artifact_structure_not_fresh_flint_replay"
        ),
        "profile": plan["profile"],
        "campaign_sha256": campaign_hash,
        "chunks_complete": scan.chunks_complete,
        "chunks_total": chunk_count,
        "complete_chain": complete,
        "final_present": final_present,
        "final_sha256": final_sha,
        "fresh_flint_replay_performed": False,
        "lean_atom_discharged": False,
    }


def retained_head_q128_cells(directory: str | Path) -> tuple[Q128CellRecord, ...]:
    """Load every retained head interval and reproduce the committed Q128 rows.

    This function first performs the complete structural/final verification.
    It then replays each retained rational preimage, rounds outward exactly,
    and requires the historical 22,491-row digest.  A summary-only chunk can
    therefore no longer be used to generate a Lean table.
    """

    root = Path(directory)
    plan, _raw, _campaign_hash = load_plan(root)
    if plan["profile"] != PLATT_HEAD_2E4.name:
        _fail("Q128 table extraction is defined only for platt-head-2e4")
    verify_campaign(root, require_complete=True)
    expected_count = int(plan["plan"]["last_included_index"])
    expected_all_count = int(plan["plan"]["total_isolation_records"])
    all_cells: list[Q128CellRecord] = []
    previous_upper = 0
    for chunk_index in range(int(plan["plan"]["chunk_count"])):
        raw = read_bounded(root / chunk_filename(chunk_index), label=f"chunk {chunk_index}")
        chunk = parse_canonical_json(raw, label=f"chunk {chunk_index}")
        retained = chunk.get("retained_ordinate_intervals")
        if not isinstance(retained, list):
            _fail(f"chunk {chunk_index} has no retained interval preimages")
        for offset, raw_row in enumerate(retained):
            row = _expect_keys(
                f"chunk {chunk_index}.retained[{offset}]",
                raw_row,
                {"index", "lower", "upper"},
            )
            index = _int("retained interval index", row["index"], minimum=1)
            interval = _parse_interval(
                f"retained interval {index}",
                {"lower": row["lower"], "upper": row["upper"]},
            )
            cell = q128_cell_from_interval(index, interval)
            if cell.index != len(all_cells) + 1:
                _fail("retained Q128 rows are not a gap-free one-based prefix")
            if cell.lower <= previous_upper:
                _fail("retained Q128 rows overlap after outward rounding")
            previous_upper = cell.upper
            all_cells.append(cell)
    if len(all_cells) != expected_all_count:
        _fail(
            f"retained Q128 campaign has {len(all_cells)} rows, "
            f"expected {expected_all_count} including the sentinel"
        )
    all_digest = hashlib.sha256()
    for cell in all_cells:
        all_digest.update(
            (
                f"{cell.index}:{cell.lower}:{cell.upper}:"
                f"{cell.reciprocal_upper}\n"
            ).encode("ascii")
        )
    if all_digest.hexdigest() != PLATT_HEAD_ALL_Q128_ROWS_SHA256:
        _fail(
            "retained Q128 rows including the sentinel differ from the reviewed "
            f"claude_math table: expected {PLATT_HEAD_ALL_Q128_ROWS_SHA256}, "
            f"got {all_digest.hexdigest()}"
        )
    cells = all_cells[:expected_count]
    included_digest = hashlib.sha256()
    for cell in cells:
        included_digest.update(
            (
                f"{cell.index}:{cell.lower}:{cell.upper}:"
                f"{cell.reciprocal_upper}\n"
            ).encode("ascii")
        )
    if included_digest.hexdigest() != PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256:
        _fail(
            "retained included Q128 source table differs from claude_math: "
            f"expected {PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256}, "
            f"got {included_digest.hexdigest()}"
        )
    return tuple(cells)


def render_head_q128_lean_module(
    cells: Sequence[Q128CellRecord],
    *,
    namespace: str = "SparkInterval.Generated.PlattHeadQ128",
) -> str:
    """Render one exact table module for compilation in the shared Lake graph.

    The renderer accepts only the complete reviewed table.  The generated
    module defines no axiom; it supplies literal rows, a kernel-checked length,
    and the `Q128CellTable` consumed by the registered receipt theorem.
    """

    if re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", namespace
    ) is None:
        _fail("generated Lean namespace is malformed")
    if len(cells) != PLATT_HEAD_2E4.expected_zero_count:
        _fail("Lean rendering requires the complete 22,491-row table")
    digest = hashlib.sha256()
    previous_upper = 0
    row_lines: list[str] = []
    for expected_index, cell in enumerate(cells, start=1):
        if not isinstance(cell, Q128CellRecord) or cell.index != expected_index:
            _fail("Lean Q128 rows are not canonical and one-based")
        if cell.lower <= previous_upper or cell.upper < cell.lower:
            _fail("Lean Q128 rows are not positive, ordered, and disjoint")
        if Q128_SCALE * Q128_SCALE > cell.reciprocal_upper * cell.lower:
            _fail("Lean Q128 row fails its reciprocal cross-product")
        previous_upper = cell.upper
        record = (
            f"{cell.index}:{cell.lower}:{cell.upper}:"
            f"{cell.reciprocal_upper}\n"
        )
        digest.update(record.encode("ascii"))
        row_lines.append(
            f"    ⟨{cell.lower}, {cell.upper}, {cell.reciprocal_upper}⟩"
        )
    if digest.hexdigest() != PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256:
        _fail("Lean Q128 renderer received a table with the wrong digest")
    rows = ",\n".join(row_lines)
    return f'''/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

/-! Generated exact Q128 cells for the Platt zeta head through height 20,000.
Do not edit by hand; regenerate from a complete retained and replayed campaign. -/

namespace {namespace}

open SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

set_option maxHeartbeats 0 in
set_option maxRecDepth 1000000 in
def rows : List Q128Cell :=
  [
{rows}
  ]

set_option maxRecDepth 1000000 in
@[simp] theorem rows_length : rows.length = sourceCount := by decide

noncomputable def table : Q128CellTable where
  entries i := rows.get (finCongr rows_length.symm i)

def reviewedRowsSha256 : String :=
  "{PLATT_HEAD_INCLUDED_Q128_ROWS_SHA256}"

end {namespace}
'''
