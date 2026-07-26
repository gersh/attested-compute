# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent replay for the compact native PT21 finalizer archives.

The optimized PT21 worker cannot retain a 600 KiB required-sign packet for
each of roughly three billion windows.  The native finalizer therefore
consumes one fixed-width commitment record per accepted window.  A record
binds the required packet, source trace, finite block artifact, optional
stationary trace, optional sparse-refinement trace, and the measured producer
commitment.  All finite failure counters must be zero.

This module is intentionally a separate implementation of the archive
validator.  It replays every retained record, exact count transition, sparse
refinement relationship, stream digest, and Merkle relationship.  It does not
turn those finite commitments into Hardy-Z or analytic Turing theorems.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
from typing import BinaryIO, Iterable


SOURCE_LOWER = 10_000_000_000
SOURCE_STEP = 1_008
SOURCE_BLOCK_COUNT = 2_966_443_783
SOURCE_LOWER_COUNT = 32_130_158_315
SOURCE_HEIGHT = 3_000_175_332_800
SOURCE_HEIGHT_COUNT = 12_363_153_437_138
SOURCE_HEIGHT_BLOCK = (SOURCE_HEIGHT - SOURCE_LOWER) // SOURCE_STEP
UPSTREAM_COMMIT = b"42b21426718e542daa2b006dc05ea2d7f26426e6"
INTERPOLATION_PATCH_SHA256 = bytes.fromhex(
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3"
)
NONE_COUNT = (1 << 64) - 1
ZERO_SHA256 = bytes(32)
SHA256_RE = re.compile(r"[0-9a-f]{64}")

BLOCK_MAGIC = b"PT21BLK1"
SHARD_HEADER_MAGIC = b"PT21SHD1"
SHARD_FOOTER_MAGIC = b"PT21SFT1"
CAMPAIGN_HEADER_MAGIC = b"PT21CMP1"
CAMPAIGN_SUMMARY_MAGIC = b"PT21CSR1"
CAMPAIGN_FOOTER_MAGIC = b"PT21CFT1"
FORMAT_VERSION = 1
MODE_BOUNDED_TEST = 0
MODE_PRODUCTION = 1
LOCAL_KAT_MAX_BLOCK_RECORDS = 64

BLOCK_RECORD = struct.Struct(
    "<8sIIQQQQIIIIIIIIQ32s32s32s32s32s32sQ32s"
)
ARCHIVE_HEADER = struct.Struct("<8sIIIIQQ32s32s32s40s32s32s16s")
ARCHIVE_FOOTER = struct.Struct("<8sIIQQQQQQQQQ32s32s32s40s32s")
CAMPAIGN_SUMMARY = struct.Struct(
    "<8sIIQQQQQQQQQQ32s32s32s32s32s32s"
)

assert BLOCK_RECORD.size == 320
assert ARCHIVE_HEADER.size == 256
assert ARCHIVE_FOOTER.size == 256
assert CAMPAIGN_SUMMARY.size == 288

BLOCK_RECORD_DOMAIN = b"sparkinterval/tg/platt-pt21-native-block-record/v1\0"
BLOCK_LEAF_DOMAIN = b"sparkinterval/tg/platt-pt21-native-block-leaf/v1\0"
BLOCK_NODE_DOMAIN = b"sparkinterval/tg/platt-pt21-native-block-node/v1\0"
SHARD_HEADER_DOMAIN = b"sparkinterval/tg/platt-pt21-native-shard-header/v1\0"
SHARD_FOOTER_DOMAIN = b"sparkinterval/tg/platt-pt21-native-shard-footer/v1\0"
CAMPAIGN_HEADER_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-campaign-header/v1\0"
)
CAMPAIGN_SUMMARY_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-campaign-summary/v1\0"
)
CAMPAIGN_LEAF_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-campaign-leaf/v1\0"
)
CAMPAIGN_NODE_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-campaign-node/v1\0"
)
CAMPAIGN_FOOTER_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-campaign-footer/v1\0"
)


class PT21NativeFinalizerError(RuntimeError):
    """A compact PT21 record or retained archive failed closed."""


@dataclass(frozen=True)
class BlockRecord:
    block: int
    lower_count: int
    upper_count: int
    main_slots: int
    stationary_resolution_count: int
    sparse_refinement_count: int
    initial_ambiguous_count: int
    invalid_disk_count: int
    unresolved_disk_count: int
    unresolved_stationary_count: int
    turing_failure_count: int
    replay_failure_count: int
    source_height_count: int | None
    source_height_slots_from_lower: int
    required_packet_sha256: bytes
    source_trace_sha256: bytes
    block_artifact_sha256: bytes
    stationary_trace_sha256: bytes
    sparse_refinement_sha256: bytes
    producer_commitment_sha256: bytes
    record_sha256: bytes


@dataclass(frozen=True)
class ShardReplay:
    path: Path
    mode: int
    first_block: int
    upper_block_exclusive: int
    block_count: int
    first_count: int
    last_count: int
    total_main_slots: int
    total_stationary_resolutions: int
    total_sparse_refinements: int
    source_height_count: int | None
    worker_sha256: bytes
    plan_sha256: bytes
    prefix_evidence_sha256: bytes
    block_merkle_root_sha256: bytes
    record_stream_sha256: bytes
    header_sha256: bytes
    footer_sha256: bytes
    archive_sha256: bytes
    archive_size_bytes: int


@dataclass(frozen=True)
class CampaignReplay:
    path: Path
    mode: int
    first_block: int
    upper_block_exclusive: int
    block_count: int
    shard_count: int
    first_count: int
    last_count: int
    total_main_slots: int
    total_stationary_resolutions: int
    total_sparse_refinements: int
    source_height_count: int | None
    worker_sha256: bytes
    plan_sha256: bytes
    prefix_evidence_sha256: bytes
    shard_merkle_root_sha256: bytes
    summary_stream_sha256: bytes
    header_sha256: bytes
    final_sha256: bytes
    archive_sha256: bytes
    archive_size_bytes: int


def _domain_digest(domain: bytes, raw: bytes) -> bytes:
    return hashlib.sha256(domain + raw).digest()


def _mode(value: int, label: str) -> int:
    if value not in (MODE_BOUNDED_TEST, MODE_PRODUCTION):
        raise PT21NativeFinalizerError(f"{label} mode is unknown")
    return value


def _digest(value: bytes, label: str, *, nonzero: bool = True) -> bytes:
    if len(value) != 32 or (nonzero and value == ZERO_SHA256):
        raise PT21NativeFinalizerError(f"{label} digest is invalid")
    return value


def _hex_digest(value: str | bytes, label: str) -> bytes:
    if isinstance(value, bytes):
        return _digest(value, label)
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PT21NativeFinalizerError(f"{label} is not lowercase SHA-256")
    return _digest(bytes.fromhex(value), label)


def _regular_open(path: Path) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as error:
        raise PT21NativeFinalizerError(
            f"cannot open retained archive without following links: {path}: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PT21NativeFinalizerError(
                f"retained archive is not a regular file: {path}"
            )
        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except Exception:
        os.close(descriptor)
        raise


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    raw = stream.read(size)
    if len(raw) != size:
        raise PT21NativeFinalizerError(f"{label} is truncated")
    return raw


class _MerkleAccumulator:
    """O(log n)-memory duplicate-odd Merkle accumulation."""

    def __init__(self, leaf_domain: bytes, node_domain: bytes) -> None:
        self._leaf_domain = leaf_domain
        self._node_domain = node_domain
        self._peaks: list[bytes | None] = [None] * 64
        self._count = 0

    def add(self, digest: bytes) -> None:
        carry = hashlib.sha256(self._leaf_domain + digest).digest()
        level = 0
        while level < len(self._peaks) and self._peaks[level] is not None:
            carry = hashlib.sha256(
                self._node_domain + self._peaks[level] + carry  # type: ignore[operator]
            ).digest()
            self._peaks[level] = None
            level += 1
        if level == len(self._peaks):
            raise PT21NativeFinalizerError("Merkle stream exceeds uint64 geometry")
        self._peaks[level] = carry
        self._count += 1

    def finish(self) -> bytes:
        if self._count == 0:
            raise PT21NativeFinalizerError(
                "cannot Merkle-finalize an empty stream"
            )
        accumulator: bytes | None = None
        accumulator_level = 0
        for level, peak in enumerate(self._peaks):
            if peak is None:
                continue
            if accumulator is None:
                accumulator = peak
                accumulator_level = level
                continue
            while accumulator_level < level:
                accumulator = hashlib.sha256(
                    self._node_domain + accumulator + accumulator
                ).digest()
                accumulator_level += 1
            accumulator = hashlib.sha256(
                self._node_domain + peak + accumulator
            ).digest()
            accumulator_level = level + 1
        if accumulator is None:  # pragma: no cover - guarded by _count.
            raise PT21NativeFinalizerError("internal empty Merkle accumulator")
        return accumulator


def _optional_count(value: int) -> int | None:
    return None if value == NONE_COUNT else value


def encode_block_record(
    *,
    block: int,
    lower_count: int,
    upper_count: int,
    main_slots: int,
    stationary_resolution_count: int = 0,
    sparse_refinement_count: int = 0,
    initial_ambiguous_count: int = 0,
    invalid_disk_count: int = 0,
    unresolved_disk_count: int = 0,
    unresolved_stationary_count: int = 0,
    turing_failure_count: int = 0,
    replay_failure_count: int = 0,
    source_height_count: int | None = None,
    source_height_slots_from_lower: int = 0,
    required_packet_sha256: str | bytes,
    source_trace_sha256: str | bytes,
    block_artifact_sha256: str | bytes,
    stationary_trace_sha256: str | bytes | None = None,
    sparse_refinement_sha256: str | bytes | None = None,
    producer_commitment_sha256: str | bytes,
) -> bytes:
    """Encode one worker commitment using the reviewed fixed-width wire."""

    stationary = (
        ZERO_SHA256
        if stationary_trace_sha256 is None
        else _hex_digest(stationary_trace_sha256, "stationary trace")
    )
    sparse = (
        ZERO_SHA256
        if sparse_refinement_sha256 is None
        else _hex_digest(sparse_refinement_sha256, "sparse refinement")
    )
    prefix = BLOCK_RECORD.pack(
        BLOCK_MAGIC,
        FORMAT_VERSION,
        BLOCK_RECORD.size,
        block,
        lower_count,
        upper_count,
        main_slots,
        stationary_resolution_count,
        sparse_refinement_count,
        initial_ambiguous_count,
        invalid_disk_count,
        unresolved_disk_count,
        unresolved_stationary_count,
        turing_failure_count,
        replay_failure_count,
        NONE_COUNT if source_height_count is None else source_height_count,
        _hex_digest(required_packet_sha256, "required packet"),
        _hex_digest(source_trace_sha256, "source trace"),
        _hex_digest(block_artifact_sha256, "block artifact"),
        stationary,
        sparse,
        _hex_digest(producer_commitment_sha256, "producer commitment"),
        source_height_slots_from_lower,
        ZERO_SHA256,
    )
    digest = _domain_digest(BLOCK_RECORD_DOMAIN, prefix[:288])
    raw = prefix[:288] + digest
    parse_block_record(raw)
    return raw


def parse_block_record(
    raw: bytes, *, expected_block: int | None = None
) -> BlockRecord:
    if len(raw) != BLOCK_RECORD.size:
        raise PT21NativeFinalizerError("native block record has the wrong length")
    (
        magic,
        version,
        record_bytes,
        block,
        lower_count,
        upper_count,
        main_slots,
        stationary_count,
        sparse_count,
        ambiguous_count,
        invalid_count,
        unresolved_disk_count,
        unresolved_stationary_count,
        turing_failure_count,
        replay_failure_count,
        source_count_raw,
        required_digest,
        source_trace_digest,
        artifact_digest,
        stationary_digest,
        sparse_digest,
        producer_digest,
        source_slots,
        record_digest,
    ) = BLOCK_RECORD.unpack(raw)
    if (
        magic != BLOCK_MAGIC
        or version != FORMAT_VERSION
        or record_bytes != BLOCK_RECORD.size
    ):
        raise PT21NativeFinalizerError("native block record identity differs")
    if block >= SOURCE_BLOCK_COUNT or (
        expected_block is not None and block != expected_block
    ):
        raise PT21NativeFinalizerError("native block record index is not gap-free")
    if lower_count == 0 or upper_count == 0 or lower_count + main_slots != upper_count:
        raise PT21NativeFinalizerError(
            "native block count transition does not telescope"
        )
    failures = (
        invalid_count,
        unresolved_disk_count,
        unresolved_stationary_count,
        turing_failure_count,
        replay_failure_count,
    )
    if any(failures):
        raise PT21NativeFinalizerError(
            "native block retains a nonzero finite failure counter"
        )
    if ambiguous_count != sparse_count:
        raise PT21NativeFinalizerError(
            "every initial ambiguity must have exactly one sparse refinement"
        )
    _digest(required_digest, "required packet")
    _digest(source_trace_digest, "source trace")
    _digest(artifact_digest, "block artifact")
    _digest(producer_digest, "producer commitment")
    if (stationary_count == 0) != (stationary_digest == ZERO_SHA256):
        raise PT21NativeFinalizerError(
            "stationary trace digest/count relationship differs"
        )
    if (sparse_count == 0) != (sparse_digest == ZERO_SHA256):
        raise PT21NativeFinalizerError(
            "sparse refinement digest/count relationship differs"
        )
    source_count = _optional_count(source_count_raw)
    if (block == SOURCE_HEIGHT_BLOCK) != (source_count is not None):
        raise PT21NativeFinalizerError(
            "exact source-height count is absent or attached to the wrong block"
        )
    if source_count is None:
        if source_slots != 0:
            raise PT21NativeFinalizerError(
                "non-target block carries source-height partial slots"
            )
    elif (
        source_slots > main_slots
        or lower_count + source_slots != source_count
    ):
        raise PT21NativeFinalizerError(
            "source-height count is not linked to the target block transition"
        )
    if record_digest != _domain_digest(BLOCK_RECORD_DOMAIN, raw[:288]):
        raise PT21NativeFinalizerError("native block record digest differs")
    return BlockRecord(
        block=block,
        lower_count=lower_count,
        upper_count=upper_count,
        main_slots=main_slots,
        stationary_resolution_count=stationary_count,
        sparse_refinement_count=sparse_count,
        initial_ambiguous_count=ambiguous_count,
        invalid_disk_count=invalid_count,
        unresolved_disk_count=unresolved_disk_count,
        unresolved_stationary_count=unresolved_stationary_count,
        turing_failure_count=turing_failure_count,
        replay_failure_count=replay_failure_count,
        source_height_count=source_count,
        source_height_slots_from_lower=source_slots,
        required_packet_sha256=required_digest,
        source_trace_sha256=source_trace_digest,
        block_artifact_sha256=artifact_digest,
        stationary_trace_sha256=stationary_digest,
        sparse_refinement_sha256=sparse_digest,
        producer_commitment_sha256=producer_digest,
        record_sha256=record_digest,
    )


def _parse_header(
    raw: bytes,
    *,
    magic: bytes,
    record_bytes: int,
    domain: bytes,
    expected_plan_sha256: bytes | None,
    expected_worker_sha256: bytes | None,
    expected_prefix_sha256: bytes | None,
) -> tuple[int, int, int, bytes, bytes, bytes, bytes]:
    (
        actual_magic,
        version,
        header_bytes,
        actual_record_bytes,
        mode,
        first_block,
        item_count,
        worker_digest,
        plan_digest,
        prefix_digest,
        upstream,
        interpolation_patch,
        header_digest,
        reserved,
    ) = ARCHIVE_HEADER.unpack(raw)
    if (
        actual_magic != magic
        or version != FORMAT_VERSION
        or header_bytes != ARCHIVE_HEADER.size
        or actual_record_bytes != record_bytes
        or upstream != UPSTREAM_COMMIT
        or interpolation_patch != INTERPOLATION_PATCH_SHA256
        or reserved != bytes(16)
    ):
        raise PT21NativeFinalizerError("native retained header identity differs")
    _mode(mode, "native retained header")
    if item_count == 0 or first_block >= SOURCE_BLOCK_COUNT:
        raise PT21NativeFinalizerError("native retained header range is empty")
    _digest(worker_digest, "worker")
    _digest(plan_digest, "plan")
    _digest(prefix_digest, "prefix evidence")
    if expected_worker_sha256 is not None and worker_digest != expected_worker_sha256:
        raise PT21NativeFinalizerError("native retained worker identity differs")
    if expected_plan_sha256 is not None and plan_digest != expected_plan_sha256:
        raise PT21NativeFinalizerError("native retained plan identity differs")
    if expected_prefix_sha256 is not None and prefix_digest != expected_prefix_sha256:
        raise PT21NativeFinalizerError(
            "native retained prefix-evidence identity differs"
        )
    if header_digest != _domain_digest(domain, raw[:208]):
        raise PT21NativeFinalizerError("native retained header digest differs")
    return (
        mode,
        first_block,
        item_count,
        worker_digest,
        plan_digest,
        prefix_digest,
        header_digest,
    )


def replay_shard(
    path: Path,
    *,
    expected_plan_sha256: str | bytes | None = None,
    expected_worker_sha256: str | bytes | None = None,
    expected_prefix_sha256: str | bytes | None = None,
    allow_bounded_test: bool = False,
    maximum_bounded_records: int = LOCAL_KAT_MAX_BLOCK_RECORDS,
    require_bounded_test_mode: bool = False,
) -> ShardReplay:
    """Replay every record and relationship in one retained shard archive."""

    expected_plan = (
        None
        if expected_plan_sha256 is None
        else _hex_digest(expected_plan_sha256, "expected plan")
    )
    expected_worker = (
        None
        if expected_worker_sha256 is None
        else _hex_digest(expected_worker_sha256, "expected worker")
    )
    expected_prefix = (
        None
        if expected_prefix_sha256 is None
        else _hex_digest(expected_prefix_sha256, "expected prefix evidence")
    )
    stream, file_size = _regular_open(path)
    with stream:
        archive_hasher = hashlib.sha256()
        header_raw = _read_exact(stream, ARCHIVE_HEADER.size, "shard header")
        archive_hasher.update(header_raw)
        (
            mode,
            first_block,
            block_count,
            worker_digest,
            plan_digest,
            prefix_digest,
            header_digest,
        ) = _parse_header(
            header_raw,
            magic=SHARD_HEADER_MAGIC,
            record_bytes=BLOCK_RECORD.size,
            domain=SHARD_HEADER_DOMAIN,
            expected_plan_sha256=expected_plan,
            expected_worker_sha256=expected_worker,
            expected_prefix_sha256=expected_prefix,
        )
        if mode == MODE_BOUNDED_TEST and not allow_bounded_test:
            raise PT21NativeFinalizerError(
                "bounded-test shard requires explicit replay authorization"
            )
        if require_bounded_test_mode and mode != MODE_BOUNDED_TEST:
            raise PT21NativeFinalizerError(
                "local KAT replay requires a bounded-test shard"
            )
        if (
            mode == MODE_BOUNDED_TEST
            and (
                isinstance(maximum_bounded_records, bool)
                or not isinstance(maximum_bounded_records, int)
                or maximum_bounded_records < 0
                or block_count > maximum_bounded_records
            )
        ):
            raise PT21NativeFinalizerError(
                "bounded-test shard exceeds its declared KAT record limit"
            )
        if first_block + block_count > SOURCE_BLOCK_COUNT:
            raise PT21NativeFinalizerError("native shard leaves the source geometry")
        expected_size = (
            ARCHIVE_HEADER.size
            + block_count * BLOCK_RECORD.size
            + ARCHIVE_FOOTER.size
        )
        if file_size != expected_size:
            raise PT21NativeFinalizerError("native shard archive length differs")

        record_hasher = hashlib.sha256()
        block_merkle = _MerkleAccumulator(BLOCK_LEAF_DOMAIN, BLOCK_NODE_DOMAIN)
        first_count = 0
        last_count = 0
        slots = 0
        stationary = 0
        sparse = 0
        source_counts: list[int] = []
        previous: BlockRecord | None = None
        for offset in range(block_count):
            raw = _read_exact(stream, BLOCK_RECORD.size, "native block record")
            archive_hasher.update(raw)
            record_hasher.update(raw)
            record = parse_block_record(raw, expected_block=first_block + offset)
            if record.producer_commitment_sha256 != worker_digest:
                raise PT21NativeFinalizerError(
                    "native block producer differs from the shard worker"
                )
            if previous is not None and previous.upper_count != record.lower_count:
                raise PT21NativeFinalizerError(
                    "native shard count chain is not contiguous"
                )
            if offset == 0:
                first_count = record.lower_count
            last_count = record.upper_count
            slots += record.main_slots
            stationary += record.stationary_resolution_count
            sparse += record.sparse_refinement_count
            if any(value > NONE_COUNT for value in (slots, stationary, sparse)):
                raise PT21NativeFinalizerError("native shard aggregate overflowed")
            if record.source_height_count is not None:
                source_counts.append(record.source_height_count)
            block_merkle.add(record.record_sha256)
            previous = record
        if first_block == 0 and mode == MODE_PRODUCTION:
            if first_count != SOURCE_LOWER_COUNT:
                raise PT21NativeFinalizerError(
                    "production shard does not start at N(10^10)"
                )
        expected_source = source_counts[0] if len(source_counts) == 1 else None
        contains_target = (
            first_block <= SOURCE_HEIGHT_BLOCK < first_block + block_count
        )
        if contains_target != (len(source_counts) == 1):
            raise PT21NativeFinalizerError(
                "native shard has the wrong source-height count multiplicity"
            )

        footer_raw = _read_exact(stream, ARCHIVE_FOOTER.size, "shard footer")
        archive_hasher.update(footer_raw)
        (
            footer_magic,
            version,
            footer_bytes,
            footer_first,
            footer_upper,
            footer_count,
            footer_first_count,
            footer_last_count,
            footer_slots,
            footer_stationary,
            footer_sparse,
            footer_source_raw,
            block_root,
            stream_digest,
            footer_header_digest,
            reserved,
            footer_digest,
        ) = ARCHIVE_FOOTER.unpack(footer_raw)
        if (
            footer_magic != SHARD_FOOTER_MAGIC
            or version != FORMAT_VERSION
            or footer_bytes != ARCHIVE_FOOTER.size
            or footer_first != first_block
            or footer_upper != first_block + block_count
            or footer_count != block_count
            or footer_first_count != first_count
            or footer_last_count != last_count
            or footer_slots != slots
            or footer_stationary != stationary
            or footer_sparse != sparse
            or _optional_count(footer_source_raw) != expected_source
            or footer_header_digest != header_digest
            or reserved != bytes(40)
        ):
            raise PT21NativeFinalizerError("native shard footer summary differs")
        if stream_digest != record_hasher.digest():
            raise PT21NativeFinalizerError("native shard record-stream digest differs")
        if block_root != block_merkle.finish():
            raise PT21NativeFinalizerError("native shard block Merkle root differs")
        if footer_digest != _domain_digest(SHARD_FOOTER_DOMAIN, footer_raw[:224]):
            raise PT21NativeFinalizerError("native shard footer digest differs")
        if stream.read(1):
            raise PT21NativeFinalizerError("native shard has trailing bytes")
    return ShardReplay(
        path=path,
        mode=mode,
        first_block=first_block,
        upper_block_exclusive=first_block + block_count,
        block_count=block_count,
        first_count=first_count,
        last_count=last_count,
        total_main_slots=slots,
        total_stationary_resolutions=stationary,
        total_sparse_refinements=sparse,
        source_height_count=expected_source,
        worker_sha256=worker_digest,
        plan_sha256=plan_digest,
        prefix_evidence_sha256=prefix_digest,
        block_merkle_root_sha256=block_root,
        record_stream_sha256=stream_digest,
        header_sha256=header_digest,
        footer_sha256=footer_digest,
        archive_sha256=archive_hasher.digest(),
        archive_size_bytes=file_size,
    )


def _parse_campaign_summary(raw: bytes) -> dict[str, int | bytes | None]:
    (
        magic,
        version,
        summary_bytes,
        first,
        upper,
        block_count,
        first_count,
        last_count,
        slots,
        stationary,
        sparse,
        source_raw,
        archive_size,
        archive_digest,
        footer_digest,
        block_root,
        worker_digest,
        record_stream_digest,
        summary_digest,
    ) = CAMPAIGN_SUMMARY.unpack(raw)
    if (
        magic != CAMPAIGN_SUMMARY_MAGIC
        or version != FORMAT_VERSION
        or summary_bytes != CAMPAIGN_SUMMARY.size
        or upper != first + block_count
        or block_count == 0
        or archive_size
        != ARCHIVE_HEADER.size
        + block_count * BLOCK_RECORD.size
        + ARCHIVE_FOOTER.size
    ):
        raise PT21NativeFinalizerError("native campaign shard summary differs")
    for value, label in (
        (archive_digest, "shard archive"),
        (footer_digest, "shard footer"),
        (block_root, "shard block root"),
        (worker_digest, "shard worker"),
        (record_stream_digest, "shard record stream"),
    ):
        _digest(value, label)
    if first_count == 0 or first_count + slots != last_count:
        raise PT21NativeFinalizerError(
            "native campaign shard summary count does not telescope"
        )
    if summary_digest != _domain_digest(CAMPAIGN_SUMMARY_DOMAIN, raw[:256]):
        raise PT21NativeFinalizerError("native campaign shard-summary digest differs")
    return {
        "first_block": first,
        "upper_block_exclusive": upper,
        "block_count": block_count,
        "first_count": first_count,
        "last_count": last_count,
        "total_main_slots": slots,
        "total_stationary_resolutions": stationary,
        "total_sparse_refinements": sparse,
        "source_height_count": _optional_count(source_raw),
        "archive_size_bytes": archive_size,
        "archive_sha256": archive_digest,
        "footer_sha256": footer_digest,
        "block_merkle_root_sha256": block_root,
        "worker_sha256": worker_digest,
        "record_stream_sha256": record_stream_digest,
        "summary_sha256": summary_digest,
    }


def replay_campaign(
    path: Path,
    shard_paths: Iterable[Path],
    *,
    expected_plan_sha256: str | bytes | None = None,
    expected_worker_sha256: str | bytes | None = None,
    expected_prefix_sha256: str | bytes | None = None,
    allow_bounded_test: bool = False,
    maximum_bounded_records: int = LOCAL_KAT_MAX_BLOCK_RECORDS,
    require_bounded_test_mode: bool = False,
) -> CampaignReplay:
    """Replay the campaign archive and independently rescan every shard."""

    paths = list(shard_paths)
    if not paths:
        raise PT21NativeFinalizerError("campaign replay has no shard archives")
    if len({str(item) for item in paths}) != len(paths):
        raise PT21NativeFinalizerError("campaign replay repeats a shard path")
    expected_plan = (
        None
        if expected_plan_sha256 is None
        else _hex_digest(expected_plan_sha256, "expected plan")
    )
    expected_worker = (
        None
        if expected_worker_sha256 is None
        else _hex_digest(expected_worker_sha256, "expected worker")
    )
    expected_prefix = (
        None
        if expected_prefix_sha256 is None
        else _hex_digest(expected_prefix_sha256, "expected prefix evidence")
    )
    stream, file_size = _regular_open(path)
    with stream:
        archive_hasher = hashlib.sha256()
        header_raw = _read_exact(stream, ARCHIVE_HEADER.size, "campaign header")
        archive_hasher.update(header_raw)
        (
            mode,
            first_block,
            shard_count,
            worker_digest,
            plan_digest,
            prefix_digest,
            header_digest,
        ) = _parse_header(
            header_raw,
            magic=CAMPAIGN_HEADER_MAGIC,
            record_bytes=CAMPAIGN_SUMMARY.size,
            domain=CAMPAIGN_HEADER_DOMAIN,
            expected_plan_sha256=expected_plan,
            expected_worker_sha256=expected_worker,
            expected_prefix_sha256=expected_prefix,
        )
        if shard_count != len(paths):
            raise PT21NativeFinalizerError(
                "campaign replay shard roster length differs"
            )
        if mode == MODE_BOUNDED_TEST and not allow_bounded_test:
            raise PT21NativeFinalizerError(
                "bounded-test campaign requires explicit replay authorization"
            )
        if require_bounded_test_mode and mode != MODE_BOUNDED_TEST:
            raise PT21NativeFinalizerError(
                "local KAT replay requires a bounded-test campaign"
            )
        if mode == MODE_BOUNDED_TEST:
            if (
                isinstance(maximum_bounded_records, bool)
                or not isinstance(maximum_bounded_records, int)
                or maximum_bounded_records < 0
            ):
                raise PT21NativeFinalizerError(
                    "bounded-test campaign has an invalid KAT record limit"
                )
            # Use file sizes as a metadata-only preflight before replaying the
            # first record.  The full parser below still validates every
            # header, footer, digest, and relationship.
            retained_records = 0
            for shard_path in paths:
                try:
                    metadata = os.stat(shard_path, follow_symlinks=False)
                except OSError as error:
                    raise PT21NativeFinalizerError(
                        f"cannot stat bounded-test shard: {shard_path}: {error}"
                    ) from error
                payload_bytes = metadata.st_size - (
                    ARCHIVE_HEADER.size + ARCHIVE_FOOTER.size
                )
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or payload_bytes < BLOCK_RECORD.size
                    or payload_bytes % BLOCK_RECORD.size != 0
                ):
                    raise PT21NativeFinalizerError(
                        "bounded-test shard has an invalid preflight size or file type"
                    )
                retained_records += payload_bytes // BLOCK_RECORD.size
                if retained_records > maximum_bounded_records:
                    raise PT21NativeFinalizerError(
                        "bounded-test campaign exceeds its declared KAT record limit"
                    )
        expected_size = (
            ARCHIVE_HEADER.size
            + shard_count * CAMPAIGN_SUMMARY.size
            + ARCHIVE_FOOTER.size
        )
        if file_size != expected_size:
            raise PT21NativeFinalizerError("native campaign archive length differs")

        summary_hasher = hashlib.sha256()
        campaign_merkle = _MerkleAccumulator(
            CAMPAIGN_LEAF_DOMAIN, CAMPAIGN_NODE_DOMAIN
        )
        summaries: list[dict[str, int | bytes | None]] = []
        replays: list[ShardReplay] = []
        for index, shard_path in enumerate(paths):
            raw = _read_exact(
                stream, CAMPAIGN_SUMMARY.size, "campaign shard summary"
            )
            archive_hasher.update(raw)
            summary_hasher.update(raw)
            summary = _parse_campaign_summary(raw)
            shard = replay_shard(
                shard_path,
                expected_plan_sha256=plan_digest,
                expected_worker_sha256=worker_digest,
                expected_prefix_sha256=prefix_digest,
                allow_bounded_test=allow_bounded_test,
                maximum_bounded_records=maximum_bounded_records,
                require_bounded_test_mode=require_bounded_test_mode,
            )
            if shard.mode != mode:
                raise PT21NativeFinalizerError(
                    "campaign and shard execution modes differ"
                )
            expected = {
                "first_block": shard.first_block,
                "upper_block_exclusive": shard.upper_block_exclusive,
                "block_count": shard.block_count,
                "first_count": shard.first_count,
                "last_count": shard.last_count,
                "total_main_slots": shard.total_main_slots,
                "total_stationary_resolutions": shard.total_stationary_resolutions,
                "total_sparse_refinements": shard.total_sparse_refinements,
                "source_height_count": shard.source_height_count,
                "archive_size_bytes": shard.archive_size_bytes,
                "archive_sha256": shard.archive_sha256,
                "footer_sha256": shard.footer_sha256,
                "block_merkle_root_sha256": shard.block_merkle_root_sha256,
                "worker_sha256": shard.worker_sha256,
                "record_stream_sha256": shard.record_stream_sha256,
            }
            if any(summary[key] != value for key, value in expected.items()):
                raise PT21NativeFinalizerError(
                    f"campaign summary {index} differs from fresh shard replay"
                )
            if replays and (
                replays[-1].upper_block_exclusive != shard.first_block
                or replays[-1].last_count != shard.first_count
            ):
                raise PT21NativeFinalizerError(
                    "campaign shard chain is not gap-free and telescoping"
                )
            campaign_merkle.add(summary["summary_sha256"])  # type: ignore[arg-type]
            summaries.append(summary)
            replays.append(shard)

        upper = replays[-1].upper_block_exclusive
        block_count = sum(item.block_count for item in replays)
        slots = sum(item.total_main_slots for item in replays)
        stationary = sum(item.total_stationary_resolutions for item in replays)
        sparse = sum(item.total_sparse_refinements for item in replays)
        if any(value > NONE_COUNT for value in (block_count, slots, stationary, sparse)):
            raise PT21NativeFinalizerError("native campaign aggregate overflowed")
        source_counts = [
            item.source_height_count
            for item in replays
            if item.source_height_count is not None
        ]
        source_count = source_counts[0] if len(source_counts) == 1 else None
        if mode == MODE_PRODUCTION and (
            first_block != 0
            or upper != SOURCE_BLOCK_COUNT
            or block_count != SOURCE_BLOCK_COUNT
            or replays[0].first_count != SOURCE_LOWER_COUNT
            or source_counts != [SOURCE_HEIGHT_COUNT]
        ):
            raise PT21NativeFinalizerError(
                "production native campaign differs from the PT21 source claim"
            )

        footer_raw = _read_exact(stream, ARCHIVE_FOOTER.size, "campaign footer")
        archive_hasher.update(footer_raw)
        (
            footer_magic,
            version,
            footer_bytes,
            footer_first,
            footer_upper,
            footer_blocks,
            footer_first_count,
            footer_last_count,
            footer_slots,
            footer_stationary,
            footer_sparse,
            footer_source_raw,
            shard_root,
            summary_stream_digest,
            footer_header_digest,
            reserved,
            final_digest,
        ) = ARCHIVE_FOOTER.unpack(footer_raw)
        if (
            footer_magic != CAMPAIGN_FOOTER_MAGIC
            or version != FORMAT_VERSION
            or footer_bytes != ARCHIVE_FOOTER.size
            or footer_first != first_block
            or footer_upper != upper
            or footer_blocks != block_count
            or footer_first_count != replays[0].first_count
            or footer_last_count != replays[-1].last_count
            or footer_slots != slots
            or footer_stationary != stationary
            or footer_sparse != sparse
            or _optional_count(footer_source_raw) != source_count
            or footer_header_digest != header_digest
            or reserved != bytes(40)
        ):
            raise PT21NativeFinalizerError("native campaign footer summary differs")
        if summary_stream_digest != summary_hasher.digest():
            raise PT21NativeFinalizerError(
                "native campaign summary-stream digest differs"
            )
        if shard_root != campaign_merkle.finish():
            raise PT21NativeFinalizerError(
                "native campaign shard Merkle root differs"
            )
        if final_digest != _domain_digest(
            CAMPAIGN_FOOTER_DOMAIN, footer_raw[:224]
        ):
            raise PT21NativeFinalizerError("native campaign final digest differs")
        if stream.read(1):
            raise PT21NativeFinalizerError("native campaign has trailing bytes")
    return CampaignReplay(
        path=path,
        mode=mode,
        first_block=first_block,
        upper_block_exclusive=upper,
        block_count=block_count,
        shard_count=shard_count,
        first_count=replays[0].first_count,
        last_count=replays[-1].last_count,
        total_main_slots=slots,
        total_stationary_resolutions=stationary,
        total_sparse_refinements=sparse,
        source_height_count=source_count,
        worker_sha256=worker_digest,
        plan_sha256=plan_digest,
        prefix_evidence_sha256=prefix_digest,
        shard_merkle_root_sha256=shard_root,
        summary_stream_sha256=summary_stream_digest,
        header_sha256=header_digest,
        final_sha256=final_digest,
        archive_sha256=archive_hasher.digest(),
        archive_size_bytes=file_size,
    )


__all__ = [
    "BLOCK_RECORD",
    "CAMPAIGN_SUMMARY",
    "CampaignReplay",
    "NONE_COUNT",
    "PT21NativeFinalizerError",
    "SOURCE_BLOCK_COUNT",
    "SOURCE_HEIGHT_BLOCK",
    "ShardReplay",
    "encode_block_record",
    "parse_block_record",
    "replay_campaign",
    "replay_shard",
]
