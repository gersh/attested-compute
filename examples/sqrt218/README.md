# Sqrt218 finite-certificate sample

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

`sample-certificate.bound64.json.txt` is a human-readable, non-production
known-answer fixture. It covers only `2 <= n <= 64`. The sole final newline is
for repository display; remove it before passing the bytes to the strict wire
verifier. The canonical wire SHA-256 is
`cc96f30214a37997c1b55fc54454b81aaec2af40fc3abd7a1836a445c8b32db7`.

Generate and check the same sample:

```bash
python3 tools/tg_sqrt218_certificate.py produce /tmp/sqrt218-64.json --bound 64
python3 tools/tg_sqrt218_certificate.py verify /tmp/sqrt218-64.json
```

The sample is not a numeric-corpus pin, an Azure result, a signed receipt, or
evidence for the production bound `2,000,000`.
