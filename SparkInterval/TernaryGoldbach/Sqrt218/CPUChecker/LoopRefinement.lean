/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.IR

/-!
# Symbolic loop refinement for the Sqrt218 fixed-width CPU checker

This module lifts the data-independent one-step refinement in `IR` through
the complete event loop.  It contains no closed production data and does not
evaluate a production archive.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

private theorem exceptBind_ok {ε α β : Type}
    {first : Except ε α} {rest : α → Except ε β} {result : β}
    (hbind : first >>= rest = .ok result) :
    ∃ value, first = .ok value ∧ rest value = .ok result := by
  change Except.bind first rest = .ok result at hbind
  cases first <;> simp_all [Except.bind]

theorem step_nextEvent
    {image : ArchiveImage} {state next : ScanState}
    (hstep : step image state = .ok next) :
    next.nextEvent = state.nextEvent + 1 := by
  unfold step at hstep
  rcases exceptBind_ok hstep with ⟨event, _hevent, hstep⟩
  rcases exceptBind_ok hstep with ⟨prime, _hprime, hstep⟩
  by_cases hguard :
      event.value < limbBase ∧
        prime.prime < limbBase ∧
        event.exponent < limbBase ∧
        0 < event.exponent ∧
        event.value ≤ image.header.bound ∧
        event.floorSqrt = Nat.sqrt event.value ∧
        (state.nextEvent = 0 ∨
          state.lastEventValue < event.value)
  · simp only [if_pos hguard] at hstep
    rcases exceptBind_ok hstep with
      ⟨expectedPower, _hpower, hstep⟩
    by_cases hpowerValue : expectedPower = event.value
    · simp only [if_pos hpowerValue] at hstep
      rcases exceptBind_ok hstep with
        ⟨_upperWord, _hupperWord, hstep⟩
      rcases exceptBind_ok hstep with
        ⟨_upperLog, _hupperLog, hstep⟩
      rcases exceptBind_ok hstep with ⟨_term, _hterm, hstep⟩
      rcases exceptBind_ok hstep with
        ⟨_weighted, _hweighted, hstep⟩
      rcases exceptBind_ok hstep with
        ⟨_lowerLog, _hlowerLog, hstep⟩
      rcases exceptBind_ok hstep with ⟨_psi, _hpsi, hstep⟩
      rcases exceptBind_ok hstep with ⟨left, _hleft, hstep⟩
      rcases exceptBind_ok hstep with ⟨right, _hright, hstep⟩
      by_cases hhead : left.lessThan right = true
      · simp only [if_pos hhead] at hstep
        cases hstep
        rfl
      · simp only [if_neg hhead] at hstep
        contradiction
    · simp only [if_neg hpowerValue] at hstep
      contradiction
  · simp only [if_neg hguard] at hstep
    contradiction

/-- A successful IR loop is a bounded sequence of successful kernel steps.

The witness `count` is the number of transitions actually taken.  The two
index equalities make the progress invariant explicit: every successful
transition increments `nextEvent` once, and successful termination occurs
exactly at the end of the event table. -/
theorem runLoop_refines_kernel
    {image : ArchiveImage} {fuel : Nat} {entry exit : ScanState}
    (hheader : headerCheck image = true)
    (hentry : entry.nextEvent ≤ image.events.length)
    (hrun : runLoop image fuel entry = .ok exit) :
    ∃ count,
      count ≤ fuel ∧
        exit.nextEvent = entry.nextEvent + count ∧
        exit.nextEvent = image.events.length ∧
        TGComputeContracts.Sqrt218.runFixedEvents
            image.events.length
            (kernelEventAt image)
            (kernelLogLowerAt image)
            (kernelLogUpperAt image)
            entry.nextEvent count entry.toFixedState =
          some exit.toFixedState := by
  induction fuel generalizing entry exit with
  | zero =>
      rw [runLoop] at hrun
      by_cases hdone : entry.nextEvent = image.events.length
      · simp only [if_pos hdone] at hrun
        change Except.ok entry = Except.ok exit at hrun
        have hexit : entry = exit := Except.ok.inj hrun
        subst exit
        refine ⟨0, Nat.zero_le _, by simp, hdone, ?_⟩
        rfl
      · simp only [if_neg hdone] at hrun
        contradiction
  | succ fuel ih =>
      rw [runLoop] at hrun
      by_cases hdone : entry.nextEvent = image.events.length
      · simp only [if_pos hdone] at hrun
        change Except.ok entry = Except.ok exit at hrun
        have hexit : entry = exit := Except.ok.inj hrun
        subst exit
        refine ⟨0, Nat.zero_le _, by simp, hdone, ?_⟩
        rfl
      · simp only [if_neg hdone] at hrun
        rcases exceptBind_ok hrun with ⟨next, hstep, htail⟩
        have hentryLt : entry.nextEvent < image.events.length := by
          omega
        have hnextEvent :
            next.nextEvent = entry.nextEvent + 1 :=
          step_nextEvent hstep
        have hnextBound : next.nextEvent ≤ image.events.length := by
          omega
        obtain
          ⟨count, hcountFuel, hexitIndex, hexitEnd, hkernelTail⟩ :=
            ih hnextBound htail
        have hkernelStep :
            TGComputeContracts.Sqrt218.fixedEventStep
                (kernelEventAt image)
                (kernelLogLowerAt image)
                (kernelLogUpperAt image)
                entry.nextEvent entry.toFixedState =
              some next.toFixedState :=
          stepRefinesKernel image entry next hheader hstep
        refine
          ⟨count + 1, by omega, by omega, hexitEnd, ?_⟩
        simp only [TGComputeContracts.Sqrt218.runFixedEvents,
          TGComputeContracts.Sqrt218.runOptionalSteps,
          TGComputeContracts.Sqrt218.boundedFixedEventStep,
          if_pos hentryLt, hkernelStep]
        simpa [TGComputeContracts.Sqrt218.runFixedEvents,
          hnextEvent] using hkernelTail

/-- The complete IR event pass refines the complete generic fixed-event fold.

This theorem is purely symbolic: it quantifies over an arbitrary image and
does not reduce `runEvents` for any concrete certificate. -/
theorem runEvents_refines_kernel
    {image : ArchiveImage} {exit : ScanState}
    (hheader : headerCheck image = true)
    (hrun : runEvents image = .ok exit) :
    TGComputeContracts.Sqrt218.runFixedEvents
        image.events.length
        (kernelEventAt image)
        (kernelLogLowerAt image)
        (kernelLogUpperAt image)
        0 image.events.length
        TGComputeContracts.Sqrt218.FixedState.zero =
      some exit.toFixedState := by
  unfold runEvents at hrun
  obtain ⟨count, _hcountFuel, hexitIndex, hexitEnd, hkernel⟩ :=
    runLoop_refines_kernel hheader (entry := ScanState.initial)
      (by simp [ScanState.initial]) hrun
  have hcount : count = image.events.length := by
    simpa [ScanState.initial] using hexitIndex.symm.trans hexitEnd
  subst count
  simpa [ScanState.initial, ScanState.toFixedState, U128.zero, U128.toNat,
    TGComputeContracts.Sqrt218.FixedState.zero] using hkernel

/-- Success of the checked arithmetic stage supplies both its validated
header and the exact generic event-fold equation for its returned state.

The endpoint `anchorSlack` computation remains orthogonal to this theorem;
its successful evaluation is retained by `runArithmetic`, but the separate
anchor-to-`anchorOK` refinement is not claimed here. -/
theorem runArithmetic_eventFold_refines
    {image : ArchiveImage} {result : ArithmeticResult}
    (hrun : runArithmetic image = .ok result) :
    headerCheck image = true ∧
      TGComputeContracts.Sqrt218.runFixedEvents
          image.events.length
          (kernelEventAt image)
          (kernelLogLowerAt image)
          (kernelLogUpperAt image)
          0 image.events.length
          TGComputeContracts.Sqrt218.FixedState.zero =
        some result.state.toFixedState := by
  unfold runArithmetic at hrun
  by_cases hheader : headerCheck image = true
  · simp only [hheader] at hrun
    rcases exceptBind_ok hrun with ⟨state, hevents, hrun⟩
    rcases exceptBind_ok hrun with ⟨slack, _hslack, hresult⟩
    change Except.ok ⟨state, slack⟩ = Except.ok result at hresult
    have hresult' : ArithmeticResult.mk state slack = result :=
      Except.ok.inj hresult
    cases hresult'
    exact ⟨hheader, runEvents_refines_kernel hheader hevents⟩
  · have hheaderFalse : headerCheck image = false :=
      Bool.eq_false_of_not_eq_true hheader
    simp only [hheaderFalse] at hrun
    contradiction

/-- A successful arithmetic run supplies both exact numerical obligations
used by the generic kernel: the complete event fold and terminal anchor
guard.  The proof is data-independent and does not inspect a closed
certificate. -/
theorem runArithmetic_refines_kernel
    {image : ArchiveImage} {result : ArithmeticResult}
    (hrun : runArithmetic image = .ok result) :
    headerCheck image = true ∧
      TGComputeContracts.Sqrt218.runFixedEvents
          image.events.length
          (kernelEventAt image)
          (kernelLogLowerAt image)
          (kernelLogUpperAt image)
          0 image.events.length
          TGComputeContracts.Sqrt218.FixedState.zero =
        some result.state.toFixedState ∧
      TGComputeContracts.Sqrt218.anchorOK
          image.header.bound
          result.state.weightedUpper.toNat
          result.state.psiLower.toNat = true := by
  have hevents := runArithmetic_eventFold_refines hrun
  exact ⟨hevents.1, hevents.2, runArithmetic_anchorOK hrun⟩

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
