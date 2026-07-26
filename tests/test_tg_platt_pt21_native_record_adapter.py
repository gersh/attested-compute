# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.platt_pt21_native_finalizer import (
    BLOCK_RECORD,
    parse_block_record,
    replay_shard,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    MANIFEST_SCHEMA,
    PT21NativeRecordAdapterError,
    adapt_block,
    adapt_manifest,
    adapt_manifest_to_native_shard,
    block_report,
    write_exclusive,
)
from tg_verifier.platt_pt21_turing_inputs import (
    ALGORITHM as TURING_ALGORITHM,
    FLINT_COMMIT,
    INTERPOLATION_PATCH_SHA256,
    SCHEMA as TURING_SCHEMA,
    SOURCE_TURING_C_SHA256,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    UPSTREAM_COMMIT,
)
from tg_verifier.platt_stationary_trace import (
    INTERPOLATION_PATCH_SHA256 as STATIONARY_PATCH_SHA256,
    RESOLUTION_DOMAIN,
    SCHEMA as STATIONARY_SCHEMA,
)


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def fnv1a(raw: bytes) -> int:
    value = 1_469_598_103_934_665_603
    for byte in raw:
        value ^= byte
        value = (value * 1_099_511_628_211) & ((1 << 64) - 1)
    return value


def rational(value: Fraction | int) -> dict[str, int]:
    fraction = Fraction(value)
    return {
        "numerator": fraction.numerator,
        "denominator": fraction.denominator,
    }


def point(value: Fraction | int) -> dict[str, object]:
    endpoint = rational(value)
    return {"lo": endpoint, "hi": dict(endpoint)}


def required_packet(directory: Path, block: int) -> Path:
    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        high = 1.0 if offset == 0 else -1.0
        samples.extend(SAMPLE.pack(high, 0.0, 0.25))
        if high > 0:
            signs[index // 8] |= 1 << (index % 8)
    source = f"native-record-adapter-source-{block}".encode()
    header = HEADER.pack(
        b"PT21SGN1",
        1,
        HEADER.size,
        0x01020304,
        1,
        1,
        768_000,
        REQUIRED_BEGIN,
        REQUIRED_END,
        REQUIRED_COUNT,
        0,
        SOURCE_LOWER_CENTER + block * SOURCE_STEP,
        len(samples),
        len(signs),
        fnv1a(samples),
        fnv1a(signs),
        len(source),
        hashlib.sha256(source).hexdigest().encode(),
        UPSTREAM_COMMIT,
    )
    path = directory / f"required-{block}.bin"
    path.write_bytes(header + samples + signs)
    return path


def stationary_trace(directory: Path, block: int) -> Path:
    resolutions: list[object] = []
    value = {
        "accepted": True,
        "ambiguous_input_disks": 0,
        "candidate_count": 0,
        "error": "",
        "failure_flags": 0,
        "input_sha256": "61" * 32,
        "interpolation_evaluations": 0,
        "interpolation_patch_sha256": STATIONARY_PATCH_SHA256,
        "maximum_depth": 64,
        "precision_bits": 128,
        "refinements_applied": 0,
        "replay_accepted": True,
        "required_sample_count": REQUIRED_COUNT,
        "resolution_sha256": hashlib.sha256(
            RESOLUTION_DOMAIN
            + json.dumps(
                resolutions, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "schema": STATIONARY_SCHEMA,
        "semantic_status": {
            "analytic_turing_realization_proved": False,
            "flint_to_mathlib_realization_proved": False,
            "hardy_z_endpoint_realization_proved": False,
        },
        "stationary_resolutions": resolutions,
        "upstream_commit": UPSTREAM_COMMIT.decode(),
    }
    path = directory / f"stationary-{block}.json"
    path.write_bytes(canonical(value))
    return path


def turing_inputs(
    directory: Path, packet: Path, block: int, lower_count: int
) -> Path:
    height_lower = 10_000_000_000 + block * 1_008
    height_upper = height_lower + 1_008
    common = Fraction(21 * lower_count)

    def side(function: str, a: int, b: int) -> dict[str, object]:
        log_term = Fraction(-(a + b), 4) * 21
        values = {
            "s_bound": point(21),
            "log_pi": point(1),
            "im_gamma_integral": point(common - log_term),
            "pi": point(1),
        }
        return {
            "function": function,
            "interval": {"a": a, "b": b},
            "values": values,
        }

    packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
    value = {
        "algorithm": TURING_ALGORITHM,
        "block": block,
        "flint_commit": FLINT_COMMIT,
        "inputs": {
            "lower": side(
                "turing_min", height_lower - 21, height_lower
            ),
            "upper": side(
                "turing_max", height_upper, height_upper + 21
            ),
        },
        "precision_bits": 128,
        "replay_precision_bits": 256,
        "required_sign_packet_sha256": packet_sha256,
        "schema": TURING_SCHEMA,
        "semantic_status": {
            "analytic_turing_realization_proved": False,
            "arb_interval_arithmetic_executed": True,
            "hardy_z_endpoint_realization_proved": False,
        },
        "source_identity": {
            "height_lower": height_lower,
            "height_upper": height_upper,
            "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
            "source_turing_c_sha256": SOURCE_TURING_C_SHA256,
            "upstream_commit": UPSTREAM_COMMIT.decode(),
        },
    }
    path = directory / f"turing-{block}.json"
    path.write_bytes(canonical(value))
    return path


def worker(directory: Path) -> Path:
    path = directory / "measured-worker"
    path.write_bytes(b"fixture-worker-v1\n")
    path.chmod(0o500)
    return path


class PT21NativeRecordAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("TG_PLATT_PT21_NATIVE_FINALIZER")
        if supplied:
            cls._build = None
            cls.runner = Path(supplied)
            if not cls.runner.is_file() or not os.access(cls.runner, os.X_OK):
                raise unittest.SkipTest(
                    "TG_PLATT_PT21_NATIVE_FINALIZER is not executable"
                )
            return
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest(
                "g++ is required for the streamed native adapter test"
            )
        cls._build = tempfile.TemporaryDirectory()
        cls.runner = Path(cls._build.name) / "tg-platt-pt21-native-finalizer"
        root = Path(__file__).resolve().parents[1]
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                f"-I{root / 'gpu/include'}",
                str(root / "reference/tg_platt_pt21_native_finalizer.cpp"),
                "-o",
                str(cls.runner),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._build is not None:
            cls._build.cleanup()

    def fixtures(
        self, directory: Path, block: int, lower_count: int
    ) -> tuple[Path, Path, Path]:
        packet = required_packet(directory, block)
        stationary = stationary_trace(directory, block)
        turing = turing_inputs(directory, packet, block, lower_count)
        return packet, stationary, turing

    def test_known_answer_rebuilds_finite_artifact_and_native_wire(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            adapted = adapt_block(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=worker(directory),
            )
            parsed = parse_block_record(adapted.record, expected_block=0)
            self.assertEqual(len(adapted.record), BLOCK_RECORD.size)
            self.assertEqual(parsed.lower_count, 1)
            self.assertEqual(parsed.upper_count, 3)
            self.assertEqual(parsed.main_slots, 2)
            self.assertEqual(parsed.stationary_resolution_count, 0)
            self.assertEqual(parsed.sparse_refinement_count, 0)
            self.assertEqual(
                parsed.required_packet_sha256.hex(),
                hashlib.sha256(packet.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                hashlib.sha256(adapted.record).hexdigest(),
                "6ccdb3cbfc12e9a60a6a554a4105d00d06037bd37c32dfd2d459510c89e851f3",
            )
            report = block_report(adapted)
            self.assertTrue(report["finite_record_wire_ready"])
            self.assertFalse(report["hardy_z_endpoint_realization_proved"])
            self.assertFalse(report["analytic_turing_realization_proved"])
            self.assertFalse(report["lean_source_claim_ready"])
            self.assertFalse(report["source_claim_ready"])

    def test_cli_emits_one_create_only_record_and_no_semantic_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            output = directory / "block.record"
            command = [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1]
                    / "tools/tg_platt_pt21_native_record_adapter.py"
                ),
                "block",
                "--required-sign-packet",
                str(packet),
                "--stationary-trace",
                str(stationary),
                "--turing-inputs",
                str(turing),
                "--worker",
                str(worker(directory)),
                "--output",
                str(output),
            ]
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.stderr, b"")
            report = json.loads(completed.stdout)
            self.assertEqual(output.stat().st_size, BLOCK_RECORD.size)
            self.assertTrue(report["finite_record_wire_ready"])
            self.assertFalse(report["source_claim_ready"])
            failed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stdout, b"")
            self.assertIn(
                b"tg_platt_pt21_native_record_adapter:", failed.stderr
            )

    def test_optional_adapter_record_enters_native_shard_and_replay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            adapted = adapt_block(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=worker(directory),
            )
            records = directory / "records.bin"
            records.write_bytes(adapted.record)
            shard = directory / "shard.bin"
            plan = "71" * 32
            prefix = "72" * 32
            completed = subprocess.run(
                [
                    str(self.runner),
                    "shard",
                    "--input",
                    str(records),
                    "--output",
                    str(shard),
                    "--first-block",
                    "0",
                    "--block-count",
                    "1",
                    "--worker-sha256",
                    adapted.worker.sha256,
                    "--plan-sha256",
                    plan,
                    "--prefix-evidence-sha256",
                    prefix,
                    "--bounded-test",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.stderr, b"")
            self.assertFalse(json.loads(completed.stdout)["source_claim_ready"])
            replay = replay_shard(
                shard,
                expected_worker_sha256=adapted.worker.sha256,
                expected_plan_sha256=plan,
                expected_prefix_sha256=prefix,
                allow_bounded_test=True,
            )
            self.assertEqual(replay.block_count, 1)
            self.assertEqual(replay.first_count, 1)
            self.assertEqual(replay.last_count, 3)

    def test_streaming_manifest_is_gap_count_and_create_only_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows: list[dict[str, object]] = []
            for block, lower in ((0, 1), (1, 3)):
                packet, stationary, turing = self.fixtures(
                    directory, block, lower
                )
                rows.append(
                    {
                        "required_sign_packet": packet.name,
                        "schema": MANIFEST_SCHEMA,
                        "stationary_trace": stationary.name,
                        "turing_inputs": turing.name,
                    }
                )
            manifest = directory / "manifest.jsonl"
            manifest.write_bytes(b"".join(canonical(row) for row in rows))
            output = directory / "records.bin"
            report = adapt_manifest(
                manifest,
                output=output,
                worker=worker(directory),
                first_block=0,
                block_count=2,
            )
            self.assertEqual(output.stat().st_size, 2 * BLOCK_RECORD.size)
            self.assertEqual(report["block_count"], 2)
            self.assertEqual(report["total_main_slots"], 4)
            self.assertFalse(report["source_claim_ready"])
            raw = output.read_bytes()
            first = parse_block_record(raw[: BLOCK_RECORD.size])
            second = parse_block_record(raw[BLOCK_RECORD.size :])
            self.assertEqual(first.upper_count, second.lower_count)
            with self.assertRaises(FileExistsError):
                adapt_manifest(
                    manifest,
                    output=output,
                    worker=directory / "measured-worker",
                    first_block=0,
                    block_count=2,
                )
            self.assertEqual(output.read_bytes(), raw)

    def test_authenticated_manifest_streams_directly_to_native_archive(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows: list[dict[str, object]] = []
            for block, lower in ((0, 1), (1, 3)):
                packet, stationary, turing = self.fixtures(
                    directory, block, lower
                )
                rows.append(
                    {
                        "required_sign_packet": packet.name,
                        "schema": MANIFEST_SCHEMA,
                        "stationary_trace": stationary.name,
                        "turing_inputs": turing.name,
                    }
                )
            manifest = directory / "manifest.jsonl"
            manifest_raw = b"".join(canonical(row) for row in rows)
            manifest.write_bytes(manifest_raw)
            runner = worker(directory)
            output = directory / "shard.bin"
            finalizer_sha256 = hashlib.sha256(
                self.runner.read_bytes()
            ).hexdigest()
            report = adapt_manifest_to_native_shard(
                manifest,
                worker=runner,
                finalizer=self.runner,
                expected_finalizer_sha256=finalizer_sha256,
                expected_manifest_sha256=hashlib.sha256(
                    manifest_raw
                ).hexdigest(),
                output=output,
                first_block=0,
                block_count=2,
                plan_sha256="71" * 32,
                prefix_evidence_sha256="72" * 32,
                bounded_test=True,
            )
            self.assertTrue(
                report["streamed_without_intermediate_record_file"]
            )
            self.assertTrue(
                report["terminal_stream_authentication_required"]
            )
            self.assertEqual(report["first_count"], 1)
            self.assertEqual(report["last_count"], 5)
            self.assertEqual(report["record_stream_bytes"], 2 * BLOCK_RECORD.size)
            self.assertFalse(report["source_claim_ready"])
            self.assertFalse(any(directory.glob("*.records")))
            replay = replay_shard(
                output,
                expected_worker_sha256=hashlib.sha256(
                    runner.read_bytes()
                ).hexdigest(),
                expected_plan_sha256="71" * 32,
                expected_prefix_sha256="72" * 32,
                allow_bounded_test=True,
            )
            self.assertEqual(replay.block_count, 2)
            self.assertEqual(replay.first_count, 1)
            self.assertEqual(replay.last_count, 5)

    def test_streamed_shard_requires_manifest_and_finalizer_pins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            row = {
                "required_sign_packet": packet.name,
                "schema": MANIFEST_SCHEMA,
                "stationary_trace": stationary.name,
                "turing_inputs": turing.name,
            }
            manifest = directory / "manifest.jsonl"
            manifest.write_bytes(canonical(row))
            runner = worker(directory)
            finalizer_sha256 = hashlib.sha256(
                self.runner.read_bytes()
            ).hexdigest()
            common = {
                "worker": runner,
                "finalizer": self.runner,
                "expected_finalizer_sha256": finalizer_sha256,
                "first_block": 0,
                "block_count": 1,
                "plan_sha256": "71" * 32,
                "prefix_evidence_sha256": "72" * 32,
                "bounded_test": True,
            }
            wrong_manifest_output = directory / "wrong-manifest.shard"
            with self.assertRaisesRegex(
                PT21NativeRecordAdapterError, "manifest SHA-256 differs"
            ):
                adapt_manifest_to_native_shard(
                    manifest,
                    expected_manifest_sha256="99" * 32,
                    output=wrong_manifest_output,
                    **common,
                )
            self.assertFalse(wrong_manifest_output.exists())

            wrong_finalizer_output = directory / "wrong-finalizer.shard"
            with self.assertRaisesRegex(
                PT21NativeRecordAdapterError, "pinned executable"
            ):
                adapt_manifest_to_native_shard(
                    manifest,
                    expected_manifest_sha256=hashlib.sha256(
                        manifest.read_bytes()
                    ).hexdigest(),
                    expected_finalizer_sha256="98" * 32,
                    output=wrong_finalizer_output,
                    **{
                        key: value
                        for key, value in common.items()
                        if key != "expected_finalizer_sha256"
                    },
                )
            self.assertFalse(wrong_finalizer_output.exists())

    def test_cli_streams_manifest_into_create_only_native_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            manifest = directory / "manifest.jsonl"
            manifest.write_bytes(
                canonical(
                    {
                        "required_sign_packet": packet.name,
                        "schema": MANIFEST_SCHEMA,
                        "stationary_trace": stationary.name,
                        "turing_inputs": turing.name,
                    }
                )
            )
            runner = worker(directory)
            output = directory / "native.shard"
            command = [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1]
                    / "tools/tg_platt_pt21_native_record_adapter.py"
                ),
                "shard-archive",
                "--manifest",
                str(manifest),
                "--expected-manifest-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--worker",
                str(runner),
                "--finalizer",
                str(self.runner),
                "--expected-finalizer-sha256",
                hashlib.sha256(self.runner.read_bytes()).hexdigest(),
                "--output",
                str(output),
                "--first-block",
                "0",
                "--block-count",
                "1",
                "--plan-sha256",
                "71" * 32,
                "--prefix-evidence-sha256",
                "72" * 32,
                "--bounded-test",
            ]
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertEqual(completed.stderr, b"")
            report = json.loads(completed.stdout)
            self.assertTrue(
                report["streamed_without_intermediate_record_file"]
            )
            self.assertFalse(report["source_claim_ready"])
            self.assertTrue(output.is_file())
            failed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stdout, b"")
            self.assertIn(b"output already exists", failed.stderr)

    def test_tampered_finite_inputs_and_semantic_overclaim_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            runner = worker(directory)

            original = stationary.read_bytes()
            value = json.loads(original)
            value["semantic_status"]["hardy_z_endpoint_realization_proved"] = True
            stationary.write_bytes(canonical(value))
            with self.assertRaisesRegex(
                PT21NativeRecordAdapterError, "stationary trace failed"
            ):
                adapt_block(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=runner,
                )
            stationary.write_bytes(original)

            original_turing = turing.read_bytes()
            value = json.loads(original_turing)
            value["required_sign_packet_sha256"] = "00" * 32
            turing.write_bytes(canonical(value))
            with self.assertRaisesRegex(
                PT21NativeRecordAdapterError, "Turing input artifact failed"
            ):
                adapt_block(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=runner,
                )
            turing.write_bytes(original_turing)

            raw = bytearray(packet.read_bytes())
            raw[-1] ^= 1
            packet.write_bytes(raw)
            with self.assertRaisesRegex(
                PT21NativeRecordAdapterError, "required-sign packet failed"
            ):
                adapt_block(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=runner,
                )

    def test_manifest_rejects_prefix_gap_noncanonical_and_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 1, 3)
            runner = worker(directory)
            row = {
                "required_sign_packet": packet.name,
                "schema": MANIFEST_SCHEMA,
                "stationary_trace": stationary.name,
                "turing_inputs": turing.name,
            }
            cases = {
                "gap": canonical(row),
                "noncanonical": json.dumps(row, indent=2).encode() + b"\n",
                "escape": canonical(
                    {
                        **row,
                        "required_sign_packet": "../outside.bin",
                    }
                ),
                "empty": b"",
            }
            for name, raw in cases.items():
                with self.subTest(name=name):
                    manifest = directory / f"{name}.jsonl"
                    manifest.write_bytes(raw)
                    output = directory / f"{name}.records"
                    with self.assertRaises(PT21NativeRecordAdapterError):
                        adapt_manifest(
                            manifest,
                            output=output,
                            worker=runner,
                            first_block=0,
                            block_count=1,
                        )
                    self.assertFalse(output.exists())

    def test_worker_and_retained_outputs_reject_symlink_or_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet, stationary, turing = self.fixtures(directory, 0, 1)
            runner = worker(directory)
            link = directory / "worker-link"
            link.symlink_to(runner)
            with self.assertRaises(PT21NativeRecordAdapterError):
                adapt_block(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=link,
                )
            output = directory / "record.bin"
            output.write_bytes(b"do-not-replace")
            with self.assertRaises(FileExistsError):
                write_exclusive(output, bytes(BLOCK_RECORD.size))
            self.assertEqual(output.read_bytes(), b"do-not-replace")


if __name__ == "__main__":
    unittest.main()
