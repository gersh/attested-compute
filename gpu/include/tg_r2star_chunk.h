// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "tg_r2star_factor_support.h"

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

// This fixed configuration is deliberately narrower than the Python
// reference's parameter space.  Q64 interval arithmetic resolves the exact
// Fraction-based floor/ceil at scale 2^32 or rejects the row as ambiguous.
constexpr std::uint32_t kTgR2StarScaleBits = 32;
constexpr std::uint32_t kTgR2StarSeriesTerms = 20;
constexpr std::uint32_t kTgR2StarHarmonicTerms = 100'000;
constexpr std::uint64_t kTgR2StarGammaLower = 2'479'051'107ULL;
constexpr std::uint64_t kTgR2StarGammaUpper = 2'479'194'040ULL;

enum class TgR2StarRowStatus : std::uint32_t {
  valid = 0,
  invalid_factor_support = 1,
  log_resolution_ambiguous = 2,
  fixed_point_overflow = 3,
};

enum class TgR2StarChunkStatus : std::uint32_t {
  valid = 0,
  invalid_row = 1,
  prefix_overflow = 2,
  squared_comparison_overflow = 3,
  inequality_failed = 4,
  no_envelope_endpoint = 5,
};

struct alignas(8) TgR2StarDirectedRow {
  std::uint64_t log_lower;
  std::uint64_t log_upper;
  std::int64_t delta_lower;
  std::int64_t delta_upper;
  std::uint32_t status;
  std::uint32_t reserved;
};

struct alignas(8) TgUnsigned128 {
  std::uint64_t low;
  std::uint64_t high;
};

struct alignas(8) TgR2StarChunkSummary {
  std::int64_t outgoing_lower;
  std::int64_t outgoing_upper;
  TgUnsigned128 minimum_squared_slack;
  std::uint64_t minimum_slack_index;
  std::uint64_t first_bad_index;
  std::uint32_t status;
  std::uint32_t reserved;
};

constexpr std::size_t kTgR2StarTransitionBlockRows = 1024;

struct alignas(8) TgR2StarPrefixBlock {
  std::int64_t lower;
  std::int64_t upper;
  std::uint64_t first_bad_index;
  std::uint32_t status;
  std::uint32_t reserved;
};

struct alignas(8) TgR2StarEnvelopeRow {
  TgUnsigned128 squared_slack;
  std::uint64_t index;
  std::uint32_t status;
  std::uint32_t reserved;
};

struct alignas(8) TgR2StarEnvelopeBlock {
  TgUnsigned128 minimum_squared_slack;
  std::uint64_t minimum_slack_index;
  std::uint64_t first_bad_index;
  std::uint32_t status;
  std::uint32_t reserved;
};

static_assert(sizeof(TgR2StarDirectedRow) == 40);
static_assert(sizeof(TgUnsigned128) == 16);
static_assert(sizeof(TgR2StarChunkSummary) == 56);
static_assert(sizeof(TgR2StarPrefixBlock) == 32);
static_assert(sizeof(TgR2StarEnvelopeRow) == 32);
static_assert(sizeof(TgR2StarEnvelopeBlock) == 40);

// Compute exact Python-contract log bounds and directed coefficient deltas.
// A row is valid only when the rigorous Q64 enclosure uniquely determines the
// scale-2^32 floor and ceil.  Ambiguous rows are rejected, never widened.
cudaError_t launch_tg_r2star_directed_rows(
    std::uint64_t lower, std::size_t count,
    const TgR2StarFactorSupport* factor_support,
    TgR2StarDirectedRow* rows, cudaStream_t stream = nullptr);

// Apply the exact additive recurrence and squared envelope in deterministic
// index order.  This single-thread reference kernel is intentionally a
// correctness implementation, not yet a production parallel prefix scan.
cudaError_t launch_tg_r2star_chunk_transition(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    TgR2StarChunkSummary* summary, cudaStream_t stream = nullptr);

// Deterministic blocked implementation of the same transition.  Each
// recurrence block scans at most 1024 rows, one tiny kernel composes block
// offsets, envelope rows are parallel, and block minima are reduced in two
// bounded stages.  Every signed addition and wide multiplication retains the
// same fail-closed checks as the serial reference.
cudaError_t launch_tg_r2star_parallel_chunk_transition(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    std::int64_t* prefix_lower, std::int64_t* prefix_upper,
    TgR2StarPrefixBlock* prefix_blocks,
    TgR2StarEnvelopeRow* envelope_rows,
    TgR2StarEnvelopeBlock* envelope_blocks,
    TgR2StarChunkSummary* summary, cudaStream_t stream = nullptr);
