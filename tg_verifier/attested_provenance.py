# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Attested-provenance N-way replication records.

This module implements the *execution* layer of the attested-provenance trust
model: the same campaign run k times on independent, non-confidential
capacity, with every replica's Merkle root compared.

It is a deliberate sibling of the signed trusted-compute receipt used by the
``azure_sevsnp_cpu`` and ``azure_ncc40ads_h100_v5`` backends, not a
replacement for it and not an extension of it.  Concretely:

- ``schemas/trusted-compute-receipt.schema.json`` is untouched, and
  ``attested_provenance_replicated`` is deliberately absent from its
  ``backend`` enum;
- ``tools/trusted_compute_receipt.py`` ``BACKENDS`` is untouched, so this
  record can never be issued as a signed receipt, admitted to
  ``TrustedComputeRegistry.lean``, or reach
  ``accepted_run_certificate_sound``; and
- the record's own ``authority`` block asserts all of that in machine-readable
  form, and this validator rejects a record that tries to claim otherwise.

What a passing record establishes: k runs, whose binaries were built from a
named source commit by an attested workflow, independently produced the same
Merkle root and the same output digest.

What it does not establish: that the computation is mathematically correct
(the Lean certificate layer answers that, unchanged); that any hardware
behaved as specified; that a cloud host did not tamper with all k replicas; or
that the record's author did not fabricate replicas they control.  The
independence thresholds are the only defence against the last two, and they
are policy, not cryptography.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised only when the dependency is absent
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_PATH = (
    REPOSITORY_ROOT / "schemas" / "attested-provenance-record.schema.json"
)

RECORD_KIND = "sparkinterval.attested-provenance-replication-record.v1"

BACKEND = "attested_provenance_replicated"

TRUST_PROFILE_PATH = (
    REPOSITORY_ROOT / "profiles" / "trust" / "attested_provenance_replicated.json"
)

TARGET_PROFILE_PATHS = {
    "replicated_public_cloud_cpu": (
        REPOSITORY_ROOT / "profiles" / "targets" / "replicated_public_cloud_cpu.json"
    ),
    "replicated_public_cloud_gpu": (
        REPOSITORY_ROOT / "profiles" / "targets" / "replicated_public_cloud_gpu.json"
    ),
}

# The signed trusted-compute receipt backends.  Listed here only so that the
# validator can prove this record is not one of them.
CONFIDENTIAL_COMPUTE_BACKENDS = ("azure_sevsnp_cpu", "azure_ncc40ads_h100_v5")


class AttestedProvenanceError(ValueError):
    """The replication record is malformed or fails its own policy."""


def _load_json(path: Path, description: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise AttestedProvenanceError(f"cannot read {description}: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise AttestedProvenanceError(f"{description} is not JSON: {error}") from error


def validate_schema(document: Any) -> None:
    """Structurally validate a record against the checked-in schema."""

    if jsonschema is None:
        raise AttestedProvenanceError(
            "jsonschema is required to validate an attested-provenance record"
        )
    schema = _load_json(SCHEMA_PATH, "attested-provenance record schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(document, schema)
    except jsonschema.exceptions.SchemaError as error:  # pragma: no cover
        raise AttestedProvenanceError(f"schema is invalid: {error.message}") from error
    except jsonschema.exceptions.ValidationError as error:
        location = "$" + "".join(f"[{part!r}]" for part in error.absolute_path)
        raise AttestedProvenanceError(
            f"record is not schema-valid at {location}: {error.message}"
        ) from error


def _check_profiles(document: dict[str, Any], failures: list[str]) -> None:
    target = document["target_profile"]
    target_path = TARGET_PROFILE_PATHS.get(target)
    if target_path is None or not target_path.is_file():
        failures.append(f"unknown target profile {target}")
    else:
        profile = _load_json(target_path, f"target profile {target}")
        if profile.get("profile_id") != target:
            failures.append(f"target profile {target} has a different profile_id")
        classes = profile.get("allowed_evidence_classes") or []
        if "hardware_attested" in classes:
            failures.append(
                f"target profile {target} must not allow hardware_attested "
                "evidence under this model"
            )
    if not TRUST_PROFILE_PATH.is_file():
        failures.append("missing trust profile attested_provenance_replicated")
        return
    trust = _load_json(TRUST_PROFILE_PATH, "trust profile")
    if trust.get("production_hardware_evidence") is not False:
        failures.append(
            "trust profile must report production_hardware_evidence false"
        )
    if target not in (trust.get("allowed_target_profiles") or []):
        failures.append(f"trust profile does not allow target profile {target}")


def _check_agreement(document: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    claim = document["claim"]
    replicas = document["replicas"]
    policy = document["policy"]

    replica_ids = [replica["replica_id"] for replica in replicas]
    duplicates = sorted(
        name for name, count in Counter(replica_ids).items() if count > 1
    )
    if duplicates:
        failures.append(f"duplicate replica_id values: {duplicates}")

    roots = sorted({replica["execution"]["merkle_root"] for replica in replicas})
    outputs = sorted({replica["execution"]["output_hash"] for replica in replicas})
    if len(roots) != 1:
        failures.append(
            f"replicas disagree on the Merkle root: {len(roots)} distinct values"
        )
    elif roots[0] != claim["merkle_root"]:
        failures.append(
            "the agreed replica Merkle root differs from the record's claim"
        )
    if len(outputs) != 1:
        failures.append(
            f"replicas disagree on the output digest: {len(outputs)} distinct values"
        )
    elif outputs[0] != claim["output_hash"]:
        failures.append(
            "the agreed replica output digest differs from the record's claim"
        )

    implementations = sorted({r["implementation_id"] for r in replicas})
    operators = sorted({r["operator_id"] for r in replicas})
    providers = sorted({r["provider_id"] for r in replicas})

    if len(replicas) < policy["minimum_replicas"]:
        failures.append(
            f"{len(replicas)} replicas is below the declared minimum "
            f"{policy['minimum_replicas']}"
        )
    if len(implementations) < policy["minimum_distinct_implementations"]:
        failures.append(
            f"{len(implementations)} distinct implementations is below the "
            f"declared minimum {policy['minimum_distinct_implementations']}"
        )
    if len(operators) < policy["minimum_distinct_operators"]:
        failures.append(
            f"{len(operators)} distinct operators is below the declared "
            f"minimum {policy['minimum_distinct_operators']}"
        )
    if len(providers) < policy["minimum_distinct_providers"]:
        failures.append(
            f"{len(providers)} distinct providers is below the declared "
            f"minimum {policy['minimum_distinct_providers']}"
        )

    third_party = [r["replica_id"] for r in replicas if r["operator_is_third_party"]]
    if policy["require_third_party_replica"] and not third_party:
        failures.append(
            "the policy requires at least one replica run by a third party, "
            "and none is recorded"
        )

    # Two replicas that name the same implementation must have run the same
    # bytes.  Otherwise "same implementation" is a label, not a fact.
    by_implementation: dict[str, set[tuple[str, ...]]] = {}
    for replica in replicas:
        digests = tuple(
            sorted(
                f"{artifact['name']}:{artifact['sha256']}"
                for artifact in replica["build_provenance"]["artifacts"]
            )
        )
        by_implementation.setdefault(replica["implementation_id"], set()).add(digests)
    for implementation, digest_sets in sorted(by_implementation.items()):
        if len(digest_sets) > 1:
            failures.append(
                f"implementation {implementation} ran {len(digest_sets)} "
                "different artifact sets across replicas"
            )

    return {
        "distinct_implementations": implementations,
        "distinct_merkle_roots": len(roots),
        "distinct_operators": operators,
        "distinct_output_hashes": len(outputs),
        "distinct_providers": providers,
        "replica_count": len(replicas),
        "third_party_replicas": sorted(third_party),
    }


def _check_build_provenance(
    document: dict[str, Any], failures: list[str]
) -> dict[str, Any]:
    policy = document["policy"]
    commits: set[str] = set()
    repositories: set[str] = set()
    workflow_refs: set[str] = set()
    unverified: list[str] = []
    missing_log: list[str] = []
    self_hosted: list[str] = []
    claimed_l3: list[str] = []

    for replica in document["replicas"]:
        provenance = replica["build_provenance"]
        commits.add(provenance["source_commit"])
        repositories.add(provenance["repository"])
        workflow_refs.add(provenance["workflow_ref"])
        if provenance["verification"]["accepted"] is not True:
            unverified.append(replica["replica_id"])
        if "transparency_log" not in provenance:
            missing_log.append(replica["replica_id"])
        if provenance.get("runner_environment") == "self-hosted":
            self_hosted.append(replica["replica_id"])
        if provenance.get("slsa_build_level") == "L3":
            claimed_l3.append(replica["replica_id"])

    if policy["require_build_provenance_verified"] and unverified:
        failures.append(
            "build provenance was not verified for replicas: "
            f"{sorted(unverified)}"
        )
    if policy["require_transparency_log_entry"] and missing_log:
        failures.append(
            "no transparency-log entry recorded for replicas: "
            f"{sorted(missing_log)}"
        )
    if claimed_l3:
        # The prototype workflow in this repository is Build L2.  A record
        # claiming L3 must come from a trusted reusable generator; refuse the
        # unsupported claim rather than let it inflate the trust story.
        failures.append(
            "replicas claim SLSA Build L3, which this repository's provenance "
            f"lane does not produce: {sorted(claimed_l3)}"
        )

    return {
        "distinct_source_commits": sorted(commits),
        "repositories": sorted(repositories),
        "self_hosted_replicas": sorted(self_hosted),
        "workflow_refs": sorted(workflow_refs),
    }


def _check_authority(document: dict[str, Any], failures: list[str]) -> None:
    authority = document["authority"]
    asserted = sorted(key for key, value in authority.items() if value is not False)
    if asserted:
        failures.append(
            "an attested-provenance record may not assert authority: "
            f"{asserted}"
        )
    if document["backend"] in CONFIDENTIAL_COMPUTE_BACKENDS:
        failures.append(
            "this record type must not reuse a confidential-compute backend "
            "identifier"
        )


def validate_record(document: Any) -> dict[str, Any]:
    """Validate a record and return its machine-readable evaluation.

    Raises :class:`AttestedProvenanceError` for a structurally invalid
    document.  A structurally valid document that fails its own declared
    independence policy is *returned* with ``accepted: false`` and an explicit
    failure list rather than raised, so a caller can report exactly which
    threshold was missed.
    """

    validate_schema(document)
    assert isinstance(document, dict)

    failures: list[str] = []
    _check_authority(document, failures)
    _check_profiles(document, failures)
    agreement = _check_agreement(document, failures)
    provenance = _check_build_provenance(document, failures)

    return {
        "accepted": not failures,
        "agreement": agreement,
        "authority": {
            "authorizes_lean_theorem": False,
            "establishes_hardware_evidence": False,
            "is_confidential_compute_evidence": False,
            "proves_mathematical_correctness": False,
            "reaches_accepted_run_certificate_sound": False,
            "resists_malicious_cloud_host": False,
        },
        "backend": document["backend"],
        "build_provenance": provenance,
        "campaign_id": document["campaign_id"],
        "claim_merkle_root": document["claim"]["merkle_root"],
        "failures": failures,
        "kind": "sparkinterval.attested-provenance-validation.v1",
        "policy": document["policy"],
        "record_kind": document["record_kind"],
        "schema_version": 1,
        "status": (
            "replication_agreement_recorded" if not failures else "record_rejected"
        ),
        "target_profile": document["target_profile"],
        "trust_profile": document["trust_profile"],
    }


def load_and_validate(path: Path) -> dict[str, Any]:
    """Load a replication record from ``path`` and validate it."""

    document = _load_json(path, f"replication record {path}")
    return validate_record(document)
