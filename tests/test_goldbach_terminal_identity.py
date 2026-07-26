#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_build_admission import load_build_admission
from tg_verifier.goldbach_terminal_identity import (
    BUNDLE_KIND,
    NOT_APPLICABLE_DIGEST,
    GoldbachTerminalIdentityError,
    child_identity_commitment,
    check_lean_terminal_pins,
    expected_child_topology,
    lean_pin_values,
    load_terminal_identity_bundle,
    render_lean_pin_candidate,
    terminal_execution_binding,
    validate_terminal_identity_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
ADMISSION_FIXTURE = ROOT / "tests/fixtures/goldbach_build_admission.test.json"
PIN_SOURCE = ROOT / "SparkInterval/Execution/Goldbach10Pow27TerminalPins.lean"


def wire_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def file_value(value: dict) -> dict:
    raw = wire_bytes(value)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "value": value,
    }


def record(
    path: str,
    role: str,
    sha256: str,
    *,
    statement_role: str | None = None,
    executable: bool = False,
    size_bytes: int = 10,
) -> dict:
    return {
        "executable": executable,
        "path": path,
        "role": role,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "statement_role": statement_role,
    }


def candidate_bundle() -> dict:
    admission = load_build_admission(
        ADMISSION_FIXTURE, allow_test_fixture=True
    )
    digest = lambda tag: hashlib.sha256(tag.encode("utf-8")).hexdigest()
    children = []
    for phase, index in expected_child_topology():
        h100 = phase.startswith(
            "h100-8192-groups-of-eight-lowered-checkpoint-leaves"
        )
        projection = digest(f"projection:{phase}:{index}")
        children.append(
            {
                "algorithm_hash": digest(f"algorithm:{phase}:{index}"),
                "algorithm_id": f"test.{phase}.{index}",
                "artifacts": {
                    "device_cubin_hash": (
                        digest("h100 executable")
                        if h100 else NOT_APPLICABLE_DIGEST
                    ),
                    "host_executable_hash": digest("child host"),
                    "kernel_manifest_hash": (
                        projection if h100 else digest(f"closure:{phase}:{index}")
                    ),
                    "source_tree_hash": digest("child source"),
                },
                "backend": (
                    "azure_ncc40ads_h100_v5" if h100 else "azure_sevsnp_cpu"
                ),
                "claim_sha256": digest(f"claim:{phase}:{index}"),
                "domain_hash": digest(f"domain:{phase}:{index}"),
                "group_id": (
                    "ternary-goldbach-finite-below-10pow27-v1::" + phase
                ),
                "input_hash": digest(f"input:{phase}:{index}"),
                "job_projection_sha256": (
                    projection if h100 else NOT_APPLICABLE_DIGEST
                ),
                "output_hash": digest(f"output:{phase}:{index}"),
                "parameters_hash": digest(f"parameters:{phase}:{index}"),
                "phase": phase,
                "receipt_sha256": digest(f"receipt:{phase}:{index}"),
                "shard_index": index,
            }
        )
    children.sort(key=lambda item: (item["phase"], item["shard_index"]))

    host_hash = digest("terminal host")
    source_hash = digest("terminal source")
    producer_hash = digest("terminal producer")
    runtime_value = {
        "goldbach_build_admission_sha256": admission.admission_sha256,
        "goldbach_build_identity_sha256": admission.build_identity_sha256,
        "kind": "sparkinterval.goldbach10pow27.image-runtime-closure.v1",
        "ladder_runner": {"sha256": producer_hash},
        "goldbach_executable": {
            "sha256": admission.core["executable"]["sha256"]
        },
        "python_executable": {"sha256": host_hash},
    }
    source_value = {
        "goldbach_build_admission_sha256": admission.admission_sha256,
        "kind": "sparkinterval.goldbach10pow27-source-reviewed-closure.v1",
    }
    runner_value = {
        "classification": "production",
        "immutable_image_reference": "test",
        "kind": "sparkinterval_measured_runner_policy",
        "production_ready": True,
    }
    runtime = file_value(runtime_value)
    source = file_value(source_value)
    runner = file_value(runner_value)
    child_commitment = file_value(
        child_identity_commitment(
            children,
            build_admission_sha256=admission.admission_sha256,
            build_identity_sha256=admission.build_identity_sha256,
            h100_executable_sha256=admission.core["executable"]["sha256"],
            h100_runtime_image_closure_sha256=admission.deployment[
                "runtime_image_closure_sha256"
            ],
        )
    )
    producer = record(
        "artifacts/ladder",
        "static_gmp_n45_ladder_producer",
        producer_hash,
        statement_role="producer_executable",
        executable=True,
    )
    target_profile_hash = digest("terminal target")
    trust_profile_hash = digest("terminal trust")
    terminal_binding = file_value(
        terminal_execution_binding(
            build_admission_sha256=admission.admission_sha256,
            child_identity_commitment_sha256=child_commitment["sha256"],
            h100_executable_sha256=admission.core["executable"]["sha256"],
            h100_runtime_image_closure_sha256=admission.deployment[
                "runtime_image_closure_sha256"
            ],
            runner_policy_sha256=runner["sha256"],
            runtime_closure_sha256=runtime["sha256"],
            source_manifest_sha256=source["sha256"],
            target_profile_sha256=target_profile_hash,
            terminal_host_executable_sha256=host_hash,
            terminal_producer_executable_sha256=producer_hash,
            trust_profile_sha256=trust_profile_hash,
        )
    )
    files = sorted(
        [
            record(
                "artifacts/python3",
                "image_bound_cpython_host",
                host_hash,
                statement_role="host_executable",
                executable=True,
            ),
            producer,
            record(
                "source/admission.json",
                "reviewed_goldbach_build_admission",
                admission.admission_sha256,
                size_bytes=admission.admission_size_bytes,
            ),
            record(
                "artifacts/goldbach-gpu",
                "h100_executable_identity_data_not_cpu_executed",
                admission.core["executable"]["sha256"],
                executable=True,
            ),
            record(
                "source/child-receipt-identities.json",
                "goldbach_child_receipt_identity_commitment",
                child_commitment["sha256"],
                size_bytes=child_commitment["size_bytes"],
            ),
            record(
                "source/terminal-execution-binding.json",
                "goldbach_terminal_post_child_run_binding",
                terminal_binding["sha256"],
                size_bytes=terminal_binding["size_bytes"],
            ),
            record(
                "source/runtime.json",
                "image_runtime_closure_manifest",
                runtime["sha256"],
                size_bytes=runtime["size_bytes"],
            ),
            record(
                "source/source.json",
                "reviewed_source_closure_manifest",
                source["sha256"],
                statement_role="source_tree",
                size_bytes=source["size_bytes"],
            ),
        ],
        key=lambda item: item["path"],
    )
    closure_hash = hashlib.sha256(
        wire_bytes(
            {
                "artifacts": files,
                "kind": "sparkinterval_executable_artifact_closure",
                "schema_version": 1,
            }
        )
    ).hexdigest()
    bundle = {
        "admission": {
            "admission_sha256": admission.admission_sha256,
            "admission_size_bytes": admission.admission_size_bytes,
            "build_identity_sha256": admission.build_identity_sha256,
            "executable_sha256": admission.core["executable"]["sha256"],
            "h100_artifact_closure_manifest_sha256": (
                admission.expected_artifacts[
                    "artifact_closure_manifest_sha256"
                ]
            ),
            "h100_runtime_image_closure": admission.runtime_image_closure(),
            "h100_runtime_image_closure_sha256": admission.deployment[
                "runtime_image_closure_sha256"
            ],
            "h100_source_tree_sha256": admission.expected_artifacts[
                "source_tree_hash"
            ],
            "source_identity_sha256": admission.core[
                "source_identity_sha256"
            ],
        },
        "children": {
            "count": len(children),
            "identities": children,
            "identities_sha256": hashlib.sha256(
                canonical_json_bytes(children)
            ).hexdigest(),
        },
        "classification": "post-run-candidate",
        "kind": BUNDLE_KIND,
        "registered_invocation": "goldbach10Pow27ProductionV1",
        "schema_version": 1,
        "terminal": {
            "artifact_closure": {
                "closure_kind": "content_addressed_image_source_reviewed_v1",
                "files": files,
                "manifest_sha256": closure_hash,
                "terminal_producer_executable": producer,
            },
            "child_identity_commitment": child_commitment,
            "claim": {
                "algorithm_hash": digest("terminal algorithm"),
                "algorithm_id": "test.terminal",
                "artifacts": {
                    "device_cubin_hash": NOT_APPLICABLE_DIGEST,
                    "host_executable_hash": host_hash,
                    "kernel_manifest_hash": closure_hash,
                    "source_tree_hash": source_hash,
                },
                "domain_hash": digest("terminal domain"),
                "input_hash": digest("terminal input"),
                "output_hash": digest("terminal output"),
                "parameters_hash": digest("terminal parameters"),
                "result": "true",
                "target": "azure_sevsnp_cpu",
                "target_profile_hash": target_profile_hash,
                "trust": "azure_sevsnp_confidential_compute",
                "trust_profile_hash": trust_profile_hash,
            },
            "job_spec_sha256": digest("terminal job"),
            "materialization_manifest_sha256": digest("terminal materialization"),
            "receipt_sha256": digest("terminal receipt"),
            "runner_policy": runner,
            "runtime_closure": runtime,
            "source_manifest": source,
            "terminal_execution_binding": terminal_binding,
        },
    }
    # The statement source-tree hash is the source-manifest artifact hash.
    bundle["terminal"]["claim"]["artifacts"]["source_tree_hash"] = source[
        "sha256"
    ]
    return bundle


class GoldbachTerminalIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = candidate_bundle()

    def test_candidate_is_complete_but_requires_explicit_review_mode(self) -> None:
        checked = validate_terminal_identity_bundle(self.bundle)
        self.assertEqual(
            checked["children"]["count"], len(expected_child_topology())
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.json"
            path.write_bytes(canonical_json_bytes(self.bundle))
            with self.assertRaisesRegex(
                GoldbachTerminalIdentityError, "explicit review mode"
            ):
                load_terminal_identity_bundle(path)
            loaded, digest = load_terminal_identity_bundle(
                path, allow_candidate=True
            )
            self.assertEqual(loaded, checked)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

            production = copy.deepcopy(self.bundle)
            production["classification"] = "reviewed-production"
            production_path = Path(temporary) / "production.json"
            production_path.write_bytes(canonical_json_bytes(production))
            with self.assertRaisesRegex(
                GoldbachTerminalIdentityError, "production.*unconfigured"
            ):
                load_terminal_identity_bundle(production_path)

    def test_child_projection_and_terminal_artifact_substitution_fail(self) -> None:
        changed = copy.deepcopy(self.bundle)
        h100 = next(
            child for child in changed["children"]["identities"]
            if child["phase"].startswith("h100-")
        )
        h100["job_projection_sha256"] = "c" * 64
        changed["children"]["identities_sha256"] = hashlib.sha256(
            canonical_json_bytes(changed["children"]["identities"])
        ).hexdigest()
        with self.assertRaisesRegex(
            GoldbachTerminalIdentityError, "wrong job projection role"
        ):
            validate_terminal_identity_bundle(changed)

        changed = copy.deepcopy(self.bundle)
        changed["terminal"]["claim"]["artifacts"][
            "host_executable_hash"
        ] = "c" * 64
        with self.assertRaisesRegex(
            GoldbachTerminalIdentityError, "wrong host_executable"
        ):
            validate_terminal_identity_bundle(changed)

    def test_changed_child_identity_changes_lean_checked_terminal_commitment(
        self,
    ) -> None:
        changed = copy.deepcopy(self.bundle)
        changed["children"]["identities"][0]["receipt_sha256"] = "c" * 64
        changed["children"]["identities_sha256"] = hashlib.sha256(
            canonical_json_bytes(changed["children"]["identities"])
        ).hexdigest()

        admission = changed["admission"]
        commitment = file_value(
            child_identity_commitment(
                changed["children"]["identities"],
                build_admission_sha256=admission["admission_sha256"],
                build_identity_sha256=admission["build_identity_sha256"],
                h100_executable_sha256=admission["executable_sha256"],
                h100_runtime_image_closure_sha256=admission[
                    "h100_runtime_image_closure_sha256"
                ],
            )
        )
        changed["terminal"]["child_identity_commitment"] = commitment
        files = changed["terminal"]["artifact_closure"]["files"]
        commitment_record = next(
            row
            for row in files
            if row["role"] == "goldbach_child_receipt_identity_commitment"
        )
        commitment_record["sha256"] = commitment["sha256"]
        commitment_record["size_bytes"] = commitment["size_bytes"]
        binding_value = dict(
            changed["terminal"]["terminal_execution_binding"]["value"]
        )
        binding_value["child_identity_commitment_sha256"] = commitment[
            "sha256"
        ]
        terminal_binding = file_value(binding_value)
        changed["terminal"][
            "terminal_execution_binding"
        ] = terminal_binding
        binding_record = next(
            row
            for row in files
            if row["role"] == "goldbach_terminal_post_child_run_binding"
        )
        binding_record["sha256"] = terminal_binding["sha256"]
        binding_record["size_bytes"] = terminal_binding["size_bytes"]
        closure_hash = hashlib.sha256(
            wire_bytes(
                {
                    "artifacts": files,
                    "kind": "sparkinterval_executable_artifact_closure",
                    "schema_version": 1,
                }
            )
        ).hexdigest()
        changed["terminal"]["artifact_closure"][
            "manifest_sha256"
        ] = closure_hash
        changed["terminal"]["claim"]["artifacts"][
            "kernel_manifest_hash"
        ] = closure_hash
        validate_terminal_identity_bundle(changed)

        original_pins = lean_pin_values(
            self.bundle,
            hashlib.sha256(canonical_json_bytes(self.bundle)).hexdigest(),
        )
        changed_pins = lean_pin_values(
            changed, hashlib.sha256(canonical_json_bytes(changed)).hexdigest()
        )
        self.assertEqual(
            changed["terminal"]["claim"]["algorithm_id"],
            self.bundle["terminal"]["claim"]["algorithm_id"],
        )
        self.assertEqual(
            changed["terminal"]["claim"]["input_hash"],
            self.bundle["terminal"]["claim"]["input_hash"],
        )
        for field in (
            "device_cubin_hash",
            "host_executable_hash",
            "source_tree_hash",
        ):
            self.assertEqual(
                changed["terminal"]["claim"]["artifacts"][field],
                self.bundle["terminal"]["claim"]["artifacts"][field],
            )
        original_roles = {
            row["role"]: row["sha256"]
            for row in self.bundle["terminal"]["artifact_closure"]["files"]
        }
        changed_roles = {
            row["role"]: row["sha256"]
            for row in changed["terminal"]["artifact_closure"]["files"]
        }
        for role in (
            "h100_executable_identity_data_not_cpu_executed",
            "image_runtime_closure_manifest",
            "reviewed_goldbach_build_admission",
            "reviewed_source_closure_manifest",
            "static_gmp_n45_ladder_producer",
        ):
            self.assertEqual(changed_roles[role], original_roles[role])
        self.assertNotEqual(
            changed_pins["kernel_manifest_hash"],
            original_pins["kernel_manifest_hash"],
        )

        unbound = copy.deepcopy(self.bundle)
        unbound["children"] = changed["children"]
        with self.assertRaisesRegex(
            GoldbachTerminalIdentityError, "child identity commitment differs"
        ):
            validate_terminal_identity_bundle(unbound)

    def test_current_lean_registration_is_null_and_candidate_pins_are_exact(self) -> None:
        raw = canonical_json_bytes(self.bundle)
        pins = lean_pin_values(
            self.bundle, hashlib.sha256(raw).hexdigest()
        )
        current = PIN_SOURCE.read_text(encoding="utf-8")
        with self.assertRaisesRegex(
            GoldbachTerminalIdentityError, "unconfigured"
        ):
            check_lean_terminal_pins(current, pins)

        candidate = render_lean_pin_candidate(pins)
        check_lean_terminal_pins(candidate, pins)
        stale = candidate.replace(
            f'some "{pins["receipt_sha256"]}"',
            f'some "{"c" * 64}"',
            1,
        )
        with self.assertRaisesRegex(GoldbachTerminalIdentityError, "stale"):
            check_lean_terminal_pins(stale, pins)

        with tempfile.TemporaryDirectory() as temporary:
            candidate_path = Path(temporary) / "Candidate.lean"
            candidate_path.write_text(candidate, encoding="utf-8")
            compiled = subprocess.run(
                ["lake", "env", "lean", str(candidate_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

    def test_generator_cli_is_explicitly_post_run(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/generate_goldbach_terminal_registration.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--child-index", completed.stdout)
        self.assertIn("--lean-candidate", completed.stdout)
        commitment_help = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/generate_goldbach_child_identity_commitment.py"
                ),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(commitment_help.returncode, 0, commitment_help.stderr)
        self.assertIn("--child-index", commitment_help.stdout)


if __name__ == "__main__":
    unittest.main()
