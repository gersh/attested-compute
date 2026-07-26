/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import TGComputeContracts.Sqrt218.Source

/-!
# Public source boundary and protocol pins for Helfgott (2.18)

The mathematical proposition lives in the package-neutral
`TGComputeContracts.Sqrt218` module.  This compatibility module preserves the
public names consumed by `claude_math` and records only the reviewed protocol
pins used by the staged cloud invocation.

It contains no replay trace, source-scale evidence, receipt, axiom, production
archive, or successful-run assertion.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics

/-! ## Stable public aliases -/

/-- Finite endpoint in Helfgott's bounded check for (2.18). -/
abbrev sourceCutoff : Nat :=
  TGComputeContracts.Sqrt218.sourceCutoff

/-- The literal square-root-weighted von Mangoldt sum in the source claim. -/
noncomputable abbrev vonMangoldtSqrtNat (N : Nat) : Real :=
  TGComputeContracts.Sqrt218.vonMangoldtSqrtNat N

/-- Exact bounded proposition consumed by the ordinary-Lean Abel
continuation. -/
abbrev SourceClaim : Prop :=
  TGComputeContracts.Sqrt218.SourceClaim

/-! ## Reviewed ordinary-computation transcript pins

These values are copied from the completed ordinary-kernel certificate.
Keeping them next to the public source alias makes the staged
full-recomputation cloud input human-auditable and prevents an accepted receipt
from silently selecting a different finite scan.  They are protocol constants,
not proofs and not a substitute for a reviewed production deployment.
-/

def reusedPrimeBound : Nat := 1_517_397
def fixedPointScale : Nat := 281_474_976_710_656
def reciprocalScale : Nat := 1_073_741_824
def logSeedCount : Nat := 30
def logLadderDepth : Nat := 14

def expectedPrimeCount : Nat := 148_933
def expectedReusedPrimeCount : Nat := 115_408
def expectedTailPrimeCount : Nat := 33_525
def expectedPrimePowerEventCount : Nat := 149_235
def expectedProperPrimePowerEventCount : Nat := 302

def expectedMinimumHeadSlack : Nat :=
  77_167_896_433_454_640_411_789_476

def expectedMinimumHeadIndex : Nat := 6_397

def expectedAnchorSlack : Nat :=
  2_134_933_357_595_048_382_226_455_716

def expectedFinalWeightedUpper : Nat :=
  854_091_852_238_662_506_255_905_837

def expectedFinalPsiLower : Nat :=
  562_949_761_260_501_289_147

def expectedPrattDigest : String :=
  "46b67778699d196eec624ba71f8fc07de9d0218afbd0a0930c2113e37ddbfd07"

def expectedLayoutDigest : String :=
  "c7a559cf7dd1a38c97e73b224a4021a44c62f68d2ad17f1a50a31f72c1ca1055"

def expectedFixedScanDigest : String :=
  "0eda447334b59b886d3d2b70e3aed3a8375823dbc1180e190e0ad67517e9c559"

/-- Human-readable source statement bound into the canonical cloud input. -/
def sourceStatement : String :=
  "For the complete prime and prime-power rosters through 2,000,000, " ++
  "the directed scale-2^48 prime-log ladder and scale-2^30 reciprocal-" ++
  "square-root scan satisfy every integer head guard in Helfgott (2.18) " ++
  "and its endpoint Abel anchor, with the exact pinned final state."

/-- Fully qualified Lean result type named in the canonical cloud input. -/
def leanClaimName : String :=
  "SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim"

end SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics

end
