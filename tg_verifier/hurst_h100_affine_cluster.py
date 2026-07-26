# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Distributed affine H100 execution for the shared Hurst computation.

The persistent CUDA worker's arithmetic over a range is affine in its two
incoming coordinates.  A worker therefore does not need the exact Mertens and
squarefree prefix produced by every preceding worker.  It may run with an
explicitly labelled proxy state and emit:

* exact additive ``delta_mertens`` and ``delta_squarefree`` values; and
* exact lower/upper guards for an admissible incoming M/Q state.

Production uses eight one-H100 Azure nodes.  This module runs their contiguous
ranges independently, then performs the ordered exclusive scan that derives
the *real* incoming state of every range from the CPU handoff.  It translates
each local extremum by the exact preceding delta, checks every derived state
against the local guards, and composes the exact global extrema with the
runner's source-order tie breaking.  The multi-GPU launcher is retained only
as a bounded local test harness.

The proxy inputs are retained in every plan and receipt.  They are never
presented as the sequential incoming states.  ``CUDA_VISIBLE_DEVICES`` is
likewise recorded only as process routing; the worker checks the visible
device class, but routing is neither hardware identity nor attestation.

This is execution/certificate machinery.  Its semantic flags deliberately do
not claim primitive Mobius realization, compiler refinement, attestation, or
Lean theorem production.
"""

from __future__ import annotations

from bisect import bisect_right
import hashlib
import math
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from typing import Any, BinaryIO, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    parse_json_bytes,
    require_azure_measured_worker_for_workload,
    sha256_bytes,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .hurst_hybrid_source import (
    CPU_HANDOFF_KIND,
    GPU_ALGORITHM,
    HurstHybridSourceError,
    MAX_INPUT_BYTES,
    MAX_JSONL_LINE_BYTES,
    MAX_RECEIPT_BYTES,
    MAX_STDERR_BYTES,
    SEMANTIC_FLAGS,
    SOURCE_PRIME_ROSTER_BYTES,
    _copy_captured,
    _cpu_command,
    _cpu_handoff,
    _digest,
    _expected_selected_prime_counts,
    _fixed_environment,
    _fsync_directory,
    _global_bound,
    _json_line,
    _load_plan,
    _open_pinned_fd,
    _plain_int,
    _prime_roster_values,
    _read_open_fd,
    _readonly_tree,
    _run_cpu,
    _run_h100,
    _select_extreme,
    _validate_cpu_numeric_types,
    _validate_header,
    _validate_leaf,
    _validate_terminal,
)
from .hurst_residual_campaign import (
    HurstResidualCampaignError,
    STATE_COMPONENTS,
    validate_runner_receipt,
)


SCHEMA_VERSION = 1
PLAN_KIND = "sparkinterval.tg.hurst-h100-affine-cluster-plan.v1"
WORKER_STATUS_KIND = (
    "sparkinterval.tg.hurst-h100-affine-cluster-worker-status.v1"
)
SCAN_KIND = "sparkinterval.tg.hurst-h100-affine-cluster-scan.v1"
RESULT_KIND = "sparkinterval.tg.hurst-h100-affine-cluster-result.v1"
PREPARED_KIND = "sparkinterval.tg.hurst-h100-affine-distributed-prepared.v1"
WORKER_BUNDLE_KIND = (
    "sparkinterval.tg.hurst-h100-affine-distributed-worker-bundle.v1"
)
ALGORITHM = "hurst-h100-eight-way-independent-affine-scan-v1"
CLASSIFICATION = (
    "validated_affine_execution_receipts_not_attestation_"
    "primitive_semantics_compiler_refinement_or_lean_proof"
)

PRODUCTION_WORKER_COUNT = 8
MAX_WORKER_COUNT = 8
WORKER_ANCHOR_DOMAIN = (
    b"sparkinterval/tg/hurst-h100-affine-worker-anchor/v1\0"
)
WORKER_CHAIN_DOMAIN = (
    b"sparkinterval/tg/hurst-h100-affine-worker-chain/v1\0"
)
RESULT_DOMAIN = b"sparkinterval/tg/hurst-h100-affine-result/v1\0"
_DEVICE_SELECTOR = re.compile(r"(?:0|[1-9][0-9]*)\Z")

# The two adjacent 10^-18 rational enclosures used by the reviewed CUDA
# squarefree endpoint predicate.  Their midpoint gives a deterministic proxy
# close to Q(x); the worker still checks the proxy against its exact guard.
_DENSITY_LOWER_NUMERATOR = 607_927_101_854_026_628
_DENSITY_UPPER_NUMERATOR = 607_927_101_854_026_629
_DENSITY_DENOMINATOR = 1_000_000_000_000_000_000


class HurstH100AffineClusterError(RuntimeError):
    """An eight-way H100 affine execution or replay failed closed."""


def _wrap(error: BaseException) -> HurstH100AffineClusterError:
    return HurstH100AffineClusterError(str(error))


def _bounded_bytes(path: Path, maximum: int, what: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size < 0
            or metadata.st_size > maximum
        ):
            raise HurstH100AffineClusterError(
                f"{what} has an invalid size or file type"
            )
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(
                descriptor, min(1 << 20, maximum + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        final = os.fstat(descriptor)
    except OSError as error:
        raise HurstH100AffineClusterError(
            f"cannot read {what}: {error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    raw = b"".join(chunks)
    if (
        total > maximum
        or len(raw) != metadata.st_size
        or final.st_size != metadata.st_size
        or final.st_mtime_ns != metadata.st_mtime_ns
        or final.st_ctime_ns != metadata.st_ctime_ns
    ):
        raise HurstH100AffineClusterError(f"{what} changed while read")
    return raw


def _canonical_object_capture(
    path: Path,
    what: str,
    *,
    maximum: int = MAX_INPUT_BYTES,
) -> tuple[dict[str, Any], bytes]:
    raw = _bounded_bytes(path, maximum, what)
    try:
        value = parse_json_bytes(raw, label=what)
    except CampaignIOError as error:
        raise HurstH100AffineClusterError(str(error)) from error
    if not isinstance(value, dict):
        raise HurstH100AffineClusterError(f"{what} is not an object")
    if raw != canonical_json_bytes(value):
        raise HurstH100AffineClusterError(
            f"{what} is not canonical JSON"
        )
    return value, raw


def _canonical_object(path: Path, what: str) -> dict[str, Any]:
    value, _ = _canonical_object_capture(path, what)
    return value


def proxy_squarefree_state(lower: int) -> int:
    """Return the deterministic midpoint-density proxy for ``Q(lower - 1)``."""

    start = _plain_int(lower, "worker lower", minimum=2) - 1
    twice_numerator = (
        _DENSITY_LOWER_NUMERATOR + _DENSITY_UPPER_NUMERATOR
    )
    denominator = 2 * _DENSITY_DENOMINATOR
    # Round to nearest, ties upward.  This is only a proxy witness.  Exact
    # admissibility is checked against the worker-emitted guard.
    result = (start * twice_numerator + denominator // 2) // denominator
    if not 0 <= result <= start:
        raise HurstH100AffineClusterError(
            "squarefree proxy escaped its elementary prefix range"
        )
    return result


def partition_affine_range(
    *,
    lower: int,
    upper_exclusive: int,
    worker_count: int,
    super_shard_rows: int,
) -> tuple[dict[str, int], ...]:
    """Partition a range into gap-free, super-shard-aligned worker ranges."""

    start = _plain_int(lower, "cluster lower", minimum=2)
    stop = _plain_int(upper_exclusive, "cluster upper", minimum=start + 1)
    workers = _plain_int(worker_count, "worker count", minimum=1)
    super_rows = _plain_int(
        super_shard_rows, "super-shard rows", minimum=1
    )
    if workers > MAX_WORKER_COUNT:
        raise HurstH100AffineClusterError(
            f"worker count exceeds the {MAX_WORKER_COUNT}-worker cap"
        )
    count = stop - start
    if count % super_rows != 0:
        raise HurstH100AffineClusterError(
            "cluster range must contain an integral number of super-shards"
        )
    blocks = count // super_rows
    if blocks < workers:
        raise HurstH100AffineClusterError(
            "cluster range has fewer super-shards than workers"
        )
    quotient, remainder = divmod(blocks, workers)
    result: list[dict[str, int]] = []
    cursor = start
    for index in range(workers):
        worker_blocks = quotient + (index < remainder)
        worker_count_rows = worker_blocks * super_rows
        worker_upper = cursor + worker_count_rows
        result.append(
            {
                "count": worker_count_rows,
                "index": index,
                "lower": cursor,
                "super_shard_count": worker_blocks,
                "upper_exclusive": worker_upper,
            }
        )
        cursor = worker_upper
    if cursor != stop:
        raise HurstH100AffineClusterError("cluster partition is not exact")
    return tuple(result)


def _device_selectors(
    worker_count: int,
    selectors: Sequence[str] | None,
    *,
    require_distinct: bool,
) -> tuple[str, ...]:
    if selectors is None:
        values = (
            tuple(str(index) for index in range(worker_count))
            if require_distinct
            else ("0",) * worker_count
        )
    else:
        values = tuple(selectors)
    if len(values) != worker_count:
        raise HurstH100AffineClusterError(
            "device selector count differs from worker count"
        )
    if (
        (
            require_distinct
            and len(set(values)) != len(values)
        )
        or any(_DEVICE_SELECTOR.fullmatch(value) is None for value in values)
    ):
        raise HurstH100AffineClusterError(
            "device selectors must be nonnegative decimal indices"
            + (" and distinct" if require_distinct else "")
        )
    return values


def build_cluster_plan(
    *,
    hybrid_plan: Mapping[str, Any],
    hybrid_plan_sha256: str,
    cpu_handoff: Mapping[str, Any],
    worker_count: int = PRODUCTION_WORKER_COUNT,
    device_selectors: Sequence[str] | None = None,
    routing_mode: str | None = None,
) -> dict[str, Any]:
    """Build the immutable independent-worker plan after the CPU handoff."""

    count = _plain_int(worker_count, "worker count", minimum=1)
    mode = hybrid_plan.get("mode")
    if mode == "production" and count != PRODUCTION_WORKER_COUNT:
        raise HurstH100AffineClusterError(
            "production requires exactly eight H100 workers"
        )
    if mode not in ("production", "bounded_test"):
        raise HurstH100AffineClusterError("hybrid plan mode changed")
    routing = (
        (
            "distributed_one_h100_per_node"
            if mode == "production"
            else "local_multi_gpu"
        )
        if routing_mode is None
        else routing_mode
    )
    if routing not in (
        "distributed_one_h100_per_node",
        "local_multi_gpu",
    ):
        raise HurstH100AffineClusterError(
            "cluster routing mode is unsupported"
        )
    if mode == "production" and routing != "distributed_one_h100_per_node":
        raise HurstH100AffineClusterError(
            "Azure NCC40ads H100 v5 production uses one H100 per node"
        )
    _digest(hybrid_plan_sha256, "hybrid plan SHA-256", nonzero=True)
    if (
        cpu_handoff.get("kind") != CPU_HANDOFF_KIND
        or cpu_handoff.get("plan_sha256") != hybrid_plan_sha256
    ):
        raise HurstH100AffineClusterError(
            "CPU handoff is not bound to the hybrid plan"
        )
    handoff_digest = _digest(
        cpu_handoff.get("receipt_chain_sha256"),
        "CPU handoff chain",
        nonzero=True,
    )
    gpu = hybrid_plan["source_geometry"]["h100"]
    h100 = hybrid_plan["h100"]
    ranges = partition_affine_range(
        lower=gpu["lower"],
        upper_exclusive=gpu["upper_exclusive"],
        worker_count=count,
        super_shard_rows=h100["super_shard_rows"],
    )
    selectors = _device_selectors(
        count,
        device_selectors,
        require_distinct=routing == "local_multi_gpu",
    )
    assignments = []
    for shard, selector in zip(ranges, selectors, strict=True):
        assignments.append(
            {
                **shard,
                "cuda_visible_devices_selector": selector,
                "logical_cuda_device": 0,
                "proxy_incoming_mertens": 0,
                "proxy_incoming_squarefree": proxy_squarefree_state(
                    shard["lower"]
                ),
                "proxy_state_is_sequential_state": False,
            }
        )
    return {
        "algorithm": ALGORITHM,
        "classification": CLASSIFICATION,
        "cpu_handoff_sha256": handoff_digest,
        "device_policy": {
            "attestation_present": False,
            "device_identity_present": False,
            "logical_cuda_device": 0,
            "required_device_class": h100["required_device_class"],
            "selectors_are_process_routing_only": True,
            "visible_device_count_required_by_worker": 1,
        },
        "hybrid_plan_sha256": hybrid_plan_sha256,
        "kind": PLAN_KIND,
        "leaf_rows": h100["leaf_rows"],
        "mode": mode,
        "schema_version": SCHEMA_VERSION,
        "routing_mode": routing,
        "semantic_flags": dict(SEMANTIC_FLAGS),
        "state_components": list(STATE_COMPONENTS),
        "super_shard_rows": h100["super_shard_rows"],
        "worker_assignments": assignments,
        "worker_count": count,
        "worker_topology": (
            "eight_azure_ncc40ads_h100_v5_nodes"
            if routing == "distributed_one_h100_per_node"
            else "one_local_host_with_multiple_visible_gpus"
        ),
    }


def worker_anchor(
    cluster_plan_sha256: str, assignment: Mapping[str, Any]
) -> str:
    """Bind one independent leaf chain to its immutable assignment."""

    _digest(cluster_plan_sha256, "cluster plan SHA-256", nonzero=True)
    payload = {
        "cluster_plan_sha256": cluster_plan_sha256,
        "count": assignment["count"],
        "cuda_visible_devices_selector": assignment[
            "cuda_visible_devices_selector"
        ],
        "index": assignment["index"],
        "lower": assignment["lower"],
        "proxy_incoming_mertens": assignment[
            "proxy_incoming_mertens"
        ],
        "proxy_incoming_squarefree": assignment[
            "proxy_incoming_squarefree"
        ],
        "upper_exclusive": assignment["upper_exclusive"],
    }
    return hashlib.sha256(
        WORKER_ANCHOR_DOMAIN + canonical_json_bytes(payload)
    ).hexdigest()


def worker_command(
    *,
    runner: Path,
    roster: Path,
    assignment: Mapping[str, Any],
    cluster_plan_sha256: str,
    leaf_rows: int,
    super_shard_rows: int,
    required_device_class: str,
) -> tuple[str, ...]:
    """Return a strict one-visible-device command for an independent shard."""

    if required_device_class != "nvidia-h100-sm90":
        raise HurstH100AffineClusterError(
            "cluster worker requires the reviewed H100 device class"
        )
    return (
        "/usr/bin/env",
        "CUDA_VISIBLE_DEVICES="
        + assignment["cuda_visible_devices_selector"],
        str(runner),
        "--lower",
        str(assignment["lower"]),
        "--count",
        str(assignment["count"]),
        "--shard-rows",
        str(leaf_rows),
        "--super-shard-rows",
        str(super_shard_rows),
        "--incoming-mertens",
        str(assignment["proxy_incoming_mertens"]),
        "--incoming-squarefree",
        str(assignment["proxy_incoming_squarefree"]),
        "--previous-leaf-sha256",
        worker_anchor(cluster_plan_sha256, assignment),
        "--source-prime-roster",
        str(roster),
        "--require-device-class",
        required_device_class,
        "--device",
        "0",
    )


def _bound_dict(
    terminal: Mapping[str, Any], name: str
) -> dict[str, Any]:
    value, witness, order, side = _global_bound(
        terminal[f"global_{name}"],
        endpoint_side=name.startswith("squarefree"),
        what=f"worker terminal global_{name}",
    )
    common: dict[str, Any] = {
        "source_order": order,
        "value": value,
        "witness_y": witness,
    }
    if name.startswith("squarefree"):
        return {**common, "side": side}
    return common


def _choose_bound(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
    *,
    maximum: bool,
) -> dict[str, Any]:
    if current is None:
        return candidate
    current_key = (
        -current["value"] if maximum else current["value"],
        current["source_order"],
    )
    candidate_key = (
        -candidate["value"] if maximum else candidate["value"],
        candidate["source_order"],
    )
    return candidate if candidate_key < current_key else current


def compose_worker_terminals(
    *,
    cluster_plan: Mapping[str, Any],
    cpu_state: Sequence[int],
    worker_statuses: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Perform the exact ordered M/Q scan and affine-extrema composition."""

    if len(cpu_state) != 4 or any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in cpu_state
    ):
        raise HurstH100AffineClusterError(
            "CPU state must contain exactly four integers"
        )
    assignments = cluster_plan["worker_assignments"]
    if len(assignments) != cluster_plan["worker_count"]:
        raise HurstH100AffineClusterError("cluster assignment count changed")
    by_index: dict[int, Mapping[str, Any]] = {}
    for status in worker_statuses:
        index = status.get("worker_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index in by_index
        ):
            raise HurstH100AffineClusterError(
                "worker status indices are malformed or duplicated"
            )
        by_index[index] = status
    if set(by_index) != set(range(len(assignments))):
        raise HurstH100AffineClusterError(
            "worker status set is incomplete"
        )

    current_m = cpu_state[0]
    current_q = cpu_state[1]
    cumulative_m = 0
    cumulative_q = 0
    expected_lower = assignments[0]["lower"]
    source_lower = expected_lower
    entries: list[dict[str, Any]] = []
    extrema: dict[str, dict[str, Any] | None] = {
        "hurst_lower": None,
        "hurst_upper": None,
        "squarefree_lower": None,
        "squarefree_upper": None,
    }
    previous_chain = cluster_plan["cpu_handoff_sha256"]
    cluster_plan_sha256 = sha256_bytes(canonical_json_bytes(cluster_plan))

    for index, assignment in enumerate(assignments):
        if (
            assignment["index"] != index
            or assignment["lower"] != expected_lower
            or assignment["upper_exclusive"]
            != assignment["lower"] + assignment["count"]
        ):
            raise HurstH100AffineClusterError(
                "worker assignments are not ordered and gap-free"
            )
        status = by_index[index]
        terminal = status.get("terminal")
        if not isinstance(terminal, Mapping):
            raise HurstH100AffineClusterError(
                f"worker {index} terminal is absent"
            )
        if (
            status.get("kind") != WORKER_STATUS_KIND
            or status.get("cluster_plan_sha256") != cluster_plan_sha256
            or status.get("worker_anchor_sha256")
            != worker_anchor(cluster_plan_sha256, assignment)
            or terminal.get("lower") != assignment["lower"]
            or terminal.get("upper_exclusive")
            != assignment["upper_exclusive"]
            or terminal.get("count") != assignment["count"]
            or terminal.get("incoming_mertens")
            != assignment["proxy_incoming_mertens"]
            or terminal.get("incoming_squarefree")
            != assignment["proxy_incoming_squarefree"]
        ):
            raise HurstH100AffineClusterError(
                f"worker {index} status is not bound to its assignment"
            )
        delta_m = _plain_int(
            terminal.get("delta_mertens"),
            f"worker {index} delta M",
        )
        delta_q = _plain_int(
            terminal.get("delta_squarefree"),
            f"worker {index} delta Q",
            minimum=0,
        )
        if (
            not -assignment["count"] <= delta_m <= assignment["count"]
            or delta_q > assignment["count"]
        ):
            raise HurstH100AffineClusterError(
                f"worker {index} delta exceeds its row count"
            )

        local_bounds = {
            name: _bound_dict(terminal, name)
            for name in extrema
        }
        if not (
            local_bounds["hurst_lower"]["value"]
            <= current_m
            <= local_bounds["hurst_upper"]["value"]
        ):
            raise HurstH100AffineClusterError(
                f"derived Mertens input violates worker {index} affine guard"
            )
        if not (
            local_bounds["squarefree_lower"]["value"]
            <= current_q
            <= local_bounds["squarefree_upper"]["value"]
        ):
            raise HurstH100AffineClusterError(
                f"derived squarefree input violates worker {index} affine guard"
            )

        translated: dict[str, dict[str, Any]] = {}
        for name, local in local_bounds.items():
            prefix = cumulative_m if name.startswith("hurst") else cumulative_q
            absolute = dict(local)
            absolute["value"] = local["value"] - prefix
            absolute["source_order"] = (
                2 * (assignment["lower"] - source_lower)
                + local["source_order"]
            )
            translated[name] = absolute
            extrema[name] = _choose_bound(
                extrema[name],
                absolute,
                maximum=name.endswith("lower"),
            )

        outgoing_m = current_m + delta_m
        outgoing_q = current_q + delta_q
        if (
            not -(assignment["upper_exclusive"] - 1)
            <= outgoing_m
            <= assignment["upper_exclusive"] - 1
            or not 0
            <= outgoing_q
            <= assignment["upper_exclusive"] - 1
        ):
            raise HurstH100AffineClusterError(
                f"worker {index} derived outgoing state is impossible"
            )
        entry_payload = {
            "derived_incoming": [current_m, current_q],
            "derived_outgoing": [outgoing_m, outgoing_q],
            "delta": [delta_m, delta_q],
            "index": index,
            "local_guard": local_bounds,
            "lower": assignment["lower"],
            "previous_worker_chain_sha256": previous_chain,
            "proxy_incoming": [
                assignment["proxy_incoming_mertens"],
                assignment["proxy_incoming_squarefree"],
            ],
            "proxy_is_derived_incoming": (
                assignment["proxy_incoming_mertens"] == current_m
                and assignment["proxy_incoming_squarefree"] == current_q
            ),
            "stream_sha256": status["stream"]["sha256"],
            "terminal_leaf_sha256": terminal["final_leaf_sha256"],
            "translated_root_guard": translated,
            "upper_exclusive": assignment["upper_exclusive"],
        }
        chain = hashlib.sha256(
            WORKER_CHAIN_DOMAIN + canonical_json_bytes(entry_payload)
        ).hexdigest()
        entries.append({**entry_payload, "worker_chain_sha256": chain})
        previous_chain = chain
        cumulative_m += delta_m
        cumulative_q += delta_q
        current_m = outgoing_m
        current_q = outgoing_q
        expected_lower = assignment["upper_exclusive"]

    if expected_lower != assignments[-1]["upper_exclusive"]:
        raise HurstH100AffineClusterError("cluster scan ended early")
    if any(value is None for value in extrema.values()):
        raise HurstH100AffineClusterError("cluster scan omitted an extremum")
    checked_extrema = {
        name: value for name, value in extrema.items() if value is not None
    }
    if not (
        checked_extrema["hurst_lower"]["value"]
        <= cpu_state[0]
        <= checked_extrema["hurst_upper"]["value"]
        and checked_extrema["squarefree_lower"]["value"]
        <= cpu_state[1]
        <= checked_extrema["squarefree_upper"]["value"]
    ):
        raise HurstH100AffineClusterError(
            "CPU handoff violates the composed root guard"
        )
    return {
        "algorithm": ALGORITHM,
        "all_derived_inputs_in_local_guards": True,
        "classification": CLASSIFICATION,
        "cluster_plan_sha256": cluster_plan_sha256,
        "cpu_handoff_state": list(cpu_state),
        "entries": entries,
        "exact_gap_free_coverage": True,
        "final_state": [
            current_m,
            current_q,
            cpu_state[2],
            cpu_state[3],
        ],
        "global_root_guard": checked_extrema,
        "kind": SCAN_KIND,
        "proxy_inputs_used_as_sequential_states": False,
        "schema_version": SCHEMA_VERSION,
        "worker_count": len(assignments),
        "worker_receipt_chain_sha256": previous_chain,
    }


def _execute_cpu_stage(
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    cpu_runner: Path,
    cpu_runner_fd: int,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    cpu_range = plan["source_geometry"]["cpu"]
    incoming = (0, 0, 0, 0)
    summary_command = _cpu_command(
        cpu_runner,
        phase="summary",
        lower=cpu_range["lower"],
        upper_exclusive=cpu_range["upper_exclusive"],
        segment_rows=plan["cpu"]["segment_rows"],
        incoming=None,
    )
    summary, summary_raw, summary_stderr = _run_cpu(
        summary_command,
        timeout_seconds=timeout_seconds,
        pass_fds=(cpu_runner_fd,),
    )
    _validate_cpu_numeric_types(summary, "CPU summary receipt")
    summary_delta = validate_runner_receipt(
        summary,
        phase="summary",
        shard_lower=cpu_range["lower"],
        shard_upper=cpu_range["upper_exclusive"],
        segment_size=plan["cpu"]["segment_rows"],
    )
    verify_command = _cpu_command(
        cpu_runner,
        phase="verify",
        lower=cpu_range["lower"],
        upper_exclusive=cpu_range["upper_exclusive"],
        segment_rows=plan["cpu"]["segment_rows"],
        incoming=incoming,
    )
    verify, verify_raw, verify_stderr = _run_cpu(
        verify_command,
        timeout_seconds=timeout_seconds,
        pass_fds=(cpu_runner_fd,),
    )
    _validate_cpu_numeric_types(verify, "CPU verify receipt")
    verify_delta = validate_runner_receipt(
        verify,
        phase="verify",
        shard_lower=cpu_range["lower"],
        shard_upper=cpu_range["upper_exclusive"],
        segment_size=plan["cpu"]["segment_rows"],
        expected_incoming=incoming,
    )
    if (
        summary_delta != verify_delta
        or summary["row_sha256"] != verify["row_sha256"]
    ):
        raise HurstH100AffineClusterError(
            "CPU summary/verify row commitment or delta differs"
        )
    outgoing = tuple(
        left + right
        for left, right in zip(incoming, verify_delta, strict=True)
    )
    if (
        not -cpu_range["count"] <= outgoing[0] <= cpu_range["count"]
        or not 0 <= outgoing[1] <= cpu_range["count"]
        or outgoing[2] > outgoing[3]
    ):
        raise HurstH100AffineClusterError(
            "CPU outgoing state is impossible"
        )
    handoff = _cpu_handoff(
        plan_sha256=plan_sha256,
        geometry=plan["source_geometry"],
        runner_sha256=plan["inputs"]["cpu_runner"]["sha256"],
        summary_raw=summary_raw,
        verify_raw=verify_raw,
        report=verify,
        outgoing=outgoing,
    )
    return handoff, {
        "cpu-summary.json": summary_raw,
        "cpu-summary.stderr": summary_stderr,
        "cpu-verify.json": verify_raw,
        "cpu-verify.stderr": verify_stderr,
        "cpu-handoff.json": canonical_json_bytes(handoff),
    }


def _execute_independent_worker_stream(
    argv: Sequence[str],
    *,
    output_path: Path,
    stderr_path: Path,
    assignment: Mapping[str, Any],
    cluster_plan: Mapping[str, Any],
    cluster_plan_sha256: str,
    runner_sha256: str,
    roster_sha256: str,
    prime_roster: Sequence[int],
    timeout_seconds: int,
    pass_fds: Sequence[int],
) -> tuple[dict[str, Any], int, str, int, bool]:
    """Run one affine-summary worker without requiring its proxy guard."""

    timeout = _plain_int(
        timeout_seconds, "H100 timeout seconds", minimum=1
    )
    try:
        with output_path.open("x+b") as output, stderr_path.open(
            "x+b"
        ) as stderr:
            completed = subprocess.run(
                list(argv),
                env=_fixed_environment(),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=stderr,
                check=False,
                pass_fds=tuple(pass_fds),
                timeout=timeout,
            )
            output.flush()
            os.fsync(output.fileno())
            stderr.flush()
            os.fsync(stderr.fileno())
            stderr_size = stderr.tell()
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HurstH100AffineClusterError(
            f"independent H100 worker failed: {error}"
        ) from error
    if stderr_size > MAX_STDERR_BYTES:
        raise HurstH100AffineClusterError(
            "independent H100 stderr exceeds capture limit"
        )
    if completed.returncode != 0:
        raise HurstH100AffineClusterError(
            f"independent H100 worker exited {completed.returncode}"
        )
    return replay_worker_stream(
        stream_path=output_path,
        assignment=assignment,
        cluster_plan=cluster_plan,
        cluster_plan_sha256=cluster_plan_sha256,
        runner_sha256=runner_sha256,
        roster_sha256=roster_sha256,
        prime_roster=prime_roster,
    )


def _worker_process_entry(
    *,
    worker_index: int,
    argv: Sequence[str],
    output_path: Path,
    stderr_path: Path,
    status_path: Path,
    gpu_range: Mapping[str, int],
    leaf_rows: int,
    super_rows: int,
    anchor: str,
    proxy_state: tuple[int, int],
    runner_sha256: str,
    roster_sha256: str,
    prime_roster: Sequence[int],
    timeout_seconds: int,
    pass_fds: Sequence[int],
    cluster_plan_sha256: str,
) -> None:
    """Fork child entry: validate one stream and publish a tiny status."""

    try:
        os.setsid()
        with output_path.open("x+b") as output:
            terminal, leaf_count = _run_h100(
                argv,
                output=output,
                stderr_path=stderr_path,
                gpu_range=gpu_range,
                leaf_rows=leaf_rows,
                super_rows=super_rows,
                initial_digest=anchor,
                initial_state=(proxy_state[0], proxy_state[1], 0, 0),
                runner_sha256=runner_sha256,
                roster_sha256=roster_sha256,
                prime_roster=prime_roster,
                timeout_seconds=timeout_seconds,
                pass_fds=pass_fds,
            )
            output.flush()
            os.fsync(output.fileno())
        status = {
            "cluster_plan_sha256": cluster_plan_sha256,
            "kind": WORKER_STATUS_KIND,
            "leaf_count": leaf_count,
            "schema_version": SCHEMA_VERSION,
            "terminal": terminal,
            "worker_anchor_sha256": anchor,
            "worker_index": worker_index,
        }
        descriptor = os.open(
            status_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(status))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as error:
        try:
            failure_path = status_path.with_suffix(".failure.json")
            descriptor = os.open(
                failure_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    canonical_json_bytes(
                        {
                            "error": str(error),
                            "worker_index": worker_index,
                        }
                    )
                )
        except BaseException:
            pass
        raise


def _terminate_worker_groups(
    processes: Sequence[multiprocessing.Process],
) -> None:
    for process in processes:
        # A failed supervisor child can leave its CUDA runner alive in the
        # session it created.  Address the process group even when the Python
        # child itself has already exited.
        if process.pid is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 5
    for process in processes:
        process.join(max(0.0, deadline - time.monotonic()))
    for process in processes:
        if process.pid is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.join()


def _run_workers(
    *,
    stage: Path,
    cluster_plan: Mapping[str, Any],
    cluster_plan_sha256: str,
    h100_runner: Path,
    roster: Path,
    h100_runner_fd: int,
    roster_fd: int,
    runner_sha256: str,
    roster_sha256: str,
    prime_roster: Sequence[int],
    timeout_seconds: int,
) -> tuple[dict[str, Any], ...]:
    try:
        context = multiprocessing.get_context("fork")
    except ValueError as error:
        raise HurstH100AffineClusterError(
            "the production cluster orchestrator requires Linux fork support"
        ) from error
    worker_root = stage / "workers"
    worker_root.mkdir()
    processes: list[multiprocessing.Process] = []
    for assignment in cluster_plan["worker_assignments"]:
        index = assignment["index"]
        anchor = worker_anchor(cluster_plan_sha256, assignment)
        gpu_range = {
            "count": assignment["count"],
            "lower": assignment["lower"],
            "upper_exclusive": assignment["upper_exclusive"],
        }
        command = worker_command(
            runner=h100_runner,
            roster=roster,
            assignment=assignment,
            cluster_plan_sha256=cluster_plan_sha256,
            leaf_rows=cluster_plan["leaf_rows"],
            super_shard_rows=cluster_plan["super_shard_rows"],
            required_device_class=cluster_plan["device_policy"][
                "required_device_class"
            ],
        )
        process = context.Process(
            name=f"tg-hurst-h100-{index}",
            target=_worker_process_entry,
            kwargs={
                "worker_index": index,
                "argv": command,
                "output_path": worker_root / f"worker-{index:02d}.jsonl",
                "stderr_path": worker_root / f"worker-{index:02d}.stderr",
                "status_path": worker_root / f"worker-{index:02d}-status.json",
                "gpu_range": gpu_range,
                "leaf_rows": cluster_plan["leaf_rows"],
                "super_rows": cluster_plan["super_shard_rows"],
                "anchor": anchor,
                "proxy_state": (
                    assignment["proxy_incoming_mertens"],
                    assignment["proxy_incoming_squarefree"],
                ),
                "runner_sha256": runner_sha256,
                "roster_sha256": roster_sha256,
                "prime_roster": prime_roster,
                "timeout_seconds": timeout_seconds,
                "pass_fds": (h100_runner_fd, roster_fd),
                "cluster_plan_sha256": cluster_plan_sha256,
            },
        )
        processes.append(process)
    try:
        for process in processes:
            process.start()
        failed: multiprocessing.Process | None = None
        while any(process.is_alive() for process in processes):
            for process in processes:
                process.join(timeout=0)
                if process.exitcode not in (None, 0):
                    failed = process
                    break
            if failed is not None:
                break
            time.sleep(0.2)
        if failed is not None:
            _terminate_worker_groups(processes)
            failure = worker_root / (
                f"worker-{processes.index(failed):02d}-status.failure.json"
            )
            detail = ""
            if failure.exists():
                try:
                    detail = str(_canonical_object(failure, "worker failure")["error"])
                except (HurstH100AffineClusterError, KeyError):
                    detail = ""
            raise HurstH100AffineClusterError(
                f"H100 worker {processes.index(failed)} failed"
                + (f": {detail}" if detail else "")
            )
        for process in processes:
            process.join()
            if process.exitcode != 0:
                raise HurstH100AffineClusterError(
                    "an H100 worker failed without a status"
                )
    except BaseException:
        _terminate_worker_groups(processes)
        raise

    statuses: list[dict[str, Any]] = []
    for assignment in cluster_plan["worker_assignments"]:
        index = assignment["index"]
        status_path = worker_root / f"worker-{index:02d}-status.json"
        status = _canonical_object(status_path, f"worker {index} status")
        stream_path = worker_root / f"worker-{index:02d}.jsonl"
        stderr_path = worker_root / f"worker-{index:02d}.stderr"
        stream_sha, stream_size = hash_file_once(stream_path)
        stderr_sha, stderr_size = hash_file_once(stderr_path)
        status["stream"] = {
            "path": f"workers/worker-{index:02d}.jsonl",
            "sha256": stream_sha,
            "size_bytes": stream_size,
        }
        status["stderr"] = {
            "path": f"workers/worker-{index:02d}.stderr",
            "sha256": stderr_sha,
            "size_bytes": stderr_size,
        }
        status_path.unlink()
        _copy_captured(
            status_path,
            canonical_json_bytes(status),
            executable=False,
        )
        statuses.append(status)
    return tuple(statuses)


def run(
    *,
    materialization_directory: Path,
    output_directory: Path,
    worker_count: int = PRODUCTION_WORKER_COUNT,
    device_selectors: Sequence[str] | None = None,
    cpu_timeout_seconds: int = 7 * 24 * 3600,
    h100_timeout_seconds: int = 7 * 24 * 3600,
) -> dict[str, Any]:
    """Run the CPU prefix and independent affine H100 workers."""

    try:
        plan, plan_sha256 = _load_plan(materialization_directory)
    except HurstHybridSourceError as error:
        raise _wrap(error) from error
    cpu_range = plan["source_geometry"]["cpu"]
    gpu_range = plan["source_geometry"]["h100"]
    exact_production = plan["mode"] == "production"
    if exact_production:
        raise HurstH100AffineClusterError(
            "the Azure NCC40ads H100 v5 production topology is one H100 "
            "per node; use prepare, run-worker on eight nodes, and reduce"
        )
    try:
        backend = require_azure_measured_worker_for_workload(
            exact_production=exact_production,
            work_bounds=(cpu_range["count"], gpu_range["count"]),
        )
    except CampaignIOError as error:
        raise _wrap(error) from error
    del backend
    if output_directory.exists() or output_directory.is_symlink():
        raise HurstH100AffineClusterError(
            "cluster execution output already exists"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.running-",
            dir=output_directory.parent,
        )
    )
    published = False
    pinned: list[int] = []
    try:
        cpu_fd = _open_pinned_fd(
            materialization_directory
            / plan["inputs"]["cpu_runner"]["path"],
            plan["inputs"]["cpu_runner"],
            "CPU runner",
            executable=True,
        )
        pinned.append(cpu_fd)
        h100_fd = _open_pinned_fd(
            materialization_directory
            / plan["inputs"]["h100_runner"]["path"],
            plan["inputs"]["h100_runner"],
            "H100 runner",
            executable=True,
        )
        pinned.append(h100_fd)
        roster_fd = _open_pinned_fd(
            materialization_directory
            / plan["inputs"]["prime_roster"]["path"],
            plan["inputs"]["prime_roster"],
            "source-prime roster",
            executable=False,
        )
        pinned.append(roster_fd)
        cpu_runner = Path(f"/proc/self/fd/{cpu_fd}")
        h100_runner = Path(f"/proc/self/fd/{h100_fd}")
        roster = Path(f"/proc/self/fd/{roster_fd}")
        roster_raw = (
            _read_open_fd(
                roster_fd,
                maximum_bytes=SOURCE_PRIME_ROSTER_BYTES,
                what="canonical source-prime roster",
            )
            if exact_production
            else None
        )
        prime_roster = _prime_roster_values(
            raw=roster_raw,
            expected_sha256=plan["inputs"]["prime_roster"]["sha256"],
            source_upper_exclusive=gpu_range["upper_exclusive"],
            production=exact_production,
        )

        handoff, cpu_files = _execute_cpu_stage(
            plan=plan,
            plan_sha256=plan_sha256,
            cpu_runner=cpu_runner,
            cpu_runner_fd=cpu_fd,
            timeout_seconds=cpu_timeout_seconds,
        )
        for name, raw in {
            "hybrid-plan.json": canonical_json_bytes(plan),
            **cpu_files,
        }.items():
            _copy_captured(stage / name, raw, executable=False)
        cluster_plan = build_cluster_plan(
            hybrid_plan=plan,
            hybrid_plan_sha256=plan_sha256,
            cpu_handoff=handoff,
            worker_count=worker_count,
            device_selectors=device_selectors,
            routing_mode="local_multi_gpu",
        )
        cluster_plan_raw = canonical_json_bytes(cluster_plan)
        cluster_plan_sha256 = sha256_bytes(cluster_plan_raw)
        _copy_captured(
            stage / "h100-affine-cluster-plan.json",
            cluster_plan_raw,
            executable=False,
        )

        statuses = _run_workers(
            stage=stage,
            cluster_plan=cluster_plan,
            cluster_plan_sha256=cluster_plan_sha256,
            h100_runner=h100_runner,
            roster=roster,
            h100_runner_fd=h100_fd,
            roster_fd=roster_fd,
            runner_sha256=plan["inputs"]["h100_runner"]["sha256"],
            roster_sha256=plan["inputs"]["prime_roster"]["sha256"],
            prime_roster=prime_roster,
            timeout_seconds=h100_timeout_seconds,
        )
        if (
            _bounded_bytes(
                stage / "h100-affine-cluster-plan.json",
                MAX_INPUT_BYTES,
                "retained cluster plan",
            )
            != cluster_plan_raw
            or _bounded_bytes(
                stage / "cpu-handoff.json",
                MAX_RECEIPT_BYTES,
                "retained CPU handoff",
            )
            != cpu_files["cpu-handoff.json"]
        ):
            raise HurstH100AffineClusterError(
                "cluster plan or CPU handoff changed during execution"
            )
        scan = compose_worker_terminals(
            cluster_plan=cluster_plan,
            cpu_state=handoff["outgoing_state"],
            worker_statuses=statuses,
        )
        scan_raw = canonical_json_bytes(scan)
        _copy_captured(
            stage / "h100-affine-scan.json", scan_raw, executable=False
        )
        receipt_pins: dict[str, Any] = {}
        for name in (
            "cpu-summary.json",
            "cpu-verify.json",
            "cpu-handoff.json",
            "h100-affine-cluster-plan.json",
            "h100-affine-scan.json",
        ):
            digest, size = hash_file_once(stage / name)
            receipt_pins[name] = {
                "path": name,
                "sha256": digest,
                "size_bytes": size,
            }
        worker_pins = [
            {
                "index": status["worker_index"],
                "status": {
                    "path": (
                        f"workers/worker-{status['worker_index']:02d}"
                        "-status.json"
                    ),
                    "sha256": hash_file_once(
                        stage
                        / (
                            f"workers/worker-{status['worker_index']:02d}"
                            "-status.json"
                        )
                    )[0],
                    "size_bytes": (
                        stage
                        / (
                            f"workers/worker-{status['worker_index']:02d}"
                            "-status.json"
                        )
                    ).stat().st_size,
                },
                "stream": status["stream"],
                "stderr": status["stderr"],
            }
            for status in statuses
        ]
        payload = {
            "accepted": False,
            "affine_composition_verified": True,
            "algorithm": ALGORITHM,
            "arithmetic_execution_completed": True,
            "classification": CLASSIFICATION,
            "cluster_plan_sha256": cluster_plan_sha256,
            "cpu_handoff_sha256": handoff["receipt_chain_sha256"],
            "device_routing_is_attestation": False,
            "final_state": scan["final_state"],
            "hybrid_plan_sha256": plan_sha256,
            "kind": RESULT_KIND,
            "mode": plan["mode"],
            "proxy_inputs_used_as_sequential_states": False,
            "receipt_artifacts": receipt_pins,
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "source_run_receipt_produced": False,
            "worker_count": len(statuses),
            "worker_receipt_chain_sha256": scan[
                "worker_receipt_chain_sha256"
            ],
            "worker_receipts": worker_pins,
        }
        result_digest = hashlib.sha256(
            RESULT_DOMAIN + canonical_json_bytes(payload)
        ).hexdigest()
        result = {**payload, "result_sha256": result_digest}
        _copy_captured(
            stage / "result.json",
            canonical_json_bytes(result),
            executable=False,
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {**result, "output_directory": str(output_directory)}
    except (
        CampaignIOError,
        EvidenceError,
        HurstHybridSourceError,
        OSError,
        ValueError,
    ) as error:
        raise _wrap(error) from error
    finally:
        for descriptor in pinned:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not published:
            shutil.rmtree(stage, ignore_errors=True)


def _distributed_worker_commands(
    cluster_plan: Mapping[str, Any],
    cluster_plan_sha256: str,
) -> dict[str, Any]:
    return {
        "classification": (
            "portable_scheduler_commands_not_execution_or_attestation"
        ),
        "cluster_plan_sha256": cluster_plan_sha256,
        "kind": "sparkinterval.tg.hurst-h100-affine-worker-commands.v1",
        "schema_version": SCHEMA_VERSION,
        "workers": [
            {
                "array_index": assignment["index"],
                "argv": [
                    "${TG_PYTHON}",
                    (
                        "${TG_REPOSITORY}/tools/"
                        "tg_hurst_h100_affine_cluster.py"
                    ),
                    "run-worker",
                    "${TG_HURST_MATERIALIZATION}",
                    "${TG_HURST_AFFINE_PREPARED}",
                    "--worker-index",
                    str(assignment["index"]),
                    "--output-dir",
                    (
                        "${TG_HURST_WORKER_OUTPUT_ROOT}/"
                        f"worker-{assignment['index']:02d}"
                    ),
                ],
                "backend": "azure_ncc40ads_h100_v5",
                "h100_count": 1,
                "range": {
                    "count": assignment["count"],
                    "lower": assignment["lower"],
                    "upper_exclusive": assignment["upper_exclusive"],
                },
            }
            for assignment in cluster_plan["worker_assignments"]
        ],
    }


def _artifact_pin(name: str, raw: bytes) -> dict[str, Any]:
    return {
        "path": name,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def prepare_distributed(
    *,
    materialization_directory: Path,
    output_directory: Path,
    worker_count: int = PRODUCTION_WORKER_COUNT,
    cpu_timeout_seconds: int = 7 * 24 * 3600,
) -> dict[str, Any]:
    """Prepare the CPU handoff and eight one-H100 Azure worker commands."""

    try:
        plan, plan_sha256 = _load_plan(materialization_directory)
    except HurstHybridSourceError as error:
        raise _wrap(error) from error
    cpu_range = plan["source_geometry"]["cpu"]
    production = plan["mode"] == "production"
    try:
        backend = require_azure_measured_worker_for_workload(
            exact_production=production,
            work_bounds=(cpu_range["count"],),
        )
    except CampaignIOError as error:
        raise _wrap(error) from error
    if production and backend not in (
        "azure_ncc40ads_h100_v5",
        "azure_sevsnp_cpu",
    ):
        raise HurstH100AffineClusterError(
            "production CPU handoff requires a measured Azure worker"
        )
    if output_directory.exists() or output_directory.is_symlink():
        raise HurstH100AffineClusterError(
            "distributed preparation output already exists"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.preparing-",
            dir=output_directory.parent,
        )
    )
    cpu_fd: int | None = None
    published = False
    try:
        cpu_fd = _open_pinned_fd(
            materialization_directory
            / plan["inputs"]["cpu_runner"]["path"],
            plan["inputs"]["cpu_runner"],
            "CPU runner",
            executable=True,
        )
        handoff, cpu_files = _execute_cpu_stage(
            plan=plan,
            plan_sha256=plan_sha256,
            cpu_runner=Path(f"/proc/self/fd/{cpu_fd}"),
            cpu_runner_fd=cpu_fd,
            timeout_seconds=cpu_timeout_seconds,
        )
        cluster_plan = build_cluster_plan(
            hybrid_plan=plan,
            hybrid_plan_sha256=plan_sha256,
            cpu_handoff=handoff,
            worker_count=worker_count,
            device_selectors=("0",) * worker_count,
            routing_mode="distributed_one_h100_per_node",
        )
        cluster_raw = canonical_json_bytes(cluster_plan)
        cluster_sha = sha256_bytes(cluster_raw)
        commands = _distributed_worker_commands(cluster_plan, cluster_sha)
        files = {
            "hybrid-plan.json": canonical_json_bytes(plan),
            **cpu_files,
            "h100-affine-cluster-plan.json": cluster_raw,
            "worker-commands.json": canonical_json_bytes(commands),
        }
        for name, raw in files.items():
            _copy_captured(stage / name, raw, executable=False)
        payload = {
            "accepted": False,
            "arithmetic_execution_completed": False,
            "classification": (
                "distributed_plan_and_cpu_handoff_not_h100_execution_"
                "attestation_or_semantic_proof"
            ),
            "cluster_plan_sha256": cluster_sha,
            "cpu_handoff_sha256": handoff["receipt_chain_sha256"],
            "hybrid_plan_sha256": plan_sha256,
            "kind": PREPARED_KIND,
            "prepared_artifacts": {
                name: _artifact_pin(name, raw)
                for name, raw in sorted(files.items())
            },
            "routing_mode": "distributed_one_h100_per_node",
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "worker_count": worker_count,
        }
        _copy_captured(
            stage / "prepared.json",
            canonical_json_bytes(payload),
            executable=False,
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {**payload, "output_directory": str(output_directory)}
    except (
        CampaignIOError,
        HurstHybridSourceError,
        OSError,
        ValueError,
    ) as error:
        raise _wrap(error) from error
    finally:
        if cpu_fd is not None:
            try:
                os.close(cpu_fd)
            except OSError:
                pass
        if not published:
            shutil.rmtree(stage, ignore_errors=True)


def _replay_prepared_cpu_handoff(
    *,
    hybrid_plan: Mapping[str, Any],
    hybrid_plan_sha256: str,
    prepared_directory: Path,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Replay the CPU receipts and reconstruct their exact handoff."""

    summary_raw = _bounded_bytes(
        prepared_directory / "cpu-summary.json",
        MAX_RECEIPT_BYTES,
        "prepared CPU summary",
    )
    verify_raw = _bounded_bytes(
        prepared_directory / "cpu-verify.json",
        MAX_RECEIPT_BYTES,
        "prepared CPU verify",
    )
    summary_stderr = _bounded_bytes(
        prepared_directory / "cpu-summary.stderr",
        MAX_STDERR_BYTES,
        "prepared CPU summary stderr",
    )
    verify_stderr = _bounded_bytes(
        prepared_directory / "cpu-verify.stderr",
        MAX_STDERR_BYTES,
        "prepared CPU verify stderr",
    )
    try:
        summary = load_decimal_json_bytes(
            summary_raw, label="prepared CPU summary"
        )
        checked = load_decimal_json_bytes(
            verify_raw, label="prepared CPU verify"
        )
        _validate_cpu_numeric_types(summary, "prepared CPU summary")
        _validate_cpu_numeric_types(checked, "prepared CPU verify")
        cpu_range = hybrid_plan["source_geometry"]["cpu"]
        summary_delta = validate_runner_receipt(
            summary,
            phase="summary",
            shard_lower=cpu_range["lower"],
            shard_upper=cpu_range["upper_exclusive"],
            segment_size=hybrid_plan["cpu"]["segment_rows"],
        )
        verify_delta = validate_runner_receipt(
            checked,
            phase="verify",
            shard_lower=cpu_range["lower"],
            shard_upper=cpu_range["upper_exclusive"],
            segment_size=hybrid_plan["cpu"]["segment_rows"],
            expected_incoming=(0, 0, 0, 0),
        )
    except (
        EvidenceError,
        HurstHybridSourceError,
        HurstResidualCampaignError,
    ) as error:
        raise _wrap(error) from error
    if (
        summary_delta != verify_delta
        or summary["row_sha256"] != checked["row_sha256"]
    ):
        raise HurstH100AffineClusterError(
            "prepared CPU summary/verify pair differs"
        )
    outgoing = tuple(verify_delta)
    if (
        not -cpu_range["count"] <= outgoing[0] <= cpu_range["count"]
        or not 0 <= outgoing[1] <= cpu_range["count"]
        or outgoing[2] > outgoing[3]
    ):
        raise HurstH100AffineClusterError(
            "prepared CPU outgoing state is impossible"
        )
    expected = _cpu_handoff(
        plan_sha256=hybrid_plan_sha256,
        geometry=hybrid_plan["source_geometry"],
        runner_sha256=hybrid_plan["inputs"]["cpu_runner"]["sha256"],
        summary_raw=summary_raw,
        verify_raw=verify_raw,
        report=checked,
        outgoing=outgoing,
    )
    actual, handoff_raw = _canonical_object_capture(
        prepared_directory / "cpu-handoff.json",
        "prepared CPU handoff",
        maximum=MAX_RECEIPT_BYTES,
    )
    if actual != expected or handoff_raw != canonical_json_bytes(expected):
        raise HurstH100AffineClusterError(
            "prepared CPU handoff does not replay"
        )
    return expected, {
        "cpu-summary.json": summary_raw,
        "cpu-summary.stderr": summary_stderr,
        "cpu-verify.json": verify_raw,
        "cpu-verify.stderr": verify_stderr,
        "cpu-handoff.json": handoff_raw,
    }


def _load_distributed_preparation(
    *,
    materialization_directory: Path,
    prepared_directory: Path,
) -> tuple[dict[str, Any], str, dict[str, Any], str, dict[str, Any]]:
    try:
        hybrid, hybrid_sha = _load_plan(materialization_directory)
    except HurstHybridSourceError as error:
        raise _wrap(error) from error
    hybrid_raw = _bounded_bytes(
        prepared_directory / "hybrid-plan.json",
        MAX_INPUT_BYTES,
        "prepared hybrid plan",
    )
    if hybrid_raw != canonical_json_bytes(hybrid):
        raise HurstH100AffineClusterError(
            "prepared hybrid plan differs from materialization"
        )
    handoff, cpu_files = _replay_prepared_cpu_handoff(
        hybrid_plan=hybrid,
        hybrid_plan_sha256=hybrid_sha,
        prepared_directory=prepared_directory,
    )
    cluster, cluster_raw = _canonical_object_capture(
        prepared_directory / "h100-affine-cluster-plan.json",
        "prepared cluster plan",
    )
    cluster_sha = sha256_bytes(cluster_raw)
    prepared, _ = _canonical_object_capture(
        prepared_directory / "prepared.json",
        "distributed preparation",
    )
    worker_count = prepared.get("worker_count")
    if (
        isinstance(worker_count, bool)
        or not isinstance(worker_count, int)
        or not 1 <= worker_count <= MAX_WORKER_COUNT
    ):
        raise HurstH100AffineClusterError(
            "distributed preparation worker count is invalid"
        )
    expected_cluster = build_cluster_plan(
        hybrid_plan=hybrid,
        hybrid_plan_sha256=hybrid_sha,
        cpu_handoff=handoff,
        worker_count=worker_count,
        device_selectors=("0",) * worker_count,
        routing_mode="distributed_one_h100_per_node",
    )
    if cluster != expected_cluster:
        raise HurstH100AffineClusterError(
            "prepared cluster plan does not reconstruct"
        )
    expected_commands = _distributed_worker_commands(cluster, cluster_sha)
    commands, commands_raw = _canonical_object_capture(
        prepared_directory / "worker-commands.json",
        "prepared worker commands",
    )
    if commands != expected_commands:
        raise HurstH100AffineClusterError(
            "prepared worker commands do not reconstruct"
        )
    files = {
        "hybrid-plan.json": hybrid_raw,
        **cpu_files,
        "h100-affine-cluster-plan.json": cluster_raw,
        "worker-commands.json": commands_raw,
    }
    expected_prepared = {
        "accepted": False,
        "arithmetic_execution_completed": False,
        "classification": (
            "distributed_plan_and_cpu_handoff_not_h100_execution_"
            "attestation_or_semantic_proof"
        ),
        "cluster_plan_sha256": cluster_sha,
        "cpu_handoff_sha256": handoff["receipt_chain_sha256"],
        "hybrid_plan_sha256": hybrid_sha,
        "kind": PREPARED_KIND,
        "prepared_artifacts": {
            name: _artifact_pin(name, raw)
            for name, raw in sorted(files.items())
        },
        "routing_mode": "distributed_one_h100_per_node",
        "schema_version": SCHEMA_VERSION,
        "semantic_flags": dict(SEMANTIC_FLAGS),
        "worker_count": worker_count,
    }
    if prepared != expected_prepared:
        raise HurstH100AffineClusterError(
            "distributed preparation summary does not replay"
        )
    return hybrid, hybrid_sha, cluster, cluster_sha, handoff


def run_distributed_worker(
    *,
    materialization_directory: Path,
    prepared_directory: Path,
    worker_index: int,
    output_directory: Path,
    h100_timeout_seconds: int = 7 * 24 * 3600,
) -> dict[str, Any]:
    """Run one prepared shard on one Azure NCC40ads H100 v5 node."""

    hybrid, _, cluster, cluster_sha, _ = _load_distributed_preparation(
        materialization_directory=materialization_directory,
        prepared_directory=prepared_directory,
    )
    index = _plain_int(worker_index, "worker index", minimum=0)
    assignments = cluster["worker_assignments"]
    if index >= len(assignments) or assignments[index]["index"] != index:
        raise HurstH100AffineClusterError(
            "worker index is outside the prepared plan"
        )
    assignment = assignments[index]
    production = hybrid["mode"] == "production"
    try:
        backend = require_azure_measured_worker_for_workload(
            exact_production=production,
            work_bounds=(assignment["count"],),
        )
    except CampaignIOError as error:
        raise _wrap(error) from error
    if production and backend != "azure_ncc40ads_h100_v5":
        raise HurstH100AffineClusterError(
            "a production arithmetic shard requires one measured "
            "Azure NCC40ads H100 v5 worker"
        )
    if output_directory.exists() or output_directory.is_symlink():
        raise HurstH100AffineClusterError(
            "distributed worker output already exists"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.running-",
            dir=output_directory.parent,
        )
    )
    h100_fd: int | None = None
    roster_fd: int | None = None
    published = False
    try:
        h100_fd = _open_pinned_fd(
            materialization_directory
            / hybrid["inputs"]["h100_runner"]["path"],
            hybrid["inputs"]["h100_runner"],
            "H100 runner",
            executable=True,
        )
        roster_fd = _open_pinned_fd(
            materialization_directory
            / hybrid["inputs"]["prime_roster"]["path"],
            hybrid["inputs"]["prime_roster"],
            "source-prime roster",
            executable=False,
        )
        production_roster = (
            _read_open_fd(
                roster_fd,
                maximum_bytes=SOURCE_PRIME_ROSTER_BYTES,
                what="canonical source-prime roster",
            )
            if production
            else None
        )
        prime_roster = _prime_roster_values(
            raw=production_roster,
            expected_sha256=hybrid["inputs"]["prime_roster"]["sha256"],
            source_upper_exclusive=hybrid["source_geometry"]["h100"][
                "upper_exclusive"
            ],
            production=production,
        )
        runner = Path(f"/proc/self/fd/{h100_fd}")
        roster = Path(f"/proc/self/fd/{roster_fd}")
        command = worker_command(
            runner=runner,
            roster=roster,
            assignment=assignment,
            cluster_plan_sha256=cluster_sha,
            leaf_rows=cluster["leaf_rows"],
            super_shard_rows=cluster["super_shard_rows"],
            required_device_class=cluster["device_policy"][
                "required_device_class"
            ],
        )
        (
            terminal,
            leaf_count,
            stream_sha,
            stream_size,
            proxy_guard_accepted,
        ) = _execute_independent_worker_stream(
            command,
            output_path=stage / "worker.jsonl",
            stderr_path=stage / "worker.stderr",
            assignment=assignment,
            cluster_plan=cluster,
            cluster_plan_sha256=cluster_sha,
            runner_sha256=hybrid["inputs"]["h100_runner"]["sha256"],
            roster_sha256=hybrid["inputs"]["prime_roster"]["sha256"],
            prime_roster=prime_roster,
            timeout_seconds=h100_timeout_seconds,
            pass_fds=(h100_fd, roster_fd),
        )
        stderr_sha, stderr_size = hash_file_once(stage / "worker.stderr")
        status = {
            "cluster_plan_sha256": cluster_sha,
            "kind": WORKER_STATUS_KIND,
            "leaf_count": leaf_count,
            "proxy_guard_accepted_diagnostic": proxy_guard_accepted,
            "proxy_guard_acceptance_required": False,
            "schema_version": SCHEMA_VERSION,
            "stderr": {
                "path": "worker.stderr",
                "sha256": stderr_sha,
                "size_bytes": stderr_size,
            },
            "stream": {
                "path": "worker.jsonl",
                "sha256": stream_sha,
                "size_bytes": stream_size,
            },
            "terminal": terminal,
            "worker_anchor_sha256": worker_anchor(
                cluster_sha, assignment
            ),
            "worker_index": index,
        }
        status_raw = canonical_json_bytes(status)
        _copy_captured(
            stage / "worker-status.json", status_raw, executable=False
        )
        payload = {
            "accepted": False,
            "arithmetic_execution_completed": True,
            "classification": CLASSIFICATION,
            "cluster_plan_sha256": cluster_sha,
            "execution_attested": False,
            "kind": WORKER_BUNDLE_KIND,
            "proxy_guard_accepted_diagnostic": proxy_guard_accepted,
            "proxy_guard_acceptance_required": False,
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "status_sha256": sha256_bytes(status_raw),
            "worker_index": index,
        }
        _copy_captured(
            stage / "bundle.json",
            canonical_json_bytes(payload),
            executable=False,
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {**payload, "output_directory": str(output_directory)}
    except (
        CampaignIOError,
        HurstHybridSourceError,
        OSError,
        ValueError,
    ) as error:
        raise _wrap(error) from error
    finally:
        for descriptor in (h100_fd, roster_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if not published:
            shutil.rmtree(stage, ignore_errors=True)


def reduce_distributed(
    *,
    materialization_directory: Path,
    prepared_directory: Path,
    worker_directories: Sequence[Path],
    output_directory: Path,
) -> dict[str, Any]:
    """Replay eight independent worker bundles and publish the exact scan."""

    hybrid, hybrid_sha, cluster, cluster_sha, handoff = (
        _load_distributed_preparation(
            materialization_directory=materialization_directory,
            prepared_directory=prepared_directory,
        )
    )
    production = hybrid["mode"] == "production"
    try:
        require_azure_measured_worker_for_workload(
            exact_production=production,
            work_bounds=(
                hybrid["source_geometry"]["h100"]["count"],
            ),
        )
    except CampaignIOError as error:
        raise _wrap(error) from error
    if len(worker_directories) != cluster["worker_count"]:
        raise HurstH100AffineClusterError(
            "distributed reducer requires every worker bundle"
        )
    if output_directory.exists() or output_directory.is_symlink():
        raise HurstH100AffineClusterError(
            "distributed reducer output already exists"
        )
    roster_path = (
        materialization_directory
        / hybrid["inputs"]["prime_roster"]["path"]
    )
    roster_raw = (
        _bounded_bytes(
            roster_path,
            SOURCE_PRIME_ROSTER_BYTES,
            "source-prime roster",
        )
        if production
        else None
    )
    prime_roster = _prime_roster_values(
        raw=roster_raw,
        expected_sha256=hybrid["inputs"]["prime_roster"]["sha256"],
        source_upper_exclusive=hybrid["source_geometry"]["h100"][
            "upper_exclusive"
        ],
        production=production,
    )
    by_index: dict[int, tuple[Path, dict[str, Any], bytes]] = {}
    for directory in worker_directories:
        bundle, bundle_raw = _canonical_object_capture(
            directory / "bundle.json",
            "distributed worker bundle",
            maximum=MAX_RECEIPT_BYTES,
        )
        index = bundle.get("worker_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index in by_index
            or bundle.get("kind") != WORKER_BUNDLE_KIND
            or bundle.get("cluster_plan_sha256") != cluster_sha
        ):
            raise HurstH100AffineClusterError(
                "distributed worker bundle index/binding changed"
            )
        by_index[index] = directory, bundle, bundle_raw
    if set(by_index) != set(range(cluster["worker_count"])):
        raise HurstH100AffineClusterError(
            "distributed worker bundle set is incomplete"
        )
    statuses: list[dict[str, Any]] = []
    bundle_pins: list[dict[str, Any]] = []
    for index, assignment in enumerate(cluster["worker_assignments"]):
        directory, bundle, bundle_raw = by_index[index]
        status_path = directory / "worker-status.json"
        status, status_raw = _canonical_object_capture(
            status_path,
            f"distributed worker {index} status",
            maximum=MAX_RECEIPT_BYTES,
        )
        (
            terminal,
            leaf_count,
            stream_sha,
            stream_size,
            proxy_guard_accepted,
        ) = replay_worker_stream(
            stream_path=directory / "worker.jsonl",
            assignment=assignment,
            cluster_plan=cluster,
            cluster_plan_sha256=cluster_sha,
            runner_sha256=hybrid["inputs"]["h100_runner"]["sha256"],
            roster_sha256=hybrid["inputs"]["prime_roster"]["sha256"],
            prime_roster=prime_roster,
        )
        stderr_raw = _bounded_bytes(
            directory / "worker.stderr",
            MAX_STDERR_BYTES,
            f"distributed worker {index} stderr",
        )
        stderr_sha = sha256_bytes(stderr_raw)
        stderr_size = len(stderr_raw)
        expected_status = {
            "cluster_plan_sha256": cluster_sha,
            "kind": WORKER_STATUS_KIND,
            "leaf_count": leaf_count,
            "proxy_guard_accepted_diagnostic": proxy_guard_accepted,
            "proxy_guard_acceptance_required": False,
            "schema_version": SCHEMA_VERSION,
            "stderr": {
                "path": "worker.stderr",
                "sha256": stderr_sha,
                "size_bytes": stderr_size,
            },
            "stream": {
                "path": "worker.jsonl",
                "sha256": stream_sha,
                "size_bytes": stream_size,
            },
            "terminal": terminal,
            "worker_anchor_sha256": worker_anchor(
                cluster_sha, assignment
            ),
            "worker_index": index,
        }
        if status != expected_status:
            raise HurstH100AffineClusterError(
                f"distributed worker {index} status does not replay"
            )
        expected_bundle = {
            "accepted": False,
            "arithmetic_execution_completed": True,
            "classification": CLASSIFICATION,
            "cluster_plan_sha256": cluster_sha,
            "execution_attested": False,
            "kind": WORKER_BUNDLE_KIND,
            "proxy_guard_accepted_diagnostic": proxy_guard_accepted,
            "proxy_guard_acceptance_required": False,
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "status_sha256": sha256_bytes(status_raw),
            "worker_index": index,
        }
        if bundle != expected_bundle:
            raise HurstH100AffineClusterError(
                f"distributed worker {index} bundle does not replay"
            )
        statuses.append(status)
        bundle_pins.append(
            {
                "bundle": {
                    "sha256": sha256_bytes(bundle_raw),
                    "size_bytes": len(bundle_raw),
                },
                "index": index,
                "proxy_guard_accepted_diagnostic": (
                    proxy_guard_accepted
                ),
                "status": {
                    "sha256": sha256_bytes(status_raw),
                    "size_bytes": len(status_raw),
                },
                "stderr": status["stderr"],
                "stream": status["stream"],
            }
        )
    scan = compose_worker_terminals(
        cluster_plan=cluster,
        cpu_state=handoff["outgoing_state"],
        worker_statuses=statuses,
    )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.reducing-",
            dir=output_directory.parent,
        )
    )
    published = False
    try:
        for name in (
            "hybrid-plan.json",
            "cpu-summary.json",
            "cpu-verify.json",
            "cpu-handoff.json",
            "h100-affine-cluster-plan.json",
        ):
            raw = _bounded_bytes(
                prepared_directory / name,
                MAX_INPUT_BYTES,
                f"prepared {name}",
            )
            _copy_captured(stage / name, raw, executable=False)
        scan_raw = canonical_json_bytes(scan)
        _copy_captured(
            stage / "h100-affine-scan.json", scan_raw, executable=False
        )
        payload = {
            "accepted": False,
            "affine_composition_verified": True,
            "algorithm": ALGORITHM,
            "arithmetic_execution_completed": True,
            "classification": CLASSIFICATION,
            "cluster_plan_sha256": cluster_sha,
            "cpu_handoff_sha256": handoff["receipt_chain_sha256"],
            "device_routing_is_attestation": False,
            "final_state": scan["final_state"],
            "hybrid_plan_sha256": hybrid_sha,
            "kind": RESULT_KIND,
            "mode": hybrid["mode"],
            "proxy_guard_acceptance_required": False,
            "proxy_inputs_used_as_sequential_states": False,
            "routing_mode": "distributed_one_h100_per_node",
            "schema_version": SCHEMA_VERSION,
            "semantic_flags": dict(SEMANTIC_FLAGS),
            "source_run_receipt_produced": False,
            "worker_bundles": bundle_pins,
            "worker_count": len(statuses),
            "worker_receipt_chain_sha256": scan[
                "worker_receipt_chain_sha256"
            ],
        }
        result = {
            **payload,
            "result_sha256": hashlib.sha256(
                RESULT_DOMAIN + canonical_json_bytes(payload)
            ).hexdigest(),
        }
        _copy_captured(
            stage / "result.json",
            canonical_json_bytes(result),
            executable=False,
        )
        _fsync_directory(stage)
        _readonly_tree(stage)
        os.replace(stage, output_directory)
        published = True
        _fsync_directory(output_directory.parent)
        return {**result, "output_directory": str(output_directory)}
    except (CampaignIOError, OSError, ValueError) as error:
        raise _wrap(error) from error
    finally:
        if not published:
            shutil.rmtree(stage, ignore_errors=True)


def replay_worker_stream(
    *,
    stream_path: Path,
    assignment: Mapping[str, Any],
    cluster_plan: Mapping[str, Any],
    cluster_plan_sha256: str,
    runner_sha256: str,
    roster_sha256: str,
    prime_roster: Sequence[int],
) -> tuple[dict[str, Any], int, str, int, bool]:
    """Independently replay one retained worker JSONL stream."""

    gpu_range = {
        "count": assignment["count"],
        "lower": assignment["lower"],
        "upper_exclusive": assignment["upper_exclusive"],
    }
    leaf_rows = cluster_plan["leaf_rows"]
    super_rows = cluster_plan["super_shard_rows"]
    anchor = worker_anchor(cluster_plan_sha256, assignment)
    proxy_m = assignment["proxy_incoming_mertens"]
    proxy_q = assignment["proxy_incoming_squarefree"]
    expected_lower = assignment["lower"]
    previous = anchor
    current_m = proxy_m
    current_q = proxy_q
    header: dict[str, Any] | None = None
    terminal: dict[str, Any] | None = None
    leaf_count = 0
    source_fast_leaf_count = 0
    source_fast_super_count = 0
    last_fast_super: int | None = None
    prime_super_index: int | None = None
    expected_selected = 0
    expected_dense = 0
    roster_device_bytes = (
        bisect_right(
            prime_roster,
            math.isqrt(assignment["upper_exclusive"] - 1),
        )
        * 4
    )
    extrema: dict[str, tuple[int, int, int, str] | None] = {
        "hurst_lower": None,
        "hurst_upper": None,
        "squarefree_lower": None,
        "squarefree_upper": None,
    }
    stream_digest = hashlib.sha256()
    stream_size = 0
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(stream_path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise HurstH100AffineClusterError(
                "worker JSONL must be one unlinked regular file"
            )
        source: BinaryIO
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            while True:
                raw = source.readline(MAX_JSONL_LINE_BYTES + 1)
                if not raw:
                    break
                if len(raw) > MAX_JSONL_LINE_BYTES or not raw.endswith(b"\n"):
                    raise HurstH100AffineClusterError(
                        "worker JSONL line framing is malformed"
                    )
                stream_digest.update(raw)
                stream_size += len(raw)
                record = _json_line(raw, "retained H100 receipt")
                kind = record.get("record")
                if header is None:
                    if kind != "header":
                        raise HurstH100AffineClusterError(
                            "retained H100 header is missing"
                        )
                    header = record
                    _validate_header(
                        header,
                        gpu_range=gpu_range,
                        leaf_rows=leaf_rows,
                        super_rows=super_rows,
                        runner_sha256=runner_sha256,
                        roster_sha256=roster_sha256,
                        roster_device_bytes=roster_device_bytes,
                    )
                    continue
                if kind == "terminal":
                    if terminal is not None:
                        raise HurstH100AffineClusterError(
                            "duplicate retained H100 terminal"
                        )
                    terminal = record
                    continue
                if terminal is not None or kind != "leaf":
                    raise HurstH100AffineClusterError(
                        "retained H100 record order changed"
                    )
                candidate_super = (
                    expected_lower - assignment["lower"]
                ) // super_rows
                if candidate_super != prime_super_index:
                    super_lower = (
                        assignment["lower"] + candidate_super * super_rows
                    )
                    super_count = min(
                        super_rows,
                        assignment["upper_exclusive"] - super_lower,
                    )
                    fast = super_count >= math.isqrt(
                        super_lower + super_count - 1
                    )
                    expected_selected, expected_dense = (
                        _expected_selected_prime_counts(
                            prime_roster,
                            super_lower=super_lower,
                            super_count=super_count,
                            source_fast_path=fast,
                        )
                    )
                    prime_super_index = candidate_super
                (
                    current_m,
                    current_q,
                    previous,
                    bounds,
                    source_fast,
                    super_index,
                ) = _validate_leaf(
                    record,
                    index=leaf_count,
                    expected_lower=expected_lower,
                    expected_previous=previous,
                    expected_mertens=current_m,
                    expected_squarefree=current_q,
                    root_mertens=proxy_m,
                    root_squarefree=proxy_q,
                    source_lower=assignment["lower"],
                    leaf_rows=leaf_rows,
                    super_rows=super_rows,
                    source_upper=assignment["upper_exclusive"],
                    executable_sha256=runner_sha256,
                    roster_sha256=roster_sha256,
                    expected_selected_prime_count=expected_selected,
                    expected_dense_prime_count=expected_dense,
                )
                for name, candidate in bounds.items():
                    extrema[name] = _select_extreme(
                        extrema[name],
                        candidate,
                        maximum=name.endswith("lower"),
                    )
                if source_fast:
                    source_fast_leaf_count += 1
                    if super_index != last_fast_super:
                        source_fast_super_count += 1
                        last_fast_super = super_index
                expected_lower = record["upper_exclusive"]
                leaf_count += 1
        final_metadata = os.fstat(descriptor)
    except (HurstHybridSourceError, OSError) as error:
        raise _wrap(error) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        stream_size != metadata.st_size
        or final_metadata.st_size != metadata.st_size
        or final_metadata.st_mtime_ns != metadata.st_mtime_ns
        or final_metadata.st_ctime_ns != metadata.st_ctime_ns
    ):
        raise HurstH100AffineClusterError(
            "worker JSONL changed during replay"
        )
    if (
        header is None
        or terminal is None
        or expected_lower != assignment["upper_exclusive"]
    ):
        raise HurstH100AffineClusterError(
            "retained H100 stream is incomplete"
        )
    hurst_lower = extrema["hurst_lower"]
    hurst_upper = extrema["hurst_upper"]
    squarefree_lower = extrema["squarefree_lower"]
    squarefree_upper = extrema["squarefree_upper"]
    if (
        hurst_lower is None
        or hurst_upper is None
        or squarefree_lower is None
        or squarefree_upper is None
    ):
        raise HurstH100AffineClusterError(
            "worker stream omitted an affine extremum"
        )
    proxy_guard_accepted = (
        hurst_lower[0] <= proxy_m <= hurst_upper[0]
        and squarefree_lower[0] <= proxy_q <= squarefree_upper[0]
    )
    if (
        terminal.get("incoming_mertens") != proxy_m
        or terminal.get("incoming_squarefree") != proxy_q
        or terminal.get("outgoing_mertens") != current_m
        or terminal.get("outgoing_squarefree") != current_q
        or terminal.get("delta_mertens") != current_m - proxy_m
        or terminal.get("delta_squarefree") != current_q - proxy_q
    ):
        raise HurstH100AffineClusterError(
            "worker terminal proxy recurrence does not replay"
        )
    # The existing strict terminal checker also verifies that its incoming
    # state lies in the accumulated guard.  For an independent affine summary
    # the proxy is not mathematically required to be admissible.  Validate all
    # terminal geometry, deltas, counters, flags, leaf root, and extrema using
    # a synthetic in-guard state while leaving the retained terminal bytes
    # untouched.  The original proxy recurrence was already replayed leaf by
    # leaf above; the reducer separately checks the exact derived state.
    synthetic_m = max(hurst_lower[0], min(0, hurst_upper[0]))
    synthetic_q = max(0, squarefree_lower[0])
    if synthetic_q > squarefree_upper[0]:
        raise HurstH100AffineClusterError(
            "worker squarefree affine guard is empty"
        )
    terminal_for_structural_check = dict(terminal)
    terminal_for_structural_check.update(
        {
            "incoming_mertens": synthetic_m,
            "outgoing_mertens": synthetic_m
            + terminal["delta_mertens"],
            "incoming_squarefree": synthetic_q,
            "outgoing_squarefree": synthetic_q
            + terminal["delta_squarefree"],
        }
    )
    try:
        _validate_terminal(
            terminal_for_structural_check,
            gpu_range=gpu_range,
            leaf_rows=leaf_rows,
            super_rows=super_rows,
            leaf_count=leaf_count,
            first_mertens=synthetic_m,
            first_squarefree=synthetic_q,
            final_mertens=(
                synthetic_m + terminal["delta_mertens"]
            ),
            final_squarefree=(
                synthetic_q + terminal["delta_squarefree"]
            ),
            final_leaf=previous,
            extrema=extrema,
            source_fast_leaf_count=source_fast_leaf_count,
            source_fast_super_shard_count=source_fast_super_count,
        )
    except HurstHybridSourceError as error:
        raise _wrap(error) from error
    return (
        terminal,
        leaf_count,
        stream_digest.hexdigest(),
        stream_size,
        proxy_guard_accepted,
    )


def verify(
    *,
    materialization_directory: Path,
    output_directory: Path,
    replay_streams: bool = True,
) -> dict[str, Any]:
    """Replay immutable controls, CPU handoff, and optionally every JSONL leaf."""

    try:
        hybrid_plan, hybrid_sha = _load_plan(materialization_directory)
    except HurstHybridSourceError as error:
        raise _wrap(error) from error
    retained_hybrid = _bounded_bytes(
        output_directory / "hybrid-plan.json",
        MAX_INPUT_BYTES,
        "retained hybrid plan",
    )
    if retained_hybrid != canonical_json_bytes(hybrid_plan):
        raise HurstH100AffineClusterError(
            "retained hybrid plan differs from materialization"
        )
    cluster_plan = _canonical_object(
        output_directory / "h100-affine-cluster-plan.json",
        "cluster plan",
    )
    cluster_sha = sha256_bytes(canonical_json_bytes(cluster_plan))
    handoff = _canonical_object(
        output_directory / "cpu-handoff.json", "CPU handoff"
    )
    if (
        cluster_plan.get("hybrid_plan_sha256") != hybrid_sha
        or cluster_plan.get("cpu_handoff_sha256")
        != handoff.get("receipt_chain_sha256")
    ):
        raise HurstH100AffineClusterError(
            "cluster plan lost its hybrid/CPU binding"
        )

    summary_raw = _bounded_bytes(
        output_directory / "cpu-summary.json",
        MAX_RECEIPT_BYTES,
        "CPU summary",
    )
    verify_raw = _bounded_bytes(
        output_directory / "cpu-verify.json",
        MAX_RECEIPT_BYTES,
        "CPU verify",
    )
    try:
        summary = load_decimal_json_bytes(
            summary_raw, label="retained CPU summary"
        )
        checked = load_decimal_json_bytes(
            verify_raw, label="retained CPU verify"
        )
    except EvidenceError as error:
        raise _wrap(error) from error
    if not isinstance(summary, dict) or not isinstance(checked, dict):
        raise HurstH100AffineClusterError(
            "retained CPU receipt is not an object"
        )
    cpu_range = hybrid_plan["source_geometry"]["cpu"]
    summary_delta = validate_runner_receipt(
        summary,
        phase="summary",
        shard_lower=cpu_range["lower"],
        shard_upper=cpu_range["upper_exclusive"],
        segment_size=hybrid_plan["cpu"]["segment_rows"],
    )
    verify_delta = validate_runner_receipt(
        checked,
        phase="verify",
        shard_lower=cpu_range["lower"],
        shard_upper=cpu_range["upper_exclusive"],
        segment_size=hybrid_plan["cpu"]["segment_rows"],
        expected_incoming=(0, 0, 0, 0),
    )
    if (
        summary_delta != verify_delta
        or summary["row_sha256"] != checked["row_sha256"]
    ):
        raise HurstH100AffineClusterError(
            "retained CPU summary/verify pair differs"
        )
    cpu_state = tuple(verify_delta)
    expected_handoff = _cpu_handoff(
        plan_sha256=hybrid_sha,
        geometry=hybrid_plan["source_geometry"],
        runner_sha256=hybrid_plan["inputs"]["cpu_runner"]["sha256"],
        summary_raw=summary_raw,
        verify_raw=verify_raw,
        report=checked,
        outgoing=cpu_state,
    )
    if handoff != expected_handoff:
        raise HurstH100AffineClusterError(
            "retained CPU handoff does not replay"
        )

    roster_path = (
        materialization_directory
        / hybrid_plan["inputs"]["prime_roster"]["path"]
    )
    production = hybrid_plan["mode"] == "production"
    roster_raw = (
        _bounded_bytes(
            roster_path,
            SOURCE_PRIME_ROSTER_BYTES,
            "source-prime roster",
        )
        if production
        else None
    )
    prime_roster = _prime_roster_values(
        raw=roster_raw,
        expected_sha256=hybrid_plan["inputs"]["prime_roster"]["sha256"],
        source_upper_exclusive=hybrid_plan["source_geometry"]["h100"][
            "upper_exclusive"
        ],
        production=production,
    )
    statuses: list[dict[str, Any]] = []
    expected_worker_pins: list[dict[str, Any]] = []
    for assignment in cluster_plan["worker_assignments"]:
        index = assignment["index"]
        status_path = (
            output_directory
            / f"workers/worker-{index:02d}-status.json"
        )
        status = _canonical_object(status_path, f"worker {index} status")
        stream_path = (
            output_directory / f"workers/worker-{index:02d}.jsonl"
        )
        stderr_path = (
            output_directory / f"workers/worker-{index:02d}.stderr"
        )
        stderr_sha, stderr_size = hash_file_once(stderr_path)
        if status.get("stderr") != {
            "path": f"workers/worker-{index:02d}.stderr",
            "sha256": stderr_sha,
            "size_bytes": stderr_size,
        }:
            raise HurstH100AffineClusterError(
                f"worker {index} stderr pin changed"
            )
        if replay_streams:
            (
                terminal,
                leaf_count,
                stream_sha,
                stream_size,
                _proxy_guard_accepted,
            ) = replay_worker_stream(
                stream_path=stream_path,
                assignment=assignment,
                cluster_plan=cluster_plan,
                cluster_plan_sha256=cluster_sha,
                runner_sha256=hybrid_plan["inputs"]["h100_runner"]["sha256"],
                roster_sha256=hybrid_plan["inputs"]["prime_roster"]["sha256"],
                prime_roster=prime_roster,
            )
            if (
                status.get("terminal") != terminal
                or status.get("leaf_count") != leaf_count
            ):
                raise HurstH100AffineClusterError(
                    f"worker {index} status differs from JSONL replay"
                )
        else:
            stream_sha, stream_size = hash_file_once(stream_path)
        if status.get("stream") != {
            "path": f"workers/worker-{index:02d}.jsonl",
            "sha256": stream_sha,
            "size_bytes": stream_size,
        }:
            raise HurstH100AffineClusterError(
                f"worker {index} stream pin changed"
            )
        statuses.append(status)
        status_sha, status_size = hash_file_once(status_path)
        expected_worker_pins.append(
            {
                "index": index,
                "status": {
                    "path": f"workers/worker-{index:02d}-status.json",
                    "sha256": status_sha,
                    "size_bytes": status_size,
                },
                "stderr": status["stderr"],
                "stream": status["stream"],
            }
        )
    expected_scan = compose_worker_terminals(
        cluster_plan=cluster_plan,
        cpu_state=cpu_state,
        worker_statuses=statuses,
    )
    if _canonical_object(
        output_directory / "h100-affine-scan.json", "affine scan"
    ) != expected_scan:
        raise HurstH100AffineClusterError(
            "retained affine scan does not replay"
        )
    result = _canonical_object(output_directory / "result.json", "result")
    payload = dict(result)
    digest = payload.pop("result_sha256", None)
    if digest != hashlib.sha256(
        RESULT_DOMAIN + canonical_json_bytes(payload)
    ).hexdigest():
        raise HurstH100AffineClusterError("result digest does not replay")
    expected_receipt_pins: dict[str, Any] = {}
    for name in (
        "cpu-summary.json",
        "cpu-verify.json",
        "cpu-handoff.json",
        "h100-affine-cluster-plan.json",
        "h100-affine-scan.json",
    ):
        artifact_sha, artifact_size = hash_file_once(output_directory / name)
        expected_receipt_pins[name] = {
            "path": name,
            "sha256": artifact_sha,
            "size_bytes": artifact_size,
        }
    if (
        result.get("cluster_plan_sha256") != cluster_sha
        or result.get("final_state") != expected_scan["final_state"]
        or result.get("worker_receipt_chain_sha256")
        != expected_scan["worker_receipt_chain_sha256"]
        or result.get("proxy_inputs_used_as_sequential_states") is not False
        or result.get("device_routing_is_attestation") is not False
        or result.get("semantic_flags") != SEMANTIC_FLAGS
        or result.get("receipt_artifacts") != expected_receipt_pins
        or result.get("worker_receipts") != expected_worker_pins
        or result.get("worker_count") != len(statuses)
        or result.get("accepted") is not False
        or result.get("affine_composition_verified") is not True
        or result.get("arithmetic_execution_completed") is not True
        or result.get("source_run_receipt_produced") is not False
    ):
        raise HurstH100AffineClusterError(
            "result summary differs from replayed controls"
        )
    return {
        "accepted": True,
        "affine_composition_verified": True,
        "arithmetic_execution_completed": True,
        "classification": (
            "independent_receipt_replay_not_source_semantics_or_attestation"
        ),
        "final_state": expected_scan["final_state"],
        "proxy_inputs_used_as_sequential_states": False,
        "stream_replay_performed": replay_streams,
        "worker_count": len(statuses),
        "worker_receipt_chain_sha256": expected_scan[
            "worker_receipt_chain_sha256"
        ],
    }


__all__ = [
    "ALGORITHM",
    "CLASSIFICATION",
    "HurstH100AffineClusterError",
    "PRODUCTION_WORKER_COUNT",
    "build_cluster_plan",
    "compose_worker_terminals",
    "partition_affine_range",
    "prepare_distributed",
    "proxy_squarefree_state",
    "reduce_distributed",
    "replay_worker_stream",
    "run",
    "run_distributed_worker",
    "verify",
    "worker_anchor",
    "worker_command",
]
