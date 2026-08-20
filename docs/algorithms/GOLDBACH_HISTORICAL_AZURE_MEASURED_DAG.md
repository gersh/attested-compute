# Historical Goldbach Azure measured DAG

> **⚠ Never validated on hardware.** No Azure run has ever been performed.
> There is no `az` CLI, no `~/.azure`, and no subscription in this environment;
> `tests/data/` contains retained evidence for Intel TDX runs only, and
> `attestation/verify_azure_ncc_evidence.py` currently fails at import. The
> Azure backend is a design, not a working path — treat everything below as a
> specification that has not been executed. The supported path is Intel TDX:
> see [`../../attestation/phala/README.md`](../../attestation/phala/README.md).

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

The source-height Helfgott--Platt reconstruction has closed Python
materialization paths for all 8,192 H100 producer groups, all six operational
CPU phase types, and the registered CPU terminal. This is executable
infrastructure, not a completed verification:

- no source-scale H100 or CPU campaign has run;
- no production receipt, terminal commitment, or terminal result is shipped;
- the registered Lean pins remain unconfigured;
- the Azure semantic-binding inventory remains disabled; and
- no production build admission, measured image, appraiser policy, or signing
  key has been reviewed and installed for this campaign.

The historical H100 route is now campaign-specific rather than a generic
operator placeholder. Its independently derived execution projection fixes
the exact job, command and trace arguments, output contract, runtime profiles,
GPU gate, immutable-image closure, and per-group domain before the signed
receipt is accepted.

## Closed CPU workload types

`tg_verifier/azure_cpu_goldbach_historical_operational_workload_factory.py`
recognizes exactly the corresponding phase rows in
`helfgott-platt-goldbach-gpu-v1`:

| Phase | Jobs | Signed predecessors |
| --- | ---: | ---: |
| `create-production-plan` | 1 | 0 |
| `initialize-prime-ladder` | 1 | 0 |
| `native-prime-ladder-range-groups` | 320 | 1 initializer each |
| `aggregate` | 1 | plan plus all 8,192 H100 groups |
| `binary-semantic-replay` | 1 | aggregate |
| `reduce-prime-ladder-ranges` | 1 | all 320 ladder groups |

Thus the operational CPU route contains 326 measured jobs. The terminal is a
separate 327th CPU job and depends on the final binary replay and ladder
reduction.

Every operational materializer:

1. requires the exact portfolio group, command, dependency shape, shard count,
   backend, owner atom, and nonterminal status;
2. loads every predecessor through the source-pinned trusted-compute receipt
   verifier;
3. verifies the predecessor's deterministic retained-export archive;
4. packages a no-shell measured job with pinned source, runtime, target,
   trust, runner-policy, verifier-key, build-admission, and GMP closure;
5. runs the reviewed phase in an isolated retained tree;
6. signs a canonical result that pins the archive and its content-addressed
   tree; and
7. independently replays the challenge work trace.

The native ladder result additionally places the ordered ordinary and native
receipt hash vectors in the signed result. This is deliberate: the final
terminal can bind every one of the 492,700 raw range receipts and native
producer receipts without carrying another 320 duplicate retained archives.

The site schema is
`schemas/azure-cpu-goldbach-historical-operational-materializer-site.schema.json`.
The output-manifest schema is
`schemas/azure-cpu-goldbach-historical-operational-materialization.schema.json`.
The operator adapter is:

```bash
python3 tools/tg_azure_cpu_goldbach_historical_operational_materializer.py \
  plan PORTFOLIO_SPEC GROUP_ID SHARD_INDEX SITE

python3 tools/tg_azure_cpu_goldbach_historical_operational_materializer.py \
  materialize PORTFOLIO_SPEC GROUP_ID SHARD_INDEX SITE
```

`plan` does not execute the computation. `materialize` builds a measured
workload package; it is also not execution evidence. The emitted
`cpu-campaign.json` is the input to the stateful Azure CPU production
operator.

## Closed H100 producer groups

`tg_verifier/azure_h100_goldbach_historical_workload_factory.py` recognizes
only the exact historical H100 phase. Group `g` runs the eight immutable
checkpoint leaves `g + k*8192` for `0 <= k < 8`. The campaign-specific
materializer:

1. verifies the signed CPU plan predecessor and its retained export;
2. requires an exact reviewed build admission for Python, NVCC, the host
   compiler, hardened Goldbach source, executable, profiles, policies, and
   immutable runtime image;
3. derives the measured-job execution projection independently from the
   signed result and includes its digest in the algorithm definition;
4. packages the exact no-shell H100 command and independent trace replay;
5. retains exactly the group's eight canonical leaf receipts; and
6. exports that archive only after the signed H100 result, portfolio
   challenge, projection, and every retained leaf hash agree.

The site and output schemas are
`schemas/azure-h100-goldbach-historical-materializer-site.schema.json` and
`schemas/azure-h100-goldbach-historical-materialization.schema.json`. The
operator adapter is:

```bash
python3 tools/tg_azure_h100_goldbach_historical_materializer.py \
  plan PORTFOLIO_SPEC GROUP_ID SHARD_INDEX SITE

python3 tools/tg_azure_h100_goldbach_historical_materializer.py \
  materialize PORTFOLIO_SPEC GROUP_ID SHARD_INDEX SITE

python3 tools/tg_azure_h100_goldbach_historical_materializer.py \
  export MATERIALIZATION_MANIFEST SIGNED_RECEIPT KEY_MANIFEST OUTPUT
```

As on the CPU route, `plan` and `materialize` are packaging operations, not
execution evidence. The emitted H100 campaign configuration must still be run
by the production operator and independently appraised.

## Retained exports and the terminal handoff

The final binary replay export has:

```text
payload/
  binary-plan.json
  binary-receipts/          # exactly 65,536 leaf receipts
  binary-aggregate.json
```

The final ladder reduction export has:

```text
payload/
  prime-ladder/
    manifest.json
    independent-receipts/   # exactly 492,700 ordinary receipts
    native-producer-receipts/
    ladder-aggregate.json
    ...
```

The registration helper transactionally maps those exports and dedicated
directories of signed producer receipts to the terminal layout:

```bash
python3 tools/generate_goldbach_historical_terminal_registration.py assemble \
  --binary-replay-export /retained/binary-replay.tar \
  --ladder-reduce-export /retained/ladder-reduce.tar \
  --h100-receipts-root /retained/signed-h100-groups \
  --ladder-receipts-root /retained/signed-ladder-groups \
  --handoff-root /terminal/handoff-tree \
  --key-manifest /reviewed/trusted_compute_keys.json \
  --build-admission /reviewed/goldbach-build-admission.json \
  --commitment-output /terminal/child-commitment.json \
  --archive-output /terminal/handoff.tar
```

The two receipt directories are dedicated, exact sets named
`receipt-00000000.json`, and so on. There must be 8,192 H100 receipts and 320
ladder receipts with no extra entry. Before any output is published, the
assembler:

- validates both retained-export manifests;
- enforces their exact top-level payload shapes;
- constructs the canonical 8,512-entry child index;
- verifies every child signature and exact algorithm/profile identity;
- replays the complete binary and ladder aggregates;
- compares every signed H100 hash to its eight raw binary leaf receipts;
- compares every signed ladder hash to its raw ordinary and native range
  receipts; and
- computes the immutable branch and child-identity commitment.

Publication is transactional. A failed validation removes the staged tree and
any commitment/archive created by that attempt.

The terminal site then pins the resulting archive, commitment, and build
admission for
`tools/tg_azure_cpu_goldbach_historical_materializer.py`. The measured
terminal independently repeats all signature, raw-artifact, aggregate, and
combined-source checks before writing the literal registered result `true`.

## Trust and review boundary

The terminal commitment is transitive at the byte/hash level:

```text
signed H100 group results ─┐
                           ├─> exact raw branch receipts ─> branch replay
signed ladder group results┘
                                      |
                                      v
8,512 signed child identities + branch summary
                                      |
                                      v
terminal artifact closure + measured CPU receipt
                                      |
                                      v
registered invocation (only after reviewed pins are installed)
```

This does not make Azure attestation a proof of CUDA, GMP, Python, compiler,
or CPU semantics. The sole trusted-compute axiom accepts a specifically
reviewed signed run. Human review must still cover the measured image,
source/build admission, target and trust profiles, appraiser roots and policy,
Managed HSM key, terminal pin candidate, and the ordinary Lean theorem that
interprets the registered result.

## Deferred verification

The Python/schema tests are:

```bash
PYTHONPATH="$PWD:$PWD/tools:$PWD/attestation:$PWD/azure" \
  python3 -m unittest \
    tests.test_azure_h100_goldbach_historical_materializer \
    tests.test_goldbach_historical_operational \
    tests.test_goldbach_historical_terminal -v
```

Lean checks for the terminal pins, registered-algorithm gate, execution import,
and registered Goldbach certificate test must be run after the shared Lean
proof lane is free. They are intentionally not implied by the Python test
result.
