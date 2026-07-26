// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <cstdint>

namespace sparkinterval::tg::dirichlet_recovery_seeds {

inline constexpr std::uint32_t kFormatVersion = 1;
inline constexpr std::uint32_t kSourceM = 4;
inline constexpr std::uint32_t kSourceMaximumQ = 400000;
inline constexpr std::uint64_t kSourceXStart = 1;
inline constexpr std::uint64_t kSourceXStop = 1999999;
inline constexpr std::uint64_t kSourceStepNumerator = 5;
inline constexpr std::uint64_t kSourceStepDenominator = 64;
inline constexpr std::uint64_t kMaximumChunkRecords = 1ULL << 20U;

inline constexpr char kHeaderMagic[8] = {'T', 'G', 'D', 'R', 'C', 'V', 'S', '1'};
inline constexpr char kChunkMagic[8] = {'T', 'G', 'D', 'R', 'C', 'V', 'C', '1'};
inline constexpr char kFooterMagic[8] = {'T', 'G', 'D', 'R', 'C', 'V', 'F', '1'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'R', 'C', 'V', 'O', '1'};

struct Header {
  char magic[8];
  std::uint32_t version;
  std::uint32_t m;
  std::uint32_t maximum_q;
  std::uint32_t record_size;
  std::uint64_t x_start;
  std::uint64_t x_stop;
  std::uint64_t t_step_numerator;
  std::uint64_t t_denominator;
  std::uint64_t record_count;
  std::uint32_t generation_precision_bits;
  std::uint32_t union_precision_bits;
  std::uint64_t chunk_records;
  std::uint64_t reserved0;
  std::uint64_t reserved1;
};

struct ChunkHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t first_x;
  std::uint64_t record_count;
  unsigned char payload_sha256[32];
};

struct SeedRecord {
  double amplitude_lo;
  double amplitude_hi;
  dirichlet_lattice::ComplexInterval phase_step;
};

struct Footer {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t record_count;
  std::uint64_t chunk_count;
  unsigned char records_sha256[32];
  unsigned char chunk_root_sha256[32];
};

// Standalone conformance/benchmark output. Records are frame-major, then
// ascending a in [1,q) with gcd(a,q)=1. Production fusion can retain the same
// device computation and write directly into the large-q composition kernel.
struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t m;
  std::uint32_t batch_count;
  std::uint64_t group_order;
  std::uint64_t first_t_index;
  std::uint64_t t_step_numerator;
  std::uint64_t t_denominator;
  std::uint64_t value_count;
  std::uint64_t reserved0;
};

static_assert(sizeof(Header) == 96);
static_assert(sizeof(ChunkHeader) == 64);
static_assert(sizeof(SeedRecord) == 48);
static_assert(sizeof(Footer) == 96);
static_assert(sizeof(OutputHeader) == 72);

}  // namespace sparkinterval::tg::dirichlet_recovery_seeds
