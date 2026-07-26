/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Lean.Data.Json
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Archive

/-!
# Canonical V1 wire decoder for Sqrt218 archives

This module decodes the existing
`sparkinterval.sqrt218-finite-certificate.v1` canonical JSON bytes into the
architecture-neutral `Sqrt218Operational.Archive`.  It does not contain
production rows and does not run the arithmetic checker.

Acceptance is deliberately stricter than "Lean's JSON parser returned an
object": after parsing all exact fields and bounded row shapes, the decoder
re-encodes the typed archive and requires byte-for-byte equality with the
input.  Consequently successful decoding proves all of the following at once:

* strict UTF-8;
* the exact V1 object fields and protocol constants;
* Python-compatible compact, sorted-key JSON spelling;
* no duplicate or extra fields and no alternate number/string spellings; and
* exact end of input (a suffix or trailing newline changes the byte array).

This is a wire theorem only.  It does not connect a receipt digest to bytes,
does not assert that a measured executable ran this decoder, and does not
change the registered V1 execution relation or its sole trust axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

open Lean

/-! ## Public V1 limits and shape -/

def maxArchiveBytes : Nat := 256 * 1024 * 1024
def maxArchiveJsonNesting : Nat := 32
def maxArchivePrimeRows : Nat := 148_933
def maxArchiveEventRows : Nat := 149_235
def maxArchivePrimeIndex : Nat := maxArchivePrimeRows - 1
def maxArchiveValue : Nat := 2_000_000
def maxArchiveExponent : Nat := 64

def archiveFieldNames : List String :=
  ["bound", "events", "kind", "log_scale", "log_seed_at", "primes",
    "reciprocal_scale", "schema_version", "summary"]

def summaryFieldNames : List String :=
  ["anchor_slack", "final_psi_lower", "final_weighted_upper",
    "fixed_scan_sha256", "layout_sha256", "minimum_head_n",
    "minimum_head_slack", "power_event_count", "pratt_sha256",
    "prime_count", "proper_power_count", "reused_prime_count",
    "tail_prime_count"]

/-- Header constants selected by the existing canonical JSON V1 protocol. -/
def Archive.HasV1Header (archive : Archive) : Prop :=
  archive.kind = certificateKind ∧
    archive.schemaVersion = 1 ∧
    archive.logSeedAt = 30 ∧
    archive.logScale = 281_474_976_710_656 ∧
    archive.reciprocalScale = 1_073_741_824

instance (archive : Archive) : Decidable archive.HasV1Header :=
  by
    unfold Archive.HasV1Header
    infer_instance

/-! ## Canonical encoder

`Json.mkObj` stores object keys in canonical lexical order.  All strings in
this protocol are ASCII, so `Json.compress` agrees with Python's
`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`
on every value admitted below.
-/

private def natJson (value : Nat) : Json :=
  toJson value

private def natListJson (values : List Nat) : Json :=
  .arr (values.map natJson).toArray

private def primeRowJson (row : PrimeRow) : Json :=
  .arr #[
    natJson row.prime,
    natJson row.witness,
    natListJson row.factors,
    natJson row.logLower,
    natJson row.logUpper
  ]

private def powerEventJson (event : PowerEvent) : Json :=
  .arr #[
    natJson event.power,
    natJson event.primeIndex,
    natJson event.exponent
  ]

private def summaryJson (summary : Summary) : Json :=
  Json.mkObj [
    ("anchor_slack", natJson summary.anchorSlack),
    ("final_psi_lower", natJson summary.finalPsiLower),
    ("final_weighted_upper", natJson summary.finalWeightedUpper),
    ("fixed_scan_sha256", .str summary.fixedScanDigest),
    ("layout_sha256", .str summary.layoutDigest),
    ("minimum_head_n", natJson summary.minimumHeadIndex),
    ("minimum_head_slack", natJson summary.minimumHeadSlack),
    ("power_event_count", natJson summary.primePowerEventCount),
    ("pratt_sha256", .str summary.prattDigest),
    ("prime_count", natJson summary.primeCount),
    ("proper_power_count", natJson summary.properPrimePowerEventCount),
    ("reused_prime_count", natJson summary.reusedPrimeCount),
    ("tail_prime_count", natJson summary.tailPrimeCount)
  ]

/-- Canonical JSON syntax tree for one typed archive. -/
def canonicalArchiveJson (archive : Archive) : Json :=
  Json.mkObj [
    ("bound", natJson archive.bound),
    ("events", .arr (archive.events.map powerEventJson).toArray),
    ("kind", .str archive.kind),
    ("log_scale", natJson archive.logScale),
    ("log_seed_at", natJson archive.logSeedAt),
    ("primes", .arr (archive.primes.map primeRowJson).toArray),
    ("reciprocal_scale", natJson archive.reciprocalScale),
    ("schema_version", natJson archive.schemaVersion),
    ("summary", summaryJson archive.summary)
  ]

/-- Exact compact canonical JSON text, without a trailing newline. -/
def canonicalArchiveText (archive : Archive) : String :=
  (canonicalArchiveJson archive).compress

/-- Exact UTF-8 artifact bytes whose digest must be placed in a receipt. -/
def canonicalArchiveBytes (archive : Archive) : ByteArray :=
  (canonicalArchiveText archive).toUTF8

/-- The encoder emits exactly the nine reviewed top-level fields. -/
theorem canonicalArchiveJson_topLevelFields (archive : Archive) :
    (canonicalArchiveJson archive).getObj?.map
        (fun object => object.keys) =
      .ok archiveFieldNames := by
  rfl

/-- The nested summary likewise has one exact, closed field set. -/
theorem canonicalArchiveJson_summaryFields (archive : Archive) :
    ((canonicalArchiveJson archive).getObjVal? "summary").bind
        (fun json => json.getObj?.map (fun object => object.keys)) =
      .ok summaryFieldNames := by
  rfl

/-- The JSON `kind` cell is exactly the typed archive's discriminator. -/
theorem canonicalArchiveJson_kindField (archive : Archive) :
    (canonicalArchiveJson archive).getObjVal? "kind" =
      .ok (.str archive.kind) := by
  rfl

/-! ## Allocation-bounded JSON preflight -/

private structure JsonScanState where
  depth : Nat := 0
  inString : Bool := false
  escaped : Bool := false
  valid : Bool := true

private def scanJsonChar
    (state : JsonScanState) (character : Char) : JsonScanState :=
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
    { state with
      depth
      valid := decide (depth ≤ maxArchiveJsonNesting) }
  else if character == '}' || character == ']' then
    if state.depth = 0 then
      { state with valid := false }
    else
      { state with depth := state.depth - 1 }
  else
    state

/-- Cheap nesting and delimiter preflight before invoking the JSON parser. -/
def archiveJsonNestingWithinLimit (text : String) : Bool :=
  let state := text.foldl scanJsonChar {}
  state.valid && !state.inString && state.depth == 0

/-! ## Strict typed parser -/

private def exactFields
    (json : Json) (expected : List String) (what : String) :
    Except String Unit := do
  let object ←
    match json.getObj? with
    | .ok object => pure object
    | .error _ => throw s!"{what} must be an object"
  let keys := object.keys
  if keys.length != expected.length || !keys.all expected.contains then
    throw s!"{what} has wrong fields"

private def field
    (json : Json) (name : String) (what : String) : Except String Json :=
  match json.getObjVal? name with
  | .ok value => pure value
  | .error _ => throw s!"{what} is missing field {name}"

private def arrayValue
    (json : Json) (what : String) : Except String (Array Json) :=
  match json.getArr? with
  | .ok values => pure values
  | .error _ => throw s!"{what} must be an array"

private def natValue (json : Json) (what : String) : Except String Nat :=
  match json.getNat? with
  | .ok value => pure value
  | .error _ => throw s!"{what} must be a nonnegative integer"

private def natField
    (json : Json) (name : String) (what : String) : Except String Nat := do
  natValue (← field json name what) s!"{what}.{name}"

private def stringValue
    (json : Json) (what : String) : Except String String :=
  match json.getStr? with
  | .ok value => pure value
  | .error _ => throw s!"{what} must be a string"

private def stringField
    (json : Json) (name : String) (what : String) : Except String String := do
  stringValue (← field json name what) s!"{what}.{name}"

private def requireRange
    (value lower upper : Nat) (what : String) : Except String Unit := do
  if value < lower || upper < value then
    throw s!"{what} is outside [{lower}, {upper}]"
  pure ()

private def requirePositive
    (value : Nat) (what : String) : Except String Unit := do
  if value = 0 then
    throw s!"{what} must be positive"
  pure ()

private def isLowerHex (character : Char) : Bool :=
  ('0' ≤ character && character ≤ '9') ||
    ('a' ≤ character && character ≤ 'f')

private def requireSha256 (digest what : String) : Except String Unit := do
  if digest.length != 64 || !digest.toList.all isLowerHex then
    throw s!"{what} must be 64 lowercase hexadecimal digits"
  pure ()

private def parseFactorList (json : Json) : Except String (List Nat) := do
  let factors ← arrayValue json "prime row factors"
  let mut result := #[]
  for factorJson in factors do
    let factor ← natValue factorJson "prime row factor"
    requireRange factor 2 maxArchiveValue "prime row factor"
    result := result.push factor
  pure result.toList

private def parsePrimeRow (json : Json) : Except String PrimeRow := do
  let row ← arrayValue json "prime row"
  if row.size != 5 then
    throw "prime row must have exactly five entries"
  let prime ← natValue row[0]! "prime row prime"
  let witness ← natValue row[1]! "prime row witness"
  let factors ← parseFactorList row[2]!
  let logLower ← natValue row[3]! "prime row lower log"
  let logUpper ← natValue row[4]! "prime row upper log"
  requireRange prime 2 maxArchiveValue "prime row prime"
  requireRange witness 0 maxArchiveValue "prime row witness"
  pure { prime, witness, factors, logLower, logUpper }

private def parsePrimeRows (json : Json) : Except String (List PrimeRow) := do
  let rows ← arrayValue json "certificate.primes"
  if rows.isEmpty || maxArchivePrimeRows < rows.size then
    throw s!"certificate.primes must contain 1..{maxArchivePrimeRows} rows"
  let mut result := #[]
  for rowJson in rows do
    result := result.push (← parsePrimeRow rowJson)
  pure result.toList

private def parsePowerEvent (json : Json) : Except String PowerEvent := do
  let row ← arrayValue json "event row"
  if row.size != 3 then
    throw "event row must have exactly three entries"
  let power ← natValue row[0]! "event row power"
  let primeIndex ← natValue row[1]! "event row prime index"
  let exponent ← natValue row[2]! "event row exponent"
  requireRange power 2 maxArchiveValue "event row power"
  requireRange primeIndex 0 maxArchivePrimeIndex "event row prime index"
  requireRange exponent 1 maxArchiveExponent "event row exponent"
  pure { power, primeIndex, exponent }

private def parsePowerEvents
    (json : Json) : Except String (List PowerEvent) := do
  let rows ← arrayValue json "certificate.events"
  if rows.isEmpty || maxArchiveEventRows < rows.size then
    throw s!"certificate.events must contain 1..{maxArchiveEventRows} rows"
  let mut result := #[]
  for rowJson in rows do
    result := result.push (← parsePowerEvent rowJson)
  pure result.toList

private def parseSummary (json : Json) : Except String Summary := do
  exactFields json summaryFieldNames "certificate.summary"
  let anchorSlack ← natField json "anchor_slack" "certificate.summary"
  let finalPsiLower ←
    natField json "final_psi_lower" "certificate.summary"
  let finalWeightedUpper ←
    natField json "final_weighted_upper" "certificate.summary"
  let fixedScanDigest ←
    stringField json "fixed_scan_sha256" "certificate.summary"
  let layoutDigest ←
    stringField json "layout_sha256" "certificate.summary"
  let minimumHeadIndex ←
    natField json "minimum_head_n" "certificate.summary"
  let minimumHeadSlack ←
    natField json "minimum_head_slack" "certificate.summary"
  let primePowerEventCount ←
    natField json "power_event_count" "certificate.summary"
  let prattDigest ←
    stringField json "pratt_sha256" "certificate.summary"
  let primeCount ← natField json "prime_count" "certificate.summary"
  let properPrimePowerEventCount ←
    natField json "proper_power_count" "certificate.summary"
  let reusedPrimeCount ←
    natField json "reused_prime_count" "certificate.summary"
  let tailPrimeCount ←
    natField json "tail_prime_count" "certificate.summary"
  requirePositive anchorSlack "summary anchor slack"
  requirePositive finalPsiLower "summary final psi lower"
  requirePositive finalWeightedUpper "summary final weighted upper"
  requireRange minimumHeadIndex 2 maxArchiveValue "summary minimum head index"
  requirePositive minimumHeadSlack "summary minimum head slack"
  requireRange primePowerEventCount 1 maxArchiveEventRows
    "summary power event count"
  requireRange primeCount 1 maxArchivePrimeRows "summary prime count"
  requireRange properPrimePowerEventCount 0 302
    "summary proper power count"
  requireRange reusedPrimeCount 0 115_408 "summary reused prime count"
  requireRange tailPrimeCount 0 33_525 "summary tail prime count"
  requireSha256 fixedScanDigest "summary fixed scan digest"
  requireSha256 layoutDigest "summary layout digest"
  requireSha256 prattDigest "summary Pratt digest"
  pure {
    anchorSlack
    finalPsiLower
    finalWeightedUpper
    fixedScanDigest
    layoutDigest
    minimumHeadIndex
    minimumHeadSlack
    primePowerEventCount
    prattDigest
    primeCount
    properPrimePowerEventCount
    reusedPrimeCount
    tailPrimeCount
  }

private def parseArchiveJson (json : Json) : Except String Archive := do
  exactFields json archiveFieldNames "certificate"
  let bound ← natField json "bound" "certificate"
  let events ← parsePowerEvents (← field json "events" "certificate")
  let kind ← stringField json "kind" "certificate"
  let logScale ← natField json "log_scale" "certificate"
  let logSeedAt ← natField json "log_seed_at" "certificate"
  let primes ← parsePrimeRows (← field json "primes" "certificate")
  let reciprocalScale ← natField json "reciprocal_scale" "certificate"
  let schemaVersion ← natField json "schema_version" "certificate"
  let summary ← parseSummary (← field json "summary" "certificate")
  requireRange bound 2 maxArchiveValue "certificate.bound"
  pure {
    kind
    schemaVersion
    bound
    logSeedAt
    logScale
    reciprocalScale
    primes
    events
    summary
  }

private def parseArchiveBytesUnchecked
    (raw : ByteArray) : Except String Archive := do
  if maxArchiveBytes < raw.size then
    throw s!"Sqrt218 archive exceeds {maxArchiveBytes} bytes"
  let text ←
    match String.fromUTF8? raw with
    | some text => pure text
    | none => throw "Sqrt218 archive is not strict UTF-8"
  if !archiveJsonNestingWithinLimit text then
    throw "Sqrt218 archive JSON nesting is excessive or unbalanced"
  let json ←
    match Json.parse text with
    | .ok json => pure json
    | .error message => throw s!"invalid Sqrt218 JSON: {message}"
  parseArchiveJson json

/-! ## Canonical finalizer and decoder theorems -/

private def finalizeCanonicalV1
    (raw : ByteArray) (archive : Archive) : Except String Archive :=
  if _ : archive.HasV1Header then
    if canonicalArchiveBytes archive = raw then
      pure archive
    else
      throw "Sqrt218 archive is not canonical V1 JSON"
  else
    throw "Sqrt218 archive has unsupported protocol constants"

/-- Decode exact canonical V1 UTF-8 bytes into a typed archive.

This function parses structure only.  Call `Sqrt218Operational.run` separately
to establish arithmetic certificate facts. -/
def decodeCanonicalArchiveBytes
    (raw : ByteArray) : Except String Archive :=
  (parseArchiveBytesUnchecked raw).bind (finalizeCanonicalV1 raw)

private theorem finalizeCanonicalV1_success
    {raw : ByteArray} {candidate archive : Archive}
    (hdecode : finalizeCanonicalV1 raw candidate = .ok archive) :
    candidate = archive ∧
      archive.HasV1Header ∧
      canonicalArchiveBytes archive = raw := by
  unfold finalizeCanonicalV1 at hdecode
  split at hdecode
  · rename_i hheader
    split at hdecode
    · rename_i hbytes
      have hcandidate :
          (Except.ok candidate : Except String Archive) =
            Except.ok archive := hdecode
      have hcandidate_eq : candidate = archive :=
        Except.ok.inj hcandidate
      subst candidate
      exact ⟨rfl, hheader, hbytes⟩
    · contradiction
  · contradiction

/-- Successful decoding fixes the V1 header and every artifact byte. -/
theorem decodeCanonicalArchiveBytes_success
    {raw : ByteArray} {archive : Archive}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok archive) :
    archive.HasV1Header ∧ canonicalArchiveBytes archive = raw := by
  unfold decodeCanonicalArchiveBytes at hdecode
  cases hparse : parseArchiveBytesUnchecked raw with
  | error message =>
      rw [hparse] at hdecode
      contradiction
  | ok candidate =>
      rw [hparse] at hdecode
      exact (finalizeCanonicalV1_success hdecode).2

/-- `kind` cannot be selected by the receipt caller or an alternate wire
spelling: it is the literal V1 discriminator. -/
theorem decodeCanonicalArchiveBytes_kind
    {raw : ByteArray} {archive : Archive}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok archive) :
    archive.kind = certificateKind :=
  (decodeCanonicalArchiveBytes_success hdecode).1.1

/-- Successful decoding fixes the schema version to one. -/
theorem decodeCanonicalArchiveBytes_schemaVersion
    {raw : ByteArray} {archive : Archive}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok archive) :
    archive.schemaVersion = 1 :=
  (decodeCanonicalArchiveBytes_success hdecode).1.2.1

/-- Exact-EOF/canonicality theorem: the entire input, not merely a parsed
prefix, is the unique encoding of the returned archive. -/
theorem decodeCanonicalArchiveBytes_exact
    {raw : ByteArray} {archive : Archive}
    (hdecode : decodeCanonicalArchiveBytes raw = .ok archive) :
    canonicalArchiveBytes archive = raw :=
  (decodeCanonicalArchiveBytes_success hdecode).2

/-- There cannot be two accepted byte spellings of the same typed archive. -/
theorem decodeCanonicalArchiveBytes_noAlternateEncoding
    {left right : ByteArray} {archive : Archive}
    (hleft : decodeCanonicalArchiveBytes left = .ok archive)
    (hright : decodeCanonicalArchiveBytes right = .ok archive) :
    left = right :=
  (decodeCanonicalArchiveBytes_exact hleft).symm.trans
    (decodeCanonicalArchiveBytes_exact hright)

end SparkInterval.TernaryGoldbach.Sqrt218Operational
