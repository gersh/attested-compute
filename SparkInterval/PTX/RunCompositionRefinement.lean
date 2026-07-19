import SparkInterval.PTX.RunControlRefinement

/-!
# Whole-module run composition

This module packages the common proof pattern for chaining an exact
whole-machine stepping prefix with a successful fuel-bounded continuation.
Its structured-code specialization combines that generic rule with the exact
fallthrough bridge for compatible module-body slices.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-! ## Exact-prefix composition -/

/-- A successful exact-step prefix followed by a successful `run`
continuation is a successful `run` from the original state with the sum of
the two fuel counts. -/
theorem stepN_prefix_run_compose
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (prefixFuel continuationFuel : Nat)
    (initial middle final : MachineState)
    (hprefix : stepN module parameters thread prefixFuel initial = some middle)
    (hcontinuation : run module parameters thread continuationFuel middle =
      some final) :
    run module parameters thread (prefixFuel + continuationFuel) initial =
      some final := by
  rcases (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
      continuationFuel middle final).mp hcontinuation with
    ⟨hcontinuationSteps, hfinalReturned⟩
  apply (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
    (prefixFuel + continuationFuel) initial final).2
  constructor
  · rw [stepN_add, hprefix]
    exact hcontinuationSteps
  · exact hfinalReturned

/-- Monotone-fuel form of `stepN_prefix_run_compose`: once the composed run
succeeds, any total fuel bound at least as large returns the same final
state. -/
theorem stepN_prefix_run_compose_mono
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (prefixFuel continuationFuel largerFuel : Nat)
    (initial middle final : MachineState)
    (hprefix : stepN module parameters thread prefixFuel initial = some middle)
    (hcontinuation : run module parameters thread continuationFuel middle =
      some final)
    (hle : prefixFuel + continuationFuel ≤ largerFuel) :
    run module parameters thread largerFuel initial = some final := by
  exact run_mono_of_eq_some module parameters thread initial final hle
    (stepN_prefix_run_compose module parameters thread prefixFuel
      continuationFuel initial middle final hprefix hcontinuation)

/-! ## Structured fallthrough composition -/

/-- Execute a compatible structured module-body slice to fallthrough, then
continue with `run`.  The exact fallthrough bridge accounts for precisely
`code.length` whole-machine steps, so the composed fuel is explicit. -/
theorem executeCode_fallthrough_run_compose_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (continuationFuel : Nat)
    (initial middle final : MachineState)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := middle })
    (hcontinuation : run module parameters thread continuationFuel middle =
      some final) :
    run module parameters thread (code.length + continuationFuel) initial =
      some final := by
  apply stepN_prefix_run_compose module parameters thread code.length
    continuationFuel initial middle final
  · exact executeCode_fallthrough_stepN_of_runStepCompatible_segment module
      parameters thread code initial middle hopcodes hsegment hnotReturned
      hexecute
  · exact hcontinuation

/-- Monotone-total-fuel specialization for a compatible structured
fallthrough prefix followed by a successful continuation. -/
theorem executeCode_fallthrough_run_compose_mono_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (continuationFuel largerFuel : Nat)
    (initial middle final : MachineState)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := middle })
    (hcontinuation : run module parameters thread continuationFuel middle =
      some final)
    (hle : code.length + continuationFuel ≤ largerFuel) :
    run module parameters thread largerFuel initial = some final := by
  apply stepN_prefix_run_compose_mono module parameters thread code.length
    continuationFuel largerFuel initial middle final
  · exact executeCode_fallthrough_stepN_of_runStepCompatible_segment module
      parameters thread code initial middle hopcodes hsegment hnotReturned
      hexecute
  · exact hcontinuation
  · exact hle

end SparkInterval.PTX
