# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer and tamper tests for the CPU-only R2Star full-row replay."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import replace
import hashlib
from math import isqrt
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from tg_verifier.campaign_io import (
    AZURE_MEASURED_WORKER_BACKEND_ENV,
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    AZURE_MEASURED_WORKER_SCOPE_ENV,
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.finite_campaigns import fixed_log_bounds
from tg_verifier.r2star import (
    R2StarChunk,
    _factor_block,
    _primes_upto,
    create_r2star_chunk,
)
from tg_verifier.r2star_campaign import (
    ARITHMETIC_REPLAY_PLAN_HEADER,
    DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
    R2StarCampaignError,
    R2StarCampaignResult,
    _arithmetic_replay_plan,
    arithmetic_replay_benchmark_plan,
    verify_campaign_arithmetic,
)
from tests.test_tg_r2star_campaign import exact_small_receipt


def _directed_rows_digest(chunk: R2StarChunk) -> str:
    rows = _factor_block(
        chunk.lower,
        chunk.upper,
        _primes_upto(isqrt(chunk.upper - 1)),
    )
    digest = hashlib.sha256()
    scale = 1 << chunk.scale_bits
    for number, factors in zip(range(chunk.lower, chunk.upper), rows):
        log_lower = 0
        log_upper = 0
        if number >= 2:
            log_lower, log_upper = fixed_log_bounds(
                number, chunk.scale_bits, chunk.series_terms
            )
        coefficient_lower = 0
        coefficient_upper = 0
        if len(factors) == 1:
            factor_lower, factor_upper = fixed_log_bounds(
                factors[0], chunk.scale_bits, chunk.series_terms
            )
            coefficient_lower = -(
                (factor_upper * factor_upper + scale - 1) // scale
            )
            coefficient_upper = -(factor_lower * factor_lower // scale)
        elif len(factors) == 2:
            left_lower, left_upper = fixed_log_bounds(
                factors[0], chunk.scale_bits, chunk.series_terms
            )
            right_lower, right_upper = fixed_log_bounds(
                factors[1], chunk.scale_bits, chunk.series_terms
            )
            coefficient_lower = 2 * left_lower * right_lower // scale
            coefficient_upper = (
                2 * left_upper * right_upper + scale - 1
            ) // scale
        digest.update(
            struct.pack(
                "<QQqqII",
                log_lower,
                log_upper,
                coefficient_lower + 2 * chunk.gamma_lower,
                coefficient_upper + 2 * chunk.gamma_upper,
                0,
                0,
            )
        )
    return digest.hexdigest()


def _plan(chunks: tuple[R2StarChunk, ...], *, limit: int) -> bytes:
    rows = [
        ARITHMETIC_REPLAY_PLAN_HEADER,
        f"expected_limit\t{limit}",
    ]
    for chunk in chunks:
        rows.append(
            "\t".join(
                (
                    "chunk",
                    str(chunk.lower),
                    str(chunk.upper),
                    str(chunk.incoming_lower),
                    str(chunk.incoming_upper),
                    str(chunk.outgoing_lower),
                    str(chunk.outgoing_upper),
                    str(chunk.minimum_squared_slack),
                    str(chunk.minimum_slack_index),
                    chunk.factor_support_digest,
                    _directed_rows_digest(chunk),
                    "0",
                )
            )
        )
    return ("\n".join(rows) + "\n").encode("ascii")


class R2StarArithmeticReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
        except MeasuredWorkerScopeError:
            raise unittest.SkipTest(
                "extended native R2Star arithmetic replay is cloud-only"
            ) from None
        configured = os.environ.get("TG_R2STAR_ARITHMETIC_REPLAYER")
        if not configured:
            raise unittest.SkipTest(
                "TG_R2STAR_ARITHMETIC_REPLAYER does not name the native replay"
            )
        cls.replayer = Path(configured).resolve(strict=True)
        first = create_r2star_chunk(
            lower=1,
            upper=501,
            scale_bits=32,
            series_terms=20,
            harmonic_terms=100_000,
            incoming_lower=0,
            incoming_upper=0,
        )
        second = create_r2star_chunk(
            lower=501,
            upper=1001,
            scale_bits=32,
            series_terms=20,
            harmonic_terms=100_000,
            incoming_lower=first.outgoing_lower,
            incoming_upper=first.outgoing_upper,
            previous_hash=first.record_hash,
        )
        cls.chunks = (first, second)

    def _run(
        self,
        raw: bytes,
        *,
        threads: int = 2,
        segment_rows: int | None = None,
    ) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary) / "plan.tsv"
            plan.write_bytes(raw)
            command = [
                str(self.replayer),
                "--plan",
                str(plan),
                "--threads",
                str(threads),
            ]
            if segment_rows is not None:
                command.extend(("--segment-rows", str(segment_rows)))
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_two_chunk_full_row_known_answer(self) -> None:
        completed = self._run(_plan(self.chunks, limit=1000))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            '{"checked_chunks":2,"checked_rows":1000,'
            '"classification":"independent_cpu_full_row_arithmetic_replay_v1",'
            '"expected_limit":1000,"status":"PASS"}\n',
        )

    def test_parallel_segments_are_byte_identical_to_serial_replay(self) -> None:
        raw = _plan(self.chunks, limit=1000)
        serial = self._run(raw, threads=1)
        segmented = self._run(raw, threads=8, segment_rows=37)
        self.assertEqual(serial.returncode, 0, serial.stderr)
        self.assertEqual(segmented.returncode, 0, segmented.stderr)
        self.assertEqual(segmented.stdout, serial.stdout)
        self.assertEqual(segmented.stderr, serial.stderr)

    def test_parallel_segments_reject_mutation_order_and_omission(self) -> None:
        raw = _plan(self.chunks, limit=1000)
        changed_factor = replace(
            self.chunks[0], factor_support_digest="0" * 64
        )
        rejected = self._run(
            _plan((changed_factor,), limit=500),
            threads=8,
            segment_rows=31,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("factor-support digest mismatch", rejected.stderr)

        mutated = raw.replace(
            _directed_rows_digest(self.chunks[0]).encode("ascii"),
            ("0" * 64).encode("ascii"),
            1,
        )
        rejected = self._run(
            mutated, threads=8, segment_rows=31
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("directed-row digest mismatch", rejected.stderr)

        changed_state = replace(
            self.chunks[0],
            outgoing_upper=self.chunks[0].outgoing_upper + 1,
        )
        rejected = self._run(
            _plan((changed_state,), limit=500),
            threads=8,
            segment_rows=31,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("outgoing directed state mismatch", rejected.stderr)

        changed_minimum = replace(
            self.chunks[0],
            minimum_squared_slack=(
                self.chunks[0].minimum_squared_slack + 1
            ),
        )
        rejected = self._run(
            _plan((changed_minimum,), limit=500),
            threads=8,
            segment_rows=31,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("minimum squared-slack witness mismatch", rejected.stderr)

        changed_fallback = _plan(
            (self.chunks[0],), limit=500
        ).replace(b"\t0\n", b"\t1\n", 1)
        rejected = self._run(
            changed_fallback, threads=8, segment_rows=31
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("exact-fallback row count mismatch", rejected.stderr)

        rows = raw.splitlines(keepends=True)
        reordered = b"".join((*rows[:2], rows[3], rows[2]))
        rejected = self._run(
            reordered, threads=8, segment_rows=31
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("declared source lower", rejected.stderr)

        omitted = b"".join((*rows[:2], rows[2]))
        rejected = self._run(
            omitted, threads=8, segment_rows=31
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("does not end immediately", rejected.stderr)

    def test_bounded_benchmark_plan_is_explicitly_nonproduction(self) -> None:
        report = exact_small_receipt()
        chunk = create_r2star_chunk(
            lower=1001,
            upper=1501,
            scale_bits=32,
            series_terms=20,
            harmonic_terms=100_000,
            incoming_lower=0,
            incoming_upper=0,
        )
        report["chunk"] = asdict(chunk)
        report["directed_rows_sha256_le_v1"] = _directed_rows_digest(chunk)
        completed = self._run(arithmetic_replay_benchmark_plan([report]))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            '{"checked_chunks":1,"checked_rows":500,'
            '"classification":"bounded_cpu_r2star_arithmetic_replay_benchmark_v1",'
            '"source_lower":1001,"source_upper_exclusive":1501,'
            '"status":"BENCHMARK_ONLY"}\n',
        )

        changed = arithmetic_replay_benchmark_plan([report]).replace(
            b"source_range\t1001\t1501",
            b"source_range\t1002\t1501",
            1,
        )
        rejected = self._run(changed)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("declared source lower", rejected.stderr)

    def test_campaign_plan_encoder_feeds_the_native_replay(self) -> None:
        report = exact_small_receipt()
        chunk = R2StarChunk(**report["chunk"])
        report["directed_rows_sha256_le_v1"] = _directed_rows_digest(chunk)
        completed = self._run(
            _arithmetic_replay_plan([report], expected_limit=500),
            threads=1,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"checked_rows":500', completed.stdout)

    def test_campaign_api_marks_rows_replayed_only_after_native_pass(
        self,
    ) -> None:
        report = exact_small_receipt()
        chunk = R2StarChunk(**report["chunk"])
        report["directed_rows_sha256_le_v1"] = _directed_rows_digest(chunk)
        structural = R2StarCampaignResult(
            endpoint=500,
            completed_upper=500,
            receipts=1,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash=chunk.record_hash,
            minimum_squared_slack=chunk.minimum_squared_slack,
            minimum_slack_index=chunk.minimum_slack_index,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch(
            "tg_verifier.r2star_campaign._verify_campaign_unlocked",
            return_value=structural,
        ), mock.patch(
            "tg_verifier.r2star_campaign._load_receipts",
            return_value=[report],
        ), mock.patch(
            "tg_verifier.r2star_campaign._load_and_validate_config",
            return_value={"endpoint": 500, "segment_count": 500},
        ):
            expected_replayer_sha256 = hashlib.sha256(
                self.replayer.read_bytes()
            ).hexdigest()
            checked = verify_campaign_arithmetic(
                Path(temporary),
                arithmetic_replayer=self.replayer,
                expected_arithmetic_replayer_sha256=(
                    expected_replayer_sha256
                ),
                replay_threads=1,
            )
            with self.assertRaisesRegex(
                R2StarCampaignError, "differs from the reviewed digest"
            ):
                verify_campaign_arithmetic(
                    Path(temporary),
                    arithmetic_replayer=self.replayer,
                    expected_arithmetic_replayer_sha256="0" * 64,
                    replay_threads=1,
                )
        self.assertTrue(checked.independent_rows_replayed)
        self.assertEqual(
            checked.arithmetic_replayer_sha256,
            expected_replayer_sha256,
        )

    def test_campaign_replay_forwards_only_validated_worker_binding(
        self,
    ) -> None:
        report = exact_small_receipt()
        chunk = R2StarChunk(**report["chunk"])
        report["directed_rows_sha256_le_v1"] = _directed_rows_digest(chunk)
        structural = R2StarCampaignResult(
            endpoint=500,
            completed_upper=500,
            receipts=1,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash=chunk.record_hash,
            minimum_squared_slack=chunk.minimum_squared_slack,
            minimum_slack_index=chunk.minimum_slack_index,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
        )
        expected_stdout = (
            b'{"checked_chunks":1,"checked_rows":500,'
            b'"classification":"independent_cpu_full_row_arithmetic_replay_v1",'
            b'"expected_limit":500,"status":"PASS"}\n'
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch(
            "tg_verifier.r2star_campaign._verify_campaign_unlocked",
            return_value=structural,
        ), mock.patch(
            "tg_verifier.r2star_campaign._load_receipts",
            return_value=[report],
        ), mock.patch(
            "tg_verifier.r2star_campaign._load_and_validate_config",
            return_value={"endpoint": 500, "segment_count": 500},
        ), mock.patch(
            "tg_verifier.r2star_campaign.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, expected_stdout, b""
            ),
        ) as replay:
            missing = {
                AZURE_MEASURED_WORKER_SCOPE_ENV: (
                    "sparkinterval.azure-measured-worker.v1"
                ),
                AZURE_MEASURED_WORKER_BACKEND_ENV: "azure_sevsnp_cpu",
                AZURE_MEASURED_WORKER_CHALLENGE_ENV: "1" * 64,
            }
            with mock.patch.dict(os.environ, missing, clear=True):
                with self.assertRaisesRegex(
                    R2StarCampaignError, "cloud-only"
                ):
                    verify_campaign_arithmetic(
                        Path(temporary),
                        arithmetic_replayer=self.replayer,
                        replay_threads=1,
                    )
            replay.assert_not_called()

            malformed = {
                **missing,
                AZURE_MEASURED_WORKER_JOB_BINDING_ENV: "g" * 64,
            }
            with mock.patch.dict(os.environ, malformed, clear=True):
                with self.assertRaisesRegex(
                    R2StarCampaignError, "cloud-only"
                ):
                    verify_campaign_arithmetic(
                        Path(temporary),
                        arithmetic_replayer=self.replayer,
                        replay_threads=1,
                    )
            replay.assert_not_called()

            validated = {
                **missing,
                AZURE_MEASURED_WORKER_JOB_BINDING_ENV: "2" * 64,
            }
            with mock.patch.dict(os.environ, validated, clear=True):
                checked = verify_campaign_arithmetic(
                    Path(temporary),
                    arithmetic_replayer=self.replayer,
                    replay_threads=1,
                )
            self.assertTrue(checked.independent_rows_replayed)
            replay.assert_called_once()
            default_command = replay.call_args.args[0]
            self.assertEqual(
                default_command[-2:],
                [
                    "--segment-rows",
                    str(DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS),
                ],
            )
            child_environment = replay.call_args.kwargs["env"]
            self.assertEqual(
                set(child_environment),
                {
                    "LANG",
                    "LC_ALL",
                    "TZ",
                    *AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS,
                },
            )
            self.assertEqual(child_environment["LANG"], "C")
            self.assertEqual(child_environment["LC_ALL"], "C")
            self.assertEqual(child_environment["TZ"], "UTC")
            for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
                self.assertEqual(child_environment[key], validated[key])

            replay.reset_mock()
            with mock.patch.dict(os.environ, validated, clear=True):
                checked = verify_campaign_arithmetic(
                    Path(temporary),
                    arithmetic_replayer=self.replayer,
                    replay_threads=1,
                    replay_segment_rows=None,
                )
            self.assertTrue(checked.independent_rows_replayed)
            replay.assert_called_once()
            serial_command = replay.call_args.args[0]
            self.assertNotIn("--segment-rows", serial_command)

    def test_factor_commitment_tamper_fails_closed(self) -> None:
        changed = replace(
            self.chunks[0],
            factor_support_digest="0" * 64,
        )
        completed = self._run(_plan((changed,), limit=500), threads=1)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("factor-support digest mismatch", completed.stderr)

    def test_arithmetic_summary_tamper_fails_closed(self) -> None:
        changed = replace(
            self.chunks[0],
            outgoing_upper=self.chunks[0].outgoing_upper + 1,
        )
        completed = self._run(_plan((changed,), limit=500), threads=1)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("outgoing directed state mismatch", completed.stderr)

    def test_gap_or_truncated_plan_fails_before_arithmetic(self) -> None:
        raw = _plan(self.chunks, limit=1000)
        changed = raw.replace(b"chunk\t501\t", b"chunk\t502\t", 1)
        completed = self._run(changed)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("range or directed-state chain", completed.stderr)
        truncated = self._run(raw[:-1])
        self.assertEqual(truncated.returncode, 2)
        self.assertIn("must end with exactly an LF", truncated.stderr)


if __name__ == "__main__":
    unittest.main()
