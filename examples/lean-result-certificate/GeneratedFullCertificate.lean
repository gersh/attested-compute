import SparkInterval.Certificate

/-!
This file is generated deterministically by
`tools/generate_lean_result_certificate.py`. Do not edit it by hand.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000
set_option cbv.maxSteps 10000000
set_option maxHeartbeats 2000000
set_option exponentiation.threshold 2048

namespace SparkInterval.GeneratedCertificate.C_b4ba4bc319743cf65a486c216897268e0a98107ea635404fa3f7825305755ba9_B_4010000000000001_M_kernel

def generatorId : String := "sparkinterval.lean_result_certificate.v1"
def decisionMode : String := "kernel"
def sourceSchemaVersion : Nat := 1
def sourceCertificateKind : String := "sparkinterval_reference_certificate"
def sourceBatchKind : String := "sparkinterval_reference_batch"
def sourceResultKind : String := "sparkinterval_reference_result"
def sourceAlgorithmId : String := "sparkinterval.binary64_interval_expr.v1"
def sourceCertificateSha256 : String := "b4ba4bc319743cf65a486c216897268e0a98107ea635404fa3f7825305755ba9"
def sourceBatchSha256 : String := "05fcf4357bfd5a8eb20a82a5ed9b2cf9dc8f5ebd159754c3a64c6f02fa45e656"
def sourceResultSha256 : String := "8fa1875dec7859395b213714e8a19140dcc6d9d8e4b4a1f4c278aa052c946eca"
def sourceCertificateJson : String :=
  r#"{"batch":{"algorithm":"sparkinterval.binary64_interval_expr.v1","expression":{"left":{"index":0,"op":"var"},"op":"mul","right":{"left":{"op":"const","value":{"hi":"3ff0000000000000","lo":"3ff0000000000000"}},"op":"add","right":{"index":1,"op":"var"}}},"kind":"sparkinterval_reference_batch","rows":[[{"hi":"3ff0000000000000","lo":"3ff0000000000000"},{"hi":"4000000000000000","lo":"4000000000000000"}],[{"hi":"3ff0000000000001","lo":"3ff0000000000000"},{"hi":"4008000000000000","lo":"4000000000000000"}]],"schema_version":1,"variable_count":2},"batch_sha256":"05fcf4357bfd5a8eb20a82a5ed9b2cf9dc8f5ebd159754c3a64c6f02fa45e656","kind":"sparkinterval_reference_certificate","result":{"algorithm":"sparkinterval.binary64_interval_expr.v1","batch_sha256":"05fcf4357bfd5a8eb20a82a5ed9b2cf9dc8f5ebd159754c3a64c6f02fa45e656","kind":"sparkinterval_reference_result","rows":[{"hi":"4008000000000000","lo":"4008000000000000"},{"hi":"4010000000000001","lo":"4008000000000000"}],"schema_version":1},"result_sha256":"8fa1875dec7859395b213714e8a19140dcc6d9d8e4b4a1f4c278aa052c946eca","schema_version":1}"#
def applicationUpperBoundHex : String := "4010000000000001"
def applicationUpperBoundBits : Nat := 0x4010000000000001
def applicationUpperBound : ℚ :=
  SparkInterval.Certificate.Binary64.finiteValue applicationUpperBoundBits
def certificateUpperBoundHex : String := "4010000000000001"
def certificateUpperBoundBits : Nat := 0x4010000000000001
def certificateUpperBound : ℚ :=
  SparkInterval.Certificate.Binary64.finiteValue certificateUpperBoundBits

def certificate : SparkInterval.Certificate.FullCertificate where
  variableCount := 2
  expression :=
    (.mul
      (.var 0)
      (.add
        (.const { lo := 0x3ff0000000000000, hi := 0x3ff0000000000000 })
        (.var 1)))
  rows :=
    #[
      #[
        { lo := 0x3ff0000000000000, hi := 0x3ff0000000000000 },
        { lo := 0x4000000000000000, hi := 0x4000000000000000 },
      ],
      #[
        { lo := 0x3ff0000000000000, hi := 0x3ff0000000000001 },
        { lo := 0x4000000000000000, hi := 0x4008000000000000 },
      ],
    ]
  results :=
    #[
      { lo := 0x4008000000000000, hi := 0x4008000000000000 },
      { lo := 0x4008000000000000, hi := 0x4010000000000001 },
    ]
  batchHash := sourceBatchSha256
  resultHash := sourceResultSha256

theorem source_certificate_sha256_check :
    SparkInterval.Certificate.SHA256.digestString sourceCertificateJson =
      sourceCertificateSha256 := by
  native_decide

theorem source_certificate_parse :
    SparkInterval.Certificate.parseCanonicalFullCertificate
      sourceCertificateJson = .ok certificate := by
  native_decide

theorem certificate_check : certificate.check = true := by
  decide_cbv

theorem certificate_upper_bound_check :
    certificate.checkUpperBound certificateUpperBoundBits = true := by
  unfold SparkInterval.Certificate.FullCertificate.checkUpperBound
  rw [certificate_check]
  decide_cbv

theorem certificate_upper_bound_decode :
    SparkInterval.Certificate.Binary64.decodeFinite
      certificateUpperBoundBits = some certificateUpperBound := by
  rfl

theorem application_upper_bound_decode :
    SparkInterval.Certificate.Binary64.decodeFinite
      applicationUpperBoundBits = some applicationUpperBound := by
  rfl

theorem certificate_upper_bound_le_application :
    certificateUpperBound ≤ applicationUpperBound := by
  norm_num [certificateUpperBound, certificateUpperBoundBits,
    applicationUpperBound, applicationUpperBoundBits,
    SparkInterval.Certificate.Binary64.finiteValue,
    SparkInterval.Certificate.Binary64.exponentBits,
    SparkInterval.Certificate.Binary64.fractionBits,
    SparkInterval.Certificate.Binary64.signBit,
    SparkInterval.Certificate.Binary64.fractionModulus,
    SparkInterval.Certificate.Binary64.exponentModulus,
    SparkInterval.Certificate.Binary64.signThreshold, div_le_iff₀]

theorem application_upper_bound_sound
    {index : Nat} (hindex : index < certificate.rows.size)
    {value : ℝ} (hreal : certificate.RowRealizes index value) :
    value ≤ (applicationUpperBound : ℝ) := by
  exact (SparkInterval.Certificate.FullCertificate.checkUpperBound_sound
    certificate_upper_bound_decode certificate_upper_bound_check hindex hreal).trans
      (Rat.cast_le.mpr certificate_upper_bound_le_application)

#print axioms application_upper_bound_sound

def certificateResultUpperSum : ℚ := certificate.resultUpperSum

theorem certificate_sum_check :
    certificate.checkSumUpperBound certificateResultUpperSum = true := by
  unfold SparkInterval.Certificate.FullCertificate.checkSumUpperBound
  rw [certificate_check]
  decide_cbv

theorem certificate_sum_upper_bound_sound
    (values : Fin certificate.rows.size → ℝ)
    (hvalues : certificate.ValuesRealize values) :
    (∑ index, values index) ≤ (certificateResultUpperSum : ℝ) := by
  exact SparkInterval.Certificate.FullCertificate.checkSumUpperBound_sound
    certificate_sum_check values hvalues

#print axioms certificate_sum_upper_bound_sound

theorem application_theorem :
    SparkInterval.Certificate.SerializedUpperBoundTheorem
      sourceCertificateJson applicationUpperBoundBits := by
  intro parsedCertificate parsedBound hparse hbound index hindex value hreal
  have hcertificate : parsedCertificate = certificate :=
    Except.ok.inj (hparse.symm.trans source_certificate_parse)
  subst parsedCertificate
  have hboundEq : parsedBound = applicationUpperBound :=
    Option.some.inj (hbound.symm.trans application_upper_bound_decode)
  subst parsedBound
  exact application_upper_bound_sound hindex hreal

#print axioms application_theorem

theorem application_sum_theorem :
    SparkInterval.Certificate.SerializedSumUpperBoundTheorem
      sourceCertificateJson certificateResultUpperSum := by
  intro parsedCertificate hparse values hvalues
  have hcertificate : parsedCertificate = certificate :=
    Except.ok.inj (hparse.symm.trans source_certificate_parse)
  subst parsedCertificate
  exact certificate_sum_upper_bound_sound values hvalues

#print axioms application_sum_theorem

end SparkInterval.GeneratedCertificate.C_b4ba4bc319743cf65a486c216897268e0a98107ea635404fa3f7825305755ba9_B_4010000000000001_M_kernel
