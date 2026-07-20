import SparkInterval.Execution.FormalPTXProgram
import SparkInterval.Zeta.CriticalLine

/-!
# Compact outcomes from an attested verifier

A server-side verifier may stream a very large certificate and return only a
small summary.  Such a summary can avoid transferring the large certificate,
but its hash or attested provenance is not, by itself, a mathematical proof.
Two distinct theorems are required:

1. accepted physical execution of the pinned program refines a stated formal
   verifier semantics; and
2. that formal verifier semantics implies the mathematical claim represented
   by the decoded summary.

This module retains the original generic formal-PTX contract, for which both
facts remain explicit arguments.  It also provides the preferred closed-
registry contract below.  On that path, the sole run-certificate axiom already
supplies the per-run physical-to-formal bridge as `RegisteredInvocation.Runs`;
only the ordinary algorithm-soundness theorem remains to be supplied.

For a zeta verifier, the second theorem is where the proved Hardy-Z model,
endpoint enclosure algorithm, streaming coverage invariant, and analytic
zero-count argument must ultimately be used.  Attestation cannot supply any
of those analytic facts.
-/

set_option autoImplicit false

universe u

namespace SparkInterval.Execution

/-- Application-neutral specification of a verifier that returns a compact
summary.

`semantics` is the formal accepted-run relation.  It should describe the
complete checker execution, including successful end-of-stream processing;
an evidence-root comparison alone is not an adequate semantics. -/
structure CompactVerifierContract (Summary : Type u) where
  decode : String → Option Summary
  semantics : FormalPTXProgram → RunStatement → Summary → Prop
  claim : Summary → Prop

namespace CompactVerifierContract

/-- Missing physical-to-formal bridge for a compact verifier.

This proposition is deliberately separate from `Sound`.  With the present
opaque `AlgorithmReturned`, it must be proved by an actual execution-refinement
result or included in the meaning of a future strengthened single trust
boundary.  Treating it as automatic would silently add a second trust step. -/
def ExecutionRefines {Summary : Type u}
    (contract : CompactVerifierContract Summary)
    (program : FormalPTXProgram) : Prop :=
  ∀ {certificate : SignedResultCertificate} {summary : Summary},
    certificate.CertifiedFormalPTXOutcome program →
      contract.decode certificate.resultCertificate = some summary →
        contract.semantics program certificate.statement summary

/-- Pure algorithm/analytic soundness theorem required of the formal verifier
semantics.  It is independent of signatures and attestation. -/
def Sound {Summary : Type u}
    (contract : CompactVerifierContract Summary)
    (program : FormalPTXProgram) : Prop :=
  ∀ {statement : RunStatement} {summary : Summary},
    contract.semantics program statement summary → contract.claim summary

end CompactVerifierContract

/-- Complete legacy compact-result handoff.  `historical` crosses
`accepted_run_certificate_sound`; `semantics` and `mathematics` then depend on
the two explicit refinement/soundness theorems.  No large certificate is
retained in this proposition. -/
structure CertifiedCompactVerifierOutcome
    {Summary : Type u}
    (certificate : SignedResultCertificate)
    (program : FormalPTXProgram)
    (contract : CompactVerifierContract Summary)
    (summary : Summary) : Prop where
  historical : certificate.CertifiedFormalPTXOutcome program
  decoded : contract.decode certificate.resultCertificate = some summary
  semantics : contract.semantics program certificate.statement summary
  mathematics : contract.claim summary

namespace SignedResultCertificate

/-- Compose the sole accepted-run boundary with explicit execution refinement
and verifier soundness.  This theorem is small enough for a server to return a
compact summary, but it intentionally does not assert either missing premise. -/
theorem certifyCompactVerifierOutcome
    {Summary : Type u}
    {certificate : SignedResultCertificate}
    {program : FormalPTXProgram}
    {contract : CompactVerifierContract Summary}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true)
    (hdecode : contract.decode certificate.resultCertificate = some summary)
    (refinement : contract.ExecutionRefines program)
    (sound : contract.Sound program) :
    CertifiedCompactVerifierOutcome certificate program contract summary := by
  have historical := outcomeCheckForFormalPTX_sound hcheck
  have hsemantics := refinement historical hdecode
  exact {
    historical := historical
    decoded := hdecode
    semantics := hsemantics
    mathematics := sound hsemantics
  }

end SignedResultCertificate

/-! ## Preferred closed-registry compact verifier -/

/-- A compact result contract whose physical execution semantics cannot be
chosen by the caller.  `decode` and `claim` remain application data, but the
soundness theorem below must derive the claim from the closed registry's
`RegisteredInvocation.Runs`. -/
structure RegisteredCompactVerifierContract (Summary : Type u) where
  decode : String → Option Summary
  claim : Summary → Prop

namespace RegisteredCompactVerifierContract

/-- Pure algorithm-soundness obligation for one closed registered invocation.

Unlike `CompactVerifierContract.ExecutionRefines`, this contains no physical
execution premise: the sole accepted-run axiom supplies `invocation.Runs` for
the particular certificate. -/
def Sound {Summary : Type u}
    (contract : RegisteredCompactVerifierContract Summary)
    (invocation : RegisteredInvocation) : Prop :=
  ∀ {output : String} {summary : Summary},
    invocation.Runs output →
      contract.decode output = some summary →
        contract.claim summary

end RegisteredCompactVerifierContract

/-- Compact theorem package for a closed registered execution.  No large input
witness or result trace is retained. -/
structure CertifiedRegisteredCompactVerifierOutcome
    {Summary : Type u}
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation)
    (contract : RegisteredCompactVerifierContract Summary)
    (summary : Summary) : Prop where
  registered : certificate.CertifiedOutcomeForRegisteredInvocation invocation
  decoded : contract.decode certificate.resultCertificate = some summary
  mathematics : contract.claim summary

namespace SignedResultCertificate

/-- The accepted certificate directly unlocks fixed registered semantics; a
proved algorithm-soundness theorem turns those semantics into the compact
claim.  This is the server-side path that needs no second execution-refinement
assumption. -/
theorem certifyRegisteredCompactVerifierOutcome
    {Summary : Type u}
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    {contract : RegisteredCompactVerifierContract Summary}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation invocation = true)
    (hdecode : contract.decode certificate.resultCertificate = some summary)
    (sound : contract.Sound invocation) :
    CertifiedRegisteredCompactVerifierOutcome
      certificate invocation contract summary := by
  have registered := outcomeCheckForRegisteredInvocation_sound hcheck
  exact {
    registered := registered
    decoded := hdecode
    mathematics := sound registered.run hdecode
  }

end SignedResultCertificate

/-! ## Finite-height zeta specialization -/

open SparkInterval.Zeta

/-- The exact mathematical conclusion represented by a successful compact
finite-height zeta-verifier summary. -/
def FiniteHeightZetaClaim (height : ℝ) : Prop :=
  ∀ z ∈ criticalRectangle height,
    riemannZeta z = 0 → z.re = (1 : ℝ) / 2

/-- Specialize a generic compact checker semantics to the finite-height zeta
claim.  `heightOf` must come from the canonically decoded summary. -/
def compactFiniteHeightZetaContract
    {Summary : Type u}
    (decode : String → Option Summary)
    (semantics : FormalPTXProgram → RunStatement → Summary → Prop)
    (heightOf : Summary → ℝ) : CompactVerifierContract Summary := {
  decode := decode
  semantics := semantics
  claim := fun summary ↦ FiniteHeightZetaClaim (heightOf summary)
}

/-- Compact zeta outcome retaining only the decoded summary, the historical
attested outcome, the formal verifier-semantics fact, and the theorem. -/
abbrev CertifiedCompactZetaVerification
    {Summary : Type u}
    (certificate : SignedResultCertificate)
    (program : FormalPTXProgram)
    (decode : String → Option Summary)
    (semantics : FormalPTXProgram → RunStatement → Summary → Prop)
    (heightOf : Summary → ℝ)
    (summary : Summary) : Prop :=
  CertifiedCompactVerifierOutcome certificate program
    (compactFiniteHeightZetaContract decode semantics heightOf) summary

namespace SignedResultCertificate

/-- Zeta-specific compact composition.

On this legacy FormalPTX route, `refinement` is the currently missing link from
the historical run to formal checker execution.  `verifierSound` is the full non-attestation theorem
that a successful formal checker run establishes the finite-height zeta claim;
it must not be replaced by an unchecked count or Merkle root. -/
theorem certifyCompactFiniteHeightZeta
    {Summary : Type u}
    {certificate : SignedResultCertificate}
    {program : FormalPTXProgram}
    {decode : String → Option Summary}
    {semantics : FormalPTXProgram → RunStatement → Summary → Prop}
    {heightOf : Summary → ℝ}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForFormalPTX program = true)
    (hdecode : decode certificate.resultCertificate = some summary)
    (refinement :
      CompactVerifierContract.ExecutionRefines
        (compactFiniteHeightZetaContract decode semantics heightOf) program)
    (verifierSound :
      ∀ {statement : RunStatement} {result : Summary},
        semantics program statement result →
          FiniteHeightZetaClaim (heightOf result)) :
    CertifiedCompactZetaVerification certificate program decode semantics
      heightOf summary := by
  apply certificate.certifyCompactVerifierOutcome hcheck hdecode refinement
  exact verifierSound

end SignedResultCertificate

/-! ### Closed-registry finite-height zeta specialization -/

/-- Compact zeta contract for a checker whose execution relation is supplied
by a closed `RegisteredInvocation`. -/
def registeredCompactFiniteHeightZetaContract
    {Summary : Type u}
    (decode : String → Option Summary)
    (heightOf : Summary → ℝ) : RegisteredCompactVerifierContract Summary := {
  decode := decode
  claim := fun summary ↦ FiniteHeightZetaClaim (heightOf summary)
}

/-- Closed-registry compact zeta outcome. -/
abbrev CertifiedRegisteredCompactZetaVerification
    {Summary : Type u}
    (certificate : SignedResultCertificate)
    (invocation : RegisteredInvocation)
    (decode : String → Option Summary)
    (heightOf : Summary → ℝ)
    (summary : Summary) : Prop :=
  CertifiedRegisteredCompactVerifierOutcome certificate invocation
    (registeredCompactFiniteHeightZetaContract decode heightOf) summary

namespace SignedResultCertificate

/-- Preferred compact zeta composition.  A future audited zeta-checker
registry constructor and a proof of `verifierSound` are the remaining
application-specific pieces; no separate physical `ExecutionRefines` premise
is present. -/
theorem certifyRegisteredCompactFiniteHeightZeta
    {Summary : Type u}
    {certificate : SignedResultCertificate}
    {invocation : RegisteredInvocation}
    {decode : String → Option Summary}
    {heightOf : Summary → ℝ}
    {summary : Summary}
    (hcheck : certificate.outcomeCheckForRegisteredInvocation invocation = true)
    (hdecode : decode certificate.resultCertificate = some summary)
    (verifierSound :
      ∀ {output : String} {result : Summary},
        invocation.Runs output →
          decode output = some result →
            FiniteHeightZetaClaim (heightOf result)) :
    CertifiedRegisteredCompactZetaVerification certificate invocation decode
      heightOf summary := by
  apply certificate.certifyRegisteredCompactVerifierOutcome hcheck hdecode
  exact verifierSound

end SignedResultCertificate

end SparkInterval.Execution
