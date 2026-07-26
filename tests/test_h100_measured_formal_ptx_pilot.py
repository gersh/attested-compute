# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import struct
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


builder = load(
    "gpu_prover_h100_measured_formal_ptx_pilot",
    "tools/build_h100_measured_formal_ptx_pilot.py",
)
runner = load("gpu_prover_h100_pilot_runner_contract", "azure/measured_runner.py")
transcript_verifier = load(
    "gpu_prover_h100_pilot_transcript_contract",
    "attestation/verify_measured_runner_transcript.py",
)
receipt_tool = load(
    "gpu_prover_h100_pilot_receipt_contract", "tools/trusted_compute_receipt.py"
)


FAKE_DRIVER_SOURCE = r'''
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>

std::string argument(int argc, char** argv, std::string_view name) {
  for (int i = 1; i + 1 < argc; ++i) if (argv[i] == name) return argv[i + 1];
  return {};
}

int main(int argc, char** argv) {
  const std::string output = argument(argc, argv, "--output");
  const std::string challenge = argument(argc, argv, "--challenge-nonce");
  const std::string module = argument(argc, argv, "--expected-module-sha256");
  const std::string input = argument(argc, argv, "--expected-input-sha256");
  if (output.empty() || challenge.size() != 64 || module.size() != 64 || input.size() != 64)
    return 2;
  unsigned char bytes[48] = {};
  const unsigned char magic[8] = {'S','I','G','6','4','O','0','1'};
  for (int i = 0; i < 8; ++i) bytes[i] = magic[i];
  bytes[8] = 1;
  bytes[16] = 1;
  const std::uint64_t one = 0x3ff0000000000000ULL;
  for (unsigned i = 0; i < 8; ++i) {
    bytes[24 + i] = static_cast<unsigned char>(one >> (8U * i));
    bytes[32 + i] = static_cast<unsigned char>(one >> (8U * i));
  }
  std::ofstream stream(output, std::ios::binary);
  stream.write(reinterpret_cast<const char*>(bytes), sizeof(bytes));
  stream.close();
  if (!stream) return 3;
  std::cout << "{\"allow_other_device\":false,\"compute_capability\":\"9.0\","
            << "\"device_count\":1,\"device_name\":\"NVIDIA H100 NVL\","
            << "\"input_payload_sha256\":\"" << input << "\","
            << "\"kind\":\"sparkinterval_generated_driver_run\","
            << "\"module_kind\":\"offline_cubin\",\"module_sha256\":\""
            << module << "\",\"output_file_sha256\":\""
            << "d12a8d4fbd2c611fa9828bfe91971bca311bfa6c99cf1a166d9014dbe1eee2da"
            << "\",\"output_file_size_bytes\":48,\"row_count\":1,"
            << "\"target\":\"sm_90\",\"challenge_nonce\":\""
            << challenge << "\"}\n";
  return 0;
}
'''


class H100MeasuredFormalPtxPilotTests(unittest.TestCase):
    class FakeTPM:
        def __init__(self):
            self.value = runner.PCR_ZERO

        def reset(self) -> None:
            self.value = runner.PCR_ZERO

        def read(self) -> bytes:
            return self.value

        def extend(self, digest_hex: str) -> None:
            self.value = runner.pcr_extend(self.value, digest_hex)

        def quote(self, qualifying_digest_hex: str, output_dir: Path) -> dict[str, object]:
            for filename in (
                "azure_hcl_report.bin",
                "azure_hcl_runtime_data.bin",
                "tcg_event_log.bin",
                "tpm_quote.msg",
                "tpm_quote.pcrs",
                "tpm_quote.sig",
                "vtpm_ak.pem",
                "vtpm_ak_cert.bin",
            ):
                (output_dir / filename).write_bytes(
                    (filename + qualifying_digest_hex).encode("ascii")
                )
            return {
                "ak_handle": "0x81000003",
                "local_checkquote_passed": True,
                "pcr_selection": runner.TPM_PCR_SELECTION,
                "qualifying_data_sha256": qualifying_digest_hex,
            }

    def _fake_driver(self, root: Path) -> Path:
        source = root / "fake-driver.cpp"
        executable = root / "fake-driver"
        source.write_text(FAKE_DRIVER_SOURCE, encoding="utf-8")
        completed = subprocess.run(
            [
                "g++",
                "-std=c++20",
                "-O2",
                "-static",
                "-s",
                "-Wl,--build-id=none",
                str(source),
                "-o",
                str(executable),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return executable

    def test_package_and_independent_trace_replay_without_h100(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_driver = self._fake_driver(temporary_path)
            package = temporary_path / "package"
            report = builder.build(
                package,
                compiler="g++",
                generator=ROOT / ".lake/build/bin/sparkinterval-gen",
                driver=fake_driver,
                ptxas="ptxas",
                nvdisasm="nvdisasm",
                runner_policy_path=(
                    ROOT / "profiles/measured_runner/development_challenge_first_v1.json"
                ),
                nvidia_policy_path=(
                    ROOT / "attestation/policies/gpu_prover_h100.rego"
                ),
                classification="development",
                allow_development_policy=True,
                allow_architecture_mismatch_for_packaging_test=True,
            )
            self.assertFalse(report["accepted"])
            self.assertFalse(report["lean_registry_admission"])
            self.assertTrue(report["lean_registry_invocation_supported"])
            self.assertEqual(
                report["lean_registry_invocation"], "h100FormalPtxConstantOneV1"
            )
            job = json.loads((package / "job.json").read_bytes())
            runner.validate_job_spec(job)
            policy, policy_hash = transcript_verifier.load_policy(
                package / "appraisal-policy.json", True
            )
            self.assertEqual(policy["allowed_job_spec_sha256"], [report["job_spec_sha256"]])
            self.assertEqual(
                policy["required_composite_appraiser_claims"],
                ["measured_runner_policy_valid", "result_artifact_bound_to_execution"],
            )
            self.assertEqual(
                policy_hash,
                hashlib.sha256((package / "appraisal-policy.json").read_bytes()).hexdigest(),
            )
            self.assertEqual(job["backend"], "azure_ncc40ads_h100_v5")
            self.assertEqual(job["output_contract"]["format"], "opaque_bytes_v1")
            self.assertEqual(job["artifact_closure"]["closure_kind"],
                             "content_addressed_image_source_reviewed_v1")
            self.assertEqual(
                job["gpu_pre_run_gate"]["secret_environment_names"],
                ["NV_ATTESTATION_SERVICE_KEY"],
            )
            ptx = (package / "artifacts/kernel.sm_90.ptx").read_text(encoding="ascii")
            self.assertTrue(ptx.startswith(".version 9.0\n.target sm_90\n"))
            self.assertEqual(job["algorithm"]["canonical_definition"], ptx)
            self.assertEqual(
                job["algorithm"]["definition_sha256"],
                hashlib.sha256(ptx.encode("ascii")).hexdigest(),
            )
            self.assertEqual(
                (package / "input/reference-batch.json").read_bytes(),
                builder.FORMAL_BATCH,
            )
            self.assertEqual(
                report["architecture_matches_azure_x86_64"],
                platform.machine().lower() in ("x86_64", "amd64"),
            )

            output_dir = package / "output"
            output_dir.mkdir()
            challenge = "42" * 32
            job_binding = "ab" * 32
            replacements = {
                "@challenge@": challenge,
                "@job_binding@": job_binding,
                "@input@": "input/reference-batch.json",
                "@output@": "output/result.json",
                "@trace@": "output/work-trace.json",
            }
            command = [
                next(
                    replacements[token]
                    for token in replacements
                    if argument == token
                )
                if argument in replacements
                else argument
                for argument in job["command"]["argv"]
            ]
            workload = subprocess.run(command, cwd=package, check=False, capture_output=True)
            self.assertEqual(workload.returncode, 0, workload.stderr.decode())
            self.assertEqual((output_dir / "result.json").read_bytes(), builder.EXPECTED_RESULT)
            builder.EXPECTED_RESULT.decode("utf-8", errors="strict")

            verifier_command = [
                replacements.get(argument, argument)
                for argument in job["work_trace_contract"]["verifier_argv"]
            ]
            verified = subprocess.run(
                verifier_command, cwd=package, check=False, capture_output=True
            )
            self.assertEqual(verified.returncode, 0, verified.stderr.decode())

            raw_path = output_dir / "result.json.gpu.raw"
            raw_bytes = raw_path.read_bytes()
            raw_path.write_bytes(raw_bytes[:-1] + bytes([raw_bytes[-1] ^ 1]))
            raw_rejected = subprocess.run(
                verifier_command, cwd=package, check=False, capture_output=True
            )
            self.assertNotEqual(raw_rejected.returncode, 0)
            raw_path.write_bytes(raw_bytes)

            result_path = output_dir / "result.json"
            result_path.write_bytes(builder.EXPECTED_RESULT + b" ")
            rejected = subprocess.run(
                verifier_command, cwd=package, check=False, capture_output=True
            )
            self.assertNotEqual(rejected.returncode, 0)

            challenge_path = temporary_path / "challenge.json"
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            challenge_value = {
                "campaign_id": "h100-formal-pilot-test",
                "expires_at_utc": (now + dt.timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "issued_at_utc": (now - dt.timedelta(minutes=1)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "kind": "gpu_prover_azure_run_challenge",
                "nonce": "24" * 32,
                "schema_version": 1,
                "shard_index": 0,
            }
            challenge_path.write_bytes(runner.canonical_json_bytes(challenge_value))

            secret = "test-service-key-must-never-be-recorded"

            def process_runner(argv, cwd, environment, timeout, stdout, stderr):
                del timeout
                if argv[0] == "artifacts/h100-gate-python-launcher":
                    self.assertEqual(environment["NV_ATTESTATION_SERVICE_KEY"], secret)

                    def value(name: str) -> str:
                        return argv[argv.index(name) + 1]

                    evidence_relative = (
                        "runner/h100-pre-run-evidence/evidence-manifest.json"
                    )
                    evidence_path = cwd / evidence_relative
                    evidence_path.parent.mkdir(parents=True)
                    evidence_bytes = runner.canonical_json_bytes(
                        {
                            "classification": "synthetic_test_only",
                            "kind": "sparkinterval_test_h100_gate_evidence",
                        }
                    )
                    evidence_path.write_bytes(evidence_bytes)
                    record = {
                        "backend": "azure_ncc40ads_h100_v5",
                        "challenge_nonce": value("--challenge-nonce"),
                        "evidence_manifest_path": evidence_relative,
                        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                        "expires_at_utc": (now + dt.timedelta(minutes=5)).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "gpu_cc_environment": "PRODUCTION",
                        "gpu_cc_mode": "ON",
                        "gpu_ready_state": "Ready",
                        "job_binding_sha256": value("--job-binding"),
                        "kind": "sparkinterval_h100_pre_run_gate",
                        "schema_version": 1,
                        "status": "release_allowed",
                    }
                    (cwd / value("--record-path")).write_bytes(
                        runner.canonical_json_bytes(record)
                    )
                    stdout.write_bytes(b"")
                    stderr.write_bytes(b"")
                    return 0
                return runner._subprocess_runner(
                    argv, cwd, environment, timeout=300, stdout_path=stdout,
                    stderr_path=stderr
                )

            run_root = temporary_path / "measured-run"
            with mock.patch.dict(
                "os.environ", {"NV_ATTESTATION_SERVICE_KEY": secret}, clear=False
            ):
                measured_report = runner.execute_job(
                    job_spec_path=package / "job.json",
                    artifact_root=package,
                    challenge_path=challenge_path,
                    output_dir=run_root,
                    tpm=self.FakeTPM(),
                    process_runner=process_runner,
                    allow_development_policy=True,
                )
            self.assertFalse(measured_report["accepted"])
            transcript_check = transcript_verifier.verify(
                run_root,
                challenge_path,
                package / "appraisal-policy.json",
                allow_development_policy=True,
            )
            self.assertFalse(transcript_check["accepted"])
            self.assertTrue(
                transcript_check["claims"]["challenge_dependent_work_trace_valid"]
            )
            statement = json.loads((run_root / "runner/statement.json").read_bytes())
            claim = receipt_tool.claim_from_bundle(
                {"statement": statement}, run_root.resolve(), "azure_ncc40ads_h100_v5"
            )
            self.assertEqual(claim["result"].encode("utf-8"), builder.EXPECTED_RESULT)
            self.assertEqual(
                claim["artifacts"]["device_cubin_hash"],
                next(
                    record["sha256"]
                    for record in job["artifact_closure"]["files"]
                    if record["statement_role"] == "gpu_cubin"
                ),
            )
            for path in (run_root / "runner").rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode("utf-8"), path.read_bytes())

    def test_production_cannot_relabel_development_policies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_driver = self._fake_driver(temporary_path)
            with self.assertRaisesRegex(builder.BuildError, "production-ready"):
                builder.build(
                    temporary_path / "rejected",
                    compiler="g++",
                    generator=ROOT / ".lake/build/bin/sparkinterval-gen",
                    driver=fake_driver,
                    ptxas="ptxas",
                    nvdisasm="nvdisasm",
                    runner_policy_path=(
                        ROOT / "profiles/measured_runner/development_challenge_first_v1.json"
                    ),
                    nvidia_policy_path=(
                        ROOT / "attestation/policies/gpu_prover_h100.rego"
                    ),
                    classification="production",
                )

    def test_expected_raw_gpu_hash_fixture_is_exact(self) -> None:
        raw = bytearray(48)
        raw[:8] = b"SIG64O01"
        raw[8] = 1
        raw[16] = 1
        struct.pack_into("<Q", raw, 24, 0x3FF0000000000000)
        struct.pack_into("<Q", raw, 32, 0x3FF0000000000000)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "d12a8d4fbd2c611fa9828bfe91971bca311bfa6c99cf1a166d9014dbe1eee2da",
        )


if __name__ == "__main__":
    unittest.main()
