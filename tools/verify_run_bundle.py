#!/usr/bin/env python3
"""Verify a SparkInterval run bundle and apply an explicit trust policy."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Iterable, MutableSet

import local_operator_signature as operator_signing

from create_run_bundle import (
    BUNDLE_KIND,
    SCHEMA_VERSION,
    ALGORITHM_ID_RE,
    BACKEND_KINDS,
    BundleError,
    GPU_EXECUTION_ROLES,
    PROFILE_ID_RE,
    ROLE_RE,
    canonical_json_bytes,
    canonical_sha256,
    hash_file,
    load_canonical_json,
    load_json,
    validate_completion,
    validate_json_value,
    validate_nonce,
    validate_profile,
    validate_sha256,
)


INTEGRITY_POLICY = "integrity"
DGX_OPERATOR_SIGNED_POLICY = "dgx_operator_signed"
HARDWARE_PRODUCTION_POLICY = "hardware_production"
H100_PRODUCTION_POLICY = "h100_production"
POLICIES = (
    INTEGRITY_POLICY,
    DGX_OPERATOR_SIGNED_POLICY,
    HARDWARE_PRODUCTION_POLICY,
    H100_PRODUCTION_POLICY,
)
DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


class VerificationError(BundleError):
    """A bundle failed structural, integrity, replay, or policy verification."""


AttestationValidator = Callable[[Path, str, str], bool]


def _fail(message: str) -> None:
    raise VerificationError(message)


def _exact_object(value: Any, expected: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be a JSON object")
    keys = set(value)
    if keys != expected:
        _fail(
            f"{what} has wrong fields "
            f"(missing={sorted(expected - keys)}, unexpected={sorted(keys - expected)})"
        )
    return value


def _load_catalog(profiles_dir: str | os.PathLike[str]) -> dict[tuple[str, str], dict[str, Any]]:
    root = Path(profiles_dir)
    locations = (("target", root / "targets"), ("trust", root / "trust"))
    catalog: dict[tuple[str, str], dict[str, Any]] = {}
    for kind, directory in locations:
        if not directory.is_dir():
            _fail(f"missing {kind} profile directory: {directory}")
        for path in sorted(directory.glob("*.json")):
            try:
                profile = validate_profile(load_json(path), kind)
            except BundleError as exc:
                _fail(f"invalid profile {path}: {exc}")
            key = (kind, profile["profile_id"])
            if key in catalog:
                _fail(f"duplicate {kind} profile_id: {profile['profile_id']}")
            catalog[key] = profile
    return catalog


def _resolve_profile_reference(
    value: Any,
    kind: str,
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    reference = _exact_object(value, {"profile_id", "sha256"}, f"{kind} profile reference")
    profile_id = reference["profile_id"]
    if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
        _fail(f"invalid {kind} profile id")
    try:
        validate_sha256(reference["sha256"], f"{kind} profile hash")
    except BundleError as exc:
        _fail(str(exc))
    profile = catalog.get((kind, profile_id))
    if profile is None:
        _fail(f"unknown {kind} profile: {profile_id}")
    expected_hash = canonical_sha256(profile)
    if reference["sha256"] != expected_hash:
        _fail(f"{kind} profile hash does not match the trusted profile catalog")
    return profile


def _safe_artifact_path(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{what} path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        _fail(f"{what} has an unsafe path")
    if path.as_posix() != value:
        _fail(f"{what} path is not in canonical POSIX form")
    return value


def _artifact_record(value: Any, what: str, *, with_role: bool) -> dict[str, Any]:
    expected = {"path", "sha256", "size_bytes"}
    if with_role:
        expected.add("role")
    result = _exact_object(value, expected, what)
    _safe_artifact_path(result["path"], what)
    try:
        validate_sha256(result["sha256"], f"{what} hash")
    except BundleError as exc:
        _fail(str(exc))
    size = result["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        _fail(f"{what} size_bytes must be a nonnegative integer")
    if with_role:
        role = result["role"]
        if not isinstance(role, str) or ROLE_RE.fullmatch(role) is None:
            _fail(f"{what} has an invalid role")
    return result


def _bound_json(value: Any, what: str) -> dict[str, Any]:
    result = _exact_object(value, {"value", "canonical_sha256"}, what)
    if not isinstance(result["value"], dict) or not result["value"]:
        _fail(f"{what} value must be a non-empty JSON object")
    try:
        validate_json_value(result["value"])
        validate_sha256(result["canonical_sha256"], f"{what} canonical hash")
    except BundleError as exc:
        _fail(str(exc))
    if result["canonical_sha256"] != canonical_sha256(result["value"]):
        _fail(f"{what} canonical hash does not match its value")
    return result


def _resolve_root(root: str | os.PathLike[str]) -> Path:
    try:
        resolved = Path(root).resolve(strict=True)
    except OSError as exc:
        _fail(f"cannot resolve artifact root {root}: {exc}")
    if not resolved.is_dir():
        _fail(f"artifact root is not a directory: {resolved}")
    return resolved


def _verify_artifact_file(record: dict[str, Any], root: Path, what: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(record["path"]).parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        _fail(f"{what} cannot be resolved safely under the artifact root: {exc}")
    if not resolved.is_file():
        _fail(f"{what} is not a regular file")
    try:
        digest, size = hash_file(resolved)
    except BundleError as exc:
        _fail(str(exc))
    if size != record["size_bytes"]:
        _fail(f"{what} size does not match the bundle")
    if digest != record["sha256"]:
        _fail(f"{what} SHA-256 does not match the bundle")
    return resolved


def _validate_evidence(
    value: Any,
    *,
    target_profile: dict[str, Any],
    trust_profile: dict[str, Any],
    statement_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    evidence = _exact_object(
        value,
        {"evidence_class", "hardware_attestation", "mock_attestation"},
        "evidence",
    )
    evidence_class = evidence["evidence_class"]
    if evidence_class != trust_profile["evidence_class"]:
        _fail("evidence class does not match the bound trust profile")
    if evidence_class not in target_profile["allowed_evidence_classes"]:
        _fail("evidence class is not allowed by the bound target profile")
    if target_profile["profile_id"] not in trust_profile["allowed_target_profiles"]:
        _fail("trust profile is not allowed for the bound target profile")

    hardware = evidence["hardware_attestation"]
    mock = evidence["mock_attestation"]
    if target_profile["profile_id"] == "dgx_spark_sm121":
        if evidence_class != "local_unattested" or hardware is not None:
            _fail("DGX Spark evidence must be local_unattested with hardware_attestation null")

    hardware_record: dict[str, Any] | None = None
    if evidence_class == "local_unattested":
        if hardware is not None or mock is not None:
            _fail("local_unattested evidence must not contain attestation")
    elif evidence_class == "mock_attested":
        if hardware is not None:
            _fail("mock evidence must have hardware_attestation null")
        marker = _exact_object(
            mock,
            {"format", "expected_report_data_sha256", "warning"},
            "mock attestation marker",
        )
        if (
            marker["format"] != "sparkinterval_mock_v1"
            or marker["expected_report_data_sha256"] != statement_sha256
            or marker["warning"] != "TEST ONLY - NOT HARDWARE EVIDENCE"
        ):
            _fail("invalid mock attestation marker")
    elif evidence_class == "hardware_attested":
        if mock is not None:
            _fail("hardware evidence must not contain a mock marker")
        hardware_record = _exact_object(
            hardware,
            {"format", "artifact", "expected_report_data_sha256"},
            "hardware attestation",
        )
        evidence_format = hardware_record["format"]
        if evidence_format not in trust_profile["accepted_attestation_formats"]:
            _fail("hardware attestation format is not accepted by the trust profile")
        if hardware_record["expected_report_data_sha256"] != statement_sha256:
            _fail("hardware attestation does not name the statement digest")
        _artifact_record(
            hardware_record["artifact"], "hardware attestation artifact", with_role=False
        )
    else:
        _fail(f"unknown evidence class: {evidence_class!r}")
    return evidence, hardware_record


def verify_bundle(
    bundle: Any,
    *,
    profiles_dir: str | os.PathLike[str] = DEFAULT_PROFILES_DIR,
    artifact_root: str | os.PathLike[str] | None = None,
    policy: str = INTEGRITY_POLICY,
    seen_nonces: MutableSet[str] | None = None,
    attestation_validator: AttestationValidator | None = None,
    operator_signature: Any | None = None,
    trusted_operator_public_key: str | os.PathLike[str] | None = None,
    openssl_executable: str | os.PathLike[str] = "openssl",
) -> dict[str, Any]:
    """Verify a parsed bundle.

    ``dgx_operator_signed`` requires artifact bytes, replay state, a detached
    Ed25519 signature, and a separately pinned operator public key.  It remains
    local evidence and never sets ``hardware_evidence``.
    ``hardware_production`` fails closed for either CPU or GPU targets unless
    artifact bytes are present, replay state is supplied, and
    ``attestation_validator`` confirms the platform evidence and report-data
    binding.  ``h100_production`` is the backward-compatible H100-specific
    form of that policy.  Merely selecting a policy or profile is never
    sufficient.
    """

    if policy not in POLICIES:
        _fail(f"unknown verification policy: {policy!r}")
    try:
        validate_json_value(bundle)
    except BundleError as exc:
        _fail(str(exc))
    top = _exact_object(
        bundle,
        {
            "schema_version",
            "bundle_kind",
            "statement",
            "statement_sha256",
            "evidence",
            "bundle_sha256",
        },
        "run bundle",
    )
    if top["schema_version"] != SCHEMA_VERSION or isinstance(
        top["schema_version"], bool
    ):
        _fail(f"unsupported schema_version: {top['schema_version']!r}")
    if top["bundle_kind"] != BUNDLE_KIND:
        _fail(f"unexpected bundle_kind: {top['bundle_kind']!r}")
    try:
        validate_sha256(top["statement_sha256"], "statement hash")
        validate_sha256(top["bundle_sha256"], "bundle hash")
    except BundleError as exc:
        _fail(str(exc))

    statement = _exact_object(
        top["statement"],
        {
            "target_profile",
            "trust_profile",
            "backend_kind",
            "algorithm",
            "input_artifact",
            "parameters",
            "domain_coverage",
            "output_artifact",
            "nonce",
            "build_artifacts",
            "execution_environment",
            "completion",
        },
        "run statement",
    )
    if canonical_sha256(statement) != top["statement_sha256"]:
        _fail("statement SHA-256 does not match the statement")

    core = {
        "schema_version": top["schema_version"],
        "bundle_kind": top["bundle_kind"],
        "statement": statement,
        "statement_sha256": top["statement_sha256"],
        "evidence": top["evidence"],
    }
    if canonical_sha256(core) != top["bundle_sha256"]:
        _fail("bundle SHA-256 does not match the bundle")

    catalog = _load_catalog(profiles_dir)
    target_profile = _resolve_profile_reference(
        statement["target_profile"], "target", catalog
    )
    trust_profile = _resolve_profile_reference(
        statement["trust_profile"], "trust", catalog
    )
    backend_kind = statement["backend_kind"]
    if not isinstance(backend_kind, str) or backend_kind not in BACKEND_KINDS:
        _fail("run statement backend_kind must be cpu or gpu")
    if backend_kind != target_profile["backend_kind"]:
        _fail("run statement backend_kind does not match the bound target profile")

    algorithm = _exact_object(
        statement["algorithm"],
        {"algorithm_id", "definition_sha256"},
        "algorithm",
    )
    algorithm_id = algorithm["algorithm_id"]
    if not isinstance(algorithm_id, str) or ALGORITHM_ID_RE.fullmatch(algorithm_id) is None:
        _fail("invalid algorithm_id")
    try:
        validate_sha256(algorithm["definition_sha256"], "algorithm definition hash")
        validate_nonce(statement["nonce"])
    except BundleError as exc:
        _fail(str(exc))

    input_record = _artifact_record(
        statement["input_artifact"], "input artifact", with_role=False
    )
    output_record = _artifact_record(
        statement["output_artifact"], "output artifact", with_role=False
    )
    _bound_json(statement["parameters"], "parameters")
    _bound_json(statement["domain_coverage"], "domain coverage")
    _bound_json(statement["execution_environment"], "execution environment")
    try:
        validate_completion(statement["completion"])
    except BundleError as exc:
        _fail(str(exc))

    raw_build_records = statement["build_artifacts"]
    if not isinstance(raw_build_records, list) or not raw_build_records:
        _fail("at least one build artifact is required")
    build_records = [
        _artifact_record(item, f"build artifact {index}", with_role=True)
        for index, item in enumerate(raw_build_records)
    ]
    if build_records != sorted(
        build_records, key=lambda item: (item["role"], item["path"])
    ):
        _fail("build artifacts are not in canonical role/path order")
    identities = [(item["role"], item["path"]) for item in build_records]
    if len(identities) != len(set(identities)):
        _fail("duplicate build artifact role/path pair")
    build_roles = {item["role"] for item in build_records}
    if "host_executable" not in build_roles:
        _fail("build artifacts do not bind the exact host_executable")
    has_gpu_image = bool(build_roles & GPU_EXECUTION_ROLES)
    if backend_kind == "gpu" and not has_gpu_image:
        _fail("GPU target build artifacts do not bind a GPU execution image")
    if backend_kind == "cpu" and has_gpu_image:
        _fail("CPU target build artifacts contain a GPU execution image")
    if input_record["path"] == output_record["path"]:
        _fail("input and output artifacts must use distinct paths")

    evidence, hardware_record = _validate_evidence(
        top["evidence"],
        target_profile=target_profile,
        trust_profile=trust_profile,
        statement_sha256=top["statement_sha256"],
    )

    resolved_root: Path | None = None
    attestation_path: Path | None = None
    if artifact_root is not None:
        resolved_root = _resolve_root(artifact_root)
        _verify_artifact_file(input_record, resolved_root, "input artifact")
        _verify_artifact_file(output_record, resolved_root, "output artifact")
        for index, record in enumerate(build_records):
            _verify_artifact_file(record, resolved_root, f"build artifact {index}")
        if hardware_record is not None:
            attestation_path = _verify_artifact_file(
                hardware_record["artifact"],
                resolved_root,
                "hardware attestation artifact",
            )

    nonce = statement["nonce"]
    if seen_nonces is not None and nonce in seen_nonces:
        _fail("replayed nonce")

    hardware_evidence = False
    operator_signature_result: dict[str, Any] | None = None
    if policy == DGX_OPERATOR_SIGNED_POLICY:
        if target_profile["profile_id"] != "dgx_spark_sm121":
            _fail("DGX operator-signed policy requires target profile dgx_spark_sm121")
        if trust_profile["profile_id"] != "local_unattested":
            _fail("DGX operator-signed policy requires local_unattested trust")
        if evidence["evidence_class"] != "local_unattested":
            _fail("DGX operator-signed policy requires local_unattested evidence")
        if resolved_root is None:
            _fail("DGX operator-signed policy requires all artifact bytes")
        if seen_nonces is None:
            _fail("DGX operator-signed policy requires persistent replay protection")
        if operator_signature is None:
            _fail("DGX operator-signed policy requires a detached operator signature")
        if trusted_operator_public_key is None:
            _fail("DGX operator-signed policy requires a pinned operator public key")
        try:
            operator_signature_result = operator_signing.verify_signature(
                top,
                operator_signature,
                trusted_operator_public_key,
                openssl=openssl_executable,
                bundle_bytes=canonical_json_bytes(top),
            )
        except operator_signing.LocalSignatureError as exc:
            _fail(f"operator signature verification failed: {exc}")
    elif operator_signature is not None or trusted_operator_public_key is not None:
        _fail("operator signature inputs require policy dgx_operator_signed")

    if policy in (HARDWARE_PRODUCTION_POLICY, H100_PRODUCTION_POLICY):
        h100_specific = policy == H100_PRODUCTION_POLICY
        policy_name = "H100 production" if h100_specific else "hardware production"
        if h100_specific and target_profile["profile_id"] != "h100_sm90":
            _fail("H100 production policy requires target profile h100_sm90")
        if h100_specific and trust_profile["profile_id"] != "h100_hardware_attested":
            _fail(
                "H100 production policy rejects local and mock trust profiles as hardware evidence"
            )
        if evidence["evidence_class"] != "hardware_attested":
            _fail(f"{policy_name} policy requires hardware_attested evidence")
        if not trust_profile["production_hardware_evidence"]:
            _fail("the trust profile is not authorized for production hardware evidence")
        if resolved_root is None or attestation_path is None:
            _fail(
                f"{policy_name} policy requires all artifact bytes, including attestation"
            )
        if seen_nonces is None:
            _fail(f"{policy_name} policy requires persistent replay protection")
        if attestation_validator is None:
            if h100_specific:
                _fail("no trusted H100 attestation verifier is configured")
            _fail("no trusted hardware-production attestation verifier is configured")
        assert hardware_record is not None
        try:
            valid_attestation = attestation_validator(
                attestation_path,
                hardware_record["format"],
                top["statement_sha256"],
            )
        except Exception as exc:
            if h100_specific:
                _fail(f"H100 attestation verifier failed: {exc}")
            _fail(f"hardware-production attestation verifier failed: {exc}")
        if valid_attestation is not True:
            if h100_specific:
                _fail(
                    "H100 attestation verifier rejected the evidence or report-data binding"
                )
            _fail(
                "hardware-production attestation verifier rejected the evidence or report-data binding"
            )
        hardware_evidence = True

    if seen_nonces is not None:
        seen_nonces.add(nonce)

    if operator_signature_result is not None:
        assurance = operator_signing.ASSURANCE
    elif hardware_evidence:
        assurance = trust_profile["profile_id"]
    elif evidence["evidence_class"] == "mock_attested":
        assurance = "mock_only_not_hardware_evidence"
    elif evidence["evidence_class"] == "local_unattested":
        assurance = "local_record_not_hardware_evidence"
    else:
        assurance = "hardware_attestation_structurally_present_but_unverified"

    result = {
        "accepted": True,
        "policy": policy,
        "statement_sha256": top["statement_sha256"],
        "bundle_sha256": top["bundle_sha256"],
        "target_profile": target_profile["profile_id"],
        "trust_profile": trust_profile["profile_id"],
        "backend_kind": backend_kind,
        "evidence_class": evidence["evidence_class"],
        "artifacts_verified": resolved_root is not None,
        "hardware_evidence": hardware_evidence,
        "assurance": assurance,
    }
    if operator_signature_result is not None:
        result["operator_signature_valid"] = True
        result["operator_key_id"] = operator_signature_result["key_id"]
    return result


def verify_bundle_file(
    path: str | os.PathLike[str], **kwargs: Any
) -> dict[str, Any]:
    try:
        bundle = load_canonical_json(path)
    except BundleError as exc:
        _fail(str(exc))
    return verify_bundle(bundle, **kwargs)


def _nonce_already_recorded(database: Path, nonce: str) -> bool:
    database.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS accepted_nonces "
                "(nonce TEXT PRIMARY KEY, statement_sha256 TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT 1 FROM accepted_nonces WHERE nonce = ?", (nonce,)
            ).fetchone()
            return row is not None
    except sqlite3.Error as exc:
        _fail(f"cannot read replay database {database}: {exc}")


def _record_nonce(database: Path, nonce: str, statement_sha256: str) -> None:
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS accepted_nonces "
                "(nonce TEXT PRIMARY KEY, statement_sha256 TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO accepted_nonces (nonce, statement_sha256) VALUES (?, ?)",
                (nonce, statement_sha256),
            )
    except sqlite3.IntegrityError as exc:
        _fail("replayed nonce")
    except sqlite3.Error as exc:
        _fail(f"cannot update replay database {database}: {exc}")


def external_attestation_validator(
    executable: str | os.PathLike[str], timeout_seconds: int = 120
) -> AttestationValidator:
    try:
        verifier = Path(executable).resolve(strict=True)
    except OSError as exc:
        _fail(f"cannot resolve attestation verifier {executable}: {exc}")
    if not verifier.is_file() or not os.access(verifier, os.X_OK):
        _fail(f"attestation verifier is not executable: {verifier}")

    def validate(evidence: Path, evidence_format: str, expected_digest: str) -> bool:
        completed = subprocess.run(
            [
                str(verifier),
                "--evidence",
                str(evidence),
                "--format",
                evidence_format,
                "--expected-report-data-sha256",
                expected_digest,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        return completed.returncode == 0

    return validate


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    parser.add_argument("--profiles-dir", default=str(DEFAULT_PROFILES_DIR))
    parser.add_argument("--artifact-root")
    parser.add_argument("--policy", choices=POLICIES, default=INTEGRITY_POLICY)
    parser.add_argument(
        "--replay-db",
        help=(
            "SQLite nonce registry; required for dgx_operator_signed, "
            "hardware_production, and h100_production"
        ),
    )
    parser.add_argument(
        "--attestation-verifier",
        help="trusted external platform-attestation evidence verifier executable",
    )
    parser.add_argument(
        "--operator-signature",
        help="canonical detached DGX operator-signature JSON",
    )
    parser.add_argument(
        "--trusted-operator-key",
        help="separately pinned Ed25519 operator public key in PEM form",
    )
    parser.add_argument(
        "--openssl",
        default="openssl",
        help="OpenSSL executable used for the DGX operator signature",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        bundle = load_canonical_json(args.bundle)
        if not isinstance(bundle, dict) or not isinstance(bundle.get("statement"), dict):
            _fail("run bundle does not contain a statement object")
        nonce = bundle["statement"].get("nonce")
        validate_nonce(nonce)

        seen: set[str] | None = None
        replay_db: Path | None = None
        if args.replay_db is not None:
            replay_db = Path(args.replay_db)
            seen = set()
            if _nonce_already_recorded(replay_db, nonce):
                seen.add(nonce)

        validator = None
        if args.attestation_verifier is not None:
            validator = external_attestation_validator(args.attestation_verifier)

        signature = None
        if args.operator_signature is not None:
            signature = operator_signing.load_signature(args.operator_signature)

        result = verify_bundle(
            bundle,
            profiles_dir=args.profiles_dir,
            artifact_root=args.artifact_root,
            policy=args.policy,
            seen_nonces=seen,
            attestation_validator=validator,
            operator_signature=signature,
            trusted_operator_public_key=args.trusted_operator_key,
            openssl_executable=args.openssl,
        )
        if replay_db is not None:
            _record_nonce(replay_db, nonce, result["statement_sha256"])
    except (BundleError, VerificationError) as exc:
        print(f"verify_run_bundle: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
