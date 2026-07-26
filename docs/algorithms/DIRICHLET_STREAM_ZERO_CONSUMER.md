# Persistent Dirichlet completed-L stream consumer

This component closes the process and storage gap immediately after the
all-character CRT/Bluestein transform.  One long-lived process consumes an
arbitrary sequence of `TGDAFFO1` frames, reconstructs the canonical primitive
frequency map, forms rigorous completed-`L` intervals with Arb, and streams
sign-change candidates.  It does not materialize a transform, spawn one
process per batch, or retain nonprimitive character values.

It is an executable arithmetic component, not a proof of Platt's Theorem 7.1.
No source campaign has run, upstream semantics are not replayed here, and sign
changes alone do not prove zero completeness.  The scalable root-number
producer and its `TGDRNRO1` artifact are now accepted through a hash- and
convention-bound path; the direct quadratic Arb calculation remains the
independent small-modulus reference.

## Persistent protocol

The process has two synchronized inputs:

- a canonical NDJSON control file or FIFO, with one record per transform
  frame; and
- concatenated binary `TGDAFFO1` frames, read from a file or standard input.

The legacy output header does not contain ordinates.  Each control record
therefore supplies the first ordinate, common denominator, step, expected
batch count, exact `L_chi(1/2+it)` semantics, and four upstream receipt hashes.
The consumer requires frame indices to be consecutive, moduli to be monotone,
and consecutive frames of one modulus to have exactly contiguous ordinate
ranges.  It recomputes component orders, group order, primitive frequencies,
primitive ordinal, Conrey number, parity, value count, and the exact Bluestein
butterfly count; none of those identities comes from the control producer.

For example, a producer can keep both FIFOs open for an entire worker shard:

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_stream_zero_consumer.py consume \
  /run/worker/control.ndjson - /run/worker/zero-events.ndjson \
  /run/worker/receipt.json \
  --root-artifact /run/worker/q.roots.bin \
  --root-receipt /run/worker/q.roots.json \
  < /run/worker/allchars.frames
```

This is a persistent framed protocol: the q=5 KAT deliberately places 129
ordinates in two frames and verifies that signs and brackets survive the frame
boundary in one process.  A production shard should keep a whole modulus in
one consumer so that a sign change cannot be lost at a shard boundary.

Every binary rectangle, including a nonprimitive one, is shape-checked and
included in the transform-stream digest.  Only primitive-frequency rectangles
enter completed-`L` arithmetic.  The compact JSON receipt binds the complete
control stream, complete binary stream, a frame hash chain, the root-number
rows, all sign decisions, and the exact event artifact.  The event artifact
contains only indeterminate samples and distinct sign-change candidates, so it
does not reproduce the much larger transform.

## Character and root-number reconstruction

`primitive_frequency_records(q)` is recomputed rather than trusted.  For each
retained frequency the consumer checks the primitive ordinal, Conrey number,
parity, FLINT conductor, and FLINT primitivity.

The reference root-number path evaluates the Gauss sum

```text
tau(chi) = sum_(a mod q) chi(a) exp(2 pi i a/q)
w(chi)   = tau(chi) / (i^a_chi sqrt(q))
epsilon  = sqrt(conj(w(chi))).
```

All terms and transcendental functions are outward Arb enclosures.  A subtle
normalization is covered by a regression test: python-flint's
`chi_exponent(a)` is divided by `character.group().exponent()`, not by
`character.order()`.  The two differ for the primitive quadratic character
modulo 5 (Conrey number 4); using the latter gives a false Gauss sum.

This direct algorithm is rigorous and convenient for replay, but calculating
it for every character is quadratic in a large modulus.  It remains the
default KAT path and reports `source_performance_ready: false`.

For source execution, `--root-artifact` and `--root-receipt` select the
`tgdaff-all-character-gauss-root-phase-v1` path documented in
`DIRICHLET_ROOT_NUMBER_STAGE.md`.  On the first frame, the consumer validates
the receipt self-hash, convention digest, artifact digest, modulus, primitive
count, input-transform hash, output-transform hash, binary shape, and every
outward unit-phase interval.  It zips stored intervals by canonical primitive
ordinal with a freshly reconstructed bulk frequency/Conrey/parity map and
uses the stored
`principal_sqrt(conj(tau/(i^parity*sqrt(q))))` directly.  The artifact is held
for the whole q shard and its binding is committed into the final receipt.
Supplying only one of the two files, using direct-mode controls with an
artifact, changing q, or tampering with either file fails closed.  This removes
the quadratic root-number hot path; it does not make the later zero-completeness
claim true, so `production_accept` remains false.

The executable source-work inventory makes the limitation quantitative.  For
the all-character range `10001 <= q <= 400000`, direct generation would visit
`7,884,109,109,859,397` character/residue pairs and evaluate
`6,584,344,411,462,564` nonzero Gauss-sum terms.  The worst single modulus is
the prime `q=399989`, with `159,990,000,156` nonzero terms.  These counts are
recomputed from the canonical primitive-character schedule and pinned; they
are workload facts, not a runtime estimate.

```bash
python3 tools/tg_dirichlet_stream_zero_consumer.py --pretty root-work
```

## Completed value and brackets

For each primitive rectangle the consumer evaluates Platt's Section 1 value

```text
epsilon_chi (q/pi)^(it/2)
  Gamma((1/2 + a_chi + it)/2) exp(pi t/4) L_chi(1/2+it).
```

A value is given a strict sign only if its real interval excludes zero, and
the computation fails if its imaginary interval does not contain zero.  An
indeterminate real interval is retained as an event with its complete
rectangle so an exception worker can refine it.

Opposite strict endpoint signs emit one candidate bracket with
`multiplicity_lower_bound: 1`.  Brackets are never deduplicated, conjugate
characters remain separate, and no candidate is promoted to exact
multiplicity.  A sign change certifies an odd crossing only after the usual
analytic continuity bridge; it cannot detect an even number of zeros between
equal signs.  Turing completeness and Platt's exception/upsampling paths are
therefore explicitly outside this receipt.

The four upstream digests ensure that a receipt cannot be relabeled onto a
different lattice, finite addback, residue adapter, or transform input.  This
consumer does not replay those earlier semantics, so the receipt says
`upstream_semantics_replayed: false` rather than treating hashes as proofs.

## Independent known-answer replay

The KAT constructs two q=5 frames from fresh FLINT `L` intervals through
height 10.  The replay independently evaluates every primitive `L` value and
FLINT Hardy Z, allows one fixed square-root orientation per character, and
requires every completed sign and sign-change count to agree.  It covers all
three primitive characters, including the group-exponent root-number
regression.  A second process then recomputes the event and receipt bytes.

```bash
.venv-tg-flint/bin/python tools/tg_dirichlet_stream_zero_consumer.py \
  --pretty known-answer /tmp/tg-dirichlet-stream-kat

.venv-tg-flint/bin/python tools/tg_dirichlet_stream_zero_consumer.py \
  --pretty verify \
  /tmp/tg-dirichlet-stream-kat/control.ndjson \
  /tmp/tg-dirichlet-stream-kat/frames.bin \
  /tmp/tg-dirichlet-stream-kat/events.ndjson \
  /tmp/tg-dirichlet-stream-kat/receipt.json
```

The KAT contains two frames, 387 primitive samples, six distinct sign-change
candidates, and no indeterminate samples.

## Local benchmark and exact limitation

On the local DGX Spark on 2026-07-21, the full q=29, 64-ordinate consumer
processed 1,728 primitive samples in 0.0415 seconds (about 41,600 primitive
samples/s).  A q=101, 64-ordinate run processed 6,336 samples in 0.165 seconds
(about 38,400/s).  At q=1009 with only eight ordinates, the quadratic direct
root-number setup dominated: 8,056 samples took 3.00 seconds (about 2,680/s).

These are representative local measurements, not an H100 result or a valid
source projection.  Completed-`L` transcendental arithmetic runs on the CPU;
the H100 supplies the upstream all-character intervals.  The scalable root
artifact removes the q=1009 setup bottleneck measured here.  A weighted
source benchmark of artifact lookup plus completed-L arithmetic is still
needed, followed by integration of the exception, upsampling, and Turing
stages.

## Verification

```bash
.venv-tg-flint/bin/python -m unittest \
  tests.test_tg_dirichlet_stream_zero_consumer -v

python3 -m py_compile \
  tg_verifier/dirichlet_stream_zero_consumer.py \
  tools/tg_dirichlet_stream_zero_consumer.py
```

The implementation is in
`tg_verifier/dirichlet_stream_zero_consumer.py`; its only CLI is
`tools/tg_dirichlet_stream_zero_consumer.py`.  Neither file is registered as a
full atom campaign, because doing so before the remaining steps would
overstate the trust boundary.
