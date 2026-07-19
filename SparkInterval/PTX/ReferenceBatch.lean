import Lean.Data.Json
import SparkInterval.PTX.AST

/-!
# Fail-closed parser for canonical reference batches

The generator consumes the Phase 3 canonical JSON batch directly.  This parser
checks canonical byte spelling, exact object fields, every finite input row,
and the stricter Phase 5 limits before constructing the polynomial AST.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

open Lean

def phase5MaxVariables : Nat := 64
def phase5MaxRows : Nat := 1000000
def phase5MaxNodes : Nat := 256
def phase5MaxDepth : Nat := 64
def phase5MaxPowExponent : Nat := 64
def phase5MaxInputBytes : Nat := 512 * 1024 * 1024

/-- A binary64 word retains both its numeric value and canonical spelling. -/
structure Bits64 where
  value : Nat
  hex : String
  deriving BEq, DecidableEq, Repr

structure IntervalBits where
  lo : Bits64
  hi : Bits64
  deriving BEq, DecidableEq, Repr

/-- The explicitly bounded Phase 5 polynomial expression slice. -/
inductive PolynomialExpr where
  | const (value : IntervalBits)
  | var (index : Nat)
  | neg (arg : PolynomialExpr)
  | add (left right : PolynomialExpr)
  | sub (left right : PolynomialExpr)
  | mul (left right : PolynomialExpr)
  | powNat (arg : PolynomialExpr) (exponent : Nat)
  deriving BEq, DecidableEq, Repr

structure ReferenceBatch where
  variableCount : Nat
  expression : PolynomialExpr
  rowCount : Nat
  deriving BEq, DecidableEq, Repr

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

private def stringField (json : Json) (name : String) (what : String) : Except String String := do
  let value ← field json name what
  match value.getStr? with
  | .ok result => pure result
  | .error _ => throw s!"{what}.{name} must be a string"

private def natField (json : Json) (name : String) (what : String) : Except String Nat := do
  let value ← field json name what
  match value.getNat? with
  | .ok result => pure result
  | .error _ => throw s!"{what}.{name} must be a nonnegative integer"

private def hexNibble? (char : Char) : Option Nat :=
  if '0' ≤ char && char ≤ '9' then some (char.toNat - '0'.toNat)
  else if 'a' ≤ char && char ≤ 'f' then some (char.toNat - 'a'.toNat + 10)
  else none

private def parseHexDigits : List Char → Option Nat
  | [] => some 0
  | char :: rest => do
      let digit ← hexNibble? char
      let suffix ← parseHexDigits rest
      return digit * 16 ^ rest.length + suffix

def parseBits64 (raw : String) (what : String) : Except String Bits64 := do
  if raw.length != 16 then throw s!"{what} must have exactly 16 hexadecimal digits"
  match parseHexDigits raw.toList with
  | none => throw s!"{what} must use lowercase hexadecimal digits"
  | some value => pure { value, hex := raw }

def Bits64.isFinite (bits : Bits64) : Bool :=
  (bits.value / 2 ^ 52) % 2048 != 2047

private def Bits64.isZero (bits : Bits64) : Bool :=
  bits.value == 0 || bits.value == 2 ^ 63

private def Bits64.isNegative (bits : Bits64) : Bool :=
  bits.value ≥ 2 ^ 63

/-- Numeric binary64 ordering for non-NaN words, identifying signed zeros. -/
def Bits64.numericLE (left right : Bits64) : Bool :=
  if left.isZero && right.isZero then true
  else if left.isNegative != right.isNegative then left.isNegative
  else if left.isNegative then left.value ≥ right.value
  else left.value ≤ right.value

private def parseInterval (json : Json) (what : String) : Except String IntervalBits := do
  exactFields json ["lo", "hi"] what
  let lo ← parseBits64 (← stringField json "lo" what) (what ++ ".lo")
  let hi ← parseBits64 (← stringField json "hi" what) (what ++ ".hi")
  if !lo.isFinite || !hi.isFinite then
    throw s!"{what} must have finite endpoints"
  if !lo.numericLE hi then throw s!"{what} has decreasing endpoints"
  return { lo, hi }

private structure ParseBudget where
  nodes : Nat := 0
  deriving Inhabited

private abbrev ParseM := StateT ParseBudget (Except String)

private def countNode (depth : Nat) : ParseM Unit := do
  if depth > phase5MaxDepth then
    throw s!"expression exceeds the Phase 5 depth limit {phase5MaxDepth}"
  let state ← get
  if state.nodes ≥ phase5MaxNodes then
    throw s!"expression exceeds the Phase 5 node limit {phase5MaxNodes}"
  set ({ nodes := state.nodes + 1 } : ParseBudget)

private partial def parseExpr (json : Json) (variableCount depth : Nat) : ParseM PolynomialExpr := do
  countNode depth
  let op ← liftM <| stringField json "op" "expression node"
  match op with
  | "const" =>
      liftM <| exactFields json ["op", "value"] "const expression"
      return .const (← liftM <| parseInterval (← liftM <| field json "value" "const expression")
        "const expression.value")
  | "var" =>
      liftM <| exactFields json ["op", "index"] "var expression"
      let index ← liftM <| natField json "index" "var expression"
      if index ≥ variableCount then
        throw s!"variable index {index} is outside variable_count {variableCount}"
      return .var index
  | "neg" =>
      liftM <| exactFields json ["op", "arg"] "neg expression"
      return .neg (← parseExpr (← liftM <| field json "arg" "neg expression")
        variableCount (depth + 1))
  | "add" | "sub" | "mul" =>
      liftM <| exactFields json ["op", "left", "right"] (op ++ " expression")
      let left ← parseExpr (← liftM <| field json "left" (op ++ " expression"))
        variableCount (depth + 1)
      let right ← parseExpr (← liftM <| field json "right" (op ++ " expression"))
        variableCount (depth + 1)
      if op == "add" then return .add left right
      else if op == "sub" then return .sub left right
      else return .mul left right
  | "pow_nat" =>
      liftM <| exactFields json ["op", "arg", "exponent"] "pow_nat expression"
      let exponent ← liftM <| natField json "exponent" "pow_nat expression"
      if exponent > phase5MaxPowExponent then
        throw s!"pow_nat exponent exceeds {phase5MaxPowExponent}"
      return .powNat
        (← parseExpr (← liftM <| field json "arg" "pow_nat expression")
          variableCount (depth + 1)) exponent
  | "div" | "abs" | "min" | "max" =>
      throw s!"operation {op} is outside the Phase 5 polynomial allowlist"
  | _ => throw s!"unsupported expression operation {op}"

private def checkFixedString (json : Json) (name expected : String) : Except String Unit := do
  let actual ← stringField json name "reference batch"
  if actual != expected then throw s!"reference batch.{name} has unsupported value"

private def validateRows (json : Json) (variableCount : Nat) : Except String Nat := do
  let rows ← match json.getArr? with
    | .ok value => pure value
    | .error _ => throw "reference batch.rows must be an array"
  if rows.isEmpty then throw "reference batch.rows must not be empty"
  if rows.size > phase5MaxRows then
    throw s!"reference batch.rows exceeds {phase5MaxRows} rows"
  for rowIndex in *...rows.size do
    let rowJson := rows[rowIndex]!
    let row ← match rowJson.getArr? with
      | .ok value => pure value
      | .error _ => throw s!"reference batch row {rowIndex} must be an array"
    if row.size != variableCount then
      throw s!"reference batch row {rowIndex} has wrong variable count"
    for column in *...row.size do
      let _ ← parseInterval row[column]! s!"reference batch.rows[{rowIndex}][{column}]"
  return rows.size

/-- Parse and fully validate a canonical Phase 3 batch under Phase 5 limits. -/
def parseCanonicalReferenceBatch (text : String) : Except String ReferenceBatch := do
  if text.utf8ByteSize > phase5MaxInputBytes then
    throw s!"reference batch exceeds {phase5MaxInputBytes} bytes"
  let json ← match Json.parse text with
    | .ok value => pure value
    | .error message => throw s!"invalid JSON: {message}"
  if json.compress != text then
    throw "reference batch is not canonical JSON"
  exactFields json
    ["schema_version", "kind", "algorithm", "variable_count", "expression", "rows"]
    "reference batch"
  let schemaVersion ← natField json "schema_version" "reference batch"
  if schemaVersion != 1 then throw "reference batch.schema_version must be 1"
  checkFixedString json "kind" "sparkinterval_reference_batch"
  checkFixedString json "algorithm" "sparkinterval.binary64_interval_expr.v1"
  let variableCount ← natField json "variable_count" "reference batch"
  if variableCount > phase5MaxVariables then
    throw s!"variable_count exceeds the Phase 5 limit {phase5MaxVariables}"
  let expressionJson ← field json "expression" "reference batch"
  let (expression, _) ← (parseExpr expressionJson variableCount 0).run {}
  let rowCount ← validateRows (← field json "rows" "reference batch") variableCount
  return { variableCount, expression, rowCount }

end SparkInterval.PTX
