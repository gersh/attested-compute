# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ATTESTATION = ROOT / "attestation"
if str(ATTESTATION) not in sys.path:
    sys.path.insert(0, str(ATTESTATION))

import collect_azure_ncc_evidence as collector  # noqa: E402
import verify_azure_ncc_evidence as verifier  # noqa: E402


def write_canonical(path: Path, value: object) -> None:
    path.write_bytes(collector.canonical_json_bytes(value) + b"\n")


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


AZURE_FAKE = r'''#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--backend", required=True)
for name in (
    "maa-token", "snp-report", "runtime-data", "hcl-report", "hcl-runtime-data",
    "ak-public", "ak-certificate", "quote-message", "quote-signature",
    "quote-pcrs", "event-log", "policy", "expected-binding-sha256",
    "pcr23-before", "pcr23-after", "expected-user-claims-sha512",
    "expected-attestation-url", "expected-maa-issuer",
    "expected-maa-audience", "expected-maa-provider",
):
    p.add_argument("--" + name, required=True)
p.add_argument("--nvidia-evidence")
p.add_argument("--nvidia-detached-eat")
p.add_argument("--nvidia-appraisal")
a = p.parse_args()
if a.backend == "azure_ncc40ads_h100_v5" and (
    not a.nvidia_evidence or not a.nvidia_detached_eat or not a.nvidia_appraisal
):
    p.error("H100 appraisal requires NVIDIA evidence")
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
not_before = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
not_after = (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
def h(name):
    return hashlib.sha256(Path(getattr(a, name.replace("-", "_"))).read_bytes()).hexdigest()
claims = {
    "accelerator_attestation_bound_to_cvm": (
        True if a.backend == "azure_ncc40ads_h100_v5" else "not_applicable"
    ),
    "azure_compliant_cvm": True,
    "debug_disabled": True,
    "event_log_replayed": True,
    "maa_policy_valid": True,
    "maa_signature_valid": True,
    "maa_time_valid": True,
    "measured_runner_policy_valid": True,
    "pcr23_binding_valid": True,
    "pre_run_accelerator_gate_valid": (
        True if a.backend == "azure_ncc40ads_h100_v5" else "not_applicable"
    ),
    "quote_ak_chain_valid": True,
    "quote_signature_valid": True,
    "runtime_data_bound": True,
    "result_artifact_bound_to_execution": True,
    "secure_boot": True,
    "tee": "amd_sev_snp",
    "vtpm": True,
}
out = {
    "accepted": True,
    "ak_certificate_sha256": h("ak-certificate"),
    "ak_public_sha256": h("ak-public"),
    "binding_sha256": a.expected_binding_sha256,
    "claims": claims,
    "event_log_sha256": h("event-log"),
    "hcl_report_sha256": h("hcl-report"),
    "hcl_runtime_data_sha256": h("hcl-runtime-data"),
    "kind": "sparkinterval_azure_sevsnp_vtpm_appraisal",
    "maa_attestation_url": a.expected_attestation_url,
    "maa_audience": a.expected_maa_audience,
    "maa_issuer": a.expected_maa_issuer,
    "maa_provider": a.expected_maa_provider,
    "maa_token_sha256": h("maa-token"),
    "not_after_utc": not_after,
    "not_before_utc": not_before,
    "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
    "pcr23_after_sha256": h("pcr23-after"),
    "pcr23_before_sha256": h("pcr23-before"),
    "quote_message_sha256": h("quote-message"),
    "quote_pcrs_sha256": h("quote-pcrs"),
    "quote_signature_sha256": h("quote-signature"),
    "runtime_data_sha256": h("runtime-data"),
    "schema_version": 1,
    "snp_report_sha256": h("snp-report"),
    "user_claims_sha512": a.expected_user_claims_sha512,
}
print(json.dumps(out, sort_keys=True, separators=(",", ":")), end="")
'''


NVIDIA_FAKE = r'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys

nonce = sys.argv[sys.argv.index("--nonce") + 1]
Path(__file__).with_name("nvidia-appraiser.invoked").write_text(nonce)
evidence = Path(sys.argv[sys.argv.index("--gpu-evidence-file") + 1])
detached_eat = json.loads(evidence.with_name("nvidia_detached_eat.json").read_text())
out = {
    "claims": [{
        "dbgstat": "disabled",
        "secboot": True,
        "x-nvidia-device-type": "gpu",
        "x-nvidia-gpu-attestation-report-nonce-match": True,
    }],
    "detached_eat": detached_eat,
    "result_code": 0,
    "result_message": "Ok",
}
print(json.dumps(out, sort_keys=True, separators=(",", ":")), end="")
'''


class EvidenceFixture:
    def __init__(self, root: Path, backend: str):
        self.root = root
        self.backend = backend
        self.pack = root / "evidence"
        self.policy_dir = root / "policy"
        self.pack.mkdir()
        self.policy_dir.mkdir()
        self.start = "11" * 32
        self.statement = "22" * 32
        self.binding = collector.derive_binding_nonce(self.start, self.statement)
        self.maa_url = (
            "https://fixture.eus.attest.azure.net/attest/SevSnpVm"
            "?api-version=2022-08-01"
        )
        self.maa_issuer = "https://fixture.eus.attest.azure.net"
        self.maa_audience = "https://attest.azure.net"
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.challenge_issued = (now - dt.timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.collection_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.challenge_expires = (now + dt.timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.challenge = {
            "campaign_id": "test-campaign",
            "expires_at_utc": self.challenge_expires,
            "issued_at_utc": self.challenge_issued,
            "kind": collector.CHALLENGE_KIND,
            "nonce": self.start,
            "schema_version": 1,
            "shard_index": 0,
        }
        self.challenge_file = root / "retained.challenge.json"
        write_canonical(self.challenge_file, self.challenge)
        self._write_pack()
        self.policy = self._write_policy()

    def _write_pack(self) -> None:
        claims = {
            "user-claims": {
                "post-run-binding-nonce": self.binding,
                "protocol": "sparkinterval.trusted-compute.result-binding.v1",
                "start-challenge": self.start,
                "statement-sha256": self.statement,
            }
        }
        claims_digest = hashlib.sha512(json.dumps(claims).encode("utf-8")).hexdigest()
        write_canonical(
            self.pack / "maa_config.json",
            {
                "api_key": "",
                "attestation_provider": "maa_snp",
                "attestation_url": self.maa_url,
                "claims": claims,
                "enable_metrics": False,
            },
        )
        (self.pack / "maa_token.jwt").write_text("e30.e30.signature\n", encoding="ascii")
        (self.pack / "report.bin").write_bytes(b"S" * 1184)
        write_canonical(self.pack / "runtime_data.json", {"user-data": claims_digest})
        pcr23_before = bytes(32)
        pcr23_after = hashlib.sha256(
            pcr23_before + bytes.fromhex(self.binding)
        ).digest()
        binary_files = {
            "azure_hcl_report.bin": b"HCL report",
            "azure_hcl_runtime_data.bin": b"HCL runtime",
            "tcg_event_log.bin": b"TCG event log",
            "tpm_quote.msg": b"TPM quote message",
            "tpm_quote.pcrs": b"TPM PCR values",
            "tpm_quote.sig": b"TPM signature",
            "pcr23.before.bin": pcr23_before,
            "pcr23.after.bin": pcr23_after,
            "vtpm_ak.pem": b"-----BEGIN PUBLIC KEY-----\nTEST\n-----END PUBLIC KEY-----\n",
            "vtpm_ak_cert.bin": b"Azure AK certificate",
        }
        for name, data in binary_files.items():
            (self.pack / name).write_bytes(data)
        quote = {
            "ak_certificate_sha256": file_sha(self.pack / "vtpm_ak_cert.bin"),
            "ak_public_sha256": file_sha(self.pack / "vtpm_ak.pem"),
            "event_log_sha256": file_sha(self.pack / "tcg_event_log.bin"),
            "kind": "gpu_prover_vtpm_quote_evidence",
            "pcr_selection": collector.TPM_PCR_SELECTION,
            "pcr23_after_sha256": file_sha(self.pack / "pcr23.after.bin"),
            "pcr23_after_value_hex": pcr23_after.hex(),
            "pcr23_before_sha256": file_sha(self.pack / "pcr23.before.bin"),
            "pcr23_before_value_hex": pcr23_before.hex(),
            "pcrs_sha256": file_sha(self.pack / "tpm_quote.pcrs"),
            "qualifying_data_sha256": self.binding,
            "quote_message_sha256": file_sha(self.pack / "tpm_quote.msg"),
            "quote_signature_sha256": file_sha(self.pack / "tpm_quote.sig"),
            "schema_version": 1,
        }
        write_canonical(self.pack / "tpm_quote_evidence.json", quote)
        gpu = None
        gpu_state = None
        if self.backend == "azure_ncc40ads_h100_v5":
            now_epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())

            def encode(value: object) -> str:
                return base64.urlsafe_b64encode(
                    json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                ).rstrip(b"=").decode()

            token = (
                encode({"alg": "test"})
                + "."
                + encode(
                    {
                        "exp": now_epoch + 1800,
                        "iat": now_epoch - 30,
                        "nbf": now_epoch - 30,
                    }
                )
                + ".signature"
            )
            detached_eat = [["JWT", token], {"GPU-0": token}]
            write_canonical(
                self.pack / "nvidia_gpu_evidence.json",
                {
                    "evidences": [{"arch": "HOPPER", "nonce": self.binding}],
                    "result_code": 0,
                    "result_message": "Ok",
                },
            )
            write_canonical(
                self.pack / "nvidia_detached_eat.json",
                detached_eat,
            )
            write_canonical(
                self.pack / "nvidia_gpu_attestation.json",
                {"claims": [{"secboot": True}], "detached_eat": detached_eat},
            )
            gpu = {"detached_eat_present": True}
            gpu_state = {
                "cc_environment": "PRODUCTION",
                "cc_gpus_ready_state": "Ready",
                "cc_mode": "ON",
            }
        records = []
        for path in sorted(self.pack.iterdir()):
            records.append(
                {
                    "path": path.name,
                    "sha256": file_sha(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        manifest = {
            "artifacts": records,
            "backend": self.backend,
            "binding": {
                "post_run_binding_nonce": self.binding,
                "protocol": "sparkinterval.trusted-compute.result-binding.v1",
                "start_challenge": self.start,
                "statement_sha256": self.statement,
            },
            "challenge": self.challenge,
            "collection_time_utc": self.collection_time,
            "gpu": gpu,
            "gpu_state": gpu_state,
            "kind": collector.KIND,
            "maa": {
                "adapter": "/pinned/azure/attest",
                "adapter_sha256": "33" * 32,
                "attestation_url": self.maa_url,
                "audience": self.maa_audience,
                "claims_sha512": claims_digest,
                "issuer": self.maa_issuer,
                "jti": "fixture-jti",
                "provider": collector.MAA_PROVIDER,
                "token_signature_verified_by_collector": False,
            },
            "schema_version": 1,
            "status": "evidence_collected_pending_independent_verification",
            "tpm": {
                "ak_handle": "0x81000003",
                "azure_ak_chain_verified_by_collector": False,
                "local_checkquote_passed": True,
                "pcr23_extended_with": self.binding,
                "pcr23_expected_after_hex": pcr23_after.hex(),
                "pcr23_initial_value_hex": pcr23_before.hex(),
                "pcr_selection": collector.TPM_PCR_SELECTION,
                "quote_evidence_sha256": file_sha(
                    self.pack / "tpm_quote_evidence.json"
                ),
                "quote_qualifying_data": self.binding,
                "tool_sha256": {"tpm2_checkquote": "44" * 32},
            },
            "trust_boundary": {
                "algorithm_execution_proven_by_collector": False,
                "maa_jws_signature_verified_by_collector": False,
                "nvidia_eat_retained": self.backend == "azure_ncc40ads_h100_v5",
                "signed_acceptance_certificate_issued": False,
            },
        }
        write_canonical(self.pack / "evidence-manifest.json", manifest)

    def _write_executable(self, name: str, source: str) -> Path:
        path = self.policy_dir / name
        path.write_text(source)
        path.chmod(0o755)
        return path

    def _write_policy(self) -> Path:
        azure_executable = self._write_executable("azure-appraiser", AZURE_FAKE)
        azure_policy = self.policy_dir / "azure-policy.json"
        write_canonical(azure_policy, {"fixture": "cryptographic-policy"})
        nvidia_record = None
        if self.backend == "azure_ncc40ads_h100_v5":
            nvidia_executable = self._write_executable("nvattest", NVIDIA_FAKE)
            nvidia_policy = self.policy_dir / "nvidia-policy.rego"
            nvidia_policy.write_text("package policy\ndefault nv_match := false\n")
            nvidia_record = {
                "executable_path": nvidia_executable.name,
                "executable_sha256": file_sha(nvidia_executable),
                "nras_url": "https://nras.attestation.nvidia.com",
                "policy_path": nvidia_policy.name,
                "policy_sha256": file_sha(nvidia_policy),
                "timeout_seconds": 30,
                "verifier": "local",
            }
        policy = {
            "allowed_backends": [self.backend],
            "azure_appraiser": {
                "executable_path": azure_executable.name,
                "executable_sha256": file_sha(azure_executable),
                "maa_accepted_audience": self.maa_audience,
                "maa_accepted_issuer": self.maa_issuer,
                "maa_accepted_provider": collector.MAA_PROVIDER,
                "maa_attestation_url": self.maa_url,
                "policy_path": azure_policy.name,
                "policy_sha256": file_sha(azure_policy),
                "timeout_seconds": 30,
            },
            "kind": verifier.POLICY_KIND,
            "nvidia_appraiser": nvidia_record,
            "schema_version": 1,
        }
        path = self.policy_dir / "composite-policy.json"
        write_canonical(path, policy)
        return path

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            evidence_pack=self.pack,
            policy=self.policy,
            backend=self.backend,
            expected_start_challenge_sha256=self.start,
            expected_result_binding_sha256=self.binding,
            expected_challenge_file=self.challenge_file,
            _test_only_allow_legacy_diagnostic=True,
        )

    def replace_azure_appraiser_source(self, old: str, new: str) -> None:
        executable = self.policy_dir / "azure-appraiser"
        source = executable.read_text()
        if old not in source:
            raise AssertionError(f"fixture appraiser source does not contain {old!r}")
        executable.write_text(source.replace(old, new, 1))
        executable.chmod(0o755)
        policy = json.loads(self.policy.read_text())
        policy["azure_appraiser"]["executable_sha256"] = file_sha(executable)
        write_canonical(self.policy, policy)


class AzureEvidenceAppraiserTests(unittest.TestCase):
    def test_appraiser_subprocess_environment_drops_loader_and_python_injection(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b'{"ok":true}', stderr=b"")
        with mock.patch.dict(
            os.environ,
            {
                "LD_LIBRARY_PATH": "/attacker",
                "LD_PRELOAD": "/attacker/preload.so",
                "PYTHONHOME": "/attacker/python",
                "PYTHONPATH": "/attacker/modules",
            },
        ), mock.patch.object(
            verifier.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(
                verifier._run_json(
                    ["/snapshot/appraiser"], timeout=1, what="test appraiser"
                ),
                {"ok": True},
            )
        environment = run.call_args.kwargs["env"]
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
            self.assertNotIn(name, environment)
        self.assertEqual(environment["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")

    def test_cpu_appraisal_invokes_azure_and_marks_nvidia_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            result = verifier.appraise(fixture.args())
            self.assertTrue(result["accepted"])
            self.assertEqual(result["kind"], "sparkinterval_evidence_appraisal")
            self.assertEqual(
                result["evidence_hashes"]["nvidia_eat_sha256"],
                verifier.NOT_APPLICABLE_DIGEST,
            )
            self.assertEqual(
                result["evidence_hashes"]["nvidia_evidence_sha256"],
                verifier.NOT_APPLICABLE_DIGEST,
            )

    def test_h100_appraisal_invokes_both_pinned_appraisers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_ncc40ads_h100_v5")
            result = verifier.appraise(fixture.args())
            self.assertTrue(result["accepted"])
            self.assertNotEqual(
                result["evidence_hashes"]["nvidia_eat_sha256"],
                verifier.NOT_APPLICABLE_DIGEST,
            )
            marker = fixture.policy_dir / "nvidia-appraiser.invoked"
            self.assertFalse(marker.exists())

    def test_cli_emits_exact_receipt_appraisal_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            process = subprocess.run(
                [
                    sys.executable,
                    str(ATTESTATION / "verify_azure_ncc_evidence.py"),
                    "--evidence-pack",
                    str(fixture.pack),
                    "--policy",
                    str(fixture.policy),
                    "--backend",
                    fixture.backend,
                    "--expected-challenge-file",
                    str(fixture.challenge_file),
                    "--expected-start-challenge-sha256",
                    fixture.start,
                    "--expected-result-binding-sha256",
                    fixture.binding,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(process.returncode, 2)
            self.assertEqual(process.stdout, "")
            self.assertIn("challenge-first measured evidence", process.stderr)

    def test_artifact_tampering_fails_before_appraisal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            with (fixture.pack / "report.bin").open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(verifier.AppraisalError, "differs from the manifest"):
                verifier.appraise(fixture.args())

    def test_unpinned_appraiser_replacement_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            with (fixture.policy_dir / "azure-appraiser").open("a") as stream:
                stream.write("\n# replaced\n")
            with self.assertRaisesRegex(verifier.AppraisalError, "pinned SHA-256"):
                verifier.appraise(fixture.args())

    def test_cpu_pack_rejects_nvidia_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            (fixture.pack / "nvidia_gpu_evidence.json").write_text("{}\n")
            with self.assertRaisesRegex(verifier.AppraisalError, "closure differs"):
                verifier.appraise(fixture.args())

    def test_self_consistent_wrong_pcr23_extend_fails_before_appraiser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            bad_after = bytes.fromhex("ff" * 32)
            (fixture.pack / "pcr23.after.bin").write_bytes(bad_after)
            quote_path = fixture.pack / "tpm_quote_evidence.json"
            quote = json.loads(quote_path.read_text())
            quote["pcr23_after_sha256"] = file_sha(fixture.pack / "pcr23.after.bin")
            quote["pcr23_after_value_hex"] = bad_after.hex()
            write_canonical(quote_path, quote)
            manifest_path = fixture.pack / "evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["tpm"]["pcr23_expected_after_hex"] = bad_after.hex()
            manifest["tpm"]["quote_evidence_sha256"] = file_sha(quote_path)
            for record in manifest["artifacts"]:
                artifact = fixture.pack / record["path"]
                record["sha256"] = file_sha(artifact)
                record["size_bytes"] = artifact.stat().st_size
            write_canonical(manifest_path, manifest)
            with self.assertRaisesRegex(verifier.AppraisalError, "post-extend value"):
                verifier.appraise(fixture.args())

    def test_policy_rejects_a_different_maa_provider_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            policy = json.loads(fixture.policy.read_text())
            policy["azure_appraiser"]["maa_attestation_url"] = (
                "https://other.eus.attest.azure.net/attest/SevSnpVm"
                "?api-version=2022-08-01"
            )
            policy["azure_appraiser"]["maa_accepted_issuer"] = (
                "https://other.eus.attest.azure.net"
            )
            write_canonical(fixture.policy, policy)
            with self.assertRaisesRegex(verifier.AppraisalError, "not allowed by policy"):
                verifier.appraise(fixture.args())

    def test_appraiser_policy_mutation_during_execution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            fixture.replace_azure_appraiser_source(
                "now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)",
                'Path(a.policy).write_text("tampered\\n")\n'
                "now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)",
            )
            with self.assertRaisesRegex(
                verifier.AppraisalError, "rejected the evidence|policy changed"
            ):
                verifier.appraise(fixture.args())

    def test_source_swap_after_snapshot_cannot_change_appraisal_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            original_appraise = verifier._appraise_azure
            observed: dict[str, Path] = {}

            def swap_sources(executable, policy, *args, **kwargs):
                observed["executable"] = executable
                observed["policy"] = policy
                self.assertNotEqual(executable, fixture.policy_dir / "azure-appraiser")
                self.assertNotEqual(policy, fixture.policy_dir / "azure-policy.json")
                self.assertEqual(executable.stat().st_mode & 0o777, 0o500)
                self.assertEqual(policy.stat().st_mode & 0o777, 0o400)
                (fixture.policy_dir / "azure-appraiser").write_text(
                    "#!/bin/sh\nexit 99\n"
                )
                (fixture.policy_dir / "azure-policy.json").write_text("substituted\n")
                (fixture.pack / "report.bin").write_bytes(b"substituted evidence")
                return original_appraise(executable, policy, *args, **kwargs)

            with mock.patch.object(
                verifier, "_appraise_azure", side_effect=swap_sources
            ):
                result = verifier.appraise(fixture.args())
            self.assertTrue(result["accepted"])
            self.assertEqual(set(observed), {"executable", "policy"})

    def test_independent_verifier_rejects_expired_and_future_challenges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            manifest_path = fixture.pack / "evidence-manifest.json"
            original = json.loads(manifest_path.read_text())
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            cases = {
                "expired": (now - dt.timedelta(hours=2), now - dt.timedelta(hours=1)),
                "future": (now + dt.timedelta(hours=1), now + dt.timedelta(hours=2)),
            }
            for label, (issued, expires) in cases.items():
                with self.subTest(label=label):
                    manifest = copy.deepcopy(original)
                    manifest["challenge"]["issued_at_utc"] = issued.strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                    manifest["challenge"]["expires_at_utc"] = expires.strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                    write_canonical(
                        fixture.challenge_file, manifest["challenge"]
                    )
                    write_canonical(manifest_path, manifest)
                    with self.assertRaisesRegex(
                        verifier.AppraisalError, "current validity window"
                    ):
                        verifier.appraise(fixture.args())

    def test_worker_cannot_rewrite_retained_challenge_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            manifest_path = fixture.pack / "evidence-manifest.json"
            original = json.loads(manifest_path.read_text())
            mutations = {
                "expiry": ("expires_at_utc", "2099-01-01T00:00:00Z"),
                "campaign": ("campaign_id", "relabeled-campaign"),
                "shard": ("shard_index", 17),
            }
            for label, (field, value) in mutations.items():
                with self.subTest(label=label):
                    manifest = copy.deepcopy(original)
                    manifest["challenge"][field] = value
                    write_canonical(manifest_path, manifest)
                    with self.assertRaisesRegex(
                        verifier.AppraisalError, "retained off-VM challenge"
                    ):
                        verifier.appraise(fixture.args())

    def test_retained_challenge_rejects_multiple_trailing_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            fixture.challenge_file.write_bytes(
                collector.canonical_json_bytes(fixture.challenge) + b"\n\n"
            )
            with self.assertRaisesRegex(verifier.AppraisalError, "canonical JSON"):
                verifier.appraise(fixture.args())

    def test_h100_rejects_retained_eat_different_from_pinned_appraisal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_ncc40ads_h100_v5")
            executable = fixture.policy_dir / "nvattest"
            source = executable.read_text()
            source = source.replace(
                '"detached_eat": detached_eat,',
                '"detached_eat": [["JWT", detached_eat[0][1][:-1] + "X"]],',
            )
            executable.write_text(source)
            executable.chmod(0o755)
            policy = json.loads(fixture.policy.read_text())
            policy["nvidia_appraiser"]["executable_sha256"] = file_sha(executable)
            write_canonical(fixture.policy, policy)
            with self.assertRaisesRegex(verifier.AppraisalError, "retained NVIDIA"):
                verifier.appraise(fixture.args())

    def test_appraiser_must_establish_measured_runner_and_result_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            fixture.replace_azure_appraiser_source(
                '"measured_runner_policy_valid": True,',
                '"measured_runner_policy_valid": False,',
            )
            with self.assertRaisesRegex(
                verifier.AppraisalError, "measured_runner_policy_valid"
            ):
                verifier.appraise(fixture.args())
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_sevsnp_cpu")
            fixture.replace_azure_appraiser_source(
                '    "result_artifact_bound_to_execution": True,\n', ""
            )
            with self.assertRaisesRegex(verifier.AppraisalError, "wrong fields"):
                verifier.appraise(fixture.args())

    def test_h100_requires_accelerator_attestation_bound_to_same_cvm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = EvidenceFixture(Path(temporary), "azure_ncc40ads_h100_v5")
            fixture.replace_azure_appraiser_source(
                '        True if a.backend == "azure_ncc40ads_h100_v5" else "not_applicable"',
                '        False if a.backend == "azure_ncc40ads_h100_v5" else "not_applicable"',
            )
            with self.assertRaisesRegex(verifier.AppraisalError, "accelerator attestation"):
                verifier.appraise(fixture.args())


if __name__ == "__main__":
    unittest.main()
