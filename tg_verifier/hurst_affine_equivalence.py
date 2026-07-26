# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded equivalence qualification for the Hurst affine optimization.

The reviewed C++ adapter exposes three modes over the same segmented Möbius
rows:

* ``summary`` computes the exact additive transition;
* ``verify`` replays the rows from one supplied incoming state; and
* ``affine`` computes the set of incoming states accepted by that replay.

This module runs all three modes over one ordered bounded range and retains
their exact stdout bytes.  Independent verification requires:

* identical mode-independent output fields, row commitments, and deltas;
* identical output on every repeated execution after removing timing only;
* one root state in the intersection of all translated affine guards;
* exact agreement of every derived incoming/outgoing state and final state;
* accepted singleton verification at those exact incoming states; and
* exact recomputation of the reported arithmetic and process timing medians.

This is deliberately a qualification artifact, not source-scale evidence.
It does not prove that the executable implements primitive Möbius rows, prove
compiler correctness, attest execution, or discharge a Lean atom.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import os
from pathlib import Path
import threading
import time
from typing import Any, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    canonical_sha256,
    hash_file_once,
    load_json,
    sha256_bytes,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .hurst_affine_campaign import (
    ATOM_PROFILES,
    HurstAffineCampaignError,
    SOURCE_UPPER_EXCLUSIVE,
    UPSTREAM_COMMIT,
    validate_affine_runner_receipt,
)
from .hurst_residual_campaign import (
    MAX_RECEIPT_BYTES,
    MAX_RUNNER_BYTES,
    MAX_SEGMENT_SIZE,
    MAX_SOURCE_BYTES,
    MIN_SEGMENT_SIZE,
    RUNNER_ALGORITHM,
    _execute_shard,
    _validate_upstream_manifest,
    validate_runner_receipt,
)


SCHEMA = "sparkinterval.tg.hurst-affine-equivalence-qualification.v1"
ALGORITHM = "hurst-affine-versus-two-pass-bounded-equivalence-v1"
CLASSIFICATION = (
    "bounded_cross_mode_qualification_not_source_evidence_attestation_or_lean_proof"
)

_TOP_FIELDS = frozenset(
    {
        "schema",
        "algorithm",
        "classification",
        "runner_algorithm",
        "upstream_commit",
        "identity",
        "configuration",
        "runs",
        "chain",
        "timing",
        "checks",
        "capabilities",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "runner_sha256",
        "runner_size_bytes",
        "source_sha256",
        "source_size_bytes",
        "upstream_manifest_sha256",
        "upstream_manifest_size_bytes",
    }
)
_CONFIG_FIELDS = frozenset(
    {
        "domain_lower",
        "domain_upper_exclusive",
        "shard_span",
        "shard_count",
        "segment_size",
        "repeat_count",
        "runner_threads",
        "root_selection",
        "root_state",
    }
)
_RUN_FIELDS = frozenset({"repeat_index", "mode_order", "summary", "verify", "affine"})
_RECORD_FIELDS = frozenset(
    {
        "index",
        "lower",
        "upper_exclusive",
        "receipt_sha256",
        "receipt_size_bytes",
        "receipt_hex",
        "report",
        "process_wall_seconds_decimal",
    }
)
_CHAIN_FIELDS = frozenset(
    {
        "root_state",
        "global_root_lower_guard",
        "global_root_upper_guard",
        "entries",
        "final_state",
    }
)
_CHAIN_ENTRY_FIELDS = frozenset(
    {
        "index",
        "lower",
        "upper_exclusive",
        "incoming",
        "delta",
        "outgoing",
        "row_sha256",
    }
)
_TIMING_FIELDS = frozenset(
    {
        "runner_elapsed_seconds",
        "process_wall_seconds",
        "runner_elapsed_two_pass_over_affine",
        "process_wall_two_pass_over_affine",
        "representative_one_pass_faster_by_runner_elapsed",
        "representative_one_pass_faster_by_process_wall",
        "scope",
    }
)
_MODE_TIMING_FIELDS = frozenset(
    {"summary_median", "verify_median", "affine_median", "two_pass_median"}
)
_CHECK_FIELDS = frozenset(
    {
        "raw_receipts_bound",
        "repeat_outputs_equal_ignoring_timing",
        "mode_independent_outputs_equal",
        "all_affine_guards_accept_derived_inputs",
        "verify_singletons_equal_derived_inputs",
        "terminal_states_equal",
        "gap_free_ordered_coverage",
    }
)
_CAPABILITY_FIELDS = frozenset(
    {
        "bounded_qualification_complete",
        "full_source_range",
        "source_rows_replayed_independently",
        "primitive_mobius_realization_proved",
        "runner_source_compilation_proved",
        "execution_attested",
        "lean_atom_discharged",
        "source_scale_speedup_claimed",
    }
)
_MODE_INDEPENDENT_FIELDS = (
    "algorithm",
    "classification",
    "upstream_commit",
    "lower",
    "upper_exclusive",
    "work_count",
    "segment_size",
    "segments",
    "row_encoding",
    "squarefree_threshold_endpoint_policy",
    "reduction_block_rows",
    "row_sha256",
    "state_components",
    "delta",
    "accepted",
    "execution_attested",
    "lean_atom_discharged",
)
_MODE_ORDERS = (
    ("affine", "summary", "verify"),
    ("summary", "verify", "affine"),
    ("verify", "affine", "summary"),
)


class HurstAffineEquivalenceError(RuntimeError):
    """A bounded cross-mode qualification failed closed."""


def _plain_int(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HurstAffineEquivalenceError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise HurstAffineEquivalenceError(f"{name} must be at least {minimum}")
    return value


def _state(value: object, name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise HurstAffineEquivalenceError(f"{name} must be a four-integer array")
    result = tuple(_plain_int(item, f"{name}[{index}]") for index, item in enumerate(value))
    return result  # type: ignore[return-value]


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise HurstAffineEquivalenceError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise HurstAffineEquivalenceError(f"{name} is not decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise HurstAffineEquivalenceError(f"{name} must be finite and nonnegative")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise HurstAffineEquivalenceError("timing value must be finite and nonnegative")
    return format(value, "f")


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise HurstAffineEquivalenceError("cannot take the median of no timings")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _ratio(numerator: Decimal, denominator: Decimal, name: str) -> Decimal:
    if denominator <= 0:
        raise HurstAffineEquivalenceError(f"{name} denominator must be positive")
    with localcontext() as context:
        context.prec = 28
        return numerator / denominator


def _ranges(
    lower: int, upper_exclusive: int, shard_span: int
) -> tuple[tuple[int, int], ...]:
    start = _plain_int(lower, "domain lower", minimum=1)
    stop = _plain_int(upper_exclusive, "domain upper exclusive", minimum=2)
    span = _plain_int(shard_span, "shard span", minimum=1)
    if start >= stop:
        raise HurstAffineEquivalenceError("qualification range is empty")
    if stop > SOURCE_UPPER_EXCLUSIVE:
        raise HurstAffineEquivalenceError("qualification exceeds the source endpoint")
    if start == 1 and stop == SOURCE_UPPER_EXCLUSIVE:
        raise HurstAffineEquivalenceError(
            "bounded qualification refuses the literal full-source campaign"
        )
    result: list[tuple[int, int]] = []
    cursor = start
    while cursor < stop:
        following = min(cursor + span, stop)
        result.append((cursor, following))
        cursor = following
    return tuple(result)


def _wire_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    elapsed = value.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, Decimal)):
        raise HurstAffineEquivalenceError("receipt elapsed_seconds is malformed")
    value["elapsed_seconds"] = _decimal_text(Decimal(elapsed))
    return value


def _semantic_without_elapsed(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    value.pop("elapsed_seconds", None)
    return value


def _command(
    runner: Path,
    *,
    mode: str,
    lower: int,
    upper_exclusive: int,
    segment_size: int,
    incoming: Sequence[int] | None,
) -> tuple[str, ...]:
    command = [
        str(runner.resolve()),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper_exclusive - 1),
        "--segment-size",
        str(segment_size),
    ]
    if mode == "verify":
        if incoming is None:
            raise HurstAffineEquivalenceError("verify mode needs an incoming state")
        for flag, coordinate in zip(
            (
                "--incoming-mertens",
                "--incoming-squarefree",
                "--incoming-little-lower",
                "--incoming-little-upper",
            ),
            incoming,
            strict=True,
        ):
            command.extend((flag, str(coordinate)))
    elif incoming is not None:
        raise HurstAffineEquivalenceError("only verify mode accepts an incoming state")
    return tuple(command)


def _run_record(
    runner: Path,
    *,
    index: int,
    mode: str,
    lower: int,
    upper_exclusive: int,
    segment_size: int,
    incoming: Sequence[int] | None,
    runner_threads: int,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    command = _command(
        runner,
        mode=mode,
        lower=lower,
        upper_exclusive=upper_exclusive,
        segment_size=segment_size,
        incoming=incoming,
    )
    started = time.monotonic_ns()
    try:
        raw = _execute_shard(
            command,
            timeout_seconds=timeout_seconds,
            runner_threads=runner_threads,
            runner_places=None,
            cancel_event=threading.Event(),
        )
    except Exception as exc:
        raise HurstAffineEquivalenceError(
            f"{mode} shard {index} execution failed: {exc}"
        ) from exc
    wall = Decimal(time.monotonic_ns() - started) / Decimal(1_000_000_000)
    try:
        report = load_decimal_json_bytes(raw, label=f"{mode} shard {index}")
    except EvidenceError as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc
    if mode == "affine":
        validate_affine_runner_receipt(
            report,
            shard_lower=lower,
            shard_upper=upper_exclusive,
            segment_size=segment_size,
        )
    else:
        validate_runner_receipt(
            report,
            phase=mode,
            shard_lower=lower,
            shard_upper=upper_exclusive,
            segment_size=segment_size,
            expected_incoming=incoming,
        )
    return {
        "index": index,
        "lower": lower,
        "upper_exclusive": upper_exclusive,
        "receipt_sha256": sha256_bytes(raw),
        "receipt_size_bytes": len(raw),
        "receipt_hex": raw.hex(),
        "report": _wire_report(report),
        "process_wall_seconds_decimal": _decimal_text(wall),
    }


def _decode_record(
    value: object,
    *,
    expected_index: int,
    expected_range: tuple[int, int],
    mode: str,
    segment_size: int,
    incoming: Sequence[int] | None,
) -> tuple[dict[str, Any], Decimal]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise HurstAffineEquivalenceError(f"{mode} record fields changed")
    lower, upper = expected_range
    if (
        value.get("index"),
        value.get("lower"),
        value.get("upper_exclusive"),
    ) != (expected_index, lower, upper):
        raise HurstAffineEquivalenceError(
            f"{mode} record order/range changed at index {expected_index}"
        )
    size = _plain_int(value.get("receipt_size_bytes"), "receipt size", minimum=1)
    if size > MAX_RECEIPT_BYTES:
        raise HurstAffineEquivalenceError("receipt exceeds its byte limit")
    raw_hex = value.get("receipt_hex")
    if not isinstance(raw_hex, str) or len(raw_hex) != 2 * size:
        raise HurstAffineEquivalenceError("receipt hex length changed")
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise HurstAffineEquivalenceError("receipt hex is malformed") from exc
    digest = value.get("receipt_sha256")
    if not isinstance(digest, str) or sha256_bytes(raw) != digest:
        raise HurstAffineEquivalenceError("receipt SHA-256 differs from retained bytes")
    try:
        report = load_decimal_json_bytes(raw, label=f"{mode} record {expected_index}")
    except EvidenceError as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc
    if value.get("report") != _wire_report(report):
        raise HurstAffineEquivalenceError("readable report differs from retained bytes")
    try:
        if mode == "affine":
            validate_affine_runner_receipt(
                report,
                shard_lower=lower,
                shard_upper=upper,
                segment_size=segment_size,
            )
        else:
            validate_runner_receipt(
                report,
                phase=mode,
                shard_lower=lower,
                shard_upper=upper,
                segment_size=segment_size,
                expected_incoming=incoming,
            )
    except (HurstAffineCampaignError, RuntimeError) as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc
    wall = _decimal(
        value.get("process_wall_seconds_decimal"), "process wall seconds"
    )
    return report, wall


def _guard_bounds(
    report: Mapping[str, Any], atom: str
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    guards = report.get("guards")
    if not isinstance(guards, Mapping):
        raise HurstAffineEquivalenceError("affine guards are malformed")
    guard = guards.get(atom)
    if not isinstance(guard, Mapping):
        raise HurstAffineEquivalenceError(f"missing affine guard {atom}")
    return (
        _state(guard.get("lower"), f"{atom} lower"),
        _state(guard.get("upper"), f"{atom} upper"),
    )


def _translated_global_guard(
    affine_reports: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    prefix = (0, 0, 0, 0)
    lower: list[int | None] = [None, None, None, None]
    upper: list[int | None] = [None, None, None, None]
    for report in affine_reports:
        for atom in ATOM_PROFILES:
            atom_lower, atom_upper = _guard_bounds(report, atom)
            for coordinate in range(4):
                translated_lower = atom_lower[coordinate] - prefix[coordinate]
                translated_upper = atom_upper[coordinate] - prefix[coordinate]
                if lower[coordinate] is None or translated_lower > lower[coordinate]:
                    lower[coordinate] = translated_lower
                if upper[coordinate] is None or translated_upper < upper[coordinate]:
                    upper[coordinate] = translated_upper
        delta = _state(report.get("delta"), "affine delta")
        prefix = tuple(
            left + right for left, right in zip(prefix, delta, strict=True)
        )
    if any(item is None for item in lower + upper):
        raise HurstAffineEquivalenceError("global affine guard is empty")
    checked_lower = tuple(int(item) for item in lower)
    checked_upper = tuple(int(item) for item in upper)
    if any(lo > hi for lo, hi in zip(checked_lower, checked_upper, strict=True)):
        raise HurstAffineEquivalenceError(
            "translated affine guards have empty global intersection"
        )
    return checked_lower, checked_upper  # type: ignore[return-value]


def _choose_root(
    lower: Sequence[int],
    upper: Sequence[int],
    requested: Sequence[int] | None,
) -> tuple[tuple[int, int, int, int], str]:
    if requested is not None:
        root = tuple(requested)
        if len(root) != 4 or any(isinstance(item, bool) or not isinstance(item, int) for item in root):
            raise HurstAffineEquivalenceError("requested root must have four integers")
        selection = "explicit"
    else:
        root = tuple(
            lo if 0 < lo else hi if 0 > hi else 0
            for lo, hi in zip(lower, upper, strict=True)
        )
        selection = "canonical_zero_clamped_to_translated_guard_intersection"
    if any(
        value < lo or value > hi
        for value, lo, hi in zip(root, lower, upper, strict=True)
    ):
        raise HurstAffineEquivalenceError(
            "requested root is outside the translated affine guard intersection"
        )
    return root, selection  # type: ignore[return-value]


def _chain(
    ranges: Sequence[tuple[int, int]],
    root: Sequence[int],
    affine_reports: Sequence[Mapping[str, Any]],
    global_lower: Sequence[int],
    global_upper: Sequence[int],
) -> dict[str, Any]:
    current = tuple(root)
    entries: list[dict[str, Any]] = []
    for index, ((lower, upper), report) in enumerate(zip(ranges, affine_reports, strict=True)):
        for atom in ATOM_PROFILES:
            atom_lower, atom_upper = _guard_bounds(report, atom)
            if any(
                value < lo or value > hi
                for value, lo, hi in zip(current, atom_lower, atom_upper, strict=True)
            ):
                raise HurstAffineEquivalenceError(
                    f"derived incoming state violates {atom} guard at shard {index}"
                )
        delta = _state(report.get("delta"), "affine delta")
        outgoing = tuple(
            left + right for left, right in zip(current, delta, strict=True)
        )
        entries.append(
            {
                "index": index,
                "lower": lower,
                "upper_exclusive": upper,
                "incoming": list(current),
                "delta": list(delta),
                "outgoing": list(outgoing),
                "row_sha256": report["row_sha256"],
            }
        )
        current = outgoing
    return {
        "root_state": list(root),
        "global_root_lower_guard": list(global_lower),
        "global_root_upper_guard": list(global_upper),
        "entries": entries,
        "final_state": list(current),
    }


def _same_mode_outputs(
    reports: Sequence[Sequence[Mapping[str, Any]]], mode: str
) -> None:
    baseline = [_semantic_without_elapsed(report) for report in reports[0]]
    for repeat_index, current in enumerate(reports[1:], start=1):
        candidate = [_semantic_without_elapsed(report) for report in current]
        if candidate != baseline:
            raise HurstAffineEquivalenceError(
                f"{mode} output changed at repeat {repeat_index}"
            )


def _same_cross_mode_outputs(
    summary: Sequence[Mapping[str, Any]],
    verify: Sequence[Mapping[str, Any]],
    affine: Sequence[Mapping[str, Any]],
) -> None:
    for index, reports in enumerate(zip(summary, verify, affine, strict=True)):
        projected = [
            {field: report[field] for field in _MODE_INDEPENDENT_FIELDS}
            for report in reports
        ]
        if projected[0] != projected[1] or projected[0] != projected[2]:
            raise HurstAffineEquivalenceError(
                f"mode-independent output differs at shard {index}"
            )


def _timing_payload(
    decoded_runs: Sequence[
        Mapping[str, tuple[Sequence[Mapping[str, Any]], Sequence[Decimal]]]
    ],
) -> dict[str, Any]:
    elapsed: dict[str, list[Decimal]] = {mode: [] for mode in ("summary", "verify", "affine")}
    wall: dict[str, list[Decimal]] = {mode: [] for mode in ("summary", "verify", "affine")}
    for run in decoded_runs:
        for mode in elapsed:
            reports, walls = run[mode]
            elapsed[mode].append(
                sum((Decimal(report["elapsed_seconds"]) for report in reports), Decimal(0))
            )
            wall[mode].append(sum(walls, Decimal(0)))

    def family(values: Mapping[str, Sequence[Decimal]]) -> tuple[dict[str, str], Decimal]:
        summary = _median(values["summary"])
        verify = _median(values["verify"])
        affine = _median(values["affine"])
        two_pass = summary + verify
        return (
            {
                "summary_median": _decimal_text(summary),
                "verify_median": _decimal_text(verify),
                "affine_median": _decimal_text(affine),
                "two_pass_median": _decimal_text(two_pass),
            },
            _ratio(two_pass, affine, "two-pass/affine timing"),
        )

    elapsed_family, elapsed_ratio = family(elapsed)
    wall_family, wall_ratio = family(wall)
    return {
        "runner_elapsed_seconds": elapsed_family,
        "process_wall_seconds": wall_family,
        "runner_elapsed_two_pass_over_affine": _decimal_text(elapsed_ratio),
        "process_wall_two_pass_over_affine": _decimal_text(wall_ratio),
        "representative_one_pass_faster_by_runner_elapsed": elapsed_ratio > 1,
        "representative_one_pass_faster_by_process_wall": wall_ratio > 1,
        "scope": (
            "bounded_same_binary_same_ranges_not_full_source_eta_or_cloud_cost_model"
        ),
    }


def _decode_and_check(
    artifact: Mapping[str, Any],
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
) -> dict[str, Any]:
    if set(artifact) != _TOP_FIELDS:
        raise HurstAffineEquivalenceError("qualification fields changed")
    if (
        artifact.get("schema"),
        artifact.get("algorithm"),
        artifact.get("classification"),
        artifact.get("runner_algorithm"),
        artifact.get("upstream_commit"),
    ) != (SCHEMA, ALGORITHM, CLASSIFICATION, RUNNER_ALGORITHM, UPSTREAM_COMMIT):
        raise HurstAffineEquivalenceError("qualification identity changed")

    identity = artifact.get("identity")
    if not isinstance(identity, dict) or set(identity) != _IDENTITY_FIELDS:
        raise HurstAffineEquivalenceError("qualification file identity fields changed")
    for path, digest_name, size_name, maximum in (
        (runner, "runner_sha256", "runner_size_bytes", MAX_RUNNER_BYTES),
        (runner_source, "source_sha256", "source_size_bytes", MAX_SOURCE_BYTES),
        (
            upstream_manifest,
            "upstream_manifest_sha256",
            "upstream_manifest_size_bytes",
            MAX_SOURCE_BYTES,
        ),
    ):
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise HurstAffineEquivalenceError(str(exc)) from exc
        if (identity.get(digest_name), identity.get(size_name)) != (digest, size):
            raise HurstAffineEquivalenceError(f"captured identity changed: {path}")
    try:
        upstream = upstream_manifest.read_bytes()
        _validate_upstream_manifest(upstream)
    except (OSError, RuntimeError) as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc

    config = artifact.get("configuration")
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise HurstAffineEquivalenceError("qualification configuration fields changed")
    lower = _plain_int(config.get("domain_lower"), "domain lower", minimum=1)
    upper = _plain_int(
        config.get("domain_upper_exclusive"), "domain upper exclusive", minimum=2
    )
    span = _plain_int(config.get("shard_span"), "shard span", minimum=1)
    ranges = _ranges(lower, upper, span)
    if config.get("shard_count") != len(ranges):
        raise HurstAffineEquivalenceError("qualification shard count changed")
    segment_size = _plain_int(config.get("segment_size"), "segment size", minimum=MIN_SEGMENT_SIZE)
    if segment_size > MAX_SEGMENT_SIZE:
        raise HurstAffineEquivalenceError("qualification segment size exceeds runner limit")
    repeat_count = _plain_int(config.get("repeat_count"), "repeat count", minimum=1)
    _plain_int(config.get("runner_threads"), "runner threads", minimum=1)
    root = _state(config.get("root_state"), "root state")
    selection = config.get("root_selection")
    if selection not in (
        "explicit",
        "canonical_zero_clamped_to_translated_guard_intersection",
    ):
        raise HurstAffineEquivalenceError("unknown root selection")

    runs = artifact.get("runs")
    if not isinstance(runs, list) or len(runs) != repeat_count:
        raise HurstAffineEquivalenceError("qualification repeats are missing")
    decoded: list[
        dict[str, tuple[list[dict[str, Any]], list[Decimal]]]
    ] = []
    expected_incoming: list[tuple[int, int, int, int]] | None = None
    for repeat_index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != _RUN_FIELDS:
            raise HurstAffineEquivalenceError("qualification run fields changed")
        if run.get("repeat_index") != repeat_index:
            raise HurstAffineEquivalenceError("qualification repeat order changed")
        mode_order = run.get("mode_order")
        if mode_order != list(_MODE_ORDERS[repeat_index % len(_MODE_ORDERS)]):
            raise HurstAffineEquivalenceError("qualification mode order changed")
        current: dict[str, tuple[list[dict[str, Any]], list[Decimal]]] = {}
        for mode in ("summary", "affine"):
            records = run.get(mode)
            if not isinstance(records, list) or len(records) != len(ranges):
                raise HurstAffineEquivalenceError(f"{mode} records are incomplete")
            reports: list[dict[str, Any]] = []
            walls: list[Decimal] = []
            for index, (record, bounds) in enumerate(zip(records, ranges, strict=True)):
                report, wall_time = _decode_record(
                    record,
                    expected_index=index,
                    expected_range=bounds,
                    mode=mode,
                    segment_size=segment_size,
                    incoming=None,
                )
                reports.append(report)
                walls.append(wall_time)
            current[mode] = (reports, walls)
        if repeat_index == 0:
            global_lower, global_upper = _translated_global_guard(current["affine"][0])
            expected_root, expected_selection = _choose_root(
                global_lower,
                global_upper,
                root if selection == "explicit" else None,
            )
            if root != expected_root or selection != expected_selection:
                raise HurstAffineEquivalenceError(
                    "configured root selection differs from affine guards"
                )
            expected_chain = _chain(
                ranges,
                root,
                current["affine"][0],
                global_lower,
                global_upper,
            )
            expected_incoming = [
                _state(entry["incoming"], "chain incoming")
                for entry in expected_chain["entries"]
            ]
        assert expected_incoming is not None
        records = run.get("verify")
        if not isinstance(records, list) or len(records) != len(ranges):
            raise HurstAffineEquivalenceError("verify records are incomplete")
        verify_reports: list[dict[str, Any]] = []
        verify_walls: list[Decimal] = []
        for index, (record, bounds, incoming) in enumerate(
            zip(records, ranges, expected_incoming, strict=True)
        ):
            report, wall_time = _decode_record(
                record,
                expected_index=index,
                expected_range=bounds,
                mode="verify",
                segment_size=segment_size,
                incoming=incoming,
            )
            verify_reports.append(report)
            verify_walls.append(wall_time)
        current["verify"] = (verify_reports, verify_walls)
        _same_cross_mode_outputs(
            current["summary"][0], current["verify"][0], current["affine"][0]
        )
        decoded.append(current)

    for mode in ("summary", "verify", "affine"):
        _same_mode_outputs([run[mode][0] for run in decoded], mode)
    assert expected_incoming is not None
    expected_timing = _timing_payload(decoded)
    timing = artifact.get("timing")
    if not isinstance(timing, dict) or set(timing) != _TIMING_FIELDS:
        raise HurstAffineEquivalenceError("qualification timing fields changed")
    for family_name in ("runner_elapsed_seconds", "process_wall_seconds"):
        family = timing.get(family_name)
        if not isinstance(family, dict) or set(family) != _MODE_TIMING_FIELDS:
            raise HurstAffineEquivalenceError("qualification timing family changed")
        for field in _MODE_TIMING_FIELDS:
            _decimal(family.get(field), f"{family_name}.{field}")
    _decimal(
        timing.get("runner_elapsed_two_pass_over_affine"),
        "runner elapsed speedup",
    )
    _decimal(
        timing.get("process_wall_two_pass_over_affine"),
        "process wall speedup",
    )
    if timing != expected_timing:
        raise HurstAffineEquivalenceError("qualification timing arithmetic changed")

    chain = artifact.get("chain")
    if not isinstance(chain, dict) or set(chain) != _CHAIN_FIELDS:
        raise HurstAffineEquivalenceError("qualification chain fields changed")
    entries = chain.get("entries")
    if not isinstance(entries, list) or len(entries) != len(ranges):
        raise HurstAffineEquivalenceError("qualification chain is incomplete")
    if any(not isinstance(entry, dict) or set(entry) != _CHAIN_ENTRY_FIELDS for entry in entries):
        raise HurstAffineEquivalenceError("qualification chain entry fields changed")
    if chain != expected_chain:
        raise HurstAffineEquivalenceError("qualification chain differs from exact replay")

    checks = artifact.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != _CHECK_FIELDS
        or any(value is not True for value in checks.values())
    ):
        raise HurstAffineEquivalenceError("qualification checks changed")
    capabilities = artifact.get("capabilities")
    expected_capabilities = {
        "bounded_qualification_complete": True,
        "full_source_range": False,
        "source_rows_replayed_independently": False,
        "primitive_mobius_realization_proved": False,
        "runner_source_compilation_proved": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "source_scale_speedup_claimed": False,
    }
    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != _CAPABILITY_FIELDS
        or capabilities != expected_capabilities
    ):
        raise HurstAffineEquivalenceError("qualification capability boundary changed")
    return dict(artifact)


def run_qualification(
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    output: Path,
    domain_lower: int,
    domain_upper_exclusive: int,
    shard_span: int,
    segment_size: int,
    repeat_count: int = 3,
    runner_threads: int = 1,
    timeout_seconds: int | None = None,
    root_state: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Run and retain one bounded exact cross-mode qualification."""

    ranges = _ranges(domain_lower, domain_upper_exclusive, shard_span)
    segment = _plain_int(segment_size, "segment size", minimum=MIN_SEGMENT_SIZE)
    if segment > MAX_SEGMENT_SIZE:
        raise HurstAffineEquivalenceError("segment size exceeds the runner limit")
    repeats = _plain_int(repeat_count, "repeat count", minimum=1)
    threads = _plain_int(runner_threads, "runner threads", minimum=1)
    if timeout_seconds is not None:
        _plain_int(timeout_seconds, "timeout seconds", minimum=1)
    if output.exists():
        raise HurstAffineEquivalenceError(
            f"refusing to overwrite qualification artifact: {output}"
        )
    try:
        runner_digest, runner_size = hash_file_once(runner, limit=MAX_RUNNER_BYTES)
        source_digest, source_size = hash_file_once(
            runner_source, limit=MAX_SOURCE_BYTES
        )
        upstream_digest, upstream_size = hash_file_once(
            upstream_manifest, limit=MAX_SOURCE_BYTES
        )
        upstream_raw = upstream_manifest.read_bytes()
        _validate_upstream_manifest(upstream_raw)
    except (CampaignIOError, OSError, RuntimeError) as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc

    runs: list[dict[str, Any]] = []
    incoming_states: list[tuple[int, int, int, int]] | None = None
    chosen_root: tuple[int, int, int, int] | None = None
    root_selection: str | None = None
    chain: dict[str, Any] | None = None
    decoded_for_timing: list[
        dict[str, tuple[list[dict[str, Any]], list[Decimal]]]
    ] = []

    for repeat_index in range(repeats):
        order = _MODE_ORDERS[repeat_index % len(_MODE_ORDERS)]
        if repeat_index == 0:
            order = _MODE_ORDERS[0]
        record_sets: dict[str, list[dict[str, Any]]] = {
            "summary": [],
            "verify": [],
            "affine": [],
        }
        decoded: dict[str, tuple[list[dict[str, Any]], list[Decimal]]] = {}
        for mode in order:
            if mode == "verify" and incoming_states is None:
                raise HurstAffineEquivalenceError(
                    "internal mode order attempted verify before root selection"
                )
            for index, (lower, upper) in enumerate(ranges):
                incoming = None if mode != "verify" else incoming_states[index]
                record_sets[mode].append(
                    _run_record(
                        runner,
                        index=index,
                        mode=mode,
                        lower=lower,
                        upper_exclusive=upper,
                        segment_size=segment,
                        incoming=incoming,
                        runner_threads=threads,
                        timeout_seconds=timeout_seconds,
                    )
                )
            reports: list[dict[str, Any]] = []
            walls: list[Decimal] = []
            for index, (record, bounds) in enumerate(
                zip(record_sets[mode], ranges, strict=True)
            ):
                report, wall = _decode_record(
                    record,
                    expected_index=index,
                    expected_range=bounds,
                    mode=mode,
                    segment_size=segment,
                    incoming=None if mode != "verify" else incoming_states[index],
                )
                reports.append(report)
                walls.append(wall)
            decoded[mode] = (reports, walls)
            if repeat_index == 0 and mode == "affine":
                global_lower, global_upper = _translated_global_guard(reports)
                chosen_root, root_selection = _choose_root(
                    global_lower, global_upper, root_state
                )
                chain = _chain(
                    ranges,
                    chosen_root,
                    reports,
                    global_lower,
                    global_upper,
                )
                incoming_states = [
                    _state(entry["incoming"], "chain incoming")
                    for entry in chain["entries"]
                ]
        _same_cross_mode_outputs(
            decoded["summary"][0], decoded["verify"][0], decoded["affine"][0]
        )
        runs.append(
            {
                "repeat_index": repeat_index,
                "mode_order": list(order),
                "summary": record_sets["summary"],
                "verify": record_sets["verify"],
                "affine": record_sets["affine"],
            }
        )
        decoded_for_timing.append(decoded)

    for mode in ("summary", "verify", "affine"):
        _same_mode_outputs(
            [decoded[mode][0] for decoded in decoded_for_timing], mode
        )
    assert chosen_root is not None
    assert root_selection is not None
    assert chain is not None
    timing = _timing_payload(decoded_for_timing)
    for path, expected, maximum in (
        (runner, (runner_digest, runner_size), MAX_RUNNER_BYTES),
        (runner_source, (source_digest, source_size), MAX_SOURCE_BYTES),
        (
            upstream_manifest,
            (upstream_digest, upstream_size),
            MAX_SOURCE_BYTES,
        ),
    ):
        try:
            observed = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise HurstAffineEquivalenceError(str(exc)) from exc
        if observed != expected:
            raise HurstAffineEquivalenceError(
                f"bound file changed during qualification: {path}"
            )
    artifact = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "classification": CLASSIFICATION,
        "runner_algorithm": RUNNER_ALGORITHM,
        "upstream_commit": UPSTREAM_COMMIT,
        "identity": {
            "runner_sha256": runner_digest,
            "runner_size_bytes": runner_size,
            "source_sha256": source_digest,
            "source_size_bytes": source_size,
            "upstream_manifest_sha256": upstream_digest,
            "upstream_manifest_size_bytes": upstream_size,
        },
        "configuration": {
            "domain_lower": domain_lower,
            "domain_upper_exclusive": domain_upper_exclusive,
            "shard_span": shard_span,
            "shard_count": len(ranges),
            "segment_size": segment,
            "repeat_count": repeats,
            "runner_threads": threads,
            "root_selection": root_selection,
            "root_state": list(chosen_root),
        },
        "runs": runs,
        "chain": chain,
        "timing": timing,
        "checks": {
            "raw_receipts_bound": True,
            "repeat_outputs_equal_ignoring_timing": True,
            "mode_independent_outputs_equal": True,
            "all_affine_guards_accept_derived_inputs": True,
            "verify_singletons_equal_derived_inputs": True,
            "terminal_states_equal": True,
            "gap_free_ordered_coverage": True,
        },
        "capabilities": {
            "bounded_qualification_complete": True,
            "full_source_range": False,
            "source_rows_replayed_independently": False,
            "primitive_mobius_realization_proved": False,
            "runner_source_compilation_proved": False,
            "execution_attested": False,
            "lean_atom_discharged": False,
            "source_scale_speedup_claimed": False,
        },
    }
    _decode_and_check(
        artifact,
        runner=runner,
        runner_source=runner_source,
        upstream_manifest=upstream_manifest,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o444,
        )
        try:
            raw = canonical_json_bytes(artifact)
            written = os.write(descriptor, raw)
            if written != len(raw):
                raise HurstAffineEquivalenceError(
                    "short write of qualification artifact"
                )
        finally:
            os.close(descriptor)
    except FileExistsError as exc:
        raise HurstAffineEquivalenceError(
            f"refusing to overwrite qualification artifact: {output}"
        ) from exc
    except OSError as exc:
        raise HurstAffineEquivalenceError(
            f"cannot write qualification artifact: {exc}"
        ) from exc
    return artifact


def verify_qualification(
    path: Path,
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
) -> dict[str, Any]:
    """Independently replay one retained bounded qualification artifact."""

    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise HurstAffineEquivalenceError(str(exc)) from exc
    if not isinstance(value, dict):
        raise HurstAffineEquivalenceError("qualification root must be an object")
    return _decode_and_check(
        value,
        runner=runner,
        runner_source=runner_source,
        upstream_manifest=upstream_manifest,
    )


def qualification_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Return the concise non-evidentiary benchmark summary."""

    return {
        "qualification_sha256": canonical_sha256(dict(artifact)),
        "configuration": artifact["configuration"],
        "final_state": artifact["chain"]["final_state"],
        "timing": artifact["timing"],
        "capabilities": artifact["capabilities"],
    }


__all__ = [
    "ALGORITHM",
    "CLASSIFICATION",
    "HurstAffineEquivalenceError",
    "SCHEMA",
    "qualification_summary",
    "run_qualification",
    "verify_qualification",
]
