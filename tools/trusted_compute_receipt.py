#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Issue and verify compact receipts for attested Azure CPU/H100 runs.

The large Azure, AMD, TPM, and NVIDIA evidence is appraised by a separately
pinned executable.  This tool binds that appraisal to an integrity-checked run
bundle, normalizes the exact Lean claim, and countersigns the compact receipt.
It never treats a self-reported ``accepted`` flag in an input file as evidence:
the verifier is executed for every issuance and its executable and policy are
both hashed into the signed receipt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from create_run_bundle import (
    BundleError,
    canonical_json_bytes,
    canonical_sha256,
    hash_file,
    load_canonical_json,
    parse_json_bytes,
    sha256_bytes,
    validate_sha256,
)
import verify_run_bundle
from tg_verifier.campaign_io import CampaignIOError, read_bytes_once
from tg_verifier.numeric_corpus import NumericCorpusError, parse_pin_bytes
from tg_verifier import sqrt218_fixed_v2_receipt as sqrt218_fixed_v2


SCHEMA_VERSION = 1
RECEIPT_KIND = "sparkinterval_trusted_compute_receipt"
SIGNATURE_ALGORITHM = "rsassa_pkcs1_v1_5_sha256_rsa3072"
BOOTSTRAP_KEY_ID = "sparkinterval-bootstrap-rsa3072-2026-07"
# Backward-compatible name used by the checked-in development fixture.
KEY_ID = BOOTSTRAP_KEY_ID
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ALGORITHM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
RSA3072_SIGNATURE_RE = re.compile(r"^[0-9a-f]{768}$")
MAX_NUMERIC_CORPUS_PIN_BYTES = 16 * 1024 * 1024
NOT_APPLICABLE_DIGEST = sha256_bytes(
    b"sparkinterval.trusted-compute.not-applicable.v1"
)
ZERO_DIGEST = "0" * 64
BACKENDS = ("azure_sevsnp_cpu", "azure_ncc40ads_h100_v5")
DEFAULT_PUBLIC_KEY = (
    Path(__file__).resolve().parent.parent
    / "profiles/verifier_keys"
    / f"{BOOTSTRAP_KEY_ID}-public.pem"
)

CLAIM_KEYS = {
    "algorithm_id",
    "algorithm_hash",
    "input_hash",
    "parameters_hash",
    "domain_hash",
    "result",
    "output_hash",
    "nonce",
    "target",
    "target_profile_hash",
    "trust",
    "trust_profile_hash",
    "artifacts",
    "completion",
}
ARTIFACT_KEYS = {
    "source_tree_hash",
    "host_executable_hash",
    "device_cubin_hash",
    "kernel_manifest_hash",
}
EVIDENCE_HASH_KEYS = {
    "platform_evidence_sha256",
    "azure_maa_token_sha256",
    "amd_snp_report_sha256",
    "tpm_quote_sha256",
    "tpm_event_log_sha256",
    "nvidia_eat_sha256",
    "nvidia_evidence_sha256",
}
VERIFICATION_OUTPUT_KEYS = {
    "schema_version",
    "kind",
    "accepted",
    "backend",
    "appraised_at_utc",
    "not_before_utc",
    "not_after_utc",
    "start_challenge_sha256",
    "result_binding_sha256",
    "policy_sha256",
    "evidence_hashes",
}


class ReceiptError(ValueError):
    """Issuance, normalization, or signature verification failed."""


def numeric_corpus_pin_binding(
    pin_path: Path,
    *,
    expected_input_hash: str,
    expected_input_size: int | None = None,
) -> dict[str, Any]:
    """Project one canonical numeric-corpus pin from a signed input hash.

    Trusted-compute receipt v1 deliberately keeps one generic ``input_hash``.
    When the exact input artifact is a canonical numeric-corpus pin, this
    check makes the transitive binding explicit:

      receipt signature -> claim.input_hash -> exact pin bytes
        -> claim/manifest/payload/source identities.

    The returned object is an audit projection, not a second receipt and not
    an assertion that the referenced mathematical claim is true.
    """

    _required_digest(expected_input_hash, "trusted claim input hash")
    try:
        raw = read_bytes_once(pin_path, limit=MAX_NUMERIC_CORPUS_PIN_BYTES)
        pin = parse_pin_bytes(raw, label=str(pin_path))
    except (CampaignIOError, NumericCorpusError) as exc:
        raise ReceiptError(f"numeric-corpus input pin is invalid: {exc}") from exc
    actual_hash = sha256_bytes(raw)
    if actual_hash != expected_input_hash:
        raise ReceiptError(
            "numeric-corpus pin SHA-256 differs from the signed claim input hash"
        )
    if expected_input_size is not None:
        if (
            isinstance(expected_input_size, bool)
            or not isinstance(expected_input_size, int)
            or expected_input_size < 1
        ):
            raise ReceiptError("numeric-corpus input size is invalid")
        if len(raw) != expected_input_size:
            raise ReceiptError(
                "numeric-corpus pin size differs from the run-bundle input size"
            )
    expected = pin["expected"]
    repository = pin["repository"]
    return {
        "binding_kind": "sparkinterval.trusted_compute.numeric_corpus_input.v1",
        "claim_id": expected["claim_id"],
        "claim_version": expected["claim_version"],
        "corpus_id": expected["corpus_id"],
        "corpus_version": expected["corpus_version"],
        "manifest_path": repository["manifest_path"],
        "manifest_sha256": repository["manifest_sha256"],
        "payload_file_count": expected["payload_file_count"],
        "payload_root_sha256": expected["payload_root_sha256"],
        "payload_total_size_bytes": expected["payload_total_size_bytes"],
        "pin_id": pin["pin_id"],
        "pin_sha256": actual_hash,
        "repository_commit": repository["commit"],
        "repository_url": repository["url"],
        "source_root_sha256": expected["source_root_sha256"],
        "statement_sha256": expected["statement_sha256"],
    }


def _numeric_corpus_binding_for_bundle_input(
    bundle: Mapping[str, Any],
    artifact_root: Path,
    *,
    expected_input_hash: str,
) -> dict[str, Any]:
    """Check that the exact run-bundle input is one canonical corpus pin."""

    input_record = bundle["statement"]["input_artifact"]
    try:
        resolved_root = artifact_root.resolve(strict=True)
        candidate_input = resolved_root.joinpath(input_record["path"])
        if candidate_input.is_symlink():
            raise ReceiptError(
                "numeric-corpus run-bundle input must not be a symlink"
            )
        resolved_input = candidate_input.resolve(strict=True)
        resolved_input.relative_to(resolved_root)
    except ReceiptError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReceiptError(
            f"cannot resolve numeric-corpus run-bundle input: {exc}"
        ) from exc
    return numeric_corpus_pin_binding(
        candidate_input,
        expected_input_hash=expected_input_hash,
        expected_input_size=input_record["size_bytes"],
    )


def _subprocess_environment(
    *, allow_nvidia_service_key: bool = False, allow_azure_identity: bool = False
) -> dict[str, str]:
    """Construct a minimal environment for security-sensitive subprocesses."""

    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    if allow_nvidia_service_key and os.environ.get("NV_ATTESTATION_SERVICE_KEY"):
        environment["NV_ATTESTATION_SERVICE_KEY"] = os.environ[
            "NV_ATTESTATION_SERVICE_KEY"
        ]
    if allow_azure_identity:
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
            if os.environ.get(name):
                environment[name] = os.environ[name]
        if "AZURE_CONFIG_DIR" not in environment and os.environ.get("HOME"):
            environment["HOME"] = os.environ["HOME"]
    return environment


def _utc_now_text() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _snapshot_regular_file(
    source: Path,
    destination: Path,
    what: str,
    *,
    executable: bool = False,
    expected_digest: str | None = None,
) -> tuple[str, int]:
    """Copy one input through non-following FDs into a private invocation root."""

    if source.is_symlink():
        raise ReceiptError(f"{what} must not be a symlink")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    source_flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        source_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    try:
        source_fd = os.open(source, source_flags)
    except OSError as exc:
        raise ReceiptError(f"cannot open {what} for snapshot: {exc}") from exc
    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        destination_flags |= os.O_CLOEXEC
    destination_mode = 0o500 if executable else 0o400
    destination_fd: int | None = None
    digest = hashlib.sha256()
    size = 0
    try:
        source_metadata = os.fstat(source_fd)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise ReceiptError(f"{what} must be a regular file")
        if executable and not source_metadata.st_mode & 0o111:
            raise ReceiptError(f"{what} must be executable")
        destination_fd = os.open(
            destination, destination_flags, destination_mode
        )
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise ReceiptError(f"short write while snapshotting {what}")
                view = view[written:]
        os.fsync(destination_fd)
        os.fchmod(destination_fd, destination_mode)
        destination_metadata = os.fstat(destination_fd)
        if (
            not stat.S_ISREG(destination_metadata.st_mode)
            or destination_metadata.st_nlink != 1
            or stat.S_IMODE(destination_metadata.st_mode) != destination_mode
        ):
            raise ReceiptError(f"private snapshot for {what} is not a fresh regular file")
    except OSError as exc:
        raise ReceiptError(f"cannot snapshot {what}: {exc}") from exc
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)
    actual_digest = digest.hexdigest()
    if expected_digest is not None and actual_digest != expected_digest:
        raise ReceiptError(f"{what} differs from its pre-snapshot SHA-256")
    return actual_digest, size


def _secure_replay_database_path(
    database: Path,
) -> tuple[Path, int, tuple[int, int]]:
    """Open a private replay DB and retain its reviewed inode through connect."""

    if database.name in {"", ".", ".."}:
        raise ReceiptError("replay database path must name a file")
    if database.parent.is_symlink():
        raise ReceiptError("replay database parent must not be a symlink")
    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        parent = database.parent.resolve(strict=True)
    except OSError as exc:
        raise ReceiptError(f"cannot resolve replay database directory: {exc}") from exc
    try:
        parent_metadata = parent.stat()
    except OSError as exc:
        raise ReceiptError(f"cannot inspect replay database directory: {exc}") from exc
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise ReceiptError("replay database parent must be a directory")
    if parent_metadata.st_uid != os.geteuid():
        raise ReceiptError("replay database parent must be owned by the issuer account")
    if stat.S_IMODE(parent_metadata.st_mode) != 0o700:
        raise ReceiptError("replay database parent permissions must be exactly 0700")
    candidate = parent / database.name
    if candidate.is_symlink():
        raise ReceiptError("replay database must not be a symlink")
    flags = os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(descriptor, 0o600)
    except FileExistsError:
        try:
            descriptor = os.open(candidate, flags)
        except OSError as exc:
            raise ReceiptError(f"cannot securely open replay database: {exc}") from exc
    except OSError as exc:
        raise ReceiptError(f"cannot securely open replay database: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReceiptError("replay database must be a regular file")
        if metadata.st_uid != os.geteuid():
            raise ReceiptError("replay database must be owned by the issuer account")
        if metadata.st_nlink != 1:
            raise ReceiptError("replay database must have exactly one hard link")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ReceiptError("replay database permissions must be exactly 0600")
        identity = (metadata.st_dev, metadata.st_ino)
    except Exception:
        os.close(descriptor)
        raise
    return candidate, descriptor, identity


def _open_replay_database(database: Path) -> sqlite3.Connection:
    path, descriptor, expected_identity = _secure_replay_database_path(database)
    try:
        connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        path_metadata = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(path_metadata.st_mode)
            or (path_metadata.st_dev, path_metadata.st_ino) != expected_identity
            or path_metadata.st_uid != os.geteuid()
            or path_metadata.st_nlink != 1
            or stat.S_IMODE(path_metadata.st_mode) != 0o600
        ):
            raise ReceiptError("replay database inode changed while SQLite opened it")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA synchronous = FULL")
        mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
        if mode is None or str(mode[0]).lower() != "delete":
            raise ReceiptError("replay database did not enable DELETE journaling")
        checked = connection.execute("PRAGMA quick_check").fetchall()
        if checked != [("ok",)]:
            raise ReceiptError("replay database integrity check failed")
        os.close(descriptor)
        return connection
    except (sqlite3.Error, ReceiptError) as exc:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass
        if isinstance(exc, ReceiptError):
            raise
        raise ReceiptError(f"cannot open replay database {path}: {exc}") from exc


def _ensure_replay_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS trusted_compute_spent_challenges (
          nonce TEXT PRIMARY KEY NOT NULL,
          challenge_sha256 TEXT NOT NULL UNIQUE,
          wire_statement_sha256 TEXT NOT NULL,
          backend TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('reserved', 'signed')),
          reserved_at_utc TEXT NOT NULL,
          signed_at_utc TEXT,
          receipt_sha256 TEXT,
          CHECK (
            (status = 'reserved' AND signed_at_utc IS NULL AND receipt_sha256 IS NULL)
            OR
            (status = 'signed' AND signed_at_utc IS NOT NULL AND receipt_sha256 IS NOT NULL)
          )
        )"""
    )
    objects = connection.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('table', 'view', 'trigger') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    if objects != [("table", "trusted_compute_spent_challenges")]:
        raise ReceiptError("replay database contains unexpected schema objects")
    expected_columns = [
        "nonce",
        "challenge_sha256",
        "wire_statement_sha256",
        "backend",
        "status",
        "reserved_at_utc",
        "signed_at_utc",
        "receipt_sha256",
    ]
    actual_columns = [
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(trusted_compute_spent_challenges)"
        ).fetchall()
    ]
    if actual_columns != expected_columns:
        raise ReceiptError("replay database table has an unexpected schema")


def _reserve_challenge(
    database: Path,
    *,
    nonce: str,
    challenge_sha256: str,
    wire_statement_sha256: str,
    backend: str,
) -> None:
    """Atomically burn a challenge before any appraisal or signing begins."""

    for value, what in (
        (nonce, "challenge nonce"),
        (challenge_sha256, "retained challenge hash"),
        (wire_statement_sha256, "wire statement hash"),
    ):
        _required_digest(value, what)
    if backend not in BACKENDS:
        raise ReceiptError(f"unsupported replay-ledger backend: {backend}")
    connection = _open_replay_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_replay_schema(connection)
        try:
            connection.execute(
                "INSERT INTO trusted_compute_spent_challenges "
                "(nonce, challenge_sha256, wire_statement_sha256, backend, status, "
                "reserved_at_utc, signed_at_utc, receipt_sha256) "
                "VALUES (?, ?, ?, ?, 'reserved', ?, NULL, NULL)",
                (
                    nonce,
                    challenge_sha256,
                    wire_statement_sha256,
                    backend,
                    _utc_now_text(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            connection.execute("ROLLBACK")
            raise ReceiptError("retained challenge is already spent") from exc
        connection.execute("COMMIT")
    except ReceiptError:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error as exc:
        if connection.in_transaction:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise ReceiptError(f"cannot reserve retained challenge: {exc}") from exc
    finally:
        connection.close()


def _mark_challenge_signed(
    database: Path,
    *,
    nonce: str,
    challenge_sha256: str,
    wire_statement_sha256: str,
    backend: str,
    receipt_sha256: str,
) -> None:
    """Transition the exact burned row to signed after durable output install."""

    _required_digest(receipt_sha256, "receipt hash")
    connection = _open_replay_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_replay_schema(connection)
        cursor = connection.execute(
            "UPDATE trusted_compute_spent_challenges "
            "SET status = 'signed', signed_at_utc = ?, receipt_sha256 = ? "
            "WHERE nonce = ? AND challenge_sha256 = ? AND wire_statement_sha256 = ? "
            "AND backend = ? AND status = 'reserved' "
            "AND signed_at_utc IS NULL AND receipt_sha256 IS NULL",
            (
                _utc_now_text(),
                receipt_sha256,
                nonce,
                challenge_sha256,
                wire_statement_sha256,
                backend,
            ),
        )
        if cursor.rowcount != 1:
            connection.execute("ROLLBACK")
            raise ReceiptError("replay ledger lacks the exact reserved challenge row")
        connection.execute("COMMIT")
    except ReceiptError:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error as exc:
        if connection.in_transaction:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise ReceiptError(f"cannot finalize retained challenge: {exc}") from exc
    finally:
        connection.close()


def _install_new_receipt(destination: Path, payload: bytes) -> None:
    """Durably install a fresh receipt without ever replacing an old path."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve(strict=True)
    final = parent / destination.name
    if final.is_symlink() or final.exists():
        raise ReceiptError(f"refusing to replace existing receipt output: {final}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    installed = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, final, follow_symlinks=False)
        except FileExistsError as exc:
            raise ReceiptError(f"refusing to replace existing receipt output: {final}") from exc
        installed = True
        temporary.unlink()
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        if not installed:
            # Never remove ``final`` here: a concurrent creator owns any path
            # that made our link fail.
            pass


def _canonical_utc_timestamp(value: Any, what: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ReceiptError(f"{what} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ReceiptError(
            f"{what} must use canonical YYYY-MM-DDTHH:MM:SSZ syntax"
        ) from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _exact_object(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise ReceiptError(
            f"{what} has wrong fields "
            f"(missing={sorted(keys - actual)}, unexpected={sorted(actual - keys)})"
        )
    return value


def _required_digest(value: Any, what: str, *, allow_not_applicable: bool = False) -> str:
    try:
        digest = validate_sha256(value, what)
    except BundleError as exc:
        raise ReceiptError(str(exc)) from exc
    if digest == ZERO_DIGEST:
        raise ReceiptError(f"{what} cannot be the all-zero placeholder")
    if not allow_not_applicable and digest == NOT_APPLICABLE_DIGEST:
        raise ReceiptError(f"{what} cannot be the not-applicable marker")
    return digest


def _committed_field(name: str, value: str) -> str:
    return f"{name}={sha256_bytes(value.encode('utf-8'))}\n"


def claim_commitment_payload(claim: Mapping[str, Any]) -> str:
    artifacts = claim["artifacts"]
    fields = (
        ("algorithm_id", claim["algorithm_id"]),
        ("algorithm_hash", claim["algorithm_hash"]),
        ("input_hash", claim["input_hash"]),
        ("parameters_hash", claim["parameters_hash"]),
        ("domain_hash", claim["domain_hash"]),
        ("result", claim["result"]),
        ("output_hash", claim["output_hash"]),
        ("nonce", claim["nonce"]),
        ("target", claim["target"]),
        ("target_profile_hash", claim["target_profile_hash"]),
        ("trust", claim["trust"]),
        ("trust_profile_hash", claim["trust_profile_hash"]),
        ("source_tree_hash", artifacts["source_tree_hash"]),
        ("host_executable_hash", artifacts["host_executable_hash"]),
        ("device_cubin_hash", artifacts["device_cubin_hash"]),
        ("kernel_manifest_hash", artifacts["kernel_manifest_hash"]),
        ("completion", claim["completion"]),
    )
    return "sparkinterval.trusted-compute.claim.v1\n" + "".join(
        _committed_field(name, value) for name, value in fields
    )


def claim_commitment(claim: Mapping[str, Any]) -> str:
    return sha256_bytes(claim_commitment_payload(claim).encode("utf-8"))


def expected_result_binding(start_challenge: str, wire_statement: str) -> str:
    payload = (
        "sparkinterval.trusted-compute.result-binding.v1\n"
        f"start_challenge_sha256={start_challenge}\n"
        f"wire_statement_sha256={wire_statement}\n"
    )
    return sha256_bytes(payload.encode("ascii"))


def canonical_signed_payload(receipt: Mapping[str, Any]) -> bytes:
    bindings = receipt["bindings"]
    hashes = receipt["evidence_hashes"]
    verifier = receipt["verifier"]
    lines = (
        "sparkinterval.trusted-compute-receipt.v1\n"
        f"backend={receipt['backend']}\n"
        f"claim_sha256={claim_commitment(receipt['claim'])}\n"
        f"run_bundle_sha256={bindings['run_bundle_sha256']}\n"
        f"wire_statement_sha256={bindings['wire_statement_sha256']}\n"
        f"platform_evidence_sha256={hashes['platform_evidence_sha256']}\n"
        f"azure_maa_token_sha256={hashes['azure_maa_token_sha256']}\n"
        f"amd_snp_report_sha256={hashes['amd_snp_report_sha256']}\n"
        f"tpm_quote_sha256={hashes['tpm_quote_sha256']}\n"
        f"tpm_event_log_sha256={hashes['tpm_event_log_sha256']}\n"
        f"nvidia_eat_sha256={hashes['nvidia_eat_sha256']}\n"
        f"nvidia_evidence_sha256={hashes['nvidia_evidence_sha256']}\n"
        f"verifier_policy_sha256={verifier['policy_sha256']}\n"
        f"verifier_artifact_sha256={verifier['artifact_sha256']}\n"
        f"start_challenge_sha256={bindings['start_challenge_sha256']}\n"
        f"result_binding_sha256={bindings['result_binding_sha256']}\n"
        + _committed_field("issued_at", verifier["issued_at"])
        + _committed_field("expires_at", verifier["expires_at"])
        + _committed_field("verifier_key_id", verifier["key_id"])
    )
    return lines.encode("utf-8")


def _artifact_role(statement: Mapping[str, Any], role: str) -> str:
    matches = [
        item["sha256"] for item in statement["build_artifacts"] if item["role"] == role
    ]
    if len(matches) != 1:
        raise ReceiptError(f"trusted receipt requires exactly one {role!r} artifact")
    return _required_digest(matches[0], f"{role} hash")


def _artifact_role_record(
    statement: Mapping[str, Any], role: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in statement["build_artifacts"]
        if item["role"] == role
    ]
    if len(matches) != 1:
        raise ReceiptError(
            f"trusted receipt requires exactly one {role!r} artifact"
        )
    return matches[0]


def _path_beneath_root(root: Path, value: str, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReceiptError(f"{what} path is missing")
    candidate = root / value
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"{what} path escapes or is absent: {exc}") from exc
    return candidate


def _sqrt218_fixed_v2_projection_for_bundle(
    *,
    bundle: Mapping[str, Any],
    verified: Mapping[str, Any],
    artifact_root: Path,
    claim: Mapping[str, Any],
    native_result_path: str,
    verification_report_path: str,
    work_trace_path: str,
) -> dict[str, Any]:
    """Audit the fixed-V2 chain without replaying the production checker."""

    statement = bundle["statement"]
    environment = statement["execution_environment"]["value"]
    if not isinstance(environment, Mapping):
        raise ReceiptError(
            "fixed-V2 statement execution environment is malformed"
        )
    try:
        job_binding = environment["job_binding_sha256"]
    except KeyError as exc:
        raise ReceiptError(
            "fixed-V2 statement omits the measured-runner job binding"
        ) from exc
    certificate = _path_beneath_root(
        artifact_root,
        statement["input_artifact"]["path"],
        "fixed-V2 certificate",
    )
    result_envelope = _path_beneath_root(
        artifact_root,
        statement["output_artifact"]["path"],
        "fixed-V2 result envelope",
    )
    host = _artifact_role_record(statement, "host_executable")
    closure = _artifact_role_record(statement, "execution_manifest")
    checker_executable = _path_beneath_root(
        artifact_root, host["path"], "fixed-V2 checker executable"
    )
    execution_closure = _path_beneath_root(
        artifact_root, closure["path"], "fixed-V2 execution closure"
    )
    native_result = _path_beneath_root(
        artifact_root, native_result_path, "fixed-V2 native result"
    )
    verification_report = _path_beneath_root(
        artifact_root,
        verification_report_path,
        "fixed-V2 verification report",
    )
    work_trace = _path_beneath_root(
        artifact_root, work_trace_path, "fixed-V2 work trace"
    )
    try:
        projection, envelope_raw, trace_raw = (
            sqrt218_fixed_v2.build_projection(
                certificate=certificate,
                native_result=native_result,
                checker_executable=checker_executable,
                execution_closure=execution_closure,
                start_challenge_sha256=statement["nonce"],
                job_binding_sha256=job_binding,
                verification_report=verification_report,
                wire_statement_sha256=verified["statement_sha256"],
            )
        )
        if result_envelope.read_bytes() != envelope_raw:
            raise ReceiptError(
                "fixed-V2 output is not the exact native-result envelope"
            )
        if work_trace.read_bytes() != trace_raw:
            raise ReceiptError(
                "fixed-V2 output trace is not the exact canonical work trace"
            )
        sqrt218_fixed_v2.verify_exact_artifacts(
            projection,
            certificate=certificate,
            native_result=native_result,
            result_envelope=result_envelope,
            checker_executable=checker_executable,
            execution_closure=execution_closure,
            verification_report=verification_report,
            work_trace=work_trace,
        )
        sqrt218_fixed_v2.validate_claim_projection(projection, claim)
        sqrt218_fixed_v2.validate_wire_statement_projection(
            projection, statement
        )
    except sqrt218_fixed_v2.FixedV2ReceiptError as exc:
        raise ReceiptError(f"fixed-V2 receipt projection failed: {exc}") from exc
    return projection


def _device_hash(statement: Mapping[str, Any], backend: str) -> str:
    gpu_roles = {"gpu_cubin", "gpu_fatbin", "gpu_executable"}
    matches = [
        item["sha256"]
        for item in statement["build_artifacts"]
        if item["role"] in gpu_roles
    ]
    if backend == "azure_sevsnp_cpu":
        if matches:
            raise ReceiptError("CPU trusted receipt must not bind a GPU execution artifact")
        return NOT_APPLICABLE_DIGEST
    if len(matches) != 1:
        raise ReceiptError("H100 trusted receipt requires exactly one GPU execution artifact")
    return _required_digest(matches[0], "GPU execution artifact hash")


def claim_from_bundle(
    bundle: Mapping[str, Any], artifact_root: Path, backend: str
) -> dict[str, Any]:
    statement = bundle["statement"]
    target_id = statement["target_profile"]["profile_id"]
    trust_id = statement["trust_profile"]["profile_id"]
    expected = {
        "azure_sevsnp_cpu": (
            "azure_sevsnp_cpu",
            "azure_sevsnp_hardware_attested",
            "azure_sevsnp_cpu",
            "azure_sevsnp_confidential_compute",
        ),
        "azure_ncc40ads_h100_v5": (
            "azure_ncc40ads_h100_v5",
            "azure_ncc_sevsnp_vtpm_nvidia_cc_attested",
            "nvidia_h100_sm90",
            "nvidia_h100_confidential_compute",
        ),
    }[backend]
    if (target_id, trust_id) != expected[:2]:
        raise ReceiptError(
            f"backend {backend} requires target/trust {expected[:2]}, "
            f"got {(target_id, trust_id)}"
        )
    output_record = statement["output_artifact"]
    output_path = artifact_root.joinpath(output_record["path"])
    try:
        resolved_output = output_path.resolve(strict=True)
        resolved_output.relative_to(artifact_root)
        output_bytes = resolved_output.read_bytes()
        result = output_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ReceiptError(f"trusted result artifact must be readable UTF-8: {exc}") from exc
    # ``verify_bundle`` checked the output earlier, but the result text enters
    # the signed claim directly.  Hash the exact bytes just read so a file
    # replacement between bundle verification and claim construction cannot
    # pair substituted text with the statement's old output digest.
    if (
        len(output_bytes) != output_record["size_bytes"]
        or sha256_bytes(output_bytes) != output_record["sha256"]
    ):
        raise ReceiptError(
            "trusted result artifact changed after run-bundle verification"
        )
    return {
        "algorithm_id": statement["algorithm"]["algorithm_id"],
        "algorithm_hash": statement["algorithm"]["definition_sha256"],
        "input_hash": statement["input_artifact"]["sha256"],
        "parameters_hash": statement["parameters"]["canonical_sha256"],
        "domain_hash": statement["domain_coverage"]["canonical_sha256"],
        "result": result,
        "output_hash": output_record["sha256"],
        "nonce": statement["nonce"],
        "target": expected[2],
        "target_profile_hash": statement["target_profile"]["sha256"],
        "trust": expected[3],
        "trust_profile_hash": statement["trust_profile"]["sha256"],
        "artifacts": {
            "source_tree_hash": _artifact_role(statement, "source_tree"),
            "host_executable_hash": _artifact_role(statement, "host_executable"),
            "device_cubin_hash": _device_hash(statement, backend),
            "kernel_manifest_hash": _artifact_role(statement, "execution_manifest"),
        },
        "completion": "successful",
    }


def _run_evidence_verifier(
    executable: Path,
    evidence_pack: Path,
    policy: Path,
    retained_challenge: Path,
    backend: str,
    start_challenge: str,
    result_binding: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(executable),
            "--evidence-pack",
            str(evidence_pack),
            "--policy",
            str(policy),
            "--expected-challenge-file",
            str(retained_challenge),
            "--backend",
            backend,
            "--expected-start-challenge-sha256",
            start_challenge,
            "--expected-result-binding-sha256",
            result_binding,
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
        env=_subprocess_environment(allow_nvidia_service_key=True),
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise ReceiptError(
            f"evidence verifier rejected the run with status {completed.returncode}: {detail}"
        )
    try:
        value = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"evidence verifier did not emit one JSON object: {exc}") from exc
    result = _exact_object(value, VERIFICATION_OUTPUT_KEYS, "verifier output")
    if result["schema_version"] != 1 or result["kind"] != "sparkinterval_evidence_appraisal":
        raise ReceiptError("evidence verifier emitted an unsupported result")
    if result["accepted"] is not True or result["backend"] != backend:
        raise ReceiptError("evidence verifier did not affirm the requested backend")
    if result["start_challenge_sha256"] != start_challenge:
        raise ReceiptError("evidence verifier changed the start challenge")
    if result["result_binding_sha256"] != result_binding:
        raise ReceiptError("evidence verifier changed the result binding")
    appraised = _canonical_utc_timestamp(
        result["appraised_at_utc"], "appraisal time"
    )
    not_before = _canonical_utc_timestamp(
        result["not_before_utc"], "evidence not-before time"
    )
    not_after = _canonical_utc_timestamp(
        result["not_after_utc"], "evidence not-after time"
    )
    if not (not_before <= appraised < not_after):
        raise ReceiptError("evidence appraisal time is outside its verified interval")
    policy_digest, _ = hash_file(policy)
    if result["policy_sha256"] != policy_digest:
        raise ReceiptError("evidence verifier policy hash differs from the supplied policy")
    hashes = _exact_object(
        result["evidence_hashes"], EVIDENCE_HASH_KEYS, "verified evidence hashes"
    )
    for name, digest in hashes.items():
        _required_digest(
            digest,
            name,
            allow_not_applicable=(
                backend == "azure_sevsnp_cpu"
                and name in {"nvidia_eat_sha256", "nvidia_evidence_sha256"}
            ),
        )
    if backend == "azure_sevsnp_cpu":
        for name in ("nvidia_eat_sha256", "nvidia_evidence_sha256"):
            if hashes[name] != NOT_APPLICABLE_DIGEST:
                raise ReceiptError(f"CPU evidence must mark {name} not applicable")
    else:
        for name in ("nvidia_eat_sha256", "nvidia_evidence_sha256"):
            if hashes[name] == NOT_APPLICABLE_DIGEST:
                raise ReceiptError(f"H100 evidence cannot omit {name}")
    return result


def _snapshot_evidence_verifier(
    executable: Path, destination_root: Path, expected_digest: str
) -> Path:
    """Snapshot the verifier entry point and its directly imported source closure.

    The official verifier's source-pinned measured-run path imports modules
    from ``attestation/``, ``azure/``, and ``tools/``.  Flattening those exact
    files into the private invocation directory makes import resolution use
    only the immutable snapshots.  The interpreter/standard-library/root-store
    closure remains a measured-image production prerequisite.
    """

    destination_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    destination = destination_root / executable.name
    _snapshot_regular_file(
        executable,
        destination,
        "evidence verifier",
        executable=True,
        expected_digest=expected_digest,
    )
    if executable.name == "verify_azure_ncc_evidence.py":
        repository = executable.resolve().parents[1]
        modules = (
            repository / "attestation/collect_azure_ncc_evidence.py",
            repository / "attestation/measured_run_archive.py",
            repository / "attestation/verify_measured_runner_transcript.py",
            repository / "azure/measured_runner.py",
            repository / "tools/create_run_bundle.py",
        )
        for module in modules:
            if not module.is_file():
                raise ReceiptError(
                    f"official evidence verifier lacks imported source module {module.name}"
                )
            _snapshot_regular_file(
                module,
                destination_root / module.name,
                f"evidence verifier source module {module.name}",
            )
        package_modules = (
            repository / "tg_verifier/campaign_io.py",
            repository / "tg_verifier/goldbach_gpu_campaign.py",
            repository / "tg_verifier/goldbach_build_admission.py",
        )
        for module in package_modules:
            if not module.is_file():
                raise ReceiptError(
                    "official evidence verifier lacks imported source module "
                    f"tg_verifier/{module.name}"
                )
            _snapshot_regular_file(
                module,
                destination_root / "tg_verifier" / module.name,
                f"evidence verifier source module tg_verifier/{module.name}",
            )
    return destination


def _sign(payload: bytes, private_key: Path, openssl: str) -> str:
    completed = subprocess.run(
        [openssl, "dgst", "-sha256", "-sign", str(private_key)],
        input=payload,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_subprocess_environment(),
    )
    if completed.returncode != 0:
        raise ReceiptError(
            "receipt signing failed: "
            + completed.stderr.decode("utf-8", errors="replace")[-2000:]
        )
    if len(completed.stdout) != 384:
        raise ReceiptError("receipt signer did not produce one RSA-3072 signature")
    return completed.stdout.hex()


def _sign_external(payload: bytes, executable: Path, arguments: list[str]) -> str:
    """Run a non-shell signer that consumes payload bytes and returns raw RSA.

    The Azure Managed HSM adapter implements this contract.  Exact argv is
    supplied explicitly; no command string is interpreted by a shell.
    """
    signer = executable.resolve(strict=True)
    if not signer.is_file() or not os.access(signer, os.X_OK):
        raise ReceiptError("external signer must be an executable regular file")
    with tempfile.TemporaryDirectory(
        prefix="sparkinterval-receipt-signer-"
    ) as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        signer_snapshot = snapshot_root / signer.name
        _snapshot_regular_file(
            signer,
            signer_snapshot,
            "external receipt signer",
            executable=True,
        )
        try:
            completed = subprocess.run(
                [str(signer_snapshot), *arguments],
                input=payload,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
                env=_subprocess_environment(allow_azure_identity=True),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReceiptError(f"external receipt signer could not run: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise ReceiptError(
            f"external receipt signer failed with status {completed.returncode}: {detail}"
        )
    if len(completed.stdout) != 384:
        raise ReceiptError("external receipt signer did not produce 384 raw RSA bytes")
    return completed.stdout.hex()


def verify_signature(
    receipt: Mapping[str, Any],
    public_key: Path | None = None,
    openssl: str = "openssl",
) -> None:
    if public_key is None:
        if receipt["verifier"]["key_id"] != BOOTSTRAP_KEY_ID:
            raise ReceiptError(
                "no public key was supplied for this non-bootstrap verifier key"
            )
        public_key = DEFAULT_PUBLIC_KEY
    signature = receipt["signature"]
    try:
        signature_bytes = bytes.fromhex(signature["value_hex"])
    except ValueError as exc:
        raise ReceiptError("signature is not hexadecimal") from exc
    if len(signature_bytes) != 384:
        raise ReceiptError("signature is not 384-byte RSA-3072 data")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        payload_path = root / "payload"
        signature_path = root / "signature"
        payload_path.write_bytes(canonical_signed_payload(receipt))
        signature_path.write_bytes(signature_bytes)
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
            env=_subprocess_environment(),
        )
    if completed.returncode != 0:
        raise ReceiptError("trusted-compute receipt signature is invalid")


def validate_receipt(receipt: Any) -> dict[str, Any]:
    top_keys = {
        "schema_version",
        "receipt_kind",
        "backend",
        "claim",
        "bindings",
        "evidence_hashes",
        "verifier",
        "signature",
        "receipt_sha256",
    }
    result = _exact_object(receipt, top_keys, "trusted-compute receipt")
    if result["schema_version"] != SCHEMA_VERSION:
        raise ReceiptError("unsupported trusted-compute receipt version")
    if result["receipt_kind"] != RECEIPT_KIND or result["backend"] not in BACKENDS:
        raise ReceiptError("unsupported trusted-compute receipt kind or backend")
    claim = _exact_object(result["claim"], CLAIM_KEYS, "claim")
    _exact_object(claim["artifacts"], ARTIFACT_KEYS, "claim artifacts")
    if claim["completion"] != "successful":
        raise ReceiptError("trusted receipt must bind successful completion")
    if not isinstance(claim["result"], str) or not isinstance(claim["algorithm_id"], str):
        raise ReceiptError("claim algorithm and result must be strings")
    if ALGORITHM_ID_RE.fullmatch(claim["algorithm_id"]) is None:
        raise ReceiptError("claim algorithm_id is malformed")
    for name in CLAIM_KEYS - {"result", "algorithm_id", "artifacts", "completion", "target", "trust"}:
        _required_digest(claim[name], f"claim {name}")
    for name, digest in claim["artifacts"].items():
        _required_digest(
            digest,
            f"claim artifact {name}",
            allow_not_applicable=name == "device_cubin_hash",
        )
    if sha256_bytes(claim["result"].encode("utf-8")) != claim["output_hash"]:
        raise ReceiptError("claim result bytes differ from claim output_hash")
    expected_claim_class = {
        "azure_sevsnp_cpu": (
            "azure_sevsnp_cpu",
            "azure_sevsnp_confidential_compute",
        ),
        "azure_ncc40ads_h100_v5": (
            "nvidia_h100_sm90",
            "nvidia_h100_confidential_compute",
        ),
    }[result["backend"]]
    if (claim["target"], claim["trust"]) != expected_claim_class:
        raise ReceiptError("claim target/trust class differs from receipt backend")
    bindings = _exact_object(
        result["bindings"],
        {
            "run_bundle_sha256",
            "wire_statement_sha256",
            "start_challenge_sha256",
            "result_binding_sha256",
        },
        "bindings",
    )
    for name, digest in bindings.items():
        _required_digest(digest, name)
    if claim["nonce"] != bindings["start_challenge_sha256"]:
        raise ReceiptError("claim nonce differs from start challenge")
    if bindings["result_binding_sha256"] != expected_result_binding(
        bindings["start_challenge_sha256"], bindings["wire_statement_sha256"]
    ):
        raise ReceiptError("result binding digest is invalid")
    hashes = _exact_object(result["evidence_hashes"], EVIDENCE_HASH_KEYS, "evidence hashes")
    for name, digest in hashes.items():
        _required_digest(digest, name, allow_not_applicable=name.startswith("nvidia_"))
    if result["backend"] == "azure_sevsnp_cpu":
        if claim["artifacts"]["device_cubin_hash"] != NOT_APPLICABLE_DIGEST:
            raise ReceiptError("CPU receipt must mark the device image not applicable")
        if any(
            hashes[name] != NOT_APPLICABLE_DIGEST
            for name in ("nvidia_eat_sha256", "nvidia_evidence_sha256")
        ):
            raise ReceiptError("CPU receipt must mark NVIDIA evidence not applicable")
    else:
        if claim["artifacts"]["device_cubin_hash"] == NOT_APPLICABLE_DIGEST:
            raise ReceiptError("H100 receipt must bind an exact device execution image")
        if any(
            hashes[name] == NOT_APPLICABLE_DIGEST
            for name in ("nvidia_eat_sha256", "nvidia_evidence_sha256")
        ):
            raise ReceiptError("H100 receipt must bind NVIDIA evidence")
    verifier = _exact_object(
        result["verifier"],
        {"policy_sha256", "artifact_sha256", "issued_at", "expires_at", "key_id"},
        "verifier",
    )
    _required_digest(verifier["policy_sha256"], "verifier policy hash")
    _required_digest(verifier["artifact_sha256"], "verifier artifact hash")
    issued = _canonical_utc_timestamp(verifier["issued_at"], "issued_at")
    expires = _canonical_utc_timestamp(verifier["expires_at"], "expires_at")
    if issued >= expires:
        raise ReceiptError("receipt expiry must be after issuance")
    if (
        not isinstance(verifier["key_id"], str)
        or KEY_ID_RE.fullmatch(verifier["key_id"]) is None
    ):
        raise ReceiptError("receipt verifier key id is malformed")
    signature = _exact_object(
        result["signature"], {"algorithm", "key_id", "value_hex"}, "signature"
    )
    if (
        signature["algorithm"] != SIGNATURE_ALGORITHM
        or signature["key_id"] != verifier["key_id"]
    ):
        raise ReceiptError("unsupported receipt signature identity")
    if (
        not isinstance(signature["value_hex"], str)
        or RSA3072_SIGNATURE_RE.fullmatch(signature["value_hex"]) is None
    ):
        raise ReceiptError(
            "signature value must be exactly 768 lowercase hexadecimal characters"
        )
    core = {key: result[key] for key in top_keys - {"receipt_sha256"}}
    if result["receipt_sha256"] != canonical_sha256(core):
        raise ReceiptError("trusted-compute receipt hash is invalid")
    return result


def load_canonical_receipt(path: Path) -> dict[str, Any]:
    """Load canonical receipt JSON, permitting one conventional final newline."""

    raw = path.read_bytes()
    payload = raw[:-1] if raw.endswith(b"\n") else raw
    receipt = validate_receipt(parse_json_bytes(payload, str(path)))
    if canonical_json_bytes(receipt) != payload:
        raise ReceiptError(f"{path} is not canonical receipt JSON")
    return receipt


def issue(args: argparse.Namespace) -> dict[str, Any]:
    if args.backend not in BACKENDS:
        raise ReceiptError(f"unsupported backend: {args.backend}")
    key_id = args.verifier_key_id
    if KEY_ID_RE.fullmatch(key_id) is None:
        raise ReceiptError("--verifier-key-id is malformed")
    if key_id != BOOTSTRAP_KEY_ID and args.public_key is None:
        raise ReceiptError(
            "non-bootstrap verifier key IDs require an explicit --public-key"
        )
    if key_id != BOOTSTRAP_KEY_ID and args.private_key is not None:
        raise ReceiptError(
            "non-bootstrap verifier key IDs require --signer-command; "
            "--private-key is development-only"
        )
    bundle = load_canonical_json(args.bundle)
    verified = verify_run_bundle.verify_bundle(
        bundle,
        artifact_root=args.artifact_root,
        policy=verify_run_bundle.INTEGRITY_POLICY,
    )
    root = Path(args.artifact_root).resolve(strict=True)
    claim = claim_from_bundle(bundle, root, args.backend)
    numeric_corpus_binding: dict[str, Any] | None = None
    if getattr(args, "require_numeric_corpus_input", False):
        numeric_corpus_binding = _numeric_corpus_binding_for_bundle_input(
            bundle,
            root,
            expected_input_hash=claim["input_hash"],
        )
    sqrt218_projection: dict[str, Any] | None = None
    if getattr(args, "require_sqrt218_fixed_v2", False):
        required_paths = {
            "native result": getattr(
                args, "sqrt218_fixed_v2_native_result", None
            ),
            "verification report": getattr(
                args, "sqrt218_fixed_v2_verification_report", None
            ),
            "work trace": getattr(
                args, "sqrt218_fixed_v2_work_trace", None
            ),
        }
        missing = [
            name for name, value in required_paths.items() if value is None
        ]
        if missing:
            raise ReceiptError(
                "--require-sqrt218-fixed-v2 also requires paths for "
                + ", ".join(missing)
            )
        sqrt218_projection = _sqrt218_fixed_v2_projection_for_bundle(
            bundle=bundle,
            verified=verified,
            artifact_root=root,
            claim=claim,
            native_result_path=required_paths["native result"],
            verification_report_path=required_paths["verification report"],
            work_trace_path=required_paths["work trace"],
        )
    start = claim["nonce"]
    wire_statement = verified["statement_sha256"]
    result_binding = expected_result_binding(start, wire_statement)
    verifier_path = Path(args.evidence_verifier).resolve(strict=True)
    if not verifier_path.is_file() or not os.access(verifier_path, os.X_OK):
        raise ReceiptError("evidence verifier must be an executable regular file")
    policy_path = Path(args.evidence_policy).resolve(strict=True)
    if not policy_path.is_file():
        raise ReceiptError("evidence policy must be a regular file")
    evidence_pack = Path(args.evidence_pack).resolve(strict=True)
    retained_challenge_input = Path(args.retained_challenge)
    if retained_challenge_input.is_symlink():
        raise ReceiptError("retained off-VM challenge must not be a symlink")
    retained_challenge = retained_challenge_input.resolve(strict=True)
    if not retained_challenge.is_file():
        raise ReceiptError("retained off-VM challenge must be a regular file")
    verifier_hash_before, _ = hash_file(verifier_path)
    replay_database = Path(args.replay_db)
    with tempfile.TemporaryDirectory(
        prefix="sparkinterval-receipt-appraisal-"
    ) as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        if stat.S_IMODE(snapshot_root.stat().st_mode) != 0o700:
            raise ReceiptError("private receipt-appraisal snapshot is not mode 0700")
        verifier_snapshot = _snapshot_evidence_verifier(
            verifier_path,
            snapshot_root / "verifier",
            verifier_hash_before,
        )
        policy_snapshot = snapshot_root / "evidence-policy"
        policy_hash_before, _ = _snapshot_regular_file(
            policy_path,
            policy_snapshot,
            "evidence policy",
        )
        challenge_snapshot = snapshot_root / "retained-challenge.json"
        challenge_digest_before, _ = _snapshot_regular_file(
            retained_challenge,
            challenge_snapshot,
            "retained off-VM challenge",
        )
        _reserve_challenge(
            replay_database,
            nonce=start,
            challenge_sha256=challenge_digest_before,
            wire_statement_sha256=wire_statement,
            backend=args.backend,
        )
        appraisal = _run_evidence_verifier(
            verifier_snapshot,
            evidence_pack,
            policy_snapshot,
            challenge_snapshot,
            args.backend,
            start,
            result_binding,
        )
        challenge_digest_after, _ = hash_file(challenge_snapshot)
        verifier_hash_after, _ = hash_file(verifier_snapshot)
        policy_hash_after, _ = hash_file(policy_snapshot)
        if challenge_digest_after != challenge_digest_before:
            raise ReceiptError(
                "retained challenge snapshot changed during evidence appraisal"
            )
        if verifier_hash_after != verifier_hash_before:
            raise ReceiptError("evidence verifier snapshot changed during appraisal")
        if policy_hash_after != policy_hash_before:
            raise ReceiptError("evidence policy snapshot changed during appraisal")
        if appraisal["policy_sha256"] != policy_hash_before:
            raise ReceiptError("evidence appraisal did not use the snapshotted policy pin")
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": RECEIPT_KIND,
        "backend": args.backend,
        "claim": claim,
        "bindings": {
            "run_bundle_sha256": verified["bundle_sha256"],
            "wire_statement_sha256": wire_statement,
            "start_challenge_sha256": start,
            "result_binding_sha256": result_binding,
        },
        "evidence_hashes": appraisal["evidence_hashes"],
        "verifier": {
            "policy_sha256": appraisal["policy_sha256"],
            "artifact_sha256": verifier_hash_before,
            "issued_at": appraisal["appraised_at_utc"],
            "expires_at": appraisal["not_after_utc"],
            "key_id": key_id,
        },
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "value_hex": "",
        },
    }
    signed_payload = canonical_signed_payload(receipt)
    if args.private_key is not None:
        receipt["signature"]["value_hex"] = _sign(
            signed_payload, Path(args.private_key), args.openssl
        )
    else:
        receipt["signature"]["value_hex"] = _sign_external(
            signed_payload, Path(args.signer_command), args.signer_arg
        )
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_receipt(receipt)
    verification_key = Path(args.public_key) if args.public_key is not None else None
    verify_signature(receipt, verification_key, args.openssl)
    _install_new_receipt(Path(args.out), canonical_json_bytes(receipt))
    _mark_challenge_signed(
        replay_database,
        nonce=start,
        challenge_sha256=challenge_digest_before,
        wire_statement_sha256=wire_statement,
        backend=args.backend,
        receipt_sha256=receipt["receipt_sha256"],
    )
    if numeric_corpus_binding is not None:
        # This is process-local audit information only.  It must never be
        # serialized into receipt v1, whose signed wire format is mirrored in
        # Lean.  The cryptographic link is the signed ``claim.input_hash``.
        setattr(args, "_numeric_corpus_binding", numeric_corpus_binding)
    if sqrt218_projection is not None:
        # Process-local audit output only.  Receipt V1 remains unchanged, and
        # the exact signed claim/wire statement carry the authoritative fields.
        setattr(args, "_sqrt218_fixed_v2_projection", sqrt218_projection)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    issue_parser = subparsers.add_parser("issue")
    issue_parser.add_argument("--bundle", required=True)
    issue_parser.add_argument("--artifact-root", required=True)
    issue_parser.add_argument("--backend", choices=BACKENDS, required=True)
    issue_parser.add_argument("--evidence-pack", required=True)
    issue_parser.add_argument("--evidence-verifier", required=True)
    issue_parser.add_argument("--evidence-policy", required=True)
    issue_parser.add_argument(
        "--retained-challenge",
        required=True,
        help="exact canonical challenge file retained outside the worker VM",
    )
    issue_parser.add_argument(
        "--replay-db",
        required=True,
        help="durable relying-party SQLite ledger; challenges burn before appraisal",
    )
    signer = issue_parser.add_mutually_exclusive_group(required=True)
    signer.add_argument(
        "--private-key",
        help="development/offline PEM signer; production should use --signer-command",
    )
    signer.add_argument(
        "--signer-command",
        help="executable that reads the canonical payload and writes 384 raw RSA bytes",
    )
    issue_parser.add_argument(
        "--signer-arg",
        action="append",
        default=[],
        help="one literal argument passed to --signer-command; repeat as needed",
    )
    issue_parser.add_argument("--verifier-key-id", default=BOOTSTRAP_KEY_ID)
    issue_parser.add_argument(
        "--public-key",
        help="explicit verifier public key; required for every non-bootstrap key ID",
    )
    issue_parser.add_argument("--openssl", default="openssl")
    issue_parser.add_argument(
        "--require-numeric-corpus-input",
        action="store_true",
        help=(
            "require the exact run-bundle input artifact to be a canonical "
            "pinned-numeric-corpus file and bind its audit projection"
        ),
    )
    issue_parser.add_argument(
        "--require-sqrt218-fixed-v2",
        action="store_true",
        help=(
            "require the exact fixed-width Sqrt218 V2 result-envelope, "
            "immutable-input digest, trace, checker, closure, and report "
            "bindings before signing; this never replays the production loop"
        ),
    )
    issue_parser.add_argument(
        "--sqrt218-fixed-v2-native-result",
        help="artifact-root-relative retained 120-byte SQ218R2 result",
    )
    issue_parser.add_argument(
        "--sqrt218-fixed-v2-verification-report",
        help="artifact-root-relative retained fixed-V2 verification report",
    )
    issue_parser.add_argument(
        "--sqrt218-fixed-v2-work-trace",
        help="artifact-root-relative canonical fixed-V2 work trace",
    )
    issue_parser.add_argument("--out", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("receipt")
    verify_parser.add_argument(
        "--public-key",
        help="explicit verifier public key; required for non-bootstrap receipts",
    )
    verify_parser.add_argument("--openssl", default="openssl")
    verify_parser.add_argument(
        "--numeric-corpus-pin",
        help=(
            "also require this canonical corpus pin's exact bytes to match "
            "the signed claim.input_hash"
        ),
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-reviewed-pins",
        help=(
            "fast receipt-only Sqrt218 V2 audit against compact reviewed "
            "digest/size pins; never opens or replays the production certificate"
        ),
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-bundle",
        help=(
            "also audit this exact fixed-V2 run bundle and retained artifacts; "
            "signature verification happens first and no production replay occurs"
        ),
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-artifact-root",
        help="artifact root paired with --sqrt218-fixed-v2-bundle",
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-native-result",
        help="artifact-root-relative retained 120-byte SQ218R2 result",
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-verification-report",
        help="artifact-root-relative retained fixed-V2 verification report",
    )
    verify_parser.add_argument(
        "--sqrt218-fixed-v2-work-trace",
        help="artifact-root-relative canonical fixed-V2 work trace",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "issue":
            receipt = issue(args)
            summary = {
                "accepted_for_lean": False,
                "backend": receipt["backend"],
                "receipt_issued": True,
                "receipt_sha256": receipt["receipt_sha256"],
                "verifier_key_id": receipt["verifier"]["key_id"],
            }
            binding = getattr(args, "_numeric_corpus_binding", None)
            if binding is not None:
                summary["numeric_corpus_binding"] = binding
            sqrt218_projection = getattr(
                args, "_sqrt218_fixed_v2_projection", None
            )
            if sqrt218_projection is not None:
                summary["sqrt218_fixed_v2_projection"] = {
                    "production_replay_performed": False,
                    "projection_kind": sqrt218_fixed_v2.PROJECTION_KIND,
                    "projection_sha256": sha256_bytes(
                        canonical_json_bytes(sqrt218_projection)
                    ),
                    "signed_field_projection_valid": True,
                }
        else:
            receipt = load_canonical_receipt(Path(args.receipt))
            verification_key = Path(args.public_key) if args.public_key is not None else None
            verify_signature(receipt, verification_key, args.openssl)
            summary = {
                "accepted_for_lean": False,
                "backend": receipt["backend"],
                "receipt_sha256": receipt["receipt_sha256"],
                "signature_valid": True,
                "verifier_key_id": receipt["verifier"]["key_id"],
            }
            if args.numeric_corpus_pin is not None:
                summary["numeric_corpus_binding"] = numeric_corpus_pin_binding(
                    Path(args.numeric_corpus_pin),
                    expected_input_hash=receipt["claim"]["input_hash"],
                )
            if args.sqrt218_fixed_v2_reviewed_pins is not None:
                reviewed_pins = (
                    sqrt218_fixed_v2.load_canonical_reviewed_pins(
                        Path(args.sqrt218_fixed_v2_reviewed_pins)
                    )
                )
                summary["sqrt218_fixed_v2_receipt_only"] = (
                    sqrt218_fixed_v2.validate_receipt_only_binding(
                        receipt, reviewed_pins
                    )
                )
            fixed_values = {
                "bundle": args.sqrt218_fixed_v2_bundle,
                "artifact root": args.sqrt218_fixed_v2_artifact_root,
                "native result": args.sqrt218_fixed_v2_native_result,
                "verification report":
                    args.sqrt218_fixed_v2_verification_report,
                "work trace": args.sqrt218_fixed_v2_work_trace,
            }
            supplied = [
                name for name, value in fixed_values.items()
                if value is not None
            ]
            if supplied and len(supplied) != len(fixed_values):
                missing = [
                    name for name, value in fixed_values.items()
                    if value is None
                ]
                raise ReceiptError(
                    "fixed-V2 receipt audit requires all artifact arguments; "
                    f"missing {', '.join(missing)}"
                )
            if supplied:
                bundle = load_canonical_json(fixed_values["bundle"])
                artifact_root = Path(
                    fixed_values["artifact root"]
                ).resolve(strict=True)
                verified = verify_run_bundle.verify_bundle(
                    bundle,
                    artifact_root=artifact_root,
                    policy=verify_run_bundle.INTEGRITY_POLICY,
                )
                if verified["bundle_sha256"] != receipt["bindings"][
                    "run_bundle_sha256"
                ]:
                    raise ReceiptError(
                        "fixed-V2 run bundle differs from the signed bundle hash"
                    )
                if verified["statement_sha256"] != receipt["bindings"][
                    "wire_statement_sha256"
                ]:
                    raise ReceiptError(
                        "fixed-V2 statement differs from the signed statement hash"
                    )
                expected_claim = claim_from_bundle(
                    bundle, artifact_root, receipt["backend"]
                )
                if expected_claim != receipt["claim"]:
                    raise ReceiptError(
                        "fixed-V2 run-bundle claim differs from the signed claim"
                    )
                projection = _sqrt218_fixed_v2_projection_for_bundle(
                    bundle=bundle,
                    verified=verified,
                    artifact_root=artifact_root,
                    claim=receipt["claim"],
                    native_result_path=fixed_values["native result"],
                    verification_report_path=fixed_values[
                        "verification report"
                    ],
                    work_trace_path=fixed_values["work trace"],
                )
                summary["sqrt218_fixed_v2_projection"] = (
                    sqrt218_fixed_v2.validate_receipt_projection(
                        projection,
                        receipt,
                        statement=bundle["statement"],
                    )
                )
    except (
        OSError,
        BundleError,
        ReceiptError,
        sqrt218_fixed_v2.FixedV2ReceiptError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"trusted_compute_receipt: {exc}", file=sys.stderr)
        return 2
    print(
        canonical_json_bytes(summary).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
