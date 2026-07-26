// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <cstdint>

namespace sparkinterval::tg::dirichlet_allchars {

// One file is one modulus and one ordinate.  Values are indexed by the
// canonical mixed-radix coordinates of
//
//   U(Z/qZ) = product of cyclic prime-power unit-group components,
//
// with the first component varying fastest.  The output uses the same order
// for character frequencies.  Both implementations reconstruct the group
// from q; no factorisation, generator, or twiddle supplied by the producer is
// trusted.
inline constexpr std::uint32_t kFormatVersion = 1;
inline constexpr std::uint32_t kMaximumModulus = 400000;
inline constexpr std::uint32_t kMaxComponents = 8;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'A', 'F', 'F', 'I', '1'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'A', 'F', 'F', 'O', '1'};

using dirichlet_lattice::ComplexInterval;

struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t component_count;
  std::uint32_t batch_count;
  std::uint64_t group_order;
  std::int64_t first_t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  std::uint64_t value_count;
  std::uint64_t reserved0;
};

struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t component_count;
  std::uint32_t batch_count;
  std::uint64_t group_order;
  std::uint64_t value_count;
  std::uint64_t radix2_butterflies;
  std::uint64_t elapsed_nanoseconds;
};

static_assert(sizeof(InputHeader) == 72);
static_assert(sizeof(OutputHeader) == 56);
static_assert(sizeof(ComplexInterval) == 32);

}  // namespace sparkinterval::tg::dirichlet_allchars
