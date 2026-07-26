# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate the non-authorizing Sqrt218 pure-entry launcher boundary.

This module reads one small JSON manifest and checks its closed contract.  It
does not open an ELF, input archive, result record, or attestation artifact;
does not import a native extension; and does not invoke a launcher, compiler,
checker, or production computation.

The checked-in V1 manifest records a concrete, unreviewed source prototype and
a separate cloud-only build plan, but no built launcher artifact.  Changing a
Boolean or filling in an artifact hash cannot make it authoritative: a
reviewed launcher plus a formal connection to the Lean initializer/observer
requires a new manifest kind and validator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "sparkinterval.sqrt218-pure-entry-launcher-boundary.v1"
MAX_MANIFEST_BYTES = 128 * 1024

AUTHORITY = {
    "architecture_execution_proved": False,
    "authorizes_lean_theorem": False,
    "production_execution_performed": False,
    "receipt_may_be_issued": False,
}

STATUS = {
    "blockers": [
        "unreviewed-pure-entry-loader-launcher-prototype",
        "cloud-built-launcher-artifact-not-yet-pinned",
        "v2-launcher-and-control-identity-not-yet-instantiated-by-reviewed-receipt",
        "missing-launcher-to-lean-initializer-observer-refinement",
        "missing-exact-elf-loader-and-x86-execution-proof",
        "missing-appraised-azure-launch-receipt",
    ],
    "execution_ready": False,
    "production_ready": False,
}

PURE_ENTRY = {
    "calling_convention": "System V AMD64 ABI",
    "dynamic_interpreter_allowed": False,
    "elf_machine": "EM_X86_64",
    "entry_is_linux_process_start": False,
    "entry_symbol": "tg_sq218_verify_snapshot_v2",
    "execve_allowed": False,
    "function_signature": (
        "int(const uint8_t *, uint64_t, uint8_t[120], uint32_t *)"
    ),
    "object_type": "ET_EXEC",
    "position_independent": False,
}

ABI = {
    "arguments": [
        {
            "c_type": "const uint8_t *",
            "name": "input",
            "register": "RDI",
            "region": "input",
        },
        {
            "c_type": "uint64_t",
            "name": "input_length",
            "register": "RSI",
            "value": "exact-input-artifact-size",
        },
        {
            "c_type": "uint8_t *",
            "name": "result",
            "register": "RDX",
            "region": "result",
        },
        {
            "c_type": "uint32_t *",
            "name": "status",
            "register": "RCX",
            "region": "status",
        },
    ],
    "callee_saved_registers": ["RBX", "RBP", "R12", "R13", "R14", "R15"],
    "direction_flag_clear_on_entry": True,
    "return_register": "RAX",
    "return_type": "int",
    "stack_alignment_at_function_entry": {
        "modulus_bytes": 16,
        "remainder_bytes": 8,
    },
}

MEMORY = {
    "all_regions_pairwise_disjoint": True,
    "elf_load_segments": {
        "exact_file_bytes_required": True,
        "fixed_virtual_addresses_required": True,
        "no_unapplied_relocations": True,
        "no_writable_executable_segment": True,
        "program_header_permissions_enforced": True,
    },
    "input": {
        "contents": "exact-input-artifact-bytes",
        "permission_during_entry": "read-only-non-executable",
        "sha256_binding_required": True,
        "size": "exact-input-artifact-size",
        "unchanged_after_return_required": True,
    },
    "result": {
        "final_contents": "exact-retained-result-bytes",
        "initial_contents": "all-zero",
        "permission_during_entry": "read-write-non-executable",
        "sha256_binding_required": True,
        "size_bytes": 120,
    },
    "stack": {
        "guard_pages_required": True,
        "permission": "read-write-non-executable",
        "size_binding_required": True,
    },
    "status": {
        "accepted_value": 0,
        "encoding": "little-endian-uint32",
        "initial_contents": "all-zero",
        "permission_during_entry": "read-write-non-executable",
        "size_bytes": 4,
    },
}

RETURN_OBSERVER = {
    "accept_only_if": [
        "normal-return-to-measured-sentinel",
        "eax-int32-return-equals-one",
        "status-buffer-little-endian-u32-equals-zero",
        "result-buffer-is-exactly-120-bytes",
        "input-bytes-unchanged",
        "no-signal-fault-or-timeout-and-exactly-one-launcher-attempt",
    ],
    "observer_executes_before_unmeasured_code": True,
    "result_retained_without_transformation": True,
    "return_address_points_into_measured_launcher_text": True,
    "return_sentinel_address_binding_required": True,
}

CLOUD_BINDING = {
    "attestation_bindings_required": [
        "off-vm-challenge",
        "job-binding-sha256",
        "launcher-sha256-and-size",
        "pure-entry-elf-sha256-and-size",
        "input-sha256-and-size",
        "exact-120-byte-result-sha256-and-size",
        "status-u32",
        "return-observer-record",
        "vm-image-measurement",
        "cpu-vendor-family-model-stepping",
        "cpu-microcode-version",
        "sev-snp-report",
        "vtpm-pcr23-quote",
    ],
    "backend": "azure_sevsnp_cpu",
    "custom_launch_mode_required": "sqrt218-static-pure-entry-loader-v1",
    "existing_popen_execve_mode_acceptable": False,
    "target_profile": "azure_sevsnp_cpu",
}

FORMAL_CONNECTION = {
    "architecture_model": (
        "SparkInterval.Execution.Architecture.X86ELF.PureEntryModel"
    ),
    "architecture_obligation": (
        "ArchitectureExecutionSuppliesSuccessfulPureEntry"
    ),
    "execution_closure_identity_binds_launch_contract": True,
    "execution_closure_identity_binds_launcher_artifact": True,
    "initializer_refinement_present": False,
    "lean_initializer_field": "PureEntryModel.initializeEntry",
    "lean_observer_field": "PureEntryModel.returnedWith",
    "observer_refinement_present": False,
    "physical_admission_rule_present": False,
    "signed_lean_launcher_binding_present": False,
}

CURRENT_IMPLEMENTATION = {
    "cloud_build_manifest": {
        "kind": "sparkinterval.sqrt218-cloud-launcher-build.v1",
        "manifest_sha256": (
            "fc4cdac2d81d66b40e453059b738073f771a9f77fde932e2e9855d49ea7f6e1d"
        ),
        "path": "launcher_build/sqrt218/cloud-launcher-build.v1.json",
    },
    "concrete_launcher_source": (
        "launcher_build/sqrt218/sqrt218_pure_entry_launcher.c"
    ),
    "concrete_trampoline_source": (
        "launcher_build/sqrt218/sqrt218_pure_entry_trampoline.S"
    ),
    "launcher_artifact": {
        "path": None,
        "sha256": None,
        "size_bytes": None,
    },
    "launcher_prototype_present": True,
    "launcher_prototype_formally_refined": False,
    "launcher_source_reviewed": False,
    "measured_runner_launch_mode": "normal-process-popen",
    "measured_runner_satisfies_contract": False,
}

LOCAL_VALIDATION = {
    "artifact_bytes_opened": False,
    "compiler_or_toolchain_invoked": False,
    "elf_or_launcher_executed": False,
    "manifest_metadata_only": True,
    "production_arithmetic_performed": False,
    "production_certificate_opened": False,
}

TOP_LEVEL_KEYS = {
    "abi",
    "authority",
    "cloud_binding",
    "current_implementation",
    "formal_connection",
    "kind",
    "local_validation",
    "manifest_sha256",
    "memory",
    "pure_entry",
    "return_observer",
    "schema_version",
    "status",
}
BODY_KEYS = TOP_LEVEL_KEYS - {"manifest_sha256"}


class LauncherBoundaryError(ValueError):
    """The static launcher boundary manifest is malformed or overclaims."""


def _exact_object(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LauncherBoundaryError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise LauncherBoundaryError(
            f"{label} has wrong fields "
            f"(missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)})"
        )
    return value


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate the closed V1 boundary without touching runtime artifacts."""

    manifest = _exact_object(value, TOP_LEVEL_KEYS, "launcher manifest")
    if manifest["kind"] != MANIFEST_KIND:
        raise LauncherBoundaryError("unsupported launcher manifest kind")
    if (
        isinstance(manifest["schema_version"], bool)
        or manifest["schema_version"] != SCHEMA_VERSION
    ):
        raise LauncherBoundaryError("unsupported launcher schema_version")

    expected_sections = {
        "abi": ABI,
        "authority": AUTHORITY,
        "cloud_binding": CLOUD_BINDING,
        "current_implementation": CURRENT_IMPLEMENTATION,
        "formal_connection": FORMAL_CONNECTION,
        "local_validation": LOCAL_VALIDATION,
        "memory": MEMORY,
        "pure_entry": PURE_ENTRY,
        "return_observer": RETURN_OBSERVER,
        "status": STATUS,
    }
    for name, expected in expected_sections.items():
        if manifest[name] != expected:
            raise LauncherBoundaryError(
                f"launcher {name} differs from the fail-closed V1 contract"
            )

    claimed = manifest["manifest_sha256"]
    if (
        not isinstance(claimed, str)
        or len(claimed) != 64
        or any(character not in "0123456789abcdef" for character in claimed)
        or claimed == "0" * 64
    ):
        raise LauncherBoundaryError(
            "manifest_sha256 must be a nonzero lowercase SHA-256 digest"
        )
    body = {key: manifest[key] for key in sorted(BODY_KEYS)}
    expected = sha256_bytes(canonical_json_bytes(body))
    if claimed != expected:
        raise LauncherBoundaryError(
            "manifest_sha256 does not match the canonical manifest body"
        )
    return manifest


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise LauncherBoundaryError("launcher manifest bytes must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise LauncherBoundaryError("launcher manifest is too large")
    try:
        value = parse_json_bytes(raw, label="Sqrt218 launcher manifest")
    except CampaignIOError as exc:
        raise LauncherBoundaryError(str(exc)) from exc
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    """Read only the bounded manifest file and validate it."""

    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as exc:
        raise LauncherBoundaryError(str(exc)) from exc
    return validate_manifest_bytes(raw)


def require_execution_ready(manifest: Any) -> None:
    """Always fail for V1; readiness needs a new reviewed manifest kind."""

    checked = validate_manifest(manifest)
    raise LauncherBoundaryError(
        "pure-entry launcher is not execution-ready: "
        + ", ".join(checked["status"]["blockers"])
    )


def review_summary(manifest: Any) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    return {
        "architecture_execution_proved": False,
        "authorizes_lean_theorem": False,
        "blockers": checked["status"]["blockers"],
        "entry_is_linux_process_start": False,
        "entry_symbol": checked["pure_entry"]["entry_symbol"],
        "execution_ready": False,
        "launcher_artifact_present": False,
        "launcher_cloud_build_ready": True,
        "launcher_prototype_present": True,
        "local_validation": checked["local_validation"],
        "measured_runner_satisfies_contract": False,
        "production_ready": False,
    }
