# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed Azure H100 factory for the source-scale R2Star campaign.

The portfolio's historical command points the resumable supervisor at a
workspace path.  That is useful on a trusted local machine, but it does not by
itself establish where a pre-existing receipt prefix came from.  This factory
instead invokes a fixed measured wrapper which requires a fresh workspace and
creates the complete receipt chain after the challenge has been measured.

This is the one terminal job for the physical campaign.  The registered
invocation is deliberately absent from every helper/build action and is bound
only here.  The factory does not enable the portfolio semantic binding and it
does not claim a CUDA-to-Lean refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


CAMPAIGN_ID = "ramare-zuniga-lemma-6-2"
OWNER_ATOM_ID = CAMPAIGN_ID
PHASE_ID = "single-job"
GROUP_ID = f"{CAMPAIGN_ID}::{PHASE_ID}"
SHARD_COUNT = 1
PHASE_DEPENDENCIES: tuple[str, ...] = ()
REGISTERED_INVOCATION = "ramareZunigaLemma62ProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ramare-zuniga-lemma-6-2.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-ramare-zuniga-lemma-6-2\n"
    "producer=gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp\n"
    "semantics=gap-free-q32-r2star-prefix-enclosures-and-exact-squared-endpoint-guards\n"
    "source-range=[1,21000000001)\n"
    "coefficient=(vonMangoldt*vonMangoldt)(n)-vonMangoldt(n)*log(n)+2*eulerMascheroniConstant\n"
    "scale=2^32\n"
    "bound=(193/100)*sqrt(x)*log(x)\n"
    "output=false-or-true-with-full-source-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"ramare-zuniga-lemma-6-2-v1",'
    b'"source_lower":1,"source_upper_exclusive":21000000001}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "chunk_span": 1_000_000,
    "gamma_lower_q32": 2_479_051_107,
    "gamma_upper_q32": 2_479_194_040,
    "harmonic_terms": 100_000,
    "log_series_terms": 20,
    "replay": "independent_cpp_full_row_exact_v1",
    "scale_bits": 32,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "bound_denominator": 100,
    "bound_numerator": 193,
    "claim": "ramare-zuniga-2024-lemma-6-2-source",
    "source_lower": 1,
    "source_upper_exclusive": 21_000_000_001,
    "x_lower": 3,
    "x_upper": 21_000_000_000,
}
REGISTERED_OUTPUT = b"true"

PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_r2star_campaign.py",
    "run",
    "--runner",
    "${TG_H100_BUILD}/sparkinterval-h100-tg-r2star-chunk",
    "--output-dir",
    "${TG_RUN_ROOT}/ramare-zuniga-lemma-6-2",
    "--segment-count",
    "1000000",
    "--device",
    "0",
    "--arithmetic-replayer",
    "${TG_H100_BUILD}/sparkinterval-tg-r2star-arithmetic-replay",
    "--replay-threads",
    "32",
    "--registered-result-output",
    "${TG_RUN_ROOT}/ramare-zuniga-lemma-6-2/registered-result.txt",
)

SOURCE_PATHS = (
    "tools/tg_r2star_azure_measured_workload.py",
    "tools/tg_r2star_campaign.py",
    "tg_verifier/arithmetic.py",
    "tg_verifier/azure_h100_r2star_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/catalog.py",
    "tg_verifier/evidence.py",
    "tg_verifier/finite_campaigns.py",
    "tg_verifier/r2star.py",
    "tg_verifier/r2star_campaign.py",
    "attestation/azure_h100_pre_run_gate.py",
    "attestation/collect_azure_ncc_evidence.py",
    "attestation/measured_run_archive.py",
    "gpu/include/sparkinterval/measured_worker_scope.hpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "gpu/include/sparkinterval/tg_r2star_replay_segments.hpp",
    "gpu/include/tg_r2star_chunk.h",
    "gpu/include/tg_r2star_factor_support.h",
    "gpu/platform/h100/h100_runtime_policy.h",
    "gpu/platform/h100/h100_tg_r2star_chunk_kernel.cu",
    "gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp",
    "gpu/platform/h100/h100_tg_r2star_factor_support_kernel.cu",
    "gpu/src/tg_r2star_chunk_kernel.cu",
    "gpu/src/tg_r2star_chunk_runner.cpp",
    "gpu/src/tg_r2star_factor_support_kernel.cu",
    "reference/tg_r2star_arithmetic_replay.cpp",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.r2star-source-scale.v1\n"
    "initial=SHA256(challenge-job-input-python-runner-arithmetic-replayer-source-closure)\n"
    "step-0=SHA256(previous-retained-archive-retained-tree)\n"
    "step-1=SHA256(previous-registered-result)\n"
    "freshness=work-directory-must-not-exist-before-measured-command\n"
    "verification=independent-complete-gap-free-campaign-export-and-cpu-row-arithmetic-replay"
)

EXPECTED_IDENTITY = {
    "algorithm_hash": "1c95ab10e8f25ed7f87739bc2ea13190bb32e520272f05a3611d13b95e7f9d9c",
    "algorithm_id": REGISTERED_ALGORITHM_ID,
    "domain_hash": "9cafd963de87e0f4f36904a616a9191b7fdf1b4ae29d05fe12a27bc60c6392f3",
    "input_hash": "386168a18f1c8639736118a2beb057efe0a1a53871561a9a7b54dafd50024c5c",
    "output_hash": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "parameters_hash": "515707b2ec16c0ffa90cd4b36cb64353e1da4f93a2c94dd21523fe42939407d5",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def registered_identity() -> dict[str, str]:
    """Return and self-audit the exact Lean/generator wire identity."""

    actual = {
        "algorithm_hash": _sha(REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")),
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": _sha(_canonical(REGISTERED_DOMAIN)),
        "input_hash": _sha(REGISTERED_INPUT),
        "output_hash": _sha(REGISTERED_OUTPUT),
        "parameters_hash": _sha(_canonical(REGISTERED_PARAMETERS)),
    }
    if actual != EXPECTED_IDENTITY:
        raise RuntimeError("R2Star registered invocation identity changed")
    return actual


@dataclass(frozen=True)
class R2StarH100WorkloadFactory:
    factory_id: str
    phase_id: str
    group_id: str
    shard_index: int
    shard_count: int
    terminal: bool
    registered_invocation: str
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


def _measured_argv(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_r2star_azure_measured_workload.py",
        mode,
        "--algorithm-id",
        REGISTERED_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
    )


def make_factory(shard_index: int = 0) -> R2StarH100WorkloadFactory:
    if shard_index != 0:
        raise ValueError("R2Star source campaign has exactly one terminal shard")
    identity = registered_identity()
    return R2StarH100WorkloadFactory(
        factory_id="ramare_zuniga_lemma_6_2_fresh_h100_v1",
        phase_id=PHASE_ID,
        group_id=GROUP_ID,
        shard_index=0,
        shard_count=SHARD_COUNT,
        terminal=True,
        registered_invocation=REGISTERED_INVOCATION,
        portfolio_argv=PORTFOLIO_ARGV,
        algorithm_id=identity["algorithm_id"],
        algorithm_definition=REGISTERED_ALGORITHM_DEFINITION,
        input_bytes=REGISTERED_INPUT,
        parameters=dict(REGISTERED_PARAMETERS),
        domain=dict(REGISTERED_DOMAIN),
        command_argv=_measured_argv("run"),
        trace_verifier_argv=_measured_argv("verify-trace"),
        timeout_seconds=24 * 60 * 60,
        trace_iterations=2,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=len(REGISTERED_OUTPUT),
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> R2StarH100WorkloadFactory | None:
    try:
        factory = make_factory(shard_index)
    except ValueError:
        return None
    if (
        group.get("campaign_id") != CAMPAIGN_ID
        or group.get("phase_id") != PHASE_ID
        or group.get("group_id") != GROUP_ID
        or group.get("backend_class") != "h100_cuda"
        or group.get("receipt_backend") != "azure_ncc40ads_h100_v5"
        or group.get("owner_atom_id") != OWNER_ATOM_ID
        or group.get("operator_adapter") != "azure/h100_production_orchestrator.py"
        or group.get("shard_count") != SHARD_COUNT
        or group.get("terminal") is not True
        or tuple(group.get("depends_on", ())) != PHASE_DEPENDENCIES
        or tuple(group.get("command_template", ())) != PORTFOLIO_ARGV
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


__all__ = [
    "CAMPAIGN_ID",
    "EXPECTED_IDENTITY",
    "GROUP_ID",
    "OWNER_ATOM_ID",
    "PHASE_DEPENDENCIES",
    "PHASE_ID",
    "PORTFOLIO_ARGV",
    "REGISTERED_ALGORITHM_DEFINITION",
    "REGISTERED_ALGORITHM_ID",
    "REGISTERED_DOMAIN",
    "REGISTERED_INPUT",
    "REGISTERED_INVOCATION",
    "REGISTERED_OUTPUT",
    "REGISTERED_PARAMETERS",
    "SHARD_COUNT",
    "SOURCE_PATHS",
    "TRACE_DEFINITION",
    "R2StarH100WorkloadFactory",
    "factory_for_portfolio_group",
    "make_factory",
    "registered_identity",
    "source_reviewed_materializer_available",
]
