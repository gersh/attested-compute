# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical, non-authorizing target-SKU performance calibration metadata.

Validation checks the compact manifest's shape, identities, canonical
self-hash, profile pins, timing geometry, and conservative node-hour
arithmetic.  It never opens the executable, closure, measured-run receipt, or
attestation appraisal named by those hashes.  A valid manifest may inform a
planning report; it cannot authorize execution, deployment, a receipt, a Lean
theorem, or an external-atom claim.
"""

from __future__ import annotations

from math import gcd
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "sparkinterval.tg.azure-target-sku-calibration.v1"
MAX_MANIFEST_BYTES = 256 * 1024
NANOSECONDS_PER_HOUR = 3_600_000_000_000
MAX_REPETITIONS = 64
MAX_DIMENSIONS = 8
MAX_U64 = (1 << 64) - 1

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,191}$")

MEASUREMENT_CLASSIFICATION = (
    "appraised-measured-target-sku-bounded-calibration-not-production-run"
)
PROJECTION_CLASSIFICATION = (
    "conservative-linear-node-hour-upper-endpoint-not-measurement"
)

AUTHORITY_BLOCK = {
    "authorizes_cloud_execution": False,
    "authorizes_lean_theorem": False,
    "authorizes_production_deployment": False,
    "authorizes_trusted_compute_receipt": False,
    "classification": "performance-calibration-metadata-only-not-authority",
    "establishes_external_atom": False,
    "may_inform_planning_sizing": True,
    "named_artifact_bytes_validated": False,
    "validation_scope": (
        "canonical-shape-self-hash-profile-pins-and-internal-arithmetic-only"
    ),
}

# These are byte hashes of the reviewed canonical profiles under ``profiles/``.
# A measured record using a local or mock trust profile is not target-SKU
# calibration evidence for the production sizing model.
REVIEWED_TARGET_BINDINGS = {
    "dc96_cpu": {
        "sku": "Standard_DC96as_v6",
        "target_profile_id": "azure_sevsnp_cpu",
        "target_profile_sha256": (
            "949316107df9d25c0bd41c660224bcd777496a3debf3dd3d1549b89cbb3d42ed"
        ),
        "trust_profile_id": "azure_sevsnp_hardware_attested",
        "trust_profile_sha256": (
            "1197cd3c434697178fd879d91e4b30710a5405b8b6b9d213253ffdfcecc0335f"
        ),
    },
    "ncc_h100": {
        "sku": "Standard_NCC40ads_H100_v5",
        "target_profile_id": "azure_ncc40ads_h100_v5",
        "target_profile_sha256": (
            "e8ce26a02aa7b4a9577f9a725f00ebb464c8b70a40dfcb5fc4b107a7f66ec148"
        ),
        "trust_profile_id": "azure_ncc_sevsnp_vtpm_nvidia_cc_attested",
        "trust_profile_sha256": (
            "470cb77b28f0c5c7e777ffbc5137ebfb670015f03cfea12ccd7ebdd544bb2c6b"
        ),
    },
}

_ROOT_KEYS = {
    "authority",
    "evidence",
    "identity",
    "kind",
    "manifest_sha256",
    "measurement",
    "profiles",
    "projection",
    "sample",
    "schema_version",
    "target",
    "timings",
}
_BODY_KEYS = _ROOT_KEYS - {"manifest_sha256"}
_IDENTITY_KEYS = {
    "artifact_closure",
    "campaign_id",
    "executable",
    "resource_class",
    "route_id",
}
_EXECUTABLE_KEYS = {"sha256", "size_bytes"}
_CLOSURE_KEYS = {"file_count", "manifest_sha256", "total_size_bytes"}
_PROFILE_KEYS = {
    "target_profile_id",
    "target_profile_sha256",
    "trust_profile_id",
    "trust_profile_sha256",
}
_TARGET_KEYS = {"node_count", "provider", "region", "sku"}
_DIMENSION_KEYS = {"count", "name", "unit"}
_SAMPLE_KEYS = {
    "dimensions",
    "effective_work_items",
    "effective_work_unit",
    "geometry_id",
    "scope",
}
_TIMING_KEYS = {
    "end_to_end_nanoseconds",
    "input_io_nanoseconds",
    "output_io_nanoseconds",
    "producer_nanoseconds",
    "repetitions",
    "replay_nanoseconds",
    "unit",
}
_MEASUREMENT_KEYS = {
    "classification",
    "full_source_execution_measured",
    "target_sku_timings_measured",
}
_EVIDENCE_KEYS = {
    "attestation_appraisal_sha256",
    "measured_run_receipt_sha256",
}
_PROJECTION_KEYS = {
    "classification",
    "conservative_high_node_hours",
    "endpoint_is_projection_not_measurement",
    "safety_factor",
    "source_effective_work_items",
    "source_effective_work_unit",
}
_FRACTION_KEYS = {"denominator", "numerator"}


class TargetSKUCalibrationError(ValueError):
    """A target-SKU calibration manifest is malformed or inconsistent."""


def _exact_object(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetSKUCalibrationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise TargetSKUCalibrationError(
            f"{label} has wrong fields "
            f"(missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)})"
        )
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise TargetSKUCalibrationError(f"{label} is not a canonical identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        raise TargetSKUCalibrationError(
            f"{label} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _nat(
    value: Any,
    label: str,
    *,
    positive: bool = False,
    maximum: int = MAX_U64,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TargetSKUCalibrationError(f"{label} must be an integer")
    minimum = 1 if positive else 0
    if value < minimum or value > maximum:
        qualifier = "positive " if positive else "nonnegative "
        raise TargetSKUCalibrationError(
            f"{label} must be a {qualifier}integer at most {maximum}"
        )
    return value


def _fraction(value: Any, label: str) -> tuple[int, int]:
    row = _exact_object(value, _FRACTION_KEYS, label)
    numerator = _nat(row["numerator"], f"{label}.numerator", positive=True)
    denominator = _nat(row["denominator"], f"{label}.denominator", positive=True)
    if gcd(numerator, denominator) != 1:
        raise TargetSKUCalibrationError(f"{label} must be in lowest terms")
    return numerator, denominator


def _timing_vector(
    value: Any,
    label: str,
    repetitions: int,
    *,
    positive: bool,
) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != repetitions:
        raise TargetSKUCalibrationError(
            f"{label} must contain exactly {repetitions} entries"
        )
    return tuple(
        _nat(item, f"{label}[{index}]", positive=positive)
        for index, item in enumerate(value)
    )


def _validate_identity(value: Any) -> str:
    identity = _exact_object(value, _IDENTITY_KEYS, "identity")
    campaign_id = _identifier(identity["campaign_id"], "identity.campaign_id")
    route_id = _identifier(identity["route_id"], "identity.route_id")
    if not route_id.startswith(campaign_id + ":"):
        raise TargetSKUCalibrationError(
            "identity.route_id is not namespaced by identity.campaign_id"
        )
    resource = _identifier(identity["resource_class"], "identity.resource_class")
    if resource not in REVIEWED_TARGET_BINDINGS:
        raise TargetSKUCalibrationError("identity.resource_class is unsupported")
    executable = _exact_object(
        identity["executable"], _EXECUTABLE_KEYS, "identity.executable"
    )
    _digest(executable["sha256"], "identity.executable.sha256")
    _nat(
        executable["size_bytes"],
        "identity.executable.size_bytes",
        positive=True,
    )
    closure = _exact_object(
        identity["artifact_closure"],
        _CLOSURE_KEYS,
        "identity.artifact_closure",
    )
    _digest(
        closure["manifest_sha256"],
        "identity.artifact_closure.manifest_sha256",
    )
    _nat(
        closure["file_count"],
        "identity.artifact_closure.file_count",
        positive=True,
    )
    _nat(
        closure["total_size_bytes"],
        "identity.artifact_closure.total_size_bytes",
        positive=True,
    )
    return resource


def _validate_profiles(value: Any, resource: str) -> None:
    profiles = _exact_object(value, _PROFILE_KEYS, "profiles")
    expected = REVIEWED_TARGET_BINDINGS[resource]
    for field in _PROFILE_KEYS:
        actual = profiles[field]
        if field.endswith("_sha256"):
            _digest(actual, f"profiles.{field}")
        else:
            _identifier(actual, f"profiles.{field}")
        if actual != expected[field]:
            raise TargetSKUCalibrationError(
                f"profiles.{field} differs from the reviewed {resource} profile"
            )


def _validate_target(value: Any, resource: str) -> int:
    target = _exact_object(value, _TARGET_KEYS, "target")
    if target["provider"] != "azure":
        raise TargetSKUCalibrationError("target.provider must be azure")
    _identifier(target["region"], "target.region")
    if target["sku"] != REVIEWED_TARGET_BINDINGS[resource]["sku"]:
        raise TargetSKUCalibrationError(
            "target.sku differs from the reviewed resource-class SKU"
        )
    return _nat(target["node_count"], "target.node_count", positive=True, maximum=4096)


def _validate_sample(value: Any) -> tuple[int, str]:
    sample = _exact_object(value, _SAMPLE_KEYS, "sample")
    _identifier(sample["geometry_id"], "sample.geometry_id")
    if sample["scope"] not in {"full_source", "source_shaped_bounded"}:
        raise TargetSKUCalibrationError(
            "sample.scope must be full_source or source_shaped_bounded"
        )
    dimensions = sample["dimensions"]
    if (
        not isinstance(dimensions, list)
        or not 1 <= len(dimensions) <= MAX_DIMENSIONS
    ):
        raise TargetSKUCalibrationError(
            f"sample.dimensions must contain 1..{MAX_DIMENSIONS} rows"
        )
    names: list[str] = []
    product = 1
    for index, raw in enumerate(dimensions):
        row = _exact_object(
            raw, _DIMENSION_KEYS, f"sample.dimensions[{index}]"
        )
        names.append(_identifier(row["name"], f"sample.dimensions[{index}].name"))
        _identifier(row["unit"], f"sample.dimensions[{index}].unit")
        product *= _nat(
            row["count"],
            f"sample.dimensions[{index}].count",
            positive=True,
        )
        if product > MAX_U64:
            raise TargetSKUCalibrationError("sample dimension product exceeds uint64")
    if names != sorted(names) or len(set(names)) != len(names):
        raise TargetSKUCalibrationError(
            "sample dimensions must have unique names in lexical order"
        )
    effective = _nat(
        sample["effective_work_items"],
        "sample.effective_work_items",
        positive=True,
    )
    if effective != product:
        raise TargetSKUCalibrationError(
            "sample.effective_work_items must equal the dimension product"
        )
    unit = _identifier(
        sample["effective_work_unit"], "sample.effective_work_unit"
    )
    return effective, unit


def _validate_timings(value: Any) -> tuple[int, tuple[int, ...]]:
    timings = _exact_object(value, _TIMING_KEYS, "timings")
    if timings["unit"] != "nanoseconds":
        raise TargetSKUCalibrationError("timings.unit must be nanoseconds")
    repetitions = _nat(
        timings["repetitions"],
        "timings.repetitions",
        positive=True,
        maximum=MAX_REPETITIONS,
    )
    if repetitions < 3:
        raise TargetSKUCalibrationError(
            "timings.repetitions must be at least three"
        )
    producer = _timing_vector(
        timings["producer_nanoseconds"],
        "timings.producer_nanoseconds",
        repetitions,
        positive=True,
    )
    replay = _timing_vector(
        timings["replay_nanoseconds"],
        "timings.replay_nanoseconds",
        repetitions,
        positive=True,
    )
    input_io = _timing_vector(
        timings["input_io_nanoseconds"],
        "timings.input_io_nanoseconds",
        repetitions,
        positive=False,
    )
    output_io = _timing_vector(
        timings["output_io_nanoseconds"],
        "timings.output_io_nanoseconds",
        repetitions,
        positive=False,
    )
    end_to_end = _timing_vector(
        timings["end_to_end_nanoseconds"],
        "timings.end_to_end_nanoseconds",
        repetitions,
        positive=True,
    )
    for index, total in enumerate(end_to_end):
        component_sum = (
            producer[index]
            + replay[index]
            + input_io[index]
            + output_io[index]
        )
        if total < component_sum:
            raise TargetSKUCalibrationError(
                "end-to-end timing is smaller than the recorded component sum at "
                f"repetition {index}"
            )
    return repetitions, end_to_end


def _validate_projection(
    value: Any,
    *,
    sample_work: int,
    sample_unit: str,
    node_count: int,
    maximum_end_to_end_ns: int,
    full_source_measured: bool,
) -> None:
    projection = _exact_object(value, _PROJECTION_KEYS, "projection")
    if projection["classification"] != PROJECTION_CLASSIFICATION:
        raise TargetSKUCalibrationError(
            "projection.classification must identify a projection, not a measurement"
        )
    if projection["endpoint_is_projection_not_measurement"] is not True:
        raise TargetSKUCalibrationError(
            "projection endpoint must be explicitly classified as non-measurement"
        )
    source_work = _nat(
        projection["source_effective_work_items"],
        "projection.source_effective_work_items",
        positive=True,
    )
    if source_work < sample_work:
        raise TargetSKUCalibrationError(
            "projection source work cannot be smaller than sample work"
        )
    if projection["source_effective_work_unit"] != sample_unit:
        raise TargetSKUCalibrationError(
            "projection and sample effective-work units differ"
        )
    if full_source_measured and source_work != sample_work:
        raise TargetSKUCalibrationError(
            "a full-source measurement must measure the full source work"
        )
    safety_num, safety_den = _fraction(
        projection["safety_factor"], "projection.safety_factor"
    )
    if safety_num < safety_den:
        raise TargetSKUCalibrationError("projection safety factor must be at least one")
    high_num, high_den = _fraction(
        projection["conservative_high_node_hours"],
        "projection.conservative_high_node_hours",
    )
    required_num = (
        maximum_end_to_end_ns * node_count * source_work * safety_num
    )
    required_den = (
        NANOSECONDS_PER_HOUR * sample_work * safety_den
    )
    if high_num * required_den < required_num * high_den:
        raise TargetSKUCalibrationError(
            "conservative high node-hour endpoint is below the measured "
            "max-repetition linear projection"
        )


def _validate_body(body: Mapping[str, Any]) -> None:
    value = _exact_object(body, _BODY_KEYS, "manifest body")
    if (
        isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise TargetSKUCalibrationError("unsupported schema_version")
    if value["kind"] != MANIFEST_KIND:
        raise TargetSKUCalibrationError("unsupported manifest kind")
    authority = _exact_object(value["authority"], set(AUTHORITY_BLOCK), "authority")
    for field, expected in AUTHORITY_BLOCK.items():
        actual = authority[field]
        if type(actual) is not type(expected) or actual != expected:
            raise TargetSKUCalibrationError(
                "authority block must retain the non-authorizing scope"
            )
    resource = _validate_identity(value["identity"])
    _validate_profiles(value["profiles"], resource)
    node_count = _validate_target(value["target"], resource)
    sample_work, sample_unit = _validate_sample(value["sample"])
    _repetitions, end_to_end = _validate_timings(value["timings"])
    measurement = _exact_object(
        value["measurement"], _MEASUREMENT_KEYS, "measurement"
    )
    if measurement["classification"] != MEASUREMENT_CLASSIFICATION:
        raise TargetSKUCalibrationError(
            "measurement.classification is not target-SKU measurement evidence"
        )
    if measurement["target_sku_timings_measured"] is not True:
        raise TargetSKUCalibrationError(
            "measurement must affirm target-SKU timing collection"
        )
    if not isinstance(measurement["full_source_execution_measured"], bool):
        raise TargetSKUCalibrationError(
            "measurement.full_source_execution_measured must be Boolean"
        )
    if measurement["full_source_execution_measured"] != (
        value["sample"]["scope"] == "full_source"
    ):
        raise TargetSKUCalibrationError(
            "measurement full-source flag differs from sample.scope"
        )
    evidence = _exact_object(value["evidence"], _EVIDENCE_KEYS, "evidence")
    _digest(
        evidence["measured_run_receipt_sha256"],
        "evidence.measured_run_receipt_sha256",
    )
    _digest(
        evidence["attestation_appraisal_sha256"],
        "evidence.attestation_appraisal_sha256",
    )
    _validate_projection(
        value["projection"],
        sample_work=sample_work,
        sample_unit=sample_unit,
        node_count=node_count,
        maximum_end_to_end_ns=max(end_to_end),
        full_source_measured=measurement["full_source_execution_measured"],
    )


def seal_manifest(body: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one body and add its canonical body hash."""

    _validate_body(body)
    manifest = dict(body)
    manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return validate_manifest(manifest)


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate strict shape, profile pins, arithmetic, and canonical self-hash."""

    manifest = _exact_object(value, _ROOT_KEYS, "target-SKU calibration manifest")
    claimed = _digest(manifest["manifest_sha256"], "manifest_sha256")
    body = {key: manifest[key] for key in sorted(_BODY_KEYS)}
    _validate_body(body)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        raise TargetSKUCalibrationError(
            "manifest_sha256 does not match the canonical manifest body"
        )
    return manifest


def validate_manifest_bytes(raw: bytes) -> dict[str, Any]:
    """Validate one bounded canonical record without opening named artifacts."""

    if not isinstance(raw, bytes):
        raise TargetSKUCalibrationError("calibration manifest bytes must be bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise TargetSKUCalibrationError(
            f"calibration manifest exceeds {MAX_MANIFEST_BYTES} bytes"
        )
    try:
        value = parse_json_bytes(raw, label="Azure target-SKU calibration manifest")
        if raw != canonical_json_bytes(value):
            raise TargetSKUCalibrationError(
                "target-SKU calibration manifest is not canonical JSON"
            )
    except CampaignIOError as error:
        raise TargetSKUCalibrationError(str(error)) from error
    return validate_manifest(value)


def load_manifest(path: Path) -> dict[str, Any]:
    """Read exactly one compact manifest and no artifact named by it."""

    try:
        raw = read_bytes_once(path, limit=MAX_MANIFEST_BYTES)
    except CampaignIOError as error:
        raise TargetSKUCalibrationError(str(error)) from error
    return validate_manifest_bytes(raw)


def calibration_key(manifest: Any) -> tuple[str, str, str]:
    """Return ``(campaign, route, resource)`` after strict validation."""

    checked = validate_manifest(manifest)
    identity = checked["identity"]
    return (
        identity["campaign_id"],
        identity["route_id"],
        identity["resource_class"],
    )


def conservative_high_node_hours(manifest: Any) -> tuple[int, int]:
    """Return the exact reduced high endpoint after strict validation."""

    checked = validate_manifest(manifest)
    value = checked["projection"]["conservative_high_node_hours"]
    return value["numerator"], value["denominator"]


def validate_manifest_set(values: Sequence[Any] | None) -> tuple[dict[str, Any], ...]:
    """Validate an explicitly supplied set and reject duplicate route branches."""

    if values is None:
        return ()
    if isinstance(values, (str, bytes, bytearray, dict)) or not isinstance(
        values, Sequence
    ):
        raise TargetSKUCalibrationError(
            "target-SKU calibrations must be an explicit sequence of manifests"
        )
    checked = tuple(validate_manifest(value) for value in values)
    keys = [calibration_key(value) for value in checked]
    if len(set(keys)) != len(keys):
        raise TargetSKUCalibrationError(
            "duplicate target-SKU calibration for one route resource"
        )
    return checked


def validation_summary(manifest: Any) -> dict[str, Any]:
    """Return a compact planning-only summary."""

    checked = validate_manifest(manifest)
    high_num, high_den = conservative_high_node_hours(checked)
    return {
        "artifact_bytes_read": False,
        "attestation_appraisal_replayed": False,
        "authorizes_cloud_execution": False,
        "authorizes_lean_theorem": False,
        "authorizes_production_deployment": False,
        "campaign_id": checked["identity"]["campaign_id"],
        "conservative_high_node_hours": {
            "numerator": high_num,
            "denominator": high_den,
        },
        "manifest_sha256": checked["manifest_sha256"],
        "measurement_classification": checked["measurement"]["classification"],
        "named_artifact_bytes_validated": False,
        "resource_class": checked["identity"]["resource_class"],
        "route_id": checked["identity"]["route_id"],
        "target_sku": checked["target"]["sku"],
        "target_sku_calibration_manifest_valid": True,
    }


__all__ = [
    "AUTHORITY_BLOCK",
    "MANIFEST_KIND",
    "MAX_MANIFEST_BYTES",
    "MEASUREMENT_CLASSIFICATION",
    "PROJECTION_CLASSIFICATION",
    "REVIEWED_TARGET_BINDINGS",
    "SCHEMA_VERSION",
    "TargetSKUCalibrationError",
    "calibration_key",
    "conservative_high_node_hours",
    "load_manifest",
    "seal_manifest",
    "validate_manifest",
    "validate_manifest_bytes",
    "validate_manifest_set",
    "validation_summary",
]
