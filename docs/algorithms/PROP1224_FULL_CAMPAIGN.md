# Full-source Proposition 12.2.4 campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

`tg_verifier/prop1224_campaign.py` is a literal, resumable external verifier
for the finite computation used by the atom `helfgott-prop-12-2-4`. It is
full-domain capable, but it has not been run to completion and it has no Lean
realization theorem.

The immutable domain is exactly:

```text
q = 1, 2, ..., 3,299,999,999
then q < 22,000,000,000 with 210 | q
total admissible q rows = 3,389,047,618
```

The rank/unrank scheduler checks that count without iterating billions of
rows. A terminal receipt is accepted structurally only when its accumulated
row count is exactly `3,389,047,618` and its state is the canonical
`q = 22,000,000,000` sentinel.

## Running it

`run` and `replay` are production arithmetic and require measured Azure worker
scope. `--max-chunks` is only a cloud checkpoint limit: one source chunk is
already far beyond the local KAT bound. Local review may create plans and
inspect the compact receipt chain; the separate directed-leaf tool permits
only at most 64 non-`q=1` rows locally.

Start or resume the source campaign:

```bash
python3 tools/tg_prop1224_campaign.py run artifacts/prop1224
```

For a bounded cloud checkpoint of the same campaign, pause after a fixed
number of new chunks:

```bash
python3 tools/tg_prop1224_campaign.py run artifacts/prop1224-test \
  --r-steps-per-chunk 100000 --q-rows-per-chunk 10000 --max-chunks 2
```

This remains an incomplete full-source campaign. It reports `complete: false`;
there is no sample mode and no option to change the initial or terminal `q`.

Check the compact hash/state chain without rerunning the arithmetic:

```bash
python3 tools/tg_prop1224_campaign.py verify artifacts/prop1224
```

Independently regenerate every arithmetic step from `q = 1`:

```bash
python3 tools/tg_prop1224_campaign.py replay artifacts/prop1224
```

`replay --max-chunks N` is useful for audits, but only replaying every retained
receipt sets `fresh_arithmetic_replay: true`.

## Why the `q = 1` row does not exhaust memory

At the default directed precision, the conservative `q = 1` window is

```text
71,575 <= k <= 23,278,583
```

so it contains 23,207,009 candidate integers. The bounded reference builds an
exact rational `G_q(k)` prefix, whose denominator and retained object graph
are unsuitable at that size. The campaign instead sieves `phi(r)` and
squarefreeness in bounded segments and maintains integers `L,U` at scale
`S = 2^precision_bits`:

```text
L <- L + floor(S / phi(r))
U <- U + ceil(S / phi(r))
```

for squarefree `r` coprime to `q`. Thus

```text
L/S <= G_q(k) <= U/S.
```

The final source margin decreases as `G_q(k)` increases, so evaluating it with
`U/S` gives a sound lower bound. A chunk stores only the incoming and outgoing
`(q,next_r,L,U)` state, counts, the minimum margin lower bound, and a SHA-256
commitment to every sieve and margin row. Candidate rows are streamed; they
are not truncated or retained in receipt JSON.

## Receipt and replay boundary

Configuration and receipts use canonical JSON, atomic writes, an advisory
campaign lock, consecutive names, source-file hashes, and a predecessor hash.
Resume checks the complete compact chain before adding a receipt. Independent
replay starts from `(q,r,L,U) = (1,1,0,0)`, regenerates each selected receipt,
and requires exact JSON equality.

The Python implementation is expected to be prohibitively slow for the full
3.389-billion-row source domain. Hashes provide integrity, not execution
attestation. The result flags therefore keep all of these false:

```text
execution_attested
lean_realization_proved
lean_atom_discharged
```

A completed and independently replayed campaign would verify the external
finite computation under the directed-rational evaluator. Retiring the Lean
atom additionally requires a theorem connecting that evaluator and its
certificate format to the proposition used by the Lean consumer.

Run the focused tests with:

```bash
python3 -m unittest tests.test_tg_prop1224_campaign -v
```
