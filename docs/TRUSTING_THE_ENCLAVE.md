# Why you should believe a SparkInterval attested run

An attested run makes a narrow claim:

> A specific binary, whose bytes we name, executed inside an Intel TDX
> confidential VM, and reported a specific result.

This document explains how that claim is established, exactly what you have to
trust for it to hold, and — the question that matters most — **how you check a
certificate yourself rather than taking our word for it.**

Nothing here requires you to trust this project. Every check below runs
offline, on bytes committed to the repository, against a certificate authority
pinned in source.

---

## 1. The problem attestation solves

A long computation cannot be redone by every reader. If it takes core-months,
"just run it again" is not a verification strategy. So the result arrives as an
assertion, and the reader is asked to believe it.

Confidential computing narrows that. The CPU measures the code before running
it and signs those measurements with a key certified by the manufacturer. If
you also arrange for the *results* to be inside what gets signed, then one
signature covers both **what ran** and **what came out**.

That is the whole idea. Everything else is making sure the two halves are
really bound together and that nothing in between can be swapped.

---

## 2. The two bindings

Everything rests on two hashes landing inside the same signed structure.

**Binding 1 — what ran.** On boot, the TDX module measures the VM into
registers the guest cannot forge: `MRTD` (initial memory image) and
`RTMR0–3` (runtime extensions). The orchestrator's compose document is
measured into `mr_config_id` as `01 ‖ SHA256(app-compose) ‖ 15 zero bytes`, and
recorded again as an `RTMR3` event. Because the artifacts and the entry point
are **embedded in that compose**, hashing it covers the code.

**Binding 2 — what came out.** The guest may supply 64 bytes of `report_data`,
which the CPU includes in the report. We put

```
report_data = SHA256( "…report-data.v1" ‖ H(enclave public key) ‖ H(statement) )
```

there. The statement names every artifact digest, every exit status, every
transcript digest, and whether each matched its pinned expectation.

Both halves matter. A key with no results attests that nothing happened; results
with no key let anyone sign them.

```
TD report (inside the quote)
  ├── mrtd, rtmr0..3     ← the CPU measured the code
  ├── mr_config_id       ← 01 ‖ compose_hash ‖ 0…0
  └── report_data        ← H(signing key, statement of results)
```

---

## 3. How the signature becomes trustworthy

The report is local to the machine. A certificate chain makes it checkable
elsewhere:

1. the CPU produces a `TDREPORT` over the measurements and `report_data`;
2. Intel's **Quoting Enclave** turns it into a v4 quote signed by an
   *attestation key*;
3. the QE's own report data is `SHA256(attestation key ‖ QE auth data)`, welding
   that key to the QE;
4. a **PCK certificate**, issued to that physical CPU, signs the QE report;
5. leaf ← intermediate ← **Intel SGX Root CA**, whose SHA-256 fingerprint
   `44a0196b…` is pinned both in `tools/intel_sgx_root_ca.pem` and as a literal
   in the verifier, so replacing the PEM alone cannot redirect the trust root.

Intel vouches for the silicon; the silicon vouches for the measurements; the
measurements include the results.

---

## 4. How to check a certificate — do this yourself

The verifier reads a run's log and re-derives everything from committed bytes.
No credentials, no network:

```
python3 verify_run.py --log <run>.log
```

It reports one line per check. The classes, and what each rules out:

| class | check | what a failure would mean |
| --- | --- | --- |
| **E** | each evidence block's SHA-256 matches its own header | the log was truncated or edited |
| **Q** | v4 quote, TEE type `0x81`, DEBUG attribute clear | not TDX, or a debuggable TD whose memory is readable |
| **A1** | attestation key signs `header ‖ TD report` | the measurements were altered |
| **A2** | QE report data is `SHA256(att key ‖ auth data)` | the attestation key is not the QE's |
| **A3–A4c** | PCK leaf signs the QE report; leaf ← intermediate ← root | the chain does not close |
| **A4d–A4e** | the root is the **pinned** Intel SGX Root CA | a different CA was substituted |
| **R1** | the event log replays to all four attested RTMRs | the log does not describe this boot |
| **R2–R4** | the RTMR3 boot chain names this app id and compose hash | the measurements belong to a different deployment |
| **C1** | `mr_config_id = 01 ‖ compose_hash ‖ 0…0` | the CPU measured a different configuration |
| **C2–C5** | the app-compose document read *inside* the TD hashes to that compose hash, and carries this repository's compose byte for byte | the code that ran is not the code you are reading |
| **C6** | that same measured document *declares the hardened posture*: no network, read-only root, no capabilities, no new privileges, an `exec` work directory | the run happened under a weaker configuration than the one documented here |
| **S1–S2** | `report_data` is `H(key, statement)`, upper 32 bytes zero | the results are not the ones attested; no second commitment hidden in the spare bytes |
| **S4–S9** | the attested artifact digests equal the ones built here; every exit status is 0; each transcript matches the digest pinned in the measured compose | a different binary ran, or a different result was produced |
| **G1–G5** | every receipt is signed by one key from the **reviewed pin table**, its canonical digest recomputes, and it names this quote and compose | the receipt was signed by a key nobody reviewed |

**Any single failure fails the run.** The checks are not scored.

### Reproduce the artifacts, don't trust ours

All artifacts rebuild bit-for-bit. Rebuild them and compare against the digests
in the certificate; if they differ, the certificate is about different code.
Reproducibility needed `-Wl,-s` on hosted links — CompCert names its
intermediate object with a random temporary and the linker records that name in
the symbol table.

### Verify the refusals too

A gate that has only ever been seen to pass is not known to be a gate. The
suite tampers with one thing at a time — a flipped byte in an artifact, a wrong
pinned digest, a wrong exit status, an unsigned quote — and requires each to be
refused. This is not decoration: **a receipt forged with an attacker's own
keypair was once accepted**, because the checker took the enclave pin as a
parameter instead of looking it up. That is now a refusal test.

---

## 5. What you must trust anyway

> For the *Lean axiom's* premises specifically — what it checks, what it leaves
> to the external verifier, and one assumption currently rated **not
> defensible** — see [`AXIOM_ASSUMPTIONS.md`](AXIOM_ASSUMPTIONS.md).


Stated plainly, because a list of green checks invites the belief that nothing
is trusted.

* **Intel.** The TDX implementation, the Quoting Enclave, and the PKI rooted at
  the pinned certificate. If the CPU is backdoored or the root key is
  compromised, everything above fails silently.
* **The dstack guest agent.** It derives the signing key and assembles
  `report_data`. It runs inside the measured VM, but it is not measured *by*
  this project.
* **CompCert's proof** for C → assembly, and the **assembler and linker**,
  which are outside it. Freestanding artifacts reduce this: zero undefined
  symbols and a five-instruction entry stub.
* **Docker, for honouring the compose.** The hardening — `network_mode: none`,
  `read_only`, `cap_drop: ALL`, `no-new-privileges`, `pids_limit` — is measured
  because it is in the compose, but the measurement proves only that *those
  words* were in the document the CPU hashed, not that the runtime obeyed them.
  The entry point records `uid`, rootfs writability, `CapEff` and `NoNewPrivs`
  from `/proc/self/status` as a cross-check, and that record is inside the
  attested transcript. `verify_run.py`'s C6 additionally requires the *measured*
  document — the bytes the CPU hashed, not the file on disk — to declare that
  posture, so a later deployment cannot quietly relax it while every other
  check still passes.
* **The contents of the base image**, `python:3.12` at the digest the compose
  names. Every executable the entry point uses — `bash`, coreutils, `gcc`, the
  libc headers, and the `python3` that signs the receipt — comes from it. The
  measurement proves *that image* ran, not that its contents are honest. What
  this buys is that the target is fixed and auditable ahead of time: the same
  bytes every run, at a digest anyone can pull and inspect. It replaced
  installing those packages at run time, which put the signing interpreter
  outside the measurement altogether (`AXIOM_ASSUMPTIONS.md` §3.3).
* **The reviewed pin table.** `attestationAuthority := true` on an entry asserts
  that a key was produced inside an enclave. That is a person's judgement. It is
  the one line in the checker that is not arithmetic, and adding one is a
  reviewable diff.

### What is *not* established

**This is not a TCB appraisal.** Chain validity says the attestation key is
Intel-rooted. It says nothing about whether the platform's microcode is current
or whether a certificate has been revoked. That needs Intel's live collateral
and is `dcap-qvl`'s job. In-enclave strict appraisal also conflicts with running
the container without network — a tension recorded in `0b368fc`, where a real
run's strict appraisal could not fetch collateral.

**Attestation says nothing about mathematics.** That an artifact computes the
object a theorem names is a separate, per-computation obligation, proved in
Lean. A receipt says a binary ran and reported a number.

---

## 6. What an attacker would have to do

| attacker | must defeat |
| --- | --- |
| the cloud host / hypervisor | Intel TDX memory encryption and integrity |
| whoever runs the deployment | `mr_config_id` and the RTMR3 event — changing one byte of the compose changes the measurement |
| someone substituting a binary | the in-enclave digest check *before execution*, and the artifact digests inside `report_data` |
| someone editing the results | `report_data`, which the CPU signed |
| someone signing their own receipt | the pin lookup — a key not in the source table cannot be made to count |
| someone forging the quote | the Intel PKI, up to a pinned root fingerprint |

Everything but the first and last is checkable by you, offline, from committed
bytes.
