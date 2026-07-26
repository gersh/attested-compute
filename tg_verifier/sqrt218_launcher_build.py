# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate the non-authorizing cloud build for the Sqrt218 launcher.

Normal validation reads only the checked-in manifest and its small pinned
source files.  It does not invoke a compiler, open a launcher artifact, open a
production input, or execute the pure-entry ELF.  Artifact indexing is a
separate command used only at the end of the guarded cloud build.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import os
import stat
from typing import Any

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "sparkinterval.sqrt218-cloud-launcher-build.v1"
ARTIFACT_INDEX_KIND = "sparkinterval.sqrt218-cloud-launcher-artifacts.v1"
SOURCE_CLOSURE_KIND = "sparkinterval.sqrt218-launcher-source-closure.v1"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024

AUTHORITY = {
    "architecture_execution_proved": False,
    "authorizes_lean_theorem": False,
    "launcher_source_formally_verified": False,
    "production_execution_performed": False,
    "reviewed_launcher_release": False,
}

BUILD = {
    "cloud_build_ready": True,
    "compile_flags": [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Wconversion",
        "-Werror",
        "-pedantic",
        "-fPIE",
        "-fno-omit-frame-pointer",
        "-fno-stack-protector",
        "-fno-strict-aliasing",
        "-static-pie",
        "-Wl,-z,relro",
        "-Wl,-z,now",
        "-Wl,-z,noexecstack",
        "-Wl,-z,separate-code",
        "-Wl,--build-id=none",
    ],
    "executes_launcher": False,
    "final_launcher": "retained/sqrt218_pure_entry_launcher",
    "opens_production_input": False,
    "ordered_steps": [
        "source_closure",
        "gcc_version",
        "gcc_target",
        "gcc_specs",
        "assembler_version",
        "linker_version",
        "libc_path",
        "compiler_sha256",
        "assembler_sha256",
        "linker_sha256",
        "libc_sha256",
        "compile",
        "elf_header",
        "elf_program_headers",
        "elf_section_headers",
        "elf_symbols",
        "elf_dynamic",
        "elf_relocations",
        "symbol_table",
        "disassembly",
        "artifact_index",
    ],
    "output_is_authority": False,
    "target": "x86_64-linux-gnu",
}

AZURE = {
    "acr_build_argv": [
        "az",
        "acr",
        "build",
        "--registry",
        "${ACR_NAME}",
        "--platform",
        "linux/amd64",
        "--image",
        "sqrt218-launcher-build:${LANE_MANIFEST_SHA256}",
        "--file",
        "launcher_build/sqrt218/Dockerfile",
        ".",
    ],
    "acr_resolve_digest_argv": [
        "az",
        "acr",
        "manifest",
        "show-metadata",
        "--registry",
        "${ACR_NAME}",
        "--name",
        "sqrt218-launcher-build:${LANE_MANIFEST_SHA256}",
        "--query",
        "digest",
        "--output",
        "tsv",
    ],
    "aci_build_argv": [
        "az",
        "container",
        "create",
        "--resource-group",
        "${RESOURCE_GROUP}",
        "--name",
        "${CONTAINER_NAME}",
        "--image",
        "${ACR_LOGIN_SERVER}/sqrt218-launcher-build@sha256:${FINAL_IMAGE_DIGEST}",
        "--os-type",
        "Linux",
        "--cpu",
        "4",
        "--memory",
        "8",
        "--restart-policy",
        "Never",
        "--assign-identity",
        "${ACI_IDENTITY_RESOURCE_ID}",
        "--acr-identity",
        "${ACI_IDENTITY_RESOURCE_ID}",
        "--azure-file-volume-account-name",
        "${STORAGE_ACCOUNT}",
        "--azure-file-volume-account-key",
        "${AZURE_STORAGE_KEY}",
        "--azure-file-volume-share-name",
        "${STORAGE_SHARE}",
        "--azure-file-volume-mount-path",
        "/workspace/export",
        "--environment-variables",
        "TG_CLOUD_LAUNCHER_BUILD=1",
        "TG_REPOSITORY_ROOT=/workspace/repository",
        "TG_OUTPUT_ROOT=/workspace/export/${OUTPUT_LEAF}",
        "TG_FINAL_IMAGE_REFERENCE=${ACR_LOGIN_SERVER}/sqrt218-launcher-build@sha256:${FINAL_IMAGE_DIGEST}",
    ],
    "acr_pull_identity_resource_id": "${ACI_IDENTITY_RESOURCE_ID}",
    "acr_pull_role_pregranted_required": True,
    "build_only_no_production_execution": True,
    "persistent_output_mount": "/workspace/export",
    "persistent_output_leaf_must_be_absent": True,
    "repository_source_closure_baked_into_image": True,
    "final_image_digest_required": True,
}

TOOLCHAIN = {
    "base_image": (
        "docker.io/rocq/rocq-prover@sha256:"
        "b85a80a11bb65c7c843f91c7cbcce282f22ee397c9ca42f123d568ab6cef68b0"
    ),
    "compiler_family": "GNU GCC",
    "compiler_target_required": "x86_64-*",
    "final_image_digest_is_primary_environment_pin": True,
    "static_libc_archive_hashed_in_cloud": True,
    "system_assembler_linker_and_libc_outside_formal_proof": True,
}

EVIDENCE_OUTPUTS = {
    "assembler.sha256": "commands/assembler_sha256.stdout",
    "assembler.version": "commands/assembler_version.stdout",
    "build.command": "commands/compile.argv0",
    "build.stderr": "commands/compile.stderr",
    "build.stdout": "commands/compile.stdout",
    "compiler.sha256": "commands/compiler_sha256.stdout",
    "compiler.specs": "commands/gcc_specs.stdout",
    "compiler.target": "commands/gcc_target.stdout",
    "compiler.version": "commands/gcc_version.stdout",
    "elf.disassembly": "commands/disassembly.stdout",
    "elf.dynamic": "commands/elf_dynamic.stdout",
    "elf.file": "retained/sqrt218_pure_entry_launcher",
    "elf.header": "commands/elf_header.stdout",
    "elf.program_headers": "commands/elf_program_headers.stdout",
    "elf.relocations": "commands/elf_relocations.stdout",
    "elf.section_headers": "commands/elf_section_headers.stdout",
    "elf.symbols": "commands/elf_symbols.stdout",
    "libc.path": "commands/libc_path.stdout",
    "libc.sha256": "commands/libc_sha256.stdout",
    "linker.map": "retained/sqrt218-launcher.map",
    "linker.sha256": "commands/linker_sha256.stdout",
    "linker.version": "commands/linker_version.stdout",
    "source.closure": "retained/source-closure.json",
    "symbol.table": "commands/symbol_table.stdout",
}

REQUIRED_SOURCE_PATHS = {
    "launcher_build/sqrt218/Dockerfile",
    "launcher_build/sqrt218/README.md",
    "launcher_build/sqrt218/run_cloud_launcher_build.sh",
    "launcher_build/sqrt218/sqrt218_launcher_abi.h",
    "launcher_build/sqrt218/sqrt218_launcher_sha256.c",
    "launcher_build/sqrt218/sqrt218_launcher_sha256.h",
    "launcher_build/sqrt218/sqrt218_pure_entry_launcher.c",
    "launcher_build/sqrt218/sqrt218_pure_entry_trampoline.S",
    "tg_verifier/campaign_io.py",
    "tg_verifier/sqrt218_launcher_build.py",
    "tools/tg_sqrt218_launcher_build.py",
}

TOP_LEVEL_KEYS = {
    "authority",
    "azure",
    "build",
    "container",
    "evidence_outputs",
    "kind",
    "manifest_sha256",
    "schema_version",
    "source_inputs",
    "status",
    "toolchain",
}
BODY_KEYS = TOP_LEVEL_KEYS - {"manifest_sha256"}


class LauncherBuildError(ValueError):
    """The launcher build metadata or retained build output is malformed."""


def _exact_object(
    value: Any, expected: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LauncherBuildError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise LauncherBuildError(
            f"{label} has wrong fields "
            f"(missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)})"
        )
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        or value == "0" * 64
    ):
        raise LauncherBuildError(f"{label} must be nonzero lowercase SHA-256")
    return value


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LauncherBuildError(f"{label} must be a relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise LauncherBuildError(f"{label} is not a normalized relative path")
    return value


def _file_pin(value: Any, label: str) -> dict[str, Any]:
    pin = _exact_object(value, {"path", "sha256", "size_bytes"}, label)
    _relative_path(pin["path"], f"{label}.path")
    _digest(pin["sha256"], f"{label}.sha256")
    size = pin["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_SOURCE_BYTES:
        raise LauncherBuildError(f"{label}.size_bytes is out of range")
    return pin


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = _exact_object(value, TOP_LEVEL_KEYS, "launcher build manifest")
    if manifest["kind"] != MANIFEST_KIND:
        raise LauncherBuildError("unsupported launcher build manifest kind")
    if (
        isinstance(manifest["schema_version"], bool)
        or manifest["schema_version"] != SCHEMA_VERSION
    ):
        raise LauncherBuildError("unsupported launcher build schema_version")
    if manifest["authority"] != AUTHORITY:
        raise LauncherBuildError("launcher build authority block overclaims")
    if manifest["build"] != BUILD:
        raise LauncherBuildError("launcher build command boundary differs")
    if manifest["azure"] != AZURE:
        raise LauncherBuildError("launcher build Azure plan differs")
    if manifest["toolchain"] != TOOLCHAIN:
        raise LauncherBuildError("launcher build toolchain boundary differs")
    if manifest["evidence_outputs"] != EVIDENCE_OUTPUTS:
        raise LauncherBuildError("launcher build evidence inventory differs")

    container = _exact_object(
        manifest["container"],
        {
            "base_image",
            "dockerfile",
            "entrypoint",
            "final_image_must_be_registry_digest_pinned",
        },
        "launcher build container",
    )
    if (
        container["base_image"] != TOOLCHAIN["base_image"]
        or container["entrypoint"]
        != "/opt/sparkinterval/run_cloud_launcher_build.sh"
        or container["final_image_must_be_registry_digest_pinned"] is not True
    ):
        raise LauncherBuildError("launcher build container boundary differs")
    _file_pin(container["dockerfile"], "launcher build Dockerfile")
    if container["dockerfile"]["path"] != "launcher_build/sqrt218/Dockerfile":
        raise LauncherBuildError("launcher build Dockerfile path differs")

    status = _exact_object(
        manifest["status"],
        {
            "blockers",
            "build_ready",
            "formal_refinement_ready",
            "production_execution_ready",
        },
        "launcher build status",
    )
    if (
        status["build_ready"] is not True
        or status["formal_refinement_ready"] is not False
        or status["production_execution_ready"] is not False
        or status["blockers"]
        != [
            "unreviewed-launcher-source",
            "cloud-built-launcher-artifact-not-yet-pinned",
            "missing-launcher-to-lean-initializer-observer-refinement",
            "missing-system-loader-x86-cpu-refinement",
            "missing-signed-execution-closure-launcher-binding",
        ]
    ):
        raise LauncherBuildError("launcher build status is not fail-closed")

    sources = manifest["source_inputs"]
    if not isinstance(sources, list) or not 11 <= len(sources) <= 32:
        raise LauncherBuildError("launcher build source_inputs has wrong length")
    checked_sources = [
        _file_pin(item, f"source_inputs[{index}]")
        for index, item in enumerate(sources)
    ]
    paths = [item["path"] for item in checked_sources]
    if len(set(paths)) != len(paths) or set(paths) != REQUIRED_SOURCE_PATHS:
        raise LauncherBuildError(
            "launcher build source_inputs is not the exact reviewed source set"
        )
    if container["dockerfile"] != next(
        item for item in checked_sources
        if item["path"] == "launcher_build/sqrt218/Dockerfile"
    ):
        raise LauncherBuildError("container Dockerfile pin differs from source pin")

    claimed = _digest(manifest["manifest_sha256"], "manifest_sha256")
    body = {key: manifest[key] for key in sorted(BODY_KEYS)}
    expected = sha256_bytes(canonical_json_bytes(body))
    if claimed != expected:
        raise LauncherBuildError(
            "manifest_sha256 does not match canonical launcher build body"
        )
    return manifest


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise LauncherBuildError("launcher build manifest bytes must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise LauncherBuildError("launcher build manifest is too large")
    try:
        value = parse_json_bytes(raw, label="Sqrt218 launcher build manifest")
    except CampaignIOError as exc:
        raise LauncherBuildError(str(exc)) from exc
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as exc:
        raise LauncherBuildError(str(exc)) from exc
    return validate_manifest_bytes(raw)


def validate_inputs(
    manifest: dict[str, Any],
    repository_root: Path,
    *,
    require_build_ready: bool = False,
) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    if not repository_root.is_dir() or repository_root.is_symlink():
        raise LauncherBuildError("repository root must be a non-symlink directory")
    for pin in checked["source_inputs"]:
        path = repository_root / pin["path"]
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise LauncherBuildError(f"cannot stat source {path}: {exc}") from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != pin["size_bytes"]
        ):
            raise LauncherBuildError(
                f"source size/type differs from pin: {pin['path']}"
            )
        try:
            raw = read_bytes_once(path, limit=MAX_SOURCE_BYTES)
        except CampaignIOError as exc:
            raise LauncherBuildError(str(exc)) from exc
        if sha256_bytes(raw) != pin["sha256"]:
            raise LauncherBuildError(
                f"source SHA-256 differs from pin: {pin['path']}"
            )
    if require_build_ready and not checked["status"]["build_ready"]:
        raise LauncherBuildError("launcher cloud build is not ready")
    return checked


def source_closure(
    manifest: dict[str, Any], repository_root: Path
) -> dict[str, Any]:
    checked = validate_inputs(manifest, repository_root, require_build_ready=True)
    return {
        "authority": dict(AUTHORITY),
        "kind": SOURCE_CLOSURE_KIND,
        "launcher_build_manifest_sha256": checked["manifest_sha256"],
        "source_inputs": checked["source_inputs"],
    }


def _artifact_pin(root: Path, relative: str) -> dict[str, Any]:
    path = root / _relative_path(relative, "artifact path")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LauncherBuildError(f"cannot stat retained artifact {path}: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise LauncherBuildError(f"retained artifact is not a regular file: {path}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_EVIDENCE_BYTES:
        raise LauncherBuildError(f"retained artifact size is invalid: {path}")
    try:
        raw = read_bytes_once(path, limit=MAX_EVIDENCE_BYTES)
    except CampaignIOError as exc:
        raise LauncherBuildError(str(exc)) from exc
    return {
        "path": relative,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def artifact_index(
    manifest: dict[str, Any],
    output_root: Path,
    final_image_reference: str,
) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    if (
        not isinstance(final_image_reference, str)
        or "@sha256:" not in final_image_reference
        or len(final_image_reference.rsplit("@sha256:", 1)[1]) != 64
    ):
        raise LauncherBuildError(
            "final launcher build image must be registry-digest pinned"
        )
    digest = final_image_reference.rsplit("@sha256:", 1)[1]
    _digest(digest, "final image digest")
    if not output_root.is_dir() or output_root.is_symlink():
        raise LauncherBuildError("launcher build output root is invalid")
    artifacts = {
        name: _artifact_pin(output_root, relative)
        for name, relative in sorted(EVIDENCE_OUTPUTS.items())
    }
    return {
        "artifacts": artifacts,
        "authority": dict(AUTHORITY),
        "final_image_reference": final_image_reference,
        "kind": ARTIFACT_INDEX_KIND,
        "launcher_build_manifest_sha256": checked["manifest_sha256"],
        "production_input_opened": False,
        "launcher_executed": False,
    }


def review_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    return {
        "architecture_execution_proved": False,
        "authorizes_lean_theorem": False,
        "blockers": list(checked["status"]["blockers"]),
        "build_ready": True,
        "executes_launcher": False,
        "formal_refinement_ready": False,
        "opens_production_input": False,
        "production_execution_ready": False,
        "source_file_count": len(checked["source_inputs"]),
    }
