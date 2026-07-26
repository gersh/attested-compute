/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFDecoder

/-!
# Data-only transitive child manifests

This module defines the small binary manifest consumed by a confidential-CPU
finalizer after one or more heavy child jobs.  It deliberately records only
data:

* an exact campaign tag and coverage interval;
* the expected backend of every child, in order;
* gap-free ordinal and range coverage;
* one nonzero receipt, artifact, and result digest per child; and
* a predecessor-digest chain rooted at a campaign-specific digest.

The parser is total and rejects truncation, trailing bytes, unknown backends,
and noncanonical framing.  `check` is also total and kernel-reducible.

For a linear campaign the coverage coordinate can be the mathematical source
index (R2Star uses `[1, 21000000001)`).  A branched campaign may instead use
the canonical flattened child ordinal interval.  The campaign specification,
not this generic wire module, fixes that interpretation.

Passing this check does **not** authenticate a receipt and does not establish
the mathematical meaning of an artifact.  A campaign finalizer must
additionally verify every complete signed receipt and independently replay the
retained arithmetic artifact.  Keeping that distinction explicit prevents a
GPU signature or a digest-only manifest from being mistaken for source
evidence.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.TransitiveChildManifest

open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder

/-- The two production backends currently used by the Goldbach campaign DAGs. -/
inductive Backend where
  | azureSEVSNPCPU
  | azureNCCadsH100v5
  deriving Repr, DecidableEq, BEq

namespace Backend

def tag : Backend → Nat
  | .azureSEVSNPCPU => 1
  | .azureNCCadsH100v5 => 2

def ofTag? : Nat → Option Backend
  | 1 => some .azureSEVSNPCPU
  | 2 => some .azureNCCadsH100v5
  | _ => none

@[simp] theorem ofTag?_tag (backend : Backend) :
    ofTag? backend.tag = some backend := by
  cases backend <;> rfl

end Backend

/-- A raw SHA-256 digest retained as exactly 32 bytes. -/
structure Digest32 where
  bytes : ByteArray
  deriving DecidableEq

namespace Digest32

instance : BEq Digest32 where
  beq left right := left.bytes == right.bytes

def zero : Digest32 where
  bytes := (List.replicate 32 (0 : UInt8)).toByteArray

def Nonzero (digest : Digest32) : Prop :=
  digest.bytes.size = 32 ∧ digest ≠ zero

instance (digest : Digest32) : Decidable digest.Nonzero := by
  unfold Nonzero
  infer_instance

end Digest32

/-- One child entry in canonical topological order. -/
structure Child where
  ordinal : Nat
  lower : Nat
  upper : Nat
  backend : Backend
  receiptDigest : Digest32
  artifactDigest : Digest32
  resultDigest : Digest32
  predecessorDigest : Digest32
  deriving DecidableEq

/-- Complete data-only finalizer manifest. -/
structure Manifest where
  schemaVersion : Nat
  campaignTag : Nat
  sourceLower : Nat
  sourceUpper : Nat
  rootDigest : Digest32
  children : List Child
  deriving DecidableEq

/-- Campaign-owned exact topology and coverage parameters. -/
structure Spec where
  campaignTag : Nat
  sourceLower : Nat
  sourceUpper : Nat
  rootDigest : Digest32
  expectedBackends : List Backend
  deriving DecidableEq

def schemaVersion : Nat := 1

/-- Eight-byte wire magic `TGCHLD01`. -/
def magic : List UInt8 :=
  [84, 71, 67, 72, 76, 68, 48, 49]

def headerSize : Nat := 62
def childSize : Nat := 149

/-- Canonical fixed-width little-endian encoding, truncating values which do
not fit. Campaign encoders prove or externally check their range bounds before
installing an artifact. -/
def encodeNatLE (width value : Nat) : List UInt8 :=
  (List.range width).map (fun index =>
    UInt8.ofNat ((value / 256 ^ index) % 256))

namespace Child

def encode (child : Child) : List UInt8 :=
  encodeNatLE 4 child.ordinal ++
    encodeNatLE 8 child.lower ++
    encodeNatLE 8 child.upper ++
    [UInt8.ofNat child.backend.tag] ++
    child.receiptDigest.bytes.toList ++
    child.artifactDigest.bytes.toList ++
    child.resultDigest.bytes.toList ++
    child.predecessorDigest.bytes.toList

end Child

/-- Canonical binary encoding used by generated, source-installed manifests. -/
def Manifest.encode (manifest : Manifest) : ByteArray :=
  (magic ++
    encodeNatLE 1 manifest.schemaVersion ++
    encodeNatLE 1 manifest.campaignTag ++
    encodeNatLE 4 manifest.children.length ++
    encodeNatLE 8 manifest.sourceLower ++
    encodeNatLE 8 manifest.sourceUpper ++
    manifest.rootDigest.bytes.toList ++
    (manifest.children.flatMap Child.encode)).toByteArray

private def readDigest?
    (bytes : ByteArray) (offset : Nat) : Option Digest32 := do
  let raw ← checkedSlice? bytes offset 32
  pure ⟨raw⟩

private def readByte?
    (bytes : ByteArray) (offset : Nat) : Option Nat :=
  readNatLE? bytes offset 1

private def magicMatches (bytes : ByteArray) : Bool :=
  match checkedSlice? bytes 0 magic.length with
  | none => false
  | some slice => slice == magic.toByteArray

private def decodeChild?
    (bytes : ByteArray) (offset : Nat) : Option Child := do
  let ordinal ← readNatLE? bytes offset 4
  let lower ← readNatLE? bytes (offset + 4) 8
  let upper ← readNatLE? bytes (offset + 12) 8
  let backendTag ← readByte? bytes (offset + 20)
  let backend ← Backend.ofTag? backendTag
  let receiptDigest ← readDigest? bytes (offset + 21)
  let artifactDigest ← readDigest? bytes (offset + 53)
  let resultDigest ← readDigest? bytes (offset + 85)
  let predecessorDigest ← readDigest? bytes (offset + 117)
  pure {
    ordinal
    lower
    upper
    backend
    receiptDigest
    artifactDigest
    resultDigest
    predecessorDigest
  }

private def decodeChildren?
    (bytes : ByteArray) : Nat → Nat → Option (List Child)
  | _, 0 => some []
  | offset, count + 1 => do
      let child ← decodeChild? bytes offset
      let rest ← decodeChildren? bytes (offset + childSize) count
      pure (child :: rest)

/-- Parse one exact manifest frame.

The child count is a 32-bit little-endian word.  Source bounds are 64-bit
little-endian words.  Each digest is its raw 32-byte value. -/
def decode (bytes : ByteArray) : Option Manifest := do
  if !magicMatches bytes then none
  let parsedSchema ← readByte? bytes 8
  let campaignTag ← readByte? bytes 9
  let childCount ← readNatLE? bytes 10 4
  let sourceLower ← readNatLE? bytes 14 8
  let sourceUpper ← readNatLE? bytes 22 8
  let rootDigest ← readDigest? bytes 30
  if bytes.size != headerSize + childCount * childSize then none
  let children ← decodeChildren? bytes headerSize childCount
  pure {
    schemaVersion := parsedSchema
    campaignTag
    sourceLower
    sourceUpper
    rootDigest
    children
  }

private def ChainValid
    (spec : Spec) : Digest32 → Nat → Nat → List Child → Prop
  | _, ordinal, nextLower, [] =>
      ordinal = spec.expectedBackends.length ∧
        nextLower = spec.sourceUpper
  | predecessor, ordinal, nextLower, child :: rest =>
      child.ordinal = ordinal ∧
        child.lower = nextLower ∧
        child.lower < child.upper ∧
        spec.expectedBackends[ordinal]? = some child.backend ∧
        child.receiptDigest.Nonzero ∧
        child.artifactDigest.Nonzero ∧
        child.resultDigest.Nonzero ∧
        child.predecessorDigest = predecessor ∧
        ChainValid spec child.receiptDigest (ordinal + 1) child.upper rest

/-- Exact structural proposition checked for one campaign. -/
def ValidFor (spec : Spec) (manifest : Manifest) : Prop :=
  manifest.schemaVersion = schemaVersion ∧
    manifest.campaignTag = spec.campaignTag ∧
    manifest.sourceLower = spec.sourceLower ∧
    manifest.sourceUpper = spec.sourceUpper ∧
    manifest.rootDigest = spec.rootDigest ∧
    spec.rootDigest.Nonzero ∧
    spec.sourceLower < spec.sourceUpper ∧
    manifest.children.length = spec.expectedBackends.length ∧
    ChainValid spec spec.rootDigest 0 spec.sourceLower manifest.children

private instance chainValidDecidable
    (spec : Spec) (predecessor : Digest32)
    (ordinal nextLower : Nat) (children : List Child) :
    Decidable (ChainValid spec predecessor ordinal nextLower children) := by
  induction children generalizing predecessor ordinal nextLower with
  | nil =>
      simp only [ChainValid]
      infer_instance
  | cons child rest ih =>
      simp only [ChainValid]
      infer_instance

instance (spec : Spec) (manifest : Manifest) :
    Decidable (ValidFor spec manifest) := by
  unfold ValidFor
  infer_instance

/-- Total structural manifest check. -/
def check (spec : Spec) (manifest : Manifest) : Bool :=
  decide (ValidFor spec manifest)

theorem check_sound
    {spec : Spec} {manifest : Manifest}
    (checked : check spec manifest = true) :
    ValidFor spec manifest :=
  of_decide_eq_true checked

end SparkInterval.Execution.Architecture.TransitiveChildManifest
