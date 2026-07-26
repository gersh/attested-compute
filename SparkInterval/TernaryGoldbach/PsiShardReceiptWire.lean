/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Lean.Data.Json

/-!
# Fail-closed wire checker for the CH25 psi shard receipts

`reference/tg_psi_residual_shard.cpp` emits one compact JSON object per
invocation.  This file parses those bytes directly; it does not parse a
hand-written descriptor or replace the producer output with a second format.

The checker validates the fixed algorithm/upstream identities, exact field
set, compact spelling, shard range, event counters, Q64 bounds, digest syntax,
summary/verify mode separation, root-derived incoming state, outgoing-state
addition, singleton guards, and equality of the independently regenerated
summary and verify transitions.  A list checker additionally validates the
fixed 100,000-shard source geometry and the published total event count.

This is intentionally only a finite wire theorem.  The two SHA-256 values in
each receipt remain opaque commitments: the receipt does not contain the
prime-power rows or the directed CRlibm logarithm endpoints that they hash.
Consequently this module does **not** construct
`PsiPrimePowerCertificate.GapSourceScaleEvidence`, prove CRlibm refinement to
`Real.log`, prove prime-power roster completeness, authenticate an execution,
or discharge CH25 Lemma 9.2.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.PsiShardReceiptWire

open Lean

def maximumReceiptBytes : Nat := 16 * 1024
def maximumJsonNesting : Nat := 4

def sourceLower : Nat := 2
def sourceUpperExclusive : Nat := 10_000_000_000_001
def sourceEventCount : Nat := 346_065_767_406
def sourceShardSpan : Nat := 100_000_000
def sourceShardCount : Nat := 100_000
def productionSieveSizeKiB : Nat := 384

def runnerAlgorithm : String :=
  "ch25-psi-prime-power-two-pass-v1"

def runnerClassification : String :=
  "source-scale-shard-not-lean-proof"

def atomId : String :=
  "ch25-psi-1e13"

def primesieveCommit : String :=
  "4f85384851da23c36c01ec01ef85b5d9d246e556"

def crlibmCommit : String :=
  "eb3063791aa75bc9705b49283bf14250465220a7"

def logIntervalEncoding : String :=
  "crlibm-binary64-directed-to-q64-v1"

def eventEncoding : String :=
  "u64be-value-u64be-prime-u32be-exponent-v1"

def rowEncoding : String :=
  "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1"

def stateComponents : List String :=
  ["psi_lower_q64", "psi_upper_q64"]

def receiptFieldNames : List String := [
  "algorithm",
  "mode",
  "classification",
  "atom",
  "primesieve_commit",
  "crlibm_commit",
  "lower",
  "upper_exclusive",
  "work_count",
  "scale_bits",
  "sieve_size_kib",
  "log_interval_encoding",
  "event_encoding",
  "event_sha256",
  "row_encoding",
  "row_sha256",
  "prime_power_events",
  "prime_events",
  "higher_power_events",
  "state_components",
  "delta",
  "guards",
  "incoming_state",
  "outgoing_state",
  "exact_fallbacks",
  "terminal_strict_lower_checked",
  "accepted",
  "elapsed_seconds",
  "execution_attested",
  "lean_atom_discharged"
]

def fallbackFieldNames : List String :=
  ["lower_left_limit", "upper_post_jump", "terminal_lower"]

def singletonGuardFieldNames : List String :=
  ["lower_guard", "upper_guard", "witnesses"]

inductive Phase where
  | summary
  | verify
  deriving Repr, DecidableEq, BEq

structure Q64State where
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq

namespace Q64State

def zero : Q64State := ⟨0, 0⟩

def add (left right : Q64State) : Q64State :=
  ⟨left.lower + right.lower, left.upper + right.upper⟩

def InU128 (state : Q64State) : Prop :=
  state.lower < 2 ^ 128 ∧ state.upper < 2 ^ 128

instance (state : Q64State) : Decidable state.InU128 := by
  unfold InU128
  infer_instance

end Q64State

structure Guard where
  lower : Q64State
  upper : Q64State
  deriving Repr, DecidableEq

structure FallbackCounts where
  lowerLeftLimit : Nat
  upperPostJump : Nat
  terminalLower : Nat
  deriving Repr, DecidableEq

structure Receipt where
  phase : Phase
  lower : Nat
  upperExclusive : Nat
  workCount : Nat
  sieveSizeKiB : Nat
  eventSHA256 : String
  rowSHA256 : String
  primePowerEvents : Nat
  primeEvents : Nat
  higherPowerEvents : Nat
  delta : Q64State
  guard : Option Guard
  incomingState : Option Q64State
  outgoingState : Option Q64State
  fallbacks : FallbackCounts
  terminalStrictLowerChecked : Bool
  accepted : Bool
  elapsedSeconds : JsonNumber
  executionAttested : Bool
  leanAtomDischarged : Bool
  deriving Repr, DecidableEq

private def exactFields
    (json : Json) (expected : List String) : Except String Unit := do
  let object ← json.getObj?
  let keys := object.keys
  if keys.length != expected.length || !keys.all expected.contains then
    throw "JSON object has the wrong field set"

private def jsonField (json : Json) (name : String) : Except String Json :=
  match json.getObjVal? name with
  | .ok value => pure value
  | .error _ => throw s!"missing JSON field {name}"

private def natField (json : Json) (name : String) : Except String Nat := do
  (← jsonField json name).getNat?

private def stringField
    (json : Json) (name : String) : Except String String := do
  (← jsonField json name).getStr?

private def boolField
    (json : Json) (name : String) : Except String Bool := do
  (← jsonField json name).getBool?

private def numberField
    (json : Json) (name : String) : Except String JsonNumber := do
  (← jsonField json name).getNum?

private def parseStringList (json : Json) : Except String (List String) := do
  let values ← json.getArr?
  values.toList.mapM Json.getStr?

private def parseState (json : Json) : Except String Q64State := do
  let values ← json.getArr?
  if values.size != 2 then
    throw "Q64 state must have exactly two coordinates"
  let lower ← (values[0]!).getNat?
  let upper ← (values[1]!).getNat?
  pure ⟨lower, upper⟩

private def parseOptionalState (json : Json) :
    Except String (Option Q64State) :=
  if json.isNull then
    pure none
  else
    some <$> parseState json

private def parseFallbacks (json : Json) :
    Except String FallbackCounts := do
  exactFields json fallbackFieldNames
  pure {
    lowerLeftLimit := ← natField json "lower_left_limit"
    upperPostJump := ← natField json "upper_post_jump"
    terminalLower := ← natField json "terminal_lower"
  }

private def parseGuard (json : Json) : Except String (Option Guard) := do
  let object ← json.getObj?
  if object.keys.isEmpty then
    pure none
  else
    exactFields json [atomId]
    let singleton ← jsonField json atomId
    exactFields singleton singletonGuardFieldNames
    let witnesses ← (← jsonField singleton "witnesses").getArr?
    if !witnesses.isEmpty then
      throw "psi singleton guard witnesses must be empty"
    pure (some {
      lower := ← parseState (← jsonField singleton "lower_guard")
      upper := ← parseState (← jsonField singleton "upper_guard")
    })

private def parsePhase (text : String) : Except String Phase :=
  if text = "summary" then
    pure .summary
  else if text = "verify" then
    pure .verify
  else
    throw "psi receipt mode must be summary or verify"

private def parseReceiptJson (json : Json) : Except String Receipt := do
  exactFields json receiptFieldNames
  if (← stringField json "algorithm") != runnerAlgorithm ||
      (← stringField json "classification") != runnerClassification ||
      (← stringField json "atom") != atomId ||
      (← stringField json "primesieve_commit") != primesieveCommit ||
      (← stringField json "crlibm_commit") != crlibmCommit ||
      (← natField json "scale_bits") != 64 ||
      (← stringField json "log_interval_encoding") !=
        logIntervalEncoding ||
      (← stringField json "event_encoding") != eventEncoding ||
      (← stringField json "row_encoding") != rowEncoding ||
      (← parseStringList (← jsonField json "state_components")) !=
        stateComponents then
    throw "psi receipt fixed identity differs"
  pure {
    phase := ← parsePhase (← stringField json "mode")
    lower := ← natField json "lower"
    upperExclusive := ← natField json "upper_exclusive"
    workCount := ← natField json "work_count"
    sieveSizeKiB := ← natField json "sieve_size_kib"
    eventSHA256 := ← stringField json "event_sha256"
    rowSHA256 := ← stringField json "row_sha256"
    primePowerEvents := ← natField json "prime_power_events"
    primeEvents := ← natField json "prime_events"
    higherPowerEvents := ← natField json "higher_power_events"
    delta := ← parseState (← jsonField json "delta")
    guard := ← parseGuard (← jsonField json "guards")
    incomingState := ←
      parseOptionalState (← jsonField json "incoming_state")
    outgoingState := ←
      parseOptionalState (← jsonField json "outgoing_state")
    fallbacks := ← parseFallbacks (← jsonField json "exact_fallbacks")
    terminalStrictLowerChecked := ←
      boolField json "terminal_strict_lower_checked"
    accepted := ← boolField json "accepted"
    elapsedSeconds := ← numberField json "elapsed_seconds"
    executionAttested := ← boolField json "execution_attested"
    leanAtomDischarged := ← boolField json "lean_atom_discharged"
  }

private def isLowerHexCharacter (character : Char) : Bool :=
  ('0' ≤ character && character ≤ '9') ||
    ('a' ≤ character && character ≤ 'f')

def isLowerSHA256 (text : String) : Bool :=
  text.length == 64 && text.toList.all isLowerHexCharacter

private structure CompactScanState where
  depth : Nat := 0
  inString : Bool := false
  escaped : Bool := false
  valid : Bool := true

private def scanCompactCharacter
    (state : CompactScanState) (character : Char) : CompactScanState :=
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
  else if character.isWhitespace then
    { state with valid := false }
  else if character == '{' || character == '[' then
    let depth := state.depth + 1
    {
      state with
      depth
      valid := decide (depth ≤ maximumJsonNesting)
    }
  else if character == '}' || character == ']' then
    if state.depth = 0 then
      { state with valid := false }
    else
      { state with depth := state.depth - 1 }
  else
    state

def compactJsonSyntax (body : String) : Bool :=
  let state := body.foldl scanCompactCharacter {}
  body.startsWith "{" && body.endsWith "}" &&
    state.valid && !state.inString && !state.escaped && state.depth == 0

private def keyOccursExactlyOnce (body name : String) : Bool :=
  (body.splitOn ("\"" ++ name ++ "\":")).length == 2

private def lexicalFieldNames (phase : Phase) : List String :=
  receiptFieldNames ++ fallbackFieldNames ++
    match phase with
    | .summary => []
    | .verify => atomId :: singletonGuardFieldNames

private def lexicalFieldsUnique (body : String) (phase : Phase) : Bool :=
  (lexicalFieldNames phase).all (keyOccursExactlyOnce body)

/-- Total parser for exactly one newline-terminated compact C++ receipt. -/
def parseReceipt (raw : ByteArray) : Option Receipt := do
  if 0 < raw.size && raw.size ≤ maximumReceiptBytes then pure () else none
  let text ← String.fromUTF8? raw
  if text.endsWith "\n" then pure () else none
  let body := (text.dropEnd 1).toString
  if compactJsonSyntax body then pure () else none
  let json ← (Json.parse body).toOption
  let receipt ← (parseReceiptJson json).toOption
  if lexicalFieldsUnique body receipt.phase then pure receipt else none

namespace Receipt

def IsValid (receipt : Receipt) : Prop :=
  sourceLower ≤ receipt.lower ∧
    receipt.lower < receipt.upperExclusive ∧
    receipt.upperExclusive ≤ sourceUpperExclusive ∧
    receipt.upperExclusive = receipt.lower + receipt.workCount ∧
    16 ≤ receipt.sieveSizeKiB ∧ receipt.sieveSizeKiB ≤ 8192 ∧
    isLowerSHA256 receipt.eventSHA256 = true ∧
    isLowerSHA256 receipt.rowSHA256 = true ∧
    receipt.primePowerEvents =
      receipt.primeEvents + receipt.higherPowerEvents ∧
    receipt.primePowerEvents ≤ receipt.workCount ∧
    receipt.delta.InU128 ∧
    receipt.delta.lower ≤ receipt.delta.upper ∧
    receipt.delta.upper ≤
      receipt.primePowerEvents * 31 * 2 ^ 64 ∧
    receipt.fallbacks.lowerLeftLimit ≤ receipt.primePowerEvents ∧
    receipt.fallbacks.upperPostJump ≤ receipt.primePowerEvents ∧
    receipt.fallbacks.terminalLower ≤ 1 ∧
    0 ≤ receipt.elapsedSeconds.mantissa ∧
    receipt.accepted = true ∧
    receipt.executionAttested = false ∧
    receipt.leanAtomDischarged = false ∧
    match receipt.phase with
    | .summary =>
        receipt.guard = none ∧
          receipt.incomingState = none ∧
          receipt.outgoingState = none ∧
          receipt.fallbacks = ⟨0, 0, 0⟩ ∧
          receipt.terminalStrictLowerChecked = false
    | .verify =>
        match receipt.incomingState, receipt.outgoingState, receipt.guard with
        | some incoming, some outgoing, some guard =>
            incoming.InU128 ∧ outgoing.InU128 ∧
              incoming.lower ≤ incoming.upper ∧
              outgoing.lower ≤ outgoing.upper ∧
              guard.lower = incoming ∧ guard.upper = incoming ∧
              outgoing = incoming.add receipt.delta ∧
              receipt.terminalStrictLowerChecked =
                decide (receipt.upperExclusive = sourceUpperExclusive)
        | _, _, _ => False

instance (receipt : Receipt) : Decidable receipt.IsValid := by
  unfold IsValid
  cases receipt.phase with
  | summary =>
      infer_instance
  | verify =>
      cases receipt.incomingState <;>
        cases receipt.outgoingState <;>
        cases receipt.guard <;>
        infer_instance

def check (receipt : Receipt) : Bool :=
  decide receipt.IsValid

@[simp] theorem check_eq_true (receipt : Receipt) :
    receipt.check = true ↔ receipt.IsValid := by
  simp [check]

end Receipt

def ValidatedReceipt (raw : ByteArray) : Prop :=
  ∃ receipt, parseReceipt raw = some receipt ∧ receipt.IsValid

def checkReceipt (raw : ByteArray) : Bool :=
  match parseReceipt raw with
  | none => false
  | some receipt => receipt.check

theorem checkReceipt_sound {raw : ByteArray}
    (hcheck : checkReceipt raw = true) :
    ValidatedReceipt raw := by
  unfold checkReceipt at hcheck
  cases hparse : parseReceipt raw with
  | none =>
      simp [hparse] at hcheck
  | some receipt =>
      exact ⟨receipt, hparse,
        (Receipt.check_eq_true receipt).mp (by
          simpa [hparse] using hcheck)⟩

structure ReceiptPair where
  summary : Receipt
  verification : Receipt
  deriving Repr, DecidableEq

namespace ReceiptPair

def IsValid (pair : ReceiptPair) : Prop :=
  pair.summary.IsValid ∧ pair.verification.IsValid ∧
    pair.summary.phase = .summary ∧
    pair.verification.phase = .verify ∧
    pair.summary.lower = pair.verification.lower ∧
    pair.summary.upperExclusive = pair.verification.upperExclusive ∧
    pair.summary.workCount = pair.verification.workCount ∧
    pair.summary.sieveSizeKiB = pair.verification.sieveSizeKiB ∧
    pair.summary.eventSHA256 = pair.verification.eventSHA256 ∧
    pair.summary.rowSHA256 = pair.verification.rowSHA256 ∧
    pair.summary.primePowerEvents =
      pair.verification.primePowerEvents ∧
    pair.summary.primeEvents = pair.verification.primeEvents ∧
    pair.summary.higherPowerEvents =
      pair.verification.higherPowerEvents ∧
    pair.summary.delta = pair.verification.delta

instance (pair : ReceiptPair) : Decidable pair.IsValid := by
  unfold IsValid
  infer_instance

def check (pair : ReceiptPair) : Bool :=
  decide pair.IsValid

@[simp] theorem check_eq_true (pair : ReceiptPair) :
    pair.check = true ↔ pair.IsValid := by
  simp [check]

end ReceiptPair

def parseReceiptPair
    (summaryRaw verificationRaw : ByteArray) : Option ReceiptPair := do
  let summary ← parseReceipt summaryRaw
  let verification ← parseReceipt verificationRaw
  pure { summary, verification }

def ValidatedReceiptPair
    (summaryRaw verificationRaw : ByteArray) : Prop :=
  ∃ pair,
    parseReceiptPair summaryRaw verificationRaw = some pair ∧
      pair.IsValid

def checkReceiptPair
    (summaryRaw verificationRaw : ByteArray) : Bool :=
  match parseReceiptPair summaryRaw verificationRaw with
  | none => false
  | some pair => pair.check

theorem checkReceiptPair_sound
    {summaryRaw verificationRaw : ByteArray}
    (hcheck : checkReceiptPair summaryRaw verificationRaw = true) :
    ValidatedReceiptPair summaryRaw verificationRaw := by
  unfold checkReceiptPair at hcheck
  cases hparse : parseReceiptPair summaryRaw verificationRaw with
  | none =>
      simp [hparse] at hcheck
  | some pair =>
      exact ⟨pair, hparse,
        (ReceiptPair.check_eq_true pair).mp (by
          simpa [hparse] using hcheck)⟩

abbrev RawReceiptPair := ByteArray × ByteArray

def parseReceiptPairs :
    List RawReceiptPair → Option (List ReceiptPair)
  | [] => some []
  | raw :: rest => do
      let pair ← parseReceiptPair raw.1 raw.2
      let pairs ← parseReceiptPairs rest
      pure (pair :: pairs)

def allPairsValid : List ReceiptPair → Bool
  | [] => true
  | pair :: rest => pair.check && allPairsValid rest

theorem allPairsValid_sound {pairs : List ReceiptPair}
    (hcheck : allPairsValid pairs = true) :
    ∀ pair ∈ pairs, pair.IsValid := by
  induction pairs with
  | nil =>
      simp
  | cons head tail ih =>
      simp only [allPairsValid, Bool.and_eq_true] at hcheck
      intro pair hmem
      simp only [List.mem_cons] at hmem
      rcases hmem with hpair | htail
      · subst pair
        exact (ReceiptPair.check_eq_true head).mp hcheck.1
      · exact ih hcheck.2 pair htail

def replayChain :
    Nat → Nat → Q64State → Nat → List ReceiptPair →
      Option (Nat × Q64State × Nat)
  | expectedLower, _sieveSizeKiB, incoming, totalEvents, [] =>
      some (expectedLower, incoming, totalEvents)
  | expectedLower, sieveSizeKiB, incoming, totalEvents, pair :: rest => do
      if pair.summary.lower = expectedLower &&
          pair.summary.sieveSizeKiB = sieveSizeKiB &&
          pair.verification.incomingState = some incoming then
        pure ()
      else
        none
      let outgoing ← pair.verification.outgoingState
      replayChain pair.summary.upperExclusive sieveSizeKiB outgoing
        (totalEvents + pair.summary.primePowerEvents) rest

def checkBoundedCampaign
    (lower upperExclusive sieveSizeKiB expectedEvents : Nat)
    (rawPairs : List RawReceiptPair) : Bool :=
  match parseReceiptPairs rawPairs with
  | none => false
  | some pairs =>
      allPairsValid pairs &&
        (replayChain lower sieveSizeKiB Q64State.zero 0 pairs).any
          (fun result =>
            result.1 = upperExclusive && result.2.2 = expectedEvents)

def sourceShardLower (index : Nat) : Nat :=
  sourceLower + index * sourceShardSpan

def sourceShardUpperExclusive (index : Nat) : Nat :=
  min sourceUpperExclusive
    (sourceLower + (index + 1) * sourceShardSpan)

def sourceGeometryFrom : Nat → List ReceiptPair → Bool
  | _, [] => true
  | index, pair :: rest =>
      pair.summary.lower == sourceShardLower index &&
        pair.summary.upperExclusive == sourceShardUpperExclusive index &&
      pair.summary.sieveSizeKiB == productionSieveSizeKiB &&
        sourceGeometryFrom (index + 1) rest

def sourceReplayCheck (pairs : List ReceiptPair) : Bool :=
  match replayChain sourceLower productionSieveSizeKiB Q64State.zero 0 pairs with
  | none => false
  | some (upperExclusive, _, totalEvents) =>
      upperExclusive == sourceUpperExclusive &&
        totalEvents == sourceEventCount

/-- Source-scale wire checker over the actual 200,000 retained JSON receipts.

This function is total but is not evaluated in this repository.  Successful
evaluation proves only receipt syntax, the fixed two-pass chain, and opaque
commitment equality; see `ValidatedSourceWire` below. -/
def checkSourceCampaign (rawPairs : List RawReceiptPair) : Bool :=
  match parseReceiptPairs rawPairs with
  | none => false
  | some pairs =>
      pairs.length == sourceShardCount &&
        sourceGeometryFrom 0 pairs &&
        allPairsValid pairs &&
        sourceReplayCheck pairs

/-- Exact, deliberately non-analytic meaning of source-wire acceptance. -/
def ValidatedSourceWire (rawPairs : List RawReceiptPair) : Prop :=
  ∃ pairs finalState,
    parseReceiptPairs rawPairs = some pairs ∧
      pairs.length = sourceShardCount ∧
      sourceGeometryFrom 0 pairs = true ∧
      allPairsValid pairs = true ∧
      replayChain sourceLower productionSieveSizeKiB Q64State.zero 0 pairs =
        some (sourceUpperExclusive, finalState, sourceEventCount)

theorem checkSourceCampaign_sound {rawPairs : List RawReceiptPair}
    (hcheck : checkSourceCampaign rawPairs = true) :
    ValidatedSourceWire rawPairs := by
  unfold checkSourceCampaign at hcheck
  cases hparse : parseReceiptPairs rawPairs with
  | none =>
      simp [hparse] at hcheck
  | some pairs =>
      simp only [hparse, Bool.and_eq_true,
        beq_iff_eq] at hcheck
      rcases hcheck with
        ⟨⟨⟨hlength, hgeometry⟩, hall⟩, hreplayCheck⟩
      unfold sourceReplayCheck at hreplayCheck
      cases hreplay :
          replayChain sourceLower productionSieveSizeKiB
            Q64State.zero 0 pairs with
      | none =>
          simp [hreplay] at hreplayCheck
      | some result =>
          rcases result with ⟨upperExclusive, finalState, totalEvents⟩
          simp only [hreplay, Bool.and_eq_true,
            beq_iff_eq] at hreplayCheck
          exact ⟨pairs, finalState, hparse, hlength, hgeometry, hall,
            by simpa [hreplayCheck.1, hreplayCheck.2] using hreplay⟩

theorem checkSourceCampaign_everyPairValid
    {rawPairs : List RawReceiptPair}
    (hcheck : checkSourceCampaign rawPairs = true) :
    ∃ pairs,
      parseReceiptPairs rawPairs = some pairs ∧
        ∀ pair ∈ pairs, pair.IsValid := by
  rcases checkSourceCampaign_sound hcheck with
    ⟨pairs, _, hparse, _, _, hall, _⟩
  exact ⟨pairs, hparse, allPairsValid_sound hall⟩

structure MissingRealizationObligations where
  retainedRows : String
  directedLogSoundness : String
  rosterAndGapCoverage : String
  executionBinding : String
  deriving Repr, DecidableEq

/-- The exact boundary left after the compact receipt wire is accepted. -/
def missing : MissingRealizationObligations where
  retainedRows :=
    "The C++ receipts retain SHA-256 commitments, not the 346,065,767,406 \
prime-power rows and their directed Q64 logarithm endpoints."
  directedLogSoundness :=
    "Ordinary Lean must connect the pinned CRlibm binary64 endpoints and \
exact binary64-to-Q64 decoder to lower and upper bounds on Mathlib Real.log."
  rosterAndGapCoverage :=
    "A data artifact and checker must prove complete, ordered, duplicate-free \
prime/prime-power coverage, state constancy between events, and the initial \
[1,2) gap through the closed endpoint 10^13."
  executionBinding :=
    "A reviewed compiler/CPU refinement or the separately declared trusted \
compute receipt boundary must bind these parsed bytes to execution of the \
pinned producer; this wire does not authenticate a machine."

end SparkInterval.TernaryGoldbach.PsiShardReceiptWire
