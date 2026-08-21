# Vendored `PrimeNumberTheoremAnd` — rectangle argument principle only

Upstream: <https://github.com/AlexKontorovich/PrimeNumberTheoremAnd>, Apache
License 2.0 (see `LICENSE` in this directory).

## What is vendored, and why

`SparkInterval/Zeta/XiArgumentPrinciple.lean` needs an argument principle on a
rectangle: the boundary integral of `f'/f` counts the zeros of `f` inside, with
multiplicity.  Mathlib does not have one.  The PrimeNumberTheoremAnd project
does, stated in Mathlib-native terms (`MeromorphicOn`, `meromorphicOrderAt`,
`MeromorphicOn.divisor`) and generic in `f` — nothing zeta-specific.

Only the **five modules in the transitive closure** of
`PrimeNumberTheoremAnd.RectangleArgumentPrinciple` are vendored:

| module | lines |
|---|---|
| `PrimeNumberTheoremAnd/RectangleArgumentPrinciple.lean` | 373 |
| `PrimeNumberTheoremAnd/ResidueCalcOnRectangles.lean` | 1288 |
| `PrimeNumberTheoremAnd/Rectangle.lean` | 281 |
| `PrimeNumberTheoremAnd/Mathlib/Analysis/Meromorphic/DivisorSupport.lean` | 137 |
| `PrimeNumberTheoremAnd/Tactic/AdditiveCombination.lean` | 186 |

They import nothing outside Mathlib and `Architect` (the `LeanArchitect`
dependency this repository already requires).  They are declared as the
`PrimeNumberTheoremAnd` `lean_lib` in `lakefile.toml`, with `srcDir = "vendor"`.

## Trust status

* All five modules are **`sorry`-free**, contain no `native_decide`, and no
  `axiom` declaration.
* `#print axioms` on the two exported results is the base trio:

  ```
  'rectangleIntegral_logDeriv_eq_sum_meromorphicOrderAt' depends on axioms:
    [propext, Classical.choice, Quot.sound]
  'rectangle_argumentChange_eq_two_pi_sum_meromorphicOrderAt' depends on axioms:
    [propext, Classical.choice, Quot.sound]
  ```

## Source snapshot and local modification

Copied on 2026-07-30 from `/home/gersh/claude_math/forks/PrimeNumberTheoremAnd`,
which is itself a vendored snapshot of the upstream `4.31`/`4.32` tree (see that
directory's `VENDOR_PROVENANCE.md`).  The statements are identical to current
upstream; the only upstream change since that snapshot touching these files is
the `v4.32.0` toolchain bump, a six-line rewrite inside one private helper, with
no change to any statement, signature, or hypothesis.

**One local modification**, in `RectangleArgumentPrinciple.lean`, inside the
private helper `tendsto_mul_self_of_sub_principal_isBigO_one`: the original
`simpa` step rewrites `fun z => z - p` into `id - fun _ => p` under this
repository's Mathlib pin and then fails to match.  It is replaced by a direct
`continuous_sub_right`/`mono_left` argument, marked in the source with a
`LOCAL ADAPTATION` comment.  Nothing else was changed.

## Re-vendoring

Copy the five files above from a newer upstream checkout, rebuild
`lake build PrimeNumberTheoremAnd.RectangleArgumentPrinciple`, and re-check
`#print axioms` on the two exported results.
