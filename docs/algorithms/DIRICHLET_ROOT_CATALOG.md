# Source-wide Dirichlet root-artifact catalog

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

The large-`q` completed-L stage needs one `TGDRNRO1` root-number artifact for
each modulus having primitive characters. Root numbers do not depend on the
ordinate, so a t-major Azure worker must authenticate them once per modulus,
not accept a new untyped hash claim on every lattice row.

[`dirichlet_root_catalog.py`](../../tg_verifier/dirichlet_root_catalog.py)
implements that boundary as bounded canonical NDJSON. The full source roster
contains exactly 292,500 strictly increasing moduli in `10001..400000`.
Moduli with no primitive character are omitted by the exact
`primitive_character_count(q)` formula; every other modulus is required once.

For each canonical pair

```text
root-q-QQQQQQ.bin
root-q-QQQQQQ.receipt.json
```

the builder:

1. opens both regular files without following symbolic links;
2. checks the receipt's canonical encoding and self-hash;
3. checks the fixed completed-L phase convention;
4. parses the exact artifact bytes through the existing `TGDRNRO1` validator;
5. checks `q`, the canonical component orders, primitive-character count,
   artifact length/hash, additive-input hash, and transform-output hash; and
6. commits the entry to both a raw-entry digest and an ordered entry-hash
   chain.

The footer commits the exact entry count and both chains. The auditor rejects
missing, duplicate, reordered, substituted, noncanonical, truncated, or
trailing records. With `--revalidate-artifacts`, it reopens and reparses every
receipt and root artifact and requires each reconstructed entry to equal the
catalog entry. It retains at most one root artifact and receipt at a time.

Build and fully reaudit a production catalog with the pinned Arb/FLINT
environment:

```bash
python3 tools/tg_dirichlet_root_catalog.py split-stream \
  /shared/root-stream.bin /shared/root-receipts.ndjson \
  /shared/dirichlet-roots \
  --expected-root-stream-sha256 ROOT_SHA256 \
  --expected-receipt-stream-sha256 RECEIPT_SHA256

python3 tools/tg_dirichlet_root_catalog.py build \
  /shared/dirichlet-roots /shared/dirichlet-roots/catalog.ndjson

python3 tools/tg_dirichlet_root_catalog.py audit \
  /shared/dirichlet-roots/catalog.ndjson \
  --root /shared/dirichlet-roots \
  --require-full-source --revalidate-artifacts
```

The expected root payload is about 945.5 GB. No full catalog has been
generated or audited in this repository, and no Azure execution is attested.
This boundary proves that the artifact bytes parse, match their receipts, and
cover the exact roster. It does not independently recompute the root numbers
from the mathematical additive/transform inputs, and there is not yet a
per-entry execution reader that pins each file immediately before use. The
catalog therefore does not isolate zeros, perform the Turing argument, or
discharge Platt's Theorem 7.1.
