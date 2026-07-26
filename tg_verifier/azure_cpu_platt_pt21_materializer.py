# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the exact five-stage PT21 CPU/FLINT Azure route.

This is a packaging/control-plane boundary, never execution evidence.  Every
predecessor archive is found by a formulaic path, checked against the result
inside its verified production receipt, structurally replayed, and copied
into a fresh immutable handoff.  The terminal handoff contains one
authenticated prefix state and exactly 1,236,316 canonical shard receipts.

The route deliberately uses a reusable, hash-pinned runtime closure.  It is
source-complete but economically unscaled; the independent portfolio sizing
gate remains false.  The incomplete optimized H100 contract is rejected.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_platt_pt21_workload_factory import (
    CAMPAIGN_ID,
    CONTRACT_FILE_SHA256,
    PHASE_COUNTS,
    REFERENCE_CONTRACT_ID,
    REGISTERED_INVOCATION,
    SHARD_COUNT,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    PT21CPUWorkloadFactory,
    PT21WorkloadFactoryError,
    execution_contract,
    expected_registered_hashes,
    factory_for_portfolio_group,
    production_capability_complete,
)
from tg_verifier.azure_cpu_platt_head_materializer import (
    PlattHeadMaterializerError,
    _flint_identity,
    _profile_and_policy_records,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    MaterializerError as CommonMaterializerError,
    PROFILE_PATHS,
    _absolute,
    _artifact_record,
    _copy_exact,
    _file_pin,
    _load_handoff,
    _operator_config,
    _pin,
    _require_x86_64_static_elf,
    _source_pin,
    _transcript_policy,
    _write_bytes,
    load_site as load_base_site,
    record_hash,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
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
    load_verified_receipt,
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402
from tg_platt_pt21_azure_measured_workload import (  # noqa: E402
    EXPORT_KIND,
    EXPORT_TREE_DOMAIN,
    HANDOFF_KIND,
    HANDOFF_TREE_DOMAIN,
    OPERATIONAL_RESULT_KIND,
    PT21MeasuredWorkloadError,
    verify_retained_export_archive,
)


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.platt-pt21-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.platt-pt21-materialization.v1"
RUNTIME_KIND = "sparkinterval.azure.cpu.platt-pt21-runtime-closure.v1"
SITE_FIELDS = {"base_site", "kind", "pt21", "schema_version"}
PT21_FIELDS = {
    "execution_contract_id",
    "flint_source_root",
    "retained_export_root",
    "runtime",
}
RUNTIME_FIELDS = {"manifest", "python", "runner"}
RUNTIME_MANIFEST_FIELDS = {
    "architecture",
    "build",
    "capability",
    "execution_contract_id",
    "execution_contract_sha256",
    "flint",
    "kind",
    "python",
    "runner",
    "schema_version",
}
RUNTIME_FILE_FIELDS = {"sha256", "size_bytes"}
RUNTIME_CAPABILITY_FIELDS = {
    "finalizer_complete",
    "full_source_geometry_complete",
    "retained_export_replay_complete",
    "worker_complete",
}
RUNTIME_BUILD_FIELDS = {
    "build_recipe_sha256",
    "classification",
    "compiler_id",
    "runner_source_sha256",
    "supervisor_source_sha256",
}
RUNTIME_FLINT_FIELDS = {
    "commit",
    "tracked_tree_sha256",
    "version",
}
OPERATIONAL_RESULT_FIELDS = {
    "execution_contract_sha256",
    "kind",
    "phase_id",
    "retained_export_sha256",
    "retained_export_size_bytes",
    "retained_tree_sha256",
    "schema_version",
    "shard_index",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
FIXED_TOOL_PATH = "/usr/bin:/bin"
FINAL_RECEIPT_TREE_DOMAIN = (
    b"sparkinterval/platt-pt21-final-shard-receipt-tree/v1\0"
)


class PT21MaterializerError(RuntimeError):
    """A runtime, handoff, receipt, export, or package failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise PT21MaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PT21MaterializerError(f"{what} is not lowercase SHA-256")
    return value


def _integer(
    value: Any, what: str, *, minimum: int, maximum: int = 2**63 - 1
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise PT21MaterializerError(
            f"{what} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise PT21MaterializerError(f"{what} must be a non-symlink directory")
    return path


def _runtime_file(value: Any, what: str) -> tuple[dict[str, Any], Path]:
    pin, path = _pin(value, what)
    if not os.access(path, os.X_OK):
        raise PT21MaterializerError(f"{what} is not executable")
    return pin, path


def _runtime_identity(
    runtime: Mapping[str, Any],
    *,
    context: azure_portfolio.PortfolioContext | None,
    flint_source_root: Path,
) -> dict[str, Any]:
    fields = _exact(runtime, RUNTIME_FIELDS, "PT21 runtime")
    manifest_pin, manifest_path = _pin(
        fields["manifest"], "PT21 runtime manifest"
    )
    python_pin, python_path = _runtime_file(
        fields["python"], "PT21 runtime Python"
    )
    runner_pin, runner_path = _runtime_file(
        fields["runner"], "PT21 runtime runner"
    )
    try:
        value = load_json(manifest_path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PT21MaterializerError(
            f"cannot load canonical PT21 runtime manifest: {error}"
        ) from error
    manifest = _exact(
        value, RUNTIME_MANIFEST_FIELDS, "PT21 runtime manifest"
    )
    build = _exact(manifest["build"], RUNTIME_BUILD_FIELDS, "runtime build")
    capability = _exact(
        manifest["capability"],
        RUNTIME_CAPABILITY_FIELDS,
        "runtime capability",
    )
    flint = _exact(manifest["flint"], RUNTIME_FLINT_FIELDS, "runtime FLINT")
    manifest_python = _exact(
        manifest["python"], RUNTIME_FILE_FIELDS, "runtime manifest Python"
    )
    manifest_runner = _exact(
        manifest["runner"], RUNTIME_FILE_FIELDS, "runtime manifest runner"
    )
    contract = execution_contract(REFERENCE_CONTRACT_ID)
    if (
        manifest["kind"] != RUNTIME_KIND
        or manifest["schema_version"] != 1
        or manifest["architecture"] != "x86_64"
        or manifest["execution_contract_id"] != REFERENCE_CONTRACT_ID
        or manifest["execution_contract_sha256"] != CONTRACT_FILE_SHA256
        or manifest_python
        != {
            "sha256": python_pin["sha256"],
            "size_bytes": python_pin["size_bytes"],
        }
        or manifest_runner
        != {
            "sha256": runner_pin["sha256"],
            "size_bytes": runner_pin["size_bytes"],
        }
        or any(capability[field] is not True for field in capability)
        or not production_capability_complete(contract)
        or contract["capability"]["under_one_week_and_10000_usd"] is not False
        or flint
        != {
            "commit": "8d5454b96761fafe4d5a9da76a369a602f500f49",
            "tracked_tree_sha256": (
                "06b194b828a12c6b6c34d5c1653cadd7d9f3f3356d8f3257a293f9ccf1beade1"
            ),
            "version": "3.6.0",
        }
        or build["classification"]
        != "operator-reviewed-reproducible-build-record-not-formal-compiler-proof"
        or not isinstance(build["compiler_id"], str)
        or not build["compiler_id"]
    ):
        raise PT21MaterializerError(
            "PT21 runtime does not satisfy the complete reference contract"
        )
    for field in (
        "build_recipe_sha256",
        "runner_source_sha256",
        "supervisor_source_sha256",
    ):
        _sha256(build[field], f"runtime build {field}")
    if context is not None:
        runner_source, _ = _source_pin(
            context, "reference/tg_platt_zeta_shard.cpp"
        )
        supervisor_source, _ = _source_pin(
            context, "tg_verifier/platt_zeta_campaign.py"
        )
        if (
            build["runner_source_sha256"] != runner_source["sha256"]
            or build["supervisor_source_sha256"]
            != supervisor_source["sha256"]
        ):
            raise PT21MaterializerError(
                "PT21 runtime build record is not bound to this repository closure"
            )
    try:
        _require_x86_64_static_elf(runner_path)
    except CommonMaterializerError as error:
        raise PT21MaterializerError(str(error)) from error
    if _flint_identity(flint_source_root)["tree_sha256"] != flint[
        "tracked_tree_sha256"
    ]:
        raise PT21MaterializerError(
            "PT21 runtime FLINT tree differs from the supplied reviewed source"
        )
    return {
        "manifest": manifest,
        "manifest_pin": manifest_pin,
        "manifest_path": manifest_path,
        "python_path": python_path,
        "python_pin": python_pin,
        "runner_path": runner_path,
        "runner_pin": runner_pin,
    }


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PT21MaterializerError(
            f"cannot load canonical PT21 materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "PT21 materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise PT21MaterializerError(
            "unsupported PT21 materializer site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise PT21MaterializerError(str(error)) from error
    inputs = _exact(site["pt21"], PT21_FIELDS, "PT21 inputs")
    if inputs["execution_contract_id"] != REFERENCE_CONTRACT_ID:
        contract_id = inputs["execution_contract_id"]
        try:
            contract = execution_contract(contract_id)
        except PT21WorkloadFactoryError as error:
            raise PT21MaterializerError(str(error)) from error
        if not production_capability_complete(contract):
            raise PT21MaterializerError(
                f"PT21 execution contract {contract_id} has an incomplete "
                "production worker/finalizer capability"
            )
        raise PT21MaterializerError(
            "this CPU materializer accepts only the reviewed reference contract"
        )
    retained = _directory(
        inputs["retained_export_root"], "PT21 retained export root"
    )
    flint = _directory(inputs["flint_source_root"], "FLINT source root")
    runtime = _runtime_identity(
        inputs["runtime"], context=None, flint_source_root=flint
    )
    return {
        "base": base,
        "pt21": inputs,
        "retained_export_root": retained,
        "runtime": runtime,
        "site_pin": _file_pin(path),
    }


class _MerkleAccumulator:
    """Streaming duplicate-odd SHA-256 Merkle accumulator."""

    def __init__(self) -> None:
        self._frontier: list[bytes | None] = []
        self.count = 0

    @staticmethod
    def _parent(left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(b"\x01" + left + right).digest()

    def add(self, digest: str) -> None:
        node = hashlib.sha256(b"\x00" + bytes.fromhex(_sha256(digest, "Merkle leaf"))).digest()
        level = 0
        self.count += 1
        while True:
            if level == len(self._frontier):
                self._frontier.append(node)
                return
            left = self._frontier[level]
            if left is None:
                self._frontier[level] = node
                return
            self._frontier[level] = None
            node = self._parent(left, node)
            level += 1

    def root(self) -> str:
        if self.count == 0:
            raise PT21MaterializerError("cannot finalize an empty Merkle tree")
        accumulated: bytes | None = None
        accumulated_level = 0
        for level, peak in enumerate(self._frontier):
            if peak is None:
                continue
            if accumulated is None:
                accumulated = peak
                accumulated_level = level
                continue
            while accumulated_level < level:
                accumulated = self._parent(accumulated, accumulated)
                accumulated_level += 1
            accumulated = self._parent(peak, accumulated)
            accumulated_level = level + 1
        assert accumulated is not None
        return accumulated.hex()


def _retained_export_path(root: Path, phase: str, shard_index: int) -> Path:
    path = root / phase / f"{shard_index:07d}.tar"
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise PT21MaterializerError(
            "formulaic PT21 retained export path escapes or is absent"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise PT21MaterializerError(
            f"PT21 retained export is not a regular file: {phase}/{shard_index}"
        )
    return path


def _operational_result(
    receipt: Mapping[str, Any],
    *,
    phase: str,
    shard_index: int,
) -> dict[str, Any]:
    claim = receipt["claim"]
    result = claim["result"]
    if (
        not isinstance(result, str)
        or hashlib.sha256(result.encode("utf-8")).hexdigest()
        != claim["output_hash"]
    ):
        raise PT21MaterializerError(
            "PT21 predecessor result/output hash is inconsistent"
        )
    try:
        value = json.loads(result)
        canonical = canonical_json_bytes(value).decode("utf-8").rstrip("\n")
    except (
        CampaignIOError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise PT21MaterializerError(
            "PT21 predecessor result is not canonical JSON"
        ) from error
    if (
        not isinstance(value, dict)
        or set(value) != OPERATIONAL_RESULT_FIELDS
        or canonical != result
        or value["kind"] != OPERATIONAL_RESULT_KIND
        or value["schema_version"] != 1
        or value["execution_contract_sha256"] != CONTRACT_FILE_SHA256
        or value["phase_id"] != phase
        or value["shard_index"] != shard_index
    ):
        raise PT21MaterializerError(
            "PT21 predecessor operational result differs"
        )
    _sha256(value["retained_export_sha256"], "retained export digest")
    _sha256(value["retained_tree_sha256"], "retained export tree")
    _integer(
        value["retained_export_size_bytes"],
        "retained export size",
        minimum=1,
    )
    return value


def _verified_predecessor(
    context: azure_portfolio.PortfolioContext,
    state: Mapping[str, Any],
    *,
    group_id: str,
    phase: str,
    shard_index: int,
    retained_root: Path,
) -> dict[str, Any]:
    group = azure_portfolio._group(context, group_id)
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None or factory.terminal:
        raise PT21MaterializerError(
            "PT21 predecessor is not a reviewed operational factory"
        )
    paths = azure_portfolio._task_paths(context, group_id, shard_index)
    task_id = paths["task_id"].name
    record = state["records"].get(task_id)
    if record is None:
        raise PT21MaterializerError(
            f"PT21 predecessor has no portfolio receipt: {task_id}"
        )
    azure_portfolio._validate_task_record(context, task_id, record)
    if record["stage"] != "verified_receipt_recorded":
        raise PT21MaterializerError(
            f"PT21 predecessor receipt is incomplete: {task_id}"
        )
    try:
        receipt = load_verified_receipt(
            paths["receipt"], key_manifest=context.verifier_key_manifest
        )
    except Exception as error:
        raise PT21MaterializerError(
            f"PT21 predecessor receipt failed verification: {error}"
        ) from error
    claim = receipt["claim"]
    if (
        receipt["backend"] != cpu_operator.BACKEND
        or claim["algorithm_id"] != factory.algorithm_id
        or claim["algorithm_hash"]
        != hashlib.sha256(
            factory.algorithm_definition.encode("utf-8")
        ).hexdigest()
        or claim["input_hash"]
        != hashlib.sha256(factory.input_bytes).hexdigest()
        or claim["parameters_hash"] != canonical_sha256(factory.parameters)
        or claim["domain_hash"] != canonical_sha256(factory.domain)
    ):
        raise PT21MaterializerError(
            "PT21 predecessor receipt is not the reviewed phase job"
        )
    result = _operational_result(
        receipt, phase=phase, shard_index=shard_index
    )
    export = _retained_export_path(retained_root, phase, shard_index)
    if hash_file_once(export) != (
        result["retained_export_sha256"],
        result["retained_export_size_bytes"],
    ):
        raise PT21MaterializerError(
            "PT21 retained predecessor differs from its signed result"
        )
    try:
        verify_retained_export_archive(
            export,
            phase=phase,
            shard_index=shard_index,
            tree_sha256=result["retained_tree_sha256"],
        )
    except (ArchiveError, PT21MeasuredWorkloadError, OSError, ValueError) as error:
        raise PT21MaterializerError(
            f"PT21 retained predecessor failed structural replay: {error}"
        ) from error
    return {
        "export_path": export,
        "export_sha256": result["retained_export_sha256"],
        "export_size_bytes": result["retained_export_size_bytes"],
        "group_id": group_id,
        "phase_id": phase,
        "portfolio_receipt_sha256": receipt["receipt_sha256"],
        "shard_index": shard_index,
        "tree_sha256": result["retained_tree_sha256"],
    }


def _single_predecessor_identity(
    factory: PT21CPUWorkloadFactory,
) -> tuple[str, str, int] | None:
    if factory.phase_id == "initialize":
        return None
    if factory.phase_id == "exact-multiplicity-count":
        phase = "initialize"
    elif factory.phase_id == "ordinary-low-index-prefix":
        phase = "exact-multiplicity-count"
    else:
        phase = "ordinary-low-index-prefix"
    return f"{CAMPAIGN_ID}::{phase}", phase, 0


def _tree(
    root: Path, *, domain: bytes, exclude: frozenset[str]
) -> tuple[int, int, str]:
    digest = hashlib.sha256(domain)
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() or relative in exclude:
            continue
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PT21MaterializerError(
                "PT21 handoff contains a linked or special file"
            )
        file_hash, size = hash_file_once(path)
        encoded = relative.encode("utf-8")
        count += 1
        total += size
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(file_hash))
    return count, total, digest.hexdigest()


def _copy_export_receipt(
    export: Path, *, phase: str, shard_index: int, destination: Path
) -> tuple[str, int]:
    temporary = destination.parent / f".expanded-{shard_index:07d}"
    try:
        extract_archive(
            export,
            temporary,
            maximum_files=4,
            maximum_bytes=16 * 1024 * 1024,
        )
        receipt = (
            temporary
            / "campaign/shards"
            / f"receipt-{shard_index:07d}.json"
        )
        raw = receipt.read_bytes()
        _write_bytes(destination, raw)
        return hashlib.sha256(raw).hexdigest(), len(raw)
    except (ArchiveError, OSError, ValueError) as error:
        raise PT21MaterializerError(
            f"cannot compact authenticated PT21 shard {shard_index}: {error}"
        ) from error
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _create_handoff(
    context: azure_portfolio.PortfolioContext,
    factory: PT21CPUWorkloadFactory,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = artifact_root / ".pt21-handoff"
    root.mkdir(mode=0o700)
    state = azure_portfolio.load_state(context)
    retained_root = site["retained_export_root"]
    entry: dict[str, Any] | None = None
    coverage: dict[str, Any] | None = None
    mode = "empty"
    export_merkle = _MerkleAccumulator()
    receipt_merkle = _MerkleAccumulator()
    try:
        predecessor = _single_predecessor_identity(factory)
        if predecessor is not None:
            group_id, phase, index = predecessor
            row = _verified_predecessor(
                context,
                state,
                group_id=group_id,
                phase=phase,
                shard_index=index,
                retained_root=retained_root,
            )
            relative = "prefix-state.tar" if factory.terminal else "predecessor.tar"
            destination = root / relative
            _copy_exact(row["export_path"], destination)
            entry = {
                "group_id": row["group_id"],
                "path": relative,
                "phase_id": row["phase_id"],
                "portfolio_receipt_sha256": row[
                    "portfolio_receipt_sha256"
                ],
                "sha256": row["export_sha256"],
                "shard_index": row["shard_index"],
                "size_bytes": row["export_size_bytes"],
                "tree_sha256": row["tree_sha256"],
            }
            mode = "single-predecessor"
        if factory.terminal:
            mode = "full-finalization"
            receipt_tree = hashlib.sha256(FINAL_RECEIPT_TREE_DOMAIN)
            shard_group = f"{CAMPAIGN_ID}::platt-turing-index-shards"
            for index in range(SHARD_COUNT):
                row = _verified_predecessor(
                    context,
                    state,
                    group_id=shard_group,
                    phase="platt-turing-index-shards",
                    shard_index=index,
                    retained_root=retained_root,
                )
                export_merkle.add(row["export_sha256"])
                receipt_merkle.add(row["portfolio_receipt_sha256"])
                relative = f"shards/receipt-{index:07d}.json"
                receipt_sha256, receipt_size = _copy_export_receipt(
                    row["export_path"],
                    phase="platt-turing-index-shards",
                    shard_index=index,
                    destination=root / relative,
                )
                encoded = relative.encode("utf-8")
                receipt_tree.update(len(encoded).to_bytes(8, "big"))
                receipt_tree.update(encoded)
                receipt_tree.update(receipt_size.to_bytes(8, "big"))
                receipt_tree.update(bytes.fromhex(receipt_sha256))
            if export_merkle.count != SHARD_COUNT or receipt_merkle.count != SHARD_COUNT:
                raise PT21MaterializerError(
                    "PT21 final handoff did not authenticate every shard"
                )
            coverage = {
                "export_identity_merkle_root_sha256": export_merkle.root(),
                "first_shard_index": 0,
                "portfolio_receipt_merkle_root_sha256": receipt_merkle.root(),
                "receipt_tree_sha256": receipt_tree.hexdigest(),
                "shard_count": SHARD_COUNT,
                "upper_shard_index_exclusive": SHARD_COUNT,
            }
        count, total, tree = _tree(
            root,
            domain=HANDOFF_TREE_DOMAIN,
            exclude=frozenset({"handoff.json"}),
        )
        handoff = {
            "entry": entry,
            "file_count": count,
            "kind": HANDOFF_KIND,
            "mode": mode,
            "schema_version": 1,
            "shard_coverage": coverage,
            "target_phase": factory.phase_id,
            "target_shard_index": factory.shard_index,
            "total_bytes": total,
            "tree_sha256": tree,
        }
        _write_bytes(root / "handoff.json", canonical_json_bytes(handoff))
        destination = artifact_root / "input/pt21-phase-handoff.tar"
        create_archive(root, destination)
        summary = {
            "authenticated_predecessor_count": (
                SHARD_COUNT + 1
                if factory.terminal
                else (0 if entry is None else 1)
            ),
            "entry": entry,
            "shard_coverage": coverage,
        }
        return destination, handoff, summary
    finally:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)


def _source_and_runtime_records(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime = _runtime_identity(
        site["pt21"]["runtime"],
        context=context,
        flint_source_root=Path(site["pt21"]["flint_source_root"]),
    )
    records: list[dict[str, Any]] = []
    source_rows = []
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(
            source, destination, executable=relative.startswith("tools/")
        )
        pin = _file_pin(destination)
        if (pin["sha256"], pin["size_bytes"]) != (
            row["sha256"],
            row["size_bytes"],
        ):
            raise PT21MaterializerError(
                f"PT21 source changed during copy: {relative}"
            )
        source_rows.append(
            {
                "path": relative,
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
        )
        records.append(
            _artifact_record(
                destination,
                artifact_root,
                role="reviewed_source",
                statement_role=None,
                executable=relative.startswith("tools/"),
            )
        )
    artifacts = artifact_root / "artifacts"
    python_target = artifacts / "python3"
    runner_target = artifacts / "tg_platt_zeta_shard"
    _copy_exact(runtime["python_path"], python_target, executable=True)
    _copy_exact(runtime["runner_path"], runner_target, executable=True)
    runtime_target = artifact_root / "source/pt21-runtime-closure.json"
    _copy_exact(runtime["manifest_path"], runtime_target)
    records.extend(
        [
            _artifact_record(
                python_target,
                artifact_root,
                role="image_bound_cpython_host",
                statement_role="host_executable",
                executable=True,
            ),
            _artifact_record(
                runner_target,
                artifact_root,
                role="static_flint_pt21_phase_runner",
                statement_role="producer_executable",
                executable=True,
            ),
            _artifact_record(
                runtime_target,
                artifact_root,
                role="reviewed_runtime_closure_manifest",
                statement_role=None,
                executable=False,
            ),
        ]
    )
    source_manifest = {
        "execution_contract_sha256": CONTRACT_FILE_SHA256,
        "files": sorted(source_rows, key=lambda row: row["path"]),
        "flint_tracked_tree_sha256": runtime["manifest"]["flint"][
            "tracked_tree_sha256"
        ],
        "kind": "sparkinterval.pt21-source-reviewed-closure.v1",
        "runtime_manifest_sha256": runtime["manifest_pin"]["sha256"],
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(source_manifest_path, canonical_json_bytes(source_manifest))
    records.append(
        _artifact_record(
            source_manifest_path,
            artifact_root,
            role="reviewed_source_closure_manifest",
            statement_role="source_tree",
            executable=False,
        )
    )
    records.sort(key=lambda row: row["path"])
    return records, {
        "execution_contract_id": REFERENCE_CONTRACT_ID,
        "execution_contract_sha256": CONTRACT_FILE_SHA256,
        "flint": runtime["manifest"]["flint"],
        "manifest": runtime["manifest_pin"],
        "python": runtime["python_pin"],
        "runner": runtime["runner_pin"],
    }


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: PT21CPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    handoff: Path,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = artifact_root / "input/registered-invocation.json"
    _write_bytes(input_path, factory.input_bytes)
    records.append(
        _artifact_record(
            handoff,
            artifact_root,
            role="authenticated_pt21_predecessor_handoff",
            statement_role=None,
            executable=False,
        )
    )
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    if factory.terminal:
        expected = registered_invocation_expected(REGISTERED_INVOCATION)
        local = expected_registered_hashes()
        if (
            registered_invocation_backend(REGISTERED_INVOCATION)
            != cpu_operator.BACKEND
            or expected
            != {
                **local,
                "result": "true",
                "target": "azure_sevsnp_cpu",
                "trust": "azure_sevsnp_confidential_compute",
            }
        ):
            raise PT21MaterializerError(
                "terminal PT21 factory differs from the registered invocation"
            )
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    records.sort(key=lambda row: row["path"])
    job = {
        "algorithm": {
            "algorithm_id": factory.algorithm_id,
            "canonical_definition": factory.algorithm_definition,
            "definition_sha256": algorithm_hash,
        },
        "artifact_closure": {
            "closure_kind": "content_addressed_image_source_reviewed_v1",
            "files": records,
            "manifest_sha256": canonical_sha256(
                _closure_manifest(records)
            ),
        },
        "backend": cpu_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv),
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
            "sha256": hashlib.sha256(factory.input_bytes).hexdigest(),
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": (
            f"tg-platt-pt21-{factory.phase_id}-"
            f"{factory.shard_index:07d}-cpu-v1"
        ),
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": (
                "output/registered-result.txt"
                if factory.terminal
                else "output/phase-result.json"
            ),
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
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": TRACE_DEFINITION,
            "trace_algorithm_sha256": hashlib.sha256(
                TRACE_DEFINITION.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(factory.trace_verifier_argv),
        },
    }
    validate_job_spec(job)
    return job


def plan_materialization(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    group, shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise PT21MaterializerError(
            "portfolio group has no complete reference PT21 CPU factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise PT21MaterializerError(
            "portfolio shard argv differs from the fixed PT21 factory"
        )
    contract = execution_contract(factory.execution_contract_id)
    if not production_capability_complete(contract):
        raise PT21MaterializerError(
            "PT21 production worker/finalizer capability is incomplete"
        )
    runtime = _runtime_identity(
        site["pt21"]["runtime"],
        context=context,
        flint_source_root=Path(site["pt21"]["flint_source_root"]),
    )
    for relative in (*SOURCE_PATHS, *PROFILE_PATHS.values()):
        _source_pin(context, relative)
    issued = cpu_operator.dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    expires = cpu_operator.dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    ttl = int((expires - issued).total_seconds())
    if (
        ttl
        <= factory.timeout_seconds
        + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS
    ):
        raise PT21MaterializerError(
            "challenge TTL cannot contain the PT21 phase and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise PT21MaterializerError(
            "materializer output_root must stay outside the repository"
        )
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": platform.machine() == "x86_64",
        "challenge": {
            **_file_pin(challenge_path),
            "nonce": challenge["nonce"],
        },
        "classification": (
            "reviewed_unscaled_pt21_materialization_plan_not_execution_evidence"
        ),
        "economic_production_gate_passed": False,
        "execution_contract_id": factory.execution_contract_id,
        "execution_contract_sha256": factory.execution_contract_sha256,
        "factory_id": factory.factory_id,
        "full_source_shard_count": SHARD_COUNT,
        "group_id": group_id,
        "output_root": str(output_root),
        "phase_id": factory.phase_id,
        "registered_invocation": factory.registered_invocation,
        "runtime": {
            "manifest": runtime["manifest_pin"],
            "python": runtime["python_pin"],
            "runner": runtime["runner_pin"],
        },
        "semantic_terminal": factory.terminal,
        "shard_config": {
            **_file_pin(shard_path),
            "task_id": shard["task_id"],
        },
        "shard_index": shard_index,
        "under_one_week_and_10000_usd": False,
    }


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(
        context, group_id, shard_index, site
    )
    if not plan["build_host_supported"]:
        raise PT21MaterializerError(
            "this host cannot package the x86_64 PT21 runtime closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise PT21MaterializerError("reviewed PT21 factory disappeared")
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.pt21-materializing-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, runtime = _source_and_runtime_records(
            context, site, artifact_root
        )
        handoff_path, handoff, predecessor_summary = _create_handoff(
            context, factory, site, artifact_root
        )
        job = _job(
            context,
            factory,
            artifact_root,
            records,
            handoff_path,
            site,
        )
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        transcript_policy = _transcript_policy(
            site["base"], record_hash(job_path), job
        )
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path,
            cpu_operator.canonical_json_bytes(transcript_policy),
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise PT21MaterializerError(
                "materializer output_root appeared during build"
            )
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site=site["base"],
            factory=factory,
            challenge=challenge,
            challenge_path=challenge_path,
            artifact_root=artifact_root,
            package=package,
            transcript_policy_path=transcript_path,
        )
        config_path = output_root / "cpu-campaign.json"
        _write_bytes(
            config_path, cpu_operator.canonical_json_bytes(config)
        )
        _validated, config_hash = cpu_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_unscaled_pt21_operator_validated_"
                "materialization_not_execution_evidence"
            ),
            "cpu_operator_config": {
                **_file_pin(config_path),
                "sha256": config_hash,
            },
            "economic_production_gate_passed": False,
            "execution_completed": False,
            "execution_contract_id": factory.execution_contract_id,
            "execution_contract_sha256": factory.execution_contract_sha256,
            "factory_id": factory.factory_id,
            "full_source_shard_count": SHARD_COUNT,
            "handoff": handoff,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "phase_id": factory.phase_id,
            "portfolio_shard_config": _file_pin(shard_path),
            "predecessors": predecessor_summary,
            "registered_invocation": factory.registered_invocation,
            "runtime": runtime,
            "schema_version": SCHEMA_VERSION,
            "semantic_terminal": factory.terminal,
            "shard_index": factory.shard_index,
            "source_run_receipt_produced": False,
            "transcript_policy": _file_pin(transcript_path),
            "under_one_week_and_10000_usd": False,
        }
        manifest_path = output_root / "materialization-manifest.json"
        _write_bytes(
            manifest_path, cpu_operator.canonical_json_bytes(manifest)
        )
        complete = True
        return {
            **manifest,
            "cpu_operator_config": {
                **manifest["cpu_operator_config"],
                "path": str(config_path),
            },
            "job_spec": {
                **manifest["job_spec"],
                "path": str(job_path),
            },
            "manifest": str(manifest_path),
            "package": {
                **manifest["package"],
                "path": str(package),
            },
        }
    except (
        ArchiveError,
        CampaignIOError,
        CommonMaterializerError,
        PlattHeadMaterializerError,
        PT21MaterializerError,
        PT21WorkloadFactoryError,
        OSError,
        ValueError,
    ) as error:
        if isinstance(error, PT21MaterializerError):
            raise
        raise PT21MaterializerError(
            f"PT21 materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "MANIFEST_KIND",
    "RUNTIME_KIND",
    "SITE_KIND",
    "PT21MaterializerError",
    "load_site",
    "materialize",
    "plan_materialization",
]
