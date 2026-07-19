import SparkInterval.PTX.MachineSemantics

/-!
# Instruction-level refinement lemmas

These lemmas connect the operands of the exact arithmetic instruction arrays
used by the generator to the status-aware bounded-arithmetic model.  Unlike an
opcode-count theorem, the statements quantify over the actual source and
destination registers and therefore detect operand swaps or aliasing.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Two modeled f64 registers contain a numerical interval. -/
def MachineState.RegistersContain (state : MachineState)
    (registers : IntervalRegisters) (interval : F64Interval) : Prop :=
  state.f64.read registers.lo.index = some interval.lo ∧
    state.f64.read registers.hi.index = some interval.hi

private theorem readF64_after_write_of_ne (state : MachineState)
    {written current : Reg .f64} (hne : current.index ≠ written.index)
    (value : F64Value) :
    (state.writeF64 written value).f64.read current.index =
      state.f64.read current.index := by
  exact RegisterFile.read_write_of_ne state.f64 hne value

/-- Exact six-instruction finite guard emitted around each arithmetic operand. -/
def finiteGuardInstructions (value : IntervalRegisters)
    (loExponent hiExponent : Reg .u64) (loNonfinite hiNonfinite : Reg .pred) :
    List Instruction :=
  [.exponentBits loExponent value.lo,
   .setpEqExponentMask loNonfinite loExponent,
   .branchIf loNonfinite wholeLabel,
   .exponentBits hiExponent value.hi,
   .setpEqExponentMask hiNonfinite hiExponent,
   .branchIf hiNonfinite wholeLabel]

/-- A finite interval falls through the exact generated guard. -/
theorem executeFiniteGuard_fallthrough
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters)
    (loExponent hiExponent : Reg .u64) (loNonfinite hiNonfinite : Reg .pred)
    (lo hi : ℝ)
    (hlo : state.f64.read value.lo.index = some (.finite lo))
    (hhi : state.f64.read value.hi.index = some (.finite hi)) :
    ∃ final,
      executeCode module parameters thread
        (finiteGuardInstructions value loExponent hiExponent
          loNonfinite hiNonfinite) state =
        some { control := .fallthrough, state := final } := by
  unfold RegisterFile.read at hlo hhi
  simp [finiteGuardInstructions, executeCode, executeInstruction,
    F64Value.exponentFieldMask, hlo, hhi, MachineState.advance,
    MachineState.writeU64, MachineState.writePred, RegisterFile.read,
    RegisterFile.write, wrapU64]

/-- A nonfinite lower endpoint takes the shared whole-interval branch before
the upper endpoint is inspected. -/
theorem executeFiniteGuard_lowerNonfinite
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters)
    (loExponent hiExponent : Reg .u64) (loNonfinite hiNonfinite : Reg .pred)
    (lo : F64Value)
    (hloKind : lo = .negInf ∨ lo = .posInf)
    (hlo : state.f64.read value.lo.index = some lo) :
    ∃ final,
      executeCode module parameters thread
        (finiteGuardInstructions value loExponent hiExponent
          loNonfinite hiNonfinite) state =
        some { control := .jump wholeLabel, state := final } := by
  rcases hloKind with rfl | rfl <;>
    unfold RegisterFile.read at hlo <;>
    simp [finiteGuardInstructions, executeCode, executeInstruction,
      F64Value.exponentFieldMask, hlo, MachineState.advance,
      MachineState.writeU64, MachineState.writePred, RegisterFile.read,
      RegisterFile.write, wrapU64]

/-- With a finite lower endpoint, a nonfinite upper endpoint takes the second
branch in the generated guard. -/
theorem executeFiniteGuard_upperNonfinite
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters)
    (loExponent hiExponent : Reg .u64) (loNonfinite hiNonfinite : Reg .pred)
    (lo : ℝ) (hi : F64Value)
    (hhiKind : hi = .negInf ∨ hi = .posInf)
    (hlo : state.f64.read value.lo.index = some (.finite lo))
    (hhi : state.f64.read value.hi.index = some hi) :
    ∃ final,
      executeCode module parameters thread
        (finiteGuardInstructions value loExponent hiExponent
          loNonfinite hiNonfinite) state =
        some { control := .jump wholeLabel, state := final } := by
  rcases hhiKind with rfl | rfl <;>
    unfold RegisterFile.read at hlo hhi <;>
    simp [finiteGuardInstructions, executeCode, executeInstruction,
      F64Value.exponentFieldMask, hlo, hhi, MachineState.advance,
      MachineState.writeU64, MachineState.writePred, RegisterFile.read,
      RegisterFile.write, wrapU64]

/-- Executing the exact two operand-sensitive addition instructions emitted by
the compiler produces `roundedBinaryInterval .add`.

The three non-aliasing hypotheses are precisely what is needed because the
lower result is written before the upper operands are read and both result
endpoints must remain observable.  Compiler freshness discharges them. -/
theorem executeAddArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result left right : IntervalRegisters)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi))
    (hresult : result.lo.index ≠ result.hi.index)
    (hleftUpper : result.lo.index ≠ left.hi.index)
    (hrightUpper : result.lo.index ≠ right.hi.index) :
    ∃ final,
      executeCode module parameters thread
          (addArithmeticFragment result left right).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        (roundedBinaryInterval .add leftLo leftHi rightLo rightHi) := by
  unfold RegisterFile.read at hleftLo hleftHi hrightLo hrightHi
  let loValue := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftLo + rightLo)
  let hiValue := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftHi + rightHi)
  let afterLo := (state.writeF64 result.lo loValue).advance
  let final := (afterLo.writeF64 result.hi hiValue).advance
  refine ⟨final, ?_, ?_⟩
  · simp [executeCode, addArithmeticFragment, executeInstruction,
      directedBinary, exactBinary, hleftLo, hrightLo, hleftHi, hrightHi,
      afterLo, final, loValue, hiValue, MachineState.advance,
      MachineState.writeF64, RegisterFile.read, RegisterFile.write,
      Ne.symm hleftUpper, Ne.symm hrightUpper]
  · constructor
    · simp [final, afterLo,
        MachineState.advance, MachineState.writeF64, RegisterFile.read,
        RegisterFile.write, hresult, roundedBinaryInterval, loValue]
    · simp [final, MachineState.advance,
        MachineState.writeF64, RegisterFile.read, RegisterFile.write,
        roundedBinaryInterval, hiValue]

/-- Operand-sensitive refinement theorem for the exact subtraction fragment. -/
theorem executeSubArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result left right : IntervalRegisters)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi))
    (hresult : result.lo.index ≠ result.hi.index)
    (hleftUpper : result.lo.index ≠ left.hi.index)
    (hrightUpper : result.lo.index ≠ right.lo.index) :
    ∃ final,
      executeCode module parameters thread
          (subArithmeticFragment result left right).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        (roundedBinaryInterval .sub leftLo leftHi rightLo rightHi) := by
  unfold RegisterFile.read at hleftLo hleftHi hrightLo hrightHi
  let loValue := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftLo - rightHi)
  let hiValue := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftHi - rightLo)
  let afterLo := (state.writeF64 result.lo loValue).advance
  let final := (afterLo.writeF64 result.hi hiValue).advance
  refine ⟨final, ?_, ?_⟩
  · simp [executeCode, subArithmeticFragment, executeInstruction,
      directedBinary, exactBinary, hleftLo, hrightLo, hleftHi, hrightHi,
      afterLo, final, loValue, hiValue, MachineState.advance,
      MachineState.writeF64, RegisterFile.read, RegisterFile.write,
      Ne.symm hleftUpper, Ne.symm hrightUpper]
  · constructor
    · simp [final, afterLo, MachineState.advance, MachineState.writeF64,
        RegisterFile.read, RegisterFile.write, hresult,
        roundedBinaryInterval, loValue]
    · simp [final, MachineState.advance, MachineState.writeF64,
        RegisterFile.read, RegisterFile.write, roundedBinaryInterval, hiValue]

private abbrev F64Write := Reg .f64 × F64Value

/-- Apply a sequence of f64 writes, including the program-counter advance
performed by each corresponding arithmetic instruction. -/
private def applyF64Writes (state : MachineState) :
    List F64Write → MachineState
  | [] => state
  | (register, value) :: rest =>
      applyF64Writes ((state.writeF64 register value).advance) rest

private def f64WriteIndices (writes : List F64Write) : List Nat :=
  writes.map fun write => write.1.index

/-- A sequence of writes preserves every register whose index is absent from
the sequence.  This packages the repeated register-file reasoning needed by
the multiplication trace into one linear induction. -/
private theorem readF64_after_writes_of_not_mem
    (state : MachineState) (writes : List F64Write)
    (current : Reg .f64)
    (hnot : current.index ∉ f64WriteIndices writes) :
    (applyF64Writes state writes).f64.read current.index =
      state.f64.read current.index := by
  induction writes generalizing state with
  | nil => rfl
  | cons head rest ih =>
      rcases head with ⟨written, value⟩
      have hne : current.index ≠ written.index := by
        intro heq
        apply hnot
        simp only [f64WriteIndices, List.map_cons, List.mem_cons]
        exact Or.inl heq
      have hrest : current.index ∉ f64WriteIndices rest := by
        intro hmem
        apply hnot
        simp only [f64WriteIndices, List.map_cons, List.mem_cons]
        exact Or.inr hmem
      change
        (applyF64Writes ((state.writeF64 written value).advance) rest).f64.read
            current.index = state.f64.read current.index
      calc
        _ = ((state.writeF64 written value).advance).f64.read current.index :=
          ih (state := (state.writeF64 written value).advance) hrest
        _ = state.f64.read current.index := by
          simpa [MachineState.advance] using
            readF64_after_write_of_ne state hne value

/-- The prefix form used to show that source operands remain readable before
each of the first eight multiplication instructions. -/
private theorem readF64_after_writes_take_of_not_mem
    (state : MachineState) (writes : List F64Write)
    (current : Reg .f64) (count : Nat)
    (hnot : current.index ∉ f64WriteIndices writes) :
    (applyF64Writes state (writes.take count)).f64.read current.index =
      state.f64.read current.index := by
  apply readF64_after_writes_of_not_mem
  intro hmem
  apply hnot
  have htake : current.index ∈ (f64WriteIndices writes).take count := by
    simpa only [f64WriteIndices, List.map_take] using hmem
  exact List.mem_of_mem_take htake

/-- Under unique destination indices, every binding written by a sequence is
still observable after the sequence finishes. -/
private theorem readF64_after_writes_of_mem
    (state : MachineState) (writes : List F64Write)
    {register : Reg .f64} {value : F64Value}
    (hnodup : (f64WriteIndices writes).Nodup)
    (hmem : (register, value) ∈ writes) :
    (applyF64Writes state writes).f64.read register.index = some value := by
  induction writes generalizing state with
  | nil => simp at hmem
  | cons head rest ih =>
      rcases head with ⟨headRegister, headValue⟩
      have hnodupCons :
          (headRegister.index :: f64WriteIndices rest).Nodup := by
        simpa only [f64WriteIndices, List.map_cons] using hnodup
      have hheadNot : headRegister.index ∉ f64WriteIndices rest :=
        (List.nodup_cons.mp hnodupCons).1
      have hrestNodup : (f64WriteIndices rest).Nodup :=
        (List.nodup_cons.mp hnodupCons).2
      have hmemCons :
          (register, value) = (headRegister, headValue) ∨
            (register, value) ∈ rest := by
        simpa only [List.mem_cons] using hmem
      rcases hmemCons with hsame | htail
      · have hregister : register = headRegister :=
          congrArg (fun write : F64Write => write.1) hsame
        have hvalue : value = headValue :=
          congrArg (fun write : F64Write => write.2) hsame
        subst headRegister
        subst headValue
        change
          (applyF64Writes
              ((state.writeF64 register value).advance) rest).f64.read
              register.index = some value
        calc
          _ = ((state.writeF64 register value).advance).f64.read
                register.index :=
            readF64_after_writes_of_not_mem _ _ _ hheadNot
          _ = some value := by
            simp [MachineState.advance, MachineState.writeF64]
      · change
          (applyF64Writes
              ((state.writeF64 headRegister headValue).advance) rest).f64.read
              register.index = some value
        exact ih (state := (state.writeF64 headRegister headValue).advance)
          hrestNodup htail

/-- Peel one binary f64 instruction from `executeCode` once its three local
semantic facts (the two reads and the directed result) are known. -/
private theorem executeCode_binaryF64_cons
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    {state : MachineState} {rest : List Instruction}
    {op : F64BinaryOp} {rounding : DirectedRounding}
    {dst left right : Reg .f64}
    {leftValue rightValue resultValue : F64Value}
    (hleft : state.f64.read left.index = some leftValue)
    (hright : state.f64.read right.index = some rightValue)
    (hvalue : directedBinary op rounding leftValue rightValue =
      some resultValue) :
    executeCode module parameters thread
        (.binaryF64 op rounding dst left right :: rest) state =
      executeCode module parameters thread rest
        ((state.writeF64 dst resultValue).advance) := by
  simp [executeCode, executeInstruction, hleft, hright, hvalue]

/-- Peel one f64 minimum instruction from `executeCode`. -/
private theorem executeCode_minimumF64_cons
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    {state : MachineState} {rest : List Instruction}
    {dst left right : Reg .f64} {leftValue rightValue : F64Value}
    (hleft : state.f64.read left.index = some leftValue)
    (hright : state.f64.read right.index = some rightValue) :
    executeCode module parameters thread
        (.minimumF64 dst left right :: rest) state =
      executeCode module parameters thread rest
        ((state.writeF64 dst (F64Value.minimum leftValue rightValue)).advance) := by
  simp [executeCode, executeInstruction, hleft, hright]

/-- Peel one f64 maximum instruction from `executeCode`. -/
private theorem executeCode_maximumF64_cons
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    {state : MachineState} {rest : List Instruction}
    {dst left right : Reg .f64} {leftValue rightValue : F64Value}
    (hleft : state.f64.read left.index = some leftValue)
    (hright : state.f64.read right.index = some rightValue) :
    executeCode module parameters thread
        (.maximumF64 dst left right :: rest) state =
      executeCode module parameters thread rest
        ((state.writeF64 dst (F64Value.maximum leftValue rightValue)).advance) := by
  simp [executeCode, executeInstruction, hleft, hright]

/-- Destination indices in the order in which the multiplication arithmetic
fragment writes them.  Keeping this list next to the refinement theorem makes
the required allocation invariant explicit and ties it to every temporary and
result register used by `mulArithmeticFragment`. -/
def mulArithmeticDestinationIndices (result : IntervalRegisters)
    (tmp : MulArithmeticTemporaries) : List Nat :=
  [tmp.down0.index, tmp.down1.index, tmp.down2.index, tmp.down3.index,
   tmp.up0.index, tmp.up1.index, tmp.up2.index, tmp.up3.index,
   tmp.down01.index, tmp.down23.index, result.lo.index,
   tmp.up01.index, tmp.up23.index, result.hi.index]

/-- Operand-sensitive refinement theorem for the exact fourteen-instruction
multiplication fragment.

The theorem is independent of the compiler's concrete register numbers.  It
only requires that all fourteen destinations are distinct and that none of the
four source endpoints is overwritten by the fragment.  Those hypotheses are
the register-allocation obligations needed to trust the actual operands and
reductions sent to the GPU, rather than merely the fragment's opcode counts. -/
theorem executeMulArithmeticFragment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (result left right : IntervalRegisters)
    (tmp : MulArithmeticTemporaries)
    (leftLo leftHi rightLo rightHi : ℝ)
    (hleftLo : state.f64.read left.lo.index = some (.finite leftLo))
    (hleftHi : state.f64.read left.hi.index = some (.finite leftHi))
    (hrightLo : state.f64.read right.lo.index = some (.finite rightLo))
    (hrightHi : state.f64.read right.hi.index = some (.finite rightHi))
    (hdestinations : (mulArithmeticDestinationIndices result tmp).Nodup)
    (hleftLoFresh : left.lo.index ∉ mulArithmeticDestinationIndices result tmp)
    (hleftHiFresh : left.hi.index ∉ mulArithmeticDestinationIndices result tmp)
    (hrightLoFresh : right.lo.index ∉ mulArithmeticDestinationIndices result tmp)
    (hrightHiFresh : right.hi.index ∉ mulArithmeticDestinationIndices result tmp) :
    ∃ final,
      executeCode module parameters thread
          (mulArithmeticFragment result left right tmp).toList state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain result
        (roundedBinaryInterval .mul leftLo leftHi rightLo rightHi) := by
  let down0Value := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftLo * rightLo)
  let down1Value := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftLo * rightHi)
  let down2Value := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftHi * rightLo)
  let down3Value := F64Value.ofExt <|
    Binary64Rounding.roundDown (leftHi * rightHi)
  let up0Value := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftLo * rightLo)
  let up1Value := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftLo * rightHi)
  let up2Value := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftHi * rightLo)
  let up3Value := F64Value.ofExt <|
    Binary64Rounding.roundUp (leftHi * rightHi)
  let down01Value := F64Value.minimum down0Value down1Value
  let down23Value := F64Value.minimum down2Value down3Value
  let loValue := F64Value.minimum down01Value down23Value
  let up01Value := F64Value.maximum up0Value up1Value
  let up23Value := F64Value.maximum up2Value up3Value
  let hiValue := F64Value.maximum up01Value up23Value

  let writes : List F64Write :=
    [(tmp.down0, down0Value), (tmp.down1, down1Value),
     (tmp.down2, down2Value), (tmp.down3, down3Value),
     (tmp.up0, up0Value), (tmp.up1, up1Value),
     (tmp.up2, up2Value), (tmp.up3, up3Value),
     (tmp.down01, down01Value), (tmp.down23, down23Value),
     (result.lo, loValue), (tmp.up01, up01Value),
     (tmp.up23, up23Value), (result.hi, hiValue)]
  let final := applyF64Writes state (writes.take 14)

  have hwritesIndices :
      f64WriteIndices writes = mulArithmeticDestinationIndices result tmp := by
    rfl
  have hwritesNodup : (f64WriteIndices writes).Nodup := by
    rw [hwritesIndices]
    exact hdestinations
  have hwritesTakeNodup (count : Nat) :
      (f64WriteIndices (writes.take count)).Nodup := by
    have htake : ((f64WriteIndices writes).take count).Nodup :=
      List.Nodup.sublist
        (List.take_sublist count (f64WriteIndices writes)) hwritesNodup
    simpa only [f64WriteIndices, List.map_take] using htake

  have hleftLoWrites : left.lo.index ∉ f64WriteIndices writes := by
    rw [hwritesIndices]
    exact hleftLoFresh
  have hleftHiWrites : left.hi.index ∉ f64WriteIndices writes := by
    rw [hwritesIndices]
    exact hleftHiFresh
  have hrightLoWrites : right.lo.index ∉ f64WriteIndices writes := by
    rw [hwritesIndices]
    exact hrightLoFresh
  have hrightHiWrites : right.hi.index ∉ f64WriteIndices writes := by
    rw [hwritesIndices]
    exact hrightHiFresh

  have hleftLoAt (count : Nat) :
      (applyF64Writes state (writes.take count)).f64.read left.lo.index =
        some (.finite leftLo) := by
    calc
      _ = state.f64.read left.lo.index :=
        readF64_after_writes_take_of_not_mem _ _ _ _ hleftLoWrites
      _ = some (.finite leftLo) := hleftLo
  have hleftHiAt (count : Nat) :
      (applyF64Writes state (writes.take count)).f64.read left.hi.index =
        some (.finite leftHi) := by
    calc
      _ = state.f64.read left.hi.index :=
        readF64_after_writes_take_of_not_mem _ _ _ _ hleftHiWrites
      _ = some (.finite leftHi) := hleftHi
  have hrightLoAt (count : Nat) :
      (applyF64Writes state (writes.take count)).f64.read right.lo.index =
        some (.finite rightLo) := by
    calc
      _ = state.f64.read right.lo.index :=
        readF64_after_writes_take_of_not_mem _ _ _ _ hrightLoWrites
      _ = some (.finite rightLo) := hrightLo
  have hrightHiAt (count : Nat) :
      (applyF64Writes state (writes.take count)).f64.read right.hi.index =
        some (.finite rightHi) := by
    calc
      _ = state.f64.read right.hi.index :=
        readF64_after_writes_take_of_not_mem _ _ _ _ hrightHiWrites
      _ = some (.finite rightHi) := hrightHi

  have hdown0At8 :
      (applyF64Writes state (writes.take 8)).f64.read tmp.down0.index =
        some down0Value :=
    readF64_after_writes_of_mem state (writes.take 8)
      (hwritesTakeNodup 8) (by simp [writes])
  have hdown1At8 :
      (applyF64Writes state (writes.take 8)).f64.read tmp.down1.index =
        some down1Value :=
    readF64_after_writes_of_mem state (writes.take 8)
      (hwritesTakeNodup 8) (by simp [writes])
  have hdown2At9 :
      (applyF64Writes state (writes.take 9)).f64.read tmp.down2.index =
        some down2Value :=
    readF64_after_writes_of_mem state (writes.take 9)
      (hwritesTakeNodup 9) (by simp [writes])
  have hdown3At9 :
      (applyF64Writes state (writes.take 9)).f64.read tmp.down3.index =
        some down3Value :=
    readF64_after_writes_of_mem state (writes.take 9)
      (hwritesTakeNodup 9) (by simp [writes])
  have hdown01At10 :
      (applyF64Writes state (writes.take 10)).f64.read tmp.down01.index =
        some down01Value :=
    readF64_after_writes_of_mem state (writes.take 10)
      (hwritesTakeNodup 10) (by simp [writes])
  have hdown23At10 :
      (applyF64Writes state (writes.take 10)).f64.read tmp.down23.index =
        some down23Value :=
    readF64_after_writes_of_mem state (writes.take 10)
      (hwritesTakeNodup 10) (by simp [writes])
  have hup0At11 :
      (applyF64Writes state (writes.take 11)).f64.read tmp.up0.index =
        some up0Value :=
    readF64_after_writes_of_mem state (writes.take 11)
      (hwritesTakeNodup 11) (by simp [writes])
  have hup1At11 :
      (applyF64Writes state (writes.take 11)).f64.read tmp.up1.index =
        some up1Value :=
    readF64_after_writes_of_mem state (writes.take 11)
      (hwritesTakeNodup 11) (by simp [writes])
  have hup2At12 :
      (applyF64Writes state (writes.take 12)).f64.read tmp.up2.index =
        some up2Value :=
    readF64_after_writes_of_mem state (writes.take 12)
      (hwritesTakeNodup 12) (by simp [writes])
  have hup3At12 :
      (applyF64Writes state (writes.take 12)).f64.read tmp.up3.index =
        some up3Value :=
    readF64_after_writes_of_mem state (writes.take 12)
      (hwritesTakeNodup 12) (by simp [writes])
  have hup01At13 :
      (applyF64Writes state (writes.take 13)).f64.read tmp.up01.index =
        some up01Value :=
    readF64_after_writes_of_mem state (writes.take 13)
      (hwritesTakeNodup 13) (by simp [writes])
  have hup23At13 :
      (applyF64Writes state (writes.take 13)).f64.read tmp.up23.index =
        some up23Value :=
    readF64_after_writes_of_mem state (writes.take 13)
      (hwritesTakeNodup 13) (by simp [writes])

  have hrun :
      executeCode module parameters thread
          (mulArithmeticFragment result left right tmp).toList state =
        some { control := .fallthrough, state := final } := by
    change executeCode module parameters thread
      [.binaryF64 .mul .down tmp.down0 left.lo right.lo,
       .binaryF64 .mul .down tmp.down1 left.lo right.hi,
       .binaryF64 .mul .down tmp.down2 left.hi right.lo,
       .binaryF64 .mul .down tmp.down3 left.hi right.hi,
       .binaryF64 .mul .up tmp.up0 left.lo right.lo,
       .binaryF64 .mul .up tmp.up1 left.lo right.hi,
       .binaryF64 .mul .up tmp.up2 left.hi right.lo,
       .binaryF64 .mul .up tmp.up3 left.hi right.hi,
       .minimumF64 tmp.down01 tmp.down0 tmp.down1,
       .minimumF64 tmp.down23 tmp.down2 tmp.down3,
       .minimumF64 result.lo tmp.down01 tmp.down23,
       .maximumF64 tmp.up01 tmp.up0 tmp.up1,
       .maximumF64 tmp.up23 tmp.up2 tmp.up3,
       .maximumF64 result.hi tmp.up01 tmp.up23] state = _
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .down) (resultValue := down0Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftLoAt 0)
      (hright := by
        simpa [writes, applyF64Writes] using hrightLoAt 0)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .down) (resultValue := down1Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftLoAt 1)
      (hright := by
        simpa [writes, applyF64Writes] using hrightHiAt 1)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .down) (resultValue := down2Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftHiAt 2)
      (hright := by
        simpa [writes, applyF64Writes] using hrightLoAt 2)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .down) (resultValue := down3Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftHiAt 3)
      (hright := by
        simpa [writes, applyF64Writes] using hrightHiAt 3)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .up) (resultValue := up0Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftLoAt 4)
      (hright := by
        simpa [writes, applyF64Writes] using hrightLoAt 4)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .up) (resultValue := up1Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftLoAt 5)
      (hright := by
        simpa [writes, applyF64Writes] using hrightHiAt 5)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .up) (resultValue := up2Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftHiAt 6)
      (hright := by
        simpa [writes, applyF64Writes] using hrightLoAt 6)
      (hvalue := by rfl)]
    rw [executeCode_binaryF64_cons
      (op := .mul) (rounding := .up) (resultValue := up3Value)
      (hleft := by
        simpa [writes, applyF64Writes] using hleftHiAt 7)
      (hright := by
        simpa [writes, applyF64Writes] using hrightHiAt 7)
      (hvalue := by rfl)]
    rw [executeCode_minimumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hdown0At8)
      (hright := by
        simpa [writes, applyF64Writes] using hdown1At8)]
    rw [executeCode_minimumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hdown2At9)
      (hright := by
        simpa [writes, applyF64Writes] using hdown3At9)]
    rw [executeCode_minimumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hdown01At10)
      (hright := by
        simpa [writes, applyF64Writes] using hdown23At10)]
    rw [executeCode_maximumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hup0At11)
      (hright := by
        simpa [writes, applyF64Writes] using hup1At11)]
    rw [executeCode_maximumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hup2At12)
      (hright := by
        simpa [writes, applyF64Writes] using hup3At12)]
    rw [executeCode_maximumF64_cons
      (hleft := by
        simpa [writes, applyF64Writes] using hup01At13)
      (hright := by
        simpa [writes, applyF64Writes] using hup23At13)]
    rfl

  refine ⟨final, hrun, ?_⟩
  constructor
  · change final.f64.read result.lo.index = some loValue
    change (applyF64Writes state (writes.take 14)).f64.read result.lo.index =
      some loValue
    exact readF64_after_writes_of_mem state (writes.take 14)
      (hwritesTakeNodup 14) (by simp [writes])
  · change final.f64.read result.hi.index = some hiValue
    change (applyF64Writes state (writes.take 14)).f64.read result.hi.index =
      some hiValue
    exact readF64_after_writes_of_mem state (writes.take 14)
      (hwritesTakeNodup 14) (by simp [writes])

end SparkInterval.PTX
