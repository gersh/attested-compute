# First real Phala TDX run: ordered runbook

This is the exact sequence for the first production run of the
`ch25-a7-boundary` campaign inside an Intel TDX confidential VM on Phala
Cloud, and for turning its result into a Lean theorem.

Everything below has been exercised locally except the parts that require a
Phala account. The local dry run is
`tests/test_phala_tdx_first_run.py`; if it passes, the only missing
ingredients are the ones marked **NEEDS PHALA** below.

Read `SparkInterval/Execution/PhalaTdxCampaignCertificate.lean` first: the
docstring on `phalaTdxAttestedRun_sound` states precisely what this path
trusts.

---

## 0. What this path is, in one paragraph

The container runs the registered CH25 Lemma A.7 producer and signs a
canonical statement of what it computed, using the P-256 key that `dstack`
derives inside the TD. Outside, `dcap-qvl` appraises the TDX quote against a
pinned policy. Lean verifies **only** the P-256 signature against a
source-pinned public key, plus the bindings between that signature, the closed
registered invocation, and the result. **Lean never parses a quote**, a PCK
certificate chain, a TCB level, or a QE identity, and it must never be
described as having done so. This is the same division of labour as the Azure
path, where MAA appraises the attestation outside Lean and Lean checks a
signature.

---

## 1. Build and publish the campaign image

The image is `linux/amd64` because Intel TDX is an x86 feature.

```bash
docker build --platform linux/amd64 \
  -f proof_build/ch25_a7_phala_tdx/Dockerfile \
  -t <registry>/sparkinterval-ch25-a7-phala-tdx:<version> .
docker push <registry>/sparkinterval-ch25-a7-phala-tdx:<version>
docker buildx imagetools inspect <registry>/sparkinterval-ch25-a7-phala-tdx:<version>
```

On a non-amd64 build host, register emulation first:

```bash
docker run --privileged --rm tonistiigi/binfmt --install amd64
```

**Record the registry digest** (`sha256:…`) from `imagetools inspect`. Every
later step references the image by that digest and never by a tag. It is
pinned in three places:

| Where | Field |
| --- | --- |
| dstack `app-compose.json` | the image reference of the campaign service |
| the signed receipt | `image_digest` |
| `SparkInterval/Execution/PhalaTdxAttestation.lean` | `PhalaTdxEnclave.pin.imageDigest` |

---

## 2. Assemble the campaign inputs

The container reads everything from `/workspace/input` and writes nothing
outside `/workspace`. Required files:

| File | What it is |
| --- | --- |
| `registered-input.json` | the exact registered input bytes; the producer compares them literally |
| `a7_boundary.json` | the **retained production A.7 artifact**, sha256 `ccc11cec…9f29` |
| `enclave-signing-key.hex` | the dstack-derived P-256 scalar, 64 lowercase hex digits |
| `tdx-quote.bin` | the TDX quote fetched from the dstack guest agent |
| `dcap-qvl-appraisal.json` | the `dcap-qvl` output for that quote |
| `dcap-qvl-policy.json` | the reviewed appraisal policy |
| `dcap-qvl-artifact.sha256` | the digest of the `dcap-qvl` binary that produced the appraisal |

**NEEDS THE RETAINED ARTIFACT.** `a7_boundary.json` is not in this
repository. A production run must supply the retained artifact whose SHA-256
is `ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29`; the
producer refuses anything else unless `--local-dry-run` is passed, and
`--local-dry-run` additionally requires the environment marker
`SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=1`. The fixture generator
`tools/tg_a7_generate_fixture_artifact.py` exists only to make the local dry
run exercise the real replay code; it must never be used for a production
claim.

Note the ordering problem the quote creates: the quote's report data commits
to the public key and the challenge, and the signature commits to the quote's
digest. So the run is: derive key → fetch quote with the report-data
commitment → appraise the quote → run the campaign with quote and appraisal in
hand. Section 4 spells this out.

---

## 3. Set the dstack job scope

The campaign entry point refuses to run without an exact TDX job binding. The
launcher (the dstack `app-compose` entry point, not the job) sets:

| Variable | Value |
| --- | --- |
| `SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE` | `sparkinterval.phala-tdx-measured-worker.v1` |
| `SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND` | `phala_dstack_tdx_cpu` |
| `SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE` | 64 hex digits, unpredictable, chosen before the run |
| `SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256` | 64 hex digits binding the job definition |
| `SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID` | the dstack app id, 40 hex digits |
| `SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH` | SHA-256 of the `app-compose.json` measured into the TD |

plus `TG_FINAL_IMAGE_REFERENCE=sha256:<image digest>` and an RFC 3339 UTC
`TG_ISSUED_AT`.

These are consumed by
`tg_verifier.campaign_io.require_phala_tdx_worker`, a route that is entirely
separate from `require_azure_measured_worker*`: different scope string,
different variables, different exception type, no shared code. A job carrying
Azure measured-runner variables is rejected outright rather than accepted by
either route. `tests/test_phala_tdx_first_run.py::GuardSeparationTests` checks
both directions.

---

## 4. Run the campaign

**NEEDS PHALA.** Deploy the image as a dstack app on Phala Cloud (CVM with
Intel TDX). Inside the CVM, in this order:

1. **Derive the signing key.** Ask the dstack guest agent for the app's
   derived ECDSA P-256 key. Write the scalar to
   `/workspace/input/enclave-signing-key.hex`. It must never leave the TD.
2. **Compute the report-data commitment.**

   ```
   sha256( "sparkinterval.phala-tdx-report-data.v1\n"
           + "enclave_public_key=" + sha256(<uncompressed SEC1 pubkey hex>) + "\n"
           + "challenge_nonce="    + sha256(<challenge>)                    + "\n"
           + "job_binding_sha256=" + sha256(<job binding>)                  + "\n" )
   ```

   `tg_verifier.phala_tdx_receipt.report_data_hash` computes exactly this.
   This is the only thing tying the quote to the signing key; without it a
   genuine quote and a genuine signature from unrelated parties would both
   verify while proving nothing jointly.
3. **Fetch the TDX quote** with that 32-byte value as the report data, and
   save it as `/workspace/input/tdx-quote.bin`.
4. **Appraise the quote** with `dcap-qvl` against the reviewed policy, saving
   the output as `/workspace/input/dcap-qvl-appraisal.json`. If the appraisal
   fails, stop — nothing downstream is meaningful.
5. **Run the entry point**, `proof_build/ch25_a7_phala_tdx/run_phala_tdx_campaign.sh`
   (the image's `ENTRYPOINT`), with no `--local-dry-run`.

Outputs, under `/workspace/output`:

* `registered-result.txt` — the registered result bytes, `true`;
* `enclave-receipt.json` — the signed statement;
* `work/a7-replay.json` — the normalized FLINT/Arb replay report.

Retrieve all three, plus `tdx-quote.bin`, `dcap-qvl-appraisal.json`,
`dcap-qvl-policy.json`, and the `dcap-qvl` binary digest.

---

## 5. Retain the evidence

Keep, immutably and together:

| Artifact | Why |
| --- | --- |
| `tdx-quote.bin` | the only evidence the TD existed and was measured; unparseable by Lean, so its retention is the whole record |
| `dcap-qvl-appraisal.json` | the appraisal Lean's axiom assumes was performed and passed |
| `dcap-qvl-policy.json` | which measurements, TCB level, and QE identity were required |
| the `dcap-qvl` binary (or its digest and provenance) | which appraiser was used |
| `enclave-receipt.json` | the signed statement Lean verifies |
| `registered-result.txt`, `work/a7-replay.json` | what the campaign computed |
| the `app-compose.json` and the image digest | what was measured into the quote |

The receipt commits to the SHA-256 of the first four, so a later substitution
is detectable but a later *loss* is not recoverable. Losing the quote or the
appraisal does not invalidate the signature, but it destroys the evidence for
assumption 4 of the axiom, and the theorem should then be treated as
unsupported.

---

## 6. Pin the enclave identity in Lean

**This is the trust-boundary review event.** Edit
`PhalaTdxEnclave.pin .ch25A7BoundaryProductionV1` in
`SparkInterval/Execution/PhalaTdxAttestation.lean`, filling in:

| Field | Value |
| --- | --- |
| `appId` | the dstack app id |
| `composeHash` | SHA-256 of the measured `app-compose.json` |
| `imageDigest` | `sha256:<registry image digest>` from step 1 |
| `enclavePublicKeyHex` | the uncompressed SEC1 P-256 public key derived by dstack, 130 hex digits |
| `quoteAppraisalPolicyHash` | SHA-256 of `dcap-qvl-policy.json` |
| `quoteAppraisalArtifactHash` | SHA-256 of the `dcap-qvl` binary |

`attestationAuthority` is already `true` for this constructor; today the empty
`enclavePublicKeyHex` is what makes every check fail closed
(`phalaTdxOutcomeCheck_ch25A7BoundaryProductionV1_eq_false` proves it).

Do **not** touch `ch25A7BoundaryLocalDryRunV1`. Its
`attestationAuthority := false` is what stops a laptop-generated key from ever
reaching a campaign theorem, and the dry-run test depends on it.

---

## 7. Close the campaign theorem

Transcribe the receipt's `signed_fields` into a `PhalaTdxReceipt` literal —
`SparkInterval/Tests/PhalaTdxDryRunTest.lean` shows the field-by-field mapping —
and apply:

```lean
theorem myRun : CertifiedCH25A7BoundaryPhalaTdx productionReceipt :=
  certifyCH25A7BoundaryPhalaTdx rfl (by decide +kernel)
```

The `rfl` discharges `attestationAuthority = true` once the production pin is
installed.

On the second argument: closing the whole check with `decide +kernel` is the
right target but was **not achievable within a 16 GB budget** on the machine
used for the dry run. The P-256 verification alone kernel-reduces in about
6.6 s; what exceeds the budget is the nineteen in-kernel SHA-256 evaluations
over strings that the composite check performs. Options, in order of
preference:

1. run the kernel check on a machine with a larger `-M` budget, and record
   the measurement;
2. split the proof so the P-256 verification is kernel-checked separately
   (`dryRunSignature_kernelChecked` in the dry-run test is the pattern) and
   only the SHA-256 conjuncts use `native_decide`;
3. use `native_decide` for the whole check, accepting
   `Lean.ofReduceBool` in the theorem's axiom set.

Whichever is chosen, run `#print axioms` on the resulting theorem and record
it. Expect `phalaTdxAttestedRun_sound` plus the base trio, plus a native
reduction axiom if option 2 or 3 was used.

---

## 8. Decide, explicitly, whether this goes on the live cone

By default it does not, and `tests/test_phala_tdx_axiom_off_cone.py` enforces
that: no capstone may transitively import the Phala layer, and
`phalaTdxAttestedRun_sound` must not appear in any capstone's `#print axioms`.
Azure remains the only path that discharges an atom.

Putting a TDX-derived result on the cone means editing that test on purpose,
and means accepting a second, differently-rooted hardware trust assumption
alongside the AMD SEV-SNP one. That is a decision for the owner, not a
consequence of a successful run.

---

## What the resulting theorem does and does not establish

**Does establish**, conditional on the axiom's assumptions:

* the closed registered invocation `ch25A7BoundaryProductionV1` ran and
  returned exactly `true`;
* therefore `A7BoundarySourceSemantics.SourceClaim` — the source-shaped CH25
  Lemma A.7 rectangle-boundary estimate — holds, via the existing
  axiom-free reduction `ch25A7BoundaryProductionV1_sourceClaim`.

**Does not establish:**

* anything about Mathlib's `riemannZeta`. The A.7 replay is a FLINT/Arb
  computation; the report itself records
  `mathlib_zeta_realization_theorem_present: false` and
  `lean_atom_discharged: false`. The realization obligation is unchanged by
  running the campaign in a TEE.
* that the TDX quote is valid. Lean did not look at it. That is assumption 4
  of the axiom, discharged by the retained `dcap-qvl` appraisal.
* that Phala behaved. It establishes that *if* the pinned measurement ran,
  it produced this result. Phala can refuse to run the job or withhold the
  output; it cannot substitute a different image without changing the
  measurement in the quote, which the pinned appraisal policy would reject.
* anything about the confidentiality of the input or output. This path is
  used for integrity only.

---

## Checklist before the first run

- [ ] Phala Cloud account and a CVM with Intel TDX — **NEEDS PHALA**
- [ ] A container registry the CVM can pull from, and the pushed image digest
- [ ] The retained production `a7_boundary.json` (`ccc11cec…9f29`)
- [ ] A reviewed `dcap-qvl` policy pinning the expected measurement set, TCB
      level, and QE identity, plus the `dcap-qvl` binary and its digest
- [ ] An unpredictable challenge nonce chosen and recorded before the run
- [ ] `python3 -m unittest tests.test_phala_tdx_first_run` passing locally
- [ ] `python3 -m unittest tests.test_phala_tdx_axiom_off_cone` passing
- [ ] `python3 tools/audit_lean_source.py` passing
