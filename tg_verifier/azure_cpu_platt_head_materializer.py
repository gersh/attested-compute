# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the closed Platt-head CPU job for Azure SEV-SNP.

The materializer is a build/control-plane boundary, not execution evidence.  It
accepts only the retained portfolio handoff plus exact local pins for the two
reviewed source trees and the reviewed x86-64 python-flint wheel.  The measured
job itself independently extracts and checks that wheel, performs the complete
indexed-zero replay, emits the literal Q128 table, and replays the retained
evidence in its external work-trace verifier.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_platt_head_workload_factory import (
    PLATT_HEAD_FACTORY,
    RUNTIME_WHEEL_PATH,
    SOURCE_PATHS,
    PlattHeadCPUWorkloadFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
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
from tg_verifier.campaign_io import CampaignIOError, load_json, read_bytes_once
from tg_verifier.python_flint_runtime import (
    GIT_TREE_DOMAIN,
    PythonFlintRuntimeError,
    extract_verified_wheel,
    load_pin as load_python_flint_pin,
    tracked_tree_identity,
    verify_checkout as verify_python_flint_checkout,
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
from fetch_flint_platt import (  # noqa: E402
    FetchFlintError,
    load_pin as load_flint_pin,
    verify as verify_flint_checkout,
)
from generate_trusted_compute_lean import (  # noqa: E402
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, load_profile, validate_job_spec  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.platt-head-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.platt-head-materialization.v1"
SITE_FIELDS = {"base_site", "kind", "platt_head", "schema_version"}
PLATT_HEAD_FIELDS = {
    "flint_source_root",
    "python_flint_source_root",
    "python_flint_wheel",
}
FIXED_TOOL_PATH = "/usr/bin:/bin"
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.platt-head-2e4.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-sha256)\n"
    "step-0=SHA256(step-domain || previous || wheel-sha256 || wheel-tree-sha256)\n"
    "step-1=SHA256(step-domain || previous || retained-archive-sha256 || retained-tree-sha256 || literal-table-sha256)\n"
    "step-2=SHA256(step-domain || previous || result-sha256)\n"
    "verification=pinned-python-flint-replays-count-isolation-q128-table-and-result"
)


class PlattHeadMaterializerError(RuntimeError):
    """A handoff, source/runtime closure, or emitted job failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise PlattHeadMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise PlattHeadMaterializerError(f"{what} must be a non-symlink directory")
    return path


def _flint_identity(checkout: Path) -> dict[str, Any]:
    try:
        pin = load_flint_pin()
        critical = verify_flint_checkout(checkout, pin)
        tree = tracked_tree_identity(checkout)
    except (FetchFlintError, PythonFlintRuntimeError, OSError, ValueError) as error:
        raise PlattHeadMaterializerError(
            f"pinned FLINT checkout failed review: {error}"
        ) from error
    expected = {
        "file_count": pin.get("tracked_file_count"),
        "size_bytes": pin.get("tracked_bytes"),
        "tree_sha256": pin.get("tracked_tree_sha256"),
    }
    if (
        tree != expected
        or pin.get("tracked_tree_hash_domain")
        != GIT_TREE_DOMAIN[:-1].decode("ascii")
    ):
        raise PlattHeadMaterializerError("FLINT tracked source tree differs from its pin")
    return {
        "commit": critical["commit"],
        "tag": critical["tag"],
        **tree,
    }


def _python_flint_identity(checkout: Path) -> dict[str, Any]:
    try:
        return verify_python_flint_checkout(checkout, load_python_flint_pin())
    except (PythonFlintRuntimeError, OSError, ValueError) as error:
        raise PlattHeadMaterializerError(
            f"pinned python-flint checkout failed review: {error}"
        ) from error


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PlattHeadMaterializerError(
            f"cannot load canonical Platt-head materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "Platt-head materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise PlattHeadMaterializerError(
            "unsupported Platt-head materializer site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise PlattHeadMaterializerError(str(error)) from error
    inputs = _exact(site["platt_head"], PLATT_HEAD_FIELDS, "Platt-head inputs")
    flint = _directory(inputs["flint_source_root"], "FLINT source root")
    python_flint = _directory(
        inputs["python_flint_source_root"], "python-flint source root"
    )
    _wheel_pin, wheel = _pin(inputs["python_flint_wheel"], "python-flint wheel")
    _flint_identity(flint)
    _python_flint_identity(python_flint)
    try:
        verify_wheel(wheel, load_python_flint_pin())
    except PythonFlintRuntimeError as error:
        raise PlattHeadMaterializerError(str(error)) from error
    return {"base": base, "platt_head": inputs, "site_pin": _file_pin(path)}


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
        raise PlattHeadMaterializerError(
            "portfolio group has no closed Platt-head CPU factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise PlattHeadMaterializerError(
            "portfolio shard argv differs from the closed Platt-head factory"
        )
    registered = registered_invocation_expected(factory.registered_invocation)
    if registered_invocation_backend(factory.registered_invocation) != cpu_operator.BACKEND:
        raise PlattHeadMaterializerError(
            "Platt-head invocation is not registered for the CPU backend"
        )
    local = expected_registered_hashes()
    for key, value in local.items():
        if registered.get(key) != value:
            raise PlattHeadMaterializerError(
                f"registered Platt-head {key} differs from the closed factory"
            )
    if registered.get("result") != "true":
        raise PlattHeadMaterializerError("registered Platt-head result is not literal true")
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
        raise PlattHeadMaterializerError(
            "challenge TTL cannot contain the Platt-head job and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise PlattHeadMaterializerError(
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
    wheel = Path(site["platt_head"]["python_flint_wheel"]["path"])
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": "reviewed_platt_head_materialization_plan_not_execution_evidence",
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
            "flint": _flint_identity(
                Path(site["platt_head"]["flint_source_root"])
            ),
            "python_flint": _python_flint_identity(
                Path(site["platt_head"]["python_flint_source_root"])
            ),
            "runtime_wheel": verify_wheel(wheel, load_python_flint_pin()),
        },
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _tracked_entries(checkout: Path) -> list[tuple[str, bool]]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), "ls-files", "--stage", "-z"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            env={"LANG": "C", "LC_ALL": "C", "PATH": FIXED_TOOL_PATH, "TZ": "UTC"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PlattHeadMaterializerError(
            f"cannot enumerate pinned source tree: {error}"
        ) from error
    if completed.returncode != 0:
        raise PlattHeadMaterializerError("cannot enumerate pinned source tree")
    entries: list[tuple[str, bool]] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, name_raw = raw.split(b"\t", 1)
            mode, _object_id, stage = metadata.decode("ascii").split(" ")
            name = name_raw.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise PlattHeadMaterializerError(
                "pinned source index entry is malformed"
            ) from error
        relative = PurePosixPath(name)
        if (
            stage != "0"
            or mode not in ("100644", "100755")
            or relative.is_absolute()
            or name != relative.as_posix()
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise PlattHeadMaterializerError("pinned source index entry is unsafe")
        entries.append((name, mode == "100755"))
    if entries != sorted(entries) or len(entries) != len(set(entries)):
        raise PlattHeadMaterializerError(
            "pinned source entries are not sorted and unique"
        )
    return entries


def _archive_tracked_source(
    checkout: Path,
    destination: Path,
    temporary: Path,
    expected_identity: Mapping[str, Any],
) -> None:
    root = temporary / destination.stem
    root.mkdir(mode=0o700, parents=True)
    entries = _tracked_entries(checkout)
    for relative, executable in entries:
        source = checkout / relative
        if source.is_symlink() or not source.is_file():
            raise PlattHeadMaterializerError(
                f"pinned source is not a regular file: {relative}"
            )
        _copy_exact(source, root / relative, executable=executable)
    digest = hashlib.sha256(GIT_TREE_DOMAIN)
    total = 0
    for relative, _executable in entries:
        raw = read_bytes_once(root / relative, limit=2**31)
        encoded = relative.encode("utf-8")
        total += len(raw)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    copied_identity = {
        "file_count": len(entries),
        "size_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }
    if copied_identity != {
        key: expected_identity[key]
        for key in ("file_count", "size_bytes", "tree_sha256")
    }:
        raise PlattHeadMaterializerError(
            "copied upstream source tree differs from its reviewed identity"
        )
    create_archive(root, destination)
    shutil.rmtree(root)


def _require_x86_64_shared_objects(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.so")):
        raw = read_bytes_once(path, limit=256 * 1024 * 1024)
        if (
            len(raw) < 20
            or raw[:4] != b"\x7fELF"
            or raw[4] != 2
            or raw[5] != 1
            or int.from_bytes(raw[18:20], "little") != 62
        ):
            raise PlattHeadMaterializerError(
                f"python-flint runtime is not x86-64 ELF: {path.name}"
            )
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    if not rows:
        raise PlattHeadMaterializerError("python-flint wheel contains no shared objects")
    return rows


def _audit_runtime(python: Path, extracted: Path) -> dict[str, Any]:
    script = (
        "import sys;sys.path.insert(0,sys.argv[1]);import flint;"
        "print(flint.__version__);print(flint.__FLINT_VERSION__);"
        "print(flint.__FLINT_RELEASE__)"
    )
    try:
        completed = subprocess.run(
            [str(python), "-I", "-c", script, str(extracted)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": FIXED_TOOL_PATH,
                "PYTHONDONTWRITEBYTECODE": "1",
                "TZ": "UTC",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PlattHeadMaterializerError(
            f"pinned python-flint runtime audit failed: {error}"
        ) from error
    if completed.returncode != 0 or completed.stdout != b"0.9.0\n3.6.0\n30600\n":
        diagnostic = (completed.stderr or completed.stdout)[-2000:].decode(
            "utf-8", "replace"
        )
        raise PlattHeadMaterializerError(
            f"pinned python-flint runtime version audit failed: {diagnostic}"
        )
    return {
        "argv_sha256": canonical_sha256(
            ["artifacts/python3", "-I", "-c", script, "<verified-wheel-root>"]
        ),
        "flint_release": 30_600,
        "flint_version": "3.6.0",
        "python_flint_version": "0.9.0",
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _build_python_flint_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    inputs: Mapping[str, Any],
    artifact_root: Path,
    *,
    source_paths: tuple[str, ...],
    family: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise PlattHeadMaterializerError(
            "Platt-head production package must be built on x86_64"
        )
    python_name = shutil.which("python3", path=FIXED_TOOL_PATH)
    if python_name is None:
        raise PlattHeadMaterializerError("Platt-head closure requires /usr/bin python3")
    python_source = Path(python_name).resolve(strict=True)
    flint_root = Path(inputs["flint_source_root"]).resolve(strict=True)
    python_flint_root = Path(
        inputs["python_flint_source_root"]
    ).resolve(strict=True)
    flint_identity = _flint_identity(flint_root)
    python_flint_identity = _python_flint_identity(python_flint_root)
    _wheel_pin, wheel_source = _pin(
        inputs["python_flint_wheel"], "python-flint wheel"
    )
    python_pin = load_python_flint_pin()
    verify_wheel(wheel_source, python_pin)

    copied: dict[str, Path] = {}
    for relative in source_paths:
        _row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        copied[relative] = destination

    python_target = artifact_root / "artifacts/python3"
    python_source_pin = _file_pin(python_source)
    _copy_exact(python_source, python_target, executable=True)
    python_target_pin = _file_pin(python_target)
    if (
        python_target_pin["sha256"] != python_source_pin["sha256"]
        or python_target_pin["size_bytes"] != python_source_pin["size_bytes"]
    ):
        raise PlattHeadMaterializerError(
            "copied CPython executable differs from its build-host source"
        )
    wheel_target = artifact_root / RUNTIME_WHEEL_PATH
    _copy_exact(wheel_source, wheel_target)

    build_root = artifact_root / ".materializer-build"
    build_root.mkdir(mode=0o700)
    extracted = build_root / "python-flint-runtime"
    try:
        extracted_identity = extract_verified_wheel(wheel_target, extracted, python_pin)
        shared_objects = _require_x86_64_shared_objects(extracted)
        runtime_audit = _audit_runtime(python_target, extracted)
        upstream_directory = artifact_root / "source/upstreams"
        upstream_directory.mkdir(mode=0o700, parents=True)
        flint_archive = upstream_directory / "flint-3.6.0.tar"
        python_flint_archive = upstream_directory / "python-flint-0.9.0.tar"
        _archive_tracked_source(
            flint_root, flint_archive, build_root, flint_identity
        )
        _archive_tracked_source(
            python_flint_root,
            python_flint_archive,
            build_root,
            python_flint_identity,
        )
    finally:
        if build_root.exists():
            for path in sorted(build_root.rglob("*"), reverse=True):
                try:
                    path.chmod(0o700 if path.is_dir() else 0o600)
                except OSError:
                    pass
            shutil.rmtree(build_root, ignore_errors=True)

    if _flint_identity(flint_root) != flint_identity:
        raise PlattHeadMaterializerError("FLINT checkout changed during materialization")
    if _python_flint_identity(python_flint_root) != python_flint_identity:
        raise PlattHeadMaterializerError(
            "python-flint checkout changed during materialization"
        )
    runtime_manifest = {
        "dynamic_runtime_boundary": (
            "copied CPython executable plus immutable Azure image loader, libc, and stdlib"
        ),
        "flint_source": {
            **flint_identity,
            "archive": {
                **_file_pin(flint_archive),
                "path": flint_archive.relative_to(artifact_root).as_posix(),
            },
        },
        "kind": f"sparkinterval.{family}.image-runtime-closure.v1",
        "python_executable": {
            **_file_pin(python_target),
            "path": python_target.relative_to(artifact_root).as_posix(),
        },
        "python_flint_source": {
            **python_flint_identity,
            "archive": {
                **_file_pin(python_flint_archive),
                "path": python_flint_archive.relative_to(artifact_root).as_posix(),
            },
        },
        "runtime_audit": runtime_audit,
        "runtime_shared_objects": shared_objects,
        "runtime_wheel": {
            **verify_wheel(wheel_target, python_pin),
            "extracted": {
                "file_count": extracted_identity["file_count"],
                "size_bytes": extracted_identity["size_bytes"],
                "tree_sha256": extracted_identity["tree_sha256"],
            },
            "path": wheel_target.relative_to(artifact_root).as_posix(),
        },
        "schema_version": 1,
    }
    runtime_path = artifact_root / "source/runtime-closure.json"
    _write_bytes(runtime_path, cpu_operator.canonical_json_bytes(runtime_manifest))

    records = [
        _artifact_record(
            python_target,
            artifact_root,
            role="image_bound_cpython_host",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            wheel_target,
            artifact_root,
            role="pinned_python_flint_runtime_wheel",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            flint_archive,
            artifact_root,
            role="reviewed_flint_full_source_archive",
            statement_role=None,
            executable=False,
        ),
        _artifact_record(
            python_flint_archive,
            artifact_root,
            role="reviewed_python_flint_full_source_archive",
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
    source_rows = []
    for relative, path in sorted(copied.items()):
        pin = _file_pin(path)
        source_rows.append(
            {
                "path": relative,
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
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
        "flint_archive": {
            **_file_pin(flint_archive),
            "path": flint_archive.relative_to(artifact_root).as_posix(),
            "tree_sha256": flint_identity["tree_sha256"],
        },
        "kind": f"sparkinterval.{family}-source-reviewed-closure.v1",
        "project_files": source_rows,
        "python_flint_archive": {
            **_file_pin(python_flint_archive),
            "path": python_flint_archive.relative_to(artifact_root).as_posix(),
            "tree_sha256": python_flint_identity["tree_sha256"],
        },
        "runtime_wheel": {
            **_file_pin(wheel_target),
            "path": wheel_target.relative_to(artifact_root).as_posix(),
            "extracted_tree_sha256": extracted_identity["tree_sha256"],
        },
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
    build_steps = [
        {
            "kind": "reviewed_full_source_archives",
            "flint_tree_sha256": flint_identity["tree_sha256"],
            "python_flint_tree_sha256": python_flint_identity["tree_sha256"],
        },
        {
            "kind": "x86_64_runtime_import_audit",
            **runtime_audit,
            "wheel_tree_sha256": extracted_identity["tree_sha256"],
        },
    ]
    runtime = {
        **python_source_pin,
        "extracted_wheel_tree_sha256": extracted_identity["tree_sha256"],
        "python_version": subprocess.run(
            [str(python_source), "-I", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip(),
        "shared_object_count": len(shared_objects),
        "wheel_sha256": _file_pin(wheel_target)["sha256"],
    }
    return records, build_steps, runtime


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return _build_python_flint_runtime_closure(
        context,
        site["platt_head"],
        artifact_root,
        source_paths=SOURCE_PATHS,
        family="platt-head",
    )


def _profile_and_policy_records(
    context: azure_portfolio.PortfolioContext,
    artifact_root: Path,
    site: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    profile_records: dict[str, dict[str, Any]] = {}
    for kind, relative in PROFILE_PATHS.items():
        _row, source = _source_pin(context, relative)
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        value = load_profile(destination, kind)
        profile_records[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": value["profile_id"],
            "sha256": canonical_sha256(value),
        }
    runner_pin, runner_source = _pin(
        site["base"]["policies"]["runner"], "runner policy", policy=True
    )
    runner_path = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_path)
    return profile_records, {
        "path": runner_path.relative_to(artifact_root).as_posix(),
        "policy_id": runner_pin["policy_id"],
        "sha256": runner_pin["sha256"],
    }


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: PlattHeadCPUWorkloadFactory,
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
        raise PlattHeadMaterializerError(
            "closed Platt-head factory differs from the Lean invocation"
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
            "environment": {
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
            },
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
        "job_id": "tg-platt-head-2e4-cpu-v1",
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
        raise PlattHeadMaterializerError(
            "this host cannot build the x86_64 Platt-head production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise PlattHeadMaterializerError("reviewed Platt-head factory disappeared")
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.platt-head-materializing-",
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
            raise PlattHeadMaterializerError(
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
                "source_reviewed_platt_head_operator_validated_materialization_not_execution_evidence"
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
        PythonFlintRuntimeError,
        OSError,
        ValueError,
    ) as error:
        raise PlattHeadMaterializerError(
            f"Platt-head materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "MANIFEST_KIND",
    "PLATT_HEAD_FACTORY",
    "PlattHeadMaterializerError",
    "SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
