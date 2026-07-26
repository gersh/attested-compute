# Azure challenge-first measured execution

`azure/measured_runner.py` is the certificate-capable execution path for finite
CPU or H100 jobs. It is deliberately separate from the older
`collect_azure_ncc_evidence.py` path. The old collector resets PCR23 after the
work has already finished; it remains useful for platform diagnostics, but
`verify_azure_ncc_evidence.py` structurally rejects its manifest kind when
invoked by receipt issuance.

## Development versus production replay

Production-sized arithmetic belongs on the measured Azure worker. A normal
developer or CI run should compile the symbolic Lean refinement, perform
static closure and policy checks, and use only tiny known-answer vectors. It
must not regenerate or independently replay a production certificate.

Production-classified runner policies inject four reserved child variables
only after the challenge, job binding, closure, profiles, policy, and PCR
start have been checked:

- `SPARKINTERVAL_MEASURED_WORKER_SCOPE`;
- `SPARKINTERVAL_MEASURED_WORKER_BACKEND`;
- `SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE`; and
- `SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256`.

Job specifications cannot set those names. Production workload and external
trace-verifier entry points compare the exact challenge and job binding
before reading their artifacts. This is a fail-fast protection against
accidental local execution, not a credential or attestation proof: a local
process can forge environment variables. The remotely appraised measured-run
transcript remains the security boundary.

Legacy mixed-purpose campaign CLIs use the same scope through a size-aware
guard. Metadata commands remain local, as do deliberately non-production
known-answer workloads whose every effective work bound is at most 64.
Production profiles and any larger finite run require the measured-worker
scope before runner or retained-artifact access.

The returned theorem handoff is intentionally compact. Lean checks the
source-pinned registered invocation and admitted signed receipt; the sole
trusted execution axiom supplies that invocation's fixed `Runs` relation.
Lean then derives the mathematical claim from `Runs` using ordinary theorems.
This does not make the receipt a proof of arbitrary mathematics: the reviewed
code-to-`Runs` refinement and the confidential-compute appraisal are exactly
the visible trust boundary. An optional archival audit may stream-check
artifact hashes, but it is separate from ordinary local theorem checking and
never performs the arithmetic replay.

The measured protocol is:

1. A relying party creates and retains a fresh challenge off the VM.
2. The runner verifies that challenge before execution, snapshots the exact
   artifact closure, and computes a canonical job binding.
3. It resets PCR23, reads 32 zero bytes, extends the start binding, and verifies
   `PCR23_started = SHA256(0^32 || start_binding)`.
4. On H100, it obtains fresh NVIDIA Ready/production-CC evidence for the exact
   challenge and job binding. A remote gate can receive
   `NV_ATTESTATION_SERVICE_KEY` through the runner's narrow, non-recorded secret
   environment forwarding; the value is never stored in the job or transcript.
   Only then may the relying-party release command materialize the input.
5. The runner invokes an exact argv array without a shell. The challenge and
   job binding are arguments to the measured program. A mandatory work trace
   depends on both values. Output and trace paths start absent and are created
   in a fresh private directory.
6. If the source-reviewed job declares `retained_artifact_contracts`, each
   record fixes one safe relative path, byte ceiling, and otherwise-unused
   SHA-256 field in the trace. This option requires a pinned external trace
   verifier. After that verifier succeeds, both the runner and the independent
   transcript verifier hash the exact regular retained file, reject symlink
   traversal or a digest/size mismatch, and place its path, size, and digest in
   the signed execution environment. Jobs which omit the optional field retain
   the original V1 shape.
7. The statement binds the result, work-trace, and any declared retained
   artifact identities. The runner extends the
   result binding without another reset and verifies
   `PCR23_final = SHA256(PCR23_started || result_binding)`.
8. It quotes the existing final PCR state. The runner and collector always say
   `accepted: false`; only a separately pinned relying-party appraiser can
   authenticate the quote and vendor chains.

## Exact runnable CPU example

Build the static, dependency-free closed cubic example on the guest image:

```bash
python3 tools/build_cubic_measured_example.py \
  --output-root /srv/jobs/cubic-20000
```

The executable accumulates `x^3` for `x = 0..20000`, checks every unsigned
64-bit operation, divides the total by three, and writes exactly
`13334666700000000` without a newline. It separately computes a 20,001-step
SHA-256 chain seeded by the challenge and job binding. The runner and the
independent transcript verifier recompute that complete trace. The mathematical
result bytes remain exactly those expected by the closed Lean invocation.

The checked-in runner and appraisal policies produced by this command are
development-only. They exercise the protocol but cannot authorize production
receipt generation.

After copying one still-live, retained challenge to the CVM, run:

```bash
sudo python3 azure/measured_runner.py \
  --job-spec /srv/jobs/cubic-20000/job.json \
  --artifact-root /srv/jobs/cubic-20000 \
  --challenge /run/gpu-prover/challenge.json \
  --output-dir /srv/runs/cubic-20000
```

A development smoke test adds `--allow-development-policy`. That flag never
changes the result to accepted.

## H100 pre-run gate

An H100 job must use target `azure_ncc40ads_h100_v5`, trust profile
`azure_ncc_sevsnp_vtpm_nvidia_cc_attested`, release mode
`relying_party_after_h100_gate`, and a non-null `gpu_pre_run_gate`. Its exact
gate argv should invoke the pinned adapter along these lines:

```text
attestation/azure_h100_pre_run_gate.py
  --challenge-nonce @challenge@
  --challenge-expires-at @challenge_expires_at@
  --job-binding @job_binding@
  --package-root .
  --record-path @gate_record@
  --policy profiles/production-nvidia-policy.rego
  --verifier remote
```

The first executable in the gate, input-release, workload, and external trace
verifier argv arrays must be a declared executable in the snapshotted artifact
closure. The input-release argv must also contain `@challenge@`,
`@job_binding@`, and `@input@`; an unpinned helper or a release request that is
not bound to this exact run is rejected before the gate executes. If a helper
uses a script interpreter or shared libraries, those bytes must be covered by
the production measured-image policy or by an equivalent closed executable
runtime manifest.

The gate contract lists `NV_ATTESTATION_SERVICE_KEY` in
`secret_environment_names`; the runner forwards only that named value to the
gate and records only the variable name. The `--policy` argument is required.
The checked-in baseline Rego is intentionally non-authorizing and requires an
explicit development opt-in even at the gate adapter.

The adapter retains raw NVAT evidence, detached EAT, appraisal, policy hash,
Ready/production state, gate nonce, challenge, and job binding. The final
Azure composite appraiser receives the immutable measured-run archive and must
cryptographically re-appraise this *pre-run* evidence. It must return
`pre_run_accelerator_gate_valid: true` as well as
`accelerator_attestation_bound_to_cvm: true`. Post-run NVIDIA evidence alone is
not enough.

## Evidence, bundle, and receipt handoff

After the runner exits, collect Azure evidence without touching PCR23:

```bash
sudo python3 attestation/collect_azure_measured_evidence.py \
  --challenge /run/relying-party/challenge.json \
  --run-package /srv/runs/cubic-20000 \
  --runner-appraisal-policy /run/relying-party/measured-policy.json \
  --backend azure_sevsnp_cpu \
  --maa-attestation-url 'https://TENANT.REGION.attest.azure.net/attest/SevSnpVm?api-version=2022-08-01' \
  --output-dir /srv/certificate-packages/cubic-20000
```

For H100, also supply a production NVIDIA policy and the selected local or
remote NVAT mode. The output has two explicit consumers:

- `evidence/` is the closed, top-level artifact pack for
  `verify_azure_ncc_evidence.py`;
- `bundle-root/run-bundle.json` is the canonical bundle for
  `trusted_compute_receipt.py`.

The adapter reconstructs the run bundle from the job, files, completion record,
and environment, refuses any statement difference, and runs the ordinary
bundle integrity verifier before publication. The measured run itself is
transported in a deterministic archive that rejects links, path traversal,
special files, duplicate names, noncanonical metadata, and configured size or
file-count excesses. Partial archives and extraction trees are removed after a
failure.

Receipt issuance privately snapshots the outer verifier and its directly
imported Python source closure. The outer verifier source-pins every module,
extracts the measured archive into its private snapshot, replays the transcript
and trace checks, validates both PCR equations, then invokes separately
hash-pinned Azure and NVIDIA cryptographic appraisers. A production Managed HSM
key may sign only the resulting normalized appraisal/claim. The Lean bridge's
single axiom applies only after a reviewer admits that signed receipt to the
source registry.

## Performance and residual trust

Artifact copying and hashing are streaming. Workload logs are independently
limited to 16 MiB for stdout and stderr. The small cubic trace is intentionally
serial and is locally recomputed in well under a second on DGX Spark. Large H100
campaigns must not use a per-event serial digest as their only trace: their
source-reviewed job should use a pinned external verifier with chunk-local
challenge-dependent commitments and a Merkle reduction, with chunk indices,
domain separation, and completeness rules formally specified. That scalable
trace format remains production work; the current generic external-verifier
hook enforces exact argv and rehashes input, result, trace, and closure after it
runs.

Attestation establishes a chain from approved measurements and policy to bytes;
it does not prove arbitrary mathematics. In particular:

- no production Azure SEV-SNP/vTPM/NVIDIA composite appraiser or measurement
  allowlist is checked in;
- no production measured-image build, dm-verity/IMA policy, NVIDIA RIM/firmware
  allowlist, Managed HSM key attestation, or global anti-rollback ledger is
  present;
- a privileged process inside a permissive measured image can reset/extend a
  dynamic PCR or forge a transcript, so the production image must make the
  runner the measured, locked-down execution authority and the appraiser must
  verify that policy;
- the NVIDIA-to-CVM same-machine binding must be established by the production
  composite appraiser, not inferred from two independent valid attestations;
- the Python interpreter, standard library, TLS roots, NVAT runtime, drivers,
  and appraiser runtime must be part of the measured immutable image or a
  separately content-addressed executable/container closure.

Until those items exist and a live Azure H100 run is reviewed, this repository
provides fail-closed execution and appraisal infrastructure, not a production
secure-enclave certificate or a discharged Lean theorem.
