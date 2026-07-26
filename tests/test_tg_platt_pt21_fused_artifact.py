# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

from tg_verifier.platt_pt21_fused_artifact import (
    INTERPOLATION_PATCH_SHA256,
    PT21FusedArtifactError,
    TRACE_SCHEMA,
    build_block_artifact,
    finalize_campaign,
    finalize_shard,
    validate_final_receipt,
    validate_shard_receipt,
    write_block_artifact,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    UPSTREAM_COMMIT,
)


ROOT = Path(__file__).resolve().parents[1]


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def fnv1a(raw: bytes) -> int:
    value = 1_469_598_103_934_665_603
    for byte in raw:
        value ^= byte
        value = (value * 1_099_511_628_211) & ((1 << 64) - 1)
    return value


def rational(value: int, denominator: int = 1) -> dict[str, int]:
    return {"numerator": value, "denominator": denominator}


def interval(value: int) -> dict[str, object]:
    return {"lo": rational(value), "hi": rational(value)}


def build_required_packet(
    directory: Path,
    *,
    block: int,
    values: dict[int, float],
    default: float,
) -> Path:
    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        hi = values.get(offset, default)
        samples.extend(SAMPLE.pack(hi, 0.0, 0.25))
        if hi > 0:
            signs[index // 8] |= 1 << (index % 8)
    source_raw = f"synthetic-source-{block}".encode()
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
        SOURCE_LOWER_CENTER + block * SOURCE_STEP,
        len(samples),
        len(signs),
        fnv1a(samples),
        fnv1a(signs),
        len(source_raw),
        hashlib.sha256(source_raw).hexdigest().encode(),
        UPSTREAM_COMMIT,
    )
    path = directory / f"required-{block}.bin"
    path.write_bytes(header + samples + signs)
    return path


def source_trace(
    *,
    block: int,
    packet: Path,
    im_gamma_integral: int,
    resolutions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": TRACE_SCHEMA,
        "upstream_commit": UPSTREAM_COMMIT.decode(),
        "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
        "block": block,
        "required_sign_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "producer": {
            "worker_sha256": "12" * 32,
            "worker_size_bytes": 1234,
            "precision_bits": 128,
            "all_required_samples_certified": True,
            "all_stationary_queries_resolved": True,
        },
        "stationary_resolutions": resolutions or [],
        "turing_inputs": {
            "lower": {
                "s_bound": interval(21),
                "log_pi": interval(0),
                "im_gamma_integral": interval(im_gamma_integral),
                "pi": interval(1),
            },
            "upper": {
                "s_bound": interval(21),
                "log_pi": interval(0),
                "im_gamma_integral": interval(im_gamma_integral),
                "pi": interval(1),
            },
        },
        "semantic_status": {
            "hardy_z_endpoint_realization_proved": False,
            "main_multiplicity_realization_proved": False,
            "analytic_turing_realization_proved": False,
        },
    }


def write_trace(directory: Path, value: dict[str, object], name: str) -> Path:
    path = directory / name
    path.write_bytes(canonical(value))
    return path


class PT21FusedArtifactTest(unittest.TestCase):
    def test_direct_packet_recomputes_events_turing_and_v2_wire(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = build_required_packet(
                directory, block=0, values={0: 1.0}, default=-1.0
            )
            trace = write_trace(
                directory,
                source_trace(block=0, packet=packet, im_gamma_integral=21),
                "trace.json",
            )
            artifact = build_block_artifact(packet, trace)
            self.assertEqual(
                artifact["schema"],
                "sparkinterval.tg.platt-pt21-lean-block-artifact.v2",
            )
            self.assertEqual(
                artifact["streams"]["main"]["events"],
                [
                    {"left_sample": -1, "right_sample": 0, "multiplicity": 1},
                    {"left_sample": 0, "right_sample": 1, "multiplicity": 1},
                ],
            )
            self.assertEqual(artifact["turing"]["lower"]["count"], 1)
            self.assertEqual(artifact["turing"]["upper"]["count"], 3)
            self.assertFalse(
                artifact.get("hardy_z_endpoint_realization_proved", False)
            )

    def test_stationary_dyadic_pair_binds_one_multiplicity_two_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = build_required_packet(
                directory,
                block=0,
                values={0: 2.0, 1: 1.0, 2: 2.0},
                default=1.0,
            )
            resolution = {
                "stream": "main",
                "outer_left_sample": 0,
                "outer_right_sample": 2,
                "lower_offset": rational(0),
                "midpoint_offset": rational(1, 2),
                "upper_offset": rational(1),
                "lower_value": interval(2),
                "midpoint_value": interval(-1),
                "upper_value": interval(1),
            }
            trace = write_trace(
                directory,
                source_trace(
                    block=0,
                    packet=packet,
                    im_gamma_integral=21,
                    resolutions=[resolution],
                ),
                "trace.json",
            )
            artifact = build_block_artifact(packet, trace)
            main = artifact["streams"]["main"]
            self.assertEqual(
                main["events"],
                [{"left_sample": 0, "right_sample": 2, "multiplicity": 2}],
            )
            self.assertEqual(len(main["brackets"]), 2)
            self.assertEqual(main["brackets"][0]["upper_offset"], rational(1, 2))
            self.assertEqual(main["brackets"][1]["lower_offset"], rational(1, 2))

    def test_missing_stationary_resolution_and_semantic_overclaim_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = build_required_packet(
                directory,
                block=0,
                values={0: 2.0, 1: 1.0, 2: 2.0},
                default=1.0,
            )
            value = source_trace(block=0, packet=packet, im_gamma_integral=21)
            trace = write_trace(directory, value, "missing.json")
            with self.assertRaisesRegex(PT21FusedArtifactError, "stationary resolutions"):
                build_block_artifact(packet, trace)
            value["semantic_status"]["hardy_z_endpoint_realization_proved"] = True
            trace = write_trace(directory, value, "overclaim.json")
            with self.assertRaisesRegex(PT21FusedArtifactError, "must not claim"):
                build_block_artifact(packet, trace)

    def test_trace_must_be_canonical_and_bound_to_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = build_required_packet(
                directory, block=0, values={0: 1.0}, default=-1.0
            )
            value = source_trace(block=0, packet=packet, im_gamma_integral=21)
            noncanonical = directory / "noncanonical.json"
            noncanonical.write_text(json.dumps(value, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(PT21FusedArtifactError, "canonical"):
                build_block_artifact(packet, noncanonical)
            value["required_sign_packet_sha256"] = "00" * 32
            wrong = write_trace(directory, value, "wrong.json")
            with self.assertRaisesRegex(PT21FusedArtifactError, "identity differs"):
                build_block_artifact(packet, wrong)

    def test_bounded_shard_and_campaign_finalizers_are_gap_and_count_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifacts: list[Path] = []
            for block, gamma in ((0, 21), (1, 63)):
                packet = build_required_packet(
                    directory, block=block, values={0: 1.0}, default=-1.0
                )
                trace = write_trace(
                    directory,
                    source_trace(
                        block=block, packet=packet, im_gamma_integral=gamma
                    ),
                    f"trace-{block}.json",
                )
                output = directory / f"block-{block}.json"
                write_block_artifact(packet, trace, output)
                artifacts.append(output)
            first_receipt = finalize_shard(
                [artifacts[0]], first_block=0, allow_bounded_test=True
            )
            second_receipt = finalize_shard(
                [artifacts[1]], first_block=1, allow_bounded_test=True
            )
            validate_shard_receipt(first_receipt)
            receipts = []
            for index, value in enumerate((first_receipt, second_receipt)):
                path = directory / f"receipt-{index}.json"
                path.write_bytes(canonical(value))
                receipts.append(path)
            final = finalize_campaign(receipts, allow_bounded_test=True)
            validate_final_receipt(final)
            self.assertEqual(final["block_count"], 2)
            self.assertEqual(final["first_count"], 1)
            self.assertEqual(final["last_count"], 5)
            self.assertTrue(final["all_finite_artifacts_closed"])
            self.assertFalse(final["source_claim_ready"])
            with self.assertRaisesRegex(PT21FusedArtifactError, "full geometry"):
                finalize_campaign(receipts[1:], allow_bounded_test=False)

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_new_schemas_accept_generated_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = build_required_packet(
                directory, block=0, values={0: 1.0}, default=-1.0
            )
            trace_value = source_trace(
                block=0, packet=packet, im_gamma_integral=21
            )
            trace_schema = json.loads(
                (ROOT / "schemas/platt-pt21-fused-source-trace.schema.json").read_text()
            )
            jsonschema.Draft202012Validator.check_schema(trace_schema)
            jsonschema.Draft202012Validator(trace_schema).validate(trace_value)
            trace = write_trace(directory, trace_value, "trace.json")
            artifact = build_block_artifact(packet, trace)
            artifact_schema = json.loads(
                (ROOT / "schemas/platt-pt21-lean-block-artifact.schema.json").read_text()
            )
            jsonschema.Draft202012Validator.check_schema(artifact_schema)
            jsonschema.Draft202012Validator(artifact_schema).validate(artifact)
            output = directory / "block.json"
            output.write_bytes(canonical(artifact))
            shard = finalize_shard(
                [output], first_block=0, allow_bounded_test=True
            )
            shard_schema = json.loads(
                (ROOT / "schemas/platt-pt21-fused-shard.schema.json").read_text()
            )
            jsonschema.Draft202012Validator.check_schema(shard_schema)
            jsonschema.Draft202012Validator(shard_schema).validate(shard)
            receipt = directory / "shard.json"
            receipt.write_bytes(canonical(shard))
            final = finalize_campaign([receipt], allow_bounded_test=True)
            final_schema = json.loads(
                (ROOT / "schemas/platt-pt21-fused-final.schema.json").read_text()
            )
            jsonschema.Draft202012Validator.check_schema(final_schema)
            jsonschema.Draft202012Validator(final_schema).validate(final)


if __name__ == "__main__":
    unittest.main()
