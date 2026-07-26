# Certified inputs for the large-q Dirichlet lattice

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This component turns the conditional input boundary of the large-`q` Taylor
kernel into replayable analytic data. It does not verify GRH or discharge
`platt-dirichlet-theorem-7-1`.

## Source mapping

The primary source is D. J. Platt,
[*Numerical computations concerning the GRH*](https://arxiv.org/abs/1305.3087v1).
The certificate records hashes of the v1 PDF and TeX source as well as this
mapping:

| Paper location | Retained artifact meaning |
|---|---|
| Section 4 and Lemma 4.1 | Supply one Hurwitz value for each unit residue before the unit-group DFT. |
| Section 4.1, page 7 | One lattice has `D=2048` rows and columns `c=0,...,15` at `s=1/2+it+c`. |
| Lemma 4.2 | Taylor reconstruction, with the strict guard `|a/q-r/D| < r/D`. |
| Paragraph after Lemma 4.2 | Use `zeta_M(s,alpha)=zeta(s,alpha)-sum_(n=0)^M (n+alpha)^(-s)` and add the omitted finite terms back. |

The v1 TeX contains candidate numerical tail lemmas inside comments; they are
absent from the rendered paper. The implementation therefore does not cite
them as published lemmas. Instead it records and exactly replays a conservative
rational derivation for the first omitted index `K=16`.

For `s=1/2+it`, `B=M+1`, and the maximum request displacement `d`, it uses

```text
Z_K <= B^(-K) + 2 B^(-(K-1))/(2K-1),
P_K <= product_(j=0)^(K-1) (t+j+1/2),
rho <= d/B * max(1, (t+1/2+K)/(K+1)),
R_K <= d^K P_K Z_K / (K! (1-rho)).
```

All quantities on the right are exact rationals, `rho < 1` is checked, and
the final binary64 radius is rounded upward. The first line follows from the
decreasing-function integral test for the absolutely convergent Dirichlet
series of `zeta_M(s+K,alpha)`. The ratio follows by comparing consecutive
absolute Taylor terms. The left edge of the lattice is clipped at `r=1`, so
the checker uses the actual rational displacement and checks Lemma 4.2's
strict guard rather than assuming the interior `1/(2D)` distance.

## Retained bundle and replay

`tg_verifier/dirichlet_lattice_certificates.py` publishes an immutable bundle:

- `lattice-input.bin` uses the existing `TGDLATI1` schema. Its 32,768 cells
  enclose the named `zeta_M` values. Every request carries the replayed uniform
  tail radius.
- `finite-recovery.bin` uses `TGDLREC1`. For each identical `(q,a)` request it
  encloses

  ```text
  R_M(s;q,a) = sum_(n=0)^M (q*n+a)^(-s).
  ```

  Thus a later transform may use the exact identity

  ```text
  L(s,chi) = sum_a chi(a) * (q^(-s) zeta_M(s,a/q) + R_M(s;q,a)).
  ```

- `certificate.json` hashes both binary files, the producer module, exact
  request sequence, paper sources, Python executable, and the relevant
  python-flint extension modules. It pins python-flint 0.9.0 / FLINT 3.6.0.

Generation computes each analytic value at two precisions and retains their
union. Replay uses a separately structured summation at still higher precision
and requires every new Arb ball to lie inside the stored binary64 rectangle.
It also recomputes the request sequence and rational tail derivation from
scratch. Hash-only tampering, a rehashed synthetic seed, and an attempt to set
`external_atom_discharged=true` all fail closed in the tests.

```bash
python3 tools/tg_dirichlet_lattice_certificates.py --pretty capability
python3 tools/tg_dirichlet_lattice_certificates.py generate /tmp/dl-cert \
  --q-start 10001 --q-stop 10001 --t-index 127 --m 4
python3 tools/tg_dirichlet_lattice_certificates.py replay /tmp/dl-cert
python3 tools/tg_dirichlet_lattice_certificates.py --pretty benchmark \
  --t-index 127987 --m 4 --lattice-rows 32 --recovery-items 128
```

`--max-items` is only a labeled sample control. Omitting it makes a complete
batch for the selected `q` interval and ordinate, not a complete Theorem 7.1
campaign.

The local verification reported below used an isolated target directory (not
a repository venv):

```bash
python3 -m pip install --target /tmp/python-flint-0.9.0 python-flint==0.9.0
PYTHONPATH=/tmp/python-flint-0.9.0:. \
  python3 -m unittest -v tests.test_tg_dirichlet_lattice_certificates
```

The certificate itself records the resolved Python executable hash and hashes
of the loaded `pyflint`, `acb`, `arb`, `arf`, `fmpq`, `fmpz`, and context
extensions; the replay refuses any python-flint/FLINT version mismatch.

## Remaining boundary

The certificate capability reports `component_ready`, `production_ready`, and
`full_source` separately. Only the certified-input component is ready. A full
source run still requires the all-character interval FFT, completed-`L` phase,
small-modulus path, zero isolation and exceptional-case handling, rigorous
upsampling, multiplicity-preserving Turing completeness, retained authenticated
runs, and the Lean realization bridge. Consequently `production_ready` and
`full_source` remain false.
