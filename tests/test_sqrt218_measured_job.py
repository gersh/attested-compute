# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "tools", ROOT / "azure"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import build_sqrt218_measured_job as builder  # noqa: E402
from create_run_bundle import canonical_json_bytes, canonical_sha256  # noqa: E402
from measured_runner import _closure_manifest, validate_job_spec  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    azure_measured_worker_environment,
    canonical_json_bytes as corpus_json_bytes,
)
from tg_verifier.numeric_corpus import (  # noqa: E402
    PAYLOAD_ROOT_HASH_DOMAIN,
    SOURCE_ROOT_HASH_DOMAIN,
    payload_root_sha256,
    source_root_sha256,
    statement_sha256,
)
from tg_verifier.sqrt218_certificate import produce_certificate_bytes  # noqa: E402
from tg_verifier.sqrt218_contract import (  # noqa: E402
    CORPUS_CLAIM_ID,
    CORPUS_COMMITMENTS,
    CORPUS_COVERAGE_ID,
    CORPUS_ENCODING,
    CORPUS_ID,
    CORPUS_PARAMETERS,
    CORPUS_ROLE,
    LEAN_CLAIM,
    SOURCE_STATEMENT,
)


class Sqrt218MeasuredJobTests(unittest.TestCase):
    def _sample_corpus(self, root: Path) -> tuple[Path, Path]:
        snapshot = root / "snapshot"
        payload_path = "corpus/payloads/sample-archive.json"
        source_path = "corpus/src/sample-producer.py"
        manifest_path = "corpus/manifest.json"
        payload_raw = produce_certificate_bytes(64)
        source_raw = b"#!/usr/bin/env python3\n# sample-only corpus source\n"
        payload = {
            "coverage_id": CORPUS_COVERAGE_ID,
            "encoding": CORPUS_ENCODING,
            "index_start": 0,
            "index_stop": 1,
            "path": payload_path,
            "role": CORPUS_ROLE,
            "row_count": 1,
            "sha256": hashlib.sha256(payload_raw).hexdigest(),
            "size_bytes": len(payload_raw),
        }
        source = {
            "executable": True,
            "path": source_path,
            "role": "sample_generator",
            "sha256": hashlib.sha256(source_raw).hexdigest(),
            "size_bytes": len(source_raw),
        }
        manifest = {
            "claim": {
                "claim_id": CORPUS_CLAIM_ID,
                "claim_version": 1,
                "lean_theorem": LEAN_CLAIM,
                "lean_type": LEAN_CLAIM,
                "statement": SOURCE_STATEMENT,
                "statement_encoding": "utf8-exact-v1",
                "statement_sha256": statement_sha256(SOURCE_STATEMENT),
            },
            "corpus_id": CORPUS_ID,
            "corpus_version": 1,
            "coverage": [
                {
                    "axis": "certificate_archive",
                    "coverage_id": CORPUS_COVERAGE_ID,
                    "index_start": 0,
                    "index_stop": 1,
                    "role": CORPUS_ROLE,
                }
            ],
            "kind": "sparkinterval.numeric_corpus_manifest.v1",
            "parameters": CORPUS_PARAMETERS,
            "payload_prefix": "corpus/payloads",
            "payload_root": {
                "file_count": 1,
                "hash_domain": PAYLOAD_ROOT_HASH_DOMAIN,
                "sha256": payload_root_sha256([payload]),
                "total_size_bytes": len(payload_raw),
            },
            "payloads": [payload],
            "schema_version": 1,
            "semantic_commitments": [
                {"hash_domain": domain, "name": name, "sha256": digest}
                for name, domain, digest in CORPUS_COMMITMENTS
            ],
            "source_files": [source],
            "source_root": {
                "file_count": 1,
                "hash_domain": SOURCE_ROOT_HASH_DOMAIN,
                "sha256": source_root_sha256([source]),
                "total_size_bytes": len(source_raw),
            },
        }
        manifest_raw = corpus_json_bytes(manifest)
        for relative, raw, mode in (
            (payload_path, payload_raw, 0o444),
            (source_path, source_raw, 0o555),
            (manifest_path, manifest_raw, 0o444),
        ):
            path = snapshot / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(mode)
        for directory in sorted(
            [snapshot, *(path for path in snapshot.rglob("*") if path.is_dir())],
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o555)
        pin = {
            "expected": {
                "claim_id": CORPUS_CLAIM_ID,
                "claim_version": 1,
                "corpus_id": CORPUS_ID,
                "corpus_version": 1,
                "payload_file_count": 1,
                "payload_root_sha256": manifest["payload_root"]["sha256"],
                "payload_total_size_bytes": len(payload_raw),
                "source_root_sha256": manifest["source_root"]["sha256"],
                "statement_sha256": manifest["claim"]["statement_sha256"],
            },
            "kind": "sparkinterval.pinned_numeric_corpus.v1",
            "pin_id": "sqrt218.sample.invalid-production-data",
            "repository": {
                "commit": "1" * 40,
                "manifest_path": manifest_path,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "manifest_size_bytes": len(manifest_raw),
                "url": "https://example.com/sqrt218-sample-corpus.git",
            },
            "schema_version": 1,
        }
        pin_path = root / "sample-pin.json"
        pin_path.write_bytes(corpus_json_bytes(pin))
        return pin_path, snapshot

    def test_development_materialization_is_closed_but_non_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sqrt218-job"
            report = builder.build(
                root,
                allow_full_recomputation_job=True,
            )
            job_raw = (root / "job.json").read_bytes()
            job = json.loads(job_raw)
            self.assertFalse(report["accepted"])
            self.assertFalse(report["lean_registry_admission"])
            self.assertFalse(report["production_receipt_present"])
            self.assertEqual(report["input_mode"], "full_recomputation")
            self.assertEqual(job["backend"], "azure_sevsnp_cpu")
            self.assertIsNone(job["gpu_pre_run_gate"])
            self.assertEqual(
                job["command"]["environment"],
                {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            )
            self.assertEqual(
                job["input_artifact"]["sha256"],
                "17d1c5328bd05b4883670f33823cd218dd1f32e53bad51c9a5c96bec5e06d178",
            )
            self.assertEqual(
                job["parameters"]["canonical_sha256"],
                "389a9a946df89008639edffb01f66f34ffdf86ace00098791bac81c774d9c502",
            )
            self.assertEqual(
                job["domain_coverage"]["canonical_sha256"],
                "44ba1f2b13b8cdbb3422d1ca674d95531e6c6ffe4e07652a969652d9c0ac120f",
            )
            self.assertEqual(job["output_contract"]["format"], "opaque_bytes_v1")
            self.assertEqual(job["work_trace_contract"]["expected_iterations"], 2_000_000)
            self.assertEqual(
                job["work_trace_contract"]["verification_mode"],
                "pinned_external_trace_verifier_v1",
            )
            validate_job_spec(job)

            files = job["artifact_closure"]["files"]
            self.assertEqual(
                canonical_sha256(_closure_manifest(files)),
                job["artifact_closure"]["manifest_sha256"],
            )
            self.assertEqual(
                len([row for row in files if row["statement_role"] == "host_executable"]),
                1,
            )
            roles = {row["statement_role"] for row in files}
            self.assertIn("operational_state_machine", roles)
            self.assertIn("known_answer_tests", roles)
            self.assertIn("translation_validation_plan", roles)
            for row in files:
                raw = (root / row["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["sha256"])
                self.assertEqual(len(raw), row["size_bytes"])

            plan = json.loads(
                (root / "provenance/translation-validation-plan.json").read_bytes()
            )
            self.assertFalse(plan["binary_refinement_proved"])
            self.assertFalse(plan["source_to_operational_ir_proved"])

            completed = subprocess.run(
                [str(root / job["command"]["argv"][0]), "--help"],
                cwd=root,
                env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())

    def test_full_recomputation_job_is_not_the_materializer_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "must-not-exist"
            with self.assertRaisesRegex(
                builder.Sqrt218BuildError,
                "--emit-full-recomputation-job",
            ):
                builder.build(root)
            self.assertFalse(root.exists())

    def test_materializer_cli_requires_explicit_cloud_only_job_emission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "must-not-exist"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/build_sqrt218_measured_job.py"),
                    "--output-root",
                    str(root),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b"--emit-full-recomputation-job", completed.stdout)
            self.assertFalse(root.exists())

            help_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/build_sqrt218_measured_job.py"),
                    "--help",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(help_result.returncode, 0)
            self.assertIn(b"cloud-only bound-2,000,000", help_result.stdout)

    def test_production_policy_cannot_build_without_a_real_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            policy = json.loads(builder.DEVELOPMENT_POLICY.read_bytes())
            policy["classification"] = "production"
            policy["policy_id"] = "sparkinterval.test.production.v1"
            policy["production_ready"] = True
            policy_path = temporary_root / "production-policy.json"
            policy_path.write_bytes(canonical_json_bytes(policy))
            with self.assertRaisesRegex(
                builder.Sqrt218BuildError,
                "requires a reviewed numeric-corpus",
            ):
                builder.build(
                    temporary_root / "job",
                    runner_policy_path=policy_path,
                )

    def test_corpus_pin_and_snapshot_are_an_atomic_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(builder.Sqrt218BuildError, "supplied together"):
                builder.build(
                    root / "job",
                    numeric_corpus_pin=root / "pin.json",
                )

    def test_corpus_mode_binds_the_pin_and_rejects_a_sample_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pin, snapshot = self._sample_corpus(root)
            job_root = root / "job"
            report = builder.build(
                job_root,
                numeric_corpus_pin=pin,
                numeric_corpus_snapshot=snapshot,
            )
            self.assertEqual(report["input_mode"], "verified_numeric_corpus")
            job = json.loads((job_root / "job.json").read_bytes())
            self.assertEqual(
                (job_root / job["input_artifact"]["path"]).read_bytes(),
                pin.read_bytes(),
            )
            self.assertIn(
                "--numeric-corpus-snapshot",
                job["command"]["argv"],
            )
            argv = [
                {
                    "@challenge@": "2" * 64,
                    "@job_binding@": "3" * 64,
                    "@input@": job["input_artifact"]["path"],
                    "@output@": job["output_contract"]["path"],
                    "@trace@": job["work_trace_contract"]["path"],
                }.get(argument, argument)
                for argument in job["command"]["argv"]
            ]
            completed = subprocess.run(
                argv,
                cwd=job_root,
                env=job["command"]["environment"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b"cloud-only", completed.stderr)
            self.assertFalse((job_root / job["output_contract"]["path"]).exists())

            measured_environment = azure_measured_worker_environment(
                job["command"]["environment"],
                backend="azure_sevsnp_cpu",
                challenge_nonce="2" * 64,
                job_binding="3" * 64,
            )
            completed = subprocess.run(
                argv,
                cwd=job_root,
                env=measured_environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b"selected profile", completed.stderr)
            self.assertFalse((job_root / job["output_contract"]["path"]).exists())


if __name__ == "__main__":
    unittest.main()
