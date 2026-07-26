# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Azure-oriented, fail-closed campaign for the public LMFDB zeta prefix.

This campaign deliberately proves less than an RH certificate.  It imports
the exact 4,766-file prefix selected by the reviewed LMFDB inventory, audits
the binary framing and multiplicity-count continuity, and retains enough
information to replay every byte-level audit.  It does *not* independently
recompute the Hardy-Z enclosures or the source Turing argument.

Consequently every artifact produced here says ``source_claim_ready=false``
and ``receipt_eligible_without_realization=false``.  A confidential-compute
wrapper may attest that this importer ran, but that attestation must not be
promoted to the finite-RH source claim without a separate realization stage.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

from tg_verifier.lmfdb_zeta_prefix import (
    FILELIST_COUNT,
    FILELIST_SHA256,
    FILELIST_SIZE,
    MD5_MANIFEST_SHA256,
    MD5_MANIFEST_SIZE,
    PREFIX_FILE_COUNT,
    SCHEMA as FILE_AUDIT_SCHEMA,
    SOURCE_DATA_URL,
    TARGET_BLOCK_BELOW_COUNT,
    TARGET_BLOCK_FIRST_COUNT,
    TARGET_BLOCK_FIRST_HEIGHT,
    TARGET_BLOCK_INDEX,
    TARGET_BLOCK_LAST_COUNT,
    TARGET_BLOCK_LAST_HEIGHT,
    TARGET_FILE,
    TARGET_FILE_BLOCKS,
    TARGET_FILE_FIRST_COUNT,
    TARGET_FILE_FIRST_HEIGHT,
    TARGET_FILE_INDEX,
    TARGET_FILE_LAST_COUNT,
    TARGET_FILE_LAST_HEIGHT,
    TARGET_FILE_MD5,
    TARGET_FILE_SHA256,
    TARGET_FILE_SIZE,
    TARGET_HEIGHT,
    TARGET_MULTIPLICITY_COUNT,
    LMFDBZetaPrefixError,
    SourceInventory,
    TargetCut,
    ZetaDataFileAudit,
    aggregate_file_audits,
    audit_data_file,
    audit_public_target_file,
    load_source_inventory,
)


PLAN_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-campaign.v1"
SHARD_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-shard-audit.v1"
REPLAY_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-shard-replay.v1"
MATERIALIZATION_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-materialization.v1"
FINAL_SCHEMA = "sparkinterval.tg.lmfdb-zeta-prefix-final.v1"

# Thirty-two source files are about three GiB for the large files.  This is a
# practical Azure disk/network unit while keeping the logical file ordering
# fixed and independent of the VM count.
FILES_PER_SHARD = 32
SHARD_COUNT = (PREFIX_FILE_COUNT + FILES_PER_SHARD - 1) // FILES_PER_SHARD
MAX_SOURCE_FILE_SIZE_BYTES = 256 * 1024 * 1024

PLAN_NAME = "campaign.json"
FINAL_NAME = "final.json"
SNAPSHOT_DIRECTORY = "reviewed-source"
SNAPSHOT_FILELIST = "filelist"
SNAPSHOT_MD5_MANIFEST = "md5sum.log"
SNAPSHOT_SPECIFICATION = "LMFDB_ZETA_PREFIX_UPSTREAM.json"

REVIEWED_SPECIFICATION_SHA256 = (
    "a0739db4fc1df1120b001a8688363c2307acc162d09851a18894feba42665703"
)
REVIEWED_SPECIFICATION_SIZE = 3_296
REVIEWED_PREFIX_INVENTORY_SHA256 = (
    "8832d6560e48041525d18a7d2ce4560c5ef07f14059599b007b8bc4e364be86b"
)
REVIEWED_PLAN_SHA256 = (
    "4a1e052f3fe9963c9f4ce0170b4ee248a3c5d4b019b903c5d80eee023453dfba"
)

# These two exact neighboring midpoint values are retained by the reviewed
# target-file audit.  They establish that no 2^-102 source interval straddles
# the integer boundary 10^10.
TARGET_PREDECESSOR_MIDPOINT_SCALED_2P102 = (
    50_706_024_008_472_293_905_172_656_473_074_529_309_074
)
TARGET_SUCCESSOR_MIDPOINT_SCALED_2P102 = (
    50_706_024_009_436_628_724_288_681_434_971_016_802_904
)

PLAN_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-plan/v1\0"
INVENTORY_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-reviewed-inventory/v1\0"
SHARD_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-shard/v1\0"
REPLAY_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-replay/v1\0"
MATERIALIZATION_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-materialization/v1\0"
FINAL_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-final/v1\0"
FILE_MERKLE_LEAF_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-file-merkle-leaf/v1\0"
FILE_MERKLE_NODE_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-file-merkle-node/v1\0"
SHARD_MERKLE_LEAF_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-shard-merkle-leaf/v1\0"
SHARD_MERKLE_NODE_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-shard-merkle-node/v1\0"
REPLAY_MERKLE_LEAF_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-replay-merkle-leaf/v1\0"
REPLAY_MERKLE_NODE_DOMAIN = b"sparkinterval/tg/lmfdb-zeta-prefix-replay-merkle-node/v1\0"

HEX32_RE = re.compile(r"[0-9a-f]{32}\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")


class LMFDBZetaPrefixCampaignError(RuntimeError):
    """The immutable plan, a shard audit, or its replay failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LMFDBZetaPrefixCampaignError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _regular_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise LMFDBZetaPrefixCampaignError(f"cannot open {path}: {error}") from error
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), f"artifact is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _load_json(path: Path) -> dict[str, Any]:
    raw = _regular_bytes(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LMFDBZetaPrefixCampaignError(f"cannot decode JSON {path}: {error}") from error
    _require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def _atomic_write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.exists(), f"refusing to replace existing artifact: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise LMFDBZetaPrefixCampaignError(
                f"artifact appeared concurrently: {path}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_size(raw: bytes) -> tuple[str, int]:
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _inventory_rows(inventory: SourceInventory) -> list[dict[str, Any]]:
    return [
        {
            "file_index": index,
            "filename": filename,
            "source_md5": inventory.md5_by_filename[filename],
        }
        for index, filename in enumerate(inventory.prefix_filenames)
    ]


def reviewed_inventory_sha256(inventory: SourceInventory) -> str:
    """Commit the exact ordered prefix names and source-published MD5s."""

    return _digest(INVENTORY_DOMAIN, _inventory_rows(inventory))


def _validate_reviewed_inventory(inventory: SourceInventory) -> None:
    _require(
        len(inventory.filenames) == FILELIST_COUNT,
        "reviewed inventory does not contain exactly 14,580 source files",
    )
    _require(
        len(inventory.prefix_filenames) == PREFIX_FILE_COUNT,
        "reviewed prefix does not contain exactly 4,766 files",
    )
    _require(inventory.prefix_filenames[0] == "zeros_14.dat", "prefix first file differs")
    _require(
        inventory.prefix_filenames[TARGET_FILE_INDEX] == TARGET_FILE,
        "prefix terminal file differs",
    )
    _require(
        inventory.md5_by_filename[TARGET_FILE] == TARGET_FILE_MD5,
        "prefix terminal source MD5 differs",
    )
    _require(
        reviewed_inventory_sha256(inventory) == REVIEWED_PREFIX_INVENTORY_SHA256,
        "ordered reviewed prefix digest differs",
    )


def _validate_specification(path: Path) -> tuple[str, int, bytes]:
    raw = _regular_bytes(path)
    sha256, size = _sha256_size(raw)
    _require(
        (sha256, size)
        == (REVIEWED_SPECIFICATION_SHA256, REVIEWED_SPECIFICATION_SIZE),
        "LMFDB prefix specification differs from the reviewed pin",
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LMFDBZetaPrefixCampaignError("reviewed specification is malformed") from error
    _require(
        value.get("kind") == "sparkinterval.pinned_lmfdb_zeta_prefix_source.v1",
        "reviewed specification kind differs",
    )
    prefix = value.get("prefix")
    trust = value.get("trust_boundary")
    _require(isinstance(prefix, dict) and isinstance(trust, dict), "specification shape differs")
    _require(
        prefix.get("file_count") == PREFIX_FILE_COUNT
        and prefix.get("target_height") == TARGET_HEIGHT
        and prefix.get("target_multiplicity_count") == TARGET_MULTIPLICITY_COUNT,
        "specification prefix geometry differs",
    )
    _require(trust.get("source_claim_ready") is False, "source claim must remain disabled")
    _require(
        trust.get("receipt_eligible_without_realization") is False,
        "receipt eligibility must remain disabled without realization",
    )
    return sha256, size, raw


def _shard_rows(inventory: SourceInventory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(SHARD_COUNT):
        lower = index * FILES_PER_SHARD
        upper = min(lower + FILES_PER_SHARD, PREFIX_FILE_COUNT)
        names = inventory.prefix_filenames[lower:upper]
        rows.append(
            {
                "shard_index": index,
                "first_file_index": lower,
                "upper_file_index_exclusive": upper,
                "file_count": upper - lower,
                "first_filename": names[0],
                "last_filename": names[-1],
            }
        )
    return rows


def create_plan(
    inventory: SourceInventory,
    *,
    specification_sha256: str = REVIEWED_SPECIFICATION_SHA256,
    specification_size: int = REVIEWED_SPECIFICATION_SIZE,
) -> dict[str, Any]:
    """Create the one production geometry; no bounded campaign mode exists."""

    _validate_reviewed_inventory(inventory)
    _require(
        (specification_sha256, specification_size)
        == (REVIEWED_SPECIFICATION_SHA256, REVIEWED_SPECIFICATION_SIZE),
        "specification identity differs from the reviewed pin",
    )
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "mode": "full_reviewed_lmfdb_prefix_internal_audit",
        "source": {
            "ordered_filelist_sha256": FILELIST_SHA256,
            "ordered_filelist_size_bytes": FILELIST_SIZE,
            "ordered_filelist_count": FILELIST_COUNT,
            "md5_manifest_sha256": MD5_MANIFEST_SHA256,
            "md5_manifest_size_bytes": MD5_MANIFEST_SIZE,
            "reviewed_prefix_inventory_sha256": REVIEWED_PREFIX_INVENTORY_SHA256,
            "specification_sha256": specification_sha256,
            "specification_size_bytes": specification_size,
            "data_base_url": SOURCE_DATA_URL,
        },
        "geometry": {
            "prefix_file_count": PREFIX_FILE_COUNT,
            "files_per_shard": FILES_PER_SHARD,
            "shard_count": SHARD_COUNT,
            "shards": _shard_rows(inventory),
        },
        "boundary": {
            "target_height": TARGET_HEIGHT,
            "target_multiplicity_count": TARGET_MULTIPLICITY_COUNT,
            "terminal_file_index": TARGET_FILE_INDEX,
            "terminal_filename": TARGET_FILE,
        },
        "trust_boundary": {
            "classification": "source_artifact_identity_and_internal_continuity_only",
            "hardy_z_realization_independently_replayed": False,
            "source_turing_completeness_independently_replayed": False,
            "source_claim_ready": False,
            "receipt_eligible_without_realization": False,
            "lean_atom_discharged": False,
        },
    }
    plan["plan_sha256"] = _digest(PLAN_DOMAIN, plan)
    _require(
        plan["plan_sha256"] == REVIEWED_PLAN_SHA256,
        "derived production plan differs from its reviewed immutable identity",
    )
    return plan


def _plan_without_digest(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def validate_plan(plan: dict[str, Any], inventory: SourceInventory) -> None:
    expected_keys = {
        "schema",
        "mode",
        "source",
        "geometry",
        "boundary",
        "trust_boundary",
        "plan_sha256",
    }
    _require(set(plan) == expected_keys and plan.get("schema") == PLAN_SCHEMA, "plan shape differs")
    _require(
        plan.get("plan_sha256") == _digest(PLAN_DOMAIN, _plan_without_digest(plan)),
        "plan digest differs",
    )
    expected = create_plan(inventory)
    _require(plan == expected, "plan values differ from the immutable reviewed geometry")


def shard_file_range(plan: dict[str, Any], index: int) -> tuple[int, int]:
    _require(isinstance(index, int), "shard index must be an integer")
    _require(0 <= index < SHARD_COUNT, "shard index is outside the immutable plan")
    row = plan["geometry"]["shards"][index]
    _require(row["shard_index"] == index, "shard table index differs")
    return row["first_file_index"], row["upper_file_index_exclusive"]


def _snapshot_paths(directory: Path) -> tuple[Path, Path, Path]:
    root = directory / SNAPSHOT_DIRECTORY
    return (
        root / SNAPSHOT_FILELIST,
        root / SNAPSHOT_MD5_MANIFEST,
        root / SNAPSHOT_SPECIFICATION,
    )


def initialize_campaign(
    *,
    output_directory: Path,
    filelist: Path,
    md5_manifest: Path,
    source_specification: Path,
) -> dict[str, Any]:
    """Snapshot the small reviewed manifests and create the immutable plan."""

    inventory = load_source_inventory(filelist, md5_manifest)
    _validate_reviewed_inventory(inventory)
    specification_sha, specification_size, specification_raw = _validate_specification(
        source_specification
    )
    plan = create_plan(
        inventory,
        specification_sha256=specification_sha,
        specification_size=specification_size,
    )
    _require(
        not output_directory.exists() or not any(output_directory.iterdir()),
        "campaign output directory must be empty",
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    snapshot_filelist, snapshot_md5, snapshot_spec = _snapshot_paths(output_directory)
    _atomic_write_new(snapshot_filelist, _regular_bytes(filelist))
    _atomic_write_new(snapshot_md5, _regular_bytes(md5_manifest))
    _atomic_write_new(snapshot_spec, specification_raw)
    _atomic_write_new(output_directory / PLAN_NAME, _canonical(plan) + b"\n")
    return plan


def load_campaign(directory: Path) -> tuple[dict[str, Any], SourceInventory]:
    snapshot_filelist, snapshot_md5, snapshot_spec = _snapshot_paths(directory)
    inventory = load_source_inventory(snapshot_filelist, snapshot_md5)
    _validate_reviewed_inventory(inventory)
    _validate_specification(snapshot_spec)
    plan = _load_json(directory / PLAN_NAME)
    validate_plan(plan, inventory)
    return plan, inventory


def _ordered_merkle_root(
    digests: list[str], *, leaf_domain: bytes, node_domain: bytes
) -> str:
    _require(digests, "cannot Merkle-aggregate an empty sequence")
    level: list[bytes] = []
    for index, digest in enumerate(digests):
        _require(HEX64_RE.fullmatch(digest) is not None, "Merkle leaf digest is malformed")
        level.append(
            hashlib.sha256(
                leaf_domain + index.to_bytes(8, "big") + bytes.fromhex(digest)
            ).digest()
        )
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(node_domain + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def _receipt_path(directory: Path, index: int) -> Path:
    return directory / "receipts" / f"shard-{index:04d}.json"


def _replay_path(directory: Path, index: int) -> Path:
    return directory / "replays" / f"shard-{index:04d}.json"


def _materialization_path(directory: Path, index: int) -> Path:
    return directory / "materializations" / f"shard-{index:04d}.json"


def _audit_expected_files(
    *,
    plan: dict[str, Any],
    inventory: SourceInventory,
    data_directory: Path,
    index: int,
) -> list[ZetaDataFileAudit]:
    lower, upper = shard_file_range(plan, index)
    expected_names = inventory.prefix_filenames[lower:upper]
    audits: list[ZetaDataFileAudit] = []
    for filename in expected_names:
        path = data_directory / filename
        if filename == TARGET_FILE:
            audit = audit_public_target_file(path, inventory)
        else:
            audit = audit_data_file(
                path,
                expected_filename=filename,
                expected_md5=inventory.md5_by_filename[filename],
            )
        audits.append(audit)
    return audits


def _aggregate_audits(
    audits: list[ZetaDataFileAudit],
    *,
    inventory: SourceInventory,
    require_complete_public_prefix: bool,
) -> dict[str, Any]:
    try:
        return aggregate_file_audits(
            audits,
            inventory=inventory,
            require_complete_public_prefix=require_complete_public_prefix,
        )
    except LMFDBZetaPrefixError as error:
        raise LMFDBZetaPrefixCampaignError(str(error)) from error


def _make_shard_receipt(
    *,
    plan: dict[str, Any],
    inventory: SourceInventory,
    index: int,
    audits: list[ZetaDataFileAudit],
    elapsed_nanoseconds: int,
) -> dict[str, Any]:
    lower, upper = shard_file_range(plan, index)
    expected_names = inventory.prefix_filenames[lower:upper]
    _require(
        tuple(audit.filename for audit in audits) == expected_names,
        "shard audit order differs from its deterministic file range",
    )
    aggregate = _aggregate_audits(
        audits, inventory=inventory, require_complete_public_prefix=False
    )
    cuts = [audit.target_cut for audit in audits if audit.target_cut is not None]
    receipt: dict[str, Any] = {
        "schema": SHARD_SCHEMA,
        "classification": "source_artifact_identity_and_internal_continuity_only",
        "plan_sha256": plan["plan_sha256"],
        "reviewed_prefix_inventory_sha256": REVIEWED_PREFIX_INVENTORY_SHA256,
        "shard_index": index,
        "first_file_index": lower,
        "upper_file_index_exclusive": upper,
        "file_count": upper - lower,
        "first_filename": audits[0].filename,
        "last_filename": audits[-1].filename,
        "first_height": audits[0].first_height,
        "last_height": audits[-1].last_height,
        "first_multiplicity_count": audits[0].first_multiplicity_count,
        "last_multiplicity_count": audits[-1].last_multiplicity_count,
        "encoded_multiplicity_slots": sum(
            audit.encoded_multiplicity_slots for audit in audits
        ),
        "total_size_bytes": sum(audit.size_bytes for audit in audits),
        "target_multiplicity_count": (
            cuts[0].multiplicity_count_below_target if cuts else None
        ),
        "file_audits": [audit.as_json() for audit in audits],
        "ordered_file_merkle_root_sha256": _ordered_merkle_root(
            [audit.leaf_sha256 for audit in audits],
            leaf_domain=FILE_MERKLE_LEAF_DOMAIN,
            node_domain=FILE_MERKLE_NODE_DOMAIN,
        ),
        "within_shard_aggregate_sha256": aggregate["aggregate_sha256"],
        "elapsed_nanoseconds": elapsed_nanoseconds,
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    semantic = {
        key: value
        for key, value in receipt.items()
        if key != "elapsed_nanoseconds"
    }
    receipt["receipt_sha256"] = _digest(SHARD_DOMAIN, semantic)
    return receipt


_AUDIT_KEYS = {
    "schema",
    "filename",
    "source_md5",
    "sha256",
    "size_bytes",
    "block_count",
    "first_height",
    "last_height",
    "first_multiplicity_count",
    "last_multiplicity_count",
    "encoded_multiplicity_slots",
    "target_cut",
    "leaf_sha256",
}
_TARGET_CUT_KEYS = {
    "block_index",
    "block_first_height",
    "block_last_height",
    "block_first_count",
    "block_last_count",
    "below_in_block",
    "multiplicity_count_below_target",
    "predecessor_midpoint_scaled_2p102",
    "successor_midpoint_scaled_2p102",
}


def _parse_audit(value: object) -> ZetaDataFileAudit:
    _require(isinstance(value, dict) and set(value) == _AUDIT_KEYS, "file audit shape differs")
    _require(value.get("schema") == FILE_AUDIT_SCHEMA, "file audit schema differs")
    _require(isinstance(value.get("filename"), str), "file audit filename is malformed")
    _require(HEX32_RE.fullmatch(value.get("source_md5", "")) is not None, "file MD5 is malformed")
    _require(HEX64_RE.fullmatch(value.get("sha256", "")) is not None, "file SHA-256 is malformed")
    _require(HEX64_RE.fullmatch(value.get("leaf_sha256", "")) is not None, "file leaf is malformed")
    integer_fields = (
        "size_bytes",
        "block_count",
        "first_height",
        "last_height",
        "first_multiplicity_count",
        "last_multiplicity_count",
        "encoded_multiplicity_slots",
    )
    for key in integer_fields:
        _require(type(value.get(key)) is int and value[key] >= 0, f"file {key} is malformed")
    _require(value["size_bytes"] > 0 and value["block_count"] > 0, "empty file audit")
    _require(value["first_height"] < value["last_height"], "file heights do not increase")
    _require(
        value["first_multiplicity_count"] <= value["last_multiplicity_count"],
        "file counts decrease",
    )
    _require(
        value["encoded_multiplicity_slots"]
        == value["last_multiplicity_count"] - value["first_multiplicity_count"],
        "file encoded slots do not telescope",
    )
    cut_value = value["target_cut"]
    cut: TargetCut | None = None
    if cut_value is not None:
        _require(
            isinstance(cut_value, dict) and set(cut_value) == _TARGET_CUT_KEYS,
            "target-cut shape differs",
        )
        _require(
            all(type(cut_value[key]) is int and cut_value[key] >= 0 for key in _TARGET_CUT_KEYS),
            "target-cut integer is malformed",
        )
        cut = TargetCut(**cut_value)
    return ZetaDataFileAudit(
        filename=value["filename"],
        source_md5=value["source_md5"],
        sha256=value["sha256"],
        size_bytes=value["size_bytes"],
        block_count=value["block_count"],
        first_height=value["first_height"],
        last_height=value["last_height"],
        first_multiplicity_count=value["first_multiplicity_count"],
        last_multiplicity_count=value["last_multiplicity_count"],
        encoded_multiplicity_slots=value["encoded_multiplicity_slots"],
        target_cut=cut,
        leaf_sha256=value["leaf_sha256"],
    )


def _validate_terminal_audit(audit: ZetaDataFileAudit) -> None:
    _require(audit.filename == TARGET_FILE, "terminal audit filename differs")
    _require(audit.source_md5 == TARGET_FILE_MD5, "terminal source MD5 differs")
    _require(audit.sha256 == TARGET_FILE_SHA256, "terminal SHA-256 differs")
    _require(audit.size_bytes == TARGET_FILE_SIZE, "terminal file size differs")
    _require(audit.block_count == TARGET_FILE_BLOCKS, "terminal block count differs")
    _require(
        (audit.first_height, audit.first_multiplicity_count)
        == (TARGET_FILE_FIRST_HEIGHT, TARGET_FILE_FIRST_COUNT),
        "terminal initial header differs",
    )
    _require(
        (audit.last_height, audit.last_multiplicity_count)
        == (TARGET_FILE_LAST_HEIGHT, TARGET_FILE_LAST_COUNT),
        "terminal final header differs",
    )
    cut = audit.target_cut
    _require(cut is not None, "terminal target cut is absent")
    _require(
        (
            cut.block_index,
            cut.block_first_height,
            cut.block_last_height,
            cut.block_first_count,
            cut.block_last_count,
            cut.below_in_block,
            cut.multiplicity_count_below_target,
            cut.predecessor_midpoint_scaled_2p102,
            cut.successor_midpoint_scaled_2p102,
        )
        == (
            TARGET_BLOCK_INDEX,
            TARGET_BLOCK_FIRST_HEIGHT,
            TARGET_BLOCK_LAST_HEIGHT,
            TARGET_BLOCK_FIRST_COUNT,
            TARGET_BLOCK_LAST_COUNT,
            TARGET_BLOCK_BELOW_COUNT,
            TARGET_MULTIPLICITY_COUNT,
            TARGET_PREDECESSOR_MIDPOINT_SCALED_2P102,
            TARGET_SUCCESSOR_MIDPOINT_SCALED_2P102,
        ),
        "terminal exact target cut differs",
    )


_SHARD_KEYS = {
    "schema",
    "classification",
    "plan_sha256",
    "reviewed_prefix_inventory_sha256",
    "shard_index",
    "first_file_index",
    "upper_file_index_exclusive",
    "file_count",
    "first_filename",
    "last_filename",
    "first_height",
    "last_height",
    "first_multiplicity_count",
    "last_multiplicity_count",
    "encoded_multiplicity_slots",
    "total_size_bytes",
    "target_multiplicity_count",
    "file_audits",
    "ordered_file_merkle_root_sha256",
    "within_shard_aggregate_sha256",
    "elapsed_nanoseconds",
    "source_turing_completeness_independently_replayed",
    "hardy_z_realization_independently_replayed",
    "source_claim_ready",
    "receipt_eligible_without_realization",
    "lean_atom_discharged",
    "accepted",
    "receipt_sha256",
}


def validate_shard_receipt(
    receipt: dict[str, Any],
    *,
    plan: dict[str, Any],
    inventory: SourceInventory,
    index: int,
) -> list[ZetaDataFileAudit]:
    _require(set(receipt) == _SHARD_KEYS and receipt.get("schema") == SHARD_SCHEMA, "shard receipt shape differs")
    lower, upper = shard_file_range(plan, index)
    expected_names = inventory.prefix_filenames[lower:upper]
    fixed = {
        "classification": "source_artifact_identity_and_internal_continuity_only",
        "plan_sha256": plan["plan_sha256"],
        "reviewed_prefix_inventory_sha256": REVIEWED_PREFIX_INVENTORY_SHA256,
        "shard_index": index,
        "first_file_index": lower,
        "upper_file_index_exclusive": upper,
        "file_count": upper - lower,
        "first_filename": expected_names[0],
        "last_filename": expected_names[-1],
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    _require(all(receipt.get(key) == value for key, value in fixed.items()), "shard receipt fixed field differs")
    _require(
        type(receipt.get("elapsed_nanoseconds")) is int
        and receipt["elapsed_nanoseconds"] >= 0,
        "shard elapsed time is malformed",
    )
    file_values = receipt.get("file_audits")
    _require(isinstance(file_values, list) and len(file_values) == upper - lower, "shard file-audit count differs")
    audits = [_parse_audit(value) for value in file_values]
    _require(tuple(audit.filename for audit in audits) == expected_names, "shard file order differs")
    for audit in audits:
        _require(
            audit.filename in inventory.md5_by_filename,
            "shard filename is absent from the reviewed inventory",
        )
        _require(
            inventory.md5_by_filename[audit.filename] == audit.source_md5,
            "shard file source MD5 differs from the reviewed manifest",
        )
    if upper == PREFIX_FILE_COUNT:
        _validate_terminal_audit(audits[-1])
    else:
        _require(all(audit.target_cut is None for audit in audits), "nonterminal shard contains a target cut")
    aggregate = _aggregate_audits(
        audits, inventory=inventory, require_complete_public_prefix=False
    )
    summaries = {
        "first_height": audits[0].first_height,
        "last_height": audits[-1].last_height,
        "first_multiplicity_count": audits[0].first_multiplicity_count,
        "last_multiplicity_count": audits[-1].last_multiplicity_count,
        "encoded_multiplicity_slots": sum(audit.encoded_multiplicity_slots for audit in audits),
        "total_size_bytes": sum(audit.size_bytes for audit in audits),
        "target_multiplicity_count": (
            audits[-1].target_cut.multiplicity_count_below_target
            if audits[-1].target_cut is not None
            else None
        ),
        "ordered_file_merkle_root_sha256": _ordered_merkle_root(
            [audit.leaf_sha256 for audit in audits],
            leaf_domain=FILE_MERKLE_LEAF_DOMAIN,
            node_domain=FILE_MERKLE_NODE_DOMAIN,
        ),
        "within_shard_aggregate_sha256": aggregate["aggregate_sha256"],
    }
    _require(all(receipt.get(key) == value for key, value in summaries.items()), "shard header summary differs")
    _require(HEX64_RE.fullmatch(receipt.get("receipt_sha256", "")) is not None, "receipt digest is malformed")
    semantic = {
        key: value
        for key, value in receipt.items()
        if key not in ("elapsed_nanoseconds", "receipt_sha256")
    }
    _require(receipt["receipt_sha256"] == _digest(SHARD_DOMAIN, semantic), "receipt digest differs")
    return audits


def run_shard(directory: Path, data_directory: Path, index: int) -> dict[str, Any]:
    plan, inventory = load_campaign(directory)
    output = _receipt_path(directory, index)
    _require(not output.exists(), "shard receipt already exists")
    before = time.monotonic_ns()
    try:
        audits = _audit_expected_files(
            plan=plan,
            inventory=inventory,
            data_directory=data_directory,
            index=index,
        )
    except LMFDBZetaPrefixError as error:
        raise LMFDBZetaPrefixCampaignError(str(error)) from error
    receipt = _make_shard_receipt(
        plan=plan,
        inventory=inventory,
        index=index,
        audits=audits,
        elapsed_nanoseconds=time.monotonic_ns() - before,
    )
    validate_shard_receipt(receipt, plan=plan, inventory=inventory, index=index)
    _atomic_write_new(output, _canonical(receipt) + b"\n")
    return receipt


_REPLAY_KEYS = {
    "schema",
    "classification",
    "plan_sha256",
    "shard_index",
    "retained_receipt_sha256",
    "fresh_receipt_sha256",
    "semantic_replay_identical",
    "file_audits",
    "ordered_file_merkle_root_sha256",
    "elapsed_nanoseconds",
    "source_turing_completeness_independently_replayed",
    "hardy_z_realization_independently_replayed",
    "source_claim_ready",
    "receipt_eligible_without_realization",
    "lean_atom_discharged",
    "accepted",
    "replay_sha256",
}


def _make_replay_receipt(
    *, retained: dict[str, Any], fresh: dict[str, Any], elapsed_nanoseconds: int
) -> dict[str, Any]:
    stable_retained = {
        key: value
        for key, value in retained.items()
        if key not in ("elapsed_nanoseconds", "receipt_sha256")
    }
    stable_fresh = {
        key: value
        for key, value in fresh.items()
        if key not in ("elapsed_nanoseconds", "receipt_sha256")
    }
    _require(stable_fresh == stable_retained, "fresh shard semantic replay differs")
    replay: dict[str, Any] = {
        "schema": REPLAY_SCHEMA,
        "classification": "independent_byte_level_replay_of_source_artifact_audit_only",
        "plan_sha256": retained["plan_sha256"],
        "shard_index": retained["shard_index"],
        "retained_receipt_sha256": retained["receipt_sha256"],
        "fresh_receipt_sha256": fresh["receipt_sha256"],
        "semantic_replay_identical": True,
        "file_audits": fresh["file_audits"],
        "ordered_file_merkle_root_sha256": fresh["ordered_file_merkle_root_sha256"],
        "elapsed_nanoseconds": elapsed_nanoseconds,
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    semantic = {key: value for key, value in replay.items() if key != "elapsed_nanoseconds"}
    replay["replay_sha256"] = _digest(REPLAY_DOMAIN, semantic)
    return replay


def validate_replay_receipt(
    replay: dict[str, Any],
    *,
    retained: dict[str, Any],
    plan: dict[str, Any],
    inventory: SourceInventory,
    index: int,
) -> None:
    _require(set(replay) == _REPLAY_KEYS and replay.get("schema") == REPLAY_SCHEMA, "replay receipt shape differs")
    retained_audits = validate_shard_receipt(
        retained, plan=plan, inventory=inventory, index=index
    )
    fixed = {
        "classification": "independent_byte_level_replay_of_source_artifact_audit_only",
        "plan_sha256": plan["plan_sha256"],
        "shard_index": index,
        "retained_receipt_sha256": retained["receipt_sha256"],
        "fresh_receipt_sha256": retained["receipt_sha256"],
        "semantic_replay_identical": True,
        "ordered_file_merkle_root_sha256": retained["ordered_file_merkle_root_sha256"],
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    _require(all(replay.get(key) == value for key, value in fixed.items()), "replay fixed field differs")
    _require(
        type(replay.get("elapsed_nanoseconds")) is int
        and replay["elapsed_nanoseconds"] >= 0,
        "replay elapsed time is malformed",
    )
    replay_audits = [_parse_audit(value) for value in replay.get("file_audits", [])]
    _require(replay_audits == retained_audits, "replay file audits differ from retained audit")
    semantic = {
        key: value
        for key, value in replay.items()
        if key not in ("elapsed_nanoseconds", "replay_sha256")
    }
    _require(
        HEX64_RE.fullmatch(replay.get("replay_sha256", "")) is not None
        and replay["replay_sha256"] == _digest(REPLAY_DOMAIN, semantic),
        "replay digest differs",
    )


def replay_shard(directory: Path, data_directory: Path, index: int) -> dict[str, Any]:
    plan, inventory = load_campaign(directory)
    output = _replay_path(directory, index)
    _require(not output.exists(), "shard replay already exists")
    retained = _load_json(_receipt_path(directory, index))
    validate_shard_receipt(retained, plan=plan, inventory=inventory, index=index)
    before = time.monotonic_ns()
    try:
        audits = _audit_expected_files(
            plan=plan,
            inventory=inventory,
            data_directory=data_directory,
            index=index,
        )
    except LMFDBZetaPrefixError as error:
        raise LMFDBZetaPrefixCampaignError(str(error)) from error
    fresh = _make_shard_receipt(
        plan=plan,
        inventory=inventory,
        index=index,
        audits=audits,
        elapsed_nanoseconds=time.monotonic_ns() - before,
    )
    replay = _make_replay_receipt(
        retained=retained,
        fresh=fresh,
        elapsed_nanoseconds=fresh["elapsed_nanoseconds"],
    )
    validate_replay_receipt(
        replay,
        retained=retained,
        plan=plan,
        inventory=inventory,
        index=index,
    )
    _atomic_write_new(output, _canonical(replay) + b"\n")
    return replay


def campaign_status(directory: Path) -> dict[str, Any]:
    plan, inventory = load_campaign(directory)
    audited = 0
    replayed = 0
    for index in range(SHARD_COUNT):
        receipt_path = _receipt_path(directory, index)
        if not receipt_path.exists():
            continue
        receipt = _load_json(receipt_path)
        validate_shard_receipt(receipt, plan=plan, inventory=inventory, index=index)
        audited += 1
        replay_path = _replay_path(directory, index)
        if replay_path.exists():
            validate_replay_receipt(
                _load_json(replay_path),
                retained=receipt,
                plan=plan,
                inventory=inventory,
                index=index,
            )
            replayed += 1
    return {
        "accepted": True,
        "classification": "lmfdb_prefix_internal_audit_campaign_status",
        "plan_sha256": plan["plan_sha256"],
        "prefix_file_count": PREFIX_FILE_COUNT,
        "shard_count": SHARD_COUNT,
        "audited_shards": audited,
        "replayed_shards": replayed,
        "complete": audited == SHARD_COUNT and replayed == SHARD_COUNT,
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
    }


def _require_exact_artifact_set(directory: Path, kind: str) -> None:
    root = directory / kind
    _require(root.is_dir() and not root.is_symlink(), f"missing safe {kind} directory")
    expected = {f"shard-{index:04d}.json" for index in range(SHARD_COUNT)}
    actual = {path.name for path in root.iterdir()}
    _require(actual == expected, f"{kind} set is missing, duplicated, or has extra artifacts")


def finalize_campaign(directory: Path) -> dict[str, Any]:
    plan, inventory = load_campaign(directory)
    _require(not (directory / FINAL_NAME).exists(), "final artifact already exists")
    _require_exact_artifact_set(directory, "receipts")
    _require_exact_artifact_set(directory, "replays")
    receipts: list[dict[str, Any]] = []
    replays: list[dict[str, Any]] = []
    all_audits: list[ZetaDataFileAudit] = []
    for index in range(SHARD_COUNT):
        receipt = _load_json(_receipt_path(directory, index))
        audits = validate_shard_receipt(
            receipt, plan=plan, inventory=inventory, index=index
        )
        replay = _load_json(_replay_path(directory, index))
        validate_replay_receipt(
            replay,
            retained=receipt,
            plan=plan,
            inventory=inventory,
            index=index,
        )
        receipts.append(receipt)
        replays.append(replay)
        all_audits.extend(audits)
    _require(len(all_audits) == PREFIX_FILE_COUNT, "final file audit count differs")
    for left, right in zip(receipts, receipts[1:], strict=False):
        _require(
            left["upper_file_index_exclusive"] == right["first_file_index"]
            and left["last_height"] == right["first_height"]
            and left["last_multiplicity_count"]
            == right["first_multiplicity_count"],
            "cross-shard height/count continuity failed",
        )
    aggregate = _aggregate_audits(
        all_audits,
        inventory=inventory,
        require_complete_public_prefix=True,
    )
    terminal = all_audits[-1]
    _validate_terminal_audit(terminal)
    assert terminal.target_cut is not None
    _require(
        terminal.target_cut.multiplicity_count_below_target
        == TARGET_MULTIPLICITY_COUNT,
        "terminal N(10^10) differs",
    )
    result: dict[str, Any] = {
        "schema": FINAL_SCHEMA,
        "classification": "complete_source_artifact_identity_and_internal_continuity_audit_only",
        "plan_sha256": plan["plan_sha256"],
        "reviewed_prefix_inventory_sha256": REVIEWED_PREFIX_INVENTORY_SHA256,
        "prefix_file_count": PREFIX_FILE_COUNT,
        "shard_count": SHARD_COUNT,
        "first_filename": all_audits[0].filename,
        "last_filename": terminal.filename,
        "first_height": all_audits[0].first_height,
        "last_file_height": terminal.last_height,
        "first_multiplicity_count": all_audits[0].first_multiplicity_count,
        "last_file_multiplicity_count": terminal.last_multiplicity_count,
        "target_height": TARGET_HEIGHT,
        "target_multiplicity_count": TARGET_MULTIPLICITY_COUNT,
        "cross_shard_height_count_continuity_verified": True,
        "all_file_sha256_and_source_md5_retained": True,
        "all_exact_file_header_summaries_retained": True,
        "ordered_file_merkle_root_sha256": _ordered_merkle_root(
            [audit.leaf_sha256 for audit in all_audits],
            leaf_domain=FILE_MERKLE_LEAF_DOMAIN,
            node_domain=FILE_MERKLE_NODE_DOMAIN,
        ),
        "ordered_shard_receipt_merkle_root_sha256": _ordered_merkle_root(
            [receipt["receipt_sha256"] for receipt in receipts],
            leaf_domain=SHARD_MERKLE_LEAF_DOMAIN,
            node_domain=SHARD_MERKLE_NODE_DOMAIN,
        ),
        "ordered_replay_merkle_root_sha256": _ordered_merkle_root(
            [replay["replay_sha256"] for replay in replays],
            leaf_domain=REPLAY_MERKLE_LEAF_DOMAIN,
            node_domain=REPLAY_MERKLE_NODE_DOMAIN,
        ),
        "source_artifact_aggregate_sha256": aggregate["aggregate_sha256"],
        "source_turing_completeness_independently_replayed": False,
        "hardy_z_realization_independently_replayed": False,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    result["final_sha256"] = _digest(FINAL_DOMAIN, result)
    _atomic_write_new(directory / FINAL_NAME, _canonical(result) + b"\n")
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # type: ignore[no-untyped-def]
        raise LMFDBZetaPrefixCampaignError(
            f"source download redirected unexpectedly ({code}) to {new_url}"
        )


def _download_one(
    *,
    destination: Path,
    filename: str,
    expected_md5: str,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Download one exact basename to an atomic local file and hash it twice."""

    _require(re.fullmatch(r"zeros_(0|[1-9][0-9]*)\.dat", filename) is not None, "download filename is malformed")
    _require(HEX32_RE.fullmatch(expected_md5) is not None, "download source MD5 is malformed")
    _require(timeout_seconds > 0, "download timeout must be positive")
    _require(not destination.exists(), f"download destination already exists: {destination}")
    expected_url = f"{SOURCE_DATA_URL}/{urllib.parse.quote(filename, safe='')}"
    request = urllib.request.Request(
        expected_url,
        headers={
            "Accept-Encoding": "identity",
            "Cookie": "human=1",
            "User-Agent": "SparkInterval-LMFDB-prefix-auditor/1",
        },
        method="GET",
    )
    open_request = opener
    if open_request is None:
        open_request = urllib.request.build_opener(_NoRedirect()).open
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{filename}.", suffix=".part", dir=destination.parent
    )
    temporary = Path(temporary_name)
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    total = 0
    etag: str | None = None
    last_modified: str | None = None
    try:
        try:
            response_context = open_request(request, timeout=timeout_seconds)
            with response_context as response:
                status = getattr(response, "status", None)
                _require(status == 200, f"source download returned HTTP {status}")
                _require(response.geturl() == expected_url, "source download final URL differs")
                length_text = response.headers.get("Content-Length")
                expected_length: int | None = None
                if length_text is not None:
                    _require(length_text.isdigit(), "source Content-Length is malformed")
                    expected_length = int(length_text)
                    _require(
                        0 < expected_length <= MAX_SOURCE_FILE_SIZE_BYTES,
                        "source Content-Length is outside the campaign limit",
                    )
                etag = response.headers.get("ETag")
                last_modified = response.headers.get("Last-Modified")
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = -1
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        _require(
                            total <= MAX_SOURCE_FILE_SIZE_BYTES,
                            "source file exceeds the campaign size limit",
                        )
                        md5.update(chunk)
                        sha256.update(chunk)
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                _require(total > 0, "source download is empty")
                if expected_length is not None:
                    _require(total == expected_length, "source download length differs")
        except LMFDBZetaPrefixCampaignError:
            raise
        except (OSError, urllib.error.URLError) as error:
            raise LMFDBZetaPrefixCampaignError(
                f"source download failed for {filename}: {error}"
            ) from error
        _require(md5.hexdigest() == expected_md5, "downloaded source MD5 differs")
        actual_sha256 = sha256.hexdigest()
        if filename == TARGET_FILE:
            _require(
                actual_sha256 == TARGET_FILE_SHA256 and total == TARGET_FILE_SIZE,
                "downloaded terminal file differs from its reviewed SHA-256 pin",
            )
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise LMFDBZetaPrefixCampaignError(
                f"download destination appeared concurrently: {destination}"
            ) from error
        return {
            "filename": filename,
            "source_url": expected_url,
            "source_md5": expected_md5,
            "sha256": actual_sha256,
            "size_bytes": total,
            "etag": etag,
            "last_modified": last_modified,
        }
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _safe_data_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)
    _require(path.is_dir() and not path.is_symlink(), "data directory is not a safe directory")


def _audit_materialized_file(
    path: Path, filename: str, inventory: SourceInventory
) -> ZetaDataFileAudit:
    try:
        return (
            audit_public_target_file(path, inventory)
            if filename == TARGET_FILE
            else audit_data_file(
                path,
                expected_filename=filename,
                expected_md5=inventory.md5_by_filename[filename],
            )
        )
    except LMFDBZetaPrefixError as error:
        raise LMFDBZetaPrefixCampaignError(str(error)) from error


def materialize_shard(
    directory: Path,
    data_directory: Path,
    index: int,
    *,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Materialize one deterministic shard; never schedules the full corpus."""

    plan, inventory = load_campaign(directory)
    output = _materialization_path(directory, index)
    _require(not output.exists(), "shard materialization receipt already exists")
    _safe_data_directory(data_directory)
    lower, upper = shard_file_range(plan, index)
    records: list[dict[str, Any]] = []
    for filename in inventory.prefix_filenames[lower:upper]:
        destination = data_directory / filename
        if destination.exists():
            _require(not destination.is_symlink() and destination.is_file(), "existing source file is unsafe")
            audit = _audit_materialized_file(destination, filename, inventory)
            records.append(
                {
                    "filename": filename,
                    "source_url": f"{SOURCE_DATA_URL}/{filename}",
                    "source_md5": audit.source_md5,
                    "sha256": audit.sha256,
                    "size_bytes": audit.size_bytes,
                    "etag": None,
                    "last_modified": None,
                }
            )
        else:
            downloaded = _download_one(
                destination=destination,
                filename=filename,
                expected_md5=inventory.md5_by_filename[filename],
                timeout_seconds=timeout_seconds,
            )
            audit = _audit_materialized_file(destination, filename, inventory)
            _require(
                (
                    downloaded["source_md5"],
                    downloaded["sha256"],
                    downloaded["size_bytes"],
                )
                == (audit.source_md5, audit.sha256, audit.size_bytes),
                "post-download framing audit identity differs",
            )
            records.append(downloaded)
    result: dict[str, Any] = {
        "schema": MATERIALIZATION_SCHEMA,
        "classification": "source_file_materialization_not_a_mathematical_receipt",
        "plan_sha256": plan["plan_sha256"],
        "shard_index": index,
        "first_file_index": lower,
        "upper_file_index_exclusive": upper,
        "files": records,
        "source_claim_ready": False,
        "receipt_eligible_without_realization": False,
        "accepted": True,
    }
    result["materialization_sha256"] = _digest(MATERIALIZATION_DOMAIN, result)
    _atomic_write_new(output, _canonical(result) + b"\n")
    return result


__all__ = [
    "FILES_PER_SHARD",
    "FINAL_SCHEMA",
    "LMFDBZetaPrefixCampaignError",
    "MAX_SOURCE_FILE_SIZE_BYTES",
    "PLAN_SCHEMA",
    "REPLAY_SCHEMA",
    "REVIEWED_PREFIX_INVENTORY_SHA256",
    "REVIEWED_PLAN_SHA256",
    "SHARD_COUNT",
    "SHARD_SCHEMA",
    "campaign_status",
    "create_plan",
    "finalize_campaign",
    "initialize_campaign",
    "load_campaign",
    "materialize_shard",
    "replay_shard",
    "reviewed_inventory_sha256",
    "run_shard",
    "shard_file_range",
    "validate_plan",
    "validate_replay_receipt",
    "validate_shard_receipt",
]
