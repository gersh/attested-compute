// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::dirichlet_fused {

// This is the compact, selected-character oracle boundary which follows the
// Taylor stage.  One input ordinate owns one D*(N+1) lattice and any number of
// modulus tasks.  Unit residues are reconstructed from the canonical CRT
// decomposition on the device; there is no per-residue input or output.
inline constexpr std::uint32_t kFormatVersion = 1;
inline constexpr std::uint32_t kMaxLocalFactors = 8;
inline constexpr std::uint32_t kMaxComponents = 8;
inline constexpr std::uint32_t kMaximumModulus = 400000;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'F', 'U', 'S', 'I', '1'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'F', 'U', 'S', 'O', '1'};

using dirichlet_lattice::ComplexInterval;

struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t lattice_rows;
  std::uint32_t taylor_degree;
  std::uint32_t task_count;
  std::uint32_t total_local_factors;
  std::uint32_t total_components;
  std::uint32_t total_characters;
  std::uint32_t reserved0;
  std::int64_t t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t lattice_cell_count;
  std::uint64_t reserved1;
  std::uint64_t reserved2;
};

// Offsets refer to the global arrays immediately following the header.  Tasks
// are stored in strictly increasing q order and all three ranges are required
// to be contiguous.  group_order must equal phi(q).
struct ModulusTask {
  std::uint32_t q;
  std::uint32_t local_factor_offset;
  std::uint32_t local_factor_count;
  std::uint32_t component_offset;
  std::uint32_t component_count;
  std::uint32_t character_offset;
  std::uint32_t character_count;
  std::uint32_t reserved0;
  std::uint64_t group_order;
  double tail_radius_hi;
  std::uint64_t reserved1;
};

// A local factor is one prime power p^e exactly dividing q.  The stored CRT
// cofactor and inverse are redundant and are independently recomputed by both
// host implementations before a kernel may run.
struct LocalFactor {
  std::uint32_t modulus;
  std::uint32_t component_offset;
  std::uint32_t component_count;
  std::uint32_t reserved0;
  std::uint64_t crt_cofactor;
  std::uint64_t crt_inverse;
};

// Odd prime powers have one cyclic component.  U(4) has one component and
// U(2^e), e>2, has the (-1,5) components.  root encloses
// exp(+2*pi*i/order); proving that transcendental fact is deliberately an
// input-certificate obligation of this conditional stage.
struct CyclicComponent {
  std::uint32_t local_factor_index;
  std::uint32_t generator;
  std::uint32_t order;
  std::uint32_t reserved0;
  ComplexInterval root;
};

// frequency[j] selects the character which maps generator j to
// root[j]^frequency[j].  Unused entries must be zero.  id is the canonical
// mixed-radix ordinal sum_j frequency[j]*product_{i<j}(order[i]); requests
// must increase strictly within each modulus task.
struct CharacterRequest {
  std::uint32_t id;
  std::uint32_t reserved0;
  std::uint32_t frequency[kMaxComponents];
};

struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t task_count;
  std::uint32_t total_characters;
  std::uint32_t reserved0;
  std::uint64_t total_group_points_per_iteration;
  std::uint64_t elapsed_nanoseconds;
  std::uint64_t reserved1;
};

struct OutputItem {
  std::uint32_t q;
  std::uint32_t character_id;
  std::uint32_t status;
  std::uint32_t reserved0;
  ComplexInterval value;
};

static_assert(sizeof(InputHeader) == 80);
static_assert(sizeof(ModulusTask) == 56);
static_assert(sizeof(LocalFactor) == 32);
static_assert(sizeof(CyclicComponent) == 48);
static_assert(sizeof(CharacterRequest) == 40);
static_assert(sizeof(OutputHeader) == 48);
static_assert(sizeof(OutputItem) == 48);

}  // namespace sparkinterval::tg::dirichlet_fused
