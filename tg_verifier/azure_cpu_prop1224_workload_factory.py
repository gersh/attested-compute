# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU factories for the Proposition 12.2.4 Azure phase DAG."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.prop1224_mpfr_campaign import make_mpfr_plan


CAMPAIGN_ID = "helfgott-prop-12-2-4-mpfr-v1"
REGISTERED_INVOCATION = "helfgottProp1224ProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach."
    "helfgott-proposition-12-2-4-mpfr.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-helfgott-proposition-12-2-4\n"
    "producer=reference/tg_prop1224_mpfr_shard.cpp\n"
    "semantics=gap-free-independent-q-directed-mpfr-gmp-row-verification\n"
    "source-rank-range=[0,3389047618)\n"
    "source-q-range=q<3300000000-or-(210-divides-q-and-q<22000000000)\n"
    "source-realization=exact-lean-ramareG-cE-f1-window-and-error-claim\n"
    "output=false-or-true-with-full-source-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"helfgott-prop-12-2-4-mpfr-v1",'
    b'"rank_lower":0,"rank_upper":3389047618}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "leaf_rows": 262_144,
    "mpfr_version": "4.2.1",
    "precision_bits": 192,
    "row_domain": "sparkinterval.tg.prop1224-mpfr-directed-rows.v1",
    "source_realization": "external-mpfr-gmp-exact-lean-row",
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "claim": "helfgott-proposition-12-2-4-finite-computation-source",
    "dense_q_upper_exclusive": 3_300_000_000,
    "extension_divisor": 210,
    "extension_q_upper_exclusive": 22_000_000_000,
    "rank_lower": 0,
    "rank_upper_exclusive": 3_389_047_618,
}
REGISTERED_OUTPUT = b"true"

PLAN = make_mpfr_plan()
PLAN_SHA256 = "c836e021ae5129306fe3257c22d21b8613f8f34ceb88ad3819182acbc25f5293"
LEAF_COUNT = 12_930
WORKER_GROUP_COUNT = 4
WORKERS_PER_GROUP = 96
if PLAN.plan_sha256 != PLAN_SHA256 or len(PLAN.shards) != LEAF_COUNT:
    raise RuntimeError("Proposition 12.2.4 production plan identity changed")

WORKSPACE = "${TG_RUN_ROOT}/helfgott-prop-12-2-4"
TOOL = "${TG_REPOSITORY}/tools/tg_prop1224_mpfr_campaign.py"
PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "mpfr-shards": (
        "${TG_PYTHON}",
        TOOL,
        "run-worker-group",
        "${TG_TG_BUILD}/sparkinterval-tg-prop1224-mpfr-shard",
        WORKSPACE,
        "${TG_ARRAY_INDEX}",
        "--worker-group-count",
        str(WORKER_GROUP_COUNT),
        "--workers",
        str(WORKERS_PER_GROUP),
    ),
    "merge-and-verify": (
        "${TG_PYTHON}",
        TOOL,
        "verify",
        WORKSPACE,
        "--registered-result-output",
        f"{WORKSPACE}/registered-result.txt",
    ),
}
PHASE_COUNTS = {"mpfr-shards": WORKER_GROUP_COUNT, "merge-and-verify": 1}
PHASE_DEPENDENCIES = {
    "mpfr-shards": (),
    "merge-and-verify": (f"{CAMPAIGN_ID}::mpfr-shards",),
}

SOURCE_PATHS = (
    "tools/tg_azure_cpu_prop1224_materializer.py",
    "tools/tg_prop1224_azure_measured_workload.py",
    "tools/tg_prop1224_mpfr_campaign.py",
    "tools/fetch_prop1224_upstreams.py",
    "tg_verifier/affine_guard_certificate.py",
    "tg_verifier/azure_cpu_prop1224_workload_factory.py",
    "tg_verifier/azure_cpu_prop1224_materializer.py",
    "tg_verifier/arithmetic.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/finite_campaigns.py",
    "tg_verifier/prop1224_candidate_artifact.py",
    "tg_verifier/prop1224_factor_plan.py",
    "tg_verifier/prop1224_mpfr_campaign.py",
    "tg_verifier/prop1224_upstreams.py",
    "attestation/measured_run_archive.py",
    "reference/tg_prop1224_mpfr_shard.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "specifications/GMP_6_3_PROP1224_UPSTREAM.json",
    "specifications/MPFR_4_2_1_PROP1224_UPSTREAM.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.prop1224.v1\n"
    "initial=SHA256(initial-domain || phase || shard-index || challenge-nonce || "
    "job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || retained-archive-sha256 || "
    "retained-tree-sha256 || terminal-candidate-artifact-and-manifest-binding)\n"
    "step-1=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-runner-replays-the-exact-leaf-or-full-fixed-plan-merge;"
    "terminal-candidate-is-arithmetic-chain-only-and-not-semantic-closure"
)


@dataclass(frozen=True)
class Prop1224CPUWorkloadFactory:
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
    output_format: str
    output_maximum_bytes: int


def leaf_indices_for_group(group_index: int) -> range:
    if not 0 <= group_index < WORKER_GROUP_COUNT:
        raise ValueError("Proposition 12.2.4 worker group is outside the plan")
    return range(group_index, LEAF_COUNT, WORKER_GROUP_COUNT)


def _operational_identity(shard_index: int) -> tuple[str, str]:
    indices = leaf_indices_for_group(shard_index)
    lower = PLAN.shards[indices.start].lower
    upper = PLAN.shards[indices[-1]].upper
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        "campaign=helfgott-prop-12-2-4-mpfr-v1\n"
        "phase=mpfr-shards\n"
        f"worker-group-index={shard_index}\n"
        f"logical-leaf-stride={indices.start}+{indices.step}*j<{indices.stop}\n"
        f"rank-envelope=[{lower},{upper})\n"
        f"plan-sha256={PLAN_SHA256}\n"
        "semantics=run-and-independently-rerun-every-source-reviewed-directed-mpfr-gmp-leaf-in-group\n"
        "output=deterministic-retained-export-identity"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.prop1224.azure-leaf.{shard_index}.{suffix}", definition


def _base_argv(
    *, mode: str, phase: str, shard_index: int, algorithm_id: str, handoff: str,
) -> list[str]:
    return [
        "artifacts/python3",
        "-I",
        "tools/tg_prop1224_azure_measured_workload.py",
        mode,
        "--phase",
        phase,
        "--shard-index",
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
        "work/prop1224",
        "--runner",
        "artifacts/tg_prop1224_mpfr_shard",
    ]


def make_factory(phase: str, shard_index: int) -> Prop1224CPUWorkloadFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("Proposition 12.2.4 phase/shard is outside the reviewed DAG")
    terminal = phase == "merge-and-verify"
    if terminal:
        algorithm_id = REGISTERED_ALGORITHM_ID
        definition = REGISTERED_ALGORITHM_DEFINITION
        input_bytes = REGISTERED_INPUT
        parameters = dict(REGISTERED_PARAMETERS)
        domain = dict(REGISTERED_DOMAIN)
    else:
        algorithm_id, definition = _operational_identity(shard_index)
        indices = leaf_indices_for_group(shard_index)
        lower = PLAN.shards[indices.start].lower
        upper = PLAN.shards[indices[-1]].upper
        input_bytes = canonical_json_bytes(
            {
                "campaign_id": CAMPAIGN_ID,
                "logical_leaf_lower": indices.start,
                "logical_leaf_step": indices.step,
                "logical_leaf_upper": LEAF_COUNT,
                "phase": phase,
                "plan_sha256": PLAN_SHA256,
                "rank_lower": lower,
                "rank_upper": upper,
                "worker_group_index": shard_index,
            }
        )
        parameters = {
            "leaf_rows": 262_144,
            "mpfr_version": "4.2.1",
            "precision_bits": 192,
            "segment_size": 250_000,
            "workers": WORKERS_PER_GROUP,
        }
        domain = {
            "campaign": CAMPAIGN_ID,
            "logical_leaf_lower": indices.start,
            "logical_leaf_step": indices.step,
            "logical_leaf_upper": LEAF_COUNT,
            "plan_sha256": PLAN_SHA256,
            "rank_lower": lower,
            "rank_upper": upper,
            "worker_group_index": shard_index,
        }
    handoff = (
        "input/prop1224-phase-handoff.tar" if terminal else "@input@"
    )
    return Prop1224CPUWorkloadFactory(
        factory_id=f"prop1224_{phase}_{shard_index:05d}_static_x86_cpu_v1",
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
        command_argv=tuple(
            _base_argv(
                mode="run",
                phase=phase,
                shard_index=shard_index,
                algorithm_id=algorithm_id,
                handoff=handoff,
            )
        ),
        trace_verifier_argv=tuple(
            _base_argv(
                mode="verify-trace",
                phase=phase,
                shard_index=shard_index,
                algorithm_id=algorithm_id,
                handoff=handoff,
            )
        ),
        timeout_seconds=2 * 3600 if not terminal else 3600,
        trace_iterations=2,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=16 if terminal else 1024,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> Prop1224CPUWorkloadFactory | None:
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
        or group.get("owner_atom_id") != "helfgott-prop-12-2-4"
        or group.get("operator_adapter") != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != factory.shard_count
        or group.get("terminal") is not factory.terminal
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES[phase]
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    semantic = group.get("semantic_binding")
    if semantic is not None and (
        not factory.terminal
        or not isinstance(semantic, Mapping)
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
        "parameters_hash": hashlib.sha256(canonical(REGISTERED_PARAMETERS)).hexdigest(),
    }


__all__ = [
    "CAMPAIGN_ID",
    "LEAF_COUNT",
    "PHASE_COUNTS",
    "PLAN",
    "PLAN_SHA256",
    "REGISTERED_INVOCATION",
    "SOURCE_PATHS",
    "TRACE_DEFINITION",
    "WORKERS_PER_GROUP",
    "WORKER_GROUP_COUNT",
    "Prop1224CPUWorkloadFactory",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "leaf_indices_for_group",
    "make_factory",
    "source_reviewed_materializer_available",
]
