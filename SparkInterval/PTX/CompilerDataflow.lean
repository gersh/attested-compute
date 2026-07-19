import SparkInterval.PTX.Generator

/-!
# Register-allocation dataflow invariants

This file proves freshness and non-aliasing facts about the concrete compiler
in `Generator.lean`.  In particular, the multiplication proof talks about the
exact fourteen f64 destinations allocated by `allocateMulRegisters`; it is not
an abstract assumption about a second allocator.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Both endpoints of an interval register pair were allocated below `bound`.
This is the invariant needed when a compiler node consumes results produced by
earlier nodes. -/
def IntervalRegisters.Below (registers : IntervalRegisters) (bound : Nat) : Prop :=
  registers.lo.index < bound ∧ registers.hi.index < bound

/-- The f64 destinations allocated for the exact multiplication fragment, in
the same order in which `mulArithmeticFragment` writes them. -/
def MulRegisterAllocation.destinationIndices
    (allocation : MulRegisterAllocation) : List Nat :=
  [allocation.temporaries.down0.index,
   allocation.temporaries.down1.index,
   allocation.temporaries.down2.index,
   allocation.temporaries.down3.index,
   allocation.temporaries.up0.index,
   allocation.temporaries.up1.index,
   allocation.temporaries.up2.index,
   allocation.temporaries.up3.index,
   allocation.temporaries.down01.index,
   allocation.temporaries.down23.index,
   allocation.result.lo.index,
   allocation.temporaries.up01.index,
   allocation.temporaries.up23.index,
   allocation.result.hi.index]

/-- The multiplication allocator consumes exactly fourteen consecutive f64
registers. -/
theorem allocateMulRegisters_nextF64 (builder : Builder) :
    (allocateMulRegisters builder).builder.nextF64 = builder.nextF64 + 14 := by
  simp [allocateMulRegisters, Builder.freshInterval, Builder.freshF64]

/-- Exact indices assigned by `allocateMulRegisters`. -/
theorem allocateMulRegisters_destinationIndices (builder : Builder) :
    (allocateMulRegisters builder).destinationIndices =
      [builder.nextF64, builder.nextF64 + 1, builder.nextF64 + 2,
       builder.nextF64 + 3, builder.nextF64 + 4, builder.nextF64 + 5,
       builder.nextF64 + 6, builder.nextF64 + 7, builder.nextF64 + 8,
       builder.nextF64 + 9, builder.nextF64 + 12, builder.nextF64 + 10,
       builder.nextF64 + 11, builder.nextF64 + 13] := by
  simp [MulRegisterAllocation.destinationIndices, allocateMulRegisters,
    Builder.freshInterval, Builder.freshF64]

/-- Every f64 destination allocated for multiplication is distinct. -/
theorem allocateMulRegisters_destinationIndices_nodup (builder : Builder) :
    (allocateMulRegisters builder).destinationIndices.Nodup := by
  simp [MulRegisterAllocation.destinationIndices, allocateMulRegisters,
    Builder.freshInterval, Builder.freshF64]
  omega

/-- Every multiplication destination is at or above the allocator's incoming
f64 frontier. -/
theorem allocateMulRegisters_destination_ge (builder : Builder) {index : Nat}
    (hindex : index ∈ (allocateMulRegisters builder).destinationIndices) :
    builder.nextF64 ≤ index := by
  simp [MulRegisterAllocation.destinationIndices, allocateMulRegisters,
    Builder.freshInterval, Builder.freshF64] at hindex
  omega

/-- An endpoint allocated before the incoming f64 frontier cannot alias any
multiplication destination. -/
theorem allocateMulRegisters_endpoint_fresh (builder : Builder) {index : Nat}
    (hindex : index < builder.nextF64) :
    index ∉ (allocateMulRegisters builder).destinationIndices := by
  intro hmember
  exact (Nat.not_le_of_gt hindex)
    (allocateMulRegisters_destination_ge builder hmember)

/-- Both endpoints of an earlier interval are absent from every multiplication
destination. -/
theorem allocateMulRegisters_source_fresh (builder : Builder)
    (source : IntervalRegisters) (hsource : source.Below builder.nextF64) :
    source.lo.index ∉ (allocateMulRegisters builder).destinationIndices ∧
      source.hi.index ∉ (allocateMulRegisters builder).destinationIndices := by
  exact ⟨allocateMulRegisters_endpoint_fresh builder hsource.1,
    allocateMulRegisters_endpoint_fresh builder hsource.2⟩

/-- The result endpoints of the concrete multiplication allocation are the
last two of its fourteen consecutive destinations. -/
theorem allocateMulRegisters_result_indices (builder : Builder) :
    (allocateMulRegisters builder).result.lo.index = builder.nextF64 + 12 ∧
      (allocateMulRegisters builder).result.hi.index = builder.nextF64 + 13 := by
  simp [allocateMulRegisters, Builder.freshInterval, Builder.freshF64]

/-- The concrete multiplication allocator never aliases its two result
endpoints. -/
theorem allocateMulRegisters_result_distinct (builder : Builder) :
    (allocateMulRegisters builder).result.lo.index ≠
      (allocateMulRegisters builder).result.hi.index := by
  simp [allocateMulRegisters, Builder.freshInterval, Builder.freshF64]

/-! ## Primitive frontier preservation -/

/-- Emitting an instruction does not allocate an f64 register. -/
@[simp] theorem Builder.emit_nextF64 (builder : Builder)
    (instruction : Instruction) :
    (builder.emit instruction).nextF64 = builder.nextF64 := by
  rfl

/-- A finite guard allocates predicate and u64 registers only. -/
@[simp] theorem emitFiniteGuard_nextF64 (value : IntervalRegisters)
    (builder : Builder) :
    (emitFiniteGuard value builder).nextF64 = builder.nextF64 := by
  simp [emitFiniteGuard, Builder.freshU64, Builder.freshPred, Builder.emit]

/-- `freshInterval` returns the next two f64 registers. -/
theorem Builder.freshInterval_indices (builder : Builder) :
    builder.freshInterval.1.lo.index = builder.nextF64 ∧
      builder.freshInterval.1.hi.index = builder.nextF64 + 1 := by
  simp [Builder.freshInterval, Builder.freshF64]

/-- `freshInterval` advances the f64 frontier by exactly two. -/
@[simp] theorem Builder.freshInterval_nextF64 (builder : Builder) :
    builder.freshInterval.2.nextF64 = builder.nextF64 + 2 := by
  simp [Builder.freshInterval, Builder.freshF64]

/-- An interval freshly allocated at `builder.nextF64` cannot alias an earlier
interval, and its own endpoints are distinct. -/
theorem Builder.freshInterval_fresh (builder : Builder)
    (source : IntervalRegisters) (hsource : source.Below builder.nextF64) :
    builder.freshInterval.1.lo.index ≠ builder.freshInterval.1.hi.index ∧
      builder.freshInterval.1.lo.index ≠ source.lo.index ∧
      builder.freshInterval.1.lo.index ≠ source.hi.index ∧
      builder.freshInterval.1.hi.index ≠ source.lo.index ∧
      builder.freshInterval.1.hi.index ≠ source.hi.index := by
  unfold IntervalRegisters.Below at hsource
  simp [Builder.freshInterval, Builder.freshF64]
  omega

/-! ## Guarded binary compiler nodes -/

/-- Addition allocates exactly the incoming frontier and its successor for
the result. -/
theorem compileAdd_result_indices (left right : IntervalRegisters)
    (builder : Builder) :
    (compileAdd left right builder).1.lo.index = builder.nextF64 ∧
      (compileAdd left right builder).1.hi.index = builder.nextF64 + 1 := by
  simp [compileAdd, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    addArithmeticFragment]

/-- Addition consumes exactly two f64 registers; its guards and emitted
instructions consume none. -/
@[simp] theorem compileAdd_nextF64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileAdd left right builder).2.nextF64 = builder.nextF64 + 2 := by
  simp [compileAdd, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    addArithmeticFragment]

/-- The concrete addition result is pairwise distinct and cannot alias either
pre-frontier operand. -/
theorem compileAdd_result_fresh (left right : IntervalRegisters)
    (builder : Builder) (hleft : left.Below builder.nextF64)
    (hright : right.Below builder.nextF64) :
    let result := (compileAdd left right builder).1
    result.lo.index ≠ result.hi.index ∧
      result.lo.index ≠ left.lo.index ∧
      result.lo.index ≠ left.hi.index ∧
      result.lo.index ≠ right.lo.index ∧
      result.lo.index ≠ right.hi.index := by
  unfold IntervalRegisters.Below at hleft hright
  simp [compileAdd, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    addArithmeticFragment]
  omega

/-- Subtraction allocates exactly the incoming frontier and its successor for
the result. -/
theorem compileSub_result_indices (left right : IntervalRegisters)
    (builder : Builder) :
    (compileSub left right builder).1.lo.index = builder.nextF64 ∧
      (compileSub left right builder).1.hi.index = builder.nextF64 + 1 := by
  simp [compileSub, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    subArithmeticFragment]

/-- Subtraction consumes exactly two f64 registers. -/
@[simp] theorem compileSub_nextF64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileSub left right builder).2.nextF64 = builder.nextF64 + 2 := by
  simp [compileSub, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    subArithmeticFragment]

/-- The concrete subtraction result is pairwise distinct and cannot alias
either pre-frontier operand. -/
theorem compileSub_result_fresh (left right : IntervalRegisters)
    (builder : Builder) (hleft : left.Below builder.nextF64)
    (hright : right.Below builder.nextF64) :
    let result := (compileSub left right builder).1
    result.lo.index ≠ result.hi.index ∧
      result.lo.index ≠ left.lo.index ∧
      result.lo.index ≠ left.hi.index ∧
      result.lo.index ≠ right.lo.index ∧
      result.lo.index ≠ right.hi.index := by
  unfold IntervalRegisters.Below at hleft hright
  simp [compileSub, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    subArithmeticFragment]
  omega

/-! ## Guarded multiplication compiler node -/

/-- Name the exact pure allocation nested inside `compileMul`, after its two
finite guards.  The equality theorem below prevents this proof-facing name
from drifting away from the production compiler. -/
def compileMulAllocation (left right : IntervalRegisters) (builder : Builder) :
    MulRegisterAllocation :=
  allocateMulRegisters
    (emitFiniteGuard right (emitFiniteGuard left builder))

/-- The production compiler returns the result of `compileMulAllocation`. -/
theorem compileMul_result_eq_allocation (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).1 =
      (compileMulAllocation left right builder).result := by
  rfl

/-- The internal allocation used by `compileMul` has fourteen distinct
destinations. -/
theorem compileMul_destinationIndices_nodup (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMulAllocation left right builder).destinationIndices.Nodup := by
  exact allocateMulRegisters_destinationIndices_nodup _

/-- Earlier source endpoints cannot alias any destination in the exact
allocation nested inside `compileMul`. -/
theorem compileMul_source_fresh (left right source : IntervalRegisters)
    (builder : Builder) (hsource : source.Below builder.nextF64) :
    source.lo.index ∉
        (compileMulAllocation left right builder).destinationIndices ∧
      source.hi.index ∉
        (compileMulAllocation left right builder).destinationIndices := by
  apply allocateMulRegisters_source_fresh
  simpa [compileMulAllocation] using hsource

/-- Multiplication returns the final two registers in its fourteen-register
allocation. -/
theorem compileMul_result_indices (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).1.lo.index = builder.nextF64 + 12 ∧
      (compileMul left right builder).1.hi.index = builder.nextF64 + 13 := by
  simp [compileMul, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    allocateMulRegisters, Builder.freshInterval, Builder.freshF64,
    Builder.emit, mulArithmeticFragment]

/-- Multiplication consumes exactly fourteen f64 registers. -/
@[simp] theorem compileMul_nextF64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).2.nextF64 = builder.nextF64 + 14 := by
  simp [compileMul, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    allocateMulRegisters, Builder.freshInterval, Builder.freshF64,
    Builder.emit, mulArithmeticFragment]

/-- The two multiplication result endpoints are distinct. -/
theorem compileMul_result_distinct (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).1.lo.index ≠
      (compileMul left right builder).1.hi.index := by
  simp [compileMul, emitFiniteGuard, Builder.freshU64, Builder.freshPred,
    allocateMulRegisters, Builder.freshInterval, Builder.freshF64,
    Builder.emit, mulArithmeticFragment]

/-- Package the exact distinctness and four source-freshness obligations for
the multiplication refinement theorem. -/
theorem compileMul_refinement_freshness (left right : IntervalRegisters)
    (builder : Builder) (hleft : left.Below builder.nextF64)
    (hright : right.Below builder.nextF64) :
    let destinations :=
      (compileMulAllocation left right builder).destinationIndices
    destinations.Nodup ∧
      left.lo.index ∉ destinations ∧
      left.hi.index ∉ destinations ∧
      right.lo.index ∉ destinations ∧
      right.hi.index ∉ destinations := by
  have hleftFresh := compileMul_source_fresh left right left builder hleft
  have hrightFresh := compileMul_source_fresh left right right builder hright
  exact ⟨compileMul_destinationIndices_nodup left right builder,
    hleftFresh.1, hleftFresh.2, hrightFresh.1, hrightFresh.2⟩

/-! ## Returned results and f64 frontiers -/

/-- A compiled addition result lies below its updated f64 frontier. -/
theorem compileAdd_result_below (left right : IntervalRegisters)
    (builder : Builder) :
    (compileAdd left right builder).1.Below
      (compileAdd left right builder).2.nextF64 := by
  unfold IntervalRegisters.Below
  have hindices := compileAdd_result_indices left right builder
  rw [compileAdd_nextF64]
  omega

/-- A compiled subtraction result lies below its updated f64 frontier. -/
theorem compileSub_result_below (left right : IntervalRegisters)
    (builder : Builder) :
    (compileSub left right builder).1.Below
      (compileSub left right builder).2.nextF64 := by
  unfold IntervalRegisters.Below
  have hindices := compileSub_result_indices left right builder
  rw [compileSub_nextF64]
  omega

/-- A compiled multiplication result lies below its updated f64 frontier. -/
theorem compileMul_result_below (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).1.Below
      (compileMul left right builder).2.nextF64 := by
  unfold IntervalRegisters.Below
  have hindices := compileMul_result_indices left right builder
  rw [compileMul_nextF64]
  omega

/-- Repeated multiplication advances the f64 frontier by fourteen registers
per iteration. -/
theorem compilePowLoop_nextF64 (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder) :
    (compilePowLoop base count current builder).2.nextF64 =
      builder.nextF64 + count * 14 := by
  induction count generalizing current builder with
  | zero => simp [compilePowLoop]
  | succ count induction =>
      rw [compilePowLoop, induction]
      rw [compileMul_nextF64]
      omega

/-- If the initial accumulator is already allocated, the result of every
iteration remains below the final frontier. -/
theorem compilePowLoop_result_below (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder)
    (hcurrent : current.Below builder.nextF64) :
    (compilePowLoop base count current builder).1.Below
      (compilePowLoop base count current builder).2.nextF64 := by
  induction count generalizing current builder with
  | zero => simpa [compilePowLoop] using hcurrent
  | succ count induction =>
      rw [compilePowLoop]
      apply induction
      exact compileMul_result_below current base builder

/-! ## Whole-expression allocation accounting -/

/-- The exact number of f64 registers allocated by an expression compiler
invocation.  Finite guards allocate only predicate and u64 registers. -/
def PolynomialExpr.f64RegisterCost : PolynomialExpr → Nat
  | .const _ => 2
  | .var _ => 2
  | .neg argument => argument.f64RegisterCost + 2
  | .add left right =>
      left.f64RegisterCost + right.f64RegisterCost + 2
  | .sub left right =>
      left.f64RegisterCost + right.f64RegisterCost + 2
  | .mul left right =>
      left.f64RegisterCost + right.f64RegisterCost + 14
  | .powNat argument exponent =>
      argument.f64RegisterCost + 2 + exponent * 14

/-- Loading a constant allocates exactly two f64 registers. -/
@[simp] theorem compileConst_nextF64 (value : IntervalBits) (builder : Builder) :
    (compileConst value builder).2.nextF64 = builder.nextF64 + 2 := by
  simp [compileConst, Builder.freshInterval, Builder.freshF64, Builder.emit]

/-- A freshly compiled constant lies below the updated frontier. -/
theorem compileConst_result_below (value : IntervalBits) (builder : Builder) :
    (compileConst value builder).1.Below
      (compileConst value builder).2.nextF64 := by
  unfold IntervalRegisters.Below
  simp [compileConst, Builder.freshInterval, Builder.freshF64, Builder.emit]
  omega

/-- Exact f64 frontier accounting for the recursive production compiler. -/
theorem compileExpr_nextF64 (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).2.nextF64 =
      builder.nextF64 + expression.f64RegisterCost := by
  induction expression generalizing builder with
  | const value =>
      simp [compileExpr, PolynomialExpr.f64RegisterCost]
  | var index =>
      simp [compileExpr, PolynomialExpr.f64RegisterCost,
        Builder.freshInterval, Builder.freshF64, Builder.emit]
  | neg argument induction =>
      simp [compileExpr, PolynomialExpr.f64RegisterCost,
        Builder.freshInterval, Builder.freshF64, Builder.emit,
        induction]
      omega
  | add left right leftInduction rightInduction =>
      rw [compileExpr, compileAdd_nextF64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.f64RegisterCost]
      omega
  | sub left right leftInduction rightInduction =>
      rw [compileExpr, compileSub_nextF64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.f64RegisterCost]
      omega
  | mul left right leftInduction rightInduction =>
      rw [compileExpr, compileMul_nextF64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.f64RegisterCost]
      omega
  | powNat argument exponent induction =>
      rw [compileExpr, compilePowLoop_nextF64, compileConst_nextF64,
        induction builder]
      simp [PolynomialExpr.f64RegisterCost]
      omega

/-- Compiling an expression never moves the f64 frontier backwards. -/
theorem compileExpr_nextF64_mono (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    builder.nextF64 ≤ (compileExpr rowBase expression builder).2.nextF64 := by
  rw [compileExpr_nextF64]
  exact Nat.le_add_right _ _

/-- A result below one frontier stays below every later frontier. -/
theorem IntervalRegisters.Below.mono {registers : IntervalRegisters}
    {earlier later : Nat} (hregisters : registers.Below earlier)
    (hfrontier : earlier ≤ later) : registers.Below later := by
  unfold IntervalRegisters.Below at hregisters ⊢
  omega

/-- Every expression compiler result is allocated below the frontier returned
with it. -/
theorem compileExpr_result_below (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).1.Below
      (compileExpr rowBase expression builder).2.nextF64 := by
  induction expression generalizing builder with
  | const value =>
      exact compileConst_result_below value builder
  | var index =>
      unfold IntervalRegisters.Below
      simp [compileExpr, Builder.freshInterval, Builder.freshF64, Builder.emit]
      omega
  | neg argument induction =>
      unfold IntervalRegisters.Below
      simp [compileExpr, Builder.freshInterval, Builder.freshF64, Builder.emit]
      omega
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      exact compileAdd_result_below _ _ _
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      exact compileSub_result_below _ _ _
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      exact compileMul_result_below _ _ _
  | powNat argument exponent induction =>
      rw [compileExpr]
      apply compilePowLoop_result_below
      exact compileConst_result_below _ _

/-- After compiling two child expressions in the production left-to-right
order, both returned intervals lie below the shared frontier passed to their
parent operation. -/
theorem compileExpr_pair_below (rowBase : Reg .u64)
    (left right : PolynomialExpr) (builder : Builder) :
    let leftCompiled := compileExpr rowBase left builder
    let rightCompiled := compileExpr rowBase right leftCompiled.2
    leftCompiled.1.Below rightCompiled.2.nextF64 ∧
      rightCompiled.1.Below rightCompiled.2.nextF64 := by
  dsimp only
  constructor
  · exact (compileExpr_result_below rowBase left builder).mono
      (compileExpr_nextF64_mono rowBase right
        (compileExpr rowBase left builder).2)
  · exact compileExpr_result_below rowBase right
      (compileExpr rowBase left builder).2

end SparkInterval.PTX
