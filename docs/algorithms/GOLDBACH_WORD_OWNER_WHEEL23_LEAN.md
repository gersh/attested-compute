# Through-23 word-owner wheel: Lean arithmetic boundary

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

`SparkInterval/TernaryGoldbach/GoldbachWordOwnerWheel23.lean` verifies the
pure arithmetic semantics of the proposed word-owner-aligned odd-residue
wheel through 23.

The checked model fixes:

- wheel primes `3, 5, 7, 11, 13, 17, 19, 23`;
- odd-index modulus `111,546,435`, their exact product;
- table value `2 * (phase % 111546435) + 1`;
- 64 duplicated head bits for one contiguous owner-word lookup;
- phase
  `((qLow >> 1) % M + ((wordIndex % M) * 64) % M + bit) % M`; and
- addressed candidate `qLow + 128 * wordIndex + 2 * bit`.

For odd `qLow` and `bit < 64`, Lean proves that the phase addresses the exact
candidate, divisibility agrees for every listed wheel prime, restoring those
eight primes exactly recovers the original square-guarded initializer, and
subsequent clearing by any remaining prime list is unchanged.

The companion
`SparkInterval/TernaryGoldbach/GoldbachWordOwnerWheel23PhaseHoist.lean`
proves the optimized machine-arithmetic layer:

- host `UInt64` `(qLow >> 1) % M`;
- device `UInt32` multiply/add without wrap;
- two guarded subtractions in place of remainder;
- `phase >> 6` and `phase & 63`; and
- both packed-table read indices within the exact `M + 64`-bit allocation.

The source word-count equation and overflow/address bounds are explicit.
Both modules use only Lean's base trio.

This is not a CUDA refinement or a production qualification. In particular,
it does not prove table generation or transfer, byte/bit packing and global
memory realization, CUDA load behavior, compiler preservation, PTX/SASS
semantics, hardware execution, or an authenticated run. A physical candidate
must bind its implementation to these models and discharge those obligations
separately.
