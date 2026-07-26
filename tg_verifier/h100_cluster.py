# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Portable, fail-closed cluster plans for the TG production campaigns.

The cluster layer deliberately does not reinterpret a successful process as a
mathematical certificate. It binds the thirteen source atoms to ten physical
source-atom campaigns and retains the distinct finite-below-``10^27`` campaign
used by the lowered analytic crossover as an eleventh campaign.  The latter is
not relabelled as the stronger Helfgott--Platt source computation.  Every
campaign has an execution class, workspace, and either a safe one-job adapter
or an explicit manual phase DAG. Atom-specific supervisors remain responsible
for authenticated checkpoints and semantic replay.
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


SCHEMA_VERSION = 3
MANIFEST_KIND = "sparkinterval.tg.h100_cluster_manifest.v3"
ATTEMPT_KIND = "sparkinterval.tg.h100_cluster_attempt.v3"
SOURCE_ATOM_IDS = (
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
GOLDBACH_10POW27_ATOM = "goldbach-finite-below-10pow27"
GOLDBACH_10POW27_CAMPAIGN = "ternary-goldbach-finite-below-10pow27-v1"
ATOM_IDS = (*SOURCE_ATOM_IDS, GOLDBACH_10POW27_ATOM)
ZETA_Q1_ATOM = "platt-trudgian-rh-3e12"
DIRICHLET_ATOM = "platt-dirichlet-theorem-7-1"
HURST_PRIMARY_ATOM = "mertens-hurst"
HURST_ATOMS = (
    HURST_PRIMARY_ATOM,
    "cdem-squarefree",
    "platt-little-mertens-2-11",
    "platt-little-mertens-stronger",
)
BACKEND_CLASSES = frozenset(
    {"h100_cuda", "cpu_flint_sidecar", "cpu_exact_sidecar"}
)
EXECUTION_MODES = frozenset(
    {"single_job", "manual_phase_dag", "shared_certificate_alias"}
)
PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
ATOM_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
HEX_OBJECT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ClusterPlanError(ValueError):
    """A deployment manifest or runtime binding failed closed."""


@dataclass(frozen=True)
class Phase:
    phase_id: str
    command: tuple[str, ...]
    depends_on: tuple[str, ...]
    scheduler_shape: str
    array_size: int = 1
    max_concurrent_tasks: int | None = None
    parallel_workers_safe: bool = False
    completion_artifact: str | None = None
    backend_class: str | None = None
    cpus_per_task: int | None = None


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
    campaign_id: str
    execution_mode: str = "single_job"
    shared_owner_atom: str | None = None
    phase_dag: tuple[Phase, ...] = ()
    dependencies: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    postcheck: tuple[str, ...] = ()


def _python_tool(name: str) -> str:
    return f"${{TG_REPOSITORY}}/tools/{name}"


def _workspace(atom_id: str) -> str:
    return f"${{TG_RUN_ROOT}}/{atom_id}"


def _phase(
    phase_id: str,
    command: tuple[str, ...],
    *,
    depends_on: tuple[str, ...] = (),
    array_size: int = 1,
    max_concurrent_tasks: int | None = None,
    parallel_workers_safe: bool = False,
    completion_artifact: str | None = None,
    backend_class: str | None = None,
    cpus_per_task: int | None = None,
) -> Phase:
    if backend_class is not None and backend_class not in BACKEND_CLASSES:
        raise ClusterPlanError("a phase backend class is not recognized")
    if cpus_per_task is not None and cpus_per_task < 1:
        raise ClusterPlanError("phase cpus_per_task must be positive")
    if max_concurrent_tasks is not None:
        if array_size == 1 or not 1 <= max_concurrent_tasks <= array_size:
            raise ClusterPlanError(
                "an array concurrency limit requires array_size > 1 and must "
                "lie within the array"
            )
        scheduler_shape = (
            f"array[0..{array_size - 1}]%{max_concurrent_tasks}"
        )
    else:
        scheduler_shape = (
            "single" if array_size == 1 else f"array[0..{array_size - 1}]"
        )
    return Phase(
        phase_id=phase_id,
        command=command,
        depends_on=depends_on,
        scheduler_shape=scheduler_shape,
        array_size=array_size,
        max_concurrent_tasks=max_concurrent_tasks,
        parallel_workers_safe=parallel_workers_safe,
        completion_artifact=completion_artifact,
        backend_class=backend_class,
        cpus_per_task=cpus_per_task,
    )


def _psi_phases() -> tuple[Phase, ...]:
    workspace = _workspace("ch25-psi-1e13")
    tool = _python_tool("tg_psi_residual_campaign.py")
    return (
        _phase(
            "initialize",
            (
                "${TG_PYTHON}", tool, "init",
                "--runner", "${TG_TG_BUILD}/sparkinterval-tg-psi-residual-shard",
                "--runner-source", "${TG_REPOSITORY}/reference/tg_psi_residual_shard.cpp",
                "--upstream-manifest", "${TG_REPOSITORY}/specifications/PSI_UPSTREAMS.json",
                "--output-dir", workspace,
            ),
            completion_artifact=f"{workspace}/campaign-config.json",
        ),
        _phase(
            "summary-shards",
            (
                "${TG_PYTHON}", tool, "run", workspace, "summary",
                "--worker-group-index", "${TG_ARRAY_INDEX}",
                "--worker-group-count", "320", "--workers", "40",
            ),
            depends_on=("initialize",),
            array_size=320,
            parallel_workers_safe=True,
        ),
        _phase(
            "reduce-summaries",
            ("${TG_PYTHON}", tool, "reduce", workspace),
            depends_on=("summary-shards",),
            completion_artifact=f"{workspace}/derived-inputs.json",
        ),
        _phase(
            "verify-shards",
            (
                "${TG_PYTHON}", tool, "run", workspace, "verify",
                "--worker-group-index", "${TG_ARRAY_INDEX}",
                "--worker-group-count", "320", "--workers", "40",
            ),
            depends_on=("reduce-summaries",),
            array_size=320,
            parallel_workers_safe=True,
        ),
        _phase(
            "finalize",
            ("${TG_PYTHON}", tool, "finalize", workspace),
            depends_on=("verify-shards",),
            completion_artifact=f"{workspace}/certificate.json",
        ),
        _phase(
            "semantic-replay",
            (
                "${TG_PYTHON}", tool, "verify", workspace,
                "--registered-result-output",
                f"{workspace}/registered-result.txt",
            ),
            depends_on=("finalize",),
            completion_artifact=f"{workspace}/registered-result.txt",
        ),
    )


def _prop1224_phases() -> tuple[Phase, ...]:
    workspace = _workspace("helfgott-prop-12-2-4")
    tool = _python_tool("tg_prop1224_mpfr_campaign.py")
    return (
        _phase(
            "mpfr-shards",
            (
                "${TG_PYTHON}", tool, "run-worker-group",
                "${TG_TG_BUILD}/sparkinterval-tg-prop1224-mpfr-shard",
                workspace, "${TG_ARRAY_INDEX}",
                "--worker-group-count", "4", "--workers", "96",
            ),
            array_size=4,
            parallel_workers_safe=True,
        ),
        _phase(
            "merge-and-verify",
            (
                "${TG_PYTHON}", tool, "verify", workspace,
                "--registered-result-output",
                f"{workspace}/registered-result.txt",
            ),
            depends_on=("mpfr-shards",),
            completion_artifact=f"{workspace}/registered-result.txt",
        ),
    )


def _platt_zeta_phases() -> tuple[Phase, ...]:
    workspace = _workspace(ZETA_Q1_ATOM)
    tool = _python_tool("tg_platt_zeta_campaign.py")
    return (
        _phase(
            "initialize",
            (
                "${TG_PYTHON}", tool, "init", workspace,
                "--runner", "${TG_TG_BUILD}/sparkinterval-tg-platt-zeta-shard",
                "--runner-source", "${TG_REPOSITORY}/reference/tg_platt_zeta_shard.cpp",
                "--upstream-manifest", "${TG_REPOSITORY}/specifications/FLINT_3_6_PLATT_UPSTREAM.json",
            ),
            completion_artifact=f"{workspace}/campaign.json",
        ),
        _phase(
            "exact-multiplicity-count",
            ("${TG_PYTHON}", tool, "count", workspace),
            depends_on=("initialize",),
            completion_artifact=f"{workspace}/count.json",
        ),
        _phase(
            "ordinary-low-index-prefix",
            ("${TG_PYTHON}", tool, "prefix", workspace),
            depends_on=("exact-multiplicity-count",),
            completion_artifact=f"{workspace}/prefix.json",
        ),
        _phase(
            "platt-turing-index-shards",
            ("${TG_PYTHON}", tool, "run-shard", workspace, "${TG_ARRAY_INDEX}"),
            depends_on=("ordinary-low-index-prefix",),
            array_size=1_236_316,
            parallel_workers_safe=True,
        ),
        _phase(
            "finalize-merkle-certificate",
            (
                "${TG_PYTHON}", tool, "finalize", workspace,
                "--registered-result-output",
                f"{workspace}/registered-result.txt",
            ),
            depends_on=("platt-turing-index-shards",),
            completion_artifact=f"{workspace}/registered-result.txt",
        ),
    )


def _hurst_phases() -> tuple[Phase, ...]:
    workspace = _workspace(HURST_PRIMARY_ATOM)
    tool = _python_tool("tg_hurst_residual_campaign.py")
    return (
        _phase(
            "initialize",
            (
                "${TG_PYTHON}", tool, "init",
                "--runner", "${TG_TG_BUILD}/sparkinterval-tg-hurst-residual-shard",
                "--runner-source", "${TG_REPOSITORY}/reference/tg_hurst_residual_shard.cpp",
                "--upstream-manifest", "${TG_REPOSITORY}/specifications/HURST_MERTENS_UPSTREAM.json",
                "--output-dir", workspace,
            ),
            completion_artifact=f"{workspace}/campaign-config.json",
        ),
        _phase(
            "summary-shards",
            (
                "${TG_PYTHON}", tool, "run", workspace, "summary",
                "--worker-group-index", "${TG_ARRAY_INDEX}",
                "--worker-group-count", "320",
                "--workers", "2",
                "--runner-threads", "20",
            ),
            depends_on=("initialize",),
            array_size=320,
            parallel_workers_safe=True,
        ),
        _phase(
            "reduce-summaries",
            ("${TG_PYTHON}", tool, "reduce", workspace),
            depends_on=("summary-shards",),
            completion_artifact=f"{workspace}/derived-inputs.json",
        ),
        _phase(
            "verify-shards",
            (
                "${TG_PYTHON}", tool, "run", workspace, "verify",
                "--worker-group-index", "${TG_ARRAY_INDEX}",
                "--worker-group-count", "320",
                "--workers", "2",
                "--runner-threads", "20",
            ),
            depends_on=("reduce-summaries",),
            array_size=320,
            parallel_workers_safe=True,
        ),
        _phase(
            "finalize-four-residual-certificate",
            ("${TG_PYTHON}", tool, "finalize", workspace),
            depends_on=("verify-shards",),
            completion_artifact=f"{workspace}/certificate.json",
        ),
        _phase(
            "semantic-replay",
            (
                "${TG_PYTHON}", tool, "verify", workspace,
                "--registered-result-output",
                f"{workspace}/registered-result.txt",
            ),
            depends_on=("finalize-four-residual-certificate",),
            completion_artifact=f"{workspace}/registered-result.txt",
        ),
    )


def _goldbach_phases() -> tuple[Phase, ...]:
    workspace = _workspace("helfgott-platt-theorem-4-1")
    binary_tool = _python_tool("tg_goldbach_gpu_campaign.py")
    ladder_tool = _python_tool("tg_goldbach_campaign.py")
    finalizer = _python_tool("tg_goldbach_historical_finalizer.py")
    plan = f"{workspace}/plan.json"
    receipts = f"{workspace}/receipts"
    aggregate = f"{workspace}/aggregate.json"
    ladder = f"{workspace}/ternary-prime-ladder"
    ladder_aggregate = f"{ladder}/ladder-aggregate.json"
    combined = f"{workspace}/combined.json"
    return (
        _phase(
            "create-production-plan",
            (
                "${TG_PYTHON}", binary_tool, "create-production-plan",
                "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
                "--executable", "${TG_GOLDBACH_EXECUTABLE}",
                "--executable-sha256", "${TG_GOLDBACH_EXECUTABLE_SHA256}",
                "--out", plan,
            ),
            completion_artifact=plan,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "initialize-prime-ladder",
            ("${TG_PYTHON}", ladder_tool, "init", ladder),
            completion_artifact=f"{ladder}/manifest.json",
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "h100-8192-groups-of-eight-checkpoint-leaves",
            (
                "${TG_PYTHON}", binary_tool, "run-group", plan, "${TG_ARRAY_INDEX}",
                "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
                "--executable", "${TG_GOLDBACH_EXECUTABLE}",
                "--output-dir", receipts,
                "--cuda-visible-device", "0",
            ),
            depends_on=("create-production-plan",),
            array_size=8_192,
            max_concurrent_tasks=8,
            parallel_workers_safe=True,
            backend_class="h100_cuda",
        ),
        _phase(
            "native-prime-ladder-range-groups",
            (
                "${TG_PYTHON}",
                _python_tool("tg_goldbach_ladder_native.py"),
                "produce-group", ladder,
                "--runner",
                "${TG_TG_BUILD}/sparkinterval-tg-goldbach-ladder-native",
                "--group-index", "${TG_ARRAY_INDEX}",
                "--group-count", "320",
                "--local-workers", "40",
                "--summary",
                f"{ladder}/groups/group-${{TG_ARRAY_INDEX}}.json",
            ),
            depends_on=("initialize-prime-ladder",),
            array_size=320,
            max_concurrent_tasks=8,
            parallel_workers_safe=True,
            backend_class="cpu_exact_sidecar",
            cpus_per_task=40,
        ),
        _phase(
            "aggregate",
            (
                "${TG_PYTHON}", binary_tool, "aggregate", plan,
                "--receipts-dir", receipts, "--out", aggregate,
            ),
            depends_on=("h100-8192-groups-of-eight-checkpoint-leaves",),
            completion_artifact=aggregate,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "binary-semantic-replay",
            (
                "${TG_PYTHON}", binary_tool, "verify", plan, aggregate,
                "--receipts-dir", receipts,
            ),
            depends_on=("aggregate",),
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "reduce-prime-ladder-ranges",
            (
                "${TG_PYTHON}", ladder_tool, "reduce-ranges", ladder,
                "--out", ladder_aggregate,
            ),
            depends_on=("native-prime-ladder-range-groups",),
            completion_artifact=ladder_aggregate,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "combine-binary-and-prime-ladder",
            (
                "${TG_PYTHON}", finalizer, ladder,
                "--ladder-aggregate", ladder_aggregate,
                "--binary-plan", plan,
                "--binary-receipts-dir", receipts,
                "--binary-aggregate", aggregate,
                "--combined-out", combined,
                "--registered-result-output",
                f"{workspace}/registered-result.txt",
            ),
            depends_on=("binary-semantic-replay", "reduce-prime-ladder-ranges"),
            completion_artifact=combined,
            backend_class="cpu_exact_sidecar",
        ),
    )


def _goldbach_10pow27_phases() -> tuple[Phase, ...]:
    """Schedule the lowered finite endpoint without changing source semantics."""

    workspace = _workspace(GOLDBACH_10POW27_ATOM)
    binary_tool = _python_tool("tg_goldbach_gpu_campaign.py")
    campaign_tool = _python_tool("tg_goldbach_10pow27_campaign.py")
    ladder_tool = _python_tool("tg_goldbach_campaign.py")
    native_ladder_tool = _python_tool("tg_goldbach_ladder_native.py")
    finalizer = _python_tool("tg_goldbach_10pow27_finalizer.py")
    plan = f"{workspace}/binary-plan.json"
    receipts = f"{workspace}/binary-receipts"
    aggregate = f"{workspace}/binary-aggregate.json"
    ladder = f"{workspace}/prime-ladder"
    ladder_aggregate = f"{ladder}/ladder-aggregate.json"
    combined = f"{workspace}/combined.json"
    registered_result = f"{workspace}/registered-result.txt"
    return (
        _phase(
            "create-lowered-binary-plan",
            (
                "${TG_PYTHON}", binary_tool, "create-analytic-10pow27-plan",
                "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
                "--executable", "${TG_GOLDBACH_EXECUTABLE}",
                "--executable-sha256", "${TG_GOLDBACH_EXECUTABLE_SHA256}",
                "--out", plan,
            ),
            completion_artifact=plan,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "initialize-lowered-prime-ladder",
            ("${TG_PYTHON}", campaign_tool, "init-ladder", ladder),
            completion_artifact=f"{ladder}/manifest.json",
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "h100-8192-groups-of-eight-lowered-checkpoint-leaves",
            (
                "${TG_PYTHON}", binary_tool, "run-group", plan,
                "${TG_ARRAY_INDEX}",
                "--source-root", "${TG_GOLDBACH_SOURCE_ROOT}",
                "--executable", "${TG_GOLDBACH_EXECUTABLE}",
                "--output-dir", receipts,
                "--cuda-visible-device", "0",
            ),
            depends_on=("create-lowered-binary-plan",),
            array_size=8_192,
            max_concurrent_tasks=8,
            parallel_workers_safe=True,
            backend_class="h100_cuda",
        ),
        _phase(
            "native-lowered-prime-ladder-range-groups",
            (
                "${TG_PYTHON}", native_ladder_tool, "produce-group", ladder,
                "--runner",
                "${TG_TG_BUILD}/sparkinterval-tg-goldbach-ladder-native",
                "--group-index", "${TG_ARRAY_INDEX}",
                "--group-count", "320",
                "--local-workers", "40",
                "--summary", f"{ladder}/groups/group-${{TG_ARRAY_INDEX}}.json",
            ),
            depends_on=("initialize-lowered-prime-ladder",),
            array_size=320,
            max_concurrent_tasks=8,
            parallel_workers_safe=True,
            backend_class="cpu_exact_sidecar",
            cpus_per_task=40,
        ),
        _phase(
            "aggregate-lowered-binary-leaves",
            (
                "${TG_PYTHON}", binary_tool, "aggregate", plan,
                "--receipts-dir", receipts, "--out", aggregate,
            ),
            depends_on=(
                "h100-8192-groups-of-eight-lowered-checkpoint-leaves",
            ),
            completion_artifact=aggregate,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "replay-lowered-binary-aggregate",
            (
                "${TG_PYTHON}", binary_tool, "verify", plan, aggregate,
                "--receipts-dir", receipts,
            ),
            depends_on=("aggregate-lowered-binary-leaves",),
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "reduce-lowered-prime-ladder-ranges",
            (
                "${TG_PYTHON}", ladder_tool, "reduce-ranges", ladder,
                "--out", ladder_aggregate,
            ),
            depends_on=("native-lowered-prime-ladder-range-groups",),
            completion_artifact=ladder_aggregate,
            backend_class="cpu_exact_sidecar",
        ),
        _phase(
            "measured-finalize-lowered-source-claim",
            (
                "${TG_PYTHON}", finalizer, ladder,
                "--ladder-aggregate", ladder_aggregate,
                "--binary-plan", plan,
                "--binary-receipts-dir", receipts,
                "--binary-aggregate", aggregate,
                "--combined-out", combined,
                "--registered-result-output", registered_result,
            ),
            depends_on=(
                "replay-lowered-binary-aggregate",
                "reduce-lowered-prime-ladder-ranges",
            ),
            completion_artifact=registered_result,
            backend_class="cpu_exact_sidecar",
        ),
    )


def _hurst_alias(atom_id: str) -> tuple[str, ...]:
    del atom_id
    return (
        "${TG_PYTHON}",
        _python_tool("tg_hurst_residual_campaign.py"),
        "verify",
        _workspace(HURST_PRIMARY_ATOM),
    )


# A single-job command is present only when the portable adapter can safely
# submit the whole physical campaign as one process.  Source-scale arrays and
# reducers are retained as explicit phase DAGs and are never flattened into a
# misleading one-job command.
WORKLOADS = (
    Workload(
        "ch25-a7-boundary",
        "cpu_flint_sidecar",
        (
            "${TG_PYTHON}",
            _python_tool("tg_verify.py"),
            "replay-a7-flint",
            "${TG_A7_TRANSCRIPT}",
            "--registered-result-output",
            "${TG_RUN_ROOT}/ch25-a7-boundary/registered-result.txt",
        ),
        8,
        32,
        "12:00:00",
        "idempotent_replay",
        "single_full_source_replay",
        "not_parallelized",
        "feasible once the exact retained boundary transcript is supplied",
        "ch25-a7-boundary",
        required_artifacts=("${TG_A7_TRANSCRIPT}",),
    ),
    Workload(
        "ch25-psi-1e13",
        "cpu_exact_sidecar",
        (),
        40,
        128,
        "1-00:00:00",
        "phase_and_shard_receipts",
        "two_pass_fixed_shard_dag",
        "320 worker groups cover 100000 independent summary leaves, then reduce, then 320 groups cover 100000 verify leaves",
        "source-scale primesieve/CRlibm implementation; current Slurm adapter requires manual phase-DAG submission",
        "ch25-psi-two-pass-v1",
        execution_mode="manual_phase_dag",
        phase_dag=_psi_phases(),
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
            "--registered-result-output",
            "${TG_RUN_ROOT}/platt-head-2e4/registered-result.txt",
        ),
        16,
        64,
        "1-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "bounded_memory_serial_batches",
        "practical CPU/FLINT sidecar (22492 indexed positive zeros)",
        "platt-head-2e4",
    ),
    Workload(
        ZETA_Q1_ATOM,
        "cpu_flint_sidecar",
        (),
        40,
        256,
        "2-00:00:00",
        "immutable_index_shard_receipts",
        "fixed_platt_turing_index_array_then_merkle_finalize",
        "1236316 independent ten-million-index FLINT Platt/Turing shards",
        "source-range complete in form but economically prohibitive: measured throughput projects about 13.4 ideal years across eight 40-core NCC nodes",
        "platt-trudgian-rh-3e12",
        execution_mode="manual_phase_dag",
        phase_dag=_platt_zeta_phases(),
    ),
    Workload(
        "helfgott-prop-12-2-4",
        "cpu_exact_sidecar",
        (),
        96,
        128,
        "1-00:00:00",
        "immutable_independent_leaf_receipts",
        "four_worker_groups_then_fixed_leaf_merkle_merge",
        "12930 independent MPFR/GMP leaves grouped into four 96-process jobs",
        "source-scale directed MPFR/GMP implementation; two measured replays have a 0.55--3.34 hour conservative compute band plus Azure control-plane overhead on four 96-core DC96as_v6 nodes",
        "helfgott-prop-12-2-4-mpfr-v1",
        execution_mode="manual_phase_dag",
        phase_dag=_prop1224_phases(),
    ),
    Workload(
        "cdem-squarefree",
        "cpu_exact_sidecar",
        _hurst_alias("cdem-squarefree"),
        4,
        16,
        "01:00:00",
        "idempotent_shared_certificate_replay",
        "shared_certificate_alias",
        "no arithmetic scan; replay the one four-residual Hurst certificate",
        "same physical two-pass run as mertens-hurst and both little-Mertens atoms",
        "hurst-four-residuals-v1",
        execution_mode="shared_certificate_alias",
        shared_owner_atom=HURST_PRIMARY_ATOM,
        dependencies=(HURST_PRIMARY_ATOM,),
        required_artifacts=(f"${{TG_RUN_ROOT}}/{HURST_PRIMARY_ATOM}/certificate.json",),
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
            "--artifact-output",
            "${TG_RUN_ROOT}/cdem-table-abel/cdem-abel-artifact.bin",
            "--registered-result-output",
            "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt",
        ),
        64,
        256,
        "2-00:00:00",
        "restart_current_full_scan",
        "single_openmp_scan",
        "one_node_openmp",
        "finite five-billion-step OpenMP scan with a closed Azure SEV-SNP "
        "materializer, independent all-chunk replay, and retained Lean "
        "artifact; the single scan restarts after interruption",
        "cdem-table-abel",
    ),
    Workload(
        "mertens-hurst",
        "cpu_exact_sidecar",
        (),
        40,
        320,
        "1-00:00:00",
        "two_pass_phase_and_shard_receipts",
        "shared_four_residual_two_pass_dag",
        "320 worker groups cover 10000 independent summary leaves, then reduce, then 320 groups cover 10000 verify leaves",
        "one source-scale two-pass Hurst/Mertens campaign supplies all four Möbius-family atoms; current adapter requires manual phase-DAG submission",
        "hurst-four-residuals-v1",
        execution_mode="manual_phase_dag",
        phase_dag=_hurst_phases(),
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
            "--arithmetic-replayer",
            "${TG_H100_BUILD}/sparkinterval-tg-r2star-arithmetic-replay",
            "--replay-threads",
            "32",
            "--registered-result-output",
            "${TG_RUN_ROOT}/ramare-zuniga-lemma-6-2/registered-result.txt",
        ),
        16,
        128,
        "7-00:00:00",
        "authenticated_chunk_resume",
        "serial_hash_chain",
        "h100_segment_acceleration_only",
        "large but direct: a 21-billion-row exact prefix chain",
        "ramare-zuniga-lemma-6-2",
    ),
    Workload(
        "helfgott-platt-theorem-4-1",
        "h100_cuda",
        (),
        16,
        128,
        "7-00:00:00",
        "immutable_binary_leaf_and_independent_ladder_range_receipts",
        "parallel_binary_and_native_ladder_branches_then_combined_replay",
        "8192 fixed H100 groups each retain eight of 65536 checkpoint leaves with at most eight concurrent GPU tasks; independently, 320 CPU groups cover all 492700 ladder ranges with 40 local workers before both branches are combined",
        "the full binary-plus-ladder DAG is implemented but has not run at source scale; the optimized GB10 binary benchmark still projects about 10.3 years across eight equal-throughput GPUs, while actual H100 throughput remains unmeasured",
        "helfgott-platt-goldbach-gpu-v1",
        execution_mode="manual_phase_dag",
        phase_dag=_goldbach_phases(),
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
        "rigorous full-domain fallback is wired but unscaled for 29547446729 primitive nonprincipal characters; the optimized primitive-only V2 path now has directed large-q batches, a fully replayed 96-MB finite-recovery seed table and fused recurrence service, an authenticated 125-GiB t-major Hurwitz-cache contract with replay repacking and a deterministic broadcast schedule, a source-wide supervisor plan pinning 56981100 real FFT batches over 3637613167 modulus/ordinate rows, an authenticated one-copy-per-row spool, a direct directed-MPFR factor/exact-rational-tail producer, and a typed 286556459000-byte source-wide row-resident CUDA input model whose bounded CUDA KAT uploads each lattice block once, plus a streaming validator for the exact 292500-modulus root catalog, a typed fixed-q FFT pipeline bundle validator, a bounded fail-closed adapter that freshly replays typed bundles in deterministic order and matches their TGDLATI1 payloads to authenticated cache rows, a persistent q-major composition/FFT/completed-L graph, and certified small-q disk arithmetic with parity-tail semantic sign reduction; however the source cache/root catalog are not populated, the row-resident TGDAFFI1 output is not wired into a persistent multi-q FFT/typed-bundle/completed-L lane, authenticated t-major zero state is not implemented, the new path is not source-scale measured or attested, and CUDA fusion/source-scale timing of the 226.996-TB small-q disk pipe, source-wide width, interpolation, exception, and Turing closure remain open",
        "platt-dirichlet-theorem-7-1",
        dependencies=(ZETA_Q1_ATOM,),
        required_artifacts=(f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",),
        postcheck=(
            "${TG_PYTHON}",
            _python_tool("tg_dirichlet_campaign.py"),
            "verify-source",
            _workspace(DIRICHLET_ATOM),
            "--q1-zeta-final",
            f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
            "--registered-result-output",
            f"${{TG_RUN_ROOT}}/{DIRICHLET_ATOM}/registered-result.txt",
        ),
    ),
    Workload(
        "platt-little-mertens-2-11",
        "cpu_exact_sidecar",
        _hurst_alias("platt-little-mertens-2-11"),
        4,
        16,
        "01:00:00",
        "idempotent_shared_certificate_replay",
        "shared_certificate_alias",
        "no arithmetic scan; replay the one four-residual Hurst certificate",
        "same physical two-pass run as mertens-hurst, squarefree, and the stronger little-Mertens atom",
        "hurst-four-residuals-v1",
        execution_mode="shared_certificate_alias",
        shared_owner_atom=HURST_PRIMARY_ATOM,
        dependencies=(HURST_PRIMARY_ATOM,),
        required_artifacts=(f"${{TG_RUN_ROOT}}/{HURST_PRIMARY_ATOM}/certificate.json",),
    ),
    Workload(
        "platt-little-mertens-stronger",
        "cpu_exact_sidecar",
        _hurst_alias("platt-little-mertens-stronger"),
        4,
        16,
        "01:00:00",
        "idempotent_shared_certificate_replay",
        "shared_certificate_alias",
        "no arithmetic scan; replay the one four-residual Hurst certificate",
        "same physical two-pass run as mertens-hurst, squarefree, and the 2/11 little-Mertens atom",
        "hurst-four-residuals-v1",
        execution_mode="shared_certificate_alias",
        shared_owner_atom=HURST_PRIMARY_ATOM,
        dependencies=(HURST_PRIMARY_ATOM,),
        required_artifacts=(f"${{TG_RUN_ROOT}}/{HURST_PRIMARY_ATOM}/certificate.json",),
    ),
    Workload(
        GOLDBACH_10POW27_ATOM,
        "h100_cuda",
        (),
        16,
        128,
        "7-00:00:00",
        "immutable_binary_leaf_and_independent_ladder_range_receipts",
        "parallel_lowered_binary_and_n45_ladder_branches_then_measured_finalizer",
        "8192 fixed H100 groups cover 65536 lowered binary leaves while 320 CPU groups cover all 7106 n=45 ladder ranges; the terminal CPU job replays both branches",
        "source-complete lowered finite campaign is UNRUN; all 8192 H100 groups and 326 CPU jobs have closed measured-job/export materializers, but H100 throughput is uncalibrated and no production receipts exist",
        GOLDBACH_10POW27_CAMPAIGN,
        execution_mode="manual_phase_dag",
        phase_dag=_goldbach_10pow27_phases(),
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
        phase_tokens = tuple(
            token for phase in workload.phase_dag for token in phase.command
        )
        required_direct_files.update(
            token[len(prefix) :]
            for token in (*workload.command, *workload.postcheck, *phase_tokens)
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


def _phase_record(
    phase: Phase, *, inherited_backend_class: str, inherited_cpus_per_task: int
) -> dict[str, Any]:
    backend_class = phase.backend_class or inherited_backend_class
    cpus_per_task = phase.cpus_per_task or inherited_cpus_per_task
    return {
        "phase_id": phase.phase_id,
        "command": list(phase.command),
        "depends_on": list(phase.depends_on),
        "scheduler_shape": phase.scheduler_shape,
        "array_size": phase.array_size,
        "max_concurrent_tasks": phase.max_concurrent_tasks,
        "parallel_workers_safe": phase.parallel_workers_safe,
        "completion_artifact": phase.completion_artifact,
        "backend_class": backend_class,
        "resources": {
            "cpus_per_task": cpus_per_task,
            "h100_gpus": 1 if backend_class == "h100_cuda" else 0,
        },
    }


def _job_record(workload: Workload) -> dict[str, Any]:
    parallel_width = max(
        (phase.array_size for phase in workload.phase_dag if phase.parallel_workers_safe),
        default=1,
    )
    return {
        "atom_id": workload.atom_id,
        "scope": "full_source",
        "sample": False,
        "backend_class": workload.backend_class,
        "campaign_id": workload.campaign_id,
        "execution_mode": workload.execution_mode,
        "shared_owner_atom": workload.shared_owner_atom,
        "single_job_adapter_supported": workload.execution_mode != "manual_phase_dag",
        "command": list(workload.command),
        "phase_dag": [
            _phase_record(
                phase,
                inherited_backend_class=workload.backend_class,
                inherited_cpus_per_task=workload.cpus,
            )
            for phase in workload.phase_dag
        ],
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
            "parallel_intra_atom_shards": parallel_width,
            "scalability": workload.scalability,
            "reason_parallel_shards_are_one": (
                None
                if parallel_width != 1
                else "The retained job is a single replay, a stateful chain, or a shared-certificate alias."
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


def _physical_campaign_records() -> list[dict[str, Any]]:
    campaign_ids: list[str] = []
    for workload in WORKLOADS:
        if workload.campaign_id not in campaign_ids:
            campaign_ids.append(workload.campaign_id)
    records: list[dict[str, Any]] = []
    for campaign_id in campaign_ids:
        members = [item for item in WORKLOADS if item.campaign_id == campaign_id]
        owners = [item for item in members if item.shared_owner_atom is None]
        if len(owners) != 1:
            raise ClusterPlanError(
                f"physical campaign {campaign_id} must have exactly one owner"
            )
        owner = owners[0]
        records.append(
            {
                "campaign_id": campaign_id,
                "owner_atom_id": owner.atom_id,
                "logical_atom_ids": [
                    atom_id for atom_id in ATOM_IDS
                    if any(item.atom_id == atom_id for item in members)
                ],
                "backend_class": owner.backend_class,
                "execution_mode": owner.execution_mode,
                "single_job_adapter_supported": owner.execution_mode == "single_job",
                "phase_dag": [
                    _phase_record(
                        phase,
                        inherited_backend_class=owner.backend_class,
                        inherited_cpus_per_task=owner.cpus,
                    )
                    for phase in owner.phase_dag
                ],
            }
        )
    return records


def build_manifest(repository_binding: Mapping[str, Any]) -> dict[str, Any]:
    """Return the reviewed source-atom plus lowered-endpoint deployment plan."""

    binding = validate_repository_binding(dict(repository_binding))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "classification": "full_source_deployment_capability_not_completed_evidence",
        "scope": "all_13_named_external_atoms_plus_distinct_10pow27_finite_endpoint",
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
                "TG_TG_BUILD": "${TG_REPOSITORY}/build/tg-production",
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
            "manual_phase_dag_bindings": [
                "TG_ARRAY_INDEX",
                "TG_GOLDBACH_SOURCE_ROOT",
                "TG_GOLDBACH_EXECUTABLE",
                "TG_GOLDBACH_EXECUTABLE_SHA256",
            ],
        },
        "portfolio_partitioning": {
            "logical_atom_count": len(ATOM_IDS),
            "source_atom_count": len(SOURCE_ATOM_IDS),
            "conditional_endpoint_campaign_count": 1,
            "physical_campaign_count": 11,
            "single_job_campaign_count": 5,
            "manual_phase_dag_campaign_count": 6,
            "shared_certificate_alias_count": 3,
            "all_atoms_single_job_submission_supported": False,
            "policy": (
                "report every named atom, deduplicate shared evidence, and require "
                "an explicit scheduler phase DAG for independently safe arrays"
            ),
        },
        "dependency_edges": [
            {
                "from": ZETA_Q1_ATOM,
                "to": DIRICHLET_ATOM,
                "scheduler_condition": "afterok",
                "artifact": f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
                "meaning": "q=1 zeta prerequisite for the Dirichlet source composition",
            },
            *[
                {
                    "from": HURST_PRIMARY_ATOM,
                    "to": atom_id,
                    "scheduler_condition": "certificate_present_and_semantic_replay",
                    "artifact": f"${{TG_RUN_ROOT}}/{HURST_PRIMARY_ATOM}/certificate.json",
                    "meaning": "logical alias of the one shared four-residual Hurst campaign",
                }
                for atom_id in HURST_ATOMS
                if atom_id != HURST_PRIMARY_ATOM
            ],
        ],
        "physical_campaigns": _physical_campaign_records(),
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
    if not isinstance(jobs, list) or len(jobs) != len(ATOM_IDS):
        raise ClusterPlanError(
            "cluster manifest must contain the thirteen source jobs and the "
            "distinct lowered finite-endpoint job"
        )
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
        execution_mode = job.get("execution_mode")
        if execution_mode not in EXECUTION_MODES:
            raise ClusterPlanError(f"{atom_id} has an invalid execution mode")
        command = job.get("command")
        if not isinstance(command, list) or not all(
            isinstance(token, str) and token for token in command
        ):
            raise ClusterPlanError(f"{atom_id} has an invalid argument vector")
        if execution_mode == "manual_phase_dag" and command:
            raise ClusterPlanError(
                f"{atom_id} must not flatten its phase DAG into one command"
            )
        if execution_mode != "manual_phase_dag" and not command:
            raise ClusterPlanError(f"{atom_id} has no executable argument vector")
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
        phase_dag = job.get("phase_dag")
        if not isinstance(phase_dag, list):
            raise ClusterPlanError(f"{atom_id} phase DAG must be an array")
        if execution_mode == "manual_phase_dag" and not phase_dag:
            raise ClusterPlanError(f"{atom_id} omits its required phase DAG")
        if execution_mode != "manual_phase_dag" and phase_dag:
            raise ClusterPlanError(f"{atom_id} unexpectedly has a phase DAG")
        phase_ids: list[str] = []
        for phase_index, phase in enumerate(phase_dag):
            if not isinstance(phase, dict):
                raise ClusterPlanError(
                    f"{atom_id} phase {phase_index} must be an object"
                )
            phase_id = phase.get("phase_id")
            phase_command = phase.get("command")
            depends_on = phase.get("depends_on")
            if (
                not isinstance(phase_id, str)
                or not phase_id
                or not isinstance(phase_command, list)
                or not phase_command
                or not all(isinstance(token, str) and token for token in phase_command)
                or not isinstance(depends_on, list)
                or not all(isinstance(item, str) and item for item in depends_on)
            ):
                raise ClusterPlanError(f"{atom_id} phase {phase_index} is malformed")
            if any(item not in phase_ids for item in depends_on):
                raise ClusterPlanError(
                    f"{atom_id} phase {phase_id} has a forward or unknown dependency"
                )
            if forbidden.intersection(phase_command):
                raise ClusterPlanError(
                    f"{atom_id} phase {phase_id} contains a sample/pause switch"
                )
            phase_ids.append(phase_id)
        if len(phase_ids) != len(set(phase_ids)):
            raise ClusterPlanError(f"{atom_id} has duplicate phase ids")
        postcheck = job.get("postcheck_command")
        if not isinstance(postcheck, list) or not all(
            isinstance(token, str) and token for token in postcheck
        ):
            raise ClusterPlanError(f"{atom_id} has an invalid postcheck argument vector")
        if forbidden.intersection(postcheck):
            raise ClusterPlanError(
                f"{atom_id} postcheck contains a sample/pause switch"
            )
    if tuple(ids) != ATOM_IDS or len(set(ids)) != len(ATOM_IDS):
        raise ClusterPlanError("cluster job ids differ from the reviewed workload set")
    campaigns = value.get("physical_campaigns")
    if not isinstance(campaigns, list) or len(campaigns) != 11:
        raise ClusterPlanError("cluster manifest must contain eleven physical campaigns")
    covered = [
        atom_id
        for campaign in campaigns
        if isinstance(campaign, dict)
        for atom_id in campaign.get("logical_atom_ids", [])
    ]
    if sorted(covered) != sorted(ATOM_IDS) or len(covered) != len(set(covered)):
        raise ClusterPlanError(
            "physical campaigns do not cover every reviewed workload exactly once"
        )
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
    del manifest
    return b"""#!/usr/bin/env bash
# Generated by tools/tg_h100_cluster.py; do not edit.
set -euo pipefail
echo "all-workloads submission is disabled: six physical campaigns require explicit Slurm phase DAGs" >&2
echo "translate the reviewed manual-phase-dags/*.json files into site-specific arrays and afterok reductions" >&2
echo "the adapter refuses to flatten psi, Platt zeta, Proposition 12.2.4, Hurst, historical Goldbach, or lowered 10^27 Goldbach into one job" >&2
exit 78
"""


def render_submit_one_script(manifest: Mapping[str, Any]) -> bytes:
    cases = []
    for job in manifest["jobs"]:
        if job["single_job_adapter_supported"]:
            cases.append(
                f"  {job['atom_id']}) partition=\"${{{_partition_variable(job['backend_class'])}:?}}\"; backend={job['backend_class']}; supported=1 ;;"
            )
        else:
            cases.append(
                f"  {job['atom_id']}) supported=0 ;;"
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
supported=0
case "${atom}" in
""" + "\n".join(cases) + """
  *) echo "unknown atom id: ${atom}" >&2; exit 64 ;;
esac
if [[ "${supported}" != 1 ]]; then
  echo "${atom} requires the explicit manual phase DAG; no single Slurm job was generated" >&2
  exit 78
fi
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
        if job["single_job_adapter_supported"]
    }
    files.update(
        {
            f"manual-phase-dags/{job['atom_id']}.json": canonical_json_bytes(
                {
                    "atom_id": job["atom_id"],
                    "campaign_id": job["campaign_id"],
                    "classification": "manual_site_scheduler_translation_required",
                    "phase_dag": job["phase_dag"],
                    "single_job_adapter_supported": False,
                }
            )
            for job in manifest["jobs"]
            if job["execution_mode"] == "manual_phase_dag"
        }
    )
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
        path.chmod(0o755 if relative.startswith("slurm/") else 0o644)
    digest = sha256_bytes(raw)
    (directory / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="ascii"
    )
    return {
        "accepted": True,
        "classification": "portable_full_source_deployment_plan_not_execution",
        "directory": str(directory),
        "manifest_sha256": digest,
        "logical_atom_count": len(ATOM_IDS),
        "source_atom_count": len(SOURCE_ATOM_IDS),
        "conditional_endpoint_campaign_count": 1,
        "physical_campaign_count": 11,
        "single_job_adapter_count": 8,
        "manual_phase_dag_count": 6,
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
        "logical_atom_count": len(ATOM_IDS),
        "source_atom_count": len(SOURCE_ATOM_IDS),
        "conditional_endpoint_campaign_count": 1,
        "physical_campaign_count": 11,
        "single_job_adapter_count": 8,
        "manual_phase_dag_count": 6,
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
        env.setdefault("TG_TG_BUILD", f"{repository}/build/tg-production")
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
        env.setdefault("TG_TG_BUILD", f"{repository}/build/tg-production")
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
    if job["execution_mode"] == "manual_phase_dag":
        raise ClusterPlanError(
            f"{atom_id} requires the explicit phase DAG in manual-phase-dags/; "
            "the one-job executor refuses to flatten it"
        )
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
    logical_counts = {backend: 0 for backend in sorted(BACKEND_CLASSES)}
    for workload in WORKLOADS:
        logical_counts[workload.backend_class] += 1
    physical = _physical_campaign_records()
    physical_counts = {backend: 0 for backend in sorted(BACKEND_CLASSES)}
    for campaign in physical:
        physical_counts[campaign["backend_class"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "cluster_execution_capability_not_completed_evidence",
        "logical_atom_count": len(WORKLOADS),
        "source_atom_count": len(SOURCE_ATOM_IDS),
        "conditional_endpoint_campaign_count": 1,
        "physical_campaign_count": len(physical),
        "logical_backend_counts": logical_counts,
        "physical_backend_counts": physical_counts,
        "all_atoms_single_job_submission_supported": False,
        "manual_phase_dag_campaigns": [
            campaign["campaign_id"]
            for campaign in physical
            if campaign["execution_mode"] == "manual_phase_dag"
        ],
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
                "campaign_id": item.campaign_id,
                "execution_mode": item.execution_mode,
                "shared_owner_atom": item.shared_owner_atom,
                "backend_class": item.backend_class,
                "resume_mode": item.resume_mode,
                "scalability": item.scalability,
                "feasibility": item.feasibility,
            }
            for item in WORKLOADS
        ],
    }
