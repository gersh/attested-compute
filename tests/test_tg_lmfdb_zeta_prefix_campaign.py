# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import tg_verifier.lmfdb_zeta_prefix_campaign as campaign
from tg_verifier.lmfdb_zeta_prefix import (
    FILELIST_COUNT,
    FILE_LEAF_DOMAIN,
    PREFIX_FILE_COUNT,
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
    TARGET_FILE_LAST_COUNT,
    TARGET_FILE_LAST_HEIGHT,
    TARGET_FILE_MD5,
    TARGET_FILE_SHA256,
    TARGET_FILE_SIZE,
    TARGET_HEIGHT,
    TARGET_MULTIPLICITY_COUNT,
    SourceInventory,
    TargetCut,
    ZetaDataFileAudit,
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def with_leaf(audit: ZetaDataFileAudit) -> ZetaDataFileAudit:
    leaf = hashlib.sha256(FILE_LEAF_DOMAIN + canonical(audit._without_leaf())).hexdigest()
    return replace(audit, leaf_sha256=leaf)


def synthetic_inventory() -> SourceInventory:
    prefix = ["zeros_14.dat"]
    prefix.extend(f"zeros_{1_000_000 + index * 1_000}.dat" for index in range(1, PREFIX_FILE_COUNT - 1))
    prefix.append(TARGET_FILE)
    suffix = [
        f"zeros_{10_000_646_000 + index * 2_100_000}.dat"
        for index in range(FILELIST_COUNT - PREFIX_FILE_COUNT)
    ]
    filenames = tuple(prefix + suffix)
    md5s = {
        filename: hashlib.md5(filename.encode(), usedforsecurity=False).hexdigest()
        for filename in filenames
    }
    md5s[TARGET_FILE] = TARGET_FILE_MD5
    return SourceInventory(filenames=filenames, md5_by_filename=md5s)


def synthetic_plan(inventory: SourceInventory) -> dict[str, object]:
    shards = []
    for index in range(campaign.SHARD_COUNT):
        lower = index * campaign.FILES_PER_SHARD
        upper = min(lower + campaign.FILES_PER_SHARD, PREFIX_FILE_COUNT)
        names = inventory.prefix_filenames[lower:upper]
        shards.append(
            {
                "shard_index": index,
                "first_file_index": lower,
                "upper_file_index_exclusive": upper,
                "file_count": upper - lower,
                "first_filename": names[0],
                "last_filename": names[-1],
            }
        )
    return {
        "plan_sha256": "4" * 64,
        "geometry": {"shards": shards},
    }


def synthetic_audits(inventory: SourceInventory) -> list[ZetaDataFileAudit]:
    audits: list[ZetaDataFileAudit] = []
    for index, filename in enumerate(inventory.prefix_filenames[:-1]):
        first_height = TARGET_FILE_FIRST_HEIGHT * index // (PREFIX_FILE_COUNT - 1)
        last_height = TARGET_FILE_FIRST_HEIGHT * (index + 1) // (PREFIX_FILE_COUNT - 1)
        first_count = TARGET_FILE_FIRST_COUNT * index // (PREFIX_FILE_COUNT - 1)
        last_count = TARGET_FILE_FIRST_COUNT * (index + 1) // (PREFIX_FILE_COUNT - 1)
        audits.append(
            with_leaf(
                ZetaDataFileAudit(
                    filename=filename,
                    source_md5=inventory.md5_by_filename[filename],
                    sha256=hashlib.sha256(filename.encode()).hexdigest(),
                    size_bytes=64 + index,
                    block_count=1,
                    first_height=first_height,
                    last_height=last_height,
                    first_multiplicity_count=first_count,
                    last_multiplicity_count=last_count,
                    encoded_multiplicity_slots=last_count - first_count,
                    target_cut=None,
                    leaf_sha256="0" * 64,
                )
            )
        )
    target_cut = TargetCut(
        block_index=TARGET_BLOCK_INDEX,
        block_first_height=TARGET_BLOCK_FIRST_HEIGHT,
        block_last_height=TARGET_BLOCK_LAST_HEIGHT,
        block_first_count=TARGET_BLOCK_FIRST_COUNT,
        block_last_count=TARGET_BLOCK_LAST_COUNT,
        below_in_block=TARGET_BLOCK_BELOW_COUNT,
        multiplicity_count_below_target=TARGET_MULTIPLICITY_COUNT,
        predecessor_midpoint_scaled_2p102=(
            campaign.TARGET_PREDECESSOR_MIDPOINT_SCALED_2P102
        ),
        successor_midpoint_scaled_2p102=(
            campaign.TARGET_SUCCESSOR_MIDPOINT_SCALED_2P102
        ),
    )
    audits.append(
        with_leaf(
            ZetaDataFileAudit(
                filename=TARGET_FILE,
                source_md5=TARGET_FILE_MD5,
                sha256=TARGET_FILE_SHA256,
                size_bytes=TARGET_FILE_SIZE,
                block_count=TARGET_FILE_BLOCKS,
                first_height=TARGET_FILE_FIRST_HEIGHT,
                last_height=TARGET_FILE_LAST_HEIGHT,
                first_multiplicity_count=TARGET_FILE_FIRST_COUNT,
                last_multiplicity_count=TARGET_FILE_LAST_COUNT,
                encoded_multiplicity_slots=(
                    TARGET_FILE_LAST_COUNT - TARGET_FILE_FIRST_COUNT
                ),
                target_cut=target_cut,
                leaf_sha256="0" * 64,
            )
        )
    )
    return audits


class FakeResponse:
    def __init__(self, raw: bytes, url: str) -> None:
        self._stream = io.BytesIO(raw)
        self._url = url
        self.status = 200
        self.headers = {
            "Content-Length": str(len(raw)),
            "ETag": '"fixture"',
            "Last-Modified": "Wed, 22 Jul 2026 00:00:00 GMT",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def read(self, size: int) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._url


class LMFDBPrefixCampaignGeometryTests(unittest.TestCase):
    def test_fixed_production_geometry_and_pins(self) -> None:
        self.assertEqual(PREFIX_FILE_COUNT, 4_766)
        self.assertEqual(campaign.FILES_PER_SHARD, 32)
        self.assertEqual(campaign.SHARD_COUNT, 149)
        self.assertEqual(campaign.REVIEWED_PLAN_SHA256, "4a1e052f3fe9963c9f4ce0170b4ee248a3c5d4b019b903c5d80eee023453dfba")
        inventory = synthetic_inventory()
        plan = synthetic_plan(inventory)
        self.assertEqual(campaign.shard_file_range(plan, 0), (0, 32))
        self.assertEqual(campaign.shard_file_range(plan, 148), (4_736, 4_766))

    def test_real_reviewed_metadata_reproduces_plan_when_available(self) -> None:
        # The public manifests are intentionally not checked into this repo.
        # This local test becomes a full pin test when the audit cache exists.
        filelist = Path("/tmp/lmfdb-zeta-audit/filelist")
        md5_manifest = Path("/tmp/lmfdb-zeta-audit/md5sum.log")
        if not filelist.exists() or not md5_manifest.exists():
            self.skipTest("public reviewed metadata cache is not present")
        inventory = campaign.load_source_inventory(filelist, md5_manifest)
        plan = campaign.create_plan(inventory)
        self.assertEqual(plan["plan_sha256"], campaign.REVIEWED_PLAN_SHA256)
        self.assertFalse(plan["trust_boundary"]["source_claim_ready"])
        self.assertFalse(
            plan["trust_boundary"]["receipt_eligible_without_realization"]
        )


class LMFDBPrefixCampaignReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = synthetic_inventory()
        cls.plan = synthetic_plan(cls.inventory)
        cls.audits = synthetic_audits(cls.inventory)

    def audit_side_effect(self, *, plan, inventory, data_directory, index):
        del inventory, data_directory
        lower, upper = campaign.shard_file_range(plan, index)
        return self.audits[lower:upper]

    def test_every_shard_audit_replay_and_ordered_finalizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(
                    campaign, "load_campaign", return_value=(self.plan, self.inventory)
                ),
                mock.patch.object(
                    campaign,
                    "_audit_expected_files",
                    side_effect=self.audit_side_effect,
                ),
            ):
                for index in range(campaign.SHARD_COUNT):
                    receipt = campaign.run_shard(root, root / "data", index)
                    self.assertFalse(receipt["source_claim_ready"])
                    self.assertFalse(receipt["receipt_eligible_without_realization"])
                    replay = campaign.replay_shard(root, root / "data", index)
                    self.assertTrue(replay["semantic_replay_identical"])
                    self.assertFalse(replay["source_claim_ready"])
                status = campaign.campaign_status(root)
                self.assertTrue(status["complete"])
                final = campaign.finalize_campaign(root)
        self.assertEqual(final["prefix_file_count"], PREFIX_FILE_COUNT)
        self.assertEqual(final["shard_count"], campaign.SHARD_COUNT)
        self.assertEqual(final["target_height"], TARGET_HEIGHT)
        self.assertEqual(
            final["target_multiplicity_count"], TARGET_MULTIPLICITY_COUNT
        )
        self.assertTrue(final["cross_shard_height_count_continuity_verified"])
        self.assertTrue(final["all_file_sha256_and_source_md5_retained"])
        self.assertFalse(final["source_claim_ready"])
        self.assertFalse(final["receipt_eligible_without_realization"])
        self.assertFalse(final["hardy_z_realization_independently_replayed"])
        self.assertFalse(
            final["source_turing_completeness_independently_replayed"]
        )
        for key in (
            "ordered_file_merkle_root_sha256",
            "ordered_shard_receipt_merkle_root_sha256",
            "ordered_replay_merkle_root_sha256",
            "source_artifact_aggregate_sha256",
            "final_sha256",
        ):
            self.assertRegex(final[key], r"^[0-9a-f]{64}$")

    def test_replay_rejects_a_changed_per_file_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(
                campaign, "load_campaign", return_value=(self.plan, self.inventory)
            ):
                with mock.patch.object(
                    campaign,
                    "_audit_expected_files",
                    side_effect=self.audit_side_effect,
                ):
                    campaign.run_shard(root, root / "data", 0)
                changed = replace(self.audits[0], sha256="f" * 64)
                changed = with_leaf(changed)

                def changed_side_effect(*, plan, inventory, data_directory, index):
                    del inventory, data_directory
                    lower, upper = campaign.shard_file_range(plan, index)
                    values = self.audits[lower:upper]
                    return [changed, *values[1:]]

                with mock.patch.object(
                    campaign,
                    "_audit_expected_files",
                    side_effect=changed_side_effect,
                ):
                    with self.assertRaisesRegex(
                        campaign.LMFDBZetaPrefixCampaignError,
                        "semantic replay differs",
                    ):
                        campaign.replay_shard(root, root / "data", 0)

    def test_receipt_rejects_reordered_file_records(self) -> None:
        receipt = campaign._make_shard_receipt(
            plan=self.plan,
            inventory=self.inventory,
            index=0,
            audits=self.audits[: campaign.FILES_PER_SHARD],
            elapsed_nanoseconds=1,
        )
        receipt["file_audits"] = list(reversed(receipt["file_audits"]))
        with self.assertRaisesRegex(
            campaign.LMFDBZetaPrefixCampaignError, "file order differs"
        ):
            campaign.validate_shard_receipt(
                receipt, plan=self.plan, inventory=self.inventory, index=0
            )


class LMFDBPrefixCampaignDownloadTests(unittest.TestCase):
    def test_atomic_download_pins_md5_and_retains_sha256(self) -> None:
        raw = b"small deterministic fixture"
        filename = "zeros_14.dat"
        url = f"{SOURCE_DATA_URL}/{filename}"

        def opener(request, timeout):
            self.assertEqual(request.full_url, url)
            self.assertEqual(timeout, 7)
            self.assertEqual(request.headers["Cookie"], "human=1")
            return FakeResponse(raw, url)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / filename
            result = campaign._download_one(
                destination=destination,
                filename=filename,
                expected_md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
                opener=opener,
                timeout_seconds=7,
            )
            self.assertEqual(destination.read_bytes(), raw)
        self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["size_bytes"], len(raw))

    def test_download_rejects_a_gate_or_cross_origin_redirect(self) -> None:
        raw = b"fixture"
        filename = "zeros_14.dat"

        def opener(_request, timeout):
            del timeout
            return FakeResponse(raw, "https://example.invalid/replaced.dat")

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / filename
            with self.assertRaisesRegex(
                campaign.LMFDBZetaPrefixCampaignError, "final URL differs"
            ):
                campaign._download_one(
                    destination=destination,
                    filename=filename,
                    expected_md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
                    opener=opener,
                )
            self.assertFalse(destination.exists())

    def test_materializer_can_only_select_one_fixed_plan_shard(self) -> None:
        inventory = synthetic_inventory()
        plan = synthetic_plan(inventory)
        audits = synthetic_audits(inventory)

        def download(*, destination, filename, expected_md5, timeout_seconds):
            self.assertEqual(timeout_seconds, 9)
            destination.write_bytes(b"fixture")
            audit = next(item for item in audits if item.filename == filename)
            self.assertEqual(expected_md5, audit.source_md5)
            return {
                "filename": filename,
                "source_url": f"{SOURCE_DATA_URL}/{filename}",
                "source_md5": audit.source_md5,
                "sha256": audit.sha256,
                "size_bytes": audit.size_bytes,
                "etag": None,
                "last_modified": None,
            }

        audit_by_name = {item.filename: item for item in audits}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(
                    campaign, "load_campaign", return_value=(plan, inventory)
                ),
                mock.patch.object(campaign, "_download_one", side_effect=download),
                mock.patch.object(
                    campaign,
                    "_audit_materialized_file",
                    side_effect=lambda _path, filename, _inventory: audit_by_name[
                        filename
                    ],
                ),
            ):
                result = campaign.materialize_shard(
                    root, root / "data", 0, timeout_seconds=9
                )
        self.assertEqual(len(result["files"]), campaign.FILES_PER_SHARD)
        self.assertEqual(result["first_file_index"], 0)
        self.assertEqual(
            result["upper_file_index_exclusive"], campaign.FILES_PER_SHARD
        )
        self.assertFalse(result["source_claim_ready"])
        self.assertFalse(result["receipt_eligible_without_realization"])


if __name__ == "__main__":
    unittest.main()
