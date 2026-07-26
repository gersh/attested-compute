# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize closed Proposition 12.2.4 Azure SEV-SNP CPU jobs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_prop1224_workload_factory import (
    CAMPAIGN_ID,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    WORKER_GROUP_COUNT,
    Prop1224CPUWorkloadFactory,
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
    _require_x86_64_static_elf,
    _source_pin,
    _transcript_policy,
    _write_bytes,
    load_site as load_base_site,
    record_hash,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    load_json,
)
from tg_verifier.prop1224_mpfr_campaign import validate_runner_report
from tg_verifier.prop1224_upstreams import (
    Prop1224UpstreamError,
    verify_source,
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
    load_verified_receipt,
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402
from tg_prop1224_azure_measured_workload import (  # noqa: E402
    verify_retained_export_archive,
)


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.prop1224-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.prop1224-materialization.v1"
SITE_FIELDS = {"base_site", "kind", "prop1224", "schema_version"}
PROP1224_FIELDS = {"gmp_source_root", "mpfr_source_root", "predecessor_exports"}
PREDECESSOR_FIELDS = {"export", "group_id", "shard_index"}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
FIXED_TOOL_PATH = "/usr/bin:/bin:/usr/local/bin"
REQUIRED_BUILD_TOOLS = (
    "ar",
    "g++",
    "gcc",
    "make",
    "python3",
    "ranlib",
    "strip",
)
BUILD_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": FIXED_TOOL_PATH,
    "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC",
}
GENERIC_CFLAGS = (
    "-O3 -march=x86-64-v2 -mtune=generic -fno-fast-math "
    "-fno-associative-math -ffp-contract=off -frounding-math"
)


class Prop1224MaterializerError(RuntimeError):
    """A handoff, upstream, static build, or measured job failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise Prop1224MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise Prop1224MaterializerError(f"{what} must be a non-symlink directory")
    return path


def _upstream_identity(root: Path, component: str) -> dict[str, Any]:
    try:
        return verify_source(root, component)
    except (OSError, Prop1224UpstreamError, ValueError) as error:
        raise Prop1224MaterializerError(
            f"pinned {component} source failed review: {error}"
        ) from error


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise Prop1224MaterializerError(
            f"cannot load canonical Proposition 12.2.4 materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "Proposition 12.2.4 materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise Prop1224MaterializerError(
            "unsupported Proposition 12.2.4 materializer site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise Prop1224MaterializerError(str(error)) from error
    inputs = _exact(site["prop1224"], PROP1224_FIELDS, "Proposition 12.2.4 inputs")
    gmp = _directory(inputs["gmp_source_root"], "GMP source root")
    mpfr = _directory(inputs["mpfr_source_root"], "MPFR source root")
    _upstream_identity(gmp, "gmp")
    _upstream_identity(mpfr, "mpfr")
    if not isinstance(inputs["predecessor_exports"], list):
        raise Prop1224MaterializerError("predecessor_exports must be an array")
    if len(inputs["predecessor_exports"]) > WORKER_GROUP_COUNT:
        raise Prop1224MaterializerError(
            "predecessor_exports exceeds the four reviewed worker groups"
        )
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(inputs["predecessor_exports"]):
        row = _exact(raw, PREDECESSOR_FIELDS, f"predecessor export {index}")
        if not isinstance(row["group_id"], str) or not row["group_id"]:
            raise Prop1224MaterializerError("predecessor group_id is malformed")
        shard = row["shard_index"]
        if (
            isinstance(shard, bool)
            or not isinstance(shard, int)
            or not 0 <= shard < WORKER_GROUP_COUNT
        ):
            raise Prop1224MaterializerError("predecessor shard_index is malformed")
        identity = (row["group_id"], shard)
        if identity in seen:
            raise Prop1224MaterializerError("duplicate predecessor export identity")
        seen.add(identity)
        _pin(row["export"], f"predecessor export {index}")
    return {"base": base, "prop1224": inputs, "site_pin": _file_pin(path)}


def _expected_predecessors(
    factory: Prop1224CPUWorkloadFactory,
) -> tuple[tuple[str, int], ...]:
    if not factory.terminal:
        return ()
    return tuple(
        (f"{CAMPAIGN_ID}::mpfr-shards", index)
        for index in range(WORKER_GROUP_COUNT)
    )


def _operational_result(
    receipt: Mapping[str, Any], shard_index: int,
) -> dict[str, Any]:
    result = receipt["claim"]["result"]
    if hashlib.sha256(result.encode("utf-8")).hexdigest() != receipt["claim"]["output_hash"]:
        raise Prop1224MaterializerError(
            "predecessor receipt result/output hash is inconsistent"
        )
    try:
        value = json.loads(result)
        canonical_result = canonical_json_bytes(value).decode("utf-8").rstrip("\n")
    except (CampaignIOError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Prop1224MaterializerError("predecessor result is not JSON") from error
    fields = {
        "kind",
        "phase",
        "retained_export_sha256",
        "retained_export_size_bytes",
        "retained_tree_sha256",
        "schema_version",
        "shard_index",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or canonical_result != result
        or value["kind"] != "sparkinterval.azure.prop1224-operational-result.v1"
        or value["phase"] != "mpfr-shards"
        or value["schema_version"] != 1
        or value["shard_index"] != shard_index
        or isinstance(value["retained_export_size_bytes"], bool)
        or not isinstance(value["retained_export_size_bytes"], int)
        or value["retained_export_size_bytes"] < 1
        or SHA256_RE.fullmatch(value["retained_export_sha256"]) is None
        or SHA256_RE.fullmatch(value["retained_tree_sha256"]) is None
    ):
        raise Prop1224MaterializerError("predecessor operational result differs")
    return value


def _predecessor_rows(
    context: azure_portfolio.PortfolioContext,
    factory: Prop1224CPUWorkloadFactory,
    site: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _expected_predecessors(factory)
    provided = {
        (row["group_id"], row["shard_index"]): row
        for row in site["prop1224"]["predecessor_exports"]
    }
    if set(provided) != set(expected):
        raise Prop1224MaterializerError(
            "predecessor exports do not exactly cover the reviewed phase"
        )
    if not expected:
        return []
    state = azure_portfolio.load_state(context)
    group_id = f"{CAMPAIGN_ID}::mpfr-shards"
    group = azure_portfolio._group(context, group_id)
    rows: list[dict[str, Any]] = []
    for _group_id, shard_index in expected:
        predecessor_factory = factory_for_portfolio_group(group, shard_index)
        if predecessor_factory is None or predecessor_factory.terminal:
            raise Prop1224MaterializerError(
                "predecessor is not a reviewed operational Proposition 12.2.4 leaf"
            )
        paths = azure_portfolio._task_paths(context, group_id, shard_index)
        task_id = paths["task_id"].name
        record = state["records"].get(task_id)
        if record is None:
            raise Prop1224MaterializerError("predecessor has no portfolio receipt")
        azure_portfolio._validate_task_record(context, task_id, record)
        if record["stage"] != "verified_receipt_recorded":
            raise Prop1224MaterializerError(
                "predecessor portfolio receipt is incomplete"
            )
        try:
            receipt = load_verified_receipt(
                paths["receipt"], key_manifest=context.verifier_key_manifest
            )
        except Exception as error:
            raise Prop1224MaterializerError(
                f"predecessor receipt failed verification: {error}"
            ) from error
        claim = receipt["claim"]
        if (
            receipt["backend"] != cpu_operator.BACKEND
            or claim["algorithm_id"] != predecessor_factory.algorithm_id
            or claim["algorithm_hash"]
            != hashlib.sha256(
                predecessor_factory.algorithm_definition.encode("utf-8")
            ).hexdigest()
            or claim["parameters_hash"]
            != canonical_sha256(predecessor_factory.parameters)
            or claim["domain_hash"] != canonical_sha256(predecessor_factory.domain)
        ):
            raise Prop1224MaterializerError(
                "predecessor receipt is not the reviewed leaf job"
            )
        result = _operational_result(receipt, shard_index)
        export_pin, export_path = _pin(
            provided[(group_id, shard_index)]["export"],
            f"retained predecessor {group_id}/{shard_index}",
        )
        if (export_pin["sha256"], export_pin["size_bytes"]) != (
            result["retained_export_sha256"],
            result["retained_export_size_bytes"],
        ):
            raise Prop1224MaterializerError(
                "retained predecessor differs from its signed result"
            )
        rows.append(
            {
                "export": export_pin,
                "group_id": group_id,
                "receipt_sha256": receipt["receipt_sha256"],
                "shard_index": shard_index,
                "source_path": export_path,
                "tree_sha256": result["retained_tree_sha256"],
            }
        )
    return rows


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
        raise Prop1224MaterializerError(
            "portfolio group has no closed Proposition 12.2.4 CPU factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise Prop1224MaterializerError(
            "portfolio shard argv differs from the closed factory"
        )
    predecessors = _predecessor_rows(context, factory, site)
    for relative in (*SOURCE_PATHS, *PROFILE_PATHS.values()):
        _source_pin(context, relative)
    issued = cpu_operator.dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    expires = cpu_operator.dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    ttl = int((expires - issued).total_seconds())
    if ttl <= 2 * factory.timeout_seconds + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS:
        raise Prop1224MaterializerError(
            "challenge TTL cannot contain both measured replays and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise Prop1224MaterializerError(
            "materializer output_root must stay outside the repository"
        )
    tools = {name: shutil.which(name, path=FIXED_TOOL_PATH) for name in REQUIRED_BUILD_TOOLS}
    supported = platform.machine() == "x86_64" and all(tools.values())
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": "reviewed_prop1224_materialization_plan_not_execution_evidence",
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "phase_id": factory.phase_id,
        "predecessor_count": len(predecessors),
        "registered_invocation": factory.registered_invocation,
        "semantic_terminal": factory.terminal,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "tools_if_supported": tools,
        "upstreams": {
            "gmp": _upstream_identity(Path(site["prop1224"]["gmp_source_root"]), "gmp"),
            "mpfr": _upstream_identity(Path(site["prop1224"]["mpfr_source_root"]), "mpfr"),
        },
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _copy_source_tree(source: Path, destination: Path) -> list[Path]:
    copied: list[Path] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise Prop1224MaterializerError("upstream source contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise Prop1224MaterializerError(
                "upstream source contains a special file"
            )
        target = destination / relative
        _copy_exact(path, target, executable=os.access(path, os.X_OK))
        copied.append(target)
    return copied


def _run_build(
    argv: list[str], *, cwd: Path, additions: Mapping[str, str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    environment = {**BUILD_ENVIRONMENT, **(dict(additions) if additions else {})}
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
        raise Prop1224MaterializerError(
            f"closed GMP/MPFR build failed: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise Prop1224MaterializerError(
            f"closed GMP/MPFR build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": dict(additions) if additions else {},
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _runner_sample(runner: Path) -> dict[str, Any]:
    sample_rank = 3_315_093_776
    completed = subprocess.run(
        [
            str(runner),
            "--rank-lower",
            str(sample_rank),
            "--rank-upper",
            str(sample_rank + 1),
            "--precision-bits",
            "192",
            "--segment-size",
            "250000",
        ],
        cwd=runner.parent,
        env=BUILD_ENVIRONMENT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise Prop1224MaterializerError(
            f"built runner sample failed: {completed.stderr[-2000:]}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise Prop1224MaterializerError(
            "built runner sample did not emit JSON"
        ) from error
    try:
        validate_runner_report(
            report,
            lower=sample_rank,
            upper=sample_rank + 1,
            precision_bits=192,
            mpfr_version="4.2.1",
        )
    except Exception as error:
        raise Prop1224MaterializerError(
            f"built runner sample failed semantic validation: {error}"
        ) from error
    return {
        "kind": "prop1224_mpfr_directed_runner_sample",
        "rank_lower": sample_rank,
        "rank_upper": sample_rank + 1,
        "row_root_sha256": report["row_root_sha256"],
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise Prop1224MaterializerError(
            "Proposition 12.2.4 production package must be built on x86_64"
        )
    tool_paths: dict[str, Path] = {}
    for name in REQUIRED_BUILD_TOOLS:
        found = shutil.which(name, path=FIXED_TOOL_PATH)
        if found is None:
            raise Prop1224MaterializerError(f"closed build requires {name}")
        tool_paths[name] = Path(found).resolve(strict=True)

    gmp_source = Path(site["prop1224"]["gmp_source_root"]).resolve(strict=True)
    mpfr_source = Path(site["prop1224"]["mpfr_source_root"]).resolve(strict=True)
    gmp_identity = _upstream_identity(gmp_source, "gmp")
    mpfr_identity = _upstream_identity(mpfr_source, "mpfr")

    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        if (_file_pin(destination)["sha256"], destination.stat().st_size) != (
            row["sha256"],
            row["size_bytes"],
        ):
            raise Prop1224MaterializerError(
                f"project source changed during copy: {relative}"
            )
        copied[relative] = destination

    upstream_root = artifact_root / ".upstreams"
    gmp_copy = upstream_root / "gmp-6.3.0"
    mpfr_copy = upstream_root / "mpfr-4.2.1"
    _copy_source_tree(gmp_source, gmp_copy)
    _copy_source_tree(mpfr_source, mpfr_copy)
    if _upstream_identity(gmp_copy, "gmp") != gmp_identity:
        raise Prop1224MaterializerError("copied GMP source differs")
    if _upstream_identity(mpfr_copy, "mpfr") != mpfr_identity:
        raise Prop1224MaterializerError("copied MPFR source differs")

    build_root = artifact_root / ".build"
    install_root = build_root / "install"
    gmp_build = build_root / "gmp"
    mpfr_build = build_root / "mpfr"
    gmp_build.mkdir(mode=0o700, parents=True)
    mpfr_build.mkdir(mode=0o700, parents=True)
    prefix_maps = (
        f"{GENERIC_CFLAGS} "
        "-ffile-prefix-map=/=. -fdebug-prefix-map=/=."
    )
    common = {
        "AR": str(tool_paths["ar"]),
        "CC": str(tool_paths["gcc"]),
        "CFLAGS": prefix_maps,
        "CPPFLAGS": prefix_maps,
        "CXX": str(tool_paths["g++"]),
        "CXXFLAGS": f"{prefix_maps} -std=c++20",
        "RANLIB": str(tool_paths["ranlib"]),
    }
    build_steps = [
        _run_build(
            [
                str(gmp_copy / "configure"),
                "--build=x86_64-pc-linux-gnu",
                "--host=x86_64-pc-linux-gnu",
                f"--prefix={install_root}",
                "--disable-shared",
                "--enable-static",
                "--enable-cxx",
                "--enable-fat",
            ],
            cwd=gmp_build,
            additions=common,
        ),
        _run_build(
            [str(tool_paths["make"]), "-j8"],
            cwd=gmp_build,
            additions=common,
        ),
        _run_build(
            [str(tool_paths["make"]), "install"],
            cwd=gmp_build,
            additions=common,
        ),
        _run_build(
            [
                str(mpfr_copy / "configure"),
                "--build=x86_64-pc-linux-gnu",
                "--host=x86_64-pc-linux-gnu",
                f"--prefix={install_root}",
                f"--with-gmp={install_root}",
                "--disable-shared",
                "--enable-static",
            ],
            cwd=mpfr_build,
            additions=common,
        ),
        _run_build(
            [str(tool_paths["make"]), "-j8"],
            cwd=mpfr_build,
            additions=common,
        ),
        _run_build(
            [str(tool_paths["make"]), "install"],
            cwd=mpfr_build,
            additions=common,
        ),
    ]

    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    python_target = artifacts / "python3"
    _copy_exact(tool_paths["python3"], python_target, executable=True)
    runner = artifacts / "tg_prop1224_mpfr_shard"
    compile_argv = [
        str(tool_paths["g++"]),
        "-O3",
        "-std=c++20",
        "-march=x86-64-v2",
        "-mtune=generic",
        "-fno-fast-math",
        "-fno-associative-math",
        "-ffp-contract=off",
        "-frounding-math",
        "-ffile-prefix-map=/=.",
        "-fdebug-prefix-map=/=.",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-Wl,--build-id=none",
        "-I",
        str(artifact_root / "gpu/include"),
        "-I",
        str(install_root / "include"),
        str(copied["reference/tg_prop1224_mpfr_shard.cpp"]),
        str(install_root / "lib/libmpfr.a"),
        str(install_root / "lib/libgmpxx.a"),
        str(install_root / "lib/libgmp.a"),
        "-lm",
        "-o",
        str(runner),
    ]
    build_steps.append(_run_build(compile_argv, cwd=artifact_root))
    build_steps.append(
        _run_build(
            [str(tool_paths["strip"]), "--strip-all", str(runner)],
            cwd=artifact_root,
        )
    )
    runner.chmod(0o500)
    _require_x86_64_static_elf(runner)
    build_steps.append(_runner_sample(runner))

    gmp_archive = artifact_root / "source/upstreams/gmp-6.3.0.tar"
    mpfr_archive = artifact_root / "source/upstreams/mpfr-4.2.1.tar"
    create_archive(gmp_copy, gmp_archive)
    create_archive(mpfr_copy, mpfr_archive)
    shutil.rmtree(upstream_root)
    shutil.rmtree(build_root)

    runtime = {
        "dynamic_runtime_boundary": (
            "copied CPython executable plus immutable Azure image loader, libc, and stdlib"
        ),
        "gmp": gmp_identity,
        "kind": "sparkinterval.prop1224.image-runtime-closure.v1",
        "mpfr": mpfr_identity,
        "python_executable": {
            **_file_pin(python_target),
            "path": "artifacts/python3",
        },
        "runner_executable": {
            **_file_pin(runner),
            "path": "artifacts/tg_prop1224_mpfr_shard",
        },
        "schema_version": 1,
    }
    python_version = subprocess.run(
        [str(python_target), "-I", "--version"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=BUILD_ENVIRONMENT,
    )
    version_raw = python_version.stdout or python_version.stderr
    if python_version.returncode != 0 or not version_raw.startswith(b"Python 3."):
        raise Prop1224MaterializerError(
            "copied CPython runtime failed its isolated version check"
        )
    runtime["python_version"] = version_raw.decode("ascii", "strict").strip()
    runtime_path = artifact_root / "source/runtime-closure.json"
    _write_bytes(runtime_path, cpu_operator.canonical_json_bytes(runtime))

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
            role="static_prop1224_mpfr_gmp_shard_producer",
            statement_role="producer_executable",
            executable=True,
        ),
        _artifact_record(
            gmp_archive,
            artifact_root,
            role="reviewed_gmp_full_source_archive",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            mpfr_archive,
            artifact_root,
            role="reviewed_mpfr_full_source_archive",
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
    ]
    project_rows = []
    for relative, path in sorted(copied.items()):
        pin = _file_pin(path)
        project_rows.append(
            {"path": relative, "sha256": pin["sha256"], "size_bytes": pin["size_bytes"]}
        )
        records.append(
            _artifact_record(
                path,
                artifact_root,
                role="reviewed_project_source",
                statement_role=None,
                executable=relative.startswith("tools/"),
            )
        )
    source_manifest = {
        "gmp_archive": {
            **_file_pin(gmp_archive),
            "path": gmp_archive.relative_to(artifact_root).as_posix(),
            "tree_sha256": gmp_identity["tree_sha256"],
        },
        "kind": "sparkinterval.prop1224-source-reviewed-closure.v1",
        "mpfr_archive": {
            **_file_pin(mpfr_archive),
            "path": mpfr_archive.relative_to(artifact_root).as_posix(),
            "tree_sha256": mpfr_identity["tree_sha256"],
        },
        "project_files": project_rows,
        "runner_executable_sha256": _file_pin(runner)["sha256"],
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(
        source_manifest_path, cpu_operator.canonical_json_bytes(source_manifest)
    )
    records.append(
        _artifact_record(
            source_manifest_path,
            artifact_root,
            role="reviewed_source_closure_manifest",
            statement_role="source_tree",
            executable=False,
        )
    )
    records.sort(key=lambda row: row["path"])
    compiler = {
        "gcc": {
            **_file_pin(tool_paths["gcc"]),
            "version_line": subprocess.run(
                [str(tool_paths["gcc"]), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.splitlines()[0],
        },
        "gxx": {
            **_file_pin(tool_paths["g++"]),
            "version_line": subprocess.run(
                [str(tool_paths["g++"]), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.splitlines()[0],
        },
    }
    return records, build_steps, {"compiler": compiler, "runtime": runtime}


def _create_handoff(
    artifact_root: Path,
    factory: Prop1224CPUWorkloadFactory,
    predecessors: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    handoff_root = artifact_root / ".handoff"
    handoff_root.mkdir(mode=0o700)
    entries: list[dict[str, Any]] = []
    try:
        for row in predecessors:
            verify_retained_export_archive(
                row["source_path"],
                phase="mpfr-shards",
                shard_index=row["shard_index"],
                tree_sha256=row["tree_sha256"],
            )
            relative = f"exports/{row['shard_index']:05d}.tar"
            destination = handoff_root / relative
            _copy_exact(row["source_path"], destination)
            pin = _file_pin(destination)
            if (pin["sha256"], pin["size_bytes"]) != (
                row["export"]["sha256"],
                row["export"]["size_bytes"],
            ):
                raise Prop1224MaterializerError(
                    "predecessor export changed between audit and handoff copy"
                )
            entries.append(
                {
                    "group_id": row["group_id"],
                    "path": relative,
                    "sha256": pin["sha256"],
                    "shard_index": row["shard_index"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        handoff = {
            "entries": entries,
            "kind": "sparkinterval.azure.prop1224-phase-handoff.v1",
            "phase": factory.phase_id,
            "schema_version": 1,
            "shard_index": factory.shard_index,
        }
        _write_bytes(
            handoff_root / "handoff.json", cpu_operator.canonical_json_bytes(handoff)
        )
        destination = artifact_root / "input/prop1224-phase-handoff.tar"
        create_archive(handoff_root, destination)
        return destination, handoff
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: Prop1224CPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    handoff_path: Path,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = artifact_root / "input/registered-invocation.json"
    _write_bytes(input_path, factory.input_bytes)
    if factory.terminal:
        records.append(
            _artifact_record(
                handoff_path,
                artifact_root,
                role="signed_predecessor_full_campaign_handoff",
                statement_role=None,
                executable=False,
            )
        )
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    input_hash = record_hash(input_path)
    if factory.terminal:
        expected = registered_invocation_expected(REGISTERED_INVOCATION)
        local = expected_registered_hashes()
        if expected != {
            **local,
            "result": "true",
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }:
            raise Prop1224MaterializerError(
                "registered Proposition 12.2.4 source identity changed"
            )
        if (
            registered_invocation_backend(REGISTERED_INVOCATION)
            != cpu_operator.BACKEND
            or algorithm_hash != expected["algorithm_hash"]
            or input_hash != expected["input_hash"]
            or canonical_sha256(factory.parameters) != expected["parameters_hash"]
            or canonical_sha256(factory.domain) != expected["domain_hash"]
        ):
            raise Prop1224MaterializerError(
                "terminal factory differs from the Lean registered invocation"
            )
    records.sort(key=lambda row: row["path"])
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": algorithm_hash,
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
            "canonical_sha256": canonical_sha256(factory.domain),
            "value": factory.domain,
        },
        "gpu_pre_run_gate": None,
        "input_artifact": {
            "path": input_path.relative_to(artifact_root).as_posix(),
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": input_hash,
            "size_bytes": input_path.stat().st_size,
        },
        "job_id": (
            f"tg-prop1224-{factory.phase_id}-{factory.shard_index:05d}-cpu-v1"
        ),
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": (
                "output/registered-result.txt"
                if factory.terminal
                else "output/phase-result.json"
            ),
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


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(context, group_id, shard_index, site)
    if not plan["build_host_supported"]:
        raise Prop1224MaterializerError(
            "this host cannot build the x86_64 GMP/MPFR production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise Prop1224MaterializerError("reviewed factory disappeared")
    predecessors = _predecessor_rows(context, factory, site)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.prop1224-materializing-",
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
        handoff_path, handoff = _create_handoff(
            artifact_root, factory, predecessors
        )
        job = _job(
            context, factory, artifact_root, records, handoff_path, site
        )
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        job_hash = record_hash(job_path)
        transcript_policy = _transcript_policy(site["base"], job_hash, job)
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise Prop1224MaterializerError(
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
            factory=factory,  # type: ignore[arg-type]
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
                "source_reviewed_prop1224_operator_validated_materialization_not_execution_evidence"
            ),
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "handoff": handoff,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "phase_id": factory.phase_id,
            "portfolio_shard_config": _file_pin(shard_path),
            "predecessor_receipts": [
                {
                    "group_id": row["group_id"],
                    "receipt_sha256": row["receipt_sha256"],
                    "shard_index": row["shard_index"],
                }
                for row in predecessors
            ],
            "registered_invocation": factory.registered_invocation,
            "runtime": runtime,
            "schema_version": SCHEMA_VERSION,
            "semantic_terminal": factory.terminal,
            "shard_index": factory.shard_index,
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
        OSError,
        ValueError,
    ) as error:
        raise Prop1224MaterializerError(
            f"Proposition 12.2.4 materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "Prop1224MaterializerError",
    "load_site",
    "materialize",
    "plan_materialization",
]
