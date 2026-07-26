# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit the signed artifact chain for the fixed-width Sqrt218 V2 checker.

The production computation is intentionally *not* replayed here.  This module
only performs bounded parsing, hashing, and exact equality checks:

* the signed input is the complete ``SQ218V2\0`` certificate byte string;
* the signed UTF-8 result is an exact lowercase-hex envelope of the complete
  120-byte ``SQ218R2\0`` native result record;
* that record contains the SHA-256 of the checker's immutable input snapshot;
* the standard measured-runner trace binds the challenge, job, input, output,
  checker executable, execution closure, and verification report; and
* the generic receipt signs the exact run-statement hash and exact claim.

The projection defined below is an unsigned human-audit aid.  It never creates
a receipt, never claims Lean acceptance, and never substitutes for signature
verification or admission to the source-pinned Lean registry.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


SCHEMA_VERSION = 1
PROJECTION_KIND = "sparkinterval.sqrt218-fixed-v2-receipt-projection.v1"
REVIEWED_PINS_KIND = "sparkinterval.sqrt218-fixed-v2-reviewed-pins.v1"
BINARY_PROTOCOL = "sparkinterval.sqrt218-fixed-certificate.v2"
NATIVE_RESULT_PROTOCOL = "sparkinterval.sqrt218-fixed-result.v1"
RESULT_ENVELOPE_PROTOCOL = "sparkinterval.sqrt218-fixed-v2-result.v1"
RESULT_ENVELOPE_PREFIX = RESULT_ENVELOPE_PROTOCOL + ":"
ALGORITHM_ID = "sparkinterval.ternary-goldbach.sqrt218-fixed-v2.v1"
TRACE_KIND = "sparkinterval_challenge_work_trace"
WORK_TRACE_DOMAIN = (
    b"sparkinterval.measured-work-trace.sqrt218-fixed-v2.binding.v1\x00"
)
SOURCE_CUTOFF = 2_000_000
CERTIFICATE_HEADER_BYTES = 160
NATIVE_RESULT_BYTES = 120
MAX_TRACE_BYTES = 64 * 1024
MAX_PROJECTION_BYTES = 64 * 1024
MAX_REVIEWED_PINS_BYTES = 16 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RESULT_HEX_RE = re.compile(r"^[0-9a-f]{240}$")
NOT_APPLICABLE_DIGEST = hashlib.sha256(
    b"sparkinterval.trusted-compute.not-applicable.v1"
).hexdigest()

REVIEWED_PIN_KEYS = {
    "algorithm_hash",
    "algorithm_id",
    "certificate_sha256",
    "certificate_size_bytes",
    "checker_executable_sha256",
    "device_cubin_sha256",
    "domain_hash",
    "execution_closure_sha256",
    "kind",
    "parameters_hash",
    "receipt_sha256",
    "schema_version",
    "source_tree_hash",
    "target_profile_hash",
    "trust_profile_hash",
    "verifier_artifact_sha256",
    "verifier_key_id",
    "verifier_policy_sha256",
    "wire_statement_sha256",
}

PROJECTION_KEYS = {
    "binary_protocol",
    "bound",
    "certificate_sha256",
    "certificate_size_bytes",
    "checker_executable_sha256",
    "checker_executable_size_bytes",
    "execution_closure_sha256",
    "execution_closure_size_bytes",
    "job_binding_sha256",
    "kind",
    "native_result_protocol",
    "native_result_sha256",
    "native_result_size_bytes",
    "result_envelope_protocol",
    "result_envelope_sha256",
    "result_envelope_size_bytes",
    "schema_version",
    "start_challenge_sha256",
    "verification_report_sha256",
    "verification_report_size_bytes",
    "wire_statement_sha256",
    "work_trace_artifact_sha256",
    "work_trace_artifact_size_bytes",
    "work_trace_chain_sha256",
}

TRACE_KEYS = {
    "algorithm_id",
    "challenge_nonce",
    "input_sha256",
    "iteration_count",
    "job_binding_sha256",
    "kind",
    "result_sha256",
    "schema_version",
    "trace_sha256",
}

DIGEST_FIELDS = {
    "certificate_sha256",
    "checker_executable_sha256",
    "execution_closure_sha256",
    "job_binding_sha256",
    "native_result_sha256",
    "result_envelope_sha256",
    "start_challenge_sha256",
    "verification_report_sha256",
    "wire_statement_sha256",
    "work_trace_artifact_sha256",
    "work_trace_chain_sha256",
}

SIZE_FIELDS = {
    "certificate_size_bytes",
    "checker_executable_size_bytes",
    "execution_closure_size_bytes",
    "native_result_size_bytes",
    "result_envelope_size_bytes",
    "verification_report_size_bytes",
    "work_trace_artifact_size_bytes",
}


class FixedV2ReceiptError(ValueError):
    """A fixed-width V2 artifact or signed-field projection is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_object(
    value: Any, expected: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise FixedV2ReceiptError(
            f"{label} has wrong fields "
            f"(missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)})"
        )
    return dict(value)


def _required_digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        raise FixedV2ReceiptError(
            f"{label} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _positive_size(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FixedV2ReceiptError(f"{label} must be a positive integer")
    return value


def _u16be(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 2], "big")


def _u32be(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 4], "big")


def _u64be(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 8], "big")


def parse_native_result(
    raw: bytes,
    *,
    expected_input_size: int | None = None,
    expected_input_sha256: str | None = None,
    require_accepted: bool = True,
) -> dict[str, Any]:
    """Parse one exact native record without executing the checker."""

    if len(raw) != NATIVE_RESULT_BYTES:
        raise FixedV2ReceiptError(
            f"native result must be exactly {NATIVE_RESULT_BYTES} bytes"
        )
    if (
        raw[:8] != b"SQ218R2\x00"
        or _u16be(raw, 8) != 1
        or _u16be(raw, 10) != NATIVE_RESULT_BYTES
    ):
        raise FixedV2ReceiptError(
            "native result has the wrong magic, version, or width"
        )
    status = _u32be(raw, 12)
    if status not in range(6):
        raise FixedV2ReceiptError("native result has an unknown checker status")
    if require_accepted and status != 0:
        raise FixedV2ReceiptError("native result does not record checker acceptance")
    if status != 0 and raw[24:88] != b"\x00" * 64:
        raise FixedV2ReceiptError(
            "rejection result must zero every state and slack field"
        )
    input_size = _u64be(raw, 16)
    input_sha256 = raw[88:120].hex()
    if expected_input_size is not None and input_size != expected_input_size:
        raise FixedV2ReceiptError(
            "native result input length differs from the certificate"
        )
    if expected_input_sha256 is not None:
        _required_digest(expected_input_sha256, "expected input digest")
        if input_sha256 != expected_input_sha256:
            raise FixedV2ReceiptError(
                "native result immutable-input digest differs from the certificate"
            )
    return {
        "anchor_slack_high": _u64be(raw, 72),
        "anchor_slack_low": _u64be(raw, 80),
        "input_sha256": input_sha256,
        "input_size_bytes": input_size,
        "last_event_value": _u64be(raw, 32),
        "next_event_index": _u64be(raw, 24),
        "psi_lower_high": _u64be(raw, 56),
        "psi_lower_low": _u64be(raw, 64),
        "status": status,
        "weighted_upper_high": _u64be(raw, 40),
        "weighted_upper_low": _u64be(raw, 48),
    }


def encode_result_envelope(raw: bytes) -> str:
    """Return the only theorem-authorizing UTF-8 spelling of a result record."""

    parse_native_result(raw)
    return RESULT_ENVELOPE_PREFIX + raw.hex()


def decode_result_envelope(
    text: str,
    *,
    expected_input_size: int | None = None,
    expected_input_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Decode the exact prefix and lowercase hex of all 120 native bytes."""

    if not isinstance(text, str) or not text.startswith(RESULT_ENVELOPE_PREFIX):
        raise FixedV2ReceiptError(
            "claim result is not a fixed-V2 native-result envelope"
        )
    payload = text[len(RESULT_ENVELOPE_PREFIX) :]
    if RESULT_HEX_RE.fullmatch(payload) is None:
        raise FixedV2ReceiptError(
            "result envelope must contain exactly 240 lowercase hex digits"
        )
    raw = bytes.fromhex(payload)
    parsed = parse_native_result(
        raw,
        expected_input_size=expected_input_size,
        expected_input_sha256=expected_input_sha256,
    )
    if encode_result_envelope(raw) != text:
        raise FixedV2ReceiptError("result envelope is not canonical")
    return raw, parsed


def validate_reviewed_pins(value: Any) -> dict[str, Any]:
    """Validate compact source-reviewed identities; never touch an artifact."""

    pins = _exact_object(value, REVIEWED_PIN_KEYS, "fixed-V2 reviewed pins")
    if (
        pins["schema_version"] != SCHEMA_VERSION
        or pins["kind"] != REVIEWED_PINS_KIND
        or pins["algorithm_id"] != ALGORITHM_ID
    ):
        raise FixedV2ReceiptError(
            "fixed-V2 reviewed pins have the wrong protocol or algorithm"
        )
    for name in (
        "algorithm_hash",
        "certificate_sha256",
        "checker_executable_sha256",
        "device_cubin_sha256",
        "domain_hash",
        "execution_closure_sha256",
        "parameters_hash",
        "receipt_sha256",
        "source_tree_hash",
        "target_profile_hash",
        "trust_profile_hash",
        "verifier_artifact_sha256",
        "verifier_policy_sha256",
        "wire_statement_sha256",
    ):
        _required_digest(pins[name], name)
    if pins["device_cubin_sha256"] != NOT_APPLICABLE_DIGEST:
        raise FixedV2ReceiptError(
            "fixed-V2 CPU pins must use the not-applicable device digest"
        )
    if not isinstance(pins["verifier_key_id"], str) or not pins[
        "verifier_key_id"
    ]:
        raise FixedV2ReceiptError("verifier_key_id must be a nonempty string")
    certificate_size = _positive_size(
        pins["certificate_size_bytes"], "certificate_size_bytes"
    )
    if certificate_size < CERTIFICATE_HEADER_BYTES:
        raise FixedV2ReceiptError(
            "certificate_size_bytes is smaller than the fixed-V2 header"
        )
    return pins


def validate_receipt_only_binding(
    receipt: Mapping[str, Any],
    reviewed_pins: Mapping[str, Any],
) -> dict[str, Any]:
    """Fast fixed-V2 audit over compact signed fields and reviewed pins only.

    The caller must first validate the generic receipt and its signature.
    This function performs no path resolution, file open, artifact hashing,
    certificate decoding, checker execution, or production replay.
    """

    pins = validate_reviewed_pins(reviewed_pins)
    if receipt.get("backend") != "azure_sevsnp_cpu":
        raise FixedV2ReceiptError(
            "fixed-V2 receipt-only validation requires the Azure CPU backend"
        )
    claim = receipt.get("claim")
    bindings = receipt.get("bindings")
    if not isinstance(claim, Mapping) or not isinstance(bindings, Mapping):
        raise FixedV2ReceiptError(
            "trusted-compute receipt claim or bindings are missing"
        )
    artifacts = claim.get("artifacts")
    verifier = receipt.get("verifier")
    if not isinstance(artifacts, Mapping) or not isinstance(verifier, Mapping):
        raise FixedV2ReceiptError("receipt claim artifacts are missing")
    result = claim.get("result")
    if not isinstance(result, str):
        raise FixedV2ReceiptError("receipt claim result is not text")
    native_raw, parsed = decode_result_envelope(
        result,
        expected_input_size=pins["certificate_size_bytes"],
        expected_input_sha256=pins["certificate_sha256"],
    )
    expected = (
        (
            receipt.get("receipt_sha256"),
            pins["receipt_sha256"],
            "receipt",
        ),
        (
            bindings.get("wire_statement_sha256"),
            pins["wire_statement_sha256"],
            "wire statement",
        ),
        (
            claim.get("nonce"),
            bindings.get("start_challenge_sha256"),
            "start challenge",
        ),
        (claim.get("algorithm_id"), ALGORITHM_ID, "algorithm ID"),
        (
            claim.get("algorithm_hash"),
            pins["algorithm_hash"],
            "algorithm definition",
        ),
        (
            claim.get("input_hash"),
            pins["certificate_sha256"],
            "certificate input",
        ),
        (
            claim.get("parameters_hash"),
            pins["parameters_hash"],
            "parameters",
        ),
        (
            claim.get("domain_hash"),
            pins["domain_hash"],
            "domain",
        ),
        (
            claim.get("output_hash"),
            sha256_bytes(result.encode("utf-8")),
            "result/output hash",
        ),
        (
            artifacts.get("host_executable_hash"),
            pins["checker_executable_sha256"],
            "checker executable",
        ),
        (
            artifacts.get("kernel_manifest_hash"),
            pins["execution_closure_sha256"],
            "execution closure",
        ),
        (
            artifacts.get("device_cubin_hash"),
            pins["device_cubin_sha256"],
            "CPU device marker",
        ),
        (
            artifacts.get("source_tree_hash"),
            pins["source_tree_hash"],
            "source tree",
        ),
        (
            claim.get("target_profile_hash"),
            pins["target_profile_hash"],
            "target profile",
        ),
        (
            claim.get("trust_profile_hash"),
            pins["trust_profile_hash"],
            "trust profile",
        ),
        (
            verifier.get("policy_sha256"),
            pins["verifier_policy_sha256"],
            "verifier policy",
        ),
        (
            verifier.get("artifact_sha256"),
            pins["verifier_artifact_sha256"],
            "verifier artifact",
        ),
        (
            verifier.get("key_id"),
            pins["verifier_key_id"],
            "verifier key ID",
        ),
        (claim.get("target"), "azure_sevsnp_cpu", "CPU target"),
        (
            claim.get("trust"),
            "azure_sevsnp_confidential_compute",
            "CPU trust profile",
        ),
        (claim.get("completion"), "successful", "completion"),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise FixedV2ReceiptError(
                f"receipt-only {label} differs from the reviewed fixed-V2 pin"
            )
    return {
        "accepted_for_lean": False,
        "certificate_artifact_opened": False,
        "native_result_sha256": sha256_bytes(native_raw),
        "production_replay_performed": False,
        "receipt_only_binding_valid": True,
        "result_input_sha256": parsed["input_sha256"],
        "result_input_size_bytes": parsed["input_size_bytes"],
        "wire_statement_sha256": pins["wire_statement_sha256"],
    }


def _validate_certificate_header(raw: bytes, size: int) -> None:
    """Check only the constant-time production header, never its record body."""

    if len(raw) != CERTIFICATE_HEADER_BYTES:
        raise FixedV2ReceiptError("fixed-V2 certificate header is truncated")
    if (
        raw[:8] != b"SQ218V2\x00"
        or _u16be(raw, 8) != 2
        or _u16be(raw, 10) != CERTIFICATE_HEADER_BYTES
        or _u32be(raw, 12) != 0
        or _u64be(raw, 16) != SOURCE_CUTOFF
        or _u64be(raw, 24) != 1_517_397
        or _u64be(raw, 32) != 30
        or _u64be(raw, 40) != 281_474_976_710_656
        or _u64be(raw, 48) != 1_073_741_824
        or _u64be(raw, 136) != size
        or raw[144:160] != b"\x00" * 16
    ):
        raise FixedV2ReceiptError(
            "fixed-V2 certificate does not have the exact production header"
        )


def _file_pin(
    path: Path,
    label: str,
    *,
    executable: bool = False,
    capture_all: bool = False,
    capture_prefix: int = 0,
    maximum: int | None = None,
) -> tuple[str, int, bytes]:
    """Hash one stable, single-linked regular file through a non-following FD."""

    if path.is_symlink():
        raise FixedV2ReceiptError(f"{label} must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FixedV2ReceiptError(f"cannot open {label}: {exc}") from exc
    digest = hashlib.sha256()
    size = 0
    captured = bytearray()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise FixedV2ReceiptError(
                f"{label} must be a single-linked regular file"
            )
        if executable and before.st_mode & 0o111 == 0:
            raise FixedV2ReceiptError(f"{label} must be executable")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
            if maximum is not None and size > maximum:
                raise FixedV2ReceiptError(f"{label} exceeds {maximum} bytes")
            if capture_all:
                captured.extend(block)
            elif len(captured) < capture_prefix:
                captured.extend(block[: capture_prefix - len(captured)])
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise FixedV2ReceiptError(f"{label} changed while it was hashed")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), size, bytes(captured)


def _trace_chain_payload(projection: Mapping[str, Any]) -> bytes:
    fields = (
        ("challenge_nonce", projection["start_challenge_sha256"]),
        ("job_binding_sha256", projection["job_binding_sha256"]),
        ("certificate_sha256", projection["certificate_sha256"]),
        ("certificate_size_bytes", str(projection["certificate_size_bytes"])),
        ("native_result_sha256", projection["native_result_sha256"]),
        ("native_result_size_bytes", str(projection["native_result_size_bytes"])),
        ("result_envelope_sha256", projection["result_envelope_sha256"]),
        (
            "result_envelope_size_bytes",
            str(projection["result_envelope_size_bytes"]),
        ),
        (
            "checker_executable_sha256",
            projection["checker_executable_sha256"],
        ),
        (
            "checker_executable_size_bytes",
            str(projection["checker_executable_size_bytes"]),
        ),
        ("execution_closure_sha256", projection["execution_closure_sha256"]),
        (
            "execution_closure_size_bytes",
            str(projection["execution_closure_size_bytes"]),
        ),
        (
            "verification_report_sha256",
            projection["verification_report_sha256"],
        ),
        (
            "verification_report_size_bytes",
            str(projection["verification_report_size_bytes"]),
        ),
    )
    return WORK_TRACE_DOMAIN + "".join(
        f"{name}={value}\n" for name, value in fields
    ).encode("ascii")


def expected_work_trace_chain_sha256(
    projection: Mapping[str, Any],
) -> str:
    return sha256_bytes(_trace_chain_payload(projection))


def canonical_work_trace(projection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "challenge_nonce": projection["start_challenge_sha256"],
        "input_sha256": projection["certificate_sha256"],
        "iteration_count": SOURCE_CUTOFF,
        "job_binding_sha256": projection["job_binding_sha256"],
        "kind": TRACE_KIND,
        "result_sha256": projection["result_envelope_sha256"],
        "schema_version": SCHEMA_VERSION,
        "trace_sha256": projection["work_trace_chain_sha256"],
    }


def canonical_work_trace_bytes(projection: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(canonical_work_trace(projection))


def validate_projection(value: Any) -> dict[str, Any]:
    projection = _exact_object(
        value, PROJECTION_KEYS, "fixed-V2 receipt projection"
    )
    if (
        projection["schema_version"] != SCHEMA_VERSION
        or projection["kind"] != PROJECTION_KIND
        or projection["binary_protocol"] != BINARY_PROTOCOL
        or projection["native_result_protocol"] != NATIVE_RESULT_PROTOCOL
        or projection["result_envelope_protocol"] != RESULT_ENVELOPE_PROTOCOL
        or projection["bound"] != SOURCE_CUTOFF
    ):
        raise FixedV2ReceiptError(
            "fixed-V2 projection has the wrong protocol, version, or bound"
        )
    for name in DIGEST_FIELDS:
        _required_digest(projection[name], name)
    for name in SIZE_FIELDS:
        _positive_size(projection[name], name)
    if projection["native_result_size_bytes"] != NATIVE_RESULT_BYTES:
        raise FixedV2ReceiptError("native result projection has the wrong width")
    if (
        projection["result_envelope_size_bytes"]
        != len(RESULT_ENVELOPE_PREFIX) + 2 * NATIVE_RESULT_BYTES
    ):
        raise FixedV2ReceiptError("result envelope projection has the wrong width")
    expected_chain = expected_work_trace_chain_sha256(projection)
    if projection["work_trace_chain_sha256"] != expected_chain:
        raise FixedV2ReceiptError("work-trace chain digest is invalid")
    trace_raw = canonical_work_trace_bytes(projection)
    if (
        projection["work_trace_artifact_sha256"] != sha256_bytes(trace_raw)
        or projection["work_trace_artifact_size_bytes"] != len(trace_raw)
    ):
        raise FixedV2ReceiptError(
            "work-trace artifact pin is not the canonical standard trace"
        )
    return projection


def build_projection(
    *,
    certificate: Path,
    native_result: Path,
    checker_executable: Path,
    execution_closure: Path,
    start_challenge_sha256: str,
    job_binding_sha256: str,
    verification_report: Path,
    wire_statement_sha256: str,
) -> tuple[dict[str, Any], bytes, bytes]:
    """Build an unsigned audit projection using only bounded reads and hashes.

    The return values are the projection, exact UTF-8 result envelope bytes,
    and exact canonical work-trace bytes.  No file is written and the
    production checker is never executed.
    """

    certificate_digest, certificate_size, certificate_header = _file_pin(
        certificate,
        "fixed-V2 certificate",
        capture_prefix=CERTIFICATE_HEADER_BYTES,
    )
    _validate_certificate_header(certificate_header, certificate_size)
    native_digest, native_size, native_raw = _file_pin(
        native_result,
        "fixed-V2 native result",
        capture_all=True,
        maximum=NATIVE_RESULT_BYTES,
    )
    parse_native_result(
        native_raw,
        expected_input_size=certificate_size,
        expected_input_sha256=certificate_digest,
    )
    envelope_raw = encode_result_envelope(native_raw).encode("ascii")
    checker_digest, checker_size, _ = _file_pin(
        checker_executable,
        "fixed-V2 checker executable",
        executable=True,
    )
    closure_digest, closure_size, _ = _file_pin(
        execution_closure,
        "fixed-V2 execution closure",
    )
    report_digest, report_size, _ = _file_pin(
        verification_report,
        "fixed-V2 verification report",
    )
    projection: dict[str, Any] = {
        "binary_protocol": BINARY_PROTOCOL,
        "bound": SOURCE_CUTOFF,
        "certificate_sha256": certificate_digest,
        "certificate_size_bytes": certificate_size,
        "checker_executable_sha256": checker_digest,
        "checker_executable_size_bytes": checker_size,
        "execution_closure_sha256": closure_digest,
        "execution_closure_size_bytes": closure_size,
        "job_binding_sha256": _required_digest(
            job_binding_sha256, "job binding"
        ),
        "kind": PROJECTION_KIND,
        "native_result_protocol": NATIVE_RESULT_PROTOCOL,
        "native_result_sha256": native_digest,
        "native_result_size_bytes": native_size,
        "result_envelope_protocol": RESULT_ENVELOPE_PROTOCOL,
        "result_envelope_sha256": sha256_bytes(envelope_raw),
        "result_envelope_size_bytes": len(envelope_raw),
        "schema_version": SCHEMA_VERSION,
        "start_challenge_sha256": _required_digest(
            start_challenge_sha256, "start challenge"
        ),
        "verification_report_sha256": report_digest,
        "verification_report_size_bytes": report_size,
        "wire_statement_sha256": _required_digest(
            wire_statement_sha256, "wire statement"
        ),
    }
    projection["work_trace_chain_sha256"] = (
        expected_work_trace_chain_sha256(projection)
    )
    trace_raw = canonical_work_trace_bytes(projection)
    projection["work_trace_artifact_sha256"] = sha256_bytes(trace_raw)
    projection["work_trace_artifact_size_bytes"] = len(trace_raw)
    return validate_projection(projection), envelope_raw, trace_raw


def _parse_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixedV2ReceiptError(f"{label} is not UTF-8") from exc

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise FixedV2ReceiptError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                FixedV2ReceiptError(
                    f"{label} contains noncanonical JSON constant {token}"
                )
            ),
        )
    except FixedV2ReceiptError:
        raise
    except json.JSONDecodeError as exc:
        raise FixedV2ReceiptError(f"{label} is not valid JSON") from exc


def load_canonical_projection(path: Path) -> dict[str, Any]:
    digest, _size, raw = _file_pin(
        path,
        "fixed-V2 receipt projection",
        capture_all=True,
        maximum=MAX_PROJECTION_BYTES,
    )
    del digest
    projection = validate_projection(
        _parse_json(raw, "fixed-V2 receipt projection")
    )
    if canonical_json_bytes(projection) != raw:
        raise FixedV2ReceiptError(
            "fixed-V2 receipt projection is not exact compact sorted-key JSON"
        )
    return projection


def load_canonical_reviewed_pins(path: Path) -> dict[str, Any]:
    """Read only the small reviewed-pin control record, with a hard bound."""

    _digest, _size, raw = _file_pin(
        path,
        "fixed-V2 reviewed pins",
        capture_all=True,
        maximum=MAX_REVIEWED_PINS_BYTES,
    )
    pins = validate_reviewed_pins(
        _parse_json(raw, "fixed-V2 reviewed pins")
    )
    if canonical_json_bytes(pins) != raw:
        raise FixedV2ReceiptError(
            "fixed-V2 reviewed pins are not exact compact sorted-key JSON"
        )
    return pins


def verify_exact_artifacts(
    projection: Mapping[str, Any],
    *,
    certificate: Path,
    native_result: Path,
    result_envelope: Path,
    checker_executable: Path,
    execution_closure: Path,
    verification_report: Path,
    work_trace: Path,
) -> dict[str, Any]:
    """Check exact retained artifacts, never replaying the certificate."""

    projection = validate_projection(projection)
    certificate_digest, certificate_size, certificate_header = _file_pin(
        certificate,
        "fixed-V2 certificate",
        capture_prefix=CERTIFICATE_HEADER_BYTES,
    )
    _validate_certificate_header(certificate_header, certificate_size)
    native_digest, native_size, native_raw = _file_pin(
        native_result,
        "fixed-V2 native result",
        capture_all=True,
        maximum=NATIVE_RESULT_BYTES,
    )
    result_digest, result_size, result_raw = _file_pin(
        result_envelope,
        "fixed-V2 result envelope",
        capture_all=True,
        maximum=len(RESULT_ENVELOPE_PREFIX) + 2 * NATIVE_RESULT_BYTES,
    )
    try:
        result_text = result_raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise FixedV2ReceiptError("result envelope is not ASCII") from exc
    envelope_native, _ = decode_result_envelope(
        result_text,
        expected_input_size=certificate_size,
        expected_input_sha256=certificate_digest,
    )
    if envelope_native != native_raw:
        raise FixedV2ReceiptError(
            "result envelope does not contain the retained native result"
        )
    checker_digest, checker_size, _ = _file_pin(
        checker_executable,
        "fixed-V2 checker executable",
        executable=True,
    )
    closure_digest, closure_size, _ = _file_pin(
        execution_closure,
        "fixed-V2 execution closure",
    )
    report_digest, report_size, _ = _file_pin(
        verification_report,
        "fixed-V2 verification report",
    )
    trace_digest, trace_size, trace_raw = _file_pin(
        work_trace,
        "fixed-V2 work trace",
        capture_all=True,
        maximum=MAX_TRACE_BYTES,
    )
    pins = {
        "certificate": (certificate_digest, certificate_size),
        "checker_executable": (checker_digest, checker_size),
        "execution_closure": (closure_digest, closure_size),
        "native_result": (native_digest, native_size),
        "result_envelope": (result_digest, result_size),
        "verification_report": (report_digest, report_size),
        "work_trace_artifact": (trace_digest, trace_size),
    }
    for stem, (digest, size) in pins.items():
        if digest != projection[f"{stem}_sha256"]:
            raise FixedV2ReceiptError(
                f"{stem} SHA-256 differs from the projection"
            )
        if size != projection[f"{stem}_size_bytes"]:
            raise FixedV2ReceiptError(
                f"{stem} size differs from the projection"
            )
    if trace_raw != canonical_work_trace_bytes(projection):
        raise FixedV2ReceiptError(
            "work trace is not the exact canonical standard trace"
        )
    return {
        "artifact_bytes_verified": True,
        "production_replay_performed": False,
        "projection_kind": PROJECTION_KIND,
        "projection_sha256": sha256_bytes(canonical_json_bytes(projection)),
        "wire_statement_sha256": projection["wire_statement_sha256"],
    }


def validate_claim_projection(
    projection: Mapping[str, Any], claim: Mapping[str, Any]
) -> dict[str, Any]:
    """Check the generic signed claim's direct fixed-V2 field projection."""

    projection = validate_projection(projection)
    artifacts = claim.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise FixedV2ReceiptError("receipt claim artifacts are missing")
    result = claim.get("result")
    if not isinstance(result, str):
        raise FixedV2ReceiptError("receipt claim result is not text")
    native_raw, _ = decode_result_envelope(
        result,
        expected_input_size=projection["certificate_size_bytes"],
        expected_input_sha256=projection["certificate_sha256"],
    )
    expected = (
        (claim.get("algorithm_id"), ALGORITHM_ID, "algorithm_id"),
        (
            claim.get("input_hash"),
            projection["certificate_sha256"],
            "input_hash/certificate",
        ),
        (
            sha256_bytes(native_raw),
            projection["native_result_sha256"],
            "result envelope/native record",
        ),
        (
            claim.get("output_hash"),
            projection["result_envelope_sha256"],
            "output_hash/result envelope",
        ),
        (
            claim.get("nonce"),
            projection["start_challenge_sha256"],
            "nonce/start challenge",
        ),
        (
            artifacts.get("host_executable_hash"),
            projection["checker_executable_sha256"],
            "host executable",
        ),
        (
            artifacts.get("kernel_manifest_hash"),
            projection["execution_closure_sha256"],
            "execution manifest/closure",
        ),
        (claim.get("target"), "azure_sevsnp_cpu", "CPU target"),
        (
            claim.get("trust"),
            "azure_sevsnp_confidential_compute",
            "CPU trust profile",
        ),
        (claim.get("completion"), "successful", "completion"),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise FixedV2ReceiptError(
                f"receipt claim {label} does not bind fixed-V2 fields"
            )
    if result.encode("utf-8") != (
        RESULT_ENVELOPE_PREFIX.encode("ascii") + native_raw.hex().encode("ascii")
    ):
        raise FixedV2ReceiptError(
            "receipt claim result is not the exact native-result envelope"
        )
    return projection


def _single_role_hash(statement: Mapping[str, Any], role: str) -> str:
    records = statement.get("build_artifacts")
    if not isinstance(records, list):
        raise FixedV2ReceiptError("wire statement build artifacts are missing")
    matches = [
        record.get("sha256")
        for record in records
        if isinstance(record, Mapping) and record.get("role") == role
    ]
    if len(matches) != 1:
        raise FixedV2ReceiptError(
            f"wire statement requires exactly one {role!r} artifact"
        )
    return _required_digest(matches[0], f"wire statement {role}")


def validate_wire_statement_projection(
    projection: Mapping[str, Any], statement: Mapping[str, Any]
) -> dict[str, Any]:
    """Reconstruct the projection from the exact signed statement preimage."""

    projection = validate_projection(projection)
    if sha256_bytes(canonical_json_bytes(statement)) != projection[
        "wire_statement_sha256"
    ]:
        raise FixedV2ReceiptError(
            "wire statement bytes differ from the signed statement hash"
        )
    algorithm = statement.get("algorithm")
    input_record = statement.get("input_artifact")
    output_record = statement.get("output_artifact")
    environment = statement.get("execution_environment")
    if not all(
        isinstance(value, Mapping)
        for value in (algorithm, input_record, output_record, environment)
    ):
        raise FixedV2ReceiptError(
            "wire statement lacks fixed-V2 projection fields"
        )
    environment_value = environment.get("value")
    if not isinstance(environment_value, Mapping):
        raise FixedV2ReceiptError(
            "wire statement execution environment is missing"
        )
    if environment.get("canonical_sha256") != sha256_bytes(
        canonical_json_bytes(environment_value)
    ):
        raise FixedV2ReceiptError(
            "wire statement execution environment hash is invalid"
        )
    expected = (
        (algorithm.get("algorithm_id"), ALGORITHM_ID, "algorithm ID"),
        (
            input_record.get("sha256"),
            projection["certificate_sha256"],
            "certificate digest",
        ),
        (
            input_record.get("size_bytes"),
            projection["certificate_size_bytes"],
            "certificate size",
        ),
        (
            output_record.get("sha256"),
            projection["result_envelope_sha256"],
            "result envelope digest",
        ),
        (
            output_record.get("size_bytes"),
            projection["result_envelope_size_bytes"],
            "result envelope size",
        ),
        (
            statement.get("nonce"),
            projection["start_challenge_sha256"],
            "start challenge",
        ),
        (
            _single_role_hash(statement, "host_executable"),
            projection["checker_executable_sha256"],
            "checker executable",
        ),
        (
            _single_role_hash(statement, "execution_manifest"),
            projection["execution_closure_sha256"],
            "execution closure",
        ),
        (
            environment_value.get("artifact_closure_manifest_sha256"),
            projection["execution_closure_sha256"],
            "environment closure",
        ),
        (
            environment_value.get("job_binding_sha256"),
            projection["job_binding_sha256"],
            "job binding",
        ),
        (
            environment_value.get("work_trace_artifact_sha256"),
            projection["work_trace_artifact_sha256"],
            "work-trace artifact",
        ),
        (
            environment_value.get("work_trace_chain_sha256"),
            projection["work_trace_chain_sha256"],
            "work-trace chain",
        ),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise FixedV2ReceiptError(
                f"wire statement {label} differs from the projection"
            )
    return projection


def validate_receipt_projection(
    projection: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    statement: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit an already signature-verified generic receipt.

    Callers must run the generic receipt signature verifier first.  This
    function intentionally does not duplicate cryptographic verification.
    """

    projection = validate_projection(projection)
    if receipt.get("backend") != "azure_sevsnp_cpu":
        raise FixedV2ReceiptError(
            "fixed-V2 projection requires the Azure confidential CPU backend"
        )
    bindings = receipt.get("bindings")
    claim = receipt.get("claim")
    if not isinstance(bindings, Mapping) or not isinstance(claim, Mapping):
        raise FixedV2ReceiptError(
            "trusted-compute receipt claim or bindings are missing"
        )
    if bindings.get("wire_statement_sha256") != projection[
        "wire_statement_sha256"
    ]:
        raise FixedV2ReceiptError(
            "receipt does not sign the projected wire statement"
        )
    validate_claim_projection(projection, claim)
    if statement is not None:
        validate_wire_statement_projection(projection, statement)
    return {
        "accepted_for_lean": False,
        "production_replay_performed": False,
        "projection_kind": PROJECTION_KIND,
        "projection_sha256": sha256_bytes(canonical_json_bytes(projection)),
        "signed_field_projection_valid": True,
        "wire_statement_preimage_checked": statement is not None,
    }
