import SparkInterval.Execution.FormalPTXProgram
import SparkInterval.Zeta.EndpointCertificate

/-!
# Signed execution to typed zeta endpoint data

This module closes the smallest currently available wire-to-zeta composition.
The returned string is still the canonical full result-certificate format.  A
typed endpoint view interprets consecutive pairs of rows as the lower and upper
endpoint of one bracket.  Every input row must be a singleton binary64 value,
and every corresponding output must decode to a finite rational interval.

The combined checker requires:

* the exact `FormalPTXProgram` statement identity and accepted historical run;
* exact returned-text and SHA-256 binding from `SignedResultCertificate`;
* canonical parsing and equality with the supplied typed `FullCertificate`;
* equality of the parser-recomputed embedded batch digest with both the
  statement input and exact formal-program canonical input digest;
* independent checking of every full-certificate arithmetic row; and
* the exact-rational ordered endpoint-family check.

Only the accepted produced outcome uses the sole project run axiom; this
full-payload route does not use its registered projection for mathematics.
Parsing, equality, arithmetic, and endpoint signs are ordinary reducible Lean
checks.  This module does not claim that the parsed intervals enclose Hardy Z:
that evaluator-specific premise remains explicit when constructing a
`ZeroCertificate`.  The Hardy-Z representation and total zero-count premises
also remain separate.

This is a monolithic full-certificate bridge, not a constant-memory chunk
parser.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate
open SparkInterval.Zeta

/-- A signed run together with the exact typed full certificate expected to be
obtained by parsing its returned payload. -/
structure SignedZetaEndpointPayload (count : Nat) where
  signed : SignedResultCertificate
  parsed : FullCertificate

namespace SignedZetaEndpointPayload

/-- Decode the single exact rational input represented by one endpoint row. -/
def decodeSingletonRow? (row : Array RawInterval) : Option ℚ := do
  if row.size != 1 then none
  let raw ← row[0]?
  if raw.lo != raw.hi then none
  Binary64.decodeFinite raw.lo

/-- Decode one bracket from rows `2 * index` and `2 * index + 1`. -/
def endpointAt? (payload : FullCertificate) (index : Nat) : Option RationalBracket := do
  let lowerIndex := 2 * index
  let upperIndex := lowerIndex + 1
  let lowerRow ← payload.rows[lowerIndex]?
  let upperRow ← payload.rows[upperIndex]?
  let lower ← decodeSingletonRow? lowerRow
  let upper ← decodeSingletonRow? upperRow
  let lowerRaw ← payload.results[lowerIndex]?
  let upperRaw ← payload.results[upperIndex]?
  let lowerValue ← lowerRaw.decodeFinite
  let upperValue ← upperRaw.decodeFinite
  pure { lower, upper, lowerValue, upperValue }

/-- The finite output intervals exposed by a successfully decoded bracket are
the exact output rows at its two source indices. -/
theorem endpointAt?_resultData
    {payload : FullCertificate} {index : Nat} {bracket : RationalBracket}
    (hendpoint : endpointAt? payload index = some bracket) :
    ∃ lowerRaw upperRaw,
      payload.results[2 * index]? = some lowerRaw ∧
      lowerRaw.decodeFinite = some bracket.lowerValue ∧
      payload.results[2 * index + 1]? = some upperRaw ∧
      upperRaw.decodeFinite = some bracket.upperValue := by
  unfold endpointAt? at hendpoint
  cases hlowerRow : payload.rows[2 * index]? with
  | none => simp [hlowerRow] at hendpoint
  | some lowerRow =>
      cases hupperRow : payload.rows[2 * index + 1]? with
      | none => simp [hlowerRow, hupperRow] at hendpoint
      | some upperRow =>
          cases hlower : decodeSingletonRow? lowerRow with
          | none => simp [hlowerRow, hupperRow, hlower] at hendpoint
          | some lower =>
              cases hupper : decodeSingletonRow? upperRow with
              | none =>
                  simp [hlowerRow, hupperRow, hupper] at hendpoint
              | some upper =>
                  cases hlowerRaw : payload.results[2 * index]? with
                  | none =>
                      simp [hlowerRow, hupperRow,
                        hlowerRaw] at hendpoint
                  | some lowerRaw =>
                      cases hupperRaw : payload.results[2 * index + 1]? with
                      | none =>
                          simp [hlowerRow, hupperRow,
                            hlowerRaw, hupperRaw] at hendpoint
                      | some upperRaw =>
                          cases hlowerValue : lowerRaw.decodeFinite with
                          | none =>
                              simp [hlowerRow, hupperRow,
                                hlowerRaw, hupperRaw, hlowerValue] at hendpoint
                          | some lowerValue =>
                              cases hupperValue : upperRaw.decodeFinite with
                              | none =>
                                  simp [hlowerRow, hupperRow,
                                    hlowerRaw, hupperRaw,
                                    hupperValue] at hendpoint
                              | some upperValue =>
                                  simp [hlowerRow, hupperRow, hlower, hupper,
                                    hlowerRaw, hupperRaw, hlowerValue,
                                    hupperValue] at hendpoint
                                  subst bracket
                                  exact ⟨lowerRaw, upperRaw, rfl,
                                    hlowerValue, rfl, hupperValue⟩

/-- Deliberately invalid fallback. `endpointViewShapeCheck` requires every
lookup to succeed, and the family checker also rejects this fallback. -/
private def invalidBracket : RationalBracket := {
  lower := 0
  upper := 0
  lowerValue := ⟨0, 0⟩
  upperValue := ⟨0, 0⟩
}

/-- Deterministic typed endpoint family derived from the parsed full
certificate. -/
def endpointFamily (payload : FullCertificate)
    (count : Nat) : RationalBracketFamily count where
  entries index := (endpointAt? payload index.1).getD invalidBracket

/-- Require exactly two singleton, finite endpoint rows per bracket. -/
def endpointViewShapeCheck (payload : FullCertificate) (count : Nat) : Bool :=
  decide (payload.variableCount = 1) &&
    decide (payload.rows.size = 2 * count) &&
    decide (payload.results.size = 2 * count) &&
    (List.range count).all fun index => (endpointAt? payload index).isSome

/-- Check that `payload` is exactly the result of parsing `text`. -/
def parseBindingCheck (text : String) (payload : FullCertificate) : Bool :=
  match parseCanonicalFullCertificate text with
  | .ok parsed => decide (parsed = payload)
  | .error _ => false

theorem parseBindingCheck_sound {text : String} {payload : FullCertificate}
    (hcheck : parseBindingCheck text payload = true) :
    parseCanonicalFullCertificate text = .ok payload := by
  unfold parseBindingCheck at hcheck
  cases hparse : parseCanonicalFullCertificate text with
  | error message => simp [hparse] at hcheck
  | ok parsed =>
      have hequal : parsed = payload := by
        simpa only [hparse, decide_eq_true_eq] using hcheck
      rw [← hequal]

/-- Pure parsing, full arithmetic, shape, and endpoint-family checks. -/
def payloadCheck {count : Nat}
    (certificate : SignedZetaEndpointPayload count) : Bool :=
  parseBindingCheck certificate.signed.resultCertificate certificate.parsed &&
    (certificate.parsed.check &&
      (endpointViewShapeCheck certificate.parsed count &&
        (endpointFamily certificate.parsed count).check))

/-- Cross-bind the batch embedded in the returned full certificate to both
the accepted statement input and the exact canonical input selected by the
formal PTX program.  The full parser has already recomputed `parsed.batchHash`
from the nested canonical batch JSON. -/
def batchBindingCheck {count : Nat}
    (certificate : SignedZetaEndpointPayload count)
    (program : FormalPTXProgram) : Bool :=
  decide (
    certificate.parsed.batchHash = certificate.signed.statement.inputHash ∧
    certificate.parsed.batchHash = SHA256.digestString program.canonicalInput)

/-- Exact equalities reflected by `batchBindingCheck`. -/
def BatchBound {count : Nat}
    (certificate : SignedZetaEndpointPayload count)
    (program : FormalPTXProgram) : Prop :=
  certificate.parsed.batchHash = certificate.signed.statement.inputHash ∧
    certificate.parsed.batchHash = SHA256.digestString program.canonicalInput

theorem batchBindingCheck_sound {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hcheck : certificate.batchBindingCheck program = true) :
    certificate.BatchBound program := by
  simpa [batchBindingCheck, BatchBound] using hcheck

/-- Exact pure facts reflected by `payloadCheck`. -/
structure CheckedPayload {count : Nat}
    (certificate : SignedZetaEndpointPayload count) : Prop where
  parsed : parseCanonicalFullCertificate certificate.signed.resultCertificate =
    .ok certificate.parsed
  arithmetic : certificate.parsed.check = true
  shape : endpointViewShapeCheck certificate.parsed count = true
  family : (endpointFamily certificate.parsed count).check = true

/-- Evaluator semantics needed to connect the independently checked full
arithmetic rows to one real function.  This is weaker and more reusable than
assuming endpoint enclosures directly: each field states only that the formal
certificate expression realizes the evaluator value at the corresponding
singleton input row. -/
def EndpointRowsRealize {count : Nat}
    (certificate : SignedZetaEndpointPayload count)
    (f : ℝ → ℝ) : Prop :=
  ∀ i : Fin count,
    certificate.parsed.RowRealizes (2 * i.1)
        (f (((endpointFamily certificate.parsed count).entries i).lower : ℝ)) ∧
      certificate.parsed.RowRealizes (2 * i.1 + 1)
        (f (((endpointFamily certificate.parsed count).entries i).upper : ℝ))

theorem payloadCheck_sound {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    (hcheck : certificate.payloadCheck = true) :
    certificate.CheckedPayload := by
  simp only [payloadCheck, Bool.and_eq_true] at hcheck
  exact {
    parsed := parseBindingCheck_sound hcheck.1
    arithmetic := hcheck.2.1
    shape := hcheck.2.2.1
    family := hcheck.2.2.2
  }

/-- Full-certificate arithmetic soundness turns row-realization semantics into
the exact endpoint enclosures consumed by the zeta sign checker. -/
theorem CheckedPayload.enclosesEndpoints
    {count : Nat} {certificate : SignedZetaEndpointPayload count}
    {f : ℝ → ℝ}
    (checked : certificate.CheckedPayload)
    (realizes : certificate.EndpointRowsRealize f) :
    ∀ i,
      ((endpointFamily certificate.parsed count).entries i).EnclosesEndpoints f := by
  have hshape := checked.shape
  simp only [endpointViewShapeCheck, Bool.and_eq_true,
    decide_eq_true_eq] at hshape
  intro i
  have hisSome : (endpointAt? certificate.parsed i.1).isSome = true :=
    (List.all_eq_true.mp hshape.2) i.1 (List.mem_range.mpr i.isLt)
  cases hendpoint : endpointAt? certificate.parsed i.1 with
  | none => simp [hendpoint] at hisSome
  | some bracket =>
      have hentry :
          (endpointFamily certificate.parsed count).entries i = bracket := by
        simp [endpointFamily, hendpoint]
      have hrealizes := realizes i
      rw [hentry] at hrealizes
      obtain ⟨lowerRaw, upperRaw, hlowerRaw, hlowerDecode,
          hupperRaw, hupperDecode⟩ := endpointAt?_resultData hendpoint
      have hlowerIndex : 2 * i.1 < certificate.parsed.rows.size := by
        rw [hshape.1.1.2]
        omega
      have hupperIndex : 2 * i.1 + 1 < certificate.parsed.rows.size := by
        rw [hshape.1.1.2]
        omega
      rw [hentry]
      constructor
      · exact FullCertificate.resultContains_of_decodeFinite
          hlowerRaw hlowerDecode
          (FullCertificate.check_sound checked.arithmetic
            hlowerIndex hrealizes.1)
      · exact FullCertificate.resultContains_of_decodeFinite
          hupperRaw hupperDecode
          (FullCertificate.check_sound checked.arithmetic
            hupperIndex hrealizes.2)

/-- Bind the exact formal generated-PTX statement, historical returned bytes,
and the independently parsed endpoint payload in one check. -/
def check {count : Nat} (certificate : SignedZetaEndpointPayload count)
    (program : FormalPTXProgram) : Bool :=
  certificate.signed.outcomeCheckForFormalPTX program &&
    (certificate.batchBindingCheck program && certificate.payloadCheck)

/-- A returned certificate for any differently hashed canonical batch is
rejected before its endpoint facts can be paired with the historical run. -/
theorem check_eq_false_of_batchHash_ne {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hne : certificate.parsed.batchHash ≠
      SHA256.digestString program.canonicalInput) :
    certificate.check program = false := by
  simp [check, batchBindingCheck, hne]

/-- The combined handoff. `formalOutcome.outcome.execution` is the only field
that crosses `accepted_run_certificate_sound`; every field in `payload` is
supplied by pure parsing and checking. -/
structure CertifiedForFormalPTX
    {count : Nat} (certificate : SignedZetaEndpointPayload count)
    (program : FormalPTXProgram) : Prop where
  formalOutcome : certificate.signed.CertifiedFormalPTXOutcome program
  batch : certificate.BatchBound program
  payload : certificate.CheckedPayload

theorem check_sound {count : Nat}
    {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (hcheck : certificate.check program = true) :
    certificate.CertifiedForFormalPTX program := by
  simp only [check, Bool.and_eq_true] at hcheck
  exact {
    formalOutcome := SignedResultCertificate.outcomeCheckForFormalPTX_sound hcheck.1
    batch := batchBindingCheck_sound hcheck.2.1
    payload := payloadCheck_sound hcheck.2.2
  }

/-- The result named directly in the accepted statement parses to the exact
typed payload. This composes the proved text equality with the pure parser
result; it adds no trust assumption. -/
theorem CertifiedForFormalPTX.statementResult_parses
    {count : Nat} {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    (certified : certificate.CertifiedForFormalPTX program) :
    parseCanonicalFullCertificate certificate.signed.statement.result =
      .ok certificate.parsed := by
  rw [certified.formalOutcome.outcome.binding.1]
  exact certified.payload.parsed

/-- With the evaluator-specific endpoint enclosure theorem supplied
explicitly, the bound parsed family constructs the generic zero certificate.
Neither historical execution nor formal PTX identity is used to manufacture
the enclosure premise. -/
theorem check_exists_zeroCertificate
    {count : Nat} {certificate : SignedZetaEndpointPayload count}
    {program : FormalPTXProgram}
    {f : ℝ → ℝ}
    (hcheck : certificate.check program = true)
    (hencloses : ∀ i,
      ((endpointFamily certificate.parsed count).entries i).EnclosesEndpoints f) :
    certificate.signed.CertifiedFormalPTXOutcome program ∧
      ∃ zeros : ZeroCertificate f count,
        ∀ i,
          (zeros.brackets i).lower =
              ((endpointFamily certificate.parsed count).entries i).lower ∧
            (zeros.brackets i).upper =
              ((endpointFamily certificate.parsed count).entries i).upper := by
  have certified := check_sound hcheck
  refine ⟨certified.formalOutcome, ?_⟩
  exact (endpointFamily certificate.parsed count).exists_zeroCertificate
    certified.payload.family hencloses

end SignedZetaEndpointPayload

end SparkInterval.Execution
