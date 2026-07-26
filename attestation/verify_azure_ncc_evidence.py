#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independently appraise an Azure SEV-SNP/vTPM or NCC H100 evidence pack.

This verifier is the executable contract consumed by
``tools/trusted_compute_receipt.py``.  It validates the complete collected
artifact closure and invokes hash-pinned cryptographic appraisers.  It never
accepts a stored boolean or the collector's local check result as evidence.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence


PINNED_COLLECTOR_MODULE_SHA256 = (
    "f506815d376f312593ae3f288a173ff37ff3bfdecc677937e4963cb223c6e454"
)
_collector_module_path = Path(__file__).resolve().with_name(
    "collect_azure_ncc_evidence.py"
)
try:
    _collector_module_bytes = _collector_module_path.read_bytes()
except OSError as error:
    raise RuntimeError(f"cannot read pinned Azure evidence collector module: {error}") from error
if hashlib.sha256(_collector_module_bytes).hexdigest() != PINNED_COLLECTOR_MODULE_SHA256:
    raise RuntimeError("Azure evidence collector module differs from verifier source pin")

PINNED_MEASURED_MODULES = {
    "measured_run_archive.py": "9d237540238b5aa3ed8b07c657671f1c51a6e05b676b2411a2488d5c9857423f",
    "verify_measured_runner_transcript.py": "0f8413c469193d196df139cba8af1a677d46f030d04d7c0745c949ef2fcd15b0",
    "measured_runner.py": "293b54e11d2f5b904ef8cd97b6eabdb569682c1d3e701de1ce1220178234ce57",
    "create_run_bundle.py": "efb00c569b13f97a42e663aa8591bf53a30b1995cabb65559fa327ec812d611a",
    "tg_verifier/campaign_io.py": "43d1fc2dbab398e906755a03d7abcc3fec514a73eeab4ab69871e6d40c566413",
    "tg_verifier/goldbach_gpu_campaign.py": "5d9f92228f6aa58cc7ab9975b988200dbda1f932294f4dcb4983b7634aea20c2",
    "tg_verifier/goldbach_build_admission.py": "f0435eeed819ffcae72769afb4867fa51fb4f9e7db1b59e624ddc7fcd13b6678",
}
_module_repository = Path(__file__).resolve().parents[1]
_module_source_candidates = {
    "measured_run_archive.py": _module_repository / "attestation/measured_run_archive.py",
    "verify_measured_runner_transcript.py": (
        _module_repository / "attestation/verify_measured_runner_transcript.py"
    ),
    "measured_runner.py": _module_repository / "azure/measured_runner.py",
    "create_run_bundle.py": _module_repository / "tools/create_run_bundle.py",
    "tg_verifier/campaign_io.py": (
        _module_repository / "tg_verifier/campaign_io.py"
    ),
    "tg_verifier/goldbach_gpu_campaign.py": (
        _module_repository / "tg_verifier/goldbach_gpu_campaign.py"
    ),
    "tg_verifier/goldbach_build_admission.py": (
        _module_repository / "tg_verifier/goldbach_build_admission.py"
    ),
}
for _module_name, _expected_module_digest in PINNED_MEASURED_MODULES.items():
    # Receipt issuance flattens the authenticated closure beside this entry
    # point; repository execution uses the normal source-tree location.
    _flat_module = Path(__file__).resolve().parent / _module_name
    _module_path = (
        _flat_module if _flat_module.is_file() else _module_source_candidates[_module_name]
    )
    try:
        _module_bytes = _module_path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"cannot read pinned measured module {_module_name}: {error}") from error
    if hashlib.sha256(_module_bytes).hexdigest() != _expected_module_digest:
        raise RuntimeError(f"measured module {_module_name} differs from verifier source pin")

from collect_azure_ncc_evidence import (
    BACKENDS,
    CAMPAIGN_RE,
    CHALLENGE_KIND,
    EvidenceError,
    HEX256_RE,
    KIND as EVIDENCE_KIND,
    MAX_CHALLENGE_TTL_SECONDS,
    MAA_PROVIDER,
    TPM_PCR_SELECTION,
    _parse_canonical_json,
    canonical_json_bytes,
    derive_binding_nonce,
    sha256_file,
    validate_maa_attestation_url,
)

_repository_root = Path(__file__).resolve().parents[1]
for _local_import_root in (
    Path(__file__).resolve().parent,
    _repository_root / "azure",
    _repository_root / "tools",
):
    if str(_local_import_root) not in sys.path:
        sys.path.insert(0, str(_local_import_root))

from measured_run_archive import ArchiveError, extract_archive  # noqa: E402
from verify_measured_runner_transcript import (  # noqa: E402
    TranscriptError,
    verify as verify_measured_runner_transcript,
)


SCHEMA_VERSION = 1
APPRAISAL_KIND = "sparkinterval_evidence_appraisal"
POLICY_KIND = "sparkinterval_azure_evidence_appraisal_policy"
AZURE_APPRAISAL_KIND = "sparkinterval_azure_sevsnp_vtpm_appraisal"
NOT_APPLICABLE_DIGEST = hashlib.sha256(
    b"sparkinterval.trusted-compute.not-applicable.v1"
).hexdigest()

OUTPUT_KEYS = {
    "schema_version",
    "kind",
    "accepted",
    "backend",
    "start_challenge_sha256",
    "result_binding_sha256",
    "policy_sha256",
    "evidence_hashes",
    "appraised_at_utc",
    "not_before_utc",
    "not_after_utc",
}
EVIDENCE_HASH_KEYS = {
    "platform_evidence_sha256",
    "azure_maa_token_sha256",
    "amd_snp_report_sha256",
    "tpm_quote_sha256",
    "tpm_event_log_sha256",
    "nvidia_eat_sha256",
    "nvidia_evidence_sha256",
}
LEGACY_MANIFEST_KEYS = {
    "artifacts",
    "backend",
    "binding",
    "challenge",
    "collection_time_utc",
    "gpu",
    "gpu_state",
    "kind",
    "maa",
    "schema_version",
    "status",
    "tpm",
    "trust_boundary",
}
MEASURED_MANIFEST_KEYS = LEGACY_MANIFEST_KEYS | {"collection_protocol", "runner"}
MANIFEST_KEYS = LEGACY_MANIFEST_KEYS
MEASURED_EVIDENCE_KIND = "gpu_prover_azure_challenge_first_measured_evidence"
MEASURED_COLLECTION_PROTOCOL = "challenge_first_pcr23_zero_start_result_v1"
POLICY_KEYS = {
    "allowed_backends",
    "azure_appraiser",
    "kind",
    "nvidia_appraiser",
    "schema_version",
}
PINNED_APPRAISER_POLICY_KEYS = {
    "executable_path",
    "executable_sha256",
    "policy_path",
    "policy_sha256",
    "timeout_seconds",
}
AZURE_APPRAISER_POLICY_KEYS = PINNED_APPRAISER_POLICY_KEYS | {
    "maa_accepted_audience",
    "maa_accepted_issuer",
    "maa_accepted_provider",
    "maa_attestation_url",
}
NVIDIA_APPRAISER_POLICY_KEYS = PINNED_APPRAISER_POLICY_KEYS | {
    "nras_url",
    "verifier",
}
AZURE_APPRAISAL_KEYS = {
    "accepted",
    "ak_certificate_sha256",
    "ak_public_sha256",
    "binding_sha256",
    "claims",
    "event_log_sha256",
    "hcl_report_sha256",
    "hcl_runtime_data_sha256",
    "kind",
    "maa_attestation_url",
    "maa_audience",
    "maa_issuer",
    "maa_provider",
    "maa_token_sha256",
    "not_after_utc",
    "not_before_utc",
    "pcr_selection",
    "pcr23_after_sha256",
    "pcr23_before_sha256",
    "quote_message_sha256",
    "quote_pcrs_sha256",
    "quote_signature_sha256",
    "runtime_data_sha256",
    "schema_version",
    "snp_report_sha256",
    "user_claims_sha512",
}
AZURE_CLAIM_KEYS = {
    "accelerator_attestation_bound_to_cvm",
    "azure_compliant_cvm",
    "debug_disabled",
    "event_log_replayed",
    "maa_policy_valid",
    "maa_signature_valid",
    "maa_time_valid",
    "measured_runner_policy_valid",
    "pcr23_binding_valid",
    "pre_run_accelerator_gate_valid",
    "quote_ak_chain_valid",
    "quote_signature_valid",
    "runtime_data_bound",
    "result_artifact_bound_to_execution",
    "secure_boot",
    "tee",
    "vtpm",
}
COMMON_REQUIRED_ARTIFACTS = {
    "azure_hcl_report.bin",
    "azure_hcl_runtime_data.bin",
    "maa_config.json",
    "maa_token.jwt",
    "pcr23.after.bin",
    "pcr23.before.bin",
    "report.bin",
    "runtime_data.json",
    "tcg_event_log.bin",
    "tpm_quote.msg",
    "tpm_quote.pcrs",
    "tpm_quote.sig",
    "tpm_quote_evidence.json",
    "vtpm_ak.pem",
    "vtpm_ak_cert.bin",
}
NVIDIA_REQUIRED_ARTIFACTS = {
    "nvidia_detached_eat.json",
    "nvidia_gpu_attestation.json",
    "nvidia_gpu_evidence.json",
}
SHA512_RE = re.compile(r"^[0-9a-f]{128}$")
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
MAA_RECORD_KEYS = {
    "adapter",
    "adapter_sha256",
    "attestation_url",
    "audience",
    "claims_sha512",
    "issuer",
    "jti",
    "provider",
    "token_signature_verified_by_collector",
}
TPM_RECORD_KEYS = {
    "ak_handle",
    "azure_ak_chain_verified_by_collector",
    "local_checkquote_passed",
    "pcr23_extended_with",
    "pcr23_expected_after_hex",
    "pcr23_initial_value_hex",
    "pcr_selection",
    "quote_evidence_sha256",
    "quote_qualifying_data",
    "tool_sha256",
}
MEASURED_TPM_RECORD_KEYS = {
    "ak_handle",
    "azure_ak_chain_verified_by_collector",
    "collection_protocol",
    "local_checkquote_passed",
    "pcr23_after_start_hex",
    "pcr23_final_hex",
    "pcr23_initial_hex",
    "pcr_selection",
    "quote_evidence_sha256",
    "quote_qualifying_data",
    "runner_transcript_sha256",
}
MEASURED_RUNNER_RECORD_KEYS = {
    "appraisal_policy_sha256",
    "archive_sha256",
    "job_spec_sha256",
    "local_transcript_check_only",
    "protocol",
    "start_binding_sha256",
    "statement_sha256",
    "transcript_sha256",
}
PCR23_ZERO = bytes(32)
CHALLENGE_KEYS = {
    "campaign_id",
    "expires_at_utc",
    "issued_at_utc",
    "kind",
    "nonce",
    "schema_version",
    "shard_index",
}
TRUST_BOUNDARY_KEYS = {
    "algorithm_execution_proven_by_collector",
    "maa_jws_signature_verified_by_collector",
    "nvidia_eat_retained",
    "signed_acceptance_certificate_issued",
}


class AppraisalError(RuntimeError):
    """Evidence or a pinned appraiser failed validation."""


def _appraiser_environment(*, include_nvidia_service_key: bool = False) -> dict[str, str]:
    """Return the small, deterministic environment allowed into appraisers."""

    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    if include_nvidia_service_key:
        service_key = os.environ.get("NV_ATTESTATION_SERVICE_KEY")
        if service_key:
            environment["NV_ATTESTATION_SERVICE_KEY"] = service_key
    return environment


def _make_private_directory(path: Path) -> None:
    """Create one owner-only directory and verify the resulting permissions."""

    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    metadata = path.stat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise AppraisalError("private snapshot directory is not mode 0700")


def _snapshot_regular_file(
    source: Path,
    destination: Path,
    what: str,
    *,
    executable: bool = False,
    expected_digest: str | None = None,
    expected_size: int | None = None,
) -> tuple[str, int]:
    """Copy one pathname into the private snapshot through non-following FDs.

    All later consumers receive ``destination``.  A rename or swap of the
    caller-controlled source pathname therefore cannot change the bytes used
    by an appraiser after this function returns.
    """

    if source.is_symlink():
        raise AppraisalError(f"{what} must not be a symlink")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    source_flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        source_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    try:
        source_fd = os.open(source, source_flags)
    except OSError as error:
        raise AppraisalError(f"cannot open {what} for snapshot: {error}") from error
    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        destination_flags |= os.O_CLOEXEC
    mode = 0o500 if executable else 0o400
    digest = hashlib.sha256()
    size = 0
    destination_fd: int | None = None
    try:
        source_metadata = os.fstat(source_fd)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise AppraisalError(f"{what} must be a regular file")
        if executable and not (source_metadata.st_mode & 0o111):
            raise AppraisalError(f"{what} must be executable")
        destination_fd = os.open(destination, destination_flags, mode)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise AppraisalError(f"short write while snapshotting {what}")
                view = view[written:]
        os.fsync(destination_fd)
        os.fchmod(destination_fd, mode)
        destination_metadata = os.fstat(destination_fd)
        if (
            not stat.S_ISREG(destination_metadata.st_mode)
            or destination_metadata.st_nlink != 1
            or stat.S_IMODE(destination_metadata.st_mode) != mode
        ):
            raise AppraisalError(f"private snapshot for {what} is not a fresh regular file")
    except OSError as error:
        raise AppraisalError(f"cannot snapshot {what}: {error}") from error
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)
    actual_digest = digest.hexdigest()
    if expected_digest is not None and actual_digest != expected_digest:
        raise AppraisalError(f"{what} differs from its pinned SHA-256")
    if expected_size is not None and size != expected_size:
        raise AppraisalError(f"{what} differs from its pinned size")
    return actual_digest, size


def _parse_utc(value: Any, what: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise AppraisalError(f"{what} must be canonical UTC to whole seconds")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise AppraisalError(f"{what} is not a real UTC timestamp") from error
    return parsed.replace(tzinfo=dt.timezone.utc)


def _format_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_live_interval(
    not_before: Any, not_after: Any, what: str
) -> tuple[dt.datetime, dt.datetime]:
    start = _parse_utc(not_before, f"{what} not_before")
    end = _parse_utc(not_after, f"{what} not_after")
    now = dt.datetime.now(dt.timezone.utc)
    if not start < end:
        raise AppraisalError(f"{what} validity interval is empty")
    if not start <= now < end:
        raise AppraisalError(f"{what} evidence is not currently valid")
    return start, end


def _exact_object(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise AppraisalError(
            f"{what} has wrong fields "
            f"(missing={sorted(keys - actual)}, unexpected={sorted(actual - keys)})"
        )
    return value


def _require_sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or HEX256_RE.fullmatch(value) is None:
        raise AppraisalError(f"{what} must be a lowercase SHA-256 digest")
    return value


def _safe_artifact_name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise AppraisalError("artifact path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.name != value:
        raise AppraisalError(f"evidence artifact is not a safe top-level path: {value!r}")
    return value


def _load_canonical_with_digest(path: Path, what: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise AppraisalError(f"cannot read {what}: {error}") from error
    try:
        value = _parse_canonical_json(raw, what)
        canonical = canonical_json_bytes(value)
    except Exception as error:
        raise AppraisalError(str(error)) from error
    if raw not in (canonical, canonical + b"\n"):
        raise AppraisalError(f"{what} is not canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _load_canonical(path: Path, what: str) -> Any:
    return _load_canonical_with_digest(path, what)[0]


def _manifest_expected_keys(value: Any) -> set[str]:
    if isinstance(value, dict) and value.get("kind") == MEASURED_EVIDENCE_KIND:
        return MEASURED_MANIFEST_KEYS
    return LEGACY_MANIFEST_KEYS


def _load_expected_challenge(
    path: Path, expected_start: str
) -> tuple[Path, dict[str, Any], str]:
    if path.is_symlink():
        raise AppraisalError("retained off-VM challenge must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise AppraisalError(f"cannot resolve retained off-VM challenge: {error}") from error
    if not resolved.is_file():
        raise AppraisalError("retained off-VM challenge must be a regular file")
    value, digest = _load_canonical_with_digest(
        resolved, "retained off-VM challenge"
    )
    challenge = _exact_object(value, CHALLENGE_KEYS, "retained off-VM challenge")
    if challenge["nonce"] != expected_start:
        raise AppraisalError(
            "retained off-VM challenge nonce differs from the requested challenge"
        )
    return resolved, challenge, digest


def _artifact_path(root: Path, name: str) -> Path:
    candidate = root / name
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise AppraisalError(f"artifact {name!r} escapes or is missing from the pack") from error
    if candidate.is_symlink() or not resolved.is_file():
        raise AppraisalError(f"artifact {name!r} must be a non-symlink regular file")
    return resolved


def _verify_artifact_closure(root: Path, manifest: Mapping[str, Any]) -> dict[str, Path]:
    records = manifest["artifacts"]
    if not isinstance(records, list) or not records:
        raise AppraisalError("manifest artifacts must be a non-empty array")
    paths: dict[str, Path] = {}
    for index, raw_record in enumerate(records):
        record = _exact_object(
            raw_record, {"path", "sha256", "size_bytes"}, f"artifact record {index}"
        )
        name = _safe_artifact_name(record["path"])
        if name in paths:
            raise AppraisalError(f"duplicate evidence artifact: {name}")
        expected_digest = _require_sha256(record["sha256"], f"artifact {name} hash")
        expected_size = record["size_bytes"]
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise AppraisalError(f"artifact {name} has invalid size")
        path = _artifact_path(root, name)
        actual_digest, actual_size = sha256_file(path)
        if (actual_digest, actual_size) != (expected_digest, expected_size):
            raise AppraisalError(f"artifact {name} differs from the manifest")
        paths[name] = path
    actual_names: set[str] = set()
    for child in root.iterdir():
        if child.name == "evidence-manifest.json":
            continue
        if child.is_symlink() or not child.is_file():
            raise AppraisalError(f"unexpected non-regular evidence-pack entry: {child.name}")
        actual_names.add(child.name)
    if actual_names != set(paths):
        raise AppraisalError(
            "evidence artifact closure differs from the manifest "
            f"(missing={sorted(set(paths) - actual_names)}, "
            f"unexpected={sorted(actual_names - set(paths))})"
        )
    return paths


def _snapshot_evidence_pack(source_root: Path, destination_root: Path) -> Path:
    """Create a closed private copy of the manifest-selected evidence bytes."""

    _make_private_directory(destination_root)
    manifest_source = source_root / "evidence-manifest.json"
    manifest_destination = destination_root / "evidence-manifest.json"
    _snapshot_regular_file(
        manifest_source,
        manifest_destination,
        "evidence manifest",
    )
    manifest_value = _load_canonical(manifest_destination, "evidence manifest")
    manifest = _exact_object(
        manifest_value, _manifest_expected_keys(manifest_value), "evidence manifest"
    )
    records = manifest["artifacts"]
    if not isinstance(records, list) or not records:
        raise AppraisalError("manifest artifacts must be a non-empty array")
    names: set[str] = set()
    normalized_records: list[tuple[str, str, int]] = []
    for index, raw_record in enumerate(records):
        record = _exact_object(
            raw_record, {"path", "sha256", "size_bytes"}, f"artifact record {index}"
        )
        name = _safe_artifact_name(record["path"])
        if name == "evidence-manifest.json" or name in names:
            raise AppraisalError(f"duplicate or reserved evidence artifact: {name}")
        names.add(name)
        expected_digest = _require_sha256(record["sha256"], f"artifact {name} hash")
        expected_size = record["size_bytes"]
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise AppraisalError(f"artifact {name} has invalid size")
        normalized_records.append((name, expected_digest, expected_size))
    actual_names: set[str] = set()
    for child in source_root.iterdir():
        if child.name == "evidence-manifest.json":
            continue
        if child.is_symlink() or not child.is_file():
            raise AppraisalError(
                f"unexpected non-regular evidence-pack entry: {child.name}"
            )
        actual_names.add(child.name)
    if actual_names != names:
        raise AppraisalError(
            "evidence artifact closure differs from the manifest "
            f"(missing={sorted(names - actual_names)}, "
            f"unexpected={sorted(actual_names - names)})"
        )
    for name, expected_digest, expected_size in normalized_records:
        actual_digest, actual_size = _snapshot_regular_file(
            source_root / name,
            destination_root / name,
            f"evidence artifact {name}",
        )
        if (actual_digest, actual_size) != (expected_digest, expected_size):
            raise AppraisalError(f"artifact {name} differs from the manifest")
    return destination_root


def _validate_legacy_manifest(
    root: Path,
    backend: str,
    expected_start: str,
    expected_binding: str,
    expected_challenge: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Path], str]:
    manifest_path = _artifact_path(root, "evidence-manifest.json")
    manifest_value, manifest_digest = _load_canonical_with_digest(
        manifest_path, "evidence manifest"
    )
    manifest = _exact_object(
        manifest_value,
        _manifest_expected_keys(manifest_value),
        "evidence manifest",
    )
    if manifest["schema_version"] != 1 or manifest["kind"] != EVIDENCE_KIND:
        raise AppraisalError("unsupported evidence manifest kind/version")
    if manifest["backend"] != backend:
        raise AppraisalError("evidence manifest backend differs from the requested backend")
    if manifest["status"] != "evidence_collected_pending_independent_verification":
        raise AppraisalError("evidence manifest is not pending independent verification")
    binding = _exact_object(
        manifest["binding"],
        {"protocol", "post_run_binding_nonce", "start_challenge", "statement_sha256"},
        "manifest binding",
    )
    if binding["protocol"] != "sparkinterval.trusted-compute.result-binding.v1":
        raise AppraisalError("unsupported result-binding protocol")
    for key in ("post_run_binding_nonce", "start_challenge", "statement_sha256"):
        _require_sha256(binding[key], f"manifest binding {key}")
    if binding["start_challenge"] != expected_start:
        raise AppraisalError("evidence start challenge differs from the requested challenge")
    if binding["post_run_binding_nonce"] != expected_binding:
        raise AppraisalError("evidence result binding differs from the requested binding")
    if derive_binding_nonce(expected_start, binding["statement_sha256"]) != expected_binding:
        raise AppraisalError("result binding is not derived from challenge and wire statement")
    challenge = _exact_object(
        manifest["challenge"],
        CHALLENGE_KEYS,
        "challenge",
    )
    if challenge != expected_challenge:
        raise AppraisalError(
            "worker-returned challenge differs from the retained off-VM challenge"
        )
    if (
        challenge["kind"] != CHALLENGE_KIND
        or challenge["schema_version"] != 1
        or challenge["nonce"] != expected_start
        or not isinstance(challenge["campaign_id"], str)
        or CAMPAIGN_RE.fullmatch(challenge["campaign_id"]) is None
        or not isinstance(challenge["shard_index"], int)
        or isinstance(challenge["shard_index"], bool)
        or not 0 <= challenge["shard_index"] <= 998
    ):
        raise AppraisalError("challenge record does not match the requested start challenge")
    challenge_issued = _parse_utc(challenge["issued_at_utc"], "challenge issued_at_utc")
    challenge_expires = _parse_utc(
        challenge["expires_at_utc"], "challenge expires_at_utc"
    )
    challenge_lifetime = challenge_expires - challenge_issued
    now = dt.datetime.now(dt.timezone.utc)
    if not dt.timedelta(0) < challenge_lifetime <= dt.timedelta(
        seconds=MAX_CHALLENGE_TTL_SECONDS
    ):
        raise AppraisalError("challenge lifetime is empty or exceeds the maximum")
    if not challenge_issued <= now < challenge_expires:
        raise AppraisalError("challenge is not in its current validity window")
    collection_time = _parse_utc(
        manifest["collection_time_utc"], "evidence collection_time_utc"
    )
    if not challenge_issued <= collection_time <= now < challenge_expires:
        raise AppraisalError("evidence collection time is outside the live challenge window")
    artifacts = _verify_artifact_closure(root, manifest)
    missing = COMMON_REQUIRED_ARTIFACTS - set(artifacts)
    if missing:
        raise AppraisalError(f"evidence pack lacks common artifacts: {sorted(missing)}")
    if artifacts["report.bin"].stat().st_size != 1184:
        raise AppraisalError("AMD SEV-SNP report must be exactly 1184 bytes")
    maa = _exact_object(manifest["maa"], MAA_RECORD_KEYS, "collector MAA record")
    try:
        maa_url, maa_url_issuer = validate_maa_attestation_url(maa["attestation_url"])
    except (EvidenceError, TypeError, ValueError) as error:
        raise AppraisalError(f"collector MAA attestation URL is invalid: {error}") from error
    if (
        not isinstance(maa["adapter"], str)
        or not isinstance(maa["issuer"], str)
        or maa["issuer"] != maa_url_issuer
        or not isinstance(maa["audience"], str)
        or not maa["audience"]
        or maa["provider"] != MAA_PROVIDER
        or maa_url != maa["attestation_url"]
        or _require_sha256(maa["adapter_sha256"], "collector MAA adapter hash")
        == NOT_APPLICABLE_DIGEST
        or not isinstance(maa["claims_sha512"], str)
        or SHA512_RE.fullmatch(maa["claims_sha512"]) is None
        or maa["token_signature_verified_by_collector"] is not False
    ):
        raise AppraisalError("collector MAA record is malformed or overclaims verification")
    pcr23_before = artifacts["pcr23.before.bin"].read_bytes()
    pcr23_after = artifacts["pcr23.after.bin"].read_bytes()
    expected_pcr23_after = hashlib.sha256(
        PCR23_ZERO + bytes.fromhex(expected_binding)
    ).digest()
    if pcr23_before != PCR23_ZERO:
        raise AppraisalError("PCR23 pre-extend value is not exactly 32 zero bytes")
    if pcr23_after != expected_pcr23_after:
        raise AppraisalError(
            "PCR23 post-extend value is not SHA256(32 zero bytes || result binding)"
        )
    tpm = _exact_object(manifest["tpm"], TPM_RECORD_KEYS, "collector TPM record")
    if (
        tpm["ak_handle"] != "0x81000003"
        or tpm["pcr_selection"] != TPM_PCR_SELECTION
        or tpm["pcr23_extended_with"] != expected_binding
        or tpm["pcr23_initial_value_hex"] != PCR23_ZERO.hex()
        or tpm["pcr23_expected_after_hex"] != expected_pcr23_after.hex()
        or tpm["quote_qualifying_data"] != expected_binding
        or tpm["local_checkquote_passed"] is not True
        or tpm["azure_ak_chain_verified_by_collector"] is not False
    ):
        raise AppraisalError("collector TPM record does not bind the expected quote contract")
    _require_sha256(tpm["quote_evidence_sha256"], "collector quote evidence hash")
    if not isinstance(tpm["tool_sha256"], dict) or not tpm["tool_sha256"]:
        raise AppraisalError("collector TPM tool hash map is absent")
    for name, digest in tpm["tool_sha256"].items():
        if not isinstance(name, str):
            raise AppraisalError("collector TPM tool name is not a string")
        _require_sha256(digest, f"collector TPM tool {name} hash")
    trust = _exact_object(
        manifest["trust_boundary"], TRUST_BOUNDARY_KEYS, "collector trust boundary"
    )
    if (
        trust["algorithm_execution_proven_by_collector"] is not False
        or trust["maa_jws_signature_verified_by_collector"] is not False
        or trust["signed_acceptance_certificate_issued"] is not False
        or trust["nvidia_eat_retained"]
        is not (backend == "azure_ncc40ads_h100_v5")
    ):
        raise AppraisalError("collector trust-boundary record is inconsistent")
    if backend == "azure_sevsnp_cpu":
        present = {name for name in artifacts if name.startswith("nvidia_")}
        if present or manifest["gpu"] is not None or manifest["gpu_state"] is not None:
            raise AppraisalError("CPU-only evidence must not contain NVIDIA evidence or claims")
    else:
        missing_gpu = NVIDIA_REQUIRED_ARTIFACTS - set(artifacts)
        if missing_gpu:
            raise AppraisalError(f"H100 evidence pack lacks NVIDIA artifacts: {sorted(missing_gpu)}")
        if not isinstance(manifest["gpu"], dict) or not isinstance(
            manifest["gpu_state"], dict
        ):
            raise AppraisalError("H100 evidence manifest lacks collected GPU state")
        if (
            manifest["gpu_state"].get("cc_mode") != "ON"
            or manifest["gpu_state"].get("cc_environment") != "PRODUCTION"
            or manifest["gpu_state"].get("cc_gpus_ready_state") != "Ready"
        ):
            raise AppraisalError("H100 evidence manifest does not record a Ready production GPU")
    return manifest, artifacts, manifest_digest


def _validate_measured_manifest(
    root: Path,
    backend: str,
    expected_start: str,
    expected_binding: str,
    expected_challenge: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Path], str]:
    manifest_path = _artifact_path(root, "evidence-manifest.json")
    manifest_value, manifest_digest = _load_canonical_with_digest(
        manifest_path, "measured evidence manifest"
    )
    manifest = _exact_object(
        manifest_value, MEASURED_MANIFEST_KEYS, "measured evidence manifest"
    )
    if (
        manifest["schema_version"] != 1
        or manifest["kind"] != MEASURED_EVIDENCE_KIND
        or manifest["collection_protocol"] != MEASURED_COLLECTION_PROTOCOL
        or manifest["status"]
        != "measured_evidence_collected_pending_independent_verification"
    ):
        raise AppraisalError("evidence is not the certificate-capable measured protocol")
    if manifest["backend"] != backend:
        raise AppraisalError("measured evidence backend differs from requested backend")
    binding = _exact_object(
        manifest["binding"],
        {"protocol", "post_run_binding_nonce", "start_challenge", "statement_sha256"},
        "measured manifest binding",
    )
    if binding["protocol"] != "sparkinterval.trusted-compute.result-binding.v1":
        raise AppraisalError("unsupported measured result-binding protocol")
    for key in ("post_run_binding_nonce", "start_challenge", "statement_sha256"):
        _require_sha256(binding[key], f"measured manifest binding {key}")
    if (
        binding["start_challenge"] != expected_start
        or binding["post_run_binding_nonce"] != expected_binding
        or derive_binding_nonce(expected_start, binding["statement_sha256"])
        != expected_binding
    ):
        raise AppraisalError("measured manifest has inconsistent challenge/statement binding")
    challenge = _exact_object(manifest["challenge"], CHALLENGE_KEYS, "measured challenge")
    if challenge != expected_challenge:
        raise AppraisalError("measured challenge differs from retained off-VM challenge")
    issued = _parse_utc(challenge["issued_at_utc"], "challenge issued_at_utc")
    expires = _parse_utc(challenge["expires_at_utc"], "challenge expires_at_utc")
    now = dt.datetime.now(dt.timezone.utc)
    if (
        challenge["kind"] != CHALLENGE_KIND
        or challenge["schema_version"] != 1
        or challenge["nonce"] != expected_start
        or not issued <= now < expires
        or not dt.timedelta(0) < expires - issued
        <= dt.timedelta(seconds=MAX_CHALLENGE_TTL_SECONDS)
    ):
        raise AppraisalError("measured challenge is malformed, expired, or overlong")
    collection_time = _parse_utc(
        manifest["collection_time_utc"], "measured evidence collection_time_utc"
    )
    if not issued <= collection_time <= now < expires:
        raise AppraisalError("measured evidence collection time is outside challenge window")
    artifacts = _verify_artifact_closure(root, manifest)
    required = COMMON_REQUIRED_ARTIFACTS | {
        "measured-run-package.tar",
        "pcr23.after-start.bin",
        "runner-appraisal-policy.json",
        "runner-job-spec.json",
        "runner-statement.json",
        "runner-transcript.json",
        "runner-work-trace.json",
    }
    missing = required - set(artifacts)
    if missing:
        raise AppraisalError(f"measured evidence pack lacks artifacts: {sorted(missing)}")
    if artifacts["report.bin"].stat().st_size != 1184:
        raise AppraisalError("AMD SEV-SNP report must be exactly 1184 bytes")

    runner = _exact_object(
        manifest["runner"], MEASURED_RUNNER_RECORD_KEYS, "measured runner record"
    )
    for key in (
        "appraisal_policy_sha256",
        "archive_sha256",
        "job_spec_sha256",
        "start_binding_sha256",
        "statement_sha256",
        "transcript_sha256",
    ):
        _require_sha256(runner[key], f"measured runner {key}")
    if (
        runner["protocol"] != MEASURED_COLLECTION_PROTOCOL
        or runner["local_transcript_check_only"] is not True
        or runner["statement_sha256"] != binding["statement_sha256"]
        or runner["archive_sha256"]
        != _expected_file_hash(artifacts, "measured-run-package.tar")
        or runner["appraisal_policy_sha256"]
        != _expected_file_hash(artifacts, "runner-appraisal-policy.json")
        or runner["transcript_sha256"]
        != _expected_file_hash(artifacts, "runner-transcript.json")
        or runner["job_spec_sha256"]
        != _expected_file_hash(artifacts, "runner-job-spec.json")
        or runner["statement_sha256"]
        != _expected_file_hash(artifacts, "runner-statement.json")
    ):
        raise AppraisalError("measured runner record is inconsistent with retained artifacts")

    pcr_before = artifacts["pcr23.before.bin"].read_bytes()
    pcr_started = artifacts["pcr23.after-start.bin"].read_bytes()
    pcr_final = artifacts["pcr23.after.bin"].read_bytes()
    expected_started = hashlib.sha256(
        PCR23_ZERO + bytes.fromhex(runner["start_binding_sha256"])
    ).digest()
    expected_final = hashlib.sha256(
        expected_started + bytes.fromhex(expected_binding)
    ).digest()
    if pcr_before != PCR23_ZERO or pcr_started != expected_started or pcr_final != expected_final:
        raise AppraisalError("PCR23 does not satisfy zero -> start -> result equations")
    tpm = _exact_object(
        manifest["tpm"], MEASURED_TPM_RECORD_KEYS, "measured TPM record"
    )
    if (
        tpm["ak_handle"] != "0x81000003"
        or tpm["azure_ak_chain_verified_by_collector"] is not False
        or tpm["collection_protocol"] != MEASURED_COLLECTION_PROTOCOL
        or tpm["local_checkquote_passed"] is not True
        or tpm["pcr23_initial_hex"] != PCR23_ZERO.hex()
        or tpm["pcr23_after_start_hex"] != expected_started.hex()
        or tpm["pcr23_final_hex"] != expected_final.hex()
        or tpm["pcr_selection"] != TPM_PCR_SELECTION
        or tpm["quote_qualifying_data"] != expected_binding
        or tpm["runner_transcript_sha256"] != runner["transcript_sha256"]
    ):
        raise AppraisalError("measured TPM record is inconsistent")
    _require_sha256(tpm["quote_evidence_sha256"], "measured quote evidence hash")

    maa = _exact_object(manifest["maa"], MAA_RECORD_KEYS, "collector MAA record")
    try:
        maa_url, maa_url_issuer = validate_maa_attestation_url(maa["attestation_url"])
    except (EvidenceError, TypeError, ValueError) as error:
        raise AppraisalError(f"collector MAA attestation URL is invalid: {error}") from error
    if (
        not isinstance(maa["adapter"], str)
        or maa["issuer"] != maa_url_issuer
        or not isinstance(maa["audience"], str)
        or not maa["audience"]
        or maa["provider"] != MAA_PROVIDER
        or maa_url != maa["attestation_url"]
        or _require_sha256(maa["adapter_sha256"], "collector MAA adapter hash")
        == NOT_APPLICABLE_DIGEST
        or not isinstance(maa["claims_sha512"], str)
        or SHA512_RE.fullmatch(maa["claims_sha512"]) is None
        or maa["token_signature_verified_by_collector"] is not False
    ):
        raise AppraisalError("collector MAA record is malformed or overclaims verification")
    trust = _exact_object(
        manifest["trust_boundary"], TRUST_BOUNDARY_KEYS, "collector trust boundary"
    )
    if (
        trust["algorithm_execution_proven_by_collector"] is not False
        or trust["maa_jws_signature_verified_by_collector"] is not False
        or trust["signed_acceptance_certificate_issued"] is not False
        or trust["nvidia_eat_retained"]
        is not (backend == "azure_ncc40ads_h100_v5")
    ):
        raise AppraisalError("collector trust-boundary record is inconsistent")
    if backend == "azure_sevsnp_cpu":
        present = {name for name in artifacts if name.startswith("nvidia_")}
        if present or manifest["gpu"] is not None or manifest["gpu_state"] is not None:
            raise AppraisalError("CPU measured evidence contains NVIDIA post-run artifacts")
    else:
        missing_gpu = NVIDIA_REQUIRED_ARTIFACTS - set(artifacts)
        if missing_gpu:
            raise AppraisalError(f"H100 measured evidence lacks NVIDIA artifacts: {sorted(missing_gpu)}")
        if not isinstance(manifest["gpu"], dict) or not isinstance(manifest["gpu_state"], dict):
            raise AppraisalError("H100 measured evidence lacks GPU state")
        if (
            manifest["gpu_state"].get("cc_mode") != "ON"
            or manifest["gpu_state"].get("cc_environment") != "PRODUCTION"
            or manifest["gpu_state"].get("cc_gpus_ready_state") != "Ready"
        ):
            raise AppraisalError("H100 post-run GPU state is not Ready production CC")
    return manifest, artifacts, manifest_digest


def _validate_manifest(
    root: Path,
    backend: str,
    expected_start: str,
    expected_binding: str,
    expected_challenge: Mapping[str, Any],
    *,
    test_only_allow_legacy: bool = False,
) -> tuple[dict[str, Any], dict[str, Path], str]:
    preview = _load_canonical(_artifact_path(root, "evidence-manifest.json"), "evidence manifest")
    if isinstance(preview, dict) and preview.get("kind") == MEASURED_EVIDENCE_KIND:
        return _validate_measured_manifest(
            root, backend, expected_start, expected_binding, expected_challenge
        )
    if not test_only_allow_legacy:
        raise AppraisalError(
            "legacy post-run-PCR-reset evidence is diagnostic and cannot authorize a receipt"
        )
    return _validate_legacy_manifest(
        root, backend, expected_start, expected_binding, expected_challenge
    )


def _resolve_pinned_file(
    outer_policy: Path,
    value: Any,
    expected_digest: Any,
    what: str,
    *,
    executable: bool,
    snapshot_to: Path | None = None,
) -> Path:
    if not isinstance(value, str) or not value:
        raise AppraisalError(f"{what} path must be a non-empty string")
    configured = Path(value)
    if not configured.is_absolute():
        configured = outer_policy.parent / configured
    if configured.is_symlink():
        raise AppraisalError(f"{what} must not be a symlink")
    try:
        resolved = configured.resolve(strict=True)
    except OSError as error:
        raise AppraisalError(f"cannot resolve {what}: {error}") from error
    if not resolved.is_file() or (executable and not os.access(resolved, os.X_OK)):
        raise AppraisalError(f"{what} is not an executable regular file")
    digest = _require_sha256(expected_digest, f"{what} pinned hash")
    if snapshot_to is not None:
        _snapshot_regular_file(
            resolved,
            snapshot_to,
            what,
            executable=executable,
            expected_digest=digest,
        )
        return snapshot_to
    actual, _size = sha256_file(resolved)
    if actual != digest:
        raise AppraisalError(f"{what} differs from its pinned SHA-256")
    return resolved


def _require_unchanged_file(path: Path, expected_digest: str, what: str) -> None:
    actual, _size = sha256_file(path)
    if actual != expected_digest:
        raise AppraisalError(f"{what} changed during independent appraisal")


def _validate_timeout(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 3600:
        raise AppraisalError(f"{what} timeout_seconds must be in [1, 3600]")
    return value


def _load_policy(
    path: Path,
    backend: str,
    *,
    resolution_policy: Path | None = None,
    snapshot_directory: Path | None = None,
) -> tuple[dict[str, Any], Path, Path, Path | None, Path | None, str]:
    policy_value, policy_digest = _load_canonical_with_digest(path, "appraisal policy")
    policy = _exact_object(policy_value, POLICY_KEYS, "policy")
    if policy["schema_version"] != 1 or policy["kind"] != POLICY_KIND:
        raise AppraisalError("unsupported appraisal policy kind/version")
    allowed = policy["allowed_backends"]
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(item not in BACKENDS for item in allowed)
        or len(set(allowed)) != len(allowed)
        or backend not in allowed
    ):
        raise AppraisalError("appraisal policy does not uniquely allow the requested backend")
    azure = _exact_object(
        policy["azure_appraiser"], AZURE_APPRAISER_POLICY_KEYS, "Azure appraiser policy"
    )
    _validate_timeout(azure["timeout_seconds"], "Azure appraiser")
    try:
        policy_maa_url, policy_maa_issuer = validate_maa_attestation_url(
            azure["maa_attestation_url"]
        )
    except (EvidenceError, TypeError, ValueError) as error:
        raise AppraisalError(f"policy MAA attestation URL is invalid: {error}") from error
    if (
        policy_maa_url != azure["maa_attestation_url"]
        or azure["maa_accepted_issuer"] != policy_maa_issuer
        or not isinstance(azure["maa_accepted_audience"], str)
        or not azure["maa_accepted_audience"]
        or azure["maa_accepted_provider"] != MAA_PROVIDER
    ):
        raise AppraisalError(
            "Azure appraiser policy must pin the endpoint-derived issuer, one audience, "
            "and the maa_snp provider"
        )
    resolution_policy = resolution_policy or path
    if snapshot_directory is not None:
        _make_private_directory(snapshot_directory)
        azure_snapshot = snapshot_directory / "azure"
        nvidia_snapshot = snapshot_directory / "nvidia"
    else:
        azure_snapshot = None
        nvidia_snapshot = None
    azure_executable = _resolve_pinned_file(
        resolution_policy,
        azure["executable_path"],
        azure["executable_sha256"],
        "Azure appraiser executable",
        executable=True,
        snapshot_to=(azure_snapshot / "executable" if azure_snapshot else None),
    )
    azure_policy = _resolve_pinned_file(
        resolution_policy,
        azure["policy_path"],
        azure["policy_sha256"],
        "Azure appraiser policy",
        executable=False,
        snapshot_to=(azure_snapshot / "policy" if azure_snapshot else None),
    )
    nvidia_executable: Path | None = None
    nvidia_policy: Path | None = None
    nvidia = policy["nvidia_appraiser"]
    if backend == "azure_sevsnp_cpu":
        if nvidia is not None:
            raise AppraisalError("CPU-only appraisal policy must set nvidia_appraiser to null")
    else:
        nvidia = _exact_object(
            nvidia, NVIDIA_APPRAISER_POLICY_KEYS, "NVIDIA appraiser policy"
        )
        _validate_timeout(nvidia["timeout_seconds"], "NVIDIA appraiser")
        if nvidia["verifier"] not in {"local", "remote"}:
            raise AppraisalError("NVIDIA verifier must be local or remote")
        if not isinstance(nvidia["nras_url"], str) or not nvidia["nras_url"].startswith(
            "https://"
        ):
            raise AppraisalError("NVIDIA NRAS URL must use HTTPS")
        nvidia_executable = _resolve_pinned_file(
            resolution_policy,
            nvidia["executable_path"],
            nvidia["executable_sha256"],
            "NVIDIA appraiser executable",
            executable=True,
            snapshot_to=(nvidia_snapshot / "executable" if nvidia_snapshot else None),
        )
        nvidia_policy = _resolve_pinned_file(
            resolution_policy,
            nvidia["policy_path"],
            nvidia["policy_sha256"],
            "NVIDIA appraiser policy",
            executable=False,
            snapshot_to=(nvidia_snapshot / "policy" if nvidia_snapshot else None),
        )
    return (
        policy,
        azure_executable,
        azure_policy,
        nvidia_executable,
        nvidia_policy,
        policy_digest,
    )


def _run_json(
    command: Sequence[str],
    *,
    timeout: int,
    what: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=dict(environment or _appraiser_environment()),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppraisalError(f"{what} could not run: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise AppraisalError(
            f"{what} rejected the evidence with status {completed.returncode}: {detail}"
        )
    try:
        value = _parse_canonical_json(completed.stdout, f"{what} output")
    except Exception as error:
        raise AppraisalError(f"{what} did not emit one strict JSON object: {error}") from error
    if not isinstance(value, dict):
        raise AppraisalError(f"{what} output is not a JSON object")
    return value


def _load_maa_claims(
    artifacts: Mapping[str, Path],
    *,
    expected_attestation_url: str,
    expected_provider: str,
    start_challenge: str,
    statement_sha256: str,
    result_binding: str,
) -> tuple[str, str]:
    config = _exact_object(
        _load_canonical(artifacts["maa_config.json"], "MAA config"),
        {"api_key", "attestation_provider", "attestation_url", "claims", "enable_metrics"},
        "MAA config",
    )
    if (
        config["attestation_provider"] != expected_provider
        or config["attestation_url"] != expected_attestation_url
        or config["api_key"] != ""
        or config["enable_metrics"] is not False
    ):
        raise AppraisalError("MAA config is not the expected keyless SEV-SNP adapter mode")
    claims = config["claims"]
    expected_claims = {
        "user-claims": {
            "post-run-binding-nonce": result_binding,
            "protocol": "sparkinterval.trusted-compute.result-binding.v1",
            "start-challenge": start_challenge,
            "statement-sha256": statement_sha256,
        }
    }
    if claims != expected_claims:
        raise AppraisalError("MAA user claims do not bind the exact challenge and statement")
    claims_digest = hashlib.sha512(json.dumps(claims).encode("utf-8")).hexdigest()
    runtime = _load_canonical(artifacts["runtime_data.json"], "MAA runtime data")
    runtime_strings = [
        str(item).lower() for _key, item in _walk_values(runtime) if isinstance(item, str)
    ]
    if claims_digest not in runtime_strings:
        raise AppraisalError("MAA runtime data does not contain the user-claims digest")
    try:
        token = artifacts["maa_token.jwt"].read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise AppraisalError(f"cannot read MAA token: {error}") from error
    if token.count(".") != 2 or any(not piece for piece in token.split(".")):
        raise AppraisalError("MAA token is not a compact JWS")
    return claims_digest, token


def _walk_values(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_values(item)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield str(index), item
            yield from _walk_values(item)


def _expected_file_hash(artifacts: Mapping[str, Path], name: str) -> str:
    return sha256_file(artifacts[name])[0]


def _appraise_azure(
    executable: Path,
    appraiser_policy: Path,
    policy_record: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    backend: str,
    binding: str,
    claims_digest: str,
) -> dict[str, Any]:
    command = [
        str(executable),
        "--backend",
        backend,
        "--maa-token",
        str(artifacts["maa_token.jwt"]),
        "--snp-report",
        str(artifacts["report.bin"]),
        "--runtime-data",
        str(artifacts["runtime_data.json"]),
        "--hcl-report",
        str(artifacts["azure_hcl_report.bin"]),
        "--hcl-runtime-data",
        str(artifacts["azure_hcl_runtime_data.bin"]),
        "--ak-public",
        str(artifacts["vtpm_ak.pem"]),
        "--ak-certificate",
        str(artifacts["vtpm_ak_cert.bin"]),
        "--quote-message",
        str(artifacts["tpm_quote.msg"]),
        "--quote-signature",
        str(artifacts["tpm_quote.sig"]),
        "--quote-pcrs",
        str(artifacts["tpm_quote.pcrs"]),
        "--event-log",
        str(artifacts["tcg_event_log.bin"]),
        "--pcr23-before",
        str(artifacts["pcr23.before.bin"]),
        "--pcr23-after",
        str(artifacts["pcr23.after.bin"]),
        "--policy",
        str(appraiser_policy),
        "--expected-attestation-url",
        policy_record["maa_attestation_url"],
        "--expected-maa-issuer",
        policy_record["maa_accepted_issuer"],
        "--expected-maa-audience",
        policy_record["maa_accepted_audience"],
        "--expected-maa-provider",
        policy_record["maa_accepted_provider"],
        "--expected-binding-sha256",
        binding,
        "--expected-user-claims-sha512",
        claims_digest,
    ]
    if "pcr23.after-start.bin" in artifacts:
        command.extend(
            [
                "--pcr23-after-start",
                str(artifacts["pcr23.after-start.bin"]),
                "--runner-transcript",
                str(artifacts["runner-transcript.json"]),
                "--runner-job-spec",
                str(artifacts["runner-job-spec.json"]),
                "--runner-appraisal-policy",
                str(artifacts["runner-appraisal-policy.json"]),
                "--measured-run-package",
                str(artifacts["measured-run-package.tar"]),
            ]
        )
    if backend == "azure_ncc40ads_h100_v5":
        command.extend(
            [
                "--nvidia-evidence",
                str(artifacts["nvidia_gpu_evidence.json"]),
                "--nvidia-detached-eat",
                str(artifacts["nvidia_detached_eat.json"]),
                "--nvidia-appraisal",
                str(artifacts["nvidia_gpu_attestation.json"]),
            ]
        )
    result = _exact_object(
        _run_json(
            command,
            timeout=_validate_timeout(
                policy_record["timeout_seconds"], "Azure appraiser"
            ),
            what="pinned Azure appraiser",
        ),
        AZURE_APPRAISAL_KEYS,
        "Azure appraiser output",
    )
    if (
        result["schema_version"] != 1
        or result["kind"] != AZURE_APPRAISAL_KIND
        or result["accepted"] is not True
        or result["binding_sha256"] != binding
        or result["user_claims_sha512"] != claims_digest
        or result["pcr_selection"] != TPM_PCR_SELECTION
        or result["maa_attestation_url"] != policy_record["maa_attestation_url"]
        or result["maa_issuer"] != policy_record["maa_accepted_issuer"]
        or result["maa_audience"] != policy_record["maa_accepted_audience"]
        or result["maa_provider"] != policy_record["maa_accepted_provider"]
    ):
        raise AppraisalError("Azure appraiser did not affirm the exact requested contract")
    _require_live_interval(
        result["not_before_utc"], result["not_after_utc"], "Azure appraisal"
    )
    expected_hashes = {
        "maa_token_sha256": _expected_file_hash(artifacts, "maa_token.jwt"),
        "snp_report_sha256": _expected_file_hash(artifacts, "report.bin"),
        "runtime_data_sha256": _expected_file_hash(artifacts, "runtime_data.json"),
        "hcl_report_sha256": _expected_file_hash(artifacts, "azure_hcl_report.bin"),
        "hcl_runtime_data_sha256": _expected_file_hash(
            artifacts, "azure_hcl_runtime_data.bin"
        ),
        "ak_public_sha256": _expected_file_hash(artifacts, "vtpm_ak.pem"),
        "ak_certificate_sha256": _expected_file_hash(artifacts, "vtpm_ak_cert.bin"),
        "quote_message_sha256": _expected_file_hash(artifacts, "tpm_quote.msg"),
        "quote_signature_sha256": _expected_file_hash(artifacts, "tpm_quote.sig"),
        "quote_pcrs_sha256": _expected_file_hash(artifacts, "tpm_quote.pcrs"),
        "event_log_sha256": _expected_file_hash(artifacts, "tcg_event_log.bin"),
        "pcr23_before_sha256": _expected_file_hash(artifacts, "pcr23.before.bin"),
        "pcr23_after_sha256": _expected_file_hash(artifacts, "pcr23.after.bin"),
    }
    for name, expected in expected_hashes.items():
        if result[name] != expected:
            raise AppraisalError(f"Azure appraiser changed {name}")
    claims = _exact_object(result["claims"], AZURE_CLAIM_KEYS, "Azure appraised claims")
    if claims["tee"] != "amd_sev_snp":
        raise AppraisalError("Azure appraiser did not identify AMD SEV-SNP")
    accelerator_binding = claims["accelerator_attestation_bound_to_cvm"]
    if backend == "azure_ncc40ads_h100_v5":
        if (
            accelerator_binding is not True
            or claims["pre_run_accelerator_gate_valid"] is not True
        ):
            raise AppraisalError(
                "composite appraiser did not cryptographically reappraise the pre-run "
                "accelerator attestation gate and bind accelerator evidence to this CVM"
            )
    elif (
        accelerator_binding != "not_applicable"
        or claims["pre_run_accelerator_gate_valid"] != "not_applicable"
    ):
        raise AppraisalError(
            "CPU appraisal must mark accelerator-to-CVM binding not applicable"
        )
    for name in AZURE_CLAIM_KEYS - {
        "tee",
        "accelerator_attestation_bound_to_cvm",
        "pre_run_accelerator_gate_valid",
    }:
        if claims[name] is not True:
            raise AppraisalError(f"Azure appraiser did not establish {name}")
    return result


def _detached_eat_interval(value: Any) -> tuple[dt.datetime, dt.datetime]:
    tokens = [
        item
        for _key, item in _walk_values(value)
        if isinstance(item, str)
        and item.count(".") == 2
        and all(item.split("."))
    ]
    if not tokens:
        raise AppraisalError("NVIDIA detached EAT contains no compact JWT")
    starts: list[dt.datetime] = []
    ends: list[dt.datetime] = []
    for token in tokens:
        payload_text = token.split(".")[1]
        try:
            payload_bytes = base64.urlsafe_b64decode(
                payload_text + "=" * (-len(payload_text) % 4)
            )
            payload = _parse_canonical_json(payload_bytes, "NVIDIA EAT JWT payload")
        except Exception as error:
            raise AppraisalError(f"cannot decode NVIDIA EAT JWT validity: {error}") from error
        if not isinstance(payload, dict):
            raise AppraisalError("NVIDIA EAT JWT payload is not an object")
        start_epoch = payload.get("nbf", payload.get("iat"))
        end_epoch = payload.get("exp")
        if (
            not isinstance(start_epoch, int)
            or isinstance(start_epoch, bool)
            or not isinstance(end_epoch, int)
            or isinstance(end_epoch, bool)
        ):
            raise AppraisalError("NVIDIA EAT JWT lacks integer nbf/iat and exp")
        try:
            starts.append(dt.datetime.fromtimestamp(start_epoch, tz=dt.timezone.utc))
            ends.append(dt.datetime.fromtimestamp(end_epoch, tz=dt.timezone.utc))
        except (OverflowError, OSError, ValueError) as error:
            raise AppraisalError("NVIDIA EAT JWT validity is outside UTC range") from error
    start = max(starts)
    end = min(ends)
    _require_live_interval(_format_utc(start), _format_utc(end), "NVIDIA appraisal")
    return start, end


def _appraise_nvidia(
    executable: Path,
    appraiser_policy: Path,
    policy_record: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    binding: str,
) -> tuple[dict[str, Any], dt.datetime, dt.datetime]:
    command = [
        str(executable),
        "--log-level",
        "error",
        "--format",
        "json",
        "attest",
        "--device",
        "gpu",
        "--verifier",
        policy_record["verifier"],
        "--gpu-evidence-source",
        "file",
        "--gpu-evidence-file",
        str(artifacts["nvidia_gpu_evidence.json"]),
        "--nonce",
        binding,
        "--relying-party-policy",
        str(appraiser_policy),
    ]
    if policy_record["verifier"] == "remote":
        if not os.environ.get("NV_ATTESTATION_SERVICE_KEY"):
            raise AppraisalError("remote NVIDIA appraisal requires NV_ATTESTATION_SERVICE_KEY")
        command.extend(["--nras-url", policy_record["nras_url"]])
    result = _run_json(
        command,
        timeout=_validate_timeout(policy_record["timeout_seconds"], "NVIDIA appraiser"),
        what="pinned NVIDIA nvattest appraiser",
        environment=_appraiser_environment(
            include_nvidia_service_key=policy_record["verifier"] == "remote"
        ),
    )
    if (
        not isinstance(result.get("result_code"), int)
        or isinstance(result.get("result_code"), bool)
        or result["result_code"] != 0
    ):
        raise AppraisalError("NVIDIA appraiser returned a nonzero result_code")
    claims = result.get("claims")
    if (
        not isinstance(claims, list)
        or len(claims) != 1
        or not isinstance(claims[0], dict)
    ):
        raise AppraisalError("NVIDIA appraiser did not return exactly one GPU claim set")
    claim = claims[0]
    if claim.get("secboot") is not True:
        raise AppraisalError("NVIDIA appraiser did not establish secure boot")
    if str(claim.get("dbgstat", "")).lower() != "disabled":
        raise AppraisalError("NVIDIA appraiser did not establish disabled debug state")
    if claim.get("x-nvidia-gpu-attestation-report-nonce-match") is not True:
        raise AppraisalError("NVIDIA appraiser did not establish nonce matching")
    if result.get("detached_eat") in (None, [], ""):
        raise AppraisalError("NVIDIA appraiser did not produce a detached EAT")
    not_before, not_after = _detached_eat_interval(result["detached_eat"])
    raw = _load_canonical(artifacts["nvidia_gpu_evidence.json"], "NVIDIA raw evidence")
    evidences = raw.get("evidences") if isinstance(raw, dict) else None
    if (
        not isinstance(evidences, list)
        or len(evidences) != 1
        or not isinstance(evidences[0], dict)
        or str(evidences[0].get("nonce", "")).lower().removeprefix("0x") != binding
    ):
        raise AppraisalError("NVIDIA raw evidence does not contain the expected binding nonce")
    retained_eat = _load_canonical(
        artifacts["nvidia_detached_eat.json"], "retained NVIDIA detached EAT"
    )
    if retained_eat in (None, [], "") or retained_eat != result["detached_eat"]:
        raise AppraisalError(
            "retained NVIDIA detached EAT differs from the pinned appraiser result"
        )
    retained_appraisal = _load_canonical(
        artifacts["nvidia_gpu_attestation.json"], "retained NVIDIA appraisal"
    )
    if (
        not isinstance(retained_appraisal, dict)
        or retained_appraisal.get("detached_eat") != retained_eat
    ):
        raise AppraisalError("retained NVIDIA appraisal and detached EAT disagree")
    return result, not_before, not_after


def appraise(args: argparse.Namespace) -> dict[str, Any]:
    """Appraise only private snapshots, never caller-controlled live paths."""

    if args.backend not in BACKENDS:
        raise AppraisalError(f"unsupported backend: {args.backend}")
    evidence_input = Path(args.evidence_pack)
    policy_input = Path(args.policy)
    challenge_input = Path(args.expected_challenge_file)
    if evidence_input.is_symlink():
        raise AppraisalError("evidence pack must not be a symlink")
    if policy_input.is_symlink():
        raise AppraisalError("composite appraisal policy must not be a symlink")
    if challenge_input.is_symlink():
        raise AppraisalError("retained off-VM challenge must not be a symlink")
    try:
        evidence_source = evidence_input.resolve(strict=True)
        policy_source = policy_input.resolve(strict=True)
        challenge_source = challenge_input.resolve(strict=True)
    except OSError as error:
        raise AppraisalError(f"cannot resolve appraisal input: {error}") from error
    if not evidence_source.is_dir():
        raise AppraisalError("evidence pack must be a directory")
    if not policy_source.is_file():
        raise AppraisalError("composite appraisal policy must be a regular file")
    if not challenge_source.is_file():
        raise AppraisalError("retained off-VM challenge must be a regular file")
    source_manifest = _load_canonical(
        _artifact_path(evidence_source, "evidence-manifest.json"),
        "source evidence manifest",
    )
    test_only_legacy = bool(getattr(args, "_test_only_allow_legacy_diagnostic", False))
    if (
        not isinstance(source_manifest, dict)
        or source_manifest.get("kind") != MEASURED_EVIDENCE_KIND
    ) and not test_only_legacy:
        raise AppraisalError(
            "certificate appraisal requires challenge-first measured evidence; "
            "legacy post-run PCR reset packs are diagnostic only"
        )
    with tempfile.TemporaryDirectory(prefix="sparkinterval-appraisal-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        if stat.S_IMODE(snapshot_root.stat().st_mode) != 0o700:
            raise AppraisalError("private appraisal snapshot root is not mode 0700")
        evidence_snapshot = _snapshot_evidence_pack(
            evidence_source, snapshot_root / "evidence"
        )
        policy_snapshot = snapshot_root / "composite-policy.json"
        _snapshot_regular_file(
            policy_source,
            policy_snapshot,
            "composite appraisal policy",
        )
        challenge_snapshot = snapshot_root / "retained-challenge.json"
        _snapshot_regular_file(
            challenge_source,
            challenge_snapshot,
            "retained off-VM challenge",
        )
        snapshot_args = argparse.Namespace(**vars(args))
        snapshot_args.evidence_pack = evidence_snapshot
        snapshot_args.policy = policy_snapshot
        snapshot_args.expected_challenge_file = challenge_snapshot
        snapshot_args._test_only_allow_legacy_diagnostic = test_only_legacy
        return _appraise_snapshots(
            snapshot_args,
            policy_resolution_path=policy_source,
            pinned_snapshot_directory=snapshot_root / "pinned-appraisers",
        )


def _appraise_snapshots(
    args: argparse.Namespace,
    *,
    policy_resolution_path: Path,
    pinned_snapshot_directory: Path,
) -> dict[str, Any]:
    if args.backend not in BACKENDS:
        raise AppraisalError(f"unsupported backend: {args.backend}")
    expected_start = _require_sha256(
        args.expected_start_challenge_sha256, "expected start challenge"
    )
    expected_binding = _require_sha256(
        args.expected_result_binding_sha256, "expected result binding"
    )
    challenge_path, expected_challenge, challenge_digest = _load_expected_challenge(
        args.expected_challenge_file, expected_start
    )
    try:
        root = args.evidence_pack.resolve(strict=True)
    except OSError as error:
        raise AppraisalError(f"cannot resolve evidence pack: {error}") from error
    if not root.is_dir():
        raise AppraisalError("evidence pack must be a directory")
    try:
        policy_path = args.policy.resolve(strict=True)
    except OSError as error:
        raise AppraisalError(f"cannot resolve appraisal policy: {error}") from error
    manifest, artifacts, platform_digest = _validate_manifest(
        root,
        args.backend,
        expected_start,
        expected_binding,
        expected_challenge,
        test_only_allow_legacy=bool(
            getattr(args, "_test_only_allow_legacy_diagnostic", False)
        ),
    )
    measured_transcript_result: dict[str, Any] | None = None
    if manifest["kind"] == MEASURED_EVIDENCE_KIND:
        extraction_parent = Path(
            tempfile.mkdtemp(prefix="measured-run-", dir=root.parent)
        )
        extraction_parent.chmod(0o700)
        extracted_run = extraction_parent / "run"
        try:
            extract_archive(artifacts["measured-run-package.tar"], extracted_run)
            measured_transcript_result = verify_measured_runner_transcript(
                extracted_run,
                challenge_path,
                artifacts["runner-appraisal-policy.json"],
                allow_development_policy=bool(
                    getattr(args, "_test_only_allow_development_runner_policy", False)
                ),
            )
        except (ArchiveError, TranscriptError, OSError, ValueError) as error:
            raise AppraisalError(
                f"challenge-first measured transcript rejected: {error}"
            ) from error
        finally:
            import shutil

            shutil.rmtree(extraction_parent, ignore_errors=True)
        if (
            measured_transcript_result["accepted"] is not False
            or measured_transcript_result["result_binding_sha256"] != expected_binding
            or measured_transcript_result["statement_sha256"]
            != manifest["binding"]["statement_sha256"]
            or measured_transcript_result["job_spec_sha256"]
            != manifest["runner"]["job_spec_sha256"]
        ):
            raise AppraisalError("measured transcript component returned inconsistent bindings")
    (
        policy,
        azure_executable,
        azure_policy,
        nvidia_executable,
        nvidia_policy,
        policy_digest,
    ) = _load_policy(
        policy_path,
        args.backend,
        resolution_policy=policy_resolution_path,
        snapshot_directory=pinned_snapshot_directory,
    )
    azure_record = policy["azure_appraiser"]
    if (
        manifest["maa"]["attestation_url"] != azure_record["maa_attestation_url"]
        or manifest["maa"]["issuer"] != azure_record["maa_accepted_issuer"]
        or manifest["maa"]["audience"] != azure_record["maa_accepted_audience"]
        or manifest["maa"]["provider"] != azure_record["maa_accepted_provider"]
    ):
        raise AppraisalError("collected MAA endpoint identity is not allowed by policy")
    claims_digest, _token = _load_maa_claims(
        artifacts,
        expected_attestation_url=azure_record["maa_attestation_url"],
        expected_provider=azure_record["maa_accepted_provider"],
        start_challenge=expected_start,
        statement_sha256=manifest["binding"]["statement_sha256"],
        result_binding=expected_binding,
    )
    azure_appraisal = _appraise_azure(
        azure_executable,
        azure_policy,
        azure_record,
        artifacts,
        args.backend,
        expected_binding,
        claims_digest,
    )
    validity_start, validity_end = _require_live_interval(
        azure_appraisal["not_before_utc"],
        azure_appraisal["not_after_utc"],
        "Azure appraisal",
    )
    challenge_issued = _parse_utc(
        manifest["challenge"]["issued_at_utc"], "challenge issued_at_utc"
    )
    challenge_expires = _parse_utc(
        manifest["challenge"]["expires_at_utc"], "challenge expires_at_utc"
    )
    validity_start = max(validity_start, challenge_issued)
    validity_end = min(validity_end, challenge_expires)
    _require_live_interval(
        _format_utc(validity_start),
        _format_utc(validity_end),
        "Azure appraisal/challenge intersection",
    )
    measured_protocol = manifest["kind"] == MEASURED_EVIDENCE_KIND
    quote_keys = {
        "ak_certificate_sha256",
        "ak_public_sha256",
        "event_log_sha256",
        "kind",
        "pcr_selection",
        "pcr23_after_sha256",
        "pcr23_after_value_hex",
        "pcr23_before_sha256",
        "pcr23_before_value_hex",
        "pcrs_sha256",
        "qualifying_data_sha256",
        "quote_message_sha256",
        "quote_signature_sha256",
        "schema_version",
    }
    if measured_protocol:
        quote_keys |= {"pcr23_after_start_sha256", "pcr23_after_start_value_hex"}
    quote_evidence = _exact_object(
        _load_canonical(artifacts["tpm_quote_evidence.json"], "TPM quote evidence"),
        quote_keys,
        "TPM quote evidence",
    )
    if measured_protocol:
        expected_started = hashlib.sha256(
            PCR23_ZERO + bytes.fromhex(manifest["runner"]["start_binding_sha256"])
        ).digest()
        expected_after = hashlib.sha256(
            expected_started + bytes.fromhex(expected_binding)
        ).hexdigest()
        expected_kind = "gpu_prover_vtpm_ordered_quote_evidence"
    else:
        expected_started = None
        expected_after = hashlib.sha256(
            PCR23_ZERO + bytes.fromhex(expected_binding)
        ).hexdigest()
        expected_kind = "gpu_prover_vtpm_quote_evidence"
    if (
        quote_evidence["kind"] != expected_kind
        or quote_evidence["schema_version"] != 1
        or quote_evidence["pcr_selection"] != TPM_PCR_SELECTION
        or quote_evidence["qualifying_data_sha256"] != expected_binding
        or quote_evidence["pcr23_before_value_hex"] != PCR23_ZERO.hex()
        or quote_evidence["pcr23_after_value_hex"] != expected_after
        or (
            measured_protocol
            and quote_evidence["pcr23_after_start_value_hex"]
            != expected_started.hex()
        )
    ):
        raise AppraisalError("TPM quote evidence does not bind the ordered measured result")
    if manifest["tpm"]["quote_evidence_sha256"] != _expected_file_hash(
        artifacts, "tpm_quote_evidence.json"
    ):
        raise AppraisalError("collector TPM quote-evidence hash is inconsistent")
    if manifest["maa"]["claims_sha512"] != claims_digest:
        raise AppraisalError("collector MAA claims digest is inconsistent")
    quote_component_map = {
        "ak_certificate_sha256": "vtpm_ak_cert.bin",
        "ak_public_sha256": "vtpm_ak.pem",
        "event_log_sha256": "tcg_event_log.bin",
        "pcr23_after_sha256": "pcr23.after.bin",
        "pcr23_before_sha256": "pcr23.before.bin",
        "pcrs_sha256": "tpm_quote.pcrs",
        "quote_message_sha256": "tpm_quote.msg",
        "quote_signature_sha256": "tpm_quote.sig",
    }
    if measured_protocol:
        quote_component_map["pcr23_after_start_sha256"] = "pcr23.after-start.bin"
    for key, filename in quote_component_map.items():
        if quote_evidence[key] != _expected_file_hash(artifacts, filename):
            raise AppraisalError(f"TPM quote evidence has wrong {key}")
    hashes = {
        "platform_evidence_sha256": platform_digest,
        "azure_maa_token_sha256": _expected_file_hash(artifacts, "maa_token.jwt"),
        "amd_snp_report_sha256": _expected_file_hash(artifacts, "report.bin"),
        "tpm_quote_sha256": _expected_file_hash(artifacts, "tpm_quote_evidence.json"),
        "tpm_event_log_sha256": _expected_file_hash(artifacts, "tcg_event_log.bin"),
        "nvidia_eat_sha256": NOT_APPLICABLE_DIGEST,
        "nvidia_evidence_sha256": NOT_APPLICABLE_DIGEST,
    }
    if args.backend == "azure_ncc40ads_h100_v5":
        if nvidia_executable is None or nvidia_policy is None:
            raise AppraisalError("H100 policy did not resolve a pinned NVIDIA appraiser")
        _nvidia_appraisal, nvidia_start, nvidia_end = _appraise_nvidia(
            nvidia_executable,
            nvidia_policy,
            policy["nvidia_appraiser"],
            artifacts,
            expected_binding,
        )
        validity_start = max(validity_start, nvidia_start)
        validity_end = min(validity_end, nvidia_end)
        _require_live_interval(
            _format_utc(validity_start),
            _format_utc(validity_end),
            "composite Azure/NVIDIA appraisal",
        )
        hashes["nvidia_eat_sha256"] = _expected_file_hash(
            artifacts, "nvidia_detached_eat.json"
        )
        hashes["nvidia_evidence_sha256"] = _expected_file_hash(
            artifacts, "nvidia_gpu_evidence.json"
        )
    # Appraisers may be long-running and evidence paths are shared with them.
    # Recheck the full closure before producing an acceptance result.
    _verify_artifact_closure(root, manifest)
    if sha256_file(_artifact_path(root, "evidence-manifest.json"))[0] != platform_digest:
        raise AppraisalError("evidence manifest changed during independent appraisal")
    reloaded_challenge_path, reloaded_challenge, reloaded_challenge_digest = (
        _load_expected_challenge(challenge_path, expected_start)
    )
    if (
        reloaded_challenge_path != challenge_path
        or reloaded_challenge != expected_challenge
        or reloaded_challenge_digest != challenge_digest
    ):
        raise AppraisalError("retained off-VM challenge changed during appraisal")
    _require_unchanged_file(policy_path, policy_digest, "composite appraisal policy")
    _require_unchanged_file(
        azure_executable,
        azure_record["executable_sha256"],
        "Azure appraiser executable",
    )
    _require_unchanged_file(
        azure_policy, azure_record["policy_sha256"], "Azure appraiser policy"
    )
    if args.backend == "azure_ncc40ads_h100_v5":
        if nvidia_executable is None or nvidia_policy is None:
            raise AppraisalError("H100 policy lost its pinned NVIDIA appraiser")
        nvidia_record = policy["nvidia_appraiser"]
        _require_unchanged_file(
            nvidia_executable,
            nvidia_record["executable_sha256"],
            "NVIDIA appraiser executable",
        )
        _require_unchanged_file(
            nvidia_policy,
            nvidia_record["policy_sha256"],
            "NVIDIA appraiser policy",
        )
    appraised_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if not validity_start <= appraised_at < validity_end:
        raise AppraisalError("evidence validity expired during independent appraisal")
    result = {
        "accepted": True,
        "appraised_at_utc": _format_utc(appraised_at),
        "backend": args.backend,
        "evidence_hashes": hashes,
        "kind": APPRAISAL_KIND,
        "not_after_utc": _format_utc(validity_end),
        "not_before_utc": _format_utc(validity_start),
        "policy_sha256": policy_digest,
        "result_binding_sha256": expected_binding,
        "schema_version": SCHEMA_VERSION,
        "start_challenge_sha256": expected_start,
    }
    _exact_object(result, OUTPUT_KEYS, "normalized appraisal")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-pack", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--expected-challenge-file", type=Path, required=True)
    parser.add_argument("--expected-start-challenge-sha256", required=True)
    parser.add_argument("--expected-result-binding-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = appraise(args)
    except (AppraisalError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"verify_azure_ncc_evidence: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
