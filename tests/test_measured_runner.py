# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    specification = importlib.util.spec_from_file_location(name, REPOSITORY_ROOT / path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


runner = load("gpu_prover_measured_runner", "azure/measured_runner.py")
builder = load("gpu_prover_cubic_builder", "tools/build_cubic_measured_example.py")
transcript_verifier = load(
    "gpu_prover_measured_transcript_verifier",
    "attestation/verify_measured_runner_transcript.py",
)
measured_collector = load(
    "gpu_prover_measured_evidence_collector",
    "attestation/collect_azure_measured_evidence.py",
)
archive_transport = load(
    "gpu_prover_measured_archive_transport",
    "attestation/measured_run_archive.py",
)
collector = load("gpu_prover_measured_collector_shape", "attestation/collect_azure_ncc_evidence.py")
outer_appraiser = load(
    "gpu_prover_outer_measured_appraiser", "attestation/verify_azure_ncc_evidence.py"
)
h100_gate = load(
    "gpu_prover_h100_pre_run_gate", "attestation/azure_h100_pre_run_gate.py"
)


def write_challenge(path: Path, nonce: str = "42" * 32) -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    value = {
        "campaign_id": "measured-runner-test",
        "expires_at_utc": (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_at_utc": (now - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "gpu_prover_azure_run_challenge",
        "nonce": nonce,
        "schema_version": 1,
        "shard_index": 0,
    }
    path.write_bytes(runner.canonical_json_bytes(value))
    return value


class FakeTPM:
    def __init__(self):
        self.value = runner.PCR_ZERO
        self.extensions: list[str] = []
        self.quoted_digests: list[str] = []

    def reset(self) -> None:
        self.value = runner.PCR_ZERO

    def read(self) -> bytes:
        return self.value

    def extend(self, digest_hex: str) -> None:
        self.extensions.append(digest_hex)
        self.value = runner.pcr_extend(self.value, digest_hex)

    def quote(self, qualifying_digest_hex: str, output_dir: Path) -> dict[str, object]:
        self.quoted_digests.append(qualifying_digest_hex)
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
            (output_dir / filename).write_bytes((filename + qualifying_digest_hex).encode("ascii"))
        return {
            "ak_handle": "0x81000003",
            "local_checkquote_passed": True,
            "pcr_selection": runner.TPM_PCR_SELECTION,
            "qualifying_data_sha256": qualifying_digest_hex,
        }


class MeasuredRunnerTests(unittest.TestCase):
    def _run_fixture(self, temporary: str):
        root = Path(temporary) / "job"
        builder.build(root, "g++")
        challenge = Path(temporary) / "challenge.json"
        challenge_value = write_challenge(challenge)
        output = Path(temporary) / "run"
        tpm = FakeTPM()
        report = runner.execute_job(
            job_spec_path=root / "job.json",
            artifact_root=root,
            challenge_path=challenge,
            output_dir=output,
            tpm=tpm,
            allow_development_policy=True,
        )
        return root, challenge, challenge_value, output, tpm, report

    def test_real_static_cubic_job_is_challenge_first_and_transcript_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, challenge, challenge_value, output, tpm, report = self._run_fixture(temporary)
            self.assertFalse(report["accepted"])
            self.assertEqual((output / "output/result.txt").read_bytes(), b"13334666700000000")
            self.assertEqual(len(tpm.extensions), 2)
            transcript = json.loads((output / "runner/transcript.json").read_bytes())
            statement = json.loads((output / "runner/statement.json").read_bytes())
            expected_result_binding = runner.derive_binding_nonce(
                challenge_value["nonce"],
                runner.canonical_sha256(statement),
            )
            self.assertEqual(report["result_binding_sha256"], expected_result_binding)
            self.assertEqual(tpm.quoted_digests, [expected_result_binding])
            self.assertEqual(
                transcript["quote"]["qualifying_data_sha256"],
                expected_result_binding,
            )
            execution_manifests = [
                row for row in statement["build_artifacts"]
                if row["role"] == "execution_manifest"
            ]
            self.assertEqual(
                [row["path"] for row in execution_manifests],
                ["runner/closure-manifest.json"],
            )
            self.assertFalse(
                (output / "runner/goldbach-execution-manifest.json").exists()
            )
            self.assertEqual(transcript["command"]["argv"][2], challenge_value["nonce"])
            self.assertEqual(transcript["command"]["argv"][4], report["job_binding_sha256"])
            self.assertLess(
                transcript["timing"]["pcr_start_extended"]["monotonic_ns"],
                transcript["timing"]["workload_started"]["monotonic_ns"],
            )
            self.assertEqual(
                transcript["pcr23"]["after_result_hex"],
                runner.pcr_extend(
                    runner.pcr_extend(runner.PCR_ZERO, tpm.extensions[0]), tpm.extensions[1]
                ).hex(),
            )
            verification = transcript_verifier.verify(
                output,
                challenge,
                root / "appraisal-policy.json",
                allow_development_policy=True,
            )
            self.assertFalse(verification["accepted"])
            self.assertTrue(verification["claims"]["challenge_dependent_work_trace_valid"])
            self.assertFalse(verification["claims"]["hardware_quote_authenticated"])

    def test_stale_result_or_trace_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, challenge, _challenge_value, output, _tpm, _report = self._run_fixture(temporary)
            (output / "output/result.txt").write_bytes(b"13334666700000001")
            with self.assertRaises(transcript_verifier.TranscriptError):
                transcript_verifier.verify(
                    output,
                    challenge,
                    root / "appraisal-policy.json",
                    allow_development_policy=True,
                )

    def test_external_trace_verifier_cannot_mutate_result_after_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "job"
            builder.build(root, "g++")
            job_path = root / "job.json"
            job = json.loads(job_path.read_bytes())
            verifier_path = root / "artifacts/trace-verifier"
            verifier_path.write_bytes((root / "artifacts/cubic_sum_div_three_20000").read_bytes())
            verifier_path.chmod(0o500)
            digest = hashlib.sha256(verifier_path.read_bytes()).hexdigest()
            job["artifact_closure"]["files"].append(
                {
                    "executable": True,
                    "path": "artifacts/trace-verifier",
                    "role": "adversarial_test_trace_verifier",
                    "sha256": digest,
                    "size_bytes": verifier_path.stat().st_size,
                    "statement_role": None,
                }
            )
            job["artifact_closure"]["manifest_sha256"] = runner.canonical_sha256(
                runner._closure_manifest(job["artifact_closure"]["files"])
            )
            job["work_trace_contract"]["verification_mode"] = (
                "pinned_external_trace_verifier_v1"
            )
            job["work_trace_contract"]["verifier_argv"] = [
                "artifacts/trace-verifier",
                "@challenge@",
                "@job_binding@",
                "@input@",
                "@output@",
                "@trace@",
            ]
            job_path.chmod(0o600)
            job_path.write_bytes(runner.canonical_json_bytes(job))
            challenge = Path(temporary) / "challenge.json"
            write_challenge(challenge)

            def adversarial_process(argv, cwd, environment, timeout, stdout, stderr):
                if argv[0] == "artifacts/trace-verifier":
                    stdout.write_bytes(b"")
                    stderr.write_bytes(b"")
                    (cwd / "output/result.txt").write_bytes(b"13334666700000001")
                    return 0
                return runner._subprocess_runner(
                    argv, cwd, environment, timeout, stdout, stderr
                )

            output = Path(temporary) / "run"
            with self.assertRaises(runner.RunnerError):
                runner.execute_job(
                    job_spec_path=job_path,
                    artifact_root=root,
                    challenge_path=challenge,
                    output_dir=output,
                    tpm=FakeTPM(),
                    process_runner=adversarial_process,
                    allow_development_policy=True,
                )
            self.assertFalse(output.exists())

    def test_source_declared_retained_artifact_is_signed_and_tamper_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "job"
            builder.build(root, "g++")
            job_path = root / "job.json"
            job = json.loads(job_path.read_bytes())
            verifier_path = root / "artifacts/trace-verifier"
            verifier_path.write_bytes(
                (root / "artifacts/cubic_sum_div_three_20000").read_bytes()
            )
            verifier_path.chmod(0o500)
            verifier_digest = hashlib.sha256(verifier_path.read_bytes()).hexdigest()
            job["artifact_closure"]["files"].append(
                {
                    "executable": True,
                    "path": "artifacts/trace-verifier",
                    "role": "retained_artifact_test_trace_verifier",
                    "sha256": verifier_digest,
                    "size_bytes": verifier_path.stat().st_size,
                    "statement_role": None,
                }
            )
            job["artifact_closure"]["manifest_sha256"] = runner.canonical_sha256(
                runner._closure_manifest(job["artifact_closure"]["files"])
            )
            job["work_trace_contract"]["verification_mode"] = (
                "pinned_external_trace_verifier_v1"
            )
            job["work_trace_contract"]["verifier_argv"] = [
                "artifacts/trace-verifier",
                "@challenge@",
                "@job_binding@",
                "@input@",
                "@output@",
                "@trace@",
            ]
            job["retained_artifact_contracts"] = [
                {
                    "maximum_bytes": 1024,
                    "path": "work/test-certificate.bin",
                    "trace_sha256_field": "certificate_sha256",
                }
            ]
            job_bytes = runner.canonical_json_bytes(job)
            job_path.chmod(0o600)
            job_path.write_bytes(job_bytes)
            policy_path = root / "appraisal-policy.json"
            policy = json.loads(policy_path.read_bytes())
            policy["allowed_job_spec_sha256"] = [
                hashlib.sha256(job_bytes).hexdigest()
            ]
            policy_path.chmod(0o600)
            policy_path.write_bytes(runner.canonical_json_bytes(policy))

            challenge = Path(temporary) / "challenge.json"
            write_challenge(challenge)
            retained_bytes = b"bounded retained certificate fixture"
            retained_digest = hashlib.sha256(retained_bytes).hexdigest()

            def retained_process(argv, cwd, environment, timeout, stdout, stderr):
                if argv[0] == "artifacts/trace-verifier":
                    stdout.write_bytes(b"")
                    stderr.write_bytes(b"")
                    return 0
                result = runner._subprocess_runner(
                    argv, cwd, environment, timeout, stdout, stderr
                )
                if result == 0:
                    retained = cwd / "work/test-certificate.bin"
                    retained.parent.mkdir(mode=0o700, parents=True)
                    retained.write_bytes(retained_bytes)
                    trace_path = cwd / "output/work-trace.json"
                    trace = json.loads(trace_path.read_bytes())
                    trace["certificate_sha256"] = retained_digest
                    trace_path.write_bytes(runner.canonical_json_bytes(trace))
                return result

            output = Path(temporary) / "run"
            report = runner.execute_job(
                job_spec_path=job_path,
                artifact_root=root,
                challenge_path=challenge,
                output_dir=output,
                tpm=FakeTPM(),
                process_runner=retained_process,
                allow_development_policy=True,
            )
            statement = json.loads((output / "runner/statement.json").read_bytes())
            expected_identity = {
                "path": "work/test-certificate.bin",
                "sha256": retained_digest,
                "size_bytes": len(retained_bytes),
            }
            self.assertEqual(
                statement["execution_environment"]["value"][
                    "retained_artifacts"
                ],
                [expected_identity],
            )
            transcript = json.loads((output / "runner/transcript.json").read_bytes())
            self.assertEqual(
                transcript["work_trace"]["retained_artifacts"],
                [expected_identity],
            )
            self.assertEqual(
                report["statement_sha256"],
                runner.canonical_sha256(statement),
            )
            with mock.patch.object(
                transcript_verifier.subprocess,
                "run",
                return_value=mock.Mock(returncode=0),
            ):
                checked = transcript_verifier.verify(
                    output,
                    challenge,
                    policy_path,
                    allow_development_policy=True,
                )
            self.assertFalse(checked["accepted"])

            (output / "work/test-certificate.bin").write_bytes(b"tampered")
            with mock.patch.object(
                transcript_verifier.subprocess,
                "run",
                return_value=mock.Mock(returncode=0),
            ):
                with self.assertRaisesRegex(
                    transcript_verifier.TranscriptError,
                    "differs from its work-trace digest",
                ):
                    transcript_verifier.verify(
                        output,
                        challenge,
                        policy_path,
                        allow_development_policy=True,
                    )

    def test_retained_artifact_contract_rejects_unsafe_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "job"
            builder.build(root, "g++")
            job = json.loads((root / "job.json").read_bytes())
            job["retained_artifact_contracts"] = [
                {
                    "maximum_bytes": 32,
                    "path": job["output_contract"]["path"],
                    "trace_sha256_field": "trace_sha256",
                }
            ]
            with self.assertRaises(runner.RunnerError):
                runner.validate_job_spec(job)

    def test_run_bundle_handoff_preserves_statement_and_verifies_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _root, _challenge, _challenge_value, output, _tpm, report = self._run_fixture(
                temporary
            )
            evidence = Path(temporary) / "evidence"
            evidence.mkdir()
            (evidence / "maa_token.jwt").write_text("header.payload.signature\n")
            bundle = measured_collector._make_run_bundle(
                output, evidence, "azure_sevsnp_cpu"
            )
            statement = json.loads((output / "runner/statement.json").read_bytes())
            self.assertEqual(bundle["statement"], statement)
            self.assertEqual(bundle["statement_sha256"], report["statement_sha256"])
            checked = measured_collector.verify_run_bundle.verify_bundle(
                bundle, artifact_root=output
            )
            self.assertTrue(checked["artifacts_verified"])

    def test_measured_adapter_bundle_and_outer_appraisal_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, challenge, challenge_value, run_output, _tpm, run_report = self._run_fixture(
                temporary
            )
            temporary_path = Path(temporary)
            maa_url = (
                "https://fixture.eus.attest.azure.net/attest/SevSnpVm"
                "?api-version=2022-08-01"
            )

            def fake_maa(stage, _command, start, statement, binding, attestation_url):
                claims = {
                    "user-claims": {
                        "post-run-binding-nonce": binding,
                        "protocol": "sparkinterval.trusted-compute.result-binding.v1",
                        "start-challenge": start,
                        "statement-sha256": statement,
                    }
                }
                claims_digest = hashlib.sha512(
                    json.dumps(claims).encode("utf-8")
                ).hexdigest()
                config = {
                    "api_key": "",
                    "attestation_provider": "maa_snp",
                    "attestation_url": attestation_url,
                    "claims": claims,
                    "enable_metrics": False,
                }
                (stage / "maa_config.json").write_bytes(runner.canonical_json_bytes(config))
                (stage / "runtime_data.json").write_bytes(
                    runner.canonical_json_bytes({"claims_sha512": claims_digest})
                )
                (stage / "report.bin").write_bytes(bytes(1184))
                (stage / "maa_token.jwt").write_text("header.payload.signature\n")
                return {
                    "adapter": "/fake/maa",
                    "adapter_sha256": "91" * 32,
                    "attestation_url": attestation_url,
                    "audience": "https://attest.azure.net",
                    "claims_sha512": claims_digest,
                    "issuer": "https://fixture.eus.attest.azure.net",
                    "jti": "measured-test",
                    "provider": "maa_snp",
                    "token_signature_verified_by_collector": False,
                }

            package = temporary_path / "certificate-package"
            collection_args = argparse.Namespace(
                allow_development_policy=True,
                backend="azure_sevsnp_cpu",
                challenge=challenge,
                dry_run=False,
                gpu_verifier="local",
                maa_attestation_url=maa_url,
                maa_command=Path("/fake/maa"),
                nras_url="https://nras.attestation.nvidia.com",
                nvattest="/fake/nvattest",
                nvidia_smi="/fake/nvidia-smi",
                output_dir=package,
                policy=REPOSITORY_ROOT / "attestation/policies/gpu_prover_h100.rego",
                run_package=run_output,
                runner_appraisal_policy=root / "appraisal-policy.json",
            )
            with (
                mock.patch.object(measured_collector.os, "geteuid", return_value=0),
                mock.patch.object(measured_collector, "_which", side_effect=lambda value: str(value)),
                mock.patch.object(measured_collector, "_collect_maa", side_effect=fake_maa),
            ):
                collected = measured_collector.collect(collection_args)
            self.assertFalse(collected["accepted"])
            self.assertEqual(collected["statement_sha256"], run_report["statement_sha256"])
            bundle = json.loads((package / "bundle-root/run-bundle.json").read_bytes())
            self.assertEqual(bundle["statement_sha256"], run_report["statement_sha256"])

            policy_dir = temporary_path / "outer-policy"
            policy_dir.mkdir()
            appraiser = policy_dir / "azure-appraiser"
            claim_names = sorted(outer_appraiser.AZURE_CLAIM_KEYS)
            appraiser_source = f'''#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--backend", required=True)
names={json.dumps(sorted([
    "maa-token", "snp-report", "runtime-data", "hcl-report", "hcl-runtime-data",
    "ak-public", "ak-certificate", "quote-message", "quote-signature", "quote-pcrs",
    "event-log", "policy", "expected-binding-sha256", "pcr23-before", "pcr23-after",
    "pcr23-after-start", "runner-transcript", "runner-job-spec", "runner-appraisal-policy",
    "measured-run-package", "expected-user-claims-sha512", "expected-attestation-url",
    "expected-maa-issuer", "expected-maa-audience", "expected-maa-provider"
]))}
for name in names: p.add_argument("--"+name, required=True)
a=p.parse_args()
def h(name): return hashlib.sha256(Path(getattr(a,name.replace("-","_"))).read_bytes()).hexdigest()
now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
claims={{name: True for name in {json.dumps(claim_names)}}}
claims["tee"]="amd_sev_snp"
claims["accelerator_attestation_bound_to_cvm"]="not_applicable"
claims["pre_run_accelerator_gate_valid"]="not_applicable"
out={{
"accepted":True,"ak_certificate_sha256":h("ak-certificate"),"ak_public_sha256":h("ak-public"),
"binding_sha256":a.expected_binding_sha256,"claims":claims,"event_log_sha256":h("event-log"),
"hcl_report_sha256":h("hcl-report"),"hcl_runtime_data_sha256":h("hcl-runtime-data"),
"kind":"sparkinterval_azure_sevsnp_vtpm_appraisal","maa_attestation_url":a.expected_attestation_url,
"maa_audience":a.expected_maa_audience,"maa_issuer":a.expected_maa_issuer,
"maa_provider":a.expected_maa_provider,"maa_token_sha256":h("maa-token"),
"not_after_utc":(now+dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
"not_before_utc":(now-dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
"pcr_selection":"sha256:0,1,2,3,4,5,6,7,23","pcr23_after_sha256":h("pcr23-after"),
"pcr23_before_sha256":h("pcr23-before"),"quote_message_sha256":h("quote-message"),
"quote_pcrs_sha256":h("quote-pcrs"),"quote_signature_sha256":h("quote-signature"),
"runtime_data_sha256":h("runtime-data"),"schema_version":1,"snp_report_sha256":h("snp-report"),
"user_claims_sha512":a.expected_user_claims_sha512}}
print(json.dumps(out,sort_keys=True,separators=(",",":")),end="")
'''
            appraiser.write_text(appraiser_source)
            appraiser.chmod(0o755)
            appraiser_policy = policy_dir / "azure-policy.json"
            appraiser_policy.write_text("{}")
            composite = {
                "allowed_backends": ["azure_sevsnp_cpu"],
                "azure_appraiser": {
                    "executable_path": str(appraiser),
                    "executable_sha256": hashlib.sha256(appraiser.read_bytes()).hexdigest(),
                    "maa_accepted_audience": "https://attest.azure.net",
                    "maa_accepted_issuer": "https://fixture.eus.attest.azure.net",
                    "maa_accepted_provider": "maa_snp",
                    "maa_attestation_url": maa_url,
                    "policy_path": str(appraiser_policy),
                    "policy_sha256": hashlib.sha256(appraiser_policy.read_bytes()).hexdigest(),
                    "timeout_seconds": 30,
                },
                "kind": "sparkinterval_azure_evidence_appraisal_policy",
                "nvidia_appraiser": None,
                "schema_version": 1,
            }
            composite_path = policy_dir / "composite.json"
            composite_path.write_bytes(runner.canonical_json_bytes(composite))
            outer_args = argparse.Namespace(
                backend="azure_sevsnp_cpu",
                evidence_pack=package / "evidence",
                expected_challenge_file=challenge,
                expected_result_binding_sha256=collected["result_binding_sha256"],
                expected_start_challenge_sha256=challenge_value["nonce"],
                policy=composite_path,
                _test_only_allow_development_runner_policy=True,
            )
            appraised = outer_appraiser.appraise(outer_args)
            self.assertTrue(appraised["accepted"])
            self.assertEqual(appraised["result_binding_sha256"], collected["result_binding_sha256"])

    def test_job_without_challenge_argument_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "job"
            builder.build(root, "g++")
            value = json.loads((root / "job.json").read_bytes())
            value["command"]["argv"].remove("@challenge@")
            with self.assertRaises(runner.RunnerError):
                runner.validate_job_spec(value)

    def test_h100_gate_dry_run_derives_bound_nonce_without_releasing_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "run"
            package_root.mkdir()
            challenge = "24" * 32
            job_binding = "81" * 32
            args = argparse.Namespace(
                allow_development_policy=False,
                challenge_expires_at="2035-01-01T00:00:00Z",
                challenge_nonce=challenge,
                dry_run=True,
                job_binding=job_binding,
                nras_url="https://nras.attestation.nvidia.com",
                nvattest="/usr/local/bin/nvattest",
                nvidia_smi="/usr/bin/nvidia-smi",
                package_root=package_root,
                policy=REPOSITORY_ROOT / "attestation/policies/gpu_prover_h100.rego",
                record_path=Path("runner/h100-gate.json"),
                ttl_seconds=300,
                verifier="remote",
            )
            result = h100_gate.collect(args)
            self.assertFalse(result["accepted"])
            self.assertEqual(result["classification"], "h100_pre_run_gate_dry_run_no_evidence")
            self.assertEqual(
                result["gate_nonce"], h100_gate.derive_gate_nonce(challenge, job_binding)
            )
            self.assertFalse((package_root / "runner/h100-gate.json").exists())
            self.assertFalse((package_root / "runner/h100-pre-run-evidence").exists())

    def test_h100_input_release_requires_pinned_run_bound_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "job"
            builder.build(root, "g++")
            value = json.loads((root / "job.json").read_bytes())
            value["backend"] = "azure_ncc40ads_h100_v5"
            value["input_artifact"]["release_mode"] = "relying_party_after_h100_gate"
            value["input_artifact"]["release_argv"] = [
                "artifacts/unpinned-input-client",
                "@challenge@",
                "@job_binding@",
                "@input@",
            ]
            with self.assertRaisesRegex(
                runner.RunnerError, "executable closure artifact"
            ):
                runner.validate_job_spec(value)

            value["input_artifact"]["release_argv"][0] = (
                "artifacts/cubic_sum_div_three_20000"
            )
            value["input_artifact"]["release_argv"].remove("@challenge@")
            with self.assertRaisesRegex(runner.RunnerError, "must contain @challenge@"):
                runner.validate_job_spec(value)

    def test_archive_rejects_links_and_traversal_and_cleans_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            (root / "regular").write_bytes(b"ok")
            (root / "link").symlink_to("regular")
            archive = Path(temporary) / "bad.tar"
            with self.assertRaises(measured_collector.ArchiveError):
                measured_collector.create_archive(root, archive)
            self.assertFalse(archive.exists())

            malicious = Path(temporary) / "traversal.tar"
            with tarfile.open(malicious, "w") as output:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                info.uid = info.gid = info.mtime = 0
                output.addfile(info, io.BytesIO(b"x"))
            extracted = Path(temporary) / "extracted"
            with self.assertRaises(measured_collector.ArchiveError):
                measured_collector.extract_archive(malicious, extracted)
            self.assertFalse(extracted.exists())

    def test_archive_fails_closed_if_regular_file_is_swapped_for_symlink_at_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            victim = root / "victim"
            victim.write_bytes(b"reviewed")
            outside = Path(temporary) / "outside-secret"
            outside.write_bytes(b"must-not-be-archived")
            destination = Path(temporary) / "result.tar"
            real_open = archive_transport.os.open
            swapped = False

            def adversarial_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if path == "victim" and dir_fd is not None and not swapped:
                    swapped = True
                    victim.unlink()
                    victim.symlink_to(outside)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch.object(
                archive_transport.os, "open", side_effect=adversarial_open
            ):
                with self.assertRaises(archive_transport.ArchiveError):
                    archive_transport.create_archive(root, destination)
            self.assertTrue(swapped)
            self.assertFalse(destination.exists())

    def test_archive_rejects_hard_linked_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            original = root / "original"
            original.write_bytes(b"same inode")
            (root / "alias").hardlink_to(original)
            destination = Path(temporary) / "result.tar"
            with self.assertRaisesRegex(archive_transport.ArchiveError, "hard-linked"):
                archive_transport.create_archive(root, destination)
            self.assertFalse(destination.exists())

    def test_archive_extraction_fails_closed_if_input_is_swapped_for_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            first_source = temporary_root / "first-source"
            second_source = temporary_root / "second-source"
            first_source.mkdir()
            second_source.mkdir()
            (first_source / "value").write_bytes(b"reviewed")
            (second_source / "value").write_bytes(b"substituted")
            archive = temporary_root / "input.tar"
            replacement = temporary_root / "replacement.tar"
            archive_transport.create_archive(first_source, archive)
            archive_transport.create_archive(second_source, replacement)
            destination = temporary_root / "extracted"
            real_open = archive_transport.os.open
            swapped = False

            def adversarial_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if Path(path) == archive and not swapped:
                    swapped = True
                    archive.unlink()
                    archive.symlink_to(replacement)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch.object(
                archive_transport.os, "open", side_effect=adversarial_open
            ):
                with self.assertRaises(archive_transport.ArchiveError):
                    archive_transport.extract_archive(archive, destination)
            self.assertTrue(swapped)
            self.assertFalse(destination.exists())

    def test_legacy_h100_collector_calls_gpu_adapter_with_exact_arity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            challenge_path = temporary_path / "challenge.json"
            challenge = write_challenge(challenge_path)
            policy = temporary_path / "policy.rego"
            policy.write_text("package test\n")
            args = mock.Mock(
                challenge=challenge_path,
                backend="azure_ncc40ads_h100_v5",
                statement_sha256="ab" * 32,
                statement_file=None,
                dry_run=False,
                output_dir=temporary_path / "evidence",
                policy=policy,
                maa_command=Path("/fake/maa"),
                maa_attestation_url=(
                    "https://provider.eus.attest.azure.net/attest/SevSnpVm"
                    "?api-version=2022-08-01"
                ),
                nvattest="nvattest",
                nvidia_smi="nvidia-smi",
                gpu_verifier="local",
                nras_url="https://nras.attestation.nvidia.com",
            )
            gpu = mock.Mock(return_value={"gpu": "record"})
            with (
                mock.patch.object(collector.os, "geteuid", return_value=0),
                mock.patch.object(collector, "_which", side_effect=lambda value: str(value)),
                mock.patch.object(collector, "_require_gpu_state", return_value={"ready": True}),
                mock.patch.object(collector, "_collect_maa", return_value={"maa": "record"}),
                mock.patch.object(collector, "_collect_gpu", gpu),
                mock.patch.object(collector, "_collect_tpm", return_value={"tpm": "record"}),
                mock.patch.object(collector, "require_current_challenge_window"),
            ):
                result = collector.collect(args)
            self.assertFalse(result["accepted"])
            gpu.assert_called_once()
            self.assertEqual(
                gpu.call_args.args,
                (
                    mock.ANY,
                    "nvattest",
                    policy,
                    collector.derive_binding_nonce(challenge["nonce"], args.statement_sha256),
                    "local",
                    "https://nras.attestation.nvidia.com",
                ),
            )


if __name__ == "__main__":
    unittest.main()
