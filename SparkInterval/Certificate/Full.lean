import SparkInterval.Certificate.Expression

/-!
# Full mathematical result certificates

A `FullCertificate` carries every input row and every claimed output interval.
The Boolean checker independently decodes each binary64 word, reevaluates the
full expression over exact rational intervals, and accepts a claimed output
only when it encloses that exact result.

The soundness theorem is over arbitrary real selections from all input and
constant intervals.  Consequently an accepted certificate is mathematical
evidence even when it was produced by an untrusted GPU or host.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

def maxVariableCount : Nat := 65536
def maxArithmeticCostPerRow : Nat := 4096
def maxTotalArithmeticWork : Nat := 10000000

/-- Self-contained full result data. Hash strings identify the originating
wire objects; exact recomputation/binding is performed by the serialized
parser. The direct mathematical checker validates their spelling and checks
all embedded data, so containment soundness does not rely on collision
resistance. -/
structure FullCertificate where
  variableCount : Nat
  expression : CertExpr
  rows : Array (Array RawInterval)
  results : Array RawInterval
  batchHash : String
  resultHash : String
  deriving BEq, DecidableEq, Repr

namespace FullCertificate

private def isLowerHexDigit (character : Char) : Bool :=
  ('0' ≤ character && character ≤ '9') ||
    ('a' ≤ character && character ≤ 'f')

/-- Validate the canonical spelling of a SHA-256 digest.  Hash recomputation
from canonical JSON belongs to the wire-format module. -/
def validDigest (digest : String) : Bool :=
  digest.length == 64 && digest.toList.all isLowerHexDigit

/-- Decode one complete input row. -/
def decodeRow (variableCount : Nat) (row : Array RawInterval) :
    Option (Array RatInterval) :=
  if row.size != variableCount then
    none
  else
    row.mapM RawInterval.decodeFinite

/-- Check a single input/output pair. -/
def checkRow (variableCount : Nat) (expression : CertExpr)
    (row : Array RawInterval) (claimed : RawInterval) : Bool :=
  match decodeRow variableCount row with
  | none => false
  | some intervalEnv =>
      match expression.eval intervalEnv with
      | none => false
      | some exact =>
          match claimed.decodeOutput with
          | none => false
          | some output => output.encloses exact

private def checkedAt (certificate : FullCertificate) (index : Nat) : Bool :=
  match certificate.rows[index]?, certificate.results[index]? with
  | some row, some result =>
      checkRow certificate.variableCount certificate.expression row result
  | _, _ => false

def rowsCheck (certificate : FullCertificate) : Bool :=
  (List.range certificate.rows.size).all certificate.checkedAt

/-- Fail before exact evaluation when a compact expression would cause
unbounded rational growth or when the row/expression product is impractical
for the non-streaming full checker. -/
def resourceCheck (certificate : FullCertificate) : Bool :=
  let cost := certificate.expression.arithmeticCostUpTo maxArithmeticCostPerRow
  decide (cost ≤ maxArithmeticCostPerRow) &&
    decide (certificate.rows.size * cost ≤ maxTotalArithmeticWork)

/-- Independently check the complete embedded batch and every result row. -/
def check (certificate : FullCertificate) : Bool :=
  validDigest certificate.batchHash &&
  validDigest certificate.resultHash &&
  decide (certificate.variableCount ≤ maxVariableCount) &&
  !certificate.rows.isEmpty &&
  certificate.rows.size == certificate.results.size &&
  certificate.resourceCheck &&
  certificate.rowsCheck

/-- A selected real environment and result for one certificate row. -/
def RowRealizes (certificate : FullCertificate) (index : Nat)
    (value : ℝ) : Prop :=
  ∃ rawRow intervalEnv realEnv,
    certificate.rows[index]? = some rawRow ∧
    decodeRow certificate.variableCount rawRow = some intervalEnv ∧
    CertExpr.EnvironmentsCorrespond realEnv intervalEnv ∧
    certificate.expression.Realizes realEnv value

/-- The claimed output at `index` decodes and contains `value`. -/
def ResultContains (certificate : FullCertificate) (index : Nat)
    (value : ℝ) : Prop :=
  ∃ rawOutput output,
    certificate.results[index]? = some rawOutput ∧
    rawOutput.decodeOutput = some output ∧
    output.ContainsReal value

private theorem rowsCheck_at {certificate : FullCertificate}
    (hcheck : certificate.rowsCheck = true) {index : Nat}
    (hindex : index < certificate.rows.size) :
    certificate.checkedAt index = true := by
  exact (List.all_eq_true.mp hcheck) index (List.mem_range.mpr hindex)

/-- Every accepted row's claimed output contains every real value realized by
that row's interval inputs and the certificate expression. -/
theorem check_sound {certificate : FullCertificate}
    (hcheck : certificate.check = true) {index : Nat}
    (hindex : index < certificate.rows.size) {value : ℝ}
    (hreal : certificate.RowRealizes index value) :
    certificate.ResultContains index value := by
  have hrows : certificate.rowsCheck = true := by
    simp only [check, Bool.and_eq_true] at hcheck
    exact hcheck.2
  have hchecked := rowsCheck_at hrows hindex
  rcases hreal with
    ⟨rawRow, intervalEnv, realEnv, hrow, hdecode, henv, hexpr⟩
  unfold checkedAt at hchecked
  rw [hrow] at hchecked
  cases hresult : certificate.results[index]? with
  | none => simp [hresult] at hchecked
  | some rawOutput =>
      cases heval : certificate.expression.eval intervalEnv with
      | none => simp [checkRow, hdecode, hresult, heval] at hchecked
      | some exact =>
          cases houtput : rawOutput.decodeOutput with
          | none =>
              simp [checkRow, hdecode, hresult, heval, houtput] at hchecked
          | some output =>
              have hcontainsExact : exact.ContainsReal value :=
                CertExpr.eval_sound henv hexpr heval
              have hcontainsOutput : output.ContainsReal value :=
                OutputInterval.encloses_containsReal (by
                  simpa [checkRow, hdecode, hresult, heval, houtput] using hchecked)
                  hcontainsExact
              exact ⟨rawOutput, output, hresult, houtput, hcontainsOutput⟩

/-- If a claimed output also decodes as a finite rational interval, the
generic extended-output containment theorem specializes to ordinary rational
interval containment. -/
theorem resultContains_of_decodeFinite
    {certificate : FullCertificate} {index : Nat} {value : ℝ}
    {raw : RawInterval} {result : RatInterval}
    (hraw : certificate.results[index]? = some raw)
    (hdecode : raw.decodeFinite = some result)
    (hcontains : certificate.ResultContains index value) :
    result.ContainsReal value := by
  rcases hcontains with
    ⟨rawOutput, output, hrawOutput, hdecodeOutput, houtputContains⟩
  rw [hraw] at hrawOutput
  simp only [Option.some.injEq] at hrawOutput
  subst rawOutput
  rw [RawInterval.decodeOutput_of_decodeFinite hdecode] at hdecodeOutput
  simp only [Option.some.injEq] at hdecodeOutput
  subst output
  exact RawInterval.finiteOutput_containsReal_iff.mp houtputContains

private def upperCheckedAt (certificate : FullCertificate) (bound : ℚ)
    (index : Nat) : Bool :=
  match certificate.results[index]? with
  | none => false
  | some rawOutput =>
      match rawOutput.decodeOutput with
      | none => false
      | some output => output.upperAtMost bound

def upperRowsCheck (certificate : FullCertificate) (bound : ℚ) : Bool :=
  (List.range certificate.rows.size).all (certificate.upperCheckedAt bound)

/-- Check the full certificate and additionally require every claimed upper
endpoint to be finite and no greater than the supplied finite binary64 word. -/
def checkUpperBound (certificate : FullCertificate) (boundBits : Nat) : Bool :=
  certificate.check &&
    match Binary64.decodeFinite boundBits with
    | none => false
    | some bound => certificate.upperRowsCheck bound

private theorem upperRowsCheck_at {certificate : FullCertificate} {bound : ℚ}
    (hcheck : certificate.upperRowsCheck bound = true) {index : Nat}
    (hindex : index < certificate.rows.size) :
    certificate.upperCheckedAt bound index = true := by
  exact (List.all_eq_true.mp hcheck) index (List.mem_range.mpr hindex)

private theorem upperRowsCheck_output {certificate : FullCertificate} {bound : ℚ}
    (hcheck : certificate.upperRowsCheck bound = true) {index : Nat}
    (hindex : index < certificate.rows.size)
    {rawOutput : RawInterval} {output : OutputInterval}
    (hraw : certificate.results[index]? = some rawOutput)
    (houtput : rawOutput.decodeOutput = some output) :
    output.upperAtMost bound = true := by
  have hat := upperRowsCheck_at hcheck hindex
  simpa [upperCheckedAt, hraw, houtput] using hat

/-- An accepted upper-bound certificate proves the bound for every arbitrary
real result realized by every checked row. -/
theorem checkUpperBound_sound {certificate : FullCertificate}
    {boundBits : Nat} {bound : ℚ}
    (hbound : Binary64.decodeFinite boundBits = some bound)
    (hcheck : certificate.checkUpperBound boundBits = true)
    {index : Nat} (hindex : index < certificate.rows.size)
    {value : ℝ} (hreal : certificate.RowRealizes index value) :
    value ≤ (bound : ℝ) := by
  simp only [checkUpperBound, Bool.and_eq_true] at hcheck
  have hfull : certificate.check = true := by
    exact hcheck.1
  have huppers : certificate.upperRowsCheck bound = true := by
    rw [hbound] at hcheck
    simpa using hcheck.2
  rcases check_sound hfull hindex hreal with
    ⟨rawOutput, output, hraw, houtput, hcontains⟩
  exact OutputInterval.upperAtMost_sound
    (upperRowsCheck_output huppers hindex hraw houtput) hcontains

/-! ## Aggregate upper bounds

This aggregate theorem still retains and checks the complete full certificate;
it is not a compressed-certificate mode. It replaces per-row use sites with
one rational bound on their sum and is directly useful for finite Dirichlet
sums such as the partial sum in the zeta tutorial.
-/

private def finiteUpperCheckedAt (certificate : FullCertificate)
    (index : Nat) : Bool :=
  match certificate.results[index]? with
  | none => false
  | some rawOutput =>
      match rawOutput.decodeOutput with
      | none => false
      | some output => output.hi.finite?.isSome

def finiteUpperRowsCheck (certificate : FullCertificate) : Bool :=
  (List.range certificate.rows.size).all certificate.finiteUpperCheckedAt

/-- The rational claimed upper endpoint at `index`, or zero outside the
finite-success path.  `finiteUpperRowsCheck` makes the default unreachable in
accepted aggregate certificates. -/
def resultUpperAt (certificate : FullCertificate) (index : Nat) : ℚ :=
  match certificate.results[index]? with
  | none => 0
  | some rawOutput =>
      match rawOutput.decodeOutput with
      | none => 0
      | some output => output.hi.finite?.getD 0

/-- Exact rational sum of all claimed finite upper endpoints. -/
def resultUpperSum (certificate : FullCertificate) : ℚ :=
  ∑ index : Fin certificate.rows.size, certificate.resultUpperAt index

/-- Check the full certificate, require finite result highs, and compare their
exact rational sum with an application-supplied rational bound. -/
def checkSumUpperBound (certificate : FullCertificate) (bound : ℚ) : Bool :=
  certificate.check && certificate.finiteUpperRowsCheck &&
    decide (certificate.resultUpperSum ≤ bound)

/-- One selected real result for every checked row. -/
def ValuesRealize (certificate : FullCertificate)
    (values : Fin certificate.rows.size → ℝ) : Prop :=
  ∀ index : Fin certificate.rows.size,
    certificate.RowRealizes index.1 (values index)

private theorem finiteUpperRowsCheck_at {certificate : FullCertificate}
    (hcheck : certificate.finiteUpperRowsCheck = true) {index : Nat}
    (hindex : index < certificate.rows.size) :
    certificate.finiteUpperCheckedAt index = true := by
  exact (List.all_eq_true.mp hcheck) index (List.mem_range.mpr hindex)

private theorem realized_le_resultUpperAt {certificate : FullCertificate}
    (hfull : certificate.check = true)
    (hfinite : certificate.finiteUpperRowsCheck = true)
    {index : Nat} (hindex : index < certificate.rows.size)
    {value : ℝ} (hreal : certificate.RowRealizes index value) :
    value ≤ (certificate.resultUpperAt index : ℝ) := by
  rcases check_sound hfull hindex hreal with
    ⟨rawOutput, output, hraw, houtput, hcontains⟩
  have hfiniteAt := finiteUpperRowsCheck_at hfinite hindex
  unfold finiteUpperCheckedAt at hfiniteAt
  rw [hraw] at hfiniteAt
  simp only at hfiniteAt
  rw [houtput] at hfiniteAt
  cases hhi : output.hi with
  | negInf => simp [RatEndpoint.finite?, hhi] at hfiniteAt
  | posInf => simp [RatEndpoint.finite?, hhi] at hfiniteAt
  | finite upper =>
      have hvalue : value ≤ (upper : ℝ) := by
        simpa [OutputInterval.ContainsReal, RatEndpoint.IsUpperBound, hhi] using
          hcontains.2
      simpa [resultUpperAt, hraw, houtput, RatEndpoint.finite?, hhi] using hvalue

/-- If the aggregate checker accepts, the sum of one arbitrary real result
realized by each row is at most the supplied exact rational bound. -/
theorem checkSumUpperBound_sound {certificate : FullCertificate} {bound : ℚ}
    (hcheck : certificate.checkSumUpperBound bound = true)
    (values : Fin certificate.rows.size → ℝ)
    (hvalues : certificate.ValuesRealize values) :
    (∑ index, values index) ≤ (bound : ℝ) := by
  simp only [checkSumUpperBound, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  have hpointwise : ∀ index : Fin certificate.rows.size,
      values index ≤ (certificate.resultUpperAt index : ℝ) := by
    intro index
    exact realized_le_resultUpperAt hcheck.1.1 hcheck.1.2 index.isLt (hvalues index)
  calc
    (∑ index, values index) ≤
        ∑ index : Fin certificate.rows.size,
          (certificate.resultUpperAt index : ℝ) :=
      Finset.sum_le_sum fun index _ ↦ hpointwise index
    _ = (certificate.resultUpperSum : ℝ) := by
      simp [resultUpperSum]
    _ ≤ (bound : ℝ) := Rat.cast_le.mpr hcheck.2

end FullCertificate

end SparkInterval.Certificate
