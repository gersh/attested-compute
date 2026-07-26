# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the six closed historical Goldbach Azure CPU phase types."""

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
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (
    CAMPAIGN_ID,
    SOURCE_PATHS,
    TRACE_DEFINITION,
    HistoricalGoldbachOperationalFactory,
    factory_for_portfolio_group,
)
from tg_verifier.azure_cpu_platt_head_materializer import (
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
from tg_verifier.goldbach_gpu_campaign import (
    verify_executable,
    verify_hardened_source_tree,
)
from tg_verifier.goldbach_build_admission import (
    GoldbachBuildAdmission,
    GoldbachBuildAdmissionError,
    load_build_admission,
    verify_admitted_file,
    verify_admitted_pin,
)
from tg_verifier.prop1224_upstreams import (
    Prop1224UpstreamError,
    verify_source,
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
    load_key_manifest,
    load_verified_receipt,
)
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, canonical_sha256, validate_job_spec  # noqa: E402
from tg_goldbach_historical_operational_azure_measured_workload import (  # noqa: E402
    HANDOFF_KIND,
    H100_PHASE,
    _validate_cpu_result,
    _validate_h100_result,
    verify_retained_export_archive,
)


SCHEMA_VERSION = 1
SITE_KIND = (
    "sparkinterval.azure.cpu."
    "helfgott-platt-goldbach-operational-materializer-site.v1"
)
MANIFEST_KIND = (
    "sparkinterval.azure.cpu."
    "helfgott-platt-goldbach-operational-materialization.v1"
)
SITE_FIELDS = {"base_site", "historical_goldbach_operational", "kind", "schema_version"}
INPUT_FIELDS = {
    "build_admission",
    "gmp_source_root",
    "goldbach_executable",
    "hardened_goldbach_source_root",
    "predecessor_exports",
}
PREDECESSOR_FIELDS = {"export", "group_id", "shard_index"}
FIXED_TOOL_PATH = "/usr/bin:/bin:/usr/local/bin"
REQUIRED_BUILD_TOOLS = (
    "ar", "g++", "gcc", "make", "python3", "ranlib", "strip",
)
BUILD_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": FIXED_TOOL_PATH,
    "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC",
}


class HistoricalGoldbachOperationalMaterializerError(RuntimeError):
    """A phase handoff, source build, or measured package failed closed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise HistoricalGoldbachOperationalMaterializerError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise HistoricalGoldbachOperationalMaterializerError(
            f"{what} must be a non-symlink directory"
        )
    return path


def _gmp_identity(root: Path) -> dict[str, Any]:
    try:
        return verify_source(root, "gmp")
    except (OSError, Prop1224UpstreamError, ValueError) as error:
        raise HistoricalGoldbachOperationalMaterializerError(
            f"pinned GMP source failed review: {error}"
        ) from error


def load_site(
    path: Path, *, allow_test_admission: bool = False,
) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise HistoricalGoldbachOperationalMaterializerError(
            f"cannot load canonical historical Goldbach materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "historical Goldbach materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise HistoricalGoldbachOperationalMaterializerError(
            "unsupported historical Goldbach materializer site kind/version"
        )
    _base_pin, base_path = _pin(site["base_site"], "base CPU materializer site")
    try:
        base = load_base_site(base_path)
    except CommonMaterializerError as error:
        raise HistoricalGoldbachOperationalMaterializerError(str(error)) from error
    inputs = _exact(site["historical_goldbach_operational"], INPUT_FIELDS, "historical Goldbach inputs")
    if (
        isinstance(inputs["build_admission"], Mapping)
        and inputs["build_admission"].get("status") == "unconfigured"
    ):
        raise HistoricalGoldbachOperationalMaterializerError(
            "Goldbach production build admission is explicitly unconfigured"
        )
    admission_pin, admission_path = _pin(
        inputs["build_admission"], "Goldbach build admission"
    )
    try:
        admission = load_build_admission(
            admission_path,
            expected_sha256=admission_pin["sha256"],
            allow_test_fixture=allow_test_admission,
        )
    except GoldbachBuildAdmissionError as error:
        raise HistoricalGoldbachOperationalMaterializerError(str(error)) from error
    gmp = _directory(inputs["gmp_source_root"], "GMP source root")
    source = _directory(
        inputs["hardened_goldbach_source_root"], "hardened Goldbach source root"
    )
    _gmp_identity(gmp)
    if (
        verify_hardened_source_tree(source)
        != admission.core["source_identity_sha256"]
    ):
        raise HistoricalGoldbachOperationalMaterializerError(
            "hardened source differs from the build admission"
        )
    executable_pin, executable = _pin(
        inputs["goldbach_executable"], "GoldbachGPU executable"
    )
    if not os.access(executable, os.X_OK):
        raise HistoricalGoldbachOperationalMaterializerError(
            "GoldbachGPU executable pin is not executable"
        )
    verify_executable(executable, executable_pin["sha256"])
    try:
        verify_admitted_pin(
            admission, "executable", inputs["goldbach_executable"]
        )
        verify_admitted_file(admission, "executable", executable)
    except GoldbachBuildAdmissionError as error:
        raise HistoricalGoldbachOperationalMaterializerError(str(error)) from error
    rows = inputs["predecessor_exports"]
    if not isinstance(rows, list) or len(rows) > 8_193:
        raise HistoricalGoldbachOperationalMaterializerError(
            "predecessor_exports is not a bounded array"
        )
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(rows):
        row = _exact(raw, PREDECESSOR_FIELDS, f"predecessor export {index}")
        if not isinstance(row["group_id"], str) or not row["group_id"]:
            raise HistoricalGoldbachOperationalMaterializerError("predecessor group_id is malformed")
        shard = row["shard_index"]
        if isinstance(shard, bool) or not isinstance(shard, int) or shard < 0:
            raise HistoricalGoldbachOperationalMaterializerError(
                "predecessor shard_index is malformed"
            )
        identity = (row["group_id"], shard)
        if identity in seen:
            raise HistoricalGoldbachOperationalMaterializerError(
                "duplicate predecessor export identity"
            )
        seen.add(identity)
        _pin(row["export"], f"predecessor export {index}")
    return {
        "admission_path": admission_path,
        "base": base,
        "build_admission": admission,
        "historical_goldbach_operational": inputs,
        "site_pin": _file_pin(path),
    }


def _expected_predecessors(
    factory: HistoricalGoldbachOperationalFactory,
) -> tuple[tuple[str, int], ...]:
    group = lambda phase: f"{CAMPAIGN_ID}::{phase}"
    phase = factory.phase_id
    if phase in ("create-production-plan", "initialize-prime-ladder"):
        return ()
    if phase == "native-prime-ladder-range-groups":
        return ((group("initialize-prime-ladder"), 0),)
    if phase == "aggregate":
        return (
            (group("create-production-plan"), 0),
            *((group(H100_PHASE), index) for index in range(8_192)),
        )
    if phase == "binary-semantic-replay":
        return ((group("aggregate"), 0),)
    if phase == "reduce-prime-ladder-ranges":
        return tuple(
            (group("native-prime-ladder-range-groups"), index)
            for index in range(320)
        )
    raise HistoricalGoldbachOperationalMaterializerError(
        "unknown historical Goldbach operational phase"
    )


def _predecessor_rows(
    context: azure_portfolio.PortfolioContext,
    factory: HistoricalGoldbachOperationalFactory,
    site: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _expected_predecessors(factory)
    provided = {
        (row["group_id"], row["shard_index"]): row
        for row in site["historical_goldbach_operational"]["predecessor_exports"]
    }
    if set(provided) != set(expected):
        raise HistoricalGoldbachOperationalMaterializerError(
            "predecessor exports do not exactly cover the reviewed phase"
        )
    state = azure_portfolio.load_state(context)
    rows: list[dict[str, Any]] = []
    for group_id, shard_index in expected:
        group = azure_portfolio._group(context, group_id)
        paths = azure_portfolio._task_paths(context, group_id, shard_index)
        task_id = paths["task_id"].name
        record = state["records"].get(task_id)
        if record is None:
            raise HistoricalGoldbachOperationalMaterializerError(
                "predecessor has no portfolio receipt"
            )
        azure_portfolio._validate_task_record(context, task_id, record)
        if record["stage"] != "verified_receipt_recorded":
            raise HistoricalGoldbachOperationalMaterializerError(
                "predecessor portfolio receipt is incomplete"
            )
        try:
            receipt = load_verified_receipt(
                paths["receipt"], key_manifest=context.verifier_key_manifest
            )
        except Exception as error:
            raise HistoricalGoldbachOperationalMaterializerError(
                f"predecessor receipt failed verification: {error}"
            ) from error
        export_pin, export_path = _pin(
            provided[(group_id, shard_index)]["export"],
            f"retained predecessor {group_id}/{shard_index}",
        )
        phase = group["phase_id"]
        if phase == H100_PHASE:
            _validate_h100_result(
                receipt, shard_index, site["build_admission"]
            )
            manifest = verify_retained_export_archive(
                export_path, H100_PHASE, shard_index
            )
        else:
            predecessor_factory = factory_for_portfolio_group(group, shard_index)
            if predecessor_factory is None or predecessor_factory.terminal:
                raise HistoricalGoldbachOperationalMaterializerError(
                    "predecessor is not a reviewed operational CPU phase"
                )
            result = _validate_cpu_result(
                receipt, phase, shard_index, export_path
            )
            manifest = verify_retained_export_archive(
                export_path, phase, shard_index
            )
            if result["retained_tree_sha256"] != manifest["tree_sha256"]:
                raise HistoricalGoldbachOperationalMaterializerError(
                    "predecessor export tree differs from its signed result"
                )
        rows.append(
            {
                "export": export_pin,
                "export_source": export_path,
                "group_id": group_id,
                "phase": phase,
                "receipt_path": paths["receipt"],
                "receipt_sha256": receipt["receipt_sha256"],
                "shard_index": shard_index,
                "tree_sha256": manifest["tree_sha256"],
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
        raise HistoricalGoldbachOperationalMaterializerError(
            "portfolio group has no closed historical Goldbach CPU factory"
        )
    if shard.get("argv") != list(factory.portfolio_argv):
        raise HistoricalGoldbachOperationalMaterializerError(
            "portfolio shard argv differs from the closed factory"
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
        raise HistoricalGoldbachOperationalMaterializerError(
            "challenge TTL cannot contain the phase and evidence margin"
        )
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    try:
        output_root.relative_to(context.repository_root)
    except ValueError:
        pass
    else:
        raise HistoricalGoldbachOperationalMaterializerError(
            "materializer output_root must stay outside the repository"
        )
    tools = {name: shutil.which(name, path=FIXED_TOOL_PATH) for name in REQUIRED_BUILD_TOOLS}
    supported = platform.machine() == "x86_64" and all(tools.values())
    return {
        "accepted": False,
        "build_host_architecture": platform.machine(),
        "build_host_supported": supported,
        "challenge": {**_file_pin(challenge_path), "nonce": challenge["nonce"]},
        "classification": "reviewed_historical_goldbach_operational_materialization_plan_not_execution_evidence",
        "build_admission_sha256": site[
            "build_admission"
        ].admission_sha256,
        "build_identity_sha256": site[
            "build_admission"
        ].build_identity_sha256,
        "factory_id": factory.factory_id,
        "group_id": group_id,
        "output_root": str(output_root),
        "phase_id": factory.phase_id,
        "predecessor_count": len(predecessors),
        "registered_invocation": factory.registered_invocation,
        "semantic_terminal": False,
        "shard_config": {**_file_pin(shard_path), "task_id": shard["task_id"]},
        "shard_index": shard_index,
        "tools_if_supported": tools,
        "upstreams": {
            "gmp": _gmp_identity(Path(site["historical_goldbach_operational"]["gmp_source_root"])),
            "goldbach_source_identity_sha256": verify_hardened_source_tree(
                Path(site["historical_goldbach_operational"]["hardened_goldbach_source_root"])
            ),
            "goldbach_executable": site["historical_goldbach_operational"]["goldbach_executable"],
        },
    }


def _copy_source_tree(source: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700, parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise HistoricalGoldbachOperationalMaterializerError("GMP source contains a symlink")
        if path.is_dir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        elif path.is_file():
            _copy_exact(path, target, executable=os.access(path, os.X_OK))
        else:
            raise HistoricalGoldbachOperationalMaterializerError(
                "GMP source contains a special file"
            )


def _run_build(
    argv: list[str], *, cwd: Path, additions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = {**BUILD_ENVIRONMENT, **({} if additions is None else additions)}
    try:
        completed = subprocess.run(
            argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HistoricalGoldbachOperationalMaterializerError(
            f"closed GMP/ladder build failed: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout)[-4000:].decode(
            "utf-8", "replace"
        )
        raise HistoricalGoldbachOperationalMaterializerError(
            f"closed GMP/ladder build exited {completed.returncode}: {diagnostic}"
        )
    return {
        "argv": argv,
        "argv_sha256": canonical_sha256(argv),
        "environment": {} if additions is None else dict(additions),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _copy_key_closure(
    context: azure_portfolio.PortfolioContext, artifact_root: Path,
) -> list[dict[str, Any]]:
    manifest_source = context.verifier_key_manifest.resolve(strict=True)
    keys = load_key_manifest(manifest_source)
    destination_root = artifact_root / "profiles/verifier-keys"
    destination = destination_root / "trusted_compute_keys.json"
    _copy_exact(manifest_source, destination)
    records = [
        _artifact_record(
            destination, artifact_root, role="predecessor_verifier_key_manifest",
            statement_role=None, executable=False,
        )
    ]
    for entry in keys.values():
        relative = Path(entry["public_key_path"])
        source = (manifest_source.parent / relative).resolve(strict=True)
        try:
            source.relative_to(manifest_source.parent.resolve(strict=True))
        except ValueError as error:
            raise HistoricalGoldbachOperationalMaterializerError(
                "verifier public key escapes its manifest"
            ) from error
        target = destination_root / relative
        _copy_exact(source, target)
        if _file_pin(target)["sha256"] != entry["public_key_sha256"]:
            raise HistoricalGoldbachOperationalMaterializerError(
                "copied verifier public key differs"
            )
        records.append(
            _artifact_record(
                target, artifact_root, role="predecessor_verifier_public_key",
                statement_role=None, executable=False,
            )
        )
    return records


def _build_runtime_closure(
    context: azure_portfolio.PortfolioContext,
    site: Mapping[str, Any],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    admission: GoldbachBuildAdmission = site["build_admission"]
    if platform.machine() != "x86_64":
        raise HistoricalGoldbachOperationalMaterializerError(
            "historical Goldbach production package must be built on x86_64"
        )
    tools: dict[str, Path] = {}
    for name in REQUIRED_BUILD_TOOLS:
        found = shutil.which(name, path=FIXED_TOOL_PATH)
        if found is None:
            raise HistoricalGoldbachOperationalMaterializerError(f"closed build requires {name}")
        tools[name] = Path(found).resolve(strict=True)

    copied: dict[str, Path] = {}
    for relative in SOURCE_PATHS:
        row, source = _source_pin(context, relative)
        destination = artifact_root / relative
        _copy_exact(source, destination, executable=relative.startswith("tools/"))
        if hash_file_once(destination) != (row["sha256"], row["size_bytes"]):
            raise HistoricalGoldbachOperationalMaterializerError(
                f"project source changed during copy: {relative}"
            )
        copied[relative] = destination

    inputs = site["historical_goldbach_operational"]
    hardened_source = Path(inputs["hardened_goldbach_source_root"]).resolve(strict=True)
    source_identity = verify_hardened_source_tree(hardened_source)
    if source_identity != admission.core["source_identity_sha256"]:
        raise HistoricalGoldbachOperationalMaterializerError(
            "CPU package source differs from the build admission"
        )
    hardened_copy = artifact_root / "source/goldbach-gpu-hardened"
    _copy_source_tree(hardened_source, hardened_copy)
    if verify_hardened_source_tree(hardened_copy) != source_identity:
        raise HistoricalGoldbachOperationalMaterializerError("copied hardened source differs")

    artifacts = artifact_root / "artifacts"
    artifacts.mkdir(mode=0o700, parents=True)
    python_target = artifacts / "python3"
    _copy_exact(tools["python3"], python_target, executable=True)
    executable_pin, executable_source = _pin(
        inputs["goldbach_executable"], "GoldbachGPU executable"
    )
    goldbach_executable = artifacts / "goldbach-gpu"
    _copy_exact(executable_source, goldbach_executable, executable=True)
    verify_executable(
        goldbach_executable, admission.core["executable"]["sha256"]
    )
    verify_admitted_file(admission, "executable", goldbach_executable)
    admission_target = artifact_root / "source/goldbach-build-admission.json"
    _copy_exact(site["admission_path"], admission_target)
    if hash_file_once(admission_target) != (
        admission.admission_sha256,
        admission.admission_size_bytes,
    ):
        raise HistoricalGoldbachOperationalMaterializerError(
            "copied Goldbach build admission differs"
        )

    gmp_source = Path(inputs["gmp_source_root"]).resolve(strict=True)
    gmp_identity = _gmp_identity(gmp_source)
    build_root = artifact_root / ".build"
    gmp_copy = build_root / "gmp-source"
    gmp_build = build_root / "gmp-build"
    install_root = build_root / "install"
    _copy_source_tree(gmp_source, gmp_copy)
    if _gmp_identity(gmp_copy) != gmp_identity:
        raise HistoricalGoldbachOperationalMaterializerError("copied GMP source differs")
    gmp_build.mkdir(mode=0o700, parents=True)
    flags = (
        "-O3 -march=x86-64-v2 -mtune=generic -ffile-prefix-map=/=. "
        "-fdebug-prefix-map=/=."
    )
    additions = {
        "AR": str(tools["ar"]), "CC": str(tools["gcc"]), "CFLAGS": flags,
        "CXX": str(tools["g++"]), "CXXFLAGS": f"{flags} -std=c++20",
        "RANLIB": str(tools["ranlib"]),
    }
    build_steps = [
        _run_build(
            [
                str(gmp_copy / "configure"), "--build=x86_64-pc-linux-gnu",
                "--host=x86_64-pc-linux-gnu", f"--prefix={install_root}",
                "--disable-shared", "--enable-static", "--enable-fat",
            ],
            cwd=gmp_build,
            additions=additions,
        ),
        _run_build([str(tools["make"]), "-j8"], cwd=gmp_build, additions=additions),
        _run_build([str(tools["make"]), "install"], cwd=gmp_build, additions=additions),
    ]
    native_source = copied["reference/tg_goldbach_ladder_native.cpp"]
    native_source_hash = hash_file_once(native_source)[0]
    ladder_runner = artifacts / "tg_goldbach_ladder_native"
    compile_argv = [
        str(tools["g++"]), "-O3", "-std=c++20", "-march=x86-64-v2",
        "-mtune=generic", "-ffile-prefix-map=/=.", "-fdebug-prefix-map=/=.",
        "-Wall", "-Wextra", "-Werror", "-static", "-Wl,--build-id=none",
        "-I", str(install_root / "include"),
        f'-DSPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256="{native_source_hash}"',
        str(native_source), str(install_root / "lib/libgmp.a"), "-o",
        str(ladder_runner),
    ]
    build_steps.append(_run_build(compile_argv, cwd=artifact_root))
    build_steps.append(
        _run_build(
            [str(tools["strip"]), "--strip-all", str(ladder_runner)],
            cwd=artifact_root,
        )
    )
    ladder_runner.chmod(0o500)
    _require_x86_64_static_elf(ladder_runner)

    gmp_archive = artifact_root / "source/upstreams/gmp-6.3.0.tar"
    create_archive(gmp_copy, gmp_archive)
    shutil.rmtree(build_root)
    key_records = _copy_key_closure(context, artifact_root)

    runtime = {
        "dynamic_runtime_boundary": (
            "copied CPython plus immutable Azure image loader, libc, stdlib, and openssl"
        ),
        "gmp": gmp_identity,
        "goldbach_executable": {
            **_file_pin(goldbach_executable), "path": "artifacts/goldbach-gpu",
            "executed_by_cpu_phase": False,
        },
        "goldbach_source_identity_sha256": source_identity,
        "goldbach_build_admission_sha256": admission.admission_sha256,
        "goldbach_build_identity_sha256": admission.build_identity_sha256,
        "kind": "sparkinterval.historical_goldbach_operational.image-runtime-closure.v1",
        "ladder_runner": {
            **_file_pin(ladder_runner),
            "path": "artifacts/tg_goldbach_ladder_native",
        },
        "python_executable": {**_file_pin(python_target), "path": "artifacts/python3"},
        "schema_version": 1,
    }
    version = subprocess.run(
        [str(python_target), "-I", "--version"], env=BUILD_ENVIRONMENT,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=30,
    )
    version_raw = version.stdout or version.stderr
    if version.returncode != 0 or not version_raw.startswith(b"Python 3."):
        raise HistoricalGoldbachOperationalMaterializerError(
            "copied CPython runtime failed isolated version check"
        )
    runtime["python_version"] = version_raw.decode("ascii", "strict").strip()
    runtime_path = artifact_root / "source/runtime-closure.json"
    _write_bytes(runtime_path, cpu_operator.canonical_json_bytes(runtime))

    records = [
        _artifact_record(
            python_target, artifact_root, role="image_bound_cpython_host",
            statement_role="host_executable", executable=True,
        ),
        _artifact_record(
            ladder_runner, artifact_root, role="static_gmp_n45_ladder_producer",
            statement_role="producer_executable", executable=True,
        ),
        _artifact_record(
            goldbach_executable, artifact_root,
            role="h100_executable_identity_data_not_cpu_executed",
            statement_role=None, executable=True,
        ),
        _artifact_record(
            gmp_archive, artifact_root, role="reviewed_gmp_full_source_archive",
            statement_role=None, executable=False,
        ),
        _artifact_record(
            runtime_path, artifact_root, role="image_runtime_closure_manifest",
            statement_role=None, executable=False,
        ),
        _artifact_record(
            admission_target,
            artifact_root,
            role="reviewed_goldbach_build_admission",
            statement_role=None,
            executable=False,
        ),
        *key_records,
    ]
    for relative, path in sorted(copied.items()):
        records.append(
            _artifact_record(
                path, artifact_root, role="reviewed_project_source",
                statement_role=None, executable=relative.startswith("tools/"),
            )
        )
    for path in sorted(item for item in hardened_copy.rglob("*") if item.is_file()):
        records.append(
            _artifact_record(
                path, artifact_root, role="reviewed_hardened_goldbach_source",
                statement_role=None, executable=False,
            )
        )
    source_manifest = {
        "gmp_archive": {
            **_file_pin(gmp_archive),
            "path": gmp_archive.relative_to(artifact_root).as_posix(),
            "tree_sha256": gmp_identity["tree_sha256"],
        },
        "goldbach_source_identity_sha256": source_identity,
        "goldbach_build_admission_sha256": admission.admission_sha256,
        "goldbach_build_identity_sha256": admission.build_identity_sha256,
        "kind": "sparkinterval.historical_goldbach_operational-source-reviewed-closure.v1",
        "project_files": [
            {
                "path": relative,
                "sha256": _file_pin(path)["sha256"],
                "size_bytes": path.stat().st_size,
            }
            for relative, path in sorted(copied.items())
        ],
        "schema_version": 1,
    }
    source_manifest_path = artifact_root / "source/source-closure.json"
    _write_bytes(
        source_manifest_path, cpu_operator.canonical_json_bytes(source_manifest)
    )
    records.append(
        _artifact_record(
            source_manifest_path, artifact_root,
            role="reviewed_source_closure_manifest", statement_role="source_tree",
            executable=False,
        )
    )
    records.sort(key=lambda row: row["path"])
    compiler = {
        **_file_pin(tools["g++"]),
        "version_line": subprocess.run(
            [str(tools["g++"]), "--version"], check=True, capture_output=True,
            text=True, timeout=30,
        ).stdout.splitlines()[0],
    }
    return records, build_steps, compiler


def _create_handoff(
    artifact_root: Path,
    factory: HistoricalGoldbachOperationalFactory,
    predecessors: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    root = artifact_root / ".handoff"
    root.mkdir(mode=0o700)
    entries: list[dict[str, Any]] = []
    try:
        for order, row in enumerate(predecessors):
            export_relative = f"exports/{order:05d}-{row['shard_index']:09d}.tar"
            receipt_relative = f"receipts/{order:05d}-{row['shard_index']:09d}.json"
            export_target = root / export_relative
            receipt_target = root / receipt_relative
            _copy_exact(row["export_source"], export_target)
            _copy_exact(row["receipt_path"], receipt_target)
            export_pin = _file_pin(export_target)
            receipt_pin = _file_pin(receipt_target)
            entries.append(
                {
                    "export_path": export_relative,
                    "export_sha256": export_pin["sha256"],
                    "export_size_bytes": export_pin["size_bytes"],
                    "group_id": row["group_id"],
                    "phase": row["phase"],
                    "receipt_file_sha256": receipt_pin["sha256"],
                    "receipt_file_size_bytes": receipt_pin["size_bytes"],
                    "receipt_path": receipt_relative,
                    "receipt_sha256": row["receipt_sha256"],
                    "shard_index": row["shard_index"],
                }
            )
        handoff = {
            "entries": entries,
            "group_index": factory.shard_index,
            "kind": HANDOFF_KIND,
            "phase": factory.phase_id,
            "schema_version": 1,
        }
        _write_bytes(root / "handoff.json", cpu_operator.canonical_json_bytes(handoff))
        destination = (
            artifact_root
            / "input/historical-goldbach-operational-phase-handoff.tar"
        )
        create_archive(root, destination)
        return destination, handoff
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _job(
    context: azure_portfolio.PortfolioContext,
    factory: HistoricalGoldbachOperationalFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
    handoff_path: Path,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    if factory.terminal or factory.registered_invocation is not None:
        raise HistoricalGoldbachOperationalMaterializerError(
            "operational materializer cannot produce a terminal job"
        )
    input_path = handoff_path
    profiles, runner_policy = _profile_and_policy_records(context, artifact_root, site)
    algorithm_hash = hashlib.sha256(
        factory.algorithm_definition.encode("utf-8")
    ).hexdigest()
    input_hash = record_hash(input_path)
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
        "job_id": (
            "tg-historical-goldbach-operational-"
            f"{factory.phase_id}-{factory.shard_index:04d}-cpu-v1"
        ),
        "kind": "sparkinterval_measured_job",
        "output_contract": {
            "expected_output_count": 1,
            "format": factory.output_format,
            "maximum_bytes": factory.output_maximum_bytes,
            "path": "output/phase-result.json",
        },
        "parameters": {
            "canonical_sha256": canonical_sha256(factory.parameters),
            "value": factory.parameters,
        },
        "runner_policy": runner_policy,
        "schema_version": 1,
        "target_profile": profiles["target"],
        "tpm_policy": {
            "ak_handle": "0x81000003", "bank": "sha256", "pcr_index": 23,
            "pcr_selection": "sha256:0,1,2,3,4,5,6,7,23",
        },
        "trust_profile": profiles["trust"],
        "work_trace_contract": {
            "expected_iterations": 2,
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


def materialize(
    context: azure_portfolio.PortfolioContext,
    group_id: str,
    shard_index: int,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    plan = plan_materialization(context, group_id, shard_index, site)
    if not plan["build_host_supported"]:
        raise HistoricalGoldbachOperationalMaterializerError(
            "this host cannot build the x86_64 historical Goldbach production closure"
        )
    group, _shard, challenge, shard_path, challenge_path = _load_handoff(
        context, group_id, shard_index
    )
    factory = factory_for_portfolio_group(group, shard_index)
    if factory is None:
        raise HistoricalGoldbachOperationalMaterializerError("reviewed factory disappeared")
    predecessors = _predecessor_rows(context, factory, site)
    output_root = _absolute(
        site["base"]["output_root"], "materializer output_root", exists=False
    )
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.historical_goldbach_operational-materializing-",
            dir=output_root.parent,
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
        job = _job(context, factory, artifact_root, records, handoff_path, site)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, cpu_operator.canonical_json_bytes(job))
        job_hash = record_hash(job_path)
        transcript_policy = _transcript_policy(site["base"], job_hash, job)
        transcript_path = stage / "policies/transcript-appraisal.json"
        _write_bytes(
            transcript_path, cpu_operator.canonical_json_bytes(transcript_policy)
        )
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        if output_root.exists() or output_root.is_symlink():
            raise HistoricalGoldbachOperationalMaterializerError(
                "materializer output_root appeared during build"
            )
        os.replace(stage, output_root)
        published = True

        artifact_root = output_root / "artifact-root"
        job_path = artifact_root / "job.json"
        transcript_path = output_root / "policies/transcript-appraisal.json"
        package = output_root / "workload.tar"
        config = _operator_config(
            site=site["base"], factory=factory, challenge=challenge,
            challenge_path=challenge_path, artifact_root=artifact_root,
            package=package, transcript_policy_path=transcript_path,
        )
        config_path = output_root / "cpu-campaign.json"
        _write_bytes(config_path, cpu_operator.canonical_json_bytes(config))
        _validated, config_hash = cpu_operator.load_config(config_path)
        manifest = {
            "accepted": False,
            "build_admission_sha256": site[
                "build_admission"
            ].admission_sha256,
            "build_identity_sha256": site[
                "build_admission"
            ].build_identity_sha256,
            "build_steps": build_steps,
            "challenge_pin": _file_pin(challenge_path),
            "classification": (
                "source_reviewed_historical_goldbach_operational_operator_validated_materialization_not_execution_evidence"
            ),
            "compiler": compiler,
            "cpu_operator_config": {**_file_pin(config_path), "sha256": config_hash},
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "handoff": {
                "entry_count": len(handoff["entries"]),
                "sha256": _file_pin(
                    artifact_root
                    / "input/historical-goldbach-operational-phase-handoff.tar"
                )["sha256"],
            },
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
            "semantic_terminal": False,
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
                **manifest["cpu_operator_config"], "path": str(config_path),
            },
            "job_spec": {**manifest["job_spec"], "path": str(job_path)},
            "manifest": str(manifest_path),
            "package": {**manifest["package"], "path": str(package)},
        }
    except (
        ArchiveError, CampaignIOError, CommonMaterializerError, OSError, ValueError,
    ) as error:
        raise HistoricalGoldbachOperationalMaterializerError(
            f"historical Goldbach materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "HistoricalGoldbachOperationalMaterializerError", "load_site", "materialize",
    "plan_materialization",
]
