# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PINNED_PYTHON = Path("/tmp/tg-flint-venv/bin/python")
ALLCHARS = (
    ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars"
)
MPFR_CHECKER = (
    ROOT
    / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"
)

from tests.tg_dirichlet_residue_composition_fixture import (  # noqa: E402
    rehash_job_artifact,
    write_job,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (  # noqa: E402
    ScheduleRecord,
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
)
from tg_verifier.dirichlet_allchars_stage import INPUT_HEADER  # noqa: E402
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    FRAMED_REQUEST_SCHEMA,
    canonical_json_bytes,
)
from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    RECOVERY_HEADER,
    RECOVERY_ITEM,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    OUTPUT_HEADER as LATTICE_OUTPUT_HEADER,
    OUTPUT_ITEM as LATTICE_OUTPUT_ITEM,
)
from tg_verifier.dirichlet_root_catalog import (  # noqa: E402
    root_artifact_filename,
    root_receipt_filename,
)
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    ROOT_ALGORITHM_ID,
)
from tg_verifier.dirichlet_scheduled_largeq_pipeline import (  # noqa: E402
    DirichletScheduledPipelineError,
    _check_invocation_artifact_record,
    _invocation_artifact_record,
    _prepare_empty_output_directory,
    _run_bounded_process,
    _validate_consumer_event_binding,
    _validate_tee_receipt,
    _wait_fail_fast,
    replay_scheduled_pipeline,
    run_scheduled_pipeline,
    sha256_bytes,
    validate_scheduled_control_alignment,
)
from tg_verifier.dirichlet_stream_zero_consumer import (  # noqa: E402
    make_control,
)


def upstream() -> dict[str, str]:
    return {
        "all_character_transform_input_sha256": "1" * 64,
        "finite_addback_receipt_sha256": "2" * 64,
        "lattice_tail_receipt_sha256": "3" * 64,
        "residue_adapter_receipt_sha256": "4" * 64,
    }


class DirichletScheduledPipelineStructuralTest(unittest.TestCase):
    SOURCE_QS = (10_001, 10_003, 10_004, 10_005)

    def _controls(self, root: Path) -> tuple[Path, Path, Path, tuple[int, ...]]:
        schedule_path = root / "schedule.bin"
        schedule_path.write_bytes(
            build_schedule_manifest_bytes(
                tuple(ScheduleRecord(q, 1) for q in self.SOURCE_QS)
            )
        )
        schedule = parse_schedule_manifest(schedule_path)
        execution = tuple(row.q for row in schedule.execution_records)
        composition_rows = []
        consumer_rows = []
        for frame_index, q in enumerate(execution):
            job, _frames = write_job(
                root / f"q-{q}" / "job", q=q, t_indices=(0,)
            )
            composition_rows.append(
                canonical_json_bytes(
                    {
                        "schema": FRAMED_REQUEST_SCHEMA,
                        "schema_version": 1,
                        "job": str(job),
                        "receipt": str(
                            root / f"q-{q}" / "composition.receipt.json"
                        ),
                    }
                )
            )
            consumer_rows.append(
                canonical_json_bytes(
                    make_control(
                        frame_index=frame_index,
                        q=q,
                        batch_count=1,
                        first_t_numerator=0,
                        t_denominator=64,
                        t_step_numerator=5,
                        upstream_receipts=upstream(),
                        root_number_mode=ROOT_ALGORITHM_ID,
                    )
                )
            )
        composition = root / "composition.ndjson"
        consumer = root / "consumer.ndjson"
        composition.write_bytes(b"".join(composition_rows))
        consumer.write_bytes(b"".join(consumer_rows))
        return composition, consumer, schedule_path, execution

    def test_exact_nonmonotone_q_and_t_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, consumer, schedule, execution = self._controls(root)
            self.assertEqual(execution, (10_005, 10_004, 10_001, 10_003))
            result = validate_scheduled_control_alignment(
                composition,
                consumer,
                schedule_manifest_path=schedule,
                base=root,
                maximum_batch_count=1,
                allow_synthetic_kat=True,
            )
            self.assertEqual(result.first_q, 10_005)
            self.assertEqual(result.last_q, 10_003)
            self.assertEqual(result.slice_count, 4)
            self.assertEqual(result.schedule.t_row_count, 4)

    def test_actual_producer_binds_manifest_and_emits_execution_qs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, _consumer, schedule_path, execution = self._controls(
                root
            )
            summary_path = root / "producer-summary.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "tests/tg_dirichlet_residue_composition_kat_worker.py"
                    ),
                    "--max-batch-count",
                    "1",
                    "framed-produce",
                    str(summary_path),
                    "--base",
                    str(root),
                    "--allow-synthetic-kat",
                    "--schedule-manifest",
                    str(schedule_path),
                ],
                input=composition.read_bytes(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            q_values = []
            offset = 0
            while offset < len(completed.stdout):
                header = INPUT_HEADER.unpack_from(completed.stdout, offset)
                q_values.append(header[2])
                offset += INPUT_HEADER.size + header[9] * 32
            self.assertEqual(tuple(q_values), execution)
            self.assertEqual(offset, len(completed.stdout))
            summary = json.loads(summary_path.read_bytes())
            manifest = parse_schedule_manifest(schedule_path)
            self.assertEqual(
                summary["schedule_manifest_sha256"],
                manifest.manifest_sha256,
            )
            self.assertEqual(summary["scheduled_t_index_rows"], 4)
            self.assertTrue(summary["TGDQORD1_exact_coverage"])

    def test_source_order_and_incomplete_q_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, consumer, schedule, _execution = self._controls(root)
            composition_rows = composition.read_bytes().splitlines(
                keepends=True
            )
            consumer_rows = consumer.read_bytes().splitlines(keepends=True)
            composition.write_bytes(b"".join(reversed(composition_rows)))
            reordered_controls = []
            for frame_index, raw in enumerate(reversed(consumer_rows)):
                value = json.loads(raw)
                value["frame_index"] = frame_index
                reordered_controls.append(canonical_json_bytes(value))
            consumer.write_bytes(b"".join(reordered_controls))
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "execution order"
            ):
                validate_scheduled_control_alignment(
                    composition,
                    consumer,
                    schedule_manifest_path=schedule,
                    base=root,
                    maximum_batch_count=1,
                    allow_synthetic_kat=True,
                )

            composition.write_bytes(b"".join(composition_rows[:-1]))
            consumer.write_bytes(b"".join(consumer_rows[:-1]))
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "exactly cover"
            ):
                validate_scheduled_control_alignment(
                    composition,
                    consumer,
                    schedule_manifest_path=schedule,
                    base=root,
                    maximum_batch_count=1,
                    allow_synthetic_kat=True,
                )

    def test_fail_fast_monitor_cancels_sibling(self) -> None:
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        failure = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(7)"]
        )
        started = time.monotonic()
        with self.assertRaisesRegex(
            DirichletScheduledPipelineError, "process failed"
        ):
            _wait_fail_fast(
                (("sleeper", sleeper), ("failure", failure)),
                timeout_seconds=5,
            )
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(sleeper.returncode)
        self.assertIsNotNone(failure.returncode)

    def test_bounded_tee_fails_before_publishing_oversize_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_bounded_stream_tee.py"),
                    str(root / "capture.bin"),
                    str(root / "receipt.json"),
                    "3",
                    "TGDAFFI1",
                    "a" * 64,
                ],
                input=b"four",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((root / "capture.bin").exists())
            self.assertFalse((root / "receipt.json").exists())

    def test_output_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            linked = root / "linked"
            linked.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "cannot be a symlink"
            ):
                _prepare_empty_output_directory(linked)

    def test_tee_receipt_requires_exact_schema_and_configured_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule = parse_schedule_manifest(
                build_schedule_manifest_bytes((ScheduleRecord(10_001, 1),))
            )
            capture = root / "capture.bin"
            receipt = root / "receipt.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_bounded_stream_tee.py"),
                    str(capture),
                    str(receipt),
                    "16",
                    "TGDAFFI1",
                    schedule.manifest_sha256,
                ],
                input=b"abc",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            _validate_tee_receipt(
                receipt,
                role="TGDAFFI1",
                schedule=schedule,
                capture=capture,
                maximum_capture_bytes=16,
            )

            value = json.loads(receipt.read_bytes())
            value["unexpected"] = True
            value.pop("receipt_sha256")
            value["receipt_sha256"] = sha256_bytes(canonical_json_bytes(value))
            receipt.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "tee receipt differs"
            ):
                _validate_tee_receipt(
                    receipt,
                    role="TGDAFFI1",
                    schedule=schedule,
                    capture=capture,
                    maximum_capture_bytes=16,
                )

            value.pop("unexpected")
            value["maximum_stream_bytes"] = 3
            value.pop("receipt_sha256")
            value["receipt_sha256"] = sha256_bytes(canonical_json_bytes(value))
            receipt.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "tee receipt differs"
            ):
                _validate_tee_receipt(
                    receipt,
                    role="TGDAFFI1",
                    schedule=schedule,
                    capture=capture,
                    maximum_capture_bytes=16,
                )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_bounded_stream_tee.py"),
                    str(root / "one-byte.capture.bin"),
                    str(root / "one-byte.receipt.json"),
                    "1",
                    "TGDAFFI1",
                    schedule.manifest_sha256,
                ],
                input=b"x",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            one_byte_receipt = root / "one-byte.receipt.json"
            value = json.loads(one_byte_receipt.read_bytes())
            value["stream_size_bytes"] = True
            value["maximum_stream_bytes"] = True
            value.pop("receipt_sha256")
            value["receipt_sha256"] = sha256_bytes(
                canonical_json_bytes(value)
            )
            one_byte_receipt.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "tee receipt differs"
            ):
                _validate_tee_receipt(
                    one_byte_receipt,
                    role="TGDAFFI1",
                    schedule=schedule,
                    capture=root / "one-byte.capture.bin",
                    maximum_capture_bytes=1,
                )

    def test_consumer_event_digest_and_size_are_directly_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.ndjson"
            events.write_bytes(b"\n")
            receipt = {
                "events_sha256": hashlib.sha256(events.read_bytes()).hexdigest(),
                "events_bytes": events.stat().st_size,
            }
            _validate_consumer_event_binding(receipt, events)
            receipt["events_bytes"] = True
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError,
                "event digest or size differs",
            ):
                _validate_consumer_event_binding(receipt, events)
            receipt["events_bytes"] = 1
            events.write_bytes(b"{}\n{}\n")
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError,
                "event digest or size differs",
            ):
                _validate_consumer_event_binding(receipt, events)

    def test_invocation_artifact_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tool = Path(temporary) / "tool.py"
            tool.write_bytes(b"print('first')\n")
            record = _invocation_artifact_record(tool, label="test tool")
            _check_invocation_artifact_record(record, label="test tool")
            malformed = json.loads(canonical_json_bytes(record))
            malformed["resolved_artifact"]["size_bytes"] = float(
                malformed["resolved_artifact"]["size_bytes"]
            )
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError,
                "artifact record differs",
            ):
                _check_invocation_artifact_record(
                    malformed, label="test tool"
                )
            tool.write_bytes(b"print('other')\n")
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError,
                "changed from its receipt",
            ):
                _check_invocation_artifact_record(record, label="test tool")

    def test_process_group_cancellation_reaches_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child_pid = root / "child.pid"
            child_ready = root / "child.ready"
            child_terminated = root / "child.terminated"
            child_code = (
                "from pathlib import Path\n"
                "import signal,time\n"
                f"ready=Path({str(child_ready)!r})\n"
                f"terminated=Path({str(child_terminated)!r})\n"
                "def stop(*_args):\n"
                "    terminated.write_text('terminated')\n"
                "    raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "ready.write_text('ready')\n"
                "time.sleep(30)\n"
            )
            parent_code = (
                "from pathlib import Path\n"
                "import subprocess,sys,time\n"
                f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
                f"Path({str(child_pid)!r}).write_text(str(child.pid))\n"
                "time.sleep(30)\n"
            )
            parent = subprocess.Popen(
                [sys.executable, "-c", parent_code],
                start_new_session=True,
            )
            deadline = time.monotonic() + 5
            while (
                (not child_pid.exists() or not child_ready.exists())
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertTrue(child_pid.is_file())
            self.assertTrue(child_ready.is_file())
            failure = subprocess.Popen(
                [sys.executable, "-c", "raise SystemExit(7)"],
                start_new_session=True,
            )
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "process failed"
            ):
                _wait_fail_fast(
                    (("parent", parent), ("failure", failure)),
                    timeout_seconds=5,
                    isolated_process_groups=True,
                )
            self.assertTrue(child_terminated.is_file())
            child = int(child_pid.read_text())
            proc_stat = Path(f"/proc/{child}/stat")
            if proc_stat.is_file():
                # A terminated orphan may remain briefly as a zombie until its
                # new parent reaps it; it must not remain a running process.
                self.assertEqual(proc_stat.read_text().split()[2], "Z")

    def test_explicit_timeout_cancels_process_group(self) -> None:
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        started = time.monotonic()
        with self.assertRaisesRegex(
            DirichletScheduledPipelineError, "explicit process timeout"
        ):
            _wait_fail_fast(
                (("sleeper", sleeper),),
                timeout_seconds=0.05,
                isolated_process_groups=True,
            )
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(sleeper.returncode)

    def test_bounded_process_reaps_descendants_after_leader_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def command(name: str, return_code: int) -> tuple[list[str], Path]:
                child_pid = root / f"{name}.pid"
                child_ready = root / f"{name}.ready"
                child_code = (
                    "from pathlib import Path\n"
                    "import os,signal,time\n"
                    f"ready=Path({str(child_ready)!r})\n"
                    "signal.signal(signal.SIGTERM,"
                    " lambda *_args: os._exit(0))\n"
                    "ready.write_text('ready')\n"
                    "time.sleep(30)\n"
                )
                parent_code = (
                    "from pathlib import Path\n"
                    "import subprocess,sys,time\n"
                    "child=subprocess.Popen("
                    f"[sys.executable,'-c',{child_code!r}])\n"
                    f"Path({str(child_pid)!r}).write_text(str(child.pid))\n"
                    f"ready=Path({str(child_ready)!r})\n"
                    "deadline=time.monotonic()+5\n"
                    "while not ready.exists() and time.monotonic()<deadline:\n"
                    "    time.sleep(.01)\n"
                    f"raise SystemExit({return_code})\n"
                )
                return [sys.executable, "-c", parent_code], child_pid

            failed_command, failed_child_pid = command("failed", 7)
            completed = _run_bounded_process(
                failed_command,
                label="failing descendant worker",
                timeout_seconds=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertEqual(completed.returncode, 7)
            self._assert_not_running(failed_child_pid)

            successful_command, successful_child_pid = command("success", 0)
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError,
                "surviving descendants",
            ):
                _run_bounded_process(
                    successful_command,
                    label="successful descendant worker",
                    timeout_seconds=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            self._assert_not_running(successful_child_pid)

    @staticmethod
    def _assert_not_running(pid_path: Path) -> None:
        child = int(pid_path.read_text())
        proc_stat = Path(f"/proc/{child}/stat")
        if proc_stat.is_file():
            if proc_stat.read_text().split()[2] != "Z":
                raise AssertionError(f"descendant {child} remains running")


@unittest.skipUnless(
    PINNED_PYTHON.is_file() and ALLCHARS.is_file() and MPFR_CHECKER.is_file(),
    "requires pinned FLINT and built CUDA/MPFR all-character runners",
)
class DirichletScheduledPipelineProcessKat(unittest.TestCase):
    SOURCE_QS = (10_001, 10_003, 10_004, 10_005)

    @staticmethod
    def _hull_payload(path: Path, *, header: object, item: object) -> None:
        raw = bytearray(path.read_bytes())
        if (len(raw) - header.size) % item.size:
            raise AssertionError("fixture interval geometry differs")
        for offset in range(header.size, len(raw), item.size):
            fields = list(item.unpack_from(raw, offset))
            fields[-4] = min(fields[-4], 0.0)
            fields[-3] = max(fields[-3], 0.0)
            fields[-2] = min(fields[-2], 0.0)
            fields[-1] = max(fields[-1], 0.0)
            item.pack_into(raw, offset, *fields)
        path.write_bytes(raw)

    def _fixture(
        self, root: Path
    ) -> tuple[Path, Path, Path, Path, Path, str]:
        schedule_path = root / "schedule.bin"
        schedule_path.write_bytes(
            build_schedule_manifest_bytes(
                tuple(ScheduleRecord(q, 1) for q in self.SOURCE_QS)
            )
        )
        schedule = parse_schedule_manifest(schedule_path)
        composition_rows = []
        consumer_rows = []
        for frame_index, record in enumerate(schedule.execution_records):
            q = record.q
            target = root / f"q-{q}"
            job, frames = write_job(
                target / "job", q=q, t_indices=(0,)
            )
            self._hull_payload(
                frames[0]["lattice_output"],
                header=LATTICE_OUTPUT_HEADER,
                item=LATTICE_OUTPUT_ITEM,
            )
            self._hull_payload(
                frames[0]["finite_recovery"],
                header=RECOVERY_HEADER,
                item=RECOVERY_ITEM,
            )
            rehash_job_artifact(job, 0, "lattice_output")
            rehash_job_artifact(job, 0, "finite_recovery")
            composition_rows.append(
                canonical_json_bytes(
                    {
                        "schema": FRAMED_REQUEST_SCHEMA,
                        "schema_version": 1,
                        "job": str(job),
                        "receipt": str(target / "composition.receipt.json"),
                    }
                )
            )
            consumer_rows.append(
                canonical_json_bytes(
                    make_control(
                        frame_index=frame_index,
                        q=q,
                        batch_count=1,
                        first_t_numerator=0,
                        t_denominator=64,
                        t_step_numerator=5,
                        upstream_receipts=upstream(),
                        root_number_mode=ROOT_ALGORITHM_ID,
                    )
                )
            )
        composition = root / "composition.ndjson"
        consumer = root / "consumer.ndjson"
        composition.write_bytes(b"".join(composition_rows))
        consumer.write_bytes(b"".join(consumer_rows))

        roots = root / "roots"
        roots.mkdir()
        root_worker = (
            ROOT / "tests/tg_dirichlet_root_number_kat_worker.py"
        )
        for q in self.SOURCE_QS:
            q_root = root / f"root-work-{q}"
            q_root.mkdir()
            additive_input = q_root / "additive.bin"
            additive_receipt = q_root / "additive.receipt.json"
            transform = q_root / "transform.bin"
            subprocess.run(
                [
                    str(PINNED_PYTHON),
                    str(root_worker),
                    "additive-input",
                    str(additive_input),
                    str(additive_receipt),
                    "--q",
                    str(q),
                    "--precision",
                    "192",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    str(MPFR_CHECKER),
                    "compute",
                    str(additive_input),
                    str(transform),
                    "192",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    str(PINNED_PYTHON),
                    str(root_worker),
                    "consume",
                    str(transform),
                    str(roots / root_artifact_filename(q)),
                    str(roots / root_receipt_filename(q)),
                    "--q",
                    str(q),
                    "--additive-receipt",
                    str(additive_receipt),
                    "--precision",
                    "192",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        catalog = root / "root-catalog.ndjson"
        completed = subprocess.run(
            [
                str(PINNED_PYTHON),
                str(ROOT / "tools/tg_dirichlet_root_catalog.py"),
                "build",
                str(roots),
                str(catalog),
                "--q-start",
                str(min(self.SOURCE_QS)),
                "--q-stop",
                str(max(self.SOURCE_QS)),
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
        catalog_sha = json.loads(completed.stdout)["catalog_sha256"]
        return (
            composition,
            consumer,
            schedule_path,
            roots,
            catalog,
            catalog_sha,
        )

    def test_manifest_ordered_process_graph_and_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                composition,
                consumer,
                schedule,
                roots,
                catalog,
                catalog_sha,
            ) = self._fixture(root)
            pipeline_receipt = root / "pipeline.receipt.json"
            result = run_scheduled_pipeline(
                composition_controls=composition,
                consumer_controls=consumer,
                schedule_manifest=schedule,
                control_base=root,
                composer_python=PINNED_PYTHON,
                composer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_residue_composition_kat_worker.py"
                ),
                allchars_runner=ALLCHARS,
                consumer_python=PINNED_PYTHON,
                consumer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                ),
                root_catalog=catalog,
                root_catalog_sha256=catalog_sha,
                root_catalog_directory=roots,
                output_directory=root / "pipeline",
                pipeline_receipt=pipeline_receipt,
                maximum_batch_count=1,
                precision=192,
                allow_synthetic_kat=True,
                maximum_capture_bytes=32 * 1024 * 1024,
                process_timeout_seconds=180,
            )
            self.assertTrue(result["TGDQORD1_exact_coverage"])
            self.assertFalse(result["increasing_q_assumed"])
            self.assertTrue(result["process_graph_backpressured"])
            self.assertTrue(result["isolated_process_groups"])
            self.assertEqual(
                result["maximum_capture_bytes"], 32 * 1024 * 1024
            )
            self.assertEqual(result["process_timeout_seconds"], 180.0)
            self.assertEqual(
                set(result["component_invocations"]),
                {
                    "allchars_runner",
                    "bounded_stream_tee",
                    "composer_python",
                    "composer_tool",
                    "consumer_python",
                    "consumer_tool",
                },
            )
            self.assertFalse(result["external_atom_discharged"])
            schedule_sha = parse_schedule_manifest(schedule).manifest_sha256
            for record in (
                result["summaries"]["composer"],
                result["summaries"]["transform"],
                result["summaries"]["consumer"],
                result["captures"]["TGDAFFI1_tee_receipt"],
                result["captures"]["TGDAFFO1_tee_receipt"],
            ):
                value = json.loads(Path(record["path"]).read_bytes())
                self.assertEqual(
                    value["schedule_manifest_sha256"], schedule_sha
                )
            consumer_value = json.loads(
                Path(result["summaries"]["consumer"]["path"]).read_bytes()
            )
            self.assertEqual(
                result["summaries"]["events"]["sha256"],
                consumer_value["events_sha256"],
            )
            self.assertEqual(
                result["summaries"]["events"]["size_bytes"],
                consumer_value["events_bytes"],
            )
            replay = replay_scheduled_pipeline(
                pipeline_receipt,
                composer_python=PINNED_PYTHON,
                composer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_residue_composition_kat_worker.py"
                ),
                allchars_checker=MPFR_CHECKER,
                consumer_python=PINNED_PYTHON,
                consumer_tool=(
                    ROOT
                    / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                ),
                control_base=root,
                precision=192,
                allow_synthetic_kat=True,
            )
            self.assertTrue(replay["producer_byte_identical"])
            self.assertTrue(replay["isolated_process_groups"])
            self.assertEqual(
                replay["maximum_capture_bytes"], 32 * 1024 * 1024
            )
            self.assertEqual(replay["process_timeout_seconds"], 900.0)
            self.assertIn(
                "allchars_checker", replay["replay_component_invocations"]
            )
            self.assertEqual(
                replay["transform_frames_independently_verified_with_MPFR"],
                4,
            )
            self.assertTrue(replay["consumer_fresh_Arb_replay_accepted"])
            self.assertFalse(replay["external_atom_discharged"])

            bounded_tamper = json.loads(canonical_json_bytes(result))
            bounded_tamper["maximum_capture_bytes"] = 1
            bounded_tamper.pop("receipt_sha256")
            bounded_tamper["receipt_sha256"] = sha256_bytes(
                canonical_json_bytes(bounded_tamper)
            )
            bounded_tamper_path = root / "bad-bound-pipeline.receipt.json"
            bounded_tamper_path.write_bytes(
                canonical_json_bytes(bounded_tamper)
            )
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "capture.*retained bound"
            ):
                replay_scheduled_pipeline(
                    bounded_tamper_path,
                    composer_python=PINNED_PYTHON,
                    composer_tool=(
                        ROOT
                        / "tests/tg_dirichlet_residue_composition_kat_worker.py"
                    ),
                    allchars_checker=MPFR_CHECKER,
                    consumer_python=PINNED_PYTHON,
                    consumer_tool=(
                        ROOT
                        / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                    ),
                    control_base=root,
                    precision=192,
                    allow_synthetic_kat=True,
                )

            capture_path = Path(result["captures"]["TGDAFFO1"]["path"])
            raw = bytearray(capture_path.read_bytes())
            raw[-1] ^= 1
            capture_path.write_bytes(raw)
            with self.assertRaisesRegex(
                DirichletScheduledPipelineError, "changed from its receipt"
            ):
                replay_scheduled_pipeline(
                    pipeline_receipt,
                    composer_python=PINNED_PYTHON,
                    composer_tool=(
                        ROOT
                        / "tests/tg_dirichlet_residue_composition_kat_worker.py"
                    ),
                    allchars_checker=MPFR_CHECKER,
                    consumer_python=PINNED_PYTHON,
                    consumer_tool=(
                        ROOT
                        / "tests/tg_dirichlet_stream_consumer_kat_worker.py"
                    ),
                    control_base=root,
                    precision=192,
                    allow_synthetic_kat=True,
                )


if __name__ == "__main__":
    unittest.main()
