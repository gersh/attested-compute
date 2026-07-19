# Project Specification: Lean-Verified GPU Interval Arithmetic for NVIDIA DGX Spark

> **Platform/trust addendum (implemented July 2026):** DGX Spark is the native
> `sm_121` target with canonical `local_unattested` evidence and no secure-
> enclave claim. H100 is a separate `sm_90` target with offline artifacts,
> mock/prod-separated evidence, and one isolated H100 hardware-execution axiom.
> DGX operator-signed records have a separate, explicit operator-trust axiom.
> Target profiles never imply trust profiles. See `docs/TRUST_MODEL.md`,
> `docs/FORMAT.md`, and `docs/IMPLEMENTATION_STATUS.md`. This addendum does not
> change the phase ordering or expand version 1 into a high-bound or
> critical-strip Riemann-zeta zero verifier.

> **Implementation-status addendum (July 2026):** Phases 0--4 are implemented.
> Phase 2's directed core and interval-operation proofs are complete, while the
> optional nearest-even midpoint-parity lemma and signed-zero bit refinement
> remain open. Phase 3's Python certificate is recomputed by Python, not Lean.
> Phase 4 passed five million randomized primitive operations and one million
> randomized expression/input cases, but the CUDA/wire evaluator does not yet
> have a Lean refinement theorem. Phase 5 is a typed generated-PTX vertical
> slice. Phase 6 now proves the canonical pure add/sub/mul instruction
> fragments against an executable Lean semantics, but whole-kernel refinement
> remains open. Phase 7 now also provides optional detached Ed25519 operator
> signatures for DGX local records; these are never hardware evidence. Phase 8
> Lean result certificates are not complete. A separate tutorial POC now
> rigorously encloses real `zeta(s)` for bounded integer `s > 1`; it does not
> implement critical-strip zero isolation or height completeness. The
> correctness statements below are final targets unless an
> implementation-status document explicitly says otherwise.

## 1. Project name

**SparkInterval**

## 2. Objective

Implement a small formally verified interval-arithmetic system that:

1. defines exact real-number interval semantics in Lean;
2. models the subset of IEEE-754 binary64 arithmetic required by the system;
3. defines a small GPU-oriented interval expression language;
4. proves that evaluating an expression with outward-rounded arithmetic produces an interval containing its exact real value;
5. generates a restricted CUDA or PTX kernel for NVIDIA DGX Spark;
6. runs large batches of independent interval computations on the DGX Spark GPU;
7. checks GPU results against a trusted CPU reference implementation;
8. records hashes of all inputs, outputs, source files, PTX, cubin files, tool versions, and hardware information;
9. produces a reproducible execution manifest;
10. optionally generates certificates that Lean can independently check.

The target machine is one NVIDIA DGX Spark containing an NVIDIA GB10 Grace Blackwell Superchip.

DGX Spark has an Arm64 CPU, 6,144 CUDA cores, 128 GB unified memory, and 273 GB/s memory bandwidth. Its GPU target is `sm_121`. ([NVIDIA Docs](https://docs.nvidia.com/dgx/dgx-spark/hardware.html))

The project must not claim that DGX Spark provides confidential-computing execution attestation. NVIDIA has stated that Confidential Compute is not supported on DGX Spark’s GB10. ([NVIDIA Developer Forums](https://forums.developer.nvidia.com/t/confidential-computing-support-for-dgx-spark-gb10/347945))

## 3. Intended correctness claim

The final system should support the following claim:

> The Lean formalization proves that the abstract interval evaluator encloses the exact real-number semantics of every supported expression. The DGX Spark kernel is generated from, or checked against, that evaluator. Subject to the stated compiler, PTX-conformance, driver, operating-system, and physical-hardware assumptions, the GPU output implements the verified interval algorithm.

A stronger claim is permitted when Lean independently checks the complete GPU output certificate:

> Lean has independently verified that the supplied intervals imply the final mathematical theorem.

The system must distinguish these claims clearly.

It must never claim:

- that the physical GPU has been formally verified;
- that `nvcc`, `ptxas`, the CUDA driver, or DGX OS has been formally verified;
- that a local digital signature proves the computation happened on particular hardware;
- that DGX Spark provides confidential-computing attestation;
- that testing the GPU against a reference implementation constitutes a proof of hardware correctness.

## 4. Initial scope

### 4.1 Numeric format

Version 1 shall support only:

- IEEE-754 binary64;
- finite interval endpoints;
- normal and subnormal binary64 values;
- positive and negative zero;
- infinities only as optional interval endpoints;
- explicit rejection of NaN inputs.

Do not initially support:

- binary32;
- binary16;
- bfloat16;
- Tensor Core arithmetic;
- FP4;
- complex intervals;
- arbitrary precision on the GPU;
- stochastic rounding;
- transcendental instructions.

### 4.2 Operations

Version 1 shall support:

- interval constants;
- input variables;
- unary negation;
- addition;
- subtraction;
- multiplication;
- reciprocal;
- division;
- integer powers for small nonnegative exponents;
- absolute value;
- minimum and maximum;
- finite sums;
- finite products.

Square root may be implemented only after the basic operations are complete.

Transcendental functions such as `exp`, `log`, `sin`, and `cos` are explicitly postponed.

### 4.3 Parallel execution model

Use one independent expression evaluation per GPU thread.

Version 1 must not use:

- shared memory;
- inter-thread communication;
- warp-level primitives;
- atomics;
- parallel reductions;
- dynamic parallelism;
- cooperative groups;
- Tensor Cores.

This restriction is intentional. It minimizes the GPU semantics and proof obligations.

## 5. Target repository layout

The following was the aspirational final layout. The implemented repository
uses equivalent modules with different names in several places; consult
`rg --files` and `docs/IMPLEMENTATION_STATUS.md` for current paths.

```text
SparkInterval/
├── README.md
├── LICENSE
├── lakefile.toml
├── lean-toolchain
├── Makefile
├── CMakeLists.txt
├── docs/
│   ├── TRUST_MODEL.md
│   ├── CORRECTNESS_CLAIMS.md
│   ├── GPU_MODEL.md
│   ├── REPRODUCIBILITY.md
│   ├── DGX_SPARK_SETUP.md
│   └── FORMAT.md
├── SparkInterval/
│   ├── Basic.lean
│   ├── RealInterval.lean
│   ├── FloatFormat.lean
│   ├── DirectedRounding.lean
│   ├── IntervalOps.lean
│   ├── IntervalOpsSound.lean
│   ├── Expr.lean
│   ├── ExactSemantics.lean
│   ├── IntervalSemantics.lean
│   ├── EvalSound.lean
│   ├── BatchSpec.lean
│   ├── Certificate.lean
│   ├── CertificateCheck.lean
│   ├── PTX/
│   │   ├── Syntax.lean
│   │   ├── State.lean
│   │   ├── FloatSemantics.lean
│   │   ├── Step.lean
│   │   ├── Kernel.lean
│   │   └── KernelSound.lean
│   └── Tests/
│       ├── RealIntervalTest.lean
│       ├── RoundingTest.lean
│       ├── ExprTest.lean
│       ├── CertificateTest.lean
│       └── AxiomAudit.lean
├── generator/
│   ├── Main.lean
│   ├── EmitPTX.lean
│   ├── EmitCUDA.lean
│   ├── EmitManifest.lean
│   └── GeneratedFormat.lean
├── gpu/
│   ├── include/
│   │   ├── spark_interval.h
│   │   └── formats.h
│   ├── src/
│   │   ├── kernel.cu
│   │   ├── runner.cpp
│   │   ├── cuda_checks.cpp
│   │   └── manifest.cpp
│   └── tests/
│       ├── test_basic.cpp
│       ├── test_rounding.cpp
│       ├── test_edge_cases.cpp
│       └── test_batch.cpp
├── reference/
│   ├── reference.py
│   ├── exact_dyadic.py
│   ├── generate_vectors.py
│   └── compare_results.py
├── tools/
│   ├── build_dgx_spark.sh
│   ├── capture_environment.sh
│   ├── extract_artifacts.sh
│   ├── inspect_sass.sh
│   ├── run_conformance.sh
│   ├── create_manifest.py
│   ├── verify_manifest.py
│   └── audit_axioms.sh
├── schemas/
│   ├── input.schema.json
│   ├── output.schema.json
│   ├── certificate.schema.json
│   └── manifest.schema.json
├── examples/
│   ├── polynomial/
│   ├── rational_bound/
│   └── batch_inequalities/
└── .github/
    └── workflows/
        └── lean-and-cpu.yml
```

## 6. Lean mathematical model

### 6.1 Real intervals

Define:

```lean
structure RealInterval where
  lo : ℝ
  hi : ℝ
  valid : lo ≤ hi
```

Define membership:

```lean
def RealInterval.Contains (I : RealInterval) (x : ℝ) : Prop :=
  I.lo ≤ x ∧ x ≤ I.hi
```

Define exact interval operations and prove soundness independently of floating-point arithmetic.

Required theorems include:

```lean
theorem add_contains
    (hx : X.Contains x)
    (hy : Y.Contains y) :
    (X.add Y).Contains (x + y)
```

```lean
theorem sub_contains
    (hx : X.Contains x)
    (hy : Y.Contains y) :
    (X.sub Y).Contains (x - y)
```

```lean
theorem mul_contains
    (hx : X.Contains x)
    (hy : Y.Contains y) :
    (X.mul Y).Contains (x * y)
```

Division must require that the denominator interval excludes zero:

```lean
def ExcludesZero (I : RealInterval) : Prop :=
  I.hi < 0 ∨ 0 < I.lo
```

```lean
theorem div_contains
    (hx : X.Contains x)
    (hy : Y.Contains y)
    (hzero : Y.ExcludesZero) :
    (X.div Y hzero).Contains (x / y)
```

### 6.2 Dyadic floating-point model

Do not initially use Lean’s runtime `Float` as the formal definition.

Define a mathematical representation of binary64:

```lean
structure Binary64Finite where
  sign : Bool
  significand : Nat
  exponent : Int
  canonical : Binary64Canonical sign significand exponent
```

Alternatively, reuse an existing trustworthy Lean IEEE-754 development if one is sufficiently mature and compatible. Document the dependency and its theorem boundary.

Define:

```lean
def Binary64Finite.toReal : Binary64Finite → ℝ
```

Define exact representability, successor, predecessor, least representable value above a real, and greatest representable value below a real.

Required abstract rounding operations:

```lean
def roundDown : ℝ → ExtBinary64
def roundUp : ℝ → ExtBinary64
def roundNearestEven : ℝ → ExtBinary64
```

Required theorems:

```lean
theorem roundDown_le (x : ℝ) :
  (roundDown x).toExtendedReal ≤ x
```

```lean
theorem le_roundUp (x : ℝ) :
  x ≤ (roundUp x).toExtendedReal
```

```lean
theorem roundDown_greatest :
  Represents y →
  y.toReal ≤ x →
  y.toReal ≤ (roundDown x).toExtendedReal
```

```lean
theorem roundUp_least :
  Represents y →
  x ≤ y.toReal →
  (roundUp x).toExtendedReal ≤ y.toReal
```

### 6.3 Floating-point interval type

Define:

```lean
structure FPInterval where
  lo : ExtBinary64
  hi : ExtBinary64
  ordered : lo ≤ hi
  notNaNLo : ¬ lo.isNaN
  notNaNHi : ¬ hi.isNaN
```

Define its real interpretation:

```lean
def FPInterval.ContainsReal (I : FPInterval) (x : ℝ) : Prop :=
  I.lo.toExtendedReal ≤ x ∧ x ≤ I.hi.toExtendedReal
```

Implement abstract outward-rounded operations:

```lean
def fpAdd (X Y : FPInterval) : FPInterval
def fpSub (X Y : FPInterval) : FPInterval
def fpMul (X Y : FPInterval) : FPInterval
def fpDiv (X Y : FPInterval) (h : XorZeroCondition Y) : FPInterval
```

Required soundness theorem for every operation:

```lean
theorem fpAdd_sound
    (hx : X.ContainsReal x)
    (hy : Y.ContainsReal y) :
    (fpAdd X Y).ContainsReal (x + y)
```

Similar theorems are required for all supported operations.

## 7. Expression language

Implementation note: Phase 1 currently uses `Expr.const : ℝ` and proves an
exact-`RealInterval` evaluator sound. Phase 2 proves `FPInterval` arithmetic
separately. The FP expression evaluator matching the interval-valued wire
constants below, and its refinement to the Phase 1 semantics, are still open.

Define a deliberately small expression language:

```lean
inductive Expr
  | const : FPInterval → Expr
  | var : Nat → Expr
  | neg : Expr → Expr
  | add : Expr → Expr → Expr
  | sub : Expr → Expr → Expr
  | mul : Expr → Expr → Expr
  | div : Expr → Expr → Expr
  | abs : Expr → Expr
  | min : Expr → Expr → Expr
  | max : Expr → Expr → Expr
  | powNat : Expr → Nat → Expr
```

Variables are indexed into an input environment.

Define two semantics.

Exact semantics:

```lean
def evalReal : Expr → Array ℝ → Option ℝ
```

Interval semantics:

```lean
def evalInterval : Expr → Array FPInterval → Option FPInterval
```

The main theorem is:

```lean
theorem evalInterval_sound
    (henv : EnvironmentsCorrespond realEnv intervalEnv)
    (hreal : evalReal expr realEnv = some value)
    (hint : evalInterval expr intervalEnv = some result) :
    result.ContainsReal value
```

This theorem is the mathematical core of the project.

No GPU work should begin until this theorem is proved for the initial expression language.

## 8. Batch semantics

Implementation note: Python and CUDA batch evaluators exist, including
explicit row-status semantics, but this Lean batch definition and the decoder
from the binary/JSON formats have not yet been implemented.

Define a batch as:

```lean
structure BatchProblem where
  expression : Expr
  rows : Array (Array FPInterval)
  variableCount : Nat
  rowsWellFormed : ...
```

Define:

```lean
def evalBatchSpec : BatchProblem → Array (Option FPInterval)
```

Prove:

```lean
theorem evalBatchSpec_sound :
  ∀ i < problem.rows.size,
    CorrespondingRealInput problem i realRow →
    ExactEvaluation problem.expression realRow value →
    (evalBatchSpec problem)[i] = some result →
    result.ContainsReal value
```

## 9. PTX strategy

### 9.1 Target

Generate PTX for the installed toolkit's supported `sm_121` PTX ISA version.
The current CUDA 13 build emits:

```text
.version 9.0
.target sm_121
.address_size 64
```

The implementation must record the emitted PTX version, detect the locally
installed CUDA toolkit, and reject an incompatible version or target rather
than silently changing either.

### 9.2 PTX versus CUDA

Implement two execution paths:

1. a readable CUDA C++ prototype;
2. a generated restricted PTX path used for the formal-verification target.

The CUDA version is for testing and benchmarking.

The PTX version is the artifact corresponding to the formal model.

Do not attempt to formalize arbitrary CUDA C++.

### 9.3 Allowed PTX subset

Initially permit only instructions needed for:

- loading kernel parameters;
- obtaining the one-dimensional thread index;
- integer index arithmetic;
- bounds checks;
- global loads;
- global stores;
- register moves;
- predicates;
- conditional branch to kernel exit;
- binary64 arithmetic with explicit rounding modes;
- integer arithmetic for indexing.

Maintain an explicit allowlist.

The generated PTX must fail validation if it contains an instruction outside the allowlist.

Suggested initial floating-point allowlist:

```text
add.rm.f64
add.rp.f64
sub.rm.f64
sub.rp.f64
mul.rm.f64
mul.rp.f64
div.rm.f64
div.rp.f64
neg.f64
min.f64
max.f64
setp.*
selp.*
mov.*
ld.*
st.*
```

Confirm the precise legal spelling and semantics against the installed PTX ISA documentation before emission.

Do not assume an instruction supports a rounding modifier merely because another instruction does.

### 9.4 PTX syntax model

Define a typed Lean AST for the allowed PTX subset.

Do not represent verified PTX as arbitrary strings.

Example:

```lean
inductive RoundingMode
  | rn
  | rz
  | rm
  | rp

inductive F64Instr
  | add : RoundingMode → Reg → Reg → Reg → F64Instr
  | sub : RoundingMode → Reg → Reg → Reg → F64Instr
  | mul : RoundingMode → Reg → Reg → Reg → F64Instr
  | div : RoundingMode → Reg → Reg → Reg → F64Instr
```

The text emitter must be proved or extensively tested to serialize each AST constructor to the intended PTX instruction.

## 10. Formal PTX model

### 10.1 Model boundary

Formalize only the generated subset of PTX.

Do not attempt to model:

- all PTX instructions;
- general warp scheduling;
- shared memory;
- atomics;
- weak-memory concurrency;
- device-side allocation;
- texture operations;
- Tensor Cores.

### 10.2 State

Define:

```lean
structure ThreadState where
  pc : Nat
  regs64 : Reg64 → BitVec 64
  regs32 : Reg32 → BitVec 32
  predicates : Pred → Bool
  exited : Bool
  faulted : Bool
```

Define read-only input memory and write-only output regions:

```lean
structure KernelMemory where
  inputBytes : ByteArray
  outputBytes : ByteArray
  inputBase : UInt64
  outputBase : UInt64
```

For version 1, model each thread independently.

The global batch semantics may be defined as a map over thread identifiers because each thread reads a disjoint logical input row and writes one disjoint output row.

### 10.3 Arithmetic semantics

For each PTX arithmetic instruction, relate its result to the binary64 rounding model.

Example:

```lean
def execAddRM (a b : Binary64) : Binary64 :=
  roundDownBinary64 (a.toReal + b.toReal)
```

Required theorem:

```lean
theorem execAddRM_correct :
  decode (execAddRM a b) =
    roundDown (decode a + decode b)
```

The PTX model should be based on the documented virtual instruction semantics, not on assumptions about SASS instruction names.

### 10.4 Kernel theorem

Required theorem:

```lean
theorem generatedKernel_sound
    (hProgram : compileExpr expr = some kernel)
    (hInputs : BatchInputsWellFormed inputs)
    (hExec : executeKernelModel kernel inputs = some outputs) :
    ∀ i < inputs.size,
      match evalInterval expr inputs[i], outputs[i] with
      | some expected, some actual =>
          expected = actual
      | _, _ => False
```

Then derive:

```lean
theorem generatedKernel_real_sound :
  ...
  actual.ContainsReal exactValue
```

## 11. Code generator

Implement a Lean executable that:

1. reads a serialized expression;
2. validates the expression;
3. allocates virtual registers;
4. emits typed PTX AST;
5. proves or constructs evidence that generated code is well formed;
6. serializes PTX;
7. emits input and output format metadata;
8. computes source hashes;
9. emits a build manifest.

The code generator must be deterministic.

Running it twice with identical inputs and versions must produce byte-identical PTX.

Final target command (metadata/manifest output is not yet implemented):

```bash
lake exe sparkinterval-gen \
  --expr examples/polynomial/expression.json \
  --output build/generated/kernel.ptx \
  --metadata build/generated/kernel.json
```

The accepted Phase 5 polynomial slice currently consumes a complete canonical
reference batch:

```bash
lake exe sparkinterval-gen --input batch.json --output build/generated/kernel.ptx
```

## 12. Native GPU runner

Implement an Arm64 Linux executable for DGX Spark.

Final target command (manifest output is not yet implemented as written):

```bash
./build/sparkinterval-run \
  --cubin build/generated/kernel.sm_121.cubin \
  --input examples/polynomial/input.bin \
  --output build/run/output.bin \
  --manifest build/run/manifest.json
```

The current Phase 5 Driver API executable is:

```bash
build/dgx-spark/sparkinterval-generated-driver \
  --cubin build/generated/kernel.sm_121.cubin \
  --input build/generated/rows.bin \
  --output build/generated/results.bin
```

Acceptance audits generated PTX, assembles it offline with `ptxas`, audits the
resulting cubin's SASS, and passes those exact cubin bytes to this command. The
driver's `--ptx` path is explicitly development-only JIT mode. It validates
and executes the current row/output ABI but does not itself emit the Phase 7
manifest named by the target interface above. The fail-closed
`create_dgx_generated_cubin_bundle.py` wrapper packages a retained strong run
after execution.

The runner must:

1. initialize CUDA;
2. check that exactly the expected GB10 device is selected;
3. record the reported compute capability;
4. reject devices other than `sm_121`, unless an explicit development override is supplied;
5. load the audited cubin for acceptance (or compile PTX only in explicit
   development mode);
6. allocate input and output buffers;
7. initialize outputs with a recognizable invalid pattern;
8. launch the kernel;
9. synchronize;
10. check every CUDA return code;
11. copy outputs back;
12. check that every expected output was written;
13. write the raw output file;
14. write an execution manifest.

The runner must not silently recover from CUDA errors.

## 13. Exact CPU reference

Implement a slow reference evaluator using exact integers, rationals, or dyadic arithmetic.

Python may be used for test-vector generation, but the authoritative reference should eventually be implemented in Lean or in a small independently auditable program.

The reference evaluator must not use ordinary binary64 arithmetic to decide the expected result.

For a binary64 operation, compute the exact mathematical result and then derive the correctly rounded binary64 endpoint.

Example:

```python
def add_down(a_bits: int, b_bits: int) -> int:
    a = decode_binary64_as_exact_dyadic(a_bits)
    b = decode_binary64_as_exact_dyadic(b_bits)
    return greatest_binary64_leq(a + b)
```

## 14. Conformance testing

### 14.1 Required edge cases

Test at minimum:

- `+0` and `-0`;
- smallest positive subnormal;
- largest subnormal;
- smallest positive normal;
- adjacent representable values;
- values near powers of two;
- largest finite binary64;
- positive and negative overflow;
- cancellation;
- multiplication by zero;
- sign changes;
- intervals crossing zero;
- division near zero;
- all four sign combinations for multiplication;
- minimum and maximum endpoint-selection ties.

### 14.2 Random testing

Generate at least:

- one million random addition cases;
- one million random subtraction cases;
- one million random multiplication cases;
- one million valid division cases;
- one million random interval-expression cases.

Compare GPU output bit-for-bit with the exact reference.

Separate test counts from proof claims in all documentation.

### 14.3 Metamorphic tests

Check properties such as:

```text
X + [0,0] contains X
X * [1,1] contains X
-X contains negations of all values in X
X + Y and Y + X produce equal or mutually enclosing intervals
X * Y and Y * X produce equal or mutually enclosing intervals
```

Do not use metamorphic testing as a replacement for exact-reference testing.

## 15. Cubin and SASS artifact inspection

Compile PTX for `sm_121` and extract all generated artifacts.

NVIDIA’s binary utilities support inspecting PTX and machine artifacts for `sm_121`. ([NVIDIA Docs](https://docs.nvidia.com/cuda/cuda-binary-utilities/index.html))

Required script:

```bash
tools/extract_artifacts.sh build/generated/kernel.ptx build/artifacts/
```

It must produce:

```text
kernel.ptx
kernel.cubin
kernel.sass.txt
kernel.sass.json
toolchain.txt
sha256sums.txt
```

Use `cuobjdump` and `nvdisasm` when available.

The SASS inspection tool must:

- identify the kernel function;
- record every instruction mnemonic;
- flag unexpected floating-point instructions;
- flag Tensor Core instructions;
- flag approximate reciprocal or approximate transcendental instructions;
- flag unexpected fused operations;
- flag unexpected loads, stores, atomics, or synchronization;
- produce a machine-readable report.

This inspection is an audit, not a proof of PTX-to-SASS equivalence.

## 16. Execution manifest

Every run must produce a canonical JSON manifest containing:

```json
{
  "schema_version": 1,
  "project_commit": "...",
  "dirty_worktree": false,
  "lean_version": "...",
  "lake_version": "...",
  "cuda_toolkit_version": "...",
  "cuda_driver_version": "...",
  "ptx_version": "...",
  "ptx_target": "sm_121",
  "device_name": "...",
  "device_uuid": "...",
  "compute_capability": "12.1",
  "dgx_os_version": "...",
  "kernel_source_sha256": "...",
  "ptx_sha256": "...",
  "cubin_sha256": "...",
  "sass_sha256": "...",
  "input_sha256": "...",
  "output_sha256": "...",
  "expression_sha256": "...",
  "row_count": 0,
  "launch": {
    "grid_x": 0,
    "block_x": 0
  },
  "cuda_errors": [],
  "reference_comparison": {
    "performed": true,
    "matching_rows": 0,
    "mismatching_rows": 0
  },
  "start_time_utc": "...",
  "end_time_utc": "...",
  "host_signature": null,
  "hardware_attestation": null
}
```

For DGX Spark, `hardware_attestation` must remain `null` unless a future genuinely supported hardware facility is integrated.

A host-generated signature may be included, but documentation must say that it proves only that possession of the signing key signed the manifest.

## 17. Certificate format

The final design supports three certificate modes.

### 17.1 Full certificate

Contains every input interval and every output interval.

Lean checks:

- file structure;
- hashes;
- row count;
- interval well-formedness;
- the final application-specific predicate for every row.

This mode is independently checkable but may be large.

### 17.2 Merkle certificate

Contains:

- Merkle root over all result rows;
- selected openings;
- aggregate metadata;
- a separate full result file.

This supports audit sampling but does not, by itself, prove every result to Lean.

Do not present a Merkle root alone as proof of all arithmetic results.

### 17.3 Application-specific compressed certificate

For some applications, the GPU should return a compact witness rather than all intermediate arithmetic.

Example:

- maximum upper bound and its row index;
- minimum lower bound and its row index;
- list of failing rows;
- segment maxima;
- recursively aggregated bounds.

Such a certificate is acceptable only when Lean proves that checking the compressed witness is sufficient to establish the desired theorem.

## 18. Axiom and trust audit

Create:

```lean
#print axioms SparkInterval.evalInterval_sound
#print axioms SparkInterval.generatedKernel_real_sound
#print axioms SparkInterval.Certificate.impliesTheorem
```

The CI job must fail if unexpected axioms appear.

Allowed foundational assumptions should be listed explicitly.

The mathematical interval theorem should ideally depend only on Lean’s standard logical foundations and approved library axioms.

The physical execution claim necessarily depends on external assumptions, including:

- NVIDIA’s PTX documentation correctly describes intended behavior;
- the CUDA driver correctly translates or executes PTX;
- the generated cubin corresponds to the recorded PTX;
- DGX Spark executes the cubin correctly;
- memory and storage are not corrupted;
- the operating system and runner report artifacts honestly;
- the SHA-256 implementation behaves correctly;
- local signing keys are not compromised.

These assumptions must appear in `docs/TRUST_MODEL.md`.

## 19. Build requirements

The primary target is native Arm64 on DGX Spark.

Required build command:

```bash
./tools/build_dgx_spark.sh
```

The build script must:

1. print system information;
2. verify `uname -m` is `aarch64`;
3. verify CUDA is installed;
4. detect CUDA version;
5. detect Lean version;
6. detect `sm_121` support;
7. build Lean proofs;
8. build the generator;
9. generate PTX;
10. build the native runner;
11. build CPU tests;
12. compile the PTX or CUDA artifact;
13. extract cubin and SASS;
14. run smoke tests;
15. produce a build manifest.

Use the installed CUDA version supported by the DGX Spark OS image rather than automatically replacing NVIDIA’s supplied driver stack.

## 20. Reproducibility

Record:

```bash
uname -a
cat /etc/os-release
lean --version
lake --version
nvcc --version
nvidia-smi
/usr/local/cuda/bin/ptxas --version
cuobjdump --version
nvdisasm --version
git rev-parse HEAD
git status --porcelain
```

Also record all relevant package versions.

The repository must contain a lockfile or exact dependency revisions.

Do not use unpinned Git dependencies.

## 21. Performance requirements

Correctness takes priority over speed.

After correctness is established, benchmark:

- kernel launch overhead;
- intervals evaluated per second;
- expressions evaluated per second;
- CPU exact-reference throughput;
- CPU floating-point-reference throughput;
- GPU-versus-CPU speedup;
- transfer overhead;
- performance versus expression size;
- performance versus batch size.

Initial performance target:

- at least 10 million primitive interval operations per second for sufficiently large batches;
- bit-for-bit agreement with the exact reference for all validation tests;
- no unexplained CUDA errors;
- deterministic output bits for identical inputs and software versions.

This target may be revised after measurement.

## 22. Development phases

### Phase 0: Environment probe

Deliver:

- system-information script;
- CUDA feature probe;
- binary64 directed-rounding probe;
- simple `sm_121` kernel;
- toolchain manifest.

Acceptance criteria:

- repository builds on the user’s DGX Spark;
- CUDA kernel executes;
- `sm_121` is detected;
- PTX, cubin, and SASS can be extracted;
- exact installed versions are recorded.

### Phase 1: Lean real interval library

Deliver:

- real interval definitions;
- exact operations;
- containment theorems;
- expression language;
- exact and interval semantics;
- evaluator soundness theorem.

Acceptance criteria:

```bash
lake build
```

passes with no `sorry`.

### Phase 2: Formal binary64 rounding model

Status: directed rounding and the four interval-operation soundness results are
implemented. Unconditional nearest-even tie parity and signed-zero bit-level
refinement remain open.

Deliver:

- binary64 representation;
- exact decoding;
- directed rounding;
- basic arithmetic soundness.

Acceptance criteria:

- all four basic interval operations are proved sound;
- edge-case tests pass;
- no hidden use of native floating-point behavior in theorem statements.

### Phase 3: CPU executable reference

Status: implemented as exact rational Python with canonical formats and edge
vectors. It is an independently auditable conformance oracle, not yet a Lean-
authoritative executable or certificate checker.

Deliver:

- serialization format;
- exact CPU evaluator;
- certificate parser;
- reference test vectors.

Acceptance criteria:

- exact reference agrees with independently generated oracle vectors;
- all edge cases pass.

### Phase 4: CUDA prototype

Status: accepted on the native GB10 at the required primitive and expression
counts, with explicit failure statuses, deterministic replay, and PTX/SASS
audits. A Lean refinement theorem is not part of this phase and remains open.

Deliver:

- one-thread-per-row CUDA kernel;
- batch runner;
- benchmark harness;
- exact-reference comparison.

Acceptance criteria:

- at least five million randomized primitive-operation tests pass;
- at least one million randomized expression tests pass;
- output is bit-for-bit deterministic.

### Phase 5: Typed PTX generator

Status: a typed deterministic polynomial vertical slice is implemented; the
full expression language and final acceptance evidence are tracked in
`docs/IMPLEMENTATION_STATUS.md`.

Deliver:

- typed PTX AST;
- deterministic emitter;
- `sm_121` target;
- instruction allowlist;
- PTX parser or validator for generated output.

Acceptance criteria:

- generated PTX runs on DGX Spark;
- generated output matches CUDA prototype and exact reference;
- no disallowed instruction occurs in PTX.

### Phase 6: Formal PTX-subset semantics

Status: a first pure-arithmetic slice is implemented. It models raw moves,
numeric sign negation, directed add/subtract/multiply, min/max, and
fresh-register execution, and proves enclosure for the exact arithmetic arrays
used by the generator. Control flow, memory, threads, emitted-text refinement,
and the full kernel theorem remain open.

Deliver:

- PTX state model;
- arithmetic instruction semantics;
- memory and indexing semantics;
- generated-kernel theorem.

Acceptance criteria:

- `generatedKernel_sound` is proved;
- proof uses no `sorry`;
- axiom audit contains only approved assumptions.

### Phase 7: Artifact and execution records

Status: diagnostic-probe and generated-cubin arithmetic bundles, artifact
hashing, local/mock/H100 policy separation, and detached Ed25519 DGX operator
signatures are implemented. The signed policy requires a separately pinned
public key, all artifact bytes, and persistent replay state while retaining
`local_unattested` evidence and `hardware_evidence: false`. The DGX
arithmetic packager requires strong acceptance and preserves exact source,
PTX, cubin, SASS, inputs, outputs, audits, replay artifacts, executables, and
toolchain binaries. It is explicitly local/unattested. H100 arithmetic
packaging still awaits real measured execution and positive evidence import.

Deliver:

- cubin extraction;
- SASS inspection;
- manifest generation;
- hash verification;
- optional local signing.

Acceptance criteria:

- every run is reproducibly associated with exact source, PTX, cubin, inputs, and outputs;
- manifest verifier detects any modified artifact;
- documentation explicitly states that this is not confidential-computing attestation.

### Phase 8: Lean-checkable application certificate

Status: not implemented. The Phase 3 Python `reference_certificate` must not be
confused with this deliverable.

Deliver:

- full certificate format;
- Lean parser;
- Lean checker;
- one nontrivial batch-inequality example.

Acceptance criteria:

- corrupting any checked row causes rejection;
- the example theorem is derived from the checked certificate;
- the final theorem’s `#print axioms` output is recorded.

## 23. Testing policy

Every bug must receive a regression test.

Tests are divided into:

- theorem-level Lean tests;
- serialization tests;
- CPU exact-reference tests;
- CUDA tests;
- PTX tests;
- CPU/GPU differential tests;
- malformed-input tests;
- manifest-integrity tests;
- certificate-corruption tests.

CI without a GPU shall run:

- all Lean proofs;
- CPU reference tests;
- serialization tests;
- PTX-generation tests;
- manifest tests.

DGX Spark local CI shall additionally run GPU tests.

## 24. Failure behavior

The program must fail closed.

Reject:

- malformed expressions;
- malformed intervals;
- NaN endpoints;
- denominator intervals containing zero;
- unsupported operations;
- unsupported PTX versions;
- unsupported compute capability;
- unexpected output length;
- untouched output sentinels;
- hash mismatches;
- CUDA launch failures;
- CUDA synchronization failures;
- unexpected SASS audit findings;
- dirty source tree when reproducibility mode is enabled.

Never replace a failed interval computation with `[−∞,+∞]` without recording a failure status.

## 25. Coding requirements for Codex

Codex must:

1. implement one phase at a time;
2. run tests after every meaningful change;
3. never introduce `sorry`, `admit`, `axiom`, or `unsafe` merely to make Lean compile;
4. never weaken a theorem silently;
5. never change a mathematical definition solely to accommodate an implementation bug;
6. document every trusted boundary;
7. keep generated files separate from hand-written files;
8. avoid adding large dependencies without justification;
9. avoid clever GPU optimizations until the simple kernel is correct;
10. preserve bit-level reproducibility;
11. report incomplete proof obligations honestly;
12. commit or provide a concise change log after each phase.

Codex must search the repository before creating duplicate definitions.

Codex must use existing mathlib definitions where they are adequate, but it must not assume that Lean’s native `Float` operations expose all required formally specified IEEE-754 properties.

## 26. Historical initial Codex task

This section governed the first milestone and is retained for provenance. The
repository has since been explicitly advanced beyond Phase 1.

Begin only with Phase 0 and Phase 1.

First:

1. inspect the DGX Spark environment;
2. record the installed Lean, CUDA, driver, DGX OS, PTX tools, and GPU capability;
3. create the repository skeleton;
4. implement `RealInterval`;
5. implement exact real interval addition, subtraction, multiplication, reciprocal, and division;
6. prove their containment theorems;
7. implement `Expr`, `evalReal`, and an exact real-interval evaluator;
8. prove evaluator soundness;
9. add tests and axiom auditing;
10. stop before implementing binary64 or CUDA arithmetic.

Do not begin GPU implementation until the abstract evaluator soundness theorem is complete.

The first milestone is complete only when:

```bash
lake build
./tools/audit_axioms.sh
```

both succeed, no `sorry` appears in the repository, and the README explains the intended DGX Spark architecture and trust boundary.

## 27. Final project deliverables

The complete project should contain:

- a Lean-verified interval expression evaluator;
- a formal binary64 outward-rounding model;
- a restricted formal PTX model;
- a deterministic `sm_121` PTX generator;
- a DGX Spark batch runner;
- exact CPU conformance testing;
- PTX and SASS artifact auditing;
- reproducible execution manifests;
- Lean-checkable result certificates;
- explicit trust documentation;
- benchmarks on the user’s DGX Spark;
- a worked mathematical example.

## 28. Final theorem target

The project should culminate in a theorem structurally similar to:

```lean
theorem checked_gpu_batch_implies_goal
    (expr : Expr)
    (problem : BatchProblem)
    (cert : BatchCertificate)
    (hCert : Certificate.check expr problem cert = true)
    (hBridge : ApplicationBridge expr problem cert) :
    DesiredMathematicalTheorem
```

The strongest assurance comes from `Certificate.check`: Lean checks the result data that implies the theorem.

The GPU is then an accelerator for producing the certificate, not an additional logical axiom needed by the final mathematical theorem.

That architecture should be preferred whenever the resulting certificate is small enough for Lean to check.
