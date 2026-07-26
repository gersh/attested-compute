# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate and index the cloud-only Sqrt218 VST/CompCert proof-build lane.

This module performs bounded metadata and file-identity checks.  It never
installs or invokes Rocq, VST, CompCert, an assembler, a linker, an ELF, or a
production Sqrt218 computation.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Mapping

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 1
LANE_KIND = "sparkinterval.sqrt218-cloud-proof-build-lane.v1"
SOURCE_CLOSURE_KIND = "sparkinterval.sqrt218-proof-source-closure.v1"
ARTIFACT_INDEX_KIND = "sparkinterval.sqrt218-proof-build-artifact-index.v1"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_BY_DIGEST_RE = re.compile(
    r"^[^\s@]+@sha256:(?P<digest>[0-9a-f]{64})$"
)
RELATIVE_PATH_RE = re.compile(
    r"^(?!/)(?!\.\.(?:/|$))(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*$"
)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")

AUTHORITY = {
    "architecture_execution_proved": False,
    "authorizes_lean_theorem": False,
    "compiler_correctness_established_by_lane_metadata": False,
    "production_certificate_opened": False,
    "production_execution_performed": False,
}

TOP_LEVEL_KEYS = {
    "authority",
    "azure",
    "container",
    "evidence_outputs",
    "kind",
    "manifest_sha256",
    "pipeline",
    "proof_project",
    "schema_version",
    "source_inputs",
    "toolchain",
}
BODY_KEYS = TOP_LEVEL_KEYS - {"manifest_sha256"}

ORDERED_STEPS = (
    "source_closure",
    "preprocess",
    "csyntaxgen",
    "clightgen",
    "rocq_makefile",
    "vst_proof",
    "rocqchk",
    "assumption_audit",
    "proof_bundle",
    "compcert",
    "assembler",
    "linker",
    "elf_header",
    "elf_program_headers",
    "elf_section_headers",
    "elf_symbols",
    "elf_dependencies",
    "artifact_index",
)

SOURCE_PATHS = (
    "cpu_checker/sqrt218/sqrt218_cpu_checker.c",
    "cpu_checker/sqrt218/sqrt218_cpu_command.c",
    "cpu_checker/sqrt218/sqrt218_cpu_checker.h",
    "cpu_checker/sqrt218/sqrt218_cpu_command.h",
    "proof_build/sqrt218/sqrt218_pure_entry_unit.c",
    "proof_build/sqrt218/Sqrt218AssumptionAudit.v",
    "proof_build/sqrt218/run_cloud_proof_build.sh",
    "tools/tg_sqrt218_proof_build.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/sqrt218_proof_build.py",
)

PROOF_PATHS = ("Sqrt218Spec.v", "Sqrt218Proof.v")

EVIDENCE_OUTPUTS = {
    "assembler.command": "commands/assembler.argv0",
    "assembler.output_object": "retained/sqrt218_pure_entry.o",
    "assembler.stderr": "commands/assembler.stderr",
    "assembler.stdout": "commands/assembler.stdout",
    "c_translation.clight_ast": "retained/Sqrt218Clight.v",
    "c_translation.compcert_c_ast": "retained/Sqrt218CompCertC.v",
    "c_translation.preprocessed_source": (
        "retained/sqrt218_pure_entry.i"
    ),
    "c_translation.source": "retained/source-closure.json",
    "compcert.abstract_assembly": "retained/sqrt218_pure_entry.sdump",
    "compcert.command": "commands/compcert.argv0",
    "compcert.configuration": "retained/compcert.ini",
    "compcert.stderr": "commands/compcert.stderr",
    "compcert.stdout": "commands/compcert.stdout",
    "compcert.textual_assembly": "retained/sqrt218_pure_entry.s",
    "elf.dependencies_report": "commands/elf_dependencies.stdout",
    "elf.file": (
        "retained/sqrt218_cpu_checker_pure_entry_x86_64_v2"
    ),
    "elf.header_report": "commands/elf_header.stdout",
    "elf.program_headers_report": "commands/elf_program_headers.stdout",
    "elf.section_headers_report": "commands/elf_section_headers.stdout",
    "elf.symbols_report": "commands/elf_symbols.stdout",
    "linker.command": "commands/linker.argv0",
    "linker.link_map": "retained/sqrt218-link.map",
    "linker.stderr": "commands/linker.stderr",
    "linker.stdout": "commands/linker.stdout",
    "vst.assumptions_report": "retained/vst-assumptions.txt",
    "vst.proof_bundle": "retained/vst-proof-bundle.tar",
    "vst.rocqchk_command": "commands/rocqchk.argv0",
    "vst.rocqchk_stderr": "retained/rocqchk.stderr",
    "vst.rocqchk_stdout": "retained/rocqchk.stdout",
}

TOOL_EXECUTABLES = (
    "as",
    "ccomp",
    "clightgen",
    "ld",
    "make",
    "readelf",
    "rocq",
    "tar",
)


class ProofBuildError(ValueError):
    """The cloud proof-build plan or retained output is not closed."""


def _exact_object(
    value: Any, expected: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProofBuildError(f"{label} must be an object")
    actual = set(value)
    if actual != set(expected):
        raise ProofBuildError(
            f"{label} has wrong fields "
            f"(missing={sorted(set(expected) - actual)}, "
            f"unexpected={sorted(actual - set(expected))})"
        )
    return value


def _string(
    value: Any, label: str, *, maximum: int = 2048
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or "\x00" in value
        or "\r" in value
        or "\n" in value
    ):
        raise ProofBuildError(
            f"{label} must be a nonempty single-line string"
        )
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        raise ProofBuildError(
            f"{label} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _positive(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > (1 << 63) - 1
    ):
        raise ProofBuildError(f"{label} must be a positive signed-64-bit integer")
    return value


def _relative_path(value: Any, label: str) -> str:
    text = _string(value, label, maximum=512)
    if RELATIVE_PATH_RE.fullmatch(text) is None:
        raise ProofBuildError(f"{label} must be a normalized relative path")
    return text


def _file_pin(
    value: Any,
    label: str,
    *,
    nullable: bool = False,
) -> dict[str, Any]:
    pin = _exact_object(
        value, {"path", "sha256", "size_bytes"}, label
    )
    _relative_path(pin["path"], f"{label}.path")
    if nullable and pin["sha256"] is None and pin["size_bytes"] is None:
        return pin
    if pin["sha256"] is None or pin["size_bytes"] is None:
        raise ProofBuildError(
            f"{label} digest and size must either both be present or both null"
        )
    _digest(pin["sha256"], f"{label}.sha256")
    _positive(pin["size_bytes"], f"{label}.size_bytes")
    return pin


def _argv(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 128
    ):
        raise ProofBuildError(f"{label} must be a nonempty bounded argv array")
    return [
        _string(item, f"{label}[{index}]", maximum=1024)
        for index, item in enumerate(value)
    ]


def _validate_toolchain(value: Any) -> None:
    toolchain = _exact_object(value, {"compcert", "rocq", "vst"}, "toolchain")
    compcert = _exact_object(
        toolchain["compcert"],
        {"configuration", "repository", "revision", "tag", "version"},
        "toolchain.compcert",
    )
    if compcert != {
        "configuration": "x86_64-linux",
        "repository": "https://github.com/AbsInt/CompCert.git",
        "revision": "7b1f02b09954b9b916eb2a91d283c9b5355bf172",
        "tag": "v3.17",
        "version": "3.17",
    }:
        raise ProofBuildError("unsupported CompCert source pin")
    if GIT_REVISION_RE.fullmatch(compcert["revision"]) is None:
        raise ProofBuildError("CompCert revision is not a full Git revision")

    rocq = _exact_object(
        toolchain["rocq"],
        {"base_image_digest", "image", "version"},
        "toolchain.rocq",
    )
    _digest(rocq["base_image_digest"], "toolchain.rocq.base_image_digest")
    if (
        rocq["image"] != "docker.io/rocq/rocq-prover"
        or rocq["version"] != "9.1.1"
    ):
        raise ProofBuildError("unsupported Rocq image or version")

    vst = _exact_object(
        toolchain["vst"],
        {"repository", "revision", "version"},
        "toolchain.vst",
    )
    if vst != {
        "repository": "https://github.com/PrincetonUniversity/VST.git",
        "revision": "cbee87efb4bee2b588f8321e16b4cb7664d5cf60",
        "version": "2.16",
    }:
        raise ProofBuildError("unsupported VST source pin")
    if GIT_REVISION_RE.fullmatch(vst["revision"]) is None:
        raise ProofBuildError("VST revision is not a full Git revision")


def _validate_proof_project(value: Any) -> None:
    project = _exact_object(
        value,
        {
            "architecture_obligation",
            "blockers",
            "checker_definition",
            "checker_id_source",
            "execution_ready",
            "required_files",
            "source_trace",
            "specification_id",
            "verification_theorem_id",
            "verified_function_id",
        },
        "proof_project",
    )
    expected_identity = {
        "architecture_obligation": (
            "ArchitectureExecutionSuppliesSuccessfulPureEntry"
        ),
        "checker_definition": "successfulPureEntryChecker",
        "checker_id_source": (
            "NativeImplementationIdentity.neutralContractId"
        ),
        "source_trace": "CSuccessfulPureEntryTrace",
        "specification_id": "sqrt218_vst_spec",
        "verification_theorem_id": (
            "body_tg_sq218_verify_snapshot_v2"
        ),
        "verified_function_id": "tg_sq218_verify_snapshot_v2",
    }
    for field, expected in expected_identity.items():
        if project[field] != expected:
            raise ProofBuildError(
                f"proof_project.{field} does not name the Lean source boundary"
            )
    if not isinstance(project["execution_ready"], bool):
        raise ProofBuildError("proof_project.execution_ready must be Boolean")
    blockers = project["blockers"]
    if not isinstance(blockers, list) or len(blockers) > 16:
        raise ProofBuildError("proof_project.blockers must be a bounded array")
    for index, blocker in enumerate(blockers):
        text = _string(blocker, f"proof_project.blockers[{index}]")
        if NAME_RE.fullmatch(text) is None:
            raise ProofBuildError("proof_project blocker is not canonical")
    if len(set(blockers)) != len(blockers):
        raise ProofBuildError("proof_project blockers must be unique")

    pins = project["required_files"]
    if not isinstance(pins, list) or len(pins) != len(PROOF_PATHS):
        raise ProofBuildError("proof_project must name exactly two proof files")
    for index, pin_value in enumerate(pins):
        pin = _file_pin(
            pin_value,
            f"proof_project.required_files[{index}]",
            nullable=True,
        )
        if pin["path"] != PROOF_PATHS[index]:
            raise ProofBuildError("proof_project file order or path is wrong")
        if project["execution_ready"] and pin["sha256"] is None:
            raise ProofBuildError("a ready proof project requires complete pins")
        if not project["execution_ready"] and pin["sha256"] is not None:
            raise ProofBuildError(
                "an unready proof project cannot carry partial authority pins"
            )
    if project["execution_ready"] != (not blockers):
        raise ProofBuildError(
            "proof readiness and explicit blockers are inconsistent"
        )


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate the closed command plan without invoking its toolchain."""

    manifest = _exact_object(value, TOP_LEVEL_KEYS, "proof-build manifest")
    if manifest["kind"] != LANE_KIND:
        raise ProofBuildError("unsupported proof-build manifest kind")
    if (
        isinstance(manifest["schema_version"], bool)
        or manifest["schema_version"] != SCHEMA_VERSION
    ):
        raise ProofBuildError("unsupported proof-build schema_version")
    if manifest["authority"] != AUTHORITY:
        raise ProofBuildError("proof-build authority block must remain false")

    claimed = _digest(manifest["manifest_sha256"], "manifest_sha256")
    body = {key: manifest[key] for key in sorted(BODY_KEYS)}
    expected = sha256_bytes(canonical_json_bytes(body))
    if claimed != expected:
        raise ProofBuildError(
            "manifest_sha256 does not match the canonical manifest body"
        )

    _validate_toolchain(manifest["toolchain"])
    container = _exact_object(
        manifest["container"],
        {
            "base_image",
            "base_platform",
            "dockerfile",
            "entrypoint",
            "final_image_must_be_registry_digest_pinned",
        },
        "container",
    )
    match = IMAGE_BY_DIGEST_RE.fullmatch(
        _string(container["base_image"], "container.base_image")
    )
    if match is None:
        raise ProofBuildError("container base image must be pinned by digest")
    if container["base_platform"] != "linux/amd64":
        raise ProofBuildError("container platform must be linux/amd64")
    if (
        container["entrypoint"]
        != "/opt/sparkinterval/run_cloud_proof_build.sh"
        or container["final_image_must_be_registry_digest_pinned"] is not True
    ):
        raise ProofBuildError("container entrypoint or digest policy is wrong")
    dockerfile = _file_pin(container["dockerfile"], "container.dockerfile")
    if dockerfile["path"] != "proof_build/sqrt218/Dockerfile":
        raise ProofBuildError("container Dockerfile path is unsupported")
    if (
        match.group("digest")
        != manifest["toolchain"]["rocq"]["base_image_digest"]
    ):
        raise ProofBuildError("Rocq base image digest bindings differ")

    pins = manifest["source_inputs"]
    if not isinstance(pins, list) or len(pins) != len(SOURCE_PATHS):
        raise ProofBuildError("source_inputs must contain the closed source set")
    for index, value_pin in enumerate(pins):
        pin = _file_pin(value_pin, f"source_inputs[{index}]")
        if pin["path"] != SOURCE_PATHS[index]:
            raise ProofBuildError("source input order or path is wrong")

    _validate_proof_project(manifest["proof_project"])

    pipeline = _exact_object(
        manifest["pipeline"],
        {
            "entry_symbol",
            "ordered_steps",
            "preprocessing_is_outside_verified_compcert",
            "proof_run_reads_production_certificate",
            "system_assembler_and_linker_are_outside_verified_compcert",
            "target",
            "vst_statement_proves_clight_not_elf_or_physical_cpu",
        },
        "pipeline",
    )
    if (
        pipeline["entry_symbol"] != "tg_sq218_verify_snapshot_v2"
        or pipeline["target"] != "x86_64-linux"
        or tuple(pipeline["ordered_steps"]) != ORDERED_STEPS
        or pipeline["preprocessing_is_outside_verified_compcert"] is not True
        or pipeline["proof_run_reads_production_certificate"] is not False
        or pipeline[
            "system_assembler_and_linker_are_outside_verified_compcert"
        ]
        is not True
        or pipeline[
            "vst_statement_proves_clight_not_elf_or_physical_cpu"
        ]
        is not True
    ):
        raise ProofBuildError("proof-build pipeline boundary or order is wrong")

    azure = _exact_object(
        manifest["azure"],
        {
            "acr_build_argv",
            "acr_resolve_digest_argv",
            "aci_run_argv",
            "final_image_digest_required",
            "network_policy",
            "workspace_mount",
        },
        "azure",
    )
    acr_argv = _argv(azure["acr_build_argv"], "azure.acr_build_argv")
    resolve_argv = _argv(
        azure["acr_resolve_digest_argv"],
        "azure.acr_resolve_digest_argv",
    )
    aci_argv = _argv(azure["aci_run_argv"], "azure.aci_run_argv")
    if acr_argv[:3] != ["az", "acr", "build"]:
        raise ProofBuildError("Azure image build argv is not closed")
    if aci_argv[:3] != ["az", "container", "create"]:
        raise ProofBuildError("Azure proof-run argv is not closed")
    if resolve_argv[:4] != ["az", "acr", "manifest", "show-metadata"]:
        raise ProofBuildError("Azure digest-resolution argv is not closed")
    if (
        "${FINAL_IMAGE_DIGEST}" not in " ".join(aci_argv)
        or "--acr-identity" not in aci_argv
        or "--vnet" not in aci_argv
        or "--subnet" not in aci_argv
        or azure["final_image_digest_required"] is not True
        or azure["workspace_mount"] != "/workspace"
        or azure["network_policy"]
        != "toolchain-image-build-official-source-egress-proof-run-operator-deny-egress-vnet-required"
    ):
        raise ProofBuildError("Azure digest, mount, or network policy is wrong")

    outputs = _exact_object(
        manifest["evidence_outputs"],
        set(EVIDENCE_OUTPUTS),
        "evidence_outputs",
    )
    if outputs != EVIDENCE_OUTPUTS:
        raise ProofBuildError(
            "evidence output mapping does not match the compiler schema lane"
        )
    for key, output_path in outputs.items():
        _relative_path(output_path, f"evidence_outputs.{key}")
    return manifest


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise ProofBuildError("proof-build manifest bytes must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ProofBuildError("proof-build manifest is too large")
    try:
        value = parse_json_bytes(raw, label="Sqrt218 proof-build manifest")
    except CampaignIOError as exc:
        raise ProofBuildError(str(exc)) from exc
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as exc:
        raise ProofBuildError(str(exc)) from exc
    return validate_manifest_bytes(raw)


def _safe_path(root: Path, relative: str, label: str) -> Path:
    _relative_path(relative, label)
    root_resolved = root.resolve(strict=True)
    path = root_resolved.joinpath(*PurePosixPath(relative).parts)
    if path.is_symlink() or not path.is_file():
        raise ProofBuildError(f"{label} is missing, not regular, or a symlink")
    try:
        path.resolve(strict=True).relative_to(root_resolved)
    except ValueError as exc:
        raise ProofBuildError(f"{label} escapes its root") from exc
    return path


def _check_pin(root: Path, pin: Mapping[str, Any], label: str) -> None:
    path = _safe_path(root, pin["path"], label)
    before = path.stat()
    if before.st_size > MAX_SOURCE_BYTES:
        raise ProofBuildError(f"{label} exceeds the source size bound")
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda stat: (
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    )
    if identity(before) != identity(after):
        raise ProofBuildError(f"{label} changed while read")
    if len(raw) != pin["size_bytes"]:
        raise ProofBuildError(f"{label} size does not match its pin")
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ProofBuildError(f"{label} SHA-256 does not match its pin")


def validate_inputs(
    manifest: Any,
    repository_root: Path,
    *,
    proof_root: Path | None = None,
    require_ready: bool = False,
) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    for index, pin in enumerate(checked["source_inputs"]):
        _check_pin(
            repository_root, pin, f"source_inputs[{index}]"
        )
    dockerfile = checked["container"]["dockerfile"]
    _check_pin(repository_root, dockerfile, "container.dockerfile")

    project = checked["proof_project"]
    if require_ready and project["execution_ready"] is not True:
        raise ProofBuildError(
            "proof build is not execution-ready: "
            + ", ".join(project["blockers"])
        )
    if project["execution_ready"]:
        if proof_root is None:
            raise ProofBuildError("a ready proof build requires --proof-root")
        for index, pin in enumerate(project["required_files"]):
            _check_pin(proof_root, pin, f"proof_project.required_files[{index}]")
    return checked


def source_closure(
    manifest: Any,
    repository_root: Path,
    proof_root: Path | None,
) -> dict[str, Any]:
    checked = validate_inputs(
        manifest,
        repository_root,
        proof_root=proof_root,
        require_ready=True,
    )
    return {
        "artifact_bytes_read": True,
        "authorizes_lean_theorem": False,
        "kind": SOURCE_CLOSURE_KIND,
        "lane_manifest_sha256": checked["manifest_sha256"],
        "production_certificate_opened": False,
        "proof_files": checked["proof_project"]["required_files"],
        "schema_version": 1,
        "source_files": checked["source_inputs"],
    }


def _artifact_pin(root: Path, relative: str, label: str) -> dict[str, Any]:
    path = _safe_path(root, relative, label)
    before = path.stat()
    if before.st_size > MAX_ARTIFACT_BYTES:
        raise ProofBuildError(f"{label} exceeds the retained artifact bound")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    after = path.stat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ProofBuildError(f"{label} changed while hashed")
    if size <= 0:
        raise ProofBuildError(f"{label} must be nonempty")
    return {"path": relative, "sha256": digest.hexdigest(), "size_bytes": size}


def artifact_index(
    manifest: Any,
    output_root: Path,
    final_image_reference: str,
) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    if IMAGE_BY_DIGEST_RE.fullmatch(final_image_reference) is None:
        raise ProofBuildError("final image must be pinned by registry digest")
    artifacts = {
        key: _artifact_pin(output_root, relative, f"evidence output {key}")
        for key, relative in checked["evidence_outputs"].items()
    }
    for step in ORDERED_STEPS[:-1]:
        exit_path = _safe_path(
            output_root,
            f"commands/{step}.exit-code",
            f"{step} exit record",
        )
        if exit_path.read_bytes() != b"0\n":
            raise ProofBuildError(f"{step} did not retain exact exit code zero")

    tools: dict[str, dict[str, Any]] = {}
    for name in TOOL_EXECUTABLES:
        resolved = shutil.which(name)
        if resolved is None:
            raise ProofBuildError(f"required tool is missing: {name}")
        path = Path(resolved)
        if not path.is_file():
            raise ProofBuildError(f"required tool is not a file: {name}")
        raw = path.read_bytes()
        if not raw:
            raise ProofBuildError(f"required tool is empty: {name}")
        tools[name] = {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    return {
        "architecture_execution_proved": False,
        "artifacts": artifacts,
        "authorizes_lean_theorem": False,
        "compiler_correctness_established_by_index": False,
        "final_image_reference": final_image_reference,
        "kind": ARTIFACT_INDEX_KIND,
        "lane_manifest_sha256": checked["manifest_sha256"],
        "production_certificate_opened": False,
        "production_execution_performed": False,
        "schema_version": 1,
        "tools": tools,
        "valex": {
            "reason": (
                "Valex is not distributed in the pinned public toolchain; "
                "the assembler/linker/ELF boundary remains explicit."
            ),
            "status": "unsupported",
        },
    }


def review_summary(manifest: Any) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    return {
        "architecture_execution_proved": False,
        "authorizes_lean_theorem": False,
        "base_image": checked["container"]["base_image"],
        "compcert_revision": checked["toolchain"]["compcert"]["revision"],
        "execution_ready": checked["proof_project"]["execution_ready"],
        "kind": LANE_KIND,
        "lane_manifest_sha256": checked["manifest_sha256"],
        "lean_checker_definition": checked["proof_project"][
            "checker_definition"
        ],
        "lean_source_trace": checked["proof_project"]["source_trace"],
        "production_certificate_opened": False,
        "vst_revision": checked["toolchain"]["vst"]["revision"],
    }


__all__ = [
    "ARTIFACT_INDEX_KIND",
    "AUTHORITY",
    "EVIDENCE_OUTPUTS",
    "LANE_KIND",
    "MAX_MANIFEST_BYTES",
    "ORDERED_STEPS",
    "PROOF_PATHS",
    "ProofBuildError",
    "SCHEMA_VERSION",
    "SOURCE_CLOSURE_KIND",
    "SOURCE_PATHS",
    "artifact_index",
    "load_manifest",
    "review_summary",
    "source_closure",
    "validate_inputs",
    "validate_manifest",
    "validate_manifest_bytes",
]
