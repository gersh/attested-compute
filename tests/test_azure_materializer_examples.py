# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None


ROOT = Path(__file__).resolve().parents[1]

EXAMPLES = {
    "azure_cpu_a7_materializer_site.redacted.json":
        "azure-cpu-a7-materializer-site.schema.json",
    "azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json":
        "azure-cpu-cdem-artifact-terminal-materializer-site.schema.json",
    "azure_cpu_portfolio_materializer_site.redacted.json":
        "azure-cpu-portfolio-materializer-site.schema.json",
    "azure_cpu_psi_portfolio_materializer_site.redacted.json":
        "azure-cpu-psi-portfolio-materializer-site.schema.json",
    "azure_cpu_hurst_materializer_site.redacted.json":
        "azure-cpu-hurst-portfolio-materializer-site.schema.json",
    "azure_cpu_platt_head_materializer_site.redacted.json":
        "azure-cpu-platt-head-materializer-site.schema.json",
    "azure_cpu_platt_pt21_materializer_site.redacted.json":
        "azure-cpu-platt-pt21-materializer-site.schema.json",
    "azure_cpu_prop1224_materializer_site.redacted.json":
        "azure-cpu-prop1224-materializer-site.schema.json",
    "azure_cpu_goldbach10pow27_materializer_site.redacted.json":
        "azure-cpu-goldbach10pow27-materializer-site.schema.json",
    "azure_cpu_goldbach_historical_operational_materializer_site.redacted.json":
        "azure-cpu-goldbach-historical-operational-materializer-site.schema.json",
    "azure_cpu_goldbach_historical_terminal_materializer_site.redacted.json":
        "azure-cpu-goldbach-historical-terminal-materializer-site.schema.json",
    "azure_cpu_dirichlet_materializer_site.redacted.json":
        "azure-cpu-dirichlet-materializer-site.schema.json",
    "azure_cpu_dirichlet_postcheck_materializer_site.redacted.json":
        "azure-cpu-dirichlet-postcheck-materializer-site.schema.json",
    "azure_h100_dirichlet_packed_materializer_site.redacted.json":
        "azure-h100-dirichlet-packed-materializer-site.schema.json",
    "azure_h100_goldbach10pow27_materializer_site.redacted.json":
        "azure-h100-goldbach10pow27-materializer-site.schema.json",
    "azure_h100_goldbach_historical_materializer_site.redacted.json":
        "azure-h100-goldbach-historical-materializer-site.schema.json",
    "azure_h100_r2star_materializer_site.redacted.json":
        "azure-h100-r2star-materializer-site.schema.json",
}


class AzureMaterializerExampleTests(unittest.TestCase):
    @unittest.skipIf(jsonschema is None, "jsonschema unavailable")
    def test_every_materializer_example_is_schema_valid_and_none_are_orphaned(self) -> None:
        example_names = {
            path.name
            for path in (ROOT / "examples/trusted-compute").glob(
                "azure_*materializer_site.redacted.json"
            )
        }
        schema_names = {
            path.name
            for path in (ROOT / "schemas").glob(
                "azure-*-materializer-site.schema.json"
            )
        }
        self.assertEqual(example_names, set(EXAMPLES))
        self.assertEqual(schema_names, set(EXAMPLES.values()))
        for example_name, schema_name in EXAMPLES.items():
            with self.subTest(example=example_name):
                example = json.loads(
                    (
                        ROOT / "examples/trusted-compute" / example_name
                    ).read_bytes()
                )
                schema = json.loads((ROOT / "schemas" / schema_name).read_bytes())
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(example, schema)

    def test_every_materializer_cli_is_directly_runnable(self) -> None:
        tools = sorted(
            (ROOT / "tools").glob("tg_azure_*materializer.py")
        )
        self.assertEqual(len(tools), 16)
        for path in tools:
            with self.subTest(tool=path.name):
                self.assertTrue(path.stat().st_mode & 0o111)
                self.assertEqual(
                    path.read_bytes().splitlines()[0],
                    b"#!/usr/bin/env python3",
                )
                result = subprocess.run(
                    [str(path), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
