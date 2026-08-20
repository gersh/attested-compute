# CH25 psi Azure measured DAG

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

The CH25 Lemma 9.2 source computation now has a closed Azure SEV-SNP CPU
materialization path. This is implementation readiness, not completed evidence:
no source-height Azure run, hardware-appraised receipt, or reviewed
`GapSourceScaleEvidence` value is checked into the repository, and the
portfolio semantic row remains disabled.

## Exact job graph

The materializer preserves the existing two-pass campaign instead of treating
it as one opaque command. It creates 644 separately challenged jobs:

| Phase | Jobs | Signed result |
|---|---:|---|
| `initialize` | 1 | retained initialized campaign export |
| `summary-shards` | 320 | retained receipts for one strided group of the 100,000 summary leaves |
| `reduce-summaries` | 1 | retained campaign with the root-derived exclusive scan |
| `verify-shards` | 320 | retained receipts for one strided group of the 100,000 verify leaves |
| `finalize` | 1 | complete retained two-pass campaign and final certificate |
| `semantic-replay` | 1 | literal `true` for `ch25PsiLemma92ProductionV1` |

The first 643 jobs are operational. Their signed result is canonical JSON
containing the SHA-256 and byte length of a deterministic retained-export tar
and the independently replayed retained-tree hash. They deliberately set
`lean_review.registered_invocation` to `null`: the CPU operator still requires
the measured run, SEV-SNP/vTPM appraisal, replay protection, and Managed HSM
signature, but it will not generate a registry or Lean theorem candidate for
an intermediate phase. The terminal is the only registered Lean invocation.

Each downstream materialization requires the exact signed predecessor
receipts from portfolio state and separately supplied export files whose pins
match those receipts. Before packaging the next job it safely extracts every
export and recomputes the complete manifest/tree. The dependencies are:

```text
initialize
  -> 320 summary groups
  -> reduce all 100,000 summary receipts
  -> 320 independent verify groups
  -> finalize all 100,000 verify receipts
  -> semantic replay and literal true
```

## Closed build and command boundary

`tools/tg_azure_cpu_psi_materializer.py` accepts a portfolio handoff and a
site document conforming to
`schemas/azure-cpu-psi-portfolio-materializer-site.schema.json`. The site can
select Azure policy/key paths, the three reviewed upstream roots, and the
exact predecessor exports. It cannot select an executable, command, shell,
algorithm, range, phase dependency, or registered output.

On x86_64 the materializer verifies the complete pinned Git trees for
primesieve and CRlibm and the reviewed Boost 1.83 header tree. It builds a
static primesieve library, builds and tests CRlibm under strict floating-point
flags, and links the arithmetic runner as a static x86-64-v2 ELF. Compiler
dependency output selects the exact Boost headers copied into the retained
source closure. The measured wrapper runs with a pinned copied CPython
executable and `-I`; its dynamic loader, libc, and standard library are part
of the immutable Azure image trust boundary. Exactly one source-closure
manifest receives the receipt's `source_tree` role.

Both the producer and external trace verifier use fixed argv arrays. The
challenge-dependent trace binds phase, group, job, input/handoff, retained
archive, retained tree, and result. No caller string is executed and no shell
is used.

Start from the redacted psi site example and regenerate its predecessor list
for each job:

```bash
python3 tools/tg_azure_cpu_psi_materializer.py plan \
  /operator/portfolio-spec.json \
  ch25-psi-two-pass-v1::initialize 0 \
  /operator/psi-materializer-site.json

python3 tools/tg_azure_cpu_psi_materializer.py materialize \
  /operator/portfolio-spec.json \
  ch25-psi-two-pass-v1::initialize 0 \
  /operator/psi-materializer-site.json
```

The materializer output validates against
`schemas/azure-cpu-psi-portfolio-materialization.schema.json` and remains
`accepted:false`, `execution_completed:false`, and
`lean_theorem_produced:false`. Execute its generated `cpu-campaign.json`
through the CPU production operator, return and appraise the hardware
evidence, issue the signed receipt, then record that receipt in the portfolio.
The retained export is taken from the measured-run package and explicitly
pinned in the next phase's site document.

## Remaining semantic gate

The terminal replay proves that the retained campaign satisfies the campaign
verifier's complete two-pass protocol. It does not by itself establish that
the C++/CRlibm row format constructs the Lean proposition
`GapSourceScaleEvidence`. Before enabling the semantic inventory row, a human
review must check the source-to-Lean refinement: directed logarithm endpoint
semantics, prime-power enumeration and gap completeness, multiplicities,
state constancy between events, and the exact integer boundary guards. Then a
real source-height run and its complete retained receipt chain must be
independently appraised. Until both happen, this path cannot close the proof.

Focused local checks are:

```bash
python3 -m unittest -v \
  tests.test_azure_cpu_psi_materializer \
  tests.test_tg_psi_residual_campaign \
  tests.test_cpu_production_orchestrator \
  tests.test_azure_tg_portfolio
```
