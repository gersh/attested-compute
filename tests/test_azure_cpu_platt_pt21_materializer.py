# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from attestation.measured_run_archive import create_archive, extract_archive
from tg_verifier.azure_cpu_platt_pt21_materializer import (
    _MerkleAccumulator,
)
import tg_verifier.azure_cpu_platt_pt21_materializer as materializer
from tg_verifier.azure_cpu_platt_pt21_workload_factory import (
    CAMPAIGN_ID,
    CONTRACT_FILE_SHA256,
    PHASE_COMMANDS,
    PHASE_COUNTS,
    PHASE_DEPENDENCIES,
    REFERENCE_CONTRACT_ID,
    REGISTERED_INVOCATION,
    SHARD_COUNT,
    SOURCE_PATHS,
    execution_contract,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
    production_capability_complete,
    source_reviewed_materializer_available,
)
from tg_verifier.campaign_io import canonical_json_bytes, hash_file_once
from tests.azure_measured_worker_test_scope import measured_worker_test_scope
from tg_verifier.platt_zeta_campaign import (
    UPSTREAM_MANIFEST_SHA256,
    _merkle_root,
    _validate_upstream,
    PlattZetaCampaignError,
)


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import generate_trusted_compute_lean as lean_registry  # noqa: E402
import tg_platt_pt21_azure_measured_workload as workload  # noqa: E402


EXECUTION_SCHEMA = (
    ROOT / "schemas/platt-pt21-azure-execution-contracts.schema.json"
)
EXECUTION_CONTRACTS = (
    ROOT / "specifications/PLATT_PT21_AZURE_EXECUTION_CONTRACTS.json"
)
SITE_SCHEMA = (
    ROOT / "schemas/azure-cpu-platt-pt21-materializer-site.schema.json"
)
SITE_EXAMPLE = (
    ROOT
    / "examples/trusted-compute/"
    "azure_cpu_platt_pt21_materializer_site.redacted.json"
)
RUNTIME_SCHEMA = (
    ROOT / "schemas/azure-cpu-platt-pt21-runtime-closure.schema.json"
)
MATERIALIZATION_SCHEMA = (
    ROOT / "schemas/azure-cpu-platt-pt21-materialization.schema.json"
)


def group(phase: str) -> dict[str, object]:
    terminal = phase == "finalize-merkle-certificate"
    return {
        "backend_class": "cpu_flint_sidecar",
        "campaign_id": CAMPAIGN_ID,
        "command_template": list(PHASE_COMMANDS[phase]),
        "depends_on": list(PHASE_DEPENDENCIES[phase]),
        "group_id": f"{CAMPAIGN_ID}::{phase}",
        "operator_adapter": "azure/cpu_production_orchestrator.py",
        "owner_atom_id": CAMPAIGN_ID,
        "phase_id": phase,
        "receipt_backend": "azure_sevsnp_cpu",
        "semantic_binding": None,
        "shard_count": PHASE_COUNTS[phase],
        "terminal": terminal,
    }


def empty_handoff(root: Path) -> Path:
    expanded = root / "empty-handoff"
    expanded.mkdir()
    manifest = {
        "entry": None,
        "file_count": 0,
        "kind": workload.HANDOFF_KIND,
        "mode": "empty",
        "schema_version": 1,
        "shard_coverage": None,
        "target_phase": "initialize",
        "target_shard_index": 0,
        "total_bytes": 0,
        "tree_sha256": hashlib.sha256(
            workload.HANDOFF_TREE_DOMAIN
        ).hexdigest(),
    }
    (expanded / "handoff.json").write_bytes(canonical_json_bytes(manifest))
    archive = root / "empty-handoff.tar"
    create_archive(expanded, archive)
    return archive


class PT21FactoryTests(unittest.TestCase):
    def test_contract_is_exact_and_optimized_route_stays_refused(self) -> None:
        self.assertEqual(
            hash_file_once(EXECUTION_CONTRACTS)[0], CONTRACT_FILE_SHA256
        )
        reference = execution_contract(REFERENCE_CONTRACT_ID)
        optimized = execution_contract("optimized-h100-windowed-v2")
        self.assertTrue(production_capability_complete(reference))
        self.assertFalse(production_capability_complete(optimized))
        self.assertFalse(
            reference["capability"]["under_one_week_and_10000_usd"]
        )
        self.assertFalse(
            optimized["capability"]["under_one_week_and_10000_usd"]
        )
        self.assertFalse(
            optimized["capability"]["production_materializer_allowed"]
        )
        self.assertTrue(optimized["capability"]["finalizer_complete"])
        self.assertTrue(
            optimized["capability"]["retained_export_replay_complete"]
        )
        self.assertFalse(optimized["capability"]["worker_complete"])
        self.assertEqual(
            optimized["finalizer_interface"]["native_record_wire"],
            "PT21BLK1",
        )
        self.assertEqual(
            optimized["finalizer_interface"]["native_record_adapter"],
            "tg_verifier/platt_pt21_native_record_adapter.py",
        )

    def test_five_groups_preserve_full_formulaic_coverage(self) -> None:
        self.assertEqual(
            list(PHASE_COUNTS.items()),
            [
                ("initialize", 1),
                ("exact-multiplicity-count", 1),
                ("ordinary-low-index-prefix", 1),
                ("platt-turing-index-shards", 1_236_316),
                ("finalize-merkle-certificate", 1),
            ],
        )
        for phase, count in PHASE_COUNTS.items():
            reviewed = group(phase)
            self.assertTrue(source_reviewed_materializer_available(reviewed))
            first = factory_for_portfolio_group(reviewed, 0)
            last = factory_for_portfolio_group(reviewed, count - 1)
            self.assertIsNotNone(first)
            self.assertIsNotNone(last)
            assert first is not None
            self.assertEqual(first.shard_count, count)
            self.assertEqual(first.terminal, phase == "finalize-merkle-certificate")
        shard = make_factory(
            "platt-turing-index-shards", SHARD_COUNT - 1
        )
        self.assertEqual(shard.domain["first_index"], 12_363_150_010_000)
        self.assertEqual(
            shard.domain["upper_exclusive"], 12_363_153_437_140
        )
        self.assertEqual(shard.timeout_seconds, 44 * 60 * 60)
        self.assertGreater(
            48 * 60 * 60,
            shard.timeout_seconds + 3 * 60 * 60,
        )
        terminal = make_factory("finalize-merkle-certificate", 0)
        self.assertEqual(terminal.registered_invocation, REGISTERED_INVOCATION)

    def test_route_gate_is_constant_time_and_tampering_fails(self) -> None:
        reviewed = group("platt-turing-index-shards")
        import tg_verifier.azure_cpu_platt_pt21_workload_factory as module

        with mock.patch.object(
            module,
            "factory_for_portfolio_group",
            wraps=module.factory_for_portfolio_group,
        ) as checked:
            self.assertTrue(module.source_reviewed_materializer_available(reviewed))
        self.assertEqual(checked.call_count, 2)

        for field, value in (
            ("shard_count", SHARD_COUNT - 1),
            ("backend_class", "h100_cuda"),
            ("terminal", True),
        ):
            changed = dict(reviewed)
            changed[field] = value
            self.assertFalse(source_reviewed_materializer_available(changed))
        changed = dict(reviewed)
        changed["command_template"] = [
            *reviewed["command_template"],
            "--accept-partial",
        ]
        self.assertFalse(source_reviewed_materializer_available(changed))

    def test_registered_terminal_hashes_match_lean_registry(self) -> None:
        expected = lean_registry.registered_invocation_expected(
            REGISTERED_INVOCATION
        )
        self.assertEqual(
            {
                key: expected[key]
                for key in expected_registered_hashes()
            },
            expected_registered_hashes(),
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(expected["target"], "azure_sevsnp_cpu")

    def test_streaming_merkle_matches_campaign_finalizer(self) -> None:
        for count in tuple(range(1, 70)) + (127, 128, 129, 1023):
            leaves = [
                hashlib.sha256(f"leaf:{index}".encode()).hexdigest()
                for index in range(count)
            ]
            accumulator = _MerkleAccumulator()
            for leaf in leaves:
                accumulator.add(leaf)
            self.assertEqual(accumulator.count, count)
            self.assertEqual(accumulator.root(), _merkle_root(leaves))

    def test_current_flint_manifest_pin_and_tracked_tree_fail_closed(self) -> None:
        raw = (
            ROOT / "specifications/FLINT_3_6_PLATT_UPSTREAM.json"
        ).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), UPSTREAM_MANIFEST_SHA256)
        _validate_upstream(raw)
        changed = json.loads(raw)
        changed["tracked_tree_sha256"] = "0" * 64
        changed_raw = json.dumps(changed, indent=2).encode() + b"\n"
        with self.assertRaisesRegex(
            PlattZetaCampaignError, "manifest bytes"
        ):
            _validate_upstream(changed_raw)
        import tg_verifier.platt_zeta_campaign as campaign

        with mock.patch.object(
            campaign,
            "UPSTREAM_MANIFEST_SHA256",
            hashlib.sha256(changed_raw).hexdigest(),
        ):
            with self.assertRaisesRegex(
                PlattZetaCampaignError, "tracked source-tree"
            ):
                campaign._validate_upstream(changed_raw)


class PT21MaterializerAuthenticationTests(unittest.TestCase):
    def _fixture(
        self, root: Path
    ) -> tuple[object, dict[str, object], Path, dict[str, object]]:
        retained = root / "retained/initialize"
        retained.mkdir(parents=True)
        export = retained / "0000000.tar"
        export.write_bytes(b"retained-export")
        factory = make_factory("initialize", 0)
        operational = {
            "execution_contract_sha256": CONTRACT_FILE_SHA256,
            "kind": workload.OPERATIONAL_RESULT_KIND,
            "phase_id": "initialize",
            "retained_export_sha256": hashlib.sha256(
                b"retained-export"
            ).hexdigest(),
            "retained_export_size_bytes": len(b"retained-export"),
            "retained_tree_sha256": "3" * 64,
            "schema_version": 1,
            "shard_index": 0,
        }
        result = canonical_json_bytes(operational).decode().rstrip("\n")
        receipt = {
            "backend": materializer.cpu_operator.BACKEND,
            "claim": {
                "algorithm_hash": hashlib.sha256(
                    factory.algorithm_definition.encode()
                ).hexdigest(),
                "algorithm_id": factory.algorithm_id,
                "domain_hash": materializer.canonical_sha256(
                    factory.domain
                ),
                "input_hash": hashlib.sha256(
                    factory.input_bytes
                ).hexdigest(),
                "output_hash": hashlib.sha256(result.encode()).hexdigest(),
                "parameters_hash": materializer.canonical_sha256(
                    factory.parameters
                ),
                "result": result,
            },
            "receipt_sha256": "4" * 64,
        }
        context = SimpleNamespace(
            verifier_key_manifest=root / "keys.json"
        )
        return context, receipt, export, factory

    def test_signed_predecessor_identity_and_export_are_both_required(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, receipt, export, _factory = self._fixture(root)
            paths = {
                "receipt": root / "receipt.json",
                "task_id": root / "initialize-task",
            }
            state = {
                "records": {
                    "initialize-task": {
                        "stage": "verified_receipt_recorded"
                    }
                }
            }
            with (
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_group",
                    return_value=group("initialize"),
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_task_paths",
                    return_value=paths,
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_validate_task_record",
                ),
                mock.patch.object(
                    materializer,
                    "load_verified_receipt",
                    return_value=receipt,
                ) as verified,
                mock.patch.object(
                    materializer,
                    "verify_retained_export_archive",
                ),
            ):
                row = materializer._verified_predecessor(
                    context,
                    state,
                    group_id=f"{CAMPAIGN_ID}::initialize",
                    phase="initialize",
                    shard_index=0,
                    retained_root=root / "retained",
                )
                self.assertEqual(
                    row["portfolio_receipt_sha256"], "4" * 64
                )
                verified.assert_called_once_with(
                    paths["receipt"],
                    key_manifest=context.verifier_key_manifest,
                )

                export.chmod(0o600)
                export.write_bytes(b"substituted-export")
                with self.assertRaisesRegex(
                    materializer.PT21MaterializerError,
                    "differs from its signed result",
                ):
                    materializer._verified_predecessor(
                        context,
                        state,
                        group_id=f"{CAMPAIGN_ID}::initialize",
                        phase="initialize",
                        shard_index=0,
                        retained_root=root / "retained",
                    )

    def test_incomplete_or_wrong_job_receipt_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, receipt, _export, _factory = self._fixture(root)
            paths = {
                "receipt": root / "receipt.json",
                "task_id": root / "initialize-task",
            }
            incomplete = {
                "records": {
                    "initialize-task": {"stage": "job_succeeded"}
                }
            }
            with (
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_group",
                    return_value=group("initialize"),
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_task_paths",
                    return_value=paths,
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_validate_task_record",
                ),
            ):
                with self.assertRaisesRegex(
                    materializer.PT21MaterializerError,
                    "receipt is incomplete",
                ):
                    materializer._verified_predecessor(
                        context,
                        incomplete,
                        group_id=f"{CAMPAIGN_ID}::initialize",
                        phase="initialize",
                        shard_index=0,
                        retained_root=root / "retained",
                    )

            wrong = json.loads(json.dumps(receipt))
            wrong["claim"]["algorithm_id"] = "substituted-worker"
            complete = {
                "records": {
                    "initialize-task": {
                        "stage": "verified_receipt_recorded"
                    }
                }
            }
            with (
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_group",
                    return_value=group("initialize"),
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_task_paths",
                    return_value=paths,
                ),
                mock.patch.object(
                    materializer.azure_portfolio,
                    "_validate_task_record",
                ),
                mock.patch.object(
                    materializer,
                    "load_verified_receipt",
                    return_value=wrong,
                ),
            ):
                with self.assertRaisesRegex(
                    materializer.PT21MaterializerError,
                    "not the reviewed phase job",
                ):
                    materializer._verified_predecessor(
                        context,
                        complete,
                        group_id=f"{CAMPAIGN_ID}::initialize",
                        phase="initialize",
                        shard_index=0,
                        retained_root=root / "retained",
                    )


class PT21MeasuredWorkloadTests(unittest.TestCase):
    def test_initialize_run_and_independent_trace_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = empty_handoff(root)
            factory = make_factory("initialize", 0)
            input_path = root / "input"
            input_path.write_bytes(factory.input_bytes)
            args = argparse.Namespace(
                phase="initialize",
                shard_index=0,
                algorithm_id=factory.algorithm_id,
                challenge="1" * 64,
                job_binding="2" * 64,
                input=input_path,
                handoff=handoff,
                output=root / "output",
                trace=root / "trace",
                work=root / "work",
                runner=Path("/bin/true"),
                runner_source=ROOT / "reference/tg_platt_zeta_shard.cpp",
                upstream_manifest=(
                    ROOT
                    / "specifications/FLINT_3_6_PLATT_UPSTREAM.json"
                ),
            )
            with measured_worker_test_scope(args):
                workload.run(args)
                workload.verify_trace(args)
            archive = root / "work" / workload.RETAINED_ARCHIVE
            with tempfile.TemporaryDirectory() as expanded:
                manifest = workload._extract_export(
                    archive, Path(expanded) / "export", "initialize", 0
                )
            self.assertEqual(manifest["file_count"], 4)
            self.assertEqual(
                manifest["execution_contract_sha256"],
                CONTRACT_FILE_SHA256,
            )

    def test_retained_export_payload_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = empty_handoff(root)
            factory = make_factory("initialize", 0)
            input_path = root / "input"
            input_path.write_bytes(factory.input_bytes)
            args = argparse.Namespace(
                phase="initialize",
                shard_index=0,
                algorithm_id=factory.algorithm_id,
                challenge="3" * 64,
                job_binding="4" * 64,
                input=input_path,
                handoff=handoff,
                output=root / "output",
                trace=root / "trace",
                work=root / "work",
                runner=Path("/bin/true"),
                runner_source=ROOT / "reference/tg_platt_zeta_shard.cpp",
                upstream_manifest=(
                    ROOT
                    / "specifications/FLINT_3_6_PLATT_UPSTREAM.json"
                ),
            )
            with measured_worker_test_scope(args):
                workload.run(args)
            archive = root / "work" / workload.RETAINED_ARCHIVE
            expanded = root / "expanded"
            extract_archive(
                archive,
                expanded,
                maximum_files=16,
                maximum_bytes=2 * 1024**3,
            )
            source = expanded / "campaign/captured-tg_platt_zeta_shard.cpp"
            source.chmod(0o600)
            source.write_bytes(source.read_bytes() + b"\n// mutation\n")
            changed = root / "changed.tar"
            create_archive(expanded, changed)
            with self.assertRaisesRegex(
                workload.PT21MeasuredWorkloadError,
                "differs",
            ):
                workload.verify_retained_export_archive(
                    changed,
                    phase="initialize",
                    shard_index=0,
                    tree_sha256=json.loads(
                        (expanded / "export-manifest.json").read_text()
                    )["tree_sha256"],
                )

    def test_terminal_handoff_requires_gap_free_formulaic_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expanded = root / "handoff"
            (expanded / "shards").mkdir(parents=True)
            prefix = expanded / "prefix-state.tar"
            prefix.write_bytes(b"prefix")
            receipt_tree = hashlib.sha256(
                b"sparkinterval/platt-pt21-final-shard-receipt-tree/v1\0"
            )
            for index in range(3):
                relative = f"shards/receipt-{index:07d}.json"
                raw = canonical_json_bytes({"index": index})
                (expanded / relative).write_bytes(raw)
                receipt_tree.update(len(relative.encode()).to_bytes(8, "big"))
                receipt_tree.update(relative.encode())
                receipt_tree.update(len(raw).to_bytes(8, "big"))
                receipt_tree.update(hashlib.sha256(raw).digest())
            entry = {
                "group_id": (
                    f"{CAMPAIGN_ID}::ordinary-low-index-prefix"
                ),
                "path": "prefix-state.tar",
                "phase_id": "ordinary-low-index-prefix",
                "portfolio_receipt_sha256": "1" * 64,
                "sha256": hashlib.sha256(b"prefix").hexdigest(),
                "shard_index": 0,
                "size_bytes": 6,
                "tree_sha256": "2" * 64,
            }
            coverage = {
                "export_identity_merkle_root_sha256": "3" * 64,
                "first_shard_index": 0,
                "portfolio_receipt_merkle_root_sha256": "4" * 64,
                "receipt_tree_sha256": receipt_tree.hexdigest(),
                "shard_count": 3,
                "upper_shard_index_exclusive": 3,
            }
            count, total, tree = workload._tree(
                expanded,
                domain=workload.HANDOFF_TREE_DOMAIN,
                excluded=frozenset({"handoff.json"}),
            )
            manifest = {
                "entry": entry,
                "file_count": count,
                "kind": workload.HANDOFF_KIND,
                "mode": "full-finalization",
                "schema_version": 1,
                "shard_coverage": coverage,
                "target_phase": "finalize-merkle-certificate",
                "target_shard_index": 0,
                "total_bytes": total,
                "tree_sha256": tree,
            }
            (expanded / "handoff.json").write_bytes(
                canonical_json_bytes(manifest)
            )
            archive = root / "handoff.tar"
            create_archive(expanded, archive)
            with mock.patch.object(workload, "SHARD_COUNT", 3):
                checked, extracted = workload._extract_handoff(
                    archive,
                    root / "checked",
                    "finalize-merkle-certificate",
                    0,
                )
            self.assertEqual(
                checked["shard_coverage"]["shard_count"], 3
            )
            self.assertTrue(extracted.is_dir())

            (expanded / "shards/receipt-0000001.json").unlink()
            count, total, tree = workload._tree(
                expanded,
                domain=workload.HANDOFF_TREE_DOMAIN,
                excluded=frozenset({"handoff.json"}),
            )
            manifest["file_count"] = count
            manifest["total_bytes"] = total
            manifest["tree_sha256"] = tree
            (expanded / "handoff.json").write_bytes(
                canonical_json_bytes(manifest)
            )
            incomplete = root / "incomplete.tar"
            create_archive(expanded, incomplete)
            with mock.patch.object(workload, "SHARD_COUNT", 3):
                with self.assertRaisesRegex(
                    workload.PT21MeasuredWorkloadError,
                    "exactly",
                ):
                    workload._extract_handoff(
                        incomplete,
                        root / "rejected",
                        "finalize-merkle-certificate",
                        0,
                    )


@unittest.skipIf(jsonschema is None, "jsonschema is not installed")
class PT21SchemaTests(unittest.TestCase):
    def test_execution_contract_and_redacted_site_validate(self) -> None:
        jsonschema.Draft202012Validator(
            json.loads(EXECUTION_SCHEMA.read_text())
        ).validate(json.loads(EXECUTION_CONTRACTS.read_text()))
        jsonschema.Draft202012Validator(
            json.loads(SITE_SCHEMA.read_text())
        ).validate(json.loads(SITE_EXAMPLE.read_text()))

    def test_runtime_and_materialization_schemas_are_well_formed(self) -> None:
        jsonschema.Draft202012Validator.check_schema(
            json.loads(RUNTIME_SCHEMA.read_text())
        )
        jsonschema.Draft202012Validator.check_schema(
            json.loads(MATERIALIZATION_SCHEMA.read_text())
        )


class PT21SourceClosureTests(unittest.TestCase):
    def test_measured_worker_runs_from_declared_source_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in SOURCE_PATHS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(package / "tools/tg_platt_pt21_azure_measured_workload.py"),
                    "--help",
                ],
                cwd=package,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
