#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the bounded actual-native multi-q t-block plan-switch worker."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tblock_plan_switch_worker import run  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


if __name__ == "__main__":
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    raise SystemExit(run())
