# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed H100 factory for one lowered finite-Goldbach worker group.

Each of the 8,192 jobs runs exactly eight strided leaves from the immutable
65,536-leaf plan.  These are operational receipts: they are authenticated DAG
inputs, not direct Lean theorems.  The CPU finalizer is the only registered
semantic invocation in this campaign.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from tg_verifier.azure_cpu_goldbach_10pow27_workload_factory import (
    CAMPAIGN_ID,
    OWNER_ATOM_ID,
    PLAN,
    RECEIPTS,
)
from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_build_admission import (
    GOLDBACH_H100_ALGORITHM_PREFIX,
    GoldbachBuildAdmission,
    goldbach_execution_projection_sha256,
)
from tg_verifier.goldbach_gpu_campaign import (
    ANALYTIC_10POW27_ALGORITHM,
    ANALYTIC_10POW27_EVEN_LIMIT,
    ANALYTIC_10POW27_EVEN_START,
    PRODUCTION_GROUPS,
)


PHASE_ID = "h100-8192-groups-of-eight-lowered-checkpoint-leaves"
GROUP_ID = f"{CAMPAIGN_ID}::{PHASE_ID}"
SHARD_COUNT = 8_192
PHASE_DEPENDENCIES = (f"{CAMPAIGN_ID}::create-lowered-binary-plan",)
BINARY_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_gpu_campaign.py"
PORTFOLIO_ARGV = (
    "${TG_PYTHON}", BINARY_TOOL, "run-group", PLAN, "${TG_ARRAY_INDEX}",
    "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
    "--executable", "${TG_GOLDBACH_EXECUTABLE}",
    "--output-dir", RECEIPTS,
    "--cuda-visible-device", "0",
)

SOURCE_PATHS = (
    "tools/tg_goldbach_10pow27_h100_measured_workload.py",
    "tools/tg_goldbach_gpu_campaign.py",
    "tg_verifier/azure_cpu_goldbach_10pow27_workload_factory.py",
    "tg_verifier/azure_h100_goldbach_10pow27_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/goldbach_build_admission.py",
    "tg_verifier/goldbach_gpu_campaign.py",
    "attestation/azure_h100_pre_run_gate.py",
    "attestation/collect_azure_ncc_evidence.py",
    "attestation/measured_run_archive.py",
    "gpu/include/sparkinterval/sha256.hpp",
    "patches/goldbach-gpu/b58b2dea-hardening.patch",
    "specifications/GOLDBACH_GPU_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.goldbach10pow27-h100-group.v1\n"
    "initial=SHA256(group-challenge-job-input-plan-executable-source)\n"
    "step-0=SHA256(previous-retained-archive-retained-tree)\n"
    "step-1=SHA256(previous-canonical-eight-leaf-result)\n"
    "verification=independent-plan-receipt-result-and-retained-export-replay"
)


def algorithm_definition(
    group_index: int, admission: GoldbachBuildAdmission,
) -> str:
    if not 0 <= group_index < SHARD_COUNT:
        raise ValueError("lowered H100 group index is outside the reviewed plan")
    projection_sha256 = expected_execution_projection_sha256(
        group_index, admission
    )
    return (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\n"
        f"phase={PHASE_ID}\n"
        f"group-index={group_index}\n"
        f"build-admission-sha256={admission.admission_sha256}\n"
        f"build-identity-sha256={admission.build_identity_sha256}\n"
        f"binary-source-identity={admission.core['source_identity_sha256']}\n"
        f"python-sha256={admission.core['python']['sha256']}\n"
        f"nvcc-sha256={admission.core['nvcc']['sha256']}\n"
        f"host-cxx-sha256={admission.core['host_cxx']['sha256']}\n"
        f"build-argv-sha256={admission.core['build_argv_sha256']}\n"
        f"executable-sha256={admission.core['executable']['sha256']}\n"
        "immutable-image-reference-sha256="
        f"{admission.deployment['immutable_image_reference_sha256']}\n"
        "runtime-image-closure-sha256="
        f"{admission.deployment['runtime_image_closure_sha256']}\n"
        "artifact-closure-manifest-sha256="
        f"{admission.expected_artifacts['artifact_closure_manifest_sha256']}\n"
        f"source-tree-sha256={admission.expected_artifacts['source_tree_hash']}\n"
        f"job-derivation-sha256={admission.core['job_derivation_sha256']}\n"
        f"execution-projection-sha256={projection_sha256}\n"
        "semantics=run-eight-strided-lowered-checkpoint-leaves-and-retain-receipts\n"
        "output=exact-eight-receipt-hash-list"
    )


def input_value(
    group_index: int, admission: GoldbachBuildAdmission,
) -> dict[str, Any]:
    return {
        "artifact_closure_manifest_sha256": admission.expected_artifacts[
            "artifact_closure_manifest_sha256"
        ],
        "build_admission_sha256": admission.admission_sha256,
        "build_identity_sha256": admission.build_identity_sha256,
        "campaign_id": CAMPAIGN_ID,
        "executable_sha256": admission.core["executable"]["sha256"],
        "group_index": group_index,
        "immutable_image_reference_sha256": admission.deployment[
            "immutable_image_reference_sha256"
        ],
        "phase": PHASE_ID,
        "runtime_image_closure_sha256": admission.deployment[
            "runtime_image_closure_sha256"
        ],
        "source_identity_sha256": admission.core["source_identity_sha256"],
    }


def parameters_value() -> dict[str, Any]:
    return {
        "cuda_visible_device": 0,
        "leaf_count": 8,
        "scheduler_group_count": PRODUCTION_GROUPS,
    }


def domain_value(group_index: int) -> dict[str, Any]:
    return {
        "algorithm": ANALYTIC_10POW27_ALGORITHM,
        "even_limit_inclusive": ANALYTIC_10POW27_EVEN_LIMIT,
        "even_start_inclusive": ANALYTIC_10POW27_EVEN_START,
        "group_index": group_index,
    }


def h100_expected_claim_identity(
    group_index: int, admission: GoldbachBuildAdmission,
) -> dict[str, str]:
    definition = algorithm_definition(group_index, admission)
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return {
        "algorithm_hash": suffix,
        "algorithm_id": f"{GOLDBACH_H100_ALGORITHM_PREFIX}{suffix}",
        "domain_hash": hashlib.sha256(
            canonical_json_bytes(domain_value(group_index))
        ).hexdigest(),
        "input_hash": hashlib.sha256(
            canonical_json_bytes(input_value(group_index, admission))
        ).hexdigest(),
        "parameters_hash": hashlib.sha256(
            canonical_json_bytes(parameters_value())
        ).hexdigest(),
    }


@dataclass(frozen=True)
class Goldbach10Pow27H100WorkloadFactory:
    factory_id: str
    phase_id: str
    group_id: str
    shard_index: int
    shard_count: int
    registered_invocation: None
    portfolio_argv: tuple[str, ...]
    algorithm_id: str
    algorithm_definition: str
    input_bytes: bytes
    parameters: dict[str, Any]
    domain: dict[str, Any]
    command_argv: tuple[str, ...]
    trace_verifier_argv: tuple[str, ...]
    timeout_seconds: int
    output_format: str
    output_maximum_bytes: int


def _measured_argv(mode: str, group_index: int, algorithm_id: str) -> tuple[str, ...]:
    return (
        "artifacts/python3", "-I",
        "tools/tg_goldbach_10pow27_h100_measured_workload.py", mode,
        "--group-index", str(group_index),
        "--algorithm-id", algorithm_id,
        "--challenge", "@challenge@",
        "--job-binding", "@job_binding@",
        "--input", "@input@",
        "--output", "@output@",
        "--trace", "@trace@",
        "--work", f"work/goldbach10pow27-h100-{group_index:08d}",
        "--plan", "plans/binary-plan.json",
        "--build-identity", "source/goldbach-build-identity.json",
        "--runtime-image-closure", "source/goldbach-runtime-image-closure.json",
        "--source-root", "source/goldbach-gpu-hardened",
        "--executable", "artifacts/goldbach-gpu",
        "--cuda-visible-device", "0",
    )


def _projection_job(
    group_index: int, admission: GoldbachBuildAdmission,
) -> dict[str, Any]:
    """Construct the exact non-algorithm job projection before identity hashing."""

    if not 0 <= group_index < SHARD_COUNT:
        raise ValueError("lowered H100 group index is outside the reviewed plan")
    placeholder_id = f"{GOLDBACH_H100_ALGORITHM_PREFIX}{'a' * 64}"
    input_bytes = canonical_json_bytes(input_value(group_index, admission))
    deployment = admission.deployment
    return {
        "algorithm": {
            "algorithm_id": placeholder_id,
            "canonical_definition": "excluded-from-execution-projection",
            "definition_sha256": "a" * 64,
        },
        "artifact_closure": {
            "closure_kind": "content_addressed_image_source_reviewed_v1",
            "files": [],
            "manifest_sha256": admission.expected_artifacts[
                "artifact_closure_manifest_sha256"
            ],
        },
        "backend": "azure_ncc40ads_h100_v5",
        "command": {
            "argv": list(_measured_argv("run", group_index, placeholder_id)),
            "cwd": ".",
            "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "timeout_seconds": 24 * 3600,
        },
        "domain_coverage": {
            "canonical_sha256": hashlib.sha256(
                canonical_json_bytes(domain_value(group_index))
            ).hexdigest(),
            "value": domain_value(group_index),
        },
        "gpu_pre_run_gate": {
            "argv": [
                "artifacts/python3", "-I", "-B",
                "attestation/azure_h100_pre_run_gate.py",
                "--challenge-nonce", "@challenge@",
                "--challenge-expires-at", "@challenge_expires_at@",
                "--job-binding", "@job_binding@",
                "--package-root", ".",
                "--record-path", "@gate_record@",
                "--policy", "profiles/nvidia-gpu.rego",
                "--verifier", deployment["gpu_verifier"],
                "--nras-url", deployment["nras_url"],
            ],
            "record_path": "runner/h100-pre-run-gate.json",
            "required": True,
            "secret_environment_names": ["NV_ATTESTATION_SERVICE_KEY"],
            "timeout_seconds": 600,
        },
        "input_artifact": {
            "path": "input/group.json",
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": hashlib.sha256(input_bytes).hexdigest(),
            "size_bytes": len(input_bytes),
        },
        "job_id": f"tg-goldbach10pow27-h100-{group_index:08d}-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": "opaque_bytes_v1",
            "maximum_bytes": 8 * 1024,
            "path": "output/group-result.json",
        },
        "parameters": {
            "canonical_sha256": hashlib.sha256(
                canonical_json_bytes(parameters_value())
            ).hexdigest(),
            "value": parameters_value(),
        },
        "runner_policy": {
            "path": "profiles/runner-policy.json",
            "policy_id": deployment["runner_policy_id"],
            "sha256": deployment["runner_policy_sha256"],
        },
        "schema_version": 1,
        "target_profile": {
            "path": "profiles/target.json",
            "profile_id": deployment["target_profile_id"],
            "sha256": deployment["target_profile_sha256"],
        },
        "tpm_policy": {
            "ak_handle": "0x81000003",
            "bank": "sha256",
            "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": {
            "path": "profiles/trust.json",
            "profile_id": deployment["trust_profile_id"],
            "sha256": deployment["trust_profile_sha256"],
        },
        "work_trace_contract": {
            "expected_iterations": 2,
            "format": "challenge_sha256_chain_json_v1",
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": TRACE_DEFINITION,
            "trace_algorithm_sha256": hashlib.sha256(
                TRACE_DEFINITION.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(
                _measured_argv("verify-trace", group_index, placeholder_id)
            ),
        },
    }


def expected_execution_projection_sha256(
    group_index: int, admission: GoldbachBuildAdmission,
) -> str:
    return goldbach_execution_projection_sha256(
        _projection_job(group_index, admission)
    )


def make_factory(
    group_index: int, admission: GoldbachBuildAdmission,
) -> Goldbach10Pow27H100WorkloadFactory:
    identity = h100_expected_claim_identity(group_index, admission)
    definition = algorithm_definition(group_index, admission)
    return Goldbach10Pow27H100WorkloadFactory(
        factory_id=f"goldbach10pow27_h100_group_{group_index:08d}_v1",
        phase_id=PHASE_ID,
        group_id=GROUP_ID,
        shard_index=group_index,
        shard_count=SHARD_COUNT,
        registered_invocation=None,
        portfolio_argv=PORTFOLIO_ARGV,
        algorithm_id=identity["algorithm_id"],
        algorithm_definition=definition,
        input_bytes=canonical_json_bytes(input_value(group_index, admission)),
        parameters=parameters_value(),
        domain=domain_value(group_index),
        command_argv=_measured_argv("run", group_index, identity["algorithm_id"]),
        trace_verifier_argv=_measured_argv(
            "verify-trace", group_index, identity["algorithm_id"]
        ),
        timeout_seconds=24 * 3600,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=8 * 1024,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any],
    shard_index: int,
    admission: GoldbachBuildAdmission | None = None,
) -> Goldbach10Pow27H100WorkloadFactory | None:
    if admission is None:
        return None
    try:
        factory = make_factory(shard_index, admission)
    except ValueError:
        return None
    if not portfolio_group_shape_matches(group):
        return None
    return factory


def portfolio_group_shape_matches(group: Mapping[str, Any]) -> bool:
    """Check the static route before a site-specific admission is loaded."""

    return not (
        group.get("campaign_id") != CAMPAIGN_ID
        or group.get("phase_id") != PHASE_ID
        or group.get("group_id") != GROUP_ID
        or group.get("backend_class") != "h100_cuda"
        or group.get("receipt_backend") != "azure_ncc40ads_h100_v5"
        or group.get("owner_atom_id") != OWNER_ATOM_ID
        or group.get("operator_adapter") != "azure/h100_production_orchestrator.py"
        or group.get("shard_count") != SHARD_COUNT
        or group.get("terminal") is not False
        or group.get("semantic_binding") is not None
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES
        or tuple(group.get("command_template", ())) != PORTFOLIO_ARGV
    )


def source_reviewed_materializer_available(
    group: Mapping[str, Any],
    admission: GoldbachBuildAdmission | None = None,
) -> bool:
    if admission is None:
        return False
    return all(
        factory_for_portfolio_group(group, index, admission) is not None
        for index in range(SHARD_COUNT)
    )


__all__ = [
    "CAMPAIGN_ID", "GROUP_ID", "PHASE_ID", "PORTFOLIO_ARGV", "SHARD_COUNT",
    "SOURCE_PATHS", "TRACE_DEFINITION", "algorithm_definition",
    "expected_execution_projection_sha256", "factory_for_portfolio_group",
    "h100_expected_claim_identity", "input_value", "make_factory",
    "portfolio_group_shape_matches", "source_reviewed_materializer_available",
]
