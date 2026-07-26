# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize source-closed shared-Hurst jobs for Azure SEV-SNP CPUs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from tg_verifier import azure_portfolio
from tg_verifier.azure_cpu_hurst_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COUNTS,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    HurstCPUWorkloadFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_hurst_affine_workload_factory import (
    HurstAffineCPUWorkloadFactory,
    expected_predecessors as affine_expected_predecessors,
    factory_for_portfolio_group as affine_factory_for_portfolio_group,
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
    _run_build,
    _source_pin,
    _transcript_policy,
    _write_bytes,
    load_site as load_base_site,
    record_hash,
)
from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes as campaign_json_bytes,
    load_json,
)
from tg_verifier.evidence import EvidenceError, load_decimal_json_bytes
from tg_verifier.hurst_residual_campaign import (
    HurstResidualCampaignError,
    MIN_SEGMENT_SIZE,
    UPSTREAM_COMMIT,
    validate_runner_receipt,
)
from tg_verifier.hurst_affine_campaign import (
    HurstAffineCampaignError,
    validate_affine_runner_receipt,
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
from fetch_hurst_mertens import (  # noqa: E402
    FetchError,
    load_pin as load_upstream_pin,
    verify_checkout,
)
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
    registered_invocation_backend,
    registered_invocation_expected,
)
from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from measured_runner import (  # noqa: E402
    _closure_manifest,
    canonical_sha256,
    load_profile,
    validate_job_spec,
)


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.hurst-portfolio-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.hurst-portfolio-materialization.v1"
SITE_FIELDS = {"base_site", "hurst", "kind", "schema_version"}
HURST_FIELDS = {"boost_include_root", "hurst_source_root", "predecessor_exports"}
PREDECESSOR_FIELDS = {"export", "group_id", "shard_index"}
BOOST_HEADER_COUNT = 15_653
BOOST_HEADER_BYTES = 149_594_508
BOOST_HEADER_TREE_SHA256 = (
    "7ecf4808a419bd489f930c685320cf2745e46c6bc5591122c26773386214d8e2"
)
BOOST_TREE_DOMAIN = b"sparkinterval/boost-header-tree/v1\0"
TREE_DOMAIN = b"sparkinterval/hurst-retained-tree/v1\0"
FIXED_TOOL_PATH = "/usr/bin:/bin:/usr/local/bin"
REQUIRED_BUILD_TOOLS = ("g++", "python3")
IDENTITY_FIELDS = {
    "runner_sha256",
    "runner_size_bytes",
    "source_sha256",
    "source_size_bytes",
    "upstream_manifest_sha256",
    "upstream_manifest_size_bytes",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
OPERATIONAL_RESULT_KIND = "sparkinterval.azure.hurst-operational-result.v1"
EXPORT_KIND = "sparkinterval.azure.hurst-retained-export.v1"
HANDOFF_KIND = "sparkinterval.azure.hurst-phase-handoff.v1"


class HurstMaterializerError(RuntimeError):
    """A source pin, predecessor, build, or measured job failed closed."""


def _factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int,
) -> HurstCPUWorkloadFactory | HurstAffineCPUWorkloadFactory | None:
    """Select exactly one reviewed two-pass or affine operational factory."""

    legacy = factory_for_portfolio_group(group, shard_index)
    affine = affine_factory_for_portfolio_group(group, shard_index)
    if legacy is not None and affine is not None:
        raise HurstMaterializerError("ambiguous Hurst workload factory")
    return legacy if legacy is not None else affine


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise HurstMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise HurstMaterializerError(f"{what} must be a non-symlink directory")
    return path


def _digest(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HurstMaterializerError(f"{what} must be lowercase SHA-256 hex")
    return value


def _integer(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HurstMaterializerError(f"{what} must be an integer >= {minimum}")
    return value


def _boost_identity(root: Path) -> dict[str, Any]:
    boost = root / "boost" if (root / "boost").is_dir() else root
    digest = hashlib.sha256(BOOST_TREE_DOMAIN)
    count = 0
    size = 0
    for path in sorted(boost.rglob("*")):
        if path.is_symlink():
            raise HurstMaterializerError("Boost header closure contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise HurstMaterializerError(
                "Boost header closure contains a special file"
            )
        relative = path.relative_to(boost).as_posix().encode("utf-8")
        raw = path.read_bytes()
        count += 1
        size += len(raw)
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    identity = {
        "file_count": count,
        "size_bytes": size,
        "tree_sha256": digest.hexdigest(),
    }
    if identity != {
        "file_count": BOOST_HEADER_COUNT,
        "size_bytes": BOOST_HEADER_BYTES,
        "tree_sha256": BOOST_HEADER_TREE_SHA256,
    }:
        raise HurstMaterializerError(
            "Boost 1.83 header closure differs from the reviewed pin"
        )
    if not (boost / "multiprecision/cpp_int.hpp").is_file():
        raise HurstMaterializerError("reviewed Boost closure lacks cpp_int.hpp")
    return {**identity, "path": str(boost)}


def _upstream_identity(root: Path) -> dict[str, Any]:
    try:
        identity = verify_checkout(root, load_upstream_pin())
    except (FetchError, OSError, ValueError) as error:
        raise HurstMaterializerError(
            f"pinned Hurst checkout failed review: {error}"
        ) from error
    if identity.get("commit") != UPSTREAM_COMMIT:
        raise HurstMaterializerError("Hurst checkout has the wrong source commit")
    return identity


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HurstMaterializerError(
            f"cannot load canonical Hurst materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "Hurst materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise HurstMaterializerError("unsupported Hurst materializer site kind/version")
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise HurstMaterializerError(str(error)) from error
    hurst = _exact(site["hurst"], HURST_FIELDS, "Hurst build inputs")
    upstream = _directory(hurst["hurst_source_root"], "Hurst source root")
    boost = _directory(hurst["boost_include_root"], "Boost include root")
    _upstream_identity(upstream)
    _boost_identity(boost)
    if not isinstance(hurst["predecessor_exports"], list):
        raise HurstMaterializerError("predecessor_exports must be an array")
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(hurst["predecessor_exports"]):
        row = _exact(raw, PREDECESSOR_FIELDS, f"predecessor export {index}")
        if not isinstance(row["group_id"], str) or not row["group_id"]:
            raise HurstMaterializerError("predecessor group_id is malformed")
        shard = row["shard_index"]
        if isinstance(shard, bool) or not isinstance(shard, int) or shard < 0:
            raise HurstMaterializerError("predecessor shard_index is malformed")
        identity = (row["group_id"], shard)
        if identity in seen:
            raise HurstMaterializerError("duplicate predecessor export identity")
        seen.add(identity)
        _pin(row["export"], f"predecessor export {index}")
    return {"base": base, "hurst": hurst, "site_pin": _file_pin(path)}


def _expected_predecessors(
    factory: HurstCPUWorkloadFactory | HurstAffineCPUWorkloadFactory,
) -> tuple[tuple[str, int], ...]:
    if isinstance(factory, HurstAffineCPUWorkloadFactory):
        return affine_expected_predecessors(factory)
    campaign = CAMPAIGN_ID
    if factory.phase_id == "initialize":
        return ()
    if factory.phase_id == "summary-shards":
        return ((f"{campaign}::initialize", 0),)
    if factory.phase_id == "reduce-summaries":
        return tuple(
            (f"{campaign}::summary-shards", index) for index in range(320)
        )
    if factory.phase_id == "verify-shards":
        return ((f"{campaign}::reduce-summaries", 0),)
    if factory.phase_id == "finalize-four-residual-certificate":
        return (
            (f"{campaign}::reduce-summaries", 0),
            *((f"{campaign}::verify-shards", index) for index in range(320)),
        )
    return ((f"{campaign}::finalize-four-residual-certificate", 0),)


def _identity_from(value: Mapping[str, Any], what: str) -> dict[str, Any]:
    identity = {name: value[name] for name in IDENTITY_FIELDS}
    for name in ("runner_sha256", "source_sha256", "upstream_manifest_sha256"):
        _digest(identity[name], f"{what} {name}")
    for name in (
        "runner_size_bytes",
        "source_size_bytes",
        "upstream_manifest_size_bytes",
    ):
        _integer(identity[name], f"{what} {name}", minimum=1)
    return identity


def _operational_result(
    receipt: Mapping[str, Any], phase: str, index: int
) -> dict[str, Any]:
    result = receipt["claim"]["result"]
    if hashlib.sha256(result.encode("utf-8")).hexdigest() != receipt["claim"][
        "output_hash"
    ]:
        raise HurstMaterializerError(
            "predecessor receipt result/output hash is inconsistent"
        )
    try:
        value = json.loads(result)
    except (TypeError, json.JSONDecodeError) as error:
        raise HurstMaterializerError("predecessor result is not JSON") from error
    fields = {
        "group_index",
        "kind",
        "phase",
        "retained_export_sha256",
        "retained_export_size_bytes",
        "retained_tree_sha256",
        "schema_version",
        *IDENTITY_FIELDS,
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or campaign_json_bytes(value).decode("utf-8") != result
        or value["kind"] != OPERATIONAL_RESULT_KIND
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != index
    ):
        raise HurstMaterializerError("predecessor operational result differs")
    _digest(value["retained_export_sha256"], "predecessor export digest")
    _digest(value["retained_tree_sha256"], "predecessor tree digest")
    _integer(value["retained_export_size_bytes"], "predecessor export size", minimum=1)
    _identity_from(value, "predecessor")
    return value


def _predecessor_rows(
    context: azure_portfolio.PortfolioContext,
    factory: HurstCPUWorkloadFactory | HurstAffineCPUWorkloadFactory,
    site: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _expected_predecessors(factory)
    provided = {
        (row["group_id"], row["shard_index"]): row
        for row in site["hurst"]["predecessor_exports"]
    }
    if set(provided) != set(expected):
        raise HurstMaterializerError(
            "predecessor exports do not exactly cover the reviewed Hurst phase"
        )
    state = azure_portfolio.load_state(context)
    rows: list[dict[str, Any]] = []
    for group_id, shard_index in expected:
        group = azure_portfolio._group(context, group_id)
        predecessor_factory = _factory_for_portfolio_group(group, shard_index)
        if predecessor_factory is None or predecessor_factory.terminal:
            raise HurstMaterializerError(
                "predecessor is not a reviewed operational Hurst phase"
            )
        paths = azure_portfolio._task_paths(context, group_id, shard_index)
        task_id = paths["task_id"].name
        record = state["records"].get(task_id)
        if record is None:
            raise HurstMaterializerError("predecessor has no portfolio receipt")
        azure_portfolio._validate_task_record(context, task_id, record)
        if record["stage"] != "verified_receipt_recorded":
            raise HurstMaterializerError(
                "predecessor portfolio receipt is incomplete"
            )
        try:
            receipt = load_verified_receipt(
                paths["receipt"], key_manifest=context.verifier_key_manifest
            )
        except Exception as error:
            raise HurstMaterializerError(
                f"predecessor receipt failed verification: {error}"
            ) from error
        claim = receipt["claim"]
        if (
            receipt["backend"] != cpu_operator.BACKEND
            or claim["algorithm_id"] != predecessor_factory.algorithm_id
            or claim["algorithm_hash"]
            != hashlib.sha256(
                predecessor_factory.algorithm_definition.encode("utf-8")
            ).hexdigest()
            or claim["parameters_hash"]
            != canonical_sha256(predecessor_factory.parameters)
            or claim["domain_hash"] != canonical_sha256(predecessor_factory.domain)
        ):
            raise HurstMaterializerError(
                "predecessor receipt is not the reviewed Hurst phase job"
            )
        result = _operational_result(
            receipt, predecessor_factory.phase_id, predecessor_factory.shard_index
        )
        export_pin, export_path = _pin(
            provided[(group_id, shard_index)]["export"],
            f"retained predecessor {group_id}/{shard_index}",
        )
        if (export_pin["sha256"], export_pin["size_bytes"]) != (
            result["retained_export_sha256"],
            result["retained_export_size_bytes"],
        ):
            raise HurstMaterializerError(
                "retained predecessor differs from its signed result"
            )
        rows.append(
            {
                "export": export_pin,
                "group_id": group_id,
                "host_executable_sha256": claim["artifacts"][
                    "host_executable_hash"
                ],
                "identity": _identity_from(result, "predecessor"),
                "phase": predecessor_factory.phase_id,
                "receipt_sha256": receipt["receipt_sha256"],
                "shard_index": shard_index,
                "source_path": export_path,
                "source_tree_sha256": claim["artifacts"]["source_tree_hash"],
                "tree_sha256": result["retained_tree_sha256"],
            }
        )
    return rows


def plan_materialization(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    group, shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = _factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise HurstMaterializerError(
            "portfolio group has no closed Hurst CPU factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise HurstMaterializerError(
            "portfolio shard argv differs from the closed Hurst factory"
        )
    predecessors = _predecessor_rows(context, factory, site)
    for relative in (*SOURCE_PATHS, *PROFILE_PATHS.values()):
        _source_pin(context, relative)
    issued = cpu_operator.dt.datetime.strptime(
        challenge["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    expires = cpu_operator.dt.datetime.strptime(
        challenge["expires_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=cpu_operator.dt.timezone.utc)
    ttl = int((expires - issued).total_seconds())
    if ttl <= factory.timeout_seconds + cpu_operator.EVIDENCE_COLLECTION_MARGIN_SECONDS:
        raise HurstMaterializerError(
            "challenge TTL cannot contain the Hurst job and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise HurstMaterializerError(
            "materializer output_root must stay outside the repository"
        )
    tools = {
        name: shutil.which(name, path=FIXED_TOOL_PATH)
        for name in REQUIRED_BUILD_TOOLS
    }
    supported = platform.machine() == "x86_64" and all(tools.values())
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": "reviewed_hurst_materialization_plan_not_execution_evidence",
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "phase_id": factory.phase_id,
        "predecessors": [
            {
                "export": row["export"],
                "group_id": row["group_id"],
                "receipt_sha256": row["receipt_sha256"],
                "shard_index": row["shard_index"],
                "tree_sha256": row["tree_sha256"],
            }
            for row in predecessors
        ],
        "registered_invocation": factory.registered_invocation,
        "semantic_terminal": factory.terminal,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "tools_if_supported": tools,
        "upstreams": {
            "boost": _boost_identity(Path(site["hurst"]["boost_include_root"])),
            "hurst": _upstream_identity(
                Path(site["hurst"]["hurst_source_root"])
            ),
        },
    }


def _copy_upstream(
    checkout: Path, destination: Path, identity: Mapping[str, Any]
) -> list[Path]:
    copied: list[Path] = []
    files = identity.get("files")
    if not isinstance(files, list) or not files:
        raise HurstMaterializerError("verified Hurst closure has no source files")
    for row in files:
        relative = Path(row["path"])
        source = checkout / relative
        target = destination / relative
        _copy_exact(source, target, executable=os.access(source, os.X_OK))
        if _file_pin(target) != {
            "path": str(target),
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }:
            raise HurstMaterializerError(
                f"copied Hurst source differs from pin: {relative}"
            )
        copied.append(target)
    return copied


def _dependency_paths(path: Path) -> list[Path]:
    raw = path.read_text(encoding="utf-8").replace("\\\n", " ")
    if ":" not in raw:
        raise HurstMaterializerError("compiler dependency file is malformed")
    _target, dependencies = raw.split(":", 1)
    try:
        values = shlex.split(dependencies)
    except ValueError as error:
        raise HurstMaterializerError(
            "compiler dependency file cannot be parsed"
        ) from error
    return [Path(value).resolve(strict=True) for value in values]


def _runner_self_check(runner: Path) -> dict[str, Any]:
    base = [
        str(runner),
        "--lower",
        "1",
        "--upper",
        "199",
        "--segment-size",
        str(MIN_SEGMENT_SIZE),
    ]
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "OMP_DYNAMIC": "FALSE",
        "OMP_NUM_THREADS": "1",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    reports: dict[str, tuple[dict[str, Any], bytes]] = {}
    for phase in ("summary", "verify", "affine"):
        argv = [*base, "--mode", phase]
        if phase == "verify":
            argv.extend(
                [
                    "--incoming-mertens",
                    "0",
                    "--incoming-squarefree",
                    "0",
                    "--incoming-little-lower",
                    "0",
                    "--incoming-little-upper",
                    "0",
                ]
            )
        completed = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            env=environment,
        )
        if completed.returncode != 0:
            diagnostic = completed.stderr[-2000:].decode("utf-8", "replace")
            raise HurstMaterializerError(
                f"built Hurst runner {phase} self-check failed: {diagnostic}"
            )
        try:
            report = load_decimal_json_bytes(
                completed.stdout, label=f"built Hurst {phase} self-check"
            )
            if phase == "affine":
                validate_affine_runner_receipt(
                    report,
                    shard_lower=1,
                    shard_upper=200,
                    segment_size=MIN_SEGMENT_SIZE,
                )
            else:
                validate_runner_receipt(
                    report,
                    phase=phase,
                    shard_lower=1,
                    shard_upper=200,
                    segment_size=MIN_SEGMENT_SIZE,
                    expected_incoming=(
                        (0, 0, 0, 0) if phase == "verify" else None
                    ),
                )
        except (
            EvidenceError,
            HurstAffineCampaignError,
            HurstResidualCampaignError,
            ValueError,
        ) as error:
            raise HurstMaterializerError(
                f"built Hurst runner {phase} output failed validation: {error}"
            ) from error
        reports[phase] = (report, completed.stdout)
    if any(
        reports["summary"][0][field] != reports[phase][0][field]
        for phase in ("verify", "affine")
        for field in ("delta", "row_sha256")
    ):
        raise HurstMaterializerError(
            "built Hurst runner modes did not reproduce one bounded row stream"
        )
    return {
        "lower": 1,
        "row_sha256": reports["summary"][0]["row_sha256"],
        "summary_stdout_sha256": hashlib.sha256(reports["summary"][1]).hexdigest(),
        "upper_inclusive": 199,
        "verify_stdout_sha256": hashlib.sha256(reports["verify"][1]).hexdigest(),
        "affine_stdout_sha256": hashlib.sha256(reports["affine"][1]).hexdigest(),
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise HurstMaterializerError("Hurst production package must be built on x86_64")
    tool_paths: dict[str, Path] = {}
    for name in REQUIRED_BUILD_TOOLS:
        found = shutil.which(name, path=FIXED_TOOL_PATH)
        if found is None:
            raise HurstMaterializerError(f"closed Hurst build requires {name}")
        tool_paths[name] = Path(found).resolve(strict=True)
    boost_identity = _boost_identity(Path(site["hurst"]["boost_include_root"]))
    boost = Path(boost_identity["path"])
    upstream_root = Path(site["hurst"]["hurst_source_root"]).resolve(strict=True)
    upstream_identity = _upstream_identity(upstream_root)

    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        _row, source = _source_pin(context, relative)
        destination = artifact_root / "source" / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        copied[relative] = destination
    upstream_destination = artifact_root / "source/upstreams/hurst"
    upstream_files = _copy_upstream(
        upstream_root, upstream_destination, upstream_identity
    )

    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    python_target = artifacts / "python3"
    _copy_exact(tool_paths["python3"], python_target, executable=True)
    build_root = artifact_root / ".build"
    build_root.mkdir(mode=0o700)
    adapter_object = build_root / "hurst-adapter.o"
    upstream_object = build_root / "hurst-upstream.o"
    adapter_dependencies = build_root / "hurst-adapter.d"
    upstream_dependencies = build_root / "hurst-upstream.d"
    common_flags = [
        "-O3",
        "-std=c++20",
        "-march=x86-64-v2",
        "-mtune=generic",
        "-fno-strict-overflow",
        f"-ffile-prefix-map={artifact_root}=.",
        f"-fmacro-prefix-map={artifact_root}=.",
        f"-fdebug-prefix-map={artifact_root}=.",
        f"-ffile-prefix-map={boost.parent}=source/boost-1.83",
        f"-fmacro-prefix-map={boost.parent}=source/boost-1.83",
        f"-fdebug-prefix-map={boost.parent}=source/boost-1.83",
        "-Wall",
        "-Wextra",
        "-fopenmp",
        "-DUSE_BUCKET_SIEVE=1",
        "-DSIEVE_NARROW_ENTRY=1",
        "-DSIEVE_SUB_BUCKETS=0",
        "-DUSE_DIVISION_FREE=1",
        f'-DSPARKINTERVAL_HURST_UPSTREAM_COMMIT="{UPSTREAM_COMMIT}"',
        "-I",
        str(artifact_root / "source/gpu/include"),
        "-I",
        str(boost.parent),
        "-I",
        str(upstream_destination / "sieve"),
    ]
    build_steps = [
        _run_build(
            [
                str(tool_paths["g++"]),
                *common_flags,
                "-MMD",
                "-MF",
                str(adapter_dependencies),
                "-c",
                str(copied["reference/tg_hurst_residual_shard.cpp"]),
                "-o",
                str(adapter_object),
            ],
            cwd=artifact_root,
        ),
        _run_build(
            [
                str(tool_paths["g++"]),
                *common_flags,
                "-MMD",
                "-MF",
                str(upstream_dependencies),
                "-c",
                str(upstream_destination / "sieve/SegmentedMobiusSieve.cpp"),
                "-o",
                str(upstream_object),
            ],
            cwd=artifact_root,
        ),
    ]
    runner = artifacts / "tg_hurst_residual_shard"
    build_steps.append(
        _run_build(
            [
                str(tool_paths["g++"]),
                "-static",
                "-fopenmp",
                str(adapter_object),
                str(upstream_object),
                "-lm",
                "-Wl,--build-id=sha1",
                "-o",
                str(runner),
            ],
            cwd=artifact_root,
        )
    )
    runner.chmod(0o500)
    _require_x86_64_static_elf(runner)
    self_check = _runner_self_check(runner)
    build_steps.append(
        {"kind": "bounded_summary_verify_affine_self_check", **self_check}
    )

    boost_dependencies: list[Path] = []
    dependency_paths = {
        *_dependency_paths(adapter_dependencies),
        *_dependency_paths(upstream_dependencies),
    }
    for dependency in sorted(dependency_paths):
        try:
            dependency.relative_to(artifact_root / "source")
            continue
        except ValueError:
            pass
        try:
            relative = dependency.relative_to(boost)
        except ValueError:
            raise HurstMaterializerError(
                f"compiler used an unreviewed non-system header: {dependency}"
            )
        destination = artifact_root / "source/boost-1.83/boost" / relative
        _copy_exact(dependency, destination)
        boost_dependencies.append(destination)
    if not boost_dependencies:
        raise HurstMaterializerError(
            "compiler did not report the pinned Boost dependency closure"
        )

    runner_pin = _file_pin(runner)
    source_pin = _file_pin(copied["reference/tg_hurst_residual_shard.cpp"])
    upstream_manifest_pin = _file_pin(
        copied["specifications/HURST_MERTENS_UPSTREAM.json"]
    )
    runtime_identity = {
        "runner_sha256": runner_pin["sha256"],
        "runner_size_bytes": runner_pin["size_bytes"],
        "source_sha256": source_pin["sha256"],
        "source_size_bytes": source_pin["size_bytes"],
        "upstream_manifest_sha256": upstream_manifest_pin["sha256"],
        "upstream_manifest_size_bytes": upstream_manifest_pin["size_bytes"],
    }
    runtime = {
        "boost_header_tree_sha256": BOOST_HEADER_TREE_SHA256,
        "dynamic_runtime_boundary": (
            "copied CPython executable plus immutable Azure image loader, libc, and stdlib"
        ),
        "identity": runtime_identity,
        "kind": "sparkinterval.hurst.image-runtime-closure.v1",
        "python_executable": {
            **_file_pin(python_target),
            "path": "artifacts/python3",
        },
        "schema_version": 1,
        "upstream_commit": UPSTREAM_COMMIT,
    }
    python_version = subprocess.run(
        [str(python_target), "-I", "--version"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
    )
    version_raw = python_version.stdout or python_version.stderr
    if python_version.returncode != 0 or not version_raw.startswith(b"Python 3."):
        raise HurstMaterializerError(
            "copied CPython runtime failed its isolated version check"
        )
    runtime["python_version"] = version_raw.decode("ascii", "strict").strip()
    runtime_path = artifact_root / "source/runtime-closure.json"
    _write_bytes(runtime_path, cpu_operator.canonical_json_bytes(runtime))

    records = [
        _artifact_record(
            python_target,
            artifact_root,
            role="image_bound_cpython_host",
            statement_role="host_executable",
            executable=True,
        ),
        _artifact_record(
            runner,
            artifact_root,
            role="static_hurst_four_residual_shard_producer",
            statement_role="producer_executable",
            executable=True,
        ),
        _artifact_record(
            runtime_path,
            artifact_root,
            role="image_runtime_closure_manifest",
            statement_role=None,
            executable=False,
        ),
    ]
    source_paths = [
        *copied.values(),
        *upstream_files,
        *boost_dependencies,
    ]
    source_rows = []
    for path in sorted(set(source_paths)):
        pin = _file_pin(path)
        source_rows.append(
            {
                "path": path.relative_to(artifact_root / "source").as_posix(),
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            }
        )
        records.append(
            _artifact_record(
                path,
                artifact_root,
                role="reviewed_source",
                statement_role=None,
                executable=os.access(path, os.X_OK),
            )
        )
    source_manifest = {
        "files": source_rows,
        "kind": "sparkinterval.hurst-source-reviewed-closure.v1",
        "runtime_identity": runtime_identity,
        "schema_version": 1,
        "upstream_commit": UPSTREAM_COMMIT,
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
    records.sort(key=lambda row: row["path"])
    compiler = {
        **_file_pin(tool_paths["g++"]),
        "version_line": subprocess.run(
            [str(tool_paths["g++"]), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.splitlines()[0],
    }
    runtime["compiler"] = compiler
    runtime["host_executable_sha256"] = _file_pin(python_target)["sha256"]
    runtime["source_tree_sha256"] = _file_pin(source_manifest_path)["sha256"]
    shutil.rmtree(build_root)
    return records, build_steps, runtime


def _retained_tree(root: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256(TREE_DOMAIN)
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == "export-manifest.json":
            continue
        if path.is_symlink():
            raise HurstMaterializerError(
                "retained export contains a linked or special file"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise HurstMaterializerError(
                "retained export contains a linked or special file"
            )
        pin = _file_pin(path)
        encoded = relative.encode("utf-8")
        count += 1
        total += pin["size_bytes"]
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(pin["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(pin["sha256"]))
    return count, total, digest.hexdigest()


def _validate_retained_export(
    archive: Path,
    *,
    phase: str,
    shard_index: int,
    tree_sha256: str,
    identity: Mapping[str, Any],
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix=".hurst-export-audit-"))
    try:
        extract_archive(
            archive,
            temporary / "export",
            maximum_files=100_100,
            maximum_bytes=128 * 1024**3,
        )
        root = temporary / "export"
        manifest = load_json(root / "export-manifest.json", require_canonical=True)
        fields = {
            "file_count",
            "group_index",
            "kind",
            "phase",
            "schema_version",
            "total_bytes",
            "tree_sha256",
            *IDENTITY_FIELDS,
        }
        count, total, tree = _retained_tree(root)
        if (
            not isinstance(manifest, dict)
            or set(manifest) != fields
            or manifest["kind"] != EXPORT_KIND
            or manifest["schema_version"] != 1
            or manifest["phase"] != phase
            or manifest["group_index"] != shard_index
            or manifest["file_count"] != count
            or manifest["total_bytes"] != total
            or manifest["tree_sha256"] != tree
            or tree != tree_sha256
            or {name: manifest[name] for name in IDENTITY_FIELDS}
            != dict(identity)
        ):
            raise HurstMaterializerError(
                "retained Hurst predecessor export failed independent tree replay"
            )
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        if isinstance(error, HurstMaterializerError):
            raise
        raise HurstMaterializerError(
            f"cannot audit retained Hurst predecessor export: {error}"
        ) from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _create_handoff(
    artifact_root: Path,
    factory: HurstCPUWorkloadFactory | HurstAffineCPUWorkloadFactory,
    predecessors: list[dict[str, Any]],
    runtime: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    identity = runtime["identity"]
    handoff_root = artifact_root / ".handoff"
    handoff_root.mkdir(mode=0o700)
    entries = []
    try:
        for order, row in enumerate(predecessors):
            if (
                row["identity"] != identity
                or row["host_executable_sha256"]
                != runtime["host_executable_sha256"]
                or row["source_tree_sha256"] != runtime["source_tree_sha256"]
            ):
                raise HurstMaterializerError(
                    "predecessor source or binary closure differs from this phase"
                )
            _validate_retained_export(
                row["source_path"],
                phase=row["phase"],
                shard_index=row["shard_index"],
                tree_sha256=row["tree_sha256"],
                identity=identity,
            )
            relative = f"exports/{order:03d}-{row['shard_index']:09d}.tar"
            destination = handoff_root / relative
            _copy_exact(row["source_path"], destination)
            pin = _file_pin(destination)
            entries.append(
                {
                    "group_id": row["group_id"],
                    **identity,
                    "path": relative,
                    "sha256": pin["sha256"],
                    "shard_index": row["shard_index"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        handoff = {
            "entries": entries,
            "group_index": factory.shard_index,
            "kind": HANDOFF_KIND,
            "phase": factory.phase_id,
            "schema_version": 1,
        }
        _write_bytes(
            handoff_root / "handoff.json", cpu_operator.canonical_json_bytes(handoff)
        )
        destination = artifact_root / "input/hurst-phase-handoff.tar"
        create_archive(handoff_root, destination)
        return destination, handoff
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)


def _profile_and_policy_records(
    context: azure_portfolio.PortfolioContext,
    artifact_root: Path,
    site: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    profile_records: dict[str, dict[str, Any]] = {}
    for kind, relative in PROFILE_PATHS.items():
        _row, source = _source_pin(context, relative)
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        value = load_profile(destination, kind)
        profile_records[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": value["profile_id"],
            "sha256": canonical_sha256(value),
        }
    runner_pin, runner_source = _pin(
        site["base"]["policies"]["runner"], "runner policy", policy=True
    )
    runner_path = artifact_root / "profiles/runner-policy.json"
    _copy_exact(runner_source, runner_path)
    return profile_records, {
        "path": runner_path.relative_to(artifact_root).as_posix(),
        "policy_id": runner_pin["policy_id"],
        "sha256": runner_pin["sha256"],
    }


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: HurstCPUWorkloadFactory | HurstAffineCPUWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    handoff_path: Path,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    if factory.terminal:
        input_path = artifact_root / "input/registered-invocation.json"
        _write_bytes(input_path, factory.input_bytes)
        records.append(
            _artifact_record(
                handoff_path,
                artifact_root,
                role="signed_predecessor_finalization_handoff",
                statement_role=None,
                executable=False,
            )
        )
    else:
        input_path = handoff_path
    profiles, runner_policy = _profile_and_policy_records(
        context, artifact_root, site
    )
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    input_hash = record_hash(input_path)
    if factory.terminal:
        expected = registered_invocation_expected(REGISTERED_INVOCATION)
        local = expected_registered_hashes()
        if expected != {
            **local,
            "result": "true",
            "target": "azure_sevsnp_cpu",
            "trust": "azure_sevsnp_confidential_compute",
        }:
            raise HurstMaterializerError("registered Hurst source identity changed")
        if (
            registered_invocation_backend(REGISTERED_INVOCATION)
            != cpu_operator.BACKEND
            or algorithm_hash != expected["algorithm_hash"]
            or input_hash != expected["input_hash"]
            or canonical_sha256(factory.parameters) != expected["parameters_hash"]
            or canonical_sha256(factory.domain) != expected["domain_hash"]
        ):
            raise HurstMaterializerError(
                "terminal Hurst factory differs from the Lean invocation"
            )
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
            "manifest_sha256": canonical_sha256(_closure_manifest(records)),
        },
        "backend": cpu_operator.BACKEND,
        "command": {
            "argv": list(factory.command_argv),
            "cwd": ".",
            "environment": {
                "LANG": "C",
                "LC_ALL": "C",
                "OMP_DYNAMIC": "FALSE",
                "OMP_NUM_THREADS": "40",
                "OMP_PROC_BIND": "spread",
                "TZ": "UTC",
            },
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
            "sha256": input_hash,
            "size_bytes": input_path.stat().st_size,
        },
        "job_id": f"tg-hurst-{factory.phase_id}-{factory.shard_index:03d}-cpu-v1",
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
            "trace_algorithm_definition": factory.trace_definition,
            "trace_algorithm_sha256": hashlib.sha256(
                factory.trace_definition.encode("utf-8")
            ).hexdigest(),
            "verification_mode": "pinned_external_trace_verifier_v1",
            "verifier_argv": list(factory.trace_verifier_argv),
        },
    }
    validate_job_spec(job)
    return job


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(context, group_id, shard_index, site)
    if not plan["build_host_supported"]:
        raise HurstMaterializerError(
            "this host cannot build the x86_64 Hurst production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = _factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise HurstMaterializerError("reviewed Hurst factory disappeared")
    predecessors = _predecessor_rows(context, factory, site)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.hurst-materializing-",
            dir=output_root.parent,
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, runtime = _build_runtime_closure(
            context, site, artifact_root
        )
        handoff_path, handoff = _create_handoff(
            artifact_root, factory, predecessors, runtime
        )
        job = _job(context, factory, artifact_root, records, handoff_path, site)
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
            raise HurstMaterializerError(
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
        _write_bytes(config_path, cpu_operator.canonical_json_bytes(config))
        _validated, config_hash = cpu_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_hurst_operator_validated_materialization_not_execution_evidence"
            ),
            "compiler": runtime["compiler"],
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "handoff": handoff,
            "job_spec": _file_pin(job_path),
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": _file_pin(package),
            "phase_id": factory.phase_id,
            "portfolio_shard_config": _file_pin(shard_path),
            "predecessor_receipts": [
                {
                    "group_id": row["group_id"],
                    "receipt_sha256": row["receipt_sha256"],
                    "shard_index": row["shard_index"],
                }
                for row in predecessors
            ],
            "registered_invocation": factory.registered_invocation,
            "runtime_identity": runtime["identity"],
            "schema_version": SCHEMA_VERSION,
            "semantic_terminal": factory.terminal,
            "shard_index": factory.shard_index,
            "source_run_receipt_produced": False,
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
        EvidenceError,
        FetchError,
        OSError,
        ValueError,
    ) as error:
        raise HurstMaterializerError(
            f"Hurst materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "HurstMaterializerError",
    "MANIFEST_KIND",
    "SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
