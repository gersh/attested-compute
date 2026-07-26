# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from tg_verifier.dirichlet_allchars_q_scheduler import (
    DirichletAllCharsQSchedulerError,
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    phase_schedule_projection,
    write_source_schedule_manifest,
)
from tg_verifier.dirichlet_completed_factor_artifacts import (
    ALGORITHM_ID as ARTIFACT_ALGORITHM_ID,
    CLASSIFICATION_FULL_SOURCE,
    FACTOR_CONVENTION_SHA256,
    CheckpointRecord,
    parse_checkpoint_artifact,
    parse_gamma_artifact,
    write_checkpoint_artifact,
    write_gamma_artifact,
    write_step_artifact,
)
from tg_verifier.dirichlet_completed_factor_service import (
    DirichletCompletedFactorServiceError,
    PINNED_PHASE_PLAN_SHA256,
    PINNED_PHASE_SCHEDULE_SHA256,
    PINNED_SOURCE_MANIFEST_SHA256,
    generate_gamma_job,
    generate_phase_job,
    generate_step_job,
    initialize_source_service,
    planner_identity,
    service_status,
)

def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


class ParsedPhaseProjectionTest(unittest.TestCase):
    def test_preparsed_manifest_has_identical_phase_commitment(self) -> None:
        raw = build_schedule_manifest_bytes(
            (
                ScheduleRecord(10_001, 3),
                ScheduleRecord(10_080, 5),
                ScheduleRecord(11_088, 4),
            )
        )
        parsed = parse_schedule_manifest(raw)
        arguments = {
            "phase_plan_sha256": "12" * 32,
            "first_t_index": 1,
            "t_index_stop_exclusive": 5,
        }
        from_raw = phase_schedule_projection(raw, **arguments)
        from_parsed = phase_schedule_projection(parsed, **arguments)
        self.assertEqual(from_parsed, from_raw)
        forged = replace(parsed, manifest_sha256="34" * 32)
        with self.assertRaisesRegex(
            DirichletAllCharsQSchedulerError, "differs from replay"
        ):
            phase_schedule_projection(forged, **arguments)


class DirichletCompletedFactorServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        producer_body = {
            "schema": (
                "sparkinterval.tg.dirichlet_completed_factor_artifacts."
                "arb_producer_identity.v1"
            ),
            "algorithm": ARTIFACT_ALGORITHM_ID,
            "factor_convention_sha256": FACTOR_CONVENTION_SHA256,
            "precision_bits": 128,
            "python_flint_version": "test-only",
            "flint_version": "test-only",
            "flint_release": 0,
            "sources": [
                {
                    "path": "test-only-nonanalytic-metadata-writer",
                    "sha256": "00" * 32,
                }
            ],
        }
        cls.producer_identity = {
            **producer_body,
            "producer_identity_sha256": hashlib.sha256(
                _canonical(producer_body)
            ).hexdigest(),
        }
        cls.producer_patch = patch(
            "tg_verifier.dirichlet_completed_factor_service."
            "arb_producer_identity",
            return_value=cls.producer_identity,
        )
        cls.producer_patch.start()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.schedule = cls.root / "schedule.bin"
        write_source_schedule_manifest(cls.schedule)
        cls.service = cls.root / "service"
        cls.initialization = initialize_source_service(
            cls.service,
            schedule_manifest=cls.schedule,
            precision=128,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
        cls.producer_patch.stop()

    def _copy_service(self, name: str) -> Path:
        destination = self.root / name
        shutil.copytree(self.service, destination)
        return destination

    def test_exact_plan_has_twelve_pending_jobs_and_no_run_claim(self) -> None:
        self.assertEqual(
            self.initialization["schedule_manifest_sha256"],
            PINNED_SOURCE_MANIFEST_SHA256,
        )
        status = service_status(self.service)
        self.assertEqual(status["job_count"], 12)
        self.assertEqual(status["complete_job_count"], 0)
        self.assertEqual(status["pending_job_count"], 12)
        plan = json.loads(
            (self.service / "source-plan.json").read_text("ascii")
        )
        self.assertEqual(len(plan["phase_jobs"]), 10)
        self.assertEqual(
            len({job["job_sha256"] for job in plan["phase_jobs"]}),
            10,
        )
        self.assertEqual(
            tuple(
                job["phase_plan_sha256"] for job in plan["phase_jobs"]
            ),
            PINNED_PHASE_PLAN_SHA256,
        )
        self.assertEqual(
            tuple(
                job["phase_schedule_sha256"]
                for job in plan["phase_jobs"]
            ),
            PINNED_PHASE_SCHEDULE_SHA256,
        )
        self.assertEqual(
            sum(
                job["checkpoint_count"]
                for job in plan["phase_jobs"]
            ),
            2_351_903,
        )
        self.assertEqual(
            sum(
                job["t_index_row_count"]
                for job in plan["phase_jobs"]
            ),
            3_637_613_167,
        )
        self.assertEqual(
            plan["gamma_job"]["expected_artifact_bytes"]
            + plan["step_job"]["expected_artifact_bytes"]
            + sum(
                job["expected_artifact_bytes"]
                for job in plan["phase_jobs"]
            ),
            101_834_360,
        )
        self.assertEqual(
            {
                source["path"]
                for source in plan["planner_identity"]["sources"]
            },
            {
                "tg_verifier/dirichlet_completed_factor_service.py",
                "tg_verifier/dirichlet_allchars_q_scheduler.py",
                "tg_verifier/dirichlet_resident_qmajor_plan.py",
                "tg_verifier/dirichlet_resident_qmajor_stream.py",
            },
        )
        planner_sha256 = plan["planner_identity"][
            "planner_identity_sha256"
        ]
        self.assertTrue(
            all(
                job["planner_identity_sha256"] == planner_sha256
                for job in (
                    plan["gamma_job"],
                    plan["step_job"],
                    *plan["phase_jobs"],
                )
            )
        )
        self.assertFalse(status["source_run_completed"])
        self.assertFalse(status["source_range_qualified"])
        self.assertFalse(status["trusted_execution_attested"])
        self.assertFalse(status["external_atom_discharged"])
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError, "12 pending"
        ):
            service_status(self.service, require_complete=True)

    def test_repaired_plan_self_hash_cannot_change_phase_geometry(self) -> None:
        service = self._copy_service("mutated-plan")
        path = service / "source-plan.json"
        plan = json.loads(path.read_text("ascii"))
        plan["phase_jobs"][9]["checkpoint_count"] += 1
        phase = dict(plan["phase_jobs"][9])
        phase.pop("job_sha256")
        plan["phase_jobs"][9]["job_sha256"] = hashlib.sha256(
            _canonical(phase)
        ).hexdigest()
        plan.pop("plan_sha256")
        plan["plan_sha256"] = hashlib.sha256(_canonical(plan)).hexdigest()
        path.write_bytes(_canonical(plan))
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError,
            "exact reconstruction",
        ):
            service_status(service)

    def test_changed_planner_identity_invalidates_existing_plan(self) -> None:
        changed = json.loads(_canonical(planner_identity()))
        changed["sources"][0]["sha256"] = "56" * 32
        changed.pop("planner_identity_sha256")
        changed["planner_identity_sha256"] = hashlib.sha256(
            _canonical(changed)
        ).hexdigest()
        with patch(
            "tg_verifier.dirichlet_completed_factor_service."
            "planner_identity",
            return_value=changed,
        ):
            with self.assertRaisesRegex(
                DirichletCompletedFactorServiceError,
                "exact reconstruction",
            ):
                service_status(self.service)

    def test_phase_job_requires_both_shared_jobs(self) -> None:
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError,
            "requires completed gamma and step",
        ):
            generate_phase_job(self.service, phase_index=9)

    def test_unknown_output_job_fails_closed(self) -> None:
        service = self._copy_service("unknown-output")
        (service / "outputs" / "unbound-job").mkdir()
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError, "unknown job"
        ):
            service_status(service)

    def test_symbolic_job_output_fails_closed(self) -> None:
        service = self._copy_service("symbolic-output")
        (service / "outputs" / "gamma").symlink_to(
            service / "staging",
            target_is_directory=True,
        )
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError,
            "not a real directory",
        ):
            service_status(service)

    def test_concurrent_gamma_publication_has_one_immutable_winner(
        self,
    ) -> None:
        service = self._copy_service("concurrent-gamma")
        unit = (1.0, 0.0, 0.0)
        barrier = threading.Barrier(2)

        def synchronized_gamma(path: Path, **arguments):
            count = 2 * (
                arguments["t_index_stop_exclusive"]
                - arguments["first_t_index"]
            )
            digest = write_gamma_artifact(
                path,
                first_t_index=arguments["first_t_index"],
                t_index_stop_exclusive=arguments[
                    "t_index_stop_exclusive"
                ],
                parity_major_disks=(unit,) * count,
                producer_identity_sha256=self.producer_identity[
                    "producer_identity_sha256"
                ],
                classification=arguments["classification"],
            )
            barrier.wait(timeout=10)
            return {
                **self.producer_identity,
                "artifact_sha256": digest,
            }

        with patch(
            "tg_verifier.dirichlet_completed_factor_service."
            "write_arb_gamma_artifact",
            side_effect=synchronized_gamma,
        ):
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = tuple(
                    workers.map(
                        lambda _index: generate_gamma_job(service),
                        range(2),
                    )
                )
        self.assertEqual(
            {result["status"] for result in results},
            {"generated", "already-complete"},
        )
        self.assertEqual(
            len(
                {
                    result["receipt"]["artifact_sha256"]
                    for result in results
                }
            ),
            1,
        )
        status = service_status(service)
        self.assertEqual(status["complete_job_count"], 1)
        self.assertEqual(status["pending_job_count"], 11)

    def test_exact_metadata_pipeline_with_nonanalytic_unit_writers(
        self,
    ) -> None:
        """Exercise publication/binding without pretending units are Arb."""

        service = self._copy_service("metadata-pipeline")
        unit = (1.0, 0.0, 0.0)

        def fake_gamma(path: Path, **arguments):
            identity = self.producer_identity
            count = 2 * (
                arguments["t_index_stop_exclusive"]
                - arguments["first_t_index"]
            )
            digest = write_gamma_artifact(
                path,
                first_t_index=arguments["first_t_index"],
                t_index_stop_exclusive=arguments[
                    "t_index_stop_exclusive"
                ],
                parity_major_disks=(unit,) * count,
                producer_identity_sha256=identity[
                    "producer_identity_sha256"
                ],
                classification=arguments["classification"],
            )
            return {**identity, "artifact_sha256": digest}

        def fake_steps(path: Path, **arguments):
            identity = self.producer_identity
            digest = write_step_artifact(
                path,
                q_start=arguments["q_start"],
                q_stop=arguments["q_stop"],
                execution_disks=(unit,) * len(arguments["execution_qs"]),
                schedule_manifest_sha256=arguments[
                    "schedule_manifest_sha256"
                ],
                execution_order_sha256=arguments[
                    "execution_order_sha256"
                ],
                classification=arguments["classification"],
            )
            return {**identity, "artifact_sha256": digest}

        def fake_checkpoints(path: Path, **arguments):
            identity = self.producer_identity
            span = arguments["checkpoint_span"]
            records = tuple(
                CheckpointRecord(
                    q=q,
                    sample_count=samples,
                    checkpoints=(unit,)
                    * ((samples + span - 1) // span),
                )
                for q, samples in arguments["q_sample_counts"]
            )
            digest = write_checkpoint_artifact(
                path,
                phase_index=arguments["phase_index"],
                first_t_index=arguments["first_t_index"],
                t_index_stop_exclusive=arguments[
                    "t_index_stop_exclusive"
                ],
                checkpoint_span=span,
                records=records,
                schedule_manifest_sha256=arguments[
                    "schedule_manifest_sha256"
                ],
                phase_schedule_sha256=arguments[
                    "phase_schedule_sha256"
                ],
                gamma_artifact_sha256=arguments[
                    "gamma_artifact_sha256"
                ],
                step_artifact_sha256=arguments[
                    "step_artifact_sha256"
                ],
                classification=CLASSIFICATION_FULL_SOURCE,
            )
            return {**identity, "artifact_sha256": digest}

        with (
            patch(
                "tg_verifier.dirichlet_completed_factor_service."
                "write_arb_gamma_artifact",
                side_effect=fake_gamma,
            ),
            patch(
                "tg_verifier.dirichlet_completed_factor_service."
                "write_arb_step_artifact",
                side_effect=fake_steps,
            ),
            patch(
                "tg_verifier.dirichlet_completed_factor_service."
                "write_arb_checkpoint_artifact",
                side_effect=fake_checkpoints,
            ),
        ):
            self.assertEqual(
                generate_gamma_job(service)["status"], "generated"
            )
            self.assertEqual(
                generate_step_job(service)["status"], "generated"
            )
            self.assertEqual(
                generate_phase_job(service, phase_index=9)["status"],
                "generated",
            )
            self.assertEqual(
                generate_phase_job(service, phase_index=9)["status"],
                "already-complete",
            )

        status = service_status(service)
        self.assertEqual(status["complete_job_count"], 3)
        self.assertEqual(status["pending_job_count"], 9)
        phase = status["jobs"][-1]
        self.assertEqual(phase["phase_index"], 9)
        self.assertEqual(phase["status"], "complete")
        self.assertFalse(status["source_run_completed"])
        self.assertFalse(status["external_atom_discharged"])
        plan = json.loads(
            (service / "source-plan.json").read_text("ascii")
        )
        gamma_receipt = json.loads(
            (
                service / "outputs" / "gamma" / "receipt.json"
            ).read_text("ascii")
        )
        step_receipt = json.loads(
            (
                service / "outputs" / "steps" / "receipt.json"
            ).read_text("ascii")
        )
        phase_receipt = json.loads(
            (
                service / "outputs" / "phase-09" / "receipt.json"
            ).read_text("ascii")
        )
        gamma_wire = parse_gamma_artifact(
            service / "outputs" / "gamma" / "artifact.bin",
            expected_sha256=gamma_receipt["artifact_sha256"],
        )
        checkpoint_wire = parse_checkpoint_artifact(
            service / "outputs" / "phase-09" / "artifact.bin",
            expected_sha256=phase_receipt["artifact_sha256"],
        )
        self.assertEqual(
            gamma_wire.producer_identity_sha256,
            plan["producer_identity"]["producer_identity_sha256"],
        )
        self.assertEqual(
            checkpoint_wire.gamma_artifact_sha256,
            gamma_receipt["artifact_sha256"],
        )
        self.assertEqual(
            checkpoint_wire.step_artifact_sha256,
            step_receipt["artifact_sha256"],
        )
        self.assertEqual(
            phase_receipt["producer_identity_sha256"],
            gamma_wire.producer_identity_sha256,
        )
        self.assertEqual(
            phase_receipt["planner_identity_sha256"],
            plan["planner_identity"]["planner_identity_sha256"],
        )

        gamma_artifact = (
            service / "outputs" / "gamma" / "artifact.bin"
        )
        original_gamma = gamma_artifact.read_bytes()

        def mutate_shared_after_checkpoint(path: Path, **arguments):
            report = fake_checkpoints(path, **arguments)
            changed = bytearray(original_gamma)
            changed[-1] ^= 1
            gamma_artifact.write_bytes(changed)
            return report

        try:
            with patch(
                "tg_verifier.dirichlet_completed_factor_service."
                "write_arb_checkpoint_artifact",
                side_effect=mutate_shared_after_checkpoint,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "gamma artifact SHA-256 differs"
                ):
                    generate_phase_job(service, phase_index=8)
        finally:
            gamma_artifact.write_bytes(original_gamma)
        self.assertFalse((service / "outputs" / "phase-08").exists())

        phase_receipt_path = (
            service / "outputs" / "phase-09" / "receipt.json"
        )
        original_receipt = phase_receipt_path.read_bytes()
        receipt = json.loads(original_receipt)
        receipt["gamma_receipt_sha256"] = "ab" * 32
        receipt.pop("receipt_sha256")
        receipt["receipt_sha256"] = hashlib.sha256(
            _canonical(receipt)
        ).hexdigest()
        phase_receipt_path.write_bytes(_canonical(receipt))
        with self.assertRaisesRegex(
            DirichletCompletedFactorServiceError, "receipt differs"
        ):
            service_status(service)
        phase_receipt_path.write_bytes(original_receipt)

        step_artifact = (
            service / "outputs" / "steps" / "artifact.bin"
        )
        raw = bytearray(step_artifact.read_bytes())
        raw[-1] ^= 1
        step_artifact.write_bytes(raw)
        with self.assertRaises(Exception):
            service_status(service)


if __name__ == "__main__":
    unittest.main()
