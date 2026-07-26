#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Produce retained NVIDIA evidence for the measured runner's H100 gate.

The gate runs after the PCR23 start extension and before relying-party input
release.  It verifies one H100 is in production CC/Ready state and obtains a
nonce-bound NVAT/NRAS appraisal.  Its ``release_allowed`` status is only a
local gate decision; it is not a trusted-compute receipt and it never emits an
``accepted: true`` field.  The final composite appraiser must reverify the
retained evidence and bind it to the same CVM and final vTPM quote.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ATTESTATION_DIR = Path(__file__).resolve().parent
if str(ATTESTATION_DIR) not in sys.path:
    sys.path.insert(0, str(ATTESTATION_DIR))

from collect_azure_ncc_evidence import (  # noqa: E402
    DEFAULT_POLICY,
    EvidenceError,
    HEX256_RE,
    _artifact_inventory,
    _collect_gpu,
    _require_gpu_state,
    _which,
    canonical_json_bytes,
)


GATE_BINDING_HEADER = "sparkinterval.h100.pre-run-gate.v1\n"


class GateError(RuntimeError):
    pass


def derive_gate_nonce(challenge_nonce: str, job_binding: str) -> str:
    for value, what in ((challenge_nonce, "challenge"), (job_binding, "job binding")):
        if not isinstance(value, str) or HEX256_RE.fullmatch(value) is None:
            raise GateError(f"{what} must be lowercase SHA-256 hex")
    return hashlib.sha256(
        (
            GATE_BINDING_HEADER
            + f"challenge_nonce={challenge_nonce}\n"
            + f"job_binding_sha256={job_binding}\n"
        ).encode("ascii")
    ).hexdigest()


def _relative(value: Path, what: str) -> str:
    text = value.as_posix()
    parsed = PurePosixPath(text)
    if parsed.is_absolute() or text != parsed.as_posix() or any(
        part in ("", ".", "..") for part in parsed.parts
    ):
        raise GateError(f"{what} must be a safe relative POSIX path")
    return text


def _sanitize_environment(remote: bool) -> None:
    service_key = os.environ.get("NV_ATTESTATION_SERVICE_KEY") if remote else None
    os.environ.clear()
    os.environ.update(
        {
            "HOME": "/root",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TZ": "UTC",
        }
    )
    if service_key is not None:
        os.environ["NV_ATTESTATION_SERVICE_KEY"] = service_key


def collect(args: argparse.Namespace) -> dict[str, object]:
    gate_nonce = derive_gate_nonce(args.challenge_nonce, args.job_binding)
    record_relative = _relative(args.record_path, "gate record path")
    try:
        package_root = args.package_root.resolve(strict=True)
    except OSError as error:
        raise GateError(f"cannot resolve package root: {error}") from error
    if not package_root.is_dir():
        raise GateError("package root must be a directory")
    record_path = package_root / record_relative
    if record_path.exists() or record_path.is_symlink():
        raise GateError("H100 gate record destination already exists")
    evidence_relative = str(PurePosixPath(record_relative).parent / "h100-pre-run-evidence")
    evidence_path = package_root / evidence_relative
    if evidence_path.exists() or evidence_path.is_symlink():
        raise GateError("H100 pre-run evidence destination already exists")
    if args.dry_run:
        return {
            "accepted": False,
            "classification": "h100_pre_run_gate_dry_run_no_evidence",
            "gate_nonce": gate_nonce,
            "record_path": record_relative,
            "required_commands": [str(args.nvidia_smi), str(args.nvattest)],
            "verifier": args.verifier,
        }
    if os.geteuid() != 0:
        raise GateError("H100 gate requires root GPU device access")
    try:
        challenge_expiry = dt.datetime.strptime(
            args.challenge_expires_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError) as error:
        raise GateError("challenge expiry must be canonical UTC to whole seconds") from error
    if challenge_expiry <= dt.datetime.now(dt.timezone.utc):
        raise GateError("challenge expired before the H100 pre-run gate")
    _sanitize_environment(args.verifier == "remote")
    nvidia_smi = _which(args.nvidia_smi)
    nvattest = _which(args.nvattest)
    if not args.policy.is_file() or args.policy.is_symlink():
        raise GateError("NVIDIA relying-party policy is absent or a symlink")
    if (
        args.policy.resolve() == DEFAULT_POLICY.resolve()
        and not args.allow_development_policy
    ):
        raise GateError(
            "the checked-in baseline Rego is development-only; supply a production "
            "policy or explicitly opt into development"
        )
    stage = Path(tempfile.mkdtemp(prefix=".h100-pre-run-gate-", dir=record_path.parent))
    os.chmod(stage, 0o700)
    try:
        gpu_state = _require_gpu_state(stage, nvidia_smi)
        gpu = _collect_gpu(
            stage,
            nvattest,
            args.policy,
            gate_nonce,
            args.verifier,
            args.nras_url,
        )
        artifacts = _artifact_inventory(stage)
        evidence_manifest = {
            "artifacts": artifacts,
            "backend": "azure_ncc40ads_h100_v5",
            "challenge_nonce": args.challenge_nonce,
            "gate_nonce": gate_nonce,
            "gpu": gpu,
            "gpu_state": gpu_state,
            "job_binding_sha256": args.job_binding,
            "kind": "sparkinterval_h100_pre_run_evidence",
            "schema_version": 1,
            "status": "retained_pending_final_composite_appraisal",
        }
        manifest_bytes = canonical_json_bytes(evidence_manifest)
        (stage / "evidence-manifest.json").write_bytes(manifest_bytes)
        os.chmod(stage / "evidence-manifest.json", 0o400)
        os.replace(stage, evidence_path)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        gate_expiry = min(now + dt.timedelta(seconds=args.ttl_seconds), challenge_expiry)
        if gate_expiry <= now:
            raise GateError("no live overlap remains between gate and challenge")
        record = {
            "backend": "azure_ncc40ads_h100_v5",
            "challenge_nonce": args.challenge_nonce,
            "evidence_manifest_path": f"{evidence_relative}/evidence-manifest.json",
            "evidence_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "expires_at_utc": gate_expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gpu_cc_environment": "PRODUCTION",
            "gpu_cc_mode": "ON",
            "gpu_ready_state": "Ready",
            "job_binding_sha256": args.job_binding,
            "kind": "sparkinterval_h100_pre_run_gate",
            "schema_version": 1,
            "status": "release_allowed",
        }
        record_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        try:
            content = canonical_json_bytes(record)
            view = memoryview(content)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise GateError("short write while publishing H100 gate record")
                view = view[count:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {
            "accepted": False,
            "classification": "h100_pre_run_gate_completed_pending_final_composite_appraisal",
            "evidence_sha256": record["evidence_sha256"],
            "gate_nonce": gate_nonce,
            "record_path": record_relative,
            "status": "release_allowed",
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge-nonce", required=True)
    parser.add_argument("--challenge-expires-at", required=True)
    parser.add_argument("--job-binding", required=True)
    parser.add_argument("--package-root", type=Path, default=Path("."))
    parser.add_argument("--record-path", type=Path, required=True)
    parser.add_argument("--nvidia-smi", default="/usr/bin/nvidia-smi")
    parser.add_argument("--nvattest", default="/usr/local/bin/nvattest")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--verifier", choices=("local", "remote"), default="remote")
    parser.add_argument("--nras-url", default="https://nras.attestation.nvidia.com")
    parser.add_argument("--ttl-seconds", type=int, default=300, choices=range(30, 901))
    parser.add_argument("--allow-development-policy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = collect(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (GateError, EvidenceError, OSError, ValueError) as error:
        print(
            json.dumps(
                {"accepted": False, "classification": "h100_pre_run_gate_failed_closed", "error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
