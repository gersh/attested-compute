# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU workload factory for the CH25 Lemma A.7 boundary replay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.azure_cpu_platt_head_workload_factory import RUNTIME_WHEEL_PATH


CAMPAIGN_ID = "ch25-a7-boundary"
GROUP_ID = "ch25-a7-boundary::single-job"
REGISTERED_INVOCATION = "ch25A7BoundaryProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
)
RETAINED_ARTIFACT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-ch25-lemma-a7-boundary\n"
    "producer=tg_verifier/a7_flint.py\n"
    "semantics=pinned-full-flint-arb-boundary-replay-with-rational-box-evidence\n"
    "source-rectangle=(-3,5)+i(-4,4)-frontier\n"
    "raw-function=-zeta-prime(s)/zeta(s)-1/(s-1)+1/(s+2)\n"
    "bound=349/250\n"
    f"retained-artifact-sha256={RETAINED_ARTIFACT_SHA256}\n"
    "source-realization=external-flint-arb-boxes-contain-mathlib-riemannZeta-expression\n"
    "output=false-or-true-with-boundary-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":'
    b'"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "flint_release": 30_600,
    "flint_version": "3.6.0",
    "leaf_count": 16_191,
    "python_flint_version": "0.9.0",
    "series_cap": 4,
    "series_length": 2,
    "threads": 1,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "bound_denominator": 250,
    "bound_numerator": 349,
    "claim": "ch25-lemma-a7-arb-boundary-source",
    "imag_lower": -4,
    "imag_upper": 4,
    "real_lower": -3,
    "real_upper": 5,
}
REGISTERED_OUTPUT = b"true"

PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_verify.py",
    "replay-a7-flint",
    "${TG_A7_TRANSCRIPT}",
    "--registered-result-output",
    "${TG_RUN_ROOT}/ch25-a7-boundary/registered-result.txt",
)

SOURCE_PATHS = (
    "tools/tg_a7_azure_measured_workload.py",
    "tools/tg_verify.py",
    "tools/fetch_flint_platt.py",
    "tools/fetch_python_flint.py",
    "tg_verifier/a7_flint.py",
    "tg_verifier/analytic.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/python_flint_runtime.py",
    "specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    "specifications/PYTHON_FLINT_0_9_UPSTREAM.json",
)


def _command(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_a7_azure_measured_workload.py",
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
        "--artifact",
        "artifacts/a7_boundary.json",
        "--wheel",
        RUNTIME_WHEEL_PATH,
        "--work",
        "work/a7-boundary",
    )


@dataclass(frozen=True)
class A7CPUWorkloadFactory:
    factory_id: str = "ch25_a7_boundary_python_flint_x86_cpu_v1"
    group_id: str = GROUP_ID
    registered_invocation: str = REGISTERED_INVOCATION
    portfolio_argv: tuple[str, ...] = PORTFOLIO_ARGV
    algorithm_id: str = REGISTERED_ALGORITHM_ID
    algorithm_definition: str = REGISTERED_ALGORITHM_DEFINITION
    input_bytes: bytes = REGISTERED_INPUT
    parameters: dict[str, Any] | None = None
    domain: dict[str, Any] | None = None
    command_argv: tuple[str, ...] = _command("run")
    trace_verifier_argv: tuple[str, ...] = _command("verify-trace")
    timeout_seconds: int = 30 * 60
    trace_iterations: int = 3
    output_format: str = "opaque_bytes_v1"
    output_maximum_bytes: int = 16
    source_paths: tuple[str, ...] = SOURCE_PATHS

    def __post_init__(self) -> None:
        if self.parameters is None:
            object.__setattr__(self, "parameters", dict(REGISTERED_PARAMETERS))
        if self.domain is None:
            object.__setattr__(self, "domain", dict(REGISTERED_DOMAIN))


A7_FACTORY = A7CPUWorkloadFactory()


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int = 0,
) -> A7CPUWorkloadFactory | None:
    factory = A7_FACTORY
    if (
        shard_index != 0
        or group.get("campaign_id") != CAMPAIGN_ID
        or group.get("group_id") != GROUP_ID
        or group.get("phase_id") != "single-job"
        or group.get("backend_class") != "cpu_flint_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != "ch25-a7-boundary"
        or group.get("operator_adapter") != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != 1
        or group.get("terminal") is not True
        or tuple(group.get("depends_on", ())) != ()
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
        "parameters_hash": hashlib.sha256(canonical(REGISTERED_PARAMETERS)).hexdigest(),
    }


__all__ = [
    "A7_FACTORY",
    "CAMPAIGN_ID",
    "GROUP_ID",
    "REGISTERED_INVOCATION",
    "RETAINED_ARTIFACT_SHA256",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "source_reviewed_materializer_available",
]
