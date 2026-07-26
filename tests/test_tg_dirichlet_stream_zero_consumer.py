# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_stream_zero_consumer as consumer  # noqa: E402
import tg_verifier.dirichlet_root_number_stage as root_stage  # noqa: E402
from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    COMPLEX_INTERVAL,
    OUTPUT_HEADER,
)


PINNED_FLINT = (
    consumer.FLINT_IMPORT_ERROR is None
    and consumer.flint.__version__ == "0.9.0"
    and consumer.flint.__FLINT_VERSION__ == "3.6.0"
)
MPFR_CHECKER = (
    ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"
)


class DirichletStreamConsumerStructuralTests(unittest.TestCase):
    def test_capability_fails_closed_on_source_claims(self) -> None:
        report = consumer.capability()
        self.assertTrue(report["persistent_multi_frame_protocol"])
        self.assertTrue(report["exact_character_identity_reconstruction"])
        self.assertFalse(report["source_performance_ready"])
        self.assertFalse(report["zero_completeness_claimed"])
        self.assertFalse(report["external_atom_discharged"])

    def test_control_rejects_unbound_upstream_semantics(self) -> None:
        with self.assertRaises(consumer.DirichletStreamConsumerError):
            consumer.make_control(
                frame_index=0,
                q=5,
                batch_count=1,
                first_t_numerator=0,
                t_denominator=64,
                t_step_numerator=5,
                upstream_receipts={},
            )

    def test_direct_root_source_work_is_explicitly_prohibitive(self) -> None:
        work = consumer.direct_root_source_work()
        self.assertEqual(work["residue_visits"], 7_884_109_109_859_397)
        self.assertEqual(work["nonzero_gauss_terms"], 6_584_344_411_462_564)
        self.assertFalse(work["source_performance_ready"])


@unittest.skipUnless(PINNED_FLINT, "requires python-flint 0.9.0 / FLINT 3.6.0")
class DirichletStreamConsumerArbTests(unittest.TestCase):
    def test_two_frame_known_answer_and_fresh_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = consumer.write_known_answer_bundle(root)
            receipt = result["receipt"]
            self.assertEqual(receipt["frame_count"], 2)
            self.assertEqual(receipt["root_number_modulus_count"], 1)
            self.assertEqual(receipt["root_number_character_count"], 3)
            self.assertEqual(receipt["primitive_sample_count"], 387)
            self.assertEqual(receipt["candidate_bracket_count"], 6)
            self.assertEqual(receipt["indeterminate_sample_count"], 0)
            self.assertEqual(result["audit"]["direct_hardy_sign_changes"], 6)
            self.assertFalse(receipt["production_accept"])
            replay = consumer.verify_paths(
                root / "control.ndjson",
                root / "frames.bin",
                root / "events.ndjson",
                root / "receipt.json",
            )
            self.assertTrue(replay["accepted"])

    def test_group_exponent_not_character_order_root_regression(self) -> None:
        roots = consumer._character_root_records(5, precision=192)
        quadratic = next(row for row in roots if row.conrey_number == 4)
        self.assertEqual(consumer.dirichlet_char(5, 4).order(), 2)
        self.assertEqual(consumer.dirichlet_char(5, 4).group().exponent(), 4)
        self.assertTrue(quadratic.root_number.real > 0)
        self.assertTrue(quadratic.root_number.imag.contains(0))
        self.assertTrue(abs(quadratic.root_number).contains(1))

    @unittest.skipUnless(MPFR_CHECKER.is_file(), "requires built MPFR TGDAFF checker")
    def test_hash_bound_root_artifact_replaces_quadratic_hot_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            direct = consumer.write_known_answer_bundle(root / "direct")["receipt"]
            additive = root_stage.write_additive_input(
                root / "root-input.bin", q=5, precision=256
            )
            subprocess.run(
                [
                    str(MPFR_CHECKER),
                    "compute",
                    str(root / "root-input.bin"),
                    str(root / "root-transform.bin"),
                    "256",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            root_receipt = root_stage.consume_transform_path(
                root / "root-transform.bin",
                root / "roots.bin",
                root / "roots.json",
                q=5,
                additive_receipt=additive,
                precision=256,
            )
            controls = []
            for raw in (root / "direct/control.ndjson").read_bytes().splitlines():
                row = json.loads(raw)
                row["root_number_mode"] = root_stage.ROOT_ALGORITHM_ID
                controls.append(consumer.canonical_json_bytes(row))
            (root / "artifact-control.ndjson").write_bytes(b"".join(controls))
            artifact = consumer.consume_paths(
                root / "artifact-control.ndjson",
                root / "direct/frames.bin",
                root / "artifact-events.ndjson",
                root / "artifact-receipt.json",
                precision=192,
                root_artifact_path=root / "roots.bin",
                root_receipt_path=root / "roots.json",
            )
            self.assertEqual(
                artifact["root_number_mode"], root_stage.ROOT_ALGORITHM_ID
            )
            self.assertTrue(artifact["root_number_artifact_supplied"])
            self.assertTrue(artifact["source_performance_ready"])
            self.assertIsNone(artifact["source_performance_blocker"])
            self.assertEqual(
                artifact["candidate_bracket_count"],
                direct["candidate_bracket_count"],
            )
            self.assertEqual(
                artifact["sign_decisions_sha256"],
                direct["sign_decisions_sha256"],
            )
            self.assertIn(
                root_receipt["root_artifact_sha256"],
                json.dumps(artifact, sort_keys=True),
            )
            replay = consumer.verify_paths(
                root / "artifact-control.ndjson",
                root / "direct/frames.bin",
                root / "artifact-events.ndjson",
                root / "artifact-receipt.json",
                precision=192,
                root_artifact_path=root / "roots.bin",
                root_receipt_path=root / "roots.json",
            )
            self.assertTrue(replay["accepted"])

    def test_malformed_nonprimitive_value_fails_before_discard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            consumer.write_known_answer_bundle(root)
            raw = bytearray((root / "frames.bin").read_bytes())
            # Frequency zero is nonprimitive for q=5.  It is still parsed and
            # validated even though it is never passed to completed-L.
            offset = OUTPUT_HEADER.size
            raw[offset : offset + COMPLEX_INTERVAL.size] = COMPLEX_INTERVAL.pack(
                math.nan, math.nan, 0.0, 0.0
            )
            (root / "malformed.bin").write_bytes(raw)
            with self.assertRaisesRegex(
                consumer.DirichletStreamConsumerError, "malformed interval"
            ):
                consumer.consume_paths(
                    root / "control.ndjson",
                    root / "malformed.bin",
                    root / "bad-events.ndjson",
                    root / "bad-receipt.json",
                )

    def test_persistent_stdin_cli_uses_one_process_for_both_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            consumer.write_known_answer_bundle(root)
            events = root / "pipe-events.ndjson"
            receipt = root / "pipe-receipt.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tests/tg_dirichlet_stream_consumer_kat_worker.py",
                    "consume",
                    str(root / "control.ndjson"),
                    "-",
                    str(events),
                    str(receipt),
                ],
                cwd=ROOT,
                input=(root / "frames.bin").read_bytes(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(b'"frame_count":2', completed.stdout)
            self.assertTrue(events.is_file())
            self.assertTrue(receipt.is_file())

    def test_replay_rejects_event_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            consumer.write_known_answer_bundle(root)
            (root / "events.ndjson").write_bytes(
                (root / "events.ndjson").read_bytes() + b"{}\n"
            )
            with self.assertRaisesRegex(
                consumer.DirichletStreamConsumerError, "replay events differ"
            ):
                consumer.verify_paths(
                    root / "control.ndjson",
                    root / "frames.bin",
                    root / "events.ndjson",
                    root / "receipt.json",
                )


if __name__ == "__main__":
    unittest.main()
