#!/usr/bin/env python3
"""Measure the Lean-kernel cost of a level-2 PT21 ladder check.

The point of comparison is the measured kernel-mode *bracket* rate quoted in
``docs/algorithms/GRH_POC_BENCHMARKS.md``: 122 rational brackets in 5.6 s,
about 22 brackets/s single-threaded.  A bracket-linear certificate for the
1.24e13-bracket Platt--Trudgian range is therefore ~5e4 core-years of
checking.

This script generates a literal ``List GroupSummary`` of the requested
length, asks the Lean kernel to reduce ``checkCampaign record groups`` to
``true`` by ``rfl``, and reports elaboration + kernel wall time.  It reports
records/s, and the implied blocks/s and brackets/s at the campaign's
average block occupancy.

Usage:

    python3 tools/benchmark_pt21_ladder.py --sizes 1000 5000 20000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time

SOURCE_BLOCK_COUNT = 2_966_443_783
SOURCE_LOWER_COUNT = 32_130_158_315
SOURCE_UPPER_COUNT = 12_363_153_437_138
SOURCE_SLOTS = SOURCE_UPPER_COUNT - SOURCE_LOWER_COUNT
KERNEL_BRACKET_RATE = 22.0  # measured, docs/algorithms/GRH_POC_BENCHMARKS.md


def average_slots_per_block() -> float:
    return SOURCE_SLOTS / SOURCE_BLOCK_COUNT


def digest_literal(seed: int) -> str:
    """A realistic 32-byte digest, as the big-endian natural it encodes.

    Production records carry real SHA-256 output, so the benchmark pays the
    same elaboration cost the real ladder pays.
    """
    material = hashlib.sha256(str(seed).encode("ascii")).digest()
    return str(int.from_bytes(material, "big"))


def emit_module(count: int, blocks_per_group: int) -> str:
    """Emit a Lean module holding ``count`` consecutive group summaries."""
    slots_per_group = int(round(average_slots_per_block() * blocks_per_group))
    lines = [
        "import SparkInterval.Zeta.PT21Ladder",
        "",
        "set_option maxRecDepth 4000000",
        "set_option maxHeartbeats 0",
        "",
        "namespace SparkInterval.Zeta.PT21Ladder.Bench",
        "",
        "open SparkInterval.Zeta.PT21Ladder",
        "",

        "def groups : List GroupSummary := [",
    ]
    entries = []
    count_cursor = SOURCE_LOWER_COUNT
    for index in range(count):
        first_block = index * blocks_per_group
        lower = count_cursor
        upper = lower + slots_per_group
        count_cursor = upper
        entries.append(
            "  { firstBlock := %d, blockCount := %d, lowerCount := %d,"
            " slots := %d, upperCount := %d, digest := %s }"
            % (
                first_block,
                blocks_per_group,
                lower,
                slots_per_group,
                upper,
                digest_literal(index),
            )
        )
    lines.append(",\n".join(entries))
    lines.append("]")
    lines.append("")
    lines.append("def record : CampaignRecord := {")
    lines.append("  firstBlock := 0")
    lines.append("  blockCount := %d" % (count * blocks_per_group))
    lines.append("  lowerCount := %d" % SOURCE_LOWER_COUNT)
    lines.append("  slots := %d" % (count * slots_per_group))
    lines.append("  upperCount := %d" % count_cursor)
    lines.append("  root := %s" % digest_literal(0))
    lines.append("}")
    lines.append("")
    lines.append("theorem ladder_accepts : checkCampaign record groups = true := by")
    lines.append("  rfl")
    lines.append("")
    lines.append("end SparkInterval.Zeta.PT21Ladder.Bench")
    lines.append("")
    return "\n".join(lines)


def run_case(repo: pathlib.Path, count: int, blocks_per_group: int) -> dict:
    module = emit_module(count, blocks_per_group)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".lean", dir=str(repo), delete=False
    ) as handle:
        handle.write(module)
        path = pathlib.Path(handle.name)
    try:
        start = time.monotonic()
        completed = subprocess.run(
            ["lake", "env", "lean", str(path)],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        elapsed = time.monotonic() - start
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit("lean rejected the generated ladder module")
    return {
        "group_records": count,
        "blocks_per_group": blocks_per_group,
        "blocks_covered": count * blocks_per_group,
        "source_bytes": len(module),
        "wall_seconds": round(elapsed, 3),
        "records_per_second": round(count / elapsed, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[500, 1500, 2830])
    # Production geometry: one level-3 record is one scheduler shard of
    # 2048 units of 512 blocks.
    parser.add_argument("--blocks-per-group", type=int, default=1048576)
    parser.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
    arguments = parser.parse_args()

    repo = pathlib.Path(arguments.repo)
    results = []
    baseline = None
    for size in arguments.sizes:
        row = run_case(repo, size, arguments.blocks_per_group)
        results.append(row)
        if baseline is None:
            baseline = row
        print(json.dumps(row))

    # Marginal rate removes the fixed elaboration/import overhead, matching the
    # way the 22 brackets/s figure was reported (it *included* ~5 s of fixed
    # overhead, so the marginal comparison is the conservative one).
    if len(results) >= 2:
        first, last = results[0], results[-1]
        delta_records = last["group_records"] - first["group_records"]
        delta_seconds = last["wall_seconds"] - first["wall_seconds"]
        marginal = delta_records / delta_seconds if delta_seconds > 0 else float("inf")
        groups_needed = SOURCE_BLOCK_COUNT / arguments.blocks_per_group
        summary = {
            "marginal_records_per_second": round(marginal, 1),
            "source_group_records": round(groups_needed, 1),
            "source_kernel_seconds": round(groups_needed / marginal, 1),
            "bracket_linear_kernel_core_years": round(
                (SOURCE_SLOTS / KERNEL_BRACKET_RATE) / (3600 * 24 * 365.25), 1
            ),
        }
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
