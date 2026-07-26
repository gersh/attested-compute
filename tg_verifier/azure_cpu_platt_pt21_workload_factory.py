# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed workload identities for the five-stage PT21 reference campaign.

The source-wide CPU/FLINT implementation is an exact, deliberately unscaled
reference route.  It is not the incomplete optimized H100 implementation and
it is not evidence for the one-week/$10k deployment objective.  Both routes
are described by one hash-pinned execution-contract inventory so a future
producer can preserve the mathematical five-stage boundary without silently
changing its count, prefix, shard coverage, or final Merkle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.platt_zeta_campaign import (
    ATOM,
    DEFAULT_FLINT_THREADS,
    DEFAULT_MICRO_BATCH,
    DEFAULT_PRECISION_BITS,
    DEFAULT_SHARD_SPAN,
    FINAL_SCHEMA,
    FLINT_COMMIT,
    PLAN_SCHEMA,
    PLATT_FIRST_INDEX,
    PREFIX_LAST_INDEX,
    RECEIPT_SCHEMA,
    SOURCE_COUNT,
    SOURCE_HEIGHT,
    SOURCE_SENTINEL,
    SOURCE_UPPER_EXCLUSIVE,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "specifications/PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json"
)
CONTRACT_FILE_SHA256 = (
    "ad280f4795d0bf9f6172a8be3b104075b2eace86ebbe74d387a41d377b551176"
)
REFERENCE_CONTRACT_ID = "reference-cpu-flint-3.6-v1"
OPTIMIZED_CONTRACT_ID = "optimized-h100-windowed-v2"
CAMPAIGN_ID = "platt-trudgian-rh-3e12"
REGISTERED_INVOCATION = "plattTrudgianFiniteRHProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.platt-trudgian-finite-rh.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-platt-trudgian-finite-rh\n"
    "producer=tg_verifier/platt_zeta_campaign.py\n"
    "semantics=fixed-index-flint-platt-turing-chunked-zero-isolation-and-global-count\n"
    "source-height=3000175332800\n"
    "source-multiplicity-count=12363153437138\n"
    "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n"
    "output=false-or-true-with-source-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"platt-trudgian-rh-3e12",'
    b'"multiplicity_count":12363153437138,'
    b'"source_height":3000175332800}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "flint_commit": FLINT_COMMIT,
    "flint_threads": DEFAULT_FLINT_THREADS,
    "flint_version": "3.6.0",
    "micro_batch": DEFAULT_MICRO_BATCH,
    "precision_bits": DEFAULT_PRECISION_BITS,
    "shard_count": 1_236_316,
    "shard_span": DEFAULT_SHARD_SPAN,
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "claim": "platt-trudgian-finite-rh-source",
    "imag_lower_exclusive": 0,
    "multiplicity_count": SOURCE_COUNT,
    "real_lower_exclusive": 0,
    "real_upper_exclusive": 1,
    "source_height": SOURCE_HEIGHT,
}
REGISTERED_OUTPUT = b"true"

SHARD_COUNT = 1_236_316
WORKSPACE = "${TG_RUN_ROOT}/platt-trudgian-rh-3e12"
TOOL = "${TG_REPOSITORY}/tools/tg_platt_zeta_campaign.py"
PHASE_COMMANDS: dict[str, tuple[str, ...]] = {
    "initialize": (
        "${TG_PYTHON}",
        TOOL,
        "init",
        WORKSPACE,
        "--runner",
        "${TG_TG_BUILD}/sparkinterval-tg-platt-zeta-shard",
        "--runner-source",
        "${TG_REPOSITORY}/reference/tg_platt_zeta_shard.cpp",
        "--upstream-manifest",
        "${TG_REPOSITORY}/specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    ),
    "exact-multiplicity-count": (
        "${TG_PYTHON}",
        TOOL,
        "count",
        WORKSPACE,
    ),
    "ordinary-low-index-prefix": (
        "${TG_PYTHON}",
        TOOL,
        "prefix",
        WORKSPACE,
    ),
    "platt-turing-index-shards": (
        "${TG_PYTHON}",
        TOOL,
        "run-shard",
        WORKSPACE,
        "${TG_ARRAY_INDEX}",
    ),
    "finalize-merkle-certificate": (
        "${TG_PYTHON}",
        TOOL,
        "finalize",
        WORKSPACE,
        "--registered-result-output",
        f"{WORKSPACE}/registered-result.txt",
    ),
}
PHASE_COUNTS = {
    "initialize": 1,
    "exact-multiplicity-count": 1,
    "ordinary-low-index-prefix": 1,
    "platt-turing-index-shards": SHARD_COUNT,
    "finalize-merkle-certificate": 1,
}
PHASE_DEPENDENCIES = {
    "initialize": (),
    "exact-multiplicity-count": (f"{CAMPAIGN_ID}::initialize",),
    "ordinary-low-index-prefix": (
        f"{CAMPAIGN_ID}::exact-multiplicity-count",
    ),
    "platt-turing-index-shards": (
        f"{CAMPAIGN_ID}::ordinary-low-index-prefix",
    ),
    "finalize-merkle-certificate": (
        f"{CAMPAIGN_ID}::platt-turing-index-shards",
    ),
}

SOURCE_PATHS = (
    "tools/tg_azure_cpu_platt_pt21_materializer.py",
    "tools/tg_platt_pt21_azure_measured_workload.py",
    "tools/tg_platt_zeta_campaign.py",
    "tg_verifier/azure_cpu_platt_pt21_materializer.py",
    "tg_verifier/azure_cpu_platt_pt21_workload_factory.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/platt_zeta_campaign.py",
    "attestation/measured_run_archive.py",
    "reference/tg_platt_zeta_shard.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
    "specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    "specifications/PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json",
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.platt-pt21-reference.v1\n"
    "initial=SHA256(initial-domain || phase || shard-index || challenge-nonce || "
    "job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || authenticated-handoff-sha256 || "
    "authenticated-handoff-tree-sha256)\n"
    "step-1=SHA256(step-domain || previous || retained-export-sha256 || "
    "retained-export-tree-sha256)\n"
    "step-2=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-python-replays-the-exact-phase-and-validates-the-fixed-"
    "count-prefix-1236316-shard-merkle-chain"
)


class PT21WorkloadFactoryError(RuntimeError):
    """The immutable campaign or implementation contract changed."""


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_contract_inventory() -> dict[str, Any]:
    try:
        if hash_file_once(CONTRACT_PATH)[0] != CONTRACT_FILE_SHA256:
            raise PT21WorkloadFactoryError(
                "PT21 execution-contract inventory differs from its source pin"
            )
        value = load_json(CONTRACT_PATH)
    except (CampaignIOError, OSError, ValueError) as error:
        if isinstance(error, PT21WorkloadFactoryError):
            raise
        raise PT21WorkloadFactoryError(
            f"cannot load PT21 execution-contract inventory: {error}"
        ) from error
    if not isinstance(value, dict) or set(value) != {
        "implementations",
        "kind",
        "mathematical_campaign",
        "schema_version",
    }:
        raise PT21WorkloadFactoryError(
            "PT21 execution-contract inventory fields changed"
        )
    if (
        value["kind"]
        != "sparkinterval.platt-pt21.azure-execution-contracts.v1"
        or value["schema_version"] != 1
        or not isinstance(value["implementations"], list)
    ):
        raise PT21WorkloadFactoryError(
            "PT21 execution-contract inventory kind/version changed"
        )
    mathematical = value["mathematical_campaign"]
    expected_mathematical = {
        "atom_id": ATOM,
        "source_height": SOURCE_HEIGHT,
        "multiplicity_count": SOURCE_COUNT,
        "ordinary_prefix_last_index": PREFIX_LAST_INDEX,
        "platt_first_index": PLATT_FIRST_INDEX,
        "sentinel_index": SOURCE_SENTINEL,
        "source_upper_exclusive": SOURCE_UPPER_EXCLUSIVE,
        "shard_span": DEFAULT_SHARD_SPAN,
        "shard_count": SHARD_COUNT,
        "phases": [
            {"phase_id": phase, "shard_count": PHASE_COUNTS[phase],
             "depends_on": [
                 dependency.removeprefix(f"{CAMPAIGN_ID}::")
                 for dependency in PHASE_DEPENDENCIES[phase]
             ]}
            for phase in PHASE_COUNTS
        ],
        "receipt_merkle_rule": (
            "sha256(00||leaf-digest), sha256(01||left||right), duplicate odd right"
        ),
        "zero_multiplicity_preserved": True,
        "simplicity_assumed": False,
    }
    if mathematical != expected_mathematical:
        raise PT21WorkloadFactoryError(
            "PT21 mathematical five-stage contract changed"
        )
    rows = value["implementations"]
    identifiers = [
        row.get("contract_id") if isinstance(row, dict) else None for row in rows
    ]
    if identifiers != [REFERENCE_CONTRACT_ID, OPTIMIZED_CONTRACT_ID]:
        raise PT21WorkloadFactoryError(
            "PT21 implementation contract order or identity changed"
        )
    return value


def execution_contract(contract_id: str) -> dict[str, Any]:
    """Return one reviewed implementation contract after exact source checks."""

    inventory = _load_contract_inventory()
    row = next(
        (
            item
            for item in inventory["implementations"]
            if item["contract_id"] == contract_id
        ),
        None,
    )
    if not isinstance(row, dict):
        raise PT21WorkloadFactoryError(
            f"unknown PT21 execution contract: {contract_id}"
        )
    return row


def production_capability_complete(contract: Mapping[str, Any]) -> bool:
    """The materializer may package only a source-complete implementation.

    Economic readiness is intentionally *not* part of this predicate.  The
    reference route is complete enough to reproduce the computation but is
    separately rejected by the portfolio sizing gate.
    """

    capability = contract.get("capability")
    if not isinstance(capability, Mapping):
        return False
    required = (
        "worker_complete",
        "finalizer_complete",
        "full_source_geometry_complete",
        "retained_export_replay_complete",
        "production_materializer_allowed",
    )
    return all(capability.get(field) is True for field in required)


def _reference_contract() -> dict[str, Any]:
    contract = execution_contract(REFERENCE_CONTRACT_ID)
    worker = contract.get("worker_interface")
    finalizer = contract.get("finalizer_interface")
    if (
        contract.get("backend_class") != "cpu_flint_sidecar"
        or contract.get("receipt_backend") != "azure_sevsnp_cpu"
        or not isinstance(worker, dict)
        or worker.get("source") != "reference/tg_platt_zeta_shard.cpp"
        or worker.get("supervisor") != "tg_verifier/platt_zeta_campaign.py"
        or worker.get("flint_commit") != FLINT_COMMIT
        or worker.get("flint_version") != "3.6.0"
        or worker.get("precision_bits") != DEFAULT_PRECISION_BITS
        or worker.get("micro_batch") != DEFAULT_MICRO_BATCH
        or worker.get("flint_threads") != DEFAULT_FLINT_THREADS
        or not isinstance(finalizer, dict)
        or finalizer.get("supervisor") != "tg_verifier/platt_zeta_campaign.py"
        or finalizer.get("plan_schema") != PLAN_SCHEMA
        or finalizer.get("receipt_schema") != RECEIPT_SCHEMA
        or finalizer.get("final_schema") != FINAL_SCHEMA
        or any(
            finalizer.get(field) is not True
            for field in (
                "requires_count",
                "requires_prefix",
                "requires_all_shards",
            )
        )
    ):
        raise PT21WorkloadFactoryError(
            "reference PT21 worker/finalizer interface changed"
        )
    if not production_capability_complete(contract):
        raise PT21WorkloadFactoryError(
            "reference PT21 production worker/finalizer capability is incomplete"
        )
    if contract["capability"].get("under_one_week_and_10000_usd") is not False:
        raise PT21WorkloadFactoryError(
            "unscaled PT21 reference contract made an economic readiness claim"
        )
    return contract


@dataclass(frozen=True)
class PT21CPUWorkloadFactory:
    factory_id: str
    execution_contract_id: str
    execution_contract_sha256: str
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


def shard_index_range(shard_index: int) -> tuple[int, int]:
    if not 0 <= shard_index < SHARD_COUNT:
        raise ValueError("PT21 shard index is outside the fixed source geometry")
    lower = PLATT_FIRST_INDEX + shard_index * DEFAULT_SHARD_SPAN
    upper = min(SOURCE_UPPER_EXCLUSIVE, lower + DEFAULT_SHARD_SPAN)
    return lower, upper


def _operational_identity(
    phase: str, shard_index: int, contract_sha256: str
) -> tuple[str, str]:
    range_lines = ""
    if phase == "platt-turing-index-shards":
        lower, upper = shard_index_range(shard_index)
        range_lines = (
            f"first-index={lower}\n"
            f"upper-exclusive={upper}\n"
            f"record-count={upper - lower}\n"
        )
    definition = (
        "sparkinterval.azure-operational-algorithm.v1\n"
        f"campaign={CAMPAIGN_ID}\n"
        f"phase={phase}\n"
        f"shard-index={shard_index}\n"
        f"execution-contract-sha256={contract_sha256}\n"
        f"{range_lines}"
        "semantics=retain-and-independently-replay-the-exact-fixed-pt21-phase\n"
        "output=deterministic-retained-export-identity"
    )
    suffix = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return (
        f"sparkinterval.tg.platt-pt21.azure-phase.{phase}."
        f"{shard_index}.{suffix}",
        definition,
    )


def _command(
    *,
    mode: str,
    phase: str,
    shard_index: int,
    algorithm_id: str,
) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_platt_pt21_azure_measured_workload.py",
        mode,
        "--phase",
        phase,
        "--shard-index",
        str(shard_index),
        "--algorithm-id",
        algorithm_id,
        "--execution-contract",
        "specifications/PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json",
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--handoff",
        "input/pt21-phase-handoff.tar",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--work",
        "work/pt21",
        "--runner",
        "artifacts/tg_platt_zeta_shard",
        "--runner-source",
        "reference/tg_platt_zeta_shard.cpp",
        "--upstream-manifest",
        "specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    )


def make_factory(phase: str, shard_index: int) -> PT21CPUWorkloadFactory:
    _reference_contract()
    if phase not in PHASE_COUNTS or not 0 <= shard_index < PHASE_COUNTS[phase]:
        raise ValueError("PT21 phase/shard is outside the reviewed five-stage DAG")
    terminal = phase == "finalize-merkle-certificate"
    if terminal:
        algorithm_id = REGISTERED_ALGORITHM_ID
        definition = REGISTERED_ALGORITHM_DEFINITION
        input_bytes = REGISTERED_INPUT
        parameters = dict(REGISTERED_PARAMETERS)
        domain = dict(REGISTERED_DOMAIN)
    else:
        algorithm_id, definition = _operational_identity(
            phase, shard_index, CONTRACT_FILE_SHA256
        )
        input_value: dict[str, Any] = {
            "campaign_id": CAMPAIGN_ID,
            "execution_contract_id": REFERENCE_CONTRACT_ID,
            "execution_contract_sha256": CONTRACT_FILE_SHA256,
            "phase": phase,
            "shard_index": shard_index,
        }
        domain = {
            "campaign": CAMPAIGN_ID,
            "phase": phase,
            "shard_index": shard_index,
            "source_height": SOURCE_HEIGHT,
        }
        if phase == "platt-turing-index-shards":
            lower, upper = shard_index_range(shard_index)
            input_value.update(
                {"first_index": lower, "upper_exclusive": upper}
            )
            domain.update(
                {"first_index": lower, "upper_exclusive": upper}
            )
        input_bytes = canonical_json_bytes(input_value)
        parameters = {
            "flint_commit": FLINT_COMMIT,
            "flint_threads": DEFAULT_FLINT_THREADS,
            "micro_batch": DEFAULT_MICRO_BATCH,
            "precision_bits": DEFAULT_PRECISION_BITS,
            "shard_count": SHARD_COUNT,
            "shard_span": DEFAULT_SHARD_SPAN,
        }
    timeouts = {
        "initialize": 30 * 60,
        "exact-multiplicity-count": 2 * 60 * 60,
        "ordinary-low-index-prefix": 2 * 60 * 60,
        "platt-turing-index-shards": 44 * 60 * 60,
        "finalize-merkle-certificate": 24 * 60 * 60,
    }
    return PT21CPUWorkloadFactory(
        factory_id=f"platt_pt21_{phase}_{shard_index:07d}_reference_cpu_v1",
        execution_contract_id=REFERENCE_CONTRACT_ID,
        execution_contract_sha256=CONTRACT_FILE_SHA256,
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
        command_argv=_command(
            mode="run",
            phase=phase,
            shard_index=shard_index,
            algorithm_id=algorithm_id,
        ),
        trace_verifier_argv=_command(
            mode="verify-trace",
            phase=phase,
            shard_index=shard_index,
            algorithm_id=algorithm_id,
        ),
        timeout_seconds=timeouts[phase],
        trace_iterations=3,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=16 if terminal else 1024,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int
) -> PT21CPUWorkloadFactory | None:
    if group.get("campaign_id") != CAMPAIGN_ID:
        return None
    phase = group.get("phase_id")
    if not isinstance(phase, str) or phase not in PHASE_COUNTS:
        return None
    try:
        factory = make_factory(phase, shard_index)
    except (PT21WorkloadFactoryError, ValueError):
        return None
    if (
        group.get("group_id") != factory.group_id
        or group.get("backend_class") != "cpu_flint_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != CAMPAIGN_ID
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
    """O(1) exact-shape gate; never allocate 1,236,316 factory objects."""

    phase = group.get("phase_id")
    if not isinstance(phase, str) or phase not in PHASE_COUNTS:
        return False
    count = PHASE_COUNTS[phase]
    return (
        factory_for_portfolio_group(group, 0) is not None
        and factory_for_portfolio_group(group, count - 1) is not None
    )


def expected_registered_hashes() -> dict[str, str]:
    return {
        "algorithm_hash": hashlib.sha256(
            REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
        ).hexdigest(),
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": _canonical_hash(REGISTERED_DOMAIN),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": hashlib.sha256(REGISTERED_OUTPUT).hexdigest(),
        "parameters_hash": _canonical_hash(REGISTERED_PARAMETERS),
    }


__all__ = [
    "CAMPAIGN_ID",
    "CONTRACT_FILE_SHA256",
    "CONTRACT_PATH",
    "OPTIMIZED_CONTRACT_ID",
    "PHASE_COUNTS",
    "PHASE_DEPENDENCIES",
    "REFERENCE_CONTRACT_ID",
    "REGISTERED_INVOCATION",
    "SHARD_COUNT",
    "SOURCE_PATHS",
    "TRACE_DEFINITION",
    "PT21CPUWorkloadFactory",
    "PT21WorkloadFactoryError",
    "execution_contract",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "make_factory",
    "production_capability_complete",
    "shard_index_range",
    "source_reviewed_materializer_available",
]
