/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFPureEntry

/-!
# Data-independent x86-64 pure-entry ABI state

This module implements the memory-layout, register-initialization, and
return-observation part of the static x86-64 pure-entry boundary.  It is
deliberately separate from an x86 instruction decoder and instruction
semantics:

* memory is a finite list of byte-addressed regions;
* every ELF `PT_LOAD` region contains the exact retained file bytes followed
  by its exact zero fill;
* the immutable input, 120-byte result, four-byte status, guarded stack, and
  measured launcher text are distinct regions;
* the System V AMD64 argument registers, entry `RIP`, aligned function-entry
  `RSP`, clear direction flag, and measured return sentinel are explicit; and
* successful return observes `EAX = 1`, little-endian status zero, exactly
  120 retained result bytes, and an unchanged input region.

`asPureEntryModel` accepts `step` as a parameter.  A production instance must
supply a closed, reviewed x86-64 instruction semantics and prove the
machine-code refinement separately.  Nothing here calls the Sqrt218 checker,
opens a production certificate, replays a trace, or grants authority to an
attestation receipt.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.X86PureEntryABI

open SparkInterval.Execution.Architecture.X86ELF

/-- The unbounded representation of one x86-64 byte address.  Range
well-formedness below prevents wraparound before conversion to `UInt64`. -/
abbrev Address := Nat

/-- Number of distinct x86-64 byte addresses. -/
def addressSpaceSize : Nat := 2 ^ 64

/-- Access permissions retained for each finite memory region. -/
structure Permissions where
  readable : Bool
  writable : Bool
  executable : Bool
  deriving DecidableEq, Repr

namespace Permissions

def readOnly : Permissions :=
  { readable := true, writable := false, executable := false }

def readWrite : Permissions :=
  { readable := true, writable := true, executable := false }

def readExecute : Permissions :=
  { readable := true, writable := false, executable := true }

def inaccessible : Permissions :=
  { readable := false, writable := false, executable := false }

def ofLoadSegment (segment : LoadSegment) : Permissions :=
  {
    readable := segment.readable
    writable := segment.writable
    executable := segment.executable
  }

end Permissions

/-- A finite, byte-addressed half-open memory region. -/
structure Region where
  base : Address
  bytes : ByteArray
  permissions : Permissions
  deriving DecidableEq

namespace Region

def endAddress (region : Region) : Address :=
  region.base + region.bytes.size

def RangeWellFormed (region : Region) : Prop :=
  region.endAddress ≤ addressSpaceSize

def Contains (region : Region) (address : Address) : Prop :=
  region.base ≤ address ∧ address < region.endAddress

def Disjoint (left right : Region) : Prop :=
  left.endAddress ≤ right.base ∨ right.endAddress ≤ left.base

/-- Exact byte-addressed lookup relation.  The explicit bound prevents the
default behavior of `ByteArray.get!` from accepting an out-of-range byte. -/
def ByteAt (region : Region) (address : Address) (value : UInt8) : Prop :=
  ∃ offset : Nat,
    offset < region.bytes.size ∧
      address = region.base + offset ∧
      region.bytes.get! offset = value

end Region

/-- A byte array containing exactly `count` zero bytes. -/
def zeroBytes (count : Nat) : ByteArray :=
  (List.replicate count (0 : UInt8)).toByteArray

@[simp] theorem zeroBytes_size (count : Nat) :
    (zeroBytes count).size = count := by
  simp [zeroBytes]

/-- The little-endian eight-byte representation placed in the return slot. -/
def littleEndian64Bytes (value : UInt64) : ByteArray :=
  ((List.range 8).map fun index =>
    UInt8.ofNat (value.toNat / 256 ^ index % 256)).toByteArray

@[simp] theorem littleEndian64Bytes_size (value : UInt64) :
    (littleEndian64Bytes value).size = 8 := by
  simp [littleEndian64Bytes]

/-- Replace a byte interval without silently extending its containing array.
The launcher's admissibility predicate ensures the eight-byte replacement is
inside the stack. -/
def replaceBytes
    (bytes : ByteArray) (offset : Nat) (replacement : ByteArray) : ByteArray :=
  bytes.extract 0 offset ++ replacement ++
    bytes.extract (offset + replacement.size) bytes.size

theorem replaceBytes_size
    {bytes replacement : ByteArray} {offset : Nat}
    (replacementFits : offset + replacement.size ≤ bytes.size) :
    (replaceBytes bytes offset replacement).size = bytes.size := by
  simp only [replaceBytes, ByteArray.size_append, ByteArray.size_extract]
  omega

/-- Exact file bytes followed by the ELF-required zero fill. -/
def loadSegmentBytes (segment : LoadSegment) : ByteArray :=
  segment.fileBytes ++
    zeroBytes (segment.memoryByteLength - segment.fileBytes.size)

/-- Concrete finite region produced by loading one decoded `PT_LOAD`. -/
def loadSegmentRegion (segment : LoadSegment) : Region :=
  {
    base := segment.virtualAddress.toNat
    bytes := loadSegmentBytes segment
    permissions := Permissions.ofLoadSegment segment
  }

/-- Source-shaped statement of exact segment loading, including zero fill. -/
structure SegmentLoadedExactly
    (segment : LoadSegment) (region : Region) : Prop where
  base : region.base = segment.virtualAddress.toNat
  fileBytesAndZeroFill :
    region.bytes =
      segment.fileBytes ++
        zeroBytes (segment.memoryByteLength - segment.fileBytes.size)
  permissions :
    region.permissions = Permissions.ofLoadSegment segment

theorem loadSegmentRegion_exact (segment : LoadSegment) :
    SegmentLoadedExactly segment (loadSegmentRegion segment) := by
  exact ⟨rfl, rfl, rfl⟩

theorem loadSegmentRegion_size
    {segment : LoadSegment}
    (fileFits : segment.fileBytes.size ≤ segment.memoryByteLength) :
    (loadSegmentRegion segment).bytes.size =
      segment.memoryByteLength := by
  simp [loadSegmentRegion, loadSegmentBytes, zeroBytes]
  omega

/-- General-purpose registers needed by the System V AMD64 boundary. -/
inductive GPRegister where
  | rax | rbx | rcx | rdx | rsi | rdi | rbp | rsp
  | r8 | r9 | r10 | r11 | r12 | r13 | r14 | r15
  deriving DecidableEq, Repr

abbrev RegisterFile := GPRegister → UInt64

/-- Architectural flags are explicit even though only `DF` is constrained by
the function-entry ABI. -/
structure Flags where
  carry : Bool
  parity : Bool
  auxiliaryCarry : Bool
  zero : Bool
  sign : Bool
  overflow : Bool
  direction : Bool
  deriving DecidableEq, Repr

def clearFlags : Flags :=
  {
    carry := false
    parity := false
    auxiliaryCarry := false
    zero := false
    sign := false
    overflow := false
    direction := false
  }

/-- Return may be represented either by the instruction semantics moving
`RIP` to the sentinel or by a semantics that records a completed `RET`. -/
inductive ReturnProgress where
  | running
  | retCompleted (target : UInt64)
  deriving DecidableEq, Repr

/-- Addresses and fixed sizes selected by the measured launcher. -/
structure Layout where
  launcherTextBase : Address
  inputBase : Address
  resultBase : Address
  statusBase : Address
  lowerGuardBase : Address
  stackBase : Address
  stackSize : Nat
  upperGuardBase : Address
  guardSize : Nat
  stackPointer : Address
  returnSentinel : Address
  deriving DecidableEq, Repr

/-- The measured launcher bytes are a separate identity-bound artifact from
the pure-entry ELF.  This structure supplies their bytes and layout, but does
not itself claim that a receipt measured them. -/
structure LauncherConfig where
  layout : Layout
  launcherTextBytes : ByteArray
  deriving DecidableEq

namespace LauncherConfig

def launcherTextRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.launcherTextBase
    bytes := config.launcherTextBytes
    permissions := Permissions.readExecute
  }

def inputRegion (config : LauncherConfig) (inputBytes : ByteArray) : Region :=
  {
    base := config.layout.inputBase
    bytes := inputBytes
    permissions := Permissions.readOnly
  }

def resultRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.resultBase
    bytes := zeroBytes 120
    permissions := Permissions.readWrite
  }

def statusRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.statusBase
    bytes := zeroBytes 4
    permissions := Permissions.readWrite
  }

def lowerGuardRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.lowerGuardBase
    bytes := zeroBytes config.layout.guardSize
    permissions := Permissions.inaccessible
  }

def returnSlotOffset (config : LauncherConfig) : Nat :=
  config.layout.stackPointer - config.layout.stackBase

def initialStackBytes (config : LauncherConfig) : ByteArray :=
  replaceBytes (zeroBytes config.layout.stackSize)
    config.returnSlotOffset
    (littleEndian64Bytes (UInt64.ofNat config.layout.returnSentinel))

def stackRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.stackBase
    bytes := config.initialStackBytes
    permissions := Permissions.readWrite
  }

def upperGuardRegion (config : LauncherConfig) : Region :=
  {
    base := config.layout.upperGuardBase
    bytes := zeroBytes config.layout.guardSize
    permissions := Permissions.inaccessible
  }

end LauncherConfig

/-- The complete finite memory image visible to the pure-entry semantics. -/
structure MemoryImage where
  loadedELF : List Region
  launcherText : Region
  input : Region
  result : Region
  status : Region
  lowerGuard : Region
  stack : Region
  upperGuard : Region
  deriving DecidableEq

namespace MemoryImage

def regions (memory : MemoryImage) : List Region :=
  memory.loadedELF ++
    [memory.launcherText, memory.input, memory.result, memory.status,
      memory.lowerGuard, memory.stack, memory.upperGuard]

def ByteAt
    (memory : MemoryImage) (address : Address) (value : UInt8) : Prop :=
  ∃ region ∈ memory.regions, region.ByteAt address value

end MemoryImage

def initialMemory
    (config : LauncherConfig) (image : ELF64Image)
    (inputBytes : ByteArray) : MemoryImage :=
  {
    loadedELF := image.segments.map loadSegmentRegion
    launcherText := config.launcherTextRegion
    input := config.inputRegion inputBytes
    result := config.resultRegion
    status := config.statusRegion
    lowerGuard := config.lowerGuardRegion
    stack := config.stackRegion
    upperGuard := config.upperGuardRegion
  }

/-- Data-independent conditions the measured launcher must establish before
jumping to the pure function.  The pairwise predicate covers the complete
finite image, including every ELF load segment and both inaccessible stack
guards. -/
structure LauncherAdmissible
    (config : LauncherConfig) (image : ELF64Image)
    (inputBytes : ByteArray) : Prop where
  staticELF : image.StaticPureEntryAdmissible
  inputNonempty : 0 < inputBytes.size
  inputLengthFits : inputBytes.size < addressSpaceSize
  launcherTextNonempty : 0 < config.launcherTextBytes.size
  stackNonempty : 8 ≤ config.layout.stackSize
  guardNonempty : 0 < config.layout.guardSize
  lowerGuardAdjacent :
    config.layout.lowerGuardBase + config.layout.guardSize =
      config.layout.stackBase
  upperGuardAdjacent :
    config.layout.upperGuardBase =
      config.layout.stackBase + config.layout.stackSize
  returnSlotInStack :
    config.layout.stackBase ≤ config.layout.stackPointer ∧
      config.layout.stackPointer + 8 ≤
        config.layout.stackBase + config.layout.stackSize
  stackPointerFits : config.layout.stackPointer < addressSpaceSize
  stackPointerAlignment : config.layout.stackPointer % 16 = 8
  returnSentinelFits : config.layout.returnSentinel < addressSpaceSize
  returnSentinelInMeasuredText :
    config.launcherTextRegion.Contains config.layout.returnSentinel
  regionsInAddressSpace :
    ∀ region ∈ (initialMemory config image inputBytes).regions,
      region.RangeWellFormed
  regionsPairwiseDisjoint :
    (initialMemory config image inputBytes).regions.Pairwise Region.Disjoint

theorem returnSlotOffset_add_eight_le
    {config : LauncherConfig} {image : ELF64Image}
    {inputBytes : ByteArray}
    (admissible : LauncherAdmissible config image inputBytes) :
    config.returnSlotOffset + 8 ≤ config.layout.stackSize := by
  unfold LauncherConfig.returnSlotOffset
  have stackBelowPointer :
      config.layout.stackBase ≤ config.layout.stackPointer :=
    admissible.returnSlotInStack.1
  have returnSlotBelowStackEnd :
      config.layout.stackPointer + 8 ≤
        config.layout.stackBase + config.layout.stackSize :=
    admissible.returnSlotInStack.2
  have afterSubtractingBase :=
    Nat.sub_le_sub_right returnSlotBelowStackEnd config.layout.stackBase
  rw [Nat.sub_add_comm stackBelowPointer] at afterSubtractingBase
  simpa only [Nat.add_sub_cancel_left] using afterSubtractingBase

/-- Concrete x86-64 state at the ABI/ISA boundary.  `entryInput` and
`entryLoadedELF` are ghost copies used only to state immutable-memory
postconditions.  The adapter below forces every future ISA step to preserve
both fields. -/
structure MachineState where
  registers : RegisterFile
  flags : Flags
  rip : UInt64
  memory : MemoryImage
  entryInput : ByteArray
  entryLoadedELF : List Region
  returnProgress : ReturnProgress

def initialRegisters
    (config : LauncherConfig) (inputByteLength : Nat) : RegisterFile
  | .rdi => UInt64.ofNat config.layout.inputBase
  | .rsi => UInt64.ofNat inputByteLength
  | .rdx => UInt64.ofNat config.layout.resultBase
  | .rcx => UInt64.ofNat config.layout.statusBase
  | .rsp => UInt64.ofNat config.layout.stackPointer
  | _ => 0

def initialState
    (config : LauncherConfig) (image : ELF64Image)
    (entryAddress : UInt64) (inputBytes : ByteArray) : MachineState :=
  {
    registers := initialRegisters config inputBytes.size
    flags := clearFlags
    rip := entryAddress
    memory := initialMemory config image inputBytes
    entryInput := inputBytes
    entryLoadedELF := image.segments.map loadSegmentRegion
    returnProgress := .running
  }

/-- Concrete relation used as `PureEntryModel.initializeEntry`. -/
def InitializeEntry
    (config : LauncherConfig) (image : ELF64Image)
    (entryAddress : UInt64) (inputBytes : ByteArray)
    (state : MachineState) : Prop :=
  LauncherAdmissible config image inputBytes ∧
    state = initialState config image entryAddress inputBytes

/-- Named entry invariants exposed to a future instruction-semantics proof. -/
structure EntryInvariant
    (config : LauncherConfig) (image : ELF64Image)
    (entryAddress : UInt64) (inputBytes : ByteArray)
    (state : MachineState) : Prop where
  admissible : LauncherAdmissible config image inputBytes
  elfSegmentsLoadedExactly :
    state.memory.loadedELF = image.segments.map loadSegmentRegion
  launcherTextExact :
    state.memory.launcherText = config.launcherTextRegion
  immutableInputExact :
    state.memory.input = config.inputRegion inputBytes
  resultInitiallyZero :
    state.memory.result = config.resultRegion
  statusInitiallyZero :
    state.memory.status = config.statusRegion
  lowerGuardExact :
    state.memory.lowerGuard = config.lowerGuardRegion
  stackAndReturnSlotExact :
    state.memory.stack = config.stackRegion
  upperGuardExact :
    state.memory.upperGuard = config.upperGuardRegion
  immutableInputPermission :
    state.memory.input.permissions = Permissions.readOnly
  resultSizeExact : state.memory.result.bytes.size = 120
  statusSizeExact : state.memory.status.bytes.size = 4
  stackSizeExact :
    state.memory.stack.bytes.size = config.layout.stackSize
  lowerGuardSizeExact :
    state.memory.lowerGuard.bytes.size = config.layout.guardSize
  lowerGuardInaccessible :
    state.memory.lowerGuard.permissions = Permissions.inaccessible
  upperGuardSizeExact :
    state.memory.upperGuard.bytes.size = config.layout.guardSize
  upperGuardInaccessible :
    state.memory.upperGuard.permissions = Permissions.inaccessible
  allRegionsInAddressSpace :
    ∀ region ∈ state.memory.regions, region.RangeWellFormed
  allRegionsPairwiseDisjoint :
    state.memory.regions.Pairwise Region.Disjoint
  ripAtEntry : state.rip = entryAddress
  rdiInput :
    state.registers .rdi = UInt64.ofNat config.layout.inputBase
  rsiInputLength :
    state.registers .rsi = UInt64.ofNat inputBytes.size
  rdxResult :
    state.registers .rdx = UInt64.ofNat config.layout.resultBase
  rcxStatus :
    state.registers .rcx = UInt64.ofNat config.layout.statusBase
  rspStack :
    state.registers .rsp = UInt64.ofNat config.layout.stackPointer
  rspAlignment :
    (state.registers .rsp).toNat % 16 = 8
  directionFlagClear : state.flags.direction = false
  returnSentinelMeasured :
    config.launcherTextRegion.Contains config.layout.returnSentinel
  noReturnYet : state.returnProgress = .running
  inputGhostExact : state.entryInput = inputBytes
  loadedELFGhostExact :
    state.entryLoadedELF = image.segments.map loadSegmentRegion

/-- The concrete initializer establishes every named ABI/memory invariant. -/
theorem initializeEntry_establishes_invariants
    {config : LauncherConfig} {image : ELF64Image}
    {entryAddress : UInt64} {inputBytes : ByteArray}
    {state : MachineState}
    (initialized :
      InitializeEntry config image entryAddress inputBytes state) :
    EntryInvariant config image entryAddress inputBytes state := by
  rcases initialized with ⟨admissible, rfl⟩
  refine {
    admissible
    elfSegmentsLoadedExactly := rfl
    launcherTextExact := rfl
    immutableInputExact := rfl
    resultInitiallyZero := rfl
    statusInitiallyZero := rfl
    lowerGuardExact := rfl
    stackAndReturnSlotExact := rfl
    upperGuardExact := rfl
    immutableInputPermission := rfl
    resultSizeExact := by
      change (zeroBytes 120).size = 120
      exact zeroBytes_size 120
    statusSizeExact := by
      change (zeroBytes 4).size = 4
      exact zeroBytes_size 4
    stackSizeExact := ?_
    lowerGuardSizeExact := by
      change (zeroBytes config.layout.guardSize).size =
        config.layout.guardSize
      exact zeroBytes_size config.layout.guardSize
    lowerGuardInaccessible := rfl
    upperGuardSizeExact := by
      change (zeroBytes config.layout.guardSize).size =
        config.layout.guardSize
      exact zeroBytes_size config.layout.guardSize
    upperGuardInaccessible := rfl
    allRegionsInAddressSpace := admissible.regionsInAddressSpace
    allRegionsPairwiseDisjoint := admissible.regionsPairwiseDisjoint
    ripAtEntry := rfl
    rdiInput := rfl
    rsiInputLength := rfl
    rdxResult := rfl
    rcxStatus := rfl
    rspStack := rfl
    rspAlignment := ?_
    directionFlagClear := rfl
    returnSentinelMeasured := admissible.returnSentinelInMeasuredText
    noReturnYet := rfl
    inputGhostExact := rfl
    loadedELFGhostExact := rfl
  }
  · change (LauncherConfig.initialStackBytes config).size =
      config.layout.stackSize
    unfold LauncherConfig.initialStackBytes
    have replacementFits :
        LauncherConfig.returnSlotOffset config +
            (littleEndian64Bytes
              (UInt64.ofNat config.layout.returnSentinel)).size ≤
          (zeroBytes config.layout.stackSize).size := by
      simp only [littleEndian64Bytes_size, zeroBytes_size]
      exact returnSlotOffset_add_eight_le admissible
    have sizePreserved := replaceBytes_size replacementFits
    simpa only [zeroBytes_size] using sizePreserved
  simp only [initialState, initialRegisters]
  have pointerFits :
      config.layout.stackPointer < 2 ^ 64 := by
    simpa [addressSpaceSize] using admissible.stackPointerFits
  change
    (BitVec.ofNat 64 config.layout.stackPointer).toNat % 16 = 8
  rw [BitVec.toNat_ofNat, Nat.mod_eq_of_lt pointerFits]
  exact admissible.stackPointerAlignment

/-- Decode exactly four bytes as a little-endian unsigned 32-bit value. -/
def decodeLE32? (bytes : ByteArray) : Option UInt32 :=
  if bytes.size = 4 then
    some (UInt32.ofNat (
      (bytes.get! 0).toNat +
      (bytes.get! 1).toNat * 256 +
      (bytes.get! 2).toNat * 256 ^ 2 +
      (bytes.get! 3).toNat * 256 ^ 3))
  else
    none

/-- Low 32 bits of the x86-64 return register. -/
def eax (state : MachineState) : UInt32 :=
  (state.registers .rax).toUInt32

/-- The selected semantics has completed a normal return to the measured
sentinel, either by exposing the target in `RIP` or by recording `RET`. -/
def ReturnedToSentinel
    (config : LauncherConfig) (state : MachineState) : Prop :=
  state.rip = UInt64.ofNat config.layout.returnSentinel ∨
    state.returnProgress =
      .retCompleted (UInt64.ofNat config.layout.returnSentinel)

/-- Complete return observer used as `PureEntryModel.returnedWith`.  Region
shape equalities prevent an instruction semantics from satisfying the
observer by moving buffers or changing their permissions. -/
structure ReturnedWith
    (config : LauncherConfig) (state : MachineState)
    (outputBytes : ByteArray) : Prop where
  returnedToSentinel : ReturnedToSentinel config state
  returnSentinelInMeasuredText :
    config.launcherTextRegion.Contains config.layout.returnSentinel
  launcherTextUnchanged :
    state.memory.launcherText = config.launcherTextRegion
  loadedELFUnchanged :
    state.memory.loadedELF = state.entryLoadedELF
  eaxIsOne : eax state = 1
  resultBaseUnchanged :
    state.memory.result.base = config.layout.resultBase
  resultPermissionsUnchanged :
    state.memory.result.permissions = Permissions.readWrite
  outputExact : state.memory.result.bytes = outputBytes
  outputSize : outputBytes.size = 120
  statusBaseUnchanged :
    state.memory.status.base = config.layout.statusBase
  statusPermissionsUnchanged :
    state.memory.status.permissions = Permissions.readWrite
  statusSize : state.memory.status.bytes.size = 4
  statusIsLittleEndianZero :
    decodeLE32? state.memory.status.bytes = some 0
  inputUnchanged :
    state.memory.input = config.inputRegion state.entryInput
  lowerGuardUnchanged :
    state.memory.lowerGuard = config.lowerGuardRegion
  stackBaseUnchanged :
    state.memory.stack.base = config.layout.stackBase
  stackPermissionsUnchanged :
    state.memory.stack.permissions = Permissions.readWrite
  upperGuardUnchanged :
    state.memory.upperGuard = config.upperGuardRegion
  allRegionsInAddressSpace :
    ∀ region ∈ state.memory.regions, region.RangeWellFormed
  allRegionsPairwiseDisjoint :
    state.memory.regions.Pairwise Region.Disjoint

/-- The observer's externally relevant facts, without exposing the entire
record of memory-shape checks. -/
theorem returnedWith_implies_exact_output_and_status
    {config : LauncherConfig} {state : MachineState}
    {outputBytes : ByteArray}
    (returned : ReturnedWith config state outputBytes) :
    state.memory.result.bytes = outputBytes ∧
      outputBytes.size = 120 ∧
      decodeLE32? state.memory.status.bytes = some 0 ∧
      eax state = 1 ∧
      state.memory.input = config.inputRegion state.entryInput := by
  exact
    ⟨returned.outputExact, returned.outputSize,
      returned.statusIsLittleEndianZero, returned.eaxIsOne,
      returned.inputUnchanged⟩

/-- Lift a future instruction transition with preservation of the two ghost
snapshots.  This prevents an arbitrary semantics from changing both the input
memory and its comparison value in the same step. -/
def preserveGhosts
    (step : MachineState → MachineState → Prop)
    (before after : MachineState) : Prop :=
  step before after ∧
    after.entryInput = before.entryInput ∧
    after.entryLoadedELF = before.entryLoadedELF

/-- Adapter into the generic static-ELF boundary.

`decode` must eventually be the exact ELF decoder plus an exact named-symbol
resolver.  `step` remains an explicit future x86-64 ISA semantics parameter;
this adapter contains no application-level transition relation.
`PureEntryModel.load` separately requires `ELF64Image.EntryAdmissible`, so the
selected address is the decoded image entry and an executable named symbol;
that obligation is intentionally not duplicated in the initializer. -/
def asPureEntryModel
    (semanticsId : Digest) (semanticsIdPresent : semanticsId ≠ "")
    (decode : ByteArray → Option ELF64Image)
    (config : LauncherConfig)
    (step : MachineState → MachineState → Prop) :
    PureEntryModel where
  semanticsId := semanticsId
  semanticsIdPresent := semanticsIdPresent
  decode := decode
  State := MachineState
  initializeEntry := InitializeEntry config
  step := preserveGhosts step
  returnedWith := ReturnedWith config

@[simp] theorem asPureEntryModel_initializeEntry
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {decode : ByteArray → Option ELF64Image}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {image : ELF64Image} {entryAddress : UInt64}
    {inputBytes : ByteArray} {state : MachineState} :
    (asPureEntryModel semanticsId semanticsIdPresent decode config step).initializeEntry
        image entryAddress inputBytes state ↔
      InitializeEntry config image entryAddress inputBytes state := by
  rfl

@[simp] theorem asPureEntryModel_returnedWith
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {decode : ByteArray → Option ELF64Image}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {state : MachineState} {outputBytes : ByteArray} :
    (asPureEntryModel semanticsId semanticsIdPresent decode config step).returnedWith
        state outputBytes ↔
      ReturnedWith config state outputBytes := by
  rfl

@[simp] theorem asPureEntryModel_step
    {semanticsId : Digest} {semanticsIdPresent : semanticsId ≠ ""}
    {decode : ByteArray → Option ELF64Image}
    {config : LauncherConfig}
    {step : MachineState → MachineState → Prop}
    {before after : MachineState} :
    (asPureEntryModel semanticsId semanticsIdPresent decode config step).step
        before after ↔
      step before after ∧
        after.entryInput = before.entryInput ∧
        after.entryLoadedELF = before.entryLoadedELF := by
  rfl

end SparkInterval.Execution.Architecture.X86PureEntryABI
