# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent bounded-memory verifier for the nonterminal ``PT21EVT1`` wire.

The fused CUDA stage emits one 192-byte record per source window.  The record
binds the exact required DD disks and all three scanner streams through the
scanner's Merkle root, but deliberately retains every stationary candidate as
unresolved.  This module therefore checks only the finite event-stage wire; it
does not manufacture Gaussian--sinc resolutions, Turing counts, or Hardy-Z
semantics.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct
from typing import BinaryIO


VERSION = 1
FINITE_EVENT_STAGE_FLAG = 1
SOURCE_BLOCK_COUNT = 2_966_443_783
REQUIRED_SAMPLE_COUNT = 25_741
REQUIRED_LOWER = -12_870
REQUIRED_UPPER = 12_870
LATTICE_NUMERATOR = 21
LATTICE_DENOMINATOR = 512
STREAM_LOWER = (-12_800, -12_288, 12_288)
STREAM_UPPER = (-12_288, 12_288, 12_800)
DIRECT_CAPACITIES = (512, 24_576, 512)
STATIONARY_CAPACITIES = (510, 24_574, 510)
EDGE_COUNTS = (512, 24_576, 512)
UPSTREAM_COMMIT = b"42b21426718e542daa2b006dc05ea2d7f26426e6"

HEADER_MAGIC = b"PT21EVH1"
RECORD_MAGIC = b"PT21EVT1"
FOOTER_MAGIC = b"PT21EVF1"
CONTRACT_DOMAIN = b"sparkinterval/tg/platt-pt21-event-contract/v1\0"
HEADER_DOMAIN = b"sparkinterval/tg/platt-pt21-event-stream-header/v1\0"
RECORD_DOMAIN = b"sparkinterval/tg/platt-pt21-event-record/v1\0"
FOOTER_DOMAIN = b"sparkinterval/tg/platt-pt21-event-stream-footer/v1\0"

HEADER = struct.Struct("<8s4I2Q32s32s32s24s32s")
RECORD = struct.Struct("<8s2IQ4I3I3I3II3q3q32s32s")
FOOTER = struct.Struct("<8s2I4Q32s32s32s16s32s")
HEADER_DIGEST_OFFSET = 160
RECORD_DIGEST_OFFSET = 160
FOOTER_DIGEST_OFFSET = 160


class PT21EventRecordError(RuntimeError):
    """The compact event stream failed a framing or finite-stage check."""


def _contract_sha256() -> bytes:
    encoded = struct.pack(
        "<I10i6I40s",
        REQUIRED_SAMPLE_COUNT,
        REQUIRED_LOWER,
        REQUIRED_UPPER,
        LATTICE_NUMERATOR,
        LATTICE_DENOMINATOR,
        STREAM_LOWER[0],
        STREAM_UPPER[0],
        STREAM_LOWER[1],
        STREAM_UPPER[1],
        STREAM_LOWER[2],
        STREAM_UPPER[2],
        *DIRECT_CAPACITIES,
        *STATIONARY_CAPACITIES,
        UPSTREAM_COMMIT,
    )
    return hashlib.sha256(CONTRACT_DOMAIN + encoded).digest()


EVENT_CONTRACT_SHA256 = _contract_sha256().hex()


def _sha256_hex(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PT21EventRecordError(f"{label} is not lowercase SHA-256")
    return value


def _nonzero(raw: bytes, label: str) -> None:
    if raw == bytes(32):
        raise PT21EventRecordError(f"{label} is zero")


def _geometry(first_block: int, block_count: int) -> None:
    if (
        block_count < 1
        or first_block < 0
        or first_block >= SOURCE_BLOCK_COUNT
        or block_count > SOURCE_BLOCK_COUNT - first_block
    ):
        raise PT21EventRecordError("event stream geometry is outside PT21")


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise PT21EventRecordError(f"{label} is truncated")
        result.extend(chunk)
    return bytes(result)


def _open_regular(path: Path) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21EventRecordError(
            f"cannot open event stream without following links: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PT21EventRecordError("event stream is not a regular file")
        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except Exception:
        os.close(descriptor)
        raise


def _parse_header(
    raw: bytes,
    *,
    expected_gamma_stream_sha256: str | None,
    expected_producer_sha256: str | None,
) -> dict[str, object]:
    if len(raw) != HEADER.size:
        raise PT21EventRecordError("event stream header has wrong size")
    (
        magic,
        version,
        header_bytes,
        record_bytes,
        flags,
        first_block,
        block_count,
        gamma,
        producer,
        contract,
        reserved,
        digest,
    ) = HEADER.unpack(raw)
    if (
        magic != HEADER_MAGIC
        or version != VERSION
        or header_bytes != HEADER.size
        or record_bytes != RECORD.size
        or flags != FINITE_EVENT_STAGE_FLAG
        or reserved != bytes(len(reserved))
    ):
        raise PT21EventRecordError("event stream fixed header differs")
    _geometry(first_block, block_count)
    _nonzero(gamma, "Gamma stream digest")
    _nonzero(producer, "producer digest")
    if contract != _contract_sha256():
        raise PT21EventRecordError("event source contract digest differs")
    if digest != hashlib.sha256(HEADER_DOMAIN + raw[:HEADER_DIGEST_OFFSET]).digest():
        raise PT21EventRecordError("event stream header digest differs")
    if (
        expected_gamma_stream_sha256 is not None
        and gamma.hex()
        != _sha256_hex(
            expected_gamma_stream_sha256,
            "expected Gamma stream SHA-256",
        )
    ):
        raise PT21EventRecordError("event stream Gamma identity differs")
    if (
        expected_producer_sha256 is not None
        and producer.hex()
        != _sha256_hex(
            expected_producer_sha256,
            "expected producer SHA-256",
        )
    ):
        raise PT21EventRecordError("event stream producer identity differs")
    return {
        "first_block": first_block,
        "block_count": block_count,
        "gamma_stream_sha256": gamma.hex(),
        "producer_sha256": producer.hex(),
        "event_contract_sha256": contract.hex(),
        "header_sha256": digest.hex(),
    }


def parse_record(raw: bytes, *, expected_block: int) -> dict[str, object]:
    """Parse and check one exact 192-byte finite event record."""

    if len(raw) != RECORD.size:
        raise PT21EventRecordError("event record has wrong size")
    fields = RECORD.unpack(raw)
    (
        magic,
        version,
        record_bytes,
        block,
        failure_flags,
        certified_sample_count,
        digest_valid,
        reserved,
        *tail,
    ) = fields
    direct = tuple(tail[0:3])
    stationary = tuple(tail[3:6])
    slots = tuple(tail[6:9])
    unresolved = tail[9]
    nleft = tuple(tail[10:13])
    nright = tuple(tail[13:16])
    artifact = tail[16]
    digest = tail[17]
    if (
        magic != RECORD_MAGIC
        or version != VERSION
        or record_bytes != RECORD.size
        or block != expected_block
        or not 0 <= block < SOURCE_BLOCK_COUNT
        or failure_flags != 0
        or certified_sample_count != REQUIRED_SAMPLE_COUNT
        or digest_valid != 1
        or reserved != 0
    ):
        raise PT21EventRecordError(
            "event record fixed fields or finite status differ"
        )
    _nonzero(artifact, "event artifact digest")
    if digest != hashlib.sha256(RECORD_DOMAIN + raw[:RECORD_DIGEST_OFFSET]).digest():
        raise PT21EventRecordError("event record digest differs")
    for stream in range(3):
        if (
            direct[stream] > DIRECT_CAPACITIES[stream]
            or stationary[stream] > STATIONARY_CAPACITIES[stream]
            or slots[stream] != direct[stream]
        ):
            raise PT21EventRecordError("event record stream counts differ")
        maximum = direct[stream] * (EDGE_COUNTS[stream] - 1)
        if (
            not -maximum <= nleft[stream] <= 0
            or not 0 <= nright[stream] <= maximum
        ):
            raise PT21EventRecordError(
                "event record direct weights leave source bounds"
            )
    if unresolved != sum(stationary):
        raise PT21EventRecordError(
            "event record unresolved stationary count differs"
        )
    return {
        "block": block,
        "direct_event_count": direct,
        "stationary_candidate_count": stationary,
        "certified_direct_slots": slots,
        "unresolved_stationary_count": unresolved,
        "direct_nleft_units": nleft,
        "direct_nright_units": nright,
        "event_artifact_sha256": artifact.hex(),
        "record_sha256": digest.hex(),
    }


def validate_stream(
    path: Path,
    *,
    expected_gamma_stream_sha256: str | None = None,
    expected_producer_sha256: str | None = None,
) -> dict[str, object]:
    """Validate a complete regular-file stream using bounded memory."""

    stream, initial_size = _open_regular(path)
    whole_hasher = hashlib.sha256()
    record_hasher = hashlib.sha256()
    direct_total = 0
    stationary_total = 0
    first_record_sha256: str | None = None
    last_record_sha256: str | None = None
    with stream:
        header_raw = _read_exact(stream, HEADER.size, "event stream header")
        whole_hasher.update(header_raw)
        header = _parse_header(
            header_raw,
            expected_gamma_stream_sha256=expected_gamma_stream_sha256,
            expected_producer_sha256=expected_producer_sha256,
        )
        expected_size = (
            HEADER.size + int(header["block_count"]) * RECORD.size + FOOTER.size
        )
        if initial_size != expected_size:
            raise PT21EventRecordError(
                "event stream byte length differs from declared geometry"
            )
        for offset in range(int(header["block_count"])):
            raw = _read_exact(stream, RECORD.size, "event record")
            whole_hasher.update(raw)
            record_hasher.update(raw)
            record = parse_record(
                raw,
                expected_block=int(header["first_block"]) + offset,
            )
            direct_total += sum(record["direct_event_count"])
            stationary_total += sum(record["stationary_candidate_count"])
            if first_record_sha256 is None:
                first_record_sha256 = str(record["record_sha256"])
            last_record_sha256 = str(record["record_sha256"])
        footer_raw = _read_exact(stream, FOOTER.size, "event stream footer")
        whole_hasher.update(footer_raw)
        (
            magic,
            version,
            footer_bytes,
            first_block,
            block_count,
            footer_direct_total,
            footer_stationary_total,
            record_stream_sha256,
            header_sha256,
            gamma_stream_sha256,
            reserved,
            footer_sha256,
        ) = FOOTER.unpack(footer_raw)
        if (
            magic != FOOTER_MAGIC
            or version != VERSION
            or footer_bytes != FOOTER.size
            or first_block != header["first_block"]
            or block_count != header["block_count"]
            or footer_direct_total != direct_total
            or footer_stationary_total != stationary_total
            or record_stream_sha256 != record_hasher.digest()
            or header_sha256.hex() != header["header_sha256"]
            or gamma_stream_sha256.hex() != header["gamma_stream_sha256"]
            or reserved != bytes(len(reserved))
            or footer_sha256
            != hashlib.sha256(
                FOOTER_DOMAIN + footer_raw[:FOOTER_DIGEST_OFFSET]
            ).digest()
        ):
            raise PT21EventRecordError("event stream footer differs")
        if stream.read(1):
            raise PT21EventRecordError("event stream has trailing bytes")
        final_size = os.fstat(stream.fileno()).st_size
        if final_size != initial_size:
            raise PT21EventRecordError("event stream changed while checked")

    assert first_record_sha256 is not None
    assert last_record_sha256 is not None
    return {
        "schema": "sparkinterval.tg.platt-pt21-event-stream-validation.v1",
        "accepted": True,
        "first_block": header["first_block"],
        "upper_block_exclusive": (
            int(header["first_block"]) + int(header["block_count"])
        ),
        "block_count": header["block_count"],
        "event_record_bytes": RECORD.size,
        "stream_size_bytes": initial_size,
        "stream_sha256": whole_hasher.hexdigest(),
        "record_stream_sha256": record_hasher.hexdigest(),
        "first_record_sha256": first_record_sha256,
        "last_record_sha256": last_record_sha256,
        "gamma_stream_sha256": header["gamma_stream_sha256"],
        "producer_sha256": header["producer_sha256"],
        "event_contract_sha256": header["event_contract_sha256"],
        "total_direct_events": direct_total,
        "total_stationary_candidates": stationary_total,
        "all_required_samples_certified": True,
        "three_stream_event_scan_complete": True,
        "stationary_candidates_unresolved": stationary_total,
        "gaussian_sinc_stationary_resolution_complete": False,
        "turing_closure_complete": False,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


__all__ = [
    "EVENT_CONTRACT_SHA256",
    "FOOTER",
    "HEADER",
    "PT21EventRecordError",
    "RECORD",
    "parse_record",
    "validate_stream",
]
