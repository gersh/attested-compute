# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""An enclave-signed receipt for one CompCert artifact run.

## Why a receipt at all, when there is already a quote

A TDX quote binds `report_data` to the measurements, and we already put the
digest of the results there.  A signature adds one thing the quote cannot: a
statement that is *self-describing*.  The quote proves 32 bytes were bound; the
receipt says which run those 32 bytes are about, in named fields a reader and a
checker can both read, and it is those named fields that Lean verifies.

## Design choices, and the upstream facts behind them

**We sign with P-256, and dstack's own `/Sign` is deliberately not used.**
`sdk/curl/api.md` gives `/Sign` three algorithms — `ed25519`, `secp256k1`,
`secp256k1_prehashed`.  None is P-256, and the Lean side has a P-256 verifier
(`SparkInterval/Certificate/P256.lean`) and no other.  Adopting `/Sign` would
mean writing ed25519 or secp256k1 verification in Lean before a receipt could
be checked at all.  So the key comes from `/GetKey` and the signing happens
here.

**Interpreting `/GetKey` material as a P-256 scalar is documented behaviour,
not a trick.**  The API reference says of the `algorithm` field: *"this selects
how the same derived 32-byte material is interpreted; it does not
domain-separate the derivation."*  The same 32 bytes back every algorithm, so
reading them as a P-256 scalar is exactly as legitimate as reading them as an
ed25519 seed.

**...which is also why the path must be algorithm-specific.**  Because the
derivation is keyed only on `path`, a P-256 key and an ed25519 key drawn from
the same path are the *same secret* in two encodings.  The upstream docs warn
about this directly ("Use algorithm-specific paths ... when independent keys
are required across algorithms"), so this module fixes a dedicated
`KEY_PATH` and nothing else may share it.

**`signature_chain` is captured but not yet checked.**  `/GetKey` returns a
chain linking the derived key to the app's KMS-rooted identity.  Lean does not
verify it today; recording it costs nothing and is what a later, stronger check
would consume.  It is evidence, not yet a premise.

## What binds the signature to the enclave

A signature alone proves nothing — anyone can sign.  What makes it evidence is
that the quote's `report_data` commits to *this public key together with this
statement*, so the enclave hardware attests which key signed.  That is
`report_data_preimage` below, and the verifier recomputes it.
"""

from __future__ import annotations

import hashlib

from tg_verifier.phala_tdx_receipt import (
    P256_GROUP_ORDER,
    public_key_hex,
    sign_digest_hex,
    verify_digest_hex,
)

RECEIPT_KIND = "sparkinterval.compcert-run-receipt.v1"
PAYLOAD_DOMAIN = "sparkinterval.compcert-run-receipt.v1"
REPORT_DATA_DOMAIN = "sparkinterval.compcert-run-report-data.v1"

#: Dedicated derivation path.  Must not be shared with any other algorithm —
#: see the module docstring.
KEY_PATH = "sparkinterval/compcert-run/p256"
KEY_PURPOSE = "compcert-run-receipt"

#: Exact order of the signed fields.  Order is load-bearing: it is part of the
#: preimage.  Adding a field is a new receipt kind, never an edit to this list.
SIGNED_FIELDS: tuple[str, ...] = (
    "algorithm_id",
    "algorithm_hash",
    "input_hash",
    "result",
    "output_hash",
    "matched_pinned_expectation",
    "app_id",
    "compose_hash",
    "app_compose_sha256",
    "docker_compose_file_sha256",
    "tdx_quote_sha256",
    "report_data_sha256",
    "issued_at",
)


class CompCertRunReceiptError(ValueError):
    """A receipt field, key, or signature was malformed."""


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _committed_field(name: str, value: str) -> str:
    """One line, with the value SHA-256 committed.

    Committing rather than inlining is what stops a value containing a newline
    from being read as a following field.
    """
    return f"{name}={_sha256_hex(value)}\n"


def scalar_from_key_material(key_hex: str) -> int:
    """Interpret `/GetKey`'s 32 bytes as a P-256 private scalar.

    Rejects the two values that are not valid scalars.  The chance of hitting
    them is about 2^-32, but a silent zero key would be catastrophic rather
    than merely unlikely, so it is checked.
    """
    if len(key_hex) != 64:
        raise CompCertRunReceiptError(
            f"GetKey returned {len(key_hex)} hex chars, expected 64")
    scalar = int(key_hex, 16)
    if not 1 <= scalar < P256_GROUP_ORDER:
        raise CompCertRunReceiptError(
            "GetKey material is not a valid P-256 scalar")
    return scalar


def report_data_preimage(*, enclave_public_key_hex: str,
                         statement_sha256: str) -> str:
    """What the TDX quote's report data commits to.

    Both halves matter.  The public key makes the hardware attest *which key
    signed*; the statement digest makes it attest *what was claimed*.  Either
    alone would leave the other unbound.
    """
    return (REPORT_DATA_DOMAIN + "\n"
            + _committed_field("enclave_public_key", enclave_public_key_hex)
            + _committed_field("statement_sha256", statement_sha256))


def report_data_hash(*, enclave_public_key_hex: str,
                     statement_sha256: str) -> str:
    return _sha256_hex(report_data_preimage(
        enclave_public_key_hex=enclave_public_key_hex,
        statement_sha256=statement_sha256))


def canonical_signed_payload(fields: dict[str, str]) -> str:
    missing = [n for n in SIGNED_FIELDS if n not in fields]
    if missing:
        raise CompCertRunReceiptError(
            "receipt is missing signed fields: " + ", ".join(missing))
    extra = sorted(set(fields) - set(SIGNED_FIELDS))
    if extra:
        raise CompCertRunReceiptError(
            "receipt carries unsigned fields: " + ", ".join(extra))
    payload = PAYLOAD_DOMAIN + "\n"
    for name in SIGNED_FIELDS:
        value = fields[name]
        if not isinstance(value, str):
            raise CompCertRunReceiptError(f"field {name} is not a string")
        payload += _committed_field(name, value)
    return payload


def receipt_digest(fields: dict[str, str]) -> str:
    return _sha256_hex(canonical_signed_payload(fields))


def sign(private_key: int, fields: dict[str, str],
         signature_chain: list[str] | None = None) -> dict:
    """Sign one run's fields.  RFC 6979, so the signature is deterministic."""
    digest = receipt_digest(fields)
    return {
        "kind": RECEIPT_KIND,
        "schema_version": 1,
        "enclave_public_key": public_key_hex(private_key),
        "key_path": KEY_PATH,
        "receipt_sha256": digest,
        "signature": sign_digest_hex(private_key, digest),
        "signature_chain": list(signature_chain or []),
        "signed_fields": dict(fields),
    }


def verify(receipt: dict, *, expected_public_key: str | None = None) -> bool:
    """Recompute the digest and check the signature.

    `expected_public_key` is optional here on purpose: this function answers
    "is this receipt internally coherent and correctly signed by the key it
    names".  Whether that key is the *right* key is a separate question,
    answered by recomputing the quote's report data — which is strictly
    stronger than comparing against a key someone typed in.
    """
    if not isinstance(receipt, dict):
        return False
    fields = receipt.get("signed_fields")
    if not isinstance(fields, dict):
        return False
    public_key = receipt.get("enclave_public_key")
    if not isinstance(public_key, str):
        return False
    if expected_public_key is not None and public_key != expected_public_key:
        return False
    try:
        digest = receipt_digest(fields)
    except CompCertRunReceiptError:
        return False
    if receipt.get("receipt_sha256") != digest:
        return False
    signature = receipt.get("signature")
    if not isinstance(signature, str):
        return False
    return verify_digest_hex(public_key, digest, signature)
