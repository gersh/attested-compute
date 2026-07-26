#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build the closed cubic-sum example and its canonical measured-job spec.

The emitted runner policy is development-only.  This tool makes a runnable,
auditable protocol fixture; it does not make an Azure attestation acceptable.
Build on the exact Azure guest image when preparing an Azure CPU run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "tools"))
sys.path.insert(0, str(REPOSITORY_ROOT / "azure"))

from create_run_bundle import canonical_json_bytes, canonical_sha256, load_profile  # noqa: E402
from measured_runner import (  # noqa: E402
    CUBIC_TRACE_DEFINITION,
    _closure_manifest,
    validate_job_spec,
)


ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=cubic-sum-div-three\n"
    "input=canonical-decimal-natural-upper-inclusive\n"
    "output=canonical-decimal-natural\n"
    "arithmetic=natural-accumulator-with-u64-proof-on-registered-domain\n"
    "division=natural-division-by-3-after-total\n"
    "semantics=loop-x-from-0-through-upper-add-x-cubed-then-divide-total"
)
PARAMETERS = {
    "accumulator": "u64-no-wrap",
    "divide_after_sum": True,
    "divisor": 3,
    "inclusive": True,
}
DOMAIN = {"input": "nat", "output": "nat", "range_start": 0}


class BuildError(RuntimeError):
    pass


def _hash(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest(), len(content)


def _copy(source: Path, destination: Path, mode: int) -> None:
    if source.is_symlink() or not source.is_file():
        raise BuildError(f"source is not a regular non-symlink file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, mode)
    try:
        content = source.read_bytes()
        view = memoryview(content)
        while view:
            count = os.write(descriptor, view)
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        view = memoryview(content)
        while view:
            count = os.write(descriptor, view)
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build(output_root: Path, compiler: str) -> dict[str, object]:
    if output_root.exists():
        raise BuildError(f"output root already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.building-", dir=output_root.parent))
    os.chmod(stage, 0o700)
    try:
        source_repository = (
            REPOSITORY_ROOT / "examples/trusted-compute/cubic_sum_div_three_20000.cpp"
        )
        source = stage / "source/cubic_sum_div_three_20000.cpp"
        executable = stage / "artifacts/cubic_sum_div_three_20000"
        _copy(source_repository, source, 0o400)
        executable.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        compiler_path = shutil.which(compiler)
        if compiler_path is None:
            raise BuildError(f"C++ compiler is absent: {compiler}")
        command = [
            compiler_path,
            "-std=c++20",
            "-O3",
            "-DNDEBUG",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-fno-ident",
            "-fno-record-gcc-switches",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            str(source),
            "-o",
            str(executable),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={"LANG": "C", "LC_ALL": "C", "PATH": os.environ.get("PATH", "")},
        )
        if completed.returncode != 0:
            raise BuildError(f"static C++ build failed: {completed.stderr[-4000:]}")
        os.chmod(executable, 0o500)
        _write(stage / "input/upper.txt", b"20000", 0o400)

        target_source = REPOSITORY_ROOT / "profiles/targets/azure_sevsnp_cpu.json"
        trust_source = REPOSITORY_ROOT / "profiles/trust/azure_sevsnp_hardware_attested.json"
        policy_source = (
            REPOSITORY_ROOT / "profiles/measured_runner/development_challenge_first_v1.json"
        )
        target_path = stage / "profiles/target.json"
        trust_path = stage / "profiles/trust.json"
        policy_path = stage / "profiles/runner-policy.json"
        _write(target_path, canonical_json_bytes(json.loads(target_source.read_bytes())), 0o400)
        _write(trust_path, canonical_json_bytes(json.loads(trust_source.read_bytes())), 0o400)
        _write(policy_path, canonical_json_bytes(json.loads(policy_source.read_bytes())), 0o400)
        target = load_profile(target_path, "target")
        trust = load_profile(trust_path, "trust")

        source_hash, source_size = _hash(source)
        executable_hash, executable_size = _hash(executable)
        files = [
            {
                "executable": True,
                "path": "artifacts/cubic_sum_div_three_20000",
                "role": "closed_cubic_workload",
                "sha256": executable_hash,
                "size_bytes": executable_size,
                "statement_role": "host_executable",
            },
            {
                "executable": False,
                "path": "source/cubic_sum_div_three_20000.cpp",
                "role": "source_definition",
                "sha256": source_hash,
                "size_bytes": source_size,
                "statement_role": "source_tree",
            },
        ]
        manifest_hash = canonical_sha256(_closure_manifest(files))
        input_hash, input_size = _hash(stage / "input/upper.txt")
        policy_hash, _ = _hash(policy_path)
        target_hash = canonical_sha256(target)
        trust_hash = canonical_sha256(trust)
        if _hash(target_path)[0] != target_hash or _hash(trust_path)[0] != trust_hash:
            raise BuildError("profiles must use canonical JSON bytes without a trailing newline")
        job = {
            "algorithm": {
                "algorithm_id": "sparkinterval.example.cubic-sum-div-three.v1",
                "canonical_definition": ALGORITHM_DEFINITION,
                "definition_sha256": hashlib.sha256(
                    ALGORITHM_DEFINITION.encode("utf-8")
                ).hexdigest(),
            },
            "artifact_closure": {
                "closure_kind": "static_elf_source_reviewed_v1",
                "files": files,
                "manifest_sha256": manifest_hash,
            },
            "backend": "azure_sevsnp_cpu",
            "command": {
                "argv": [
                    "artifacts/cubic_sum_div_three_20000",
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
                "timeout_seconds": 60,
            },
            "domain_coverage": {"canonical_sha256": canonical_sha256(DOMAIN), "value": DOMAIN},
            "gpu_pre_run_gate": None,
            "input_artifact": {
                "path": "input/upper.txt",
                "release_argv": None,
                "release_mode": "prepositioned_public_after_start",
                "sha256": input_hash,
                "size_bytes": input_size,
            },
            "job_id": "cubic-sum-div-three-20000-cpu-v1",
            "kind": "sparkinterval_measured_job",
            "output_contract": {
                "expected_output_count": 1,
                "format": "canonical_decimal_natural_no_newline_v1",
                "maximum_bytes": 32,
                "path": "output/result.txt",
            },
            "parameters": {
                "canonical_sha256": canonical_sha256(PARAMETERS),
                "value": PARAMETERS,
            },
            "runner_policy": {
                "path": "profiles/runner-policy.json",
                "policy_id": "sparkinterval.measured-runner.development.challenge-first.v1",
                "sha256": policy_hash,
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
                "expected_iterations": 20001,
                "format": "challenge_sha256_chain_json_v1",
                "path": "output/work-trace.json",
                "required": True,
                "trace_algorithm_definition": CUBIC_TRACE_DEFINITION,
                "trace_algorithm_sha256": hashlib.sha256(
                    CUBIC_TRACE_DEFINITION.encode("utf-8")
                ).hexdigest(),
                "verification_mode": "builtin_cubic_sum_div_three_20000_v1",
                "verifier_argv": None,
            },
        }
        validate_job_spec(job)
        job_bytes = canonical_json_bytes(job)
        _write(stage / "job.json", job_bytes)
        job_hash = hashlib.sha256(job_bytes).hexdigest()
        appraisal_policy = {
            "allowed_backends": ["azure_sevsnp_cpu"],
            "allowed_job_spec_sha256": [job_hash],
            "allowed_runner_policy_sha256": [policy_hash],
            "allowed_target_profile_sha256": [target_hash],
            "allowed_trust_profile_sha256": [trust_hash],
            "classification": "development",
            "kind": "sparkinterval_measured_runner_appraisal_policy",
            "policy_id": "sparkinterval.cubic-20000.development-appraisal.v1",
            "require_authenticated_hardware_quote": True,
            "required_composite_appraiser_claims": [
                "measured_runner_policy_valid",
                "result_artifact_bound_to_execution",
            ],
            "schema_version": 1,
        }
        _write(stage / "appraisal-policy.json", canonical_json_bytes(appraisal_policy))
        os.replace(stage, output_root)
        return {
            "accepted": False,
            "artifact_root": str(output_root),
            "classification": "development_measured_job_built",
            "executable_sha256": executable_hash,
            "job_spec": str(output_root / "job.json"),
            "job_spec_sha256": job_hash,
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args(argv)
    try:
        result = build(args.output_root, args.compiler)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (BuildError, OSError, ValueError) as error:
        print(
            json.dumps(
                {"accepted": False, "classification": "measured_job_build_failed", "error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
