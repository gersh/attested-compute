# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Portable, fail-closed cluster plans for the thirteen TG campaigns.

The cluster layer deliberately does not reinterpret a successful process as a
mathematical certificate.  It only binds each named full-source entry point to
an execution class, a workspace, and a Slurm job.  Atom-specific supervisors
remain responsible for authenticated checkpoints and semantic replay.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
MANIFEST_KIND = "sparkinterval.tg.h100_cluster_manifest.v1"
ATTEMPT_KIND = "sparkinterval.tg.h100_cluster_attempt.v1"
ATOM_IDS = (
    "ch25-a7-boundary",
    "ch25-psi-1e13",
    "platt-head-2e4",
    "platt-trudgian-rh-3e12",
    "helfgott-prop-12-2-4",
    "cdem-squarefree",
    "cdem-table-abel",
    "mertens-hurst",
    "ramare-zuniga-lemma-6-2",
    "helfgott-platt-theorem-4-1",
    "platt-dirichlet-theorem-7-1",
    "platt-little-mertens-2-11",
    "platt-little-mertens-stronger",
)
ZETA_Q1_ATOM = "platt-trudgian-rh-3e12"
DIRICHLET_ATOM = "platt-dirichlet-theorem-7-1"
BACKEND_CLASSES = frozenset(
    {"h100_cuda", "cpu_flint_sidecar", "cpu_exact_sidecar"}
)
PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
ATOM_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
HEX_OBJECT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ClusterPlanError(ValueError):
    """A deployment manifest or runtime binding failed closed."""


@dataclass(frozen=True)
class Workload:
    atom_id: str
    backend_class: str
    command: tuple[str, ...]
    cpus: int
    memory_gib: int
    walltime: str
    resume_mode: str
    partition_mode: str
    scalability: str
    feasibility: str
    dependencies: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    postcheck: tuple[str, ...] = ()


def _python_tool(name: str) -> str:
    return f"${{TG_REPOSITORY}}/tools/{name}"


def _workspace(atom_id: str) -> str:
    return f"${{TG_RUN_ROOT}}/{atom_id}"


def _mobius(atom_id: str, target: str, segment_count: int) -> tuple[str, ...]:
    return (
        "${TG_PYTHON}",
        _python_tool("tg_mobius_campaign.py"),
        "run",
        "--runner",
        "${TG_H100_BUILD}/sparkinterval-h100-tg-mobius-segment",
        "--output-dir",
        _workspace(atom_id),
        "--target",
        target,
        "--segment-count",
        str(segment_count),
        "--device",
        "0",
    )


# These are literal full-source entry points.  Bounded references, --max-*
# switches, and sample modes are intentionally absent.
WORKLOADS = (
    Workload(
        "ch25-a7-boundary",
        "cpu_flint_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_verify.py"),
            "replay-a7-flint",
            "${TG_A7_TRANSCRIPT}",
        ),
        8,
        32,
        "12:00:00",
        "idempotent_replay",
        "single_full_source_replay",
        "not_parallelized",
        "feasible once the exact retained boundary transcript is supplied",
        required_artifacts=("${TG_A7_TRANSCRIPT}",),
    ),
    Workload(
        "ch25-psi-1e13",
        "cpu_exact_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_psi_campaign.py"),
            "run",
            _workspace("ch25-psi-1e13"),
            "--chunk-span",
            "1000000",
            "--segment-size",
            "1000000",
        ),
        32,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "linear_serial_prefix",
        "not practically scalable: the Python stream reaches 10^13 and sees hundreds of billions of primes",
    ),
    Workload(
        "platt-head-2e4",
        "cpu_flint_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_zeta_campaign.py"),
            "full",
            _workspace("platt-head-2e4"),
            "--profile",
            "platt-head-2e4",
            "--batch-size",
            "4096",
            "--precision-bits",
            "96",
        ),
        16,
        64,
        "1-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "bounded_memory_serial_batches",
        "practical CPU/FLINT sidecar (22492 indexed positive zeros)",
    ),
    Workload(
        ZETA_Q1_ATOM,
        "cpu_flint_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_zeta_campaign.py"),
            "full",
            _workspace(ZETA_Q1_ATOM),
            "--profile",
            ZETA_Q1_ATOM,
            "--batch-size",
            "4096",
            "--precision-bits",
            "96",
        ),
        32,
        256,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "linear_serial_zero_isolation",
        "prohibitive in the present FLINT implementation: more than twelve trillion indexed zero records",
    ),
    Workload(
        "helfgott-prop-12-2-4",
        "cpu_exact_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_prop1224_campaign.py"),
            "run",
            _workspace("helfgott-prop-12-2-4"),
        ),
        32,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "linear_serial_q_windows",
        "prohibitively slow in Python over 3389047618 admissible q rows",
    ),
    Workload(
        "cdem-squarefree",
        "h100_cuda",
        _mobius("cdem-squarefree", "squarefree", 100_000_000),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "algorithmically prohibitive: a gap-free linear prefix through 10^16",
    ),
    Workload(
        "cdem-table-abel",
        "cpu_exact_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_verify.py"),
            "run-cdem-abel-full",
            "${TG_REPOSITORY}/reference/tg_cdem_abel.cpp",
            "--replay-source",
            "${TG_REPOSITORY}/reference/tg_cdem_abel_chunk_replay.cpp",
            "--compiler",
            "${TG_CXX}",
            "--threads",
            "64",
            "--workers",
            "64",
            "--max-seconds",
            "86400",
            "--chunk-max-seconds",
            "3600",
            "--transcript-output",
            "${TG_RUN_ROOT}/cdem-table-abel/transcript.txt",
        ),
        64,
        256,
        "2-00:00:00",
        "restart_current_full_scan",
        "single_openmp_scan",
        "one_node_openmp",
        "finite five-billion-step OpenMP scan; no production checkpoint adapter",
    ),
    Workload(
        "mertens-hurst",
        "h100_cuda",
        _mobius("mertens-hurst", "hurst", 100_000_000),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "algorithmically prohibitive: a gap-free linear Mertens prefix through 10^16",
    ),
    Workload(
        "ramare-zuniga-lemma-6-2",
        "h100_cuda",
        (
            "${TG_PYTHON}",
            _python_tool("tg_r2star_campaign.py"),
            "run",
            "--runner",
            "${TG_H100_BUILD}/sparkinterval-h100-tg-r2star-chunk",
            "--output-dir",
            _workspace("ramare-zuniga-lemma-6-2"),
            "--segment-count",
            "1000000",
            "--device",
            "0",
        ),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "large but direct: a 21-billion-row exact prefix chain",
    ),
    Workload(
        "helfgott-platt-theorem-4-1",
        "cpu_exact_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_goldbach_campaign.py"),
            "full",
            _workspace("helfgott-platt-theorem-4-1"),
            "--general-prime-producer",
            "${TG_REPOSITORY}/tools/tg_pocklington_producer.py",
        ),
        64,
        256,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "literal_binary_goldbach_scan",
        "computationally astronomical: checks roughly two quintillion even inputs before the ladder",
    ),
    Workload(
        DIRICHLET_ATOM,
        "cpu_flint_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_dirichlet_campaign.py"),
            "source",
            _workspace(DIRICHLET_ATOM),
            "--q1-zeta-final",
            f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
            "--characters-per-chunk",
            "1",
        ),
        32,
        256,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "raw_l_contour_per_character",
        "wired but unscaled: 29565923837 primitive characters and no fast Platt lattice-FFT implementation",
        dependencies=(ZETA_Q1_ATOM,),
        required_artifacts=(f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",),
        postcheck=(
            "${TG_PYTHON}",
            _python_tool("tg_dirichlet_campaign.py"),
            "verify-source",
            _workspace(DIRICHLET_ATOM),
            "--q1-zeta-final",
            f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
        ),
    ),
    Workload(
        "platt-little-mertens-2-11",
        "h100_cuda",
        _mobius("platt-little-mertens-2-11", "2-11", 100_000_000),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "large linear exact prefix through 10^12; resumable but not multi-node sharded",
    ),
    Workload(
        "platt-little-mertens-stronger",
        "h100_cuda",
        _mobius("platt-little-mertens-stronger", "stronger", 100_000_000),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "direct 7727068587-step exact prefix; resumable but not multi-node sharded",
    ),
)
WORKLOADS_BY_ID = {workload.atom_id: workload for workload in WORKLOADS}


def _git(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ClusterPlanError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def inspect_clean_repository(repository: Path) -> dict[str, Any]:
    """Bind a clean checkout and every tracked file by Git and SHA-256."""

    repository = repository.resolve()
    if not repository.is_dir():
        raise ClusterPlanError("repository binding requires an existing directory")
    top = Path(_git(repository, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != repository:
        raise ClusterPlanError("repository path must be the Git worktree root")
    status = _git(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status:
        display = status.replace(b"\x00", b"\n").decode("utf-8", errors="replace")
        raise ClusterPlanError(
            "repository has dirty or untracked files; commit/revert them before "
            f"planning:\n{display.strip()}"
        )
    object_format = _git(repository, "rev-parse", "--show-object-format").decode().strip()
    if object_format not in {"sha1", "sha256"}:
        raise ClusterPlanError(f"unsupported Git object format: {object_format}")
    commit = _git(repository, "rev-parse", "HEAD^{commit}").decode().strip()
    tree = _git(repository, "rev-parse", "HEAD^{tree}").decode().strip()
    raw_paths = _git(repository, "ls-files", "-z")
    paths: list[str] = []
    for raw in raw_paths.split(b"\x00"):
        if not raw:
            continue
        try:
            relative = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ClusterPlanError("tracked paths must be valid UTF-8") from error
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative != path.as_posix():
            raise ClusterPlanError(f"unsafe tracked repository path: {relative}")
        paths.append(relative)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ClusterPlanError("git ls-files did not return unique sorted paths")
    files: list[dict[str, Any]] = []
    for relative in paths:
        path = repository / relative
        if path.is_symlink() or not path.is_file():
            raise ClusterPlanError(
                f"tracked implementation closure entry is not a regular file: {relative}"
            )
        raw = path.read_bytes()
        files.append(
            {
                "path": relative,
                "sha256": sha256_bytes(raw),
                "size_bytes": len(raw),
            }
        )
    # Detect a concurrent modification during hashing, including a new
    # untracked implementation file or index update.
    if _git(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ):
        raise ClusterPlanError("repository changed while its implementation closure was hashed")
    if _git(repository, "rev-parse", "HEAD^{commit}").decode().strip() != commit:
        raise ClusterPlanError("repository HEAD changed while it was hashed")
    if _git(repository, "rev-parse", "HEAD^{tree}").decode().strip() != tree:
        raise ClusterPlanError("repository tree changed while it was hashed")
    return {
        "kind": "sparkinterval.tg.clean_git_repository_closure.v1",
        "coverage": "all_git_tracked_regular_files",
        "clean_worktree": True,
        "untracked_files_absent": True,
        "git_object_format": object_format,
        "git_commit_oid": commit,
        "git_tree_oid": tree,
        "file_count": len(files),
        "files": files,
    }


def validate_repository_binding(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ClusterPlanError("repository binding must be an object")
    expected_fields = {
        "kind",
        "coverage",
        "clean_worktree",
        "untracked_files_absent",
        "git_object_format",
        "git_commit_oid",
        "git_tree_oid",
        "file_count",
        "files",
    }
    if set(value) != expected_fields:
        raise ClusterPlanError("repository binding fields differ")
    if value["kind"] != "sparkinterval.tg.clean_git_repository_closure.v1":
        raise ClusterPlanError("repository binding kind differs")
    if value["coverage"] != "all_git_tracked_regular_files":
        raise ClusterPlanError("repository binding does not cover every tracked file")
    if value["clean_worktree"] is not True or value["untracked_files_absent"] is not True:
        raise ClusterPlanError("repository binding is not explicitly clean")
    if value["git_object_format"] not in {"sha1", "sha256"}:
        raise ClusterPlanError("repository binding has an unsupported Git object format")
    commit = value["git_commit_oid"]
    tree = value["git_tree_oid"]
    if not isinstance(commit, str) or HEX_OBJECT_RE.fullmatch(commit) is None:
        raise ClusterPlanError("repository commit object id is malformed")
    if not isinstance(tree, str) or HEX_OBJECT_RE.fullmatch(tree) is None:
        raise ClusterPlanError("repository tree object id is malformed")
    expected_length = 40 if value["git_object_format"] == "sha1" else 64
    if len(commit) != expected_length or len(tree) != expected_length:
        raise ClusterPlanError("Git object ids disagree with the object format")
    files = value["files"]
    if not isinstance(files, list) or not files:
        raise ClusterPlanError("repository binding files must be a nonempty list")
    paths: list[str] = []
    for index, row in enumerate(files):
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
            raise ClusterPlanError(f"repository file binding {index} is malformed")
        relative = row["path"]
        if not isinstance(relative, str) or not relative:
            raise ClusterPlanError(f"repository file binding {index} has no path")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative != path.as_posix():
            raise ClusterPlanError(f"unsafe repository file binding path: {relative}")
        if not isinstance(row["sha256"], str) or SHA256_RE.fullmatch(row["sha256"]) is None:
            raise ClusterPlanError(f"repository file binding {relative} has bad SHA-256")
        if (
            isinstance(row["size_bytes"], bool)
            or not isinstance(row["size_bytes"], int)
            or row["size_bytes"] < 0
        ):
            raise ClusterPlanError(f"repository file binding {relative} has bad size")
        paths.append(relative)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ClusterPlanError("repository file bindings must be sorted and unique")
    if value["file_count"] != len(files):
        raise ClusterPlanError("repository binding file count differs")
    required_direct_files = {
        "tg_verifier/h100_cluster.py",
        "tools/tg_h100_cluster.py",
        "reference/tg_cdem_abel.cpp",
    }
    for workload in WORKLOADS:
        prefix = "${TG_REPOSITORY}/"
        required_direct_files.update(
            token[len(prefix) :]
            for token in (*workload.command, *workload.postcheck)
            if token.startswith(prefix)
        )
    missing = required_direct_files - set(paths)
    if missing:
        raise ClusterPlanError(
            f"repository closure omits directly referenced implementation files: {sorted(missing)}"
        )
    return value


def verify_repository_binding(repository: Path, expected: object) -> dict[str, Any]:
    expected_binding = validate_repository_binding(expected)
    actual = inspect_clean_repository(repository)
    if actual != expected_binding:
        raise ClusterPlanError(
            "TG_REPOSITORY does not match the clean commit/tree and complete "
            "tracked-file SHA-256 closure in the deployment manifest"
        )
    return actual


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _job_record(workload: Workload) -> dict[str, Any]:
    return {
        "atom_id": workload.atom_id,
        "scope": "full_source",
        "sample": False,
        "backend_class": workload.backend_class,
        "command": list(workload.command),
        "postcheck_command": list(workload.postcheck),
        "dependencies": list(workload.dependencies),
        "required_artifacts": list(workload.required_artifacts),
        "resources": {
            "nodes": 1,
            "tasks": 1,
            "cpus_per_task": workload.cpus,
            "memory_gib": workload.memory_gib,
            "walltime": workload.walltime,
            "h100_gpus": 1 if workload.backend_class == "h100_cuda" else 0,
        },
        "partitioning": {
            "portfolio_shards": 1,
            "intra_atom_mode": workload.partition_mode,
            "parallel_intra_atom_shards": 1,
            "scalability": workload.scalability,
            "reason_parallel_shards_are_one": (
                "The retained atom certificate is a stateful gap-free chain or "
                "single full-source replay; this adapter does not invent unsafe "
                "independent mathematical shards."
            ),
        },
        "resume": {
            "mode": workload.resume_mode,
            "same_workspace_required": True,
            "slurm_resubmission_safe": True,
        },
        "feasibility": workload.feasibility,
        "completion_semantics": (
            "process exit success only; inspect the atom-specific final receipt "
            "and replay it before claiming external evidence"
        ),
    }


def build_manifest(repository_binding: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic site-portable plan for exactly thirteen atoms."""

    binding = validate_repository_binding(dict(repository_binding))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "classification": "full_source_deployment_capability_not_completed_evidence",
        "scope": "all_13_named_ternary_goldbach_external_atoms",
        "sample": False,
        "scheduler_adapter": "slurm",
        "repository_binding": binding,
        "environment": {
            "required": [
                "TG_REPOSITORY",
                "TG_RUN_ROOT",
                "TG_A7_TRANSCRIPT",
                "TG_H100_PARTITION",
                "TG_CPU_FLINT_PARTITION",
                "TG_CPU_EXACT_PARTITION",
            ],
            "optional_defaults": {
                "TG_PYTHON": "python3",
                "TG_CXX": "g++",
                "TG_H100_BUILD": "${TG_REPOSITORY}/build/h100-native",
                "TG_H100_GRES": "gpu:h100:1",
                "TG_SLURM_REQUEUE": "0",
            },
            "optional_site_overrides": [
                "TG_H100_CONSTRAINT",
                "TG_SLURM_ACCOUNT",
                "TG_SLURM_QOS",
                "TG_SLURM_RESERVATION",
                "TG_H100_WALLTIME",
                "TG_CPU_FLINT_WALLTIME",
                "TG_CPU_EXACT_WALLTIME",
            ],
        },
        "portfolio_partitioning": {
            "job_count": 13,
            "concurrent_named_atom_jobs": 12,
            "dependency_delayed_jobs": 1,
            "policy": (
                "partition across named atoms and backend classes; preserve each "
                "atom supervisor's gap-free checkpoint chain"
            ),
        },
        "dependency_edges": [
            {
                "from": ZETA_Q1_ATOM,
                "to": DIRICHLET_ATOM,
                "scheduler_condition": "afterok",
                "artifact": f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
                "meaning": "q=1 zeta prerequisite for the Dirichlet source composition",
            }
        ],
        "jobs": [_job_record(workload) for workload in WORKLOADS],
        "promotion_policy": {
            "sample_receipts_accepted": False,
            "process_exit_promotes_to_external_evidence": False,
            "process_exit_discharges_lean_atom": False,
            "required_scope": "full_source",
        },
    }


def validate_manifest(value: object) -> dict[str, Any]:
    """Require the exact reviewed plan and independently enforce no-sample rules."""

    if not isinstance(value, dict):
        raise ClusterPlanError("cluster manifest must be an object")
    if value.get("sample") is not False:
        raise ClusterPlanError("cluster manifest must be explicitly non-sample")
    jobs = value.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 13:
        raise ClusterPlanError("cluster manifest must contain exactly thirteen jobs")
    ids: list[str] = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise ClusterPlanError(f"job {index} must be an object")
        atom_id = job.get("atom_id")
        if not isinstance(atom_id, str) or ATOM_RE.fullmatch(atom_id) is None:
            raise ClusterPlanError(f"job {index} has an invalid atom id")
        ids.append(atom_id)
        if job.get("scope") != "full_source" or job.get("sample") is not False:
            raise ClusterPlanError(f"{atom_id} is not an explicit full-source job")
        if job.get("backend_class") not in BACKEND_CLASSES:
            raise ClusterPlanError(f"{atom_id} has an invalid backend class")
        command = job.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(token, str) and token for token in command
        ):
            raise ClusterPlanError(f"{atom_id} has an invalid argument vector")
        forbidden = {
            "bounded_sample",
            "sample",
            "--allow-unpinned",
            "--max-chunks",
            "--max-new-chunks",
            "--max-new-ranges",
        }
        if forbidden.intersection(command):
            raise ClusterPlanError(f"{atom_id} command contains a sample/pause switch")
        postcheck = job.get("postcheck_command")
        if not isinstance(postcheck, list) or not all(
            isinstance(token, str) and token for token in postcheck
        ):
            raise ClusterPlanError(f"{atom_id} has an invalid postcheck argument vector")
        if forbidden.intersection(postcheck):
            raise ClusterPlanError(
                f"{atom_id} postcheck contains a sample/pause switch"
            )
    if tuple(ids) != ATOM_IDS or len(set(ids)) != 13:
        raise ClusterPlanError("cluster job ids differ from the reviewed thirteen")
    repository_binding = validate_repository_binding(value.get("repository_binding"))
    expected = build_manifest(repository_binding)
    if value != expected:
        raise ClusterPlanError("cluster manifest differs from the reviewed deterministic plan")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ClusterPlanError("cluster manifest must be a regular non-symlink file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw, parse_constant=lambda text: (_ for _ in ()).throw(
            ClusterPlanError(f"non-finite JSON constant: {text}")
        ))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ClusterPlanError(f"invalid cluster manifest JSON: {error}") from error
    if canonical_json_bytes(value) != raw:
        raise ClusterPlanError("cluster manifest is not canonical JSON")
    return validate_manifest(value)


def _partition_variable(backend_class: str) -> str:
    return {
        "h100_cuda": "TG_H100_PARTITION",
        "cpu_flint_sidecar": "TG_CPU_FLINT_PARTITION",
        "cpu_exact_sidecar": "TG_CPU_EXACT_PARTITION",
    }[backend_class]


def render_slurm_common_script() -> bytes:
    """Return shared fail-closed helpers for generated Slurm submitters."""

    atom_case = "|".join(ATOM_IDS)
    atom_regex = "^(" + "|".join(ATOM_IDS) + ")$"
    text = f'''#!/usr/bin/env bash
# Generated by tools/tg_h100_cluster.py; do not edit.

tg_known_atom() {{
  case "$1" in
    {atom_case}) return 0 ;;
    *) return 1 ;;
  esac
}}

tg_require_submit_environment() {{
  : "${{TG_REPOSITORY:?set TG_REPOSITORY}}"
  : "${{TG_RUN_ROOT:?set TG_RUN_ROOT to persistent shared storage}}"
  case "${{TG_RUN_ROOT}}" in
    /*) ;;
    *) echo "TG_RUN_ROOT must be absolute" >&2; return 64 ;;
  esac
  command -v sbatch >/dev/null || {{ echo "sbatch is required" >&2; return 69; }}
  command -v flock >/dev/null || {{ echo "flock is required" >&2; return 69; }}
  command -v sync >/dev/null || {{ echo "sync is required" >&2; return 69; }}
  mkdir -p "${{TG_RUN_ROOT}}/slurm-logs"
}}

tg_acquire_submission_lock() {{
  exec 9>"${{TG_RUN_ROOT}}/.slurm-submission.lock"
  if ! flock -n 9; then
    echo "another ternary-Goldbach submission process holds the lock" >&2
    return 75
  fi
}}

tg_init_journal() {{
  local journal="$1" tmp
  if [[ -e "${{journal}}" ]]; then
    [[ -f "${{journal}}" && ! -L "${{journal}}" ]] || {{
      echo "unsafe submission journal: ${{journal}}" >&2
      return 74
    }}
    return 0
  fi
  tmp="$(mktemp "${{journal}}.tmp.XXXXXX")"
  printf 'atom_id\tjob_id\tdependency\n' >"${{tmp}}"
  sync -d "${{tmp}}"
  mv "${{tmp}}" "${{journal}}"
  sync -d "${{journal}}"
  sync -d "$(dirname "${{journal}}")"
}}

tg_validate_journal() {{
  local journal="$1" unique_atoms="$2"
  awk -F '\t' -v unique_atoms="${{unique_atoms}}" \
    -v atom_re='{atom_regex}' '
    NR == 1 {{
      if ($0 != "atom_id\tjob_id\tdependency") exit 10
      next
    }}
    NF != 3 {{ exit 11 }}
    $1 !~ atom_re {{ exit 12 }}
    $2 !~ /^[0-9]+$/ {{ exit 13 }}
    $3 != "" && $3 !~ /^[0-9]+$/ {{ exit 14 }}
    unique_atoms == "1" && seen[$1]++ {{ exit 15 }}
    END {{ if (NR < 1) exit 16 }}
  ' "${{journal}}" || {{
    echo "submission journal is malformed: ${{journal}}" >&2
    return 74
  }}
}}

tg_validate_complete_portfolio() {{
  local journal="$1" atom zeta_job dependency count
  tg_validate_journal "${{journal}}" 1 || return $?
  count="$(awk 'END {{ print NR - 1 }}' "${{journal}}")" || return $?
  if [[ "${{count}}" != "13" ]]; then
    echo "submission journal does not contain exactly thirteen jobs" >&2
    return 74
  fi
  for atom in {' '.join(ATOM_IDS)}; do
    tg_journal_job "${{journal}}" "${{atom}}" >/dev/null || {{
      echo "submission journal omits atom: ${{atom}}" >&2
      return 74
    }}
  done
  zeta_job="$(tg_journal_job "${{journal}}" {ZETA_Q1_ATOM})" || return $?
  dependency="$(awk -F '\t' -v atom='{DIRICHLET_ATOM}' \
    '$1 == atom {{ print $3 }}' "${{journal}}")" || return $?
  if [[ -z "${{zeta_job}}" || "${{dependency}}" != "${{zeta_job}}" ]]; then
    echo "Dirichlet journal dependency does not equal the q=1 zeta job id" >&2
    return 74
  fi
}}

tg_journal_job() {{
  local journal="$1" atom="$2"
  awk -F '\t' -v atom="${{atom}}" '$1 == atom {{ value=$2 }} END {{
    if (value == "") exit 1
    print value
  }}' "${{journal}}"
}}

tg_normalize_job_id() {{
  local raw="$1" job_id
  if [[ "${{raw}}" =~ ^([0-9]+)(;[A-Za-z0-9._-]+)?$ ]]; then
    job_id="${{BASH_REMATCH[1]}}"
  else
    echo "sbatch returned a malformed job id: ${{raw}}" >&2
    return 74
  fi
  printf '%s' "${{job_id}}"
}}

tg_record_job() {{
  local journal="$1" atom="$2" job_id="$3" dependency="$4"
  tg_known_atom "${{atom}}" || {{ echo "unknown atom id: ${{atom}}" >&2; return 64; }}
  [[ "${{job_id}}" =~ ^[0-9]+$ ]] || {{ echo "malformed job id" >&2; return 74; }}
  [[ -z "${{dependency}}" || "${{dependency}}" =~ ^[0-9]+$ ]] || {{
    echo "dependency must be a numeric Slurm job id" >&2
    return 64
  }}
  printf '%s\t%s\t%s\n' "${{atom}}" "${{job_id}}" "${{dependency}}" >>"${{journal}}"
  sync -d "${{journal}}"
}}

tg_add_site_args() {{
  local backend="$1" walltime=""
  [[ -z "${{TG_SLURM_ACCOUNT:-}}" ]] || args+=(--account="${{TG_SLURM_ACCOUNT}}")
  [[ -z "${{TG_SLURM_QOS:-}}" ]] || args+=(--qos="${{TG_SLURM_QOS}}")
  [[ -z "${{TG_SLURM_RESERVATION:-}}" ]] || args+=(--reservation="${{TG_SLURM_RESERVATION}}")
  case "${{TG_SLURM_REQUEUE:-0}}" in
    0|"") ;;
    1) args+=(--requeue) ;;
    *) echo "TG_SLURM_REQUEUE must be 0 or 1" >&2; return 64 ;;
  esac
  case "${{backend}}" in
    h100_cuda)
      args+=(--gres="${{TG_H100_GRES:-gpu:h100:1}}")
      [[ -z "${{TG_H100_CONSTRAINT:-}}" ]] || args+=(--constraint="${{TG_H100_CONSTRAINT}}")
      walltime="${{TG_H100_WALLTIME:-}}"
      ;;
    cpu_flint_sidecar) walltime="${{TG_CPU_FLINT_WALLTIME:-}}" ;;
    cpu_exact_sidecar) walltime="${{TG_CPU_EXACT_WALLTIME:-}}" ;;
    *) echo "unknown backend class: ${{backend}}" >&2; return 64 ;;
  esac
  [[ -z "${{walltime}}" ]] || args+=(--time="${{walltime}}")
}}

tg_add_log_args() {{
  local atom="$1"
  args+=(
    --chdir="${{TG_RUN_ROOT}}"
    --output="${{TG_RUN_ROOT}}/slurm-logs/${{atom}}-%j.out"
    --error="${{TG_RUN_ROOT}}/slurm-logs/${{atom}}-%j.err"
  )
}}
'''
    return text.encode("utf-8")


def render_job_script(job: Mapping[str, Any]) -> bytes:
    atom_id = str(job["atom_id"])
    resources = job["resources"]
    gpu_environment = ""
    if resources["h100_gpus"] == 1:
        gpu_environment = """: "${CUDA_VISIBLE_DEVICES:?Slurm must assign exactly one H100}"
case "${CUDA_VISIBLE_DEVICES}" in
  ""|*,*) echo "exactly one H100 must be visible to the strict runner" >&2; exit 69 ;;
esac
"""
    text = f"""#!/usr/bin/env bash
# Generated by tools/tg_h100_cluster.py; do not edit.
#SBATCH --job-name=tg-{atom_id[:38]}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={resources['cpus_per_task']}
#SBATCH --mem={resources['memory_gib']}G
#SBATCH --time={resources['walltime']}
set -euo pipefail
: "${{TG_REPOSITORY:?set TG_REPOSITORY to the reviewed checkout}}"
: "${{TG_RUN_ROOT:?set TG_RUN_ROOT to persistent shared storage}}"
{gpu_environment}
script_dir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
"${{TG_PYTHON:-python3}}" "${{TG_REPOSITORY}}/tools/tg_h100_cluster.py" \\
  execute "${{script_dir}}/../../manifest.json" --atom "{atom_id}"
"""
    return text.encode("utf-8")


def render_submit_script(manifest: Mapping[str, Any]) -> bytes:
    # q=1 is submitted first and Dirichlet is submitted only with its afterok
    # dependency.  All other atoms are independent portfolio shards.
    ordered = [ZETA_Q1_ATOM] + [
        atom for atom in ATOM_IDS if atom not in {ZETA_Q1_ATOM, DIRICHLET_ATOM}
    ]
    class_by_id = {job["atom_id"]: job["backend_class"] for job in manifest["jobs"]}
    lines = [
        "#!/usr/bin/env bash",
        "# Generated by tools/tg_h100_cluster.py; do not edit.",
        "set -euo pipefail",
        ': "${TG_REPOSITORY:?set TG_REPOSITORY}"',
        ': "${TG_RUN_ROOT:?set TG_RUN_ROOT}"',
        ': "${TG_A7_TRANSCRIPT:?set TG_A7_TRANSCRIPT}"',
        ': "${TG_H100_PARTITION:?set TG_H100_PARTITION}"',
        ': "${TG_CPU_FLINT_PARTITION:?set TG_CPU_FLINT_PARTITION}"',
        ': "${TG_CPU_EXACT_PARTITION:?set TG_CPU_EXACT_PARTITION}"',
        'script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'source "${script_dir}/common.sh"',
        "tg_require_submit_environment",
        "tg_acquire_submission_lock",
        'mkdir -p "${TG_RUN_ROOT}"',
        'journal="${TG_RUN_ROOT}/slurm-submission.tsv"',
        'tg_init_journal "${journal}"',
        'tg_validate_journal "${journal}" 1',
        "submit_atom() {",
        '  local atom="$1" partition="$2" backend="$3" dependency="${4:-}" known raw job_id',
        '  if known="$(tg_journal_job "${journal}" "${atom}")"; then',
        '    printf \'%s\' "${known}"',
        "    return 0",
        "  fi",
        '  [[ -z "${dependency}" || "${dependency}" =~ ^[0-9]+$ ]] || {',
        '    echo "dependency must be a numeric Slurm job id" >&2; return 64;',
        "  }",
        "  local args=(--parsable --export=ALL --partition=\"${partition}\")",
        '  tg_add_site_args "${backend}" || return $?',
        '  tg_add_log_args "${atom}" || return $?',
        '  if [[ -n "${dependency}" ]]; then args+=(--dependency="afterok:${dependency}"); fi',
        '  raw="$(sbatch "${args[@]}" "${script_dir}/jobs/${atom}.sbatch")" || return $?',
        '  job_id="$(tg_normalize_job_id "${raw}")" || return $?',
        '  tg_record_job "${journal}" "${atom}" "${job_id}" "${dependency}" || return $?',
        '  printf \'%s\' "${job_id}"',
        "}",
    ]
    for atom_id in ordered:
        var = _partition_variable(class_by_id[atom_id])
        backend = class_by_id[atom_id]
        if atom_id == ZETA_Q1_ATOM:
            lines.append(
                f'zeta_job="$(submit_atom {atom_id} "${{{var}}}" {backend})"'
            )
        else:
            lines.append(
                f'submit_atom {atom_id} "${{{var}}}" {backend} >/dev/null'
            )
    var = _partition_variable(class_by_id[DIRICHLET_ATOM])
    backend = class_by_id[DIRICHLET_ATOM]
    lines.extend(
        [
            f'submit_atom {DIRICHLET_ATOM} "${{{var}}}" {backend} "${{zeta_job}}" >/dev/null',
            'tg_validate_complete_portfolio "${journal}"',
            'echo "submission journal contains all thirteen jobs: ${journal}"',
        ]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_submit_one_script(manifest: Mapping[str, Any]) -> bytes:
    cases = []
    for job in manifest["jobs"]:
        cases.append(
            f"  {job['atom_id']}) partition=\"${{{_partition_variable(job['backend_class'])}:?}}\"; backend={job['backend_class']} ;;"
        )
    text = """#!/usr/bin/env bash
# Generated by tools/tg_h100_cluster.py; do not edit.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 ATOM_ID [AFTEROK_JOB_ID]" >&2
  exit 64
fi
atom="$1"
dependency="${2:-}"
case "${atom}" in
""" + "\n".join(cases) + """
  *) echo "unknown atom id: ${atom}" >&2; exit 64 ;;
esac
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/common.sh"
tg_require_submit_environment
tg_acquire_submission_lock
[[ -z "${dependency}" || "${dependency}" =~ ^[0-9]+$ ]] || {
  echo "AFTEROK_JOB_ID must be numeric" >&2
  exit 64
}
journal="${TG_RUN_ROOT}/slurm-resubmissions.tsv"
tg_init_journal "${journal}"
tg_validate_journal "${journal}" 0
args=(--parsable --export=ALL --partition="${partition}")
tg_add_site_args "${backend}" || exit $?
tg_add_log_args "${atom}" || exit $?
if [[ -n "${dependency}" ]]; then args+=(--dependency="afterok:${dependency}"); fi
raw="$(sbatch "${args[@]}" "${script_dir}/jobs/${atom}.sbatch")" || exit $?
job_id="$(tg_normalize_job_id "${raw}")" || exit $?
tg_record_job "${journal}" "${atom}" "${job_id}" "${dependency}" || exit $?
tg_validate_journal "${journal}" 0
printf '%s\n' "${job_id}"
"""
    return text.encode("utf-8")


def expected_adapter_files(manifest: Mapping[str, Any]) -> dict[str, bytes]:
    files = {
        f"slurm/jobs/{job['atom_id']}.sbatch": render_job_script(job)
        for job in manifest["jobs"]
    }
    files["slurm/submit.sh"] = render_submit_script(manifest)
    files["slurm/submit-one.sh"] = render_submit_one_script(manifest)
    files["slurm/common.sh"] = render_slurm_common_script()
    return files


def _write_deployment_manifest(
    directory: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    manifest = validate_manifest(dict(manifest))
    raw = canonical_json_bytes(manifest)
    if directory.exists() and any(directory.iterdir()):
        raise ClusterPlanError("deployment directory must be absent or empty")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(raw)
    for relative, content in expected_adapter_files(manifest).items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755)
    digest = sha256_bytes(raw)
    (directory / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="ascii"
    )
    return {
        "accepted": True,
        "classification": "portable_full_source_deployment_plan_not_execution",
        "directory": str(directory),
        "manifest_sha256": digest,
        "job_count": 13,
        "sample": False,
        "campaigns_completed": 0,
        "lean_atoms_discharged": 0,
    }


def write_deployment(directory: Path, repository: Path) -> dict[str, Any]:
    """Inspect a clean checkout, bind its complete closure, and write a plan."""

    return _write_deployment_manifest(
        directory, build_manifest(inspect_clean_repository(repository))
    )


def verify_deployment(
    directory: Path, repository: Path | None = None
) -> dict[str, Any]:
    path = directory / "manifest.json"
    manifest = load_manifest(path)
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    expected_digest = f"{digest}  manifest.json\n"
    digest_path = directory / "manifest.sha256"
    if digest_path.is_symlink() or not digest_path.is_file():
        raise ClusterPlanError("manifest SHA-256 sidecar is missing or unsafe")
    if digest_path.read_text(encoding="ascii") != expected_digest:
        raise ClusterPlanError("manifest SHA-256 sidecar differs")
    for relative, expected in expected_adapter_files(manifest).items():
        actual_path = directory / relative
        if actual_path.is_symlink() or not actual_path.is_file():
            raise ClusterPlanError(f"missing or unsafe generated adapter: {relative}")
        if actual_path.read_bytes() != expected:
            raise ClusterPlanError(f"generated adapter differs: {relative}")
    repository_verified = False
    if repository is not None:
        verify_repository_binding(repository, manifest["repository_binding"])
        repository_verified = True
    return {
        "accepted": True,
        "classification": "deployment_plan_and_adapter_integrity_only",
        "manifest_sha256": digest,
        "job_count": 13,
        "sample": False,
        "repository_commit_and_full_file_closure_verified": repository_verified,
        "campaigns_completed": 0,
        "lean_atoms_discharged": 0,
    }


def _expand_token(token: str, environment: Mapping[str, str]) -> str:
    previous = None
    result = token
    for _ in range(4):
        if result == previous:
            break
        previous = result

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            value = environment.get(name)
            if value is None or not value:
                raise ClusterPlanError(f"required runtime variable is unset: {name}")
            if "\x00" in value:
                raise ClusterPlanError(f"runtime variable contains NUL: {name}")
            return value

        result = PLACEHOLDER_RE.sub(replace, result)
    if PLACEHOLDER_RE.search(result):
        raise ClusterPlanError(f"unresolved or recursive placeholder in token: {token}")
    return result


def resolve_command(
    job: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    env = dict(os.environ if environment is None else environment)
    env.setdefault("TG_PYTHON", sys.executable)
    env.setdefault("TG_CXX", "g++")
    repository = env.get("TG_REPOSITORY")
    if repository:
        env.setdefault("TG_H100_BUILD", f"{repository}/build/h100-native")
    return tuple(_expand_token(token, env) for token in job["command"])


def resolve_postcheck_command(
    job: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    env = dict(os.environ if environment is None else environment)
    env.setdefault("TG_PYTHON", sys.executable)
    env.setdefault("TG_CXX", "g++")
    repository = env.get("TG_REPOSITORY")
    if repository:
        env.setdefault("TG_H100_BUILD", f"{repository}/build/h100-native")
    return tuple(
        _expand_token(token, env) for token in job["postcheck_command"]
    )


def _next_attempt_path(log_dir: Path) -> Path:
    for index in range(1, 1_000_000):
        path = log_dir / f"attempt-{index:06d}.json"
        if not path.exists():
            return path
    raise ClusterPlanError("too many retained execution attempts")


def execute_job(
    manifest_path: Path,
    atom_id: str,
    *,
    environment: Mapping[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    try:
        job = next(job for job in manifest["jobs"] if job["atom_id"] == atom_id)
    except StopIteration as error:
        raise ClusterPlanError(f"unknown atom id: {atom_id}") from error
    command = resolve_command(job, environment)
    postcheck_command = resolve_postcheck_command(job, environment)
    env = dict(os.environ if environment is None else environment)
    env.setdefault("TG_PYTHON", sys.executable)
    env.setdefault("TG_CXX", "g++")
    repository = env.get("TG_REPOSITORY")
    run_root_raw = env.get("TG_RUN_ROOT")
    if not repository or not Path(repository).is_absolute() or not Path(repository).is_dir():
        raise ClusterPlanError("TG_REPOSITORY must be an existing absolute directory")
    verify_repository_binding(Path(repository), manifest["repository_binding"])
    if not run_root_raw or not Path(run_root_raw).is_absolute():
        raise ClusterPlanError("TG_RUN_ROOT must be an absolute persistent path")
    run_root = Path(run_root_raw)
    workspace = run_root / atom_id
    workspace.mkdir(parents=True, exist_ok=True)
    for artifact in job["required_artifacts"]:
        resolved = Path(_expand_token(artifact, env))
        if resolved.is_symlink() or not resolved.is_file():
            raise ClusterPlanError(
                f"required dependency artifact is absent or unsafe: {resolved}"
            )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": ATTEMPT_KIND,
        "atom_id": atom_id,
        "scope": "full_source",
        "sample": False,
        "backend_class": job["backend_class"],
        "command": list(command),
        "postcheck_command": list(postcheck_command),
        "dry_run": dry_run,
        "classification": "execution_attempt_not_semantic_certificate",
        "lean_atom_discharged": False,
    }
    if dry_run:
        result["process_exit_code"] = None
        return result
    log_dir = run_root / "cluster-logs" / atom_id
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "latest.stdout"
    stderr_path = log_dir / "latest.stderr"
    completed = subprocess.run(
        command,
        cwd=repository,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    postcheck_completed: subprocess.CompletedProcess[bytes] | None = None
    postcheck_stdout_path = log_dir / "latest.postcheck.stdout"
    postcheck_stderr_path = log_dir / "latest.postcheck.stderr"
    if completed.returncode == 0 and postcheck_command:
        postcheck_completed = subprocess.run(
            postcheck_command,
            cwd=repository,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        postcheck_stdout_path.write_bytes(postcheck_completed.stdout)
        postcheck_stderr_path.write_bytes(postcheck_completed.stderr)
    overall_success = completed.returncode == 0 and (
        postcheck_completed is None or postcheck_completed.returncode == 0
    )
    result.update(
        {
            "process_exit_code": completed.returncode,
            "process_exit_success": completed.returncode == 0,
            "stdout_sha256": sha256_bytes(completed.stdout),
            "stderr_sha256": sha256_bytes(completed.stderr),
            "postcheck_exit_code": (
                None if postcheck_completed is None else postcheck_completed.returncode
            ),
            "postcheck_stdout_sha256": (
                None
                if postcheck_completed is None
                else sha256_bytes(postcheck_completed.stdout)
            ),
            "postcheck_stderr_sha256": (
                None
                if postcheck_completed is None
                else sha256_bytes(postcheck_completed.stderr)
            ),
            "cluster_argument_vectors_all_exited_successfully": overall_success,
            "atom_specific_postcheck_run_by_cluster_layer": bool(postcheck_command),
            "external_evidence_promoted": False,
        }
    )
    attempt_path = _next_attempt_path(log_dir)
    attempt_path.write_bytes(canonical_json_bytes(result))
    if not overall_success:
        failed_code = (
            completed.returncode
            if completed.returncode != 0
            else postcheck_completed.returncode  # type: ignore[union-attr]
        )
        raise ClusterPlanError(
            f"{atom_id} process/check failed with exit code {failed_code}; "
            f"inspect {stderr_path} and resubmit the same atom workspace"
        )
    return result


def capability_report() -> dict[str, Any]:
    counts = {backend: 0 for backend in sorted(BACKEND_CLASSES)}
    for workload in WORKLOADS:
        counts[workload.backend_class] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "cluster_execution_capability_not_completed_evidence",
        "job_count": len(WORKLOADS),
        "backend_counts": counts,
        "q1_zeta_dependency": {
            "producer": ZETA_Q1_ATOM,
            "consumer": DIRICHLET_ATOM,
            "condition": "afterok_and_final_artifact_revalidation",
        },
        "sample_jobs": 0,
        "campaigns_completed": 0,
        "lean_atoms_discharged": 0,
        "jobs": [
            {
                "atom_id": item.atom_id,
                "backend_class": item.backend_class,
                "resume_mode": item.resume_mode,
                "scalability": item.scalability,
                "feasibility": item.feasibility,
            }
            for item in WORKLOADS
        ],
    }
