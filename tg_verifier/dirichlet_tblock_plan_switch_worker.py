# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Actual bounded multi-q plan-switch worker for t-block protocol v2.

For every active q in one authenticated t block, this worker invokes the
existing real residue composer, q-specific native all-character executable,
and FLINT completed-L consumer, builds a typed bundle, and emits bundles in
the protocol's explicit ``t_block_major_then_q`` order.  A canonical recipe
pins every input and runtime artifact.  The handshake advertises arithmetic
capabilities only after those hashes and the Python-FLINT version probe pass.

This remains a bounded structural KAT.  It does not claim certified analytic
inputs, source-scale execution, CUDA attestation, zero/Turing completeness,
trusted execution, or discharge of Platt's theorem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_fft_pipeline_bundle import (
    build_bundle,
    replay_bundle,
)
from tg_verifier.dirichlet_largeq_pipeline import run_pipeline
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_lattice_stage import maximum_t_index
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    FRAME_LENGTH,
    MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK,
    NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION,
    WORKER_ALGORITHM_ID,
)
from tg_verifier.dirichlet_tblock_bundle_worker import (
    _frame_header,
    _stream_header,
    _validate_request,
)
from tg_verifier.dirichlet_tblock_supervisor import (
    ATOM_ID,
    AUTHOR,
    _canonical_line,
    _digest,
    _integer,
)
from tg_verifier.dirichlet_tblock_bundle_supervisor import (
    HANDSHAKE_SCHEMA,
    RESPONSE_SCHEMA,
)
from tg_verifier.dirichlet_tblock_worker import _file_sha256
from tg_verifier.dirichlet_tmajor_adapter import BLOCK_MAJOR_TARGET_ORDER
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
)


RECIPE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_plan_switch.recipe.v1"
)
RECIPE_CLASSIFICATION = (
    "bounded_actual_native_multi_q_plan_switch_recipe_not_source_evidence"
)
MAXIMUM_RECIPE_BYTES = 4 * 1024 * 1024
MAXIMUM_RUNTIME_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAXIMUM_EVENT_BYTES_PER_TARGET = 640 * 1024 * 1024
DEFAULT_MAXIMUM_RETAINED_OUTPUT_BYTES = 1024 * 1024 * 1024
MAXIMUM_RETAINED_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
NON_EVENT_OUTPUT_RESERVE_BYTES = 16 * 1024 * 1024
EXPECTED_PYTHON_FLINT = {
    "python_flint_version": "0.9.0",
    "flint_version": "3.6.0",
}


class DirichletTBlockPlanSwitchWorkerError(RuntimeError):
    """A pinned recipe, runtime, target, or arithmetic invocation failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTBlockPlanSwitchWorkerError(message)


def _safe_file(path: Path, *, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletTBlockPlanSwitchWorkerError(
            f"cannot open pinned regular file without following links: {path}"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size <= 0
            or status.st_size > maximum_bytes
        ):
            _fail("pinned file type or size is outside its fixed bound")
        raw = source.read()
    return raw, {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def artifact_record(path: Path) -> dict[str, Any]:
    """Return a pinned record for one non-symlink input artifact."""

    _raw, record = _safe_file(
        path.resolve(), maximum_bytes=MAXIMUM_RUNTIME_ARTIFACT_BYTES
    )
    return record


def runtime_artifact_record(path: Path) -> dict[str, Any]:
    """Pin a possibly-symlinked invocation path and its resolved file."""

    invocation = path.absolute()
    resolved = invocation.resolve()
    _raw, artifact = _safe_file(
        resolved, maximum_bytes=MAXIMUM_RUNTIME_ARTIFACT_BYTES
    )
    return {
        "invocation_path": str(invocation),
        "resolved_path": artifact["path"],
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
    }


def _validate_artifact(
    value: object,
    *,
    label: str,
) -> Path:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "sha256", "size_bytes"}
    ):
        _fail(f"{label} artifact record fields differ")
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        _fail(f"{label} artifact path is malformed")
    path = Path(raw_path)
    if not path.is_absolute() or str(path.resolve()) != raw_path:
        _fail(f"{label} artifact path is not absolute and normalized")
    raw, observed = _safe_file(
        path, maximum_bytes=MAXIMUM_RUNTIME_ARTIFACT_BYTES
    )
    del raw
    if observed != value:
        _fail(f"{label} artifact differs from its recipe pin")
    return path


def _validate_runtime_artifact(
    value: object,
    *,
    label: str,
    executable: bool,
) -> Path:
    required = {
        "invocation_path",
        "resolved_path",
        "sha256",
        "size_bytes",
    }
    if not isinstance(value, dict) or set(value) != required:
        _fail(f"{label} runtime artifact fields differ")
    invocation_value = value.get("invocation_path")
    resolved_value = value.get("resolved_path")
    if (
        not isinstance(invocation_value, str)
        or not isinstance(resolved_value, str)
        or not Path(invocation_value).is_absolute()
        or not Path(resolved_value).is_absolute()
    ):
        _fail(f"{label} runtime path is malformed")
    invocation = Path(invocation_value)
    resolved = invocation.resolve()
    if str(resolved) != resolved_value:
        _fail(f"{label} invocation path resolves to another artifact")
    raw, observed = _safe_file(
        resolved, maximum_bytes=MAXIMUM_RUNTIME_ARTIFACT_BYTES
    )
    del raw
    if observed != {
        "path": resolved_value,
        "sha256": value.get("sha256"),
        "size_bytes": value.get("size_bytes"),
    }:
        _fail(f"{label} runtime artifact differs from its recipe pin")
    if executable and not os.access(invocation, os.X_OK):
        _fail(f"{label} runtime invocation is not executable")
    return invocation


def _python_flint_probe(python: Path) -> dict[str, str]:
    command = [
        str(python),
        "-c",
        (
            "import flint,json;"
            "print(json.dumps({"
            "'flint_version':flint.__FLINT_VERSION__,"
            "'python_flint_version':flint.__version__"
            "},sort_keys=True,separators=(',',':')))"
        ),
    ]
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        _fail(
            "pinned Python-FLINT probe failed: "
            + completed.stderr.decode("utf-8", "replace")[-1024:]
        )
    try:
        value = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTBlockPlanSwitchWorkerError(
            "pinned Python-FLINT probe returned invalid JSON"
        ) from error
    if value != EXPECTED_PYTHON_FLINT:
        _fail("pinned Python-FLINT versions differ")
    return value


def _recipe_body(
    *,
    contract_path: Path,
    runtime: Mapping[str, Path],
    targets: Sequence[Mapping[str, Any]],
    allow_synthetic_kat: bool,
    maximum_batch_count: int,
    device: int,
    precision: int,
    maximum_event_bytes_per_target: int,
    maximum_retained_output_bytes: int,
) -> dict[str, Any]:
    runtime_keys = {
        "composer_python",
        "composer_tool",
        "allchars_runner",
        "consumer_python",
        "consumer_tool",
    }
    if set(runtime) != runtime_keys:
        _fail("native plan-switch runtime keys differ")
    runtime_records = {
        key: runtime_artifact_record(path)
        for key, path in sorted(runtime.items())
    }
    python_flint = _python_flint_probe(runtime["consumer_python"])
    maximum_event_bytes_per_target = _integer(
        maximum_event_bytes_per_target,
        "maximum event bytes per target",
        minimum=1,
        maximum=MAXIMUM_RETAINED_OUTPUT_BYTES,
    )
    maximum_retained_output_bytes = _integer(
        maximum_retained_output_bytes,
        "maximum retained output bytes",
        minimum=NON_EVENT_OUTPUT_RESERVE_BYTES + 1,
        maximum=MAXIMUM_RETAINED_OUTPUT_BYTES,
    )
    if maximum_event_bytes_per_target > maximum_retained_output_bytes:
        _fail("per-target event budget exceeds retained output budget")
    normalized_targets: list[dict[str, Any]] = []
    for value in targets:
        required = {
            "sequence_index",
            "q",
            "first_t_index",
            "t_index_stop_exclusive",
            "control_base",
            "composition_controls",
            "consumer_controls",
            "root_artifact",
            "root_receipt",
        }
        if set(value) != required:
            _fail("native plan-switch target input keys differ")
        control_base = Path(value["control_base"]).resolve()
        if not control_base.is_dir() or control_base.is_symlink():
            _fail("native target control base is not a non-symlink directory")
        normalized_targets.append(
            {
                "sequence_index": _integer(
                    value["sequence_index"],
                    "target sequence",
                    minimum=0,
                ),
                "q": _integer(value["q"], "target q", minimum=10_001),
                "first_t_index": _integer(
                    value["first_t_index"], "target first t", minimum=0
                ),
                "t_index_stop_exclusive": _integer(
                    value["t_index_stop_exclusive"],
                    "target t stop",
                    minimum=value["first_t_index"] + 1,
                ),
                "control_base": str(control_base),
                "composition_controls": artifact_record(
                    Path(value["composition_controls"])
                ),
                "consumer_controls": artifact_record(
                    Path(value["consumer_controls"])
                ),
                "root_artifact": artifact_record(
                    Path(value["root_artifact"])
                ),
                "root_receipt": artifact_record(
                    Path(value["root_receipt"])
                ),
            }
        )
    normalized_targets.sort(
        key=lambda item: (item["sequence_index"], item["q"])
    )
    identities = [
        (item["sequence_index"], item["q"]) for item in normalized_targets
    ]
    if len(set(identities)) != len(identities):
        _fail("native plan-switch target identities are duplicated")
    contract_record = artifact_record(contract_path)
    contract_value = json.loads(Path(contract_record["path"]).read_bytes())
    contract_sha256 = _digest(
        contract_value.get("contract_sha256"), "recipe source contract"
    )
    return {
        "schema": RECIPE_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "classification": RECIPE_CLASSIFICATION,
        "target_order": BLOCK_MAJOR_TARGET_ORDER,
        "contract": contract_record,
        "source_contract_sha256": contract_sha256,
        "allow_synthetic_kat": bool(allow_synthetic_kat),
        "maximum_batch_count": _integer(
            maximum_batch_count,
            "maximum batch count",
            minimum=1,
            maximum=64,
        ),
        "device": _integer(device, "device", minimum=0),
        "precision": _integer(
            precision, "precision", minimum=128, maximum=4096
        ),
        "storage_policy": {
            "event_storage_mode": COMPACT_EVENT_STORAGE_MODE,
            "maximum_event_bytes_per_target": (
                maximum_event_bytes_per_target
            ),
            "maximum_retained_output_bytes": (
                maximum_retained_output_bytes
            ),
            "raw_event_streams_retained_for_typed_bundle_resume": False,
            "compact_event_summary_replayed_on_resume": True,
            "source_scale_storage_admitted": False,
        },
        "runtime": runtime_records,
        "python_flint": python_flint,
        "targets": normalized_targets,
        "source_scale_run": False,
        "claims": {
            "certified_analytic_inputs": False,
            "cuda_execution_attested": False,
            "zero_completeness": False,
            "turing_completeness": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }


def write_recipe(
    output_path: Path,
    *,
    contract_path: Path,
    runtime: Mapping[str, Path],
    targets: Sequence[Mapping[str, Any]],
    allow_synthetic_kat: bool = True,
    maximum_batch_count: int = 64,
    device: int = 0,
    precision: int = 192,
    maximum_event_bytes_per_target: int = (
        DEFAULT_MAXIMUM_EVENT_BYTES_PER_TARGET
    ),
    maximum_retained_output_bytes: int = (
        DEFAULT_MAXIMUM_RETAINED_OUTPUT_BYTES
    ),
) -> dict[str, Any]:
    """Build one canonical, self-hashed bounded arithmetic recipe."""

    body = _recipe_body(
        contract_path=contract_path,
        runtime=runtime,
        targets=targets,
        allow_synthetic_kat=allow_synthetic_kat,
        maximum_batch_count=maximum_batch_count,
        device=device,
        precision=precision,
        maximum_event_bytes_per_target=maximum_event_bytes_per_target,
        maximum_retained_output_bytes=maximum_retained_output_bytes,
    )
    recipe = dict(body)
    recipe["recipe_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    if output_path.exists():
        _fail("refusing to replace immutable native plan-switch recipe")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = __import__("tempfile").mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(recipe))
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary_name, output_path)
        os.unlink(temporary_name)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return recipe


def load_recipe(path: Path) -> tuple[dict[str, Any], dict[str, Path], str]:
    raw, observed = _safe_file(path, maximum_bytes=MAXIMUM_RECIPE_BYTES)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTBlockPlanSwitchWorkerError(
            "native plan-switch recipe is invalid JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("native plan-switch recipe is not canonical JSON")
    body = dict(value)
    recipe_sha256 = _digest(
        body.pop("recipe_sha256", None), "native plan-switch recipe"
    )
    if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != recipe_sha256:
        _fail("native plan-switch recipe self-hash differs")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "classification",
        "target_order",
        "contract",
        "source_contract_sha256",
        "allow_synthetic_kat",
        "maximum_batch_count",
        "device",
        "precision",
        "storage_policy",
        "runtime",
        "python_flint",
        "targets",
        "source_scale_run",
        "claims",
    }
    if (
        set(body) != required
        or value.get("schema") != RECIPE_SCHEMA
        or value.get("schema_version") != 1
        or value.get("author") != AUTHOR
        or value.get("atom_id") != ATOM_ID
        or value.get("classification") != RECIPE_CLASSIFICATION
        or value.get("target_order") != BLOCK_MAJOR_TARGET_ORDER
        or value.get("source_scale_run") is not False
        or value.get("allow_synthetic_kat") is not True
    ):
        _fail("native plan-switch recipe identity or boundary differs")
    expected_claims = {
        "certified_analytic_inputs": False,
        "cuda_execution_attested": False,
        "zero_completeness": False,
        "turing_completeness": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    if value.get("claims") != expected_claims:
        _fail("native plan-switch recipe claims differ")
    contract_path = _validate_artifact(
        value.get("contract"), label="source contract"
    )
    contract = json.loads(contract_path.read_bytes())
    if contract.get("contract_sha256") != _digest(
        value.get("source_contract_sha256"), "recipe source contract"
    ):
        _fail("native plan-switch contract semantic digest differs")
    runtime_value = value.get("runtime")
    runtime_keys = {
        "composer_python",
        "composer_tool",
        "allchars_runner",
        "consumer_python",
        "consumer_tool",
    }
    if not isinstance(runtime_value, dict) or set(runtime_value) != runtime_keys:
        _fail("native plan-switch runtime inventory differs")
    runtime_paths = {
        key: _validate_runtime_artifact(
            runtime_value[key],
            label=key,
            executable=key
            in {
                "composer_python",
                "allchars_runner",
                "consumer_python",
            },
        )
        for key in sorted(runtime_keys)
    }
    if (
        value.get("python_flint") != EXPECTED_PYTHON_FLINT
        or _python_flint_probe(runtime_paths["consumer_python"])
        != value["python_flint"]
    ):
        _fail("native plan-switch Python-FLINT probe differs")
    targets = value.get("targets")
    if not isinstance(targets, list) or len(targets) > (
        MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK * 4096
    ):
        _fail("native plan-switch target inventory is malformed or excessive")
    previous: tuple[int, int] | None = None
    for target in targets:
        if not isinstance(target, dict):
            _fail("native plan-switch target is malformed")
        identity = (
            _integer(
                target.get("sequence_index"),
                "recipe target sequence",
                minimum=0,
            ),
            _integer(target.get("q"), "recipe target q", minimum=10_001),
        )
        if previous is not None and identity <= previous:
            _fail("native plan-switch targets are duplicated or reordered")
        previous = identity
        first = _integer(
            target.get("first_t_index"),
            "recipe target first t",
            minimum=0,
        )
        _integer(
            target.get("t_index_stop_exclusive"),
            "recipe target t stop",
            minimum=first + 1,
            maximum=first + 64,
        )
        control_base = target.get("control_base")
        if (
            not isinstance(control_base, str)
            or not Path(control_base).is_absolute()
            or str(Path(control_base).resolve()) != control_base
            or not Path(control_base).is_dir()
            or Path(control_base).is_symlink()
        ):
            _fail("recipe target control base differs")
        expected_target_fields = {
            "sequence_index",
            "q",
            "first_t_index",
            "t_index_stop_exclusive",
            "control_base",
            "composition_controls",
            "consumer_controls",
            "root_artifact",
            "root_receipt",
        }
        if set(target) != expected_target_fields:
            _fail("recipe target fields differ")
        for field in (
            "composition_controls",
            "consumer_controls",
            "root_artifact",
            "root_receipt",
        ):
            _validate_artifact(target[field], label=f"target {field}")
    _integer(
        value.get("maximum_batch_count"),
        "recipe maximum batch count",
        minimum=1,
        maximum=64,
    )
    _integer(value.get("device"), "recipe device", minimum=0)
    _integer(
        value.get("precision"),
        "recipe precision",
        minimum=128,
        maximum=4096,
    )
    storage_policy = value.get("storage_policy")
    if (
        not isinstance(storage_policy, dict)
        or set(storage_policy)
        != {
            "maximum_event_bytes_per_target",
            "maximum_retained_output_bytes",
            "event_storage_mode",
            "raw_event_streams_retained_for_typed_bundle_resume",
            "compact_event_summary_replayed_on_resume",
            "source_scale_storage_admitted",
        }
        or storage_policy.get("event_storage_mode")
        != COMPACT_EVENT_STORAGE_MODE
        or storage_policy.get(
            "raw_event_streams_retained_for_typed_bundle_resume"
        )
        is not False
        or storage_policy.get(
            "compact_event_summary_replayed_on_resume"
        )
        is not True
        or storage_policy.get("source_scale_storage_admitted") is not False
    ):
        _fail("native plan-switch storage policy differs")
    maximum_event_bytes = _integer(
        storage_policy.get("maximum_event_bytes_per_target"),
        "recipe maximum event bytes per target",
        minimum=1,
        maximum=MAXIMUM_RETAINED_OUTPUT_BYTES,
    )
    maximum_retained_bytes = _integer(
        storage_policy.get("maximum_retained_output_bytes"),
        "recipe maximum retained output bytes",
        minimum=NON_EVENT_OUTPUT_RESERVE_BYTES + 1,
        maximum=MAXIMUM_RETAINED_OUTPUT_BYTES,
    )
    if maximum_event_bytes > maximum_retained_bytes:
        _fail("recipe event budget exceeds retained output budget")
    runtime_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "runtime": runtime_value,
                "python_flint": value["python_flint"],
            }
        )
    ).hexdigest()
    if observed["sha256"] != hashlib.sha256(raw).hexdigest():
        raise AssertionError("unreachable recipe digest mismatch")
    return value, runtime_paths | {"contract": contract_path}, runtime_sha256


def native_handshake(
    implementation_path: Path,
    *,
    launcher_path: Path,
    recipe: Mapping[str, Any],
    runtime_artifacts_sha256: str,
) -> dict[str, Any]:
    implementation_identity = {
        "module_sha256": _file_sha256(implementation_path),
        "launcher_sha256": _file_sha256(launcher_path),
    }
    implementation_sha256 = hashlib.sha256(
        canonical_json_bytes(implementation_identity)
    ).hexdigest()
    body: dict[str, Any] = {
        "schema": HANDSHAKE_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "classification": NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION,
        "worker_id": "python-actual-native-multi-q-plan-switch-worker-v1",
        "worker_implementation_sha256": implementation_sha256,
        "capabilities": {
            "accepts_one_authenticated_t_block_payload": True,
            "derives_exact_active_q_roster_formulaically": True,
            "multi_q_target_iteration": True,
            "multi_q_plan_switching": True,
            "resumable_idempotent_outputs": True,
            "actual_residue_composer": True,
            "actual_all_character_transform": True,
            "actual_completed_l_consumer": True,
            "typed_bundle_emission": True,
            "adapter_compatible_output": True,
            "framed_typed_bundle_bytes_to_supervisor": True,
        },
        "execution_profile": {
            "target_order": BLOCK_MAJOR_TARGET_ORDER,
            "recipe_sha256": recipe["recipe_sha256"],
            "runtime_artifacts_sha256": runtime_artifacts_sha256,
            "arithmetic_backend": (
                "pinned_python_flint_composer_native_allchars_flint_consumer"
            ),
            "storage_policy": dict(recipe["storage_policy"]),
            "source_scale_run": False,
        },
        "claims": {
            "cuda_execution_attested": False,
            "completed_l_zero_completeness": False,
            "turing_completeness": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    result = dict(body)
    result["handshake_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _target_inputs(
    recipe: Mapping[str, Any],
    *,
    sequence: int,
    request: Mapping[str, Any],
) -> list[dict[str, Any]]:
    roster = request["target_roster"]
    first = request["row_block"]["first_t_index"]
    stop = request["row_block"]["t_index_stop_exclusive"]
    q_sequence = [
        q
        for q in range(
            roster["q_start_inclusive"], roster["q_stop_inclusive"] + 1
        )
        if first <= maximum_t_index(q)
    ]
    selected = [
        target
        for target in recipe["targets"]
        if target["sequence_index"] == sequence
    ]
    if [target["q"] for target in selected] != q_sequence:
        _fail("recipe q roster differs from the exact active request roster")
    for target, q in zip(selected, q_sequence):
        expected_stop = min(stop, maximum_t_index(q) + 1)
        if (
            target["first_t_index"] != first
            or target["t_index_stop_exclusive"] != expected_stop
        ):
            _fail("recipe target t range differs from the exact request")
    return selected


def _fresh_target_artifacts(target: Mapping[str, Any]) -> None:
    for field in (
        "composition_controls",
        "consumer_controls",
        "root_artifact",
        "root_receipt",
    ):
        _validate_artifact(target[field], label=f"request target {field}")


def _tree_regular_bytes(root: Path) -> int:
    """Count retained regular-file bytes and reject links/special files."""

    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            _fail("native output tree contains a symlink")
        if path.is_dir():
            continue
        status = path.stat()
        if not stat.S_ISREG(status.st_mode):
            _fail("native output tree contains a non-regular file")
        total += status.st_size
    return total


def _target_storage(root: Path, *, q: int) -> dict[str, Any]:
    pipeline = root / "pipeline"
    bundle = root / "typed-bundle.json"
    consumer_receipt_path = pipeline / "consumer-receipt.json"
    if not consumer_receipt_path.is_file() or not bundle.is_file():
        _fail("native target storage artifacts are incomplete")
    consumer_receipt = json.loads(consumer_receipt_path.read_bytes())
    event_storage_mode = consumer_receipt.get("event_storage_mode")
    events = pipeline / (
        "events-summary.json"
        if event_storage_mode == COMPACT_EVENT_STORAGE_MODE
        else "events.ndjson"
    )
    if not events.is_file():
        _fail("native target event artifact is missing")
    pipeline_bytes = _tree_regular_bytes(pipeline)
    return {
        "q": q,
        "event_artifact_bytes": events.stat().st_size,
        "event_storage_mode": event_storage_mode,
        "pipeline_bytes": pipeline_bytes,
        "typed_bundle_bytes": bundle.stat().st_size,
        "target_output_bytes": _tree_regular_bytes(root),
        "raw_event_stream_retained": (
            event_storage_mode != COMPACT_EVENT_STORAGE_MODE
        ),
        "compact_event_summary_retained": (
            event_storage_mode == COMPACT_EVENT_STORAGE_MODE
        ),
        "classification": "exact_worker_filesystem_bytes_not_proof_evidence",
    }


def _bundle_raw(
    *,
    recipe: Mapping[str, Any],
    runtime: Mapping[str, Path],
    target: Mapping[str, Any],
    output_root: Path,
) -> tuple[bytes, bool, dict[str, Any], dict[str, Any]]:
    sequence = target["sequence_index"]
    q = target["q"]
    root = (
        output_root
        / f"block-{sequence:08d}"
        / f"q-{q:06d}"
    )
    pipeline_directory = root / "pipeline"
    pipeline_receipt = root / "pipeline-receipt.json"
    bundle_path = root / "typed-bundle.json"
    consumer_timing_path = root / "consumer-timing.json"
    worker_timing_path = root / "worker-timing.json"
    contract_path = runtime["contract"]
    if bundle_path.exists():
        raw = bundle_path.read_bytes()
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DirichletTBlockPlanSwitchWorkerError(
                "cached typed bundle is invalid JSON"
            ) from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
            _fail("cached typed bundle is not canonical JSON")
        replay = replay_bundle(
            bundle_path,
            contract_path=contract_path,
            control_base=Path(target["control_base"]),
            allow_structural_kat=True,
            expected_bundle_sha256=_digest(
                value.get("bundle_sha256"), "cached typed bundle"
            ),
        )
        if (
            replay.get("q") != q
            or replay.get("first_t_index") != target["first_t_index"]
            or replay.get("t_index_stop_exclusive")
            != target["t_index_stop_exclusive"]
        ):
            _fail("cached typed bundle covers another target")
        return (
            raw,
            False,
            _target_timing(
                root,
                q=q,
                target=target,
                generated_this_invocation=False,
            ),
            _target_storage(root, q=q),
        )
    if root.exists():
        _fail("partial native plan-switch output exists without a typed bundle")
    root.mkdir(parents=True)
    _fresh_target_artifacts(target)
    storage_policy = recipe["storage_policy"]
    retained_before = _tree_regular_bytes(output_root)
    retained_budget = storage_policy["maximum_retained_output_bytes"]
    remaining = retained_budget - retained_before
    if remaining <= NON_EVENT_OUTPUT_RESERVE_BYTES:
        _fail("native retained-output byte budget is exhausted")
    event_budget = min(
        storage_policy["maximum_event_bytes_per_target"],
        remaining - NON_EVENT_OUTPUT_RESERVE_BYTES,
    )
    started = time.perf_counter()
    run_pipeline(
        composition_controls=Path(
            target["composition_controls"]["path"]
        ),
        consumer_controls=Path(target["consumer_controls"]["path"]),
        control_base=Path(target["control_base"]),
        composer_python=runtime["composer_python"],
        composer_tool=runtime["composer_tool"],
        allchars_runner=runtime["allchars_runner"],
        consumer_python=runtime["consumer_python"],
        consumer_tool=runtime["consumer_tool"],
        root_artifact=Path(target["root_artifact"]["path"]),
        root_receipt=Path(target["root_receipt"]["path"]),
        output_directory=pipeline_directory,
        pipeline_receipt=pipeline_receipt,
        maximum_batch_count=recipe["maximum_batch_count"],
        device=recipe["device"],
        precision=recipe["precision"],
        allow_synthetic_kat=True,
        consumer_timing_output=consumer_timing_path,
        maximum_event_bytes=event_budget,
        event_storage_mode=storage_policy["event_storage_mode"],
    )
    pipeline_wall = time.perf_counter() - started
    worker_timing = {
        "schema": (
            "sparkinterval.tg.dirichlet_tblock_plan_switch.timing.v1"
        ),
        "classification": "diagnostic_wall_time_not_proof_evidence",
        "q": q,
        "pipeline_wall_seconds": pipeline_wall,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    worker_timing["timing_sha256"] = hashlib.sha256(
        canonical_json_bytes(worker_timing)
    ).hexdigest()
    worker_timing_path.write_bytes(canonical_json_bytes(worker_timing))
    build_bundle(
        bundle_path,
        contract_path=contract_path,
        lane_index=0,
        q=q,
        first_t_index=target["first_t_index"],
        pipeline_receipt_path=pipeline_receipt,
        control_base=Path(target["control_base"]),
        allow_structural_kat=True,
    )
    retained_after = _tree_regular_bytes(output_root)
    if retained_after > retained_budget:
        _fail("native output exceeds its recipe-pinned retained-byte budget")
    return (
        bundle_path.read_bytes(),
        True,
        _target_timing(
            root,
            q=q,
            target=target,
            generated_this_invocation=True,
        ),
        _target_storage(root, q=q),
    )


def _timing_value(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        _fail(f"{label} diagnostic timing is invalid")
    return float(value)


def _target_timing(
    root: Path,
    *,
    q: int,
    target: Mapping[str, Any],
    generated_this_invocation: bool,
) -> dict[str, Any]:
    composition_seconds = 0.0
    for raw_control in Path(
        target["composition_controls"]["path"]
    ).read_bytes().splitlines():
        control = json.loads(raw_control)
        receipt_path = Path(control["receipt"])
        if not receipt_path.is_absolute():
            receipt_path = Path(target["control_base"]) / receipt_path
        composition_receipt = json.loads(receipt_path.read_bytes())
        composition_seconds += _timing_value(
            composition_receipt.get("elapsed_seconds"),
            "composer wall",
        )
    transform = json.loads(
        (root / "pipeline" / "transform-summary.json").read_bytes()
    )
    consumer = json.loads((root / "consumer-timing.json").read_bytes())
    worker = json.loads((root / "worker-timing.json").read_bytes())
    if (
        transform.get("q") != q
        or worker.get("q") != q
        or consumer.get("classification")
        != "diagnostic_wall_time_not_proof_evidence"
        or worker.get("classification")
        != "diagnostic_wall_time_not_proof_evidence"
        or consumer.get("trusted_execution_attested") is not False
        or worker.get("trusted_execution_attested") is not False
    ):
        _fail("native target diagnostic timing identity differs")
    return {
        "q": q,
        "generated_this_invocation": generated_this_invocation,
        "pipeline_wall_seconds": _timing_value(
            worker.get("pipeline_wall_seconds"), "pipeline wall"
        ),
        "composer_wall_seconds": _timing_value(
            composition_seconds, "composer wall"
        ),
        "allchars_preparation_seconds": _timing_value(
            transform.get("preparation_nanoseconds"),
            "allchars preparation",
        )
        / 1_000_000_000,
        "allchars_execution_seconds": _timing_value(
            transform.get("elapsed_nanoseconds"), "allchars execution"
        )
        / 1_000_000_000,
        "flint_consumer_wall_seconds": _timing_value(
            consumer.get("elapsed_seconds"), "FLINT consumer wall"
        ),
        "classification": "diagnostic_timing_not_proof_evidence",
    }


def _response(
    request: Mapping[str, Any],
    *,
    active: int,
    references: int,
    formula_sha256: str,
    payload_sha256: str,
    q_sequence: list[int],
    generated: int,
    cached: int,
    recipe_sha256: str,
    runtime_artifacts_sha256: str,
    target_timings: Sequence[Mapping[str, Any]],
    target_storage: Sequence[Mapping[str, Any]],
    storage_policy: Mapping[str, Any],
    retained_output_bytes: int,
    lie_plan_switch: bool,
) -> dict[str, Any]:
    executed = generated > 0
    native_execution = {
        "target_order": BLOCK_MAJOR_TARGET_ORDER,
        "q_sequence": (
            list(reversed(q_sequence)) if lie_plan_switch else q_sequence
        ),
        "plan_load_count": len(q_sequence),
        "plan_switch_count": max(0, len(q_sequence) - 1),
        "generated_target_count": generated,
        "cached_target_count": cached,
        "recipe_sha256": recipe_sha256,
        "runtime_artifacts_sha256": runtime_artifacts_sha256,
        "actual_native_arithmetic_executed": executed,
        "source_scale_run": False,
        "target_timings": [dict(value) for value in target_timings],
        "storage_accounting": {
            "classification": (
                "exact_worker_filesystem_bytes_not_proof_evidence"
            ),
            "policy": dict(storage_policy),
            "retained_output_bytes": retained_output_bytes,
            "targets": [dict(value) for value in target_storage],
            "content_addressed_shared_row_inputs": False,
            "streamed_compact_event_resume": True,
            "source_scale_storage_admitted": False,
        },
    }
    body: dict[str, Any] = {
        "schema": RESPONSE_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": WORKER_ALGORITHM_ID,
        "status": "completed",
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "payload_stream_sha256": payload_sha256,
        "active_q_count": active,
        "target_row_reference_count": references,
        "target_roster_formula_sha256": formula_sha256,
        "framed_typed_bundle_count": len(q_sequence),
        "worker_services_executed": {
            "residue_composer": executed,
            "all_character_transform": executed,
            "completed_l_consumer": executed,
            "typed_bundle_replay": True,
            "tmajor_adapter_admission": False,
        },
        "native_execution": native_execution,
        "claims": {
            "cuda_execution_attested": False,
            "completed_l_zero_completeness": False,
            "turing_completeness": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }
    result = dict(body)
    result["response_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("recipe", type=Path)
    result.add_argument("output_root", type=Path)
    result.add_argument("--reverse-output-on-sequence", type=int)
    result.add_argument("--substitute-bundle-on-sequence", type=int)
    result.add_argument("--truncate-frame-on-sequence", type=int)
    result.add_argument("--lie-plan-switch-on-sequence", type=int)
    return result


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        recipe, runtime, runtime_sha256 = load_recipe(args.recipe)
        output_root = args.output_root.resolve()
        if output_root.exists():
            if not output_root.is_dir() or output_root.is_symlink():
                _fail("native plan-switch output root is not a safe directory")
        else:
            output_root.mkdir(parents=True)
        handshake = native_handshake(
            Path(__file__).resolve(),
            launcher_path=Path(sys.argv[0]).resolve(),
            recipe=recipe,
            runtime_artifacts_sha256=runtime_sha256,
        )
        source = sys.stdin.buffer
        output = sys.stdout.buffer
        output.write(canonical_json_bytes(handshake))
        output.flush()
        while raw_request := source.readline(1024 * 1024 + 1):
            request = _canonical_line(
                raw_request, label="native plan-switch request"
            )
            sequence = _integer(
                request.get("sequence_index"),
                "native plan-switch sequence",
                minimum=0,
            )
            active, references, formula_sha, payload_sha = _validate_request(
                request, source
            )
            targets = _target_inputs(
                recipe, sequence=sequence, request=request
            )
            if len(targets) != active:
                _fail("native plan-switch target count differs")
            payloads: list[bytes] = []
            target_timings: list[dict[str, Any]] = []
            target_storage: list[dict[str, Any]] = []
            generated = 0
            for target in targets:
                raw, was_generated, timing, storage = _bundle_raw(
                    recipe=recipe,
                    runtime=runtime,
                    target=target,
                    output_root=output_root,
                )
                payloads.append(raw)
                target_timings.append(timing)
                target_storage.append(storage)
                generated += int(was_generated)
            cached = len(payloads) - generated
            q_sequence = [target["q"] for target in targets]
            transmitted = list(payloads)
            if sequence == args.reverse_output_on_sequence:
                transmitted.reverse()
            if (
                sequence == args.substitute_bundle_on_sequence
                and len(transmitted) >= 2
            ):
                transmitted[1] = transmitted[0]
            output.write(
                canonical_json_bytes(_stream_header(request, len(transmitted)))
            )
            for ordinal, raw in enumerate(transmitted):
                output.write(
                    canonical_json_bytes(
                        _frame_header(request, ordinal=ordinal, raw=raw)
                    )
                )
                output.write(FRAME_LENGTH.pack(len(raw)))
                if (
                    sequence == args.truncate_frame_on_sequence
                    and ordinal == 0
                ):
                    output.write(raw[: len(raw) // 2])
                    output.flush()
                    return 7
                output.write(raw)
            output.write(
                canonical_json_bytes(
                    _response(
                        request,
                        active=active,
                        references=references,
                        formula_sha256=formula_sha,
                        payload_sha256=payload_sha,
                        q_sequence=q_sequence,
                        generated=generated,
                        cached=cached,
                        recipe_sha256=recipe["recipe_sha256"],
                        runtime_artifacts_sha256=runtime_sha256,
                        target_timings=target_timings,
                        target_storage=target_storage,
                        storage_policy=recipe["storage_policy"],
                        retained_output_bytes=_tree_regular_bytes(
                            output_root
                        ),
                        lie_plan_switch=(
                            sequence == args.lie_plan_switch_on_sequence
                        ),
                    )
                )
            )
            output.flush()
    except (
        DirichletTBlockPlanSwitchWorkerError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(
            f"Dirichlet native plan-switch worker error: {error}",
            file=sys.stderr,
        )
        return 2
    return 0


__all__ = [
    "DEFAULT_MAXIMUM_EVENT_BYTES_PER_TARGET",
    "DEFAULT_MAXIMUM_RETAINED_OUTPUT_BYTES",
    "EXPECTED_PYTHON_FLINT",
    "RECIPE_SCHEMA",
    "artifact_record",
    "load_recipe",
    "native_handshake",
    "run",
    "runtime_artifact_record",
    "write_recipe",
]
