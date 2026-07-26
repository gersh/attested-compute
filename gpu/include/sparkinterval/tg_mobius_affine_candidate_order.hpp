// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "tg_mobius_segment.h"

#include <cstdint>

#if defined(__CUDACC__)
#define SPARKINTERVAL_TG_HD __host__ __device__
#else
#define SPARKINTERVAL_TG_HD
#endif

namespace sparkinterval::tg::detail {

constexpr std::int64_t kCandidateSigned64Minimum =
    (-9'223'372'036'854'775'807LL - 1);
constexpr std::int64_t kCandidateSigned64Maximum =
    9'223'372'036'854'775'807LL;
constexpr std::uint32_t kCandidateUnsigned32Maximum =
    4'294'967'295U;

SPARKINTERVAL_TG_HD inline TgMobiusAffineMqBoundCandidate
empty_max_candidate() {
  return {kCandidateSigned64Minimum, 0,
          kCandidateUnsigned32Maximum};
}

SPARKINTERVAL_TG_HD inline TgMobiusAffineMqBoundCandidate
empty_min_candidate() {
  return {kCandidateSigned64Maximum, 0,
          kCandidateUnsigned32Maximum};
}

SPARKINTERVAL_TG_HD inline bool same_candidate_order(
    const TgMobiusAffineMqBoundCandidate& left,
    const TgMobiusAffineMqBoundCandidate& right) {
  return left.order == right.order;
}

SPARKINTERVAL_TG_HD inline bool better_max_candidate(
    const TgMobiusAffineMqBoundCandidate& left,
    const TgMobiusAffineMqBoundCandidate& right) {
  return left.value > right.value ||
         (left.value == right.value && left.order < right.order);
}

SPARKINTERVAL_TG_HD inline bool better_min_candidate(
    const TgMobiusAffineMqBoundCandidate& left,
    const TgMobiusAffineMqBoundCandidate& right) {
  return left.value < right.value ||
         (left.value == right.value && left.order < right.order);
}

// Deterministically retain the best exact candidate.  Production passes a
// null second pointer and is sound because every row is exact-corrected before
// insertion.  A nonnull second pointer exists only for the adversarial KAT
// demonstrating why a fixed-width conservative prefilter would be unsound.
SPARKINTERVAL_TG_HD inline void insert_max_candidate(
    TgMobiusAffineMqBoundCandidate candidate,
    TgMobiusAffineMqBoundCandidate* first,
    TgMobiusAffineMqBoundCandidate* second) {
  if (same_candidate_order(candidate, *first)) {
    if (better_max_candidate(candidate, *first)) *first = candidate;
    return;
  }
  if (better_max_candidate(candidate, *first)) {
    if (second != nullptr) *second = *first;
    *first = candidate;
    return;
  }
  if (second == nullptr || same_candidate_order(candidate, *second)) return;
  if (better_max_candidate(candidate, *second)) *second = candidate;
}

SPARKINTERVAL_TG_HD inline void insert_min_candidate(
    TgMobiusAffineMqBoundCandidate candidate,
    TgMobiusAffineMqBoundCandidate* first,
    TgMobiusAffineMqBoundCandidate* second) {
  if (same_candidate_order(candidate, *first)) {
    if (better_min_candidate(candidate, *first)) *first = candidate;
    return;
  }
  if (better_min_candidate(candidate, *first)) {
    if (second != nullptr) *second = *first;
    *first = candidate;
    return;
  }
  if (second == nullptr || same_candidate_order(candidate, *second)) return;
  if (better_min_candidate(candidate, *second)) *second = candidate;
}

SPARKINTERVAL_TG_HD inline TgMobiusAffineMqThreadCandidates
empty_affine_candidates() {
  return {
      empty_max_candidate(),
      empty_min_candidate(),
      empty_max_candidate(),
      empty_min_candidate()};
}

// This is the native realization of the Lean reduction keys
//
//   maximum: (-value, sourceOrder)
//   minimum: ( value, sourceOrder).
//
// Exact candidates make this operation associative, commutative, and
// idempotent.  The corresponding architecture-independent laws are proved in
// HurstAffineCandidateFilter.lean; CUDA execution remains a separate
// refinement obligation.
SPARKINTERVAL_TG_HD inline TgMobiusAffineMqThreadCandidates
combine_affine_candidates(
    TgMobiusAffineMqThreadCandidates left,
    const TgMobiusAffineMqThreadCandidates& right) {
  insert_max_candidate(right.hurst_lower, &left.hurst_lower, nullptr);
  insert_min_candidate(right.hurst_upper, &left.hurst_upper, nullptr);
  insert_max_candidate(
      right.squarefree_lower, &left.squarefree_lower, nullptr);
  insert_min_candidate(
      right.squarefree_upper, &left.squarefree_upper, nullptr);
  return left;
}

}  // namespace sparkinterval::tg::detail

#undef SPARKINTERVAL_TG_HD
