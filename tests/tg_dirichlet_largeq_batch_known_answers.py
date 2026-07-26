#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Replay a fused CUDA batch against the scalar and MPFR composition paths."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import (  # noqa: E402
    rehash_job_artifact,
    write_job,
)
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    INPUT_HEADER as AFFINE_HEADER,
    read_input_header,
)
from tg_verifier.dirichlet_largeq_batch import (  # noqa: E402
    INPUT_HEADER as BATCH_HEADER,
    pack_input,
    write_job_from_composition_job,
)
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    CompositionEngine,
)


def _run(command: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
    )


def _nested_or_equal(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    a_contains_b = a[0] <= b[0] <= b[1] <= a[1] and a[2] <= b[2] <= b[3] <= a[3]
    b_contains_a = b[0] <= a[0] <= a[1] <= b[1] and b[2] <= a[2] <= a[3] <= b[3]
    return a_contains_b or b_contains_a


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--lattice-checker", type=Path, required=True)
    parser.add_argument("--composition-checker", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        composition_job, frames = write_job(
            root / "composition", q=10_001, t_indices=(127, 128)
        )
        # The stock synthetic composition fixture's TGDLATO1 is arbitrary.
        # Replace it with the exact Taylor checker output from the same zero
        # lattice used by the fused runner, then update only the synthetic job
        # hash records.
        for index, frame in enumerate(frames):
            exact = frame["lattice_output"].with_suffix(".exact")
            _run(
                [
                    str(args.lattice_checker.resolve()),
                    "compute",
                    str(frame["lattice_input"]),
                    str(exact),
                ],
                quiet=True,
            )
            os.replace(exact, frame["lattice_output"])
            rehash_job_artifact(composition_job, index, "lattice_output")

        scalar_output = root / "scalar.bin"
        CompositionEngine(backend="scalar").compose(
            composition_job, scalar_output, allow_synthetic_kat=True
        )
        batch_job = root / "batch-job.json"
        write_job_from_composition_job(
            composition_job, batch_job, certified=False
        )
        batch_input = root / "batch-input.bin"
        pack_input(batch_job, batch_input, allow_synthetic_kat=True)
        cuda_output = root / "cuda.bin"
        runner = _run(
            [
                str(args.runner.resolve()),
                str(batch_input),
                str(cuda_output),
                str(args.device),
                "1",
            ],
            quiet=True,
        )
        runner_report = json.loads(runner.stdout)
        parsed = read_input_header(cuda_output)
        if (
            parsed["q"] != 10_001
            or parsed["batch_count"] != 2
            or parsed["value_count"] != 19_584
            or runner_report["kernel_launches"] != 1
            or runner_report["transcendental_device_calls"] != 0
        ):
            raise RuntimeError("fused runner identity or launch count changed")

        mpfr_command = [
            str(args.composition_checker.resolve()),
            "verify",
            str(cuda_output),
            "384",
        ]
        for frame in frames:
            mpfr_command.extend(
                [str(frame["lattice_output"]), str(frame["finite_recovery"])]
            )
        mpfr = _run(mpfr_command, quiet=True)
        mpfr_report = json.loads(mpfr.stdout)
        if (
            mpfr_report["value_count"] != 19_584
            or mpfr_report["precision_bits"] != 384
            or mpfr_report["external_atom_discharged"] is not False
        ):
            raise RuntimeError("independent MPFR replay report changed")

        cuda_raw = cuda_output.read_bytes()
        scalar_raw = scalar_output.read_bytes()
        if cuda_raw[:AFFINE_HEADER.size] != scalar_raw[:AFFINE_HEADER.size]:
            raise RuntimeError("CUDA and scalar TGDAFFI1 identities differ")
        nested = 0
        for index in range(parsed["value_count"]):
            offset = AFFINE_HEADER.size + index * COMPLEX_INTERVAL.size
            cuda_box = COMPLEX_INTERVAL.unpack_from(cuda_raw, offset)
            scalar_box = COMPLEX_INTERVAL.unpack_from(scalar_raw, offset)
            if not _nested_or_equal(cuda_box, scalar_box):
                raise RuntimeError(f"CUDA/scalar boxes disagree at value {index}")
            nested += 1

        # A canonical residue descriptor is independently reconstructed by the
        # runner.  Corrupting it must fail before any output is published.
        forged = root / "forged-input.bin"
        forged.write_bytes(batch_input.read_bytes())
        with forged.open("r+b") as target:
            target.seek(BATCH_HEADER.size)
            a, row = struct.unpack("<II", target.read(8))
            target.seek(BATCH_HEADER.size)
            target.write(struct.pack("<II", a + 1, row))
        rejected = subprocess.run(
            [
                str(args.runner.resolve()),
                str(forged),
                str(root / "forged-output.bin"),
                str(args.device),
                "1",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("runner accepted a forged CRT descriptor")

        # The source grid fixes denominator 64.  In particular, the optimized
        # exact 2^-6 ordinate scaling must never be reachable for a forged
        # denominator.
        forged_grid = root / "forged-grid-input.bin"
        forged_grid.write_bytes(batch_input.read_bytes())
        with forged_grid.open("r+b") as target:
            # InputHeader.t_denominator is the uint64 at byte offset 56.
            target.seek(56)
            target.write(struct.pack("<Q", 63))
        rejected_grid = subprocess.run(
            [
                str(args.runner.resolve()),
                str(forged_grid),
                str(root / "forged-grid-output.bin"),
                str(args.device),
                "1",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected_grid.returncode == 0:
            raise RuntimeError("runner accepted a non-source t denominator")

        service_composition, _ = write_job(
            root / "service-composition", q=10_001, t_indices=(129,)
        )
        service_job = root / "service-job.json"
        write_job_from_composition_job(
            service_composition, service_job, certified=False
        )
        service_input = root / "service-input.bin"
        pack_input(service_job, service_input, allow_synthetic_kat=True)
        service_summary = root / "service-summary.json"
        service_output = root / "service-output.bin"
        with service_output.open("wb") as output:
            service = subprocess.run(
                [
                    str(args.runner.resolve()),
                    "--framed-service",
                    "10001",
                    "64",
                    str(service_summary),
                    str(args.device),
                ],
                input=batch_input.read_bytes() + service_input.read_bytes(),
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if service.returncode != 0:
            raise RuntimeError(
                "persistent service failed: "
                + service.stderr.decode("utf-8", errors="replace")
            )
        summary = json.loads(service_summary.read_text("ascii"))
        stream = service_output.read_bytes()
        first_size = AFFINE_HEADER.size + 19_584 * COMPLEX_INTERVAL.size
        second_size = AFFINE_HEADER.size + 9_792 * COMPLEX_INTERVAL.size
        if (
            summary["frame_count"] != 2
            or summary["kernel_launches"] != 2
            or summary["value_count"] != 29_376
            or len(stream) != first_size + second_size
            or stream[:8] != b"TGDAFFI1"
            or stream[first_size : first_size + 8] != b"TGDAFFI1"
        ):
            raise RuntimeError("persistent framed service contract changed")

        print(
            json.dumps(
                {
                    "classification": "synthetic_cross_backend_kat_only",
                    "q": 10_001,
                    "batch_count": 2,
                    "value_count": nested,
                    "cuda_kernel_launches": 1,
                    "cuda_transcendental_calls": 0,
                    "scalar_nesting_passed": True,
                    "mpfr_384_bit_replay_passed": True,
                    "forged_descriptor_rejected": True,
                    "forged_source_grid_rejected": True,
                    "persistent_service_frames": 2,
                    "persistent_service_kernel_launches": 2,
                    "external_atom_discharged": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
