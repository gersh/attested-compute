# Fixed decision checker boundary

[`FixedDecisionChecker.lean`](../../SparkInterval/Execution/FixedDecisionChecker.lean)
defines an application-neutral `NativeCheckerSemantics` for one decidable
Lean proposition. Acceptance is exactly the conjunction

```text
resultBytes = fixedSuccessResult ∧ decide FixedClaim = true.
```

The input bytes are not interpreted by this final adapter. Their complete
meaning belongs in the separately proved executable-to-checker refinement.
The checker-to-mathematics step is ordinary decidable reflection:
`of_decide_eq_true`.

The compact end-to-end theorem takes two substantive premises:

1. a `CompactInputReceiptExecutionFact` retaining the exact reviewed
   executable and fixed result while hiding the large input and machine
   trace; and
2. an `ArchitectureRefinesNativeChecker` theorem for that exact executable,
   entry point, formal architecture, and fixed checker.

The receipt contains no proposition field. `FixedClaim` is captured by the
Lean checker definition and cannot be decoded from, or selected by, the
receipt's input or output. The module introduces no axiom.

## Safe production use requires a closed adapter

The definitions are deliberately generic so applications can reuse them, but
a generic instantiation is not a production trust boundary. A safe downstream
adapter must fix all of the following as reviewed declarations:

- the proposition and its intended decision procedure;
- checker identifier and success-result bytes;
- measurement scheme and formal CPU or GPU semantics;
- compact run pins, retained executable, and entry point;
- the exact architecture-to-checker refinement theorem; and
- the sole closed receipt authority allowed to supply the execution fact.

Do not create a trusted importer quantified over the proposition, checker,
machine, pins, or refinement theorem. Such an importer would let the caller
choose the meaning of an attested run. Likewise, do not expose a theorem whose
receipt payload contains an encoded proposition. Only a closed downstream
adapter can show that a particular reviewed physical invocation implements a
particular fixed Lean decision.

The bridge does not make native computation magically trustworthy. The hard
ordinary proof remains `ArchitectureRefinesNativeChecker`: it must connect
the exact loaded executable and its architecture execution to the fixed
result and to the Lean decision procedure. Attestation supplies execution of
the reviewed machine image; it does not supply this semantic refinement.
