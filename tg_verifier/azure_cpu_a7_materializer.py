# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the closed CH25 Lemma A.7 Azure SEV-SNP CPU job."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.analytic import (
    AnalyticArtifactError,
    read_analytic_artifact_bytes,
    verify_a7_boundary_bytes,
)
from tg_verifier.azure_cpu_a7_workload_factory import (
    A7_FACTORY,
    RETAINED_ARTIFACT_SHA256,
    SOURCE_PATHS,
    A7CPUWorkloadFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_platt_head_materializer import (
    PlattHeadMaterializerError,
    _build_python_flint_runtime_closure,
    _flint_identity,
    _profile_and_policy_records,
    _python_flint_identity,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    MaterializerError as CommonMaterializerError,
    PROFILE_PATHS,
    _absolute,
    _artifact_record,
    _copy_exact,
    _file_pin,
    _load_handoff,
    _operator_config,
    _pin,
    _source_pin,
    _transcript_policy,
    _write_bytes,
    load_site as load_base_site,
    record_hash,
)
from tg_verifier.campaign_io import CampaignIOError, load_json
from tg_verifier.python_flint_runtime import (
    PythonFlintRuntimeError,
    load_pin as load_python_flint_pin,
    verify_wheel,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (
    REPOSITORY_ROOT / "azure",
    REPOSITORY_ROOT / "attestation",
    REPOSITORY_ROOT / "tools",
):
    if str(directory) not in os.sys.path:
        os.sys.path.insert(0, str(directory))

import cpu_production_orchestrator as cpu_operator  # noqa: E402
from generate_trusted_compute_lean import (  # noqa: E402
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.a7-boundary-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.a7-boundary-materialization.v1"
SITE_FIELDS = {"a7", "base_site", "kind", "schema_version"}
A7_FIELDS = {
    "artifact",
    "flint_source_root",
    "python_flint_source_root",
    "python_flint_wheel",
}
FIXED_TOOL_PATH = "/usr/bin:/bin"
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.ch25-a7-boundary.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || wheel-sha256)\n"
    "step-1=SHA256(step-domain || previous || retained-artifact-sha256 || normalized-report-sha256)\n"
    "step-2=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-python-flint-replays-all-16191-leaves-and-exact-endpoints"
)


class A7MaterializerError(RuntimeError):
    """The A.7 handoff, source closure, artifact, or job failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise A7MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise A7MaterializerError(f"{what} must be a non-symlink directory")
    return path


def _artifact_identity(path: Path) -> dict[str, Any]:
    try:
        raw = read_analytic_artifact_bytes(path, label="A7 boundary artifact")
        report = verify_a7_boundary_bytes(raw, require_retained_identity=True)
    except (AnalyticArtifactError, OSError, ValueError) as error:
        raise A7MaterializerError(
            f"retained A.7 artifact failed structural review: {error}"
        ) from error
    if report.get("artifact_sha256") != RETAINED_ARTIFACT_SHA256:
        raise A7MaterializerError("retained A.7 artifact identity differs")
    return {
        "leaf_count": report["leaf_count"],
        "sha256": report["artifact_sha256"],
        "size_bytes": len(raw),
    }


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise A7MaterializerError(
            f"cannot load canonical A.7 materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "A.7 materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise A7MaterializerError("unsupported A.7 materializer site kind/version")
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise A7MaterializerError(str(error)) from error
    inputs = _exact(site["a7"], A7_FIELDS, "A.7 inputs")
    flint = _directory(inputs["flint_source_root"], "FLINT source root")
    python_flint = _directory(
        inputs["python_flint_source_root"], "python-flint source root"
    )
    _artifact_pin, artifact = _pin(inputs["artifact"], "retained A.7 artifact")
    _wheel_pin, wheel = _pin(inputs["python_flint_wheel"], "python-flint wheel")
    _flint_identity(flint)
    _python_flint_identity(python_flint)
    _artifact_identity(artifact)
    try:
        verify_wheel(wheel, load_python_flint_pin())
    except PythonFlintRuntimeError as error:
        raise A7MaterializerError(str(error)) from error
    return {"a7": inputs, "base": base, "site_pin": _file_pin(path)}


def plan_materialization(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    group, shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise A7MaterializerError("portfolio group has no closed A.7 CPU factory")
    if shard.get("argv") != list(factory.portfolio_argv):
        raise A7MaterializerError(
            "portfolio shard argv differs from the closed A.7 factory"
        )
    registered = registered_invocation_expected(factory.registered_invocation)
    local = expected_registered_hashes()
    if (
        registered_invocation_backend(factory.registered_invocation)
        != cpu_operator.BACKEND
        or any(registered.get(key) != value for key, value in local.items())
        or registered.get("result") != "true"
    ):
        raise A7MaterializerError("registered A.7 identity differs from the factory")
    source_rows = [_source_pin(context, relative)[0] for relative in SOURCE_PATHS]
    for relative in PROFILE_PATHS.values():
        _source_pin(context, relative)
    issued = cpu_operator.dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    expires = cpu_operator.dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    ttl = int((expires - issued).total_seconds())
    if ttl <= factory.timeout_seconds + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS:
        raise A7MaterializerError(
            "challenge TTL cannot contain the A.7 job and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise A7MaterializerError(
            "materializer output_root must stay outside the repository"
        )
    python = shutil.which("python3", path=FIXED_TOOL_PATH)
    python_path = Path(python).resolve(strict=True) if python else None
    supported = (
        platform.machine() == "x86_64"
        and python_path is not None
        and python_path.is_file()
        and os.access(python_path, os.X_OK)
    )
    artifact = Path(site["a7"]["artifact"]["path"])
    wheel = Path(site["a7"]["python_flint_wheel"]["path"])
    return {
        "accepted": False,
        "artifact": _artifact_identity(artifact),
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": "reviewed_a7_materialization_plan_not_execution_evidence",
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "python_path_if_supported": str(python_path) if python_path else None,
        "registered_invocation": factory.registered_invocation,
        "registered_invocation_hashes": local,
        "semantic_binding_enabled": group.get("semantic_binding") is not None,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "source_closure": source_rows,
        "upstreams": {
            "flint": _flint_identity(Path(site["a7"]["flint_source_root"])),
            "python_flint": _python_flint_identity(
                Path(site["a7"]["python_flint_source_root"])
            ),
            "runtime_wheel": verify_wheel(wheel, load_python_flint_pin()),
        },
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    runtime_inputs = {
        key: site["a7"][key]
        for key in (
            "flint_source_root",
            "python_flint_source_root",
            "python_flint_wheel",
        )
    }
    try:
        records, build_steps, runtime = _build_python_flint_runtime_closure(
            context,
            runtime_inputs,
            artifact_root,
            source_paths=SOURCE_PATHS,
            family="ch25-a7-boundary",
        )
    except PlattHeadMaterializerError as error:
        raise A7MaterializerError(str(error)) from error

    _artifact_pin, artifact_source = _pin(
        site["a7"]["artifact"], "retained A.7 artifact"
    )
    identity = _artifact_identity(artifact_source)
    artifact_target = artifact_root / "artifacts/a7_boundary.json"
    _copy_exact(artifact_source, artifact_target)
    if _artifact_identity(artifact_target) != identity:
        raise A7MaterializerError("copied A.7 artifact differs")
    records.append(
        _artifact_record(
            artifact_target,
            artifact_root,
            role="reviewed_retained_a7_boundary_transcript",
            statement_role=None,
            executable=False,
        )
    )
    base_source = next(
        (row for row in records if row["statement_role"] == "source_tree"), None
    )
    if base_source is None:
        raise A7MaterializerError("python-flint closure lacks its source-tree manifest")
    base_source["statement_role"] = None
    envelope = {
        "a7_artifact": {
            **_file_pin(artifact_target),
            "leaf_count": identity["leaf_count"],
            "path": artifact_target.relative_to(artifact_root).as_posix(),
        },
        "kind": "sparkinterval.ch25-a7-boundary-source-envelope.v1",
        "python_flint_source_closure": {
            "path": base_source["path"],
            "sha256": base_source["sha256"],
            "size_bytes": base_source["size_bytes"],
        },
        "schema_version": 1,
    }
    envelope_path = artifact_root / "source/a7-source-envelope.json"
    _write_bytes(envelope_path, cpu_operator.canonical_json_bytes(envelope))
    records.append(
        _artifact_record(
            envelope_path,
            artifact_root,
            role="reviewed_a7_source_envelope",
            statement_role="source_tree",
            executable=False,
        )
    )
    records.sort(key=lambda row: row["path"])
    build_steps.append(
        {
            "artifact_sha256": identity["sha256"],
            "kind": "retained_a7_structural_review",
            "leaf_count": identity["leaf_count"],
        }
    )
    return records, build_steps, runtime


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: A7CPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    site: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = artifact_root / "input/registered-invocation.json"
    _write_bytes(input_path, factory.input_bytes)
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    expected = registered_invocation_expected(factory.registered_invocation)
    local = expected_registered_hashes()
    if (
        registered_invocation_backend(factory.registered_invocation)
        != cpu_operator.BACKEND
        or expected
        != {
            **local,
            "result": "true",
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    ):
        raise A7MaterializerError("closed A.7 factory differs from the Lean invocation")
    records.sort(key=lambda row: row["path"])
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": local["algorithm_hash"],
        },
        "artifact_closure": {
            "closure_kind": "content_addressed_image_source_reviewed_v1",
            "files": records,
            "manifest_sha256": canonical_sha256(_closure_manifest(records)),
        },
        "backend": cpu_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv),
            "cwd": ".",
            "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "timeout_seconds": factory.timeout_seconds,
        },
        "domain_coverage": {
            "canonical_sha256": local["domain_hash"],
            "value": factory.domain,
        },
        "gpu_pre_run_gate": None,
        "input_artifact": {
            "path": input_path.relative_to(artifact_root).as_posix(),
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": local["input_hash"],
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": "tg-ch25-a7-boundary-cpu-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": "output/registered-result.txt",
        },
        "parameters": {
            "canonical_sha256": local["parameters_hash"],
            "value": factory.parameters,
        },
        "runner_policy": runner_policy,
        "schema_version": 1,
        "target_profile": profiles["target"],
        "tpm_policy": {
            "ak_handle": "0x81000003",
            "bank": "sha256",
            "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": profiles["trust"],
        "work_trace_contract": {
            "expected_iterations": factory.trace_iterations,
            "format": "challenge_sha256_chain_json_v1",
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": TRACE_DEFINITION,
            "trace_algorithm_sha256": hashlib.sha256(
                TRACE_DEFINITION.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(factory.trace_verifier_argv),
        },
    }
    validate_job_spec(job)
    return job


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(context, group_id, shard_index, site)
    if not plan["build_host_supported"]:
        raise A7MaterializerError(
            "this host cannot build the x86_64 A.7 production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise A7MaterializerError("reviewed A.7 factory disappeared")
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.a7-materializing-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, runtime = _build_runtime_closure(
            context, site, artifact_root
        )
        job = _job(context, factory, artifact_root, records, site)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        transcript_policy = _transcript_policy(
            site["base"], record_hash(job_path), job
        )
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise A7MaterializerError("materializer output_root appeared during build")
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site=site["base"],
            factory=factory,
            challenge=challenge,
            challenge_path=challenge_path,
            artifact_root=artifact_root,
            package=package,
            transcript_policy_path=transcript_path,
        )
        config_path = output_root / "cpu-campaign.json"
        _write_bytes(config_path, cpu_operator.canonical_json_bytes(config))
        _validated, config_hash = cpu_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "artifact": plan["artifact"],
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_a7_operator_validated_materialization_not_execution_evidence"
            ),
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "portfolio_shard_config": _file_pin(shard_path),
            "registered_invocation": factory.registered_invocation,
            "runtime": runtime,
            "schema_version": SCHEMA_VERSION,
            "semantic_binding_enabled": group.get("semantic_binding") is not None,
            "source_run_receipt_produced": False,
            "transcript_policy": _file_pin(transcript_path),
        }
        manifest_path = output_root / "materialization-manifest.json"
        _write_bytes(manifest_path, cpu_operator.canonical_json_bytes(manifest))
        complete = True
        return {
            **manifest,
            "cpu_operator_config": {
                **manifest["cpu_operator_config"],
                "path": str(config_path),
            },
            "job_spec": {**manifest["job_spec"], "path": str(job_path)},
            "manifest": str(manifest_path),
            "package": {**manifest["package"], "path": str(package)},
        }
    except (
        ArchiveError,
        CampaignIOError,
        CommonMaterializerError,
        PlattHeadMaterializerError,
        PythonFlintRuntimeError,
        OSError,
        ValueError,
    ) as error:
        raise A7MaterializerError(f"A.7 materialization failed closed: {error}") from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "A7_FACTORY",
    "A7MaterializerError",
    "MANIFEST_KIND",
    "SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
