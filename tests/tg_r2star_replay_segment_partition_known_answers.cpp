// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_r2star_replay_segments.hpp"

#include <array>
#include <cstdint>
#include <iostream>

namespace {

using sparkinterval::R2StarReplaySegmentBoundary;

template <std::size_t Size>
bool accepted(
    std::uint64_t lower, std::uint64_t upper,
    const std::array<R2StarReplaySegmentBoundary, Size>& boundaries) {
  return sparkinterval::is_exact_r2star_replay_partition(
      lower, upper, boundaries);
}

}  // namespace

int main() {
  const std::array<R2StarReplaySegmentBoundary, 3> exact{{
      {0, 1, 17},
      {1, 17, 33},
      {2, 33, 42},
  }};
  if (!accepted(1, 42, exact)) {
    std::cerr << "exact partition was rejected\n";
    return 1;
  }

  auto reordered = exact;
  std::swap(reordered[0], reordered[1]);
  if (accepted(1, 42, reordered)) {
    std::cerr << "reordered partition was accepted\n";
    return 1;
  }

  const std::array<R2StarReplaySegmentBoundary, 2> omitted{{
      exact[0],
      exact[2],
  }};
  if (accepted(1, 42, omitted)) {
    std::cerr << "omitted partition was accepted\n";
    return 1;
  }

  auto mutated = exact;
  ++mutated[1].lower;
  if (accepted(1, 42, mutated)) {
    std::cerr << "gapped partition was accepted\n";
    return 1;
  }

  mutated = exact;
  ++mutated[1].upper;
  if (accepted(1, 42, mutated)) {
    std::cerr << "overlapping partition was accepted\n";
    return 1;
  }

  mutated = exact;
  mutated[1].ordinal = 0;
  if (accepted(1, 42, mutated)) {
    std::cerr << "duplicated ordinal was accepted\n";
    return 1;
  }

  if (accepted(
          1, 42, std::array<R2StarReplaySegmentBoundary, 0>{})) {
    std::cerr << "empty partition was accepted\n";
    return 1;
  }

  std::cout << "R2Star ordered segment-partition KAT passed\n";
  return 0;
}
