# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded tests for the three disabled Platt terminal-result contracts."""

from __future__ import annotations

import importlib.util
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    specification = importlib.util.spec_from_file_location(
        f"_terminal_contract_{name}", path
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


HEAD = _load_tool("tg_zeta_campaign")
PT21 = _load_tool("tg_platt_zeta_campaign")
DIRICHLET = _load_tool("tg_dirichlet_campaign")


class PlattTerminalResultContractTests(unittest.TestCase):
    def test_all_three_writers_are_exact_and_exclusive(self) -> None:
        for label, writer in (
            ("head", HEAD._write_registered_result),
            ("pt21", PT21._write_registered_result),
            ("dirichlet", DIRICHLET._write_registered_result),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "nested" / "registered-result.txt"
                writer(output)
                self.assertEqual(output.read_bytes(), b"true")
                with self.assertRaises(FileExistsError):
                    writer(output)
                self.assertEqual(output.read_bytes(), b"true")

    def test_head_full_writes_only_after_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "registered-result.txt"
            arguments = SimpleNamespace(
                directory=root / "campaign",
                profile="platt-head-2e4",
                batch_size=4096,
                precision_bits=96,
                registered_result_output=output,
                pretty=False,
            )
            with (
                mock.patch.object(HEAD, "require_azure_measured_worker_for_workload"),
                mock.patch.object(HEAD, "initialize_campaign", return_value={}),
                mock.patch.object(HEAD, "run_campaign", return_value={}),
                mock.patch.object(
                    HEAD, "finalize_campaign", side_effect=RuntimeError("incomplete")
                ),
                mock.patch.object(HEAD, "_emit"),
            ):
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    HEAD.command_full(arguments)
            self.assertFalse(output.exists())

            with (
                mock.patch.object(HEAD, "require_azure_measured_worker_for_workload"),
                mock.patch.object(HEAD, "initialize_campaign", return_value={}),
                mock.patch.object(
                    HEAD,
                    "run_campaign",
                    return_value={"complete": True, "chunks_total": 2},
                ),
                mock.patch.object(HEAD, "finalize_campaign", return_value={}),
                mock.patch.object(HEAD, "replay_chunk"),
                mock.patch.object(
                    HEAD, "retained_head_q128_cells", return_value=()
                ),
                mock.patch.object(HEAD, "render_head_q128_lean_module"),
                mock.patch.object(HEAD, "_emit"),
            ):
                self.assertEqual(HEAD.command_full(arguments), 0)
            self.assertEqual(output.read_bytes(), b"true")

    def test_pt21_finalize_writes_only_after_complete_finalizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "registered-result.txt"
            argv = [
                "finalize",
                str(root / "campaign"),
                "--registered-result-output",
                str(output),
            ]
            with (
                mock.patch.object(PT21, "_guard_finite_work"),
                mock.patch.object(
                    PT21,
                    "finalize_campaign",
                    side_effect=PT21.PlattZetaCampaignError("incomplete"),
                ),
                mock.patch.object(PT21, "emit"),
            ):
                self.assertEqual(PT21.main(argv), 2)
            self.assertFalse(output.exists())

            with (
                mock.patch.object(PT21, "_guard_finite_work"),
                mock.patch.object(
                    PT21,
                    "finalize_campaign",
                    return_value={
                        "mode": "full_source",
                        "shard_count": 1_236_316,
                        "retained_shards": 1_236_316,
                        "count_ready": True,
                        "prefix_ready": True,
                        "complete": True,
                        "final_ready": True,
                    },
                ),
                mock.patch.object(PT21, "emit"),
            ):
                self.assertEqual(PT21.main(argv), 0)
            self.assertEqual(output.read_bytes(), b"true")

    def test_dirichlet_postcheck_writes_only_after_full_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = {"accepted": True, "source": "exact-two-branch"}
            (root / "source-final.json").write_bytes(
                DIRICHLET.canonical_json_bytes(source)
            )
            output = root / "registered-result.txt"
            arguments = SimpleNamespace(
                root=root,
                q1_zeta_input=root / "q1-final.json",
                registered_result_output=output,
                pretty=False,
            )
            common = (
                mock.patch.object(
                    DIRICHLET, "_q1_zeta_requirement", return_value={"q1": True}
                ),
                mock.patch.object(
                    DIRICHLET, "require_azure_measured_worker_for_workload"
                ),
                mock.patch.object(DIRICHLET, "_validate_retained_source_requirement"),
                mock.patch.object(DIRICHLET, "finalize_campaign", return_value={}),
                mock.patch.object(DIRICHLET, "_source_document", return_value=source),
                mock.patch.object(DIRICHLET, "_emit"),
            )
            with ExitStack() as stack:
                for patcher in common:
                    stack.enter_context(patcher)
                stack.enter_context(
                    mock.patch.object(
                        DIRICHLET,
                        "verify_campaign",
                        return_value={"complete": False, "final_present": False},
                    )
                )
                with self.assertRaisesRegex(
                    DIRICHLET.DirichletCampaignError, "not complete"
                ):
                    DIRICHLET.command_verify_source(arguments)
            self.assertFalse(output.exists())

            common = (
                mock.patch.object(
                    DIRICHLET, "_q1_zeta_requirement", return_value={"q1": True}
                ),
                mock.patch.object(
                    DIRICHLET, "require_azure_measured_worker_for_workload"
                ),
                mock.patch.object(DIRICHLET, "_validate_retained_source_requirement"),
                mock.patch.object(DIRICHLET, "finalize_campaign", return_value={}),
                mock.patch.object(DIRICHLET, "_source_document", return_value=source),
                mock.patch.object(
                    DIRICHLET,
                    "rerun_external_checkers",
                    return_value={
                        "complete": True,
                        "final_present": True,
                        "fresh_checker_replay_performed": True,
                        "fresh_external_checker_replays": 3,
                    },
                ),
                mock.patch.object(DIRICHLET, "_emit"),
            )
            with ExitStack() as stack:
                for patcher in common:
                    stack.enter_context(patcher)
                stack.enter_context(
                    mock.patch.object(
                    DIRICHLET,
                    "verify_campaign",
                    return_value={
                        "complete": True,
                        "final_present": True,
                        "chunks": 3,
                        "mode": "full_source",
                        "q_start": DIRICHLET.SOURCE_MIN_Q,
                        "q_stop": DIRICHLET.SOURCE_MAX_Q,
                        "characters_total": 29_565_923_837,
                        "characters_covered": 29_565_923_837,
                    },
                )
                )
                DIRICHLET.command_verify_source(arguments)
            self.assertEqual(output.read_bytes(), b"true")


if __name__ == "__main__":
    unittest.main()
