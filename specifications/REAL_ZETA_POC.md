# Real-integer Riemann-zeta proof-of-concept algorithm

Algorithm identifier:
`sparkinterval.real_zeta_integer_dirichlet_integral_tail.v1`.

This document is the human-readable algorithm definition whose exact bytes
are SHA-256-bound into each POC report and run bundle. The calculation is a
rigorous enclosure of the value of the Riemann zeta function at a real integer
`s` satisfying `2 <= s <= 64`. It is a tutorial-scale application of the
interval backend; it is not an algorithm for finding or counting zeta zeros.

## Mathematical statement

For an integer `s >= 2`, use the absolutely convergent Dirichlet series

```text
zeta(s) = sum_{n=1}^infinity 1 / n^s.
```

Choose a positive term count `N`. The GPU evaluates the first `N` terms, one
row per integer `n`, using the fixed postfix expression

```text
const(1), var(0), pow_nat(s), div
```

and the point interval input `[n,n]`. Every input integer is exactly
representable because the wire format permits at most one million rows.

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

## Run and verify

Build the native DGX Spark backend first, then run the default `zeta(2)`
tutorial with 4,096 terms:

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --parallel
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta2-4096 \
  --s 2 --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

The retained test calculation on a GB10 produced the real interval whose raw
binary64 endpoints were

```text
[3ffa51a65a53d51c, 3ffa51a66a52e51f]
```

or, for readability only, approximately
`[1.64493403705757312849, 1.64493409664857614949]`.

Another positive integer argument can use the same algorithm, subject to the
fixed exponent limit and the requirement that all intermediate powers remain
finite. For example:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta3-2048 \
  --s 3 --terms 2048
python3 tools/run_zeta_poc.py verify build/examples/zeta3-2048
```

The run command refuses an existing destination. It stages the exact
executable, input, both byte-identical GPU outputs, runner records, extracted
PTX/SASS and their audits, the arithmetic sources, and this definition under
the new directory. It then creates a canonical `local_unattested` run bundle.
The verifier checks every artifact hash, reparses the exact postfix program
and rows, recomputes all terms, repeats the reduction and tail calculation,
and reconstructs the complete canonical report.

## Trust and scope

The interval conclusion can be independently recomputed from the retained
bytes. The run bundle records that the local runner reported successful DGX
Spark execution, but GB10 provides no confidential-computing attestation for
this workflow. A cryptographic signature made with a user-controlled key can
authenticate which key endorsed the bundle; it cannot prove that the GPU ran,
that the machine was uncompromised, or that the timestamps are externally
trusted.

This algorithm only evaluates `zeta(s)` for real integer `s > 1`. Verification
of zeros on the critical strip additionally needs complex interval
arithmetic, certified transcendental functions and argument reduction,
zero-isolation logic, adaptive precision, and a completeness argument such as
a rigorously instantiated Turing-method layer.
