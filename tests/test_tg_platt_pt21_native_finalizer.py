# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tg_verifier.platt_pt21_native_finalizer import (
    BLOCK_RECORD_DOMAIN,
    PT21NativeFinalizerError,
    SOURCE_HEIGHT_BLOCK,
    SOURCE_HEIGHT_COUNT,
    encode_block_record,
    replay_campaign,
    replay_shard,
)


ROOT = Path(__file__).resolve().parents[1]
WORKER = "aa" * 32
PLAN = "bb" * 32
PREFIX = "cc" * 32
STREAM_AUTH = "dd" * 32
STREAM_AUTH_FOOTER = struct.Struct("<8sII32s")


def record(
    block: int,
    lower: int,
    slots: int,
    *,
    stationary: int = 0,
    sparse: int = 0,
    source_count: int | None = None,
) -> bytes:
    return encode_block_record(
        block=block,
        lower_count=lower,
        upper_count=lower + slots,
        main_slots=slots,
        stationary_resolution_count=stationary,
        sparse_refinement_count=sparse,
        initial_ambiguous_count=sparse,
        source_height_count=source_count,
        source_height_slots_from_lower=(
            0 if source_count is None else source_count - lower
        ),
        required_packet_sha256="11" * 32,
        source_trace_sha256="22" * 32,
        block_artifact_sha256="33" * 32,
        stationary_trace_sha256="44" * 32 if stationary else None,
        sparse_refinement_sha256="55" * 32 if sparse else None,
        producer_commitment_sha256=WORKER,
    )


def resign_block(raw: bytearray) -> None:
    raw[288:320] = hashlib.sha256(BLOCK_RECORD_DOMAIN + raw[:288]).digest()


def authenticated_stream(raw: bytes) -> bytes:
    return raw + STREAM_AUTH_FOOTER.pack(
        b"PT21END1", 1, STREAM_AUTH_FOOTER.size, bytes.fromhex(STREAM_AUTH)
    )


class PT21NativeFinalizerTest(unittest.TestCase):
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
            raise unittest.SkipTest("g++ is required for the native finalizer test")
        cls._build = tempfile.TemporaryDirectory()
        cls.runner = Path(cls._build.name) / "tg-platt-pt21-native-finalizer"
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                f"-I{ROOT / 'gpu/include'}",
                str(ROOT / "reference/tg_platt_pt21_native_finalizer.cpp"),
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

    def run_native(
        self,
        *arguments: str,
        expect_success: bool = True,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            [str(self.runner), *arguments],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if expect_success:
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stderr, b"")
        else:
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, b"")
            self.assertIn(b"tg_platt_pt21_native_finalizer:", completed.stderr)
        return completed

    def test_native_shard_accepts_exact_authenticated_record_pipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "streamed.shard"
            raw = record(0, 1, 2) + record(1, 3, 1)
            result = self.run_native(
                "shard",
                "--input",
                "-",
                "--output",
                str(output),
                "--first-block",
                "0",
                "--block-count",
                "2",
                "--worker-sha256",
                WORKER,
                "--plan-sha256",
                PLAN,
                "--prefix-evidence-sha256",
                PREFIX,
                "--stream-auth-sha256",
                STREAM_AUTH,
                "--bounded-test",
                input_bytes=authenticated_stream(raw),
            )
            summary = json.loads(result.stdout)
            self.assertEqual(summary["block_count"], 2)
            replay = replay_shard(
                output,
                expected_plan_sha256=PLAN,
                expected_worker_sha256=WORKER,
                expected_prefix_sha256=PREFIX,
                allow_bounded_test=True,
            )
            self.assertEqual(replay.first_count, 1)
            self.assertEqual(replay.last_count, 4)

    def test_native_record_pipe_rejects_prefix_and_trailing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            complete = record(0, 1, 2)
            for name, raw in (
                ("prefix", authenticated_stream(complete[:-1])),
                ("trailing", authenticated_stream(complete) + b"\0"),
                (
                    "wrong-authentication",
                    complete
                    + STREAM_AUTH_FOOTER.pack(
                        b"PT21END1",
                        1,
                        STREAM_AUTH_FOOTER.size,
                        bytes.fromhex("ee" * 32),
                    ),
                ),
            ):
                with self.subTest(name=name):
                    output = directory / f"{name}.shard"
                    self.run_native(
                        "shard",
                        "--input",
                        "-",
                        "--output",
                        str(output),
                        "--first-block",
                        "0",
                        "--block-count",
                        "1",
                        "--worker-sha256",
                        WORKER,
                        "--plan-sha256",
                        PLAN,
                        "--prefix-evidence-sha256",
                        PREFIX,
                        "--stream-auth-sha256",
                        STREAM_AUTH,
                        "--bounded-test",
                        input_bytes=raw,
                        expect_success=False,
                    )
                    self.assertFalse(output.exists())

    def finalize_shard(
        self,
        directory: Path,
        *,
        name: str,
        first_block: int,
        records: list[bytes],
        bounded: bool = True,
    ) -> Path:
        source = directory / f"{name}.records"
        output = directory / f"{name}.shard"
        source.write_bytes(b"".join(records))
        arguments = [
            "shard",
            "--input",
            str(source),
            "--output",
            str(output),
            "--first-block",
            str(first_block),
            "--block-count",
            str(len(records)),
            "--worker-sha256",
            WORKER,
            "--plan-sha256",
            PLAN,
            "--prefix-evidence-sha256",
            PREFIX,
        ]
        if bounded:
            arguments.append("--bounded-test")
        result = self.run_native(*arguments)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["source_claim_ready"], False)
        self.assertEqual(summary["block_count"], len(records))
        return output

    def finalize_campaign(
        self,
        directory: Path,
        shards: list[Path],
        *,
        bounded: bool = True,
    ) -> Path:
        roster = directory / "shards.txt"
        roster.write_text(
            "".join(f"{path}\n" for path in shards), encoding="utf-8"
        )
        output = directory / "campaign.bin"
        arguments = [
            "campaign",
            "--shard-list",
            str(roster),
            "--output",
            str(output),
            "--worker-sha256",
            WORKER,
            "--plan-sha256",
            PLAN,
            "--prefix-evidence-sha256",
            PREFIX,
        ]
        if bounded:
            arguments.append("--bounded-test")
        result = self.run_native(*arguments)
        self.assertFalse(json.loads(result.stdout)["source_claim_ready"])
        return output

    def test_native_shard_campaign_and_independent_full_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = self.finalize_shard(
                directory,
                name="first",
                first_block=0,
                records=[
                    record(0, 1, 2, stationary=2, sparse=1),
                    record(1, 3, 1),
                ],
            )
            second = self.finalize_shard(
                directory,
                name="second",
                first_block=2,
                records=[record(2, 4, 3, stationary=1)],
            )
            third = self.finalize_shard(
                directory,
                name="third",
                first_block=3,
                records=[record(3, 7, 2)],
            )
            first_replay = replay_shard(
                first,
                expected_plan_sha256=PLAN,
                expected_worker_sha256=WORKER,
                expected_prefix_sha256=PREFIX,
                allow_bounded_test=True,
            )
            self.assertEqual(first_replay.total_main_slots, 3)
            self.assertEqual(first_replay.total_stationary_resolutions, 2)
            self.assertEqual(first_replay.total_sparse_refinements, 1)
            campaign = self.finalize_campaign(directory, [first, second, third])
            replay = replay_campaign(
                campaign,
                [first, second, third],
                expected_plan_sha256=PLAN,
                expected_worker_sha256=WORKER,
                expected_prefix_sha256=PREFIX,
                allow_bounded_test=True,
            )
            self.assertEqual(replay.block_count, 4)
            self.assertEqual(replay.first_count, 1)
            self.assertEqual(replay.last_count, 9)
            self.assertEqual(replay.total_main_slots, 8)
            self.assertEqual(replay.total_stationary_resolutions, 3)
            self.assertEqual(replay.total_sparse_refinements, 1)

            roster = directory / "replay-shards.txt"
            roster.write_text(
                "".join(f"{path}\n" for path in (first, second, third)),
                encoding="utf-8",
            )
            cli = subprocess.run(
                [
                    "python3",
                    str(ROOT / "tools/tg_platt_pt21_native_finalizer.py"),
                    "replay-campaign",
                    str(campaign),
                    "--shard-list",
                    str(roster),
                    "--expected-worker-sha256",
                    WORKER,
                    "--expected-plan-sha256",
                    PLAN,
                    "--expected-prefix-evidence-sha256",
                    PREFIX,
                    "--allow-bounded-test",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            cli_value = json.loads(cli.stdout)
            self.assertEqual(cli.stderr, b"")
            self.assertTrue(cli_value["replayed_every_retained_record"])
            self.assertTrue(cli_value["replayed_every_shard_archive"])
            self.assertFalse(cli_value["source_claim_ready"])

    def test_source_height_count_is_bound_to_the_unique_target_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shard = self.finalize_shard(
                directory,
                name="target",
                first_block=SOURCE_HEIGHT_BLOCK,
                records=[
                    record(
                        SOURCE_HEIGHT_BLOCK,
                        SOURCE_HEIGHT_COUNT - 2,
                        4,
                        source_count=SOURCE_HEIGHT_COUNT,
                    )
                ],
            )
            replay = replay_shard(shard, allow_bounded_test=True)
            self.assertEqual(replay.source_height_count, SOURCE_HEIGHT_COUNT)

            misplaced = bytearray(record(0, 1, 2))
            misplaced[80:88] = struct.pack("<Q", SOURCE_HEIGHT_COUNT)
            resign_block(misplaced)
            source = directory / "misplaced.records"
            source.write_bytes(misplaced)
            self.run_native(
                "shard",
                "--input",
                str(source),
                "--output",
                str(directory / "misplaced.shard"),
                "--first-block",
                "0",
                "--block-count",
                "1",
                "--worker-sha256",
                WORKER,
                "--plan-sha256",
                PLAN,
                "--prefix-evidence-sha256",
                PREFIX,
                "--bounded-test",
                expect_success=False,
            )

            unlinked = bytearray(
                record(
                    SOURCE_HEIGHT_BLOCK,
                    SOURCE_HEIGHT_COUNT - 2,
                    4,
                    source_count=SOURCE_HEIGHT_COUNT,
                )
            )
            unlinked[280:288] = struct.pack("<Q", 3)
            resign_block(unlinked)
            source = directory / "unlinked.records"
            source.write_bytes(unlinked)
            self.run_native(
                "shard",
                "--input",
                str(source),
                "--output",
                str(directory / "unlinked.shard"),
                "--first-block",
                str(SOURCE_HEIGHT_BLOCK),
                "--block-count",
                "1",
                "--worker-sha256",
                WORKER,
                "--plan-sha256",
                PLAN,
                "--prefix-evidence-sha256",
                PREFIX,
                "--bounded-test",
                expect_success=False,
            )

    def test_unresolved_failure_and_incomplete_sparse_refinement_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cases: list[tuple[str, bytearray]] = []

            unresolved = bytearray(record(0, 1, 2))
            unresolved[64:68] = struct.pack("<I", 1)
            resign_block(unresolved)
            cases.append(("unresolved", unresolved))

            sparse_mismatch = bytearray(record(0, 1, 2, sparse=1))
            sparse_mismatch[56:60] = struct.pack("<I", 0)
            resign_block(sparse_mismatch)
            cases.append(("sparse-mismatch", sparse_mismatch))

            missing_sparse_digest = bytearray(record(0, 1, 2, sparse=1))
            missing_sparse_digest[216:248] = bytes(32)
            resign_block(missing_sparse_digest)
            cases.append(("missing-sparse-digest", missing_sparse_digest))

            wrong_worker = bytearray(
                encode_block_record(
                    block=0,
                    lower_count=1,
                    upper_count=3,
                    main_slots=2,
                    required_packet_sha256="11" * 32,
                    source_trace_sha256="22" * 32,
                    block_artifact_sha256="33" * 32,
                    producer_commitment_sha256="77" * 32,
                )
            )
            cases.append(("wrong-worker", wrong_worker))

            for name, raw in cases:
                with self.subTest(name=name):
                    source = directory / f"{name}.records"
                    source.write_bytes(raw)
                    self.run_native(
                        "shard",
                        "--input",
                        str(source),
                        "--output",
                        str(directory / f"{name}.shard"),
                        "--first-block",
                        "0",
                        "--block-count",
                        "1",
                        "--worker-sha256",
                        WORKER,
                        "--plan-sha256",
                        PLAN,
                        "--prefix-evidence-sha256",
                        PREFIX,
                        "--bounded-test",
                        expect_success=False,
                    )
                    self.assertFalse((directory / f"{name}.shard").exists())

    def test_replay_rejects_record_footer_trailing_and_symlink_mutations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shard = self.finalize_shard(
                directory,
                name="base",
                first_block=0,
                records=[record(0, 1, 2)],
            )
            raw = shard.read_bytes()
            mutations = {
                "record": raw[:300] + bytes([raw[300] ^ 1]) + raw[301:],
                "footer": raw[:-32] + bytes([raw[-32] ^ 1]) + raw[-31:],
                "truncated": raw[:-1],
                "trailing": raw + b"\0",
            }
            for name, changed in mutations.items():
                with self.subTest(name=name):
                    path = directory / f"{name}.shard"
                    path.write_bytes(changed)
                    with self.assertRaises(PT21NativeFinalizerError):
                        replay_shard(path, allow_bounded_test=True)

            link = directory / "linked.shard"
            os.symlink(shard, link)
            with self.assertRaisesRegex(
                PT21NativeFinalizerError, "without following links"
            ):
                replay_shard(link, allow_bounded_test=True)

    def test_campaign_replay_requires_exact_order_and_fresh_shard_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = self.finalize_shard(
                directory,
                name="first",
                first_block=0,
                records=[record(0, 1, 2)],
            )
            second = self.finalize_shard(
                directory,
                name="second",
                first_block=1,
                records=[record(1, 3, 1)],
            )
            campaign = self.finalize_campaign(directory, [first, second])
            with self.assertRaises(PT21NativeFinalizerError):
                replay_campaign(
                    campaign, [second, first], allow_bounded_test=True
                )
            with self.assertRaisesRegex(PT21NativeFinalizerError, "repeats"):
                replay_campaign(
                    campaign, [first, first], allow_bounded_test=True
                )

            changed = bytearray(second.read_bytes())
            changed[300] ^= 1
            second.write_bytes(changed)
            with self.assertRaises(PT21NativeFinalizerError):
                replay_campaign(
                    campaign, [first, second], allow_bounded_test=True
                )

    def test_output_is_create_only_and_incomplete_production_campaign_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "records.bin"
            source.write_bytes(record(1, 3, 1))
            output = directory / "existing.shard"
            output.write_bytes(b"do-not-replace")
            arguments = [
                "shard",
                "--input",
                str(source),
                "--output",
                str(output),
                "--first-block",
                "1",
                "--block-count",
                "1",
                "--worker-sha256",
                WORKER,
                "--plan-sha256",
                PLAN,
                "--prefix-evidence-sha256",
                PREFIX,
                "--bounded-test",
            ]
            self.run_native(*arguments, expect_success=False)
            self.assertEqual(output.read_bytes(), b"do-not-replace")

            production_shard = self.finalize_shard(
                directory,
                name="production-partial",
                first_block=1,
                records=[record(1, 3, 1)],
                bounded=False,
            )
            roster = directory / "production.txt"
            roster.write_text(f"{production_shard}\n", encoding="utf-8")
            self.run_native(
                "campaign",
                "--shard-list",
                str(roster),
                "--output",
                str(directory / "production-campaign.bin"),
                "--worker-sha256",
                WORKER,
                "--plan-sha256",
                PLAN,
                "--prefix-evidence-sha256",
                PREFIX,
                expect_success=False,
            )


if __name__ == "__main__":
    unittest.main()
