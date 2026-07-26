/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQSeed

/-!
# Checked finite traces for the factored small-`q` Gaussian recurrence

This module is the arithmetic certificate bridge for a bounded piece of the
version-3 small-conductor computation.  A certificate records:

* a disk `W` containing the exact Gaussian base `w`;
* checked multiplications for `W^2` and the initial ratio `W^3`; and
* a finite linked trace whose two checked products implement
  `z <- z * ratio` and `ratio <- ratio * W^2`.

`TraceCertificate.check maxSteps` is a kernel-reducible Boolean checker.  Its
soundness theorem proves that every accepted final disk contains the exact
powers used by the finite Gaussian recurrence.  The explicit `maxSteps`
guard bounds the amount of certificate data accepted by a caller.

The theorem begins after typed rational disks and multiplication witnesses
have been constructed.  It does **not** prove that a version-3 binary frame
was parsed into these values, that CUDA/PTX/SASS implements this checker, or
that a full production range supplied an accepted trace.  Those parser,
compiled-artifact refinement, and whole-range coverage edges remain separate.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQTrace

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQSeed

/-- The two disks carried between finite-Gaussian recurrence steps. -/
structure DiskGaussianState where
  z : ComplexDisk
  ratio : ComplexDisk
  deriving Repr, DecidableEq, BEq

namespace DiskGaussianState

/-- Semantic invariant at zero-based recurrence index `n`. -/
def ContainsPowers (state : DiskGaussianState) (w : ℂ) (n : ℕ) : Prop :=
  state.z.ContainsComplex (w ^ ((n + 1) ^ 2)) ∧
  state.ratio.ContainsComplex (w ^ (2 * (n + 1) + 1))

end DiskGaussianState

/-- The two directed disk multiplications proposed for one recurrence step. -/
structure StepCertificate where
  zTimesRatio : ComplexDisk.MulCertificate
  ratioTimesSquare : ComplexDisk.MulCertificate
  deriving Repr, DecidableEq, BEq

namespace StepCertificate

/-- State proposed by a step certificate. -/
def output (certificate : StepCertificate) : DiskGaussianState :=
  ⟨certificate.zTimesRatio.output,
    certificate.ratioTimesSquare.output⟩

/-- Arithmetic checks and exact links to the preceding state and shared
square disk.  Link checks prevent independently valid multiplication rows
from being reordered or substituted into a trace. -/
def WellFormed (certificate : StepCertificate) (square : ComplexDisk)
    (current : DiskGaussianState) : Prop :=
  certificate.zTimesRatio.check = true ∧
  certificate.ratioTimesSquare.check = true ∧
  certificate.zTimesRatio.left = current.z ∧
  certificate.zTimesRatio.right = current.ratio ∧
  certificate.ratioTimesSquare.left = current.ratio ∧
  certificate.ratioTimesSquare.right = square

instance instDecidableWellFormed (certificate : StepCertificate)
    (square : ComplexDisk) (current : DiskGaussianState) :
    Decidable (certificate.WellFormed square current) := by
  unfold WellFormed
  infer_instance

/-- Executable checker for a single linked recurrence row. -/
def check (certificate : StepCertificate) (square : ComplexDisk)
    (current : DiskGaussianState) : Bool :=
  decide (certificate.WellFormed square current)

theorem check_sound {certificate : StepCertificate} {square : ComplexDisk}
    {current : DiskGaussianState}
    (hcheck : certificate.check square current = true) :
    certificate.WellFormed square current :=
  of_decide_eq_true hcheck

/-- One accepted row preserves the exact power invariant. -/
theorem output_contains_powers {certificate : StepCertificate}
    {square : ComplexDisk} {current : DiskGaussianState} {w : ℂ} {n : ℕ}
    (hvalid : certificate.WellFormed square current)
    (hsquare : square.ContainsComplex (w ^ 2))
    (hcurrent : current.ContainsPowers w n) :
    certificate.output.ContainsPowers w (n + 1) := by
  rcases hvalid with
    ⟨hzCheck, hratioCheck, hzLeft, hzRight, hratioLeft, hratioRight⟩
  have hzLeftContains :
      certificate.zTimesRatio.left.ContainsComplex (w ^ ((n + 1) ^ 2)) := by
    rw [hzLeft]
    exact hcurrent.1
  have hzRightContains :
      certificate.zTimesRatio.right.ContainsComplex
        (w ^ (2 * (n + 1) + 1)) := by
    rw [hzRight]
    exact hcurrent.2
  have hratioLeftContains :
      certificate.ratioTimesSquare.left.ContainsComplex
        (w ^ (2 * (n + 1) + 1)) := by
    rw [hratioLeft]
    exact hcurrent.2
  have hratioRightContains :
      certificate.ratioTimesSquare.right.ContainsComplex (w ^ 2) := by
    rw [hratioRight]
    exact hsquare
  have hzProduct := ComplexDisk.MulCertificate.output_contains_mul
    hzCheck hzLeftContains hzRightContains
  have hratioProduct := ComplexDisk.MulCertificate.output_contains_mul
    hratioCheck hratioLeftContains hratioRightContains
  constructor
  · change certificate.zTimesRatio.output.ContainsComplex
      (w ^ (((n + 1) + 1) ^ 2))
    rw [← pow_add] at hzProduct
    have hexponent :
        (n + 1) ^ 2 + (2 * (n + 1) + 1) = ((n + 1) + 1) ^ 2 := by
      ring
    rw [hexponent] at hzProduct
    exact hzProduct
  · change certificate.ratioTimesSquare.output.ContainsComplex
      (w ^ (2 * ((n + 1) + 1) + 1))
    rw [← pow_add] at hratioProduct
    have hexponent :
        (2 * (n + 1) + 1) + 2 = 2 * ((n + 1) + 1) + 1 := by
      ring
    rw [hexponent] at hratioProduct
    exact hratioProduct

end StepCertificate

/-- Exact linked-list predicate corresponding to `checkLinked`. -/
def Linked (square : ComplexDisk) :
    DiskGaussianState → List StepCertificate → Prop
  | _, [] => True
  | current, step :: rest =>
      step.WellFormed square current ∧ Linked square step.output rest

/-- Boolean replay of all row checks and state links. -/
def checkLinked (square : ComplexDisk) :
    DiskGaussianState → List StepCertificate → Bool
  | _, [] => true
  | current, step :: rest =>
      step.check square current && checkLinked square step.output rest

theorem checkLinked_sound {square : ComplexDisk}
    {current : DiskGaussianState} {steps : List StepCertificate}
    (hcheck : checkLinked square current steps = true) :
    Linked square current steps := by
  induction steps generalizing current with
  | nil => simp [Linked]
  | cons step rest ih =>
      simp only [checkLinked, Bool.and_eq_true] at hcheck
      exact ⟨StepCertificate.check_sound hcheck.1, ih hcheck.2⟩

/-- Replay a trace by retaining the two proposed output disks of each row. -/
def run : DiskGaussianState → List StepCertificate → DiskGaussianState
  | current, [] => current
  | _, step :: rest => run step.output rest

/-- A linked trace transports the exact power invariant to its final row. -/
theorem run_contains_powers {square : ComplexDisk}
    {current : DiskGaussianState} {steps : List StepCertificate}
    {w : ℂ} {n : ℕ}
    (hsquare : square.ContainsComplex (w ^ 2))
    (hlinked : Linked square current steps)
    (hcurrent : current.ContainsPowers w n) :
    (run current steps).ContainsPowers w (n + steps.length) := by
  induction steps generalizing current n with
  | nil => simpa [run] using hcurrent
  | cons step rest ih =>
      rcases hlinked with ⟨hstep, hrest⟩
      have hnext := StepCertificate.output_contains_powers
        hstep hsquare hcurrent
      have hfinal := ih hrest hnext
      simpa [run, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm] using hfinal

/-- A bounded certificate for the complete typed recurrence trace. -/
structure TraceCertificate where
  base : ComplexDisk
  square : ComplexDisk.MulCertificate
  cube : ComplexDisk.MulCertificate
  steps : List StepCertificate
  deriving Repr, DecidableEq, BEq

namespace TraceCertificate

def initialState (certificate : TraceCertificate) : DiskGaussianState :=
  ⟨certificate.base, certificate.cube.output⟩

def output (certificate : TraceCertificate) : DiskGaussianState :=
  run certificate.initialState certificate.steps

/-- Checks for the shared square, initial cube, and their exact links. -/
def InitialWellFormed (certificate : TraceCertificate) : Prop :=
  certificate.square.check = true ∧
  certificate.cube.check = true ∧
  certificate.square.left = certificate.base ∧
  certificate.square.right = certificate.base ∧
  certificate.cube.left = certificate.square.output ∧
  certificate.cube.right = certificate.base

instance instDecidableInitialWellFormed (certificate : TraceCertificate) :
    Decidable certificate.InitialWellFormed := by
  unfold InitialWellFormed
  infer_instance

/-- Proposition recovered from an accepted bounded trace. -/
def Accepted (certificate : TraceCertificate) (maxSteps : ℕ) : Prop :=
  certificate.steps.length ≤ maxSteps ∧
  certificate.InitialWellFormed ∧
  Linked certificate.square.output certificate.initialState certificate.steps

/-- Kernel-reducible checker.  Producers are untrusted; both arithmetic and
all state links are recomputed here. -/
def check (certificate : TraceCertificate) (maxSteps : ℕ) : Bool :=
  decide (certificate.steps.length ≤ maxSteps) &&
  decide certificate.InitialWellFormed &&
  checkLinked certificate.square.output certificate.initialState
    certificate.steps

theorem checker_sound {certificate : TraceCertificate} {maxSteps : ℕ}
    (hcheck : certificate.check maxSteps = true) :
    certificate.Accepted maxSteps := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1.1, hcheck.1.2, checkLinked_sound hcheck.2⟩

/-- An accepted initialization contains `w^2` in its shared square disk. -/
theorem square_contains {certificate : TraceCertificate} {w : ℂ}
    (hinitial : certificate.InitialWellFormed)
    (hbase : certificate.base.ContainsComplex w) :
    certificate.square.output.ContainsComplex (w ^ 2) := by
  rcases hinitial with
    ⟨hsquareCheck, _, hsquareLeft, hsquareRight, _, _⟩
  have hleft : certificate.square.left.ContainsComplex w := by
    rw [hsquareLeft]
    exact hbase
  have hright : certificate.square.right.ContainsComplex w := by
    rw [hsquareRight]
    exact hbase
  simpa [pow_two] using
    (ComplexDisk.MulCertificate.output_contains_mul
      hsquareCheck hleft hright)

/-- An accepted initialization establishes recurrence index zero. -/
theorem initial_contains_powers {certificate : TraceCertificate} {w : ℂ}
    (hinitial : certificate.InitialWellFormed)
    (hbase : certificate.base.ContainsComplex w) :
    certificate.initialState.ContainsPowers w 0 := by
  rcases hinitial with
    ⟨hsquareCheck, hcubeCheck, hsquareLeft, hsquareRight,
      hcubeLeft, hcubeRight⟩
  have hsquare : certificate.square.output.ContainsComplex (w ^ 2) := by
    have hleft : certificate.square.left.ContainsComplex w := by
      rw [hsquareLeft]
      exact hbase
    have hright : certificate.square.right.ContainsComplex w := by
      rw [hsquareRight]
      exact hbase
    simpa [pow_two] using
      (ComplexDisk.MulCertificate.output_contains_mul
        hsquareCheck hleft hright)
  have hcubeLeftContains :
      certificate.cube.left.ContainsComplex (w ^ 2) := by
    rw [hcubeLeft]
    exact hsquare
  have hcubeRightContains : certificate.cube.right.ContainsComplex w := by
    rw [hcubeRight]
    exact hbase
  have hcube := ComplexDisk.MulCertificate.output_contains_mul
    hcubeCheck hcubeLeftContains hcubeRightContains
  constructor
  · simpa [initialState, DiskGaussianState.ContainsPowers] using hbase
  · change certificate.cube.output.ContainsComplex (w ^ (2 * (0 + 1) + 1))
    simpa [pow_succ] using hcube

/-- Main arithmetic application theorem for an accepted bounded trace. -/
theorem output_contains_powers {certificate : TraceCertificate}
    {maxSteps : ℕ} {w : ℂ}
    (hcheck : certificate.check maxSteps = true)
    (hbase : certificate.base.ContainsComplex w) :
    certificate.output.ContainsPowers w certificate.steps.length := by
  have haccepted := checker_sound hcheck
  have hsquare := square_contains haccepted.2.1 hbase
  have hinitial := initial_contains_powers haccepted.2.1 hbase
  have hrun := run_contains_powers hsquare haccepted.2.2 hinitial
  simpa [output] using hrun

/-- The accepted disks contain the exact state from the source-level
finite-Gaussian recurrence, not merely two coincidentally shaped powers. -/
theorem output_contains_exact_after {certificate : TraceCertificate}
    {maxSteps : ℕ} {w : ℂ}
    (hcheck : certificate.check maxSteps = true)
    (hbase : certificate.base.ContainsComplex w) :
    certificate.output.z.ContainsComplex
        (ExactGaussianState.after w certificate.steps.length).z ∧
      certificate.output.ratio.ContainsComplex
        (ExactGaussianState.after w certificate.steps.length).ratio := by
  have hcontains := output_contains_powers hcheck hbase
  have hexact := ExactGaussianState.after_eq_powers
    w certificate.steps.length
  rw [hexact.1, hexact.2]
  exact hcontains

end TraceCertificate

end SparkInterval.Dirichlet.FactoredSmallQTrace
