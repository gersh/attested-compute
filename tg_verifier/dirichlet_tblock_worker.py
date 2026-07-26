# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic bounded protocol harness for the t-block supervisor.

This worker authenticates the streamed rows and independently enumerates the
formulaic active-q roster.  It intentionally does not pretend to execute the
composer, all-character transform, completed-L consumer, typed-bundle replay,
or t-major adapter.  Its handshake therefore cannot pass production
admission.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any, Mapping, NoReturn

from tg_verifier.dirichlet_lattice_cache import (
    ROW_PAYLOAD_BYTES,
    canonical_json_bytes,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    maximum_t_index,
)
from tg_verifier.dirichlet_source_supervisor import FFT_BATCH_SIZE
from tg_verifier.dirichlet_tblock_supervisor import (
    ACTIVE_Q_PREDICATE_ID,
    ATOM_ID,
    AUTHOR,
    HANDSHAKE_SCHEMA,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    STRUCTURAL_WORKER_CLASSIFICATION,
    TARGET_DESCRIPTOR_ID,
    WORKER_ALGORITHM_ID,
    _canonical_line,
    _digest,
    _integer,
    _self_hash,
    extend_result_chain,
)
from tg_verifier.dirichlet_tmajor_spool import BLOCK_ROW_BINDING_DOMAIN


EMPTY_TYPED_BUNDLE_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-worker/empty-bundles/v1\0"
)


class DirichletTBlockWorkerError(RuntimeError):
    """A structural worker request or streamed row failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTBlockWorkerError(message)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def structural_handshake(implementation_path: Path) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": HANDSHAKE_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "classification": STRUCTURAL_WORKER_CLASSIFICATION,
        "worker_id": "python-structural-t-block-protocol-harness-v1",
        "worker_implementation_sha256": _file_sha256(implementation_path),
        "capabilities": {
            "accepts_one_authenticated_t_block_payload": True,
            "derives_exact_active_q_roster_formulaically": True,
            "multi_q_target_iteration": True,
            "multi_q_plan_switching": False,
            "resumable_idempotent_outputs": True,
            "actual_residue_composer": False,
            "actual_all_character_transform": False,
            "actual_completed_l_consumer": False,
            "typed_bundle_emission": False,
            "adapter_compatible_output": False,
            "framed_typed_bundle_bytes_to_supervisor": False,
        },
        "claims": {
            "cuda_execution_attested": False,
            "completed_l_zero_completeness": False,
            "turing_completeness": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    result = dict(body)
    result["handshake_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _validate_roster(
    request: Mapping[str, Any],
) -> tuple[int, int, str]:
    roster = request.get("target_roster")
    block = request.get("row_block")
    if not isinstance(roster, dict) or not isinstance(block, dict):
        _fail("request roster or row block is malformed")
    first = _integer(
        block.get("first_t_index"), "block first t", minimum=0
    )
    stop = _integer(
        block.get("t_index_stop_exclusive"),
        "block t stop",
        minimum=first + 1,
        maximum=first + FFT_BATCH_SIZE,
    )
    q_start = _integer(
        roster.get("q_start_inclusive"), "q start", minimum=10_001
    )
    q_stop = _integer(
        roster.get("q_stop_inclusive"), "q stop", minimum=q_start
    )
    expected_formula = {
        "source_contract_sha256": request.get("source_contract_sha256"),
        "lane_index": request.get("lane_index"),
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "q_iteration_order": "strictly_increasing",
        "active_q_predicate_id": ACTIVE_Q_PREDICATE_ID,
        "active_q_predicate": "first_t_index <= maximum_t_index(q)",
        "maximum_t_index_equation": (
            "floor(max(100000000,200*q+(75000000 if q even "
            "else 37500000))*64/(5*q))"
        ),
        "target_descriptor_id": TARGET_DESCRIPTOR_ID,
        "target_batch_stop_equation": (
            "min(t_index_stop_exclusive,maximum_t_index(q)+1)"
        ),
        "first_t_index": first,
        "t_index_stop_exclusive": stop,
        "sample_numerator": SOURCE_SAMPLE_NUMERATOR,
        "sample_denominator": SOURCE_SAMPLE_DENOMINATOR,
    }
    formula_sha256 = hashlib.sha256(
        canonical_json_bytes(expected_formula)
    ).hexdigest()
    observed_formula = {
        key: roster.get(key) for key in expected_formula
    }
    if observed_formula != expected_formula:
        _fail("target-roster public formula differs")
    if roster.get("target_roster_formula_sha256") != formula_sha256:
        _fail("target-roster formula digest differs")

    active = 0
    references = 0
    # This loop is the bounded harness's independent enumeration.  A real
    # worker must use the same order while switching/retaining its q plans.
    for q in range(q_start, q_stop + 1):
        maximum = maximum_t_index(q)
        if first <= maximum:
            active += 1
            references += min(stop, maximum + 1) - first
    if (
        roster.get("active_q_count") != active
        or roster.get("target_row_reference_count") != references
    ):
        _fail("target-roster count differs from independent enumeration")
    expected_keys = set(expected_formula) | {
        "active_q_count",
        "target_row_reference_count",
        "target_roster_formula_sha256",
    }
    if set(roster) != expected_keys:
        _fail("target-roster fields differ")
    return active, references, formula_sha256


def _read_payload(
    request: Mapping[str, Any],
    source: Any,
) -> str:
    block = request.get("row_block")
    if not isinstance(block, dict):
        _fail("row block is malformed")
    expected_keys = {
        "row_payload_bytes",
        "row_count",
        "first_t_index",
        "t_index_stop_exclusive",
        "rows",
        "row_bindings_sha256",
    }
    if set(block) != expected_keys:
        _fail("row-block fields differ")
    count = _integer(
        block.get("row_count"),
        "row count",
        minimum=1,
        maximum=FFT_BATCH_SIZE,
    )
    if block.get("row_payload_bytes") != ROW_PAYLOAD_BYTES:
        _fail("row payload geometry differs")
    first = _integer(block.get("first_t_index"), "block first t", minimum=0)
    stop = _integer(
        block.get("t_index_stop_exclusive"),
        "block t stop",
        minimum=first + 1,
        maximum=first + FFT_BATCH_SIZE,
    )
    if stop - first != count:
        _fail("row-block count and bounds differ")
    rows = block.get("rows")
    if not isinstance(rows, list) or len(rows) != count:
        _fail("row-block roster length differs")

    binding = hashlib.sha256(BLOCK_ROW_BINDING_DOMAIN)
    binding.update(
        bytes.fromhex(_digest(request.get("spool_receipt_sha256"), "spool"))
    )
    payload_stream = hashlib.sha256()
    for offset, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or set(row) != {"t_index", "payload_sha256"}
            or row.get("t_index") != first + offset
        ):
            _fail("row-block roster is substituted, skipped, or reordered")
        expected_sha256 = _digest(
            row.get("payload_sha256"), "row payload"
        )
        payload = source.read(ROW_PAYLOAD_BYTES)
        if len(payload) != ROW_PAYLOAD_BYTES:
            _fail("streamed t-block payload is truncated")
        observed_sha256 = hashlib.sha256(payload).hexdigest()
        if observed_sha256 != expected_sha256:
            _fail("streamed t-block payload is substituted")
        binding.update((first + offset).to_bytes(8, "little"))
        binding.update(bytes.fromhex(expected_sha256))
        payload_stream.update(payload)
    if binding.hexdigest() != block.get("row_bindings_sha256"):
        _fail("row-block binding digest differs")
    return payload_stream.hexdigest()


def process_request(
    request: Mapping[str, Any],
    source: Any,
    *,
    handshake: Mapping[str, Any],
) -> dict[str, Any]:
    _self_hash(request, "request_sha256", label="worker request")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "sequence_index",
        "source_contract_sha256",
        "spool_receipt_sha256",
        "lane_index",
        "row_block",
        "target_roster",
        "result_chain_before",
        "request_sha256",
    }
    if (
        set(request) != required
        or request.get("schema") != REQUEST_SCHEMA
        or request.get("schema_version") != 1
        or request.get("author") != AUTHOR
        or request.get("atom_id") != ATOM_ID
        or request.get("algorithm_id")
        != "platt-dirichlet-t-block-supervisor-v1"
    ):
        _fail("worker request identity or fields differ")
    sequence = _integer(
        request.get("sequence_index"), "sequence index", minimum=0
    )
    _digest(request.get("source_contract_sha256"), "source contract")
    _digest(request.get("spool_receipt_sha256"), "spool receipt")
    _integer(request.get("lane_index"), "lane index", minimum=0)
    _digest(request.get("result_chain_before"), "result-chain predecessor")
    active, references, formula_sha256 = _validate_roster(request)
    payload_sha256 = _read_payload(request, source)
    empty_chain = hashlib.sha256(EMPTY_TYPED_BUNDLE_CHAIN_DOMAIN)
    empty_chain.update(bytes.fromhex(request["request_sha256"]))
    typed_chain = empty_chain.hexdigest()
    result_after = extend_result_chain(
        before=request["result_chain_before"],
        request_sha256=request["request_sha256"],
        payload_stream_sha256=payload_sha256,
        typed_bundle_count=0,
        typed_bundle_chain_sha256=typed_chain,
    )
    body: dict[str, Any] = {
        "schema": RESPONSE_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "status": "completed",
        "sequence_index": sequence,
        "request_sha256": request["request_sha256"],
        "payload_stream_sha256": payload_sha256,
        "active_q_count": active,
        "target_row_reference_count": references,
        "target_roster_formula_sha256": formula_sha256,
        "typed_bundle_count": 0,
        "typed_bundle_chain_sha256": typed_chain,
        "result_chain_before": request["result_chain_before"],
        "result_chain_after": result_after,
        "services_executed": {
            "residue_composer": False,
            "all_character_transform": False,
            "completed_l_consumer": False,
            "typed_bundle_builder_and_replay": False,
            "tmajor_adapter": False,
        },
        "claims": dict(handshake["claims"]),
    }
    result = dict(body)
    result["response_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--fail-on-sequence", type=int)
    result.add_argument("--truncate-response-on-sequence", type=int)
    result.add_argument("--substitute-response-on-sequence", type=int)
    return result


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    implementation_path = Path(__file__).resolve()
    handshake = structural_handshake(implementation_path)
    output = sys.stdout.buffer
    source = sys.stdin.buffer
    output.write(canonical_json_bytes(handshake))
    output.flush()
    try:
        while raw := source.readline(1024 * 1024 + 1):
            request = _canonical_line(raw, label="worker request")
            sequence = request.get("sequence_index")
            if sequence == args.fail_on_sequence:
                _fail("injected downstream failure")
            response = process_request(
                request,
                source,
                handshake=handshake,
            )
            if sequence == args.substitute_response_on_sequence:
                response["active_q_count"] += 1
                body = dict(response)
                body.pop("response_sha256")
                response["response_sha256"] = hashlib.sha256(
                    canonical_json_bytes(body)
                ).hexdigest()
            raw_response = canonical_json_bytes(response)
            if sequence == args.truncate_response_on_sequence:
                output.write(raw_response[: len(raw_response) // 2])
                output.flush()
                return 7
            output.write(raw_response)
            output.flush()
    except (DirichletTBlockWorkerError, RuntimeError, ValueError) as error:
        print(f"Dirichlet t-block worker error: {error}", file=sys.stderr)
        return 2
    return 0
