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
    GOLDBACH_10POW27_ATOM,
    GOLDBACH_10POW27_CAMPAIGN,
    HURST_PRIMARY_ATOM,
    SOURCE_ATOM_IDS,
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
        phase_tokens = tuple(
            token for phase in workload.phase_dag for token in phase.command
        )
        paths.update(
            token[len(prefix) :]
            for token in (*workload.command, *workload.postcheck, *phase_tokens)
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
    def test_source_atoms_and_lowered_endpoint_are_distinct_campaigns(self) -> None:
        manifest = validate_manifest(build_manifest(fake_repository_binding()))
        jobs = manifest["jobs"]
        self.assertEqual(tuple(job["atom_id"] for job in jobs), ATOM_IDS)
        self.assertEqual(len(SOURCE_ATOM_IDS), 13)
        self.assertEqual(len(manifest["physical_campaigns"]), 11)
        self.assertEqual(
            sum(job["execution_mode"] == "manual_phase_dag" for job in jobs), 6
        )
        self.assertEqual(
            sum(job["execution_mode"] == "shared_certificate_alias" for job in jobs),
            3,
        )
        self.assertEqual(
            {
                backend: sum(job["backend_class"] == backend for job in jobs)
                for backend in (
                    "h100_cuda",
                    "cpu_flint_sidecar",
                    "cpu_exact_sidecar",
                )
            },
            {"h100_cuda": 3, "cpu_flint_sidecar": 4, "cpu_exact_sidecar": 7},
        )
        self.assertEqual(
            manifest["portfolio_partitioning"]["source_atom_count"], 13
        )
        self.assertEqual(
            manifest["portfolio_partitioning"][
                "conditional_endpoint_campaign_count"
            ],
            1,
        )
        self.assertTrue(all(job["scope"] == "full_source" for job in jobs))
        self.assertTrue(all(job["sample"] is False for job in jobs))
        self.assertFalse(
            manifest["portfolio_partitioning"][
                "all_atoms_single_job_submission_supported"
            ]
        )

    def test_source_scale_phase_dags_name_real_supervisors(self) -> None:
        jobs = {
            job["atom_id"]: job
            for job in build_manifest(fake_repository_binding())["jobs"]
        }
        psi = jobs["ch25-psi-1e13"]["phase_dag"]
        self.assertEqual(
            [phase["array_size"] for phase in psi],
            [1, 320, 1, 320, 1, 1],
        )
        self.assertIn("tg_psi_residual_campaign.py", " ".join(psi[0]["command"]))
        self.assertIn("--worker-group-count", psi[1]["command"])
        self.assertIn("320", psi[1]["command"])
        psi_terminal = psi[-1]
        self.assertEqual(psi_terminal["phase_id"], "semantic-replay")
        result_flag = psi_terminal["command"].index(
            "--registered-result-output"
        )
        self.assertEqual(
            psi_terminal["command"][result_flag + 1],
            "${TG_RUN_ROOT}/ch25-psi-1e13/registered-result.txt",
        )
        self.assertEqual(
            psi_terminal["completion_artifact"],
            "${TG_RUN_ROOT}/ch25-psi-1e13/registered-result.txt",
        )

        prop = jobs["helfgott-prop-12-2-4"]["phase_dag"]
        self.assertEqual([phase["array_size"] for phase in prop], [4, 1])
        self.assertIn(
            "tg_prop1224_mpfr_campaign.py", " ".join(prop[0]["command"])
        )
        self.assertIn("run-worker-group", prop[0]["command"])
        self.assertIn("--workers", prop[0]["command"])
        self.assertIn("96", prop[0]["command"])
        prop_terminal = prop[-1]
        result_flag = prop_terminal["command"].index(
            "--registered-result-output"
        )
        self.assertEqual(
            prop_terminal["command"][result_flag + 1],
            "${TG_RUN_ROOT}/helfgott-prop-12-2-4/registered-result.txt",
        )
        self.assertEqual(
            prop_terminal["completion_artifact"],
            "${TG_RUN_ROOT}/helfgott-prop-12-2-4/registered-result.txt",
        )

        zeta = jobs[ZETA_Q1_ATOM]["phase_dag"]
        self.assertEqual(
            [phase["array_size"] for phase in zeta],
            [1, 1, 1, 1_236_316, 1],
        )
        self.assertIn("tg_platt_zeta_campaign.py", " ".join(zeta[0]["command"]))

        goldbach = jobs["helfgott-platt-theorem-4-1"]["phase_dag"]
        self.assertEqual(
            [phase["array_size"] for phase in goldbach],
            [1, 1, 8_192, 320, 1, 1, 1, 1],
        )
        self.assertIn(
            "tg_goldbach_gpu_campaign.py", " ".join(goldbach[0]["command"])
        )
        self.assertIn("create-production-plan", goldbach[0]["command"])
        self.assertNotIn("create-analytic-10pow27-plan", goldbach[0]["command"])
        self.assertEqual(goldbach[1]["depends_on"], [])
        self.assertIn("run-group", goldbach[2]["command"])
        self.assertEqual(goldbach[2]["max_concurrent_tasks"], 8)
        self.assertEqual(goldbach[2]["scheduler_shape"], "array[0..8191]%8")
        self.assertEqual(goldbach[2]["backend_class"], "h100_cuda")
        self.assertEqual(goldbach[2]["resources"]["h100_gpus"], 1)
        self.assertIn(
            "tg_goldbach_ladder_native.py", " ".join(goldbach[3]["command"])
        )
        self.assertIn("produce-group", goldbach[3]["command"])
        self.assertEqual(goldbach[3]["max_concurrent_tasks"], 8)
        self.assertEqual(goldbach[3]["scheduler_shape"], "array[0..319]%8")
        self.assertEqual(goldbach[3]["backend_class"], "cpu_exact_sidecar")
        self.assertEqual(goldbach[3]["resources"]["cpus_per_task"], 40)
        self.assertEqual(goldbach[3]["resources"]["h100_gpus"], 0)
        self.assertIn("40", goldbach[3]["command"])
        self.assertIn(
            "reduce-ranges", goldbach[6]["command"]
        )
        self.assertIn(
            "tg_goldbach_historical_finalizer.py",
            " ".join(goldbach[7]["command"]),
        )
        self.assertIn("--registered-result-output", goldbach[7]["command"])
        self.assertEqual(
            goldbach[7]["depends_on"],
            ["binary-semantic-replay", "reduce-prime-ladder-ranges"],
        )

        lowered = jobs[GOLDBACH_10POW27_ATOM]
        self.assertEqual(lowered["campaign_id"], GOLDBACH_10POW27_CAMPAIGN)
        self.assertNotEqual(
            lowered["campaign_id"],
            jobs["helfgott-platt-theorem-4-1"]["campaign_id"],
        )
        lowered_phases = lowered["phase_dag"]
        self.assertEqual(
            [phase["array_size"] for phase in lowered_phases],
            [1, 1, 8_192, 320, 1, 1, 1, 1],
        )
        self.assertIn(
            "create-analytic-10pow27-plan", lowered_phases[0]["command"]
        )
        self.assertIn(
            "tg_goldbach_10pow27_campaign.py",
            " ".join(lowered_phases[1]["command"]),
        )
        self.assertEqual(lowered_phases[2]["backend_class"], "h100_cuda")
        self.assertEqual(lowered_phases[2]["max_concurrent_tasks"], 8)
        terminal = lowered_phases[-1]
        self.assertEqual(
            terminal["depends_on"],
            [
                "replay-lowered-binary-aggregate",
                "reduce-lowered-prime-ladder-ranges",
            ],
        )
        self.assertEqual(terminal["backend_class"], "cpu_exact_sidecar")
        result_flag = terminal["command"].index("--registered-result-output")
        self.assertEqual(
            terminal["command"][result_flag + 1],
            "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/registered-result.txt",
        )
        self.assertEqual(
            terminal["completion_artifact"], terminal["command"][result_flag + 1]
        )

        cdem = jobs["cdem-table-abel"]["command"]
        self.assertIn("run-cdem-abel-full", cdem)
        self.assertIn(
            "${TG_REPOSITORY}/reference/tg_cdem_abel_chunk_replay.cpp", cdem
        )
        result_flag = cdem.index("--registered-result-output")
        self.assertEqual(
            cdem[result_flag + 1],
            "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt",
        )
        self.assertIn("verify-source", jobs[DIRICHLET_ATOM]["postcheck_command"])

    def test_one_hurst_campaign_supplies_four_logical_atoms(self) -> None:
        manifest = build_manifest(fake_repository_binding())
        hurst = next(
            campaign
            for campaign in manifest["physical_campaigns"]
            if campaign["campaign_id"] == "hurst-four-residuals-v1"
        )
        expected_atoms = {
            HURST_PRIMARY_ATOM,
            "cdem-squarefree",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        }
        self.assertEqual(set(hurst["logical_atom_ids"]), expected_atoms)
        self.assertEqual(hurst["owner_atom_id"], HURST_PRIMARY_ATOM)
        self.assertEqual(
            [phase["array_size"] for phase in hurst["phase_dag"]],
            [1, 320, 1, 320, 1, 1],
        )
        terminal = hurst["phase_dag"][-1]
        result_flag = terminal["command"].index("--registered-result-output")
        self.assertEqual(
            terminal["command"][result_flag + 1],
            "${TG_RUN_ROOT}/mertens-hurst/registered-result.txt",
        )
        self.assertEqual(
            terminal["completion_artifact"],
            "${TG_RUN_ROOT}/mertens-hurst/registered-result.txt",
        )
        jobs = {job["atom_id"]: job for job in manifest["jobs"]}
        for atom in expected_atoms:
            self.assertEqual(jobs[atom]["campaign_id"], "hurst-four-residuals-v1")
        for atom in expected_atoms - {HURST_PRIMARY_ATOM}:
            self.assertEqual(jobs[atom]["execution_mode"], "shared_certificate_alias")
            self.assertEqual(jobs[atom]["dependencies"], [HURST_PRIMARY_ATOM])
            self.assertFalse(any("mobius" in token for token in jobs[atom]["command"]))

    def test_dependency_edges_cover_zeta_and_hurst_aliases(self) -> None:
        manifest = build_manifest(fake_repository_binding())
        edges = {(edge["from"], edge["to"]): edge for edge in manifest["dependency_edges"]}
        self.assertIn((ZETA_Q1_ATOM, DIRICHLET_ATOM), edges)
        self.assertEqual(edges[(ZETA_Q1_ATOM, DIRICHLET_ATOM)]["scheduler_condition"], "afterok")
        for atom in (
            "cdem-squarefree",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        ):
            self.assertEqual(
                edges[(HURST_PRIMARY_ATOM, atom)]["scheduler_condition"],
                "certificate_present_and_semantic_replay",
            )

    def test_sample_pause_or_flattening_tampering_is_rejected(self) -> None:
        manifest = build_manifest(fake_repository_binding())
        manifest["jobs"][0]["sample"] = True
        with self.assertRaisesRegex(ClusterPlanError, "full-source"):
            validate_manifest(manifest)

        manifest = build_manifest(fake_repository_binding())
        manifest["jobs"][1]["phase_dag"][0]["command"].extend(
            ["--max-chunks", "1"]
        )
        with self.assertRaisesRegex(ClusterPlanError, "sample/pause"):
            validate_manifest(manifest)

        manifest = build_manifest(fake_repository_binding())
        manifest["jobs"][1]["command"] = ["pretend-all-phases-ran"]
        with self.assertRaisesRegex(ClusterPlanError, "must not flatten"):
            validate_manifest(manifest)

    def test_generated_adapters_and_manual_dags_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "deployment"
            result = _write_deployment_manifest(
                root, build_manifest(fake_repository_binding())
            )
            self.assertEqual(result["logical_atom_count"], 14)
            self.assertEqual(result["source_atom_count"], 13)
            self.assertEqual(result["physical_campaign_count"], 11)
            self.assertTrue(verify_deployment(root)["accepted"])
            self.assertEqual(len(list((root / "slurm" / "jobs").glob("*.sbatch"))), 8)
            self.assertEqual(
                len(list((root / "manual-phase-dags").glob("*.json"))), 6
            )
            for script in (root / "slurm").rglob("*.sh"):
                subprocess.run(["bash", "-n", str(script)], check=True)
            for script in (root / "slurm" / "jobs").glob("*.sbatch"):
                subprocess.run(["bash", "-n", str(script)], check=True)
            manual = json.loads(
                (root / "manual-phase-dags" / "ch25-psi-1e13.json").read_text()
            )
            self.assertFalse(manual["single_job_adapter_supported"])

            path = root / "manual-phase-dags" / "ch25-psi-1e13.json"
            path.write_text(path.read_text() + " ")
            with self.assertRaisesRegex(ClusterPlanError, "adapter differs"):
                verify_deployment(root)

    def test_all_atoms_and_manual_single_submit_fail_before_sbatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deployment = root / "deployment"
            _write_deployment_manifest(
                deployment, build_manifest(fake_repository_binding())
            )
            result = subprocess.run(
                ["bash", str(deployment / "slurm" / "submit.sh")],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 78)
            self.assertIn("explicit Slurm phase DAGs", result.stderr)

            result = subprocess.run(
                [
                    "bash",
                    str(deployment / "slurm" / "submit-one.sh"),
                    "ch25-psi-1e13",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 78)
            self.assertIn("explicit manual phase DAG", result.stderr)

    def test_clean_git_closure_rejects_dirty_or_untracked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            binding = initialize_clean_test_repository(root)
            self.assertEqual(binding["coverage"], "all_git_tracked_regular_files")
            (root / "tools" / "untracked_implementation.py").write_text("pass\n")
            with self.assertRaisesRegex(ClusterPlanError, "dirty or untracked"):
                inspect_clean_repository(root)

    def test_noncanonical_or_changed_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(
                json.dumps(build_manifest(fake_repository_binding()), indent=2) + "\n"
            )
            with self.assertRaisesRegex(ClusterPlanError, "not canonical"):
                load_manifest(path)

            value = build_manifest(fake_repository_binding())
            value["portfolio_partitioning"]["logical_atom_count"] = 12
            path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ClusterPlanError, "differs"):
                load_manifest(path)

    def test_alias_resolution_uses_no_shell_or_mobius_rescan(self) -> None:
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
            },
        )
        self.assertEqual(command[0], "/usr/bin/python3")
        self.assertEqual(
            command[1], str(REPOSITORY / "tools" / "tg_hurst_residual_campaign.py")
        )
        self.assertEqual(command[-2:], ("verify", "/shared/tg/mertens-hurst"))
        self.assertFalse(any("mobius" in token for token in command))
        with self.assertRaisesRegex(ClusterPlanError, "TG_RUN_ROOT"):
            resolve_command(job, {"TG_REPOSITORY": str(REPOSITORY)})

    def test_manual_execute_and_missing_dependency_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            binding = initialize_clean_test_repository(repository)
            deployment = root / "deployment"
            _write_deployment_manifest(deployment, build_manifest(binding))
            environment = {
                "TG_REPOSITORY": str(repository),
                "TG_RUN_ROOT": str(root / "runs"),
                "TG_PYTHON": "/usr/bin/python3",
            }
            with self.assertRaisesRegex(ClusterPlanError, "explicit phase DAG"):
                execute_job(
                    deployment / "manifest.json",
                    "ch25-psi-1e13",
                    environment=environment,
                    dry_run=True,
                )
            with self.assertRaisesRegex(ClusterPlanError, "dependency artifact"):
                execute_job(
                    deployment / "manifest.json",
                    DIRICHLET_ATOM,
                    environment=environment,
                    dry_run=True,
                )


if __name__ == "__main__":
    unittest.main()
