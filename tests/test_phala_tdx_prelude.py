# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The in-CVM prelude, exercised against a mock dstack guest agent.

**No TDX hardware is involved and none is required.**  These tests drive
``proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py`` against an
in-process unix-socket HTTP server that answers ``/Info``, ``/GetKey`` and
``/GetQuote`` the way dstack v0.5.3's guest agent does, and against a stand-in
``dcap-qvl`` that prints canned JSON in the schema dcap-qvl v0.6.1 actually
emits (observed on 2026-07-27 by decoding the upstream sample TDX quote with
the pinned binary).

What that does and does not establish is worth being blunt about.  It
establishes that the prelude speaks the documented wire format, computes the
report-data commitment with ``tg_verifier.phala_tdx_receipt`` rather than a
private copy, refuses every failure mode it is supposed to refuse, and
produces exactly the seven files ``run_phala_tdx_campaign.sh`` requires.  It
establishes **nothing** about a real TD: the quote here is arbitrary bytes, the
appraisal is a fixture, and the real path has never run.

The two byte-pinned downloads -- the ``dcap-qvl`` binary and the retained A.7
artifact -- are pinned by SHA-256 constants in the prelude module.  These
tests rebind those constants in a child interpreter, which is why they need no
network.  There is no environment variable that relaxes either pin.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socketserver
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    P256_GROUP_ORDER,
    public_key_hex,
    report_data_hash,
    report_data_preimage,
)

PRELUDE = ROOT / "proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py"

CHALLENGE = "5c" * 32
JOB_BINDING = "a3" * 32
APP_ID = "9f" * 20
COMPOSE_HASH = "7e" * 32
INSTANCE_ID = ""
IMAGE_DIGEST = "sha256:" + "4e" * 32
ISSUED_AT = "2026-08-01T00:00:00Z"

# A fixed, non-secret P-256 scalar standing in for the dstack-derived one.
MOCK_SCALAR = int(
    "3f1a9c4e2b8d7605af31c29e4d5b6a7089cbe1f23a4d5e6f708192a3b4c5d6e7", 16
)
RTMR3_EVENT_TYPE = 0x08000001


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------


def rtmr3_digest(event: str, payload_hex: str) -> str:
    return hashlib.sha384(
        RTMR3_EVENT_TYPE.to_bytes(4, "little")
        + b":"
        + event.encode("utf-8")
        + b":"
        + bytes.fromhex(payload_hex)
    ).hexdigest()


def replay(history: list[str]) -> str:
    measurement = bytes(48)
    for digest in history:
        content = bytes.fromhex(digest).ljust(48, b"\x00")
        measurement = hashlib.sha384(measurement + content).digest()
    return measurement.hex()


def build_event_log(*, app_id: str = APP_ID, compose_hash: str = COMPOSE_HASH):
    events = []
    for index in (0, 1, 2):
        for step in range(2):
            events.append(
                {
                    "imr": index,
                    "event_type": 4,
                    "digest": hashlib.sha384(
                        f"imr{index}-{step}".encode("ascii")
                    ).hexdigest(),
                    "event": "",
                    "event_payload": "",
                }
            )
    for name, payload in (
        ("system-preparing", ""),
        ("key-provider", hashlib.sha256(b"kp").hexdigest()),
        ("os-image-hash", hashlib.sha256(b"os").hexdigest()),
        ("app-id", app_id),
        ("compose-hash", compose_hash),
        ("instance-id", INSTANCE_ID),
        ("boot-mr-done", ""),
        ("system-ready", ""),
    ):
        events.append(
            {
                "imr": 3,
                "event_type": RTMR3_EVENT_TYPE,
                "digest": rtmr3_digest(name, payload),
                "event": name,
                "event_payload": payload,
            }
        )
    rtmrs = {
        index: replay([e["digest"] for e in events if e["imr"] == index])
        for index in range(4)
    }
    return events, rtmrs


QE_MR_SIGNER = hashlib.sha256(b"mock-qe-signer").hexdigest()
QE_VENDOR_ID = hashlib.md5(b"mock-qe-vendor").hexdigest()
QE_ISV_PROD_ID = 1
QE_ISV_SVN = 8


def build_qe_report() -> str:
    raw = bytearray(384)
    raw[64:96] = hashlib.sha256(b"mock-qe-enclave").digest()
    raw[128:160] = bytes.fromhex(QE_MR_SIGNER)
    raw[256:258] = QE_ISV_PROD_ID.to_bytes(2, "little")
    raw[258:260] = QE_ISV_SVN.to_bytes(2, "little")
    return raw.hex()


MEASUREMENTS = {
    "tee_tcb_svn": "06010300000000000000000000000000",
    "mr_seam": hashlib.sha384(b"mock-mr-seam").hexdigest(),
    "mr_signer_seam": "00" * 48,
    "td_attributes": "0000001000000000",
    "xfam": "e702060000000000",
    "mr_td": hashlib.sha384(b"mock-mr-td").hexdigest(),
}


def build_decode(report_data_padded: str, rtmrs: dict[int, str]) -> dict:
    body = dict(MEASUREMENTS)
    body.update(
        {
            "mr_config_id": "00" * 48,
            "mr_owner": "00" * 48,
            "mr_owner_config": "00" * 48,
            "rt_mr0": rtmrs[0],
            "rt_mr1": rtmrs[1],
            "rt_mr2": rtmrs[2],
            "rt_mr3": rtmrs[3],
            "report_data": report_data_padded,
        }
    )
    return {
        "header": {
            "version": 4,
            "attestation_key_type": 2,
            "tee_type": 129,
            "qe_svn": 0,
            "pce_svn": 0,
            "qe_vendor_id": QE_VENDOR_ID,
            "user_data": "11" * 20,
        },
        "report": {"TD10": body},
        "auth_data": {
            "V4": {
                "ecdsa_signature": "22" * 64,
                "ecdsa_attestation_key": "33" * 64,
                "certification_data": {"cert_type": 6, "body": "44" * 8},
                "qe_report_data": {
                    "qe_report": build_qe_report(),
                    "qe_report_signature": "55" * 64,
                    "qe_auth_data": "66" * 16,
                    "certification_data": {"cert_type": 5, "body": "77" * 8},
                },
            }
        },
    }


def build_appraisal(decode: dict, *, advisories=()) -> dict:
    return {
        "status": "UpToDate",
        "advisory_ids": list(advisories),
        "report": decode["report"],
        "ppid": "88" * 16,
        "qe_status": {"status": "UpToDate", "advisory_ids": []},
        "platform_status": {"status": "UpToDate", "advisory_ids": []},
    }


def build_policy(
    appraiser_sha256: str,
    *,
    pinned: bool = True,
    discovery: bool = False,
    advisories=(),
    require_strict: bool = False,
    rtmrs: dict[int, str] | None = None,
    extra: dict | None = None,
) -> dict:
    def pin(value: str) -> str:
        return value if pinned else "TODO: fill me in"

    measurements = {name: pin(value) for name, value in MEASUREMENTS.items()}
    for index in range(4):
        measurements[f"rt_mr{index}"] = pin((rtmrs or {})[index])
    policy = {
        "kind": "sparkinterval.phala-tdx.dcap-qvl-appraisal-policy.v1",
        "schema_version": 1,
        "first_run_measurement_discovery": discovery,
        "require_dcap_qvl_strict": require_strict,
        "appraiser": {
            "project": "Phala-Network/dcap-qvl",
            "version": "v0.6.1",
            "commit": "6ac45907f814e1c3e8bfc1b0e3c6a99710d4ef9f",
            "asset": "dcap-qvl-linux-x86_64-musl",
            "sha256": appraiser_sha256,
        },
        "quote": {
            "tee_type": 129,
            "min_quote_version": 4,
            "accepted_report_kinds": ["TD10", "TD15"],
        },
        "measurements": measurements,
        "tcb": {
            "allowed_statuses": ["UpToDate"],
            "allowed_platform_statuses": ["UpToDate"],
            "allowed_qe_statuses": ["UpToDate"],
            "accepted_advisory_ids": list(advisories),
        },
        "qe_identity": {
            "qe_vendor_id": pin(QE_VENDOR_ID),
            "mr_signer": pin(QE_MR_SIGNER),
            "isv_prod_id": QE_ISV_PROD_ID if pinned else "TODO: fill me in",
            "min_isv_svn": QE_ISV_SVN if pinned else "TODO: fill me in",
        },
    }
    if extra:
        policy.update(extra)
    return policy


# ---------------------------------------------------------------------------
# Mock dstack guest agent
# ---------------------------------------------------------------------------


class _UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self) -> None:
        socketserver.UnixStreamServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = 0


class MockGuestAgent:
    """Answers the three dstack v0.5.3 methods the prelude calls."""

    def __init__(self, socket_path: Path, responses: dict) -> None:
        self.socket_path = socket_path
        self.responses = responses
        self.seen: list[tuple[str, dict]] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:  # noqa: N802
                pass

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = {}
                method = self.path.lstrip("/").split("?")[0]
                outer.seen.append((method, payload))
                answer = outer.responses.get(method)
                if callable(answer):
                    answer = answer(payload)
                if answer is None:
                    body = json.dumps({"error": f"no such method {method}"})
                    status = 404
                else:
                    body = json.dumps(answer)
                    status = 200
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

    def __enter__(self) -> "MockGuestAgent":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


DRIVER = textwrap.dedent(
    """
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("prelude", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DCAP_QVL_SHA256 = sys.argv[2]
    module.RETAINED_ARTIFACT_SHA256 = sys.argv[3]
    module.RETAINED_ARTIFACT_BYTES = int(sys.argv[4])
    sys.argv = ["prelude"] + sys.argv[5:]
    sys.exit(module.main())
    """
)


FAKE_DCAP_QVL = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    fixtures = os.environ["FAKE_DCAP_QVL_FIXTURES"]
    argv = sys.argv[1:]
    if argv[0] == "decode":
        sys.stdout.write(open(os.path.join(fixtures, "decode.json")).read())
        sys.exit(0)
    if argv[0] == "verify" and "--strict" in argv:
        strict = json.load(open(os.path.join(fixtures, "strict.json")))
        sys.stderr.write(strict["stderr"])
        sys.exit(strict["exit_status"])
    if argv[0] == "verify":
        status = int(open(os.path.join(fixtures, "verify.status")).read())
        if status != 0:
            sys.stderr.write("Error: Failed to verify quote\\n")
            sys.exit(status)
        sys.stdout.write(open(os.path.join(fixtures, "verify.json")).read())
        sys.exit(0)
    sys.exit(64)
    """
)


class PreludeHarness:
    """One temporary CVM-shaped workspace plus a mock guest agent."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phala-prelude-"))
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.fixtures = self.tmp / "fixtures"
        self.fixtures.mkdir()
        # Short path: AF_UNIX addresses are capped near 108 bytes.
        self.socket_path = Path(tempfile.mkdtemp(prefix="phsk-")) / "d.sock"

        self.public_key = public_key_hex(MOCK_SCALAR)
        self.report_data = report_data_hash(
            enclave_public_key_hex=self.public_key,
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        self.report_data_padded = self.report_data + "00" * 32

        self.events, self.rtmrs = build_event_log()
        self.decode = build_decode(self.report_data_padded, self.rtmrs)
        self.appraisal = build_appraisal(self.decode)
        self.strict = {"exit_status": 1, "stderr": "Dynamic platform is not allowed\n"}
        self.verify_status = 0

        self.dcap = self.tmp / "dcap-qvl"
        self.dcap.write_text(FAKE_DCAP_QVL, encoding="utf-8")
        self.dcap.chmod(0o755)
        self.dcap_sha256 = hashlib.sha256(self.dcap.read_bytes()).hexdigest()

        self.artifact = self.tmp / "a7_boundary.json"
        self.artifact.write_bytes(b'{"mock":"a7 artifact"}\n')
        self.artifact_sha256 = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.artifact_bytes = self.artifact.stat().st_size

        self.policy = build_policy(self.dcap_sha256, rtmrs=self.rtmrs)
        self.info = {
            "app_id": APP_ID,
            "instance_id": "",
            "app_cert": "-----BEGIN CERTIFICATE-----\nmock\n-----END CERTIFICATE-----",
            "tcb_info": json.dumps(
                {
                    "mrtd": MEASUREMENTS["mr_td"],
                    "rootfs_hash": "00" * 32,
                    "rtmr0": self.rtmrs[0],
                    "rtmr1": self.rtmrs[1],
                    "rtmr2": self.rtmrs[2],
                    "rtmr3": self.rtmrs[3],
                    "event_log": self.events,
                }
            ),
            "app_name": "sparkinterval-ch25-a7-boundary",
            "device_id": "aa" * 32,
            "mr_aggregated": "bb" * 32,
            "os_image_hash": "cc" * 32,
            "key_provider_info": json.dumps({"name": "kms", "id": "dd" * 32}),
            "compose_hash": COMPOSE_HASH,
        }
        self.quote = bytes(range(256)) * 8
        self.key_hex = f"{MOCK_SCALAR:064x}"
        self.echo_report_data = None  # None means: echo what was asked for
        self.extra_env: dict[str, str] = {}

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.socket_path.parent, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------

    def _write_fixtures(self) -> None:
        (self.fixtures / "decode.json").write_text(
            json.dumps(self.decode), encoding="utf-8"
        )
        (self.fixtures / "verify.json").write_text(
            json.dumps(self.appraisal), encoding="utf-8"
        )
        (self.fixtures / "verify.status").write_text(
            str(self.verify_status), encoding="utf-8"
        )
        (self.fixtures / "strict.json").write_text(
            json.dumps(self.strict), encoding="utf-8"
        )

    def _responses(self) -> dict:
        def get_quote(payload: dict) -> dict:
            echoed = self.echo_report_data or payload.get("report_data", "")
            return {
                "quote": self.quote.hex(),
                "event_log": json.dumps(self.events),
                "report_data": echoed,
            }

        return {
            "Info": lambda _payload: self.info,
            "GetKey": lambda _payload: {
                "key": self.key_hex,
                "signature_chain": ["ee" * 65, "ff" * 65],
            },
            "GetQuote": get_quote,
        }

    # -- run --------------------------------------------------------------

    def run(self, *, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
        self._write_fixtures()
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(ROOT),
            "HOME": str(self.tmp),
            "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE":
                "sparkinterval.phala-tdx-measured-worker.v1",
            "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND": "phala_dstack_tdx_cpu",
            "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE": CHALLENGE,
            "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256": JOB_BINDING,
            "TG_FINAL_IMAGE_REFERENCE": IMAGE_DIGEST,
            "TG_ISSUED_AT": ISSUED_AT,
            "TG_DSTACK_SOCKET": str(self.socket_path),
            "TG_DCAP_QVL_BINARY": str(self.dcap),
            "TG_A7_ARTIFACT_PATH": str(self.artifact),
            "TG_DCAP_QVL_POLICY_B64": base64.b64encode(
                json.dumps(self.policy, indent=2).encode("utf-8")
            ).decode("ascii"),
            "FAKE_DCAP_QVL_FIXTURES": str(self.fixtures),
        }
        environment.update(self.extra_env)
        environment.update(env_overrides or {})
        with MockGuestAgent(self.socket_path, self._responses()) as agent:
            self.agent = agent
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    DRIVER,
                    str(PRELUDE),
                    self.dcap_sha256,
                    self.artifact_sha256,
                    str(self.artifact_bytes),
                    "--input-root",
                    str(self.workspace / "staging" / "input"),
                    "--evidence-root",
                    str(self.workspace / "retained" / "evidence"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
                env=environment,
            )
        return completed

    # -- accessors --------------------------------------------------------

    @property
    def input_root(self) -> Path:
        return self.workspace / "staging" / "input"

    @property
    def evidence_root(self) -> Path:
        return self.workspace / "retained" / "evidence"


REQUIRED_INPUTS = (
    "registered-input.json",
    "a7_boundary.json",
    "enclave-signing-key.hex",
    "tdx-quote.bin",
    "dcap-qvl-appraisal.json",
    "dcap-qvl-policy.json",
    "dcap-qvl-artifact.sha256",
)


class PreludeHappyPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = PreludeHarness()
        cls.result = cls.harness.run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.close()

    def test_exit_status_is_zero(self) -> None:
        self.assertEqual(
            self.result.returncode,
            0,
            f"stdout:\n{self.result.stdout}\nstderr:\n{self.result.stderr}",
        )

    def test_every_required_input_is_produced(self) -> None:
        for name in REQUIRED_INPUTS:
            path = self.harness.input_root / name
            self.assertTrue(path.is_file(), f"{name} was not produced")
            self.assertFalse(path.is_symlink())
            self.assertGreater(path.stat().st_size, 0)

    def test_the_signing_key_is_the_derived_scalar_and_is_not_world_readable(
        self,
    ) -> None:
        path = self.harness.input_root / "enclave-signing-key.hex"
        self.assertEqual(
            path.read_text(encoding="ascii").strip(), self.harness.key_hex
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)

    def test_the_signing_key_is_never_printed(self) -> None:
        combined = self.result.stdout + self.result.stderr
        self.assertNotIn(self.harness.key_hex, combined)
        self.assertIn(self.harness.public_key, combined)

    def test_report_data_is_the_library_commitment_byte_for_byte(self) -> None:
        """The quote must be requested for exactly what Lean will re-derive."""

        requested = dict(self.harness.agent.seen)["GetQuote"]["report_data"]
        expected = report_data_hash(
            enclave_public_key_hex=public_key_hex(MOCK_SCALAR),
            challenge_nonce=CHALLENGE,
            job_binding=JOB_BINDING,
        )
        self.assertEqual(requested, expected + "00" * 32)
        summary = json.loads(
            (self.harness.evidence_root / "prelude-summary.json").read_text("utf-8")
        )
        self.assertEqual(summary["report_data_sha256"], expected)
        self.assertEqual(summary["enclave_public_key"], public_key_hex(MOCK_SCALAR))

    def test_the_documented_preimage_and_the_library_agree(self) -> None:
        """docs/PHALA_FIRST_RUN.md section 4 step 2, spelled out once here."""

        key = public_key_hex(MOCK_SCALAR)

        def committed(name: str, value: str) -> str:
            return f"{name}={hashlib.sha256(value.encode('utf-8')).hexdigest()}\n"

        documented = (
            "sparkinterval.phala-tdx-report-data.v1\n"
            + committed("enclave_public_key", key)
            + committed("challenge_nonce", CHALLENGE)
            + committed("job_binding_sha256", JOB_BINDING)
        )
        self.assertEqual(
            documented,
            report_data_preimage(
                enclave_public_key_hex=key,
                challenge_nonce=CHALLENGE,
                job_binding=JOB_BINDING,
            ),
        )
        self.assertEqual(
            hashlib.sha256(documented.encode("utf-8")).hexdigest(),
            report_data_hash(
                enclave_public_key_hex=key,
                challenge_nonce=CHALLENGE,
                job_binding=JOB_BINDING,
            ),
        )

    def test_the_quote_is_stored_as_raw_bytes(self) -> None:
        self.assertEqual(
            (self.harness.input_root / "tdx-quote.bin").read_bytes(),
            self.harness.quote,
        )

    def test_the_appraiser_digest_file_names_the_binary_actually_used(self) -> None:
        line = (
            self.harness.input_root / "dcap-qvl-artifact.sha256"
        ).read_text(encoding="ascii")
        self.assertTrue(line.startswith(self.harness.dcap_sha256 + "  "))
        self.assertIn("dcap-qvl-linux-x86_64-musl-v0.6.1", line)

    def test_the_retained_policy_is_the_delivered_policy(self) -> None:
        stored = json.loads(
            (self.harness.input_root / "dcap-qvl-policy.json").read_text("utf-8")
        )
        self.assertEqual(stored, self.harness.policy)

    def test_the_job_scope_carries_the_attested_app_id_and_compose_hash(self) -> None:
        text = (self.harness.input_root / "job-scope.env").read_text("ascii")
        self.assertIn(f"SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID={APP_ID}\n", text)
        self.assertIn(
            f"SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH={COMPOSE_HASH}\n", text
        )

    def test_the_strict_verdict_is_retained_even_though_it_failed(self) -> None:
        strict = json.loads(
            (self.harness.evidence_root / "dcap-qvl-strict.json").read_text("utf-8")
        )
        self.assertIs(strict["passed"], False)
        self.assertEqual(strict["exit_status"], 1)

    def test_the_registered_input_is_the_producer_literal(self) -> None:
        workload = (ROOT / "tools/tg_a7_phala_tdx_workload.py").read_text("utf-8")
        produced = (self.harness.input_root / "registered-input.json").read_bytes()
        # The producer spells the same literal across two source lines, so
        # compare the halves it actually contains.
        halves = (
            '{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":',
            '"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}',
        )
        self.assertEqual(produced.decode("ascii"), "".join(halves))
        for half in halves:
            self.assertIn(half, workload)

    def test_measurements_are_recorded_as_pinned(self) -> None:
        summary = json.loads(
            (self.harness.evidence_root / "prelude-summary.json").read_text("utf-8")
        )
        self.assertIs(summary["measurements_pinned"], True)
        self.assertEqual(summary["unpinned"], [])
        self.assertFalse((self.harness.evidence_root / "MEASUREMENTS-NOT-PINNED").exists())


class PreludeRefusalTests(unittest.TestCase):
    """Every one of these must stop the run before any input is handed over."""

    def setUp(self) -> None:
        self.harness = PreludeHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def assertRefused(self, result, needle: str) -> None:
        self.assertNotEqual(result.returncode, 0, "the prelude should have refused")
        self.assertIn(
            needle,
            result.stdout + result.stderr,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertFalse(
            (self.harness.input_root / "job-scope.env").exists(),
            "a refused run must not hand over a job scope",
        )

    def test_unpinned_policy_is_refused_and_prints_the_observed_values(self) -> None:
        self.harness.policy = build_policy(
            self.harness.dcap_sha256, pinned=False, rtmrs=self.harness.rtmrs
        )
        result = self.harness.run()
        self.assertRefused(result, "leaves these pins as TODO")
        self.assertIn(self.harness.rtmrs[3], result.stdout + result.stderr)

    def test_discovery_mode_proceeds_but_marks_the_run(self) -> None:
        self.harness.policy = build_policy(
            self.harness.dcap_sha256,
            pinned=False,
            discovery=True,
            rtmrs=self.harness.rtmrs,
        )
        result = self.harness.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.harness.evidence_root / "MEASUREMENTS-NOT-PINNED").is_file()
        )
        self.assertIn("MEASUREMENTS ARE NOT PINNED", result.stdout)
        summary = json.loads(
            (self.harness.evidence_root / "prelude-summary.json").read_text("utf-8")
        )
        self.assertIs(summary["measurements_pinned"], False)

    def test_a_failed_appraisal_is_fatal(self) -> None:
        self.harness.verify_status = 1
        result = self.harness.run()
        self.assertRefused(result, "could not verify the quote")
        self.assertFalse(
            (self.harness.input_root / "dcap-qvl-appraisal.json").exists()
        )

    def test_required_strict_that_fails_is_fatal(self) -> None:
        self.harness.policy = build_policy(
            self.harness.dcap_sha256, rtmrs=self.harness.rtmrs, require_strict=True
        )
        self.assertRefused(self.harness.run(), "requires dcap-qvl --strict")

    def test_report_data_the_quote_does_not_carry_is_fatal(self) -> None:
        self.harness.decode = build_decode("00" * 64, self.harness.rtmrs)
        self.harness.appraisal = build_appraisal(self.harness.decode)
        self.assertRefused(
            self.harness.run(), "not this run's commitment"
        )

    def test_an_echoed_report_data_mismatch_is_fatal(self) -> None:
        self.harness.echo_report_data = "01" * 64
        self.assertRefused(self.harness.run(), "echoed report data")

    def test_a_relabelled_rtmr3_event_is_fatal(self) -> None:
        for event in self.harness.events:
            if event.get("event") == "compose-hash":
                event["event_payload"] = "de" * 32
        self.assertRefused(self.harness.run(), "does not hash to its recorded digest")

    def test_an_rtmr_the_quote_does_not_attest_is_fatal(self) -> None:
        self.harness.decode["report"]["TD10"]["rt_mr3"] = "ab" * 48
        self.harness.appraisal = build_appraisal(self.harness.decode)
        self.harness.policy = build_policy(
            self.harness.dcap_sha256,
            rtmrs={**self.harness.rtmrs, 3: "ab" * 48},
        )
        self.assertRefused(self.harness.run(), "but the quote attests")

    def test_an_app_id_the_quote_does_not_attest_is_fatal(self) -> None:
        events, rtmrs = build_event_log(app_id="1f" * 20)
        self.harness.events = events
        self.harness.rtmrs = rtmrs
        self.harness.decode = build_decode(
            self.harness.report_data_padded, rtmrs
        )
        self.harness.appraisal = build_appraisal(self.harness.decode)
        self.harness.policy = build_policy(self.harness.dcap_sha256, rtmrs=rtmrs)
        self.assertRefused(self.harness.run(), "RTMR3 attests app-id")

    def test_an_unlisted_advisory_is_fatal(self) -> None:
        self.harness.appraisal = build_appraisal(
            self.harness.decode, advisories=("INTEL-SA-00999",)
        )
        self.assertRefused(self.harness.run(), "INTEL-SA-00999")

    def test_a_debuggable_td_is_fatal(self) -> None:
        self.harness.decode["report"]["TD10"]["td_attributes"] = "0100001000000000"
        self.harness.appraisal = build_appraisal(self.harness.decode)
        self.assertRefused(self.harness.run(), "debuggable")

    def test_an_sgx_quote_is_fatal(self) -> None:
        self.harness.decode["header"]["tee_type"] = 0
        self.harness.appraisal = build_appraisal(self.harness.decode)
        self.assertRefused(self.harness.run(), "tee_type")

    def test_a_scalar_outside_the_p256_group_is_fatal(self) -> None:
        self.harness.key_hex = f"{P256_GROUP_ORDER:064x}"
        self.assertRefused(self.harness.run(), "not a valid P-256 private key")

    def test_a_wrong_artifact_digest_is_fatal(self) -> None:
        self.harness.artifact.write_bytes(b"not the retained artifact\n")
        self.assertRefused(self.harness.run(), "refusing to continue")

    def test_an_azure_measured_runner_variable_is_fatal(self) -> None:
        self.harness.extra_env = {
            "SPARKINTERVAL_MEASURED_WORKER_SCOPE": "anything"
        }
        self.assertRefused(self.harness.run(), "mixed-scope job")

    def test_a_policy_with_an_unknown_key_is_fatal(self) -> None:
        self.harness.policy = build_policy(
            self.harness.dcap_sha256,
            rtmrs=self.harness.rtmrs,
            extra={"allow_everything": True},
        )
        self.assertRefused(self.harness.run(), "unknown keys")

    def test_a_policy_naming_a_different_appraiser_is_fatal(self) -> None:
        self.harness.policy = build_policy("00" * 32, rtmrs=self.harness.rtmrs)
        self.assertRefused(self.harness.run(), "different dcap-qvl binary")

    def test_a_policy_allowing_revoked_is_fatal(self) -> None:
        policy = build_policy(self.harness.dcap_sha256, rtmrs=self.harness.rtmrs)
        policy["tcb"]["allowed_statuses"] = ["UpToDate", "Revoked"]
        self.harness.policy = policy
        self.assertRefused(self.harness.run(), "Revoked")

    def test_a_pre_existing_input_tree_is_fatal(self) -> None:
        self.harness.input_root.mkdir(parents=True)
        self.assertRefused(self.harness.run(), "already exists")

    def test_an_unreachable_guest_agent_is_fatal(self) -> None:
        result = self.harness.run(
            env_overrides={"TG_DSTACK_SOCKET": str(self.harness.tmp / "absent.sock")}
        )
        self.assertRefused(result, "cannot reach the dstack guest agent")


if __name__ == "__main__":
    unittest.main()
