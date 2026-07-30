# A leancompcert campaign, built for real: what worked and what did not

Every number here is **M** (measured by me on this host on 2026-07-30) unless
marked **E**.  Host: 20-core aarch64 Linux, 119 GB RAM, CompCert 3.17 (two
installs, aarch64 and x86_64), Lean 4.32, Docker 29.2.1 with linux/amd64
emulation.

**No CVM was created and no credits were spent, because there is no Phala
credential on this host.**  See §6.

---

## 1. What was built

| | |
|---|---|
| campaign | Platt's stronger little-Mertens range, `\|Σ_{m≤n} μ(m)/m\| ≤ 1/(2√(n+1))` |
| covered | `n ∈ [3, 7 727 065 383]` — **3,204 short** of the axiom's `7 727 068 587`, see §4 |
| artifacts | **230** statically linked, freestanding, CompCert-compiled x86_64 executables |
| total artifact bytes | **2,093,896** (mean 9,104 B) |
| campaign image | **136 MB**, `linux/amd64`, no analytic stack |
| `canonicalDefinition` | **505 bytes**, names the manifest by SHA-256 |
| `algorithmHash` | `ddf877d5…47c10`, kernel-proved preimage, base trio |
| discovery run | `[1, 7 727 065 383]`, ~7.7×10⁹ integers, one core, ~11 min wall |

Files:

* `proof_build/leancompcert_tdx/SegChainEmit.lean` — window emitter with a
  **self-checking** freestanding driver
* `proof_build/leancompcert_tdx/build_seg_campaign.py` — the four-phase builder
* `proof_build/leancompcert_tdx/run_seg_campaign.sh` — enclave entry point
* `proof_build/leancompcert_tdx/Dockerfile.seg` — the campaign image
* `tools/tg_seg_campaign_check.py` — manifest / chain / digest pre-check
* `SparkInterval/Execution/LeanCompCertSegCampaign.lean` — the Lean pin
* `proof_build/leancompcert_tdx/seg_campaign_pin_kernel_check.lean` — the
  10 GB kernel binding
* `tests/data/leancompcert_seg_plattstrong/` — the reviewed manifest and pin

---

## 2. The thing the design note did not anticipate: a campaign is a *chain*

`Ports.ArraySegSieve`'s residue tests its whole window against **one**
threshold — the majorant at the window's worst endpoint.  Covering
`[3, 7.7×10⁹]` at full strength therefore cannot be one executable.  It is 230
of them, each seeded with the previous one's carry-out.

That has three consequences the "one 640 KB artifact" framing misses.

**(a) The stock freestanding driver is not sound for a chain.**
`bench/ArraySegEmit.lean`'s exit driver compares only the violation count.  A
window seeded with the *wrong* carry-in still exits 0, so a chain of such
artifacts proves nothing about the range it claims.  `SegChainEmit.lean` emits
a driver that returns 0 only when the violation count **and** all three result
slots (`rT`, `rTmax`, `rTmin`) match the manifest.  Chain integrity then
becomes a textual property — window `k+1`'s seed is window `k`'s carry — that
`tg_seg_campaign_check.py` verifies on the build host, inside the TD, and by a
reviewer, from the same 85,644-byte manifest.

**(b) The seeds must be discovered before the artifacts can be built.**  The
build host runs the entire computation once (gcc, hosted driver) to learn every
carry-out, then re-emits each window with those values baked in.  So the
enclave does not save the operator the compute; it makes the compute
*attestable*.  For plattstrong that is ~11 min on one core, twice.  For
`residual_platt_2_11` (10¹²) it would be **~15.6 core-hours** of host discovery
before a single artifact exists (**E**, from the measured 54 ns/integer).

**(c) `canonicalDefinition` names a manifest, not a binary.**  Naming 230
binaries individually would not fit in 505 bytes.  One `manifest-sha256` line
does, and the manifest names all 230 plus their C preimages, seeds, carries and
thresholds.

---

## 3. Measured facts

### 3.1 The x86_64 freestanding stub now has evidence

`~/leancompcert/runtime/start/x86_64.S` was checked in marked
"UNASSEMBLED / UNTESTED".  Both checks from its own README now pass, run in a
`linux/amd64` container:

| check | result |
|---|---|
| `int main(void){return 7;}` | exit **7** — the stub propagates `main`'s value |
| deliberate null write | exit **139** — a crash stays a signal death, not a clean 0 |

Binary sizes: 4,680 B (`ret7`), 9,104 B mean for a real window artifact.
`ld` pulls in **no libc**; the CompCert objects have zero undefined symbols.

### 3.2 `ccomp` for x86_64 works from this aarch64 host

`~/compcert-x86_64/ccomp` reports `arch=x86`, `model=64`.  Note for
`build_artifact.sh`: it compares that field against the literal `x86_64` and
would refuse — `compcert.ini` says **`x86`**, not `x86_64`.

The documented preprocessing gotcha is real: `ccomp` shells out to `gcc -m64`,
which the aarch64 gcc rejects.  `gcc -E -U__GNUC__ -U__SIZEOF_INT128__` first,
then `ccomp -S -O2` on the `.i`, works.

### 3.3 The image

**136 MB**, versus 163 MB for the A.7 image.  The design note estimated 50–80 MB
on the basis that `python:3.10-slim` is ~45 MB.  **That estimate is wrong for
`linux/amd64`**: `python:3.12-slim` (trixie) is ~120 MB there.  The campaign
contributes only ~10 MB (2.1 MB of artifacts plus 4.4 MB of emitted C, which is
carried so the image exhibits the preimage of every `cSha256`).

So the honest headline is: **the analytic stack is gone (no python-flint, no
FLINT/Arb, no compiled bytecode, no external artifact fetch over HTTPS), and
the image still costs 136 MB because the attestation prelude needs a Python
interpreter.**  Reaching ~10 MB means rewriting the dstack/GetQuote/dcap-qvl/
RTMR3/P-256 prelude in C, which a leancompcert `Program` cannot express — it
has no I/O, no sockets and no key material.

### 3.4 The Lean pin

| | A.7 today | this campaign |
|---|---|---|
| `canonicalDefinition` | 514 B paragraph, `producer=tg_verifier/a7_flint.py` | **505 B**, `manifest-sha256=6b20f834…ead38` |
| preimage binding | *not* a theorem — "an import trust boundary rather than a multi-gigabyte theorem proof" | **`decide +kernel`**, base trio |
| kernel cost | not paid | **16.46 s user, 10.27 GB resident** |

The upgrade is 9 bytes *cheaper* than the paragraph it replaces.  But 10.27 GB
exceeds `lakefile.toml`'s `weakLeanArgs = [..., "-M8192"]`, so the theorem
lives in `proof_build/` and the library keeps a Bool diagnostic — the same
split the repo already uses for `prod5_kernel_full_check.lean`.

### 3.5 `#print axioms`

```
segCampaignAlgorithmHash_eq                    [propext, Classical.choice, Quot.sound]
segCampaignAlgorithmHashDiagnosticCheck_def    [propext, Classical.choice, Quot.sound]
segCampaignLimit_lt_littleStrongerLimit        does not depend on any axioms
segCampaignAlgorithmHash_not_ch25A7Boundary    does not depend on any axioms
certifySegCampaignLittleStrongerAt             [propext, Classical.choice, Quot.sound,
                                                phalaTdxAttestedEmission_sound]
```

No `sorry`, no `native_decide`, and `phalaTdxAttestedEmission_sound` is the
only attestation axiom, still concluding bytes only.

### 3.6 The exit-status discipline, exercised

A window artifact replaced by one that segfaults makes the entry point print
`REFUSED: window 1 (bin/w00001) exited 139, which is neither verdict` and exit
1.  It does **not** emit `false`.  Tamper checks on the manifest (chain break),
on a binary (one flipped byte), and on the artifact set (one file removed) are
each refused by `tg_seg_campaign_check.py` before anything runs.

---

## 4. The finding that changes the claim: the accumulator's rounding budget

The campaign stops at **7 727 065 383**, not at Platt's stated
**7 727 068 587**.  3,204 integers, and the reason is not compute.

`plattStrongerThreshold N = ⌊2^62/(2√N)⌋ − ⌈N/2⌉`.  The subtracted term is the
accumulated round-to-nearest budget of the 64-bit fixed-point accumulator —
one half-ulp per summand — and it is what makes a passing *integer* test a
bound on the *real* sum.  At `N ≈ 7.727×10⁹` it is `1.47×10⁻⁴` of the
threshold, so the artifact certifies `|S(n)| ≤ (1 − 1.47×10⁻⁴)/(2√N)`.

`7 727 068 587` is the point where the majorant stops holding, so the family's
slack there is *smaller* than that budget.  The builder's halving search
located the first uncertifiable point exactly: **`n = 7 727 068 562`**, at
window width 1 — where the window schedule gives away nothing at all, so the
budget is the whole explanation.

Consequences:

* The campaign discharges `residual_platt_stronger_range` **restricted to
  `x ≤ 7 727 065 383`**.  `segCampaignLimit_lt_littleStrongerLimit` states the
  gap in Lean so it cannot be overlooked.
* Closing it needs a **wider accumulator**, not a longer run: the budget scales
  as `N/2^S`, so `S = 62 → 78` buys four decimal digits of margin.  That is a
  leancompcert change.
* The same will bite `residual_platt_2_11` at 10¹² **more** severely (budget
  `N/2^62` grows linearly in `N`), and it is worth checking *before* spending
  15.6 core-hours of discovery.

Also worth recording, because it cost two failed runs: a window `[lo, hi]`
seeds `rTmax`/`rTmin` from its **carry-in**, so it actually asserts the bound
over `[lo−1, hi]`.  That is why the campaign is emitted with `range-lo = 4`
and nonetheless covers `n = 3`, and why a chain claimed from `n = 3` fails
immediately (it would assert the bound at `n = 2`, where it is false:
`S(2) = 0.5 > 1/(2√3)`).

---

## 5. What of the four target axioms is actually reachable

| axiom | status |
|---|---|
| `residual_platt_stronger_range` (7.7e9) | **BUILT**, minus the top 3,204 integers (§4) |
| `residual_platt_2_11` (1e12) | emitter exists (`platt211` mode); needs ~15.6 core-hours of host discovery first, and §4 must be checked at 10¹² |
| `finite_check_helfgott_prop_12_2_4` (9.5e10) | **not emittable.**  Its reduction is a per-`(q,k)` large-sieve table needing `Nat.totient`, a product over `q.primeFactors`, a log sum and two `rpow` terms.  No `ArraySegSieve` mode computes it, and the reduction itself is on an unmerged claude_math worktree branch |
| `reproducibleTable_abel_verifier` (5e9) | **not emittable.**  Abel summation over a 199,331-entry resident μ table with a `√k` weight; it has no Nat-family reduction at all |

The two that work are exactly the two that are Möbius running sums.  This is
the same boundary `docs/COMPCERT_ARTIFACT_UNDER_TDX.md` §6.4 drew, one level
finer: the architecture fits *integer folds over a sieve*, and the other two
targets are not that.

---

## 6. Why nothing was deployed

There is **no Phala Cloud credential on this host**.  `phala status` reports
`Not authenticated`; there is no `~/.phala*`, no `PHALA_CLOUD_API_KEY` in the
environment or in any file under `$HOME`, and the four `~/phala-a7-run*/`
directories from the 2026-07-27 run contain the deploy env and evidence but no
API key.  `/api/v1/auth/me` cannot be called, so **credits before and after are
both unavailable, and the actual spend is $0.00 — nothing was created.**

Everything up to the deploy is done and verified locally:

* the image builds and its 230 artifacts pass the in-image pre-check;
* 130 of the 230 windows were executed inside the `linux/amd64` image under
  emulation and all exited 0 (the remaining 100 cover 7.7×10⁹ integers, which
  qemu user emulation would take days to replay — a real x86_64 CPU does the
  whole chain in about 7 minutes, **E**);
* the entry point's refusal paths are exercised.

To run it, an operator needs: `phala login` with an API key, a public GHCR
package (`ghcr.io/gersh/sparkinterval-leancompcert-plattstrong:v1` is built
locally and not pushed), the `--campaign-entry` switch in
`tools/tg_phala_tdx_compose.py` (**not written**), and the discovery-mode
first run described in `docs/PHALA_FIRST_RUN.md` §4b.
