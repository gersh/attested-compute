# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU factories for the six-stage CH25 psi Azure portfolio DAG."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "ch25-psi-two-pass-v1"
REGISTERED_INVOCATION = "ch25PsiLemma92ProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-ch25-psi-lemma-9-2\n"
    "producer=reference/tg_psi_residual_shard.cpp\n"
    "semantics=gap-free-two-pass-prime-power-q64-endpoint-guards\n"
    "source-range=[1,10000000000000]\n"
    "state=psi-lower-q64-psi-upper-q64\n"
    "output=false-or-true-with-prime-power-gap-log-and-integer-guard-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"ch25-psi-lemma-9-2-v1",'
    b'"source_lower":1,"source_upper":10000000000000}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "crlibm_commit": "eb3063791aa75bc9705b49283bf14250465220a7",
    "event_count": 346_065_767_406,
    "primesieve_commit": "4f85384851da23c36c01ec01ef85b5d9d246e556",
    "q64_scale_bits": 64,
    "replay": "independent-two-pass",
    "row_domain": "sparkinterval.tg.psi-prime-power-rows.v1",
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "claim": "ch25-lemma-9-2-psi-source",
    "source_lower": 1,
    "source_upper": 10_000_000_000_000,
    "upper_denominator": 25_000_000,
    "upper_numerator": 19_764_819,
}
REGISTERED_OUTPUT = b"true"
REGISTERED_OUTPUT_SHA256 = hashlib.sha256(REGISTERED_OUTPUT).hexdigest()
REGISTERED_ALGORITHM_SHA256 = hashlib.sha256(
    REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
).hexdigest()

WORKSPACE = "${TG_RUN_ROOT}/ch25-psi-1e13"
TOOL = "${TG_REPOSITORY}/tools/tg_psi_residual_campaign.py"
PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "initialize": (
        "${TG_PYTHON}", TOOL, "init",
        "--runner", "${TG_TG_BUILD}/sparkinterval-tg-psi-residual-shard",
        "--runner-source", "${TG_REPOSITORY}/reference/tg_psi_residual_shard.cpp",
        "--upstream-manifest", "${TG_REPOSITORY}/specifications/PSI_UPSTREAMS.json",
        "--output-dir", WORKSPACE,
    ),
    "summary-shards": (
        "${TG_PYTHON}", TOOL, "run", WORKSPACE, "summary",
        "--worker-group-index", "${TG_ARRAY_INDEX}",
        "--worker-group-count", "320", "--workers", "40",
    ),
    "reduce-summaries": (
        "${TG_PYTHON}", TOOL, "reduce", WORKSPACE,
    ),
    "verify-shards": (
        "${TG_PYTHON}", TOOL, "run", WORKSPACE, "verify",
        "--worker-group-index", "${TG_ARRAY_INDEX}",
        "--worker-group-count", "320", "--workers", "40",
    ),
    "finalize": (
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
    "finalize": 1,
    "semantic-replay": 1,
}
PHASE_DEPENDENCIES = {
    "initialize": (),
    "summary-shards": (f"{CAMPAIGN_ID}::initialize",),
    "reduce-summaries": (f"{CAMPAIGN_ID}::summary-shards",),
    "verify-shards": (f"{CAMPAIGN_ID}::reduce-summaries",),
    "finalize": (f"{CAMPAIGN_ID}::verify-shards",),
    "semantic-replay": (f"{CAMPAIGN_ID}::finalize",),
}

SOURCE_PATHS = (
    "tools/tg_psi_azure_measured_workload.py",
    "tools/tg_psi_residual_campaign.py",
    "tools/fetch_psi_upstreams.py",
    "tg_verifier/affine_guard_certificate.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/evidence.py",
    "tg_verifier/psi_residual_campaign.py",
    "attestation/measured_run_archive.py",
    "reference/tg_psi_residual_shard.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "specifications/PSI_UPSTREAMS.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.ch25-psi.v1\n"
    "initial=SHA256(initial-domain || phase || group-index || challenge-nonce || "
    "job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || retained-archive-sha256 || "
    "retained-tree-sha256)\n"
    "step-1=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-python-replays-canonical-retained-export-and-final-campaign"
)


@dataclass(frozen=True)
class PsiCPUWorkloadFactory:
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
        "campaign=ch25-psi-two-pass-v1\n"
        f"phase={phase}\n"
        f"group-index={shard_index}\n"
        "semantics=retain-and-replay-source-reviewed-psi-phase-artifacts\n"
        "output=deterministic-link-free-retained-export-tar"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return f"sparkinterval.tg.psi.azure-phase.{phase}.{suffix}", definition


def _base_argv(
    *, mode: str, phase: str, shard_index: int, algorithm_id: str,
    handoff: str,
) -> list[str]:
    return [
        "artifacts/python3",
        "-I",
        "tools/tg_psi_azure_measured_workload.py",
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
        "work/psi",
    ]


def make_factory(phase: str, shard_index: int) -> PsiCPUWorkloadFactory:
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("psi phase/shard is outside the reviewed DAG")
    terminal = phase == "semantic-replay"
    if terminal:
        algorithm_id = REGISTERED_ALGORITHM_ID
        definition = REGISTERED_ALGORITHM_DEFINITION
        input_bytes = REGISTERED_INPUT
        parameters = REGISTERED_PARAMETERS
        domain = REGISTERED_DOMAIN
    else:
        algorithm_id, definition = _operational_identity(phase, shard_index)
        input_value = {
            "campaign_id": CAMPAIGN_ID,
            "group_index": shard_index,
            "phase": phase,
            "retained_handoff": "input artifact is a canonical deterministic archive",
        }
        input_bytes = canonical_json_bytes(input_value)
        parameters = {
            "leaf_count": (
                len(range(shard_index, 100_000, 320))
                if phase in ("summary-shards", "verify-shards")
                else 0
            ),
            "source_leaf_count": 100_000,
            "worker_group_count": 320,
        }
        domain = {
            "campaign": CAMPAIGN_ID,
            "group_index": shard_index,
            "phase": phase,
            "source_lower": 1,
            "source_upper": 10_000_000_000_000,
        }
    handoff = "input/psi-phase-handoff.tar" if terminal else "@input@"
    command = _base_argv(
        mode="run",
        phase=phase,
        shard_index=shard_index,
        algorithm_id=algorithm_id,
        handoff=handoff,
    )
    command.extend(
        [
            "--runner",
            "artifacts/tg_psi_residual_shard",
            "--runner-source",
            "source/reference/tg_psi_residual_shard.cpp",
            "--upstream-manifest",
            "source/specifications/PSI_UPSTREAMS.json",
        ]
    )
    verifier = _base_argv(
        mode="verify-trace",
        phase=phase,
        shard_index=shard_index,
        algorithm_id=algorithm_id,
        handoff=handoff,
    )
    return PsiCPUWorkloadFactory(
        factory_id=f"ch25_psi_{phase}_{shard_index:03d}_image_cpu_v1",
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
        timeout_seconds=(12 * 3600 if phase in ("summary-shards", "verify-shards") else 6 * 3600),
        output_format="opaque_bytes_v1",
        output_maximum_bytes=(16 if terminal else 1024),
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> PsiCPUWorkloadFactory | None:
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
        or group.get("owner_atom_id") != "ch25-psi-1e13"
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
        "algorithm_hash": REGISTERED_ALGORITHM_SHA256,
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": hashlib.sha256(canonical(REGISTERED_DOMAIN)).hexdigest(),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": REGISTERED_OUTPUT_SHA256,
        "parameters_hash": hashlib.sha256(canonical(REGISTERED_PARAMETERS)).hexdigest(),
    }
