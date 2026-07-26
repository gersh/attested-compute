/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

/-!
# Typed archive for the Sqrt218 finite computation

This module is the architecture-neutral typed image of the canonical JSON
archive consumed by `tg_verifier.sqrt218_certificate_verifier`.  It contains
no production rows and evaluating it performs no finite replay.

The strict, data-independent V1 byte decoder is in the sibling `Wire` module.
Keeping it separate means users of the typed arithmetic model do not parse or
hash an artifact merely by importing this type.  Neither module asserts that
a signed receipt supplied particular bytes or that a measured physical
executable refines the operational evaluator; those remain explicit
integration boundaries.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

/-- One typed row of the certificate's `primes` array.

The factor list is the complete factorization of `prime - 1`, with
multiplicity.  `witness` is the Lucas witness used by the independent
verifier. -/
structure PrimeRow where
  prime : Nat
  witness : Nat
  factors : List Nat
  logLower : Nat
  logUpper : Nat
  deriving Repr, DecidableEq, Inhabited

/-- One typed row of the certificate's ordered `events` array. -/
structure PowerEvent where
  power : Nat
  primeIndex : Nat
  exponent : Nat
  deriving Repr, DecidableEq, Inhabited

/-- The small summary emitted after the full streaming replay.

Digest strings remain ordinary values here.  The operational checker in the
sibling module recomputes them from exact transcript strings; this type alone
gives a digest no mathematical authority. -/
structure Summary where
  anchorSlack : Nat
  finalPsiLower : Nat
  finalWeightedUpper : Nat
  fixedScanDigest : String
  layoutDigest : String
  minimumHeadIndex : Nat
  minimumHeadSlack : Nat
  primePowerEventCount : Nat
  prattDigest : String
  primeCount : Nat
  properPrimePowerEventCount : Nat
  reusedPrimeCount : Nat
  tailPrimeCount : Nat
  deriving Repr, DecidableEq

/-- Public, data-independent parameters of one finite replay profile.

Production selects `some expectedSummary`, binding the complete known
transcript.  `none` is reserved for samples and development KATs.  Keeping
the value in the profile lets the operational IR stay data-independent while
still making the registered production invocation exact. -/
structure Profile where
  bound : Nat
  reusedPrimeBound : Nat
  logSeedAt : Nat
  logScale : Nat
  reciprocalScale : Nat
  expectedSummary : Option Summary
  deriving Repr, DecidableEq

/-- Exact protocol discriminator required by the canonical wire format. -/
def certificateKind : String :=
  "sparkinterval.sqrt218-finite-certificate.v1"

/-- Typed image of the complete Sqrt218 certificate archive.

`kind`, `schemaVersion`, and the three arithmetic constants are retained even
though a registered profile also supplies the numeric values: the independent
verifier rejects an archive that changes any of these header fields. -/
structure Archive where
  kind : String
  schemaVersion : Nat
  bound : Nat
  logSeedAt : Nat
  logScale : Nat
  reciprocalScale : Nat
  primes : List PrimeRow
  events : List PowerEvent
  summary : Summary
  deriving Repr, DecidableEq

namespace Archive

/-- Prime values in archive order. -/
def primeValues (archive : Archive) : List Nat :=
  archive.primes.map PrimeRow.prime

end Archive

/-! ## Exact ASCII transcript fragments

These definitions mirror the producer and independent verifier.  They are
kept with the typed format so later decoder/refinement work has one canonical
target rather than a second ad hoc transcript language.
-/

private def commaSeparatedNats : List Nat → String
  | [] => ""
  | first :: rest =>
      rest.foldl (fun text value => text ++ "," ++ toString value)
        (toString first)

/-- Exact Pratt/Lucas transcript row hashed by both Python implementations. -/
def PrimeRow.prattTranscript (row : PrimeRow) : String :=
  toString row.prime ++ ":" ++ toString row.witness ++ ":" ++
    commaSeparatedNats row.factors ++ "\n"

/-- Exact concatenated Pratt/Lucas transcript. -/
def Archive.prattTranscript (archive : Archive) : String :=
  archive.primes.foldl
    (fun text row => text ++ row.prattTranscript) ""

private def eventIndicesForPrimeAux
    (targetPrimeIndex : Nat) : Nat → List PowerEvent → List Nat
  | _, [] => []
  | eventIndex, event :: rest =>
      let tail :=
        eventIndicesForPrimeAux targetPrimeIndex (eventIndex + 1) rest
      if event.primeIndex = targetPrimeIndex then
        eventIndex :: tail
      else
        tail

/-- Positions in the globally ordered event stream belonging to one prime. -/
def Archive.eventIndicesForPrime
    (archive : Archive) (primeIndex : Nat) : List Nat :=
  eventIndicesForPrimeAux primeIndex 0 archive.events

private def primeLayoutTranscript :
    Nat → List PrimeRow → Archive → String
  | _, [], _ => ""
  | primeIndex, row :: rest, archive =>
      let indices := archive.eventIndicesForPrime primeIndex
      "prime:" ++ toString primeIndex ++ ":" ++ toString row.prime ++
        ":count=" ++ toString indices.length ++ ":map=" ++
        commaSeparatedNats indices ++ "\n" ++
        primeLayoutTranscript (primeIndex + 1) rest archive

private def eventLayoutTranscript : Nat → List PowerEvent → String
  | _, [] => ""
  | eventIndex, event :: rest =>
      "event:" ++ toString eventIndex ++ ":" ++ toString event.power ++
        ":" ++ toString event.primeIndex ++ ":" ++
        toString event.exponent ++ ":sqrt=" ++
        toString (Nat.sqrt event.power) ++ "\n" ++
        eventLayoutTranscript (eventIndex + 1) rest

/-- Exact prime-power layout transcript hashed by the Python implementations. -/
def Archive.layoutTranscript (archive : Archive) : String :=
  primeLayoutTranscript 0 archive.primes archive ++
    eventLayoutTranscript 0 archive.events

end SparkInterval.TernaryGoldbach.Sqrt218Operational
