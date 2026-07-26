#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Verify a challenge-first measured-runner transcript and PCR equations.

This is a relying-party *component*.  It verifies the source-reviewed job
allowlist, retained challenge, complete artifact manifest, exact statement,
challenge-dependent work trace, causal event ordering, and the two PCR23
extension equations.  It does not authenticate a TPM quote or an Azure/NVIDIA
endorsement chain, so its JSON result always has ``accepted: false``.  A
production Azure appraiser must run this logic on immutable snapshots and then
authenticate that the quoted final PCR belongs to the allowed measured image.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_path in (
    REPOSITORY_ROOT,
    REPOSITORY_ROOT / "azure",
    REPOSITORY_ROOT / "tools",
    REPOSITORY_ROOT / "attestation",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from create_run_bundle import canonical_json_bytes, canonical_sha256  # noqa: E402
from measured_runner import (  # noqa: E402
    PCR_ZERO,
    TRANSCRIPT_KEYS,
    TRANSCRIPT_KIND,
    RunnerError,
    _build_statement,
    _canonical_file,
    _closure_manifest,
    _expand_argv,
    _file_identity,
    _safe_relative_path,
    _validate_artifact_records,
    _validate_h100_gate,
    _validate_retained_artifacts,
    _validate_trace,
    _verify_output,
    derive_job_binding,
    derive_start_binding,
    pcr_extend,
    validate_job_spec,
)
from collect_azure_ncc_evidence import (  # noqa: E402
    TPM_PCR_SELECTION,
    derive_binding_nonce,
    require_current_challenge_window,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GOLDBACH_H100_ALGORITHM_PREFIX,
    GoldbachBuildAdmissionError,
    goldbach_execution_projection,
)


POLICY_KIND = "sparkinterval_measured_runner_appraisal_policy"
POLICY_KEYS = {
    "allowed_backends",
    "allowed_job_spec_sha256",
    "allowed_runner_policy_sha256",
    "allowed_target_profile_sha256",
    "allowed_trust_profile_sha256",
    "classification",
    "kind",
    "policy_id",
    "require_authenticated_hardware_quote",
    "required_composite_appraiser_claims",
    "schema_version",
}
REQUIRED_COMPOSITE_CLAIMS = {
    "measured_runner_policy_valid",
    "result_artifact_bound_to_execution",
}
REQUIRED_QUOTE_ARTIFACTS = {
    "runner/azure_hcl_report.bin",
    "runner/azure_hcl_runtime_data.bin",
    "runner/tcg_event_log.bin",
    "runner/tpm_quote.msg",
    "runner/tpm_quote.pcrs",
    "runner/tpm_quote.sig",
    "runner/vtpm_ak.pem",
    "runner/vtpm_ak_cert.bin",
}
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class TranscriptError(RuntimeError):
    """A transcript or its relying-party allowlist failed closed."""


def _exact(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise TranscriptError(
            f"{what} has wrong fields "
            f"(missing={sorted(keys - actual)}, unexpected={sorted(actual - keys)})"
        )
    return value


def _digest(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise TranscriptError(f"required artifact is not a regular non-symlink file: {path}")
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _allowlist(values: Any, what: str) -> set[str]:
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in values
    ):
        raise TranscriptError(f"{what} must be a nonempty SHA-256 allowlist")
    if len(values) != len(set(values)):
        raise TranscriptError(f"{what} contains duplicates")
    return set(values)


def load_policy(path: Path, allow_development: bool) -> tuple[dict[str, Any], str]:
    try:
        value, canonical = _canonical_file(path, "measured-runner appraisal policy")
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    policy = _exact(value, POLICY_KEYS, "measured-runner appraisal policy")
    if policy["kind"] != POLICY_KIND or policy["schema_version"] != 1:
        raise TranscriptError("unsupported measured-runner appraisal policy")
    if policy["classification"] not in ("development", "production"):
        raise TranscriptError("appraisal policy classification is invalid")
    if policy["classification"] != "production" and not allow_development:
        raise TranscriptError("development appraisal policy requires explicit opt-in")
    if policy["require_authenticated_hardware_quote"] is not True:
        raise TranscriptError("appraisal policy must require an authenticated hardware quote")
    claims = policy["required_composite_appraiser_claims"]
    if not isinstance(claims, list) or set(claims) != REQUIRED_COMPOSITE_CLAIMS:
        raise TranscriptError("appraisal policy has wrong composite-appraiser claims")
    if not isinstance(policy["allowed_backends"], list) or not policy["allowed_backends"]:
        raise TranscriptError("appraisal policy backend allowlist is empty")
    for name in (
        "allowed_job_spec_sha256",
        "allowed_runner_policy_sha256",
        "allowed_target_profile_sha256",
        "allowed_trust_profile_sha256",
    ):
        _allowlist(policy[name], name)
    if not isinstance(policy["policy_id"], str) or not policy["policy_id"]:
        raise TranscriptError("appraisal policy id is absent")
    return policy, hashlib.sha256(canonical).hexdigest()


def _verify_timing(transcript: dict[str, Any], challenge: dict[str, Any]) -> None:
    required = [
        "challenge_validated",
        "pcr_reset_read",
        "pcr_start_extended",
    ]
    if transcript["backend"] == "azure_ncc40ads_h100_v5":
        required.append("gpu_gate_passed")
    required.extend(
        [
            "input_released",
            "workload_started",
            "workload_finished",
            "artifacts_validated",
            "pcr_result_extended",
            "quote_completed",
        ]
    )
    timing = transcript["timing"]
    if not isinstance(timing, dict) or set(timing) != set(required):
        raise TranscriptError("runner timing events are absent or out of protocol order")
    previous_monotonic = -1
    previous_wall: dt.datetime | None = None
    issued = dt.datetime.strptime(challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    expires = dt.datetime.strptime(challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    for name in required:
        record = _exact(timing[name], {"monotonic_ns", "utc"}, f"timing event {name}")
        monotonic = record["monotonic_ns"]
        if not isinstance(monotonic, int) or isinstance(monotonic, bool) or monotonic <= previous_monotonic:
            raise TranscriptError("runner monotonic event order is not strictly increasing")
        if not isinstance(record["utc"], str) or UTC_RE.fullmatch(record["utc"]) is None:
            raise TranscriptError(f"timing event {name} is not canonical UTC")
        wall = dt.datetime.strptime(record["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
        if not issued <= wall < expires or (previous_wall is not None and wall < previous_wall):
            raise TranscriptError("runner wall-clock events leave the challenge window or regress")
        previous_monotonic = monotonic
        previous_wall = wall


def _artifact_matches(root: Path, record: dict[str, Any]) -> None:
    try:
        relative = _safe_relative_path(record["path"], "artifact inventory path")
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    path = root / relative
    digest, size = _digest(path)
    if digest != record["sha256"] or size != record["size_bytes"]:
        raise TranscriptError(f"artifact differs from transcript/job record: {record['path']}")


def verify(
    package: Path,
    retained_challenge: Path,
    policy_path: Path,
    *,
    allow_development_policy: bool = False,
) -> dict[str, Any]:
    if package.is_symlink():
        raise TranscriptError("run package must not be a symlink")
    try:
        root = package.resolve(strict=True)
    except OSError as error:
        raise TranscriptError(f"cannot resolve run package: {error}") from error
    if not root.is_dir():
        raise TranscriptError("run package is not a directory")
    policy, policy_sha256 = load_policy(policy_path, allow_development_policy)
    try:
        job_value, job_bytes = _canonical_file(root / "runner/job-spec.json", "packaged job spec")
        job = validate_job_spec(job_value)
        transcript_value, _transcript_bytes = _canonical_file(
            root / "runner/transcript.json", "runner transcript"
        )
        transcript = _exact(transcript_value, TRANSCRIPT_KEYS, "runner transcript")
        challenge_value, challenge_bytes = _canonical_file(
            retained_challenge, "retained off-VM challenge"
        )
        packaged_challenge, packaged_challenge_bytes = _canonical_file(
            root / "runner/challenge.json", "packaged challenge"
        )
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    if packaged_challenge != challenge_value or packaged_challenge_bytes != challenge_bytes:
        raise TranscriptError("packaged challenge differs from the retained off-VM challenge")
    try:
        require_current_challenge_window(challenge_value)
    except Exception as error:
        raise TranscriptError(f"retained challenge is not current: {error}") from error
    if transcript["accepted"] is not False or transcript["kind"] != TRANSCRIPT_KIND or transcript[
        "schema_version"
    ] != 1:
        raise TranscriptError("runner transcript kind/version/acceptance boundary is wrong")
    if transcript["status"] != "run_complete_pending_independent_hardware_appraisal":
        raise TranscriptError("runner transcript overclaims or has incomplete status")
    trust = _exact(
        transcript["trust_boundary"],
        {
            "hardware_quote_appraised",
            "mathematical_correctness_proven_by_runner",
            "measured_runner_policy_appraised",
            "signed_acceptance_certificate_issued",
        },
        "runner trust boundary",
    )
    if set(trust.values()) != {False}:
        raise TranscriptError("runner transcript overclaims trust-boundary verification")
    if transcript["challenge"] != challenge_value:
        raise TranscriptError("transcript challenge differs from retained challenge")
    if transcript["backend"] != job["backend"] or transcript["backend"] not in policy[
        "allowed_backends"
    ]:
        raise TranscriptError("runner backend is not job/policy allowed")
    if transcript["job_id"] != job["job_id"]:
        raise TranscriptError("transcript job id differs from job spec")
    if transcript["algorithm"] != {
        "algorithm_id": job["algorithm"]["algorithm_id"],
        "definition_sha256": job["algorithm"]["definition_sha256"],
    }:
        raise TranscriptError("transcript algorithm differs from job spec")
    if transcript["artifact_closure"] != {
        "closure_kind": job["artifact_closure"]["closure_kind"],
        "manifest_sha256": job["artifact_closure"]["manifest_sha256"],
    }:
        raise TranscriptError("transcript artifact closure differs from job spec")
    if transcript["profiles"] != {
        "target_profile_id": job["target_profile"]["profile_id"],
        "target_profile_sha256": job["target_profile"]["sha256"],
        "trust_profile_id": job["trust_profile"]["profile_id"],
        "trust_profile_sha256": job["trust_profile"]["sha256"],
    }:
        raise TranscriptError("transcript profile tuple differs from job spec")

    job_sha256 = hashlib.sha256(job_bytes).hexdigest()
    if job_sha256 not in _allowlist(policy["allowed_job_spec_sha256"], "job allowlist"):
        raise TranscriptError("job specification is not relying-party allowlisted")
    runner_policy_sha256 = job["runner_policy"]["sha256"]
    if runner_policy_sha256 not in _allowlist(
        policy["allowed_runner_policy_sha256"], "runner-policy allowlist"
    ):
        raise TranscriptError("runner policy is not relying-party allowlisted")
    runner_policy_value, _runner_policy_bytes = _canonical_file(
        root / job["runner_policy"]["path"], "packaged runner policy"
    )
    if (
        policy["classification"] == "production"
        and runner_policy_value.get("classification") != "production"
    ):
        raise TranscriptError(
            "production appraisal cannot authorize a non-production measured-runner policy"
        )
    if transcript["runner_policy"] != {
        "classification": runner_policy_value.get("classification"),
        "policy_id": job["runner_policy"]["policy_id"],
        "sha256": runner_policy_sha256,
    }:
        raise TranscriptError("transcript runner-policy metadata differs from job spec")
    if job["target_profile"]["sha256"] not in _allowlist(
        policy["allowed_target_profile_sha256"], "target-profile allowlist"
    ):
        raise TranscriptError("target profile is not relying-party allowlisted")
    if job["trust_profile"]["sha256"] not in _allowlist(
        policy["allowed_trust_profile_sha256"], "trust-profile allowlist"
    ):
        raise TranscriptError("trust profile is not relying-party allowlisted")

    files = _validate_artifact_records(job["artifact_closure"]["files"])
    closure_value, closure_bytes = _canonical_file(
        root / "runner/closure-manifest.json", "packaged artifact closure"
    )
    if closure_value != _closure_manifest(files):
        raise TranscriptError("packaged artifact closure differs from the job spec")
    closure_sha256 = hashlib.sha256(closure_bytes).hexdigest()
    if closure_sha256 != job["artifact_closure"]["manifest_sha256"]:
        raise TranscriptError("artifact closure manifest hash is wrong")
    if job["algorithm"]["algorithm_id"].startswith(
        GOLDBACH_H100_ALGORITHM_PREFIX
    ):
        try:
            execution_value, _execution_bytes = _canonical_file(
                root / "runner/goldbach-execution-manifest.json",
                "packaged Goldbach execution projection",
            )
            expected_execution = goldbach_execution_projection(job)
        except (GoldbachBuildAdmissionError, RunnerError) as error:
            raise TranscriptError(
                f"Goldbach execution projection is malformed: {error}"
            ) from error
        if execution_value != expected_execution:
            raise TranscriptError(
                "Goldbach execution projection differs from the actual job"
            )
    for record in files:
        _artifact_matches(root, record)
    for name in ("target_profile", "trust_profile", "runner_policy"):
        record = job[name]
        digest, _size = _digest(root / record["path"])
        if digest != record["sha256"]:
            raise TranscriptError(f"packaged {name} hash is wrong")

    challenge_object_sha256 = hashlib.sha256(challenge_bytes).hexdigest()
    job_binding = derive_job_binding(
        challenge_object_sha256,
        challenge_value["nonce"],
        job_sha256,
        closure_sha256,
        runner_policy_sha256,
        job["target_profile"]["sha256"],
        job["trust_profile"]["sha256"],
    )
    start_binding = derive_start_binding(job_binding)
    bindings = _exact(
        transcript["bindings"],
        {
            "challenge_object_sha256",
            "job_binding_sha256",
            "job_spec_sha256",
            "result_binding_sha256",
            "start_binding_sha256",
            "statement_sha256",
        },
        "runner bindings",
    )
    if bindings != {
        **bindings,
        "challenge_object_sha256": challenge_object_sha256,
        "job_binding_sha256": job_binding,
        "job_spec_sha256": job_sha256,
        "start_binding_sha256": start_binding,
    }:
        raise TranscriptError("runner pre-execution bindings are inconsistent")

    replacements = {
        "@challenge@": challenge_value["nonce"],
        "@challenge_expires_at@": challenge_value["expires_at_utc"],
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
    argv = _expand_argv(job["command"]["argv"], replacements)
    command = _exact(
        transcript["command"], {"argv", "argv_sha256", "environment", "exit_code", "shell"},
        "runner command",
    )
    if command != {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": job["command"]["environment"],
        "exit_code": 0,
        "shell": False,
    }:
        raise TranscriptError("runner command is not the exact source-reviewed no-shell argv")

    input_record = transcript["input_artifact"]
    if input_record != {
        "path": job["input_artifact"]["path"],
        "release_mode": job["input_artifact"]["release_mode"],
        "sha256": job["input_artifact"]["sha256"],
        "size_bytes": job["input_artifact"]["size_bytes"],
    }:
        raise TranscriptError("transcript input record differs from job spec")
    _artifact_matches(root, input_record)
    output_record = transcript["output_artifact"]
    _artifact_matches(root, output_record)
    if output_record["path"] != job["output_contract"]["path"] or output_record[
        "format"
    ] != job["output_contract"]["format"]:
        raise TranscriptError("transcript result differs from output contract")
    try:
        independently_checked_output = _verify_output(
            root / output_record["path"], job["output_contract"]
        )
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    if (
        independently_checked_output["sha256"] != output_record["sha256"]
        or independently_checked_output["size_bytes"] != output_record["size_bytes"]
    ):
        raise TranscriptError("independent result-contract check diverged from transcript")

    if job["backend"] == "azure_ncc40ads_h100_v5":
        gate_contract = job["gpu_pre_run_gate"]
        gate_argv = _expand_argv(gate_contract["argv"], replacements)
        try:
            expected_gate = _validate_h100_gate(
                root / gate_contract["record_path"],
                challenge_value["nonce"],
                job_binding,
                root,
            )
        except RunnerError as error:
            raise TranscriptError(str(error)) from error
        expected_gate.update(
            {
                "argv": gate_argv,
                "argv_sha256": canonical_sha256(gate_argv),
                "record_path": gate_contract["record_path"],
                "secret_environment_names_forwarded": gate_contract[
                    "secret_environment_names"
                ],
            }
        )
        if transcript["gpu_pre_run_gate"] != expected_gate:
            raise TranscriptError("transcript H100 pre-run gate metadata is inconsistent")
    elif transcript["gpu_pre_run_gate"] is not None:
        raise TranscriptError("CPU transcript contains an H100 gate record")

    trace_contract = job["work_trace_contract"]
    if trace_contract["verification_mode"] == "pinned_external_trace_verifier_v1":
        verifier_argv = _expand_argv(trace_contract["verifier_argv"], replacements)
        completed = subprocess.run(
            verifier_argv,
            cwd=root,
            env=job["command"]["environment"],
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=job["command"]["timeout_seconds"],
        )
        if completed.returncode != 0:
            raise TranscriptError("independent pinned work-trace verifier rejected the trace")
        for record in files:
            _artifact_matches(root, record)
        _artifact_matches(root, input_record)
        _artifact_matches(root, output_record)
        trace_path = root / _safe_relative_path(
            trace_contract["path"], "work-trace artifact path"
        )
        trace_digest_after, trace_size_after = _digest(trace_path)
        transcript_trace = transcript["work_trace"]
        if (
            trace_digest_after != transcript_trace.get("artifact_sha256")
            or trace_size_after != trace_path.stat().st_size
        ):
            raise TranscriptError("external trace verifier changed the work-trace artifact")
    try:
        trace = _validate_trace(
            root / trace_contract["path"],
            algorithm_id=job["algorithm"]["algorithm_id"],
            challenge_nonce=challenge_value["nonce"],
            job_binding=job_binding,
            input_sha256=input_record["sha256"],
            result_sha256=output_record["sha256"],
            contract=trace_contract,
            input_bytes=(
                (root / input_record["path"]).read_bytes()
                if trace_contract["verification_mode"]
                == "builtin_cubic_sum_div_three_20000_v1"
                else None
            ),
            retained_artifact_contracts=job.get(
                "retained_artifact_contracts", []
            ),
        )
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    try:
        retained_artifacts = _validate_retained_artifacts(
            root,
            job.get("retained_artifact_contracts", []),
            trace,
        )
    except RunnerError as error:
        raise TranscriptError(str(error)) from error
    if retained_artifacts:
        trace["retained_artifacts"] = retained_artifacts
    trace["path"] = trace_contract["path"]
    if transcript["work_trace"] != trace:
        raise TranscriptError("transcript work-trace record is inconsistent")

    _verify_timing(transcript, challenge_value)
    expected_statement = _build_statement(
        job,
        root,
        files,
        challenge_value["nonce"],
        job_sha256,
        job_binding,
        start_binding,
        trace,
        argv,
        transcript["timing"]["workload_started"]["utc"],
        transcript["timing"]["workload_finished"]["utc"],
    )
    statement_value, statement_bytes = _canonical_file(
        root / "runner/statement.json", "runner statement"
    )
    if statement_value != expected_statement:
        raise TranscriptError("runner statement does not reconstruct from the source-reviewed job")
    statement_sha256 = hashlib.sha256(statement_bytes).hexdigest()
    result_binding = derive_binding_nonce(challenge_value["nonce"], statement_sha256)
    if bindings["statement_sha256"] != statement_sha256 or bindings[
        "result_binding_sha256"
    ] != result_binding:
        raise TranscriptError("statement/result binding is inconsistent")
    if transcript["statement"] != {
        "path": "runner/statement.json",
        "sha256": statement_sha256,
    }:
        raise TranscriptError("transcript statement record is inconsistent")

    pcr = _exact(
        transcript["pcr23"],
        {"after_result_hex", "after_start_hex", "bank", "index", "initial_hex", "ordered_equation"},
        "PCR23 transcript",
    )
    expected_start = pcr_extend(PCR_ZERO, start_binding)
    expected_final = pcr_extend(expected_start, result_binding)
    expected_equation = (
        "PCR23_started=SHA256(0^32||start_binding);"
        "PCR23_final=SHA256(PCR23_started||result_binding)"
    )
    if pcr != {
        "after_result_hex": expected_final.hex(),
        "after_start_hex": expected_start.hex(),
        "bank": "sha256",
        "index": 23,
        "initial_hex": PCR_ZERO.hex(),
        "ordered_equation": expected_equation,
    }:
        raise TranscriptError("PCR23 ordered extension equations are invalid")
    for filename, expected in (
        ("runner/pcr23.initial.bin", PCR_ZERO),
        ("runner/pcr23.after-start.bin", expected_start),
        ("runner/pcr23.after-result.bin", expected_final),
    ):
        path = root / filename
        if path.is_symlink() or path.read_bytes() != expected:
            raise TranscriptError(f"PCR artifact does not match transcript: {filename}")

    quote = _exact(
        transcript["quote"],
        {"ak_handle", "artifacts", "local_checkquote_passed", "pcr_selection", "qualifying_data_sha256"},
        "quote record",
    )
    if (
        quote["ak_handle"] != "0x81000003"
        or quote["local_checkquote_passed"] is not True
        or quote["pcr_selection"] != TPM_PCR_SELECTION
        or quote["qualifying_data_sha256"] != result_binding
    ):
        raise TranscriptError("quote record does not bind the final measured run")
    artifacts = quote["artifacts"]
    if not isinstance(artifacts, list):
        raise TranscriptError("quote artifact inventory is absent")
    paths: set[str] = set()
    for record in artifacts:
        _exact(record, {"path", "sha256", "size_bytes"}, "quote artifact")
        if record["path"] in paths:
            raise TranscriptError("quote artifact inventory has duplicate paths")
        paths.add(record["path"])
        _artifact_matches(root, record)
    if not REQUIRED_QUOTE_ARTIFACTS <= paths:
        raise TranscriptError(
            f"quote artifact closure is incomplete: {sorted(REQUIRED_QUOTE_ARTIFACTS - paths)}"
        )

    return {
        "accepted": False,
        "backend": job["backend"],
        "claims": {
            "artifact_closure_valid": True,
            "causal_transcript_equations_valid": True,
            "challenge_dependent_work_trace_valid": True,
            "hardware_quote_authenticated": False,
            "job_and_runner_policy_allowlisted": True,
            "retained_challenge_valid": True,
        },
        "classification": "transcript_valid_pending_authenticated_hardware_appraisal",
        "job_spec_sha256": job_sha256,
        "policy_sha256": policy_sha256,
        "result_binding_sha256": result_binding,
        "statement_sha256": statement_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-package", type=Path, required=True)
    parser.add_argument("--retained-challenge", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--allow-development-policy", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify(
            args.run_package,
            args.retained_challenge,
            args.policy,
            allow_development_policy=args.allow_development_policy,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (TranscriptError, RunnerError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "measured_runner_transcript_rejected",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
