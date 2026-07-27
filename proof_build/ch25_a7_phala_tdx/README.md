# CH25 Lemma A.7 campaign image for Phala/dstack Intel TDX

Packaging for the cheapest registered campaign (`ch25-a7-boundary`, about
1.6 s of FLINT/Arb compute) so it can run as a `dstack` application inside an
Intel TDX confidential VM.

* `Dockerfile` — the campaign image. `linux/amd64`, base image pinned by
  digest, python-flint pinned by URL *and* SHA-256 and re-verified at run time
  against `specifications/PYTHON_FLINT_0_9_UPSTREAM.json`.
* `run_phala_tdx_campaign.sh` — the entry point. Validates the job scope and
  the required inputs, then runs `tools/tg_a7_phala_tdx_workload.py`. It
  **creates none of its inputs**: all seven must already exist.
* `prelude_phala_tdx_inputs.py` — the in-CVM prelude that creates them.
  Derives the P-256 signing key from the dstack guest agent, commits to its
  public key in the TDX quote's report data, fetches the quote, appraises it
  with the pinned `dcap-qvl` against the reviewed policy, replays the RTMR
  event log against the quote, stages the retained A.7 artifact, and hands
  over. Hard-fails on anything unexpected.
* `dcap-qvl-policy.json` — the reviewed appraisal policy. Shipped as a
  template in which **every measurement is an explicit `TODO:`**; the prelude
  refuses to proceed while any remains. Delivered to the CVM as base64 in an
  encrypted environment variable, deliberately *not* inside `app-compose.json`
  (it pins RTMR3, which is a function of the compose bytes).
* `docker-compose.yaml`, `app-compose.json` — the dstack deploy manifest,
  **generated** by `tools/tg_phala_tdx_compose.py`. The image is referenced by
  registry digest, never by a tag. The prelude's source is embedded verbatim,
  so it is inside the compose hash and inside RTMR3.

The pinned appraiser is recorded in
`specifications/DCAP_QVL_0_6_1_UPSTREAM.json`.

## No TDX hardware was available

The prelude has never run against a real dstack guest agent or a real quote.
Its wire contract was read out of `Dstack-TEE/dstack` at v0.5.3 and
`Phala-Network/dcap-qvl` at v0.6.1, and it is exercised only against mocks in
`tests/test_phala_tdx_prelude.py`. Treat the first real run as a discovery
run.

The ordered procedure for a real run, what must be pinned and where, and what
the resulting theorem does and does not establish are in
[`docs/PHALA_FIRST_RUN.md`](../../docs/PHALA_FIRST_RUN.md).

## What this image does not do

It does not verify the TDX quote. Quote parsing, the PCK certificate chain,
TCB levels, and QE identity are appraised outside by `dcap-qvl`; the image
requires the quote and the appraisal to be present as files and commits their
SHA-256 into the signed statement. Lean, in turn, verifies only the enclave's
P-256 signature and the statement bindings.

## Local dry run

`tests/test_phala_tdx_first_run.py` builds this image and runs it against the
committed stand-in key and a freshly generated fixture A.7 artifact. That test
is the readiness check: if it passes, the only missing ingredients for a real
run are Phala credentials and the retained production A.7 artifact.

A dry run is contained by the Lean enclave pin, not by this directory: the
`ch25A7BoundaryLocalDryRunV1` identity has `attestationAuthority := false`, so
no receipt signed by the stand-in key can reach a campaign theorem.
