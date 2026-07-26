#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the closed Sqrt218 verifier for the existing Azure CPU runner.

The default runner policy is deliberately development-only.  A caller may
provide an independently reviewed production runner policy, but this builder
does not invent an appraisal policy, Azure identity, signing key, or receipt.
Emitting the production-sized full-recomputation job is also opt-in: ordinary
materialization without a verified corpus fails before creating an artifact
tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "tools", REPOSITORY_ROOT / "azure"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from create_run_bundle import (  # noqa: E402
    canonical_json_bytes,
    canonical_sha256,
    load_profile,
    parse_json_bytes,
)
from measured_runner import _closure_manifest, validate_job_spec  # noqa: E402
from tg_verifier.campaign_io import read_bytes_once  # noqa: E402
from tg_verifier.numeric_corpus import (  # noqa: E402
    MAX_CONTROL_BYTES,
    NumericCorpusError,
    parse_manifest_bytes,
    parse_pin_bytes,
    verify_snapshot,
)
from tg_verifier.sqrt218_contract import (  # noqa: E402
    ALGORITHM_DEFINITION,
    ALGORITHM_ID,
    BOUND,
    BOUND_64_KAT,
    LOG_DEPTH,
    OPERATIONAL_STATE_MACHINE,
    RECIPROCAL_SCALE,
    SCALE,
    TRACE_DEFINITION,
    recomputation_run_input_bytes,
)
from tg_verifier.sqrt218_numeric_corpus import (  # noqa: E402
    Sqrt218CorpusError,
    require_sqrt218_manifest,
)


DEVELOPMENT_POLICY = (
    REPOSITORY_ROOT
    / "profiles/measured_runner/development_challenge_first_v1.json"
)
TARGET_PROFILE = REPOSITORY_ROOT / "profiles/targets/azure_sevsnp_cpu.json"
TRUST_PROFILE = (
    REPOSITORY_ROOT / "profiles/trust/azure_sevsnp_hardware_attested.json"
)
RUNTIME_SOURCES = (
    "tools/tg_sqrt218_azure_measured_workload.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/numeric_corpus.py",
    "tg_verifier/sqrt218_contract.py",
    "tg_verifier/sqrt218_certificate.py",
    "tg_verifier/sqrt218_certificate_verifier.py",
    "tg_verifier/sqrt218_numeric_corpus.py",
)
MINIMAL_PACKAGE = (
    b"# Generated minimal runtime package for the measured Sqrt218 job.\n"
    b"# The exact execution closure is in provenance/source-manifest.json.\n"
)
PARAMETERS = {
    "independent_replay": True,
    "log_depth": LOG_DEPTH,
    "log_seed_count": 30,
    "log_scale": SCALE,
    "reciprocal_scale": RECIPROCAL_SCALE,
}
DOMAIN = {
    "claim": "helfgott-2-18-finite-head-and-anchor",
    "head_lower": 1,
    "head_upper": BOUND,
    "strict": True,
}


class Sqrt218BuildError(RuntimeError):
    """A source, policy, profile, or emitted measured job was not closed."""


def _write(path: Path, raw: bytes, mode: int = 0o400) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise Sqrt218BuildError(f"short write to {path}")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy(source: Path, destination: Path, mode: int) -> None:
    if source.is_symlink() or not source.is_file():
        raise Sqrt218BuildError(
            f"runtime source is not a regular non-symlink file: {source}"
        )
    with source.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if identity(before) != identity(after):
        raise Sqrt218BuildError(f"runtime source changed while read: {source}")
    _write(destination, raw, mode)


def _identity(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _load_runner_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise Sqrt218BuildError(
            f"runner policy is not a regular non-symlink file: {path}"
        )
    raw = path.read_bytes()
    try:
        value = parse_json_bytes(raw, "Sqrt218 runner policy")
    except ValueError as error:
        raise Sqrt218BuildError(str(error)) from error
    canonical = canonical_json_bytes(value)
    if not isinstance(value, dict) or raw not in (canonical, canonical + b"\n"):
        raise Sqrt218BuildError(
            "runner policy must be canonical JSON with at most one final newline"
        )
    required = {
        "classification",
        "kind",
        "policy_id",
        "production_ready",
        "schema_version",
    }
    if (
        not required.issubset(value)
        or value["kind"] != "sparkinterval_measured_runner_policy"
        or value["schema_version"] != 1
        or not isinstance(value["policy_id"], str)
        or not value["policy_id"]
        or value["classification"] not in {"development", "production"}
        or not isinstance(value["production_ready"], bool)
    ):
        raise Sqrt218BuildError("runner policy has an unsupported identity or status")
    if value["classification"] == "production" and value["production_ready"] is not True:
        raise Sqrt218BuildError(
            "a production runner policy must explicitly be production-ready"
        )
    if value["classification"] != "production" and value["production_ready"] is not False:
        raise Sqrt218BuildError(
            "a non-production runner policy cannot be production-ready"
        )
    return value, raw


def _artifact(
    root: Path,
    relative: str,
    *,
    executable: bool,
    role: str,
    statement_role: str | None,
) -> dict[str, Any]:
    digest, size = _identity(root / relative)
    return {
        "executable": executable,
        "path": relative,
        "role": role,
        "sha256": digest,
        "size_bytes": size,
        "statement_role": statement_role,
    }


def _load_corpus(
    pin_path: Path,
    snapshot_root: Path,
) -> tuple[bytes, dict[str, Any], list[tuple[str, bool, str]]]:
    if pin_path.is_symlink() or not pin_path.is_file():
        raise Sqrt218BuildError(
            "numeric-corpus pin must be a regular non-symlink file"
        )
    try:
        pin_raw = read_bytes_once(pin_path, limit=MAX_CONTROL_BYTES)
        pin = parse_pin_bytes(pin_raw, label=str(pin_path))
        manifest_path = snapshot_root / PurePosixPath(
            pin["repository"]["manifest_path"]
        )
        manifest_raw = read_bytes_once(manifest_path, limit=MAX_CONTROL_BYTES)
        manifest = parse_manifest_bytes(
            manifest_raw,
            pin=pin,
            label=str(manifest_path),
        )
        require_sqrt218_manifest(pin, manifest)
        verify_snapshot(snapshot_root, pin, manifest)
    except (NumericCorpusError, Sqrt218CorpusError, OSError, ValueError) as error:
        raise Sqrt218BuildError(
            f"numeric-corpus snapshot is not production-shaped Sqrt218 data: {error}"
        ) from error
    members = [
        (pin["repository"]["manifest_path"], False, "numeric_corpus_manifest")
    ]
    members.extend(
        (record["path"], False, "numeric_corpus_payload")
        for record in manifest["payloads"]
    )
    members.extend(
        (record["path"], record["executable"], "numeric_corpus_source")
        for record in manifest["source_files"]
    )
    return pin_raw, manifest, members


def build(
    output_root: Path,
    *,
    runner_policy_path: Path | None = None,
    numeric_corpus_pin: Path | None = None,
    numeric_corpus_snapshot: Path | None = None,
    allow_full_recomputation_job: bool = False,
) -> dict[str, Any]:
    """Build an immutable source closure and a runner-consumable job spec."""

    if output_root.exists():
        raise Sqrt218BuildError(f"output root already exists: {output_root}")
    policy_source = runner_policy_path or DEVELOPMENT_POLICY
    runner_policy, runner_policy_raw = _load_runner_policy(policy_source)
    if (numeric_corpus_pin is None) != (numeric_corpus_snapshot is None):
        raise Sqrt218BuildError(
            "--numeric-corpus-pin and --numeric-corpus-snapshot must be supplied together"
        )
    corpus: tuple[bytes, dict[str, Any], list[tuple[str, bool, str]]] | None = None
    if numeric_corpus_pin is not None and numeric_corpus_snapshot is not None:
        corpus = _load_corpus(numeric_corpus_pin, numeric_corpus_snapshot)
    if runner_policy["classification"] == "production" and corpus is None:
        raise Sqrt218BuildError(
            "production Sqrt218 materialization requires a reviewed numeric-corpus "
            "pin and its verified snapshot"
        )
    if corpus is None and not allow_full_recomputation_job:
        raise Sqrt218BuildError(
            "full-recomputation Sqrt218 job emission is disabled by default; "
            "pass --emit-full-recomputation-job to materialize the cloud-only "
            "development job"
        )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.building-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    try:
        for relative in RUNTIME_SOURCES:
            mode = 0o500 if relative.startswith("tools/") else 0o400
            _copy(REPOSITORY_ROOT / relative, stage / relative, mode)
        _write(stage / "tg_verifier/__init__.py", MINIMAL_PACKAGE)
        snapshot_members: list[tuple[str, bool, str]] = []
        if corpus is None:
            input_relative = "input/sqrt218-recomputation.json"
            input_raw = recomputation_run_input_bytes()
            input_mode = "full_recomputation"
        else:
            input_relative = "input/sqrt218-corpus-pin.json"
            input_raw, _manifest, snapshot_members = corpus
            input_mode = "verified_numeric_corpus"
            assert numeric_corpus_snapshot is not None
            for relative, executable, _role in snapshot_members:
                _copy(
                    numeric_corpus_snapshot / PurePosixPath(relative),
                    stage / "corpus/snapshot" / PurePosixPath(relative),
                    0o500 if executable else 0o400,
                )
        _write(stage / input_relative, input_raw)
        _write(
            stage / "profiles/target.json",
            canonical_json_bytes(parse_json_bytes(TARGET_PROFILE.read_bytes(), "target profile")),
        )
        _write(
            stage / "profiles/trust.json",
            canonical_json_bytes(parse_json_bytes(TRUST_PROFILE.read_bytes(), "trust profile")),
        )
        _write(stage / "profiles/runner-policy.json", runner_policy_raw)

        source_paths = list(RUNTIME_SOURCES) + ["tg_verifier/__init__.py"]
        source_manifest = {
            "files": [
                {
                    "path": relative,
                    "sha256": _identity(stage / relative)[0],
                    "size_bytes": _identity(stage / relative)[1],
                }
                for relative in source_paths
            ],
            "kind": "sparkinterval_sqrt218_measured_source_manifest",
            "schema_version": 1,
        }
        _write(
            stage / "provenance/source-manifest.json",
            canonical_json_bytes(source_manifest),
        )
        _write(
            stage / "provenance/operational-state-machine.json",
            canonical_json_bytes(OPERATIONAL_STATE_MACHINE),
        )
        _write(
            stage / "provenance/known-answer-tests.json",
            canonical_json_bytes(
                {
                    "kind": "sparkinterval.sqrt218-known-answer-tests.v1",
                    "schema_version": 1,
                    "tests": [BOUND_64_KAT],
                }
            ),
        )
        translation_plan = {
            "architecture": "x86_64_azure_sevsnp_cpu",
            "binary_refinement_proved": False,
            "execution_runtime": (
                "CPython and standard library from the independently appraised "
                "content-addressed guest image"
            ),
            "kind": "sparkinterval.sqrt218-translation-validation-plan.v1",
            "known_answer_tests_sha256": _identity(
                stage / "provenance/known-answer-tests.json"
            )[0],
            "operational_state_machine_sha256": _identity(
                stage / "provenance/operational-state-machine.json"
            )[0],
            "schema_version": 1,
            "source_manifest_sha256": _identity(
                stage / "provenance/source-manifest.json"
            )[0],
            "source_to_operational_ir_proved": False,
            "status": (
                "deterministic KAT and full independent replay are available; "
                "formal Python-to-IR and x86-binary refinement remain absent"
            ),
        }
        _write(
            stage / "provenance/translation-validation-plan.json",
            canonical_json_bytes(translation_plan),
        )

        files = [
            _artifact(
                stage,
                "tools/tg_sqrt218_azure_measured_workload.py",
                executable=True,
                role="sqrt218_measured_workload",
                statement_role="host_executable",
            ),
            _artifact(
                stage,
                "tg_verifier/__init__.py",
                executable=False,
                role="minimal_runtime_package",
                statement_role=None,
            ),
            _artifact(
                stage,
                "tg_verifier/campaign_io.py",
                executable=False,
                role="canonical_runtime_io",
                statement_role="runtime_dependency",
            ),
            _artifact(
                stage,
                "tg_verifier/numeric_corpus.py",
                executable=False,
                role="numeric_corpus_verifier",
                statement_role="corpus_verifier",
            ),
            _artifact(
                stage,
                "tg_verifier/sqrt218_contract.py",
                executable=False,
                role="sqrt218_wire_contract",
                statement_role="protocol_contract",
            ),
            _artifact(
                stage,
                "tg_verifier/sqrt218_certificate.py",
                executable=False,
                role="sqrt218_certificate_producer",
                statement_role="certificate_producer",
            ),
            _artifact(
                stage,
                "tg_verifier/sqrt218_certificate_verifier.py",
                executable=False,
                role="sqrt218_independent_verifier",
                statement_role="certificate_verifier",
            ),
            _artifact(
                stage,
                "tg_verifier/sqrt218_numeric_corpus.py",
                executable=False,
                role="sqrt218_corpus_adapter",
                statement_role="corpus_adapter",
            ),
            _artifact(
                stage,
                "provenance/source-manifest.json",
                executable=False,
                role="sqrt218_source_manifest",
                statement_role="source_tree",
            ),
            _artifact(
                stage,
                "provenance/operational-state-machine.json",
                executable=False,
                role="sqrt218_operational_ir",
                statement_role="operational_state_machine",
            ),
            _artifact(
                stage,
                "provenance/known-answer-tests.json",
                executable=False,
                role="sqrt218_known_answer_tests",
                statement_role="known_answer_tests",
            ),
            _artifact(
                stage,
                "provenance/translation-validation-plan.json",
                executable=False,
                role="sqrt218_translation_validation",
                statement_role="translation_validation_plan",
            ),
        ]
        target = load_profile(stage / "profiles/target.json", "target")
        trust = load_profile(stage / "profiles/trust.json", "trust")
        target_hash = canonical_sha256(target)
        trust_hash = canonical_sha256(trust)
        runner_hash = hashlib.sha256(runner_policy_raw).hexdigest()
        input_hash, input_size = _identity(stage / input_relative)
        command = [
            "tools/tg_sqrt218_azure_measured_workload.py",
            "run",
            "--cloud-production",
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
            "--certificate",
            "work/sqrt218-certificate.json",
            "--report",
            "work/sqrt218-verification.json",
        ]
        verifier = command.copy()
        verifier[1] = "verify-trace"
        if corpus is not None:
            command.extend(
                ["--numeric-corpus-snapshot", "corpus/snapshot"]
            )
            verifier.extend(
                ["--numeric-corpus-snapshot", "corpus/snapshot"]
            )
        for relative, executable, role in snapshot_members:
            files.append(
                _artifact(
                    stage,
                    f"corpus/snapshot/{relative}",
                    executable=executable,
                    role=role,
                    statement_role=role,
                )
            )
        # The corpus members are part of the executable closure, so recompute
        # the manifest hash only after selecting the exact input mode.
        closure_hash = canonical_sha256(_closure_manifest(files))
        job = {
            "algorithm": {
                "algorithm_id": ALGORITHM_ID,
                "canonical_definition": ALGORITHM_DEFINITION,
                "definition_sha256": hashlib.sha256(
                    ALGORITHM_DEFINITION.encode("utf-8")
                ).hexdigest(),
            },
            "artifact_closure": {
                "closure_kind": "content_addressed_image_source_reviewed_v1",
                "files": files,
                "manifest_sha256": closure_hash,
            },
            "backend": "azure_sevsnp_cpu",
            "command": {
                "argv": command,
                "cwd": ".",
                "environment": {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                },
                "timeout_seconds": 21_600,
            },
            "domain_coverage": {
                "canonical_sha256": canonical_sha256(DOMAIN),
                "value": DOMAIN,
            },
            "gpu_pre_run_gate": None,
            "input_artifact": {
                "path": input_relative,
                "release_argv": None,
                "release_mode": "prepositioned_public_after_start",
                "sha256": input_hash,
                "size_bytes": input_size,
            },
            "job_id": "ternary-goldbach-sqrt218-finite-cpu-v1",
            "kind": "sparkinterval_measured_job",
            "output_contract": {
                "expected_output_count": 1,
                "format": "opaque_bytes_v1",
                "maximum_bytes": 4,
                "path": "output/result.txt",
            },
            "parameters": {
                "canonical_sha256": canonical_sha256(PARAMETERS),
                "value": PARAMETERS,
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
                "expected_iterations": BOUND,
                "format": "challenge_sha256_chain_json_v1",
                "path": "output/work-trace.json",
                "required": True,
                "trace_algorithm_definition": TRACE_DEFINITION,
                "trace_algorithm_sha256": hashlib.sha256(
                    TRACE_DEFINITION.encode("utf-8")
                ).hexdigest(),
                "verification_mode": "pinned_external_trace_verifier_v1",
                "verifier_argv": verifier,
            },
        }
        validate_job_spec(job)
        job_raw = canonical_json_bytes(job)
        _write(stage / "job.json", job_raw)
        job_hash = hashlib.sha256(job_raw).hexdigest()

        if runner_policy["classification"] == "development":
            appraisal = {
                "allowed_backends": ["azure_sevsnp_cpu"],
                "allowed_job_spec_sha256": [job_hash],
                "allowed_runner_policy_sha256": [runner_hash],
                "allowed_target_profile_sha256": [target_hash],
                "allowed_trust_profile_sha256": [trust_hash],
                "classification": "development",
                "kind": "sparkinterval_measured_runner_appraisal_policy",
                "policy_id": "sparkinterval.sqrt218.development-appraisal.v1",
                "require_authenticated_hardware_quote": True,
                "required_composite_appraiser_claims": [
                    "measured_runner_policy_valid",
                    "result_artifact_bound_to_execution",
                ],
                "schema_version": 1,
            }
            _write(
                stage / "appraisal-policy.json",
                canonical_json_bytes(appraisal),
            )

        os.replace(stage, output_root)
        return {
            "accepted": False,
            "artifact_root": str(output_root),
            "classification": (
                "development_job_built"
                if runner_policy["classification"] == "development"
                else "production_policy_job_built_pending_execution_and_appraisal"
            ),
            "input_mode": input_mode,
            "job_spec": str(output_root / "job.json"),
            "job_spec_sha256": job_hash,
            "lean_registry_admission": False,
            "production_receipt_present": False,
            "runner_policy_classification": runner_policy["classification"],
            "target": "azure_sevsnp_cpu",
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--runner-policy",
        type=Path,
        help=(
            "Canonical reviewed runner policy; omission selects the repository's "
            "non-authorizing development policy."
        ),
    )
    parser.add_argument(
        "--numeric-corpus-pin",
        type=Path,
        help="Canonical reviewed Sqrt218 numeric-corpus pin.",
    )
    parser.add_argument(
        "--numeric-corpus-snapshot",
        type=Path,
        help="Previously resolved and verified read-only corpus snapshot.",
    )
    parser.add_argument(
        "--emit-full-recomputation-job",
        action="store_true",
        help=(
            "Explicitly emit the cloud-only bound-2,000,000 development job "
            "when no numeric corpus is supplied. This materializes but does "
            "not execute or authorize the computation."
        ),
    )
    args = parser.parse_args(argv)
    try:
        report = build(
            args.output_root,
            runner_policy_path=args.runner_policy,
            numeric_corpus_pin=args.numeric_corpus_pin,
            numeric_corpus_snapshot=args.numeric_corpus_snapshot,
            allow_full_recomputation_job=args.emit_full_recomputation_job,
        )
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, Sqrt218BuildError, ValueError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "sqrt218_measured_job_build_failed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
