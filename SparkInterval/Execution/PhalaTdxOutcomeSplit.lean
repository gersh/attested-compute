/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxAttestation

/-!
# Checking a TDX receipt in four pieces instead of one

`phalaTdxOutcomeCheck` is a conjunction of four independent checks:

```lean
phalaTdxPinCheck enclave receipt &&
  phalaTdxInvocationCheck invocation receipt &&
    phalaTdxQuoteCheck enclave receipt &&
      phalaTdxSignatureCheck enclave receipt
```

Six theorems prove it `false` from a single bad part, so the *refusal*
direction is already decomposed. The **acceptance** direction was not: there
was no lemma assembling the whole check from four separately established
parts, so anyone wanting a kernel proof of acceptance had to reduce all four
at once, in one module, in one memory budget.

That is why the measurement in `proof_build/leancompcert_tdx/live_campaign_kernel_check.lean`
records the live-campaign composite still reducing after 62 minutes at 44 GB
without finishing, while `proof_build/ch25_a7_phala_tdx/prod5_kernel_full_check.lean`
records the earlier, quote-free prod5 composite completing at 1,209 s / 42.9 GB.
Both are near the ceiling because both are one term.

`phalaTdxOutcomeCheck_of_parts` is the missing one-liner. With it each part can
be discharged in **its own module compilation**, under its own `-M` budget, by
whichever method suits that part:

| part | what dominates | affordable method |
| --- | --- | --- |
| `phalaTdxSignatureCheck` | one ECDSA-P256 verify | `decide +kernel`, ~3.9 s / +1.1 GB |
| `phalaTdxQuoteCheck` | SHA-256 of 5,010 quote bytes | `rfl` over `PackedBytes` with chunk lemmas, as `Tests/PhalaTdxSegEvidenceTest.lean:246` already does |
| `phalaTdxPinCheck` | four short `digestString`s | `decide +kernel` |
| `phalaTdxInvocationCheck` | five `digestString`s, one over the result | `decide +kernel` |

The costly ones are the `String` digests, not the cryptography: `digestString`
is `digestByteArray text.toUTF8`, and unfolding a String literal to `List Char`
with per-`Char` validity proofs runs to megabytes of kernel term per input
byte (1,024 bytes = 92.3 s / 22.0 GB; 2,048 bytes did not complete in 2,885 s
at 46.9 GB — `docs/COMPCERT_ARTIFACT_UNDER_TDX.md:250`). Splitting does not
make any single digest cheaper. What it buys is that the four peaks no longer
have to coexist in one process, which is the difference between 44 GB and four
budgets that each fit.

This module adds no axiom and no `native_decide`; it is one `simp` over the
definition.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Assemble `phalaTdxOutcomeCheck` from its four parts.

The counterpart to the six `…_eq_false_of_…` refusal lemmas: those take one bad
part to a rejected whole, this takes four good parts to an accepted whole. Its
purpose is entirely operational — it lets each part be proved in a separate
module rather than forcing one kernel reduction to hold all four at once. -/
theorem phalaTdxOutcomeCheck_of_parts
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (hPin : phalaTdxPinCheck enclave receipt = true)
    (hInvocation : phalaTdxInvocationCheck invocation receipt = true)
    (hQuote : phalaTdxQuoteCheck enclave receipt = true)
    (hSignature : phalaTdxSignatureCheck enclave receipt = true) :
    phalaTdxOutcomeCheck enclave invocation receipt = true := by
  simp [phalaTdxOutcomeCheck, hPin, hInvocation, hQuote, hSignature]

/-- The converse, so the split is an equivalence and no strength is lost by
working part-wise: an accepted whole gives all four parts back. -/
theorem phalaTdxOutcomeCheck_parts_of
    {enclave : PhalaTdxEnclave} {invocation : RegisteredInvocation}
    {receipt : PhalaTdxReceipt}
    (h : phalaTdxOutcomeCheck enclave invocation receipt = true) :
    phalaTdxPinCheck enclave receipt = true ∧
      phalaTdxInvocationCheck invocation receipt = true ∧
        phalaTdxQuoteCheck enclave receipt = true ∧
          phalaTdxSignatureCheck enclave receipt = true := by
  simpa [phalaTdxOutcomeCheck, Bool.and_eq_true, and_assoc] using h

end SparkInterval.Execution
