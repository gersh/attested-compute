#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build the smallest challenge-first Azure H100 measured-runner pilot.

The pilot is the one-row, zero-variable ``ReferenceBatch`` already modeled in
``SparkInterval.Tests.FormalPTXProgramTest``: its expression is the constant
binary64 interval [1,1].  The tool emits Lean-generated ``sm_90`` PTX, an
offline cubin, PTX/SASS audits, a static measured wrapper, an independently
compiled static trace verifier, and a measured-runner job specification.

Every build reports ``accepted: false``.  A production policy, x86_64 build in
the exact measured Azure image, real NCC H100 evidence, and relying-party
appraisal are still required.  The closed Lean invocation and importer mapping
exist, but the tracked trusted-compute receipt registry deliberately remains
empty until a real receipt is independently appraised and source-reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "tools"))
sys.path.insert(0, str(REPOSITORY_ROOT / "azure"))

from create_run_bundle import (  # noqa: E402
    canonical_json_bytes,
    canonical_sha256,
    load_profile,
    parse_json_bytes,
)
from measured_runner import _closure_manifest, _elf_has_interp, validate_job_spec  # noqa: E402


ALGORITHM_ID = "sparkinterval.pilot.h100-formal-ptx-constant-one.v1"
FORMAL_BATCH = (
    b'{"algorithm":"sparkinterval.binary64_interval_expr.v1",'
    b'"expression":{"op":"const","value":{"hi":"3ff0000000000000",'
    b'"lo":"3ff0000000000000"}},"kind":"sparkinterval_reference_batch",'
    b'"rows":[[]],"schema_version":1,"variable_count":0}'
)
FORMAL_SCOPE_DESCRIPTION = (
    "sparkinterval.h100-formal-ptx-pilot.v1\n"
    "formal-input=canonical SparkInterval.PTX.ReferenceBatch with zero variables, one row, and constant [0x3ff0000000000000,0x3ff0000000000000]\n"
    "formal-emission=SparkInterval.PTX.buildModule then target-selected renderUncheckedFor sm_90\n"
    "device-execution=one invocation of the pinned generated PTX cubin on exactly one NVIDIA H100 compute-capability 9.0 device\n"
    "result=canonical UTF-8 manifest for one [1,1] interval with status 0\n"
    "formal-scope=typed PTX generation and reference result; external-scope=ptxas lowering, CUDA driver execution, measured image, and hardware attestation"
)
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.v1\n"
    "algorithm=h100-formal-ptx-constant-one\n"
    "initial=SHA256(initial-domain || challenge_nonce || job_binding_sha256 || formal_batch_sha256 || formal_ptx_sha256 || cubin_sha256 || driver_sha256 || result_sha256 || driver_report_sha256)\n"
    "step=SHA256(step-domain || previous || iteration=0 || expected_interval=3ff0000000000000:3ff0000000000000 || status=0)\n"
    "driver-report=independently checked exact H100/sm_90/challenge/cubin/input/raw-output bindings\n"
    "iteration-count=1"
)
EXPECTED_RESULT = (
    b'{"format":"sparkinterval_h100_formal_ptx_pilot_result_v1",'
    b'"hi":"3ff0000000000000","lo":"3ff0000000000000",'
    b'"row_count":1,"schema_version":1,"status":0,"target":"sm_90"}'
)
ROWS_FILE = struct.pack("<8sIIQ", b"SIG64I01", 1, 0, 1)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
DEFAULT_NVIDIA_POLICY = REPOSITORY_ROOT / "attestation/policies/gpu_prover_h100.rego"
PINNED_FORMAL_PTX = (
    REPOSITORY_ROOT
    / "examples/trusted-compute/h100_formal_ptx_constant_one.sm_90.ptx"
)


class BuildError(RuntimeError):
    pass


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _write(path: Path, content: bytes, mode: int = 0o400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        mode,
    )
    try:
        view = memoryview(content)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise BuildError(f"short write to {path}")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy(source: Path, destination: Path, mode: int) -> None:
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise BuildError(f"cannot resolve source {source}: {error}") from error
    if source.is_symlink() or not resolved.is_file():
        raise BuildError(f"source must be a regular non-symlink file: {source}")
    _write(destination, resolved.read_bytes(), mode)


def _executable(value: str | Path, what: str) -> Path:
    text = str(value)
    candidate = Path(text)
    if candidate.parent != Path(".") or candidate.is_absolute():
        path = candidate.resolve()
    else:
        located = shutil.which(text)
        if located is None:
            raise BuildError(f"required {what} executable is absent: {text}")
        path = Path(located).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise BuildError(f"{what} is not an executable file: {path}")
    return path


def _run(
    argv: Sequence[str | Path],
    *,
    cwd: Path,
    what: str,
    stdout_path: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    command = [str(item) for item in argv]
    try:
        if stdout_path is None:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "TZ": "UTC",
                },
                check=False,
                capture_output=True,
            )
        else:
            stdout_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with stdout_path.open("xb") as output:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env={
                        "LANG": "C",
                        "LC_ALL": "C",
                        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                        "TZ": "UTC",
                    },
                    check=False,
                    stdout=output,
                    stderr=subprocess.PIPE,
                )
    except OSError as error:
        raise BuildError(f"{what} could not start: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or b"")[-4000:].decode(
            "utf-8", "replace"
        )
        raise BuildError(f"{what} failed ({completed.returncode}): {detail}")
    return completed


def _elf_machine(path: Path) -> int:
    header = path.read_bytes()[:20]
    if len(header) != 20 or header[:4] != b"\x7fELF":
        raise BuildError(f"expected ELF executable: {path}")
    if header[5] == 1:
        return int.from_bytes(header[18:20], "little")
    if header[5] == 2:
        return int.from_bytes(header[18:20], "big")
    raise BuildError(f"ELF has invalid byte order: {path}")


def _tool_identity(path: Path, version_argv: Sequence[str] | None = None) -> dict[str, Any]:
    digest, size = _hash(path)
    result: dict[str, Any] = {
        "path_basename": path.name,
        "sha256": digest,
        "size_bytes": size,
    }
    if version_argv is not None:
        completed = _run([path, *version_argv], cwd=REPOSITORY_ROOT, what=f"{path.name} version")
        result["version_output_sha256"] = _digest_bytes(
            completed.stdout + completed.stderr
        )
    return result


def _artifact(
    root: Path,
    relative: str,
    role: str,
    *,
    executable: bool = False,
    statement_role: str | None = None,
) -> dict[str, Any]:
    path = root / relative
    digest, size = _hash(path)
    return {
        "executable": executable,
        "path": relative,
        "role": role,
        "sha256": digest,
        "size_bytes": size,
        "statement_role": statement_role,
    }


def _compile_static(
    compiler: Path,
    source: Path,
    output: Path,
    include_dirs: Sequence[Path],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    argv: list[str | Path] = [
        compiler,
        "-std=c++20",
        "-O3",
        "-DNDEBUG",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        "-Werror",
        "-fno-ident",
        "-fno-record-gcc-switches",
        "-static",
        "-s",
        "-Wl,--build-id=none",
    ]
    for directory in include_dirs:
        argv.extend(["-I", directory])
    argv.extend([source, "-o", output])
    _run(argv, cwd=REPOSITORY_ROOT, what=f"static build of {source.name}")
    os.chmod(output, 0o500)
    if _elf_has_interp(output):
        raise BuildError(f"static pilot executable declares PT_INTERP: {output}")


def _validate_policy(
    runner_policy_path: Path,
    nvidia_policy_path: Path,
    classification: str,
    allow_development_policy: bool,
) -> dict[str, Any]:
    try:
        raw_policy = runner_policy_path.read_bytes()
        runner_policy = parse_json_bytes(raw_policy, "measured-runner policy")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise BuildError(f"cannot parse runner policy: {error}") from error
    if not isinstance(runner_policy, dict):
        raise BuildError("runner policy must be a JSON object")
    canonical = canonical_json_bytes(runner_policy)
    if raw_policy not in (canonical, canonical + b"\n"):
        raise BuildError("runner policy must use canonical JSON bytes")
    if classification == "production":
        if (
            runner_policy.get("classification") != "production"
            or runner_policy.get("production_ready") is not True
        ):
            raise BuildError("production packaging requires an explicitly production-ready runner policy")
        if nvidia_policy_path.resolve() == DEFAULT_NVIDIA_POLICY.resolve():
            raise BuildError("production packaging rejects the checked-in development NVIDIA policy")
        if platform.machine().lower() not in ("x86_64", "amd64"):
            raise BuildError("production Azure NCC packaging must run on x86_64")
    else:
        if not allow_development_policy:
            raise BuildError("development packaging requires --allow-development-policy")
        if runner_policy.get("classification") == "production":
            raise BuildError("a production runner policy must not be relabeled development")
    if not nvidia_policy_path.is_file() or nvidia_policy_path.is_symlink():
        raise BuildError("NVIDIA appraisal policy must be a regular non-symlink file")
    return runner_policy


def build(
    output_root: Path,
    *,
    compiler: str | Path,
    generator: str | Path,
    driver: str | Path,
    ptxas: str | Path,
    nvdisasm: str | Path,
    runner_policy_path: Path,
    nvidia_policy_path: Path,
    classification: str,
    allow_development_policy: bool = False,
    allow_architecture_mismatch_for_packaging_test: bool = False,
) -> dict[str, Any]:
    if output_root.exists():
        raise BuildError(f"output root already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    compiler_path = _executable(compiler, "C++ compiler")
    generator_path = _executable(generator, "Lean PTX generator")
    driver_path = _executable(driver, "generated PTX CUDA driver")
    ptxas_path = _executable(ptxas, "ptxas")
    nvdisasm_path = _executable(nvdisasm, "nvdisasm")
    runner_policy = _validate_policy(
        runner_policy_path,
        nvidia_policy_path,
        classification,
        allow_development_policy,
    )
    stage = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.building-", dir=output_root.parent))
    os.chmod(stage, 0o700)
    try:
        _write(stage / "input/reference-batch.json", FORMAL_BATCH)
        _write(stage / "artifacts/rows.bin", ROWS_FILE)
        _copy(driver_path, stage / "artifacts/sparkinterval-generated-driver", 0o500)
        _copy(generator_path, stage / "provenance/sparkinterval-gen", 0o400)

        _run(
            [
                generator_path,
                "--target",
                "sm_90",
                "--input",
                stage / "input/reference-batch.json",
                "--output",
                stage / "artifacts/kernel.sm_90.ptx",
            ],
            cwd=REPOSITORY_ROOT,
            what="Lean sm_90 PTX generation",
        )
        if (stage / "artifacts/kernel.sm_90.ptx").read_bytes() != PINNED_FORMAL_PTX.read_bytes():
            raise BuildError(
                "Lean-generated sm_90 PTX differs from the source-pinned closed invocation"
            )
        _run(
            [
                sys.executable,
                REPOSITORY_ROOT / "tools/inspect_generated_ptx.py",
                stage / "artifacts/kernel.sm_90.ptx",
                stage / "provenance/ptx-audit.json",
                "--target",
                "sm_90",
            ],
            cwd=REPOSITORY_ROOT,
            what="generated PTX audit",
        )
        _run(
            [
                ptxas_path,
                "-arch=sm_90",
                stage / "artifacts/kernel.sm_90.ptx",
                "-o",
                stage / "artifacts/kernel.sm_90.cubin",
            ],
            cwd=REPOSITORY_ROOT,
            what="offline sm_90 assembly",
        )
        _run(
            [nvdisasm_path, stage / "artifacts/kernel.sm_90.cubin"],
            cwd=REPOSITORY_ROOT,
            what="sm_90 SASS extraction",
            stdout_path=stage / "provenance/kernel.sm_90.sass.txt",
        )
        _run(
            [
                sys.executable,
                REPOSITORY_ROOT / "tools/inspect_generated_sass.py",
                stage / "provenance/kernel.sm_90.sass.txt",
                stage / "provenance/ptx-audit.json",
                stage / "provenance/sass-audit.json",
                "--cubin",
                stage / "artifacts/kernel.sm_90.cubin",
            ],
            cwd=REPOSITORY_ROOT,
            what="sm_90 SASS audit",
        )

        source_paths = [
            "examples/trusted-compute/h100_formal_ptx_pilot_workload.cpp",
            "examples/trusted-compute/h100_formal_ptx_pilot_trace_verifier.cpp",
            "examples/trusted-compute/h100_gate_python_launcher.cpp",
            "examples/trusted-compute/h100_formal_ptx_constant_one.sm_90.ptx",
            "gpu/src/generated_ptx_driver.cpp",
            "gpu/src/generated_ptx_driver_report.hpp",
            "gpu/include/sparkinterval/sha256.hpp",
            "attestation/azure_h100_pre_run_gate.py",
            "attestation/collect_azure_ncc_evidence.py",
            "SparkInterval/Execution/FormalPTXProgram.lean",
            "SparkInterval/Execution/RegisteredAlgorithm.lean",
            "SparkInterval/Execution/RegisteredH100FormalPtxPilot.lean",
            "SparkInterval/Tests/FormalPTXProgramTest.lean",
            "SparkInterval/Tests/RegisteredH100FormalPtxPilotTest.lean",
            "SparkInterval/GeneratePTX.lean",
        ]
        for relative in source_paths:
            _copy(REPOSITORY_ROOT / relative, stage / "source" / relative, 0o400)
        _copy(
            REPOSITORY_ROOT / "attestation/azure_h100_pre_run_gate.py",
            stage / "attestation/azure_h100_pre_run_gate.py",
            0o400,
        )
        _copy(
            REPOSITORY_ROOT / "attestation/collect_azure_ncc_evidence.py",
            stage / "attestation/collect_azure_ncc_evidence.py",
            0o400,
        )
        _copy(nvidia_policy_path, stage / "profiles/nvidia-gpu.rego", 0o400)

        cubin_hash, cubin_size = _hash(stage / "artifacts/kernel.sm_90.cubin")
        ptx_hash, _ = _hash(stage / "artifacts/kernel.sm_90.ptx")
        try:
            formal_ptx = (stage / "artifacts/kernel.sm_90.ptx").read_text(
                encoding="ascii"
            )
        except UnicodeDecodeError as error:
            raise BuildError("Lean-generated formal PTX must be ASCII") from error
        if _digest_bytes(formal_ptx.encode("ascii")) != ptx_hash:
            raise BuildError("formal PTX text/hash changed while packaged")
        driver_hash, driver_size = _hash(stage / "artifacts/sparkinterval-generated-driver")
        rows_hash, rows_size = _hash(stage / "artifacts/rows.bin")
        expected_gpu = bytearray(48)
        expected_gpu[:8] = b"SIG64O01"
        expected_gpu[8] = 1
        expected_gpu[16] = 1
        struct.pack_into("<Q", expected_gpu, 24, 0x3FF0000000000000)
        struct.pack_into("<Q", expected_gpu, 32, 0x3FF0000000000000)
        constants = f"""// Generated by build_h100_measured_formal_ptx_pilot.py; source-reviewed values only.\n#pragma once\n#include <cstddef>\n#include <string_view>\nnamespace h100_pilot {{\ninline constexpr std::string_view kAlgorithmId = \"{ALGORITHM_ID}\";\ninline constexpr std::string_view kFormalBatchSha256 = \"{_digest_bytes(FORMAL_BATCH)}\";\ninline constexpr std::size_t kFormalBatchSize = {len(FORMAL_BATCH)};\ninline constexpr std::string_view kPtxSha256 = \"{ptx_hash}\";\ninline constexpr std::string_view kCubinSha256 = \"{cubin_hash}\";\ninline constexpr std::size_t kCubinSize = {cubin_size};\ninline constexpr std::string_view kDriverSha256 = \"{driver_hash}\";\ninline constexpr std::size_t kDriverSize = {driver_size};\ninline constexpr std::string_view kRowsFileSha256 = \"{rows_hash}\";\ninline constexpr std::size_t kRowsFileSize = {rows_size};\ninline constexpr std::string_view kRowsPayloadSha256 = \"{EMPTY_SHA256}\";\ninline constexpr std::string_view kExpectedGpuOutputSha256 = \"{_digest_bytes(bytes(expected_gpu))}\";\ninline constexpr std::string_view kExpectedResultSha256 = \"{_digest_bytes(EXPECTED_RESULT)}\";\ninline constexpr std::string_view kDriverPath = \"artifacts/sparkinterval-generated-driver\";\ninline constexpr std::string_view kCubinPath = \"artifacts/kernel.sm_90.cubin\";\ninline constexpr std::string_view kRowsPath = \"artifacts/rows.bin\";\n}}\n""".encode("ascii")
        _write(stage / "source/h100_formal_ptx_pilot_constants.hpp", constants)
        include_dirs = [stage / "source", REPOSITORY_ROOT / "gpu/include"]
        _compile_static(
            compiler_path,
            stage / "source/examples/trusted-compute/h100_formal_ptx_pilot_workload.cpp",
            stage / "artifacts/h100-formal-ptx-pilot-workload",
            include_dirs,
        )
        _compile_static(
            compiler_path,
            stage / "source/examples/trusted-compute/h100_formal_ptx_pilot_trace_verifier.cpp",
            stage / "artifacts/h100-formal-ptx-pilot-trace-verifier",
            include_dirs,
        )
        _compile_static(
            compiler_path,
            stage / "source/examples/trusted-compute/h100_gate_python_launcher.cpp",
            stage / "artifacts/h100-gate-python-launcher",
            include_dirs,
        )

        machines = {
            name: _elf_machine(stage / "artifacts" / name)
            for name in (
                "h100-formal-ptx-pilot-workload",
                "h100-formal-ptx-pilot-trace-verifier",
                "h100-gate-python-launcher",
                "sparkinterval-generated-driver",
            )
        }
        architecture_matches_azure = all(machine == 62 for machine in machines.values())
        if not architecture_matches_azure and not allow_architecture_mismatch_for_packaging_test:
            raise BuildError(
                "Azure NCC H100 host artifacts must all be x86_64 ELF; use the explicit "
                "packaging-test override only for a non-executable local dry run"
            )
        if classification == "production" and not architecture_matches_azure:
            raise BuildError("production H100 packages cannot use the architecture-test override")

        target_source = REPOSITORY_ROOT / "profiles/targets/azure_ncc40ads_h100_v5.json"
        trust_source = REPOSITORY_ROOT / "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json"
        target_path = stage / "profiles/target.json"
        trust_path = stage / "profiles/trust.json"
        runner_path = stage / "profiles/runner-policy.json"
        _write(target_path, canonical_json_bytes(json.loads(target_source.read_bytes())))
        _write(trust_path, canonical_json_bytes(json.loads(trust_source.read_bytes())))
        _write(runner_path, canonical_json_bytes(runner_policy))
        target = load_profile(target_path, "target")
        trust = load_profile(trust_path, "trust")
        target_hash = canonical_sha256(target)
        trust_hash = canonical_sha256(trust)
        runner_hash, _ = _hash(runner_path)

        build_report = {
            "accepted": False,
            "architecture_matches_azure_x86_64": architecture_matches_azure,
            "classification": classification,
            "elf_machine_values": machines,
            "formal_batch_sha256": _digest_bytes(FORMAL_BATCH),
            "formal_scope_description": FORMAL_SCOPE_DESCRIPTION,
            "kind": "sparkinterval_h100_formal_ptx_pilot_build",
            "schema_version": 1,
            "target": "sm_90",
            "toolchain": {
                "compiler": _tool_identity(compiler_path, ["--version"]),
                "lean_generator": _tool_identity(generator_path),
                "nvdisasm": _tool_identity(nvdisasm_path, ["--version"]),
                "ptxas": _tool_identity(ptxas_path, ["--version"]),
            },
            "trust_status": "packaged_pending_real_hardware_execution_and_appraisal",
        }
        _write(stage / "provenance/build-report.json", canonical_json_bytes(build_report))

        provenance_files = sorted(
            path for path in (stage / "source").rglob("*") if path.is_file()
        )
        source_manifest = {
            "files": [
                {
                    "path": path.relative_to(stage).as_posix(),
                    "sha256": _hash(path)[0],
                    "size_bytes": _hash(path)[1],
                }
                for path in provenance_files
            ],
            "kind": "sparkinterval_h100_formal_ptx_pilot_source_manifest",
            "schema_version": 1,
        }
        _write(stage / "provenance/source-manifest.json", canonical_json_bytes(source_manifest))

        artifact_specs = [
            ("artifacts/h100-formal-ptx-pilot-workload", "measured_workload", True, "host_executable"),
            ("artifacts/h100-formal-ptx-pilot-trace-verifier", "independent_trace_verifier", True, "trace_verifier"),
            ("artifacts/h100-gate-python-launcher", "h100_gate_launcher", True, "attestation_gate"),
            ("artifacts/sparkinterval-generated-driver", "strict_cuda_driver", True, "cuda_driver_host_support"),
            ("artifacts/kernel.sm_90.cubin", "offline_sm90_cubin", False, "gpu_cubin"),
            ("artifacts/kernel.sm_90.ptx", "lean_generated_ptx", False, "formal_ptx_source"),
            ("artifacts/rows.bin", "fixed_cuda_input_encoding", False, None),
            ("attestation/azure_h100_pre_run_gate.py", "h100_gate_source", False, None),
            ("attestation/collect_azure_ncc_evidence.py", "h100_gate_dependency", False, None),
            ("profiles/nvidia-gpu.rego", "nvidia_appraisal_policy", False, "gpu_attestation_policy"),
            ("provenance/source-manifest.json", "source_manifest", False, "source_tree"),
            ("provenance/build-report.json", "build_provenance", False, None),
            ("provenance/ptx-audit.json", "ptx_audit", False, None),
            ("provenance/kernel.sm_90.sass.txt", "sass_listing", False, None),
            ("provenance/sass-audit.json", "sass_audit", False, None),
            ("provenance/sparkinterval-gen", "lean_generator_binary", False, None),
        ]
        for path in provenance_files:
            artifact_specs.append(
                (path.relative_to(stage).as_posix(), "source_review_material", False, None)
            )
        files = [
            _artifact(
                stage,
                relative,
                role,
                executable=executable,
                statement_role=statement_role,
            )
            for relative, role, executable, statement_role in artifact_specs
        ]
        closure_hash = canonical_sha256(_closure_manifest(files))
        input_hash, input_size = _hash(stage / "input/reference-batch.json")
        gate_argv = [
            "artifacts/h100-gate-python-launcher",
            "--challenge-nonce",
            "@challenge@",
            "--challenge-expires-at",
            "@challenge_expires_at@",
            "--job-binding",
            "@job_binding@",
            "--package-root",
            ".",
            "--record-path",
            "@gate_record@",
            "--policy",
            "profiles/nvidia-gpu.rego",
            "--verifier",
            "remote",
        ]
        if classification == "development":
            gate_argv.append("--allow-development-policy")
        parameters = {
            "result_format": "sparkinterval_h100_formal_ptx_pilot_result_v1",
            "row_count": 1,
            "target": "sm_90",
            "variable_count": 0,
        }
        domain = {
            "expression": "constant_interval_one",
            "interval_hi_bits": "3ff0000000000000",
            "interval_lo_bits": "3ff0000000000000",
            "rows": 1,
            "status": 0,
        }
        job = {
            "algorithm": {
                "algorithm_id": ALGORITHM_ID,
                "canonical_definition": formal_ptx,
                "definition_sha256": ptx_hash,
            },
            "artifact_closure": {
                "closure_kind": "content_addressed_image_source_reviewed_v1",
                "files": files,
                "manifest_sha256": closure_hash,
            },
            "backend": "azure_ncc40ads_h100_v5",
            "command": {
                "argv": [
                    "artifacts/h100-formal-ptx-pilot-workload",
                    "--challenge",
                    "@challenge@",
                    "--job-binding",
                    "@job_binding@",
                    "--input",
                    "@input@",
                    "--result",
                    "@output@",
                    "--trace",
                    "@trace@",
                ],
                "cwd": ".",
                "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
                "timeout_seconds": 300,
            },
            "domain_coverage": {"canonical_sha256": canonical_sha256(domain), "value": domain},
            "gpu_pre_run_gate": {
                "argv": gate_argv,
                "record_path": "runner/h100-pre-run-gate.json",
                "required": True,
                "secret_environment_names": ["NV_ATTESTATION_SERVICE_KEY"],
                "timeout_seconds": 600,
            },
            "input_artifact": {
                "path": "input/reference-batch.json",
                "release_argv": None,
                "release_mode": "prepositioned_public_after_start",
                "sha256": input_hash,
                "size_bytes": input_size,
            },
            "job_id": "h100-formal-ptx-constant-one-v1",
            "kind": "sparkinterval_measured_job",
            "output_contract": {
                "expected_output_count": 1,
                "format": "opaque_bytes_v1",
                "maximum_bytes": 512,
                "path": "output/result.json",
            },
            "parameters": {
                "canonical_sha256": canonical_sha256(parameters),
                "value": parameters,
            },
            "runner_policy": {
                "path": "profiles/runner-policy.json",
                "policy_id": runner_policy["policy_id"],
                "sha256": runner_hash,
            },
            "schema_version": 1,
            "target_profile": {
                "path": "profiles/target.json",
                "profile_id": target["profile_id"],
                "sha256": target_hash,
            },
            "tpm_policy": {
                "ak_handle": "0x81000003",
                "bank": "sha256",
                "pcr_index": 23,
                "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
            },
            "trust_profile": {
                "path": "profiles/trust.json",
                "profile_id": trust["profile_id"],
                "sha256": trust_hash,
            },
            "work_trace_contract": {
                "expected_iterations": 1,
                "format": "challenge_sha256_chain_json_v1",
                "path": "output/work-trace.json",
                "required": True,
                "trace_algorithm_definition": TRACE_DEFINITION,
                "trace_algorithm_sha256": _digest_bytes(TRACE_DEFINITION.encode("utf-8")),
                "verification_mode": "pinned_external_trace_verifier_v1",
                "verifier_argv": [
                    "artifacts/h100-formal-ptx-pilot-trace-verifier",
                    "--challenge",
                    "@challenge@",
                    "--job-binding",
                    "@job_binding@",
                    "--input",
                    "@input@",
                    "--result",
                    "@output@",
                    "--trace",
                    "@trace@",
                ],
            },
        }
        validate_job_spec(job)
        job_bytes = canonical_json_bytes(job)
        _write(stage / "job.json", job_bytes, 0o400)
        job_hash = _digest_bytes(job_bytes)
        appraisal_policy = {
            "allowed_backends": ["azure_ncc40ads_h100_v5"],
            "allowed_job_spec_sha256": [job_hash],
            "allowed_runner_policy_sha256": [runner_hash],
            "allowed_target_profile_sha256": [target_hash],
            "allowed_trust_profile_sha256": [trust_hash],
            "classification": classification,
            "kind": "sparkinterval_measured_runner_appraisal_policy",
            "policy_id": f"sparkinterval.h100-formal-ptx-pilot.{classification}.v1",
            "require_authenticated_hardware_quote": True,
            "required_composite_appraiser_claims": [
                "measured_runner_policy_valid",
                "result_artifact_bound_to_execution",
            ],
            "schema_version": 1,
        }
        _write(stage / "appraisal-policy.json", canonical_json_bytes(appraisal_policy), 0o400)
        os.replace(stage, output_root)
        return {
            "accepted": False,
            "architecture_matches_azure_x86_64": architecture_matches_azure,
            "artifact_root": str(output_root),
            "classification": "h100_formal_ptx_pilot_packaged_pending_real_attestation",
            "job_spec": str(output_root / "job.json"),
            "job_spec_sha256": job_hash,
            "lean_registry_admission": False,
            "lean_registry_invocation": "h100FormalPtxConstantOneV1",
            "lean_registry_invocation_supported": True,
            "lean_registry_status": "eligible only after a genuine production receipt is source-admitted",
            "target": "azure_ncc40ads_h100_v5",
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--generator", default=REPOSITORY_ROOT / ".lake/build/bin/sparkinterval-gen")
    parser.add_argument("--driver", default=REPOSITORY_ROOT / "build/dgx-spark/sparkinterval-generated-driver")
    parser.add_argument("--ptxas", default="ptxas")
    parser.add_argument("--nvdisasm", default="nvdisasm")
    parser.add_argument("--runner-policy", type=Path, required=True)
    parser.add_argument("--nvidia-policy", type=Path, required=True)
    parser.add_argument("--classification", choices=("development", "production"), required=True)
    parser.add_argument("--allow-development-policy", action="store_true")
    parser.add_argument(
        "--allow-architecture-mismatch-for-packaging-test",
        action="store_true",
        help="permit a non-x86_64 non-executable package only for local validation",
    )
    args = parser.parse_args(argv)
    try:
        report = build(
            args.output_root,
            compiler=args.compiler,
            generator=args.generator,
            driver=args.driver,
            ptxas=args.ptxas,
            nvdisasm=args.nvdisasm,
            runner_policy_path=args.runner_policy,
            nvidia_policy_path=args.nvidia_policy,
            classification=args.classification,
            allow_development_policy=args.allow_development_policy,
            allow_architecture_mismatch_for_packaging_test=(
                args.allow_architecture_mismatch_for_packaging_test
            ),
        )
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (BuildError, OSError, RuntimeError, ValueError, KeyError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "h100_formal_ptx_pilot_build_failed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
