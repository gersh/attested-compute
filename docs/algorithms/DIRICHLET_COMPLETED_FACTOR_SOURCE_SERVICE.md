# Completed-factor source artifact service

`tg_verifier/dirichlet_completed_factor_service.py` prepares the completed
Dirichlet-\(L\) factors used by the resident q-major pipeline without
materializing a q-by-t table. The service is source-shaped and exact, but it
is not itself a source run or a proof.

## Fixed work graph

The service accepts only the canonical primitive-V2 `TGDQORD1` manifest:

- 292,500 active moduli in the closed range \(10001\le q\le400000\);
- manifest SHA-256
  `a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93`;
- source-roster SHA-256
  `d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c`;
- execution-order SHA-256
  `34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd`.

Initialization freshly invokes `build_stream_plan` for all ten exact resident
phases and obtains each projected q/sample roster from
`phase_schedule_projection`. The resulting work graph has twelve jobs:

1. one gamma artifact with both parity rows for all 127,988 t indices;
2. one conductor-step disk for every q in canonical execution order; and
3. one direct-conductor-checkpoint artifact for each of the ten phases.

The validated compact geometry table is persisted in `source-plan.json`.
Subsequent shared-job commands check it against the independent pins without
reiterating all ten 292,500-record projections. A phase command reconstructs
the exact q/sample roster for only its selected phase. Initialization remains
the full ten-phase audit path.

The phase bounds are

```text
[0,768) [768,1600) [1600,2368) [2368,3200) [3200,4032)
[4032,5568) [5568,9600) [9600,49088) [49088,88512)
[88512,127988)
```

Each phase job binds the full q-manifest digest, execution-order digest,
resident phase-plan digest, phase-schedule digest, q count, t-row count,
checkpoint count, factor convention, precision, and pinned Arb producer
identity. A separate planner identity hashes the service, q scheduler,
resident phase-plan, and resident stream sources and is included in the plan,
every job, and every receipt. The checkpoint artifact additionally binds the
exact generated gamma and step artifact hashes.

The compact representation is exactly 101,834,360 bytes at checkpoint span
4096, versus 174,605,432,016 bytes for the unused parity-major q-by-t disk
table.

## Operator workflow

First create the canonical q manifest and the immutable plan. Planning does
not evaluate gamma functions, logarithms, or exponentials.

```bash
python3 tools/tg_dirichlet_allchars_q_scheduler.py \
  source-manifest /work/q-order.tgdqord1

python3 tools/tg_dirichlet_completed_factor_service.py init \
  /work/completed-factors \
  --schedule-manifest /work/q-order.tgdqord1 \
  --precision 384
```

Generate each shared catalog once:

```bash
python3 tools/tg_dirichlet_completed_factor_service.py run-gamma \
  /work/completed-factors --execute-full-source-artifact-job

python3 tools/tg_dirichlet_completed_factor_service.py run-steps \
  /work/completed-factors --execute-full-source-artifact-job
```

After both shared jobs validate, phase jobs 0 through 9 are independent and
may run on separate CPU workers:

```bash
python3 tools/tg_dirichlet_completed_factor_service.py run-phase \
  /work/completed-factors --phase-index 7 \
  --execute-full-source-artifact-job
```

Every job publishes by atomically renaming a staging directory containing
both `artifact.bin` and `receipt.json`. Repeating a completed command validates
and returns the existing immutable result. An interrupted worker leaves only
an ignored staging directory, so another worker can rerun that job. `status`
reports the count of such staging entries but does not delete them.
Before publication, the artifact file and staging directory are fsynced.
Phase workers also reopen and revalidate both shared artifacts immediately
before the phase directory is published and again before success is returned.

```bash
python3 tools/tg_dirichlet_completed_factor_service.py status \
  /work/completed-factors

python3 tools/tg_dirichlet_completed_factor_service.py status \
  /work/completed-factors --require-complete
```

The explicit execution acknowledgement prevents an accidental full artifact
job from a planning or inspection command.

## Validation and bounded timing

On the local DGX Spark host on 2026-07-25, with python-flint 0.9.0 / FLINT
3.6.0 and 384-bit Arb precision:

- exact twelve-job initialization took 15.32 seconds and generated no Arb
  artifacts; a fresh process then revalidated the pending service status in
  3.49 seconds using the persisted pin-checked geometry;
- a terminal 4,096-sample, one-q bundle generated and replayed 8,192 gamma
  disks, one step disk, and one checkpoint disk in 0.35 seconds including
  Python startup;
- a bounded phase-7 sample of 16,384 execution-order q records generated
  75,434 direct checkpoint disks in 2.04 seconds, about 37,062
  checkpoints/second; the artifact was replayed after the timed region.

The last rate gives an informal one-core projection near 64 seconds for all
2,351,903 checkpoint disks. It is not a source execution measurement. The ten
phase jobs can run concurrently, and gamma and steps are generated only once.
No full artifact generation was launched for this benchmark.

Focused tests are:

```bash
python3 -m unittest -v \
  tests.test_tg_dirichlet_completed_factor_artifacts \
  tests.test_tg_dirichlet_completed_factor_service
```

The service tests reconstruct all ten exact plan and phase commitments,
exercise atomic/idempotent publication with explicitly nonanalytic unit-disk
writers, reject repaired-hash plan changes, reject artifact mutation, and run
the existing bounded real-Arb producer KAT when pinned python-flint is
available.

## Lean production artifact checker

`SparkInterval/Dirichlet/CompletedFactorStreamingWire.lean` checks the same
source-shaped headers, roster, geometry, cross-artifact hashes, and optional
complete-artifact pins as the materializing reference checker. Its executable
path walks each 24-byte disk and checkpoint record once. It retains headers,
counters, the required expected roster, and one modulus hash set, but no
parsed disk or checkpoint-record list. Separate proved tail-recursive passes
replace the former list sort, generic `Nodup` decision, and `List.sum`.
Successful acceptance derives the existing
`FullSourceExpectations.IsValid` proposition, the exact ordered checkpoint
roster relation, and validity of every encoded disk.

Bounded `lean --run` qualification accepted 2,351,903 disks (56,445,672
bytes) in 28.74 seconds, 292,500 checkpoint rows with 292,500 disks in 9.00
seconds, and the complete 292,500-row roster aggregate/freshness pass in 3.35
seconds. These timings include Lean frontend startup and are local
measurements, not native-executable, Azure, or source-run evidence. The
materializing reference parser remains available for small independent
fixtures.

## Trust boundary

The receipts prove only internal file consistency to the Python validator.
They are not cryptographic attestations that Arb ran, and a party able to
replace the program and all unsigned files can fabricate them. They must
therefore be treated as inputs to the later measured/attested execution and
Lean bridge, not as substitutes for that boundary.

The compatible v1 step and checkpoint binary headers do not contain a
producer-identity field. Their producer binding is deliberately transitive:

1. the plan binds the Arb producer identity and planner identity;
2. each self-hashed job and receipt binds those identities and the exact
   artifact SHA-256;
3. the gamma binary carries the same producer identity directly; and
4. each checkpoint binary carries the exact gamma and step artifact hashes.

Consequently, a step or checkpoint binary by itself does not establish a
producer identity. Auditors must keep the plan, receipts, gamma artifact, and
bundle cross-hashes together. The structural test suite exercises this chain
and rejects a repaired receipt hash with a substituted dependency.
The service receipts are self-hashed, not signed. A later enclave/measured-run
receipt must cryptographically commit the service plan hash, job receipt
hashes, and exact artifact hashes before this transitive chain can cross the
trusted-compute boundary.

Even when all twelve jobs are complete, every service report keeps
`source_run_completed`, `source_range_qualified`,
`trusted_execution_attested`, `zero_completeness_claimed`, and
`external_atom_discharged` false. The later q-major transform, completed-sign
fold, zero isolation, multiplicity handling, Turing completeness, secure
execution receipt, and Lean refinement remain separate obligations.
