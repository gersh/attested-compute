#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Test-only entry point for bounded synthetic root-number KATs."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.tg_dirichlet_root_number_stage as worker  # noqa: E402


worker.require_azure_measured_worker_for_workload = lambda **_kwargs: None


if __name__ == "__main__":
    raise SystemExit(worker.main())
