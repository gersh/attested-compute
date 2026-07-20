# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI = REPOSITORY_ROOT / "tools" / "tg_campaign.py"

from tg_verifier.campaign import (  # noqa: E402
    CampaignError,
    STATUS_KIND,
    create_plan,
    doctor_profile,
    load_registry,
    validate_plan,
    validate_status,
    verify_plan_inputs,
    verify_workspace,
    workspace_status,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    atomic_write_json,
    canonical_json_bytes,
    canonical_sha256,
    load_json,
    write_immutable_json,
)
from tg_verifier.catalog import ATOMS  # noqa: E402


class CampaignRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry()

    def _minimal_cdem_repository(self, root: Path) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        for spec in profile.required_inputs:
            if spec.kind != "repository_file":
                continue
            source = REPOSITORY_ROOT / spec.locator
            destination = root / spec.locator
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (root / "unrelated.txt").write_bytes(b"tracked but not a bound input\n")
        subprocess.run(
            ["git", "init", "-q"], cwd=root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "--", "."], cwd=root, check=True, capture_output=True
        )

    def test_registry_matches_all_thirteen_catalog_ids_exactly(self) -> None:
        self.assertEqual(len(self.registry.profiles), 13)
        self.assertEqual(
            [profile.atom_id for profile in self.registry.profiles],
            [atom.atom_id for atom in ATOMS],
        )
        self.assertEqual(len(self.registry.by_id), 13)

    def test_every_sample_engine_is_explicitly_not_full_source(self) -> None:
        for profile in self.registry.profiles:
            for engine in profile.engines:
                if engine.sample_only:
                    self.assertFalse(engine.supports_full_source, profile.atom_id)
                    self.assertFalse(engine.supports_resume, profile.atom_id)

    def test_capability_never_claims_a_completed_campaign_or_lean_proof(self) -> None:
        from tg_verifier.campaign import capability_record

        for profile in self.registry.profiles:
            record = capability_record(profile)
            self.assertFalse(record["full_source_campaign_completed"])
            self.assertFalse(record["lean_atom_discharged"])

    def test_registry_rejects_duplicate_keys_and_floats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(CampaignError, "duplicate JSON key"):
                load_registry(duplicate)
            floating = Path(directory) / "float.json"
            floating.write_text('{"schema_version":1.0}\n', encoding="utf-8")
            with self.assertRaisesRegex(CampaignError, "floating-point JSON"):
                load_registry(floating)

    def test_registry_rejects_catalog_hash_change(self) -> None:
        value = json.loads(
            (
                REPOSITORY_ROOT
                / "specifications"
                / "TERNARY_GOLDBACH_CAMPAIGN_PROFILES.json"
            ).read_text(encoding="utf-8")
        )
        value["source_catalog_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(CampaignError, "not bound"):
                load_registry(path)

    def test_all_thirteen_expose_a_full_source_engine(self) -> None:
        self.assertTrue(all(profile.full_source_engines for profile in self.registry.profiles))
        self.assertNotIn(
            "blocked", {profile.implementation_state for profile in self.registry.profiles}
        )

    def test_full_plan_refuses_missing_required_artifact(self) -> None:
        profile = self.registry.by_id["ch25-a7-boundary"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CampaignError, "missing or invalid inputs"):
                create_plan(
                    self.registry,
                    profile,
                    {},
                    workspace=Path(directory),
                )

    def test_cdem_full_plan_is_hash_bound_and_not_a_completion_claim(self) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        diagnosis = doctor_profile(profile, {})
        if not diagnosis["prerequisites_available"]:
            self.skipTest("g++ is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            plan = create_plan(
                self.registry,
                profile,
                {},
                workspace=Path(directory),
            )
        self.assertEqual(plan["scope"], "full_source")
        self.assertFalse(plan["sample"])
        self.assertFalse(plan["full_source_campaign_completed"])
        self.assertFalse(plan["lean_atom_discharged"])
        self.assertEqual(len(canonical_sha256(plan)), 64)

    def test_plan_rejects_invocation_tampering_and_changed_inputs(self) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        diagnosis = doctor_profile(profile, {})
        if not diagnosis["prerequisites_available"]:
            self.skipTest("g++ is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = create_plan(self.registry, profile, {}, workspace=workspace)
            changed = dict(plan)
            changed["invocation"] = ["/bin/true"]
            with self.assertRaisesRegex(CampaignError, "invocation differs"):
                validate_plan(changed, self.registry, workspace=workspace)

            source_record = next(
                record
                for record in plan["bound_inputs"]
                if record["id"] == "cdem_source"
            )
            changed = json.loads(json.dumps(plan))
            changed_record = next(
                record
                for record in changed["bound_inputs"]
                if record["id"] == "cdem_source"
            )
            changed_record["resolved"] = str(workspace / "other.cpp")
            changed["invocation"] = [
                token.replace(source_record["resolved"], changed_record["resolved"])
                for token in plan["invocation"]
            ]
            with self.assertRaisesRegex(CampaignError, "repository input path"):
                validate_plan(changed, self.registry, workspace=workspace)

            validate_plan(plan, self.registry, workspace=workspace)
            self.assertGreaterEqual(len(verify_plan_inputs(plan)), 3)

    def test_plan_binds_complete_git_tracked_working_tree(self) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        diagnosis = doctor_profile(profile, {})
        if not diagnosis["prerequisites_available"]:
            self.skipTest("g++ is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._minimal_cdem_repository(root)
            workspace = root / "workspace"
            first = create_plan(
                self.registry,
                profile,
                {},
                repository_root=root,
                workspace=workspace,
            )
            second = create_plan(
                self.registry,
                profile,
                {},
                repository_root=root,
                workspace=workspace,
            )
            self.assertEqual(first, second)
            self.assertEqual(first["schema_version"], 2)
            self.assertEqual(first["repository_tree"]["tracked_file_count"], 5)

            ignored = root / "build" / "untracked.bin"
            ignored.parent.mkdir()
            ignored.write_bytes(b"not part of git ls-files\n")
            validate_plan(
                first,
                self.registry,
                repository_root=root,
                workspace=workspace,
            )
            verify_plan_inputs(first)

            unrelated = root / "unrelated.txt"
            original = unrelated.read_bytes()
            unrelated.write_bytes(original + b"changed\n")
            with self.assertRaisesRegex(
                CampaignError, "tracked repository tree changed"
            ):
                validate_plan(
                    first,
                    self.registry,
                    repository_root=root,
                    workspace=workspace,
                )
            with self.assertRaisesRegex(
                CampaignError, "tracked repository tree changed"
            ):
                verify_plan_inputs(first)

            unrelated.write_bytes(original)
            validate_plan(
                first,
                self.registry,
                repository_root=root,
                workspace=workspace,
            )
            os.chmod(unrelated, unrelated.stat().st_mode | 0o111)
            with self.assertRaisesRegex(CampaignError, "executable bit"):
                validate_plan(
                    first,
                    self.registry,
                    repository_root=root,
                    workspace=workspace,
                )
            with self.assertRaisesRegex(CampaignError, "executable bit"):
                verify_plan_inputs(first)

            os.chmod(unrelated, unrelated.stat().st_mode & ~0o111)
            unrelated.unlink()
            (root / "untracked-target.txt").write_bytes(original)
            unrelated.symlink_to("untracked-target.txt")
            with self.assertRaisesRegex(CampaignError, "symbolic link"):
                validate_plan(
                    first,
                    self.registry,
                    repository_root=root,
                    workspace=workspace,
                )
            with self.assertRaisesRegex(CampaignError, "symbolic link"):
                verify_plan_inputs(first)

    def test_status_rejects_sample_promoted_to_full(self) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        diagnosis = doctor_profile(profile, {})
        if not diagnosis["prerequisites_available"]:
            self.skipTest("g++ is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            plan = create_plan(
                self.registry, profile, {}, workspace=Path(directory)
            )
            status = {
                "schema_version": 1,
                "kind": STATUS_KIND,
                "atom_id": profile.atom_id,
                "profile_sha256": profile.profile_sha256,
                "plan_sha256": canonical_sha256(plan),
                "state": "verified",
                "scope": "sample",
                "sample": True,
                "covered_lower": profile.full_source_domain["lower"],
                "covered_upper": profile.full_source_domain["upper"],
                "covered_work_items": profile.full_source_domain[
                    "target_work_items"
                ],
                "artifacts": [],
                "semantic_verification": "accepted",
                "full_source_campaign": True,
                "lean_atom_discharged": False,
            }
            with self.assertRaisesRegex(CampaignError, "sample can never"):
                validate_status(
                    status,
                    plan=plan,
                    plan_sha256=canonical_sha256(plan),
                    profile=profile,
                )

    def test_workspace_verification_checks_artifact_bytes_but_not_semantics(self) -> None:
        profile = self.registry.by_id["cdem-table-abel"]
        diagnosis = doctor_profile(profile, {})
        if not diagnosis["prerequisites_available"]:
            self.skipTest("g++ is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = create_plan(self.registry, profile, {}, workspace=workspace)
            plan_hash = write_immutable_json(workspace / "plan.json", plan)
            artifact = workspace / "receipt.txt"
            artifact.write_bytes(b"external producer output\n")
            raw = artifact.read_bytes()
            status = {
                "schema_version": 1,
                "kind": STATUS_KIND,
                "atom_id": profile.atom_id,
                "profile_sha256": profile.profile_sha256,
                "plan_sha256": plan_hash,
                "state": "execution_complete",
                "scope": "full_source",
                "sample": False,
                "covered_lower": profile.full_source_domain["lower"],
                "covered_upper": profile.full_source_domain["lower"],
                "covered_work_items": 0,
                "artifacts": [
                    {
                        "path": "receipt.txt",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                        "role": "producer_stdout",
                    }
                ],
                "semantic_verification": "not_run",
                "full_source_campaign": False,
                "lean_atom_discharged": False,
            }
            atomic_write_json(workspace / "status.json", status)
            result = verify_workspace(workspace, self.registry)
            self.assertTrue(result["accepted"])
            self.assertFalse(result["semantic_result_replayed"])
            self.assertFalse(result["full_source_campaign_verified_by_this_command"])
            self.assertFalse(result["lean_atom_discharged"])
            artifact.write_bytes(b"changed\n")
            with self.assertRaisesRegex(CampaignError, "does not match"):
                verify_workspace(workspace, self.registry)

    def test_missing_workspace_is_explicitly_not_planned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = workspace_status(Path(directory), self.registry)
        self.assertEqual(result["state"], "not_planned")
        self.assertFalse(result["full_source_campaign"])
        self.assertFalse(result["lean_atom_discharged"])


class CampaignIOTests(unittest.TestCase):
    def test_immutable_write_is_idempotent_and_refuses_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            first = write_immutable_json(path, {"b": 2, "a": 1})
            second = write_immutable_json(path, {"a": 1, "b": 2})
            self.assertEqual(first, second)
            self.assertEqual(path.read_bytes(), b'{"a":1,"b":2}\n')
            with self.assertRaisesRegex(CampaignIOError, "different bytes"):
                write_immutable_json(path, {"a": 2, "b": 2})

    def test_canonical_loader_rejects_pretty_equivalent_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text('{\n  "a": 1\n}\n', encoding="utf-8")
            self.assertEqual(load_json(path), {"a": 1})
            with self.assertRaisesRegex(CampaignIOError, "not in canonical form"):
                load_json(path, require_canonical=True)


class CampaignCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_capability_reports_exactly_thirteen_without_completion(self) -> None:
        completed = self.run_cli("capability")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(value["profile_count"], 13)
        self.assertEqual(value["full_source_campaigns_completed"], 0)
        self.assertEqual(value["lean_atoms_discharged"], 0)

    def test_dirichlet_plan_without_q1_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_cli(
                "plan",
                "platt-dirichlet-theorem-7-1",
                "--workspace",
                directory,
            )
        self.assertEqual(completed.returncode, 2)
        value = json.loads(completed.stdout)
        self.assertFalse(value["accepted"])
        self.assertFalse(value["full_source_campaign"])
        self.assertFalse(value["lean_atom_discharged"])

    def test_status_missing_workspace_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_cli("status", directory)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(value["state"], "not_planned")
        self.assertFalse(value["full_source_campaign"])


if __name__ == "__main__":
    unittest.main()
