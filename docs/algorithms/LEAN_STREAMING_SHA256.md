# Verified packed-byte SHA-256

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`SparkInterval/Certificate/SHA256.lean` contains two implementations of
SHA-256:

- `digestByteArrayReference` is a deliberately simple specification that
  converts the complete message to a linked list and indexes its padded
  blocks.
- `digestByteArray` is the production implementation. It reads the packed
  `ByteArray` directly and folds consecutive 64-byte blocks without
  materializing the message as a list.

`ByteSource` also supports virtual slices and concatenation.
`digestPrefixSlice prefix bytes start stop` hashes the prefix followed by the
selected half-open byte range without copying or extracting that range. This
is the form used by large binary manifests whose record stream has a
domain-separated digest.

Lean proves, for arbitrary bytes:

```text
digestByteArray bytes
  = digestByteArrayReference bytes

digestPrefixSlice prefix bytes start stop
  = digestByteArray (prefix ++ bytes.extract start stop)
```

The proof connects packed `get!` behavior, virtual padding, every message
schedule block, and the final state to the list reference. It uses no FFI,
`unsafe`, `native_decide`, or project axiom.

## Local forced-evaluation benchmark

The following results were measured on the DGX Spark host and include Lean
interpreter/frontend overhead:

| Input | Packed implementation | List/index reference | Speedup |
|---|---:|---:|---:|
| 1 MiB of zero bytes | 5.042 s | 16.281 s | 3.23x |
| Canonical 2,340,112-byte `TGDQORD1` manifest | 11.769 s | 69.853 s | 5.94x |
| Domain prefix plus manifest record slice | 11.989 s | — | — |

The whole-manifest digest was
`a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93`;
the prefix-plus-slice test digest was
`13305cc4157645a35ed8c5ca01f57462031fa822b666907d586e904aaab4ccd7`.
Both matched Python `hashlib`.

These timings qualify the pure Lean algorithm, not a compiled-binary
refinement or an Azure run. SHA-256 collision and second-preimage resistance
remain standard cryptographic assumptions whenever a digest is used as an
identity commitment; the Lean theorem proves computation equality, not
injectivity of SHA-256.
