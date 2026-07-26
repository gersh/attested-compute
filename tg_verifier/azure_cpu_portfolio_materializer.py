# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize one reviewed TG portfolio CPU shard for the SEV-SNP operator.

This is a build/control-plane boundary, not execution evidence.  It consumes
an immutable shard handoff already retained by :mod:`azure_portfolio`, selects
a closed workload factory, builds a static source/runtime closure with exact
argv arrays, and emits a measured job, deterministic package, transcript
policy, and CPU operator configuration.  It never accepts a workload
executable or shell command from the caller.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier.azure_cpu_workload_factory import (
    ClosedCPUWorkloadFactory,
    factory_for_portfolio_group,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    hash_file_once,
    load_json,
    read_bytes_once,
)
from tg_verifier import azure_portfolio


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for path in (REPOSITORY_ROOT / "azure", REPOSITORY_ROOT / "attestation", REPOSITORY_ROOT / "tools"):
    if str(path) not in os.sys.path:
        os.sys.path.insert(0, str(path))

import cpu_production_orchestrator as cpu_operator  # noqa: E402
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import (  # noqa: E402
    _closure_manifest,
    _elf_has_interp,
    canonical_sha256,
    load_profile,
    validate_job_spec,
)
from generate_trusted_compute_lean import (  # noqa: E402
    registered_invocation_backend,
    registered_invocation_expected,
)


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.portfolio-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.portfolio-materialization.v1"
SITE_FIELDS = {
    "azure",
    "kind",
    "lean_namespace",
    "managed_hsm",
    "output_root",
    "policies",
    "schema_version",
    "worker",
}
SITE_POLICY_FIELDS = {
    "composite_appraisal",
    "evidence_verifier",
    "runner",
    "transcript_policy_id",
}
SITE_WORKER_FIELDS = {"guest_root", "maa_attestation_url"}
PIN_FIELDS = {"path", "sha256", "size_bytes"}
POLICY_PIN_FIELDS = PIN_FIELDS | {"classification", "policy_id"}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
NAMESPACE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
FIXED_COMPILER_SEARCH_PATH = "/usr/bin:/usr/local/bin"
PROFILE_PATHS = {
    "target": "profiles/targets/azure_sevsnp_cpu.json",
    "trust": "profiles/trust/azure_sevsnp_hardware_attested.json",
}


class MaterializerError(RuntimeError):
    """The shard, site, source closure, build, or emitted config failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _absolute(value: Any, what: str, *, exists: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise MaterializerError(f"{what} must be a nonempty absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise MaterializerError(f"{what} must be absolute without '..'")
    if path.is_symlink():
        raise MaterializerError(f"{what} must not be a symbolic link")
    try:
        return path.resolve(strict=exists)
    except OSError as error:
        raise MaterializerError(f"cannot resolve {what}: {error}") from error


def _pin(value: Any, what: str, *, policy: bool = False) -> tuple[dict[str, Any], Path]:
    fields = POLICY_PIN_FIELDS if policy else PIN_FIELDS
    pin = _exact(value, fields, what)
    if policy:
        if pin["classification"] != "production" or not isinstance(
            pin["policy_id"], str
        ) or NAME_RE.fullmatch(pin["policy_id"]) is None:
            raise MaterializerError(f"{what} is not a named production policy")
    path = _absolute(pin["path"], f"{what} path", exists=True)
    if Path(pin["path"]).is_symlink() or not path.is_file():
        raise MaterializerError(f"{what} must be a regular non-symlink file")
    if not isinstance(pin["sha256"], str) or SHA256_RE.fullmatch(pin["sha256"]) is None:
        raise MaterializerError(f"{what} has an invalid digest")
    if (
        isinstance(pin["size_bytes"], bool)
        or not isinstance(pin["size_bytes"], int)
        or not 0 <= pin["size_bytes"] <= 2**63 - 1
    ):
        raise MaterializerError(f"{what} has an invalid size")
    try:
        actual = hash_file_once(path)
    except CampaignIOError as error:
        raise MaterializerError(str(error)) from error
    if actual != (pin["sha256"], pin["size_bytes"]):
        raise MaterializerError(f"{what} differs from its exact pin")
    return pin, path


def _file_pin(path: Path) -> dict[str, Any]:
    digest, size = hash_file_once(path)
    return {"path": str(path), "sha256": digest, "size_bytes": size}


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise MaterializerError(f"cannot load canonical materializer site: {error}") from error
    site = _exact(value, SITE_FIELDS, "materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise MaterializerError("unsupported materializer site kind/version")
    if not isinstance(site["lean_namespace"], str) or NAMESPACE_RE.fullmatch(
        site["lean_namespace"]
    ) is None:
        raise MaterializerError("Lean namespace is malformed")
    output_root = _absolute(site["output_root"], "materializer output_root", exists=False)
    if output_root.exists():
        raise MaterializerError("materializer output_root must be fresh")
    policies = _exact(site["policies"], SITE_POLICY_FIELDS, "site policies")
    _pin(policies["runner"], "runner policy", policy=True)
    _pin(policies["composite_appraisal"], "composite appraisal policy", policy=True)
    _pin(policies["evidence_verifier"], "evidence verifier")
    if not isinstance(policies["transcript_policy_id"], str) or NAME_RE.fullmatch(
        policies["transcript_policy_id"]
    ) is None:
        raise MaterializerError("transcript policy id is malformed")
    worker = _exact(site["worker"], SITE_WORKER_FIELDS, "site worker")
    _absolute(worker["guest_root"], "guest root", exists=False)
    if not isinstance(worker["maa_attestation_url"], str):
        raise MaterializerError("worker MAA URL is absent")
    _exact(site["azure"], cpu_operator.AZURE_KEYS, "site Azure settings")
    _exact(site["managed_hsm"], cpu_operator.HSM_KEYS, "site Managed HSM settings")
    return site


def _repository_rows(context: azure_portfolio.PortfolioContext) -> dict[str, dict[str, Any]]:
    rows = context.cluster_manifest["repository_binding"]["files"]
    return {row["path"]: row for row in rows}


def _source_pin(
    context: azure_portfolio.PortfolioContext, relative: str
) -> tuple[dict[str, Any], Path]:
    row = _repository_rows(context).get(relative)
    if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
        raise MaterializerError(
            f"closed workload source is absent from the clean repository closure: {relative}"
        )
    path = (context.repository_root / relative).resolve(strict=True)
    try:
        path.relative_to(context.repository_root)
    except ValueError as error:
        raise MaterializerError(f"closed workload source escapes: {relative}") from error
    if path.is_symlink() or hash_file_once(path) != (row["sha256"], row["size_bytes"]):
        raise MaterializerError(f"closed workload source differs: {relative}")
    return row, path


def _challenge_ttl(challenge: Mapping[str, Any]) -> int:
    try:
        issued = dt.datetime.strptime(
            challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=dt.timezone.utc)
        expires = dt.datetime.strptime(
            challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=dt.timezone.utc)
    except (KeyError, TypeError, ValueError) as error:
        raise MaterializerError("portfolio challenge timestamps are malformed") from error
    seconds = int((expires - issued).total_seconds())
    if not 1 <= seconds <= cpu_operator.MAX_CHALLENGE_TTL_SECONDS:
        raise MaterializerError("portfolio challenge TTL is outside the CPU protocol")
    return seconds


def _load_handoff(
    context: azure_portfolio.PortfolioContext, group_id: str, shard_index: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path]:
    # load_state replays every immutable portfolio record and recomputes each
    # shard config from the pinned plan before we inspect this one.
    state = azure_portfolio.load_state(context)
    group = azure_portfolio._group(context, group_id)
    if isinstance(shard_index, bool) or not isinstance(shard_index, int) or not (
        0 <= shard_index < group["shard_count"]
    ):
        raise MaterializerError("shard index is outside the reviewed group")
    paths = azure_portfolio._task_paths(context, group_id, shard_index)
    task_id = paths["task_id"].name
    record = state["records"].get(task_id)
    if record is None:
        raise MaterializerError("portfolio shard has not been prepared")
    azure_portfolio._validate_task_record(context, task_id, record)
    if record["stage"] != "challenge_created":
        raise MaterializerError("portfolio shard already has a recorded receipt")
    shard = load_json(paths["config"], require_canonical=True)
    challenge = load_json(paths["challenge"], require_canonical=True)
    return group, shard, challenge, paths["config"], paths["challenge"]


def plan_materialization(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the complete handoff and return a non-executing build plan."""

    group, shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group)
    if factory is None:
        raise MaterializerError("portfolio group has no closed CPU workload factory")
    binding = shard.get("semantic_binding")
    if not isinstance(binding, dict) or binding.get("registered_invocation") != (
        factory.registered_invocation
    ):
        raise MaterializerError("shard does not bind the factory's registered invocation")
    expected_environment = sorted(
        {"TG_CXX", "TG_PYTHON", "TG_REPOSITORY", "TG_RUN_ROOT"}
    )
    if shard.get("argv") != list(factory.portfolio_argv) or shard.get(
        "required_environment"
    ) != expected_environment:
        raise MaterializerError("shard argv/placeholders differ from the closed factory")
    registered = registered_invocation_expected(factory.registered_invocation)
    if registered_invocation_backend(factory.registered_invocation) != cpu_operator.BACKEND:
        raise MaterializerError("factory invocation is not registered for the CPU backend")
    source_rows = [_source_pin(context, relative)[0] for relative in factory.source_paths]
    for relative in PROFILE_PATHS.values():
        _source_pin(context, relative)
    ttl = _challenge_ttl(challenge)
    if ttl <= factory.timeout_seconds + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS:
        raise MaterializerError(
            "portfolio challenge TTL cannot contain the closed workload timeout and "
            "evidence-collection margin"
        )
    output_root = _absolute(site["output_root"], "materializer output_root", exists=False)
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise MaterializerError("materializer output_root must stay outside the repository")
    compiler = shutil.which("g++", path=FIXED_COMPILER_SEARCH_PATH)
    compiler_path = Path(compiler).resolve(strict=True) if compiler else None
    build_host_supported = (
        platform.machine() == "x86_64"
        and compiler_path is not None
        and compiler_path.is_file()
        and os.access(compiler_path, os.X_OK)
    )
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": build_host_supported,
        "challenge": {
            "campaign_id": challenge["campaign_id"],
            "nonce": challenge["nonce"],
            "path": str(challenge_path),
            "sha256": record_hash(challenge_path),
            "shard_index": challenge["shard_index"],
            "ttl_seconds": ttl,
        },
        "classification": "reviewed_materialization_plan_not_execution_evidence",
        "compiler_path_if_supported": str(compiler_path) if compiler_path else None,
        "factory_id": factory.factory_id,
        "output_root": str(output_root),
        "portfolio_argv": list(factory.portfolio_argv),
        "portfolio_placeholder_resolution": {
            "TG_CXX": "replaced-by-closed-static-build-step",
            "TG_PYTHON": "eliminated-by-static-measured-supervisor",
            "TG_REPOSITORY": "replaced-by-pinned-repository-source-closure",
            "TG_RUN_ROOT": "replaced-by-fresh-measured-stage-relative-paths",
        },
        "registered_invocation": factory.registered_invocation,
        "registered_invocation_hashes": {
            key: registered[key]
            for key in (
                "algorithm_hash",
                "algorithm_id",
                "domain_hash",
                "input_hash",
                "output_hash",
                "parameters_hash",
            )
        },
        "shard_config": {
            "path": str(shard_path),
            "sha256": record_hash(shard_path),
            "task_id": shard["task_id"],
        },
        "source_closure": source_rows,
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def record_hash(path: Path) -> str:
    return hash_file_once(path)[0]


def _copy_exact(source: Path, destination: Path, *, executable: bool = False) -> None:
    raw = read_bytes_once(source, limit=2**31)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o500 if executable else 0o400,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _run_build(argv: list[str], *, cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
                "SOURCE_DATE_EPOCH": "0",
                "TZ": "UTC",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MaterializerError(f"closed static build failed to complete: {error}") from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise MaterializerError(
            f"closed static build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _artifact_record(
    path: Path, root: Path, *, role: str, statement_role: str | None, executable: bool
) -> dict[str, Any]:
    pin = _file_pin(path)
    return {
        "executable": executable,
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "sha256": pin["sha256"],
        "size_bytes": pin["size_bytes"],
        "statement_role": statement_role,
    }


def _require_x86_64_static_elf(path: Path) -> None:
    raw = read_bytes_once(path, limit=2**31)
    if (
        len(raw) < 20
        or raw[:4] != b"\x7fELF"
        or raw[4] != 2  # ELFCLASS64
        or raw[5] != 1  # little endian
        or int.from_bytes(raw[18:20], "little") != 62  # EM_X86_64
        or _elf_has_interp(path)
    ):
        raise MaterializerError(
            "closed CDEM executable is not static x86_64 ELF"
        )


def _build_static_closure(
    context: azure_portfolio.PortfolioContext,
    factory: ClosedCPUWorkloadFactory,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise MaterializerError(
            "production CPU package must be built on x86_64 for azure_sevsnp_cpu"
        )
    compiler_name = shutil.which("g++", path=FIXED_COMPILER_SEARCH_PATH)
    if compiler_name is None:
        raise MaterializerError("closed factory requires g++ in the fixed system search path")
    compiler = Path(compiler_name).resolve(strict=True)
    compiler_pin = _file_pin(compiler)
    version = subprocess.run(
        [str(compiler), "--version"],
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if version.returncode != 0 or version.stderr or not version.stdout.splitlines():
        raise MaterializerError("closed compiler identity could not be captured")

    copied: dict[str, Path] = {}
    for relative in factory.source_paths:
        _row, source = _source_pin(context, relative)
        destination = artifact_root / "source" / relative
        _copy_exact(source, destination)
        copied[relative] = destination
    include = artifact_root / "source/gpu/include"
    outputs = {
        "producer": artifact_root / "artifacts/tg_cdem_abel",
        "replayer": artifact_root / "artifacts/tg_cdem_abel_chunk_replay",
        "supervisor": artifact_root / "artifacts/tg_cdem_abel_measured_workload",
    }
    outputs["producer"].parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    common = [str(compiler), "-O3", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-static"]
    build_steps = [
        _run_build(
            common
            + [
                "-fopenmp",
                "-pthread",
                "-I",
                str(include),
                str(copied["reference/tg_cdem_abel.cpp"]),
                "-o",
                str(outputs["producer"]),
            ],
            cwd=artifact_root,
        ),
        _run_build(
            common
            + [
                str(copied["reference/tg_cdem_abel_chunk_replay.cpp"]),
                "-o",
                str(outputs["replayer"]),
            ],
            cwd=artifact_root,
        ),
        _run_build(
            common
            + [
                "-pthread",
                "-I",
                str(include),
                str(copied["reference/tg_cdem_abel_measured_workload.cpp"]),
                "-o",
                str(outputs["supervisor"]),
            ],
            cwd=artifact_root,
        ),
    ]
    for output in outputs.values():
        output.chmod(0o500)
        _require_x86_64_static_elf(output)
    records = [
        _artifact_record(
            outputs["supervisor"],
            artifact_root,
            role="closed_cdem_measured_supervisor_and_trace_verifier",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            outputs["producer"],
            artifact_root,
            role="cdem_full_source_producer",
            statement_role="producer_executable",
            executable=True,
        ),
        _artifact_record(
            outputs["replayer"],
            artifact_root,
            role="cdem_independent_chunk_replayer",
            statement_role="checker_executable",
            executable=True,
        ),
    ]
    source_manifest_rows = []
    for relative, copied_path in sorted(copied.items()):
        copied_pin = _file_pin(copied_path)
        source_manifest_rows.append(
            {
                "path": relative,
                "sha256": copied_pin["sha256"],
                "size_bytes": copied_pin["size_bytes"],
            }
        )
    source_manifest = {
        "files": source_manifest_rows,
        "kind": "sparkinterval.source-reviewed-closure.v1",
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
    for relative, copied_path in sorted(copied.items()):
        records.append(
            _artifact_record(
                copied_path,
                artifact_root,
                role="reviewed_source",
                statement_role=None,
                executable=False,
            )
        )
    records.sort(key=lambda row: row["path"])
    return records, build_steps, {
        **compiler_pin,
        "version_line": version.stdout.splitlines()[0],
    }


def _write_bytes(path: Path, raw: bytes, *, mode: int = 0o400) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: ClosedCPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    site: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = artifact_root / "input/registered-invocation.json"
    _write_bytes(input_path, factory.input_bytes)
    profile_values: dict[str, dict[str, Any]] = {}
    profile_records: dict[str, dict[str, Any]] = {}
    for kind, relative in PROFILE_PATHS.items():
        _row, source = _source_pin(context, relative)
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        profile_values[kind] = load_profile(destination, kind)
        profile_records[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": profile_values[kind]["profile_id"],
            "sha256": canonical_sha256(profile_values[kind]),
        }
    runner_pin, runner_source = _pin(
        site["policies"]["runner"], "runner policy", policy=True
    )
    runner_path = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_path)
    registered = registered_invocation_expected(factory.registered_invocation)
    algorithm_hash = hashlib.sha256(factory.algorithm_definition.encode("utf-8")).hexdigest()
    if (
        algorithm_hash != registered["algorithm_hash"]
        or hashlib.sha256(factory.input_bytes).hexdigest() != registered["input_hash"]
        or canonical_sha256(factory.parameters) != registered["parameters_hash"]
        or canonical_sha256(factory.domain) != registered["domain_hash"]
        or factory.algorithm_id != registered["algorithm_id"]
    ):
        raise MaterializerError("closed factory differs from the registered Lean invocation")
    closure_hash = canonical_sha256(_closure_manifest(records))
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": algorithm_hash,
        },
        "artifact_closure": {
            "closure_kind": "static_elf_source_reviewed_v1",
            "files": records,
            "manifest_sha256": closure_hash,
        },
        "backend": cpu_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv),
            "cwd": ".",
            "environment": {
                "LANG": "C",
                "LC_ALL": "C",
                "OMP_NUM_THREADS": "64",
                "OMP_PLACES": "cores",
                "OMP_PROC_BIND": "spread",
                "OMP_TARGET_OFFLOAD": "DISABLED",
                "TZ": "UTC",
            },
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
            "sha256": registered["input_hash"],
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": "tg-cdem-table-abel-source-full-cpu-v1",
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
        "runner_policy": {
            "path": runner_path.relative_to(artifact_root).as_posix(),
            "policy_id": runner_pin["policy_id"],
            "sha256": runner_pin["sha256"],
        },
        "schema_version": 1,
        "target_profile": profile_records["target"],
        "tpm_policy": {
            "ak_handle": "0x81000003",
            "bank": "sha256",
            "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": profile_records["trust"],
        "work_trace_contract": {
            "expected_iterations": factory.trace_iterations,
            "format": "challenge_sha256_chain_json_v1",
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": factory.trace_definition,
            "trace_algorithm_sha256": hashlib.sha256(
                factory.trace_definition.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(factory.trace_verifier_argv),
        },
    }
    if factory.retained_artifact_contracts:
        job["retained_artifact_contracts"] = [
            dict(contract) for contract in factory.retained_artifact_contracts
        ]
    validate_job_spec(job)
    return job


def _transcript_policy(
    site: Mapping[str, Any], job_hash: str, job: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "allowed_backends": [cpu_operator.BACKEND],
        "allowed_job_spec_sha256": [job_hash],
        "allowed_runner_policy_sha256": [job["runner_policy"]["sha256"]],
        "allowed_target_profile_sha256": [job["target_profile"]["sha256"]],
        "allowed_trust_profile_sha256": [job["trust_profile"]["sha256"]],
        "classification": "production",
        "kind": "sparkinterval_measured_runner_appraisal_policy",
        "policy_id": site["policies"]["transcript_policy_id"],
        "require_authenticated_hardware_quote": True,
        "required_composite_appraiser_claims": [
            "measured_runner_policy_valid",
            "result_artifact_bound_to_execution",
        ],
        "schema_version": 1,
    }


def _operator_config(
    *,
    site: Mapping[str, Any],
    factory: ClosedCPUWorkloadFactory,
    challenge: Mapping[str, Any],
    challenge_path: Path,
    artifact_root: Path,
    package: Path,
    transcript_policy_path: Path,
) -> dict[str, Any]:
    output_root = artifact_root.parent
    review = output_root / "review"
    handoffs = output_root / "handoffs"
    guest = _absolute(site["worker"]["guest_root"], "guest root", exists=False)
    runner_path = artifact_root / "profiles/runner-policy.json"
    job_path = artifact_root / "job.json"
    transcript_pin = {
        **_file_pin(transcript_policy_path),
        "classification": "production",
        "policy_id": site["policies"]["transcript_policy_id"],
    }
    config = {
        "azure": site["azure"],
        "campaign_id": challenge["campaign_id"],
        "challenge": {
            "mode": "pinned_portfolio_handoff_v1",
            "pin": _file_pin(challenge_path),
            "shard_index": challenge["shard_index"],
        },
        "challenge_ttl_seconds": _challenge_ttl(challenge),
        "handoffs": {
            "returned_certificate_archive": str(handoffs / "returned-certificate.tar"),
            "returned_worker_completion": str(handoffs / "returned-completion.json"),
            "worker_stage_manifest": str(handoffs / "worker-stage.json"),
        },
        "kind": cpu_operator.CONFIG_KIND,
        "lean_review": {
            "namespace": site["lean_namespace"],
            "registered_invocation": factory.registered_invocation,
        },
        "managed_hsm": site["managed_hsm"],
        "outputs": {
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
        },
        "policies": {
            "composite_appraisal": site["policies"]["composite_appraisal"],
            "evidence_verifier": site["policies"]["evidence_verifier"],
            "runner": {
                **_file_pin(runner_path),
                "classification": "production",
                "policy_id": site["policies"]["runner"]["policy_id"],
            },
            "transcript_appraisal": transcript_pin,
        },
        "schema_version": 1,
        "worker": {
            "artifact_root": str(guest / "artifact-root"),
            "certificate_archive": str(guest / "return/certificate.tar"),
            "certificate_package": str(guest / "certificate-package"),
            "challenge": str(guest / "input/challenge.json"),
            "completion_manifest": str(guest / "return/completion.json"),
            "job_spec": str(guest / "artifact-root/job.json"),
            "maa_attestation_url": site["worker"]["maa_attestation_url"],
            "run_package": str(guest / "measured-run"),
            "stage_manifest": str(guest / "input/worker-stage.json"),
            "transcript_appraisal_policy": str(
                guest / "input/transcript-appraisal-production.json"
            ),
            "workload_package": str(guest / "input/workload.tar"),
        },
        "workload": {
            "artifact_root": str(artifact_root),
            "job_spec": _file_pin(job_path),
            "package": _file_pin(package),
        },
    }
    return config


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and atomically publish one operator-validated CPU package."""

    plan = plan_materialization(context, group_id, shard_index, site)
    if not plan["build_host_supported"]:
        raise MaterializerError(
            "this host cannot build the x86_64 static production CPU closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group)
    assert factory is not None
    output_root = _absolute(site["output_root"], "materializer output_root", exists=False)
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.materializing-", dir=output_root.parent
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, compiler = _build_static_closure(
            context, factory, artifact_root
        )
        job = _job(context, factory, artifact_root, records, site)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        job_hash = record_hash(job_path)
        transcript_policy = _transcript_policy(site, job_hash, job)
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise MaterializerError("materializer output_root appeared during build")
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site=site,
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
                "source_reviewed_operator_validated_materialization_not_execution_evidence"
            ),
            "compiler": compiler,
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "portfolio_shard_config": _file_pin(shard_path),
            "registered_invocation": factory.registered_invocation,
            "schema_version": SCHEMA_VERSION,
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
                "path": str(output_root / "cpu-campaign.json"),
            },
            "job_spec": {
                **manifest["job_spec"],
                "path": str(output_root / "artifact-root/job.json"),
            },
            "manifest": str(output_root / "materialization-manifest.json"),
            "package": {
                **manifest["package"],
                "path": str(output_root / "workload.tar"),
            },
        }
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        raise MaterializerError(f"materialization failed closed: {error}") from error
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root)
