# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed planning for all thirteen ternary-Goldbach campaigns.

The registry describes executable capability, not evidence that a computation
ran.  In particular, a bounded engine or sample receipt can never be promoted
to full-source coverage by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_sha256,
    hash_file_once,
    load_json,
)
from .catalog import ATOMS, ATOMS_BY_ID, CATALOG_PATH


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    REPOSITORY_ROOT / "specifications" / "TERNARY_GOLDBACH_CAMPAIGN_PROFILES.json"
)
PROFILE_KIND = "sparkinterval_ternary_goldbach_campaign_profiles"
PROFILE_SCHEMA_VERSION = 1
PLAN_KIND = "sparkinterval_ternary_goldbach_campaign_plan"
PLAN_SCHEMA_VERSION = 2
REPOSITORY_TREE_ALGORITHM = "git-tracked-working-tree-sha256-v1"
STATUS_KIND = "sparkinterval_ternary_goldbach_campaign_status"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ATOM_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
INPUT_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
ENGINE_ID_RE = INPUT_ID_RE
DECIMAL_INTEGER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")

IMPLEMENTATION_STATES = frozenset(
    {
        "full_campaign_ready",
        "full_campaign_runnable_unscaled",
        "bounded_only",
        "blocked",
    }
)
ENGINE_STATES = frozenset({"ready", "bounded_only", "missing"})
INPUT_KINDS = frozenset(
    {
        "repository_file",
        "artifact",
        "executable",
        "python_module",
        "cuda_device",
        "system_header",
    }
)
ENGINE_ROLES = frozenset({"producer", "checker", "producer_and_checker", "reference"})
STATUS_STATES = frozenset(
    {
        "not_started",
        "running",
        "paused",
        "failed",
        "sample_complete",
        "execution_complete",
        "verified",
    }
)


class CampaignError(ValueError):
    """A campaign profile, plan, or status failed its exact contract."""


@dataclass(frozen=True)
class InputSpec:
    input_id: str
    kind: str
    locator: str
    immutable_sha256: str | None
    purpose: str


@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    role: str
    state: str
    invocation: tuple[str, ...]
    supports_full_source: bool
    supports_resume: bool
    sample_only: bool
    required_input_ids: tuple[str, ...]


@dataclass(frozen=True)
class CampaignProfile:
    atom_id: str
    catalog_verifier: str
    implementation_state: str
    full_source_domain: dict[str, Any]
    required_inputs: tuple[InputSpec, ...]
    engines: tuple[EngineSpec, ...]
    assurance: dict[str, bool]
    remaining_requirements: tuple[str, ...]
    canonical_value: dict[str, Any]

    @property
    def profile_sha256(self) -> str:
        return canonical_sha256(self.canonical_value)

    @property
    def full_source_engines(self) -> tuple[EngineSpec, ...]:
        return tuple(
            engine
            for engine in self.engines
            if engine.state == "ready"
            and engine.supports_full_source
            and not engine.sample_only
        )


@dataclass(frozen=True)
class CampaignRegistry:
    source_catalog_sha256: str
    profiles: tuple[CampaignProfile, ...]
    canonical_value: dict[str, Any]

    @property
    def registry_sha256(self) -> str:
        return canonical_sha256(self.canonical_value)

    @property
    def by_id(self) -> dict[str, CampaignProfile]:
        return {profile.atom_id: profile for profile in self.profiles}


def _fail(message: str) -> None:
    raise CampaignError(message)


def _exact_object(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be an object")
    actual = set(value)
    if actual != fields:
        _fail(
            f"{what} fields differ; missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}"
        )
    return value


def _plain_int(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{what} must be an integer not less than {minimum}")
    return value


def _nonempty_string(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{what} must be a nonempty string")
    return value


def _boolean(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{what} must be Boolean")
    return value


def _string_list(value: Any, what: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        _fail(f"{what} must be a{' nonempty' if not allow_empty else ''} list")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_nonempty_string(item, f"{what}[{index}]"))
    return tuple(result)


def _validate_domain(value: Any, atom_id: str, target_work_items: int) -> dict[str, Any]:
    domain = _exact_object(
        value,
        {
            "domain_kind",
            "lower",
            "upper",
            "coverage_rule",
            "work_unit",
            "target_work_items",
        },
        f"{atom_id} full_source_domain",
    )
    if domain["domain_kind"] not in {
        "closed_real_range",
        # `upper` is the first point NOT covered.  Needed by
        # platt-little-mertens-stronger, whose closed statement is false at
        # its endpoint; see TGComputeContracts.HurstV2.littleStrongerLimit.
        "half_open_real_range",
        "closed_integer_range",
        "finite_index_set",
        "compound_finite_range",
    }:
        _fail(f"{atom_id} has unsupported domain_kind")
    for name in ("lower", "upper"):
        bound = _nonempty_string(domain[name], f"{atom_id} domain {name}")
        if DECIMAL_INTEGER_RE.fullmatch(bound) is None:
            _fail(f"{atom_id} domain {name} must be a canonical decimal integer")
    if int(domain["lower"]) > int(domain["upper"]):
        _fail(f"{atom_id} domain bounds are reversed")
    _nonempty_string(domain["coverage_rule"], f"{atom_id} coverage_rule")
    _nonempty_string(domain["work_unit"], f"{atom_id} work_unit")
    work = _plain_int(
        domain["target_work_items"], f"{atom_id} target_work_items", minimum=0
    )
    if work != target_work_items:
        _fail(f"{atom_id} target_work_items differs from the external-atom catalog")
    return dict(domain)


def _validate_input(value: Any, atom_id: str, index: int) -> InputSpec:
    row = _exact_object(
        value,
        {"id", "kind", "locator", "immutable_sha256", "purpose"},
        f"{atom_id} input {index}",
    )
    input_id = _nonempty_string(row["id"], f"{atom_id} input id")
    if INPUT_ID_RE.fullmatch(input_id) is None:
        _fail(f"{atom_id} has invalid input id: {input_id}")
    kind = row["kind"]
    if kind not in INPUT_KINDS:
        _fail(f"{atom_id} input {input_id} has unsupported kind")
    locator = _nonempty_string(row["locator"], f"{atom_id} input {input_id} locator")
    digest = row["immutable_sha256"]
    if digest is not None and (
        not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
    ):
        _fail(f"{atom_id} input {input_id} has invalid immutable SHA-256")
    if kind in {"python_module", "cuda_device"} and digest is not None:
        _fail(f"{atom_id} non-file input {input_id} cannot have an immutable hash")
    purpose = _nonempty_string(row["purpose"], f"{atom_id} input {input_id} purpose")
    return InputSpec(input_id, kind, locator, digest, purpose)


def _validate_engine(
    value: Any, atom_id: str, index: int, known_input_ids: set[str]
) -> EngineSpec:
    row = _exact_object(
        value,
        {
            "id",
            "role",
            "state",
            "invocation",
            "supports_full_source",
            "supports_resume",
            "sample_only",
            "required_input_ids",
        },
        f"{atom_id} engine {index}",
    )
    engine_id = _nonempty_string(row["id"], f"{atom_id} engine id")
    if ENGINE_ID_RE.fullmatch(engine_id) is None:
        _fail(f"{atom_id} has invalid engine id: {engine_id}")
    if row["role"] not in ENGINE_ROLES:
        _fail(f"{atom_id} engine {engine_id} has invalid role")
    if row["state"] not in ENGINE_STATES:
        _fail(f"{atom_id} engine {engine_id} has invalid state")
    invocation = _string_list(
        row["invocation"], f"{atom_id} engine {engine_id} invocation"
    )
    supports_full = _boolean(
        row["supports_full_source"], f"{atom_id} engine supports_full_source"
    )
    supports_resume = _boolean(
        row["supports_resume"], f"{atom_id} engine supports_resume"
    )
    sample_only = _boolean(row["sample_only"], f"{atom_id} engine sample_only")
    required_input_ids = _string_list(
        row["required_input_ids"],
        f"{atom_id} engine {engine_id} required_input_ids",
    )
    if len(set(required_input_ids)) != len(required_input_ids):
        _fail(f"{atom_id} engine {engine_id} repeats a required input")
    unknown_inputs = sorted(set(required_input_ids) - known_input_ids)
    if unknown_inputs:
        _fail(f"{atom_id} engine {engine_id} has unknown inputs: {unknown_inputs}")
    if row["state"] == "missing" and invocation:
        _fail(f"{atom_id} missing engine {engine_id} must not have an invocation")
    if row["state"] != "missing" and not invocation:
        _fail(f"{atom_id} implemented engine {engine_id} lacks an invocation")
    if sample_only and supports_full:
        _fail(f"{atom_id} sample engine {engine_id} cannot support full source")
    if supports_resume and not supports_full:
        _fail(f"{atom_id} bounded engine {engine_id} cannot advertise resume")
    return EngineSpec(
        engine_id,
        row["role"],
        row["state"],
        invocation,
        supports_full,
        supports_resume,
        sample_only,
        required_input_ids,
    )


def _validate_assurance(value: Any, atom_id: str) -> dict[str, bool]:
    fields = {
        "arithmetic_decisions_exact",
        "directed_enclosures",
        "gap_free_full_domain_capable",
        "authenticated_resume_capable",
        "independent_replay_capable",
        "lean_realization_proved",
    }
    assurance = _exact_object(value, fields, f"{atom_id} assurance")
    return {
        name: _boolean(assurance[name], f"{atom_id} assurance {name}")
        for name in sorted(fields)
    }


def load_registry(path: Path = PROFILE_PATH) -> CampaignRegistry:
    """Load the 13-profile registry and bind it to the exact atom catalog."""

    try:
        root = load_json(path)
    except CampaignIOError as exc:
        raise CampaignError(str(exc)) from exc
    root = _exact_object(
        root,
        {"schema_version", "registry_kind", "source_catalog_sha256", "profiles"},
        "campaign registry",
    )
    if root["schema_version"] != PROFILE_SCHEMA_VERSION:
        _fail("unsupported campaign registry schema version")
    if root["registry_kind"] != PROFILE_KIND:
        _fail("unexpected campaign registry kind")
    catalog_hash = root["source_catalog_sha256"]
    if not isinstance(catalog_hash, str) or SHA256_RE.fullmatch(catalog_hash) is None:
        _fail("source_catalog_sha256 must be a lowercase SHA-256 digest")
    actual_catalog_hash, _ = hash_file_once(CATALOG_PATH)
    if catalog_hash != actual_catalog_hash:
        _fail("campaign registry is not bound to the checked external-atom catalog")

    rows = root["profiles"]
    if not isinstance(rows, list) or len(rows) != 13:
        _fail("campaign registry must contain exactly thirteen profiles")
    profiles: list[CampaignProfile] = []
    seen: set[str] = set()
    profile_fields = {
        "atom_id",
        "catalog_verifier",
        "implementation_state",
        "full_source_domain",
        "required_inputs",
        "engines",
        "assurance",
        "remaining_requirements",
    }
    for index, value in enumerate(rows):
        row = _exact_object(value, profile_fields, f"profile {index}")
        atom_id = _nonempty_string(row["atom_id"], f"profile {index} atom_id")
        if ATOM_ID_RE.fullmatch(atom_id) is None or atom_id not in ATOMS_BY_ID:
            _fail(f"unknown atom id in campaign registry: {atom_id}")
        if atom_id in seen:
            _fail(f"duplicate campaign profile: {atom_id}")
        seen.add(atom_id)
        atom = ATOMS_BY_ID[atom_id]
        if row["catalog_verifier"] != atom.verifier:
            _fail(f"{atom_id} catalog_verifier differs from atom catalog")
        implementation_state = row["implementation_state"]
        if implementation_state not in IMPLEMENTATION_STATES:
            _fail(f"{atom_id} has unsupported implementation_state")
        domain = _validate_domain(
            row["full_source_domain"], atom_id, atom.target_work_items
        )
        raw_inputs = row["required_inputs"]
        if not isinstance(raw_inputs, list):
            _fail(f"{atom_id} required_inputs must be a list")
        inputs = tuple(
            _validate_input(item, atom_id, input_index)
            for input_index, item in enumerate(raw_inputs)
        )
        if len({item.input_id for item in inputs}) != len(inputs):
            _fail(f"{atom_id} has duplicate input ids")
        raw_engines = row["engines"]
        if not isinstance(raw_engines, list) or not raw_engines:
            _fail(f"{atom_id} engines must be a nonempty list")
        engines = tuple(
            _validate_engine(
                item,
                atom_id,
                engine_index,
                {input_spec.input_id for input_spec in inputs},
            )
            for engine_index, item in enumerate(raw_engines)
        )
        if len({item.engine_id for item in engines}) != len(engines):
            _fail(f"{atom_id} has duplicate engine ids")
        assurance = _validate_assurance(row["assurance"], atom_id)
        requirements = _string_list(
            row["remaining_requirements"],
            f"{atom_id} remaining_requirements",
        )
        full_engines = tuple(
            engine
            for engine in engines
            if engine.state == "ready"
            and engine.supports_full_source
            and not engine.sample_only
        )
        if implementation_state in {
            "full_campaign_ready",
            "full_campaign_runnable_unscaled",
        } and not full_engines:
            _fail(f"{atom_id} advertises a full campaign without a full engine")
        if implementation_state in {"bounded_only", "blocked"} and full_engines:
            _fail(f"{atom_id} understates an advertised ready full engine")
        profiles.append(
            CampaignProfile(
                atom_id,
                atom.verifier,
                implementation_state,
                domain,
                inputs,
                engines,
                assurance,
                requirements,
                dict(row),
            )
        )
    catalog_ids = {atom.atom_id for atom in ATOMS}
    if seen != catalog_ids:
        _fail(
            "campaign and catalog ids differ; "
            f"missing={sorted(catalog_ids - seen)}, extra={sorted(seen - catalog_ids)}"
        )
    if [profile.atom_id for profile in profiles] != [atom.atom_id for atom in ATOMS]:
        _fail("campaign profiles must use the external-atom catalog order")
    return CampaignRegistry(catalog_hash, tuple(profiles), dict(root))


def parse_input_bindings(values: Sequence[str]) -> dict[str, Path]:
    """Parse repeatable ``NAME=PATH`` arguments without silently overwriting."""

    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if separator != "=" or INPUT_ID_RE.fullmatch(name) is None or not raw_path:
            _fail(f"input binding must have form NAME=PATH: {value!r}")
        if name in result:
            _fail(f"duplicate input binding: {name}")
        result[name] = Path(raw_path)
    return result


def _resolve_input(
    spec: InputSpec,
    bindings: Mapping[str, Path],
    *,
    repository_root: Path,
) -> dict[str, Any]:
    supplied = bindings.get(spec.input_id)
    available = False
    resolved: str | None = None
    digest: str | None = None
    size: int | None = None
    detail = ""
    if spec.kind == "repository_file":
        candidate = repository_root / spec.locator
        if supplied is not None:
            detail = "repository_file inputs cannot be overridden"
        elif candidate.is_file():
            available = True
            candidate = candidate.resolve()
            resolved = str(candidate)
            digest, size = hash_file_once(candidate)
        else:
            detail = f"missing repository file: {candidate}"
    elif spec.kind == "artifact":
        if supplied is None:
            detail = f"supply --input {spec.input_id}=PATH"
        elif supplied.is_file():
            available = True
            candidate = supplied.resolve()
            resolved = str(candidate)
            digest, size = hash_file_once(candidate)
        else:
            detail = f"artifact is not a regular file: {supplied}"
    elif spec.kind == "executable":
        if supplied is not None:
            candidate_text = str(supplied)
        else:
            candidate_text = spec.locator
        found = shutil.which(candidate_text)
        if found is not None:
            candidate = Path(found).resolve()
        else:
            candidate = Path(candidate_text)
            if not candidate.is_absolute():
                candidate = repository_root / candidate
        if candidate.is_file() and os.access(candidate, os.X_OK):
            available = True
            resolved = str(candidate.resolve())
            digest, size = hash_file_once(candidate)
        else:
            detail = f"executable not found: {candidate_text}"
    elif spec.kind == "python_module":
        if supplied is not None:
            detail = "python_module inputs cannot be overridden"
        elif importlib.util.find_spec(spec.locator) is not None:
            if spec.locator == "flint":
                try:
                    module = importlib.import_module("flint")
                    version = str(module.__version__)
                    flint_version = str(module.__FLINT_VERSION__)
                    release = int(module.__FLINT_RELEASE__)
                except (ImportError, AttributeError, TypeError, ValueError) as exc:
                    detail = f"cannot inspect python-flint runtime: {exc}"
                else:
                    if (version, flint_version, release) != (
                        "0.9.0",
                        "3.6.0",
                        30600,
                    ):
                        detail = (
                            "python-flint/FLINT version mismatch: "
                            f"{version}/{flint_version}/{release}"
                        )
                    else:
                        available = True
                        resolved = "python-flint==0.9.0;FLINT==3.6.0;release=30600"
            else:
                available = True
                resolved = spec.locator
        else:
            detail = f"Python module is not importable: {spec.locator}"
    elif spec.kind == "system_header":
        if supplied is not None:
            candidate = supplied
        else:
            candidate = Path(spec.locator)
        if candidate.is_file():
            available = True
            candidate = candidate.resolve()
            resolved = str(candidate)
            digest, size = hash_file_once(candidate)
        else:
            detail = f"system header not found: {candidate}"
    elif spec.kind == "cuda_device":
        if supplied is not None:
            detail = "cuda_device inputs cannot be overridden"
        else:
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi is None:
                detail = "nvidia-smi is unavailable"
            else:
                try:
                    probe = subprocess.run(
                        [nvidia_smi, "--query-gpu=name,compute_cap", "--format=csv,noheader"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    detail = f"CUDA device probe failed: {exc}"
                else:
                    lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
                    matches_policy = bool(lines)
                    if spec.locator == "NVIDIA H100 compute capability 9.0":
                        matches_policy = any(
                            "H100" in line
                            and re.search(r",\s*9\.0\s*\Z", line) is not None
                            for line in lines
                        )
                    elif spec.locator != "NVIDIA GPU":
                        _fail(f"unsupported CUDA device policy: {spec.locator}")
                    if probe.returncode == 0 and matches_policy:
                        available = True
                        resolved = "; ".join(lines)
                    else:
                        detail = f"no CUDA device satisfies policy: {spec.locator}"
    if available and spec.immutable_sha256 is not None and digest != spec.immutable_sha256:
        available = False
        detail = "immutable SHA-256 mismatch"
    return {
        "id": spec.input_id,
        "kind": spec.kind,
        "available": available,
        "resolved": resolved,
        "sha256": digest,
        "size_bytes": size,
        "immutable_sha256": spec.immutable_sha256,
        "detail": detail,
    }


def doctor_profile(
    profile: CampaignProfile,
    bindings: Mapping[str, Path],
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Check local prerequisites without running a campaign."""

    known = {item.input_id for item in profile.required_inputs}
    unknown = sorted(set(bindings) - known)
    if unknown:
        _fail(f"unknown input bindings for {profile.atom_id}: {unknown}")
    checks = [
        _resolve_input(item, bindings, repository_root=repository_root)
        for item in profile.required_inputs
    ]
    full_engines = profile.full_source_engines
    checks_by_id = {item["id"]: item for item in checks}
    engine_checks = [
        {
            "engine_id": engine.engine_id,
            "required_input_ids": list(engine.required_input_ids),
            "prerequisites_available": all(
                checks_by_id[input_id]["available"]
                for input_id in engine.required_input_ids
            ),
        }
        for engine in full_engines
    ]
    ready = any(item["prerequisites_available"] for item in engine_checks)
    return {
        "atom_id": profile.atom_id,
        "implementation_state": profile.implementation_state,
        "full_source_engine_ids": [engine.engine_id for engine in full_engines],
        "inputs": checks,
        "full_source_engine_checks": engine_checks,
        "prerequisites_available": ready,
        "ready_for_full_campaign": ready,
        "full_source_campaign_completed": False,
        "lean_atom_discharged": False,
    }


def capability_record(profile: CampaignProfile) -> dict[str, Any]:
    """Return machine-readable capability without inferring run completion."""

    return {
        "atom_id": profile.atom_id,
        "implementation_state": profile.implementation_state,
        "profile_sha256": profile.profile_sha256,
        "full_source_domain": profile.full_source_domain,
        "required_inputs": [item.__dict__ for item in profile.required_inputs],
        "engines": [
            {
                "id": engine.engine_id,
                "role": engine.role,
                "state": engine.state,
                "invocation": list(engine.invocation),
                "supports_full_source": engine.supports_full_source,
                "supports_resume": engine.supports_resume,
                "sample_only": engine.sample_only,
                "required_input_ids": list(engine.required_input_ids),
            }
            for engine in profile.engines
        ],
        "assurance": profile.assurance,
        "remaining_requirements": list(profile.remaining_requirements),
        "full_source_campaign_completed": False,
        "lean_atom_discharged": False,
    }


def _render_invocation(
    engine: EngineSpec,
    resolved_inputs: Mapping[str, dict[str, Any]],
    *,
    repository_root: Path,
    workspace: Path,
) -> list[str]:
    result: list[str] = []
    for token in engine.invocation:
        rendered = token.replace("{python}", sys.executable)
        rendered = rendered.replace("{repository}", str(repository_root.resolve()))
        rendered = rendered.replace("{workspace}", str(workspace.resolve()))
        for input_id, record in resolved_inputs.items():
            marker = "{input:" + input_id + "}"
            replacement = record.get("resolved")
            if marker in rendered:
                if not record.get("available") or not isinstance(replacement, str):
                    _fail(f"cannot render unavailable input {input_id}")
                rendered = rendered.replace(marker, replacement)
        if "{" in rendered or "}" in rendered:
            _fail(f"unresolved invocation placeholder in {token!r}")
        result.append(rendered)
    return result


def _run_git(repository_root: Path, arguments: Sequence[str]) -> bytes:
    """Run a read-only Git query or fail closed with a campaign error."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _fail(f"cannot inspect the tracked repository tree: {exc}")
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        _fail(
            "cannot inspect the tracked repository tree"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout


def _tracked_index_entries(
    repository_root: Path,
) -> tuple[bytes, list[tuple[bytes, bool]]]:
    """Return the exact stage-zero regular-file closure from Git's index."""

    listing = _run_git(
        repository_root, ["ls-files", "--stage", "--cached", "-z", "--"]
    )
    entries: list[tuple[bytes, bool]] = []
    seen: set[bytes] = set()
    for row in listing.split(b"\0"):
        if not row:
            continue
        metadata, separator, relative = row.partition(b"\t")
        fields = metadata.split(b" ")
        if separator != b"\t" or len(fields) != 3:
            _fail("Git returned a malformed tracked-tree entry")
        mode, object_id, stage = fields
        if (
            len(object_id) not in {40, 64}
            or any(byte not in b"0123456789abcdef" for byte in object_id)
        ):
            _fail("Git returned an invalid tracked object id")
        if stage != b"0":
            _fail("the tracked repository tree contains an unmerged entry")
        if mode not in {b"100644", b"100755"}:
            display = os.fsdecode(relative)
            _fail(
                f"tracked path has unsupported mode {mode.decode(errors='replace')}: "
                f"{display}; symbolic links and gitlinks are not accepted"
            )
        components = relative.split(b"/")
        if (
            not relative
            or relative.startswith(b"/")
            or any(part in {b"", b".", b"..", b".git"} for part in components)
        ):
            _fail("Git returned an unsafe tracked path")
        if relative in seen:
            _fail("Git returned a duplicate tracked path")
        seen.add(relative)
        entries.append((relative, mode == b"100755"))
    if not entries:
        _fail("the repository has no tracked regular files")
    entries.sort(key=lambda item: item[0])
    return listing, entries


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Fields that must remain stable while a tracked file is hashed."""

    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _hash_tracked_file(
    digest: Any,
    root_bytes: bytes,
    relative: bytes,
    *,
    index_executable: bool,
) -> None:
    """Hash one tracked regular file without following a final-component link."""

    components = relative.split(b"/")
    current = root_bytes
    try:
        for component in components[:-1]:
            current = os.path.join(current, component)
            parent_status = os.lstat(current)
            if stat.S_ISLNK(parent_status.st_mode):
                _fail(
                    "tracked path traverses a symbolic link: "
                    f"{os.fsdecode(relative)}"
                )
            if not stat.S_ISDIR(parent_status.st_mode):
                _fail(
                    "tracked path parent is not a directory: "
                    f"{os.fsdecode(relative)}"
                )
        path = os.path.join(root_bytes, relative)
        before = os.lstat(path)
    except OSError as exc:
        _fail(f"cannot inspect tracked path {os.fsdecode(relative)}: {exc}")
    if stat.S_ISLNK(before.st_mode):
        _fail(f"tracked path is a symbolic link: {os.fsdecode(relative)}")
    if not stat.S_ISREG(before.st_mode):
        _fail(f"tracked path is not a regular file: {os.fsdecode(relative)}")
    executable = bool(before.st_mode & 0o111)
    if executable != index_executable:
        _fail(
            "tracked executable bit differs from the Git index: "
            f"{os.fsdecode(relative)}"
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        _fail(f"cannot open tracked path {os.fsdecode(relative)} safely: {exc}")
    byte_count = 0
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (before.st_dev, before.st_ino):
            _fail(f"tracked path changed while opening: {os.fsdecode(relative)}")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(b"\x01" if executable else b"\x00")
        digest.update(opened.st_size.to_bytes(8, "big"))
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            byte_count += len(block)
        after = os.fstat(descriptor)
    except OSError as exc:
        _fail(f"cannot hash tracked path {os.fsdecode(relative)}: {exc}")
    finally:
        os.close(descriptor)
    if byte_count != opened.st_size or _stat_identity(opened) != _stat_identity(after):
        _fail(f"tracked path changed while hashing: {os.fsdecode(relative)}")
    try:
        final = os.lstat(path)
    except OSError as exc:
        _fail(f"cannot recheck tracked path {os.fsdecode(relative)}: {exc}")
    if _stat_identity(final) != _stat_identity(after):
        _fail(f"tracked path changed while hashing: {os.fsdecode(relative)}")


def _repository_tree_record(repository_root: Path) -> dict[str, Any]:
    """Commit to every Git-tracked working-tree path, executable bit, and byte."""

    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        _fail(f"cannot resolve the repository root: {exc}")
    if not root.is_dir():
        _fail("repository root is not a directory")
    top_level_bytes = _run_git(root, ["rev-parse", "--show-toplevel"])
    try:
        top_level_text = top_level_bytes.rstrip(b"\r\n").decode(
            sys.getfilesystemencoding(), errors="strict"
        )
        top_level = Path(top_level_text).resolve(strict=True)
    except (OSError, UnicodeError) as exc:
        _fail(f"Git returned an invalid repository root: {exc}")
    if top_level != root:
        _fail("repository_root must be the Git worktree top level")

    listing, entries = _tracked_index_entries(root)
    digest = hashlib.sha256()
    digest.update(b"sparkinterval.git-tracked-working-tree.v1\0")
    digest.update(len(entries).to_bytes(8, "big"))
    root_bytes = os.fsencode(root)
    for relative, index_executable in entries:
        _hash_tracked_file(
            digest,
            root_bytes,
            relative,
            index_executable=index_executable,
        )
    repeated_listing, _ = _tracked_index_entries(root)
    if repeated_listing != listing:
        _fail("the Git index changed while hashing the tracked repository tree")
    return {
        "algorithm": REPOSITORY_TREE_ALGORITHM,
        "repository_root": str(root),
        "tracked_file_count": len(entries),
        "sha256": digest.hexdigest(),
    }


def _validate_repository_tree_record(
    value: Any,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and replay a plan's full tracked-working-tree commitment."""

    record = _exact_object(
        value,
        {"algorithm", "repository_root", "tracked_file_count", "sha256"},
        "campaign plan repository_tree",
    )
    if record["algorithm"] != REPOSITORY_TREE_ALGORITHM:
        _fail("campaign plan has an unsupported repository-tree algorithm")
    root_text = _nonempty_string(
        record["repository_root"], "campaign plan repository root"
    )
    root = Path(root_text)
    try:
        normalized_root = root.resolve(strict=True)
    except OSError as exc:
        _fail(f"cannot resolve the campaign plan repository root: {exc}")
    if not root.is_absolute() or str(normalized_root) != root_text:
        _fail("campaign plan repository root must be an absolute normalized path")
    if repository_root is not None:
        try:
            expected_root = repository_root.resolve(strict=True)
        except OSError as exc:
            _fail(f"cannot resolve the expected repository root: {exc}")
        if expected_root != normalized_root:
            _fail("campaign plan is being used from a different repository")
    _plain_int(
        record["tracked_file_count"],
        "campaign plan tracked_file_count",
        minimum=1,
    )
    if (
        not isinstance(record["sha256"], str)
        or SHA256_RE.fullmatch(record["sha256"]) is None
    ):
        _fail("campaign plan repository tree has an invalid SHA-256")
    current = _repository_tree_record(normalized_root)
    if current != record:
        _fail("tracked repository tree changed after planning")
    return current


def create_plan(
    registry: CampaignRegistry,
    profile: CampaignProfile,
    bindings: Mapping[str, Path],
    *,
    engine_id: str | None = None,
    repository_root: Path = REPOSITORY_ROOT,
    workspace: Path,
) -> dict[str, Any]:
    """Create an immutable full-source plan or fail if only a sample exists."""

    available = {engine.engine_id: engine for engine in profile.full_source_engines}
    if engine_id is None:
        if len(available) != 1:
            _fail(
                f"{profile.atom_id} requires --engine; full engines={sorted(available)}"
            )
        engine = next(iter(available.values()))
    else:
        engine = available.get(engine_id)
        if engine is None:
            _fail(f"{profile.atom_id} engine {engine_id!r} is not full-source ready")
    diagnosis = doctor_profile(profile, bindings, repository_root=repository_root)
    resolved_all = {item["id"]: item for item in diagnosis["inputs"]}
    selected_checks = [resolved_all[input_id] for input_id in engine.required_input_ids]
    if not all(item["available"] for item in selected_checks):
        missing = [item["id"] for item in selected_checks if not item["available"]]
        _fail(f"missing or invalid inputs for {profile.atom_id}: {missing}")
    resolved = {item["id"]: item for item in selected_checks}
    invocation = _render_invocation(
        engine,
        resolved,
        repository_root=repository_root,
        workspace=workspace,
    )
    repository_tree = _repository_tree_record(repository_root)
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "registry_sha256": registry.registry_sha256,
        "source_catalog_sha256": registry.source_catalog_sha256,
        "profile_sha256": profile.profile_sha256,
        "atom_id": profile.atom_id,
        "engine_id": engine.engine_id,
        "workspace": str(workspace.resolve()),
        "repository_tree": repository_tree,
        "scope": "full_source",
        "sample": False,
        "full_source_domain": profile.full_source_domain,
        "bound_inputs": list(resolved.values()),
        "invocation": invocation,
        "supports_resume": engine.supports_resume,
        "completion_classification": "external_campaign_only_not_lean_discharge",
        "full_source_campaign_completed": False,
        "lean_atom_discharged": False,
    }


def validate_plan(
    value: Any,
    registry: CampaignRegistry,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    workspace: Path | None = None,
) -> tuple[dict[str, Any], CampaignProfile, EngineSpec]:
    """Validate a plan and all immutable registry/profile bindings."""

    fields = {
        "schema_version",
        "kind",
        "registry_sha256",
        "source_catalog_sha256",
        "profile_sha256",
        "atom_id",
        "engine_id",
        "workspace",
        "repository_tree",
        "scope",
        "sample",
        "full_source_domain",
        "bound_inputs",
        "invocation",
        "supports_resume",
        "completion_classification",
        "full_source_campaign_completed",
        "lean_atom_discharged",
    }
    plan = _exact_object(value, fields, "campaign plan")
    if plan["schema_version"] != PLAN_SCHEMA_VERSION or plan["kind"] != PLAN_KIND:
        _fail("unsupported campaign plan schema or kind")
    if plan["registry_sha256"] != registry.registry_sha256:
        _fail("campaign plan registry hash mismatch")
    if plan["source_catalog_sha256"] != registry.source_catalog_sha256:
        _fail("campaign plan catalog hash mismatch")
    _validate_repository_tree_record(
        plan["repository_tree"], repository_root=repository_root
    )
    atom_id = plan["atom_id"]
    profile = registry.by_id.get(atom_id)
    if profile is None:
        _fail("campaign plan has an unknown atom id")
    if plan["profile_sha256"] != profile.profile_sha256:
        _fail("campaign plan profile hash mismatch")
    engines = {engine.engine_id: engine for engine in profile.full_source_engines}
    engine = engines.get(plan["engine_id"])
    if engine is None:
        _fail("campaign plan engine is not a ready full-source engine")
    if (
        plan["scope"] != "full_source"
        or plan["sample"] is not False
        or plan["full_source_domain"] != profile.full_source_domain
        or plan["supports_resume"] != engine.supports_resume
        or plan["completion_classification"]
        != "external_campaign_only_not_lean_discharge"
        or plan["full_source_campaign_completed"] is not False
        or plan["lean_atom_discharged"] is not False
    ):
        _fail("campaign plan narrows scope or overstates completion")
    planned_workspace_text = _nonempty_string(plan["workspace"], "plan workspace")
    planned_workspace = Path(planned_workspace_text)
    if not planned_workspace.is_absolute() or str(planned_workspace) != str(
        planned_workspace.resolve()
    ):
        _fail("campaign plan workspace must be an absolute normalized path")
    if workspace is not None and workspace.resolve() != planned_workspace:
        _fail("campaign plan is being used from a different workspace")
    if not isinstance(plan["invocation"], list) or not plan["invocation"]:
        _fail("campaign plan invocation must be nonempty")
    if not all(isinstance(item, str) and item for item in plan["invocation"]):
        _fail("campaign plan invocation contains an invalid argument")
    bound_inputs = plan["bound_inputs"]
    if not isinstance(bound_inputs, list):
        _fail("campaign plan bound_inputs must be a list")
    expected_ids = set(engine.required_input_ids)
    input_specs = {item.input_id: item for item in profile.required_inputs}
    found_ids: set[str] = set()
    resolved_inputs: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(bound_inputs):
        record = _exact_object(
            item,
            {
                "id",
                "kind",
                "available",
                "resolved",
                "sha256",
                "size_bytes",
                "immutable_sha256",
                "detail",
            },
            f"bound input {index}",
        )
        input_id = record["id"]
        if input_id in found_ids or input_id not in expected_ids:
            _fail("campaign plan has duplicate or unknown bound inputs")
        found_ids.add(input_id)
        spec = input_specs[input_id]
        if record["available"] is not True:
            _fail("campaign plan binds an unavailable input")
        if (
            record["kind"] != spec.kind
            or record["immutable_sha256"] != spec.immutable_sha256
            or record["detail"] != ""
        ):
            _fail("campaign plan input metadata differs from its profile")
        resolved = record["resolved"]
        if not isinstance(resolved, str) or not resolved:
            _fail("campaign plan input has no resolved identity")
        if spec.kind in {
            "repository_file",
            "artifact",
            "executable",
            "system_header",
        }:
            if not Path(resolved).is_absolute():
                _fail("campaign plan file input is not an absolute path")
            if (
                not isinstance(record["sha256"], str)
                or SHA256_RE.fullmatch(record["sha256"]) is None
            ):
                _fail("campaign plan file input has an invalid SHA-256")
            _plain_int(record["size_bytes"], "bound input size_bytes")
            if spec.immutable_sha256 is not None and (
                record["sha256"] != spec.immutable_sha256
            ):
                _fail("campaign plan input differs from its immutable profile hash")
            if spec.kind == "repository_file" and Path(resolved) != (
                repository_root / spec.locator
            ).resolve():
                _fail("campaign plan repository input path differs from its profile")
        elif record["sha256"] is not None or record["size_bytes"] is not None:
            _fail("campaign plan non-file input contains a file digest")
        elif spec.kind == "python_module":
            expected_module = (
                "python-flint==0.9.0;FLINT==3.6.0;release=30600"
                if spec.locator == "flint"
                else spec.locator
            )
            if resolved != expected_module:
                _fail("campaign plan Python-module identity differs from its profile")
        resolved_inputs[input_id] = record
    if found_ids != expected_ids:
        _fail("campaign plan omits required inputs")
    expected_invocation = _render_invocation(
        engine,
        resolved_inputs,
        repository_root=repository_root,
        workspace=planned_workspace,
    )
    if plan["invocation"] != expected_invocation:
        _fail("campaign plan invocation differs from its profile and bound inputs")
    return plan, profile, engine


def verify_plan_inputs(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Rehash the repository closure and every input in a validated plan."""

    repository_tree = _validate_repository_tree_record(plan.get("repository_tree"))
    checks: list[dict[str, Any]] = [
        {
            "id": "git_tracked_repository_tree",
            "sha256": repository_tree["sha256"],
            "tracked_file_count": repository_tree["tracked_file_count"],
        }
    ]
    for record in plan["bound_inputs"]:
        if record["kind"] not in {
            "repository_file",
            "artifact",
            "executable",
            "system_header",
        }:
            continue
        path = Path(record["resolved"])
        digest, size = hash_file_once(path)
        if digest != record["sha256"] or size != record["size_bytes"]:
            _fail(f"bound input changed after planning: {record['id']}")
        if record["kind"] == "executable" and not os.access(path, os.X_OK):
            _fail(f"bound executable is no longer executable: {record['id']}")
        checks.append(
            {
                "id": record["id"],
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return checks


def _artifact_record(value: Any, index: int) -> dict[str, Any]:
    record = _exact_object(
        value, {"path", "sha256", "size_bytes", "role"}, f"artifact {index}"
    )
    path = _nonempty_string(record["path"], f"artifact {index} path")
    pure = Path(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        _fail(f"artifact {index} path must be safe and relative")
    if not isinstance(record["sha256"], str) or SHA256_RE.fullmatch(record["sha256"]) is None:
        _fail(f"artifact {index} has an invalid SHA-256")
    _plain_int(record["size_bytes"], f"artifact {index} size_bytes")
    _nonempty_string(record["role"], f"artifact {index} role")
    return record


def validate_status(
    value: Any,
    *,
    plan: dict[str, Any],
    plan_sha256: str,
    profile: CampaignProfile,
) -> dict[str, Any]:
    """Validate status without trusting it as semantic computation evidence."""

    fields = {
        "schema_version",
        "kind",
        "atom_id",
        "profile_sha256",
        "plan_sha256",
        "state",
        "scope",
        "sample",
        "covered_lower",
        "covered_upper",
        "covered_work_items",
        "artifacts",
        "semantic_verification",
        "full_source_campaign",
        "lean_atom_discharged",
    }
    status = _exact_object(value, fields, "campaign status")
    if status["schema_version"] != 1 or status["kind"] != STATUS_KIND:
        _fail("unsupported campaign status schema or kind")
    if (
        status["atom_id"] != profile.atom_id
        or status["profile_sha256"] != profile.profile_sha256
        or status["plan_sha256"] != plan_sha256
    ):
        _fail("campaign status does not bind its immutable plan/profile")
    if status["state"] not in STATUS_STATES:
        _fail("campaign status has an unsupported state")
    sample = _boolean(status["sample"], "campaign status sample")
    full = _boolean(status["full_source_campaign"], "full_source_campaign")
    if status["lean_atom_discharged"] is not False:
        _fail("campaign status must not claim Lean atom discharge")
    if status["scope"] not in {"sample", "full_source"}:
        _fail("campaign status has an unsupported scope")
    if sample != (status["scope"] == "sample"):
        _fail("campaign status sample and scope disagree")
    lower = _nonempty_string(status["covered_lower"], "covered_lower")
    upper = _nonempty_string(status["covered_upper"], "covered_upper")
    if DECIMAL_INTEGER_RE.fullmatch(lower) is None or DECIMAL_INTEGER_RE.fullmatch(upper) is None:
        _fail("campaign coverage bounds must be canonical decimal integers")
    if int(lower) > int(upper):
        _fail("campaign coverage bounds are reversed")
    _plain_int(status["covered_work_items"], "covered_work_items")
    artifacts = status["artifacts"]
    if not isinstance(artifacts, list):
        _fail("campaign status artifacts must be a list")
    for index, artifact in enumerate(artifacts):
        _artifact_record(artifact, index)
    if status["semantic_verification"] not in {"not_run", "failed", "accepted"}:
        _fail("campaign status has invalid semantic_verification")
    domain = profile.full_source_domain
    exact_coverage = (
        lower == domain["lower"]
        and upper == domain["upper"]
        and status["covered_work_items"] == domain["target_work_items"]
    )
    if sample and (full or status["state"] == "verified"):
        _fail("a sample can never be a verified full-source campaign")
    if full and (
        status["state"] != "verified"
        or status["scope"] != "full_source"
        or not exact_coverage
        or status["semantic_verification"] != "accepted"
    ):
        _fail("full_source_campaign lacks exact coverage and accepted verification")
    if status["state"] == "verified" and not full:
        _fail("verified status must represent exact full-source coverage")
    return status


def verify_workspace(
    workspace: Path,
    registry: CampaignRegistry,
) -> dict[str, Any]:
    """Verify plan/status/artifact integrity; do not assert theorem semantics."""

    plan_path = workspace / "plan.json"
    status_path = workspace / "status.json"
    try:
        plan_value = load_json(plan_path, require_canonical=True)
        status_value = load_json(status_path, require_canonical=True)
    except CampaignIOError as exc:
        raise CampaignError(str(exc)) from exc
    plan, profile, _ = validate_plan(plan_value, registry, workspace=workspace)
    input_checks = verify_plan_inputs(plan)
    plan_hash = canonical_sha256(plan)
    status = validate_status(
        status_value, plan=plan, plan_sha256=plan_hash, profile=profile
    )
    artifact_checks: list[dict[str, Any]] = []
    workspace_root = workspace.resolve()
    for index, value in enumerate(status["artifacts"]):
        record = _artifact_record(value, index)
        candidate = workspace_root / record["path"]
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(workspace_root)
        except (OSError, ValueError) as exc:
            _fail(f"artifact {index} cannot be resolved safely: {exc}")
        if not resolved.is_file():
            _fail(f"artifact {index} is not a regular file")
        digest, size = hash_file_once(resolved)
        if digest != record["sha256"] or size != record["size_bytes"]:
            _fail(f"artifact {index} content does not match its immutable record")
        artifact_checks.append(
            {"path": record["path"], "sha256": digest, "size_bytes": size}
        )
    return {
        "schema_version": 1,
        "classification": "campaign_control_and_artifact_integrity_only",
        "accepted": True,
        "atom_id": profile.atom_id,
        "plan_sha256": plan_hash,
        "status_sha256": canonical_sha256(status),
        "artifacts": artifact_checks,
        "bound_inputs": input_checks,
        "reported_state": status["state"],
        "reported_full_source_campaign": status["full_source_campaign"],
        "semantic_result_replayed": False,
        "full_source_campaign_verified_by_this_command": False,
        "lean_atom_discharged": False,
    }


def workspace_status(workspace: Path, registry: CampaignRegistry) -> dict[str, Any]:
    """Return fail-closed status for a missing, partial, or valid workspace."""

    plan_path = workspace / "plan.json"
    status_path = workspace / "status.json"
    if not plan_path.exists():
        return {
            "state": "not_planned",
            "workspace": str(workspace),
            "full_source_campaign": False,
            "lean_atom_discharged": False,
        }
    try:
        plan_value = load_json(plan_path, require_canonical=True)
        plan, profile, engine = validate_plan(
            plan_value, registry, workspace=workspace
        )
        plan_hash = canonical_sha256(plan)
        if not status_path.exists():
            return {
                "state": "planned",
                "workspace": str(workspace),
                "atom_id": profile.atom_id,
                "engine_id": engine.engine_id,
                "plan_sha256": plan_hash,
                "full_source_campaign": False,
                "lean_atom_discharged": False,
            }
        status_value = load_json(status_path, require_canonical=True)
        status = validate_status(
            status_value, plan=plan, plan_sha256=plan_hash, profile=profile
        )
    except (CampaignIOError, CampaignError) as exc:
        return {
            "state": "invalid",
            "workspace": str(workspace),
            "error": str(exc),
            "full_source_campaign": False,
            "lean_atom_discharged": False,
        }
    return {
        "state": status["state"],
        "workspace": str(workspace),
        "atom_id": profile.atom_id,
        "plan_sha256": plan_hash,
        "scope": status["scope"],
        "sample": status["sample"],
        "covered_lower": status["covered_lower"],
        "covered_upper": status["covered_upper"],
        "covered_work_items": status["covered_work_items"],
        "reported_full_source_campaign": status["full_source_campaign"],
        "integrity_verified": False,
        "full_source_campaign": False,
        "lean_atom_discharged": False,
    }
