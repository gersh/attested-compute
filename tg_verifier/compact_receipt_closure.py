# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Static audit for the ternary-Goldbach compact receipt closure matrix.

This module deliberately performs no campaign computation, certificate
replay, compiler invocation, or executable inspection.  It cross-checks the
small source catalogs and the data-independent Lean declaration surface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tg_verifier import h100_cluster


DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    DEFAULT_REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.json"
)


class CompactReceiptClosureError(ValueError):
    """The static compact-receipt closure inventory is inconsistent."""


def _reject_float(value: str) -> None:
    raise CompactReceiptClosureError(
        f"floating-point JSON is forbidden in closure inventory: {value}"
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CompactReceiptClosureError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json_strict(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompactReceiptClosureError(f"cannot load {path}: {error}") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _definition_block(source: str, name: str) -> str:
    start_match = re.search(
        rf"(?m)^(?:def|theorem)\s+{re.escape(name)}(?:\s|:)", source
    )
    if start_match is None:
        raise CompactReceiptClosureError(f"missing Lean declaration {name}")
    end_match = re.search(
        r"(?m)^(?:def|theorem|structure|inductive|abbrev|class|instance)\s+",
        source[start_match.end() :],
    )
    end = len(source)
    if end_match is not None:
        end = start_match.end() + end_match.start()
    return source[start_match.start() : end]


def _case_string(block: str, constructor: str, label: str) -> str:
    match = re.search(
        rf"\|\s+\.{re.escape(constructor)}\s*=>\s*\"([^\"]*)\"",
        block,
    )
    if match is None:
        raise CompactReceiptClosureError(
            f"missing {label} case for .{constructor}"
        )
    return match.group(1)


def _case_constructor(block: str, constructor: str, label: str) -> str:
    match = re.search(
        rf"\|\s+\.{re.escape(constructor)}\s*=>\s*\.([A-Za-z0-9_]+)",
        block,
    )
    if match is None:
        raise CompactReceiptClosureError(
            f"missing {label} case for .{constructor}"
        )
    return match.group(1)


def _require_unique_ids(rows: list[dict[str, Any]], field: str, label: str) -> None:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise CompactReceiptClosureError(f"{label} contains duplicate {field}")


_RESULT_FILES = {
    "ch25-a7-boundary": "SparkInterval/Execution/RegisteredA7BoundaryCertificate.lean",
    "ch25-psi-two-pass-v1": (
        "SparkInterval/Execution/RegisteredPsiLemma92Certificate.lean"
    ),
    "platt-head-2e4": "SparkInterval/Execution/RegisteredZetaHeadCertificate.lean",
    "platt-trudgian-rh-3e12": (
        "SparkInterval/Execution/RegisteredZetaRHCertificate.lean"
    ),
    "helfgott-prop-12-2-4-mpfr-v1": (
        "SparkInterval/Execution/RegisteredProp1224Certificate.lean"
    ),
    "hurst-four-residuals-v1": (
        "SparkInterval/Execution/RegisteredHurstSharedCertificate.lean"
    ),
    "cdem-table-abel": (
        "SparkInterval/Execution/RegisteredCDEMAbelCertificate.lean"
    ),
    "ramare-zuniga-lemma-6-2": (
        "SparkInterval/Execution/RegisteredR2StarCertificate.lean"
    ),
    "helfgott-platt-goldbach-gpu-v1": (
        "SparkInterval/Execution/RegisteredGoldbachCertificate.lean"
    ),
    "platt-dirichlet-theorem-7-1": (
        "SparkInterval/Execution/RegisteredPlattTheorem71Certificate.lean"
    ),
    "ternary-goldbach-finite-below-10pow27-v1": (
        "SparkInterval/Execution/RegisteredGoldbach10Pow27Certificate.lean"
    ),
}


_EVIDENCE_THEOREM_FILES = {
    "ch25-a7-boundary": (
        "SparkInterval/TernaryGoldbach/A7BoundarySuccessEvidence.lean"
    ),
    "ch25-psi-two-pass-v1": (
        "SparkInterval/TernaryGoldbach/PsiPrimePowerCertificate.lean"
    ),
    "platt-head-2e4": (
        "SparkInterval/TernaryGoldbach/ZetaHeadSourceSemantics.lean"
    ),
    "platt-trudgian-rh-3e12": (
        "SparkInterval/TernaryGoldbach/ZetaRHSourceSemantics.lean"
    ),
    "helfgott-prop-12-2-4-mpfr-v1": (
        "SparkInterval/TernaryGoldbach/Prop1224SourceSemantics.lean"
    ),
    "hurst-four-residuals-v1": (
        "SparkInterval/TernaryGoldbach/HurstSourceSemantics.lean"
    ),
    "cdem-table-abel": (
        "SparkInterval/TernaryGoldbach/CDEMAbelRecurrenceCertificate.lean"
    ),
    "ramare-zuniga-lemma-6-2": (
        "SparkInterval/TernaryGoldbach/R2StarSourceSemantics.lean"
    ),
    "helfgott-platt-goldbach-gpu-v1": (
        "SparkInterval/TernaryGoldbach/GoldbachSourceSemantics.lean"
    ),
    "platt-dirichlet-theorem-7-1": (
        "SparkInterval/Dirichlet/PlattTheorem71Contract.lean"
    ),
    "ternary-goldbach-finite-below-10pow27-v1": (
        "SparkInterval/TernaryGoldbach/Goldbach10Pow27CampaignSemantics.lean"
    ),
}


_COMPACT_ADAPTER_FILES = {
    "ch25-a7-boundary": (
        "SparkInterval/TernaryGoldbach/A7BoundaryCompactChecker.lean"
    ),
    "ch25-psi-two-pass-v1": (
        "SparkInterval/TernaryGoldbach/PsiCompactChecker.lean"
    ),
    "platt-head-2e4": (
        "SparkInterval/TernaryGoldbach/ZetaHeadCompactChecker.lean"
    ),
    "platt-trudgian-rh-3e12": (
        "SparkInterval/TernaryGoldbach/ZetaRHCompactChecker.lean"
    ),
    "helfgott-prop-12-2-4-mpfr-v1": (
        "SparkInterval/TernaryGoldbach/Prop1224CompactChecker.lean"
    ),
    "hurst-four-residuals-v1": (
        "SparkInterval/TernaryGoldbach/HurstCompactChecker.lean"
    ),
    "cdem-table-abel": (
        "SparkInterval/TernaryGoldbach/CDEMAbelCompactChecker.lean"
    ),
    "ramare-zuniga-lemma-6-2": (
        "SparkInterval/TernaryGoldbach/R2StarCompactChecker.lean"
    ),
    "helfgott-platt-goldbach-gpu-v1": (
        "SparkInterval/TernaryGoldbach/GoldbachCompactChecker.lean"
    ),
    "platt-dirichlet-theorem-7-1": (
        "SparkInterval/Dirichlet/PlattTheorem71CompactChecker.lean"
    ),
    "ternary-goldbach-finite-below-10pow27-v1": (
        "SparkInterval/TernaryGoldbach/Goldbach10Pow27CompactChecker.lean"
    ),
}


def _lean_string_definition(
    source: str,
    name: str,
    cache: dict[str, str] | None = None,
) -> str:
    """Evaluate the tiny literal/concatenation language used by compact IDs."""

    if cache is None:
        cache = {}
    if name in cache:
        return cache[name]
    block = _definition_block(source, name)
    if ":=" not in block:
        raise CompactReceiptClosureError(
            f"Lean string definition {name} has no value"
        )
    expression = block.split(":=", 1)[1]
    expression = re.sub(r"/-.*?-/", "", expression, flags=re.DOTALL)
    expression = re.sub(r"--[^\n]*", "", expression)
    tokens = re.findall(
        r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*|\+\+|[()]',
        expression,
    )
    parts: list[str] = []
    for token in tokens:
        if token in {"++", "(", ")"}:
            continue
        if token.startswith('"'):
            try:
                parts.append(json.loads(token))
            except json.JSONDecodeError as error:
                raise CompactReceiptClosureError(
                    f"invalid string literal in Lean definition {name}"
                ) from error
            continue
        if re.search(
            rf"(?m)^def\s+{re.escape(token)}(?:\s|:)", source
        ) is None:
            raise CompactReceiptClosureError(
                f"unsupported token {token} in Lean string definition {name}"
            )
        parts.append(_lean_string_definition(source, token, cache))
    value = "".join(parts)
    cache[name] = value
    return value


def _validate_source_pins(document: dict[str, Any], root: Path) -> None:
    for label, pin in document["source_pins"].items():
        path = root / pin["path"]
        if not path.is_file():
            raise CompactReceiptClosureError(
                f"{label} source pin references missing {pin['path']}"
            )
        actual = _sha256_file(path)
        if actual != pin["sha256"]:
            raise CompactReceiptClosureError(
                f"{label} source pin changed: expected {pin['sha256']}, got {actual}"
            )


def _validate_catalog_and_claims(
    document: dict[str, Any], root: Path
) -> list[dict[str, Any]]:
    catalog = load_json_strict(
        root / document["source_pins"]["external_atom_catalog"]["path"]
    )
    claims = document["claims"]
    external = [row for row in claims if row["catalog_kind"] == "external_atom"]
    expected = [
        (row["id"], row["lean_name"])
        for row in catalog["atoms"]
    ]
    actual = [(row["claim_id"], row["lean_claim"]) for row in external]
    if actual != expected:
        raise CompactReceiptClosureError(
            "external claim id/declaration pairs differ from source catalog order"
        )
    lowered = [
        row for row in claims if row["catalog_kind"] == "lowered_finite_endpoint"
    ]
    if len(lowered) != 1 or lowered[0]["claim_id"] != document["scope"][
        "lowered_endpoint_id"
    ]:
        raise CompactReceiptClosureError(
            "lowered finite endpoint must occur exactly once"
        )
    return external


def _validate_closed_lean_catalog(
    external: list[dict[str, Any]], root: Path
) -> None:
    path = root / "SparkInterval/Execution/CompactArchitectureRegistry.lean"
    source = path.read_text(encoding="utf-8")
    ids = _definition_block(source, "catalogId")
    names = _definition_block(source, "leanDeclaration")
    id_pairs = re.findall(
        r"\|\s+\.([A-Za-z0-9_]+)\s*=>\s*\"([^\"]+)\"", ids
    )
    name_pairs = re.findall(
        r"\|\s+\.([A-Za-z0-9_]+)\s*=>\s*\"([^\"]+)\"", names
    )
    if [constructor for constructor, _ in id_pairs] != [
        constructor for constructor, _ in name_pairs
    ]:
        raise CompactReceiptClosureError(
            "closed Lean atom catalog has mismatched id/name constructors"
        )
    actual = [
        (catalog_id, declaration)
        for (_, catalog_id), (_, declaration) in zip(id_pairs, name_pairs)
    ]
    expected = [(row["claim_id"], row["lean_claim"]) for row in external]
    if actual != expected:
        raise CompactReceiptClosureError(
            "closed Lean atom catalog differs from exact JSON id/declaration pairs"
        )


def _validate_physical_partition(
    document: dict[str, Any], root: Path
) -> None:
    del root
    reported = {
        row["campaign_id"]: row["logical_claim_ids"]
        for row in document["campaigns"]
    }
    expected = {
        row["campaign_id"]: row["logical_atom_ids"]
        for row in h100_cluster._physical_campaign_records()
    }
    if reported != expected:
        raise CompactReceiptClosureError(
            "compact closure physical campaign partition differs from scheduler"
        )

    by_campaign = {row["campaign_id"]: row for row in document["campaigns"]}
    for source in h100_cluster._physical_campaign_records():
        row = by_campaign[source["campaign_id"]]
        if row["backend_class"] != source["backend_class"]:
            raise CompactReceiptClosureError(
                f"{source['campaign_id']} backend class differs from scheduler"
            )
        if row["execution_mode"] != source["execution_mode"]:
            raise CompactReceiptClosureError(
                f"{source['campaign_id']} execution mode differs from scheduler"
            )


def _validate_registered_identities(
    document: dict[str, Any], root: Path
) -> None:
    path = root / "SparkInterval/Execution/RegisteredAlgorithm.lean"
    source = path.read_text(encoding="utf-8")
    algorithm_cases = _definition_block(source, "algorithm")
    algorithm_ids = _definition_block(source, "algorithmId")
    algorithm_hashes = _definition_block(source, "algorithmHash")
    input_cases = _definition_block(source, "canonicalInput")
    input_hashes = _definition_block(source, "canonicalInputHash")
    parameter_hashes = _definition_block(source, "canonicalParametersHash")
    domain_hashes = _definition_block(source, "canonicalDomainHash")

    for campaign in document["campaigns"]:
        identity = campaign["registered_identity"]
        invocation = identity["invocation"]
        algorithm = identity["algorithm"]
        actual_algorithm = _case_constructor(
            algorithm_cases, invocation, "registered algorithm"
        )
        if actual_algorithm != algorithm:
            raise CompactReceiptClosureError(
                f"{campaign['campaign_id']} invocation selects {actual_algorithm}, "
                f"not {algorithm}"
            )
        expected_fields = {
            "algorithm_id": _case_string(
                algorithm_ids, algorithm, "algorithm id"
            ),
            "algorithm_hash": _case_string(
                algorithm_hashes, algorithm, "algorithm hash"
            ),
            "input_hash": _case_string(
                input_hashes, invocation, "canonical input hash"
            ),
            "parameters_hash": _case_string(
                parameter_hashes, algorithm, "parameter hash"
            ),
            "domain_hash": _case_string(
                domain_hashes, algorithm, "domain hash"
            ),
        }
        for field, expected in expected_fields.items():
            if identity[field] != expected:
                raise CompactReceiptClosureError(
                    f"{campaign['campaign_id']} {field} differs from Lean selector"
                )

        input_name = identity["canonical_input_selector"].rsplit(".", 1)[-1]
        input_case = re.search(
            rf"\|\s+\.{re.escape(invocation)}\s*=>\s*"
            rf"RegisteredAlgorithm\.{re.escape(input_name)}\b",
            input_cases,
        )
        if input_case is None:
            raise CompactReceiptClosureError(
                f"{campaign['campaign_id']} canonical input selector differs from Lean"
            )
        _definition_block(source, input_name)


def _validate_results_and_theorems(
    document: dict[str, Any], root: Path
) -> None:
    registered_source = (
        root / "SparkInterval/Execution/RegisteredAlgorithm.lean"
    ).read_text(encoding="utf-8")
    for campaign in document["campaigns"]:
        campaign_id = campaign["campaign_id"]
        result = campaign["registered_identity"]["success_result"]
        encoded = result["bytes_utf8"].encode("utf-8")
        expected_pin = {
            "byte_length": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        if result["pin"] != expected_pin:
            raise CompactReceiptClosureError(
                f"{campaign_id} registered result pin differs from exact UTF-8"
            )
        if campaign["physical_compact_pins"]["result"] != expected_pin:
            raise CompactReceiptClosureError(
                f"{campaign_id} physical result pin differs from registered result"
            )
        result_source = (root / _RESULT_FILES[campaign_id]).read_text(
            encoding="utf-8"
        )
        result_name = result["selector"].rsplit(".", 1)[-1]
        if re.search(
            rf"(?m)^def\s+{re.escape(result_name)}(?:\s|:)", result_source
        ) is None:
            raise CompactReceiptClosureError(
                f"{campaign_id} result selector {result_name} is absent"
            )

        evidence_theorem = campaign["lean_soundness"][
            "evidence_to_claim_theorem"
        ].rsplit(".", 1)[-1]
        evidence_source = (root / _EVIDENCE_THEOREM_FILES[campaign_id]).read_text(
            encoding="utf-8"
        )
        if re.search(
            rf"(?m)^theorem\s+{re.escape(evidence_theorem)}(?:\s|$)",
            evidence_source,
        ) is None:
            raise CompactReceiptClosureError(
                f"{campaign_id} evidence theorem {evidence_theorem} is absent"
            )
        registered_theorem = campaign["lean_soundness"][
            "registered_success_theorem"
        ].rsplit(".", 1)[-1]
        if re.search(
            rf"(?m)^theorem\s+{re.escape(registered_theorem)}(?:\s|$)",
            registered_source,
        ) is None:
            raise CompactReceiptClosureError(
                f"{campaign_id} registered theorem {registered_theorem} is absent"
            )

    cdem = next(
        row for row in document["campaigns"]
        if row["campaign_id"] == "cdem-table-abel"
    )
    signed_target = 324_880_457_633_740
    absolute_target = 48_710_223_109_607_260_068_028
    paired = (
        absolute_target * absolute_target + signed_target
        if signed_target < absolute_target
        else signed_target * signed_target + signed_target + absolute_target
    )
    if cdem["registered_identity"]["success_result"]["bytes_utf8"] != str(paired):
        raise CompactReceiptClosureError(
            "CDEM result is not the exact Mathlib Nat.pair of source targets"
        )


def _validate_compact_adapters(
    document: dict[str, Any], root: Path
) -> None:
    for campaign in document["campaigns"]:
        campaign_id = campaign["campaign_id"]
        path = root / _COMPACT_ADAPTER_FILES[campaign_id]
        source = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*axiom\s+", source) is not None:
            raise CompactReceiptClosureError(
                f"{campaign_id} compact adapter must not declare an axiom"
            )
        accepts = _definition_block(source, "Accepts")
        if "SourceClaim" in accepts or "RealSourceClaims" in accepts:
            raise CompactReceiptClosureError(
                f"{campaign_id} compact acceptance contains a derived source claim"
            )
        for required in ("canonicalInputBytes", "canonicalResultBytes"):
            if required not in accepts:
                raise CompactReceiptClosureError(
                    f"{campaign_id} compact acceptance omits {required}"
                )
        input_text = _lean_string_definition(source, "canonicalInputText")
        input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        expected_hash = campaign["registered_identity"]["input_hash"]
        if input_hash != expected_hash:
            raise CompactReceiptClosureError(
                f"{campaign_id} compact canonical input differs from registered input"
            )
        adapter = campaign["receipt_closure"]["per_campaign_adapter"]
        theorem_name = adapter.rsplit(".", 1)[-1]
        if re.search(
            rf"(?m)^theorem\s+{re.escape(theorem_name)}(?:\s|$)",
            source,
        ) is None:
            raise CompactReceiptClosureError(
                f"{campaign_id} compact adapter theorem {theorem_name} is absent"
            )
        if "ArchitectureRefinesNativeChecker" not in _definition_block(
            source, theorem_name
        ):
            raise CompactReceiptClosureError(
                f"{campaign_id} adapter hides the executable-refinement premise"
            )


def _validate_static_gaps(document: dict[str, Any], root: Path) -> None:
    for campaign in document["campaigns"]:
        campaign_id = campaign["campaign_id"]
        for relative in campaign["implementation_sources"]:
            if not (root / relative).is_file():
                raise CompactReceiptClosureError(
                    f"{campaign_id} implementation source is missing: {relative}"
                )
        pins = campaign["physical_compact_pins"]
        for field in (
            "receipt_hash",
            "measurement_scheme_id",
            "machine_semantics_id",
            "entry_point",
            "executable",
            "input",
        ):
            if pins[field] is not None:
                raise CompactReceiptClosureError(
                    f"{campaign_id} pre-run physical field {field} must be null"
                )
        closure = campaign["receipt_closure"]
        if campaign["execution_mode"] == "manual_phase_dag":
            if closure["receipt_scope"] != "transitive_campaign_graph":
                raise CompactReceiptClosureError(
                    f"{campaign_id} DAG must require transitive campaign closure"
                )
            if closure["one_ordinary_process_receipt_sufficient"]:
                raise CompactReceiptClosureError(
                    f"{campaign_id} DAG cannot use one ordinary process receipt"
                )
        if closure["receipt_scope"] != "direct_single_process":
            if "transitive_child_execution_closure" not in closure["missing_proofs"]:
                raise CompactReceiptClosureError(
                    f"{campaign_id} transitive scope omits graph-closure gap"
                )
        if campaign["lean_soundness"]["native_bytes_to_evidence_theorem"] is not None:
            raise CompactReceiptClosureError(
                f"{campaign_id} overclaims native-bytes realization"
            )
        if campaign["machine_refinement"]["exact_executable_refinement"]:
            raise CompactReceiptClosureError(
                f"{campaign_id} overclaims exact executable refinement"
            )
        if closure["can_one_receipt_yield_claim_now"]:
            raise CompactReceiptClosureError(
                f"{campaign_id} overclaims current receipt authority"
            )
        if not isinstance(closure["per_campaign_adapter"], str):
            raise CompactReceiptClosureError(
                f"{campaign_id} omits its conditional compact claim adapter"
            )


def validate_closure_document(
    document: dict[str, Any],
    *,
    repository_root: Path = DEFAULT_REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Cross-check the complete static closure matrix and return it."""

    root = repository_root.resolve()
    campaigns = document.get("campaigns")
    claims = document.get("claims")
    if not isinstance(campaigns, list) or not isinstance(claims, list):
        raise CompactReceiptClosureError("campaigns and claims must be arrays")
    if len(campaigns) != 11 or len(claims) != 14:
        raise CompactReceiptClosureError(
            "closure matrix must contain exactly 11 campaigns and 14 claims"
        )
    _require_unique_ids(campaigns, "campaign_id", "campaign inventory")
    _require_unique_ids(claims, "claim_id", "claim inventory")

    _validate_source_pins(document, root)
    external = _validate_catalog_and_claims(document, root)
    _validate_closed_lean_catalog(external, root)
    _validate_physical_partition(document, root)
    _validate_registered_identities(document, root)
    _validate_results_and_theorems(document, root)
    _validate_compact_adapters(document, root)
    _validate_static_gaps(document, root)

    campaign_ids = {row["campaign_id"] for row in campaigns}
    for claim in claims:
        if claim["campaign_id"] not in campaign_ids:
            raise CompactReceiptClosureError(
                f"{claim['claim_id']} selects unknown campaign"
            )
    flattened = [
        claim_id
        for campaign in campaigns
        for claim_id in campaign["logical_claim_ids"]
    ]
    if set(flattened) != {row["claim_id"] for row in claims}:
        raise CompactReceiptClosureError(
            "campaign logical claims do not partition all fourteen claims"
        )
    if len(flattened) != len(set(flattened)):
        raise CompactReceiptClosureError(
            "a logical claim is assigned to multiple physical campaigns"
        )
    return document


def load_and_validate_closure(
    path: Path = DEFAULT_MANIFEST,
    *,
    repository_root: Path = DEFAULT_REPOSITORY_ROOT,
) -> dict[str, Any]:
    document = load_json_strict(path)
    if not isinstance(document, dict):
        raise CompactReceiptClosureError("closure inventory root must be an object")
    return validate_closure_document(
        document,
        repository_root=repository_root,
    )


__all__ = [
    "CompactReceiptClosureError",
    "DEFAULT_MANIFEST",
    "load_and_validate_closure",
    "load_json_strict",
    "validate_closure_document",
]
