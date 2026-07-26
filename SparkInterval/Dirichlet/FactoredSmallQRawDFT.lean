/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFTCorrectness

/-!
# Bounded raw binary64 certificates for the factored small-`q` DFT

This module replaces the total function fields of `FactoredSmallQDFT` by
finite, canonically ordered raw-binary64 lists.  A raw stage contains exactly
one butterfly per `(group, offset)`, in row-major order

```
group * 2^stage + offset.
```

The decoder checks the complete source-owned shape before decoding any
arithmetic witness.  It then decodes every disk, addition witness, and
multiplication witness to exact rationals and realizes the finite lists as the
typed lookup tables used by `FactoredSmallQDFT.Certificate.check`.

The public checker has three independent resource bounds: transform
`logLength`, line length, and total raw record count.  These bounds are tested
before binary64 decoding.  The separately supplied final-output words are
also decoded and checked pointwise equal to the output derived from the full
butterfly trace.  Thus the application theorem names the actual raw output
word for every frequency, not merely an unlinked typed result.

This is a finite arithmetic bridge, not a byte parser or an execution claim.
The initial bit-reversal containment and transcendental root containment
remain explicit mathematical premises. The generic radix-2/DFT identity is
proved in `FactoredSmallQDFTCorrectness`.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawDFT

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT

variable {α β : Type*}

/-! ## Order-preserving raw decoding -/

/-- Decode a list without inserting, dropping, or reordering any element. -/
def decodeList (decode : α → Option β) : List α → Option (List β)
  | [] => some []
  | raw :: rest => do
      let value ← decode raw
      let values ← decodeList decode rest
      pure (value :: values)

theorem decodeList_forall₂ {decode : α → Option β}
    {raws : List α} {values : List β}
    (hdecode : decodeList decode raws = some values) :
    List.Forall₂ (fun raw value => decode raw = some value) raws values := by
  induction raws generalizing values with
  | nil =>
      simp [decodeList] at hdecode
      subst values
      exact .nil
  | cons raw rest ih =>
      simp only [decodeList] at hdecode
      cases hraw : decode raw with
      | none => simp [hraw] at hdecode
      | some value =>
          cases hrest : decodeList decode rest with
          | none => simp [hraw, hrest] at hdecode
          | some decoded =>
              simp [hraw, hrest] at hdecode
              subst values
              exact .cons hraw (ih hrest)

theorem decodeList_length {decode : α → Option β}
    {raws : List α} {values : List β}
    (hdecode : decodeList decode raws = some values) :
    values.length = raws.length :=
  (decodeList_forall₂ hdecode).length_eq.symm

def decodeDisks : List ComplexDisk.Raw → Option (List ComplexDisk) :=
  decodeList ComplexDisk.Raw.decode

def decodeDiskRows : List (List ComplexDisk.Raw) →
    Option (List (List ComplexDisk)) :=
  decodeList decodeDisks

/-! ## Raw butterfly and stage rows -/

/-- Raw binary64 form of one fully linked typed butterfly row. -/
structure RawButterflyCertificate where
  stageExponent : Nat
  stageLength : Nat
  group : Nat
  offset : Nat
  leftIndex : Nat
  rightIndex : Nat
  twiddleTimesRight : ComplexDisk.RawMulCertificate
  addToLeft : ComplexDisk.RawAddCertificate
  addNegToRight : ComplexDisk.RawAddCertificate
  deriving Repr, DecidableEq, BEq

namespace RawButterflyCertificate

def decode (raw : RawButterflyCertificate) : Option ButterflyCertificate := do
  let twiddleTimesRight ← raw.twiddleTimesRight.decode
  let addToLeft ← raw.addToLeft.decode
  let addNegToRight ← raw.addNegToRight.decode
  pure {
    stageExponent := raw.stageExponent
    stageLength := raw.stageLength
    group := raw.group
    offset := raw.offset
    leftIndex := raw.leftIndex
    rightIndex := raw.rightIndex
    twiddleTimesRight
    addToLeft
    addNegToRight
  }

end RawButterflyCertificate

def decodeButterflies : List RawButterflyCertificate →
    Option (List ButterflyCertificate) :=
  decodeList RawButterflyCertificate.decode

/-- Harmless total-table fallback.  Exact shape checks ensure that the typed
checker never reaches it at a source-owned query. -/
def fallbackDisk : ComplexDisk := ⟨0, 0, 0⟩

def fallbackAdd : ComplexDisk.AddCertificate := {
  left := fallbackDisk
  right := fallbackDisk
  output := fallbackDisk
  centerErrorBound := 0
}

def fallbackMul : ComplexDisk.MulCertificate := {
  left := fallbackDisk
  right := fallbackDisk
  output := fallbackDisk
  centerErrorBound := 0
  leftCenterNormBound := 0
  rightCenterNormBound := 0
}

def fallbackButterfly : ButterflyCertificate := {
  stageExponent := 0
  stageLength := 0
  group := 0
  offset := 0
  leftIndex := 0
  rightIndex := 0
  twiddleTimesRight := fallbackMul
  addToLeft := fallbackAdd
  addNegToRight := fallbackAdd
}

/-- Canonical row-major realization of one finite butterfly list. -/
def butterflyTable (expectedStage : Nat)
    (rows : List ButterflyCertificate) : Nat → Nat → ButterflyCertificate :=
  fun group offset =>
    rows.getD (group * halfLength expectedStage + offset) fallbackButterfly

/-- Finite raw rows for one stage.  `stageExponent` is retained as certificate
data and checked again by the typed checker. -/
structure RawStageCertificate where
  stageExponent : Nat
  rows : List RawButterflyCertificate
  deriving Repr, DecidableEq, BEq

namespace RawStageCertificate

def decode {logLength : Nat} (expectedStage : Nat)
    (raw : RawStageCertificate) : Option (StageCertificate logLength) := do
  let rows ← decodeButterflies raw.rows
  pure {
    stageExponent := raw.stageExponent
    rows := butterflyTable expectedStage rows
  }

end RawStageCertificate

def decodeStages {logLength : Nat} :
    Nat → List RawStageCertificate →
      Option (List (StageCertificate logLength))
  | _, [] => some []
  | expectedStage, raw :: rest => do
      let stage ← raw.decode expectedStage
      let stages ← decodeStages (expectedStage + 1) rest
      pure (stage :: stages)

/-! ## Finite table realization and canonical shape -/

def diskAt (values : List ComplexDisk) (index : Nat) : ComplexDisk :=
  values.getD index fallbackDisk

def diskStateOfList {logLength : Nat}
    (values : List ComplexDisk) : DiskState logLength :=
  ⟨fun index => diskAt values index.val⟩

def diskTableOfRows (rows : List (List ComplexDisk)) :
    Nat → Nat → ComplexDisk :=
  fun stage offset => diskAt (rows.getD stage []) offset

def lineLength (logLength : Nat) : Nat := 2 ^ logLength

def butterflyRowsPerStage (logLength : Nat) : Nat :=
  lineLength logLength / 2

/-- Exact finite shape at one source-owned stage index. -/
def StageShape (logLength expectedStage : Nat)
    (twiddleRows : List (List ComplexDisk.Raw))
    (stages : List RawStageCertificate) : Prop :=
  match twiddleRows[expectedStage]? with
  | none => False
  | some twiddles =>
      match stages[expectedStage]? with
      | none => False
      | some stage =>
          twiddles.length = halfLength expectedStage ∧
          stage.stageExponent = expectedStage ∧
          stage.rows.length = butterflyRowsPerStage logLength

instance instDecidableStageShape (logLength expectedStage : Nat)
    (twiddleRows : List (List ComplexDisk.Raw))
    (stages : List RawStageCertificate) :
    Decidable (StageShape logLength expectedStage twiddleRows stages) := by
  cases htwiddles : twiddleRows[expectedStage]? with
  | none => exact isFalse (by simp [StageShape, htwiddles])
  | some twiddles =>
      cases hstage : stages[expectedStage]? with
      | none => exact isFalse (by simp [StageShape, htwiddles, hstage])
      | some stage =>
          simp only [StageShape, htwiddles, hstage]
          infer_instance

/-- The complete source-owned list shape.  In particular, no lookup table can
be populated by a short list plus fallback values. -/
def CanonicalShape {logLength : Nat}
    (input output : List ComplexDisk.Raw)
    (twiddleRows : List (List ComplexDisk.Raw))
    (stages : List RawStageCertificate) : Prop :=
  input.length = lineLength logLength ∧
  output.length = lineLength logLength ∧
  twiddleRows.length = logLength ∧
  stages.length = logLength ∧
  ∀ expectedStage ∈ List.range logLength,
    StageShape logLength expectedStage twiddleRows stages

instance instDecidableCanonicalShape {logLength : Nat}
    (input output : List ComplexDisk.Raw)
    (twiddleRows : List (List ComplexDisk.Raw))
    (stages : List RawStageCertificate) :
    Decidable (CanonicalShape (logLength := logLength)
      input output twiddleRows stages) := by
  unfold CanonicalShape
  infer_instance

/-! ## Complete raw transform certificate -/

/-- Finite raw binary64 transform trace, including an independently supplied
final line that must agree with the trace-derived line. -/
structure RawCertificate (logLength : Nat) where
  input : List ComplexDisk.Raw
  twiddleRows : List (List ComplexDisk.Raw)
  stages : List RawStageCertificate
  output : List ComplexDisk.Raw
  deriving Repr, DecidableEq, BEq

/-- Decoded finite payload.  Its typed certificate and claimed final state are
definitions of these exact finite lists, not extra trusted claims. -/
structure DecodedCertificate (logLength : Nat) where
  inputValues : List ComplexDisk
  twiddleValues : List (List ComplexDisk)
  stageValues : List (StageCertificate logLength)
  outputValues : List ComplexDisk

namespace DecodedCertificate

def certificate {logLength : Nat}
    (decoded : DecodedCertificate logLength) : Certificate logLength := {
  input := diskStateOfList decoded.inputValues
  twiddleDisks := diskTableOfRows decoded.twiddleValues
  stages := decoded.stageValues
}

def claimedOutput {logLength : Nat}
    (decoded : DecodedCertificate logLength) : DiskState logLength :=
  diskStateOfList decoded.outputValues

/-- The separately decoded output line is exactly the one derived from the
checked butterfly trace at every source-owned frequency. -/
def OutputLinked {logLength : Nat}
    (decoded : DecodedCertificate logLength) : Prop :=
  ∀ frequency,
    decoded.claimedOutput.value frequency =
      decoded.certificate.output.value frequency

instance instDecidableOutputLinked {logLength : Nat}
    (decoded : DecodedCertificate logLength) :
    Decidable decoded.OutputLinked := by
  unfold OutputLinked
  infer_instance

/-- Every standalone disk table decoded from the raw certificate has a
nonnegative radius.  Disks nested inside butterfly addition/multiplication
witnesses are already covered by those witnesses' checked `WellFormed`
propositions; the input, output, and root tables need this explicit guard,
especially for the stage-free `logLength = 0` case. -/
def TableRadiiNonnegative {logLength : Nat}
    (decoded : DecodedCertificate logLength) : Prop :=
  (∀ disk ∈ decoded.inputValues, 0 ≤ disk.radius) ∧
  (∀ row ∈ decoded.twiddleValues,
    ∀ disk ∈ row, 0 ≤ disk.radius) ∧
  (∀ disk ∈ decoded.outputValues, 0 ≤ disk.radius)

instance instDecidableTableRadiiNonnegative {logLength : Nat}
    (decoded : DecodedCertificate logLength) :
    Decidable decoded.TableRadiiNonnegative := by
  unfold TableRadiiNonnegative
  infer_instance

end DecodedCertificate

/-- Bounds checked before nested binary64 decoding. -/
structure Bounds where
  maxLogLength : Nat
  maxLineLength : Nat
  maxRecords : Nat
  deriving Repr, DecidableEq, BEq

namespace RawCertificate

def recordCount {logLength : Nat} (raw : RawCertificate logLength) : Nat :=
  raw.input.length + raw.output.length +
    (raw.twiddleRows.map List.length).sum +
    (raw.stages.map (fun stage => stage.rows.length)).sum

/-- Human-readable resource proposition behind the short-circuiting Boolean
guard. -/
def WithinBounds {logLength : Nat} (raw : RawCertificate logLength)
    (bounds : Bounds) : Prop :=
  logLength ≤ bounds.maxLogLength ∧
  lineLength logLength ≤ bounds.maxLineLength ∧
  raw.recordCount ≤ bounds.maxRecords

def boundsCheck {logLength : Nat} (raw : RawCertificate logLength)
    (bounds : Bounds) : Bool :=
  decide (logLength ≤ bounds.maxLogLength) &&
  decide (lineLength logLength ≤ bounds.maxLineLength) &&
  decide (raw.recordCount ≤ bounds.maxRecords)

theorem boundsCheck_sound {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    (hcheck : raw.boundsCheck bounds = true) :
    raw.WithinBounds bounds := by
  simp only [boundsCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1.1, hcheck.1.2, hcheck.2⟩

/-- Shape-first, order-preserving decoding into the typed finite-query
certificate. -/
def decode {logLength : Nat} (raw : RawCertificate logLength) :
    Option (DecodedCertificate logLength) := do
  if CanonicalShape (logLength := logLength) raw.input raw.output
      raw.twiddleRows raw.stages then pure () else none
  let inputValues ← decodeDisks raw.input
  let twiddleValues ← decodeDiskRows raw.twiddleRows
  let stageValues ← decodeStages 0 raw.stages
  let outputValues ← decodeDisks raw.output
  pure { inputValues, twiddleValues, stageValues, outputValues }

/-- Proposition recovered from an accepted bounded raw transform. -/
def Validated {logLength : Nat} (raw : RawCertificate logLength)
    (bounds : Bounds) : Prop :=
  raw.WithinBounds bounds ∧
  ∃ decoded : DecodedCertificate logLength,
    raw.decode = some decoded ∧
    decoded.certificate.check = true ∧
    decoded.OutputLinked ∧
    decoded.TableRadiiNonnegative

/-- Fail-closed checker.  Resource bounds precede shape traversal, binary64
decoding, exact rational arithmetic, and the final output comparison. -/
def check {logLength : Nat} (raw : RawCertificate logLength)
    (bounds : Bounds) : Bool :=
  raw.boundsCheck bounds &&
  match raw.decode with
  | none => false
  | some decoded =>
      decoded.certificate.check && decide decoded.OutputLinked &&
        decide decoded.TableRadiiNonnegative

theorem checker_sound {logLength : Nat} {raw : RawCertificate logLength}
    {bounds : Bounds} (hcheck : raw.check bounds = true) :
    raw.Validated bounds := by
  unfold check at hcheck
  simp only [Bool.and_eq_true] at hcheck
  refine ⟨boundsCheck_sound hcheck.1, ?_⟩
  cases hdecode : raw.decode with
  | none => simp [hdecode] at hcheck
  | some decoded =>
      have htail :
          ((decoded.certificate.check && decide decoded.OutputLinked) &&
            decide decoded.TableRadiiNonnegative) = true := by
        simpa [hdecode] using hcheck.2
      have houter := Bool.and_eq_true_iff.mp htail
      have hinner := Bool.and_eq_true_iff.mp houter.1
      refine ⟨decoded, by simp, hinner.1,
        of_decide_eq_true hinner.2, ?_⟩
      exact of_decide_eq_true houter.2

theorem canonicalShape_of_decode {logLength : Nat}
    {raw : RawCertificate logLength}
    {decoded : DecodedCertificate logLength}
    (hdecode : raw.decode = some decoded) :
    CanonicalShape (logLength := logLength) raw.input raw.output
      raw.twiddleRows raw.stages := by
  unfold decode at hdecode
  by_cases hshape : CanonicalShape (logLength := logLength)
      raw.input raw.output raw.twiddleRows raw.stages
  · exact hshape
  · simp [hshape] at hdecode

/-- Successful complete decoding exposes the exact order-preserving decode of
the separately supplied output list. -/
theorem outputValues_decode_eq {logLength : Nat}
    {raw : RawCertificate logLength}
    {decoded : DecodedCertificate logLength}
    (hdecode : raw.decode = some decoded) :
    decodeDisks raw.output = some decoded.outputValues := by
  unfold decode at hdecode
  split at hdecode
  · rename_i hshape
    simp only [Option.bind_eq_bind] at hdecode
    cases hinput : decodeDisks raw.input with
    | none => simp [hinput] at hdecode
    | some inputValues =>
        cases htwiddles : decodeDiskRows raw.twiddleRows with
        | none => simp [hinput, htwiddles] at hdecode
        | some twiddleValues =>
            cases hstages : decodeStages (logLength := logLength) 0 raw.stages with
            | none => simp [hinput, htwiddles, hstages] at hdecode
            | some stageValues =>
                cases houtput : decodeDisks raw.output with
                | none => simp [hinput, htwiddles, hstages, houtput] at hdecode
                | some outputValues =>
                    simp [hinput, htwiddles, hstages, houtput] at hdecode
                    subst decoded
                    simp
  · simp at hdecode

/-- Every source-owned final word decodes to the corresponding claimed output
disk.  This is the exact raw-word endpoint used by the application theorem. -/
theorem output_word_decodes {logLength : Nat}
    {raw : RawCertificate logLength}
    {decoded : DecodedCertificate logLength}
    (hdecode : raw.decode = some decoded)
    (frequency : Fin (lineLength logLength)) :
    ∃ rawDisk : ComplexDisk.Raw,
      raw.output[frequency.val]? = some rawDisk ∧
      rawDisk.decode = some (decoded.claimedOutput.value frequency) := by
  have hshape := canonicalShape_of_decode hdecode
  have hrawLength : raw.output.length = lineLength logLength := hshape.2.1
  have hvaluesDecode := outputValues_decode_eq hdecode
  have hvaluesLength : decoded.outputValues.length = raw.output.length :=
    decodeList_length hvaluesDecode
  have hrawLt : frequency.val < raw.output.length := by
    rw [hrawLength]
    exact frequency.isLt
  have hvaluesLt : frequency.val < decoded.outputValues.length := by
    rw [hvaluesLength]
    exact hrawLt
  let rawDisk := raw.output[frequency.val]
  refine ⟨rawDisk, ?_, ?_⟩
  · exact List.getElem?_eq_getElem hrawLt
  · have hrelation := (decodeList_forall₂ hvaluesDecode).get
        hrawLt hvaluesLt
    change rawDisk.decode =
      some (decoded.outputValues.getD frequency.val fallbackDisk)
    rw [List.getD_eq_getElem _ _ hvaluesLt]
    simpa [rawDisk] using hrelation

/-- Named-decoding application theorem for the exact staged transform. -/
theorem decoded_output_contains_transform {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    {decoded : DecodedCertificate logLength}
    {initial : ExactState logLength} {twiddles : Nat → Nat → ℂ}
    (hcheck : raw.check bounds = true)
    (hdecode : raw.decode = some decoded)
    (hinput : StateContains decoded.certificate.input initial)
    (htwiddles : TwiddlesContain (logLength := logLength)
      decoded.certificate.twiddleDisks twiddles) :
    StateContains decoded.claimedOutput
      (runExactStages twiddles logLength 0 initial) := by
  have hvalidated := checker_sound hcheck
  rcases hvalidated.2 with
    ⟨checked, hcheckedDecode, htypedCheck, hlinked, _⟩
  have hsame : checked = decoded := by
    rw [hdecode] at hcheckedDecode
    exact (Option.some.inj hcheckedDecode).symm
  subst checked
  have htyped := Certificate.output_contains_transform
    htypedCheck hinput htwiddles
  intro frequency
  rw [hlinked frequency]
  exact htyped frequency

/-- Raw-word endpoint for the exact staged transform. -/
theorem output_words_contain_transform {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    {decoded : DecodedCertificate logLength}
    {initial : ExactState logLength} {twiddles : Nat → Nat → ℂ}
    (hcheck : raw.check bounds = true)
    (hdecode : raw.decode = some decoded)
    (hinput : StateContains decoded.certificate.input initial)
    (htwiddles : TwiddlesContain (logLength := logLength)
      decoded.certificate.twiddleDisks twiddles) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        raw.output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some (decoded.claimedOutput.value frequency) ∧
        (decoded.claimedOutput.value frequency).ContainsComplex
          ((runExactStages twiddles logLength 0 initial).value frequency) := by
  have hcontains := decoded_output_contains_transform
    hcheck hdecode hinput htwiddles
  intro frequency
  rcases output_word_decodes hdecode frequency with
    ⟨rawDisk, hword, hwordDecode⟩
  exact ⟨rawDisk, hword, hwordDecode, hcontains frequency⟩

/-- Positive-sign radix-2 corollary with raw final-word linkage. -/
theorem output_words_contain_positiveRadix2 {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    {decoded : DecodedCertificate logLength}
    {source : ExactState logLength}
    (hcheck : raw.check bounds = true)
    (hdecode : raw.decode = some decoded)
    (hbitReverse : StateContains decoded.certificate.input
      (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      decoded.certificate.twiddleDisks positiveTwiddle) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        raw.output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some (decoded.claimedOutput.value frequency) ∧
        (decoded.claimedOutput.value frequency).ContainsComplex
          ((positiveRadix2Transform source).value frequency) := by
  simpa [positiveRadix2Transform] using
    (output_words_contain_transform hcheck hdecode hbitReverse hroots)

/-- Compatibility direct-DFT corollary parameterized by the generic radix-2
correctness proposition. The premise-free theorem below discharges it. -/
theorem output_words_contain_positiveDFT {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    {decoded : DecodedCertificate logLength}
    {source : ExactState logLength}
    (hcheck : raw.check bounds = true)
    (hdecode : raw.decode = some decoded)
    (hbitReverse : StateContains decoded.certificate.input
      (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      decoded.certificate.twiddleDisks positiveTwiddle)
    (hRadix2 : Radix2CorrectFor source) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        raw.output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some (decoded.claimedOutput.value frequency) ∧
        (decoded.claimedOutput.value frequency).ContainsComplex
          (positiveDFT source frequency) := by
  have hradix := output_words_contain_positiveRadix2
    hcheck hdecode hbitReverse hroots
  intro frequency
  rcases hradix frequency with
    ⟨rawDisk, hword, hwordDecode, hcontains⟩
  refine ⟨rawDisk, hword, hwordDecode, ?_⟩
  rw [← hRadix2 frequency]
  exact hcontains

/-- Premise-free direct positive-sign DFT endpoint. The generic radix-2
identity is proved once in `FactoredSmallQDFTCorrectness`; certificates retain
only the arithmetic input and root-containment premises. -/
theorem output_words_contain_positiveDFT_unconditional {logLength : Nat}
    {raw : RawCertificate logLength} {bounds : Bounds}
    {decoded : DecodedCertificate logLength}
    {source : ExactState logLength}
    (hcheck : raw.check bounds = true)
    (hdecode : raw.decode = some decoded)
    (hbitReverse : StateContains decoded.certificate.input
      (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      decoded.certificate.twiddleDisks positiveTwiddle) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        raw.output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some (decoded.claimedOutput.value frequency) ∧
        (decoded.claimedOutput.value frequency).ContainsComplex
          (positiveDFT source frequency) :=
  output_words_contain_positiveDFT hcheck hdecode hbitReverse hroots
    (radix2CorrectFor source)

end RawCertificate

end SparkInterval.Dirichlet.FactoredSmallQRawDFT
