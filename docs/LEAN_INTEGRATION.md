# Using computation certificates from Lean

SparkInterval's full result certificates are usable as Lean theorems today.
The separate compact Azure path now has evidence collection, independent
appraisal plumbing, signed receipt issuance, a source-pinned registry
generator, and a generated Lean consumer. Its tracked receipt registry is
empty: no production Azure run has been admitted. A public certificate service
also remains future work.

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

### Cross-repository theorem handoff

Lean theorem objects are not a version-neutral interchange format.  In
particular, a downstream project must not copy an `.olean` built with a
different Lean or Mathlib revision and treat that file as a certificate.  A
clean public handoff uses source modules under one Lake dependency graph:

1. pin the producer repository at an immutable reviewed commit and align its
   Lean and Mathlib revisions with the consumer;
2. build the receipt registry, generated receipt module, registered invocation
   semantics, and application soundness theorem from source in that same Lake
   environment;
3. import the generated application theorem in a small downstream adapter;
4. prove, definition by definition, that the producer's source-shaped result
   is the consumer's live proposition; and
5. audit the concrete capstone with both `#audit certificates` and
   `#print axioms`.

The generated receipt theorem, rather than a copied Boolean or a restated
axiom, is the premise of the downstream adapter.  The adapter may repeat a
small source-normal-form proposition temporarily when the repositories are on
incompatible revisions, but that is only a conditional API: it does not retire
the consumer's external atom until the compatible dependency and concrete
receipt theorem are imported.  Once connected, the only project execution
axiom reachable from the concrete theorem should remain
`accepted_run_certificate_sound`; arithmetic reductions and identification of
the consumer definitions are ordinary Lean theorems.

The current Hurst V2 scaffold implements the conditional half of this split as
`TGComputeContracts.HurstV2`.  `gpu_prover` and `claude_math` compile identical
source bytes for that axiom-free contract under their respective pins, and the
producer proves the shared `RealSourceClaims` type from its exact campaign
certificate.  This is **not** the completed receipt handoff: it supplies a
stable proposition, not evidence that a production run occurred.

End-to-end retirement has two acceptable migration paths.  Either align the
repository pins and import the actual `gpu_prover` generated receipt theorem
from source, or extract the minimal receipt decoder/generator and **move**
`accepted_run_certificate_sound` into the shared package.  The latter must
remove the producer-local declaration rather than duplicate it.  In both
cases, the concrete downstream theorem must audit to the same single execution
axiom plus Lean/Mathlib's foundational axioms; adding a convenient second axiom
to the contract package is forbidden.

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
algorithm registry and composition theorems exist. The Azure collector,
independent-appraisal adapter, signed receipt, source-registry generator, and
Lean consumer also exist, but no production appraiser/key/run/receipt ships as
accepted evidence. Attestation must be paired with a reviewed measured runner;
it does not prove arbitrary user-space causality.

## Compact trusted-compute import

The compact route deliberately has no signature-verification oracle inside
Lean. A relying party first runs the exact hash-pinned Azure/NVIDIA appraisers,
then signs the normalized receipt with a production key. A maintainer adds that
key, its public-key hash, and every approved exact
`(backend, target profile SHA-256, trust profile SHA-256, verifier artifact
SHA-256, appraisal policy SHA-256)` tuple to
[`trusted_compute_keys.json`](../profiles/verifier_keys/trusted_compute_keys.json)
as `production`, adds the identical classified tuples to the reviewed Lean
allowlist, reviews its
Managed HSM key-attestation record out of band according to the
[Managed HSM signing guide](AZURE_MANAGED_HSM_SIGNING.md), and generates the
source registry:

```bash
python3 tools/generate_trusted_compute_registry.py \
  /path/to/receipt.json \
  --out SparkInterval/Execution/TrustedComputeRegistry.lean
git diff -- SparkInterval/Execution/TrustedComputeRegistry.lean

mkdir -p build/trusted-compute
python3 tools/generate_trusted_compute_lean.py \
  /path/to/receipt.json \
  --namespace ReviewedAzureRun \
  --out build/trusted-compute/ReviewedAzureRun.lean
./tools/safe_lean.sh build/trusted-compute/ReviewedAzureRun.lean
```

The generated module imports
`SparkInterval.Audit.TrustedComputeCertificates` and finishes with:

```lean
#audit certificates producedOutcome
```

The generated `producedOutcome` calls
`acceptedRunCertificateForReceipt` with a literal 64-character lowercase
receipt digest. Its separate equality argument is checked by Lean's kernel and
forces that literal to equal the hash selected by
`certificate.attestation`. The wrapper then invokes the same sole
`accepted_run_certificate_sound` axiom; there is still one project execution
axiom, not one axiom per receipt.

For interactive inspection, `#print certificates producedOutcome` emits the
receipt SHA-256, the wrapper declaration, the transitive proof path, the full
root-axiom set, and stable machine-readable records. It reports `COVERED` only
when every path to the execution axiom has a closed canonical receipt wrapper.
`AXIOM_FREE` means that axiom is unreachable. `FAIL_UNATTRIBUTED` means a path
uses the generic boundary without a concrete valid wrapper, while
`FAIL_UNEXPECTED_AXIOMS` means the theorem depends on an undisclosed axiom.
The `#audit` form prints the report and then fails for either failure status.

This distinction is intentional for reusable conditional APIs. For example,
a theorem parameterized by a proof that `checkTrustedCompute ... = true` can
legitimately be generic and therefore print `FAIL_UNATTRIBUTED`; it is not yet
evidence of an accepted run. A receipt-specific generated theorem must cross
the hash-binding wrapper and pass `#audit certificates` before being described
as concrete. The live registry is currently empty, so this repository ships
no `COVERED` production theorem.

The registry generator verifies canonical JSON, the source-pinned RSA-3072
signature, the key-specific exact backend/target-profile/trust-profile/
verifier/policy tuple, current
appraisal validity, exact backend/claim class, and duplicate
receipt, run, challenge, statement, and result-binding identities. It refuses
an empty registry unless `--allow-empty` is explicit and refuses the bundled
development key unless `--allow-development-key` is explicit. That flag is for
fixture parsing/source generation only: the Lean production checker
unconditionally rejects every `development` issuer profile.

There is no wildcard issuer profile. A synchronization regression test keeps
the JSON manifest and Lean tuple list identical, and `checkTrustedCompute`
rechecks the tuple so an accidental hand-edited registry entry cannot silently
change the approved workload profiles, appraiser, or policy.

The generated `accepted` theorem uses ordinary kernel reduction to check exact
receipt lookup and complete structural binding. The Lean Boolean also
recomputes the SHA-256 binding from result bytes to `outputHash` and the
challenge/wire-statement binding to `resultBindingHash`; those two equations no
longer rely only on the Python importer. Its `producedOutcome` theorem then
crosses the one project execution axiom,
`accepted_run_certificate_sound`. This yields an exact historical result and,
only for a matching constructor of the closed `RegisteredInvocation` type, its
fixed `Runs` semantics. An application theorem still follows from a separately
proved Lean theorem about those semantics; neither the signature nor the axiom
lets a receipt choose an arbitrary proposition.

The certificate audit examines proof terms and root axioms; it does not verify
the external signature or hardware evidence. Lean deliberately performs no
RSA oracle call on this compact path. A hand edit that admits a registry entry
therefore changes an external fact trusted by the sole execution axiom and is
trust-equivalent at that boundary. The printed digest and path make the exact
admission easy to locate and review, but do not reduce that trust. Separately,
`#audit project axioms` fails unless the named run-certificate axiom is the
only project axiom in the imported kernel environment; import the complete
project surface when using it as a repository gate.

For project-wide receipt discovery, `#print project certificates` lists every
loaded concrete hash/anchor site and every direct caller of the sole axiom.
`#audit project certificates` additionally fails for malformed sites,
unreviewed direct callers, uncovered concrete anchors, or unexpected project
axioms. The checked repository gate runs it from the aggregate Execution API
environment via `SparkInterval/Tests/ProjectCertificateAudit.lean`; the
machine-readable summary is `project-certificate-audit-v1`.

## Relationship to existing Lean approaches

SparkInterval is one point in a useful design space:

| Approach | Where the expensive work happens | What Lean receives | Main tradeoff |
| --- | --- | --- | --- |
| Symbolic theorem or proof-producing tactic | During proof development/elaboration | An ordinary proof term | Strong kernel story and often the best choice, but not every large finite calculation has a compact symbolic proof |
| Kernel `decide` | In Lean reduction when the module is built | Proof from reduction of the decision procedure | Small trust base; large computations can make elaboration and clean builds expensive or fail to reduce well |
| `native_decide` | Compiled native evaluation during elaboration | A theorem with a native-computation axiom dependency | Often much faster, but widens the explicit trust boundary and still runs when that theorem module is rebuilt |
| Domain certificate, such as LRAT | External solver discovers; verified checker replays | A theorem tied to the checked formula/certificate | Excellent when the problem fits the certificate language; requires a sound encoding from the application problem |
| SparkInterval full certificate | CPU/GPU produces interval rows; Lean checks exact interval containment | Reusable row and aggregate bound theorems | Works today and can avoid `native_decide` for direct typed data; complete witnesses can be large |
| SparkInterval compact attested certificate | Measured external Azure SEV-SNP CPU or composite Azure NCC H100 execution | Source-admitted historical result and registered `Runs` semantics through one axiom | Tooling is implemented but the tracked registry is empty; production appraisers, key custody/attestation, measured-runner policy, a real run, registry review, and application soundness are still required |

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
  certificates, native reflection, or source-admitted compact attested
  certificates according to their policy and scale.

A hosted shared public registry is future work. Today, a project can vendor a
generated full-certificate module or review compact receipts into its own
source registry and consume the resulting theorem exactly as described above.
