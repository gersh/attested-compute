# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tg_verifier.h100_cluster import (
    ATOM_IDS,
    DIRICHLET_ATOM,
    ZETA_Q1_ATOM,
    ClusterPlanError,
    WORKLOADS,
    _write_deployment_manifest,
    build_manifest,
    canonical_json_bytes,
    execute_job,
    inspect_clean_repository,
    load_manifest,
    resolve_command,
    validate_manifest,
    verify_deployment,
)


REPOSITORY = Path(__file__).resolve().parents[1]
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def direct_repository_paths() -> list[str]:
    paths = {
        "tg_verifier/h100_cluster.py",
        "tools/tg_h100_cluster.py",
        "reference/tg_cdem_abel.cpp",
    }
    prefix = "${TG_REPOSITORY}/"
    for workload in WORKLOADS:
        paths.update(
            token[len(prefix) :]
            for token in (*workload.command, *workload.postcheck)
            if token.startswith(prefix)
        )
    return sorted(paths)


def fake_repository_binding() -> dict[str, object]:
    paths = direct_repository_paths()
    return {
        "kind": "sparkinterval.tg.clean_git_repository_closure.v1",
        "coverage": "all_git_tracked_regular_files",
        "clean_worktree": True,
        "untracked_files_absent": True,
        "git_object_format": "sha1",
        "git_commit_oid": "a" * 40,
        "git_tree_oid": "b" * 40,
        "file_count": len(paths),
        "files": [
            {"path": path, "sha256": EMPTY_SHA256, "size_bytes": 0}
            for path in paths
        ],
    }


def initialize_clean_test_repository(root: Path) -> dict[str, object]:
    for relative in direct_repository_paths():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=TG Cluster Test",
            "-c",
            "user.email=tg-cluster@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
    )
    return inspect_clean_repository(root)


class H100ClusterPlanTests(unittest.TestCase):
    def test_exactly_thirteen_full_source_jobs_are_classified(self) -> None:
        manifest = validate_manifest(build_manifest(fake_repository_binding()))
        jobs = manifest["jobs"]
        self.assertEqual(tuple(job["atom_id"] for job in jobs), ATOM_IDS)
        self.assertEqual(sum(job["backend_class"] == "h100_cuda" for job in jobs), 5)
        self.assertEqual(
            sum(job["backend_class"] == "cpu_flint_sidecar" for job in jobs), 4
        )
        self.assertEqual(
            sum(job["backend_class"] == "cpu_exact_sidecar" for job in jobs), 4
        )
        self.assertTrue(all(job["scope"] == "full_source" for job in jobs))
        self.assertTrue(all(job["sample"] is False for job in jobs))
        self.assertTrue(
            all(job["partitioning"]["parallel_intra_atom_shards"] == 1 for job in jobs)
        )

    def test_dirichlet_has_scheduler_and_artifact_dependency_on_q1_zeta(self) -> None:
        manifest = build_manifest(fake_repository_binding())
        by_id = {job["atom_id"]: job for job in manifest["jobs"]}
        job = by_id[DIRICHLET_ATOM]
        self.assertEqual(job["dependencies"], [ZETA_Q1_ATOM])
        self.assertEqual(
            job["required_artifacts"],
            [f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json"],
        )
        self.assertIn("--q1-zeta-final", job["command"])
        self.assertEqual(
            manifest["dependency_edges"],
            [
                {
                    "from": ZETA_Q1_ATOM,
                    "to": DIRICHLET_ATOM,
                    "scheduler_condition": "afterok",
                    "artifact": f"${{TG_RUN_ROOT}}/{ZETA_Q1_ATOM}/final.json",
                    "meaning": "q=1 zeta prerequisite for the Dirichlet source composition",
                }
            ],
        )

    def test_sample_or_pause_tampering_is_rejected(self) -> None:
        manifest = build_manifest(fake_repository_binding())
        manifest["jobs"][0]["sample"] = True
        with self.assertRaisesRegex(ClusterPlanError, "full-source"):
            validate_manifest(manifest)

        manifest = build_manifest(fake_repository_binding())
        manifest["jobs"][0]["command"].extend(["--max-chunks", "1"])
        with self.assertRaisesRegex(ClusterPlanError, "sample/pause"):
            validate_manifest(manifest)

    def test_plan_and_all_generated_adapter_bytes_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "deployment"
            result = _write_deployment_manifest(
                root, build_manifest(fake_repository_binding())
            )
            self.assertEqual(result["job_count"], 13)
            verified = verify_deployment(root)
            self.assertTrue(verified["accepted"])
            submit = (root / "slurm" / "submit.sh").read_text()
            self.assertIn(
                "submit_atom platt-dirichlet-theorem-7-1 "
                '"${TG_CPU_FLINT_PARTITION}" cpu_flint_sidecar "${zeta_job}"',
                submit,
            )
            common = (root / "slurm" / "common.sh").read_text()
            self.assertIn("TG_H100_GRES:-gpu:h100:1", common)
            self.assertIn("tg_acquire_submission_lock", common)
            self.assertIn("sync -d", common)
            self.assertEqual(len(list((root / "slurm" / "jobs").glob("*.sbatch"))), 13)
            h100_script = (
                root / "slurm" / "jobs" / "cdem-squarefree.sbatch"
            ).read_text()
            self.assertNotIn("#SBATCH --gres", h100_script)
            self.assertIn("Slurm must assign exactly one H100", h100_script)
            self.assertNotIn("CUDA_VISIBLE_DEVICES:-0", h100_script)
            for script in (root / "slurm").rglob("*.sh"):
                subprocess.run(["bash", "-n", str(script)], check=True)
            for script in (root / "slurm" / "jobs").glob("*.sbatch"):
                subprocess.run(["bash", "-n", str(script)], check=True)
            normalized = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; tg_normalize_job_id "12345;safe-cluster"',
                    "bash",
                    str(root / "slurm" / "common.sh"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(normalized.stdout, "12345")
            malformed = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; tg_normalize_job_id "12345;cluster;garbage"',
                    "bash",
                    str(root / "slurm" / "common.sh"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(malformed.returncode, 0)

            job_script = root / "slurm" / "jobs" / "cdem-squarefree.sbatch"
            job_script.write_text(job_script.read_text() + "# tamper\n")
            with self.assertRaisesRegex(ClusterPlanError, "adapter differs"):
                verify_deployment(root)

    def test_clean_git_closure_rejects_dirty_or_untracked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            binding = initialize_clean_test_repository(root)
            self.assertEqual(binding["coverage"], "all_git_tracked_regular_files")
            self.assertEqual(binding["file_count"], len(binding["files"]))
            (root / "tools" / "untracked_implementation.py").write_text("pass\n")
            with self.assertRaisesRegex(ClusterPlanError, "dirty or untracked"):
                inspect_clean_repository(root)

    def test_reconciled_full_entry_points_are_present(self) -> None:
        jobs = {
            job["atom_id"]: job
            for job in build_manifest(fake_repository_binding())["jobs"]
        }
        goldbach = jobs["helfgott-platt-theorem-4-1"]["command"]
        self.assertIn("--general-prime-producer", goldbach)
        self.assertIn(
            "${TG_REPOSITORY}/tools/tg_pocklington_producer.py", goldbach
        )
        cdem = jobs["cdem-table-abel"]["command"]
        self.assertIn("run-cdem-abel-full", cdem)
        self.assertIn(
            "${TG_REPOSITORY}/reference/tg_cdem_abel_chunk_replay.cpp", cdem
        )
        self.assertIn("verify-source", jobs[DIRICHLET_ATOM]["postcheck_command"])

    def test_generated_submitter_schedules_all_thirteen_and_afterok(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deployment = root / "deployment"
            _write_deployment_manifest(
                deployment, build_manifest(fake_repository_binding())
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sbatch = bin_dir / "sbatch"
            fake_sbatch.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
counter_file="${TG_FAKE_SBATCH_COUNTER}"
log_file="${TG_FAKE_SBATCH_LOG}"
n=1000
if [[ -f "${counter_file}" ]]; then n="$(<"${counter_file}")"; fi
n=$((n + 1))
printf '%s\n' "${n}" >"${counter_file}"
printf '%s\t' "${n}" >>"${log_file}"
printf '%q ' "$@" >>"${log_file}"
printf '\n' >>"${log_file}"
printf '%s;fixture-cluster\n' "${n}"
""",
                encoding="utf-8",
            )
            fake_sbatch.chmod(0o755)
            run_root = root / "runs"
            transcript = root / "a7.json"
            transcript.write_text("{}\n")
            environment = {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TG_REPOSITORY": str(root / "repository"),
                "TG_RUN_ROOT": str(run_root),
                "TG_A7_TRANSCRIPT": str(transcript),
                "TG_H100_PARTITION": "h100",
                "TG_CPU_FLINT_PARTITION": "flint",
                "TG_CPU_EXACT_PARTITION": "exact",
                "TG_FAKE_SBATCH_COUNTER": str(root / "counter"),
                "TG_FAKE_SBATCH_LOG": str(root / "sbatch.log"),
            }
            subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            receipt = (run_root / "slurm-submission.tsv").read_text().splitlines()
            self.assertEqual(len(receipt), 14)
            rows = {line.split("\t")[0]: line.split("\t") for line in receipt[1:]}
            self.assertEqual(rows[DIRICHLET_ATOM][2], rows[ZETA_Q1_ATOM][1])
            log = (root / "sbatch.log").read_text()
            self.assertIn(f"--dependency=afterok:{rows[ZETA_Q1_ATOM][1]}", log)
            self.assertIn("--gres=gpu:h100:1", log)
            self.assertIn(f"--chdir={run_root}", log)
            self.assertIn(f"--output={run_root}/slurm-logs/", log)

            resume_environment = {
                **environment,
                "TG_H100_GRES": "gpu:1",
                "TG_H100_CONSTRAINT": "h100-site-label",
                "TG_SLURM_ACCOUNT": "proof-account",
                "TG_SLURM_QOS": "proof-qos",
                "TG_SLURM_RESERVATION": "proof-reservation",
                "TG_H100_WALLTIME": "01:23:45",
            }
            resumed = subprocess.run(
                [
                    "bash",
                    str(deployment / "slurm" / "submit-one.sh"),
                    "ramare-zuniga-lemma-6-2",
                ],
                check=True,
                env=resume_environment,
                capture_output=True,
                text=True,
            )
            self.assertRegex(resumed.stdout, r"^[0-9]+\n$")
            resume_rows = (
                run_root / "slurm-resubmissions.tsv"
            ).read_text().splitlines()
            self.assertEqual(len(resume_rows), 2)
            self.assertEqual(resume_rows[1].split("\t")[1], resumed.stdout.strip())
            resume_log = (root / "sbatch.log").read_text().splitlines()[-1]
            self.assertIn("--gres=gpu:1", resume_log)
            self.assertIn("--constraint=h100-site-label", resume_log)
            self.assertIn("--account=proof-account", resume_log)
            self.assertIn("--qos=proof-qos", resume_log)
            self.assertIn("--reservation=proof-reservation", resume_log)
            self.assertIn("--time=01:23:45", resume_log)

    def test_partial_submission_journal_resumes_without_duplicate_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deployment = root / "deployment"
            _write_deployment_manifest(
                deployment, build_manifest(fake_repository_binding())
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sbatch = bin_dir / "sbatch"
            fake_sbatch.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
counter_file="${TG_FAKE_SBATCH_COUNTER}"
log_file="${TG_FAKE_SBATCH_LOG}"
n=2000
if [[ -f "${counter_file}" ]]; then n="$(<"${counter_file}")"; fi
n=$((n + 1))
printf '%s\n' "${n}" >"${counter_file}"
if [[ "${TG_FAKE_SBATCH_FAIL_ON:-}" == "${n}" ]]; then exit 88; fi
printf '%s\t' "${n}" >>"${log_file}"
printf '%q ' "$@" >>"${log_file}"
printf '\n' >>"${log_file}"
printf '%s;fixture-cluster\n' "${n}"
""",
                encoding="utf-8",
            )
            fake_sbatch.chmod(0o755)
            run_root = root / "runs"
            transcript = root / "a7.json"
            transcript.write_text("{}\n")
            environment = {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TG_REPOSITORY": str(root / "repository"),
                "TG_RUN_ROOT": str(run_root),
                "TG_A7_TRANSCRIPT": str(transcript),
                "TG_H100_PARTITION": "h100",
                "TG_CPU_FLINT_PARTITION": "flint",
                "TG_CPU_EXACT_PARTITION": "exact",
                "TG_FAKE_SBATCH_COUNTER": str(root / "counter"),
                "TG_FAKE_SBATCH_LOG": str(root / "sbatch.log"),
                "TG_FAKE_SBATCH_FAIL_ON": "2004",
            }
            failed = subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=False,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            partial = (run_root / "slurm-submission.tsv").read_text().splitlines()
            self.assertEqual(len(partial), 4)

            environment.pop("TG_FAKE_SBATCH_FAIL_ON")
            subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            complete = (run_root / "slurm-submission.tsv").read_text().splitlines()
            self.assertEqual(len(complete), 14)
            atoms = [line.split("\t")[0] for line in complete[1:]]
            self.assertEqual(len(atoms), len(set(atoms)))
            self.assertEqual(set(atoms), set(ATOM_IDS))
            submitted = (root / "sbatch.log").read_text().splitlines()
            self.assertEqual(len(submitted), 13)

    def test_first_zeta_submission_failure_is_fatal_and_retry_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deployment = root / "deployment"
            _write_deployment_manifest(
                deployment, build_manifest(fake_repository_binding())
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sbatch = bin_dir / "sbatch"
            fake_sbatch.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
counter_file="${TG_FAKE_SBATCH_COUNTER}"
log_file="${TG_FAKE_SBATCH_LOG}"
n=3000
if [[ -f "${counter_file}" ]]; then n="$(<"${counter_file}")"; fi
n=$((n + 1))
printf '%s\n' "${n}" >"${counter_file}"
if [[ "${TG_FAKE_SBATCH_FAIL_ON:-}" == "${n}" ]]; then exit 88; fi
printf '%s\t' "${n}" >>"${log_file}"
printf '%q ' "$@" >>"${log_file}"
printf '\n' >>"${log_file}"
printf '%s;fixture-cluster\n' "${n}"
""",
                encoding="utf-8",
            )
            fake_sbatch.chmod(0o755)
            run_root = root / "runs"
            transcript = root / "a7.json"
            transcript.write_text("{}\n")
            environment = {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TG_REPOSITORY": str(root / "repository"),
                "TG_RUN_ROOT": str(run_root),
                "TG_A7_TRANSCRIPT": str(transcript),
                "TG_H100_PARTITION": "h100",
                "TG_CPU_FLINT_PARTITION": "flint",
                "TG_CPU_EXACT_PARTITION": "exact",
                "TG_FAKE_SBATCH_COUNTER": str(root / "counter"),
                "TG_FAKE_SBATCH_LOG": str(root / "sbatch.log"),
                "TG_FAKE_SBATCH_FAIL_ON": "3001",
            }
            failed = subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=False,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            journal = run_root / "slurm-submission.tsv"
            self.assertEqual(journal.read_text().splitlines(), [
                "atom_id\tjob_id\tdependency"
            ])
            self.assertFalse((root / "sbatch.log").exists())

            environment.pop("TG_FAKE_SBATCH_FAIL_ON")
            subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            rows = {
                row[0]: row
                for row in (
                    line.split("\t") for line in journal.read_text().splitlines()[1:]
                )
            }
            self.assertEqual(set(rows), set(ATOM_IDS))
            self.assertEqual(rows[DIRICHLET_ATOM][2], rows[ZETA_Q1_ATOM][1])
            self.assertEqual(len((root / "sbatch.log").read_text().splitlines()), 13)

    def test_noncanonical_or_changed_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(
                json.dumps(build_manifest(fake_repository_binding()), indent=2) + "\n"
            )
            with self.assertRaisesRegex(ClusterPlanError, "not canonical"):
                load_manifest(path)

            value = build_manifest(fake_repository_binding())
            value["portfolio_partitioning"]["job_count"] = 12
            path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ClusterPlanError, "differs"):
                load_manifest(path)

    def test_command_resolution_uses_no_shell_and_requires_bindings(self) -> None:
        job = next(
            job
            for job in build_manifest(fake_repository_binding())["jobs"]
            if job["atom_id"] == "cdem-squarefree"
        )
        command = resolve_command(
            job,
            {
                "TG_REPOSITORY": str(REPOSITORY),
                "TG_RUN_ROOT": "/shared/tg",
                "TG_PYTHON": "/usr/bin/python3",
                "TG_H100_BUILD": "/opt/tg-h100",
            },
        )
        self.assertEqual(command[0], "/usr/bin/python3")
        self.assertIn("/opt/tg-h100/sparkinterval-h100-tg-mobius-segment", command)
        self.assertNotIn("--allow-other-device", command)
        with self.assertRaisesRegex(ClusterPlanError, "TG_RUN_ROOT"):
            resolve_command(job, {"TG_REPOSITORY": str(REPOSITORY)})

    def test_dirichlet_dry_run_refuses_missing_q1_final(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            binding = initialize_clean_test_repository(repository)
            deployment = root / "deployment"
            _write_deployment_manifest(deployment, build_manifest(binding))
            run_root = root / "runs"
            environment = {
                "TG_REPOSITORY": str(repository),
                "TG_RUN_ROOT": str(run_root),
                "TG_PYTHON": "/usr/bin/python3",
            }
            with self.assertRaisesRegex(ClusterPlanError, "dependency artifact"):
                execute_job(
                    deployment / "manifest.json",
                    DIRICHLET_ATOM,
                    environment=environment,
                    dry_run=True,
                )


if __name__ == "__main__":
    unittest.main()
