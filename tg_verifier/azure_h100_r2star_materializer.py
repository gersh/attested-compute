# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the source-reviewed R2Star Azure H100 terminal job.

The package is built from a fixed repository source list, a reviewed Boost
1.83 tree, exact compiler pins, and compiler-reported header dependencies.
The measured command cannot consume a caller-supplied campaign directory: it
always starts in a fresh challenge-bound workspace.  Materialization is not
execution evidence and this module never edits the semantic binding registry.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_h100_r2star_workload_factory import (
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    R2StarH100WorkloadFactory,
    factory_for_portfolio_group,
    make_factory,
    registered_identity,
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
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes as campaign_json_bytes,
    hash_file_once,
    load_json,
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
from create_run_bundle import (  # noqa: E402
    canonical_json_bytes as bundle_json_bytes,
    canonical_sha256,
    load_canonical_json,
    load_profile,
)
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
    validate_registered_invocation,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import _closure_manifest, validate_job_spec  # noqa: E402
import verify_run_bundle  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.h100.r2star-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.h100.r2star-materialization.v1"
SITE_FIELDS = {
    "base_campaign",
    "build",
    "kind",
    "output_root",
    "schema_version",
}
BUILD_FIELDS = {"boost_include_root", "host_cxx", "nvcc", "python"}
H100_PROFILE_PATHS = {
    "target": "profiles/targets/azure_ncc40ads_h100_v5.json",
    "trust": "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json",
}
BOOST_HEADER_COUNT = 15_653
BOOST_HEADER_BYTES = 149_594_508
BOOST_HEADER_TREE_SHA256 = (
    "7ecf4808a419bd489f930c685320cf2745e46c6bc5591122c26773386214d8e2"
)
BOOST_TREE_DOMAIN = b"sparkinterval/boost-header-tree/v1\0"
SOURCE_CLOSURE_KIND = "sparkinterval.r2star-h100-source-closure.v1"
RETAINED_EXPORT_RELATIVE = (
    "bundle-root/work/r2star-source-scale/r2star-full-source.tar"
)
BUILD_ENVIRONMENT_BASE = {
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC",
}


class R2StarH100MaterializerError(RuntimeError):
    """A source, build, portfolio, or signed-export binding failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise R2StarH100MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise R2StarH100MaterializerError(
            f"{what} must be a non-symlink directory"
        )
    return path


def _boost_identity(root: Path) -> dict[str, Any]:
    boost = root / "boost" if (root / "boost").is_dir() else root
    digest = hashlib.sha256(BOOST_TREE_DOMAIN)
    count = 0
    size = 0
    for path in sorted(boost.rglob("*")):
        if path.is_symlink():
            raise R2StarH100MaterializerError(
                "Boost header closure contains a symlink"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise R2StarH100MaterializerError(
                "Boost header closure contains a special file"
            )
        relative = path.relative_to(boost).as_posix().encode("utf-8")
        raw = path.read_bytes()
        count += 1
        size += len(raw)
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    identity = {
        "file_count": count,
        "size_bytes": size,
        "tree_sha256": digest.hexdigest(),
    }
    expected = {
        "file_count": BOOST_HEADER_COUNT,
        "size_bytes": BOOST_HEADER_BYTES,
        "tree_sha256": BOOST_HEADER_TREE_SHA256,
    }
    if identity != expected or not (boost / "multiprecision/cpp_int.hpp").is_file():
        raise R2StarH100MaterializerError(
            "Boost 1.83 header closure differs from the reviewed pin"
        )
    return {**identity, "path": str(boost)}


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise R2StarH100MaterializerError(
            f"cannot load canonical R2Star H100 materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "R2Star H100 materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise R2StarH100MaterializerError(
            "unsupported R2Star H100 materializer site kind/version"
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
        raise R2StarH100MaterializerError(
            "base H100 campaign template has the wrong kind/version"
        )
    build = _exact(site["build"], BUILD_FIELDS, "R2Star H100 build inputs")
    boost = _directory(build["boost_include_root"], "Boost include root")
    _boost_identity(boost)
    for field in ("host_cxx", "nvcc", "python"):
        _unused_pin, executable = _pin(build[field], field)
        if not os.access(executable, os.X_OK):
            raise R2StarH100MaterializerError(f"{field} is not executable")
    output_root = _absolute(site["output_root"], "output_root", exists=False)
    try:
        output_root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise R2StarH100MaterializerError(
            "output_root must stay outside the repository"
        )
    return {
        "build": build,
        "output_root": output_root,
        "site_pin": _file_pin(path),
        "template": template,
    }


def _run_build(
    argv: list[str], *, cwd: Path, nvcc_directory: Path, timeout: int = 1800
) -> dict[str, Any]:
    environment = {
        **BUILD_ENVIRONMENT_BASE,
        "PATH": f"{nvcc_directory}:/usr/bin:/bin",
    }
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise R2StarH100MaterializerError(
            f"closed R2Star CUDA build failed: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise R2StarH100MaterializerError(
            f"closed R2Star CUDA build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": environment,
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _dependency_paths(path: Path) -> list[Path]:
    raw = path.read_text(encoding="utf-8").replace("\\\n", " ")
    if ":" not in raw:
        raise R2StarH100MaterializerError("compiler dependency file is malformed")
    _target, dependencies = raw.split(":", 1)
    try:
        values = shlex.split(dependencies)
    except ValueError as error:
        raise R2StarH100MaterializerError(
            "compiler dependency file cannot be parsed"
        ) from error
    return [Path(value).resolve(strict=True) for value in values]


def _require_x86_64_elf(path: Path) -> None:
    raw = path.read_bytes()[:20]
    if (
        len(raw) != 20
        or raw[:4] != b"\x7fELF"
        or raw[4] != 2
        or raw[5] != 1
        or int.from_bytes(raw[18:20], "little") != 62
    ):
        raise R2StarH100MaterializerError(
            "built R2Star executable is not little-endian x86_64 ELF"
        )


def _runner_policy_self_check(runner: Path) -> dict[str, Any]:
    environment = {**BUILD_ENVIRONMENT_BASE, "PATH": "/usr/bin:/bin"}
    help_run = subprocess.run(
        [str(runner), "--help"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=environment,
    )
    forbidden = subprocess.run(
        [str(runner), "--allow-other-device"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=environment,
    )
    if (
        help_run.returncode != 0
        or b"Requires exactly one visible NVIDIA H100" not in help_run.stdout
        or forbidden.returncode == 0
        or b"disabled by the H100 runner" not in forbidden.stderr
    ):
        raise R2StarH100MaterializerError(
            "built R2Star runner failed its H100 policy-only self-check"
        )
    return {
        "help_stdout_sha256": hashlib.sha256(help_run.stdout).hexdigest(),
        "kind": "h100_policy_interface_self_check_no_cuda_execution",
        "override_stderr_sha256": hashlib.sha256(forbidden.stderr).hexdigest(),
    }


def _arithmetic_replayer_self_check(replayer: Path) -> dict[str, Any]:
    environment = {**BUILD_ENVIRONMENT_BASE, "PATH": "/usr/bin:/bin"}
    help_run = subprocess.run(
        [str(replayer), "--help"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=environment,
    )
    forbidden = subprocess.run(
        [str(replayer), "--unknown-option"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=environment,
    )
    if (
        help_run.returncode != 0
        or b"CPU-only full row-arithmetic replay" not in help_run.stdout
        or forbidden.returncode == 0
        or b"unknown argument" not in forbidden.stderr
    ):
        raise R2StarH100MaterializerError(
            "built R2Star arithmetic replayer failed its fail-closed self-check"
        )
    return {
        "help_stdout_sha256": hashlib.sha256(help_run.stdout).hexdigest(),
        "kind": "cpu_arithmetic_replayer_interface_self_check",
        "unknown_option_stderr_sha256": hashlib.sha256(
            forbidden.stderr
        ).hexdigest(),
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
    if factory is None or shard.get("argv") != list(factory.portfolio_argv):
        raise R2StarH100MaterializerError(
            "portfolio shard has no exact source-reviewed R2Star H100 factory"
        )
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
        raise R2StarH100MaterializerError(
            "challenge TTL cannot contain the R2Star job, H100 gate, and evidence margin"
        )
    output_root = Path(site["output_root"])
    if output_root.exists() or output_root.is_symlink():
        raise R2StarH100MaterializerError(
            "R2Star materialization output already exists"
        )
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": platform.machine().lower() in ("x86_64", "amd64"),
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": (
            "reviewed_r2star_h100_materialization_plan_not_execution_evidence"
        ),
        "factory_id": factory.factory_id,
        "fresh_workspace_required": True,
        "group_id": group_id,
        "output_root": str(output_root),
        "registered_invocation": REGISTERED_INVOCATION,
        "resume_policy": "no_external_resume_or_prepopulated_campaign_state",
        "retained_export_relative_path": RETAINED_EXPORT_RELATIVE,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise R2StarH100MaterializerError(
            "R2Star production package must be built on x86_64"
        )
    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=False)
        if hash_file_once(destination) != (row["sha256"], row["size_bytes"]):
            raise R2StarH100MaterializerError(
                f"project source changed during copy: {relative}"
            )
        copied[relative] = destination

    boost_identity = _boost_identity(Path(site["build"]["boost_include_root"]))
    boost = Path(boost_identity["path"])
    _nvcc_pin, nvcc = _pin(site["build"]["nvcc"], "nvcc")
    _cxx_pin, cxx = _pin(site["build"]["host_cxx"], "host C++ compiler")
    _python_pin, python = _pin(site["build"]["python"], "python")
    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    python_target = artifacts / "python3"
    _copy_exact(python, python_target, executable=True)
    build_root = artifact_root / ".build"
    build_root.mkdir(mode=0o700)

    prefix = artifact_root.resolve().as_posix()
    boost_parent = boost.parent.resolve().as_posix()
    common = [
        str(nvcc),
        "-O3",
        "-std=c++17",
        "-arch=sm_90",
        "-ccbin",
        str(cxx),
        "--threads",
        "1",
        "-I",
        str(artifact_root / "gpu/include"),
        "-I",
        str(boost.parent),
        (
            "-Xcompiler=-O3,-march=x86-64-v2,-mtune=generic,"
            f"-ffile-prefix-map={prefix}=.,-fmacro-prefix-map={prefix}=.,"
            f"-fdebug-prefix-map={prefix}=.,"
            f"-ffile-prefix-map={boost_parent}=source/boost-1.83,"
            f"-fmacro-prefix-map={boost_parent}=source/boost-1.83,"
            f"-fdebug-prefix-map={boost_parent}=source/boost-1.83"
        ),
    ]
    compilation = (
        (
            "factor",
            copied["gpu/platform/h100/h100_tg_r2star_factor_support_kernel.cu"],
        ),
        (
            "chunk",
            copied["gpu/platform/h100/h100_tg_r2star_chunk_kernel.cu"],
        ),
        (
            "runner",
            copied["gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp"],
        ),
    )
    build_steps: list[dict[str, Any]] = []
    objects: list[Path] = []
    dependencies: list[Path] = []
    for name, source in compilation:
        object_path = build_root / f"{name}.o"
        dependency_path = build_root / f"{name}.d"
        device_flags = (
            [
                "--fmad=false",
                "--ftz=false",
                "--prec-div=true",
                "--prec-sqrt=true",
                "-lineinfo",
            ]
            if source.suffix == ".cu"
            else []
        )
        argv = [
            *common,
            *device_flags,
            "-MMD",
            "-MF",
            str(dependency_path),
            "-c",
            str(source),
            "-o",
            str(object_path),
        ]
        build_steps.append(
            _run_build(argv, cwd=artifact_root, nvcc_directory=nvcc.parent)
        )
        objects.append(object_path)
        dependencies.extend(_dependency_paths(dependency_path))

    arithmetic_replayer = artifacts / "r2star-arithmetic-replay"
    arithmetic_dependency_path = build_root / "arithmetic-replay.d"
    arithmetic_argv = [
        str(cxx),
        "-O3",
        "-std=c++17",
        "-pthread",
        "-MMD",
        "-MF",
        str(arithmetic_dependency_path),
        "-I",
        str(artifact_root / "gpu/include"),
        "-I",
        str(boost.parent),
        "-march=x86-64-v2",
        "-mtune=generic",
        f"-ffile-prefix-map={prefix}=.",
        f"-fmacro-prefix-map={prefix}=.",
        f"-fdebug-prefix-map={prefix}=.",
        f"-ffile-prefix-map={boost_parent}=source/boost-1.83",
        f"-fmacro-prefix-map={boost_parent}=source/boost-1.83",
        f"-fdebug-prefix-map={boost_parent}=source/boost-1.83",
        str(copied["reference/tg_r2star_arithmetic_replay.cpp"]),
        "-o",
        str(arithmetic_replayer),
    ]
    build_steps.append(
        _run_build(
            arithmetic_argv,
            cwd=artifact_root,
            nvcc_directory=nvcc.parent,
        )
    )
    dependencies.extend(_dependency_paths(arithmetic_dependency_path))
    arithmetic_replayer.chmod(0o500)
    _require_x86_64_elf(arithmetic_replayer)
    build_steps.append(
        _arithmetic_replayer_self_check(arithmetic_replayer)
    )

    runner = artifacts / "r2star-h100"
    link = [
        str(nvcc),
        "-arch=sm_90",
        "-ccbin",
        str(cxx),
        *[str(path) for path in objects],
        "-Xlinker",
        "--build-id=sha1",
        "-o",
        str(runner),
    ]
    build_steps.append(
        _run_build(link, cwd=artifact_root, nvcc_directory=nvcc.parent)
    )
    runner.chmod(0o500)
    _require_x86_64_elf(runner)
    build_steps.append(_runner_policy_self_check(runner))

    dependency_copies: list[Path] = []
    dependency_rows: list[dict[str, Any]] = []
    for dependency in sorted(set(dependencies)):
        try:
            relative = dependency.relative_to(artifact_root)
            destination = artifact_root / relative
            classification = "reviewed_project_source"
        except ValueError:
            try:
                relative = dependency.relative_to(boost)
                destination = (
                    artifact_root / "source/boost-1.83/boost" / relative
                )
                classification = "reviewed_boost_1_83_header"
            except ValueError:
                relative = Path(*dependency.parts[1:])
                destination = artifact_root / "source/build-host" / relative
                classification = "exact_compiler_reported_build_header"
            if not destination.exists():
                _copy_exact(dependency, destination)
                dependency_copies.append(destination)
        pin = _file_pin(destination)
        dependency_rows.append(
            {
                "classification": classification,
                "path": destination.relative_to(artifact_root).as_posix(),
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
        )
    if not any(
        row["classification"] == "reviewed_boost_1_83_header"
        and row["path"].endswith("boost/multiprecision/cpp_int.hpp")
        for row in dependency_rows
    ):
        raise R2StarH100MaterializerError(
            "compiler did not report the reviewed cpp_int dependency"
        )

    version_rows = {}
    for name, executable, argv in (
        ("host_cxx", cxx, [str(cxx), "--version"]),
        ("nvcc", nvcc, [str(nvcc), "--version"]),
        ("python", python_target, [str(python_target), "-I", "--version"]),
    ):
        completed = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            env={**BUILD_ENVIRONMENT_BASE, "PATH": f"{nvcc.parent}:/usr/bin:/bin"},
        )
        if completed.returncode != 0:
            raise R2StarH100MaterializerError(f"{name} version check failed")
        version_rows[name] = {
            **_file_pin(executable),
            "version_output_sha256": hashlib.sha256(
                completed.stdout + completed.stderr
            ).hexdigest(),
        }

    template = site["template"]
    _nvidia_pin, nvidia_source = _pin(
        template["policies"]["nvidia"], "NVIDIA policy", policy=True
    )
    nvidia_target = artifact_root / "profiles/nvidia-gpu.rego"
    _copy_exact(nvidia_source, nvidia_target)

    runner_pin = _file_pin(runner)
    arithmetic_replayer_pin = _file_pin(arithmetic_replayer)
    python_pin = _file_pin(python_target)
    source_rows = []
    source_paths = sorted(set((*copied.values(), *dependency_copies)))
    for source in source_paths:
        pin = _file_pin(source)
        source_rows.append(
            {
                "path": source.relative_to(artifact_root).as_posix(),
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
        )
    source_manifest = {
        "build": {
            "boost_header_tree_sha256": boost_identity["tree_sha256"],
            "compiler_reported_dependencies": dependency_rows,
            "steps": [row["argv_sha256"] for row in build_steps if "argv_sha256" in row],
            "tools": version_rows,
        },
        "files": source_rows,
        "kind": SOURCE_CLOSURE_KIND,
        "runtime": {
            "arithmetic_replayer": {
                "path": "artifacts/r2star-arithmetic-replay",
                "sha256": arithmetic_replayer_pin["sha256"],
                "size_bytes": arithmetic_replayer_pin["size_bytes"],
            },
            "dynamic_runtime_boundary": (
                "exact versioned Azure private image plus NVIDIA driver/CUDA loader; "
                "not a CUDA-to-Lean refinement claim"
            ),
            "python": {
                "path": "artifacts/python3",
                "sha256": python_pin["sha256"],
                "size_bytes": python_pin["size_bytes"],
            },
            "runner": {
                "path": "artifacts/r2star-h100",
                "sha256": runner_pin["sha256"],
                "size_bytes": runner_pin["size_bytes"],
            },
        },
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(source_manifest_path, campaign_json_bytes(source_manifest))

    records = [
        _artifact_record(
            python_target,
            artifact_root,
            role="image_bound_cpython_host",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            runner,
            artifact_root,
            role="source_reviewed_sm90_r2star_runner",
            statement_role="gpu_executable",
            executable=True,
        ),
        _artifact_record(
            arithmetic_replayer,
            artifact_root,
            role="source_reviewed_cpu_r2star_full_row_arithmetic_replayer",
            statement_role="checker_executable",
            executable=True,
        ),
        _artifact_record(
            nvidia_target,
            artifact_root,
            role="nvidia_pre_run_appraisal_policy",
            statement_role="gpu_attestation_policy",
            executable=False,
        ),
        _artifact_record(
            source_manifest_path,
            artifact_root,
            role="reviewed_r2star_source_closure_manifest",
            statement_role="source_tree",
            executable=False,
        ),
    ]
    for path in source_paths:
        records.append(
            _artifact_record(
                path,
                artifact_root,
                role="reviewed_source_or_build_header",
                statement_role=None,
                executable=False,
            )
        )
    records.sort(key=lambda row: row["path"])
    return records, build_steps, source_manifest


def _profiles_and_runner(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
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
    runner_pin, runner_source = _pin(
        site["template"]["policies"]["runner"],
        "runner policy",
        policy=True,
    )
    runner_target = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_target)
    return profiles, {
        "path": runner_target.relative_to(artifact_root).as_posix(),
        "policy_id": runner_pin["policy_id"],
        "sha256": runner_pin["sha256"],
    }


def _job(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    factory: R2StarH100WorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    input_path = artifact_root / "input/r2star-source-range.json"
    _write_bytes(input_path, factory.input_bytes)
    profiles, runner_policy = _profiles_and_runner(context, site, artifact_root)
    identity = registered_identity()
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    if (
        algorithm_hash != identity["algorithm_hash"]
        or hashlib.sha256(factory.input_bytes).hexdigest() != identity["input_hash"]
        or canonical_sha256(factory.parameters) != identity["parameters_hash"]
        or canonical_sha256(factory.domain) != identity["domain_hash"]
    ):
        raise R2StarH100MaterializerError(
            "R2Star materializer identity differs from the closed invocation"
        )
    closure_hash = canonical_sha256(_closure_manifest(records))
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
                "artifacts/python3",
                "-I",
                "-B",
                "attestation/azure_h100_pre_run_gate.py",
                "--challenge-nonce",
                "@challenge@",
                "--challenge-expires-at",
                "@challenge_expires_at@",
                "--job-binding",
                "@job_binding@",
                "--package-root",
                ".",
                "--record-path",
                "@gate_record@",
                "--policy",
                "profiles/nvidia-gpu.rego",
                "--verifier",
                site["template"]["worker"]["gpu_verifier"],
                "--nras-url",
                site["template"]["worker"]["nras_url"],
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
            "sha256": identity["input_hash"],
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": "tg-ramare-zuniga-lemma-6-2-fresh-h100-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": "output/registered-result.txt",
        },
        "parameters": {
            "canonical_sha256": canonical_sha256(factory.parameters),
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
            "measured_runner_policy_valid",
            "result_artifact_bound_to_execution",
        ],
        "schema_version": 1,
    }


def _operator_config(
    site: Mapping[str, Any],
    factory: R2StarH100WorkloadFactory,
    challenge: Mapping[str, Any],
    challenge_path: Path,
    output_root: Path,
    artifact_root: Path,
    package: Path,
    transcript_path: Path,
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
    worker = base_worker / "ramare-zuniga-lemma-6-2"
    template["azure"]["name_prefix"] = (
        template["azure"]["name_prefix"][:50] + "-r2star"
    )
    template["campaign_id"] = challenge["campaign_id"]
    template["challenge"] = {
        "mode": "pinned_portfolio_handoff_v1",
        "pin": _file_pin(challenge_path),
        "shard_index": factory.shard_index,
    }
    template["challenge_ttl_seconds"] = int((expires - issued).total_seconds())
    template["lean_review"] = {
        "namespace": "RamareZunigaLemma62Azure",
        "registered_invocation": factory.registered_invocation,
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
        "transcript_appraisal_policy": str(
            worker / "input/transcript-appraisal.json"
        ),
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
        raise R2StarH100MaterializerError(
            "R2Star production package must be built on x86_64"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise R2StarH100MaterializerError("reviewed R2Star factory disappeared")
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
        records, build_steps, source_manifest = _build_runtime_closure(
            context, site, artifact_root
        )
        job = _job(context, site, factory, artifact_root, records)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, bundle_json_bytes(job))
        transcript = _transcript_policy(site["template"], hash_file_once(job_path)[0], job)
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(transcript_path, bundle_json_bytes(transcript))
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise R2StarH100MaterializerError(
                "R2Star materialization output appeared during build"
            )
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site,
            factory,
            challenge,
            challenge_path,
            output_root,
            artifact_root,
            package,
            transcript_path,
        )
        config_path = output_root / "h100-campaign.json"
        _write_bytes(config_path, bundle_json_bytes(config))
        _validated, config_hash = h100_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_fresh_r2star_h100_operator_validated_"
                "materialization_not_execution_evidence"
            ),
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "fresh_workspace_required": True,
            "h100_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "portfolio_shard_config": _file_pin(shard_path),
            "registered_invocation": factory.registered_invocation,
            "resume_policy": "no_external_resume_or_prepopulated_campaign_state",
            "retained_export_inside_certificate": RETAINED_EXPORT_RELATIVE,
            "schema_version": 1,
            "semantic_binding_enabled": False,
            "shard_index": shard_index,
            "source_manifest_sha256": hashlib.sha256(
                campaign_json_bytes(source_manifest)
            ).hexdigest(),
            "source_run_receipt_produced": False,
            "transcript_policy": _file_pin(transcript_path),
        }
        manifest_path = output_root / "materialization-manifest.json"
        _write_bytes(manifest_path, campaign_json_bytes(manifest))
        complete = True
        return {
            **manifest,
            "h100_operator_config": {
                **manifest["h100_operator_config"],
                "path": str(config_path),
            },
            "job_spec": {**manifest["job_spec"], "path": str(job_path)},
            "manifest": str(manifest_path),
            "package": {**manifest["package"], "path": str(package)},
        }
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise R2StarH100MaterializerError(
            f"R2Star H100 materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


def export_retained_campaign(
    materialization_manifest: Path,
    signed_receipt_path: Path,
    key_manifest: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Authenticate, independently replay, and copy the retained full chain.

    Authentication is not inferred from the R2Star structural hashes.  The
    signed receipt first fixes the exact registered invocation and wire/run
    bundle.  The wire statement fixes the work-trace artifact and chain hash;
    the pinned trace verifier then fixes and replays the retained archive.
    """

    try:
        manifest = load_json(materialization_manifest, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise R2StarH100MaterializerError(
            f"cannot load R2Star materialization manifest: {error}"
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("schema_version") != 1
        or manifest.get("registered_invocation") != REGISTERED_INVOCATION
        or manifest.get("fresh_workspace_required") is not True
        or manifest.get("semantic_binding_enabled") is not False
        or manifest.get("retained_export_inside_certificate")
        != RETAINED_EXPORT_RELATIVE
    ):
        raise R2StarH100MaterializerError(
            "materialization manifest is not the exact fresh R2Star terminal"
        )
    _config_pin, config_path = _pin(
        manifest["h100_operator_config"], "materialized H100 operator config"
    )
    config, _config_hash = h100_operator.load_config(config_path)
    if config["lean_review"]["registered_invocation"] != REGISTERED_INVOCATION:
        raise R2StarH100MaterializerError(
            "materialized operator changed the registered invocation"
        )
    try:
        signed = load_verified_receipt(
            signed_receipt_path.resolve(strict=True), key_manifest=key_manifest
        )
        validate_registered_invocation(signed, REGISTERED_INVOCATION)
    except Exception as error:
        raise R2StarH100MaterializerError(
            f"signed R2Star receipt failed verification: {error}"
        ) from error
    _challenge_pin, challenge_path = _pin(
        config["challenge"]["pin"], "portfolio challenge"
    )
    challenge = load_json(challenge_path, require_canonical=True)
    if signed["claim"]["nonce"] != challenge.get("nonce"):
        raise R2StarH100MaterializerError(
            "signed R2Star receipt is not bound to the portfolio challenge"
        )

    run_root = Path(config["outputs"]["extracted_certificate_package"]) / "bundle-root"
    bundle_path = run_root / "run-bundle.json"
    try:
        bundle = load_canonical_json(bundle_path)
        checked = verify_run_bundle.verify_bundle(bundle, artifact_root=run_root)
    except Exception as error:
        raise R2StarH100MaterializerError(
            f"returned R2Star run bundle failed verification: {error}"
        ) from error
    if (
        checked.get("artifacts_verified") is not True
        or checked.get("bundle_sha256") != signed["bindings"]["run_bundle_sha256"]
        or checked.get("statement_sha256")
        != signed["bindings"]["wire_statement_sha256"]
    ):
        raise R2StarH100MaterializerError(
            "signed receipt does not authenticate the returned R2Star run bundle"
        )
    statement = bundle.get("statement")
    environment = (
        statement.get("execution_environment", {}).get("value")
        if isinstance(statement, dict)
        else None
    )
    _job_pin, job_path = _pin(config["workload"]["job_spec"], "R2Star job spec")
    job = load_canonical_json(job_path)
    factory = make_factory(0)
    if job.get("command", {}).get("argv") != list(
        factory.command_argv
    ) or job.get("work_trace_contract", {}).get("verifier_argv") != list(
        factory.trace_verifier_argv
    ):
        raise R2StarH100MaterializerError(
            "materialized job differs from the exact R2Star factory"
        )
    trace_path = run_root / job["work_trace_contract"]["path"]
    trace = load_json(trace_path, require_canonical=True)
    trace_sha, _trace_size = hash_file_once(trace_path)
    if (
        not isinstance(environment, dict)
        or trace_sha != environment.get("work_trace_artifact_sha256")
        or trace.get("trace_sha256") != environment.get("work_trace_chain_sha256")
        or trace.get("job_binding_sha256")
        != environment.get("job_binding_sha256")
    ):
        raise R2StarH100MaterializerError(
            "wire statement does not authenticate the retained R2Star trace"
        )
    replacements = {
        "@challenge@": challenge["nonce"],
        "@job_binding@": environment["job_binding_sha256"],
        "@input@": job["input_artifact"]["path"],
        "@output@": job["output_contract"]["path"],
        "@trace@": job["work_trace_contract"]["path"],
    }
    verifier_argv = [
        replacements.get(token, token)
        for token in factory.trace_verifier_argv
    ]
    completed = subprocess.run(
        verifier_argv,
        cwd=run_root,
        env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=factory.timeout_seconds,
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr[-4000:].decode("utf-8", "replace")
        raise R2StarH100MaterializerError(
            f"retained R2Star trace replay failed: {diagnostic}"
        )
    archive = Path(config["outputs"]["extracted_certificate_package"]) / Path(
        RETAINED_EXPORT_RELATIVE
    ).relative_to("bundle-root")
    if output_path.exists() or output_path.is_symlink():
        raise R2StarH100MaterializerError(
            "retained R2Star export output must be fresh"
        )
    _copy_exact(archive, output_path)
    archive_pin = _file_pin(output_path)
    return {
        "accepted": False,
        "classification": (
            "signed_challenge_bound_r2star_retained_export_for_human_audit"
        ),
        "receipt_sha256": signed["receipt_sha256"],
        "retained_export": archive_pin,
        "semantic_binding_enabled": False,
        "wire_statement_sha256": checked["statement_sha256"],
        "work_trace_sha256": trace_sha,
    }


__all__ = [
    "MANIFEST_KIND",
    "R2StarH100MaterializerError",
    "SITE_KIND",
    "export_retained_campaign",
    "load_site",
    "materialize",
    "plan_materialization",
]
