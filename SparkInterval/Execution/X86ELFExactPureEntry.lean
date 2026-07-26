/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFDecoder
import SparkInterval.Execution.X86PureEntryABI

/-!
# Exact-decoder x86 pure-entry composition

This module closes the data-independent composition between the strict ELF64
decoder and the concrete pure-entry ABI model.  The decoder and selected
symbol are fixed here:

* executable bytes are decoded only by `X86ELFDecoder.decodeSelectedImage`;
* the entry name is exactly `X86ELFDecoder.selectedEntrySymbol`; and
* successful `PureEntryModel.load` exposes the exact decoded image and the
  existing static-image, launcher-layout, and SysV entry invariants.

The architecture-semantics digest and x86 transition relation remain explicit
parameters.  This module does not define x86 instruction semantics, execute an
ELF image, or refine a physical launcher.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.X86ELFExactPureEntry

open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder
open SparkInterval.Execution.Architecture.X86PureEntryABI

/-- The pure-entry model with the exact selected-entry ELF decoder fixed.

Only the architecture-semantics identity and the instruction transition
relation remain parameters.  In particular, callers cannot substitute a
different decoder or entry symbol through this definition. -/
def exactDecoderModel
    (semanticsId : Digest) (semanticsIdPresent : semanticsId ≠ "")
    (config : LauncherConfig)
    (step : MachineState → MachineState → Prop) :
    PureEntryModel :=
  asPureEntryModel semanticsId semanticsIdPresent
    decodeSelectedImage config step

@[simp] theorem exactDecoderModel_semanticsId
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop} :
    (exactDecoderModel semanticsId semanticsIdPresent config step).semanticsId =
      semanticsId := by
  rfl

@[simp] theorem exactDecoderModel_decode
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop} :
    (exactDecoderModel semanticsId semanticsIdPresent config step).decode =
      decodeSelectedImage := by
  rfl

@[simp] theorem exactDecoderModel_step
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {before after : MachineState} :
    (exactDecoderModel semanticsId semanticsIdPresent config step).step
        before after ↔
      step before after ∧
        after.entryInput = before.entryInput ∧
        after.entryLoadedELF = before.entryLoadedELF := by
  rfl

/-- All data-independent facts exposed by one successful exact-decoder load.

The existential decoder image and loader-selected address have been
canonicalized to the image returned by `decodeSelectedImage` and its ELF
header entry.  `entryInvariant` retains the exact loaded segment bytes and
zero fill, region separation, argument registers, aligned stack pointer,
clear direction flag, and measured return sentinel. -/
structure SuccessfulLoadFacts
    (config : LauncherConfig)
    (image : ELF64Image)
    (executableBytes inputBytes : ByteArray)
    (state : MachineState) : Prop where
  decodedExactly :
    decodeSelectedImage executableBytes = some image
  staticELF :
    image.StaticPureEntryAdmissible
  selectedEntry :
    image.EntryAdmissible selectedEntrySymbol image.entryAddress
  launcherAdmissible :
    LauncherAdmissible config image inputBytes
  initialized :
    InitializeEntry config image image.entryAddress inputBytes state
  entryInvariant :
    EntryInvariant config image image.entryAddress inputBytes state

/-- A successful load at the fixed selected symbol supplies the exact decoder
image and every existing static-image and ABI-initialization invariant.

This theorem is independent of the contents or size of any production
artifact.  The `step` parameter is neither evaluated nor assumed to have any
application-specific behavior. -/
theorem successfulLoad_facts
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {executableBytes inputBytes : ByteArray}
    {state : MachineState}
    (loaded :
      (exactDecoderModel semanticsId semanticsIdPresent config step).load
        selectedEntrySymbol executableBytes inputBytes state) :
    ∃ image : ELF64Image,
      SuccessfulLoadFacts config image executableBytes inputBytes state := by
  rcases loaded with
    ⟨image, entryAddress, decoded, staticELF, selectedEntry, initialized⟩
  have entryAddressExact : entryAddress = image.entryAddress :=
    selectedEntry.2.1
  subst entryAddress
  change decodeSelectedImage executableBytes = some image at decoded
  change
    InitializeEntry config image image.entryAddress inputBytes state
      at initialized
  have decoderSelectedEntry :
      image.EntryAdmissible selectedEntrySymbol image.entryAddress :=
    decodeSelectedImage_entryAdmissible decoded
  exact ⟨image, {
      decodedExactly := decoded
      staticELF
      selectedEntry := decoderSelectedEntry
      launcherAdmissible := initialized.1
      initialized
      entryInvariant :=
        initializeEntry_establishes_invariants initialized
    }⟩

/-- Convenient projection of the exact segment image and the System V AMD64
entry-register facts.  These are not new assumptions: they are fields of the
existing `EntryInvariant` established by `successfulLoad_facts`. -/
theorem successfulLoad_exactSegmentsAndABI
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {executableBytes inputBytes : ByteArray}
    {state : MachineState}
    (loaded :
      (exactDecoderModel semanticsId semanticsIdPresent config step).load
        selectedEntrySymbol executableBytes inputBytes state) :
    ∃ image : ELF64Image,
      decodeSelectedImage executableBytes = some image ∧
      state.memory.loadedELF =
        image.segments.map loadSegmentRegion ∧
      image.SafeLoadSegments ∧
      image.DisjointLoadSegments ∧
      state.rip = image.entryAddress ∧
      state.registers .rdi =
        UInt64.ofNat config.layout.inputBase ∧
      state.registers .rsi =
        UInt64.ofNat inputBytes.size ∧
      state.registers .rdx =
        UInt64.ofNat config.layout.resultBase ∧
      state.registers .rcx =
        UInt64.ofNat config.layout.statusBase ∧
      state.registers .rsp =
        UInt64.ofNat config.layout.stackPointer ∧
      (state.registers .rsp).toNat % 16 = 8 ∧
      state.flags.direction = false := by
  rcases successfulLoad_facts loaded with ⟨image, facts⟩
  exact
    ⟨image, facts.decodedExactly,
      facts.entryInvariant.elfSegmentsLoadedExactly,
      facts.staticELF.safeLoadSegments,
      facts.staticELF.disjointLoadSegments,
      facts.entryInvariant.ripAtEntry,
      facts.entryInvariant.rdiInput,
      facts.entryInvariant.rsiInputLength,
      facts.entryInvariant.rdxResult,
      facts.entryInvariant.rcxStatus,
      facts.entryInvariant.rspStack,
      facts.entryInvariant.rspAlignment,
      facts.entryInvariant.directionFlagClear⟩

end SparkInterval.Execution.Architecture.X86ELFExactPureEntry
