# CDEM Abel artifact-input terminal

Status: the standalone C++ terminal, strict production parser, independent
all-row subprocess replay, trace verifier, bounded protocol tests, optional
CMake target, and an **additive two-stage Azure CPU materializer** are
implemented. The current single-stage Azure CDEM factory is unchanged. No
production terminal receipt or C++/ELF-to-Lean refinement is claimed.

## Purpose

[`tg_cdem_abel_artifact_terminal.cpp`](../../reference/tg_cdem_abel_artifact_terminal.cpp)
supports a future two-stage Azure topology:

1. a measured producer creates the complete
   `TG-CDEM-ABEL-ARTIFACT-V1` recurrence artifact; and
2. a separately measured SEV-SNP CPU terminal takes those artifact bytes as
   its measured input, replays every row, and emits the legacy registered
   result.

This is the operational shape required by
[`CDEMAbelArtifactProgram.lean`](../../SparkInterval/TernaryGoldbach/CDEMAbelArtifactProgram.lean)
and `ProjectedCertificateProgram`: the architecture program sees the complete
artifact, not merely the small historical job descriptor. Ordinary Lean can
project successful artifact-checker acceptance to the existing descriptor-era
checker afterward.

## Accepted artifact

The parser accepts exactly one 195,228-byte production frame. It checks:

- the complete invocation, terminal, and canonical-job header;
- the two exact target numerators;
- exactly 1,000 fixed-width rows and no suffix;
- canonical 32-byte little-endian naturals and sign/magnitude integers,
  including rejection of unknown signs and negative zero;
- the exact 5,000,000-event row geometry covering
  `[1, 5,000,000,001)`;
- incoming-state continuity and final floor state `112`; and
- exact signed and absolute row reductions to the target numerators.

The non-authorizing `--validate-artifact` mode exercises only these framing
checks. It cannot write a result or trace and reports
`"source_claim_ready":false`.

## Measured terminal run

`--run` requires the expected SHA-256 of the already materialized chunk
replayer. The terminal reads and hashes that executable, copies the exact
bytes into a fresh scratch directory, and launches only that captured copy.
It uses `posix_spawn`, a fixed four-variable environment, exact decimal
arguments, 64 parallel workers, and no shell.

For every row, success requires:

- normal child exit with code zero;
- empty stderr;
- exact canonical stdout field order and encoding;
- exact low/high/incoming/outgoing state and both retained Abel totals; and
- a canonical variation field.

The 1,000 variation fields must reduce to `1,678,512,305`. After joining all
workers, the terminal rereads all captured outputs and the copied executable.
It then writes a challenge/job/artifact/replayer/result-bound hash chain in
the measured runner's exact nine-field work-trace schema and writes the
canonical registered result exclusively **last**.
Thus a parsing, replay, reduction, trace-write, or stale-output failure cannot
leave a newly published successful result.

The artifact is the measured input, so its digest occupies the base
`input_sha256` field. The copied replayer digest, every artifact-row digest,
every exact stdout digest, and the variation reduction are incorporated into
`trace_sha256`; they are not extra top-level JSON fields. The Azure closure
and measured argv must independently pin the expected replayer digest.

The same executable's `--verify-trace` mode rereads the artifact, registered
result, copied replayer, and all 2,000 captured stdout/stderr files, then
reconstructs the exact trace. It does not rerun the expensive arithmetic.

The two-stage materializer binds the replayer ELF digest in the measured argv,
the independently checked trace, and the measured job's static artifact
closure. A caller-supplied digest is never accepted: the materializer builds
the replayer from the source-pinned repository closure and inserts the digest
of that exact static ELF.

## Azure two-stage package

[`azure_cpu_cdem_artifact_terminal_materializer.py`](../../tg_verifier/azure_cpu_cdem_artifact_terminal_materializer.py)
is deliberately separate from the existing one-stage materializer. It will
not plan or build until the portfolio record for
`cdem-table-abel::single-job/0` is at `verified_receipt_recorded`.

The materializer then:

1. verifies the producer receipt under the repository-pinned production key
   manifest and checks the exact registered
   `cdemTableAbelProductionV2` identity;
2. safely extracts the separately pinned returned producer certificate
   archive;
3. verifies every run-bundle artifact, reconstructs the receipt claim, and
   requires the bundle statement hash to equal the signed receipt's wire
   statement hash;
4. requires that signed statement to name exactly
   `work/cdem-abel-artifact.bin` as its sole retained artifact;
5. copies those exact bytes as
   `input/cdem-abel-artifact.bin`, the second measured job's actual input;
6. builds static x86-64 terminal and replayer ELFs from the repository-pinned
   sources, pins both binaries and all sources in the measured closure; and
7. retains the producer certificate archive, receipt, and a canonical
   predecessor-binding record in that closure, together with the exact
   source-pinned verifier-key manifest and public key used for the dependency
   check.

The second stage uses a fresh operator-generated challenge. Its operator
configuration sets `registered_invocation` to `null`; therefore the generic
operator can issue an operational receipt after appraisal, but cannot generate
a Lean registry or theorem candidate for this stage. The existing registered
one-stage receipt remains the only current semantic CDEM route.

Prepare a canonical site file from
[`azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json`](../../examples/trusted-compute/azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json),
then run:

```bash
python3 tools/tg_azure_cpu_cdem_artifact_terminal_materializer.py \
  plan /srv/sparkinterval-operator/portfolio/portfolio.json \
  /srv/sparkinterval-operator/sites/cdem-terminal.json

python3 tools/tg_azure_cpu_cdem_artifact_terminal_materializer.py \
  materialize /srv/sparkinterval-operator/portfolio/portfolio.json \
  /srv/sparkinterval-operator/sites/cdem-terminal.json
```

The returned `cpu-campaign.json` is run with the ordinary
[`cpu_production_orchestrator.py`](../../azure/cpu_production_orchestrator.py)
challenge-first workflow. Package creation is not execution evidence.
The checked-in verifier-key manifest currently contains no production key, so
the materializer correctly refuses a production dependency until the reviewed
Azure key is installed there.

## Build and bounded checks

Direct source build:

```bash
g++ -std=c++20 -O3 -Wall -Wextra -Werror -pthread \
  -Igpu/include reference/tg_cdem_abel_artifact_terminal.cpp \
  -o build/tg_cdem_abel_artifact_terminal
```

The optional CMake target is enabled with
`-DSPARKINTERVAL_BUILD_TG_CDEM=ON` and is named
`sparkinterval-tg-cdem-abel-artifact-terminal`.

The focused test is:

```bash
python3 -m unittest -v tests.test_tg_cdem_abel_artifact_terminal
python3 -m unittest -v \
  tests.test_azure_cpu_cdem_artifact_terminal_materializer
```

It compiles the terminal, audits parser/tamper failures, and uses a
constant-time protocol stub to exercise all 1,000 `posix_spawn` handoffs,
exclusive publication, and retained-trace replay. It never evaluates the
five-billion-event CDEM recurrence and is not verification evidence.

## Remaining proof and deployment boundary

This terminal is deliberately a source implementation, not a proof of source
correctness. Before an Azure receipt can discharge the architecture side of
the Lean artifact program, the project still needs:

1. operator deployment values, production policy/key pins, and an x86-64
   materialization of the implemented two-stage package;
2. an actual attested terminal run whose measured input is the complete
   artifact;
3. a formal refinement from successful terminal/replayer execution to
   `CDEMAbelArtifactProgram.artifactNativeChecker`; and
4. compiler, static ELF, loader, ABI, and x86-64 refinement for the measured
   binaries.

Hash binding and confidential-compute attestation establish identity and
execution provenance. They do not establish items 3 or 4.
