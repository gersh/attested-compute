# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed source-reviewed CPU workload factories for Azure portfolio shards.

The editable portfolio argv is never treated as permission to execute a
program.  A group is materializable only when its complete shape equals one
entry below.  The factory then chooses every source, compiler flag, runtime
artifact name, measured argv, trace verifier, profile, and output contract.
There is deliberately no caller-supplied executable field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


CDEM_FACTORY_ID = "cdem_table_abel_static_cpu_v2"
CDEM_REGISTERED_INVOCATION = "cdemTableAbelProductionV2"
CDEM_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v2\n"
    "name=ternary-goldbach-cdem-table-abel\n"
    "producer=reference/tg_cdem_abel_measured_workload.cpp\n"
    "semantics=checked-gap-free-local-floorjump-recurrence-certificate-with-local-fold-evidence\n"
    "certificate=SparkInterval.Generated.CDEMAbelProduction.certificate\n"
    "certificate-transcript-sha256=2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123\n"
    "certificate-lean-source-sha256=c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9\n"
    "artifact=TG-CDEM-ABEL-ARTIFACT-V1-complete-recurrence-stream\n"
    "artifact-binding=trace-recomputes-artifact-after-complete-independent-replay\n"
    "output=false-or-canonical-decimal-nat-pair-u-v\n"
    "pairing=mathlib-nat-pair\n"
    "weight-scale=1000000000000000000\n"
    "signed-rounding=ceil-positive-floor-negative\n"
    "sqrt-rounding=least-q-with-q-squared-times-n-at-least-scale-squared"
)
CDEM_INPUT = '{"K":199330,"N":5000000000,"weight_scale":1000000000000000000}'
CDEM_PARAMETERS: dict[str, Any] = {
    "a": 5_000_000_001,
    "g_zero_override": True,
    "mobius": "linear-sieve-exact",
    "output_encoding": "nat_pair_decimal",
    "sqrt_rounding": "exact_square_test",
}
CDEM_DOMAIN: dict[str, Any] = {
    "claim": "two-pre-endpoint-abel-increment-upper-bounds",
    "index_lower": 1,
    "index_upper": 5_000_000_000,
    "prefix_upper": 199_330,
}
CDEM_TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.cdem-abel.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || checked-producer-transcript-sha256)\n"
    "steps-1-through-1000=SHA256(step-domain || previous || chunk-index || "
    "checked-canonical-chunk-row || independently-replayed-output-sha256)\n"
    "step-1001=SHA256(step-domain || previous || "
    "closed-artifact-sha256 || registered-result-sha256)\n"
    "verification=source-reviewed-static-host-rechecks-transcript-replay-manifest-result-and-chain"
)
CDEM_PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_verify.py",
    "run-cdem-abel-full",
    "${TG_REPOSITORY}/reference/tg_cdem_abel.cpp",
    "--replay-source",
    "${TG_REPOSITORY}/reference/tg_cdem_abel_chunk_replay.cpp",
    "--compiler",
    "${TG_CXX}",
    "--threads",
    "64",
    "--workers",
    "64",
    "--max-seconds",
    "86400",
    "--chunk-max-seconds",
    "3600",
    "--transcript-output",
    "${TG_RUN_ROOT}/cdem-table-abel/transcript.txt",
    "--artifact-output",
    "${TG_RUN_ROOT}/cdem-table-abel/cdem-abel-artifact.bin",
    "--registered-result-output",
    "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt",
)


@dataclass(frozen=True)
class ClosedCPUWorkloadFactory:
    factory_id: str
    campaign_id: str
    group_id: str
    registered_invocation: str
    portfolio_argv: tuple[str, ...]
    source_paths: tuple[str, ...]
    algorithm_id: str
    algorithm_definition: str
    input_bytes: bytes
    parameters: dict[str, Any]
    domain: dict[str, Any]
    command_argv: tuple[str, ...]
    trace_verifier_argv: tuple[str, ...]
    trace_definition: str
    trace_iterations: int
    timeout_seconds: int
    output_format: str
    output_maximum_bytes: int
    retained_artifact_contracts: tuple[dict[str, Any], ...] = ()


CDEM_FACTORY = ClosedCPUWorkloadFactory(
    factory_id=CDEM_FACTORY_ID,
    campaign_id="cdem-table-abel",
    group_id="cdem-table-abel::single-job",
    registered_invocation=CDEM_REGISTERED_INVOCATION,
    portfolio_argv=CDEM_PORTFOLIO_ARGV,
    source_paths=(
        "reference/tg_cdem_abel.cpp",
        "reference/tg_cdem_abel_chunk_replay.cpp",
        "reference/tg_cdem_abel_measured_workload.cpp",
        "gpu/include/sparkinterval/sha256.hpp",
    ),
    algorithm_id="sparkinterval.ternary-goldbach.cdem-table-abel.v2",
    algorithm_definition=CDEM_ALGORITHM_DEFINITION,
    input_bytes=CDEM_INPUT.encode("ascii"),
    parameters=CDEM_PARAMETERS,
    domain=CDEM_DOMAIN,
    command_argv=(
        "artifacts/tg_cdem_abel_measured_workload",
        "--run",
        "--producer",
        "artifacts/tg_cdem_abel",
        "--replayer",
        "artifacts/tg_cdem_abel_chunk_replay",
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
        "--artifact",
        "work/cdem-abel-artifact.bin",
        "--transcript",
        "work/cdem-transcript.txt",
        "--replay-manifest",
        "work/cdem-replay-manifest.txt",
        "--workers",
        "64",
    ),
    trace_verifier_argv=(
        "artifacts/tg_cdem_abel_measured_workload",
        "--verify-trace",
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
        "--artifact",
        "work/cdem-abel-artifact.bin",
        "--transcript",
        "work/cdem-transcript.txt",
        "--replay-manifest",
        "work/cdem-replay-manifest.txt",
    ),
    trace_definition=CDEM_TRACE_DEFINITION,
    trace_iterations=1002,
    timeout_seconds=36 * 60 * 60,
    output_format="canonical_decimal_natural_no_newline_v1",
    output_maximum_bytes=64,
    retained_artifact_contracts=(
        {
            "maximum_bytes": 262_144,
            "path": "work/cdem-abel-artifact.bin",
            "trace_sha256_field": "artifact_sha256",
        },
    ),
)

FACTORIES_BY_CAMPAIGN = {CDEM_FACTORY.campaign_id: CDEM_FACTORY}

# These are explicit extension points, not available factories.  Their names
# prevent an inventory entry from being mistaken for an executable closure.
PENDING_FACTORY_GAPS = {
    "hurst-four-residuals-v1": (
        "the V2 registered invocation exists, but the two-pass shard/reduction "
        "package and terminal result importer are not source-closed"
    ),
    "ch25-psi-two-pass-v1": (
        "the registered invocation and terminal true output are staged, but the "
        "two-pass shard/reduction measured package and retained-evidence review "
        "are not source-closed"
    ),
}


def factory_for_portfolio_group(
    group: Mapping[str, Any],
) -> ClosedCPUWorkloadFactory | None:
    """Return a factory only for a byte-for-byte reviewed group shape."""

    campaign_id = group.get("campaign_id")
    factory = FACTORIES_BY_CAMPAIGN.get(campaign_id)
    if factory is None:
        return None
    if (
        group.get("group_id") != factory.group_id
        or group.get("phase_id") != "single-job"
        or group.get("backend_class") != "cpu_exact_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("shard_count") != 1
        or group.get("terminal") is not True
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    semantic = group.get("semantic_binding")
    if semantic is not None and semantic.get("registered_invocation") != (
        factory.registered_invocation
    ):
        return None
    return factory


def source_reviewed_materializer_available(group: Mapping[str, Any]) -> bool:
    return factory_for_portfolio_group(group) is not None
