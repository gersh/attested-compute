# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed structural checks for self-authored CUDA Moebius receipts.

The runner reports that it independently CPU-checks every GPU row. This module
does not replay those rows or authenticate execution; it validates the
deterministic summary's internal structure and composes consecutive state
transitions. A receipt is external evidence, not a Lean proof.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Mapping, Sequence


SOURCE_LIMIT = 10_000_000_000_000_000
RUNNER_MAX_RECORD_COUNT = 100_000_000
ZERO_DIGEST = "0" * 64
_DIGEST = re.compile(r"[0-9a-f]{64}")


class MobiusReceiptError(ValueError):
    """A receipt or receipt chain failed a structural check."""


def _integer(report: Mapping[str, Any], name: str) -> int:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MobiusReceiptError(f"{name} must be an integer")
    return value


def _digest(report: Mapping[str, Any], name: str) -> str:
    value = report.get(name)
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise MobiusReceiptError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _problem_n(report: Mapping[str, Any], name: str) -> int:
    value = report.get(name)
    if value is None:
        return 0
    if not isinstance(value, Mapping):
        raise MobiusReceiptError(f"{name} must be null or an object")
    n = value.get("interval_n")
    if isinstance(n, bool) or not isinstance(n, int):
        raise MobiusReceiptError(f"{name}.interval_n must be an integer")
    return n


def _problem_fields(report: Mapping[str, Any], name: str) -> tuple[int, str, int]:
    value = report.get(name)
    if value is None:
        return 0, "none", 0
    if not isinstance(value, Mapping):
        raise MobiusReceiptError(f"{name} must be null or an object")
    n = _problem_n(report, name)
    side = value.get("side")
    y = value.get("y")
    if side not in (
        "at_integer_or_open_right_limit",
        "left_limit_at_next_integer",
    ) or isinstance(y, bool) or not isinstance(y, int):
        raise MobiusReceiptError(f"{name} has invalid endpoint fields")
    if y != n + int(side == "left_limit_at_next_integer"):
        raise MobiusReceiptError(f"{name} endpoint does not match its interval")
    return n, side, y


def _canonical_transition(report: Mapping[str, Any]) -> bytes:
    histogram = report.get("mobius_histogram")
    if not isinstance(histogram, Mapping):
        raise MobiusReceiptError("mobius_histogram must be an object")
    first_hurst = report.get("hurst_first_failure")
    if first_hurst is not None and (
        isinstance(first_hurst, bool) or not isinstance(first_hurst, int)
    ):
        raise MobiusReceiptError("hurst_first_failure must be null or an integer")
    b1_n, b1_side, b1_y = _problem_fields(
        report, "cdem_b1_first_not_proved_safe"
    )
    b2_n, b2_side, b2_y = _problem_fields(
        report, "cdem_b2_first_not_proved_safe"
    )
    minimum_slack = report.get("hurst_minimum_squared_slack")
    minimum_at = report.get("hurst_minimum_squared_slack_at")
    if minimum_slack is not None and (
        isinstance(minimum_slack, bool) or not isinstance(minimum_slack, int)
    ):
        raise MobiusReceiptError("hurst minimum slack must be null or an integer")
    if minimum_at is not None and (
        isinstance(minimum_at, bool) or not isinstance(minimum_at, int)
    ):
        raise MobiusReceiptError("hurst minimum location must be null or an integer")
    values: dict[str, Any] = {
        "previous": _digest(report, "previous_receipt_sha256"),
        "lower": _integer(report, "lower"),
        "upper": _integer(report, "upper"),
        "incoming_mertens": _integer(report, "incoming_mertens"),
        "outgoing_mertens": _integer(report, "outgoing_mertens"),
        "incoming_squarefree": _integer(report, "incoming_squarefree"),
        "outgoing_squarefree": _integer(report, "outgoing_squarefree"),
        "record_sha256": _digest(report, "gpu_record_sha256_le_v1"),
        "executable_sha256": _digest(report, "executable_sha256"),
        "density_interval": report.get("squarefree_density_interval_id"),
        "mu_negative": histogram.get("-1"),
        "mu_zero": histogram.get("0"),
        "mu_positive": histogram.get("1"),
        "hurst_checks": _integer(report, "hurst_integer_checks"),
        "hurst_first_failure": 0 if first_hurst is None else first_hurst,
        "hurst_minimum_slack": "null" if minimum_slack is None else minimum_slack,
        "hurst_minimum_at": 0 if minimum_at is None else minimum_at,
        "b1_checks": _integer(report, "cdem_b1_endpoint_checks"),
        "b1_problem_n": b1_n,
        "b1_problem_side": b1_side,
        "b1_problem_y": b1_y,
        "b2_checks": _integer(report, "cdem_b2_endpoint_checks"),
        "b2_problem_n": b2_n,
        "b2_problem_side": b2_side,
        "b2_problem_y": b2_y,
    }
    for name in ("mu_negative", "mu_zero", "mu_positive"):
        if isinstance(values[name], bool) or not isinstance(values[name], int):
            raise MobiusReceiptError(f"{name} must be an integer")
    return (
        "algorithm=tg_mobius_segment_v1\n"
        "previous={previous}\n"
        "lower={lower}\nupper={upper}\n"
        "incoming_mertens={incoming_mertens}\n"
        "outgoing_mertens={outgoing_mertens}\n"
        "incoming_squarefree={incoming_squarefree}\n"
        "outgoing_squarefree={outgoing_squarefree}\n"
        "record_sha256={record_sha256}\n"
        "executable_sha256={executable_sha256}\n"
        "density_interval={density_interval}\n"
        "mu_negative={mu_negative}\nmu_zero={mu_zero}\n"
        "mu_positive={mu_positive}\n"
        "hurst_checks={hurst_checks}\n"
        "hurst_first_failure={hurst_first_failure}\n"
        "hurst_minimum_slack={hurst_minimum_slack}\n"
        "hurst_minimum_at={hurst_minimum_at}\n"
        "b1_checks={b1_checks}\nb1_problem_n={b1_problem_n}\n"
        "b1_problem_side={b1_problem_side}\nb1_problem_y={b1_problem_y}\n"
        "b2_checks={b2_checks}\nb2_problem_n={b2_problem_n}\n"
        "b2_problem_side={b2_problem_side}\nb2_problem_y={b2_problem_y}\n"
    ).format(**values).encode("ascii")


def verify_mobius_receipt(report: Mapping[str, Any]) -> None:
    """Validate one receipt, including its canonical transition digest."""

    if not isinstance(report, Mapping):
        raise MobiusReceiptError("each receipt must be an object")
    for required in (
        "hurst_first_failure",
        "hurst_minimum_squared_slack",
        "hurst_minimum_squared_slack_at",
        "cdem_b1_first_not_proved_safe",
        "cdem_b2_first_not_proved_safe",
    ):
        if required not in report:
            raise MobiusReceiptError(f"receipt omits required field {required}")
    if report.get("schema_version") != 1 or report.get("algorithm") != (
        "tg_mobius_segment_v1"
    ):
        raise MobiusReceiptError("unsupported receipt schema or algorithm")
    if report.get("classification") != (
        "bounded_exact_transition_not_external_atom_proof"
    ) or report.get("canonical_transition_format") != (
        "tg_mobius_transition_lines_v1"
    ):
        raise MobiusReceiptError("unexpected receipt classification or format")
    lower, upper, count = (
        _integer(report, "lower"),
        _integer(report, "upper"),
        _integer(report, "record_count"),
    )
    if (
        lower < 1
        or upper > SOURCE_LIMIT
        or count < 1
        or count > RUNNER_MAX_RECORD_COUNT
        or upper - lower + 1 != count
    ):
        raise MobiusReceiptError("receipt range is malformed")
    incoming_mertens = _integer(report, "incoming_mertens")
    incoming_squarefree = _integer(report, "incoming_squarefree")
    previous_digest = _digest(report, "previous_receipt_sha256")
    if not (-(lower - 1) <= incoming_mertens <= lower - 1):
        raise MobiusReceiptError("incoming Mertens state exceeds its prefix range")
    if not (0 <= incoming_squarefree <= lower - 1):
        raise MobiusReceiptError("incoming squarefree state exceeds its prefix range")
    if lower == 1 and (
        incoming_mertens != 0
        or incoming_squarefree != 0
        or previous_digest != ZERO_DIGEST
    ):
        raise MobiusReceiptError("root receipt is not rooted at zero")
    if lower != 1 and previous_digest == ZERO_DIGEST:
        raise MobiusReceiptError("non-root receipt has a zero previous digest")
    gpu_digest = _digest(report, "gpu_record_sha256_le_v1")
    if gpu_digest == ZERO_DIGEST:
        raise MobiusReceiptError("record digest must be nonzero")
    if _digest(report, "cpu_record_sha256_le_v1") != gpu_digest:
        raise MobiusReceiptError("GPU and CPU record hashes differ")
    if _digest(report, "executable_sha256") == ZERO_DIGEST:
        raise MobiusReceiptError("executable digest must be nonzero")
    if report.get("all_records_compared_with_independent_cpu_segmented_sieve") is not True:
        raise MobiusReceiptError("complete CPU comparison is absent")
    if _integer(report, "mismatch_count") != 0 or report.get("first_mismatch_number") is not None:
        raise MobiusReceiptError("receipt records a GPU/CPU mismatch")

    histogram = report.get("mobius_histogram")
    if not isinstance(histogram, Mapping):
        raise MobiusReceiptError("mobius_histogram must be an object")
    counts: list[int] = []
    for key in ("-1", "0", "1"):
        value = histogram.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MobiusReceiptError(f"invalid histogram entry {key}")
        counts.append(value)
    negative, zero, positive = counts
    if sum(counts) != count:
        raise MobiusReceiptError("Moebius histogram does not cover the range")
    delta = positive - negative
    if _integer(report, "delta_mertens") != delta or _integer(
        report, "outgoing_mertens"
    ) != _integer(report, "incoming_mertens") + delta:
        raise MobiusReceiptError("Mertens transition does not compose")
    if _integer(report, "segment_squarefree_count") != positive + negative or _integer(
        report, "outgoing_squarefree"
    ) != _integer(report, "incoming_squarefree") + positive + negative:
        raise MobiusReceiptError("squarefree transition does not compose")

    if _integer(report, "hurst_integer_checks") != max(
        0, upper - max(lower, 33) + 1
    ):
        raise MobiusReceiptError("Hurst check count is incomplete")
    first_hurst = report.get("hurst_first_failure")
    if first_hurst is not None and not (max(lower, 33) <= first_hurst <= upper):
        raise MobiusReceiptError("Hurst failure lies outside the checked range")
    minimum_at = report.get("hurst_minimum_squared_slack_at")
    if (minimum_at is None) != (_integer(report, "hurst_integer_checks") == 0):
        raise MobiusReceiptError("Hurst minimum location has wrong nullability")
    if minimum_at is not None and not (max(lower, 33) <= minimum_at <= upper):
        raise MobiusReceiptError("Hurst minimum lies outside the checked range")
    minimum_slack = report.get("hurst_minimum_squared_slack")
    if _integer(report, "hurst_integer_checks") == 0:
        if minimum_slack is not None:
            raise MobiusReceiptError("empty Hurst range has a minimum slack")
    elif isinstance(minimum_slack, bool) or not isinstance(minimum_slack, int):
        raise MobiusReceiptError("nonempty Hurst range lacks an integer minimum slack")
    elif first_hurst is None and minimum_slack < 0:
        raise MobiusReceiptError("negative Hurst minimum without a recorded failure")
    elif first_hurst is not None and minimum_slack >= 0:
        raise MobiusReceiptError("recorded Hurst failure with nonnegative minimum")

    def cdem_checks(threshold: int) -> int:
        rows = max(0, upper - max(lower, threshold) + 1)
        return 2 * rows - int(rows > 0 and upper == SOURCE_LIMIT)

    if _integer(report, "cdem_b1_endpoint_checks") != cdem_checks(9_243) or _integer(
        report, "cdem_b2_endpoint_checks"
    ) != cdem_checks(438_429):
        raise MobiusReceiptError("CDEM endpoint coverage is incomplete")
    if report.get("squarefree_density_interval_id") != (
        "machin_20_6_coarsened_1e18_v1"
    ) or report.get("squarefree_density_lower") != (
        "607927101854026628/1000000000000000000"
    ) or report.get("squarefree_density_upper") != (
        "607927101854026629/1000000000000000000"
    ):
        raise MobiusReceiptError("squarefree density enclosure changed")
    for name, threshold in (
        ("cdem_b1_first_not_proved_safe", 9_243),
        ("cdem_b2_first_not_proved_safe", 438_429),
    ):
        problem = report.get(name)
        if problem is not None:
            if not isinstance(problem, Mapping):
                raise MobiusReceiptError(f"{name} must be an object")
            n = problem["interval_n"]
            if not (max(lower, threshold) <= n <= upper):
                raise MobiusReceiptError(f"{name} lies outside its checked range")
            if problem["y"] > SOURCE_LIMIT:
                raise MobiusReceiptError(f"{name} lies above the source endpoint")
    if report.get("incoming_state_is_locally_rooted") is not (lower == 1):
        raise MobiusReceiptError("incoming-state root classification is wrong")
    if report.get("nonroot_claims_are_conditional_on_hash_linked_incoming_state") is not (
        lower != 1
    ):
        raise MobiusReceiptError("conditional incoming-state classification is wrong")
    if report.get("checks_hurst_source_shape_conditionally") is not True or report.get(
        "checks_cdem_squarefree_source_shape_conditionally"
    ) is not True:
        raise MobiusReceiptError("source-shape status is absent or false")
    expected_digest = hashlib.sha256(_canonical_transition(report)).hexdigest()
    receipt_digest = _digest(report, "receipt_chain_sha256")
    if receipt_digest == ZERO_DIGEST:
        raise MobiusReceiptError("receipt transition digest must be nonzero")
    if receipt_digest != expected_digest:
        raise MobiusReceiptError("receipt transition hash is invalid")
    for name in (
        "single_receipt_covers_full_1e16_range",
        "has_complete_1e16_receipt_chain",
        "proves_mertens_hurst_external_atom",
        "proves_cdem_squarefree_external_atom",
        "proves_any_external_atom",
    ):
        if report.get(name) is not False:
            raise MobiusReceiptError(f"unsafe claim in {name}")


@dataclass(frozen=True)
class MobiusChainResult:
    upper: int
    receipts: int
    final_mertens: int
    final_squarefree: int
    structurally_reports_no_hurst_failure: bool
    structurally_reports_no_cdem_b1_failure: bool
    structurally_reports_no_cdem_b2_failure: bool
    structurally_claims_full_source_range: bool
    execution_authenticated: bool = False
    rows_replayed_by_chain_checker: bool = False
    lean_atoms_discharged: bool = False


def verify_mobius_receipt_chain(
    reports: Sequence[Mapping[str, Any]],
) -> MobiusChainResult:
    """Compose self-reported states without replaying or authenticating rows."""

    if not reports:
        raise MobiusReceiptError("receipt chain must be nonempty")
    previous: Mapping[str, Any] | None = None
    executable_sha256: str | None = None
    for report in reports:
        if not isinstance(report, Mapping):
            raise MobiusReceiptError("each receipt must be an object")
        verify_mobius_receipt(report)
        report_executable = _digest(report, "executable_sha256")
        if executable_sha256 is None:
            executable_sha256 = report_executable
        elif report_executable != executable_sha256:
            raise MobiusReceiptError("receipt chain changes executable identity")
        if previous is None:
            if _integer(report, "lower") != 1 or _integer(
                report, "incoming_mertens"
            ) != 0 or _integer(report, "incoming_squarefree") != 0 or _digest(
                report, "previous_receipt_sha256"
            ) != ZERO_DIGEST:
                raise MobiusReceiptError("receipt chain is not rooted at zero")
        else:
            if _integer(report, "lower") != _integer(previous, "upper") + 1:
                raise MobiusReceiptError("receipt ranges are not consecutive")
            if _integer(report, "incoming_mertens") != _integer(
                previous, "outgoing_mertens"
            ) or _integer(report, "incoming_squarefree") != _integer(
                previous, "outgoing_squarefree"
            ) or _digest(report, "previous_receipt_sha256") != _digest(
                previous, "receipt_chain_sha256"
            ):
                raise MobiusReceiptError("receipt states or hash links do not compose")
        previous = report
    if previous is None:
        raise MobiusReceiptError("receipt chain unexpectedly ended empty")
    upper = _integer(previous, "upper")
    hurst = upper >= 33 and all(
        r.get("hurst_first_failure") is None for r in reports
    )
    b1 = upper >= 9_243 and all(
        r.get("cdem_b1_first_not_proved_safe") is None for r in reports
    )
    b2 = upper >= 438_429 and all(
        r.get("cdem_b2_first_not_proved_safe") is None for r in reports
    )
    return MobiusChainResult(
        upper=upper,
        receipts=len(reports),
        final_mertens=_integer(previous, "outgoing_mertens"),
        final_squarefree=_integer(previous, "outgoing_squarefree"),
        structurally_reports_no_hurst_failure=hurst,
        structurally_reports_no_cdem_b1_failure=b1,
        structurally_reports_no_cdem_b2_failure=b2,
        structurally_claims_full_source_range=(
            upper == SOURCE_LIMIT and hurst and b1 and b2
        ),
    )
