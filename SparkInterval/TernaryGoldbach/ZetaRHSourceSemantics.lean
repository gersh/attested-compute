/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.StreamingChunkVerifier

/-!
# Exact Platt--Trudgian finite-RH source semantics

The source atom is the positive-height, open-critical-strip assertion that all
zeta zeros through the exact height `3000175332800` lie on the critical line.
The generic zeta verifier already proves the stronger closed-rectangle result
from chunked ordered brackets, a Hardy-Z bridge, and a matching global count.
This module records the exact source proposition and proves the elementary
range specialization.

`SourceEvidence` contains no final RH conclusion.  Its `checked` field is the
reusable chunked verifier contract, so the expensive campaign must still
provide endpoint-enclosure realization and a Turing/argument-principle count.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

open SparkInterval.Zeta

/-- The exact endpoint verified by Platt--Trudgian. -/
def sourceHeight : ℝ := 3_000_175_332_800

/-- Exact source-shaped positive-height finite RH statement. -/
def SourceClaim : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 →
    0 < s.re → s.re < 1 →
    0 < s.im → s.im ≤ sourceHeight →
    s.re = (1 : ℝ) / 2

/-- Chunked checker evidence at the exact source endpoint. -/
structure SourceEvidence where
  f : ℝ → ℝ
  chunkCount : Nat
  checked : ChunkedZetaVerifierEvidence f sourceHeight chunkCount

/-- The stronger symmetric closed-rectangle verifier result implies the
paper's positive-height open-strip statement. -/
theorem sourceClaim_of_evidence (evidence : SourceEvidence) : SourceClaim := by
  intro s hzero hre0 hre1 him0 himUpper
  apply evidence.checked.all_zeros_on_criticalLine s
  · rw [mem_criticalRectangle]
    have hheight : (0 : ℝ) ≤ sourceHeight := by norm_num [sourceHeight]
    exact ⟨hre0.le, hre1.le, by linarith, himUpper⟩
  · exact hzero

end SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

end
