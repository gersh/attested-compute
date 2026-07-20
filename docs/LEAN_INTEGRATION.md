# Using computation certificates from Lean

SparkInterval's full result certificates are usable as Lean theorems today.
The unfinished part of the vision is production enclave-backed issuance and a
shared public certificate registry, not the basic certificate-to-theorem path.

The central idea is to separate three costs:

1. **Discovery:** run the finite calculation or search, possibly on a large CPU
   or GPU system.
2. **Certification:** check a witness with a smaller checker whose soundness is
   proved in Lean, then build a Lean module exporting the result theorem.
3. **Consumption:** import that compiled module and apply the theorem in later
   proofs.

Discovery and checking are not the same computation. A certificate should make
checking substantially more direct than discovering the result, although the
current complete interval certificate still scales with the number and size of
its rows.

## What the certificate preserves

The current full certificate is not merely a result string. Its canonical JSON
contains:

- an algorithm identifier;
- the interval-expression AST—the actual formula being evaluated;
- the variable count and every canonical input row;
- every claimed binary64 interval result; and
- hashes that bind the batch and result.

The generated Lean module materializes the same expression, rows, and results
as typed data. Its namespace includes the certificate digest, requested
application bound, and decision mode. This keeps the calculation available for
review, replay, alternate checking, and future migration even though ordinary
downstream proofs consume only the exported theorem.

For registered compact computations, the analogous formula lives in the
closed Lean registry as executable semantics with a stable definition digest.
The certificate selects an existing invocation; it cannot supply arbitrary
Lean code or choose its own proposition.

## Producer workflow

A certificate producer:

1. fixes the formula, canonical inputs, finite coverage, numeric semantics, and
   intended theorem;
2. calculates the interval rows on a CPU or GPU;
3. independently recomputes or validates the rows using exact rational
   binary64 semantics;
4. packages the complete canonical certificate; and
5. generates a deterministic Lean module and receipt.

The checked-in two-row example can be regenerated with:

```bash
mkdir -p build/examples
CERT_DIR="$(mktemp -d build/examples/lean-result-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --decision-mode kernel \
  --output "$CERT_DIR/GeneratedFullCertificate.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/GeneratedFullCertificate.lean"
```

The Python generator refuses a certificate unless its independent exact
recomputation matches every claimed result. The mathematical authority in the
generated theorem is nevertheless the Lean checker and its soundness theorem,
not the Python precheck.

## Publisher workflow

To make a certificate reusable, place the generated source under a valid Lean
module path in a package, build it once, and re-export the digest-bound theorem
under a meaningful API name. Preserve the canonical certificate and generation
receipt alongside it so auditors can reproduce the module.

A wrapper around the checked-in example has this shape:

```lean
import MyProject.Certificates.IntervalSweep

open SparkInterval.GeneratedCertificate.C_b4ba4bc319743cf65a486c216897268e0a98107ea635404fa3f7825305755ba9_B_4010000000000001_M_kernel

/-- Application-facing name for one exact certificate and bound. -/
theorem certifiedApplicationBound
    {i : Nat} (hi : i < certificate.rows.size)
    {x : ℝ} (hx : certificate.RowRealizes i x) :
    x ≤ (applicationUpperBound : ℝ) :=
  application_upper_bound_sound hi hx
```

The generated module also exports
`certificate_sum_upper_bound_sound`, which bounds a finite sum containing one
realized value from every row. Applications should state a domain theorem that
connects their mathematical object to `RowRealizes` or `ValuesRealize`; a
certificate only proves its declared predicate.

The package boundary matters for performance. Lean serializes an elaborated
module environment to `.olean`; importing that current module loads the
serialized environment rather than executing its source commands again. Lake
tracks dependencies and rebuilds the certificate module when its source,
imports, or toolchain-relevant inputs change. See Lean's official
[module documentation](https://lean-lang.org/doc/reference/latest/Source-Files-and-Modules/#elaborated-modules)
and [Lake documentation](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/).

Do not present `.olean` caching as proof by itself. The certificate module must
first be built and checked under a pinned Lean/SparkInterval revision, and a
clean or invalidated build pays that checking cost again. Independent releases
should retain source certificates and receipts rather than distributing only
opaque compiled files.

## Consumer workflow

A downstream proof imports the small application wrapper and applies an
ordinary theorem. It does not need:

- CUDA or the GPU used by the producer;
- the original parallel execution schedule;
- the Python generator at theorem-application time; or
- enough compute to repeat the original discovery calculation.

It does need the compatible compiled Lean dependency, and a clean source build
must be capable of checking that dependency's certificate. This distinction is
the source of the model's build-time advantage: expensive discovery happens
once, certificate verification happens once per invalidated certificate
module, and theorem use can happen many times.

## Kernel mode and `native_decide`

Lean's standard `decide` reduces a `Decidable` proposition, while
`native_decide` (now `decide +native`) evaluates it through compiled code and
admits that native result through an axiom. Native evaluation can be much
faster, but Lean's reference manual notes that it enlarges the trusted base and
that the axiom appears in `#print axioms`. See
[Validating a Lean proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/)
and the
[tactic reference](https://lean-lang.org/doc/reference/latest/Tactic-Proofs/Tactic-Reference/#native_decide).

SparkInterval's generated full certificates expose the choice rather than
hiding it:

| Generated theorem | Default `kernel` mode | `native` mode |
| --- | --- | --- |
| Direct typed certificate, row bound, and finite-sum bound | Checked with `decide_cbv`; recorded theorem dependencies do not include `native_decide` | Checked with `native_decide` |
| Exact canonical JSON, SHA-256, and parser binding | Concrete equality currently uses `native_decide` | Uses `native_decide` |

Therefore the direct typed-data theorem is a genuine current alternative when
a policy rejects `native_decide`: the expensive producer computation is
external, the typed witness is checked by kernel reduction when its module is
built, and downstream code imports the theorem. The tradeoff is that the
current direct theorem proves the mathematics of the materialized Lean data
without also proving that those typed values came from the exact JSON bytes.

Certificate checking does not magically make all large builds cheap. Kernel
reduction over a very large full witness can itself be slow or memory hungry.
The longer-term compact route is meant for computations where storing and
checking every row locally is impractical: a secure measured run returns a
small result for a closed registered checker, and the single execution axiom
bridges accepted evidence to that invocation's proved semantics. The closed
registry and composition theorems exist; the production attestation verifier
and trusted positive-evidence importer do not.

## Relationship to existing Lean approaches

SparkInterval is one point in a useful design space:

| Approach | Where the expensive work happens | What Lean receives | Main tradeoff |
| --- | --- | --- | --- |
| Symbolic theorem or proof-producing tactic | During proof development/elaboration | An ordinary proof term | Strong kernel story and often the best choice, but not every large finite calculation has a compact symbolic proof |
| Kernel `decide` | In Lean reduction when the module is built | Proof from reduction of the decision procedure | Small trust base; large computations can make elaboration and clean builds expensive or fail to reduce well |
| `native_decide` | Compiled native evaluation during elaboration | A theorem with a native-computation axiom dependency | Often much faster, but widens the explicit trust boundary and still runs when that theorem module is rebuilt |
| Domain certificate, such as LRAT | External solver discovers; verified checker replays | A theorem tied to the checked formula/certificate | Excellent when the problem fits the certificate language; requires a sound encoding from the application problem |
| SparkInterval full certificate | CPU/GPU produces interval rows; Lean checks exact interval containment | Reusable row and aggregate bound theorems | Works today and can avoid `native_decide` for direct typed data; complete witnesses can be large |
| SparkInterval compact attested certificate | Measured external CPU/GPU execution | Historical result and registered `Runs` semantics through one axiom | Intended to minimize local checking, but production attestation/import is work in progress and application soundness still needs proof |

Lean's `bv_decide` ecosystem demonstrates the certificate pattern directly:
an external SAT solver can produce an LRAT proof, and `bv_check` reads an
existing LRAT file so a consumer without the solver can verify the result. See
the official
[`bv_decide` API](https://lean-lang.org/doc/api/Lean/Elab/Tactic/BVDecide.html).

Recent Lean work applies the same separation elsewhere:

- [PBLean](https://arxiv.org/abs/2602.08692) imports pseudo-Boolean solver
  certificates, checks them with a proved Boolean checker, and yields
  composable Lean theorems.
- [Automated Tactics for Polynomial Reasoning in Lean 4](https://arxiv.org/abs/2604.13514)
  moves Gröbner-basis discovery to SageMath or SymPy and verifies the returned
  certificate in Lean.
- [LRAT-Catcher](https://arxiv.org/abs/2607.00815) turns externally generated
  SAT certificates into Lean theorems and discusses the time/memory tradeoffs
  between explicit proof terms, kernel reflection, and native reflection.

These projects solve different problems and make different trust/performance
choices. The shared benefit is architectural: expensive discovery can be
optimized independently, while a smaller checker and a verified encoding
determine exactly what theorem is admitted into the formal library.

## Benefits for a shared certificate library

A well-designed certificate library could provide:

- **amortized computation:** many proof developments reuse one expensive finite
  result;
- **hardware independence:** consumers need Lean, not the producer's GPU or
  confidential-computing platform;
- **auditability:** formulas, domains, results, hashes, checker versions, and
  theorem dependencies remain available;
- **stable build boundaries:** application modules depend on a named theorem
  instead of embedding a large calculation in each proof;
- **independent reproduction:** another group can regenerate the result or
  check the same certificate with a different implementation; and
- **precise trust choices:** consumers can select kernel-checked full
  certificates, native reflection, or—when implemented—compact attested
  certificates according to their policy and scale.

The shared public registry is future work. Today, a project can still vendor a
generated certificate module and receipt in its own Lean package and consume
the resulting theorem exactly as described above.
