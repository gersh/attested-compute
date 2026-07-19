import SparkInterval.Certificate

/-! Direct rejection tests for the Phase 8 Lean wire parser and checker. -/

set_option autoImplicit false

namespace SparkInterval.Tests.CertificateFormat

open SparkInterval.Certificate

def valid : String :=
  r#"{"batch":{"algorithm":"sparkinterval.binary64_interval_expr.v1","expression":{"index":0,"op":"var"},"kind":"sparkinterval_reference_batch","rows":[[{"hi":"3ff0000000000000","lo":"3ff0000000000000"}]],"schema_version":1,"variable_count":1},"batch_sha256":"ea395d8a7142fa175f516f663fe58e753133789a56cb1c47acdd2400b62cd772","kind":"sparkinterval_reference_certificate","result":{"algorithm":"sparkinterval.binary64_interval_expr.v1","batch_sha256":"ea395d8a7142fa175f516f663fe58e753133789a56cb1c47acdd2400b62cd772","kind":"sparkinterval_reference_result","rows":[{"hi":"3ff0000000000000","lo":"3ff0000000000000"}],"schema_version":1},"result_sha256":"e626cd4f4d41cdd76b2a4868d0f616337972690c8f916540ce18f9d17be3998e","schema_version":1}"#

/-- Structurally and cryptographically valid, but the rehashed claimed point
`2` does not contain the exact result `1`. -/
def rehashedWrongResult : String :=
  r#"{"batch":{"algorithm":"sparkinterval.binary64_interval_expr.v1","expression":{"index":0,"op":"var"},"kind":"sparkinterval_reference_batch","rows":[[{"hi":"3ff0000000000000","lo":"3ff0000000000000"}]],"schema_version":1,"variable_count":1},"batch_sha256":"ea395d8a7142fa175f516f663fe58e753133789a56cb1c47acdd2400b62cd772","kind":"sparkinterval_reference_certificate","result":{"algorithm":"sparkinterval.binary64_interval_expr.v1","batch_sha256":"ea395d8a7142fa175f516f663fe58e753133789a56cb1c47acdd2400b62cd772","kind":"sparkinterval_reference_result","rows":[{"hi":"4000000000000000","lo":"4000000000000000"}],"schema_version":1},"result_sha256":"dedf6237209d103e9a5e5af35774d77d23951c20be76ad06212ea58329d5d38f","schema_version":1}"#

/-- This compact, fully rehashed input would expand `(1 + 2^-52)` to an
exact rational power of `64^5`. The parser must reject its symbolic arithmetic
cost before row evaluation. -/
def explosive : String :=
  r#"{"batch":{"algorithm":"sparkinterval.binary64_interval_expr.v1","expression":{"arg":{"arg":{"arg":{"arg":{"arg":{"index":0,"op":"var"},"exponent":64,"op":"pow_nat"},"exponent":64,"op":"pow_nat"},"exponent":64,"op":"pow_nat"},"exponent":64,"op":"pow_nat"},"exponent":64,"op":"pow_nat"},"kind":"sparkinterval_reference_batch","rows":[[{"hi":"3ff0000000000001","lo":"3ff0000000000001"}]],"schema_version":1,"variable_count":1},"batch_sha256":"e88a8ea2b10db29b0e7f958dbb18c7fb34e1b112961937d7237bf50eb1ad93e8","kind":"sparkinterval_reference_certificate","result":{"algorithm":"sparkinterval.binary64_interval_expr.v1","batch_sha256":"e88a8ea2b10db29b0e7f958dbb18c7fb34e1b112961937d7237bf50eb1ad93e8","kind":"sparkinterval_reference_result","rows":[{"hi":"3ff00000800001dc","lo":"3ff0000040000060"}],"schema_version":1},"result_sha256":"95647f3ea2fe95f43cf4b4d6410e33b1573abe85c7d5645b6697de635631eb70","schema_version":1}"#

def parseRejected (text : String) : Bool :=
  match parseCanonicalFullCertificate text with
  | .ok _ => false
  | .error _ => true

example : checkCanonicalFullCertificate valid = true := by
  native_decide

example : checkCanonicalFullCertificateSumUpperBound valid 1 = true := by
  native_decide

example : checkCanonicalFullCertificateSumUpperBound valid (1 / 2) = false := by
  native_decide

example : parseRejected rehashedWrongResult = false := by
  native_decide

example : checkCanonicalFullCertificate rehashedWrongResult = false := by
  native_decide

example : parseRejected (valid ++ "\n") = true := by
  native_decide

example : parseRejected
    (valid.replace
      "ea395d8a7142fa175f516f663fe58e753133789a56cb1c47acdd2400b62cd772"
      "0000000000000000000000000000000000000000000000000000000000000000") =
    true := by
  native_decide

example : parseRejected
    ("{\"schema_version\":1," ++ valid.drop 1) = true := by
  native_decide

example : parseRejected explosive = true := by
  native_decide

def excessivelyNestedJson : String :=
  String.ofList
    (List.replicate (maxCertificateJsonNesting + 1) '[' ++
      List.replicate (maxCertificateJsonNesting + 1) ']')

example : jsonNestingWithinLimit excessivelyNestedJson = false := by
  native_decide

example : parseRejected excessivelyNestedJson = true := by
  native_decide

#print axioms SparkInterval.Certificate.impliesSumTheorem

end SparkInterval.Tests.CertificateFormat
