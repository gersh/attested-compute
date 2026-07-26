#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed wrapper for the PT21 bitreverse+tile9 qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sparkinterval.tg.platt-pt21-live-transform-candidate-qualification.v1"
REPORT_SCHEMA = (
    "sparkinterval.tg.platt-pt21-bitreverse-tile9-qualification-report.v1"
)
SOURCE_MANIFEST_SCHEMA = (
    "sparkinterval.tg.pt21-bitreverse-tile9-repo-source-closure.v1"
)
SOURCE_MANIFEST = (
    ROOT
    / "reference/manifests/"
    "pt21_bitreverse_tile9_repo_source_closure.v1.json"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "cff3696bbc6ffec6f6c65f6b5ed169391"
    "1aa94f700dcac10bde5da168ce869be"
)
EXPECTED_STREAM_SHA256 = (
    "d484eb1f0d382ffcf3683e18cd0c9570"
    "c5a215efaa595cb9bb677e3c2ebfbdbc"
)
EXPECTED_STREAM_FILE_SHA256 = (
    "b1269afd7d15842fb15a86301627280ac"
    "ddd190de9a7e2d961510a555f14f391"
)
EXPECTED_ORDINARY_ALL_SHA256 = (
    "f11156870b9681147f3b48d70bd9bdc3"
    "613f015fa9a8783230fc731f49564224"
)
EXPECTED_ORDINARY_REQUIRED_SHA256 = (
    "3a12d63c8545aaf98ce6585994412a7e"
    "96c817a4b3d93e40da671c58883a97e4"
)
EXPECTED_ORDINARY_ARTIFACT_SHA256 = (
    "583a257079353e8efb334f1be2d7c415"
    "14a8f9759898f1dc1b2220fbda2dae60"
)
EXPECTED_CANDIDATE_ALL_SHA256 = (
    "06e55d44a684548c93f4ac48996fdca0"
    "6bca00e1ab4ba493d02f84d03bc16c19"
)
EXPECTED_CANDIDATE_REQUIRED_SHA256 = (
    "46ceeae8f719f85bf747a9b660f26c42"
    "6016859293e22bb0e653041365f60c57"
)
EXPECTED_CANDIDATE_ARTIFACT_SHA256 = (
    "65292e38a013baa83abc61bd5cdcd8c2"
    "e014032d9bceabe08d6fd5578d06ef89"
)


class QualificationError(RuntimeError):
    """The native differential report did not meet the candidate contract."""


def _sha256_fd(descriptor: int, byte_count: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < byte_count:
        chunk = os.pread(descriptor, min(1024 * 1024, byte_count - offset), offset)
        if not chunk:
            raise QualificationError("executable changed or truncated while hashing")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _read_fd(descriptor: int, byte_count: int) -> bytes:
    chunks = []
    offset = 0
    while offset < byte_count:
        chunk = os.pread(descriptor, min(1024 * 1024, byte_count - offset), offset)
        if not chunk:
            raise QualificationError("file changed or truncated while reading")
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _open_regular_nofollow(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink < 1:
        os.close(descriptor)
        raise QualificationError(f"{path} is not a linked regular file")
    return descriptor, metadata


def validate_repo_source_manifest(
    manifest_path: Path = SOURCE_MANIFEST,
) -> dict[str, object]:
    descriptor, metadata = _open_regular_nofollow(manifest_path)
    try:
        manifest_bytes = _read_fd(descriptor, metadata.st_size)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_sha256 != EXPECTED_SOURCE_MANIFEST_SHA256:
            raise QualificationError("repo source-closure manifest SHA-256 differs")
        value = json.loads(manifest_bytes.decode("utf-8"))
    finally:
        os.close(descriptor)
    if (
        not isinstance(value, dict)
        or value.get("schema") != SOURCE_MANIFEST_SCHEMA
    ):
        raise QualificationError("repo source-closure manifest schema differs")
    entries = value.get("files")
    if not isinstance(entries, list) or len(entries) != 17:
        raise QualificationError("repo source-closure file roster differs")
    paths: list[str] = []
    total_bytes = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise QualificationError("repo source-closure entry is malformed")
        relative = entry["path"]
        byte_count = entry["bytes"]
        expected_sha256 = entry["sha256"]
        if (
            not isinstance(relative, str)
            or relative.startswith("/")
            or "\\" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef"
                   for character in expected_sha256)
        ):
            raise QualificationError("repo source-closure entry is invalid")
        source_descriptor, source_metadata = _open_regular_nofollow(
            ROOT / relative
        )
        try:
            if (
                source_metadata.st_size != byte_count
                or _sha256_fd(source_descriptor, byte_count)
                != expected_sha256
            ):
                raise QualificationError(
                    f"repo source identity differs: {relative}"
                )
        finally:
            os.close(source_descriptor)
        paths.append(relative)
        total_bytes += byte_count
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise QualificationError("repo source-closure paths are not canonical")
    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "sha256": manifest_sha256,
        "bytes": metadata.st_size,
        "file_count": len(entries),
        "source_bytes": total_bytes,
        "depfile_derived": True,
        "external_build_dependencies_pinned": False,
        "compiler_refinement_proved": False,
    }


def _boolean(row: dict[str, object], field: str, expected: bool) -> None:
    if row.get(field) is not expected:
        raise QualificationError(f"native report {field} differs")


def _finite_positive(value: object, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise QualificationError(f"{what} is not finite and positive")
    return float(value)


EXPECTED_STREAM_REPLAY = [
    {
        "stream": 0,
        "direct_event_count": 71,
        "stationary_candidate_count": 0,
        "certified_direct_multiplicity_slots": 71,
        "direct_nleft_units": -18200,
        "direct_nright_units": 18081,
    },
    {
        "stream": 1,
        "direct_event_count": 3397,
        "stationary_candidate_count": 1,
        "certified_direct_multiplicity_slots": 3397,
        "direct_nleft_units": -41749543,
        "direct_nright_units": 41731732,
    },
    {
        "stream": 2,
        "direct_event_count": 71,
        "stationary_candidate_count": 0,
        "certified_direct_multiplicity_slots": 71,
        "direct_nleft_units": -18240,
        "direct_nright_units": 18041,
    },
]


def _validate_variant(
    value: object,
    expected_name: str,
    *,
    all_sha256: str,
    required_sha256: str,
    artifact_sha256: str,
    digest_xor: str,
    maximum_radius_bits: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("name") != expected_name:
        raise QualificationError(f"{expected_name} variant is absent")
    if (
        value.get("all_sample_sha256") != all_sha256
        or value.get("required_sample_sha256") != required_sha256
        or value.get("scanner_artifact_sha256") != artifact_sha256
        or value.get("required_digest_xor") != digest_xor
        or value.get("maximum_required_radius_bits") != maximum_radius_bits
        or value.get("transform_failure_flags") != 0
        or value.get("required_invalid") != 0
        or value.get("required_ambiguous") != 0
        or value.get("scanner_failure_flags") != 0
        or value.get("finite_and_reproduced") is not True
        or value.get("scanner_accepted") is not True
        or value.get("scanner_device_matches_host") is not True
        or value.get("scanner_shared_endpoints_agree") is not True
        or value.get("streams") != EXPECTED_STREAM_REPLAY
    ):
        raise QualificationError(f"{expected_name} known answer differs")
    return value


def validate_native_report(
    value: object, *, forced_rejection: bool, repetitions: int
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QualificationError("native report is not a JSON object")
    row = value
    if row.get("schema") != SCHEMA:
        raise QualificationError("native report schema differs")
    _boolean(row, "accepted", True)
    _boolean(row, "candidate_semantic_gates_accepted", True)
    _boolean(row, "candidate_rejection_forced_for_test", forced_rejection)
    _boolean(row, "candidate_qualified", not forced_rejection)
    _boolean(row, "qualification_only", True)
    _boolean(row, "gamma_stream_authenticated_before_gpu_allocation", True)
    _boolean(row, "single_accumulator_workspace", True)
    _boolean(row, "single_transform_workspace", True)
    _boolean(row, "single_event_scanner_workspace", True)
    _boolean(row, "ordinary_known_answer", True)
    _boolean(row, "settled_sloppy_known_answer", True)
    _boolean(row, "tile9_sloppy_known_answer", True)
    _boolean(row, "tile_settled_all_sample_bytes_identical", True)
    _boolean(row, "tile_settled_replay_artifact_identical", True)
    _boolean(row, "ordinary_sloppy_event_topology_identical", True)
    _boolean(row, "source_geometry_accepted", True)
    if (
        row.get("first_block") != 0
        or row.get("block_count") != 1
        or row.get("repetitions") != repetitions
        or row.get("gamma_stream_file_bytes") != 848
        or row.get("gamma_stream_file_sha256")
        != EXPECTED_STREAM_FILE_SHA256
        or row.get("accumulator_workspace_device_bytes") != 570977292
        or row.get("transform_workspace_device_bytes") != 195429316
        or row.get("event_scanner_workspace_device_bytes") != 7750989
    ):
        raise QualificationError("source-shaped block-0 identity differs")
    if row.get("gamma_stream_logical_sha256") != EXPECTED_STREAM_SHA256:
        raise QualificationError("authenticated logical stream digest differs")
    if row.get("gamma_summary") != {
        "logical_block": 0,
        "invalid_disks": 0,
        "digest": "1f06f98539bba568",
        "maximum_radius_bits": "3ae12980bb87079a",
        "known_answer": True,
    }:
        raise QualificationError("Gamma synthesis known answer differs")
    if row.get("accumulator_audit") != {
        "active_cells": 153502,
        "inactive_cells": 600162,
        "malformed_active_cells": 0,
        "nonzero_inactive_cells": 0,
        "offsets_bounded_monotone": True,
        "active_roster_exact": True,
        "geometry_sha256":
            "67dc2eda921762f6ad1eaf046188b9500"
            "b1b19c87b46e60facf30cfb3bf28ad4",
        "accepted": True,
    }:
        raise QualificationError("source accumulator audit differs")
    if row.get("root_table_audit") != {
        "before_sha256":
            "0b4e51572104edf59d096d680ca010a5"
            "15157208c6cdba14be867d9c22d52040",
        "after_sha256":
            "0b4e51572104edf59d096d680ca010a5"
            "15157208c6cdba14be867d9c22d52040",
        "immutable": True,
        "accepted": True,
    }:
        raise QualificationError("root-table identity differs")
    if row.get("selected_implementation") != (
        "ordinary-fallback" if forced_rejection else "tile9-sloppy-root"
    ):
        raise QualificationError("native selected implementation differs")
    if row.get("fallback_exercised") is not forced_rejection:
        raise QualificationError("fallback execution status differs")
    if row.get("fallback_reproduced_ordinary") is not forced_rejection:
        raise QualificationError("fallback reproduction status differs")

    containment = row.get("exact_all_sample_containment")
    if not isinstance(containment, dict) or containment != {
        "sample_count": 131072,
        "malformed": 0,
        "radius_order_failures": 0,
        "squared_distance_failures": 0,
        "accepted": True,
    }:
        raise QualificationError("exact all-sample containment differs")
    signs = row.get("required_sign_comparison")
    if not isinstance(signs, dict) or signs != {
        "ordinary_ambiguous": 0,
        "ordinary_malformed": 0,
        "candidate_ambiguous": 0,
        "candidate_malformed": 0,
        "mismatch": 0,
        "accepted": True,
    }:
        raise QualificationError("required sign comparison differs")
    variants = row.get("variants")
    if not isinstance(variants, list) or len(variants) != 3:
        raise QualificationError("native variant roster differs")
    _validate_variant(
        variants[0],
        "ordinary",
        all_sha256=EXPECTED_ORDINARY_ALL_SHA256,
        required_sha256=EXPECTED_ORDINARY_REQUIRED_SHA256,
        artifact_sha256=EXPECTED_ORDINARY_ARTIFACT_SHA256,
        digest_xor="55c2a006ce805986",
        maximum_radius_bits="3d59e1dd5c163e26",
    )
    for index, name in (
        (1, "settled-sloppy-root"),
        (2, "tile9-sloppy-root"),
    ):
        _validate_variant(
            variants[index],
            name,
            all_sha256=EXPECTED_CANDIDATE_ALL_SHA256,
            required_sha256=EXPECTED_CANDIDATE_REQUIRED_SHA256,
            artifact_sha256=EXPECTED_CANDIDATE_ARTIFACT_SHA256,
            digest_xor="094f3182295e6c3f",
            maximum_radius_bits="3d59e1dd5cf62222",
        )

    resources = row.get("kernel_resources")
    if not isinstance(resources, dict):
        raise QualificationError("candidate resource report is absent")
    if (
        resources.get("accepted") is not True
        or resources.get("local_bytes_per_thread") != 0
        or resources.get("static_shared_bytes") != 32768
        or not isinstance(resources.get("registers_per_thread"), int)
        or not 1 <= int(resources["registers_per_thread"]) <= 255
        or not isinstance(resources.get("maximum_threads_per_block"), int)
        or int(resources["maximum_threads_per_block"]) < 256
        or not isinstance(
            resources.get("active_blocks_per_multiprocessor"), int
        )
        or int(resources["active_blocks_per_multiprocessor"]) < 1
    ):
        raise QualificationError("actual fused-kernel resources fail closed")

    for field in (
        "candidate_selected_in_production",
        "receipt_emitted",
        "secure_enclave_attested",
        "cuda_to_lean_refinement_proved",
        "ordinary_hardy_z_realization_proved",
        "flint_to_mathlib_proved",
        "all_window_coverage_complete",
        "stationary_turing_closure_complete",
        "source_claim_ready",
        "production_ready",
        "pt21_atom_discharged",
        "performance_evidence_eligible",
    ):
        _boolean(row, field, False)
    if row.get("runtime_instrumentation_status") != "not-inspected-by-runner":
        raise QualificationError("runtime instrumentation status differs")

    timing = row.get("timing")
    if not isinstance(timing, dict):
        raise QualificationError("timing report is absent")
    if forced_rejection:
        if any(value != 0 for value in timing.values()):
            raise QualificationError("fallback run must not report candidate timing")
    else:
        for field in (
            "ordinary_median_ms",
            "settled_sloppy_median_ms",
            "tile9_sloppy_median_ms",
        ):
            _finite_positive(timing.get(field), f"timing.{field}")
    return row


def run_native(
    executable: Path,
    expected_executable_sha256: str,
    stream: Path,
    repetitions: int,
    forced_rejection: bool,
) -> tuple[dict[str, object], str, int]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(executable, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink < 1:
            raise QualificationError("executable is not a linked regular file")
        digest = _sha256_fd(descriptor, metadata.st_size)
        if digest != expected_executable_sha256:
            raise QualificationError("executable SHA-256 differs")
        command = [
            f"/proc/self/fd/{descriptor}",
            str(stream),
            f"--expected-stream-sha256={EXPECTED_STREAM_SHA256}",
            f"--repetitions={repetitions}",
        ]
        if forced_rejection:
            command.append("--force-candidate-rejection-for-test")
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            pass_fds=(descriptor,),
            timeout=180,
        )
        if completed.returncode != 0 or completed.stderr:
            raise QualificationError(
                "native qualifier failed: "
                f"exit={completed.returncode} stderr={completed.stderr!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise QualificationError("native qualifier did not emit one JSON line")
        report = validate_native_report(
            json.loads(lines[0]),
            forced_rejection=forced_rejection,
            repetitions=repetitions,
        )
        if _sha256_fd(descriptor, metadata.st_size) != digest:
            raise QualificationError("executable changed during qualification")
        return report, digest, metadata.st_size
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--stream", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=9)
    parser.add_argument(
        "--force-candidate-rejection-for-test", action="store_true"
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.repetitions <= 101:
        parser.error("--repetitions must be in 1..101")
    if (
        len(arguments.expected_executable_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in arguments.expected_executable_sha256
        )
    ):
        parser.error("--expected-executable-sha256 must be lowercase hex")
    try:
        source_identity_before = validate_repo_source_manifest()
        native, digest, byte_count = run_native(
            arguments.executable,
            arguments.expected_executable_sha256,
            arguments.stream,
            arguments.repetitions,
            arguments.force_candidate_rejection_for_test,
        )
        source_identity_after = validate_repo_source_manifest()
        if source_identity_after != source_identity_before:
            raise QualificationError(
                "repo source identity changed during qualification"
            )
    except (OSError, ValueError, json.JSONDecodeError, QualificationError) as error:
        print(f"qualify_pt21_bitreverse_tile9: {error}", file=sys.stderr)
        return 2
    output = {
        "schema": REPORT_SCHEMA,
        "accepted": True,
        "candidate": "pt21-bitreverse-tile9-sloppy-root",
        "nested_candidate_label": "tile9-sloppy-root",
        "nested_candidate_label_is_inherited_alias": True,
        "executable_sha256": digest,
        "executable_bytes": byte_count,
        "audited_source_snapshot": source_identity_before,
        "audited_source_snapshot_validated": True,
        "binary_to_source_binding_proved": False,
        "build_flags_authenticated": False,
        "external_headers_authenticated": False,
        "native_report": native,
        "source_claim_ready": False,
        "production_ready": False,
        "receipt_emitted": False,
        "compiler_refinement_proved": False,
        "h100_performance_claimed": False,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
