#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and retain provenance for the CH25 psi candidate/reference pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402


PRIMESIEVE_COMMIT = "4f85384851da23c36c01ec01ef85b5d9d246e556"
CRLIBM_COMMIT = "eb3063791aa75bc9705b49283bf14250465220a7"


class BuildError(RuntimeError):
    """The qualification build did not complete exactly."""


def file_identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def capture(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise BuildError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def build(
    *,
    compiler: Path,
    source: Path,
    gpu_include: Path,
    boost_include: Path,
    crlibm_include: Path,
    primesieve_include: Path,
    primesieve_library: Path,
    crlibm_library: Path,
    output: Path,
    depfile: Path,
    literal_reference: bool,
) -> tuple[list[str], str]:
    command = [
        os.fspath(compiler),
        "-std=c++20",
        "-O3",
        "-DNDEBUG",
        "-march=native",
        "-mtune=native",
        "-fno-fast-math",
        "-fno-associative-math",
        "-ffp-contract=off",
        "-frounding-math",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-MMD",
        "-MF",
        os.fspath(depfile),
        f'-DSPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT="{CRLIBM_COMMIT}"',
        f'-DSPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT="{PRIMESIEVE_COMMIT}"',
    ]
    if literal_reference:
        command.append("-DSPARKINTERVAL_PSI_LITERAL_REFERENCE=1")
    command += [
        f"-I{gpu_include}",
        f"-I{boost_include}",
        f"-I{crlibm_include}",
        f"-I{primesieve_include}",
        os.fspath(source),
        os.fspath(primesieve_library),
        os.fspath(crlibm_library),
        "-lm",
        "-o",
        os.fspath(output),
    ]
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise BuildError(
            f"compile failed ({completed.returncode}):\n"
            f"{completed.stdout}"
        )
    if not output.is_file() or not os.access(output, os.X_OK):
        raise BuildError("compiler did not create an executable")
    if not depfile.is_file():
        raise BuildError("compiler did not retain a dependency file")
    return command, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default="g++")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "reference" / "tg_psi_residual_shard.cpp",
    )
    parser.add_argument(
        "--gpu-include", type=Path, default=ROOT / "gpu" / "include"
    )
    parser.add_argument("--boost-include", required=True, type=Path)
    parser.add_argument("--crlibm-include", required=True, type=Path)
    parser.add_argument("--primesieve-include", required=True, type=Path)
    parser.add_argument("--primesieve-library", required=True, type=Path)
    parser.add_argument("--crlibm-library", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    resolved_compiler = shutil.which(arguments.compiler)
    if resolved_compiler is None:
        raise BuildError(f"compiler is not on PATH: {arguments.compiler}")
    compiler = Path(resolved_compiler).resolve()
    inputs = {
        "source": arguments.source.resolve(),
        "gpu_include": arguments.gpu_include.resolve(),
        "boost_include": arguments.boost_include.resolve(),
        "crlibm_include": arguments.crlibm_include.resolve(),
        "primesieve_include": arguments.primesieve_include.resolve(),
        "primesieve_library": arguments.primesieve_library.resolve(),
        "crlibm_library": arguments.crlibm_library.resolve(),
    }
    for name, path in inputs.items():
        expected_directory = name.endswith("_include")
        if (expected_directory and not path.is_dir()) or (
            not expected_directory and not path.is_file()
        ):
            raise BuildError(f"{name} does not exist with the expected type")
    output_directory = arguments.output_directory.resolve()
    manifest = arguments.manifest.resolve()
    if output_directory.exists():
        raise BuildError(f"refusing to reuse output directory: {output_directory}")
    if manifest.exists():
        raise BuildError(f"refusing to overwrite manifest: {manifest}")
    output_directory.mkdir(parents=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    records: dict[str, Any] = {}
    for label, literal in (("candidate", False), ("literal_reference", True)):
        output = output_directory / label
        depfile = output_directory / f"{label}.d"
        command, compiler_output = build(
            compiler=compiler,
            source=inputs["source"],
            gpu_include=inputs["gpu_include"],
            boost_include=inputs["boost_include"],
            crlibm_include=inputs["crlibm_include"],
            primesieve_include=inputs["primesieve_include"],
            primesieve_library=inputs["primesieve_library"],
            crlibm_library=inputs["crlibm_library"],
            output=output,
            depfile=depfile,
            literal_reference=literal,
        )
        records[label] = {
            "macro_mode": (
                "optimized_square_filter_and_compile_time_dispatch"
                if not literal
                else "literal_integer_sqrt_filter_and_runtime_dispatch"
            ),
            "literal_reference_macro": literal,
            "argv": command,
            "compiler_output": compiler_output,
            "executable": file_identity(output),
            "dependency_file": {
                **file_identity(depfile),
                "text": depfile.read_text(encoding="utf-8"),
            },
        }

    value = {
        "schema": "sparkinterval.tg.psi-qualification-build.v1",
        "classification": (
            "local_source_build_identity_not_compiler_or_cpu_refinement"
        ),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "compiler": {
            "requested": arguments.compiler,
            "resolved_path": os.fspath(compiler),
            **file_identity(compiler),
            "version": capture([os.fspath(compiler), "--version"]),
            "dumpmachine": capture([os.fspath(compiler), "-dumpmachine"]).strip(),
            "dumpversion": capture(
                [os.fspath(compiler), "-dumpfullversion", "-dumpversion"]
            ).strip(),
        },
        "source": {
            "path": os.fspath(inputs["source"]),
            **file_identity(inputs["source"]),
        },
        "linked_inputs": {
            "primesieve": {
                "commit": PRIMESIEVE_COMMIT,
                **file_identity(inputs["primesieve_library"]),
            },
            "crlibm": {
                "commit": CRLIBM_COMMIT,
                **file_identity(inputs["crlibm_library"]),
            },
        },
        "builds": records,
        "capabilities": {
            "both_modes_built_from_identical_source_bytes": True,
            "compiler_refinement_proved": False,
            "cpu_refinement_proved": False,
            "source_run_completed": False,
            "execution_attested": False,
            "lean_atom_discharged": False,
        },
    }
    raw = canonical_json_bytes(value)
    with manifest.open("xb") as stream:
        if stream.write(raw) != len(raw):
            raise BuildError("short build-manifest write")
    print(
        json.dumps(
            {
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "source": value["source"],
                "compiler": value["compiler"],
                "builds": {
                    label: record["executable"]
                    for label, record in records.items()
                },
                "capabilities": value["capabilities"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
