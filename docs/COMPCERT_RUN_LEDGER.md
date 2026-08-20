> **⚠ SUPERSEDED — read [`ATTESTED_COMPCERT_RUNS.md`](ATTESTED_COMPCERT_RUNS.md) instead.**
>
> This was the design note written *before* the mechanism was built, and parts
> of it were wrong in ways the build corrected: the emitted-C binding is not
> unachievable (it is a 45 s kernel proof), the pin is looked up rather than
> supplied, and the trust surface came out at one axiom rather than the shape
> sketched here.  It is kept because it records why the design went the way it
> did, and what was believed at each turn.
>
> It predates the `gpu_prover` → `sparkinterval` rename, and quotes lakefile
> comments verbatim from that period.  Those mentions are left as written
> because they are quotations.

# Supplying CompCert run admissions from signed attestations

## The problem

`claude_math` has ~90 run admissions of the shape

```lean
axiom ceUHarmonic_compcert_run : computation.Returns ((1 : Nat) : Int)
```

Each is a bare axiom: an empirical claim that a binary ran and reported a
value. The Lean chain above each one is *proved* — for `ceu_harmonic_1048576`,
`harmProgram_denote` + `sourceAccepts_of_denote` + `sourceSum_eq_ceUHarmAux`
carry `Returns 1` all the way to `ceUHarmAux 1048576 0 ≤ 254033977410453` — so
the run admission is the single unproved link in an otherwise complete
argument. Attesting the run should discharge it.

Three things stand in the way, and this document is the design for all three.

### 1. The registry is closed, so every run costs a rebuild

`SparkInterval/Execution/RegisteredAlgorithm.lean` is 2,388 lines defining an
inductive with **16 constructors**, plus `canonicalDefinition`, `algorithmHash`,
`canonicalParameters` and `Runs` as matches over it. Registering a campaign
means adding a constructor and a case to each match — so it recompiles that
file, every `Registered*Certificate.lean` beside it, and every `claude_math`
bridge downstream. At ninety runs that is untenable.

**Fix: one constructor, parameterised by data.** A single
`| compcertRunV1 (spec : CompCertRunSpec)` is added once. Thereafter a new run
is a new *value* of `CompCertRunSpec`, not a new constructor, and nothing in
this directory recompiles.

### 2. Nothing connects a signed statement to `Computation.Returns`

SparkInterval's `Runs : RegisteredAlgorithm → String → String → Prop` speaks about
strings, and SparkInterval has no LeanCompCert dependency (deliberately — the two
repositories share a Lean/Mathlib package graph but not a compiler model). So
the producer cannot state `Computation.Returns`.

**Fix: state the neutral fact here, bridge it there.** `Runs` for a CompCert
run says only *which artifact* ran and *what it reported*, both as canonical
strings. `claude_math` — which imports both packages — turns that into
`Computation.Returns`.

### 3. What ran must line up with what was proved

This is the substantive one. A signature over "the artifact returned 1" is
worthless unless *that artifact* is the compilation of *the program the theorem
is about*. The chain has to be:

```
  Lean program p
      │  emit                       (a Lean function: p ↦ C text)
      ▼
  C text ──sha256──▶ d
      │  ccomp                      (CompCert's proved C → asm)
      ▼
  artifact ──runs in TDX──▶ value v
      │  signed receipt binds (d, v)
      ▼
  Lean: the artifact with C-digest d reported v
```

Every arrow but the third is either a Lean function or a proved theorem. The
binding that makes it a chain rather than four unrelated facts is **`d`**, and
`d` must be computed from `p` on the Lean side, not asserted.

`algorithmHashDiagnosticCheck` is the existing precedent for exactly this move:

```lean
def algorithmHashDiagnosticCheck (algorithm : RegisteredAlgorithm) : Bool :=
  SHA256.digestString algorithm.canonicalDefinition == algorithm.algorithmHash
```

It kernel-computes a SHA-256 of a Lean-side string and compares it to the
digest the receipt signs over. For the sixteen existing constructors
`algorithmHash` is a *reviewed literal*, so that check is a real constraint —
it catches a stale or mistyped digest.

⚠ **For a parameterised constructor the same shape would be vacuous.** If
`algorithmHash (.compcertRunV1 spec)` is *defined* as
`SHA256.digestString (canonicalDefinition (.compcertRunV1 spec))`, then
`algorithmHashDiagnosticCheck` reduces to `rfl` and constrains nothing. It
would be a check parameterised by the thing it is supposed to constrain.

So the non-vacuous binding for a CompCert run is a *different* equation, and it
cannot live in this repository, because only `claude_math` knows `emit`:

```lean
-- in claude_math, where both packages are in scope
SHA256.digestString (emittedC p) = spec.emittedCDigest
```

That is decidable. **It is not affordable, and an earlier draft of this
document said it was — on a misremembered cost.** The measurements in this
repository are:

| kernel evaluation | cost | source |
| --- | --- | --- |
| `digestString` of a 505-byte String | 16.4 s / 10.0 GB | `proof_build/leancompcert_tdx/seg_campaign_pin_kernel_check.lean:11` |
| `digestString` of a 1,024-byte String | 92.3 s / 22.0 GB | `docs/COMPCERT_ARTIFACT_UNDER_TDX.md:250` |
| `digestString` of a 2,048-byte String | **did not complete in 2,885 s at 46.9 GB** | `docs/COMPCERT_ARTIFACT_UNDER_TDX.md:250` |
| `String.toUTF8` alone, 1,024 bytes | 21.2 s / 3.93 GB | `docs/COMPCERT_ARTIFACT_UNDER_TDX.md:274` |
| one `P256.verifyDigestHex` | 3.9 s / +1.1 GB | `SparkInterval/Certificate/P256.lean:90` |

The smallest artifact in the population, `ceu_harmonic_1048576.c`, is **1,116
bytes** — already past the 1 KB point and near the 2 KB cliff. `psi_seg.c` is
**84,444 bytes**, which is not close. So hashing the emitted C in the kernel is
*true and unachievable*: the equation typechecks, is the right equation, and
cannot be reduced at the sizes that actually occur.

Note what the table says about *where* the cost is. ECDSA is 3.9 s. The
expense is `digestString = digestByteArray text.toUTF8`, because unfolding a
String literal to `List Char` with per-`Char` validity proofs costs on the
order of megabytes of kernel term per input byte. The crypto is cheap; the
`String` is not.

**The affordable shape is `PackedBytes`.** `SHA256Packed` represents bytes as a
single `Nat` with `Nat.shiftRight`/`Nat.land` field extraction — two GMP
operations, no `List Char` — and `SparkInterval/Tests/PhalaTdxSegEvidenceTest.lean:246`
proves a **5,010-byte** digest by `rfl` inside the ordinary `-M8192` library
build, using ten explicit chunk lemmas. That is the regime this binding must
be moved into if it is ever to be proved. Doing so means carrying the emitted
C as packed bytes rather than as a `String`, which is a change to the emitter,
not to this module.

Until then the binding is a **reviewed literal**, recomputed outside the kernel
by re-emitting and comparing digests — reproducibly, since all four x86_64
artifacts now rebuild bit-for-bit. That is exactly the trust position the
sixteen existing constructors already occupy (`algorithmHash` is a reviewed
literal there too, and its docstring says so: *"that preimage binding is part
of the disclosed certificate/import trust boundary rather than a
multi-gigabyte theorem proof"*). It is no worse than the status quo — but it
must be recorded as a reviewed literal, not presented as proved.

## The shape

```lean
structure CompCertRunSpec where
  programName    : String   -- human-facing; also inside canonicalDefinition
  emittedCDigest : Digest   -- SHA-256 of the exact C text handed to ccomp
  toolchain      : String   -- "ccomp 3.17 -O -fstruct-passing", x86_64-linux
  acceptedValue  : Nat      -- the value the artifact must report
```

```lean
| .compcertRunV1 spec, input, output =>
    input  = spec.emittedCDigest ∧
    output = canonicalNatString spec.acceptedValue
```

`canonicalDefinition` is generated from the spec, so it names the artifact and
the toolchain and nothing else; `algorithmHash` is its SHA-256, computed.

## Why this does not recompile much

| change | rebuild |
| --- | --- |
| add the constructor (once) | `RegisteredAlgorithm.lean` + dependents |
| add a run (a new `CompCertRunSpec` value) | **one new leaf module** |
| attest a run that was previously axiomatic | that run's leaf module only |
| change the capstone's mathematics | the capstone, not the runs |

The capstone stays conditional, in the shape
`Math/Problems/TernaryGoldbach/AzureConditional10Pow27.lean` already uses:

```lean
theorem ternary_goldbach_of_allRegistered10Pow27Checks_and_rs62Theorem15
    {a7Certificate psiCertificate … : SignedResultCertificate}
    (hA7 : a7Certificate.ch25A7BoundaryProductionCheck = true)
    …
    : ∀ n : ℕ, Odd n → 7 ≤ n → IsThreePrimeSum n
```

Hypotheses, not axioms. The theorem is proved once and never recompiles as
runs are supplied; each run is discharged in its own leaf, and a leaf that has
not been attested yet supplies its hypothesis from the bare axiom exactly as
today. **The interface does not change when a run moves from axiom to
receipt** — that is what keeps the rebuild local.

## Checking a receipt in four pieces

`SparkInterval/Execution/PhalaTdxOutcomeSplit.lean` adds the acceptance
counterpart to the six existing refusal lemmas:

```lean
theorem phalaTdxOutcomeCheck_of_parts
    (hPin : phalaTdxPinCheck enclave receipt = true)
    (hInvocation : phalaTdxInvocationCheck invocation receipt = true)
    (hQuote : phalaTdxQuoteCheck enclave receipt = true)
    (hSignature : phalaTdxSignatureCheck enclave receipt = true) :
    phalaTdxOutcomeCheck enclave invocation receipt = true
```

plus its converse, so nothing is lost by working part-wise. This is what lets a
receipt be checked across four module compilations instead of one: the four
kernel peaks no longer have to coexist in a single process. It does not make
any individual digest cheaper — the `String` cost is unchanged — but it is the
difference between one 44 GB reduction that did not finish and four budgets
that each fit.

## ⚠ A stale pin, worth fixing while here

`claude_math/lakefile.toml:129` retargets the `SparkInterval` dependency away
from `../gpu_prover` to a worktree on `agent/lean-bridge-integration`, with a
comment explaining that `main` "carries neither the generic registered-campaign
certificate layer ... nor the Ramaré production-fold campaign".

**That is no longer true.** `agent/lean-bridge-integration` is an ancestor of
`main` (`git merge-base --is-ancestor` confirms it), so `main` now carries both
— *and* the Phala TDX attestation modules, which the branch does not. Anything
that needs receipts and the campaign layer together can only be built on
`main`. The comment already anticipates this: *"When
`agent/lean-bridge-integration` is merged to gpu_prover `main`, revert this to
`path = "../gpu_prover"` — nothing else in this repository has to change."*

## What the enclave must sign

The receipt format already exists (`tg_verifier/phala_tdx_receipt.py`, pure
stdlib, 328 lines including its own P-256 — so it can be embedded in a compose
and run with no network). Its `SIGNED_FIELDS` already carry `algorithm_id`,
`algorithm_hash`, `input_hash`, `result` and `output_hash`, which is precisely
the tuple above. For a CompCert run:

* `algorithm_hash` = SHA-256 of the generated `canonicalDefinition`,
* `input_hash` = SHA-256 of `spec.emittedCDigest`,
* `result` / `output_hash` = the value the artifact reported.

The 2026-08-18 x86_64 runs in `claude_math/audits/compcert/rh_phala/` fetch a
TDX quote whose `report_data` commits to a statement, but derive **no key and
sign nothing**. Adding `GetKey` + `sign_receipt` to that entry point is what
turns those runs into receipts this layer can consume.

## ⚠ Corrections after mapping the consumer

Three things found after this design was first written. They narrow it.

**1. The conditional mechanism already exists upstream, and is unused.**
`leancompcert/LeanCompCert/Attest/Admission.lean` defines
`opaque MachineExecuted` (the same stance as `PhalaTdxAttestedEmission`) and

```lean
structure RunAdmission (crypto : ReceiptCrypto) (artifact : Artifact)
    (receipt : RunReceipt) : Prop where
  executed : MachineExecuted crypto artifact receipt
  reported : artifact.body.modelResult = some receipt.value
```

with `receiptBinds` as the checked receipt and `modelResult_of_receipt` /
the `Returns` join as the composition. That *is* "supply the runs as
hypotheses to a conditional theorem", already built, already at the
`Computation` level the consumer needs — and `claude_math` imports none of
`LeanCompCert.Attest`.

So `CompCertRunLedger` here must not be a rival ledger. Its job is narrower
and is the piece that genuinely does not exist: gpu_prover attests *signed
statements about strings*, leancompcert admits *runs of artifacts*, and
nothing joins them. `CertifiedCompCertRun` is the producer-side half of that
join; the join itself belongs in `claude_math`, the only place that imports
both packages. **Do not add a third notion of "a run happened."**

**2. The population is far more heterogeneous than a single `acceptedValue`.**
Of the 90 capstone run atoms: 43 are `AComputation.Returns`, 32
`Computation.Returns`, 2 `ObservesReg`, 6 `SegmentReceipt`, 3 raw
`evalMCCSequence` equalities, 2 observation-record equalities, 2 other receipt
structures. **12 are parameterized axioms** (`∀ row ∈ rows`), not closed
propositions. A `CompCertRunSpec` with one `acceptedValue : Nat` therefore
addresses the 75 `Returns`-shaped atoms and *not* the other 15. Any bundle
must tolerate quantified members.

**3. 42 of the 90 are not in `claude_math` at all** — they are in
`../leancompcert/LeanCompCert/Ports/*`, reached through a path dependency with
no commit pin. A bundle spans three repositories.

For scale: changing one run-axiom file today recompiles a median of 789 and up
to 1,218 modules of the default build; the union over all 46 such files is
1,388 (~13%).

## What is still not proved, after all of this

That the artifact computes the mathematical object its atom names. That is
`evaluates_atom_predicate`, proved in Lean and CompCert per atom, and it is
`false` for both RH pilots. A receipt says a binary ran and reported a number.
