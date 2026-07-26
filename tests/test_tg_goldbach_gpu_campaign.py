#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused tests for the fixed hardened GoldbachGPU campaign boundary."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import tempfile
import unittest
from unittest.mock import patch

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_gpu_campaign import (
    ANALYTIC_10POW27_ALGORITHM,
    ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
    ANALYTIC_10POW27_EVEN_COUNT,
    ANALYTIC_10POW27_EVEN_LIMIT,
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
    EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256,
    GoldbachGPUCampaignError,
    GoldbachPlan,
    OPTIMIZED_PRODUCTION_ALGORITHM,
    PRODUCTION_EVEN_COUNT,
    PRODUCTION_EVEN_LIMIT,
    PRODUCTION_EVEN_START,
    PRODUCTION_GROUPS,
    PRODUCTION_LEAVES_PER_GROUP,
    PRODUCTION_NODES,
    PRODUCTION_SHARDS,
    aggregate_directory,
    aggregate_receipts,
    load_plan,
    load_receipt,
    make_bounded_sample_plan,
    make_analytic_10pow27_production_plan,
    make_optimized_analytic_10pow27_production_plan,
    make_optimized_production_plan,
    make_production_plan,
    parse_runner_stdout,
    production_group_leaf_indices,
    receipt_paths,
    run_group,
    run_shard,
    validate_aggregate,
    validate_receipt,
    verify_executable,
    write_plan,
)
from tools.tg_goldbach_gpu_binary_checker import (
    BinaryCheckerError,
    verify_request,
)
from tools.tg_goldbach_gpu_campaign import build_parser as build_campaign_parser


FAKE_RUNNER = r'''#!/usr/bin/env python3
import math
import sys

limit = int(sys.argv[1])
options = {}
for argument in sys.argv[2:]:
    name, value = argument.split("=", 1)
    options[name] = value
required = {
    "--start", "--seg-size", "--p-small", "--batch-size", "--gpus", "--primetest"
}
if set(options) != required:
    raise SystemExit(90)
if options["--primetest"] != "mr" or options["--gpus"] != "1":
    raise SystemExit(91)
if options["--seg-size"] != "200000000" or options["--p-small"] != "1000000":
    raise SystemExit(92)
if options["--batch-size"] != "2000000":
    raise SystemExit(93)
start = int(options["--start"])
count = (limit - start) // 2 + 1
p_small = min(1000000, limit)
small = max(math.isqrt(limit) + 1, p_small)
if small % 2 == 0:
    small += 1
print("[Hardware] GPU 0: NVIDIA H100 80GB HBM3 (81559 MB VRAM)")
print(f"Building small primes bitset up to {small}...")
print("Pre-generating CPU primes up to 100000000...")
print("Initialization completed in 12.5 ms.\n")
print("--- Launching Multi-GPU Verifier ---")
print(f"Checking range : [{start}, {limit}]")
print(f"Total numbers  : {count}\n")
print("\n--- Verification Complete ---")
print(f"All even numbers from {start} up to {limit} satisfy Goldbach. ✓")
print("Total computation time : 2.5e+01 seconds")
print("Phase 2 fallbacks      : 0")
'''

FAKE_H100_PROBE = {
    "schema": "nvidia-smi-exact-device-identity-v1",
    "device_selector": 0,
    "name": "NVIDIA H100 80GB HBM3",
    "compute_capability": "9.0",
    "memory_total_mb": 81559,
    "uuid": "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "pci_bus_id": "0000000F:01:00.0",
    "nvidia_smi_sha256": "a" * 64,
}


class GoldbachGPUCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runner = self.root / "fake-goldbach"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.runner.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.runner_sha = hashlib.sha256(self.runner.read_bytes()).hexdigest()
        self.source = self.root / "prepared-source"
        self.receipts = self.root / "receipts"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_word_owner_prefix_lists_exactly_the_primes_through_2039(self) -> None:
        patch_text = (
            Path(__file__).resolve().parents[1]
            / "patches"
            / "goldbach-gpu"
            / "b58b2dea-hardening.patch"
        ).read_text(encoding="utf-8")
        listed = [
            int(value)
            for value in re.findall(
                r"^\+\s+clear_small_prime_from_word<(\d+)>\(word_low, word\);$",
                patch_text,
                re.MULTILINE,
            )
        ]

        def prime(value: int) -> bool:
            return value >= 2 and all(
                value % divisor for divisor in range(2, int(value**0.5) + 1)
            )

        expected = [value for value in range(3, 2040) if prime(value)]
        self.assertEqual(listed, expected)
        self.assertIn("WORD_OWNER_SIEVE_LIMIT = 2039", patch_text)

    def test_production_plan_is_literal_balanced_and_gap_free(self) -> None:
        plan = make_production_plan(executable_sha256=self.runner_sha)
        self.assertTrue(plan.production)
        self.assertEqual(len(plan.shards), 65_536)
        self.assertEqual(len(plan.shards), PRODUCTION_SHARDS)
        self.assertEqual(plan.core_dict()["runner"]["production_nodes"], 8)
        self.assertEqual(PRODUCTION_NODES, 8)
        self.assertEqual(PRODUCTION_GROUPS, 8_192)
        self.assertEqual(PRODUCTION_LEAVES_PER_GROUP, 8)
        self.assertEqual(
            production_group_leaf_indices(plan, 17),
            tuple(17 + 8_192 * offset for offset in range(8)),
        )
        self.assertEqual(
            (plan.even_start, plan.even_limit),
            (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT),
        )
        self.assertEqual(sum(shard.even_count for shard in plan.shards), PRODUCTION_EVEN_COUNT)

    def test_analytic_10pow27_plan_is_a_distinct_exact_production_profile(self) -> None:
        plan = make_analytic_10pow27_production_plan(
            executable_sha256=self.runner_sha
        )
        self.assertTrue(plan.production)
        self.assertEqual(plan.algorithm, ANALYTIC_10POW27_ALGORITHM)
        self.assertEqual((plan.even_start, plan.even_limit), (4, ANALYTIC_10POW27_EVEN_LIMIT))
        self.assertEqual(len(plan.shards), 65_536)
        self.assertEqual(
            sum(shard.even_count for shard in plan.shards),
            ANALYTIC_10POW27_EVEN_COUNT,
        )
        self.assertEqual(
            production_group_leaf_indices(plan, 17),
            tuple(17 + 8_192 * offset for offset in range(8)),
        )
        self.assertLessEqual(
            max(shard.even_count for shard in plan.shards)
            - min(shard.even_count for shard in plan.shards),
            1,
        )
        for left, right in zip(plan.shards, plan.shards[1:], strict=False):
            self.assertEqual(left.rank_upper, right.rank_lower)
            self.assertEqual(left.even_limit + 2, right.even_start)

        plan_path = self.root / "plan.json"
        write_plan(plan_path, plan)
        self.assertEqual(load_plan(plan_path), plan)

    def test_optimized_profiles_bind_the_transformed_source_identity(self) -> None:
        historical = make_optimized_production_plan(
            executable_sha256=self.runner_sha
        )
        lowered = make_optimized_analytic_10pow27_production_plan(
            executable_sha256=self.runner_sha
        )
        self.assertEqual(
            historical.algorithm, OPTIMIZED_PRODUCTION_ALGORITHM
        )
        self.assertEqual(
            lowered.algorithm, ANALYTIC_10POW27_OPTIMIZED_ALGORITHM
        )
        for plan in (historical, lowered):
            self.assertEqual(
                plan.core_dict()["hardened_source_identity_sha256"],
                EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256,
            )
            self.assertEqual(GoldbachPlan.from_dict(plan.to_dict()), plan)
        self.assertEqual(
            (historical.even_start, historical.even_limit),
            (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT),
        )
        self.assertEqual(
            (lowered.even_start, lowered.even_limit),
            (4, ANALYTIC_10POW27_EVEN_LIMIT),
        )
        self.assertNotEqual(historical.plan_sha256, lowered.plan_sha256)

    def test_optimized_plan_cli_requires_a_qualified_candidate_package(self) -> None:
        common = [
            "--source-root",
            str(self.root / "candidate" / "source"),
            "--executable",
            str(self.root / "candidate" / "artifacts" / "goldbach-gpu"),
            "--executable-sha256",
            "a" * 64,
            "--out",
            str(self.root / "plan.json"),
        ]
        for command in (
            "create-optimized-production-plan",
            "create-optimized-analytic-10pow27-plan",
        ):
            with self.subTest(command=command):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        build_campaign_parser().parse_args([command, *common])
                self.assertEqual(raised.exception.code, 2)
                parsed = build_campaign_parser().parse_args(
                    [
                        command,
                        *common,
                        "--candidate-package-root",
                        str(self.root / "candidate"),
                        "--candidate-manifest-file-sha256",
                        "b" * 64,
                    ]
                )
                self.assertEqual(
                    parsed.candidate_package_root,
                    self.root / "candidate",
                )
                self.assertEqual(
                    parsed.candidate_manifest_file_sha256,
                    "b" * 64,
                )

    def test_run_group_resumes_only_after_receipt_validation(self) -> None:
        plan = make_production_plan(executable_sha256=self.runner_sha)

        def probe(device: int):
            return dict(FAKE_H100_PROBE, device_selector=device)

        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ), patch(
            "tg_verifier.goldbach_gpu_campaign.collect_production_gpu_identity",
            side_effect=probe,
        ):
            first = run_group(
                plan=plan,
                group_index=0,
                executable=self.runner,
                source_root=self.source,
                output_directory=self.receipts,
            )
            replay = run_group(
                plan=plan,
                group_index=0,
                executable=self.runner,
                source_root=self.source,
                output_directory=self.receipts,
            )
        self.assertEqual(first["leaf_indices"], list(range(0, 65_536, 8_192)))
        self.assertTrue(
            all(
                row["status"] == "completed-new-receipt"
                for row in first["receipts"]
            )
        )
        self.assertTrue(
            all(
                row["status"] == "validated-existing-receipt"
                for row in replay["receipts"]
            )
        )
        changed = json.loads(
            (self.receipts / "receipt-00000000.json").read_text(encoding="utf-8")
        )
        changed["receipt_sha256"] = "0" * 64
        (self.receipts / "receipt-00000000.json").write_bytes(
            canonical_json_bytes(changed)
        )
        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ):
            with self.assertRaisesRegex(GoldbachGPUCampaignError, "receipt SHA"):
                run_group(
                    plan=plan,
                    group_index=0,
                    executable=self.runner,
                    source_root=self.source,
                    output_directory=self.receipts,
                )

    def test_bounded_sample_cannot_masquerade_as_production(self) -> None:
        sample = make_bounded_sample_plan(
            even_start=4,
            even_limit=1_000_002,
            shard_count=2,
            executable_sha256=self.runner_sha,
        )
        self.assertFalse(sample.production)
        self.assertEqual(sample.classification, "bounded-sample-not-production")
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "production plan"):
            make_bounded_sample_plan(
                even_start=PRODUCTION_EVEN_START,
                even_limit=PRODUCTION_EVEN_LIMIT,
                shard_count=8,
                executable_sha256=self.runner_sha,
            )

    def test_plan_rejects_gap_overlap_duplicate_and_tamper(self) -> None:
        plan = make_production_plan(executable_sha256=self.runner_sha)
        for mutation in ("gap", "overlap", "duplicate", "hash"):
            value = json.loads(json.dumps(plan.to_dict()))
            if mutation == "gap":
                value["shards"][1]["rank_lower"] += 1
            elif mutation == "overlap":
                value["shards"][1]["even_start"] -= 2
            elif mutation == "duplicate":
                value["shards"][1] = dict(value["shards"][0])
            else:
                value["plan_sha256"] = "f" * 64
            with self.subTest(mutation=mutation):
                with self.assertRaises(GoldbachGPUCampaignError):
                    GoldbachPlan.from_dict(value)

    def _valid_stdout(self, plan, index: int = 0) -> bytes:
        shard = plan.shards[index]
        import subprocess

        return subprocess.run(
            [str(self.runner), str(shard.even_limit),
             f"--start={shard.even_start}", "--seg-size=200000000",
             "--p-small=1000000", "--batch-size=2000000", "--gpus=1",
             "--primetest=mr"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout

    def test_stdout_parser_is_anchored_and_range_bound(self) -> None:
        plan = make_production_plan(executable_sha256=self.runner_sha)
        raw = self._valid_stdout(plan)
        parsed = parse_runner_stdout(raw, plan.shards[0])
        self.assertEqual(parsed["gpu_name"], "NVIDIA H100 80GB HBM3")
        self.assertTrue(parsed["all_even_numbers_reported_satisfied"])
        for changed in (
            raw + b"unexpected\n",
            raw.replace(b"--never-present--", b"x"),
            raw.replace(
                str(plan.shards[0].even_start).encode(),
                str(plan.shards[0].even_start + 2).encode(),
                1,
            ),
        ):
            if changed == raw:
                continue
            with self.assertRaises(GoldbachGPUCampaignError):
                parse_runner_stdout(changed, plan.shards[0])

    def test_reduced_leaf_protocol_aggregate_does_not_overstate_trust(self) -> None:
        # Exercise the full receipt/Merkle protocol with a reduced leaf count;
        # the preceding test constructs and round-trips the literal 65,536-leaf
        # production plan.
        production_shards_patch = patch(
            "tg_verifier.goldbach_gpu_campaign.PRODUCTION_SHARDS", 8
        )
        production_shards_patch.start()
        self.addCleanup(production_shards_patch.stop)
        plan = make_production_plan(executable_sha256=self.runner_sha)
        def probe(device: int):
            return dict(FAKE_H100_PROBE, device_selector=device)

        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ), patch(
            "tg_verifier.goldbach_gpu_campaign.collect_production_gpu_identity",
            side_effect=probe,
        ):
            generated = [
                run_shard(
                    plan=plan,
                    shard_index=index,
                    executable=self.runner,
                    source_root=self.source,
                    output_directory=self.receipts,
                    cuda_visible_device=index,
                )
                for index in range(len(plan.shards))
            ]
        self.assertIn("--primetest=mr", generated[0]["runner_arguments"])
        self.assertFalse(generated[0]["execution_attested"])
        self.assertFalse(generated[0]["lean_atom_discharged"])
        plan_path = self.root / "plan.json"
        aggregate_path = self.root / "aggregate.json"
        write_plan(plan_path, plan)
        aggregate = aggregate_directory(
            plan=plan,
            output_directory=self.receipts,
            aggregate_path=aggregate_path,
        )
        self.assertTrue(aggregate["production_campaign_complete"])
        self.assertTrue(aggregate["coverage_structurally_complete"])
        self.assertFalse(aggregate["execution_attested"])
        self.assertFalse(aggregate["lean_atom_discharged"])
        self.assertRegex(aggregate["receipt_merkle_root_sha256"], r"^[0-9a-f]{64}$")

        request_path = self.root / "request.json"
        request_path.write_bytes(
            canonical_json_bytes(
                {
                    "artifact_sha256": hashlib.sha256(
                        aggregate_path.read_bytes()
                    ).hexdigest(),
                    "every_even": True,
                    "first_even": str(PRODUCTION_EVEN_START),
                    "kind": "tg_binary_goldbach_request_v1",
                    "last_even": str(PRODUCTION_EVEN_LIMIT),
                }
            )
        )
        adapted = verify_request(request_path, aggregate_path)
        self.assertTrue(adapted["verified"])
        self.assertEqual(adapted["kind"], "tg_binary_goldbach_result_v1")
        loaded = [load_receipt(path, plan=plan) for path in receipt_paths(self.receipts)]
        self.assertEqual(aggregate_receipts(plan=plan, receipts=list(reversed(loaded))), aggregate)
        self.assertEqual(validate_aggregate(aggregate, plan=plan, receipts=loaded), aggregate)

        # A lowered-domain production plan must never satisfy the historical
        # [4,4e18] request merely because both plans say production=true.
        wrong_root = self.root / "wrong-domain"
        wrong_root.mkdir()
        wrong_aggregate = wrong_root / "aggregate.json"
        wrong_aggregate.write_bytes(b"{}\n")
        write_plan(
            wrong_root / "plan.json",
            make_analytic_10pow27_production_plan(
                executable_sha256=self.runner_sha
            ),
        )
        wrong_request = wrong_root / "request.json"
        wrong_request.write_bytes(
            canonical_json_bytes(
                {
                    "artifact_sha256": hashlib.sha256(
                        wrong_aggregate.read_bytes()
                    ).hexdigest(),
                    "every_even": True,
                    "first_even": str(PRODUCTION_EVEN_START),
                    "kind": "tg_binary_goldbach_request_v1",
                    "last_even": str(PRODUCTION_EVEN_LIMIT),
                }
            )
        )
        with self.assertRaisesRegex(
            BinaryCheckerError, "historical-domain"
        ):
            verify_request(wrong_request, wrong_aggregate)

        with self.assertRaisesRegex(GoldbachGPUCampaignError, "incomplete"):
            aggregate_receipts(plan=plan, receipts=loaded[:-1])
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "duplicate"):
            aggregate_receipts(plan=plan, receipts=loaded[:-1] + [loaded[0]])
        changed = json.loads(json.dumps(loaded[0]))
        changed["execution_attested"] = True
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "unsafe"):
            validate_receipt(changed, plan=plan)

        non_h100 = json.loads(json.dumps(loaded[0]))
        old_stdout = non_h100["stdout_utf8"]
        new_stdout = old_stdout.replace(
            "NVIDIA H100 80GB HBM3 (81559 MB VRAM)",
            "NVIDIA GB10 (122566 MB VRAM)",
        )
        non_h100["stdout_utf8"] = new_stdout
        non_h100["stdout_sha256"] = hashlib.sha256(new_stdout.encode()).hexdigest()
        # Deliberately leave the parsed output and receipt commitments stale:
        # validation must fail at the production hardware check first.
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "NVIDIA H100"):
            validate_receipt(non_h100, plan=plan)

        wrong_capability = json.loads(json.dumps(loaded[0]))
        wrong_capability["production_gpu_probe"]["compute_capability"] = "12.1"
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "exactly 9.0"):
            validate_receipt(wrong_capability, plan=plan)

    def test_receipt_is_immutable_and_executable_hash_is_enforced(self) -> None:
        plan = make_bounded_sample_plan(
            even_start=4,
            even_limit=1_000_002,
            shard_count=1,
            executable_sha256=self.runner_sha,
        )
        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ):
            first = run_shard(
                plan=plan,
                shard_index=0,
                executable=self.runner,
                source_root=self.source,
                output_directory=self.receipts,
            )
            second = run_shard(
                plan=plan,
                shard_index=0,
                executable=self.runner,
                source_root=self.source,
                output_directory=self.receipts,
            )
        self.assertEqual(first, second)

        path = self.receipts / "receipt-00000000.json"
        changed = dict(first)
        changed["stdout_sha256"] = "0" * 64
        path.write_bytes(canonical_json_bytes(changed))
        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ):
            with self.assertRaisesRegex(GoldbachGPUCampaignError, "immutable"):
                run_shard(
                    plan=plan,
                    shard_index=0,
                    executable=self.runner,
                    source_root=self.source,
                    output_directory=self.receipts,
                )

        self.runner.write_text(FAKE_RUNNER + "\n# tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(GoldbachGPUCampaignError, "hash differs"):
            verify_executable(self.runner, self.runner_sha)

    def test_launch_uses_the_hash_checked_inode_after_path_replacement(self) -> None:
        import subprocess

        plan = make_bounded_sample_plan(
            even_start=4,
            even_limit=1_000_002,
            shard_count=1,
            executable_sha256=self.runner_sha,
        )
        real_run = subprocess.run
        observed: list[str] = []

        def replace_path_then_run(argv, **kwargs):
            observed.append(argv[0])
            self.assertRegex(argv[0], r"^/proc/self/fd/[0-9]+$")
            self.assertEqual(Path(argv[0]).read_bytes(), FAKE_RUNNER.encode())
            self.runner.unlink()
            self.runner.write_text(
                "#!/usr/bin/env python3\nraise SystemExit(99)\n",
                encoding="utf-8",
            )
            self.runner.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            return real_run(argv, **kwargs)

        with patch(
            "tg_verifier.goldbach_gpu_campaign.verify_hardened_source_tree",
            return_value=EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
        ), patch(
            "tg_verifier.goldbach_gpu_campaign.subprocess.run",
            side_effect=replace_path_then_run,
        ):
            receipt = run_shard(
                plan=plan,
                shard_index=0,
                executable=self.runner,
                source_root=self.source,
                output_directory=self.receipts,
            )
        self.assertEqual(len(observed), 1)
        self.assertTrue(receipt["parsed_output"]["all_even_numbers_reported_satisfied"])


if __name__ == "__main__":
    unittest.main()
