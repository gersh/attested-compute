# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the closed historical Helfgott--Platt CPU terminal."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_goldbach_historical_workload_factory import (
    SOURCE_PATHS,
    TRACE_DEFINITION,
    HistoricalGoldbachTerminalFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_platt_head_materializer import (
    _profile_and_policy_records,
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
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.goldbach_build_admission import (
    GoldbachBuildAdmission,
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from tg_verifier.goldbach_historical_terminal import (
    HistoricalGoldbachTerminalError,
    load_child_identity_commitment,
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
    load_key_manifest,
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import (  # noqa: E402
    _closure_manifest,
    canonical_sha256,
    validate_job_spec,
)


SCHEMA_VERSION = 1
SITE_KIND = (
    "sparkinterval.azure.cpu.helfgott-platt-goldbach-terminal-materializer-site.v1"
)
MANIFEST_KIND = (
    "sparkinterval.azure.cpu.helfgott-platt-goldbach-terminal-materialization.v1"
)
SITE_FIELDS = {"base_site", "historical_goldbach", "kind", "schema_version"}
INPUT_FIELDS = {
    "build_admission",
    "child_identity_commitment",
    "terminal_handoff",
}
FIXED_TOOL_PATH = "/usr/bin:/bin:/usr/local/bin"


class HistoricalGoldbachMaterializerError(RuntimeError):
    """The terminal handoff, identity closure, or package failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise HistoricalGoldbachMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def load_site(
    path: Path, *, allow_test_admission: bool = False,
) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachMaterializerError(
            f"cannot load canonical historical Goldbach site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "historical Goldbach materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise HistoricalGoldbachMaterializerError(
            "unsupported historical Goldbach site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise HistoricalGoldbachMaterializerError(str(error)) from error
    inputs = _exact(
        site["historical_goldbach"],
        INPUT_FIELDS,
        "historical Goldbach terminal inputs",
    )
    admission_pin, admission_path = _pin(
        inputs["build_admission"], "Goldbach build admission"
    )
    handoff_pin, handoff_path = _pin(
        inputs["terminal_handoff"], "historical Goldbach terminal handoff"
    )
    commitment_pin, commitment_path = _pin(
        inputs["child_identity_commitment"],
        "historical Goldbach child identity commitment",
    )
    try:
        admission = load_build_admission(
            admission_path, allow_test_fixture=allow_test_admission
        )
        commitment, commitment_sha256 = load_child_identity_commitment(
            commitment_path, expected_sha256=commitment_pin["sha256"]
        )
    except (GoldbachBuildAdmissionError, HistoricalGoldbachTerminalError) as error:
        raise HistoricalGoldbachMaterializerError(str(error)) from error
    if admission_pin["sha256"] != admission.admission_sha256:
        raise HistoricalGoldbachMaterializerError(
            "build admission pin differs from its canonical identity"
        )
    return {
        "admission": admission,
        "admission_path": admission_path,
        "base": base,
        "commitment": commitment,
        "commitment_path": commitment_path,
        "commitment_sha256": commitment_sha256,
        "handoff_path": handoff_path,
        "handoff_pin": handoff_pin,
        "site_pin": _file_pin(path),
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
        raise HistoricalGoldbachMaterializerError(
            "portfolio group has no closed historical Goldbach terminal factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise HistoricalGoldbachMaterializerError(
            "portfolio shard argv differs from the terminal factory"
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
        raise HistoricalGoldbachMaterializerError(
            "registered historical Goldbach identity differs from the factory"
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
        raise HistoricalGoldbachMaterializerError(
            "challenge TTL cannot contain terminal replay and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise HistoricalGoldbachMaterializerError(
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
    return {
        "accepted": False,
        "build_admission_sha256": site["admission"].admission_sha256,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "child_identity_commitment_sha256": site["commitment_sha256"],
        "classification": (
            "reviewed_historical_goldbach_terminal_materialization_plan_"
            "not_execution_evidence"
        ),
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
        "terminal_handoff": site["handoff_pin"],
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _copy_key_closure(
    context: azure_portfolio.PortfolioContext, artifact_root: Path,
) -> tuple[list[dict[str, Any]], str]:
    manifest_source = context.verifier_key_manifest.resolve(strict=True)
    keys = load_key_manifest(manifest_source)
    destination_root = artifact_root / "profiles/verifier-keys"
    destination = destination_root / "trusted_compute_keys.json"
    _copy_exact(manifest_source, destination)
    records = [
        _artifact_record(
            destination,
            artifact_root,
            role="child_receipt_verifier_key_manifest",
            statement_role=None,
            executable=False,
        )
    ]
    for entry in keys.values():
        relative = Path(entry["public_key_path"])
        source = (manifest_source.parent / relative).resolve(strict=True)
        try:
            source.relative_to(manifest_source.parent.resolve(strict=True))
        except ValueError as error:
            raise HistoricalGoldbachMaterializerError(
                "child verifier public key escapes its manifest"
            ) from error
        target = destination_root / relative
        _copy_exact(source, target)
        if _file_pin(target)["sha256"] != entry["public_key_sha256"]:
            raise HistoricalGoldbachMaterializerError(
                "copied child verifier public key differs"
            )
        records.append(
            _artifact_record(
                target,
                artifact_root,
                role="child_receipt_verifier_public_key",
                statement_role=None,
                executable=False,
            )
        )
    return records, _file_pin(destination)["sha256"]


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    python = shutil.which("python3", path=FIXED_TOOL_PATH)
    if platform.machine() != "x86_64" or python is None:
        raise HistoricalGoldbachMaterializerError(
            "terminal closure requires x86_64 and fixed-path CPython"
        )
    python_source = Path(python).resolve(strict=True)
    python_target = artifact_root / "artifacts/python3"
    _copy_exact(python_source, python_target, executable=True)
    version = subprocess.run(
        [str(python_target), "-I", "--version"],
        env={"LANG": "C", "LC_ALL": "C", "PATH": FIXED_TOOL_PATH, "TZ": "UTC"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    version_raw = version.stdout or version.stderr
    if version.returncode != 0 or not version_raw.startswith(b"Python 3."):
        raise HistoricalGoldbachMaterializerError(
            "copied CPython failed isolated version check"
        )

    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        if hash_file_once(destination) != (row["sha256"], row["size_bytes"]):
            raise HistoricalGoldbachMaterializerError(
                f"project source changed during copy: {relative}"
            )
        copied[relative] = destination

    admission_target = artifact_root / "source/goldbach-build-admission.json"
    _copy_exact(site["admission_path"], admission_target)
    if hash_file_once(admission_target) != (
        site["admission"].admission_sha256,
        site["admission"].admission_size_bytes,
    ):
        raise HistoricalGoldbachMaterializerError(
            "copied build admission differs"
        )
    commitment_target = (
        artifact_root / "source/historical-goldbach-child-commitment.json"
    )
    _copy_exact(site["commitment_path"], commitment_target)
    if hash_file_once(commitment_target)[0] != site["commitment_sha256"]:
        raise HistoricalGoldbachMaterializerError(
            "copied child commitment differs"
        )
    handoff_target = (
        artifact_root / "input/historical-goldbach-terminal-handoff.tar"
    )
    _copy_exact(site["handoff_path"], handoff_target)
    if hash_file_once(handoff_target) != (
        site["handoff_pin"]["sha256"],
        site["handoff_pin"]["size_bytes"],
    ):
        raise HistoricalGoldbachMaterializerError(
            "copied terminal handoff differs"
        )
    key_records, key_manifest_sha256 = _copy_key_closure(
        context, artifact_root
    )
    runtime = {
        "child_verifier_key_manifest_sha256": key_manifest_sha256,
        "dynamic_runtime_boundary": (
            "copied CPython plus immutable Azure image loader, libc, stdlib, "
            "and openssl"
        ),
        "kind": (
            "sparkinterval.helfgott-platt-goldbach-terminal-runtime-closure.v1"
        ),
        "python_executable": {
            **_file_pin(python_target),
            "path": "artifacts/python3",
        },
        "python_version": version_raw.decode("ascii", "strict").strip(),
        "schema_version": 1,
    }
    runtime_path = artifact_root / "source/runtime-closure.json"
    _write_bytes(runtime_path, cpu_operator.canonical_json_bytes(runtime))
    source_manifest = {
        "build_admission_sha256": site["admission"].admission_sha256,
        "child_identity_commitment_sha256": site["commitment_sha256"],
        "kind": (
            "sparkinterval.helfgott-platt-goldbach-terminal-source-closure.v1"
        ),
        "project_files": [
            {
                "path": relative,
                "sha256": _file_pin(path)["sha256"],
                "size_bytes": path.stat().st_size,
            }
            for relative, path in sorted(copied.items())
        ],
        "runtime_closure_sha256": _file_pin(runtime_path)["sha256"],
        "schema_version": 1,
        "terminal_handoff_sha256": site["handoff_pin"]["sha256"],
    }
    source_path = artifact_root / "source/source-closure.json"
    _write_bytes(source_path, cpu_operator.canonical_json_bytes(source_manifest))
    records = [
        _artifact_record(
            python_target,
            artifact_root,
            role="image_bound_cpython_host",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            admission_target,
            artifact_root,
            role="reviewed_goldbach_build_admission",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            commitment_target,
            artifact_root,
            role="historical_goldbach_child_identity_commitment",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            handoff_target,
            artifact_root,
            role="historical_goldbach_complete_branch_handoff",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            runtime_path,
            artifact_root,
            role="image_runtime_closure_manifest",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            source_path,
            artifact_root,
            role="reviewed_source_closure_manifest",
            statement_role="source_tree",
            executable=False,
        ),
        *key_records,
    ]
    for relative, path in sorted(copied.items()):
        records.append(
            _artifact_record(
                path,
                artifact_root,
                role="reviewed_project_source",
                statement_role=None,
                executable=relative.startswith("tools/"),
            )
        )
    records.sort(key=lambda row: row["path"])
    return records, runtime


def _one_hash(records: list[dict[str, Any]], field: str, value: str) -> str:
    matches = [record["sha256"] for record in records if record[field] == value]
    if len(matches) != 1:
        raise HistoricalGoldbachMaterializerError(
            f"terminal closure needs exactly one {field}={value}"
        )
    return matches[0]


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: HistoricalGoldbachTerminalFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    site: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = artifact_root / "input/registered-invocation.json"
    _write_bytes(input_path, factory.input_bytes)
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    binding = {
        "build_admission_sha256": site["admission"].admission_sha256,
        "child_identity_commitment_sha256": site["commitment_sha256"],
        "child_verifier_key_manifest_sha256": _one_hash(
            records, "role", "child_receipt_verifier_key_manifest"
        ),
        "kind": (
            "sparkinterval.helfgott-platt-goldbach-terminal-"
            "post-child-run-binding.v1"
        ),
        "runner_policy_sha256": runner_policy["sha256"],
        "runtime_closure_sha256": _one_hash(
            records, "role", "image_runtime_closure_manifest"
        ),
        "schema_version": 1,
        "source_manifest_sha256": _one_hash(
            records, "role", "reviewed_source_closure_manifest"
        ),
        "target_profile_sha256": profiles["target"]["sha256"],
        "terminal_handoff_sha256": site["handoff_pin"]["sha256"],
        "terminal_host_executable_sha256": _one_hash(
            records, "statement_role", "host_executable"
        ),
        "trust_profile_sha256": profiles["trust"]["sha256"],
    }
    binding_path = artifact_root / "source/terminal-execution-binding.json"
    _write_bytes(binding_path, canonical_json_bytes(binding))
    records.append(
        _artifact_record(
            binding_path,
            artifact_root,
            role="historical_goldbach_terminal_post_child_run_binding",
            statement_role=None,
            executable=False,
        )
    )
    local = expected_registered_hashes()
    expected = registered_invocation_expected(factory.registered_invocation)
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
        raise HistoricalGoldbachMaterializerError(
            "terminal factory differs from registered invocation"
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
        "job_id": "tg-helfgott-platt-historical-terminal-cpu-v1",
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
        raise HistoricalGoldbachMaterializerError(
            "this host cannot build the historical Goldbach terminal closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise HistoricalGoldbachMaterializerError(
            "reviewed historical Goldbach terminal factory disappeared"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.historical-goldbach-materializing-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, runtime = _build_runtime_closure(
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
            raise HistoricalGoldbachMaterializerError(
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
            "build_admission_sha256": site["admission"].admission_sha256,
            "challenge_pin": _file_pin(challenge_path),
            "child_identity_commitment_sha256": site["commitment_sha256"],
            "classification": (
                "source_reviewed_historical_goldbach_terminal_operator_"
                "validated_materialization_not_execution_evidence"
            ),
            "cpu_operator_config": {
                **_file_pin(config_path),
                "sha256": config_hash,
            },
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
            "terminal_handoff_sha256": site["handoff_pin"]["sha256"],
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
        GoldbachBuildAdmissionError,
        HistoricalGoldbachTerminalError,
        OSError,
        ValueError,
    ) as error:
        raise HistoricalGoldbachMaterializerError(
            f"historical Goldbach materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "HistoricalGoldbachMaterializerError",
    "load_site",
    "materialize",
    "plan_materialization",
]
