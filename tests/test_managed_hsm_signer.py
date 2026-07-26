# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "azure"
if str(AZURE) not in sys.path:
    sys.path.insert(0, str(AZURE))

import managed_hsm_signer as signer  # noqa: E402


class ManagedHsmSignerTests(unittest.TestCase):
    def test_unversioned_key_uri_is_rejected_before_azure_call(self) -> None:
        with mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(signer.SignerError, "versioned"):
                signer.sign_payload(
                    b"payload",
                    key_uri="https://proof.managedhsm.azure.net/keys/receipt-key",
                    public_key=Path("unused.pem"),
                )
        run.assert_not_called()

    def test_symbolic_latest_key_uri_is_rejected_before_azure_call(self) -> None:
        with mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(signer.SignerError, "versioned"):
                signer.sign_payload(
                    b"payload",
                    key_uri=(
                        "https://proof.managedhsm.azure.net/keys/"
                        "receipt-key/latest"
                    ),
                    public_key=Path("unused.pem"),
                )
        run.assert_not_called()

    def test_exact_versioned_hsm_command_and_raw_signature(self) -> None:
        raw_signature = bytes(range(256)) + bytes(range(128))
        response = {
            "result": base64.urlsafe_b64encode(raw_signature).decode("ascii").rstrip("=")
        }
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(__import__("json").dumps(response)).encode("utf-8"),
            stderr=b"",
        )
        key_uri = (
            "https://proof.managedhsm.azure.net/keys/receipt-key/"
            "1234567890abcdef1234567890abcdef"
        )
        with mock.patch.object(subprocess, "run", return_value=completed) as run:
            with mock.patch.object(signer, "_verify_locally") as verify:
                actual = signer.sign_payload(
                    b"payload",
                    key_uri=key_uri,
                    public_key=Path("pinned.pem"),
                )
        self.assertEqual(actual, raw_signature)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["az", "keyvault", "key", "sign", "--id"])
        self.assertIn(key_uri, command)
        self.assertIn("RS256", command)
        verify.assert_called_once_with(
            b"payload", raw_signature, Path("pinned.pem"), "openssl"
        )

    def test_ambiguous_azure_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(signer.SignerError, "exactly one"):
            signer._signature_field({"result": "a", "value": "b"})

    def test_azure_cli_environment_rejects_loader_and_python_injection(self) -> None:
        hostile = {
            "AZURE_CLIENT_ID": "reviewed-client",
            "AZURE_TENANT_ID": "reviewed-tenant",
            "LD_PRELOAD": "/tmp/hostile.so",
            "PYTHONPATH": "/tmp/hostile-python",
            "RUBYOPT": "-r/tmp/hostile.rb",
        }
        with mock.patch.dict(os.environ, hostile, clear=True):
            environment = signer._azure_cli_environment()
        self.assertEqual(environment["AZURE_CLIENT_ID"], "reviewed-client")
        self.assertEqual(environment["AZURE_TENANT_ID"], "reviewed-tenant")
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("RUBYOPT", environment)

    def test_local_openssl_verifier_uses_fixed_sanitized_environment(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"Verified OK\n", stderr=b""
        )
        with tempfile.TemporaryDirectory() as temporary:
            public_key = Path(temporary) / "public.pem"
            public_key.write_text("test fixture", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "PATH": "/attacker/bin",
                    "LD_PRELOAD": "/attacker/preload.so",
                    "OPENSSL_CONF": "/attacker/openssl.cnf",
                },
                clear=False,
            ), mock.patch.object(
                subprocess, "run", return_value=completed
            ) as run:
                signer._verify_locally(
                    b"payload", bytes(signer.RSA3072_SIGNATURE_BYTES), public_key, "openssl"
                )
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("OPENSSL_CONF", environment)


if __name__ == "__main__":
    unittest.main()
