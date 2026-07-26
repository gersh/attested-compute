# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed terminal replay for historical Helfgott--Platt Goldbach.

The terminal has two independent inputs:

* retained mathematical artifacts for all 65,536 binary leaves and all
  492,700 prime-ladder ranges; and
* signed child receipts for the exact 8,192 H100 groups and 320 CPU ladder
  groups which produced those artifacts.

Both are required.  The signed child results are compared with the raw
receipt hashes before the existing aggregate replayers run.  Consequently a
valid signature cannot authorize a substituted branch archive, while a
self-consistent unsigned archive cannot impersonate an attested child run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.goldbach_campaign import (
    CampaignError,
    CampaignParameters,
    independent_group_bounds,
    independent_receipt_filename,
    load_campaign,
    validate_independent_aggregate,
    combine_with_hardened_binary_goldbach,
)
from tg_verifier.goldbach_gpu_campaign import (
    GoldbachGPUCampaignError,
    PRODUCTION_ALGORITHM,
    PRODUCTION_EVEN_LIMIT,
    PRODUCTION_EVEN_START,
    PRODUCTION_GROUPS,
    PRODUCTION_SHARDS,
    aggregate_receipts,
    load_plan,
    load_receipt as load_binary_receipt,
    make_production_plan,
    production_group_leaf_indices,
    receipt_paths as binary_receipt_paths,
    validate_aggregate as validate_binary_aggregate,
)
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (
    OPERATIONAL_RESULT_KIND,
    expected_claim_identity as operational_expected_claim_identity,
)
from tg_verifier.goldbach_native_ladder import (
    NATIVE_GROUP_KIND,
    NATIVE_SCHEMA,
    native_receipt_filename,
)


CAMPAIGN_ID = "helfgott-platt-goldbach-gpu-v1"
H100_PHASE = "h100-8192-groups-of-eight-checkpoint-leaves"
LADDER_PHASE = "native-prime-ladder-range-groups"
H100_GROUP_COUNT = PRODUCTION_GROUPS
LADDER_GROUP_COUNT = 320
CHILD_COUNT = H100_GROUP_COUNT + LADDER_GROUP_COUNT
CHILD_INDEX_KIND = (
    "sparkinterval.helfgott-platt-goldbach-child-receipt-index.v1"
)
CHILD_COMMITMENT_KIND = (
    "sparkinterval.helfgott-platt-goldbach-child-identity-commitment.v1"
)
BRANCH_SUMMARY_KIND = (
    "sparkinterval.helfgott-platt-goldbach-branch-summary.v1"
)
SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ZERO_DIGEST = "0" * 64
NOT_APPLICABLE_DIGEST = hashlib.sha256(
    b"sparkinterval.trusted-compute.not-applicable.v1"
).hexdigest()
NATIVE_SOURCE_SHA256 = (
    "02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6"
)

INDEX_FIELDS = {"entries", "kind", "schema_version"}
INDEX_ENTRY_FIELDS = {
    "phase",
    "receipt_file_sha256",
    "receipt_file_size_bytes",
    "receipt_path",
    "shard_index",
}
ARTIFACT_FIELDS = {
    "device_cubin_hash",
    "host_executable_hash",
    "kernel_manifest_hash",
    "source_tree_hash",
}
IDENTITY_FIELDS = {
    "algorithm_hash",
    "algorithm_id",
    "artifacts",
    "auxiliary_receipt_sha256s",
    "backend",
    "claim_sha256",
    "domain_hash",
    "group_id",
    "input_hash",
    "output_hash",
    "parameters_hash",
    "payload_receipt_sha256s",
    "phase",
    "receipt_sha256",
    "shard_index",
}
COMMITMENT_FIELDS = {
    "branch_summary",
    "child_count",
    "child_identities_sha256",
    "kind",
    "schema_version",
}
BRANCH_FIELDS = {
    "binary_aggregate_file_sha256",
    "binary_aggregate_sha256",
    "binary_plan_sha256",
    "binary_receipt_merkle_root_sha256",
    "kind",
    "ladder_aggregate_file_sha256",
    "ladder_aggregate_sha256",
    "ladder_manifest_sha256",
    "ladder_receipt_merkle_root_sha256",
    "schema_version",
}


class HistoricalGoldbachTerminalError(ValueError):
    """A child receipt, retained branch, or terminal commitment differed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise HistoricalGoldbachTerminalError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def _digest(value: Any, what: str, *, allow_na: bool = False) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == ZERO_DIGEST
        or (value == NOT_APPLICABLE_DIGEST and not allow_na)
    ):
        raise HistoricalGoldbachTerminalError(
            f"{what} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _plain_int(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HistoricalGoldbachTerminalError(
            f"{what} must be an integer at least {minimum}"
        )
    return value


def _safe_relative(value: Any, what: str) -> Path:
    if not isinstance(value, str):
        raise HistoricalGoldbachTerminalError(f"{what} must be text")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise HistoricalGoldbachTerminalError(
            f"{what} must be a canonical relative path"
        )
    return Path(*relative.parts)


def expected_child_topology() -> tuple[tuple[str, int], ...]:
    """Canonical order for every attested producer group."""

    return (
        *((H100_PHASE, index) for index in range(H100_GROUP_COUNT)),
        *((LADDER_PHASE, index) for index in range(LADDER_GROUP_COUNT)),
    )


def ladder_group_definition(
    group_index: int, *, ladder_manifest_sha256: str,
) -> str:
    lower, upper = independent_group_bounds(
        CampaignParameters().range_count, group_index, LADDER_GROUP_COUNT
    )
    return (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\n"
        f"phase={LADDER_PHASE}\n"
        f"group-index={group_index}\n"
        f"group-count={LADDER_GROUP_COUNT}\n"
        f"range-lower={lower}\n"
        f"range-upper-exclusive={upper}\n"
        f"ladder-manifest-sha256={ladder_manifest_sha256}\n"
        f"native-source-sha256={NATIVE_SOURCE_SHA256}\n"
        "semantics=produce-and-independently-replay-every-assigned-source-range\n"
        "output=ordered-ordinary-and-native-receipt-hash-lists"
    )


def ladder_group_identity(
    group_index: int, *, ladder_manifest_sha256: str,
) -> dict[str, str]:
    manifest = _digest(ladder_manifest_sha256, "ladder manifest")
    lower, upper = independent_group_bounds(
        CampaignParameters().range_count, group_index, LADDER_GROUP_COUNT
    )
    definition = ladder_group_definition(
        group_index, ladder_manifest_sha256=manifest
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    input_value = {
        "campaign_id": CAMPAIGN_ID,
        "group_count": LADDER_GROUP_COUNT,
        "group_index": group_index,
        "ladder_manifest_sha256": manifest,
        "phase": LADDER_PHASE,
    }
    parameters = {
        "builtin_pocklington": True,
        "group_count": LADDER_GROUP_COUNT,
        "local_workers": 40,
        "native_source_sha256": NATIVE_SOURCE_SHA256,
        "sieve_block_candidates": 1 << 24,
    }
    domain = {
        "first_range_index": lower,
        "last_range_index": upper - 1,
        "range_count": upper - lower,
        "source_range_count": CampaignParameters().range_count,
    }
    return {
        "algorithm_hash": suffix,
        "algorithm_id": f"sparkinterval.tg.goldbach.ladder-group.{suffix}",
        "domain_hash": hashlib.sha256(canonical_json_bytes(domain)).hexdigest(),
        "input_hash": hashlib.sha256(
            canonical_json_bytes(input_value)
        ).hexdigest(),
        "parameters_hash": hashlib.sha256(
            canonical_json_bytes(parameters)
        ).hexdigest(),
    }


def _claim_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
    claim = receipt.get("claim")
    if not isinstance(claim, dict):
        raise HistoricalGoldbachTerminalError("signed child omits its claim")
    result = claim.get("result")
    if (
        not isinstance(result, str)
        or hashlib.sha256(result.encode("utf-8")).hexdigest()
        != claim.get("output_hash")
    ):
        raise HistoricalGoldbachTerminalError(
            "signed child result differs from its output hash"
        )
    try:
        value = json.loads(result)
    except json.JSONDecodeError as error:
        raise HistoricalGoldbachTerminalError(
            "signed child result is not JSON"
        ) from error
    if (
        not isinstance(value, dict)
        or canonical_json_bytes(value).decode("utf-8") != result
    ):
        raise HistoricalGoldbachTerminalError(
            "signed child result is not canonical JSON"
        )
    return value


def _identity(
    receipt: Mapping[str, Any],
    *,
    phase: str,
    shard_index: int,
    payload: list[str],
    auxiliary: list[str],
) -> dict[str, Any]:
    claim = receipt["claim"]
    artifacts = _exact(
        claim.get("artifacts"), ARTIFACT_FIELDS, "signed child artifacts"
    )
    normalized_artifacts = {
        field: _digest(
            artifacts[field],
            f"signed child artifact {field}",
            allow_na=field == "device_cubin_hash",
        )
        for field in sorted(ARTIFACT_FIELDS)
    }
    claim_bytes = json.dumps(
        claim,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    identity = {
        "algorithm_hash": claim["algorithm_hash"],
        "algorithm_id": claim["algorithm_id"],
        "artifacts": normalized_artifacts,
        "auxiliary_receipt_sha256s": auxiliary,
        "backend": receipt["backend"],
        "claim_sha256": hashlib.sha256(claim_bytes).hexdigest(),
        "domain_hash": claim["domain_hash"],
        "group_id": f"{CAMPAIGN_ID}::{phase}",
        "input_hash": claim["input_hash"],
        "output_hash": claim["output_hash"],
        "parameters_hash": claim["parameters_hash"],
        "payload_receipt_sha256s": payload,
        "phase": phase,
        "receipt_sha256": receipt["receipt_sha256"],
        "shard_index": shard_index,
    }
    return validate_child_identity(identity, phase=phase, shard_index=shard_index)


def validate_child_identity(
    value: Any, *, phase: str | None = None, shard_index: int | None = None,
) -> dict[str, Any]:
    row = _exact(value, IDENTITY_FIELDS, "historical Goldbach child identity")
    actual_phase = row["phase"]
    actual_index = row["shard_index"]
    if (
        actual_phase not in {H100_PHASE, LADDER_PHASE}
        or isinstance(actual_index, bool)
        or not isinstance(actual_index, int)
        or actual_index < 0
        or (phase is not None and actual_phase != phase)
        or (shard_index is not None and actual_index != shard_index)
        or row["group_id"] != f"{CAMPAIGN_ID}::{actual_phase}"
        or not isinstance(row["algorithm_id"], str)
        or not row["algorithm_id"]
    ):
        raise HistoricalGoldbachTerminalError(
            "historical Goldbach child topology/algorithm is malformed"
        )
    expected_backend = (
        "azure_ncc40ads_h100_v5"
        if actual_phase == H100_PHASE
        else "azure_sevsnp_cpu"
    )
    if row["backend"] != expected_backend:
        raise HistoricalGoldbachTerminalError(
            "historical Goldbach child uses the wrong backend"
        )
    artifacts = _exact(
        row["artifacts"], ARTIFACT_FIELDS, "historical Goldbach child artifacts"
    )
    normalized = dict(row)
    normalized["artifacts"] = {
        field: _digest(
            artifacts[field],
            f"historical Goldbach child artifact {field}",
            allow_na=field == "device_cubin_hash",
        )
        for field in sorted(ARTIFACT_FIELDS)
    }
    for field in (
        "algorithm_hash",
        "claim_sha256",
        "domain_hash",
        "input_hash",
        "output_hash",
        "parameters_hash",
        "receipt_sha256",
    ):
        normalized[field] = _digest(row[field], f"child identity {field}")
    payload = row["payload_receipt_sha256s"]
    auxiliary = row["auxiliary_receipt_sha256s"]
    if not isinstance(payload, list) or not isinstance(auxiliary, list):
        raise HistoricalGoldbachTerminalError(
            "child receipt hash lists must be arrays"
        )
    normalized["payload_receipt_sha256s"] = [
        _digest(item, "child payload receipt") for item in payload
    ]
    normalized["auxiliary_receipt_sha256s"] = [
        _digest(item, "child auxiliary receipt") for item in auxiliary
    ]
    expected_count = (
        8
        if actual_phase == H100_PHASE
        else (
            independent_group_bounds(
                CampaignParameters().range_count,
                actual_index,
                LADDER_GROUP_COUNT,
            )[1]
            - independent_group_bounds(
                CampaignParameters().range_count,
                actual_index,
                LADDER_GROUP_COUNT,
            )[0]
        )
    )
    if (
        len(normalized["payload_receipt_sha256s"]) != expected_count
        or (
            actual_phase == H100_PHASE
            and normalized["auxiliary_receipt_sha256s"]
        )
        or (
            actual_phase == LADDER_PHASE
            and len(normalized["auxiliary_receipt_sha256s"]) != expected_count
        )
    ):
        raise HistoricalGoldbachTerminalError(
            "child result omits or adds branch receipt hashes"
        )
    return normalized


def _validate_h100_receipt(
    receipt: Mapping[str, Any], group_index: int, admission: Any,
) -> dict[str, Any]:
    from tg_verifier.azure_h100_goldbach_historical_workload_factory import (
        expected_claim_identity,
        expected_execution_projection_sha256,
    )

    claim = receipt.get("claim")
    expected = expected_claim_identity(group_index, admission)
    expected_artifacts = {
        "device_cubin_hash": admission.core["executable"]["sha256"],
        "host_executable_hash": admission.core["python"]["sha256"],
        "kernel_manifest_hash": expected_execution_projection_sha256(
            group_index, admission
        ),
        "source_tree_hash": admission.expected_artifacts["source_tree_hash"],
    }
    if (
        receipt.get("backend") != "azure_ncc40ads_h100_v5"
        or not isinstance(claim, dict)
        or any(claim.get(field) != value for field, value in expected.items())
        or claim.get("artifacts") != expected_artifacts
        or claim.get("target") != "nvidia_h100_sm90"
        or claim.get("trust") != "nvidia_h100_confidential_compute"
        or claim.get("target_profile_hash")
        != admission.deployment["target_profile_sha256"]
        or claim.get("trust_profile_hash")
        != admission.deployment["trust_profile_sha256"]
    ):
        raise HistoricalGoldbachTerminalError(
            "signed H100 child is not the exact admitted historical group"
        )
    result = _claim_result(receipt)
    fields = {
        "all_group_receipts_valid",
        "execution_attested",
        "group_index",
        "leaf_indices",
        "lean_atom_discharged",
        "receipts",
        "scheduler_group_count",
        "schema",
    }
    indices = list(production_group_leaf_indices(
        make_production_plan(
            executable_sha256=admission.core["executable"]["sha256"]
        ),
        group_index,
    ))
    if (
        set(result) != fields
        or result["schema"] != "sparkinterval.goldbach-gpu-run-group.v1"
        or result["group_index"] != group_index
        or result["scheduler_group_count"] != H100_GROUP_COUNT
        or result["leaf_indices"] != indices
        or result["all_group_receipts_valid"] is not True
        or result["execution_attested"] is not False
        or result["lean_atom_discharged"] is not False
        or not isinstance(result["receipts"], list)
        or len(result["receipts"]) != 8
    ):
        raise HistoricalGoldbachTerminalError(
            "signed H100 child result has wrong group geometry"
        )
    by_index: dict[int, str] = {}
    for item in result["receipts"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"leaf_index", "receipt_sha256", "status"}
            or item["leaf_index"] not in indices
            or item["leaf_index"] in by_index
            or item["status"] not in {
                "completed-new-receipt",
                "validated-existing-receipt",
            }
        ):
            raise HistoricalGoldbachTerminalError(
                "signed H100 child has a duplicate/foreign leaf"
            )
        by_index[item["leaf_index"]] = _digest(
            item["receipt_sha256"], "H100 leaf receipt"
        )
    if set(by_index) != set(indices):
        raise HistoricalGoldbachTerminalError("signed H100 child omitted a leaf")
    return _identity(
        receipt,
        phase=H100_PHASE,
        shard_index=group_index,
        payload=[by_index[index] for index in indices],
        auxiliary=[],
    )


def _validate_ladder_receipt(
    receipt: Mapping[str, Any],
    group_index: int,
    *,
    ladder_manifest_sha256: str,
) -> dict[str, Any]:
    claim = receipt.get("claim")
    # Validate the final branch manifest even though the measured operational
    # child identity is independent of this later merged-branch digest.
    _digest(ladder_manifest_sha256, "ladder manifest")
    expected = operational_expected_claim_identity(
        LADDER_PHASE, group_index
    )
    if (
        receipt.get("backend") != "azure_sevsnp_cpu"
        or not isinstance(claim, dict)
        or any(claim.get(field) != value for field, value in expected.items())
        or claim.get("target") != "azure_sevsnp_cpu"
        or claim.get("trust") != "azure_sevsnp_confidential_compute"
        or claim.get("artifacts", {}).get("device_cubin_hash")
        != NOT_APPLICABLE_DIGEST
    ):
        raise HistoricalGoldbachTerminalError(
            "signed CPU child is not the exact historical ladder group"
        )
    operational_result = _claim_result(receipt)
    operational_fields = {
        "group_index",
        "kind",
        "phase",
        "phase_result",
        "retained_export_sha256",
        "retained_export_size_bytes",
        "retained_tree_sha256",
        "schema_version",
    }
    if (
        set(operational_result) != operational_fields
        or operational_result["kind"] != OPERATIONAL_RESULT_KIND
        or operational_result["schema_version"] != SCHEMA_VERSION
        or operational_result["phase"] != LADDER_PHASE
        or operational_result["group_index"] != group_index
        or isinstance(operational_result["retained_export_size_bytes"], bool)
        or not isinstance(
            operational_result["retained_export_size_bytes"], int
        )
        or operational_result["retained_export_size_bytes"] <= 0
    ):
        raise HistoricalGoldbachTerminalError(
            "signed CPU child is not an exact retained ladder operation"
        )
    _digest(
        operational_result["retained_export_sha256"],
        "ladder child retained archive",
    )
    _digest(
        operational_result["retained_tree_sha256"],
        "ladder child retained tree",
    )
    result = operational_result["phase_result"]
    lower, upper = independent_group_bounds(
        CampaignParameters().range_count, group_index, LADDER_GROUP_COUNT
    )
    fields = {
        "classification",
        "first_range_index",
        "group_count",
        "group_index",
        "kind",
        "last_range_index",
        "local_workers",
        "native_receipt_sha256s",
        "range_count",
        "range_receipt_sha256s",
        "schema",
    }
    if (
        not isinstance(result, dict)
        or set(result) != fields
        or result["classification"] != "full_source"
        or result["first_range_index"] != lower
        or result["last_range_index"] != upper - 1
        or result["group_count"] != LADDER_GROUP_COUNT
        or result["group_index"] != group_index
        or result["local_workers"] != 40
        or result["kind"] != NATIVE_GROUP_KIND
        or result["range_count"] != upper - lower
        or result["schema"] != NATIVE_SCHEMA
        or not isinstance(result["range_receipt_sha256s"], list)
        or not isinstance(result["native_receipt_sha256s"], list)
        or len(result["range_receipt_sha256s"]) != upper - lower
        or len(result["native_receipt_sha256s"]) != upper - lower
    ):
        raise HistoricalGoldbachTerminalError(
            "signed CPU child result has wrong range geometry"
        )
    payload = [
        _digest(item, "ladder ordinary receipt")
        for item in result["range_receipt_sha256s"]
    ]
    auxiliary = [
        _digest(item, "ladder native receipt")
        for item in result["native_receipt_sha256s"]
    ]
    return _identity(
        receipt,
        phase=LADDER_PHASE,
        shard_index=group_index,
        payload=payload,
        auxiliary=auxiliary,
    )


def load_verified_child_identities(
    root: Path,
    *,
    index_path: Path,
    key_manifest: Path,
    admission: Any,
    ladder_manifest_sha256: str,
    allow_development_key: bool = False,
) -> list[dict[str, Any]]:
    """Verify exact topology, every signature, and every child result."""

    try:
        value = load_json(index_path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachTerminalError(
            f"cannot load child receipt index: {error}"
        ) from error
    index = _exact(value, INDEX_FIELDS, "historical Goldbach child index")
    if (
        index["kind"] != CHILD_INDEX_KIND
        or index["schema_version"] != SCHEMA_VERSION
        or not isinstance(index["entries"], list)
        or len(index["entries"]) != CHILD_COUNT
    ):
        raise HistoricalGoldbachTerminalError(
            "child receipt index does not cover the exact producer topology"
        )
    from generate_trusted_compute_lean import load_verified_receipt

    identities: list[dict[str, Any]] = []
    expected = expected_child_topology()
    for position, (entry_value, topology) in enumerate(
        zip(index["entries"], expected, strict=True)
    ):
        entry = _exact(
            entry_value, INDEX_ENTRY_FIELDS, f"child index entry {position}"
        )
        phase, shard_index = topology
        if entry["phase"] != phase or entry["shard_index"] != shard_index:
            raise HistoricalGoldbachTerminalError(
                "child index order/topology differs from the canonical sequence"
            )
        relative = _safe_relative(
            entry["receipt_path"], f"child receipt path {position}"
        )
        expected_relative = Path(
            "children",
            "h100" if phase == H100_PHASE else "ladder",
            f"receipt-{shard_index:08d}.json",
        )
        if relative != expected_relative:
            raise HistoricalGoldbachTerminalError(
                "child receipt path is not canonical for its topology"
            )
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise HistoricalGoldbachTerminalError(
                f"child receipt {position} is absent or linked"
            )
        if hash_file_once(path) != (
            entry["receipt_file_sha256"],
            entry["receipt_file_size_bytes"],
        ):
            raise HistoricalGoldbachTerminalError(
                f"child receipt {position} differs from its index pin"
            )
        try:
            receipt = load_verified_receipt(
                path,
                key_manifest=key_manifest,
                allow_development_key=allow_development_key,
            )
        except Exception as error:
            raise HistoricalGoldbachTerminalError(
                f"child receipt {position} failed signature verification: {error}"
            ) from error
        if phase == H100_PHASE:
            identity = _validate_h100_receipt(
                receipt, shard_index, admission
            )
        else:
            identity = _validate_ladder_receipt(
                receipt,
                shard_index,
                ladder_manifest_sha256=ladder_manifest_sha256,
            )
        identities.append(identity)
    return identities


def validate_branch_summary(value: Any) -> dict[str, Any]:
    row = _exact(value, BRANCH_FIELDS, "historical Goldbach branch summary")
    if (
        row["kind"] != BRANCH_SUMMARY_KIND
        or row["schema_version"] != SCHEMA_VERSION
    ):
        raise HistoricalGoldbachTerminalError(
            "unsupported historical Goldbach branch summary"
        )
    checked = dict(row)
    for field in BRANCH_FIELDS - {"kind", "schema_version"}:
        checked[field] = _digest(row[field], f"branch summary {field}")
    return checked


def child_identity_commitment(
    identities: list[dict[str, Any]], branch_summary: Mapping[str, Any],
) -> dict[str, Any]:
    expected = expected_child_topology()
    if len(identities) != len(expected):
        raise HistoricalGoldbachTerminalError(
            "child identities do not cover every producer group"
        )
    checked = [
        validate_child_identity(item, phase=phase, shard_index=index)
        for item, (phase, index) in zip(identities, expected, strict=True)
    ]
    summary = validate_branch_summary(dict(branch_summary))
    return {
        "branch_summary": summary,
        "child_count": len(checked),
        "child_identities_sha256": hashlib.sha256(
            canonical_json_bytes(checked)
        ).hexdigest(),
        "kind": CHILD_COMMITMENT_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def validate_child_identity_commitment(value: Any) -> dict[str, Any]:
    row = _exact(
        value, COMMITMENT_FIELDS, "historical Goldbach child commitment"
    )
    if (
        row["kind"] != CHILD_COMMITMENT_KIND
        or row["schema_version"] != SCHEMA_VERSION
        or row["child_count"] != CHILD_COUNT
    ):
        raise HistoricalGoldbachTerminalError(
            "child commitment has wrong kind/version/count"
        )
    return {
        "branch_summary": validate_branch_summary(row["branch_summary"]),
        "child_count": CHILD_COUNT,
        "child_identities_sha256": _digest(
            row["child_identities_sha256"], "child identities"
        ),
        "kind": CHILD_COMMITMENT_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def load_child_identity_commitment(
    path: Path, *, expected_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    try:
        value = load_json(path, require_canonical=True)
        digest, _size = hash_file_once(path, limit=1024 * 1024)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachTerminalError(
            f"cannot load child identity commitment: {error}"
        ) from error
    if expected_sha256 is not None and digest != _digest(
        expected_sha256, "child commitment pin"
    ):
        raise HistoricalGoldbachTerminalError(
            "child identity commitment differs from its pin"
        )
    return validate_child_identity_commitment(value), digest


def _binary_branch(root: Path) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    plan_path = root / "binary/plan.json"
    receipts_root = root / "binary/receipts"
    aggregate_path = root / "binary/aggregate.json"
    plan = load_plan(plan_path)
    expected_plan = make_production_plan(
        executable_sha256=plan.executable_sha256
    )
    if (
        plan != expected_plan
        or plan.algorithm != PRODUCTION_ALGORITHM
        or len(plan.shards) != PRODUCTION_SHARDS
        or (plan.even_start, plan.even_limit)
        != (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT)
    ):
        raise HistoricalGoldbachTerminalError(
            "binary branch plan is not the exact source-height plan"
        )
    paths = binary_receipt_paths(receipts_root)
    if len(paths) != PRODUCTION_SHARDS:
        raise HistoricalGoldbachTerminalError(
            "binary branch omits source-plan leaf receipts"
        )
    receipts = [load_binary_receipt(path, plan=plan) for path in paths]
    aggregate_value = load_json(aggregate_path, require_canonical=True)
    aggregate = validate_binary_aggregate(
        aggregate_value, plan=plan, receipts=receipts
    )
    return plan, receipts, aggregate


def _ladder_branch(root: Path) -> tuple[Path, dict[str, Any]]:
    ladder = root / "ladder/campaign"
    if load_campaign(ladder) != CampaignParameters():
        raise HistoricalGoldbachTerminalError(
            "prime-ladder branch is not the exact full-source profile"
        )
    aggregate_path = root / "ladder/aggregate.json"
    value = load_json(aggregate_path, require_canonical=True)
    aggregate = validate_independent_aggregate(ladder, value)
    return ladder, aggregate


def branch_summary(
    root: Path,
    *,
    binary_plan: Any,
    binary_aggregate: Mapping[str, Any],
    ladder: Path,
    ladder_aggregate: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_branch_summary(
        {
            "binary_aggregate_file_sha256": hash_file_once(
                root / "binary/aggregate.json"
            )[0],
            "binary_aggregate_sha256": binary_aggregate["aggregate_sha256"],
            "binary_plan_sha256": binary_plan.plan_sha256,
            "binary_receipt_merkle_root_sha256": binary_aggregate[
                "receipt_merkle_root_sha256"
            ],
            "kind": BRANCH_SUMMARY_KIND,
            "ladder_aggregate_file_sha256": hash_file_once(
                root / "ladder/aggregate.json"
            )[0],
            "ladder_aggregate_sha256": ladder_aggregate["aggregate_sha256"],
            "ladder_manifest_sha256": hash_file_once(
                ladder / "manifest.json"
            )[0],
            "ladder_receipt_merkle_root_sha256": ladder_aggregate[
                "range_receipt_merkle_root_sha256"
            ],
            "schema_version": SCHEMA_VERSION,
        }
    )


def _bind_children_to_raw_artifacts(
    identities: list[dict[str, Any]],
    *,
    binary_plan: Any,
    binary_receipts: list[dict[str, Any]],
    ladder: Path,
) -> None:
    by_leaf = {
        int(receipt["shard"]["index"]): receipt["receipt_sha256"]
        for receipt in binary_receipts
    }
    for group_index in range(H100_GROUP_COUNT):
        identity = identities[group_index]
        indices = production_group_leaf_indices(binary_plan, group_index)
        expected = [by_leaf[index] for index in indices]
        if identity["payload_receipt_sha256s"] != expected:
            raise HistoricalGoldbachTerminalError(
                f"signed H100 group {group_index} differs from raw binary leaves"
            )
    ladder_offset = H100_GROUP_COUNT
    for group_index in range(LADDER_GROUP_COUNT):
        lower, upper = independent_group_bounds(
            CampaignParameters().range_count, group_index, LADDER_GROUP_COUNT
        )
        expected: list[str] = []
        expected_native: list[str] = []
        for range_index in range(lower, upper):
            value = load_json(
                ladder
                / "independent-receipts"
                / independent_receipt_filename(range_index),
                require_canonical=True,
            )
            expected.append(_digest(value["receipt_sha256"], "range receipt"))
            native = load_json(
                ladder
                / "native-producer-receipts"
                / native_receipt_filename(range_index),
                require_canonical=True,
            )
            if (
                not isinstance(native, dict)
                or "native_receipt_sha256" not in native
            ):
                raise HistoricalGoldbachTerminalError(
                    f"native producer receipt {range_index} is malformed"
                )
            expected_native.append(
                _digest(
                    native["native_receipt_sha256"],
                    "native producer receipt",
                )
            )
        identity = identities[ladder_offset + group_index]
        if (
            identity["payload_receipt_sha256s"] != expected
            or identity["auxiliary_receipt_sha256s"] != expected_native
        ):
            raise HistoricalGoldbachTerminalError(
                f"signed ladder group {group_index} differs from raw ordinary/native receipts"
            )


def replay_terminal_handoff(
    root: Path,
    *,
    child_commitment: Mapping[str, Any],
    key_manifest: Path,
    admission: Any,
    combined_output: Path | None = None,
    allow_development_key: bool = False,
) -> dict[str, Any]:
    """Verify signatures, exact coverage, branch bytes, and final reduction."""

    checked_commitment = validate_child_identity_commitment(
        dict(child_commitment)
    )
    try:
        plan, binary_receipts, binary_aggregate = _binary_branch(root)
        ladder, ladder_aggregate = _ladder_branch(root)
    except (
        CampaignError,
        CampaignIOError,
        GoldbachGPUCampaignError,
        OSError,
        ValueError,
    ) as error:
        if isinstance(error, HistoricalGoldbachTerminalError):
            raise
        raise HistoricalGoldbachTerminalError(
            f"historical Goldbach branch replay failed: {error}"
        ) from error
    summary = branch_summary(
        root,
        binary_plan=plan,
        binary_aggregate=binary_aggregate,
        ladder=ladder,
        ladder_aggregate=ladder_aggregate,
    )
    if summary != checked_commitment["branch_summary"]:
        raise HistoricalGoldbachTerminalError(
            "branch bytes differ from the post-run child commitment"
        )
    identities = load_verified_child_identities(
        root,
        index_path=root / "children/index.json",
        key_manifest=key_manifest,
        admission=admission,
        ladder_manifest_sha256=summary["ladder_manifest_sha256"],
        allow_development_key=allow_development_key,
    )
    identities_sha256 = hashlib.sha256(
        canonical_json_bytes(identities)
    ).hexdigest()
    if identities_sha256 != checked_commitment["child_identities_sha256"]:
        raise HistoricalGoldbachTerminalError(
            "signed child identities differ from the terminal commitment"
        )
    _bind_children_to_raw_artifacts(
        identities,
        binary_plan=plan,
        binary_receipts=binary_receipts,
        ladder=ladder,
    )
    combined = combine_with_hardened_binary_goldbach(
        ladder,
        ladder_aggregate_path=root / "ladder/aggregate.json",
        binary_plan_path=root / "binary/plan.json",
        binary_receipts_directory=root / "binary/receipts",
        binary_aggregate_path=root / "binary/aggregate.json",
        output_path=combined_output,
    )
    return {
        "branch_summary": summary,
        "child_count": len(identities),
        "child_identities_sha256": identities_sha256,
        "combined": combined,
    }


def prepare_terminal_handoff_commitment(
    root: Path,
    *,
    key_manifest: Path,
    admission: Any,
    allow_development_key: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate a complete pre-terminal tree and construct its commitment.

    This is the non-circular preparation boundary used before packaging the
    measured terminal input.  It checks every retained branch artifact and
    every signed child, binds the signed receipt hashes to the retained
    mathematical receipts, and only then returns a commitment suitable for
    inclusion in the terminal's measured artifact closure.
    """

    try:
        plan, binary_receipts, binary_aggregate = _binary_branch(root)
        ladder, ladder_aggregate = _ladder_branch(root)
    except (
        CampaignError,
        CampaignIOError,
        GoldbachGPUCampaignError,
        OSError,
        ValueError,
    ) as error:
        if isinstance(error, HistoricalGoldbachTerminalError):
            raise
        raise HistoricalGoldbachTerminalError(
            f"historical Goldbach branch preparation failed: {error}"
        ) from error
    summary = branch_summary(
        root,
        binary_plan=plan,
        binary_aggregate=binary_aggregate,
        ladder=ladder,
        ladder_aggregate=ladder_aggregate,
    )
    identities = load_verified_child_identities(
        root,
        index_path=root / "children/index.json",
        key_manifest=key_manifest,
        admission=admission,
        ladder_manifest_sha256=summary["ladder_manifest_sha256"],
        allow_development_key=allow_development_key,
    )
    _bind_children_to_raw_artifacts(
        identities,
        binary_plan=plan,
        binary_receipts=binary_receipts,
        ladder=ladder,
    )
    commitment = child_identity_commitment(identities, summary)
    return commitment, identities


__all__ = [
    "BRANCH_SUMMARY_KIND",
    "CAMPAIGN_ID",
    "CHILD_COMMITMENT_KIND",
    "CHILD_COUNT",
    "CHILD_INDEX_KIND",
    "H100_GROUP_COUNT",
    "H100_PHASE",
    "HistoricalGoldbachTerminalError",
    "LADDER_GROUP_COUNT",
    "LADDER_PHASE",
    "NOT_APPLICABLE_DIGEST",
    "branch_summary",
    "child_identity_commitment",
    "expected_child_topology",
    "ladder_group_definition",
    "ladder_group_identity",
    "load_child_identity_commitment",
    "load_verified_child_identities",
    "prepare_terminal_handoff_commitment",
    "replay_terminal_handoff",
    "validate_branch_summary",
    "validate_child_identity",
    "validate_child_identity_commitment",
]
