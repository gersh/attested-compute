# Prop1224 and Hurst candidate artifact wires

The Azure terminal programs now retain exact binary inputs for the total Lean
decoders:

- `SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact.decode`;
- `SparkInterval.TernaryGoldbach.HurstCandidateArtifact.decode`.

The matching Python codecs are
`tg_verifier/prop1224_candidate_artifact.py` and
`tg_verifier/hurst_candidate_artifact.py`. Naturals use 32-byte unsigned
little-endian fields. Integers use one canonical sign byte followed by a
32-byte magnitude; negative zero and unknown signs are rejected. Both
decoders require the literal Lean header, bounded row count, and exact EOF.
The Lean and Python tests share SHA-256 known answers over complete binary
fixtures, including negative Hurst coordinates.

## Azure retention and ordering

The Prop1224 terminal first independently replays all fixed-plan receipts.
Only then does it encode the gap-free shard chain. The candidate and its
canonical JSON manifest are members of `prop1224-retained.tar`, so the
existing retained-tree and archive hashes bind both files. The work trace
hash directly commits their relative paths, sizes, and SHA-256 digests.  The
published trace object itself retains the measured runner's closed nine-field
schema; the pinned external trace verifier reconstructs those candidate
commitments from the retained archive.

The Hurst terminal first replays the complete retained campaign and constructs
the four-coordinate affine chain in memory. It then performs the existing
registered-result replay. Only after both checks succeed does it exclusively
write the candidate and manifest under `work/hurst/candidate/`. Their paths,
sizes, and SHA-256 digests are direct inputs to the terminal trace hash. The
trace verifier reconstructs the candidate from a fresh campaign replay and
requires byte-for-byte equality.  Candidate metadata is not an unrecognized
top-level trace extension, so the generic measured runner can validate the
same closed trace schema before signing the statement.

Neither candidate is a successful semantic certificate. Every manifest sets
`semantic_closure` to `false`, and the Lean `runCandidate` programs still
return their dedicated missing-realization rejection codes.

## Exact missing realization data

Prop1224 still lacks:

1. per-rank factorization and Euler-totient realization;
2. outward MPFR intervals for `log`, `exp`, real powers, Euler gamma, and
   `c_E`;
3. exact directed GMP `G_q` accumulator values;
4. conservative integer-window endpoint decisions; and
5. an ordinary Lean theorem from those records to each literal source row.

Hurst still lacks:

1. per-row Möbius and squarefree increments;
2. per-row directed lower and upper Q96 little-Mertens increments;
3. local prefix recurrence records within each block;
4. each integer guard decision; and
5. ordinary Lean row-soundness and exact block-coverage proofs.

The CLI makes this distinction reviewable:

```bash
python3 tools/tg_candidate_artifact.py inspect prop1224 ARTIFACT
python3 tools/tg_candidate_artifact.py inspect hurst ARTIFACT
python3 tools/tg_candidate_artifact.py require-semantic-realization \
  prop1224 ARTIFACT
```

The last command always fails and prints the absent fields; it cannot promote
an arithmetic candidate by treating hashes, margins, or a successful Azure
receipt as the missing source-row theorem.
