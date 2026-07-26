#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Prepare and audit the historical Helfgott--Platt terminal boundary.

``assemble`` transactionally constructs the canonical terminal tree from the
two final operational exports and all 8,512 signed producer receipts.
``index`` constructs the canonical child index inside an already assembled
tree.  ``prepare`` verifies every signed child and both complete retained
branches before emitting the immutable commitment and handoff archive.
``audit`` independently checks the signed CPU terminal job and emits a
review-only Lean pin candidate.  It never installs production pins.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "tools", ROOT / "attestation", ROOT / "azure"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from create_run_bundle import load_canonical_json  # noqa: E402
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402
from tg_verifier.azure_cpu_goldbach_historical_materializer import (  # noqa: E402
    MANIFEST_KIND,
)
from tg_verifier.azure_cpu_goldbach_historical_workload_factory import (  # noqa: E402
    REGISTERED_INVOCATION,
    TERMINAL_FACTORY,
    expected_registered_hashes,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from tg_verifier.goldbach_historical_terminal import (  # noqa: E402
    CHILD_INDEX_KIND,
    H100_PHASE,
    LADDER_PHASE,
    NOT_APPLICABLE_DIGEST,
    HistoricalGoldbachTerminalError,
    expected_child_topology,
    load_child_identity_commitment,
    prepare_terminal_handoff_commitment,
)
from tg_goldbach_historical_operational_azure_measured_workload import (  # noqa: E402
    MAX_EXPORT_BYTES,
    MAX_EXPORT_FILES,
    _copy_file,
    _copy_tree,
    _validate_export,
)


CANDIDATE_KIND = (
    "sparkinterval.helfgott-platt-goldbach-terminal-registration-candidate.v1"
)
SCHEMA_VERSION = 1
INDEX_ENTRY_FIELDS = {
    "phase",
    "receipt_file_sha256",
    "receipt_file_size_bytes",
    "receipt_path",
    "shard_index",
}
ARTIFACT_RECORD_FIELDS = {
    "executable",
    "path",
    "role",
    "sha256",
    "size_bytes",
    "statement_role",
}
PIN_DEFINITIONS = {
    "bundle_sha256": "helfgottPlattGoldbachTerminalIdentityBundleSha256",
    "receipt_sha256": "helfgottPlattGoldbachTerminalReceiptSha256",
    "job_spec_sha256": "helfgottPlattGoldbachTerminalJobSpecSha256",
    "artifact_closure_manifest_sha256": (
        "helfgottPlattGoldbachTerminalArtifactClosureSha256"
    ),
    "source_tree_hash": "helfgottPlattGoldbachTerminalSourceTreeSha256",
    "host_executable_hash": (
        "helfgottPlattGoldbachTerminalHostExecutableSha256"
    ),
    "kernel_manifest_hash": (
        "helfgottPlattGoldbachTerminalPostRunCommitmentSha256"
    ),
    "child_identities_sha256": (
        "helfgottPlattGoldbachChildReceiptIdentitiesSha256"
    ),
    "build_admission_sha256": (
        "helfgottPlattGoldbachBuildAdmissionSha256"
    ),
    "runtime_closure_sha256": (
        "helfgottPlattGoldbachTerminalRuntimeClosureSha256"
    ),
    "terminal_handoff_sha256": (
        "helfgottPlattGoldbachTerminalHandoffSha256"
    ),
}


class HistoricalGoldbachRegistrationError(RuntimeError):
    """A handoff, signed terminal, materialization, or pin differed."""


def _write_exclusive(path: Path, raw: bytes, *, mode: int = 0o400) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        mode,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(f"short write while publishing {path}")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _safe_file(root: Path, value: Any, what: str) -> Path:
    if not isinstance(value, str):
        raise HistoricalGoldbachRegistrationError(f"{what} path must be text")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise HistoricalGoldbachRegistrationError(
            f"{what} path must be canonical and relative"
        )
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise HistoricalGoldbachRegistrationError(
            f"{what} escapes or is absent: {error}"
        ) from error
    if candidate.is_symlink() or not resolved.is_file():
        raise HistoricalGoldbachRegistrationError(
            f"{what} must be a nonsymlink regular file"
        )
    return resolved


def _artifact_path(root: Path, record: Any, what: str) -> Path:
    if not isinstance(record, dict) or set(record) != ARTIFACT_RECORD_FIELDS:
        raise HistoricalGoldbachRegistrationError(
            f"{what} artifact record has wrong fields"
        )
    path = _safe_file(root, record["path"], what)
    if hash_file_once(path) != (record["sha256"], record["size_bytes"]):
        raise HistoricalGoldbachRegistrationError(
            f"{what} differs from its artifact record"
        )
    executable = bool(path.stat().st_mode & 0o111)
    if record["executable"] is not executable:
        raise HistoricalGoldbachRegistrationError(
            f"{what} executable mode differs"
        )
    return path


def _one_role(
    records: list[dict[str, Any]], field: str, value: str,
) -> dict[str, Any]:
    found = [row for row in records if row[field] == value]
    if len(found) != 1:
        raise HistoricalGoldbachRegistrationError(
            f"terminal closure requires exactly one {field}={value}"
        )
    return found[0]


def build_child_index(handoff_root: Path) -> dict[str, Any]:
    """Pin canonical child receipt paths in topology order."""

    root = handoff_root.resolve(strict=True)
    if handoff_root.is_symlink() or not root.is_dir():
        raise HistoricalGoldbachRegistrationError(
            "handoff root must be a nonsymlink directory"
        )
    entries: list[dict[str, Any]] = []
    for phase, shard_index in expected_child_topology():
        family = "h100" if phase == H100_PHASE else "ladder"
        relative = (
            Path("children")
            / family
            / f"receipt-{shard_index:08d}.json"
        )
        path = _safe_file(root, relative.as_posix(), "child receipt")
        digest, size = hash_file_once(path)
        entries.append(
            {
                "phase": phase,
                "receipt_file_sha256": digest,
                "receipt_file_size_bytes": size,
                "receipt_path": relative.as_posix(),
                "shard_index": shard_index,
            }
        )
    return {
        "entries": entries,
        "kind": CHILD_INDEX_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def prepare_handoff(args: argparse.Namespace) -> dict[str, Any]:
    admission = load_build_admission(
        args.build_admission, allow_test_fixture=args.allow_test_fixture
    )
    root = args.handoff_root.resolve(strict=True)
    commitment, identities = prepare_terminal_handoff_commitment(
        root,
        key_manifest=args.key_manifest,
        admission=admission,
        allow_development_key=args.allow_development_key,
    )
    _write_exclusive(args.commitment_output, canonical_json_bytes(commitment))
    try:
        args.archive_output.parent.mkdir(
            mode=0o700, parents=True, exist_ok=True
        )
        create_archive(root, args.archive_output)
    except BaseException:
        args.commitment_output.unlink(missing_ok=True)
        raise
    archive_sha256, archive_size = hash_file_once(args.archive_output)
    return {
        "accepted": False,
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_size,
        "child_count": len(identities),
        "child_identities_sha256": commitment["child_identities_sha256"],
        "classification": (
            "verified_historical_goldbach_terminal_handoff_"
            "not_execution_evidence"
        ),
        "commitment_sha256": hash_file_once(args.commitment_output)[0],
    }


def _copy_receipt_family(
    source_root: Path,
    destination_root: Path,
    *,
    count: int,
    what: str,
) -> None:
    try:
        source = source_root.resolve(strict=True)
    except OSError as error:
        raise HistoricalGoldbachRegistrationError(
            f"{what} receipt directory is unavailable: {error}"
        ) from error
    if source_root.is_symlink() or not source.is_dir():
        raise HistoricalGoldbachRegistrationError(
            f"{what} receipt root must be a nonsymlink directory"
        )
    expected = {f"receipt-{index:08d}.json" for index in range(count)}
    actual: set[str] = set()
    for path in source.iterdir():
        if path.is_symlink() or not path.is_file():
            raise HistoricalGoldbachRegistrationError(
                f"{what} receipt root contains a linked or non-file entry"
            )
        actual.add(path.name)
    if actual != expected:
        raise HistoricalGoldbachRegistrationError(
            f"{what} receipt root does not exactly cover {count} groups"
        )
    destination_root.mkdir(mode=0o700, parents=True)
    for index in range(count):
        name = f"receipt-{index:08d}.json"
        _copy_file(source / name, destination_root / name)


def _require_children(
    root: Path, expected: set[str], what: str,
) -> None:
    if root.is_symlink() or not root.is_dir():
        raise HistoricalGoldbachRegistrationError(
            f"{what} payload is not a nonsymlink directory"
        )
    actual = {path.name for path in root.iterdir()}
    if actual != expected:
        raise HistoricalGoldbachRegistrationError(
            f"{what} payload has unexpected or missing top-level entries"
        )


def assemble_handoff(args: argparse.Namespace) -> dict[str, Any]:
    """Build and fully verify the terminal tree from final DAG outputs."""

    for path, what in (
        (args.handoff_root, "handoff root"),
        (args.commitment_output, "commitment output"),
        (args.archive_output, "archive output"),
    ):
        if path.exists() or path.is_symlink():
            raise HistoricalGoldbachRegistrationError(
                f"{what} must not already exist"
            )
    args.handoff_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = args.handoff_root.parent.resolve(strict=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{args.handoff_root.name}.assembling-",
            dir=parent,
        )
    )
    scratch = Path(
        tempfile.mkdtemp(
            prefix=".historical-goldbach-exports-",
            dir=parent,
        )
    )
    commitment_published = False
    archive_published = False
    handoff_published = False
    try:
        binary_export = scratch / "binary"
        ladder_export = scratch / "ladder"
        extract_archive(
            args.binary_replay_export,
            binary_export,
            maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
        extract_archive(
            args.ladder_reduce_export,
            ladder_export,
            maximum_files=MAX_EXPORT_FILES,
            maximum_bytes=MAX_EXPORT_BYTES,
        )
        _validate_export(binary_export, "binary-semantic-replay", 0)
        _validate_export(
            ladder_export, "reduce-prime-ladder-ranges", 0
        )
        binary_payload = binary_export / "payload"
        _require_children(
            binary_payload,
            {
                "binary-aggregate.json",
                "binary-plan.json",
                "binary-receipts",
            },
            "binary replay",
        )
        ladder_payload = ladder_export / "payload"
        _require_children(
            ladder_payload, {"prime-ladder"}, "ladder reduction"
        )
        binary_target = stage / "binary"
        binary_target.mkdir(mode=0o700)
        _copy_file(
            binary_payload / "binary-plan.json",
            binary_target / "plan.json",
        )
        _copy_tree(
            binary_payload / "binary-receipts",
            binary_target / "receipts",
        )
        _copy_file(
            binary_payload / "binary-aggregate.json",
            binary_target / "aggregate.json",
        )
        ladder_source = ladder_payload / "prime-ladder"
        _copy_tree(ladder_source, stage / "ladder/campaign")
        _copy_file(
            ladder_source / "ladder-aggregate.json",
            stage / "ladder/aggregate.json",
        )
        _copy_receipt_family(
            args.h100_receipts_root,
            stage / "children/h100",
            count=8_192,
            what="H100",
        )
        _copy_receipt_family(
            args.ladder_receipts_root,
            stage / "children/ladder",
            count=320,
            what="ladder",
        )
        index = build_child_index(stage)
        _write_exclusive(
            stage / "children/index.json", canonical_json_bytes(index)
        )
        admission = load_build_admission(
            args.build_admission,
            allow_test_fixture=args.allow_test_fixture,
        )
        commitment, identities = prepare_terminal_handoff_commitment(
            stage,
            key_manifest=args.key_manifest,
            admission=admission,
            allow_development_key=args.allow_development_key,
        )
        _write_exclusive(
            args.commitment_output, canonical_json_bytes(commitment)
        )
        commitment_published = True
        args.archive_output.parent.mkdir(
            mode=0o700, parents=True, exist_ok=True
        )
        create_archive(stage, args.archive_output)
        archive_published = True
        os.replace(stage, args.handoff_root)
        handoff_published = True
        archive_sha256, archive_size = hash_file_once(args.archive_output)
        return {
            "accepted": False,
            "archive_sha256": archive_sha256,
            "archive_size_bytes": archive_size,
            "child_count": len(identities),
            "child_identities_sha256": commitment[
                "child_identities_sha256"
            ],
            "classification": (
                "assembled_and_verified_historical_goldbach_terminal_"
                "handoff_not_execution_evidence"
            ),
            "commitment_sha256": hash_file_once(
                args.commitment_output
            )[0],
            "handoff_root": str(args.handoff_root.resolve(strict=True)),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if not handoff_published:
            shutil.rmtree(stage, ignore_errors=True)
            if archive_published:
                args.archive_output.unlink(missing_ok=True)
            if commitment_published:
                args.commitment_output.unlink(missing_ok=True)


def _validate_terminal(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, str]]:
    admission = load_build_admission(
        args.build_admission, allow_test_fixture=args.allow_test_fixture
    )
    receipt = load_verified_receipt(
        args.terminal_receipt,
        key_manifest=args.key_manifest,
        allow_development_key=args.allow_development_key,
    )
    artifact_root = args.artifact_root.resolve(strict=True)
    if args.artifact_root.is_symlink() or not artifact_root.is_dir():
        raise HistoricalGoldbachRegistrationError(
            "terminal artifact root must be a nonsymlink directory"
        )
    job_path = artifact_root / "job.json"
    job = validate_job_spec(load_canonical_json(job_path))
    claim = receipt["claim"]
    expected = registered_invocation_expected(REGISTERED_INVOCATION)
    local = expected_registered_hashes()
    factory = TERMINAL_FACTORY
    if (
        receipt["backend"] != "azure_sevsnp_cpu"
        or any(claim.get(field) != value for field, value in expected.items())
        or claim.get("result") != "true"
        or job["algorithm"]["algorithm_id"] != factory.algorithm_id
        or job["algorithm"]["canonical_definition"]
        != factory.algorithm_definition
        or job["algorithm"]["definition_sha256"] != local["algorithm_hash"]
        or job["input_artifact"]["sha256"] != local["input_hash"]
        or job["parameters"]["canonical_sha256"] != local["parameters_hash"]
        or job["domain_coverage"]["canonical_sha256"]
        != local["domain_hash"]
        or job["backend"] != "azure_sevsnp_cpu"
        or job["command"]["argv"] != list(factory.command_argv)
        or job["output_contract"]["path"]
        != "output/registered-result.txt"
        or job["work_trace_contract"]["verifier_argv"]
        != list(factory.trace_verifier_argv)
        or claim.get("target_profile_hash")
        != job["target_profile"]["sha256"]
        or claim.get("trust_profile_hash")
        != job["trust_profile"]["sha256"]
        or claim.get("artifacts", {}).get("device_cubin_hash")
        != NOT_APPLICABLE_DIGEST
    ):
        raise HistoricalGoldbachRegistrationError(
            "terminal receipt/job is not the exact registered invocation"
        )
    records = job["artifact_closure"]["files"]
    if records != sorted(records, key=lambda row: row["path"]):
        raise HistoricalGoldbachRegistrationError(
            "terminal artifact closure is not path sorted"
        )
    for index, record in enumerate(records):
        _artifact_path(artifact_root, record, f"terminal artifact {index}")
    closure_sha256 = canonical_sha256(_closure_manifest(records))
    if (
        closure_sha256 != job["artifact_closure"]["manifest_sha256"]
        or claim["artifacts"]["kernel_manifest_hash"] != closure_sha256
    ):
        raise HistoricalGoldbachRegistrationError(
            "terminal execution closure differs from its signed statement"
        )
    host = _one_role(records, "statement_role", "host_executable")
    source = _one_role(records, "statement_role", "source_tree")
    if (
        claim["artifacts"]["host_executable_hash"] != host["sha256"]
        or claim["artifacts"]["source_tree_hash"] != source["sha256"]
    ):
        raise HistoricalGoldbachRegistrationError(
            "terminal host/source statement roles differ"
        )

    admission_record = _one_role(
        records, "role", "reviewed_goldbach_build_admission"
    )
    commitment_record = _one_role(
        records, "role", "historical_goldbach_child_identity_commitment"
    )
    handoff_record = _one_role(
        records, "role", "historical_goldbach_complete_branch_handoff"
    )
    runtime_record = _one_role(
        records, "role", "image_runtime_closure_manifest"
    )
    source_record = _one_role(
        records, "role", "reviewed_source_closure_manifest"
    )
    binding_record = _one_role(
        records,
        "role",
        "historical_goldbach_terminal_post_child_run_binding",
    )
    if (
        admission_record["sha256"] != admission.admission_sha256
        or admission_record["size_bytes"] != admission.admission_size_bytes
    ):
        raise HistoricalGoldbachRegistrationError(
            "terminal closure contains another build admission"
        )
    commitment, commitment_sha256 = load_child_identity_commitment(
        _artifact_path(artifact_root, commitment_record, "child commitment"),
        expected_sha256=commitment_record["sha256"],
    )
    binding = load_canonical_json(
        _artifact_path(artifact_root, binding_record, "terminal binding")
    )
    expected_binding = {
        "build_admission_sha256": admission.admission_sha256,
        "child_identity_commitment_sha256": commitment_sha256,
        "child_verifier_key_manifest_sha256": _one_role(
            records, "role", "child_receipt_verifier_key_manifest"
        )["sha256"],
        "kind": (
            "sparkinterval.helfgott-platt-goldbach-terminal-"
            "post-child-run-binding.v1"
        ),
        "runner_policy_sha256": job["runner_policy"]["sha256"],
        "runtime_closure_sha256": runtime_record["sha256"],
        "schema_version": 1,
        "source_manifest_sha256": source_record["sha256"],
        "target_profile_sha256": claim["target_profile_hash"],
        "terminal_handoff_sha256": handoff_record["sha256"],
        "terminal_host_executable_sha256": host["sha256"],
        "trust_profile_sha256": claim["trust_profile_hash"],
    }
    if binding != expected_binding:
        raise HistoricalGoldbachRegistrationError(
            "terminal post-child binding differs from its complete identity"
        )

    manifest = load_canonical_json(args.materialization_manifest)
    job_sha256, job_size = hash_file_once(job_path)
    manifest_sha256, _manifest_size = hash_file_once(
        args.materialization_manifest
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("registered_invocation") != REGISTERED_INVOCATION
        or manifest.get("build_admission_sha256")
        != admission.admission_sha256
        or manifest.get("child_identity_commitment_sha256")
        != commitment_sha256
        or manifest.get("terminal_handoff_sha256")
        != handoff_record["sha256"]
        or manifest.get("job_spec", {}).get("sha256") != job_sha256
        or manifest.get("job_spec", {}).get("size_bytes") != job_size
    ):
        raise HistoricalGoldbachRegistrationError(
            "terminal materialization manifest differs from the signed job"
        )
    candidate = {
        "artifact_closure_manifest_sha256": closure_sha256,
        "build_admission_sha256": admission.admission_sha256,
        "child_identities_sha256": commitment["child_identities_sha256"],
        "classification": "post-run-candidate",
        "host_executable_hash": host["sha256"],
        "job_spec_sha256": job_sha256,
        "kernel_manifest_hash": claim["artifacts"]["kernel_manifest_hash"],
        "kind": CANDIDATE_KIND,
        "materialization_manifest_sha256": manifest_sha256,
        "receipt_sha256": receipt["receipt_sha256"],
        "registered_invocation": REGISTERED_INVOCATION,
        "runtime_closure_sha256": runtime_record["sha256"],
        "schema_version": SCHEMA_VERSION,
        "source_tree_hash": source["sha256"],
        "terminal_handoff_sha256": handoff_record["sha256"],
    }
    raw = canonical_json_bytes(candidate)
    pins = {
        **{
            field: candidate[field]
            for field in PIN_DEFINITIONS
            if field != "bundle_sha256"
        },
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return candidate, pins


def render_lean_pin_candidate(pins: Mapping[str, str]) -> str:
    lines = [
        "/- Review-only candidate. Do not install without independent audit. -/",
        "",
    ]
    for field, lean_name in PIN_DEFINITIONS.items():
        lines.append(
            f'def {lean_name} : Option Digest := some "{pins[field]}"'
        )
    lines.append("")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser("assemble")
    assemble.add_argument(
        "--binary-replay-export", type=Path, required=True
    )
    assemble.add_argument(
        "--ladder-reduce-export", type=Path, required=True
    )
    assemble.add_argument(
        "--h100-receipts-root", type=Path, required=True
    )
    assemble.add_argument(
        "--ladder-receipts-root", type=Path, required=True
    )
    assemble.add_argument("--handoff-root", type=Path, required=True)
    assemble.add_argument("--key-manifest", type=Path, required=True)
    assemble.add_argument("--build-admission", type=Path, required=True)
    assemble.add_argument("--commitment-output", type=Path, required=True)
    assemble.add_argument("--archive-output", type=Path, required=True)
    assemble.add_argument(
        "--allow-test-fixture", action="store_true", help=argparse.SUPPRESS
    )
    assemble.add_argument(
        "--allow-development-key", action="store_true", help=argparse.SUPPRESS
    )

    index = subparsers.add_parser("index")
    index.add_argument("--handoff-root", type=Path, required=True)
    index.add_argument("--output", type=Path, required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--handoff-root", type=Path, required=True)
    prepare.add_argument("--key-manifest", type=Path, required=True)
    prepare.add_argument("--build-admission", type=Path, required=True)
    prepare.add_argument("--commitment-output", type=Path, required=True)
    prepare.add_argument("--archive-output", type=Path, required=True)
    prepare.add_argument(
        "--allow-test-fixture", action="store_true", help=argparse.SUPPRESS
    )
    prepare.add_argument(
        "--allow-development-key", action="store_true", help=argparse.SUPPRESS
    )

    audit = subparsers.add_parser("audit")
    audit.add_argument("--terminal-receipt", type=Path, required=True)
    audit.add_argument("--key-manifest", type=Path, required=True)
    audit.add_argument("--build-admission", type=Path, required=True)
    audit.add_argument("--artifact-root", type=Path, required=True)
    audit.add_argument("--materialization-manifest", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--lean-candidate", type=Path)
    audit.add_argument(
        "--allow-test-fixture", action="store_true", help=argparse.SUPPRESS
    )
    audit.add_argument(
        "--allow-development-key", action="store_true", help=argparse.SUPPRESS
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "assemble":
            print(
                canonical_json_bytes(assemble_handoff(args)).decode("utf-8")
            )
            return 0
        if args.command == "index":
            value = build_child_index(args.handoff_root)
            _write_exclusive(args.output, canonical_json_bytes(value))
            print(
                canonical_json_bytes(
                    {
                        "accepted": False,
                        "child_count": len(value["entries"]),
                        "classification": (
                            "canonical_child_index_not_execution_evidence"
                        ),
                        "index_sha256": hash_file_once(args.output)[0],
                    }
                ).decode("utf-8")
            )
            return 0
        if args.command == "prepare":
            print(
                canonical_json_bytes(prepare_handoff(args)).decode("utf-8")
            )
            return 0
        candidate, pins = _validate_terminal(args)
        raw = canonical_json_bytes(candidate)
        _write_exclusive(args.output, raw)
        if args.lean_candidate is not None:
            _write_exclusive(
                args.lean_candidate,
                render_lean_pin_candidate(pins).encode("utf-8"),
            )
        print(
            "historical Goldbach post-run candidate generated; production "
            "registration remains unconfigured "
            f"(bundle_sha256={pins['bundle_sha256']})"
        )
        return 0
    except (
        ArchiveError,
        CampaignIOError,
        GoldbachBuildAdmissionError,
        HistoricalGoldbachRegistrationError,
        HistoricalGoldbachTerminalError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"historical Goldbach registration error: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
