#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Challenge-first measured execution for Azure confidential CPU/H100 VMs.

This program is an execution/measurement component, not a relying-party
appraiser.  It always reports ``accepted: false``.  A production appraiser
must independently verify the VM/GPU evidence, the measured-runner policy,
the transcript equations, the retained off-VM challenge, and the exact job
and artifact allowlists before a signing service may issue a receipt.

The runner deliberately has no shell mode.  Workload, optional H100 gate, and
input-release commands are exact argv arrays whose executables are members of
the content-addressed artifact closure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Protocol, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPOSITORY_ROOT / "tools"
ATTESTATION_DIR = REPOSITORY_ROOT / "attestation"
for import_path in (
    str(REPOSITORY_ROOT),
    str(TOOLS_DIR),
    str(ATTESTATION_DIR),
):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from create_run_bundle import (  # noqa: E402
    BundleError,
    _bound_json,
    artifact_record,
    canonical_json_bytes,
    canonical_sha256,
    load_profile,
    parse_json_bytes,
    profile_reference,
    validate_completion,
)
from collect_azure_ncc_evidence import (  # noqa: E402
    BACKENDS,
    HEX256_RE,
    TPM_PCR_SELECTION,
    canonical_json_bytes as evidence_canonical_json_bytes,
    derive_binding_nonce,
    load_challenge,
    require_current_challenge_window,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GOLDBACH_H100_ALGORITHM_PREFIX,
    goldbach_execution_projection_bytes,
)
from tg_verifier.campaign_io import (  # noqa: E402
    AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS,
    MeasuredWorkerScopeError,
    azure_measured_worker_environment,
)


JOB_KIND = "sparkinterval_measured_job"
TRANSCRIPT_KIND = "sparkinterval_measured_runner_transcript"
TRACE_KIND = "sparkinterval_challenge_work_trace"
SCHEMA_VERSION = 1
PCR_INDEX = 23
PCR_BANK = "sha256"
PCR_ZERO = bytes(32)
START_BINDING_HEADER = "sparkinterval.measured-runner.start-binding.v1\n"
JOB_BINDING_HEADER = "sparkinterval.measured-runner.job-binding.v1\n"
PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
TRACE_DIGEST_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
TOKENS = {
    "@challenge@",
    "@challenge_expires_at@",
    "@job_binding@",
    "@input@",
    "@output@",
    "@trace@",
    "@gate_record@",
}
FORBIDDEN_ENVIRONMENT_KEYS = {
    "BASH_ENV",
    "ENV",
    "GCONV_PATH",
    "GLIBC_TUNABLES",
    "IFS",
    "LOCPATH",
    "NLSPATH",
    "PATH",
}
FORBIDDEN_ENVIRONMENT_PREFIXES = ("DYLD_", "LD_", "PERL", "PYTHON", "RUBY")
CUBIC_TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.v1\n"
    "algorithm=cubic-sum-div-three-20000\n"
    "initial=SHA256(initial-domain || challenge_nonce || job_binding_sha256 || input_sha256)\n"
    "step=SHA256(step-domain || previous || canonical-decimal-x || canonical-decimal-accumulator)\n"
    "step-order=after-checked-u64-cube-addition-for-x=0-through-20000-inclusive\n"
    "final=step-at-x-20000"
)

JOB_KEYS = {
    "algorithm",
    "artifact_closure",
    "backend",
    "command",
    "domain_coverage",
    "gpu_pre_run_gate",
    "input_artifact",
    "job_id",
    "kind",
    "output_contract",
    "parameters",
    "runner_policy",
    "schema_version",
    "target_profile",
    "tpm_policy",
    "trust_profile",
    "work_trace_contract",
}
OPTIONAL_JOB_KEYS = {"retained_artifact_contracts"}
ARTIFACT_KEYS = {"executable", "path", "role", "sha256", "size_bytes", "statement_role"}
RETAINED_ARTIFACT_CONTRACT_KEYS = {
    "maximum_bytes",
    "path",
    "trace_sha256_field",
}
WORK_TRACE_KEYS = {
    "algorithm_id",
    "challenge_nonce",
    "input_sha256",
    "iteration_count",
    "job_binding_sha256",
    "kind",
    "result_sha256",
    "schema_version",
    "trace_sha256",
}
TRANSCRIPT_KEYS = {
    "accepted",
    "algorithm",
    "artifact_closure",
    "backend",
    "bindings",
    "challenge",
    "command",
    "gpu_pre_run_gate",
    "input_artifact",
    "job_id",
    "kind",
    "output_artifact",
    "pcr23",
    "profiles",
    "quote",
    "runner_policy",
    "schema_version",
    "statement",
    "status",
    "timing",
    "trust_boundary",
    "work_trace",
}


class RunnerError(RuntimeError):
    """A job, challenge, artifact, execution, or TPM operation failed closed."""


def _exact_object(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise RunnerError(
            f"{what} has wrong fields "
            f"(missing={sorted(keys - actual)}, unexpected={sorted(actual - keys)})"
        )
    return value


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_relative_path(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{what} must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise RunnerError(f"{what} is unsafe: {value!r}")
    return value


def _sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or HEX256_RE.fullmatch(value) is None:
        raise RunnerError(f"{what} must be lowercase SHA-256 hex")
    return value


def _canonical_file(path: Path, what: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = parse_json_bytes(raw, what)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, BundleError) as error:
        raise RunnerError(f"cannot load {what}: {error}") from error
    if not isinstance(value, dict):
        raise RunnerError(f"{what} must be a JSON object")
    canonical = canonical_json_bytes(value)
    if raw not in (canonical, canonical + b"\n"):
        raise RunnerError(f"{what} must be canonical JSON")
    return value, canonical


def _elf_has_interp(path: Path) -> bool:
    """Return whether an ELF executable declares a PT_INTERP loader."""

    raw = path.read_bytes()
    if len(raw) < 64 or raw[:4] != b"\x7fELF":
        raise RunnerError(f"static closure host executable is not ELF: {path}")
    elf_class, endian_tag = raw[4], raw[5]
    if endian_tag == 1:
        endian = "<"
    elif endian_tag == 2:
        endian = ">"
    else:
        raise RunnerError("ELF executable has invalid endianness")
    if elf_class == 2:
        if len(raw) < 64:
            raise RunnerError("ELF64 header is truncated")
        phoff = struct.unpack_from(endian + "Q", raw, 32)[0]
        phentsize = struct.unpack_from(endian + "H", raw, 54)[0]
        phnum = struct.unpack_from(endian + "H", raw, 56)[0]
    elif elf_class == 1:
        if len(raw) < 52:
            raise RunnerError("ELF32 header is truncated")
        phoff = struct.unpack_from(endian + "I", raw, 28)[0]
        phentsize = struct.unpack_from(endian + "H", raw, 42)[0]
        phnum = struct.unpack_from(endian + "H", raw, 44)[0]
    else:
        raise RunnerError("ELF executable has unsupported class")
    if phentsize < 4 or phnum > 4096 or phoff + phentsize * phnum > len(raw):
        raise RunnerError("ELF program-header table is malformed")
    return any(
        struct.unpack_from(endian + "I", raw, phoff + index * phentsize)[0] == 3
        for index in range(phnum)
    )


def _closure_manifest(files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifacts": files,
        "kind": "sparkinterval_executable_artifact_closure",
        "schema_version": 1,
    }


def derive_job_binding(
    challenge_object_sha256: str,
    challenge_nonce: str,
    job_spec_sha256: str,
    closure_manifest_sha256: str,
    runner_policy_sha256: str,
    target_profile_sha256: str,
    trust_profile_sha256: str,
) -> str:
    values = (
        (challenge_object_sha256, "challenge object hash"),
        (challenge_nonce, "challenge nonce"),
        (job_spec_sha256, "job specification hash"),
        (closure_manifest_sha256, "closure manifest hash"),
        (runner_policy_sha256, "runner policy hash"),
        (target_profile_sha256, "target profile hash"),
        (trust_profile_sha256, "trust profile hash"),
    )
    for value, what in values:
        _sha256(value, what)
    payload = JOB_BINDING_HEADER + "".join(
        f"{name}={value}\n"
        for name, value in (
            ("challenge_object_sha256", challenge_object_sha256),
            ("challenge_nonce", challenge_nonce),
            ("job_spec_sha256", job_spec_sha256),
            ("closure_manifest_sha256", closure_manifest_sha256),
            ("runner_policy_sha256", runner_policy_sha256),
            ("target_profile_sha256", target_profile_sha256),
            ("trust_profile_sha256", trust_profile_sha256),
        )
    )
    return _digest(payload.encode("ascii"))


def derive_start_binding(job_binding_sha256: str) -> str:
    _sha256(job_binding_sha256, "job binding")
    return _digest(
        (START_BINDING_HEADER + f"job_binding_sha256={job_binding_sha256}\n").encode(
            "ascii"
        )
    )


def pcr_extend(previous: bytes, digest_hex: str) -> bytes:
    if len(previous) != 32:
        raise RunnerError("SHA-256 PCR value must be exactly 32 bytes")
    _sha256(digest_hex, "PCR extension digest")
    return hashlib.sha256(previous + bytes.fromhex(digest_hex)).digest()


def _validate_artifact_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise RunnerError("artifact closure must contain at least one file")
    files: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(value):
        record = _exact_object(raw, ARTIFACT_KEYS, f"artifact closure record {index}")
        path = _safe_relative_path(record["path"], f"artifact closure path {index}")
        if path in seen_paths:
            raise RunnerError(f"duplicate artifact closure path: {path}")
        seen_paths.add(path)
        _sha256(record["sha256"], f"artifact {path} hash")
        if (
            not isinstance(record["size_bytes"], int)
            or isinstance(record["size_bytes"], bool)
            or record["size_bytes"] < 0
        ):
            raise RunnerError(f"artifact {path} size is invalid")
        if not isinstance(record["executable"], bool):
            raise RunnerError(f"artifact {path} executable flag is invalid")
        if not isinstance(record["role"], str) or ROLE_RE.fullmatch(record["role"]) is None:
            raise RunnerError(f"artifact {path} role is invalid")
        statement_role = record["statement_role"]
        if statement_role is not None and (
            not isinstance(statement_role, str) or ROLE_RE.fullmatch(statement_role) is None
        ):
            raise RunnerError(f"artifact {path} statement role is invalid")
        files.append(record)
    if len([item for item in files if item["statement_role"] == "host_executable"]) != 1:
        raise RunnerError("artifact closure must identify exactly one host_executable")
    return files


def validate_job_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunnerError("measured job specification must be an object")
    actual_job_keys = set(value)
    missing_job_keys = JOB_KEYS - actual_job_keys
    unexpected_job_keys = actual_job_keys - JOB_KEYS - OPTIONAL_JOB_KEYS
    if missing_job_keys or unexpected_job_keys:
        raise RunnerError(
            "measured job specification has wrong fields "
            f"(missing={sorted(missing_job_keys)}, "
            f"unexpected={sorted(unexpected_job_keys)})"
        )
    job = value
    if job["kind"] != JOB_KIND or job["schema_version"] != SCHEMA_VERSION:
        raise RunnerError("unsupported measured job kind/version")
    if job["backend"] not in BACKENDS:
        raise RunnerError("unsupported measured job backend")
    if not isinstance(job["job_id"], str) or PROFILE_ID_RE.fullmatch(job["job_id"]) is None:
        raise RunnerError("job id is malformed")

    algorithm = _exact_object(
        job["algorithm"],
        {"algorithm_id", "canonical_definition", "definition_sha256"},
        "algorithm",
    )
    if not isinstance(algorithm["algorithm_id"], str) or PROFILE_ID_RE.fullmatch(
        algorithm["algorithm_id"]
    ) is None:
        raise RunnerError("algorithm id is malformed")
    if not isinstance(algorithm["canonical_definition"], str) or not algorithm[
        "canonical_definition"
    ]:
        raise RunnerError("canonical algorithm definition is absent")
    if _digest(algorithm["canonical_definition"].encode("utf-8")) != _sha256(
        algorithm["definition_sha256"], "algorithm definition hash"
    ):
        raise RunnerError("algorithm definition digest does not match its bytes")

    for name in ("parameters", "domain_coverage"):
        record = _exact_object(job[name], {"canonical_sha256", "value"}, name)
        if not isinstance(record["value"], dict) or not record["value"]:
            raise RunnerError(f"{name} value must be a nonempty object")
        if canonical_sha256(record["value"]) != _sha256(
            record["canonical_sha256"], f"{name} hash"
        ):
            raise RunnerError(f"{name} digest does not match its canonical value")

    closure = _exact_object(
        job["artifact_closure"],
        {"closure_kind", "files", "manifest_sha256"},
        "artifact closure",
    )
    if closure["closure_kind"] not in (
        "static_elf_source_reviewed_v1",
        "content_addressed_image_source_reviewed_v1",
    ):
        raise RunnerError("artifact closure kind is unsupported")
    files = _validate_artifact_records(closure["files"])
    manifest = _closure_manifest(files)
    if canonical_sha256(manifest) != _sha256(
        closure["manifest_sha256"], "closure manifest hash"
    ):
        raise RunnerError("artifact closure manifest digest is inconsistent")

    input_record = _exact_object(
        job["input_artifact"],
        {"path", "release_argv", "release_mode", "sha256", "size_bytes"},
        "input artifact",
    )
    _safe_relative_path(input_record["path"], "input artifact path")
    _sha256(input_record["sha256"], "input artifact hash")
    if (
        not isinstance(input_record["size_bytes"], int)
        or isinstance(input_record["size_bytes"], bool)
        or input_record["size_bytes"] < 0
    ):
        raise RunnerError("input artifact size is invalid")
    if input_record["release_mode"] == "prepositioned_public_after_start":
        if input_record["release_argv"] is not None:
            raise RunnerError("prepositioned public input cannot have a release command")
    elif input_record["release_mode"] == "relying_party_after_h100_gate":
        if job["backend"] != "azure_ncc40ads_h100_v5":
            raise RunnerError("relying-party-after-H100 release requires the H100 backend")
        release_argv = _validate_argv(input_record["release_argv"], "input release argv")
        for token in ("@challenge@", "@job_binding@", "@input@"):
            if token not in release_argv:
                raise RunnerError(f"input release argv must contain {token}")
        release_executable = next(
            (item for item in files if item["path"] == release_argv[0]), None
        )
        if release_executable is None or not release_executable["executable"]:
            raise RunnerError("input release argv[0] must be an executable closure artifact")
    else:
        raise RunnerError("unsupported input release mode")

    command = _exact_object(
        job["command"], {"argv", "cwd", "environment", "timeout_seconds"}, "command"
    )
    argv = _validate_argv(command["argv"], "workload argv")
    for token in ("@challenge@", "@job_binding@", "@input@", "@output@", "@trace@"):
        if token not in argv:
            raise RunnerError(f"workload argv must contain the reserved {token} token")
    if command["cwd"] != ".":
        raise RunnerError("measured commands currently require cwd='.'")
    if not isinstance(command["environment"], dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(item, str)
        for key, item in command["environment"].items()
    ):
        raise RunnerError("command environment must map nonempty strings to strings")
    for key in command["environment"]:
        if key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            raise RunnerError(
                f"measured worker execution-scope variable is runner-reserved: {key}"
            )
        if key in FORBIDDEN_ENVIRONMENT_KEYS or key.startswith(
            FORBIDDEN_ENVIRONMENT_PREFIXES
        ):
            raise RunnerError(f"dangerous loader/interpreter environment variable is forbidden: {key}")
    if not 1 <= _integer(command["timeout_seconds"], "command timeout") <= 7 * 86400:
        raise RunnerError("command timeout must be between 1 second and 7 days")
    executable_record = next(
        (item for item in files if item["path"] == argv[0]), None
    )
    if executable_record is None or not executable_record["executable"]:
        raise RunnerError("workload argv[0] must be an executable closure artifact")

    output = _exact_object(
        job["output_contract"],
        {"expected_output_count", "format", "maximum_bytes", "path"},
        "output contract",
    )
    _safe_relative_path(output["path"], "output path")
    if output["format"] not in (
        "canonical_decimal_natural_no_newline_v1",
        "opaque_bytes_v1",
    ):
        raise RunnerError("output format is unsupported")
    if output["expected_output_count"] != 1 or isinstance(
        output["expected_output_count"], bool
    ):
        raise RunnerError("runner currently requires exactly one result artifact")
    if not 1 <= _integer(output["maximum_bytes"], "maximum output bytes") <= 2**31:
        raise RunnerError("maximum output size is invalid")

    trace = _exact_object(
        job["work_trace_contract"],
        {
            "expected_iterations",
            "format",
            "path",
            "required",
            "trace_algorithm_definition",
            "trace_algorithm_sha256",
            "verification_mode",
            "verifier_argv",
        },
        "work-trace contract",
    )
    if (
        trace["format"] != "challenge_sha256_chain_json_v1"
        or trace["required"] is not True
    ):
        raise RunnerError("challenge-dependent SHA-256 work traces are mandatory")
    _safe_relative_path(trace["path"], "work-trace path")
    if (
        not isinstance(trace["trace_algorithm_definition"], str)
        or not trace["trace_algorithm_definition"]
        or _digest(trace["trace_algorithm_definition"].encode("utf-8"))
        != _sha256(trace["trace_algorithm_sha256"], "work-trace algorithm hash")
    ):
        raise RunnerError("work-trace algorithm definition/hash is inconsistent")
    if _integer(trace["expected_iterations"], "expected trace iteration count") < 1:
        raise RunnerError("expected trace iteration count must be positive")
    if trace["verification_mode"] == "builtin_cubic_sum_div_three_20000_v1":
        if trace["verifier_argv"] is not None or trace["trace_algorithm_definition"] != CUBIC_TRACE_DEFINITION:
            raise RunnerError("built-in cubic trace contract is not source-exact")
        if trace["expected_iterations"] != 20001:
            raise RunnerError("built-in cubic trace must contain exactly 20,001 iterations")
    elif trace["verification_mode"] == "pinned_external_trace_verifier_v1":
        verifier_argv = _validate_argv(trace["verifier_argv"], "work-trace verifier argv")
        for token in ("@challenge@", "@job_binding@", "@input@", "@output@", "@trace@"):
            if token not in verifier_argv:
                raise RunnerError(f"work-trace verifier argv must contain {token}")
        verifier_executable = next(
            (item for item in files if item["path"] == verifier_argv[0]), None
        )
        if verifier_executable is None or not verifier_executable["executable"]:
            raise RunnerError("work-trace verifier executable is not in the artifact closure")
    else:
        raise RunnerError("unsupported work-trace verification mode")
    if len({input_record["path"], output["path"], trace["path"]}) != 3:
        raise RunnerError("input, result, and work-trace paths must be distinct")

    retained_contracts = job.get("retained_artifact_contracts", [])
    if (
        not isinstance(retained_contracts, list)
        or len(retained_contracts) > 64
        or ("retained_artifact_contracts" in job and not retained_contracts)
    ):
        raise RunnerError(
            "retained artifact contracts must be a nonempty array of at most 64 records"
        )
    retained_paths: set[str] = set()
    retained_trace_fields: set[str] = set()
    reserved_paths = {
        input_record["path"],
        output["path"],
        trace["path"],
        *(record["path"] for record in files),
    }
    for index, raw_contract in enumerate(retained_contracts):
        retained = _exact_object(
            raw_contract,
            RETAINED_ARTIFACT_CONTRACT_KEYS,
            f"retained artifact contract {index}",
        )
        retained_path = _safe_relative_path(
            retained["path"], f"retained artifact contract {index} path"
        )
        if retained_path in retained_paths or retained_path in reserved_paths:
            raise RunnerError(
                "retained artifact paths must be unique and distinct from "
                "job inputs, outputs, traces, and immutable closure artifacts"
            )
        retained_paths.add(retained_path)
        maximum_bytes = _integer(
            retained["maximum_bytes"],
            f"retained artifact contract {index} maximum bytes",
        )
        if not 1 <= maximum_bytes <= 2**31:
            raise RunnerError("retained artifact maximum size is invalid")
        trace_field = retained["trace_sha256_field"]
        if (
            not isinstance(trace_field, str)
            or TRACE_DIGEST_FIELD_RE.fullmatch(trace_field) is None
            or trace_field in WORK_TRACE_KEYS
            or trace_field in retained_trace_fields
        ):
            raise RunnerError(
                "retained artifact trace digest fields must be unique "
                "lowercase identifiers outside the base trace schema"
            )
        retained_trace_fields.add(trace_field)
    if retained_contracts and (
        trace["verification_mode"] != "pinned_external_trace_verifier_v1"
    ):
        raise RunnerError(
            "retained artifact contracts require a pinned external trace verifier"
        )

    tpm = _exact_object(
        job["tpm_policy"], {"ak_handle", "bank", "pcr_index", "pcr_selection"}, "TPM policy"
    )
    if (
        tpm["ak_handle"] != "0x81000003"
        or tpm["bank"] != PCR_BANK
        or tpm["pcr_index"] != PCR_INDEX
        or tpm["pcr_selection"] != TPM_PCR_SELECTION
    ):
        raise RunnerError("job TPM policy does not match the measured-runner protocol")

    for name, expected_kind in (("target_profile", "target"), ("trust_profile", "trust")):
        profile = _exact_object(
            job[name], {"path", "profile_id", "sha256"}, name.replace("_", " ")
        )
        _safe_relative_path(profile["path"], f"{name} path")
        if not isinstance(profile["profile_id"], str) or PROFILE_ID_RE.fullmatch(
            profile["profile_id"]
        ) is None:
            raise RunnerError(f"{name} id is malformed")
        _sha256(profile["sha256"], f"{name} hash")
        del expected_kind

    runner_policy = _exact_object(
        job["runner_policy"], {"path", "policy_id", "sha256"}, "runner policy"
    )
    _safe_relative_path(runner_policy["path"], "runner policy path")
    if not isinstance(runner_policy["policy_id"], str) or PROFILE_ID_RE.fullmatch(
        runner_policy["policy_id"]
    ) is None:
        raise RunnerError("runner policy id is malformed")
    _sha256(runner_policy["sha256"], "runner policy hash")

    gate = job["gpu_pre_run_gate"]
    if job["backend"] == "azure_ncc40ads_h100_v5":
        gate = _exact_object(
            gate,
            {
                "argv",
                "record_path",
                "required",
                "secret_environment_names",
                "timeout_seconds",
            },
            "H100 pre-run gate",
        )
        if gate["required"] is not True:
            raise RunnerError("H100 jobs require a pre-run GPU Ready/attestation gate")
        gate_argv = _validate_argv(gate["argv"], "H100 gate argv")
        for token in (
            "@challenge@",
            "@challenge_expires_at@",
            "@job_binding@",
            "@gate_record@",
        ):
            if token not in gate_argv:
                raise RunnerError(f"H100 gate argv must contain {token}")
        gate_executable = next(
            (item for item in files if item["path"] == gate_argv[0]), None
        )
        if gate_executable is None or not gate_executable["executable"]:
            raise RunnerError("H100 gate executable is not in the artifact closure")
        _safe_relative_path(gate["record_path"], "H100 gate record path")
        if not 1 <= _integer(gate["timeout_seconds"], "H100 gate timeout") <= 3600:
            raise RunnerError("H100 gate timeout is invalid")
        secret_names = gate["secret_environment_names"]
        if (
            not isinstance(secret_names, list)
            or len(secret_names) != len(set(secret_names))
            or any(name != "NV_ATTESTATION_SERVICE_KEY" for name in secret_names)
        ):
            raise RunnerError(
                "H100 gate may forward only the unrecorded NV_ATTESTATION_SERVICE_KEY"
            )
    elif gate is not None:
        raise RunnerError("CPU jobs must not declare an H100 pre-run gate")
    return job


def _integer(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RunnerError(f"{what} must be an integer")
    return value


def _validate_argv(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item or "\x00" in item for item in value
    ):
        raise RunnerError(f"{what} must be a nonempty array of nonempty strings")
    for item in value:
        for token in re.findall(r"@[a-z_]+@", item):
            if token not in TOKENS:
                raise RunnerError(f"{what} contains unknown reserved token {token}")
    return value


def _snapshot_file(source: Path, destination: Path, expected_hash: str, expected_size: int, executable: bool) -> None:
    if source.is_symlink():
        raise RunnerError(f"artifact must not be a symlink: {source}")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(source, flags)
    except OSError as error:
        raise RunnerError(f"cannot open artifact {source}: {error}") from error
    output: int | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RunnerError(f"artifact is not a regular file: {source}")
        digest = hashlib.sha256()
        size = 0
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            output_flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            output_flags |= os.O_NOFOLLOW
        output = os.open(destination, output_flags, 0o500 if executable else 0o400)
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
            view = memoryview(block)
            while view:
                count = os.write(output, view)
                if count <= 0:
                    raise RunnerError(f"short write while snapshotting artifact: {source}")
                view = view[count:]
        os.fsync(output)
        after = os.fstat(descriptor)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        if identity(before) != identity(after):
            raise RunnerError(f"artifact changed while snapshotted: {source}")
    finally:
        os.close(descriptor)
        if output is not None:
            os.close(output)
    if size != expected_size or digest.hexdigest() != expected_hash:
        destination.unlink(missing_ok=True)
        raise RunnerError(f"artifact does not match job specification: {source}")


def _write_exclusive(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(content)
        while view:
            count = os.write(descriptor, view)
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class TPMBackend(Protocol):
    def reset(self) -> None: ...
    def read(self) -> bytes: ...
    def extend(self, digest_hex: str) -> None: ...
    def quote(self, qualifying_digest_hex: str, output_dir: Path) -> dict[str, Any]: ...


class CommandTPMBackend:
    """TPM2-tools adapter for a real Azure confidential VM vTPM."""

    REQUIRED = (
        "tpm2_pcrreset",
        "tpm2_pcrread",
        "tpm2_pcrextend",
        "tpm2_quote",
        "tpm2_checkquote",
        "tpm2_readpublic",
        "tpm2_nvread",
    )

    def __init__(self, work_dir: Path, command_timeout: int = 600):
        self.work_dir = work_dir
        self.command_timeout = command_timeout
        self.tools: dict[str, str] = {}
        for name in self.REQUIRED:
            executable = shutil.which(
                name, path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            )
            if executable is None:
                raise RunnerError(f"required TPM executable is absent: {name}")
            self.tools[name] = executable
        self.read_counter = 0

    def _run(self, argv: Sequence[str], label: str) -> subprocess.CompletedProcess[bytes]:
        try:
            result = subprocess.run(
                list(argv),
                cwd=self.work_dir,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "TZ": "UTC",
                },
                check=False,
                capture_output=True,
                timeout=self.command_timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RunnerError(f"{label} could not run: {error}") from error
        _write_exclusive(self.work_dir / f"{label}.stdout.bin", result.stdout)
        _write_exclusive(self.work_dir / f"{label}.stderr.bin", result.stderr)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout)[-2000:].decode("utf-8", "replace")
            raise RunnerError(f"{label} failed ({result.returncode}): {detail}")
        return result

    def reset(self) -> None:
        self._run([self.tools["tpm2_pcrreset"], str(PCR_INDEX)], "tpm_pcr23_reset")

    def read(self) -> bytes:
        self.read_counter += 1
        path = self.work_dir / f".pcr23-read-{self.read_counter}.bin"
        self._run(
            [
                self.tools["tpm2_pcrread"],
                f"{PCR_BANK}:{PCR_INDEX}",
                "--pcrs_format",
                "values",
                "-o",
                str(path),
            ],
            f"tpm_pcr23_read_{self.read_counter}",
        )
        try:
            value = path.read_bytes()
            path.unlink()
        except OSError as error:
            raise RunnerError(f"cannot read TPM PCR output: {error}") from error
        if len(value) != 32:
            raise RunnerError("TPM PCR read did not return exactly 32 bytes")
        return value

    def extend(self, digest_hex: str) -> None:
        _sha256(digest_hex, "TPM extension digest")
        self._run(
            [self.tools["tpm2_pcrextend"], f"{PCR_INDEX}:{PCR_BANK}={digest_hex}"],
            f"tpm_pcr23_extend_{self.read_counter}",
        )

    def quote(self, qualifying_digest_hex: str, output_dir: Path) -> dict[str, Any]:
        _sha256(qualifying_digest_hex, "quote qualifying digest")
        paths = {
            "ak_public": output_dir / "vtpm_ak.pem",
            "message": output_dir / "tpm_quote.msg",
            "signature": output_dir / "tpm_quote.sig",
            "pcrs": output_dir / "tpm_quote.pcrs",
        }
        self._run(
            [self.tools["tpm2_readpublic"], "-c", "0x81000003", "-f", "pem", "-o", str(paths["ak_public"])],
            "tpm_read_ak",
        )
        self._run(
            [
                self.tools["tpm2_quote"], "-c", "0x81000003", "-l", TPM_PCR_SELECTION,
                "-q", qualifying_digest_hex, "-m", str(paths["message"]), "-s",
                str(paths["signature"]), "-o", str(paths["pcrs"]), "-g", PCR_BANK,
            ],
            "tpm_quote",
        )
        self._run(
            [
                self.tools["tpm2_checkquote"], "-u", str(paths["ak_public"]), "-m",
                str(paths["message"]), "-s", str(paths["signature"]), "-f",
                str(paths["pcrs"]), "-g", PCR_BANK, "-q", qualifying_digest_hex,
            ],
            "tpm_checkquote",
        )
        for index, filename in (
            ("0x01C101D0", "vtpm_ak_cert.bin"),
            ("0x01400001", "azure_hcl_report.bin"),
            ("0x01400002", "azure_hcl_runtime_data.bin"),
        ):
            self._run(
                [self.tools["tpm2_nvread"], "-C", "o", index, "-o", str(output_dir / filename)],
                f"tpm_nvread_{index.lower()}",
            )
        event_log = Path("/sys/kernel/security/tpm0/binary_bios_measurements")
        if not event_log.is_file():
            raise RunnerError("kernel TCG event log is absent")
        _snapshot_unpinned(event_log, output_dir / "tcg_event_log.bin")
        return {
            "ak_handle": "0x81000003",
            "local_checkquote_passed": True,
            "pcr_selection": TPM_PCR_SELECTION,
            "qualifying_data_sha256": qualifying_digest_hex,
        }


def _snapshot_unpinned(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise RunnerError(f"evidence source is not a regular non-symlink file: {source}")
    _write_exclusive(destination, source.read_bytes())


ProcessRunner = Callable[[Sequence[str], Path, Mapping[str, str], int, Path, Path], int]


def _subprocess_runner(
    argv: Sequence[str], cwd: Path, environment: Mapping[str, str], timeout: int,
    stdout_path: Path, stderr_path: Path,
) -> int:
    maximum_log_bytes = 16 * 1024 * 1024
    stdout = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    stderr = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=dict(environment),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise RunnerError(f"measured command could not complete: {error}") from error
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, (stdout, "stdout"))
        selector.register(process.stderr, selectors.EVENT_READ, (stderr, "stderr"))
        counts = {"stdout": 0, "stderr": 0}
        deadline = time.monotonic() + timeout
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.wait()
                    raise RunnerError(f"measured command exceeded timeout of {timeout} seconds")
                for key, _events in selector.select(min(remaining, 1.0)):
                    block = os.read(key.fileobj.fileno(), 64 * 1024)
                    if not block:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    destination, label = key.data
                    counts[label] += len(block)
                    if counts[label] > maximum_log_bytes:
                        process.kill()
                        process.wait()
                        raise RunnerError(
                            f"measured command {label} exceeded {maximum_log_bytes} bytes"
                        )
                    view = memoryview(block)
                    while view:
                        written = os.write(destination, view)
                        if written <= 0:
                            raise RunnerError(f"short write while retaining measured {label}")
                        view = view[written:]
            return_code = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        os.fsync(stdout)
        os.fsync(stderr)
        return return_code
    finally:
        os.close(stdout)
        os.close(stderr)


def _expand_argv(argv: Sequence[str], replacements: Mapping[str, str]) -> list[str]:
    result: list[str] = []
    for argument in argv:
        expanded = argument
        for token, replacement in replacements.items():
            expanded = expanded.replace(token, replacement)
        if re.search(r"@[a-z_]+@", expanded):
            raise RunnerError(f"unexpanded reserved token in argv argument: {expanded!r}")
        result.append(expanded)
    return result


def _file_identity(path: Path, what: str, maximum: int | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RunnerError(f"{what} is absent or not a regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        after = os.fstat(stream.fileno())
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
        raise RunnerError(f"{what} changed while hashed")
    if maximum is not None and size > maximum:
        raise RunnerError(f"{what} exceeds its maximum byte length")
    return {"path": path.as_posix(), "sha256": digest.hexdigest(), "size_bytes": size}


def _validate_trace(
    path: Path, *, algorithm_id: str, challenge_nonce: str, job_binding: str,
    input_sha256: str,
    result_sha256: str,
    contract: dict[str, Any],
    input_bytes: bytes | None,
    retained_artifact_contracts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    value, canonical = _canonical_file(path, "work trace")
    retained_fields = {
        record["trace_sha256_field"] for record in retained_artifact_contracts
    }
    trace = _exact_object(
        value,
        WORK_TRACE_KEYS | retained_fields,
        "work trace",
    )
    if (
        trace["kind"] != TRACE_KIND
        or trace["schema_version"] != 1
        or trace["algorithm_id"] != algorithm_id
        or trace["challenge_nonce"] != challenge_nonce
        or trace["job_binding_sha256"] != job_binding
        or trace["input_sha256"] != input_sha256
        or trace["result_sha256"] != result_sha256
        or not isinstance(trace["iteration_count"], int)
        or isinstance(trace["iteration_count"], bool)
        or trace["iteration_count"] < 1
    ):
        raise RunnerError("work trace does not bind this challenge/job/input/result")
    _sha256(trace["trace_sha256"], "work-trace chain digest")
    for field in sorted(retained_fields):
        _sha256(trace[field], f"retained artifact trace digest {field}")
    if trace["iteration_count"] != contract["expected_iterations"]:
        raise RunnerError("work trace iteration count differs from the source-reviewed contract")
    if contract["verification_mode"] == "builtin_cubic_sum_div_three_20000_v1":
        if input_bytes != b"20000":
            raise RunnerError("built-in cubic work-trace verifier requires exact input 20000")
        expected_trace = _recompute_cubic_trace(challenge_nonce, job_binding, input_sha256)
        if trace["trace_sha256"] != expected_trace:
            raise RunnerError("cubic work-trace chain digest failed independent recomputation")
    result = {
        "artifact_sha256": _digest(canonical),
        "iteration_count": trace["iteration_count"],
        "path": path.as_posix(),
        "trace_sha256": trace["trace_sha256"],
    }
    if retained_artifact_contracts:
        result["retained_artifacts"] = [
            {
                "path": record["path"],
                "sha256": trace[record["trace_sha256_field"]],
            }
            for record in retained_artifact_contracts
        ]
    return result


def _validate_retained_artifacts(
    root: Path,
    contracts: Sequence[Mapping[str, Any]],
    trace_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Bind every source-declared retained file to its trace digest.

    The external verifier checks the computation-specific relationship.  This
    generic layer independently checks that the exact regular file retained in
    the measured package has the digest named by that already-bound trace.
    """

    if not contracts:
        if "retained_artifacts" in trace_record:
            raise RunnerError("work trace names undeclared retained artifacts")
        return []
    declared = trace_record.get("retained_artifacts")
    if not isinstance(declared, list) or len(declared) != len(contracts):
        raise RunnerError("work trace retained-artifact inventory is incomplete")
    root_resolved = root.resolve(strict=True)
    identities: list[dict[str, Any]] = []
    for index, (contract, trace_identity) in enumerate(zip(contracts, declared)):
        expected_trace_identity = {
            "path": contract["path"],
            "sha256": trace_identity.get("sha256")
            if isinstance(trace_identity, Mapping)
            else None,
        }
        if trace_identity != expected_trace_identity:
            raise RunnerError(
                f"work trace retained-artifact record {index} is malformed"
            )
        relative = _safe_relative_path(
            contract["path"], f"retained artifact contract {index} path"
        )
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (OSError, ValueError) as error:
            raise RunnerError(
                f"retained artifact {relative} escapes or is absent: {error}"
            ) from error
        if resolved != candidate:
            raise RunnerError(
                f"retained artifact {relative} traverses a symbolic link"
            )
        identity = _file_identity(
            candidate,
            f"retained artifact {relative}",
            contract["maximum_bytes"],
        )
        if identity["sha256"] != trace_identity["sha256"]:
            raise RunnerError(
                f"retained artifact {relative} differs from its work-trace digest"
            )
        identities.append(
            {
                "path": relative,
                "sha256": identity["sha256"],
                "size_bytes": identity["size_bytes"],
            }
        )
    return identities


def _recompute_cubic_trace(challenge: str, job_binding: str, input_sha256: str) -> str:
    initial_domain = "sparkinterval.measured-work-trace.cubic-sum-div-three.initial.v1\n"
    step_domain = "sparkinterval.measured-work-trace.cubic-sum-div-three.step.v1\n"
    current = _digest(
        (
            initial_domain
            + f"challenge_nonce={challenge}\n"
            + f"job_binding_sha256={job_binding}\n"
            + f"input_sha256={input_sha256}\n"
        ).encode("ascii")
    )
    accumulator = 0
    for value in range(20001):
        accumulator += value * value * value
        current = _digest(
            (
                step_domain
                + f"previous={current}\n"
                + f"x={value}\n"
                + f"accumulator={accumulator}\n"
            ).encode("ascii")
        )
    return current


def _build_statement(
    job: dict[str, Any], stage: Path, files: list[dict[str, Any]],
    challenge_nonce: str, job_spec_sha256: str, job_binding: str,
    start_binding: str, trace_record: dict[str, Any], executed_argv: list[str],
    start_time: str, end_time: str,
) -> dict[str, Any]:
    target = load_profile(stage / job["target_profile"]["path"], "target")
    trust = load_profile(stage / job["trust_profile"]["path"], "trust")
    build_artifacts = [
        artifact_record(stage / item["path"], stage, role=item["statement_role"])
        for item in files
        if item["statement_role"] is not None
    ]
    execution_manifest = stage / "runner/closure-manifest.json"
    if job["algorithm"]["algorithm_id"].startswith(
        GOLDBACH_H100_ALGORITHM_PREFIX
    ):
        execution_manifest = stage / "runner/goldbach-execution-manifest.json"
    build_artifacts.append(
        artifact_record(execution_manifest, stage, role="execution_manifest")
    )
    build_artifacts.sort(key=lambda record: (record["role"], record["path"]))
    execution_environment = {
        "artifact_closure_manifest_sha256": job["artifact_closure"]["manifest_sha256"],
        "backend": job["backend"],
        "challenge_object_protocol": "retained_off_vm_challenge_v1",
        "executed_argv": executed_argv,
        "job_binding_sha256": job_binding,
        "job_spec_sha256": job_spec_sha256,
        "measured_runner_protocol": "challenge_first_pcr23_ordered_v1",
        "runner_policy_sha256": job["runner_policy"]["sha256"],
        "start_binding_sha256": start_binding,
        "work_trace_artifact_sha256": trace_record["artifact_sha256"],
        "work_trace_chain_sha256": trace_record["trace_sha256"],
    }
    if "retained_artifacts" in trace_record:
        execution_environment["retained_artifacts"] = trace_record[
            "retained_artifacts"
        ]
    completion = validate_completion(
        {
            "cuda_errors": [],
            "end_time_utc": end_time,
            "exit_code": 0,
            "expected_output_count": 1,
            "start_time_utc": start_time,
            "status": "success",
            "written_output_count": 1,
        }
    )
    statement = {
        "algorithm": {
            "algorithm_id": job["algorithm"]["algorithm_id"],
            "definition_sha256": job["algorithm"]["definition_sha256"],
        },
        "backend_kind": "gpu" if job["backend"] == "azure_ncc40ads_h100_v5" else "cpu",
        "build_artifacts": build_artifacts,
        "completion": completion,
        "domain_coverage": _bound_json(job["domain_coverage"]["value"], "domain coverage"),
        "execution_environment": _bound_json(execution_environment, "execution environment"),
        "input_artifact": artifact_record(stage / job["input_artifact"]["path"], stage),
        "nonce": challenge_nonce,
        "output_artifact": artifact_record(stage / job["output_contract"]["path"], stage),
        "parameters": _bound_json(job["parameters"]["value"], "parameters"),
        "target_profile": profile_reference(target),
        "trust_profile": profile_reference(trust),
    }
    if statement["parameters"]["canonical_sha256"] != job["parameters"]["canonical_sha256"]:
        raise RunnerError("statement parameter hash diverged from job specification")
    if statement["domain_coverage"]["canonical_sha256"] != job["domain_coverage"]["canonical_sha256"]:
        raise RunnerError("statement domain hash diverged from job specification")
    return statement


def _verify_output(path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    identity = _file_identity(path, "result artifact", contract["maximum_bytes"])
    raw = path.read_bytes()
    if contract["format"] == "canonical_decimal_natural_no_newline_v1":
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise RunnerError("natural result is not ASCII") from error
        if not text or not text.isdigit() or (len(text) > 1 and text[0] == "0"):
            raise RunnerError("result is not a canonical decimal natural")
    return identity


def _validate_h100_gate(
    path: Path, challenge: str, job_binding: str, package_root: Path
) -> dict[str, Any]:
    value, canonical = _canonical_file(path, "H100 pre-run gate record")
    gate = _exact_object(
        value,
        {
            "backend", "challenge_nonce", "evidence_sha256", "expires_at_utc",
            "evidence_manifest_path",
            "gpu_cc_environment", "gpu_cc_mode", "gpu_ready_state", "job_binding_sha256",
            "kind", "schema_version", "status",
        },
        "H100 pre-run gate record",
    )
    if (
        gate["kind"] != "sparkinterval_h100_pre_run_gate"
        or gate["schema_version"] != 1
        or gate["backend"] != "azure_ncc40ads_h100_v5"
        or gate["challenge_nonce"] != challenge
        or gate["job_binding_sha256"] != job_binding
        or gate["status"] != "release_allowed"
        or gate["gpu_cc_environment"] != "PRODUCTION"
        or gate["gpu_cc_mode"] != "ON"
        or gate["gpu_ready_state"] != "Ready"
    ):
        raise RunnerError("H100 pre-run gate did not authorize this exact challenge/job")
    _sha256(gate["evidence_sha256"], "H100 gate evidence hash")
    evidence_relative = _safe_relative_path(
        gate["evidence_manifest_path"], "H100 pre-run evidence manifest path"
    )
    evidence_path = package_root / evidence_relative
    evidence_identity = _file_identity(evidence_path, "H100 pre-run evidence manifest")
    if evidence_identity["sha256"] != gate["evidence_sha256"]:
        raise RunnerError("H100 gate record does not bind its retained evidence manifest")
    if not isinstance(gate["expires_at_utc"], str) or UTC_RE.fullmatch(gate["expires_at_utc"]) is None:
        raise RunnerError("H100 gate expiry is not canonical UTC")
    expiry = dt.datetime.strptime(gate["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    if dt.datetime.now(dt.timezone.utc) >= expiry:
        raise RunnerError("H100 pre-run gate record is expired")
    return {
        "evidence_manifest_path": evidence_relative,
        "evidence_sha256": gate["evidence_sha256"],
        "record_sha256": _digest(canonical),
        "status": "release_allowed",
    }


def execute_job(
    *, job_spec_path: Path, artifact_root: Path, challenge_path: Path,
    output_dir: Path, tpm: TPMBackend | None = None,
    process_runner: ProcessRunner = _subprocess_runner,
    allow_development_policy: bool = False,
) -> dict[str, Any]:
    """Execute one job and atomically publish a pending-appraisal run package."""

    if output_dir.exists():
        raise RunnerError(f"output directory already exists: {output_dir}")
    job_value, job_canonical = _canonical_file(job_spec_path, "measured job specification")
    job = validate_job_spec(job_value)
    challenge = load_challenge(challenge_path)
    require_current_challenge_window(challenge)
    challenge_canonical = evidence_canonical_json_bytes(challenge)
    challenge_object_sha256 = _digest(challenge_canonical)
    job_spec_sha256 = _digest(job_canonical)
    try:
        root = artifact_root.resolve(strict=True)
    except OSError as error:
        raise RunnerError(f"cannot resolve artifact root: {error}") from error
    if not root.is_dir():
        raise RunnerError("artifact root must be a directory")

    output_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.running-", dir=output_dir.parent))
    os.chmod(stage, 0o700)
    try:
        files = _validate_artifact_records(job["artifact_closure"]["files"])
        for record in files:
            _snapshot_file(
                root / record["path"], stage / record["path"], record["sha256"],
                record["size_bytes"], record["executable"],
            )
        if job["artifact_closure"]["closure_kind"] == "static_elf_source_reviewed_v1":
            host = next(item for item in files if item["statement_role"] == "host_executable")
            if _elf_has_interp(stage / host["path"]):
                raise RunnerError(
                    "static closure host executable declares a dynamic PT_INTERP loader"
                )
        closure_manifest = _closure_manifest(files)
        closure_bytes = canonical_json_bytes(closure_manifest)
        if _digest(closure_bytes) != job["artifact_closure"]["manifest_sha256"]:
            raise RunnerError("snapshotted closure manifest hash is wrong")
        _write_exclusive(stage / "runner/closure-manifest.json", closure_bytes)
        if job["algorithm"]["algorithm_id"].startswith(
            GOLDBACH_H100_ALGORITHM_PREFIX
        ):
            _write_exclusive(
                stage / "runner/goldbach-execution-manifest.json",
                goldbach_execution_projection_bytes(job),
            )
        _write_exclusive(stage / "runner/job-spec.json", job_canonical)
        _write_exclusive(stage / "runner/challenge.json", challenge_canonical)

        for field, expected_kind in (("target_profile", "target"), ("trust_profile", "trust")):
            record = job[field]
            _snapshot_file(root / record["path"], stage / record["path"], record["sha256"],
                           (root / record["path"]).stat().st_size, False)
            profile = load_profile(stage / record["path"], expected_kind)
            if profile["profile_id"] != record["profile_id"] or canonical_sha256(profile) != record["sha256"]:
                raise RunnerError(f"{field} identity/hash mismatch")
        policy_record = job["runner_policy"]
        policy_source = root / policy_record["path"]
        _snapshot_file(policy_source, stage / policy_record["path"], policy_record["sha256"],
                       policy_source.stat().st_size, False)
        policy, _policy_bytes = _canonical_file(stage / policy_record["path"], "runner policy")
        if policy.get("policy_id") != policy_record["policy_id"]:
            raise RunnerError("runner policy id does not match its contents")
        if policy.get("classification") != "production" and not allow_development_policy:
            raise RunnerError("non-production runner policy requires --allow-development-policy")

        job_binding = derive_job_binding(
            challenge_object_sha256, challenge["nonce"], job_spec_sha256,
            job["artifact_closure"]["manifest_sha256"], policy_record["sha256"],
            job["target_profile"]["sha256"], job["trust_profile"]["sha256"],
        )
        start_binding = derive_start_binding(job_binding)
        timeline: dict[str, dict[str, Any]] = {}

        def mark(name: str) -> None:
            timeline[name] = {"monotonic_ns": time.monotonic_ns(), "utc": _utc_now()}

        mark("challenge_validated")
        if tpm is None:
            if os.geteuid() != 0:
                raise RunnerError("real measured execution requires root TPM access")
            tpm = CommandTPMBackend(stage)
        tpm.reset()
        initial = tpm.read()
        mark("pcr_reset_read")
        if initial != PCR_ZERO:
            raise RunnerError("PCR23 did not reset to the all-zero SHA-256 value")
        _write_exclusive(stage / "runner/pcr23.initial.bin", initial)
        tpm.extend(start_binding)
        after_start = tpm.read()
        mark("pcr_start_extended")
        expected_after_start = pcr_extend(PCR_ZERO, start_binding)
        if after_start != expected_after_start:
            raise RunnerError("PCR23 start extension equation failed")
        _write_exclusive(stage / "runner/pcr23.after-start.bin", after_start)

        replacements = {
            "@challenge@": challenge["nonce"],
            "@challenge_expires_at@": challenge["expires_at_utc"],
            "@job_binding@": job_binding,
            "@input@": job["input_artifact"]["path"],
            "@output@": job["output_contract"]["path"],
            "@trace@": job["work_trace_contract"]["path"],
            "@gate_record@": (
                job["gpu_pre_run_gate"]["record_path"]
                if job["gpu_pre_run_gate"] is not None
                else "runner/not-applicable-gate.json"
            ),
        }
        gate_result: dict[str, Any] | None = None
        if job["backend"] == "azure_ncc40ads_h100_v5":
            gate = job["gpu_pre_run_gate"]
            gate_argv = _expand_argv(gate["argv"], replacements)
            gate_environment = dict(job["command"]["environment"])
            for name in gate["secret_environment_names"]:
                secret = os.environ.get(name)
                if not secret:
                    raise RunnerError(f"required H100 gate secret is absent: {name}")
                gate_environment[name] = secret
            exit_code = process_runner(
                gate_argv, stage, gate_environment, gate["timeout_seconds"],
                stage / "runner/gpu-gate.stdout.bin", stage / "runner/gpu-gate.stderr.bin",
            )
            if exit_code != 0:
                raise RunnerError(f"H100 pre-run gate failed with exit code {exit_code}")
            gate_result = _validate_h100_gate(
                stage / gate["record_path"], challenge["nonce"], job_binding, stage
            )
            gate_result.update(
                {
                    "argv": gate_argv,
                    "argv_sha256": canonical_sha256(gate_argv),
                    "record_path": gate["record_path"],
                    "secret_environment_names_forwarded": gate[
                        "secret_environment_names"
                    ],
                }
            )
            mark("gpu_gate_passed")

        input_record = job["input_artifact"]
        input_destination = stage / input_record["path"]
        if input_destination.exists():
            raise RunnerError("input destination existed before post-start release")
        if input_record["release_mode"] == "prepositioned_public_after_start":
            _snapshot_file(
                root / input_record["path"], input_destination, input_record["sha256"],
                input_record["size_bytes"], False,
            )
        else:
            release_argv = _expand_argv(input_record["release_argv"], replacements)
            exit_code = process_runner(
                release_argv, stage, job["command"]["environment"], 600,
                stage / "runner/input-release.stdout.bin", stage / "runner/input-release.stderr.bin",
            )
            if exit_code != 0:
                raise RunnerError(f"input release failed with exit code {exit_code}")
        input_identity = _file_identity(input_destination, "released input")
        if (
            input_identity["sha256"] != input_record["sha256"]
            or input_identity["size_bytes"] != input_record["size_bytes"]
        ):
            raise RunnerError("released input does not match its source-reviewed digest")
        os.chmod(input_destination, 0o400)
        mark("input_released")
        require_current_challenge_window(challenge)

        output_path = stage / job["output_contract"]["path"]
        trace_path = stage / job["work_trace_contract"]["path"]
        for candidate in (output_path, trace_path):
            if candidate.exists():
                raise RunnerError(f"fresh workload destination already exists: {candidate}")
            candidate.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        argv = _expand_argv(job["command"]["argv"], replacements)
        workload_environment = dict(job["command"]["environment"])
        if policy.get("classification") == "production":
            try:
                workload_environment = azure_measured_worker_environment(
                    workload_environment,
                    backend=job["backend"],
                    challenge_nonce=challenge["nonce"],
                    job_binding=job_binding,
                )
            except MeasuredWorkerScopeError as error:
                raise RunnerError(str(error)) from error
        mark("workload_started")
        start_time = timeline["workload_started"]["utc"]
        exit_code = process_runner(
            argv, stage, workload_environment, job["command"]["timeout_seconds"],
            stage / "runner/workload.stdout.bin", stage / "runner/workload.stderr.bin",
        )
        mark("workload_finished")
        end_time = timeline["workload_finished"]["utc"]
        if exit_code != 0:
            raise RunnerError(f"measured workload failed with exit code {exit_code}")
        trace_contract = job["work_trace_contract"]
        if trace_contract["verification_mode"] == "pinned_external_trace_verifier_v1":
            trace_verifier_argv = _expand_argv(trace_contract["verifier_argv"], replacements)
            trace_exit_code = process_runner(
                trace_verifier_argv,
                stage,
                workload_environment,
                job["command"]["timeout_seconds"],
                stage / "runner/trace-verifier.stdout.bin",
                stage / "runner/trace-verifier.stderr.bin",
            )
            if trace_exit_code != 0:
                raise RunnerError(
                    f"pinned work-trace verifier failed with exit code {trace_exit_code}"
                )
            for record in files:
                current = _file_identity(stage / record["path"], f"closure artifact {record['path']}")
                if current["sha256"] != record["sha256"] or current["size_bytes"] != record["size_bytes"]:
                    raise RunnerError("external trace verifier changed an artifact-closure member")
        # Hash every mutable workload artifact only after any external trace
        # verifier has exited.  This closes a stale-hash window in which a
        # verifier could otherwise alter input/result/trace before statement
        # construction.
        input_after_verifier = _file_identity(input_destination, "released input after trace verification")
        if (
            input_after_verifier["sha256"] != input_record["sha256"]
            or input_after_verifier["size_bytes"] != input_record["size_bytes"]
        ):
            raise RunnerError("input changed during external trace verification")
        output_identity = _verify_output(output_path, job["output_contract"])
        trace_record = _validate_trace(
            trace_path, algorithm_id=job["algorithm"]["algorithm_id"],
            challenge_nonce=challenge["nonce"], job_binding=job_binding,
            input_sha256=input_record["sha256"], result_sha256=output_identity["sha256"],
            contract=trace_contract,
            input_bytes=(
                input_destination.read_bytes()
                if trace_contract["verification_mode"]
                == "builtin_cubic_sum_div_three_20000_v1"
                else None
            ),
            retained_artifact_contracts=job.get(
                "retained_artifact_contracts", []
            ),
        )
        retained_artifacts = _validate_retained_artifacts(
            stage,
            job.get("retained_artifact_contracts", []),
            trace_record,
        )
        if retained_artifacts:
            trace_record["retained_artifacts"] = retained_artifacts
        trace_record["path"] = job["work_trace_contract"]["path"]
        mark("artifacts_validated")

        statement = _build_statement(
            job, stage, files, challenge["nonce"], job_spec_sha256, job_binding,
            start_binding, trace_record, argv, start_time, end_time,
        )
        statement_bytes = canonical_json_bytes(statement)
        statement_sha256 = _digest(statement_bytes)
        _write_exclusive(stage / "runner/statement.json", statement_bytes)
        result_binding = derive_binding_nonce(challenge["nonce"], statement_sha256)
        tpm.extend(result_binding)
        after_result = tpm.read()
        mark("pcr_result_extended")
        expected_after_result = pcr_extend(after_start, result_binding)
        if after_result != expected_after_result:
            raise RunnerError("PCR23 ordered result extension equation failed")
        _write_exclusive(stage / "runner/pcr23.after-result.bin", after_result)
        quote = tpm.quote(result_binding, stage / "runner")
        mark("quote_completed")
        require_current_challenge_window(challenge)

        quote_artifacts = []
        for path in sorted((stage / "runner").iterdir()):
            if path.is_file() and path.name.startswith(("tpm_", "vtpm_", "azure_hcl_", "tcg_")):
                quote_artifacts.append(
                    {"path": path.relative_to(stage).as_posix(), "sha256": _digest(path.read_bytes()),
                     "size_bytes": path.stat().st_size}
                )
        transcript = {
            "accepted": False,
            "algorithm": {
                "algorithm_id": job["algorithm"]["algorithm_id"],
                "definition_sha256": job["algorithm"]["definition_sha256"],
            },
            "artifact_closure": {
                "closure_kind": job["artifact_closure"]["closure_kind"],
                "manifest_sha256": job["artifact_closure"]["manifest_sha256"],
            },
            "backend": job["backend"],
            "bindings": {
                "challenge_object_sha256": challenge_object_sha256,
                "job_binding_sha256": job_binding,
                "job_spec_sha256": job_spec_sha256,
                "result_binding_sha256": result_binding,
                "start_binding_sha256": start_binding,
                "statement_sha256": statement_sha256,
            },
            "challenge": challenge,
            "command": {
                "argv": argv,
                "argv_sha256": canonical_sha256(argv),
                "environment": job["command"]["environment"],
                "exit_code": exit_code,
                "shell": False,
            },
            "gpu_pre_run_gate": gate_result,
            "input_artifact": {
                "path": input_record["path"], "release_mode": input_record["release_mode"],
                "sha256": input_identity["sha256"], "size_bytes": input_identity["size_bytes"],
            },
            "job_id": job["job_id"],
            "kind": TRANSCRIPT_KIND,
            "output_artifact": {
                "format": job["output_contract"]["format"],
                "path": job["output_contract"]["path"],
                "sha256": output_identity["sha256"], "size_bytes": output_identity["size_bytes"],
            },
            "pcr23": {
                "after_result_hex": after_result.hex(),
                "after_start_hex": after_start.hex(),
                "bank": PCR_BANK,
                "index": PCR_INDEX,
                "initial_hex": initial.hex(),
                "ordered_equation": (
                    "PCR23_started=SHA256(0^32||start_binding);"
                    "PCR23_final=SHA256(PCR23_started||result_binding)"
                ),
            },
            "profiles": {
                "target_profile_id": job["target_profile"]["profile_id"],
                "target_profile_sha256": job["target_profile"]["sha256"],
                "trust_profile_id": job["trust_profile"]["profile_id"],
                "trust_profile_sha256": job["trust_profile"]["sha256"],
            },
            "quote": {**quote, "artifacts": quote_artifacts},
            "runner_policy": {
                "classification": policy.get("classification"),
                "policy_id": policy_record["policy_id"],
                "sha256": policy_record["sha256"],
            },
            "schema_version": SCHEMA_VERSION,
            "statement": {"path": "runner/statement.json", "sha256": statement_sha256},
            "status": "run_complete_pending_independent_hardware_appraisal",
            "timing": timeline,
            "trust_boundary": {
                "hardware_quote_appraised": False,
                "mathematical_correctness_proven_by_runner": False,
                "measured_runner_policy_appraised": False,
                "signed_acceptance_certificate_issued": False,
            },
            "work_trace": trace_record,
        }
        if set(transcript) != TRANSCRIPT_KEYS:
            raise RunnerError("internal transcript field mismatch")
        _write_exclusive(stage / "runner/transcript.json", canonical_json_bytes(transcript))
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(stage, output_dir)
        return {
            "accepted": False,
            "backend": job["backend"],
            "classification": "measured_run_complete_pending_independent_hardware_appraisal",
            "job_binding_sha256": job_binding,
            "output_dir": str(output_dir),
            "result_binding_sha256": result_binding,
            "statement_sha256": statement_sha256,
        }
    except (BundleError, OSError, ValueError, json.JSONDecodeError) as error:
        shutil.rmtree(stage, ignore_errors=True)
        if isinstance(error, RunnerError):
            raise
        raise RunnerError(str(error)) from error
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-spec", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-development-policy", action="store_true",
        help="run a non-production policy for testing; output still says accepted=false",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute_job(
            job_spec_path=args.job_spec,
            artifact_root=args.artifact_root,
            challenge_path=args.challenge,
            output_dir=args.output_dir,
            allow_development_policy=args.allow_development_policy,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (RunnerError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "measured_runner_failed_closed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
