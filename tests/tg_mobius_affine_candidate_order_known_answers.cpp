// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_mobius_affine_candidate_order.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <vector>

namespace {

[[noreturn]] void fail(const char* message) {
  std::cerr << message << '\n';
  std::exit(1);
}

TgMobiusAffineMqBoundCandidate candidate(std::int64_t value,
                                         std::uint64_t order) {
  if (order > std::numeric_limits<std::uint32_t>::max()) {
    fail("candidate KAT order exceeds 32 bits");
  }
  return {value, static_cast<std::uint32_t>(2'000 + order),
          static_cast<std::uint32_t>(order)};
}

bool same(const TgMobiusAffineMqBoundCandidate& left,
          const TgMobiusAffineMqBoundCandidate& right) {
  return left.value == right.value &&
         left.local_squarefree == right.local_squarefree &&
         left.order == right.order;
}

bool same(const TgMobiusAffineMqThreadCandidates& left,
          const TgMobiusAffineMqThreadCandidates& right) {
  return same(left.hurst_lower, right.hurst_lower) &&
         same(left.hurst_upper, right.hurst_upper) &&
         same(left.squarefree_lower, right.squarefree_lower) &&
         same(left.squarefree_upper, right.squarefree_upper);
}

TgMobiusAffineMqThreadCandidates record(std::int64_t value,
                                        std::uint32_t order) {
  return {
      candidate(value, order),
      candidate(-value, order),
      candidate(value - static_cast<std::int64_t>(order % 5), order),
      candidate(-value + static_cast<std::int64_t>(order % 7), order)};
}

std::vector<TgMobiusAffineMqThreadCandidates> all_parenthesizations(
    const std::vector<TgMobiusAffineMqThreadCandidates>& rows,
    std::size_t begin, std::size_t end) {
  using sparkinterval::tg::detail::combine_affine_candidates;
  if (end - begin == 1) return {rows[begin]};
  std::vector<TgMobiusAffineMqThreadCandidates> results;
  for (std::size_t split = begin + 1; split < end; ++split) {
    const auto left =
        all_parenthesizations(rows, begin, split);
    const auto right =
        all_parenthesizations(rows, split, end);
    for (const auto& first : left) {
      for (const auto& second : right) {
        results.push_back(
            combine_affine_candidates(first, second));
      }
    }
  }
  return results;
}

}  // namespace

int main() {
  using sparkinterval::tg::detail::empty_max_candidate;
  using sparkinterval::tg::detail::empty_min_candidate;
  using sparkinterval::tg::detail::empty_affine_candidates;
  using sparkinterval::tg::detail::combine_affine_candidates;
  using sparkinterval::tg::detail::insert_max_candidate;
  using sparkinterval::tg::detail::insert_min_candidate;

  auto max_first = empty_max_candidate();
  auto max_second = empty_max_candidate();
  insert_max_candidate(candidate(17, 9), &max_first, &max_second);
  insert_max_candidate(candidate(17, 3), &max_first, &max_second);
  insert_max_candidate(candidate(17, 7), &max_first, &max_second);
  if (max_first.value != 17 || max_first.order != 3 ||
      max_second.value != 17 || max_second.order != 7) {
    fail("maximum reducer discarded an equal-valued distinct order");
  }
  // This models exact replay moving the earlier conservative tie inward by
  // one while leaving the retained second tie unchanged.
  if (max_first.value - 1 >= max_second.value) {
    fail("adversarial maximum tie does not exercise the second candidate");
  }
  insert_max_candidate(candidate(18, 11), &max_first, &max_second);
  if (max_first.value != 18 || max_first.order != 11 ||
      max_second.value != 17 || max_second.order != 3) {
    fail("maximum reducer did not shift the previous first candidate");
  }

  auto min_first = empty_min_candidate();
  auto min_second = empty_min_candidate();
  insert_min_candidate(candidate(-23, 12), &min_first, &min_second);
  insert_min_candidate(candidate(-23, 4), &min_first, &min_second);
  insert_min_candidate(candidate(-23, 8), &min_first, &min_second);
  if (min_first.value != -23 || min_first.order != 4 ||
      min_second.value != -23 || min_second.order != 8) {
    fail("minimum reducer discarded an equal-valued distinct order");
  }
  if (min_first.value + 1 <= min_second.value) {
    fail("adversarial minimum tie does not exercise the second candidate");
  }
  insert_min_candidate(candidate(-24, 14), &min_first, &min_second);
  if (min_first.value != -24 || min_first.order != 14 ||
      min_second.value != -23 || min_second.order != 4) {
    fail("minimum reducer did not shift the previous first candidate");
  }

  // A conservative top-two scheme is not accepted: three rows can tie before
  // exact replay, the first two can move inward, and the third can remain the
  // true extremum.  The production reducer therefore exact-corrects every
  // row before applying the ordinary one-best reduction exercised here.
  auto exact_max = empty_max_candidate();
  insert_max_candidate(candidate(16, 1), &exact_max, nullptr);
  insert_max_candidate(candidate(16, 2), &exact_max, nullptr);
  insert_max_candidate(candidate(17, 3), &exact_max, nullptr);
  if (exact_max.value != 17 || exact_max.order != 3) {
    fail("three-way exact maximum adversary lost its third candidate");
  }
  auto exact_min = empty_min_candidate();
  insert_min_candidate(candidate(-16, 1), &exact_min, nullptr);
  insert_min_candidate(candidate(-16, 2), &exact_min, nullptr);
  insert_min_candidate(candidate(-17, 3), &exact_min, nullptr);
  if (exact_min.value != -17 || exact_min.order != 3) {
    fail("three-way exact minimum adversary lost its third candidate");
  }

  auto singleton_max = empty_max_candidate();
  auto singleton_min = empty_min_candidate();
  insert_max_candidate(candidate(1, 1), &singleton_max, nullptr);
  insert_min_candidate(candidate(-1, 1), &singleton_min, nullptr);
  if (singleton_max.value != 1 || singleton_min.value != -1) {
    fail("single-candidate reducer path failed");
  }

  const auto identity = empty_affine_candidates();
  const auto first = record(11, 8);
  const auto second = record(-4, 3);
  const auto third = record(11, 2);
  if (!same(combine_affine_candidates(identity, first), first) ||
      !same(combine_affine_candidates(first, identity), first)) {
    fail("hierarchical reducer empty identity failed");
  }
  if (!same(combine_affine_candidates(first, first), first)) {
    fail("hierarchical reducer duplicate idempotence failed");
  }
  if (!same(combine_affine_candidates(first, second),
            combine_affine_candidates(second, first))) {
    fail("hierarchical reducer commutativity failed");
  }
  if (!same(
          combine_affine_candidates(
              combine_affine_candidates(first, second), third),
          combine_affine_candidates(
              first, combine_affine_candidates(second, third)))) {
    fail("hierarchical reducer parenthesization failed");
  }
  const std::vector<TgMobiusAffineMqThreadCandidates>
      parenthesization_rows{
          first, second, third, record(-19, 5), record(11, 1)};
  auto parenthesization_expected = identity;
  for (const auto& item : parenthesization_rows) {
    parenthesization_expected =
        combine_affine_candidates(parenthesization_expected, item);
  }
  const auto parenthesized = all_parenthesizations(
      parenthesization_rows, 0, parenthesization_rows.size());
  if (parenthesized.size() != 14 ||
      std::any_of(
          parenthesized.begin(), parenthesized.end(),
          [&](const auto& item) {
            return !same(item, parenthesization_expected);
          })) {
    fail("not all five-input parenthesizations agree");
  }
  const auto earliest_tie =
      combine_affine_candidates(first, third);
  if (earliest_tie.hurst_lower.value != 11 ||
      earliest_tie.hurst_lower.order != 2 ||
      earliest_tie.hurst_upper.value != -11 ||
      earliest_tie.hurst_upper.order != 2) {
    fail("hierarchical reducer did not retain the earliest tie");
  }

  std::mt19937_64 random(0x6d6f626975735f76ULL);
  std::vector<TgMobiusAffineMqThreadCandidates> rows;
  rows.reserve(513);
  for (std::uint32_t order = 0; order < 512; ++order) {
    const std::int64_t value =
        static_cast<std::int64_t>(random() % 41) - 20;
    rows.push_back(record(value, order));
  }
  rows.push_back(rows[137]);
  auto scalar = identity;
  for (const auto& row : rows) {
    scalar = combine_affine_candidates(scalar, row);
  }

  // Simulate thread -> block -> device grouping with deliberately irregular
  // group sizes, then compare it with the scalar fold.
  std::vector<TgMobiusAffineMqThreadCandidates> groups;
  for (std::size_t begin = 0; begin < rows.size(); begin += 17) {
    auto group = identity;
    const std::size_t end = std::min(rows.size(), begin + 17);
    for (std::size_t index = begin; index < end; ++index) {
      group = combine_affine_candidates(group, rows[index]);
    }
    groups.push_back(group);
  }
  auto hierarchical = identity;
  for (const auto& group : groups) {
    hierarchical = combine_affine_candidates(hierarchical, group);
  }
  if (!same(scalar, hierarchical)) {
    fail("thread-block-device reduction differs from scalar fold");
  }

  std::array<std::size_t, 6> permutation{};
  std::iota(permutation.begin(), permutation.end(), 0);
  const std::array<TgMobiusAffineMqThreadCandidates, 6> fixed{
      record(7, 9), record(7, 1), record(-8, 6),
      record(3, 4), record(-8, 2), identity};
  auto expected = identity;
  for (const auto& item : fixed) {
    expected = combine_affine_candidates(expected, item);
  }
  do {
    auto permuted = identity;
    for (const std::size_t index : permutation) {
      permuted = combine_affine_candidates(permuted, fixed[index]);
    }
    if (!same(expected, permuted)) {
      fail("hierarchical reducer depends on input permutation");
    }
  } while (std::next_permutation(
      permutation.begin(), permutation.end()));

  std::cout
      << "affine MQ tied-candidate and hierarchical reduction KAT passed\n";
  return 0;
}
