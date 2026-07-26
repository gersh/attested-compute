#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the bounded Hurst cross-mode qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.hurst_affine_equivalence import (
    HurstAffineEquivalenceError,
    run_qualification,
    verify_qualification,
)
from tg_verifier.hurst_residual_campaign import UPSTREAM_COMMIT


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--segment-size", type=int, required=True)
p.add_argument("--mode", choices=("summary", "verify", "affine"), required=True)
p.add_argument("--incoming-mertens", type=int)
p.add_argument("--incoming-squarefree", type=int)
p.add_argument("--incoming-little-lower", type=int)
p.add_argument("--incoming-little-upper", type=int)
a = p.parse_args()

upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
delta = [count % 7 - 3, count, -2 * count, 3 * count]
incoming = [
    a.incoming_mertens,
    a.incoming_squarefree,
    a.incoming_little_lower,
    a.incoming_little_upper,
]
if a.mode == "verify" and any(value is None for value in incoming):
    raise SystemExit("verify requires an incoming state")
if a.mode != "verify" and any(value is not None for value in incoming):
    raise SystemExit("non-verify mode received an incoming state")

wide_lower = [
    -4000000000000000000,
    -4000000000000000000,
    -(1 << 120),
    -(1 << 120),
]
wide_upper = [
    4000000000000000000,
    4000000000000000000,
    1 << 120,
    1 << 120,
]

def affine_guard(components):
    return {
        "lower": list(wide_lower),
        "upper": list(wide_upper),
        "witnesses": [
            {
                "component": component,
                "lower_n": 0,
                "lower_side": "none",
                "upper_n": 0,
                "upper_side": "none",
            }
            for component in components
        ],
    }

def singleton_guard():
    return {"lower": list(incoming), "upper": list(incoming), "witnesses": []}

if a.mode == "affine":
    guards = {
        "mertens-hurst": affine_guard([0]),
        "cdem-squarefree": affine_guard([1]),
        "platt-little-mertens-2-11": affine_guard([2, 3]),
        "platt-little-mertens-stronger": affine_guard([2, 3]),
    }
elif a.mode == "verify":
    guards = {
        atom: singleton_guard()
        for atom in (
            "mertens-hurst",
            "cdem-squarefree",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        )
    }
else:
    guards = {}

elapsed = {"summary": 2.0, "verify": 3.0, "affine": 2.857142857}[a.mode]
print(json.dumps({
    "algorithm": "hurst-segmented-mobius-two-pass-v2",
    "mode": a.mode,
    "classification": "source-scale-shard-not-lean-proof",
    "upstream_commit": "fb47790c876c92690fce62990199ce961c5bdd72",
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "work_count": count,
    "segment_size": a.segment_size,
    "segments": (count + a.segment_size - 1) // a.segment_size,
    "row_encoding": "mu-plus-one-block-sha256-v1",
    "squarefree_threshold_endpoint_policy":
        "inclusive-value-and-right-limit-v2",
    "reduction_block_rows": 1048576,
    "row_sha256": hashlib.sha256(
        f"bounded-row-v1:{a.lower}:{upper_exclusive}".encode("ascii")
    ).hexdigest(),
    "state_components": ["M", "Q", "lm_lower_q96", "lm_upper_q96"],
    "delta": delta,
    "guards": guards,
    "exact_fallbacks": {
        "mertens_hurst": 0,
        "squarefree": 0,
        "little_mertens_2_11": 0,
        "little_mertens_stronger": 0,
    },
    "accepted": True,
    "elapsed_seconds": elapsed,
    "execution_attested": False,
    "lean_atom_discharged": False,
}, sort_keys=True, separators=(",", ":")))
'''


class HurstAffineEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        )
        self.source = self.root / "source.cpp"
        self.source.write_text("// bounded fake source\n", encoding="utf-8")
        self.upstream = self.root / "upstream.json"
        self.upstream.write_bytes(
            canonical_json_bytes(
                {
                    "kind": "sparkinterval.pinned_upstream_source.v1",
                    "name": "bounded fake closure",
                    "repository": "https://example.invalid/upstream",
                    "commit": UPSTREAM_COMMIT,
                    "license": "MIT",
                    "files": [
                        {
                            "path": "sieve/SegmentedMobiusSieve.h",
                            "sha256": "1" * 64,
                            "size_bytes": 1,
                        }
                    ],
                }
            )
        )
        self.artifact = self.root / "qualification.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def qualify(self) -> dict:
        return run_qualification(
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            output=self.artifact,
            domain_lower=1,
            domain_upper_exclusive=41_581,
            shard_span=13_860,
            segment_size=13_860,
            repeat_count=3,
            runner_threads=1,
        )

    def replay(self) -> dict:
        return verify_qualification(
            self.artifact,
            runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
        )

    def rewrite(self, value: dict) -> None:
        self.artifact.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.artifact.write_bytes(canonical_json_bytes(value))

    def test_exact_chain_output_and_timing_equivalence(self) -> None:
        artifact = self.qualify()
        self.assertEqual(self.replay(), artifact)
        self.assertEqual(artifact["configuration"]["shard_count"], 3)
        self.assertEqual(artifact["chain"]["root_state"], [0, 0, 0, 0])
        self.assertEqual(
            artifact["timing"]["runner_elapsed_two_pass_over_affine"],
            "1.750000000087500000004375000",
        )
        self.assertTrue(
            artifact["timing"][
                "representative_one_pass_faster_by_runner_elapsed"
            ]
        )
        self.assertFalse(artifact["capabilities"]["full_source_range"])
        self.assertFalse(
            artifact["capabilities"]["primitive_mobius_realization_proved"]
        )
        self.assertFalse(artifact["capabilities"]["execution_attested"])
        self.assertFalse(artifact["capabilities"]["lean_atom_discharged"])

    def test_readable_receipt_mutation_fails_closed(self) -> None:
        self.qualify()
        value = json.loads(self.artifact.read_bytes())
        value["runs"][0]["affine"][0]["report"]["delta"][0] += 1
        self.rewrite(value)
        with self.assertRaisesRegex(
            HurstAffineEquivalenceError, "readable report differs"
        ):
            self.replay()

    def test_self_consistent_cross_mode_mutation_fails_closed(self) -> None:
        self.qualify()
        value = json.loads(self.artifact.read_bytes())
        record = value["runs"][0]["affine"][0]
        raw_report = json.loads(bytes.fromhex(record["receipt_hex"]))
        raw_report["row_sha256"] = "f" * 64
        raw = (
            json.dumps(raw_report, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        record["receipt_hex"] = raw.hex()
        record["receipt_size_bytes"] = len(raw)
        record["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
        record["report"] = raw_report
        record["report"]["elapsed_seconds"] = "2.857142857"
        self.rewrite(value)
        with self.assertRaisesRegex(
            HurstAffineEquivalenceError,
            "mode-independent output differs",
        ):
            self.replay()

    def test_omission_and_order_mutations_fail_closed(self) -> None:
        self.qualify()
        original = json.loads(self.artifact.read_bytes())

        omitted = json.loads(json.dumps(original))
        omitted["runs"][1]["summary"].pop()
        self.rewrite(omitted)
        with self.assertRaisesRegex(
            HurstAffineEquivalenceError, "summary records are incomplete"
        ):
            self.replay()

        reordered = json.loads(json.dumps(original))
        reordered["runs"][0]["verify"][0], reordered["runs"][0]["verify"][1] = (
            reordered["runs"][0]["verify"][1],
            reordered["runs"][0]["verify"][0],
        )
        self.rewrite(reordered)
        with self.assertRaisesRegex(
            HurstAffineEquivalenceError, "record order/range changed"
        ):
            self.replay()

    def test_positive_trust_boundary_mutation_fails_closed(self) -> None:
        self.qualify()
        value = json.loads(self.artifact.read_bytes())
        value["capabilities"]["execution_attested"] = True
        self.rewrite(value)
        with self.assertRaisesRegex(
            HurstAffineEquivalenceError, "capability boundary changed"
        ):
            self.replay()


if __name__ == "__main__":
    unittest.main()
