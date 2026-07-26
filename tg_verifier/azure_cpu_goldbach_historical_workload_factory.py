# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU terminal factory for the historical Helfgott--Platt campaign.

This is deliberately distinct from the finite-below-``10^27`` campaign.  The
terminal consumes a canonical handoff containing the complete source-height
binary Goldbach and prime-ladder branches, independently replays both
aggregates, and emits the registered result only after their signed child
identities and raw retained artifacts agree.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.goldbach_gpu_campaign import (
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
)
from tg_verifier.goldbach_historical_terminal import (
    H100_GROUP_COUNT,
    LADDER_GROUP_COUNT,
)


CAMPAIGN_ID = "helfgott-platt-goldbach-gpu-v1"
OWNER_ATOM_ID = "helfgott-platt-theorem-4-1"
PHASE_ID = "combine-binary-and-prime-ladder"
GROUP_ID = f"{CAMPAIGN_ID}::{PHASE_ID}"
REGISTERED_INVOCATION = "helfgottPlattGoldbachProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.helfgott-platt-finite-goldbach.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-helfgott-platt-finite-goldbach\n"
    "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_campaign.py\n"
    "semantics=complete-binary-goldbach-plus-checked-prime-ladder-source-evidence\n"
    "binary-campaign=goldbach-gpu-hardened-production-65536-leaf-v2\n"
    "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n"
    f"binary-source-identity={EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256}\n"
    "ladder-campaign=tg_goldbach_ladder_parallel_campaign_v1\n"
    "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n"
    "ladder-native-source=02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6\n"
    "combined-artifact=tg_goldbach_gpu_plus_ladder_result_v1\n"
    "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n"
    "source-realization=external-branch-artifacts-to-checked-source-evidence\n"
    "output=false-or-true-with-checked-source-evidence"
)
REGISTERED_INPUT = (
    '{"binary_artifact_kind":"sparkinterval.goldbach-gpu-aggregate.v1",'
    '"binary_campaign":"goldbach-gpu-hardened-production-65536-leaf-v2",'
    f'"binary_source_identity_sha256":"{EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256}",'
    '"campaign":"helfgott-platt-goldbach-gpu-v1",'
    '"combined_artifact_kind":"tg_goldbach_gpu_plus_ladder_result_v1",'
    '"ladder_artifact_kind":"tg_goldbach_ladder_parallel_aggregate_v1",'
    '"ladder_campaign":"tg_goldbach_ladder_parallel_campaign_v1",'
    '"ladder_native_source_sha256":'
    '"02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6"}'
).encode("ascii")
REGISTERED_PARAMETERS: dict[str, Any] = {
    "binary_even_count": 1_999_999_999_999_999_999,
    "binary_leaves_per_group": 8,
    "binary_shards": 65_536,
    "h100_groups": H100_GROUP_COUNT,
    "ladder_cpu_groups": LADDER_GROUP_COUNT,
    "ladder_maximum_gap": 4_000_000_000_000_000_000,
    "ladder_proth_exponent": 52,
    "ladder_range_count": 492_700,
    "ladder_sieve_bound": 16_000,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "binary_even_lower": 4,
    "binary_even_upper": 4_000_000_000_000_000_000,
    "claim": "helfgott-platt-theorem-4-1-source",
    "source_lower": 7,
    "source_upper": 8_875_694_145_621_773_516_800_000_000_000,
}
REGISTERED_OUTPUT = b"true"

PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_goldbach_historical_finalizer.py",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/ternary-prime-ladder",
    "--ladder-aggregate",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/ternary-prime-ladder/ladder-aggregate.json",
    "--binary-plan",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/plan.json",
    "--binary-receipts-dir",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/receipts",
    "--binary-aggregate",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/aggregate.json",
    "--combined-out",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/combined.json",
    "--registered-result-output",
    "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/registered-result.txt",
)
PHASE_DEPENDENCIES = (
    f"{CAMPAIGN_ID}::binary-semantic-replay",
    f"{CAMPAIGN_ID}::reduce-prime-ladder-ranges",
)

SOURCE_PATHS = (
    "tools/tg_goldbach_historical_azure_measured_workload.py",
    "tools/tg_goldbach_historical_finalizer.py",
    "tools/generate_trusted_compute_lean.py",
    "tools/trusted_compute_receipt.py",
    "tools/create_run_bundle.py",
    "tools/verify_run_bundle.py",
    "tools/local_operator_signature.py",
    "tg_verifier/azure_cpu_goldbach_historical_operational_workload_factory.py",
    "tg_verifier/azure_cpu_goldbach_historical_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/goldbach.py",
    "tg_verifier/goldbach_build_admission.py",
    "tg_verifier/goldbach_campaign.py",
    "tg_verifier/goldbach_gpu_campaign.py",
    "tg_verifier/goldbach_historical_terminal.py",
    "tg_verifier/goldbach_native_ladder.py",
    "attestation/measured_run_archive.py",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.goldbach-historical-terminal.v1\n"
    "initial=SHA256(challenge-job-input-handoff-child-commitment)\n"
    "step-0=SHA256(previous-binary-plan-receipt-merkle-aggregate)\n"
    "step-1=SHA256(previous-ladder-manifest-receipt-merkle-aggregate)\n"
    "step-2=SHA256(previous-combined-artifact-result)\n"
    "verification=independent-complete-child-signature-and-branch-artifact-replay"
)


@dataclass(frozen=True)
class HistoricalGoldbachTerminalFactory:
    factory_id: str = "helfgott_platt_historical_terminal_cpu_v1"
    phase_id: str = PHASE_ID
    group_id: str = GROUP_ID
    shard_index: int = 0
    shard_count: int = 1
    terminal: bool = True
    registered_invocation: str = REGISTERED_INVOCATION
    portfolio_argv: tuple[str, ...] = PORTFOLIO_ARGV
    algorithm_id: str = REGISTERED_ALGORITHM_ID
    algorithm_definition: str = REGISTERED_ALGORITHM_DEFINITION
    input_bytes: bytes = REGISTERED_INPUT
    parameters: dict[str, Any] | None = None
    domain: dict[str, Any] | None = None
    command_argv: tuple[str, ...] = (
        "artifacts/python3",
        "-I",
        "tools/tg_goldbach_historical_azure_measured_workload.py",
        "run",
        "--algorithm-id",
        REGISTERED_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--handoff",
        "input/historical-goldbach-terminal-handoff.tar",
        "--child-commitment",
        "source/historical-goldbach-child-commitment.json",
        "--build-admission",
        "source/goldbach-build-admission.json",
        "--key-manifest",
        "profiles/verifier-keys/trusted_compute_keys.json",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--work",
        "work/historical-goldbach-terminal",
    )
    trace_verifier_argv: tuple[str, ...] = (
        "artifacts/python3",
        "-I",
        "tools/tg_goldbach_historical_azure_measured_workload.py",
        "verify-trace",
        "--algorithm-id",
        REGISTERED_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--handoff",
        "input/historical-goldbach-terminal-handoff.tar",
        "--child-commitment",
        "source/historical-goldbach-child-commitment.json",
        "--build-admission",
        "source/goldbach-build-admission.json",
        "--key-manifest",
        "profiles/verifier-keys/trusted_compute_keys.json",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--work",
        "work/historical-goldbach-terminal",
    )
    timeout_seconds: int = 6 * 24 * 60 * 60
    trace_iterations: int = 3
    output_format: str = "opaque_bytes_v1"
    output_maximum_bytes: int = 16

    def __post_init__(self) -> None:
        if self.parameters is None:
            object.__setattr__(self, "parameters", dict(REGISTERED_PARAMETERS))
        if self.domain is None:
            object.__setattr__(self, "domain", dict(REGISTERED_DOMAIN))


TERMINAL_FACTORY = HistoricalGoldbachTerminalFactory()


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int = 0,
) -> HistoricalGoldbachTerminalFactory | None:
    factory = TERMINAL_FACTORY
    if (
        shard_index != 0
        or group.get("campaign_id") != CAMPAIGN_ID
        or group.get("group_id") != GROUP_ID
        or group.get("phase_id") != PHASE_ID
        or group.get("backend_class") != "cpu_exact_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != OWNER_ATOM_ID
        or group.get("operator_adapter") != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != 1
        or group.get("terminal") is not True
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    semantic = group.get("semantic_binding")
    if semantic is not None and (
        not isinstance(semantic, Mapping)
        or semantic.get("registered_invocation") != REGISTERED_INVOCATION
    ):
        return None
    return factory


def source_reviewed_materializer_available(group: Mapping[str, Any]) -> bool:
    return factory_for_portfolio_group(group, 0) is not None


def expected_registered_hashes() -> dict[str, str]:
    canonical = lambda value: json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "algorithm_hash": hashlib.sha256(
            REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
        ).hexdigest(),
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": hashlib.sha256(canonical(REGISTERED_DOMAIN)).hexdigest(),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": hashlib.sha256(REGISTERED_OUTPUT).hexdigest(),
        "parameters_hash": hashlib.sha256(
            canonical(REGISTERED_PARAMETERS)
        ).hexdigest(),
    }


__all__ = [
    "CAMPAIGN_ID",
    "GROUP_ID",
    "OWNER_ATOM_ID",
    "PHASE_DEPENDENCIES",
    "PHASE_ID",
    "PORTFOLIO_ARGV",
    "REGISTERED_INVOCATION",
    "SOURCE_PATHS",
    "TERMINAL_FACTORY",
    "TRACE_DEFINITION",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "source_reviewed_materializer_available",
]
