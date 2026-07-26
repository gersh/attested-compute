# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate the compact evidence index for the Sqrt218 CPU build.

This module does not run a compiler, proof checker, assembler, linker, binary,
or production certificate replay.  It validates one bounded canonical JSON
record containing only logical identifiers, byte sizes, digests, tool
identities, and an explicit residual-trust inventory.

In particular, a valid record is *evidence metadata*.  It is not a Lean
theorem, a trusted-compute receipt, an attestation appraisal, or proof that the
artifacts named by its digests exist or have the claimed semantics.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 2
MANIFEST_KIND = "sparkinterval.sqrt218-compiler-evidence-manifest.v2"
MAX_MANIFEST_BYTES = 256 * 1024
EXECUTION_CLOSURE_METADATA_KIND = (
    "sparkinterval.sqrt218-execution-closure-identity.v1"
)
EXECUTION_CLOSURE_PROJECTION_KIND = (
    "sparkinterval.sqrt218-execution-closure-projection.v1"
)
EXECUTION_CLOSURE_PROJECTION_SCHEMA_VERSION = 1
EXECUTION_CLOSURE_TARGET = "azure_sevsnp_cpu"
EXECUTION_CLOSURE_METADATA_FIELDS = (
    "compiler_evidence_manifest_version",
    "compiler_evidence_manifest_sha256",
    "compiler_source_sha256",
    "compiler_id",
    "compiler_version",
    "compiler_binary_sha256",
    "compiler_configuration_sha256",
    "formal_architecture_model_sha256",
    "target",
    "sysv_abi_contract_sha256",
    "neutral_contract_id",
    "neutral_contract_sha256",
    "elf_sha256",
    "entry_point",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{7,64}$")
ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._:/+@-]{0,191}$")
WORD64_HEX_RE = re.compile(r"^[0-9a-f]{16}$")

AUTHORITY_BLOCK = {
    "authorizes_lean_theorem": False,
    "authorizes_receipt": False,
    "classification": "evidence-index-only-not-proof-or-authority",
    "compiler_correctness_established_by_manifest": False,
    "machine_code_refinement_established_by_manifest": False,
    "production_execution_performed": False,
    "validation_scope": "canonical-shape-digests-and-chain-consistency-only",
}

REQUIRED_RESIDUAL_TRUST = frozenset(
    {
        "azure_attestation_appraisal",
        "compcert_extraction_and_compiler_executable",
        "cross_prover_contract_equivalence",
        "preprocessing_and_clight_generation",
        "rocq_kernel_vst_compcert_assumptions",
        "signing_key_registry_and_lean_admission",
        "system_assembler_linker_and_elf_tools",
        "x86_64_abi_loader_and_os_runtime",
        "x86_64_cpu_conformance",
    }
)

_ROOT_KEYS = {
    "authority",
    "build_chain",
    "contracts",
    "kind",
    "manifest_sha256",
    "residual_trust",
    "schema_version",
}
_BODY_KEYS = _ROOT_KEYS - {"manifest_sha256"}
_ARTIFACT_KEYS = {"artifact_id", "sha256", "size_bytes"}


class CompilerEvidenceError(ValueError):
    """The compiler-evidence index is malformed or internally inconsistent."""


def _exact_object(
    value: Any, expected: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CompilerEvidenceError(f"{label} must be an object")
    actual = set(value)
    if actual != set(expected):
        raise CompilerEvidenceError(
            f"{label} has wrong fields "
            f"(missing={sorted(set(expected) - actual)}, "
            f"unexpected={sorted(actual - set(expected))})"
        )
    return value


def _string(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 512,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) < minimum
        or len(value) > maximum
        or "\x00" in value
    ):
        raise CompilerEvidenceError(
            f"{label} must be a non-NUL string of length {minimum}..{maximum}"
        )
    return value


def _identifier(value: Any, label: str) -> str:
    text = _string(value, label, maximum=192)
    if ID_RE.fullmatch(text) is None:
        raise CompilerEvidenceError(f"{label} is not a canonical identifier")
    return text


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        raise CompilerEvidenceError(
            f"{label} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _word64_hex(value: Any, label: str, *, nonzero: bool = False) -> str:
    if not isinstance(value, str) or WORD64_HEX_RE.fullmatch(value) is None:
        raise CompilerEvidenceError(
            f"{label} must be exactly 16 lowercase hexadecimal digits"
        )
    if nonzero and value == "0" * 16:
        raise CompilerEvidenceError(f"{label} must be nonzero")
    return value


def _nat(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompilerEvidenceError(f"{label} must be an integer")
    if value < (1 if positive else 0) or value > (1 << 63) - 1:
        qualifier = "positive " if positive else "nonnegative "
        raise CompilerEvidenceError(
            f"{label} must be a {qualifier}signed-64-bit integer"
        )
    return value


def _artifact(value: Any, label: str) -> dict[str, Any]:
    artifact = _exact_object(value, _ARTIFACT_KEYS, label)
    _identifier(artifact["artifact_id"], f"{label}.artifact_id")
    _digest(artifact["sha256"], f"{label}.sha256")
    _nat(artifact["size_bytes"], f"{label}.size_bytes", positive=True)
    return artifact


def _validate_contracts(value: Any) -> None:
    contracts = _exact_object(
        value, {"cross_prover_map", "lean", "neutral", "rocq"}, "contracts"
    )
    neutral = _exact_object(
        contracts["neutral"],
        {"contract_id", "contract_sha256", "format"},
        "contracts.neutral",
    )
    neutral_id = _identifier(
        neutral["contract_id"], "contracts.neutral.contract_id"
    )
    neutral_hash = _digest(
        neutral["contract_sha256"], "contracts.neutral.contract_sha256"
    )
    _identifier(neutral["format"], "contracts.neutral.format")

    lean = _exact_object(
        contracts["lean"],
        {
            "declaration_id",
            "neutral_contract_id",
            "neutral_contract_sha256",
            "source_sha256",
            "statement_sha256",
        },
        "contracts.lean",
    )
    _identifier(lean["declaration_id"], "contracts.lean.declaration_id")
    _digest(lean["source_sha256"], "contracts.lean.source_sha256")
    _digest(lean["statement_sha256"], "contracts.lean.statement_sha256")

    rocq = _exact_object(
        contracts["rocq"],
        {
            "neutral_contract_id",
            "neutral_contract_sha256",
            "source_sha256",
            "statement_sha256",
            "theorem_id",
        },
        "contracts.rocq",
    )
    _identifier(rocq["theorem_id"], "contracts.rocq.theorem_id")
    _digest(rocq["source_sha256"], "contracts.rocq.source_sha256")
    _digest(rocq["statement_sha256"], "contracts.rocq.statement_sha256")

    for prover, implementation in (("Lean", lean), ("Rocq", rocq)):
        if implementation["neutral_contract_id"] != neutral_id:
            raise CompilerEvidenceError(
                f"{prover} contract does not name the neutral contract"
            )
        if implementation["neutral_contract_sha256"] != neutral_hash:
            raise CompilerEvidenceError(
                f"{prover} contract does not bind the neutral contract digest"
            )

    mapping = _exact_object(
        contracts["cross_prover_map"],
        {"mapping_id", "mapping_sha256", "status"},
        "contracts.cross_prover_map",
    )
    _identifier(mapping["mapping_id"], "contracts.cross_prover_map.mapping_id")
    _digest(mapping["mapping_sha256"], "contracts.cross_prover_map.mapping_sha256")
    if mapping["status"] not in {
        "not_reviewed",
        "reviewed_not_machine_checked",
        "machine_checked_external_evidence",
    }:
        raise CompilerEvidenceError(
            "contracts.cross_prover_map.status is unsupported"
        )


def _validate_rocqchk(value: Any) -> None:
    if not isinstance(value, dict):
        raise CompilerEvidenceError("build_chain.vst.rocqchk must be an object")
    status = value.get("status")
    if status == "not_run":
        record = _exact_object(
            value, {"reason", "status"}, "build_chain.vst.rocqchk"
        )
        _string(record["reason"], "build_chain.vst.rocqchk.reason")
        return
    record = _exact_object(
        value,
        {
            "command_sha256",
            "executable",
            "exit_code",
            "status",
            "stderr",
            "stdout",
            "version",
        },
        "build_chain.vst.rocqchk",
    )
    if status not in {"passed", "failed"}:
        raise CompilerEvidenceError("build_chain.vst.rocqchk.status is unsupported")
    _artifact(record["executable"], "build_chain.vst.rocqchk.executable")
    _artifact(record["stdout"], "build_chain.vst.rocqchk.stdout")
    _artifact(record["stderr"], "build_chain.vst.rocqchk.stderr")
    _digest(record["command_sha256"], "build_chain.vst.rocqchk.command_sha256")
    exit_code = _nat(record["exit_code"], "build_chain.vst.rocqchk.exit_code")
    _string(record["version"], "build_chain.vst.rocqchk.version", maximum=256)
    if (status == "passed") != (exit_code == 0):
        raise CompilerEvidenceError(
            "rocqchk status and exit_code are inconsistent"
        )


def _validate_valex(value: Any, textual_assembly_sha256: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise CompilerEvidenceError("build_chain.valex must be null or an object")
    status = value.get("status")
    if status in {"not_run", "unsupported"}:
        record = _exact_object(
            value, {"reason", "status"}, "build_chain.valex"
        )
        _string(record["reason"], "build_chain.valex.reason")
        return
    record = _exact_object(
        value,
        {
            "command_sha256",
            "exit_code",
            "report",
            "status",
            "tool",
            "validated_assembly_sha256",
            "version",
        },
        "build_chain.valex",
    )
    if status not in {"passed", "failed"}:
        raise CompilerEvidenceError("build_chain.valex.status is unsupported")
    _artifact(record["tool"], "build_chain.valex.tool")
    _artifact(record["report"], "build_chain.valex.report")
    _digest(record["command_sha256"], "build_chain.valex.command_sha256")
    validated = _digest(
        record["validated_assembly_sha256"],
        "build_chain.valex.validated_assembly_sha256",
    )
    _string(record["version"], "build_chain.valex.version", maximum=256)
    exit_code = _nat(record["exit_code"], "build_chain.valex.exit_code")
    if validated != textual_assembly_sha256:
        raise CompilerEvidenceError(
            "Valex evidence does not bind the CompCert textual assembly"
        )
    if (status == "passed") != (exit_code == 0):
        raise CompilerEvidenceError("Valex status and exit_code are inconsistent")


def _validate_build_chain(value: Any) -> None:
    chain = _exact_object(
        value,
        {
            "assembler",
            "c_translation",
            "compcert",
            "elf",
            "formal_architecture",
            "linker",
            "valex",
            "vst",
        },
        "build_chain",
    )
    translation = _exact_object(
        chain["c_translation"],
        {
            "clight_ast",
            "compcert_c_ast",
            "preprocessed_source",
            "source",
        },
        "build_chain.c_translation",
    )
    for name in ("source", "preprocessed_source", "compcert_c_ast", "clight_ast"):
        _artifact(
            translation[name], f"build_chain.c_translation.{name}"
        )

    vst = _exact_object(
        chain["vst"],
        {
            "assumptions_report",
            "proof_bundle",
            "rocqchk",
            "specification_id",
            "verification_theorem_id",
            "verified_function_id",
        },
        "build_chain.vst",
    )
    _artifact(vst["proof_bundle"], "build_chain.vst.proof_bundle")
    _artifact(vst["assumptions_report"], "build_chain.vst.assumptions_report")
    for field in (
        "specification_id",
        "verification_theorem_id",
        "verified_function_id",
    ):
        _identifier(vst[field], f"build_chain.vst.{field}")
    _validate_rocqchk(vst["rocqchk"])

    compcert = _exact_object(
        chain["compcert"],
        {
            "abstract_assembly",
            "clight_ast_sha256",
            "command_sha256",
            "compcert_c_ast_sha256",
            "configuration",
            "executable",
            "exit_code",
            "compiler_id",
            "preprocessed_input_sha256",
            "source_revision",
            "textual_assembly",
            "version",
        },
        "build_chain.compcert",
    )
    _identifier(compcert["compiler_id"], "build_chain.compcert.compiler_id")
    _string(compcert["version"], "build_chain.compcert.version", maximum=128)
    revision = _string(
        compcert["source_revision"],
        "build_chain.compcert.source_revision",
        maximum=64,
    )
    if REVISION_RE.fullmatch(revision) is None:
        raise CompilerEvidenceError(
            "build_chain.compcert.source_revision must be lowercase hex"
        )
    for field in (
        "executable",
        "configuration",
        "abstract_assembly",
        "textual_assembly",
    ):
        _artifact(compcert[field], f"build_chain.compcert.{field}")
    _digest(compcert["command_sha256"], "build_chain.compcert.command_sha256")
    if _nat(compcert["exit_code"], "build_chain.compcert.exit_code") != 0:
        raise CompilerEvidenceError("CompCert exit_code must be zero")

    digest_links = (
        (
            "preprocessed_input_sha256",
            translation["preprocessed_source"]["sha256"],
        ),
        ("compcert_c_ast_sha256", translation["compcert_c_ast"]["sha256"]),
        ("clight_ast_sha256", translation["clight_ast"]["sha256"]),
    )
    for field, expected in digest_links:
        actual = _digest(
            compcert[field], f"build_chain.compcert.{field}"
        )
        if actual != expected:
            raise CompilerEvidenceError(
                f"CompCert {field} does not bind c_translation"
            )

    assembler = _exact_object(
        chain["assembler"],
        {
            "command_sha256",
            "executable",
            "exit_code",
            "input_assembly_sha256",
            "output_object",
            "tool_id",
            "version",
        },
        "build_chain.assembler",
    )
    _identifier(assembler["tool_id"], "build_chain.assembler.tool_id")
    _string(assembler["version"], "build_chain.assembler.version", maximum=256)
    _artifact(assembler["executable"], "build_chain.assembler.executable")
    _artifact(assembler["output_object"], "build_chain.assembler.output_object")
    _digest(assembler["command_sha256"], "build_chain.assembler.command_sha256")
    if _nat(assembler["exit_code"], "build_chain.assembler.exit_code") != 0:
        raise CompilerEvidenceError("assembler exit_code must be zero")
    assembly_input = _digest(
        assembler["input_assembly_sha256"],
        "build_chain.assembler.input_assembly_sha256",
    )
    if assembly_input != compcert["textual_assembly"]["sha256"]:
        raise CompilerEvidenceError(
            "assembler input does not bind the CompCert textual assembly"
        )

    linker = _exact_object(
        chain["linker"],
        {
            "command_sha256",
            "executable",
            "exit_code",
            "input_objects",
            "link_map",
            "output_elf_sha256",
            "tool_id",
            "version",
        },
        "build_chain.linker",
    )
    _identifier(linker["tool_id"], "build_chain.linker.tool_id")
    _string(linker["version"], "build_chain.linker.version", maximum=256)
    _artifact(linker["executable"], "build_chain.linker.executable")
    _artifact(linker["link_map"], "build_chain.linker.link_map")
    _digest(linker["command_sha256"], "build_chain.linker.command_sha256")
    if _nat(linker["exit_code"], "build_chain.linker.exit_code") != 0:
        raise CompilerEvidenceError("linker exit_code must be zero")
    objects = linker["input_objects"]
    if not isinstance(objects, list) or not 1 <= len(objects) <= 256:
        raise CompilerEvidenceError(
            "build_chain.linker.input_objects must contain 1..256 artifacts"
        )
    object_hashes: list[str] = []
    object_ids: list[str] = []
    for index, item in enumerate(objects):
        artifact = _artifact(
            item, f"build_chain.linker.input_objects[{index}]"
        )
        object_hashes.append(artifact["sha256"])
        object_ids.append(artifact["artifact_id"])
    if len(set(object_hashes)) != len(object_hashes) or len(set(object_ids)) != len(
        object_ids
    ):
        raise CompilerEvidenceError("linker input objects must be unique")
    if assembler["output_object"]["sha256"] not in object_hashes:
        raise CompilerEvidenceError(
            "linker inputs omit the object emitted by the assembler"
        )
    output_elf_sha256 = _digest(
        linker["output_elf_sha256"], "build_chain.linker.output_elf_sha256"
    )

    elf = _exact_object(
        chain["elf"],
        {
            "architecture",
            "dependencies_report_sha256",
            "elf_class",
            "elf_header_sha256",
            "endianness",
            "entry_symbol",
            "entry_virtual_address_hex",
            "file",
            "file_type",
            "has_writable_executable_segment",
            "interpreter_present",
            "link_map_sha256",
            "needed_libraries",
            "nx_stack",
            "pie",
            "program_headers_sha256",
            "section_headers_sha256",
            "static_linked",
            "symbols_sha256",
        },
        "build_chain.elf",
    )
    _artifact(elf["file"], "build_chain.elf.file")
    expected_properties = {
        "architecture": "x86_64",
        "elf_class": "ELF64",
        "endianness": "little",
        "file_type": "ET_EXEC",
        "has_writable_executable_segment": False,
        "interpreter_present": False,
        "nx_stack": True,
        "pie": False,
        "static_linked": True,
    }
    for field, expected in expected_properties.items():
        if type(elf[field]) is not type(expected) or elf[field] != expected:
            raise CompilerEvidenceError(
                f"build_chain.elf.{field} must equal {expected!r}"
            )
    _identifier(elf["entry_symbol"], "build_chain.elf.entry_symbol")
    _word64_hex(
        elf["entry_virtual_address_hex"],
        "build_chain.elf.entry_virtual_address_hex",
        nonzero=True,
    )
    libraries = elf["needed_libraries"]
    if libraries != []:
        raise CompilerEvidenceError(
            "static Sqrt218 ELF must have no needed libraries"
        )
    for field in (
        "dependencies_report_sha256",
        "elf_header_sha256",
        "link_map_sha256",
        "program_headers_sha256",
        "section_headers_sha256",
        "symbols_sha256",
    ):
        _digest(elf[field], f"build_chain.elf.{field}")
    if elf["file"]["sha256"] != output_elf_sha256:
        raise CompilerEvidenceError("ELF file does not bind the linker output")
    if elf["link_map_sha256"] != linker["link_map"]["sha256"]:
        raise CompilerEvidenceError("ELF properties do not bind the link map")

    formal_architecture = _exact_object(
        chain["formal_architecture"],
        {
            "architecture",
            "entry_symbol",
            "entry_virtual_address_hex",
            "lean_model_declaration_id",
            "model_id",
            "model_sha256",
            "sysv_abi_contract_sha256",
        },
        "build_chain.formal_architecture",
    )
    if formal_architecture["architecture"] != "x86_64":
        raise CompilerEvidenceError(
            "build_chain.formal_architecture.architecture must equal 'x86_64'"
        )
    _identifier(
        formal_architecture["entry_symbol"],
        "build_chain.formal_architecture.entry_symbol",
    )
    _word64_hex(
        formal_architecture["entry_virtual_address_hex"],
        "build_chain.formal_architecture.entry_virtual_address_hex",
        nonzero=True,
    )
    _identifier(
        formal_architecture["lean_model_declaration_id"],
        "build_chain.formal_architecture.lean_model_declaration_id",
    )
    _identifier(
        formal_architecture["model_id"],
        "build_chain.formal_architecture.model_id",
    )
    _digest(
        formal_architecture["model_sha256"],
        "build_chain.formal_architecture.model_sha256",
    )
    _digest(
        formal_architecture["sysv_abi_contract_sha256"],
        "build_chain.formal_architecture.sysv_abi_contract_sha256",
    )
    if formal_architecture["entry_symbol"] != elf["entry_symbol"]:
        raise CompilerEvidenceError(
            "formal architecture entry symbol does not bind the ELF entry symbol"
        )
    if (
        formal_architecture["entry_virtual_address_hex"]
        != elf["entry_virtual_address_hex"]
    ):
        raise CompilerEvidenceError(
            "formal architecture entry address does not bind the ELF entry address"
        )

    _validate_valex(
        chain["valex"], compcert["textual_assembly"]["sha256"]
    )


def _validate_residual_trust(value: Any) -> None:
    if not isinstance(value, list) or len(value) != len(REQUIRED_RESIDUAL_TRUST):
        raise CompilerEvidenceError(
            "residual_trust must enumerate every current residual boundary"
        )
    identifiers: list[str] = []
    for index, item in enumerate(value):
        row = _exact_object(
            item,
            {"boundary_id", "note", "status"},
            f"residual_trust[{index}]",
        )
        boundary_id = _identifier(
            row["boundary_id"], f"residual_trust[{index}].boundary_id"
        )
        if row["status"] not in {
            "mitigated_not_eliminated",
            "out_of_scope",
            "trusted",
            "unproved",
        }:
            raise CompilerEvidenceError(
                f"residual_trust[{index}].status is unsupported"
            )
        _string(row["note"], f"residual_trust[{index}].note", maximum=2048)
        identifiers.append(boundary_id)
    if len(set(identifiers)) != len(identifiers):
        raise CompilerEvidenceError("residual_trust contains a duplicate boundary")
    if set(identifiers) != REQUIRED_RESIDUAL_TRUST:
        raise CompilerEvidenceError(
            "residual_trust boundary set is incomplete or unknown"
        )


def _validate_body(body: Mapping[str, Any]) -> None:
    value = _exact_object(body, _BODY_KEYS, "manifest body")
    if (
        isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise CompilerEvidenceError("unsupported schema_version")
    if value["kind"] != MANIFEST_KIND:
        raise CompilerEvidenceError("unsupported manifest kind")
    authority = _exact_object(
        value["authority"], set(AUTHORITY_BLOCK), "authority"
    )
    for field, expected in AUTHORITY_BLOCK.items():
        actual = authority[field]
        if type(actual) is not type(expected) or actual != expected:
            raise CompilerEvidenceError(
                "authority block must state the non-authorizing validation scope"
            )
    _validate_contracts(value["contracts"])
    _validate_build_chain(value["build_chain"])
    _validate_residual_trust(value["residual_trust"])


def seal_manifest(body: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a body and add its domain-local canonical self-hash."""

    _validate_body(body)
    manifest = dict(body)
    manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return validate_manifest(manifest)


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate shape, canonical self-hash, and digest-chain equalities only."""

    manifest = _exact_object(value, _ROOT_KEYS, "compiler-evidence manifest")
    claimed = _digest(manifest["manifest_sha256"], "manifest_sha256")
    body = {key: manifest[key] for key in sorted(_BODY_KEYS)}
    _validate_body(body)
    expected = sha256_bytes(canonical_json_bytes(body))
    if claimed != expected:
        raise CompilerEvidenceError("manifest_sha256 does not match canonical body")
    return manifest


def validate_execution_closure_metadata(value: Any) -> dict[str, Any]:
    """Validate every field in the exact Lean metadata projection.

    This validates only compact values already present in the compiler
    manifest.  It never resolves an artifact identifier or opens a hashed
    artifact.
    """

    metadata = _exact_object(
        value,
        set(EXECUTION_CLOSURE_METADATA_FIELDS),
        "execution-closure metadata",
    )
    version = metadata["compiler_evidence_manifest_version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != SCHEMA_VERSION
    ):
        raise CompilerEvidenceError(
            "execution-closure compiler manifest version is unsupported"
        )
    for field_name in (
        "compiler_evidence_manifest_sha256",
        "compiler_source_sha256",
        "compiler_binary_sha256",
        "compiler_configuration_sha256",
        "formal_architecture_model_sha256",
        "sysv_abi_contract_sha256",
        "neutral_contract_sha256",
        "elf_sha256",
    ):
        _digest(metadata[field_name], f"execution-closure {field_name}")
    _identifier(metadata["compiler_id"], "execution-closure compiler_id")
    _string(
        metadata["compiler_version"],
        "execution-closure compiler_version",
        maximum=128,
    )
    if metadata["target"] != EXECUTION_CLOSURE_TARGET:
        raise CompilerEvidenceError(
            "execution-closure target must equal 'azure_sevsnp_cpu'"
        )
    _identifier(
        metadata["neutral_contract_id"],
        "execution-closure neutral_contract_id",
    )
    _identifier(metadata["entry_point"], "execution-closure entry_point")
    return dict(metadata)


def _derive_execution_closure_metadata(
    checked: Mapping[str, Any],
) -> dict[str, Any]:
    chain = checked["build_chain"]
    translation = chain["c_translation"]
    compiler = chain["compcert"]
    architecture = chain["formal_architecture"]
    neutral = checked["contracts"]["neutral"]
    elf = chain["elf"]
    return validate_execution_closure_metadata({
        "compiler_evidence_manifest_version": checked["schema_version"],
        "compiler_evidence_manifest_sha256": checked["manifest_sha256"],
        "compiler_source_sha256": translation["source"]["sha256"],
        "compiler_id": compiler["compiler_id"],
        "compiler_version": compiler["version"],
        "compiler_binary_sha256": compiler["executable"]["sha256"],
        "compiler_configuration_sha256": compiler["configuration"]["sha256"],
        "formal_architecture_model_sha256": architecture["model_sha256"],
        "target": EXECUTION_CLOSURE_TARGET,
        "sysv_abi_contract_sha256": architecture[
            "sysv_abi_contract_sha256"
        ],
        "neutral_contract_id": neutral["contract_id"],
        "neutral_contract_sha256": neutral["contract_sha256"],
        "elf_sha256": elf["file"]["sha256"],
        "entry_point": architecture["entry_symbol"],
    })


def derive_execution_closure_metadata(manifest: Any) -> dict[str, Any]:
    """Project one validated compiler manifest to the exact Lean object."""

    return _derive_execution_closure_metadata(validate_manifest(manifest))


def _lean_frame(value: str) -> bytes:
    """Encode `ExecutionClosureIdentity.frame` byte-for-byte."""

    encoded = value.encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded


def encode_execution_closure_metadata(metadata: Any) -> bytes:
    """Encode the exact field order and spellings used by Lean.

    The kind is the literal domain separator.  Every following field is the
    concatenation of a UTF-8-byte-length-framed name and framed value.
    """

    checked = validate_execution_closure_metadata(metadata)
    encoded = bytearray(EXECUTION_CLOSURE_METADATA_KIND.encode("utf-8"))
    for field_name in EXECUTION_CLOSURE_METADATA_FIELDS:
        value = checked[field_name]
        text = str(value)
        encoded.extend(_lean_frame(field_name))
        encoded.extend(_lean_frame(text))
    return bytes(encoded)


_EXECUTION_CLOSURE_PROJECTION_KEYS = {
    "artifact_bytes_read",
    "authorizes_lean_theorem",
    "authorizes_receipt",
    "canonical_metadata_size_bytes",
    "canonical_metadata_text",
    "canonical_metadata_utf8_hex",
    "compiler_correctness_established_by_projection",
    "execution_closure_sha256",
    "kind",
    "metadata",
    "metadata_kind",
    "production_replay_performed",
    "schema_version",
    "sha256_uniqueness_proven",
}


def validate_execution_closure_projection(
    value: Any,
    *,
    manifest: Any | None = None,
) -> dict[str, Any]:
    """Validate a review-only projection and optionally its source manifest."""

    projection = _exact_object(
        value,
        _EXECUTION_CLOSURE_PROJECTION_KEYS,
        "execution-closure projection",
    )
    if projection["kind"] != EXECUTION_CLOSURE_PROJECTION_KIND:
        raise CompilerEvidenceError("unsupported execution-closure projection kind")
    if (
        isinstance(projection["schema_version"], bool)
        or not isinstance(projection["schema_version"], int)
        or projection["schema_version"]
        != EXECUTION_CLOSURE_PROJECTION_SCHEMA_VERSION
    ):
        raise CompilerEvidenceError(
            "unsupported execution-closure projection schema_version"
        )
    if projection["metadata_kind"] != EXECUTION_CLOSURE_METADATA_KIND:
        raise CompilerEvidenceError("execution-closure metadata kind is wrong")
    for field_name in (
        "artifact_bytes_read",
        "authorizes_lean_theorem",
        "authorizes_receipt",
        "compiler_correctness_established_by_projection",
        "production_replay_performed",
        "sha256_uniqueness_proven",
    ):
        if projection[field_name] is not False:
            raise CompilerEvidenceError(
                f"execution-closure {field_name} must be false"
            )

    metadata = validate_execution_closure_metadata(projection["metadata"])
    if manifest is not None:
        expected_metadata = derive_execution_closure_metadata(manifest)
        if metadata != expected_metadata:
            raise CompilerEvidenceError(
                "execution-closure metadata does not match compiler manifest"
            )

    canonical = encode_execution_closure_metadata(metadata)
    try:
        text = canonical.decode("utf-8")
    except UnicodeDecodeError as exc:  # Defensive; construction is UTF-8.
        raise CompilerEvidenceError(
            "execution-closure canonical bytes are not UTF-8"
        ) from exc
    if projection["canonical_metadata_text"] != text:
        raise CompilerEvidenceError(
            "execution-closure canonical metadata text mismatch"
        )
    if projection["canonical_metadata_utf8_hex"] != canonical.hex():
        raise CompilerEvidenceError(
            "execution-closure canonical metadata byte mismatch"
        )
    size = _nat(
        projection["canonical_metadata_size_bytes"],
        "execution-closure canonical metadata size",
        positive=True,
    )
    if size != len(canonical):
        raise CompilerEvidenceError(
            "execution-closure canonical metadata size mismatch"
        )
    digest = _digest(
        projection["execution_closure_sha256"],
        "execution-closure SHA-256",
    )
    if digest != sha256_bytes(canonical):
        raise CompilerEvidenceError("execution-closure SHA-256 mismatch")
    return dict(projection)


def execution_closure_projection(manifest: Any) -> dict[str, Any]:
    """Emit a bounded review object for `ExecutionClosureIdentity.Metadata`.

    The output is not a receipt, registry entry, compiler proof, or statement
    authorization.  Its digest still relies on standard SHA-256
    collision/second-preimage resistance when used as an external identity.
    """

    checked_manifest = validate_manifest(manifest)
    metadata = _derive_execution_closure_metadata(checked_manifest)
    canonical = encode_execution_closure_metadata(metadata)
    projection = {
        "artifact_bytes_read": False,
        "authorizes_lean_theorem": False,
        "authorizes_receipt": False,
        "canonical_metadata_size_bytes": len(canonical),
        "canonical_metadata_text": canonical.decode("utf-8"),
        "canonical_metadata_utf8_hex": canonical.hex(),
        "compiler_correctness_established_by_projection": False,
        "execution_closure_sha256": sha256_bytes(canonical),
        "kind": EXECUTION_CLOSURE_PROJECTION_KIND,
        "metadata": metadata,
        "metadata_kind": EXECUTION_CLOSURE_METADATA_KIND,
        "production_replay_performed": False,
        "schema_version": EXECUTION_CLOSURE_PROJECTION_SCHEMA_VERSION,
        "sha256_uniqueness_proven": False,
    }
    return validate_execution_closure_projection(
        projection, manifest=checked_manifest
    )


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    """Validate one compact canonical manifest without reading named artifacts."""

    if not isinstance(raw, bytes):
        raise CompilerEvidenceError("compiler-evidence manifest bytes must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise CompilerEvidenceError(
            f"compiler-evidence manifest exceeds {MAX_MANIFEST_BYTES} bytes"
        )
    try:
        value = parse_json_bytes(raw, label="Sqrt218 compiler-evidence manifest")
        if raw != canonical_json_bytes(value):
            raise CompilerEvidenceError(
                "compiler-evidence manifest is not canonical JSON"
            )
    except CampaignIOError as exc:
        raise CompilerEvidenceError(str(exc)) from exc
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    """Read exactly one bounded manifest; never open any artifact it names."""

    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as exc:
        raise CompilerEvidenceError(str(exc)) from exc
    return validate_manifest_bytes(raw)


def validation_summary(manifest: Any) -> dict[str, Any]:
    """Return an intentionally non-authorizing audit summary."""

    checked = validate_manifest(manifest)
    formal_architecture = checked["build_chain"]["formal_architecture"]
    projection = execution_closure_projection(checked)
    return {
        "artifact_bytes_read": False,
        "authorizes_lean_theorem": False,
        "authorizes_receipt": False,
        "compiler_evidence_manifest_valid": True,
        "formal_architecture_entry_symbol": formal_architecture["entry_symbol"],
        "formal_architecture_model_sha256": formal_architecture["model_sha256"],
        "identity_bindings_checked": True,
        "execution_closure_projection_checked": True,
        "execution_closure_sha256": projection["execution_closure_sha256"],
        "machine_code_refinement_proven_by_validation": False,
        "manifest_sha256": checked["manifest_sha256"],
        "production_replay_performed": False,
        "residual_trust_count": len(checked["residual_trust"]),
    }


__all__ = [
    "AUTHORITY_BLOCK",
    "CompilerEvidenceError",
    "EXECUTION_CLOSURE_METADATA_FIELDS",
    "EXECUTION_CLOSURE_METADATA_KIND",
    "EXECUTION_CLOSURE_PROJECTION_KIND",
    "EXECUTION_CLOSURE_PROJECTION_SCHEMA_VERSION",
    "EXECUTION_CLOSURE_TARGET",
    "MANIFEST_KIND",
    "MAX_MANIFEST_BYTES",
    "REQUIRED_RESIDUAL_TRUST",
    "SCHEMA_VERSION",
    "derive_execution_closure_metadata",
    "encode_execution_closure_metadata",
    "execution_closure_projection",
    "load_manifest",
    "seal_manifest",
    "validate_manifest",
    "validate_manifest_bytes",
    "validate_execution_closure_metadata",
    "validate_execution_closure_projection",
    "validation_summary",
]
