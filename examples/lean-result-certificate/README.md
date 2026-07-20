# Full Lean result-certificate example

The checked-in certificate computes `x * (1 + y)` over two complete input rows.
Lean independently parses and hash-checks the canonical JSON, decodes every
binary64 endpoint into an exact rational, reevaluates each row, and derives
row-wise and finite-sum upper bounds.

The generated file is also a reusable Lean module. In a real certificate
library it can live at a normal module path, be built into an `.olean`, and be
imported by application proofs. Those consumers use its exported theorem; they
do not rerun the calculation that produced the interval rows. See
[Using computation certificates from Lean](../../docs/LEAN_INTEGRATION.md) for
an import wrapper and the clean-build verification caveat.

## Reproduce the proof

The generator refuses to overwrite its Lean output. From the repository root,
choose a fresh directory:

```bash
mkdir -p build/examples
CERT_DIR="$(mktemp -d build/examples/lean-result-certificate.XXXXXX)"
./tools/safe_lake_build.py SparkInterval.Certificate \
  --target sparkinterval-check-certificate
python3 tools/generate_lean_result_certificate.py \
  --certificate examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001 \
  --decision-mode kernel \
  --output "$CERT_DIR/GeneratedFullCertificate.lean" \
  > "$CERT_DIR/receipt.json"
./tools/safe_lean.sh "$CERT_DIR/GeneratedFullCertificate.lean"
./tools/with_memory_limit.sh \
  .lake/build/bin/sparkinterval-check-certificate \
  examples/lean-result-certificate/certificate.json \
  --upper-bound 4010000000000001
```

The upper-bound word is the exact finite binary64 value
`4.000000000000000888...`.

## Generated theorem choices

`application_upper_bound_sound` proves a bound for an arbitrary real value
represented by any checked row. `certificate_sum_upper_bound_sound` bounds the
sum of one arbitrary represented value from every row.

With explicit `--decision-mode kernel`, these direct typed-data theorems use
kernel reduction and their axiom reports do not include `native_decide`. The
serialized `application_theorem` and `application_sum_theorem` additionally
bind the exact JSON, SHA-256 values, and parser result; their concrete parser
equality uses `native_decide`.

For a large materialized witness, `--decision-mode native` also uses
`native_decide` for the direct typed checks. The namespace and receipt bind the
certificate digest, upper bound, and selected decision mode so differently
configured witnesses can coexist without ambiguity.

## Scope

Malformed data, a hash mismatch, or a result narrowed past Lean's exact
reevaluation is rejected. The generator is stricter than the generic
containment theorem and emits source only when exact Python recomputation
matches every claimed result.

This is an independently checked mathematical witness, not execution evidence
or hardware attestation. It does not prove who produced the certificate. See
[Using SparkInterval](../../docs/USING.md#full-lean-result-certificate) and
[Full Lean result certificates](../../docs/FORMAT.md#exact-reference-and-full-lean-certificates)
for the general workflow and wire format.
