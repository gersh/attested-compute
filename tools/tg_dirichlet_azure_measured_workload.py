#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured full-source CPU fallback for Platt's Dirichlet Theorem 7.1.

The workload consumes a complete retained PT21 q=1 campaign and computes the
q=2..400000 source range with the rigorous FLINT/Arb contour backend.  This is
a correctness-oriented fallback, not the fast algorithm reported by Platt.
It emits ``true`` only after both source branches are complete and replayable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation", ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive, extract_archive  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    canonical_sha256,
    hash_file_once,
    load_json,
    read_bytes_once,
    require_azure_measured_worker,
)
from tg_verifier.dirichlet_campaign import (  # noqa: E402
    FULL_SOURCE_CHARACTER_COUNT,
    SOURCE_MAX_Q,
    SOURCE_MIN_Q,
    DirichletCampaignError,
    finalize_campaign,
    initialize_campaign,
    rerun_external_checkers,
    run_campaign,
    verify_campaign,
)
from tg_verifier import dirichlet_booker_smallq_compact_v3 as smallq_compact  # noqa: E402
from tg_verifier import dirichlet_booker_smallq_packed_stream_v1 as smallq_packed  # noqa: E402
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact_v3  # noqa: E402
from tg_verifier.dirichlet_booker_smallq_compact_v3 import (  # noqa: E402
    SmallQCompactV3Error,
    load_pinset as load_smallq_pinset,
)
from tg_verifier.dirichlet_booker_smallq_packed_stream_v1 import (  # noqa: E402
    PACKER_ALGORITHM_ID as SMALLQ_PACKER_ALGORITHM_ID,
    RECEIPT_SCHEMA as SMALLQ_PACKED_RECEIPT_SCHEMA,
    REDUCER_ALGORITHM_ID as SMALLQ_REDUCER_ALGORITHM_ID,
    SmallQPackedStreamV1Error,
    reduce_packed_stream_to_compact_v3,
)
from tg_verifier.dirichlet_compact_state_streaming_v3 import (  # noqa: E402
    DirichletCompactStateV3Error,
)
from tg_verifier.platt_zeta_campaign import (  # noqa: E402
    ATOM as Q1_ATOM,
    FINAL_SCHEMA as Q1_FINAL_SCHEMA,
    SOURCE_COUNT as Q1_SOURCE_COUNT,
    SOURCE_HEIGHT as Q1_SOURCE_HEIGHT,
    PlattZetaCampaignError,
    campaign_status as q1_campaign_status,
)
from tg_verifier.python_flint_runtime import (  # noqa: E402
    PythonFlintRuntimeError,
    extract_verified_wheel,
    load_pin as load_python_flint_pin,
    verify_wheel,
)
from generate_trusted_compute_lean import (  # noqa: E402
    ReceiptError,
    load_verified_receipt,
    require_production_verifier,
    validate_registered_invocation,
)
import verify_run_bundle  # noqa: E402


REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.v1"
)
REGISTERED_INPUT = (
    b'{"campaign":"platt-dirichlet-theorem-7-1",'
    b'"q1_source_campaign":"platt-trudgian-rh-3e12",'
    b'"q2_to_q400000_primitive_character_count":29565923837,'
    b'"source_modulus_lower":1,"source_modulus_upper":400000}'
)
REGISTERED_RESULT = b"true"
TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_ITERATIONS = 4
POSTCHECK_TRACE_KIND = TRACE_KIND
POSTCHECK_TRACE_ITERATIONS = 4
INITIAL_DOMAIN = b"sparkinterval.dirichlet-measured-trace.initial.v1\n"
STEP_DOMAIN = b"sparkinterval.dirichlet-measured-trace.step.v1\n"
POSTCHECK_INITIAL_DOMAIN = b"sparkinterval.dirichlet-postcheck-trace.initial.v1\n"
POSTCHECK_STEP_DOMAIN = b"sparkinterval.dirichlet-postcheck-trace.step.v1\n"
RETAINED_KIND = "sparkinterval.azure.dirichlet-fallback-retained.v1"
SOURCE_FINAL_KIND = "sparkinterval.azure.dirichlet-source-composition.v1"
CHARACTERS_PER_CHUNK = 1_000_000
MAX_Q1_FILES = 5_000_000
MAX_Q1_BYTES = 16 * 1024**4
MAX_Q2_FILES = 1_000_000
MAX_Q2_BYTES = 16 * 1024**4
MAX_PREDECESSOR_FILES = 2_000_000
# The common CPU operator currently enforces this same returned-package cap.
MAX_PREDECESSOR_BYTES = 256 * 1024**3
SOURCE_REGISTERED_INVOCATION = "plattDirichletTheorem71ProductionV1"
Q1_REGISTERED_INVOCATION = "plattTrudgianFiniteRHProductionV1"
PREDECESSOR_REQUIRED_PATHS = {
    "bundle": Path("bundle-root/run-bundle.json"),
    "statement": Path("bundle-root/runner/statement.json"),
    "trace": Path("bundle-root/output/work-trace.json"),
    "output": Path("bundle-root/output/registered-result.txt"),
    "retained": Path(
        "bundle-root/work/platt-dirichlet-theorem-7-1/dirichlet-retained.tar"
    ),
    "q1_archive": Path("bundle-root/inputs/platt-trudgian-rh-3e12.tar"),
    "q1_receipt": Path(
        "bundle-root/inputs/platt-trudgian-rh-3e12-receipt.json"
    ),
}

# The optimized small-q route is an operational phase.  It intentionally has
# no registered Lean invocation and cannot emit the theorem-producing literal
# ``true``.  A production-classified predecessor receipt must authenticate the
# exact runner, source, reducer, plan, batch, control, and pinset manifest.
PACKED_PHASE_ALGORITHM_ID = (
    "sparkinterval.tg.dirichlet.smallq-packed-compact-phase.v1"
)
PACKED_PHASE_ALGORITHM_DEFINITION = (
    "sparkinterval.azure-operational-algorithm.v1\n"
    "campaign=platt-dirichlet-theorem-7-1\n"
    "phase=smallq-packed-compact-v1\n"
    "transport=TGDBSPK1-to-TGDCSB03\n"
    "packing-location=manifest-bound\n"
    "output=canonical-operational-result-with-retained-compact-state\n"
    "source-admission=false"
)
PACKED_PREDECESSOR_ALGORITHM_ID = (
    "sparkinterval.tg.dirichlet.smallq-packed-input-closure.v1"
)
PACKED_PREDECESSOR_ALGORITHM_DEFINITION = (
    "sparkinterval.azure-operational-algorithm.v1\n"
    "campaign=platt-dirichlet-theorem-7-1\n"
    "phase=smallq-packed-input-closure-v1\n"
    "semantics=reviewed-runner-source-and-exact-plan-batch-control-pinset-roster\n"
    "output=canonical-input-closure-binding"
)
PACKED_INPUT_KIND = "sparkinterval.azure.dirichlet-smallq-packed-inputs.v1"
PACKED_PREDECESSOR_RESULT_KIND = (
    "sparkinterval.azure.dirichlet-smallq-packed-input-authentication.v1"
)
PACKED_RESULT_KIND = (
    "sparkinterval.azure.dirichlet-smallq-packed-operational-result.v1"
)
PACKED_TRACE_KIND = TRACE_KIND
PACKED_TRACE_ITERATIONS = 4
PACKED_INITIAL_DOMAIN = (
    b"sparkinterval.dirichlet-smallq-packed-trace.initial.v1\n"
)
PACKED_STEP_DOMAIN = (
    b"sparkinterval.dirichlet-smallq-packed-trace.step.v1\n"
)
PACKING_MODE = "tgdbspk1_strict_sign_v1"
HOST_PACKING_LOCATION = "runner_host_after_full_disk_d2h_v1"
DEVICE_PACKING_LOCATION = "runner_device_after_full_dft_before_d2h_v1"
SUPPORTED_PACKING_LOCATIONS = frozenset(
    {HOST_PACKING_LOCATION, DEVICE_PACKING_LOCATION}
)
# The transport reducer names its wire mode independently of the operational
# manifest.  Keep the translation explicit and closed: adding a device-packed
# producer requires a reviewed manifest location and a deliberate new entry.
PACKED_REDUCER_LOCATION_BY_MANIFEST = {
    HOST_PACKING_LOCATION: "host",
    DEVICE_PACKING_LOCATION: "device",
}
PACKED_RUNNER_OPTION_BY_MANIFEST = {
    HOST_PACKING_LOCATION: "--strict-sign-packed",
    DEVICE_PACKING_LOCATION: "--strict-sign-packed-device",
}
PACKED_RUNNER_REPORT_ID_BY_MANIFEST = {
    HOST_PACKING_LOCATION: SMALLQ_PACKER_ALGORITHM_ID,
    DEVICE_PACKING_LOCATION: (
        "platt-booker-smallq-runner-strict-sign-pack-device-v1"
    ),
}
PACKED_WIRE_MODE_BY_MANIFEST = {
    HOST_PACKING_LOCATION: smallq_packed.HOST_PRODUCTION_MODE,
    DEVICE_PACKING_LOCATION: smallq_packed.DEVICE_PRODUCTION_MODE,
}
PACKED_ALLOWED_PREDECESSOR_BACKENDS = frozenset(
    {"azure_ncc40ads_h100_v5", "azure_sevsnp_cpu"}
)
PACKED_MAXIMUM_MANIFEST_BYTES = 16 * 1024 * 1024
PACKED_MAXIMUM_RESULT_BYTES = 1024 * 1024
PACKED_MAXIMUM_BATCH_COUNT = 1 << 16
PACKED_DEFAULT_RUNNER_TIMEOUT_SECONDS = 6 * 24 * 60 * 60


class DirichletMeasuredWorkloadError(RuntimeError):
    pass


def _hex(value: Any, what: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise DirichletMeasuredWorkloadError(f"{what} is not lowercase SHA-256")
    return value


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as error:
        raise DirichletMeasuredWorkloadError(f"cannot read {what}: {error}") from error


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o400)
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        path.unlink(missing_ok=True)
        raise DirichletMeasuredWorkloadError(
            f"cannot create immutable output {path}: {error}"
        ) from error


def _load_canonical(path: Path, what: str) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as error:
        raise DirichletMeasuredWorkloadError(f"cannot load {what}: {error}") from error
    if not isinstance(value, dict):
        raise DirichletMeasuredWorkloadError(f"{what} is not an object")
    return value


def _exact_fields(
    value: Any, expected: set[str], what: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise DirichletMeasuredWorkloadError(
            f"{what} fields differ "
            f"(missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)})"
        )
    return value


def _plain_int(value: Any, what: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DirichletMeasuredWorkloadError(
            f"{what} must be an integer >= {minimum}"
        )
    return value


def _stat_identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        getattr(status, "st_mtime_ns", int(status.st_mtime * 1_000_000_000)),
        getattr(status, "st_ctime_ns", int(status.st_ctime * 1_000_000_000)),
    )


def _regular_record(
    path: Path,
    what: str,
    *,
    executable: bool = False,
    maximum: int | None = None,
) -> tuple[dict[str, Any], tuple[int, ...]]:
    try:
        before = path.lstat()
    except OSError as error:
        raise DirichletMeasuredWorkloadError(
            f"cannot stat {what}: {error}"
        ) from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise DirichletMeasuredWorkloadError(
            f"{what} must be one nonsymbolic, singly linked regular file"
        )
    if executable and not os.access(path, os.X_OK):
        raise DirichletMeasuredWorkloadError(f"{what} is not executable")
    try:
        digest, size = hash_file_once(path, limit=maximum)
        after = path.lstat()
    except (CampaignIOError, OSError) as error:
        raise DirichletMeasuredWorkloadError(
            f"cannot hash {what}: {error}"
        ) from error
    identity = _stat_identity(before)
    if _stat_identity(after) != identity or size != before.st_size:
        raise DirichletMeasuredWorkloadError(f"{what} changed while hashed")
    return {"sha256": digest, "size_bytes": size}, identity


def _restate_regular(
    path: Path,
    record: Mapping[str, Any],
    identity: tuple[int, ...],
    what: str,
) -> None:
    observed, final_identity = _regular_record(path, what)
    if dict(record) != observed or final_identity != identity:
        raise DirichletMeasuredWorkloadError(
            f"{what} changed during the measured packed phase"
        )


def _packed_batches(directory: Path) -> tuple[Path, ...]:
    try:
        status = directory.lstat()
    except OSError as error:
        raise DirichletMeasuredWorkloadError(
            f"cannot stat packed batch directory: {error}"
        ) from error
    if directory.is_symlink() or not stat.S_ISDIR(status.st_mode):
        raise DirichletMeasuredWorkloadError(
            "packed batch directory must be a nonsymbolic directory"
        )
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise DirichletMeasuredWorkloadError(
            f"cannot enumerate packed batch directory: {error}"
        ) from error
    if (
        not entries
        or len(entries) > PACKED_MAXIMUM_BATCH_COUNT
        or any(
            not path.name.startswith("batch-")
            or path.suffix != ".bin"
            for path in entries
        )
    ):
        raise DirichletMeasuredWorkloadError(
            "packed batch directory is not one bounded batch-*.bin roster"
        )
    return tuple(entries)


def _packed_artifacts(
    args: argparse.Namespace,
) -> tuple[
    dict[str, Any],
    dict[Path, tuple[dict[str, Any], tuple[int, ...], str]],
    tuple[Path, ...],
]:
    batches = _packed_batches(args.batch_directory)
    paths: dict[str, tuple[Path, bool, int | None]] = {
        "runner": (args.runner, True, 8 * 1024**3),
        "runner_source": (args.runner_source, False, 64 * 1024**2),
        "packed_reducer_source": (
            ROOT / "tg_verifier/dirichlet_booker_smallq_packed_stream_v1.py",
            False,
            16 * 1024**2,
        ),
        "compact_reducer_source": (
            ROOT / "tg_verifier/dirichlet_compact_state_streaming_v3.py",
            False,
            32 * 1024**2,
        ),
        "measured_workload_source": (Path(__file__), False, 16 * 1024**2),
        "plan": (args.plan, False, 16 * 1024**3),
        "control": (args.control, False, 1024 * 1024**3),
        "control_receipt": (
            args.control_receipt,
            False,
            16 * 1024**2,
        ),
        "pinset": (args.pinset, False, 1024 * 1024),
    }
    records: dict[Path, tuple[dict[str, Any], tuple[int, ...], str]] = {}
    artifacts: dict[str, Any] = {}
    for role, (path, executable, maximum) in paths.items():
        record, identity = _regular_record(
            path, f"packed {role}", executable=executable, maximum=maximum
        )
        artifacts[role] = record
        records[path] = (record, identity, f"packed {role}")
    batch_rows: list[dict[str, Any]] = []
    for path in batches:
        record, identity = _regular_record(
            path, f"packed batch {path.name}", maximum=16 * 1024**3
        )
        row = {"name": path.name, **record}
        batch_rows.append(row)
        records[path] = (record, identity, f"packed batch {path.name}")
    artifacts["batches"] = batch_rows
    resolved = [path.resolve() for path in records]
    if len(set(resolved)) != len(resolved):
        raise DirichletMeasuredWorkloadError(
            "packed phase inputs contain aliased paths"
        )
    return artifacts, records, batches


def _packed_predecessor_result(
    manifest: Mapping[str, Any], manifest_sha256: str,
) -> dict[str, Any]:
    artifacts = manifest["artifacts"]
    return {
        "artifact_roster_sha256": manifest["artifact_roster_sha256"],
        "compact_source_binding_sha256": manifest[
            "compact_source_binding_sha256"
        ],
        "dft_arithmetic_containment_realized": False,
        "input_manifest_sha256": manifest_sha256,
        "kind": PACKED_PREDECESSOR_RESULT_KIND,
        "packing_location": manifest["packing_location"],
        "packing_mode": manifest["packing_mode"],
        "pinset_sha256": manifest["pinset_sha256"],
        "production_ready": False,
        "q": manifest["q"],
        "runner_sha256": artifacts["runner"]["sha256"],
        "runner_source_sha256": artifacts["runner_source"]["sha256"],
        "schema_version": 1,
        "source_admission_enabled": False,
    }


def _verify_packed_predecessor_receipt(
    path: Path,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
) -> dict[str, Any]:
    key_manifest = ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
    try:
        receipt = load_verified_receipt(
            path,
            key_manifest=key_manifest,
            allow_development_key=False,
        )
        require_production_verifier(receipt, key_manifest)
    except ReceiptError as error:
        raise DirichletMeasuredWorkloadError(
            f"packed predecessor receipt failed production verification: {error}"
        ) from error
    claim = receipt.get("claim")
    if not isinstance(claim, Mapping):
        raise DirichletMeasuredWorkloadError(
            "packed predecessor receipt has no claim"
        )
    expected = _packed_predecessor_result(manifest, manifest_sha256)
    expected_raw = canonical_json_bytes(expected)
    result = claim.get("result")
    if (
        receipt.get("backend") not in PACKED_ALLOWED_PREDECESSOR_BACKENDS
        or claim.get("algorithm_id") != PACKED_PREDECESSOR_ALGORITHM_ID
        or claim.get("algorithm_hash")
        != hashlib.sha256(
            PACKED_PREDECESSOR_ALGORITHM_DEFINITION.encode("utf-8")
        ).hexdigest()
        or claim.get("completion") != "successful"
        or claim.get("input_hash") != manifest_sha256
        or not isinstance(result, str)
        or result.encode("utf-8") != expected_raw
        or claim.get("output_hash") != hashlib.sha256(expected_raw).hexdigest()
    ):
        raise DirichletMeasuredWorkloadError(
            "packed predecessor receipt does not authenticate the exact "
            "reviewed input closure"
        )
    receipt_file_sha256, receipt_file_size = hash_file_once(
        path, limit=16 * 1024**2
    )
    return {
        "backend": receipt["backend"],
        "receipt_file_sha256": receipt_file_sha256,
        "receipt_file_size_bytes": receipt_file_size,
        "receipt_sha256": _hex(
            receipt.get("receipt_sha256"),
            "packed predecessor receipt self hash",
        ),
        "verifier_key_id": receipt["verifier"]["key_id"],
    }


def _load_packed_inputs(
    args: argparse.Namespace,
) -> dict[str, Any]:
    manifest = _load_canonical(args.input, "packed input manifest")
    manifest_fields = {
        "artifact_roster_sha256",
        "artifacts",
        "compact_source_binding_sha256",
        "dft_arithmetic_containment_realized",
        "full_source_span",
        "kind",
        "packing_location",
        "packing_mode",
        "pinset_sha256",
        "production_ready",
        "q",
        "schema_version",
        "source_admission_enabled",
        "structural_bounded_span_kat",
    }
    _exact_fields(manifest, manifest_fields, "packed input manifest")
    if (
        manifest["kind"] != PACKED_INPUT_KIND
        or manifest["schema_version"] != 1
        or manifest["packing_mode"] != PACKING_MODE
        or manifest["packing_location"] not in SUPPORTED_PACKING_LOCATIONS
        or manifest["full_source_span"] is not True
        or manifest["structural_bounded_span_kat"] is not False
        or manifest["dft_arithmetic_containment_realized"] is not False
        or manifest["source_admission_enabled"] is not False
        or manifest["production_ready"] is not False
    ):
        raise DirichletMeasuredWorkloadError(
            "packed input manifest mode, span, or admission classification differs"
        )
    q = _plain_int(manifest["q"], "packed input q", minimum=2)
    pinset_sha256 = _hex(
        manifest["pinset_sha256"], "packed input pinset SHA-256"
    )
    source_binding = _hex(
        manifest["compact_source_binding_sha256"],
        "packed input source binding SHA-256",
    )
    artifact_roster = _hex(
        manifest["artifact_roster_sha256"],
        "packed input artifact roster SHA-256",
    )
    manifest_sha256, manifest_size = hash_file_once(
        args.input, limit=PACKED_MAXIMUM_MANIFEST_BYTES
    )
    artifacts, snapshots, batches = _packed_artifacts(args)
    if (
        manifest["artifacts"] != artifacts
        or artifact_roster != canonical_sha256(artifacts)
    ):
        raise DirichletMeasuredWorkloadError(
            "packed input artifacts differ from the authenticated manifest"
        )
    pins = load_smallq_pinset(
        args.pinset, expected_pinset_sha256=pinset_sha256
    )
    if (
        pins.q != q
        or pins.structural_bounded_span_kat
        or smallq_compact._source_binding_sha256(pins) != source_binding
    ):
        raise DirichletMeasuredWorkloadError(
            "packed typed pinset differs from the production manifest"
        )
    # This repeats the reducer's complete plan/batch/control/roster preflight
    # before any reviewed runner byte executes.
    prepared = smallq_packed._prepare(
        args.plan,
        batches,
        args.control,
        args.control_receipt,
        pins,
    )
    if (
        prepared.plan.q != q
        or prepared.source_binding != source_binding
        or prepared.pins != pins
    ):
        raise DirichletMeasuredWorkloadError(
            "packed preflight differs from the authenticated source binding"
        )
    predecessor = _verify_packed_predecessor_receipt(
        args.predecessor_receipt, manifest, manifest_sha256
    )
    return {
        "artifact_roster_sha256": artifact_roster,
        "artifacts": artifacts,
        "batches": batches,
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "manifest_size_bytes": manifest_size,
        "pins": pins,
        "prepared": prepared,
        "predecessor": predecessor,
        "q": q,
        "snapshots": snapshots,
        "source_binding_sha256": source_binding,
    }


def _tree_identity(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256(b"sparkinterval/dirichlet-retained-tree/v1\0")
    files = 0
    size = 0
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise DirichletMeasuredWorkloadError(
                "retained campaign contains a linked or special file"
            )
        relative = path.relative_to(root).as_posix().encode("utf-8")
        file_hash, file_size = hash_file_once(path)
        files += 1
        size += file_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(file_size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(file_hash))
    if files == 0:
        raise DirichletMeasuredWorkloadError("retained campaign is empty")
    return {"file_count": files, "size_bytes": size, "tree_sha256": digest.hexdigest()}


def _activate_runtime(wheel: Path, destination: Path) -> dict[str, Any]:
    pin = load_python_flint_pin(ROOT / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json")
    identity = extract_verified_wheel(wheel, destination, pin)
    sys.path.insert(0, str(destination))
    os.environ["PYTHONPATH"] = str(destination)
    try:
        import flint  # type: ignore

        versions = (
            str(flint.__version__),
            str(flint.__FLINT_VERSION__),
            int(flint.__FLINT_RELEASE__),
        )
    except (ImportError, AttributeError, OSError, ValueError) as error:
        raise DirichletMeasuredWorkloadError(
            f"cannot load pinned python-flint runtime: {error}"
        ) from error
    if versions != ("0.9.0", "3.6.0", 30_600):
        raise DirichletMeasuredWorkloadError("loaded FLINT runtime version differs")
    return identity


def _verify_q1(root: Path) -> dict[str, Any]:
    status = q1_campaign_status(root)
    if not (
        status["mode"] == "full_source"
        and status["complete"] is True
        and status["final_ready"] is True
    ):
        raise DirichletMeasuredWorkloadError("q=1 PT21 campaign is not complete")
    final = _load_canonical(root / "final.json", "q=1 final artifact")
    if (
        final.get("schema") != Q1_FINAL_SCHEMA
        or final.get("atom") != Q1_ATOM
        or final.get("height") != Q1_SOURCE_HEIGHT
        or final.get("multiplicity_count") != Q1_SOURCE_COUNT
        or final.get("zero_multiplicity_preserved") is not True
        or final.get("simplicity_assumed") is not False
        or final.get("receipt_merkle_root_sha256") != status["merkle_root_sha256"]
    ):
        raise DirichletMeasuredWorkloadError("q=1 PT21 final identity differs")
    return {
        "atom": Q1_ATOM,
        "height": Q1_SOURCE_HEIGHT,
        "multiplicity_count": Q1_SOURCE_COUNT,
        "plan_sha256": status["plan_sha256"],
        "receipt_merkle_root_sha256": status["merkle_root_sha256"],
    }


def _verified_production_receipt(
    path: Path, invocation: str, what: str,
) -> dict[str, Any]:
    key_manifest = ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
    try:
        receipt = load_verified_receipt(
            path,
            key_manifest=key_manifest,
            allow_development_key=False,
        )
        require_production_verifier(receipt, key_manifest)
        validate_registered_invocation(receipt, invocation)
    except ReceiptError as error:
        raise DirichletMeasuredWorkloadError(
            f"{what} failed production verification: {error}"
        ) from error
    if receipt["claim"]["result"] != "true":
        raise DirichletMeasuredWorkloadError(
            f"{what} does not bind literal true"
        )
    return receipt


def _verify_q1_receipt(path: Path) -> dict[str, Any]:
    receipt = _verified_production_receipt(
        path, Q1_REGISTERED_INVOCATION, "q=1 trusted receipt"
    )
    return {
        "receipt_sha256": receipt["receipt_sha256"],
        "registered_invocation": Q1_REGISTERED_INVOCATION,
        "verifier_key_id": receipt["verifier"]["key_id"],
    }


def _source_final(q1: dict[str, Any], q2: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": SOURCE_FINAL_KIND,
        "schema_version": 1,
        "classification": "complete_q1_pt21_plus_q2_dirichlet_flint_fallback",
        "q1": q1,
        "q2_to_q400000": {
            "characters_covered": q2["characters_covered"],
            "coverage_class": q2["coverage_class"],
            "schedule_sha256": q2["schedule_sha256"],
            "terminal_chain_sha256": q2["terminal_chain_sha256"],
        },
        "source_modulus_lower": 1,
        "source_modulus_upper": SOURCE_MAX_Q,
        "primitive_character_count_q2_to_q400000": FULL_SOURCE_CHARACTER_COUNT,
        "parity_branches": ["even", "odd"],
        "lean_atom_discharged": False,
    }


def _trace_hash(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    q1_archive_sha256: str,
    q1_receipt_sha256: str,
    retained_archive_sha256: str,
    retained_tree_sha256: str,
    source_final_sha256: str,
    result_sha256: str,
) -> str:
    state = hashlib.sha256(
        INITIAL_DOMAIN
        + bytes.fromhex(challenge)
        + bytes.fromhex(job_binding)
        + bytes.fromhex(input_sha256)
    ).digest()
    for fields in (
        (q1_archive_sha256, q1_receipt_sha256),
        (retained_archive_sha256, retained_tree_sha256),
        (source_final_sha256,),
        (result_sha256,),
    ):
        state = hashlib.sha256(
            STEP_DOMAIN + state + b"".join(bytes.fromhex(field) for field in fields)
        ).digest()
    return state.hex()


def _source_trace(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    q1_archive_sha256: str,
    q1_receipt_sha256: str,
    retained_archive_sha256: str,
    retained_tree_sha256: str,
    source_final_sha256: str,
) -> dict[str, Any]:
    result_sha256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
    return {
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "challenge_nonce": challenge,
        "input_sha256": input_sha256,
        "iteration_count": TRACE_ITERATIONS,
        "job_binding_sha256": job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": _trace_hash(
            challenge=challenge,
            job_binding=job_binding,
            input_sha256=input_sha256,
            q1_archive_sha256=q1_archive_sha256,
            q1_receipt_sha256=q1_receipt_sha256,
            retained_archive_sha256=retained_archive_sha256,
            retained_tree_sha256=retained_tree_sha256,
            source_final_sha256=source_final_sha256,
            result_sha256=result_sha256,
        ),
    }


def _postcheck_trace_hash(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    predecessor_certificate_sha256: str,
    predecessor_receipt_file_sha256: str,
    predecessor_receipt_sha256: str,
    predecessor_statement_sha256: str,
    predecessor_source_trace_sha256: str,
    q1_archive_sha256: str,
    q1_receipt_sha256: str,
    retained_archive_sha256: str,
    retained_tree_sha256: str,
    source_final_sha256: str,
    result_sha256: str,
) -> str:
    state = hashlib.sha256(
        POSTCHECK_INITIAL_DOMAIN
        + bytes.fromhex(challenge)
        + bytes.fromhex(job_binding)
        + bytes.fromhex(input_sha256)
    ).digest()
    for fields in (
        (
            predecessor_certificate_sha256,
            predecessor_receipt_file_sha256,
            predecessor_receipt_sha256,
        ),
        (
            predecessor_statement_sha256,
            predecessor_source_trace_sha256,
            q1_archive_sha256,
            q1_receipt_sha256,
        ),
        (
            retained_archive_sha256,
            retained_tree_sha256,
            source_final_sha256,
        ),
        (result_sha256,),
    ):
        state = hashlib.sha256(
            POSTCHECK_STEP_DOMAIN
            + state
            + b"".join(bytes.fromhex(field) for field in fields)
        ).digest()
    return state.hex()


def _source_trace_header_identity(
    trace: dict[str, Any],
    *,
    statement: dict[str, Any],
) -> str:
    expected_fields = {
        "algorithm_id", "challenge_nonce", "input_sha256", "iteration_count",
        "job_binding_sha256", "kind", "result_sha256", "schema_version",
        "trace_sha256",
    }
    if set(trace) != expected_fields:
        raise DirichletMeasuredWorkloadError(
            "predecessor source trace fields differ"
        )
    environment = statement.get("execution_environment", {}).get("value")
    input_record = statement.get("input_artifact")
    if not isinstance(environment, dict) or not isinstance(input_record, dict):
        raise DirichletMeasuredWorkloadError(
            "predecessor statement lacks bound execution identity"
        )
    result_sha256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
    for field in (
        "challenge_nonce", "input_sha256", "job_binding_sha256",
        "result_sha256", "trace_sha256",
    ):
        _hex(trace.get(field), f"predecessor source trace {field}")
    if (
        trace["kind"] != TRACE_KIND
        or trace["schema_version"] != 1
        or trace["algorithm_id"] != REGISTERED_ALGORITHM_ID
        or trace["iteration_count"] != TRACE_ITERATIONS
        or trace["challenge_nonce"] != statement.get("nonce")
        or trace["input_sha256"] != input_record.get("sha256")
        or trace["job_binding_sha256"] != environment.get("job_binding_sha256")
        or trace["result_sha256"] != result_sha256
    ):
        raise DirichletMeasuredWorkloadError(
            "predecessor source trace identity differs"
        )
    return result_sha256


def _source_trace_identity(
    trace: dict[str, Any],
    *,
    statement: dict[str, Any],
    q1_archive_sha256: str,
    q1_receipt_sha256: str,
    retained_archive_sha256: str,
    retained_tree_sha256: str,
    source_final_sha256: str,
) -> None:
    result_sha256 = _source_trace_header_identity(
        trace, statement=statement
    )
    for value, what in (
        (q1_archive_sha256, "predecessor q=1 archive hash"),
        (q1_receipt_sha256, "predecessor q=1 receipt hash"),
        (retained_archive_sha256, "predecessor retained archive hash"),
        (retained_tree_sha256, "predecessor retained tree hash"),
        (source_final_sha256, "predecessor source composition hash"),
    ):
        _hex(value, what)
    expected_chain = _trace_hash(
        challenge=trace["challenge_nonce"],
        job_binding=trace["job_binding_sha256"],
        input_sha256=trace["input_sha256"],
        q1_archive_sha256=q1_archive_sha256,
        q1_receipt_sha256=q1_receipt_sha256,
        retained_archive_sha256=retained_archive_sha256,
        retained_tree_sha256=retained_tree_sha256,
        source_final_sha256=source_final_sha256,
        result_sha256=result_sha256,
    )
    if trace["trace_sha256"] != expected_chain:
        raise DirichletMeasuredWorkloadError(
            "predecessor source trace chain differs"
        )


def _statement_matches_receipt(
    statement: dict[str, Any], receipt: dict[str, Any]
) -> None:
    claim = receipt["claim"]
    algorithm = statement.get("algorithm")
    parameters = statement.get("parameters")
    domain = statement.get("domain_coverage")
    input_record = statement.get("input_artifact")
    output_record = statement.get("output_artifact")
    target = statement.get("target_profile")
    trust = statement.get("trust_profile")
    completion = statement.get("completion")
    if not all(
        isinstance(value, dict)
        for value in (
            algorithm, parameters, domain, input_record, output_record,
            target, trust, completion,
        )
    ):
        raise DirichletMeasuredWorkloadError(
            "predecessor statement lacks registered receipt fields"
        )
    if (
        statement.get("nonce") != claim["nonce"]
        or algorithm.get("algorithm_id") != claim["algorithm_id"]
        or algorithm.get("definition_sha256") != claim["algorithm_hash"]
        or parameters.get("canonical_sha256") != claim["parameters_hash"]
        or domain.get("canonical_sha256") != claim["domain_hash"]
        or input_record.get("sha256") != claim["input_hash"]
        or output_record.get("sha256") != claim["output_hash"]
        or target.get("sha256") != claim["target_profile_hash"]
        or trust.get("sha256") != claim["trust_profile_hash"]
        or completion.get("status") != "success"
        or claim["completion"] != "successful"
    ):
        raise DirichletMeasuredWorkloadError(
            "predecessor statement and signed registered claim differ"
        )


def _load_predecessor(
    certificate_archive: Path,
    receipt_path: Path,
    destination: Path,
) -> dict[str, Any]:
    """Authenticate and unpack the exact source-job snapshot.

    The retained archive is not accepted merely because it appeared beside a
    signed Boolean.  The production receipt binds the run bundle and statement;
    the statement binds the source trace; and the source trace binds q=1, the
    retained q>=2 archive/tree, the source composition, and literal ``true``.
    """

    source_receipt = _verified_production_receipt(
        receipt_path,
        SOURCE_REGISTERED_INVOCATION,
        "predecessor source trusted receipt",
    )
    certificate_sha256, _certificate_size = hash_file_once(certificate_archive)
    receipt_file_sha256, _receipt_size = hash_file_once(receipt_path)
    extract_archive(
        certificate_archive,
        destination,
        maximum_files=MAX_PREDECESSOR_FILES,
        maximum_bytes=MAX_PREDECESSOR_BYTES,
    )
    paths = {
        key: destination / relative
        for key, relative in PREDECESSOR_REQUIRED_PATHS.items()
    }
    for key, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise DirichletMeasuredWorkloadError(
                f"predecessor certificate lacks regular {key} artifact"
            )

    bundle = _load_canonical(paths["bundle"], "predecessor run bundle")
    run_root = destination / "bundle-root"
    try:
        checked = verify_run_bundle.verify_bundle(
            bundle,
            profiles_dir=ROOT / "profiles",
            artifact_root=run_root,
        )
    except verify_run_bundle.VerificationError as error:
        raise DirichletMeasuredWorkloadError(
            f"predecessor run bundle failed integrity verification: {error}"
        ) from error
    if checked.get("artifacts_verified") is not True:
        raise DirichletMeasuredWorkloadError(
            "predecessor run bundle did not verify its artifact bytes"
        )
    bindings = source_receipt["bindings"]
    if (
        checked.get("bundle_sha256") != bindings["run_bundle_sha256"]
        or checked.get("statement_sha256")
        != bindings["wire_statement_sha256"]
    ):
        raise DirichletMeasuredWorkloadError(
            "production receipt does not authenticate predecessor bundle"
        )
    statement = bundle.get("statement")
    if not isinstance(statement, dict):
        raise DirichletMeasuredWorkloadError(
            "predecessor bundle statement is not an object"
        )
    statement_copy = _load_canonical(
        paths["statement"], "predecessor runner statement"
    )
    if statement_copy != statement:
        raise DirichletMeasuredWorkloadError(
            "predecessor runner statement differs from signed run bundle"
        )
    _statement_matches_receipt(statement, source_receipt)

    output_raw = _read(paths["output"], 16, "predecessor registered result")
    output_record = statement["output_artifact"]
    result_sha256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
    if (
        output_record.get("path") != "output/registered-result.txt"
        or output_record.get("size_bytes") != len(REGISTERED_RESULT)
        or output_record.get("sha256") != result_sha256
        or source_receipt["claim"]["output_hash"] != result_sha256
        or output_raw != REGISTERED_RESULT
    ):
        raise DirichletMeasuredWorkloadError(
            "predecessor output is not the registered literal true"
        )

    trace = _load_canonical(paths["trace"], "predecessor source trace")
    trace_sha256, _trace_size = hash_file_once(paths["trace"])
    environment = statement.get("execution_environment", {}).get("value")
    if (
        not isinstance(environment, dict)
        or trace_sha256 != environment.get("work_trace_artifact_sha256")
        or trace.get("trace_sha256")
        != environment.get("work_trace_chain_sha256")
    ):
        raise DirichletMeasuredWorkloadError(
            "signed predecessor statement does not authenticate source trace"
        )
    q1_archive_sha256, _q1_size = hash_file_once(paths["q1_archive"])
    q1_receipt_sha256, _q1_receipt_size = hash_file_once(paths["q1_receipt"])
    retained_archive_sha256, _retained_size = hash_file_once(paths["retained"])
    _source_trace_header_identity(trace, statement=statement)
    _verify_q1_receipt(paths["q1_receipt"])
    return {
        "certificate_sha256": certificate_sha256,
        "paths": paths,
        "q1_archive_sha256": q1_archive_sha256,
        "q1_receipt_sha256": q1_receipt_sha256,
        "receipt_file_sha256": receipt_file_sha256,
        "receipt_sha256": source_receipt["receipt_sha256"],
        "retained_archive_sha256": retained_archive_sha256,
        "source_trace": trace,
        "source_trace_sha256": trace_sha256,
        "statement": statement,
        "statement_sha256": checked["statement_sha256"],
    }


def _replay_predecessor(
    certificate_archive: Path,
    receipt_path: Path,
    wheel: Path,
    temporary_root: Path,
) -> dict[str, str]:
    extracted = temporary_root / "predecessor"
    predecessor = _load_predecessor(
        certificate_archive, receipt_path, extracted
    )
    runtime = temporary_root / "python-flint-runtime"
    q1_root = temporary_root / "q1"
    q2_root = temporary_root / "q2"
    _activate_runtime(wheel, runtime)
    extract_archive(
        predecessor["paths"]["q1_archive"],
        q1_root,
        maximum_files=MAX_Q1_FILES,
        maximum_bytes=MAX_Q1_BYTES,
    )
    q1 = _verify_q1(q1_root)
    q1["trusted_compute"] = _verify_q1_receipt(
        predecessor["paths"]["q1_receipt"]
    )
    extract_archive(
        predecessor["paths"]["retained"],
        q2_root,
        maximum_files=MAX_Q2_FILES,
        maximum_bytes=MAX_Q2_BYTES,
    )
    tree = _tree_identity(q2_root)
    source_trace = predecessor["source_trace"]
    state = verify_campaign(q2_root, require_complete=True)
    if not state["final_present"]:
        raise DirichletMeasuredWorkloadError(
            "retained q>=2 campaign has no final artifact"
        )
    # This is a fresh replay over every retained chunk.  Producer and checker
    # are the same pinned reviewed implementation; no independence is claimed.
    rerun_external_checkers(q2_root)
    q2_final = finalize_campaign(q2_root)
    expected_source = canonical_json_bytes(_source_final(q1, q2_final))
    retained_source = _read(
        q2_root / "source-final.json", 1024 * 1024, "source composition"
    )
    source_final_sha256 = hashlib.sha256(retained_source).hexdigest()
    if retained_source != expected_source:
        raise DirichletMeasuredWorkloadError(
            "retained source composition differs after full replay"
        )
    _source_trace_identity(
        source_trace,
        statement=predecessor["statement"],
        q1_archive_sha256=predecessor["q1_archive_sha256"],
        q1_receipt_sha256=predecessor["q1_receipt_sha256"],
        retained_archive_sha256=predecessor["retained_archive_sha256"],
        retained_tree_sha256=tree["tree_sha256"],
        source_final_sha256=source_final_sha256,
    )
    return {
        "predecessor_certificate_sha256": predecessor["certificate_sha256"],
        "predecessor_receipt_file_sha256": predecessor["receipt_file_sha256"],
        "predecessor_receipt_sha256": predecessor["receipt_sha256"],
        "predecessor_statement_sha256": predecessor["statement_sha256"],
        "predecessor_source_trace_sha256": predecessor["source_trace_sha256"],
        "q1_archive_sha256": predecessor["q1_archive_sha256"],
        "q1_receipt_sha256": predecessor["q1_receipt_sha256"],
        "retained_archive_sha256": predecessor["retained_archive_sha256"],
        "retained_tree_sha256": tree["tree_sha256"],
        "source_final_sha256": source_final_sha256,
    }


def _validate_common(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise DirichletMeasuredWorkloadError("algorithm id differs")
    challenge = _hex(args.challenge, "challenge")
    job_binding = _hex(args.job_binding, "job binding")
    input_raw = _read(args.input, 4096, "registered input")
    if input_raw != REGISTERED_INPUT:
        raise DirichletMeasuredWorkloadError("registered input differs")
    verify_wheel(
        args.wheel,
        load_python_flint_pin(ROOT / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json"),
    )
    return challenge, job_binding, hashlib.sha256(input_raw).hexdigest()


def _validate_packed_common(
    args: argparse.Namespace,
) -> tuple[str, str, str, dict[str, Any]]:
    if args.algorithm_id != PACKED_PHASE_ALGORITHM_ID:
        raise DirichletMeasuredWorkloadError(
            "packed operational algorithm id differs"
        )
    challenge = _hex(args.challenge, "challenge")
    job_binding = _hex(args.job_binding, "job binding")
    inputs = _load_packed_inputs(args)
    return challenge, job_binding, inputs["manifest_sha256"], inputs


def _packed_runner_environment() -> dict[str, str]:
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    # These names are part of the measured job environment and are the only
    # inherited CUDA selectors.  The exact resulting map is bound below.
    for name in (
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
        "NVIDIA_VISIBLE_DEVICES",
    ):
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    return environment


def _packed_runner_argv(
    args: argparse.Namespace, inputs: Mapping[str, Any],
) -> list[str]:
    pins = inputs["pins"]
    packing_location = inputs["manifest"]["packing_location"]
    argv = [
        str(args.runner),
        "--source-samples-only",
        PACKED_RUNNER_OPTION_BY_MANIFEST[packing_location],
        str(args.control),
        pins.time_tail_control_receipt_sha256,
        pins.compact_complete_roster_sha256,
        inputs["manifest"]["pinset_sha256"],
        inputs["source_binding_sha256"],
        "--factored-service",
        str(args.plan),
    ]
    for batch in inputs["batches"]:
        argv.extend((str(batch), "-"))
    if len(argv) > 2 * PACKED_MAXIMUM_BATCH_COUNT + 16:
        raise DirichletMeasuredWorkloadError(
            "packed runner argument vector exceeds its reviewed bound"
        )
    return argv


def _packed_runner_report(
    path: Path,
    compact_receipt: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _read(path, 64 * 1024**2, "packed runner stderr")
    packing_location = inputs["manifest"]["packing_location"]
    expected_algorithm = PACKED_RUNNER_REPORT_ID_BY_MANIFEST[
        packing_location
    ]
    strict: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict)
            and value.get("algorithm") == expected_algorithm
        ):
            strict.append(value)
    fields = {
        "algorithm",
        "ambiguous",
        "bytes",
        "classification",
        "control_upload_nanoseconds",
        "device_classification_nanoseconds",
        "device_to_host_bounded_status_bytes",
        "device_to_host_payload_bytes",
        "device_to_host_transfer_nanoseconds",
        "dft_arithmetic_containment_replayed",
        "frames",
        "full_disk_status_array_bytes_not_copied",
        "items",
        "negative",
        "packing_location",
        "packing_mode",
        "positive",
        "production_ready",
        "source_admission_enabled",
        "stream_sha256",
        "turing_closure_realized",
        "zero_multiplicity_realized",
    }
    if len(strict) != 1 or set(strict[0]) != fields:
        raise DirichletMeasuredWorkloadError(
            "packed runner stderr lacks one exact strict-sign summary"
        )
    report = strict[0]
    for field in (
        "ambiguous",
        "bytes",
        "control_upload_nanoseconds",
        "device_classification_nanoseconds",
        "device_to_host_bounded_status_bytes",
        "device_to_host_payload_bytes",
        "device_to_host_transfer_nanoseconds",
        "frames",
        "full_disk_status_array_bytes_not_copied",
        "items",
        "negative",
        "packing_mode",
        "positive",
    ):
        _plain_int(report[field], f"packed runner report {field}")
    prepared = inputs["prepared"]
    expected_payload_bytes = sum(
        (len(batch.characters) * prepared.sample_count + 3) // 4
        for batch in prepared.batches
    )
    expected_full_array_bytes = sum(
        len(batch.characters) * prepared.plan.transform_length * 28
        for batch in prepared.batches
    )
    device_mode = packing_location == DEVICE_PACKING_LOCATION
    if (
        report["classification"] != "transport_not_source_or_dft_replay"
        or report["packing_location"]
        != PACKED_REDUCER_LOCATION_BY_MANIFEST[packing_location]
        or report["packing_mode"]
        != PACKED_WIRE_MODE_BY_MANIFEST[packing_location]
        or report["frames"] != compact_receipt["frame_count"]
        or report["items"] != compact_receipt["item_count"]
        or report["ambiguous"] != compact_receipt["ambiguous_sample_count"]
        or report["negative"] != compact_receipt["negative_sample_count"]
        or report["positive"] != compact_receipt["positive_sample_count"]
        or report["bytes"]
        != compact_receipt["packed_stream_bytes_consumed"]
        or report["stream_sha256"]
        != compact_receipt["packed_stream_sha256_receipt_only"]
        or report["dft_arithmetic_containment_replayed"] is not False
        or report["zero_multiplicity_realized"] is not False
        or report["turing_closure_realized"] is not False
        or report["source_admission_enabled"] is not False
        or report["production_ready"] is not False
        or (
            not device_mode
            and any(
                report[field] != 0
                for field in (
                    "control_upload_nanoseconds",
                    "device_classification_nanoseconds",
                    "device_to_host_bounded_status_bytes",
                    "device_to_host_payload_bytes",
                    "device_to_host_transfer_nanoseconds",
                    "full_disk_status_array_bytes_not_copied",
                )
            )
        )
        or (
            device_mode
            and (
                report["device_to_host_payload_bytes"]
                != expected_payload_bytes
                or report["device_to_host_bounded_status_bytes"]
                != 8 * len(prepared.batches)
                or report["full_disk_status_array_bytes_not_copied"]
                != expected_full_array_bytes
            )
        )
    ):
        raise DirichletMeasuredWorkloadError(
            "packed runner summary differs from the compact reducer receipt"
        )
    stderr_sha256, stderr_size = hash_file_once(path, limit=64 * 1024**2)
    return report, {
        "sha256": stderr_sha256,
        "size_bytes": stderr_size,
    }


def _validate_packed_compact_receipt(
    receipt_path: Path,
    state_path: Path,
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    receipt = _load_canonical(receipt_path, "packed compact-state receipt")
    if (
        receipt.get("schema") != SMALLQ_PACKED_RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("algorithm_id") != SMALLQ_REDUCER_ALGORITHM_ID
        or receipt.get("q") != inputs["q"]
        or receipt.get("pinset_sha256")
        != inputs["manifest"]["pinset_sha256"]
        or receipt.get("compact_source_binding_sha256")
        != inputs["source_binding_sha256"]
        or receipt.get("expected_packing_location")
        != PACKED_REDUCER_LOCATION_BY_MANIFEST[
            inputs["manifest"]["packing_location"]
        ]
        or receipt.get("packing_mode")
        != PACKED_WIRE_MODE_BY_MANIFEST[
            inputs["manifest"]["packing_location"]
        ]
        or receipt.get("full_source_span") is not True
        or receipt.get("structural_bounded_span_kat") is not False
        or receipt.get("packed_stream_materialized") is not False
        or receipt.get("raw_disk_stream_materialized") is not False
        or receipt.get("strict_sign_codes_fed_directly_to_TGDCSB03")
        is not True
        or receipt.get("frame_hash_chain_checked") is not True
        or receipt.get("terminal_coverage_and_eof_checked") is not True
        or receipt.get("runner_strict_sign_arithmetic_replayed_by_reducer")
        is not False
        or receipt.get("dft_arithmetic_containment_replayed") is not False
        or receipt.get("analytic_seed_values_replayed") is not False
        or receipt.get("character_exponent_semantics_replayed") is not False
        or receipt.get("zero_multiplicity_realized") is not False
        or receipt.get("turing_closure_realized") is not False
        or receipt.get("source_admission_enabled") is not False
        or receipt.get("external_atom_discharged") is not False
        or receipt.get("production_ready") is not False
    ):
        raise DirichletMeasuredWorkloadError(
            "packed compact-state receipt changed its exact boundary"
        )
    self_hash = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if (
        _hex(self_hash, "packed compact receipt self hash")
        != hashlib.sha256(
            smallq_compact._canonical_json_bytes(body)
        ).hexdigest()
    ):
        raise DirichletMeasuredWorkloadError(
            "packed compact-state receipt self hash differs"
        )
    expected_state = receipt.get("compact_state_artifact")
    if not isinstance(expected_state, Mapping):
        raise DirichletMeasuredWorkloadError(
            "packed compact-state receipt has no state record"
        )
    replayed = compact_v3.replay_compact_state_v3(
        state_path, expected_record=expected_state
    )
    receipt_sha256, receipt_size = hash_file_once(
        receipt_path, limit=1024 * 1024
    )
    return receipt, replayed, {
        "sha256": receipt_sha256,
        "size_bytes": receipt_size,
    }


def _packed_result(
    *,
    inputs: Mapping[str, Any],
    compact_receipt: Mapping[str, Any],
    compact_state: Mapping[str, Any],
    compact_receipt_file: Mapping[str, Any],
    runner_report: Mapping[str, Any],
    runner_stderr: Mapping[str, Any],
    runner_argv_sha256: str,
    runner_environment_sha256: str,
) -> dict[str, Any]:
    artifacts = inputs["artifacts"]
    device_mode = (
        inputs["manifest"]["packing_location"] == DEVICE_PACKING_LOCATION
    )
    return {
        "algorithm_id": PACKED_PHASE_ALGORITHM_ID,
        "analytic_seed_values_replayed": False,
        "artifact_roster_sha256": inputs["artifact_roster_sha256"],
        "character_exponent_semantics_replayed": False,
        "classification": (
            "measured_smallq_runner_packed_sign_to_compact_state_"
            "not_source_dft_multiplicity_or_turing_evidence"
        ),
        "compact_source_binding_sha256": inputs["source_binding_sha256"],
        "compact_state_artifact_sha256": compact_state["artifact_sha256"],
        "compact_state_receipt_file_sha256": compact_receipt_file["sha256"],
        "compact_state_receipt_sha256": compact_receipt["receipt_sha256"],
        "compact_state_size_bytes": compact_state["size_bytes"],
        "device_side_classification_implemented": device_mode,
        "dft_arithmetic_containment_replayed": False,
        "external_atom_discharged": False,
        "frame_count": compact_receipt["frame_count"],
        "input_manifest_sha256": inputs["manifest_sha256"],
        "item_count": compact_receipt["item_count"],
        "kind": PACKED_RESULT_KIND,
        "packed_stream_materialized": False,
        "packed_stream_sha256": compact_receipt[
            "packed_stream_sha256_receipt_only"
        ],
        "packing_location": inputs["manifest"]["packing_location"],
        "packing_mode": inputs["manifest"]["packing_mode"],
        "pinset_sha256": inputs["manifest"]["pinset_sha256"],
        "predecessor_receipt_file_sha256": inputs["predecessor"][
            "receipt_file_sha256"
        ],
        "predecessor_receipt_sha256": inputs["predecessor"]["receipt_sha256"],
        "production_ready": False,
        "q": inputs["q"],
        "raw_disk_device_to_host_transfer_eliminated": device_mode,
        "raw_disk_stream_materialized": False,
        "retained_compact_receipt_name": "compact-receipt.json",
        "retained_compact_state_name": "compact-state.bin",
        "runner_argv_sha256": runner_argv_sha256,
        "runner_environment_sha256": runner_environment_sha256,
        "runner_control_upload_nanoseconds": runner_report[
            "control_upload_nanoseconds"
        ],
        "runner_device_classification_nanoseconds": runner_report[
            "device_classification_nanoseconds"
        ],
        "runner_device_to_host_bounded_status_bytes": runner_report[
            "device_to_host_bounded_status_bytes"
        ],
        "runner_device_to_host_payload_bytes": runner_report[
            "device_to_host_payload_bytes"
        ],
        "runner_device_to_host_transfer_nanoseconds": runner_report[
            "device_to_host_transfer_nanoseconds"
        ],
        "runner_full_disk_status_array_bytes_not_copied": runner_report[
            "full_disk_status_array_bytes_not_copied"
        ],
        "runner_report_sha256": canonical_sha256(runner_report),
        "runner_sha256": artifacts["runner"]["sha256"],
        "runner_source_sha256": artifacts["runner_source"]["sha256"],
        "runner_stderr_sha256": runner_stderr["sha256"],
        "schema_version": 1,
        "source_admission_enabled": False,
        "terminal_stream_digest_bound": True,
        "turing_closure_realized": False,
        "zero_multiplicity_realized": False,
    }


def _packed_trace_hash(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    predecessor_receipt_file_sha256: str,
    predecessor_receipt_sha256: str,
    artifact_roster_sha256: str,
    runner_sha256: str,
    runner_source_sha256: str,
    pinset_sha256: str,
    source_binding_sha256: str,
    packed_stream_sha256: str,
    compact_state_sha256: str,
    compact_receipt_file_sha256: str,
    compact_receipt_sha256: str,
    runner_stderr_sha256: str,
    result_sha256: str,
) -> str:
    state = hashlib.sha256(
        PACKED_INITIAL_DOMAIN
        + bytes.fromhex(challenge)
        + bytes.fromhex(job_binding)
        + bytes.fromhex(input_sha256)
    ).digest()
    for fields in (
        (
            predecessor_receipt_file_sha256,
            predecessor_receipt_sha256,
            artifact_roster_sha256,
        ),
        (
            runner_sha256,
            runner_source_sha256,
            pinset_sha256,
            source_binding_sha256,
        ),
        (
            packed_stream_sha256,
            compact_state_sha256,
            compact_receipt_file_sha256,
            compact_receipt_sha256,
        ),
        (runner_stderr_sha256, result_sha256),
    ):
        state = hashlib.sha256(
            PACKED_STEP_DOMAIN
            + state
            + b"".join(bytes.fromhex(field) for field in fields)
        ).digest()
    return state.hex()


def _packed_trace(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    result: Mapping[str, Any],
    result_sha256: str,
) -> dict[str, Any]:
    fields = {
        "algorithm_id": PACKED_PHASE_ALGORITHM_ID,
        "challenge_nonce": challenge,
        "input_sha256": input_sha256,
        "iteration_count": PACKED_TRACE_ITERATIONS,
        "job_binding_sha256": job_binding,
        "kind": PACKED_TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
    }
    fields["trace_sha256"] = _packed_trace_hash(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        predecessor_receipt_file_sha256=result[
            "predecessor_receipt_file_sha256"
        ],
        predecessor_receipt_sha256=result["predecessor_receipt_sha256"],
        artifact_roster_sha256=result["artifact_roster_sha256"],
        runner_sha256=result["runner_sha256"],
        runner_source_sha256=result["runner_source_sha256"],
        pinset_sha256=result["pinset_sha256"],
        source_binding_sha256=result["compact_source_binding_sha256"],
        packed_stream_sha256=result["packed_stream_sha256"],
        compact_state_sha256=result["compact_state_artifact_sha256"],
        compact_receipt_file_sha256=result[
            "compact_state_receipt_file_sha256"
        ],
        compact_receipt_sha256=result["compact_state_receipt_sha256"],
        runner_stderr_sha256=result["runner_stderr_sha256"],
        result_sha256=result_sha256,
    )
    return fields


def _packed_output_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return (
        args.work / "compact-state.bin",
        args.work / "compact-receipt.json",
        args.work / "runner-stderr.jsonl",
    )


def run_packed_smallq(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256, inputs = _validate_packed_common(args)
    for path, what in (
        (args.output, "packed measured output"),
        (args.trace, "packed measured trace"),
        (args.work, "packed measured work directory"),
    ):
        if path.exists() or path.is_symlink():
            raise DirichletMeasuredWorkloadError(
                f"refusing to replace existing or linked {what}"
            )
    args.work.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.work.mkdir(mode=0o700)
    state_path, receipt_path, stderr_path = _packed_output_paths(args)
    runner_argv = _packed_runner_argv(args, inputs)
    runner_environment = _packed_runner_environment()
    runner_argv_sha256 = canonical_sha256(runner_argv)
    runner_environment_sha256 = canonical_sha256(runner_environment)
    timeout = _plain_int(
        args.runner_timeout_seconds,
        "packed runner timeout",
        minimum=1,
    )
    timed_out = threading.Event()
    process: subprocess.Popen[bytes] | None = None
    timer: threading.Timer | None = None
    generated = (state_path, receipt_path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(stderr_path, flags, 0o400)
        with os.fdopen(descriptor, "wb") as stderr_output:
            process = subprocess.Popen(
                runner_argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr_output,
                cwd=ROOT,
                env=runner_environment,
                close_fds=True,
                shell=False,
            )
            if process.stdout is None:
                raise DirichletMeasuredWorkloadError(
                    "packed runner has no stdout stream"
                )

            def expire() -> None:
                timed_out.set()
                assert process is not None
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

            timer = threading.Timer(timeout, expire)
            timer.daemon = True
            timer.start()
            try:
                compact_receipt = reduce_packed_stream_to_compact_v3(
                    args.plan,
                    inputs["batches"],
                    args.control,
                    args.control_receipt,
                    process.stdout,
                    state_path,
                    pins=inputs["pins"],
                    receipt_path=receipt_path,
                    chunk_items=args.chunk_items,
                    expected_packing_location=(
                        PACKED_REDUCER_LOCATION_BY_MANIFEST[
                            inputs["manifest"]["packing_location"]
                        ]
                    ),
                )
            except BaseException:
                process.stdout.close()
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
                raise
            finally:
                process.stdout.close()
            return_code = process.wait()
            stderr_output.flush()
            os.fsync(stderr_output.fileno())
        if timed_out.is_set():
            raise DirichletMeasuredWorkloadError(
                "packed certified runner exceeded its measured timeout"
            )
        if return_code != 0:
            diagnostic = _read(
                stderr_path, 64 * 1024**2, "failed packed runner stderr"
            )[-2000:].decode("utf-8", "replace")
            raise DirichletMeasuredWorkloadError(
                f"packed certified runner exited {return_code}: {diagnostic}"
            )
        for path, (record, identity, what) in inputs["snapshots"].items():
            _restate_regular(path, record, identity, what)
        checked_receipt, state_record, receipt_file = (
            _validate_packed_compact_receipt(
                receipt_path, state_path, inputs
            )
        )
        if checked_receipt != compact_receipt:
            raise DirichletMeasuredWorkloadError(
                "packed reducer return value differs from its immutable receipt"
            )
        runner_report, stderr_record = _packed_runner_report(
            stderr_path, checked_receipt, inputs
        )
        result = _packed_result(
            inputs=inputs,
            compact_receipt=checked_receipt,
            compact_state=state_record,
            compact_receipt_file=receipt_file,
            runner_report=runner_report,
            runner_stderr=stderr_record,
            runner_argv_sha256=runner_argv_sha256,
            runner_environment_sha256=runner_environment_sha256,
        )
        result_raw = canonical_json_bytes(result)
        if len(result_raw) > PACKED_MAXIMUM_RESULT_BYTES:
            raise DirichletMeasuredWorkloadError(
                "packed operational result exceeds its measured output bound"
            )
        result_sha256 = hashlib.sha256(result_raw).hexdigest()
        trace = _packed_trace(
            challenge=challenge,
            job_binding=job_binding,
            input_sha256=input_sha256,
            result=result,
            result_sha256=result_sha256,
        )
        _write_exclusive(args.output, result_raw)
        _write_exclusive(args.trace, canonical_json_bytes(trace))
    except BaseException:
        for path in generated:
            path.unlink(missing_ok=True)
        if not args.output.exists():
            args.trace.unlink(missing_ok=True)
        raise
    finally:
        if timer is not None:
            timer.cancel()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()


def verify_packed_smallq_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256, inputs = _validate_packed_common(args)
    state_path, receipt_path, stderr_path = _packed_output_paths(args)
    receipt, state_record, receipt_file = _validate_packed_compact_receipt(
        receipt_path, state_path, inputs
    )
    runner_report, stderr_record = _packed_runner_report(
        stderr_path, receipt, inputs
    )
    for path, (record, identity, what) in inputs["snapshots"].items():
        _restate_regular(path, record, identity, what)
    result = _packed_result(
        inputs=inputs,
        compact_receipt=receipt,
        compact_state=state_record,
        compact_receipt_file=receipt_file,
        runner_report=runner_report,
        runner_stderr=stderr_record,
        runner_argv_sha256=canonical_sha256(
            _packed_runner_argv(args, inputs)
        ),
        runner_environment_sha256=canonical_sha256(
            _packed_runner_environment()
        ),
    )
    expected_raw = canonical_json_bytes(result)
    actual_raw = _read(
        args.output, PACKED_MAXIMUM_RESULT_BYTES, "packed measured output"
    )
    if actual_raw != expected_raw:
        raise DirichletMeasuredWorkloadError(
            "packed measured output differs from structural replay"
        )
    expected_trace = _packed_trace(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        result=result,
        result_sha256=hashlib.sha256(expected_raw).hexdigest(),
    )
    actual_trace = _load_canonical(args.trace, "packed measured trace")
    if actual_trace != expected_trace:
        raise DirichletMeasuredWorkloadError(
            "packed measured trace differs from structural replay"
        )


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256 = _validate_common(args)
    args.work.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.work.mkdir(mode=0o700, exist_ok=False)
    runtime = args.work / "python-flint-runtime"
    q1_root = args.work / "q1"
    q2_root = args.work / "q2"
    _activate_runtime(args.wheel, runtime)
    extract_archive(
        args.q1_archive,
        q1_root,
        maximum_files=MAX_Q1_FILES,
        maximum_bytes=MAX_Q1_BYTES,
    )
    q1 = _verify_q1(q1_root)
    q1_receipt = _verify_q1_receipt(args.q1_receipt)
    q1["trusted_compute"] = q1_receipt

    os.environ.update(
        {
            "TG_DIRICHLET_FLINT_MAX_PRECISION": "16384",
            "TG_DIRICHLET_FLINT_MAX_CONTOUR_DEPTH": "96",
            "TG_DIRICHLET_FLINT_MAX_CONTOUR_EVALUATIONS": "0",
            "TG_DIRICHLET_FLINT_MAX_GRID_REFINEMENTS": "24",
        }
    )
    backend = ROOT / "tools/tg_dirichlet_flint_backend.py"
    initialize_campaign(
        q2_root,
        producer=backend,
        checker=backend,
        characters_per_chunk=CHARACTERS_PER_CHUNK,
        mode="full_source",
        q_start=SOURCE_MIN_Q,
        q_stop=SOURCE_MAX_Q,
    )
    state = run_campaign(q2_root)
    if not state["complete"]:
        raise DirichletMeasuredWorkloadError("q=2..400000 campaign is incomplete")
    q2_final = finalize_campaign(q2_root)
    source_final = _source_final(q1, q2_final)
    source_raw = canonical_json_bytes(source_final)
    _write_exclusive(q2_root / "source-final.json", source_raw)
    tree = _tree_identity(q2_root)
    retained_archive = args.work / "dirichlet-retained.tar"
    create_archive(q2_root, retained_archive)
    retained_sha256, _ = hash_file_once(retained_archive)
    # The archive is the authenticated handoff.  Keeping the unpacked campaign
    # as well would duplicate the dominant returned-package payload; both the
    # source trace verifier and terminal postcheck independently re-extract it.
    shutil.rmtree(q2_root)
    q1_sha256, _ = hash_file_once(args.q1_archive)
    q1_receipt_sha256, _ = hash_file_once(args.q1_receipt)
    trace = _source_trace(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        q1_archive_sha256=q1_sha256,
        q1_receipt_sha256=q1_receipt_sha256,
        retained_archive_sha256=retained_sha256,
        retained_tree_sha256=tree["tree_sha256"],
        source_final_sha256=hashlib.sha256(source_raw).hexdigest(),
    )
    _write_exclusive(args.output, REGISTERED_RESULT)
    _write_exclusive(args.trace, canonical_json_bytes(trace))


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256 = _validate_common(args)
    if _read(args.output, 16, "registered result") != REGISTERED_RESULT:
        raise DirichletMeasuredWorkloadError("registered result is not literal true")
    trace = _load_canonical(args.trace, "work trace")
    expected_fields = {
        "algorithm_id", "challenge_nonce", "input_sha256", "iteration_count",
        "job_binding_sha256", "kind", "result_sha256", "schema_version",
        "trace_sha256",
    }
    if set(trace) != expected_fields:
        raise DirichletMeasuredWorkloadError("work trace fields differ")
    retained_archive = args.work / "dirichlet-retained.tar"
    q1_sha256, _ = hash_file_once(args.q1_archive)
    q1_receipt_sha256, _ = hash_file_once(args.q1_receipt)
    retained_sha256, _ = hash_file_once(retained_archive)
    result_sha256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
    if (
        trace["kind"] != TRACE_KIND
        or trace["schema_version"] != 1
        or trace["algorithm_id"] != REGISTERED_ALGORITHM_ID
        or trace["challenge_nonce"] != challenge
        or trace["job_binding_sha256"] != job_binding
        or trace["input_sha256"] != input_sha256
        or trace["iteration_count"] != TRACE_ITERATIONS
        or trace["result_sha256"] != result_sha256
    ):
        raise DirichletMeasuredWorkloadError("work trace identity differs")

    with tempfile.TemporaryDirectory(prefix="tg-dirichlet-trace-") as temporary:
        temporary_root = Path(temporary)
        runtime = temporary_root / "runtime"
        q1_root = temporary_root / "q1"
        q2_root = temporary_root / "q2"
        _activate_runtime(args.wheel, runtime)
        extract_archive(
            args.q1_archive, q1_root,
            maximum_files=MAX_Q1_FILES, maximum_bytes=MAX_Q1_BYTES,
        )
        q1 = _verify_q1(q1_root)
        q1["trusted_compute"] = _verify_q1_receipt(args.q1_receipt)
        extract_archive(
            retained_archive, q2_root,
            maximum_files=MAX_Q2_FILES, maximum_bytes=MAX_Q2_BYTES,
        )
        tree = _tree_identity(q2_root)
        state = verify_campaign(q2_root, require_complete=True)
        if not state["final_present"]:
            raise DirichletMeasuredWorkloadError("retained q2 final is absent")
        # Re-execute the pinned checker over every retained source chunk.  The
        # producer/checker currently share reviewed bytes, which is recorded by
        # the campaign; this is replay, not an independence claim.
        rerun_external_checkers(q2_root)
        q2_final = finalize_campaign(q2_root)
        expected_source = canonical_json_bytes(_source_final(q1, q2_final))
        retained_source = _read(
            q2_root / "source-final.json", 1024 * 1024, "source composition"
        )
        if retained_source != expected_source:
            raise DirichletMeasuredWorkloadError("source composition differs")
        source_final_sha256 = hashlib.sha256(retained_source).hexdigest()
    expected_trace_hash = _trace_hash(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        q1_archive_sha256=q1_sha256,
        q1_receipt_sha256=q1_receipt_sha256,
        retained_archive_sha256=retained_sha256,
        retained_tree_sha256=tree["tree_sha256"],
        source_final_sha256=source_final_sha256,
        result_sha256=result_sha256,
    )
    if trace["trace_sha256"] != expected_trace_hash:
        raise DirichletMeasuredWorkloadError("work trace chain differs")


def _postcheck_trace(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    replay: dict[str, str],
) -> dict[str, Any]:
    result_sha256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
    fields: dict[str, Any] = {
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "challenge_nonce": challenge,
        "input_sha256": input_sha256,
        "iteration_count": POSTCHECK_TRACE_ITERATIONS,
        "job_binding_sha256": job_binding,
        "kind": POSTCHECK_TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
    }
    fields["trace_sha256"] = _postcheck_trace_hash(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        result_sha256=result_sha256,
        **replay,
    )
    return fields


def postcheck(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256 = _validate_common(args)
    if args.predecessor_certificate is None or args.predecessor_receipt is None:
        raise DirichletMeasuredWorkloadError(
            "postcheck requires predecessor certificate and receipt"
        )
    args.work.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.work.mkdir(mode=0o700, exist_ok=False)
    try:
        replay = _replay_predecessor(
            args.predecessor_certificate,
            args.predecessor_receipt,
            args.wheel,
            args.work,
        )
    finally:
        shutil.rmtree(args.work, ignore_errors=True)
    trace = _postcheck_trace(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        replay=replay,
    )
    # No output is created before the production receipt chain, q=1 campaign,
    # retained q>=2 tree, every q>=2 checker, and source composition all pass.
    _write_exclusive(args.output, REGISTERED_RESULT)
    _write_exclusive(args.trace, canonical_json_bytes(trace))


def verify_postcheck_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    challenge, job_binding, input_sha256 = _validate_common(args)
    if args.predecessor_certificate is None or args.predecessor_receipt is None:
        raise DirichletMeasuredWorkloadError(
            "postcheck trace verification requires predecessor inputs"
        )
    if _read(args.output, 16, "postcheck registered result") != REGISTERED_RESULT:
        raise DirichletMeasuredWorkloadError(
            "postcheck registered result is not literal true"
        )
    actual = _load_canonical(args.trace, "postcheck work trace")
    with tempfile.TemporaryDirectory(
        prefix="tg-dirichlet-postcheck-trace-"
    ) as temporary:
        replay = _replay_predecessor(
            args.predecessor_certificate,
            args.predecessor_receipt,
            args.wheel,
            Path(temporary),
        )
    expected = _postcheck_trace(
        challenge=challenge,
        job_binding=job_binding,
        input_sha256=input_sha256,
        replay=replay,
    )
    if actual != expected:
        raise DirichletMeasuredWorkloadError(
            "postcheck trace differs from independent predecessor replay"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "run",
            "verify-trace",
            "postcheck",
            "verify-postcheck-trace",
            "run-packed-smallq",
            "verify-packed-smallq-trace",
        ),
    )
    parser.add_argument("--algorithm-id", required=True)
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--job-binding", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--q1-archive", type=Path)
    parser.add_argument("--q1-receipt", type=Path)
    parser.add_argument("--predecessor-certificate", type=Path)
    parser.add_argument("--predecessor-receipt", type=Path)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--runner-source", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--batch-directory", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--control-receipt", type=Path)
    parser.add_argument("--pinset", type=Path)
    parser.add_argument(
        "--chunk-items",
        type=int,
        default=smallq_packed.DEFAULT_CHUNK_ITEMS,
    )
    parser.add_argument(
        "--runner-timeout-seconds",
        type=int,
        default=PACKED_DEFAULT_RUNNER_TIMEOUT_SECONDS,
    )
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require_azure_measured_worker(
            challenge_nonce=args.challenge,
            job_binding=args.job_binding,
        )
        if args.mode in (
            "run",
            "verify-trace",
            "postcheck",
            "verify-postcheck-trace",
        ) and args.wheel is None:
            raise DirichletMeasuredWorkloadError(
                "FLINT source and postcheck modes require --wheel"
            )
        if args.mode in ("run", "verify-trace") and (
            args.q1_archive is None or args.q1_receipt is None
        ):
            raise DirichletMeasuredWorkloadError(
                "source run and trace verification require q=1 inputs"
            )
        if args.mode in (
            "run-packed-smallq",
            "verify-packed-smallq-trace",
        ):
            required = {
                "--batch-directory": args.batch_directory,
                "--control": args.control,
                "--control-receipt": args.control_receipt,
                "--pinset": args.pinset,
                "--plan": args.plan,
                "--predecessor-receipt": args.predecessor_receipt,
                "--runner": args.runner,
                "--runner-source": args.runner_source,
            }
            missing = sorted(name for name, value in required.items() if value is None)
            if missing:
                raise DirichletMeasuredWorkloadError(
                    "packed mode lacks required arguments: "
                    + ", ".join(missing)
                )
        dispatch = {
            "run": run,
            "verify-trace": verify_trace,
            "postcheck": postcheck,
            "verify-postcheck-trace": verify_postcheck_trace,
            "run-packed-smallq": run_packed_smallq,
            "verify-packed-smallq-trace": verify_packed_smallq_trace,
        }
        dispatch[args.mode](args)
        return 0
    except (
        ArchiveError,
        CampaignIOError,
        DirichletCampaignError,
        DirichletCompactStateV3Error,
        DirichletMeasuredWorkloadError,
        PlattZetaCampaignError,
        PythonFlintRuntimeError,
        ReceiptError,
        SmallQCompactV3Error,
        SmallQPackedStreamV1Error,
        OSError,
        ValueError,
    ) as error:
        print(f"tg_dirichlet_azure_measured_workload: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
