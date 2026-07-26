# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Differential known answers for the native PT21 v2 artifact builder.

Every accepted case here asserts BYTE identity between the pinned native
builder and the independent Python reference finalizer.  The Python
implementation is not being retired: it is the oracle these tests compare
against.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from tests.test_tg_platt_pt21_native_record_adapter import worker
from tg_verifier.platt_pt21_bounded_block_chain import (
    synthetic_required_packet,
)
from tg_verifier.platt_pt21_fused_artifact import (
    INTERPOLATION_PATCH_SHA256,
    PT21FusedArtifactError,
    TRACE_SCHEMA,
    _directed_sample_interval,
    _is_stationary_candidate_exact,
    build_block_artifact,
)
from tg_verifier.platt_pt21_lean_artifact import (
    STREAM_RANGES,
    UPSTREAM_COMMIT,
)
from tg_verifier.platt_pt21_native_artifact_fastpath import (
    NativeArtifactSession,
    PT21NativeArtifactFastpathError,
    STREAM_REQUEST_HEADER,
    STREAM_REQUEST_MAGIC,
    STREAM_RESPONSE_HEADER,
    STREAM_RESPONSE_MAGIC,
    build_block_artifact_native,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    PT21NativeRecordAdapterError,
    adapt_block,
    adapt_block_native_artifact_fastpath,
    adapt_block_native_artifact_session,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    UPSTREAM_COMMIT as PACKET_UPSTREAM_COMMIT,
    _fnv1a,
    load_required_sign_packet,
)


BUILDER_VARIABLE = "TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BLOCK_ZERO_TRACE = FIXTURES / "pt21_block0_fused_source_trace.json"


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def rational(value: Fraction | int) -> dict[str, int]:
    fraction = Fraction(value)
    return {
        "numerator": fraction.numerator,
        "denominator": fraction.denominator,
    }


def point(value: Fraction | int) -> dict[str, object]:
    endpoint = rational(value)
    return {"lo": endpoint, "hi": dict(endpoint)}


def flat_packet(directory: Path, block: int) -> Path:
    """One packet whose only sign change surrounds retained offset zero."""

    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        high = 1.0 if offset == 0 else -1.0
        samples.extend(SAMPLE.pack(high, 0.0, 0.25))
        if high > 0:
            signs[index // 8] |= 1 << (index % 8)
    source = f"native-artifact-builder-source-{block}".encode()
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
        _fnv1a(samples),
        _fnv1a(signs),
        len(source),
        hashlib.sha256(source).hexdigest().encode(),
        PACKET_UPSTREAM_COMMIT,
    )
    path = directory / f"required-{block}.bin"
    path.write_bytes(header + samples + signs)
    return path


def turing_side(a: int, b: int, common: Fraction) -> dict[str, object]:
    """A closed-form exact side whose quotient has a unique rounding."""

    log_term = Fraction(-(a + b), 4) * 21
    return {
        "s_bound": point(21),
        "log_pi": point(1),
        "im_gamma_integral": point(common - log_term),
        "pi": point(1),
    }


def turing_common(units: int, weight: int) -> Fraction:
    """Cancel the flank weight so the quotient is the exact integer target."""

    return Fraction(21 * units) + Fraction(21 * weight, 512)


def fused_trace(
    directory: Path,
    *,
    block: int,
    packet_sha256: str,
    resolutions: list[dict[str, object]],
    lower_count: int,
    main_slots: int,
    lower_weight: int = 0,
    upper_weight: int = 0,
    name: str = "source-trace.json",
) -> Path:
    height_lower = 10_000_000_000 + block * 1_008
    height_upper = height_lower + 1_008
    value = {
        "schema": TRACE_SCHEMA,
        "upstream_commit": UPSTREAM_COMMIT,
        "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
        "block": block,
        "required_sign_packet_sha256": packet_sha256,
        "producer": {
            "worker_sha256": "5c" * 32,
            "worker_size_bytes": 4_096,
            "precision_bits": 128,
            "all_required_samples_certified": True,
            "all_stationary_queries_resolved": True,
        },
        "stationary_resolutions": resolutions,
        "turing_inputs": {
            "lower": turing_side(
                height_lower - 21,
                height_lower,
                turing_common(lower_count, lower_weight),
            ),
            # The upper floor lands two above the lower ceiling for equal
            # constants, so the closed chain needs ``slots - 2`` extra units.
            "upper": turing_side(
                height_upper,
                height_upper + 21,
                turing_common(lower_count + main_slots - 2, upper_weight),
            ),
        },
        "semantic_status": {
            "hardy_z_endpoint_realization_proved": False,
            "main_multiplicity_realization_proved": False,
            "analytic_turing_realization_proved": False,
        },
    }
    path = directory / name
    path.write_bytes(canonical(value))
    return path


def stationary_resolution(left: int) -> dict[str, object]:
    """One exact +,-,+ dyadic resolution of the cell ``[left, left + 2]``."""

    return {
        "stream": "main",
        "outer_left_sample": left,
        "outer_right_sample": left + 2,
        "lower_offset": rational(left),
        "midpoint_offset": rational(Fraction(2 * left + 1, 2)),
        "upper_offset": rational(left + 1),
        "lower_value": point(1),
        "midpoint_value": point(-1),
        "upper_value": point(1),
    }


def _pack_packet(
    directory: Path, block: int, triples: list[tuple[float, float, float]]
) -> Path:
    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index, (high, low, radius) in enumerate(triples):
        samples.extend(SAMPLE.pack(high, low, radius))
        if high > 0:
            signs[index // 8] |= 1 << (index % 8)
    source = f"native-artifact-random-source-{block}".encode()
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
        _fnv1a(samples),
        _fnv1a(signs),
        len(source),
        hashlib.sha256(source).hexdigest().encode(),
        PACKET_UPSTREAM_COMMIT,
    )
    path = directory / f"random-required-{block}.bin"
    path.write_bytes(header + samples + signs)
    return path


def random_packet(
    directory: Path, *, block: int, seed: int
) -> tuple[Path, int]:
    """Build one varied packet and report its inconclusive-filter count."""

    rng = random.Random(seed)
    flips: set[int] = set()
    for lower, upper, count in (
        (-12_288, 12_288, 900),
        (-12_800, -12_288, 40),
        (12_288, 12_800, 40),
    ):
        while len({offset for offset in flips if lower <= offset < upper}) < (
            count
        ):
            flips.add(rng.randrange(lower, upper))
    positive = [True] * REQUIRED_COUNT
    current = rng.choice((True, False))
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        if offset - 1 in flips:
            current = not current
        positive[index] = current
    magnitude = [3.0] * REQUIRED_COUNT
    low = [0.0] * REQUIRED_COUNT
    radius = [0.0] * REQUIRED_COUNT
    for index in range(REQUIRED_COUNT):
        choice = rng.randrange(24)
        if choice == 0:
            magnitude[index] = 5e-324
        elif choice == 1:
            magnitude[index] = 1e-300
            radius[index] = 5e-324
        elif choice == 2:
            magnitude[index] = 3.0
            low[index] = 1e-17
            radius[index] = 1e-30
        elif choice == 3:
            magnitude[index] = 1e300
    # Interior extrema: a strictly smaller magnitude at the middle of a
    # same-sign triple.  Half use a one-ulp separation, which the outward
    # binary64 filter cannot certify or reject.
    inconclusive = 0
    used: set[int] = set()
    attempts = 0
    while len(used) < 12 and attempts < 4_000:
        attempts += 1
        offset = rng.randrange(-12_200, 12_200)
        index = offset + 12_870
        if any(abs(offset - other) < 6 for other in used):
            continue
        if not (
            positive[index] == positive[index + 1] == positive[index + 2]
        ):
            continue
        for step in range(-1, 4):
            magnitude[index + step] = 3.0
            low[index + step] = 0.0
            radius[index + step] = 0.0
        if len(used) % 2 == 0:
            magnitude[index + 1] = math.nextafter(3.0, 0.0)
            inconclusive += 1
        else:
            magnitude[index + 1] = 1.0
        used.add(offset)
    triples = [
        (
            magnitude[index] if positive[index] else -magnitude[index],
            low[index] if positive[index] else -low[index],
            radius[index],
        )
        for index in range(REQUIRED_COUNT)
    ]
    return _pack_packet(directory, block, triples), inconclusive


def inconclusive_triples(packet: Path) -> int:
    """Count same-sign triples the outward binary64 filter cannot decide.

    Every one of these is decided by exact rational arithmetic in both
    implementations, so a nonzero count proves the fallback is exercised.
    """

    loaded = load_required_sign_packet(packet)
    directed = tuple(
        _directed_sample_interval(sample) for sample in loaded.samples
    )
    total = 0
    for lower, upper in STREAM_RANGES.values():
        for offset in range(lower, upper - 1):
            first = loaded.samples[offset + 12_870]
            middle = loaded.samples[offset + 1 + 12_870]
            right = loaded.samples[offset + 2 + 12_870]
            if not (first.positive == middle.positive == right.positive):
                continue
            low = directed[offset + 12_870]
            mid = directed[offset + 1 + 12_870]
            high = directed[offset + 2 + 12_870]
            if middle.positive:
                certified = low[0] > mid[1] and high[0] > mid[1]
                rejected = (
                    first == middle
                    or right == middle
                    or low[1] <= mid[0]
                    or high[1] <= mid[0]
                )
            else:
                certified = mid[0] > low[1] and mid[0] > high[1]
                rejected = (
                    first == middle
                    or right == middle
                    or mid[1] <= low[0]
                    or mid[1] <= high[0]
                )
            if not certified and not rejected:
                total += 1
    return total


def matching_trace(directory: Path, packet: Path, *, block: int) -> Path:
    """Build the fused trace the reference builder demands for ``packet``."""

    loaded = load_required_sign_packet(packet)
    resolutions: list[dict[str, object]] = []
    slots = 0
    events: dict[str, list[tuple[int, int, int]]] = {
        stream: [] for stream in STREAM_RANGES
    }
    for name, (lower, upper) in STREAM_RANGES.items():
        for offset in range(lower, upper):
            if (
                loaded.samples[offset + 12_870].positive
                != loaded.samples[offset + 1 + 12_870].positive
            ):
                events[name].append((offset, offset + 1, 1))
                if name == "main":
                    slots += 1
        for offset in range(lower, upper - 1):
            if not _is_stationary_candidate_exact(loaded.samples, offset):
                continue
            events[name].append((offset, offset + 2, 2))
            if name == "main":
                slots += 2
            source_sign = loaded.samples[offset + 1 + 12_870].positive
            sign = 1 if source_sign else -1
            resolutions.append(
                {
                    "stream": name,
                    "outer_left_sample": offset,
                    "outer_right_sample": offset + 2,
                    "lower_offset": rational(offset),
                    "midpoint_offset": rational(Fraction(2 * offset + 1, 2)),
                    "upper_offset": rational(offset + 1),
                    "lower_value": point(sign),
                    "midpoint_value": point(-sign),
                    "upper_value": point(sign),
                }
            )
    left_lower, left_upper = STREAM_RANGES["left_flank"]
    right_lower, right_upper = STREAM_RANGES["right_flank"]
    lower_weight = -sum(
        multiplicity * (left - left_lower)
        for left, _right, multiplicity in events["left_flank"]
    )
    upper_weight = sum(
        multiplicity * ((right_upper - right_lower) - (right - right_lower))
        for _left, right, multiplicity in events["right_flank"]
    )
    del left_upper
    return fused_trace(
        directory,
        block=block,
        packet_sha256=loaded.sha256,
        resolutions=resolutions,
        lower_count=32_130_158_315,
        main_slots=slots,
        lower_weight=lower_weight,
        upper_weight=upper_weight,
        name=f"random-source-trace-{block}.json",
    )


class PT21NativeArtifactBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = os.environ.get(BUILDER_VARIABLE)
        if not value:
            raise unittest.SkipTest(
                f"{BUILDER_VARIABLE} is not set; native builder not built"
            )
        cls.builder = Path(value).resolve()
        if not cls.builder.is_file():
            raise unittest.SkipTest("native artifact builder is missing")
        cls.builder_sha256 = hashlib.sha256(
            cls.builder.read_bytes()
        ).hexdigest()

    # -- fixtures ---------------------------------------------------------

    def _flat_case(self, directory: Path, block: int) -> tuple[Path, Path]:
        packet = flat_packet(directory, block)
        packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
        trace = fused_trace(
            directory,
            block=block,
            packet_sha256=packet_sha256,
            resolutions=[],
            lower_count=32_130_158_315,
            main_slots=2,
        )
        return packet, trace

    def _block_zero_packet(self, directory: Path) -> Path:
        path = directory / "synthetic-required-sign-packet.bin"
        path.write_bytes(synthetic_required_packet())
        return path

    def _block_zero_synthetic_case(self, directory: Path) -> tuple[Path, Path]:
        packet = self._block_zero_packet(directory)
        packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
        trace = fused_trace(
            directory,
            block=0,
            packet_sha256=packet_sha256,
            resolutions=[
                stationary_resolution(0),
                stationary_resolution(10),
            ],
            lower_count=32_130_158_315,
            main_slots=3_469,
            name="synthetic-source-trace.json",
        )
        return packet, trace

    def _block_zero_measured_case(self, directory: Path) -> tuple[Path, Path]:
        packet = self._block_zero_packet(directory)
        trace = directory / "measured-source-trace.json"
        trace.write_bytes(BLOCK_ZERO_TRACE.read_bytes())
        return packet, trace

    def _native(self, packet: Path, trace: Path, **kwargs: object) -> bytes:
        produced = build_block_artifact_native(
            required_sign_packet=packet,
            source_trace=trace,
            builder=self.builder,
            expected_builder_sha256=self.builder_sha256,
            **kwargs,  # type: ignore[arg-type]
        )
        self.assertEqual(
            produced.sha256, hashlib.sha256(produced.raw).hexdigest()
        )
        return produced.raw

    def _reference(self, packet: Path, trace: Path) -> bytes:
        return canonical(build_block_artifact(packet, trace))

    # -- byte identity ----------------------------------------------------

    def test_flat_packet_bytes_are_identical_to_the_reference(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._flat_case(directory, 5)
            self.assertEqual(
                self._native(packet, trace), self._reference(packet, trace)
            )

    def test_block_zero_synthetic_bytes_are_identical(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_synthetic_case(directory)
            reference = self._reference(packet, trace)
            self.assertEqual(self._native(packet, trace), reference)
            value = json.loads(reference)
            self.assertEqual(len(value["streams"]["main"]["brackets"]), 3_469)
            self.assertEqual(len(value["streams"]["main"]["events"]), 3_467)

    def test_block_zero_measured_trace_bytes_are_identical(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            reference = self._reference(packet, trace)
            native = self._native(packet, trace)
            self.assertEqual(native, reference)
            self.assertEqual(
                hashlib.sha256(native).hexdigest(),
                hashlib.sha256(reference).hexdigest(),
            )

    def test_full_reference_validation_accepts_the_native_document(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            native = self._native(
                packet, trace, full_reference_validation=True
            )
            self.assertEqual(native, self._reference(packet, trace))

    def test_persistent_session_repeats_the_one_shot_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            reference = self._reference(packet, trace)
            raw_packet = packet.read_bytes()
            raw_trace = trace.read_bytes()
            with NativeArtifactSession(
                builder=self.builder,
                expected_builder_sha256=self.builder_sha256,
            ) as session:
                for _index in range(4):
                    produced = session.artifact(raw_packet, raw_trace)
                    self.assertEqual(produced.raw, reference)
                    self.assertEqual(produced.block, 0)
                    self.assertEqual(produced.window_center, 10_000_000_504)

    def test_randomised_packets_agree_byte_for_byte(self) -> None:
        """Differential agreement over varied DD disks and near ties.

        The generated packets include subnormal magnitudes (exact denominator
        ``2**1074``), nonzero DD low words, and one-ulp separations whose
        outward binary64 filter is inconclusive, so the exact rational
        fallback -- not the fast filter -- decides those stationary triples.
        """

        inconclusive_total = 0
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for trial in range(3):
                packet, _near_ties = random_packet(
                    directory, block=11 + trial, seed=97 + trial
                )
                inconclusive_total += inconclusive_triples(packet)
                trace = matching_trace(directory, packet, block=11 + trial)
                self.assertEqual(
                    self._native(packet, trace),
                    self._reference(packet, trace),
                )
        self.assertGreater(inconclusive_total, 0)

    # -- semantic guards --------------------------------------------------

    def test_no_acceptance_flag_is_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            value = json.loads(self._native(packet, trace))
            for key in value:
                self.assertNotIn("proved", key)
                self.assertNotIn("accept", key)
                self.assertNotIn("ready", key)
                self.assertNotIn("attest", key)

    def test_analytic_claim_in_the_trace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            value = json.loads(trace.read_bytes())
            value["semantic_status"][
                "analytic_turing_realization_proved"
            ] = True
            tampered = directory / "claiming-source-trace.json"
            tampered.write_bytes(canonical(value))
            with self.assertRaises(PT21FusedArtifactError):
                build_block_artifact(packet, tampered)
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(packet, tampered)

    # -- fail-closed ------------------------------------------------------

    def test_non_canonical_trace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            spaced = directory / "spaced-source-trace.json"
            spaced.write_bytes(
                json.dumps(json.loads(trace.read_bytes()), indent=1).encode()
                + b"\n"
            )
            with self.assertRaises(PT21FusedArtifactError):
                build_block_artifact(packet, spaced)
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(packet, spaced)

    def test_trace_bound_to_another_packet_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, _trace = self._block_zero_measured_case(directory)
            other = directory / "other-source-trace.json"
            value = json.loads(BLOCK_ZERO_TRACE.read_bytes())
            value["required_sign_packet_sha256"] = "0f" * 32
            other.write_bytes(canonical(value))
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(packet, other)

    def test_missing_stationary_resolution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet = self._block_zero_packet(directory)
            packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
            trace = fused_trace(
                directory,
                block=0,
                packet_sha256=packet_sha256,
                resolutions=[stationary_resolution(0)],
                lower_count=32_130_158_315,
                main_slots=3_469,
                name="incomplete-source-trace.json",
            )
            with self.assertRaises(PT21FusedArtifactError):
                build_block_artifact(packet, trace)
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(packet, trace)

    def test_truncated_packet_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            short = directory / "short-packet.bin"
            short.write_bytes(packet.read_bytes()[:-1])
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(short, trace)

    def test_flipped_sample_byte_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            raw = bytearray(packet.read_bytes())
            raw[HEADER.size] ^= 0x01
            flipped = directory / "flipped-packet.bin"
            flipped.write_bytes(bytes(raw))
            with self.assertRaises(PT21NativeArtifactFastpathError):
                self._native(flipped, trace)

    def test_unpinned_builder_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet, trace = self._block_zero_measured_case(directory)
            with self.assertRaises(PT21NativeArtifactFastpathError):
                build_block_artifact_native(
                    required_sign_packet=packet,
                    source_trace=trace,
                    builder=self.builder,
                    expected_builder_sha256="0e" * 32,
                )

    def test_stream_rejects_a_mismatched_payload_digest(self) -> None:
        raw_packet = synthetic_required_packet()
        raw_trace = BLOCK_ZERO_TRACE.read_bytes()
        request = STREAM_REQUEST_HEADER.pack(
            STREAM_REQUEST_MAGIC,
            1,
            STREAM_REQUEST_HEADER.size,
            0,
            len(raw_packet),
            len(raw_trace),
            hashlib.sha256(raw_packet).digest(),
            hashlib.sha256(raw_trace + b"x").digest(),
        )
        completed = subprocess.run(
            [str(self.builder), "--stream"],
            input=request + raw_packet + raw_trace,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, b"")
        self.assertIn(b"digest differs", completed.stderr)

    def test_stream_rejects_an_out_of_order_request_id(self) -> None:
        raw_packet = synthetic_required_packet()
        raw_trace = BLOCK_ZERO_TRACE.read_bytes()
        request = STREAM_REQUEST_HEADER.pack(
            STREAM_REQUEST_MAGIC,
            1,
            STREAM_REQUEST_HEADER.size,
            7,
            len(raw_packet),
            len(raw_trace),
            hashlib.sha256(raw_packet).digest(),
            hashlib.sha256(raw_trace).digest(),
        )
        completed = subprocess.run(
            [str(self.builder), "--stream"],
            input=request + raw_packet + raw_trace,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, b"")
        self.assertIn(b"framing differs", completed.stderr)

    def test_stream_response_header_is_fixed(self) -> None:
        raw_packet = synthetic_required_packet()
        raw_trace = BLOCK_ZERO_TRACE.read_bytes()
        request = STREAM_REQUEST_HEADER.pack(
            STREAM_REQUEST_MAGIC,
            1,
            STREAM_REQUEST_HEADER.size,
            0,
            len(raw_packet),
            len(raw_trace),
            hashlib.sha256(raw_packet).digest(),
            hashlib.sha256(raw_trace).digest(),
        )
        completed = subprocess.run(
            [str(self.builder), "--stream"],
            input=request + raw_packet + raw_trace,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, b"")
        (
            magic,
            version,
            header_bytes,
            request_id,
            artifact_bytes,
            block,
            window_center,
            packet_sha256,
            artifact_sha256,
        ) = STREAM_RESPONSE_HEADER.unpack(
            completed.stdout[: STREAM_RESPONSE_HEADER.size]
        )
        body = completed.stdout[STREAM_RESPONSE_HEADER.size :]
        self.assertEqual(magic, STREAM_RESPONSE_MAGIC)
        self.assertEqual(version, 1)
        self.assertEqual(header_bytes, STREAM_RESPONSE_HEADER.size)
        self.assertEqual(request_id, 0)
        self.assertEqual(artifact_bytes, len(body))
        self.assertEqual(block, 0)
        self.assertEqual(window_center, 10_000_000_504)
        self.assertEqual(packet_sha256, hashlib.sha256(raw_packet).digest())
        self.assertEqual(artifact_sha256, hashlib.sha256(body).digest())

    # -- record adapter ---------------------------------------------------

    def test_record_adapter_fastpath_reproduces_the_reference_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet = self._block_zero_packet(directory)
            stationary = directory / "stationary-trace.json"
            turing = directory / "turing-inputs.json"
            source = _measured_sidecars()
            if source is None:
                self.skipTest(
                    "measured block-zero stationary/Turing sidecars absent"
                )
            stationary.write_bytes(source[0])
            turing.write_bytes(source[1])
            measured_worker = worker(directory)
            reference = adapt_block(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=measured_worker,
            )
            fast = adapt_block_native_artifact_fastpath(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=measured_worker,
                native_builder=self.builder,
                expected_native_builder_sha256=self.builder_sha256,
            )
            self.assertEqual(fast.record, reference.record)
            self.assertEqual(fast.block_artifact, reference.block_artifact)
            self.assertEqual(fast.source_trace, reference.source_trace)
            with NativeArtifactSession(
                builder=self.builder,
                expected_builder_sha256=self.builder_sha256,
            ) as session:
                streamed = adapt_block_native_artifact_session(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=measured_worker,
                    session=session,
                )
            self.assertEqual(streamed.record, reference.record)

    def test_record_adapter_fastpath_rejects_an_unpinned_builder(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            packet = self._block_zero_packet(directory)
            source = _measured_sidecars()
            if source is None:
                self.skipTest(
                    "measured block-zero stationary/Turing sidecars absent"
                )
            stationary = directory / "stationary-trace.json"
            turing = directory / "turing-inputs.json"
            stationary.write_bytes(source[0])
            turing.write_bytes(source[1])
            with self.assertRaises(PT21NativeRecordAdapterError):
                adapt_block_native_artifact_fastpath(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=worker(directory),
                    native_builder=self.builder,
                    expected_native_builder_sha256="0d" * 32,
                )


def _measured_sidecars() -> tuple[bytes, bytes] | None:
    """Return the retained block-zero stationary/Turing sidecars if present.

    The record-adapter comparison needs the measured FLINT/Arb sidecars whose
    fused trace is the vendored fixture.  They are not vendored, so the two
    adapter cases are skipped where they are unavailable.
    """

    stationary = FIXTURES / "pt21_block0_stationary_trace.json"
    turing = FIXTURES / "pt21_block0_turing_inputs.json"
    if not stationary.is_file() or not turing.is_file():
        return None
    return stationary.read_bytes(), turing.read_bytes()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
