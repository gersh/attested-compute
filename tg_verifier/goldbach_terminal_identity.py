# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Post-run identity bundle for the finite-Goldbach terminal registration.

No production identity is configured in source.  A completed campaign may
produce a candidate bundle, but it cannot become a Lean registration until a
human reviews the exact bundle digest and installs matching Lean pins.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from tg_verifier.azure_cpu_goldbach_10pow27_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COUNTS,
)
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
    PHASE_ID as H100_PHASE,
    SHARD_COUNT as H100_GROUP_COUNT,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)


BUNDLE_KIND = "sparkinterval.goldbach10pow27-terminal-identity-bundle.v1"
CHILD_INDEX_KIND = "sparkinterval.goldbach10pow27-child-receipt-index.v1"
CHILD_COMMITMENT_KIND = (
    "sparkinterval.goldbach10pow27-child-receipt-identity-commitment.v1"
)
TERMINAL_BINDING_KIND = (
    "sparkinterval.goldbach10pow27-terminal-post-child-run-binding.v1"
)
SCHEMA_VERSION = 1
REGISTERED_INVOCATION = "goldbach10Pow27ProductionV1"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ZERO_DIGEST = "0" * 64
NOT_APPLICABLE_DIGEST = hashlib.sha256(
    b"sparkinterval.trusted-compute.not-applicable.v1"
).hexdigest()

# Intentionally empty until a real completed campaign has been independently
# reviewed.  Candidate generation cannot populate this authority.
REVIEWED_PRODUCTION_BUNDLE_SHA256S: frozenset[str] = frozenset()

TOP_FIELDS = {
    "admission",
    "children",
    "classification",
    "kind",
    "registered_invocation",
    "schema_version",
    "terminal",
}
ADMISSION_FIELDS = {
    "admission_sha256",
    "admission_size_bytes",
    "build_identity_sha256",
    "executable_sha256",
    "h100_artifact_closure_manifest_sha256",
    "h100_runtime_image_closure",
    "h100_runtime_image_closure_sha256",
    "h100_source_tree_sha256",
    "source_identity_sha256",
}
CHILDREN_FIELDS = {
    "count",
    "identities",
    "identities_sha256",
}
CHILD_FIELDS = {
    "algorithm_hash",
    "algorithm_id",
    "artifacts",
    "backend",
    "claim_sha256",
    "domain_hash",
    "group_id",
    "input_hash",
    "job_projection_sha256",
    "output_hash",
    "parameters_hash",
    "phase",
    "receipt_sha256",
    "shard_index",
}
CLAIM_ARTIFACT_FIELDS = {
    "device_cubin_hash",
    "host_executable_hash",
    "kernel_manifest_hash",
    "source_tree_hash",
}
TERMINAL_FIELDS = {
    "artifact_closure",
    "child_identity_commitment",
    "claim",
    "job_spec_sha256",
    "materialization_manifest_sha256",
    "receipt_sha256",
    "runner_policy",
    "runtime_closure",
    "source_manifest",
    "terminal_execution_binding",
}
CHILD_COMMITMENT_FIELDS = {
    "build_admission_sha256",
    "build_identity_sha256",
    "child_count",
    "child_identities_sha256",
    "h100_executable_sha256",
    "h100_runtime_image_closure_sha256",
    "kind",
    "schema_version",
}
TERMINAL_BINDING_FIELDS = {
    "build_admission_sha256",
    "child_identity_commitment_sha256",
    "h100_executable_sha256",
    "h100_runtime_image_closure_sha256",
    "kind",
    "runner_policy_sha256",
    "runtime_closure_sha256",
    "schema_version",
    "source_manifest_sha256",
    "target_profile_sha256",
    "terminal_host_executable_sha256",
    "terminal_producer_executable_sha256",
    "trust_profile_sha256",
}
ARTIFACT_RECORD_FIELDS = {
    "executable",
    "path",
    "role",
    "sha256",
    "size_bytes",
    "statement_role",
}
TERMINAL_CLAIM_FIELDS = {
    "algorithm_hash",
    "algorithm_id",
    "artifacts",
    "domain_hash",
    "input_hash",
    "output_hash",
    "parameters_hash",
    "result",
    "target",
    "target_profile_hash",
    "trust",
    "trust_profile_hash",
}
PIN_DEFINITIONS = {
    "bundle_sha256": "goldbach10Pow27TerminalIdentityBundleSha256",
    "receipt_sha256": "goldbach10Pow27TerminalReceiptSha256",
    "job_spec_sha256": "goldbach10Pow27TerminalJobSpecSha256",
    "artifact_closure_manifest_sha256": (
        "goldbach10Pow27TerminalArtifactClosureSha256"
    ),
    "source_tree_hash": "goldbach10Pow27TerminalSourceTreeSha256",
    "host_executable_hash": "goldbach10Pow27TerminalHostExecutableSha256",
    "kernel_manifest_hash": (
        "goldbach10Pow27TerminalPostRunCommitmentSha256"
    ),
    "child_identities_sha256": "goldbach10Pow27ChildReceiptIdentitiesSha256",
    "build_admission_sha256": "goldbach10Pow27BuildAdmissionSha256",
    "runtime_closure_sha256": "goldbach10Pow27TerminalRuntimeClosureSha256",
}


class GoldbachTerminalIdentityError(ValueError):
    """A candidate bundle, topology, or Lean pin set differed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise GoldbachTerminalIdentityError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def _digest(value: Any, what: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == ZERO_DIGEST
    ):
        raise GoldbachTerminalIdentityError(
            f"{what} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _size(value: Any, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= 2**63 - 1
    ):
        raise GoldbachTerminalIdentityError(f"{what} must be a positive size")
    return value


def _wire_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def expected_child_topology() -> tuple[tuple[str, int], ...]:
    """Every signed nonterminal DAG node required by the finalizer."""

    result = [
        (H100_PHASE, index) for index in range(H100_GROUP_COUNT)
    ]
    for phase, count in PHASE_COUNTS.items():
        if phase == "measured-finalize-lowered-source-claim":
            continue
        result.extend((phase, index) for index in range(count))
    return tuple(sorted(result))


def _validate_artifacts(value: Any, what: str) -> dict[str, str]:
    row = _exact(value, CLAIM_ARTIFACT_FIELDS, what)
    return {
        key: _digest(row[key], f"{what} {key}")
        for key in sorted(CLAIM_ARTIFACT_FIELDS)
    }


def _validate_children(value: Any) -> dict[str, Any]:
    row = _exact(value, CHILDREN_FIELDS, "terminal child identities")
    identities = row["identities"]
    if not isinstance(identities, list):
        raise GoldbachTerminalIdentityError(
            "terminal child identities must be an array"
        )
    expected = expected_child_topology()
    if row["count"] != len(expected) or len(identities) != len(expected):
        raise GoldbachTerminalIdentityError(
            "terminal child receipt count does not cover the complete DAG"
        )
    checked: list[dict[str, Any]] = []
    topology: list[tuple[str, int]] = []
    for index, value in enumerate(identities):
        child = _exact(value, CHILD_FIELDS, f"terminal child identity {index}")
        phase = child["phase"]
        shard_index = child["shard_index"]
        if (
            not isinstance(phase, str)
            or isinstance(shard_index, bool)
            or not isinstance(shard_index, int)
            or shard_index < 0
            or child["group_id"] != f"{CAMPAIGN_ID}::{phase}"
            or child["backend"]
            not in {"azure_ncc40ads_h100_v5", "azure_sevsnp_cpu"}
        ):
            raise GoldbachTerminalIdentityError(
                f"terminal child identity {index} has invalid topology"
            )
        normalized = dict(child)
        normalized["artifacts"] = _validate_artifacts(
            child["artifacts"], f"terminal child identity {index}"
        )
        for field in (
            "algorithm_hash",
            "claim_sha256",
            "domain_hash",
            "input_hash",
            "job_projection_sha256",
            "output_hash",
            "parameters_hash",
            "receipt_sha256",
        ):
            normalized[field] = _digest(
                child[field], f"terminal child identity {index} {field}"
            )
        if (
            phase == H100_PHASE
            and (
                child["backend"] != "azure_ncc40ads_h100_v5"
                or child["job_projection_sha256"]
                != normalized["artifacts"]["kernel_manifest_hash"]
            )
        ) or (
            phase != H100_PHASE
            and (
                child["backend"] != "azure_sevsnp_cpu"
                or child["job_projection_sha256"] != NOT_APPLICABLE_DIGEST
            )
        ):
            raise GoldbachTerminalIdentityError(
                f"terminal child identity {index} has wrong job projection role"
            )
        if not isinstance(child["algorithm_id"], str) or not child["algorithm_id"]:
            raise GoldbachTerminalIdentityError(
                f"terminal child identity {index} algorithm ID is invalid"
            )
        topology.append((phase, shard_index))
        checked.append(normalized)
    if tuple(sorted(topology)) != expected or len(set(topology)) != len(expected):
        raise GoldbachTerminalIdentityError(
            "terminal child identities have a gap, duplicate, or foreign node"
        )
    checked.sort(key=lambda item: (item["phase"], item["shard_index"]))
    identities_sha256 = hashlib.sha256(canonical_json_bytes(checked)).hexdigest()
    if row["identities_sha256"] != identities_sha256:
        raise GoldbachTerminalIdentityError(
            "terminal child identity aggregate digest differs"
        )
    return {
        "count": len(checked),
        "identities": checked,
        "identities_sha256": identities_sha256,
    }


def child_identity_commitment(
    identities: list[dict[str, Any]],
    *,
    build_admission_sha256: str,
    build_identity_sha256: str,
    h100_executable_sha256: str,
    h100_runtime_image_closure_sha256: str,
) -> dict[str, Any]:
    """Commit every signed nonterminal identity and its reviewed build/runtime."""

    checked = _validate_children(
        {
            "count": len(identities),
            "identities": identities,
            "identities_sha256": hashlib.sha256(
                canonical_json_bytes(identities)
            ).hexdigest(),
        }
    )
    return {
        "build_admission_sha256": _digest(
            build_admission_sha256, "child commitment build admission"
        ),
        "build_identity_sha256": _digest(
            build_identity_sha256, "child commitment build identity"
        ),
        "child_count": checked["count"],
        "child_identities_sha256": checked["identities_sha256"],
        "h100_executable_sha256": _digest(
            h100_executable_sha256, "child commitment H100 executable"
        ),
        "h100_runtime_image_closure_sha256": _digest(
            h100_runtime_image_closure_sha256,
            "child commitment H100 runtime image closure",
        ),
        "kind": CHILD_COMMITMENT_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def validate_child_identity_commitment(value: Any) -> dict[str, Any]:
    row = _exact(
        value, CHILD_COMMITMENT_FIELDS, "Goldbach child identity commitment"
    )
    if (
        row["kind"] != CHILD_COMMITMENT_KIND
        or row["schema_version"] != SCHEMA_VERSION
        or isinstance(row["child_count"], bool)
        or row["child_count"] != len(expected_child_topology())
    ):
        raise GoldbachTerminalIdentityError(
            "unsupported or incomplete Goldbach child identity commitment"
        )
    checked = dict(row)
    for field in CHILD_COMMITMENT_FIELDS - {
        "child_count", "kind", "schema_version"
    }:
        checked[field] = _digest(
            row[field], f"Goldbach child identity commitment {field}"
        )
    return checked


def load_child_identity_commitment(
    path: Path, *, expected_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    try:
        value = load_json(path, require_canonical=True)
        digest, _size_bytes = hash_file_once(path, limit=4 * 1024 * 1024)
    except (CampaignIOError, OSError, ValueError) as error:
        raise GoldbachTerminalIdentityError(
            f"cannot load canonical child identity commitment: {error}"
        ) from error
    if expected_sha256 is not None and digest != _digest(
        expected_sha256, "child identity commitment pin"
    ):
        raise GoldbachTerminalIdentityError(
            "child identity commitment differs from its pin"
        )
    return validate_child_identity_commitment(value), digest


def terminal_execution_binding(**values: str) -> dict[str, Any]:
    """Canonical noncircular links included in the terminal artifact closure."""

    expected = TERMINAL_BINDING_FIELDS - {"kind", "schema_version"}
    if set(values) != expected:
        raise GoldbachTerminalIdentityError(
            "terminal execution binding arguments have wrong fields"
        )
    return {
        **{
            field: _digest(
                values[field], f"terminal execution binding {field}"
            )
            for field in sorted(expected)
        },
        "kind": TERMINAL_BINDING_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def validate_terminal_execution_binding(value: Any) -> dict[str, Any]:
    row = _exact(
        value, TERMINAL_BINDING_FIELDS, "Goldbach terminal execution binding"
    )
    if (
        row["kind"] != TERMINAL_BINDING_KIND
        or row["schema_version"] != SCHEMA_VERSION
    ):
        raise GoldbachTerminalIdentityError(
            "unsupported Goldbach terminal execution binding"
        )
    return terminal_execution_binding(
        **{
            field: row[field]
            for field in TERMINAL_BINDING_FIELDS - {"kind", "schema_version"}
        }
    )


def validate_terminal_identity_bundle(value: Any) -> dict[str, Any]:
    bundle = _exact(value, TOP_FIELDS, "Goldbach terminal identity bundle")
    if (
        bundle["kind"] != BUNDLE_KIND
        or bundle["schema_version"] != SCHEMA_VERSION
        or bundle["registered_invocation"] != REGISTERED_INVOCATION
    ):
        raise GoldbachTerminalIdentityError(
            "unsupported Goldbach terminal identity bundle"
        )
    classification = bundle["classification"]
    if classification not in {"post-run-candidate", "reviewed-production"}:
        raise GoldbachTerminalIdentityError(
            "Goldbach terminal identity classification is unsupported"
        )

    admission = _exact(
        bundle["admission"], ADMISSION_FIELDS, "terminal build admission"
    )
    for field in ADMISSION_FIELDS - {"admission_size_bytes", "h100_runtime_image_closure"}:
        _digest(admission[field], f"terminal admission {field}")
    _size(admission["admission_size_bytes"], "terminal admission")
    if not isinstance(admission["h100_runtime_image_closure"], dict):
        raise GoldbachTerminalIdentityError(
            "terminal admission omits the H100 runtime image closure"
        )
    if hashlib.sha256(
        canonical_json_bytes(admission["h100_runtime_image_closure"])
    ).hexdigest() != admission["h100_runtime_image_closure_sha256"]:
        raise GoldbachTerminalIdentityError(
            "terminal admission H100 runtime image closure digest differs"
        )
    children = _validate_children(bundle["children"])

    terminal = _exact(bundle["terminal"], TERMINAL_FIELDS, "terminal identity")
    for field in (
        "job_spec_sha256",
        "materialization_manifest_sha256",
        "receipt_sha256",
    ):
        _digest(terminal[field], f"terminal {field}")
    claim = _exact(terminal["claim"], TERMINAL_CLAIM_FIELDS, "terminal claim")
    for field in (
        "algorithm_hash",
        "domain_hash",
        "input_hash",
        "output_hash",
        "parameters_hash",
        "target_profile_hash",
        "trust_profile_hash",
    ):
        _digest(claim[field], f"terminal claim {field}")
    _validate_artifacts(claim["artifacts"], "terminal claim artifacts")
    if (
        not isinstance(claim["algorithm_id"], str)
        or not claim["algorithm_id"]
        or claim["result"] != "true"
        or claim["target"] != "azure_sevsnp_cpu"
        or claim["trust"] != "azure_sevsnp_confidential_compute"
    ):
        raise GoldbachTerminalIdentityError(
            "terminal claim is not the successful registered CPU result"
        )
    closure = terminal["artifact_closure"]
    if (
        not isinstance(closure, dict)
        or set(closure)
        != {
            "closure_kind",
            "files",
            "manifest_sha256",
            "terminal_producer_executable",
        }
        or not isinstance(closure["files"], list)
        or closure.get("manifest_sha256")
        != claim["artifacts"]["kernel_manifest_hash"]
    ):
        raise GoldbachTerminalIdentityError(
            "terminal artifact closure is not claim-bound"
        )
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(closure["files"]):
        record = _exact(
            item, ARTIFACT_RECORD_FIELDS, f"terminal artifact record {index}"
        )
        if (
            not isinstance(record["path"], str)
            or not record["path"]
            or record["path"] in seen
            or not isinstance(record["role"], str)
            or not record["role"]
            or not isinstance(record["executable"], bool)
            or (
                record["statement_role"] is not None
                and (
                    not isinstance(record["statement_role"], str)
                    or not record["statement_role"]
                )
            )
        ):
            raise GoldbachTerminalIdentityError(
                f"terminal artifact record {index} is malformed"
            )
        seen.add(record["path"])
        _digest(record["sha256"], f"terminal artifact record {index}")
        _size(record["size_bytes"], f"terminal artifact record {index}")
        files.append(record)
    if files != sorted(files, key=lambda item: item["path"]):
        raise GoldbachTerminalIdentityError(
            "terminal artifact records are not path sorted"
        )
    expected_closure_sha256 = hashlib.sha256(
        _wire_json_bytes(
            {
                "artifacts": files,
                "kind": "sparkinterval_executable_artifact_closure",
                "schema_version": 1,
            }
        )
    ).hexdigest()
    if closure["manifest_sha256"] != expected_closure_sha256:
        raise GoldbachTerminalIdentityError(
            "terminal artifact closure manifest digest differs"
        )
    for role, expected_hash in (
        ("host_executable", claim["artifacts"]["host_executable_hash"]),
        ("source_tree", claim["artifacts"]["source_tree_hash"]),
    ):
        matches = [
            item["sha256"] for item in files
            if item["statement_role"] == role
        ]
        if matches != [expected_hash]:
            raise GoldbachTerminalIdentityError(
                f"terminal artifact closure has wrong {role}"
            )
    if any(
        item["statement_role"] in {"gpu_executable", "gpu_cubin", "gpu_fatbin"}
        for item in files
    ):
        raise GoldbachTerminalIdentityError(
            "terminal CPU closure unexpectedly contains a GPU execution role"
        )
    producer = closure["terminal_producer_executable"]
    if (
        not isinstance(producer, dict)
        or producer not in files
        or producer.get("statement_role") != "producer_executable"
    ):
        raise GoldbachTerminalIdentityError(
            "terminal producer executable is not in the exact closure"
        )
    for name in (
        "child_identity_commitment",
        "runner_policy",
        "runtime_closure",
        "source_manifest",
        "terminal_execution_binding",
    ):
        item = terminal[name]
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "size_bytes", "value"}
        ):
            raise GoldbachTerminalIdentityError(
                f"terminal {name} has wrong fields"
            )
        _digest(item["sha256"], f"terminal {name}")
        _size(item["size_bytes"], f"terminal {name}")
        if not isinstance(item["value"], dict):
            raise GoldbachTerminalIdentityError(
                f"terminal {name} value must be an object"
            )
        raw = _wire_json_bytes(item["value"])
        if (
            hashlib.sha256(raw).hexdigest() != item["sha256"]
            or len(raw) != item["size_bytes"]
        ):
            raise GoldbachTerminalIdentityError(
                f"terminal {name} canonical file identity differs"
            )
    expected_child_commitment = child_identity_commitment(
        children["identities"],
        build_admission_sha256=admission["admission_sha256"],
        build_identity_sha256=admission["build_identity_sha256"],
        h100_executable_sha256=admission["executable_sha256"],
        h100_runtime_image_closure_sha256=admission[
            "h100_runtime_image_closure_sha256"
        ],
    )
    if (
        validate_child_identity_commitment(
            terminal["child_identity_commitment"]["value"]
        )
        != expected_child_commitment
    ):
        raise GoldbachTerminalIdentityError(
            "terminal child identity commitment differs from the complete "
            "signed child set"
        )

    def exact_role_hash(role: str) -> str | None:
        matches = [item["sha256"] for item in files if item["role"] == role]
        if len(matches) > 1:
            raise GoldbachTerminalIdentityError(
                f"terminal closure duplicates required role {role}"
            )
        return matches[0] if matches else None

    if (
        exact_role_hash("goldbach_child_receipt_identity_commitment")
        != terminal["child_identity_commitment"]["sha256"]
        or exact_role_hash("goldbach_terminal_post_child_run_binding")
        != terminal["terminal_execution_binding"]["sha256"]
        or exact_role_hash("image_runtime_closure_manifest")
        != terminal["runtime_closure"]["sha256"]
        or exact_role_hash("reviewed_source_closure_manifest")
        != terminal["source_manifest"]["sha256"]
        or exact_role_hash("reviewed_goldbach_build_admission")
        != admission["admission_sha256"]
        or exact_role_hash("h100_executable_identity_data_not_cpu_executed")
        != admission["executable_sha256"]
    ):
        raise GoldbachTerminalIdentityError(
            "terminal closure omits its child/source/runtime/admission/H100 "
            "executable identities"
        )
    if (
        terminal["runtime_closure"]["value"].get(
            "goldbach_build_admission_sha256"
        )
        != admission["admission_sha256"]
        or terminal["runtime_closure"]["value"].get(
            "goldbach_build_identity_sha256"
        )
        != admission["build_identity_sha256"]
        or terminal["source_manifest"]["value"].get(
            "goldbach_build_admission_sha256"
        )
        != admission["admission_sha256"]
    ):
        raise GoldbachTerminalIdentityError(
            "terminal source/runtime closure does not bind the admission"
        )
    if (
        terminal["runtime_closure"]["value"].get(
            "goldbach_executable", {}
        ).get("sha256")
        != admission["executable_sha256"]
        or terminal["runtime_closure"]["value"].get(
            "python_executable", {}
        ).get("sha256")
        != claim["artifacts"]["host_executable_hash"]
        or terminal["runtime_closure"]["value"].get(
            "ladder_runner", {}
        ).get("sha256")
        != producer["sha256"]
    ):
        raise GoldbachTerminalIdentityError(
            "terminal runtime closure differs from the H100, host, or "
            "terminal producer executable"
        )
    expected_terminal_binding = terminal_execution_binding(
        build_admission_sha256=admission["admission_sha256"],
        child_identity_commitment_sha256=terminal[
            "child_identity_commitment"
        ]["sha256"],
        h100_executable_sha256=admission["executable_sha256"],
        h100_runtime_image_closure_sha256=admission[
            "h100_runtime_image_closure_sha256"
        ],
        runner_policy_sha256=terminal["runner_policy"]["sha256"],
        runtime_closure_sha256=terminal["runtime_closure"]["sha256"],
        source_manifest_sha256=terminal["source_manifest"]["sha256"],
        target_profile_sha256=claim["target_profile_hash"],
        terminal_host_executable_sha256=claim["artifacts"][
            "host_executable_hash"
        ],
        terminal_producer_executable_sha256=producer["sha256"],
        trust_profile_sha256=claim["trust_profile_hash"],
    )
    if (
        validate_terminal_execution_binding(
            terminal["terminal_execution_binding"]["value"]
        )
        != expected_terminal_binding
    ):
        raise GoldbachTerminalIdentityError(
            "terminal post-child-run binding differs from its exact "
            "children, runtime, admission, executables, policy, or profiles"
        )

    result = dict(bundle)
    result["admission"] = dict(admission)
    result["children"] = children
    result["terminal"] = dict(terminal)
    result["terminal"]["claim"] = {
        **claim,
        "artifacts": _validate_artifacts(
            claim["artifacts"], "terminal claim artifacts"
        ),
    }
    return result


def load_terminal_identity_bundle(
    path: Path,
    *,
    expected_sha256: str | None = None,
    allow_candidate: bool = False,
) -> tuple[dict[str, Any], str]:
    try:
        value = load_json(path, require_canonical=True)
        digest, _size_bytes = hash_file_once(path, limit=64 * 1024 * 1024)
    except (CampaignIOError, OSError, ValueError) as error:
        raise GoldbachTerminalIdentityError(
            f"cannot load canonical terminal identity bundle: {error}"
        ) from error
    if expected_sha256 is not None and digest != _digest(
        expected_sha256, "terminal bundle pin"
    ):
        raise GoldbachTerminalIdentityError(
            "terminal identity bundle differs from its pin"
        )
    checked = validate_terminal_identity_bundle(value)
    if checked["classification"] == "post-run-candidate":
        if not allow_candidate:
            raise GoldbachTerminalIdentityError(
                "post-run terminal candidate requires explicit review mode"
            )
    elif digest not in REVIEWED_PRODUCTION_BUNDLE_SHA256S:
        raise GoldbachTerminalIdentityError(
            "production terminal registration is unconfigured"
        )
    return checked, digest


def lean_pin_values(bundle: Mapping[str, Any], bundle_sha256: str) -> dict[str, str]:
    checked = validate_terminal_identity_bundle(bundle)
    terminal = checked["terminal"]
    claim = terminal["claim"]
    return {
        "artifact_closure_manifest_sha256": terminal["artifact_closure"][
            "manifest_sha256"
        ],
        "build_admission_sha256": checked["admission"]["admission_sha256"],
        "bundle_sha256": _digest(bundle_sha256, "terminal bundle"),
        "child_identities_sha256": checked["children"]["identities_sha256"],
        "host_executable_hash": claim["artifacts"]["host_executable_hash"],
        "job_spec_sha256": terminal["job_spec_sha256"],
        "kernel_manifest_hash": claim["artifacts"]["kernel_manifest_hash"],
        "receipt_sha256": terminal["receipt_sha256"],
        "runtime_closure_sha256": terminal["runtime_closure"]["sha256"],
        "source_tree_hash": claim["artifacts"]["source_tree_hash"],
    }


def check_lean_terminal_pins(
    lean_source: str, pins: Mapping[str, str],
) -> None:
    """Reject absent or stale source pins; comments cannot satisfy the check."""

    for key, definition in PIN_DEFINITIONS.items():
        value = _digest(pins[key], f"Lean pin {key}")
        pattern = re.compile(
            rf"^\s*def\s+{re.escape(definition)}\s*:\s*Option\s+Digest\s*"
            rf':=\s*some\s*"{re.escape(value)}"\s*$',
            re.MULTILINE,
        )
        if pattern.search(lean_source) is None:
            if re.search(rf"\b{re.escape(definition)}\b", lean_source):
                if re.search(
                    rf"^\s*def\s+{re.escape(definition)}\s*:\s*"
                    r"Option\s+Digest\s*:=\s*none\s*$",
                    lean_source,
                    re.MULTILINE,
                ):
                    raise GoldbachTerminalIdentityError(
                        f"Lean terminal pin {definition} is unconfigured"
                    )
                raise GoldbachTerminalIdentityError(
                    f"Lean terminal pin {definition} is stale"
                )
            raise GoldbachTerminalIdentityError(
                f"Lean terminal pin {definition} is unconfigured"
            )


def render_lean_pin_candidate(pins: Mapping[str, str]) -> str:
    """Render review-only definitions; this does not register a theorem."""

    lines = [
        "/- Copyright (c) 2026 Gershon Bialer. All rights reserved.",
        "SPDX-License-Identifier: MIT -/",
        "",
        "import SparkInterval.Execution.Statement",
        "",
        "/- REVIEW CANDIDATE ONLY: human review is required before replacement. -/",
        "set_option autoImplicit false",
        "",
        "namespace SparkInterval.Execution",
        "",
    ]
    for key, definition in PIN_DEFINITIONS.items():
        value = _digest(pins[key], f"Lean pin {key}")
        lines.append(f'def {definition} : Option Digest := some "{value}"')
    lines.extend(
        [
            "",
            "def goldbach10Pow27TerminalArtifactPins : Option ArtifactHashes := do",
            "  let _bundleSha256 ← goldbach10Pow27TerminalIdentityBundleSha256",
            "  let _receiptSha256 ← goldbach10Pow27TerminalReceiptSha256",
            "  let _jobSpecSha256 ← goldbach10Pow27TerminalJobSpecSha256",
            "  let _artifactClosureSha256 ← goldbach10Pow27TerminalArtifactClosureSha256",
            "  let sourceTreeHash ← goldbach10Pow27TerminalSourceTreeSha256",
            "  let hostExecutableHash ← goldbach10Pow27TerminalHostExecutableSha256",
            "  let kernelManifestHash ← goldbach10Pow27TerminalPostRunCommitmentSha256",
            "  let _childIdentitiesSha256 ← goldbach10Pow27ChildReceiptIdentitiesSha256",
            "  let _buildAdmissionSha256 ← goldbach10Pow27BuildAdmissionSha256",
            "  let _runtimeClosureSha256 ← goldbach10Pow27TerminalRuntimeClosureSha256",
            "  some {",
            "    sourceTreeHash",
            "    hostExecutableHash",
            f'    deviceCubinHash := "{NOT_APPLICABLE_DIGEST}"',
            "    kernelManifestHash",
            "  }",
            "",
            "end SparkInterval.Execution",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "BUNDLE_KIND",
    "CHILD_COMMITMENT_KIND",
    "CHILD_INDEX_KIND",
    "GoldbachTerminalIdentityError",
    "NOT_APPLICABLE_DIGEST",
    "PIN_DEFINITIONS",
    "REGISTERED_INVOCATION",
    "REVIEWED_PRODUCTION_BUNDLE_SHA256S",
    "TERMINAL_BINDING_KIND",
    "child_identity_commitment",
    "check_lean_terminal_pins",
    "expected_child_topology",
    "lean_pin_values",
    "load_child_identity_commitment",
    "load_terminal_identity_bundle",
    "render_lean_pin_candidate",
    "terminal_execution_binding",
    "validate_child_identity_commitment",
    "validate_terminal_execution_binding",
    "validate_terminal_identity_bundle",
]
