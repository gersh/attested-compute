# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the second measured CDEM artifact-input CPU stage.

The existing CDEM producer route is left unchanged.  This additive
materializer requires that route to have a verified portfolio receipt and a
matching returned certificate archive.  It recovers the exact retained
artifact authenticated by the producer's signed wire statement and makes
those bytes -- not the historical job descriptor -- the measured input to a
fresh SEV-SNP CPU job.

The resulting operator configuration intentionally has
``registered_invocation = null``.  It can issue an operational receipt for
the terminal run, but it cannot generate a Lean theorem candidate.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_cdem_artifact_terminal_workload_factory import (
    CDEM_ARTIFACT_TERMINAL_FACTORY,
    INPUT_PATH,
    OUTPUT_PATH,
    PRODUCER_BINDING_PATH,
    PRODUCER_CERTIFICATE_PATH,
    PRODUCER_RECEIPT_PATH,
    PRODUCER_VERIFIER_MANIFEST_PATH,
    PRODUCER_VERIFIER_PUBLIC_KEY_PATH,
    REPLAYER_PATH,
    RESULT,
    TERMINAL_PATH,
    TRACE_PATH,
    CdemArtifactTerminalFactory,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    MaterializerError as CommonMaterializerError,
    PROFILE_PATHS,
    _absolute,
    _artifact_record,
    _copy_exact,
    _file_pin,
    _pin,
    _run_build,
    _source_pin,
    _transcript_policy,
    _write_bytes,
    load_site as load_base_site,
    record_hash,
)
from tg_verifier.azure_cpu_workload_factory import (
    CDEM_FACTORY,
    factory_for_portfolio_group,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    hash_file_once,
    load_json,
    read_bytes_once,
)
from tg_verifier.cdem_abel_artifact import (
    CdemAbelArtifactError,
    validate_production_artifact,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (
    REPOSITORY_ROOT / "azure",
    REPOSITORY_ROOT / "attestation",
    REPOSITORY_ROOT / "tools",
):
    if str(directory) not in os.sys.path:
        os.sys.path.insert(0, str(directory))

import cpu_production_orchestrator as cpu_operator  # noqa: E402
from generate_trusted_compute_lean import (  # noqa: E402
    ReceiptError,
    load_key_manifest,
    load_verified_receipt,
    require_production_verifier,
    validate_registered_invocation,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import (  # noqa: E402
    _closure_manifest,
    canonical_sha256,
    load_profile,
    validate_job_spec,
)
import trusted_compute_receipt as receipt_issuer  # noqa: E402
import verify_run_bundle  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.cdem-artifact-terminal-materializer-site.v1"
MANIFEST_KIND = (
    "sparkinterval.azure.cpu.cdem-artifact-terminal-materialization.v1"
)
SITE_FIELDS = {"base_site", "cdem", "kind", "schema_version"}
CDEM_FIELDS = {"challenge_ttl_seconds", "producer_certificate_archive"}
PRODUCER_GROUP_ID = "cdem-table-abel::single-job"
PRODUCER_SHARD_INDEX = 0
PRODUCER_ARTIFACT_PATH = "work/cdem-abel-artifact.bin"
MAXIMUM_CERTIFICATE_FILES = 10_000
MAXIMUM_CERTIFICATE_BYTES = 2 * 1024**3
FIXED_COMPILER_SEARCH_PATH = "/usr/bin:/usr/local/bin"
VERIFIER_KEY_MANIFEST = (
    REPOSITORY_ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
)
VERIFIER_KEY_MANIFEST_RELATIVE = (
    "profiles/verifier_keys/trusted_compute_keys.json"
)


class CdemArtifactTerminalMaterializerError(RuntimeError):
    """The predecessor, source closure, build, or package failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise CdemArtifactTerminalMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise CdemArtifactTerminalMaterializerError(
            f"cannot load canonical CDEM terminal materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "CDEM terminal materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise CdemArtifactTerminalMaterializerError(
            "unsupported CDEM terminal materializer site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise CdemArtifactTerminalMaterializerError(str(error)) from error
    cdem = _exact(site["cdem"], CDEM_FIELDS, "CDEM terminal inputs")
    _pin(
        cdem["producer_certificate_archive"],
        "returned CDEM producer certificate archive",
    )
    ttl = cdem["challenge_ttl_seconds"]
    if (
        isinstance(ttl, bool)
        or not isinstance(ttl, int)
        or not 1 <= ttl <= cpu_operator.MAX_CHALLENGE_TTL_SECONDS
        or ttl
        <= CDEM_ARTIFACT_TERMINAL_FACTORY.timeout_seconds
        + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS
    ):
        raise CdemArtifactTerminalMaterializerError(
            "terminal challenge TTL cannot contain the workload timeout and "
            "evidence-collection margin"
        )
    return {
        "base": base,
        "cdem": cdem,
        "site_pin": _file_pin(path),
    }


def _producer_receipt_path(
    context: azure_portfolio.PortfolioContext,
) -> Path:
    group = azure_portfolio._group(context, PRODUCER_GROUP_ID)
    if factory_for_portfolio_group(group) != CDEM_FACTORY:
        raise CdemArtifactTerminalMaterializerError(
            "producer portfolio group is not the reviewed one-stage CDEM factory"
        )
    state = azure_portfolio.load_state(context)
    paths = azure_portfolio._task_paths(
        context, PRODUCER_GROUP_ID, PRODUCER_SHARD_INDEX
    )
    task_id = paths["task_id"].name
    record = state["records"].get(task_id)
    if record is None:
        raise CdemArtifactTerminalMaterializerError(
            "CDEM producer has no portfolio receipt"
        )
    azure_portfolio._validate_task_record(context, task_id, record)
    if record["stage"] != "verified_receipt_recorded":
        raise CdemArtifactTerminalMaterializerError(
            "CDEM producer receipt is not verified and recorded"
        )
    return paths["receipt"]


def _safe_bundle_path(root: Path, relative: str, what: str) -> Path:
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != relative
    ):
        raise CdemArtifactTerminalMaterializerError(
            f"{what} has an unsafe path"
        )
    root_resolved = root.resolve(strict=True)
    candidate_path = root / candidate
    try:
        if candidate_path.is_symlink():
            raise ValueError("symbolic link")
        resolved = candidate_path.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as error:
        raise CdemArtifactTerminalMaterializerError(
            f"{what} escapes or is absent"
        ) from error
    if resolved.is_symlink() or not resolved.is_file():
        raise CdemArtifactTerminalMaterializerError(
            f"{what} is not a regular file"
        )
    return resolved


def _inspect_producer_certificate(
    archive: Path,
    receipt: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    """Recover the exact artifact committed by the signed producer statement."""

    temporary = Path(tempfile.mkdtemp(prefix=".cdem-producer-certificate-audit-"))
    try:
        extracted = temporary / "certificate"
        extract_archive(
            archive,
            extracted,
            maximum_files=MAXIMUM_CERTIFICATE_FILES,
            maximum_bytes=MAXIMUM_CERTIFICATE_BYTES,
        )
        bundle_root = extracted / "bundle-root"
        bundle_path = bundle_root / "run-bundle.json"
        bundle = load_json(bundle_path, require_canonical=True)
        checked = verify_run_bundle.verify_bundle(
            bundle,
            artifact_root=bundle_root,
        )
        wire_statement = receipt["bindings"]["wire_statement_sha256"]
        signed_bundle = receipt["bindings"]["run_bundle_sha256"]
        if (
            checked.get("accepted") is not True
            or checked.get("artifacts_verified") is not True
            or checked.get("statement_sha256") != wire_statement
            or bundle.get("statement_sha256") != wire_statement
            or checked.get("bundle_sha256") != signed_bundle
            or bundle.get("bundle_sha256") != signed_bundle
        ):
            raise CdemArtifactTerminalMaterializerError(
                "producer certificate does not match the signed run bundle and "
                "wire statement"
            )
        reconstructed_claim = receipt_issuer.claim_from_bundle(
            bundle, bundle_root, cpu_operator.BACKEND
        )
        if reconstructed_claim != receipt["claim"]:
            raise CdemArtifactTerminalMaterializerError(
                "producer certificate claim differs from the signed receipt"
            )
        statement = bundle["statement"]
        environment = statement["execution_environment"]["value"]
        if not isinstance(environment, dict):
            raise CdemArtifactTerminalMaterializerError(
                "producer statement execution environment is malformed"
            )
        retained = environment.get("retained_artifacts")
        if (
            not isinstance(retained, list)
            or len(retained) != 1
            or not isinstance(retained[0], dict)
            or set(retained[0]) != {"path", "sha256"}
            or retained[0]["path"] != PRODUCER_ARTIFACT_PATH
            or not isinstance(retained[0]["sha256"], str)
            or len(retained[0]["sha256"]) != 64
        ):
            raise CdemArtifactTerminalMaterializerError(
                "producer statement does not bind exactly one canonical CDEM artifact"
            )
        artifact_path = _safe_bundle_path(
            bundle_root, retained[0]["path"], "retained CDEM artifact"
        )
        artifact_raw = read_bytes_once(artifact_path, limit=262_144)
        artifact_sha256 = hashlib.sha256(artifact_raw).hexdigest()
        if artifact_sha256 != retained[0]["sha256"]:
            raise CdemArtifactTerminalMaterializerError(
                "retained CDEM artifact differs from the signed statement digest"
            )
        try:
            certificate = validate_production_artifact(artifact_raw)
        except CdemAbelArtifactError as error:
            raise CdemArtifactTerminalMaterializerError(
                f"retained CDEM artifact is not the production frame: {error}"
            ) from error
        return artifact_raw, {
            "artifact_sha256": artifact_sha256,
            "artifact_size_bytes": len(artifact_raw),
            "certificate_archive": _file_pin(archive),
            "chunk_count": len(certificate.chunks),
            "producer_algorithm_hash": receipt["claim"]["algorithm_hash"],
            "producer_algorithm_id": receipt["claim"]["algorithm_id"],
            "producer_input_hash": receipt["claim"]["input_hash"],
            "producer_nonce": receipt["claim"]["nonce"],
            "producer_receipt_sha256": receipt["receipt_sha256"],
            "producer_run_bundle_sha256": signed_bundle,
            "producer_wire_statement_sha256": wire_statement,
            "retained_artifact_path": retained[0]["path"],
        }
    except (
        ArchiveError,
        CampaignIOError,
        OSError,
        ReceiptError,
        ValueError,
        verify_run_bundle.VerificationError,
    ) as error:
        if isinstance(error, CdemArtifactTerminalMaterializerError):
            raise
        raise CdemArtifactTerminalMaterializerError(
            f"cannot audit CDEM producer certificate: {error}"
        ) from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _producer_dependency(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], Path, Path, Path, Path]:
    receipt_path = _producer_receipt_path(context)
    _archive_pin, archive = _pin(
        site["cdem"]["producer_certificate_archive"],
        "returned CDEM producer certificate archive",
    )
    try:
        _manifest_row, manifest_path = _source_pin(
            context, VERIFIER_KEY_MANIFEST_RELATIVE
        )
        if manifest_path != VERIFIER_KEY_MANIFEST.resolve(strict=True):
            raise ReceiptError(
                "source-pinned verifier manifest resolved unexpectedly"
            )
        receipt = load_verified_receipt(
            receipt_path,
            key_manifest=manifest_path,
            allow_development_key=False,
        )
        require_production_verifier(receipt, manifest_path)
        validate_registered_invocation(
            receipt, CDEM_FACTORY.registered_invocation
        )
        manifest = load_key_manifest(manifest_path)
        verifier_key_id = receipt["verifier"]["key_id"]
        public_relative = (
            Path("profiles/verifier_keys")
            / manifest[verifier_key_id]["public_key_path"]
        ).as_posix()
        _public_row, public_key_path = _source_pin(context, public_relative)
    except (CommonMaterializerError, KeyError, ReceiptError) as error:
        raise CdemArtifactTerminalMaterializerError(
            f"CDEM producer receipt failed source-pinned verification: {error}"
        ) from error
    artifact_raw, binding = _inspect_producer_certificate(archive, receipt)
    binding.update(
        {
            "kind": "sparkinterval.azure.cdem-producer-terminal-handoff.v1",
            "producer_group_id": PRODUCER_GROUP_ID,
            "producer_receipt_file": _file_pin(receipt_path),
            "producer_shard_index": PRODUCER_SHARD_INDEX,
            "producer_verifier_key_id": verifier_key_id,
            "producer_verifier_key_manifest_sha256": record_hash(
                manifest_path
            ),
            "producer_verifier_public_key_sha256": record_hash(
                public_key_path
            ),
            "schema_version": 1,
        }
    )
    return (
        artifact_raw,
        binding,
        archive,
        receipt_path,
        manifest_path,
        public_key_path,
    )


def plan_materialization(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    (
        artifact_raw,
        binding,
        _archive,
        receipt_path,
        _manifest,
        _public_key,
    ) = _producer_dependency(context, site)
    source_rows = [
        _source_pin(context, relative)[0]
        for relative in CDEM_ARTIFACT_TERMINAL_FACTORY.source_paths
    ]
    for relative in PROFILE_PATHS.values():
        _source_pin(context, relative)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise CdemArtifactTerminalMaterializerError(
            "materializer output_root must stay outside the repository"
        )
    compiler_name = shutil.which("g++", path=FIXED_COMPILER_SEARCH_PATH)
    compiler = Path(compiler_name).resolve(strict=True) if compiler_name else None
    supported = (
        platform.machine() == "x86_64"
        and compiler is not None
        and compiler.is_file()
        and os.access(compiler, os.X_OK)
    )
    return {
        "accepted": False,
        "artifact_input": {
            "sha256": hashlib.sha256(artifact_raw).hexdigest(),
            "size_bytes": len(artifact_raw),
        },
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge_mode": "operator_generated_fresh_v1",
        "challenge_ttl_seconds": site["cdem"]["challenge_ttl_seconds"],
        "classification": (
            "reviewed_cdem_two_stage_terminal_materialization_plan_"
            "not_execution_evidence"
        ),
        "compiler_path_if_supported": str(compiler) if compiler else None,
        "factory_id": CDEM_ARTIFACT_TERMINAL_FACTORY.factory_id,
        "lean_theorem_produced": False,
        "output_root": str(output_root),
        "producer_dependency": binding,
        "producer_receipt": _file_pin(receipt_path),
        "registered_invocation": None,
        "source_closure": source_rows,
    }


def _require_x86_64_static_elf(path: Path) -> None:
    from measured_runner import _elf_has_interp

    raw = read_bytes_once(path, limit=2**31)
    if (
        len(raw) < 20
        or raw[:4] != b"\x7fELF"
        or raw[4] != 2
        or raw[5] != 1
        or int.from_bytes(raw[18:20], "little") != 62
        or _elf_has_interp(path)
    ):
        raise CdemArtifactTerminalMaterializerError(
            "CDEM artifact terminal closure is not static x86_64 ELF"
        )


def _build_static_closure(
    context: azure_portfolio.PortfolioContext,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise CdemArtifactTerminalMaterializerError(
            "production terminal package must be built on x86_64"
        )
    compiler_name = shutil.which("g++", path=FIXED_COMPILER_SEARCH_PATH)
    if compiler_name is None:
        raise CdemArtifactTerminalMaterializerError(
            "closed terminal factory requires g++ in the fixed search path"
        )
    compiler = Path(compiler_name).resolve(strict=True)
    compiler_pin = _file_pin(compiler)
    version = subprocess.run(
        [str(compiler), "--version"],
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if version.returncode != 0 or version.stderr or not version.stdout.splitlines():
        raise CdemArtifactTerminalMaterializerError(
            "closed compiler identity could not be captured"
        )
    copied: dict[str, Path] = {}
    for relative in CDEM_ARTIFACT_TERMINAL_FACTORY.source_paths:
        _row, source = _source_pin(context, relative)
        destination = artifact_root / "source" / relative
        _copy_exact(source, destination)
        copied[relative] = destination
    include = artifact_root / "source/gpu/include"
    terminal = artifact_root / TERMINAL_PATH
    replayer = artifact_root / REPLAYER_PATH
    terminal.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    common = [
        str(compiler),
        "-O3",
        "-std=c++20",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
    ]
    build_steps = [
        _run_build(
            common
            + [
                str(copied["reference/tg_cdem_abel_chunk_replay.cpp"]),
                "-o",
                str(replayer),
            ],
            cwd=artifact_root,
        ),
        _run_build(
            common
            + [
                "-pthread",
                "-I",
                str(include),
                str(copied["reference/tg_cdem_abel_artifact_terminal.cpp"]),
                "-o",
                str(terminal),
            ],
            cwd=artifact_root,
        ),
    ]
    for output in (terminal, replayer):
        output.chmod(0o500)
        _require_x86_64_static_elf(output)
    records = [
        _artifact_record(
            terminal,
            artifact_root,
            role="closed_cdem_artifact_terminal_and_trace_verifier",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            replayer,
            artifact_root,
            role="cdem_independent_chunk_replayer",
            statement_role="checker_executable",
            executable=True,
        ),
    ]
    source_rows = []
    for relative, copied_path in sorted(copied.items()):
        pin = _file_pin(copied_path)
        source_rows.append(
            {
                "path": relative,
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
        )
    source_manifest = {
        "files": source_rows,
        "kind": "sparkinterval.source-reviewed-closure.v1",
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(
        source_manifest_path, cpu_operator.canonical_json_bytes(source_manifest)
    )
    records.append(
        _artifact_record(
            source_manifest_path,
            artifact_root,
            role="reviewed_source_closure_manifest",
            statement_role="source_tree",
            executable=False,
        )
    )
    for relative, copied_path in sorted(copied.items()):
        records.append(
            _artifact_record(
                copied_path,
                artifact_root,
                role="reviewed_source",
                statement_role=None,
                executable=False,
            )
        )
    records.sort(key=lambda row: row["path"])
    return records, build_steps, {
        **compiler_pin,
        "version_line": version.stdout.splitlines()[0],
    }


def _profile_and_policy_records(
    context: azure_portfolio.PortfolioContext,
    artifact_root: Path,
    site: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for kind, relative in PROFILE_PATHS.items():
        _row, source = _source_pin(context, relative)
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        value = load_profile(destination, kind)
        profiles[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": value["profile_id"],
            "sha256": canonical_sha256(value),
        }
    runner_pin, runner_source = _pin(
        site["base"]["policies"]["runner"], "runner policy", policy=True
    )
    runner_path = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_path)
    return profiles, {
        "path": runner_path.relative_to(artifact_root).as_posix(),
        "policy_id": runner_pin["policy_id"],
        "sha256": runner_pin["sha256"],
    }


def _install_dependency(
    artifact_root: Path,
    *,
    artifact_raw: bytes,
    binding: Mapping[str, Any],
    certificate_archive: Path,
    receipt_path: Path,
    verifier_manifest_path: Path,
    verifier_public_key_path: Path,
    records: list[dict[str, Any]],
) -> Path:
    input_path = artifact_root / INPUT_PATH
    _write_bytes(input_path, artifact_raw)
    certificate_target = artifact_root / PRODUCER_CERTIFICATE_PATH
    receipt_target = artifact_root / PRODUCER_RECEIPT_PATH
    binding_target = artifact_root / PRODUCER_BINDING_PATH
    verifier_manifest_target = artifact_root / PRODUCER_VERIFIER_MANIFEST_PATH
    verifier_public_key_target = (
        artifact_root / PRODUCER_VERIFIER_PUBLIC_KEY_PATH
    )
    _copy_exact(certificate_archive, certificate_target)
    _copy_exact(receipt_path, receipt_target)
    _copy_exact(verifier_manifest_path, verifier_manifest_target)
    _copy_exact(verifier_public_key_path, verifier_public_key_target)
    _write_bytes(binding_target, cpu_operator.canonical_json_bytes(binding))
    for path, role in (
        (
            certificate_target,
            "authenticated_cdem_producer_certificate_archive",
        ),
        (receipt_target, "production_cdem_producer_trusted_compute_receipt"),
        (
            verifier_manifest_target,
            "source_pinned_cdem_producer_verifier_key_manifest",
        ),
        (
            verifier_public_key_target,
            "source_pinned_cdem_producer_verifier_public_key",
        ),
        (binding_target, "cdem_producer_terminal_handoff_binding"),
    ):
        records.append(
            _artifact_record(
                path,
                artifact_root,
                role=role,
                statement_role=None,
                executable=False,
            )
        )
    return input_path


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: CdemArtifactTerminalFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    input_path: Path,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    replayer_sha256 = record_hash(artifact_root / REPLAYER_PATH)
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    input_pin = _file_pin(input_path)
    records.sort(key=lambda row: row["path"])
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": algorithm_hash,
        },
        "artifact_closure": {
            "closure_kind": "static_elf_source_reviewed_v1",
            "files": records,
            "manifest_sha256": canonical_sha256(_closure_manifest(records)),
        },
        "backend": cpu_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv(replayer_sha256)),
            "cwd": ".",
            "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "timeout_seconds": factory.timeout_seconds,
        },
        "domain_coverage": {
            "canonical_sha256": canonical_sha256(factory.domain),
            "value": factory.domain,
        },
        "gpu_pre_run_gate": None,
        "input_artifact": {
            "path": input_path.relative_to(artifact_root).as_posix(),
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": input_pin["sha256"],
            "size_bytes": input_pin["size_bytes"],
        },
        "job_id": "tg-cdem-table-abel-artifact-terminal-cpu-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": OUTPUT_PATH,
        },
        "parameters": {
            "canonical_sha256": canonical_sha256(factory.parameters),
            "value": factory.parameters,
        },
        "runner_policy": runner_policy,
        "schema_version": 1,
        "target_profile": profiles["target"],
        "tpm_policy": {
            "ak_handle": "0x81000003",
            "bank": "sha256",
            "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": profiles["trust"],
        "work_trace_contract": {
            "expected_iterations": factory.trace_iterations,
            "format": "challenge_sha256_chain_json_v1",
            "path": TRACE_PATH,
            "required": True,
            "trace_algorithm_definition": factory.trace_definition,
            "trace_algorithm_sha256": hashlib.sha256(
                factory.trace_definition.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(
                factory.trace_verifier_argv(replayer_sha256)
            ),
        },
    }
    validate_job_spec(job)
    return job


def _operator_config(
    *,
    site: Mapping[str, Any],
    artifact_root: Path,
    package: Path,
    transcript_policy_path: Path,
) -> dict[str, Any]:
    output_root = artifact_root.parent
    review = output_root / "review"
    handoffs = output_root / "handoffs"
    guest = _absolute(site["base"]["worker"]["guest_root"], "guest root", exists=False)
    runner_path = artifact_root / "profiles/runner-policy.json"
    job_path = artifact_root / "job.json"
    transcript_pin = {
        **_file_pin(transcript_policy_path),
        "classification": "production",
        "policy_id": site["base"]["policies"]["transcript_policy_id"],
    }
    return {
        "azure": site["base"]["azure"],
        "campaign_id": CDEM_ARTIFACT_TERMINAL_FACTORY.campaign_id,
        "challenge": {
            "mode": "operator_generated_fresh_v1",
            "pin": None,
            "shard_index": 0,
        },
        "challenge_ttl_seconds": site["cdem"]["challenge_ttl_seconds"],
        "handoffs": {
            "returned_certificate_archive": str(
                handoffs / "returned-certificate.tar"
            ),
            "returned_worker_completion": str(
                handoffs / "returned-completion.json"
            ),
            "worker_stage_manifest": str(handoffs / "worker-stage.json"),
        },
        "kind": cpu_operator.CONFIG_KIND,
        "lean_review": {
            "namespace": site["base"]["lean_namespace"],
            "registered_invocation": None,
        },
        "managed_hsm": site["base"]["managed_hsm"],
        "outputs": {
            "appraisal_report": str(review / "reports/appraisal.json"),
            "challenge_dir": str(review / "challenge"),
            "deployment_record": str(review / "deployment.json"),
            "extracted_certificate_package": str(review / "returned-package"),
            "lean_candidate": str(review / "candidates/Certificate.lean"),
            "receipt": str(review / "receipt.json"),
            "registry_candidate": str(
                review / "candidates/TrustedComputeRegistry.lean"
            ),
            "replay_db": str(review / "replay/trusted-compute.sqlite3"),
            "review_root": str(review),
            "state": str(review / "operator-state.json"),
            "transcript_report": str(review / "reports/transcript.json"),
        },
        "policies": {
            "composite_appraisal": site["base"]["policies"][
                "composite_appraisal"
            ],
            "evidence_verifier": site["base"]["policies"]["evidence_verifier"],
            "runner": {
                **_file_pin(runner_path),
                "classification": "production",
                "policy_id": site["base"]["policies"]["runner"]["policy_id"],
            },
            "transcript_appraisal": transcript_pin,
        },
        "schema_version": 1,
        "worker": {
            "artifact_root": str(guest / "artifact-root"),
            "certificate_archive": str(guest / "return/certificate.tar"),
            "certificate_package": str(guest / "certificate-package"),
            "challenge": str(guest / "input/challenge.json"),
            "completion_manifest": str(guest / "return/completion.json"),
            "job_spec": str(guest / "artifact-root/job.json"),
            "maa_attestation_url": site["base"]["worker"][
                "maa_attestation_url"
            ],
            "run_package": str(guest / "measured-run"),
            "stage_manifest": str(guest / "input/worker-stage.json"),
            "transcript_appraisal_policy": str(
                guest / "input/transcript-appraisal-production.json"
            ),
            "workload_package": str(guest / "input/workload.tar"),
        },
        "workload": {
            "artifact_root": str(artifact_root),
            "job_spec": _file_pin(job_path),
            "package": _file_pin(package),
        },
    }


def materialize(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(context, site)
    if not plan["build_host_supported"]:
        raise CdemArtifactTerminalMaterializerError(
            "this host cannot build the x86_64 static terminal closure"
        )
    (
        artifact_raw,
        binding,
        certificate_archive,
        receipt_path,
        verifier_manifest_path,
        verifier_public_key_path,
    ) = _producer_dependency(context, site)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.cdem-terminal-materializing-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, compiler = _build_static_closure(
            context, artifact_root
        )
        input_path = _install_dependency(
            artifact_root,
            artifact_raw=artifact_raw,
            binding=binding,
            certificate_archive=certificate_archive,
            receipt_path=receipt_path,
            verifier_manifest_path=verifier_manifest_path,
            verifier_public_key_path=verifier_public_key_path,
            records=records,
        )
        job = _job(
            context,
            CDEM_ARTIFACT_TERMINAL_FACTORY,
            artifact_root,
            records,
            input_path,
            site,
        )
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        transcript_policy = _transcript_policy(
            site["base"], record_hash(job_path), job
        )
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise CdemArtifactTerminalMaterializerError(
                "materializer output_root appeared during build"
            )
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site=site,
            artifact_root=artifact_root,
            package=package,
            transcript_policy_path=transcript_path,
        )
        config_path = output_root / "cpu-campaign.json"
        _write_bytes(config_path, cpu_operator.canonical_json_bytes(config))
        _validated, config_hash = cpu_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "artifact_input": _file_pin(artifact_root / INPUT_PATH),
            "build_steps": build_steps,
            "challenge_mode": "operator_generated_fresh_v1",
            "classification": (
                "source_reviewed_cdem_two_stage_terminal_operator_validated_"
                "materialization_not_execution_evidence"
            ),
            "compiler": compiler,
            "cpu_operator_config": {
                **_file_pin(config_path),
                "sha256": config_hash,
            },
            "execution_completed": False,
            "factory_id": CDEM_ARTIFACT_TERMINAL_FACTORY.factory_id,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "producer_dependency": binding,
            "registered_invocation": None,
            "schema_version": SCHEMA_VERSION,
            "terminal_receipt_produced": False,
            "transcript_policy": _file_pin(transcript_path),
        }
        manifest_path = output_root / "materialization-manifest.json"
        _write_bytes(manifest_path, cpu_operator.canonical_json_bytes(manifest))
        complete = True
        return {
            **manifest,
            "cpu_operator_config": {
                **manifest["cpu_operator_config"],
                "path": str(config_path),
            },
            "job_spec": {**manifest["job_spec"], "path": str(job_path)},
            "manifest": str(manifest_path),
            "package": {**manifest["package"], "path": str(package)},
        }
    except (
        ArchiveError,
        CampaignIOError,
        CommonMaterializerError,
        OSError,
        ValueError,
    ) as error:
        if isinstance(error, CdemArtifactTerminalMaterializerError):
            raise
        raise CdemArtifactTerminalMaterializerError(
            f"CDEM terminal materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "CDEM_FIELDS",
    "CdemArtifactTerminalMaterializerError",
    "MANIFEST_KIND",
    "PRODUCER_ARTIFACT_PATH",
    "PRODUCER_GROUP_ID",
    "SCHEMA_VERSION",
    "SITE_FIELDS",
    "SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
