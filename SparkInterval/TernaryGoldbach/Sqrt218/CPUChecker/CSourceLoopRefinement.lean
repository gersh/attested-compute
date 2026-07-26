/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CStepRefinement

/-!
# Successful C-source loop refinement for the Sqrt218 checker

This module lifts the source-level theorem for `tg_sq218_scan_step_v2`
through the successful path of `tg_sq218_scan_all_events_v2`.

`CScanTrace` is a data-independent relational model of the C `while` loop.
Each transition records exactly the two decoded accessor results, their
fixed-width facts, and the accepted source step.  Keeping those facts on the
transition where they are used avoids an impossible global hypothesis over
arbitrary, unreachable scan states.

The complete-trace theorem proves the exact generic fixed-event fold.  It
does not open or reduce a production archive.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-- Successful transitions of the source `while` loop.

The trace count is the number of calls to `tg_sq218_scan_step_v2`.  A
transition can only be constructed with the decoded records and word facts
for that particular reachable state. -/
inductive CScanTrace (image : ArchiveImage) :
    Nat → ScanState → ScanState → Prop
  | nil (state : ScanState) :
      CScanTrace image 0 state state
  | cons
      {count : Nat} {entry next exit : ScanState}
      {event : EventRecord} {prime : PrimeRecord}
      (records : DecodedStepRecords image entry event prime)
      (words : CStepWordFacts image entry event prime)
      (accepted :
        cAcceptedScanStep image entry event prime = some next)
      (tail : CScanTrace image count next exit) :
      CScanTrace image (count + 1) entry exit

/-- A successful C-source trace advances the event cursor exactly once per
transition.  In particular, every unchecked C increment in the trace is
proved not to wrap. -/
theorem CScanTrace.nextEvent
    {image : ArchiveImage} {count : Nat} {entry exit : ScanState}
    (trace : CScanTrace image count entry exit) :
    exit.nextEvent = entry.nextEvent + count := by
  induction trace with
  | nil state =>
      simp
  | @cons count entry next exit event prime
      records words accepted tail ih =>
      have hstep :
          next.nextEvent = entry.nextEvent + 1 :=
        cAcceptedScanStep_nextEvent words.eventCount accepted
      omega

/-- Every successful C-source trace computes the same fixed-point state as
the corresponding segment of the generic kernel.

The `headerCheck` premise identifies the decoded scale words with the kernel
constants.  Record bounds come from each trace edge, so the bounded kernel
step and the C loop take exactly the same branch. -/
theorem CScanTrace.refines_fixedEvents
    {image : ArchiveImage} {count : Nat} {entry exit : ScanState}
    (hheader : headerCheck image = true)
    (trace : CScanTrace image count entry exit) :
    TGComputeContracts.Sqrt218.runFixedEvents
        image.events.length
        (kernelEventAt image)
        (kernelLogLowerAt image)
        (kernelLogUpperAt image)
        entry.nextEvent count entry.toFixedState =
      some exit.toFixedState := by
  induction trace with
  | nil state =>
      rfl
  | @cons count entry next exit event prime
      records words accepted tail ih =>
      have hentryLt : entry.nextEvent < image.events.length :=
        (List.getElem?_eq_some_iff.mp records.eventAt).1
      have hstep :
          TGComputeContracts.Sqrt218.fixedEventStep
              (kernelEventAt image)
              (kernelLogLowerAt image)
              (kernelLogUpperAt image)
              entry.nextEvent entry.toFixedState =
            some next.toFixedState :=
        cAcceptedScanStep_refines_fixedEventStep
          hheader records words accepted
      have hprogress :
          next.nextEvent = entry.nextEvent + 1 :=
        cAcceptedScanStep_nextEvent words.eventCount accepted
      simp only [TGComputeContracts.Sqrt218.runFixedEvents,
        TGComputeContracts.Sqrt218.runOptionalSteps,
        TGComputeContracts.Sqrt218.boundedFixedEventStep,
        if_pos hentryLt, hstep]
      simpa only [TGComputeContracts.Sqrt218.runFixedEvents,
        hprogress] using ih

/-- A complete successful C scan from the source initial state refines the
entire generic fixed-event fold.

`hcomplete` is the literal successful loop-exit condition
`state.next_event == header.event_count`.  Together with exact no-wrap
progress, it proves that the trace length is exactly the decoded event
count, not merely at most that count. -/
theorem CScanTrace.complete_refines_fixedEvents
    {image : ArchiveImage} {count : Nat} {exit : ScanState}
    (hheader : headerCheck image = true)
    (trace :
      CScanTrace image count ScanState.initial exit)
    (hcomplete :
      exit.nextEvent = image.header.eventCount) :
    TGComputeContracts.Sqrt218.runFixedEvents
        image.events.length
        (kernelEventAt image)
        (kernelLogLowerAt image)
        (kernelLogUpperAt image)
        0 image.events.length
        TGComputeContracts.Sqrt218.FixedState.zero =
      some exit.toFixedState := by
  have hheaderFacts := headerCheck_sound hheader
  have hprogress := trace.nextEvent
  have hcount : count = image.events.length := by
    simpa only [ScanState.initial, Nat.zero_add,
      hheaderFacts.eventCount] using hprogress.symm.trans hcomplete
  have hrefines := trace.refines_fixedEvents hheader
  subst count
  simpa only [ScanState.initial, ScanState.toFixedState,
    U128.zero, U128.toNat, Nat.zero_mul, Nat.zero_add,
    TGComputeContracts.Sqrt218.FixedState.zero] using hrefines

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement
