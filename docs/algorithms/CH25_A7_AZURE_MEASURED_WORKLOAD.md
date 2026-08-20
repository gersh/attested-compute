# CH25 Lemma A.7: closed Azure measured boundary replay

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

The `ch25-a7-boundary::single-job` portfolio group has a closed Azure
SEV-SNP CPU materializer and measured workload. The package can replay the
complete retained finite computation. This is an implementation/readiness
claim only: no Azure execution, hardware appraisal, signed receipt, registry
admission, or capstone theorem is claimed here. The portfolio semantic row is
identity-staged but remains disabled.

## Exact registered claim

The only accepted invocation is `ch25A7BoundaryProductionV1`. It fixes:

- the frontier of `(-3,5) + i(-4,4)`;
- the regularized expression
  `-zeta'(s)/zeta(s) - 1/(s-1) + 1/(s+2)`;
- the target `349/250`;
- all 16,191 retained leaves;
- python-flint `0.9.0`, bundled FLINT `3.6.0` / release `30600`, one
  FLINT thread, series length two, and series cap four;
- the exact 1,494,999-byte artifact with SHA-256
  `ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29`;
  and
- the literal successful output `true`.

The registered hashes are:

| Field | SHA-256 |
| --- | --- |
| algorithm | `340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa` |
| input | `4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674` |
| parameters | `f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e` |
| domain | `629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5` |
| output `true` | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` |

`tools/tg_a7_azure_measured_workload.py` rejects any different input,
artifact, wheel, version, report shape, or result. It safely extracts the
pinned wheel, performs `replay_a7_flint(...,
require_retained_identity=True)`, and writes `true` exclusively after it has:

1. rechecked the exact four-edge dyadic cover;
2. recomputed every FLINT/Arb zeta jet and all 16,191 output boxes;
3. checked the pole and zeta-nonvanishing guards;
4. matched every fresh exact dyadic evidence endpoint;
5. rechecked the strict squared-norm bound; and
6. retained a canonical normalized replay report.

The external work-trace verifier loads a fresh runtime, repeats the complete
16,191-leaf replay, requires byte-identical normalized evidence, and verifies
the three-step challenge-bound trace. Thus a successful first process exit or
a self-authored `true` file is insufficient.

## Pinned source, artifact, and runtime closure

The site document conforms to
`schemas/azure-cpu-a7-materializer-site.schema.json`. Its caller may supply
only a pinned base operator site and these four reviewed inputs:

- the exact retained A.7 artifact above;
- a clean FLINT checkout at commit
  `8d5454b96761fafe4d5a9da76a369a602f500f49` (`v3.6.0`), whose complete
  10,128-file tree hashes to
  `06b194b828a12c6b6c34d5c1653cadd7d9f3f3356d8f3257a293f9ccf1beade1`;
- a clean python-flint checkout at commit
  `572c8a213a88c0f92feb1bdb938ce4622f4517fa` (`0.9.0`), whose complete
  347-file tree hashes to
  `f5465a668c780dc41e251d94d2b5d7cfc38c742b4b4f4c02b42bdb7804713d0d`;
  and
- the reviewed x86-64 CPython-ABI3 wheel with SHA-256
  `376b88cacd30612479e839ffdba887599d3f9c8c0e214852bf80bb2b194e4d76`.

The materializer performs the artifact's complete structural review before
copying it. It also verifies both clean source trees, every tracked byte, the
wheel and its extracted-tree identity
`ebab958796d833d67b2e282611c3481a7dc624ad2b6f1aedb8d916d8ceb5f1a6`,
all x86-64 ELF extensions, and an isolated import reporting exactly `0.9.0`,
`3.6.0`, and `30600`. It carries deterministic full-source archives and an
A.7 source envelope. Exactly one closure record has statement role
`source_tree`, and exactly one copied CPython executable has
`host_executable`.

The wheel remains a reviewed binary pin, not a claimed reproducible rebuild
from the carried sources. The copied CPython executable uses the loader,
libc, and standard library in the reviewed Azure image. Production review
must include those disclosed boundaries.

The site schema contains no executable, shell, environment, or argv field.
Both measured argv arrays come only from
`tg_verifier/azure_cpu_a7_workload_factory.py`. The redacted shape is in
`examples/trusted-compute/azure_cpu_a7_materializer_site.redacted.json`; its
zero base-site pin is deliberately unusable.

## Package and run

Prepare shard zero through the portfolio controller. On an x86-64 review
host, inspect the plan and then materialize:

```bash
python3 tools/tg_azure_cpu_a7_materializer.py plan \
  /operator/portfolio-spec.json ch25-a7-boundary::single-job 0 \
  /operator/a7-materializer-site.json

python3 tools/tg_azure_cpu_a7_materializer.py materialize \
  /operator/portfolio-spec.json ch25-a7-boundary::single-job 0 \
  /operator/a7-materializer-site.json
```

The current aarch64 DGX Spark host is refused as a production materialization
host. Review `materialization-manifest.json` against
`schemas/azure-cpu-a7-materialization.schema.json`, then use the emitted
`cpu-campaign.json` with `docs/AZURE_CPU_PRODUCTION_OPERATOR.md`.

Materialization reports `accepted:false`: it creates an operator-valid
package but no execution evidence. Completion still requires the production
Azure run, independent MAA/SEV-SNP/vTPM and transcript appraisal, a Managed
HSM signature, source-registry admission, and explicit semantic-binding
review and enablement.

The disabled inventory row records
`ch25A7BoundaryProductionV1`,
`ch25A7BoundarySourceClaimV1`, and
`RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim`. The portable
terminal command writes the exact no-newline bytes `true` only after a full
pinned replay, using `tools/tg_verify.py::_write_a7_registered_result`, at
`${TG_RUN_ROOT}/ch25-a7-boundary/registered-result.txt`. Exclusive creation
prevents a stale result from being reused. These staged identities are not
authority: the realization remains only in `PENDING_TG_REALIZATIONS`, the
production deployment pin is `none`, the source registry is empty, and the
semantic row is `enabled:false`.

## The analytic boundary remains explicit

The external FLINT replay is complete, but it is not an ordinary-kernel Lean
proof of FLINT/Arb. `A7BoundaryCertificate.AnalyticRealization` is the exact
remaining mathematical refinement statement: for every retained dyadic leaf,
the stored lower endpoint bounds Mathlib's `riemannZeta`, and the stored upper
endpoint bounds the exact `rawG` expression. Ordinary Lean proves that the
transparent integer checker, this realization statement, and the explicit
pole guards imply the source claim.

The registered `Runs` relation deliberately includes one existential
transcript-shaped certificate, `certificate.check = true`, and a nonempty
`AnalyticRealization certificate`. Admitting a successful measured receipt
through `accepted_run_certificate_sound` therefore trusts the reviewed
measured program as an implementation of exactly that relation. It does not
require a local build to contain or evaluate the 16,191-leaf production
certificate. Enabling the semantic row without reviewing the
FLINT-to-Mathlib interpretation would overstate what the finite bytes alone
establish. The workload itself reports
`mathlib_zeta_realization_theorem_present:false` and
`lean_atom_discharged:false` to keep that distinction machine-visible.

## Total finite-wire parser

The retained JSON now has a deterministic compact projection for Lean:
`TGA7WIR1`.  Its 144-byte header pins the source transcript and canonical
seven-field leaf array, and each 88-byte record preserves exactly

```text
edge, depth, index,
norm-square-upper mantissa/exponent,
zeta-absolute-lower mantissa/exponent.
```

The compact profile allows 256-bit positive mantissas and signed exponents
from -16,384 through 16,384.  The retained data use at most 192 mantissa bits;
the norm exponents range from -196 to -178 and the zeta exponents from -198
to -182.  Thus the fixed-width projection does not truncate a retained
integer.

For the retained 16,191-leaf transcript, the wire is 1,424,952 bytes with:

| Object | SHA-256 |
| --- | --- |
| canonical JSON leaf array | `abac27f61cb8ce53f649cb0c2111c123c761a37793a1bc536033981c215cabef` |
| fixed-width record payload | `f2893e9488df7353c31f7d647948b697eb2c88f331b7ea4405c9e328f974148c` |
| complete `TGA7WIR1` wire | `1ea01e78e29143ecfef926faac7b788c2d4dc9dd6240b7d0b401e7f62fa9de4c` |

`tg_verifier/a7_boundary_wire.py` first invokes the authoritative JSON
validator and then emits the wire.  Its separate binary decoder rechecks
layout, all hashes, bounded integers, exact dyadic inequalities, canonical
ordering, and four gap-free covers.  A review-only materialization is:

```bash
python3 tools/tg_a7_boundary_wire.py \
  --input "$CLAUDE_MATH_ROOT/ext/ch25_certificates/certificates/a7_boundary.json" \
  --output /review/a7_boundary.tga7wir1
```

`SparkInterval/TernaryGoldbach/A7BoundaryWire.lean` independently parses the
fixed-width format as a total function.  It requires exact formulaic length,
so truncation and appended bytes fail closed; checks the payload SHA-256;
decodes every record; and feeds the resulting list to
`A7BoundaryCertificate.Certificate.check`.  `checkRetainedBytes` additionally
pins the exact source, leaf-array, payload, and whole-wire identities.
`exactLength_of_checkBytes`, `acceptedCertificate_of_checkBytes`, and
`checkRetainedBytes_sound` state the finite results in ordinary Lean.

The cross-language test uses a Python-emitted 496-byte fixture and mutates
magic, count, payload, digest, truncation, and suffix bytes.  Python tests also
repair the payload digest after semantic mutations and confirm that topology,
strict-bound, positivity, index, and exponent checks still reject them.

This closes the byte-parser gap for the retained **finite seven-field
transcript**, not the analytic gap.  The wire deliberately contains no proof
that FLINT/Arb enclosures realize Mathlib's functions.
`sourceClaim_of_checked_retained_wire` therefore still requires the same
explicit `AnalyticRealization`; it does not turn finite bytes or their hashes
into the source theorem.

## Retained timing evidence and cloud-only production

On 2026-07-22 a fresh native aarch64 python-flint/FLINT replay checked all
16,191 leaves in about 1.56 seconds and reproduced leaf digest
`abac27f61cb8ce53f649cb0c2111c123c761a37793a1bc536033981c215cabef`.
The measured job performs two full replays, so computation should remain a
matter of seconds; its conservative timeout is 30 minutes to leave ample
operational margin.

That historical timing measurement is not a request to repeat the production
replay during development. Ordinary local validation is limited to symbolic
Lean compilation, static binding checks, and tiny certificates. Both complete
FLINT passes belong inside the measured Azure job. After appraisal, the local
handoff checks only the compact signed receipt and source-pinned identities;
it does not open the production transcript or redo its arithmetic.

The full materializer path was smoke-tested through a 55,879,680-byte FLINT
archive, a 3,112,960-byte python-flint archive, the exact artifact, 39 x86-64
wheel extensions, 19 closure records, and the unique statement roles. The
only deferred check was importing the x86-64 wheel on this aarch64 host; the
materializer performs that check and fails closed on its required x86-64
review/Azure host.

## Focused checks

```bash
python3 -m unittest -v \
  tests.test_a7_boundary_wire \
  tests.test_a7_lean_certificate \
  tests.test_azure_cpu_a7_materializer \
  tests.test_azure_tg_portfolio \
  tests.test_tg_semantic_bindings \
  tests.test_trusted_compute_invocation_catalog \
  tests.test_trusted_compute_registry

./tools/safe_lean.sh \
  SparkInterval/Tests/A7BoundaryWireTest.lean

./tools/safe_lean.sh \
  SparkInterval/Tests/RegisteredA7BoundaryCertificateTest.lean
```

These checks cover exact registered hashes, group routing, schema and CLI
closure, corrupt-artifact rejection, measured-job statement roles, and a
forced second complete trace replay. They do not substitute for the x86-64
materialization, production attestation, or semantic review.
