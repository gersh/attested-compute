#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate a Lean consumer for one source-admitted trusted-compute receipt.

The receipt must first be added to ``TrustedComputeRegistry.lean`` with
``generate_trusted_compute_registry.py``.  The generated theorem is therefore
fail closed: its structural proof succeeds only while the exact receipt hash
and statement remain in that reviewed source registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from create_run_bundle import (
    BundleError,
    canonical_json_bytes,
    hash_file,
    parse_json_bytes,
    validate_sha256,
)
from trusted_compute_receipt import (
    BACKENDS,
    KEY_ID_RE,
    ReceiptError,
    validate_receipt,
    verify_signature,
)
from tg_verifier import sqrt218_fixed_v2_receipt


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_KEY_MANIFEST = (
    REPOSITORY_ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
)
ISSUER_PROFILE_FIELDS = {
    "backend",
    "target_profile_sha256",
    "trust_profile_sha256",
    "verifier_artifact_sha256",
    "verifier_policy_sha256",
}
REGISTERED_INVOCATIONS = (
    "cubicSumDivThree20000V1",
    "h100FormalPtxConstantOneV1",
    "cdemTableAbelProductionV2",
    "hurstSharedFourResidualProductionV2",
    "ch25PsiLemma92ProductionV1",
    "ramareZunigaLemma62ProductionV1",
    "helfgottProp1224ProductionV1",
    "ch25A7BoundaryProductionV1",
    "plattHead2e4ProductionV1",
    "plattDirichletTheorem71ProductionV1",
    "plattTrudgianFiniteRHProductionV1",
    "helfgottPlattGoldbachProductionV1",
    "goldbach10Pow27ProductionV1",
    "helfgottSqrt218ProductionV1",
    "helfgottSqrt218FixedProductionV2",
    "plattStrongerRangeLiveProductionV1",
)
SQRT218_FIXED_V2_INVOCATION = "helfgottSqrt218FixedProductionV2"


def canonical_hex_certificate_name(value: str) -> str:
    """Name used by the source-registry generator for an exact hex value."""

    identity = hashlib.sha256(value.encode("ascii")).hexdigest()
    return f"trustedComputeCanonicalHex_{len(value)}_{identity}"


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError(f"duplicate JSON key in verifier-key manifest: {key!r}")
        result[key] = value
    return result


def load_key_manifest(path: Path) -> dict[str, dict]:
    """Load and validate a source-reviewed verifier-key manifest."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"cannot read verifier-key manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "keys"}:
        raise ReceiptError("verifier-key manifest has wrong top-level fields")
    if value["schema_version"] != 1 or not isinstance(value["keys"], list):
        raise ReceiptError("unsupported verifier-key manifest")
    result: dict[str, dict] = {}
    expected_fields = {
        "allowed_verifier_profiles",
        "key_id",
        "public_key_path",
        "public_key_sha256",
        "classification",
    }
    public_key_identities: dict[str, str] = {}
    for entry in value["keys"]:
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise ReceiptError("verifier-key manifest entry has wrong fields")
        key_id = entry["key_id"]
        if not isinstance(key_id, str) or KEY_ID_RE.fullmatch(key_id) is None:
            raise ReceiptError("verifier-key manifest contains an invalid key id")
        if key_id in result:
            raise ReceiptError(f"duplicate verifier key id in manifest: {key_id!r}")
        if entry["classification"] not in {"development", "production"}:
            raise ReceiptError(f"invalid classification for verifier key {key_id!r}")
        try:
            public_key_hash = validate_sha256(
                entry["public_key_sha256"], "verifier public-key hash"
            )
        except BundleError as exc:
            raise ReceiptError(str(exc)) from exc
        prior_key_id = public_key_identities.get(public_key_hash)
        if prior_key_id is not None:
            raise ReceiptError(
                "duplicate verifier public-key hash across identities: "
                f"{prior_key_id!r} and {key_id!r}"
            )
        public_key_identities[public_key_hash] = key_id
        profiles = entry["allowed_verifier_profiles"]
        if not isinstance(profiles, list) or not profiles:
            raise ReceiptError(
                f"verifier key {key_id!r} must allow at least one exact verifier profile"
            )
        normalized_profiles: list[dict[str, str]] = []
        for profile in profiles:
            if not isinstance(profile, dict) or set(profile) != ISSUER_PROFILE_FIELDS:
                raise ReceiptError(
                    f"verifier key {key_id!r} has a malformed verifier profile"
                )
            backend = profile["backend"]
            if backend not in BACKENDS:
                raise ReceiptError(
                    f"verifier key {key_id!r} has unsupported backend {backend!r}"
                )
            for field in (
                "target_profile_sha256",
                "trust_profile_sha256",
                "verifier_artifact_sha256",
                "verifier_policy_sha256",
            ):
                try:
                    digest = validate_sha256(profile[field], field.replace("_", " "))
                except BundleError as exc:
                    raise ReceiptError(str(exc)) from exc
                if digest == "0" * 64:
                    raise ReceiptError(
                        f"verifier key {key_id!r} profile {field} cannot be all zero"
                    )
            normalized_profiles.append(dict(profile))
        profile_identities = [
            (
                profile["backend"],
                profile["target_profile_sha256"],
                profile["trust_profile_sha256"],
                profile["verifier_artifact_sha256"],
                profile["verifier_policy_sha256"],
            )
            for profile in normalized_profiles
        ]
        if len(profile_identities) != len(set(profile_identities)):
            raise ReceiptError(f"verifier key {key_id!r} has duplicate verifier profiles")
        relative = Path(entry["public_key_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ReceiptError("manifest public-key path must stay within its directory")
        normalized = dict(entry)
        normalized["allowed_verifier_profiles"] = normalized_profiles
        result[key_id] = normalized
    return result


def verified_public_key(
    receipt: dict,
    *,
    key_manifest: Path,
    public_key: Path | None,
    allow_development_key: bool,
) -> Path:
    """Resolve the receipt key through the manifest and verify its file hash."""

    manifest = load_key_manifest(key_manifest)
    key_id = receipt["verifier"]["key_id"]
    try:
        pin = manifest[key_id]
    except KeyError as exc:
        raise ReceiptError(f"verifier key id is absent from manifest: {key_id!r}") from exc
    if pin["classification"] == "development" and not allow_development_key:
        raise ReceiptError(
            f"development verifier key {key_id!r} requires --allow-development-key"
        )
    actual_profile = {
        "backend": receipt["backend"],
        "target_profile_sha256": receipt["claim"]["target_profile_hash"],
        "trust_profile_sha256": receipt["claim"]["trust_profile_hash"],
        "verifier_artifact_sha256": receipt["verifier"]["artifact_sha256"],
        "verifier_policy_sha256": receipt["verifier"]["policy_sha256"],
    }
    if actual_profile not in pin["allowed_verifier_profiles"]:
        raise ReceiptError(
            "receipt backend/target-profile/trust-profile/verifier-artifact/policy "
            "tuple is not source-approved "
            f"for verifier key {key_id!r}"
        )
    manifest_directory = key_manifest.parent.resolve(strict=True)
    selected = public_key or manifest_directory / pin["public_key_path"]
    try:
        selected = selected.resolve(strict=True)
    except OSError as exc:
        raise ReceiptError(f"cannot resolve verifier public key: {exc}") from exc
    if not selected.is_file():
        raise ReceiptError("verifier public key is not a regular file")
    if public_key is None:
        try:
            selected.relative_to(manifest_directory)
        except ValueError as exc:
            raise ReceiptError(
                "manifest-relative verifier public key escapes through a symlink"
            ) from exc
    actual_hash, _ = hash_file(selected)
    if actual_hash != pin["public_key_sha256"]:
        raise ReceiptError("verifier public key does not match the manifest pin")
    return selected


def load_verified_receipt(
    path: Path,
    *,
    key_manifest: Path = DEFAULT_KEY_MANIFEST,
    public_key: Path | None = None,
    allow_development_key: bool = False,
) -> dict:
    """Read one canonical signed receipt and verify the source-pinned key.

    A single conventional final newline is accepted for reviewed fixtures and
    source files.  No other non-canonical JSON spelling is accepted.
    """

    raw = path.read_bytes()
    payload = raw[:-1] if raw.endswith(b"\n") else raw
    receipt = validate_receipt(parse_json_bytes(payload, str(path)))
    if canonical_json_bytes(receipt) != payload:
        raise ReceiptError(f"{path} is not canonical JSON")
    selected_key = verified_public_key(
        receipt,
        key_manifest=key_manifest,
        public_key=public_key,
        allow_development_key=allow_development_key,
    )
    verify_signature(receipt, selected_key)
    return receipt


def lean_string(value: str) -> str:
    pieces: list[str] = ['"']
    for character in value:
        code = ord(character)
        if character == '"':
            pieces.append('\\"')
        elif character == "\\":
            pieces.append("\\\\")
        elif character == "\n":
            pieces.append("\\n")
        elif character == "\r":
            pieces.append("\\r")
        elif character == "\t":
            pieces.append("\\t")
        elif 0x20 <= code <= 0x7E:
            pieces.append(character)
        else:
            pieces.append(f"\\u{{{code:x}}}")
    pieces.append('"')
    return "".join(pieces)


def render_lean_allowed_verifier_profiles(path: Path = DEFAULT_KEY_MANIFEST) -> str:
    """Render the exact Lean allowlist block synchronized with the key manifest."""

    manifest = load_key_manifest(path)
    profiles = sorted(
        (
            key_id,
            entry["classification"],
            profile["backend"],
            profile["target_profile_sha256"],
            profile["trust_profile_sha256"],
            profile["verifier_artifact_sha256"],
            profile["verifier_policy_sha256"],
        )
        for key_id, entry in manifest.items()
        for profile in entry["allowed_verifier_profiles"]
    )
    records = ",\n  ".join(
        "{\n"
        f"    keyId := {lean_string(key_id)}\n"
        f"    classification := {lean_string(classification)}\n"
        f"    backend := {lean_string(backend)}\n"
        f"    targetProfileHash := {lean_string(target_profile_hash)}\n"
        f"    trustProfileHash := {lean_string(trust_profile_hash)}\n"
        f"    verifierArtifactHash := {lean_string(artifact_hash)}\n"
        f"    verifierPolicyHash := {lean_string(policy_hash)}\n"
        "  }"
        for key_id, classification, backend, target_profile_hash,
        trust_profile_hash, artifact_hash, policy_hash in profiles
    )
    return (
        "def trustedComputeAllowedVerifierProfiles : "
        "List TrustedComputeVerifierProfile := [\n  "
        + records
        + "\n]"
    )


def require_production_verifier(receipt: dict, key_manifest: Path) -> None:
    """Reject generation of a theorem consumer under a development key."""

    manifest = load_key_manifest(key_manifest)
    key_id = receipt["verifier"]["key_id"]
    try:
        classification = manifest[key_id]["classification"]
    except KeyError as exc:
        raise ReceiptError(f"verifier key id is absent from manifest: {key_id!r}") from exc
    if classification != "production":
        raise ReceiptError(
            "Lean trusted-compute consumers require a production-classified "
            f"verifier key; {key_id!r} is {classification!r}"
        )


def _require_sqrt218_fixed_v2_reviewed_pins(
    reviewed_pins: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate the compact pins used only to restrict a verified receipt.

    These unsigned pins never authorize a receipt.  The command-line path
    first verifies the generic receipt under a source-pinned production key;
    this helper then requires exact equality with every fixed-V2 pin.
    """

    if reviewed_pins is None:
        raise ReceiptError(
            "helfgottSqrt218FixedProductionV2 requires exact reviewed pins"
        )
    try:
        return sqrt218_fixed_v2_receipt.validate_reviewed_pins(reviewed_pins)
    except sqrt218_fixed_v2_receipt.FixedV2ReceiptError as exc:
        raise ReceiptError(f"invalid fixed-V2 reviewed pins: {exc}") from exc


def registered_invocation_expected(
    invocation: str,
    *,
    sqrt218_fixed_v2_reviewed_pins: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return the source-reviewed wire identity for one closed invocation.

    The fixed-V2 input and output are produced by the reviewed cloud run.
    Its static identity is returned here, while
    ``validate_registered_invocation`` additionally checks the complete
    281-byte result envelope and every receipt/deployment field against the
    mandatory compact reviewed pins.
    """

    if invocation == "cubicSumDivThree20000V1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=cubic-sum-div-three\n"
            "input=canonical-decimal-natural-upper-inclusive\n"
            "output=canonical-decimal-natural\n"
            "arithmetic=natural-accumulator-with-u64-proof-on-registered-domain\n"
            "division=natural-division-by-3-after-total\n"
            "semantics=loop-x-from-0-through-upper-add-x-cubed-then-divide-total"
        )
        input_text = "20000"
        parameters = (
            '{"accumulator":"u64-no-wrap","divide_after_sum":true,'
            '"divisor":3,"inclusive":true}'
        )
        domain = '{"input":"nat","output":"nat","range_start":0}'
        algorithm_id = "sparkinterval.example.cubic-sum-div-three.v1"
        result = "13334666700000000"
        deployment: dict[str, str] = {}
    elif invocation == "h100FormalPtxConstantOneV1":
        ptx_path = (
            REPOSITORY_ROOT
            / "examples/trusted-compute/h100_formal_ptx_constant_one.sm_90.ptx"
        )
        try:
            definition = ptx_path.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as error:
            raise ReceiptError(f"cannot read source-pinned H100 pilot PTX: {error}") from error
        input_text = (
            '{"algorithm":"sparkinterval.binary64_interval_expr.v1",'
            '"expression":{"op":"const","value":{"hi":"3ff0000000000000",'
            '"lo":"3ff0000000000000"}},"kind":"sparkinterval_reference_batch",'
            '"rows":[[]],"schema_version":1,"variable_count":0}'
        )
        parameters = (
            '{"result_format":"sparkinterval_h100_formal_ptx_pilot_result_v1",'
            '"row_count":1,"target":"sm_90","variable_count":0}'
        )
        domain = (
            '{"expression":"constant_interval_one",'
            '"interval_hi_bits":"3ff0000000000000",'
            '"interval_lo_bits":"3ff0000000000000","rows":1,"status":0}'
        )
        algorithm_id = "sparkinterval.pilot.h100-formal-ptx-constant-one.v1"
        result = (
            '{"format":"sparkinterval_h100_formal_ptx_pilot_result_v1",'
            '"hi":"3ff0000000000000","lo":"3ff0000000000000",'
            '"row_count":1,"schema_version":1,"status":0,"target":"sm_90"}'
        )
        deployment = {
            "target": "nvidia_h100_sm90",
            "trust": "nvidia_h100_confidential_compute",
        }
    elif invocation == "cdemTableAbelProductionV2":
        definition = (
            "sparkinterval.registered-algorithm.v2\n"
            "name=ternary-goldbach-cdem-table-abel\n"
            "producer=reference/tg_cdem_abel_measured_workload.cpp\n"
            "semantics=checked-gap-free-local-floorjump-recurrence-certificate-with-local-fold-evidence\n"
            "certificate=SparkInterval.Generated.CDEMAbelProduction.certificate\n"
            "certificate-transcript-sha256=2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123\n"
            "certificate-lean-source-sha256=c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9\n"
            "artifact=TG-CDEM-ABEL-ARTIFACT-V1-complete-recurrence-stream\n"
            "artifact-binding=trace-recomputes-artifact-after-complete-independent-replay\n"
            "output=false-or-canonical-decimal-nat-pair-u-v\n"
            "pairing=mathlib-nat-pair\n"
            "weight-scale=1000000000000000000\n"
            "signed-rounding=ceil-positive-floor-negative\n"
            "sqrt-rounding=least-q-with-q-squared-times-n-at-least-scale-squared"
        )
        input_text = (
            '{"K":199330,"N":5000000000,'
            '"weight_scale":1000000000000000000}'
        )
        parameters = (
            '{"a":5000000001,"g_zero_override":true,'
            '"mobius":"linear-sieve-exact",'
            '"output_encoding":"nat_pair_decimal",'
            '"sqrt_rounding":"exact_square_test"}'
        )
        domain = (
            '{"claim":"two-pre-endpoint-abel-increment-upper-bounds",'
            '"index_lower":1,"index_upper":5000000000,'
            '"prefix_upper":199330}'
        )
        algorithm_id = "sparkinterval.ternary-goldbach.cdem-table-abel.v2"
        result = "2372685835387717172679029560108650251645442524"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "hurstSharedFourResidualProductionV2":
        definition = (
            "sparkinterval.registered-algorithm.v2\n"
            "name=ternary-goldbach-hurst-shared-four-residual\n"
            "producer=reference/tg_hurst_residual_shard.cpp\n"
            "semantics=gap-free-two-pass-mobius-prefix-and-exact-directed-guard-checks\n"
            "evidence=local-primitive-row-deltas-plus-local-state-guard-decisions\n"
            "global-prefix=derived-in-lean-from-root-zero-and-row-delta-recurrence\n"
            "little-q96-tracking=active-through-1000000000000-zero-after\n"
            "source-range=[1,10000000000000001)\n"
            "state=mertens-squarefree-little-lower-q96-little-upper-q96\n"
            "hurst-guard=1000000*abs(M)^2<=571^2*n-for-n>=33\n"
            "squarefree-density=607927101854026628/10^18<=6/pi^2<=607927101854026629/10^18\n"
            "squarefree-b1=151/2000-after-9243;check-value-at-n>=9243-and-right-limit-at-n+1\n"
            "squarefree-b2=57/2000-after-438429;check-value-at-n>=438429-and-right-limit-at-n+1\n"
            "little-2-11=right*abs(q96)^2<=2*2^192-for-1<=n<=10^12\n"
            "little-stronger=4*right*abs(q96)^2<=2^192-for-3<=n<7727068587\n"
            "output=false-or-true-with-local-replay-evidence"
        )
        input_text = (
            '{"campaign":"hurst-shared-four-residual-v2",'
            '"source_lower":1,'
            '"source_upper_exclusive":10000000000000001}'
        )
        parameters = (
            '{"little_scale_bits":96,"receipt_leaves":10000,'
            '"replay":"independent-two-pass",'
            '"row_domain":"sparkinterval.tg.hurst-residual-mobius-rows.v1",'
            '"squarefree_threshold_endpoints":'
            '"inclusive_value_and_right_limit"}'
        )
        domain = (
            '{"atoms":["cdem-squarefree","mertens-hurst",'
            '"platt-little-mertens-2-11",'
            '"platt-little-mertens-stronger"],'
            '"source_lower":1,'
            '"source_upper_exclusive":10000000000000001,'
            '"squarefree_thresholds":[9243,438429]}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.hurst-shared-four-residual.v2"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "ch25PsiLemma92ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-ch25-psi-lemma-9-2\n"
            "producer=reference/tg_psi_residual_shard.cpp\n"
            "semantics=gap-free-two-pass-prime-power-q64-endpoint-guards\n"
            "source-range=[1,10000000000000]\n"
            "state=psi-lower-q64-psi-upper-q64\n"
            "output=false-or-true-with-prime-power-gap-log-and-integer-guard-evidence"
        )
        input_text = (
            '{"campaign":"ch25-psi-lemma-9-2-v1",'
            '"source_lower":1,"source_upper":10000000000000}'
        )
        parameters = (
            '{"crlibm_commit":"eb3063791aa75bc9705b49283bf14250465220a7",'
            '"event_count":346065767406,'
            '"primesieve_commit":"4f85384851da23c36c01ec01ef85b5d9d246e556",'
            '"q64_scale_bits":64,"replay":"independent-two-pass",'
            '"row_domain":"sparkinterval.tg.psi-prime-power-rows.v1"}'
        )
        domain = (
            '{"claim":"ch25-lemma-9-2-psi-source",'
            '"source_lower":1,"source_upper":10000000000000,'
            '"upper_denominator":25000000,"upper_numerator":19764819}'
        )
        algorithm_id = "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.v1"
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "ramareZunigaLemma62ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-ramare-zuniga-lemma-6-2\n"
            "producer=gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp\n"
            "semantics=gap-free-q32-r2star-prefix-enclosures-and-exact-squared-endpoint-guards\n"
            "source-range=[1,21000000001)\n"
            "coefficient=(vonMangoldt*vonMangoldt)(n)-vonMangoldt(n)*log(n)+2*eulerMascheroniConstant\n"
            "scale=2^32\n"
            "bound=(193/100)*sqrt(x)*log(x)\n"
            "output=false-or-true-with-full-source-evidence"
        )
        input_text = (
            '{"campaign":"ramare-zuniga-lemma-6-2-v1",'
            '"source_lower":1,"source_upper_exclusive":21000000001}'
        )
        parameters = (
            '{"chunk_span":1000000,"gamma_lower_q32":2479051107,'
            '"gamma_upper_q32":2479194040,"harmonic_terms":100000,'
            '"log_series_terms":20,"replay":"independent_cpp_full_row_exact_v1",'
            '"scale_bits":32}'
        )
        domain = (
            '{"bound_denominator":100,"bound_numerator":193,'
            '"claim":"ramare-zuniga-2024-lemma-6-2-source",'
            '"source_lower":1,"source_upper_exclusive":21000000001,'
            '"x_lower":3,"x_upper":21000000000}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.ramare-zuniga-lemma-6-2.v1"
        )
        result = "true"
        deployment = {
            "target": "nvidia_h100_sm90",
            "trust": "nvidia_h100_confidential_compute",
        }
    elif invocation == "helfgottProp1224ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-helfgott-proposition-12-2-4\n"
            "producer=reference/tg_prop1224_mpfr_shard.cpp\n"
            "semantics=gap-free-independent-q-directed-mpfr-gmp-row-verification\n"
            "source-rank-range=[0,3389047618)\n"
            "source-q-range=q<3300000000-or-(210-divides-q-and-q<22000000000)\n"
            "source-realization=exact-lean-ramareG-cE-f1-window-and-error-claim\n"
            "output=false-or-true-with-full-source-evidence"
        )
        input_text = (
            '{"campaign":"helfgott-prop-12-2-4-mpfr-v1",'
            '"rank_lower":0,"rank_upper":3389047618}'
        )
        parameters = (
            '{"leaf_rows":262144,"mpfr_version":"4.2.1",'
            '"precision_bits":192,'
            '"row_domain":"sparkinterval.tg.prop1224-mpfr-directed-rows.v1",'
            '"source_realization":"external-mpfr-gmp-exact-lean-row"}'
        )
        domain = (
            '{"claim":"helfgott-proposition-12-2-4-finite-computation-source",'
            '"dense_q_upper_exclusive":3300000000,"extension_divisor":210,'
            '"extension_q_upper_exclusive":22000000000,'
            '"rank_lower":0,"rank_upper_exclusive":3389047618}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach."
            "helfgott-proposition-12-2-4-mpfr.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "ch25A7BoundaryProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-ch25-lemma-a7-boundary\n"
            "producer=tg_verifier/a7_flint.py\n"
            "semantics=pinned-full-flint-arb-boundary-replay-with-rational-box-evidence\n"
            "source-rectangle=(-3,5)+i(-4,4)-frontier\n"
            "raw-function=-zeta-prime(s)/zeta(s)-1/(s-1)+1/(s+2)\n"
            "bound=349/250\n"
            "retained-artifact-sha256="
            "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29\n"
            "source-realization=external-flint-arb-boxes-contain-mathlib-riemannZeta-expression\n"
            "output=false-or-true-with-boundary-evidence"
        )
        input_text = (
            '{"campaign":"ch25-a7-boundary-v1",'
            '"retained_artifact_sha256":'
            '"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
        )
        parameters = (
            '{"flint_release":30600,"flint_version":"3.6.0",'
            '"leaf_count":16191,"python_flint_version":"0.9.0",'
            '"series_cap":4,"series_length":2,"threads":1}'
        )
        domain = (
            '{"bound_denominator":250,"bound_numerator":349,'
            '"claim":"ch25-lemma-a7-arb-boundary-source",'
            '"imag_lower":-4,"imag_upper":4,'
            '"real_lower":-3,"real_upper":5}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "plattHead2e4ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-platt-head-2e4\n"
            "producer=tg_verifier/zeta_zero_campaign.py\n"
            "semantics=complete-indexed-flint-platt-head-replay-to-literal-q128-table\n"
            "source-height=20000\n"
            "source-multiplicity-count=22491\n"
            "all-q128-rows-sha256="
            "fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca\n"
            "included-q128-rows-sha256="
            "e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7\n"
            "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n"
            "output=false-or-true-with-literal-q128-checked-head-evidence"
        )
        input_text = (
            '{"all_q128_rows_sha256":'
            '"fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",'
            '"campaign":"platt-head-2e4",'
            '"included_q128_rows_sha256":'
            '"e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",'
            '"source_height":20000,"source_multiplicity_count":22491}'
        )
        parameters = (
            '{"flint_release":30600,"flint_threads":1,'
            '"flint_version":"3.6.0","precision_bits":96,'
            '"python_flint_version":"0.9.0","q128_scale_bits":128}'
        )
        domain = (
            '{"all_q128_rows_sha256":'
            '"fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca",'
            '"claim":"platt-zero-enumeration-2e4-source",'
            '"imag_lower_exclusive":0,'
            '"included_q128_rows_sha256":'
            '"e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7",'
            '"multiplicity_count":22491,'
            '"real_lower_exclusive":0,"real_upper_exclusive":1,'
            '"source_height":20000}'
        )
        algorithm_id = "sparkinterval.ternary-goldbach.platt-head-2e4.v1"
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "plattDirichletTheorem71ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-platt-dirichlet-theorem-7-1\n"
            "producer=tools/tg_dirichlet_campaign.py+tools/tg_dirichlet_flint_backend.py\n"
            "semantics=complete-source-roster-even-and-odd-grh-verification-at-platt-heights\n"
            "source-modulus-range=[1,400000]\n"
            "q2-to-q400000-primitive-character-count=29565923837\n"
            "q1-source-campaign=platt-trudgian-rh-3e12\n"
            "source-realization=external-roster-completed-l-hardy-zero-brackets-conjugation-and-total-zero-count\n"
            "finalizer-target=azure-sevsnp-cpu-after-h100-and-cpu-branches\n"
            "output=false-or-true-with-two-branch-source-evidence"
        )
        input_text = (
            '{"campaign":"platt-dirichlet-theorem-7-1",'
            '"q1_source_campaign":"platt-trudgian-rh-3e12",'
            '"q2_to_q400000_primitive_character_count":29565923837,'
            '"source_modulus_lower":1,"source_modulus_upper":400000}'
        )
        parameters = (
            '{"even_height":"max(10^8/q,200+7.5*10^7/q)",'
            '"odd_height":"max(10^8/q,200+3.75*10^7/q)",'
            '"q1_source_campaign":"platt-trudgian-rh-3e12",'
            '"source_evidence":"PlattTheorem71SourceEvidence"}'
        )
        domain = (
            '{"characters":"all-primitive-dirichlet-characters",'
            '"claim":"platt-theorem-7-1-dirichlet-verification",'
            '"modulus_lower":1,"modulus_upper":400000,'
            '"parity_branches":["even","odd"],'
            '"zero_imag_bound":"absolute-source-height",'
            '"zero_real_lower_exclusive":0,"zero_real_upper_exclusive":1}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "plattTrudgianFiniteRHProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-platt-trudgian-finite-rh\n"
            "producer=tg_verifier/platt_zeta_campaign.py\n"
            "semantics=fixed-index-flint-platt-turing-chunked-zero-isolation-and-global-count\n"
            "source-height=3000175332800\n"
            "source-multiplicity-count=12363153437138\n"
            "source-realization=external-endpoint-enclosures-hardy-z-bridge-and-turing-count\n"
            "output=false-or-true-with-source-evidence"
        )
        input_text = (
            '{"campaign":"platt-trudgian-rh-3e12",'
            '"multiplicity_count":12363153437138,'
            '"source_height":3000175332800}'
        )
        parameters = (
            '{"flint_commit":"8d5454b96761fafe4d5a9da76a369a602f500f49",'
            '"flint_threads":1,"flint_version":"3.6.0",'
            '"micro_batch":4096,"precision_bits":96,'
            '"shard_count":1236316,"shard_span":10000000}'
        )
        domain = (
            '{"claim":"platt-trudgian-finite-rh-source",'
            '"imag_lower_exclusive":0,'
            '"multiplicity_count":12363153437138,'
            '"real_lower_exclusive":0,"real_upper_exclusive":1,'
            '"source_height":3000175332800}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.platt-trudgian-finite-rh.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "helfgottPlattGoldbachProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-helfgott-platt-finite-goldbach\n"
            "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_campaign.py\n"
            "semantics=complete-binary-goldbach-plus-checked-prime-ladder-source-evidence\n"
            "binary-campaign=goldbach-gpu-hardened-production-65536-leaf-v2\n"
            "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n"
            "binary-source-identity=9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\n"
            "ladder-campaign=tg_goldbach_ladder_parallel_campaign_v1\n"
            "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n"
            "ladder-native-source=02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6\n"
            "combined-artifact=tg_goldbach_gpu_plus_ladder_result_v1\n"
            "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n"
            "source-realization=external-branch-artifacts-to-checked-source-evidence\n"
            "output=false-or-true-with-checked-source-evidence"
        )
        input_text = (
            '{"binary_artifact_kind":"sparkinterval.goldbach-gpu-aggregate.v1",'
            '"binary_campaign":"goldbach-gpu-hardened-production-65536-leaf-v2",'
            '"binary_source_identity_sha256":'
            '"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55",'
            '"campaign":"helfgott-platt-goldbach-gpu-v1",'
            '"combined_artifact_kind":"tg_goldbach_gpu_plus_ladder_result_v1",'
            '"ladder_artifact_kind":"tg_goldbach_ladder_parallel_aggregate_v1",'
            '"ladder_campaign":"tg_goldbach_ladder_parallel_campaign_v1",'
            '"ladder_native_source_sha256":'
            '"02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6"}'
        )
        parameters = (
            '{"binary_even_count":1999999999999999999,'
            '"binary_leaves_per_group":8,"binary_shards":65536,'
            '"h100_groups":8192,"ladder_cpu_groups":320,'
            '"ladder_maximum_gap":4000000000000000000,'
            '"ladder_proth_exponent":52,"ladder_range_count":492700,'
            '"ladder_sieve_bound":16000}'
        )
        domain = (
            '{"binary_even_lower":4,'
            '"binary_even_upper":4000000000000000000,'
            '"claim":"helfgott-platt-theorem-4-1-source",'
            '"source_lower":7,'
            '"source_upper":8875694145621773516800000000000}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.helfgott-platt-finite-goldbach.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "goldbach10Pow27ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-finite-below-10pow27\n"
            "producer=tg_verifier/goldbach_gpu_campaign.py+tg_verifier/goldbach_native_ladder.py+tg_verifier/goldbach_10pow27_campaign.py+tools/tg_goldbach_10pow27_finalizer.py\n"
            "semantics=complete-word-indexed-lowered-binary-goldbach-coverage-plus-checked-n45-prime-ladder-evidence\n"
            "binary-campaign=goldbach-gpu-analytic-10pow27-production-65536-leaf-v1\n"
            "binary-artifact=sparkinterval.goldbach-gpu-aggregate.v1\n"
            "binary-source-identity=9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\n"
            "ladder-campaign=analytic_10pow27\n"
            "ladder-artifact=tg_goldbach_ladder_parallel_aggregate_v1\n"
            "combined-artifact=tg_goldbach_10pow27_gpu_plus_ladder_result_v1\n"
            "finalizer-target=azure-sevsnp-cpu-after-h100-binary-and-cpu-ladder-branches\n"
            "source-realization=external-branch-artifacts-to-exact-word-campaign-and-checked-ladder-evidence\n"
            "output=false-or-true-with-checked-campaign-evidence"
        )
        input_text = (
            '{"binary_artifact_kind":"sparkinterval.goldbach-gpu-aggregate.v1",'
            '"binary_campaign":"goldbach-gpu-analytic-10pow27-production-65536-leaf-v1",'
            '"binary_source_identity_sha256":"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55",'
            '"campaign":"ternary-goldbach-finite-below-10pow27-v1",'
            '"combined_artifact_kind":"tg_goldbach_10pow27_gpu_plus_ladder_result_v1",'
            '"ladder_artifact_kind":"tg_goldbach_ladder_parallel_aggregate_v1",'
            '"ladder_campaign":"analytic_10pow27",'
            '"semantic_target_inclusive":1000000000000000000000000000}'
        )
        parameters = (
            '{"binary_even_count":15624999999999999,'
            '"binary_leaves_per_group":8,"binary_shards":65536,'
            '"h100_groups":8192,"ladder_maximum_gap":31250000000000000,'
            '"ladder_proth_exponent":45,"ladder_range_count":7106,'
            '"ladder_range_width":140737488355328000000000,'
            '"ladder_scheduled_endpoint":1000080592252960768000000000,'
            '"ladder_sieve_bound":16000}'
        )
        domain = (
            '{"binary_even_lower":4,'
            '"binary_even_upper":31250000000000000,'
            '"claim":"ternary-goldbach-finite-below-10pow27",'
            '"source_lower":7,'
            '"source_upper":1000000000000000000000000000}'
        )
        algorithm_id = (
            "sparkinterval.ternary-goldbach.finite-below-10pow27.v1"
        )
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "helfgottSqrt218ProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=ternary-goldbach-sqrt218-finite\n"
            "bound=2000000\n"
            "prime-roster=complete-eratosthenes-and-lucas-pratt-witnesses\n"
            "prime-powers=all-powers-p^k-with-k-positive-and-p^k-at-most-bound\n"
            "log-enclosure=scale-2^48-seed-30-rational-ladder-depth-14\n"
            "reciprocal-sqrt=scale-2^30-rational-lower-and-upper-bounds\n"
            "scan=ordered-prime-power-fixed-point-prefix-with-every-head-guard\n"
            "terminal=exact-final-state-and-endpoint-abel-anchor\n"
            "result=canonical-ascii-true-only-after-independent-full-archive-replay"
        )
        input_text = (
            '{"bound":2000000,'
            '"claim_id":"helfgott-sqrt218-finite-v1",'
            '"expected":{'
            '"anchor_slack":2134933357595048382226455716,'
            '"final_psi_lower":562949761260501289147,'
            '"final_weighted_upper":854091852238662506255905837,'
            '"fixed_scan_sha256":'
            '"0eda447334b59b886d3d2b70e3aed3a8375823dbc1180e190e0ad67517e9c559",'
            '"layout_sha256":'
            '"c7a559cf7dd1a38c97e73b224a4021a44c62f68d2ad17f1a50a31f72c1ca1055",'
            '"minimum_head_n":6397,'
            '"minimum_head_slack":77167896433454640411789476,'
            '"power_event_count":149235,'
            '"pratt_sha256":'
            '"46b67778699d196eec624ba71f8fc07de9d0218afbd0a0930c2113e37ddbfd07",'
            '"prime_count":148933,"proper_power_count":302,'
            '"reused_prime_count":115408,"tail_prime_count":33525},'
            '"kind":"sparkinterval.sqrt218-finite-run-input.v1",'
            '"lean_claim":'
            '"SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim",'
            '"log_depth":14,"log_scale":281474976710656,'
            '"reciprocal_scale":1073741824,"schema_version":1,'
            '"source_statement":'
            '"For the complete prime and prime-power rosters through 2,000,000, '
            'the directed scale-2^48 prime-log ladder and scale-2^30 reciprocal-'
            'square-root scan satisfy every integer head guard in Helfgott (2.18) '
            'and its endpoint Abel anchor, with the exact pinned final state."}'
        )
        parameters = (
            '{"independent_replay":true,"log_depth":14,'
            '"log_scale":281474976710656,"log_seed_count":30,'
            '"reciprocal_scale":1073741824}'
        )
        domain = (
            '{"claim":"helfgott-2-18-finite-head-and-anchor",'
            '"head_lower":1,"head_upper":2000000,"strict":true}'
        )
        algorithm_id = "sparkinterval.ternary-goldbach.sqrt218-finite.v1"
        result = "true"
        deployment = {
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == SQRT218_FIXED_V2_INVOCATION:
        pins = _require_sqrt218_fixed_v2_reviewed_pins(
            sqrt218_fixed_v2_reviewed_pins
        )
        definition = (
            "sparkinterval.registered-algorithm.v2\n"
            "name=ternary-goldbach-sqrt218-fixed-v2\n"
            "input=exact-reviewed-SQ218V2-binary-certificate\n"
            "input-binding=statement-input-sha256-plus-reviewed-byte-length\n"
            "decoder=canonical-big-endian-fixed-width-exact-eof\n"
            "semantics=complete-V2-roster-layout-log-event-fold-and-anchor-check\n"
            "result=false-or-canonical-ascii-exact-hex-envelope-of-120-byte-SQ218R2-record\n"
            "success-binding=result-state-input-length-and-input-sha256"
        )
        parameters = (
            '{"certificate_format":"SQ218V2","certificate_version":2,'
            '"result_bytes":120,"result_envelope":"canonical-lower-hex",'
            '"result_format":"SQ218R2"}'
        )
        domain = (
            '{"claim":"helfgott-2-18-finite-head-and-anchor",'
            '"head_lower":1,"head_upper":2000000,'
            '"input_identity":"reviewed-byte-length-and-sha256",'
            '"strict":true}'
        )
        digest = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
        return {
            "algorithm_id": sqrt218_fixed_v2_receipt.ALGORITHM_ID,
            "algorithm_hash": digest(definition),
            "input_hash": pins["certificate_sha256"],
            "parameters_hash": digest(parameters),
            "domain_hash": digest(domain),
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }
    elif invocation == "plattStrongerRangeLiveProductionV1":
        definition = (
            "sparkinterval.registered-algorithm.v1\n"
            "name=platt-stronger-range-live\n"
            "producer=leancompcert\n"
            "program=Ports.ArraySegSieve.mobiusLiveProgram\n"
            "reduced-family=MathExtras.Reductions.PlattStrongerRangeNatFamily\n"
            "range=[5,7727068586]\n"
            "windows=10\n"
            "manifest-sha256=6c67c2a900889087d3c1f88eed9caecf4e08ba0c40ab23e83ef316ff0d7ef0a9\n"
            "manifest-bytes=4528\n"
            "compcert-version=3.17\n"
            "compcert-target=x86_64-linux\n"
            "link=static-freestanding-no-libc\n"
            "semantics=AProgram.evalCC_compile\n"
            "success=every-window-exit-status-zero\n"
            "output=false-or-true\n"
        )
        input_text = (
            '{"campaign":"platt-stronger-range-live-v1",'
            '"campaign_manifest_sha256":'
            '"6c67c2a900889087d3c1f88eed9caecf4e08ba0c40ab23e83ef316ff0d7ef0a9",'
            '"range_hi":7727068586,"range_lo":5}'
        )
        parameters = (
            '{"accumulator_bits":78,"budget":"ceil(n/2^17)+1",'
            '"chain":"two-limb-carry","test":"every-integer",'
            '"threshold":"floor(2^78/ceil(sqrt(n+1)))"}'
        )
        domain = (
            '{"claim":"platt-stronger-little-mertens-live",'
            '"source_lower":5,"source_upper":7727068586}'
        )
        algorithm_id = "sparkinterval.leancompcert.platt-stronger-range-live.v1"
        result = "true"
        # Target-polymorphic, like ``cubicSumDivThree20000V1``.  The real
        # deployment restriction for this campaign is the pinned Intel TDX
        # enclave image on the Phala path, which does not go through the
        # ``RunStatement`` target/trust enumeration at all.
        deployment = {}
    else:
        raise ReceiptError(f"unsupported registered invocation: {invocation!r}")
    digest = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "algorithm_id": algorithm_id,
        "algorithm_hash": digest(definition),
        "input_hash": digest(input_text),
        "parameters_hash": digest(parameters),
        "domain_hash": digest(domain),
        "result": result,
        "output_hash": digest(result),
        **deployment,
    }


def registered_invocation_backend(invocation: str) -> str | None:
    """Return a mandatory backend when it is part of invocation identity."""

    if invocation == "cubicSumDivThree20000V1":
        return None
    if invocation == "h100FormalPtxConstantOneV1":
        return "azure_ncc40ads_h100_v5"
    if invocation == "cdemTableAbelProductionV2":
        return "azure_sevsnp_cpu"
    if invocation == "hurstSharedFourResidualProductionV2":
        return "azure_sevsnp_cpu"
    if invocation == "ch25PsiLemma92ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "ramareZunigaLemma62ProductionV1":
        return "azure_ncc40ads_h100_v5"
    if invocation == "helfgottProp1224ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "ch25A7BoundaryProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "plattHead2e4ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "plattDirichletTheorem71ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "plattTrudgianFiniteRHProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "helfgottPlattGoldbachProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "goldbach10Pow27ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == "helfgottSqrt218ProductionV1":
        return "azure_sevsnp_cpu"
    if invocation == SQRT218_FIXED_V2_INVOCATION:
        return "azure_sevsnp_cpu"
    if invocation == "plattStrongerRangeLiveProductionV1":
        # No mandatory backend: the campaign's identity is its pinned enclave
        # image on the Phala TDX path, not a trusted-compute backend name.
        return None
    raise ReceiptError(f"unsupported registered invocation: {invocation!r}")


def validate_registered_invocation(
    receipt: dict,
    invocation: str,
    *,
    sqrt218_fixed_v2_reviewed_pins: dict[str, Any] | None = None,
) -> None:
    """Check the receipt's literal identity before emitting formal aliases."""

    expected = registered_invocation_expected(
        invocation,
        sqrt218_fixed_v2_reviewed_pins=sqrt218_fixed_v2_reviewed_pins,
    )
    required_backend = registered_invocation_backend(invocation)
    if required_backend is not None and receipt["backend"] != required_backend:
        raise ReceiptError(
            f"receipt does not match {invocation}: wrong backend"
        )
    claim = receipt["claim"]
    for field, value in expected.items():
        if claim[field] != value:
            raise ReceiptError(
                f"receipt does not match {invocation}: wrong claim {field}"
            )
    if invocation == SQRT218_FIXED_V2_INVOCATION:
        pins = _require_sqrt218_fixed_v2_reviewed_pins(
            sqrt218_fixed_v2_reviewed_pins
        )
        try:
            sqrt218_fixed_v2_receipt.validate_receipt_only_binding(
                receipt, pins
            )
        except sqrt218_fixed_v2_receipt.FixedV2ReceiptError as exc:
            raise ReceiptError(
                f"receipt does not match {invocation}: {exc}"
            ) from exc


def validate_bound_registered_results(
    receipt: dict,
    *,
    sqrt218_fixed_v2_reviewed_pins: dict[str, Any] | None = None,
) -> None:
    """Reject a wrong result for any complete closed-invocation identity.

    This runs during source-registry admission, not merely when a convenience
    consumer is generated.  Therefore a Lean author cannot bypass the result
    check and project ``ProducedOutcome.registered`` directly from a receipt
    carrying the right registered identity but different output bytes.
    """

    claim = receipt["claim"]
    for invocation in REGISTERED_INVOCATIONS:
        if (
            invocation == SQRT218_FIXED_V2_INVOCATION
            and sqrt218_fixed_v2_reviewed_pins is None
        ):
            # Dynamic fixed-V2 output admission is impossible without the
            # exact reviewed receipt/certificate pins.  The source-admission
            # function below likewise fails closed when they are absent.
            continue
        expected = registered_invocation_expected(
            invocation,
            sqrt218_fixed_v2_reviewed_pins=sqrt218_fixed_v2_reviewed_pins,
        )
        required_backend = registered_invocation_backend(invocation)
        identity_fields = tuple(
            field for field in expected if field not in ("result", "output_hash")
        )
        if (
            (required_backend is None or receipt["backend"] == required_backend)
            and all(claim[field] == expected[field] for field in identity_fields)
        ):
            if invocation == SQRT218_FIXED_V2_INVOCATION:
                validate_registered_invocation(
                    receipt,
                    invocation,
                    sqrt218_fixed_v2_reviewed_pins=(
                        sqrt218_fixed_v2_reviewed_pins
                    ),
                )
                continue
            for field in ("result", "output_hash"):
                if claim[field] != expected[field]:
                    raise ReceiptError(
                        f"receipt binds {invocation} but has wrong claim {field}"
                    )


def validate_source_admitted_registered_invocation(
    receipt: dict,
    *,
    sqrt218_fixed_v2_reviewed_pins: dict[str, Any] | None = None,
) -> str:
    """Require an exact match to one currently closed formal invocation.

    Registry membership is durable source authority.  Rejecting unknown
    identities prevents a later extension of the closed Lean registry from
    retroactively giving old generic receipts new formal semantics.
    """

    matches = []
    for invocation in REGISTERED_INVOCATIONS:
        try:
            validate_registered_invocation(
                receipt,
                invocation,
                sqrt218_fixed_v2_reviewed_pins=(
                    sqrt218_fixed_v2_reviewed_pins
                ),
            )
        except ReceiptError:
            continue
        matches.append(invocation)
    if len(matches) != 1:
        raise ReceiptError(
            "source registry requires exactly one current closed registered "
            f"invocation; found {len(matches)}"
        )
    return matches[0]


def generate(
    receipt: dict,
    namespace: str,
    registered_invocation: str | None = None,
    *,
    sqrt218_fixed_v2_reviewed_pins: dict[str, Any] | None = None,
) -> str:
    if IDENTIFIER.fullmatch(namespace) is None:
        raise ReceiptError("namespace must be one simple Lean identifier")
    if registered_invocation is not None:
        validate_registered_invocation(
            receipt,
            registered_invocation,
            sqrt218_fixed_v2_reviewed_pins=(
                sqrt218_fixed_v2_reviewed_pins
            ),
        )
    q = lean_string
    receipt_hash = receipt["receipt_sha256"]
    registry_entry = "importedTrustedComputeRun_" + receipt_hash
    lookup_theorem = "lookup_" + registry_entry
    artifacts = receipt["claim"]["artifacts"]
    statement_digest_values = [
        receipt["claim"][field]
        for field in (
            "algorithm_hash",
            "input_hash",
            "parameters_hash",
            "domain_hash",
            "output_hash",
            "nonce",
            "target_profile_hash",
            "trust_profile_hash",
        )
    ] + [
        artifacts[field]
        for field in (
            "source_tree_hash",
            "host_executable_hash",
            "device_cubin_hash",
            "kernel_manifest_hash",
        )
    ]
    bindings = receipt["bindings"]
    hashes = receipt["evidence_hashes"]
    evidence_digest_values = [
        receipt_hash,
        bindings["run_bundle_sha256"],
        bindings["wire_statement_sha256"],
        hashes["platform_evidence_sha256"],
        hashes["azure_maa_token_sha256"],
        hashes["amd_snp_report_sha256"],
        hashes["tpm_quote_sha256"],
        hashes["tpm_event_log_sha256"],
        receipt["verifier"]["policy_sha256"],
        receipt["verifier"]["artifact_sha256"],
        bindings["start_challenge_sha256"],
        bindings["result_binding_sha256"],
    ]
    # The CPU device-CUBIN field is the protocol's canonical N/A digest.  It
    # needs a syntax certificate, but unlike every other statement digest it
    # must not satisfy ``trustedComputeRequiredDigest``.
    statement_required_digest_values = [
        value
        for value in statement_digest_values
        if value != artifacts["device_cubin_hash"]
    ] + (
        [artifacts["device_cubin_hash"]]
        if artifacts["device_cubin_hash"]
        != "b272852e69f12bacf5fbb095bc43233bfd184f238a86f5bb66d85772b849d02b"
        else []
    )
    required_digest_values = sorted(
        set(statement_required_digest_values + evidence_digest_values)
    )
    required_digest_theorems = {
        value: "requiredDigest_" + canonical_hex_certificate_name(value)
        for value in required_digest_values
    }
    required_digest_source = "\n\n".join(
        f'''/-- This reviewed digest is canonical and is neither a zero nor
the protocol's not-applicable marker. -/
theorem {required_digest_theorems[value]} :
    trustedComputeRequiredDigest
      {canonical_hex_certificate_name(value)}.value = true :=
  trustedComputeRequiredDigest_of_canonical
    {canonical_hex_certificate_name(value)}.canonical (by rfl) (by rfl)'''
        for value in required_digest_values
    )
    statement_simp = ",\n      ".join(
        required_digest_theorems[value]
        for value in sorted(set(statement_required_digest_values))
    )
    device_certificate = canonical_hex_certificate_name(
        artifacts["device_cubin_hash"]
    )
    if statement_simp:
        statement_simp += ",\n      "
    statement_simp += device_certificate + ".canonical"
    evidence_simp = ",\n      ".join(
        required_digest_theorems[value]
        for value in sorted(set(evidence_digest_values))
    )
    signature_certificate = canonical_hex_certificate_name(
        receipt["signature"]["value_hex"]
    )
    registered_source = ""
    if registered_invocation in REGISTERED_INVOCATIONS:
        registered_binding_values = {
            receipt["receipt_sha256"],
            *(
                receipt["claim"][field]
                for field in (
                    "algorithm_hash",
                    "input_hash",
                    "parameters_hash",
                    "domain_hash",
                    "target_profile_hash",
                    "trust_profile_hash",
                )
            ),
            *artifacts.values(),
        }
        registered_value_theorems = ",\n      ".join(
            canonical_hex_certificate_name(value) + "_value"
            for value in sorted(registered_binding_values)
        )
        if registered_invocation == "cubicSumDivThree20000V1":
            registered_source = f'''
/-- Registry-fixed operational semantics recovered from the accepted run. -/
theorem registeredRun :
    RegisteredInvocation.cubicSumDivThree20000V1.Runs
      certificate.statement.result :=
  producedOutcome.registered .cubicSumDivThree20000V1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact returned bytes together with the ordinary Lean arithmetic theorem. -/
theorem applicationResult :
    certificate.statement.result = "13334666700000000" ∧
      RegisteredAlgorithm.cubicSumDivThree 20000 =
        (13334666700000000 : ℚ) :=
  RegisteredInvocation.cubicSumDivThree20000V1_result registeredRun

/-- Application-level theorem projected after the one trusted run bridge. -/
theorem exactMathematicalResult :
    RegisteredAlgorithm.cubicSumDivThree 20000 =
      (13334666700000000 : ℚ) :=
  applicationResult.2

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "h100FormalPtxConstantOneV1":
            registered_source = f'''
/-- Axiom-free identity between the signed PTX definition and formal emitter. -/
theorem formalProgramIdentity :=
  h100FormalPtxConstantOnePTX_eq_formalEmitter

/-- Registry-fixed H100 execution semantics recovered from the accepted run. -/
theorem registeredRun :
    RegisteredInvocation.h100FormalPtxConstantOneV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .h100FormalPtxConstantOneV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- The reusable formal pilot theorem adds exact decoding and PTX identity to
the sole trusted run projection. -/
theorem certifiedApplication :=
  h100FormalPtxConstantOne_result_of_run registeredRun

/-- Exact returned manifest and its ordinary Lean binary64 interpretation. -/
theorem applicationResult :
    certificate.statement.result =
        RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) :=
  ⟨certifiedApplication.1, certifiedApplication.2.1,
    certifiedApplication.2.2.1⟩

/-- Application-level theorem projected after the one trusted run bridge. -/
theorem exactMathematicalResult :
    certificate.statement.result =
        RegisteredAlgorithm.h100FormalPtxConstantOneOutput ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) ∧
      Binary64.decodeFinite 0x3ff0000000000000 = some (1 : ℚ) :=
  applicationResult

#print axioms registeredRun
#print axioms certifiedApplication
#print axioms applicationResult
#print axioms exactMathematicalResult
#print axioms formalProgramIdentity
'''
        elif registered_invocation == "cdemTableAbelProductionV2":
            registered_source = f'''
/-- Registry-fixed CDEM execution semantics recovered from the accepted run. -/
theorem registeredRun :
    RegisteredInvocation.cdemTableAbelProductionV2.Runs
      certificate.statement.result :=
  producedOutcome.registered .cdemTableAbelProductionV2 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact source-shaped two-conjunct CDEM Abel result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim :=
  RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim
    registeredRun (by rfl)

/-- Application-level theorem projected after the one trusted run bridge. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "hurstSharedFourResidualProductionV2":
            registered_source = f'''
/-- Registry-fixed V2 Hurst execution semantics recovered from the accepted
full-range CPU run. -/
theorem registeredRun :
    RegisteredInvocation.hurstSharedFourResidualProductionV2.Runs
      certificate.statement.result :=
  producedOutcome.registered .hurstSharedFourResidualProductionV2 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- All five ordinary real inequalities for the four shared Hurst-family
source atoms. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.RealSourceClaims :=
  RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.RealSourceClaims :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "ch25PsiLemma92ProductionV1":
            registered_source = f'''
/-- Registry-fixed CH25 psi execution semantics recovered from the accepted
gap-free, two-pass CPU run. -/
theorem registeredRun :
    RegisteredInvocation.ch25PsiLemma92ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .ch25PsiLemma92ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact paper-shaped CH25 Lemma 9.2 real-variable result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim :=
  RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "ramareZunigaLemma62ProductionV1":
            registered_source = f'''
/-- Registry-fixed Ramaré--Zúñiga Lemma 6.2 execution semantics recovered
from the accepted gap-free, directed Q32 H100 campaign. -/
theorem registeredRun :
    RegisteredInvocation.ramareZunigaLemma62ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .ramareZunigaLemma62ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact paper-shaped Ramaré--Zúñiga Lemma 6.2 real-variable result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceClaim :=
  RegisteredInvocation.ramareZunigaLemma62ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.R2StarSourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "helfgottProp1224ProductionV1":
            registered_source = f'''
/-- Registry-fixed Proposition 12.2.4 execution semantics recovered from the
accepted gap-free directed MPFR/GMP CPU run. -/
theorem registeredRun :
    RegisteredInvocation.helfgottProp1224ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .helfgottProp1224ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact source-shaped Proposition 12.2.4 finite-computation claim. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceClaim :=
  RegisteredInvocation.helfgottProp1224ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.Prop1224SourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "ch25A7BoundaryProductionV1":
            registered_source = f'''
/-- Registry-fixed CH25 Lemma A.7 execution semantics recovered from the
accepted pinned FLINT/Arb CPU replay. -/
theorem registeredRun :
    RegisteredInvocation.ch25A7BoundaryProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .ch25A7BoundaryProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact source-shaped CH25 Lemma A.7 boundary result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "plattHead2e4ProductionV1":
            registered_source = f'''
/-- Registry-fixed Platt-head execution semantics recovered from the accepted
exact height-20,000 FLINT/Q128 CPU replay. -/
theorem registeredRun :
    RegisteredInvocation.plattHead2e4ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .plattHead2e4ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Literal Q128 source table, its exact included-row commitment, and the
multiplicity-preserving Platt-head enumeration. -/
theorem applicationResult :
    SparkInterval.Generated.PlattHeadQ128.table.commitment =
        RegisteredAlgorithm.plattHead2e4IncludedQ128RowsCommitment ∧
      SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128SourceClaim
        SparkInterval.Generated.PlattHeadQ128.table :=
  RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream table adapter. -/
theorem exactMathematicalResult :
    SparkInterval.Generated.PlattHeadQ128.table.commitment =
        RegisteredAlgorithm.plattHead2e4IncludedQ128RowsCommitment ∧
      SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128SourceClaim
        SparkInterval.Generated.PlattHeadQ128.table :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "plattDirichletTheorem71ProductionV1":
            registered_source = f'''
/-- Registry-fixed Platt Dirichlet execution semantics recovered from the
accepted source-wide CPU finalizer. -/
theorem registeredRun :
    RegisteredInvocation.plattDirichletTheorem71ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .plattDirichletTheorem71ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact two-branch source proposition of Platt's Dirichlet Theorem 7.1. -/
theorem applicationResult :
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification :=
  RegisteredInvocation.plattDirichletTheorem71ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.Dirichlet.PlattTheorem71DirichletVerification :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "plattTrudgianFiniteRHProductionV1":
            registered_source = f'''
/-- Registry-fixed PT21 finite-RH execution semantics recovered from the
accepted exact-height FLINT CPU campaign. -/
theorem registeredRun :
    RegisteredInvocation.plattTrudgianFiniteRHProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .plattTrudgianFiniteRHProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact source-shaped PT21 positive-height finite-RH result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim :=
  RegisteredInvocation.plattTrudgianFiniteRHProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "helfgottPlattGoldbachProductionV1":
            registered_source = f'''
/-- Registry-fixed finite Goldbach execution semantics recovered from the
accepted CPU finalizer for the pinned binary-H100 and CPU-ladder campaigns. -/
theorem registeredRun :
    RegisteredInvocation.helfgottPlattGoldbachProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .helfgottPlattGoldbachProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact source-shaped finite Helfgott--Platt three-prime result. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.SourceClaim :=
  RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "goldbach10Pow27ProductionV1":
            registered_source = f'''
/-- Registry-fixed lowered finite-Goldbach execution semantics recovered from
the accepted CPU finalizer for the exact H100 and n=45 ladder aggregates. -/
theorem registeredRun :
    RegisteredInvocation.goldbach10Pow27ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .goldbach10Pow27ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact finite three-prime result through `10^27`. -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics.SourceClaim :=
  RegisteredInvocation.goldbach10Pow27ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "helfgottSqrt218ProductionV1":
            registered_source = f'''
/-- Registry-fixed Sqrt218 execution semantics recovered from the accepted
independent Azure CPU/SEV-SNP archive replay. -/
theorem registeredRun :
    RegisteredInvocation.helfgottSqrt218ProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .helfgottSqrt218ProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact bounded head-and-anchor proposition used in Helfgott (2.18). -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim :=
  RegisteredInvocation.helfgottSqrt218ProductionV1_sourceClaim
    registeredRun (by rfl)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == SQRT218_FIXED_V2_INVOCATION:
            registered_source = f'''
/-- Registry-fixed Sqrt218 fixed-V2 execution semantics recovered from the
accepted Azure CPU/SEV-SNP run.  The registered relation binds the exact raw
certificate bytes, reviewed byte length and SHA-256, strict decoder, complete
checker result, and the full canonical 120-byte native result record. -/
theorem registeredRun :
    RegisteredInvocation.helfgottSqrt218FixedProductionV2.Runs
      certificate.statement.result :=
  producedOutcome.registered .helfgottSqrt218FixedProductionV2 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sqrt218FixedV2AcceptedResultCheck,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      reviewedSqrt218FixedV2DeploymentCheck,
      reviewedSqrt218FixedV2ReceiptCheck,
      reviewedProductionDeploymentCheck,
      reviewedProductionReceiptCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      helfgottSqrt218FixedV2ProductionDeployment,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- Exact bounded head-and-anchor proposition used in Helfgott (2.18). -/
theorem applicationResult :
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim :=
  RegisteredInvocation.helfgottSqrt218FixedProductionV2_sourceClaim
    registeredRun (by decide)

/-- Stable application-level alias consumed by the downstream source adapter. -/
theorem exactMathematicalResult :
    SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
        elif registered_invocation == "plattStrongerRangeLiveProductionV1":
            registered_source = f'''
/-- Registry-fixed execution semantics recovered from the accepted run. -/
theorem registeredRun :
    RegisteredInvocation.plattStrongerRangeLiveProductionV1.Runs
      certificate.statement.result :=
  producedOutcome.registered .plattStrongerRangeLiveProductionV1 (by
    simp [RegisteredInvocation.certificateBindingCheck,
      RegisteredInvocation.receiptCheck,
      RegisteredInvocation.statementCheck,
      RegisteredInvocation.resultCheck,
      RegisteredInvocation.ResultAllowed,
      RegisteredInvocation.sourceBindingDiagnosticCheck,
      RegisteredInvocation.inputHashDiagnosticCheck,
      RegisteredInvocation.canonicalInput,
      RegisteredAlgorithm.algorithmHashDiagnosticCheck,
      RegisteredAlgorithm.metadataHashesDiagnosticCheck,
      RegisteredAlgorithm.canonicalDefinition,
      RegisteredAlgorithm.canonicalParameters,
      RegisteredAlgorithm.canonicalDomain,
      RegisteredInvocation.artifactCheck,
      RegisteredInvocation.deploymentCheck,
      RegisteredInvocation.canonicalInputHash,
      RegisteredAlgorithm.algorithmId,
      RegisteredAlgorithm.algorithmHash,
      RegisteredAlgorithm.canonicalParametersHash,
      RegisteredAlgorithm.canonicalDomainHash,
      RunClaim.toStatement, certificate, statement, claim, evidence,
      {registry_entry},
      {registered_value_theorems}])

/-- **This campaign's registered relation has no mathematical content, and
neither does this theorem.**

leancompcert proves that *compilation* is faithful -- the Lean `Program`, the
C it lowers to, and the CompCert-produced x86_64 all agree.  It does not prove
that `mobiusLiveProgram` computes `Σ_(m≤n) μ(m)/m`, nor that a zero exit
status means the little-Mertens threshold inequality holds.  So the strongest
honest conclusion available from an accepted run is the canonical result
language, which is exactly what is stated here.

The mathematical claim `|Σ_(m≤n) μ(m)/m| ≤ 1/(2√(n+1))` on `[5, 7727068586]`
requires a separate, explicitly stated realisation premise on the attestation
path.  It is deliberately *not* derived here, and the name
`exactMathematicalResult` below is a fixed generator alias rather than a claim
that a mathematical result was obtained. -/
theorem applicationResult :
    certificate.statement.result = "false" ∨
      certificate.statement.result = "true" :=
  RegisteredInvocation.resultAllowed_of_runs registeredRun

/-- Stable generator alias.  See the warning on `applicationResult`: this is
the result language, not a theorem about Möbius partial sums. -/
theorem exactMathematicalResult :
    certificate.statement.result = "false" ∨
      certificate.statement.result = "true" :=
  applicationResult

#print axioms registeredRun
#print axioms applicationResult
#print axioms exactMathematicalResult
'''
    elif registered_invocation is not None:
        raise ReceiptError(
            f"unsupported registered invocation: {registered_invocation!r}"
        )
    registered_import = {
        "h100FormalPtxConstantOneV1":
            "import SparkInterval.Execution.RegisteredH100FormalPtxPilot\n",
        "cdemTableAbelProductionV2":
            "import SparkInterval.Execution.RegisteredCDEMAbelCertificate\n",
        "hurstSharedFourResidualProductionV2":
            "import SparkInterval.Execution.RegisteredHurstSharedCertificate\n",
        "ch25PsiLemma92ProductionV1":
            "import SparkInterval.Execution.RegisteredPsiLemma92Certificate\n",
        "ramareZunigaLemma62ProductionV1":
            "import SparkInterval.Execution.RegisteredR2StarCertificate\n",
        "helfgottProp1224ProductionV1":
            "import SparkInterval.Execution.RegisteredProp1224Certificate\n",
        "ch25A7BoundaryProductionV1":
            "import SparkInterval.Execution.RegisteredA7BoundaryCertificate\n",
        "plattHead2e4ProductionV1":
            "import SparkInterval.Execution.RegisteredZetaHeadCertificate\n",
        "plattDirichletTheorem71ProductionV1":
            "import SparkInterval.Execution.RegisteredPlattTheorem71Certificate\n",
        "plattTrudgianFiniteRHProductionV1":
            "import SparkInterval.Execution.RegisteredZetaRHCertificate\n",
        "helfgottPlattGoldbachProductionV1":
            "import SparkInterval.Execution.RegisteredGoldbachCertificate\n",
        "goldbach10Pow27ProductionV1":
            "import SparkInterval.Execution.RegisteredGoldbach10Pow27Certificate\n",
        "helfgottSqrt218ProductionV1":
            "import SparkInterval.Execution.RegisteredSqrt218Certificate\n",
        SQRT218_FIXED_V2_INVOCATION:
            "import SparkInterval.Execution.RegisteredSqrt218FixedV2Certificate\n",
        # No `Registered...Certificate` adapter exists for this campaign, and
        # none should: there is no source-claim theorem to adapt.  The closed
        # registry itself is the only extra module the generated file needs.
        "plattStrongerRangeLiveProductionV1":
            "import SparkInterval.Execution.RegisteredAlgorithm\n",
    }.get(registered_invocation, "")
    return f'''import SparkInterval.Audit.TrustedComputeCertificates
{registered_import}

/-! Generated by tools/generate_trusted_compute_lean.py.

The generator verified the source-pinned verifier signature before producing
this file.  Lean acceptance is deliberately based on the exact receipt hash
and literal evidence in `TrustedComputeRegistry`, not on a public evidence
constructor or a cryptographic oracle.  Small structural proof terms connect
the registry lookup to the policy without expanding the whole receipt through
`decide_cbv`.  The final `producedOutcome` theorem crosses exactly the
repository's one named trusted-execution axiom.  This module uses neither FFI
nor `native_decide`.
-/

set_option autoImplicit false
set_option maxHeartbeats 0
set_option maxRecDepth 100000

namespace SparkInterval.GeneratedTrustedCompute.{namespace}

open SparkInterval.Execution

/-- Exact signed evidence source-pinned in the reviewed registry. -/
def evidence : TrustedComputeEvidence := {registry_entry}

/-- The literal signed claim carried by `evidence`. -/
def claim : RunClaim := evidence.claim

def statement : RunStatement := claim.toStatement

def certificate : RunCertificate := {{
  statement := statement
  attestation := .trustedCompute {q(receipt_hash)}
}}

{required_digest_source}

/-- Fieldwise digest syntax, proved from small compositional registry
certificates rather than one monolithic character reduction. -/
theorem statementDigestsCanonical :
    evidence.claim.toStatement.allDigestsCanonical = true := by
  simp [RunStatement.allDigestsCanonical, isCanonicalSHA256,
    RunClaim.toStatement, evidence,
    {registry_entry},
      {statement_simp}]

/-- Canonical normalized evidence metadata from the same small certificates. -/
theorem evidenceMetadataPresent : evidence.allMetadataPresent = true := by
  simp [TrustedComputeEvidence.allMetadataPresent,
    evidence, {registry_entry}, trustedComputeVerifierKeyAllowed,
    trustedComputeAllowedVerifierKeyIds, trustedComputeAllowedVerifierProfiles,
      {evidence_simp}]

/-- The full RSA signature is composed from independently checked 16-character
chunks; the abstract append theorem avoids rescanning 768 characters here. -/
theorem signatureCanonical :
    isCanonicalRSA3072Signature evidence.signatureHex = true := by
  change SparkInterval.Certificate.isCanonicalLowerHexOfLength 768
    {signature_certificate}.value = true
  exact {signature_certificate}.canonical

/-- Kernel-checked SHA-256 binding from the exact returned UTF-8 bytes to the
output digest carried by the reviewed statement. -/
theorem resultPayloadHashBound :
    SparkInterval.Certificate.SHA256.digestString
        evidence.claim.toStatement.result =
      evidence.claim.toStatement.outputHash := by
  decide

/-- Kernel-checked challenge/wire-statement commitment carried by the signed
receipt.  The external importer checks the same equation before generation. -/
theorem challengeResultBindingBound :
    evidence.resultBindingHash = evidence.expectedResultBindingHash := by
  decide

/-- Kernel-checked closed-registry membership and complete statement binding.
Each residual goal is a small definitional fact about the one literal entry;
no bulk evaluator or native code is trusted. -/
theorem trustedComputeAccepted :
    checkTrustedCompute statement certificate.attestation = true := by
  change checkTrustedCompute evidence.claim.toStatement
    (.trustedCompute {q(receipt_hash)}) = true
  apply checkTrustedCompute_of_imported
  · exact {lookup_theorem}
  · rfl
  · rfl
  · exact statementDigestsCanonical
  · exact evidenceMetadataPresent
  · exact signatureCanonical
  · rfl
  · rfl
  · exact resultPayloadHashBound
  · exact challengeResultBindingBound
  all_goals rfl

/-- Unified certificate acceptance derived from the trusted-compute policy. -/
theorem accepted : certificate.check = true :=
  RunCertificate.check_of_trustedCompute trustedComputeAccepted

/-- The only theorem in this module that uses external execution trust. -/
theorem producedOutcome : certificate.ProducedOutcome :=
  SparkInterval.Execution.Trusted.acceptedRunCertificateForReceipt
    {q(receipt_hash)} certificate (by rfl) trustedComputeAccepted
{registered_source}

#print axioms statementDigestsCanonical
#print axioms evidenceMetadataPresent
#print axioms signatureCanonical
#print axioms resultPayloadHashBound
#print axioms challengeResultBindingBound
#print axioms trustedComputeAccepted
#print axioms accepted
#print axioms producedOutcome
#audit certificates producedOutcome

end SparkInterval.GeneratedTrustedCompute.{namespace}
'''


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--registered-invocation",
        choices=REGISTERED_INVOCATIONS,
        help="also derive the closed invocation and its application theorem",
    )
    parser.add_argument(
        "--sqrt218-fixed-v2-reviewed-pins",
        type=Path,
        help=(
            "mandatory compact reviewed pins for the dynamic fixed-V2 "
            "invocation; these restrict but never authorize the already "
            "signature-verified receipt"
        ),
    )
    parser.add_argument("--key-manifest", type=Path, default=DEFAULT_KEY_MANIFEST)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument(
        "--allow-development-key",
        action="store_true",
        help=(
            "permit development-key signature diagnostics; Lean consumer "
            "generation still requires a production-classified key"
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        path = Path(args.receipt)
        receipt = load_verified_receipt(
            path,
            key_manifest=args.key_manifest,
            public_key=args.public_key,
            allow_development_key=args.allow_development_key,
        )
        require_production_verifier(receipt, args.key_manifest)
        reviewed_pins = None
        if args.sqrt218_fixed_v2_reviewed_pins is not None:
            if args.registered_invocation != SQRT218_FIXED_V2_INVOCATION:
                raise ReceiptError(
                    "--sqrt218-fixed-v2-reviewed-pins is valid only with "
                    f"--registered-invocation {SQRT218_FIXED_V2_INVOCATION}"
                )
            reviewed_pins = (
                sqrt218_fixed_v2_receipt.load_canonical_reviewed_pins(
                    args.sqrt218_fixed_v2_reviewed_pins
                )
            )
        source = generate(
            receipt,
            args.namespace,
            args.registered_invocation,
            sqrt218_fixed_v2_reviewed_pins=reviewed_pins,
        )
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    except (
        OSError,
        BundleError,
        ReceiptError,
        sqrt218_fixed_v2_receipt.FixedV2ReceiptError,
        KeyError,
    ) as exc:
        print(f"generate_trusted_compute_lean: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
