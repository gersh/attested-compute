import Lean.Data.Json
import SparkInterval.Certificate.Full
import SparkInterval.Certificate.SHA256

/-!
# Canonical full result-certificate parser

This is the Phase 8 parser for the existing self-contained Phase 3 reference
certificate.  Unlike the Phase 5 generator parser, it retains every input and
result row and accepts the complete expression language.  It rejects
noncanonical JSON, duplicate/extra fields, malformed or unordered binary64
endpoints, nonfinite inputs, invalid hashes, mismatched row counts, and
resource-limit violations before constructing `FullCertificate` data.

Hash checking is defense in depth.  The mathematical result does not rely on
SHA-256 collision resistance: `FullCertificate.check` independently decodes
and recomputes every complete row using exact rational interval arithmetic.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

open Lean

def maxCertificateBytes : Nat := 512 * 1024 * 1024
def maxCertificateVariables : Nat := 65536
def maxCertificateRows : Nat := 1000000
def maxCertificateNodes : Nat := 100000
def maxCertificateDepth : Nat := 256
def maxCertificatePowExponent : Nat := 64
def maxCertificateJsonNesting : Nat := 300

private structure JsonScanState where
  depth : Nat := 0
  inString : Bool := false
  escaped : Bool := false
  valid : Bool := true

private def scanJsonChar (state : JsonScanState) (character : Char) : JsonScanState :=
  if !state.valid then
    state
  else if state.inString then
    if state.escaped then
      { state with escaped := false }
    else if character == '\\' then
      { state with escaped := true }
    else if character == '"' then
      { state with inString := false }
    else
      state
  else if character == '"' then
    { state with inString := true }
  else if character == '{' || character == '[' then
    let depth := state.depth + 1
    { state with depth, valid := decide (depth ≤ maxCertificateJsonNesting) }
  else if character == '}' || character == ']' then
    if state.depth = 0 then
      { state with valid := false }
    else
      { state with depth := state.depth - 1 }
  else
    state

/-- Cheap allocation-bounded preflight before invoking Lean's JSON parser. It
tracks nesting while respecting quoted/escaped delimiters. Full JSON syntax is
still decided by `Json.parse`. -/
def jsonNestingWithinLimit (text : String) : Bool :=
  let state := text.foldl scanJsonChar {}
  state.valid && !state.inString && state.depth == 0

private def exactFields (json : Json) (expected : List String)
    (what : String) : Except String Unit := do
  let object ← json.getObj?
  let keys := object.keys
  if keys.length != expected.length || !keys.all expected.contains then
    throw s!"{what} has wrong fields"

private def field (json : Json) (name : String) (what : String) : Except String Json :=
  match json.getObjVal? name with
  | .ok value => pure value
  | .error _ => throw s!"{what} is missing field {name}"

private def stringValue (json : Json) (what : String) : Except String String :=
  match json.getStr? with
  | .ok result => pure result
  | .error _ => throw s!"{what} must be a string"

private def stringField (json : Json) (name : String) (what : String) : Except String String := do
  stringValue (← field json name what) s!"{what}.{name}"

private def natField (json : Json) (name : String) (what : String) : Except String Nat := do
  let value ← field json name what
  match value.getNat? with
  | .ok result => pure result
  | .error _ => throw s!"{what}.{name} must be a nonnegative integer"

private def arrayValue (json : Json) (what : String) : Except String (Array Json) :=
  match json.getArr? with
  | .ok result => pure result
  | .error _ => throw s!"{what} must be an array"

private def requireString (actual expected what : String) : Except String Unit :=
  if actual != expected then throw s!"{what} has unsupported value" else pure ()

private def lowerHexNibble? (char : Char) : Option Nat :=
  if '0' ≤ char && char ≤ '9' then some (char.toNat - '0'.toNat)
  else if 'a' ≤ char && char ≤ 'f' then some (char.toNat - 'a'.toNat + 10)
  else none

private def parseHexDigits : List Char → Option Nat
  | [] => some 0
  | char :: rest => do
      let digit ← lowerHexNibble? char
      let suffix ← parseHexDigits rest
      pure (digit * 16 ^ rest.length + suffix)

private def parseWord (raw what : String) : Except String Nat := do
  if raw.length != 16 then throw s!"{what} must have exactly 16 hexadecimal digits"
  match parseHexDigits raw.toList with
  | none => throw s!"{what} must use lowercase hexadecimal digits"
  | some value => pure value

private def exponentBits (raw : Nat) : Nat := (raw / 2 ^ 52) % 2048
private def fractionBits (raw : Nat) : Nat := raw % (2 ^ 52)
private def isFiniteWord (raw : Nat) : Bool := exponentBits raw != 2047
private def isNaNWord (raw : Nat) : Bool :=
  exponentBits raw == 2047 && fractionBits raw != 0
private def isZeroWord (raw : Nat) : Bool := raw == 0 || raw == 2 ^ 63
private def isNegativeWord (raw : Nat) : Bool := raw ≥ 2 ^ 63

/-- Parse one canonical finite binary64 word for an application parameter. -/
def parseFiniteBinary64Hex (raw : String) : Except String Nat := do
  let value ← parseWord raw "binary64 application bound"
  if !isFiniteWord value then
    throw "binary64 application bound must be finite"
  pure value

/-- IEEE numeric ordering for non-NaN words, identifying the two signed zeros. -/
private def numericLE (left right : Nat) : Bool :=
  if isZeroWord left && isZeroWord right then true
  else if isNegativeWord left != isNegativeWord right then isNegativeWord left
  else if isNegativeWord left then left ≥ right
  else left ≤ right

private def parseRawInterval (json : Json) (what : String)
    (requireFinite : Bool) : Except String RawInterval := do
  exactFields json ["lo", "hi"] what
  let lo ← parseWord (← stringField json "lo" what) (what ++ ".lo")
  let hi ← parseWord (← stringField json "hi" what) (what ++ ".hi")
  if isNaNWord lo || isNaNWord hi then throw s!"{what} must not contain NaN"
  if requireFinite && (!isFiniteWord lo || !isFiniteWord hi) then
    throw s!"{what} must have finite endpoints"
  if !numericLE lo hi then throw s!"{what} has decreasing endpoints"
  pure { lo, hi }

private def requireSha256 (digest what : String) : Except String Unit := do
  if digest.length != 64 || !digest.toList.all (fun char => (lowerHexNibble? char).isSome) then
    throw s!"{what} must be 64 lowercase hexadecimal digits"

private structure ParseBudget where
  nodes : Nat := 0
  deriving Inhabited

private abbrev ParseM := StateT ParseBudget (Except String)

private def countNode (depth : Nat) : ParseM Unit := do
  if depth > maxCertificateDepth then
    throw s!"expression exceeds maximum depth {maxCertificateDepth}"
  let state ← get
  if state.nodes ≥ maxCertificateNodes then
    throw s!"expression exceeds maximum node count {maxCertificateNodes}"
  set ({ nodes := state.nodes + 1 } : ParseBudget)

private partial def parseExpression (json : Json) (variableCount depth : Nat) :
    ParseM CertExpr := do
  countNode depth
  let op ← liftM <| stringField json "op" "expression node"
  match op with
  | "const" =>
      liftM <| exactFields json ["op", "value"] "const expression"
      pure (.const (← liftM <| parseRawInterval
        (← liftM <| field json "value" "const expression")
        "const expression.value" true))
  | "var" =>
      liftM <| exactFields json ["op", "index"] "var expression"
      let index ← liftM <| natField json "index" "var expression"
      if index ≥ variableCount then
        throw s!"variable index {index} is outside variable_count {variableCount}"
      pure (.var index)
  | "neg" | "abs" =>
      liftM <| exactFields json ["op", "arg"] (op ++ " expression")
      let argument ← parseExpression
        (← liftM <| field json "arg" (op ++ " expression"))
        variableCount (depth + 1)
      if op == "neg" then pure (.neg argument) else pure (.abs argument)
  | "pow_nat" =>
      liftM <| exactFields json ["op", "arg", "exponent"] "pow_nat expression"
      let exponent ← liftM <| natField json "exponent" "pow_nat expression"
      if exponent > maxCertificatePowExponent then
        throw s!"pow_nat exponent exceeds {maxCertificatePowExponent}"
      pure (.powNat
        (← parseExpression
          (← liftM <| field json "arg" "pow_nat expression")
          variableCount (depth + 1)) exponent)
  | "add" | "sub" | "mul" | "div" | "min" | "max" =>
      liftM <| exactFields json ["op", "left", "right"] (op ++ " expression")
      let left ← parseExpression
        (← liftM <| field json "left" (op ++ " expression"))
        variableCount (depth + 1)
      let right ← parseExpression
        (← liftM <| field json "right" (op ++ " expression"))
        variableCount (depth + 1)
      match op with
      | "add" => pure (.add left right)
      | "sub" => pure (.sub left right)
      | "mul" => pure (.mul left right)
      | "div" => pure (.div left right)
      | "min" => pure (.min left right)
      | _ => pure (.max left right)
  | _ => throw s!"unsupported expression operation {op}"

private def parseRows (json : Json) (variableCount : Nat) :
    Except String (Array (Array RawInterval)) := do
  let rows ← arrayValue json "reference batch.rows"
  if rows.isEmpty then throw "reference batch.rows must not be empty"
  if rows.size > maxCertificateRows then
    throw s!"reference batch.rows exceeds {maxCertificateRows} rows"
  let mut parsed := #[]
  for rowIndex in *...rows.size do
    let row ← arrayValue rows[rowIndex]! s!"reference batch.rows[{rowIndex}]"
    if row.size != variableCount then
      throw s!"reference batch.rows[{rowIndex}] has wrong variable count"
    let mut parsedRow := #[]
    for column in *...row.size do
      parsedRow := parsedRow.push (← parseRawInterval row[column]!
        s!"reference batch.rows[{rowIndex}][{column}]" true)
    parsed := parsed.push parsedRow
  pure parsed

private def parseResults (json : Json) : Except String (Array RawInterval) := do
  let rows ← arrayValue json "reference result.rows"
  if rows.size > maxCertificateRows then
    throw s!"reference result.rows exceeds {maxCertificateRows} rows"
  let mut parsed := #[]
  for rowIndex in *...rows.size do
    parsed := parsed.push (← parseRawInterval rows[rowIndex]!
      s!"reference result.rows[{rowIndex}]" false)
  pure parsed

/-- Parse the canonical self-contained reference-certificate JSON format.

Successful parsing validates both nested SHA-256 digests and the result's
binding to the exact canonical batch.  Arithmetic is checked separately by
`FullCertificate.check` so callers can choose an application predicate.
-/
def parseCanonicalFullCertificate (text : String) : Except String FullCertificate := do
  if text.utf8ByteSize > maxCertificateBytes then
    throw s!"reference certificate exceeds {maxCertificateBytes} bytes"
  if !jsonNestingWithinLimit text then
    throw s!"reference certificate JSON nesting exceeds {maxCertificateJsonNesting} or is unbalanced"
  let json ← match Json.parse text with
    | .ok value => pure value
    | .error message => throw s!"invalid JSON: {message}"
  if json.compress != text then throw "reference certificate is not canonical JSON"

  exactFields json
    ["schema_version", "kind", "batch", "batch_sha256", "result", "result_sha256"]
    "reference certificate"
  let schemaVersion ← natField json "schema_version" "reference certificate"
  if schemaVersion != 1 then throw "reference certificate.schema_version must be 1"
  requireString (← stringField json "kind" "reference certificate")
    "sparkinterval_reference_certificate" "reference certificate.kind"

  let batchJson ← field json "batch" "reference certificate"
  let batchHash ← stringField json "batch_sha256" "reference certificate"
  requireSha256 batchHash "reference certificate.batch_sha256"
  if SHA256.digestString batchJson.compress != batchHash then
    throw "reference certificate batch SHA-256 mismatch"

  exactFields batchJson
    ["schema_version", "kind", "algorithm", "variable_count", "expression", "rows"]
    "reference batch"
  let batchVersion ← natField batchJson "schema_version" "reference batch"
  if batchVersion != 1 then throw "reference batch.schema_version must be 1"
  requireString (← stringField batchJson "kind" "reference batch")
    "sparkinterval_reference_batch" "reference batch.kind"
  requireString (← stringField batchJson "algorithm" "reference batch")
    "sparkinterval.binary64_interval_expr.v1" "reference batch.algorithm"
  let variableCount ← natField batchJson "variable_count" "reference batch"
  if variableCount > maxCertificateVariables then
    throw s!"variable_count exceeds {maxCertificateVariables}"
  let (expression, _) ← (parseExpression
    (← field batchJson "expression" "reference batch") variableCount 0).run {}
  let rows ← parseRows (← field batchJson "rows" "reference batch") variableCount
  let arithmeticCost := expression.arithmeticCostUpTo maxArithmeticCostPerRow
  if arithmeticCost > maxArithmeticCostPerRow then
    throw s!"expression arithmetic cost exceeds {maxArithmeticCostPerRow}"
  if rows.size * arithmeticCost > maxTotalArithmeticWork then
    throw s!"row count times expression arithmetic cost exceeds {maxTotalArithmeticWork}"

  let resultJson ← field json "result" "reference certificate"
  let resultHash ← stringField json "result_sha256" "reference certificate"
  requireSha256 resultHash "reference certificate.result_sha256"
  if SHA256.digestString resultJson.compress != resultHash then
    throw "reference certificate result SHA-256 mismatch"
  exactFields resultJson
    ["schema_version", "kind", "algorithm", "batch_sha256", "rows"]
    "reference result"
  let resultVersion ← natField resultJson "schema_version" "reference result"
  if resultVersion != 1 then throw "reference result.schema_version must be 1"
  requireString (← stringField resultJson "kind" "reference result")
    "sparkinterval_reference_result" "reference result.kind"
  requireString (← stringField resultJson "algorithm" "reference result")
    "sparkinterval.binary64_interval_expr.v1" "reference result.algorithm"
  let resultBatchHash ← stringField resultJson "batch_sha256" "reference result"
  requireSha256 resultBatchHash "reference result.batch_sha256"
  if resultBatchHash != batchHash then throw "reference result does not bind the batch"
  let results ← parseResults (← field resultJson "rows" "reference result")
  if results.size != rows.size then throw "reference result row count does not match batch"

  pure { variableCount, expression, rows, results, batchHash, resultHash }

/-- Parse and independently check every arithmetic row. -/
def checkCanonicalFullCertificate (text : String) : Bool :=
  match parseCanonicalFullCertificate text with
  | .ok certificate => certificate.check
  | .error _ => false

/-- Parse, check every row, and require the application upper bound. -/
def checkCanonicalFullCertificateUpperBound (text : String) (boundBits : Nat) : Bool :=
  match parseCanonicalFullCertificate text with
  | .ok certificate => certificate.checkUpperBound boundBits
  | .error _ => false

/-- Parse, check every row, require finite result highs, and compare their
exact rational sum with an application bound. -/
def checkCanonicalFullCertificateSumUpperBound (text : String) (bound : ℚ) : Bool :=
  match parseCanonicalFullCertificate text with
  | .ok certificate => certificate.checkSumUpperBound bound
  | .error _ => false

/-- Mathematical statement established by checking a serialized full
certificate against one finite application upper bound. -/
def SerializedUpperBoundTheorem (text : String) (boundBits : Nat) : Prop :=
  ∀ (certificate : FullCertificate) (bound : ℚ),
    parseCanonicalFullCertificate text = .ok certificate →
    Binary64.decodeFinite boundBits = some bound →
    ∀ (index : Nat), index < certificate.rows.size →
      ∀ (value : ℝ), certificate.RowRealizes index value →
        value ≤ (bound : ℝ)

/-- Finite-sum statement established by a serialized full certificate. -/
def SerializedSumUpperBoundTheorem (text : String) (bound : ℚ) : Prop :=
  ∀ certificate : FullCertificate,
    parseCanonicalFullCertificate text = .ok certificate →
    ∀ values : Fin certificate.rows.size → ℝ,
      certificate.ValuesRealize values →
      (∑ index, values index) ≤ (bound : ℝ)

/-- **Phase 8 result-certificate theorem.**

If the Boolean serialized checker accepts, every real value represented by
every complete input row is below the supplied bound.  The proof uses exact
rational row recomputation and no physical-execution or attestation axiom.
-/
theorem impliesTheorem {text : String} {boundBits : Nat}
    (hcheck : checkCanonicalFullCertificateUpperBound text boundBits = true) :
    SerializedUpperBoundTheorem text boundBits := by
  intro certificate bound hparse hbound index hindex value hreal
  unfold checkCanonicalFullCertificateUpperBound at hcheck
  rw [hparse] at hcheck
  exact certificate.checkUpperBound_sound hbound hcheck hindex hreal

/-- Serialized Phase 8 theorem for a finite sum of one realized value from
every complete row. -/
theorem impliesSumTheorem {text : String} {bound : ℚ}
    (hcheck : checkCanonicalFullCertificateSumUpperBound text bound = true) :
    SerializedSumUpperBoundTheorem text bound := by
  intro certificate hparse values hvalues
  unfold checkCanonicalFullCertificateSumUpperBound at hcheck
  rw [hparse] at hcheck
  exact certificate.checkSumUpperBound_sound hcheck values hvalues

end SparkInterval.Certificate
