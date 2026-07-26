# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate the metadata-only Sqrt218 compiler-discovery lane.

Validation is intentionally bounded to the manifest bytes.  This module does
not inspect source files or artifacts and never invokes a compiler, linker,
container, executable, or production Sqrt218 computation.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 1
LANE_KIND = "sparkinterval.sqrt218-compiler-discovery-lane.v1"
MAX_MANIFEST_BYTES = 256 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA512_RE = re.compile(r"^[0-9a-f]{128}$")
RELATIVE_PATH_RE = re.compile(
    r"^(?!/)(?!\.\.(?:/|$))(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*$"
)

AUTHORITY = {
    "architecture_execution_proved": False,
    "authorizes_lean_theorem": False,
    "authorizes_receipt": False,
    "compiler_correctness_proved": False,
    "elf_loader_correctness_proved": False,
    "instruction_decoder_correctness_proved": False,
    "isa_correctness_proved": False,
    "production_certificate_opened": False,
    "production_execution_performed": False,
    "vst_proof_present": False,
}

CLOUD_POLICY = {
    "blockers": [
        "missing-pinned-discovery-container-and-runner",
    ],
    "cloud_only": True,
    "execution_ready": False,
    "generated_elf_execution_allowed": False,
    "local_tool_invocation_allowed": False,
    "network_policy": (
        "operator-deny-egress-discovery-run-required"
    ),
    "production_certificate_access_allowed": False,
    "requires_final_image_registry_digest": True,
}

SCOPE = {
    "downstream_unproved_obligation": (
        "ArchitectureExecutionSuppliesSuccessfulPureEntry"
    ),
    "entry_symbol": "tg_sq218_verify_snapshot_v2",
    "function_entry_elf_classification": (
        "function-entry-analysis-only-not-linux-process-start"
    ),
    "linux_startup_wrapper_present": False,
    "purpose": "mm0-derived-lean4-x86-model-opcode-scoping-only",
    "sysv_direct_call_initial_state_remains_unproved": True,
}

ELF_GATE = {
    "all_pt_load_rows_count_permissions_recorded": True,
    "duplicate_entry_symbol_rejected": True,
    "dynamic_dependencies_rejected": True,
    "entry_must_equal_unique_defined_global_function": True,
    "interpreter_rejected": True,
    "relocations_in_final_elf_rejected": True,
    "undefined_final_symbols_rejected": True,
    "writable_executable_segments_rejected": True,
}

INVENTORY_CONTRACT = {
    "aggregate_keys": [
        "exact_prefix_sequence",
        "candidate_opcode_bytes",
        "mnemonic_and_normalized_operand_form",
    ],
    "decoder_authoritative_for_x86_semantics": False,
    "direct_cfg_closure_complete_required": True,
    "every_aggregate_form_has_gap_tags": True,
    "every_instruction_has_gap_tags": True,
    "exact_instruction_fields": [
        "virtual_address",
        "file_offset",
        "raw_bytes",
        "length",
        "legacy_prefix_bytes",
        "rex_prefix_bytes",
        "encoding_family",
        "candidate_opcode_bytes",
        "mnemonic",
        "normalized_operands",
        "direct_targets",
        "fallthrough",
    ],
    "reachability_classification": (
        "objdump-derived-direct-cfg-closure-not-semantic-proof"
    ),
    "required_gap_tags": [
        "operand-size-prefix-0x66",
        "imul-two-or-three-operand",
        "bswap",
        "shld",
        "sse-or-xmm",
        "rol-or-ror",
        "vex",
        "evex",
        "unknown-encoding-form",
    ],
    "reject_conditions": [
        "decoder-disagreement-with-elf-bytes",
        "duplicate-instruction-address",
        "indirect-call-or-jump",
        "target-into-instruction-middle",
        "target-outside-executable-load",
        "unknown-control-transfer",
        "unresolved-direct-target",
    ],
}

TOOLCHAIN = {
    "binutils": {
        "source_sha512": (
            "b85d3bbc0e334cf67a96219d3c7c65fbf3e832b2c98a7417bf131f3645a03070"
            "57ec81cd2b29ff2563cec53e3d42f73e2c60cc5708e80d4a730efdcc6ae14ad7"
        ),
        "source_url": (
            "https://sourceware.org/pub/binutils/releases/"
            "binutils-2.44.tar.xz"
        ),
        "version": "2.44",
    },
    "compcert": {
        "configuration": "x86_64-linux",
        "repository": "https://github.com/AbsInt/CompCert.git",
        "revision": "7b1f02b09954b9b916eb2a91d283c9b5355bf172",
        "tag": "v3.17",
        "version": "3.17",
    },
    "rocq_base_image": {
        "image": (
            "docker.io/rocq/rocq-prover@sha256:"
            "b85a80a11bb65c7c843f91c7cbcce282f22ee397c9ca42f123d568ab6cef68b0"
        ),
        "version": "9.1.1",
    },
}

SOURCE_INPUTS = (
    {
        "path": "cpu_checker/sqrt218/sqrt218_cpu_checker.c",
        "sha256": "9444117c43f4fde219d24dbc33fba29c8b59aa91a146b88b2f83ccb7add80b6a",
        "size_bytes": 41978,
    },
    {
        "path": "cpu_checker/sqrt218/sqrt218_cpu_command.c",
        "sha256": "b7aa9e740f221d1ba12913b44d05acb5587b725316e164697abfe01385c627cb",
        "size_bytes": 16141,
    },
    {
        "path": "cpu_checker/sqrt218/sqrt218_cpu_checker.h",
        "sha256": "7bbca1f910ff436517a565a975f9f014252ccd8aca48ee9e0a3d6bd4f6fdc0f4",
        "size_bytes": 7421,
    },
    {
        "path": "cpu_checker/sqrt218/sqrt218_cpu_command.h",
        "sha256": "e0a1a579122db51c4ad3d9504663175df86e509eaac80a07ae926564bfc38cf5",
        "size_bytes": 2844,
    },
    {
        "path": "proof_build/sqrt218/sqrt218_pure_entry_unit.c",
        "sha256": "7298b3cc405d40b23f6b6ac4a9ebf57bda64954ef23d9757a345fb3092f6969f",
        "size_bytes": 652,
    },
)

ORDERED_STEPS = (
    "source_closure",
    "preprocess",
    "csyntaxgen",
    "clightgen",
    "compcert",
    "assembler",
    "object_inspection",
    "linker",
    "elf_inspection",
    "raw_objdump",
    "direct_cfg_inventory",
    "artifact_index",
)

COMMANDS = (
    {
        "step": "preprocess",
        "argv": [
            "ccomp", "-E", "-std=c11", "-fnone", "-Wall", "-Werror",
            "-DTG_SQ218_PURE_ENTRY_ONLY=1",
            "-I${REPOSITORY_ROOT}/cpu_checker/sqrt218",
            "-o", "${WORK}/sqrt218_pure_entry.i",
            "${REPOSITORY_ROOT}/proof_build/sqrt218/sqrt218_pure_entry_unit.c",
        ],
    },
    {
        "step": "csyntaxgen",
        "argv": [
            "clightgen", "-csyntax", "-canonical-idents", "-fnone",
            "-Wall", "-Werror", "-o", "${WORK}/Sqrt218CompCertC.v",
            "${WORK}/sqrt218_pure_entry.i",
        ],
    },
    {
        "step": "clightgen",
        "argv": [
            "clightgen", "-clight", "-normalize", "-canonical-idents",
            "-fnone", "-Wall", "-Werror", "-dc", "-dclight", "-o",
            "${WORK}/Sqrt218Clight.v", "${WORK}/sqrt218_pure_entry.i",
        ],
    },
    {
        "step": "compcert",
        "argv": [
            "ccomp", "-S", "-sdump", "-dc", "-dclight", "-std=c11",
            "-fnone", "-Wall", "-Werror", "-fno-pie", "-o",
            "${WORK}/sqrt218_pure_entry.s",
            "${WORK}/sqrt218_pure_entry.i",
        ],
    },
    {
        "step": "assembler",
        "argv": [
            "as", "--64", "--fatal-warnings", "-o",
            "${WORK}/sqrt218_pure_entry.o",
            "${WORK}/sqrt218_pure_entry.s",
        ],
    },
    {
        "step": "linker",
        "argv": [
            "ld", "-m", "elf_x86_64", "-static", "-no-pie",
            "--no-dynamic-linker", "--gc-sections", "--build-id=none",
            "--entry=tg_sq218_verify_snapshot_v2",
            "--require-defined=tg_sq218_verify_snapshot_v2",
            "--no-undefined", "--fatal-warnings", "-z", "noexecstack",
            "-z", "separate-code", "-z", "text",
            "-Map=${OUTPUT}/retained/sqrt218-link.map", "-o",
            "${OUTPUT}/retained/sqrt218_pure_entry.elf",
            "${WORK}/sqrt218_pure_entry.o",
        ],
    },
    {
        "step": "raw_objdump",
        "argv": [
            "objdump", "--disassemble", "--disassemble-zeroes", "--wide",
            "--show-raw-insn", "--insn-width=15", "-Mintel",
            "${OUTPUT}/retained/sqrt218_pure_entry.elf",
        ],
    },
)

RETAINED_ARTIFACTS = (
    "retained/source-closure.json",
    "retained/sqrt218_pure_entry.i",
    "retained/Sqrt218CompCertC.v",
    "retained/Sqrt218Clight.v",
    "retained/sqrt218_pure_entry.compcert.c",
    "retained/sqrt218_pure_entry.light.c",
    "retained/sqrt218_pure_entry.sdump",
    "retained/sqrt218_pure_entry.s",
    "retained/sqrt218_pure_entry.o",
    "retained/sqrt218_pure_entry.elf",
    "retained/sqrt218-link.map",
    "retained/object-readelf-all.txt",
    "retained/elf-readelf-header.txt",
    "retained/elf-readelf-program-headers.txt",
    "retained/elf-readelf-section-headers.txt",
    "retained/elf-readelf-symbols.txt",
    "retained/elf-readelf-dynamic.txt",
    "retained/elf-readelf-relocations.txt",
    "retained/elf-objdump-raw.txt",
    "retained/direct-cfg-instructions.ndjson",
    "retained/mnemonic-operand-form-inventory.json",
    "retained/prefix-form-inventory.json",
    "retained/opcode-form-inventory.json",
    "retained/undefined-symbol-report.json",
    "retained/elf-structural-audit.json",
    "retained/artifact-index.json",
)

TOP_LEVEL_KEYS = {
    "authority",
    "cloud_policy",
    "elf_gate",
    "inventory_contract",
    "kind",
    "manifest_sha256",
    "pipeline",
    "retained_artifacts",
    "schema_version",
    "scope",
    "source_inputs",
    "toolchain",
}
BODY_KEYS = TOP_LEVEL_KEYS - {"manifest_sha256"}


class CompilerDiscoveryError(ValueError):
    """The discovery metadata is malformed or attempts to claim authority."""


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CompilerDiscoveryError(f"{label} has wrong fields")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CompilerDiscoveryError(f"{label} must be lowercase SHA-256")
    if value == "0" * 64:
        raise CompilerDiscoveryError(f"{label} cannot be zero")
    return value


def _relative_path(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or RELATIVE_PATH_RE.fullmatch(value) is None
    ):
        raise CompilerDiscoveryError(f"{label} is not a safe relative path")
    return value


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate only the canonical discovery metadata."""

    manifest = _exact_object(value, TOP_LEVEL_KEYS, "discovery manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CompilerDiscoveryError("unsupported schema_version")
    if manifest["kind"] != LANE_KIND:
        raise CompilerDiscoveryError("unsupported manifest kind")
    if manifest["authority"] != AUTHORITY:
        raise CompilerDiscoveryError("all discovery authority fields must be false")
    if manifest["cloud_policy"] != CLOUD_POLICY:
        raise CompilerDiscoveryError("cloud policy/readiness must remain fail-closed")
    if manifest["scope"] != SCOPE:
        raise CompilerDiscoveryError("discovery scope is not exact")
    if manifest["elf_gate"] != ELF_GATE:
        raise CompilerDiscoveryError("ELF gate is not exact")
    if manifest["inventory_contract"] != INVENTORY_CONTRACT:
        raise CompilerDiscoveryError("instruction inventory contract is not exact")
    if manifest["toolchain"] != TOOLCHAIN:
        raise CompilerDiscoveryError("toolchain pins are not exact")
    if SHA512_RE.fullmatch(
        manifest["toolchain"]["binutils"]["source_sha512"]
    ) is None:
        raise CompilerDiscoveryError("Binutils source SHA-512 is malformed")

    sources = manifest["source_inputs"]
    if sources != list(SOURCE_INPUTS):
        raise CompilerDiscoveryError("source pins are not the closed source set")
    for index, pin in enumerate(sources):
        _exact_object(
            pin, {"path", "sha256", "size_bytes"}, f"source_inputs[{index}]"
        )
        _relative_path(pin["path"], f"source_inputs[{index}].path")
        _digest(pin["sha256"], f"source_inputs[{index}].sha256")
        if (
            isinstance(pin["size_bytes"], bool)
            or not isinstance(pin["size_bytes"], int)
            or pin["size_bytes"] <= 0
        ):
            raise CompilerDiscoveryError("source size pin must be positive")

    pipeline = _exact_object(
        manifest["pipeline"], {"commands", "ordered_steps"}, "pipeline"
    )
    if pipeline["ordered_steps"] != list(ORDERED_STEPS):
        raise CompilerDiscoveryError("discovery step order is not exact")
    if pipeline["commands"] != list(COMMANDS):
        raise CompilerDiscoveryError("discovery command templates are not exact")

    if manifest["retained_artifacts"] != list(RETAINED_ARTIFACTS):
        raise CompilerDiscoveryError("retained artifact set is not exact")
    for index, path in enumerate(manifest["retained_artifacts"]):
        _relative_path(path, f"retained_artifacts[{index}]")

    claimed = _digest(manifest["manifest_sha256"], "manifest_sha256")
    body = {key: manifest[key] for key in sorted(BODY_KEYS)}
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        raise CompilerDiscoveryError("manifest self-hash does not match")
    return manifest


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise CompilerDiscoveryError("manifest input must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise CompilerDiscoveryError("manifest exceeds size bound")
    try:
        value = parse_json_bytes(raw, label="Sqrt218 discovery manifest")
    except CampaignIOError as exc:
        raise CompilerDiscoveryError(str(exc)) from exc
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    """Read exactly one bounded manifest; no pinned source/artifact is opened."""

    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as exc:
        raise CompilerDiscoveryError(str(exc)) from exc
    return validate_manifest_bytes(raw)


def review_summary(manifest: Any) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    return {
        "architecture_execution_proved": False,
        "authorizes_lean_theorem": False,
        "authorizes_receipt": False,
        "cloud_only": True,
        "execution_ready": False,
        "function_entry_is_linux_process_start": False,
        "generated_elf_execution_allowed": False,
        "kind": checked["kind"],
        "lane_manifest_sha256": checked["manifest_sha256"],
        "local_tool_invocation_allowed": False,
        "production_certificate_opened": False,
        "retained_artifact_count": len(checked["retained_artifacts"]),
    }


__all__ = [
    "AUTHORITY",
    "BODY_KEYS",
    "CLOUD_POLICY",
    "COMMANDS",
    "CompilerDiscoveryError",
    "ELF_GATE",
    "INVENTORY_CONTRACT",
    "LANE_KIND",
    "MAX_MANIFEST_BYTES",
    "ORDERED_STEPS",
    "RETAINED_ARTIFACTS",
    "SCHEMA_VERSION",
    "SCOPE",
    "SOURCE_INPUTS",
    "TOOLCHAIN",
    "load_manifest",
    "review_summary",
    "validate_manifest",
    "validate_manifest_bytes",
]
