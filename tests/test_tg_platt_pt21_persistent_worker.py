# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from tg_verifier.platt_pt21_persistent_worker import (
    JUNCTION_REQUEST,
    JUNCTION_REQUEST_MAGIC,
    JUNCTION_RESPONSE,
    JUNCTION_RESPONSE_MAGIC,
    PT21PersistentWorkerError,
    SCHEMA,
    TURING_REQUEST,
    TURING_REQUEST_MAGIC,
    TURING_RESPONSE,
    TURING_RESPONSE_MAGIC,
    _decode_junction_response,
    _decode_turing_response,
    junction_request,
    run_persistent_bounded_batch,
    turing_request,
)
from tg_verifier.platt_pt21_fused_artifact import (
    REQUIRED_OFFSET_LOWER,
    _directed_sample_interval,
    _is_stationary_candidate,
    _is_stationary_candidate_exact,
    _sample_interval,
)
from tg_verifier.platt_required_sign_packet import RequiredSample


ROOT = Path(__file__).resolve().parents[1]


class PT21PersistentWorkerPureTest(unittest.TestCase):
    def test_request_frames_are_fixed_little_endian(self) -> None:
        junction = junction_request(0x01020304)
        self.assertEqual(len(junction), JUNCTION_REQUEST.size)
        self.assertEqual(
            junction,
            bytes.fromhex(
                "505432314a525131"
                "01000000"
                "18000000"
                "0403020100000000"
            ),
        )
        packet = "0123456789abcdef" * 4
        turing = turing_request(7, packet)
        self.assertEqual(len(turing), TURING_REQUEST.size)
        magic, version, encoded_bytes, block, digest = TURING_REQUEST.unpack(
            turing
        )
        self.assertEqual(magic, TURING_REQUEST_MAGIC)
        self.assertEqual(version, 1)
        self.assertEqual(encoded_bytes, TURING_REQUEST.size)
        self.assertEqual(block, 7)
        self.assertEqual(digest.hex(), packet)
        self.assertEqual(
            JUNCTION_REQUEST.unpack(junction)[0],
            JUNCTION_REQUEST_MAGIC,
        )

    def test_request_builders_fail_closed(self) -> None:
        with self.assertRaises(PT21PersistentWorkerError):
            junction_request(-1)
        with self.assertRaises(PT21PersistentWorkerError):
            junction_request(2_966_443_783)
        with self.assertRaises(PT21PersistentWorkerError):
            turing_request(0, "AA" * 32)
        with self.assertRaises(PT21PersistentWorkerError):
            turing_request(0, "0" * 63)

    def test_response_decoders_enforce_exact_framing(self) -> None:
        event = bytes(192)
        junction = bytes(400)
        trace = b"{}\n"
        frame_bytes = JUNCTION_RESPONSE.size + len(event + junction + trace)
        raw = JUNCTION_RESPONSE.pack(
            JUNCTION_RESPONSE_MAGIC,
            1,
            frame_bytes,
            7,
            len(event),
            len(junction),
            len(trace),
            0,
        ) + event + junction + trace
        with tempfile.TemporaryFile() as stream:
            stream.write(raw)
            stream.seek(0)
            parsed = _decode_junction_response(stream, expected_block=7)
        self.assertEqual(parsed.event_record, event)
        self.assertEqual(parsed.junction_record, junction)
        self.assertEqual(parsed.stationary_trace, trace)

        malformed_headers = (
            JUNCTION_RESPONSE.pack(
                JUNCTION_RESPONSE_MAGIC,
                1,
                frame_bytes + 1,
                7,
                len(event),
                len(junction),
                len(trace),
                0,
            ),
            JUNCTION_RESPONSE.pack(
                JUNCTION_RESPONSE_MAGIC,
                1,
                frame_bytes,
                8,
                len(event),
                len(junction),
                len(trace),
                0,
            ),
            JUNCTION_RESPONSE.pack(
                JUNCTION_RESPONSE_MAGIC,
                1,
                frame_bytes,
                7,
                len(event),
                len(junction),
                len(trace),
                1,
            ),
        )
        for header in malformed_headers:
            with self.subTest(header=header.hex()):
                with tempfile.TemporaryFile() as stream:
                    stream.write(header)
                    stream.seek(0)
                    with self.assertRaises(PT21PersistentWorkerError):
                        _decode_junction_response(stream, expected_block=7)

        artifact = b"{}\n"
        turing_raw = TURING_RESPONSE.pack(
            TURING_RESPONSE_MAGIC,
            1,
            TURING_RESPONSE.size + len(artifact),
        ) + artifact
        with tempfile.TemporaryFile() as stream:
            stream.write(turing_raw)
            stream.seek(0)
            self.assertEqual(_decode_turing_response(stream), artifact)
        with tempfile.TemporaryFile() as stream:
            stream.write(turing_raw[:-1])
            stream.seek(0)
            with self.assertRaises(PT21PersistentWorkerError):
                _decode_turing_response(stream)

    def test_directed_intervals_enclose_exact_binary64_arithmetic_edges(
        self,
    ) -> None:
        least_subnormal = math.ldexp(1.0, -1074)
        maximum = float.fromhex("0x1.fffffffffffffp+1023")
        samples = (
            RequiredSample(least_subnormal, 0.0, 0.0, True),
            RequiredSample(-least_subnormal, 0.0, 0.0, False),
            RequiredSample(1.0, -math.nextafter(1.0, 0.0), 0.0, True),
            RequiredSample(-1.0, math.nextafter(1.0, 0.0), 0.0, False),
            RequiredSample(maximum, maximum / 2.0, 0.0, True),
        )
        for sample in samples:
            with self.subTest(sample=sample):
                exact = _sample_interval(sample)
                outer = _directed_sample_interval(sample)
                if math.isfinite(outer[0]) and math.isfinite(outer[1]):
                    self.assertLessEqual(
                        Fraction.from_float(outer[0]), exact[0]
                    )
                    self.assertLessEqual(
                        exact[1], Fraction.from_float(outer[1])
                    )
                else:
                    self.assertEqual(outer, (-math.inf, math.inf))

    def test_directed_candidate_filter_matches_exact_reference(self) -> None:
        generator = random.Random(0x50543231)
        triples: list[tuple[RequiredSample, ...]] = []
        for _ in range(2_000):
            positive = bool(generator.getrandbits(1))
            sign = 1.0 if positive else -1.0
            values: list[RequiredSample] = []
            for _position in range(3):
                exponent = generator.randint(-900, 900)
                high = sign * math.ldexp(generator.uniform(1.0, 2.0), exponent)
                low = math.ldexp(
                    generator.uniform(-1.0, 1.0), exponent - 48
                )
                radius = math.ldexp(
                    generator.uniform(0.0, 1.0), exponent - 52
                )
                values.append(
                    RequiredSample(high, low, radius, positive)
                )
            triples.append(tuple(values))
        one = 1.0
        near = math.nextafter(one, math.inf)
        triples.extend(
            [
                (
                    RequiredSample(one, 0.0, 0.0, True),
                    RequiredSample(one, 0.0, 0.0, True),
                    RequiredSample(one, 0.0, 0.0, True),
                ),
                (
                    RequiredSample(near, 0.0, 0.0, True),
                    RequiredSample(one, 0.0, 0.0, True),
                    RequiredSample(near, 0.0, 0.0, True),
                ),
                (
                    RequiredSample(-near, 0.0, 0.0, False),
                    RequiredSample(-one, 0.0, 0.0, False),
                    RequiredSample(-near, 0.0, 0.0, False),
                ),
            ]
        )
        for index, samples in enumerate(triples):
            directed = tuple(
                _directed_sample_interval(sample) for sample in samples
            )
            actual = _is_stationary_candidate(
                samples, directed, {}, REQUIRED_OFFSET_LOWER
            )
            expected = _is_stationary_candidate_exact(
                samples, REQUIRED_OFFSET_LOWER
            )
            self.assertEqual(actual, expected, index)

    def test_native_artifact_builder_cannot_be_half_selected(self) -> None:
        """Both the path and its pinned digest are required together."""

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "out"
            common = {
                "junction_executable": Path("/nonexistent/junction"),
                "turing_executable": Path("/nonexistent/turing"),
                "flint_library": Path("/nonexistent/libflint.so.24.0.0"),
                "finalizer_executable": Path("/nonexistent/finalizer"),
                "output_directory": directory,
                "request_count": 1,
            }
            for extra in (
                {"native_artifact_builder": Path("/nonexistent/builder")},
                {"expected_native_artifact_builder_sha256": "5c" * 32},
            ):
                with self.assertRaises(PT21PersistentWorkerError) as caught:
                    run_persistent_bounded_batch(**common, **extra)
                self.assertIn(
                    "both its path and its expected SHA-256",
                    str(caught.exception),
                )
            self.assertFalse(directory.exists())

    def test_native_artifact_builder_cli_rejects_a_half_selection(
        self,
    ) -> None:
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "tools" / "tg_platt_pt21_persistent_worker.py"),
                "--junction-executable", "/nonexistent/junction",
                "--turing-executable", "/nonexistent/turing",
                "--flint-library", "/nonexistent/libflint.so.24.0.0",
                "--finalizer-executable", "/nonexistent/finalizer",
                "--output-directory", "/nonexistent/out",
                "--native-artifact-builder", "/nonexistent/builder",
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn(b"must be given together", completed.stderr)


class PT21PersistentWorkerNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build = ROOT / "build"
        cls.junction = Path(
            os.environ.get(
                "TG_PLATT_STATIONARY_JUNCTION",
                build
                / "pt21-junction"
                / "sparkinterval-tg-platt-stationary-junction-benchmark",
            )
        )
        cls.turing = Path(
            os.environ.get(
                "TG_PLATT_PT21_TURING_INPUTS",
                build
                / "tg-production-kat"
                / "sparkinterval-tg-platt-pt21-turing-inputs",
            )
        )
        cls.finalizer = Path(
            os.environ.get(
                "TG_PLATT_PT21_NATIVE_FINALIZER",
                build
                / "platt-fused"
                / "sparkinterval-tg-platt-pt21-native-finalizer",
            )
        )
        supplied_flint = os.environ.get("TG_PLATT_FLINT_LIBRARY")
        if supplied_flint:
            cls.flint = Path(supplied_flint).resolve()
        else:
            candidates = sorted(
                Path("/tmp/flint-3.6-install/lib").glob(
                    "libflint.so.*.*.*"
                )
            )
            cls.flint = candidates[-1] if candidates else Path("/missing")
        missing = [
            path
            for path in (
                cls.junction,
                cls.turing,
                cls.finalizer,
                cls.flint,
            )
            if not path.is_file()
        ]
        if missing:
            raise unittest.SkipTest(
                "persistent PT21 executables are missing: "
                + ", ".join(map(str, missing))
            )

    def test_native_artifact_fast_path_moves_no_retained_digest(self) -> None:
        """The opt-in fast path must change timings, never bytes."""

        value = os.environ.get("TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER")
        if not value:
            raise unittest.SkipTest(
                "TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER is not set"
            )
        builder = Path(value).resolve()
        if not builder.is_file():
            raise unittest.SkipTest("native artifact builder is missing")
        builder_sha256 = hashlib.sha256(builder.read_bytes()).hexdigest()
        reports: dict[str, dict[str, object]] = {}
        for label, extra in (
            ("python_reference", {}),
            (
                "pinned_native_fastpath",
                {
                    "native_artifact_builder": builder,
                    "expected_native_artifact_builder_sha256": builder_sha256,
                },
            ),
        ):
            with tempfile.TemporaryDirectory(
                prefix=f"pt21-persistent-{label}-"
            ) as temporary:
                result = run_persistent_bounded_batch(
                    junction_executable=self.junction,
                    turing_executable=self.turing,
                    flint_library=self.flint,
                    finalizer_executable=self.finalizer,
                    output_directory=Path(temporary),
                    request_count=2,
                    **extra,  # type: ignore[arg-type]
                )
            reports[label] = result.report
            self.assertEqual(
                result.report["artifact_builder_implementation"], label
            )
            self.assertEqual(result.report["byte_identical_pt21blk1_count"], 2)
            self.assertTrue(
                result.report["persistent_output_independently_replayed"]
            )
            self.assertTrue(
                result.report["persistent_output_native_shard_replayed"]
            )
        reference = reports["python_reference"]
        fast = reports["pinned_native_fastpath"]
        for key in (
            "chain_commitment_sha256",
            "shard_archive_sha256",
            "block_record_sha256",
            "event_record_sha256",
            "stationary_junction_record_sha256",
            "stationary_trace_sha256",
            "turing_inputs_sha256",
            "adapter_sources_sha256",
        ):
            self.assertEqual(fast[key], reference[key], key)
        self.assertEqual(reference["persistent_process_count"], 2)
        self.assertEqual(fast["persistent_process_count"], 3)
        self.assertIsNone(reference["native_artifact_builder_sha256"])
        self.assertEqual(
            fast["native_artifact_builder_sha256"], builder_sha256
        )
        for report in (reference, fast):
            for key in (
                "hardy_z_endpoint_realization_proved",
                "main_multiplicity_realization_proved",
                "analytic_turing_realization_proved",
                "azure_attestation_verified",
                "production_ready",
                "source_claim_ready",
                "source_eta_claimed",
            ):
                self.assertFalse(report[key], key)

    def test_three_requests_match_one_shot_and_replay(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="pt21-persistent-worker-test-"
        ) as temporary:
            result = run_persistent_bounded_batch(
                junction_executable=self.junction,
                turing_executable=self.turing,
                flint_library=self.flint,
                finalizer_executable=self.finalizer,
                output_directory=Path(temporary),
                request_count=3,
            )
        report = result.report
        self.assertEqual(report["schema"], SCHEMA)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["request_count"], 3)
        self.assertEqual(report["byte_identical_pt21evt1_count"], 3)
        self.assertEqual(report["byte_identical_pt21stj1_count"], 3)
        self.assertEqual(report["byte_identical_pt21blk1_count"], 3)
        self.assertEqual(report["persistent_process_count"], 2)
        self.assertEqual(report["per_request_native_process_start_count"], 0)
        self.assertTrue(report["persistent_output_independently_replayed"])
        self.assertTrue(report["persistent_output_native_shard_replayed"])
        self.assertEqual(
            report["performance_bottleneck"],
            "python_exact_rational_artifact_replay",
        )
        self.assertEqual(
            hashlib.sha256(result.event_record).hexdigest(),
            "38512c0d8e20f2dd612fb71e13821ba6d4ad82565f0c49f483fc92fd703bcb7d",
        )
        self.assertEqual(
            hashlib.sha256(result.turing_inputs).hexdigest(),
            "fd8f83a9363928e62a78f4a27134f2fd231576c522a3e254e36e1694c3576eb7",
        )
        self.assertEqual(
            hashlib.sha256(result.stationary_junction_record).hexdigest(),
            report["stationary_junction_record_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(result.block_record).hexdigest(),
            report["block_record_sha256"],
        )
        for field in (
            "hardy_z_endpoint_realization_proved",
            "flint_to_mathlib_realization_proved",
            "main_multiplicity_realization_proved",
            "analytic_turing_realization_proved",
            "azure_attestation_verified",
            "production_ready",
            "source_claim_ready",
            "source_work_count_measured",
            "source_eta_claimed",
        ):
            self.assertFalse(report[field], field)

    def test_turing_persistent_protocol_rejects_bad_magic(self) -> None:
        environment = dict(os.environ)
        environment["LD_LIBRARY_PATH"] = (
            str(self.flint.parent)
            + ":"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        request = bytearray(
            turing_request(0, hashlib.sha256(b"packet").hexdigest())
        )
        request[0] ^= 1
        completed = subprocess.run(
            [self.turing, "--persistent-requests", "1"],
            input=bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout)
        self.assertIn(b"request header differs", completed.stderr)

    def test_junction_persistent_protocol_rejects_bad_magic(self) -> None:
        environment = dict(os.environ)
        environment["LD_LIBRARY_PATH"] = (
            str(self.flint.parent)
            + ":"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        request = bytearray(junction_request(0))
        request[0] ^= 1
        completed = subprocess.run(
            [
                self.junction,
                "--mode",
                "valid",
                "--fixture",
                "turing-closure",
                "--persistent-requests",
                "1",
                "--resolver-sha256",
                hashlib.sha256(self.junction.read_bytes()).hexdigest(),
                "--flint-sha256",
                hashlib.sha256(self.flint.read_bytes()).hexdigest(),
            ],
            input=bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout)
        self.assertIn(b"request header differs", completed.stderr)

    def test_synthetic_junction_cannot_relabel_block_zero(self) -> None:
        environment = dict(os.environ)
        environment["LD_LIBRARY_PATH"] = (
            str(self.flint.parent)
            + ":"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        completed = subprocess.run(
            [
                self.junction,
                "--mode",
                "valid",
                "--fixture",
                "turing-closure",
                "--persistent-requests",
                "1",
                "--resolver-sha256",
                hashlib.sha256(self.junction.read_bytes()).hexdigest(),
                "--flint-sha256",
                hashlib.sha256(self.flint.read_bytes()).hexdigest(),
            ],
            input=junction_request(1),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout)
        self.assertIn(b"restricted to block zero", completed.stderr)

    def test_junction_rejects_noncanonical_numeric_argument(self) -> None:
        environment = dict(os.environ)
        environment["LD_LIBRARY_PATH"] = (
            str(self.flint.parent)
            + ":"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        completed = subprocess.run(
            [
                self.junction,
                "--mode",
                "valid",
                "--fixture",
                "turing-closure",
                "--persistent-requests",
                "1junk",
                "--resolver-sha256",
                hashlib.sha256(self.junction.read_bytes()).hexdigest(),
                "--flint-sha256",
                hashlib.sha256(self.flint.read_bytes()).hexdigest(),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout)
        self.assertIn(
            b"is not an unsigned decimal integer", completed.stderr
        )

    def test_native_workers_reject_trailing_request_bytes(self) -> None:
        environment = dict(os.environ)
        environment["LD_LIBRARY_PATH"] = (
            str(self.flint.parent)
            + ":"
            + environment.get("LD_LIBRARY_PATH", "")
        )
        cases = (
            (
                [
                    self.turing,
                    "--persistent-requests",
                    "1",
                ],
                turing_request(
                    0, hashlib.sha256(b"packet").hexdigest()
                ),
                TURING_RESPONSE_MAGIC,
                b"Turing request stream has trailing bytes",
            ),
            (
                [
                    self.junction,
                    "--mode",
                    "valid",
                    "--fixture",
                    "turing-closure",
                    "--persistent-requests",
                    "1",
                    "--resolver-sha256",
                    hashlib.sha256(self.junction.read_bytes()).hexdigest(),
                    "--flint-sha256",
                    hashlib.sha256(self.flint.read_bytes()).hexdigest(),
                ],
                junction_request(0),
                JUNCTION_RESPONSE_MAGIC,
                b"junction request stream has trailing bytes",
            ),
        )
        for command, request, response_magic, diagnostic in cases:
            with self.subTest(command=command[0]):
                completed = subprocess.run(
                    command,
                    input=request + b"\0",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    timeout=10,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertTrue(completed.stdout.startswith(response_magic))
                self.assertIn(diagnostic, completed.stderr)


if __name__ == "__main__":
    unittest.main()
