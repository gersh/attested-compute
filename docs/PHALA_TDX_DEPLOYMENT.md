# Running an attested computation on Phala / dstack

This is the operational half of
[`TRUSTING_THE_ENCLAVE.md`](TRUSTING_THE_ENCLAVE.md): what actually happens when
a computation is run inside an Intel TDX confidential VM, which platform
features are used, which are deliberately not, and where the trust boundary
falls at each step.

Phala Cloud is one deployment target, not a dependency of the approach. It runs
[dstack](https://github.com/Dstack-TEE/dstack), an open framework for
confidential containers; anything speaking the same guest-agent protocol would
serve.

---

## 1. What the platform provides

Inside the VM, applications talk to a **guest agent** over the unix socket
`/var/run/dstack.sock` — HTTP with JSON bodies, methods as paths. The four that
matter here:

| method | request | what it gives us |
| --- | --- | --- |
| `POST /Info` | `{}` | `app_id`, `compose_hash`, `instance_id`, and `tcb_info` containing the RTMR event log |
| `POST /GetQuote` | `{"report_data": <128 hex>}` | the v4 TDX quote, hex-encoded, over measurements **and** our 64 chosen bytes |
| `POST /GetKey` | `{"path", "purpose"}` | 32 bytes of deterministically derived key material, plus a `signature_chain` linking it to the app identity |
| — | — | the socket is not network access; it works under `network_mode: none` |

`report_data` is at most 64 bytes and is zero-padded on the right. We send the
padded value so the echo comparison is exact.

### Two platform features we deliberately do not use

**`/Sign`.** dstack will sign for you, but offers only `ed25519`, `secp256k1`
and `secp256k1_prehashed`. The Lean side has a P-256 verifier and no other, so
adopting `/Sign` would mean writing and reviewing new verified elliptic-curve
code before any receipt could be checked at all. We take key *material* from
`/GetKey` and sign with our own P-256 implementation instead.

This is sound because of a documented property: of `/GetKey`'s `algorithm`
field, upstream says *"this selects how the same derived 32-byte material is
interpreted; it does not domain-separate the derivation."* The same bytes back
every algorithm, so reading them as a P-256 scalar is as legitimate as reading
them as an ed25519 seed.

⚠ It also means **a shared derivation path is key reuse across algorithms.**
The upstream docs warn about this. Use a dedicated path — ours is
`sparkinterval/compcert-run/p256` — and let nothing else touch it.

**In-enclave `dcap-qvl` appraisal.** Verifying the quote *inside* the VM needs
Intel's collateral (TCB info, QE identity, CRLs), which needs network, which
conflicts with running the container without egress. This is not hypothetical:
an earlier run's strict appraisal could not fetch collateral and recorded
`strict_exit_status = 1` beside `exit_status = 0`. We appraise **outside**
instead, which is also the stronger position — the enclave does not vouch for
itself.

## 2. The compose is the unit of measurement

dstack wraps your `docker-compose.yaml` in an **app-compose document**, and
`SHA256` of that document's raw bytes is the `compose_hash` the CPU measures
into `mr_config_id` as `01 ‖ compose_hash ‖ 15 zero bytes`, and records again as
an `RTMR3` event.

So **whatever is inside the compose is measured.** We exploit that directly:
the artifacts are embedded in it as gzip+base64, along with their SHA-256
digests and the expected results. The entry point is embedded verbatim too.
Nothing is fetched at run time that isn't measured.

The canonicalization is specified in dstack's `docs/normalized-app-compose.md`
— keys sorted, no extra whitespace, `ensure_ascii=False` — and the measured
document matches `json.dumps(d, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` byte for byte.

⚠ **Do not reconstruct the document from the Cloud API.** Its JSON view has a
different key set and is not byte-faithful; 224 candidate re-serializations of
it failed to reproduce the measured hash. Read the real bytes from
`/tapp/app-compose.json` (also at `/dstack/app-compose.json`) *inside* the VM,
where they are exactly what was hashed.

**Size limit:** `docker_compose_file` plus `pre_launch_script` must stay under
**200 KB**. Beyond that, reference an image by digest and record that digest in
the signed statement.

## 3. What the enclave does, in order

1. **Decode and check.** Every embedded artifact is decoded and its SHA-256
   compared against the digest the compose declares. A mismatch refuses
   *before anything executes*.
2. **Run.** Each artifact runs; exit status and the SHA-256 of its whole
   transcript are recorded. Exit 0 means agreement, 1 disagreement, anything
   else abnormal — and abnormal is never read as a verdict.
3. **Compare against pinned expectations.** Both are checked against values
   pinned in the compose, so the success criterion is *measured* rather than
   left to the binary's own say-so. An artifact that exits 0 while printing
   different numbers fails here.
4. **Differentially rebuild.** Sources are recompiled with the enclave's own
   compiler and the transcripts diffed against the verified-compiler output. A
   wrong-code bug would have to hit both toolchains identically.
5. **Derive the signing key** from `/GetKey` on the dedicated path.
6. **Bind and quote.** `report_data = H(public key, statement)`, then
   `/GetQuote`. The hardware now attests *which key signed* **and** *what was
   claimed*.
7. **Sign** one receipt per artifact, and emit everything.

## 4. Getting evidence out

A container that exits takes its logs with it, and volumes are not reachable
from outside. So the only channel is **stdout of a container that stays
alive**, and evidence travels as delimited base64 blocks, each carrying its own
name, byte count and SHA-256:

```
<MARKER> BEGIN {"name":"tdx-quote.bin","sha256":"…","bytes":5010}
<MARKER> DATA  <base64…>
<MARKER> END   {"name":"tdx-quote.bin","sha256":"…"}
```

The marker is located *within* the line rather than anchored to its start,
because the log tool prefixes timestamps. Measured capacity: a **553 KB** log
came back whole, so the ~64 KiB cap in older notes no longer applies.

## 5. Lifecycle and cost

```
build artifacts → generate compose → rehearse against a mock agent
   → deploy → poll for the completion marker → capture evidence
   → verify offline → DESTROY
```

**Destroy, never stop** — retained disk keeps billing while stopped.

⚠ `phala cvms delete` prompts for confirmation even with stdin closed, and has
no `--yes`, so unattended it silently does nothing. Delete through the REST API
(`DELETE /api/v1/cvms/<id>`, expect 204) and **confirm the status code**. A
missed teardown once left a VM billing until someone noticed.

Cost is negligible and should not shape decisions: a `tdx.medium` run of this
size is about **$0.005**, and eight runs across a full development session came
to **$0.0174**.

### Rehearse first — this is not optional

Extract the entry point from the **committed** compose and run it against a mock
guest agent before spending anything. "The repository has a script that does X"
is not evidence the script runs: an earlier project's first signed run cost two
deployments to a script that had never been executed. Our rehearsal has since
caught, in order:

* `apt-get --no-install-recommends gcc` not pulling in `libc6-dev`;
* `[ -f x ] && cmd` as the last command under `set -e`, which exits the script
  before the completion marker — a deploy would poll for twenty minutes, give
  up, and leave the VM billing;
* `set -e` not being function-scoped, so a refusal inside a function exited
  before the marker: an **invisible refusal**, the worst way for a check to
  fail;
* capturing output with `$(…)` and re-emitting with `printf`, which fabricates a
  trailing newline and made every empty transcript hash wrongly.

## 6. Other operational gotchas

* **Do not pass `--node-id`.** The CLI forwards it as `teepod_id` and the
  mapping is not what you expect; auto-selection works.
* **Escape `$` as `$$`** in anything embedded in the compose — compose runs its
  own interpolation pass first and aborts on `${VAR:?msg}`.
* **A tmpfs-backed *named* volume is not shared between containers**; each gets
  its own empty one. Use an ordinary named volume for cross-container data and
  service-level `tmpfs:` for secrets.
* **Pin the base image by digest.** A moved tag changes what ran without
  changing anything you recorded.
* **Take the event log from `/Info`'s `tcb_info`.** Upstream documents
  `/GetQuote`'s `event_log` as carrying digests (only RTMR0–2 payloads are
  stripped), but the `/Info` route is what we verify against.

## 7. Where the trust boundary falls

| step | who could interfere | what stops them |
| --- | --- | --- |
| VM memory and execution | the cloud host, the hypervisor | Intel TDX memory encryption and integrity |
| what code is loaded | whoever deploys | `mr_config_id` and the RTMR3 event: one changed byte changes the measurement |
| which binary runs | anyone with compose access | the in-enclave digest check, plus the digests inside `report_data` |
| the results | the container itself | `report_data`, signed by the CPU |
| who signed the receipt | anyone with a keypair | the pin lookup — a key not in the reviewed source table cannot count |
| the quote itself | — | the Intel PKI, up to a fingerprint pinned in source |

**What you still trust:** Intel's TDX implementation and PKI; the dstack guest
agent, which derives the key and assembles `report_data` and which runs inside
the measured VM but is not measured by us; and the human judgement recorded in
the pin table. Phala as an operator is *not* on that list for confidentiality
or integrity of the computation — that is what TDX is for — but they do control
availability, and the KMS/key-provider design is dstack's, which we have not
independently reviewed.

Full detail, including what each verification failure would actually mean, is
in [`TRUSTING_THE_ENCLAVE.md`](TRUSTING_THE_ENCLAVE.md).

## 8. Reference implementation

The pipeline is `attestation/phala/`:

| file | what it is |
| --- | --- |
| `build_compose.py` | generates the measured compose from a deployment manifest |
| `enclave_run.sh` | the in-enclave entry point, embedded verbatim in that compose |
| `mock_dstack.py` | a stand-in guest agent, for rehearsal only |
| `dry_run.sh` | runs the **committed** entry point against the mock |
| `deploy.sh` | deploy, capture, verify, destroy |
| `verify_run.py` | the offline verifier |
| `negative_test.sh` | requires every gate to refuse what it must |

It names no artifact and no consumer: a deployment is a `deployment.json`
manifest plus its artifacts, and lives wherever its owner keeps it.

```sh
attestation/phala/build_compose.py --manifest <dir>/deployment.json
attestation/phala/dry_run.sh       <dir>      # free
attestation/phala/deploy.sh        <dir>      # ~$0.005
attestation/phala/verify_run.py --log <dir>/retained-evidence/phala-run.log \
                                --deployment <dir>
```

Historical records of individual runs are in
[`PHALA_FIRST_RUN.md`](PHALA_FIRST_RUN.md) and
[`COMPCERT_ARTIFACT_UNDER_TDX.md`](COMPCERT_ARTIFACT_UNDER_TDX.md).
