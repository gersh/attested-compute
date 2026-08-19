/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.SignedResultCertificateComposition

/-!
# Attesting CompCert artifact runs, without growing the registry

A consumer of this repository (`claude_math`) carries about ninety run
admissions of the shape

```lean
axiom ceUHarmonic_compcert_run : computation.Returns ((1 : Nat) : Int)
```

Each is an empirical claim — a binary ran and reported a value — sitting under
an otherwise complete proof. This module lets a signed enclave receipt supply
that claim instead.

## Why this is not another `RegisteredAlgorithm` constructor

`RegisteredAlgorithm` is a closed inductive of sixteen constructors in a
2,388-line file, and `canonicalDefinition`, `algorithmHash`,
`canonicalParameters`, `canonicalDomain`, `Runs` and their invocation-level
counterparts are all matches over it. Registering a campaign there means
adding roughly twenty match arms, which recompiles that file, every
`Registered*Certificate.lean` beside it, and every consumer bridge. At ninety
runs that is untenable, and the runs are all the *same kind of thing*, so
sixteen-plus-ninety constructors would be a data table encoded as a type.

`SignedResultCertificate.outcomeCheckForAlgorithm` is already keyed on an
`ExpectedExecutableIdentity` — two plain strings — and is completely
independent of the registry. This module builds on that. **A new attested run
is a new `CompCertRunSpec` value, so nothing here recompiles when one is
added.**

The closed registry keeps its role: it is how a *reviewed, named* campaign
with bespoke semantics is pinned. A CompCert artifact run has no bespoke
semantics — it is always "this artifact reported this number" — so it belongs
in a table, not in a type.

## What a spec pins, and what it does not

`CompCertRunSpec` names the artifact by the SHA-256 of the exact C text handed
to `ccomp`, together with the toolchain and the value the artifact must
report. `canonicalDefinition` is generated from those fields, and the
algorithm hash is its SHA-256, so the signature covers all of them.

⚠ **The algorithm-hash binding is weaker here than in the closed registry, and
deliberately so.** For the sixteen registered constructors `algorithmHash` is a
*reviewed literal* and `algorithmHashDiagnosticCheck` compares it against
`SHA256 canonicalDefinition`, catching a stale digest. Here the hash is
*computed* from the spec, so the same comparison would be `rfl` — a check
parameterised by the thing it is meant to constrain, which is no check at all.
`specWellFormed` therefore carries what can honestly be checked at this level
(the digest is 64 lowercase hex, the names are non-empty), and the real
binding — that `emittedCDigest` is the digest of the C emitted from the Lean
program the theorem is about — is stated and discharged in the consumer, which
is the only place where both the program and the emitter are in scope. See
`docs/COMPCERT_RUN_LEDGER.md`.

## ⚠ This is a connector, not a ledger

`leancompcert/LeanCompCert/Attest/Admission.lean` already defines
`opaque MachineExecuted` and `RunAdmission {executed, reported}`, with
`receiptBinds` as the checked receipt and a join to `Computation.Returns`.
That is the "runs as hypotheses to a conditional theorem" design, already
built at exactly the level the consumer needs — and currently unused
downstream.

Nothing here is meant to replace it. What does not exist anywhere is the join
between the two halves: this package attests *signed statements about
strings*; leancompcert admits *runs of artifacts*. `CertifiedCompCertRun` is
the producer-side end of that join. The join itself belongs in the consumer,
which is the only place importing both packages. **Do not grow this into a
second notion of "a run happened."**

Note also the population it can address: of the ninety capstone run atoms, 75
are `Returns`-shaped and 15 are not (`SegmentReceipt` records, raw
`evalMCCSequence` equalities, observation equalities), and 12 are quantified
over a row list rather than closed. A spec with a single `acceptedValue`
covers the former and not the latter.

## What this module adds to the trust surface

Nothing. Every path below reaches `outcomeCheckForAlgorithm_sound`, and
through it the repository's single `accepted_run_certificate_sound` boundary.
No axiom, no `native_decide`, no `sorry` is introduced here.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

-- `SHA256.digestString` is `SparkInterval.Certificate.SHA256.digestString`;
-- `RegisteredAlgorithm.lean` reaches it through this same `open`.
open SparkInterval.Certificate

/-- Identification of one CompCert-compiled artifact run.

Everything here is *data*: adding a run means adding a value, not a
constructor, which is the whole point of this module. -/
structure CompCertRunSpec where
  /-- Stable name of the emitted program, e.g. `"CeUHarmonic1048576"`.  It
  appears in `canonicalDefinition` and therefore under the signature. -/
  programName : String
  /-- SHA-256 of the **exact C text handed to `ccomp`**, 64 lowercase hex.
  This is the artifact's identity; the consumer binds it to a Lean program. -/
  emittedCDigest : String
  /-- Compiler identity and flags, e.g.
  `"CompCert 3.17 x86_64-linux -O -fstruct-passing"`. -/
  toolchain : String
  /-- The value the artifact must report for the run to count as accepting. -/
  acceptedValue : Nat
  deriving Repr, DecidableEq, BEq

namespace CompCertRunSpec

/-- A lowercase hexadecimal digit. -/
private def isHexDigit (c : Char) : Bool :=
  ('0' ≤ c && c ≤ '9') || ('a' ≤ c && c ≤ 'f')

/-- A 256-bit digest written as 64 lowercase hex characters. -/
def isDigest256 (s : String) : Bool :=
  s.length == 64 && s.toList.all isHexDigit

/-- What can honestly be checked about a spec *at this level*.

This is **not** the artifact-to-program binding — that needs the emitter and
lives in the consumer.  It is the well-formedness that stops a malformed spec
from being pinned at all, and it occupies the slot that
`algorithmHashDiagnosticCheck` occupies for the closed registry (where the
analogous check would here be vacuous; see the module docstring). -/
def specWellFormed (spec : CompCertRunSpec) : Bool :=
  isDigest256 spec.emittedCDigest &&
    spec.programName != "" &&
    spec.toolchain != ""

/-- Canonical, signature-covered description of the artifact.

Line-oriented and fixed-order, so the preimage is unambiguous: every field is
either a fixed-length digest, a decimal natural, or a name from the run table,
and no field value can slide into another field's position. -/
def canonicalDefinition (spec : CompCertRunSpec) : String :=
  "sparkinterval.registered-algorithm.compcert-run.v1\n" ++
  "program=" ++ spec.programName ++ "\n" ++
  "emitted_c_sha256=" ++ spec.emittedCDigest ++ "\n" ++
  "toolchain=" ++ spec.toolchain ++ "\n" ++
  "accepted_value=" ++ toString spec.acceptedValue ++ "\n" ++
  "semantics=compile-the-named-c-with-the-named-toolchain-then-run-it-and-" ++
  "report-the-value-its-entry-point-returns"

/-- Algorithm identifier carried by the signed statement. -/
def algorithmId (spec : CompCertRunSpec) : String :=
  "compcert-run-v1:" ++ spec.programName

/-- Algorithm hash carried by the signed statement: the SHA-256 of the
generated `canonicalDefinition`, so the signature covers the artifact digest,
the toolchain and the accepted value. -/
def algorithmHash (spec : CompCertRunSpec) : String :=
  SHA256.digestString spec.canonicalDefinition

/-- The identity a downstream theorem pins, in the form
`SignedResultCertificate.outcomeCheckForAlgorithm` already consumes. -/
def expectedIdentity (spec : CompCertRunSpec) : ExpectedExecutableIdentity :=
  { algorithmId := spec.algorithmId, algorithmHash := spec.algorithmHash }

/-- Canonical textual form of the accepted value: the decimal digits and
nothing else.  The artifact's reported value is compared against this, so the
comparison is on bytes the signature covers. -/
def acceptedOutput (spec : CompCertRunSpec) : String :=
  toString spec.acceptedValue

end CompCertRunSpec

namespace SignedResultCertificate

/-- Fail-closed application check for one CompCert artifact run: the spec is
well formed, the signed statement names this artifact, the receipt is
accepted, the returned bytes and their digest are bound to the statement, and
the returned bytes are exactly the accepted value's decimal form. -/
def compcertRunCheck (certificate : SignedResultCertificate)
    (spec : CompCertRunSpec) : Bool :=
  spec.specWellFormed &&
    certificate.outcomeCheckForAlgorithm spec.expectedIdentity &&
    certificate.resultCertificate == spec.acceptedOutput

end SignedResultCertificate

/-- What an accepted CompCert run certificate establishes.

`execution` is the load-bearing one: the named artifact returned exactly the
accepted value's decimal form.  A consumer turns that into a statement about
its own program; this structure deliberately says nothing about denotations,
because this package has no compiler model. -/
structure CertifiedCompCertRun (certificate : SignedResultCertificate)
    (spec : CompCertRunSpec) : Prop where
  /-- The signed statement names this artifact and this toolchain. -/
  identity : certificate.ExecutableIdentityBound spec.expectedIdentity
  /-- The spec itself is well formed. -/
  wellFormed : spec.specWellFormed = true
  /-- The returned bytes are the accepted value's decimal form. -/
  resultCertificate_eq : certificate.resultCertificate = spec.acceptedOutput
  /-- The trusted run boundary: this computation returned those bytes. -/
  execution : AlgorithmReturned certificate.statement spec.acceptedOutput

/-- Soundness of the fail-closed check.  Reaches the repository's single
`accepted_run_certificate_sound` boundary through
`outcomeCheckForAlgorithm_sound`, and adds nothing to it. -/
theorem certifyCompCertRun {certificate : SignedResultCertificate}
    {spec : CompCertRunSpec}
    (hcheck : certificate.compcertRunCheck spec = true) :
    CertifiedCompCertRun certificate spec := by
  -- Two things the compiler had to settle, both easy to get wrong by reading:
  -- `&&` associates LEFT, so `simp` leaves `(A ∧ B) ∧ C`; and the components
  -- must be taken by projection rather than `obtain`, because destructuring
  -- makes `cases` attempt dependent elimination on the String equation in the
  -- last component and fail.
  simp only [SignedResultCertificate.compcertRunCheck, Bool.and_eq_true,
    beq_iff_eq] at hcheck
  have hwf := hcheck.1.1
  have houtcome := hcheck.1.2
  have hresult := hcheck.2
  have hcertified :=
    SignedResultCertificate.outcomeCheckForAlgorithm_sound houtcome
  exact {
    identity := hcertified.identity
    wellFormed := hwf
    resultCertificate_eq := hresult
    execution := hresult ▸ hcertified.outcome.execution
  }

end SparkInterval.Execution
