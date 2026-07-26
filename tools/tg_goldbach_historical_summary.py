#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit the exact archived Oliveira e Silva Goldbach summary table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_historical_artifact import (  # noqa: E402
    HistoricalGoldbachArtifactError,
    audit_public_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = audit_public_summary(arguments.summary).as_json()
    except (HistoricalGoldbachArtifactError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if arguments.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

