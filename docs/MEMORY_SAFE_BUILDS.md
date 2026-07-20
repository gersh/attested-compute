# Memory-safe builds

Lean proof elaboration can consume substantial memory, especially when a
large structural equality is handed directly to `simp` or several modules are
built concurrently. SparkInterval therefore uses three independent limits:

1. `lakefile.toml` passes `-j1 -M8192` to batch Lean processes and
   `-j1 -M4096` to the Lean language server. The `-M` values are MiB.
2. `tools/safe_lake_build.py` orders all local modules by their import graph
   and builds them one at a time. A full-plan lock prevents separate planners
   from interleaving their dependency closures and remains held through every
   module and executable target. A second planner prints that it is waiting
   instead of appearing to have stalled.
3. `tools/with_memory_limit.sh` places each build step in a systemd user
   cgroup with `MemoryHigh=10G`, `MemoryMax=12G`, and `MemorySwapMax=2G`.
   A repository lock also prevents two safe build commands from running at
   the same time in separate terminals or automation jobs.

Run these commands from the repository root. Use the safe entry points for
routine work:

```bash
./tools/safe_lake_build.py
./tools/safe_lake_build.py SparkInterval.PTX.InstructionRefinement
./tools/safe_lake_build.py --target sparkinterval-gen
./tools/safe_lake_build.py SparkInterval.PTX.StructuralCompilerCorrect
./tools/safe_lake_build.py --blueprint-json
make lean
```

The `--blueprint-json` and `--blueprint-tex` modes build the single curated
`SparkInterval.Blueprint` LeanArchitect facet after its local dependency
closure. They retain the same complete-plan lock, source snapshot, serial
module ordering, and aggregate memory cap. See the
[proof-blueprint guide](PROOF_BLUEPRINT.md); do not replace these modes with a
direct `lake build :blueprintJson` command.

LeanArchitect's metadata loader needs more runtime support threads than an
ordinary elaboration even though Lean remains at `-j1`. The safe planner gives
only the Blueprint module and facets `TasksMax=64`; all other steps retain the
default `TasksMax=32`, and every step retains the same 12 GiB aggregate memory
ceiling. An explicit `SPARKINTERVAL_TASKS_MAX` still takes precedence.

For an individual generated, scratch, or example Lean file, first build its
local imports with the safe planner, then use `safe_lean.sh`; do not invoke
`lake env lean` directly. Tracked library modules must always go through the
planner so its dependency and source-snapshot checks apply. Do not replace the
planner with a direct
capped Lake command: `build`, `query`, `exe`, `test`, `lint`, `run`, `script`,
and `shake` can initiate builds in which Lake schedules several stale
dependency modules concurrently even when Lean itself receives `-j1`. The
wrapper rejects those commands unless they are authorized planner steps; pass
a module argument or `--target` to `safe_lake_build.py` instead.

The planner does not trust a dependency graph computed before it obtained the
full-plan lock. After acquiring the lock (including after waiting for another
planner), it rereads the local Lean sources and reconstructs the import graph
from the captured bytes. It snapshots the complete local module-name/path set
and the SHA-256 content digest of every source in the selected dependency
closure. The module set and selected content are checked before and after each
module build and executable target. If a source is added, removed, moved, or
changed during the plan, the planner reports the drift, asks for a restart,
and exits with status 66. A plan assembled from mixed source revisions cannot
report success.

Each authorized Lake step inherits the planner's open descriptor for the
full-plan lock. `with_memory_limit.sh` verifies that descriptor refers to the
repository's expected plan-lock path before it starts `systemd-run`. Merely
setting `SPARKINTERVAL_SERIAL_LAKE_STEP` or forging the descriptor-number
environment variable does not authorize a direct Lake command.

`safe_lean.sh` owns Lean's resource arguments: it supplies `-j1` and derives
`-M` from `SPARKINTERVAL_LEAN_MEMORY_MB`. It rejects caller-provided `-j*` and
`-M*` arguments so later arguments cannot enable parallel elaboration or
override the per-process memory ceiling. Change the memory value through the
environment variable; parallel Lean execution is unsupported.

For CMake, keep configuration and compilation inside the same aggregate cap
and make the job bound explicit:

```bash
./tools/with_memory_limit.sh cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
./tools/with_memory_limit.sh cmake --build build/dgx-spark --parallel 1
./tools/with_memory_limit.sh ctest --test-dir build/dgx-spark \
  --parallel 1 --output-on-failure
```

`SPARKINTERVAL_MEMORY_HIGH`, `SPARKINTERVAL_MEMORY_MAX`,
`SPARKINTERVAL_SWAP_MAX`, `SPARKINTERVAL_TASKS_MAX`, and
`SPARKINTERVAL_LEAN_MEMORY_MB` can lower or raise the defaults deliberately.
`SPARKINTERVAL_RUNTIME_MAX` changes the default 30-minute per-step timeout.
The wrapper fails closed when a systemd user manager is unavailable. On a
machine already protected by an equivalent container or scheduler limit,
`SPARKINTERVAL_ALLOW_UNCAPPED=1` permits the command while retaining Lean's
per-process limit.

The wrapper preserves the caller's toolchain search variables (for example
`PATH`, CUDA paths, compiler selections, and library/include paths) but does
not copy the complete environment into the transient service. Command
arguments are passed literally, including dollar signs. Interrupting the
wrapper stops the complete transient cgroup before propagating the signal.
Call the safe entry points directly: do not place `safe_lake_build.py`,
`safe_lean.sh`, or `build_dgx_spark.sh` inside another
`with_memory_limit.sh` invocation. Nested wrappers fail immediately because
the repository lock is intentionally non-reentrant.

CMake builds use one job by default through the repository entry points. A
bare `cmake --build ... --parallel` can select all available CPUs and is not a
supported default. Set `CMAKE_BUILD_JOBS` for `make` or
`SPARKINTERVAL_BUILD_JOBS` for `tools/build_dgx_spark.sh` only after checking
the available host memory.

An exceeded Lean `-M` limit or cgroup limit is a failed proof check, never a
reason to weaken a theorem or silently increase the limit. Refactor the proof
term, use smaller compositional lemmas, or use the documented native
full-certificate mode for large materialized witnesses.
