# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed artifact tests for the bounded CH25 psi qualification."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tg_verifier.campaign_io import canonical_json_bytes, sha256_bytes
from tg_verifier.evidence import load_decimal_json_bytes
from tg_verifier.psi_residual_campaign import CRLIBM_COMMIT, PRIMESIEVE_COMMIT
from tg_verifier import psi_two_pass_qualification as qualification


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
delta = [100 * count, 101 * count]
event_sha = hashlib.sha256(
    f"fake-psi-events-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
row_sha = hashlib.sha256(
    f"fake-psi-rows-v1:{a.lower}:{upper_exclusive}".encode("ascii")
).hexdigest()
incoming = [a.incoming_lower, a.incoming_upper]
outgoing = [incoming[0] + delta[0], incoming[1] + delta[1]]
verify = a.mode == "verify"
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
    "prime_power_events": count,
    "prime_events": count,
    "higher_power_events": 0,
    "state_components": ["psi_lower_q64", "psi_upper_q64"],
    "delta": delta,
    "guards": ({
        "ch25-psi-1e13": {
            "lower_guard": incoming,
            "upper_guard": incoming,
            "witnesses": [],
        }
    } if verify else {}),
    "incoming_state": incoming if verify else None,
    "outgoing_state": outgoing if verify else None,
    "exact_fallbacks": {
        "lower_left_limit": 0,
        "upper_post_jump": 0,
        "terminal_lower": 0,
    },
    "terminal_strict_lower_checked": (
        verify and upper_exclusive == 10_000_000_000_001
    ),
    "accepted": True,
    "elapsed_seconds": 0.001,
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


def fake_literal_oracle(
    *,
    crlibm_shared: Path,
    ranges: tuple[tuple[int, int], ...],
    series_terms: int,
    segment_size: int,
) -> dict[str, object]:
    del crlibm_shared, series_terms, segment_size
    current = (0, 0)
    entries: list[dict[str, object]] = []
    total = 0
    for index, (lower, upper) in enumerate(ranges):
        count = upper - lower
        incoming = current
        delta = (100 * count, 101 * count)
        current = (current[0] + delta[0], current[1] + delta[1])
        entries.append(
            {
                "index": index,
                "lower": lower,
                "upper_exclusive": upper,
                "prime_power_events": count,
                "prime_events": count,
                "higher_power_events": 0,
                "event_sha256": hashlib.sha256(
                    f"fake-psi-events-v1:{lower}:{upper}".encode("ascii")
                ).hexdigest(),
                "row_sha256": hashlib.sha256(
                    f"fake-psi-rows-v1:{lower}:{upper}".encode("ascii")
                ).hexdigest(),
                "delta": list(delta),
                "incoming": list(incoming),
                "outgoing": list(current),
                "exact_fallbacks": {
                    "lower_left_limit": 0,
                    "upper_post_jump": 0,
                    "terminal_lower": 0,
                },
                "all_gap_guards_accept": True,
            }
        )
        total += count
    timing = {
        "prime_power_enumeration_seconds_decimal": "0",
        "directed_log_refinement_seconds_decimal": "0",
        "commitment_gap_fold_seconds_decimal": "0",
        "total_seconds_decimal": "0",
        "scope": (
            "bounded_python_roster_rational_log_and_loaded_crlibm_oracle_timing"
        ),
    }
    return {
        "semantics": {
            "prime_power_events": total,
            "prime_events": total,
            "higher_power_events": 0,
            "unique_primes": total,
            "rational_log_pairs_enclosed": total,
            "root_state": [0, 0],
            "entries": entries,
            "final_state": list(current),
        },
        "timing": timing,
    }


class PsiTwoPassQualificationAttackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.runner = cls.root / "fake-runner.py"
        cls.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        cls.runner.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        cls.source = cls.root / "worker.cpp"
        cls.source.write_text("// qualification fixture\n", encoding="utf-8")
        cls.upstream = cls.root / "PSI_UPSTREAMS.json"
        cls.upstream.write_bytes(canonical_json_bytes(upstream_manifest()))
        cls.crlibm = cls.root / "libcrlibm-fixture.so"
        cls.crlibm.write_bytes(b"not loaded because the literal oracle is patched")
        cls.artifact_path = cls.root / "qualification.json"
        with mock.patch.object(
            qualification, "_literal_oracle", fake_literal_oracle
        ):
            cls.artifact = qualification.run_qualification(
                candidate_runner=cls.runner,
                baseline_runner=cls.runner,
                runner_source=cls.source,
                upstream_manifest=cls.upstream,
                crlibm_shared=cls.crlibm,
                output=cls.artifact_path,
                domain_upper_exclusive=14,
                shard_span=4,
                sieve_size_kib=64,
                series_terms=3,
                oracle_segment_size=11,
                repeat_count=2,
                performance_lower=100,
                performance_upper_exclusive=120,
                performance_repeat_count=2,
                timeout_seconds=10,
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def verify_changed(self, value: dict[str, object]) -> None:
        path = self.root / f"changed-{self.id().rsplit('.', 1)[-1]}.json"
        path.write_bytes(canonical_json_bytes(value))
        qualification.verify_qualification(
            path,
            candidate_runner=self.runner,
            baseline_runner=self.runner,
            runner_source=self.source,
            upstream_manifest=self.upstream,
            crlibm_shared=self.crlibm,
            regenerate_oracle=False,
        )

    @staticmethod
    def rewrite_record(record: dict[str, object], **changes: object) -> None:
        raw = bytes.fromhex(record["receipt_hex"])  # type: ignore[arg-type]
        report = load_decimal_json_bytes(raw, label="test receipt")
        report.update(changes)
        report["elapsed_seconds"] = float(report["elapsed_seconds"])
        changed = json.dumps(
            report, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        decoded = load_decimal_json_bytes(changed, label="changed test receipt")
        record["receipt_hex"] = changed.hex()
        record["receipt_size_bytes"] = len(changed)
        record["receipt_sha256"] = sha256_bytes(changed)
        record["report"] = qualification._wire_report(decoded)

    def test_unmodified_artifact_replays_without_oracle_regeneration(self) -> None:
        self.verify_changed(deepcopy(self.artifact))

    def test_readable_report_cannot_differ_from_retained_receipt(self) -> None:
        changed = deepcopy(self.artifact)
        record = changed["executions"]["candidate"]["runs"][0]["summary"][0]
        record["report"]["event_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError,
            "readable report differs",
        ):
            self.verify_changed(changed)

    def test_self_consistent_event_commitment_mutation_fails_oracle(self) -> None:
        changed = deepcopy(self.artifact)
        record = changed["executions"]["candidate"]["runs"][0]["summary"][0]
        self.rewrite_record(record, event_sha256="f" * 64)
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError,
            "differs from literal oracle",
        ):
            self.verify_changed(changed)

    def test_self_consistent_row_commitment_mutation_fails_oracle(self) -> None:
        changed = deepcopy(self.artifact)
        record = changed["executions"]["candidate"]["runs"][0]["verify"][0]
        self.rewrite_record(record, row_sha256="f" * 64)
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError,
            "differs from literal oracle",
        ):
            self.verify_changed(changed)

    def test_omitted_record_fails_closed(self) -> None:
        changed = deepcopy(self.artifact)
        changed["executions"]["candidate"]["runs"][0]["summary"].pop()
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError, "incomplete"
        ):
            self.verify_changed(changed)

    def test_reordered_records_fail_closed(self) -> None:
        changed = deepcopy(self.artifact)
        records = changed["executions"]["candidate"]["runs"][0]["verify"]
        records[0], records[1] = records[1], records[0]
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError, "order/range changed"
        ):
            self.verify_changed(changed)

    def test_incoming_chain_mutation_fails_without_fresh_oracle(self) -> None:
        changed = deepcopy(self.artifact)
        changed["oracle"]["semantics"]["entries"][1]["incoming"][0] += 1
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError, "incoming-state chain"
        ):
            self.verify_changed(changed)

    def test_u128_fold_overflow_fails_without_fresh_oracle(self) -> None:
        changed = deepcopy(self.artifact)
        changed["oracle"]["semantics"]["entries"][1]["delta"] = [
            qualification.U128_LIMIT - 1,
            qualification.U128_LIMIT - 1,
        ]
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError, "overflows u128"
        ):
            self.verify_changed(changed)

    def test_capability_escalation_fails_closed(self) -> None:
        changed = deepcopy(self.artifact)
        changed["capabilities"]["receipt_admitted"] = True
        with self.assertRaisesRegex(
            qualification.PsiTwoPassQualificationError, "capability boundary"
        ):
            self.verify_changed(changed)


if __name__ == "__main__":
    unittest.main()
