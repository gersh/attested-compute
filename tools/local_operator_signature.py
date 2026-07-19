#!/usr/bin/env python3
"""Create and verify detached DGX Spark operator signatures.

An operator signature authenticates the exact canonical run-bundle bytes to a
separately trusted Ed25519 public key.  It is deliberately not represented as
hardware attestation and does not prove that the recorded computation ran.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable

from create_run_bundle import (
    BUNDLE_KIND,
    SCHEMA_VERSION as RUN_BUNDLE_SCHEMA_VERSION,
    BundleError,
    SHA256_RE,
    canonical_json_bytes,
    load_canonical_json,
    parse_json_bytes,
    validate_json_value,
)


SIGNATURE_SCHEMA_VERSION = 1
SIGNATURE_KIND = "sparkinterval_dgx_local_operator_signature"
SIGNATURE_ALGORITHM = "ed25519"
SIGNATURE_CONTEXT = "SparkInterval DGX local operator signature v1"
SIGNATURE_WARNING = "LOCAL OPERATOR SIGNATURE ONLY - NOT HARDWARE ATTESTATION"
ASSURANCE = "operator_signed_local_record_not_hardware_evidence"

# RFC 8410 SubjectPublicKeyInfo prefix for an Ed25519 public key.  The prefix
# is followed by the raw 32-byte public key.
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
ED25519_SPKI_SIZE = len(ED25519_SPKI_PREFIX) + 32
ED25519_SIGNATURE_SIZE = 64

ENVELOPE_KEYS = {
    "schema_version",
    "signature_kind",
    "algorithm",
    "key_id",
    "public_key_spki_der_base64",
    "signed_payload",
    "signature_base64",
    "warning",
}
PAYLOAD_KEYS = {
    "context",
    "bundle_file_sha256",
    "bundle_sha256",
    "statement_sha256",
}


class LocalSignatureError(BundleError):
    """A key, signature, or signed bundle is invalid."""


def _fail(message: str) -> None:
    raise LocalSignatureError(message)


def _exact_object(value: Any, expected: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be a JSON object")
    keys = set(value)
    if keys != expected:
        _fail(
            f"{what} has wrong fields "
            f"(missing={sorted(expected - keys)}, unexpected={sorted(keys - expected)})"
        )
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(f"{what} must be a lowercase hexadecimal SHA-256")
    return value


def _canonical_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_canonical_base64(value: Any, what: str) -> bytes:
    if not isinstance(value, str) or not value:
        _fail(f"{what} must be a non-empty base64 string")
    try:
        encoded = value.encode("ascii", errors="strict")
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise LocalSignatureError(f"{what} is not valid canonical base64") from exc
    if _canonical_base64(decoded) != value:
        _fail(f"{what} is not in canonical base64 form")
    return decoded


def _resolve_executable(value: str | os.PathLike[str]) -> Path:
    name = os.fspath(value)
    located = shutil.which(name)
    if located is None:
        _fail(f"cannot find OpenSSL executable: {name}")
    try:
        executable = Path(located).resolve(strict=True)
    except OSError as exc:
        raise LocalSignatureError(f"cannot resolve OpenSSL executable {located}: {exc}") from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        _fail(f"OpenSSL executable is not executable: {executable}")
    return executable


def _run_openssl(
    openssl: str | os.PathLike[str],
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    timeout_seconds: int = 120,
) -> bytes:
    executable = _resolve_executable(openssl)
    try:
        completed = subprocess.run(
            [str(executable), *arguments],
            check=False,
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalSignatureError(f"OpenSSL invocation failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        if len(detail) > 1000:
            detail = detail[:1000] + "..."
        suffix = f": {detail}" if detail else ""
        _fail(f"OpenSSL rejected the operation{suffix}")
    return completed.stdout


def _resolve_regular_file(path: str | os.PathLike[str], what: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError as exc:
        raise LocalSignatureError(f"cannot resolve {what} {path}: {exc}") from exc
    if not resolved.is_file():
        _fail(f"{what} is not a regular file: {resolved}")
    return resolved


def _require_private_permissions(path: Path, what: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        _fail(f"{what} must not be accessible by group or other users")


def _passphrase_argument(
    passphrase_file: str | os.PathLike[str] | None,
    option: str,
) -> list[str]:
    if passphrase_file is None:
        return []
    resolved = _resolve_regular_file(passphrase_file, "passphrase file")
    _require_private_permissions(resolved, "passphrase file")
    return [option, f"file:{resolved}"]


def _validate_ed25519_spki(der: bytes, what: str) -> bytes:
    if len(der) != ED25519_SPKI_SIZE or not der.startswith(ED25519_SPKI_PREFIX):
        _fail(f"{what} is not an RFC 8410 Ed25519 public key")
    return der


def public_key_spki_der(
    public_key: str | os.PathLike[str], *, openssl: str | os.PathLike[str] = "openssl"
) -> bytes:
    key = _resolve_regular_file(public_key, "public key")
    der = _run_openssl(
        openssl,
        ["pkey", "-pubin", "-in", str(key), "-outform", "DER"],
    )
    return _validate_ed25519_spki(der, "public key")


def _private_key_spki_der(
    private_key: str | os.PathLike[str],
    *,
    openssl: str | os.PathLike[str],
    passphrase_file: str | os.PathLike[str] | None,
) -> bytes:
    key = _resolve_regular_file(private_key, "private key")
    _require_private_permissions(key, "private key")
    arguments = ["pkey", "-in", str(key), "-pubout", "-outform", "DER"]
    arguments.extend(_passphrase_argument(passphrase_file, "-passin"))
    der = _run_openssl(openssl, arguments)
    return _validate_ed25519_spki(der, "private key's public key")


def key_id_from_spki(der: bytes) -> str:
    return _sha256(_validate_ed25519_spki(der, "public key"))


def _create_exclusive_file(path: Path, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError as exc:
        raise LocalSignatureError(f"refusing to overwrite existing file: {path}") from exc
    except OSError as exc:
        raise LocalSignatureError(f"cannot create {path}: {exc}") from exc
    os.close(descriptor)


def generate_keypair(
    private_key: str | os.PathLike[str],
    public_key: str | os.PathLike[str],
    *,
    openssl: str | os.PathLike[str] = "openssl",
    passphrase_file: str | os.PathLike[str] | None = None,
    allow_unencrypted_private_key: bool = False,
) -> dict[str, Any]:
    """Generate a new Ed25519 key pair without overwriting either destination."""

    if (passphrase_file is None) == (not allow_unencrypted_private_key):
        _fail(
            "choose exactly one of passphrase_file or "
            "allow_unencrypted_private_key=True"
        )
    private_path = Path(private_key).resolve(strict=False)
    public_path = Path(public_key).resolve(strict=False)
    if private_path == public_path:
        _fail("private and public key paths must be distinct")
    if passphrase_file is not None:
        _passphrase_argument(passphrase_file, "-pass")

    created: list[Path] = []
    try:
        _create_exclusive_file(private_path, 0o600)
        created.append(private_path)
        _create_exclusive_file(public_path, 0o644)
        created.append(public_path)

        arguments = ["genpkey", "-algorithm", "Ed25519", "-out", str(private_path)]
        if passphrase_file is not None:
            arguments.extend(["-aes-256-cbc"])
            arguments.extend(_passphrase_argument(passphrase_file, "-pass"))
        _run_openssl(openssl, arguments)
        os.chmod(private_path, 0o600)

        public_arguments = [
            "pkey",
            "-in",
            str(private_path),
            "-pubout",
            "-out",
            str(public_path),
        ]
        public_arguments.extend(_passphrase_argument(passphrase_file, "-passin"))
        _run_openssl(openssl, public_arguments)
        os.chmod(public_path, 0o644)
        der = public_key_spki_der(public_path, openssl=openssl)
    except Exception:
        for path in reversed(created):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id_from_spki(der),
        "private_key": str(private_path),
        "public_key": str(public_path),
        "private_key_encrypted": passphrase_file is not None,
    }


def _load_bundle_bytes(path: str | os.PathLike[str]) -> tuple[bytes, dict[str, Any]]:
    bundle_path = _resolve_regular_file(path, "run bundle")
    try:
        data = bundle_path.read_bytes()
    except OSError as exc:
        raise LocalSignatureError(f"cannot read run bundle {bundle_path}: {exc}") from exc
    value = parse_json_bytes(data, str(bundle_path))
    if data != canonical_json_bytes(value):
        _fail(f"{bundle_path} is not canonical JSON")
    if not isinstance(value, dict):
        _fail("run bundle must be a JSON object")
    return data, value


def _require_local_dgx_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != RUN_BUNDLE_SCHEMA_VERSION:
        _fail("operator signatures require run-bundle schema version 1")
    if bundle.get("bundle_kind") != BUNDLE_KIND:
        _fail("operator signatures require a SparkInterval run bundle")
    statement = bundle.get("statement")
    if not isinstance(statement, dict):
        _fail("run bundle is missing its statement")
    target = statement.get("target_profile")
    trust = statement.get("trust_profile")
    evidence = bundle.get("evidence")
    if not isinstance(target, dict) or target.get("profile_id") != "dgx_spark_sm121":
        _fail("operator signatures are restricted to DGX Spark bundles")
    if not isinstance(trust, dict) or trust.get("profile_id") != "local_unattested":
        _fail("operator signatures require the local_unattested trust profile")
    if not isinstance(evidence, dict):
        _fail("run bundle is missing its evidence record")
    if (
        evidence.get("evidence_class") != "local_unattested"
        or evidence.get("hardware_attestation") is not None
        or evidence.get("mock_attestation") is not None
    ):
        _fail("operator-signed DGX evidence must remain local and unattested")
    _require_sha256(bundle.get("bundle_sha256"), "bundle hash")
    _require_sha256(bundle.get("statement_sha256"), "statement hash")


def signing_payload(bundle_bytes: bytes, bundle: dict[str, Any]) -> dict[str, str]:
    _require_local_dgx_bundle(bundle)
    return {
        "context": SIGNATURE_CONTEXT,
        "bundle_file_sha256": _sha256(bundle_bytes),
        "bundle_sha256": bundle["bundle_sha256"],
        "statement_sha256": bundle["statement_sha256"],
    }


def _sign_bytes(
    payload: bytes,
    private_key: str | os.PathLike[str],
    *,
    openssl: str | os.PathLike[str],
    passphrase_file: str | os.PathLike[str] | None,
) -> bytes:
    key = _resolve_regular_file(private_key, "private key")
    _require_private_permissions(key, "private key")
    with _temporary_bytes(payload, "sparkinterval-signing-payload-") as payload_path:
        arguments = [
            "pkeyutl",
            "-sign",
            "-inkey",
            str(key),
            "-rawin",
            "-in",
            str(payload_path),
        ]
        arguments.extend(_passphrase_argument(passphrase_file, "-passin"))
        signature = _run_openssl(openssl, arguments)
    if len(signature) != ED25519_SIGNATURE_SIZE:
        _fail("OpenSSL returned an invalid Ed25519 signature length")
    return signature


def create_signature_envelope(
    bundle_bytes: bytes,
    bundle: dict[str, Any],
    private_key: str | os.PathLike[str],
    *,
    openssl: str | os.PathLike[str] = "openssl",
    passphrase_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Sign the exact canonical run-bundle bytes with a local operator key."""

    if bundle_bytes != canonical_json_bytes(bundle):
        _fail("run bundle bytes are not the canonical encoding of the bundle")
    payload = signing_payload(bundle_bytes, bundle)
    payload_bytes = canonical_json_bytes(payload)
    der = _private_key_spki_der(
        private_key,
        openssl=openssl,
        passphrase_file=passphrase_file,
    )
    signature = _sign_bytes(
        payload_bytes,
        private_key,
        openssl=openssl,
        passphrase_file=passphrase_file,
    )
    return {
        "schema_version": SIGNATURE_SCHEMA_VERSION,
        "signature_kind": SIGNATURE_KIND,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id_from_spki(der),
        "public_key_spki_der_base64": _canonical_base64(der),
        "signed_payload": payload,
        "signature_base64": _canonical_base64(signature),
        "warning": SIGNATURE_WARNING,
    }


def _write_new_canonical_json(value: Any, destination: str | os.PathLike[str]) -> Path:
    path = Path(destination).resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise LocalSignatureError(f"refusing to overwrite existing file: {path}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


@contextmanager
def _temporary_bytes(data: bytes, prefix: str) -> Iterable[Path]:
    descriptor, name = tempfile.mkstemp(prefix=prefix)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def sign_bundle_file(
    bundle_path: str | os.PathLike[str],
    private_key: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    artifact_root: str | os.PathLike[str],
    openssl: str | os.PathLike[str] = "openssl",
    passphrase_file: str | os.PathLike[str] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Integrity-check a DGX bundle and write its detached operator signature."""

    bundle_bytes, bundle = _load_bundle_bytes(bundle_path)
    # Import lazily so verify_run_bundle can import this module for its signed
    # policy without creating an import cycle.
    from verify_run_bundle import verify_bundle

    checked = verify_bundle(bundle, artifact_root=artifact_root)
    if checked["target_profile"] != "dgx_spark_sm121":
        _fail("operator signatures are restricted to DGX Spark bundles")
    envelope = create_signature_envelope(
        bundle_bytes,
        bundle,
        private_key,
        openssl=openssl,
        passphrase_file=passphrase_file,
    )
    return envelope, _write_new_canonical_json(envelope, output_path)


def validate_signature_envelope(
    envelope: Any,
    bundle_bytes: bytes,
    bundle: dict[str, Any],
) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    """Strictly validate an envelope and its binding before cryptography."""

    try:
        validate_json_value(envelope)
    except BundleError as exc:
        raise LocalSignatureError(str(exc)) from exc
    record = _exact_object(envelope, ENVELOPE_KEYS, "operator signature")
    if record["schema_version"] != SIGNATURE_SCHEMA_VERSION or isinstance(
        record["schema_version"], bool
    ):
        _fail("unsupported operator-signature schema version")
    if record["signature_kind"] != SIGNATURE_KIND:
        _fail("unexpected operator-signature kind")
    if record["algorithm"] != SIGNATURE_ALGORITHM:
        _fail("operator signature must use Ed25519")
    if record["warning"] != SIGNATURE_WARNING:
        _fail("operator signature warning is missing or altered")

    payload = _exact_object(record["signed_payload"], PAYLOAD_KEYS, "signed payload")
    if payload["context"] != SIGNATURE_CONTEXT:
        _fail("operator signature has the wrong domain-separation context")
    for field, label in (
        ("bundle_file_sha256", "signed bundle file hash"),
        ("bundle_sha256", "signed bundle hash"),
        ("statement_sha256", "signed statement hash"),
    ):
        _require_sha256(payload[field], label)
    _require_sha256(record["key_id"], "operator key id")

    _require_local_dgx_bundle(bundle)
    if bundle_bytes != canonical_json_bytes(bundle):
        _fail("run bundle bytes are not canonical")
    expected = signing_payload(bundle_bytes, bundle)
    if payload != expected:
        _fail("operator signature payload does not match the exact run bundle")

    der = _validate_ed25519_spki(
        _decode_canonical_base64(
            record["public_key_spki_der_base64"], "embedded public key"
        ),
        "embedded public key",
    )
    if record["key_id"] != key_id_from_spki(der):
        _fail("operator key id does not match the embedded public key")
    signature = _decode_canonical_base64(record["signature_base64"], "signature")
    if len(signature) != ED25519_SIGNATURE_SIZE:
        _fail("operator signature must be exactly 64 bytes")
    return record, der, signature, canonical_json_bytes(payload)


def verify_signature(
    bundle: dict[str, Any],
    envelope: Any,
    trusted_public_key: str | os.PathLike[str],
    *,
    openssl: str | os.PathLike[str] = "openssl",
    bundle_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Verify a detached signature against a separately pinned public key."""

    exact_bundle_bytes = canonical_json_bytes(bundle) if bundle_bytes is None else bundle_bytes
    record, embedded_der, signature, payload = validate_signature_envelope(
        envelope, exact_bundle_bytes, bundle
    )
    trusted_key = _resolve_regular_file(trusted_public_key, "trusted operator public key")
    trusted_der = public_key_spki_der(trusted_key, openssl=openssl)
    if trusted_der != embedded_der or key_id_from_spki(trusted_der) != record["key_id"]:
        _fail("operator signature key does not match the pinned trusted public key")

    with _temporary_bytes(
        signature, "sparkinterval-signature-"
    ) as signature_path, _temporary_bytes(
        payload, "sparkinterval-verification-payload-"
    ) as payload_path:
        _run_openssl(
            openssl,
            [
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(trusted_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
        )

    signed_payload = record["signed_payload"]
    return {
        "signature_valid": True,
        "signature_kind": SIGNATURE_KIND,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": record["key_id"],
        "bundle_file_sha256": signed_payload["bundle_file_sha256"],
        "bundle_sha256": signed_payload["bundle_sha256"],
        "statement_sha256": signed_payload["statement_sha256"],
        "hardware_evidence": False,
        "assurance": ASSURANCE,
    }


def load_signature(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        value = load_canonical_json(path)
    except BundleError as exc:
        raise LocalSignatureError(str(exc)) from exc
    if not isinstance(value, dict):
        _fail("operator signature must be a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    keygen = subcommands.add_parser("keygen", help="create a new Ed25519 key pair")
    keygen.add_argument("--private-key", required=True)
    keygen.add_argument("--public-key", required=True)
    keygen.add_argument("--openssl", default="openssl")
    key_choice = keygen.add_mutually_exclusive_group(required=True)
    key_choice.add_argument(
        "--passphrase-file",
        help="0600 file used to encrypt the private key",
    )
    key_choice.add_argument(
        "--allow-unencrypted-private-key",
        action="store_true",
        help="explicitly acknowledge creation of a mode-0600 unencrypted private key",
    )

    sign = subcommands.add_parser("sign", help="sign an integrity-checked DGX bundle")
    sign.add_argument("bundle")
    sign.add_argument("--artifact-root", required=True)
    sign.add_argument("--private-key", required=True)
    sign.add_argument("--passphrase-file")
    sign.add_argument("--openssl", default="openssl")
    sign.add_argument("--out", required=True)

    check = subcommands.add_parser("verify", help="verify bundle artifacts and its signature")
    check.add_argument("bundle")
    check.add_argument("signature")
    check.add_argument("--artifact-root", required=True)
    check.add_argument("--trusted-public-key", required=True)
    check.add_argument("--openssl", default="openssl")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "keygen":
            result = generate_keypair(
                args.private_key,
                args.public_key,
                openssl=args.openssl,
                passphrase_file=args.passphrase_file,
                allow_unencrypted_private_key=args.allow_unencrypted_private_key,
            )
        elif args.command == "sign":
            envelope, output = sign_bundle_file(
                args.bundle,
                args.private_key,
                args.out,
                artifact_root=args.artifact_root,
                openssl=args.openssl,
                passphrase_file=args.passphrase_file,
            )
            result = {
                "algorithm": envelope["algorithm"],
                "key_id": envelope["key_id"],
                "output": str(output),
                "statement_sha256": envelope["signed_payload"]["statement_sha256"],
                "warning": SIGNATURE_WARNING,
            }
        else:
            bundle_bytes, bundle = _load_bundle_bytes(args.bundle)
            from verify_run_bundle import verify_bundle

            integrity = verify_bundle(bundle, artifact_root=args.artifact_root)
            signature = verify_signature(
                bundle,
                load_signature(args.signature),
                args.trusted_public_key,
                openssl=args.openssl,
                bundle_bytes=bundle_bytes,
            )
            result = {**integrity, **signature}
    except (BundleError, LocalSignatureError, OSError) as exc:
        print(f"local_operator_signature: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
