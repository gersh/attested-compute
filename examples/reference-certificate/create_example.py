#!/usr/bin/env python3
"""Create the canonical reference-batch input used by this example."""

from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from reference import format as wire  # noqa: E402


def interval(lo: str, hi: str | None = None) -> dict[str, str]:
    return {"lo": lo, "hi": lo if hi is None else hi}


batch = {
    "schema_version": 1,
    "kind": wire.BATCH_KIND,
    "algorithm": wire.ALGORITHM_ID,
    "variable_count": 2,
    "expression": {
        "op": "mul",
        "left": {"op": "var", "index": 0},
        "right": {
            "op": "add",
            "left": {"op": "const", "value": interval("3ff0000000000000")},
            "right": {"op": "var", "index": 1},
        },
    },
    "rows": [
        [interval("3ff0000000000000"), interval("4000000000000000")],
        [
            interval("3ff0000000000000", "3ff0000000000001"),
            interval("4000000000000000", "4008000000000000"),
        ],
    ],
}

wire.validate_batch(batch)
wire.write_canonical_json(Path(__file__).with_name("batch.json"), batch)
