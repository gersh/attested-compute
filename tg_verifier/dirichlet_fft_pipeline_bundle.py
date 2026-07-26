# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Typed, fail-closed replay for one fixed-q Dirichlet FFT pipeline target.

The large-q source supervisor enumerates fixed-modulus batches containing at
most 64 consecutive ordinates.  The persistent pipeline emits a compact JSON
receipt for such a batch, but a bare SHA-256 of that receipt is not a typed
handoff: it does not show that the named file is a pipeline receipt, that its
nested files still exist, or that it covers the expected source-grid target.

This module closes that *receipt-typing* seam.  It independently reparses and
hashes the pipeline receipt and every retained artifact, reconstructs the
composition/control inventory from the original jobs, validates the exact
composer/FFT/consumer receipt shapes, reparses the event stream and root
artifact, and binds the result to one ``fft_batch_descriptor`` from an
authenticated source-supervisor contract.  It also extracts and hashes the
canonical lattice payload inside every ``TGDLATI1`` so the t-major admission
adapter can require byte identity with independently authenticated cache rows.

It deliberately does not claim an independent replay of the discarded
``TGDAFFI1``/``TGDAFFO1`` arithmetic, zero completeness, a Turing argument, or
Platt's theorem.  Those facts are not recoverable from compact stream hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_stage import (
    ALGORITHM_ID as ALLCHARS_ALGORITHM_ID,
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    canonical_component_orders,
    group_order,
    modulus_butterflies,
)
from tg_verifier.dirichlet_campaign import primitive_character_count
from tg_verifier.dirichlet_largeq_pipeline import (
    ALGORITHM_ID as PIPELINE_ALGORITHM_ID,
    ATOM_ID,
    AUTHOR,
    RECEIPT_SCHEMA as PIPELINE_RECEIPT_SCHEMA,
    validate_control_alignment,
)
from tg_verifier.dirichlet_lattice_stage import (
    FORMAT_VERSION as LATTICE_FORMAT_VERSION,
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    INPUT_ITEM as LATTICE_INPUT_ITEM,
    INPUT_MAGIC as LATTICE_INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    SOURCE_SAMPLE_DENOMINATOR as LATTICE_T_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR as LATTICE_T_STEP_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
)
from tg_verifier.dirichlet_residue_composition import (
    ALGORITHM_ID as COMPOSITION_ALGORITHM_ID,
    ATOM_ID as COMPOSITION_ATOM_ID,
    AUTHOR as COMPOSITION_AUTHOR,
    CERTIFIED_CLASSIFICATION,
    CHECKER_ID as COMPOSITION_CHECKER_ID,
    FRAMED_REQUEST_SCHEMA,
    RECEIPT_SCHEMA as COMPOSITION_RECEIPT_SCHEMA,
    SYNTHETIC_CLASSIFICATION,
    ResiduePlanCache,
    _validate_certificate_chain,
    canonical_json_bytes,
    load_job,
)
from tg_verifier.dirichlet_root_number_stage import (
    CONVENTION_SHA256 as ROOT_CONVENTION_SHA256,
    ROOT_ALGORITHM_ID,
    read_root_artifact_bytes,
)
from tg_verifier.dirichlet_source_supervisor import (
    SOURCE_CONTRACT_CLASSIFICATION,
    STRUCTURAL_KAT_CLASSIFICATION,
    fft_batch_descriptor,
    load_contract,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    ALGORITHM_ID as CONSUMER_ALGORITHM_ID,
    COMPACT_EVENT_SCHEMA,
    COMPACT_EVENT_STORAGE_MODE,
    EVENT_FILE_SCHEMA,
    EVENT_SCHEMA,
    RAW_EVENT_STORAGE_MODE,
    RECEIPT_SCHEMA as CONSUMER_RECEIPT_SCHEMA,
    validate_compact_event_summary,
    validate_control,
)


ALGORITHM_ID = "platt-dirichlet-typed-fft-pipeline-receipt-bundle-v1"
BUNDLE_SCHEMA = "sparkinterval.tg.dirichlet_fft_pipeline_bundle.v1"
REPLAY_SCHEMA = "sparkinterval.tg.dirichlet_fft_pipeline_bundle.replay.v1"
CLASSIFICATION = "typed_fft_pipeline_component_receipt_not_zero_closure"
MAXIMUM_JSON_BYTES = 16 * 1024 * 1024
MAXIMUM_CONTROL_BYTES = 256 * 1024 * 1024
MAXIMUM_EVENT_LINE_BYTES = 4 * 1024 * 1024
MAXIMUM_LATTICE_INPUT_BYTES = 16 * 1024 * 1024
SOURCE_T_DENOMINATOR = 64
SOURCE_T_STEP_NUMERATOR = 5

_HEX = frozenset("0123456789abcdef")


class DirichletFFTPipelineBundleError(RuntimeError):
    """A retained pipeline receipt or its fixed-q binding failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletFFTPipelineBundleError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(f"{label} is not a lowercase SHA-256 digest")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{label} is below {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} is above {maximum}")
    return value


def _measurement(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be numeric")
    if not math.isfinite(value) or value < 0:
        _fail(f"{label} must be finite and nonnegative")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for key, value in pairs:
        if key in answer:
            _fail(f"duplicate JSON key: {key}")
        answer[key] = value
    return answer


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _parse_json(raw: bytes, *, label: str, canonical: bool) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletFFTPipelineBundleError(
            f"invalid {label} JSON"
        ) from error
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    if canonical and canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    if not canonical and (
        not raw.endswith(b"\n") or b"\n" in raw[:-1]
    ):
        _fail(f"{label} is not exactly one newline-terminated JSON record")
    return value


def _safe_read(
    path: Path,
    *,
    label: str,
    maximum_bytes: int | None = None,
    retain_bytes: bool = True,
) -> tuple[bytes | None, dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletFFTPipelineBundleError(
            f"cannot open {label} without following a final symlink: {path}"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode):
            _fail(f"{label} is not a regular file")
        if status.st_size <= 0:
            _fail(f"{label} is empty")
        if maximum_bytes is not None and status.st_size > maximum_bytes:
            _fail(f"{label} exceeds {maximum_bytes} bytes")
        digest = hashlib.sha256()
        size = 0
        retained = bytearray() if retain_bytes else None
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
            if retained is not None:
                retained.extend(block)
    return (bytes(retained) if retained is not None else None), {
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _artifact(
    record: object,
    *,
    label: str,
    maximum_bytes: int | None = None,
    retain_bytes: bool = True,
) -> tuple[Path, bytes | None, dict[str, Any]]:
    if not isinstance(record, dict) or set(record) != {
        "path",
        "sha256",
        "size_bytes",
    }:
        _fail(f"{label} is not an exact artifact record")
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        _fail(f"{label}.path is malformed")
    path = Path(raw_path)
    if not path.is_absolute() or str(path.resolve()) != raw_path:
        _fail(f"{label}.path is not an absolute normalized path")
    expected_sha = _digest(record.get("sha256"), f"{label}.sha256")
    expected_size = _integer(
        record.get("size_bytes"), f"{label}.size_bytes", minimum=1
    )
    raw, observed = _safe_read(
        path,
        label=label,
        maximum_bytes=maximum_bytes,
        retain_bytes=retain_bytes,
    )
    if (
        observed["sha256"] != expected_sha
        or observed["size_bytes"] != expected_size
        or observed["path"] != raw_path
    ):
        _fail(f"{label} hash, size, or normalized path differs")
    return path, raw, observed


def _self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail(f"{label} self-hash differs")
    return claimed


def _merkle_receipts(digests: Sequence[str]) -> str:
    if not digests:
        _fail("cannot Merkle-hash no composition receipts")
    level = [hashlib.sha256(bytes.fromhex(value)).digest() for value in digests]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def _job_input_merkle(job: Any) -> str:
    leaves: list[bytes] = []
    for frame in job.frames:
        for artifact in (
            frame.lattice_input,
            frame.lattice_output,
            frame.finite_recovery,
            frame.lattice_certificate,
            frame.lattice_replay,
            frame.lattice_stage_receipt,
        ):
            if artifact is not None:
                leaves.append(
                    hashlib.sha256(bytes.fromhex(artifact.sha256)).digest()
                )
    if not leaves:
        _fail("composition job has no upstream artifact leaves")
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256(leaves[index] + leaves[index + 1]).digest()
            for index in range(0, len(leaves), 2)
        ]
    return leaves[0].hex()


def _revalidate_job_artifacts(job: Any) -> None:
    for frame_index, frame in enumerate(job.frames):
        for name, artifact in (
            ("lattice_input", frame.lattice_input),
            ("lattice_output", frame.lattice_output),
            ("finite_recovery", frame.finite_recovery),
            ("lattice_certificate", frame.lattice_certificate),
            ("lattice_replay", frame.lattice_replay),
            ("lattice_stage_receipt", frame.lattice_stage_receipt),
        ):
            if artifact is None:
                continue
            _raw, record = _safe_read(
                artifact.path,
                label=f"composition frame {frame_index} {name}",
                retain_bytes=False,
            )
            if (
                record["sha256"] != artifact.sha256
                or record["size_bytes"] != artifact.size_bytes
            ):
                _fail(
                    f"composition frame {frame_index} {name} changed "
                    "during typed replay"
                )


def _lattice_cache_row_bindings(
    jobs: Sequence[Any],
    *,
    first_t_index: int,
) -> tuple[tuple[int, str], ...]:
    """Recover the exact cache-row payload identity from every TGDLATI1.

    A composition job hashes the complete q-specific ``TGDLATI1`` file.  The
    t-major cache instead hashes only its shared one-MiB lattice payload.  This
    bounded replay extracts and hashes that canonical middle region so a later
    adapter can prove that a typed fixed-q bundle consumed the authenticated
    cache rows assigned to the same source ordinates.
    """

    row_bytes = LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
    bindings: list[tuple[int, str]] = []
    expected_t_index = first_t_index
    for job_index, job in enumerate(jobs):
        for frame_index, frame in enumerate(job.frames):
            raw, record = _safe_read(
                frame.lattice_input.path,
                label=(
                    f"composition job {job_index} frame {frame_index} "
                    "lattice input"
                ),
                maximum_bytes=MAXIMUM_LATTICE_INPUT_BYTES,
            )
            assert raw is not None
            if (
                record["sha256"] != frame.lattice_input.sha256
                or record["size_bytes"] != frame.lattice_input.size_bytes
            ):
                _fail("lattice input changed during cache-row identity replay")
            if len(raw) < LATTICE_INPUT_HEADER.size + row_bytes:
                _fail("lattice input is too short for one canonical cache row")
            (
                magic,
                version,
                rows,
                degree,
                reserved0,
                t_numerator,
                t_denominator,
                input_count,
                lattice_count,
                reserved1,
            ) = LATTICE_INPUT_HEADER.unpack_from(raw)
            expected_size = (
                LATTICE_INPUT_HEADER.size
                + row_bytes
                + input_count * LATTICE_INPUT_ITEM.size
            )
            if (
                magic != LATTICE_INPUT_MAGIC
                or version != LATTICE_FORMAT_VERSION
                or rows != LATTICE_ROWS
                or degree != TAYLOR_DEGREE
                or reserved0 != 0
                or reserved1 != 0
                or t_numerator
                != expected_t_index * LATTICE_T_STEP_NUMERATOR
                or t_denominator != LATTICE_T_DENOMINATOR
                or input_count <= 0
                or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
                or len(raw) != expected_size
            ):
                _fail("lattice input cache-row geometry or source ordinate differs")
            payload_start = LATTICE_INPUT_HEADER.size
            payload = raw[payload_start : payload_start + row_bytes]
            bindings.append(
                (expected_t_index, hashlib.sha256(payload).hexdigest())
            )
            expected_t_index += 1
    if not bindings:
        _fail("pipeline replay contains no lattice cache rows")
    return tuple(bindings)


@dataclass(frozen=True)
class _FramedRequest:
    job_path: Path
    receipt_path: Path


@dataclass(frozen=True)
class PipelineReplay:
    pipeline_receipt_file: dict[str, Any]
    pipeline_receipt_sha256: str
    q: int
    first_t_index: int
    t_index_stop_exclusive: int
    frame_count: int
    slice_count: int
    value_count: int
    radix2_butterflies: int
    event_count: int
    indeterminate_sample_count: int
    all_composition_inputs_certified: bool
    lattice_cache_rows: tuple[tuple[int, str], ...]


def _framed_requests(raw: bytes, *, base: Path) -> tuple[_FramedRequest, ...]:
    requests: list[_FramedRequest] = []
    for index, line in enumerate(raw.splitlines(keepends=True)):
        value = _parse_json(
            line, label=f"composition control {index}", canonical=True
        )
        if (
            set(value) != {"schema", "schema_version", "job", "receipt"}
            or value.get("schema") != FRAMED_REQUEST_SCHEMA
            or value.get("schema_version") != 1
        ):
            _fail(f"composition control {index} schema differs")
        paths: list[Path] = []
        for name in ("job", "receipt"):
            raw_path = value.get(name)
            if (
                not isinstance(raw_path, str)
                or not raw_path
                or "\x00" in raw_path
            ):
                _fail(f"composition control {index} {name} path is malformed")
            path = Path(raw_path)
            if not path.is_absolute():
                path = base / path
            paths.append(path.resolve())
        requests.append(_FramedRequest(paths[0], paths[1]))
    if not requests:
        _fail("composition control stream is empty")
    if len({row.receipt_path for row in requests}) != len(requests):
        _fail("composition receipt paths are not unique")
    return tuple(requests)


def _consumer_controls(raw: bytes) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(raw.splitlines(keepends=True)):
        value = _parse_json(
            line, label=f"consumer control {index}", canonical=True
        )
        try:
            checked = validate_control(
                value,
                expected_frame_index=index,
                expected_root_number_mode=ROOT_ALGORITHM_ID,
            )
        except Exception as error:
            raise DirichletFFTPipelineBundleError(
                f"consumer control {index} failed typed replay: {error}"
            ) from error
        rows.append(dict(checked))
    if not rows:
        _fail("consumer control stream is empty")
    return tuple(rows)


def _validate_binary64_hex_box(value: object, *, label: str) -> None:
    if not isinstance(value, list) or len(value) != 4:
        _fail(f"{label} must contain four binary64 hexadecimal values")
    endpoints: list[float] = []
    for index, text in enumerate(value):
        if not isinstance(text, str):
            _fail(f"{label}[{index}] is not text")
        try:
            endpoint = float.fromhex(text)
        except ValueError as error:
            raise DirichletFFTPipelineBundleError(
                f"{label}[{index}] is not binary64 hexadecimal"
            ) from error
        if not math.isfinite(endpoint) or endpoint.hex() != text:
            _fail(f"{label}[{index}] is not canonical finite binary64")
        endpoints.append(endpoint)
    if endpoints[0] > endpoints[1] or endpoints[2] > endpoints[3]:
        _fail(f"{label} is not an ordered complex rectangle")


def _validate_composition_receipt(
    path: Path,
    *,
    job: Any,
    allow_synthetic_kat: bool,
) -> dict[str, Any]:
    raw, _record = _safe_read(
        path, label="composition receipt", maximum_bytes=MAXIMUM_JSON_BYTES
    )
    assert raw is not None
    value = _parse_json(raw, label="composition receipt", canonical=True)
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "checker_id",
        "classification",
        "job",
        "upstream_artifact_merkle_sha256",
        "q",
        "M",
        "first_t_numerator",
        "t_denominator",
        "t_step_numerator",
        "batch_count",
        "group_order",
        "component_orders",
        "value_count",
        "output",
        "q_to_the_minus_s_factors",
        "factor_backend",
        "composition_backend",
        "bounded_working_set",
        "elapsed_seconds",
        "values_per_second",
        "decisions",
        "receipt_sha256",
    }
    if set(value) != required:
        _fail("composition receipt fields differ")
    _self_hash(value, "receipt_sha256", label="composition receipt")
    classification = (
        "certified_residue_composition_adapter_only"
        if job.classification == CERTIFIED_CLASSIFICATION
        else "synthetic_residue_composition_kat_only"
    )
    if job.classification == SYNTHETIC_CLASSIFICATION and not allow_synthetic_kat:
        _fail("synthetic composition receipt requires explicit KAT authorization")
    orders = canonical_component_orders(job.q)
    order = math.prod(orders)
    batch_count = len(job.frames)
    plan = ResiduePlanCache().get(job.q)
    expected_m: int | None = None
    if job.classification == CERTIFIED_CLASSIFICATION:
        for index, frame in enumerate(job.frames):
            try:
                m = _validate_certificate_chain(
                    frame,
                    plan=plan,
                    expected_t_numerator=(
                        job.first_t_numerator
                        + index * job.t_step_numerator
                    ),
                )
            except Exception as error:
                raise DirichletFFTPipelineBundleError(
                    "composition input certificate chain replay failed"
                ) from error
            expected_m = m if expected_m is None else expected_m
            if m != expected_m:
                _fail("composition input certificate M changes within a batch")
    else:
        expected_m = _integer(
            value.get("M"), "synthetic composition M", minimum=1
        )
    if (
        value.get("schema") != COMPOSITION_RECEIPT_SCHEMA
        or value.get("schema_version") != 1
        or value.get("author") != COMPOSITION_AUTHOR
        or value.get("atom_id") != COMPOSITION_ATOM_ID
        or value.get("algorithm_id") != COMPOSITION_ALGORITHM_ID
        or value.get("checker_id") != COMPOSITION_CHECKER_ID
        or value.get("classification") != classification
        or value.get("job")
        != {"path": str(job.path), "sha256": job.sha256}
        or value.get("upstream_artifact_merkle_sha256")
        != _job_input_merkle(job)
        or value.get("M") != expected_m
        or value.get("q") != job.q
        or value.get("first_t_numerator") != job.first_t_numerator
        or value.get("t_denominator") != job.t_denominator
        or value.get("t_step_numerator") != job.t_step_numerator
        or value.get("batch_count") != batch_count
        or value.get("group_order") != order
        or value.get("component_orders") != list(orders)
        or value.get("value_count") != batch_count * order
    ):
        _fail("composition receipt identity or exact work differs")
    output = value.get("output")
    if (
        not isinstance(output, dict)
        or set(output)
        != {
            "path",
            "sha256",
            "size_bytes",
            "streamed_fifo",
            "streamed_framed_service",
            "magic",
        }
        or output.get("path") != "<framed-stdout>"
        or output.get("magic") != "TGDAFFI1"
        or output.get("streamed_fifo") is not False
        or output.get("streamed_framed_service") is not True
        or output.get("size_bytes")
        != INPUT_HEADER.size + batch_count * order * COMPLEX_INTERVAL.size
    ):
        _fail("composition receipt framed output contract differs")
    _digest(output.get("sha256"), "composition TGDAFFI1 frame digest")
    factors = value.get("q_to_the_minus_s_factors")
    if not isinstance(factors, list) or len(factors) != batch_count:
        _fail("composition factor inventory length differs")
    for index, factor in enumerate(factors):
        if (
            not isinstance(factor, dict)
            or set(factor) != {"t_numerator", "binary64_hex"}
            or factor.get("t_numerator")
            != job.first_t_numerator + index * job.t_step_numerator
        ):
            _fail(f"composition factor {index} identity differs")
        _validate_binary64_hex_box(
            factor.get("binary64_hex"),
            label=f"composition factor {index}",
        )
    factor_backend = value.get("factor_backend")
    if (
        not isinstance(factor_backend, dict)
        or set(factor_backend)
        != {"library", "version", "precision_bits", "angle_enclosure"}
        or factor_backend.get("library") != "MPFR"
        or not isinstance(factor_backend.get("version"), str)
        or _integer(
            factor_backend.get("precision_bits"),
            "composition factor precision",
            minimum=128,
        )
        < 128
        or factor_backend.get("angle_enclosure")
        != "directed log/mul/div plus global trig Lipschitz bound"
    ):
        _fail("composition factor backend differs")
    composition_backend = value.get("composition_backend")
    if (
        not isinstance(composition_backend, dict)
        or set(composition_backend)
        != {"name", "ieee_binary64_nextafter_outward", "numpy_version"}
        or composition_backend.get("name") not in {"numpy", "scalar"}
        or composition_backend.get("ieee_binary64_nextafter_outward") is not True
        or (
            composition_backend.get("numpy_version") is not None
            and not isinstance(composition_backend.get("numpy_version"), str)
        )
    ):
        _fail("composition interval backend differs")
    working = value.get("bounded_working_set")
    if (
        not isinstance(working, dict)
        or set(working)
        != {
            "frames_resident",
            "binary_interval_payload_bytes",
            "residue_position_bytes",
            "conservative_backend_payload_bound_bytes",
            "bound_note",
            "batch_count_bound",
            "campaign_outputs_retained",
        }
        or working.get("frames_resident") != 1
        or working.get("binary_interval_payload_bytes")
        != order * COMPLEX_INTERVAL.size
        or working.get("campaign_outputs_retained") is not False
        or _integer(
            working.get("batch_count_bound"),
            "composition batch bound",
            minimum=batch_count,
        )
        < batch_count
    ):
        _fail("composition bounded-working-set receipt differs")
    _integer(
        working.get("residue_position_bytes"),
        "composition residue map bytes",
        minimum=1,
    )
    _integer(
        working.get("conservative_backend_payload_bound_bytes"),
        "composition working-set bound",
        minimum=working["binary_interval_payload_bytes"],
    )
    if not isinstance(working.get("bound_note"), str):
        _fail("composition working-set note is malformed")
    _measurement(value.get("elapsed_seconds"), "composition elapsed seconds")
    if _measurement(
        value.get("values_per_second"), "composition values per second"
    ) <= 0:
        _fail("composition values per second must be positive")
    if value.get("decisions") != {
        "upstream_hashes_verified_before_output": True,
        "exact_q_a_row_t_lockstep_verified": True,
        "certificate_and_replay_chain_verified": (
            job.classification == CERTIFIED_CLASSIFICATION
        ),
        "outward_interval_composition_completed": True,
        "canonical_crt_residue_order_emitted": True,
        "all_character_fft_completed_here": False,
        "completed_l_phase_completed": False,
        "zero_isolation_completed": False,
        "turing_completeness_completed": False,
        "full_source_run_completed": False,
        "external_atom_discharged": False,
    }:
        _fail("composition receipt decision boundary differs")
    return value


def _validate_composer_summary(
    value: Mapping[str, Any],
    *,
    inventory: Any,
    requests: Sequence[_FramedRequest],
    jobs: Sequence[Any],
    composition_receipts: Sequence[Mapping[str, Any]],
    maximum_batch_count: int,
) -> None:
    required = {
        "kind",
        "classification",
        "q",
        "maximum_batch_count",
        "frame_count",
        "slice_count",
        "value_count",
        "first_t_numerator",
        "t_denominator",
        "t_step_numerator",
        "TGDAFFI1_stream_sha256",
        "control_jsonl_sha256",
        "stream_size_bytes",
        "composition_receipt_merkle_sha256",
        "retained_output_frames",
        "persistent_allchars_framed_service_compatible",
        "full_source_run_completed",
        "external_atom_discharged",
        "summary_sha256",
    }
    if set(value) != required:
        _fail("composer summary fields differ")
    _self_hash(value, "summary_sha256", label="composer summary")
    stream_bytes = sum(
        INPUT_HEADER.size
        + len(job.frames) * group_order(job.q) * COMPLEX_INTERVAL.size
        for job in jobs
    )
    receipt_digests = [
        _digest(row.get("receipt_sha256"), "composition receipt self-hash")
        for row in composition_receipts
    ]
    if (
        value.get("kind")
        != "sparkinterval.tg.dirichlet_residue_composition.framed_stream.v1"
        or value.get("classification")
        != "composition_stream_adapter_not_atom_closure"
        or value.get("q") != inventory.q
        or value.get("maximum_batch_count") != maximum_batch_count
        or value.get("frame_count") != inventory.frame_count
        or value.get("slice_count") != inventory.slice_count
        or value.get("value_count") != inventory.value_count
        or value.get("first_t_numerator") != inventory.first_t_numerator
        or value.get("t_denominator") != inventory.t_denominator
        or value.get("t_step_numerator") != inventory.t_step_numerator
        or value.get("control_jsonl_sha256")
        != inventory.composition_sha256
        or value.get("stream_size_bytes") != stream_bytes
        or value.get("composition_receipt_merkle_sha256")
        != _merkle_receipts(receipt_digests)
        or value.get("retained_output_frames") != 0
        or value.get("persistent_allchars_framed_service_compatible") is not True
        or value.get("full_source_run_completed") is not False
        or value.get("external_atom_discharged") is not False
    ):
        _fail("composer summary identity, coverage, or claim boundary differs")
    _digest(value.get("TGDAFFI1_stream_sha256"), "TGDAFFI1 stream digest")
    if len(requests) != inventory.frame_count:
        _fail("composer request count differs from inventory")


def _validate_transform_summary(
    value: Mapping[str, Any],
    *,
    inventory: Any,
    maximum_batch_count: int,
    expected_butterflies: int,
) -> None:
    required = {
        "kind",
        "algorithm",
        "q",
        "maximum_batch_count",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        "retained_input_frames",
        "retained_output_frames",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    if set(value) != required:
        _fail("transform summary fields differ")
    if (
        value.get("kind")
        != "sparkinterval.tg.dirichlet_allchars.framed_service.v1"
        or value.get("algorithm") != ALLCHARS_ALGORITHM_ID
        or value.get("q") != inventory.q
        or value.get("maximum_batch_count") != maximum_batch_count
        or value.get("frame_count") != inventory.frame_count
        or value.get("slice_count") != inventory.slice_count
        or value.get("value_count") != inventory.value_count
        or value.get("radix2_butterflies") != expected_butterflies
        or value.get("retained_input_frames") != 0
        or value.get("retained_output_frames") != 0
    ):
        _fail("transform summary identity, work, or retention boundary differs")
    _integer(
        value.get("preparation_nanoseconds"),
        "transform preparation nanoseconds",
        minimum=0,
    )
    _integer(
        value.get("elapsed_nanoseconds"),
        "transform elapsed nanoseconds",
        minimum=0,
    )
    _digest(value.get("input_stream_sha256"), "transform input stream")
    _digest(value.get("output_stream_sha256"), "transform output stream")


def _fraction(value: object, *, label: str) -> tuple[int, int]:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{label} is not an exact fraction")
    numerator = _integer(value.get("numerator"), f"{label}.numerator")
    denominator = _integer(
        value.get("denominator"), f"{label}.denominator", minimum=1
    )
    return numerator, denominator


def _rational_interval(value: object, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"lower", "upper"}:
        _fail(f"{label} is not an exact rational interval")
    lower = _fraction(value.get("lower"), label=f"{label}.lower")
    upper = _fraction(value.get("upper"), label=f"{label}.upper")
    if lower[0] * upper[1] > upper[0] * lower[1]:
        _fail(f"{label} has reversed endpoints")


def _event_identity(
    value: Mapping[str, Any],
    *,
    q: int,
    primitive_characters: int,
    frame_count: int,
) -> None:
    _integer(value.get("conrey_number"), "event Conrey number", minimum=1, maximum=q)
    _integer(value.get("parity"), "event parity", minimum=0, maximum=1)
    _integer(
        value.get("primitive_ordinal"),
        "event primitive ordinal",
        minimum=0,
        maximum=primitive_characters - 1,
    )
    if "frame_index" in value:
        _integer(
            value.get("frame_index"),
            "event frame index",
            minimum=0,
            maximum=frame_count - 1,
        )


def _validate_events(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    q: int,
    primitive_characters: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
) -> tuple[int, int, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletFFTPipelineBundleError(
            f"cannot open event stream without following a final symlink: {path}"
        ) from error
    digest = hashlib.sha256()
    size = 0
    event_count = 0
    sign_change_count = 0
    indeterminate_count = 0
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode):
            _fail("event stream is not a regular file")
        for line_index, line in enumerate(source):
            if len(line) > MAXIMUM_EVENT_LINE_BYTES:
                _fail("event line exceeds its bound")
            digest.update(line)
            size += len(line)
            value = _parse_json(
                line, label=f"event line {line_index}", canonical=True
            )
            if line_index == 0:
                if value != {
                    "classification": (
                        "multiplicity-lower-bound-events-not-zero-completeness"
                    ),
                    "kind": EVENT_FILE_SCHEMA,
                    "schema_version": 1,
                }:
                    _fail("event stream header differs")
                continue
            event_count += 1
            if value.get("kind") != EVENT_SCHEMA or value.get("q") != q:
                _fail(f"event {event_count - 1} kind or modulus differs")
            _event_identity(
                value,
                q=q,
                primitive_characters=primitive_characters,
                frame_count=frame_count,
            )
            event = value.get("event")
            if event == "sign_change_candidate":
                required = {
                    "conrey_number",
                    "contains_indeterminate_samples",
                    "endpoint_signs",
                    "event",
                    "kind",
                    "lower_ordinate",
                    "multiplicity_exact",
                    "multiplicity_lower_bound",
                    "parity",
                    "primitive_ordinal",
                    "q",
                    "upper_ordinate",
                }
                if (
                    set(value) != required
                    or value.get("multiplicity_exact") is not False
                    or value.get("multiplicity_lower_bound") != 1
                    or value.get("endpoint_signs") not in ([1, -1], [-1, 1])
                    or not isinstance(
                        value.get("contains_indeterminate_samples"), bool
                    )
                ):
                    _fail("sign-change event fields or multiplicity boundary differ")
                lower = _fraction(value.get("lower_ordinate"), label="lower ordinate")
                upper = _fraction(value.get("upper_ordinate"), label="upper ordinate")
                if lower[0] * upper[1] >= upper[0] * lower[1]:
                    _fail("sign-change event ordinate interval is not increasing")
                if (
                    lower[0] * SOURCE_T_DENOMINATOR
                    < first_t_numerator * lower[1]
                    or upper[0] * SOURCE_T_DENOMINATOR
                    >= stop_t_numerator * upper[1]
                ):
                    _fail("sign-change event is outside the pipeline ordinate grid")
                sign_change_count += 1
            elif event == "indeterminate_completed_value":
                required = {
                    "completed_rectangle",
                    "conrey_number",
                    "event",
                    "frame_index",
                    "kind",
                    "multiplicity_claimed",
                    "ordinate",
                    "parity",
                    "primitive_ordinal",
                    "q",
                    "sign",
                }
                if (
                    set(value) != required
                    or value.get("multiplicity_claimed") != 0
                    or value.get("sign") != 0
                    or not isinstance(value.get("completed_rectangle"), dict)
                ):
                    _fail("indeterminate event fields or claim boundary differ")
                ordinate = _fraction(
                    value.get("ordinate"), label="indeterminate ordinate"
                )
                if (
                    ordinate[0] * SOURCE_T_DENOMINATOR
                    < first_t_numerator * ordinate[1]
                    or ordinate[0] * SOURCE_T_DENOMINATOR
                    >= stop_t_numerator * ordinate[1]
                ):
                    _fail("indeterminate event is outside the pipeline ordinate grid")
                rectangle = value["completed_rectangle"]
                if (
                    not isinstance(rectangle, dict)
                    or set(rectangle) != {"real", "imag"}
                ):
                    _fail("indeterminate completed rectangle fields differ")
                _rational_interval(
                    rectangle["real"], label="indeterminate completed real interval"
                )
                _rational_interval(
                    rectangle["imag"], label="indeterminate completed imag interval"
                )
                indeterminate_count += 1
            else:
                _fail("unsupported event type")
    if event_count == 0 and size == 0:
        _fail("event stream is empty")
    if digest.hexdigest() != expected_sha256 or size != expected_size:
        _fail("event stream hash or size differs from its receipt")
    return event_count, sign_change_count, indeterminate_count


def _validate_event_artifact(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    expected_storage_mode: str,
    q: int,
    primitive_characters: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
) -> tuple[int, int, int]:
    if expected_storage_mode == RAW_EVENT_STORAGE_MODE:
        return _validate_events(
            path,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            q=q,
            primitive_characters=primitive_characters,
            frame_count=frame_count,
            first_t_numerator=first_t_numerator,
            stop_t_numerator=stop_t_numerator,
        )
    if expected_storage_mode != COMPACT_EVENT_STORAGE_MODE:
        _fail("consumer event storage mode differs")
    if expected_size > MAXIMUM_JSON_BYTES:
        _fail("compact event summary exceeds its JSON bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletFFTPipelineBundleError(
            "cannot open compact event summary without following a final "
            "symlink"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size != expected_size
        ):
            _fail("compact event summary type or size differs")
        raw = source.read(MAXIMUM_JSON_BYTES + 1)
    if (
        len(raw) != expected_size
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        _fail("compact event summary hash or size differs")
    value = _parse_json(raw, label="compact event summary", canonical=True)
    if value.get("schema") != COMPACT_EVENT_SCHEMA:
        _fail("compact event summary schema differs")
    try:
        return validate_compact_event_summary(
            value,
            q=q,
            primitive_characters=primitive_characters,
            frame_count=frame_count,
            first_t_numerator=first_t_numerator,
            stop_t_numerator=stop_t_numerator,
        )
    except RuntimeError as error:
        raise DirichletFFTPipelineBundleError(
            "compact event summary semantic validation failed"
        ) from error


def _validate_consumer_receipt(
    value: Mapping[str, Any],
    *,
    inventory: Any,
    events_path: Path,
    root_metadata: Mapping[str, Any],
    root_receipt: Mapping[str, Any],
) -> tuple[int, int]:
    required = {
        "algorithm_id",
        "all_frames_arithmetically_accepted",
        "atom_id",
        "author",
        "candidate_bracket_count",
        "classification",
        "control_stream_sha256",
        "discarded_nonprimitive_value_count",
        "event_count",
        "event_storage_mode",
        "events_bytes",
        "events_sha256",
        "external_atom_discharged",
        "frame_chain_sha256",
        "frame_count",
        "full_source_campaign_run",
        "indeterminate_sample_count",
        "kind",
        "multiplicity_lower_bound_sum",
        "multiplicity_policy",
        "ordinary_sign_scan_resolved",
        "precision_bits",
        "primitive_sample_count",
        "production_accept",
        "raw_event_records_retained",
        "root_number_artifact_chain_sha256",
        "root_number_artifact_bindings",
        "root_number_artifact_supplied",
        "root_number_character_count",
        "root_number_mode",
        "root_number_modulus_count",
        "root_number_rows_sha256",
        "sign_decisions_sha256",
        "source_performance_ready",
        "source_performance_blocker",
        "transform_stream_sha256",
        "upstream_semantics_replayed",
        "upstream_semantics_status",
        "value_count",
        "zero_completeness_claimed",
        "receipt_sha256",
    }
    if set(value) != required:
        _fail("consumer receipt fields differ")
    _self_hash(value, "receipt_sha256", label="consumer receipt")
    primitive_characters = primitive_character_count(inventory.q)
    primitive_samples = primitive_characters * inventory.slice_count
    discarded = inventory.value_count - primitive_samples
    root_binding = {
        "artifact_sha256": root_metadata["root_artifact_sha256"],
        "convention_sha256": ROOT_CONVENTION_SHA256,
        "primitive_character_count": primitive_characters,
        "q": inventory.q,
        "receipt_sha256": root_receipt.get("receipt_sha256"),
        "transform_output_sha256": root_metadata["transform_output_sha256"],
    }
    root_chain = hashlib.sha256(canonical_json_bytes(root_binding)).hexdigest()
    event_sha = _digest(value.get("events_sha256"), "consumer event stream")
    event_bytes = _integer(
        value.get("events_bytes"), "consumer event stream bytes", minimum=1
    )
    event_storage_mode = value.get("event_storage_mode")
    event_count, sign_changes, indeterminates = _validate_event_artifact(
        events_path,
        expected_sha256=event_sha,
        expected_size=event_bytes,
        expected_storage_mode=event_storage_mode,
        q=inventory.q,
        primitive_characters=primitive_characters,
        frame_count=inventory.frame_count,
        first_t_numerator=inventory.first_t_numerator,
        stop_t_numerator=inventory.stop_t_numerator,
    )
    if (
        value.get("kind") != CONSUMER_RECEIPT_SCHEMA
        or value.get("algorithm_id") != CONSUMER_ALGORITHM_ID
        or value.get("atom_id") != ATOM_ID
        or value.get("author") != AUTHOR
        or value.get("classification")
        != "streamed-completed-L-sign-candidates-not-zero-completeness"
        or value.get("all_frames_arithmetically_accepted") is not True
        or value.get("control_stream_sha256") != inventory.consumer_sha256
        or value.get("frame_count") != inventory.frame_count
        or value.get("value_count") != inventory.value_count
        or value.get("primitive_sample_count") != primitive_samples
        or value.get("discarded_nonprimitive_value_count") != discarded
        or value.get("event_count") != event_count
        or value.get("candidate_bracket_count") != sign_changes
        or value.get("multiplicity_lower_bound_sum") != sign_changes
        or value.get("indeterminate_sample_count") != indeterminates
        or value.get("event_storage_mode")
        not in {RAW_EVENT_STORAGE_MODE, COMPACT_EVENT_STORAGE_MODE}
        or value.get("raw_event_records_retained")
        is not (event_storage_mode == RAW_EVENT_STORAGE_MODE)
        or value.get("ordinary_sign_scan_resolved") is not (indeterminates == 0)
        or value.get("root_number_artifact_bindings") != [root_binding]
        or value.get("root_number_artifact_chain_sha256") != root_chain
        or value.get("root_number_artifact_supplied") is not True
        or value.get("root_number_character_count") != primitive_characters
        or value.get("root_number_modulus_count") != 1
        or value.get("root_number_mode") != ROOT_ALGORITHM_ID
        or value.get("source_performance_ready") is not True
        or value.get("source_performance_blocker") is not None
        or value.get("full_source_campaign_run") is not False
        or value.get("production_accept") is not False
        or value.get("upstream_semantics_replayed") is not False
        or value.get("external_atom_discharged") is not False
        or value.get("zero_completeness_claimed") is not False
    ):
        _fail("consumer receipt identity, counts, roots, or claim boundary differs")
    if value.get("multiplicity_policy") != (
        "one lower-bound event per strict endpoint sign change; never "
        "deduplicated or promoted to exact multiplicity"
    ):
        _fail("consumer multiplicity policy differs")
    if value.get("upstream_semantics_status") != (
        "four required receipts are identity/hash checked, but this component "
        "does not replay lattice tails, q^-s, or finite addback"
    ):
        _fail("consumer upstream-semantics boundary differs")
    _integer(
        value.get("precision_bits"),
        "consumer precision",
        minimum=128,
        maximum=4096,
    )
    for field in (
        "frame_chain_sha256",
        "root_number_rows_sha256",
        "sign_decisions_sha256",
        "transform_stream_sha256",
    ):
        _digest(value.get(field), f"consumer {field}")
    return event_count, indeterminates


def replay_pipeline_receipt(
    path: Path,
    *,
    control_base: Path | None = None,
    expected_file_sha256: str | None = None,
    allow_synthetic_kat: bool = False,
) -> PipelineReplay:
    """Reparse one retained pipeline receipt and all of its named artifacts."""

    raw, pipeline_file = _safe_read(
        path, label="pipeline receipt", maximum_bytes=MAXIMUM_JSON_BYTES
    )
    assert raw is not None
    if expected_file_sha256 is not None and pipeline_file["sha256"] != _digest(
        expected_file_sha256, "expected pipeline receipt file"
    ):
        _fail("pipeline receipt file differs from the externally pinned digest")
    receipt = _parse_json(raw, label="pipeline receipt", canonical=True)
    required = {
        "algorithm_id",
        "atom_id",
        "author",
        "classification",
        "component_processes_persistent",
        "external_atom_discharged",
        "frame_count",
        "full_source_campaign_run",
        "kind",
        "maximum_batch_count",
        "process_return_codes",
        "q",
        "ordinate_grid",
        "controls",
        "root_artifact",
        "root_receipt",
        "source_performance_ready_for_wired_components",
        "summaries",
        "stream_bindings_verified",
        "zero_completeness_claimed",
        "receipt_sha256",
    }
    if set(receipt) != required:
        _fail("pipeline receipt fields differ")
    receipt_sha = _self_hash(receipt, "receipt_sha256", label="pipeline receipt")
    maximum_batch_count = _integer(
        receipt.get("maximum_batch_count"),
        "pipeline maximum batch count",
        minimum=1,
        maximum=64,
    )
    if (
        receipt.get("kind") != PIPELINE_RECEIPT_SCHEMA
        or receipt.get("algorithm_id") != PIPELINE_ALGORITHM_ID
        or receipt.get("atom_id") != ATOM_ID
        or receipt.get("author") != AUTHOR
        or receipt.get("classification")
        != "persistent_component_pipeline_not_zero_or_grh_closure"
        or receipt.get("component_processes_persistent") is not True
        or receipt.get("process_return_codes")
        != {"composer": 0, "consumer": 0, "transform": 0}
        or receipt.get("source_performance_ready_for_wired_components") is not True
        or receipt.get("stream_bindings_verified") is not True
        or receipt.get("full_source_campaign_run") is not False
        or receipt.get("external_atom_discharged") is not False
        or receipt.get("zero_completeness_claimed") is not False
    ):
        _fail("pipeline identity, process status, or claim boundary differs")
    controls = receipt.get("controls")
    summaries = receipt.get("summaries")
    if (
        not isinstance(controls, dict)
        or set(controls) != {"composition", "consumer"}
        or not isinstance(summaries, dict)
        or set(summaries) != {"composer", "consumer", "events", "transform"}
    ):
        _fail("pipeline control or summary artifact inventory differs")
    composition_path, composition_raw, _ = _artifact(
        controls["composition"],
        label="composition controls",
        maximum_bytes=MAXIMUM_CONTROL_BYTES,
    )
    assert composition_raw is not None
    consumer_path, _consumer_raw, _ = _artifact(
        controls["consumer"],
        label="consumer controls",
        maximum_bytes=MAXIMUM_CONTROL_BYTES,
    )
    base = composition_path.parent if control_base is None else control_base.resolve()
    inventory = validate_control_alignment(
        composition_path,
        consumer_path,
        base=base,
        maximum_batch_count=maximum_batch_count,
        allow_synthetic_kat=allow_synthetic_kat,
    )
    requests = _framed_requests(composition_raw, base=base)
    jobs = [
        load_job(
            request.job_path,
            allow_synthetic_kat=allow_synthetic_kat,
            max_batch_count=maximum_batch_count,
        )
        for request in requests
    ]
    for request, job in zip(requests, jobs):
        _job_raw, job_record = _safe_read(
            request.job_path,
            label="composition job",
            maximum_bytes=MAXIMUM_JSON_BYTES,
            retain_bytes=False,
        )
        if job_record["sha256"] != job.sha256:
            _fail("composition job changed during typed replay")
        _revalidate_job_artifacts(job)
    composition_receipts = [
        _validate_composition_receipt(
            request.receipt_path,
            job=job,
            allow_synthetic_kat=allow_synthetic_kat,
        )
        for request, job in zip(requests, jobs)
    ]
    consumer_controls = _consumer_controls(_consumer_raw)
    if len(consumer_controls) != len(composition_receipts):
        _fail("consumer control and composition receipt counts differ")

    composer_path, composer_raw, _ = _artifact(
        summaries["composer"],
        label="composer summary",
        maximum_bytes=MAXIMUM_JSON_BYTES,
    )
    del composer_path
    assert composer_raw is not None
    composer = _parse_json(
        composer_raw, label="composer summary", canonical=True
    )
    _validate_composer_summary(
        composer,
        inventory=inventory,
        requests=requests,
        jobs=jobs,
        composition_receipts=composition_receipts,
        maximum_batch_count=maximum_batch_count,
    )

    transform_path, transform_raw, _ = _artifact(
        summaries["transform"],
        label="transform summary",
        maximum_bytes=MAXIMUM_JSON_BYTES,
    )
    del transform_path
    assert transform_raw is not None
    transform = _parse_json(
        transform_raw, label="transform summary", canonical=False
    )
    expected_butterflies = sum(
        modulus_butterflies(job.q, batch_count=len(job.frames)) for job in jobs
    )
    _validate_transform_summary(
        transform,
        inventory=inventory,
        maximum_batch_count=maximum_batch_count,
        expected_butterflies=expected_butterflies,
    )

    _root_path, root_raw, _ = _artifact(
        receipt.get("root_artifact"),
        label="root artifact",
    )
    root_receipt_path, root_receipt_raw, _ = _artifact(
        receipt.get("root_receipt"),
        label="root receipt",
        maximum_bytes=MAXIMUM_JSON_BYTES,
    )
    del root_receipt_path
    assert root_receipt_raw is not None
    root_receipt = _parse_json(
        root_receipt_raw, label="root receipt", canonical=True
    )
    assert root_raw is not None
    try:
        root_metadata, _roots = read_root_artifact_bytes(
            root_raw, root_receipt
        )
    except Exception as error:
        raise DirichletFFTPipelineBundleError(
            f"root artifact semantic replay failed: {error}"
        ) from error
    if root_metadata.get("q") != inventory.q:
        _fail("root artifact modulus differs from the pipeline")

    events_path, _events_raw, _ = _artifact(
        summaries["events"], label="consumer events", retain_bytes=False
    )
    consumer_path, consumer_raw, _ = _artifact(
        summaries["consumer"],
        label="consumer receipt",
        maximum_bytes=MAXIMUM_JSON_BYTES,
    )
    del consumer_path
    assert consumer_raw is not None
    consumer = _parse_json(
        consumer_raw, label="consumer receipt", canonical=True
    )
    event_count, indeterminate_count = _validate_consumer_receipt(
        consumer,
        inventory=inventory,
        events_path=events_path,
        root_metadata=root_metadata,
        root_receipt=root_receipt,
    )

    if (
        composer.get("TGDAFFI1_stream_sha256")
        != transform.get("input_stream_sha256")
        or transform.get("output_stream_sha256")
        != consumer.get("transform_stream_sha256")
    ):
        _fail("independently reparsed cross-stage stream hashes differ")
    if (
        receipt.get("q") != inventory.q
        or receipt.get("frame_count") != inventory.frame_count
        or receipt.get("ordinate_grid")
        != {
            "first_t_numerator": inventory.first_t_numerator,
            "stop_t_numerator_exclusive": inventory.stop_t_numerator,
            "t_denominator": inventory.t_denominator,
            "t_step_numerator": inventory.t_step_numerator,
            "slice_count": inventory.slice_count,
        }
    ):
        _fail("pipeline receipt coverage differs from reconstructed controls")
    if (
        inventory.t_denominator != SOURCE_T_DENOMINATOR
        or inventory.t_step_numerator != SOURCE_T_STEP_NUMERATOR
        or inventory.first_t_numerator % SOURCE_T_STEP_NUMERATOR
        or inventory.stop_t_numerator % SOURCE_T_STEP_NUMERATOR
    ):
        _fail("pipeline does not cover the exact 5/64 source grid")
    first_t_index = inventory.first_t_numerator // SOURCE_T_STEP_NUMERATOR
    stop_t_index = inventory.stop_t_numerator // SOURCE_T_STEP_NUMERATOR
    lattice_cache_rows = _lattice_cache_row_bindings(
        jobs,
        first_t_index=first_t_index,
    )
    if (
        len(lattice_cache_rows) != inventory.slice_count
        or lattice_cache_rows[-1][0] + 1 != stop_t_index
    ):
        _fail("lattice cache-row bindings do not cover the pipeline target")
    return PipelineReplay(
        pipeline_receipt_file=pipeline_file,
        pipeline_receipt_sha256=receipt_sha,
        q=inventory.q,
        first_t_index=first_t_index,
        t_index_stop_exclusive=stop_t_index,
        frame_count=inventory.frame_count,
        slice_count=inventory.slice_count,
        value_count=inventory.value_count,
        radix2_butterflies=expected_butterflies,
        event_count=event_count,
        indeterminate_sample_count=indeterminate_count,
        all_composition_inputs_certified=all(
            job.classification == CERTIFIED_CLASSIFICATION for job in jobs
        ),
        lattice_cache_rows=lattice_cache_rows,
    )


def _bundle_body(
    *,
    contract: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    replay: PipelineReplay,
) -> dict[str, Any]:
    return {
        "schema": BUNDLE_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": CLASSIFICATION,
        "source_contract_sha256": contract["contract_sha256"],
        "source_contract_classification": contract["classification"],
        "target": dict(descriptor),
        "pipeline_receipt_file": replay.pipeline_receipt_file,
        "pipeline_receipt_sha256": replay.pipeline_receipt_sha256,
        "replayed_inventory": {
            "q": replay.q,
            "first_t_index": replay.first_t_index,
            "t_index_stop_exclusive": replay.t_index_stop_exclusive,
            "frame_count": replay.frame_count,
            "slice_count": replay.slice_count,
            "value_count": replay.value_count,
            "radix2_butterflies": replay.radix2_butterflies,
            "event_count": replay.event_count,
            "indeterminate_sample_count": replay.indeterminate_sample_count,
            "all_composition_inputs_certified": (
                replay.all_composition_inputs_certified
            ),
            "lattice_cache_rows": [
                {
                    "t_index": t_index,
                    "payload_sha256": payload_sha256,
                }
                for t_index, payload_sha256 in replay.lattice_cache_rows
            ],
        },
        "decisions": {
            "source_contract_reconstructed_and_hash_bound": True,
            "exact_fixed_q_fft_target_covered": True,
            "pipeline_and_nested_artifact_hashes_replayed": True,
            "composition_jobs_and_input_certificate_chains_replayed": (
                replay.all_composition_inputs_certified
            ),
            "lattice_cache_row_payload_identities_replayed": True,
            "consumer_control_digest_shapes_replayed": True,
            "consumer_control_upstream_semantics_replayed": False,
            "composer_fft_consumer_receipts_typed": True,
            "root_artifact_semantics_replayed": True,
            "event_stream_shape_and_counts_replayed": True,
            "discarded_composition_stream_arithmetic_independently_replayed": False,
            "discarded_fft_stream_arithmetic_independently_replayed": False,
            "zero_state_transition_validated": False,
            "zero_completeness_claimed": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }


def build_bundle(
    output_path: Path,
    *,
    contract_path: Path,
    lane_index: int,
    q: int,
    first_t_index: int,
    pipeline_receipt_path: Path,
    control_base: Path | None = None,
    allow_structural_kat: bool = False,
    expected_contract_sha256: str | None = None,
    expected_pipeline_file_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one immutable typed bundle for an exact supervisor FFT target."""

    contract = load_contract(
        contract_path,
        allow_structural_kat=allow_structural_kat,
        expected_contract_sha256=expected_contract_sha256,
    )
    descriptor = fft_batch_descriptor(
        contract,
        lane_index=lane_index,
        q=q,
        first_t_index=first_t_index,
    )
    replay = replay_pipeline_receipt(
        pipeline_receipt_path,
        control_base=control_base,
        expected_file_sha256=expected_pipeline_file_sha256,
        allow_synthetic_kat=(
            allow_structural_kat
            and contract["classification"] == STRUCTURAL_KAT_CLASSIFICATION
        ),
    )
    expected_stop = descriptor["t_index_stop_exclusive"]
    if (
        replay.q != descriptor["q"]
        or replay.first_t_index != descriptor["first_t_index"]
        or replay.t_index_stop_exclusive != expected_stop
        or replay.slice_count != descriptor["batch_count"]
        or replay.value_count != descriptor["value_count"]
        or replay.radix2_butterflies != descriptor["radix2_butterflies"]
    ):
        _fail("pipeline replay does not exactly cover the fixed-q FFT target")
    body = _bundle_body(contract=contract, descriptor=descriptor, replay=replay)
    bundle = dict(body)
    bundle["bundle_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    if output_path.exists():
        _fail(f"refusing to replace immutable typed bundle: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    try:
        with os.fdopen(descriptor_fd, "wb") as output:
            output.write(canonical_json_bytes(bundle))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, output_path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return bundle


def replay_bundle(
    bundle_path: Path,
    *,
    contract_path: Path,
    control_base: Path | None = None,
    allow_structural_kat: bool = False,
    expected_bundle_sha256: str | None = None,
    expected_contract_sha256: str | None = None,
    _validated_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconstruct a typed bundle from its retained receipt and contract.

    ``_validated_contract`` is an internal lane-session fast path.  The
    t-major adapter supplies only the exact object returned by its one initial
    ``AuthenticatedLaneReader`` reconstruction, avoiding a source-wide
    recovery/root/catalog replay for every bundle in the same lane.
    """

    raw, bundle_file = _safe_read(
        bundle_path, label="typed FFT pipeline bundle", maximum_bytes=MAXIMUM_JSON_BYTES
    )
    assert raw is not None
    value = _parse_json(
        raw, label="typed FFT pipeline bundle", canonical=True
    )
    expected_fields = set(
        _bundle_body(
            contract={
                "contract_sha256": "0" * 64,
                "classification": STRUCTURAL_KAT_CLASSIFICATION,
            },
            descriptor={},
            replay=PipelineReplay(
                pipeline_receipt_file={},
                pipeline_receipt_sha256="0" * 64,
                q=0,
                first_t_index=0,
                t_index_stop_exclusive=0,
                frame_count=0,
                slice_count=0,
                value_count=0,
                radix2_butterflies=0,
                event_count=0,
                indeterminate_sample_count=0,
                all_composition_inputs_certified=False,
                lattice_cache_rows=(),
            ),
        )
    ) | {"bundle_sha256"}
    if set(value) != expected_fields:
        _fail("typed bundle fields differ")
    bundle_sha = _self_hash(value, "bundle_sha256", label="typed bundle")
    if expected_bundle_sha256 is not None and bundle_sha != _digest(
        expected_bundle_sha256, "expected typed bundle"
    ):
        _fail("typed bundle differs from its externally pinned digest")
    if _validated_contract is None:
        contract = load_contract(
            contract_path,
            allow_structural_kat=allow_structural_kat,
            expected_contract_sha256=expected_contract_sha256,
        )
    else:
        contract = dict(_validated_contract)
        contract_sha = _digest(
            contract.get("contract_sha256"),
            "prevalidated source contract",
        )
        classification = contract.get("classification")
        if classification == STRUCTURAL_KAT_CLASSIFICATION:
            if not allow_structural_kat:
                _fail("prevalidated structural contract requires explicit authorization")
        elif classification == SOURCE_CONTRACT_CLASSIFICATION:
            if expected_contract_sha256 is None:
                _fail("prevalidated production contract requires an external digest")
        else:
            _fail("prevalidated source contract classification differs")
        if (
            expected_contract_sha256 is not None
            and contract_sha
            != _digest(
                expected_contract_sha256,
                "expected source contract",
            )
        ):
            _fail("prevalidated source contract differs from its external digest")
    bundle_contract_sha = _digest(
        value.get("source_contract_sha256"), "bundle source contract"
    )
    if contract["contract_sha256"] != bundle_contract_sha:
        _fail("typed bundle is not bound to the supplied source contract")
    target = value.get("target")
    if not isinstance(target, dict):
        _fail("typed bundle target is malformed")
    descriptor = fft_batch_descriptor(
        contract,
        lane_index=_integer(target.get("lane_index"), "target lane", minimum=0),
        q=_integer(target.get("q"), "target q", minimum=3),
        first_t_index=_integer(
            target.get("first_t_index"), "target first t index", minimum=0
        ),
    )
    pipeline_file = value.get("pipeline_receipt_file")
    if (
        not isinstance(pipeline_file, dict)
        or set(pipeline_file) != {"path", "sha256", "size_bytes"}
        or not isinstance(pipeline_file.get("path"), str)
    ):
        _fail("typed bundle pipeline receipt artifact is malformed")
    replay = replay_pipeline_receipt(
        Path(pipeline_file["path"]),
        control_base=control_base,
        expected_file_sha256=_digest(
            pipeline_file.get("sha256"), "bundle pipeline receipt file"
        ),
        allow_synthetic_kat=(
            allow_structural_kat
            and contract["classification"] == STRUCTURAL_KAT_CLASSIFICATION
        ),
    )
    reconstructed = _bundle_body(
        contract=contract, descriptor=descriptor, replay=replay
    )
    observed_body = dict(value)
    observed_body.pop("bundle_sha256")
    if reconstructed != observed_body:
        _fail("typed bundle differs from fresh independent reconstruction")
    return {
        "schema": REPLAY_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "accepted": True,
        "bundle_file_sha256": bundle_file["sha256"],
        "bundle_sha256": bundle_sha,
        "source_contract_sha256": contract["contract_sha256"],
        "pipeline_receipt_sha256": replay.pipeline_receipt_sha256,
        "q": replay.q,
        "first_t_index": replay.first_t_index,
        "t_index_stop_exclusive": replay.t_index_stop_exclusive,
        "all_composition_inputs_certified": (
            replay.all_composition_inputs_certified
        ),
        "lattice_cache_rows": [
            {
                "t_index": t_index,
                "payload_sha256": payload_sha256,
            }
            for t_index, payload_sha256 in replay.lattice_cache_rows
        ],
        "discarded_composition_stream_arithmetic_independently_replayed": False,
        "discarded_fft_stream_arithmetic_independently_replayed": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "typed_receipt_validator_not_external_evidence",
        "typed_fft_pipeline_receipt_bundle_validator_implemented": True,
        "fixed_q_source_target_binding_implemented": True,
        "nested_artifact_hash_and_schema_replay_implemented": True,
        "composition_input_certificate_chain_replay_implemented": True,
        "lattice_cache_row_payload_identity_replay_implemented": True,
        "consumer_control_digest_shapes_replayed": True,
        "consumer_control_upstream_semantics_replayed": False,
        "root_artifact_semantic_replay_implemented": True,
        "event_stream_shape_and_count_replay_implemented": True,
        "discarded_composition_stream_arithmetic_independently_replayed": False,
        "discarded_fft_stream_arithmetic_independently_replayed": False,
        "zero_state_import_export_implemented": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "BUNDLE_SCHEMA",
    "CLASSIFICATION",
    "DirichletFFTPipelineBundleError",
    "PipelineReplay",
    "REPLAY_SCHEMA",
    "build_bundle",
    "capability",
    "replay_bundle",
    "replay_pipeline_receipt",
]
