# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded CUDA/FLINT PT21STJ1 -> Turing -> PT21BLK1 integration.

This module is a deliberately small integration witness for the optimized
PT21 path.  It executes the real CUDA event scanner and FLINT stationary
resolver, independently replays their ``PT21STJ1`` record, executes the real
directed-Arb one-sided Turing-input producer, rebuilds the exact-rational
block artifact, and passes one authenticated ``PT21BLK1`` record through the
native shard finalizer.

The finite sample values are explicitly synthetic.  They were chosen so that
the real Turing rounding equations close without an injected count:

* 3,465 direct main-stream sign changes;
* two stationary candidates, each retained with multiplicity two; and
* 3,469 total main-stream slots, equal to the real Arb endpoint-count gap.

Nothing here promotes a synthetic disk to Hardy Z or proves the analytic
Turing inequalities.  Every such status remains false.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from typing import Any

from tg_verifier.platt_pt21_fused_artifact import (
    PT21FusedArtifactError,
    build_block_artifact,
)
from tg_verifier.platt_pt21_native_finalizer import (
    PT21NativeFinalizerError,
    encode_block_record,
    parse_block_record,
    replay_shard,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    PT21NativeRecordAdapterError,
    adapt_block,
    worker_identity,
    write_exclusive,
)
from tg_verifier.platt_pt21_stationary_junction import (
    Candidate,
    PT21StationaryJunctionError,
    SAMPLE as JUNCTION_SAMPLE,
    parse_record as parse_junction_record,
    replay as replay_junction,
)
from tg_verifier.platt_pt21_turing_inputs import (
    MAX_BYTES as TURING_MAXIMUM_BYTES,
    PT21TuringInputsError,
    validate as validate_turing_inputs,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE as PACKET_SAMPLE,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    UPSTREAM_COMMIT,
    load_required_sign_packet,
)
from tg_verifier.platt_stationary_trace import (
    MAXIMUM_BYTES as STATIONARY_MAXIMUM_BYTES,
    PT21StationaryTraceError,
    validate as validate_stationary_trace,
)


SCHEMA = "sparkinterval.tg.platt-pt21-bounded-block-chain.v1"
JUNCTION_SCHEMA = (
    "sparkinterval.tg.platt-pt21-stationary-junction-benchmark.v1"
)
SHARD_SUMMARY_SCHEMA = (
    "sparkinterval.tg.platt-pt21-native-shard-summary.v1"
)
CHAIN_COMMITMENT_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-bounded-block-chain-commitment/v1\0"
)
PLAN_DOMAIN = b"sparkinterval/tg/platt-pt21-bounded-plan/v1\0"
PREFIX_DOMAIN = b"sparkinterval/tg/platt-pt21-bounded-prefix/v1\0"
BLOCK = 0
DIRECT_MAIN_EVENTS = 3_465
STATIONARY_CANDIDATES = 2
RESOLVED_MULTIPLICITY_SLOTS = 4
MAIN_SLOTS = 3_469
MAXIMUM_JUNCTION_STDOUT = 128 * 1024
MAXIMUM_FINALIZER_STDOUT = 64 * 1024
SYNTHETIC_SOURCE = (
    b"sparkinterval-explicitly-synthetic-pt21-turing-closure-fixture-v1"
)
JUNCTION_FIELDS = {
    "accepted_records",
    "analytic_turing_realization_proved",
    "candidate_count",
    "cold_scanner_replay_seconds",
    "elapsed_seconds",
    "event_record_hex",
    "failure_flags",
    "fixture",
    "flint_sha256",
    "flint_to_mathlib_realization_proved",
    "first_interior_terminal_blocks",
    "hardy_z_endpoint_realization_proved",
    "invocations",
    "junctions_per_second",
    "mode",
    "pt21_source_claim_discharged",
    "record_bytes",
    "record_hex",
    "required_sample_payload_sha256",
    "resolved_multiplicity_slots_per_record",
    "resolver_sha256",
    "schema",
    "stationary_trace_hex",
    "synthetic_finite_fixture",
    "test_success",
    "warm_scanner_replay_seconds",
}


class PT21BoundedBlockChainError(RuntimeError):
    """One finite predecessor, identity, or count relationship differs."""


@dataclass(frozen=True)
class BoundedBlockChain:
    report: dict[str, object]
    event_record: bytes
    stationary_junction_record: bytes
    required_packet: bytes
    stationary_trace: bytes
    turing_inputs: bytes
    source_trace: bytes
    block_artifact: bytes
    block_record: bytes
    shard_archive: bytes


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21BoundedBlockChainError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes, *, maximum: int, label: str) -> dict[str, Any]:
    if not raw or len(raw) > maximum:
        raise PT21BoundedBlockChainError(f"{label} byte length is invalid")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21BoundedBlockChainError(
            f"{label} is not strict JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise PT21BoundedBlockChainError(f"{label} is not a JSON object")
    return value


def _lower_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        or value == "0" * 64
    ):
        raise PT21BoundedBlockChainError(
            f"{label} is not nonzero lowercase SHA-256"
        )
    return value


def _regular_identity(path: Path, label: str) -> tuple[str, int]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21BoundedBlockChainError(
            f"cannot open {label} without following links: {error}"
        ) from error
    digest = hashlib.sha256()
    consumed = 0
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            raise PT21BoundedBlockChainError(
                f"{label} is not a nonempty regular file"
            )
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        final = os.fstat(descriptor)
        if consumed != metadata.st_size or final.st_size != metadata.st_size:
            raise PT21BoundedBlockChainError(
                f"{label} changed while being hashed"
            )
        return digest.hexdigest(), metadata.st_size
    finally:
        os.close(descriptor)


def _require_flint_loader_alias(flint_library: Path) -> None:
    """Ensure the FLINT 3.6 SONAME resolves to the file whose bytes we hash."""

    alias = flint_library.parent / "libflint.so.24"
    try:
        actual = flint_library.resolve(strict=True)
        loaded = alias.resolve(strict=True)
    except OSError as error:
        raise PT21BoundedBlockChainError(
            f"cannot resolve the FLINT 3.6 loader identity: {error}"
        ) from error
    if actual != loaded:
        raise PT21BoundedBlockChainError(
            "libflint.so.24 does not resolve to the hashed FLINT library"
        )


def _fnv1a(raw: bytes) -> int:
    value = 1_469_598_103_934_665_603
    for byte in raw:
        value ^= byte
        value = (value * 1_099_511_628_211) & ((1 << 64) - 1)
    return value


def synthetic_samples() -> tuple[bytes, bytes]:
    """Return the exact CUDA fixture payload and its redundant sign bitmap."""

    radius = 2.0**-80
    triples: list[tuple[float, float, float]] = []
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    positive = True
    for index, offset in enumerate(range(-12_870, 12_871)):
        if offset > -12_870:
            boundary = offset - 1
            if boundary in (2, 3, 12, 13) or 100 <= boundary <= 3_560:
                positive = not positive
        high = 3.0 if positive else -3.0
        if offset in (1, 11):
            high = 1.0
        elif offset in (3, 13):
            high = -100.0
        triples.append((high, 0.0, radius))
        if high > 0:
            signs[index // 8] |= 1 << (index % 8)
    samples = b"".join(PACKET_SAMPLE.pack(*sample) for sample in triples)
    if (
        PACKET_SAMPLE.size != JUNCTION_SAMPLE.size
        or len(samples) != REQUIRED_COUNT * JUNCTION_SAMPLE.size
    ):
        raise PT21BoundedBlockChainError(
            "synthetic sample wire differs between packet and junction"
        )
    return samples, bytes(signs)


def synthetic_candidates() -> list[Candidate]:
    result: list[Candidate] = []
    lower, upper = -12_288, 12_288
    for left in (0, 10):
        edge = left - lower
        result.append(
            Candidate(
                stream=1,
                left_sample=left,
                middle_sample=left + 1,
                right_sample=left + 2,
                nleft_units_per_slot=-edge,
                nright_units_per_slot=upper - lower - edge - 2,
                source_positive=1,
                strict_stat_pt=1,
                requires_adaptive_resolution=1,
                certified_multiplicity_slots=0,
                multiplicity_slots_if_resolved=2,
            )
        )
    return result


def synthetic_required_packet() -> bytes:
    samples, signs = synthetic_samples()
    source_sha256 = hashlib.sha256(SYNTHETIC_SOURCE).hexdigest().encode()
    header = HEADER.pack(
        b"PT21SGN1",
        1,
        HEADER.size,
        0x01020304,
        1,
        1,
        768_000,
        REQUIRED_BEGIN,
        REQUIRED_END,
        REQUIRED_COUNT,
        0,
        SOURCE_LOWER_CENTER + BLOCK * SOURCE_STEP,
        len(samples),
        len(signs),
        _fnv1a(samples),
        _fnv1a(signs),
        len(SYNTHETIC_SOURCE),
        source_sha256,
        UPSTREAM_COMMIT,
    )
    return header + samples + signs


def _run(
    executable: Path,
    arguments: list[str],
    *,
    expected_sha256: str,
    maximum_stdout: int,
    environment: dict[str, str],
    label: str,
) -> bytes:
    expected = _lower_sha256(expected_sha256, f"expected {label} executable")
    descriptor = -1
    try:
        descriptor = os.open(
            executable,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_mode & 0o111 == 0
        ):
            raise PT21BoundedBlockChainError(
                f"{label} is not a nonempty executable regular file"
            )
        digest = hashlib.sha256()
        consumed = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        final = os.fstat(descriptor)
        if (
            consumed != metadata.st_size
            or final.st_size != metadata.st_size
            or digest.hexdigest() != expected
        ):
            raise PT21BoundedBlockChainError(
                f"{label} changed after its identity was selected"
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        pinned = f"/proc/self/fd/{descriptor}"
        completed = subprocess.run(
            [pinned, *arguments],
            executable=pinned,
            pass_fds=(descriptor,),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=30,
        )
    except OSError as error:
        raise PT21BoundedBlockChainError(
            f"cannot execute pinned {label}: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        completed.returncode != 0
        or completed.stderr
        or not completed.stdout
        or len(completed.stdout) > maximum_stdout
    ):
        diagnostic = completed.stderr.decode(errors="replace").strip()
        raise PT21BoundedBlockChainError(
            f"{label} failed closed"
            + (f": {diagnostic}" if diagnostic else "")
        )
    return completed.stdout


def _validate_junction_output(
    raw: bytes,
    *,
    resolver_sha256: str,
    flint_sha256: str,
) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    value = _strict_json(
        raw, maximum=MAXIMUM_JUNCTION_STDOUT, label="CUDA/FLINT junction output"
    )
    if set(value) != JUNCTION_FIELDS:
        raise PT21BoundedBlockChainError("junction output fields differ")
    fixed = {
        "accepted_records": 1,
        "analytic_turing_realization_proved": False,
        "candidate_count": STATIONARY_CANDIDATES,
        "failure_flags": 0,
        "fixture": "turing-closure",
        "flint_sha256": flint_sha256,
        "flint_to_mathlib_realization_proved": False,
        "first_interior_terminal_blocks": [BLOCK],
        "hardy_z_endpoint_realization_proved": False,
        "invocations": 1,
        "mode": "valid",
        "pt21_source_claim_discharged": False,
        "record_bytes": 400,
        "resolved_multiplicity_slots_per_record": (
            RESOLVED_MULTIPLICITY_SLOTS
        ),
        "resolver_sha256": resolver_sha256,
        "schema": JUNCTION_SCHEMA,
        "synthetic_finite_fixture": True,
        "test_success": True,
    }
    if any(value[key] != expected for key, expected in fixed.items()):
        raise PT21BoundedBlockChainError(
            "junction output finite status or identity differs"
        )
    for name in (
        "cold_scanner_replay_seconds",
        "warm_scanner_replay_seconds",
        "elapsed_seconds",
        "junctions_per_second",
    ):
        measured = value[name]
        if (
            isinstance(measured, bool)
            or not isinstance(measured, (float, int))
            or not math.isfinite(measured)
            or measured <= 0
        ):
            raise PT21BoundedBlockChainError(
                f"junction output {name} is not a positive finite measurement"
            )
    samples, _signs = synthetic_samples()
    if value["required_sample_payload_sha256"] != hashlib.sha256(samples).hexdigest():
        raise PT21BoundedBlockChainError(
            "junction CUDA sample payload differs from the reconstructed fixture"
        )
    encoded = (
        ("record_hex", 400),
        ("event_record_hex", 192),
        ("stationary_trace_hex", None),
    )
    decoded: dict[str, bytes] = {}
    for name, expected_bytes in encoded:
        text = value[name]
        if (
            not isinstance(text, str)
            or len(text) % 2
            or any(character not in "0123456789abcdef" for character in text)
        ):
            raise PT21BoundedBlockChainError(f"junction {name} is not lower hex")
        result = bytes.fromhex(text)
        if expected_bytes is not None and len(result) != expected_bytes:
            raise PT21BoundedBlockChainError(
                f"junction {name} has the wrong byte length"
            )
        decoded[name] = result
    stationary_raw = decoded["stationary_trace_hex"]
    if (
        not stationary_raw
        or len(stationary_raw) > STATIONARY_MAXIMUM_BYTES
    ):
        raise PT21BoundedBlockChainError(
            "stationary trace has an invalid byte length"
        )
    stationary_value = _strict_json(
        stationary_raw,
        maximum=STATIONARY_MAXIMUM_BYTES,
        label="stationary trace",
    )
    if stationary_raw != _canonical(stationary_value) + b"\n":
        raise PT21BoundedBlockChainError("stationary trace is not canonical")
    try:
        validated_trace = validate_stationary_trace(stationary_value)
        replay_junction(
            decoded["record_hex"],
            event_record=decoded["event_record_hex"],
            sample_payload=samples,
            candidates=synthetic_candidates(),
            refinements=[],
            stationary_trace=validated_trace,
            expected_resolver_sha256=resolver_sha256,
            expected_flint_sha256=flint_sha256,
        )
    except (PT21StationaryTraceError, PT21StationaryJunctionError) as error:
        raise PT21BoundedBlockChainError(
            f"independent PT21STJ1 replay failed: {error}"
        ) from error
    return (
        value,
        decoded["record_hex"],
        decoded["event_record_hex"],
        stationary_raw,
    )


def _adapter_source_identity() -> str:
    root = Path(__file__).resolve().parent
    names = (
        "platt_pt21_bounded_block_chain.py",
        "platt_pt21_fused_artifact.py",
        "platt_pt21_native_finalizer.py",
        "platt_pt21_native_record_adapter.py",
        "platt_pt21_stationary_junction.py",
        "platt_pt21_turing_inputs.py",
    )
    frame = bytearray()
    for name in names:
        raw = (root / name).read_bytes()
        frame.extend(struct.pack("<I", len(name)))
        frame.extend(name.encode())
        frame.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(
        b"sparkinterval/tg/platt-pt21-python-adapter-sources/v1\0" + frame
    ).hexdigest()


def _chain_commitment(
    *,
    event_record: bytes,
    junction_record: bytes,
    required_packet: bytes,
    stationary_trace: bytes,
    turing_inputs: bytes,
    junction_executable_sha256: str,
    turing_executable_sha256: str,
    flint_sha256: str,
    adapter_sources_sha256: str,
    finalizer_sha256: str,
) -> str:
    digests = (
        hashlib.sha256(event_record).digest(),
        hashlib.sha256(junction_record).digest(),
        hashlib.sha256(required_packet).digest(),
        hashlib.sha256(stationary_trace).digest(),
        hashlib.sha256(turing_inputs).digest(),
        bytes.fromhex(junction_executable_sha256),
        bytes.fromhex(turing_executable_sha256),
        bytes.fromhex(flint_sha256),
        bytes.fromhex(adapter_sources_sha256),
        bytes.fromhex(finalizer_sha256),
    )
    return hashlib.sha256(
        CHAIN_COMMITMENT_DOMAIN + struct.pack("<Q", BLOCK) + b"".join(digests)
    ).hexdigest()


def verify_predecessor_commitment(
    *,
    block_record: bytes,
    event_record: bytes,
    junction_record: bytes,
    required_packet: bytes,
    stationary_trace: bytes,
    turing_inputs: bytes,
    junction_executable_sha256: str,
    turing_executable_sha256: str,
    flint_sha256: str,
    adapter_sources_sha256: str,
    finalizer_sha256: str,
) -> str:
    """Recompute the complete predecessor seal stored in ``PT21BLK1``."""

    identities = {
        "junction executable": junction_executable_sha256,
        "Turing executable": turing_executable_sha256,
        "FLINT": flint_sha256,
        "adapter sources": adapter_sources_sha256,
        "native finalizer": finalizer_sha256,
    }
    for label, digest in identities.items():
        _lower_sha256(digest, label)
    expected = _chain_commitment(
        event_record=event_record,
        junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        junction_executable_sha256=junction_executable_sha256,
        turing_executable_sha256=turing_executable_sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sources_sha256,
        finalizer_sha256=finalizer_sha256,
    )
    try:
        parsed = parse_block_record(block_record, expected_block=BLOCK)
    except PT21NativeFinalizerError as error:
        raise PT21BoundedBlockChainError(
            f"bound PT21BLK1 fails finite replay: {error}"
        ) from error
    if parsed.producer_commitment_sha256.hex() != expected:
        raise PT21BoundedBlockChainError(
            "PT21BLK1 predecessor commitment differs"
        )
    return expected


def _bound_block_record(
    adapted: object,
    *,
    chain_commitment_sha256: str,
) -> bytes:
    parsed = parse_block_record(adapted.record, expected_block=BLOCK)
    try:
        raw = encode_block_record(
            block=parsed.block,
            lower_count=parsed.lower_count,
            upper_count=parsed.upper_count,
            main_slots=parsed.main_slots,
            stationary_resolution_count=parsed.stationary_resolution_count,
            sparse_refinement_count=parsed.sparse_refinement_count,
            initial_ambiguous_count=parsed.initial_ambiguous_count,
            invalid_disk_count=parsed.invalid_disk_count,
            unresolved_disk_count=parsed.unresolved_disk_count,
            unresolved_stationary_count=parsed.unresolved_stationary_count,
            turing_failure_count=parsed.turing_failure_count,
            replay_failure_count=parsed.replay_failure_count,
            source_height_count=parsed.source_height_count,
            source_height_slots_from_lower=parsed.source_height_slots_from_lower,
            required_packet_sha256=parsed.required_packet_sha256,
            source_trace_sha256=parsed.source_trace_sha256,
            block_artifact_sha256=parsed.block_artifact_sha256,
            stationary_trace_sha256=parsed.stationary_trace_sha256,
            sparse_refinement_sha256=(
                None
                if parsed.sparse_refinement_count == 0
                else parsed.sparse_refinement_sha256
            ),
            producer_commitment_sha256=chain_commitment_sha256,
        )
        rebound = parse_block_record(raw, expected_block=BLOCK)
    except PT21NativeFinalizerError as error:
        raise PT21BoundedBlockChainError(
            f"bound PT21BLK1 encoding failed: {error}"
        ) from error
    if rebound.producer_commitment_sha256.hex() != chain_commitment_sha256:
        raise PT21BoundedBlockChainError(
            "PT21BLK1 lost the complete predecessor commitment"
        )
    return raw


def _validate_multiplicity(
    *,
    junction_record: bytes,
    block_record: bytes,
    block_artifact: bytes,
    stationary_trace: bytes,
) -> None:
    junction = parse_junction_record(junction_record)
    block = parse_block_record(block_record, expected_block=BLOCK)
    artifact = _strict_json(
        block_artifact,
        maximum=16 * 1024 * 1024,
        label="exact-rational block artifact",
    )
    events = artifact["streams"]["main"]["events"]
    direct = sum(event["multiplicity"] == 1 for event in events)
    stationary = sum(event["multiplicity"] == 2 for event in events)
    slots = sum(int(event["multiplicity"]) for event in events)
    if (
        int(junction["candidate_count"]) != STATIONARY_CANDIDATES
        or int(junction["resolved_multiplicity_slots"])
        != RESOLVED_MULTIPLICITY_SLOTS
        or block.stationary_resolution_count != STATIONARY_CANDIDATES
        or block.stationary_trace_sha256
        != bytes.fromhex(str(junction["stationary_trace_sha256"]))
        or block.stationary_trace_sha256
        != hashlib.sha256(stationary_trace).digest()
        or direct != DIRECT_MAIN_EVENTS
        or stationary != STATIONARY_CANDIDATES
        or slots != MAIN_SLOTS
        or block.main_slots != MAIN_SLOTS
        or block.lower_count + MAIN_SLOTS != block.upper_count
    ):
        raise PT21BoundedBlockChainError(
            "stationary multiplicity or Turing closure linkage differs"
        )


def verify_retained_chain(
    *,
    event_record: bytes,
    junction_record: bytes,
    required_packet: bytes,
    stationary_trace: bytes,
    turing_inputs: bytes,
    source_trace: bytes,
    block_artifact: bytes,
    block_record: bytes,
    junction_executable_sha256: str,
    turing_executable_sha256: str,
    flint_sha256: str,
    adapter_sources_sha256: str,
    finalizer_sha256: str,
) -> dict[str, int | str | bool]:
    """Independently replay every retained finite relationship."""

    if required_packet != synthetic_required_packet():
        raise PT21BoundedBlockChainError(
            "required packet is not the explicit bounded synthetic fixture"
        )
    samples, _signs = synthetic_samples()
    stationary_value = _strict_json(
        stationary_trace,
        maximum=STATIONARY_MAXIMUM_BYTES,
        label="retained stationary trace",
    )
    if stationary_trace != _canonical(stationary_value) + b"\n":
        raise PT21BoundedBlockChainError(
            "retained stationary trace is not canonical"
        )
    try:
        validated_stationary = validate_stationary_trace(stationary_value)
        replay_junction(
            junction_record,
            event_record=event_record,
            sample_payload=samples,
            candidates=synthetic_candidates(),
            refinements=[],
            stationary_trace=validated_stationary,
            expected_resolver_sha256=junction_executable_sha256,
            expected_flint_sha256=flint_sha256,
        )
    except (PT21StationaryTraceError, PT21StationaryJunctionError) as error:
        raise PT21BoundedBlockChainError(
            f"retained stationary junction failed: {error}"
        ) from error

    packet_sha256 = hashlib.sha256(required_packet).hexdigest()
    turing_value = _strict_json(
        turing_inputs,
        maximum=TURING_MAXIMUM_BYTES,
        label="retained Turing inputs",
    )
    if turing_inputs != _canonical(turing_value) + b"\n":
        raise PT21BoundedBlockChainError(
            "retained Turing inputs are not canonical"
        )
    try:
        turing = validate_turing_inputs(
            turing_value,
            expected_block=BLOCK,
            expected_packet_sha256=packet_sha256,
        )
    except PT21TuringInputsError as error:
        raise PT21BoundedBlockChainError(
            f"retained Turing inputs failed: {error}"
        ) from error
    source_value = _strict_json(
        source_trace,
        maximum=16 * 1024 * 1024,
        label="retained source trace",
    )
    if (
        source_trace != _canonical(source_value) + b"\n"
        or source_value.get("turing_inputs") != turing["turing_inputs"]
    ):
        raise PT21BoundedBlockChainError(
            "source trace is noncanonical or changed the Turing inputs"
        )
    with tempfile.TemporaryDirectory(
        prefix="pt21-bounded-independent-replay-"
    ) as temporary:
        root = Path(temporary)
        packet_path = root / "packet.bin"
        source_path = root / "source.json"
        packet_path.write_bytes(required_packet)
        source_path.write_bytes(source_trace)
        try:
            rebuilt = build_block_artifact(packet_path, source_path)
        except (OSError, PT21FusedArtifactError) as error:
            raise PT21BoundedBlockChainError(
                f"exact-rational block replay failed: {error}"
            ) from error
    rebuilt_raw = _canonical(rebuilt) + b"\n"
    if rebuilt_raw != block_artifact:
        raise PT21BoundedBlockChainError(
            "retained block artifact differs from exact-rational replay"
        )
    try:
        parsed = parse_block_record(block_record, expected_block=BLOCK)
    except PT21NativeFinalizerError as error:
        raise PT21BoundedBlockChainError(
            f"retained PT21BLK1 failed: {error}"
        ) from error
    bindings = {
        "required packet": (
            parsed.required_packet_sha256,
            hashlib.sha256(required_packet).digest(),
        ),
        "source trace": (
            parsed.source_trace_sha256,
            hashlib.sha256(source_trace).digest(),
        ),
        "block artifact": (
            parsed.block_artifact_sha256,
            hashlib.sha256(block_artifact).digest(),
        ),
        "stationary trace": (
            parsed.stationary_trace_sha256,
            hashlib.sha256(stationary_trace).digest(),
        ),
    }
    for label, (actual, expected) in bindings.items():
        if actual != expected:
            raise PT21BoundedBlockChainError(
                f"PT21BLK1 {label} binding differs"
            )
    commitment = verify_predecessor_commitment(
        block_record=block_record,
        event_record=event_record,
        junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        junction_executable_sha256=junction_executable_sha256,
        turing_executable_sha256=turing_executable_sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sources_sha256,
        finalizer_sha256=finalizer_sha256,
    )
    _validate_multiplicity(
        junction_record=junction_record,
        block_record=block_record,
        block_artifact=block_artifact,
        stationary_trace=stationary_trace,
    )
    return {
        "accepted": True,
        "block": BLOCK,
        "lower_count": parsed.lower_count,
        "upper_count": parsed.upper_count,
        "main_slots": parsed.main_slots,
        "stationary_candidate_count": STATIONARY_CANDIDATES,
        "resolved_stationary_multiplicity_slots": (
            RESOLVED_MULTIPLICITY_SLOTS
        ),
        "chain_commitment_sha256": commitment,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }


def run_bounded_block_chain(
    *,
    junction_executable: Path,
    turing_executable: Path,
    flint_library: Path,
    finalizer_executable: Path,
    output_directory: Path,
) -> BoundedBlockChain:
    """Execute and retain one bounded, fully fail-closed finite chain."""

    if output_directory.exists():
        if (
            output_directory.is_symlink()
            or not output_directory.is_dir()
            or any(output_directory.iterdir())
        ):
            raise PT21BoundedBlockChainError(
                "output directory must be an existing empty directory"
            )
    else:
        output_directory.mkdir(parents=True)
    try:
        junction_identity = worker_identity(junction_executable)
        turing_identity = worker_identity(turing_executable)
        finalizer_identity = worker_identity(finalizer_executable)
    except PT21NativeRecordAdapterError as error:
        raise PT21BoundedBlockChainError(
            f"executable identity failed: {error}"
        ) from error
    flint_sha256, flint_size = _regular_identity(
        flint_library, "FLINT shared library"
    )
    _require_flint_loader_alias(flint_library)
    environment = dict(os.environ)
    inherited_library_path = environment.get("LD_LIBRARY_PATH")
    environment["LD_LIBRARY_PATH"] = str(flint_library.parent) + (
        ":" + inherited_library_path if inherited_library_path else ""
    )

    junction_stdout = _run(
        junction_executable,
        [
            "--mode",
            "valid",
            "--iterations",
            "1",
            "--fixture",
            "turing-closure",
            "--block",
            str(BLOCK),
            "--resolver-sha256",
            junction_identity.sha256,
            "--flint-sha256",
            flint_sha256,
        ],
        maximum_stdout=MAXIMUM_JUNCTION_STDOUT,
        expected_sha256=junction_identity.sha256,
        environment=environment,
        label="CUDA/FLINT stationary junction",
    )
    (
        junction_output,
        junction_record,
        event_record,
        stationary_trace,
    ) = _validate_junction_output(
        junction_stdout,
        resolver_sha256=junction_identity.sha256,
        flint_sha256=flint_sha256,
    )

    required_packet = synthetic_required_packet()
    required_path = output_directory / "synthetic-required-sign-packet.bin"
    write_exclusive(required_path, required_packet)
    packet = load_required_sign_packet(required_path)
    samples, _signs = synthetic_samples()
    if (
        required_packet[HEADER.size : HEADER.size + len(samples)] != samples
        or packet.sha256 != hashlib.sha256(required_packet).hexdigest()
    ):
        raise PT21BoundedBlockChainError(
            "retained synthetic packet differs from the CUDA sample payload"
        )

    turing_inputs = _run(
        turing_executable,
        [
            "--block",
            str(BLOCK),
            "--required-sign-packet-sha256",
            packet.sha256,
        ],
        maximum_stdout=TURING_MAXIMUM_BYTES,
        expected_sha256=turing_identity.sha256,
        environment=environment,
        label="directed-Arb Turing-input producer",
    )
    turing_value = _strict_json(
        turing_inputs,
        maximum=TURING_MAXIMUM_BYTES,
        label="Turing input artifact",
    )
    if turing_inputs != _canonical(turing_value) + b"\n":
        raise PT21BoundedBlockChainError(
            "Turing producer output is not canonical JSON"
        )
    try:
        turing = validate_turing_inputs(
            turing_value,
            expected_block=BLOCK,
            expected_packet_sha256=packet.sha256,
        )
    except PT21TuringInputsError as error:
        raise PT21BoundedBlockChainError(
            f"Turing input validation failed: {error}"
        ) from error

    stationary_path = output_directory / "stationary-trace.json"
    turing_path = output_directory / "turing-inputs.json"
    write_exclusive(stationary_path, stationary_trace)
    write_exclusive(turing_path, turing_inputs)
    try:
        adapted = adapt_block(
            required_sign_packet=required_path,
            stationary_trace=stationary_path,
            turing_inputs=turing_path,
            worker=junction_identity,
        )
    except PT21NativeRecordAdapterError as error:
        raise PT21BoundedBlockChainError(
            f"native record adapter failed: {error}"
        ) from error
    source_trace_value = _strict_json(
        adapted.source_trace,
        maximum=16 * 1024 * 1024,
        label="fused source trace",
    )
    if source_trace_value["turing_inputs"] != turing["turing_inputs"]:
        raise PT21BoundedBlockChainError(
            "fused source trace changed the canonical Turing inputs"
        )

    adapter_sha256 = _adapter_source_identity()
    chain_commitment = _chain_commitment(
        event_record=event_record,
        junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        junction_executable_sha256=junction_identity.sha256,
        turing_executable_sha256=turing_identity.sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sha256,
        finalizer_sha256=finalizer_identity.sha256,
    )
    block_record = _bound_block_record(
        adapted, chain_commitment_sha256=chain_commitment
    )
    verify_predecessor_commitment(
        block_record=block_record,
        event_record=event_record,
        junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        junction_executable_sha256=junction_identity.sha256,
        turing_executable_sha256=turing_identity.sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sha256,
        finalizer_sha256=finalizer_identity.sha256,
    )
    _validate_multiplicity(
        junction_record=junction_record,
        block_record=block_record,
        block_artifact=adapted.block_artifact,
        stationary_trace=stationary_trace,
    )
    verify_retained_chain(
        event_record=event_record,
        junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        source_trace=adapted.source_trace,
        block_artifact=adapted.block_artifact,
        block_record=block_record,
        junction_executable_sha256=junction_identity.sha256,
        turing_executable_sha256=turing_identity.sha256,
        flint_sha256=flint_sha256,
        adapter_sources_sha256=adapter_sha256,
        finalizer_sha256=finalizer_identity.sha256,
    )

    event_path = output_directory / "event-record.pt21evt1"
    junction_path = output_directory / "stationary-junction.pt21stj1"
    source_trace_path = output_directory / "source-trace.json"
    artifact_path = output_directory / "block-artifact.json"
    record_path = output_directory / "block.pt21blk1"
    records_path = output_directory / "records.bin"
    shard_path = output_directory / "bounded-shard.bin"
    for path, raw in (
        (event_path, event_record),
        (junction_path, junction_record),
        (source_trace_path, adapted.source_trace),
        (artifact_path, adapted.block_artifact),
        (record_path, block_record),
        (records_path, block_record),
    ):
        write_exclusive(path, raw)

    plan_sha256 = hashlib.sha256(
        PLAN_DOMAIN + bytes.fromhex(chain_commitment)
    ).hexdigest()
    prefix_sha256 = hashlib.sha256(
        PREFIX_DOMAIN + bytes.fromhex(chain_commitment)
    ).hexdigest()
    finalizer_stdout = _run(
        finalizer_executable,
        [
            "shard",
            "--input",
            str(records_path),
            "--output",
            str(shard_path),
            "--first-block",
            str(BLOCK),
            "--block-count",
            "1",
            "--worker-sha256",
            chain_commitment,
            "--plan-sha256",
            plan_sha256,
            "--prefix-evidence-sha256",
            prefix_sha256,
            "--bounded-test",
        ],
        maximum_stdout=MAXIMUM_FINALIZER_STDOUT,
        expected_sha256=finalizer_identity.sha256,
        environment=environment,
        label="native PT21 shard finalizer",
    )
    finalizer_summary = _strict_json(
        finalizer_stdout,
        maximum=MAXIMUM_FINALIZER_STDOUT,
        label="native finalizer summary",
    )
    shard_archive = shard_path.read_bytes()
    if (
        finalizer_stdout != _canonical(finalizer_summary) + b"\n"
        or finalizer_summary.get("schema") != SHARD_SUMMARY_SCHEMA
        or finalizer_summary.get("source_claim_ready") is not False
        or finalizer_summary.get("block_count") != 1
        or finalizer_summary.get("total_main_slots") != MAIN_SLOTS
        or finalizer_summary.get("total_stationary_resolutions")
        != STATIONARY_CANDIDATES
        or finalizer_summary.get("archive_sha256")
        != hashlib.sha256(shard_archive).hexdigest()
    ):
        raise PT21BoundedBlockChainError(
            "native finalizer summary differs from the bounded chain"
        )
    try:
        replayed = replay_shard(
            shard_path,
            expected_worker_sha256=chain_commitment,
            expected_plan_sha256=plan_sha256,
            expected_prefix_sha256=prefix_sha256,
            allow_bounded_test=True,
        )
    except PT21NativeFinalizerError as error:
        raise PT21BoundedBlockChainError(
            f"independent native shard replay failed: {error}"
        ) from error
    if (
        replayed.block_count != 1
        or replayed.total_main_slots != MAIN_SLOTS
        or replayed.total_stationary_resolutions
        != STATIONARY_CANDIDATES
    ):
        raise PT21BoundedBlockChainError(
            "independent shard replay changed finite totals"
        )
    final_flint_sha256, final_flint_size = _regular_identity(
        flint_library, "FLINT shared library after execution"
    )
    if (
        final_flint_sha256 != flint_sha256
        or final_flint_size != flint_size
    ):
        raise PT21BoundedBlockChainError(
            "FLINT shared-library identity changed during the bounded chain"
        )

    parsed_block = parse_block_record(block_record, expected_block=BLOCK)
    report: dict[str, object] = {
        "schema": SCHEMA,
        "accepted": True,
        "bounded_test": True,
        "synthetic_finite_values": True,
        "block": BLOCK,
        "direct_main_events": DIRECT_MAIN_EVENTS,
        "stationary_candidate_count": STATIONARY_CANDIDATES,
        "resolved_stationary_multiplicity_slots": (
            RESOLVED_MULTIPLICITY_SLOTS
        ),
        "main_slots": MAIN_SLOTS,
        "lower_count": parsed_block.lower_count,
        "upper_count": parsed_block.upper_count,
        "count_gap": parsed_block.upper_count - parsed_block.lower_count,
        "event_record_sha256": hashlib.sha256(event_record).hexdigest(),
        "stationary_junction_record_sha256": hashlib.sha256(
            junction_record
        ).hexdigest(),
        "required_sign_packet_sha256": packet.sha256,
        "stationary_trace_sha256": hashlib.sha256(
            stationary_trace
        ).hexdigest(),
        "turing_inputs_sha256": hashlib.sha256(turing_inputs).hexdigest(),
        "source_trace_sha256": adapted.source_trace_sha256,
        "block_artifact_sha256": adapted.block_artifact_sha256,
        "block_record_sha256": parsed_block.record_sha256.hex(),
        "shard_archive_sha256": hashlib.sha256(shard_archive).hexdigest(),
        "chain_commitment_sha256": chain_commitment,
        "junction_executable_sha256": junction_identity.sha256,
        "junction_executable_size_bytes": junction_identity.size_bytes,
        "turing_executable_sha256": turing_identity.sha256,
        "turing_executable_size_bytes": turing_identity.size_bytes,
        "flint_library_sha256": flint_sha256,
        "flint_library_size_bytes": flint_size,
        "adapter_sources_sha256": adapter_sha256,
        "native_finalizer_sha256": finalizer_identity.sha256,
        "native_finalizer_size_bytes": finalizer_identity.size_bytes,
        "junctions_per_second": junction_output["junctions_per_second"],
        "arb_interval_arithmetic_executed": True,
        "cuda_event_scanner_executed": True,
        "flint_stationary_resolver_executed": True,
        "native_finalizer_replayed": True,
        "hardy_z_endpoint_realization_proved": False,
        "flint_to_mathlib_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }
    return BoundedBlockChain(
        report=report,
        event_record=event_record,
        stationary_junction_record=junction_record,
        required_packet=required_packet,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        source_trace=adapted.source_trace,
        block_artifact=adapted.block_artifact,
        block_record=block_record,
        shard_archive=shard_archive,
    )


__all__ = [
    "BLOCK",
    "BoundedBlockChain",
    "DIRECT_MAIN_EVENTS",
    "MAIN_SLOTS",
    "PT21BoundedBlockChainError",
    "RESOLVED_MULTIPLICITY_SLOTS",
    "SCHEMA",
    "STATIONARY_CANDIDATES",
    "run_bounded_block_chain",
    "synthetic_candidates",
    "synthetic_required_packet",
    "synthetic_samples",
    "verify_predecessor_commitment",
    "verify_retained_chain",
]
