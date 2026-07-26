#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Collect certificate-capable Azure evidence from a measured-run package.

Unlike ``collect_azure_ncc_evidence.py``'s legacy diagnostic path, this adapter
never resets or extends PCR23.  It consumes the quote and the ordered
zero->start->result transcript already produced by the challenge-first runner,
then obtains post-run Azure MAA and (for H100) NVIDIA evidence for the same
result binding.  It also emits a canonical run bundle whose statement must be
identical to the measured statement.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_path in (REPOSITORY_ROOT / "tools", REPOSITORY_ROOT / "azure", Path(__file__).parent):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from collect_azure_ncc_evidence import (  # noqa: E402
    BACKENDS,
    DEFAULT_MAA_COMMAND,
    DEFAULT_POLICY,
    EvidenceError,
    MAA_API_VERSION,
    MAA_SEVSNP_PATH,
    TPM_PCR_SELECTION,
    _artifact_inventory,
    _collect_gpu,
    _collect_maa,
    _parse_canonical_json,
    _require_gpu_state,
    _which,
    canonical_json_bytes,
    load_challenge,
    require_current_challenge_window,
    sha256_file,
    validate_maa_attestation_url,
)
from create_run_bundle import (  # noqa: E402
    BundleError,
    create_bundle,
    load_profile,
    write_bundle,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from verify_measured_runner_transcript import (  # noqa: E402
    TranscriptError,
    verify as verify_transcript,
)
import verify_run_bundle  # noqa: E402


KIND = "gpu_prover_azure_challenge_first_measured_evidence"
SCHEMA_VERSION = 1
COLLECTION_PROTOCOL = "challenge_first_pcr23_zero_start_result_v1"


class MeasuredEvidenceError(RuntimeError):
    pass


def _copy_regular(source: Path, destination: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise MeasuredEvidenceError("measured artifact copying requires O_NOFOLLOW")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_descriptor = -1
    destination_descriptor = -1
    try:
        source_descriptor = os.open(
            source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        before = os.fstat(source_descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise MeasuredEvidenceError(
                f"required measured-run artifact is not one unlinked regular file: {source}"
            )
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o400,
        )
        with os.fdopen(os.dup(source_descriptor), "rb") as input_stream:
            while block := input_stream.read(1024 * 1024):
                view = memoryview(block)
                while view:
                    count = os.write(destination_descriptor, view)
                    view = view[count:]
        after = os.fstat(source_descriptor)
        stable_fields = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_uid,
            value.st_gid,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if stable_fields(before) != stable_fields(after):
            raise MeasuredEvidenceError(
                f"required measured-run artifact changed while copying: {source}"
            )
        os.fsync(destination_descriptor)
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise MeasuredEvidenceError(
            f"cannot copy required measured-run artifact {source}: {error}"
        ) from error
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        if source_descriptor >= 0:
            os.close(source_descriptor)


def _load_canonical(path: Path, what: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = _parse_canonical_json(raw, what)
    except (EvidenceError, OSError) as error:
        raise MeasuredEvidenceError(f"cannot load {what}: {error}") from error
    if not isinstance(value, dict) or raw not in (canonical_json_bytes(value), canonical_json_bytes(value) + b"\n"):
        raise MeasuredEvidenceError(f"{what} is not a canonical JSON object")
    return value


def _quote_evidence(stage: Path, transcript: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pcr = transcript["pcr23"]
    quote = transcript["quote"]
    quote_evidence = {
        "ak_certificate_sha256": sha256_file(stage / "vtpm_ak_cert.bin")[0],
        "ak_public_sha256": sha256_file(stage / "vtpm_ak.pem")[0],
        "event_log_sha256": sha256_file(stage / "tcg_event_log.bin")[0],
        "kind": "gpu_prover_vtpm_ordered_quote_evidence",
        "pcr_selection": TPM_PCR_SELECTION,
        "pcr23_after_sha256": sha256_file(stage / "pcr23.after.bin")[0],
        "pcr23_after_start_sha256": sha256_file(stage / "pcr23.after-start.bin")[0],
        "pcr23_after_start_value_hex": pcr["after_start_hex"],
        "pcr23_after_value_hex": pcr["after_result_hex"],
        "pcr23_before_sha256": sha256_file(stage / "pcr23.before.bin")[0],
        "pcr23_before_value_hex": pcr["initial_hex"],
        "pcrs_sha256": sha256_file(stage / "tpm_quote.pcrs")[0],
        "qualifying_data_sha256": quote["qualifying_data_sha256"],
        "quote_message_sha256": sha256_file(stage / "tpm_quote.msg")[0],
        "quote_signature_sha256": sha256_file(stage / "tpm_quote.sig")[0],
        "schema_version": 1,
    }
    path = stage / "tpm_quote_evidence.json"
    path.write_bytes(canonical_json_bytes(quote_evidence))
    os.chmod(path, 0o400)
    tpm = {
        "ak_handle": "0x81000003",
        "azure_ak_chain_verified_by_collector": False,
        "collection_protocol": COLLECTION_PROTOCOL,
        "local_checkquote_passed": True,
        "pcr23_after_start_hex": pcr["after_start_hex"],
        "pcr23_final_hex": pcr["after_result_hex"],
        "pcr23_initial_hex": pcr["initial_hex"],
        "pcr_selection": TPM_PCR_SELECTION,
        "quote_evidence_sha256": sha256_file(path)[0],
        "quote_qualifying_data": quote["qualifying_data_sha256"],
        "runner_transcript_sha256": sha256_file(stage / "runner-transcript.json")[0],
    }
    return quote_evidence, tpm


def _make_run_bundle(
    bundle_root: Path,
    evidence_root: Path,
    backend: str,
) -> dict[str, Any]:
    job = _load_canonical(bundle_root / "runner/job-spec.json", "packaged measured job")
    statement = _load_canonical(bundle_root / "runner/statement.json", "measured statement")
    target = load_profile(bundle_root / job["target_profile"]["path"], "target")
    trust = load_profile(bundle_root / job["trust_profile"]["path"], "trust")
    build_artifacts = [
        (record["role"], bundle_root / record["path"])
        for record in statement["build_artifacts"]
    ]
    evidence_destination = bundle_root / "certificate-evidence"
    evidence_destination.mkdir(mode=0o700)
    if backend == "azure_sevsnp_cpu":
        hardware_source = evidence_root / "maa_token.jwt"
        hardware_destination = evidence_destination / "maa_token.jwt"
        evidence_format = "azure_attestation_sevsnp_jwt"
    else:
        hardware_source = evidence_root / "evidence-manifest.json"
        hardware_destination = evidence_destination / "evidence-manifest.json"
        evidence_format = "azure_ncc_sevsnp_vtpm_nvidia_cc_evidence_v1"
    _copy_regular(hardware_source, hardware_destination)
    bundle = create_bundle(
        root=bundle_root,
        target_profile=target,
        trust_profile=trust,
        algorithm_id=statement["algorithm"]["algorithm_id"],
        algorithm_definition_sha256=statement["algorithm"]["definition_sha256"],
        input_path=bundle_root / statement["input_artifact"]["path"],
        parameters=statement["parameters"]["value"],
        domain_coverage=statement["domain_coverage"]["value"],
        output_path=bundle_root / statement["output_artifact"]["path"],
        nonce=statement["nonce"],
        build_artifacts=build_artifacts,
        execution_environment=statement["execution_environment"]["value"],
        completion=statement["completion"],
        hardware_attestation_path=hardware_destination,
        hardware_attestation_format=evidence_format,
    )
    if bundle["statement"] != statement:
        raise MeasuredEvidenceError("run-bundle reconstruction changed the measured statement")
    write_bundle(bundle, bundle_root / "run-bundle.json")
    checked = verify_run_bundle.verify_bundle(bundle, artifact_root=bundle_root)
    if checked["statement_sha256"] != bundle["statement_sha256"] or not checked[
        "artifacts_verified"
    ]:
        raise MeasuredEvidenceError("run-bundle integrity verifier rejected the finalized bundle")
    return bundle


def collect(args: argparse.Namespace) -> dict[str, Any]:
    if args.output_dir.exists():
        raise MeasuredEvidenceError(f"output directory already exists: {args.output_dir}")
    challenge = load_challenge(args.challenge)
    validate_maa_attestation_url(args.maa_attestation_url)
    local_verification = verify_transcript(
        args.run_package,
        args.challenge,
        args.runner_appraisal_policy,
        allow_development_policy=args.allow_development_policy,
    )
    if local_verification["claims"]["hardware_quote_authenticated"] is not False:
        raise MeasuredEvidenceError("transcript component unexpectedly overclaimed hardware appraisal")
    transcript = _load_canonical(
        args.run_package / "runner/transcript.json", "measured runner transcript"
    )
    if transcript["backend"] != args.backend or transcript["challenge"] != challenge:
        raise MeasuredEvidenceError("measured transcript backend/challenge mismatch")
    binding = transcript["bindings"]["result_binding_sha256"]
    statement_sha256 = transcript["bindings"]["statement_sha256"]
    if args.dry_run:
        return {
            "accepted": False,
            "backend": args.backend,
            "classification": "challenge_first_measured_evidence_dry_run",
            "collection_protocol": COLLECTION_PROTOCOL,
            "result_binding_sha256": binding,
            "statement_sha256": statement_sha256,
        }
    if os.geteuid() != 0:
        raise MeasuredEvidenceError("Azure measured-evidence collection requires root device access")
    args.output_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{args.output_dir.name}.collecting-", dir=args.output_dir.parent))
    os.chmod(stage, 0o700)
    evidence = stage / "evidence"
    bundle_root = stage / "bundle-root"
    evidence.mkdir(mode=0o700)
    try:
        archive_path = evidence / "measured-run-package.tar"
        create_archive(args.run_package, archive_path)
        extract_archive(archive_path, bundle_root)
        # Reverify the extracted snapshot, not the caller-controlled live tree.
        policy_copy = evidence / "runner-appraisal-policy.json"
        _copy_regular(args.runner_appraisal_policy, policy_copy)
        verify_transcript(
            bundle_root,
            args.challenge,
            policy_copy,
            allow_development_policy=args.allow_development_policy,
        )
        _copy_regular(bundle_root / "runner/transcript.json", evidence / "runner-transcript.json")
        _copy_regular(bundle_root / "runner/job-spec.json", evidence / "runner-job-spec.json")
        _copy_regular(bundle_root / "runner/statement.json", evidence / "runner-statement.json")
        _copy_regular(bundle_root / "output/work-trace.json", evidence / "runner-work-trace.json")
        for destination, source in {
            "azure_hcl_report.bin": "runner/azure_hcl_report.bin",
            "azure_hcl_runtime_data.bin": "runner/azure_hcl_runtime_data.bin",
            "pcr23.after-start.bin": "runner/pcr23.after-start.bin",
            "pcr23.after.bin": "runner/pcr23.after-result.bin",
            "pcr23.before.bin": "runner/pcr23.initial.bin",
            "tcg_event_log.bin": "runner/tcg_event_log.bin",
            "tpm_quote.msg": "runner/tpm_quote.msg",
            "tpm_quote.pcrs": "runner/tpm_quote.pcrs",
            "tpm_quote.sig": "runner/tpm_quote.sig",
            "vtpm_ak.pem": "runner/vtpm_ak.pem",
            "vtpm_ak_cert.bin": "runner/vtpm_ak_cert.bin",
        }.items():
            _copy_regular(bundle_root / source, evidence / destination)
        _quote_evidence(evidence, transcript)

        is_h100 = args.backend == "azure_ncc40ads_h100_v5"
        maa_command = _which(args.maa_command)
        gpu_state = None
        gpu = None
        if is_h100:
            nvidia_smi = _which(args.nvidia_smi)
            nvattest = _which(args.nvattest)
            gpu_state = _require_gpu_state(evidence, nvidia_smi)
            gpu = _collect_gpu(
                evidence,
                nvattest,
                args.policy,
                binding,
                args.gpu_verifier,
                args.nras_url,
            )
        maa = _collect_maa(
            evidence,
            maa_command,
            challenge["nonce"],
            statement_sha256,
            binding,
            args.maa_attestation_url,
        )
        require_current_challenge_window(challenge)
        quote_evidence = _load_canonical(evidence / "tpm_quote_evidence.json", "quote evidence")
        tpm = {
            "ak_handle": "0x81000003",
            "azure_ak_chain_verified_by_collector": False,
            "collection_protocol": COLLECTION_PROTOCOL,
            "local_checkquote_passed": True,
            "pcr23_after_start_hex": transcript["pcr23"]["after_start_hex"],
            "pcr23_final_hex": transcript["pcr23"]["after_result_hex"],
            "pcr23_initial_hex": transcript["pcr23"]["initial_hex"],
            "pcr_selection": TPM_PCR_SELECTION,
            "quote_evidence_sha256": sha256_file(evidence / "tpm_quote_evidence.json")[0],
            "quote_qualifying_data": binding,
            "runner_transcript_sha256": sha256_file(evidence / "runner-transcript.json")[0],
        }
        runner_record = {
            "appraisal_policy_sha256": sha256_file(policy_copy)[0],
            "archive_sha256": sha256_file(archive_path)[0],
            "job_spec_sha256": transcript["bindings"]["job_spec_sha256"],
            "local_transcript_check_only": True,
            "protocol": COLLECTION_PROTOCOL,
            "start_binding_sha256": transcript["bindings"]["start_binding_sha256"],
            "statement_sha256": statement_sha256,
            "transcript_sha256": sha256_file(evidence / "runner-transcript.json")[0],
        }
        manifest = {
            "artifacts": _artifact_inventory(evidence),
            "backend": args.backend,
            "binding": {
                "protocol": "sparkinterval.trusted-compute.result-binding.v1",
                "post_run_binding_nonce": binding,
                "start_challenge": challenge["nonce"],
                "statement_sha256": statement_sha256,
            },
            "challenge": challenge,
            "collection_protocol": COLLECTION_PROTOCOL,
            "collection_time_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gpu": gpu,
            "gpu_state": gpu_state,
            "kind": KIND,
            "maa": maa,
            "runner": runner_record,
            "schema_version": SCHEMA_VERSION,
            "status": "measured_evidence_collected_pending_independent_verification",
            "tpm": tpm,
            "trust_boundary": {
                "algorithm_execution_proven_by_collector": False,
                "maa_jws_signature_verified_by_collector": False,
                "nvidia_eat_retained": is_h100,
                "signed_acceptance_certificate_issued": False,
            },
        }
        manifest_path = evidence / "evidence-manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        os.chmod(manifest_path, 0o400)
        bundle = _make_run_bundle(bundle_root, evidence, args.backend)
        os.replace(stage, args.output_dir)
        return {
            "accepted": False,
            "backend": args.backend,
            "bundle": str(args.output_dir / "bundle-root/run-bundle.json"),
            "bundle_sha256": bundle["bundle_sha256"],
            "classification": "certificate_package_pending_independent_hardware_appraisal",
            "collection_protocol": COLLECTION_PROTOCOL,
            "evidence_pack": str(args.output_dir / "evidence"),
            "result_binding_sha256": binding,
            "statement_sha256": statement_sha256,
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--run-package", type=Path, required=True)
    parser.add_argument("--runner-appraisal-policy", type=Path, required=True)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maa-command", type=Path, default=DEFAULT_MAA_COMMAND)
    parser.add_argument(
        "--maa-attestation-url",
        required=True,
        help=f"exact HTTPS {MAA_SEVSNP_PATH}?api-version={MAA_API_VERSION} endpoint",
    )
    parser.add_argument("--nvattest", default="/usr/local/bin/nvattest")
    parser.add_argument("--nvidia-smi", default="/usr/bin/nvidia-smi")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--gpu-verifier", choices=("local", "remote"), default="remote")
    parser.add_argument("--nras-url", default="https://nras.attestation.nvidia.com")
    parser.add_argument("--allow-development-policy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = collect(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        ArchiveError,
        BundleError,
        EvidenceError,
        MeasuredEvidenceError,
        OSError,
        TranscriptError,
        ValueError,
        verify_run_bundle.VerificationError,
    ) as error:
        print(
            json.dumps(
                {"accepted": False, "classification": "measured_evidence_collection_failed_closed", "error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
