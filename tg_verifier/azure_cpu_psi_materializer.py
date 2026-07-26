# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize closed CH25 psi phase jobs for the Azure SEV-SNP operator."""

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
from tg_verifier.azure_cpu_psi_workload_factory import (
    CAMPAIGN_ID,
    PHASE_COUNTS,
    REGISTERED_INVOCATION,
    SOURCE_PATHS,
    PsiCPUWorkloadFactory,
    expected_registered_hashes,
    factory_for_portfolio_group,
    make_factory,
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
    hash_file_once,
    load_json,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (REPOSITORY_ROOT / "azure", REPOSITORY_ROOT / "attestation", REPOSITORY_ROOT / "tools"):
    if str(directory) not in os.sys.path:
        os.sys.path.insert(0, str(directory))

import cpu_production_orchestrator as cpu_operator  # noqa: E402
from fetch_psi_upstreams import (  # noqa: E402
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
from measured_runner import _closure_manifest, canonical_sha256, load_profile, validate_job_spec  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.cpu.psi-portfolio-materializer-site.v1"
MANIFEST_KIND = "sparkinterval.azure.cpu.psi-portfolio-materialization.v1"
SITE_FIELDS = {"base_site", "kind", "psi", "schema_version"}
PSI_FIELDS = {
    "boost_include_root",
    "crlibm_root",
    "predecessor_exports",
    "primesieve_root",
}
PREDECESSOR_FIELDS = {"export", "group_id", "shard_index"}
BOOST_HEADER_COUNT = 15_653
BOOST_HEADER_BYTES = 149_594_508
BOOST_HEADER_TREE_SHA256 = (
    "7ecf4808a419bd489f930c685320cf2745e46c6bc5591122c26773386214d8e2"
)
BOOST_TREE_DOMAIN = b"sparkinterval/boost-header-tree/v1\0"
FIXED_TOOL_PATH = "/usr/bin:/bin:/usr/local/bin"
REQUIRED_BUILD_TOOLS = (
    "g++",
    "gcc",
    "cmake",
    "make",
    "python3",
    "aclocal",
    "autoheader",
    "autoconf",
    "automake",
    "ar",
    "ranlib",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class PsiMaterializerError(RuntimeError):
    """A psi handoff, source closure, build, or measured job failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise PsiMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise PsiMaterializerError(f"{what} must be a non-symlink directory")
    return path


def _boost_identity(root: Path) -> dict[str, Any]:
    boost = root / "boost" if (root / "boost").is_dir() else root
    digest = hashlib.sha256(BOOST_TREE_DOMAIN)
    count = 0
    size = 0
    for path in sorted(boost.rglob("*")):
        if path.is_symlink():
            raise PsiMaterializerError("Boost header closure contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PsiMaterializerError("Boost header closure contains a special file")
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
        raise PsiMaterializerError("Boost 1.83 header closure differs from the reviewed pin")
    if not (boost / "multiprecision/cpp_int.hpp").is_file():
        raise PsiMaterializerError("reviewed Boost closure lacks cpp_int.hpp")
    return {**identity, "path": str(boost)}


def _upstream_identity(root: Path, component: str) -> dict[str, Any]:
    try:
        return verify_checkout(root, component, load_upstream_pin(component))
    except (FetchError, OSError, ValueError) as error:
        raise PsiMaterializerError(
            f"pinned {component} checkout failed review: {error}"
        ) from error


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PsiMaterializerError(f"cannot load canonical psi materializer site: {error}") from error
    site = _exact(value, SITE_FIELDS, "psi materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise PsiMaterializerError("unsupported psi materializer site kind/version")
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise PsiMaterializerError(str(error)) from error
    psi = _exact(site["psi"], PSI_FIELDS, "psi build inputs")
    primesieve = _directory(psi["primesieve_root"], "primesieve root")
    crlibm = _directory(psi["crlibm_root"], "CRlibm root")
    boost = _directory(psi["boost_include_root"], "Boost include root")
    _upstream_identity(primesieve, "primesieve")
    _upstream_identity(crlibm, "crlibm")
    _boost_identity(boost)
    if not isinstance(psi["predecessor_exports"], list):
        raise PsiMaterializerError("predecessor_exports must be an array")
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(psi["predecessor_exports"]):
        row = _exact(raw, PREDECESSOR_FIELDS, f"predecessor export {index}")
        if not isinstance(row["group_id"], str) or not row["group_id"]:
            raise PsiMaterializerError("predecessor group_id is malformed")
        shard = row["shard_index"]
        if isinstance(shard, bool) or not isinstance(shard, int) or shard < 0:
            raise PsiMaterializerError("predecessor shard_index is malformed")
        identity = (row["group_id"], shard)
        if identity in seen:
            raise PsiMaterializerError("duplicate predecessor export identity")
        seen.add(identity)
        _pin(row["export"], f"predecessor export {index}")
    return {"base": base, "psi": psi, "site_pin": _file_pin(path)}


def _expected_predecessors(factory: PsiCPUWorkloadFactory) -> tuple[tuple[str, int], ...]:
    campaign = CAMPAIGN_ID
    if factory.phase_id in ("initialize", "summary-shards"):
        return ()
    if factory.phase_id == "reduce-summaries":
        return tuple((f"{campaign}::summary-shards", index) for index in range(320))
    if factory.phase_id == "verify-shards":
        return ((f"{campaign}::reduce-summaries", 0),)
    if factory.phase_id == "finalize":
        return (
            (f"{campaign}::reduce-summaries", 0),
            *((f"{campaign}::verify-shards", index) for index in range(320)),
        )
    return ((f"{campaign}::finalize", 0),)


def _operational_result(receipt: Mapping[str, Any], phase: str, index: int) -> dict[str, Any]:
    result = receipt["claim"]["result"]
    if hashlib.sha256(result.encode("utf-8")).hexdigest() != receipt["claim"]["output_hash"]:
        raise PsiMaterializerError("predecessor receipt result/output hash is inconsistent")
    try:
        value = json.loads(result)
    except (TypeError, json.JSONDecodeError) as error:
        raise PsiMaterializerError("predecessor result is not JSON") from error
    fields = {
        "group_index",
        "kind",
        "phase",
        "retained_export_sha256",
        "retained_export_size_bytes",
        "retained_tree_sha256",
        "schema_version",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or campaign_json_bytes(value).decode("utf-8") != result
        or value["kind"] != "sparkinterval.azure.psi-operational-result.v1"
        or value["schema_version"] != 1
        or value["phase"] != phase
        or value["group_index"] != index
        or not isinstance(value["retained_export_size_bytes"], int)
        or isinstance(value["retained_export_size_bytes"], bool)
        or value["retained_export_size_bytes"] < 1
        or SHA256_RE.fullmatch(value["retained_export_sha256"]) is None
        or SHA256_RE.fullmatch(value["retained_tree_sha256"]) is None
    ):
        raise PsiMaterializerError("predecessor operational result differs")
    return value


def _predecessor_rows(
    context: azure_portfolio.PortfolioContext,
    factory: PsiCPUWorkloadFactory,
    site: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _expected_predecessors(factory)
    provided = {
        (row["group_id"], row["shard_index"]): row
        for row in site["psi"]["predecessor_exports"]
    }
    if set(provided) != set(expected):
        raise PsiMaterializerError("predecessor exports do not exactly cover the reviewed phase")
    state = azure_portfolio.load_state(context)
    rows: list[dict[str, Any]] = []
    for group_id, shard_index in expected:
        group = azure_portfolio._group(context, group_id)
        predecessor_factory = factory_for_portfolio_group(group, shard_index)
        if predecessor_factory is None or predecessor_factory.terminal:
            raise PsiMaterializerError("predecessor is not a reviewed operational psi phase")
        paths = azure_portfolio._task_paths(context, group_id, shard_index)
        task_id = paths["task_id"].name
        record = state["records"].get(task_id)
        if record is None:
            raise PsiMaterializerError("predecessor has no portfolio receipt")
        azure_portfolio._validate_task_record(context, task_id, record)
        if record["stage"] != "verified_receipt_recorded":
            raise PsiMaterializerError("predecessor portfolio receipt is incomplete")
        try:
            receipt = load_verified_receipt(
                paths["receipt"], key_manifest=context.verifier_key_manifest
            )
        except Exception as error:
            raise PsiMaterializerError(f"predecessor receipt failed verification: {error}") from error
        claim = receipt["claim"]
        if (
            receipt["backend"] != cpu_operator.BACKEND
            or claim["algorithm_id"] != predecessor_factory.algorithm_id
            or claim["algorithm_hash"]
            != hashlib.sha256(
                predecessor_factory.algorithm_definition.encode("utf-8")
            ).hexdigest()
            or claim["parameters_hash"] != canonical_sha256(predecessor_factory.parameters)
            or claim["domain_hash"] != canonical_sha256(predecessor_factory.domain)
        ):
            raise PsiMaterializerError("predecessor receipt is not the reviewed phase job")
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
            raise PsiMaterializerError("retained predecessor differs from its signed result")
        rows.append(
            {
                "export": export_pin,
                "group_id": group_id,
                "phase": predecessor_factory.phase_id,
                "shard_index": shard_index,
                "tree_sha256": result["retained_tree_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "source_path": export_path,
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
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise PsiMaterializerError("portfolio group has no closed psi CPU factory")
    if shard.get("argv") != list(factory.portfolio_argv):
        raise PsiMaterializerError("portfolio shard argv differs from the closed psi factory")
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
        raise PsiMaterializerError("challenge TTL cannot contain the psi job and evidence margin")
    output_root = _absolute(site["base"]["output_root"], "materializer output_root", exists=False)
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise PsiMaterializerError("materializer output_root must stay outside the repository")
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
        "classification": "reviewed_psi_materialization_plan_not_execution_evidence",
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "phase_id": factory.phase_id,
        "predecessors": [
            {
                key: row[key]
                for key in ("export", "group_id", "receipt_sha256", "shard_index", "tree_sha256")
            }
            for row in predecessors
        ],
        "registered_invocation": factory.registered_invocation,
        "semantic_terminal": factory.terminal,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "tools_if_supported": tools,
        "upstreams": {
            "boost": _boost_identity(Path(site["psi"]["boost_include_root"])),
            "crlibm": _upstream_identity(Path(site["psi"]["crlibm_root"]), "crlibm"),
            "primesieve": _upstream_identity(
                Path(site["psi"]["primesieve_root"]), "primesieve"
            ),
        },
    }


def _tracked_paths(checkout: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(checkout), "ls-files", "-z"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        env={"LANG": "C", "LC_ALL": "C", "PATH": FIXED_TOOL_PATH, "TZ": "UTC"},
    )
    if completed.returncode != 0:
        raise PsiMaterializerError("cannot enumerate pinned upstream checkout")
    try:
        paths = [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]
    except UnicodeDecodeError as error:
        raise PsiMaterializerError("upstream tracked path is not UTF-8") from error
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise PsiMaterializerError("upstream tracked paths are not unique and sorted")
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative != path.as_posix():
            raise PsiMaterializerError("upstream tracked path is unsafe")
    return paths


def _copy_upstream(checkout: Path, destination: Path) -> list[Path]:
    copied: list[Path] = []
    for relative in _tracked_paths(checkout):
        source = checkout / relative
        if source.is_symlink() or not source.is_file():
            raise PsiMaterializerError("upstream tracked source is not a regular file")
        target = destination / relative
        _copy_exact(source, target, executable=os.access(source, os.X_OK))
        copied.append(target)
    return copied


def _dependency_paths(path: Path) -> list[Path]:
    raw = path.read_text(encoding="utf-8").replace("\\\n", " ")
    if ":" not in raw:
        raise PsiMaterializerError("compiler dependency file is malformed")
    _target, dependencies = raw.split(":", 1)
    try:
        values = shlex.split(dependencies)
    except ValueError as error:
        raise PsiMaterializerError("compiler dependency file cannot be parsed") from error
    return [Path(value).resolve(strict=True) for value in values]


def _run_build_with_environment(
    argv: list[str], *, cwd: Path, additions: Mapping[str, str]
) -> dict[str, Any]:
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "SOURCE_DATE_EPOCH": "0",
        "TZ": "UTC",
        **additions,
    }
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PsiMaterializerError(f"closed psi build failed: {error}") from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise PsiMaterializerError(
            f"closed psi build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": additions,
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if platform.machine() != "x86_64":
        raise PsiMaterializerError("psi production package must be built on x86_64")
    tool_paths: dict[str, Path] = {}
    for name in REQUIRED_BUILD_TOOLS:
        found = shutil.which(name, path=FIXED_TOOL_PATH)
        if found is None:
            raise PsiMaterializerError(f"closed psi build requires {name}")
        tool_paths[name] = Path(found).resolve(strict=True)
    boost_identity = _boost_identity(Path(site["psi"]["boost_include_root"]))
    boost = Path(boost_identity["path"])
    primesieve_root = Path(site["psi"]["primesieve_root"]).resolve(strict=True)
    crlibm_root = Path(site["psi"]["crlibm_root"]).resolve(strict=True)
    _upstream_identity(primesieve_root, "primesieve")
    _upstream_identity(crlibm_root, "crlibm")

    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        _row, source = _source_pin(context, relative)
        destination = artifact_root / "source" / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        copied[relative] = destination
    upstream_destination = artifact_root / "source/upstreams"
    upstream_files = {
        "primesieve": _copy_upstream(
            primesieve_root, upstream_destination / "primesieve"
        ),
        "crlibm": _copy_upstream(crlibm_root, upstream_destination / "crlibm"),
    }

    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    python_target = artifacts / "python3"
    _copy_exact(tool_paths["python3"], python_target, executable=True)
    build_root = artifact_root / ".build"
    build_root.mkdir(mode=0o700)
    primesieve_build = build_root / "primesieve"
    build_steps = [
        _run_build(
            [
                str(tool_paths["cmake"]),
                "-S",
                str(upstream_destination / "primesieve"),
                "-B",
                str(primesieve_build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DBUILD_PRIMESIEVE=OFF",
                "-DBUILD_STATIC_LIBS=ON",
                "-DBUILD_SHARED_LIBS=OFF",
                "-DBUILD_DOC=OFF",
                "-DBUILD_MANPAGE=OFF",
                "-DBUILD_EXAMPLES=OFF",
                "-DBUILD_TESTS=OFF",
                "-DWITH_MULTIARCH=ON",
            ],
            cwd=build_root,
        ),
        _run_build(
            [
                str(tool_paths["cmake"]),
                "--build",
                str(primesieve_build),
                "--target",
                "libprimesieve-static",
                "-j8",
            ],
            cwd=build_root,
        ),
    ]
    crlibm_build = build_root / "crlibm"
    shutil.copytree(upstream_destination / "crlibm", crlibm_build)
    crlibm_environment = {
        "CC": str(tool_paths["gcc"]),
        "CFLAGS": (
            "-O3 -fno-fast-math -fno-associative-math -ffp-contract=off "
            "-frounding-math -fexcess-precision=standard"
        ),
    }
    build_steps.extend(
        [
            _run_build_with_environment(
                [str(crlibm_build / "prepare")],
                cwd=crlibm_build,
                additions=crlibm_environment,
            ),
            _run_build_with_environment(
                [str(tool_paths["make"]), "-j8"],
                cwd=crlibm_build,
                additions=crlibm_environment,
            ),
            _run_build_with_environment(
                [str(tool_paths["make"]), "check"],
                cwd=crlibm_build,
                additions=crlibm_environment,
            ),
        ]
    )
    runner = artifacts / "tg_psi_residual_shard"
    dependency_file = build_root / "psi-runner.d"
    compile_argv = [
        str(tool_paths["g++"]),
        "-O3",
        "-std=c++20",
        "-march=x86-64-v2",
        "-mtune=generic",
        "-fno-fast-math",
        "-fno-associative-math",
        "-ffp-contract=off",
        "-frounding-math",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-pthread",
        "-MMD",
        "-MF",
        str(dependency_file),
        "-I",
        str(artifact_root / "source/gpu/include"),
        "-I",
        str(boost.parent),
        "-I",
        str(upstream_destination / "primesieve/include"),
        "-I",
        str(upstream_destination / "crlibm"),
        "-DSPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT=\"4f85384851da23c36c01ec01ef85b5d9d246e556\"",
        "-DSPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT=\"eb3063791aa75bc9705b49283bf14250465220a7\"",
        str(copied["reference/tg_psi_residual_shard.cpp"]),
        str(primesieve_build / "libprimesieve.a"),
        str(crlibm_build / "libcrlibm.a"),
        "-lm",
        "-o",
        str(runner),
    ]
    build_steps.append(_run_build(compile_argv, cwd=artifact_root))
    runner.chmod(0o500)
    # The Python host is image-bound and dynamic; the arithmetic producer is
    # required to be a static x86_64 ELF.
    from tg_verifier.azure_cpu_portfolio_materializer import _require_x86_64_static_elf

    _require_x86_64_static_elf(runner)
    boost_dependencies: list[Path] = []
    for dependency in _dependency_paths(dependency_file):
        try:
            relative = dependency.relative_to(boost)
        except ValueError:
            continue
        destination = artifact_root / "source/boost-1.83" / relative
        _copy_exact(dependency, destination)
        boost_dependencies.append(destination)
    if not boost_dependencies:
        raise PsiMaterializerError("compiler did not report the pinned Boost dependency closure")

    runtime = {
        "boost_header_tree_sha256": BOOST_HEADER_TREE_SHA256,
        "dynamic_runtime_boundary": (
            "copied CPython executable plus immutable Azure image loader, libc, and stdlib"
        ),
        "kind": "sparkinterval.psi.image-runtime-closure.v1",
        "python_executable": {
            **_file_pin(python_target),
            "path": "artifacts/python3",
        },
        "schema_version": 1,
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
        raise PsiMaterializerError("copied CPython runtime failed its isolated version check")
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
            role="static_psi_prime_power_shard_producer",
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
        *upstream_files["primesieve"],
        *upstream_files["crlibm"],
        *boost_dependencies,
    ]
    source_rows = []
    for path in sorted(source_paths):
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
        "kind": "sparkinterval.psi-source-reviewed-closure.v1",
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
    shutil.rmtree(build_root)
    return records, build_steps, compiler


def _retained_tree(root: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256(b"sparkinterval/psi-retained-tree/v1\0")
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        relative_text = path.relative_to(root).as_posix()
        if relative_text == "export-manifest.json" or path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise PsiMaterializerError("retained export contains a linked or special file")
        pin = _file_pin(path)
        encoded = relative_text.encode("utf-8")
        count += 1
        total += pin["size_bytes"]
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(pin["size_bytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(pin["sha256"]))
    return count, total, digest.hexdigest()


def _validate_retained_export(
    archive: Path, *, phase: str, shard_index: int, tree_sha256: str
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix=".psi-export-audit-"))
    try:
        extract_archive(
            archive,
            temporary / "export",
            maximum_files=400_500,
            maximum_bytes=256 * 1024**3,
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
        }
        count, total, tree = _retained_tree(root)
        if (
            not isinstance(manifest, dict)
            or set(manifest) != fields
            or manifest["kind"] != "sparkinterval.azure.psi-retained-export.v1"
            or manifest["schema_version"] != 1
            or manifest["phase"] != phase
            or manifest["group_index"] != shard_index
            or manifest["file_count"] != count
            or manifest["total_bytes"] != total
            or manifest["tree_sha256"] != tree
            or tree != tree_sha256
        ):
            raise PsiMaterializerError("retained predecessor export failed tree replay")
    except (ArchiveError, CampaignIOError, OSError, ValueError) as error:
        if isinstance(error, PsiMaterializerError):
            raise
        raise PsiMaterializerError(f"cannot audit retained predecessor export: {error}") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _create_handoff(
    artifact_root: Path,
    factory: PsiCPUWorkloadFactory,
    predecessors: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    handoff_root = artifact_root / ".handoff"
    handoff_root.mkdir(mode=0o700)
    entries = []
    try:
        for order, row in enumerate(predecessors):
            _validate_retained_export(
                row["source_path"],
                phase=row["phase"],
                shard_index=row["shard_index"],
                tree_sha256=row["tree_sha256"],
            )
            relative = f"exports/{order:03d}-{row['shard_index']:09d}.tar"
            destination = handoff_root / relative
            _copy_exact(row["source_path"], destination)
            pin = _file_pin(destination)
            entries.append(
                {
                    "group_id": row["group_id"],
                    "path": relative,
                    "sha256": pin["sha256"],
                    "shard_index": row["shard_index"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        handoff = {
            "entries": entries,
            "group_index": factory.shard_index,
            "kind": "sparkinterval.azure.psi-phase-handoff.v1",
            "phase": factory.phase_id,
            "schema_version": 1,
        }
        _write_bytes(
            handoff_root / "handoff.json", cpu_operator.canonical_json_bytes(handoff)
        )
        destination = artifact_root / "input/psi-phase-handoff.tar"
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
    factory: PsiCPUWorkloadFactory,
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
        if expected != {**local, "result": "true", "target": "azure_sevsnp_cpu", "trust": "azure_sevsnp_confidential_compute"}:
            raise PsiMaterializerError("registered psi source identity changed")
        if (
            registered_invocation_backend(REGISTERED_INVOCATION) != cpu_operator.BACKEND
            or algorithm_hash != expected["algorithm_hash"]
            or input_hash != expected["input_hash"]
            or canonical_sha256(factory.parameters) != expected["parameters_hash"]
            or canonical_sha256(factory.domain) != expected["domain_hash"]
        ):
            raise PsiMaterializerError("terminal psi factory differs from the Lean invocation")
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
            "sha256": input_hash,
            "size_bytes": input_path.stat().st_size,
        },
        "job_id": f"tg-psi-{factory.phase_id}-{factory.shard_index:03d}-cpu-v1",
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": "output/registered-result.txt" if factory.terminal else "output/phase-result.json",
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
            "expected_iterations": 2,
            "format": "challenge_sha256_chain_json_v1",
            "path": "output/work-trace.json",
            "required": True,
            "trace_algorithm_definition": (
                "sparkinterval.challenge-work-trace.ch25-psi.v1\n"
                "initial=SHA256(phase-group-challenge-job-input)\n"
                "step-0=SHA256(previous-retained-archive-retained-tree)\n"
                "step-1=SHA256(previous-result)\n"
                "verification=closed-retained-export-and-final-campaign-replay"
            ),
            "trace_algorithm_sha256": hashlib.sha256(
                (
                    "sparkinterval.challenge-work-trace.ch25-psi.v1\n"
                    "initial=SHA256(phase-group-challenge-job-input)\n"
                    "step-0=SHA256(previous-retained-archive-retained-tree)\n"
                    "step-1=SHA256(previous-result)\n"
                    "verification=closed-retained-export-and-final-campaign-replay"
                ).encode("utf-8")
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
        raise PsiMaterializerError(
            "this host cannot build the x86_64 psi production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise PsiMaterializerError("reviewed psi factory disappeared")
    predecessors = _predecessor_rows(context, factory, site)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.psi-materializing-", dir=output_root.parent
        )
    )
    os.chmod(stage, 0o700)
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        records, build_steps, compiler = _build_runtime_closure(
            context, site, artifact_root
        )
        handoff_path, handoff = _create_handoff(
            artifact_root, factory, predecessors
        )
        job = _job(
            context, factory, artifact_root, records, handoff_path, site
        )
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        job_hash = record_hash(job_path)
        transcript_policy = _transcript_policy(
            site["base"], job_hash, job
        )
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise PsiMaterializerError("materializer output_root appeared during build")
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
                "source_reviewed_psi_operator_validated_materialization_not_execution_evidence"
            ),
            "compiler": compiler,
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
        OSError,
        ValueError,
    ) as error:
        raise PsiMaterializerError(f"psi materialization failed closed: {error}") from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)
