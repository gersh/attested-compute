# Exact reference-certificate example

This example computes `x * (1 + y)` over two interval rows. Its checked-in
`batch.json` includes point and non-point inputs.

From the repository root, choose a fresh output directory:

```bash
mkdir -p build/examples
REF_DIR="$(mktemp -d build/examples/reference.XXXXXX)"
python3 -m reference.cli evaluate \
  examples/reference-certificate/batch.json "$REF_DIR/result.json"
python3 -m reference.cli certify \
  --result "$REF_DIR/result.json" \
  examples/reference-certificate/batch.json "$REF_DIR/certificate.json"
python3 -m reference.cli check "$REF_DIR/certificate.json"
```

`create_example.py` deterministically regenerates the checked-in `batch.json`
when maintenance of the example input is required. Ordinary users can use the
checked-in batch directly.

The checker recomputes every endpoint with exact rational binary64 arithmetic.
This Python-only package is mathematical reference evidence, not a Lean theorem
and not proof that a GPU ran. To import the same canonical format into Lean,
continue with the [full Lean certificate example](../lean-result-certificate/README.md).
