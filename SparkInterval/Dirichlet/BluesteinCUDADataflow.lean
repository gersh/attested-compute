/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinFFTConvolution

/-!
# Exact dataflow of the CUDA Bluestein transform

This module models the exact, unrounded dataflow and address permutations of
`gpu/platform/h100/h100_tg_dirichlet_allchars_bluestein.cu`.

The source performs the following operations on every transform line:

* `initializeA` multiplies the live input by the positive chirp, pads with
  literal zero, and scatters it to bit-reversed addresses;
* `bitReverseCopy` scatters the natural-order padded kernel to bit-reversed
  addresses before its negative-sign forward transform;
* `pointwiseBitReverseCopy` multiplies two natural-order forward transforms
  and scatters the product directly to the addresses consumed by the
  positive-sign inverse transform;
* `gatherOutput` multiplies by the positive post-chirp and performs the only
  `1 / L` normalization.

The definitions below retain the source's negative-forward/positive-inverse
sign convention.  The final theorem composes these layout identities with
`BluesteinFFTConvolution.cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT`.

This is an exact complex-arithmetic theorem.  It does not claim that directed
binary64 disks contain these values, that a CUDA execution realizes these
functions, or that compilation preserves them.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.BluesteinCUDADataflow

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Zeta.WindowedRadix2

/-! ## CUDA's 32-bit bit-reversal address -/

/-- Extending a bit reversal with high zero input bits appends low zero
output bits. -/
theorem reverseBits_extend {bits extra index : Nat}
    (hindex : index < 2 ^ bits) :
    reverseBits (bits + extra) index =
      reverseBits bits index * 2 ^ extra := by
  induction extra with
  | zero => simp
  | succ extra ih =>
      have hbits : bits ≤ bits + extra := Nat.le_add_right _ _
      have hpow : 2 ^ bits ≤ 2 ^ (bits + extra) :=
        Nat.pow_le_pow_right (by omega) hbits
      have hindex' : index < 2 ^ (bits + extra) :=
        lt_of_lt_of_le hindex hpow
      rw [show bits + (extra + 1) = (bits + extra) + 1 by omega]
      have hextend :
          reverseBits ((bits + extra) + 1) index =
            2 * reverseBits (bits + extra) index := by
        simpa using
          reverseBits_highBit (bits + extra) index 0 hindex' (by omega)
      rw [hextend]
      rw [ih]
      simp [pow_succ]
      ring

/-- Natural-number semantics of
`__brev(position) >> (32U - logLength)`.  The separate theorem below records
the guards under which this is exactly the low-`logLength` reversal. -/
def cudaBrevShift (logLength position : Nat) : Nat :=
  reverseBits 32 position / 2 ^ (32 - logLength)

/-- The source's 32-bit CUDA address calculation is the same permutation as
the verified radix-2 model.  The actual source catalog has
`2 ≤ logLength ≤ 20`; this reusable statement only needs
`logLength ≤ 32`. -/
theorem cudaBrevShift_eq_reverseBits {logLength position : Nat}
    (_hlogPos : 0 < logLength) (hlog : logLength ≤ 32)
    (hposition : position < 2 ^ logLength) :
    cudaBrevShift logLength position = reverseBits logLength position := by
  have hdecomp : logLength + (32 - logLength) = 32 := by omega
  have hextend :=
    reverseBits_extend
      (bits := logLength) (extra := 32 - logLength) hposition
  rw [hdecomp] at hextend
  unfold cudaBrevShift
  rw [hextend]
  exact Nat.mul_div_left _ (Nat.pow_pos (by omega))

/-- Typed bit-reversal index used by all three scatter kernels. -/
def bitReverseIndex {logLength : Nat}
    (position : Fin (2 ^ logLength)) : Fin (2 ^ logLength) :=
  finIndex logLength (reverseBits logLength position.val)

@[simp] theorem bitReverseIndex_val {logLength : Nat}
    (position : Fin (2 ^ logLength)) :
    (bitReverseIndex position).val =
      reverseBits logLength position.val := by
  exact finIndex_val_of_lt (reverseBits_lt_two_pow _ _)

@[simp] theorem bitReverseIndex_involutive {logLength : Nat}
    (position : Fin (2 ^ logLength)) :
    bitReverseIndex (bitReverseIndex position) = position := by
  apply Fin.ext
  simp [reverseBits_involutive _ _ position.isLt]

theorem bitReverseIndex_injective {logLength : Nat} :
    Function.Injective
      (@bitReverseIndex logLength) := by
  intro left right heq
  have := congrArg bitReverseIndex heq
  simpa using this

/-- Literal flattened address `line * length + position`. -/
def workspaceIndex {lines logLength : Nat}
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    Fin (lines * 2 ^ logLength) :=
  finProdFinEquiv (line, position)

@[simp] theorem workspaceIndex_val {lines logLength : Nat}
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    (workspaceIndex line position).val =
      line.val * 2 ^ logLength + position.val := by
  simp [workspaceIndex]
  ring

/-- Literal scatter address used by `initializeA`,
`bitReverseCopy`, and `pointwiseBitReverseCopy`. -/
def bitReversedWorkspaceIndex {lines logLength : Nat}
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    Fin (lines * 2 ^ logLength) :=
  workspaceIndex line (bitReverseIndex position)

/-- Distinct `(line, position)` workers have distinct scatter destinations;
there is no write collision hidden by the functional state model. -/
theorem bitReversedWorkspaceIndex_injective
    {lines logLength : Nat} :
    Function.Injective
      (fun coordinate : Fin lines × Fin (2 ^ logLength) =>
        bitReversedWorkspaceIndex coordinate.1 coordinate.2) := by
  intro left right heq
  unfold bitReversedWorkspaceIndex workspaceIndex at heq
  have hpair :
      (left.1, bitReverseIndex left.2) =
        (right.1, bitReverseIndex right.2) :=
    finProdFinEquiv.injective heq
  apply Prod.ext_iff.mpr
  exact
    ⟨congrArg (fun pair => pair.1) hpair,
      bitReverseIndex_injective
        (congrArg (fun pair => pair.2) hpair)⟩

theorem bitReversedWorkspaceIndex_val_eq_cuda
    {lines logLength : Nat} (hlogPos : 0 < logLength)
    (hlog : logLength ≤ 32)
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    (bitReversedWorkspaceIndex line position).val =
      line.val * 2 ^ logLength +
        cudaBrevShift logLength position.val := by
  rw [bitReversedWorkspaceIndex, workspaceIndex_val,
    bitReverseIndex_val,
    cudaBrevShift_eq_reverseBits hlogPos hlog position.isLt]

/-! ## Strided tensor source and target addresses -/

/-- The literal source/target address expression in `initializeA` and
`gatherOutput`, written as a reusable natural-number function. -/
def tensorAddress (length stride line position : Nat) : Nat :=
  (line / stride) * length * stride +
    position * stride + line % stride

/-- Name of the address used for the `input[source]` read in `initializeA`. -/
def initializeASourceAddress
    (length stride line position : Nat) : Nat :=
  tensorAddress length stride line position

/-- Name of the address used for the `output[target]` write in
`gatherOutput`. -/
def gatherOutputTargetAddress
    (length stride line position : Nat) : Nat :=
  tensorAddress length stride line position

/-- Resolving a line as `(outer, inner)` gives the ordinary row-major tensor
address.  The positive-stride guard is explicit because the CUDA execution
never admits a zero stride. -/
theorem tensorAddress_outer_inner
    {length stride outer inner position : Nat}
    (hstride : 0 < stride) (hinner : inner < stride) :
    tensorAddress length stride (outer * stride + inner) position =
      outer * length * stride + position * stride + inner := by
  unfold tensorAddress
  have hdiv : (outer * stride + inner) / stride = outer := by
    rw [show outer * stride = stride * outer by ring,
      Nat.mul_add_div hstride, Nat.div_eq_of_lt hinner]
    simp
  have hmod : (outer * stride + inner) % stride = inner := by
    rw [show outer * stride = stride * outer by ring,
      Nat.mul_add_mod, Nat.mod_eq_of_lt hinner]
  rw [hdiv, hmod]

/-- The strided address is in the source-owned allocation whenever the
logical line and position satisfy the launch bounds.  Positivity guards match
the live CUDA plan even though `position < length` already entails the
length guard in this pointwise statement. -/
theorem tensorAddress_lt_total
    {outerCount length stride line position : Nat}
    (hstride : 0 < stride) (_hlength : 0 < length)
    (hline : line < outerCount * stride)
    (hposition : position < length) :
    tensorAddress length stride line position <
      outerCount * length * stride := by
  have houter : line / stride < outerCount := by
    rw [Nat.div_lt_iff_lt_mul hstride]
    simpa [mul_comm] using hline
  have hinner : line % stride < stride := Nat.mod_lt _ hstride
  have hcoordinate :
      line / stride * length + position < outerCount * length := by
    calc
      line / stride * length + position <
          line / stride * length + length :=
        Nat.add_lt_add_left hposition _
      _ = (line / stride + 1) * length := by ring
      _ ≤ outerCount * length :=
        Nat.mul_le_mul_right length (by omega)
  have hscaled :
      (line / stride * length + position) * stride + line % stride <
        outerCount * length * stride := by
    calc
      (line / stride * length + position) * stride + line % stride <
          (line / stride * length + position) * stride + stride :=
        Nat.add_lt_add_left hinner _
      _ = (line / stride * length + position + 1) * stride := by ring
      _ ≤ outerCount * length * stride :=
        Nat.mul_le_mul_right stride (by omega)
  unfold tensorAddress
  nlinarith

/-- `initializeA` and `gatherOutput` use exactly the same strided physical
address for a given logical `(line, position)`. -/
theorem initializeA_source_eq_gatherOutput_target
    (length stride line position : Nat) :
    initializeASourceAddress length stride line position =
      gatherOutputTargetAddress length stride line position :=
  rfl

/-! ## Exact scatter states -/

/-- A source-style scatter through bit reversal, represented by the value
found at each destination address after all unique writes complete. -/
noncomputable def bitReverseScatter {logLength : Nat}
    (natural : ExactState logLength) : ExactState logLength :=
  ⟨fun address => natural.value (bitReverseIndex address)⟩

theorem bitReverseScatter_eq_bitReversed {logLength : Nat}
    (natural : ExactState logLength) :
    bitReverseScatter natural = bitReversed natural := by
  rfl

/-- Reading the source kernel's bit-reversed destination recovers exactly the
natural-order value written by that source position. -/
theorem bitReverseScatter_write {logLength : Nat}
    (natural : ExactState logLength)
    (position : Fin (2 ^ logLength)) :
    (bitReverseScatter natural).value (bitReverseIndex position) =
      natural.value position := by
  simp [bitReverseScatter]

/-- Flatten a family of transform lines with the source's
`line * length + position` layout. -/
noncomputable def flattenLineStates {lines logLength : Nat}
    (states : Fin lines → ExactState logLength) :
    Fin (lines * 2 ^ logLength) → ℂ :=
  fun address =>
    let coordinates := finProdFinEquiv.symm address
    (states coordinates.1).value coordinates.2

@[simp] theorem flattenLineStates_workspaceIndex
    {lines logLength : Nat} (states : Fin lines → ExactState logLength)
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    flattenLineStates states (workspaceIndex line position) =
      (states line).value position := by
  simp [flattenLineStates, workspaceIndex]

/-- Batched scatter semantics at the literal flattened destination. -/
noncomputable def bitReverseScatterLines {lines logLength : Nat}
    (natural : Fin lines → ExactState logLength) :
    Fin (lines * 2 ^ logLength) → ℂ :=
  flattenLineStates (fun line => bitReverseScatter (natural line))

theorem bitReverseScatterLines_write {lines logLength : Nat}
    (natural : Fin lines → ExactState logLength)
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    bitReverseScatterLines natural
        (bitReversedWorkspaceIndex line position) =
      (natural line).value position := by
  simp [bitReverseScatterLines, bitReversedWorkspaceIndex,
    bitReverseScatter_write]

/-- Natural-order values produced inside `initializeA`: positive pre-chirp
on the live prefix, literal zero on the padded tail. -/
noncomputable def initializeANatural (order logLength : Nat)
    (source : Fin order → ℂ) : ExactState logLength :=
  paddedInputState order logLength source

/-- Exact workspace after every `initializeA` scatter write. -/
noncomputable def initializeAWorkspace (order logLength : Nat)
    (source : Fin order → ℂ) : ExactState logLength :=
  bitReverseScatter (initializeANatural order logLength source)

theorem initializeAWorkspace_eq_bitReversed
    (order logLength : Nat) (source : Fin order → ℂ) :
    initializeAWorkspace order logLength source =
      bitReversed (paddedInputState order logLength source) := by
  rfl

/-- Exact value stored by `initializeA` at the bit-reversed destination of
one natural source position. -/
theorem initializeA_write_to_bit_reversed_address
    {order logLength : Nat} (source : Fin order → ℂ)
    (position : Fin (2 ^ logLength)) :
    (initializeAWorkspace order logLength source).value
        (bitReverseIndex position) =
      BluesteinDFT.paddedChirpedInput
        order (2 ^ logLength) source position := by
  simpa only [initializeAWorkspace, initializeANatural, paddedInputState] using
    bitReverseScatter_write
      (initializeANatural order logLength source) position

/-- Batched `initializeA` at the source's literal flattened workspace
addresses. -/
noncomputable def initializeABatchWorkspace
    (lines order logLength : Nat)
    (source : Fin lines → Fin order → ℂ) :
    Fin (lines * 2 ^ logLength) → ℂ :=
  bitReverseScatterLines
    (fun line => initializeANatural order logLength (source line))

theorem initializeABatch_write_to_flat_address
    {lines order logLength : Nat}
    (source : Fin lines → Fin order → ℂ)
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    initializeABatchWorkspace lines order logLength source
        (bitReversedWorkspaceIndex line position) =
      BluesteinDFT.paddedChirpedInput
        order (2 ^ logLength) (source line) position := by
  simpa only [initializeABatchWorkspace, initializeANatural,
    paddedInputState] using
      bitReverseScatterLines_write
        (fun line => initializeANatural order logLength (source line))
        line position

/-- Exact state produced by the standalone source kernel
`bitReverseCopy`. -/
noncomputable def bitReverseCopy {logLength : Nat}
    (input : ExactState logLength) : ExactState logLength :=
  bitReverseScatter input

theorem bitReverseCopy_write {logLength : Nat}
    (input : ExactState logLength)
    (position : Fin (2 ^ logLength)) :
    (bitReverseCopy input).value (bitReverseIndex position) =
      input.value position := by
  exact bitReverseScatter_write input position

/-- Exact state produced by `pointwiseBitReverseCopy`: multiplication occurs
at the natural frequency, then that one product is scattered. -/
noncomputable def pointwiseBitReverseCopy {logLength : Nat}
    (values multiplier : ExactState logLength) : ExactState logLength :=
  bitReverseScatter (pointwiseProduct values multiplier)

theorem pointwiseBitReverseCopy_write {logLength : Nat}
    (values multiplier : ExactState logLength)
    (position : Fin (2 ^ logLength)) :
    (pointwiseBitReverseCopy values multiplier).value
        (bitReverseIndex position) =
      values.value position * multiplier.value position := by
  simpa only [pointwiseBitReverseCopy, pointwiseProduct] using
    bitReverseScatter_write
      (pointwiseProduct values multiplier) position

/-- Batched fused pointwise/scatter kernel in the literal flattened
workspace layout. -/
noncomputable def pointwiseBitReverseCopyBatch
    (lines logLength : Nat)
    (values : Fin lines → ExactState logLength)
    (multiplier : ExactState logLength) :
    Fin (lines * 2 ^ logLength) → ℂ :=
  bitReverseScatterLines
    (fun line => pointwiseProduct (values line) multiplier)

theorem pointwiseBitReverseCopyBatch_write_to_flat_address
    {lines logLength : Nat}
    (values : Fin lines → ExactState logLength)
    (multiplier : ExactState logLength)
    (line : Fin lines) (position : Fin (2 ^ logLength)) :
    pointwiseBitReverseCopyBatch lines logLength values multiplier
        (bitReversedWorkspaceIndex line position) =
      (values line).value position * multiplier.value position := by
  simpa only [pointwiseBitReverseCopyBatch, pointwiseProduct] using
    bitReverseScatterLines_write
      (fun line => pointwiseProduct (values line) multiplier)
      line position

/-! ## Exact negative-forward and positive-inverse stage graphs -/

/-- Negative roots used by `rootsForwardData`. -/
noncomputable def negativeTwiddle (stageExponent offset : Nat) : ℂ :=
  starRingEnd ℂ (positiveTwiddle stageExponent offset)

theorem conjugateExactState_involutive {logLength : Nat}
    (state : ExactState logLength) :
    conjugateExactState (conjugateExactState state) = state := by
  cases state with
  | mk value =>
      apply congrArg ExactState.mk
      funext index
      simp [conjugateExactState]

theorem bitReversed_conjugate {logLength : Nat}
    (state : ExactState logLength) :
    bitReversed (conjugateExactState state) =
      conjugateExactState (bitReversed state) := by
  rfl

/-- Conjugation changes one positive-root CUDA stage into the corresponding
negative-root stage without changing its schedule. -/
theorem conjugate_exactStage_negativeTwiddle
    {logLength stage : Nat} (state : ExactState logLength) :
    conjugateExactState
        (exactStage stage negativeTwiddle state) =
      exactStage stage positiveTwiddle
        (conjugateExactState state) := by
  apply congrArg ExactState.mk
  funext index
  simp only [conjugateExactState, exactStage]
  split <;>
    simp [negativeTwiddle, ButterflyCertificate.exactLeft,
      ButterflyCertificate.exactRight]

/-- The complete negative-root staged graph is exactly the
conjugate-positive-conjugate transform already used by the generic proof. -/
theorem runExactStages_negative_eq_conjugate_positive
    {logLength count stage : Nat}
    (state : ExactState logLength) :
    runExactStages negativeTwiddle count stage state =
      conjugateExactState
        (runExactStages positiveTwiddle count stage
          (conjugateExactState state)) := by
  induction count generalizing stage state with
  | zero =>
      simp [runExactStages, conjugateExactState_involutive]
  | succ count ih =>
      rw [runExactStages, runExactStages]
      rw [ih]
      rw [← conjugate_exactStage_negativeTwiddle]

/-- Staged negative FFT entered with a source-style bit-reversed state. -/
noncomputable def negativeFFTFromBitReversed {logLength : Nat}
    (state : ExactState logLength) : ExactState logLength :=
  runExactStages negativeTwiddle logLength 0 state

theorem negativeFFTFromBitReversed_scatter
    {logLength : Nat} (natural : ExactState logLength) :
    negativeFFTFromBitReversed (bitReverseScatter natural) =
      negativeRadix2Transform natural := by
  unfold negativeFFTFromBitReversed negativeRadix2Transform
  rw [runExactStages_negative_eq_conjugate_positive]
  rw [bitReverseScatter_eq_bitReversed]
  rw [← bitReversed_conjugate]
  rfl

/-- Staged positive FFT entered with a source-style bit-reversed state. -/
noncomputable def positiveFFTFromBitReversed {logLength : Nat}
    (state : ExactState logLength) : ExactState logLength :=
  runExactStages positiveTwiddle logLength 0 state

theorem positiveFFTFromBitReversed_scatter
    {logLength : Nat} (natural : ExactState logLength) :
    positiveFFTFromBitReversed (bitReverseScatter natural) =
      positiveRadix2Transform natural := by
  rfl

/-! ## Shared-memory initial-stage tiles -/

/-- The global stage group of a position in an aligned tile splits into its
tile number and its stage group inside that tile. -/
theorem groupAt_aligned_tile
    {stage tileLog tile slot : Nat}
    (hstage : stage < tileLog) :
    groupAt stage (tile * 2 ^ tileLog + slot) =
      tile * 2 ^ (tileLog - stage - 1) + slot / width stage := by
  have hwidth : 0 < width stage := by simp [width, halfLength]
  have hfactor :
      2 ^ tileLog = width stage * 2 ^ (tileLog - stage - 1) :=
    transformLength_factor hstage
  unfold groupAt
  rw [hfactor]
  rw [show tile * (width stage * 2 ^ (tileLog - stage - 1)) + slot =
      width stage * (tile * 2 ^ (tileLog - stage - 1)) + slot by ring]
  rw [Nat.mul_add_div hwidth]

/-- Every read and write of a stage whose source `stageLength` is at most the
shared `tileLength` stays in the aligned tile containing the output.  Here a
Lean stage exponent `stage` corresponds to source
`stageLength = 2^(stage+1)`, hence the exact guard `stage < tileLog`. -/
theorem stage_addresses_mem_aligned_tile
    {stage tileLog tile slot : Nat}
    (hstage : stage < tileLog) (hslot : slot < 2 ^ tileLog) :
    tile * 2 ^ tileLog ≤
        scheduledLeft stage
          (groupAt stage (tile * 2 ^ tileLog + slot))
          (offsetAt stage (tile * 2 ^ tileLog + slot)) ∧
      scheduledLeft stage
          (groupAt stage (tile * 2 ^ tileLog + slot))
          (offsetAt stage (tile * 2 ^ tileLog + slot)) <
        (tile + 1) * 2 ^ tileLog ∧
      tile * 2 ^ tileLog ≤
        scheduledRight stage
          (groupAt stage (tile * 2 ^ tileLog + slot))
          (offsetAt stage (tile * 2 ^ tileLog + slot)) ∧
      scheduledRight stage
          (groupAt stage (tile * 2 ^ tileLog + slot))
          (offsetAt stage (tile * 2 ^ tileLog + slot)) <
        (tile + 1) * 2 ^ tileLog := by
  let span := width stage
  let blocks := 2 ^ (tileLog - stage - 1)
  let groupLocal := slot / span
  let offset := offsetAt stage (tile * 2 ^ tileLog + slot)
  have hspan : 0 < span := by simp [span, width, halfLength]
  have hhalf : 0 < halfLength stage := by simp [halfLength]
  have hfactor : 2 ^ tileLog = span * blocks := by
    simpa [span, blocks] using transformLength_factor hstage
  have hgroup :
      groupAt stage (tile * 2 ^ tileLog + slot) =
        tile * blocks + groupLocal := by
    simpa [blocks, groupLocal, span] using
      (groupAt_aligned_tile (tile := tile) (slot := slot) hstage)
  have hoffset : offset < halfLength stage := by
    exact Nat.mod_lt _ hhalf
  have hoffsetSpan : offset < span := by
    dsimp [span]
    rw [show width stage = 2 * halfLength stage by rfl]
    omega
  have hgroupLocal : groupLocal < blocks := by
    rw [Nat.div_lt_iff_lt_mul hspan]
    rw [mul_comm, ← hfactor]
    exact hslot
  have hlocalLeft : groupLocal * span + offset < blocks * span := by
    calc
      groupLocal * span + offset < groupLocal * span + span :=
        Nat.add_lt_add_left hoffsetSpan _
      _ = (groupLocal + 1) * span := by ring
      _ ≤ blocks * span := Nat.mul_le_mul_right span (by omega)
  have hlocalRight :
      groupLocal * span + offset + halfLength stage < blocks * span := by
    have hoffsetHalf : offset + halfLength stage < span := by
      dsimp [span]
      rw [show width stage = 2 * halfLength stage by rfl]
      omega
    calc
      groupLocal * span + offset + halfLength stage =
          groupLocal * span + (offset + halfLength stage) := by omega
      _ < groupLocal * span + span := Nat.add_lt_add_left hoffsetHalf _
      _ = (groupLocal + 1) * span := by ring
      _ ≤ blocks * span := Nat.mul_le_mul_right span (by omega)
  rw [hgroup]
  dsimp only [scheduledLeft, scheduledRight]
  change
    tile * 2 ^ tileLog ≤
        (tile * blocks + groupLocal) * span + offset ∧
      (tile * blocks + groupLocal) * span + offset <
        (tile + 1) * 2 ^ tileLog ∧
      tile * 2 ^ tileLog ≤
        (tile * blocks + groupLocal) * span + offset + halfLength stage ∧
      (tile * blocks + groupLocal) * span + offset + halfLength stage <
        (tile + 1) * 2 ^ tileLog
  rw [hfactor]
  constructor
  · nlinarith
  constructor
  · nlinarith [hlocalLeft]
  constructor
  · nlinarith
  · nlinarith [hlocalRight]

/-- Number of aligned tiles times the tile length is the complete transform
length. -/
theorem pow_tile_factor {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) :
    2 ^ (logLength - tileLog) * 2 ^ tileLog = 2 ^ logLength := by
  rw [← pow_add]
  congr 1
  omega

/-- Global natural address of a shared-memory tile coordinate. -/
def tileGlobalIndex {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength)
    (tile : Fin (2 ^ (logLength - tileLog)))
    (slot : Fin (2 ^ tileLog)) : Fin (2 ^ logLength) :=
  Fin.cast (pow_tile_factor htile) (finProdFinEquiv (tile, slot))

@[simp] theorem tileGlobalIndex_val {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength)
    (tile : Fin (2 ^ (logLength - tileLog)))
    (slot : Fin (2 ^ tileLog)) :
    (tileGlobalIndex htile tile slot).val =
      tile.val * 2 ^ tileLog + slot.val := by
  simp [tileGlobalIndex]
  ring

/-- One aligned shared-memory tile copied from a global exact state. -/
noncomputable def tileState {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength)
    (tile : Fin (2 ^ (logLength - tileLog))) : ExactState tileLog :=
  ⟨fun slot => state.value (tileGlobalIndex htile tile slot)⟩

/-- The exact grouped execution performed while one tile is resident in
shared memory. -/
noncomputable def initialStagesInTile {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength)
    (tile : Fin (2 ^ (logLength - tileLog))) : ExactState tileLog :=
  runExactStages positiveTwiddle tileLog 0 (tileState htile state tile)

theorem runInitialStages_eq_blockTransform
    {logLength count : Nat} (hcount : count ≤ logLength)
    (state : ExactState logLength) :
    runExactStages positiveTwiddle count 0 state =
      blockTransform count state := by
  calc
    runExactStages positiveTwiddle count 0 state =
        runExactStages positiveTwiddle count 0
          (blockTransform 0 state) := by
      rw [blockTransform_zero]
    _ = blockTransform (0 + count) state :=
      runExactStages_blockTransform state (by omega)
    _ = blockTransform count state := by simp

/-- Executing all initial stages independently in aligned shared-memory tiles
is pointwise identical to executing those same stages over the global array.
Together with `stage_addresses_mem_aligned_tile`, this proves both absence of
cross-tile communication and preservation of the exact global butterfly
graph. -/
theorem initialStages_grouped_by_tile
    {logLength tileLog : Nat} (htile : tileLog ≤ logLength)
    (state : ExactState logLength)
    (tile : Fin (2 ^ (logLength - tileLog)))
    (slot : Fin (2 ^ tileLog)) :
    (runExactStages positiveTwiddle tileLog 0 state).value
        (tileGlobalIndex htile tile slot) =
      (initialStagesInTile htile state tile).value slot := by
  rw [runInitialStages_eq_blockTransform htile]
  unfold initialStagesInTile
  rw [runInitialStages_eq_blockTransform (le_refl tileLog)]
  simp only [blockTransform, tileGlobalIndex_val]
  have htileLength : 0 < 2 ^ tileLog := Nat.pow_pos (by omega)
  have hglobalDiv :
      (tile.val * 2 ^ tileLog + slot.val) / 2 ^ tileLog =
        tile.val := by
    rw [show tile.val * 2 ^ tileLog =
        2 ^ tileLog * tile.val by ring,
      Nat.mul_add_div htileLength, Nat.div_eq_of_lt slot.isLt]
    simp
  have hglobalMod :
      (tile.val * 2 ^ tileLog + slot.val) % 2 ^ tileLog =
        slot.val := by
    rw [show tile.val * 2 ^ tileLog =
        2 ^ tileLog * tile.val by ring,
      Nat.mul_add_mod, Nat.mod_eq_of_lt slot.isLt]
  have hlocalDiv : slot.val / 2 ^ tileLog = 0 :=
    Nat.div_eq_of_lt slot.isLt
  have hlocalMod : slot.val % 2 ^ tileLog = slot.val :=
    Nat.mod_eq_of_lt slot.isLt
  rw [hglobalDiv, hglobalMod, hlocalDiv, hlocalMod]
  simp only [zero_mul, zero_add, tileState]
  apply Finset.sum_congr rfl
  intro row _hrow
  congr 2
  apply Fin.ext
  simp only [tileGlobalIndex_val]
  rw [finIndex_val_of_lt (reverseBits_lt_two_pow tileLog row)]
  have hrev := reverseBits_lt_two_pow tileLog row
  have hglobalBound :
      tile.val * 2 ^ tileLog + reverseBits tileLog row <
        2 ^ logLength := by
    have htileNext :
        tile.val + 1 ≤ 2 ^ (logLength - tileLog) := by
      omega
    have hle := Nat.mul_le_mul_right (2 ^ tileLog) htileNext
    rw [pow_tile_factor htile] at hle
    nlinarith
  rw [finIndex_val_of_lt hglobalBound]

/-- Negative-root counterpart used by the source's forward FFT launch. -/
noncomputable def negativeInitialStagesInTile
    {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength)
    (tile : Fin (2 ^ (logLength - tileLog))) : ExactState tileLog :=
  runExactStages negativeTwiddle tileLog 0 (tileState htile state tile)

/-- The shared-memory prefix preserves the same global butterfly graph for
the source's negative-root forward transforms as well. -/
theorem negativeInitialStages_grouped_by_tile
    {logLength tileLog : Nat} (htile : tileLog ≤ logLength)
    (state : ExactState logLength)
    (tile : Fin (2 ^ (logLength - tileLog)))
    (slot : Fin (2 ^ tileLog)) :
    (runExactStages negativeTwiddle tileLog 0 state).value
        (tileGlobalIndex htile tile slot) =
      (negativeInitialStagesInTile htile state tile).value slot := by
  unfold negativeInitialStagesInTile
  rw [runExactStages_negative_eq_conjugate_positive]
  rw [runExactStages_negative_eq_conjugate_positive]
  change starRingEnd ℂ
      ((runExactStages positiveTwiddle tileLog 0
        (conjugateExactState state)).value
          (tileGlobalIndex htile tile slot)) =
    starRingEnd ℂ
      ((runExactStages positiveTwiddle tileLog 0
        (conjugateExactState
          (tileState htile state tile))).value slot)
  rw [initialStages_grouped_by_tile htile
    (conjugateExactState state) tile slot]
  rfl

/-- Decode a global index into the tile and shared-memory slot from which it
is reconstructed. -/
def tileCoordinates {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (index : Fin (2 ^ logLength)) :
    Fin (2 ^ (logLength - tileLog)) × Fin (2 ^ tileLog) :=
  finProdFinEquiv.symm
    (Fin.cast (pow_tile_factor htile).symm index)

@[simp] theorem tileGlobalIndex_tileCoordinates
    {logLength tileLog : Nat} (htile : tileLog ≤ logLength)
    (index : Fin (2 ^ logLength)) :
    tileGlobalIndex htile (tileCoordinates htile index).1
      (tileCoordinates htile index).2 = index := by
  unfold tileGlobalIndex tileCoordinates
  rw [Equiv.apply_symm_apply]
  apply Fin.ext
  rfl

/-- Reassemble the positive-root shared-memory tile results into the global
array. -/
noncomputable def groupedInitialStages {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    ExactState logLength :=
  ⟨fun index =>
    let coordinate := tileCoordinates htile index
    (initialStagesInTile htile state coordinate.1).value coordinate.2⟩

theorem groupedInitialStages_eq_global
    {logLength tileLog : Nat} (htile : tileLog ≤ logLength)
    (state : ExactState logLength) :
    groupedInitialStages htile state =
      runExactStages positiveTwiddle tileLog 0 state := by
  apply congrArg ExactState.mk
  funext index
  let coordinate := tileCoordinates htile index
  have hindex :
      tileGlobalIndex htile coordinate.1 coordinate.2 = index := by
    exact tileGlobalIndex_tileCoordinates htile index
  change
    (initialStagesInTile htile state coordinate.1).value coordinate.2 =
      (runExactStages positiveTwiddle tileLog 0 state).value index
  rw [← hindex]
  exact
    (initialStages_grouped_by_tile htile state
      coordinate.1 coordinate.2).symm

/-- Reassemble the negative-root shared-memory tile results. -/
noncomputable def groupedNegativeInitialStages
    {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    ExactState logLength :=
  ⟨fun index =>
    let coordinate := tileCoordinates htile index
    (negativeInitialStagesInTile htile state coordinate.1).value
      coordinate.2⟩

theorem groupedNegativeInitialStages_eq_global
    {logLength tileLog : Nat} (htile : tileLog ≤ logLength)
    (state : ExactState logLength) :
    groupedNegativeInitialStages htile state =
      runExactStages negativeTwiddle tileLog 0 state := by
  apply congrArg ExactState.mk
  funext index
  let coordinate := tileCoordinates htile index
  have hindex :
      tileGlobalIndex htile coordinate.1 coordinate.2 = index := by
    exact tileGlobalIndex_tileCoordinates htile index
  change
    (negativeInitialStagesInTile htile state coordinate.1).value
        coordinate.2 =
      (runExactStages negativeTwiddle tileLog 0 state).value index
  rw [← hindex]
  exact
    (negativeInitialStages_grouped_by_tile htile state
      coordinate.1 coordinate.2).symm

/-- Split a staged graph after any prefix without changing its operation
order. -/
theorem runExactStages_split {logLength : Nat}
    (twiddles : Nat → Nat → ℂ) (first rest stage : Nat)
    (state : ExactState logLength) :
    runExactStages twiddles (first + rest) stage state =
      runExactStages twiddles rest (stage + first)
        (runExactStages twiddles first stage state) := by
  induction first generalizing stage state with
  | zero => simp [runExactStages]
  | succ first ih =>
      rw [show first + 1 + rest = (first + rest) + 1 by omega]
      rw [runExactStages, runExactStages]
      rw [ih]
      rw [show stage + (first + 1) = (stage + 1) + first by omega]

/-- Positive-root `launchFft`: grouped shared prefix followed by the remaining
global stages. -/
noncomputable def positiveSharedLaunch {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    ExactState logLength :=
  runExactStages positiveTwiddle (logLength - tileLog) tileLog
    (groupedInitialStages htile state)

theorem positiveSharedLaunch_eq_full {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    positiveSharedLaunch htile state =
      runExactStages positiveTwiddle logLength 0 state := by
  unfold positiveSharedLaunch
  rw [groupedInitialStages_eq_global]
  have hsum : tileLog + (logLength - tileLog) = logLength := by omega
  simpa only [zero_add, hsum] using
    (runExactStages_split positiveTwiddle tileLog
      (logLength - tileLog) 0 state).symm

/-- Negative-root `launchFft`: grouped shared prefix followed by the remaining
global stages. -/
noncomputable def negativeSharedLaunch {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    ExactState logLength :=
  runExactStages negativeTwiddle (logLength - tileLog) tileLog
    (groupedNegativeInitialStages htile state)

theorem negativeSharedLaunch_eq_full {logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (state : ExactState logLength) :
    negativeSharedLaunch htile state =
      runExactStages negativeTwiddle logLength 0 state := by
  unfold negativeSharedLaunch
  rw [groupedNegativeInitialStages_eq_global]
  have hsum : tileLog + (logLength - tileLog) = logLength := by omega
  simpa only [zero_add, hsum] using
    (runExactStages_split negativeTwiddle tileLog
      (logLength - tileLog) 0 state).symm

/-- Production `launchFft` tile exponent. -/
def sourceTileLog (logLength : Nat) : Nat :=
  min logLength 10

theorem sourceTileLog_le (logLength : Nat) :
    sourceTileLog logLength ≤ logLength :=
  Nat.min_le_left _ _

/-- `2^sourceTileLog` is exactly the source expression
`min(transformLength, 1024)`. -/
theorem sourceTileLength_eq (logLength : Nat) :
    2 ^ sourceTileLog logLength = min (2 ^ logLength) 1024 := by
  by_cases hlog : logLength ≤ 10
  · rw [sourceTileLog, Nat.min_eq_left hlog]
    rw [Nat.min_eq_left]
    have hpow := Nat.pow_le_pow_right (n := 2) (by omega) hlog
    norm_num at hpow ⊢
    exact hpow
  · have hten : 10 ≤ logLength := by omega
    rw [sourceTileLog, Nat.min_eq_right hten]
    rw [Nat.min_eq_right]
    · norm_num
    · have hpow := Nat.pow_le_pow_right (n := 2) (by omega) hten
      norm_num at hpow ⊢
      exact hpow

/-! ## Gather and complete line dataflow -/

/-- Exact source order in `gatherOutput`: multiply by the positive
post-chirp, then divide once by the convolution length. -/
noncomputable def gatherOutputValue
    (order logLength : Nat) (workspace : ExactState logLength)
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength) : ℂ :=
  (workspace.value (paddedFrequency hle frequency) *
      BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2)) /
    (2 ^ logLength : Nat)

/-- Source-order post-chirp/division is the normalized value expected by the
exact CUDA-sign convolution theorem. -/
theorem gatherOutputValue_eq_postChirp_normalized
    {order logLength : Nat} (workspace : ExactState logLength)
    (frequency : Fin order) (hle : order ≤ 2 ^ logLength) :
    gatherOutputValue order logLength workspace frequency hle =
      BluesteinDFT.halfRoot order ((frequency.val : Int) ^ 2) *
        (((2 ^ logLength : Nat) : ℂ)⁻¹ *
          workspace.value (paddedFrequency hle frequency)) := by
  unfold gatherOutputValue
  rw [div_eq_mul_inv]
  ring

/-- The exact per-line value obtained by following the source's four kernels
and both staged transforms. -/
noncomputable def cudaBluesteinLineValue
    (order logLength : Nat) (source : Fin order → ℂ)
    (frequency : Fin order)
    (hle : order ≤ 2 ^ logLength) : ℂ :=
  let initialized :=
    initializeAWorkspace order logLength source
  let kernel :=
    bitReverseCopy (zeroPaddedKernelState order logLength)
  let transformedInput :=
    negativeFFTFromBitReversed initialized
  let transformedKernel :=
    negativeFFTFromBitReversed kernel
  let fused :=
    pointwiseBitReverseCopy transformedInput transformedKernel
  let inverse :=
    positiveFFTFromBitReversed fused
  gatherOutputValue order logLength inverse frequency hle

/-- Complete exact source-layout theorem.  All source address permutations,
the fused inverse bit reversal, signs, post-chirp order, and the single
normalization reduce to the direct arbitrary-length positive DFT. -/
theorem cudaBluesteinLineValue_eq_positiveDFT
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    cudaBluesteinLineValue order logLength source frequency
        (by omega : order ≤ 2 ^ logLength) =
      BluesteinDFT.positiveDFT order source frequency := by
  rw [cudaBluesteinLineValue]
  simp only [initializeAWorkspace, bitReverseCopy,
    pointwiseBitReverseCopy]
  rw [negativeFFTFromBitReversed_scatter]
  rw [negativeFFTFromBitReversed_scatter]
  rw [positiveFFTFromBitReversed_scatter]
  rw [gatherOutputValue_eq_postChirp_normalized]
  exact
    cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT
      horder hfft source frequency

/-- The full exact line dataflow with the source's shared-memory prefix made
explicit.  `tileLog = min logLength 10` models the production
`tileLength = min(length, 1024)` choice; keeping it as a guarded parameter
makes the reusable theorem cover other legal tile sizes. -/
noncomputable def cudaBluesteinSharedLineValue
    (order logLength tileLog : Nat)
    (htile : tileLog ≤ logLength) (source : Fin order → ℂ)
    (frequency : Fin order) (hle : order ≤ 2 ^ logLength) : ℂ :=
  let initialized := initializeAWorkspace order logLength source
  let kernel := bitReverseCopy (zeroPaddedKernelState order logLength)
  let transformedInput := negativeSharedLaunch htile initialized
  let transformedKernel := negativeSharedLaunch htile kernel
  let fused := pointwiseBitReverseCopy transformedInput transformedKernel
  let inverse := positiveSharedLaunch htile fused
  gatherOutputValue order logLength inverse frequency hle

theorem cudaBluesteinSharedLineValue_eq_ungrouped
    {order logLength tileLog : Nat}
    (htile : tileLog ≤ logLength) (source : Fin order → ℂ)
    (frequency : Fin order) (hle : order ≤ 2 ^ logLength) :
    cudaBluesteinSharedLineValue order logLength tileLog htile
        source frequency hle =
      cudaBluesteinLineValue order logLength source frequency hle := by
  simp only [cudaBluesteinSharedLineValue, cudaBluesteinLineValue]
  rw [negativeSharedLaunch_eq_full]
  rw [negativeSharedLaunch_eq_full]
  rw [positiveSharedLaunch_eq_full]
  rfl

/-- Strongest exact dataflow theorem: the literal scatter/gather layout,
fused pointwise inverse permutation, negative-forward/positive-inverse
stages, and shared-memory stage grouping compute the direct positive DFT. -/
theorem cudaBluesteinSharedLineValue_eq_positiveDFT
    {order logLength tileLog : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (htile : tileLog ≤ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    cudaBluesteinSharedLineValue order logLength tileLog htile
        source frequency (by omega : order ≤ 2 ^ logLength) =
      BluesteinDFT.positiveDFT order source frequency := by
  rw [cudaBluesteinSharedLineValue_eq_ungrouped]
  exact
    cudaBluesteinLineValue_eq_positiveDFT
      horder hfft source frequency

/-- Exact line value with the production source's concrete
`min(transformLength, 1024)` tile selection. -/
noncomputable def cudaBluesteinSourceLineValue
    (order logLength : Nat) (source : Fin order → ℂ)
    (frequency : Fin order) (hle : order ≤ 2 ^ logLength) : ℂ :=
  cudaBluesteinSharedLineValue order logLength
    (sourceTileLog logLength) (sourceTileLog_le logLength)
    source frequency hle

/-- Source-shaped capstone for the exact arithmetic/dataflow layer. -/
theorem cudaBluesteinSourceLineValue_eq_positiveDFT
    {order logLength : Nat} (horder : 0 < order)
    (hfft : 2 * order - 1 ≤ 2 ^ logLength)
    (source : Fin order → ℂ) (frequency : Fin order) :
    cudaBluesteinSourceLineValue order logLength source frequency
        (by omega : order ≤ 2 ^ logLength) =
      BluesteinDFT.positiveDFT order source frequency := by
  unfold cudaBluesteinSourceLineValue
  exact
    cudaBluesteinSharedLineValue_eq_positiveDFT
      horder hfft (sourceTileLog_le logLength) source frequency

end SparkInterval.Dirichlet.BluesteinCUDADataflow
