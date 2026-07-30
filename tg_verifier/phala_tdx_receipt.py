# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Enclave-signed campaign receipt for the Phala/dstack Intel TDX path.

This module owns exactly three things:

* the canonical, domain-separated byte string an enclave signs;
* the report-data preimage that binds the enclave's derived P-256 public key
  to the campaign challenge inside the TDX quote; and
* a deterministic (RFC 6979) pure-Python P-256 signer/verifier, so a
  container run produces byte-identical output for identical inputs.

What this module deliberately does **not** do is verify a TDX quote.  Quote
parsing, the PCK certificate chain, TCB levels, and QE identity are appraised
outside by ``dcap-qvl``; only the SHA-256 identities of the retained quote,
the appraisal output, the appraisal policy, and the appraisal binary enter
the signed statement.  Lean verifies the P-256 signature and the bindings,
nothing more.

The canonical payload is mirrored bit for bit by
``SparkInterval/Execution/PhalaTdxAttestation.lean``; the two are kept in
step by ``tests/test_phala_tdx_first_run.py``.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any


PAYLOAD_DOMAIN = "sparkinterval.phala-tdx-attested-run.v1"
REPORT_DATA_DOMAIN = "sparkinterval.phala-tdx-report-data.v1"

# NIST P-256 (secp256r1).
P256_FIELD_PRIME = (
    0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
)
P256_GROUP_ORDER = (
    0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
)
P256_A = P256_FIELD_PRIME - 3
P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
P256_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
P256_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5

# Ordered exactly as the Lean canonical payload emits them.
SIGNED_FIELDS: tuple[str, ...] = (
    "algorithm_id",
    "algorithm_hash",
    "input_hash",
    "parameters_hash",
    "domain_hash",
    "result",
    "output_hash",
    "challenge_nonce",
    "job_binding_sha256",
    "app_id",
    "compose_hash",
    "image_digest",
    "tdx_quote_sha256",
    "dcap_qvl_output_sha256",
    "dcap_qvl_policy_sha256",
    "dcap_qvl_artifact_sha256",
    "report_data_sha256",
    "issued_at",
)


class PhalaTdxReceiptError(ValueError):
    """A receipt field, key, or signature was malformed."""


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _committed_field(name: str, value: str) -> str:
    return f"{name}={_sha256_hex(value)}\n"


def report_data_preimage(
    *, enclave_public_key_hex: str, challenge_nonce: str, job_binding: str
) -> str:
    """Bytes whose SHA-256 the enclave places in the TDX quote report data.

    This is the only thing that ties the quote (which proves *an* enclave with
    a given measurement ran) to the signing key (which proves *this* run's
    bytes).  Without it a valid quote and a valid signature could come from
    two unrelated parties.
    """

    return (
        REPORT_DATA_DOMAIN
        + "\n"
        + _committed_field("enclave_public_key", enclave_public_key_hex)
        + _committed_field("challenge_nonce", challenge_nonce)
        + _committed_field("job_binding_sha256", job_binding)
    )


def report_data_hash(
    *, enclave_public_key_hex: str, challenge_nonce: str, job_binding: str
) -> str:
    return _sha256_hex(
        report_data_preimage(
            enclave_public_key_hex=enclave_public_key_hex,
            challenge_nonce=challenge_nonce,
            job_binding=job_binding,
        )
    )


def canonical_signed_payload(fields: dict[str, str]) -> str:
    """Return the exact string the enclave signs.

    Every variable-length value is SHA-256 committed before it enters the
    line-oriented format, so no field value can be shifted into another
    field's position.
    """

    missing = [name for name in SIGNED_FIELDS if name not in fields]
    if missing:
        raise PhalaTdxReceiptError(
            "receipt is missing signed fields: " + ", ".join(missing)
        )
    extra = sorted(set(fields) - set(SIGNED_FIELDS))
    if extra:
        raise PhalaTdxReceiptError(
            "receipt carries unsigned fields: " + ", ".join(extra)
        )
    payload = PAYLOAD_DOMAIN + "\n"
    for name in SIGNED_FIELDS:
        value = fields[name]
        if not isinstance(value, str):
            raise PhalaTdxReceiptError(f"receipt field {name} is not a string")
        payload += _committed_field(name, value)
    return payload


def statement_digest(fields: dict[str, str]) -> str:
    """SHA-256 of the canonical signed payload, in lowercase hexadecimal."""

    return _sha256_hex(canonical_signed_payload(fields))


# ---------------------------------------------------------------------------
# Deterministic P-256 ECDSA (RFC 6979), pure Python.
#
# The enclave's key is derived by dstack, so signing happens in our own code
# inside the container.  RFC 6979 removes the last source of nondeterminism
# from the image's output, which is what makes the run reproducible.
# ---------------------------------------------------------------------------


def _point_add(
    left: tuple[int, int] | None, right: tuple[int, int] | None
) -> tuple[int, int] | None:
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and (y1 + y2) % P256_FIELD_PRIME == 0:
        return None
    if left == right:
        slope = (
            3 * x1 * x1 + P256_A
        ) * pow(2 * y1, P256_FIELD_PRIME - 2, P256_FIELD_PRIME)
    else:
        slope = (y2 - y1) * pow(x2 - x1, P256_FIELD_PRIME - 2, P256_FIELD_PRIME)
    slope %= P256_FIELD_PRIME
    x3 = (slope * slope - x1 - x2) % P256_FIELD_PRIME
    y3 = (slope * (x1 - x3) - y1) % P256_FIELD_PRIME
    return (x3, y3)


def _scalar_mul(scalar: int, point: tuple[int, int] | None) -> tuple[int, int] | None:
    result: tuple[int, int] | None = None
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def is_on_curve(x: int, y: int) -> bool:
    if not (0 <= x < P256_FIELD_PRIME and 0 <= y < P256_FIELD_PRIME):
        return False
    return (y * y - (x * x * x + P256_A * x + P256_B)) % P256_FIELD_PRIME == 0


def public_key_hex(private_key: int) -> str:
    """Uncompressed SEC1 encoding (``04`` || X || Y) as 130 hex digits."""

    if not 1 <= private_key < P256_GROUP_ORDER:
        raise PhalaTdxReceiptError("private key is out of range")
    point = _scalar_mul(private_key, (P256_GX, P256_GY))
    if point is None:
        raise PhalaTdxReceiptError("private key annihilates the base point")
    return "04" + f"{point[0]:064x}" + f"{point[1]:064x}"


def _rfc6979_nonce(private_key: int, digest: bytes) -> int:
    holen = 32
    rolen = 32
    bits = int.from_bytes(digest, "big")
    if bits >> (8 * holen - 256) > 0:
        bits >>= 8 * holen - 256
    h1 = (bits % P256_GROUP_ORDER).to_bytes(rolen, "big")
    key = private_key.to_bytes(rolen, "big")
    v = b"\x01" * holen
    k = b"\x00" * holen
    k = hmac.new(k, v + b"\x00" + key + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + key + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        candidate = int.from_bytes(v, "big")
        if 1 <= candidate < P256_GROUP_ORDER:
            return candidate
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign_digest_hex(private_key: int, digest_hex: str) -> str:
    """Deterministically sign a 32-byte digest; return ``r || s`` hex.

    ``s`` is normalized to the low half of the group, so the emitted encoding
    is unique for a given key and digest.
    """

    if len(digest_hex) != 64 or any(
        character not in "0123456789abcdef" for character in digest_hex
    ):
        raise PhalaTdxReceiptError("digest must be 64 lowercase hex digits")
    digest = bytes.fromhex(digest_hex)
    e = int.from_bytes(digest, "big") % P256_GROUP_ORDER
    while True:
        k = _rfc6979_nonce(private_key, digest)
        point = _scalar_mul(k, (P256_GX, P256_GY))
        if point is None:
            continue
        r = point[0] % P256_GROUP_ORDER
        if r == 0:
            continue
        s = (
            pow(k, P256_GROUP_ORDER - 2, P256_GROUP_ORDER)
            * (e + r * private_key)
        ) % P256_GROUP_ORDER
        if s == 0:
            continue
        if 2 * s > P256_GROUP_ORDER:
            s = P256_GROUP_ORDER - s
        return f"{r:064x}{s:064x}"


def verify_digest_hex(
    public_key_hex_value: str, digest_hex: str, signature_hex: str
) -> bool:
    """Reference verifier, mirroring ``SparkInterval.Certificate.P256``."""

    if len(public_key_hex_value) != 130 or not public_key_hex_value.startswith("04"):
        return False
    if len(signature_hex) != 128:
        return False
    try:
        x = int(public_key_hex_value[2:66], 16)
        y = int(public_key_hex_value[66:130], 16)
        r = int(signature_hex[:64], 16)
        s = int(signature_hex[64:], 16)
        e = int(digest_hex, 16)
    except ValueError:
        return False
    if not is_on_curve(x, y):
        return False
    if not (1 <= r < P256_GROUP_ORDER and 1 <= s < P256_GROUP_ORDER):
        return False
    e %= P256_GROUP_ORDER
    w = pow(s, P256_GROUP_ORDER - 2, P256_GROUP_ORDER)
    point = _point_add(
        _scalar_mul((e * w) % P256_GROUP_ORDER, (P256_GX, P256_GY)),
        _scalar_mul((r * w) % P256_GROUP_ORDER, (x, y)),
    )
    if point is None:
        return False
    return point[0] % P256_GROUP_ORDER == r


def sign_receipt(private_key: int, fields: dict[str, str]) -> dict[str, Any]:
    """Return the complete enclave-signed receipt for one campaign run."""

    digest = statement_digest(fields)
    return {
        "kind": "sparkinterval.phala-tdx-attested-run.v1",
        "schema_version": 1,
        "enclave_public_key": public_key_hex(private_key),
        "statement_sha256": digest,
        "signature": sign_digest_hex(private_key, digest),
        "signed_fields": dict(fields),
    }


def verify_receipt(receipt: dict[str, Any], *, enclave_public_key: str) -> bool:
    """Recompute the digest and check the signature against a pinned key."""

    if not isinstance(receipt, dict):
        return False
    fields = receipt.get("signed_fields")
    if not isinstance(fields, dict):
        return False
    if receipt.get("enclave_public_key") != enclave_public_key:
        return False
    try:
        digest = statement_digest(fields)
    except PhalaTdxReceiptError:
        return False
    if receipt.get("statement_sha256") != digest:
        return False
    signature = receipt.get("signature")
    if not isinstance(signature, str):
        return False
    return verify_digest_hex(enclave_public_key, digest, signature)
