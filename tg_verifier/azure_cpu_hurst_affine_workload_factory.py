# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed operational Azure CPU factories for the Hurst affine campaign.

This four-stage DAG is intentionally non-semantic.  Its terminal phase
replays the one-pass conditional certificate but cannot emit the registered
Boolean result or instantiate a Lean execution theorem.  It is a deployable
measurement path for the optimization while physical row realization and
production registration remain pending.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "hurst-four-residuals-affine-onepass-v1"
OWNER_ATOM_ID = "mertens-hurst"
WORKSPACE = "${TG_RUN_ROOT}/mertens-hurst-affine-onepass"
TOOL = "${TG_REPOSITORY}/tools/tg_hurst_affine_campaign.py"

PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "initialize-affine": (
        "${TG_PYTHON}",
        TOOL,
        "init",
        "--runner",
        "${TG_TG_BUILD}/sparkinterval-tg-hurst-residual-shard",
        "--runner-source",
        "${TG_REPOSITORY}/reference/tg_hurst_residual_shard.cpp",
        "--upstream-manifest",
        "${TG_REPOSITORY}/specifications/HURST_MERTENS_UPSTREAM.json",
        "--output-dir",
        WORKSPACE,
    ),
    "affine-shards": (
        "${TG_PYTHON}",
        TOOL,
        "run",
        WORKSPACE,
        "--worker-group-index",
        "${TG_ARRAY_INDEX}",
        "--worker-group-count",
        "320",
        "--workers",
        "2",
        "--runner-threads",
        "20",
    ),
    "finalize-affine-certificate": (
        "${TG_PYTHON}",
        TOOL,
        "finalize",
        WORKSPACE,
    ),
    "replay-affine-certificate": (
        "${TG_PYTHON}",
        TOOL,
        "verify",
        WORKSPACE,
    ),
}
PHASE_COUNTS = {
    "initialize-affine": 1,
    "affine-shards": 320,
    "finalize-affine-certificate": 1,
    "replay-affine-certificate": 1,
}
PHASE_DEPENDENCIES = {
    "initialize-affine": (),
    "affine-shards": (f"{CAMPAIGN_ID}::initialize-affine",),
    "finalize-affine-certificate": (
        f"{CAMPAIGN_ID}::affine-shards",
    ),
    "replay-affine-certificate": (
        f"{CAMPAIGN_ID}::finalize-affine-certificate",
    ),
}

SOURCE_PATHS = (
    "tools/tg_hurst_affine_azure_measured_workload.py",
    "tools/tg_hurst_affine_campaign.py",
    "tools/tg_hurst_azure_measured_workload.py",
    "tools/tg_hurst_residual_campaign.py",
    "tools/fetch_hurst_mertens.py",
    "tg_verifier/affine_guard_certificate.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/evidence.py",
    "tg_verifier/hurst_affine_campaign.py",
    "tg_verifier/hurst_residual_campaign.py",
    "attestation/measured_run_archive.py",
    "reference/tg_hurst_residual_shard.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "specifications/HURST_MERTENS_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.hurst-affine-onepass.v1\n"
    "initial=SHA256(initial-domain || phase || group-index || challenge-nonce || "
    "job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || runner-sha256 || source-sha256 || "
    "upstream-manifest-sha256 || retained-archive-sha256 || retained-tree-sha256)\n"
    "step-1=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-independent-python-replay-of-operational-export-and-"
    "conditional-affine-certificate;never-registered-semantic-closure"
)


@dataclass(frozen=True)
class HurstAffineCPUWorkloadFactory:
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
    trace_iterations: int
    trace_definition: str
    output_format: str
    output_maximum_bytes: int


def _identity(phase: str, shard_index: int) -> tuple[str, str]:
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\n"
        f"phase={phase}\n"
        f"group-index={shard_index}\n"
        "semantics=one-pass-exact-affine-guards-root-derived-exclusive-scan-"
        "and-fail-closed-four-atom-membership\n"
        "coverage=[1,10000000000000001)-in-10000-fixed-leaves\n"
        "trust=conditional-certificate-not-row-realization-not-attestation-"
        "not-lean-atom\n"
        "output=canonical-operational-result-pinning-deterministic-export"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.hurst.affine-onepass.{phase}.{suffix}", definition


def _argv(
    mode: str,
    phase: str,
    shard_index: int,
    algorithm_id: str,
) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_hurst_affine_azure_measured_workload.py",
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
        "work/hurst-affine-onepass",
        "--runner",
        "artifacts/tg_hurst_residual_shard",
        "--runner-source",
        "source/reference/tg_hurst_residual_shard.cpp",
        "--upstream-manifest",
        "source/specifications/HURST_MERTENS_UPSTREAM.json",
    )


def make_factory(
    phase: str, shard_index: int
) -> HurstAffineCPUWorkloadFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("Hurst affine phase/shard is outside the reviewed DAG")
    algorithm_id, definition = _identity(phase, shard_index)
    input_bytes = canonical_json_bytes(
        {
            "campaign_id": CAMPAIGN_ID,
            "group_index": shard_index,
            "phase": phase,
            "retained_handoff": (
                "canonical archive whose signed result fixes every predecessor"
            ),
        }
    )
    parameters = {
        "leaf_count": (
            len(range(shard_index, 10_000, 320))
            if phase == "affine-shards"
            else 0
        ),
        "source_leaf_count": 10_000,
        "worker_group_count": 320,
        "arithmetic_passes_per_leaf": 1,
        "row_realization_status": "pending",
    }
    domain = {
        "atoms": [
            "cdem-squarefree",
            "mertens-hurst",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        ],
        "campaign": CAMPAIGN_ID,
        "group_index": shard_index,
        "phase": phase,
        "source_lower": 1,
        "source_upper_exclusive": 10_000_000_000_000_001,
    }
    return HurstAffineCPUWorkloadFactory(
        factory_id=f"hurst_affine_{phase}_{shard_index:03d}_source_cpu_v1",
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
            48 * 3600 if phase == "affine-shards" else 12 * 3600
        ),
        trace_iterations=2,
        trace_definition=TRACE_DEFINITION,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=2048,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int
) -> HurstAffineCPUWorkloadFactory | None:
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


def source_reviewed_materializer_available(
    group: Mapping[str, Any],
) -> bool:
    count = group.get("shard_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return False
    return all(
        factory_for_portfolio_group(group, index) is not None
        for index in range(count)
    )


def expected_predecessors(
    factory: HurstAffineCPUWorkloadFactory,
) -> tuple[tuple[str, int], ...]:
    group = lambda phase: f"{CAMPAIGN_ID}::{phase}"
    if factory.phase_id == "initialize-affine":
        return ()
    if factory.phase_id == "affine-shards":
        return ((group("initialize-affine"), 0),)
    if factory.phase_id == "finalize-affine-certificate":
        return tuple((group("affine-shards"), index) for index in range(320))
    return ((group("finalize-affine-certificate"), 0),)


__all__ = [
    "CAMPAIGN_ID",
    "HurstAffineCPUWorkloadFactory",
    "OWNER_ATOM_ID",
    "PHASE_COMMANDS",
    "PHASE_COUNTS",
    "PHASE_DEPENDENCIES",
    "SOURCE_PATHS",
    "TRACE_DEFINITION",
    "expected_predecessors",
    "factory_for_portfolio_group",
    "make_factory",
    "source_reviewed_materializer_available",
]
