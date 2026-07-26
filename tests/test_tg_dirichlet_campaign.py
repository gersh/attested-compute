# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.dirichlet_campaign import (  # noqa: E402
    FULL_SOURCE_CHARACTER_COUNT,
    SOURCE_MAX_Q,
    SOURCE_MIN_Q,
    DirichletCampaignError,
    ScheduleIndex,
    canonical_json_bytes,
    finalize_campaign,
    initialize_campaign,
    primitive_character_count,
    primitive_character_descriptor,
    rerun_external_checkers,
    run_campaign,
    source_height,
    verify_campaign,
)
from tools.tg_dirichlet_campaign import (  # noqa: E402
    _validate_retained_source_requirement,
)


BACKEND_TEMPLATE = r'''#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys

ROLE = "__ROLE__"
RIGOROUS = __RIGOROUS__
PRODUCER_PROTOCOL = "sparkinterval.dirichlet-grh-producer.v1"
CHECKER_PROTOCOL = "sparkinterval.dirichlet-grh-checker.v1"
RESULT_SCHEMA = "sparkinterval.tg.dirichlet_campaign.external_result.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_campaign.external_checker_receipt.v2"

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")

def options(words):
    return {words[i]: Path(words[i + 1]) for i in range(0, len(words), 2)}

if sys.argv[1:] == ["protocol-version"]:
    print(PRODUCER_PROTOCOL if ROLE == "producer" else CHECKER_PROTOCOL)
    raise SystemExit(0)

command = sys.argv[1]
args = options(sys.argv[2:])
request_raw = args["--request"].read_bytes()
request = json.loads(request_raw)
if ROLE == "producer" and command == "produce":
    payload = args["--artifact-root"]
    payload.mkdir(exist_ok=True)
    proof = payload / "proof.txt"
    proof.write_text(request["compact_task_set_sha256"] + "\n", encoding="ascii")
    proof_raw = proof.read_bytes()
    result = {
        "kind": RESULT_SCHEMA,
        "schema_version": 1,
        "producer_algorithm_id": "test-producer-v1",
        "producer_version": "1",
        "request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "compact_task_set_sha256": request["compact_task_set_sha256"],
        "character_count": request["character_count"],
        "segment_count": request["segment_count"],
        "completed": True,
        "output_artifacts": [{
            "path": "proof.txt",
            "sha256": hashlib.sha256(proof_raw).hexdigest(),
            "size": len(proof_raw),
            "media_type": "text/plain",
        }],
    }
    args["--output"].write_bytes(canonical(result))
    raise SystemExit(0)
if ROLE == "checker" and command == "verify":
    result_raw = args["--result"].read_bytes()
    result = json.loads(result_raw)
    receipt = {
        "kind": RECEIPT_SCHEMA,
        "schema_version": 1,
        "checker_algorithm_id": "test-checker-v1",
        "checker_version": "1",
        "request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "compact_task_set_sha256": request["compact_task_set_sha256"],
        "character_count": request["character_count"],
        "segment_count": request["segment_count"],
        "accepted": RIGOROUS,
        "all_requested_characters_covered": RIGOROUS,
        "primitive_character_mapping_checked": RIGOROUS,
        "source_height_exact": RIGOROUS,
        "closed_symmetric_height_covered": RIGOROUS,
        "analytic_function_enclosures_rigorous": RIGOROUS,
        "critical_strip_boundary_zero_free": RIGOROUS,
        "turing_or_argument_principle_count_complete": RIGOROUS,
        "zero_multiplicities_preserved": RIGOROUS,
        "all_nontrivial_zeros_on_critical_line": RIGOROUS,
    }
    args["--receipt"].write_bytes(canonical(receipt))
    raise SystemExit(0)
raise SystemExit(2)
'''


def make_backend(directory: Path, role: str, *, rigorous: bool = True) -> Path:
    path = directory / role
    path.write_text(
        BACKEND_TEMPLATE.replace("__ROLE__", role).replace(
            "__RIGOROUS__", "True" if rigorous else "False"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


class DirichletCampaignTests(unittest.TestCase):
    def test_source_verifier_checks_the_retained_requirement_wrapper(self) -> None:
        q1 = {
            "kind": "test-q1-final",
            "zeta_final_sha256": "a" * 64,
        }
        requirement = {
            "kind": "sparkinterval.tg.dirichlet_campaign.source_requirement.v1",
            "q1_zeta": q1,
            "reference_backend_limits": {
                "maximum_precision_bits": 16_384,
                "maximum_contour_depth": 96,
                "maximum_contour_evaluations": 0,
                "maximum_grid_refinements": 24,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "q1-zeta-requirement.json"
            path.write_bytes(canonical_json_bytes(requirement))
            self.assertEqual(
                _validate_retained_source_requirement(path, q1), requirement
            )
            path.write_bytes(canonical_json_bytes(q1))
            with self.assertRaisesRegex(DirichletCampaignError, "fields differ"):
                _validate_retained_source_requirement(path, q1)

    def test_primitive_counts_and_conrey_unranking(self) -> None:
        expected_counts = {
            1: 1,
            2: 0,
            3: 1,
            4: 1,
            5: 3,
            6: 0,
            7: 5,
            8: 2,
            9: 4,
            10: 0,
            12: 1,
            16: 4,
        }
        self.assertEqual(
            {q: primitive_character_count(q) for q in expected_counts},
            expected_counts,
        )
        self.assertEqual(
            [primitive_character_descriptor(5, i)["conrey_number"] for i in range(3)],
            [2, 4, 3],
        )
        self.assertEqual(
            [primitive_character_descriptor(5, i)["parity"] for i in range(3)],
            [1, 0, 1],
        )
        self.assertEqual(
            [primitive_character_descriptor(8, i)["conrey_number"] for i in range(2)],
            [5, 3],
        )
        self.assertEqual(
            [primitive_character_descriptor(8, i)["parity"] for i in range(2)],
            [0, 1],
        )

    def test_exact_source_heights(self) -> None:
        self.assertEqual(source_height(1), Fraction(100_000_000))
        self.assertEqual(source_height(100_000), Fraction(1_000))
        self.assertEqual(source_height(400_000), Fraction(775, 2))
        self.assertEqual(source_height(399_999), Fraction(117_499_800, 399_999))

    def test_full_schedule_has_pinned_source_count(self) -> None:
        schedule = ScheduleIndex.build(SOURCE_MIN_Q, SOURCE_MAX_Q)
        self.assertEqual(schedule.total_characters, FULL_SOURCE_CHARACTER_COUNT)
        self.assertEqual(schedule.nonzero_moduli, 299_999)
        self.assertEqual(
            schedule.schedule_sha256,
            "074a34d0b0fe4024781efa878e82601a1139628cc4144f90875d1d090f22f8fc",
        )

    def test_compact_segments_cross_empty_moduli_without_gaps(self) -> None:
        schedule = ScheduleIndex.build(1, 8)
        self.assertEqual(schedule.total_characters, 13)
        segments = schedule.segments(0, 5)
        self.assertEqual([row["q"] for row in segments], [1, 3, 4, 5])
        self.assertEqual(
            sum(
                row["character_ordinal_stop"] - row["character_ordinal_start"]
                for row in segments
            ),
            5,
        )
        self.assertEqual(segments[-1]["character_ordinal_stop"], 2)

    def test_campaign_resumes_replays_and_labels_external_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            producer = make_backend(base, "producer")
            checker = make_backend(base, "checker")
            root = base / "campaign"
            plan = initialize_campaign(
                root,
                producer=producer,
                checker=checker,
                characters_per_chunk=5,
                mode="bounded_sample",
                q_start=1,
                q_stop=8,
            )
            self.assertEqual(plan["total_primitive_characters"], 13)
            partial = run_campaign(root, max_chunks=1)
            self.assertEqual(partial["characters_covered"], 5)
            self.assertFalse(partial["complete"])
            complete = run_campaign(root)
            self.assertTrue(complete["complete"])
            self.assertFalse(complete["lean_atom_discharged"])
            final = finalize_campaign(root)
            self.assertEqual(
                final["coverage_class"], "bounded_sample_external_checker_asserted"
            )
            replay = rerun_external_checkers(root)
            self.assertEqual(replay["fresh_external_checker_replays"], 3)
            checked = verify_campaign(root, require_complete=True)
            self.assertTrue(checked["final_present"])
            self.assertFalse(checked["internally_implemented_turing_or_argument_principle"])

    def test_nonrigorous_numeric_sanity_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            producer = make_backend(base, "producer")
            checker = make_backend(base, "checker", rigorous=False)
            root = base / "campaign"
            initialize_campaign(
                root,
                producer=producer,
                checker=checker,
                characters_per_chunk=5,
                mode="bounded_sample",
                q_start=3,
                q_stop=5,
            )
            with self.assertRaisesRegex(DirichletCampaignError, "did not establish accepted"):
                run_campaign(root, max_chunks=1)
            self.assertEqual(list((root / "chunks").iterdir()), [])

    def test_payload_tampering_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            producer = make_backend(base, "producer")
            checker = make_backend(base, "checker")
            root = base / "campaign"
            initialize_campaign(
                root,
                producer=producer,
                checker=checker,
                characters_per_chunk=10,
                mode="bounded_sample",
                q_start=3,
                q_stop=5,
            )
            run_campaign(root)
            proof = root / "chunks" / "chunk-00000000" / "payload" / "proof.txt"
            proof.write_text("tampered\n", encoding="ascii")
            with self.assertRaisesRegex(DirichletCampaignError, "digest mismatch"):
                verify_campaign(root)

    def test_forged_checker_byte_distinction_flag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            producer = make_backend(base, "producer")
            checker = make_backend(base, "checker")
            root = base / "campaign"
            initialize_campaign(
                root,
                producer=producer,
                checker=checker,
                mode="bounded_sample",
                q_start=3,
                q_stop=3,
            )
            plan_path = root / "campaign.json"
            plan = json.loads(plan_path.read_text(encoding="ascii"))
            producer_bytes = (root / "artifacts" / "producer").read_bytes()
            (root / "artifacts" / "checker").write_bytes(producer_bytes)
            plan["checker"]["sha256"] = plan["producer"]["sha256"]
            plan["checker"]["size"] = plan["producer"]["size"]
            plan["checker"]["bytes_distinct_from_producer"] = True
            del plan["plan_sha256"]
            plan["plan_sha256"] = hashlib.sha256(
                canonical_json_bytes(plan)
            ).hexdigest()
            plan_path.write_bytes(canonical_json_bytes(plan))
            with self.assertRaisesRegex(DirichletCampaignError, "byte-distinction"):
                verify_campaign(root)

    def test_payload_symbolic_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            producer = make_backend(base, "producer")
            checker = make_backend(base, "checker")
            root = base / "campaign"
            initialize_campaign(
                root,
                producer=producer,
                checker=checker,
                characters_per_chunk=10,
                mode="bounded_sample",
                q_start=3,
                q_stop=3,
            )
            run_campaign(root)
            proof = root / "chunks" / "chunk-00000000" / "payload" / "proof.txt"
            replacement = base / "replacement.txt"
            replacement.write_bytes(proof.read_bytes())
            proof.unlink()
            proof.symlink_to(replacement)
            with self.assertRaisesRegex(DirichletCampaignError, "symbolic link"):
                verify_campaign(root)

    def test_cli_separates_slow_argument_reference_from_fast_backend(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/tg_dirichlet_campaign.py", "capability"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(report["total_primitive_characters"], FULL_SOURCE_CHARACTER_COUNT)
        self.assertTrue(
            report["in_repository_rigorous_argument_principle_reference_backend"]
        )
        self.assertFalse(report["in_repository_fast_platt_lattice_fft_backend"])
        self.assertTrue(report["in_repository_optimized_platt_components"])
        self.assertTrue(
            report["conditional_large_q_taylor_stage"]["unit_group_fft_present"]
        )
        self.assertTrue(
            report["optimized_component_capabilities"][
                "persistent_source_composition_ready"
            ]
        )
        self.assertTrue(
            report["optimized_component_capabilities"][
                "scalable_root_number_artifact_ready"
            ]
        )
        self.assertTrue(
            report["optimized_component_capabilities"][
                "t_major_lattice_cache_contract_ready"
            ]
        )
        self.assertEqual(
            report["optimized_component_capabilities"][
                "t_major_unique_lattice_payload_bytes"
            ],
            134_205_145_088,
        )
        self.assertEqual(
            report["optimized_component_capabilities"][
                "t_major_compact_total_input_bytes"
            ],
            286_556_459_000,
        )
        self.assertTrue(
            report["optimized_component_capabilities"][
                "row_resident_t_major_cuda_component_executable"
            ]
        )
        self.assertFalse(
            report["optimized_component_capabilities"][
                "hurwitz_lattice_cache_and_broadcast_ready"
            ]
        )
        self.assertFalse(
            report["optimized_component_capabilities"][
                "certified_box_producer_and_source_io_ready"
            ]
        )
        self.assertFalse(
            report["optimized_component_capabilities"][
                "production_closed_optimized_campaign_ready"
            ]
        )
        self.assertFalse(report["current_numeric_turing_sanity_accepted_as_completeness"])


if __name__ == "__main__":
    unittest.main()
