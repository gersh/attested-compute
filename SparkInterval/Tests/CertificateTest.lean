import SparkInterval.Certificate

/-! Regression tests for the axiom-free full result-certificate checker. -/

set_option autoImplicit false

namespace SparkInterval.Tests.Certificate

open SparkInterval.Certificate

def zeroDigest : String :=
  "0000000000000000000000000000000000000000000000000000000000000000"

def one : RawInterval :=
  { lo := 0x3ff0000000000000, hi := 0x3ff0000000000000 }

def two : RawInterval :=
  { lo := 0x4000000000000000, hi := 0x4000000000000000 }

def three : RawInterval :=
  { lo := 0x4008000000000000, hi := 0x4008000000000000 }

def whole : RawInterval :=
  { lo := 0xfff0000000000000, hi := 0x7ff0000000000000 }

def addCertificate : FullCertificate := {
  variableCount := 2
  expression := .add (.var 0) (.var 1)
  rows := #[#[one, two]]
  results := #[three]
  batchHash := zeroDigest
  resultHash := zeroDigest
}

example : Binary64.decodeFinite 0x3ff0000000000000 = some 1 := by native_decide
example : Binary64.decodeFinite 0x4008000000000000 = some 3 := by native_decide
example : Binary64.decodeFinite 0x8000000000000000 = some 0 := by native_decide
example : Binary64.decodeFinite 0xbff0000000000000 = some (-1) := by native_decide
example : Binary64.decodeFinite 0x0000000000000001 =
    some ((2 : ℚ) ^ (-1074 : Int)) := by native_decide
example : Binary64.decodeFinite 0x7fefffffffffffff =
    some ((9007199254740991 : ℚ) * (2 : ℚ) ^ (971 : Int)) := by native_decide
example : Binary64.decodeFinite 0x7ff0000000000000 = none := by native_decide
example : Binary64.decodeFinite 0x7ff8000000000000 = none := by native_decide
example : Binary64.decodeFinite (2 ^ 64) = none := by native_decide
example : Binary64.decodeEndpoint 0xfff0000000000000 = some .negInf := by
  native_decide
example : Binary64.decodeEndpoint 0x7ff0000000000000 = some .posInf := by
  native_decide
theorem addCertificate_check_cbv : addCertificate.check = true := by
  decide_cbv
example : addCertificate.checkUpperBound 0x4008000000000000 = true := by
  native_decide
example : addCertificate.checkUpperBound 0x4000000000000000 = false := by
  native_decide

def narrowedCertificate : FullCertificate :=
  { addCertificate with results := #[two] }

example : narrowedCertificate.check = false := by native_decide

def infiniteCertificate : FullCertificate :=
  { addCertificate with results := #[whole] }

example : infiniteCertificate.check = true := by native_decide
example : infiniteCertificate.checkUpperBound 0x7fefffffffffffff = false := by
  native_decide

def pointRowsCertificate : FullCertificate := {
  variableCount := 1
  expression := .var 0
  rows := #[#[one], #[two]]
  results := #[one, two]
  batchHash := zeroDigest
  resultHash := zeroDigest
}

example : pointRowsCertificate.checkSumUpperBound 3 = true := by native_decide
example : pointRowsCertificate.checkSumUpperBound (5 / 2) = false := by
  native_decide

def fullOpsCertificate : FullCertificate := {
  variableCount := 3
  expression :=
    .max
      (.min
        (.abs
          (.neg
            (.sub
              (.add (.var 0) (.const one))
              (.mul (.var 1) (.powNat (.var 2) 2)))))
        (.div (.var 0) (.const two)))
      (.const one)
  rows := #[#[one, two, three]]
  results := #[one]
  batchHash := zeroDigest
  resultHash := zeroDigest
}

example : fullOpsCertificate.check = true := by native_decide

def crossesZero : RawInterval :=
  { lo := 0xbff0000000000000, hi := 0x3ff0000000000000 }

def rejectedDivisionCertificate : FullCertificate := {
  variableCount := 1
  expression := .div (.const one) (.var 0)
  rows := #[#[crossesZero]]
  results := #[whole]
  batchHash := zeroDigest
  resultHash := zeroDigest
}

example : rejectedDivisionCertificate.check = false := by native_decide

def explosiveExpression : CertExpr :=
  .powNat (.powNat (.powNat (.powNat (.powNat (.var 0) 64) 64) 64) 64) 64

def explosiveCertificate : FullCertificate :=
  { pointRowsCertificate with
    expression := explosiveExpression
    rows := #[#[one]]
    results := #[one] }

example :
    explosiveExpression.arithmeticCostUpTo maxArithmeticCostPerRow =
      maxArithmeticCostPerRow + 1 := by
  decide_cbv

/-- The resource guard short-circuits before attempting the enormous exact
rational exponentiation. -/
example : explosiveCertificate.check = false := by
  decide_cbv

example (values : Fin pointRowsCertificate.rows.size → ℝ)
    (hvalues : pointRowsCertificate.ValuesRealize values) :
    (∑ index, values index) ≤ (3 : ℝ) := by
  exact FullCertificate.checkSumUpperBound_sound (by native_decide) values hvalues

#print axioms FullCertificate.check_sound
#print axioms FullCertificate.checkUpperBound_sound
#print axioms FullCertificate.checkSumUpperBound_sound
#print axioms addCertificate_check_cbv

end SparkInterval.Tests.Certificate
