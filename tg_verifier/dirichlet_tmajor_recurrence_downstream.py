# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded downstream qualification for the t-major factor recurrence.

This module deliberately exercises the existing, real execution path:

``TGDLTMB1 -> CUDA residue composition -> CUDA all-character transform
             -> independent MPFR transform replay -> Arb/FLINT consumer``.

It compares the current direct-MPFR sidecars with factors enclosed by the
``TGDFREC1`` disk recurrence.  The fixture uses synthetic lattice/recovery
data and only two source-range moduli.  It is therefore a qualification and
attack test, never source evidence, an attestation, or an external-atom
certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct
import subprocess
import time
from typing import Any, Iterable, Mapping, NoReturn, Sequence

from tg_verifier import dirichlet_recovery_seeds as seeds
from tg_verifier import dirichlet_tmajor_cuda_block as cuda_block
from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    INPUT_MAGIC,
    OUTPUT_HEADER,
    OUTPUT_MAGIC,
    canonical_component_orders,
    canonical_residue_order,
    validate_multiq_framed_summary,
)
from tg_verifier.dirichlet_lattice_cache import (
    _synthetic_row,
    build_cache_catalog,
    cache_shard_filename,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
)
from tg_verifier.dirichlet_largeq_batch import (
    FRAME_FACTOR,
    RESIDUE_DESCRIPTOR,
)
from tg_verifier.dirichlet_root_number_stage import (
    ROOT_ALGORITHM_ID,
    consume_transform_path,
    write_additive_input,
)
from tg_verifier.dirichlet_source_supervisor import (
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    consume_paths,
    make_control,
)
from tg_verifier.dirichlet_tmajor_cuda_block import (
    TMajorCudaBlockBuilder,
    replay_tmajor_cuda_block,
    validate_tmajor_cuda_execution_summary,
    write_sidecar_manifest,
)
from tg_verifier.dirichlet_tmajor_factor_recurrence import (
    _factor_contains,
    _parse_artifact,
    build_artifact_bytes,
    verify_artifact_bytes,
)
from tg_verifier.dirichlet_tmajor_spool import build_lane_spool


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-tmajor-recurrence-downstream-kat-v1"
REPORT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_recurrence_downstream.report.v1"
)
DEFAULT_QS = (10_001, 10_003)
DEFAULT_FIRST_T_INDEX = 0
DEFAULT_FACTOR_COUNT = 64
MAXIMUM_Q_COUNT = 2
MAXIMUM_OUTPUT_BYTES = 256 * 1024 * 1024


class DirichletTMajorRecurrenceDownstreamError(RuntimeError):
    """A bounded downstream qualification or attack failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorRecurrenceDownstreamError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }


def _validate_request(
    *,
    qs: Sequence[int],
    first_t_index: int,
    factor_count: int,
) -> tuple[int, ...]:
    roster = tuple(qs)
    if (
        not 1 <= len(roster) <= MAXIMUM_Q_COUNT
        or tuple(sorted(set(roster))) != roster
        or roster[0] < cuda_block.SOURCE_Q_START
        or roster[-1] > cuda_block.SOURCE_Q_STOP
        or tuple(
            cuda_block._expected_qs(
                q_start=roster[0],
                q_stop=roster[-1],
                first_t_index=first_t_index,
            )
        )
        != roster
        or isinstance(first_t_index, bool)
        or not isinstance(first_t_index, int)
        or first_t_index < 0
        or isinstance(factor_count, bool)
        or not isinstance(factor_count, int)
        or not 1 <= factor_count <= 64
    ):
        _fail("qualification request is outside the bounded source roster")
    stop = first_t_index + factor_count
    if any(stop - 1 > cuda_block.maximum_t_index(q) for q in roster):
        _fail("qualification ordinate block exceeds a modulus source grid")
    return roster


def _write_structural_seed_artifact(path: Path, *, q_stop: int) -> str:
    """Stream the existing prefix-KAT recovery artifact without 1 GiB RAM."""

    if path.exists():
        _fail("refusing to replace structural recovery artifact")
    x_stop = (seeds.SOURCE_M + 1) * q_stop - 1
    chunk_records = 4096
    record_count = x_stop
    header = seeds.HEADER.pack(
        seeds.HEADER_MAGIC,
        seeds.FORMAT_VERSION,
        seeds.SOURCE_M,
        seeds.SOURCE_MAX_Q,
        seeds.SEED_RECORD.size,
        1,
        x_stop,
        seeds.SOURCE_STEP_NUMERATOR,
        seeds.SOURCE_STEP_DENOMINATOR,
        record_count,
        192,
        256,
        chunk_records,
        0,
        0,
    )
    records_digest = hashlib.sha256()
    root_digest = hashlib.sha256(seeds.ROOT_DOMAIN)
    artifact_digest = hashlib.sha256()
    chunk_count = 0
    first_x = 1
    record = seeds.SEED_RECORD.pack(0.001, 0.001, 1.0, 1.0, 0.0, 0.0)
    with path.open("xb") as output:
        output.write(header)
        artifact_digest.update(header)
        while first_x <= x_stop:
            count = min(chunk_records, x_stop - first_x + 1)
            payload = record * count
            chunk_digest = hashlib.sha256(
                seeds.CHUNK_DOMAIN
                + first_x.to_bytes(8, "little")
                + count.to_bytes(8, "little")
                + payload
            ).digest()
            chunk_header = seeds.CHUNK_HEADER.pack(
                seeds.CHUNK_MAGIC,
                seeds.FORMAT_VERSION,
                0,
                first_x,
                count,
                chunk_digest,
            )
            output.write(chunk_header)
            output.write(payload)
            artifact_digest.update(chunk_header)
            artifact_digest.update(payload)
            records_digest.update(payload)
            root_digest.update(chunk_digest)
            first_x += count
            chunk_count += 1
        footer = seeds.FOOTER.pack(
            seeds.FOOTER_MAGIC,
            seeds.FORMAT_VERSION,
            0,
            record_count,
            chunk_count,
            records_digest.digest(),
            root_digest.digest(),
        )
        output.write(footer)
        artifact_digest.update(footer)
        output.flush()
        os.fsync(output.fileno())
    return artifact_digest.hexdigest()


def _direct_factors(
    *,
    qs: Sequence[int],
    first_t_index: int,
    factor_count: int,
) -> tuple[dict[int, tuple[tuple[float, float, float, float], ...]], float]:
    result: dict[int, tuple[tuple[float, float, float, float], ...]] = {}
    started = time.perf_counter()
    with cuda_block.MPFRFactorProvider(
        cuda_block.DIRECT_FACTOR_PRECISION_BITS
    ) as generator:
        with cuda_block.MPFRFactorProvider(
            cuda_block.DIRECT_FACTOR_REPLAY_PRECISION_BITS
        ) as replayer:
            for q in qs:
                boxes = []
                for t_index in range(
                    first_t_index, first_t_index + factor_count
                ):
                    arguments = {
                        "q": q,
                        "t_numerator": (
                            t_index * cuda_block.SOURCE_SAMPLE_NUMERATOR
                        ),
                        "t_denominator": (
                            cuda_block.SOURCE_SAMPLE_DENOMINATOR
                        ),
                    }
                    generated = generator.factor(**arguments)
                    replayed = replayer.factor(**arguments)
                    if not cuda_block._factor_contains(
                        generated, replayed
                    ):
                        _fail(
                            "higher-precision direct MPFR factor escaped "
                            "the generated box"
                        )
                    boxes.append(generated)
                result[q] = tuple(boxes)
    return result, time.perf_counter() - started


def _recurrence_factors(
    root: Path,
    *,
    qs: Sequence[int],
    first_t_index: int,
    factor_count: int,
) -> tuple[
    dict[int, tuple[tuple[float, float, float, float], ...]],
    tuple[dict[str, Any], ...],
    float,
]:
    result = {}
    reports = []
    elapsed = 0.0
    for q in qs:
        started = time.perf_counter()
        raw = build_artifact_bytes(
            q=q,
            first_t_index=first_t_index,
            count=factor_count,
        )
        elapsed += time.perf_counter() - started
        path = root / f"q-{q}.tgdfr"
        path.write_bytes(raw)
        # This is deliberately outside the producer timing: it performs the
        # full bounded direct-MPFR differential audit.
        report = verify_artifact_bytes(raw, full_direct_mpfr=True)
        parsed = _parse_artifact(raw)
        result[q] = parsed.factors
        reports.append(
            {
                **report,
                "artifact": _artifact(path),
            }
        )
    return result, tuple(reports), elapsed


def compare_factor_rosters(
    direct: Mapping[int, Sequence[Sequence[float]]],
    recurrence: Mapping[int, Sequence[Sequence[float]]],
) -> dict[str, Any]:
    if set(direct) != set(recurrence):
        _fail("direct and recurrence modulus rosters differ")
    direct_widths = []
    recurrence_widths = []
    contained = 0
    count = 0
    for q in sorted(direct):
        if len(direct[q]) != len(recurrence[q]):
            _fail("direct and recurrence factor counts differ")
        for direct_box, recurrence_box in zip(direct[q], recurrence[q]):
            if len(direct_box) != 4 or len(recurrence_box) != 4:
                _fail("factor roster contains a malformed interval")
            if not _factor_contains(recurrence_box, direct_box):
                _fail("recurrence factor does not contain direct MPFR factor")
            contained += 1
            count += 1
            direct_widths.append(
                max(
                    direct_box[1] - direct_box[0],
                    direct_box[3] - direct_box[2],
                )
            )
            recurrence_widths.append(
                max(
                    recurrence_box[1] - recurrence_box[0],
                    recurrence_box[3] - recurrence_box[2],
                )
            )
    ratios = [
        outer / inner
        for inner, outer in zip(direct_widths, recurrence_widths)
        if inner > 0.0
    ]
    return {
        "factor_count": count,
        "recurrence_contains_direct_count": contained,
        "all_recurrence_factors_contain_direct_MPFR": contained == count,
        "direct_maximum_width": max(direct_widths),
        "recurrence_maximum_width": max(recurrence_widths),
        "median_recurrence_over_direct_width": statistics.median(ratios),
    }


def _write_seeded_input(
    path: Path,
    *,
    q: int,
    first_t_index: int,
    factors: Sequence[Sequence[float]],
    rows: Sequence[bytes],
    tails: Sequence[bytes],
) -> dict[str, Any]:
    if len(factors) != len(rows) or len(rows) != len(tails):
        _fail("seeded recurrence input rosters differ")
    residues = canonical_residue_order(q)
    orders = canonical_component_orders(q)
    count = len(factors)
    header = seeds.SEEDED_BATCH_HEADER.pack(
        seeds.SEEDED_BATCH_MAGIC,
        2,
        q,
        LATTICE_ROWS,
        TAYLOR_DEGREE,
        len(orders),
        count,
        seeds.SOURCE_M,
        0,
        len(residues),
        first_t_index * cuda_block.SOURCE_SAMPLE_NUMERATOR,
        cuda_block.SOURCE_SAMPLE_DENOMINATOR,
        cuda_block.SOURCE_SAMPLE_NUMERATOR,
        count * LATTICE_ROWS * TAYLOR_COLUMNS,
        count * len(residues),
        0,
    )
    descriptors = b"".join(
        RESIDUE_DESCRIPTOR.pack(a, canonical_lattice_row(q, a))
        for a in residues
    )
    factor_raw = b"".join(FRAME_FACTOR.pack(*box) for box in factors)
    raw = header + descriptors + factor_raw + b"".join(rows) + b"".join(tails)
    path.write_bytes(raw)
    return {
        "q": q,
        "path": str(path.resolve()),
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }


@dataclass(frozen=True)
class _BlockFixture:
    seed_path: Path
    seed_sha256: str
    direct_artifact: Path
    direct_receipt_path: Path
    direct_receipt: dict[str, Any]
    recurrence_artifact: Path
    recurrence_receipt_path: Path
    recurrence_receipt: dict[str, Any]


def _build_block_fixture(
    root: Path,
    *,
    qs: Sequence[int],
    first_t_index: int,
    factor_count: int,
    recurrence_factors: Mapping[
        int, Sequence[Sequence[float]]
    ],
) -> _BlockFixture:
    seed_path = root / "recovery-seeds.bin"
    seed_sha = _write_structural_seed_artifact(seed_path, q_stop=max(qs))
    cache = root / "cache"
    cache.mkdir()
    plan = source_cache_plan(
        t_index_stop_exclusive=first_t_index + factor_count,
        t_indices_per_shard=first_t_index + factor_count,
    )
    write_synthetic_cache_shard(
        cache / cache_shard_filename(0),
        plan=plan,
        shard_index=0,
    )
    catalog = cache / "catalog.json"
    build_cache_catalog(
        catalog,
        cache,
        plan=plan,
        require_replayed_receipts=False,
    )
    contract = root / "contract.json"
    build_structural_kat_contract(
        contract,
        cache_root=cache,
        cache_catalog=catalog,
        lane_count=1,
        recovery_artifact_sha256=seed_sha,
        recovery_replay_sha256="b" * 64,
        q_tile_size=1,
        q_start=min(qs),
        q_stop=max(qs),
    )
    spool_path = root / "spool.bin"
    spool_receipt_path = root / "spool.receipt.json"
    spool_receipt = build_lane_spool(
        spool_path,
        spool_receipt_path,
        contract_path=contract,
        lane_index=0,
        allow_structural_kat=True,
    )

    direct_artifact = root / "direct-block.bin"
    direct_receipt_path = root / "direct-block.receipt.json"
    with TMajorCudaBlockBuilder(
        contract_path=contract,
        spool_receipt_path=spool_receipt_path,
        expected_spool_receipt_sha256=spool_receipt["receipt_sha256"],
        allow_structural_kat=True,
    ) as builder:
        direct_receipt = builder.build(
            direct_artifact,
            direct_receipt_path,
            first_t_index=first_t_index,
            direct_sidecars=True,
        )
    replay_tmajor_cuda_block(
        direct_artifact,
        direct_receipt_path,
        expected_receipt_sha256=direct_receipt["receipt_sha256"],
    )

    rows = tuple(
        _synthetic_row(t_index)
        for t_index in range(
            first_t_index, first_t_index + factor_count
        )
    )
    tails = cuda_block._global_tail_words(
        first_t_index=first_t_index,
        t_index_stop_exclusive=first_t_index + factor_count,
    )
    entries = []
    for q in qs:
        entries.append(
            _write_seeded_input(
                root / f"q-{q}.recurrence-seeded.bin",
                q=q,
                first_t_index=first_t_index,
                factors=recurrence_factors[q],
                rows=rows,
                tails=tails,
            )
        )
    manifest = root / "recurrence-sidecars.ndjson"
    manifest_record = write_sidecar_manifest(manifest, entries)
    recurrence_artifact = root / "recurrence-block.bin"
    recurrence_receipt_path = root / "recurrence-block.receipt.json"
    with TMajorCudaBlockBuilder(
        contract_path=contract,
        spool_receipt_path=spool_receipt_path,
        expected_spool_receipt_sha256=spool_receipt["receipt_sha256"],
        allow_structural_kat=True,
    ) as builder:
        recurrence_receipt = builder.build(
            recurrence_artifact,
            recurrence_receipt_path,
            sidecar_manifest_path=manifest,
            expected_sidecar_manifest_sha256=manifest_record["sha256"],
            first_t_index=first_t_index,
        )
    replay_tmajor_cuda_block(
        recurrence_artifact,
        recurrence_receipt_path,
        expected_receipt_sha256=recurrence_receipt["receipt_sha256"],
    )
    return _BlockFixture(
        seed_path,
        seed_sha,
        direct_artifact,
        direct_receipt_path,
        direct_receipt,
        recurrence_artifact,
        recurrence_receipt_path,
        recurrence_receipt,
    )


def _extract_block_factors(
    artifact: Path,
) -> dict[int, tuple[tuple[float, float, float, float], ...]]:
    raw = artifact.read_bytes()
    header = cuda_block.BLOCK_HEADER.unpack_from(raw)
    row_count = int(header[3])
    target_count = int(header[4])
    position = cuda_block.BLOCK_HEADER.size + row_count * (
        cuda_block.ROW_HEADER.size + cuda_block.ROW_PAYLOAD_BYTES
    )
    result = {}
    for _ in range(target_count):
        target = cuda_block.TARGET_HEADER.unpack_from(raw, position)
        q = int(target[2])
        count = int(target[4])
        factor_bytes = int(target[12])
        tail_bytes = int(target[13])
        position += cuda_block.TARGET_HEADER.size
        factors = tuple(
            FRAME_FACTOR.iter_unpack(raw[position : position + factor_bytes])
        )
        if len(factors) != count:
            _fail("block factor extraction count differs")
        result[q] = factors
        position += factor_bytes + tail_bytes
    if position != len(raw) - cuda_block.BLOCK_FOOTER.size:
        _fail("block factor extraction lost target framing")
    return result


def _run_composition(
    root: Path,
    *,
    label: str,
    runner: Path,
    device: int,
    fixture: _BlockFixture,
    recurrence: bool,
    timeout_seconds: float,
) -> tuple[bytes, dict[str, Any], float]:
    artifact = (
        fixture.recurrence_artifact
        if recurrence
        else fixture.direct_artifact
    )
    receipt_path = (
        fixture.recurrence_receipt_path
        if recurrence
        else fixture.direct_receipt_path
    )
    receipt = (
        fixture.recurrence_receipt
        if recurrence
        else fixture.direct_receipt
    )
    summary_path = root / f"{label}-composition-summary.json"
    output_path = root / f"{label}-composition.bin"
    started = time.perf_counter()
    with output_path.open("wb") as output:
        completed = subprocess.run(
            [
                str(runner.resolve()),
                "--tmajor-block",
                str(fixture.seed_path.resolve()),
                fixture.seed_sha256,
                str(artifact.resolve()),
                receipt["artifact"]["sha256"],
                str(summary_path.resolve()),
                str(device),
                "--allow-prefix-kat",
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    wall = time.perf_counter() - started
    if completed.returncode != 0:
        _fail(
            f"{label} CUDA composition failed: "
            + completed.stderr.decode(errors="replace")
        )
    if output_path.stat().st_size > MAXIMUM_OUTPUT_BYTES:
        _fail(f"{label} CUDA composition exceeded bounded output size")
    output = output_path.read_bytes()
    summary = json.loads(summary_path.read_bytes())
    validate_tmajor_cuda_execution_summary(
        summary_path,
        artifact,
        receipt_path,
        expected_summary_sha256=_sha256(summary_path.read_bytes()),
        expected_receipt_sha256=receipt["receipt_sha256"],
    )
    if summary["output_stream_sha256"] != _sha256(output):
        _fail(f"{label} CUDA composition summary output hash differs")
    return output, summary, wall


def _run_transform(
    root: Path,
    *,
    label: str,
    runner: Path,
    checker: Path,
    device: int,
    input_stream: bytes,
    timeout_seconds: float,
) -> tuple[bytes, dict[str, Any], float, int]:
    summary_path = root / f"{label}-transform-summary.json"
    output_path = root / f"{label}-transform.bin"
    started = time.perf_counter()
    with output_path.open("wb") as output:
        completed = subprocess.run(
            [
                str(runner.resolve()),
                "--multiq-framed-service",
                "64",
                "512",
                str(summary_path.resolve()),
                str(device),
            ],
            input=input_stream,
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    wall = time.perf_counter() - started
    if completed.returncode != 0:
        _fail(
            f"{label} CUDA all-character transform failed: "
            + completed.stderr.decode(errors="replace")
        )
    output_stream = output_path.read_bytes()
    summary = json.loads(summary_path.read_bytes())
    validate_multiq_framed_summary(
        summary,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    frames = _independent_mpfr_transform_replay(
        root / f"{label}-mpfr-replay",
        input_stream=input_stream,
        output_stream=output_stream,
        checker=checker,
        timeout_seconds=timeout_seconds,
    )
    return output_stream, summary, wall, frames


def _framed_values(
    raw: bytes, *, output: bool
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[float, float, float, float], ...],
]:
    header = OUTPUT_HEADER if output else INPUT_HEADER
    magic = OUTPUT_MAGIC if output else INPUT_MAGIC
    position = 0
    identities = []
    values = []
    while position < len(raw):
        if len(raw) - position < header.size:
            _fail("interval stream has a partial header")
        fields = header.unpack_from(raw, position)
        if fields[0] != magic:
            _fail("interval stream magic differs")
        if output:
            value_count = int(fields[6])
            identity = tuple(int(value) for value in fields[1:8])
        else:
            value_count = int(fields[9])
            identity = tuple(int(value) for value in fields[1:])
        position += header.size
        stop = position + value_count * COMPLEX_INTERVAL.size
        if stop > len(raw):
            _fail("interval stream values are truncated")
        for endpoints in COMPLEX_INTERVAL.iter_unpack(raw[position:stop]):
            if not (
                all(math.isfinite(value) for value in endpoints)
                and endpoints[0] <= endpoints[1]
                and endpoints[2] <= endpoints[3]
            ):
                _fail("interval stream contains a malformed rectangle")
            values.append(endpoints)
        identities.append(identity)
        position = stop
    if not identities:
        _fail("interval stream is empty")
    return tuple(identities), tuple(values)


def compare_interval_streams(
    direct: bytes,
    recurrence: bytes,
    *,
    output: bool,
) -> dict[str, Any]:
    direct_ids, direct_values = _framed_values(direct, output=output)
    recurrence_ids, recurrence_values = _framed_values(
        recurrence, output=output
    )
    if direct_ids != recurrence_ids or len(direct_values) != len(
        recurrence_values
    ):
        _fail("direct and recurrence interval stream identities differ")
    direct_widths = []
    recurrence_widths = []
    ratios = []
    contained = 0
    equal = 0
    for direct_box, recurrence_box in zip(
        direct_values, recurrence_values
    ):
        if not _factor_contains(recurrence_box, direct_box):
            _fail("recurrence interval stream does not contain direct output")
        contained += 1
        if FRAME_FACTOR.pack(*direct_box) == FRAME_FACTOR.pack(
            *recurrence_box
        ):
            equal += 1
        direct_width = max(
            direct_box[1] - direct_box[0],
            direct_box[3] - direct_box[2],
        )
        recurrence_width = max(
            recurrence_box[1] - recurrence_box[0],
            recurrence_box[3] - recurrence_box[2],
        )
        direct_widths.append(direct_width)
        recurrence_widths.append(recurrence_width)
        if direct_width > 0.0:
            ratios.append(recurrence_width / direct_width)
    return {
        "frame_count": len(direct_ids),
        "interval_count": len(direct_values),
        "recurrence_contains_direct_count": contained,
        "all_recurrence_intervals_contain_direct": (
            contained == len(direct_values)
        ),
        "byte_identical_streams": direct == recurrence,
        "byte_identical_interval_count": equal,
        "direct_maximum_width": max(direct_widths),
        "recurrence_maximum_width": max(recurrence_widths),
        "median_recurrence_over_direct_width": statistics.median(ratios),
    }


def _iter_frame_bytes(raw: bytes, *, output: bool) -> Iterable[bytes]:
    header = OUTPUT_HEADER if output else INPUT_HEADER
    position = 0
    while position < len(raw):
        fields = header.unpack_from(raw, position)
        count = int(fields[6] if output else fields[9])
        stop = position + header.size + count * COMPLEX_INTERVAL.size
        if stop > len(raw):
            _fail("frame split encountered truncated values")
        yield raw[position:stop]
        position = stop


def _zero_hull_transform_frame(raw: bytes) -> bytes:
    """Broaden a synthetic TGDAFFO1 frame so the Arb protocol can consume it.

    The structural lattice fixture is not a completed-L function and its
    phase-rotated imaginary interval need not contain zero.  The real
    consumer correctly rejects such an input.  For the consumer protocol KAT
    only, hull every complex transform rectangle with zero.  This preserves
    containment of the actual CUDA output but deliberately destroys sign
    usefulness; the report exposes the broadening and never treats it as
    source evidence.
    """

    changed = bytearray(raw)
    fields = OUTPUT_HEADER.unpack_from(changed)
    count = int(fields[6])
    if len(changed) != OUTPUT_HEADER.size + count * COMPLEX_INTERVAL.size:
        _fail("zero-hull transform frame geometry differs")
    for index in range(count):
        offset = OUTPUT_HEADER.size + index * COMPLEX_INTERVAL.size
        box = list(COMPLEX_INTERVAL.unpack_from(changed, offset))
        box[0] = min(box[0], 0.0)
        box[1] = max(box[1], 0.0)
        box[2] = min(box[2], 0.0)
        box[3] = max(box[3], 0.0)
        COMPLEX_INTERVAL.pack_into(changed, offset, *box)
    return bytes(changed)


def _independent_mpfr_transform_replay(
    root: Path,
    *,
    input_stream: bytes,
    output_stream: bytes,
    checker: Path,
    timeout_seconds: float,
) -> int:
    root.mkdir()
    inputs = tuple(_iter_frame_bytes(input_stream, output=False))
    outputs = tuple(_iter_frame_bytes(output_stream, output=True))
    if len(inputs) != len(outputs):
        _fail("MPFR replay input/output frame counts differ")
    for index, (input_frame, output_frame) in enumerate(
        zip(inputs, outputs)
    ):
        input_path = root / f"input-{index}.bin"
        output_path = root / f"output-{index}.bin"
        input_path.write_bytes(input_frame)
        output_path.write_bytes(output_frame)
        completed = subprocess.run(
            [
                str(checker.resolve()),
                "verify",
                str(input_path.resolve()),
                str(output_path.resolve()),
                "192",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            _fail(
                f"independent MPFR transform replay {index} failed: "
                + completed.stderr.decode(errors="replace")
            )
    return len(inputs)


def _arb_consume(
    root: Path,
    *,
    label: str,
    checker: Path,
    input_stream: bytes,
    transform_stream: bytes,
    block_receipt: Mapping[str, Any],
    composition_summary: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    input_frames = tuple(_iter_frame_bytes(input_stream, output=False))
    output_frames = tuple(_iter_frame_bytes(transform_stream, output=True))
    if len(input_frames) != len(output_frames):
        _fail("Arb consumer input/output frame counts differ")
    results = []
    total_wall = 0.0
    for index, (input_frame, output_frame) in enumerate(
        zip(input_frames, output_frames)
    ):
        input_header = INPUT_HEADER.unpack_from(input_frame)
        q = int(input_header[2])
        count = int(input_header[4])
        first = int(input_header[6])
        denominator = int(input_header[7])
        step = int(input_header[8])
        frame_root = root / f"q-{q}"
        frame_root.mkdir(parents=True)
        additive_input = frame_root / "root-additive.bin"
        additive_receipt = write_additive_input(
            additive_input, q=q, precision=192
        )
        root_transform = frame_root / "root-transform.bin"
        completed = subprocess.run(
            [
                str(checker.resolve()),
                "compute",
                str(additive_input.resolve()),
                str(root_transform.resolve()),
                "192",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            _fail(
                f"root-number MPFR transform q={q} failed: "
                + completed.stderr.decode(errors="replace")
            )
        root_artifact = frame_root / "roots.bin"
        root_receipt_path = frame_root / "roots.json"
        root_receipt = consume_transform_path(
            root_transform,
            root_artifact,
            root_receipt_path,
            q=q,
            additive_receipt=additive_receipt,
            precision=192,
        )
        control_path = frame_root / f"{label}-control.ndjson"
        control_path.write_bytes(
            canonical_json_bytes(
                make_control(
                    frame_index=0,
                    q=q,
                    batch_count=count,
                    first_t_numerator=first,
                    t_denominator=denominator,
                    t_step_numerator=step,
                    upstream_receipts={
                        "all_character_transform_input_sha256": _sha256(
                            input_frame
                        ),
                        "finite_addback_receipt_sha256": str(
                            block_receipt["receipt_sha256"]
                        ),
                        "lattice_tail_receipt_sha256": str(
                            block_receipt["spool_receipt_sha256"]
                        ),
                        "residue_adapter_receipt_sha256": str(
                            composition_summary["output_stream_sha256"]
                        ),
                    },
                    root_number_mode=ROOT_ALGORITHM_ID,
                )
            )
        )
        # The real CUDA output has already passed the independent MPFR
        # transform checker before this function.  Its synthetic lattice
        # values are not completed-L-real, so the consumer protocol smoke
        # test receives an explicit outward zero hull.
        consumer_frame = _zero_hull_transform_frame(output_frame)
        frame_path = frame_root / f"{label}-transform-frame-zero-hull.bin"
        frame_path.write_bytes(consumer_frame)
        events_path = frame_root / f"{label}-events.ndjson"
        receipt_path = frame_root / f"{label}-consumer.json"
        started = time.perf_counter()
        receipt = consume_paths(
            control_path,
            frame_path,
            events_path,
            receipt_path,
            precision=192,
            root_artifact_path=root_artifact,
            root_receipt_path=root_receipt_path,
            event_storage_mode=COMPACT_EVENT_STORAGE_MODE,
        )
        wall = time.perf_counter() - started
        total_wall += wall
        results.append(
            {
                "q": q,
                "wall_seconds": wall,
                "frame_count": receipt["frame_count"],
                "primitive_sample_count": receipt[
                    "primitive_sample_count"
                ],
                "candidate_bracket_count": receipt[
                    "candidate_bracket_count"
                ],
                "indeterminate_sample_count": receipt[
                    "indeterminate_sample_count"
                ],
                "receipt_sha256": receipt["receipt_sha256"],
                "events_sha256": receipt["events_sha256"],
                "root_receipt_sha256": root_receipt[
                    "receipt_sha256"
                ],
                "production_accept": receipt["production_accept"],
                "external_atom_discharged": receipt[
                    "external_atom_discharged"
                ],
            }
        )
    return {
        "Arb_FLINT_consumer_executed": True,
        "fresh_Arb_replay_executed": False,
        "consumer_input_mode": (
            "outward_zero_hull_of_synthetic_CUDA_transform_KAT"
        ),
        "raw_CUDA_transform_consumed_without_broadening": False,
        "frame_results": results,
        "total_wall_seconds": total_wall,
        "source_semantics_realized": False,
        "source_scale_run": False,
        "external_atom_discharged": False,
    }


def run_qualification(
    output_root: Path,
    *,
    composition_runner: Path,
    allchars_runner: Path,
    allchars_checker: Path,
    device: int = 0,
    qs: Sequence[int] = DEFAULT_QS,
    first_t_index: int = DEFAULT_FIRST_T_INDEX,
    factor_count: int = DEFAULT_FACTOR_COUNT,
    run_arb_consumer: bool = True,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    """Run the complete bounded direct-versus-recurrence comparison."""

    roster = _validate_request(
        qs=qs,
        first_t_index=first_t_index,
        factor_count=factor_count,
    )
    if output_root.exists() and any(output_root.iterdir()):
        _fail("qualification output directory must be empty")
    output_root.mkdir(parents=True, exist_ok=True)
    for path, label in (
        (composition_runner, "CUDA composition runner"),
        (allchars_runner, "CUDA all-character runner"),
        (allchars_checker, "MPFR all-character checker"),
    ):
        if not path.is_file():
            _fail(f"{label} is missing")

    direct, direct_factor_seconds = _direct_factors(
        qs=roster,
        first_t_index=first_t_index,
        factor_count=factor_count,
    )
    recurrence, recurrence_reports, recurrence_factor_seconds = (
        _recurrence_factors(
            output_root,
            qs=roster,
            first_t_index=first_t_index,
            factor_count=factor_count,
        )
    )
    factor_comparison = compare_factor_rosters(direct, recurrence)
    fixture = _build_block_fixture(
        output_root,
        qs=roster,
        first_t_index=first_t_index,
        factor_count=factor_count,
        recurrence_factors=recurrence,
    )
    if _extract_block_factors(fixture.direct_artifact) != direct:
        _fail("direct TGDLTMB1 factors differ from timed MPFR roster")
    if _extract_block_factors(fixture.recurrence_artifact) != recurrence:
        _fail("recurrence TGDLTMB1 factors differ from TGDFREC1 roster")

    direct_composition, direct_composition_summary, direct_composition_wall = (
        _run_composition(
            output_root,
            label="direct",
            runner=composition_runner,
            device=device,
            fixture=fixture,
            recurrence=False,
            timeout_seconds=timeout_seconds,
        )
    )
    (
        recurrence_composition,
        recurrence_composition_summary,
        recurrence_composition_wall,
    ) = _run_composition(
        output_root,
        label="recurrence",
        runner=composition_runner,
        device=device,
        fixture=fixture,
        recurrence=True,
        timeout_seconds=timeout_seconds,
    )
    composition_comparison = compare_interval_streams(
        direct_composition,
        recurrence_composition,
        output=False,
    )

    (
        direct_transform,
        direct_transform_summary,
        direct_transform_wall,
        direct_mpfr_frames,
    ) = _run_transform(
        output_root,
        label="direct",
        runner=allchars_runner,
        checker=allchars_checker,
        device=device,
        input_stream=direct_composition,
        timeout_seconds=timeout_seconds,
    )
    (
        recurrence_transform,
        recurrence_transform_summary,
        recurrence_transform_wall,
        recurrence_mpfr_frames,
    ) = _run_transform(
        output_root,
        label="recurrence",
        runner=allchars_runner,
        checker=allchars_checker,
        device=device,
        input_stream=recurrence_composition,
        timeout_seconds=timeout_seconds,
    )
    transform_comparison = compare_interval_streams(
        direct_transform,
        recurrence_transform,
        output=True,
    )

    arb = None
    if run_arb_consumer:
        arb = {
            "direct": _arb_consume(
                output_root / "direct-arb",
                label="direct",
                checker=allchars_checker,
                input_stream=direct_composition,
                transform_stream=direct_transform,
                block_receipt=fixture.direct_receipt,
                composition_summary=direct_composition_summary,
                timeout_seconds=timeout_seconds,
            ),
            "recurrence": _arb_consume(
                output_root / "recurrence-arb",
                label="recurrence",
                checker=allchars_checker,
                input_stream=recurrence_composition,
                transform_stream=recurrence_transform,
                block_receipt=fixture.recurrence_receipt,
                composition_summary=recurrence_composition_summary,
                timeout_seconds=timeout_seconds,
            ),
        }

    factor_speedup = (
        direct_factor_seconds / recurrence_factor_seconds
        if recurrence_factor_seconds > 0.0
        else math.inf
    )
    enclosure_quality_no_worse = (
        transform_comparison["recurrence_maximum_width"]
        <= transform_comparison["direct_maximum_width"]
    )
    beneficial = factor_speedup > 1.0 and enclosure_quality_no_worse
    report = {
        "schema": REPORT_SCHEMA,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_synthetic_downstream_qualification_not_source_evidence"
        ),
        "q_roster": list(roster),
        "first_t_index": first_t_index,
        "factor_count_per_q": factor_count,
        "factor_recurrence_reports": list(recurrence_reports),
        "factor_comparison": factor_comparison,
        "composition_comparison": composition_comparison,
        "transform_comparison": transform_comparison,
        "performance": {
            "direct_two_precision_factor_seconds": direct_factor_seconds,
            "recurrence_build_and_exact_self_replay_seconds": (
                recurrence_factor_seconds
            ),
            "direct_over_recurrence_factor_speedup": factor_speedup,
            "direct_composition_wall_seconds": direct_composition_wall,
            "recurrence_composition_wall_seconds": (
                recurrence_composition_wall
            ),
            "direct_composition_kernel_nanoseconds": (
                direct_composition_summary["elapsed_kernel_nanoseconds"]
            ),
            "recurrence_composition_kernel_nanoseconds": (
                recurrence_composition_summary[
                    "elapsed_kernel_nanoseconds"
                ]
            ),
            "direct_transform_wall_seconds": direct_transform_wall,
            "recurrence_transform_wall_seconds": (
                recurrence_transform_wall
            ),
            "direct_transform_kernel_nanoseconds": (
                direct_transform_summary["elapsed_nanoseconds"]
            ),
            "recurrence_transform_kernel_nanoseconds": (
                recurrence_transform_summary["elapsed_nanoseconds"]
            ),
        },
        "independent_MPFR_transform_frames": {
            "direct": direct_mpfr_frames,
            "recurrence": recurrence_mpfr_frames,
        },
        "Arb_FLINT_consumer": arb,
        "assessment": {
            "factor_generation_faster": factor_speedup > 1.0,
            "downstream_enclosure_quality_no_worse": (
                enclosure_quality_no_worse
            ),
            "recurrence_beneficial_for_current_pipeline": beneficial,
            "reason": (
                "The recurrence is only beneficial under this conservative "
                "qualification rule when factor generation is faster and "
                "the final all-character enclosures are no wider. The "
                "measured recurrence enclosures are wider."
            ),
        },
        "production_TGDLTMB1_format_changed": False,
        "compiled_recurrence_refinement_proved": False,
        "source_semantics_realized": False,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    body = canonical_json_bytes(report)
    report["report_sha256"] = _sha256(body)
    (output_root / "qualification.json").write_bytes(
        canonical_json_bytes(report)
    )
    return report


__all__ = [
    "ALGORITHM_ID",
    "DEFAULT_FACTOR_COUNT",
    "DEFAULT_FIRST_T_INDEX",
    "DEFAULT_QS",
    "DirichletTMajorRecurrenceDownstreamError",
    "compare_factor_rosters",
    "compare_interval_streams",
    "run_qualification",
]
