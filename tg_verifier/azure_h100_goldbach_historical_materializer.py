# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize one source-reviewed historical Goldbach Azure H100 group."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_h100_goldbach_historical_workload_factory import (
    PHASE_ID,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    HistoricalGoldbachH100WorkloadFactory,
    expected_execution_projection_sha256,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    _absolute,
    _artifact_record,
    _copy_exact,
    _file_pin,
    _load_handoff,
    _pin,
    _source_pin,
    _write_bytes,
    record_hash,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.goldbach_gpu_campaign import (
    PRODUCTION_ALGORITHM,
    PRODUCTION_EVEN_LIMIT,
    PRODUCTION_EVEN_START,
    load_plan,
    load_receipt as load_binary_receipt,
    production_group_leaf_indices,
    verify_executable,
    verify_hardened_source_tree,
)
from tg_verifier.goldbach_build_admission import (
    H100_BUILD_ARGV_TEMPLATE,
    H100_BUILD_ENVIRONMENT,
    GoldbachBuildAdmission,
    GoldbachBuildAdmissionError,
    goldbach_execution_projection_sha256,
    load_build_admission,
    verify_runtime_image_closure,
    verify_admitted_file,
    verify_admitted_pin,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (
    REPOSITORY_ROOT / "azure",
    REPOSITORY_ROOT / "attestation",
    REPOSITORY_ROOT / "tools",
):
    if str(directory) not in os.sys.path:
        os.sys.path.insert(0, str(directory))

import h100_production_orchestrator as h100_operator  # noqa: E402
from create_run_bundle import load_profile  # noqa: E402
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402
from tg_goldbach_historical_operational_azure_measured_workload import (  # noqa: E402
    _validate_cpu_result,
    _validate_h100_result,
    verify_retained_export_archive,
)


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.h100.helfgott-platt-goldbach-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.h100.helfgott-platt-goldbach-materialization.v1"
SITE_FIELDS = {
    "base_campaign", "build", "kind", "output_root", "schema_version",
}
BUILD_FIELDS = {
    "build_admission", "hardened_goldbach_source_root", "host_cxx", "nvcc",
    "plan_predecessor_export", "python",
}
H100_PROFILE_PATHS = {
    "target": "profiles/targets/azure_ncc40ads_h100_v5.json",
    "trust": "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json",
}
PLAN_GROUP = (
    "helfgott-platt-goldbach-gpu-v1::create-production-plan"
)
BUILD_ENVIRONMENT = H100_BUILD_ENVIRONMENT


class HistoricalGoldbachH100MaterializerError(RuntimeError):
    """A source, predecessor, build, or operator binding failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise HistoricalGoldbachH100MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise HistoricalGoldbachH100MaterializerError(
            f"{what} must be a non-symlink directory"
        )
    return path


def load_site(
    path: Path, *, allow_test_admission: bool = False,
) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"cannot load canonical H100 materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "H100 materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise HistoricalGoldbachH100MaterializerError(
            "unsupported H100 materializer site kind/version"
        )
    _template_pin, template_path = _pin(
        site["base_campaign"], "base H100 campaign template"
    )
    template = load_json(template_path, require_canonical=True)
    _exact(template, h100_operator.CONFIG_KEYS, "base H100 campaign template")
    if (
        template["kind"] != h100_operator.CONFIG_KIND
        or template["schema_version"] != 1
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "base H100 campaign template has the wrong kind/version"
        )
    build = _exact(site["build"], BUILD_FIELDS, "H100 build inputs")
    if (
        isinstance(build["build_admission"], Mapping)
        and build["build_admission"].get("status") == "unconfigured"
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "Goldbach production build admission is explicitly unconfigured"
        )
    admission_pin, admission_path = _pin(
        build["build_admission"], "Goldbach build admission"
    )
    try:
        admission = load_build_admission(
            admission_path,
            expected_sha256=admission_pin["sha256"],
            allow_test_fixture=allow_test_admission,
        )
    except GoldbachBuildAdmissionError as error:
        raise HistoricalGoldbachH100MaterializerError(str(error)) from error
    source = _directory(
        build["hardened_goldbach_source_root"], "hardened Goldbach source root"
    )
    if (
        verify_hardened_source_tree(source)
        != admission.core["source_identity_sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "hardened source differs from the build admission"
        )
    for field in ("host_cxx", "nvcc", "plan_predecessor_export", "python"):
        _pin(build[field], field)
    for field in ("host_cxx", "nvcc", "python"):
        try:
            verify_admitted_pin(admission, field, build[field])
        except GoldbachBuildAdmissionError as error:
            raise HistoricalGoldbachH100MaterializerError(str(error)) from error
    for field in ("host_cxx", "nvcc", "python"):
        path_value = Path(build[field]["path"])
        if not os.access(path_value, os.X_OK):
            raise HistoricalGoldbachH100MaterializerError(
                f"{field} is not executable"
            )
    output_root = _absolute(site["output_root"], "output_root", exists=False)
    try:
        output_root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise HistoricalGoldbachH100MaterializerError(
            "output_root must stay outside the repository"
        )
    runner = template["policies"]["runner"]
    nvidia = template["policies"]["nvidia"]
    deployment = admission.deployment
    image_reference = template["azure"]["image"]
    _runner_pin, runner_path = _pin(
        runner, "runner policy", policy=True
    )
    runner_value = load_json(runner_path, require_canonical=True)
    required_claims = (
        runner_value.get("required_claims")
        if isinstance(runner_value, dict)
        else None
    )
    if (
        image_reference != deployment["immutable_image_reference"]
        or hashlib.sha256(image_reference.encode("utf-8")).hexdigest()
        != deployment["immutable_image_reference_sha256"]
        or runner.get("policy_id") != deployment["runner_policy_id"]
        or runner.get("sha256") != deployment["runner_policy_sha256"]
        or nvidia.get("sha256") != deployment["nvidia_policy_sha256"]
        or template["worker"].get("gpu_verifier") != deployment["gpu_verifier"]
        or template["worker"].get("nras_url") != deployment["nras_url"]
        or not isinstance(runner_value, dict)
        or runner_value.get("classification") != "production"
        or runner_value.get("production_ready") is not True
        or runner_value.get("immutable_image_reference") != image_reference
        or runner_value.get("immutable_image_reference_sha256")
        != deployment["immutable_image_reference_sha256"]
        or not isinstance(required_claims, list)
        or "immutable_image_and_runtime_closure"
        not in required_claims
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "H100 template/runtime image deployment differs from the build admission"
        )
    return {
        "admission_path": admission_path,
        "build_admission": admission,
        "build": build,
        "output_root": output_root,
        "site_pin": _file_pin(path),
        "template": template,
    }


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists() or source.is_symlink() or not source.is_dir():
        raise HistoricalGoldbachH100MaterializerError("unsafe source-tree copy")
    destination.mkdir(mode=0o700, parents=True)
    for path in sorted(source.rglob("*")):
        target = destination / path.relative_to(source)
        if path.is_symlink():
            raise HistoricalGoldbachH100MaterializerError(
                "source tree contains a symlink"
            )
        if path.is_dir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        elif path.is_file():
            _copy_exact(path, target, executable=os.access(path, os.X_OK))
        else:
            raise HistoricalGoldbachH100MaterializerError(
                "source tree contains a special file"
            )


def _run_build(argv: list[str], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=BUILD_ENVIRONMENT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"closed CUDA build failed: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise HistoricalGoldbachH100MaterializerError(
            f"closed CUDA build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": BUILD_ENVIRONMENT,
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _tool_version(path: Path, what: str) -> str:
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            env=BUILD_ENVIRONMENT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"cannot query admitted {what} version: {error}"
        ) from error
    raw = completed.stdout or completed.stderr
    if (
        completed.returncode != 0
        or not raw
        or len(raw) > 64 * 1024
    ):
        raise HistoricalGoldbachH100MaterializerError(
            f"admitted {what} version query failed"
        )
    try:
        return raw.decode("utf-8", "strict").strip()
    except UnicodeDecodeError as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"admitted {what} version is not UTF-8"
        ) from error


def _plan_predecessor(
    context: azure_portfolio.PortfolioContext, site: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    state = azure_portfolio.load_state(context)
    paths = azure_portfolio._task_paths(context, PLAN_GROUP, 0)
    task_id = paths["task_id"].name
    record = state["records"].get(task_id)
    if record is None:
        raise HistoricalGoldbachH100MaterializerError(
            "source-height binary plan predecessor has no portfolio receipt"
        )
    azure_portfolio._validate_task_record(context, task_id, record)
    if record["stage"] != "verified_receipt_recorded":
        raise HistoricalGoldbachH100MaterializerError(
            "source-height binary plan predecessor is incomplete"
        )
    try:
        receipt = load_verified_receipt(
            paths["receipt"], key_manifest=context.verifier_key_manifest
        )
    except Exception as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"plan predecessor receipt failed verification: {error}"
        ) from error
    _export_pin, export = _pin(
        site["build"]["plan_predecessor_export"], "plan predecessor export"
    )
    result = _validate_cpu_result(
        receipt, "create-production-plan", 0, export
    )
    manifest = verify_retained_export_archive(
        export, "create-production-plan", 0
    )
    if result["retained_tree_sha256"] != manifest["tree_sha256"]:
        raise HistoricalGoldbachH100MaterializerError(
            "plan predecessor tree differs from its signed result"
        )
    return export, {
        "receipt_sha256": receipt["receipt_sha256"],
        "tree_sha256": manifest["tree_sha256"],
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
    factory = factory_for_portfolio_group(
        group, shard_index, site["build_admission"]
    )
    if factory is None or shard.get("argv") != list(factory.portfolio_argv):
        raise HistoricalGoldbachH100MaterializerError(
            "portfolio shard has no exact historical Goldbach H100 factory"
        )
    predecessor_export, predecessor = _plan_predecessor(context, site)
    for relative in (*SOURCE_PATHS, *H100_PROFILE_PATHS.values()):
        _source_pin(context, relative)
    issued = dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    expires = dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    ttl = int((expires - issued).total_seconds())
    if ttl <= (
        factory.timeout_seconds
        + 600
        + h100_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "challenge TTL cannot contain the H100 group, gate, and evidence margin"
        )
    output_root = Path(site["output_root"]) / f"group-{shard_index:08d}"
    if output_root.exists() or output_root.is_symlink():
        raise HistoricalGoldbachH100MaterializerError(
            "group materialization output already exists"
        )
    supported = platform.machine().lower() in ("x86_64", "amd64")
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": (
            "reviewed_historical-goldbach_h100_materialization_plan_not_execution_evidence"
        ),
        "build_admission_sha256": site[
            "build_admission"
        ].admission_sha256,
        "build_identity_sha256": site[
            "build_admission"
        ].build_identity_sha256,
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "plan_predecessor": {
            **predecessor,
            "export_sha256": _file_pin(predecessor_export)["sha256"],
        },
        "registered_invocation": None,
        "retained_export_relative_path": (
            f"bundle-root/work/goldbach-historical-h100-{shard_index:08d}/"
            f"goldbach-historical-h100-group-{shard_index:08d}.tar"
        ),
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
    }


def _extract_plan(export: Path, destination: Path) -> Any:
    temporary = Path(tempfile.mkdtemp(prefix=".historical-goldbach-h100-plan-"))
    try:
        extract_archive(export, temporary / "export")
        source = temporary / "export/payload/binary-plan.json"
        if not source.is_file() or source.is_symlink():
            raise HistoricalGoldbachH100MaterializerError(
                "plan predecessor omitted binary-plan.json"
            )
        _copy_exact(source, destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    plan = load_plan(destination)
    if (
        not plan.production
        or plan.algorithm != PRODUCTION_ALGORITHM
        or (plan.even_start, plan.even_limit)
        != (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT)
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "predecessor plan is not the exact source-height profile"
        )
    return plan


def _runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    factory: HistoricalGoldbachH100WorkloadFactory,
    artifact_root: Path,
    predecessor_export: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    admission: GoldbachBuildAdmission = site["build_admission"]
    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        if hash_file_once(destination) != (row["sha256"], row["size_bytes"]):
            raise HistoricalGoldbachH100MaterializerError(
                f"project source changed during copy: {relative}"
            )
        copied[relative] = destination

    source = Path(site["build"]["hardened_goldbach_source_root"]).resolve(strict=True)
    source_identity = verify_hardened_source_tree(source)
    if source_identity != admission.core["source_identity_sha256"]:
        raise HistoricalGoldbachH100MaterializerError(
            "materialized source differs from the build admission"
        )
    source_copy = artifact_root / "source/goldbach-gpu-hardened"
    _copy_tree(source, source_copy)
    if verify_hardened_source_tree(source_copy) != source_identity:
        raise HistoricalGoldbachH100MaterializerError("copied hardened source differs")

    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    _python_pin, python_source = _pin(site["build"]["python"], "python")
    verify_admitted_file(admission, "python", python_source)
    python_target = artifacts / "python3"
    _copy_exact(python_source, python_target, executable=True)
    verify_admitted_file(admission, "python", python_target)
    plan_path = artifact_root / "plans/binary-plan.json"
    plan_path.parent.mkdir(mode=0o700)
    plan = _extract_plan(predecessor_export, plan_path)
    if plan.executable_sha256 != admission.core["executable"]["sha256"]:
        raise HistoricalGoldbachH100MaterializerError(
            "source-height binary plan does not bind the admitted executable"
        )

    _nvcc_pin, nvcc = _pin(site["build"]["nvcc"], "nvcc")
    _cxx_pin, cxx = _pin(site["build"]["host_cxx"], "host C++ compiler")
    verify_admitted_file(admission, "nvcc", nvcc)
    verify_admitted_file(admission, "host_cxx", cxx)
    for role, path in (("python", python_target), ("nvcc", nvcc), ("host_cxx", cxx)):
        if _tool_version(path, role) != admission.core[role]["version"]:
            raise HistoricalGoldbachH100MaterializerError(
                f"{role} version differs from the build admission"
            )
    executable = artifacts / "goldbach-gpu"
    prefix = artifact_root.resolve().as_posix()
    replacements = {
        "nvcc": str(nvcc),
        "host-cxx": str(cxx),
        "source/goldbach-gpu-hardened/include": str(source_copy / "include"),
        "source/goldbach-gpu-hardened/src/goldbach.cu": str(
            source_copy / "src/goldbach.cu"
        ),
        "source/goldbach-gpu-hardened/src/prime_bitset.cpp": str(
            source_copy / "src/prime_bitset.cpp"
        ),
        "source/goldbach-gpu-hardened/src/segmented_sieve.cpp": str(
            source_copy / "src/segmented_sieve.cpp"
        ),
        "artifacts/goldbach-gpu": str(executable),
    }
    compile_argv = [
        replacements.get(token, token.replace("<artifact-root>", prefix))
        for token in H100_BUILD_ARGV_TEMPLATE
    ]
    build_steps = [_run_build(compile_argv, artifact_root)]
    executable.chmod(0o500)
    header = executable.read_bytes()[:20]
    if (
        len(header) != 20
        or header[:4] != b"\x7fELF"
        or header[5] != 1
        or int.from_bytes(header[18:20], "little") != 62
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "built GoldbachGPU executable is not x86_64 ELF"
        )
    verify_executable(executable, admission.core["executable"]["sha256"])
    verify_admitted_file(admission, "executable", executable)

    template = site["template"]
    _nvidia_pin, nvidia_source = _pin(
        template["policies"]["nvidia"], "NVIDIA policy", policy=True
    )
    if _nvidia_pin["sha256"] != admission.deployment["nvidia_policy_sha256"]:
        raise HistoricalGoldbachH100MaterializerError(
            "NVIDIA policy differs from the build admission"
        )
    nvidia_target = artifact_root / "profiles/nvidia-gpu.rego"
    _copy_exact(nvidia_source, nvidia_target)

    runtime_identity_path = artifact_root / "source/goldbach-build-identity.json"
    _write_bytes(
        runtime_identity_path, canonical_json_bytes(admission.runtime_identity())
    )
    runtime_image_path = (
        artifact_root / "source/goldbach-runtime-image-closure.json"
    )
    runtime_image_value = admission.runtime_image_closure()
    verify_runtime_image_closure(
        runtime_image_value,
        admission.deployment["runtime_image_closure_sha256"],
    )
    _write_bytes(runtime_image_path, canonical_json_bytes(runtime_image_value))
    if (
        hash_file_once(runtime_image_path)[0]
        != admission.deployment["runtime_image_closure_sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "runtime image closure differs from the build admission"
        )
    source_manifest = {
        "build_argv_sha256": admission.core["build_argv_sha256"],
        "build_identity_sha256": admission.build_identity_sha256,
        "goldbach_executable": {
            **_file_pin(executable), "path": "artifacts/goldbach-gpu",
        },
        "hardened_source_identity_sha256": source_identity,
        "host_cxx": admission.core["host_cxx"],
        "kind": "sparkinterval.historical-goldbach-h100-source-closure.v1",
        "nvcc": admission.core["nvcc"],
        "plan_sha256": plan.plan_sha256,
        "python": admission.core["python"],
        "runtime_image_closure_sha256": admission.deployment[
            "runtime_image_closure_sha256"
        ],
        "project_files": [
            {
                "path": relative,
                "sha256": _file_pin(path)["sha256"],
                "size_bytes": path.stat().st_size,
            }
            for relative, path in sorted(copied.items())
        ],
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(source_manifest_path, canonical_json_bytes(source_manifest))
    if (
        hash_file_once(source_manifest_path)[0]
        != admission.expected_artifacts["source_tree_hash"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "source manifest differs from the reviewed build admission"
        )

    records = [
        _artifact_record(
            python_target, artifact_root, role="image_bound_cpython_host_and_h100_gate",
            statement_role="host_executable", executable=True,
        ),
        _artifact_record(
            executable, artifact_root, role="hardened_sm90_goldbach_producer",
            statement_role="gpu_executable", executable=True,
        ),
        _artifact_record(
            plan_path, artifact_root, role="signed_predecessor_source_height_binary_plan",
            statement_role="execution_plan", executable=False,
        ),
        _artifact_record(
            nvidia_target, artifact_root, role="nvidia_pre_run_appraisal_policy",
            statement_role="gpu_attestation_policy", executable=False,
        ),
        _artifact_record(
            source_manifest_path, artifact_root, role="reviewed_source_closure_manifest",
            statement_role="source_tree", executable=False,
        ),
        _artifact_record(
            runtime_identity_path,
            artifact_root,
            role="reviewed_goldbach_build_identity",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            runtime_image_path,
            artifact_root,
            role="reviewed_dynamic_runtime_and_immutable_image_closure",
            statement_role=None,
            executable=False,
        ),
    ]
    for relative, path in sorted(copied.items()):
        records.append(
            _artifact_record(
                path, artifact_root, role="reviewed_project_source",
                statement_role=None, executable=relative.startswith("tools/"),
            )
        )
    for path in sorted(item for item in source_copy.rglob("*") if item.is_file()):
        records.append(
            _artifact_record(
                path, artifact_root, role="reviewed_hardened_goldbach_source",
                statement_role=None, executable=False,
            )
        )
    records.sort(key=lambda row: row["path"])
    return records, build_steps, source_manifest


def _profiles_and_runner(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    admission: GoldbachBuildAdmission = site["build_admission"]
    profiles: dict[str, dict[str, Any]] = {}
    for kind, relative in H100_PROFILE_PATHS.items():
        _row, source = _source_pin(context, relative)
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        value = load_profile(destination, kind)
        profiles[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": value["profile_id"],
            "sha256": canonical_sha256(value),
        }
        admitted_id = admission.deployment[f"{kind}_profile_id"]
        admitted_sha256 = admission.deployment[f"{kind}_profile_sha256"]
        if (
            profiles[kind]["profile_id"] != admitted_id
            or profiles[kind]["sha256"] != admitted_sha256
        ):
            raise HistoricalGoldbachH100MaterializerError(
                f"{kind} profile differs from the build admission"
            )
    runner_pin, runner_source = _pin(
        site["template"]["policies"]["runner"], "runner policy", policy=True
    )
    runner_target = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_target)
    if (
        runner_pin["policy_id"] != admission.deployment["runner_policy_id"]
        or runner_pin["sha256"]
        != admission.deployment["runner_policy_sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "runner policy differs from the build admission"
        )
    return profiles, {
        "path": runner_target.relative_to(artifact_root).as_posix(),
        "policy_id": runner_pin["policy_id"],
        "sha256": runner_pin["sha256"],
    }


def _job(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    factory: HistoricalGoldbachH100WorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    input_path = artifact_root / "input/group.json"
    _write_bytes(input_path, factory.input_bytes)
    profiles, runner_policy = _profiles_and_runner(context, site, artifact_root)
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    if algorithm_hash not in factory.algorithm_id:
        raise HistoricalGoldbachH100MaterializerError("algorithm ID/hash binding differs")
    closure_hash = canonical_sha256(_closure_manifest(records))
    admission: GoldbachBuildAdmission = site["build_admission"]
    if (
        closure_hash
        != admission.expected_artifacts["artifact_closure_manifest_sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "artifact closure differs from the build admission"
        )
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": algorithm_hash,
        },
        "artifact_closure": {
            "closure_kind": "content_addressed_image_source_reviewed_v1",
            "files": records,
            "manifest_sha256": closure_hash,
        },
        "backend": h100_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv),
            "cwd": ".",
            "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "timeout_seconds": factory.timeout_seconds,
        },
        "domain_coverage": {
            "canonical_sha256": canonical_sha256(factory.domain),
            "value": factory.domain,
        },
        "gpu_pre_run_gate": {
            "argv": [
                "artifacts/python3", "-I", "-B",
                "attestation/azure_h100_pre_run_gate.py",
                "--challenge-nonce", "@challenge@",
                "--challenge-expires-at", "@challenge_expires_at@",
                "--job-binding", "@job_binding@",
                "--package-root", ".",
                "--record-path", "@gate_record@",
                "--policy", "profiles/nvidia-gpu.rego",
                "--verifier", site["template"]["worker"]["gpu_verifier"],
                "--nras-url", site["template"]["worker"]["nras_url"],
            ],
            "record_path": "runner/h100-pre-run-gate.json",
            "required": True,
            "secret_environment_names": ["NV_ATTESTATION_SERVICE_KEY"],
            "timeout_seconds": 600,
        },
        "input_artifact": {
            "path": input_path.relative_to(artifact_root).as_posix(),
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": hashlib.sha256(factory.input_bytes).hexdigest(),
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": f"tg-goldbach-historical-h100-{factory.shard_index:08d}-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": "output/group-result.json",
        },
        "parameters": {
            "canonical_sha256": canonical_sha256(factory.parameters),
            "value": factory.parameters,
        },
        "runner_policy": runner_policy,
        "schema_version": 1,
        "target_profile": profiles["target"],
        "tpm_policy": {
            "ak_handle": "0x81000003", "bank": "sha256", "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": profiles["trust"],
        "work_trace_contract": {
            "expected_iterations": 2,
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
    actual_projection = goldbach_execution_projection_sha256(job)
    expected_projection = expected_execution_projection_sha256(
        factory.shard_index, admission
    )
    if actual_projection != expected_projection:
        raise HistoricalGoldbachH100MaterializerError(
            "materialized H100 job differs from its reviewed execution projection"
        )
    return job


def _transcript_policy(
    template: Mapping[str, Any], job_hash: str, job: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "allowed_backends": [h100_operator.BACKEND],
        "allowed_job_spec_sha256": [job_hash],
        "allowed_runner_policy_sha256": [job["runner_policy"]["sha256"]],
        "allowed_target_profile_sha256": [job["target_profile"]["sha256"]],
        "allowed_trust_profile_sha256": [job["trust_profile"]["sha256"]],
        "classification": "production",
        "kind": "sparkinterval_measured_runner_appraisal_policy",
        "policy_id": template["policies"]["transcript_appraisal"]["policy_id"],
        "require_authenticated_hardware_quote": True,
        "required_composite_appraiser_claims": [
            "measured_runner_policy_valid", "result_artifact_bound_to_execution",
        ],
        "schema_version": 1,
    }


def _operator_config(
    site: Mapping[str, Any], factory: HistoricalGoldbachH100WorkloadFactory,
    challenge: Mapping[str, Any], challenge_path: Path, output_root: Path,
    artifact_root: Path, package: Path, transcript_path: Path,
) -> dict[str, Any]:
    template = copy.deepcopy(site["template"])
    issued = dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    expires = dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    review = output_root / "review"
    handoffs = output_root / "handoffs"
    base_worker = Path(template["worker"]["artifact_root"]).parent
    worker = base_worker / "historical-goldbach" / f"group-{factory.shard_index:08d}"
    base_prefix = template["azure"]["name_prefix"][:52]
    template["azure"]["name_prefix"] = f"{base_prefix}-g{factory.shard_index:08d}"
    template["campaign_id"] = challenge["campaign_id"]
    template["challenge"] = {
        "mode": "pinned_portfolio_handoff_v1",
        "pin": _file_pin(challenge_path),
        "shard_index": factory.shard_index,
    }
    template["challenge_ttl_seconds"] = int((expires - issued).total_seconds())
    template["lean_review"] = {
        "namespace": "HistoricalGoldbachOperational",
        "registered_invocation": None,
    }
    template["outputs"] = {
        "appraisal_report": str(review / "reports/appraisal.json"),
        "challenge_dir": str(review / "challenge"),
        "deployment_record": str(review / "deployment.json"),
        "extracted_certificate_package": str(review / "returned-package"),
        "lean_candidate": str(review / "candidates/Certificate.lean"),
        "receipt": str(review / "receipt.json"),
        "registry_candidate": str(review / "candidates/TrustedComputeRegistry.lean"),
        "replay_db": str(review / "replay/trusted-compute.sqlite3"),
        "review_root": str(review),
        "state": str(review / "operator-state.json"),
        "transcript_report": str(review / "reports/transcript.json"),
    }
    template["handoffs"] = {
        "returned_certificate_archive": str(handoffs / "returned-certificate.tar"),
        "returned_worker_completion": str(handoffs / "returned-completion.json"),
        "worker_stage_manifest": str(handoffs / "worker-stage.json"),
    }
    template["workload"] = {
        "artifact_root": str(artifact_root),
        "job_spec": _file_pin(artifact_root / "job.json"),
        "package": _file_pin(package),
    }
    template["policies"]["transcript_appraisal"] = {
        **_file_pin(transcript_path),
        "classification": "production",
        "policy_id": template["policies"]["transcript_appraisal"]["policy_id"],
    }
    template["worker"] = {
        "artifact_root": str(worker / "artifact-root"),
        "certificate_archive": str(worker / "return/certificate.tar"),
        "certificate_package": str(worker / "certificate-package"),
        "challenge": str(worker / "input/challenge.json"),
        "completion_manifest": str(worker / "return/completion.json"),
        "gpu_verifier": site["template"]["worker"]["gpu_verifier"],
        "job_spec": str(worker / "artifact-root/job.json"),
        "maa_attestation_url": site["template"]["worker"]["maa_attestation_url"],
        "nras_url": site["template"]["worker"]["nras_url"],
        "nvidia_policy": str(worker / "input/nvidia-production.rego"),
        "run_package": str(worker / "measured-run"),
        "stage_manifest": str(worker / "input/worker-stage.json"),
        "transcript_appraisal_policy": str(worker / "input/transcript-appraisal.json"),
        "workload_package": str(worker / "input/workload.tar"),
    }
    return template


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    planned = plan_materialization(context, group_id, shard_index, site)
    if not planned["build_host_supported"]:
        raise HistoricalGoldbachH100MaterializerError(
            "H100 production package must be built on x86_64"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(
        group, shard_index, site["build_admission"]
    )
    if factory is None:
        raise HistoricalGoldbachH100MaterializerError("reviewed factory disappeared")
    predecessor_export, predecessor = _plan_predecessor(context, site)
    output_root = Path(planned["output_root"])
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.materializing-", dir=output_root.parent
        )
    )
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, source_manifest = _runtime_closure(
            context, site, factory, artifact_root, predecessor_export
        )
        job = _job(context, site, factory, artifact_root, records)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, canonical_json_bytes(job))
        transcript = _transcript_policy(site["template"], record_hash(job_path), job)
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(transcript_path, canonical_json_bytes(transcript))
        admission_target = stage / "control/goldbach-build-admission.json"
        _copy_exact(site["admission_path"], admission_target)
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise HistoricalGoldbachH100MaterializerError(
                "group materialization output appeared during build"
            )
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        admission_target = output_root / "control/goldbach-build-admission.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site, factory, challenge, challenge_path, output_root,
            artifact_root, package, transcript_path,
        )
        config_path = output_root / "h100-campaign.json"
        _write_bytes(config_path, canonical_json_bytes(config))
        _validated, config_hash = h100_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "build_admission": _file_pin(admission_target),
            "build_identity_sha256": site[
                "build_admission"
            ].build_identity_sha256,
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_historical-goldbach_h100_operator_validated_"
                "materialization_not_execution_evidence"
            ),
            "execution_completed": False,
            "execution_projection_sha256": (
                expected_execution_projection_sha256(
                    shard_index, site["build_admission"]
                )
            ),
            "runtime_image_closure_sha256": site[
                "build_admission"
            ].deployment["runtime_image_closure_sha256"],
            "factory_id": factory.factory_id,
            "h100_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "plan_predecessor": predecessor,
            "portfolio_shard_config": _file_pin(shard_path),
            "registered_invocation": None,
            "retained_export_inside_certificate": planned[
                "retained_export_relative_path"
            ],
            "schema_version": 1,
            "shard_index": shard_index,
            "source_manifest_sha256": hashlib.sha256(
                canonical_json_bytes(source_manifest)
            ).hexdigest(),
            "source_run_receipt_produced": False,
            "transcript_policy": _file_pin(transcript_path),
        }
        manifest_path = output_root / "materialization-manifest.json"
        _write_bytes(manifest_path, canonical_json_bytes(manifest))
        complete = True
        return {
            **manifest,
            "h100_operator_config": {
                **manifest["h100_operator_config"], "path": str(config_path),
            },
            "job_spec": {**manifest["job_spec"], "path": str(job_path)},
            "manifest": str(manifest_path),
            "package": {**manifest["package"], "path": str(package)},
        }
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"H100 historical Goldbach materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


def export_retained_group(
    materialization_manifest: Path,
    signed_receipt_path: Path,
    key_manifest: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Extract one signed, replayed H100 export for the CPU aggregate handoff."""

    try:
        manifest = load_json(materialization_manifest, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"cannot load H100 materialization manifest: {error}"
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("schema_version") != 1
        or manifest.get("registered_invocation") is not None
        or not isinstance(manifest.get("shard_index"), int)
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "materialization manifest is not an operational H100 group"
        )
    group_index = manifest["shard_index"]
    _admission_pin, admission_path = _pin(
        manifest.get("build_admission"),
        "materialized Goldbach build admission",
    )
    try:
        admission = load_build_admission(
            admission_path, expected_sha256=_admission_pin["sha256"]
        )
    except GoldbachBuildAdmissionError as error:
        raise HistoricalGoldbachH100MaterializerError(str(error)) from error
    if (
        manifest.get("build_identity_sha256")
        != admission.build_identity_sha256
        or manifest.get("execution_projection_sha256")
        != expected_execution_projection_sha256(group_index, admission)
        or manifest.get("runtime_image_closure_sha256")
        != admission.deployment["runtime_image_closure_sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "materialization manifest build/job admission differs"
        )
    _config_pin, config_path = _pin(
        manifest["h100_operator_config"], "materialized H100 operator config"
    )
    config, _config_hash = h100_operator.load_config(config_path)
    try:
        signed = load_verified_receipt(
            signed_receipt_path.resolve(strict=True), key_manifest=key_manifest
        )
    except Exception as error:
        raise HistoricalGoldbachH100MaterializerError(
            f"signed H100 receipt failed verification: {error}"
        ) from error
    signed_rows = _validate_h100_result(
        signed, group_index, admission
    )["receipt_sha256s"]
    challenge_pin, challenge_path = _pin(
        config["challenge"]["pin"], "portfolio challenge"
    )
    challenge = load_json(challenge_path, require_canonical=True)
    if (
        signed["claim"]["nonce"] != challenge.get("nonce")
        or challenge_pin["sha256"] != config["challenge"]["pin"]["sha256"]
    ):
        raise HistoricalGoldbachH100MaterializerError(
            "signed H100 receipt is not bound to the materialized portfolio challenge"
        )
    relative = manifest.get("retained_export_inside_certificate")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise HistoricalGoldbachH100MaterializerError(
            "retained export path is not safe and relative"
        )
    extracted = Path(config["outputs"]["extracted_certificate_package"])
    # The persisted path is relative to the certificate package root.  The
    # operator extraction root itself is that package, so strip its leading
    # bundle-root component only by normal path composition, never by globbing.
    archive = extracted / relative
    export_manifest = verify_retained_export_archive(
        archive, PHASE_ID, group_index
    )
    plan = load_plan(Path(config["workload"]["artifact_root"]) / "plans/binary-plan.json")
    temporary = Path(tempfile.mkdtemp(prefix=".historical-goldbach-h100-export-review-"))
    try:
        extract_archive(archive, temporary / "export")
        receipts = temporary / "export/payload/binary-receipts"
        indices = production_group_leaf_indices(plan, group_index)
        names = {path.name for path in receipts.iterdir() if path.is_file()}
        if names != {f"receipt-{index:08d}.json" for index in indices}:
            raise HistoricalGoldbachH100MaterializerError(
                "retained H100 export does not contain its exact eight leaves"
            )
        for index in indices:
            value = load_binary_receipt(
                receipts / f"receipt-{index:08d}.json", plan=plan
            )
            if value["receipt_sha256"] != signed_rows[index]:
                raise HistoricalGoldbachH100MaterializerError(
                    "retained leaf differs from the signed H100 group result"
                )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    if output_path.exists() or output_path.is_symlink():
        raise HistoricalGoldbachH100MaterializerError(
            "retained export output must be fresh"
        )
    _copy_exact(archive, output_path)
    return {
        "accepted": False,
        "classification": "signed_h100_operational_export_for_cpu_dag_handoff",
        "group_index": group_index,
        "receipt_sha256": signed["receipt_sha256"],
        "retained_export": _file_pin(output_path),
        "retained_tree_sha256": export_manifest["tree_sha256"],
    }


__all__ = [
    "HistoricalGoldbachH100MaterializerError", "export_retained_group", "load_site",
    "materialize", "plan_materialization",
]
