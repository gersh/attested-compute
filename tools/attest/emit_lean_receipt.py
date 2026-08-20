#!/usr/bin/env python3
"""Emit the Lean `CompCertRunReceipt` literal for one attested run.

The receipt fields in a Lean module used to be transcribed by hand from
`retained-evidence/receipts.json`.  A transcription error there does not fail
loudly: `compcertRunReceiptCheck` simply returns `false` and the module stops
compiling, which costs an afternoon to localise -- or, worse, a *consistent*
error in the same field on both sides typechecks and pins nothing.

This reads the receipt the enclave actually signed and prints the literal.

    tools/attest/emit_lean_receipt.py <evidence-dir> <algorithm-id>
    tools/attest/emit_lean_receipt.py <evidence-dir> --list

The field order matches the structure declaration; the values are copied
verbatim, so what Lean checks is what the enclave signed.
"""
import json
import pathlib
import sys

# Lean field name -> key in the receipt's `signed_fields` (or, for the four
# marked None, the receipt's top level).
FIELDS = [
    ("algorithmId",             "algorithm_id"),
    ("algorithmHash",           "algorithm_hash"),
    ("inputHash",               "input_hash"),
    ("result",                  "result"),
    ("outputHash",              "output_hash"),
    ("matchedPinnedExpectation", "matched_pinned_expectation"),
    ("appId",                   "app_id"),
    ("composeHash",             "compose_hash"),
    ("appComposeSha256",        "app_compose_sha256"),
    ("dockerComposeFileSha256", "docker_compose_file_sha256"),
    ("tdxQuoteSha256",          "tdx_quote_sha256"),
    ("reportDataSha256",        "report_data_sha256"),
    ("issuedAt",                "issued_at"),
    ("enclavePublicKey",        None),
    ("receiptSha256",           None),
    ("signature",               None),
]
TOP_LEVEL = {"enclavePublicKey": "enclave_public_key",
             "receiptSha256": "receipt_sha256",
             "signature": "signature"}


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    evidence, wanted = pathlib.Path(argv[1]), argv[2]
    receipts = json.loads((evidence / "receipts.json").read_text())

    ids = [r["signed_fields"]["algorithm_id"] for r in receipts]
    if wanted == "--list":
        for i in ids:
            print(i)
        return 0

    matches = [r for r in receipts if r["signed_fields"]["algorithm_id"] == wanted]
    if len(matches) != 1:
        print(f"expected exactly one receipt for {wanted!r}, found {len(matches)}.\n"
              f"available: {', '.join(ids)}", file=sys.stderr)
        return 1
    receipt = matches[0]
    signed = receipt["signed_fields"]

    # The pin table keys on app id, so surface the identity the reviewer must
    # have already pinned -- a receipt whose app id is unpinned is refused by
    # `compcertRunReceiptCheck`, and it is better to say so here than to let
    # the kernel report a bare `false`.
    print(f"-- app id      {signed['app_id']}", file=sys.stderr)
    print(f"-- compose     {signed['compose_hash']}", file=sys.stderr)
    print(f"-- enclave key {receipt['enclave_public_key']}", file=sys.stderr)

    width = max(len(lean) for lean, _ in FIELDS)
    lines = []
    for lean, key in FIELDS:
        value = receipt[TOP_LEVEL[lean]] if key is None else signed[key]
        if not isinstance(value, str):
            raise SystemExit(f"{lean}: expected a string, got {type(value).__name__}")
        if '"' in value or "\\" in value or "\n" in value:
            raise SystemExit(f"{lean}: value is not a plain Lean string literal")
        lines.append(f"    {lean.ljust(width)} := \"{value}\"")
    print("{ " + ",\n".join(lines).lstrip() + " }")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
