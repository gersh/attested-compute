// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace sparkinterval::tg_goldbach {

constexpr std::uint32_t kOddWheelModulus = 3U * 5U * 7U * 11U * 13U;
constexpr std::uint32_t kOddWheelMaximumStep = 11U;

inline bool odd_wheel_coprime(std::uint32_t residue) {
  return residue % 3U != 0U && residue % 5U != 0U &&
         residue % 7U != 0U && residue % 11U != 0U &&
         residue % 13U != 0U;
}

inline const std::array<std::uint8_t, kOddWheelModulus>&
odd_wheel_step_table() {
  static const std::array<std::uint8_t, kOddWheelModulus> table = [] {
    std::array<std::uint8_t, kOddWheelModulus> result{};
    for (std::uint32_t residue = 0; residue < kOddWheelModulus; ++residue) {
      for (std::uint32_t step = 1; step <= kOddWheelMaximumStep; ++step) {
        if (odd_wheel_coprime(
                (residue + 2U * step) % kOddWheelModulus)) {
          result[residue] = static_cast<std::uint8_t>(step);
          break;
        }
      }
      if (result[residue] == 0U) {
        throw std::logic_error("odd-wheel transition exceeded reviewed gap");
      }
    }
    return result;
  }();
  return table;
}

inline std::uint32_t next_odd_wheel_step(std::uint32_t residue) {
  if (residue >= kOddWheelModulus) {
    throw std::logic_error("odd-wheel residue is outside canonical range");
  }
  return odd_wheel_step_table()[residue];
}

struct DensePrimeState {
  std::uint32_t prime = 0;
  std::uint64_t next_offset = 0;
  std::uint16_t wheel_phase = 0;
};

struct PreparedOddSegment {
  std::uint64_t segment_index = 0;
  std::uint64_t odd_low = 0;
  std::uint64_t odd_count = 0;
  std::vector<DensePrimeState> newly_active_dense;
  std::vector<std::uint32_t> sparse_composite_offsets;
};

namespace detail {

inline std::uint64_t checked_add(std::uint64_t left, std::uint64_t right,
                                 const char* message) {
  if (right > std::numeric_limits<std::uint64_t>::max() - left) {
    throw std::overflow_error(message);
  }
  return left + right;
}

inline std::uint64_t checked_segment_span(std::uint64_t odd_count) {
  if (odd_count == 0 ||
      odd_count > std::numeric_limits<std::uint64_t>::max() / 2U) {
    throw std::invalid_argument("odd segment count is zero or overflows");
  }
  return 2U * odd_count;
}

inline std::uint64_t floor_sqrt(std::uint64_t value) {
  std::uint64_t candidate = static_cast<std::uint64_t>(
      std::sqrt(static_cast<long double>(value)));
  while (candidate != 0 && candidate > value / candidate) --candidate;
  while (candidate != std::numeric_limits<std::uint64_t>::max() &&
         candidate + 1U <= value / (candidate + 1U)) {
    ++candidate;
  }
  return candidate;
}

inline std::uint64_t first_odd_multiple(std::uint64_t odd_low,
                                        std::uint32_t prime) {
  const std::uint64_t p = prime;
  const std::uint64_t quotient = odd_low / p + (odd_low % p != 0 ? 1U : 0U);
  if (quotient > std::numeric_limits<std::uint64_t>::max() / p) {
    throw std::overflow_error("first odd multiple overflows uint64");
  }
  std::uint64_t multiple = quotient * p;
  if ((multiple & 1U) == 0U) {
    multiple = checked_add(multiple, p,
                           "odd-multiple parity adjustment overflows");
  }
  const std::uint64_t square = p * p;
  return std::max(multiple, square);
}

inline std::vector<std::uint32_t> small_seed_primes(std::uint32_t limit) {
  std::vector<std::uint32_t> primes;
  if (limit < 3) return primes;
  const std::size_t odd_count = (static_cast<std::size_t>(limit) - 1U) / 2U;
  std::vector<unsigned char> prime(odd_count, 1U);
  for (std::size_t index = 0; index < odd_count; ++index) {
    const std::uint64_t p = 2U * index + 3U;
    if (p > static_cast<std::uint64_t>(limit) / p) break;
    if (prime[index] == 0U) continue;
    const std::uint64_t first = (p * p - 3U) / 2U;
    for (std::uint64_t composite = first; composite < odd_count;
         composite += p) {
      prime[static_cast<std::size_t>(composite)] = 0U;
    }
  }
  for (std::size_t index = 0; index < odd_count; ++index) {
    if (prime[index] != 0U) {
      primes.push_back(static_cast<std::uint32_t>(2U * index + 3U));
    }
  }
  return primes;
}

}  // namespace detail

inline std::uint64_t floor_sqrt(std::uint64_t value) {
  return detail::floor_sqrt(value);
}

// Generate every odd prime <= limit with bounded working memory.  The seed
// sieve has size O(sqrt(limit)); the output itself is necessarily O(pi(limit)).
inline std::vector<std::uint32_t> segmented_odd_primes(
    std::uint32_t limit, std::uint64_t segment_odds = 1U << 20U) {
  if (limit < 3) return {};
  if (segment_odds == 0 || segment_odds > (1ULL << 31U)) {
    throw std::invalid_argument("base-prime segment size is outside review bounds");
  }
  const std::uint32_t root = static_cast<std::uint32_t>(
      detail::floor_sqrt(static_cast<std::uint64_t>(limit)));
  const std::vector<std::uint32_t> seeds = detail::small_seed_primes(root);
  std::vector<std::uint32_t> primes;
  if (limit >= 100) {
    const long double estimate =
        static_cast<long double>(limit) / std::log(static_cast<long double>(limit));
    const long double reserved = std::min<long double>(
        static_cast<long double>(std::numeric_limits<std::size_t>::max()),
        estimate * 1.2L + 1024.0L);
    primes.reserve(static_cast<std::size_t>(reserved));
  }

  const std::uint64_t value_span = 2U * segment_odds;
  for (std::uint64_t low = 3; low <= limit;) {
    const std::uint64_t remaining =
        static_cast<std::uint64_t>(limit) - low + 1U;
    const std::uint64_t high =
        low + std::min<std::uint64_t>(value_span, remaining);
    const std::size_t count = static_cast<std::size_t>((high - low + 1U) / 2U);
    std::vector<unsigned char> is_prime(count, 1U);
    for (const std::uint32_t p32 : seeds) {
      const std::uint64_t p = p32;
      if (p > (high - 1U) / p) break;
      std::uint64_t multiple = detail::first_odd_multiple(low, p32);
      if (multiple >= high) continue;
      for (; multiple < high;) {
        is_prime[static_cast<std::size_t>((multiple - low) / 2U)] = 0U;
        if (2U * p > std::numeric_limits<std::uint64_t>::max() - multiple) break;
        multiple += 2U * p;
      }
    }
    for (std::size_t index = 0; index < count; ++index) {
      const std::uint64_t value = low + 2U * index;
      if (value <= limit && is_prime[index] != 0U) {
        primes.push_back(static_cast<std::uint32_t>(value));
      }
    }
    if (high > limit) break;
    low = (high & 1U) == 0U ? high + 1U : high;
  }
  return primes;
}

// A persistent hybrid schedule for contiguous equal-size odd segments.
//
// Primes p <= odd_count are dense: a consumer retains one next offset and
// visits that state every segment.  Larger primes have at most one odd
// multiple in a segment.  They are therefore retained only in the circular
// bucket containing their next actual multiple.  No segment scans all sparse
// primes.  A prime is activated once p^2 first enters the campaign, so a
// campaign beginning below its largest base-prime square is also exact.
class PersistentOddPrimeSchedule {
 public:
  PersistentOddPrimeSchedule(std::uint64_t first_odd_low,
                             std::uint64_t odd_count,
                             std::uint64_t segment_count,
                             std::vector<std::uint32_t> odd_primes,
                             bool wheel_filtered = false)
      : first_odd_low_(first_odd_low),
        odd_count_(odd_count),
        segment_count_(segment_count),
        wheel_filtered_(wheel_filtered),
        odd_primes_(std::move(odd_primes)) {
    if ((first_odd_low_ & 1U) == 0U) {
      throw std::invalid_argument("first odd-segment low endpoint must be odd");
    }
    if (segment_count_ == 0) {
      throw std::invalid_argument("segment count must be positive");
    }
    if (odd_count_ > std::numeric_limits<std::uint32_t>::max()) {
      throw std::invalid_argument("odd segment count must fit sparse offsets");
    }
    const std::uint64_t span = detail::checked_segment_span(odd_count_);
    if (segment_count_ >
        (std::numeric_limits<std::uint64_t>::max() - first_odd_low_) / span) {
      throw std::invalid_argument("campaign endpoint overflows uint64");
    }
    for (std::size_t index = 0; index < odd_primes_.size(); ++index) {
      const std::uint32_t p = odd_primes_[index];
      if (p < 3 || (p & 1U) == 0U ||
          (index != 0 && odd_primes_[index - 1U] >= p)) {
        throw std::invalid_argument(
            "base-prime table must be strictly increasing odd integers >= 3");
      }
    }
    base_limit_ = odd_primes_.empty() ? 1U : odd_primes_.back();
    const std::uint64_t horizon_multiplier =
        wheel_filtered_ ? kOddWheelMaximumStep : 1U;
    if (base_limit_ >
        std::numeric_limits<std::uint64_t>::max() / horizon_multiplier) {
      throw std::invalid_argument("bucket horizon multiplication overflows");
    }
    const std::uint64_t ring_size =
        horizon_multiplier * base_limit_ / odd_count_ + 3U;
    if (ring_size > (1ULL << 24U)) {
      throw std::invalid_argument(
          "bucket ring exceeds review bound; use a larger odd segment");
    }
    buckets_.resize(static_cast<std::size_t>(ring_size));
  }

  std::uint64_t odd_count() const { return odd_count_; }
  std::uint64_t segment_count() const { return segment_count_; }
  std::uint64_t prepared_count() const { return next_segment_; }
  std::uint64_t bucket_ring_size() const { return buckets_.size(); }
  std::uint64_t activated_prime_count() const { return activation_index_; }
  std::uint64_t sparse_event_count() const { return sparse_event_count_; }
  const std::vector<std::uint32_t>& odd_primes() const { return odd_primes_; }

  PreparedOddSegment prepare_next() {
    if (next_segment_ >= segment_count_) {
      throw std::out_of_range("all configured odd segments were already prepared");
    }
    const std::uint64_t span = 2U * odd_count_;
    const std::uint64_t low = first_odd_low_ + next_segment_ * span;
    const std::uint64_t high = low + span;
    PreparedOddSegment result;
    result.segment_index = next_segment_;
    result.odd_low = low;
    result.odd_count = odd_count_;

    // Each prime is examined here exactly once over the entire campaign.
    while (activation_index_ < odd_primes_.size()) {
      const std::uint32_t p = odd_primes_[activation_index_];
      const std::uint64_t square = static_cast<std::uint64_t>(p) * p;
      if (square >= high) break;
      ++activation_index_;
      std::uint64_t multiple = detail::first_odd_multiple(low, p);
      std::uint32_t wheel_phase = 0;
      if (wheel_filtered_) {
        std::uint64_t cofactor = multiple / p;
        while (!odd_wheel_coprime(
            static_cast<std::uint32_t>(cofactor % kOddWheelModulus))) {
          if (2U * static_cast<std::uint64_t>(p) >
              std::numeric_limits<std::uint64_t>::max() - multiple) {
            throw std::overflow_error("wheel-filtered multiple overflows");
          }
          multiple += 2U * static_cast<std::uint64_t>(p);
          cofactor += 2U;
        }
        wheel_phase =
            static_cast<std::uint32_t>(cofactor % kOddWheelModulus);
      }
      if (multiple < low || ((multiple - low) & 1U) != 0U) {
        throw std::logic_error("odd multiple does not align with odd segment");
      }
      const std::uint64_t offset = (multiple - low) / 2U;
      if (p <= odd_count_) {
        result.newly_active_dense.push_back(
            {p, offset, static_cast<std::uint16_t>(wheel_phase)});
      } else {
        schedule_sparse(p, offset, wheel_phase, next_segment_);
      }
    }

    const std::size_t slot =
        static_cast<std::size_t>(next_segment_ % buckets_.size());
    std::vector<SparseEvent> events;
    events.swap(buckets_[slot]);
    result.sparse_composite_offsets.reserve(events.size());
    for (const SparseEvent& event : events) {
      if (event.offset >= odd_count_ || event.prime <= odd_count_) {
        throw std::logic_error("malformed sparse-prime bucket event");
      }
      result.sparse_composite_offsets.push_back(event.offset);
      ++sparse_event_count_;
      const std::uint32_t step =
          wheel_filtered_ ? next_odd_wheel_step(event.wheel_phase) : 1U;
      const std::uint64_t next =
          static_cast<std::uint64_t>(event.offset) +
          static_cast<std::uint64_t>(event.prime) * step;
      const std::uint32_t next_phase = wheel_filtered_
          ? (event.wheel_phase + 2U * step) % kOddWheelModulus
          : 0U;
      const std::uint64_t delta = next / odd_count_;
      if (delta == 0 || delta >= buckets_.size()) {
        throw std::logic_error("sparse event escaped circular-bucket horizon");
      }
      const std::uint64_t target = next_segment_ + delta;
      if (target < segment_count_) {
        buckets_[static_cast<std::size_t>(target % buckets_.size())].push_back(
            {event.prime, static_cast<std::uint32_t>(next % odd_count_),
             static_cast<std::uint16_t>(next_phase)});
      }
    }
    ++next_segment_;
    return result;
  }

 private:
  struct SparseEvent {
    std::uint32_t prime = 0;
    std::uint32_t offset = 0;
    std::uint16_t wheel_phase = 0;
  };

  void schedule_sparse(std::uint32_t prime, std::uint64_t offset,
                       std::uint32_t wheel_phase,
                       std::uint64_t current_segment) {
    const std::uint64_t delta = offset / odd_count_;
    if (delta >= buckets_.size()) {
      throw std::logic_error("initial sparse event escaped bucket horizon");
    }
    const std::uint64_t target = current_segment + delta;
    if (target < segment_count_) {
      buckets_[static_cast<std::size_t>(target % buckets_.size())].push_back(
          {prime, static_cast<std::uint32_t>(offset % odd_count_),
           static_cast<std::uint16_t>(wheel_phase)});
    }
  }

  std::uint64_t first_odd_low_ = 0;
  std::uint64_t odd_count_ = 0;
  std::uint64_t segment_count_ = 0;
  bool wheel_filtered_ = false;
  std::vector<std::uint32_t> odd_primes_;
  std::uint64_t base_limit_ = 0;
  std::vector<std::vector<SparseEvent>> buckets_;
  std::size_t activation_index_ = 0;
  std::uint64_t next_segment_ = 0;
  std::uint64_t sparse_event_count_ = 0;
};

inline std::vector<std::uint64_t> stateless_odd_prime_words(
    std::uint64_t odd_low, std::uint64_t odd_count,
    const std::vector<std::uint32_t>& odd_primes,
    bool include_wheel_primes = false) {
  if ((odd_low & 1U) == 0U || odd_count == 0 ||
      odd_count > (1ULL << 32U)) {
    throw std::invalid_argument("invalid stateless odd-prime segment");
  }
  const std::uint64_t span = detail::checked_segment_span(odd_count);
  const std::uint64_t high = detail::checked_add(
      odd_low, span, "stateless odd-prime endpoint overflows");
  std::vector<std::uint64_t> words(
      static_cast<std::size_t>((odd_count + 63U) / 64U),
      std::numeric_limits<std::uint64_t>::max());
  if (include_wheel_primes) {
    constexpr std::uint32_t wheel_primes[] = {3U, 5U, 7U, 11U, 13U};
    for (const std::uint32_t p : wheel_primes) {
      std::uint64_t multiple = detail::first_odd_multiple(odd_low, p);
      while (multiple < high) {
        const std::uint64_t offset = (multiple - odd_low) / 2U;
        words[static_cast<std::size_t>(offset / 64U)] &=
            ~(1ULL << (offset & 63U));
        multiple += 2U * p;
      }
    }
  }
  for (const std::uint32_t p : odd_primes) {
    const std::uint64_t square = static_cast<std::uint64_t>(p) * p;
    if (square >= high) break;
    std::uint64_t multiple = detail::first_odd_multiple(odd_low, p);
    for (; multiple < high;) {
      const std::uint64_t offset = (multiple - odd_low) / 2U;
      words[static_cast<std::size_t>(offset / 64U)] &=
          ~(1ULL << (offset & 63U));
      if (2U * p > std::numeric_limits<std::uint64_t>::max() - multiple) break;
      multiple += 2U * p;
    }
  }
  if (odd_low == 1U) words[0] &= ~1ULL;
  const unsigned tail = static_cast<unsigned>(odd_count & 63U);
  if (tail != 0U) words.back() &= (1ULL << tail) - 1U;
  return words;
}

}  // namespace sparkinterval::tg_goldbach
