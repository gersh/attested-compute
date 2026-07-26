# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import unittest

from tg_verifier.dirichlet_deferred_q_scaling_audit import (
    _canonical_json,
    audit_deferred_q_scaling,
)


class DirichletDeferredQScalingAuditTest(unittest.TestCase):
    def test_exact_counterexample_rejects_naive_single_dft_deferral(
        self,
    ) -> None:
        report = audit_deferred_q_scaling()
        self.assertEqual(
            report["counterexample"]["current_composer_value"],
            {"numerator": 305, "denominator": 101},
        )
        self.assertEqual(
            report["counterexample"]["naively_deferred_value"],
            {"numerator": 5, "denominator": 101},
        )
        self.assertEqual(
            report["counterexample"]["nonzero_difference"],
            {"numerator": 300, "denominator": 101},
        )
        self.assertTrue(report["naive_deferred_scaling_rejected"])
        self.assertFalse(report["uniform_common_q_to_minus_s_factor_present"])
        self.assertFalse(report["source_usefulness_established"])
        body = dict(report)
        claimed = body.pop("audit_sha256")
        self.assertEqual(
            claimed, hashlib.sha256(_canonical_json(body)).hexdigest()
        )


if __name__ == "__main__":
    unittest.main()
