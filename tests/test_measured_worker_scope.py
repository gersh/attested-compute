# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tiny tests for the cloud-only production execution-scope guard."""

from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from tg_verifier.campaign_io import (
    AZURE_MEASURED_WORKER_BACKEND_ENV,
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    AZURE_MEASURED_WORKER_SCOPE,
    AZURE_MEASURED_WORKER_SCOPE_ENV,
    MeasuredWorkerScopeError,
    azure_measured_worker_environment,
    require_azure_measured_worker,
)


CHALLENGE = "1" * 64
JOB_BINDING = "2" * 64
ROOT = Path(__file__).resolve().parents[1]


class MeasuredWorkerScopeTest(unittest.TestCase):
    def test_ordinary_local_environment_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            MeasuredWorkerScopeError, "production arithmetic/replay is cloud-only"
        ):
            require_azure_measured_worker(
                challenge_nonce=CHALLENGE,
                job_binding=JOB_BINDING,
                environment={},
            )

    def test_runner_injected_cpu_scope_is_accepted(self) -> None:
        environment = azure_measured_worker_environment(
            {"LANG": "C"},
            backend="azure_sevsnp_cpu",
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        self.assertEqual(
            require_azure_measured_worker(
                challenge_nonce=CHALLENGE,
                job_binding=JOB_BINDING,
                environment=environment,
            ),
            "azure_sevsnp_cpu",
        )
        self.assertEqual(environment["LANG"], "C")
        self.assertEqual(
            environment[AZURE_MEASURED_WORKER_SCOPE_ENV],
            AZURE_MEASURED_WORKER_SCOPE,
        )

    def test_runner_injected_h100_scope_is_accepted(self) -> None:
        environment = azure_measured_worker_environment(
            {},
            backend="azure_ncc40ads_h100_v5",
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        self.assertEqual(
            require_azure_measured_worker(
                challenge_nonce=CHALLENGE,
                job_binding=JOB_BINDING,
                environment=environment,
            ),
            "azure_ncc40ads_h100_v5",
        )

    def test_scope_is_bound_to_exact_challenge_and_job(self) -> None:
        environment = azure_measured_worker_environment(
            {},
            backend="azure_sevsnp_cpu",
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        for challenge, binding in (
            ("3" * 64, JOB_BINDING),
            (CHALLENGE, "4" * 64),
        ):
            with self.subTest(challenge=challenge, binding=binding):
                with self.assertRaises(MeasuredWorkerScopeError):
                    require_azure_measured_worker(
                        challenge_nonce=challenge,
                        job_binding=binding,
                        environment=environment,
                    )

    def test_job_cannot_preseed_runner_reserved_scope(self) -> None:
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            with self.subTest(key=key):
                with self.assertRaisesRegex(
                    MeasuredWorkerScopeError, "runner-reserved"
                ):
                    azure_measured_worker_environment(
                        {key: "attacker-selected"},
                        backend="azure_sevsnp_cpu",
                        challenge_nonce=CHALLENGE,
                        job_binding=JOB_BINDING,
                    )

    def test_scope_has_all_four_exact_bindings(self) -> None:
        environment = azure_measured_worker_environment(
            {},
            backend="azure_sevsnp_cpu",
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        self.assertEqual(
            {
                AZURE_MEASURED_WORKER_SCOPE_ENV,
                AZURE_MEASURED_WORKER_BACKEND_ENV,
                AZURE_MEASURED_WORKER_CHALLENGE_ENV,
                AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
            },
            set(environment),
        )

    def test_guarded_production_clis_stop_before_reading_artifacts(self) -> None:
        environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            environment.pop(key, None)
        common = [
            "run",
            "--challenge",
            CHALLENGE,
            "--job-binding",
            JOB_BINDING,
            "--input",
            "absent-input",
            "--output",
            "absent-output",
            "--trace",
            "absent-trace",
            "--wheel",
            "absent-wheel",
            "--work",
            "absent-work",
        ]
        commands = (
            [
                sys.executable,
                str(ROOT / "tools/tg_a7_azure_measured_workload.py"),
                *common[:1],
                "--algorithm-id",
                "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1",
                *common[1:],
                "--artifact",
                "absent-artifact",
            ],
            [
                sys.executable,
                str(ROOT / "tools/tg_platt_head_azure_measured_workload.py"),
                *common[:1],
                "--algorithm-id",
                "sparkinterval.ternary-goldbach.platt-head-2e4.v1",
                *common[1:],
            ],
        )
        for command in commands:
            with self.subTest(script=command[1]):
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn(
                    b"production arithmetic/replay is cloud-only",
                    completed.stderr,
                )
                self.assertNotIn(b"absent-input", completed.stderr)

    def test_remaining_production_entry_points_fail_before_artifact_access(
        self,
    ) -> None:
        """Every full run/replay/postcheck is guarded inside its callable."""

        class GuardOnlyArguments:
            challenge = CHALLENGE
            job_binding = JOB_BINDING
            mode = "run"

            def __getattr__(self, name: str) -> object:
                raise AssertionError(
                    f"artifact argument {name!r} was accessed before the guard"
                )

        workloads = {
            "dirichlet": (
                "tg_dirichlet_azure_measured_workload.py",
                (
                    "run",
                    "verify_trace",
                    "postcheck",
                    "verify_postcheck_trace",
                    "run_packed_smallq",
                    "verify_packed_smallq_trace",
                ),
            ),
            "goldbach-10pow27-cpu": (
                "tg_goldbach_10pow27_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "goldbach-10pow27-h100": (
                "tg_goldbach_10pow27_h100_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "goldbach-historical-cpu": (
                "tg_goldbach_historical_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "goldbach-historical-h100": (
                "tg_goldbach_historical_h100_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "goldbach-historical-operational": (
                "tg_goldbach_historical_operational_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "hurst": (
                "tg_hurst_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "platt-pt21": (
                "tg_platt_pt21_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "prop1224": (
                "tg_prop1224_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "psi": (
                "tg_psi_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
            "r2star": (
                "tg_r2star_azure_measured_workload.py",
                ("run", "verify_trace"),
            ),
        }
        clean_environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            clean_environment.pop(key, None)
        for workload, (filename, entry_points) in workloads.items():
            path = ROOT / "tools" / filename
            spec = importlib.util.spec_from_file_location(
                f"_measured_scope_test_{workload}", path
            )
            if spec is None or spec.loader is None:
                self.fail(f"cannot import measured workload {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for entry_point in entry_points:
                with self.subTest(
                    workload=workload,
                    entry_point=entry_point,
                ), mock.patch.dict(os.environ, clean_environment, clear=True):
                    with self.assertRaisesRegex(
                        MeasuredWorkerScopeError,
                        "production arithmetic/replay is cloud-only",
                    ):
                        getattr(module, entry_point)(GuardOnlyArguments())
            fake_parser = mock.Mock()
            fake_parser.parse_args.return_value = GuardOnlyArguments()
            if workload == "dirichlet":
                parser_patch = mock.patch.object(
                    module.argparse.ArgumentParser,
                    "parse_args",
                    return_value=GuardOnlyArguments(),
                )
            else:
                parser_patch = mock.patch.object(
                    module,
                    "parser",
                    return_value=fake_parser,
                )
            stderr = io.StringIO()
            with self.subTest(
                workload=workload,
                entry_point="main",
            ), parser_patch, mock.patch.dict(
                os.environ, clean_environment, clear=True
            ), redirect_stderr(stderr):
                self.assertEqual(module.main(), 2)
            self.assertIn(
                "production arithmetic/replay is cloud-only",
                stderr.getvalue(),
            )

    def test_package_only_modes_remain_local(self) -> None:
        """Packaging signed H100 receipts performs no production arithmetic."""

        clean_environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            clean_environment.pop(key, None)
        for workload, filename in (
            (
                "goldbach-10pow27-cpu",
                "tg_goldbach_10pow27_azure_measured_workload.py",
            ),
            (
                "goldbach-historical-operational",
                "tg_goldbach_historical_operational_azure_measured_workload.py",
            ),
        ):
            path = ROOT / "tools" / filename
            spec = importlib.util.spec_from_file_location(
                f"_package_scope_test_{workload}", path
            )
            if spec is None or spec.loader is None:
                self.fail(f"cannot import measured workload {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            arguments = mock.Mock(
                mode="package-h100",
                plan=Path("plan"),
                receipts_dir=Path("receipts"),
                signed_receipt=Path("signed-receipt"),
                group_index=0,
                key_manifest=Path("key-manifest"),
                build_admission=Path("build-admission"),
                output=Path("package"),
            )
            fake_parser = mock.Mock()
            fake_parser.parse_args.return_value = arguments
            stdout = mock.Mock(buffer=io.BytesIO())
            with self.subTest(workload=workload), mock.patch.object(
                module, "parser", return_value=fake_parser
            ), mock.patch.object(
                module, "package_h100_export", return_value={"packaged": True}
            ) as package, mock.patch.object(
                module.sys, "stdout", stdout
            ), mock.patch.dict(
                os.environ, clean_environment, clear=True
            ):
                self.assertEqual(module.main(), 0)
                package.assert_called_once()


if __name__ == "__main__":
    unittest.main()
