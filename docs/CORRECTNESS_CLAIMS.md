# Correctness claims

Mathematical evidence and execution provenance are independent axes.

| Mathematical evidence | Current status | Meaning |
| --- | --- | --- |
| Lean real/binary64 interval proofs | Implemented | Lean proves the abstract directed-rounding enclosure/extremality results, add/subtract/multiply/divide containment, and enclosure for the exact pure add/subtract/multiply typed-PTX instruction fragments emitted by the Phase 5 generator. |
| Exact-reference comparison | Implemented | Every tested CUDA and generated-PTX output bit/status matched exact rational Python recomputation. This is testing evidence, not a refinement theorem. |
| Full or compressed Lean result certificate | Not implemented | Lean would check the serialized witness that implies an application theorem. |

| Execution evidence | Current status | Meaning |
| --- | --- | --- |
| `local_unattested` | Implemented on DGX Spark | Reproducibility/integrity record only; forgeable by the host. |
| Detached operator signature over `local_unattested` | Implemented on DGX Spark | A pinned Ed25519 operator key signed the exact artifact-verified record. This is operator provenance, not hardware evidence or proof the record is true. |
| `mock_attested` | Test-only | Exercises protocol rejection; never production evidence. |
| `hardware_attested` | No accepted instance | Intended H100 provenance, accepted only through pinned production policy and the explicit execution axiom. |

The current Lean results cover exact real intervals and formal binary64
directed interval operations. They also cover execution of the generator's
pure arithmetic instruction arrays on a canonical fresh-register layout. They
do not yet cover PTX control flow, memory, threads, text emission, or a whole
kernel. The DGX Spark primitive acceptance run compared
5,000,000 randomized operations with zero mismatches.  The expression run
compared 1,000,000 randomized expression/input cases across 256 programs plus
3,504 curated cases, with zero mismatches and a byte-identical replay.  Expected
division-by-zero and nonfinite-intermediate rows carried explicit nonzero
statuses; a passing conformance report does not mean every row is usable by an
application.

The Phase 5 polynomial vertical slice additionally ran 100,000 rows from one
fixed nontrivial polynomial plus nine signed-zero multiplication cases. It
matched exact Python and the Phase 4 CUDA payload, and passed deterministic
PTX/cubin/output replay and specialized PTX/cubin-SASS audits. The executed
module was the exact offline cubin bound to those audits, and the closure
independently recomputed the exact comparison. This is not coverage of the
full expression language.

The Python package called a `reference_certificate` is recomputed by Python,
not Lean.  There is not yet a Lean theorem relating the canonical wire
expression, Python evaluator, CUDA interpreter, or output status format to
Lean's `Expr`/`FPInterval` semantics. Likewise, there is no proof that the Lean
PTX parser/generator or generated kernel refines those semantics. PTX and SASS
audits are lexical and do not prove compiler or hardware behavior. Those
boundaries must remain in any statement of the result.

An operator-signed DGX record can establish `AlgorithmReturned` only by
deliberately importing the separate `dgx_operator_signed_run_sound` axiom. The
signature verifier itself continues to report `hardware_evidence: false`; the
axiom represents trust in the operator's assertion that the signed record is
truthful.

An accepted H100 certificate would establish only the provenance proposition
`AlgorithmReturned` through the named axiom.  Algorithm soundness is separate,
and an additional proved bridge must identify and decode the result before an
application theorem follows.  No genuine H100 result currently satisfies the
axiom's premise.

## Riemann zeta scope

The repository now contains a rigorous tutorial-scale real-value calculation.
For a recorded integer `s > 1`, the GPU computes interval enclosures for the
first `N` terms of `sum 1/n^s`; the independent Python checker recomputes every
raw row and outward reduction, and a documented integral-test remainder
encloses the infinite tail. The retained `s = 2`, `N = 4096` run yielded real
binary64 endpoints `3ffa51a65a53d51c` and `3ffa51a66a52e51f` with zero row
mismatches and byte-identical replay.

That result is not yet checked by a Lean wire decoder/refinement theorem, and
this repository is not a verifier for the Riemann hypothesis or for zeros of
the Riemann zeta function up to a stated height. A usable zero application
must additionally supply and prove:

- complex interval arithmetic and rigorous argument reduction;
- certified logarithmic, trigonometric, and other required analytic bounds;
- a proved high-height zeta evaluation and zero-isolation algorithm, including
  adaptive precision and exceptional-case rules;
- a complete zero count/coverage argument, for example a rigorously
  instantiated Turing-method layer;
- an application certificate binding exact height coverage, parameters,
  results, failure statuses, and the final theorem.

A run certificate without those theorems establishes provenance only.  Only
after all components exist may a result claim that the required zeros or
points up to a particular bound were verified.
