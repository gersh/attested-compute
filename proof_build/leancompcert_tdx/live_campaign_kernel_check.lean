/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

# The whole `platt-stronger-range-live` acceptance check, reduced by the kernel

This file is **not** part of any `lean_lib` and is not built by `lake build`.
It is the live campaign's counterpart of
`proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean`, and it exists for
the same reason: `phalaTdxOutcomeCheck` performs nineteen SHA-256 evaluations
over strings, plus the SHA-256 of the retained quote, plus an ECDSA P-256
verification, before it returns, and reducing all of that in the Lean kernel
needs far more memory than this repository's `weakLeanArgs = ["-j1", "-M8192"]`
ceiling allows.

Run it with an explicit memory budget, on a host with the memory actually
free:

```
lake env lean -j1 -M110000 \
  proof_build/leancompcert_tdx/live_campaign_kernel_check.lean
```

`prod5_kernel_full_check.lean` measured 1209 s and 42.9 GB for the equivalent
pair of declarations on a 20-core x86-64 host with 119 GB of RAM, most of it
spent in swap because about 19 GB was tied up elsewhere.  Budget at least that
much *genuinely free* physical memory, not merely a large `-M`.

**Two measured cautions, recorded 2026-07-31.**

First, run the two declarations below in *separate* invocations, one file at a
time.  Lean does not return the kernel's working memory to the allocator
between declarations, so a single file pays for both peaks at once.

Second, and more important: those prod5 numbers were measured **before**
`PhalaTdxReceipt` carried the quote bytes.  `phalaTdxQuoteCheck` now hashes
5,010 bytes of retained quote in the kernel on top of the nineteen string
digests, and that cost has not been measured for either deployment.  On this
host the positive declaration below was still reducing after 62 minutes at a
steady 44 GB resident -- steady, i.e. progressing rather than diverging, but
not finished.  Treat "how long does the quote hash take in the kernel" as an
open measurement, not as a known 20 minutes.  The rest of the check *is*
kernel-verified today, in
`SparkInterval/Tests/PhalaTdxLiveCampaignRunTest.lean`: the ECDSA P-256
verification over the enclave's real signature and three refusals, all
`decide +kernel`, all base trio.

Both declarations below report `[propext, Classical.choice, Quot.sound]`:
no `native_decide`, no `ofReduceBool`, no compiled evaluator.

If this file stops closing, the receipt pinned in
`SparkInterval/Execution/PhalaTdxLiveCampaignEvidence.lean` no longer satisfies
the acceptance check by kernel reduction, and nothing downstream of it should
be believed.
-/

import SparkInterval.Execution.PhalaTdxLiveCampaignEvidence

set_option autoImplicit false
set_option maxRecDepth 200000
set_option maxHeartbeats 10000000

open SparkInterval.Execution

/-- The one-character-altered pinned key, refused by kernel reduction of the
whole check rather than of the P-256 primitive alone.  Stated first because it
is the cheap one: it fails at the quote's report-data commitment, which is a
digest *of the pinned key*, before the statement digest is ever built.

Axioms: the base trio. -/
theorem liveOutcome_rejectsAlteredKey_kernel :
    phalaTdxOutcomeCheck .plattStrongerRangeLiveTamperedKeyV1
      .plattStrongerRangeLiveProductionV1
      PhalaTdxLiveCampaign.receipt = false := by
  decide +kernel

/-- **The complete fail-closed acceptance check, reduced entirely by the Lean
kernel** on the receipt a genuine Intel TDX enclave signed for the per-integer
`Σ μ(m)/m` campaign: no `native_decide`, no compiled evaluator.  This reduces
the canonical eighteen-field payload, its SHA-256, the SHA-256 of the retained
quote, the `mrconfigid` and report-data bindings read out of the quote's
bytes, and the ECDSA P-256 verification.

Axioms: the base trio. -/
theorem liveOutcome_kernel :
    phalaTdxOutcomeCheck .plattStrongerRangeLivePhalaV1
      .plattStrongerRangeLiveProductionV1
      PhalaTdxLiveCampaign.receipt = true := by
  decide +kernel

#print axioms liveOutcome_rejectsAlteredKey_kernel
#print axioms liveOutcome_kernel
