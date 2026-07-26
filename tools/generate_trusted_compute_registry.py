#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate the closed Lean registry of admitted trusted-compute receipts.

Every input is parsed canonically, structurally validated, and verified under
the repository's source-pinned verifier key before any output is written.
Generation is atomic, duplicate receipt/run/challenge identities are rejected,
and an empty registry requires the explicit ``--allow-empty`` flag.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterable

from create_run_bundle import BundleError
from generate_trusted_compute_lean import (
    DEFAULT_KEY_MANIFEST,
    SQRT218_FIXED_V2_INVOCATION,
    lean_string,
    load_verified_receipt,
    validate_bound_registered_results,
    validate_source_admitted_registered_invocation,
)
from tg_verifier import sqrt218_fixed_v2_receipt
from trusted_compute_receipt import ReceiptError


HEX_CHUNK_LENGTH = 16


def _canonical_hex_name(value: str) -> str:
    identity = hashlib.sha256(value.encode("ascii")).hexdigest()
    return f"trustedComputeCanonicalHex_{len(value)}_{identity}"


def _canonical_hex_term(value: str) -> str:
    if len(value) not in {64, 768} or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ReceiptError("Lean registry hexadecimal literal is not canonical")
    chunks = [
        value[index : index + HEX_CHUNK_LENGTH]
        for index in range(0, len(value), HEX_CHUNK_LENGTH)
    ]
    leaves = [
        "({ value := "
        + lean_string(chunk)
        + ", canonical := by rfl } : "
        + "SparkInterval.Certificate.CanonicalLowerHex "
        + str(HEX_CHUNK_LENGTH)
        + ")"
        for chunk in chunks
    ]
    result = leaves[0]
    for leaf in leaves[1:]:
        result = (
            "SparkInterval.Certificate.CanonicalLowerHex.append\n    ("
            + result
            + ")\n    ("
            + leaf
            + ")"
        )
    return result


def _canonical_hex_value(value: str) -> str:
    return _canonical_hex_name(value) + ".value"


def _receipt_hex_values(receipt: dict) -> list[str]:
    claim = receipt["claim"]
    values = [
        receipt["receipt_sha256"],
        claim["algorithm_hash"],
        claim["input_hash"],
        claim["parameters_hash"],
        claim["domain_hash"],
        claim["output_hash"],
        claim["nonce"],
        claim["target_profile_hash"],
        claim["trust_profile_hash"],
        *claim["artifacts"].values(),
        *receipt["bindings"].values(),
        *receipt["evidence_hashes"].values(),
        receipt["verifier"]["policy_sha256"],
        receipt["verifier"]["artifact_sha256"],
        receipt["signature"]["value_hex"],
    ]
    return sorted(set(values), key=lambda value: (len(value), value))


def _canonical_hex_definitions(receipts: list[dict]) -> str:
    values = sorted(
        {value for receipt in receipts for value in _receipt_hex_values(receipt)},
        key=lambda value: (len(value), value),
    )
    return "\n\n".join(
        "/-- Compositional kernel certificate for this exact reviewed "
        + f"{len(value)}-character hexadecimal literal. -/\n"
        + "def "
        + _canonical_hex_name(value)
        + " : SparkInterval.Certificate.CanonicalLowerHex "
        + str(len(value))
        + " :=\n  "
        + _canonical_hex_term(value)
        + (
            "\n\n/-- Exact reconstruction of the reviewed digest literal. -/\n"
            + "theorem "
            + _canonical_hex_name(value)
            + "_value :\n  "
            + _canonical_hex_name(value)
            + ".value = "
            + lean_string(value)
            + " := by\n  rfl"
            if len(value) == 64
            else ""
        )
        for value in values
    )


def _canonical_utc_timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ReceiptError(f"{field} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ReceiptError(
            f"{field} must use canonical YYYY-MM-DDTHH:MM:SSZ syntax"
        ) from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def validate_registry_admission(
    receipt: dict,
    *,
    now: dt.datetime | None = None,
    sqrt218_fixed_v2_reviewed_pins: dict | None = None,
) -> str:
    """Apply time, backend, and source-key checks specific to admission.

    Expiry is checked only while generating the source registry.  Once a
    reviewed entry and theorem are checked in, their historical execution fact
    remains durable rather than depending on wall-clock reduction in Lean.
    """

    verifier = receipt["verifier"]
    issued = _canonical_utc_timestamp(verifier["issued_at"], "issued_at")
    expires = _canonical_utc_timestamp(verifier["expires_at"], "expires_at")
    if issued >= expires:
        raise ReceiptError("trusted-compute receipt must expire after issuance")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current < issued:
        raise ReceiptError("trusted-compute receipt is not valid yet")
    if current >= expires:
        raise ReceiptError("trusted-compute receipt expired before registry admission")
    expected_claim_class = {
        "azure_sevsnp_cpu": (
            "azure_sevsnp_cpu",
            "azure_sevsnp_confidential_compute",
        ),
        "azure_ncc40ads_h100_v5": (
            "nvidia_h100_sm90",
            "nvidia_h100_confidential_compute",
        ),
    }[receipt["backend"]]
    actual_claim_class = (receipt["claim"]["target"], receipt["claim"]["trust"])
    if actual_claim_class != expected_claim_class:
        raise ReceiptError(
            f"backend {receipt['backend']!r} cannot admit claim class "
            f"{actual_claim_class!r}"
        )
    validate_bound_registered_results(
        receipt,
        sqrt218_fixed_v2_reviewed_pins=sqrt218_fixed_v2_reviewed_pins,
    )
    return validate_source_admitted_registered_invocation(
        receipt,
        sqrt218_fixed_v2_reviewed_pins=sqrt218_fixed_v2_reviewed_pins,
    )


def _claim_literal(receipt: dict) -> str:
    claim = receipt["claim"]
    artifacts = claim["artifacts"]
    target = {
        "azure_sevsnp_cpu": ".azureSEVSNPCPU",
        "nvidia_h100_sm90": ".nvidiaH100SM90",
    }[claim["target"]]
    trust = {
        "azure_sevsnp_confidential_compute": ".azureSEVSNPConfidentialCompute",
        "nvidia_h100_confidential_compute": ".nvidiaH100ConfidentialCompute",
    }[claim["trust"]]
    q = lean_string
    h = _canonical_hex_value
    return f"""{{
      algorithmId := {q(claim['algorithm_id'])}
      algorithmHash := {h(claim['algorithm_hash'])}
      inputHash := {h(claim['input_hash'])}
      parametersHash := {h(claim['parameters_hash'])}
      domainHash := {h(claim['domain_hash'])}
      result := {q(claim['result'])}
      outputHash := {h(claim['output_hash'])}
      nonce := {h(claim['nonce'])}
      target := {target}
      targetProfileHash := {h(claim['target_profile_hash'])}
      trust := {trust}
      trustProfileHash := {h(claim['trust_profile_hash'])}
      artifacts := {{
        sourceTreeHash := {h(artifacts['source_tree_hash'])}
        hostExecutableHash := {h(artifacts['host_executable_hash'])}
        deviceCubinHash := {h(artifacts['device_cubin_hash'])}
        kernelManifestHash := {h(artifacts['kernel_manifest_hash'])}
      }}
      completion := .successful
    }}"""


def _evidence_literal(receipt: dict) -> str:
    bindings = receipt["bindings"]
    hashes = receipt["evidence_hashes"]
    verifier = receipt["verifier"]
    backend = {
        "azure_sevsnp_cpu": ".azureSEVSNPCPU",
        "azure_ncc40ads_h100_v5": ".azureNCCadsH100v5",
    }[receipt["backend"]]
    q = lean_string
    h = _canonical_hex_value
    return f"""{{
    receiptHash := {h(receipt['receipt_sha256'])}
    backend := {backend}
    claim := {_claim_literal(receipt)}
    runBundleHash := {h(bindings['run_bundle_sha256'])}
    wireStatementHash := {h(bindings['wire_statement_sha256'])}
    platformEvidenceHash := {h(hashes['platform_evidence_sha256'])}
    azureMaaTokenHash := {h(hashes['azure_maa_token_sha256'])}
    amdSnpReportHash := {h(hashes['amd_snp_report_sha256'])}
    tpmQuoteHash := {h(hashes['tpm_quote_sha256'])}
    tpmEventLogHash := {h(hashes['tpm_event_log_sha256'])}
    nvidiaEatHash := {h(hashes['nvidia_eat_sha256'])}
    nvidiaEvidenceHash := {h(hashes['nvidia_evidence_sha256'])}
    verifierPolicyHash := {h(verifier['policy_sha256'])}
    verifierArtifactHash := {h(verifier['artifact_sha256'])}
    startChallengeHash := {h(bindings['start_challenge_sha256'])}
    resultBindingHash := {h(bindings['result_binding_sha256'])}
    issuedAt := {q(verifier['issued_at'])}
    expiresAt := {q(verifier['expires_at'])}
    verifierKeyId := {q(verifier['key_id'])}
    signatureHex := {h(receipt['signature']['value_hex'])}
  }}"""


def _entry_name(receipt: dict) -> str:
    """Return a collision-free Lean identifier for one canonical receipt."""

    return "importedTrustedComputeRun_" + receipt["receipt_sha256"]


def generate_registry(
    receipts: list[dict],
    *,
    admission_time: str | None = None,
    sqrt218_fixed_v2_reviewed_pins: dict | None = None,
) -> str:
    invocations = []
    for receipt in receipts:
        validate_bound_registered_results(
            receipt,
            sqrt218_fixed_v2_reviewed_pins=sqrt218_fixed_v2_reviewed_pins,
        )
        invocations.append(
            validate_source_admitted_registered_invocation(
                receipt,
                sqrt218_fixed_v2_reviewed_pins=(
                    sqrt218_fixed_v2_reviewed_pins
                ),
            )
        )
    if (
        sqrt218_fixed_v2_reviewed_pins is not None
        and SQRT218_FIXED_V2_INVOCATION not in invocations
    ):
        raise ReceiptError(
            "fixed-V2 reviewed pins were supplied without their exact receipt"
        )
    ordered = sorted(receipts, key=lambda receipt: receipt["receipt_sha256"])
    unique_fields = (
        ("receipt hash", [receipt["receipt_sha256"] for receipt in ordered]),
        (
            "run-bundle hash",
            [receipt["bindings"]["run_bundle_sha256"] for receipt in ordered],
        ),
        (
            "wire-statement hash",
            [receipt["bindings"]["wire_statement_sha256"] for receipt in ordered],
        ),
        (
            "start challenge",
            [receipt["bindings"]["start_challenge_sha256"] for receipt in ordered],
        ),
        (
            "result binding",
            [receipt["bindings"]["result_binding_sha256"] for receipt in ordered],
        ),
    )
    for label, values in unique_fields:
        if len(values) != len(set(values)):
            raise ReceiptError(f"duplicate trusted-compute {label}")
    hex_definitions = _canonical_hex_definitions(ordered)
    definitions = "\n\n".join(
        "/-- Exact source-admitted receipt ``"
        + receipt["receipt_sha256"]
        + "``. -/\n"
        + "def "
        + _entry_name(receipt)
        + " : TrustedComputeEvidence := "
        + _evidence_literal(receipt)
        for receipt in ordered
    )
    all_definitions = "\n\n".join(
        block for block in (hex_definitions, definitions) if block
    )
    definitions_block = (all_definitions + "\n\n") if all_definitions else ""
    entries = ",\n  ".join(_entry_name(receipt) for receipt in ordered)
    registry = "[]" if not entries else "[\n  " + entries + "\n]"
    lookup_theorems = "\n\n".join(
        "/-- Kernel reduction witnesses exact source-registry membership. -/\n"
        + "@[simp] theorem lookup_"
        + _entry_name(receipt)
        + " :\n  lookupImportedTrustedComputeRun "
        + lean_string(receipt["receipt_sha256"])
        + " =\n    some "
        + _entry_name(receipt)
        + " := by\n  rfl"
        for receipt in ordered
    )
    lookup_theorems_block = ("\n\n" + lookup_theorems) if lookup_theorems else ""
    admission_provenance = (
        "Registry admission review UTC: `" + admission_time + "`.\n\n"
        if ordered and admission_time is not None
        else ""
    )
    return f"""/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.CanonicalHex
import SparkInterval.Execution.Attestation

/-!
# Source-pinned imported trusted-compute runs

This file is generated from independently verified, signed receipts by
`tools/generate_trusted_compute_registry.py` and then reviewed like any other
change to the project's trust boundary.

{admission_provenance}Keeping admission as a closed source list lets concrete imported certificates
reduce in the Lean kernel without a signature-verification oracle or
`native_decide`.  Editing this list is security-equivalent to changing the one
trusted-execution axiom and must receive the same review.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

{definitions_block}/-- Exact normalized receipts admitted by the reviewed importer. -/
def importedTrustedComputeRuns : List TrustedComputeEvidence := {registry}

/-- Lookup is keyed by the canonical receipt SHA-256.  Duplicate identifiers
are rejected by the registry generator before this source is emitted. -/
def lookupImportedTrustedComputeRun
    (receiptHash : Digest) : Option TrustedComputeEvidence :=
  importedTrustedComputeRuns.find? (fun evidence =>
    evidence.receiptHash == receiptHash){lookup_theorems_block}

end SparkInterval.Execution
"""


def _atomic_write(destination: Path, source: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="*")
    parser.add_argument("--out", required=True)
    parser.add_argument("--key-manifest", type=Path, default=DEFAULT_KEY_MANIFEST)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument(
        "--sqrt218-fixed-v2-reviewed-pins",
        type=Path,
        help=(
            "compact source-reviewed fixed-V2 pins; loaded only after every "
            "receipt signature has been verified"
        ),
    )
    parser.add_argument(
        "--admission-time",
        help=(
            "canonical UTC review time used for deterministic audits; "
            "defaults to current UTC"
        ),
    )
    parser.add_argument(
        "--allow-development-key",
        action="store_true",
        help="explicitly permit the development-only bootstrap verifier key",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="explicitly generate the fail-closed empty registry",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check that --out is exactly reproducible without writing it",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.receipts and not args.allow_empty:
            raise ReceiptError("refusing to generate an empty registry without --allow-empty")
        if args.admission_time is not None and not args.check:
            raise ReceiptError(
                "--admission-time is audit-only and requires --check; "
                "new registry writes always use current UTC"
            )
        if args.check and args.receipts and args.admission_time is None:
            raise ReceiptError(
                "checking a nonempty registry requires its recorded --admission-time"
            )
        receipts = [
            load_verified_receipt(
                Path(path),
                key_manifest=args.key_manifest,
                public_key=args.public_key,
                allow_development_key=args.allow_development_key,
            )
            for path in args.receipts
        ]
        reviewed_pins = None
        if args.sqrt218_fixed_v2_reviewed_pins is not None:
            reviewed_pins = (
                sqrt218_fixed_v2_receipt.load_canonical_reviewed_pins(
                    args.sqrt218_fixed_v2_reviewed_pins
                )
            )
        if args.admission_time is None:
            admission = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            admission_text = admission.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            admission_text = args.admission_time
            admission = _canonical_utc_timestamp(admission_text, "admission_time")
        invocations = [
            validate_registry_admission(
                receipt,
                now=admission,
                sqrt218_fixed_v2_reviewed_pins=reviewed_pins,
            )
            for receipt in receipts
        ]
        if (
            reviewed_pins is not None
            and SQRT218_FIXED_V2_INVOCATION not in invocations
        ):
            raise ReceiptError(
                "fixed-V2 reviewed pins were supplied without their exact receipt"
            )
        source = generate_registry(
            receipts,
            admission_time=admission_text if receipts else None,
            sqrt218_fixed_v2_reviewed_pins=reviewed_pins,
        )
        destination = Path(args.out)
        if args.check:
            if destination.read_text(encoding="utf-8") != source:
                raise ReceiptError(f"{destination} is not the generated registry")
        else:
            _atomic_write(destination, source)
    except (
        OSError,
        BundleError,
        ReceiptError,
        sqrt218_fixed_v2_receipt.FixedV2ReceiptError,
        KeyError,
    ) as exc:
        print(f"generate_trusted_compute_registry: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
