# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Adversarial tests for the one-pass CH25 psi affine supervisor."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.psi_affine_guard_campaign import (
    CAPABILITIES,
    CHILD_DIRECTORY,
    FINAL_NAME,
    PLAN_NAME,
    RECEIPT_DIRECTORY,
    SCALE,
    U128_LIMIT,
    PsiAffineCampaignError,
    _lower_radius,
    command_for_shard,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt_bytes,
    initialize_campaign,
    run_campaign,
    verify_campaign,
)
from tg_verifier.psi_residual_campaign import (
    CRLIBM_COMMIT,
    PRIMESIEVE_COMMIT,
    finalize_campaign as finalize_two_pass,
    initialize_campaign as initialize_two_pass,
    reduce_summaries,
    run_phase,
)


CLI = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "tg_psi_affine_guard_campaign.py"
)


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
from math import isqrt
import json

S = 1 << 64

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--sieve-size-kib", type=int, required=True)
p.add_argument("--mode", choices=("affine", "summary", "verify"), required=True)
p.add_argument("--incoming-lower", type=int, default=0)
p.add_argument("--incoming-upper", type=int, default=0)
a = p.parse_args()
upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
delta = [count * S, count * S]
event_sha = hashlib.sha256(
    f"fake-psi-events-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
row_sha = hashlib.sha256(
    f"fake-psi-rows-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
common = {
    "classification": "source-scale-shard-not-lean-proof",
    "atom": "ch25-psi-1e13",
    "primesieve_commit": "4f85384851da23c36c01ec01ef85b5d9d246e556",
    "crlibm_commit": "eb3063791aa75bc9705b49283bf14250465220a7",
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "work_count": count,
    "scale_bits": 64,
    "sieve_size_kib": a.sieve_size_kib,
    "log_interval_encoding": "crlibm-binary64-directed-to-q64-v1",
    "event_encoding": "u64be-value-u64be-prime-u32be-exponent-v1",
    "event_sha256": event_sha,
    "row_encoding": "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1",
    "row_sha256": row_sha,
    "prime_power_events": count,
    "prime_events": count,
    "higher_power_events": 0,
    "state_components": ["psi_lower_q64", "psi_upper_q64"],
    "delta": delta,
    "accepted": True,
    "elapsed_seconds": 0.001,
    "execution_attested": False,
    "lean_atom_discharged": False,
}
if a.mode == "affine":
    value = a.lower
    lower_root = isqrt((2 * value) << 32)
    lower_radius = lower_root << 48
    upper_root = isqrt(value << 32)
    upper_radius = (19764819 * upper_root * (1 << 48)) // 25000000
    common.update({
        "algorithm": "ch25-psi-prime-power-affine-guard-v1",
        "mode": "affine",
        "guard_encoding": "independent-q64-rectangle-with-lower-le-upper-v1",
        "allowed_incoming_q64": {
            "lower_min": max(0, value * S - lower_radius),
            "upper_max": value * S + upper_radius - S,
            "predicate": "lower_min<=lower<=upper<=upper_max",
        },
        "guard_witnesses": {
            "lower_min": {
                "event_index": 0,
                "value": value,
                "prefix_delta_q64": 0,
                "radius_q64": lower_radius,
                "strict": False,
                "kind": "lower_left_limit",
            },
            "upper_max": {
                "event_index": 0,
                "value": value,
                "prefix_delta_q64": S,
                "radius_q64": upper_radius,
                "kind": "upper_post_jump",
            },
        },
        "guard_derivation": {
            "sqrt_fraction_bits": 16,
            "lower_radius": "floor(sqrt(2*x)*2^16)*2^48",
            "upper_radius":
                "floor(19764819*floor(sqrt(x)*2^16)*2^48/25000000)",
        },
        "terminal_strict_lower_constrained": False,
        "incoming_state": None,
        "outgoing_state": None,
    })
else:
    incoming = [a.incoming_lower, a.incoming_upper]
    outgoing = [incoming[0] + delta[0], incoming[1] + delta[1]]
    common.update({
        "algorithm": "ch25-psi-prime-power-two-pass-v1",
        "mode": a.mode,
        "guards": (
            {} if a.mode == "summary" else {
                "ch25-psi-1e13": {
                    "lower_guard": incoming,
                    "upper_guard": incoming,
                    "witnesses": [],
                }
            }
        ),
        "incoming_state": None if a.mode == "summary" else incoming,
        "outgoing_state": None if a.mode == "summary" else outgoing,
        "exact_fallbacks": {
            "lower_left_limit": 0,
            "upper_post_jump": 0,
            "terminal_lower": 0,
        },
        "terminal_strict_lower_checked": False,
    })
print(json.dumps(common, sort_keys=True))
'''


def upstream_manifest() -> dict[str, object]:
    return {
        "kind": "sparkinterval.pinned_upstream_bundle.v1",
        "components": {
            "primesieve": {
                "name": "kimwalisch/primesieve segmented prime sieve",
                "repository": "https://github.com/kimwalisch/primesieve.git",
                "commit": PRIMESIEVE_COMMIT,
                "license": "BSD-2-Clause",
                "tracked_file_count": 159,
                "tracked_bytes": 1_496_122,
                "tree_sha256": (
                    "f67523ec2a0985e2338dbddb0589ab47fe6eeb11a7d17583b8f0f113a9000f92"
                ),
            },
            "crlibm": {
                "name": "crlibm correctly rounded elementary functions",
                "repository": "https://github.com/taschini/crlibm.git",
                "commit": CRLIBM_COMMIT,
                "license": "LGPL-2.1-or-later",
                "tracked_file_count": 253,
                "tracked_bytes": 8_929_126,
                "tree_sha256": (
                    "0eaccef04d464f8a827a27b044887df37717503d46cce45d064a5ca22840a76c"
                ),
            },
        },
    }


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


class PsiAffineGuardCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        )
        self.source = self.root / "tg_psi_affine_guard_shard.cpp"
        self.source.write_text(
            "// bounded fake affine adapter\n", encoding="utf-8"
        )
        self.upstream = self.root / "PSI_UPSTREAMS.json"
        self.upstream.write_text(
            json.dumps(upstream_manifest(), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.output = self.root / "affine-campaign"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize(self) -> None:
        result = initialize_campaign(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output_directory=self.output,
            shard_span=4,
            sieve_size_kib=64,
            domain_upper_exclusive=14,
            allow_bounded_test=True,
        )
        self.assertEqual(
            (result.mode, result.shard_count, result.receipts),
            ("bounded_test", 3, 0),
        )

    def receipt(self, index: int) -> bytes:
        return subprocess.run(
            command_for_shard(self.output, index),
            check=True,
            stdout=subprocess.PIPE,
        ).stdout

    def test_parallel_run_scan_and_commit_are_fail_closed(self) -> None:
        self.initialize()
        running = run_campaign(self.output, workers=3)
        self.assertEqual(running.receipts, 3)
        self.assertFalse(running.complete)
        final = finalize_campaign(self.output)
        self.assertTrue(final.complete)
        self.assertEqual(final.final_state, (12 * SCALE, 12 * SCALE))
        self.assertIsNotNone(final.child_merkle_root_sha256)
        self.assertIsNotNone(final.certificate_root_sha256)
        certificate = load_json(
            self.output / FINAL_NAME, require_canonical=True
        )
        self.assertEqual(certificate["root_state"], [0, 0])
        self.assertEqual(certificate["capabilities"], CAPABILITIES)
        self.assertEqual(len(certificate["ordered_child_sha256"]), 3)
        self.assertEqual(
            len(
                list(
                    (self.output / CHILD_DIRECTORY).glob("child-*.json")
                )
            ),
            3,
        )
        self.assertEqual(verify_campaign(self.output), final)

    def test_semantics_match_old_two_pass_supervisor(self) -> None:
        self.initialize()
        run_campaign(self.output, workers=3)
        affine = finalize_campaign(self.output)

        old = self.root / "two-pass-campaign"
        initialize_two_pass(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output_directory=old,
            shard_span=4,
            sieve_size_kib=64,
            domain_upper_exclusive=14,
            allow_bounded_test=True,
        )
        run_phase(old, phase="summary", workers=3)
        derived = reduce_summaries(old)
        run_phase(old, phase="verify", workers=3)
        two_pass = finalize_two_pass(old)
        self.assertEqual(affine.final_state, two_pass.final_state)
        for index in range(3):
            child = load_json(
                self.output
                / CHILD_DIRECTORY
                / f"child-{index:08d}.json",
                require_canonical=True,
            )
            entry = derived["entries"][index]
            self.assertEqual(child["delta"], entry["delta"])
            self.assertEqual(child["event_sha256"], entry["event_sha256"])
            self.assertEqual(child["row_sha256"], entry["row_sha256"])
            self.assertEqual(child["incoming_state"], entry["incoming"])
            self.assertEqual(child["outgoing_state"], entry["outgoing"])

    def test_grouped_dispatch_is_disjoint_and_complete(self) -> None:
        self.initialize()
        self.assertEqual(
            grouped_shard_indices(
                self.output, group_index=0, group_count=2
            ),
            (0, 2),
        )
        self.assertEqual(
            grouped_shard_indices(
                self.output, group_index=1, group_count=2
            ),
            (1,),
        )
        run_campaign(
            self.output, shard_indices=(0, 2), workers=2
        )
        self.assertEqual(verify_campaign(self.output).receipts, 2)
        run_campaign(self.output, shard_indices=(1,), workers=1)
        self.assertEqual(verify_campaign(self.output).receipts, 3)
        finalize_campaign(self.output)

    def test_incomplete_receipts_cannot_be_finalized(self) -> None:
        self.initialize()
        run_campaign(self.output, max_shards=2, workers=2)
        with self.assertRaisesRegex(PsiAffineCampaignError, "incomplete"):
            finalize_campaign(self.output)

    def test_receipt_is_bound_to_exact_plan_index_and_bytes(self) -> None:
        self.initialize()
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "range|config"
        ):
            ingest_receipt_bytes(self.output, 0, self.receipt(1))
        raw = self.receipt(0)
        ingest_receipt_bytes(self.output, 0, raw)
        ingest_receipt_bytes(self.output, 0, raw)
        changed = json.loads(raw)
        changed["elapsed_seconds"] = 0.002
        with self.assertRaisesRegex(PsiAffineCampaignError, "different bytes"):
            ingest_receipt_bytes(self.output, 0, json_bytes(changed))

    def test_algorithm_pin_digest_and_trust_flag_mutations_are_rejected(self) -> None:
        self.initialize()
        raw = self.receipt(0)
        mutations = (
            ("algorithm", "wrong", "identity"),
            ("crlibm_commit", "0" * 40, "identity"),
            ("event_sha256", "F" * 64, "SHA-256"),
            ("execution_attested", True, "identity|trust"),
        )
        for field, value, pattern in mutations:
            changed = json.loads(raw)
            changed[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    PsiAffineCampaignError, pattern
                ):
                    ingest_receipt_bytes(
                        self.output, 0, json_bytes(changed)
                    )

    def test_root_rectangle_violation_is_rejected_by_scan(self) -> None:
        self.initialize()
        changed = json.loads(self.receipt(0))
        witness = changed["guard_witnesses"]["lower_min"]
        witness["value"] = 5
        witness["radius_q64"] = _lower_radius(5, False)
        changed["allowed_incoming_q64"]["lower_min"] = (
            5 * SCALE - witness["radius_q64"]
        )
        ingest_receipt_bytes(self.output, 0, json_bytes(changed))
        run_campaign(self.output, shard_indices=(1, 2), workers=2)
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "root-derived"
        ):
            finalize_campaign(self.output)

    def test_overflow_admission_and_impossible_counts_are_rejected(self) -> None:
        self.initialize()
        raw = self.receipt(0)
        overflowing = json.loads(raw)
        overflowing["allowed_incoming_q64"]["upper_max"] = U128_LIMIT - 1
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "overflow|rectangle"
        ):
            ingest_receipt_bytes(
                self.output, 0, json_bytes(overflowing)
            )
        counts = json.loads(raw)
        counts["prime_power_events"] = 5
        counts["prime_events"] = 5
        counts["delta"] = [5 * SCALE, 5 * SCALE]
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "shard width"
        ):
            ingest_receipt_bytes(self.output, 0, json_bytes(counts))

    def test_gap_or_extra_artifact_is_rejected(self) -> None:
        self.initialize()
        plan = load_json(
            self.output / PLAN_NAME, require_canonical=True
        )
        broken = deepcopy(plan)
        broken["shards"][1]["lower"] += 1
        (self.output / PLAN_NAME).write_bytes(canonical_json_bytes(broken))
        with self.assertRaises(PsiAffineCampaignError):
            verify_campaign(self.output)

        self.output = self.root / "fresh-campaign"
        self.initialize()
        run_campaign(self.output, workers=3)
        extra = self.output / RECEIPT_DIRECTORY / "unplanned.json"
        extra.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "unexpected file"
        ):
            verify_campaign(self.output)

    def test_omitted_receipt_or_mutated_child_breaks_replay(self) -> None:
        self.initialize()
        run_campaign(self.output, workers=3)
        finalize_campaign(self.output)
        child = (
            self.output
            / CHILD_DIRECTORY
            / "child-00000001.json"
        )
        changed = load_json(child, require_canonical=True)
        changed["outgoing_state"][0] += 1
        child.write_bytes(canonical_json_bytes(changed))
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "child"
        ):
            verify_campaign(self.output)

        self.output = self.root / "omitted-campaign"
        self.initialize()
        run_campaign(self.output, workers=3)
        finalize_campaign(self.output)
        (
            self.output
            / RECEIPT_DIRECTORY
            / "receipt-00000001.json"
        ).unlink()
        with self.assertRaisesRegex(
            PsiAffineCampaignError, "before receipt completion"
        ):
            verify_campaign(self.output)

    def test_cli_dispatches_bounded_campaign(self) -> None:
        self.initialize()
        command = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "command",
                str(self.output),
                "0",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(
            json.loads(command.stdout)["argv"],
            list(command_for_shard(self.output, 0)),
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "run",
                str(self.output),
                "--workers",
                "3",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout)["receipts"], 3)


if __name__ == "__main__":
    unittest.main()
