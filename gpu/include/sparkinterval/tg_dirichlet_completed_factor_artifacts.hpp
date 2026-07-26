// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_dirichlet_booker_smallq_certified.hpp"

#include <cstdint>

namespace sparkinterval::tg::dirichlet_completed_factor_artifacts {

namespace certified = dirichlet_booker_smallq_certified;

inline constexpr char kGammaMagic[8] =
    {'T', 'G', 'D', 'C', 'G', 'A', 'M', '1'};
inline constexpr char kStepMagic[8] =
    {'T', 'G', 'D', 'C', 'S', 'T', 'P', '1'};
inline constexpr char kCheckpointMagic[8] =
    {'T', 'G', 'D', 'C', 'C', 'P', 'B', '1'};
inline constexpr std::uint32_t kFormatVersion = 1U;
inline constexpr std::uint32_t kBoundedClassification = 0U;
inline constexpr std::uint32_t kFullSourceClassification = 1U;
inline constexpr std::uint64_t kSourceDenominator = 64U;
inline constexpr std::uint32_t kSourceStepNumerator = 5U;
inline constexpr std::uint32_t kDefaultCheckpointSpan = 4096U;
inline constexpr std::uint64_t kSourceTIndexStop = 127988U;
inline constexpr std::uint64_t kSourceQStop = 400000U;

// SHA-256 of the ASCII convention string exported by
// tg_verifier.dirichlet_completed_factor_artifacts.
inline constexpr Sha256Digest kFactorConventionSha256 = {
    0xd4, 0xa3, 0x37, 0xca, 0xef, 0x77, 0x22, 0xd1,
    0x45, 0x36, 0x7b, 0xa2, 0xf8, 0x37, 0x03, 0x53,
    0xc3, 0x3f, 0x1f, 0xd6, 0xc2, 0xd1, 0x64, 0xe3,
    0xbc, 0x71, 0xaf, 0x93, 0x74, 0x73, 0x19, 0x72,
};

struct GammaHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t classification;
  std::uint32_t disk_size;
  std::uint32_t reserved;
  std::uint64_t first_t_index;
  std::uint64_t t_index_stop_exclusive;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  std::uint64_t disk_count;
  Sha256Digest factor_convention_sha256;
  Sha256Digest producer_identity_sha256;
};

struct StepHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t classification;
  std::uint32_t disk_size;
  std::uint32_t reserved;
  std::uint32_t primitive_roster_version;
  std::uint32_t q_count;
  std::uint64_t q_start;
  std::uint64_t q_stop;
  Sha256Digest schedule_manifest_sha256;
  Sha256Digest execution_order_sha256;
  Sha256Digest factor_convention_sha256;
};

struct CheckpointHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t classification;
  std::uint32_t disk_size;
  std::uint32_t record_header_size;
  std::uint64_t phase_index;
  std::uint64_t first_t_index;
  std::uint64_t t_index_stop_exclusive;
  std::uint64_t t_denominator;
  std::uint32_t t_step_numerator;
  std::uint32_t checkpoint_span;
  std::uint64_t q_count;
  std::uint64_t checkpoint_count;
  Sha256Digest schedule_manifest_sha256;
  Sha256Digest phase_schedule_sha256;
  Sha256Digest gamma_artifact_sha256;
  Sha256Digest step_artifact_sha256;
};

struct CheckpointRecordHeader {
  std::uint32_t q;
  std::uint32_t sample_count;
  std::uint32_t checkpoint_count;
  std::uint32_t reserved;
};

static_assert(sizeof(certified::Disk) == 24U);
static_assert(sizeof(GammaHeader) == 128U);
static_assert(sizeof(StepHeader) == 144U);
static_assert(sizeof(CheckpointHeader) == 208U);
static_assert(sizeof(CheckpointRecordHeader) == 16U);

}  // namespace sparkinterval::tg::dirichlet_completed_factor_artifacts
