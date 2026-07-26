/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86PureEntryABI

/-!
Tiny ordinary-Lean interface checks for the pure-entry ABI layer.  They use
only symbolic hypotheses and small fixed byte arrays; no production artifact
or instruction trace is evaluated.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.X86PureEntryABITest

open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86PureEntryABI

example
    {config : LauncherConfig} {image : ELF64Image}
    {entryAddress : UInt64} {inputBytes : ByteArray}
    {state : MachineState}
    (initialized :
      InitializeEntry config image entryAddress inputBytes state) :
    state.registers .rdi = UInt64.ofNat config.layout.inputBase ∧
      state.registers .rsi = UInt64.ofNat inputBytes.size ∧
      state.registers .rdx = UInt64.ofNat config.layout.resultBase ∧
      state.registers .rcx = UInt64.ofNat config.layout.statusBase ∧
      (state.registers .rsp).toNat % 16 = 8 ∧
      state.flags.direction = false := by
  have invariant := initializeEntry_establishes_invariants initialized
  exact
    ⟨invariant.rdiInput, invariant.rsiInputLength,
      invariant.rdxResult, invariant.rcxStatus,
      invariant.rspAlignment, invariant.directionFlagClear⟩

example
    {config : LauncherConfig} {state : MachineState}
    {outputBytes : ByteArray}
    (returned : ReturnedWith config state outputBytes) :
    outputBytes.size = 120 ∧
      decodeLE32? state.memory.status.bytes = some 0 ∧
      eax state = 1 ∧
      state.memory.input = config.inputRegion state.entryInput := by
  have facts :=
    returnedWith_implies_exact_output_and_status returned
  exact ⟨facts.2.1, facts.2.2.1, facts.2.2.2.1, facts.2.2.2.2⟩

example (segment : LoadSegment) :
    SegmentLoadedExactly segment (loadSegmentRegion segment) :=
  loadSegmentRegion_exact segment

end SparkInterval.Execution.Architecture.X86PureEntryABITest
