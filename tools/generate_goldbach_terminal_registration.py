#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and audit a post-run finite-Goldbach terminal identity candidate.

The command never installs a Lean registration.  Production admission remains
disabled until the canonical bundle has been independently reviewed and its
exact pins are deliberately added to Lean and to the Python allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "tools", ROOT / "attestation", ROOT / "azure"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from create_run_bundle import (  # noqa: E402
    canonical_json_bytes as wire_json_bytes,
    canonical_sha256 as wire_sha256,
    load_canonical_json,
)
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
    registered_invocation_expected,
)
from measured_runner import _closure_manifest, validate_job_spec  # noqa: E402
from tg_goldbach_10pow27_azure_measured_workload import (  # noqa: E402
    _validate_cpu_result,
    _validate_h100_result,
    verify_retained_export_archive,
)
from tg_verifier.azure_cpu_goldbach_10pow27_workload_factory import (  # noqa: E402
    CAMPAIGN_ID,
    REGISTERED_INVOCATION,
    expected_registered_hashes,
    make_factory,
)
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (  # noqa: E402
    PHASE_ID as H100_PHASE,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GoldbachBuildAdmission,
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from tg_verifier.goldbach_terminal_identity import (  # noqa: E402
    BUNDLE_KIND,
    CHILD_INDEX_KIND,
    NOT_APPLICABLE_DIGEST,
    GoldbachTerminalIdentityError,
    child_identity_commitment,
    check_lean_terminal_pins,
    expected_child_topology,
    lean_pin_values,
    render_lean_pin_candidate,
    terminal_execution_binding,
    validate_child_identity_commitment,
    validate_terminal_execution_binding,
    validate_terminal_identity_bundle,
)


INDEX_FIELDS = {"entries", "kind", "schema_version"}
INDEX_ENTRY_FIELDS = {"export", "phase", "receipt", "shard_index"}
FILE_PIN_FIELDS = {"path", "sha256", "size_bytes"}
ARTIFACT_FIELDS = {
    "executable", "path", "role", "sha256", "size_bytes", "statement_role",
}


class GoldbachTerminalGeneratorError(RuntimeError):
    """A post-run file, signed child, or terminal identity differed."""


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while publishing terminal identity")
        view = view[written:]


def _safe_index_path(root: Path, value: Any, what: str) -> Path:
    if not isinstance(value, str):
        raise GoldbachTerminalGeneratorError(f"{what} path must be text")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise GoldbachTerminalGeneratorError(
            f"{what} path must be canonical and index-relative"
        )
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise GoldbachTerminalGeneratorError(
            f"{what} path escapes or is absent: {error}"
        ) from error
    if candidate.is_symlink() or not resolved.is_file():
        raise GoldbachTerminalGeneratorError(
            f"{what} must be a nonsymlink regular file"
        )
    return resolved


def _index_pin(root: Path, value: Any, what: str) -> Path:
    if not isinstance(value, dict) or set(value) != FILE_PIN_FIELDS:
        raise GoldbachTerminalGeneratorError(f"{what} pin has wrong fields")
    path = _safe_index_path(root, value["path"], what)
    if hash_file_once(path) != (value["sha256"], value["size_bytes"]):
        raise GoldbachTerminalGeneratorError(f"{what} differs from its pin")
    return path


def _child_identity(
    receipt: Mapping[str, Any], phase: str, shard_index: int,
) -> dict[str, Any]:
    claim = receipt["claim"]
    return {
        "algorithm_hash": claim["algorithm_hash"],
        "algorithm_id": claim["algorithm_id"],
        "artifacts": dict(claim["artifacts"]),
        "backend": receipt["backend"],
        "claim_sha256": wire_sha256(claim),
        "domain_hash": claim["domain_hash"],
        "group_id": f"{CAMPAIGN_ID}::{phase}",
        "input_hash": claim["input_hash"],
        "job_projection_sha256": (
            claim["artifacts"]["kernel_manifest_hash"]
            if phase == H100_PHASE
            else NOT_APPLICABLE_DIGEST
        ),
        "output_hash": claim["output_hash"],
        "parameters_hash": claim["parameters_hash"],
        "phase": phase,
        "receipt_sha256": receipt["receipt_sha256"],
        "shard_index": shard_index,
    }


def load_child_identities(
    index_path: Path,
    *,
    key_manifest: Path,
    admission: GoldbachBuildAdmission,
    allow_development_key: bool = False,
) -> list[dict[str, Any]]:
    """Verify all 8,517 signed nonterminal nodes and their retained exports."""

    try:
        value = load_json(index_path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise GoldbachTerminalGeneratorError(
            f"cannot load canonical child receipt index: {error}"
        ) from error
    if (
        not isinstance(value, dict)
        or set(value) != INDEX_FIELDS
        or value["kind"] != CHILD_INDEX_KIND
        or value["schema_version"] != 1
        or not isinstance(value["entries"], list)
    ):
        raise GoldbachTerminalGeneratorError(
            "child receipt index has wrong fields/kind/version"
        )
    expected = expected_child_topology()
    if len(value["entries"]) != len(expected):
        raise GoldbachTerminalGeneratorError(
            "child receipt index does not cover the complete DAG"
        )
    index_root = index_path.resolve(strict=True).parent
    identities: list[dict[str, Any]] = []
    topology: list[tuple[str, int]] = []
    for position, entry in enumerate(value["entries"]):
        if not isinstance(entry, dict) or set(entry) != INDEX_ENTRY_FIELDS:
            raise GoldbachTerminalGeneratorError(
                f"child receipt index entry {position} has wrong fields"
            )
        phase = entry["phase"]
        shard_index = entry["shard_index"]
        if (
            not isinstance(phase, str)
            or isinstance(shard_index, bool)
            or not isinstance(shard_index, int)
            or shard_index < 0
        ):
            raise GoldbachTerminalGeneratorError(
                f"child receipt index entry {position} has invalid topology"
            )
        receipt_path = _index_pin(
            index_root, entry["receipt"], f"child receipt {position}"
        )
        export_path = _index_pin(
            index_root, entry["export"], f"child export {position}"
        )
        try:
            receipt = load_verified_receipt(
                receipt_path,
                key_manifest=key_manifest,
                allow_development_key=allow_development_key,
            )
        except Exception as error:
            raise GoldbachTerminalGeneratorError(
                f"child receipt {position} failed signature review: {error}"
            ) from error
        if phase == H100_PHASE:
            _validate_h100_result(receipt, shard_index, admission)
            verify_retained_export_archive(export_path, phase, shard_index)
        else:
            _validate_cpu_result(receipt, phase, shard_index, export_path)
        identities.append(_child_identity(receipt, phase, shard_index))
        topology.append((phase, shard_index))
    if tuple(sorted(topology)) != expected or len(set(topology)) != len(expected):
        raise GoldbachTerminalGeneratorError(
            "child receipt index has a gap, duplicate, or foreign node"
        )
    identities.sort(key=lambda item: (item["phase"], item["shard_index"]))
    return identities


def _artifact_path(root: Path, record: Mapping[str, Any]) -> Path:
    if not isinstance(record, dict) or set(record) != ARTIFACT_FIELDS:
        raise GoldbachTerminalGeneratorError(
            "terminal artifact closure record has wrong fields"
        )
    path = _safe_index_path(root, record["path"], "terminal artifact")
    if hash_file_once(path) != (record["sha256"], record["size_bytes"]):
        raise GoldbachTerminalGeneratorError(
            f"terminal artifact differs from its record: {record['path']}"
        )
    executable = bool(path.stat().st_mode & 0o111)
    if record["executable"] is not executable:
        raise GoldbachTerminalGeneratorError(
            f"terminal artifact executable mode differs: {record['path']}"
        )
    return path


def _one_role(
    records: list[dict[str, Any]], field: str, value: str,
) -> dict[str, Any]:
    rows = [record for record in records if record[field] == value]
    if len(rows) != 1:
        raise GoldbachTerminalGeneratorError(
            f"terminal closure requires exactly one {field}={value}"
        )
    return rows[0]


def _file_value(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    path = _artifact_path(root, record)
    value = load_canonical_json(path)
    if not isinstance(value, dict):
        raise GoldbachTerminalGeneratorError(
            f"terminal JSON artifact is not an object: {record['path']}"
        )
    return {
        "sha256": record["sha256"],
        "size_bytes": record["size_bytes"],
        "value": value,
    }


def terminal_identity(
    *,
    receipt: Mapping[str, Any],
    admission: GoldbachBuildAdmission,
    child_identities: list[dict[str, Any]],
    artifact_root: Path,
    materialization_manifest_path: Path,
) -> dict[str, Any]:
    """Validate and extract the exact terminal job/source/runtime identity."""

    root = artifact_root.resolve(strict=True)
    if artifact_root.is_symlink() or not root.is_dir():
        raise GoldbachTerminalGeneratorError(
            "terminal artifact root must be a nonsymlink directory"
        )
    job_path = root / "job.json"
    job = validate_job_spec(load_canonical_json(job_path))
    factory = make_factory("measured-finalize-lowered-source-claim", 0)
    expected = registered_invocation_expected(REGISTERED_INVOCATION)
    claim = receipt["claim"]
    if (
        receipt["backend"] != "azure_sevsnp_cpu"
        or any(claim.get(field) != value for field, value in expected.items())
        or claim.get("result") != "true"
        or job["algorithm"]["algorithm_id"] != factory.algorithm_id
        or job["algorithm"]["canonical_definition"] != factory.algorithm_definition
        or job["algorithm"]["definition_sha256"] != expected["algorithm_hash"]
        or job["input_artifact"]["sha256"] != expected["input_hash"]
        or job["parameters"]["canonical_sha256"] != expected["parameters_hash"]
        or job["domain_coverage"]["canonical_sha256"] != expected["domain_hash"]
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal receipt/job is not the exact successful registered invocation"
        )

    records = job["artifact_closure"]["files"]
    if records != sorted(records, key=lambda item: item["path"]):
        raise GoldbachTerminalGeneratorError(
            "terminal artifact closure is not path sorted"
        )
    for record in records:
        _artifact_path(root, record)
    closure_sha256 = wire_sha256(_closure_manifest(records))
    if (
        closure_sha256 != job["artifact_closure"]["manifest_sha256"]
        or claim["artifacts"]["kernel_manifest_hash"] != closure_sha256
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal execution manifest differs from the job/receipt"
        )
    host = _one_role(records, "statement_role", "host_executable")
    source = _one_role(records, "statement_role", "source_tree")
    if (
        claim["artifacts"]["host_executable_hash"] != host["sha256"]
        or claim["artifacts"]["source_tree_hash"] != source["sha256"]
        or claim["artifacts"]["device_cubin_hash"] != NOT_APPLICABLE_DIGEST
        or claim["target_profile_hash"] != job["target_profile"]["sha256"]
        or claim["trust_profile_hash"] != job["trust_profile"]["sha256"]
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal claim artifacts/profiles differ from the exact job"
        )

    admission_record = _one_role(
        records, "role", "reviewed_goldbach_build_admission"
    )
    if (
        admission_record["sha256"] != admission.admission_sha256
        or admission_record["size_bytes"] != admission.admission_size_bytes
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal closure contains another Goldbach build admission"
        )
    runtime_record = _one_role(
        records, "role", "image_runtime_closure_manifest"
    )
    child_commitment_record = _one_role(
        records, "role", "goldbach_child_receipt_identity_commitment"
    )
    terminal_binding_record = _one_role(
        records, "role", "goldbach_terminal_post_child_run_binding"
    )
    source_record = _one_role(
        records, "role", "reviewed_source_closure_manifest"
    )
    producer = _one_role(records, "statement_role", "producer_executable")
    goldbach_executable = _one_role(
        records, "role", "h100_executable_identity_data_not_cpu_executed"
    )
    if goldbach_executable["sha256"] != admission.core["executable"]["sha256"]:
        raise GoldbachTerminalGeneratorError(
            "terminal closure carries another H100 executable identity"
        )

    runtime = _file_value(root, runtime_record)
    child_commitment = _file_value(root, child_commitment_record)
    terminal_binding = _file_value(root, terminal_binding_record)
    source_manifest = _file_value(root, source_record)
    expected_child_commitment = child_identity_commitment(
        child_identities,
        build_admission_sha256=admission.admission_sha256,
        build_identity_sha256=admission.build_identity_sha256,
        h100_executable_sha256=admission.core["executable"]["sha256"],
        h100_runtime_image_closure_sha256=admission.deployment[
            "runtime_image_closure_sha256"
        ],
    )
    if (
        validate_child_identity_commitment(child_commitment["value"])
        != expected_child_commitment
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal closure child commitment differs from all verified "
            "signed child identities"
        )
    runner_record = job["runner_policy"]
    runner_path = _safe_index_path(
        root, runner_record["path"], "terminal runner policy"
    )
    if hash_file_once(runner_path)[0] != runner_record["sha256"]:
        raise GoldbachTerminalGeneratorError(
            "terminal runner policy differs from the job"
        )
    runner_value = load_canonical_json(runner_path)
    required_claims = (
        runner_value.get("required_claims")
        if isinstance(runner_value, dict)
        else None
    )
    if (
        not isinstance(runner_value, dict)
        or runner_value.get("classification") != "production"
        or runner_value.get("production_ready") is not True
        or not isinstance(required_claims, list)
        or any(not isinstance(item, str) for item in required_claims)
        or "immutable_image_and_runtime_closure"
        not in required_claims
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal runner policy does not bind an immutable runtime image"
        )
    runner_policy = {
        "sha256": runner_record["sha256"],
        "size_bytes": runner_path.stat().st_size,
        "value": runner_value,
    }
    expected_terminal_binding = terminal_execution_binding(
        build_admission_sha256=admission.admission_sha256,
        child_identity_commitment_sha256=child_commitment["sha256"],
        h100_executable_sha256=goldbach_executable["sha256"],
        h100_runtime_image_closure_sha256=admission.deployment[
            "runtime_image_closure_sha256"
        ],
        runner_policy_sha256=runner_policy["sha256"],
        runtime_closure_sha256=runtime["sha256"],
        source_manifest_sha256=source_manifest["sha256"],
        target_profile_sha256=claim["target_profile_hash"],
        terminal_host_executable_sha256=host["sha256"],
        terminal_producer_executable_sha256=producer["sha256"],
        trust_profile_sha256=claim["trust_profile_hash"],
    )
    if (
        validate_terminal_execution_binding(terminal_binding["value"])
        != expected_terminal_binding
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal post-child-run binding differs from its exact "
            "children, runtime, admission, executables, policy, or profiles"
        )

    manifest = load_canonical_json(materialization_manifest_path)
    manifest_sha256, _manifest_size = hash_file_once(
        materialization_manifest_path
    )
    job_sha256, job_size = hash_file_once(job_path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind")
        != "sparkinterval.azure.cpu.goldbach10pow27-materialization.v1"
        or manifest.get("registered_invocation") != REGISTERED_INVOCATION
        or manifest.get("semantic_terminal") is not True
        or manifest.get("build_admission_sha256")
        != admission.admission_sha256
        or manifest.get("build_identity_sha256")
        != admission.build_identity_sha256
        or manifest.get("terminal_child_identity_commitment_sha256")
        != child_commitment["sha256"]
        or manifest.get("job_spec", {}).get("sha256") != job_sha256
        or manifest.get("job_spec", {}).get("size_bytes") != job_size
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal materialization manifest differs from the admitted job"
        )
    if producer["sha256"] != runtime["value"].get("ladder_runner", {}).get(
        "sha256"
    ):
        raise GoldbachTerminalGeneratorError(
            "terminal producer executable differs from the runtime closure"
        )
    return {
        "artifact_closure": {
            "closure_kind": job["artifact_closure"]["closure_kind"],
            "files": records,
            "manifest_sha256": closure_sha256,
            "terminal_producer_executable": producer,
        },
        "child_identity_commitment": child_commitment,
        "claim": {
            key: claim[key]
            for key in (
                "algorithm_hash",
                "algorithm_id",
                "artifacts",
                "domain_hash",
                "input_hash",
                "output_hash",
                "parameters_hash",
                "result",
                "target",
                "target_profile_hash",
                "trust",
                "trust_profile_hash",
            )
        },
        "job_spec_sha256": job_sha256,
        "materialization_manifest_sha256": manifest_sha256,
        "receipt_sha256": receipt["receipt_sha256"],
        "runner_policy": runner_policy,
        "runtime_closure": runtime,
        "source_manifest": source_manifest,
        "terminal_execution_binding": terminal_binding,
    }


def build_bundle(
    *,
    receipt: Mapping[str, Any],
    admission: GoldbachBuildAdmission,
    child_identities: list[dict[str, Any]],
    artifact_root: Path,
    materialization_manifest_path: Path,
) -> dict[str, Any]:
    children = sorted(
        child_identities, key=lambda item: (item["phase"], item["shard_index"])
    )
    bundle = {
        "admission": {
            "admission_sha256": admission.admission_sha256,
            "admission_size_bytes": admission.admission_size_bytes,
            "build_identity_sha256": admission.build_identity_sha256,
            "executable_sha256": admission.core["executable"]["sha256"],
            "h100_artifact_closure_manifest_sha256": admission.expected_artifacts[
                "artifact_closure_manifest_sha256"
            ],
            "h100_runtime_image_closure": admission.runtime_image_closure(),
            "h100_runtime_image_closure_sha256": admission.deployment[
                "runtime_image_closure_sha256"
            ],
            "h100_source_tree_sha256": admission.expected_artifacts[
                "source_tree_hash"
            ],
            "source_identity_sha256": admission.core[
                "source_identity_sha256"
            ],
        },
        "children": {
            "count": len(children),
            "identities": children,
            "identities_sha256": hashlib.sha256(
                canonical_json_bytes(children)
            ).hexdigest(),
        },
        "classification": "post-run-candidate",
        "kind": BUNDLE_KIND,
        "registered_invocation": REGISTERED_INVOCATION,
        "schema_version": 1,
        "terminal": terminal_identity(
            receipt=receipt,
            admission=admission,
            child_identities=children,
            artifact_root=artifact_root,
            materialization_manifest_path=materialization_manifest_path,
        ),
    }
    return validate_terminal_identity_bundle(bundle)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--terminal-receipt", type=Path, required=True)
    result.add_argument("--key-manifest", type=Path, required=True)
    result.add_argument("--build-admission", type=Path, required=True)
    result.add_argument("--child-index", type=Path, required=True)
    result.add_argument("--artifact-root", type=Path, required=True)
    result.add_argument("--materialization-manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--lean-candidate", type=Path)
    result.add_argument("--check-lean-source", type=Path)
    result.add_argument("--allow-test-fixture", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--allow-development-key", action="store_true", help=argparse.SUPPRESS)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        admission = load_build_admission(
            args.build_admission,
            allow_test_fixture=args.allow_test_fixture,
        )
        receipt = load_verified_receipt(
            args.terminal_receipt,
            key_manifest=args.key_manifest,
            allow_development_key=args.allow_development_key,
        )
        children = load_child_identities(
            args.child_index,
            key_manifest=args.key_manifest,
            admission=admission,
            allow_development_key=args.allow_development_key,
        )
        bundle = build_bundle(
            receipt=receipt,
            admission=admission,
            child_identities=children,
            artifact_root=args.artifact_root,
            materialization_manifest_path=args.materialization_manifest,
        )
        raw = canonical_json_bytes(bundle)
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            args.output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o400,
        )
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        bundle_sha256 = hashlib.sha256(raw).hexdigest()
        pins = lean_pin_values(bundle, bundle_sha256)
        if args.lean_candidate is not None:
            candidate = render_lean_pin_candidate(pins).encode("utf-8")
            candidate_descriptor = os.open(
                args.lean_candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o400,
            )
            try:
                _write_all(candidate_descriptor, candidate)
                os.fsync(candidate_descriptor)
            finally:
                os.close(candidate_descriptor)
        if args.check_lean_source is not None:
            check_lean_terminal_pins(
                args.check_lean_source.read_text(encoding="utf-8"), pins
            )
        print(
            "post-run candidate generated; production registration remains "
            f"unconfigured (bundle_sha256={bundle_sha256})"
        )
        return 0
    except (
        CampaignIOError,
        GoldbachBuildAdmissionError,
        GoldbachTerminalGeneratorError,
        GoldbachTerminalIdentityError,
        OSError,
        ValueError,
    ) as error:
        print(f"Goldbach terminal registration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
