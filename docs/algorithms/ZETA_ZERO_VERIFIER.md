# High-bound Riemann-zeta zero verifier

This document describes the intended high-bound verifier and the Lean
foundations already in the repository. It is a design and status document, not
an announcement that zeros have been verified to any positive height.

The current implementation proves the finite-counting deductions and their
complete finite-height composition theorem, including a canonical signed full-
payload parser/checker and a multiplicity-aware count handoff. It does **not**
yet define a concrete Hardy Z, evaluate the Riemann-Siegel formula, certify
transcendental functions, or prove a Turing or argument-principle count.
Consequently, no current Boolean checker constructs all analytic premises
needed by the final zeta theorem.

The existing [real-integer zeta tutorial](REAL_ZETA_POC.md) is a separate
calculation of positive real values `zeta(s)` for integer `s > 1`. It is not a
component of the critical-strip verifier described here.

## Exact target

For a real height `T`, Lean defines the closed rectangle

```text
R(T) = {s : C | 0 <= re(s) <= 1 and -T <= im(s) <= T}.
```

In the code this is `SparkInterval.Zeta.criticalRectangle T`. The exact target
theorem is:

```lean
theorem all_zeros_to_height_on_criticalLine
    {height : ℝ}
    (hcount :
      (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zetaZerosIn (criticalRectangle height)).ncard) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2
```

Thus the final mathematical obligation is precise: prove that the number of
distinct zeta zeros in `R(T)` equals the number of those zeros on
`re(s) = 1/2`. Once that equality is available, the displayed conclusion is an
ordinary axiom-free Lean theorem.

This is a finite-height, closed-critical-strip statement. It is not by itself
Mathlib's global `RiemannHypothesis`, and it does not prove that every
nontrivial zero lies in the critical strip. A global theorem additionally needs
the usual zero-localization and symmetry results and a way to range over all
heights.

## What is proved now

### Ordered zero brackets and the count handoff

[`ZeroCertificate.lean`](../../SparkInterval/Zeta/ZeroCertificate.lean) proves a
generic real-variable layer. It is not specific to zeta.

- A `Bracket` is a nondegenerate closed interval.
- A weak endpoint sign change plus continuity produces a zero in the bracket.
- A strict endpoint sign change puts that zero in the open bracket.
- `OrderedBrackets` requires a strict gap between every earlier and later
  bracket, so their closed carriers are pairwise disjoint.
- A continuous `ZeroCertificate` therefore supplies one distinct selected zero
  per bracket.
- `ZeroCountUpperBound f domain count` supplies finiteness and the matching
  upper bound on the number of distinct zeros.
- `ZeroCertificate.complete_of_count_upperBound` combines the bracket lower
  bound and external upper bound into an exact count and proves that every zero
  in the domain belongs to one of the brackets.

These are proved topological and finite-set deductions. This base
`ZeroCertificate` layer itself contains Lean propositions; the later
`EndpointCertificate` and signed-payload sections provide Boolean endpoint and
arithmetic checks. The regression test here uses the polynomial
`(x + 2) * (x - 2)`, not Hardy Z.

### Critical rectangle and final finite-set deduction

[`CriticalLine.lean`](../../SparkInterval/Zeta/CriticalLine.lean) connects the
target to Mathlib's `riemannZeta`.

- `criticalRectangle T` is `[0, 1] x [-T, T]` in complex real/imaginary
  coordinates and is proved compact.
- Mathlib's discreteness theorem implies that the zeta zeros in every such
  rectangle form a finite set.
- Critical-line zeros are a subset of all zeros in the rectangle.
- Equal finite set cardinalities imply equality of the two sets.
- `all_zeros_to_height_on_criticalLine` gives the pointwise finite-height
  conclusion shown above.

The count is `Set.ncard`, so it counts distinct complex points, not analytic
multiplicity. The multiplicity bridge below now proves the safe inequality
needed to consume a conventional analytic count; no executable theorem yet
constructs that analytic count from numerical zeta data.

### Multiplicity-aware total-count bridge

[`MultiplicityCount.lean`](../../SparkInterval/Zeta/MultiplicityCount.lean)
uses Mathlib's `analyticOrderAt riemannZeta z : ℕ∞`. It proves that every zeta
zero contributes at least one and therefore

```text
(distinct zeros in R(T)).ncard
    <= sum(z in zeros in R(T), analyticOrderAt riemannZeta z).
```

No simplicity assumption is required, and keeping the sum in `ℕ∞` avoids
silently truncating an infinite analytic order. A
`ZetaMultiplicityCountUpperBound T n` then yields the existing
`ZetaZeroCountUpperBound T n` contract. The small
`ZetaMultiplicityCountCertificate.check` checks only the final natural-number
inequality between a claimed analytic count and the bracket-bound requested by
the verifier.

The difficult analytic premise remains explicit:
`ZetaMultiplicityCountUpperBound` must still be constructed by a rigorous
Turing, Riemann--von Mangoldt, or argument-principle proof with the required
height, multiplicity, and contour-boundary conventions. The Boolean arithmetic
wrapper does not prove that premise.

[`SymmetricCount.lean`](../../SparkInterval/Zeta/SymmetricCount.lean) now makes
the conventional positive-ordinate handoff precise. Unconditionally, the
closed symmetric rectangle's multiplicity count partitions into its positive,
negative, and real-axis contributions. Turning a bound for
`0 < im(z) <= T` into the symmetric `[-T,T]` bound then requires two explicit
analytic premises:

- `ZetaConjugationMultiplicitySymmetry`, asserting that conjugation preserves
  both zeta zeros and their analytic orders; and
- `NoRealAxisZetaZeros T`, excluding a boundary contribution at `im(z) = 0`.

Given those premises, Lean proves that the symmetric count is twice the
positive count and that `PositiveZetaMultiplicityCountUpperBound T n` supplies
both `ZetaMultiplicityCountUpperBound T (2*n)` and the verifier's distinct-zero
upper bound. The finite-set partition and doubling deductions are proved; this
repository does not currently derive the conjugation/multiplicity or
no-real-axis premises from Mathlib's zeta API.

### Exact verifier composition

[`Verifier.lean`](../../SparkInterval/Zeta/Verifier.lean) proves the complete
application-level wiring theorem. `CriticalLineZeroBridge f T` states that the
zeros of a real evaluator `f` on `[-T,T]` agree with Mathlib's zeta zeros at
`1/2 + i t`. `ZetaZeroCountUpperBound T n` states that the total number of zeta
zeros in the rectangle is at most `n`.

`ZetaVerifierEvidence` then combines those two analytic inputs with `n`
ordered sign-change brackets. Lean proves:

```lean
ZetaVerifierEvidence.all_zeros_on_criticalLine
```

The proof maps real roots injectively to the critical line, transfers compact
finiteness back through that map, obtains the bracket lower bound, collapses it
against the total upper bound, and invokes the exact finite-height target. No
zeta-specific axiom is introduced.

[`ChunkCertificate.lean`](../../SparkInterval/Zeta/ChunkCertificate.lean) and
`ChunkedZetaVerifierEvidence` provide the high-bound form. Brackets are grouped
under ordered contiguous spans; Lean proves cross-chunk disjointness and that
the global lower bound is the sum of all local counts. A matching total upper
bound again yields the final zeta theorem. This is logical chunk composition,
not yet a serialized constant-memory implementation.

[`EndpointCertificate.lean`](../../SparkInterval/Zeta/EndpointCertificate.lean)
adds the first executable certificate check. A rational bracket records exact
rational endpoints and rational enclosures of the evaluator at both endpoints.
The kernel-reducible Boolean checker validates each bracket and compares only
consecutive brackets: for `n` entries it performs `n - 1` adjacent-order
comparisons rather than an all-pairs separation scan. The proved
`isValid_iff_checkCondition` theorem lifts those adjacent inequalities, using
local nondegeneracy and transitivity, to the all-pairs ordering required by
`ZeroCertificate`. It rejects decreasing endpoints, malformed enclosures,
zero-containing results, equal signs, and overlapping or misordered families.
Given evaluator-specific enclosure theorems, its soundness theorem constructs
the ordered certificate. Thus sign and ordering decisions require neither
`native_decide` nor trusted floating-point comparisons. This is linear in the
number of bracket comparisons, although exact-rational operand sizes still
govern individual comparison cost and the current family is held in memory.

[`TouchingEndpointCertificate.lean`](../../SparkInterval/Zeta/TouchingEndpointCertificate.lean)
provides the source-shaped variant needed by the Platt--Trudgian scan. Its
linear exact-rational checker accepts `upper <= next.lower`, but continues to
require strict nonzero endpoint signs. Continuity therefore places every
selected root in an open bracket. Lean proves those open brackets contain
distinct roots even when two closed brackets share an endpoint, and carries
the result through the same exact-count and completeness argument. This does
not assume simple zeta zeros: a resolved stationary cell may contribute two
touching strict brackets. The remaining PT21 integration work is to decode
the signed source sign/enclosure packet into this typed family and establish
its Hardy-Z endpoint realization.

The monolithic signed bridge below parses one canonical full certificate.
`StreamingChunkVerifier.lean` additionally proves a resumable exact-rational
chunk transition, cross-chunk ordering/contiguity, summed counts, conversion to
`ChunkCertificate`, and the final conditional finite-height theorem. Its inputs
are still theorem-level lists; a production byte parser, rolling digest, and
resource-bounded I/O checker are missing.

[`HardyZContract.lean`](../../SparkInterval/Zeta/HardyZContract.lean) isolates
the analytic evaluator contract: a continuous real function represented as a
nonzero complex phase times `riemannZeta (1/2 + i t)`. Lean proves that any
implementation satisfying this contract supplies the exact critical-line
zero bridge used above. The file does not assume that the current code
satisfies the contract. `HardyZModel.verifyEndpointFamily` is the current
composition edge: a successful endpoint-family check, proved evaluator
enclosures, bracket-domain bounds, and a matching total-zero-count upper bound
yield the finite-height zeta conclusion. The theorem does not construct the
Hardy-Z model, prove the endpoint enclosures, or supply the total count; those
remain the explicit analytic obligations.

### Formal generated-PTX identity

[`FormalPTXProgram.lean`](../../SparkInterval/Execution/FormalPTXProgram.lean)
closes the formal-AST-to-emitted-PTX identity edge for the existing typed
generator.

`FormalPTXProgram.statementCheck`:

1. parses the exact canonical input text and requires it to equal the selected
   `ReferenceBatch`, including rows and `rowCount`;
2. builds the typed module from that batch, then validates and deterministically
   emits it for the selected target;
3. recomputes SHA-256 over the emitted PTX and over the exact canonical input,
   parameter, and domain texts;
4. compares those digests and the algorithm ID with the run statement; and
5. requires exact equality of the target, target-profile hash, and the complete
   caller-selected artifact-hash record (source tree, host executable, device
   cubin, and kernel manifest).

`statementCheck_sound` exposes those equalities, and
`outcomeCheckForFormalPTX_sound` composes them with the exact returned-result
binding and the single external-run trust axiom. This identifies the formal
module, emitted PTX bytes, canonical run inputs, and deployment identities
named by a particular accepted statement. Canonical parameter and domain text
are hash-bound literally here; application-specific interpretation of those
texts remains a separate parser/specification obligation.

For this formal path, `RunStatement.algorithmHash` is the digest of the emitted
PTX text. The measured cubin has a separate
`RunStatement.artifacts.deviceCubinHash`; an importer must not substitute one
digest for the other.

Equality with `RunStatement.artifacts` binds the *claimed* cubin and deployment
hashes; it does not prove that the named cubin was compiled from the emitted
PTX. Nor does it prove that `ptxas`, SASS, the CUDA driver, or an H100 implements
the typed PTX machine. The current typed source language is also still the
polynomial interval language; it is not a Riemann-Siegel or Hardy-Z program.

### Closed registered execution semantics

The preferred way for an accepted certificate to carry formal execution
meaning is the closed registry in
[`RegisteredAlgorithm.lean`](../../SparkInterval/Execution/RegisteredAlgorithm.lean).
A `RegisteredInvocation` fixes the algorithm constructor and canonical input;
`statementCheck` binds its library-defined algorithm ID, definition digest,
input digest, parameter digest, and domain digest. The sole run-certificate
axiom returns both the historical bytes and a fail-closed registered projection.
`accepted_registered_run_sound` is a proved projection that yields the
invocation's fixed `Runs` relation, not another axiom.

The current invocations are unrelated to zeta: the CPU tutorial
`cubicSumDivThree20000V1` and the one-row
`h100FormalPtxConstantOneV1` `sm_90` deployment pilot. The cubic `Runs`
relation uses an executable integer cube
accumulator followed by one division; separate axiom-free theorems prove the
exact output `13334666700000000`, rational-specification agreement, and u64
no-overflow for every loop step without `native_decide`. Those model-level
proofs do not establish GPU opcode execution. The H100 pilot only fixes a
constant `[1,1]` batch, links its PTX source to the formal emitter, and checks
the exact compact result shape. There is no registered Hardy-Z,
endpoint, streaming, or total-count checker, so this mechanism does not advance
the current zeta height by itself.

### Signed endpoint payload and final conditional theorem

[`SignedZetaEndpointPayload.lean`](../../SparkInterval/Execution/SignedZetaEndpointPayload.lean)
connects the exact returned string to typed endpoint data. Its pure
`payloadCheck` requires all of the following:

1. canonical parsing of the entire returned full-certificate string and exact
   equality with the supplied typed `FullCertificate`;
2. `FullCertificate.check = true`, which independently evaluates and checks
   every arithmetic row under the format's resource limits;
3. exactly two rows and two results per bracket, one variable per row, a
   singleton finite binary64 endpoint in each row, and a finite rational output
   interval for each endpoint; and
4. the exact-rational family checker, including strict signs and linear
   adjacent ordering.

`SignedZetaEndpointPayload.check` conjoins those pure checks with
`outcomeCheckForFormalPTX` and requires the embedded batch digest to equal both
the accepted statement input digest and the exact formal program input digest.
Its soundness result keeps the fields separate:
`ProducedOutcome` uses `accepted_run_certificate_sound`; formal PTX identity,
returned-text binding, canonical parsing, arithmetic, shape, and endpoint-
family validity come from ordinary Lean checks. This generic full-payload path
does not use the registered projection. A separate exact PT21 finite-RH
invocation is now in the closed registry and requires its chunked
`SourceEvidence` directly. `statementResult_parses` proves that the exact result named in the
accepted statement parses to the typed full certificate.

Full-certificate arithmetic now supplies more than sign data.
`CheckedPayload.enclosesEndpoints` applies `FullCertificate.check_sound` to
derive every `EnclosesEndpoints f` fact from the weaker
`EndpointRowsRealize f` premise. That premise says the checked certificate
expression realizes the selected evaluator value at each singleton endpoint
row. Thus the interval enclosures are derived from checked rows; the remaining
application obligation is the row-realization theorem connecting that
expression to Hardy Z. Neither signature/attestation nor parsing invents this
semantic connection. The lower-level `check_exists_zeroCertificate` and
`verifyFiniteHeight` entry points remain available when callers already have
endpoint enclosures directly.

[`SignedZetaVerifier.lean`](../../SparkInterval/Execution/SignedZetaVerifier.lean)
provides the final conditional composition. `verifyFiniteHeight` takes:

- a successful signed/formal-PTX/payload check;
- a proved `HardyZModel f T`;
- endpoint enclosure and bracket-domain proofs; and
- a `ZetaMultiplicityCountUpperBound T count`.

It returns `CertifiedZetaVerification`, pairing the accepted run outcome
with the theorem that every zeta zero in `R(T)` lies on the critical line. Only
`ProducedOutcome` crosses the sole project axiom; the mathematical field is
derived independently from the pure payload facts and the explicit analytic premises. The
`verifyFiniteHeightWithCountCertificate` variant also checks the final numeric
comparison, but still takes the analytic multiplicity upper bound explicitly.
`verifyFiniteHeightFromCheckedRows` instead takes `EndpointRowsRealize f` and
derives endpoint enclosures from full-certificate arithmetic soundness.

`verifyFiniteHeightFromPositiveCount` is the conventional positive-ordinate
entry point. It takes a payload with `2*n` brackets, a positive multiplicity
upper bound `n`, explicit conjugation/multiplicity symmetry, and the
no-real-axis-zero premise, then uses the proved doubling handoff. None of these
theorems supplies the concrete row-realization/Hardy-Z/Riemann-Siegel proof,
the positive Turing/argument-principle bound, the zeta
conjugation/multiplicity contract, or the no-real-axis theorem, so no positive
height is certified today.

`verifyFiniteHeightFromPositiveRows` is the smaller high-bound endpoint route.
When the concrete real evaluator is proved even, Lean reflects the checked
positive brackets in reverse order, swaps their endpoint enclosures, and
constructs the symmetric `2*n` family. The payload therefore needs two rows per
positive bracket rather than positive and negative copies. Evenness,
conjugation/multiplicity symmetry, and absence of real-axis zeros are still
explicit analytic premises.

[`CompactAttestedVerifier.lean`](../../SparkInterval/Execution/CompactAttestedVerifier.lean)
formalizes two small-download server architectures. The legacy generic
FormalPTX theorem `certifyCompactFiniteHeightZeta` still requires two explicit
proofs: accepted physical execution refines caller-supplied checker semantics,
and those semantics imply the finite-height claim.

The preferred `certifyRegisteredCompactFiniteHeightZeta` instead accepts a
closed `RegisteredInvocation`. Its `Runs` relation is fixed by the library and
the sole axiom supplies that relation for the accepted run, so there is no
separate `ExecutionRefines` premise. A full `verifierSound` theorem must still
derive the zeta claim from `Runs`. The exact PT21 invocation and its ordinary
source-claim theorem now instantiate this pattern through a dedicated signed
wrapper, but no external artifacts yet construct the required endpoint,
Hardy-Z and count evidence. It remains a conditional interface rather than a
completed compact verifier.

### `sm_90` emitter path

[`Emitter.lean`](../../SparkInterval/PTX/Emitter.lean) now parameterizes the PTX
target. `EmitterTarget.sm90` renders `.target sm_90`, while `sm121` retains the
DGX Spark path. `emitFor_success` proves that any successful target-parameterized
emission is exactly the deterministic rendering of the validated typed module.
`FormalPTXProgram` maps `nvidiaH100SM90` to this `sm90` path.

This is an H100-targeted PTX **emitter**, not a proved H100 backend. The existing
pinned-NVIDIA partial refinement proves finite directed `add/sub/mul` and
non-NaN `min/max` behavior in the typed model. It has no typed division opcode,
no transcendental opcodes, and no PTX-to-cubin or hardware refinement theorem.
The operational measured H100 pilot covers one closed constant `[1,1]` batch
on this generated-module path. It does not yet cover the zeta verifier or turn
the PTX-to-cubin and physical-hardware steps into refinement theorems.

### Binary power schedule

[`PowSchedule.lean`](../../SparkInterval/PTX/PowSchedule.lean) defines a
left-to-right binary exponentiation schedule and proves:

```lean
runPowValues base (powSchedule n) 1 = base ^ n
```

For example, exponent 64 needs seven schedule multiplications rather than 64
repeated multiplications. The schedule uses only squaring and multiplication by
the base, so a future compiler can lower it through the already modeled
interval multiplication operation.

The schedule is not wired into the version-1 compiler. Outward-rounded interval
multiplication is not bitwise associative, so changing the schedule can change
the interval endpoints even though both schedules contain the same exact
power. Deployment therefore requires a versioned compiler/wire-format change
and new interval and whole-kernel refinement theorems.

### Complex rectangle arithmetic

[`ComplexInterval.lean`](../../SparkInterval/ComplexInterval.lean) now lifts
the proved real interval operations to complex rectangles. Point, negation,
addition, subtraction, multiplication, squaring, and natural powers all have
axiom-free exact-complex containment theorems. This validates the standard
four-real-multiply/two-add lowering for complex multiplication. It is a
mathematical lowering foundation; no multi-output PTX ABI, complex division,
or transcendental evaluator has yet been implemented.

### Reading the proof and trust graph

The repository's [LeanArchitect registry](../../SparkInterval/Blueprint.lean)
and [proof-map guide](../PROOF_BLUEPRINT.md) distinguish proved dependencies,
documented gaps, NVIDIA-source traceability, and the one execution trust axiom.
The high-bound graph must preserve two separate branches:

```text
returned full payload -> canonical parse -> arithmetic/shape/family checks
                                                        |        [pure checks]
proved Hardy model + endpoint enclosures/domain bounds -+
                                                        |
analytic multiplicity upper bound -> distinct-count bound
                                                        |
                                                        v
                             finite-height zeta mathematics     [proved]

formal batch/run identity -> target PTX and statement bindings [pure checks]
accepted run certificate -> ProducedOutcome                     [one axiom]
                              | historical: exact returned bytes
                              | registered: fixed Runs, only after closed check
                                      \                         /
                                       v                       v
                            CertifiedZetaVerification pairs both fields
```

The current full-payload zeta branch does not use the registered projection to
prove the analytic arrows. The separate PT21 compact branch derives the source
claim from its fixed `Runs` relation through an ordinary Lean theorem, but its
successful relation still requires the endpoint/Hardy-Z/count evidence that no
current artifact materializes. The finite-set theorem does not prove that a
CPU or GPU ran. A Blueprint edge to a pinned NVIDIA clause is
reviewable source traceability, not a universal proof of `ptxas`, SASS, driver,
or physical-H100 refinement.

## Intended fast architecture

The high-bound path should be a deterministic, chunked pipeline rather than one
monolithic GPU launch or one giant Lean value.

### 1. Bind the computation

A canonical manifest fixes at least:

- the height interval and endpoint convention;
- the Hardy-Z, theta, and Riemann-Siegel formula versions;
- precision and adaptive-retry policy;
- sampling, bracket-refinement, and exceptional-case policy;
- the total-zero-count method and every explicit analytic constant;
- the formal PTX source batch or other formally identified executable;
- input, parameter, domain, output, target-profile, and artifact digests; and
- a verifier-provided nonce.

Changing any of these fields creates a different computation statement.

### 2. Evaluate independent blocks on the GPU

The primary H100 workload evaluates rigorous enclosures for Hardy Z at ordered
sample points. A fast first pass uses one uniform precision class and sends only
ambiguous intervals to higher-precision queues. Grouping retries by precision
avoids making every GPU warp follow the worst exceptional point.

Within a block, evaluation order and reductions must be fixed. The checker
must reproduce the same mathematical interval algorithm; a nondeterministic
floating reduction cannot be the definition of the certified result. The
binary power schedule is a foundation for reducing repeated-power cost, but it
does not supply the missing transcendental or Riemann-Siegel evaluator.

At ordinary Riemann-Siegel complexity, evaluating one point takes on the order
of `sqrt(t)` terms. More advanced amortized evaluation may eventually be useful,
but it requires its own formal approximation and error theorem and must not be
silently substituted for the versioned algorithm.

### 3. Produce disjoint critical-line brackets

For each unambiguous strict sign change, refine an interval until its endpoint
enclosures exclude zero with opposite signs. Emit brackets in strict order and
reject overlaps. Uncertain samples, near-coincident roots, endpoint roots, and
possible non-sign-changing roots go to an exceptional path; dropping them is
not allowed.

Once Hardy Z is connected to `riemannZeta (1/2 + t * I)`, the existing generic
bracket theorem gives a distinct critical-line zero for every accepted bracket.

### 4. Prove the total count independently

The bracket list supplies only a lower bound. A second proof supplies an upper
bound for all zeta zeros in the rectangle, including off-line zeros. The two
standard designs are:

- a formal Turing-method/Riemann-von-Mangoldt calculation with explicit error
  constants; or
- an argument-principle computation whose contour is proved zero-free and whose
  enclosed winding/logarithmic-derivative integral determines the integer count.

This stage should be block-oriented too. Its final output is a small exact count
and the checked evidence for every bound used to obtain it.

When that analytic result uses the conventional positive-ordinate count, its
formal handoff is `PositiveZetaMultiplicityCountUpperBound`. The current
doubling theorem additionally requires explicit
`ZetaConjugationMultiplicitySymmetry` and `NoRealAxisZetaZeros`; an imported
count cannot silently change conventions from `(0,T]` to `[-T,T]`.

### 5. Compose checked data and analytic evidence in Lean

The current end-to-end theorem is
`SignedZetaEndpointPayload.verifyFiniteHeightFromCheckedRows`. It combines a
checked canonical payload with an explicitly proved Hardy-Z model,
`EndpointRowsRealize`, domain bounds, and a multiplicity-count upper bound.
Full-certificate soundness derives the endpoint enclosures from the checked
rows. The conclusion pairs historical provenance with the finite-height zeta
theorem; it does not infer row realization or analytic soundness from
provenance.

A future production checker should replace the remaining analytic arguments
with sound executable certificate theorems. That replacement composes with the
same final finite-set deduction and needs no new execution axiom.
If the complete checker becomes a reviewed closed `RegisteredInvocation`,
`certifyRegisteredCompactFiniteHeightZeta` can consume its small decoded result
without a second `ExecutionRefines` premise. Its checker-soundness theorem must
still prove all analytic obligations from the fixed `Runs` relation.

## Missing mathematical and checker work

The following are required before the proposed checker can establish even one
nontrivial height.

| Missing layer | Required formal result |
| --- | --- |
| Hardy Z and theta | Define the functions, prove continuity and real-valuedness, and prove `Z(t) = 0` exactly when `riemannZeta (1/2 + t * I) = 0`. |
| Zeta symmetry and localization | Instantiate `ZetaConjugationMultiplicitySymmetry`, prove `NoRealAxisZetaZeros`, and justify that the closed symmetric rectangle/count convention covers the intended nontrivial zeros. The partition and conditional doubling theorems are already proved. |
| Riemann-Siegel evaluation | Prove the exact finite formula used by the implementation together with explicit, valid remainder bounds over every admitted height/precision domain. |
| Certified transcendentals | Sound complex interval implementations for at least argument reduction, `sin`, `cos`, `exp`, `log`, powers, and the Gamma/theta ingredients actually used. |
| Adaptive precision | Prove that retrying at higher precision preserves the same specification and that unresolved rows fail closed. |
| Endpoint evaluator realization | The canonical full-payload parser, arithmetic, shape, and family checks exist, and checked rows derive enclosures. A production path must prove `EndpointRowsRealize` for its Hardy-Z expression and discharge domain membership. |
| Analytic total zero count | Construct `PositiveZetaMultiplicityCountUpperBound` or the symmetric `ZetaMultiplicityCountUpperBound` from a fully explicit Turing or argument-principle theorem tied to executable interval evidence, including contour-boundary handling. |
| Compiler coverage | Add every arithmetic operation used by the selected formula to the typed compiler and prove expression, instruction, module, and emitted-code refinement. Directed division remains absent today. |
| Streaming byte integration | The logical previous-bracket transition is resumable across list chunks and proves global family validity. The separate PT21 checker now proves the source-permitted touching-bracket topology. A high-bound format still needs a byte parser, rolling digest, resource-bounded allocation/work and I/O, plus a refinement theorem from the signed source packet to the appropriate logical runner. |

Mathlib currently provides analytic `riemannZeta`, its functional equation,
trivial zeros, nonvanishing on `re(s) >= 1`, and discreteness/finiteness of its
zero set on compact regions. It does not currently provide the Hardy-Z,
Riemann-Siegel, Turing-method, Riemann-von-Mangoldt, or argument-principle
theorems needed above.

## Certificate size and streaming

A high-bound verifier must not reuse the current full-certificate format as one
giant in-memory object. That checker is intentionally non-streaming and caps a
certificate at 512 MiB, one million rows, 4,096 arithmetic-cost units per row,
and ten million total arithmetic-cost units. Those are useful safety limits for
the present format, not a scale target for zeta zeros.

The number of zeros through height `T` grows roughly like

```text
T / (2*pi) * log(T / (2*pi)) - T / (2*pi).
```

A certificate containing one explicit bracket per zero is therefore inherently
linear in that count. Avoiding operation traces greatly reduces the constant
factor, but it does not make the root list asymptotically small.

[`StreamingEndpointCertificate.lean`](../../SparkInterval/Zeta/StreamingEndpointCertificate.lean)
now proves the logical one-pass core. `EndpointStreamState` retains only the
previous bracket; each transition checks local validity and predecessor order.
`runEndpointChunk_append` proves that resuming across list chunks equals one
concatenated run, and `checkEndpointStream_isValid` upgrades successful
predecessor checks to the existing global all-pairs family validity. Thus the
resumable transition and its mathematical soundness are proved.

This theorem consumes already-decoded `List RationalBracket` chunks. The
remaining production integration should add:

- a small canonical top-level manifest;
- fixed-size data chunks containing ordered samples, endpoint enclosures,
  brackets, exceptional cases, and local count evidence;
- a domain-separated hash for every chunk and a manifest-bound hash tree or
  ordered hash chain;
- a runtime streaming state containing the current decoded record, preceding
  bracket, bounded analytic accumulators, counts, and hash frontier;
- deterministic per-chunk summaries and a proved associative composition rule;
  and
- explicit limits on chunk bytes, records, precision, expression work, retry
  count, and total declared work before allocation.

The missing byte parser, rolling digest, resource-bounded allocator/work
accounting, and file/network I/O loop must be proved to refine the logical
transition. Once implemented, a server can generate and check chunks while the
GPU continues with later blocks. Total transfer and checking work remain
linear in the evidence actually inspected.

A Merkle root by itself proves only integrity of later-opened chunks. It does
not prove their arithmetic or that unopened chunks contain every zero. A truly
small independently verifiable download would require either a substantially
more compressed analytic certificate or a sound succinct-proof system; neither
exists in this repository.

### Host foundation microbenchmark

The bounded development benchmark can be run with:

```bash
python3 tools/benchmark_zeta_foundations.py --pretty
```

It measures Python generation/validation of the binary power schedule and
Python streaming generation, decoding, exact-integer local validation, and
adjacent ordering of a **synthetic fixed-width** rational-bracket format. It
does not evaluate zeta, find or count zeros, elaborate or kernel-check Lean,
run a GPU, or parse the production full-certificate format.

Interpret its fields literally:

- `peak_memory_bytes` is peak Python allocation observed by `tracemalloc` for
  each timed phase, not process RSS, GPU memory, or stored-certificate size;
- `synthetic_certificate_bytes` is exact only for the benchmark's synthetic
  fixed-width encoding, not an estimate of the current or future production
  certificate; and
- throughput includes `tracemalloc` overhead and varies with the host and
  load.

The benchmark demonstrates bounded chunk retention and exercises the linear
adjacent comparison pattern. It is a host-side smoke benchmark, not an H100
capacity estimate or evidence that the high-bound verifier is complete.

### Server-only checking option

The large chunks may instead stay on the GPU server, with a measured CPU-side
checker streaming them and returning only the manifest, final counts, result,
and evidence root. This avoids a large download only if the verifier trusts
attestation for that exact checker, its inputs, completion, and output. It is a
different assurance mode from locally replaying the mathematical certificate.

The repository now has a source-reviewed CPU-TEE/H100 receipt importer and
closed CPU/H100 pilot invocations, but its admitted receipt registry is empty
and it has no closed registered zeta checker. The generic theorem
`certifyRegisteredCompactFiniteHeightZeta` shows how a small summary can be
used once such an invocation and its full `Runs`-to-zeta soundness theorem
exist; it does not provide either one. This mode must keep the extra CPU-TEE,
checker-runtime, storage, evidence-importer, and sole-axiom assumptions
explicit. It must not describe a hash of an unchecked large certificate as a
Lean proof.

## H100 trust boundary

The repository has exactly one project execution/certificate axiom:

```lean
axiom accepted_run_certificate_sound
    {certificate : RunCertificate}
    (accepted : checkTrustedCompute certificate.statement
      certificate.attestation = true) :
    certificate.ProducedOutcome
```

For an accepted certificate this yields `ProducedOutcome.historical`, stating
that the exact named computation returned the bound serialized result, and a
fail-closed `.registered` field. The latter supplies a fixed
`RegisteredInvocation.Runs` relation only when that closed invocation's full
statement check succeeds. `accepted_registered_run_sound` is a proved
projection of this same axiom, not an additional axiom. The legacy H100/DGX
structures cannot reach it.

For H100, `checkH100Attestation` is only a structural diagnostic. It requires the
H100 `sm_90` target, the confidential-computing trust profile, complete metadata,
successful completion, and exact equality of the algorithm, inputs, parameters,
domain, result, nonce, target, trust profile, and artifact hashes. Local, mock,
and DGX-signature evidence are rejected. `RunCertificate.check` also rejects
the `.h100Hardware` constructor even if that diagnostic succeeds, so it cannot
establish `AlgorithmReturned` or `Runs`.

Lean does not verify NVIDIA evidence cryptography. The Azure trusted-compute
path first calls independently pinned Azure and NVIDIA appraisers, verifies and
signs the normalized receipt, and source-pins an exact closed entry consumed by
`checkTrustedCompute`. That external admission must verify certificate chains,
TCB and measurement policy, debug state, freshness, CPU/GPU evidence binding,
measured-runner causality, and exact report data. The tooling exists, but the
tracked receipt registry is empty and there is no accepted H100 certificate
instance.

For a matching closed invocation, a future accepted instance also trusts the
physical-to-formal relation for that particular run. It still does not prove:

- that the zeta algorithm is mathematically sound;
- that the result bytes satisfy `check_count_sound`;
- that the registered PT21 checker has been run successfully or that its
  required `SourceEvidence` has been materialized;
- a universal theorem that emitted PTX was lowered faithfully to the measured
  cubin or that `ptxas`, SASS, the driver, or hardware refines the Lean PTX
  model; or
- that every future run returns the same result.

There are therefore two honest end states:

1. **Independent certificate verification.** Stream and check all mathematical
   evidence with a proved zeta checker. H100 attestation adds provenance but is
   unnecessary for the resulting zeta theorem.
2. **Attested server verification.** Keep the large witness server-side and
   register the exact checker invocation, trust an accepted run that returns a
   small result, and prove that its fixed `Runs` relation implies the zeta
   claim. This minimizes transfer but deliberately places the measured CPU/GPU
   execution, importer, closed registry binding, and sole run-certificate axiom
   in the theorem's trust story. The axiom supplies the particular-run
   physical-to-formal bridge; the formal checker-correctness theorem remains a
   required ordinary Lean proof.

The current repository has foundations for both designs, but completes neither
high-bound path.

## Completion criterion

The verifier may claim “all Riemann-zeta zeros in the closed critical strip
through absolute height `T` lie on the critical line” only when a concrete,
bounded certificate has been checked and its Lean theorem dependencies show:

1. sound Hardy-Z endpoint enclosures and disjoint root brackets;
2. a complete total-zero count with multiplicity handled explicitly;
3. the proved equality consumed by `all_zeros_to_height_on_criticalLine`; and
4. any execution or attestation assumptions stated separately from the
   mathematical checker result.

Until then, the new declarations are proof architecture and reusable
finite-counting infrastructure, not a verified high-bound zeta computation.
