# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize one nonterminal TGDBSPK1 Dirichlet H100 measured job.

The materializer accepts no caller command.  It packages the exact operational
factory, a production-authenticated input manifest, the reviewed CUDA runner
and source, and the complete plan/batch/control/pinset closure.  It does not
create a Lean candidate or enable any analytic source binding.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping

from tg_verifier.azure_cpu_dirichlet_workload_factory import (
    PACKED_BATCH_DIRECTORY,
    PACKED_CONTROL_PATH,
    PACKED_CONTROL_RECEIPT_PATH,
    PACKED_DEVICE_LOCATION,
    PACKED_PINSET_PATH,
    PACKED_PLAN_PATH,
    PACKED_PREDECESSOR_RECEIPT_PATH,
    PACKED_RUNNER_PATH,
    PACKED_RUNNER_SOURCE_PATH,
    PACKED_SOURCE_PATHS,
    DirichletPackedOperationalWorkloadFactory,
    make_packed_phase_factory,
)
from tg_verifier.azure_cpu_portfolio_materializer import (
    _absolute,
    _artifact_record,
    _copy_exact,
    _file_pin,
    _pin,
    _write_bytes,
)
from tg_verifier.campaign_io import CampaignIOError, canonical_json_bytes, load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (
    REPOSITORY_ROOT / "attestation",
    REPOSITORY_ROOT / "tools",
):
    if str(directory) not in os.sys.path:
        os.sys.path.insert(0, str(directory))

import h100_production_orchestrator as h100_operator  # noqa: E402
from create_run_bundle import canonical_sha256, load_profile  # noqa: E402
from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from measured_runner import _closure_manifest, validate_job_spec  # noqa: E402


SCHEMA_VERSION = 1
SITE_KIND = "sparkinterval.azure.h100.dirichlet-packed-materializer-site.v1"
MANIFEST_KIND = (
    "sparkinterval.azure.h100.dirichlet-packed-materialization.v1"
)
SITE_FIELDS = {
    "batch_directory",
    "control",
    "control_receipt",
    "gpu_verifier",
    "input_manifest",
    "kind",
    "nras_url",
    "nvidia_policy",
    "output_root",
    "pinset",
    "plan",
    "predecessor_receipt",
    "python",
    "runner",
    "runner_policy",
    "runner_source",
    "schema_version",
}
PIN_FIELDS = {"path", "sha256", "size_bytes"}
POLICY_FIELDS = {
    "classification",
    "path",
    "policy_id",
    "sha256",
    "size_bytes",
}
H100_PROFILE_PATHS = {
    "target": "profiles/targets/azure_ncc40ads_h100_v5.json",
    "trust": "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json",
}
SOURCE_CLOSURE_KIND = (
    "sparkinterval.dirichlet-smallq-packed-source-closure.v1"
)


class DirichletPackedMaterializerError(RuntimeError):
    """A site pin, signed input closure, or package job failed closed."""


def _workload_module():
    name = "sparkinterval_dirichlet_packed_materializer_workload"
    loaded = os.sys.modules.get(name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(
        name,
        REPOSITORY_ROOT / "tools/tg_dirichlet_azure_measured_workload.py",
    )
    if spec is None or spec.loader is None:
        raise DirichletPackedMaterializerError(
            "cannot load the reviewed Dirichlet measured workload"
        )
    module = importlib.util.module_from_spec(spec)
    os.sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exact(value: Any, fields: set[str], what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise DirichletPackedMaterializerError(
            f"{what} fields differ "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def _directory(value: Any, what: str) -> Path:
    path = _absolute(value, what, exists=True)
    if Path(value).is_symlink() or not path.is_dir():
        raise DirichletPackedMaterializerError(
            f"{what} must be a nonsymbolic directory"
        )
    return path


def _site_pin(value: Any, what: str, *, executable: bool = False) -> Path:
    _exact(value, PIN_FIELDS, what)
    _unused, path = _pin(value, what)
    if executable and not os.access(path, os.X_OK):
        raise DirichletPackedMaterializerError(f"{what} is not executable")
    return path


def _packed_args(site: Mapping[str, Any], *, copied_root: Path | None = None):
    if copied_root is None:
        return SimpleNamespace(
            batch_directory=Path(site["batch_directory"]),
            control=Path(site["control"]["path"]),
            control_receipt=Path(site["control_receipt"]["path"]),
            input=Path(site["input_manifest"]["path"]),
            pinset=Path(site["pinset"]["path"]),
            plan=Path(site["plan"]["path"]),
            predecessor_receipt=Path(site["predecessor_receipt"]["path"]),
            runner=Path(site["runner"]["path"]),
            runner_source=Path(site["runner_source"]["path"]),
        )
    return SimpleNamespace(
        batch_directory=copied_root / PACKED_BATCH_DIRECTORY,
        control=copied_root / PACKED_CONTROL_PATH,
        control_receipt=copied_root / PACKED_CONTROL_RECEIPT_PATH,
        input=copied_root / "input/packed-input-manifest.json",
        pinset=copied_root / PACKED_PINSET_PATH,
        plan=copied_root / PACKED_PLAN_PATH,
        predecessor_receipt=(
            copied_root / PACKED_PREDECESSOR_RECEIPT_PATH
        ),
        runner=copied_root / PACKED_RUNNER_PATH,
        runner_source=copied_root / PACKED_RUNNER_SOURCE_PATH,
    )


def load_site(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise DirichletPackedMaterializerError(
            f"cannot load canonical packed materializer site: {error}"
        ) from error
    site = _exact(value, SITE_FIELDS, "packed materializer site")
    if site["kind"] != SITE_KIND or site["schema_version"] != SCHEMA_VERSION:
        raise DirichletPackedMaterializerError(
            "unsupported packed materializer site kind/version"
        )
    for field in (
        "control",
        "control_receipt",
        "input_manifest",
        "pinset",
        "plan",
        "predecessor_receipt",
        "runner_source",
    ):
        _site_pin(site[field], f"packed site {field}")
    _site_pin(site["python"], "packed site python", executable=True)
    _site_pin(site["runner"], "packed site runner", executable=True)
    policy = _exact(
        site["runner_policy"], POLICY_FIELDS, "packed runner policy"
    )
    _pin(policy, "packed runner policy", policy=True)
    if policy["classification"] != "production":
        raise DirichletPackedMaterializerError(
            "packed runner policy is not production-classified"
        )
    _site_pin(site["nvidia_policy"], "packed NVIDIA policy")
    batch_directory = _directory(
        site["batch_directory"], "packed batch directory"
    )
    output_root = _absolute(
        site["output_root"], "packed output_root", exists=False
    )
    try:
        output_root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise DirichletPackedMaterializerError(
            "packed output_root must stay outside the repository"
        )
    if (
        not isinstance(site["gpu_verifier"], str)
        or not site["gpu_verifier"]
        or not isinstance(site["nras_url"], str)
        or not site["nras_url"].startswith("https://")
    ):
        raise DirichletPackedMaterializerError(
            "packed H100 verifier or NRAS endpoint is malformed"
        )
    reviewed_source_pin = _file_pin(
        REPOSITORY_ROOT
        / "gpu/platform/h100/h100_tg_dirichlet_booker_smallq_certified.cu"
    )
    if (
        site["runner_source"]["sha256"] != reviewed_source_pin["sha256"]
        or site["runner_source"]["size_bytes"]
        != reviewed_source_pin["size_bytes"]
    ):
        raise DirichletPackedMaterializerError(
            "packed runner source differs from the reviewed repository source"
        )
    checked_site = dict(site)
    checked_site["batch_directory"] = str(batch_directory)
    checked_site["output_root"] = str(output_root)
    try:
        inputs = _workload_module()._load_packed_inputs(
            _packed_args(checked_site)
        )
    except Exception as error:
        raise DirichletPackedMaterializerError(
            f"packed signed input closure failed validation: {error}"
        ) from error
    factory = make_packed_phase_factory(inputs["manifest"])
    return {
        "factory": factory,
        "inputs": inputs,
        "output_root": output_root,
        "site": checked_site,
        "site_pin": _file_pin(path),
    }


def plan_materialization(site: Mapping[str, Any]) -> dict[str, Any]:
    factory = site["factory"]
    inputs = site["inputs"]
    device_mode = (
        inputs["manifest"]["packing_location"] == PACKED_DEVICE_LOCATION
    )
    return {
        "accepted": False,
        "artifact_roster_sha256": inputs["artifact_roster_sha256"],
        "classification": (
            "reviewed_dirichlet_smallq_packed_h100_materialization_plan_"
            "not_execution_or_source_evidence"
        ),
        "device_side_classification_implemented": device_mode,
        "factory_id": factory.factory_id,
        "input_manifest_sha256": inputs["manifest_sha256"],
        "output_root": str(site["output_root"]),
        "packing_location": inputs["manifest"]["packing_location"],
        "packing_mode": inputs["manifest"]["packing_mode"],
        "pinset_sha256": inputs["manifest"]["pinset_sha256"],
        "predecessor_receipt_sha256": inputs["predecessor"][
            "receipt_sha256"
        ],
        "production_ready": False,
        "q": inputs["q"],
        "raw_disk_device_to_host_transfer_eliminated": device_mode,
        "registered_invocation": None,
        "source_admission_enabled": False,
        "workload_argv": list(factory.command_argv),
        "work_trace_verifier_argv": list(factory.trace_verifier_argv),
    }


def _copy_inputs(
    site: Mapping[str, Any], artifact_root: Path,
) -> list[Path]:
    pairs = (
        ("input_manifest", "input/packed-input-manifest.json", False),
        ("runner", PACKED_RUNNER_PATH, True),
        ("runner_source", PACKED_RUNNER_SOURCE_PATH, False),
        ("plan", PACKED_PLAN_PATH, False),
        ("control", PACKED_CONTROL_PATH, False),
        ("control_receipt", PACKED_CONTROL_RECEIPT_PATH, False),
        ("pinset", PACKED_PINSET_PATH, False),
        (
            "predecessor_receipt",
            PACKED_PREDECESSOR_RECEIPT_PATH,
            False,
        ),
        ("python", "artifacts/python3", True),
        ("nvidia_policy", "profiles/nvidia-gpu.rego", False),
    )
    copied: list[Path] = []
    for field, relative, executable in pairs:
        source = Path(site[field]["path"])
        target = artifact_root / relative
        _copy_exact(source, target, executable=executable)
        copied.append(target)
    batch_target = artifact_root / PACKED_BATCH_DIRECTORY
    batch_target.mkdir(mode=0o700, parents=True)
    for source in sorted(Path(site["batch_directory"]).iterdir()):
        target = batch_target / source.name
        _copy_exact(source, target)
        copied.append(target)
    return copied


def _copy_sources(artifact_root: Path) -> list[Path]:
    copied: list[Path] = []
    for relative in PACKED_SOURCE_PATHS:
        source = REPOSITORY_ROOT / relative
        target = artifact_root / relative
        # The runner source has a second manifest-facing copy under source/.
        _copy_exact(source, target, executable=False)
        copied.append(target)
    return copied


def _profiles(
    artifact_root: Path,
) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for kind, relative in H100_PROFILE_PATHS.items():
        source = REPOSITORY_ROOT / relative
        destination = artifact_root / f"profiles/{kind}.json"
        _copy_exact(source, destination)
        value = load_profile(destination, kind)
        profiles[kind] = {
            "path": destination.relative_to(artifact_root).as_posix(),
            "profile_id": value["profile_id"],
            "sha256": canonical_sha256(value),
        }
    return profiles


def _job(
    site: Mapping[str, Any],
    factory: DirichletPackedOperationalWorkloadFactory,
    artifact_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    profiles = _profiles(artifact_root)
    runner_policy = {
        "path": "profiles/runner-policy.json",
        "policy_id": site["runner_policy"]["policy_id"],
        "sha256": site["runner_policy"]["sha256"],
    }
    _copy_exact(
        Path(site["runner_policy"]["path"]),
        artifact_root / runner_policy["path"],
    )
    for profile_kind in ("target", "trust"):
        records.append(
            _artifact_record(
                artifact_root / profiles[profile_kind]["path"],
                artifact_root,
                role=f"measured_{profile_kind}_profile",
                statement_role=None,
                executable=False,
            )
        )
    records.append(
        _artifact_record(
            artifact_root / runner_policy["path"],
            artifact_root,
            role="measured_runner_appraisal_policy",
            statement_role=None,
            executable=False,
        )
    )
    input_path = artifact_root / "input/packed-input-manifest.json"
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
            "manifest_sha256": canonical_sha256(_closure_manifest(records)),
        },
        "backend": h100_operator.BACKEND,
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
        "gpu_pre_run_gate": {
            "argv": [
                "artifacts/python3",
                "-I",
                "-B",
                "attestation/azure_h100_pre_run_gate.py",
                "--challenge-nonce",
                "@challenge@",
                "--challenge-expires-at",
                "@challenge_expires_at@",
                "--job-binding",
                "@job_binding@",
                "--package-root",
                ".",
                "--record-path",
                "@gate_record@",
                "--policy",
                "profiles/nvidia-gpu.rego",
                "--verifier",
                site["gpu_verifier"],
                "--nras-url",
                site["nras_url"],
            ],
            "record_path": "runner/h100-pre-run-gate.json",
            "required": True,
            "secret_environment_names": ["NV_ATTESTATION_SERVICE_KEY"],
            "timeout_seconds": 600,
        },
        "input_artifact": {
            "path": "input/packed-input-manifest.json",
            "release_argv": None,
            "release_mode": "prepositioned_public_after_start",
            "sha256": hashlib.sha256(factory.input_bytes).hexdigest(),
            "size_bytes": len(factory.input_bytes),
        },
        "job_id": factory.factory_id.replace("_", "-"),
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
    if input_path.read_bytes() != factory.input_bytes:
        raise DirichletPackedMaterializerError(
            "copied packed manifest differs from the factory input"
        )
    validate_job_spec(job)
    return job


def materialize(site: Mapping[str, Any]) -> dict[str, Any]:
    plan = plan_materialization(site)
    output_root = site["output_root"]
    output_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.dirichlet-packed-materializing-",
            dir=output_root.parent,
        )
    )
    published = False
    complete = False
    try:
        artifact_root = stage / "artifact-root"
        artifact_root.mkdir(mode=0o700)
        sources = _copy_sources(artifact_root)
        copied = _copy_inputs(site["site"], artifact_root)
        # Re-run the exact production receipt, typed pinset, full-span, roster,
        # and artifact checks over the bytes that will actually execute.
        try:
            packaged_inputs = _workload_module()._load_packed_inputs(
                _packed_args(site["site"], copied_root=artifact_root)
            )
        except Exception as error:
            raise DirichletPackedMaterializerError(
                f"packaged packed input closure failed validation: {error}"
            ) from error
        if (
            packaged_inputs["manifest_sha256"]
            != site["inputs"]["manifest_sha256"]
            or packaged_inputs["artifact_roster_sha256"]
            != site["inputs"]["artifact_roster_sha256"]
            or packaged_inputs["predecessor"]["receipt_sha256"]
            != site["inputs"]["predecessor"]["receipt_sha256"]
        ):
            raise DirichletPackedMaterializerError(
                "packaged packed input closure differs after copy"
            )
        packaged_bound_sources = {
            "compact_reducer_source": (
                artifact_root
                / "tg_verifier/dirichlet_compact_state_streaming_v3.py"
            ),
            "measured_workload_source": (
                artifact_root
                / "tools/tg_dirichlet_azure_measured_workload.py"
            ),
            "packed_reducer_source": (
                artifact_root
                / "tg_verifier/dirichlet_booker_smallq_packed_stream_v1.py"
            ),
            "runner_source": artifact_root / PACKED_RUNNER_SOURCE_PATH,
        }
        for role, path in packaged_bound_sources.items():
            pin = _file_pin(path)
            expected = packaged_inputs["artifacts"][role]
            if {
                "sha256": pin["sha256"],
                "size_bytes": pin["size_bytes"],
            } != expected:
                raise DirichletPackedMaterializerError(
                    f"packaged {role} differs from its authenticated manifest"
                )
        source_rows = []
        for path in sorted(sources):
            pin = _file_pin(path)
            source_rows.append(
                {
                    "path": path.relative_to(artifact_root).as_posix(),
                    "sha256": pin["sha256"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        source_manifest = {
            "device_side_classification_implemented": (
                packaged_inputs["manifest"]["packing_location"]
                == PACKED_DEVICE_LOCATION
            ),
            "files": source_rows,
            "kind": SOURCE_CLOSURE_KIND,
            "packing_location": packaged_inputs["manifest"][
                "packing_location"
            ],
            "packing_mode": packaged_inputs["manifest"]["packing_mode"],
            "raw_disk_device_to_host_transfer_eliminated": (
                packaged_inputs["manifest"]["packing_location"]
                == PACKED_DEVICE_LOCATION
            ),
            "runner_sha256": packaged_inputs["artifacts"]["runner"]["sha256"],
            "schema_version": 1,
            "source_admission_enabled": False,
        }
        source_manifest_path = (
            artifact_root / "source/dirichlet-packed-source-closure.json"
        )
        _write_bytes(source_manifest_path, canonical_json_bytes(source_manifest))
        records: list[dict[str, Any]] = []
        for path in sources:
            records.append(
                _artifact_record(
                    path,
                    artifact_root,
                    role="reviewed_dirichlet_packed_source",
                    statement_role=None,
                    executable=False,
                )
            )
        roles = {
            "artifacts/python3": (
                "image_bound_cpython_host",
                "host_executable",
                True,
            ),
            PACKED_RUNNER_PATH: (
                "receipt_authenticated_dirichlet_smallq_h100_runner",
                "gpu_executable",
                True,
            ),
            "profiles/nvidia-gpu.rego": (
                "nvidia_pre_run_appraisal_policy",
                "gpu_attestation_policy",
                False,
            ),
            "input/packed-input-manifest.json": (
                "production_authenticated_packed_input_manifest",
                None,
                False,
            ),
        }
        for path in copied:
            relative = path.relative_to(artifact_root).as_posix()
            role, statement_role, executable = roles.get(
                relative,
                ("authenticated_dirichlet_packed_input", None, False),
            )
            records.append(
                _artifact_record(
                    path,
                    artifact_root,
                    role=role,
                    statement_role=statement_role,
                    executable=executable,
                )
            )
        records.append(
            _artifact_record(
                source_manifest_path,
                artifact_root,
                role="reviewed_dirichlet_packed_source_closure_manifest",
                statement_role="source_tree",
                executable=False,
            )
        )
        factory = site["factory"]
        job = _job(site["site"], factory, artifact_root, records)
        job_path = artifact_root / "job.json"
        _write_bytes(job_path, canonical_json_bytes(job))
        package = stage / "workload.tar"
        create_archive(artifact_root, package)
        job_pin = _file_pin(job_path)
        job_pin["path"] = str(output_root / "artifact-root/job.json")
        package_pin = _file_pin(package)
        package_pin["path"] = str(output_root / "workload.tar")
        manifest = {
            "accepted": False,
            "artifact_roster_sha256": packaged_inputs[
                "artifact_roster_sha256"
            ],
            "classification": (
                "source_reviewed_dirichlet_smallq_packed_h100_"
                "materialization_not_execution_or_source_evidence"
            ),
            "device_side_classification_implemented": (
                packaged_inputs["manifest"]["packing_location"]
                == PACKED_DEVICE_LOCATION
            ),
            "execution_completed": False,
            "factory_id": factory.factory_id,
            "input_manifest_sha256": packaged_inputs["manifest_sha256"],
            "job_spec": job_pin,
            "kind": MANIFEST_KIND,
            "lean_theorem_produced": False,
            "package": package_pin,
            "packing_location": packaged_inputs["manifest"][
                "packing_location"
            ],
            "packing_mode": packaged_inputs["manifest"]["packing_mode"],
            "pinset_sha256": packaged_inputs["manifest"]["pinset_sha256"],
            "predecessor_receipt_sha256": packaged_inputs["predecessor"][
                "receipt_sha256"
            ],
            "production_ready": False,
            "q": factory.q,
            "raw_disk_device_to_host_transfer_eliminated": (
                packaged_inputs["manifest"]["packing_location"]
                == PACKED_DEVICE_LOCATION
            ),
            "registered_invocation": None,
            "schema_version": 1,
            "source_admission_enabled": False,
        }
        manifest_path = stage / "materialization-manifest.json"
        _write_bytes(manifest_path, canonical_json_bytes(manifest))
        if output_root.exists() or output_root.is_symlink():
            raise DirichletPackedMaterializerError(
                "packed output_root appeared during materialization"
            )
        os.replace(stage, output_root)
        published = True
        complete = True
        return {
            **manifest,
            "manifest": str(
                output_root / "materialization-manifest.json"
            ),
        }
    except (
        ArchiveError,
        CampaignIOError,
        OSError,
        ValueError,
    ) as error:
        raise DirichletPackedMaterializerError(
            f"packed Dirichlet materialization failed closed: {error}"
        ) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if published and not complete and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)


__all__ = [
    "DirichletPackedMaterializerError",
    "MANIFEST_KIND",
    "SITE_KIND",
    "load_site",
    "materialize",
    "plan_materialization",
]
