# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize an Azure H100 measured job for candidate calibration only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any

from azure.measured_runner import (
    RunnerError,
    canonical_sha256 as runner_canonical_sha256,
    validate_job_spec,
)

from .campaign_io import canonical_json_bytes
from .goldbach_optimized_calibration_contract import (
    CLASSIFICATION,
    DEFAULT_SAMPLE_EVEN_COUNT,
    DEFAULT_SAMPLE_EVEN_LIMIT,
    DEFAULT_SAMPLE_EVEN_START,
    INPUT_KIND,
    TRACE_DEFINITION,
    algorithm_identity,
    parameters_value,
    validate_input,
)
from .goldbach_optimized_candidate import (
    GoldbachOptimizedCandidateError,
    validate_candidate_package,
)


MATERIALIZATION_KIND = (
    "sparkinterval.azure.h100.goldbach-optimized-calibration-package.v1"
)
CALIBRATION_CAPABILITY = (
    "bounded-candidate-target-sku-calibration-ready-not-production-ready"
)
NCC_TARGET_PROFILE_ID = "azure_ncc40ads_h100_v5"
NCC_TARGET_PROFILE_SHA256 = (
    "e8ce26a02aa7b4a9577f9a725f00ebb464c8b70a40dfcb5fc4b107a7f66ec148"
)
NCC_TRUST_PROFILE_ID = (
    "azure_ncc_sevsnp_vtpm_nvidia_cc_attested"
)
NCC_TRUST_PROFILE_SHA256 = (
    "470cb77b28f0c5c7e777ffbc5137ebfb670015f03cfea12ccd7ebdd544bb2c6b"
)
_ROOT = Path(__file__).resolve().parents[1]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_PATHS = (
    "tools/tg_goldbach_optimized_h100_measured_workload.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/goldbach_optimized_calibration_contract.py",
    "attestation/azure_h100_pre_run_gate.py",
    "attestation/collect_azure_ncc_evidence.py",
)


class GoldbachCalibrationMaterializationError(RuntimeError):
    """The candidate or Azure calibration package failed closed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pin(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise GoldbachCalibrationMaterializationError(
            f"calibration package input is not a nonsymlink file: {path}"
        )
    return {"sha256": _sha256(path), "size_bytes": metadata.st_size}


def _copy_file(source: Path, destination: Path, *, executable: bool = False) -> None:
    if source.is_symlink() or not source.is_file():
        raise GoldbachCalibrationMaterializationError(
            f"calibration package source is absent or linked: {source}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o500 if executable else 0o400)


def _profile(
    path: Path, *, kind: str, expected_id: str | None = None
) -> tuple[dict[str, Any], dict[str, object]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldbachCalibrationMaterializationError(
            f"cannot load {kind} profile"
        ) from error
    if canonical_json_bytes(value) != raw or not isinstance(value, dict):
        raise GoldbachCalibrationMaterializationError(
            f"{kind} profile is not canonical JSON"
        )
    id_field = "policy_id" if kind == "runner" else "profile_id"
    identity = value.get(id_field)
    if (
        not isinstance(identity, str)
        or not identity
        or (expected_id is not None and identity != expected_id)
    ):
        raise GoldbachCalibrationMaterializationError(
            f"{kind} profile identity differs"
        )
    return value, {"id": identity, "sha256": hashlib.sha256(raw).hexdigest()}


def _candidate_input(
    manifest: dict[str, Any],
    *,
    even_start: int,
    even_limit: int,
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    count = (even_limit - even_start) // 2 + 1
    artifacts = manifest["artifacts"]
    value = {
        "candidate": {
            "candidate_closure_sha256": manifest["closure_sha256"],
            "candidate_manifest_sha256": manifest["manifest_sha256"],
            "cubin_sha256": artifacts["cubin"]["sha256"],
            "executable_sha256": artifacts["executable"]["sha256"],
            "executable_size_bytes": artifacts["executable"]["size_bytes"],
            "ptx_sha256": artifacts["ptx"]["sha256"],
            "sass_sha256": artifacts["sass"]["sha256"],
            "source_identity_sha256": manifest["optimized_source"][
                "source_identity_sha256"
            ],
        },
        "classification": CLASSIFICATION,
        "domain": {
            "even_count": count,
            "even_limit_inclusive": even_limit,
            "even_start_inclusive": even_start,
        },
        "kind": INPUT_KIND,
        "repetitions": repetitions,
        "schema_version": 1,
        "warmups": warmups,
    }
    return validate_input(value)


def _artifact_records(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    excluded = {"input/calibration.json", "job.json"}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise GoldbachCalibrationMaterializationError(
                "calibration package contains a symbolic link"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise GoldbachCalibrationMaterializationError(
                "calibration package contains a special file"
            )
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        is_python = relative == "artifacts/python3"
        executable = is_python or relative == "candidate/artifacts/goldbach-gpu"
        if relative.startswith("candidate/"):
            role = "candidate_artifact"
        elif relative.startswith("profiles/"):
            role = "calibration_policy"
        elif relative.startswith("attestation/"):
            role = "h100_pre_run_gate"
        elif relative.startswith(("tools/", "tg_verifier/")):
            role = "calibration_replay_source"
        else:
            role = "calibration_runtime"
        records.append(
            {
                "executable": executable,
                "path": relative,
                "role": role,
                "sha256": _sha256(path),
                "size_bytes": metadata.st_size,
                "statement_role": "host_executable" if is_python else None,
            }
        )
    return records


def _workload_argv(
    mode: str, algorithm_id: str, timeout: int
) -> list[str]:
    return [
        "artifacts/python3",
        "-I",
        "tools/tg_goldbach_optimized_h100_measured_workload.py",
        mode,
        "--algorithm-id",
        algorithm_id,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--candidate-root",
        "candidate",
        "--executable",
        "candidate/artifacts/goldbach-gpu",
        "--timeout",
        str(timeout),
    ]


def _job(
    *,
    root: Path,
    input_value: dict[str, Any],
    runner: dict[str, object],
    target: dict[str, object],
    trust: dict[str, object],
    gpu_verifier: str,
    nras_url: str,
    per_run_timeout: int,
) -> dict[str, Any]:
    identity = algorithm_identity(input_value)
    records = _artifact_records(root)
    closure_manifest = {
        "artifacts": records,
        "kind": "sparkinterval_executable_artifact_closure",
        "schema_version": 1,
    }
    input_raw = canonical_json_bytes(input_value)
    domain = input_value["domain"]
    parameters = parameters_value(input_value)
    total_timeout = min(
        7 * 86_400,
        max(
            600,
            (input_value["warmups"] + input_value["repetitions"])
            * per_run_timeout
            + 600,
        ),
    )
    return {
        "algorithm": identity,
        "artifact_closure": {
            "closure_kind": "content_addressed_image_source_reviewed_v1",
            "files": records,
            "manifest_sha256": runner_canonical_sha256(closure_manifest),
        },
        "backend": "azure_ncc40ads_h100_v5",
        "command": {
            "argv": _workload_argv(
                "run", identity["algorithm_id"], per_run_timeout
            ),
            "cwd": ".",
            "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "timeout_seconds": total_timeout,
        },
        "domain_coverage": {
            "canonical_sha256": runner_canonical_sha256(domain),
            "value": domain,
        },
        "gpu_pre_run_gate": {
            "argv": [
                "artifacts/python3",
                "-I",
                "-B",
                "attestation/azure_h100_pre_run_gate.py",
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
                gpu_verifier,
                "--nras-url",
                nras_url,
            ],
            "record_path": "runner/h100-pre-run-gate.json",
            "required": True,
            "secret_environment_names": ["NV_ATTESTATION_SERVICE_KEY"],
            "timeout_seconds": 600,
        },
        "input_artifact": {
            "path": "input/calibration.json",
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": hashlib.sha256(input_raw).hexdigest(),
            "size_bytes": len(input_raw),
        },
        "job_id": (
            "tg-goldbach-optimized-h100-calibration-"
            + input_value["candidate"]["candidate_manifest_sha256"][:16]
        ),
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": "opaque_bytes_v1",
            "maximum_bytes": 1024 * 1024,
            "path": "output/calibration-result.json",
        },
        "parameters": {
            "canonical_sha256": runner_canonical_sha256(parameters),
            "value": parameters,
        },
        "runner_policy": {
            "path": "profiles/runner-policy.json",
            "policy_id": runner["id"],
            "sha256": runner["sha256"],
        },
        "schema_version": 1,
        "target_profile": {
            "path": "profiles/target.json",
            "profile_id": target["id"],
            "sha256": target["sha256"],
        },
        "tpm_policy": {
            "ak_handle": "0x81000003",
            "bank": "sha256",
            "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": {
            "path": "profiles/trust.json",
            "profile_id": trust["id"],
            "sha256": trust["sha256"],
        },
        "work_trace_contract": {
            "expected_iterations": 1,
            "format": "challenge_sha256_chain_json_v1",
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": TRACE_DEFINITION,
            "trace_algorithm_sha256": hashlib.sha256(
                TRACE_DEFINITION.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": _workload_argv(
                "verify-trace", identity["algorithm_id"], per_run_timeout
            ),
        },
    }


def materialize_calibration_job(
    candidate_root: Path,
    destination: Path,
    *,
    python_executable: Path,
    runner_policy: Path,
    nvidia_policy: Path,
    target_profile: Path = (
        _ROOT / "profiles/targets/azure_ncc40ads_h100_v5.json"
    ),
    trust_profile: Path = (
        _ROOT
        / "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json"
    ),
    gpu_verifier: str = "remote",
    nras_url: str = "https://nras.attestation.nvidia.com",
    even_start: int = DEFAULT_SAMPLE_EVEN_START,
    even_limit: int = DEFAULT_SAMPLE_EVEN_LIMIT,
    warmups: int = 1,
    repetitions: int = 5,
    per_run_timeout: int = 3600,
    require_x86_64_candidate: bool = True,
) -> dict[str, object]:
    """Create one generic-measured-runner package for bounded H100 timing."""

    if destination.exists() or destination.is_symlink():
        raise GoldbachCalibrationMaterializationError(
            "calibration destination must be absent"
        )
    if gpu_verifier not in {"local", "remote"} or not nras_url.startswith(
        "https://"
    ):
        raise GoldbachCalibrationMaterializationError(
            "calibration NVIDIA verifier configuration differs"
        )
    if not 60 <= per_run_timeout <= 86_400:
        raise GoldbachCalibrationMaterializationError(
            "calibration per-run timeout is outside [60,86400]"
        )
    try:
        manifest = validate_candidate_package(candidate_root)
    except GoldbachOptimizedCandidateError as error:
        raise GoldbachCalibrationMaterializationError(str(error)) from error
    if (
        require_x86_64_candidate
        and manifest["build"].get("host_architecture") != "x86_64"
    ):
        raise GoldbachCalibrationMaterializationError(
            "Azure NCC calibration requires an x86_64 candidate build"
        )
    if (
        manifest.get("bounded_full_differential_completed") is not True
        or manifest.get("bounded_component_kats_completed") is not True
        or any(
            value is not False
            for value in manifest["trust_status"].values()
        )
    ):
        raise GoldbachCalibrationMaterializationError(
            "candidate qualification/trust status differs"
        )
    input_value = _candidate_input(
        manifest,
        even_start=even_start,
        even_limit=even_limit,
        warmups=warmups,
        repetitions=repetitions,
    )
    target_value, target_pin = _profile(
        target_profile, kind="target", expected_id=NCC_TARGET_PROFILE_ID
    )
    del target_value
    if target_pin["sha256"] != NCC_TARGET_PROFILE_SHA256:
        raise GoldbachCalibrationMaterializationError(
            "Azure NCC target profile bytes differ"
        )
    trust_value, trust_pin = _profile(
        trust_profile, kind="trust", expected_id=NCC_TRUST_PROFILE_ID
    )
    del trust_value
    if trust_pin["sha256"] != NCC_TRUST_PROFILE_SHA256:
        raise GoldbachCalibrationMaterializationError(
            "Azure NCC trust profile bytes differ"
        )
    runner_value, runner_pin = _profile(
        runner_policy, kind="runner"
    )
    del runner_value
    _pin(nvidia_policy)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
    )
    succeeded = False
    try:
        shutil.copytree(candidate_root, stage / "candidate")
        _copy_file(
            python_executable.resolve(strict=True),
            stage / "artifacts/python3",
            executable=True,
        )
        for relative in _SOURCE_PATHS:
            _copy_file(_ROOT / relative, stage / relative)
        _copy_file(target_profile, stage / "profiles/target.json")
        _copy_file(trust_profile, stage / "profiles/trust.json")
        _copy_file(runner_policy, stage / "profiles/runner-policy.json")
        _copy_file(nvidia_policy, stage / "profiles/nvidia-gpu.rego")
        input_path = stage / "input/calibration.json"
        input_path.parent.mkdir()
        input_path.write_bytes(canonical_json_bytes(input_value))
        os.chmod(input_path, 0o400)
        job = _job(
            root=stage,
            input_value=input_value,
            runner=runner_pin,
            target=target_pin,
            trust=trust_pin,
            gpu_verifier=gpu_verifier,
            nras_url=nras_url,
            per_run_timeout=per_run_timeout,
        )
        validate_job_spec(job)
        job_path = stage / "job.json"
        job_path.write_bytes(canonical_json_bytes(job))
        os.chmod(job_path, 0o400)
        stage.rename(destination)
        succeeded = True
        return {
            "accepted": True,
            "capability": CALIBRATION_CAPABILITY,
            "candidate_manifest_sha256": manifest["manifest_sha256"],
            "classification": (
                "materialized-measured-job-not-execution-or-calibration-evidence"
            ),
            "destination": str(destination.resolve()),
            "job_sha256": _sha256(destination / "job.json"),
            "kind": MATERIALIZATION_KIND,
            "trust_status": {
                "confidential_attestation_completed": False,
                "lean_atom_discharged": False,
                "production_identity_promoted": False,
                "source_scale_completion": False,
                "target_h100_measured": False,
            },
        }
    except (OSError, RunnerError, ValueError) as error:
        if isinstance(error, GoldbachCalibrationMaterializationError):
            raise
        raise GoldbachCalibrationMaterializationError(str(error)) from error
    finally:
        if not succeeded:
            shutil.rmtree(stage, ignore_errors=True)


__all__ = [
    "CALIBRATION_CAPABILITY",
    "GoldbachCalibrationMaterializationError",
    "MATERIALIZATION_KIND",
    "materialize_calibration_job",
]
