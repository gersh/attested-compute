#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Emit a review-only Lean deployment pin from one verified production receipt.

The command never edits ``ProductionDeploymentPins.lean``.  Reviewers first
admit the same receipt to ``TrustedComputeRegistry.lean``, compare the
human-readable audit fields printed here, and then manually install the exact
definition after the corresponding source-scale run has been accepted.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

from create_run_bundle import BundleError
from generate_trusted_compute_lean import (
    DEFAULT_KEY_MANIFEST,
    SQRT218_FIXED_V2_INVOCATION,
    lean_string,
    load_verified_receipt,
    require_production_verifier,
    validate_source_admitted_registered_invocation,
)
from tg_verifier import sqrt218_fixed_v2_receipt
from trusted_compute_receipt import ReceiptError


DEPLOYMENT_DEFINITIONS = {
    "cdemTableAbelProductionV2": "cdemTableAbelProductionDeployment",
    "hurstSharedFourResidualProductionV2":
        "hurstSharedFourResidualProductionDeployment",
    "ch25PsiLemma92ProductionV1": "ch25PsiLemma92ProductionDeployment",
    "ramareZunigaLemma62ProductionV1":
        "ramareZunigaLemma62ProductionDeployment",
    "helfgottProp1224ProductionV1":
        "helfgottProp1224ProductionDeployment",
    "ch25A7BoundaryProductionV1": "ch25A7BoundaryProductionDeployment",
    "plattHead2e4ProductionV1": "plattHead2e4ProductionDeployment",
    "plattDirichletTheorem71ProductionV1":
        "plattDirichletTheorem71ProductionDeployment",
    "plattTrudgianFiniteRHProductionV1":
        "plattTrudgianFiniteRHProductionDeployment",
    "helfgottPlattGoldbachProductionV1":
        "helfgottPlattGoldbachProductionDeployment",
    "goldbach10Pow27ProductionV1": "goldbach10Pow27ProductionDeployment",
    "helfgottSqrt218ProductionV1": "helfgottSqrt218ProductionDeployment",
    SQRT218_FIXED_V2_INVOCATION:
        "helfgottSqrt218FixedV2ProductionDeployment",
}


def fixed_v2_reviewed_pins_from_verified_receipt(receipt: dict) -> dict:
    """Derive the review candidate from one already verified signed receipt.

    This helper performs no signature verification and grants no authority.
    The CLI calls it only after ``load_verified_receipt`` and production-key
    classification.  The strict result parser recovers the exact certificate
    byte length and requires its embedded digest to equal ``claim.input_hash``.
    """

    claim = receipt["claim"]
    artifacts = claim["artifacts"]
    verifier = receipt["verifier"]
    bindings = receipt["bindings"]
    try:
        _, native_result = sqrt218_fixed_v2_receipt.decode_result_envelope(
            claim["result"],
            expected_input_sha256=claim["input_hash"],
        )
        pins = sqrt218_fixed_v2_receipt.validate_reviewed_pins({
            "algorithm_hash": claim["algorithm_hash"],
            "algorithm_id": claim["algorithm_id"],
            "certificate_sha256": claim["input_hash"],
            "certificate_size_bytes": native_result["input_size_bytes"],
            "checker_executable_sha256": artifacts["host_executable_hash"],
            "device_cubin_sha256": artifacts["device_cubin_hash"],
            "domain_hash": claim["domain_hash"],
            "execution_closure_sha256": artifacts["kernel_manifest_hash"],
            "kind": sqrt218_fixed_v2_receipt.REVIEWED_PINS_KIND,
            "parameters_hash": claim["parameters_hash"],
            "receipt_sha256": receipt["receipt_sha256"],
            "schema_version": sqrt218_fixed_v2_receipt.SCHEMA_VERSION,
            "source_tree_hash": artifacts["source_tree_hash"],
            "target_profile_hash": claim["target_profile_hash"],
            "trust_profile_hash": claim["trust_profile_hash"],
            "verifier_artifact_sha256": verifier["artifact_sha256"],
            "verifier_key_id": verifier["key_id"],
            "verifier_policy_sha256": verifier["policy_sha256"],
            "wire_statement_sha256": bindings["wire_statement_sha256"],
        })
    except sqrt218_fixed_v2_receipt.FixedV2ReceiptError as exc:
        raise ReceiptError(
            f"cannot derive fixed-V2 production candidate: {exc}"
        ) from exc
    validate_source_admitted_registered_invocation(
        receipt,
        sqrt218_fixed_v2_reviewed_pins=pins,
    )
    return pins


def _invocation_and_deployment_binding(receipt: dict) -> tuple[str, dict]:
    if receipt["claim"]["algorithm_id"] == sqrt218_fixed_v2_receipt.ALGORITHM_ID:
        fixed_pins = fixed_v2_reviewed_pins_from_verified_receipt(receipt)
        invocation = SQRT218_FIXED_V2_INVOCATION
    else:
        fixed_pins = None
        invocation = validate_source_admitted_registered_invocation(receipt)

    claim = receipt["claim"]
    artifacts = claim["artifacts"]
    binding = {
        "receipt_hash": receipt["receipt_sha256"],
        "target_profile_hash": claim["target_profile_hash"],
        "trust_profile_hash": claim["trust_profile_hash"],
        "artifacts": {
            "source_tree_hash": artifacts["source_tree_hash"],
            "host_executable_hash": artifacts["host_executable_hash"],
            "device_cubin_hash": artifacts["device_cubin_hash"],
            "kernel_manifest_hash": artifacts["kernel_manifest_hash"],
        },
    }
    if fixed_pins is not None:
        binding.update({
            "certificate_sha256": fixed_pins["certificate_sha256"],
            "certificate_bytes": fixed_pins["certificate_size_bytes"],
        })
    return invocation, binding


def deployment_binding_values(receipt: dict) -> dict:
    """Return the exact fields compared by the reviewed Lean deployment pin.

    This is a review diagnostic, not an authorization predicate: signature
    verification, source-registry admission, and the Lean trusted-run bridge
    remain separate required checks.  Keeping the extraction in one helper
    prevents the candidate renderer and its substitution regressions from
    silently disagreeing about which run-specific fields are pinned.
    """

    return _invocation_and_deployment_binding(receipt)[1]


def matches_deployment_binding(receipt: dict, binding: dict) -> bool:
    """Check the run-specific equality portion of a reviewed deployment pin.

    A ``True`` result is necessary but deliberately not sufficient for
    authorization.  In particular, this helper does not verify a signature or
    assert that either the receipt or the pin is present in reviewed Lean
    source.
    """

    try:
        return deployment_binding_values(receipt) == binding
    except (KeyError, ReceiptError, TypeError):
        return False


def generate_candidate(receipt: dict) -> str:
    invocation, binding = _invocation_and_deployment_binding(receipt)
    try:
        definition = DEPLOYMENT_DEFINITIONS[invocation]
    except KeyError as exc:
        raise ReceiptError(
            f"{invocation!r} is a tutorial/pilot and has no production pin"
        ) from exc
    artifacts = binding["artifacts"]
    bindings = receipt["bindings"]
    verifier = receipt["verifier"]
    q = lean_string
    reviewed_type = (
        "ReviewedSqrt218FixedV2Deployment"
        if invocation == SQRT218_FIXED_V2_INVOCATION
        else "ReviewedProductionDeployment"
    )
    fixed_fields = (
        "\n"
        f"  certificateSHA256 := {q(binding['certificate_sha256'])}\n"
        f"  certificateBytes := {binding['certificate_bytes']}"
        if invocation == SQRT218_FIXED_V2_INVOCATION
        else ""
    )
    return f"""-- Review-only candidate; do not install before the real run and
-- source-registry entry have both been independently reviewed.
-- registered invocation: {invocation}
-- registry entry: importedTrustedComputeRun_{receipt['receipt_sha256']}
-- wire statement: {bindings['wire_statement_sha256']}
-- run bundle: {bindings['run_bundle_sha256']}
-- verifier policy: {verifier['policy_sha256']}
-- verifier artifact: {verifier['artifact_sha256']}
def {definition} :
    Option {reviewed_type} := some {{
  receiptHash := {q(binding['receipt_hash'])}
  targetProfileHash := {q(binding['target_profile_hash'])}
  trustProfileHash := {q(binding['trust_profile_hash'])}
  artifacts := {{
    sourceTreeHash := {q(artifacts['source_tree_hash'])}
    hostExecutableHash := {q(artifacts['host_executable_hash'])}
    deviceCubinHash := {q(artifacts['device_cubin_hash'])}
    kernelManifestHash := {q(artifacts['kernel_manifest_hash'])}
  }}{fixed_fields}
}}
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--key-manifest", type=Path, default=DEFAULT_KEY_MANIFEST)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument(
        "--allow-development-key",
        action="store_true",
        help=(
            "permit development-key signature diagnostics; candidate "
            "generation still requires a production-classified key"
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = load_verified_receipt(
            args.receipt,
            key_manifest=args.key_manifest,
            public_key=args.public_key,
            allow_development_key=args.allow_development_key,
        )
        require_production_verifier(receipt, args.key_manifest)
        source = generate_candidate(receipt)
        if args.out is None:
            sys.stdout.write(source)
        else:
            args.out.write_text(source, encoding="utf-8")
    except (OSError, BundleError, ReceiptError, KeyError) as exc:
        print(
            f"generate_production_deployment_candidate: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
