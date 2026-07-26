// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_allchars.hpp"
#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::dirichlet_largeq_batch {

// One self-delimiting input frame is one q and at most 64 consecutive
// ordinates.  It contains no transcendental expressions for CUDA to evaluate:
// every Hurwitz value, finite-recovery sum, Taylor radius, and q^(-s) factor
// is already an outward binary64 interval produced by a separately audited
// MPFR/Arb certificate generator.
inline constexpr std::uint32_t kFormatVersion = 1;
inline constexpr std::uint32_t kMaximumBatchCount = 64;
inline constexpr std::uint32_t kMinimumModulus = 10001;
inline constexpr std::uint32_t kMaximumModulus = 400000;
inline constexpr std::uint64_t kSourceTDenominator = 64;
inline constexpr std::uint64_t kSourceTStepNumerator = 5;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'L', 'Q', 'B', 'I', '1'};

using dirichlet_lattice::ComplexInterval;

struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t lattice_rows;
  std::uint32_t taylor_degree;
  std::uint32_t component_count;
  std::uint32_t batch_count;
  std::uint32_t m;
  std::uint32_t reserved0;
  std::uint64_t group_order;
  std::int64_t first_t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  std::uint64_t lattice_cell_count;
  std::uint64_t value_count;
  std::uint64_t reserved1;
};

// Stored once per canonical mixed-radix group position.  The runner
// independently reconstructs the same CRT order from q before launching.
struct ResidueDescriptor {
  std::uint32_t a;
  std::uint32_t lattice_row;

  bool operator==(const ResidueDescriptor&) const = default;
};

// Stored once per ordinate.  The producer computes this enclosure with MPFR:
//
//   q^(-1/2-it) = q^(-1/2) (cos(t log q) - i sin(t log q)).
//
// It is data, never recomputed with CUDA libdevice.
struct FrameFactor {
  ComplexInterval q_to_the_minus_s;
};

// Stored once per (ordinate, canonical residue).  finite_recovery encloses
// sum_{n=0}^M (qn+a)^(-s), generated/replayed outside this CUDA stage.
struct CertifiedResidueBox {
  double taylor_tail_radius_hi;
  ComplexInterval finite_recovery;
};

static_assert(sizeof(InputHeader) == 96);
static_assert(sizeof(ResidueDescriptor) == 8);
static_assert(sizeof(FrameFactor) == 32);
static_assert(sizeof(CertifiedResidueBox) == 40);

}  // namespace sparkinterval::tg::dirichlet_largeq_batch
