# Numeric-corpus reference templates

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

These files show every required field in the pinned numeric-corpus protocol:

- `manifest.template.json` is the record stored with the corpus;
- `pin.template.json` is the small record stored by its consumer.

They are documentation, not accepted fixtures. Every commit ID and SHA-256
digest is the all-zero reserved placeholder, and both files are pretty
printed rather than encoded as canonical JSON. The production loader must
reject them.

The illustrative payload layout has one declared coverage interval `[0, 3)`
split exactly between `[0, 2)` and `[2, 3)`. Its sizes, counts, and names show
how manifest fields relate; they do not describe files checked into this
directory.

To publish a real corpus:

1. copy the field layout, not the placeholder values;
2. write the exact source-shaped statement and computation parameters;
3. hash the intended payload and source blobs;
4. compute the domain-separated statement, payload-root, and source-root
   hashes;
5. write and commit the canonical manifest and every referenced blob;
6. read the manifest back from that exact commit;
7. build the canonical consumer pin from the committed manifest; and
8. validate it, for example, with:

   ```bash
   python3 tools/fetch_tg_numeric_corpus.py \
     path/to/pin.json \
     --checkout /path/to/corpus-repository
   ```

See
[`docs/NUMERIC_CORPUS_REFERENCES.md`](../../docs/NUMERIC_CORPUS_REFERENCES.md)
for the complete trust model, hash definitions, range rules, and review
checklist.
