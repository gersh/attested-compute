#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Synthetic, explicitly non-analytic fixtures for residue-composition KATs."""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    DECISIONS,
    MANIFEST_SCHEMA,
    RECOVERY_FORMAT_VERSION,
    RECOVERY_HEADER,
    RECOVERY_ITEM,
    RECOVERY_MAGIC,
    REPLAY_SCHEMA,
    REQUEST_ENUMERATION,
    _source_record,
)
import tg_verifier.dirichlet_lattice_certificates as _lattice_certificates  # noqa: E402
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    FORMAT_VERSION as LATTICE_FORMAT_VERSION,
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    INPUT_ITEM as LATTICE_INPUT_ITEM,
    INPUT_MAGIC as LATTICE_INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    OUTPUT_HEADER as LATTICE_OUTPUT_HEADER,
    OUTPUT_ITEM as LATTICE_OUTPUT_ITEM,
    OUTPUT_MAGIC as LATTICE_OUTPUT_MAGIC,
    RECEIPT_SCHEMA as LATTICE_RECEIPT_SCHEMA,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
)
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CERTIFIED_CLASSIFICATION,
    JOB_SCHEMA,
    SYNTHETIC_CLASSIFICATION,
    artifact_record,
    canonical_json_bytes,
    sha256_bytes,
)


def _units(q: int) -> list[int]:
    return [a for a in range(1, q) if math.gcd(a, q) == 1]


def _zeta_box(a: int, t_index: int) -> tuple[float, float, float, float]:
    real = ((17 * a + 3 * t_index) % 251 - 125) / 64.0
    imag = ((29 * a + 5 * t_index) % 257 - 128) / 64.0
    radius = math.ldexp(1.0, -36)
    return real - radius, real + radius, imag - radius, imag + radius


def _recovery_box(a: int, t_index: int) -> tuple[float, float, float, float]:
    real = ((7 * a + t_index) % 61 - 30) / 256.0
    imag = ((11 * a + 2 * t_index) % 67 - 33) / 256.0
    radius = math.ldexp(1.0, -39)
    return real - radius, real + radius, imag - radius, imag + radius


def write_frame(root: Path, *, q: int, t_index: int, m: int = 4) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    units = _units(q)
    t_numerator = 5 * t_index
    lattice_input = root / "lattice-input.bin"
    with lattice_input.open("wb") as output:
        output.write(
            LATTICE_INPUT_HEADER.pack(
                LATTICE_INPUT_MAGIC,
                LATTICE_FORMAT_VERSION,
                LATTICE_ROWS,
                TAYLOR_DEGREE,
                0,
                t_numerator,
                64,
                len(units),
                LATTICE_ROWS * TAYLOR_COLUMNS,
                0,
            )
        )
        output.write(bytes(LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size))
        for a in units:
            output.write(
                LATTICE_INPUT_ITEM.pack(
                    q, a, canonical_lattice_row(q, a), 0, math.ldexp(1.0, -42)
                )
            )

    lattice_output = root / "lattice-output.bin"
    with lattice_output.open("wb") as output:
        output.write(
            LATTICE_OUTPUT_HEADER.pack(
                LATTICE_OUTPUT_MAGIC,
                LATTICE_FORMAT_VERSION,
                LATTICE_ROWS,
                TAYLOR_DEGREE,
                0,
                len(units),
                0,
                0,
            )
        )
        for a in units:
            output.write(
                LATTICE_OUTPUT_ITEM.pack(
                    q,
                    a,
                    canonical_lattice_row(q, a),
                    0,
                    *_zeta_box(a, t_index),
                )
            )

    finite_recovery = root / "finite-recovery.bin"
    with finite_recovery.open("wb") as output:
        output.write(
            RECOVERY_HEADER.pack(
                RECOVERY_MAGIC,
                RECOVERY_FORMAT_VERSION,
                m,
                0,
                t_numerator,
                64,
                len(units),
                0,
            )
        )
        for a in units:
            output.write(
                RECOVERY_ITEM.pack(q, a, 0, 0, *_recovery_box(a, t_index))
            )
    return {
        "lattice_input": lattice_input,
        "lattice_output": lattice_output,
        "finite_recovery": finite_recovery,
    }


def write_job(
    root: Path, *, q: int = 10_001, t_indices: tuple[int, ...] = (127, 128)
) -> tuple[Path, list[dict[str, Path]]]:
    if not t_indices or any(
        right != left + 1 for left, right in zip(t_indices, t_indices[1:])
    ):
        raise ValueError("fixture ordinates must be nonempty and consecutive")
    frames = [
        write_frame(root / f"frame-{index}", q=q, t_index=t_index)
        for index, t_index in enumerate(t_indices)
    ]
    job = {
        "schema": JOB_SCHEMA,
        "schema_version": 1,
        "classification": SYNTHETIC_CLASSIFICATION,
        "q": q,
        "first_t_numerator": 5 * t_indices[0],
        "t_denominator": 64,
        "t_step_numerator": 5,
        "frames": [
            {
                name: artifact_record(path, relative_to=root)
                for name, path in frame.items()
            }
            for frame in frames
        ],
    }
    path = root / "job.json"
    path.write_bytes(canonical_json_bytes(job))
    return path, frames


def rehash_job_artifact(job_path: Path, frame_index: int, name: str) -> None:
    value = json.loads(job_path.read_text("ascii"))
    path = job_path.parent / value["frames"][frame_index][name]["path"]
    value["frames"][frame_index][name] = artifact_record(
        path, relative_to=job_path.parent
    )
    job_path.write_bytes(canonical_json_bytes(value))


def write_structural_certified_job(
    root: Path, *, q: int = 10_001, t_indices: tuple[int, ...] = (127,)
) -> tuple[Path, list[dict[str, Path]]]:
    """Build metadata-contract fixtures; these are not analytic certificates."""

    synthetic_job, frames = write_job(root, q=q, t_indices=t_indices)
    synthetic_job.unlink()
    units = _units(q)
    request_digest = __import__("hashlib").sha256()
    for a in units:
        request_digest.update(
            __import__("struct").pack("<III", q, a, canonical_lattice_row(q, a))
        )
    frame_records = []
    runtime = {
        "python_implementation": "CPython",
        "python_version": "test",
        "python_executable": {
            "filename": "python-test", "sha256": "4" * 64, "size_bytes": 1
        },
        "python_flint_version": "0.9.0",
        "flint_version": "3.6.0",
        "flint_release": 30_600,
        "machine": "test",
        "extensions": {
            name: {"filename": f"{name}.so", "sha256": "5" * 64, "size_bytes": 1}
            for name in (
                "pyflint", "flint_context", "acb", "arb", "arf", "fmpq", "fmpz"
            )
        },
        "flint_threads": 1,
    }
    producer = artifact_record(Path(_lattice_certificates.__file__))
    for index, (t_index, frame) in enumerate(zip(t_indices, frames)):
        from fractions import Fraction

        t = Fraction(5 * t_index, 64)
        certificate = {
            "schema": MANIFEST_SCHEMA,
            "schema_version": 1,
            "author": "Gershon Bialer",
            "atom_id": "platt-dirichlet-theorem-7-1",
            "algorithm_id": "platt-dirichlet-certified-lattice-input-v1",
            "checker_id": "higher-precision-flint-plus-exact-rational-tail-v1",
            "classification": "source_shaped_certified_analytic_batch_not_theorem_7_1",
            "source": _source_record(),
            "parameters": {
                "q_start_inclusive": q,
                "q_stop_inclusive": q,
                "t_index": t_index,
                "t": {"numerator": str(t.numerator), "denominator": str(t.denominator)},
                "D": 2048,
                "N": 15,
                "columns": 16,
                "M": 4,
                "generation_precision_bits": 192,
                "second_generation_precision_bits": 256,
                "max_items": None,
            },
            "requests": {
                "count": len(units),
                "sha256_le_u32_q_a_row": request_digest.hexdigest(),
                "first": {
                    "q": q, "a": units[0],
                    "row": canonical_lattice_row(q, units[0]),
                },
                "last": {
                    "q": q, "a": units[-1],
                    "row": canonical_lattice_row(q, units[-1]),
                },
                "enumeration": REQUEST_ENUMERATION,
            },
            "uniform_taylor_tail": {"classification": "test_metadata_only"},
            "artifacts": {
                "lattice-input.bin": {
                    key: value for key, value in artifact_record(frame["lattice_input"]).items()
                    if key != "path"
                },
                "finite-recovery.bin": {
                    key: value for key, value in artifact_record(frame["finite_recovery"]).items()
                    if key != "path"
                },
                "producer_module": {
                    "sha256": producer["sha256"],
                    "size_bytes": producer["size_bytes"],
                },
            },
            "generator_runtime": runtime,
            "decisions": DECISIONS,
        }
        certificate["certificate_sha256"] = sha256_bytes(
            canonical_json_bytes(certificate)
        )
        certificate_path = frame["lattice_input"].parent / "certificate.json"
        certificate_path.write_bytes(canonical_json_bytes(certificate))

        replay = {
            "schema": REPLAY_SCHEMA,
            "schema_version": 1,
            "classification": "complete_input_bundle_replay_not_theorem_7_1",
            "certificate_sha256": certificate["certificate_sha256"],
            "replay_precision_bits": 320,
            "lattice_cells_replayed": 2048 * 16,
            "finite_recovery_values_replayed": len(units),
            "uniform_tail_replayed_exactly": True,
            "strict_request_geometry_replayed": True,
            "higher_precision_arb_containment_passed": True,
            "generator_runtime": certificate["generator_runtime"],
            "replay_runtime": runtime,
            "same_runtime_binary": True,
            "elapsed_seconds": 0.0,
            "external_atom_discharged": False,
        }
        replay["replay_sha256"] = sha256_bytes(canonical_json_bytes(replay))
        replay_path = frame["lattice_input"].parent / "replay.json"
        replay_path.write_bytes(canonical_json_bytes(replay))

        input_artifact = artifact_record(frame["lattice_input"])
        output_artifact = artifact_record(frame["lattice_output"])
        certificate_artifact = artifact_record(certificate_path)
        receipt = {
            "schema": LATTICE_RECEIPT_SCHEMA,
            "schema_version": 1,
            "author": "Gershon Bialer",
            "atom_id": "platt-dirichlet-theorem-7-1",
            "algorithm_id": "platt-dirichlet-large-q-lattice-taylor-stage-v1",
            "checker_id": "cpu-exact-rational-natural-interval-v1",
            "source_plan_sha256": "1" * 64,
            "classification": "conditional_taylor_stage_with_external_lattice_certificate",
            "input": {
                "sha256": input_artifact["sha256"],
                "size_bytes": input_artifact["size_bytes"],
                "t": {"numerator": 5 * t_index, "denominator": 64},
                "item_count": len(units),
                "first_request": {"q": q, "a": units[0]},
                "last_request": {"q": q, "a": units[-1]},
            },
            "artifacts": {
                "runner": {"sha256": "2" * 64, "size_bytes": 1},
                "checker": {"sha256": "3" * 64, "size_bytes": 1},
                "output": {
                    "sha256": output_artifact["sha256"],
                    "size_bytes": output_artifact["size_bytes"],
                },
                "lattice_certificate": {
                    "sha256": certificate_artifact["sha256"],
                    "size_bytes": certificate_artifact["size_bytes"],
                },
            },
            "decisions": {
                "canonical_input_replayed": True,
                "exact_rational_arithmetic_replay_passed": True,
                "lattice_semantics_proved_by_this_receipt": False,
                "taylor_tail_bound_proved_by_this_receipt": False,
                "unit_group_fft_completed": False,
                "turing_completeness_completed": False,
                "external_atom_discharged": False,
            },
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
        receipt_path = frame["lattice_input"].parent / "receipt.json"
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        frame_records.append(
            {
                "lattice_input": artifact_record(frame["lattice_input"], relative_to=root),
                "lattice_output": artifact_record(frame["lattice_output"], relative_to=root),
                "finite_recovery": artifact_record(frame["finite_recovery"], relative_to=root),
                "lattice_certificate": artifact_record(certificate_path, relative_to=root),
                "lattice_replay": artifact_record(replay_path, relative_to=root),
                "lattice_stage_receipt": artifact_record(receipt_path, relative_to=root),
            }
        )
    job = {
        "schema": JOB_SCHEMA,
        "schema_version": 1,
        "classification": CERTIFIED_CLASSIFICATION,
        "q": q,
        "first_t_numerator": 5 * t_indices[0],
        "t_denominator": 64,
        "t_step_numerator": 5,
        "frames": frame_records,
    }
    path = root / "job.json"
    path.write_bytes(canonical_json_bytes(job))
    return path, frames


__all__ = [
    "rehash_job_artifact",
    "write_frame",
    "write_job",
    "write_structural_certified_job",
]
