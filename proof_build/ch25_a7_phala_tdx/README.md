# CH25 Lemma A.7 campaign image for Phala/dstack Intel TDX

Packaging for the cheapest registered campaign (`ch25-a7-boundary`, about
1.6 s of FLINT/Arb compute) so it can run as a `dstack` application inside an
Intel TDX confidential VM.

* `Dockerfile` — the campaign image. `linux/amd64`, base image pinned by
  digest, python-flint pinned by URL *and* SHA-256 and re-verified at run time
  against `specifications/PYTHON_FLINT_0_9_UPSTREAM.json`.
* `run_phala_tdx_campaign.sh` — the entry point. Validates the job scope and
  the required inputs, then runs `tools/tg_a7_phala_tdx_workload.py`.

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
