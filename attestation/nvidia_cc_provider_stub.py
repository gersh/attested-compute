#!/usr/bin/env python3
"""Fail-closed placeholder for a future NVIDIA H100 CC evidence provider.

The program always exits with EX_CONFIG (78).  It writes a checklist, never a
certificate or an attestation envelope.  There is intentionally no flag that
turns this stub into a successful production provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gpu_listing() -> Optional[str]:
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return None
    try:
        completed = subprocess.run(
            [nvidia_smi, "-L"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    listing = completed.stdout.strip()
    return listing if completed.returncode == 0 and listing else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-manifest", type=Path)
    args = parser.parse_args()

    listing = gpu_listing()
    artifact = None
    if args.artifact_manifest is not None and args.artifact_manifest.is_file():
        artifact = {
            "file": str(args.artifact_manifest),
            "sha256": sha256_file(args.artifact_manifest),
            "status": "build_input_only_not_attested",
        }

    checklist = {
        "schema_version": "gpu-prover.nvidia-cc-checklist.v1",
        "kind": "production_acceptance_checklist",
        "provider_status": "NOT_IMPLEMENTED",
        "fail_closed": True,
        "evidence_class": "none",
        "production_evidence_emitted": False,
        "exit_code": os.EX_CONFIG,
        "local_observation": {
            "host_architecture": platform.machine(),
            "nvidia_smi_listing": listing,
            "h100_name_observed": bool(listing and "H100" in listing),
            "confidential_compute_mode_verified": False,
        },
        "artifact_manifest": artifact,
        "required_before_implementation_can_accept_a_run": [
            "Build and test the host runner for the H100 host architecture.",
            "Require an H100 in the intended NVIDIA confidential-computing mode.",
            "Collect fresh hardware evidence bound to a verifier-supplied nonce.",
            "Verify the complete NVIDIA evidence and certificate chain against pinned trust roots.",
            "Bind the measured executable or cubin, inputs, parameters, result digest, and successful completion.",
            "Reject stale evidence, replayed nonces, debug or non-CC modes, and every measurement mismatch.",
            "Pass tamper, replay, version-skew, driver-skew, and forced-failure acceptance tests on an H100.",
        ],
        "message": (
            "No production attestation provider exists in this repository yet; "
            "the command fails closed and emits only this checklist."
        ),
    }
    json.dump(checklist, fp=os.sys.stdout, indent=2, sort_keys=True)
    os.sys.stdout.write("\n")
    return os.EX_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
