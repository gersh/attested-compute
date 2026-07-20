import SparkInterval.Certificate.RatInterval

/-!
# Executable binary64 decoding for result certificates

Certificate endpoints are raw 64-bit words represented by `Nat`.  This module
decodes finite words to exact rational values, and result endpoints to the
extended rational line.  No Lean runtime `Float` operation is involved.

Inputs and expression constants must decode to finite intervals.  Claimed
result intervals may additionally use either infinity, but never a NaN.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

/-- A raw interval in the canonical wire representation. -/
structure RawInterval where
  lo : Nat
  hi : Nat
  deriving BEq, DecidableEq, Repr

namespace Binary64

def wordLimit : Nat := 2 ^ 64
def signThreshold : Nat := 2 ^ 63
def fractionModulus : Nat := 2 ^ 52
def exponentModulus : Nat := 2 ^ 11
def exponentAllOnes : Nat := 2047

def fractionBits (raw : Nat) : Nat :=
  raw % fractionModulus

def exponentBits (raw : Nat) : Nat :=
  (raw / fractionModulus) % exponentModulus

def signBit (raw : Nat) : Bool :=
  decide (signThreshold ≤ raw)

/-- The exact rational value described by the fields of a finite word.

The caller is responsible for first excluding the all-ones exponent.  Keeping
this field calculation separate makes both finite and extended decoding small
and executable.
-/
def finiteValue (raw : Nat) : ℚ :=
  let exponent := exponentBits raw
  let significand :=
    if exponent = 0 then fractionBits raw
    else fractionModulus + fractionBits raw
  let power : Int :=
    if exponent = 0 then -1074
    else (exponent : Int) - 1075
  let magnitude : ℚ := (significand : ℚ) * (2 : ℚ) ^ power
  if signBit raw then -magnitude else magnitude

/-- Decode a finite binary64 word to its exact rational value.

Words outside 64 bits, infinities, and NaNs are rejected.  Both signed-zero
encodings decode to the rational number zero.
-/
def decodeFinite (raw : Nat) : Option ℚ :=
  if raw < wordLimit && exponentBits raw != exponentAllOnes then
    some (finiteValue raw)
  else
    none

@[simp] theorem decodeFinite_eq_some_iff (raw : Nat) (value : ℚ) :
    decodeFinite raw = some value ↔
      raw < wordLimit ∧ exponentBits raw ≠ exponentAllOnes ∧
        finiteValue raw = value := by
  simp [decodeFinite, Bool.and_eq_true, decide_eq_true_eq, and_assoc]

end Binary64

/-- Extended rational endpoints admitted for claimed result intervals. -/
inductive RatEndpoint where
  | negInf
  | finite (value : ℚ)
  | posInf
  deriving BEq, DecidableEq, Repr

namespace RatEndpoint

/-- Order on the extended rational endpoints. -/
def leProp : RatEndpoint → RatEndpoint → Prop
  | .negInf, _ => True
  | _, .posInf => True
  | .finite left, .finite right => left ≤ right
  | .finite _, .negInf => False
  | .posInf, .negInf => False
  | .posInf, .finite _ => False

instance : _root_.LE RatEndpoint := ⟨RatEndpoint.leProp⟩

instance (left right : RatEndpoint) : Decidable (left ≤ right) := by
  change Decidable (leProp left right)
  cases left <;> cases right <;> dsimp only [leProp] <;> infer_instance

def le (left right : RatEndpoint) : Bool :=
  decide (left ≤ right)

@[simp] theorem le_eq_true {left right : RatEndpoint} :
    left.le right = true ↔ left ≤ right := by
  simp [le]

/-- `endpoint` is a lower bound for the embedded real `value`. -/
def IsLowerBound : RatEndpoint → ℝ → Prop
  | .negInf, _ => True
  | .finite endpoint, value => (endpoint : ℝ) ≤ value
  | .posInf, _ => False

/-- `endpoint` is an upper bound for the embedded real `value`. -/
def IsUpperBound : RatEndpoint → ℝ → Prop
  | .negInf, _ => False
  | .finite endpoint, value => value ≤ (endpoint : ℝ)
  | .posInf, _ => True

def lowerLE (endpoint : RatEndpoint) (value : ℚ) : Bool :=
  match endpoint with
  | .negInf => true
  | .finite endpoint => decide (endpoint ≤ value)
  | .posInf => false

def upperGE (endpoint : RatEndpoint) (value : ℚ) : Bool :=
  match endpoint with
  | .negInf => false
  | .finite endpoint => decide (value ≤ endpoint)
  | .posInf => true

theorem lowerLE_sound {endpoint : RatEndpoint} {lower : ℚ} {value : ℝ}
    (hbound : endpoint.lowerLE lower = true)
    (hvalue : (lower : ℝ) ≤ value) :
    endpoint.IsLowerBound value := by
  cases endpoint with
  | negInf => trivial
  | posInf => simp [lowerLE] at hbound
  | finite endpoint =>
      simp only [lowerLE, decide_eq_true_eq] at hbound
      exact (Rat.cast_le.mpr hbound).trans hvalue

theorem upperGE_sound {endpoint : RatEndpoint} {upper : ℚ} {value : ℝ}
    (hbound : endpoint.upperGE upper = true)
    (hvalue : value ≤ (upper : ℝ)) :
    endpoint.IsUpperBound value := by
  cases endpoint with
  | negInf => simp [upperGE] at hbound
  | posInf => trivial
  | finite endpoint =>
      simp only [upperGE, decide_eq_true_eq] at hbound
      exact hvalue.trans (Rat.cast_le.mpr hbound)

def finite? : RatEndpoint → Option ℚ
  | .finite value => some value
  | _ => none

end RatEndpoint

namespace Binary64

/-- Decode a non-NaN result endpoint, retaining either infinity. -/
def decodeEndpoint (raw : Nat) : Option RatEndpoint :=
  if raw ≥ wordLimit then
    none
  else if exponentBits raw = exponentAllOnes then
    if fractionBits raw ≠ 0 then
      none
    else if signBit raw then
      some .negInf
    else
      some .posInf
  else
    some (.finite (finiteValue raw))

theorem decodeEndpoint_of_decodeFinite {raw : Nat} {value : ℚ}
    (h : decodeFinite raw = some value) :
    decodeEndpoint raw = some (.finite value) := by
  rw [decodeFinite_eq_some_iff] at h
  rcases h with ⟨hrange, hexponent, rfl⟩
  simp [decodeEndpoint, Nat.not_le.mpr hrange, hexponent]

end Binary64

/-- A decoded, non-NaN result interval with possibly infinite endpoints. -/
structure OutputInterval where
  lo : RatEndpoint
  hi : RatEndpoint
  deriving BEq, DecidableEq, Repr

namespace OutputInterval

def IsValid (interval : OutputInterval) : Prop :=
  interval.lo ≤ interval.hi

instance (interval : OutputInterval) : Decidable interval.IsValid := by
  unfold IsValid
  infer_instance

def isValid (interval : OutputInterval) : Bool :=
  decide interval.IsValid

@[simp] theorem isValid_eq_true {interval : OutputInterval} :
    interval.isValid = true ↔ interval.IsValid := by
  simp [isValid]

def ContainsReal (interval : OutputInterval) (value : ℝ) : Prop :=
  interval.lo.IsLowerBound value ∧ interval.hi.IsUpperBound value

/-- Check that an extended output interval contains a finite rational one. -/
def encloses (output : OutputInterval) (exact : RatInterval) : Bool :=
  output.isValid && exact.isValid &&
    output.lo.lowerLE exact.lo && output.hi.upperGE exact.hi

theorem encloses_containsReal {output : OutputInterval} {exact : RatInterval}
    (hencloses : output.encloses exact = true) {value : ℝ}
    (hvalue : exact.ContainsReal value) :
    output.ContainsReal value := by
  simp only [encloses, Bool.and_eq_true] at hencloses
  exact ⟨RatEndpoint.lowerLE_sound hencloses.1.2 hvalue.1,
    RatEndpoint.upperGE_sound hencloses.2 hvalue.2⟩

/-- Require the claimed upper endpoint to be finite and at most `bound`. -/
def upperAtMost (output : OutputInterval) (bound : ℚ) : Bool :=
  match output.hi with
  | .finite upper => decide (upper ≤ bound)
  | _ => false

theorem upperAtMost_sound {output : OutputInterval} {bound : ℚ}
    (hbound : output.upperAtMost bound = true) {value : ℝ}
    (hvalue : output.ContainsReal value) :
    value ≤ (bound : ℝ) := by
  cases hhi : output.hi with
  | negInf => simp [upperAtMost, hhi] at hbound
  | posInf => simp [upperAtMost, hhi] at hbound
  | finite upper =>
      simp only [upperAtMost, hhi, decide_eq_true_eq] at hbound
      have hvalueUpper : value ≤ (upper : ℝ) := by
        simpa [ContainsReal, hhi, RatEndpoint.IsUpperBound] using hvalue.2
      exact hvalueUpper.trans (Rat.cast_le.mpr hbound)

end OutputInterval

namespace RawInterval

/-- Decode an input/constant interval and require finite ordered endpoints. -/
def decodeFinite (raw : RawInterval) : Option RatInterval := do
  let lo ← Binary64.decodeFinite raw.lo
  let hi ← Binary64.decodeFinite raw.hi
  let result : RatInterval := { lo, hi }
  if result.isValid then some result else none

/-- Decode a claimed result interval, permitting either infinity but no NaN. -/
def decodeOutput (raw : RawInterval) : Option OutputInterval := do
  let lo ← Binary64.decodeEndpoint raw.lo
  let hi ← Binary64.decodeEndpoint raw.hi
  let result : OutputInterval := { lo, hi }
  if result.isValid then some result else none

theorem decodeFinite_isValid {raw : RawInterval} {result : RatInterval}
    (hdecode : raw.decodeFinite = some result) : result.IsValid := by
  unfold decodeFinite at hdecode
  cases hlo : Binary64.decodeFinite raw.lo with
  | none => simp [hlo] at hdecode
  | some lo =>
      cases hhi : Binary64.decodeFinite raw.hi with
      | none => simp [hlo, hhi] at hdecode
      | some hi =>
          by_cases hvalid : ({ lo, hi } : RatInterval).isValid = true
          · simp [hlo, hhi, hvalid] at hdecode
            subst result
            exact RatInterval.isValid_eq_true.mp hvalid
          · simp [hlo, hhi, hvalid] at hdecode

/-- A finite interval decodes to the corresponding pair of finite extended
endpoints in the more permissive output decoder. -/
theorem decodeOutput_of_decodeFinite {raw : RawInterval} {result : RatInterval}
    (hdecode : raw.decodeFinite = some result) :
    raw.decodeOutput = some {
      lo := .finite result.lo
      hi := .finite result.hi
    } := by
  unfold decodeFinite at hdecode
  cases hlo : Binary64.decodeFinite raw.lo with
  | none => simp [hlo] at hdecode
  | some lo =>
      cases hhi : Binary64.decodeFinite raw.hi with
      | none => simp [hlo, hhi] at hdecode
      | some hi =>
          by_cases hvalid : ({ lo, hi } : RatInterval).isValid = true
          · simp [hlo, hhi, hvalid] at hdecode
            subst result
            unfold decodeOutput
            rw [Binary64.decodeEndpoint_of_decodeFinite hlo,
              Binary64.decodeEndpoint_of_decodeFinite hhi]
            have hle : lo ≤ hi := by
              simpa [RatInterval.isValid] using hvalid
            have hout :
                ({ lo := .finite lo, hi := .finite hi } :
                  OutputInterval).isValid = true := by
              unfold OutputInterval.isValid OutputInterval.IsValid
              change decide (lo ≤ hi) = true
              exact decide_eq_true_eq.mpr hle
            change (if
                ({ lo := .finite lo, hi := .finite hi } :
                  OutputInterval).isValid = true
              then some ({
                lo := .finite lo
                hi := .finite hi
              } : OutputInterval)
              else none) = some ({
                lo := .finite lo
                hi := .finite hi
              } : OutputInterval)
            rw [hout]
            rfl
          · simp [hlo, hhi, hvalid] at hdecode

/-- On finite endpoints, `OutputInterval.ContainsReal` is exactly the ordinary
rational-interval containment proposition. -/
@[simp] theorem finiteOutput_containsReal_iff
    {interval : RatInterval} {value : ℝ} :
    ({ lo := .finite interval.lo, hi := .finite interval.hi } :
      OutputInterval).ContainsReal value ↔ interval.ContainsReal value := by
  rfl

theorem decodeOutput_isValid {raw : RawInterval} {result : OutputInterval}
    (hdecode : raw.decodeOutput = some result) : result.IsValid := by
  unfold decodeOutput at hdecode
  cases hlo : Binary64.decodeEndpoint raw.lo with
  | none => simp [hlo] at hdecode
  | some lo =>
      cases hhi : Binary64.decodeEndpoint raw.hi with
      | none => simp [hlo, hhi] at hdecode
      | some hi =>
          simp [hlo, hhi] at hdecode
          rcases hdecode with ⟨hvalid, heq⟩
          rw [← heq]
          exact hvalid

end RawInterval

end SparkInterval.Certificate
