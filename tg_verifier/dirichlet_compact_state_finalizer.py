# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact ordered cross-lane reduction of fixed-q compact sign-scan state.

The t-block supervisor emits one replayed ``TGDCSB02`` head per active
modulus in each completed lane.  This finalizer authenticates pinned lane
receipts, replays every head binary, and merges adjacent states with
``combine_compact_state_summaries`` -- the same associative boundary rule
used within a lane.  Moduli may retire as height increases, but may never
appear for the first time after lane zero or reappear after retirement.

The output is still sign-scan restart state.  It does not claim refinement,
Turing completeness, a source execution, or the external theorem.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_compact_state_binary import (
    AMBIGUITY_RANGE_RECORD,
    ARTIFACT_HEADER,
    BRACKET_RECORD,
    CHARACTER_RECORD,
    DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    MAXIMUM_ARTIFACT_BYTES,
    DirichletCompactStateBinaryError,
    read_compact_state_binary,
    write_compact_state_binary,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    DirichletStreamConsumerError,
    canonical_json_bytes,
    combine_compact_state_summaries,
    validate_compact_state_summary,
)
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    ALGORITHM_ID as LANE_ALGORITHM_ID,
    ATOM_ID,
    AUTHOR,
    NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION,
    RECEIPT_CLASSIFICATION as LANE_RECEIPT_CLASSIFICATION,
    RECEIPT_SCHEMA as LANE_RECEIPT_SCHEMA,
)


FINALIZER_SCHEMA = (
    "sparkinterval.tg.dirichlet_compact_state_finalizer.receipt.v1"
)
FINALIZER_ALGORITHM_ID = "platt-dirichlet-compact-state-lane-finalizer-v1"
FINALIZER_CLASSIFICATION = (
    "ordered_cross_lane_restart_state_not_zero_or_turing_evidence"
)
MAXIMUM_LANE_COUNT = 64
MAXIMUM_LANE_RECEIPT_BYTES = 64 * 1024 * 1024
DEFAULT_MAXIMUM_TOTAL_OUTPUT_BYTES = 1024 * 1024 * 1024
MAXIMUM_TOTAL_OUTPUT_BYTES = 16 * 1024 * 1024 * 1024
FINAL_STATE_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state-finalizer/state/v1\0"
)


class DirichletCompactStateFinalizerError(RuntimeError):
    """A lane receipt or cross-lane compact-state reduction failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompactStateFinalizerError(message)


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _integer(
    name: str,
    value: object,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        suffix = f"..{maximum}" if maximum is not None else " or larger"
        _fail(f"{name} must be an integer in {minimum}{suffix}")
    return value


def _read_canonical_receipt(path: Path) -> dict[str, Any]:
    try:
        status = path.lstat()
        raw = path.read_bytes()
    except OSError as error:
        raise DirichletCompactStateFinalizerError(
            f"cannot read lane receipt: {error}"
        ) from error
    if (
        not stat.S_ISREG(status.st_mode)
        or path.is_symlink()
        or not 0 < len(raw) <= MAXIMUM_LANE_RECEIPT_BYTES
    ):
        _fail("lane receipt is not one bounded regular file")
    final = path.lstat()
    if (
        final.st_dev != status.st_dev
        or final.st_ino != status.st_ino
        or final.st_size != status.st_size
    ):
        _fail("lane receipt changed during replay")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletCompactStateFinalizerError(
            f"lane receipt is invalid JSON: {error}"
        ) from error
    if (
        not isinstance(value, dict)
        or canonical_json_bytes(value) != raw
    ):
        _fail("lane receipt is not a canonical JSON object")
    body = dict(value)
    claimed = body.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail("lane receipt self-hash differs")
    return value


def _validate_lane_receipt(
    value: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_lane_index: int,
    expected_contract_sha256: str | None,
    previous_t_stop: int | None,
) -> tuple[str, int, int, list[Mapping[str, Any]]]:
    claimed = _digest("lane receipt", value.get("receipt_sha256"))
    if claimed != _digest("expected lane receipt", expected_sha256):
        _fail("lane receipt differs from its external pin")
    if (
        value.get("schema") != LANE_RECEIPT_SCHEMA
        or value.get("schema_version") != 2
        or value.get("author") != AUTHOR
        or value.get("atom_id") != ATOM_ID
        or value.get("algorithm_id") != LANE_ALGORITHM_ID
        or value.get("classification") != LANE_RECEIPT_CLASSIFICATION
        or value.get("worker_classification")
        != NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
        or value.get("complete") is not True
        or value.get("lane_index") != expected_lane_index
    ):
        _fail("lane receipt identity, ordering, or completion differs")
    contract = _digest(
        "lane source contract", value.get("source_contract_sha256")
    )
    if (
        expected_contract_sha256 is not None
        and contract != expected_contract_sha256
    ):
        _fail("lane source contract differs")
    decisions = value.get("decisions")
    required_true = {
        "all_artifact_hashes_computed_by_supervisor",
        "all_typed_bundles_freshly_replayed",
        "all_typed_bundles_admitted_by_existing_tmajor_adapter",
        "streamed_compact_event_resume_integrated",
        "compact_q_state_binary_checkpoint_resume_integrated",
        "compact_q_state_exact_roster_grid_adjacency_validated",
        "exact_ambiguity_ranges_retained",
        "ordered_bracket_records_retained",
    }
    if (
        not isinstance(decisions, dict)
        or any(decisions.get(key) is not True for key in required_true)
        or decisions.get("refinement_artifacts_complete") is not False
        or decisions.get("turing_completeness_claimed") is not False
        or decisions.get("external_atom_discharged") is not False
    ):
        _fail("lane compact-state decision boundary differs")
    adapter = value.get("adapter_lane_receipt")
    if not isinstance(adapter, dict):
        _fail("lane adapter receipt is absent")
    adapter_body = dict(adapter)
    adapter_claimed = adapter_body.pop("receipt_sha256", None)
    if (
        adapter_claimed
        != hashlib.sha256(canonical_json_bytes(adapter_body)).hexdigest()
        or adapter.get("lane_index") != expected_lane_index
        or adapter.get("source_contract_sha256") != contract
    ):
        _fail("lane adapter receipt binding differs")
    assignment = adapter.get("assignment")
    if not isinstance(assignment, dict):
        _fail("lane assignment is absent")
    t_start = _integer(
        "lane t start", assignment.get("t_index_start_inclusive")
    )
    t_stop = _integer(
        "lane t stop",
        assignment.get("t_index_stop_exclusive"),
        minimum=t_start + 1,
    )
    if (
        assignment.get("lane_index") != expected_lane_index
        or (expected_lane_index == 0 and t_start != 0)
        or (previous_t_stop is not None and t_start != previous_t_stop)
    ):
        _fail("lane assignment has a gap, overlap, or reorder")
    heads = value.get("compact_state_heads")
    if (
        not isinstance(heads, list)
        or value.get("compact_state_q_count") != len(heads)
    ):
        _fail("lane compact-state head count differs")
    return contract, t_start, t_stop, heads


def _validate_head_shape(
    head: Mapping[str, Any],
    *,
    previous_q: int | None,
) -> int:
    required = {
        "q",
        "state_sha256",
        "first_t_numerator",
        "stop_t_numerator",
        "primitive_character_count",
        "leaf_event_summary_count",
        "sign_change_lower_bound",
        "ambiguity_sample_count",
        "state_after_binary",
        "exact_ambiguity_ranges_retained",
        "ordered_bracket_records_retained",
        "turing_completeness",
        "external_atom_discharged",
    }
    q = _integer("lane head q", head.get("q"), minimum=1)
    if (
        set(head) != required
        or (previous_q is not None and q <= previous_q)
        or head.get("exact_ambiguity_ranges_retained") is not True
        or head.get("ordered_bracket_records_retained") is not True
        or head.get("turing_completeness") is not False
        or head.get("external_atom_discharged") is not False
        or not isinstance(head.get("state_after_binary"), dict)
    ):
        _fail("lane compact-state heads are malformed or reordered")
    _digest("lane head state", head.get("state_sha256"))
    for field in (
        "first_t_numerator",
        "stop_t_numerator",
        "primitive_character_count",
        "leaf_event_summary_count",
        "sign_change_lower_bound",
        "ambiguity_sample_count",
    ):
        _integer(f"lane head {field}", head.get(field))
    if head["stop_t_numerator"] < head["first_t_numerator"]:
        _fail("lane compact-state head grid is reversed")
    return q


def _binary_size(state: Mapping[str, Any]) -> int:
    ranges = sum(
        len(character["ambiguity_ranges"])
        for character in state["character_states"]
    )
    brackets = sum(
        len(character["bracket_records"])
        for character in state["character_states"]
    )
    return (
        ARTIFACT_HEADER.size
        + len(state["character_states"]) * CHARACTER_RECORD.size
        + ranges * AMBIGUITY_RANGE_RECORD.size
        + brackets * BRACKET_RECORD.size
    )


def finalize_compact_state_lanes(
    output_receipt_path: Path,
    output_state_directory: Path,
    *,
    lane_receipt_paths: Sequence[Path],
    expected_lane_receipt_sha256s: Sequence[str],
    expected_lane_count: int,
    expected_t_index_stop_exclusive: int,
    expected_source_contract_sha256: str | None = None,
    maximum_binary_bytes_per_q: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_total_output_bytes: int = DEFAULT_MAXIMUM_TOTAL_OUTPUT_BYTES,
) -> dict[str, Any]:
    """Replay and exactly merge a complete, externally pinned lane sequence."""

    expected_lane_count = _integer(
        "expected lane count",
        expected_lane_count,
        minimum=1,
        maximum=MAXIMUM_LANE_COUNT,
    )
    expected_t_index_stop_exclusive = _integer(
        "expected final t stop",
        expected_t_index_stop_exclusive,
        minimum=1,
    )
    if (
        len(lane_receipt_paths) != expected_lane_count
        or len(expected_lane_receipt_sha256s) != len(lane_receipt_paths)
    ):
        _fail("lane receipt roster is incomplete or count-mismatched")
    maximum_binary_bytes_per_q = _integer(
        "maximum binary bytes per q",
        maximum_binary_bytes_per_q,
        minimum=1,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    maximum_total_output_bytes = _integer(
        "maximum total output bytes",
        maximum_total_output_bytes,
        minimum=1,
        maximum=MAXIMUM_TOTAL_OUTPUT_BYTES,
    )
    if output_receipt_path.exists():
        _fail("compact-state finalizer receipt already exists")
    output_state_directory.mkdir(parents=True, exist_ok=True)

    merged: dict[int, dict[str, Any]] = {}
    prior_active_q: set[int] | None = None
    contract: str | None = (
        _digest(
            "expected source contract", expected_source_contract_sha256
        )
        if expected_source_contract_sha256 is not None
        else None
    )
    previous_t_stop: int | None = None
    lane_receipt_hashes: list[str] = []
    cross_lane_inserted = 0
    for lane_index, (path, expected_sha256) in enumerate(
        zip(lane_receipt_paths, expected_lane_receipt_sha256s)
    ):
        receipt = _read_canonical_receipt(path)
        observed_contract, t_start, t_stop, heads = _validate_lane_receipt(
            receipt,
            expected_sha256=expected_sha256,
            expected_lane_index=lane_index,
            expected_contract_sha256=contract,
            previous_t_stop=previous_t_stop,
        )
        if contract is None:
            contract = observed_contract
        current_q: set[int] = set()
        previous_q: int | None = None
        replayed_heads: dict[int, dict[str, Any]] = {}
        for raw_head in heads:
            if not isinstance(raw_head, dict):
                _fail("lane compact-state head is not an object")
            q = _validate_head_shape(raw_head, previous_q=previous_q)
            previous_q = q
            current_q.add(q)
            record = raw_head["state_after_binary"]
            try:
                state = read_compact_state_binary(
                    Path(record["path"]),
                    expected_record=record,
                    maximum_bytes=maximum_binary_bytes_per_q,
                )
            except (KeyError, DirichletCompactStateBinaryError) as error:
                raise DirichletCompactStateFinalizerError(
                    f"lane compact-state binary replay failed: {error}"
                ) from error
            context = state["context"]
            if (
                state["state_sha256"] != raw_head["state_sha256"]
                or context["q"] != q
                or context["first_t_numerator"]
                != raw_head["first_t_numerator"]
                or context["stop_t_numerator"]
                != raw_head["stop_t_numerator"]
                or context["primitive_character_count"]
                != raw_head["primitive_character_count"]
                or state["leaf_event_summary_count"]
                != raw_head["leaf_event_summary_count"]
                or state["sign_change_lower_bound"]
                != raw_head["sign_change_lower_bound"]
                or state["ambiguity_sample_count"]
                != raw_head["ambiguity_sample_count"]
                or context["first_t_numerator"] != 5 * t_start
                or context["stop_t_numerator"] > 5 * t_stop
            ):
                _fail("lane compact-state head differs from binary semantics")
            replayed_heads[q] = state
        if prior_active_q is not None and not current_q <= prior_active_q:
            _fail("a modulus appears for the first time or reappears after retirement")
        for q in sorted(current_q):
            state = replayed_heads[q]
            before = merged.get(q)
            if before is None:
                if lane_index != 0:
                    _fail("a modulus has no lane-zero compact-state prefix")
                merged[q] = state
                continue
            before_signs = before["sign_change_lower_bound"]
            leaf_signs = state["sign_change_lower_bound"]
            try:
                after = combine_compact_state_summaries(before, state)
            except DirichletStreamConsumerError as error:
                raise DirichletCompactStateFinalizerError(
                    f"cross-lane q-state merge failed: {error}"
                ) from error
            inserted = (
                after["sign_change_lower_bound"]
                - before_signs
                - leaf_signs
            )
            if inserted < 0:
                _fail("cross-lane merge lost a sign-change lower bound")
            cross_lane_inserted += inserted
            merged[q] = after
        prior_active_q = current_q
        previous_t_stop = t_stop
        lane_receipt_hashes.append(receipt["receipt_sha256"])
    assert contract is not None
    if previous_t_stop != expected_t_index_stop_exclusive:
        _fail("lane receipts do not reach the externally pinned final t stop")

    projected_total = sum(_binary_size(state) for state in merged.values())
    if projected_total > maximum_total_output_bytes:
        _fail("final compact-state binaries exceed the total output byte bound")
    final_heads: list[dict[str, Any]] = []
    state_chain = hashlib.sha256(FINAL_STATE_CHAIN_DOMAIN)
    state_chain.update(bytes.fromhex(contract))
    for receipt_sha256 in lane_receipt_hashes:
        state_chain.update(bytes.fromhex(receipt_sha256))
    written_total = 0
    for q, state in sorted(merged.items()):
        validate_compact_state_summary(state)
        path = output_state_directory / f"q-{q:06d}.bin"
        try:
            record = write_compact_state_binary(
                path,
                state,
                maximum_bytes=maximum_binary_bytes_per_q,
            )
            replayed = read_compact_state_binary(
                path,
                expected_record=record,
                maximum_bytes=maximum_binary_bytes_per_q,
            )
        except DirichletCompactStateBinaryError as error:
            raise DirichletCompactStateFinalizerError(
                f"final compact-state binary replay failed: {error}"
            ) from error
        if replayed != state:
            _fail("final compact-state binary semantic replay differs")
        written_total += record["size_bytes"]
        if written_total > maximum_total_output_bytes:
            _fail("final compact-state output byte counter overflowed its bound")
        state_chain.update(bytes.fromhex(record["record_sha256"]))
        final_heads.append(
            {
                "q": q,
                "state_sha256": state["state_sha256"],
                "first_t_numerator": state["context"][
                    "first_t_numerator"
                ],
                "stop_t_numerator": state["context"]["stop_t_numerator"],
                "primitive_character_count": state["context"][
                    "primitive_character_count"
                ],
                "leaf_event_summary_count": state[
                    "leaf_event_summary_count"
                ],
                "sign_change_lower_bound": state[
                    "sign_change_lower_bound"
                ],
                "ambiguity_sample_count": state["ambiguity_sample_count"],
                "state_binary": record,
            }
        )
    body: dict[str, Any] = {
        "schema": FINALIZER_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": FINALIZER_ALGORITHM_ID,
        "classification": FINALIZER_CLASSIFICATION,
        "source_contract_sha256": contract,
        "lane_count": len(lane_receipt_hashes),
        "expected_t_index_stop_exclusive": (
            expected_t_index_stop_exclusive
        ),
        "lane_receipt_sha256s": lane_receipt_hashes,
        "q_state_count": len(final_heads),
        "q_state_heads": final_heads,
        "state_chain_sha256": state_chain.hexdigest(),
        "cross_lane_sign_changes_inserted": cross_lane_inserted,
        "maximum_binary_bytes_per_q": maximum_binary_bytes_per_q,
        "maximum_total_output_bytes": maximum_total_output_bytes,
        "output_state_bytes": written_total,
        "decisions": {
            "lane_order_and_contiguous_assignments_validated": True,
            "q_rosters_sorted_and_retirement_monotone": True,
            "all_lane_head_binaries_freshly_replayed": True,
            "same_associative_boundary_rule_used_within_and_across_lanes": True,
            "final_q_state_binaries_freshly_replayed": True,
            "exact_ambiguity_ranges_retained": True,
            "ordered_bracket_records_retained": True,
            "refinement_artifacts_complete": False,
            "turing_completeness": False,
            "source_scale_state_encoding": False,
            "source_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    result = dict(body)
    result["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    temporary = output_receipt_path.with_name(
        output_receipt_path.name + ".tmp"
    )
    output_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(canonical_json_bytes(result))
    temporary.replace(output_receipt_path)
    return result


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": FINALIZER_ALGORITHM_ID,
        "canonical_lane_order_required": True,
        "exact_lane_assignment_adjacency_required": True,
        "q_reappearance_rejected": True,
        "same_associative_boundary_rule_as_tblock_reducer": True,
        "binary_gap_overlap_reorder_and_overflow_rejected": True,
        "maximum_lane_count": MAXIMUM_LANE_COUNT,
        "maximum_lane_receipt_bytes": MAXIMUM_LANE_RECEIPT_BYTES,
        "maximum_binary_bytes_per_q": MAXIMUM_ARTIFACT_BYTES,
        "maximum_total_output_bytes": MAXIMUM_TOTAL_OUTPUT_BYTES,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "turing_completeness": False,
        "source_scale_state_encoding": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "DEFAULT_MAXIMUM_TOTAL_OUTPUT_BYTES",
    "DirichletCompactStateFinalizerError",
    "FINALIZER_ALGORITHM_ID",
    "FINALIZER_CLASSIFICATION",
    "FINALIZER_SCHEMA",
    "MAXIMUM_LANE_COUNT",
    "MAXIMUM_LANE_RECEIPT_BYTES",
    "MAXIMUM_TOTAL_OUTPUT_BYTES",
    "capability",
    "finalize_compact_state_lanes",
]
