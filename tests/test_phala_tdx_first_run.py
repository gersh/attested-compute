# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Local end-to-end dry run of the Phala/dstack TDX campaign path.

This is the test that says whether the repository is ready for a first real
Phala run.  It exercises, locally, everything except the TEE itself:

* the separately named TDX acceptance route in ``tg_verifier/campaign_io.py``,
  including that it and the Azure route reject each other's environments;
* the canonical signed payload, in Python and in Lean, byte for byte;
* the deterministic P-256 signer, against the RFC 6979 test vector;
* the campaign image: built from ``proof_build/ch25_a7_phala_tdx/Dockerfile``
  and actually run, executing the real CH25 Lemma A.7 FLINT/Arb replay and
  emitting the registered result plus an enclave-signed receipt; and
* that the receipt the container produced is exactly the one pinned in
  ``SparkInterval/Tests/PhalaTdxDryRunTest.lean``, which drives it to the Lean
  campaign theorem.

The Docker stage is skipped when Docker is unavailable or cannot run
``linux/amd64``; the rest always runs.  Set
``SPARKINTERVAL_PHALA_TDX_RUN_DOCKER=0`` to skip it explicitly.

Nothing here is attested and nothing here is a production claim: the signing
key is the committed stand-in, the A.7 artifact is a freshly generated fixture
rather than the retained production artifact, and the quote/appraisal files
are labelled placeholders.
"""

from __future__ import annotations

import gzip
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    AZURE_MEASURED_WORKER_BACKEND_ENV,
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    AZURE_MEASURED_WORKER_SCOPE,
    AZURE_MEASURED_WORKER_SCOPE_ENV,
    MeasuredWorkerScopeError,
    PhalaTdxWorkerScopeError,
    phala_tdx_worker_environment,
    require_azure_measured_worker_for_workload,
    require_phala_tdx_worker_for_workload,
)
from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    SIGNED_FIELDS,
    canonical_signed_payload,
    public_key_hex,
    report_data_hash,
    sign_digest_hex,
    statement_digest,
    verify_digest_hex,
    verify_receipt,
)

DATA = ROOT / "tests/data/phala_tdx_dry_run"
LEAN_DRY_RUN = ROOT / "SparkInterval/Tests/PhalaTdxDryRunTest.lean"
LEAN_PIN = ROOT / "SparkInterval/Execution/PhalaTdxAttestation.lean"
LEAN_REGISTRY = ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
DOCKERFILE = ROOT / "proof_build/ch25_a7_phala_tdx/Dockerfile"
IMAGE_TAG = "sparkinterval-ch25-a7-phala-tdx:dryrun"

REGISTERED_INPUT = (
    b'{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":'
    b'"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
)

# The dry-run job identity.  These are also the literals in the Lean dry-run
# enclave pin; the tests below assert the two agree.
DRY_RUN_CHALLENGE = "11" * 32
DRY_RUN_JOB_BINDING = "22" * 32
DRY_RUN_APP_ID = "327d84eaf0cfb23bfc4260453516a9afc0287705"
DRY_RUN_COMPOSE_HASH = (
    "44c2baa7f7fbf92c08d9800071ec0d3d21404c07af1db8254ebd77c717b8e35c"
)
DRY_RUN_IMAGE_DIGEST = (
    "sha256:43233eef77b7ad2463aa6b352a7459ffd42b0d1f8b9373858889d8f1bc0c073c"
)
DRY_RUN_ISSUED_AT = "2026-07-26T00:00:00Z"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lean_string_literals(text: str, name: str) -> str:
    """Extract a Lean `def name : String := "…" ++ "…"` value."""

    match = re.search(
        rf"def\s+{re.escape(name)}\s*:\s*String\s*:=\s*((?:\s*\"[^\"]*\"\s*(?:\+\+)?)+)",
        text,
    )
    assert match, f"cannot find Lean definition {name}"
    return "".join(re.findall(r'"([^"]*)"', match.group(1)))


def _docker_available() -> bool:
    if os.environ.get("SPARKINTERVAL_PHALA_TDX_RUN_DOCKER") == "0":
        return False
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64",
         DOCKER_PROBE_IMAGE, "true"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    return probe.returncode == 0


DOCKER_PROBE_IMAGE = "debian:bookworm-slim"

EMITTER = ROOT / "proof_build/ch25_a7_phala_tdx/emit_phala_tdx_evidence.py"
EXTRACTOR = ROOT / "tools/tg_phala_tdx_extract_evidence.py"


class _UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


class MockGetKeyAgent:
    """The one dstack method the campaign entry point now calls.

    The campaign container no longer receives the signing key as a file: it
    asks the guest agent for it, exactly as the prelude did, and refuses
    unless what it gets reproduces the report-data commitment the prelude
    recorded.  So the dry run must answer `POST /GetKey`, and it answers with
    the committed stand-in scalar -- which is why the receipt the container
    produces is still byte-for-byte the one pinned in Lean.
    """

    def __init__(self, socket_path: Path, key_hex: str) -> None:
        self.socket_path = socket_path
        self.calls: list[str] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:  # noqa: N802
                pass

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                if length:
                    self.rfile.read(length)
                method = self.path.lstrip("/").split("?")[0]
                outer.calls.append(method)
                if method == "GetKey":
                    body = json.dumps({"key": key_hex, "signature_chain": []})
                    status = 200
                else:
                    body = json.dumps({"error": f"no such method {method}"})
                    status = 404
                encoded = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self._server = _UnixHTTPServer(str(socket_path), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    def __enter__(self) -> "MockGetKeyAgent":
        self._thread.start()
        os.chmod(self.socket_path, 0o666)
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


class GuardSeparationTests(unittest.TestCase):
    """The two acceptance routes must not be able to admit each other."""

    def test_tdx_route_rejects_an_azure_environment(self) -> None:
        azure = {
            AZURE_MEASURED_WORKER_SCOPE_ENV: AZURE_MEASURED_WORKER_SCOPE,
            AZURE_MEASURED_WORKER_BACKEND_ENV: "azure_sevsnp_cpu",
            AZURE_MEASURED_WORKER_CHALLENGE_ENV: "aa" * 32,
            AZURE_MEASURED_WORKER_JOB_BINDING_ENV: "bb" * 32,
        }
        with self.assertRaises(PhalaTdxWorkerScopeError):
            require_phala_tdx_worker_for_workload(
                exact_production=True, work_bounds=(), environment=azure
            )

    def test_azure_route_rejects_a_tdx_environment(self) -> None:
        tdx = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        with self.assertRaises(MeasuredWorkerScopeError):
            require_azure_measured_worker_for_workload(
                exact_production=True, work_bounds=(), environment=tdx
            )

    def test_tdx_route_rejects_a_mixed_scope_environment(self) -> None:
        mixed = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        mixed[AZURE_MEASURED_WORKER_SCOPE_ENV] = AZURE_MEASURED_WORKER_SCOPE
        with self.assertRaises(PhalaTdxWorkerScopeError):
            require_phala_tdx_worker_for_workload(
                exact_production=True, work_bounds=(), environment=mixed
            )

    def test_tdx_route_accepts_only_its_own_binding(self) -> None:
        tdx = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        job = require_phala_tdx_worker_for_workload(
            exact_production=True, work_bounds=(), environment=tdx
        )
        self.assertEqual(job["backend"], "phala_dstack_tdx_cpu")
        self.assertEqual(job["app_id"], DRY_RUN_APP_ID)
        self.assertEqual(job["compose_hash"], DRY_RUN_COMPOSE_HASH)

    def test_azure_guard_source_is_unchanged_by_the_tdx_route(self) -> None:
        """The Azure functions must not reference anything TDX."""

        text = (ROOT / "tg_verifier/campaign_io.py").read_text(encoding="utf-8")
        azure_block = text[
            text.index("def require_azure_measured_worker(") : text.index(
                "# Phala/dstack Intel TDX acceptance route"
            )
        ]
        for token in ("phala", "PHALA", "PhalaTdx", "tdx"):
            self.assertNotIn(token, azure_block)


class SignerTests(unittest.TestCase):
    def test_rfc6979_nonce_matches_the_published_vector(self) -> None:
        # RFC 6979 A.2.5, P-256/SHA-256, message "sample".  Our signer
        # additionally normalizes to low `s`, so `r` must match exactly and
        # `s` must be the published value negated modulo the group order.
        private = int(
            "C9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721",
            16,
        )
        order = int(
            "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551",
            16,
        )
        digest = hashlib.sha256(b"sample").hexdigest()
        signature = sign_digest_hex(private, digest)
        self.assertEqual(
            signature[:64],
            "efd48b2aacb6a8fd1140dd9cd45e81d69d2c877b56aaf991c34d0ea84eaf3716",
        )
        published_s = int(
            "F7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8",
            16,
        )
        self.assertEqual(int(signature[64:], 16), order - published_s)
        self.assertTrue(
            verify_digest_hex(public_key_hex(private), digest, signature)
        )

    def test_signing_is_deterministic(self) -> None:
        private = int(DATA_KEY_HEX, 16)
        digest = hashlib.sha256(b"determinism").hexdigest()
        self.assertEqual(
            sign_digest_hex(private, digest), sign_digest_hex(private, digest)
        )

    def test_canonical_payload_rejects_missing_and_extra_fields(self) -> None:
        fields = {name: "x" for name in SIGNED_FIELDS}
        canonical_signed_payload(fields)
        with self.assertRaises(Exception):
            canonical_signed_payload({k: v for k, v in list(fields.items())[:-1]})
        with self.assertRaises(Exception):
            canonical_signed_payload({**fields, "extra": "x"})


DATA_KEY_HEX = (
    DATA / "enclave-signing-key.NOT-SECRET.hex"
).read_text(encoding="ascii").strip()


class LeanPinAgreementTests(unittest.TestCase):
    """The Python and Lean sides must pin the same literals."""

    def setUp(self) -> None:
        self.pin_text = LEAN_PIN.read_text(encoding="utf-8")
        self.dry_run_text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        self.registry_text = LEAN_REGISTRY.read_text(encoding="utf-8")

    def test_dry_run_public_key_is_the_lean_pin(self) -> None:
        expected = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertIn(expected[:64], self.pin_text)
        self.assertIn(expected[64:], self.pin_text)
        self.assertEqual(
            expected, _lean_string_literals(self.dry_run_text, "dryRunPinnedKey")
        )

    def test_dry_run_pin_records_the_placeholder_evidence_hashes(self) -> None:
        self.assertIn(
            _sha256_file(DATA / "dcap-qvl-policy.json"), self.pin_text
        )
        self.assertIn(
            _sha256_file(DATA / "dcap-qvl-artifact.sha256"), self.pin_text
        )
        self.assertIn(DRY_RUN_APP_ID, self.pin_text)
        self.assertIn(DRY_RUN_COMPOSE_HASH, self.pin_text)
        self.assertIn(DRY_RUN_IMAGE_DIGEST.split(":", 1)[1], self.pin_text)

    def test_dry_run_pin_has_no_attestation_authority(self) -> None:
        block = self.pin_text[
            self.pin_text.index("ch25A7BoundaryLocalDryRunV1 =>") :
        ]
        self.assertIn("attestationAuthority := false", block)

    def test_production_pin_is_not_installed(self) -> None:
        block = self.pin_text[
            self.pin_text.index("ch25A7BoundaryProductionV1 =>") : self.pin_text.index(
                "ch25A7BoundaryLocalDryRunV1 =>"
            )
        ]
        self.assertIn('enclavePublicKeyHex := ""', block)

    def test_registered_algorithm_literals_match_the_producer(self) -> None:
        workload = (
            ROOT / "tools/tg_a7_phala_tdx_workload.py"
        ).read_text(encoding="utf-8")
        for literal in (
            "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1",
            "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa",
            "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674",
            "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e",
            "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5",
        ):
            self.assertIn(literal, workload)
            self.assertIn(literal, self.registry_text)

    def test_canonical_payload_field_order_matches_lean(self) -> None:
        lean = LEAN_PIN.read_text(encoding="utf-8")
        body = lean[lean.index("def PhalaTdxReceipt.canonicalSignedPayload") :]
        body = body[: body.index("/-- SHA-256 of the canonical signed payload")]
        found = re.findall(r'phalaTdxCommittedField\s+"([a-z0-9_]+)"', body)
        self.assertEqual(tuple(found), SIGNED_FIELDS)


class DryRunReceiptTests(unittest.TestCase):
    """The receipt pinned in Lean is self-consistent and verifies."""

    def setUp(self) -> None:
        self.fields = self._lean_receipt_fields()

    @staticmethod
    def _lean_receipt_fields() -> dict[str, str]:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        body = text[text.index("def dryRunReceipt") : text.index(
            "def dryRunStatementDigest"
        )]
        lean_to_wire = {
            "algorithmId": "algorithm_id",
            "algorithmHash": "algorithm_hash",
            "inputHash": "input_hash",
            "parametersHash": "parameters_hash",
            "domainHash": "domain_hash",
            "result": "result",
            "outputHash": "output_hash",
            "challengeNonce": "challenge_nonce",
            "jobBindingHash": "job_binding_sha256",
            "appId": "app_id",
            "composeHash": "compose_hash",
            "imageDigest": "image_digest",
            "quoteHash": "tdx_quote_sha256",
            "quoteAppraisalHash": "dcap_qvl_output_sha256",
            "quoteAppraisalPolicyHash": "dcap_qvl_policy_sha256",
            "quoteAppraisalArtifactHash": "dcap_qvl_artifact_sha256",
            "reportDataHash": "report_data_sha256",
            "issuedAt": "issued_at",
        }
        fields: dict[str, str] = {}
        for lean_name, wire_name in lean_to_wire.items():
            match = re.search(
                rf"\b{lean_name}\s*:=\s*((?:\s*\"[^\"]*\"\s*(?:\+\+)?)+)", body
            )
            assert match, f"cannot find receipt field {lean_name}"
            fields[wire_name] = "".join(re.findall(r'"([^"]*)"', match.group(1)))
        return fields

    def test_lean_receipt_digest_matches_python(self) -> None:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        pinned = _lean_string_literals(text, "dryRunStatementDigest")
        self.assertEqual(statement_digest(self.fields), pinned)

    def test_lean_receipt_signature_verifies(self) -> None:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        body = text[text.index("def dryRunReceipt") :]
        match = re.search(
            r'signatureHex\s*:=\s*((?:\s*"[^"]*"\s*(?:\+\+)?)+)', body
        )
        assert match
        signature = "".join(re.findall(r'"([^"]*)"', match.group(1)))
        key = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertTrue(
            verify_digest_hex(key, statement_digest(self.fields), signature)
        )

    def test_report_data_binds_the_key_to_the_challenge(self) -> None:
        key = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertEqual(
            self.fields["report_data_sha256"],
            report_data_hash(
                enclave_public_key_hex=key,
                challenge_nonce=self.fields["challenge_nonce"],
                job_binding=self.fields["job_binding_sha256"],
            ),
        )

    def test_output_hash_binds_the_result(self) -> None:
        self.assertEqual(
            self.fields["output_hash"],
            hashlib.sha256(self.fields["result"].encode("ascii")).hexdigest(),
        )

    def test_placeholder_evidence_hashes_match_the_committed_files(
        self,
    ) -> None:
        self.assertEqual(
            self.fields["tdx_quote_sha256"],
            _sha256_file(DATA / "tdx-quote.NOT-A-QUOTE.bin"),
        )
        self.assertEqual(
            self.fields["dcap_qvl_output_sha256"],
            _sha256_file(DATA / "dcap-qvl-appraisal.NOT-AN-APPRAISAL.json"),
        )


class ContainerDryRunTests(unittest.TestCase):
    """Build and run the campaign image; compare with the Lean literals."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.docker = _docker_available()
        if not cls.docker:
            return
        build = subprocess.run(
            [
                "docker", "build", "--platform", "linux/amd64",
                "-f", str(DOCKERFILE), "-t", IMAGE_TAG, str(ROOT),
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        assert build.returncode == 0, f"image build failed:\n{build.stderr[-4000:]}"

    def test_container_reproduces_the_pinned_receipt(self) -> None:
        if not self.docker:
            self.skipTest("docker cannot run linux/amd64 here")

        with tempfile.TemporaryDirectory() as workspace:
            work = Path(workspace)
            inputs = work / "input"
            evidence = work / "evidence"
            outputs = work / "out"
            inputs.mkdir()
            evidence.mkdir()
            outputs.mkdir()
            (inputs / "registered-input.json").write_bytes(REGISTERED_INPUT)
            with gzip.open(
                DATA / "a7_boundary.fixture.json.gz", "rb"
            ) as source:
                (inputs / "a7_boundary.json").write_bytes(source.read())
            # The key is NOT staged as an input any more: the container
            # derives it.  What is staged is the prelude summary it checks the
            # derived key against.
            key = public_key_hex(int(DATA_KEY_HEX, 16))
            (evidence / "prelude-summary.json").write_text(
                json.dumps(
                    {
                        "kind": "sparkinterval.phala-tdx-prelude-summary.v1",
                        "challenge_nonce": DRY_RUN_CHALLENGE,
                        "job_binding_sha256": DRY_RUN_JOB_BINDING,
                        "enclave_public_key": key,
                        "report_data_sha256": report_data_hash(
                            enclave_public_key_hex=key,
                            challenge_nonce=DRY_RUN_CHALLENGE,
                            job_binding=DRY_RUN_JOB_BINDING,
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            shutil.copyfile(
                DATA / "tdx-quote.NOT-A-QUOTE.bin", inputs / "tdx-quote.bin"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-appraisal.NOT-AN-APPRAISAL.json",
                inputs / "dcap-qvl-appraisal.json",
            )
            shutil.copyfile(
                DATA / "dcap-qvl-policy.json", inputs / "dcap-qvl-policy.json"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-artifact.sha256",
                inputs / "dcap-qvl-artifact.sha256",
            )
            for path in inputs.rglob("*"):
                os.chmod(path, 0o444)
            os.chmod(inputs, 0o555)

            uid, gid = os.getuid(), os.getgid()
            socket_dir = Path(tempfile.mkdtemp(prefix="phdry-"))
            socket_path = socket_dir / "d.sock"
            try:
                with MockGetKeyAgent(socket_path, DATA_KEY_HEX) as agent:
                    run = subprocess.run(
                        [
                            "docker", "run", "--rm", "--platform", "linux/amd64",
                            "--user", f"{uid}:{gid}",
                            "--network", "none", "--read-only",
                            "-v", f"{inputs}:/workspace/input:ro",
                            "-v", f"{evidence}:/workspace/evidence:ro",
                            "-v", f"{outputs}:/workspace/outroot",
                            "-v", f"{socket_path}:/var/run/dstack.sock",
                            "--tmpfs",
                            f"/workspace/runtime:exec,size=64m,uid={uid},gid={gid}",
                            "--tmpfs",
                            f"/workspace/keys:size=1m,mode=0700,uid={uid},gid={gid}",
                            "-e", "TG_OUTPUT_ROOT=/workspace/outroot/output",
                            "-e", "TG_ENCLAVE_KEY_ROOT=/workspace/keys",
                            "-e",
                            "TG_PRELUDE_SUMMARY="
                            "/workspace/evidence/prelude-summary.json",
                            "-e", f"TG_FINAL_IMAGE_REFERENCE={DRY_RUN_IMAGE_DIGEST}",
                            "-e", f"TG_ISSUED_AT={DRY_RUN_ISSUED_AT}",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE="
                            "sparkinterval.phala-tdx-measured-worker.v1",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND="
                            "phala_dstack_tdx_cpu",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE="
                            + DRY_RUN_CHALLENGE,
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256="
                            + DRY_RUN_JOB_BINDING,
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID="
                            + DRY_RUN_APP_ID,
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH="
                            + DRY_RUN_COMPOSE_HASH,
                            "-e", "SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=1",
                            IMAGE_TAG,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=7200,
                    )
            finally:
                shutil.rmtree(socket_dir, ignore_errors=True)
            self.assertEqual(
                run.returncode,
                0,
                f"campaign run failed:\n{run.stdout[-4000:]}\n{run.stderr[-4000:]}",
            )
            self.assertIn(
                "GetKey",
                agent.calls,
                "the container did not derive the signing key from the socket",
            )
            self.assertNotIn(DATA_KEY_HEX, run.stdout + run.stderr)

            produced = outputs / "output"
            self.assertEqual(
                (produced / "registered-result.txt").read_bytes(), b"true"
            )
            replay = json.loads(
                (produced / "work" / "a7-replay.json").read_text("utf-8")
            )
            self.assertIs(replay["accepted"], True)
            self.assertIs(
                replay["external_analytic_verification_complete"], True
            )
            self.assertIs(replay["lean_atom_discharged"], False)
            # The fixture is deliberately not the retained artifact.
            self.assertIs(replay["artifact_bytes_match_pinned_sha256"], False)

            receipt = json.loads(
                (produced / "enclave-receipt.json").read_text("utf-8")
            )
            self.assertIs(receipt["local_dry_run"], True)
            key = public_key_hex(int(DATA_KEY_HEX, 16))
            self.assertTrue(verify_receipt(receipt, enclave_public_key=key))

            pinned = DryRunReceiptTests._lean_receipt_fields()
            self.assertEqual(
                receipt["signed_fields"],
                pinned,
                "the container's receipt no longer matches the Lean dry-run "
                "literals; regenerate SparkInterval/Tests/PhalaTdxDryRunTest.lean",
            )
            text = LEAN_DRY_RUN.read_text(encoding="utf-8")
            self.assertEqual(
                receipt["statement_sha256"],
                _lean_string_literals(text, "dryRunStatementDigest"),
            )
            body = text[text.index("def dryRunReceipt") :]
            match = re.search(
                r'signatureHex\s*:=\s*((?:\s*"[^"]*"\s*(?:\+\+)?)+)', body
            )
            assert match
            self.assertEqual(
                receipt["signature"],
                "".join(re.findall(r'"([^"]*)"', match.group(1))),
            )

            self._evidence_round_trips(work, inputs, evidence, produced)

    def test_the_committed_campaign_entrypoint_runs_end_to_end(self) -> None:
        """Run the measured campaign entry point itself, not the image's.

        This is the closest local proxy for what the CVM will actually
        execute: the *committed* `docker-compose.yaml` block scalar, verbatim.
        It writes the three measured sources to /tmp, sources the job scope
        that the prelude left on the shared volume, re-derives the signing key
        from the dstack socket onto a container-local tmpfs, runs the replay,
        signs the receipt, prints the evidence, and holds the container open.

        The first real run got all the way through attestation and then died
        here, on a shared-volume assumption that a unit test could not see.
        """

        if not self.docker:
            self.skipTest("docker cannot run linux/amd64 here")
        try:
            import yaml  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            self.skipTest("PyYAML is unavailable")

        compose = yaml.safe_load(
            (ROOT / "proof_build/ch25_a7_phala_tdx/docker-compose.yaml").read_text(
                encoding="utf-8"
            )
        )
        entrypoint = compose["services"]["campaign"]["entrypoint"]
        self.assertEqual(entrypoint[:2], ["/bin/bash", "-ec"])

        with tempfile.TemporaryDirectory() as workspace:
            work = Path(workspace)
            shared = work / "shared"
            inputs = shared / "input"
            evidence = shared / "evidence"
            outputs = work / "out"
            inputs.mkdir(parents=True)
            evidence.mkdir(parents=True)
            outputs.mkdir()

            key = public_key_hex(int(DATA_KEY_HEX, 16))
            (inputs / "job-scope.env").write_text(
                f"SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID={DRY_RUN_APP_ID}\n"
                "SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH="
                f"{DRY_RUN_COMPOSE_HASH}\n",
                encoding="ascii",
            )
            (inputs / "registered-input.json").write_bytes(REGISTERED_INPUT)
            with gzip.open(DATA / "a7_boundary.fixture.json.gz", "rb") as source:
                (inputs / "a7_boundary.json").write_bytes(source.read())
            shutil.copyfile(
                DATA / "tdx-quote.NOT-A-QUOTE.bin", inputs / "tdx-quote.bin"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-appraisal.NOT-AN-APPRAISAL.json",
                inputs / "dcap-qvl-appraisal.json",
            )
            shutil.copyfile(
                DATA / "dcap-qvl-policy.json", inputs / "dcap-qvl-policy.json"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-artifact.sha256",
                inputs / "dcap-qvl-artifact.sha256",
            )
            (evidence / "prelude-summary.json").write_text(
                json.dumps(
                    {
                        "kind": "sparkinterval.phala-tdx-prelude-summary.v1",
                        "challenge_nonce": DRY_RUN_CHALLENGE,
                        "job_binding_sha256": DRY_RUN_JOB_BINDING,
                        "enclave_public_key": key,
                        "report_data_sha256": report_data_hash(
                            enclave_public_key_hex=key,
                            challenge_nonce=DRY_RUN_CHALLENGE,
                            job_binding=DRY_RUN_JOB_BINDING,
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            # The prelude-only evidence the emitter also expects.
            for name, raw in (
                ("dstack-info.json", b'{"app_id":"placeholder"}'),
                ("dstack-event-log.json", b"[]"),
                ("dcap-qvl-decode.json", b'{"header":{}}'),
                ("dcap-qvl-verify.stderr", b""),
                ("dcap-qvl-strict.json", b'{"passed":false}'),
                ("rtmr-replay.json", b'{"replayed_rtmrs":{}}'),
            ):
                (evidence / name).write_bytes(raw)

            uid, gid = os.getuid(), os.getgid()
            socket_dir = Path(tempfile.mkdtemp(prefix="phdry2-"))
            socket_path = socket_dir / "d.sock"
            try:
                with MockGetKeyAgent(socket_path, DATA_KEY_HEX) as agent:
                    run = subprocess.run(
                        [
                            "docker", "run", "--rm", "--platform", "linux/amd64",
                            "--user", f"{uid}:{gid}",
                            "--network", "none", "--read-only",
                            "--entrypoint", "/bin/bash",
                            "-v", f"{shared}:/workspace/shared:ro",
                            "-v", f"{outputs}:/workspace/out",
                            "-v", f"{socket_path}:/var/run/dstack.sock",
                            "--tmpfs",
                            f"/workspace/runtime:exec,size=64m,uid={uid},gid={gid}",
                            "--tmpfs",
                            f"/workspace/keys:size=1m,mode=0700,uid={uid},gid={gid}",
                            "--tmpfs", f"/tmp:size=32m,uid={uid},gid={gid}",
                            "-e", "TG_INPUT_ROOT=/workspace/shared/input",
                            "-e", "TG_OUTPUT_ROOT=/workspace/out/output",
                            "-e", "TG_ENCLAVE_KEY_ROOT=/workspace/keys",
                            "-e",
                            "TG_PHALA_TDX_KEY_DERIVER="
                            "/tmp/prelude_phala_tdx_inputs.py",
                            "-e",
                            "TG_PRELUDE_SUMMARY="
                            "/workspace/shared/evidence/prelude-summary.json",
                            "-e", "TG_EVIDENCE_HOLD_SECONDS=1",
                            "-e", f"TG_FINAL_IMAGE_REFERENCE={DRY_RUN_IMAGE_DIGEST}",
                            "-e", f"TG_ISSUED_AT={DRY_RUN_ISSUED_AT}",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE="
                            "sparkinterval.phala-tdx-measured-worker.v1",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND="
                            "phala_dstack_tdx_cpu",
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE="
                            + DRY_RUN_CHALLENGE,
                            "-e",
                            "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256="
                            + DRY_RUN_JOB_BINDING,
                            "-e", "SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=1",
                            IMAGE_TAG,
                            "-ec", entrypoint[2],
                        ],
                        capture_output=True,
                        text=True,
                        timeout=7200,
                    )
            finally:
                shutil.rmtree(socket_dir, ignore_errors=True)

            self.assertEqual(
                run.returncode,
                0,
                f"compose entry point failed:\n{run.stdout[-6000:]}\n"
                f"{run.stderr[-6000:]}",
            )
            self.assertIn("GetKey", agent.calls)
            self.assertNotIn(DATA_KEY_HEX, run.stdout)
            self.assertNotIn(DATA_KEY_HEX, run.stderr)

            recovered = work / "recovered"
            extracted = subprocess.run(
                [sys.executable, str(EXTRACTOR), "--out-dir", str(recovered)],
                input=run.stdout,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(
                extracted.returncode,
                0,
                f"evidence extraction failed:\n{extracted.stdout}\n"
                f"{extracted.stderr}",
            )
            receipt = json.loads(
                (recovered / "output/enclave-receipt.json").read_text("utf-8")
            )
            self.assertEqual(
                receipt["signed_fields"],
                DryRunReceiptTests._lean_receipt_fields(),
                "the receipt recovered from the container's log is not the "
                "one pinned in Lean",
            )
            self.assertTrue(verify_receipt(receipt, enclave_public_key=key))
            self.assertEqual(
                (recovered / "output/registered-result.txt").read_bytes(), b"true"
            )
            for path in recovered.rglob("*"):
                if path.is_file():
                    self.assertNotIn(
                        DATA_KEY_HEX, path.read_bytes().decode("latin-1")
                    )

    def _evidence_round_trips(
        self, work: Path, inputs: Path, evidence: Path, produced: Path
    ) -> None:
        """The only channel out of a real CVM, exercised on real output.

        A dstack CVM's volumes are unreachable and `phala cvms logs` drops the
        logs of exited containers, so the campaign prints its evidence and
        stays alive.  This runs the emitter over what the container actually
        produced -- with a real key file present, so the "never printed"
        assertion has something to be about -- and puts the log back through
        the extractor.
        """

        key_file = work / "enclave-signing-key.hex"
        shutil.copyfile(DATA / "enclave-signing-key.NOT-SECRET.hex", key_file)
        emitted = subprocess.run(
            [
                sys.executable, str(EMITTER),
                "--input-root", str(inputs),
                "--evidence-root", str(evidence),
                "--output-root", str(produced),
                "--refuse-if-contains", str(key_file),
                "--campaign-status", "0",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        # Several prelude-only files are absent in a dry run, so a non-zero
        # "required file missing" status is expected; what must hold is that
        # everything present round-trips and the key is nowhere in the log.
        self.assertNotIn(DATA_KEY_HEX, emitted.stdout)
        self.assertNotIn(DATA_KEY_HEX, emitted.stderr)
        self.assertIn("enclave-receipt.json", emitted.stdout)

        recovered = work / "recovered"
        log = work / "run.log"
        log.write_text(emitted.stdout, encoding="utf-8")
        extracted = subprocess.run(
            [
                sys.executable, str(EXTRACTOR),
                "--log", str(log), "--out-dir", str(recovered),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertIn("enclave-receipt.json", extracted.stdout)
        self.assertEqual(
            (recovered / "output/enclave-receipt.json").read_bytes(),
            (produced / "enclave-receipt.json").read_bytes(),
        )
        self.assertEqual(
            (recovered / "output/registered-result.txt").read_bytes(), b"true"
        )
        self.assertEqual(
            (recovered / "input/tdx-quote.bin").read_bytes(),
            (inputs / "tdx-quote.bin").read_bytes(),
        )
        for path in recovered.rglob("*"):
            if path.is_file():
                self.assertNotIn(
                    DATA_KEY_HEX, path.read_bytes().decode("latin-1")
                )


if __name__ == "__main__":
    unittest.main()
