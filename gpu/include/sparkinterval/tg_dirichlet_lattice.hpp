// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::dirichlet_lattice {

// Platt, arXiv:1305.3087v1, Section 4.1: the large-q Hurwitz lattice has
// D = 2048 rows and columns c = 0,...,N with N = 15.
inline constexpr std::uint32_t kLatticeRows = 2048;
inline constexpr std::uint32_t kTaylorDegree = 15;
inline constexpr std::uint32_t kTaylorColumns = kTaylorDegree + 1;
inline constexpr std::uint64_t kLatticeCellCount =
    static_cast<std::uint64_t>(kLatticeRows) * kTaylorColumns;
inline constexpr std::uint32_t kFormatVersion = 1;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'L', 'A', 'T', 'I', '1'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'L', 'A', 'T', 'O', '1'};

struct RealInterval {
  double lo;
  double hi;
};

struct ComplexInterval {
  RealInterval re;
  RealInterval im;
};

// One input contains a single exact ordinate t=t_numerator/t_denominator,
// its shared D*(N+1) Hurwitz-zeta lattice, then item_count residue requests.
// All integers and binary64 values are little-endian. Production profiles use
// t >= 0; negative ordinates are intentionally outside this stage contract.
struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t lattice_rows;
  std::uint32_t taylor_degree;
  std::uint32_t reserved0;
  std::int64_t t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t item_count;
  std::uint64_t lattice_cell_count;
  std::uint64_t reserved1;
};

// The lattice row is not trusted: both runners recompute the canonical nearest
// row to a/q, with ties toward the lower row and clipping to [1,D]. Only unit
// residues are admitted. tail_radius_hi is an externally certified upper bound
// for the complex Taylor remainder; this stage does not manufacture that bound.
struct InputItem {
  std::uint32_t q;
  std::uint32_t a;
  std::uint32_t lattice_row;
  std::uint32_t reserved;
  double tail_radius_hi;
};

struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t lattice_rows;
  std::uint32_t taylor_degree;
  std::uint32_t reserved0;
  std::uint64_t item_count;
  std::uint64_t elapsed_nanoseconds;
  std::uint64_t reserved1;
};

struct OutputItem {
  std::uint32_t q;
  std::uint32_t a;
  std::uint32_t lattice_row;
  std::uint32_t status;
  ComplexInterval value;
};

inline constexpr std::size_t lattice_index(std::uint32_t row,
                                            std::uint32_t column) {
  return (static_cast<std::size_t>(row) - 1U) * kTaylorColumns + column;
}

// floor(D*a/q + 1/2), with exact integer arithmetic, ties toward the lower
// integer. Since 1 <= a < q, the upper clipping is defensive only.
inline constexpr std::uint32_t canonical_lattice_row(std::uint32_t q,
                                                      std::uint32_t a) {
  const std::uint64_t twice_numerator =
      2ULL * kLatticeRows * static_cast<std::uint64_t>(a);
  const std::uint64_t twice_q = 2ULL * q;
  // Subtract one before division so an exact half-way case rounds down.
  std::uint64_t row = (twice_numerator + q - 1ULL) / twice_q;
  if (row < 1ULL) row = 1ULL;
  if (row > kLatticeRows) row = kLatticeRows;
  return static_cast<std::uint32_t>(row);
}

static_assert(sizeof(RealInterval) == 16);
static_assert(sizeof(ComplexInterval) == 32);
static_assert(sizeof(InputHeader) == 64);
static_assert(sizeof(InputItem) == 24);
static_assert(sizeof(OutputHeader) == 48);
static_assert(sizeof(OutputItem) == 48);

}  // namespace sparkinterval::tg::dirichlet_lattice
