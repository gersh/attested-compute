// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

namespace sparkinterval {

// Boundary metadata for one independently computed R2Star replay segment.
// The arithmetic payload is deliberately not represented here: the replay
// checks that payload against the retained whole-chunk SHA-256 commitments
// after this structural check succeeds.
struct R2StarReplaySegmentBoundary {
  std::size_t ordinal = 0;
  std::uint64_t lower = 0;
  std::uint64_t upper = 0;
};

// A parallel producer may complete segments in any temporal order, but the
// prefix transition and both legacy SHA-256 streams must consume them in this
// single canonical order.  Requiring the ordinal and both endpoints detects
// reordered, duplicated, omitted, overlapping, and gapped segment summaries
// before any ordered merge is attempted.
template <typename Boundaries>
inline bool is_exact_r2star_replay_partition(
    std::uint64_t expected_lower, std::uint64_t expected_upper,
    const Boundaries& boundaries) {
  if (expected_upper <= expected_lower || boundaries.empty()) return false;
  std::uint64_t cursor = expected_lower;
  for (std::size_t index = 0; index < boundaries.size(); ++index) {
    const R2StarReplaySegmentBoundary& boundary = boundaries[index];
    if (boundary.ordinal != index || boundary.lower != cursor ||
        boundary.upper <= boundary.lower ||
        boundary.upper > expected_upper) {
      return false;
    }
    cursor = boundary.upper;
  }
  return cursor == expected_upper;
}

}  // namespace sparkinterval
