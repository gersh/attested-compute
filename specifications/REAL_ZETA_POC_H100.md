# H100 real-integer Riemann-zeta proof-of-concept algorithm

Algorithm identifier:
`sparkinterval.real_zeta_integer_dirichlet_integral_tail.h100.v1`.

This document is the human-readable algorithm definition whose exact bytes
are SHA-256-bound into each H100 POC report and run bundle. The calculation is
a rigorous enclosure of the value of the Riemann zeta function at a real
integer `s` satisfying `2 <= s <= 64`. It is a tutorial-scale application of
the H100 interval backend; it is not an algorithm for finding or counting zeta
zeros.

## Mathematical statement

For an integer `s >= 2`, use the absolutely convergent Dirichlet series

```text
zeta(s) = sum_{n=1}^infinity 1 / n^s.
```

Choose a positive term count `N`. A single visible NVIDIA H100 with compute
capability 9.0 evaluates the first `N` terms, one row per integer `n`, using
the fixed postfix expression

```text
const(1), var(0), pow_nat(s), div
```

and the point interval input `[n,n]`. Every input integer is exactly
representable because the wire format permits at most one million rows. The
H100 runner must reject a non-H100 device and must not accept the generic
cross-device override.

The exact checker requires every raw output endpoint and status byte to equal
the result of the rational `reference.exact_binary64` evaluator. It then adds
the retained output intervals sequentially in ascending `n` order using
outward-rounded binary64 interval addition.

For `f(x) = x^(-s)`, positivity and monotone decrease give the integral-test
remainder bounds

```text
1 / ((s - 1) * (N + 1)^(s - 1))
    <= sum_{n=N+1}^infinity 1 / n^s
    <= 1 / ((s - 1) * N^(s - 1)).
```

Both rationals are converted to an outward-rounded binary64 interval. Adding
that interval to the partial-sum interval yields the reported enclosure of
the real part of `zeta(s)`. The imaginary part is exactly zero for these real
arguments.

## Run, replay, and verify

The H100 executable is built specifically for `sm_90`. Before either retained
run, its embedded device image is extracted and checked for the expected
directed binary64 operations and target, and its SASS is inspected by the
repository policy. The exact executable, input, both byte-identical outputs,
runner records, extracted PTX/SASS and audits, arithmetic sources, target
profile, and this definition are hash-bound into a canonical
`local_unattested` run bundle.

The verifier does not trust the report's success boolean. It checks every
artifact hash, reparses the exact postfix program and rows, recomputes every
term, repeats the ordered reduction and tail calculation, reruns the PTX and
SASS audits, and requires both H100 executions to have byte-identical output.

## Trust and scope

The interval conclusion can be independently recomputed from the retained
bytes. The local run bundle records that the strict runner reported execution
on an H100, but this algorithm version does not claim confidential-computing
attestation. A local operator signature authenticates only an endorsement of
the retained bytes. It does not by itself prove that the GPU ran, that the
machine was uncompromised, or that the timestamps are externally trusted.

This algorithm only evaluates `zeta(s)` for a real integer `s > 1`.
Verification of zeros on the critical strip additionally needs complex
interval arithmetic, certified transcendental functions and argument
reduction, zero-isolation logic, adaptive precision, and a completeness
argument such as a rigorously instantiated Turing-method layer.
