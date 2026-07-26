# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import struct
import unittest

from tg_verifier import platt_pt21_inline_stationary as inline_wire


ROOT = Path(__file__).resolve().parents[1]


def _runner(environment: str, default: Path) -> Path | None:
    supplied = os.environ.get(environment)
    candidate = Path(supplied) if supplied else default
    return candidate if candidate.is_file() else None


def _one_json(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    rows = [row for row in completed.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise AssertionError(
            f"expected one JSON row, received {len(rows)}: "
            f"{completed.stdout!r}"
        )
    return json.loads(rows[0])


class PT21InlineStationarySourceTest(unittest.TestCase):
    def test_default_worker_is_compile_time_isolated(self) -> None:
        source = (
            ROOT
            / "gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu"
        ).read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        wire = (
            ROOT
            / "gpu/include/sparkinterval/"
            "tg_platt_inline_stationary_stream.hpp"
        ).read_text(encoding="utf-8")

        self.assertIn("pes::replay_captured(slot.capture)", source)
        replay = source.index("pes::replay_captured(slot.capture)")
        junction = source.index("psj::resolve_replayed_block(", replay)
        ordered_wait = source.index("std::unique_lock lock(replay_mutex)", replay)
        self.assertLess(junction, ordered_wait)
        self.assertIn(
            "SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION", source
        )
        for token in (
            "SPARKINTERVAL_CMAKE_BUILD_CONFIG",
            "kNdebugDefined",
            "kReleasePerformanceBuild",
            '\\"build_profile\\"',
            '\\"cmake_build_config\\"',
            '\\"ndebug_defined\\"',
            '\\"release_performance_build\\"',
        ):
            self.assertIn(token, source)
        self.assertIn(
            "sparkinterval-tg-platt-inline-stationary-qualification", cmake
        )
        default_target = cmake[
            cmake.index(
                "add_executable(sparkinterval-tg-platt-fused-source-worker-v2"
            ) :
            cmake.index(
                "add_executable(sparkinterval-tg-dirichlet-allchars"
            )
        ]
        self.assertNotIn(
            "SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION",
            default_target,
        )
        self.assertIn(
            'SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"',
            default_target,
        )

        for token in (
            "PT21IQH1",
            "PT21IQF1",
            "PT21IQT1",
            "PT21EVT1",
            "PT21STJ1",
            "event_record_sha256",
            "stationary_trace_sha256",
            "resolver_sha256",
            "flint_sha256",
            "kFiniteQualificationOnlyFlag",
        ):
            self.assertIn(token, wire)
        self.assertEqual(wire.count("PT21BLK1"), 1)
        for field in (
            '"sgn2_static_manifest_bound":false',
            '"multi_block_source_chain_closed":false',
            '"source_claim_ready":false',
            '"production_ready":false',
            '"pt21_atom_discharged":false',
        ):
            self.assertIn(field.replace('"', '\\"'), source)

    def test_real_block_zero_precision_non_nesting_uses_exact_hull(
        self,
    ) -> None:
        fixture = json.loads(
            (
                ROOT
                / "tests/fixtures/"
                "pt21_block0_precision_non_nesting.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(fixture["block"], 0)
        self.assertEqual(fixture["base_precision_bits"], 128)
        self.assertEqual(fixture["replay_precision_bits"], 192)

        def interval(value: object) -> tuple[Fraction, Fraction]:
            assert isinstance(value, dict)
            lower = value["lo"]
            upper = value["hi"]
            return (
                Fraction(lower["numerator"], lower["denominator"]),
                Fraction(upper["numerator"], upper["denominator"]),
            )

        non_nested = []
        for name in ("lower", "midpoint", "upper"):
            endpoint = fixture["endpoints"][name]
            base = interval(endpoint["base_interval"])
            replay = interval(endpoint["replay_interval"])
            hull = interval(endpoint["retained_hull"])
            self.assertEqual(
                hull,
                (min(base[0], replay[0]), max(base[1], replay[1])),
            )
            self.assertLessEqual(hull[0], base[0])
            self.assertGreaterEqual(hull[1], base[1])
            self.assertLessEqual(hull[0], replay[0])
            self.assertGreaterEqual(hull[1], replay[1])
            base_sign = 1 if base[0] > 0 else -1
            replay_sign = 1 if replay[0] > 0 else -1
            hull_sign = 1 if hull[0] > 0 else -1
            self.assertEqual(base_sign, replay_sign)
            self.assertEqual(base_sign, hull_sign)
            non_nested.append(
                not (base[0] <= replay[0] and replay[1] <= base[1])
            )
        self.assertEqual(non_nested, [False, True, True])


class PT21InlineStationaryNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inline = _runner(
            "TG_PLATT_INLINE_STATIONARY_KAT",
            ROOT
            / "build/pt21-inline/"
            "sparkinterval-tg-platt-inline-stationary-kat",
        )
        cls.standalone = _runner(
            "TG_PLATT_STATIONARY_JUNCTION",
            ROOT
            / "build/pt21-inline/"
            "sparkinterval-tg-platt-stationary-junction-benchmark",
        )
        if cls.inline is None or cls.standalone is None:
            raise unittest.SkipTest(
                "inline and standalone stationary junction KATs are required"
            )

    def test_inline_capture_matches_existing_standalone_and_rejects_tamper(
        self,
    ) -> None:
        environment = {
            **os.environ,
            "LD_LIBRARY_PATH": (
                "/tmp/flint-3.6-install/lib:"
                + os.environ.get("LD_LIBRARY_PATH", "")
            ),
        }
        inline_completed = subprocess.run(
            [str(self.inline), "--iterations=1"],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        inline = _one_json(inline_completed)
        standalone_completed = subprocess.run(
            [
                str(self.standalone),
                "--mode",
                "valid",
                "--fixture",
                "turing-closure",
                "--block",
                "0",
                "--iterations",
                "1",
                "--precision-hull-audit",
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        standalone = _one_json(standalone_completed)

        self.assertTrue(inline["test_success"])
        self.assertTrue(inline["inline_matches_standalone_bytes"])
        self.assertEqual(
            inline["event_record_hex"], standalone["event_record_hex"]
        )
        self.assertEqual(
            inline["junction_record_hex"], standalone["record_hex"]
        )
        self.assertEqual(
            inline["stationary_trace_hex"],
            standalone["stationary_trace_hex"],
        )
        for field in (
            "tampered_frame_rejected",
            "tampered_event_root_rejected",
            "zero_identity_rejected",
            "wrong_expected_identity_rejected",
            "zero_producer_rejected",
            "overflowing_range_rejected",
            "truncated_frame_rejected",
            "trailing_frame_rejected",
            "relabeled_frame_rejected",
            "cross_spliced_footer_rejected",
            "wrong_record_total_rejected",
            "trace_cap_rejected_without_partial_output",
            "unpinned_replay_precision_rejected",
        ):
            self.assertTrue(inline[field], field)
        self.assertGreater(inline["inline_junctions_per_second"], 0)
        self.assertLess(
            inline["zero_candidate_v2_trace_bytes"],
            inline["two_candidate_v2_trace_bytes"],
        )
        self.assertGreater(
            inline["representative_v2_bytes_per_candidate"], 0
        )
        self.assertLessEqual(
            inline["representative_candidates_within_16mib"],
            inline["absolute_candidate_roster_cap"],
        )
        self.assertFalse(inline["producer_sha256_self_verified"])
        self.assertTrue(
            inline["producer_sha256_requires_external_manifest_pin"]
        )
        self.assertFalse(inline["resolver_sha256_self_verified"])
        self.assertFalse(inline["flint_sha256_self_verified"])
        self.assertTrue(
            inline[
                "identity_pins_require_external_manifest_or_attestation"
            ]
        )
        self.assertFalse(inline["resolver_inputs_retained"])
        self.assertFalse(
            inline["resolver_input_sha256_recomputed_from_frame"]
        )
        self.assertFalse(
            inline["candidate_completeness_recomputed_from_frame"]
        )
        self.assertFalse(inline["independent_checker_complete"])
        self.assertEqual(
            inline["higher_precision_containment_semantics"],
            "replay_contained_in_retained_outward_hull",
        )

        stream = bytes.fromhex(str(inline["two_frame_stream_hex"]))
        replay = inline_wire.validate_bytes(
            stream,
            expected_gamma_stream_sha256="11" * 32,
            expected_producer_sha256="aa" * 32,
            expected_resolver_sha256="a5" * 32,
            expected_flint_sha256="5a" * 32,
        )
        self.assertTrue(replay["accepted"])
        self.assertFalse(replay["resolver_inputs_retained"])
        self.assertFalse(
            replay["resolver_input_sha256_recomputed_from_frame"]
        )
        self.assertFalse(
            replay["candidate_completeness_recomputed_from_frame"]
        )
        self.assertFalse(replay["independent_checker_complete"])
        self.assertFalse(replay["producer_sha256_self_verified"])
        self.assertFalse(replay["resolver_sha256_self_verified"])
        self.assertFalse(replay["flint_sha256_self_verified"])
        self.assertTrue(
            replay[
                "identity_pins_require_external_manifest_or_attestation"
            ]
        )
        self.assertEqual(len(replay["frames"]), 2)
        self.assertEqual(
            replay["frames"][0]["stationary_trace"].hex(),
            inline["stationary_trace_hex"],
        )
        self.assertTrue(
            replay["frames"][0]["trace_value"]["accepted"]
        )

        header = stream[: inline_wire.HEADER.size]
        footer = stream[-inline_wire.FOOTER.size :]
        first_offset = inline_wire.HEADER.size
        first_bytes = struct.unpack_from("<I", stream, first_offset + 12)[0]
        first = stream[first_offset : first_offset + first_bytes]
        second_offset = first_offset + first_bytes
        second_bytes = struct.unpack_from(
            "<I", stream, second_offset + 12
        )[0]
        second = stream[second_offset : second_offset + second_bytes]

        malformed = {
            "trailing": stream + b"\0",
            "truncated_footer": stream[:-1],
            "missing_frame": header + first + footer,
            "duplicate_frame": header + first + first + footer,
            "swapped_frames": header + second + first + footer,
        }
        for label, raw in malformed.items():
            with self.subTest(label=label), self.assertRaises(
                inline_wire.PT21InlineStationaryError
            ):
                inline_wire.validate_bytes(
                    raw,
                    expected_gamma_stream_sha256="11" * 32,
                    expected_producer_sha256="aa" * 32,
                    expected_resolver_sha256="a5" * 32,
                    expected_flint_sha256="5a" * 32,
                )

        cross_spliced = bytearray(stream)
        cross_spliced[72] ^= 1
        cross_spliced[224:256] = hashlib.sha256(
            inline_wire.HEADER_DOMAIN + cross_spliced[:224]
        ).digest()
        with self.assertRaisesRegex(
            inline_wire.PT21InlineStationaryError, "footer header_sha256"
        ):
            inline_wire.validate_bytes(
                bytes(cross_spliced),
                expected_gamma_stream_sha256="11" * 32,
                expected_producer_sha256=bytes(
                    cross_spliced[72:104]
                ).hex(),
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        overflowing_trace_total = bytearray(stream)
        footer_offset = len(stream) - inline_wire.FOOTER.size
        struct.pack_into(
            "<Q", overflowing_trace_total, footer_offset + 48, 2**64 - 1
        )
        overflowing_trace_total[
            footer_offset + 160 : footer_offset + 192
        ] = hashlib.sha256(
            inline_wire.FOOTER_DOMAIN
            + overflowing_trace_total[footer_offset : footer_offset + 160]
        ).digest()
        with self.assertRaisesRegex(
            inline_wire.PT21InlineStationaryError, "total_trace_bytes"
        ):
            inline_wire.validate_bytes(
                bytes(overflowing_trace_total),
                expected_gamma_stream_sha256="11" * 32,
                expected_producer_sha256="aa" * 32,
                expected_resolver_sha256="a5" * 32,
                expected_flint_sha256="5a" * 32,
            )

        for label, offset in (
            ("producer", 72),
            ("resolver", 104),
            ("FLINT", 136),
        ):
            zeroed = bytearray(header)
            zeroed[offset : offset + 32] = bytes(32)
            zeroed[224:256] = hashlib.sha256(
                inline_wire.HEADER_DOMAIN + zeroed[:224]
            ).digest()
            with self.subTest(zero=label), self.assertRaises(
                inline_wire.PT21InlineStationaryError
            ):
                inline_wire.parse_header(bytes(zeroed))

        for label, arguments in (
            ("producer", {"expected_producer_sha256": "ab" * 32}),
            ("resolver", {"expected_resolver_sha256": "a4" * 32}),
            ("FLINT", {"expected_flint_sha256": "5b" * 32}),
        ):
            pins = {
                "expected_gamma_stream_sha256": "11" * 32,
                "expected_producer_sha256": "aa" * 32,
                "expected_resolver_sha256": "a5" * 32,
                "expected_flint_sha256": "5a" * 32,
                **arguments,
            }
            with self.subTest(relabeled=label), self.assertRaises(
                inline_wire.PT21InlineStationaryError
            ):
                inline_wire.parse_header(header, **pins)

        for first_block, block_count in (
            (inline_wire.SOURCE_BLOCK_COUNT - 1, 2),
            (inline_wire.SOURCE_BLOCK_COUNT, 1),
            (0, 0),
        ):
            with self.subTest(
                first_block=first_block, block_count=block_count
            ), self.assertRaises(inline_wire.PT21InlineStationaryError):
                inline_wire._geometry(first_block, block_count)

        for field in (
            "hardy_z_endpoint_realization_proved",
            "flint_to_mathlib_realization_proved",
            "analytic_turing_realization_proved",
            "sgn2_static_manifest_bound",
            "multi_block_source_chain_closed",
            "source_claim_ready",
            "production_ready",
            "pt21_atom_discharged",
        ):
            self.assertFalse(inline[field], field)


if __name__ == "__main__":
    unittest.main()
