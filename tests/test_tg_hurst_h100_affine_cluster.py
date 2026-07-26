#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact-scan and process-routing tests for the eight-H100 Hurst path."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tg_verifier.campaign_io import canonical_json_bytes
import tg_verifier.hurst_h100_affine_cluster as cluster_module
from tg_verifier.hurst_h100_affine_cluster import (
    ALGORITHM,
    HurstH100AffineClusterError,
    PLAN_KIND,
    SCAN_KIND,
    SCHEMA_VERSION,
    WORKER_STATUS_KIND,
    build_cluster_plan,
    compose_worker_terminals,
    partition_affine_range,
    proxy_squarefree_state,
    worker_anchor,
    worker_command,
)
from tg_verifier.hurst_hybrid_source import (
    CPU_HANDOFF_KIND,
    GPU_CLASSIFICATION,
    GPU_HEADER_FIELDS,
    GPU_LEAF_FIELDS,
    GPU_SCHEMA,
    GPU_TERMINAL_FIELDS,
    SEMANTIC_FLAGS,
    materialize,
)
from tg_verifier.hurst_residual_campaign import (
    ATOM_PROFILES,
    RUNNER_ALGORITHM,
    RUNNER_CLASSIFICATION,
    STATE_COMPONENTS,
    UPSTREAM_COMMIT,
)


CPU_STATE = (2, 10, -5, 7)
NONZERO = "1" * 64


def _cpu_runner_source() -> str:
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
upper = a.upper + 1
incoming = [
    a.incoming_mertens, a.incoming_squarefree,
    a.incoming_little_lower, a.incoming_little_upper,
]
guards = {{}}
if a.mode == "verify":
    guards = {{
        atom: {{"lower": incoming, "upper": incoming, "witnesses": []}}
        for atom in {tuple(ATOM_PROFILES)!r}
    }}
print(json.dumps({{
    "algorithm": {RUNNER_ALGORITHM!r},
    "mode": a.mode,
    "classification": {RUNNER_CLASSIFICATION!r},
    "upstream_commit": {UPSTREAM_COMMIT!r},
    "lower": a.lower,
    "upper_exclusive": upper,
    "work_count": upper - a.lower,
    "segment_size": a.segment_size,
    "segments": (upper - a.lower + a.segment_size - 1) // a.segment_size,
    "row_encoding": "mu-plus-one-block-sha256-v1",
    "squarefree_threshold_endpoint_policy":
        "inclusive-value-and-right-limit-v2",
    "reduction_block_rows": 1048576,
    "row_sha256": hashlib.sha256(b"cluster-cpu-rows").hexdigest(),
    "state_components": {list(STATE_COMPONENTS)!r},
    "delta": {list(CPU_STATE)!r},
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


def _h100_runner_source() -> str:
    return f"""#!/usr/bin/python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HEADER_FIELDS = {tuple(sorted(GPU_HEADER_FIELDS))!r}
LEAF_FIELDS = {tuple(sorted(GPU_LEAF_FIELDS))!r}
TERMINAL_FIELDS = {tuple(sorted(GPU_TERMINAL_FIELDS))!r}
p = argparse.ArgumentParser()
p.add_argument("--lower", type=int, required=True)
p.add_argument("--count", type=int, required=True)
p.add_argument("--shard-rows", type=int, required=True)
p.add_argument("--super-shard-rows", type=int, required=True)
p.add_argument("--incoming-mertens", type=int, required=True)
p.add_argument("--incoming-squarefree", type=int, required=True)
p.add_argument("--previous-leaf-sha256", required=True)
p.add_argument("--source-prime-roster", required=True)
p.add_argument("--require-device-class", required=True)
p.add_argument("--device", type=int, required=True)
a = p.parse_args()
upper = a.lower + a.count
exe_sha = hashlib.sha256(Path(sys.argv[0]).read_bytes()).hexdigest()
roster_sha = hashlib.sha256(
    Path(a.source_prime_roster).read_bytes()
).hexdigest()
if a.lower == 17:
    dm, dq = 3, 4
    ml, mu, ql, qu = -5, 5, 8, 20
else:
    dm, dq = -2, 3
    # A distributed one-GPU node routes every worker through visible device
    # zero.  Make that worker's proxy M=0 inadmissible while the exact derived
    # M=5 remains admissible, proving proxy acceptance is not required.
    ml = 4 if os.environ.get("CUDA_VISIBLE_DEVICES") == "0" else -5
    mu, ql, qu = 6, 10, 25

header = {{name: 0 for name in HEADER_FIELDS}}
header.update({{
    "record": "header",
    "schema": {GPU_SCHEMA!r},
    "algorithm": {cluster_module.GPU_ALGORITHM!r},
    "classification": {GPU_CLASSIFICATION!r},
    "lower": a.lower,
    "upper_exclusive": upper,
    "count": a.count,
    "shard_rows": a.shard_rows,
    "super_shard_rows": a.super_shard_rows,
    "prime_roster_sha256": roster_sha,
    "executable_sha256": exe_sha,
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
    "affine_prefix_device_bytes": 128,
    "affine_workspace_device_bytes": 64,
    "fused_support_device_bytes": 128,
    "mobius_device_bytes": 0,
    "persistent_device_allocation_bytes": 412,
    "device_free_bytes_before_allocation": 1 << 30,
    "device_total_bytes": 2 << 30,
    "production_device_to_host_bytes_per_leaf": 76,
    "production_mu_rows_transferred": False,
    "production_mu_rows_hashed": False,
    "leaf_chain_binds_compact_gpu_summary": True,
    "mu_row_commitment_present_in_production": False,
    "host_rechecks_final_squarefree_winners": True,
    "little_mertens_deltas_are_exact_zero": True,
    "production_fused_prefix_input_path": True,
    "production_split_square_support_path": True,
    "inline_square_modulo_reference_path": False,
    "distinct_factor_events_compute_square_modulo": False,
    "separate_square_strike_pass": True,
    "split_square_dense_prime_limit": 200,
    "split_square_operation_order":
        "initialize_then_distinct_then_square_then_finalize",
    "intermediate_mobius_device_rows_materialized": False,
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
print(json.dumps(header, sort_keys=True, separators=(",", ":")))

leaf = {{name: 0 for name in LEAF_FIELDS}}
leaf.update({{
    "record": "leaf",
    "index": 0,
    "lower": a.lower,
    "upper_exclusive": upper,
    "count": a.count,
    "previous_leaf_sha256": a.previous_leaf_sha256,
    "leaf_sha256": "0" * 64,
    "qualification_mu_plus_one_sha256": None,
    "incoming_mertens": a.incoming_mertens,
    "outgoing_mertens": a.incoming_mertens + dm,
    "delta_mertens": dm,
    "incoming_squarefree": a.incoming_squarefree,
    "outgoing_squarefree": a.incoming_squarefree + dq,
    "delta_squarefree": dq,
    "hurst_lower": {{"value": ml, "witness_y": a.lower}},
    "hurst_upper": {{"value": mu, "witness_y": a.lower}},
    "squarefree_lower": {{
        "value": ql, "witness_y": a.lower, "side": "integer"
    }},
    "squarefree_upper": {{
        "value": qu, "witness_y": a.lower, "side": "integer"
    }},
    "source_prime_fast_path": True,
    "selected_prime_count": 3,
    "dense_prime_count": 0,
    "super_shard_index": 0,
    "super_shard_leaf_index": 0,
    "super_shard_lower": a.lower,
    "super_shard_upper_exclusive": upper,
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
# Spell the production digest protocol literally.
text = (
    "domain=sparkinterval.tg.mobius-persistent-leaf.v1\\n"
    "algorithm={cluster_module.GPU_ALGORITHM}\\n"
    f"executable_sha256={{exe_sha}}\\n"
    f"prime_roster_sha256={{roster_sha}}\\n"
    f"previous={{leaf['previous_leaf_sha256']}}\\n"
    f"lower={{leaf['lower']}}\\n"
    f"upper_exclusive={{leaf['upper_exclusive']}}\\n"
    "poison_count=0\\n"
    f"incoming_mertens={{leaf['incoming_mertens']}}\\n"
    f"outgoing_mertens={{leaf['outgoing_mertens']}}\\n"
    f"delta_mertens={{leaf['delta_mertens']}}\\n"
    f"incoming_squarefree={{leaf['incoming_squarefree']}}\\n"
    f"outgoing_squarefree={{leaf['outgoing_squarefree']}}\\n"
    f"delta_squarefree={{leaf['delta_squarefree']}}\\n"
    f"hurst_lower={{ml}}\\n"
    f"hurst_lower_y={{a.lower}}\\n"
    f"hurst_upper={{mu}}\\n"
    f"hurst_upper_y={{a.lower}}\\n"
    f"squarefree_lower={{ql}}\\n"
    f"squarefree_lower_y={{a.lower}}\\n"
    "squarefree_lower_order=0\\n"
    f"squarefree_upper={{qu}}\\n"
    f"squarefree_upper_y={{a.lower}}\\n"
    "squarefree_upper_order=0\\n"
)
leaf["leaf_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
print(json.dumps(leaf, sort_keys=True, separators=(",", ":")))

terminal = {{name: 0 for name in TERMINAL_FIELDS}}
terminal.update({{
    "record": "terminal",
    "algorithm": {cluster_module.GPU_ALGORITHM!r},
    "classification": {GPU_CLASSIFICATION!r},
    "lower": a.lower,
    "upper_exclusive": upper,
    "count": a.count,
    "leaf_count": 1,
    "final_leaf_sha256": leaf["leaf_sha256"],
    "production_mu_row_commitment_present": False,
    "incoming_mertens": a.incoming_mertens,
    "outgoing_mertens": a.incoming_mertens + dm,
    "delta_mertens": dm,
    "incoming_squarefree": a.incoming_squarefree,
    "outgoing_squarefree": a.incoming_squarefree + dq,
    "delta_squarefree": dq,
    "global_hurst_lower": {{
        "value": ml, "witness_y": a.lower, "source_order": 0
    }},
    "global_hurst_upper": {{
        "value": mu, "witness_y": a.lower, "source_order": 0
    }},
    "global_squarefree_lower": {{
        "value": ql, "witness_y": a.lower, "source_order": 0,
        "side": "integer"
    }},
    "global_squarefree_upper": {{
        "value": qu, "witness_y": a.lower, "source_order": 0,
        "side": "integer"
    }},
    "source_fast_path_leaf_count": 1,
    "source_fast_path_super_shard_count": 1,
    "super_shard_count": 1,
    "sieve_launch_count": 1,
    "receipt_leaf_count": 1,
    "sieve_launches_saved_vs_leaf_schedule": 0,
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
print(json.dumps(terminal, sort_keys=True, separators=(",", ":")))
"""


def _minimal_cluster_plan() -> dict:
    return {
        "algorithm": ALGORITHM,
        "classification": cluster_module.CLASSIFICATION,
        "cpu_handoff_sha256": "2" * 64,
        "device_policy": {
            "attestation_present": False,
            "device_identity_present": False,
            "logical_cuda_device": 0,
            "required_device_class": "nvidia-h100-sm90",
            "selectors_are_process_routing_only": True,
            "visible_device_count_required_by_worker": 1,
        },
        "hybrid_plan_sha256": NONZERO,
        "kind": PLAN_KIND,
        "leaf_rows": 8,
        "mode": "bounded_test",
        "schema_version": SCHEMA_VERSION,
        "semantic_flags": dict(SEMANTIC_FLAGS),
        "state_components": list(STATE_COMPONENTS),
        "super_shard_rows": 8,
        "worker_assignments": [
            {
                "count": 8,
                "cuda_visible_devices_selector": "0",
                "index": 0,
                "logical_cuda_device": 0,
                "lower": 17,
                "proxy_incoming_mertens": 0,
                "proxy_incoming_squarefree": 10,
                "proxy_state_is_sequential_state": False,
                "super_shard_count": 1,
                "upper_exclusive": 25,
            },
            {
                "count": 8,
                "cuda_visible_devices_selector": "1",
                "index": 1,
                "logical_cuda_device": 0,
                "lower": 25,
                "proxy_incoming_mertens": 5,
                "proxy_incoming_squarefree": 14,
                "proxy_state_is_sequential_state": False,
                "super_shard_count": 1,
                "upper_exclusive": 33,
            },
        ],
        "worker_count": 2,
    }


def _terminal(
    *,
    lower: int,
    upper: int,
    proxy_m: int,
    proxy_q: int,
    delta_m: int,
    delta_q: int,
    m_lower: tuple[int, int, int],
    m_upper: tuple[int, int, int],
    q_lower: tuple[int, int, int, str],
    q_upper: tuple[int, int, int, str],
) -> dict:
    return {
        "algorithm": cluster_module.GPU_ALGORITHM,
        "count": upper - lower,
        "delta_mertens": delta_m,
        "delta_squarefree": delta_q,
        "final_leaf_sha256": hashlib.sha256(
            f"{lower}:{upper}".encode("ascii")
        ).hexdigest(),
        "global_hurst_lower": {
            "source_order": m_lower[2],
            "value": m_lower[0],
            "witness_y": m_lower[1],
        },
        "global_hurst_upper": {
            "source_order": m_upper[2],
            "value": m_upper[0],
            "witness_y": m_upper[1],
        },
        "global_squarefree_lower": {
            "side": q_lower[3],
            "source_order": q_lower[2],
            "value": q_lower[0],
            "witness_y": q_lower[1],
        },
        "global_squarefree_upper": {
            "side": q_upper[3],
            "source_order": q_upper[2],
            "value": q_upper[0],
            "witness_y": q_upper[1],
        },
        "incoming_mertens": proxy_m,
        "incoming_squarefree": proxy_q,
        "lower": lower,
        "outgoing_mertens": proxy_m + delta_m,
        "outgoing_squarefree": proxy_q + delta_q,
        "record": "terminal",
        "upper_exclusive": upper,
    }


def _statuses(plan: dict) -> list[dict]:
    plan_sha = hashlib.sha256(canonical_json_bytes(plan)).hexdigest()
    first, second = plan["worker_assignments"]
    terminals = (
        _terminal(
            lower=17,
            upper=25,
            proxy_m=first["proxy_incoming_mertens"],
            proxy_q=first["proxy_incoming_squarefree"],
            delta_m=3,
            delta_q=4,
            m_lower=(-2, 18, 2),
            m_upper=(5, 19, 4),
            q_lower=(8, 18, 2, "integer"),
            q_upper=(14, 19, 4, "integer"),
        ),
        _terminal(
            lower=25,
            upper=33,
            proxy_m=second["proxy_incoming_mertens"],
            proxy_q=second["proxy_incoming_squarefree"],
            delta_m=-2,
            delta_q=3,
            m_lower=(4, 26, 2),
            m_upper=(6, 27, 4),
            q_lower=(13, 26, 2, "integer"),
            q_upper=(17, 27, 4, "integer"),
        ),
    )
    return [
        {
            "cluster_plan_sha256": plan_sha,
            "kind": WORKER_STATUS_KIND,
            "leaf_count": 1,
            "schema_version": SCHEMA_VERSION,
            "stream": {
                "path": f"workers/worker-{index:02d}.jsonl",
                "sha256": str(index + 3) * 64,
                "size_bytes": 123 + index,
            },
            "terminal": terminals[index],
            "worker_anchor_sha256": worker_anchor(
                plan_sha, plan["worker_assignments"][index]
            ),
            "worker_index": index,
        }
        for index in range(2)
    ]


class HurstH100AffineClusterTests(unittest.TestCase):
    @staticmethod
    def _make_writable(root: Path) -> None:
        if not root.exists():
            return
        root.chmod(0o700)
        for path in root.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)

    def test_production_partition_is_exact_balanced_and_aligned(self) -> None:
        shards = partition_affine_range(
            lower=10**12 + 1,
            upper_exclusive=10**16 + 1,
            worker_count=8,
            super_shard_rows=10**9,
        )
        self.assertEqual(len(shards), 8)
        self.assertEqual(
            {shard["count"] for shard in shards},
            {1_249_875_000_000_000},
        )
        self.assertEqual(shards[0]["lower"], 10**12 + 1)
        self.assertEqual(shards[-1]["upper_exclusive"], 10**16 + 1)
        self.assertTrue(
            all(
                left["upper_exclusive"] == right["lower"]
                for left, right in zip(shards, shards[1:])
            )
        )
        self.assertEqual(
            sum(shard["count"] for shard in shards),
            10**16 - 10**12,
        )

    def test_exact_scan_uses_real_prefix_not_proxy_states(self) -> None:
        plan = _minimal_cluster_plan()
        scan = compose_worker_terminals(
            cluster_plan=plan,
            cpu_state=CPU_STATE,
            worker_statuses=list(reversed(_statuses(plan))),
        )
        self.assertEqual(scan["kind"], SCAN_KIND)
        self.assertEqual(scan["final_state"], [3, 17, -5, 7])
        self.assertTrue(scan["all_derived_inputs_in_local_guards"])
        self.assertFalse(scan["proxy_inputs_used_as_sequential_states"])
        self.assertEqual(
            [entry["derived_incoming"] for entry in scan["entries"]],
            [[2, 10], [5, 14]],
        )
        self.assertEqual(
            scan["global_root_guard"]["hurst_lower"]["value"], 1
        )
        self.assertEqual(
            scan["global_root_guard"]["hurst_upper"]["value"], 3
        )
        self.assertEqual(
            scan["global_root_guard"]["squarefree_lower"]["value"], 9
        )
        self.assertEqual(
            scan["global_root_guard"]["squarefree_upper"]["value"], 13
        )

    def test_scan_rejects_a_real_prefix_outside_local_guard(self) -> None:
        plan = _minimal_cluster_plan()
        statuses = _statuses(plan)
        statuses[1]["terminal"]["global_hurst_lower"]["value"] = 6
        with self.assertRaisesRegex(
            HurstH100AffineClusterError, "derived Mertens input"
        ):
            compose_worker_terminals(
                cluster_plan=plan,
                cpu_state=CPU_STATE,
                worker_statuses=statuses,
            )

    def test_worker_anchor_binds_assignment_and_plan(self) -> None:
        plan = _minimal_cluster_plan()
        assignment = plan["worker_assignments"][0]
        first = worker_anchor("a" * 64, assignment)
        changed = dict(assignment)
        changed["lower"] += 1
        self.assertNotEqual(first, worker_anchor("a" * 64, changed))
        self.assertNotEqual(first, worker_anchor("b" * 64, assignment))

    def test_worker_command_isolates_routing_from_attestation(self) -> None:
        plan = _minimal_cluster_plan()
        assignment = plan["worker_assignments"][1]
        command = worker_command(
            runner=Path("/runner"),
            roster=Path("/roster"),
            assignment=assignment,
            cluster_plan_sha256="a" * 64,
            leaf_rows=8,
            super_shard_rows=8,
            required_device_class="nvidia-h100-sm90",
        )
        self.assertEqual(command[:2], (
            "/usr/bin/env", "CUDA_VISIBLE_DEVICES=1"
        ))
        self.assertEqual(command[command.index("--device") + 1], "0")
        self.assertEqual(
            command[command.index("--require-device-class") + 1],
            "nvidia-h100-sm90",
        )
        self.assertNotIn("--allow-other-device", command)

    def test_build_plan_requires_eight_workers_in_production(self) -> None:
        hybrid = {
            "h100": {
                "leaf_rows": 100_000_000,
                "required_device_class": "nvidia-h100-sm90",
                "super_shard_rows": 1_000_000_000,
            },
            "mode": "production",
            "source_geometry": {
                "h100": {
                    "count": 10**16 - 10**12,
                    "lower": 10**12 + 1,
                    "upper_exclusive": 10**16 + 1,
                }
            },
        }
        handoff = {
            "kind": CPU_HANDOFF_KIND,
            "plan_sha256": NONZERO,
            "receipt_chain_sha256": "2" * 64,
        }
        with self.assertRaisesRegex(
            HurstH100AffineClusterError, "exactly eight"
        ):
            build_cluster_plan(
                hybrid_plan=hybrid,
                hybrid_plan_sha256=NONZERO,
                cpu_handoff=handoff,
                worker_count=7,
            )
        plan = build_cluster_plan(
            hybrid_plan=hybrid,
            hybrid_plan_sha256=NONZERO,
            cpu_handoff=handoff,
        )
        self.assertEqual(plan["worker_count"], 8)
        self.assertEqual(
            plan["routing_mode"], "distributed_one_h100_per_node"
        )
        self.assertEqual(
            plan["worker_topology"],
            "eight_azure_ncc40ads_h100_v5_nodes",
        )
        self.assertEqual(
            {
                assignment["cuda_visible_devices_selector"]
                for assignment in plan["worker_assignments"]
            },
            {"0"},
        )
        self.assertFalse(
            plan["device_policy"]["attestation_present"]
        )
        self.assertTrue(
            plan["device_policy"]["selectors_are_process_routing_only"]
        )
        self.assertTrue(
            all(
                assignment["proxy_state_is_sequential_state"] is False
                for assignment in plan["worker_assignments"]
            )
        )

    def test_proxy_is_deterministic_and_elementary(self) -> None:
        for lower in (17, 10**12 + 1, 10**16):
            proxy = proxy_squarefree_state(lower)
            self.assertEqual(proxy, proxy_squarefree_state(lower))
            self.assertGreaterEqual(proxy, 0)
            self.assertLessEqual(proxy, lower - 1)

    def test_local_launcher_rejects_production_topology(self) -> None:
        production = {
            "mode": "production",
            "source_geometry": {
                "cpu": {"count": 10**12},
                "h100": {"count": 10**16 - 10**12},
            },
        }
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            cluster_module,
            "_load_plan",
            return_value=(production, NONZERO),
        ):
            with self.assertRaisesRegex(
                HurstH100AffineClusterError, "one H100 per node"
            ):
                cluster_module.run(
                    materialization_directory=Path(temporary),
                    output_directory=Path(temporary) / "must-not-run",
                )

    @unittest.skipUnless(hasattr(os, "fork"), "requires Linux fork")
    def test_process_orchestrator_runs_disjoint_workers(self) -> None:
        plan = _minimal_cluster_plan()
        plan_sha = hashlib.sha256(canonical_json_bytes(plan)).hexdigest()

        def fake_run_h100(
            argv,
            *,
            output,
            stderr_path,
            gpu_range,
            leaf_rows,
            super_rows,
            initial_digest,
            initial_state,
            runner_sha256,
            roster_sha256,
            prime_roster,
            timeout_seconds,
            pass_fds=(),
        ):
            del (
                leaf_rows,
                super_rows,
                runner_sha256,
                roster_sha256,
                prime_roster,
                timeout_seconds,
                pass_fds,
            )
            self.assertEqual(argv[0], "/usr/bin/env")
            self.assertTrue(argv[1].startswith("CUDA_VISIBLE_DEVICES="))
            index = 0 if gpu_range["lower"] == 17 else 1
            assignment = plan["worker_assignments"][index]
            self.assertEqual(
                initial_digest, worker_anchor(plan_sha, assignment)
            )
            output.write(
                canonical_json_bytes(
                    {"index": index, "proxy": list(initial_state[:2])}
                )
                + b"\n"
            )
            stderr_path.write_bytes(b"")
            terminal = _statuses(plan)[index]["terminal"]
            return terminal, 1

        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            runner_fd = os.open("/dev/null", os.O_RDONLY)
            roster_fd = os.open("/dev/null", os.O_RDONLY)
            try:
                with mock.patch.object(
                    cluster_module, "_run_h100", side_effect=fake_run_h100
                ):
                    statuses = cluster_module._run_workers(
                        stage=stage,
                        cluster_plan=plan,
                        cluster_plan_sha256=plan_sha,
                        h100_runner=Path(f"/proc/self/fd/{runner_fd}"),
                        roster=Path(f"/proc/self/fd/{roster_fd}"),
                        h100_runner_fd=runner_fd,
                        roster_fd=roster_fd,
                        runner_sha256="a" * 64,
                        roster_sha256="b" * 64,
                        prime_roster=(2, 3, 5),
                        timeout_seconds=10,
                    )
            finally:
                os.close(runner_fd)
                os.close(roster_fd)
            self.assertEqual(len(statuses), 2)
            self.assertEqual(
                [status["worker_index"] for status in statuses], [0, 1]
            )
            self.assertNotEqual(
                statuses[0]["stream"]["sha256"],
                statuses[1]["stream"]["sha256"],
            )
            for index in range(2):
                self.assertTrue(
                    (
                        stage
                        / f"workers/worker-{index:02d}-status.json"
                    ).is_file()
                )

    @unittest.skipUnless(hasattr(os, "fork"), "requires Linux fork")
    def test_end_to_end_run_full_replay_and_immutable_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpu_runner = root / "cpu.py"
            h100_runner = root / "h100.py"
            roster = root / "roster.bin"
            cpu_runner.write_text(_cpu_runner_source(), encoding="utf-8")
            h100_runner.write_text(_h100_runner_source(), encoding="utf-8")
            cpu_runner.chmod(
                stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            )
            h100_runner.chmod(
                stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            )
            roster.write_bytes(b"bounded cluster roster\n")
            materialization = root / "materialization"
            output = root / "output"
            try:
                materialize(
                    cpu_runner=cpu_runner,
                    h100_runner=h100_runner,
                    prime_roster=roster,
                    output_directory=materialization,
                    cpu_segment_rows=13_860,
                    h100_leaf_rows=16,
                    h100_super_shard_rows=16,
                    split=17,
                    upper_exclusive=49,
                    allow_bounded_test=True,
                )
                result = cluster_module.run(
                    materialization_directory=materialization,
                    output_directory=output,
                    worker_count=2,
                    device_selectors=("0", "1"),
                    cpu_timeout_seconds=10,
                    h100_timeout_seconds=10,
                )
                self.assertEqual(result["final_state"], [3, 17, -5, 7])
                self.assertFalse(result["accepted"])
                self.assertFalse(
                    result["proxy_inputs_used_as_sequential_states"]
                )
                checked = cluster_module.verify(
                    materialization_directory=materialization,
                    output_directory=output,
                )
                self.assertTrue(checked["accepted"])
                self.assertTrue(checked["stream_replay_performed"])
                self.assertEqual(checked["final_state"], [3, 17, -5, 7])
                for tree in (materialization, output):
                    self.assertEqual(tree.stat().st_mode & 0o222, 0)
                    self.assertTrue(
                        all(
                            path.stat().st_mode & 0o222 == 0
                            for path in tree.rglob("*")
                        )
                    )

                self._make_writable(output)
                stream = output / "workers/worker-01.jsonl"
                stream.write_bytes(stream.read_bytes() + b"{}\n")
                with self.assertRaisesRegex(
                    HurstH100AffineClusterError,
                    "stream pin changed|record order",
                ):
                    cluster_module.verify(
                        materialization_directory=materialization,
                        output_directory=output,
                    )
            finally:
                self._make_writable(materialization)
                self._make_writable(output)

    @unittest.skipUnless(hasattr(os, "fork"), "requires Linux fork")
    def test_distributed_one_h100_nodes_and_offline_reducer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpu_runner = root / "distributed-cpu.py"
            h100_runner = root / "distributed-h100.py"
            roster = root / "distributed-roster.bin"
            cpu_runner.write_text(_cpu_runner_source(), encoding="utf-8")
            h100_runner.write_text(_h100_runner_source(), encoding="utf-8")
            cpu_runner.chmod(0o700)
            h100_runner.chmod(0o700)
            roster.write_bytes(b"bounded distributed roster\n")
            materialization = root / "materialization"
            prepared = root / "prepared"
            worker_directories = [
                root / "worker-00",
                root / "worker-01",
            ]
            reduced = root / "reduced"
            try:
                materialize(
                    cpu_runner=cpu_runner,
                    h100_runner=h100_runner,
                    prime_roster=roster,
                    output_directory=materialization,
                    cpu_segment_rows=13_860,
                    h100_leaf_rows=16,
                    h100_super_shard_rows=16,
                    split=17,
                    upper_exclusive=49,
                    allow_bounded_test=True,
                )
                cluster_module.prepare_distributed(
                    materialization_directory=materialization,
                    output_directory=prepared,
                    worker_count=2,
                    cpu_timeout_seconds=10,
                )
                plan = json.loads(
                    (
                        prepared / "h100-affine-cluster-plan.json"
                    ).read_bytes()
                )
                self.assertEqual(
                    plan["routing_mode"],
                    "distributed_one_h100_per_node",
                )
                self.assertEqual(
                    [
                        row["cuda_visible_devices_selector"]
                        for row in plan["worker_assignments"]
                    ],
                    ["0", "0"],
                )
                commands = json.loads(
                    (prepared / "worker-commands.json").read_bytes()
                )
                self.assertEqual(
                    [row["h100_count"] for row in commands["workers"]],
                    [1, 1],
                )
                worker_results = [
                    cluster_module.run_distributed_worker(
                        materialization_directory=materialization,
                        prepared_directory=prepared,
                        worker_index=index,
                        output_directory=worker_directories[index],
                        h100_timeout_seconds=10,
                    )
                    for index in range(2)
                ]
                self.assertTrue(
                    worker_results[0]["proxy_guard_accepted_diagnostic"]
                )
                self.assertFalse(
                    worker_results[1]["proxy_guard_accepted_diagnostic"]
                )
                self.assertTrue(
                    all(
                        result["proxy_guard_acceptance_required"] is False
                        for result in worker_results
                    )
                )
                result = cluster_module.reduce_distributed(
                    materialization_directory=materialization,
                    prepared_directory=prepared,
                    worker_directories=tuple(reversed(worker_directories)),
                    output_directory=reduced,
                )
                self.assertEqual(result["final_state"], [3, 17, -5, 7])
                self.assertEqual(
                    result["routing_mode"],
                    "distributed_one_h100_per_node",
                )
                self.assertFalse(
                    result["proxy_guard_acceptance_required"]
                )
                scan = json.loads(
                    (reduced / "h100-affine-scan.json").read_bytes()
                )
                self.assertEqual(
                    [row["derived_incoming"] for row in scan["entries"]],
                    [[2, 10], [5, 14]],
                )

                self._make_writable(worker_directories[1])
                bundle_path = worker_directories[1] / "bundle.json"
                bundle = json.loads(bundle_path.read_bytes())
                bundle["status_sha256"] = "0" * 64
                bundle_path.write_bytes(canonical_json_bytes(bundle))
                with self.assertRaisesRegex(
                    HurstH100AffineClusterError,
                    "bundle does not replay",
                ):
                    cluster_module.reduce_distributed(
                        materialization_directory=materialization,
                        prepared_directory=prepared,
                        worker_directories=worker_directories,
                        output_directory=root / "tampered-reduced",
                    )

                self._make_writable(prepared)
                summary_stderr = prepared / "cpu-summary.stderr"
                summary_stderr.write_bytes(
                    summary_stderr.read_bytes() + b"tampered\n"
                )
                with self.assertRaisesRegex(
                    HurstH100AffineClusterError,
                    "preparation summary does not replay",
                ):
                    cluster_module.run_distributed_worker(
                        materialization_directory=materialization,
                        prepared_directory=prepared,
                        worker_index=0,
                        output_directory=root / "tampered-worker",
                        h100_timeout_seconds=10,
                    )
            finally:
                for directory in (
                    materialization,
                    prepared,
                    *worker_directories,
                    reduced,
                ):
                    self._make_writable(directory)


if __name__ == "__main__":
    unittest.main()
