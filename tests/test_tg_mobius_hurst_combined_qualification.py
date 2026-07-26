#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools.qualify_tg_mobius_hurst_combined import (
    AFFINE_ROWS_PER_BLOCK,
    AFFINE_ROWS_PER_THREAD,
    CANDIDATE_ALGORITHM,
    CANDIDATE_LEAF_DOMAIN,
    CLASSIFICATION,
    EVENTS_PER_BLOCK,
    LEAF_SEMANTIC_FIELDS,
    MINIMUM_CROSSOVER_ROWS,
    NONROOT_DIGEST,
    PRODUCTION_ALGORITHM,
    PRODUCTION_LEAF_DOMAIN,
    QualificationError,
    RESOURCE_ROLE_PATTERNS,
    ROOT,
    SCHEMA,
    SOURCE_FILES,
    SOURCE_LIMIT,
    SOURCE_ROSTER_SHA256,
    TERMINAL_SEMANTIC_FIELDS,
    _digest,
    _multiple_count,
    _parse_resource_usage,
    _summary_count,
    validate_report,
)


SHA = "2" * 64


def resource(registers: int, stack: int, shared: int) -> dict[str, int]:
    return {
        "registers_per_thread": registers,
        "stack_bytes_per_thread": stack,
        "shared_bytes_per_block": shared,
        "local_bytes_per_thread": 0,
        "constant0_bytes": 560,
    }


def fixture(mode: str = "bounded") -> dict[str, object]:
    h100 = mode == "azure-h100-benchmark"
    repetitions = 5 if h100 else 3
    schedule = []
    for pair in range(repetitions):
        schedule.extend(
            ("current", "candidate")
            if pair % 2 == 0
            else ("candidate", "current")
        )
    count = 100_000_000 if h100 else MINIMUM_CROSSOVER_ROWS
    lower = SOURCE_LIMIT - count + 1
    runtime_sha = SHA if h100 else "3" * 64
    source_files = [
        {"path": path, "sha256": SHA} for path in SOURCE_FILES
    ]
    metadata = [
        {"path": "CMakeCache.txt", "sha256": SHA},
        {"path": "build.ninja", "sha256": SHA},
    ]

    def build(target: str, architecture: str, digest: str) -> dict[str, object]:
        return {
            "target": target,
            "cmake_build_type": "Release",
            "cmake_cuda_architectures": architecture,
            "affine_rows_per_thread": AFFINE_ROWS_PER_THREAD,
            "cmake_cache_sha256": SHA,
            "metadata": copy.deepcopy(metadata),
            "metadata_manifest_sha256": _digest(metadata),
            "elf_build_id": "abcdef",
            "executable_sha256": digest,
        }

    def timing(milliseconds: str) -> dict[str, object]:
        result: dict[str, object] = {}
        for name in ("kernel", "affine", "device_work", "process", "wall"):
            result[f"{name}_ms"] = [milliseconds] * repetitions
            result[f"{name}_median_ms"] = milliseconds
        return result

    resources = {
        family: {
            role: resource(32, 0, 1_024)
            for role in roles
        }
        for family, roles in RESOURCE_ROLE_PATTERNS.items()
    }
    return {
        "schema": SCHEMA,
        "accepted": True,
        "classification": CLASSIFICATION,
        "mode": mode,
        "workload": {
            "lower": lower,
            "upper_exclusive": lower + count,
            "count": count,
            "shard_rows": count,
            "super_shard_rows": count,
            "incoming_mertens": 0,
            "incoming_squarefree": 0,
            "previous_leaf_sha256": NONROOT_DIGEST,
            "prime_roster_sha256": SOURCE_ROSTER_SHA256,
            "affine_summary_count": _summary_count(count),
            "crosses_256_summary_boundary": True,
            "p13_multiple_count": _multiple_count(lower, count, 13),
            "p13_second_event_block_exercised": True,
            "events_per_block": EVENTS_PER_BLOCK,
        },
        "identities": {
            "source_manifest_sha256": _digest(source_files),
            "source_files": source_files,
            "runtime_original_sha256": runtime_sha,
            "execution_image_sha256": runtime_sha,
            "strict_h100_executable_sha256": SHA,
            "same_execution_image_both_variants": True,
            "runtime_matches_strict_h100_executable": h100,
            "current_algorithm": PRODUCTION_ALGORITHM,
            "production_leaf_domain": PRODUCTION_LEAF_DOMAIN,
            "candidate_algorithm": CANDIDATE_ALGORITHM,
            "candidate_leaf_domain": CANDIDATE_LEAF_DOMAIN,
        },
        "build_evidence": {
            "strict_build_invoked": True,
            "runtime_build_invoked": True,
            "strict": build(
                "sparkinterval-h100-tg-mobius-persistent", "90", SHA
            ),
            "runtime": build(
                (
                    "sparkinterval-h100-tg-mobius-persistent"
                    if h100
                    else "sparkinterval-tg-mobius-persistent"
                ),
                "90" if h100 else "121",
                runtime_sha,
            ),
            "tools": {
                "cuobjdump": {
                    "sha256": SHA,
                    "version_sha256": SHA,
                },
                "nvcc": {
                    "sha256": SHA,
                    "version_sha256": SHA,
                },
            },
        },
        "cuda_resources": {
            "strict_sm90_cubin_only": True,
            "strict_resource_usage_sha256": SHA,
            "strict_cubin_names_sha256": SHA,
            **resources,
            "gate": {
                "accepted": True,
                "maximum_registers_per_thread": 64,
                "maximum_stack_bytes_per_thread": 64,
                "maximum_shared_bytes_per_block": 227_328,
                "required_local_bytes_per_thread": 0,
            },
            "resource_gate_passed": True,
        },
        "allocation": {
            "current": {
                "persistent_total": 1_000,
                "fused_support": 100,
                "prefix": 800,
                "workspace": 100,
                "block_summaries": 0,
            },
            "candidate": {
                "persistent_total": 200,
                "fused_support": 100,
                "prefix": 8,
                "workspace": 0,
                "block_summaries": 92,
            },
            "candidate_saved_bytes": 800,
            "exact_component_equation_verified": True,
        },
        "semantic_equivalence": {
            "compared_leaf_fields": list(LEAF_SEMANTIC_FIELDS),
            "compared_terminal_fields": list(TERMINAL_SEMANTIC_FIELDS),
            "leaf_count": 1,
            "current_transcript_sha256": SHA,
            "candidate_transcript_sha256": SHA,
            "exact_output_semantics_equal": True,
            "four_residual_projection": {
                "mertens_hurst": {
                    "lower": {"value": 1},
                    "upper": {"value": 2},
                },
                "squarefree_cdem": {
                    "lower": {"value": 3},
                    "upper": {"value": 4},
                },
                "little_mertens_lower_delta": 0,
                "little_mertens_upper_delta": 0,
            },
            "receipt_domains_distinct": True,
            "receipt_digests_distinct": True,
        },
        "alternating_benchmark": {
            "repetitions": repetitions,
            "schedule": schedule,
            "current": timing("3"),
            "candidate": timing("2"),
            "current_over_candidate_device_work_ratio": "1.5",
            "measured_not_projected": True,
        },
        "runtime_device": {
            "visible_device_count": 1,
            "selected_index": "0",
            "selected_name": "NVIDIA H100" if h100 else "NVIDIA GB10",
            "selected_compute_capability": "9.0" if h100 else "12.1",
            "selected_uuid": "GPU-test",
            "driver_version": "test",
            "cuda_visible_devices_selector_present": h100,
            "strict_h100_runtime": h100,
            "target_h100_measured": h100,
        },
        "runtime_instrumentation": {
            "status": "not-inspected-by-paired-runner",
            "sanitizer_evidence_bound_to_report": False,
        },
        "claims": {
            "candidate_selected_in_production": False,
            "production_identity_changed": False,
            "default_behavior_changed": False,
            "production_receipt_identity_changed": False,
            "production_theorem_identity_changed": False,
            "execution_attested": False,
            "compiler_refinement_proved": False,
            "cuda_to_lean_refinement_proved": False,
            "source_range_evidence": False,
            "proves_any_external_atom": False,
            "projection_used": False,
            "performance_evidence_eligible": h100,
        },
    }


class MobiusHurstCombinedQualificationTests(unittest.TestCase):
    def test_closed_report_contract_for_bounded_and_h100_modes(self) -> None:
        for mode in ("bounded", "azure-h100-benchmark"):
            with self.subTest(mode=mode):
                value = fixture(mode)
                self.assertIs(validate_report(value), value)

    def test_mutations_fail_closed(self) -> None:
        mutations: list[tuple[dict[str, object], str]] = []
        for field in (
            "candidate_selected_in_production",
            "production_identity_changed",
            "default_behavior_changed",
            "production_receipt_identity_changed",
            "production_theorem_identity_changed",
            "execution_attested",
            "compiler_refinement_proved",
            "cuda_to_lean_refinement_proved",
            "source_range_evidence",
            "proves_any_external_atom",
            "projection_used",
        ):
            changed = copy.deepcopy(fixture())
            changed["claims"][field] = True
            mutations.append((changed, field))
        changed = copy.deepcopy(fixture())
        changed["semantic_equivalence"][
            "candidate_transcript_sha256"
        ] = "3" * 64
        mutations.append((changed, "semantic transcript"))
        changed = copy.deepcopy(fixture())
        changed["identities"]["candidate_algorithm"] = PRODUCTION_ALGORITHM
        mutations.append((changed, "candidate algorithm"))
        changed = copy.deepcopy(fixture())
        changed["cuda_resources"]["strict_sm90_cubin_only"] = False
        mutations.append((changed, "strict sm90"))
        changed = copy.deepcopy(fixture())
        changed["allocation"]["candidate_saved_bytes"] = 0
        mutations.append((changed, "allocation"))
        changed = copy.deepcopy(fixture())
        changed["runtime_instrumentation"]["status"] = (
            "compute-sanitizer-passed"
        )
        mutations.append((changed, "runtime instrumentation"))
        changed = copy.deepcopy(fixture())
        changed["alternating_benchmark"]["schedule"][2] = "current"
        mutations.append((changed, "alternation"))
        changed = copy.deepcopy(fixture("azure-h100-benchmark"))
        changed["runtime_device"]["target_h100_measured"] = False
        mutations.append((changed, "H100 measurement"))
        changed = copy.deepcopy(fixture())
        changed["unexpected"] = True
        mutations.append((changed, "unexpected field"))
        for value, label in mutations:
            with self.subTest(label=label):
                with self.assertRaises(QualificationError):
                    validate_report(value)

    def test_cuobjdump_resource_roles_are_unique_and_machine_readable(
        self,
    ) -> None:
        names = {
            "shared": {
                "dense_distinct_divisor": (
                    "mark_dense_prime_fused_distinct_divisors_"
                    "multiblockILm512EEE"
                ),
                "sparse_distinct_divisor": (
                    "mark_sparse_prime_fused_distinct_divisorsE"
                ),
                "dense_square_strike": (
                    "mark_dense_prime_fused_squarefulE"
                ),
                "sparse_square_strike": (
                    "mark_sparse_prime_fused_squarefulE"
                ),
                "roster_preflight": (
                    "validate_split_square_mobius_rosterE"
                ),
            },
            "current": {
                "p5_initializer": (
                    "initialize_fused_mobius_support_residue_235"
                    "ILb0ELb0ELb0EEE"
                ),
                "prefix_input_finalizer": (
                    "finalize_fused_mobius_prefix_inputsE"
                ),
                "cub_global_scan": "DeviceScanKernel",
                "thread_candidates": "affine_mq_thread_candidatesE",
                "block_candidates": "affine_mq_block_candidatesE",
                "device_candidate": "affine_mq_device_candidateE",
            },
            "candidate": {
                "p11_initializer": (
                    "initialize_fused_mobius_support_residue_235"
                    "ILb1ELb1ELb0EEE"
                ),
                "block_summaries": (
                    "affine_mq_block_summaries_from_fused_supportsE"
                ),
                "ordered_block_compose": (
                    "affine_mq_compose_block_summariesE"
                ),
            },
        }
        lines = []
        value = 8
        for family in names.values():
            for name in family.values():
                lines.append(f" Function prefix_{name}_suffix:")
                lines.append(
                    f"  REG:{value} STACK:0 SHARED:1024 LOCAL:0 "
                    "CONSTANT[0]:560 TEXTURE:0"
                )
                value += 1
        parsed = _parse_resource_usage(("\n".join(lines) + "\n").encode())
        self.assertTrue(parsed["gate"]["accepted"])
        self.assertEqual(
            parsed["roles"]["current"]["p5_initializer"],
            resource(13, 0, 1024),
        )
        self.assertEqual(
            parsed["roles"]["candidate"]["ordered_block_compose"],
            resource(21, 0, 1024),
        )

    def test_resource_overflow_and_ambiguous_role_reject(self) -> None:
        # Reuse the real strict artifact when present to exercise the parser
        # against all role names, then mutate one gate-relevant number.
        executable = (
            ROOT
            / "build/h100-native/"
            "sparkinterval-h100-tg-mobius-persistent"
        )
        cuobjdump = Path("/usr/local/cuda/bin/cuobjdump")
        if not executable.is_file() or not cuobjdump.is_file():
            self.skipTest("strict H100 artifact is unavailable")
        completed = subprocess.run(
            [str(cuobjdump), "--dump-resource-usage", str(executable)],
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = _parse_resource_usage(
            completed.stdout + completed.stderr
        )
        self.assertTrue(parsed["gate"]["accepted"])
        mutated = (completed.stdout + completed.stderr).replace(
            b"REG:64 STACK:64", b"REG:65 STACK:64", 1
        )
        with self.assertRaisesRegex(QualificationError, "resource gate"):
            _parse_resource_usage(mutated)

    def test_crossover_is_exact_and_source_paths_remain_isolated(self) -> None:
        self.assertEqual(_summary_count(MINIMUM_CROSSOVER_ROWS), 257)
        self.assertEqual(AFFINE_ROWS_PER_THREAD, 256)
        self.assertEqual(AFFINE_ROWS_PER_BLOCK, 65_536)
        runner = (
            ROOT / "gpu/src/tg_mobius_persistent_runner.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "--qualification-residue-235711-seed", runner
        )
        self.assertIn(
            "--qualification-affine-block-compose", runner
        )
        self.assertIn(PRODUCTION_ALGORITHM, runner)
        self.assertIn(
            "qualification_only_residue_235711_and_affine_"
            "block_compose_not_",
            runner,
        )
        lean = (
            ROOT
            / "SparkInterval/TernaryGoldbach/"
            "HurstAffineBlockComposition.lean"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "cudaExtractedChunksAndTree_refine_orderedFold", lean
        )
        self.assertIn(
            "cudaAffineMqTileSummaryTree_eq_perRowSummary", lean
        )
        seed = (
            ROOT
            / "SparkInterval/TernaryGoldbach/"
            "MobiusQualificationSeededRefinement.lean"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "output_decodeWord_packedSplitRunResidue235711Seeded_"
            "eq_moebius",
            seed,
        )

    def test_optional_bounded_runtime(self) -> None:
        runner = os.environ.get("TG_MOBIUS_HURST_COMBINED_RUNNER")
        strict = os.environ.get(
            "TG_MOBIUS_HURST_COMBINED_STRICT_RUNNER"
        )
        roster = os.environ.get("TG_MOBIUS_PRIME_ROSTER")
        runtime_build = os.environ.get(
            "TG_MOBIUS_HURST_COMBINED_RUNTIME_BUILD"
        )
        strict_build = os.environ.get(
            "TG_MOBIUS_HURST_COMBINED_STRICT_BUILD"
        )
        if not all((runner, strict, roster, runtime_build, strict_build)):
            self.skipTest("paired bounded runtime inputs were not provided")
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/qualify_tg_mobius_hurst_combined.py"
                ),
                "--runner",
                runner,
                "--runtime-build-dir",
                runtime_build,
                "--strict-h100-runner",
                strict,
                "--strict-build-dir",
                strict_build,
                "--prime-roster",
                roster,
                "--repeats",
                "1",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=1_800,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        validate_report(json.loads(completed.stdout))


if __name__ == "__main__":
    unittest.main()
