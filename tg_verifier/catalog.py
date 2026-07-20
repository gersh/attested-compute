# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Strict catalog for the thirteen live ternary-Goldbach trust atoms."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = (
    REPOSITORY_ROOT / "specifications" / "TERNARY_GOLDBACH_EXTERNAL_ATOMS.json"
)
CATALOG_KIND = "sparkinterval_ternary_goldbach_external_atoms"
SCHEMA_VERSION = 1
_GIT_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")


class CatalogError(ValueError):
    """The checked-in atom catalog is malformed or incomplete."""


@dataclass(frozen=True)
class AtomSpec:
    """One exact external-computation boundary and its executable plan."""

    atom_id: str
    lean_name: str
    claim: str
    verifier: str
    present_evidence: str
    completion_requirement: str
    feasibility: str
    work_unit: str
    # Zero means that no honest exact work count is currently known.  It must
    # not be interpreted as a zero-cost campaign.
    target_work_items: int


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_float(token: str) -> None:
    raise CatalogError(f"floating-point JSON is forbidden in the catalog: {token}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogError(f"cannot read catalog {path}: {exc}") from exc
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise CatalogError(f"invalid catalog JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError("catalog root must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CatalogError(f"{label} keys differ; missing={missing}, extra={extra}")


def load_catalog(path: Path = CATALOG_PATH) -> tuple[AtomSpec, ...]:
    """Load and fail-closed validate the source-shaped atom catalog."""

    root = _load_json(path)
    _require_exact_keys(
        root,
        {
            "schema_version",
            "catalog_kind",
            "source_theorem",
            "source_commit",
            "atoms",
        },
        "catalog",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise CatalogError("unsupported catalog schema version")
    if root["catalog_kind"] != CATALOG_KIND:
        raise CatalogError("unexpected catalog kind")
    if root["source_theorem"] != "Math.Problems.TernaryGoldbach.ternary_goldbach":
        raise CatalogError("unexpected source theorem")
    source_commit = root["source_commit"]
    if not isinstance(source_commit, str) or _GIT_SHA1_RE.fullmatch(source_commit) is None:
        raise CatalogError("source_commit must be a lowercase hexadecimal Git SHA-1")

    rows = root["atoms"]
    if not isinstance(rows, list) or len(rows) != 13:
        raise CatalogError("catalog must contain exactly thirteen atoms")
    required = {
        "id",
        "lean_name",
        "claim",
        "verifier",
        "present_evidence",
        "completion_requirement",
        "feasibility",
        "work_unit",
        "target_work_items",
    }
    result: list[AtomSpec] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CatalogError(f"atom {index} is not an object")
        _require_exact_keys(row, required, f"atom {index}")
        for field in required - {"target_work_items"}:
            if not isinstance(row[field], str) or not row[field]:
                raise CatalogError(f"atom {index} field {field!r} must be nonempty")
        work = row["target_work_items"]
        if isinstance(work, bool) or not isinstance(work, int) or work < 0:
            raise CatalogError(f"atom {index} target_work_items must be nonnegative")
        atom_id = row["id"]
        lean_name = row["lean_name"]
        if atom_id in seen_ids:
            raise CatalogError(f"duplicate atom id: {atom_id}")
        if lean_name in seen_names:
            raise CatalogError(f"duplicate Lean name: {lean_name}")
        seen_ids.add(atom_id)
        seen_names.add(lean_name)
        result.append(
            AtomSpec(
                atom_id=atom_id,
                lean_name=lean_name,
                claim=row["claim"],
                verifier=row["verifier"],
                present_evidence=row["present_evidence"],
                completion_requirement=row["completion_requirement"],
                feasibility=row["feasibility"],
                work_unit=row["work_unit"],
                target_work_items=work,
            )
        )
    return tuple(result)


ATOMS = load_catalog()
ATOMS_BY_ID = {atom.atom_id: atom for atom in ATOMS}
CATALOG_SOURCE_COMMIT = _load_json(CATALOG_PATH)["source_commit"]
