// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstdint>

namespace sparkinterval::tg::dirichlet_booker_smallq {

// This format is an explicitly untrusted GPU proposal boundary.  The CUDA
// kernel evaluates the finite Gaussian sum from Platt's Lemmas 7.1/7.2.  The
// Arb checker reconstructs the character, epsilon phase, truncation tail and
// both periodization errors independently; a GPU value never becomes a
// certificate merely by satisfying this binary format.
inline constexpr std::uint32_t kFormatVersion = 1;
inline constexpr std::uint32_t kMaximumModulus = 10000;
inline constexpr std::uint32_t kNonUnitExponent = 0xffffffffU;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'B', 'S', 'Q', 'I', '1'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'B', 'S', 'Q', 'O', '1'};

#pragma pack(push, 1)
struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t group_exponent;
  std::uint32_t parity;
  std::uint64_t transform_length;
  std::uint64_t frequency_start;
  std::uint64_t frequency_count;
  double eta;
  double b;
  double epsilon_real;
  double epsilon_imag;
  std::uint64_t reserved0;
};

// One exponent per residue follows the header.  UINT32_MAX denotes a
// non-unit; otherwise chi(a)=exp(2*pi*i*exponent/group_exponent).
struct FrequencyRequest {
  std::uint64_t index;
  std::int64_t signed_index;
  std::uint32_t truncation;
  std::uint32_t reserved0;
};

struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint64_t frequency_start;
  std::uint64_t frequency_count;
  std::uint64_t elapsed_nanoseconds;
  std::uint64_t reserved0;
};

struct OutputItem {
  std::uint64_t index;
  double real;
  double imag;
  std::uint32_t status;
  std::uint32_t reserved0;
};
#pragma pack(pop)

static_assert(sizeof(InputHeader) == 88);
static_assert(sizeof(FrequencyRequest) == 24);
static_assert(sizeof(OutputHeader) == 48);
static_assert(sizeof(OutputItem) == 32);

}  // namespace sparkinterval::tg::dirichlet_booker_smallq
