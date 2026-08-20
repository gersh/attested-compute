# Platt head through 20,000: closed Azure measured workload

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

The `platt-head-2e4::single-job` portfolio group now has a closed Azure
SEV-SNP CPU materializer and measured workload. The package is capable of
running the complete finite computation, but this repository does not claim
that an Azure run, hardware appraisal, signed receipt, or Lean admission has
already occurred. The portfolio semantic row remains disabled.

## Exact registered claim

The only accepted invocation is `plattHead2e4ProductionV1`. It fixes:

- source height `20,000` and multiplicity count `22,491`;
- python-flint `0.9.0`, bundled FLINT `3.6.0` / release `30600`, one FLINT
  thread, and 96-bit working precision;
- Q128 scale `2^128`;
- the sentinel-inclusive 22,492-row commitment
  `fc67e829c51adda0804b23b959db33d48e9e1a70076a9caf2ec4d6be96cf29ca`;
- the included 22,491-row source-table commitment
  `e7943dee86b5bf029e9159bd5e54e8726bac14ecaf9a5f42c9b254d98d15a6b7`;
  and
- the literal successful output `true`.

The two commitments are intentionally different. A package containing only
the older sentinel-inclusive digest cannot impersonate the literal Lean
source table.

`tools/tg_platt_head_azure_measured_workload.py` performs, in one measured
job:

1. exact `N(20000)` replay and the required count `22491`;
2. all 22,492 indexed FLINT zero isolations, including the first sentinel
   above the cutoff;
3. a second fresh replay of each of the six retained chunks;
4. final campaign verification and extraction of all exact interval
   preimages;
5. outward Q128 conversion, verification of both reviewed commitments, and
   emission of the literal `PlattHeadQ128.lean` table;
6. a deterministic retained archive; and
7. exclusive emission of `true` only after every preceding check succeeds.

The pinned external trace verifier safely extracts that archive, reloads the
same wheel, freshly replays the count and all six chunks, regenerates the
literal table byte for byte, rechecks the campaign finalization, and verifies
the three-step challenge-bound trace. Thus a successful process exit alone
is insufficient.

## Pinned source and runtime closure

The site document conforms to
`schemas/azure-cpu-platt-head-materializer-site.schema.json`. Its caller may
supply only a pinned base operator site and these three reviewed inputs:

- a clean FLINT checkout at commit
  `8d5454b96761fafe4d5a9da76a369a602f500f49` (`v3.6.0`), whose complete
  10,128-file tracked tree hashes to
  `06b194b828a12c6b6c34d5c1653cadd7d9f3f3356d8f3257a293f9ccf1beade1`;
- a clean python-flint checkout at commit
  `572c8a213a88c0f92feb1bdb938ce4622f4517fa` (`0.9.0`), whose complete
  347-file tracked tree hashes to
  `f5465a668c780dc41e251d94d2b5d7cfc38c742b4b4f4c02b42bdb7804713d0d`;
  and
- the official x86-64 CPython-ABI3 wheel with SHA-256
  `376b88cacd30612479e839ffdba887599d3f9c8c0e214852bf80bb2b194e4d76`.

The materializer verifies both clean Git identities, every tracked byte, the
wheel byte pin, its safe-extraction identity
`ebab958796d833d67b2e282611c3481a7dc624ad2b6f1aedb8d916d8ceb5f1a6`,
the x86-64 ELF type of every extension, and an isolated import reporting
exactly `0.9.0`, `3.6.0`, and `30600`. It carries deterministic full-source
archives, not merely the handful of files listed for convenient human review.
Exactly one closure manifest receives the receipt statement role
`source_tree`, and exactly one copied CPython executable receives
`host_executable`.

The official wheel is an execution binary pin; the materializer does not
claim a reproducible bit-for-bit rebuild of that wheel from the two source
archives. The copied CPython executable also uses the loader, libc, and
standard library in the immutable reviewed Azure image. Those boundaries
must be included in production image and source review.

The site schema contains no executable, shell, or argv field. Workload and
trace argv arrays come only from
`tg_verifier/azure_cpu_platt_head_workload_factory.py`.
The redacted shape is in
`examples/trusted-compute/azure_cpu_platt_head_materializer_site.redacted.json`;
its zero base-site pin is a placeholder and cannot pass validation.

## Package and run

First prepare shard zero through the portfolio controller. On an x86-64
review host, inspect the non-executing plan and materialize the package:

```bash
python3 tools/tg_azure_cpu_platt_head_materializer.py plan \
  /operator/portfolio-spec.json platt-head-2e4::single-job 0 \
  /operator/platt-head-materializer-site.json

python3 tools/tg_azure_cpu_platt_head_materializer.py materialize \
  /operator/portfolio-spec.json platt-head-2e4::single-job 0 \
  /operator/platt-head-materializer-site.json
```

The current aarch64 DGX Spark host is intentionally refused as a production
materialization host. Review `materialization-manifest.json` against
`schemas/azure-cpu-platt-head-materialization.schema.json`, then follow the
CPU operator workflow in `docs/AZURE_CPU_PRODUCTION_OPERATOR.md` using the
emitted `cpu-campaign.json`.

Materialization still reports `accepted:false`. It proves only that a closed,
operator-valid package was built. Completion requires an actual Azure
SEV-SNP run, independent MAA/SEV-SNP/vTPM and transcript appraisal, a
production Managed HSM signature, admission of the exact receipt into the
source registry, review that the executed FLINT realization supports the
Hardy-Z endpoint and Turing/count obligations represented by the registered
Lean relation, and explicit enabling of the semantic binding. Until then,
the computation contributes no theorem to the public capstone.

## Local timing evidence

On 2026-07-22 the current source completed a fresh native aarch64
python-flint 0.9.0 / FLINT 3.6.0 pass from campaign creation through all six
chunks and finalization in about 122 seconds. A separate fresh replay of all
six chunks succeeded, and the emitted 3,080,088-byte Lean module had SHA-256
`45187b8d368c9a8c159dc7305b67a9b940f110ad3f7b4b068d7d069c2c81c8e5`
while reproducing both registered row commitments. The measured workload does
three full isolation passes in total: production, in-process replay, and
external trace replay. A conservative same-throughput expectation is roughly
six to seven minutes plus packaging and evidence collection, well inside its
two-hour job timeout.

That is not an x86 production benchmark. This DGX Spark host is aarch64 and
has no amd64 binary-format emulator, so it cannot load the exact reviewed
x86-64 wheel. The source materializer was smoke-tested through complete
55,879,680-byte FLINT and 3,112,960-byte python-flint archives, exact extracted
wheel identity, all 39 x86-64 extension checks, closure records, and manifest
roles; only the isolated x86 import was necessarily deferred to an x86-64
review/Azure host. Record the actual materialization and measured-job timings
before promotion.

## Focused checks

```bash
python3 -m unittest -v \
  tests.test_azure_cpu_platt_head_materializer \
  tests.test_tg_zeta_zero_campaign \
  tests.test_trusted_compute_registry
```

The focused tests exercise exact invocation hashes, digest separation,
factory routing, schema and CLI closure, corrupt-wheel rejection, measured-job
roles, retained interval authentication, and the registered source-claim
mapping. They are not a substitute for the source-height measured run.
