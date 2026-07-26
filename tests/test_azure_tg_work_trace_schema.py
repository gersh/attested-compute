# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded fleet-wide checks for the measured-runner work-trace boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import re
from types import SimpleNamespace
import tempfile
import unittest

from azure.measured_runner import TRACE_KIND, WORK_TRACE_KEYS
from tg_verifier.azure_cpu_workload_factory import CDEM_FACTORY
from tools import tg_dirichlet_azure_measured_workload as dirichlet
from tools import (
    tg_goldbach_10pow27_azure_measured_workload as goldbach_10pow27,
)
from tools import (
    tg_goldbach_historical_operational_azure_measured_workload
    as goldbach_historical_operational,
)


ROOT = Path(__file__).resolve().parents[1]

# This is deliberately an explicit reviewed roster.  Adding another measured
# workload must classify its trace before an expensive Azure run can use it.
PYTHON_WORKLOADS = {
    Path("tools/tg_a7_azure_measured_workload.py"),
    Path("tools/tg_dirichlet_azure_measured_workload.py"),
    Path("tools/tg_goldbach_10pow27_azure_measured_workload.py"),
    Path("tools/tg_goldbach_10pow27_h100_measured_workload.py"),
    Path("tools/tg_goldbach_historical_azure_measured_workload.py"),
    Path("tools/tg_goldbach_historical_h100_measured_workload.py"),
    Path("tools/tg_goldbach_historical_operational_azure_measured_workload.py"),
    Path("tools/tg_hurst_azure_measured_workload.py"),
    Path("tools/tg_platt_head_azure_measured_workload.py"),
    Path("tools/tg_platt_pt21_azure_measured_workload.py"),
    Path("tools/tg_prop1224_azure_measured_workload.py"),
    Path("tools/tg_psi_azure_measured_workload.py"),
    Path("tools/tg_r2star_azure_measured_workload.py"),
    Path("tools/tg_sqrt218_azure_measured_workload.py"),
}

CXX_TRACE_FIELDS = {
    Path("reference/tg_cdem_abel_measured_workload.cpp"): {
        *WORK_TRACE_KEYS,
        "artifact_sha256",
    },
    Path("reference/tg_cdem_abel_artifact_terminal.cpp"): set(WORK_TRACE_KEYS),
}

TRACE_SHAPE_REQUIRED = {
    "algorithm_id",
    "challenge_nonce",
    "input_sha256",
    "iteration_count",
    "job_binding_sha256",
    "kind",
    "result_sha256",
    "schema_version",
}


def _constant_strings(tree: ast.Module) -> dict[str, str]:
    pending: dict[str, ast.expr] = {}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            pending[statement.targets[0].id] = statement.value
    values: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for name, value in pending.items():
            resolved: str | None = None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                resolved = value.value
            elif isinstance(value, ast.Name):
                resolved = values.get(value.id)
            if resolved is not None and values.get(name) != resolved:
                values[name] = resolved
                changed = True
    return values


class AzureTGWorkTraceSchemaTests(unittest.TestCase):
    def test_python_workload_roster_is_complete(self) -> None:
        discovered = {
            path.relative_to(ROOT)
            for path in (ROOT / "tools").glob("tg_*measured_workload.py")
        }
        self.assertEqual(discovered, PYTHON_WORKLOADS)

    def test_every_python_trace_literal_fits_the_runner_schema(self) -> None:
        for relative in sorted(PYTHON_WORKLOADS):
            with self.subTest(workload=relative.as_posix()):
                tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
                constants = _constant_strings(tree)
                trace_literals = 0
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Dict):
                        continue
                    literal_keys = {
                        key.value
                        for key in node.keys
                        if isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                    }
                    if not TRACE_SHAPE_REQUIRED <= literal_keys:
                        continue
                    trace_literals += 1
                    self.assertFalse(
                        any(key is None for key in node.keys),
                        "trace construction may not inject unclassified **fields",
                    )
                    self.assertLessEqual(literal_keys, WORK_TRACE_KEYS)
                    kind_index = next(
                        index
                        for index, key in enumerate(node.keys)
                        if isinstance(key, ast.Constant) and key.value == "kind"
                    )
                    kind_value = node.values[kind_index]
                    if isinstance(kind_value, ast.Constant):
                        resolved_kind = kind_value.value
                    elif isinstance(kind_value, ast.Name):
                        resolved_kind = constants.get(kind_value.id)
                    else:
                        resolved_kind = None
                    self.assertEqual(resolved_kind, TRACE_KIND)
                self.assertGreater(trace_literals, 0)

    def test_cdem_cpp_trace_fields_match_declared_contracts(self) -> None:
        retained_fields = {
            record["trace_sha256_field"]
            for record in CDEM_FACTORY.retained_artifact_contracts
        }
        self.assertEqual(retained_fields, {"artifact_sha256"})
        for relative, expected in CXX_TRACE_FIELDS.items():
            with self.subTest(workload=relative.as_posix()):
                source = (ROOT / relative).read_text(encoding="utf-8")
                start = source.index("std::string traceJson")
                body = source[start:]
                body = body[: body.index("\n}") + 2]
                actual = set(
                    re.findall(r'\\"([a-z0-9_]+)\\":', body)
                )
                self.assertEqual(actual, expected)
                self.assertIn(
                    '\\"kind\\":\\"sparkinterval_challenge_work_trace\\"',
                    body,
                )

    def test_dynamic_problematic_trace_builders_are_exact(self) -> None:
        digest = "a" * 64
        source = dirichlet._source_trace(
            challenge=digest,
            job_binding=digest,
            input_sha256=digest,
            q1_archive_sha256=digest,
            q1_receipt_sha256=digest,
            retained_archive_sha256=digest,
            retained_tree_sha256=digest,
            source_final_sha256=digest,
        )
        replay = {
            "predecessor_certificate_sha256": digest,
            "predecessor_receipt_file_sha256": digest,
            "predecessor_receipt_sha256": digest,
            "predecessor_statement_sha256": digest,
            "predecessor_source_trace_sha256": digest,
            "q1_archive_sha256": digest,
            "q1_receipt_sha256": digest,
            "retained_archive_sha256": digest,
            "retained_tree_sha256": digest,
            "source_final_sha256": digest,
        }
        postcheck = dirichlet._postcheck_trace(
            challenge=digest,
            job_binding=digest,
            input_sha256=digest,
            replay=replay,
        )
        packed = dirichlet._packed_trace(
            challenge=digest,
            job_binding=digest,
            input_sha256=digest,
            result={
                "artifact_roster_sha256": digest,
                "compact_source_binding_sha256": digest,
                "compact_state_artifact_sha256": digest,
                "compact_state_receipt_file_sha256": digest,
                "compact_state_receipt_sha256": digest,
                "packed_stream_sha256": digest,
                "pinset_sha256": digest,
                "predecessor_receipt_file_sha256": digest,
                "predecessor_receipt_sha256": digest,
                "runner_sha256": digest,
                "runner_source_sha256": digest,
                "runner_stderr_sha256": digest,
            },
            result_sha256=digest,
        )
        for trace in (source, postcheck, packed):
            self.assertEqual(set(trace), WORK_TRACE_KEYS)
            self.assertEqual(trace["kind"], TRACE_KIND)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input"
            handoff_path = root / "handoff"
            output_path = root / "output"
            input_path.write_bytes(b"input")
            handoff_path.write_bytes(b"handoff")
            output_path.write_bytes(b"result")
            args = SimpleNamespace(
                algorithm_id="test.algorithm",
                challenge=digest,
                group_index=0,
                handoff=handoff_path,
                input=input_path,
                job_binding=digest,
                output=output_path,
                phase="test-phase",
            )
            lowered = goldbach_10pow27._trace_value(
                args,
                retained_sha256=digest,
                retained_tree_sha256=digest,
            )
            historical = goldbach_historical_operational._trace_value(
                args,
                retained_sha256=digest,
                retained_tree_sha256=digest,
            )
        for trace in (lowered, historical):
            self.assertEqual(set(trace), WORK_TRACE_KEYS)
            self.assertEqual(trace["kind"], TRACE_KIND)


if __name__ == "__main__":
    unittest.main()
