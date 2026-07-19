#!/usr/bin/env python3
"""Package a successful GB10 rounding probe as local, unattested evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
from typing import Any

import create_run_bundle as bundle_format
import verify_run_bundle as bundle_verify


EXPECTED_FIELDS = {
    "add_down": "0x3ff0000000000000",
    "add_up": "0x3ff0000000000001",
    "sub_down": "0x3fefffffffffffff",
    "sub_up": "0x3ff0000000000000",
    "mul_down": "0x3ff0000000000002",
    "mul_up": "0x3ff0000000000003",
    "div_down": "0x3fd5555555555555",
    "div_up": "0x3fd5555555555556",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_canonical(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bundle_format.canonical_json_bytes(value))


def checked_probe(path: Path) -> dict[str, Any]:
    probe = bundle_format.load_json(path)
    if not isinstance(probe, dict):
        raise bundle_format.BundleError("probe output is not a JSON object")
    if probe.get("evidence_class") != "local_unattested":
        raise bundle_format.BundleError("probe is not marked local_unattested")
    if probe.get("hardware_attestation") is not None:
        raise bundle_format.BundleError("DGX probe unexpectedly contains attestation")
    if probe.get("device_name") != "NVIDIA GB10":
        raise bundle_format.BundleError("probe did not run on the expected NVIDIA GB10")
    if probe.get("compute_capability") != "12.1":
        raise bundle_format.BundleError("probe did not run at compute capability 12.1")
    if probe.get("passed") is not True:
        raise bundle_format.BundleError("directed-rounding probe did not pass")
    if probe.get("directed_rounding_bits") != EXPECTED_FIELDS:
        raise bundle_format.BundleError("probe output bits do not match the fixed contract")
    return probe


def copy_artifact(source: Path, destination: Path) -> Path:
    source = source.resolve(strict=True)
    if not source.is_file():
        raise bundle_format.BundleError(f"artifact is not a file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--probe-output", required=True, type=Path)
    result.add_argument("--host-executable", required=True, type=Path)
    result.add_argument("--cubin", required=True, type=Path)
    result.add_argument("--ptx", required=True, type=Path)
    result.add_argument("--ptx-audit", required=True, type=Path)
    result.add_argument("--sass", required=True, type=Path)
    result.add_argument("--sass-audit", required=True, type=Path)
    result.add_argument("--kernel-source", required=True, type=Path)
    result.add_argument("--environment-record", required=True, type=Path)
    result.add_argument("--output-root", required=True, type=Path)
    result.add_argument("--start-time-utc", required=True)
    result.add_argument("--end-time-utc", required=True)
    result.add_argument(
        "--nonce",
        help="64 lowercase hex characters; defaults to a local random nonce (not verifier freshness)",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        probe = checked_probe(args.probe_output)
        ptx_audit_value = bundle_format.load_json(args.ptx_audit)
        if (
            not isinstance(ptx_audit_value, dict)
            or ptx_audit_value.get("passed") is not True
            or ptx_audit_value.get("targets") != ["sm_121"]
        ):
            raise bundle_format.BundleError("PTX probe allowlist audit did not pass for sm_121")
        sass_audit = bundle_format.load_json(args.sass_audit)
        if not isinstance(sass_audit, dict) or sass_audit.get("passed") is not True:
            raise bundle_format.BundleError("SASS audit did not pass")
        if sass_audit.get("targets") != ["sm_121"]:
            raise bundle_format.BundleError("SASS audit does not identify sm_121")

        output_root = args.output_root.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        artifacts_dir = output_root / "artifacts"
        records_dir = output_root / "records"
        host = copy_artifact(args.host_executable, artifacts_dir / "sparkinterval-probe")
        cubin = copy_artifact(args.cubin, artifacts_dir / "probe.sm_121.cubin")
        ptx = copy_artifact(args.ptx, artifacts_dir / "probe.sm_121.ptx")
        ptx_audit = copy_artifact(args.ptx_audit, artifacts_dir / "probe.ptx.json")
        sass_dump = copy_artifact(args.sass, artifacts_dir / "probe.sm_121.sass.txt")
        sass = copy_artifact(args.sass_audit, artifacts_dir / "probe.sass.json")
        source = copy_artifact(args.kernel_source, artifacts_dir / "probe_kernel.cu")
        environment_text = copy_artifact(
            args.environment_record, records_dir / "environment.txt"
        )
        probe_output = copy_artifact(args.probe_output, records_dir / "probe-output.json")

        fixed_input = {
            "contract": "sparkinterval_directed_rounding_probe_v1",
            "runtime_inputs": "none_constants_are_bound_by_algorithm_source",
            "operations": {
                "add": {"a_bits": "0x3ff0000000000000", "b_bits": "0x3ca0000000000000"},
                "sub": {"a_bits": "0x3ff0000000000000", "b_bits": "0x3c90000000000000"},
                "mul": {"a_bits": "0x3ff0000000000001", "b_bits": "0x3ff0000000000001"},
                "div": {"a_bits": "0x3ff0000000000000", "b_bits": "0x4008000000000000"},
            },
        }
        input_path = records_dir / "probe-input.json"
        write_canonical(input_path, fixed_input)

        nonce = args.nonce or secrets.token_hex(32)
        target = bundle_format.load_profile(
            Path(__file__).resolve().parents[1]
            / "profiles/targets/dgx_spark_sm121.json",
            "target",
        )
        trust = bundle_format.load_profile(
            Path(__file__).resolve().parents[1]
            / "profiles/trust/local_unattested.json",
            "trust",
        )
        completion = {
            "status": "success",
            "exit_code": 0,
            "expected_output_count": 8,
            "written_output_count": 8,
            "cuda_errors": [],
            "start_time_utc": args.start_time_utc,
            "end_time_utc": args.end_time_utc,
        }
        parameters = {
            "cuda_fmad": False,
            "cuda_ftz": False,
            "cuda_precise_division": True,
            "cuda_precise_sqrt": True,
            "grid_x": 1,
            "block_x": 1,
            "ptx_target": "sm_121",
            "result_encoding": "binary64_raw_bits_hex",
        }
        coverage = {
            "case_count": 8,
            "operations": ["add", "sub", "mul", "div"],
            "rounding_directions": ["down", "up"],
            "scope": "fixed_environment_diagnostic_cases_only",
        }
        execution_environment = {
            "device_name": probe["device_name"],
            "compute_capability": probe["compute_capability"],
            "cuda_driver_api_version": probe["cuda_driver_api_version"],
            "cuda_runtime_version": probe["cuda_runtime_version"],
            "environment_record_sha256": sha256_file(environment_text),
            "hardware_attestation": None,
        }
        bundle = bundle_format.create_bundle(
            root=output_root,
            target_profile=target,
            trust_profile=trust,
            algorithm_id="SparkInterval.DirectedRoundingProbe.v1",
            algorithm_definition_sha256=sha256_file(source),
            input_path=input_path,
            parameters=parameters,
            domain_coverage=coverage,
            output_path=probe_output,
            nonce=nonce,
            build_artifacts=[
                ("gpu_cubin", cubin),
                ("gpu_ptx", ptx),
                ("ptx_audit", ptx_audit),
                ("host_executable", host),
                ("environment_record", environment_text),
                ("gpu_sass_dump", sass_dump),
                ("kernel_source", source),
                ("sass_audit", sass),
            ],
            execution_environment=execution_environment,
            completion=completion,
        )
        bundle_path = output_root / "run-bundle.json"
        bundle_format.write_bundle(bundle, bundle_path)
        verification = bundle_verify.verify_bundle_file(
            bundle_path, artifact_root=output_root
        )
        write_canonical(output_root / "verification.json", verification)
    except (OSError, bundle_format.BundleError, bundle_verify.VerificationError) as exc:
        print(f"create_dgx_probe_bundle: {exc}", file=sys.stderr)
        return 2

    print(bundle_format.canonical_json_bytes(verification).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
