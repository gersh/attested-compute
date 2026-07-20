# H100-cluster deployment for all thirteen external atoms

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`tools/tg_h100_cluster.py` creates one deterministic, site-portable Slurm
deployment for all thirteen named ternary-Goldbach external atoms. It is a
control plane, not a certificate and not a Lean axiom discharge. A process
exit of zero only means that the selected atom-specific command exited
successfully. The atom's own final receipt still has to exist and pass its own
semantic replay.

The adapter makes two boundaries explicit:

- five campaigns use native exact H100 CUDA segment runners;
- eight campaigns are CPU sidecars (four FLINT/Arb and four exact integer or
  directed-rational computations).

An H100 does not make FLINT's zeta or Dirichlet-L implementation a CUDA
implementation. It also does not turn a sequential, hash-linked prefix into
safe independent mathematical shards.

## Build and runtime prerequisites

Use a reviewed checkout on storage visible from every compute node. Build the
native H100 runners once in that checkout:

```bash
cmake -S . -B build/h100-native \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/h100-native \
  --target sparkinterval-h100-native \
  --parallel 1
ctest --test-dir build/h100-native \
  -R '^h100_native_cli_offline$' \
  --output-on-failure
```

The five CUDA jobs require the resulting
`sparkinterval-h100-tg-mobius-segment` or
`sparkinterval-h100-tg-r2star-chunk` binary on an H100 (`sm_90`) node. The
FLINT jobs require the pinned interpreter described by
`requirements-tg-flint.txt`. The A.7 replay additionally requires the exact
retained boundary transcript; the portable manifest never substitutes a
sample transcript. Submission nodes also need Bash, `sbatch`, `flock`, and GNU
`sync`; the generated submitters use an OS-released lock and durable journals
to resume a partially submitted portfolio.

Inspect the non-executing capability report:

```bash
python3 tools/tg_h100_cluster.py --pretty capability
```

## Create and verify the portable deployment

The destination must be absent or empty. The command writes canonical
`manifest.json`, its SHA-256 sidecar, thirteen generated `sbatch` files, an
all-atoms submitter, and a single-atom resume submitter.

Planning also requires a completely clean Git worktree. It records the exact
commit OID, root tree OID, Git object format, and SHA-256 plus byte size of
every tracked regular file—not only the thin command wrappers. This binds the
transitive imported implementation closure without relying on a hand-curated
Python import list. Any modified, staged, or non-ignored untracked file makes
planning fail. Execution and `verify` independently reconstruct the same
complete closure from `TG_REPOSITORY`.

```bash
python3 tools/tg_h100_cluster.py --pretty plan \
  /shared/tg/deployment \
  --repository /shared/src/gpu_prover
python3 tools/tg_h100_cluster.py --pretty verify \
  /shared/tg/deployment \
  --repository /shared/src/gpu_prover
```

`verify` reconstructs every adapter and compares its exact bytes. Editing the
manifest, changing a job to a sample, adding a `--max-*` pause switch, or
editing a generated script fails closed.

Set the site-specific bindings before submitting. The first six variables are
required. The interpreter, compiler, build directory, and Slurm policy
variables are optional; the latter let the same verified scripts fit sites
whose H100 GRES, constraint, account, QOS, reservation, or maximum walltime
differs from the defaults:

```bash
export TG_REPOSITORY=/shared/src/gpu_prover
export TG_RUN_ROOT=/shared/tg/runs
export TG_A7_TRANSCRIPT=/shared/inputs/ch25-a7-boundary.json
export TG_H100_PARTITION=h100
export TG_CPU_FLINT_PARTITION=cpu-large
export TG_CPU_EXACT_PARTITION=cpu-large
export TG_PYTHON=/shared/venvs/tg-flint/bin/python
export TG_CXX=g++
export TG_H100_BUILD=/shared/src/gpu_prover/build/h100-native

# Optional site policy (examples, not universal defaults).
export TG_H100_GRES=gpu:h100:1
export TG_H100_CONSTRAINT=h100
export TG_SLURM_ACCOUNT=my-project
export TG_SLURM_QOS=normal
export TG_SLURM_RESERVATION=my-reservation
export TG_H100_WALLTIME=2-00:00:00
export TG_CPU_FLINT_WALLTIME=2-00:00:00
export TG_CPU_EXACT_WALLTIME=2-00:00:00
export TG_SLURM_REQUEUE=0

/shared/tg/deployment/slurm/submit.sh
```

Unset optional variables that the site does not use. Their values are passed
as individual `sbatch` array arguments; no value is evaluated as shell code.
The default H100 request is `--gres=gpu:h100:1`. Per-job CPU, memory, and
source-informed walltime directives remain in the job files unless a
class-specific walltime variable overrides them on the `sbatch` command line.

Slurm receives 12 independent named-atom jobs immediately. The Dirichlet job
is submitted with `afterok` on `platt-trudgian-rh-3e12`. At runtime it also
requires and revalidates
`$TG_RUN_ROOT/platt-trudgian-rh-3e12/final.json`; a forged scheduler state or
missing file cannot bypass the q=1 zeta prerequisite.

By default every H100 submission requests one `gpu:h100` generic resource.
The job refuses to start unless Slurm supplied `CUDA_VISIBLE_DEVICES`, and a
comma-separated visibility set is rejected before the strict runner starts.
The native runner then checks that the selected device is an H100 with compute
capability 9.0. Boost.Multiprecision is needed while building the CUDA runners,
but it is not a cluster runtime input. Submit through the generated
submitters; invoking a generated `.sbatch` file directly omits the site
allocation arguments and is unsupported.

Every submission passes an absolute shared `--chdir` and absolute stdout and
stderr paths below `$TG_RUN_ROOT/slurm-logs`; it never relies on the login
shell's current directory being visible from a compute node.

The all-atoms submitter holds
`$TG_RUN_ROOT/.slurm-submission.lock`, records each normalized numeric job ID
in `$TG_RUN_ROOT/slurm-submission.tsv` immediately after `sbatch` succeeds,
and syncs the journal before submitting the next job. If a later `sbatch`
call fails, rerunning `submit.sh` skips every journaled atom and submits only
the missing ones. This handles ordinary partial submission failures without
duplicating earlier jobs. The journal records submission, not completion; use
`submit-one.sh` when a journaled job later fails, times out, or is cancelled.
As with any scheduler client, an abrupt process or
node death in the narrow interval after Slurm accepts a job but before its ID
is journaled is not transactionally recoverable; inspect `squeue` or `sacct`
for the generated `tg-*` job name before retrying after such a crash.

To resume one preempted or timed-out campaign in the same persistent
workspace, submit that atom again:

```bash
/shared/tg/deployment/slurm/submit-one.sh \
  ramare-zuniga-lemma-6-2
```

`submit-one.sh` strips a federated `jobid;cluster` response to its validated
numeric job ID, prints only that ID, and durably appends it to
`$TG_RUN_ROOT/slurm-resubmissions.tsv`.

For a fresh Dirichlet resubmission whose zeta prerequisite is itself being
resubmitted, pass the zeta Slurm job ID as the second argument:

```bash
zeta_job=$(/shared/tg/deployment/slurm/submit-one.sh \
  platt-trudgian-rh-3e12)
/shared/tg/deployment/slurm/submit-one.sh \
  platt-dirichlet-theorem-7-1 "$zeta_job"
```

The resumable supervisors replay the existing contiguous hash chain and
continue at its first absent chunk. A.7 replay is idempotent. The current CDEM
Abel producer has no production checkpoint adapter, so a failed allocation
restarts its five-billion-step scan. `TG_SLURM_REQUEUE=1` asks Slurm to mark
jobs requeueable, but generic Slurm does not promise automatic requeue on
walltime or preemption. The portable recovery mechanism is an explicit
`submit-one.sh` invocation after the prior allocation has ended.

## Exact execution split and scalability

| Named atom | Allocation | Current partition/resume boundary | Honest feasibility |
|---|---|---|---|
| `ch25-a7-boundary` | CPU + FLINT | one idempotent full-transcript replay | Feasible when the retained 16,191-leaf transcript is supplied. |
| `ch25-psi-1e13` | exact CPU | serial authenticated chunks | The Python prime-power stream reaches `10^13`; it is not practical at source scale. |
| `platt-head-2e4` | CPU + FLINT | serial indexed-zero batches | Practical: 22,492 positive zero slots. |
| `platt-trudgian-rh-3e12` | CPU + FLINT | serial indexed-zero batches | Present algorithm would retain more than twelve trillion zero records and is prohibitive. |
| `helfgott-prop-12-2-4` | exact CPU | serial q-window chain | Present Python algorithm scans 3,389,047,618 admissible q rows and is prohibitively slow. |
| `cdem-squarefree` | H100 CUDA | serial Möbius/squarefree segments | A linear gap-free prefix through `10^16` remains prohibitive despite GPU segments. |
| `cdem-table-abel` | exact CPU/OpenMP | one full scan plus independent replay of all 1,000 chunks; restart on failure | Five billion recurrence steps are finite, but the producer is one-node and non-checkpointed. |
| `mertens-hurst` | H100 CUDA | serial Möbius/Mertens segments | A linear gap-free prefix through `10^16` remains prohibitive. |
| `ramare-zuniga-lemma-6-2` | H100 CUDA | serial exact R2Star segments | Large but direct: 21 billion prefix rows. |
| `helfgott-platt-theorem-4-1` | exact CPU | serial binary-Goldbach chunks, then ladder ranges, with the unbounded Pocklington producer available | The literal scan checks about two quintillion even inputs and is computationally astronomical. |
| `platt-dirichlet-theorem-7-1` | CPU + FLINT | serial primitive-character contour chunks after q=1, followed by `verify-source` | The wired reference handles all 29,565,923,837 primitive characters, but lacks Platt's fast lattice/FFT implementation and is unscaled. |
| `platt-little-mertens-2-11` | H100 CUDA | serial weighted-Möbius segments | Linear through `10^12`; resumable, but not safely multi-node sharded. |
| `platt-little-mertens-stronger` | H100 CUDA | serial weighted-Möbius segments | Direct 7,727,068,587-step chain; resumable, but not safely multi-node sharded. |

The cluster obtains portfolio concurrency: distinct named atoms may run on
different nodes. Inside a named atom, the current certificates bind a
contiguous prefix, prior state, and hash chain. The adapter therefore records
`parallel_intra_atom_shards: 1`. Splitting one such chain among nodes without
a proved merge certificate would risk gaps, duplicated boundaries, or an
incorrect prefix state, so this deployment does not claim that capability.

## Sample and trust policy

Every generated job contains `scope: full_source` and `sample: false`. The
reviewed argument vectors contain no bounded-sample mode and no `--max-*`
work-count pause option (`--max-seconds` remains only a fail-closed wall-clock
timeout for the full CDEM scan). The validator checks those invariants before any command is
resolved and then requires the entire deterministic manifest to match the
reviewed plan.

This still leaves the documented external-computation boundary: FLINT/Arb,
CUDA hardware and binaries, compilers, Python, the operating system, and the
atom-specific realization in Lean are not proved by the Slurm adapter. Keep
the campaign's final receipt, semantic replay output, manifest, scheduler
logs, environment/toolchain inventory, and immutable input hashes together
for human audit.

The CUDA campaign supervisors copy the selected runner into the persistent
campaign, bind its SHA-256 in immutable configuration, and require every
receipt to name those captured bytes. The CDEM supervisor similarly hashes the
compiler and reviewed producer/replayer sources. These runtime bindings are in
addition to, not a replacement for, the manifest's complete clean-Git source
closure.
