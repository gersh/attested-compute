# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU factories for the six-stage shared Hurst Azure DAG.

The first five phases are operational jobs.  Their signed results retain an
exact runner/source/upstream identity and a deterministic archive, but they
cannot generate Lean.  Only ``semantic-replay`` uses the closed registered
invocation and may return the literal registered result ``true``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "hurst-four-residuals-v1"
OWNER_ATOM_ID = "mertens-hurst"
REGISTERED_INVOCATION = "hurstSharedFourResidualProductionV2"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.hurst-shared-four-residual.v2"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v2\n"
    "name=ternary-goldbach-hurst-shared-four-residual\n"
    "producer=reference/tg_hurst_residual_shard.cpp\n"
    "semantics=gap-free-two-pass-mobius-prefix-and-exact-directed-guard-checks\n"
    "evidence=local-primitive-row-deltas-plus-local-state-guard-decisions\n"
    "global-prefix=derived-in-lean-from-root-zero-and-row-delta-recurrence\n"
    "little-q96-tracking=active-through-1000000000000-zero-after\n"
    "source-range=[1,10000000000000001)\n"
    "state=mertens-squarefree-little-lower-q96-little-upper-q96\n"
    "hurst-guard=1000000*abs(M)^2<=571^2*n-for-n>=33\n"
    "squarefree-density=607927101854026628/10^18<=6/pi^2<=607927101854026629/10^18\n"
    "squarefree-b1=151/2000-after-9243;check-value-at-n>=9243-and-right-limit-at-n+1\n"
    "squarefree-b2=57/2000-after-438429;check-value-at-n>=438429-and-right-limit-at-n+1\n"
    "little-2-11=right*abs(q96)^2<=2*2^192-for-1<=n<=10^12\n"
    "little-stronger=4*right*abs(q96)^2<=2^192-for-3<=n<7727068587\n"
    "output=false-or-true-with-local-replay-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"hurst-shared-four-residual-v2","source_lower":1,'
    b'"source_upper_exclusive":10000000000000001}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "little_scale_bits": 96,
    "receipt_leaves": 10_000,
    "replay": "independent-two-pass",
    "row_domain": "sparkinterval.tg.hurst-residual-mobius-rows.v1",
    "squarefree_threshold_endpoints": "inclusive_value_and_right_limit",
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "atoms": [
        "cdem-squarefree",
        "mertens-hurst",
        "platt-little-mertens-2-11",
        "platt-little-mertens-stronger",
    ],
    "source_lower": 1,
    "source_upper_exclusive": 10_000_000_000_000_001,
    "squarefree_thresholds": [9_243, 438_429],
}
REGISTERED_OUTPUT = b"true"
REGISTERED_OUTPUT_SHA256 = hashlib.sha256(REGISTERED_OUTPUT).hexdigest()
REGISTERED_ALGORITHM_SHA256 = hashlib.sha256(
    REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
).hexdigest()

WORKSPACE = "${TG_RUN_ROOT}/mertens-hurst"
TOOL = "${TG_REPOSITORY}/tools/tg_hurst_residual_campaign.py"
PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "initialize": (
        "${TG_PYTHON}", TOOL, "init",
        "--runner", "${TG_TG_BUILD}/sparkinterval-tg-hurst-residual-shard",
        "--runner-source", "${TG_REPOSITORY}/reference/tg_hurst_residual_shard.cpp",
        "--upstream-manifest", "${TG_REPOSITORY}/specifications/HURST_MERTENS_UPSTREAM.json",
        "--output-dir", WORKSPACE,
    ),
    "summary-shards": (
        "${TG_PYTHON}", TOOL, "run", WORKSPACE, "summary",
        "--worker-group-index", "${TG_ARRAY_INDEX}",
        "--worker-group-count", "320",
        "--workers", "2",
        "--runner-threads", "20",
    ),
    "reduce-summaries": (
        "${TG_PYTHON}", TOOL, "reduce", WORKSPACE,
    ),
    "verify-shards": (
        "${TG_PYTHON}", TOOL, "run", WORKSPACE, "verify",
        "--worker-group-index", "${TG_ARRAY_INDEX}",
        "--worker-group-count", "320",
        "--workers", "2",
        "--runner-threads", "20",
    ),
    "finalize-four-residual-certificate": (
        "${TG_PYTHON}", TOOL, "finalize", WORKSPACE,
    ),
    "semantic-replay": (
        "${TG_PYTHON}", TOOL, "verify", WORKSPACE,
        "--registered-result-output", f"{WORKSPACE}/registered-result.txt",
    ),
}
PHASE_COUNTS = {
    "initialize": 1,
    "summary-shards": 320,
    "reduce-summaries": 1,
    "verify-shards": 320,
    "finalize-four-residual-certificate": 1,
    "semantic-replay": 1,
}
PHASE_DEPENDENCIES = {
    "initialize": (),
    "summary-shards": (f"{CAMPAIGN_ID}::initialize",),
    "reduce-summaries": (f"{CAMPAIGN_ID}::summary-shards",),
    "verify-shards": (f"{CAMPAIGN_ID}::reduce-summaries",),
    "finalize-four-residual-certificate": (
        f"{CAMPAIGN_ID}::verify-shards",
    ),
    "semantic-replay": (
        f"{CAMPAIGN_ID}::finalize-four-residual-certificate",
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
    "tg_verifier/hurst_candidate_artifact.py",
    "tg_verifier/hurst_residual_campaign.py",
    "tg_verifier/azure_cpu_hurst_affine_workload_factory.py",
    "attestation/measured_run_archive.py",
    "reference/tg_hurst_residual_shard.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "specifications/HURST_MERTENS_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.hurst-four-residuals.v1\n"
    "initial=SHA256(initial-domain || phase || group-index || challenge-nonce || "
    "job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || runner-sha256 || source-sha256 || "
    "upstream-manifest-sha256 || retained-archive-sha256 || retained-tree-sha256 || "
    "terminal-candidate-artifact-and-manifest-binding)\n"
    "step-1=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-independent-python-replay-of-export-and-full-campaign;"
    "terminal-candidate-is-arithmetic-chain-only-and-not-semantic-closure"
)


@dataclass(frozen=True)
class HurstCPUWorkloadFactory:
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
    trace_iterations: int
    trace_definition: str
    output_format: str
    output_maximum_bytes: int


def _operational_identity(phase: str, shard_index: int) -> tuple[str, str]:
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        "campaign=hurst-four-residuals-v1\n"
        f"phase={phase}\n"
        f"group-index={shard_index}\n"
        "semantics=retain-source-reviewed-four-state-phase-artifacts-with-exact-binary-pins\n"
        "output=canonical-operational-result-pinning-link-free-deterministic-export"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.hurst.azure-phase.{phase}.{suffix}", definition


def _base_argv(
    *, mode: str, phase: str, shard_index: int, algorithm_id: str, handoff: str,
) -> list[str]:
    return [
        "artifacts/python3",
        "-I",
        "tools/tg_hurst_azure_measured_workload.py",
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
        handoff,
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--work",
        "work/hurst",
        "--runner",
        "artifacts/tg_hurst_residual_shard",
        "--runner-source",
        "source/reference/tg_hurst_residual_shard.cpp",
        "--upstream-manifest",
        "source/specifications/HURST_MERTENS_UPSTREAM.json",
    ]


def make_factory(phase: str, shard_index: int) -> HurstCPUWorkloadFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("Hurst phase/shard is outside the reviewed DAG")
    terminal = phase == "semantic-replay"
    if terminal:
        algorithm_id = REGISTERED_ALGORITHM_ID
        definition = REGISTERED_ALGORITHM_DEFINITION
        input_bytes = REGISTERED_INPUT
        parameters = dict(REGISTERED_PARAMETERS)
        domain = dict(REGISTERED_DOMAIN)
    else:
        algorithm_id, definition = _operational_identity(phase, shard_index)
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
                if phase in ("summary-shards", "verify-shards")
                else 0
            ),
            "source_leaf_count": 10_000,
            "upstream_commit": "fb47790c876c92690fce62990199ce961c5bdd72",
            "worker_group_count": 320,
        }
        domain = {
            "campaign": CAMPAIGN_ID,
            "group_index": shard_index,
            "phase": phase,
            "source_lower": 1,
            "source_upper_exclusive": 10_000_000_000_000_001,
        }
    handoff = "input/hurst-phase-handoff.tar" if terminal else "@input@"
    command = _base_argv(
        mode="run",
        phase=phase,
        shard_index=shard_index,
        algorithm_id=algorithm_id,
        handoff=handoff,
    )
    verifier = _base_argv(
        mode="verify-trace",
        phase=phase,
        shard_index=shard_index,
        algorithm_id=algorithm_id,
        handoff=handoff,
    )
    return HurstCPUWorkloadFactory(
        factory_id=f"hurst_{phase}_{shard_index:03d}_source_cpu_v1",
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
            48 * 3600
            if phase in ("summary-shards", "verify-shards")
            else 12 * 3600
        ),
        trace_iterations=2,
        trace_definition=TRACE_DEFINITION,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=(16 if terminal else 2048),
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> HurstCPUWorkloadFactory | None:
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
    return all(
        factory_for_portfolio_group(group, index) is not None
        for index in range(count)
    )


def expected_registered_hashes() -> dict[str, str]:
    canonical = lambda value: json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "algorithm_hash": REGISTERED_ALGORITHM_SHA256,
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": hashlib.sha256(canonical(REGISTERED_DOMAIN)).hexdigest(),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": REGISTERED_OUTPUT_SHA256,
        "parameters_hash": hashlib.sha256(
            canonical(REGISTERED_PARAMETERS)
        ).hexdigest(),
    }


__all__ = [
    "CAMPAIGN_ID",
    "OWNER_ATOM_ID",
    "PHASE_COMMANDS",
    "PHASE_COUNTS",
    "PHASE_DEPENDENCIES",
    "REGISTERED_ALGORITHM_DEFINITION",
    "REGISTERED_ALGORITHM_ID",
    "REGISTERED_INPUT",
    "REGISTERED_INVOCATION",
    "REGISTERED_OUTPUT",
    "SOURCE_PATHS",
    "HurstCPUWorkloadFactory",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "make_factory",
    "source_reviewed_materializer_available",
]
