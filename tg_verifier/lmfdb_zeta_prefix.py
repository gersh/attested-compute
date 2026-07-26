# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed reader for the public Platt/LMFDB zeta-zero prefix.

The LMFDB files are useful *input artifacts*, not self-authenticating proofs.
This module checks their pinned public inventory, binary framing, exact count
continuity, 104-bit delta stream, and the non-ambiguous cut at ``10^10``.  It
does not silently promote the database's stated Turing completeness to a
kernel theorem.  A receipt using this reader must retain that source
realization as an explicit trusted-compute premise, or independently replay
the Hardy-Z/Turing computation.

All comparisons with the target height are integer comparisons at scale
``2^102``.  No binary64 or host-libm comparison decides the boundary count.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
from typing import Any, BinaryIO


SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-file.v1"
AGGREGATE_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-aggregate.v1"
SOURCE_BASE_URL = "https://beta.lmfdb.org/riemann-zeta-zeros"
SOURCE_KNOWL_URL = "https://www.lmfdb.org/knowledge/show/rcs.source.zeros.zeta"
SOURCE_DATA_URL = f"{SOURCE_BASE_URL}/data"
SOURCE_FILELIST_URL = f"{SOURCE_BASE_URL}/build_index/filelist"
SOURCE_MD5_URL = f"{SOURCE_BASE_URL}/md5sum.log"
SOURCE_README_URL = f"{SOURCE_BASE_URL}/README.dvi"
SOURCE_PARSER_URL = (
    "https://github.com/LMFDB/lmfdb/blob/"
    "d0ab659fdc4f3433ea4ce7f68fe5d82d3970056a/"
    "lmfdb/zeros/zeta/platt_zeros.py"
)
SOURCE_PARSER_COMMIT = "d0ab659fdc4f3433ea4ce7f68fe5d82d3970056a"
SOURCE_PARSER_SHA256 = (
    "fe44da14f1012476e6fba7fcff92500a99ed9bd3697ef9352dce2b5935cacdc3"
)

FILELIST_SHA256 = "92da8bb7c28598bc0e20cc36820d80c20f788984bbad1f6bfaf4d9b0d842ebef"
FILELIST_SIZE = 315_441
FILELIST_COUNT = 14_580
MD5_MANIFEST_SHA256 = (
    "6ca3534a1e967f593a93428e6479eac0992c446a105da3eeb0b7a64121808521"
)
MD5_MANIFEST_SIZE = 811_161
README_SHA256 = "697f75be46faafcb9c39e482d16dd011be44c92ae96d6d24259413e5e0a29158"
README_SIZE = 8_636

TARGET_HEIGHT = 10_000_000_000
TARGET_MULTIPLICITY_COUNT = 32_130_158_315
TARGET_FILE = "zeros_9998546000.dat"
TARGET_FILE_INDEX = 4_765  # zero based in the reviewed upstream filelist
PREFIX_FILE_COUNT = TARGET_FILE_INDEX + 1
TARGET_FILE_MD5 = "a1a886b1d1b1532e25afbc234ccee93d"
TARGET_FILE_SHA256 = (
    "f6d3fbaad771da06fe8e6420fc74eb086d204a138863c4a2c2938d33ec9e497c"
)
TARGET_FILE_SIZE = 92_092_112
TARGET_FILE_BLOCKS = 1_001
TARGET_FILE_FIRST_HEIGHT = 9_998_546_000
TARGET_FILE_FIRST_COUNT = 32_125_255_196
TARGET_FILE_LAST_HEIGHT = 10_000_646_000
TARGET_FILE_LAST_COUNT = 32_132_336_740
TARGET_BLOCK_INDEX = 693
TARGET_BLOCK_FIRST_HEIGHT = 9_999_999_200
TARGET_BLOCK_LAST_HEIGHT = 10_000_001_300
TARGET_BLOCK_FIRST_COUNT = 32_130_155_617
TARGET_BLOCK_LAST_COUNT = 32_130_162_699
TARGET_BLOCK_BELOW_COUNT = 2_698

FILE_RE = re.compile(r"zeros_(0|[1-9][0-9]*)\.dat")
MD5_RE = re.compile(r"([0-9a-f]{32}) [ *](zeros_(?:0|[1-9][0-9]*)\.dat)")
FILE_LEAF_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-file/v1\0"
AGGREGATE_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-aggregate/v1\0"


class LMFDBZetaPrefixError(RuntimeError):
    """The source inventory or a binary zero file failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LMFDBZetaPrefixError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _domain_digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _regular_bytes(path: Path, *, expected_size: int, expected_sha256: str) -> bytes:
    _require(not path.is_symlink(), f"source metadata must not be a symlink: {path}")
    try:
        mode = path.stat().st_mode
    except OSError as error:
        raise LMFDBZetaPrefixError(f"cannot stat source metadata {path}: {error}") from error
    _require(stat.S_ISREG(mode), f"source metadata is not a regular file: {path}")
    raw = path.read_bytes()
    _require(len(raw) == expected_size, f"source metadata size differs: {path}")
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        f"source metadata SHA-256 differs: {path}",
    )
    return raw


@dataclass(frozen=True)
class SourceInventory:
    """Reviewed LMFDB ordering and its source-published MD5 identities."""

    filenames: tuple[str, ...]
    md5_by_filename: dict[str, str]

    @property
    def prefix_filenames(self) -> tuple[str, ...]:
        return self.filenames[:PREFIX_FILE_COUNT]


def load_source_inventory(filelist_path: Path, md5_manifest_path: Path) -> SourceInventory:
    """Load the exact public inventory pinned by SHA-256 in this package."""

    filelist_raw = _regular_bytes(
        filelist_path,
        expected_size=FILELIST_SIZE,
        expected_sha256=FILELIST_SHA256,
    )
    md5_raw = _regular_bytes(
        md5_manifest_path,
        expected_size=MD5_MANIFEST_SIZE,
        expected_sha256=MD5_MANIFEST_SHA256,
    )
    return parse_source_inventory(filelist_raw, md5_raw, require_public_shape=True)


def parse_source_inventory(
    filelist_raw: bytes,
    md5_manifest_raw: bytes,
    *,
    require_public_shape: bool,
) -> SourceInventory:
    """Parse an inventory; tests may exercise framing without the public pin."""

    try:
        filelist_text = filelist_raw.decode("ascii")
        md5_text = md5_manifest_raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise LMFDBZetaPrefixError("source inventory is not ASCII") from error
    _require(filelist_text.endswith("\n"), "filelist is missing its final newline")
    _require(md5_text.endswith("\n"), "MD5 manifest is missing its final newline")
    filenames = tuple(filelist_text.splitlines())
    _require(filenames, "filelist is empty")
    _require(len(set(filenames)) == len(filenames), "filelist contains a duplicate")
    _require(all(FILE_RE.fullmatch(name) for name in filenames), "filelist name is malformed")
    starts = tuple(int(FILE_RE.fullmatch(name).group(1)) for name in filenames)  # type: ignore[union-attr]
    _require(
        all(left < right for left, right in zip(starts, starts[1:], strict=False)),
        "filelist heights are not strictly increasing",
    )

    md5_by_filename: dict[str, str] = {}
    for line in md5_text.splitlines():
        match = MD5_RE.fullmatch(line)
        _require(match is not None, "MD5 manifest row is malformed")
        digest, filename = match.groups()
        _require(filename not in md5_by_filename, "MD5 manifest contains a duplicate")
        md5_by_filename[filename] = digest
    _require(
        set(md5_by_filename) == set(filenames),
        "filelist and MD5 manifest do not name the same files",
    )

    if require_public_shape:
        _require(len(filenames) == FILELIST_COUNT, "public file count differs")
        _require(filenames[0] == "zeros_14.dat", "public first file differs")
        _require(filenames[TARGET_FILE_INDEX] == TARGET_FILE, "target file index differs")
        _require(
            filenames[TARGET_FILE_INDEX + 1] == "zeros_10000646000.dat",
            "file following target file differs",
        )
        _require(md5_by_filename[TARGET_FILE] == TARGET_FILE_MD5, "target MD5 differs")
    return SourceInventory(filenames=filenames, md5_by_filename=md5_by_filename)


class _HashingReader:
    """Single-pass exact reader that commits every byte it consumes."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.md5 = hashlib.md5(usedforsecurity=False)
        self.sha256 = hashlib.sha256()
        self.offset = 0

    def read_exact(self, size: int) -> bytes:
        _require(size >= 0, "negative binary read size")
        raw = self.stream.read(size)
        _require(len(raw) == size, f"truncated zero file at byte {self.offset}")
        self.md5.update(raw)
        self.sha256.update(raw)
        self.offset += size
        return raw

    def finish(self) -> None:
        _require(self.stream.read(1) == b"", "zero file contains unframed trailing bytes")


@dataclass(frozen=True)
class TargetCut:
    block_index: int
    block_first_height: int
    block_last_height: int
    block_first_count: int
    block_last_count: int
    below_in_block: int
    multiplicity_count_below_target: int
    predecessor_midpoint_scaled_2p102: int
    successor_midpoint_scaled_2p102: int

    def as_json(self) -> dict[str, int]:
        return {
            "block_index": self.block_index,
            "block_first_height": self.block_first_height,
            "block_last_height": self.block_last_height,
            "block_first_count": self.block_first_count,
            "block_last_count": self.block_last_count,
            "below_in_block": self.below_in_block,
            "multiplicity_count_below_target": self.multiplicity_count_below_target,
            "predecessor_midpoint_scaled_2p102": self.predecessor_midpoint_scaled_2p102,
            "successor_midpoint_scaled_2p102": self.successor_midpoint_scaled_2p102,
        }


@dataclass(frozen=True)
class ZetaDataFileAudit:
    filename: str
    source_md5: str
    sha256: str
    size_bytes: int
    block_count: int
    first_height: int
    last_height: int
    first_multiplicity_count: int
    last_multiplicity_count: int
    encoded_multiplicity_slots: int
    target_cut: TargetCut | None
    leaf_sha256: str

    def _without_leaf(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "filename": self.filename,
            "source_md5": self.source_md5,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "block_count": self.block_count,
            "first_height": self.first_height,
            "last_height": self.last_height,
            "first_multiplicity_count": self.first_multiplicity_count,
            "last_multiplicity_count": self.last_multiplicity_count,
            "encoded_multiplicity_slots": self.encoded_multiplicity_slots,
            "target_cut": None if self.target_cut is None else self.target_cut.as_json(),
        }

    def as_json(self) -> dict[str, Any]:
        value = self._without_leaf()
        value["leaf_sha256"] = self.leaf_sha256
        return value


def _open_regular_binary(path: Path) -> tuple[BinaryIO, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise LMFDBZetaPrefixError(f"cannot open zero file {path}: {error}") from error
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), f"zero file is not regular: {path}")
        return os.fdopen(descriptor, "rb", closefd=True), info.st_size
    except BaseException:
        os.close(descriptor)
        raise


def audit_data_file(
    path: Path,
    *,
    expected_filename: str,
    expected_md5: str,
    target_height: int | None = None,
    expected_target_count: int | None = None,
) -> ZetaDataFileAudit:
    """Stream and validate one LMFDB binary file exactly once."""

    _require(FILE_RE.fullmatch(expected_filename) is not None, "expected filename is malformed")
    _require(path.name == expected_filename, "zero-file basename differs from the inventory")
    _require(re.fullmatch(r"[0-9a-f]{32}", expected_md5) is not None, "expected MD5 is malformed")
    _require(
        (target_height is None) == (expected_target_count is None),
        "target height and target count must be supplied together",
    )
    if target_height is not None:
        _require(target_height >= 0 and expected_target_count >= 0, "negative target")  # type: ignore[operator]

    stream, file_size = _open_regular_binary(path)
    with stream:
        reader = _HashingReader(stream)
        block_count = struct.unpack("<Q", reader.read_exact(8))[0]
        _require(0 < block_count <= 10_000_000, "zero-file block count is unreasonable")
        first_height: int | None = None
        last_height: int | None = None
        first_count: int | None = None
        last_count: int | None = None
        previous_end: tuple[int, int] | None = None
        encoded_slots = 0
        target_cut: TargetCut | None = None

        for block_index in range(block_count):
            t0_float, t1_float, n0, n1 = struct.unpack("<ddQQ", reader.read_exact(32))
            _require(math.isfinite(t0_float) and math.isfinite(t1_float), "non-finite height")
            _require(t0_float.is_integer() and t1_float.is_integer(), "non-integral block height")
            t0 = int(t0_float)
            t1 = int(t1_float)
            _require(0 <= t0 < t1 < 1 << 53, "block height is outside exact binary64 integers")
            _require(n0 <= n1, "block multiplicity counts decrease")
            if previous_end is not None:
                _require(previous_end == (t0, n0), "within-file block continuity failed")
            if first_height is None:
                first_height, first_count = t0, n0
            previous_end = (t1, n1)
            last_height, last_count = t1, n1

            slot_count = n1 - n0
            encoded_slots += slot_count
            cumulative = 0
            previous_midpoint: int | None = None
            below = 0
            predecessor: int | None = None
            successor: int | None = None
            target_in_block = target_height is not None and t0 <= target_height < t1
            target_scaled = None if target_height is None else target_height << 102
            t0_scaled = t0 << 102
            t1_scaled = t1 << 102

            for _slot in range(slot_count):
                low64, middle32, high8 = struct.unpack("<QIB", reader.read_exact(13))
                delta = low64 + (middle32 << 64) + (high8 << 96)
                cumulative += delta
                midpoint_scaled = t0_scaled + 2 * cumulative
                lower = midpoint_scaled - 1
                upper = midpoint_scaled + 1
                _require(t0_scaled < lower and upper < t1_scaled, "zero interval leaves its block")
                if previous_midpoint is not None:
                    _require(
                        previous_midpoint <= midpoint_scaled,
                        "stored zero midpoints are not multiplicity-preserving order",
                    )
                previous_midpoint = midpoint_scaled

                if target_in_block:
                    assert target_scaled is not None
                    if upper < target_scaled:
                        below += 1
                        predecessor = midpoint_scaled
                    elif lower >= target_scaled:
                        if successor is None:
                            successor = midpoint_scaled
                    else:
                        raise LMFDBZetaPrefixError(
                            "a stored zero interval straddles the target height"
                        )

            if target_in_block:
                _require(target_cut is None, "target occurs in more than one block")
                _require(predecessor is not None and successor is not None, "target lacks neighbors")
                count_at_target = n0 + below
                _require(
                    count_at_target == expected_target_count,
                    "target multiplicity count differs",
                )
                target_cut = TargetCut(
                    block_index=block_index,
                    block_first_height=t0,
                    block_last_height=t1,
                    block_first_count=n0,
                    block_last_count=n1,
                    below_in_block=below,
                    multiplicity_count_below_target=count_at_target,
                    predecessor_midpoint_scaled_2p102=predecessor,
                    successor_midpoint_scaled_2p102=successor,
                )

        reader.finish()
        _require(reader.offset == file_size, "zero-file framing did not consume its exact size")
        actual_md5 = reader.md5.hexdigest()
        actual_sha256 = reader.sha256.hexdigest()

    _require(actual_md5 == expected_md5, "zero-file source MD5 differs")
    if target_height is not None:
        _require(target_cut is not None, "target height is absent from the zero file")
    assert first_height is not None and last_height is not None
    assert first_count is not None and last_count is not None
    value = {
        "schema": SCHEMA,
        "filename": expected_filename,
        "source_md5": actual_md5,
        "sha256": actual_sha256,
        "size_bytes": file_size,
        "block_count": block_count,
        "first_height": first_height,
        "last_height": last_height,
        "first_multiplicity_count": first_count,
        "last_multiplicity_count": last_count,
        "encoded_multiplicity_slots": encoded_slots,
        "target_cut": None if target_cut is None else target_cut.as_json(),
    }
    return ZetaDataFileAudit(
        filename=expected_filename,
        source_md5=actual_md5,
        sha256=actual_sha256,
        size_bytes=file_size,
        block_count=block_count,
        first_height=first_height,
        last_height=last_height,
        first_multiplicity_count=first_count,
        last_multiplicity_count=last_count,
        encoded_multiplicity_slots=encoded_slots,
        target_cut=target_cut,
        leaf_sha256=_domain_digest(FILE_LEAF_DOMAIN, value),
    )


def audit_public_target_file(path: Path, inventory: SourceInventory) -> ZetaDataFileAudit:
    """Check the public file containing the exact ``10^10`` boundary."""

    _require(inventory.filenames[TARGET_FILE_INDEX] == TARGET_FILE, "target inventory moved")
    audit = audit_data_file(
        path,
        expected_filename=TARGET_FILE,
        expected_md5=inventory.md5_by_filename[TARGET_FILE],
        target_height=TARGET_HEIGHT,
        expected_target_count=TARGET_MULTIPLICITY_COUNT,
    )
    _require(audit.sha256 == TARGET_FILE_SHA256, "reviewed target SHA-256 differs")
    _require(audit.size_bytes == TARGET_FILE_SIZE, "reviewed target size differs")
    _require(audit.block_count == TARGET_FILE_BLOCKS, "reviewed target block count differs")
    _require(
        (audit.first_height, audit.first_multiplicity_count)
        == (TARGET_FILE_FIRST_HEIGHT, TARGET_FILE_FIRST_COUNT),
        "reviewed target initial header differs",
    )
    _require(
        (audit.last_height, audit.last_multiplicity_count)
        == (TARGET_FILE_LAST_HEIGHT, TARGET_FILE_LAST_COUNT),
        "reviewed target terminal header differs",
    )
    cut = audit.target_cut
    _require(cut is not None, "reviewed target cut is absent")
    _require(
        (
            cut.block_index,
            cut.block_first_height,
            cut.block_last_height,
            cut.block_first_count,
            cut.block_last_count,
            cut.below_in_block,
        )
        == (
            TARGET_BLOCK_INDEX,
            TARGET_BLOCK_FIRST_HEIGHT,
            TARGET_BLOCK_LAST_HEIGHT,
            TARGET_BLOCK_FIRST_COUNT,
            TARGET_BLOCK_LAST_COUNT,
            TARGET_BLOCK_BELOW_COUNT,
        ),
        "reviewed target cut geometry differs",
    )
    return audit


def aggregate_file_audits(
    audits: list[ZetaDataFileAudit],
    *,
    inventory: SourceInventory,
    require_complete_public_prefix: bool,
) -> dict[str, Any]:
    """Check cross-file count/height continuity and commit an ordered root."""

    _require(audits, "no file audits supplied")
    names = tuple(audit.filename for audit in audits)
    expected_names = inventory.prefix_filenames if require_complete_public_prefix else names
    _require(names == expected_names, "file-audit order differs from the prefix inventory")
    for audit in audits:
        _require(
            inventory.md5_by_filename[audit.filename] == audit.source_md5,
            "file audit MD5 differs from the source inventory",
        )
        _require(
            audit.leaf_sha256 == _domain_digest(FILE_LEAF_DOMAIN, audit._without_leaf()),
            "file audit leaf digest differs",
        )
    for left, right in zip(audits, audits[1:], strict=False):
        _require(
            (left.last_height, left.last_multiplicity_count)
            == (right.first_height, right.first_multiplicity_count),
            "cross-file height/count continuity failed",
        )

    cuts = [audit.target_cut for audit in audits if audit.target_cut is not None]
    if require_complete_public_prefix:
        _require(len(audits) == PREFIX_FILE_COUNT, "public prefix file count differs")
        _require(audits[-1].filename == TARGET_FILE, "public prefix terminal file differs")
        _require(len(cuts) == 1, "public prefix must have exactly one target cut")
        _require(
            cuts[0].multiplicity_count_below_target == TARGET_MULTIPLICITY_COUNT,
            "public prefix target count differs",
        )

    root_input = {
        "schema": AGGREGATE_SCHEMA,
        "source_filelist_sha256": FILELIST_SHA256,
        "source_md5_manifest_sha256": MD5_MANIFEST_SHA256,
        "first_filename": audits[0].filename,
        "last_filename": audits[-1].filename,
        "file_count": len(audits),
        "first_height": audits[0].first_height,
        "last_height": audits[-1].last_height,
        "first_multiplicity_count": audits[0].first_multiplicity_count,
        "last_multiplicity_count": audits[-1].last_multiplicity_count,
        "target_height": TARGET_HEIGHT if cuts else None,
        "target_multiplicity_count": (
            cuts[0].multiplicity_count_below_target if cuts else None
        ),
        "ordered_leaf_sha256": [audit.leaf_sha256 for audit in audits],
        "classification": "source_artifact_identity_and_internal_continuity_only",
        "source_turing_completeness_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
    }
    result = dict(root_input)
    result["aggregate_sha256"] = _domain_digest(AGGREGATE_DOMAIN, root_input)
    return result
