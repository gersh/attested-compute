# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded protocol-v2 worker that transports staged real typed bundles.

The worker authenticates the incoming row block and exact target roster, then
ships prebuilt typed-bundle files as length-framed bytes.  It does not claim
that it ran the composer, transform, consumer, replay, adapter, CUDA, or an
attested source campaign.  The supervisor independently performs replay and
adapter admission after receipt.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any, Mapping, NoReturn

from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    ALGORITHM_ID as SUPERVISOR_ALGORITHM_ID,
    FRAME_LENGTH,
    FRAME_SCHEMA,
    HANDSHAKE_SCHEMA,
    MAXIMUM_BUNDLE_BYTES,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    STREAM_SCHEMA,
    WORKER_ALGORITHM_ID,
    WORKER_CLASSIFICATION,
)
from tg_verifier.dirichlet_tmajor_adapter import BLOCK_MAJOR_TARGET_ORDER
from tg_verifier.dirichlet_tblock_supervisor import (
    ATOM_ID,
    AUTHOR,
    _canonical_line,
    _digest,
    _integer,
    _self_hash,
)
from tg_verifier.dirichlet_tblock_worker import (
    _file_sha256,
    _read_payload,
    _validate_roster,
)


class DirichletTBlockBundleWorkerError(RuntimeError):
    """A v2 request, staged bundle, or injected protocol path failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTBlockBundleWorkerError(message)


def bundle_handshake(implementation_path: Path) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": HANDSHAKE_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "classification": WORKER_CLASSIFICATION,
        "worker_id": "python-bounded-typed-bundle-transport-v2",
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
            "typed_bundle_emission": True,
            "adapter_compatible_output": True,
            "framed_typed_bundle_bytes_to_supervisor": True,
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


def _validate_request(
    request: Mapping[str, Any],
    source: Any,
) -> tuple[int, int, str, str]:
    _self_hash(request, "request_sha256", label="v2 worker request")
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
        "bundle_output_order",
        "request_sha256",
    }
    if (
        set(request) != required
        or request.get("schema") != REQUEST_SCHEMA
        or request.get("schema_version") != 2
        or request.get("author") != AUTHOR
        or request.get("atom_id") != ATOM_ID
        or request.get("algorithm_id") != SUPERVISOR_ALGORITHM_ID
        or request.get("bundle_output_order") != BLOCK_MAJOR_TARGET_ORDER
    ):
        _fail("v2 worker request identity or fields differ")
    _integer(request.get("sequence_index"), "sequence index", minimum=0)
    _digest(request.get("source_contract_sha256"), "source contract")
    _digest(request.get("spool_receipt_sha256"), "spool receipt")
    _integer(request.get("lane_index"), "lane index", minimum=0)
    _digest(request.get("result_chain_before"), "result-chain predecessor")
    active, references, formula_sha256 = _validate_roster(request)
    payload_sha256 = _read_payload(request, source)
    return active, references, formula_sha256, payload_sha256


def _stream_header(
    request: Mapping[str, Any], frame_count: int
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": STREAM_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "frame_count": frame_count,
    }
    result = dict(body)
    result["stream_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _frame_header(
    request: Mapping[str, Any],
    *,
    ordinal: int,
    raw: bytes,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": FRAME_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "ordinal": ordinal,
        "size_bytes": len(raw),
        "transport_sha256": hashlib.sha256(raw).hexdigest(),
    }
    result = dict(body)
    result["frame_header_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _response(
    request: Mapping[str, Any],
    *,
    active: int,
    references: int,
    formula_sha256: str,
    payload_sha256: str,
    frame_count: int,
    lie_admission: bool,
) -> dict[str, Any]:
    services = {
        "residue_composer": False,
        "all_character_transform": False,
        "completed_l_consumer": False,
        "typed_bundle_replay": lie_admission,
        "tmajor_adapter_admission": lie_admission,
    }
    body: dict[str, Any] = {
        "schema": RESPONSE_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "status": "completed",
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "payload_stream_sha256": payload_sha256,
        "active_q_count": active,
        "target_row_reference_count": references,
        "target_roster_formula_sha256": formula_sha256,
        "framed_typed_bundle_count": frame_count,
        "worker_services_executed": services,
        "claims": {
            "cuda_execution_attested": False,
            "completed_l_zero_completeness": False,
            "turing_completeness": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    result = dict(body)
    result["response_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _frame_spec(text: str) -> tuple[int, Path]:
    sequence_text, separator, path_text = text.partition(":")
    if not separator or not path_text:
        raise argparse.ArgumentTypeError(
            "bundle frame must have the form SEQUENCE:/absolute/path"
        )
    try:
        sequence = int(sequence_text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "bundle-frame sequence must be an integer"
        ) from error
    path = Path(path_text)
    if sequence < 0 or not path.is_absolute():
        raise argparse.ArgumentTypeError(
            "bundle-frame requires a nonnegative sequence and absolute path"
        )
    return sequence, path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--bundle-frame",
        type=_frame_spec,
        action="append",
        required=True,
        help="repeat SEQUENCE:/absolute/bundle.json in exact target order",
    )
    result.add_argument("--substitute-frame-on-sequence", type=int)
    result.add_argument("--truncate-frame-on-sequence", type=int)
    result.add_argument("--reorder-frame-on-sequence", type=int)
    result.add_argument("--lie-admission-on-sequence", type=int)
    return result


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    frames: dict[int, list[Path]] = {}
    for sequence, path in args.bundle_frame:
        frames.setdefault(sequence, []).append(path)
    handshake = bundle_handshake(Path(__file__).resolve())
    source = sys.stdin.buffer
    output = sys.stdout.buffer
    output.write(canonical_json_bytes(handshake))
    output.flush()
    try:
        while raw_request := source.readline(1024 * 1024 + 1):
            request = _canonical_line(
                raw_request, label="v2 worker request"
            )
            sequence = _integer(
                request.get("sequence_index"),
                "v2 sequence index",
                minimum=0,
            )
            active, references, formula_sha, payload_sha = _validate_request(
                request, source
            )
            paths = frames.get(sequence)
            if paths is None or len(paths) != active:
                _fail(
                    "configured typed-bundle frame count differs from the "
                    "exact active-q roster"
                )
            payloads: list[bytes] = []
            for path in paths:
                raw = path.read_bytes()
                if not raw or len(raw) > MAXIMUM_BUNDLE_BYTES:
                    _fail("configured typed-bundle file size is invalid")
                payloads.append(raw)
            output.write(
                canonical_json_bytes(_stream_header(request, len(payloads)))
            )
            for ordinal, original in enumerate(payloads):
                transmitted = original
                if (
                    sequence == args.substitute_frame_on_sequence
                    and ordinal == 0
                ):
                    transmitted = original[:-1] + bytes(
                        [original[-1] ^ 1]
                    )
                header = _frame_header(
                    request,
                    ordinal=(
                        ordinal + 1
                        if sequence == args.reorder_frame_on_sequence
                        and ordinal == 0
                        else ordinal
                    ),
                    # Bind the honest staged file; substitution is detectable
                    # independently at the supervisor transport boundary.
                    raw=original,
                )
                output.write(canonical_json_bytes(header))
                output.write(FRAME_LENGTH.pack(len(original)))
                if (
                    sequence == args.truncate_frame_on_sequence
                    and ordinal == 0
                ):
                    output.write(transmitted[: len(transmitted) // 2])
                    output.flush()
                    return 7
                output.write(transmitted)
            output.write(
                canonical_json_bytes(
                    _response(
                        request,
                        active=active,
                        references=references,
                        formula_sha256=formula_sha,
                        payload_sha256=payload_sha,
                        frame_count=len(payloads),
                        lie_admission=(
                            sequence == args.lie_admission_on_sequence
                        ),
                    )
                )
            )
            output.flush()
    except (
        DirichletTBlockBundleWorkerError,
        RuntimeError,
        OSError,
        ValueError,
    ) as error:
        print(f"Dirichlet v2 bundle worker error: {error}", file=sys.stderr)
        return 2
    return 0


__all__ = ["bundle_handshake", "run"]
