# CH25 Lemma A.7 campaign image for Phala/dstack Intel TDX

Packaging for the cheapest registered campaign (`ch25-a7-boundary`, about
1.6 s of FLINT/Arb compute) so it can run as a `dstack` application inside an
Intel TDX confidential VM.

* `Dockerfile` — the campaign image. `linux/amd64`, base image pinned by
  digest, python-flint pinned by URL *and* SHA-256 and re-verified at run time
  against `specifications/PYTHON_FLINT_0_9_UPSTREAM.json`.
* `run_phala_tdx_campaign.sh` — the entry point. Validates the job scope and
  the required inputs, re-derives the enclave signing key from the dstack
  guest agent onto a container-local tmpfs, then runs
  `tools/tg_a7_phala_tdx_workload.py`. It **creates none of its non-secret
  inputs**: all six must already exist.
* `prelude_phala_tdx_inputs.py` — the in-CVM prelude that creates them.
  Derives the P-256 signing key from the dstack guest agent, commits to its
  public key in the TDX quote's report data, fetches the quote, appraises it
  with the pinned `dcap-qvl` against the reviewed policy, replays the RTMR
  event log against the quote, stages the retained A.7 artifact, and hands
  over. Hard-fails on anything unexpected. It **writes the key nowhere**; its
  second mode, `--derive-key-only`, is what the campaign container runs.
* `emit_phala_tdx_evidence.py` — prints the evidence to stdout as delimited
  base64 at the end of the campaign, from a hardcoded allowlist that cannot
  name key material. `tools/tg_phala_tdx_extract_evidence.py` turns the log
  back into files and verifies every digest. This is the only channel out of
  a dstack CVM: volumes are unreachable and `phala cvms logs` drops the logs
  of containers that have exited.
* `dcap-qvl-policy.json` — the reviewed appraisal policy. The platform
  measurements were filled from the 2026-07-27 discovery run; `rt_mr3` stays
  the `verified-by-event-log-replay` sentinel, because it is a function of the
  compose bytes and a literal pin would be a trap. Delivered to the CVM as
  base64 in an encrypted environment variable, deliberately *not* inside
  `app-compose.json` (it pins RTMR3, which is a function of the compose bytes).
* `docker-compose.yaml`, `app-compose.json` — the dstack deploy manifest,
  **generated** by `tools/tg_phala_tdx_compose.py`. The image is referenced by
  registry digest, never by a tag. The prelude, the entry point and the
  evidence emitter are embedded verbatim, so they are inside the compose hash
  and inside RTMR3, and the campaign service runs those copies rather than the
  ones baked into the image.

## The volume layout, and the mistake it encodes

`campaign-shared` is an **ordinary** named volume. It must never be given
`driver_opts: {type: tmpfs}`: a tmpfs-backed *named* volume is not shared
between containers — each one gets its own fresh, empty tmpfs. The first real
run on Phala TDX hardware passed the whole attestation and then died with
`job-scope.env: No such file or directory` for exactly that reason.

Since the shared volume is therefore disk-backed, nothing secret goes on it.
The signing key is not handed over at all: both containers mount
`/var/run/dstack.sock` and derive it, and the campaign refuses unless what it
derives reproduces the report-data commitment inside the quote. The socket is
not network access; the campaign service keeps `network_mode: none` and
`read_only: true`.

The pinned appraiser is recorded in
`specifications/DCAP_QVL_0_6_1_UPSTREAM.json`.

## What has and has not run on real hardware

A run on 2026-07-27 got through the whole attestation on Phala TDX hardware —
key derivation, quote, `dcap-qvl` appraisal, every pinned platform
measurement, and the RTMR3 event-log replay binding the quote to our
app-compose hash — and then failed in the campaign container on the volume
mistake described above. The layout in this directory is the fix and **has not
been run on TDX hardware**. It is exercised locally by
`tests/test_phala_tdx_first_run.py`, which builds the image and runs the
committed compose entry point verbatim against a mock dstack `GetKey` socket.

The `dcap-qvl` interaction is still exercised only against a stand-in that
prints the schema dcap-qvl v0.6.1 was observed to emit.

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

`tests/test_phala_tdx_first_run.py` builds this image and runs it twice: once
through the image's own entry point, and once through the committed compose
entry point verbatim. Both derive the signing key from a mock dstack `GetKey`
unix socket that returns the committed stand-in scalar, so the receipt is
byte-for-byte the one pinned in Lean; the second run additionally emits the
evidence to stdout and puts it back through
`tools/tg_phala_tdx_extract_evidence.py`. That pair is the readiness check: if
it passes, the only missing ingredients for a real run are Phala credentials
and the retained production A.7 artifact.

A dry run is contained by the Lean enclave pin, not by this directory: the
`ch25A7BoundaryLocalDryRunV1` identity has `attestationAuthority := false`, so
no receipt signed by the stand-in key can reach a campaign theorem.
