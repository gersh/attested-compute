# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the source-closed Dirichlet FLINT fallback for Azure SEV-SNP.

The package binds the exact portfolio handoff, registered Lean invocation,
reviewed project sources, pinned FLINT and python-flint source trees, reviewed
x86-64 wheel, and a complete retained q=1 PT21 campaign archive.  Publication
is atomic and remains explicitly distinct from execution evidence.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_dirichlet_workload_factory import (
    DIRICHLET_FACTORY,
    DIRICHLET_POSTCHECK_FACTORY,
    PREDECESSOR_CERTIFICATE_PATH,
    PREDECESSOR_RECEIPT_PATH,
    Q1_ARCHIVE_PATH,
    Q1_RECEIPT_PATH,
    SOURCE_PATHS,
    DirichletCPUWorkloadFactory,
    DirichletPostcheckCPUWorkloadFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_platt_head_materializer import (
    FIXED_TOOL_PATH,
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
    ReceiptError,
    load_verified_receipt,
    registered_invocation_backend,
    registered_invocation_expected,
    require_production_verifier,
    validate_registered_invocation,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.dirichlet-materializer-site.v1"
POSTCHECK_SITE_KIND = (
    "sparkinterval.azure.cpu.dirichlet-postcheck-materializer-site.v1"
)
MANIFEST_KIND = "sparkinterval.azure.cpu.dirichlet-materialization.v1"
SITE_FIELDS = {"base_site", "dirichlet", "kind", "schema_version"}
POSTCHECK_SITE_FIELDS = {
    "base_site", "dirichlet_postcheck", "kind", "schema_version"
}
DIRICHLET_FIELDS = {
    "flint_source_root",
    "platt_trudgian_campaign_archive",
    "platt_trudgian_trusted_receipt",
    "python_flint_source_root",
    "python_flint_wheel",
}
DIRICHLET_POSTCHECK_FIELDS = {
    "flint_source_root",
    "predecessor_certificate_archive",
    "predecessor_trusted_receipt",
    "python_flint_source_root",
    "python_flint_wheel",
}
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.platt-dirichlet-fallback.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || q1-campaign-archive-sha256 || q1-production-receipt-sha256)\n"
    "step-1=SHA256(step-domain || previous || retained-q2-archive-sha256 || retained-q2-tree-sha256)\n"
    "step-2=SHA256(step-domain || previous || source-composition-sha256)\n"
    "step-3=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-python-flint-replays-q1-and-every-q2-checker-before-true"
)
POSTCHECK_TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.platt-dirichlet-postcheck.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || predecessor-certificate-sha256 || predecessor-receipt-file-sha256 || predecessor-receipt-sha256)\n"
    "step-1=SHA256(step-domain || previous || predecessor-statement-sha256 || predecessor-source-trace-sha256 || q1-campaign-archive-sha256 || q1-production-receipt-sha256)\n"
    "step-2=SHA256(step-domain || previous || retained-q2-archive-sha256 || retained-q2-tree-sha256 || source-composition-sha256)\n"
    "step-3=SHA256(step-domain || previous || result-sha256)\n"
    "verification=production-receipt-authenticates-bundle-and-source-trace-then-pinned-python-flint-replays-q1-and-every-q2-checker-before-true"
)


class DirichletMaterializerError(RuntimeError):
    """A handoff, dependency, source closure, or emitted job failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise DirichletMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise DirichletMaterializerError(f"{what} must be a non-symlink directory")
    return path


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise DirichletMaterializerError(
            f"cannot load canonical Dirichlet materializer site: {error}"
        ) from error
    if not isinstance(value, dict):
        raise DirichletMaterializerError(
            "Dirichlet materializer site is not an object"
        )
    kind = value.get("kind")
    if kind == SITE_KIND:
        site = _exact(value, SITE_FIELDS, "Dirichlet materializer site")
        input_key = "dirichlet"
        input_fields = DIRICHLET_FIELDS
        stage_kind = "source"
    elif kind == POSTCHECK_SITE_KIND:
        site = _exact(
            value, POSTCHECK_SITE_FIELDS, "Dirichlet postcheck materializer site"
        )
        input_key = "dirichlet_postcheck"
        input_fields = DIRICHLET_POSTCHECK_FIELDS
        stage_kind = "postcheck"
    else:
        raise DirichletMaterializerError(
            "unsupported Dirichlet materializer site kind"
        )
    if site["schema_version"] != SCHEMA_VERSION:
        raise DirichletMaterializerError(
            "unsupported Dirichlet materializer site version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise DirichletMaterializerError(str(error)) from error
    inputs = _exact(site[input_key], input_fields, "Dirichlet inputs")
    flint = _directory(inputs["flint_source_root"], "FLINT source root")
    python_flint = _directory(
        inputs["python_flint_source_root"], "python-flint source root"
    )
    _wheel_pin, wheel = _pin(inputs["python_flint_wheel"], "python-flint wheel")
    if stage_kind == "source":
        _dependency_pin, _dependency = _pin(
            inputs["platt_trudgian_campaign_archive"],
            "complete q=1 PT21 campaign archive",
        )
        _receipt_pin, receipt_path = _pin(
            inputs["platt_trudgian_trusted_receipt"],
            "production q=1 PT21 trusted-compute receipt",
        )
        receipt_invocation = "plattTrudgianFiniteRHProductionV1"
    else:
        _dependency_pin, _dependency = _pin(
            inputs["predecessor_certificate_archive"],
            "returned Dirichlet source certificate archive",
        )
        _receipt_pin, receipt_path = _pin(
            inputs["predecessor_trusted_receipt"],
            "production Dirichlet source trusted-compute receipt",
        )
        receipt_invocation = "plattDirichletTheorem71ProductionV1"
    try:
        _flint_identity(flint)
        _python_flint_identity(python_flint)
        verify_wheel(wheel, load_python_flint_pin())
        key_manifest = REPOSITORY_ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
        receipt = load_verified_receipt(
            receipt_path,
            key_manifest=key_manifest,
            allow_development_key=False,
        )
        require_production_verifier(receipt, key_manifest)
        validate_registered_invocation(receipt, receipt_invocation)
        if receipt["claim"]["result"] != "true":
            raise ReceiptError("Dirichlet dependency receipt is not literal true")
    except (
        PlattHeadMaterializerError,
        PythonFlintRuntimeError,
        ReceiptError,
    ) as error:
        raise DirichletMaterializerError(str(error)) from error
    return {
        "base": base,
        "dirichlet": inputs,
        "site_pin": _file_pin(path),
        "stage_kind": stage_kind,
    }


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
        raise DirichletMaterializerError(
            "portfolio group has no closed Dirichlet CPU fallback factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise DirichletMaterializerError(
            "portfolio shard argv differs from the closed Dirichlet factory"
        )
    is_postcheck = isinstance(factory, DirichletPostcheckCPUWorkloadFactory)
    expected_stage_kind = "postcheck" if is_postcheck else "source"
    if site.get("stage_kind") != expected_stage_kind:
        raise DirichletMaterializerError(
            f"{expected_stage_kind} group requires its matching materializer site"
        )
    registered = registered_invocation_expected(factory.registered_invocation)
    if registered_invocation_backend(factory.registered_invocation) != cpu_operator.BACKEND:
        raise DirichletMaterializerError(
            "Dirichlet invocation is not registered for the CPU backend"
        )
    local = expected_registered_hashes()
    for key, value in local.items():
        if registered.get(key) != value:
            raise DirichletMaterializerError(
                f"registered Dirichlet {key} differs from the closed factory"
            )
    if registered.get("result") != "true":
        raise DirichletMaterializerError(
            "registered Dirichlet result is not literal true"
        )
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
        raise DirichletMaterializerError(
            "challenge TTL cannot contain the Dirichlet timeout and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise DirichletMaterializerError(
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
    inputs = site["dirichlet"]
    dependency_rows: dict[str, Any]
    if is_postcheck:
        _certificate_pin, certificate = _pin(
            inputs["predecessor_certificate_archive"],
            "returned Dirichlet source certificate archive",
        )
        _receipt_pin, source_receipt = _pin(
            inputs["predecessor_trusted_receipt"],
            "production Dirichlet source trusted-compute receipt",
        )
        dependency_rows = {
            "predecessor_certificate": _file_pin(certificate),
            "predecessor_trusted_receipt": _file_pin(source_receipt),
        }
    else:
        _q1_pin, q1_archive = _pin(
            inputs["platt_trudgian_campaign_archive"],
            "complete q=1 PT21 campaign archive",
        )
        _receipt_pin, q1_receipt = _pin(
            inputs["platt_trudgian_trusted_receipt"],
            "production q=1 PT21 trusted-compute receipt",
        )
        dependency_rows = {
            "q1_dependency": _file_pin(q1_archive),
            "q1_trusted_receipt": _file_pin(q1_receipt),
        }
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": (
            "reviewed_dirichlet_retained_postcheck_materialization_plan_not_execution_evidence"
            if is_postcheck
            else "reviewed_dirichlet_fallback_materialization_plan_not_execution_evidence"
        ),
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "python_path_if_supported": str(python_path) if python_path else None,
        **dependency_rows,
        "registered_invocation": factory.registered_invocation,
        "registered_invocation_hashes": local,
        "semantic_binding_enabled": group.get("semantic_binding") is not None,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "stage_kind": expected_stage_kind,
        "source_closure": source_rows,
        "source_scale_feasibility": {
            "azure_timeout_seconds": factory.timeout_seconds,
            "expected_to_complete_with_raw_contour_fallback": False,
            "optimized_platt_pipeline_selected": False,
        },
        "upstreams": {
            "flint": _flint_identity(Path(inputs["flint_source_root"])),
            "python_flint": _python_flint_identity(
                Path(inputs["python_flint_source_root"])
            ),
            "runtime_wheel": verify_wheel(
                Path(inputs["python_flint_wheel"]["path"]),
                load_python_flint_pin(),
            ),
        },
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
    factory: DirichletCPUWorkloadFactory = DIRICHLET_FACTORY,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        records, build_steps, runtime = _build_python_flint_runtime_closure(
            context,
            site["dirichlet"],
            artifact_root,
            source_paths=SOURCE_PATHS,
            family="platt-dirichlet",
        )
    except PlattHeadMaterializerError as error:
        raise DirichletMaterializerError(str(error)) from error
    is_postcheck = isinstance(factory, DirichletPostcheckCPUWorkloadFactory)
    if is_postcheck:
        _dependency_pin, dependency_source = _pin(
            site["dirichlet"]["predecessor_certificate_archive"],
            "returned Dirichlet source certificate archive",
        )
        dependency_target = artifact_root / PREDECESSOR_CERTIFICATE_PATH
        dependency_role = "authenticated_dirichlet_source_certificate_archive"
        _receipt_pin, receipt_source = _pin(
            site["dirichlet"]["predecessor_trusted_receipt"],
            "production Dirichlet source trusted-compute receipt",
        )
        receipt_target = artifact_root / PREDECESSOR_RECEIPT_PATH
        receipt_role = "production_dirichlet_source_trusted_compute_receipt"
        build_kind = "pinned_authenticated_dirichlet_source_certificate"
    else:
        _dependency_pin, dependency_source = _pin(
            site["dirichlet"]["platt_trudgian_campaign_archive"],
            "complete q=1 PT21 campaign archive",
        )
        dependency_target = artifact_root / Q1_ARCHIVE_PATH
        dependency_role = "complete_platt_trudgian_q1_campaign_dependency"
        _receipt_pin, receipt_source = _pin(
            site["dirichlet"]["platt_trudgian_trusted_receipt"],
            "production q=1 PT21 trusted-compute receipt",
        )
        receipt_target = artifact_root / Q1_RECEIPT_PATH
        receipt_role = "production_platt_trudgian_q1_trusted_compute_receipt"
        build_kind = "pinned_complete_q1_campaign_archive"
    _copy_exact(dependency_source, dependency_target)
    _copy_exact(receipt_source, receipt_target)
    records.append(
        _artifact_record(
            dependency_target,
            artifact_root,
            role=dependency_role,
            statement_role=None,
            executable=False,
        )
    )
    records.append(
        _artifact_record(
            receipt_target,
            artifact_root,
            role=receipt_role,
            statement_role=None,
            executable=False,
        )
    )
    records.sort(key=lambda row: row["path"])
    build_steps.append(
        {
            "kind": build_kind,
            "sha256": _file_pin(dependency_target)["sha256"],
            "size_bytes": _file_pin(dependency_target)["size_bytes"],
            "trusted_receipt_sha256": _file_pin(receipt_target)["sha256"],
        }
    )
    return records, build_steps, runtime


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: DirichletCPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    site: Mapping[str, Any],
) -> dict[str, Any]:
    is_postcheck = isinstance(factory, DirichletPostcheckCPUWorkloadFactory)
    trace_definition = (
        POSTCHECK_TRACE_DEFINITION if is_postcheck else TRACE_DEFINITION
    )
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
        raise DirichletMaterializerError(
            "closed Dirichlet factory differs from the Lean invocation"
        )
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
        "job_id": (
            "tg-platt-dirichlet-theorem-7-1-retained-postcheck-v1"
            if is_postcheck
            else "tg-platt-dirichlet-theorem-7-1-cpu-fallback-v1"
        ),
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
            "trace_algorithm_definition": trace_definition,
            "trace_algorithm_sha256": hashlib.sha256(
                trace_definition.encode("utf-8")
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
        raise DirichletMaterializerError(
            "this host cannot build the x86_64 Dirichlet production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise DirichletMaterializerError("reviewed Dirichlet factory disappeared")
    is_postcheck = isinstance(factory, DirichletPostcheckCPUWorkloadFactory)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.dirichlet-materializing-",
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
            context, site, artifact_root, factory
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
            raise DirichletMaterializerError(
                "materializer output_root appeared during build"
            )
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
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_dirichlet_retained_postcheck_operator_validated_"
                "materialization_not_execution_evidence"
                if is_postcheck
                else
                "source_reviewed_dirichlet_fallback_operator_validated_"
                "materialization_not_execution_evidence"
            ),
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "optimized_platt_pipeline_selected": False,
            "package": _file_pin(package),
            "portfolio_shard_config": _file_pin(shard_path),
            "raw_fallback_expected_to_finish_within_timeout": False,
            "registered_invocation": factory.registered_invocation,
            "runtime": runtime,
            "schema_version": SCHEMA_VERSION,
            "semantic_binding_enabled": group.get("semantic_binding") is not None,
            "source_run_receipt_produced": False,
            "stage_kind": "postcheck" if is_postcheck else "source",
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
        raise DirichletMaterializerError(
            f"Dirichlet materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "DIRICHLET_FACTORY",
    "DIRICHLET_POSTCHECK_FACTORY",
    "DirichletMaterializerError",
    "MANIFEST_KIND",
    "SITE_KIND",
    "POSTCHECK_SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
