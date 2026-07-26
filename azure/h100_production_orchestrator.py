#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed operator workflow for one measured Azure NCC H100 run.

This program coordinates existing repository components; it is not an
attestation appraiser and never reports an accepted theorem.  Remote transfer
of a workload/challenge into the private VM is deliberately outside its
authority.  The transfer must be acknowledged by a canonical, hash-bound
worker-stage manifest.  Likewise, the certificate package must be returned by
an operator-controlled channel before appraisal and receipt issuance.

No command uses a shell string.  Production Lean trust pins and the live
trusted-compute registry are never edited: the final command writes review
candidates under the configured review root.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterator, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_path in (
    REPOSITORY_ROOT / "azure",
    REPOSITORY_ROOT / "attestation",
    REPOSITORY_ROOT / "tools",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from collect_azure_ncc_evidence import (  # noqa: E402
    EvidenceError,
    HEX256_RE,
    load_challenge,
    require_current_challenge_window,
    validate_maa_attestation_url,
)
from create_run_bundle import canonical_json_bytes, parse_json_bytes  # noqa: E402
from generate_trusted_compute_lean import (  # noqa: E402
    load_key_manifest,
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import create_archive, extract_archive  # noqa: E402
from measured_runner import validate_job_spec  # noqa: E402
from verify_measured_runner_transcript import (  # noqa: E402
    TranscriptError,
    load_policy as load_transcript_appraisal_policy,
)
import verify_run_bundle  # noqa: E402


CONFIG_KIND = "sparkinterval_azure_h100_production_campaign"
STATE_KIND = "sparkinterval_azure_h100_operator_state"
STAGE_HANDOFF_KIND = "sparkinterval_azure_h100_worker_stage_handoff"
WORKER_COMPLETION_KIND = "sparkinterval_azure_h100_worker_completion"
SCHEMA_VERSION = 1
BACKEND = "azure_ncc40ads_h100_v5"
VM_SIZE = "Standard_NCC40ads_H100_v5"
TARGET_PROFILE_ID = "azure_ncc40ads_h100_v5"
TRUST_PROFILE_ID = "azure_ncc_sevsnp_vtpm_nvidia_cc_attested"
COLLECTION_PROTOCOL = "challenge_first_pcr23_zero_start_result_v1"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
AZURE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
KEY_URI_RE = re.compile(
    r"^https://[a-z0-9-]+\.managedhsm\.azure\.net/keys/"
    r"[A-Za-z0-9-]+/[0-9a-f]{32}$"
)
PRIVATE_IMAGE_RE = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Compute/galleries/[^/]+/images/[^/]+/versions/"
    r"[0-9]+(?:\.[0-9]+){2}$",
    re.IGNORECASE,
)
SUBNET_RE = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+/subnets/[^/]+$",
    re.IGNORECASE,
)
NVIDIA_FAIL_CLOSED_RE = re.compile(
    rb"^[ \t]*default[ \t]+nv_match[ \t]*:=[ \t]*false[ \t]*$",
    re.MULTILINE,
)
CONFIG_KEYS = {
    "azure",
    "campaign_id",
    "challenge",
    "challenge_ttl_seconds",
    "handoffs",
    "kind",
    "lean_review",
    "managed_hsm",
    "outputs",
    "policies",
    "schema_version",
    "worker",
    "workload",
}
CHALLENGE_SOURCE_KEYS = {"mode", "pin", "shard_index"}
MAX_CHALLENGE_TTL_SECONDS = 7 * 24 * 60 * 60
EVIDENCE_COLLECTION_MARGIN_SECONDS = 3 * 60 * 60
AZURE_KEYS = {
    "admin_username",
    "image",
    "location",
    "name_prefix",
    "nodes",
    "os_disk_size_gb",
    "resource_group",
    "ssh_public_key",
    "subnet_id",
    "subscription_id",
    "vm_size",
    "zone",
}
FILE_PIN_KEYS = {"path", "sha256", "size_bytes"}
POLICY_PIN_KEYS = FILE_PIN_KEYS | {"classification", "policy_id"}
WORKLOAD_KEYS = {"artifact_root", "job_spec", "package"}
POLICIES_KEYS = {
    "composite_appraisal",
    "evidence_verifier",
    "nvidia",
    "runner",
    "transcript_appraisal",
}
HSM_KEYS = {"key_id", "key_manifest", "key_uri", "public_key"}
OUTPUT_KEYS = {
    "appraisal_report",
    "challenge_dir",
    "deployment_record",
    "extracted_certificate_package",
    "lean_candidate",
    "receipt",
    "replay_db",
    "registry_candidate",
    "review_root",
    "state",
    "transcript_report",
}
HANDOFF_KEYS = {
    "returned_certificate_archive",
    "returned_worker_completion",
    "worker_stage_manifest",
}
WORKER_KEYS = {
    "artifact_root",
    "certificate_archive",
    "certificate_package",
    "challenge",
    "completion_manifest",
    "job_spec",
    "maa_attestation_url",
    "nras_url",
    "nvidia_policy",
    "run_package",
    "stage_manifest",
    "transcript_appraisal_policy",
    "workload_package",
    "gpu_verifier",
}
WORKER_PATH_KEYS = WORKER_KEYS - {"gpu_verifier", "maa_attestation_url", "nras_url"}
LEAN_REVIEW_KEYS = {"namespace", "registered_invocation"}
STATE_KEYS = {
    "accepted",
    "campaign_config_sha256",
    "campaign_id",
    "history",
    "kind",
    "records",
    "schema_version",
    "stage",
}

LIVE_TRUST_PATHS = {
    (REPOSITORY_ROOT / "SparkInterval/Execution/TrustedComputeKey.lean").resolve(),
    (REPOSITORY_ROOT / "SparkInterval/Execution/TrustedComputeRegistry.lean").resolve(),
    (REPOSITORY_ROOT / "profiles/verifier_keys/trusted_compute_keys.json").resolve(),
}


class OrchestratorError(RuntimeError):
    """A campaign, state transition, prerequisite, or child command failed."""


def _exact(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise OrchestratorError(
            f"{what} has wrong fields "
            f"(missing={sorted(keys - actual)}, unexpected={sorted(actual - keys)})"
        )
    return value


def _canonical_load(path: Path, what: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise OrchestratorError(f"{what} must be a regular non-symlink file: {path}")
    try:
        raw = path.read_bytes()
        value = parse_json_bytes(raw, what)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OrchestratorError(f"cannot load {what}: {error}") from error
    if not isinstance(value, dict):
        raise OrchestratorError(f"{what} must be a JSON object")
    canonical = canonical_json_bytes(value)
    if raw not in (canonical, canonical + b"\n"):
        raise OrchestratorError(f"{what} must use canonical JSON")
    return value, canonical


def _sha256_file(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise OrchestratorError(f"pinned input must be a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        after = os.fstat(source.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if identity(before) != identity(after):
        raise OrchestratorError(f"pinned input changed while hashing: {path}")
    return digest.hexdigest(), size


def _read_regular_once(
    path: Path, what: str, maximum: int = 64 * 1024 * 1024
) -> bytes:
    """Capture one non-linked regular file through a non-following descriptor."""

    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size < 0
                or before.st_size > maximum
            ):
                raise OrchestratorError(
                    f"{what} must be one non-linked regular file of at most {maximum} bytes"
                )
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                block = os.read(descriptor, min(remaining, 1024 * 1024))
                if not block:
                    raise OrchestratorError(f"{what} was truncated while captured")
                chunks.append(block)
                remaining -= len(block)
            if os.read(descriptor, 1):
                raise OrchestratorError(f"{what} grew while captured")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise OrchestratorError(f"cannot capture {what}: {error}") from error
    identity = lambda item: (
        item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size,
        item.st_mtime_ns, item.st_ctime_ns,
    )
    if identity(before) != identity(after):
        raise OrchestratorError(f"{what} changed while captured")
    return b"".join(chunks)


def _absolute_path(value: Any, what: str, *, allow_missing: bool = True) -> Path:
    if not isinstance(value, str) or not value:
        raise OrchestratorError(f"{what} must be a nonempty absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise OrchestratorError(f"{what} must be an absolute path without '..'")
    if not allow_missing:
        try:
            return path.resolve(strict=True)
        except OSError as error:
            raise OrchestratorError(f"cannot resolve {what}: {error}") from error
    return path.resolve(strict=False)


def _digest(value: Any, what: str) -> str:
    if not isinstance(value, str) or HEX256_RE.fullmatch(value) is None:
        raise OrchestratorError(f"{what} must be lowercase SHA-256 hex")
    return value


def _integer(value: Any, what: str, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise OrchestratorError(f"{what} must be in [{minimum}, {maximum}]")
    return value


def _resource_subscription(resource_id: str) -> str:
    pieces = resource_id.split("/")
    if len(pieces) < 3 or pieces[1].casefold() != "subscriptions" or not pieces[2]:
        raise OrchestratorError("Azure resource ID omits its subscription")
    return pieces[2]


def _file_pin(value: Any, what: str, *, executable: bool = False) -> tuple[dict[str, Any], Path]:
    pin = _exact(value, FILE_PIN_KEYS, what)
    raw_path = Path(pin["path"]) if isinstance(pin["path"], str) else Path()
    if raw_path.is_symlink():
        raise OrchestratorError(f"{what} path must not be a symlink: {raw_path}")
    path = _absolute_path(pin["path"], f"{what} path", allow_missing=False)
    digest, size = _sha256_file(path)
    if digest != _digest(pin["sha256"], f"{what} digest") or size != _integer(
        pin["size_bytes"], f"{what} size", 0, 2**63 - 1
    ):
        raise OrchestratorError(f"{what} does not match its configured digest/size")
    if executable and not os.access(path, os.X_OK):
        raise OrchestratorError(f"{what} is not executable: {path}")
    return pin, path


def _declared_file_pin(value: Any, what: str) -> dict[str, Any]:
    """Validate a guest-side pin without assuming it exists on the operator."""

    pin = _exact(value, FILE_PIN_KEYS, what)
    _absolute_path(pin["path"], f"{what} path")
    _digest(pin["sha256"], f"{what} digest")
    _integer(pin["size_bytes"], f"{what} size", 0, 2**63 - 1)
    return pin


def _policy_pin(value: Any, what: str) -> tuple[dict[str, Any], Path]:
    pin = _exact(value, POLICY_PIN_KEYS, what)
    if pin["classification"] != "production":
        raise OrchestratorError(f"{what} must be classified production")
    if not isinstance(pin["policy_id"], str) or NAME_RE.fullmatch(pin["policy_id"]) is None:
        raise OrchestratorError(f"{what} policy_id is malformed")
    file_pin = {key: pin[key] for key in FILE_PIN_KEYS}
    _unused, path = _file_pin(file_pin, what)
    return pin, path


def _path_under(path: Path, root: Path, what: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise OrchestratorError(f"{what} must stay under review_root") from error


def _load_runner_policy(path: Path, expected: dict[str, Any], image: str) -> None:
    policy, canonical = _canonical_load(path, "production measured-runner policy")
    if (
        policy.get("kind") != "sparkinterval_measured_runner_policy"
        or policy.get("schema_version") != 1
        or policy.get("classification") != "production"
        or policy.get("production_ready") is not True
        or policy.get("policy_id") != expected["policy_id"]
        or policy.get("immutable_image_reference") != image
        or policy.get("immutable_image_reference_sha256")
        != hashlib.sha256(image.encode("utf-8")).hexdigest()
    ):
        raise OrchestratorError(
            "runner policy is not a production policy bound to the exact immutable image"
        )
    required = policy.get("required_claims")
    minimum_claims = {
        "challenge_received_before_pcr_start",
        "ordered_pcr23_start_and_result_extensions",
        "exact_argv_without_shell",
        "challenge_dependent_work_trace",
        "fresh_exclusive_output",
        "retained_off_vm_challenge_match",
        "immutable_image_and_runtime_closure",
    }
    if not isinstance(required, list) or not minimum_claims <= set(required):
        raise OrchestratorError("runner policy omits required production claims")
    if hashlib.sha256(canonical).hexdigest() != expected["sha256"]:
        raise OrchestratorError("runner policy canonical digest differs from its file pin")


def _load_transcript_policy(
    path: Path,
    expected: dict[str, Any],
    *,
    job_hash: str,
    runner_policy_hash: str,
    target_profile_hash: str,
    trust_profile_hash: str,
) -> None:
    try:
        policy, canonical_hash = load_transcript_appraisal_policy(
            path, allow_development=False
        )
    except (OSError, TranscriptError, ValueError) as error:
        raise OrchestratorError(f"production transcript appraisal policy rejected: {error}") from error
    if (
        policy.get("classification") != "production"
        or policy.get("policy_id") != expected["policy_id"]
        or BACKEND not in policy.get("allowed_backends", [])
        or job_hash not in policy.get("allowed_job_spec_sha256", [])
        or runner_policy_hash not in policy.get("allowed_runner_policy_sha256", [])
        or target_profile_hash not in policy.get("allowed_target_profile_sha256", [])
        or trust_profile_hash not in policy.get("allowed_trust_profile_sha256", [])
    ):
        raise OrchestratorError("transcript policy does not allow every exact production H100 pin")
    if canonical_hash != expected["sha256"]:
        raise OrchestratorError("transcript policy canonical digest differs from its file pin")


def _resolve_policy_child(policy_path: Path, value: Any, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise OrchestratorError(f"{what} path is absent")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = policy_path.parent / candidate
    return candidate.resolve(strict=True)


def _load_composite_policy(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    policy, canonical = _canonical_load(path, "production composite appraisal policy")
    if (
        policy.get("kind") != "sparkinterval_azure_evidence_appraisal_policy"
        or policy.get("schema_version") != 1
        or BACKEND not in policy.get("allowed_backends", [])
        or not isinstance(policy.get("azure_appraiser"), dict)
        or not isinstance(policy.get("nvidia_appraiser"), dict)
    ):
        raise OrchestratorError("composite appraiser policy is not H100-capable")
    if hashlib.sha256(canonical).hexdigest() != expected["sha256"]:
        raise OrchestratorError("composite appraiser policy digest differs from its file pin")
    for name in ("azure_appraiser", "nvidia_appraiser"):
        record = policy[name]
        executable = _resolve_policy_child(path, record.get("executable_path"), f"{name} executable")
        child_policy = _resolve_policy_child(path, record.get("policy_path"), f"{name} policy")
        executable_hash, _ = _sha256_file(executable)
        child_hash, _ = _sha256_file(child_policy)
        if executable_hash != record.get("executable_sha256") or child_hash != record.get(
            "policy_sha256"
        ):
            raise OrchestratorError(f"{name} executable/policy differs from its composite pin")
        if not os.access(executable, os.X_OK):
            raise OrchestratorError(f"{name} executable is not executable")
    return policy


def _validate_key(
    hsm: dict[str, Any],
    *,
    evidence_verifier_sha256: str,
    evidence_policy_sha256: str,
    target_profile_sha256: str,
    trust_profile_sha256: str,
) -> tuple[Path, Path]:
    if KEY_URI_RE.fullmatch(hsm["key_uri"]) is None:
        raise OrchestratorError("Managed HSM key URI must include an immutable 32-hex version")
    if not isinstance(hsm["key_id"], str) or NAME_RE.fullmatch(hsm["key_id"]) is None:
        raise OrchestratorError("Managed HSM key_id is malformed")
    _manifest_pin, manifest_path = _file_pin(hsm["key_manifest"], "verifier-key manifest")
    public_pin, public_path = _file_pin(hsm["public_key"], "pinned verifier public key")
    try:
        manifest = load_key_manifest(manifest_path)
    except Exception as error:
        raise OrchestratorError(f"verifier-key manifest rejected: {error}") from error
    if hsm["key_id"] not in manifest:
        raise OrchestratorError("production key_id is absent from verifier-key manifest")
    key = manifest[hsm["key_id"]]
    if key["classification"] != "production" or key["public_key_sha256"] != public_pin["sha256"]:
        raise OrchestratorError("Managed HSM public key is not production-pinned")
    expected_profile = {
        "backend": BACKEND,
        "target_profile_sha256": target_profile_sha256,
        "trust_profile_sha256": trust_profile_sha256,
        "verifier_artifact_sha256": evidence_verifier_sha256,
        "verifier_policy_sha256": evidence_policy_sha256,
    }
    if expected_profile not in key["allowed_verifier_profiles"]:
        raise OrchestratorError("production key manifest does not allow the exact H100 verifier tuple")
    return manifest_path, public_path


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    config, canonical = _canonical_load(path, "H100 production campaign config")
    config = _exact(config, CONFIG_KEYS, "campaign config")
    if config["kind"] != CONFIG_KIND or config["schema_version"] != SCHEMA_VERSION:
        raise OrchestratorError("unsupported campaign config kind/version")
    if not isinstance(config["campaign_id"], str) or NAME_RE.fullmatch(config["campaign_id"]) is None:
        raise OrchestratorError("campaign_id is malformed")
    challenge_source = _exact(
        config["challenge"], CHALLENGE_SOURCE_KEYS, "challenge source"
    )
    challenge_index = _integer(
        challenge_source["shard_index"], "challenge shard index", 0, 10**9
    )
    pinned_challenge: dict[str, Any] | None = None
    if challenge_source["mode"] == "operator_generated_fresh_v1":
        if challenge_source["pin"] is not None or challenge_index != 0:
            raise OrchestratorError(
                "operator-generated challenges require pin=null and shard_index=0"
            )
    elif challenge_source["mode"] == "pinned_portfolio_handoff_v1":
        _challenge_pin, pinned_challenge_path = _file_pin(
            challenge_source["pin"], "pinned portfolio challenge"
        )
        try:
            pinned_challenge = load_challenge(pinned_challenge_path)
        except (EvidenceError, OSError, TypeError, ValueError) as error:
            raise OrchestratorError(
                f"pinned portfolio challenge is invalid: {error}"
            ) from error
        if (
            pinned_challenge["campaign_id"] != config["campaign_id"]
            or pinned_challenge["shard_index"] != challenge_index
        ):
            raise OrchestratorError(
                "pinned portfolio challenge identity differs from this campaign"
            )
    else:
        raise OrchestratorError("unsupported challenge source mode")
    review = _exact(config["lean_review"], LEAN_REVIEW_KEYS, "Lean review config")
    if not isinstance(review["namespace"], str) or re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", review["namespace"]
    ) is None:
        raise OrchestratorError("Lean review namespace is malformed")
    registered_expected: dict[str, Any] | None = None
    if review["registered_invocation"] is not None:
        if not isinstance(review["registered_invocation"], str) or not review[
            "registered_invocation"
        ]:
            raise OrchestratorError("registered_invocation is malformed")
        try:
            registered_expected = registered_invocation_expected(
                review["registered_invocation"]
            )
            registered_backend = registered_invocation_backend(
                review["registered_invocation"]
            )
        except Exception as error:
            raise OrchestratorError("registered_invocation is not source-supported") from error
        if registered_backend != BACKEND:
            raise OrchestratorError("registered_invocation is not H100-backend-compatible")

    azure = _exact(config["azure"], AZURE_KEYS, "azure config")
    if azure["vm_size"] != VM_SIZE or azure["nodes"] != 1:
        raise OrchestratorError("one exact Standard_NCC40ads_H100_v5 VM is required")
    if azure["location"] not in {"centralus", "eastus2", "westeurope"}:
        raise OrchestratorError("Azure location is outside the reviewed NCC region set")
    if azure["zone"] not in (None, "1", "2", "3"):
        raise OrchestratorError("Azure zone must be null, 1, 2, or 3")
    if PRIVATE_IMAGE_RE.fullmatch(azure["image"]) is None:
        raise OrchestratorError("Azure image must be an exact versioned private Compute Gallery image")
    if SUBNET_RE.fullmatch(azure["subnet_id"]) is None:
        raise OrchestratorError("Azure subnet must be a complete private subnet resource ID")
    for key in ("resource_group", "name_prefix", "admin_username"):
        if not isinstance(azure[key], str) or AZURE_NAME_RE.fullmatch(azure[key]) is None:
            raise OrchestratorError(f"Azure {key} is malformed")
    if not isinstance(azure["subscription_id"], str) or not azure["subscription_id"]:
        raise OrchestratorError("Azure subscription_id is absent")
    if (
        _resource_subscription(azure["image"]).casefold()
        != azure["subscription_id"].casefold()
        or _resource_subscription(azure["subnet_id"]).casefold()
        != azure["subscription_id"].casefold()
    ):
        raise OrchestratorError("image and subnet must belong to the selected Azure subscription")
    _integer(azure["os_disk_size_gb"], "OS disk size", 100, 32767)
    _file_pin(azure["ssh_public_key"], "Azure SSH public key")

    workload = _exact(config["workload"], WORKLOAD_KEYS, "workload config")
    artifact_root = _absolute_path(workload["artifact_root"], "workload artifact_root", allow_missing=False)
    if not artifact_root.is_dir():
        raise OrchestratorError("workload artifact_root is not a directory")
    job_pin, job_path = _file_pin(workload["job_spec"], "measured job spec")
    _package_pin, package_path = _file_pin(workload["package"], "measured workload package")
    try:
        job_path.relative_to(artifact_root)
    except ValueError as error:
        raise OrchestratorError("measured job spec must be inside artifact_root") from error
    try:
        package_path.relative_to(artifact_root)
    except ValueError:
        pass
    else:
        raise OrchestratorError("measured workload package must be outside artifact_root")
    job_value, job_canonical = _canonical_load(job_path, "measured job spec")
    try:
        job = validate_job_spec(job_value)
    except Exception as error:
        raise OrchestratorError(f"measured H100 job spec rejected: {error}") from error
    if hashlib.sha256(job_canonical).hexdigest() != job_pin["sha256"]:
        raise OrchestratorError("job spec canonical digest differs from its file pin")
    if job["backend"] != BACKEND:
        raise OrchestratorError("measured job is not an Azure NCC H100 job")
    registered_job_fields = {
        "algorithm_hash": job["algorithm"]["definition_sha256"],
        "algorithm_id": job["algorithm"]["algorithm_id"],
        "domain_hash": job["domain_coverage"]["canonical_sha256"],
        "input_hash": job["input_artifact"]["sha256"],
        "parameters_hash": job["parameters"]["canonical_sha256"],
    }
    if registered_expected is not None and any(
        registered_expected.get(name) != value
        for name, value in registered_job_fields.items()
    ):
        raise OrchestratorError(
            "measured job algorithm/input/parameters/domain do not match the selected "
            "closed H100 invocation"
        )
    if (
        job["target_profile"]["profile_id"] != TARGET_PROFILE_ID
        or job["trust_profile"]["profile_id"] != TRUST_PROFILE_ID
    ):
        raise OrchestratorError("measured job uses the wrong production target/trust profiles")
    challenge_ttl = _integer(
        config["challenge_ttl_seconds"],
        "challenge TTL",
        1,
        MAX_CHALLENGE_TTL_SECONDS,
    )
    if pinned_challenge is not None:
        try:
            issued = dt.datetime.strptime(
                pinned_challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=dt.timezone.utc)
            expires = dt.datetime.strptime(
                pinned_challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=dt.timezone.utc)
        except (KeyError, TypeError, ValueError) as error:
            raise OrchestratorError(
                "pinned portfolio challenge has non-canonical timestamps"
            ) from error
        if expires - issued != dt.timedelta(seconds=challenge_ttl):
            raise OrchestratorError(
                "pinned portfolio challenge TTL differs from the H100 campaign"
            )
    command_timeout = job.get("command", {}).get("timeout_seconds")
    gate_timeout = job.get("gpu_pre_run_gate", {}).get("timeout_seconds")
    if (
        not isinstance(command_timeout, int)
        or isinstance(command_timeout, bool)
        or not isinstance(gate_timeout, int)
        or isinstance(gate_timeout, bool)
    ):
        raise OrchestratorError("validated H100 job omits command/gate timeout bounds")
    required_ttl = command_timeout + gate_timeout + EVIDENCE_COLLECTION_MARGIN_SECONDS
    if challenge_ttl <= required_ttl:
        raise OrchestratorError(
            "challenge TTL must exceed the job timeout, H100 gate timeout, and "
            f"{EVIDENCE_COLLECTION_MARGIN_SECONDS}-second evidence margin; one shard must fit"
        )

    policies = _exact(config["policies"], POLICIES_KEYS, "policy config")
    runner_pin, runner_path = _policy_pin(policies["runner"], "measured-runner policy")
    _nvidia_pin, nvidia_path = _policy_pin(policies["nvidia"], "NVIDIA policy")
    transcript_pin, transcript_path = _policy_pin(
        policies["transcript_appraisal"], "transcript appraisal policy"
    )
    composite_pin, composite_path = _policy_pin(
        policies["composite_appraisal"], "composite appraisal policy"
    )
    evidence_pin, _evidence_path = _file_pin(
        policies["evidence_verifier"], "evidence verifier", executable=True
    )
    if nvidia_path.resolve() == (REPOSITORY_ROOT / "attestation/policies/gpu_prover_h100.rego").resolve():
        raise OrchestratorError("checked-in baseline NVIDIA policy is development-only")
    if NVIDIA_FAIL_CLOSED_RE.search(nvidia_path.read_bytes()) is None:
        raise OrchestratorError("production NVIDIA policy must fail closed by default")
    if job["runner_policy"]["sha256"] != runner_pin["sha256"]:
        raise OrchestratorError("job runner-policy digest differs from campaign policy")
    _load_runner_policy(runner_path, runner_pin, azure["image"])
    _load_transcript_policy(
        transcript_path,
        transcript_pin,
        job_hash=job_pin["sha256"],
        runner_policy_hash=runner_pin["sha256"],
        target_profile_hash=job["target_profile"]["sha256"],
        trust_profile_hash=job["trust_profile"]["sha256"],
    )
    composite_policy = _load_composite_policy(composite_path, composite_pin)

    hsm = _exact(config["managed_hsm"], HSM_KEYS, "Managed HSM config")
    _validate_key(
        hsm,
        evidence_verifier_sha256=evidence_pin["sha256"],
        evidence_policy_sha256=composite_pin["sha256"],
        target_profile_sha256=job["target_profile"]["sha256"],
        trust_profile_sha256=job["trust_profile"]["sha256"],
    )

    outputs = _exact(config["outputs"], OUTPUT_KEYS, "output config")
    review_root = _absolute_path(outputs["review_root"], "review_root")
    output_paths: dict[str, Path] = {}
    for name in OUTPUT_KEYS - {"review_root"}:
        output_paths[name] = _absolute_path(outputs[name], f"output {name}")
        _path_under(output_paths[name], review_root, f"output {name}")
        if output_paths[name] in LIVE_TRUST_PATHS:
            raise OrchestratorError(f"output {name} targets a live production trust file")
    if len(set(output_paths.values())) != len(output_paths):
        raise OrchestratorError("operator output paths must be pairwise distinct")
    handoffs = _exact(config["handoffs"], HANDOFF_KEYS, "handoff config")
    handoff_paths = {
        name: _absolute_path(value, f"handoff {name}")
        for name, value in handoffs.items()
    }
    if len(set(handoff_paths.values())) != len(handoff_paths):
        raise OrchestratorError("operator handoff paths must be pairwise distinct")
    if set(handoff_paths.values()) & set(output_paths.values()):
        raise OrchestratorError("operator handoff and output paths must be distinct")
    if set(handoff_paths.values()) & LIVE_TRUST_PATHS:
        raise OrchestratorError("operator handoff path targets a live production trust file")
    worker = _exact(config["worker"], WORKER_KEYS, "worker config")
    worker_paths = {
        name: _absolute_path(worker[name], f"worker {name}") for name in WORKER_PATH_KEYS
    }
    if len(set(worker_paths.values())) != len(worker_paths):
        raise OrchestratorError("worker paths must be pairwise distinct")
    try:
        worker_paths["job_spec"].relative_to(worker_paths["artifact_root"])
    except ValueError as error:
        raise OrchestratorError("worker job_spec must be inside worker artifact_root") from error
    for name, worker_path in worker_paths.items():
        if name in {"artifact_root", "job_spec"}:
            continue
        try:
            worker_path.relative_to(worker_paths["artifact_root"])
        except ValueError:
            continue
        raise OrchestratorError(
            f"worker {name} must be outside the fresh archive extraction root"
        )
    try:
        maa_url, _maa_issuer = validate_maa_attestation_url(worker["maa_attestation_url"])
    except (EvidenceError, TypeError, ValueError) as error:
        raise OrchestratorError(f"worker MAA endpoint is invalid: {error}") from error
    azure_appraiser = composite_policy["azure_appraiser"]
    nvidia_appraiser = composite_policy["nvidia_appraiser"]
    if (
        maa_url != worker["maa_attestation_url"]
        or worker["maa_attestation_url"] != azure_appraiser["maa_attestation_url"]
        or worker["gpu_verifier"] != nvidia_appraiser["verifier"]
        or worker["nras_url"] != nvidia_appraiser["nras_url"]
    ):
        raise OrchestratorError(
            "worker collection endpoints/verifier must equal the production appraisal policy"
        )
    if worker["gpu_verifier"] not in {"local", "remote"}:
        raise OrchestratorError("worker gpu_verifier must be local or remote")
    if not isinstance(worker["nras_url"], str) or not worker["nras_url"].startswith("https://"):
        raise OrchestratorError("worker NRAS endpoint must use HTTPS")
    return config, hashlib.sha256(canonical).hexdigest()


def load_worker_config(path: Path) -> tuple[dict[str, Any], str]:
    """Validate a staged config without dereferencing operator-local paths.

    The operator already validated every source pin before creating the stage
    handoff.  The guest revalidates the canonical config and all guest-local
    transferred bytes; it must not need access to operator storage.
    """

    config, canonical = _canonical_load(path, "staged H100 campaign config")
    config = _exact(config, CONFIG_KEYS, "campaign config")
    if config["kind"] != CONFIG_KIND or config["schema_version"] != SCHEMA_VERSION:
        raise OrchestratorError("unsupported staged campaign config kind/version")
    if not isinstance(config["campaign_id"], str) or NAME_RE.fullmatch(
        config["campaign_id"]
    ) is None:
        raise OrchestratorError("staged campaign_id is malformed")
    challenge_source = _exact(
        config["challenge"], CHALLENGE_SOURCE_KEYS, "staged challenge source"
    )
    challenge_index = _integer(
        challenge_source["shard_index"],
        "staged challenge shard index",
        0,
        10**9,
    )
    if challenge_source["mode"] == "operator_generated_fresh_v1":
        if challenge_source["pin"] is not None or challenge_index != 0:
            raise OrchestratorError("staged operator-generated challenge is malformed")
    elif challenge_source["mode"] == "pinned_portfolio_handoff_v1":
        _declared_file_pin(
            challenge_source["pin"], "staged pinned portfolio challenge"
        )
    else:
        raise OrchestratorError("unsupported staged challenge source mode")
    _integer(
        config["challenge_ttl_seconds"],
        "staged challenge TTL",
        1,
        MAX_CHALLENGE_TTL_SECONDS,
    )
    azure = _exact(config["azure"], AZURE_KEYS, "azure config")
    if (
        azure["vm_size"] != VM_SIZE
        or azure["nodes"] != 1
        or PRIVATE_IMAGE_RE.fullmatch(azure["image"]) is None
        or SUBNET_RE.fullmatch(azure["subnet_id"]) is None
    ):
        raise OrchestratorError("staged config is not bound to one exact private NCC H100 VM")
    if (
        not isinstance(azure["subscription_id"], str)
        or _resource_subscription(azure["image"]).casefold()
        != azure["subscription_id"].casefold()
        or _resource_subscription(azure["subnet_id"]).casefold()
        != azure["subscription_id"].casefold()
    ):
        raise OrchestratorError("staged Azure resource subscriptions are inconsistent")
    workload = _exact(config["workload"], WORKLOAD_KEYS, "workload config")
    _absolute_path(workload["artifact_root"], "operator workload artifact_root")
    _declared_file_pin(workload["job_spec"], "operator measured job spec")
    _declared_file_pin(workload["package"], "operator workload package")
    policies = _exact(config["policies"], POLICIES_KEYS, "policy config")
    for name in ("runner", "nvidia", "transcript_appraisal", "composite_appraisal"):
        pin = _exact(policies[name], POLICY_PIN_KEYS, f"operator {name} policy")
        if pin["classification"] != "production":
            raise OrchestratorError(f"operator {name} policy is not production-classified")
        if not isinstance(pin["policy_id"], str) or NAME_RE.fullmatch(pin["policy_id"]) is None:
            raise OrchestratorError(f"operator {name} policy_id is malformed")
        _declared_file_pin({key: pin[key] for key in FILE_PIN_KEYS}, f"operator {name} policy")
    _declared_file_pin(policies["evidence_verifier"], "operator evidence verifier")
    _exact(config["managed_hsm"], HSM_KEYS, "Managed HSM config")
    outputs = _exact(config["outputs"], OUTPUT_KEYS, "output config")
    for name, value in outputs.items():
        _absolute_path(value, f"operator output {name}")
    handoffs = _exact(config["handoffs"], HANDOFF_KEYS, "handoff config")
    for name, value in handoffs.items():
        _absolute_path(value, f"handoff {name}")
    worker = _exact(config["worker"], WORKER_KEYS, "worker config")
    worker_paths = {
        name: _absolute_path(worker[name], f"worker {name}") for name in WORKER_PATH_KEYS
    }
    if len(set(worker_paths.values())) != len(worker_paths):
        raise OrchestratorError("worker paths must be pairwise distinct")
    try:
        worker_paths["job_spec"].relative_to(worker_paths["artifact_root"])
    except ValueError as error:
        raise OrchestratorError("worker job_spec must be inside worker artifact_root") from error
    for name, worker_path in worker_paths.items():
        if name in {"artifact_root", "job_spec"}:
            continue
        try:
            worker_path.relative_to(worker_paths["artifact_root"])
        except ValueError:
            continue
        raise OrchestratorError(
            f"worker {name} must be outside the fresh archive extraction root"
        )
    try:
        maa_url, _maa_issuer = validate_maa_attestation_url(worker["maa_attestation_url"])
    except (EvidenceError, TypeError, ValueError) as error:
        raise OrchestratorError(f"worker MAA endpoint is invalid: {error}") from error
    if maa_url != worker["maa_attestation_url"]:
        raise OrchestratorError("worker MAA endpoint is not canonical")
    if worker["gpu_verifier"] not in {"local", "remote"}:
        raise OrchestratorError("worker gpu_verifier must be local or remote")
    if not isinstance(worker["nras_url"], str) or not worker["nras_url"].startswith("https://"):
        raise OrchestratorError("worker NRAS endpoint must use HTTPS")
    review = _exact(config["lean_review"], LEAN_REVIEW_KEYS, "Lean review config")
    if not isinstance(review["namespace"], str) or re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", review["namespace"]
    ) is None:
        raise OrchestratorError("staged Lean review namespace is malformed")
    if review["registered_invocation"] is not None:
        try:
            backend = registered_invocation_backend(review["registered_invocation"])
        except Exception as error:
            raise OrchestratorError("staged registered_invocation is unsupported") from error
        if backend != BACKEND:
            raise OrchestratorError("staged registered_invocation is not H100-compatible")
    return config, hashlib.sha256(canonical).hexdigest()


def _tool(relative: str) -> Path:
    path = (REPOSITORY_ROOT / relative).resolve(strict=True)
    if not path.is_file():
        raise OrchestratorError(f"required repository tool is absent: {relative}")
    return path


def _challenge_path(config: dict[str, Any]) -> Path:
    shard_index = config["challenge"]["shard_index"]
    filename = (
        "shard-000.challenge.json"
        if config["challenge"]["mode"] == "operator_generated_fresh_v1"
        else f"shard-{shard_index:09d}.challenge.json"
    )
    return Path(config["outputs"]["challenge_dir"]) / filename


def command_plan(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    azure = config["azure"]
    policies = config["policies"]
    outputs = config["outputs"]
    worker = config["worker"]
    hsm = config["managed_hsm"]
    review = config["lean_review"]
    deploy = [
        sys.executable,
        str(_tool("azure/ncc_h100.py")),
        "deploy",
        "--subscription",
        azure["subscription_id"],
        "--location",
        azure["location"],
        "--nodes",
        "1",
        "--resource-group",
        azure["resource_group"],
        "--name-prefix",
        azure["name_prefix"],
        "--admin-username",
        azure["admin_username"],
        "--ssh-key",
        azure["ssh_public_key"]["path"],
        "--subnet-id",
        azure["subnet_id"],
        "--image",
        azure["image"],
        "--os-disk-size-gb",
        str(azure["os_disk_size_gb"]),
    ]
    if azure["zone"] is not None:
        deploy.extend(["--zone", azure["zone"]])
    if config["challenge"]["mode"] == "operator_generated_fresh_v1":
        challenge: list[str] | None = [
            sys.executable,
            str(_tool("azure/create_attestation_challenges.py")),
            "--campaign-id",
            config["campaign_id"],
            "--count",
            "1",
            "--output-dir",
            outputs["challenge_dir"],
            "--ttl-seconds",
            str(config["challenge_ttl_seconds"]),
        ]
    else:
        challenge = None
    runner = [
        sys.executable,
        str(_tool("azure/measured_runner.py")),
        "--job-spec",
        worker["job_spec"],
        "--artifact-root",
        worker["artifact_root"],
        "--challenge",
        worker["challenge"],
        "--output-dir",
        worker["run_package"],
    ]
    collector = [
        sys.executable,
        str(_tool("attestation/collect_azure_measured_evidence.py")),
        "--challenge",
        worker["challenge"],
        "--run-package",
        worker["run_package"],
        "--runner-appraisal-policy",
        worker["transcript_appraisal_policy"],
        "--backend",
        BACKEND,
        "--output-dir",
        worker["certificate_package"],
        "--maa-attestation-url",
        worker["maa_attestation_url"],
        "--policy",
        worker["nvidia_policy"],
        "--gpu-verifier",
        worker["gpu_verifier"],
        "--nras-url",
        worker["nras_url"],
    ]
    extracted = Path(outputs["extracted_certificate_package"])
    run_root = extracted / "bundle-root"
    evidence_root = extracted / "evidence"
    bundle = run_root / "run-bundle.json"
    retained_challenge = _challenge_path(config)
    transcript = [
        sys.executable,
        str(_tool("attestation/verify_measured_runner_transcript.py")),
        "--run-package",
        str(run_root),
        "--retained-challenge",
        str(retained_challenge),
        "--policy",
        policies["transcript_appraisal"]["path"],
    ]
    appraisal = [
        policies["evidence_verifier"]["path"],
        "--evidence-pack",
        str(evidence_root),
        "--policy",
        policies["composite_appraisal"]["path"],
        "--backend",
        BACKEND,
        "--expected-challenge-file",
        str(retained_challenge),
        "--expected-start-challenge-sha256",
        "<challenge-nonce-from-retained-challenge>",
        "--expected-result-binding-sha256",
        "<result-binding-from-verified-transcript>",
    ]
    replay_db = Path(outputs["replay_db"])
    signer = _tool("azure/managed_hsm_signer.py")
    receipt = [
        sys.executable,
        str(_tool("tools/trusted_compute_receipt.py")),
        "issue",
        "--bundle",
        str(bundle),
        "--artifact-root",
        str(run_root),
        "--backend",
        BACKEND,
        "--evidence-pack",
        str(evidence_root),
        "--evidence-verifier",
        policies["evidence_verifier"]["path"],
        "--evidence-policy",
        policies["composite_appraisal"]["path"],
        "--retained-challenge",
        str(retained_challenge),
        "--replay-db",
        str(replay_db),
        "--signer-command",
        str(signer),
        "--signer-arg=--key-uri",
        f"--signer-arg={hsm['key_uri']}",
        "--signer-arg=--public-key",
        f"--signer-arg={hsm['public_key']['path']}",
        "--verifier-key-id",
        hsm["key_id"],
        "--public-key",
        hsm["public_key"]["path"],
        "--out",
        outputs["receipt"],
    ]
    if review["registered_invocation"] is None:
        registry: list[str] | None = None
        lean: list[str] | None = None
    else:
        registry = [
            sys.executable,
            str(_tool("tools/generate_trusted_compute_registry.py")),
            outputs["receipt"],
            "--out",
            outputs["registry_candidate"],
            "--key-manifest",
            hsm["key_manifest"]["path"],
            "--public-key",
            hsm["public_key"]["path"],
        ]
        lean = [
            sys.executable,
            str(_tool("tools/generate_trusted_compute_lean.py")),
            outputs["receipt"],
            "--namespace",
            review["namespace"],
            "--registered-invocation",
            review["registered_invocation"],
            "--out",
            outputs["lean_candidate"],
            "--key-manifest",
            hsm["key_manifest"]["path"],
            "--public-key",
            hsm["public_key"]["path"],
        ]
    return {
        "accepted": False,
        "campaign_config_sha256": config_hash,
        "challenge_lifetime_contract": {
            "evidence_collection_margin_seconds": EVIDENCE_COLLECTION_MARGIN_SECONDS,
            "one_shard_must_finish_before_expiry": True,
            "ttl_seconds": config["challenge_ttl_seconds"],
        },
        "classification": "reviewable_dry_run_no_commands_executed",
        "manual_security_boundaries": [
            {
                "after": "challenge_created",
                "artifact": config["handoffs"]["worker_stage_manifest"],
                "reason": (
                    "No reviewed remote package/challenge transport or secure-input-release "
                    "channel exists. Stage the exact workload archive, challenge, and two "
                    "guest policy files through an operator-approved private channel, then "
                    "provide the canonical handoff. The guest itself safely extracts the archive."
                ),
            },
            {
                "after": "worker_certificate_archive_created",
                "artifacts": [
                    config["handoffs"]["returned_certificate_archive"],
                    config["handoffs"]["returned_worker_completion"],
                ],
                "reason": (
                    "No reviewed automatic exfiltration channel exists. Return the immutable "
                    "certificate archive and worker completion manifest through an "
                    "operator-controlled channel."
                ),
            },
            {
                "after": "review_candidates_generated",
                "artifact": outputs["registry_candidate"],
                "reason": (
                    "Lean production key pins and the live receipt registry require a separate "
                    "human-reviewed source change; this orchestrator never edits them."
                ),
            },
        ],
        "steps": [
            {"id": "deploy", "execution": "operator_local", "argv": deploy},
            {"id": "challenge", "execution": "operator_local_off_vm", "argv": challenge},
            {
                "id": "stage_worker",
                "execution": "manual_prerequisite",
                "argv": None,
                "operator_action": (
                    "after authenticated transfer and guest-side digest comparison, run "
                    "record-worker-stage-handoff --confirm-exact-staging, copy that exact "
                    "manifest to worker.stage_manifest, then run ack-worker-stage"
                ),
                "output": config["handoffs"]["worker_stage_manifest"],
            },
            {
                "id": "extract_pinned_workload_package",
                "execution": "guest_internal_safe_archive_extraction",
                "argv": None,
                "input": worker["workload_package"],
                "output": worker["artifact_root"],
            },
            {"id": "measured_runner", "execution": "guest_local_root", "argv": runner},
            {"id": "no_reset_evidence_collection", "execution": "guest_local_root", "argv": collector},
            {
                "id": "return_certificate_archive",
                "execution": "manual_prerequisite",
                "argv": None,
                "completion": config["handoffs"]["returned_worker_completion"],
                "output": config["handoffs"]["returned_certificate_archive"],
            },
            {"id": "transcript_verify", "execution": "operator_local", "argv": transcript},
            {"id": "hardware_appraise", "execution": "operator_local", "argv": appraisal},
            {"id": "receipt_issue_hsm", "execution": "operator_local", "argv": receipt},
            {"id": "registry_review_candidate", "execution": "operator_local", "argv": registry},
            {"id": "lean_review_candidate", "execution": "operator_local", "argv": lean},
        ],
    }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, content: bytes, mode: int = 0o600, *, replace: bool) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise OrchestratorError(f"refusing symlink output: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(content)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OrchestratorError(f"short write for {path}")
            view = view[count:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if not replace and path.exists():
            raise OrchestratorError(f"refusing to replace existing output: {path}")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _state_path(config: dict[str, Any]) -> Path:
    return Path(config["outputs"]["state"])


@contextmanager
def _operator_lock(config: dict[str, Any], *, exclusive: bool) -> Iterator[None]:
    """Serialize operator state transitions without trusting a shell lock."""

    state_path = _state_path(config)
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = state_path.with_name(f".{state_path.name}.lock")
    if lock_path.is_symlink():
        raise OrchestratorError(f"refusing symlink operator lock: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OrchestratorError("operator lock must be one regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def initialize_state(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    state_path = _state_path(config)
    if state_path.exists():
        return load_state(config, config_hash)
    state = {
        "accepted": False,
        "campaign_config_sha256": config_hash,
        "campaign_id": config["campaign_id"],
        "history": [
            {
                "at_utc": _now(),
                "from": None,
                "record_sha256": None,
                "to": "initialized",
            }
        ],
        "kind": STATE_KIND,
        "records": {},
        "schema_version": SCHEMA_VERSION,
        "stage": "initialized",
    }
    _atomic_write(state_path, canonical_json_bytes(state), replace=False)
    return state


def load_state(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    state, _canonical = _canonical_load(_state_path(config), "operator state")
    state = _exact(state, STATE_KEYS, "operator state")
    if (
        state["kind"] != STATE_KIND
        or state["schema_version"] != SCHEMA_VERSION
        or state["accepted"] is not False
        or state["campaign_id"] != config["campaign_id"]
        or state["campaign_config_sha256"] != config_hash
        or not isinstance(state["history"], list)
        or not isinstance(state["records"], dict)
        or not isinstance(state["stage"], str)
    ):
        raise OrchestratorError("operator state does not belong to this exact campaign config")
    return state


def _transition(
    config: dict[str, Any],
    config_hash: str,
    expected: str,
    target: str,
    *,
    record_name: str | None = None,
    record_sha256: str | None = None,
) -> dict[str, Any]:
    state = load_state(config, config_hash)
    if state["stage"] != expected:
        raise OrchestratorError(f"transition requires stage {expected!r}, found {state['stage']!r}")
    if record_name is not None:
        if record_name in state["records"]:
            raise OrchestratorError(f"state record already exists: {record_name}")
        state["records"][record_name] = record_sha256
    state["history"].append(
        {
            "at_utc": _now(),
            "from": expected,
            "record_sha256": record_sha256,
            "to": target,
        }
    )
    state["stage"] = target
    _atomic_write(_state_path(config), canonical_json_bytes(state), replace=True)
    return state


def _require_recorded_file(
    config: dict[str, Any], config_hash: str, record_name: str, path: Path
) -> str:
    state = load_state(config, config_hash)
    expected = state["records"].get(record_name)
    if not isinstance(expected, str) or HEX256_RE.fullmatch(expected) is None:
        raise OrchestratorError(f"operator state lacks immutable record {record_name}")
    actual, _size = _sha256_file(path)
    if actual != expected:
        raise OrchestratorError(f"{record_name} file changed after its state transition")
    return actual


def _environment(
    *,
    include_azure_identity: bool = False,
    include_nvidia_service_key: bool = False,
) -> dict[str, str]:
    # Start from constants rather than inheriting PATH/HOME.  Azure CLI token
    # state and managed-identity credentials are capabilities and must not be
    # exposed to the independently supplied appraisers or source generators.
    allowed: set[str] = set()
    if include_azure_identity:
        allowed.update(
            {
                "AZURE_CLIENT_ID",
                "AZURE_CONFIG_DIR",
                "AZURE_FEDERATED_TOKEN_FILE",
                "AZURE_TENANT_ID",
                "HOME",
                "IDENTITY_ENDPOINT",
                "IDENTITY_HEADER",
                "IMDS_ENDPOINT",
                "MSI_ENDPOINT",
                "MSI_SECRET",
            }
        )
    if include_nvidia_service_key:
        # Forward only to the reviewed in-guest collection process.  It is never
        # copied into state, plans, manifests, command arguments, or output.
        allowed.add("NV_ATTESTATION_SERVICE_KEY")
    result = {key: value for key, value in os.environ.items() if key in allowed}
    result.update(
        {
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TZ": "UTC",
        }
    )
    return result


CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[bytes]]


def _default_run(argv: Sequence[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    command = list(argv)
    collector = str(_tool("attestation/collect_azure_measured_evidence.py"))
    measured_runner = str(_tool("azure/measured_runner.py"))
    azure_deployer = str(_tool("azure/ncc_h100.py"))
    receipt_issuer = str(_tool("tools/trusted_compute_receipt.py"))
    include_azure_identity = (
        len(command) >= 2 and command[1] in {azure_deployer, receipt_issuer}
    )
    include_nvidia_service_key = (
        len(command) >= 2
        and (
            command[1] == measured_runner
            or (
                command[1] == collector
                and "--gpu-verifier" in command
                and command[command.index("--gpu-verifier") + 1] == "remote"
            )
        )
    )
    try:
        return subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
            env=_environment(
                include_azure_identity=include_azure_identity,
                include_nvidia_service_key=include_nvidia_service_key,
            ),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OrchestratorError(f"command could not complete: {error}") from error


def _run_json(argv: Sequence[str], timeout: int, runner: CommandRunner) -> dict[str, Any]:
    completed = runner(argv, timeout)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise OrchestratorError(f"child command failed with status {completed.returncode}: {detail}")
    try:
        value = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrchestratorError("child command did not emit one JSON object") from error
    if not isinstance(value, dict):
        raise OrchestratorError("child command JSON is not an object")
    return value


def _validate_deployment_result(result: dict[str, Any], config: dict[str, Any]) -> None:
    azure = config["azure"]
    vms = result.get("virtual_machines")
    if (
        result.get("accepted") is not True
        or result.get("classification") != "azure_ncc_h100_vms_created"
        or result.get("resolved_image") != azure["image"]
        or result.get("resource_group") != azure["resource_group"]
        or result.get("subnet_id") != azure["subnet_id"]
        or result.get("subnet_default_outbound_access") is not False
        or result.get("public_ip_addresses") is not False
        or result.get("attestation_collected") is not False
        or result.get("resources_proven_attested") != 0
        or not isinstance(vms, list)
        or len(vms) != 1
    ):
        raise OrchestratorError("Azure deploy adapter did not confirm the exact private VM set")
    vm = vms[0]
    if (
        not isinstance(vm, dict)
        or vm.get("sku") != VM_SIZE
        or vm.get("image") != azure["image"]
        or vm.get("provisioning_state") != "Succeeded"
        or vm.get("security_type") != "ConfidentialVM"
        or vm.get("secure_boot_enabled") is not True
        or vm.get("vtpm_enabled") is not True
        or vm.get("public_ip_address_resource_id") is not None
        or not isinstance(vm.get("id"), str)
        or not isinstance(vm.get("private_ip_address"), str)
    ):
        raise OrchestratorError("Azure deploy adapter returned an unreviewed VM configuration")


def _load_recorded_deployment(
    config: dict[str, Any], config_hash: str
) -> dict[str, Any]:
    path = Path(config["outputs"]["deployment_record"])
    _require_recorded_file(
        config, config_hash, "deployment_record_sha256", path
    )
    value, _canonical = _canonical_load(path, "deployment record")
    _validate_deployment_result(value, config)
    return value


def deploy(config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run) -> dict[str, Any]:
    state = load_state(config, config_hash)
    if state["stage"] == "azure_deployed":
        return _load_recorded_deployment(config, config_hash)
    if state["stage"] != "initialized":
        raise OrchestratorError(
            f"deployment cannot run from {state['stage']!r}; "
            "reconcile ambiguous state first"
        )
    plan = command_plan(config, config_hash)
    argv = next(step["argv"] for step in plan["steps"] if step["id"] == "deploy")
    _transition(config, config_hash, "initialized", "azure_deployment_in_progress")
    try:
        result = _run_json(argv, 3600, runner)
        _validate_deployment_result(result, config)
        destination = Path(config["outputs"]["deployment_record"])
        content = canonical_json_bytes(result)
        _atomic_write(destination, content, replace=False)
        digest = hashlib.sha256(content).hexdigest()
        _transition(
            config,
            config_hash,
            "azure_deployment_in_progress",
            "azure_deployed",
            record_name="deployment_record_sha256",
            record_sha256=digest,
        )
        return result
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "azure_deployment_in_progress",
                "azure_deployment_failed_or_unknown_manual_reconciliation_required",
            )
        except Exception:
            pass
        raise


def reconcile_deployment(
    config: dict[str, Any], config_hash: str
) -> dict[str, Any]:
    """Adopt only an independently inspected exact H100 deployment record."""

    state = load_state(config, config_hash)
    if state["stage"] != (
        "azure_deployment_failed_or_unknown_manual_reconciliation_required"
    ):
        raise OrchestratorError("deployment reconciliation is not currently required")
    path = Path(config["outputs"]["deployment_record"])
    result, canonical = _canonical_load(
        path, "independently inspected deployment record"
    )
    _validate_deployment_result(result, config)
    _transition(
        config,
        config_hash,
        state["stage"],
        "azure_deployed",
        record_name="deployment_record_sha256",
        record_sha256=hashlib.sha256(canonical).hexdigest(),
    )
    return result


def _validate_challenge(config: dict[str, Any]) -> dict[str, Any]:
    challenge = load_challenge(_challenge_path(config))
    if (
        challenge["campaign_id"] != config["campaign_id"]
        or challenge["shard_index"] != config["challenge"]["shard_index"]
    ):
        raise OrchestratorError("challenge identity differs from this campaign")
    require_current_challenge_window(challenge)
    return challenge


def _adopt_pinned_portfolio_challenge(config: dict[str, Any]) -> dict[str, Any]:
    challenge_source = config["challenge"]
    if challenge_source["mode"] != "pinned_portfolio_handoff_v1":
        raise OrchestratorError("challenge source is not a pinned portfolio handoff")
    pin, source = _file_pin(
        challenge_source["pin"], "pinned portfolio challenge"
    )
    raw = _read_regular_once(source, "pinned portfolio challenge")
    try:
        parsed = parse_json_bytes(raw, "pinned portfolio challenge")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OrchestratorError(
            f"cannot capture pinned portfolio challenge: {error}"
        ) from error
    if (
        hashlib.sha256(raw).hexdigest() != pin["sha256"]
        or len(raw) != pin["size_bytes"]
        or raw not in (canonical_json_bytes(parsed), canonical_json_bytes(parsed) + b"\n")
    ):
        raise OrchestratorError("pinned portfolio challenge changed while captured")
    destination = _challenge_path(config)
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError as error:
        raise OrchestratorError(
            "pinned challenge destination already exists; reconciliation is required"
        ) from error
    _atomic_write(destination, raw, replace=False)
    challenge = _validate_challenge(config)
    copied_hash, copied_size = _sha256_file(destination)
    if (copied_hash, copied_size) != (pin["sha256"], pin["size_bytes"]):
        raise OrchestratorError("adopted portfolio challenge differs from its exact pin")
    return challenge


def create_challenge_step(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    state = load_state(config, config_hash)
    if state["stage"] == "challenge_created_awaiting_manual_worker_stage":
        _require_recorded_file(
            config,
            config_hash,
            "retained_challenge_sha256",
            _challenge_path(config),
        )
        return _validate_challenge(config)
    if state["stage"] != "azure_deployed":
        raise OrchestratorError("challenge generation requires azure_deployed")
    _load_recorded_deployment(config, config_hash)
    plan = command_plan(config, config_hash)
    argv = next(step["argv"] for step in plan["steps"] if step["id"] == "challenge")
    _transition(config, config_hash, "azure_deployed", "challenge_generation_in_progress")
    try:
        if config["challenge"]["mode"] == "pinned_portfolio_handoff_v1":
            adopted = _adopt_pinned_portfolio_challenge(config)
            result = {
                "accepted": True,
                "classification": "exact_pinned_portfolio_challenge_adopted_off_vm",
                "count": 1,
                "nonce": adopted["nonce"],
                "ttl_seconds": config["challenge_ttl_seconds"],
            }
        else:
            if argv is None:
                raise OrchestratorError("fresh challenge command is absent")
            result = _run_json(argv, 60, runner)
            if (
                result.get("accepted") is not True
                or result.get("count") != 1
                or result.get("ttl_seconds") != config["challenge_ttl_seconds"]
            ):
                raise OrchestratorError(
                    "challenge generator did not persist one fresh challenge"
                )
            _validate_challenge(config)
        digest, _ = _sha256_file(_challenge_path(config))
        _transition(
            config,
            config_hash,
            "challenge_generation_in_progress",
            "challenge_created_awaiting_manual_worker_stage",
            record_name="retained_challenge_sha256",
            record_sha256=digest,
        )
        return result
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "challenge_generation_in_progress",
                "challenge_generation_failed_or_unknown_manual_reconciliation_required",
            )
        except Exception:
            pass
        raise


def reconcile_challenge(
    config: dict[str, Any], config_hash: str
) -> dict[str, Any]:
    """Adopt only the exact still-live challenge retained after an ambiguity."""

    state = load_state(config, config_hash)
    if state["stage"] != (
        "challenge_generation_failed_or_unknown_manual_reconciliation_required"
    ):
        raise OrchestratorError("challenge reconciliation is not currently required")
    challenge = _validate_challenge(config)
    digest, _ = _sha256_file(_challenge_path(config))
    _transition(
        config,
        config_hash,
        state["stage"],
        "challenge_created_awaiting_manual_worker_stage",
        record_name="retained_challenge_sha256",
        record_sha256=digest,
    )
    return challenge


def _stage_manifest_expected(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    deployment_path = Path(config["outputs"]["deployment_record"])
    deployment, deployment_bytes = _canonical_load(deployment_path, "deployment record")
    challenge_path = _challenge_path(config)
    challenge = _validate_challenge(config)
    challenge_hash, _ = _sha256_file(challenge_path)
    vm = deployment["virtual_machines"][0]
    worker = config["worker"]
    return {
        "campaign_config_sha256": config_hash,
        "challenge_nonce": challenge["nonce"],
        "challenge_sha256": challenge_hash,
        "deployment_record_sha256": hashlib.sha256(deployment_bytes).hexdigest(),
        "immutable_image": config["azure"]["image"],
        "job_spec_sha256": config["workload"]["job_spec"]["sha256"],
        "kind": STAGE_HANDOFF_KIND,
        "schema_version": 1,
        "status": "operator_confirmed_exact_package_and_challenge_staged",
        "vm_id": vm["id"],
        "vm_private_ip": vm["private_ip_address"],
        "worker_artifact_root": worker["artifact_root"],
        "worker_input_bindings": {
            "challenge": {
                "path": worker["challenge"],
                "sha256": challenge_hash,
            },
            "job_spec": {
                "path": worker["job_spec"],
                "sha256": config["workload"]["job_spec"]["sha256"],
                "size_bytes": config["workload"]["job_spec"]["size_bytes"],
            },
            "nvidia_policy": {
                "path": worker["nvidia_policy"],
                "sha256": config["policies"]["nvidia"]["sha256"],
                "size_bytes": config["policies"]["nvidia"]["size_bytes"],
            },
            "transcript_appraisal_policy": {
                "path": worker["transcript_appraisal_policy"],
                "sha256": config["policies"]["transcript_appraisal"]["sha256"],
                "size_bytes": config["policies"]["transcript_appraisal"]["size_bytes"],
            },
            "workload_package": {
                "path": worker["workload_package"],
                "sha256": config["workload"]["package"]["sha256"],
                "size_bytes": config["workload"]["package"]["size_bytes"],
            },
        },
        "worker_output_paths": {
            "certificate_archive": worker["certificate_archive"],
            "certificate_package": worker["certificate_package"],
            "completion_manifest": worker["completion_manifest"],
            "run_package": worker["run_package"],
        },
        "worker_stage_manifest_path": worker["stage_manifest"],
        "workload_package_sha256": config["workload"]["package"]["sha256"],
    }


def _validate_worker_manifest_local(
    manifest: dict[str, Any], config: dict[str, Any], config_hash: str
) -> None:
    """Validate the operator handoff using only staged guest-side material."""

    worker = config["worker"]
    if (
        manifest.get("kind") != STAGE_HANDOFF_KIND
        or manifest.get("schema_version") != 1
        or manifest.get("campaign_config_sha256") != config_hash
        or manifest.get("immutable_image") != config["azure"]["image"]
        or manifest.get("job_spec_sha256") != config["workload"]["job_spec"]["sha256"]
        or manifest.get("workload_package_sha256") != config["workload"]["package"]["sha256"]
        or manifest.get("status")
        != "operator_confirmed_exact_package_and_challenge_staged"
        or manifest.get("worker_artifact_root") != worker["artifact_root"]
        or manifest.get("worker_output_paths")
        != {
            "certificate_archive": worker["certificate_archive"],
            "certificate_package": worker["certificate_package"],
            "completion_manifest": worker["completion_manifest"],
            "run_package": worker["run_package"],
        }
        or manifest.get("worker_stage_manifest_path") != worker["stage_manifest"]
    ):
        raise OrchestratorError("worker-stage handoff does not bind this guest campaign")
    expected_inputs = {
        "challenge": {
            "path": worker["challenge"],
            "sha256": manifest.get("challenge_sha256"),
        },
        "job_spec": {
            "path": worker["job_spec"],
            "sha256": config["workload"]["job_spec"]["sha256"],
            "size_bytes": config["workload"]["job_spec"]["size_bytes"],
        },
        "nvidia_policy": {
            "path": worker["nvidia_policy"],
            "sha256": config["policies"]["nvidia"]["sha256"],
            "size_bytes": config["policies"]["nvidia"]["size_bytes"],
        },
        "transcript_appraisal_policy": {
            "path": worker["transcript_appraisal_policy"],
            "sha256": config["policies"]["transcript_appraisal"]["sha256"],
            "size_bytes": config["policies"]["transcript_appraisal"]["size_bytes"],
        },
        "workload_package": {
            "path": worker["workload_package"],
            "sha256": config["workload"]["package"]["sha256"],
            "size_bytes": config["workload"]["package"]["size_bytes"],
        },
    }
    if manifest.get("worker_input_bindings") != expected_inputs:
        raise OrchestratorError("worker-stage handoff has inconsistent guest input bindings")


def record_worker_stage_handoff(
    config: dict[str, Any], config_hash: str, *, confirmed: bool
) -> dict[str, Any]:
    """Persist the operator's explicit, manual staging confirmation."""

    state = load_state(config, config_hash)
    if state["stage"] != "challenge_created_awaiting_manual_worker_stage":
        raise OrchestratorError("worker-stage confirmation is not the next operator action")
    if not confirmed:
        raise OrchestratorError(
            "worker staging must be manually checked before recording the handoff"
        )
    _require_recorded_file(
        config,
        config_hash,
        "deployment_record_sha256",
        Path(config["outputs"]["deployment_record"]),
    )
    _require_recorded_file(
        config,
        config_hash,
        "retained_challenge_sha256",
        _challenge_path(config),
    )
    manifest = _stage_manifest_expected(config, config_hash)
    canonical = canonical_json_bytes(manifest)
    destination = Path(config["handoffs"]["worker_stage_manifest"])
    if destination.exists():
        existing, existing_bytes = _canonical_load(
            destination, "worker-stage handoff"
        )
        if existing != manifest:
            raise OrchestratorError(
                "existing worker-stage handoff differs from this campaign"
            )
        canonical = existing_bytes
    else:
        _atomic_write(destination, canonical, replace=False)
    return {
        "accepted": False,
        "classification": "manual_worker_stage_confirmation_recorded_pending_ack",
        "manifest_path": str(destination),
        "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def acknowledge_worker_stage(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    state = load_state(config, config_hash)
    path = Path(config["handoffs"]["worker_stage_manifest"])
    if state["stage"] == "worker_stage_confirmed":
        _require_recorded_file(
            config, config_hash, "worker_stage_manifest_sha256", path
        )
        manifest, _ = _canonical_load(path, "worker-stage handoff")
        return manifest
    if state["stage"] != "challenge_created_awaiting_manual_worker_stage":
        raise OrchestratorError("worker-stage acknowledgment is not the next transition")
    _require_recorded_file(
        config,
        config_hash,
        "deployment_record_sha256",
        Path(config["outputs"]["deployment_record"]),
    )
    _require_recorded_file(
        config,
        config_hash,
        "retained_challenge_sha256",
        _challenge_path(config),
    )
    manifest, canonical = _canonical_load(path, "worker-stage handoff")
    expected = _stage_manifest_expected(config, config_hash)
    if manifest != expected:
        raise OrchestratorError("worker-stage handoff does not bind the exact deployment/package/challenge")
    digest = hashlib.sha256(canonical).hexdigest()
    _transition(
        config,
        config_hash,
        "challenge_created_awaiting_manual_worker_stage",
        "worker_stage_confirmed",
        record_name="worker_stage_manifest_sha256",
        record_sha256=digest,
    )
    return manifest


def run_worker_local(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    """Run only on the staged VM; this does not mutate the operator state."""

    manifest_path = Path(config["worker"]["stage_manifest"])
    manifest, manifest_bytes = _canonical_load(manifest_path, "worker-stage handoff")
    _validate_worker_manifest_local(manifest, config, config_hash)
    worker = config["worker"]
    local_package_hash, local_package_size = _sha256_file(Path(worker["workload_package"]))
    if (
        local_package_hash != config["workload"]["package"]["sha256"]
        or local_package_size != config["workload"]["package"]["size_bytes"]
    ):
        raise OrchestratorError("staged workload package differs from the operator pin")
    # The authenticated handoff stages only the immutable archive.  Extracting
    # it here prevents an unrelated pre-expanded tree from being substituted.
    extract_archive(Path(worker["workload_package"]), Path(worker["artifact_root"]))
    local_job_hash, local_job_size = _sha256_file(Path(worker["job_spec"]))
    if (
        local_job_hash != config["workload"]["job_spec"]["sha256"]
        or local_job_size != config["workload"]["job_spec"]["size_bytes"]
    ):
        raise OrchestratorError("staged job spec differs from the operator pin")
    local_job_value, local_job_canonical = _canonical_load(
        Path(worker["job_spec"]), "staged measured job spec"
    )
    try:
        local_job = validate_job_spec(local_job_value)
    except Exception as error:
        raise OrchestratorError(f"staged measured H100 job rejected: {error}") from error
    if (
        hashlib.sha256(local_job_canonical).hexdigest() != local_job_hash
        or local_job["backend"] != BACKEND
        or local_job["target_profile"]["profile_id"] != TARGET_PROFILE_ID
        or local_job["trust_profile"]["profile_id"] != TRUST_PROFILE_ID
        or local_job["runner_policy"]["sha256"]
        != config["policies"]["runner"]["sha256"]
    ):
        raise OrchestratorError("staged job does not retain the production H100 bindings")
    invocation = config["lean_review"]["registered_invocation"]
    if invocation is not None:
        try:
            registered_expected = registered_invocation_expected(invocation)
            registered_backend = registered_invocation_backend(invocation)
        except Exception as error:
            raise OrchestratorError(
                "staged registered_invocation is not source-supported"
            ) from error
        if registered_backend != BACKEND or any(
            registered_expected.get(name) != value
            for name, value in {
                "algorithm_hash": local_job["algorithm"]["definition_sha256"],
                "algorithm_id": local_job["algorithm"]["algorithm_id"],
                "domain_hash": local_job["domain_coverage"]["canonical_sha256"],
                "input_hash": local_job["input_artifact"]["sha256"],
                "parameters_hash": local_job["parameters"]["canonical_sha256"],
            }.items()
        ):
            raise OrchestratorError(
                "staged job differs from the selected closed H100 invocation"
            )
    for worker_name, policy_name in (
        ("nvidia_policy", "nvidia"),
        ("transcript_appraisal_policy", "transcript_appraisal"),
    ):
        policy_path = Path(worker[worker_name])
        policy_hash, policy_size = _sha256_file(policy_path)
        expected_policy = config["policies"][policy_name]
        if (
            policy_hash != expected_policy["sha256"]
            or policy_size != expected_policy["size_bytes"]
        ):
            raise OrchestratorError(
                f"staged {worker_name.replace('_', ' ')} differs from the operator pin"
            )
    challenge = load_challenge(Path(worker["challenge"]))
    challenge_hash, _challenge_size = _sha256_file(Path(worker["challenge"]))
    if (
        challenge["nonce"] != manifest["challenge_nonce"]
        or challenge_hash != manifest["challenge_sha256"]
    ):
        raise OrchestratorError("staged challenge differs from the retained challenge handoff")
    _issued, expires = require_current_challenge_window(challenge)
    required_remaining = (
        local_job["command"]["timeout_seconds"]
        + local_job["gpu_pre_run_gate"]["timeout_seconds"]
        + EVIDENCE_COLLECTION_MARGIN_SECONDS
    )
    remaining = (expires - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if remaining <= required_remaining:
        raise OrchestratorError(
            "staged challenge no longer has enough lifetime for one complete measured shard; "
            "generate a fresh challenge and repeat the authenticated ingress handoff"
        )
    plan = command_plan(config, config_hash)
    runner_argv = next(step["argv"] for step in plan["steps"] if step["id"] == "measured_runner")
    collector_argv = next(
        step["argv"] for step in plan["steps"] if step["id"] == "no_reset_evidence_collection"
    )
    run_result = _run_json(runner_argv, 7 * 86400, runner)
    if run_result.get("accepted") is not False or run_result.get("backend") != BACKEND:
        raise OrchestratorError("measured runner crossed or changed its pending-appraisal boundary")
    collection_result = _run_json(collector_argv, 7200, runner)
    if (
        collection_result.get("accepted") is not False
        or collection_result.get("collection_protocol") != COLLECTION_PROTOCOL
    ):
        raise OrchestratorError("measured collector crossed or changed its trust boundary")
    archive = Path(worker["certificate_archive"])
    create_archive(Path(worker["certificate_package"]), archive)
    archive_hash, archive_size = _sha256_file(archive)
    completion = {
        "archive_sha256": archive_hash,
        "archive_size_bytes": archive_size,
        "campaign_config_sha256": config_hash,
        "collection_protocol": COLLECTION_PROTOCOL,
        "job_spec_sha256": config["workload"]["job_spec"]["sha256"],
        "kind": WORKER_COMPLETION_KIND,
        "result_binding_sha256": collection_result["result_binding_sha256"],
        "schema_version": 1,
        "statement_sha256": collection_result["statement_sha256"],
        "status": "certificate_archive_ready_for_operator_return",
        "worker_stage_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    _atomic_write(
        Path(worker["completion_manifest"]), canonical_json_bytes(completion), replace=False
    )
    return completion


def _verify_returned_completion(
    config: dict[str, Any], config_hash: str
) -> tuple[dict[str, Any], bytes, Path]:
    completion_path = Path(config["handoffs"]["returned_worker_completion"])
    completion, canonical = _canonical_load(completion_path, "returned worker completion")
    expected_keys = {
        "archive_sha256",
        "archive_size_bytes",
        "campaign_config_sha256",
        "collection_protocol",
        "job_spec_sha256",
        "kind",
        "result_binding_sha256",
        "schema_version",
        "statement_sha256",
        "status",
        "worker_stage_manifest_sha256",
    }
    completion = _exact(completion, expected_keys, "worker completion")
    _require_recorded_file(
        config,
        config_hash,
        "worker_stage_manifest_sha256",
        Path(config["handoffs"]["worker_stage_manifest"]),
    )
    _require_recorded_file(
        config,
        config_hash,
        "retained_challenge_sha256",
        _challenge_path(config),
    )
    stage_hash, _ = _sha256_file(Path(config["handoffs"]["worker_stage_manifest"]))
    if (
        completion["kind"] != WORKER_COMPLETION_KIND
        or completion["schema_version"] != 1
        or completion["campaign_config_sha256"] != config_hash
        or completion["collection_protocol"] != COLLECTION_PROTOCOL
        or completion["job_spec_sha256"] != config["workload"]["job_spec"]["sha256"]
        or completion["worker_stage_manifest_sha256"] != stage_hash
        or completion["status"] != "certificate_archive_ready_for_operator_return"
    ):
        raise OrchestratorError("returned worker completion has inconsistent bindings")
    _digest(completion["archive_sha256"], "returned archive hash")
    _digest(completion["statement_sha256"], "returned statement hash")
    _digest(completion["result_binding_sha256"], "returned result binding")
    archive = Path(config["handoffs"]["returned_certificate_archive"])
    archive_hash, archive_size = _sha256_file(archive)
    if archive_hash != completion["archive_sha256"] or archive_size != completion[
        "archive_size_bytes"
    ]:
        raise OrchestratorError("returned certificate archive differs from worker completion")
    return completion, canonical, archive


def ingest_returned_package(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    state = load_state(config, config_hash)
    transcript_path = Path(config["outputs"]["transcript_report"])
    if state["stage"] == "certificate_package_verified":
        _require_recorded_file(
            config, config_hash, "transcript_report_sha256", transcript_path
        )
        report, _ = _canonical_load(transcript_path, "transcript report")
        return report
    if state["stage"] != "worker_stage_confirmed":
        raise OrchestratorError("returned package ingestion requires worker_stage_confirmed")
    completion, completion_bytes, archive = _verify_returned_completion(config, config_hash)
    _transition(
        config,
        config_hash,
        "worker_stage_confirmed",
        "certificate_ingestion_in_progress",
    )
    try:
        destination = Path(config["outputs"]["extracted_certificate_package"])
        extract_archive(archive, destination)
        run_root = destination / "bundle-root"
        evidence_root = destination / "evidence"
        bundle_path = run_root / "run-bundle.json"
        if not run_root.is_dir() or not evidence_root.is_dir() or not bundle_path.is_file():
            raise OrchestratorError("returned certificate package has the wrong layout")
        bundle, _bundle_bytes = _canonical_load(bundle_path, "returned run bundle")
        checked = verify_run_bundle.verify_bundle(bundle, artifact_root=run_root)
        if (
            checked["statement_sha256"] != completion["statement_sha256"]
            or not checked["artifacts_verified"]
        ):
            raise OrchestratorError("returned run bundle does not match worker completion")
        plan = command_plan(config, config_hash)
        transcript_argv = next(
            step["argv"] for step in plan["steps"] if step["id"] == "transcript_verify"
        )
        report = _run_json(transcript_argv, 600, runner)
        if (
            report.get("accepted") is not False
            or report.get("classification")
            != "transcript_valid_pending_authenticated_hardware_appraisal"
            or report.get("statement_sha256") != completion["statement_sha256"]
            or report.get("result_binding_sha256") != completion["result_binding_sha256"]
        ):
            raise OrchestratorError(
                "independent transcript verification returned inconsistent bindings"
            )
        report_bytes = canonical_json_bytes(report)
        _atomic_write(transcript_path, report_bytes, replace=False)
        if hashlib.sha256(completion_bytes).hexdigest() != _sha256_file(
            Path(config["handoffs"]["returned_worker_completion"])
        )[0]:
            raise OrchestratorError("worker completion changed during ingestion")
        _transition(
            config,
            config_hash,
            "certificate_ingestion_in_progress",
            "certificate_package_verified",
            record_name="transcript_report_sha256",
            record_sha256=hashlib.sha256(report_bytes).hexdigest(),
        )
        return report
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "certificate_ingestion_in_progress",
                "certificate_ingestion_failed_or_unknown_manual_reconciliation_required",
            )
        except Exception:
            pass
        raise


def appraise(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    state = load_state(config, config_hash)
    report_path = Path(config["outputs"]["appraisal_report"])
    if state["stage"] == "hardware_appraisal_prechecked":
        _require_recorded_file(
            config, config_hash, "appraisal_report_sha256", report_path
        )
        report, _ = _canonical_load(report_path, "appraisal report")
        return report
    if state["stage"] != "certificate_package_verified":
        raise OrchestratorError("hardware appraisal requires a verified returned package")
    _require_recorded_file(
        config,
        config_hash,
        "transcript_report_sha256",
        Path(config["outputs"]["transcript_report"]),
    )
    completion, _bytes, _archive = _verify_returned_completion(config, config_hash)
    plan = command_plan(config, config_hash)
    argv = next(step["argv"] for step in plan["steps"] if step["id"] == "hardware_appraise")
    argv = [
        completion["result_binding_sha256"] if item == "<result-binding-from-verified-transcript>" else
        load_challenge(_challenge_path(config))["nonce"]
        if item == "<challenge-nonce-from-retained-challenge>" else item
        for item in argv
    ]
    _transition(
        config,
        config_hash,
        "certificate_package_verified",
        "hardware_appraisal_in_progress",
    )
    try:
        report = _run_json(argv, 3600, runner)
        if (
            report.get("accepted") is not True
            or report.get("backend") != BACKEND
            or report.get("result_binding_sha256") != completion["result_binding_sha256"]
            or report.get("start_challenge_sha256")
            != load_challenge(_challenge_path(config))["nonce"]
        ):
            raise OrchestratorError("hardware appraiser did not accept the exact measured bindings")
        report_bytes = canonical_json_bytes(report)
        _atomic_write(report_path, report_bytes, replace=False)
        _transition(
            config,
            config_hash,
            "hardware_appraisal_in_progress",
            "hardware_appraisal_prechecked",
            record_name="appraisal_report_sha256",
            record_sha256=hashlib.sha256(report_bytes).hexdigest(),
        )
        return report
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "hardware_appraisal_in_progress",
                "hardware_appraisal_failed_or_unknown_manual_reconciliation_required",
            )
        except Exception:
            pass
        raise


def issue_receipt(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    state = load_state(config, config_hash)
    receipt_path = Path(config["outputs"]["receipt"])
    if state["stage"] == "receipt_issued_pending_source_review":
        _require_recorded_file(
            config, config_hash, "receipt_file_sha256", receipt_path
        )
        receipt, _ = _canonical_load(receipt_path, "trusted-compute receipt")
        return {
            "accepted_for_lean": False,
            "backend": receipt.get("backend"),
            "receipt_issued": True,
            "receipt_sha256": receipt.get("receipt_sha256"),
            "verifier_key_id": receipt.get("verifier", {}).get("key_id"),
        }
    if state["stage"] != "hardware_appraisal_prechecked":
        raise OrchestratorError(
            "receipt issuance requires successful H100 appraisal"
        )
    _require_recorded_file(
        config,
        config_hash,
        "retained_challenge_sha256",
        _challenge_path(config),
    )
    _require_recorded_file(
        config,
        config_hash,
        "appraisal_report_sha256",
        Path(config["outputs"]["appraisal_report"]),
    )
    plan = command_plan(config, config_hash)
    argv = next(step["argv"] for step in plan["steps"] if step["id"] == "receipt_issue_hsm")
    _transition(
        config,
        config_hash,
        "hardware_appraisal_prechecked",
        "receipt_issuance_in_progress_challenge_may_be_burned",
    )
    try:
        result = _run_json(argv, 1800, runner)
        if result.get("receipt_issued") is not True or result.get("accepted_for_lean") is not False:
            raise OrchestratorError("receipt issuer crossed or changed the source-review boundary")
        receipt_hash, _ = _sha256_file(receipt_path)
        receipt, _receipt_bytes = _canonical_load(receipt_path, "issued trusted-compute receipt")
        if (
            result.get("receipt_sha256") is None
            or receipt.get("receipt_sha256") != result.get("receipt_sha256")
            or receipt.get("backend") != BACKEND
            or receipt.get("verifier", {}).get("key_id")
            != config["managed_hsm"]["key_id"]
        ):
            raise OrchestratorError("receipt issuer omitted the canonical receipt identity")
        _transition(
            config,
            config_hash,
            "receipt_issuance_in_progress_challenge_may_be_burned",
            "receipt_issued_pending_source_review",
            record_name="receipt_file_sha256",
            record_sha256=receipt_hash,
        )
        return result
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "receipt_issuance_in_progress_challenge_may_be_burned",
                "receipt_issuance_failed_challenge_reconciliation_required",
            )
        except Exception:
            pass
        raise


def reconcile_receipt(
    config: dict[str, Any],
    config_hash: str,
    runner: CommandRunner = _default_run,
) -> dict[str, Any]:
    """Adopt only a persisted, signature-valid receipt after ambiguity."""

    state = load_state(config, config_hash)
    if state["stage"] != "receipt_issuance_failed_challenge_reconciliation_required":
        raise OrchestratorError("receipt reconciliation is not currently required")
    receipt_path = Path(config["outputs"]["receipt"])
    argv = [
        sys.executable,
        str(_tool("tools/trusted_compute_receipt.py")),
        "verify",
        str(receipt_path),
        "--public-key",
        config["managed_hsm"]["public_key"]["path"],
    ]
    verified = _run_json(argv, 300, runner)
    receipt, _ = _canonical_load(receipt_path, "reconciled receipt")
    if (
        verified.get("signature_valid") is not True
        or verified.get("accepted_for_lean") is not False
        or verified.get("backend") != BACKEND
        or verified.get("verifier_key_id") != config["managed_hsm"]["key_id"]
        or receipt.get("receipt_sha256") != verified.get("receipt_sha256")
        or receipt.get("backend") != BACKEND
    ):
        raise OrchestratorError(
            "persisted receipt failed exact H100/key reconciliation"
        )
    receipt_hash, _ = _sha256_file(receipt_path)
    _transition(
        config,
        config_hash,
        state["stage"],
        "receipt_issued_pending_source_review",
        record_name="receipt_file_sha256",
        record_sha256=receipt_hash,
    )
    return verified


def _review_pair_hash(registry: Path, lean: Path) -> str:
    registry_hash, _ = _sha256_file(registry)
    lean_hash, _ = _sha256_file(lean)
    return hashlib.sha256(
        (registry_hash + "\n" + lean_hash + "\n").encode("ascii")
    ).hexdigest()


def generate_review_candidates(
    config: dict[str, Any], config_hash: str, runner: CommandRunner = _default_run
) -> dict[str, Any]:
    if config["lean_review"]["registered_invocation"] is None:
        raise OrchestratorError(
            "operational phase receipts intentionally have no Lean review candidate"
        )
    state = load_state(config, config_hash)
    registry_destination = Path(config["outputs"]["registry_candidate"])
    lean_destination = Path(config["outputs"]["lean_candidate"])
    if state["stage"] == "review_candidates_generated_human_source_review_required":
        expected = state["records"].get("review_candidates_sha256")
        if expected != _review_pair_hash(registry_destination, lean_destination):
            raise OrchestratorError(
                "review candidates changed after generation"
            )
        return {
            "accepted": False,
            "classification": (
                "review_candidates_generated_no_live_trust_files_modified"
            ),
            "lean_candidate": str(lean_destination),
            "registry_candidate": str(registry_destination),
        }
    if state["stage"] != "receipt_issued_pending_source_review":
        raise OrchestratorError("review generation requires an issued receipt")
    _require_recorded_file(
        config,
        config_hash,
        "receipt_file_sha256",
        Path(config["outputs"]["receipt"]),
    )
    plan = command_plan(config, config_hash)
    registry_argv = next(
        step["argv"] for step in plan["steps"] if step["id"] == "registry_review_candidate"
    )
    lean_argv = next(
        step["argv"] for step in plan["steps"] if step["id"] == "lean_review_candidate"
    )
    if registry_destination.exists() or lean_destination.exists():
        raise OrchestratorError("review candidate outputs must be fresh")
    review_root = Path(config["outputs"]["review_root"])
    review_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _transition(
        config,
        config_hash,
        "receipt_issued_pending_source_review",
        "review_candidate_generation_in_progress",
    )
    temporary_root: Path | None = None
    try:
        temporary_root = Path(tempfile.mkdtemp(prefix=".lean-review-", dir=review_root))
        registry_tmp = temporary_root / "TrustedComputeRegistry.lean"
        lean_tmp = temporary_root / "Certificate.lean"
        registry_argv = [str(registry_tmp) if item == str(registry_destination) else item for item in registry_argv]
        lean_argv = [str(lean_tmp) if item == str(lean_destination) else item for item in lean_argv]
        for argv in (registry_argv, lean_argv):
            completed = runner(argv, 600)
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
                raise OrchestratorError(f"review source generator rejected the receipt: {detail}")
        if not registry_tmp.is_file() or not lean_tmp.is_file():
            raise OrchestratorError("review generators did not create both candidate sources")
        registry_destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lean_destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.replace(registry_tmp, registry_destination)
        os.replace(lean_tmp, lean_destination)
        registry_hash, _ = _sha256_file(registry_destination)
        lean_hash, _ = _sha256_file(lean_destination)
        _transition(
            config,
            config_hash,
            "review_candidate_generation_in_progress",
            "review_candidates_generated_human_source_review_required",
            record_name="review_candidates_sha256",
            record_sha256=hashlib.sha256(
                (registry_hash + "\n" + lean_hash + "\n").encode("ascii")
            ).hexdigest(),
        )
        return {
            "accepted": False,
            "classification": "review_candidates_generated_no_live_trust_files_modified",
            "lean_candidate": str(lean_destination),
            "registry_candidate": str(registry_destination),
        }
    except BaseException:
        try:
            _transition(
                config,
                config_hash,
                "review_candidate_generation_in_progress",
                "review_candidate_generation_failed_or_unknown_manual_reconciliation_required",
            )
        except Exception:
            pass
        raise
    finally:
        if temporary_root is not None:
            shutil.rmtree(temporary_root, ignore_errors=True)


def _result(operation: str, payload: Any) -> dict[str, Any]:
    return {
        "accepted": False,
        "classification": "operator_workflow_progress_not_theorem_acceptance",
        "operation": operation,
        "operation_succeeded": True,
        "result": payload,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in (
        "validate",
        "plan",
        "init",
        "status",
        "deploy",
        "reconcile-deployment",
        "challenge",
        "reconcile-challenge",
        "worker-run-local",
        "ingest-returned",
        "appraise",
        "issue-receipt",
        "reconcile-receipt",
        "generate-review-candidates",
    ):
        child = subparsers.add_parser(name)
        child.add_argument("config", type=Path)
    record_stage = subparsers.add_parser("record-worker-stage-handoff")
    record_stage.add_argument("config", type=Path)
    record_stage.add_argument(
        "--confirm-exact-staging",
        action="store_true",
        required=True,
        help="confirm that every manifest-bound byte is staged at its guest path",
    )
    acknowledge = subparsers.add_parser("ack-worker-stage")
    acknowledge.add_argument("config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "worker-run-local":
            config, config_hash = load_worker_config(args.config)
        else:
            config, config_hash = load_config(args.config)
        if args.command == "validate":
            payload: Any = {"campaign_config_sha256": config_hash, "valid": True}
        elif args.command == "plan":
            payload = command_plan(config, config_hash)
        elif args.command == "worker-run-local":
            payload = run_worker_local(config, config_hash)
        else:
            with _operator_lock(config, exclusive=args.command != "status"):
                if args.command == "init":
                    payload = initialize_state(config, config_hash)
                elif args.command == "status":
                    payload = load_state(config, config_hash)
                elif args.command == "deploy":
                    payload = deploy(config, config_hash)
                elif args.command == "reconcile-deployment":
                    payload = reconcile_deployment(config, config_hash)
                elif args.command == "challenge":
                    payload = create_challenge_step(config, config_hash)
                elif args.command == "reconcile-challenge":
                    payload = reconcile_challenge(config, config_hash)
                elif args.command == "record-worker-stage-handoff":
                    payload = record_worker_stage_handoff(
                        config,
                        config_hash,
                        confirmed=args.confirm_exact_staging,
                    )
                elif args.command == "ack-worker-stage":
                    payload = acknowledge_worker_stage(config, config_hash)
                elif args.command == "ingest-returned":
                    payload = ingest_returned_package(config, config_hash)
                elif args.command == "appraise":
                    payload = appraise(config, config_hash)
                elif args.command == "issue-receipt":
                    payload = issue_receipt(config, config_hash)
                elif args.command == "reconcile-receipt":
                    payload = reconcile_receipt(config, config_hash)
                else:
                    payload = generate_review_candidates(config, config_hash)
        print(json.dumps(_result(args.command, payload), sort_keys=True, separators=(",", ":")))
        return 0
    except (
        OrchestratorError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "azure_h100_operator_workflow_failed_closed",
                    "error": str(error),
                    "operation_succeeded": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
