/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFExactPureEntry

set_option autoImplicit false

namespace SparkInterval.Tests.X86ELFExactPureEntryTest

open SparkInterval.Execution
open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder
open SparkInterval.Execution.Architecture.X86ELFExactPureEntry
open SparkInterval.Execution.Architecture.X86PureEntryABI

/-- The composition fixes the decoder while retaining the semantics identity
and the future x86 instruction transition as explicit parameters. -/
example
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop} :
    (exactDecoderModel semanticsId semanticsIdPresent config step).semanticsId =
        semanticsId ∧
      (exactDecoderModel semanticsId semanticsIdPresent config step).decode =
        decodeSelectedImage := by
  exact ⟨rfl, rfl⟩

example
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

/-- A symbolic successful load exposes the exact decoded image, both policy
predicates, launcher initialization, and every named entry invariant. -/
example
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
      image.StaticPureEntryAdmissible ∧
      image.EntryAdmissible selectedEntrySymbol image.entryAddress ∧
      LauncherAdmissible config image inputBytes ∧
      InitializeEntry config image image.entryAddress inputBytes state ∧
      EntryInvariant config image image.entryAddress inputBytes state := by
  rcases successfulLoad_facts loaded with ⟨image, facts⟩
  exact
    ⟨image, facts.decodedExactly, facts.staticELF,
      facts.selectedEntry, facts.launcherAdmissible,
      facts.initialized, facts.entryInvariant⟩

/-- The named invariant really exports the exact segment image and the
concrete SysV register, stack-alignment, and direction-flag facts. -/
example
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {executableBytes inputBytes : ByteArray}
    {state : MachineState}
    (loaded :
      (exactDecoderModel semanticsId semanticsIdPresent config step).load
        selectedEntrySymbol executableBytes inputBytes state) :
    ∃ image : ELF64Image,
      state.memory.loadedELF =
        image.segments.map loadSegmentRegion ∧
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
  rcases successfulLoad_exactSegmentsAndABI loaded with
    ⟨image, _decoded, segments, _safe, _disjoint, rip,
      rdi, rsi, rdx, rcx, rsp, aligned, df⟩
  exact
    ⟨image, segments, rip, rdi, rsi, rdx, rcx, rsp, aligned, df⟩

end SparkInterval.Tests.X86ELFExactPureEntryTest
