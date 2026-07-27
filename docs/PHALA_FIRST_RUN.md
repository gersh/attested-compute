# First real Phala TDX run: ordered runbook

This is the exact sequence for the first production run of the
`ch25-a7-boundary` campaign inside an Intel TDX confidential VM on Phala
Cloud, and for turning its result into a Lean theorem.

Everything below has been exercised locally except the parts that require a
Phala account. The local dry run is
`tests/test_phala_tdx_first_run.py`; if it passes, the only missing
ingredients are the ones marked **NEEDS PHALA** below.

**Be clear about what "exercised locally" means for the in-CVM prelude.** No
Intel TDX hardware was available when it was written. Its dstack guest-agent
interaction is exercised only against an in-process mock
(`tests/test_phala_tdx_prelude.py`) built from dstack v0.5.3's source and
its own SDKs, and its `dcap-qvl` interaction only against a stand-in that
prints the schema dcap-qvl v0.6.1 was observed to emit. **The real path has
never been executed.** Expect the first attempt to surface at least one
mismatch between the source-derived wire contract and what a running guest
agent actually does; the prelude is written to fail loudly rather than to
paper over it, and the first run is a discovery run by design (section 4b).

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

None of these files is created by the entry point: it requires all seven to
already exist. They are produced inside the CVM by
`proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py`, which runs as a
separate one-shot compose service before the campaign service starts. Section
4 describes it.

**NEEDS THE RETAINED ARTIFACT.** `a7_boundary.json` is not in this
repository and is **not baked into the image** — the published image contains
no `COPY` of it. A production run must supply the retained artifact whose
SHA-256 is `ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29`;
the producer refuses anything else unless `--local-dry-run` is passed, and
`--local-dry-run` additionally requires the environment marker
`SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=1`. The fixture generator
`tools/tg_a7_generate_fixture_artifact.py` exists only to make the local dry
run exercise the real replay code; it must never be used for a production
claim.

**How the artifact reaches the CVM.** The prelude fetches it over HTTPS from
`TG_A7_ARTIFACT_URL` and refuses to continue unless the bytes hash to
`ccc11cec…9f29` and are exactly 1,494,999 bytes long. The expected digest is a
constant in the prelude source, which is measured into the compose hash, so
the delivery host is **not trusted**: it can withhold the artifact, but it
cannot substitute one. (The producer then re-checks the same digest, and the
Lean-side registered input commits to it a third time.) A local path may be
given instead with `TG_A7_ARTIFACT_PATH`, under the identical digest check;
that is the hook a future sidecar image referenced by digest would use.

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

The first four, plus the two `TG_` variables, are literals in
`docker-compose.yaml`, so they are inside the compose hash and inside RTMR3 —
the quote covers this run's challenge.

The last two **cannot** be literals there, and the reason is worth stating
because it looks like an omission: `compose_hash` is the SHA-256 of the
document that would have to contain it. Instead the prelude reads them from
the guest agent's `/Info`, checks them against the `app-id` and `compose-hash`
events the quote actually attests in RTMR3 (see section 4), and writes them to
`job-scope.env`, which the campaign service's shell sources before `exec`ing
the entry point. `require_phala_tdx_worker` therefore sees exactly the six
variables above, unchanged, and the two it could not be handed as literals
came from the attested event log rather than from anyone's assertion.

These are consumed by
`tg_verifier.campaign_io.require_phala_tdx_worker`, a route that is entirely
separate from `require_azure_measured_worker*`: different scope string,
different variables, different exception type, no shared code. A job carrying
Azure measured-runner variables is rejected outright rather than accepted by
either route. `tests/test_phala_tdx_first_run.py::GuardSeparationTests` checks
both directions.

---

## 4. Run the campaign

**NEEDS PHALA.** Deploy the manifest as a dstack app on Phala Cloud (CVM with
Intel TDX). The compose file defines two one-shot services. The second has

```yaml
depends_on:
  prelude:
    condition: service_completed_successfully
```

so a failed appraisal is not followed by a receipt: the campaign container is
never started at all.

### 4a. What the prelude does, in order

`proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py`, embedded verbatim
in the compose document and therefore measured into RTMR3:

1. **Ask `/Info`** for the dstack app id and app-compose hash.
2. **Derive the signing key.** `POST /GetKey` with the domain-separated path
   `sparkinterval/ch25-a7-boundary/enclave-signing-key/v1`. dstack returns the
   32 raw bytes of `HKDF-SHA256(salt="RATLS", ikm=app key, info=path)` — the
   same bytes its own `derive_ecdsa_key_pair_from_bytes` feeds to
   `p256::SecretKey`, so reading them as a P-256 scalar is dstack's own use of
   that KDF output, and it is **deterministic** in the app key and the path.
   (`GetTlsKey` is *not* usable here: it seeds from `SystemRandom` and so
   returns a different key on every call.) The scalar is validated to lie in
   `[1, n)` for the P-256 group, written to `enclave-signing-key.hex` mode
   `0400` on a **tmpfs** volume, and never printed, logged, or copied.
   About one derivation path in 2^32 yields a value at or above the P-256
   group order; the prelude refuses it and tells you to bump the path suffix
   rather than reducing modulo the order.
3. **Compute the report-data commitment.**

   ```
   sha256( "sparkinterval.phala-tdx-report-data.v1\n"
           + "enclave_public_key=" + sha256(<uncompressed SEC1 pubkey hex>) + "\n"
           + "challenge_nonce="    + sha256(<challenge>)                    + "\n"
           + "job_binding_sha256=" + sha256(<job binding>)                  + "\n" )
   ```

   `tg_verifier.phala_tdx_receipt.report_data_hash` computes exactly this, and
   the prelude **calls that function** rather than re-deriving the formula; it
   additionally asserts at run time that the imported module still produces
   the preimage written above, so a shadowed or stale module fails closed.
   This is the only thing tying the quote to the signing key; without it a
   genuine quote and a genuine signature from unrelated parties would both
   verify while proving nothing jointly.
4. **Fetch the TDX quote.** `POST /GetQuote` with the 32-byte commitment
   right-padded to 64 bytes, saved as `tdx-quote.bin`. dstack's JSON layer has
   no `deny_unknown_fields` and defaults every absent field, so a misspelled
   request key would silently yield a quote over 64 zero bytes; the prelude
   therefore checks the **echoed** `report_data` and, later, the `report_data`
   the appraiser reads out of the quote itself.
5. **Appraise the quote.** `dcap-qvl v0.6.1` (pinned by SHA-256; see
   `specifications/DCAP_QVL_0_6_1_UPSTREAM.json`) is fetched, digest-checked,
   and run twice: plain `verify`, whose JSON becomes
   `dcap-qvl-appraisal.json` and whose non-zero exit is fatal, and
   `verify --strict`, whose verdict is retained as evidence. Strict is
   evidence rather than a gate because dcap-qvl's built-in strict policy
   rejects any DYNAMIC_PLATFORM / CACHED_KEYS / SMT platform — running it
   against upstream's own sample TDX quote on 2026-07-27 failed with *"Dynamic
   platform is not allowed by policy"*. Set `require_dcap_qvl_strict` in the
   policy to make it a gate.
6. **Replay the event log against the quote.** Every RTMR3 entry is re-hashed
   with dstack's `sha384(event_type_le || ":" || event || ":" || payload)` so
   the name/payload columns cannot be relabelled, all four IMRs are replayed
   and must equal the RTMRs the quote attests, and the `app-id` and
   `compose-hash` events in the boot chain — everything up to `system-ready`,
   so a post-boot `EmitEvent` cannot spoof them — must equal what `/Info`
   reported. **This is what binds the quote to these compose bytes.**
7. **Apply the reviewed policy** (section 4b).
8. **Stage the retained A.7 artifact** under its pinned digest, write
   `registered-input.json`, and hand over.

Anything unexpected is a hard failure: the prelude exits non-zero, writes no
`job-scope.env`, and the campaign never runs.

### 4b. The appraisal policy, and why the first run fails on purpose

`proof_build/ch25_a7_phala_tdx/dcap-qvl-policy.json` is delivered as
base64 in `TG_DCAP_QVL_POLICY_B64` (a dstack encrypted env listed in
`allowed_envs`), **not** inside the compose document. That placement is
forced: the policy pins RTMR3, and RTMR3 is a function of the compose bytes,
so a policy embedded in the compose could never be filled in.

Because the policy is therefore unmeasured, the prelude is built so that the
policy can only ever **tighten**. The floor is hardcoded in the measured
prelude and no policy value removes any of it: TDX TEE type, an accepted
report kind, non-debuggable TD, the report-data binding, the event-log replay,
and the RTMR3 app-id / compose-hash bindings. The policy adds pinned
measurements, TCB-status whitelists, an exhaustive advisory whitelist, and the
quoting-enclave identity. Its SHA-256 enters the signed receipt and is pinned
in Lean as `quoteAppraisalPolicyHash`, so substitution is detectable at the
promotion review.

Every measurement in the shipped template is an explicit `TODO:` — no
wildcards, no fabricated values, and deliberately no example values, because
an example in a measurement field is a paste hazard. So:

* **Run 1 (discovery).** With `first_run_measurement_discovery: false` — the
  shipped setting — the prelude performs the whole cryptographic appraisal,
  **prints every observed measurement and the quoting-enclave identity**, and
  then exits non-zero. Nothing is produced. Fill the pins from that output,
  cross-checking MRTD and RTMR0–2 against the measurements Phala publishes for
  the dstack OS image the CVM booted.
* Setting `first_run_measurement_discovery: true` lets a run proceed with
  unpinned measurements, but it is not silent: a banner is printed,
  `/workspace/retained/evidence/MEASUREMENTS-NOT-PINNED` is written, and the
  flag is inside the policy bytes whose SHA-256 the receipt signs — so the
  receipt itself proves the measurements were unpinned. **A receipt produced
  in discovery mode must never be promoted to the Lean production pin.**
* **Run 2 (attested).** Pins filled, discovery false. Editing the policy does
  not change the compose hash, so RTMR3 is unchanged and the pin from run 1
  still holds. That is the whole reason the policy lives outside the compose.

### 4c. Outputs

Under `/workspace/out/output`:

* `registered-result.txt` — the registered result bytes, `true`;
* `enclave-receipt.json` — the signed statement;
* `work/a7-replay.json` — the normalized FLINT/Arb replay report.

Under `/workspace/retained/evidence` (an ordinary volume, so it survives the
containers): `dstack-info.json`, `dstack-event-log.json`,
`dcap-qvl-decode.json`, `dcap-qvl-verify.stderr`, `dcap-qvl-strict.json`,
`rtmr-replay.json`, `prelude-summary.json`, and the `dcap-qvl` binary itself.

Retrieve all of it, plus `tdx-quote.bin`, `dcap-qvl-appraisal.json`,
`dcap-qvl-policy.json`, and `dcap-qvl-artifact.sha256` from
`/workspace/staging/input`, **before destroying the CVM** — the staging volume
is a tmpfs and the evidence volume dies with the VM.

---

## 4d. Deploying: the manifest, and the registry

`proof_build/ch25_a7_phala_tdx/docker-compose.yaml` and `app-compose.json` are
generated by `tools/tg_phala_tdx_compose.py`; the committed pair is a template
whose challenge and job binding are refusal sentinels, so it cannot be
deployed by accident. `tests/test_phala_tdx_manifest.py` fails if the
committed files drift from the generator or from the prelude source.

`app-compose.json` sets `no_instance_id: true` on purpose: it removes the
per-instance random value from the RTMR3 chain, which is what makes RTMR3 a
function of the app id and compose hash alone, and therefore pinnable at all.

**The registry.** As of 2026-07-27 an anonymous pull of
`ghcr.io/gersh/sparkinterval-ch25-a7-phala-tdx@sha256:4e6029a3…` returns
`403 DENIED` — the package is **private**, so a CVM cannot pull it as things
stand. Two options:

1. **Make the GHCR package public. This is the recommendation.**
   Confidentiality is not a goal of this path — the axiom's docstring says so
   — and integrity does not come from registry access control: it comes from
   the digest, which is pinned in the compose (measured into RTMR3), in the
   receipt, and in the Lean enclave identity. A public image cannot be
   substituted.
2. Supply registry credentials. Note that dstack v0.5.3's built-in
   `docker_config` path does **not** work for GHCR: `setup_docker_account`
   runs `docker login -u <user> -p <token>` with no server argument, which
   authenticates to Docker Hub, and `docker_config.registry` only configures a
   registry *mirror*. The working route is a `pre_launch_script` in
   `app-compose.json` (it is sourced by `app-compose.sh` before
   `docker compose up`, and it *is* inside the compose hash):

   ```json
   "pre_launch_script": "echo \"$GHCR_TOKEN\" | docker login ghcr.io -u <user> --password-stdin\n"
   ```

   with `GHCR_TOKEN` added to `allowed_envs` and supplied as encrypted env.
   This puts a GitHub token inside the CVM and adds an unmeasured moving part
   for no integrity gain, which is why option 1 is preferred.

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

**Preconditions for promoting a receipt to this pin.** Do not fill any field
above unless all of the following hold, and record that you checked them:

* the retained `dcap-qvl-policy.json` has `first_run_measurement_discovery`
  set to `false` and **no** remaining `TODO:` value;
* `/workspace/retained/evidence/MEASUREMENTS-NOT-PINNED` is absent from the
  retained evidence, and `prelude-summary.json` reports
  `"measurements_pinned": true`;
* the retained `rtmr-replay.json` shows the replayed RTMRs equal to the ones
  the quote attests, and the RTMR3 boot chain's `app-id` and `compose-hash`
  equal the receipt's `app_id` and `compose_hash`;
* the policy's `mr_td` and `rt_mr0..2` were cross-checked against the
  measurements Phala publishes for the dstack OS image version that booted —
  the prelude cannot do this for you, since it only ever sees one machine;
* `dcap-qvl-strict.json` was read and its verdict consciously accepted.

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
- [ ] The GHCR package made public, or a `pre_launch_script` login in place
      (section 4d) — **the package is private today and the CVM cannot pull it**
- [ ] The retained production `a7_boundary.json` (`ccc11cec…9f29`) published at
      an HTTPS URL the CVM can reach — **NEEDS THE OPERATOR**
- [ ] An unpredictable challenge nonce and a job binding chosen and recorded
      before the run
- [ ] `python3 -m unittest tests.test_phala_tdx_first_run` passing locally
- [ ] `python3 -m unittest tests.test_phala_tdx_axiom_off_cone` passing
- [ ] `python3 -m unittest tests.test_phala_tdx_prelude` passing
- [ ] `python3 -m unittest tests.test_phala_tdx_manifest` passing
- [ ] `python3 tools/audit_lean_source.py` passing

The `dcap-qvl` policy is **not** on this list as something to have ready: its
measurement pins cannot be known before the first run. Discovering them is
what run 1 is for (section 4b).

---

## The exact command sequence

```bash
# 0. Local gates.
python3 -m unittest tests.test_phala_tdx_first_run \
                    tests.test_phala_tdx_axiom_off_cone \
                    tests.test_phala_tdx_prelude \
                    tests.test_phala_tdx_manifest
python3 tools/audit_lean_source.py

# 1. Choose the campaign scope and generate the manifest.
CHALLENGE=$(openssl rand -hex 32)
JOB_BINDING=$(openssl rand -hex 32)
ISSUED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'challenge=%s\njob_binding=%s\nissued_at=%s\n' \
    "$CHALLENGE" "$JOB_BINDING" "$ISSUED_AT" > run-scope.txt   # retain this

python3 tools/tg_phala_tdx_compose.py \
    --challenge "$CHALLENGE" \
    --job-binding "$JOB_BINDING" \
    --issued-at "$ISSUED_AT" \
    --out-dir ./deploy
# prints the compose hash and the app id; retain both.

# 2. Publish the retained artifact and make the image pullable.
sha256sum /path/to/a7_boundary.json     # must be ccc11cec…9f29
#   upload it somewhere HTTPS; export the URL as ARTIFACT_URL
#   make ghcr.io/gersh/sparkinterval-ch25-a7-phala-tdx public (section 4d)

# 3. Discovery run.  The policy still has every measurement as TODO.
POLICY_B64=$(base64 -w0 proof_build/ch25_a7_phala_tdx/dcap-qvl-policy.json)
#   deploy ./deploy/app-compose.json to Phala Cloud with encrypted env
#     TG_DCAP_QVL_POLICY_B64=$POLICY_B64
#     TG_A7_ARTIFACT_URL=$ARTIFACT_URL
#   the prelude will FAIL after printing the observed measurements.
#   Copy them out of the prelude container's log.

# 4. Fill the policy and re-run.
#   paste the observed values into dcap-qvl-policy.json,
#   leave first_run_measurement_discovery false,
#   re-base64 it, redeploy the SAME app-compose.json (unchanged: the policy is
#   not part of it, so the compose hash and RTMR3 do not move).

# 5. Retrieve everything BEFORE destroying the CVM.
#   /workspace/out/output/{registered-result.txt,enclave-receipt.json,work/a7-replay.json}
#   /workspace/staging/input/{tdx-quote.bin,dcap-qvl-appraisal.json,
#                             dcap-qvl-policy.json,dcap-qvl-artifact.sha256}
#   /workspace/retained/evidence/*        (NOT enclave-signing-key.hex)

# 6. Pin the enclave identity in Lean (section 6) and close the theorem
#    (section 7).  This is the trust-boundary review event.
```

**Never retrieve `enclave-signing-key.hex`.** It is the one file that must die
with the CVM.
