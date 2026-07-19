# Versioned algorithm specifications

Files in this directory are protocol inputs, not mutable tutorials. Their
exact bytes may be hashed into reports and run bundles.

`REAL_ZETA_POC.md` is the immutable definition of
`sparkinterval.real_zeta_integer_dirichlet_integral_tail.v1`. Its SHA-256 is
`9a3bd6af5548d2c8c882f30787e4fe1170babca78143a24d40523fbf72ec6cb9`.
Changing the algorithm requires a new identifier and a new specification;
editing the v1 file in place would break verification of existing v1 records.

For current commands and explanatory material, use the mutable
[real-zeta tutorial](../docs/algorithms/REAL_ZETA_POC.md).
