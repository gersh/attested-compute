#!/usr/bin/env python3
"""Create development-only mock evidence from an offline H100 build manifest.

This module deliberately emits no signature and makes no execution claim.  Its
only purpose is exercising parsers and downstream proof plumbing before H100
confidential-computing integration is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_offline_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    if manifest.get("evidence_class") != "offline_device_build":
        raise ValueError("manifest is not offline_device_build evidence")
    if manifest.get("execution", {}).get("executed") is not False:
        raise ValueError("offline manifest unexpectedly contains an execution claim")
    if manifest.get("production_attestation", {}).get("present") is not False:
        raise ValueError("offline manifest unexpectedly claims production attestation")
    return manifest


def checked_cubin(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, str]:
    cubin_entry = manifest.get("artifacts", {}).get("cubin")
    if not isinstance(cubin_entry, dict):
        raise ValueError("offline manifest has no cubin artifact")

    filename = cubin_entry.get("file")
    expected_hash = cubin_entry.get("sha256")
    if not isinstance(filename, str) or not isinstance(expected_hash, str):
        raise ValueError("offline manifest cubin entry is malformed")

    cubin_path = (manifest_path.parent / filename).resolve()
    if manifest_path.parent not in cubin_path.parents:
        raise ValueError("cubin artifact escapes the offline build directory")
    actual_hash = sha256_file(cubin_path)
    if actual_hash != expected_hash:
        raise ValueError("cubin hash does not match the offline manifest")
    return {"file": filename, "sha256": actual_hash}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = load_offline_manifest(manifest_path)
    cubin = checked_cubin(manifest_path, manifest)

    evidence = {
        "schema_version": "gpu-prover.mock-attestation.v1",
        "evidence_class": "mock_attested",
        "evidence_role": "development_parser_fixture_only",
        "production_acceptable": False,
        "cryptographically_authenticated": False,
        "hardware_attestation_present": False,
        "h100_execution_claimed": False,
        "algorithm_executed": False,
        "nonce": args.nonce,
        "offline_build_manifest": {
            "file": manifest_path.name,
            "sha256": sha256_file(manifest_path),
        },
        "device_artifact": cubin,
        "synthetic_result": {
            "status": "not_executed",
            "result": None,
        },
        "rejection_rule": (
            "Production verifiers MUST reject evidence_class=mock_attested and "
            "production_acceptable=false."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
