#!/usr/bin/env python3
"""Create a canonical SparkInterval run bundle.

This module intentionally uses only the Python standard library.  It records a
claim and the hashes of the files involved in that claim; it does not turn a
local record into hardware evidence.  Hardware evidence is accepted only by
the production policy in ``verify_run_bundle.py`` and only when a separate
attestation verifier validates it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
BUNDLE_KIND = "sparkinterval_run_bundle"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ROLE_RE = PROFILE_ID_RE
ALGORITHM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z$"
)

TARGET_PROFILE_KEYS = {
    "profile_version",
    "profile_kind",
    "profile_id",
    "host_architecture",
    "gpu_architecture",
    "device_family",
    "confidential_compute",
    "allowed_evidence_classes",
    "description",
}
TRUST_PROFILE_KEYS = {
    "profile_version",
    "profile_kind",
    "profile_id",
    "evidence_class",
    "production_hardware_evidence",
    "requires_hardware_attestation",
    "requires_mock_attestation",
    "allowed_target_profiles",
    "accepted_attestation_formats",
    "description",
}
EVIDENCE_CLASSES = {
    "local_unattested",
    "mock_attested",
    "hardware_attested",
}
GPU_EXECUTION_ROLES = {"gpu_executable", "gpu_cubin", "gpu_fatbin", "gpu_ptx"}


class BundleError(ValueError):
    """A bundle or one of its inputs is invalid."""


def _reject_float(value: str) -> None:
    raise BundleError(f"JSON floating-point values are forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise BundleError(f"non-finite JSON value is forbidden: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def validate_json_value(value: Any, path: str = "$") -> None:
    """Reject values outside the canonical integer-only JSON subset."""

    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise BundleError(f"JSON floating-point value is forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BundleError(f"JSON object key is not a string at {path}")
            validate_json_value(item, f"{path}.{key}")
        return
    raise BundleError(f"value at {path} is not representable in canonical JSON")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode the project canonical JSON subset as UTF-8, without a newline."""

    validate_json_value(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise BundleError(f"cannot encode canonical JSON: {exc}") from exc
    return encoded.encode("utf-8", errors="strict")


def parse_json_bytes(data: bytes, source: str = "JSON input") -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BundleError(f"{source} is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except BundleError:
        raise
    except json.JSONDecodeError as exc:
        raise BundleError(f"cannot parse {source}: {exc}") from exc
    validate_json_value(value)
    return value


def load_json(path: str | os.PathLike[str]) -> Any:
    json_path = Path(path)
    try:
        data = json_path.read_bytes()
    except OSError as exc:
        raise BundleError(f"cannot read {json_path}: {exc}") from exc
    return parse_json_bytes(data, str(json_path))


def load_canonical_json(path: str | os.PathLike[str]) -> Any:
    json_path = Path(path)
    try:
        data = json_path.read_bytes()
    except OSError as exc:
        raise BundleError(f"cannot read {json_path}: {exc}") from exc
    value = parse_json_bytes(data, str(json_path))
    if data != canonical_json_bytes(value):
        raise BundleError(f"{json_path} is not canonical JSON")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _require_exact_keys(value: Any, expected: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError(f"{what} must be a JSON object")
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        unexpected = sorted(keys - expected)
        raise BundleError(
            f"{what} has wrong fields (missing={missing}, unexpected={unexpected})"
        )
    return value


def _require_nonempty_string(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise BundleError(f"{what} must be a non-empty string")
    return value


def _require_bool(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise BundleError(f"{what} must be a boolean")
    return value


def _require_string_list(value: Any, what: str, *, nonempty: bool) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty" if nonempty else "a"
        raise BundleError(f"{what} must be {qualifier} string array")
    if any(not isinstance(item, str) or not item for item in value):
        raise BundleError(f"{what} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise BundleError(f"{what} must not contain duplicates")
    return value


def validate_profile(profile: Any, expected_kind: str | None = None) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise BundleError("profile must be a JSON object")
    kind = profile.get("profile_kind")
    if expected_kind is not None and kind != expected_kind:
        raise BundleError(f"expected a {expected_kind} profile, got {kind!r}")
    if kind == "target":
        result = _require_exact_keys(profile, TARGET_PROFILE_KEYS, "target profile")
        if result["profile_version"] != 1 or isinstance(
            result["profile_version"], bool
        ):
            raise BundleError("target profile_version must be integer 1")
        profile_id = result["profile_id"]
        if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
            raise BundleError("invalid target profile_id")
        for key in (
            "host_architecture",
            "gpu_architecture",
            "device_family",
            "confidential_compute",
            "description",
        ):
            _require_nonempty_string(result[key], f"target profile {key}")
        classes = _require_string_list(
            result["allowed_evidence_classes"],
            "target profile allowed_evidence_classes",
            nonempty=True,
        )
        if not set(classes) <= EVIDENCE_CLASSES:
            raise BundleError("target profile contains an unknown evidence class")
        return result
    if kind == "trust":
        result = _require_exact_keys(profile, TRUST_PROFILE_KEYS, "trust profile")
        if result["profile_version"] != 1 or isinstance(
            result["profile_version"], bool
        ):
            raise BundleError("trust profile_version must be integer 1")
        profile_id = result["profile_id"]
        if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
            raise BundleError("invalid trust profile_id")
        evidence_class = result["evidence_class"]
        if evidence_class not in EVIDENCE_CLASSES:
            raise BundleError("trust profile contains an unknown evidence class")
        for key in (
            "production_hardware_evidence",
            "requires_hardware_attestation",
            "requires_mock_attestation",
        ):
            _require_bool(result[key], f"trust profile {key}")
        targets = _require_string_list(
            result["allowed_target_profiles"],
            "trust profile allowed_target_profiles",
            nonempty=True,
        )
        if any(PROFILE_ID_RE.fullmatch(item) is None for item in targets):
            raise BundleError("trust profile contains an invalid target profile id")
        formats = _require_string_list(
            result["accepted_attestation_formats"],
            "trust profile accepted_attestation_formats",
            nonempty=False,
        )
        if any(PROFILE_ID_RE.fullmatch(item) is None for item in formats):
            raise BundleError("trust profile contains an invalid attestation format")
        _require_nonempty_string(result["description"], "trust profile description")

        requires_hardware = result["requires_hardware_attestation"]
        requires_mock = result["requires_mock_attestation"]
        production = result["production_hardware_evidence"]
        if requires_hardware and requires_mock:
            raise BundleError("a trust profile cannot require hardware and mock evidence")
        if evidence_class == "local_unattested":
            if requires_hardware or requires_mock or production or formats:
                raise BundleError("local_unattested trust profile has unsafe settings")
        elif evidence_class == "mock_attested":
            if requires_hardware or not requires_mock or production:
                raise BundleError("mock_attested trust profile has unsafe settings")
        elif evidence_class == "hardware_attested":
            if not requires_hardware or requires_mock or not production or not formats:
                raise BundleError("hardware_attested trust profile has unsafe settings")
        return result
    raise BundleError(f"unknown profile_kind: {kind!r}")


def load_profile(
    path: str | os.PathLike[str], expected_kind: str
) -> dict[str, Any]:
    return validate_profile(load_json(path), expected_kind)


def profile_reference(profile: dict[str, Any]) -> dict[str, str]:
    validate_profile(profile)
    return {
        "profile_id": profile["profile_id"],
        "sha256": canonical_sha256(profile),
    }


def _resolved_root(root: str | os.PathLike[str]) -> Path:
    try:
        result = Path(root).resolve(strict=True)
    except OSError as exc:
        raise BundleError(f"cannot resolve artifact root {root}: {exc}") from exc
    if not result.is_dir():
        raise BundleError(f"artifact root is not a directory: {result}")
    return result


def _relative_artifact_path(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise BundleError(f"artifact {path} is outside bundle root {root}") from exc
    if relative == Path("."):
        raise BundleError("artifact path cannot be the bundle root")
    posix = relative.as_posix()
    parsed = PurePosixPath(posix)
    if parsed.is_absolute() or ".." in parsed.parts or "." in parsed.parts:
        raise BundleError(f"unsafe artifact path: {posix!r}")
    return posix


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            before = os.fstat(source.fileno())
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(source.fileno())
    except OSError as exc:
        raise BundleError(f"cannot hash artifact {path}: {exc}") from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise BundleError(f"artifact changed while it was being hashed: {path}")
    return digest.hexdigest(), before.st_size


def artifact_record(
    path: str | os.PathLike[str],
    root: str | os.PathLike[str] | Path,
    *,
    role: str | None = None,
) -> dict[str, Any]:
    resolved_root = root if isinstance(root, Path) else _resolved_root(root)
    try:
        resolved_path = Path(path).resolve(strict=True)
    except OSError as exc:
        raise BundleError(f"cannot resolve artifact {path}: {exc}") from exc
    if not resolved_path.is_file():
        raise BundleError(f"artifact is not a regular file: {resolved_path}")
    relative = _relative_artifact_path(resolved_path, resolved_root)
    digest, size = hash_file(resolved_path)
    result: dict[str, Any] = {
        "path": relative,
        "sha256": digest,
        "size_bytes": size,
    }
    if role is not None:
        if ROLE_RE.fullmatch(role) is None:
            raise BundleError(f"invalid build artifact role: {role!r}")
        result["role"] = role
    return result


def _bound_json(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise BundleError(f"{what} must be a non-empty JSON object")
    validate_json_value(value)
    return {"value": value, "canonical_sha256": canonical_sha256(value)}


def validate_sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise BundleError(f"{what} must be a lowercase hexadecimal SHA-256")
    return value


def validate_nonce(value: Any) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise BundleError("nonce must be 32 bytes encoded as lowercase hexadecimal")
    return value


def _parse_utc(value: Any, what: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise BundleError(f"{what} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BundleError(f"invalid {what}: {value!r}") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise BundleError(f"{what} must use UTC")
    return parsed


def validate_completion(value: Any) -> dict[str, Any]:
    keys = {
        "status",
        "exit_code",
        "expected_output_count",
        "written_output_count",
        "cuda_errors",
        "start_time_utc",
        "end_time_utc",
    }
    result = _require_exact_keys(value, keys, "completion record")
    if result["status"] != "success":
        raise BundleError("a run bundle can only claim a successfully completed run")
    if result["exit_code"] != 0 or isinstance(result["exit_code"], bool):
        raise BundleError("successful completion requires integer exit_code 0")
    expected = result["expected_output_count"]
    written = result["written_output_count"]
    if (
        not isinstance(expected, int)
        or isinstance(expected, bool)
        or expected < 1
        or not isinstance(written, int)
        or isinstance(written, bool)
        or written != expected
    ):
        raise BundleError("all expected outputs must have been written")
    if result["cuda_errors"] != []:
        raise BundleError("successful completion requires an empty cuda_errors array")
    started = _parse_utc(result["start_time_utc"], "completion start_time_utc")
    ended = _parse_utc(result["end_time_utc"], "completion end_time_utc")
    if ended < started:
        raise BundleError("completion end_time_utc precedes start_time_utc")
    return result


def _check_profile_compatibility(
    target_profile: dict[str, Any], trust_profile: dict[str, Any]
) -> None:
    target_id = target_profile["profile_id"]
    evidence_class = trust_profile["evidence_class"]
    if evidence_class not in target_profile["allowed_evidence_classes"]:
        raise BundleError(
            f"target profile {target_id} does not allow {evidence_class} evidence"
        )
    if target_id not in trust_profile["allowed_target_profiles"]:
        raise BundleError(
            f"trust profile {trust_profile['profile_id']} does not allow target {target_id}"
        )
    if target_id == "dgx_spark_sm121" and evidence_class != "local_unattested":
        raise BundleError("DGX Spark bundles must use local_unattested evidence")


def create_bundle(
    *,
    root: str | os.PathLike[str],
    target_profile: dict[str, Any],
    trust_profile: dict[str, Any],
    algorithm_id: str,
    algorithm_definition_sha256: str,
    input_path: str | os.PathLike[str],
    parameters: dict[str, Any],
    domain_coverage: dict[str, Any],
    output_path: str | os.PathLike[str],
    nonce: str,
    build_artifacts: Sequence[tuple[str, str | os.PathLike[str]]],
    execution_environment: dict[str, Any],
    completion: dict[str, Any],
    hardware_attestation_path: str | os.PathLike[str] | None = None,
    hardware_attestation_format: str | None = None,
) -> dict[str, Any]:
    """Construct, validate, and hash a run bundle value."""

    validate_profile(target_profile, "target")
    validate_profile(trust_profile, "trust")
    _check_profile_compatibility(target_profile, trust_profile)
    if not isinstance(algorithm_id, str) or ALGORITHM_ID_RE.fullmatch(algorithm_id) is None:
        raise BundleError(f"invalid algorithm_id: {algorithm_id!r}")
    validate_sha256(algorithm_definition_sha256, "algorithm definition hash")
    validate_nonce(nonce)
    validate_completion(completion)
    resolved_root = _resolved_root(root)

    if not build_artifacts:
        raise BundleError("at least one build artifact is required")
    build_records = [
        artifact_record(path, resolved_root, role=role)
        for role, path in build_artifacts
    ]
    build_records.sort(key=lambda item: (item["role"], item["path"]))
    identities = [(item["role"], item["path"]) for item in build_records]
    if len(set(identities)) != len(identities):
        raise BundleError("duplicate build artifact role/path pair")
    build_roles = {item["role"] for item in build_records}
    if "host_executable" not in build_roles:
        raise BundleError("build artifacts must bind the exact host_executable")
    if not build_roles & GPU_EXECUTION_ROLES:
        raise BundleError("build artifacts must bind an exact GPU execution image")

    input_record = artifact_record(input_path, resolved_root)
    output_record = artifact_record(output_path, resolved_root)
    if input_record["path"] == output_record["path"]:
        raise BundleError("input and output artifacts must use distinct paths")

    statement: dict[str, Any] = {
        "target_profile": profile_reference(target_profile),
        "trust_profile": profile_reference(trust_profile),
        "algorithm": {
            "algorithm_id": algorithm_id,
            "definition_sha256": algorithm_definition_sha256,
        },
        "input_artifact": input_record,
        "parameters": _bound_json(parameters, "parameters"),
        "domain_coverage": _bound_json(domain_coverage, "domain_coverage"),
        "output_artifact": output_record,
        "nonce": nonce,
        "build_artifacts": build_records,
        "execution_environment": _bound_json(
            execution_environment, "execution_environment"
        ),
        "completion": completion,
    }
    statement_sha256 = canonical_sha256(statement)

    evidence_class = trust_profile["evidence_class"]
    hardware_attestation: dict[str, Any] | None = None
    mock_attestation: dict[str, Any] | None = None
    if evidence_class == "local_unattested":
        if hardware_attestation_path is not None or hardware_attestation_format is not None:
            raise BundleError("local_unattested bundles cannot contain attestation")
    elif evidence_class == "mock_attested":
        if hardware_attestation_path is not None or hardware_attestation_format is not None:
            raise BundleError("mock bundles cannot contain hardware attestation")
        mock_attestation = {
            "format": "sparkinterval_mock_v1",
            "expected_report_data_sha256": statement_sha256,
            "warning": "TEST ONLY - NOT HARDWARE EVIDENCE",
        }
    elif evidence_class == "hardware_attested":
        if hardware_attestation_path is None or hardware_attestation_format is None:
            raise BundleError("hardware-attested bundles require an evidence artifact and format")
        if hardware_attestation_format not in trust_profile["accepted_attestation_formats"]:
            raise BundleError(
                f"attestation format {hardware_attestation_format!r} is not accepted by the trust profile"
            )
        hardware_attestation = {
            "format": hardware_attestation_format,
            "artifact": artifact_record(hardware_attestation_path, resolved_root),
            "expected_report_data_sha256": statement_sha256,
        }
    else:  # pragma: no cover - validate_profile already prevents this
        raise BundleError(f"unknown evidence class: {evidence_class!r}")

    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bundle_kind": BUNDLE_KIND,
        "statement": statement,
        "statement_sha256": statement_sha256,
        "evidence": {
            "evidence_class": evidence_class,
            "hardware_attestation": hardware_attestation,
            "mock_attestation": mock_attestation,
        },
    }
    bundle = dict(core)
    bundle["bundle_sha256"] = canonical_sha256(core)
    return bundle


def write_bundle(bundle: dict[str, Any], path: str | os.PathLike[str]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(bundle)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise BundleError(f"cannot write bundle {destination}: {exc}") from exc


def _parse_build_artifact(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("build artifact must be ROLE=PATH")
    role, path = value.split("=", 1)
    if ROLE_RE.fullmatch(role) is None or not path:
        raise argparse.ArgumentTypeError("build artifact must be valid ROLE=PATH")
    return role, path


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="root containing all bound artifacts")
    parser.add_argument("--target-profile", required=True)
    parser.add_argument("--trust-profile", required=True)
    parser.add_argument("--algorithm-id", required=True)
    parser.add_argument("--algorithm-definition-sha256", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--parameters", required=True, help="integer-only JSON object")
    parser.add_argument("--domain-coverage", required=True, help="integer-only JSON object")
    parser.add_argument("--output", required=True)
    parser.add_argument("--nonce", required=True, help="challenger nonce: 64 lowercase hex characters")
    parser.add_argument(
        "--build-artifact",
        action="append",
        type=_parse_build_artifact,
        required=True,
        metavar="ROLE=PATH",
    )
    parser.add_argument("--execution-environment", required=True, help="integer-only JSON object")
    parser.add_argument("--completion", required=True, help="successful completion JSON object")
    parser.add_argument("--hardware-attestation")
    parser.add_argument("--hardware-attestation-format")
    parser.add_argument("--out", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        bundle = create_bundle(
            root=args.root,
            target_profile=load_profile(args.target_profile, "target"),
            trust_profile=load_profile(args.trust_profile, "trust"),
            algorithm_id=args.algorithm_id,
            algorithm_definition_sha256=args.algorithm_definition_sha256,
            input_path=args.input,
            parameters=load_json(args.parameters),
            domain_coverage=load_json(args.domain_coverage),
            output_path=args.output,
            nonce=args.nonce,
            build_artifacts=args.build_artifact,
            execution_environment=load_json(args.execution_environment),
            completion=load_json(args.completion),
            hardware_attestation_path=args.hardware_attestation,
            hardware_attestation_format=args.hardware_attestation_format,
        )
        write_bundle(bundle, args.out)
    except BundleError as exc:
        print(f"create_run_bundle: {exc}", file=sys.stderr)
        return 2
    print(
        canonical_json_bytes(
            {
                "bundle_sha256": bundle["bundle_sha256"],
                "evidence_class": bundle["evidence"]["evidence_class"],
                "output": str(Path(args.out)),
                "statement_sha256": bundle["statement_sha256"],
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
