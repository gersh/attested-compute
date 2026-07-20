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

`TERNARY_GOLDBACH_EXTERNAL_ATOMS.json` is the machine-readable catalog of the
thirteen source-shaped external atoms currently used by the `claude_math`
ternary Goldbach theorem.  It fixes each Lean declaration name, exact claim,
present evidence, missing completion requirement, feasibility class, and
work-unit count.  The catalog is an audit and planning input; it does not
declare that an external artifact has discharged a Lean atom.

The shared bounded CUDA producer for the CDEM squarefree and Hurst/Mertens
entries is `tg_mobius_segment_v1`.  Its runner emits a deterministic
`tg_mobius_transition_lines_v1` hash chain and independently CPU-checks every
GPU row.  This implementation detail supplements the two source-shaped
catalog entries; it is not a new atom and does not make an incomplete prefix
chain into a full-range certificate. The Python receipt-chain checker only
checks self-reported structure and composition: it neither replays the rows
nor authenticates executable or GPU execution.

For checker commands, the evidence-class vocabulary, measured local timings,
and explicitly labeled H100 planning ranges, read the
[ternary Goldbach external-atoms guide](../docs/algorithms/TERNARY_GOLDBACH_EXTERNAL_ATOMS.md).
