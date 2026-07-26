# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU workload factory for the Platt zeta head through 20,000."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


CAMPAIGN_ID = "platt-head-2e4"
GROUP_ID = "platt-head-2e4::single-job"
REGISTERED_INVOCATION = "plattHead2e4ProductionV1"
REGISTERED_ALGORITHM_ID = "sparkinterval.ternary-goldbach.platt-head-2e4.v1"
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-platt-head-2e4\n"
    "producer=tg_verifier/zeta_zero_campaign.py\n"
    "semantics=complete-indexed-flint-platt-head-replay-to-literal-q128-table\n"
    "source-height=20000\n"
    "source-multiplicity-count=22491\n"
    "all-q128-rows-sha256=fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca\n"
    "included-q128-rows-sha256=e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7\n"
    "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n"
    "output=false-or-true-with-literal-q128-checked-head-evidence"
)
REGISTERED_INPUT = (
    b'{"all_q128_rows_sha256":"fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",'
    b'"campaign":"platt-head-2e4",'
    b'"included_q128_rows_sha256":"e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",'
    b'"source_height":20000,"source_multiplicity_count":22491}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "flint_release": 30_600,
    "flint_threads": 1,
    "flint_version": "3.6.0",
    "precision_bits": 96,
    "python_flint_version": "0.9.0",
    "q128_scale_bits": 128,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "all_q128_rows_sha256": "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",
    "claim": "platt-zero-enumeration-2e4-source",
    "imag_lower_exclusive": 0,
    "included_q128_rows_sha256": "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",
    "multiplicity_count": 22_491,
    "real_lower_exclusive": 0,
    "real_upper_exclusive": 1,
    "source_height": 20_000,
}
REGISTERED_OUTPUT = b"true"
RUNTIME_WHEEL_PATH = (
    "runtime/python_flint-0.9.0-cp310-abi3-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.whl"
)

PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_zeta_campaign.py",
    "full",
    "${TG_RUN_ROOT}/platt-head-2e4",
    "--profile",
    "platt-head-2e4",
    "--batch-size",
    "4096",
    "--precision-bits",
    "96",
    "--registered-result-output",
    "${TG_RUN_ROOT}/platt-head-2e4/registered-result.txt",
)

SOURCE_PATHS = (
    "tools/tg_platt_head_azure_measured_workload.py",
    "tools/tg_zeta_campaign.py",
    "tools/fetch_flint_platt.py",
    "tools/fetch_python_flint.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/python_flint_runtime.py",
    "tg_verifier/zeta_zero_campaign.py",
    "attestation/measured_run_archive.py",
    "specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    "specifications/PYTHON_FLINT_0_9_UPSTREAM.json",
)


def _command(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_platt_head_azure_measured_workload.py",
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
        "--wheel",
        RUNTIME_WHEEL_PATH,
        "--work",
        "work/platt-head",
    )


@dataclass(frozen=True)
class PlattHeadCPUWorkloadFactory:
    factory_id: str = "platt_head_2e4_python_flint_x86_cpu_v1"
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
    timeout_seconds: int = 2 * 60 * 60
    trace_iterations: int = 3
    output_format: str = "opaque_bytes_v1"
    output_maximum_bytes: int = 16
    source_paths: tuple[str, ...] = SOURCE_PATHS

    def __post_init__(self) -> None:
        if self.parameters is None:
            object.__setattr__(self, "parameters", dict(REGISTERED_PARAMETERS))
        if self.domain is None:
            object.__setattr__(self, "domain", dict(REGISTERED_DOMAIN))


PLATT_HEAD_FACTORY = PlattHeadCPUWorkloadFactory()


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int = 0,
) -> PlattHeadCPUWorkloadFactory | None:
    factory = PLATT_HEAD_FACTORY
    if (
        shard_index != 0
        or group.get("campaign_id") != CAMPAIGN_ID
        or group.get("group_id") != GROUP_ID
        or group.get("phase_id") != "single-job"
        or group.get("backend_class") != "cpu_flint_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != "platt-head-2e4"
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
    "CAMPAIGN_ID",
    "GROUP_ID",
    "PLATT_HEAD_FACTORY",
    "REGISTERED_INVOCATION",
    "RUNTIME_WHEEL_PATH",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "source_reviewed_materializer_available",
]
