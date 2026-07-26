/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedChirpStateWire
import SparkInterval.Dirichlet.CertifiedFFTRootTableWire

/-!
# Experimental theorem-backed DFT-root parameter sweep

This executable varies only the number of Taylor terms and the number of
double-angle climb steps in the same exact-rational construction used by
`CertifiedRootTable.rootRectFast?`.  It exists to qualify a production
configuration; it is not imported by the production checker.

Every accepted raw binary64 box is checked against a rational rectangle whose
containment of the exact DFT root is proved below.  The native executable is
still unattested and does not establish compiler refinement.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedRootParameterSweep

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.CertifiedRootWire

/-- Exact-rational endpoint check for one raw production box. -/
def checkConfigured
    (terms depth workPrecision outputPrecision order exponent : Nat)
    (raw : RawComplexBox) : Bool :=
  match raw.decodeFinite,
      CertifiedRootTable.rootRectConfigured?
        terms depth workPrecision outputPrecision
        order exponent with
  | some outer, some inner => decide (RationallyEncloses outer inner)
  | _, _ => false

theorem checkConfigured_sound
    {terms : Nat} (hterms : 0 < terms)
    {depth workPrecision outputPrecision order exponent : Nat}
    {raw : RawComplexBox}
    (hcheck :
      checkConfigured terms depth workPrecision outputPrecision
        order exponent raw = true) :
    ∃ (outer : ComplexRect) (hvalid : outer.IsValid),
      raw.decodeFinite = some outer ∧
      (toComplexInterval outer hvalid).Contains
        (FactoredSmallQDFT.unitRoot order exponent) := by
  unfold checkConfigured at hcheck
  cases houter : raw.decodeFinite with
  | none => simp [houter] at hcheck
  | some outer =>
      cases hinner :
          CertifiedRootTable.rootRectConfigured?
            terms depth workPrecision outputPrecision
            order exponent with
      | none => simp [houter, hinner] at hcheck
      | some inner =>
          simp only [houter, hinner, decide_eq_true_eq] at hcheck
          let hvalid := RawComplexBox.decodeFinite_isValid houter
          exact
            ⟨outer, hvalid, rfl,
              CertifiedBluesteinRootBridge.contains_of_enclosesRect
                (rationallyEncloses_to_enclosesRect hvalid hcheck)
                (CertifiedRootTable.rootRectConfigured?_containsComplex
                  hterms hinner)⟩

structure Configuration where
  terms : Nat
  depth : Nat
  workPrecision : Nat
  outputPrecision : Nat
  deriving Repr

private def parseNat (label value : String) : IO Nat := do
  let some result := value.toNat?
    | throw <| IO.userError s!"{label} must be a natural number"
  pure result

private def parseConfiguration
    (termsText depthText workText outputText : String) :
    IO Configuration := do
  let terms ← parseNat "terms" termsText
  if terms = 0 then
    throw <| IO.userError "terms must be positive"
  pure
    { terms
      depth := ← parseNat "depth" depthText
      workPrecision := ← parseNat "work precision" workText
      outputPrecision := ← parseNat "output precision" outputText }

private def rectWidth (R : ComplexRect) : ℚ :=
  (R.re.hi - R.re.lo) + (R.im.hi - R.im.lo)

private def maxComponentWidth (R : ComplexRect) : ℚ :=
  max (R.re.hi - R.re.lo) (R.im.hi - R.im.lo)

structure RootMetrics where
  innerWidth : ℚ
  endpointMargins : List ℚ

/-- Diagnostic data computed only after the exact production enclosure test
has passed.  This does not replace `checkConfigured`; the qualification modes
below still use that theorem-backed Boolean as their acceptance gate. -/
private def rootMetrics?
    (terms depth workPrecision outputPrecision order exponent : Nat)
    (raw : RawComplexBox) : Option RootMetrics := do
  let outer ← raw.decodeFinite
  let inner ←
    CertifiedRootTable.rootRectConfigured?
      terms depth workPrecision outputPrecision order exponent
  if decide (RationallyEncloses outer inner) then
    some
      { innerWidth := maxComponentWidth inner
        endpointMargins :=
          [inner.re.lo - outer.re.lo,
           outer.re.hi - inner.re.hi,
           inner.im.lo - outer.im.lo,
           outer.im.hi - inner.im.hi] }
  else
    none

private def updateMinimumPositive
    (current : Option ℚ) (values : List ℚ) : Option ℚ :=
  values.foldl
    (fun result value =>
      if value ≤ 0 then result
      else
        match result with
        | none => some value
        | some previous => some (min previous value))
    current

private def benchmark
    (configuration : Configuration) (order count : Nat) : IO UInt32 := do
  if order = 0 then
    throw <| IO.userError "order must be positive"
  let mut checksum : ℚ := 0
  let mut widest : ℚ := 0
  for exponent in [0:count] do
    match CertifiedRootTable.rootRectConfigured?
        configuration.terms configuration.depth
        configuration.workPrecision configuration.outputPrecision
        order exponent with
    | none =>
        IO.eprintln s!"rejected exponent={exponent}"
        return 1
    | some rectangle =>
        let width := rectWidth rectangle
        checksum := checksum + width
        widest := max widest width
  IO.println <|
    "{\"accepted\":true," ++
    "\"mode\":\"benchmark\"," ++
    "\"terms\":" ++ toString configuration.terms ++ "," ++
    "\"depth\":" ++ toString configuration.depth ++ "," ++
    "\"work_precision\":" ++ toString configuration.workPrecision ++ "," ++
    "\"output_precision\":" ++ toString configuration.outputPrecision ++ "," ++
    "\"order\":" ++ toString order ++ "," ++
    "\"root_count\":" ++ toString count ++ "," ++
    "\"checksum\":\"" ++ toString checksum ++ "\"," ++
    "\"widest\":\"" ++ toString widest ++ "\"}"
  pure 0

private def checkChirpRange
    (configuration : Configuration) (raw : ByteArray)
    (length start count : Nat) (reportMetrics : Bool := false) : IO UInt32 := do
  if length = 0 then
    throw <| IO.userError "length must be positive"
  if raw.size !=
      CertifiedChirpStateWire.recordBytes * length then
    throw <| IO.userError "chirp dump has the wrong exact byte length"
  if length < start + count then
    throw <| IO.userError "chirp range exceeds the declared length"
  let mut widestInner : ℚ := 0
  let mut minimumPositiveMargin : Option ℚ := none
  for offset in [0:count] do
    let index := start + offset
    let some row := CertifiedChirpStateWire.readRow? raw index
      | IO.eprintln s!"rejected index={index} component=malformed_row"
        return 1
    if !checkConfigured
        configuration.terms configuration.depth
        configuration.workPrecision configuration.outputPrecision
        (2 * length) (index ^ 2) row.chirp then
      IO.eprintln s!"rejected index={index} component=chirp"
      return 1
    if reportMetrics then
      let some metrics :=
          rootMetrics?
            configuration.terms configuration.depth
            configuration.workPrecision configuration.outputPrecision
            (2 * length) (index ^ 2) row.chirp
        | throw <| IO.userError "internal chirp metric mismatch"
      widestInner := max widestInner metrics.innerWidth
      minimumPositiveMargin :=
        updateMinimumPositive minimumPositiveMargin metrics.endpointMargins
    if !checkConfigured
        configuration.terms configuration.depth
        configuration.workPrecision configuration.outputPrecision
        (2 * length) (2 * index + 1) row.oddStep then
      IO.eprintln s!"rejected index={index} component=odd_step"
      return 1
    if reportMetrics then
      let some metrics :=
          rootMetrics?
            configuration.terms configuration.depth
            configuration.workPrecision configuration.outputPrecision
            (2 * length) (2 * index + 1) row.oddStep
        | throw <| IO.userError "internal odd-step metric mismatch"
      widestInner := max widestInner metrics.innerWidth
      minimumPositiveMargin :=
        updateMinimumPositive minimumPositiveMargin metrics.endpointMargins
  let reportPrefix :=
    "{\"accepted\":true," ++
    "\"mode\":\"chirp\"," ++
    "\"terms\":" ++ toString configuration.terms ++ "," ++
    "\"depth\":" ++ toString configuration.depth ++ "," ++
    "\"work_precision\":" ++ toString configuration.workPrecision ++ "," ++
    "\"output_precision\":" ++ toString configuration.outputPrecision ++ "," ++
    "\"length\":" ++ toString length ++ "," ++
    "\"start\":" ++ toString start ++ "," ++
    "\"row_count\":" ++ toString count ++ "," ++
    "\"roots_checked\":" ++ toString (2 * count)
  if reportMetrics then
    IO.println <|
      reportPrefix ++
      ",\"widest_inner_component\":\"" ++ toString widestInner ++ "\"," ++
      "\"minimum_positive_endpoint_margin\":" ++
        (match minimumPositiveMargin with
         | none => "null"
         | some margin => "\"" ++ toString margin ++ "\"") ++ "}"
  else
    IO.println <| reportPrefix ++ "}"
  pure 0

private def checkFftRange
    (configuration : Configuration) (raw : ByteArray)
    (length start count : Nat) (reportMetrics : Bool := false) : IO UInt32 := do
  if !CertifiedFFTRootTableWire.sourceConvolution length then
    throw <| IO.userError "unsupported FFT convolution length"
  let rootCount := length - 1
  if raw.size !=
      CertifiedFFTRootTableWire.recordBytes * rootCount then
    throw <| IO.userError "FFT-root dump has the wrong exact byte length"
  if rootCount < start + count then
    throw <| IO.userError "FFT-root range exceeds the declared length"
  let mut widestInner : ℚ := 0
  let mut minimumPositiveMargin : Option ℚ := none
  for offset in [0:count] do
    let index := start + offset
    let some root := CertifiedFFTRootTableWire.readRoot? raw index
      | IO.eprintln s!"rejected flat_index={index} component=malformed_record"
        return 1
    let spec := CertifiedFFTRootTableWire.specAtFlatIndex index
    if !checkConfigured
        configuration.terms configuration.depth
        configuration.workPrecision configuration.outputPrecision
        spec.stage spec.exponent root then
      IO.eprintln <|
        s!"rejected flat_index={index} stage={spec.stage} " ++
        s!"exponent={spec.exponent} component=root"
      return 1
    if reportMetrics then
      let some metrics :=
          rootMetrics?
            configuration.terms configuration.depth
            configuration.workPrecision configuration.outputPrecision
            spec.stage spec.exponent root
        | throw <| IO.userError "internal FFT-root metric mismatch"
      widestInner := max widestInner metrics.innerWidth
      minimumPositiveMargin :=
        updateMinimumPositive minimumPositiveMargin metrics.endpointMargins
  let reportPrefix :=
    "{\"accepted\":true," ++
    "\"mode\":\"fft\"," ++
    "\"terms\":" ++ toString configuration.terms ++ "," ++
    "\"depth\":" ++ toString configuration.depth ++ "," ++
    "\"work_precision\":" ++ toString configuration.workPrecision ++ "," ++
    "\"output_precision\":" ++ toString configuration.outputPrecision ++ "," ++
    "\"length\":" ++ toString length ++ "," ++
    "\"start\":" ++ toString start ++ "," ++
    "\"root_count\":" ++ toString count
  if reportMetrics then
    IO.println <|
      reportPrefix ++
      ",\"widest_inner_component\":\"" ++ toString widestInner ++ "\"," ++
      "\"minimum_positive_endpoint_margin\":" ++
        (match minimumPositiveMargin with
         | none => "null"
         | some margin => "\"" ++ toString margin ++ "\"") ++ "}"
  else
    IO.println <| reportPrefix ++ "}"
  pure 0

private def readFile (path : String) : IO ByteArray :=
  IO.FS.readBinFile (path : System.FilePath)

private def usage : String :=
  "usage:\n" ++
  "  benchmark TERMS DEPTH WORK OUTPUT ORDER COUNT\n" ++
  "  chirp|chirp-metrics FILE LENGTH START COUNT TERMS DEPTH WORK OUTPUT\n" ++
  "  fft|fft-metrics FILE LENGTH START COUNT TERMS DEPTH WORK OUTPUT"

def run (arguments : List String) : IO UInt32 := do
  match arguments with
  | ["benchmark", termsText, depthText, workText, outputText,
      orderText, countText] =>
      let configuration ←
        parseConfiguration termsText depthText workText outputText
      benchmark configuration
        (← parseNat "order" orderText) (← parseNat "count" countText)
  | ["chirp", path, lengthText, startText, countText,
      termsText, depthText, workText, outputText] =>
      let configuration ←
        parseConfiguration termsText depthText workText outputText
      checkChirpRange configuration (← readFile path)
        (← parseNat "length" lengthText)
        (← parseNat "start" startText)
        (← parseNat "count" countText)
  | ["chirp-metrics", path, lengthText, startText, countText,
      termsText, depthText, workText, outputText] =>
      let configuration ←
        parseConfiguration termsText depthText workText outputText
      checkChirpRange configuration (← readFile path)
        (← parseNat "length" lengthText)
        (← parseNat "start" startText)
        (← parseNat "count" countText) true
  | ["fft", path, lengthText, startText, countText,
      termsText, depthText, workText, outputText] =>
      let configuration ←
        parseConfiguration termsText depthText workText outputText
      checkFftRange configuration (← readFile path)
        (← parseNat "length" lengthText)
        (← parseNat "start" startText)
        (← parseNat "count" countText)
  | ["fft-metrics", path, lengthText, startText, countText,
      termsText, depthText, workText, outputText] =>
      let configuration ←
        parseConfiguration termsText depthText workText outputText
      checkFftRange configuration (← readFile path)
        (← parseNat "length" lengthText)
        (← parseNat "start" startText)
        (← parseNat "count" countText) true
  | _ =>
      IO.eprintln usage
      pure 2

#print axioms CertifiedRootTable.rootRectConfigured?_containsComplex
#print axioms checkConfigured_sound

end SparkInterval.Tests.CertifiedRootParameterSweep

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Tests.CertifiedRootParameterSweep.run arguments
