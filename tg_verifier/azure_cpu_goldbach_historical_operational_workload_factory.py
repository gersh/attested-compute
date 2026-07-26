# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed measured CPU factories for historical Goldbach predecessor phases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "helfgott-platt-goldbach-gpu-v1"
OWNER_ATOM_ID = "helfgott-platt-theorem-4-1"
H100_PHASE = "h100-8192-groups-of-eight-checkpoint-leaves"
WORKSPACE = "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1"
PLAN = f"{WORKSPACE}/plan.json"
RECEIPTS = f"{WORKSPACE}/receipts"
AGGREGATE = f"{WORKSPACE}/aggregate.json"
LADDER = f"{WORKSPACE}/ternary-prime-ladder"
LADDER_AGGREGATE = f"{LADDER}/ladder-aggregate.json"
BINARY_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_gpu_campaign.py"
LADDER_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_campaign.py"
NATIVE_LADDER_TOOL = "${TG_REPOSITORY}/tools/tg_goldbach_ladder_native.py"
OPERATIONAL_RESULT_KIND = (
    "sparkinterval.azure.goldbach-historical-operational-result.v1"
)

PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "create-production-plan": (
        "${TG_PYTHON}",
        BINARY_TOOL,
        "create-production-plan",
        "--source-root",
        "${TG_GOLDBACH_SOURCE_ROOT}",
        "--executable",
        "${TG_GOLDBACH_EXECUTABLE}",
        "--executable-sha256",
        "${TG_GOLDBACH_EXECUTABLE_SHA256}",
        "--out",
        PLAN,
    ),
    "initialize-prime-ladder": (
        "${TG_PYTHON}",
        LADDER_TOOL,
        "init",
        LADDER,
    ),
    "native-prime-ladder-range-groups": (
        "${TG_PYTHON}",
        NATIVE_LADDER_TOOL,
        "produce-group",
        LADDER,
        "--runner",
        "${TG_TG_BUILD}/sparkinterval-tg-goldbach-ladder-native",
        "--group-index",
        "${TG_ARRAY_INDEX}",
        "--group-count",
        "320",
        "--local-workers",
        "40",
        "--summary",
        f"{LADDER}/groups/group-${{TG_ARRAY_INDEX}}.json",
    ),
    "aggregate": (
        "${TG_PYTHON}",
        BINARY_TOOL,
        "aggregate",
        PLAN,
        "--receipts-dir",
        RECEIPTS,
        "--out",
        AGGREGATE,
    ),
    "binary-semantic-replay": (
        "${TG_PYTHON}",
        BINARY_TOOL,
        "verify",
        PLAN,
        AGGREGATE,
        "--receipts-dir",
        RECEIPTS,
    ),
    "reduce-prime-ladder-ranges": (
        "${TG_PYTHON}",
        LADDER_TOOL,
        "reduce-ranges",
        LADDER,
        "--out",
        LADDER_AGGREGATE,
    ),
}
PHASE_COUNTS = {
    "create-production-plan": 1,
    "initialize-prime-ladder": 1,
    "native-prime-ladder-range-groups": 320,
    "aggregate": 1,
    "binary-semantic-replay": 1,
    "reduce-prime-ladder-ranges": 1,
}
PHASE_DEPENDENCIES = {
    "create-production-plan": (),
    "initialize-prime-ladder": (),
    "native-prime-ladder-range-groups": (
        f"{CAMPAIGN_ID}::initialize-prime-ladder",
    ),
    "aggregate": (f"{CAMPAIGN_ID}::{H100_PHASE}",),
    "binary-semantic-replay": (f"{CAMPAIGN_ID}::aggregate",),
    "reduce-prime-ladder-ranges": (
        f"{CAMPAIGN_ID}::native-prime-ladder-range-groups",
    ),
}

SOURCE_PATHS = (
    "tools/tg_goldbach_historical_operational_azure_measured_workload.py",
    "tools/tg_goldbach_gpu_campaign.py",
    "tools/tg_goldbach_campaign.py",
    "tools/tg_goldbach_ladder_native.py",
    "tools/generate_trusted_compute_lean.py",
    "tools/trusted_compute_receipt.py",
    "tools/create_run_bundle.py",
    "tools/verify_run_bundle.py",
    "tools/local_operator_signature.py",
    "tg_verifier/azure_cpu_goldbach_historical_operational_workload_factory.py",
    "tg_verifier/azure_h100_goldbach_historical_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/goldbach.py",
    "tg_verifier/goldbach_build_admission.py",
    "tg_verifier/goldbach_campaign.py",
    "tg_verifier/goldbach_gpu_campaign.py",
    "tg_verifier/goldbach_historical_terminal.py",
    "tg_verifier/goldbach_native_ladder.py",
    "tg_verifier/numeric_corpus.py",
    "tg_verifier/sqrt218_fixed_v2_receipt.py",
    "attestation/measured_run_archive.py",
    "reference/tg_goldbach_ladder_native.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "patches/goldbach-gpu/b58b2dea-hardening.patch",
    "specifications/GOLDBACH_GPU_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.goldbach-historical-cpu.v1\n"
    "initial=SHA256(phase-group-challenge-job-input-handoff)\n"
    "step-0=SHA256(previous-retained-archive-retained-tree)\n"
    "step-1=SHA256(previous-result)\n"
    "verification=closed-predecessor-signature-export-and-source-profile-replay"
)


@dataclass(frozen=True)
class HistoricalGoldbachOperationalFactory:
    factory_id: str
    phase_id: str
    group_id: str
    shard_index: int
    shard_count: int
    terminal: bool
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


def _identity(phase: str, shard_index: int) -> tuple[str, str]:
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\n"
        f"phase={phase}\n"
        f"group-index={shard_index}\n"
        "profile=historical-helfgott-platt-source-height\n"
        "semantics=verify-signed-predecessors-run-reviewed-phase-retain-replayable-export\n"
        "output=canonical-operational-result-pinning-deterministic-export"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.goldbach-historical.cpu.{suffix}", definition


def _argv(
    mode: str, phase: str, shard_index: int, algorithm_id: str,
) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_goldbach_historical_operational_azure_measured_workload.py",
        mode,
        "--phase",
        phase,
        "--group-index",
        str(shard_index),
        "--algorithm-id",
        algorithm_id,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--handoff",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--work",
        "work/historical-goldbach-operational",
        "--build-admission",
        "source/goldbach-build-admission.json",
        "--goldbach-source",
        "source/goldbach-gpu-hardened",
        "--goldbach-executable",
        "artifacts/goldbach-gpu",
        "--ladder-runner",
        "artifacts/tg_goldbach_ladder_native",
        "--key-manifest",
        "profiles/verifier-keys/trusted_compute_keys.json",
    )


def make_factory(
    phase: str, shard_index: int,
) -> HistoricalGoldbachOperationalFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError(
            "historical Goldbach phase/shard is outside the reviewed DAG"
        )
    algorithm_id, definition = _identity(phase, shard_index)
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
        "ladder_range_count": 492_700,
    }
    domain = {
        "campaign": CAMPAIGN_ID,
        "group_index": shard_index,
        "phase": phase,
        "source_upper": 8_875_694_145_621_773_516_800_000_000_000,
    }
    return HistoricalGoldbachOperationalFactory(
        factory_id=(
            f"historical_goldbach_{phase}_{shard_index:04d}_image_cpu_v1"
        ),
        phase_id=phase,
        group_id=f"{CAMPAIGN_ID}::{phase}",
        shard_index=shard_index,
        shard_count=PHASE_COUNTS[phase],
        terminal=False,
        registered_invocation=None,
        portfolio_argv=PHASE_COMMANDS[phase],
        algorithm_id=algorithm_id,
        algorithm_definition=definition,
        input_bytes=input_bytes,
        parameters=parameters,
        domain=domain,
        command_argv=_argv("run", phase, shard_index, algorithm_id),
        trace_verifier_argv=_argv(
            "verify-trace", phase, shard_index, algorithm_id
        ),
        timeout_seconds=(
            36 * 3600
            if phase == "native-prime-ladder-range-groups"
            else 12 * 3600
        ),
        output_format="opaque_bytes_v1",
        # A native ladder child signs both ordered hash vectors so the final
        # terminal can bind its merged range files without retaining 320
        # duplicate per-group archives in the terminal handoff.
        output_maximum_bytes=(
            512 * 1024
            if phase == "native-prime-ladder-range-groups"
            else 2048
        ),
    )


def expected_claim_identity(phase: str, shard_index: int) -> dict[str, str]:
    """Identity fields fixed independently of the predecessor handoff bytes."""

    factory = make_factory(phase, shard_index)
    return {
        "algorithm_hash": hashlib.sha256(
            factory.algorithm_definition.encode("utf-8")
        ).hexdigest(),
        "algorithm_id": factory.algorithm_id,
        "domain_hash": hashlib.sha256(
            canonical_json_bytes(factory.domain)
        ).hexdigest(),
        "parameters_hash": hashlib.sha256(
            canonical_json_bytes(factory.parameters)
        ).hexdigest(),
    }


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> HistoricalGoldbachOperationalFactory | None:
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
        or group.get("operator_adapter")
        != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != factory.shard_count
        or group.get("terminal") is not False
        or group.get("semantic_binding") is not None
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES[phase]
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    return factory


def source_reviewed_materializer_available(group: Mapping[str, Any]) -> bool:
    count = group.get("shard_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return False
    return all(
        factory_for_portfolio_group(group, index) is not None
        for index in range(count)
    )


__all__ = [
    "CAMPAIGN_ID",
    "H100_PHASE",
    "HistoricalGoldbachOperationalFactory",
    "OWNER_ATOM_ID",
    "PHASE_COMMANDS",
    "PHASE_COUNTS",
    "PHASE_DEPENDENCIES",
    "SOURCE_PATHS",
    "TRACE_DEFINITION",
    "factory_for_portfolio_group",
    "make_factory",
    "source_reviewed_materializer_available",
]
