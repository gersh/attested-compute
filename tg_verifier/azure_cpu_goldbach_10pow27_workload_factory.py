# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU factories for the lowered finite-Goldbach Azure DAG.

The seven CPU phase groups are deliberately distinct from the H100 binary
worker group.  Operational phases retain a replayable archive; only the last
phase uses the registered ``goldbach10Pow27ProductionV1`` identity and may
emit the literal registered result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_gpu_campaign import (
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
)


CAMPAIGN_ID = "ternary-goldbach-finite-below-10pow27-v1"
OWNER_ATOM_ID = "goldbach-finite-below-10pow27"
REGISTERED_INVOCATION = "goldbach10Pow27ProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.finite-below-10pow27.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-finite-below-10pow27\n"
    "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_10pow27_campaign.py+tools/tg_goldbach_10pow27_finalizer.py\n"
    "semantics=complete-word-indexed-lowered-binary-goldbach-coverage-plus-checked-n45-prime-ladder-evidence\n"
    "binary-campaign=goldbach-gpu-analytic-10pow27-production-65536-leaf-v1\n"
    "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n"
    f"binary-source-identity={EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256}\n"
    "ladder-campaign=analytic_10pow27\n"
    "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n"
    "combined-artifact=tg_goldbach_10pow27_gpu_plus_ladder_result_v1\n"
    "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n"
    "source-realization=external-branch-artifacts-to-exact-word-campaign-and-checked-ladder-evidence\n"
    "output=false-or-true-with-checked-campaign-evidence"
)
REGISTERED_INPUT = (
    '{"binary_artifact_kind":"sparkinterval.goldbach-gpu-aggregate.v1",'
    '"binary_campaign":"goldbach-gpu-analytic-10pow27-production-65536-leaf-v1",'
    f'"binary_source_identity_sha256":"{EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256}",'
    '"campaign":"ternary-goldbach-finite-below-10pow27-v1",'
    '"combined_artifact_kind":"tg_goldbach_10pow27_gpu_plus_ladder_result_v1",'
    '"ladder_artifact_kind":"tg_goldbach_ladder_parallel_aggregate_v1",'
    '"ladder_campaign":"analytic_10pow27",'
    '"semantic_target_inclusive":1000000000000000000000000000}'
).encode("ascii")
REGISTERED_PARAMETERS: dict[str, Any] = {
    "binary_even_count": 15_624_999_999_999_999,
    "binary_leaves_per_group": 8,
    "binary_shards": 65_536,
    "h100_groups": 8_192,
    "ladder_maximum_gap": 31_250_000_000_000_000,
    "ladder_proth_exponent": 45,
    "ladder_range_count": 7_106,
    "ladder_range_width": 140_737_488_355_328_000_000_000,
    "ladder_scheduled_endpoint": 1_000_080_592_252_960_768_000_000_000,
    "ladder_sieve_bound": 16_000,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "binary_even_lower": 4,
    "binary_even_upper": 31_250_000_000_000_000,
    "claim": "ternary-goldbach-finite-below-10pow27",
    "source_lower": 7,
    "source_upper": 1_000_000_000_000_000_000_000_000_000,
}
REGISTERED_OUTPUT = b"true"

WORKSPACE = "${TG_RUN_ROOT}/goldbach-finite-below-10pow27"
PLAN = f"{WORKSPACE}/binary-plan.json"
RECEIPTS = f"{WORKSPACE}/binary-receipts"
AGGREGATE = f"{WORKSPACE}/binary-aggregate.json"
LADDER = f"{WORKSPACE}/prime-ladder"
LADDER_AGGREGATE = f"{LADDER}/ladder-aggregate.json"
COMBINED = f"{WORKSPACE}/combined.json"
REGISTERED_RESULT = f"{WORKSPACE}/registered-result.txt"
BINARY_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_gpu_campaign.py"
CAMPAIGN_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_10pow27_campaign.py"
LADDER_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_campaign.py"
NATIVE_LADDER_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_ladder_native.py"
FINALIZER_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_10pow27_finalizer.py"

PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "create-lowered-binary-plan": (
        "${TG_PYTHON}", BINARY_TOOL, "create-analytic-10pow27-plan",
        "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
        "--executable", "${TG_GOLDBACH_EXECUTABLE}",
        "--executable-sha256", "${TG_GOLDBACH_EXECUTABLE_SHA256}",
        "--out", PLAN,
    ),
    "initialize-lowered-prime-ladder": (
        "${TG_PYTHON}", CAMPAIGN_TOOL, "init-ladder", LADDER,
    ),
    "native-lowered-prime-ladder-range-groups": (
        "${TG_PYTHON}", NATIVE_LADDER_TOOL, "produce-group", LADDER,
        "--runner", "${TG_TG_BUILD}/sparkinterval-tg-goldbach-ladder-native",
        "--group-index", "${TG_ARRAY_INDEX}", "--group-count", "320",
        "--local-workers", "40", "--summary",
        f"{LADDER}/groups/group-${{TG_ARRAY_INDEX}}.json",
    ),
    "aggregate-lowered-binary-leaves": (
        "${TG_PYTHON}", BINARY_TOOL, "aggregate", PLAN,
        "--receipts-dir", RECEIPTS, "--out", AGGREGATE,
    ),
    "replay-lowered-binary-aggregate": (
        "${TG_PYTHON}", BINARY_TOOL, "verify", PLAN, AGGREGATE,
        "--receipts-dir", RECEIPTS,
    ),
    "reduce-lowered-prime-ladder-ranges": (
        "${TG_PYTHON}", LADDER_TOOL, "reduce-ranges", LADDER,
        "--out", LADDER_AGGREGATE,
    ),
    "measured-finalize-lowered-source-claim": (
        "${TG_PYTHON}", FINALIZER_TOOL, LADDER,
        "--ladder-aggregate", LADDER_AGGREGATE,
        "--binary-plan", PLAN, "--binary-receipts-dir", RECEIPTS,
        "--binary-aggregate", AGGREGATE, "--combined-out", COMBINED,
        "--registered-result-output", REGISTERED_RESULT,
    ),
}
PHASE_COUNTS = {
    "create-lowered-binary-plan": 1,
    "initialize-lowered-prime-ladder": 1,
    "native-lowered-prime-ladder-range-groups": 320,
    "aggregate-lowered-binary-leaves": 1,
    "replay-lowered-binary-aggregate": 1,
    "reduce-lowered-prime-ladder-ranges": 1,
    "measured-finalize-lowered-source-claim": 1,
}
PHASE_DEPENDENCIES = {
    "create-lowered-binary-plan": (),
    "initialize-lowered-prime-ladder": (),
    "native-lowered-prime-ladder-range-groups": (
        f"{CAMPAIGN_ID}::initialize-lowered-prime-ladder",
    ),
    "aggregate-lowered-binary-leaves": (
        f"{CAMPAIGN_ID}::h100-8192-groups-of-eight-lowered-checkpoint-leaves",
    ),
    "replay-lowered-binary-aggregate": (
        f"{CAMPAIGN_ID}::aggregate-lowered-binary-leaves",
    ),
    "reduce-lowered-prime-ladder-ranges": (
        f"{CAMPAIGN_ID}::native-lowered-prime-ladder-range-groups",
    ),
    "measured-finalize-lowered-source-claim": (
        f"{CAMPAIGN_ID}::reduce-lowered-prime-ladder-ranges",
        f"{CAMPAIGN_ID}::replay-lowered-binary-aggregate",
    ),
}

SOURCE_PATHS = (
    "tools/tg_goldbach_10pow27_azure_measured_workload.py",
    "tools/tg_goldbach_10pow27_campaign.py",
    "tools/tg_goldbach_10pow27_finalizer.py",
    "tools/tg_goldbach_gpu_campaign.py",
    "tools/tg_goldbach_campaign.py",
    "tools/tg_goldbach_ladder_native.py",
    "tools/generate_trusted_compute_lean.py",
    "tools/trusted_compute_receipt.py",
    "tools/create_run_bundle.py",
    "tools/verify_run_bundle.py",
    "tools/local_operator_signature.py",
    "tg_verifier/azure_cpu_goldbach_10pow27_workload_factory.py",
    "tg_verifier/azure_h100_goldbach_10pow27_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/evidence.py",
    "tg_verifier/goldbach.py",
    "tg_verifier/goldbach_build_admission.py",
    "tg_verifier/goldbach_campaign.py",
    "tg_verifier/goldbach_native_ladder.py",
    "tg_verifier/goldbach_gpu_campaign.py",
    "tg_verifier/goldbach_10pow27_campaign.py",
    "tg_verifier/binary_goldbach_campaign.py",
    "tg_verifier/numeric_corpus.py",
    "tg_verifier/sqrt218_fixed_v2_receipt.py",
    "attestation/measured_run_archive.py",
    "reference/tg_goldbach_ladder_native.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "patches/goldbach-gpu/b58b2dea-hardening.patch",
    "specifications/GOLDBACH_GPU_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.goldbach10pow27-cpu.v1\n"
    "initial=SHA256(phase-group-challenge-job-input-handoff)\n"
    "step-0=SHA256(previous-retained-archive-retained-tree)\n"
    "step-1=SHA256(previous-result)\n"
    "verification=closed-predecessor-signature-export-and-campaign-replay"
)


@dataclass(frozen=True)
class Goldbach10Pow27CPUWorkloadFactory:
    factory_id: str
    phase_id: str
    group_id: str
    shard_index: int
    shard_count: int
    terminal: bool
    registered_invocation: str | None
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


def _operational_identity(phase: str, shard_index: int) -> tuple[str, str]:
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\nphase={phase}\ngroup-index={shard_index}\n"
        "semantics=verify-signed-predecessors-run-reviewed-phase-retain-replayable-export\n"
        "output=canonical-operational-result-pinning-deterministic-export"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.gb10.cpu.{suffix}", definition


def _base_argv(
    *, mode: str, phase: str, shard_index: int, algorithm_id: str, handoff: str,
) -> list[str]:
    return [
        "artifacts/python3", "-I",
        "tools/tg_goldbach_10pow27_azure_measured_workload.py", mode,
        "--phase", phase, "--group-index", str(shard_index),
        "--algorithm-id", algorithm_id, "--challenge", "@challenge@",
        "--job-binding", "@job_binding@", "--input", "@input@",
        "--handoff", handoff, "--output", "@output@", "--trace", "@trace@",
        "--work", "work/goldbach10pow27",
        "--build-admission", "source/goldbach-build-admission.json",
        "--goldbach-source", "source/goldbach-gpu-hardened",
        "--goldbach-executable", "artifacts/goldbach-gpu",
        "--ladder-runner", "artifacts/tg_goldbach_ladder_native",
        "--key-manifest", "profiles/verifier-keys/trusted_compute_keys.json",
    ]


def make_factory(phase: str, shard_index: int) -> Goldbach10Pow27CPUWorkloadFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("lowered Goldbach phase/shard is outside the reviewed DAG")
    terminal = phase == "measured-finalize-lowered-source-claim"
    if terminal:
        algorithm_id = REGISTERED_ALGORITHM_ID
        definition = REGISTERED_ALGORITHM_DEFINITION
        input_bytes = REGISTERED_INPUT
        parameters = REGISTERED_PARAMETERS
        domain = REGISTERED_DOMAIN
    else:
        algorithm_id, definition = _operational_identity(phase, shard_index)
        input_bytes = canonical_json_bytes(
            {
                "campaign_id": CAMPAIGN_ID,
                "group_index": shard_index,
                "phase": phase,
                "retained_handoff": "canonical signed-predecessor archive",
            }
        )
        parameters = {
            "binary_shards": 65_536,
            "h100_group_count": 8_192,
            "ladder_group_count": 320,
            "ladder_range_count": 7_106,
        }
        domain = {
            "campaign": CAMPAIGN_ID,
            "group_index": shard_index,
            "phase": phase,
            "source_upper": 10**27,
        }
    handoff = "input/goldbach10pow27-phase-handoff.tar" if terminal else "@input@"
    command = _base_argv(
        mode="run", phase=phase, shard_index=shard_index,
        algorithm_id=algorithm_id, handoff=handoff,
    )
    verifier = _base_argv(
        mode="verify-trace", phase=phase, shard_index=shard_index,
        algorithm_id=algorithm_id, handoff=handoff,
    )
    return Goldbach10Pow27CPUWorkloadFactory(
        factory_id=f"goldbach10pow27_{phase}_{shard_index:04d}_image_cpu_v1",
        phase_id=phase,
        group_id=f"{CAMPAIGN_ID}::{phase}",
        shard_index=shard_index,
        shard_count=PHASE_COUNTS[phase],
        terminal=terminal,
        registered_invocation=REGISTERED_INVOCATION if terminal else None,
        portfolio_argv=PHASE_COMMANDS[phase],
        algorithm_id=algorithm_id,
        algorithm_definition=definition,
        input_bytes=input_bytes,
        parameters=parameters,
        domain=domain,
        command_argv=tuple(command),
        trace_verifier_argv=tuple(verifier),
        timeout_seconds=(
            36 * 3600
            if phase == "native-lowered-prime-ladder-range-groups"
            else 12 * 3600
        ),
        output_format="opaque_bytes_v1",
        output_maximum_bytes=16 if terminal else 2048,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> Goldbach10Pow27CPUWorkloadFactory | None:
    if group.get("campaign_id") != CAMPAIGN_ID:
        return None
    phase = group.get("phase_id")
    if not isinstance(phase, str) or phase not in PHASE_COUNTS:
        return None
    try:
        factory = make_factory(phase, shard_index)
    except ValueError:
        return None
    if (
        group.get("group_id") != factory.group_id
        or group.get("backend_class") != "cpu_exact_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != OWNER_ATOM_ID
        or group.get("operator_adapter") != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != factory.shard_count
        or group.get("terminal") is not factory.terminal
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES[phase]
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    semantic = group.get("semantic_binding")
    if factory.terminal:
        if semantic is not None and (
            not isinstance(semantic, Mapping)
            or semantic.get("registered_invocation") != REGISTERED_INVOCATION
        ):
            return None
    elif semantic is not None:
        return None
    return factory


def source_reviewed_materializer_available(group: Mapping[str, Any]) -> bool:
    count = group.get("shard_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return False
    return all(factory_for_portfolio_group(group, index) is not None for index in range(count))


def expected_registered_hashes() -> dict[str, str]:
    canonical = lambda value: json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "algorithm_hash": hashlib.sha256(
            REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
        ).hexdigest(),
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": hashlib.sha256(canonical(REGISTERED_DOMAIN)).hexdigest(),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": hashlib.sha256(REGISTERED_OUTPUT).hexdigest(),
        "parameters_hash": hashlib.sha256(canonical(REGISTERED_PARAMETERS)).hexdigest(),
    }


__all__ = [
    "CAMPAIGN_ID", "PHASE_COMMANDS", "PHASE_COUNTS", "PHASE_DEPENDENCIES",
    "REGISTERED_INVOCATION", "SOURCE_PATHS", "TRACE_DEFINITION",
    "expected_registered_hashes", "factory_for_portfolio_group", "make_factory",
    "source_reviewed_materializer_available",
]
