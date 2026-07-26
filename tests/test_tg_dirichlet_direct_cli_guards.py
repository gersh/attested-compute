# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tiny fail-before-path checks for direct Dirichlet production CLIs."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.campaign_io import AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
HEX = "0" * 64


class DirectDirichletCLIGuardTest(unittest.TestCase):
    def test_source_scale_routes_fail_before_path_or_runner_access(self) -> None:
        environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            environment.pop(key, None)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            absent = root / "must-not-be-opened"
            output = root / "must-not-be-created"
            routes = {
                "campaign-source": [
                    "tools/tg_dirichlet_campaign.py",
                    "source",
                    str(output),
                    "--q1-zeta-final",
                    str(absent),
                ],
                "allchars-expanded-value-count": [
                    "tools/tg_dirichlet_allchars_stage.py",
                    "synthetic-input",
                    str(output),
                    "--q",
                    "400000",
                    "--batch-count",
                    "1",
                ],
                "smallq-replay": [
                    "tools/tg_dirichlet_booker_smallq.py",
                    "replay-chunk",
                    str(absent),
                ],
                "smallq-expanded-q-frequency": [
                    "tools/tg_dirichlet_booker_smallq.py",
                    "produce-chunk",
                    str(output),
                    "65",
                    "1",
                    "0",
                    "1",
                ],
                "lattice-replay": [
                    "tools/tg_dirichlet_lattice_certificates.py",
                    "replay",
                    str(absent),
                ],
                "lattice-runner": [
                    "tools/tg_dirichlet_lattice_stage.py",
                    "run-batch",
                    str(output),
                    "--input",
                    str(absent),
                    "--runner",
                    str(absent),
                    "--checker",
                    str(absent),
                    "--lattice-certificate",
                    str(absent),
                ],
                "recovery-replay": [
                    "tools/tg_dirichlet_recovery_seeds.py",
                    "replay",
                    str(absent),
                    str(absent),
                ],
                "tblock-supervisor": [
                    "tools/tg_dirichlet_tblock_supervisor.py",
                    "run",
                    str(absent),
                    str(absent),
                    str(output),
                    str(output),
                    "--expected-spool-receipt-sha256",
                    HEX,
                    "--stop-after-blocks",
                    "1",
                    "--worker-command",
                    str(absent),
                ],
                "tblock-direct-worker": [
                    "tools/tg_dirichlet_tblock_worker.py",
                ],
                "tblock-bundle-supervisor": [
                    "tools/tg_dirichlet_tblock_bundle_supervisor.py",
                    "run",
                    str(absent),
                    str(absent),
                    str(output),
                    str(output),
                    "--expected-spool-receipt-sha256",
                    HEX,
                    "--stop-after-blocks",
                    "1",
                    "--worker-command",
                    str(absent),
                ],
                "tmajor-spool-build": [
                    "tools/tg_dirichlet_tmajor_spool.py",
                    "build-spool",
                    str(absent),
                    str(output),
                    str(output),
                    "--lane-index",
                    "0",
                ],
                "largeq-pipeline": [
                    "tools/tg_dirichlet_largeq_pipeline.py",
                    "run",
                    str(absent),
                    str(absent),
                    str(absent),
                    str(absent),
                    str(output),
                    str(output),
                    "--allchars-runner",
                    str(absent),
                    "--consumer-python",
                    str(absent),
                ],
                "completed-l-consume": [
                    "tools/tg_dirichlet_stream_zero_consumer.py",
                    "consume",
                    str(absent),
                    str(absent),
                    str(output),
                    str(output),
                ],
                "postprocess-produce": [
                    "tools/tg_dirichlet_postprocess.py",
                    "produce",
                    str(absent),
                    str(output),
                ],
                "root-number-replay": [
                    "tools/tg_dirichlet_root_number_stage.py",
                    "direct-replay",
                    str(absent),
                    str(absent),
                ],
                "zero-closure": [
                    "tools/tg_dirichlet_zero_closure.py",
                    "run",
                    str(absent),
                    str(output),
                    str(output),
                ],
                "residue-framed": [
                    "tools/tg_dirichlet_residue_composition.py",
                    "framed-produce",
                    str(output),
                ],
                "flint-high-height": [
                    "tools/tg_dirichlet_flint_backend.py",
                    "verify-character",
                    "--q",
                    "3",
                    "--conrey",
                    "2",
                    "--height",
                    "65",
                ],
            }
            for route, words in routes.items():
                with self.subTest(route=route):
                    completed = subprocess.run(
                        [PYTHON, str(ROOT / words[0]), *words[1:]],
                        cwd=ROOT,
                        env=environment,
                        input=b"",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=10,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn(
                        b"production arithmetic/replay is cloud-only",
                        completed.stdout + completed.stderr,
                    )
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
