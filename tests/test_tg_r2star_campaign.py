# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import asdict
import unittest

from tg_verifier.r2star import create_r2star_chunk
from tg_verifier.r2star_campaign import (
    R2StarCampaignError,
    verify_runner_receipt,
)


def exact_small_receipt() -> dict[str, object]:
    chunk = create_r2star_chunk(
        lower=1,
        upper=501,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=0,
        incoming_upper=0,
    )
    return {
        "receipt_schema": "sparkinterval.r2star-bounded-chunk.v1",
        "classification": "bounded_exact_python_contract_chunk_not_full_atom_proof",
        "chunk": asdict(chunk),
        "factor_support_encoding": "r2star-distinct-prime-support-u64be-v1",
        "factor_support_digest_producer": "independent_host_segmented_exact_factorization_v1",
        "gpu_capped_factor_support_matches_host": True,
        "directed_rows_sha256_le_v1": "1" * 64,
        "ambiguous_log_rows": 0,
        "exact_rational_fallback_rows": 0,
        "integer_overflow_rows": 0,
        "log_algorithm": "q64_directed_atanh_with_exact_rational_host_fallback_v1",
        "prefix_implementation": "deterministic_blocked_exact_scan_v1",
        "serial_cross_check_performed": False,
        "device_name": "test device",
        "compute_capability": "0.0",
        "cuda_driver_api_version": 0,
        "cuda_runtime_version": 0,
        "kernel_milliseconds": 1,
        "factor_kernel_milliseconds": 1,
        "directed_row_kernel_milliseconds": 1,
        "parallel_transition_kernel_milliseconds": 1,
        "serial_reference_kernel_milliseconds": 0,
        "independent_factor_check_milliseconds": 1,
        "full_source_range": False,
        "python_contract_replay_required": True,
        "hash_chain_is_integrity_not_authentication": True,
        "lean_atom_discharged": False,
        "proves_any_external_atom": False,
    }


class R2StarCampaignTests(unittest.TestCase):
    def test_structural_receipt_accepts_exact_python_chunk(self) -> None:
        report = exact_small_receipt()
        chunk = verify_runner_receipt(report)
        self.assertEqual((chunk.lower, chunk.upper), (1, 501))

    def test_structural_receipt_rejects_changed_transition(self) -> None:
        report = exact_small_receipt()
        report["chunk"]["outgoing_lower"] += 1  # type: ignore[index]
        with self.assertRaisesRegex(R2StarCampaignError, "canonical hash"):
            verify_runner_receipt(report)

    def test_structural_receipt_requires_segmented_factor_digest(self) -> None:
        report = exact_small_receipt()
        report["factor_support_digest_producer"] = "trial_division"
        with self.assertRaisesRegex(R2StarCampaignError, "segmented"):
            verify_runner_receipt(report)


if __name__ == "__main__":
    unittest.main()
