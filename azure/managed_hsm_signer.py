#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Sign a trusted-compute receipt payload with an Azure Managed HSM key.

The payload is read from standard input and the raw RSA-3072 signature is
written to standard output.  Diagnostics go only to standard error.  The key
URI must include an immutable key version, and the returned signature is
independently checked with a locally pinned public key before it is released.

This small adapter is suitable for ``trusted_compute_receipt.py
--signer-command``.  It does not create keys, grant roles, or silently select
the latest key version.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable


KEY_URI_RE = re.compile(
    r"^https://[a-z0-9-]+\.managedhsm\.azure\.net/keys/"
    r"[A-Za-z0-9-]+/[0-9a-f]{32}$"
)
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
RSA3072_SIGNATURE_BYTES = 384


class SignerError(RuntimeError):
    """The HSM operation or local pin verification failed closed."""


def _azure_cli_environment() -> dict[str, str]:
    """Return the narrow environment needed by Azure CLI authentication.

    The signer can run in a long-lived receipt-issuer process.  Inheriting
    variables such as ``PYTHONPATH`` or ``LD_PRELOAD`` there would let the
    caller change code loaded by ``az`` despite the signer entry point itself
    being snapshotted by the issuer.  Forward only the documented identity
    coordinates and a deterministic process environment.
    """

    environment = {
        "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    for name in (
        "AZURE_CLIENT_ID",
        "AZURE_CONFIG_DIR",
        "AZURE_FEDERATED_TOKEN_FILE",
        "AZURE_TENANT_ID",
        "IDENTITY_ENDPOINT",
        "IDENTITY_HEADER",
        "IMDS_ENDPOINT",
        "MSI_ENDPOINT",
        "MSI_SECRET",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if "AZURE_CONFIG_DIR" in environment and os.environ.get("HOME"):
        # Interactive operator authentication stores its tokens below HOME.
        # Workload/managed identities do not need this exception.
        environment["HOME"] = os.environ["HOME"]
    return environment


def _local_verifier_environment() -> dict[str, str]:
    """Return a deterministic environment for the local OpenSSL verifier."""

    return {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "TZ": "UTC",
    }


def _decode_base64_signature(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise SignerError("Azure CLI response contains no signature")
    padded = value + "=" * (-len(value) % 4)
    try:
        signature = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise SignerError("Azure CLI signature is not base64/base64url") from error
    if len(signature) != RSA3072_SIGNATURE_BYTES:
        raise SignerError(
            "Managed HSM key is not the required RSA-3072 key "
            f"({len(signature)} signature bytes returned)"
        )
    return signature


def _signature_field(response: Any) -> str:
    if not isinstance(response, dict):
        raise SignerError("Azure CLI signing response is not a JSON object")
    # Azure SDK/CLI versions have exposed the operation bytes as either
    # ``result`` or ``value``.  Accept exactly one spelling, never an arbitrary
    # recursively discovered string.
    present = [name for name in ("result", "value") if name in response]
    if len(present) != 1:
        raise SignerError(
            "Azure CLI signing response must contain exactly one result/value field"
        )
    value = response[present[0]]
    if not isinstance(value, str):
        raise SignerError("Azure CLI signing result is not a string")
    return value


def _verify_locally(
    payload: bytes, signature: bytes, public_key: Path, openssl: str
) -> None:
    if not public_key.is_file():
        raise SignerError(f"pinned public key is not a file: {public_key}")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        payload_path = root / "payload"
        signature_path = root / "signature"
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        try:
            completed = subprocess.run(
                [
                    openssl,
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(public_key),
                    "-signature",
                    str(signature_path),
                    str(payload_path),
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                env=_local_verifier_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SignerError(f"local OpenSSL verification could not run: {error}") from error
    if completed.returncode != 0:
        raise SignerError("Managed HSM signature does not match the pinned public key")


def sign_payload(
    payload: bytes,
    *,
    key_uri: str,
    public_key: Path,
    az: str = "az",
    openssl: str = "openssl",
) -> bytes:
    if KEY_URI_RE.fullmatch(key_uri) is None:
        raise SignerError(
            "--key-uri must be a versioned https://NAME.managedhsm.azure.net/keys/KEY/VERSION URI"
        )
    if not payload:
        raise SignerError("refusing to sign an empty payload")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise SignerError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    digest = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    command = [
        az,
        "keyvault",
        "key",
        "sign",
        "--id",
        key_uri,
        "--algorithm",
        "RS256",
        "--digest",
        digest,
        "--only-show-errors",
        "--output",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            env=_azure_cli_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SignerError(f"Azure Managed HSM signing could not run: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise SignerError(
            f"Azure Managed HSM signing failed with status {completed.returncode}: {detail}"
        )
    try:
        response = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SignerError("Azure CLI signing response is not valid JSON") from error
    signature = _decode_base64_signature(_signature_field(response))
    _verify_locally(payload, signature, public_key, openssl)
    return signature


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-uri", required=True)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--az", default="az")
    parser.add_argument("--openssl", default="openssl")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
        signature = sign_payload(
            payload,
            key_uri=args.key_uri,
            public_key=args.public_key,
            az=args.az,
            openssl=args.openssl,
        )
    except SignerError as error:
        print(f"managed_hsm_signer: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(signature)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
