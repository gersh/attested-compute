# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tests.test_tg_dirichlet_booker_smallq_compact_v3 import _write_fixture
from tests.azure_measured_worker_test_scope import measured_worker_test_scope
from tg_verifier import azure_h100_dirichlet_packed_materializer as packed_materializer
from tg_verifier import dirichlet_booker_smallq as smallq
from tg_verifier import dirichlet_booker_smallq_compact_v3 as compact_adapter
from tg_verifier import dirichlet_booker_smallq_packed_stream_v1 as packed
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact_v3
from tg_verifier import azure_cpu_dirichlet_workload_factory as factory_module
from tg_verifier.campaign_io import canonical_json_bytes, canonical_sha256


ROOT = Path(__file__).resolve().parents[1]


def load_workload_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_prover_dirichlet_azure_packed_workload",
        ROOT / "tools/tg_dirichlet_azure_measured_workload.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workload = load_workload_module()


def _write(path: Path, raw: bytes, mode: int = 0o400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


class DirichletAzurePackedWorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_temporary = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_temporary.name)
        (
            cls.plan,
            cls.batches,
            cls.control,
            cls.control_receipt,
            _raw,
            bounded_pins,
            _expected,
        ) = _write_fixture(root)
        cls.batch_directory = root / "batches"
        cls.batch_directory.mkdir()
        copied_batches = []
        for batch in cls.batches:
            target = cls.batch_directory / batch.name
            shutil.copyfile(batch, target)
            target.chmod(0o400)
            copied_batches.append(target)
        cls.batches = tuple(copied_batches)
        parameters = smallq.transform_parameters(bounded_pins.q)
        cls.pins = replace(
            bounded_pins,
            stop_t_numerator=(
                parameters.sample_count * compact_v3.SOURCE_SAMPLE_NUMERATOR
            ),
            structural_bounded_span_kat=False,
        )
        pinset_body = {
            "pins": cls.pins.record(),
            "schema": compact_adapter.PINSET_SCHEMA,
            "schema_version": 1,
        }
        cls.pinset = _write(
            root / "pinset.json",
            canonical_json_bytes(
                {
                    **pinset_body,
                    "pinset_sha256": compact_adapter.pinset_sha256(cls.pins),
                }
            ),
        )
        cls.packed_stream, counts = cls._all_ambiguous_stream("host")
        cls.device_packed_stream, device_counts = (
            cls._all_ambiguous_stream("device")
        )
        assert counts == device_counts
        cls.stream_counts = counts
        cls.stream_file = _write(root / "packed.bin", cls.packed_stream)
        cls.device_stream_file = _write(
            root / "packed-device.bin", cls.device_packed_stream
        )
        runner_source = (
            "#!/usr/bin/python3\n"
            "import hashlib,json,pathlib,sys\n"
            "device='--strict-sign-packed-device' in sys.argv\n"
            f"p=pathlib.Path({str(cls.device_stream_file)!r} if device "
            f"else {str(cls.stream_file)!r})\n"
            "raw=p.read_bytes()\n"
            "sys.stdout.buffer.write(raw)\n"
            "sys.stdout.buffer.flush()\n"
            "location='device' if device else 'host'\n"
            "algorithm=('platt-booker-smallq-runner-strict-sign-pack-device-v1' "
            f"if device else {packed.PACKER_ALGORITHM_ID!r})\n"
            "report={"
            "'algorithm':algorithm,"
            "'classification':'transport_not_source_or_dft_replay',"
            "'packing_location':location,'packing_mode':3 if device else 1,"
            f"'frames':{counts['frames']},'items':{counts['items']},"
            f"'ambiguous':{counts['items']},'negative':0,'positive':0,"
            "'bytes':len(raw),'stream_sha256':hashlib.sha256(raw).hexdigest(),"
            "'control_upload_nanoseconds':0,"
            "'device_classification_nanoseconds':0,"
            "'device_to_host_transfer_nanoseconds':0,"
            f"'device_to_host_payload_bytes':{counts['payload_bytes']} "
            "if device else 0,"
            f"'device_to_host_bounded_status_bytes':{counts['bounded_status_bytes']} "
            "if device else 0,"
            f"'full_disk_status_array_bytes_not_copied':{counts['full_array_bytes']} "
            "if device else 0,"
            "'source_admission_enabled':False,"
            "'dft_arithmetic_containment_replayed':False,"
            "'zero_multiplicity_realized':False,"
            "'turing_closure_realized':False,'production_ready':False}\n"
            "sys.stderr.write(json.dumps(report,separators=(',',':'))+'\\n')\n"
        ).encode("utf-8")
        cls.runner = _write(root / "runner", runner_source, 0o500)
        cls.runner_source = _write(root / "runner-source.py", runner_source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temporary.cleanup()

    @classmethod
    def _all_ambiguous_stream(
        cls, packing_location: str
    ) -> tuple[bytes, dict[str, int]]:
        prepared = packed._prepare(
            cls.plan,
            cls.batches,
            cls.control,
            cls.control_receipt,
            cls.pins,
        )
        stream = bytearray()
        stream_digest = hashlib.sha256()
        previous = packed.ZERO_DIGEST
        items = 0
        payload_bytes = 0
        full_array_bytes = 0
        for ordinal, batch in enumerate(prepared.batches):
            butterflies = (
                len(batch.characters)
                * (prepared.plan.transform_length // 2)
                * (prepared.plan.transform_length.bit_length() - 1)
            )
            prefix, binding, digests = packed._frame_bytes(
                prepared,
                batch,
                terms=0,
                butterflies=butterflies,
                elapsed=0,
                previous_frame=previous,
                packing_location=packing_location,
            )
            frame_items = len(batch.characters) * prepared.sample_count
            payload = b"\x00" * ((frame_items + 3) // 4)
            payload_bytes += len(payload)
            full_array_bytes += (
                len(batch.characters)
                * prepared.plan.transform_length
                * 28
            )
            frame_body = prefix + binding + digests + payload
            frame_sha256 = hashlib.sha256(
                packed.FRAME_DOMAIN + frame_body
            ).digest()
            trailer = packed.FRAME_TRAILER.pack(
                packed.TRAILER_MAGIC,
                packed.FORMAT_VERSION_V1,
                0,
                ordinal,
                len(payload),
                hashlib.sha256(payload).digest(),
                frame_sha256,
            )
            frame = frame_body + trailer
            stream.extend(frame)
            stream_digest.update(frame)
            previous = frame_sha256
            items += frame_items
        end = packed.STREAM_END.pack(
            packed.END_MAGIC,
            packed.FORMAT_VERSION_V1,
            0,
            len(prepared.batches),
            items,
            previous,
            stream_digest.digest(),
        )
        stream.extend(end)
        return bytes(stream), {
            "bounded_status_bytes": 8 * len(prepared.batches),
            "frames": len(prepared.batches),
            "full_array_bytes": full_array_bytes,
            "items": items,
            "payload_bytes": payload_bytes,
        }

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.receipt_path = _write(self.root / "predecessor-receipt.json", b"receipt")
        provisional = SimpleNamespace(
            batch_directory=self.batch_directory,
            control=self.control,
            control_receipt=self.control_receipt,
            input=self.root / "manifest.json",
            pinset=self.pinset,
            plan=self.plan,
            predecessor_receipt=self.receipt_path,
            runner=self.runner,
            runner_source=self.runner_source,
        )
        artifacts, _snapshots, _batches = workload._packed_artifacts(provisional)
        self.manifest = {
            "artifact_roster_sha256": canonical_sha256(artifacts),
            "artifacts": artifacts,
            "compact_source_binding_sha256": (
                compact_adapter._source_binding_sha256(self.pins)
            ),
            "dft_arithmetic_containment_realized": False,
            "full_source_span": True,
            "kind": workload.PACKED_INPUT_KIND,
            "packing_location": workload.HOST_PACKING_LOCATION,
            "packing_mode": workload.PACKING_MODE,
            "pinset_sha256": compact_adapter.pinset_sha256(self.pins),
            "production_ready": False,
            "q": self.pins.q,
            "schema_version": 1,
            "source_admission_enabled": False,
            "structural_bounded_span_kat": False,
        }
        self.manifest_path = _write(
            self.root / "manifest.json", canonical_json_bytes(self.manifest)
        )
        self.args = SimpleNamespace(
            algorithm_id=workload.PACKED_PHASE_ALGORITHM_ID,
            batch_directory=self.batch_directory,
            challenge="1" * 64,
            chunk_items=1 << 20,
            control=self.control,
            control_receipt=self.control_receipt,
            input=self.manifest_path,
            job_binding="2" * 64,
            output=self.root / "output.json",
            pinset=self.pinset,
            plan=self.plan,
            predecessor_receipt=self.receipt_path,
            runner=self.runner,
            runner_source=self.runner_source,
            runner_timeout_seconds=120,
            trace=self.root / "trace.json",
            work=self.root / "work",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _receipt(self, manifest: dict[str, object] | None = None) -> dict[str, object]:
        selected = self.manifest if manifest is None else manifest
        manifest_sha = hashlib.sha256(
            canonical_json_bytes(selected)
        ).hexdigest()
        result = workload._packed_predecessor_result(selected, manifest_sha)
        result_raw = canonical_json_bytes(result)
        return {
            "backend": "azure_ncc40ads_h100_v5",
            "claim": {
                "algorithm_hash": hashlib.sha256(
                    workload.PACKED_PREDECESSOR_ALGORITHM_DEFINITION.encode()
                ).hexdigest(),
                "algorithm_id": workload.PACKED_PREDECESSOR_ALGORITHM_ID,
                "completion": "successful",
                "input_hash": manifest_sha,
                "output_hash": hashlib.sha256(result_raw).hexdigest(),
                "result": result_raw.decode("utf-8"),
            },
            "receipt_sha256": "3" * 64,
            "verifier": {"key_id": "production-test-key"},
        }

    def _materializer_site(
        self, manifest_path: Path, output_name: str
    ) -> dict[str, object]:
        runner_policy_path = ROOT / (
            "profiles/measured_runner/development_challenge_first_v1.json"
        )
        nvidia_policy_path = (
            ROOT / "attestation/policies/gpu_prover_h100.rego"
        )
        return {
            "batch_directory": str(self.batch_directory),
            "control": _pin(self.control),
            "control_receipt": _pin(self.control_receipt),
            "gpu_verifier": "/usr/bin/false",
            "input_manifest": _pin(manifest_path),
            "kind": packed_materializer.SITE_KIND,
            "nras_url": "https://nras.example.invalid",
            "nvidia_policy": _pin(nvidia_policy_path),
            "output_root": str(self.root / output_name),
            "pinset": _pin(self.pinset),
            "plan": _pin(self.plan),
            "predecessor_receipt": _pin(self.receipt_path),
            "python": _pin(Path(sys.executable).resolve()),
            "runner": _pin(self.runner),
            "runner_policy": {
                **_pin(runner_policy_path),
                "classification": "production",
                "policy_id": "production-test-policy",
            },
            "runner_source": _pin(self.runner_source),
            "schema_version": 1,
        }

    def _direct_materialize(
        self,
        raw_site: dict[str, object],
        manifest: dict[str, object],
    ) -> dict[str, object]:
        packaged_worker = packed_materializer._workload_module()
        with mock.patch.object(
            packaged_worker,
            "load_verified_receipt",
            return_value=self._receipt(manifest),
        ), mock.patch.object(
            packaged_worker, "require_production_verifier"
        ):
            inputs = packaged_worker._load_packed_inputs(
                packed_materializer._packed_args(raw_site)
            )
            loaded_site = {
                "factory": factory_module.make_packed_phase_factory(
                    inputs["manifest"]
                ),
                "inputs": inputs,
                "output_root": Path(raw_site["output_root"]),
                "site": raw_site,
                "site_pin": {
                    "path": str(self.root / "not-needed-in-direct-test"),
                    "sha256": "0" * 64,
                    "size_bytes": 0,
                },
            }
            return packed_materializer.materialize(loaded_site)

    def test_measured_phase_streams_and_structurally_replays(self) -> None:
        receipt = self._receipt()
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload, "load_verified_receipt", return_value=receipt
        ), mock.patch.object(workload, "require_production_verifier"):
            workload.run_packed_smallq(self.args)
            workload.verify_packed_smallq_trace(self.args)
        result = json.loads(self.args.output.read_bytes())
        self.assertEqual(
            result["packing_location"], workload.HOST_PACKING_LOCATION
        )
        self.assertEqual(result["packing_mode"], workload.PACKING_MODE)
        self.assertEqual(
            result["packed_stream_sha256"],
            hashlib.sha256(self.packed_stream).hexdigest(),
        )
        self.assertEqual(result["item_count"], self.stream_counts["items"])
        self.assertTrue(result["terminal_stream_digest_bound"])
        self.assertFalse(result["raw_disk_device_to_host_transfer_eliminated"])
        self.assertFalse(result["device_side_classification_implemented"])
        self.assertFalse(result["dft_arithmetic_containment_replayed"])
        self.assertFalse(result["zero_multiplicity_realized"])
        self.assertFalse(result["turing_closure_realized"])
        self.assertFalse(result["source_admission_enabled"])
        self.assertFalse(result["external_atom_discharged"])
        self.assertFalse(result["production_ready"])

    def test_factory_is_nonterminal_h100_and_manifest_selects_host_mode(self) -> None:
        factory = factory_module.make_packed_phase_factory(self.manifest)
        self.assertFalse(factory.terminal)
        self.assertIsNone(factory.registered_invocation)
        self.assertEqual(factory.backend, "azure_ncc40ads_h100_v5")
        self.assertEqual(
            factory.parameters["packing_location"],
            workload.HOST_PACKING_LOCATION,
        )
        self.assertEqual(
            factory.command_argv[3], "run-packed-smallq"
        )
        self.assertEqual(
            factory.trace_verifier_argv[3],
            "verify-packed-smallq-trace",
        )
        self.assertEqual(
            factory_module.PACKED_PHASE_ALGORITHM_DEFINITION,
            workload.PACKED_PHASE_ALGORITHM_DEFINITION,
        )
        device = dict(self.manifest)
        device["packing_location"] = workload.DEVICE_PACKING_LOCATION
        device_factory = factory_module.make_packed_phase_factory(device)
        self.assertIn("_h100_device_v1", device_factory.factory_id)
        self.assertEqual(
            device_factory.parameters["runner_packing_stage"],
            "after_full_dft_before_disk_device_to_host_copy",
        )
        changed = dict(device)
        changed["packing_location"] = "runner_device_before_disk_d2h_v1"
        with self.assertRaisesRegex(ValueError, "exact reviewed host/device"):
            factory_module.make_packed_phase_factory(changed)

    def test_device_manifest_selects_device_runner_and_reducer(self) -> None:
        device = dict(self.manifest)
        device["packing_location"] = workload.DEVICE_PACKING_LOCATION
        device_path = _write(
            self.root / "device-manifest.json",
            canonical_json_bytes(device),
        )
        self.args.input = device_path
        receipt = self._receipt(device)
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload, "load_verified_receipt", return_value=receipt
        ), mock.patch.object(workload, "require_production_verifier"):
            inputs = workload._load_packed_inputs(self.args)
            self.assertEqual(
                workload._packed_runner_argv(self.args, inputs)[2],
                "--strict-sign-packed-device",
            )
            workload.run_packed_smallq(self.args)
            workload.verify_packed_smallq_trace(self.args)
        result = json.loads(self.args.output.read_bytes())
        self.assertEqual(
            result["packing_location"], workload.DEVICE_PACKING_LOCATION
        )
        self.assertEqual(
            result["packed_stream_sha256"],
            hashlib.sha256(self.device_packed_stream).hexdigest(),
        )
        self.assertTrue(result["device_side_classification_implemented"])
        self.assertTrue(result["raw_disk_device_to_host_transfer_eliminated"])
        self.assertEqual(
            result["runner_device_to_host_payload_bytes"],
            self.stream_counts["payload_bytes"],
        )
        self.assertFalse(result["dft_arithmetic_containment_replayed"])
        self.assertFalse(result["zero_multiplicity_realized"])
        self.assertFalse(result["turing_closure_realized"])
        self.assertFalse(result["source_admission_enabled"])
        self.assertFalse(result["external_atom_discharged"])
        self.assertFalse(result["production_ready"])

    def test_device_manifest_rejects_host_mode_stream_substitution(self) -> None:
        forced_host_source = self.runner_source.read_text().replace(
            "device='--strict-sign-packed-device' in sys.argv",
            "device=False",
        ).encode("utf-8")
        forced_runner = _write(
            self.root / "forced-host-runner", forced_host_source, 0o500
        )
        forced_source = _write(
            self.root / "forced-host-runner-source.py", forced_host_source
        )
        self.args.runner = forced_runner
        self.args.runner_source = forced_source
        artifacts, _snapshots, _batches = workload._packed_artifacts(self.args)
        device = {
            **self.manifest,
            "artifact_roster_sha256": canonical_sha256(artifacts),
            "artifacts": artifacts,
            "packing_location": workload.DEVICE_PACKING_LOCATION,
        }
        self.args.input = _write(
            self.root / "device-substitution-manifest.json",
            canonical_json_bytes(device),
        )
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload,
            "load_verified_receipt",
            return_value=self._receipt(device),
        ), mock.patch.object(workload, "require_production_verifier"):
            with self.assertRaisesRegex(
                packed.SmallQPackedStreamV1Error,
                "identity, mode, span",
            ):
                workload.run_packed_smallq(self.args)

    def test_h100_materializer_schemas_cli_and_nonterminal_package(self) -> None:
        for relative in (
            "schemas/azure-h100-dirichlet-packed-materializer-site.schema.json",
            "schemas/azure-h100-dirichlet-packed-materialization.schema.json",
        ):
            schema = json.loads((ROOT / relative).read_bytes())
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(schema)
        completed = __import__("subprocess").run(
            [
                sys.executable,
                str(
                    ROOT
                    / "tools/tg_azure_h100_dirichlet_packed_materializer.py"
                ),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("materialize", completed.stdout)

        raw_site = self._materializer_site(
            self.manifest_path, "materialized-host"
        )
        materialized = self._direct_materialize(raw_site, self.manifest)
        self.assertFalse(materialized["accepted"])
        self.assertIsNone(materialized["registered_invocation"])
        self.assertFalse(materialized["source_admission_enabled"])
        self.assertFalse(materialized["production_ready"])
        self.assertFalse(materialized["device_side_classification_implemented"])
        self.assertFalse(
            materialized["raw_disk_device_to_host_transfer_eliminated"]
        )
        job = json.loads(
            Path(materialized["job_spec"]["path"]).read_bytes()
        )
        self.assertEqual(job["backend"], "azure_ncc40ads_h100_v5")
        self.assertEqual(
            job["output_contract"]["path"], "output/phase-result.json"
        )
        self.assertIn("run-packed-smallq", job["command"]["argv"])
        self.assertEqual(
            job["parameters"]["value"]["packing_mode"],
            workload.PACKING_MODE,
        )
        stored_manifest = json.loads(
            Path(materialized["manifest"]).read_bytes()
        )
        self.assertEqual(stored_manifest["job_spec"], materialized["job_spec"])
        self.assertEqual(stored_manifest["package"], materialized["package"])
        schema = json.loads(
            (
                ROOT
                / "schemas/azure-h100-dirichlet-packed-materialization.schema.json"
            ).read_bytes()
        )
        if jsonschema is not None:
            jsonschema.validate(stored_manifest, schema)
        records = {
            row["path"]: row
            for row in job["artifact_closure"]["files"]
        }
        for relative in (
            "profiles/runner-policy.json",
            "profiles/target.json",
            "profiles/trust.json",
        ):
            self.assertIn(relative, records)

    def test_h100_device_materializer_binds_exact_selected_mode(self) -> None:
        device = {
            **self.manifest,
            "packing_location": workload.DEVICE_PACKING_LOCATION,
        }
        device_path = _write(
            self.root / "device-materializer-manifest.json",
            canonical_json_bytes(device),
        )
        raw_site = self._materializer_site(
            device_path, "materialized-device"
        )
        materialized = self._direct_materialize(raw_site, device)
        self.assertTrue(materialized["device_side_classification_implemented"])
        self.assertTrue(
            materialized["raw_disk_device_to_host_transfer_eliminated"]
        )
        self.assertFalse(materialized["source_admission_enabled"])
        self.assertFalse(materialized["production_ready"])
        self.assertIsNone(materialized["registered_invocation"])
        self.assertEqual(
            materialized["packing_location"],
            workload.DEVICE_PACKING_LOCATION,
        )
        job = json.loads(Path(materialized["job_spec"]["path"]).read_bytes())
        self.assertEqual(
            job["parameters"]["value"]["packing_location"],
            workload.DEVICE_PACKING_LOCATION,
        )
        self.assertEqual(
            job["parameters"]["value"]["runner_packing_stage"],
            "after_full_dft_before_disk_device_to_host_copy",
        )
        source_manifest = json.loads(
            (
                Path(materialized["job_spec"]["path"]).parent
                / "source/dirichlet-packed-source-closure.json"
            ).read_bytes()
        )
        self.assertTrue(
            source_manifest["device_side_classification_implemented"]
        )
        self.assertTrue(
            source_manifest[
                "raw_disk_device_to_host_transfer_eliminated"
            ]
        )
        stored_manifest = json.loads(
            Path(materialized["manifest"]).read_bytes()
        )
        schema = json.loads(
            (
                ROOT
                / "schemas/azure-h100-dirichlet-packed-materialization.schema.json"
            ).read_bytes()
        )
        if jsonschema is not None:
            jsonschema.validate(stored_manifest, schema)

    def test_mismatched_predecessor_receipt_is_rejected(self) -> None:
        receipt = self._receipt()
        receipt["claim"]["input_hash"] = "f" * 64
        with mock.patch.object(
            workload, "load_verified_receipt", return_value=receipt
        ), mock.patch.object(workload, "require_production_verifier"):
            with self.assertRaisesRegex(
                workload.DirichletMeasuredWorkloadError,
                "does not authenticate",
            ):
                workload._load_packed_inputs(self.args)

    def test_unreviewed_runner_and_partial_span_are_rejected(self) -> None:
        changed = bytearray(self.runner.read_bytes())
        changed[-1] ^= 1
        self.runner.chmod(0o700)
        self.runner.write_bytes(changed)
        self.runner.chmod(0o500)
        with mock.patch.object(
            workload, "load_verified_receipt", return_value=self._receipt()
        ), mock.patch.object(workload, "require_production_verifier"):
            with self.assertRaisesRegex(
                workload.DirichletMeasuredWorkloadError,
                "artifacts differ",
            ):
                workload._load_packed_inputs(self.args)
        self.runner.chmod(0o700)
        self.runner.write_bytes(self.runner_source.read_bytes())
        self.runner.chmod(0o500)

        partial = dict(self.manifest)
        partial["structural_bounded_span_kat"] = True
        partial_path = _write(
            self.root / "partial.json", canonical_json_bytes(partial)
        )
        self.args.input = partial_path
        with self.assertRaisesRegex(
            workload.DirichletMeasuredWorkloadError,
            "mode, span, or admission",
        ):
            workload._load_packed_inputs(self.args)

    def test_existing_and_symlink_outputs_fail_before_runner(self) -> None:
        self.args.output = _write(self.root / "existing.json", b"{}\n")
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload,
            "_validate_packed_common",
            return_value=("1" * 64, "2" * 64, "4" * 64, {}),
        ), self.assertRaisesRegex(
            workload.DirichletMeasuredWorkloadError,
            "refusing to replace",
        ):
            workload.run_packed_smallq(self.args)
        self.args.output.unlink()
        self.args.output.symlink_to(self.root / "missing-target")
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload,
            "_validate_packed_common",
            return_value=("1" * 64, "2" * 64, "4" * 64, {}),
        ), self.assertRaisesRegex(
            workload.DirichletMeasuredWorkloadError,
            "refusing to replace",
        ):
            workload.run_packed_smallq(self.args)

    def test_trace_digest_substitution_is_rejected(self) -> None:
        receipt = self._receipt()
        with measured_worker_test_scope(
            self.args, backend="azure_ncc40ads_h100_v5"
        ), mock.patch.object(
            workload, "load_verified_receipt", return_value=receipt
        ), mock.patch.object(workload, "require_production_verifier"):
            workload.run_packed_smallq(self.args)
            value = json.loads(self.args.trace.read_bytes())
            value["packed_stream_sha256"] = "f" * 64
            self.args.trace.chmod(0o600)
            self.args.trace.write_bytes(canonical_json_bytes(value))
            self.args.trace.chmod(0o400)
            with self.assertRaisesRegex(
                workload.DirichletMeasuredWorkloadError,
                "trace differs",
            ):
                workload.verify_packed_smallq_trace(self.args)


if __name__ == "__main__":
    unittest.main()
