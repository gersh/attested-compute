# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded real-Arb factor-artifact to resident-CUDA qualification.

This constructs a small inverse-DFT input whose primitive frequency values
are the conjugates of the direct completed-factor multipliers.  Therefore
both the direct-factor path and the checkpoint-recurrence path should classify
every completed value as positive.  The two paths must emit the same exact
compact state.

The input is synthetic and has no Dirichlet-L source semantics.  This is an
arithmetic/integration qualification only, never source or GRH evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from typing import Any, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER,
    canonical_component_orders,
)
from tg_verifier.dirichlet_completed_factor_artifacts import (
    write_bounded_arb_artifacts,
)
from tg_verifier.dirichlet_completed_sign_gpu_reducer import (
    _binary_box,
    _box_disk,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = (
    "tg-dirichlet-completed-factor-arb-resident-handoff-qualification-v1"
)
Q = 7
DIRECT_FACTOR_MAGIC = b"TGDCFCT1"
ROOT_HEADER = struct.Struct("<8sIIIIQ32s32s")
ROOT_RECORD = struct.Struct("<dddd")
FACTOR_HEADER = struct.Struct("<8sIIIIQQQQ")
DISK = struct.Struct("<ddd")


class DirichletCompletedFactorArbHandoffError(RuntimeError):
    """The bounded real-Arb recurrence handoff differed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompletedFactorArbHandoffError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_new(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _fail(f"refusing to replace qualification artifact: {path}")
    path.write_bytes(raw)
    return _sha256(raw)


def _coordinates(ordinal: int, orders: tuple[int, ...]) -> tuple[int, ...]:
    coordinates = []
    for order in orders:
        ordinal, coordinate = divmod(ordinal, order)
        coordinates.append(coordinate)
    if ordinal:
        _fail("inverse-DFT coordinate overflow")
    return tuple(coordinates)


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def run_bounded_arb_handoff_qualification(
    *,
    directory: Path,
    runner: Path,
    device: int = 0,
    first_t_index: int = 0,
    sample_count: int = 8,
    precision: int = 384,
    checkpoint_span: int = 4,
) -> dict[str, Any]:
    """Run direct and recurrence factor paths on the same resident FFT."""

    if (
        not runner.is_file()
        or isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
        or isinstance(first_t_index, bool)
        or not isinstance(first_t_index, int)
        or first_t_index < 0
        or isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or not 1 <= sample_count <= 64
        or isinstance(precision, bool)
        or not isinstance(precision, int)
        or not 128 <= precision <= 4096
        or not 1 <= checkpoint_span <= sample_count
    ):
        _fail("bounded Arb handoff parameters differ")
    try:
        from flint import acb, arb, ctx
        from tg_verifier.dirichlet_root_number_stage import (
            direct_root_records,
            primitive_frequency_records_bulk,
            require_flint,
        )
    except ImportError as error:
        raise DirichletCompletedFactorArbHandoffError(
            "pinned python-flint is required"
        ) from error
    require_flint()
    directory = directory.resolve()
    if directory.exists():
        _fail("qualification directory must be absent")
    directory.mkdir(parents=True)
    orders = canonical_component_orders(Q)
    group_order = math.prod(orders)
    previous_precision = ctx.prec
    try:
        ctx.prec = precision
        roots = direct_root_records(Q, precision=precision)
        identities = primitive_frequency_records_bulk(Q)
        if len(roots) != len(identities) or not roots:
            _fail("direct root inventory differs")
        t_values = tuple(
            arb(5 * (first_t_index + sample)) / 64
            for sample in range(sample_count)
        )
        conductor = tuple(
            acb(0, t * (arb(Q) / arb.pi()).log() / 2).exp()
            for t in t_values
        )
        factors = tuple(
            conductor[sample]
            * acb(arb(1 + 2 * parity) / 4, t / 2).gamma()
            * (arb.pi() * t / 4).exp()
            for parity in (0, 1)
            for sample, t in enumerate(t_values)
        )
        input_boxes: list[tuple[float, float, float, float]] = []
        for sample in range(sample_count):
            frequencies = [acb(0) for _ in range(group_order)]
            for identity, root in zip(identities, roots, strict=True):
                if (
                    identity["primitive_ordinal"]
                    != root["primitive_ordinal"]
                ):
                    _fail("root and primitive ordinal differ")
                parity = identity["parity"]
                factor = factors[parity * sample_count + sample]
                frequencies[identity["frequency_id"]] = (
                    root["hardy_multiplier"] * factor
                ).conjugate()
            for exponent_id in range(group_order):
                exponent = _coordinates(exponent_id, orders)
                value = acb(0)
                for frequency_id, frequency_value in enumerate(frequencies):
                    frequency = _coordinates(frequency_id, orders)
                    phase = sum(
                        arb(left * right) / order
                        for left, right, order in zip(
                            exponent, frequency, orders, strict=True
                        )
                    )
                    value += frequency_value * acb(
                        0, -2 * arb.pi() * phase
                    ).exp()
                input_boxes.append(_binary_box(value / group_order))
        root_boxes = tuple(
            _binary_box(record["hardy_multiplier"]) for record in roots
        )
        factor_disks = tuple(
            _box_disk(_binary_box(value)) for value in factors
        )
    finally:
        ctx.prec = previous_precision

    input_path = directory / "input.bin"
    root_path = directory / "roots.bin"
    direct_factor_path = directory / "direct-factors.bin"
    input_raw = bytearray(
        INPUT_HEADER.pack(
            b"TGDAFFI1",
            1,
            Q,
            len(orders),
            sample_count,
            group_order,
            first_t_index * 5,
            64,
            5,
            group_order * sample_count,
            0,
        )
    )
    for box in input_boxes:
        input_raw.extend(COMPLEX_INTERVAL.pack(*box))
    input_sha256 = _write_new(input_path, bytes(input_raw))
    root_raw = bytearray(
        ROOT_HEADER.pack(
            b"TGDRNRO1",
            1,
            Q,
            len(orders),
            ROOT_RECORD.size,
            len(root_boxes),
            bytes.fromhex("31" * 32),
            bytes.fromhex("32" * 32),
        )
    )
    for box in root_boxes:
        root_raw.extend(ROOT_RECORD.pack(*box))
    root_sha256 = _write_new(root_path, bytes(root_raw))
    direct_factor_raw = bytearray(
        FACTOR_HEADER.pack(
            DIRECT_FACTOR_MAGIC,
            1,
            Q,
            sample_count,
            0,
            first_t_index * 5,
            64,
            5,
            2 * sample_count,
        )
    )
    for disk in factor_disks:
        direct_factor_raw.extend(DISK.pack(*disk))
    direct_factor_sha256 = _write_new(
        direct_factor_path, bytes(direct_factor_raw)
    )
    recurrence = write_bounded_arb_artifacts(
        directory / "recurrence",
        q=Q,
        first_t_index=first_t_index,
        sample_count=sample_count,
        precision=precision,
        checkpoint_span=checkpoint_span,
    )

    direct_state = directory / "direct-state.bin"
    direct_summary = directory / "direct-summary.json"
    recurrence_state = directory / "recurrence-state.bin"
    recurrence_summary = directory / "recurrence-summary.json"
    direct_command = (
        str(runner.resolve()),
        "--bounded-resident-completed-sign-handoff",
        str(input_path),
        str(root_path),
        root_sha256,
        str(direct_factor_path),
        direct_factor_sha256,
        str(direct_state),
        str(direct_summary),
        str(device),
    )
    recurrence_command = (
        str(runner.resolve()),
        "--bounded-resident-completed-sign-arb-recurrence-handoff",
        str(input_path),
        str(root_path),
        root_sha256,
        recurrence["producer_identity_sha256"],
        recurrence["gamma_path"],
        recurrence["gamma_sha256"],
        recurrence["step_path"],
        recurrence["step_sha256"],
        recurrence["checkpoint_path"],
        recurrence["checkpoint_sha256"],
        str(recurrence_state),
        str(recurrence_summary),
        str(device),
    )
    for label, command in (
        ("direct", direct_command),
        ("recurrence", recurrence_command),
    ):
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0 or completed.stdout:
            _fail(
                f"{label} resident handoff failed: "
                + completed.stderr[-4096:].decode(
                    "utf-8", errors="replace"
                )
            )
    direct_raw = direct_state.read_bytes()
    recurrence_raw = recurrence_state.read_bytes()
    if direct_raw != recurrence_raw:
        _fail("direct and Arb-recurrence compact states differ")
    direct_record = json.loads(direct_summary.read_text("ascii"))
    recurrence_record = json.loads(recurrence_summary.read_text("ascii"))
    if (
        direct_record["factor_checkpoint_recurrence_path"]
        or not recurrence_record["factor_checkpoint_recurrence_path"]
        or recurrence_record["classification"]
        != (
            "bounded_real_arb_recurrence_qualification_"
            "not_source_or_atom_closure"
        )
        or recurrence_record["expected_factor_producer_sha256"]
        != recurrence["producer_identity_sha256"]
        or recurrence_record["source_factor_recurrence_path"]
        or recurrence_record["source_packed_state_path"]
        or recurrence_record["external_atom_discharged"]
        or direct_record["state_sha256"]
        != recurrence_record["state_sha256"]
    ):
        _fail("bounded Arb handoff summary boundary differs")
    report: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_factor_artifacts."
            "arb_resident_handoff_qualification.v1"
        ),
        "algorithm": ALGORITHM_ID,
        "author": AUTHOR,
        "classification": (
            "bounded_synthetic_inverse_dft_real_arb_factor_"
            "qualification_not_source_evidence"
        ),
        "q": Q,
        "first_t_index": first_t_index,
        "sample_count": sample_count,
        "precision_bits": precision,
        "checkpoint_span": checkpoint_span,
        "input_sha256": input_sha256,
        "root_sha256": root_sha256,
        "direct_factor_sha256": direct_factor_sha256,
        "gamma_sha256": recurrence["gamma_sha256"],
        "step_sha256": recurrence["step_sha256"],
        "checkpoint_sha256": recurrence["checkpoint_sha256"],
        "producer_identity_sha256": recurrence[
            "producer_identity_sha256"
        ],
        "compact_state_sha256": direct_record["state_sha256"],
        "compact_state_bytes": len(direct_raw),
        "direct_and_recurrence_compact_state_byte_identical": True,
        "TGDAFFO1_device_to_host_bytes": 0,
        "phase_state_device_to_host_bytes": 0,
        "per_frame_count_device_to_host_bytes": 0,
        "source_range_qualified": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    report["qualification_sha256"] = _sha256(_canonical_json(report))
    return report


__all__ = [
    "ALGORITHM_ID",
    "DirichletCompletedFactorArbHandoffError",
    "run_bounded_arb_handoff_qualification",
]
