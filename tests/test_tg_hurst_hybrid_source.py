#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed protocol tests for the CPU/H100 Hurst source handoff."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tg_verifier.campaign_io import canonical_json_bytes, load_json
import tg_verifier.hurst_hybrid_source as hybrid_module
from tg_verifier.hurst_hybrid_source import (
    CPU_UPPER_EXCLUSIVE,
    DEFAULT_H100_SUPER_SHARD_ROWS,
    GPU_ALGORITHM,
    GPU_CLASSIFICATION,
    GPU_HEADER_FIELDS,
    GPU_LEAF_FIELDS,
    GPU_SCHEMA,
    GPU_TERMINAL_FIELDS,
    H100_LOWER,
    HurstHybridSourceError,
    SEMANTIC_FLAGS,
    SOURCE_LOWER,
    SOURCE_UPPER_EXCLUSIVE,
    materialize,
    run,
    source_geometry,
)
from tg_verifier.hurst_residual_campaign import (
    ATOM_PROFILES,
    RUNNER_ALGORITHM,
    RUNNER_CLASSIFICATION,
    STATE_COMPONENTS,
    UPSTREAM_COMMIT,
)


CPU_LOWER = 1
CPU_UPPER = 17
GPU_LOWER = 17
GPU_UPPER = 33
CPU_SEGMENT_ROWS = 13_860
GPU_LEAF_ROWS = 8
GPU_SUPER_ROWS = 16
CPU_DELTA = (2, 10, -5, 7)


def _replay_leaf_digest(
    record: dict, *, executable_sha256: str, roster_sha256: str
) -> str:
    square_lower_order = 2 * (
        record["squarefree_lower"]["witness_y"] - record["lower"]
    ) - (record["squarefree_lower"]["side"] == "right_limit")
    square_upper_order = 2 * (
        record["squarefree_upper"]["witness_y"] - record["lower"]
    ) - (record["squarefree_upper"]["side"] == "right_limit")
    text = (
        "domain=sparkinterval.tg.mobius-persistent-leaf.v1\n"
        f"algorithm={GPU_ALGORITHM}\n"
        f"executable_sha256={executable_sha256}\n"
        f"prime_roster_sha256={roster_sha256}\n"
        f"previous={record['previous_leaf_sha256']}\n"
        f"lower={record['lower']}\n"
        f"upper_exclusive={record['upper_exclusive']}\n"
        "poison_count=0\n"
        f"incoming_mertens={record['incoming_mertens']}\n"
        f"outgoing_mertens={record['outgoing_mertens']}\n"
        f"delta_mertens={record['delta_mertens']}\n"
        f"incoming_squarefree={record['incoming_squarefree']}\n"
        f"outgoing_squarefree={record['outgoing_squarefree']}\n"
        f"delta_squarefree={record['delta_squarefree']}\n"
        f"hurst_lower={record['hurst_lower']['value']}\n"
        f"hurst_lower_y={record['hurst_lower']['witness_y']}\n"
        f"hurst_upper={record['hurst_upper']['value']}\n"
        f"hurst_upper_y={record['hurst_upper']['witness_y']}\n"
        f"squarefree_lower={record['squarefree_lower']['value']}\n"
        f"squarefree_lower_y={record['squarefree_lower']['witness_y']}\n"
        f"squarefree_lower_order={square_lower_order}\n"
        f"squarefree_upper={record['squarefree_upper']['value']}\n"
        f"squarefree_upper_y={record['squarefree_upper']['witness_y']}\n"
        f"squarefree_upper_order={square_upper_order}\n"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cpu_runner_source(*, mismatch: bool = False) -> str:
    return f"""#!/usr/bin/python3
import argparse
import hashlib
import json

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--upper", type=int, required=True)
p.add_argument("--segment-size", type=int, required=True)
p.add_argument("--mode", choices=("summary", "verify"), required=True)
p.add_argument("--incoming-mertens", type=int, default=0)
p.add_argument("--incoming-squarefree", type=int, default=0)
p.add_argument("--incoming-little-lower", type=int, default=0)
p.add_argument("--incoming-little-upper", type=int, default=0)
a = p.parse_args()
upper_exclusive = a.upper + 1
count = upper_exclusive - a.lower
incoming = [
    a.incoming_mertens,
    a.incoming_squarefree,
    a.incoming_little_lower,
    a.incoming_little_upper,
]
guards = {{}}
if a.mode == "verify":
    guards = {{
        atom: {{"lower": incoming, "upper": incoming, "witnesses": []}}
        for atom in {tuple(ATOM_PROFILES)!r}
    }}
row_sha256 = hashlib.sha256(
    f"tiny-hurst-source:{{a.lower}}:{{upper_exclusive}}".encode("ascii")
).hexdigest()
if {mismatch!r} and a.mode == "verify":
    row_sha256 = "f" * 64
print(json.dumps({{
    "algorithm": {RUNNER_ALGORITHM!r},
    "mode": a.mode,
    "classification": {RUNNER_CLASSIFICATION!r},
    "upstream_commit": {UPSTREAM_COMMIT!r},
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "work_count": count,
    "segment_size": a.segment_size,
    "segments": (count + a.segment_size - 1) // a.segment_size,
    "row_encoding": "mu-plus-one-block-sha256-v1",
    "squarefree_threshold_endpoint_policy":
        "inclusive-value-and-right-limit-v2",
    "reduction_block_rows": 1048576,
    "row_sha256": row_sha256,
    "state_components": {list(STATE_COMPONENTS)!r},
    "delta": {list(CPU_DELTA)!r},
    "guards": guards,
    "exact_fallbacks": {{
        "mertens_hurst": 0,
        "squarefree": 0,
        "little_mertens_2_11": 0,
        "little_mertens_stronger": 0,
    }},
    "accepted": True,
    "elapsed_seconds": 0,
    "execution_attested": False,
    "lean_atom_discharged": False,
}}, sort_keys=True, separators=(",", ":")))
"""


def _h100_runner_source(*, fault: str = "none") -> str:
    return f"""#!/usr/bin/python3
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HEADER_FIELDS = {tuple(sorted(GPU_HEADER_FIELDS))!r}
LEAF_FIELDS = {tuple(sorted(GPU_LEAF_FIELDS))!r}
TERMINAL_FIELDS = {tuple(sorted(GPU_TERMINAL_FIELDS))!r}
ALGORITHM = {GPU_ALGORITHM!r}
CLASSIFICATION = {GPU_CLASSIFICATION!r}
SCHEMA = {GPU_SCHEMA!r}
FAULT = {fault!r}

p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--count", type=int, required=True)
p.add_argument("--shard-rows", type=int, required=True)
p.add_argument("--super-shard-rows", type=int, required=True)
p.add_argument("--incoming-mertens", type=int, required=True)
p.add_argument("--incoming-squarefree", type=int, required=True)
p.add_argument("--previous-leaf-sha256", required=True)
p.add_argument("--source-prime-roster", required=True)
p.add_argument("--device", type=int, required=True)
p.add_argument(
    "--require-device-class",
    choices=("nvidia-h100-sm90",),
    required=True,
)
p.add_argument("--allow-other-device", action="store_true")
a = p.parse_args()
if FAULT == "partial_line":
    sys.stdout.write("{{")
    sys.stdout.flush()
    time.sleep(5)
    raise SystemExit(0)
upper_exclusive = a.lower + a.count
executable_sha256 = hashlib.sha256(Path(sys.argv[0]).read_bytes()).hexdigest()
roster_sha256 = hashlib.sha256(
    Path(a.source_prime_roster).read_bytes()
).hexdigest()

header = {{name: 0 for name in HEADER_FIELDS}}
header.update({{
    "record": "header",
    "schema": SCHEMA,
    "algorithm": ALGORITHM,
    "classification": CLASSIFICATION,
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "count": a.count,
    "shard_rows": a.shard_rows,
    "super_shard_rows": a.super_shard_rows,
    "prime_roster_sha256": roster_sha256,
    "executable_sha256": executable_sha256,
    "prime_roster_load_count": 1,
    "prime_roster_upload_count": 1,
    "cuda_allocation_epoch_count": 1,
    "cuda_event_set_count": 1,
    "fused_support_load_balanced_dense_schedule": True,
    "fused_support_residue_235_initializer": True,
    "residue_235_initializer_table_rows": 900,
    "residue_235_initializer_table_bytes": 7200,
    "residue_235_table_storage": "fatbinary_device_global_init",
    "residue_235_table_materialization_scope": "cuda_module_context_load",
    "residue_235_explicit_h2d_upload_bytes_per_sieve": 0,
    "fused_multiblock_dense_prime_limit": 200,
    "fused_multiblock_slots_per_prime": 512,
    "fused_multiblock_unseeded_slots_per_prime": 512,
    "fused_multiblock_residue_235_slots_per_prime": 512,
    "fused_multiblock_residue_235_minimum_safe_slots_per_prime": 147,
    "fused_multiblock_iterations_per_thread": 4096,
    "affine_candidates_transferred_per_leaf": 1,
    "affine_candidate_bytes_per_leaf": 64,
    "affine_prefix_device_bytes": min(a.count, a.shard_rows) * 8,
    "affine_workspace_device_bytes": 64,
    "fused_support_device_bytes": min(a.count, a.super_shard_rows) * 8,
    "mobius_device_bytes": 0,
    "persistent_device_allocation_bytes": 348,
    "device_free_bytes_before_allocation": 1 << 30,
    "device_total_bytes": 2 << 30,
    "production_device_to_host_bytes_per_leaf": 76,
    "production_mu_rows_transferred": False,
    "production_mu_rows_hashed": False,
    "production_fused_prefix_input_path": True,
    "production_split_square_support_path": True,
    "inline_square_modulo_reference_path": False,
    "distinct_factor_events_compute_square_modulo": False,
    "separate_square_strike_pass": True,
    "split_square_dense_prime_limit": 200,
    "split_square_operation_order":
        "initialize_then_distinct_then_square_then_finalize",
    "intermediate_mobius_device_rows_materialized": False,
    "leaf_chain_binds_compact_gpu_summary": True,
    "mu_row_commitment_present_in_production": False,
    "host_rechecks_final_squarefree_winners": True,
    "little_mertens_deltas_are_exact_zero": True,
    "qualification_mu_output": False,
    "source_rows_replayed_independently": False,
    "full_source_range": False,
    "execution_attested": False,
    "cuda_or_cpp_compiler_refinement_proved": False,
    "primitive_mobius_realization_proved": False,
    "lean_atom_discharged": False,
    "proves_any_external_atom": False,
    "roster_load_milliseconds": "0",
    "allocation_milliseconds": "0",
    "roster_upload_milliseconds": "0",
}})
if FAULT == "unsafe_flag":
    header["execution_attested"] = True
if FAULT == "bool_counter":
    header["prime_roster_load_count"] = True
if FAULT == "allocation":
    header["persistent_device_allocation_bytes"] += 1
header_text = json.dumps(header, sort_keys=True, separators=(",", ":"))
if FAULT == "duplicate_key":
    header_text = header_text[:-1] + ',"record":"header"}}'
print(header_text)

def leaf_digest(record):
    square_lower_order = 2 * (
        record["squarefree_lower"]["witness_y"] - record["lower"]
    ) - (record["squarefree_lower"]["side"] == "right_limit")
    square_upper_order = 2 * (
        record["squarefree_upper"]["witness_y"] - record["lower"]
    ) - (record["squarefree_upper"]["side"] == "right_limit")
    text = (
        "domain=sparkinterval.tg.mobius-persistent-leaf.v1\\n"
        f"algorithm={{ALGORITHM}}\\n"
        f"executable_sha256={{executable_sha256}}\\n"
        f"prime_roster_sha256={{roster_sha256}}\\n"
        f"previous={{record['previous_leaf_sha256']}}\\n"
        f"lower={{record['lower']}}\\n"
        f"upper_exclusive={{record['upper_exclusive']}}\\n"
        "poison_count=0\\n"
        f"incoming_mertens={{record['incoming_mertens']}}\\n"
        f"outgoing_mertens={{record['outgoing_mertens']}}\\n"
        f"delta_mertens={{record['delta_mertens']}}\\n"
        f"incoming_squarefree={{record['incoming_squarefree']}}\\n"
        f"outgoing_squarefree={{record['outgoing_squarefree']}}\\n"
        f"delta_squarefree={{record['delta_squarefree']}}\\n"
        f"hurst_lower={{record['hurst_lower']['value']}}\\n"
        f"hurst_lower_y={{record['hurst_lower']['witness_y']}}\\n"
        f"hurst_upper={{record['hurst_upper']['value']}}\\n"
        f"hurst_upper_y={{record['hurst_upper']['witness_y']}}\\n"
        f"squarefree_lower={{record['squarefree_lower']['value']}}\\n"
        f"squarefree_lower_y={{record['squarefree_lower']['witness_y']}}\\n"
        f"squarefree_lower_order={{square_lower_order}}\\n"
        f"squarefree_upper={{record['squarefree_upper']['value']}}\\n"
        f"squarefree_upper_y={{record['squarefree_upper']['witness_y']}}\\n"
        f"squarefree_upper_order={{square_upper_order}}\\n"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

leaf_specs = (
    {{
        "delta_mertens": 3,
        "delta_squarefree": 4,
        "hurst_lower": {{"value": 0, "witness_y": 18}},
        "hurst_upper": {{"value": 5, "witness_y": 19}},
        "squarefree_lower": {{
            "value": 8, "witness_y": 18, "side": "integer"
        }},
        "squarefree_upper": {{
            "value": 14, "witness_y": 19, "side": "right_limit"
        }},
    }},
    {{
        "delta_mertens": -2,
        "delta_squarefree": 3,
        "hurst_lower": {{"value": 4, "witness_y": 26}},
        "hurst_upper": {{"value": 6, "witness_y": 27}},
        "squarefree_lower": {{
            "value": 13, "witness_y": 33, "side": "right_limit"
        }},
        "squarefree_upper": {{
            "value": 15, "witness_y": 27, "side": "integer"
        }},
    }},
)
if FAULT == "guard_exclusion":
    leaf_specs[0]["hurst_lower"] = {{"value": 3, "witness_y": 18}}
    leaf_specs[1]["hurst_lower"] = {{"value": 6, "witness_y": 26}}
previous = a.previous_leaf_sha256
current_mertens = a.incoming_mertens
current_squarefree = a.incoming_squarefree
leaves = []
for index, spec in enumerate(leaf_specs):
    lower = a.lower + index * a.shard_rows
    upper = min(lower + a.shard_rows, upper_exclusive)
    leaf = {{name: 0 for name in LEAF_FIELDS}}
    leaf.update({{
        "record": "leaf",
        "index": index,
        "lower": lower,
        "upper_exclusive": upper,
        "count": upper - lower,
        "previous_leaf_sha256": previous,
        "leaf_sha256": "0" * 64,
        "qualification_mu_plus_one_sha256": None,
        "incoming_mertens": current_mertens,
        "outgoing_mertens": current_mertens + spec["delta_mertens"],
        "delta_mertens": spec["delta_mertens"],
        "incoming_squarefree": current_squarefree,
        "outgoing_squarefree":
            current_squarefree + spec["delta_squarefree"],
        "delta_squarefree": spec["delta_squarefree"],
        "hurst_lower": spec["hurst_lower"],
        "hurst_upper": spec["hurst_upper"],
        "squarefree_lower": spec["squarefree_lower"],
        "squarefree_upper": spec["squarefree_upper"],
        "source_prime_fast_path": True,
        "selected_prime_count": 3,
        "dense_prime_count": 0,
        "super_shard_index": 0,
        "super_shard_leaf_index": index,
        "super_shard_lower": a.lower,
        "super_shard_upper_exclusive": upper_exclusive,
        "super_shard_count": a.count,
        "active_prime_filter_milliseconds": "0",
        "active_prime_upload_milliseconds": "0",
        "kernel_milliseconds": "0",
        "super_shard_sieve_kernel_milliseconds": "0",
        "affine_milliseconds": "0",
        "transfer_milliseconds": "0",
        "control_loop_milliseconds": "0",
        "affine_candidate_bytes_transferred": 64,
        "poison_count": 0,
        "production_device_to_host_bytes": 76,
        "qualification_device_to_host_mu_bytes": 0,
        "mu_row_commitment_present": False,
        "source_rows_replayed_independently": False,
        "execution_attested": False,
        "cuda_or_cpp_compiler_refinement_proved": False,
        "lean_atom_discharged": False,
        "proves_any_external_atom": False,
    }})
    if FAULT == "continuity" and index == 1:
        leaf["incoming_mertens"] += 1
        leaf["outgoing_mertens"] += 1
    if FAULT == "selected_prime_count" and index == 0:
        leaf["selected_prime_count"] = 999
    leaf["leaf_sha256"] = leaf_digest(leaf)
    if FAULT == "bad_digest" and index == 0:
        leaf["leaf_sha256"] = "0" * 64
    print(json.dumps(leaf, sort_keys=True, separators=(",", ":")))
    leaves.append(leaf)
    previous = leaf["leaf_sha256"]
    current_mertens = leaf["outgoing_mertens"]
    current_squarefree = leaf["outgoing_squarefree"]

terminal = {{name: 0 for name in TERMINAL_FIELDS}}
terminal.update({{
    "record": "terminal",
    "algorithm": ALGORITHM,
    "classification": CLASSIFICATION,
    "lower": a.lower,
    "upper_exclusive": upper_exclusive,
    "count": a.count,
    "leaf_count": len(leaves),
    "final_leaf_sha256": previous,
    "production_mu_row_commitment_present": False,
    "incoming_mertens": a.incoming_mertens,
    "outgoing_mertens": current_mertens,
    "delta_mertens": current_mertens - a.incoming_mertens,
    "incoming_squarefree": a.incoming_squarefree,
    "outgoing_squarefree": current_squarefree,
    "delta_squarefree": current_squarefree - a.incoming_squarefree,
    "global_hurst_lower": {{
        "value": 1, "witness_y": 26, "source_order": 18
    }},
    "global_hurst_upper": {{
        "value": 3, "witness_y": 27, "source_order": 20
    }},
    "global_squarefree_lower": {{
        "value": 9, "witness_y": 33, "source_order": 31,
        "side": "right_limit"
    }},
    "global_squarefree_upper": {{
        "value": 11, "witness_y": 27, "source_order": 20,
        "side": "integer"
    }},
    "source_fast_path_leaf_count": len(leaves),
    "source_fast_path_super_shard_count": 1,
    "super_shard_count": 1,
    "sieve_launch_count": 1,
    "receipt_leaf_count": len(leaves),
    "sieve_launches_saved_vs_leaf_schedule": len(leaves) - 1,
    "super_shard_rows": a.super_shard_rows,
    "active_filter_milliseconds": "0",
    "active_prime_upload_milliseconds": "0",
    "kernel_milliseconds": "0",
    "affine_milliseconds": "0",
    "transfer_milliseconds": "0",
    "control_loop_milliseconds": "0",
    "roster_load_count": 1,
    "roster_upload_count": 1,
    "allocation_epoch_count": 1,
    "event_set_count": 1,
    "buffers_reused_across_all_leaves": True,
    "affine_candidates_transferred_per_leaf": 1,
    "affine_candidate_bytes_per_leaf": 64,
    "production_device_to_host_bytes_per_leaf": 76,
    "production_mu_rows_transferred": False,
    "production_mu_rows_hashed": False,
    "leaf_chain_binds_compact_gpu_summary": True,
    "host_rechecks_final_squarefree_winners": True,
    "checkpoint_restart_fields_emitted_per_leaf": True,
    "little_mertens_lower_delta": 0,
    "little_mertens_upper_delta": 0,
    "source_rows_replayed_independently": False,
    "full_source_range": False,
    "execution_attested": False,
    "cuda_or_cpp_compiler_refinement_proved": False,
    "primitive_mobius_realization_proved": False,
    "lean_atom_discharged": False,
    "proves_any_external_atom": False,
    "process_milliseconds": "0",
}})
if FAULT == "guard_exclusion":
    terminal["global_hurst_lower"] = {{
        "value": 3, "witness_y": 18, "source_order": 2
    }}
print(json.dumps(terminal, sort_keys=True, separators=(",", ":")))
if FAULT == "trailing":
    print(json.dumps({{"record": "trailing"}}, separators=(",", ":")))
"""


def _make_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
        else:
            path.chmod(0o600)
    root.chmod(0o700)


class HurstHybridSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.roster = self.root / "source-prime-roster.bin"
        self.roster.write_bytes(b"tiny pinned prime roster\n")

    def tearDown(self) -> None:
        for path in self.root.iterdir():
            if path.is_dir():
                _make_writable(path)
        self.temporary.cleanup()

    def _write_runner(self, name: str, source: str) -> Path:
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return path

    def _materialize(
        self,
        *,
        cpu_mismatch: bool = False,
        gpu_fault: str = "none",
        name: str = "materialization",
    ) -> Path:
        cpu_runner = self._write_runner(
            f"{name}-cpu.py", _cpu_runner_source(mismatch=cpu_mismatch)
        )
        h100_runner = self._write_runner(
            f"{name}-h100.py", _h100_runner_source(fault=gpu_fault)
        )
        output = self.root / name
        materialize(
            cpu_runner=cpu_runner,
            h100_runner=h100_runner,
            prime_roster=self.roster,
            output_directory=output,
            cpu_segment_rows=CPU_SEGMENT_ROWS,
            h100_leaf_rows=GPU_LEAF_ROWS,
            h100_super_shard_rows=GPU_SUPER_ROWS,
            split=CPU_UPPER,
            upper_exclusive=GPU_UPPER,
            allow_bounded_test=True,
        )
        return output

    def _run(self, materialization: Path, name: str = "execution") -> dict:
        return run(
            materialization_directory=materialization,
            output_directory=self.root / name,
            cpu_timeout_seconds=10,
            h100_timeout_seconds=10,
        )

    def test_cli_bootstraps_repository_imports_outside_checkout(self) -> None:
        cli = Path(__file__).resolve().parents[1] / (
            "tools/tg_hurst_hybrid_source.py"
        )
        completed = subprocess.run(
            [sys.executable, str(cli), "--help"],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("{materialize,run}", completed.stdout)

    def test_positive_chain_extrema_and_immutable_outputs(self) -> None:
        materialization = self._materialize()
        result = self._run(materialization)
        output = Path(result["output_directory"])

        self.assertFalse(result["accepted"])
        self.assertTrue(result["arithmetic_execution_completed"])
        self.assertFalse(result["source_run_receipt_produced"])
        self.assertEqual(result["semantic_flags"], SEMANTIC_FLAGS)
        self.assertEqual(result["final_state"], [3, 17, -5, 7])
        self.assertEqual(result["h100_leaf_count"], 2)

        handoff = load_json(output / "cpu-handoff.json")
        retained_plan_raw = (output / "hybrid-plan.json").read_bytes()
        records = [
            json.loads(line)
            for line in (output / "h100-receipts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        header, first, second, terminal = records
        plan = load_json(materialization / "hybrid-plan.json")
        self.assertEqual(load_json(output / "hybrid-plan.json"), plan)
        self.assertEqual(
            result["plan_artifact"],
            {
                "path": "hybrid-plan.json",
                "sha256": hashlib.sha256(retained_plan_raw).hexdigest(),
                "size_bytes": len(retained_plan_raw),
            },
        )
        handoff_payload = dict(handoff)
        handoff_chain = handoff_payload.pop("receipt_chain_sha256")
        self.assertEqual(
            handoff_chain,
            hashlib.sha256(
                b"sparkinterval/tg/hurst-cpu-h100-handoff/v1\0"
                + canonical_json_bytes(handoff_payload)
            ).hexdigest(),
        )
        self.assertEqual(handoff["outgoing_state"], list(CPU_DELTA))
        self.assertEqual(
            first["previous_leaf_sha256"],
            handoff_chain,
        )
        self.assertEqual(
            header["executable_sha256"],
            plan["inputs"]["h100_runner"]["sha256"],
        )
        self.assertEqual(
            header["prime_roster_sha256"],
            plan["inputs"]["prime_roster"]["sha256"],
        )
        self.assertEqual(second["previous_leaf_sha256"], first["leaf_sha256"])
        for leaf in (first, second):
            self.assertEqual(
                leaf["leaf_sha256"],
                _replay_leaf_digest(
                    leaf,
                    executable_sha256=plan["inputs"]["h100_runner"]["sha256"],
                    roster_sha256=plan["inputs"]["prime_roster"]["sha256"],
                ),
            )
        self.assertEqual(
            terminal["global_hurst_lower"],
            {"value": 1, "witness_y": 26, "source_order": 18},
        )
        self.assertEqual(
            terminal["global_hurst_upper"],
            {"value": 3, "witness_y": 27, "source_order": 20},
        )
        self.assertEqual(
            terminal["global_squarefree_upper"],
            {
                "value": 11,
                "witness_y": 27,
                "source_order": 20,
                "side": "integer",
            },
        )
        self.assertEqual(
            terminal["global_squarefree_lower"],
            {
                "value": 9,
                "witness_y": 33,
                "source_order": 31,
                "side": "right_limit",
            },
        )
        self.assertLessEqual(
            terminal["global_hurst_lower"]["value"],
            handoff["outgoing_state"][0],
        )
        self.assertLessEqual(
            handoff["outgoing_state"][0],
            terminal["global_hurst_upper"]["value"],
        )
        self.assertLessEqual(
            terminal["global_squarefree_lower"]["value"],
            handoff["outgoing_state"][1],
        )
        self.assertLessEqual(
            handoff["outgoing_state"][1],
            terminal["global_squarefree_upper"]["value"],
        )
        self.assertEqual(terminal["final_leaf_sha256"], second["leaf_sha256"])
        self.assertEqual(result["final_leaf_sha256"], second["leaf_sha256"])

        for tree in (materialization, output):
            self.assertEqual(tree.stat().st_mode & 0o222, 0)
            for path in tree.rglob("*"):
                self.assertEqual(path.stat().st_mode & 0o222, 0, str(path))
        with self.assertRaises(HurstHybridSourceError):
            self._run(materialization)

    def test_production_and_bounded_geometry_are_literal(self) -> None:
        self.assertEqual(DEFAULT_H100_SUPER_SHARD_ROWS, 100_000_000)
        production = source_geometry()
        self.assertEqual(production["source_lower"], SOURCE_LOWER)
        self.assertEqual(production["cpu"]["upper_exclusive"], CPU_UPPER_EXCLUSIVE)
        self.assertEqual(production["split"], H100_LOWER)
        self.assertEqual(
            production["source_upper_exclusive"], SOURCE_UPPER_EXCLUSIVE
        )
        self.assertTrue(production["gap_free"])
        bounded = source_geometry(
            split=CPU_UPPER,
            upper_exclusive=GPU_UPPER,
            allow_bounded_test=True,
        )
        self.assertEqual(bounded["cpu"], {
            "count": 16, "lower": 1, "upper_exclusive": 17
        })
        self.assertEqual(bounded["h100"], {
            "count": 16, "lower": 17, "upper_exclusive": 33
        })
        with self.assertRaises(HurstHybridSourceError):
            source_geometry(split=CPU_UPPER, upper_exclusive=GPU_UPPER)
        with self.assertRaises(HurstHybridSourceError):
            source_geometry(
                split=CPU_UPPER,
                upper_exclusive=100,
                allow_bounded_test=True,
            )

    def test_materialization_rejects_symlinked_input(self) -> None:
        cpu_runner = self._write_runner("cpu-real.py", _cpu_runner_source())
        symlink = self.root / "cpu-link.py"
        symlink.symlink_to(cpu_runner)
        h100_runner = self._write_runner(
            "h100.py", _h100_runner_source()
        )
        with self.assertRaises(HurstHybridSourceError):
            materialize(
                cpu_runner=symlink,
                h100_runner=h100_runner,
                prime_roster=self.roster,
                output_directory=self.root / "rejected-materialization",
                cpu_segment_rows=CPU_SEGMENT_ROWS,
                h100_leaf_rows=GPU_LEAF_ROWS,
                h100_super_shard_rows=GPU_SUPER_ROWS,
                split=CPU_UPPER,
                upper_exclusive=GPU_UPPER,
                allow_bounded_test=True,
            )
        self.assertFalse((self.root / "rejected-materialization").exists())

    def test_captured_input_identity_tamper_is_rejected(self) -> None:
        materialization = self._materialize(name="identity-materialization")
        _make_writable(materialization)
        captured = materialization / "inputs/cpu-hurst-runner"
        captured.write_bytes(captured.read_bytes() + b"\n# tampered\n")
        with self.assertRaises(HurstHybridSourceError):
            self._run(materialization, "identity-execution")
        self.assertFalse((self.root / "identity-execution").exists())

    def test_post_validation_cpu_runner_swap_is_not_executed(self) -> None:
        materialization = self._materialize(name="swap-materialization")
        marker = self.root / "swapped-runner-executed"
        original_load = hybrid_module._load_plan

        def load_then_swap(root: Path) -> tuple[dict, str]:
            loaded = original_load(root)
            _make_writable(materialization)
            captured = materialization / "inputs/cpu-hurst-runner"
            captured.write_text(
                "#!/usr/bin/python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            captured.chmod(0o700)
            return loaded

        with mock.patch.object(
            hybrid_module, "_load_plan", side_effect=load_then_swap
        ):
            with self.assertRaises(HurstHybridSourceError):
                self._run(materialization, "swap-execution")
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "swap-execution").exists())

    def test_plan_identity_is_bound_by_materialization_manifest(self) -> None:
        materialization = self._materialize(name="plan-materialization")
        _make_writable(materialization)
        plan_path = materialization / "hybrid-plan.json"
        plan = load_json(plan_path)
        plan["classification"] = "tampered-but-canonical-plan"
        plan_path.write_bytes(canonical_json_bytes(plan))
        with self.assertRaises(HurstHybridSourceError):
            self._run(materialization, "plan-execution")
        self.assertFalse((self.root / "plan-execution").exists())

    def test_cpu_summary_verify_mismatch_is_rejected(self) -> None:
        materialization = self._materialize(
            cpu_mismatch=True, name="cpu-mismatch-materialization"
        )
        with self.assertRaises(HurstHybridSourceError):
            self._run(materialization, "cpu-mismatch-execution")
        self.assertFalse((self.root / "cpu-mismatch-execution").exists())

    def test_device_class_cannot_be_relaxed(self) -> None:
        materialization = self._materialize(name="device-materialization")
        with self.assertRaises(HurstHybridSourceError):
            run(
                materialization_directory=materialization,
                output_directory=self.root / "device-execution",
                cpu_timeout_seconds=10,
                h100_timeout_seconds=10,
                allow_other_device=True,
            )
        self.assertFalse((self.root / "device-execution").exists())

    def test_gpu_stream_tampering_is_rejected(self) -> None:
        for index, fault in enumerate(
            (
                "bad_digest",
                "continuity",
                "trailing",
                "unsafe_flag",
                "guard_exclusion",
                "bool_counter",
                "allocation",
                "duplicate_key",
                "selected_prime_count",
            )
        ):
            with self.subTest(fault=fault):
                materialization = self._materialize(
                    gpu_fault=fault,
                    name=f"gpu-{index}-materialization",
                )
                output = f"gpu-{index}-execution"
                with self.assertRaises(HurstHybridSourceError):
                    self._run(materialization, output)
                self.assertFalse((self.root / output).exists())

    def test_partial_jsonl_line_obeys_h100_timeout(self) -> None:
        materialization = self._materialize(
            gpu_fault="partial_line",
            name="partial-timeout-materialization",
        )
        started = time.monotonic()
        with self.assertRaisesRegex(HurstHybridSourceError, "timed out"):
            run(
                materialization_directory=materialization,
                output_directory=self.root / "partial-timeout-execution",
                cpu_timeout_seconds=10,
                h100_timeout_seconds=1,
            )
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertFalse((self.root / "partial-timeout-execution").exists())


if __name__ == "__main__":
    unittest.main()
