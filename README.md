# SparkInterval

SparkInterval has a Lean-verified interval-arithmetic core and tested GPU
backends under two execution profiles:

- **DGX Spark (`aarch64`, `sm_121`)** is the first native target. It has no
  confidential-computing execution attestation. Its manifests provide artifact
  identity and reproducibility metadata. An optional Ed25519 operator signature
  proves which approved key endorsed the exact record, but still does not prove
  that a particular physical GPU performed a run.
- **H100 (`x86_64`, `sm_90`)** is a subsequent target. Its code, cubin, result
  statement, and attestation interface can be developed offline; a real
  confidential H100 is required for final attestation acceptance.

The project deliberately separates four facts:

1. Lean proves soundness of the mathematical interval algorithm.
2. The current Python, CUDA, and generated-PTX slice are tested against exact
   arithmetic; formal decoder/backend/generator-refinement theorems are still
   pending.
3. A physical GPU run depends on the disclosed compiler, driver, operating
   system, and hardware assumptions.
4. An independently checked Lean certificate can remove the GPU run from the
   final theorem, while a provenance-based theorem instead exposes the named
   execution axiom appropriate to H100 hardware or DGX operator trust.

Phases 0--4 are now implemented.  The repository contains the exact
real-interval evaluator, a formal binary64 decoding and directed-rounding
model, proved binary64 interval add/subtract/multiply/divide containment, an
exact rational Python oracle and canonical formats, and native GB10 primitive
and postfix-expression CUDA batch runners.  Phase 4 passed 5,000,000 randomized
primitive cases and 1,000,000 randomized expression/input cases with zero bit
mismatches. The retained expression report also binds the executable and
audited `sm_121` PTX/SASS hashes and includes a byte-identical replay.

These are conformance results, not a Lean proof about the wire evaluator or
CUDA program.  The files named `reference_certificate` are Python-recomputed
packages, not Phase 8 Lean certificates. Phase 5 now has an accepted typed,
deterministic restricted-PTX vertical slice for one fixed polynomial: 100,000
native rows matched both exact Python and the Phase 4 CUDA payload. Acceptance
audited PTX, assembled a cubin offline, audited that cubin's SASS, and loaded
those exact cubin bytes. Deterministic PTX/cubin/output replay and a separate
signed-zero suite also passed. The full expression language, formal PTX
kernel semantics, and generated-kernel theorem remain open. A first Phase 6
slice now defines Lean semantics for the exact pure add/subtract/multiply
instruction arrays emitted by the generator and proves their enclosure; it
does not yet cover guards, control flow, memory, threads, or emitted PTX text.
Phase 7 now also supports detached Ed25519 signatures over complete DGX local
bundles, with separately pinned public keys and replay protection. The inner
evidence remains `local_unattested` and verification still reports
`hardware_evidence: false`.

## DGX Spark quick start

```bash
./tools/build_dgx_spark.sh
```

The command checks the host architecture and GPU target, builds the Lean
development and CUDA paths, runs development-sized tests, captures the environment, and
extracts inspectable GPU artifacts under `build/`. It emits
`build/dgx-probe-bundle/run-bundle.json`; verification reports
`hardware_evidence: false` by design.  That bundle records the diagnostic
probe, not the large arithmetic acceptance runs.

Run the full arithmetic acceptance paths explicitly:

```bash
python3 tools/run_primitive_conformance.py --count 1250000 \
  --work-dir build/primitive-conformance/rows-1250000 \
  > build/primitive-conformance-1250000.json
python3 tools/run_expression_conformance.py --count 1000000 \
  --program-count 256 \
  --work-dir build/expression-conformance/rows-1000000-programs-256
```

The primitive count is per operation; the expression count is shared across
the requested randomized programs.  Exact CPU recomputation dominates the
wall time.

The accepted generated-PTX polynomial slice is a two-step run. The closure
does not trust the base report's comparison claim: it independently recomputes
the exact result, regenerates and reassembles the cubin, replays the exact
cubin, and cross-checks the Phase 4 backend. See `docs/REPRODUCIBILITY.md` for
the commands and scope.

After closure, `tools/create_dgx_generated_cubin_bundle.py` packages the full
arithmetic run into the same canonical bundle format used elsewhere. The
retained 100,000-row bundle passes byte-integrity verification and reports
`local_unattested` / `hardware_evidence: false`, as required for GB10.

To supply a challenger nonce instead of a locally generated uniqueness value:

```bash
SPARKINTERVAL_NONCE_HEX=<64-lowercase-hex-characters> \
  ./tools/build_dgx_spark.sh
```

## Examples

The worked examples are indexed in [`examples/README.md`](examples/README.md).
They cover exact reference certificates, axiom-free Lean interval proofs,
unsigned DGX records, operator key generation/signing, the generated-cubin
acceptance path, H100 offline artifacts, and the execution-axiom boundary.

The application tutorial computes a rigorous real enclosure of `zeta(2)` from
4,096 GPU interval terms plus an integral-test tail, then independently
recomputes every row and audit:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta2-4096 \
  --s 2 --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

The retained GB10 calculation produced raw binary64 real endpoints
`[3ffa51a65a53d51c, 3ffa51a66a52e51f]`. See
[`docs/algorithms/REAL_ZETA_POC.md`](docs/algorithms/REAL_ZETA_POC.md) for the
algorithm, tail proof, additional integer examples, and exact scope.

## H100 work that can be done offline

```bash
./tools/build_h100_offline.sh
./tests/test_h100_offline.sh
./tools/build_h100_interval_batch_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

These commands generate and audit real `compute_90` PTX and `sm_90` cubin/SASS
without claiming they ran. `tools/run_h100_mock.sh` is test-only.
`tools/run_h100_cc_acceptance.sh` always fails closed (exit 78) until its stub
is replaced and tested on a supported confidential H100 platform.

## Trust boundary

DGX Spark's GB10 does not provide the confidential-computing facility required
for a hardware-backed run certificate. `hardware_attestation` therefore remains
`null` for this profile. See `docs/TRUST_MODEL.md` and
`docs/CORRECTNESS_CLAIMS.md` before interpreting a result.

The mathematical core remains independent of execution provenance. The source
audit permits exactly two project execution postulates:
`h100_attested_run_sound` for accepted H100 hardware evidence and
`dgx_operator_signed_run_sound` for the explicit decision to trust the truth of
an approved operator's signed DGX claim. The latter is deliberately stronger
than what Ed25519 proves. Unsigned local and mock evidence reduce to rejection
before either boundary.

Two formal details also remain visible rather than being hidden by the test
results: the value-level Lean model identifies the two signed-zero encodings,
whereas Python/CUDA preserve their bits, and the optional nearest-even
candidate still lacks its unconditional midpoint-parity theorem.  Directed
rounding and the interval soundness theorems do not depend on that nearest-even
obligation.

The real-integer POC rigorously encloses `zeta(s)` for recorded integers
`2 <= s <= 64` whose fixed binary64 program remains finite. This is not a
high-bound Riemann-zeta zero verifier. Complex intervals, certified
transcendental functions, critical-strip evaluation and zero isolation, and a
completeness argument such as a proved Turing-method layer remain future work.
No current theorem turns an `AlgorithmReturned` provenance fact or the POC
wire report into a zeta-zero theorem. The exact phase boundary is recorded in
`docs/IMPLEMENTATION_STATUS.md`.
