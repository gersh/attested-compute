# Attestation adapters

This directory implements the evidence boundary between a measured physical
run and a Lean proof. It does not turn attestation into a mathematical proof.
The result of any pipeline here is a signed statement about one measured
historical run; Lean can attach mathematical meaning only when that statement
matches a closed computation with an ordinary soundness theorem.

There are two independent backends, and they are at different stages:

| | |
| --- | --- |
| [`phala/`](phala/README.md) | **Intel TDX on Phala Cloud.** The current path, exercised on real hardware. Runs CompCert artifacts inside a confidential VM and produces evidence checkable offline against the pinned Intel SGX Root CA. Start at [`phala/README.md`](phala/README.md); the trust surface is in [`../docs/TRUSTING_THE_ENCLAVE.md`](../docs/TRUSTING_THE_ENCLAVE.md) and what the Lean axiom does *not* check is in [`../docs/AXIOM_ASSUMPTIONS.md`](../docs/AXIOM_ASSUMPTIONS.md). |
| the Azure files below | **Azure confidential CPU and H100 — never validated on hardware.** An earlier, more elaborate design built around a relying-party challenge and MAA/NVAT appraisal. It has never been executed: there is no `az` CLI, no subscription, `tests/data/` holds retained evidence for Intel TDX only, and `verify_azure_ncc_evidence.py` currently fails at import. Read it as a specification. |

## Why the Azure path is still here at all

Its own readiness document said so plainly — *"Nothing here was verified
against a live Azure account"*, with `tg_azure_launch_preflight.py` reporting
zero of ten campaigns `cloud_launch_ready` — so on 2026-08-20 the parts that
nothing else depended on were deleted: 27 Azure-only tests, 3 tools and 2
documents, 30 files in all, recoverable from git history.

The rest stays because it is not separable. `azure/measured_runner.py` has 37
referrers and `azure/cpu_production_orchestrator.py` has 29, spanning the H100
and GPU measured-worker machinery that is not Azure-specific despite living
under this name. Deleting those would remove the measured-run subsystem, not
an unused backend. Every surviving Azure document now carries a banner saying
it was never executed, and they are grouped under their own heading in
`../docs/README.md` rather than listed as if supported.

The rest of this document describes that unvalidated Azure path.

The certificate-capable Azure path has six distinct stages:

1. [`azure/measured_runner.py`](../azure/measured_runner.py) validates a fresh
   relying-party challenge and a source-reviewed, content-addressed job
   closure; extends PCR 23 with the start binding; releases the exact input;
   executes the CPU or H100 workload; independently checks its
   challenge-dependent work trace; extends the result binding without another
   reset; and quotes the final PCR state. Its local report always says
   `accepted: false`.
2. For H100 jobs,
   [`azure_h100_pre_run_gate.py`](azure_h100_pre_run_gate.py) runs between the
   start extension and input release. It requires one production-CC H100 in
   Ready state and retains challenge/job-bound NVAT evidence. The final
   appraiser must cryptographically reappraise that evidence and bind it to
   the same CVM.
3. [`collect_azure_measured_evidence.py`](collect_azure_measured_evidence.py)
   archives the exact measured-run package, copies its existing quote without
   resetting or extending PCR 23, and obtains post-run Azure MAA evidence and,
   for H100, result-bound NVIDIA evidence. Collection is not acceptance.
4. [`verify_azure_ncc_evidence.py`](verify_azure_ncc_evidence.py) recomputes
   the complete artifact closure, compares the complete challenge object with
   the exact canonical file retained outside the worker, and calls separately installed,
   hash-pinned Azure and NVIDIA appraisers under a hash-pinned policy. It does
   not trust the collector's local success flags.
5. [`tools/trusted_compute_receipt.py`](../tools/trusted_compute_receipt.py)
   binds the normalized appraisal, exact run bundle, output, challenge,
   appraiser, and policy into a compact RSA-3072-signed receipt. Production
   signing is supported through an external signer such as the Azure Managed
   HSM adapter; the checked-in bootstrap key is development-only.
6. [`tools/generate_trusted_compute_registry.py`](../tools/generate_trusted_compute_registry.py)
   verifies a source-pinned key and emits the closed reviewed Lean receipt
   registry. [`tools/generate_trusted_compute_lean.py`](../tools/generate_trusted_compute_lean.py)
   then emits a consumer whose registry membership and structural claim
   binding reduce with ordinary Lean computation.

The tracked registry is intentionally empty: no real Azure H100 run has been
performed or admitted in this repository. A production admission still needs
Azure credentials, quota and capacity, a genuine run, reviewed measurements,
a pinned cryptographic Azure appraiser and policy, NVIDIA appraisal for the
H100 route, a production Managed HSM key with reviewed key attestation and
public-key/issuer-tuple pins (including exact target/trust profile digests), a
shared retained replay database, and a reviewed source-registry change.
The Azure appraiser must explicitly establish measured-runner policy, binding
of the result artifact to that execution, and (for H100) binding of accelerator
attestation to the same CVM. The test fake demonstrates only the JSON ABI; no
production implementation of those claims is included, so issuance must stay
blocked if the retained vendor evidence and measured protocol cannot establish
them.

Attestation alone cannot prove that arbitrary user-space code produced an
output. Production policy must measure and constrain the runner and executable
closure, for example through a reviewed immutable image plus dm-verity/IMA or
an equivalent mechanism. The vTPM result binding shows that the measured
environment committed to the challenge and output; it is not, by itself, a
proof of program causality.

The older adapters remain deliberately limited:

- `collect_azure_ncc_evidence.py` is a legacy diagnostic collector. Its
  post-work PCR reset cannot establish the required start-to-result execution
  chain; the command-line verifier and receipt path structurally reject its
  manifest kind;
- `mock_attestation.py` emits visibly non-production data for parser and
  rejection tests;
- `nvidia_cc_provider_stub.py` exits fail-closed and cannot produce positive
  evidence; and
- DGX operator signatures authenticate a local operator endorsement but are
  not hardware evidence and do not use the Azure importer.

Start with the [challenge-first measured-runner guide](../docs/AZURE_MEASURED_RUNNER.md)
and the [Azure deployment guide](../docs/AZURE_CONFIDENTIAL_COMPUTE.md),
then consult the [verifier guide](../docs/VERIFYING.md),
[trust model](../docs/TRUST_MODEL.md), [bundle format](../docs/FORMAT.md), and
[H100 guide](../docs/H100.md). Production signers should also follow the
[Managed HSM key and receipt-signing guide](../docs/AZURE_MANAGED_HSM_SIGNING.md).
