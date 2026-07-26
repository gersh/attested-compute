# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed checks for retained external finite-computation evidence.

These checks validate exact fields, hashes, and arithmetic in imported
artifacts.  They intentionally do not claim that an external executable
realizes a Mathlib analytic definition or that a physical GPU ran.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """An evidence artifact is malformed or fails its exact contract."""


@dataclass(frozen=True)
class EvidenceCheck:
    atom_id: str
    accepted: bool
    classification: str
    checks: tuple[str, ...]
    metrics: dict[str, str | int]
    proves_lean_claim: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "accepted": self.accepted,
            "classification": self.classification,
            "checks": list(self.checks),
            "metrics": dict(self.metrics),
            "proves_lean_claim": self.proves_lean_claim,
        }


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise EvidenceError(f"non-finite JSON number is forbidden: {token}")


def load_decimal_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    """Parse one captured byte string with exact decimal tokens."""

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_float=Decimal,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, InvalidOperation) as exc:
        raise EvidenceError(f"cannot parse {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("artifact root must be a JSON object")
    return value


def read_artifact_bytes(path: Path) -> bytes:
    """Capture an artifact exactly once for identity and semantic checks."""

    try:
        return path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"cannot read {path}: {exc}") from exc


def load_decimal_json(path: Path) -> dict[str, Any]:
    """Parse one file read with exact decimals and duplicate-key rejection."""

    return load_decimal_json_bytes(read_artifact_bytes(path), label=str(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


RAMARE_RETAINED_FOCUSED_SHA256 = (
    "cc4ec7e3f570fce2900c33e87d921039fea9abb4c8551b7bdda52e9a110d042f"
)
RAMARE_RETAINED_RAW_SHA256 = (
    "35201cf14ed7c01dea38deb053a8d1266712b40a6629e33112b373bef966a383"
)


def verify_ramare_zuniga_report(
    focused_path: Path,
    raw_report_path: Path | None = None,
    *,
    expected_focused_sha256: str | None = None,
    expected_raw_sha256: str | None = None,
) -> EvidenceCheck:
    """Check exact fields and identity of an R2Star summary artifact.

    The report's ``PASS`` labels and claimed extremum remain producer output;
    this function does not replay the 21-billion-step stream.  Supplying the
    expected hashes pins an audited artifact but does not change that semantic
    boundary.
    """

    focused_raw = read_artifact_bytes(focused_path)
    focused_sha256 = hashlib.sha256(focused_raw).hexdigest()
    if expected_focused_sha256 is not None:
        _require(
            SHA256_RE.fullmatch(expected_focused_sha256) is not None,
            "invalid expected focused-report digest",
        )
        _require(
            focused_sha256 == expected_focused_sha256,
            "focused R2Star report SHA-256 mismatch",
        )

    value = load_decimal_json_bytes(focused_raw, label=str(focused_path))
    _require(value.get("status") == "PASS", "focused R2Star status is not PASS")
    scope = value.get("finite_sweep")
    _require(isinstance(scope, dict), "missing finite_sweep object")
    r2 = scope.get("R2star_sqrt_log")
    _require(isinstance(r2, dict), "missing R2Star scoped result")
    _require(scope.get("limit") == 21_000_000_000, "wrong sweep limit")
    _require(r2.get("intended_full_range_end") == 21_000_000_000, "wrong endpoint")
    _require(r2.get("real_range_start") == 3, "wrong lower endpoint")
    _require(r2.get("status") == "PASS", "scoped R2Star status is not PASS")
    _require(r2.get("last_bad_integer") is None, "R2Star report records a failure")
    worst = r2.get("worst_ratio_abs_R2_over_sqrt_n_log_n")
    _require(isinstance(worst, dict), "missing R2Star worst-value record")
    worst_value = worst.get("value")
    budget = r2.get("float64_outward_error_budget_at_worst")
    bound = r2.get("bound")
    _require(
        isinstance(worst_value, Decimal)
        and isinstance(budget, Decimal)
        and isinstance(bound, Decimal),
        "R2Star decimal fields must be JSON decimals",
    )
    _require(bound == Decimal("1.93"), "wrong R2Star source bound")
    worst_n = worst.get("n")
    _require(
        not isinstance(worst_n, bool)
        and isinstance(worst_n, int)
        and 3 <= worst_n <= 21_000_000_000,
        "R2Star worst-value index is outside the source range",
    )
    _require(worst_value >= 0 and budget >= 0, "negative R2Star value or budget")
    certified = worst_value + budget
    _require(certified < bound, "R2Star outward upper bound does not close")

    reported_certified = value.get("certified_worst_ratio_upper_bound")
    _require(isinstance(reported_certified, str), "missing certified decimal string")
    _require(
        Decimal(reported_certified) == certified,
        "reported certified bound differs from exact decimal addition",
    )
    recorded_raw_hash = value.get("source_report_sha256")
    _require(
        isinstance(recorded_raw_hash, str) and SHA256_RE.fullmatch(recorded_raw_hash),
        "invalid raw-report digest",
    )
    checks = [
        "exact full endpoint",
        "stored PASS and no-bad-integer fields present",
        "stored decimal worst-plus-budget is arithmetically below 1.93",
        "well-formed raw-report digest",
    ]
    if expected_focused_sha256 is not None:
        checks.append("focused-report SHA-256 pinned")
    if raw_report_path is not None:
        actual_raw_hash = sha256_file(raw_report_path)
        _require(
            actual_raw_hash == recorded_raw_hash,
            "raw R2Star report SHA-256 mismatch",
        )
        if expected_raw_sha256 is not None:
            _require(
                SHA256_RE.fullmatch(expected_raw_sha256) is not None,
                "invalid expected raw-report digest",
            )
            _require(
                actual_raw_hash == expected_raw_sha256,
                "raw R2Star report differs from pinned artifact",
            )
        checks.append("raw-report SHA-256")

    return EvidenceCheck(
        atom_id="ramare-zuniga-lemma-6-2",
        accepted=True,
        classification=(
            "pinned_summary_identity_and_internal_arithmetic_only"
            if expected_focused_sha256 is not None
            else "summary_structure_and_internal_arithmetic_only"
        ),
        checks=tuple(checks),
        metrics={
            "range_start": 3,
            "range_end": 21_000_000_000,
            "worst_index": worst_n,
            "certified_worst_ratio_upper": str(certified),
            "elapsed_seconds_reported": str(scope.get("elapsed_seconds")),
        },
    )


CDEM_REQUIRED_FIELDS: dict[str, int] = {
    "K": 199_330,
    "N": 5_000_000_000,
    "A": 5_000_000_001,
    "MOBIUS_M": -6,
    "MOBIUS_Q": 121_174,
    "COEFF_SCALE": 10**30,
    "S_LOWER_NUM": 20_985_957_655_978_471_021_715,
    "S_UPPER_NUM": 20_985_957_655_978_471_142_885,
    "FINAL_F": 112,
    "FINAL_G": 111,
    "TOTAL_VARIATION": 1_678_512_305,
    "WEIGHT_SCALE": 10**18,
    "ENDPOINT_RSQRT_UPPER_NUM": 14_142_135_622_317,
}
CDEM_U_TARGET = 324_880_457_633_740
CDEM_V_TARGET = 48_710_223_109_607_260_068_028
CDEM_REGISTERED_RESULT = "2372685835387717172679029560108650251645442524"
CDEM_REGISTERED_RESULT_SHA256 = (
    "84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c"
)


def nat_pair(left: int, right: int) -> int:
    """Exact Python counterpart of Mathlib's injective ``Nat.pair``.

    The registered Lean bridge uses ``Nat.unpair`` to recover both directed
    numerators.  Keeping this tiny encoder beside the transcript checker makes
    the measured wrapper's compact result deterministic and independently
    testable without adding a JSON parser to the theorem boundary.
    """

    if isinstance(left, bool) or not isinstance(left, int) or left < 0:
        raise EvidenceError("Nat.pair left input must be a natural")
    if isinstance(right, bool) or not isinstance(right, int) or right < 0:
        raise EvidenceError("Nat.pair right input must be a natural")
    return right * right + left if left < right else left * left + left + right


def cdem_abel_registered_result(
    signed_numerator: int, absolute_numerator: int
) -> str:
    """Canonical newline-free result consumed by the closed Lean invocation."""

    return str(nat_pair(signed_numerator, absolute_numerator))

EXPECTED_INVENTORY_CARDS: dict[str, str] = {
    "AnalyticNT.ChebyshevPsi.finite_check_ch25_lemA7_arb_boundary_source": "ch25-lemma-a7-arb-boundary.md",
    "AnalyticNT.ChebyshevPsi.finite_check_ch25_lemma_9_2_psi_source": "ch25-lemma-9-2-psi.md",
    "AnalyticNT.ChebyshevPsi.finite_check_platt_zero_enumeration_2e4_source": "ch25-proposition-7-7-platt-head-2e4.md",
    "AnalyticNT.ChebyshevPsi.finite_check_platt_trudgian_rh_zeta_3e12": "platt-trudgian-rh-zeta-3e12.md",
    "AnalyticNT.LargeSieve.finite_check_helfgott_prop_12_2_4_computation_source": "helfgott_prop_12_2_4.md",
    "Math.Problems.TernaryGoldbach.helfgott_platt_theorem_4_1_source": "helfgott_platt_theorem_4_1.md",
    "MathExtras.CohenDressElMarraki.reproducibleSquarefree_verifier_output": "cdem-squarefree-verifier-output.md",
    "MathExtras.CohenDressElMarraki.reproducibleTable_abel_verifier_output": "cdem-reproducible-table-verifier-output.md",
    "MathExtras.EffectiveMertensDecay.mertensM_hurst_sqrt_source": "hurst-mertens-sqrt.md",
    "MathExtras.Helfgott.MajorArcsStart.platt_theorem_7_1_dirichlet_verification_source": "helfgott-major-4-6-platt-dirichlet.md",
    "MathExtras.Helfgott.Section24.residual_platt_2_11": "platt_2_11.md",
    "MathExtras.Helfgott.Section24.residual_platt_stronger_range": "platt_stronger_range.md",
    "MathExtras.RamareMertens2025.ramare_zuniga_2024_lemma_6_2_source": "ramare-zuniga-2024-lemma-6-2.md",
}


def parse_key_value_transcript(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if "=" not in line:
            raise EvidenceError(f"line {line_number} is not KEY=VALUE")
        key, value = line.split("=", 1)
        if not key or not value or key in result:
            raise EvidenceError(f"invalid or duplicate key on line {line_number}")
        result[key] = value
    return result


def _verify_cdem_chunk_manifest(
    fields: dict[str, str], *, require_chunks: bool
) -> tuple[int, str] | None:
    if "CHUNK_COUNT" not in fields:
        if require_chunks:
            raise EvidenceError("CDEM transcript is missing the chunk manifest")
        return None
    try:
        chunk_count = int(fields["CHUNK_COUNT"])
        block_size = int(fields["BLOCK_SIZE"])
    except (KeyError, ValueError) as exc:
        raise EvidenceError("invalid CDEM chunk-count or block-size field") from exc
    _require(chunk_count > 0 and block_size > 0, "invalid CDEM chunk geometry")
    expected_count = (CDEM_REQUIRED_FIELDS["N"] + block_size - 1) // block_size
    _require(chunk_count == expected_count, "CDEM chunk count differs from its geometry")
    expected_low = 1
    expected_before = 0
    total_u = 0
    total_v = 0
    total_variation = 0
    manifest_parts: list[str] = []
    for index in range(chunk_count):
        key = f"CHUNK_{index}"
        try:
            value = fields[key]
            pieces = value.split(",")
            if len(pieces) != 7:
                raise ValueError
            low, high, before, after, upper_u, upper_v, variation = map(int, pieces)
        except (KeyError, ValueError) as exc:
            raise EvidenceError(f"missing or malformed CDEM chunk {index}") from exc
        _require(low == expected_low, f"CDEM chunk {index} breaks range coverage")
        expected_high = min(CDEM_REQUIRED_FIELDS["N"], low + block_size - 1)
        _require(high == expected_high, f"CDEM chunk {index} has the wrong endpoint")
        _require(before == expected_before, f"CDEM chunk {index} breaks prefix state")
        _require(
            -(1 << 63) <= before < (1 << 63)
            and -(1 << 63) <= after < (1 << 63),
            f"CDEM chunk {index} prefix state exceeds the producer's int64 range",
        )
        _require(
            -(1 << 127) <= upper_u < (1 << 127),
            f"CDEM chunk {index} signed aggregate exceeds the producer's int128 range",
        )
        _require(
            0 <= upper_v < (1 << 128)
            and 0 <= variation < (1 << 64),
            f"CDEM chunk {index} unsigned aggregate exceeds the producer range",
        )
        total_u += upper_u
        total_v += upper_v
        total_variation += variation
        expected_before = after
        expected_low = high + 1
        manifest_parts.append(f"{key}={value}\n")
    _require(expected_low == CDEM_REQUIRED_FIELDS["N"] + 1, "CDEM chunks do not reach N")
    _require(expected_before == CDEM_REQUIRED_FIELDS["FINAL_F"], "CDEM chunk terminal prefix differs")
    _require(total_u == CDEM_U_TARGET, "CDEM chunk signed reduction differs")
    _require(total_v == CDEM_V_TARGET, "CDEM chunk absolute reduction differs")
    _require(
        total_variation == CDEM_REQUIRED_FIELDS["TOTAL_VARIATION"],
        "CDEM chunk variation reduction differs",
    )
    manifest = "".join(manifest_parts).encode("ascii")
    digest = hashlib.sha256(manifest).hexdigest()
    _require(
        fields.get("CHUNK_MANIFEST_SHA256") == digest,
        "CDEM chunk-manifest SHA-256 differs",
    )
    unexpected_chunks = {
        key for key in fields if key.startswith("CHUNK_")
    } - {"CHUNK_COUNT", "CHUNK_MANIFEST_SHA256"} - {
        f"CHUNK_{index}" for index in range(chunk_count)
    }
    _require(not unexpected_chunks, "CDEM transcript has unexpected chunk rows")
    return chunk_count, digest


def verify_cdem_abel_text(
    text: str, *, require_chunks: bool = False
) -> EvidenceCheck:
    """Check every deterministic field used by the CDEM Abel trust atom."""

    fields = parse_key_value_transcript(text)
    for name, expected in CDEM_REQUIRED_FIELDS.items():
        try:
            actual = int(fields[name])
        except (KeyError, ValueError) as exc:
            raise EvidenceError(f"missing or invalid CDEM field {name}") from exc
        _require(actual == expected, f"CDEM field {name} differs from expected")
    try:
        u_upper = int(fields["U_INC_UPPER_NUM"])
        v_upper = int(fields["V_INC_UPPER_NUM"])
    except (KeyError, ValueError) as exc:
        raise EvidenceError("missing or invalid CDEM Abel numerator") from exc
    # These are deterministic outputs of the fully specified recurrence, not
    # arbitrary witness values.  Pinning equality prevents a fabricated
    # negative "upper bound" (or any other easier number) from being accepted.
    _require(u_upper == CDEM_U_TARGET, "CDEM signed Abel output differs")
    _require(v_upper == CDEM_V_TARGET, "CDEM absolute Abel output differs")
    chunks = _verify_cdem_chunk_manifest(fields, require_chunks=require_chunks)

    checks = [
        "exact K/N/A and Mobius trace",
        "exact coefficient enclosures",
        "expected stored recurrence endpoint and variation fields",
        "exact signed Abel numerator output",
        "exact absolute square-root-weighted Abel numerator output",
    ]
    metrics: dict[str, str | int] = {
        "range_end": 5_000_000_000,
        "u_increment_upper_numerator": u_upper,
        "v_increment_upper_numerator": v_upper,
        "weight_scale": 10**18,
        "registered_result": cdem_abel_registered_result(u_upper, v_upper),
        "registered_result_sha256": hashlib.sha256(
            cdem_abel_registered_result(u_upper, v_upper).encode("ascii")
        ).hexdigest(),
    }
    if chunks is not None:
        checks.extend(
            (
                "gap-free chunk range and prefix-state composition",
                "exact chunk U/V/variation reductions",
                "canonical chunk-manifest SHA-256",
            )
        )
        metrics["chunk_count"] = chunks[0]
        metrics["chunk_manifest_sha256"] = chunks[1]

    return EvidenceCheck(
        atom_id="cdem-table-abel",
        accepted=True,
        classification="expected_transcript_fields_and_bounds_only",
        checks=tuple(checks),
        metrics=metrics,
    )


def verify_cdem_abel_transcript(path: Path) -> EvidenceCheck:
    """Read and check a complete CDEM Abel producer transcript."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"cannot read CDEM transcript {path}: {exc}") from exc
    return verify_cdem_abel_text(text)


def compare_claude_math_inventory(
    path: Path, *, require_card_files: bool = False
) -> EvidenceCheck:
    """Check the exact inventory shape, names, card mapping, and optional bytes."""

    from .catalog import ATOMS

    inventory_raw = read_artifact_bytes(path)
    value = load_decimal_json_bytes(inventory_raw, label=str(path))
    _require(
        set(value) == {"declaration", "status", "entries"},
        "inventory root fields differ from the reviewed schema",
    )
    _require(
        value.get("declaration")
        == "Math.Problems.TernaryGoldbach.ternary_goldbach",
        "inventory declaration differs from the catalog theorem",
    )
    _require(
        isinstance(value.get("status"), str) and bool(value["status"].strip()),
        "inventory status must be a nonempty string",
    )
    entries = value.get("entries")
    _require(isinstance(entries, list), "inventory has no entries array")
    names: list[str] = []
    cards: dict[str, str] = {}
    for index, entry in enumerate(entries):
        _require(isinstance(entry, dict), f"inventory entry {index} is malformed")
        _require(
            set(entry)
            == {"axiom", "card", "source_kind", "trust_class", "source_locators"},
            f"inventory entry {index} fields differ from the reviewed schema",
        )
        name = entry.get("axiom")
        _require(isinstance(name, str), f"inventory entry {index} has no axiom")
        card = entry.get("card")
        _require(isinstance(card, str), f"inventory entry {index} has no card")
        _require(
            entry.get("trust_class") == "external_finite_computation",
            f"inventory entry {index} has the wrong trust class",
        )
        _require(
            isinstance(entry.get("source_kind"), str)
            and bool(entry["source_kind"].strip()),
            f"inventory entry {index} has no source-kind description",
        )
        locators = entry.get("source_locators")
        _require(
            isinstance(locators, list)
            and bool(locators)
            and all(isinstance(locator, str) and locator for locator in locators),
            f"inventory entry {index} has invalid source locators",
        )
        names.append(name)
        cards[name] = card
    expected = {atom.lean_name for atom in ATOMS}
    actual = set(names)
    _require(len(names) == 13 and len(actual) == 13, "inventory must have 13 names")
    _require(actual == expected, "GPU catalog and Lean inventory names differ")
    _require(cards == EXPECTED_INVENTORY_CARDS, "inventory citation-card mapping differs")
    checks = [
        "reviewed inventory schema",
        "theorem declaration",
        "thirteen unique names",
        "exact catalog name-set equality",
        "exact axiom-to-card mapping",
        "external-computation trust classes",
        "nonempty source descriptions and locator lists",
    ]
    metrics: dict[str, str | int] = {
        "atom_count": 13,
        "inventory_sha256": hashlib.sha256(inventory_raw).hexdigest(),
    }
    if require_card_files:
        card_hashes: dict[str, str] = {}
        for name, card in sorted(cards.items()):
            card_path = path.parent / card
            _require(card_path.is_file(), f"citation card is missing: {card_path}")
            card_hashes[name] = sha256_file(card_path)
        card_manifest = json.dumps(
            card_hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        metrics["citation_card_manifest_sha256"] = hashlib.sha256(
            card_manifest
        ).hexdigest()
        checks.append("all mapped citation-card bytes hashed")
    return EvidenceCheck(
        atom_id="catalog-sync",
        accepted=True,
        classification="exact_name_set_comparison",
        checks=tuple(checks),
        metrics=metrics,
    )
