# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused protocol tests for the deployable two-pass psi campaign."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.psi_residual_campaign import (
    ATOM,
    CRLIBM_COMMIT,
    DEFAULT_SHARD_SPAN,
    PRIMESIEVE_COMMIT,
    REGISTERED_RESULT_SHA256,
    PsiResidualCampaignError,
    SOURCE_UPPER_EXCLUSIVE,
    command_for_shard,
    create_plan,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    reduce_summaries,
    run_phase,
    verify_campaign,
    write_registered_result,
)


CLI = Path(__file__).resolve().parents[1] / "tools" / "tg_psi_residual_campaign.py"


FAKE_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--sieve-size-kib", type=int, required=True)
p.add_argument("--mode", choices=("summary", "verify"), required=True)
p.add_argument("--incoming-lower", type=int, default=0)
p.add_argument("--incoming-upper", type=int, default=0)
a = p.parse_args()
upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
events = count
delta = [100 * count, 101 * count]
event_sha = hashlib.sha256(
    f"fake-psi-events-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
row_sha = hashlib.sha256(
    f"fake-psi-rows-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
incoming = [a.incoming_lower, a.incoming_upper]
outgoing = [incoming[0] + delta[0], incoming[1] + delta[1]]
guards = {}
incoming_report = None
outgoing_report = None
terminal = False
if a.mode == "verify":
    guards = {
        "ch25-psi-1e13": {
            "lower_guard": incoming,
            "upper_guard": incoming,
            "witnesses": [],
        }
    }
    incoming_report = incoming
    outgoing_report = outgoing
    terminal = upper_exclusive == 10_000_000_000_001
print(json.dumps({
    "algorithm": "ch25-psi-prime-power-two-pass-v1",
    "mode": a.mode,
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
    "prime_power_events": events,
    "prime_events": events,
    "higher_power_events": 0,
    "state_components": ["psi_lower_q64", "psi_upper_q64"],
    "delta": delta,
    "guards": guards,
    "incoming_state": incoming_report,
    "outgoing_state": outgoing_report,
    "exact_fallbacks": {
        "lower_left_limit": 0,
        "upper_post_jump": 0,
        "terminal_lower": 0,
    },
    "terminal_strict_lower_checked": terminal,
    "accepted": True,
    "elapsed_seconds": 0,
    "execution_attested": False,
    "lean_atom_discharged": False,
}, sort_keys=True))
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


class PsiResidualCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.source = self.root / "tg_psi_residual_shard.cpp"
        self.source.write_text("// bounded fake psi adapter\n", encoding="utf-8")
        self.upstream = self.root / "PSI_UPSTREAMS.json"
        self.upstream.write_text(
            json.dumps(upstream_manifest(), sort_keys=True) + "\n", encoding="utf-8"
        )
        self.output = self.root / "campaign"

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
        self.assertEqual((result.shard_count, result.mode), (3, "bounded_test"))

    def test_full_plan_has_one_hundred_thousand_checkpoint_leaves(self) -> None:
        plan = create_plan(
            runner_sha256="1" * 64,
            source_sha256="2" * 64,
            upstream_manifest_sha256="3" * 64,
            domain_upper_exclusive=SOURCE_UPPER_EXCLUSIVE,
            shard_span=DEFAULT_SHARD_SPAN,
        )
        self.assertEqual(len(plan.shards), 100_000)
        self.assertEqual(
            (plan.domain_lower, plan.domain_upper),
            (2, 10_000_000_000_001),
        )
        self.assertEqual(plan.shards[0].lower, 2)
        self.assertEqual(plan.shards[-1].upper, 10_000_000_000_001)
        for left, right in zip(plan.shards, plan.shards[1:], strict=False):
            self.assertEqual(left.upper, right.lower)

        with self.assertRaisesRegex(PsiResidualCampaignError, "fixed"):
            create_plan(
                runner_sha256="1" * 64,
                source_sha256="2" * 64,
                upstream_manifest_sha256="3" * 64,
                domain_upper_exclusive=SOURCE_UPPER_EXCLUSIVE,
                shard_span=DEFAULT_SHARD_SPAN * 2,
            )

    def test_bounded_plan_requires_explicit_classification(self) -> None:
        with self.assertRaisesRegex(PsiResidualCampaignError, "explicit"):
            create_plan(
                runner_sha256="1" * 64,
                source_sha256="2" * 64,
                upstream_manifest_sha256="3" * 64,
                domain_upper_exclusive=14,
                shard_span=4,
            )

    def test_upstream_tree_identity_is_not_advisory(self) -> None:
        changed = upstream_manifest()
        changed["components"]["crlibm"]["tree_sha256"] = "f" * 64  # type: ignore[index]
        self.upstream.write_text(
            json.dumps(changed, sort_keys=True) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(PsiResidualCampaignError, "source closure"):
            self.initialize()

    def test_parallel_two_pass_builds_affine_merkle_certificate(self) -> None:
        self.initialize()
        summary = run_phase(self.output, phase="summary", workers=3)
        self.assertEqual(summary.summaries, 3)
        derived = reduce_summaries(self.output)
        self.assertEqual(derived["root_state"], [0, 0])
        self.assertEqual(
            derived["entries"][1]["incoming"], derived["entries"][0]["outgoing"]
        )
        self.assertFalse(derived["source_event_count_matches"])
        command = command_for_shard(self.output, phase="verify", shard_index=1)
        self.assertIn("--incoming-lower", command)
        verification = run_phase(self.output, phase="verify", workers=3)
        self.assertEqual(verification.verifications, 3)
        final = finalize_campaign(self.output)
        self.assertTrue(final.complete)
        self.assertFalse(final.full_source_range)
        self.assertFalse(final.source_atom_replayed)
        self.assertIsNotNone(final.certificate_root_sha256)
        self.assertEqual(
            len(list((self.output / "affine-leaves").glob("leaf-*.json"))), 3
        )
        certificate = load_json(self.output / "certificate.json", require_canonical=True)
        self.assertEqual(certificate["atom"], ATOM)
        self.assertFalse(certificate["full_source_range"])
        self.assertFalse(certificate["lean_atom_discharged"])
        self.assertEqual(verify_campaign(self.output), final)

    def test_bounded_campaign_cannot_emit_registered_success(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary", workers=3)
        reduce_summaries(self.output)
        run_phase(self.output, phase="verify", workers=3)
        finalize_campaign(self.output)
        registered = self.root / "registered-result.txt"
        with self.assertRaisesRegex(PsiResidualCampaignError, "full-source"):
            write_registered_result(self.output, registered)
        self.assertFalse(registered.exists())

    def test_registered_result_constants_are_literal_true(self) -> None:
        self.assertEqual(
            REGISTERED_RESULT_SHA256,
            hashlib.sha256(b"true").hexdigest(),
        )

    def test_cluster_command_and_ingest_cli(self) -> None:
        self.initialize()
        command_report = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "command",
                str(self.output),
                "summary",
                "0",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        argv = json.loads(command_report.stdout)["argv"]
        receipt = self.root / "cluster-summary.json"
        receipt.write_bytes(
            subprocess.run(argv, check=True, stdout=subprocess.PIPE).stdout
        )
        ingested = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "ingest",
                str(self.output),
                "summary",
                "0",
                str(receipt),
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(json.loads(ingested.stdout)["summaries"], 1)

    def test_worker_groups_partition_leaves_without_changing_receipts(self) -> None:
        self.initialize()
        self.assertEqual(
            grouped_shard_indices(self.output, group_index=0, group_count=2),
            (0, 2),
        )
        self.assertEqual(
            grouped_shard_indices(self.output, group_index=1, group_count=2),
            (1,),
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "run",
                str(self.output),
                "summary",
                "--worker-group-index",
                "0",
                "--worker-group-count",
                "2",
                "--workers",
                "2",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout)["summaries"], 2)
        self.assertEqual(
            sorted(path.name for path in (self.output / "summary").glob("*.json")),
            ["receipt-00000000.json", "receipt-00000002.json"],
        )

    def test_reducer_and_finalizer_reject_incomplete_phases(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary", max_shards=2, workers=2)
        with self.assertRaisesRegex(PsiResidualCampaignError, "incomplete"):
            reduce_summaries(self.output)
        run_phase(self.output, phase="summary", workers=2)
        reduce_summaries(self.output)
        run_phase(self.output, phase="verify", max_shards=2, workers=2)
        with self.assertRaisesRegex(PsiResidualCampaignError, "incomplete"):
            finalize_campaign(self.output)

    def test_verify_event_commitment_must_match_summary(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary", workers=3)
        reduce_summaries(self.output)
        raw = subprocess.run(
            command_for_shard(self.output, phase="verify", shard_index=0),
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        report = json.loads(raw)
        report["event_sha256"] = "f" * 64
        changed = self.root / "changed.json"
        changed.write_bytes(canonical_json_bytes(report))
        with self.assertRaisesRegex(PsiResidualCampaignError, "event SHA"):
            ingest_receipt(
                self.output,
                phase="verify",
                shard_index=0,
                receipt_path=changed,
            )

    def test_root_derived_guard_cannot_be_substituted(self) -> None:
        self.initialize()
        run_phase(self.output, phase="summary", workers=3)
        reduce_summaries(self.output)
        raw = subprocess.run(
            command_for_shard(self.output, phase="verify", shard_index=1),
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        report = json.loads(raw)
        report["guards"][ATOM]["lower_guard"][0] += 1
        changed = self.root / "wrong-guard.json"
        changed.write_bytes(canonical_json_bytes(report))
        with self.assertRaisesRegex(PsiResidualCampaignError, "root-derived"):
            ingest_receipt(
                self.output,
                phase="verify",
                shard_index=1,
                receipt_path=changed,
            )

    def test_captured_source_is_rechecked(self) -> None:
        self.initialize()
        captured = self.output / "captured-tg-psi-residual-shard.cpp"
        captured.write_text("// tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(PsiResidualCampaignError, "identity changed"):
            verify_campaign(self.output)


if __name__ == "__main__":
    unittest.main()
