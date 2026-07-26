# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.zeta_zero_campaign import (  # noqa: E402
    EXPECTED_FLINT,
    EXPECTED_FLINT_RELEASE,
    EXPECTED_PYTHON_FLINT,
    PLATT_HEAD_2E4,
    PLATT_TRUDGIAN_RH_3E12,
    IsolatedOrdinate,
    ZetaCampaignError,
    canonical_json_bytes,
    create_plan,
    finalize_campaign,
    initialize_campaign,
    q128_cell_from_interval,
    replay_chunk,
    render_head_q128_lean_module,
    retained_head_q128_cells,
    run_campaign,
    verify_campaign,
)


class FakeBackend:
    def __init__(self, count: int = 22_491) -> None:
        self.count = count
        self.count_calls = 0
        self.isolation_calls: list[tuple[int, int, int]] = []

    def version_record(self) -> dict[str, object]:
        return {
            "python_flint": EXPECTED_PYTHON_FLINT,
            "flint": EXPECTED_FLINT,
            "flint_release": EXPECTED_FLINT_RELEASE,
        }

    def exact_zero_count(self, height: int, precision_bits: int) -> int:
        self.count_calls += 1
        return self.count

    def isolate_ordinates(
        self, first_index: int, count: int, precision_bits: int
    ) -> list[IsolatedOrdinate]:
        self.isolation_calls.append((first_index, count, precision_bits))
        result: list[IsolatedOrdinate] = []
        last_included = PLATT_HEAD_2E4.expected_zero_count
        for index in range(first_index, first_index + count):
            if index <= last_included:
                # Strictly increasing exact points in [10000, 19999].  Their
                # reciprocal sum is below the source profile's 5.15966 target.
                numerator = 10_000 * last_included + 9_999 * index
                exact = Fraction(numerator, last_included)
            else:
                exact = Fraction(20_001 + index - last_included - 1, 1)
            result.append(IsolatedOrdinate(exact, exact))
        return result


class ShiftedFakeBackend(FakeBackend):
    def isolate_ordinates(
        self, first_index: int, count: int, precision_bits: int
    ) -> list[IsolatedOrdinate]:
        result = super().isolate_ordinates(first_index, count, precision_bits)
        first = result[0]
        delta = Fraction(1, 1_000_000)
        result[0] = IsolatedOrdinate(first.lower + delta, first.upper + delta)
        return result


class ZetaZeroCampaignTests(unittest.TestCase):
    def test_named_profiles_pin_the_source_height_and_count(self) -> None:
        self.assertEqual(PLATT_HEAD_2E4.height, 20_000)
        self.assertEqual(PLATT_HEAD_2E4.expected_zero_count, 22_491)
        self.assertEqual(PLATT_TRUDGIAN_RH_3E12.height, 3_000_175_332_800)
        self.assertEqual(
            PLATT_TRUDGIAN_RH_3E12.expected_zero_count, 12_363_153_437_138
        )

    def test_plan_rejects_a_fresh_count_mismatch(self) -> None:
        with self.assertRaisesRegex(ZetaCampaignError, "requires 22491"):
            create_plan(PLATT_HEAD_2E4, backend=FakeBackend(count=22_490))

    def test_campaign_resumes_finalizes_and_replays(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialized = initialize_campaign(
                root,
                PLATT_HEAD_2E4,
                batch_size=11_246,
                precision_bits=96,
                backend=backend,
            )
            self.assertEqual(initialized["chunk_count"], 2)
            partial = run_campaign(
                root, max_chunks=1, replay_count=True, backend=backend
            )
            self.assertFalse(partial["complete"])
            self.assertEqual(partial["chunks_complete"], 1)
            structural = verify_campaign(root)
            self.assertFalse(structural["complete_chain"])
            self.assertFalse(structural["fresh_flint_replay_performed"])

            complete = run_campaign(root, replay_count=True, backend=backend)
            self.assertTrue(complete["complete"])
            final = finalize_campaign(root)
            self.assertTrue(final["all_zeros_through_height_on_critical_line"])
            self.assertFalse(final["lean_atom_discharged"])
            checked = verify_campaign(root, require_complete=True)
            self.assertTrue(checked["complete_chain"])
            self.assertTrue(checked["final_present"])
            self.assertIn("not_fresh_flint_replay", checked["classification"])

            replayed = replay_chunk(root, 1, backend=backend)
            self.assertEqual(replayed["records_recomputed"], 11_246)
            self.assertFalse(replayed["lean_atom_discharged"])

    def test_campaign_rejects_a_chunk_after_a_gap(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(
                root,
                PLATT_HEAD_2E4,
                batch_size=11_246,
                backend=backend,
            )
            (root / "chunk-000000000001.json").write_bytes(
                canonical_json_bytes({})
            )
            with self.assertRaisesRegex(ZetaCampaignError, "contiguous prefix"):
                verify_campaign(root)

    def test_campaign_rejects_noncanonical_or_duplicate_json(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(root, PLATT_HEAD_2E4, backend=backend)
            plan = root / "campaign.json"
            value = json.loads(plan.read_text(encoding="ascii"))
            plan.write_text(json.dumps(value), encoding="ascii")
            with self.assertRaisesRegex(ZetaCampaignError, "not canonical"):
                verify_campaign(root)

    def test_resume_rejects_a_different_implementation_source_hash(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(root, PLATT_HEAD_2E4, backend=backend)
            plan_path = root / "campaign.json"
            plan = json.loads(plan_path.read_text(encoding="ascii"))
            plan["provenance"]["implementation_source_sha256"] = "0" * 64
            plan_path.write_bytes(canonical_json_bytes(plan))
            with self.assertRaisesRegex(
                ZetaCampaignError, "differs from the source pinned"
            ):
                run_campaign(root, max_chunks=1, backend=backend)

    def test_fresh_chunk_replay_rejects_a_changed_interval(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(
                root,
                PLATT_HEAD_2E4,
                batch_size=22_492,
                backend=backend,
            )
            run_campaign(root, replay_count=False, backend=backend)
            with self.assertRaisesRegex(ZetaCampaignError, "fresh FLINT replay differs"):
                replay_chunk(root, 0, backend=ShiftedFakeBackend())

    def test_head_chunks_retain_and_authenticate_every_interval_preimage(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(
                root,
                PLATT_HEAD_2E4,
                batch_size=22_492,
                backend=backend,
            )
            run_campaign(root, replay_count=False, backend=backend)
            path = root / "chunk-000000000000.json"
            document = json.loads(path.read_text(encoding="ascii"))
            retained = document["retained_ordinate_intervals"]
            self.assertEqual(len(retained), 22_492)
            self.assertEqual(retained[0]["index"], 1)
            self.assertEqual(retained[-1]["index"], 22_492)
            changed = Fraction(
                retained[1]["lower"]["numerator"] + 1,
                retained[1]["lower"]["denominator"],
            )
            retained[1]["lower"] = {
                "numerator": changed.numerator,
                "denominator": changed.denominator,
            }
            retained[1]["upper"] = dict(retained[1]["lower"])
            path.write_bytes(canonical_json_bytes(document))
            with self.assertRaisesRegex(ZetaCampaignError, "retained interval digest"):
                verify_campaign(root, require_complete=True)

    def test_q128_rounding_and_reviewed_table_gate(self) -> None:
        cell = q128_cell_from_interval(
            1, IsolatedOrdinate(Fraction(3, 2), Fraction(3, 2))
        )
        self.assertEqual(cell.lower, 3 * (1 << 127))
        self.assertEqual(cell.upper, cell.lower)
        self.assertGreaterEqual(cell.reciprocal_upper * cell.lower, 1 << 256)
        with self.assertRaisesRegex(ZetaCampaignError, "namespace is malformed"):
            render_head_q128_lean_module((), namespace="Bad; #eval 1")

    def test_fake_campaign_cannot_impersonate_reviewed_q128_table(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_campaign(
                root,
                PLATT_HEAD_2E4,
                batch_size=22_492,
                backend=backend,
            )
            run_campaign(root, replay_count=False, backend=backend)
            finalize_campaign(root)
            with self.assertRaisesRegex(
                ZetaCampaignError, "differ from the reviewed claude_math table"
            ):
                retained_head_q128_cells(root)

    def test_cli_exposes_profiles_without_importing_flint(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_zeta_campaign.py", "profiles"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual(
            document["profiles"]["platt-trudgian-rh-3e12"]["height"],
            3_000_175_332_800,
        )
        self.assertFalse(document["lean_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
