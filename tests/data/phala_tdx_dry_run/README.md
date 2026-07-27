# Local dry-run inputs for the Phala/dstack TDX path

**None of this is attestation evidence and none of it is secret.**

* `enclave-signing-key.NOT-SECRET.hex` — a P-256 scalar committed in the clear.
  It stands in for the key `dstack` derives inside a TD. Its public key is
  pinned in Lean as `PhalaTdxEnclave.ch25A7BoundaryLocalDryRunV1`, whose
  `attestationAuthority` is `false`, so no receipt it signs can reach a
  campaign theorem.
* `tdx-quote.NOT-A-QUOTE.bin`, `dcap-qvl-appraisal.NOT-AN-APPRAISAL.json`,
  `dcap-qvl-policy.json`, `dcap-qvl-artifact.sha256` — placeholders occupying
  the slots a real quote, appraisal, policy, and appraiser digest occupy. No
  TDX hardware was involved and no appraisal was performed.
* `a7_boundary.fixture.json.gz` — a freshly generated, genuinely FLINT-verified
  A.7 boundary artifact (16,191 leaves) produced by
  `tools/tg_a7_generate_fixture_artifact.py`. It is **not** the retained
  production artifact `ccc11cec…9f29`, and `require_retained_identity=True`
  correctly rejects it.

See `docs/PHALA_FIRST_RUN.md` for what a real run supplies instead.
