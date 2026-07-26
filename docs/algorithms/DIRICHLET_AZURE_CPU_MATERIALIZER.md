# Source-closed Azure CPU fallback for Platt Theorem 7.1

## Status

This route packages the repository's rigorous FLINT/Arb contour fallback. It
does **not** implement or claim the performance of Platt's lattice/FFT
computation, and materializing the package is not evidence for the theorem.
The registered result is written as literal `true` only after the complete
q=1 and q=2 through 400000 source domains have been replayed.

The Azure portfolio currently expands this campaign into two physical groups:

| group | source-closed status | remaining issue |
|---|---|---|
| `platt-dirichlet-theorem-7-1::single-job` | Factory, measured worker, source/runtime closure, deterministic package, trace replay, and operator configuration are implemented | The raw contour fallback is not expected to finish within Azure's seven-day challenge lifetime |
| `platt-dirichlet-theorem-7-1::postcheck` | Factory, measured worker, authenticated predecessor import, independent full replay, deterministic package, trace replay, and operator configuration are implemented | The raw retained package is expected to exceed practical runtime and possibly the operator's 256 GiB extraction limit |

Consequently this work still does not make the campaign Azure-ready and does
not enable its semantic binding. It does close the protocol gap between the
two physical groups: the postcheck accepts the returned source certificate
archive only together with its production-signed receipt.

The separate
[small-q packed-sign H100 phase](DIRICHLET_SMALLQ_PACKED_SIGN_TRANSPORT.md)
now has a fail-closed measured package for both explicitly signed host- and
device-packing modes. It is an operational compact-state phase, not a
replacement for this source-wide CPU fallback, and it is deliberately absent
from the terminal portfolio route until the remaining analytic source
realizations exist.

## Bound inputs

The materializer accepts no caller-selected executable or shell command. Its
site file, validated by
`schemas/azure-cpu-dirichlet-materializer-site.schema.json`, binds:

- the common production CPU materializer site and all attestation policies;
- the reviewed FLINT 3.6 source checkout;
- the reviewed python-flint 0.9.0 source checkout;
- the pinned x86-64 python-flint wheel and its extracted tree digest;
- a deterministic archive of the complete PT21 q=1 campaign;
- a production-key, source-allowlisted trusted-compute receipt for the exact
  `plattTrudgianFiniteRHProductionV1` invocation;
- the exact portfolio shard config and challenge;
- every project source used by the measured worker and trace verifier.

The q=1 archive is checked as the current fixed-index
`tg_verifier.platt_zeta_campaign` format. This intentionally repairs a format
seam in the older `tg_dirichlet_campaign.py source` command, which still asks
for the legacy `zeta_zero_campaign` layout. Structural replay of that archive
is not treated as proof that its expensive zero computations ran: the worker
also verifies the production receipt signature, source-approved verifier
profile, exact registered invocation, and literal `true` result. The current
repository key manifest contains only a development profile, so no present
receipt can satisfy this production gate.

The postcheck uses a second site shape, validated by
`schemas/azure-cpu-dirichlet-postcheck-materializer-site.schema.json`. It pins
the complete returned source certificate package and the production receipt
for `plattDirichletTheorem71ProductionV1`, in addition to the same reviewed
FLINT/python-flint closure. The outer package contains the measured runner's
entire `bundle-root`, including the retained q>=2 archive.

## Measured computation

`tools/tg_dirichlet_azure_measured_workload.py` performs the following closed
sequence:

1. verify and activate the pinned python-flint wheel;
2. extract and structurally replay the complete PT21 q=1 campaign, including
   its exact height, multiplicity count, and Merkle root;
3. enumerate every primitive character for q=2 through 400000 with the exact
   parity-dependent heights;
4. run the FLINT/Arb winding-plus-Hardy-sign fallback and its checker;
5. retain the full q>=2 hash-linked campaign and source composition;
6. independently extract the retained archive and rerun every checker before
   accepting the work trace;
7. emit literal `true` only after all preceding checks succeed.

The terminal postcheck independently enforces this authentication chain:

1. production receipt signature, production verifier allowlist, and exact
   registered invocation;
2. receipt bindings to the returned run-bundle and wire-statement hashes;
3. run-bundle verification of every statement artifact;
4. wire-statement binding to the source work-trace artifact and chain;
5. source-trace binding to the q=1 archive and receipt, retained q>=2 archive
   and tree, source composition, and literal `true` output;
6. fresh q=1 verification and fresh execution of every retained q>=2 checker;
7. recomputation of the source composition before the postcheck writes its own
   literal `true` and challenge-bound trace.

No unsigned path, filename, Boolean, or structural archive hash substitutes
for that chain.

The producer and checker are presently the same reviewed backend bytes. The
campaign records that fact, and the documentation does not describe the trace
replay as an independent implementation.

## Operator commands

After a portfolio shard has reached `challenge_created`, plan or materialize
the source job with:

```bash
python3 tools/tg_azure_cpu_dirichlet_materializer.py \
  plan PORTFOLIO_SPEC \
  platt-dirichlet-theorem-7-1::single-job 0 SITE_JSON

python3 tools/tg_azure_cpu_dirichlet_materializer.py \
  materialize PORTFOLIO_SPEC \
  platt-dirichlet-theorem-7-1::single-job 0 SITE_JSON
```

After the source job has a production receipt and returned certificate archive,
use a postcheck site file and replace the group id with
`platt-dirichlet-theorem-7-1::postcheck`. The same CLI emits the terminal
measured package; it does not execute or sign it.

The output manifest has schema
`schemas/azure-cpu-dirichlet-materialization.schema.json` and states
`accepted: false`, `execution_completed: false`,
`source_run_receipt_produced: false`, and
`raw_fallback_expected_to_finish_within_timeout: false`.

## Inputs still needed for a practical completion

A practical source-scale route still needs all of the following:

- a completed, retained PT21 q=1 campaign archive and its production-signed
  registered receipt (neither exists yet, and the production verifier profile
  has not been installed);
- source-wide useful enclosures for the optimized small-q and large-q paths;
- uniform interpolation and exception refinement;
- corrected reflected Turing/count closure connected to the Lean source
  contract;
- a measured optimized worker whose full run fits the challenge lifetime;
- a bounded or streamed retained-evidence transport if the raw archive exceeds
  the CPU operator's current 256 GiB extraction cap.

Until those exist and a complete receipt is admitted, the external atom
remains undischarged.
