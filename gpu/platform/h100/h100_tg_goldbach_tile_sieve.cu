// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Race-free tile-compacted odd-prime sieve for the word-oriented Goldbach
// route.  The implementation deliberately has a new, unregistered identity.
// It is a performance experiment and cannot issue a production receipt.

#include <cuda_runtime.h>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_goldbach_bucket_sieve.hpp"

namespace {

constexpr unsigned kThreads = 256U;
constexpr std::uint32_t kNoStride = 0U;

struct TileEvent {
  std::uint32_t local_offset;
  std::uint32_t stride;
};

static_assert(sizeof(TileEvent) == 8U);

void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::uint64_t parse_u64(const char* text, const char* name) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error(std::string(name) + " must be a natural number");
  }
  char* end = nullptr;
  errno = 0;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0') {
    throw std::runtime_error(std::string(name) + " is not canonical decimal");
  }
  return static_cast<std::uint64_t>(value);
}

std::string json_escape(const char* text) {
  std::string result;
  for (const unsigned char byte : std::string(text)) {
    switch (byte) {
      case '\\': result += "\\\\"; break;
      case '"': result += "\\\""; break;
      case '\n': result += "\\n"; break;
      case '\r': result += "\\r"; break;
      case '\t': result += "\\t"; break;
      default:
        if (byte < 0x20U) {
          constexpr char hex[] = "0123456789abcdef";
          result += "\\u00";
          result.push_back(hex[byte >> 4U]);
          result.push_back(hex[byte & 0x0fU]);
        } else {
          result.push_back(static_cast<char>(byte));
        }
    }
  }
  return result;
}

struct Options {
  std::uint64_t odd_low = 100000000000001ULL;
  std::uint64_t segment_odds = 1ULL << 20U;
  std::uint64_t segments = 8U;
  std::uint64_t tile_odds = 1ULL << 15U;
  std::uint64_t replay_segments = 2U;
  std::uint64_t base_limit = 0U;
  std::uint64_t base_prime_segment_odds = 1ULL << 20U;
};

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    auto value_after = [&](const char* prefix) -> const char* {
      const std::string key(prefix);
      if (argument.rfind(key, 0) != 0) return nullptr;
      return argv[index] + key.size();
    };
    if (const char* value = value_after("--odd-low=")) {
      options.odd_low = parse_u64(value, "odd low");
    } else if (const char* value = value_after("--segment-odds=")) {
      options.segment_odds = parse_u64(value, "segment odd count");
    } else if (const char* value = value_after("--segments=")) {
      options.segments = parse_u64(value, "segment count");
    } else if (const char* value = value_after("--tile-odds=")) {
      options.tile_odds = parse_u64(value, "tile odd count");
    } else if (const char* value = value_after("--replay-segments=")) {
      options.replay_segments = parse_u64(value, "replay segment count");
    } else if (const char* value = value_after("--base-limit=")) {
      options.base_limit = parse_u64(value, "base-prime limit");
    } else if (const char* value = value_after("--base-prime-segment-odds=")) {
      options.base_prime_segment_odds =
          parse_u64(value, "base-prime segment odd count");
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  if ((options.odd_low & 1U) == 0U || options.segment_odds == 0U ||
      options.segment_odds > (1ULL << 31U) || options.segments == 0U ||
      options.replay_segments > options.segments || options.tile_odds < 64U ||
      (options.tile_odds & 63U) != 0U ||
      options.tile_odds > options.segment_odds ||
      options.base_prime_segment_odds == 0U ||
      options.base_prime_segment_odds > (1ULL << 31U)) {
    throw std::runtime_error("requested tile-sieve dimensions are outside review bounds");
  }
  const std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max();
  if (options.segments > maximum / 2U ||
      options.segment_odds > maximum / (2U * options.segments) ||
      2U * options.segment_odds * options.segments > maximum - options.odd_low) {
    throw std::runtime_error("requested tile-sieve campaign endpoint overflows uint64");
  }
  const std::uint64_t exclusive_high =
      options.odd_low + 2U * options.segment_odds * options.segments;
  const std::uint64_t required_limit =
      sparkinterval::tg_goldbach::floor_sqrt(exclusive_high - 1U);
  if (options.base_limit == 0U) options.base_limit = required_limit;
  if (options.base_limit < required_limit ||
      options.base_limit > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error(
        "base limit must cover floor(sqrt(last odd candidate)) and fit uint32");
  }
  return options;
}

template <std::uint32_t Prime>
__device__ __forceinline__ void clear_small_prime_from_word(
    std::uint64_t word_low, unsigned long long& word) {
  constexpr std::uint32_t inverse_two = (Prime + 1U) / 2U;
  const std::uint32_t residue = static_cast<std::uint32_t>(word_low % Prime);
  const std::uint32_t first = static_cast<std::uint32_t>(
      (static_cast<std::uint64_t>((Prime - residue) % Prime) * inverse_two) %
      Prime);
  constexpr std::uint64_t square =
      static_cast<std::uint64_t>(Prime) * Prime;
  for (std::uint32_t bit = first; bit < 64U; bit += Prime) {
    const std::uint64_t candidate = word_low + 2U * bit;
    if (candidate >= square) word &= ~(1ULL << bit);
  }
}

__device__ __forceinline__ std::uint64_t next_tile_multiple(
    std::uint64_t offset, std::uint64_t prime, std::uint64_t tile_odds,
    std::uint64_t odd_count) {
  const std::uint64_t tile = offset / tile_odds;
  const std::uint64_t boundary =
      min((tile + 1U) * tile_odds, odd_count);
  const std::uint64_t distance = boundary - offset;
  const std::uint64_t steps = distance / prime + (distance % prime != 0U);
  return offset + steps * prime;
}

__global__ void count_dense_tile_events(
    const std::uint32_t* __restrict__ primes,
    const std::uint64_t* __restrict__ next_offsets,
    std::uint64_t prime_count, std::uint64_t odd_count,
    std::uint64_t tile_odds, std::uint32_t* __restrict__ tile_counts) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  std::uint64_t offset = next_offsets[index];
  while (offset < odd_count) {
    atomicAdd(tile_counts + offset / tile_odds, 1U);
    offset = next_tile_multiple(offset, prime, tile_odds, odd_count);
  }
}

__global__ void count_sparse_tile_events(
    const std::uint32_t* __restrict__ sparse_offsets,
    std::uint64_t sparse_count, std::uint64_t tile_odds,
    std::uint32_t* __restrict__ tile_counts) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < sparse_count) {
    atomicAdd(tile_counts + sparse_offsets[index] / tile_odds, 1U);
  }
}

__global__ void prefix_tile_counts(
    const std::uint32_t* __restrict__ tile_counts,
    std::uint32_t* __restrict__ tile_offsets,
    std::uint32_t* __restrict__ tile_cursors, std::uint32_t tile_count,
    std::uint32_t event_capacity, std::uint32_t* __restrict__ overflow) {
  if (blockIdx.x != 0U || threadIdx.x != 0U) return;
  std::uint64_t total = 0U;
  for (std::uint32_t tile = 0U; tile < tile_count; ++tile) {
    const std::uint32_t clipped = static_cast<std::uint32_t>(
        min(total, static_cast<std::uint64_t>(event_capacity)));
    tile_offsets[tile] = clipped;
    tile_cursors[tile] = clipped;
    total += tile_counts[tile];
  }
  tile_offsets[tile_count] = static_cast<std::uint32_t>(
      min(total, static_cast<std::uint64_t>(event_capacity)));
  if (total > event_capacity) *overflow = 1U;
}

__global__ void fill_dense_tile_events(
    const std::uint32_t* __restrict__ primes,
    std::uint64_t* __restrict__ next_offsets, std::uint64_t prime_count,
    std::uint64_t odd_count, std::uint64_t tile_odds,
    const std::uint32_t* __restrict__ tile_offsets,
    std::uint32_t* __restrict__ tile_cursors,
    TileEvent* __restrict__ events, std::uint32_t* __restrict__ overflow) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  std::uint64_t offset = next_offsets[index];
  while (offset < odd_count) {
    const std::uint32_t tile = static_cast<std::uint32_t>(offset / tile_odds);
    const std::uint32_t position = atomicAdd(tile_cursors + tile, 1U);
    if (position < tile_offsets[tile + 1U]) {
      events[position] = {
          static_cast<std::uint32_t>(offset -
                                     static_cast<std::uint64_t>(tile) *
                                         tile_odds),
          static_cast<std::uint32_t>(prime)};
    } else {
      atomicExch(overflow, 1U);
    }
    offset = next_tile_multiple(offset, prime, tile_odds, odd_count);
  }
  next_offsets[index] = offset - odd_count;
}

__global__ void fill_sparse_tile_events(
    const std::uint32_t* __restrict__ sparse_offsets,
    std::uint64_t sparse_count, std::uint64_t tile_odds,
    const std::uint32_t* __restrict__ tile_offsets,
    std::uint32_t* __restrict__ tile_cursors,
    TileEvent* __restrict__ events, std::uint32_t* __restrict__ overflow) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= sparse_count) return;
  const std::uint64_t offset = sparse_offsets[index];
  const std::uint32_t tile = static_cast<std::uint32_t>(offset / tile_odds);
  const std::uint32_t position = atomicAdd(tile_cursors + tile, 1U);
  if (position < tile_offsets[tile + 1U]) {
    events[position] = {
        static_cast<std::uint32_t>(offset -
                                   static_cast<std::uint64_t>(tile) *
                                       tile_odds),
        kNoStride};
  } else {
    atomicExch(overflow, 1U);
  }
}

// Each block owns one tile.  Event producers never mutate shared sieve words
// without synchronization: all colliding clears use 64-bit shared atomicAnd.
// After the block barrier, each packed word has exactly one output owner.
__global__ void mark_compacted_tiles(
    std::uint64_t odd_low, std::uint64_t odd_count,
    std::uint64_t tile_odds,
    const std::uint32_t* __restrict__ tile_offsets,
    const TileEvent* __restrict__ events,
    unsigned long long* __restrict__ output_words) {
  extern __shared__ unsigned long long shared_words[];
  const std::uint64_t tile = blockIdx.x;
  const std::uint64_t tile_begin = tile * tile_odds;
  if (tile_begin >= odd_count) return;
  const std::uint64_t live_odds = min(tile_odds, odd_count - tile_begin);
  const std::uint64_t live_words = (live_odds + 63U) / 64U;

  for (std::uint64_t word_index = threadIdx.x; word_index < live_words;
       word_index += blockDim.x) {
    const std::uint64_t global_word = tile_begin / 64U + word_index;
    const std::uint64_t word_low = odd_low + 128U * global_word;
    unsigned long long word = ~0ULL;
    clear_small_prime_from_word<3U>(word_low, word);
    clear_small_prime_from_word<5U>(word_low, word);
    clear_small_prime_from_word<7U>(word_low, word);
    clear_small_prime_from_word<11U>(word_low, word);
    clear_small_prime_from_word<13U>(word_low, word);
    shared_words[word_index] = word;
  }
  __syncthreads();

  const std::uint32_t event_begin = tile_offsets[tile];
  const std::uint32_t event_end = tile_offsets[tile + 1U];
  for (std::uint64_t event_index =
           static_cast<std::uint64_t>(event_begin) + threadIdx.x;
       event_index < event_end; event_index += blockDim.x) {
    const TileEvent event = events[event_index];
    std::uint64_t local = event.local_offset;
    do {
      atomicAnd(shared_words + local / 64U,
                ~(1ULL << static_cast<unsigned>(local & 63U)));
      if (event.stride == kNoStride) break;
      local += event.stride;
    } while (local < live_odds);
  }
  __syncthreads();

  for (std::uint64_t word_index = threadIdx.x; word_index < live_words;
       word_index += blockDim.x) {
    output_words[tile_begin / 64U + word_index] = shared_words[word_index];
  }
}

__global__ void mask_prime_word_edges(std::uint64_t odd_low,
                                      std::uint64_t odd_count,
                                      unsigned long long* words) {
  if (blockIdx.x != 0U || threadIdx.x != 0U) return;
  if (odd_low == 1U) words[0] &= ~1ULL;
  const unsigned tail = static_cast<unsigned>(odd_count & 63U);
  if (tail != 0U) {
    words[(odd_count - 1U) / 64U] &= (1ULL << tail) - 1U;
  }
}

void update_canonical_digest(sparkinterval::detail::Sha256& hasher,
                             const std::vector<std::uint64_t>& words) {
  unsigned char encoded[8];
  for (const std::uint64_t word : words) {
    for (unsigned byte = 0U; byte < 8U; ++byte) {
      encoded[byte] = static_cast<unsigned char>(word >> (8U * byte));
    }
    hasher.update(encoded, sizeof(encoded));
  }
}

std::uint64_t dense_tile_event_capacity(
    const std::vector<std::uint32_t>& scheduled_primes,
    std::uint64_t dense_count, std::uint64_t odd_count,
    std::uint64_t tile_odds) {
  const std::uint64_t tile_count = (odd_count + tile_odds - 1U) / tile_odds;
  std::uint64_t capacity = 0U;
  for (std::uint64_t index = 0U; index < dense_count; ++index) {
    const std::uint64_t prime = scheduled_primes[index];
    const std::uint64_t multiples = (odd_count + prime - 1U) / prime;
    const std::uint64_t contribution = std::min(tile_count, multiples);
    if (contribution > std::numeric_limits<std::uint64_t>::max() - capacity) {
      throw std::runtime_error("dense tile-event bound overflows uint64");
    }
    capacity += contribution;
  }
  return capacity;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    int device = 0;
    cudaDeviceProp properties{};
    cuda_check(cudaGetDevice(&device), "cudaGetDevice");
    cuda_check(cudaGetDeviceProperties(&properties, device),
               "cudaGetDeviceProperties");

    const std::uint64_t tile_count64 =
        (options.segment_odds + options.tile_odds - 1U) / options.tile_odds;
    if (tile_count64 > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("tile count does not fit the CUDA grid");
    }
    const std::uint32_t tile_count = static_cast<std::uint32_t>(tile_count64);
    const std::size_t tile_shared_bytes =
        static_cast<std::size_t>((options.tile_odds + 63U) / 64U) *
        sizeof(unsigned long long);
    const std::size_t shared_limit = properties.sharedMemPerBlockOptin != 0U
        ? properties.sharedMemPerBlockOptin
        : properties.sharedMemPerBlock;
    if (tile_shared_bytes > shared_limit) {
      throw std::runtime_error("tile words exceed the device shared-memory bound");
    }
    if (tile_shared_bytes > properties.sharedMemPerBlock) {
      cuda_check(cudaFuncSetAttribute(
                     mark_compacted_tiles,
                     cudaFuncAttributeMaxDynamicSharedMemorySize,
                     static_cast<int>(tile_shared_bytes)),
                 "cudaFuncSetAttribute tile shared memory");
    }

    const auto base_start = std::chrono::steady_clock::now();
    const std::vector<std::uint32_t> base_primes =
        sparkinterval::tg_goldbach::segmented_odd_primes(
            static_cast<std::uint32_t>(options.base_limit),
            options.base_prime_segment_odds);
    const auto base_stop = std::chrono::steady_clock::now();
    const double base_seconds =
        std::chrono::duration<double>(base_stop - base_start).count();

    std::vector<std::uint32_t> scheduled_primes;
    scheduled_primes.reserve(base_primes.size());
    for (const std::uint32_t prime : base_primes) {
      if (prime != 3U && prime != 5U && prime != 7U && prime != 11U &&
          prime != 13U) {
        scheduled_primes.push_back(prime);
      }
    }
    const std::size_t dense_capacity = static_cast<std::size_t>(
        std::upper_bound(
            scheduled_primes.begin(), scheduled_primes.end(),
            static_cast<std::uint32_t>(options.segment_odds)) -
        scheduled_primes.begin());
    const std::size_t sparse_prime_count =
        scheduled_primes.size() - dense_capacity;
    const std::uint64_t dense_event_bound = dense_tile_event_capacity(
        scheduled_primes, dense_capacity, options.segment_odds,
        options.tile_odds);
    const std::uint64_t event_capacity64 =
        dense_event_bound + sparse_prime_count;
    if (event_capacity64 == 0U ||
        event_capacity64 > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("tile-event capacity is outside uint32 bounds");
    }
    const std::uint32_t event_capacity =
        static_cast<std::uint32_t>(event_capacity64);

    sparkinterval::tg_goldbach::PersistentOddPrimeSchedule schedule(
        options.odd_low, options.segment_odds, options.segments,
        std::move(scheduled_primes), true);

    std::uint32_t* device_dense_primes = nullptr;
    std::uint64_t* device_dense_offsets = nullptr;
    if (dense_capacity != 0U) {
      cuda_check(cudaMalloc(&device_dense_primes,
                            dense_capacity * sizeof(std::uint32_t)),
                 "cudaMalloc dense primes");
      cuda_check(cudaMalloc(&device_dense_offsets,
                            dense_capacity * sizeof(std::uint64_t)),
                 "cudaMalloc dense offsets");
    }
    std::uint32_t* device_sparse_offsets = nullptr;
    std::size_t sparse_capacity = 0U;
    std::uint32_t* device_tile_counts = nullptr;
    std::uint32_t* device_tile_offsets = nullptr;
    std::uint32_t* device_tile_cursors = nullptr;
    std::uint32_t* device_overflow = nullptr;
    TileEvent* device_events = nullptr;
    unsigned long long* device_words = nullptr;
    cuda_check(cudaMalloc(&device_tile_counts,
                          tile_count * sizeof(std::uint32_t)),
               "cudaMalloc tile counts");
    cuda_check(cudaMalloc(&device_tile_offsets,
                          (static_cast<std::size_t>(tile_count) + 1U) *
                              sizeof(std::uint32_t)),
               "cudaMalloc tile offsets");
    cuda_check(cudaMalloc(&device_tile_cursors,
                          tile_count * sizeof(std::uint32_t)),
               "cudaMalloc tile cursors");
    cuda_check(cudaMalloc(&device_overflow, sizeof(std::uint32_t)),
               "cudaMalloc overflow flag");
    cuda_check(cudaMalloc(&device_events,
                          static_cast<std::size_t>(event_capacity) *
                              sizeof(TileEvent)),
               "cudaMalloc tile events");
    const std::uint64_t word_count = (options.segment_odds + 63U) / 64U;
    cuda_check(cudaMalloc(&device_words,
                          word_count * sizeof(unsigned long long)),
               "cudaMalloc output words");

    cudaEvent_t gpu_start{};
    cudaEvent_t gpu_stop{};
    cuda_check(cudaEventCreate(&gpu_start), "cudaEventCreate start");
    cuda_check(cudaEventCreate(&gpu_stop), "cudaEventCreate stop");

    std::size_t active_dense_count = 0U;
    std::uint64_t total_sparse_events = 0U;
    std::uint64_t total_compacted_events = 0U;
    std::uint64_t replayed_prime_bits = 0U;
    double host_schedule_seconds = 0.0;
    double gpu_seconds = 0.0;
    double pipeline_seconds = 0.0;
    double replay_seconds = 0.0;
    sparkinterval::detail::Sha256 replay_hasher;
    std::vector<std::uint64_t> host_words(static_cast<std::size_t>(word_count));

    for (std::uint64_t segment_index = 0U;
         segment_index < options.segments; ++segment_index) {
      const auto pipeline_start = std::chrono::steady_clock::now();
      const auto schedule_start = std::chrono::steady_clock::now();
      const sparkinterval::tg_goldbach::PreparedOddSegment prepared =
          schedule.prepare_next();
      const auto schedule_stop = std::chrono::steady_clock::now();
      host_schedule_seconds +=
          std::chrono::duration<double>(schedule_stop - schedule_start).count();

      if (active_dense_count + prepared.newly_active_dense.size() >
          dense_capacity) {
        throw std::runtime_error("active dense-prime state exceeded capacity");
      }
      if (!prepared.newly_active_dense.empty()) {
        std::vector<std::uint32_t> new_primes;
        std::vector<std::uint64_t> new_offsets;
        new_primes.reserve(prepared.newly_active_dense.size());
        new_offsets.reserve(prepared.newly_active_dense.size());
        for (const auto& state : prepared.newly_active_dense) {
          new_primes.push_back(state.prime);
          new_offsets.push_back(state.next_offset);
        }
        cuda_check(cudaMemcpy(device_dense_primes + active_dense_count,
                              new_primes.data(),
                              new_primes.size() * sizeof(std::uint32_t),
                              cudaMemcpyHostToDevice),
                   "cudaMemcpy new dense primes");
        cuda_check(cudaMemcpy(device_dense_offsets + active_dense_count,
                              new_offsets.data(),
                              new_offsets.size() * sizeof(std::uint64_t),
                              cudaMemcpyHostToDevice),
                   "cudaMemcpy new dense offsets");
        active_dense_count += prepared.newly_active_dense.size();
      }

      const std::size_t sparse_count =
          prepared.sparse_composite_offsets.size();
      if (sparse_count > sparse_capacity) {
        if (device_sparse_offsets != nullptr) {
          cuda_check(cudaFree(device_sparse_offsets),
                     "cudaFree old sparse offsets");
        }
        sparse_capacity = sparse_count;
        cuda_check(cudaMalloc(&device_sparse_offsets,
                              sparse_capacity * sizeof(std::uint32_t)),
                   "cudaMalloc sparse offsets");
      }
      if (sparse_count != 0U) {
        cuda_check(cudaMemcpy(device_sparse_offsets,
                              prepared.sparse_composite_offsets.data(),
                              sparse_count * sizeof(std::uint32_t),
                              cudaMemcpyHostToDevice),
                   "cudaMemcpy sparse offsets");
      }
      total_sparse_events += sparse_count;

      cuda_check(cudaEventRecord(gpu_start), "cudaEventRecord start");
      cuda_check(cudaMemset(device_tile_counts, 0,
                            tile_count * sizeof(std::uint32_t)),
                 "cudaMemset tile counts");
      cuda_check(cudaMemset(device_overflow, 0, sizeof(std::uint32_t)),
                 "cudaMemset overflow flag");
      if (active_dense_count != 0U) {
        const std::uint32_t blocks = static_cast<std::uint32_t>(
            (active_dense_count + kThreads - 1U) / kThreads);
        count_dense_tile_events<<<blocks, kThreads>>>(
            device_dense_primes, device_dense_offsets, active_dense_count,
            options.segment_odds, options.tile_odds, device_tile_counts);
        cuda_check(cudaGetLastError(), "count dense tile events launch");
      }
      if (sparse_count != 0U) {
        const std::uint32_t blocks = static_cast<std::uint32_t>(
            (sparse_count + kThreads - 1U) / kThreads);
        count_sparse_tile_events<<<blocks, kThreads>>>(
            device_sparse_offsets, sparse_count, options.tile_odds,
            device_tile_counts);
        cuda_check(cudaGetLastError(), "count sparse tile events launch");
      }
      prefix_tile_counts<<<1U, 1U>>>(
          device_tile_counts, device_tile_offsets, device_tile_cursors,
          tile_count, event_capacity, device_overflow);
      cuda_check(cudaGetLastError(), "prefix tile counts launch");
      if (active_dense_count != 0U) {
        const std::uint32_t blocks = static_cast<std::uint32_t>(
            (active_dense_count + kThreads - 1U) / kThreads);
        fill_dense_tile_events<<<blocks, kThreads>>>(
            device_dense_primes, device_dense_offsets, active_dense_count,
            options.segment_odds, options.tile_odds, device_tile_offsets,
            device_tile_cursors, device_events, device_overflow);
        cuda_check(cudaGetLastError(), "fill dense tile events launch");
      }
      if (sparse_count != 0U) {
        const std::uint32_t blocks = static_cast<std::uint32_t>(
            (sparse_count + kThreads - 1U) / kThreads);
        fill_sparse_tile_events<<<blocks, kThreads>>>(
            device_sparse_offsets, sparse_count, options.tile_odds,
            device_tile_offsets, device_tile_cursors, device_events,
            device_overflow);
        cuda_check(cudaGetLastError(), "fill sparse tile events launch");
      }
      mark_compacted_tiles<<<tile_count, kThreads, tile_shared_bytes>>>(
          prepared.odd_low, options.segment_odds, options.tile_odds,
          device_tile_offsets, device_events, device_words);
      cuda_check(cudaGetLastError(), "mark compacted tiles launch");
      mask_prime_word_edges<<<1U, 1U>>>(prepared.odd_low,
                                        options.segment_odds, device_words);
      cuda_check(cudaGetLastError(), "mask prime word edges launch");
      cuda_check(cudaEventRecord(gpu_stop), "cudaEventRecord stop");
      cuda_check(cudaEventSynchronize(gpu_stop), "cudaEventSynchronize stop");
      float segment_gpu_ms = 0.0F;
      cuda_check(cudaEventElapsedTime(&segment_gpu_ms, gpu_start, gpu_stop),
                 "cudaEventElapsedTime");
      gpu_seconds += static_cast<double>(segment_gpu_ms) / 1000.0;

      std::uint32_t overflow = 0U;
      std::uint32_t compacted_events = 0U;
      cuda_check(cudaMemcpy(&overflow, device_overflow,
                            sizeof(std::uint32_t), cudaMemcpyDeviceToHost),
                 "cudaMemcpy overflow flag");
      cuda_check(cudaMemcpy(&compacted_events,
                            device_tile_offsets + tile_count,
                            sizeof(std::uint32_t), cudaMemcpyDeviceToHost),
                 "cudaMemcpy compacted event count");
      if (overflow != 0U) {
        throw std::runtime_error("tile-event capacity was exceeded");
      }
      total_compacted_events += compacted_events;
      const auto pipeline_stop = std::chrono::steady_clock::now();
      pipeline_seconds +=
          std::chrono::duration<double>(pipeline_stop - pipeline_start).count();

      if (segment_index < options.replay_segments) {
        const auto replay_start = std::chrono::steady_clock::now();
        cuda_check(cudaMemcpy(host_words.data(), device_words,
                              host_words.size() * sizeof(std::uint64_t),
                              cudaMemcpyDeviceToHost),
                   "cudaMemcpy replay words");
        const std::vector<std::uint64_t> expected =
            sparkinterval::tg_goldbach::stateless_odd_prime_words(
                prepared.odd_low, options.segment_odds, base_primes);
        if (host_words != expected) {
          for (std::size_t word = 0U; word < host_words.size(); ++word) {
            if (host_words[word] != expected[word]) {
              throw std::runtime_error(
                  "CPU replay mismatch in segment " +
                  std::to_string(segment_index) + ", word " +
                  std::to_string(word));
            }
          }
          throw std::runtime_error("CPU replay mismatch with unequal sizes");
        }
        for (const std::uint64_t word : host_words) {
          replayed_prime_bits += std::popcount(word);
        }
        update_canonical_digest(replay_hasher, host_words);
        const auto replay_stop = std::chrono::steady_clock::now();
        replay_seconds +=
            std::chrono::duration<double>(replay_stop - replay_start).count();
      }
    }

    const std::uint64_t processed_candidates =
        options.segment_odds * options.segments;
    const double rate = pipeline_seconds == 0.0
        ? 0.0
        : static_cast<double>(processed_candidates) / pipeline_seconds;
    const std::uint64_t state_bytes =
        dense_capacity * (sizeof(std::uint32_t) + sizeof(std::uint64_t)) +
        static_cast<std::uint64_t>(event_capacity) * sizeof(TileEvent) +
        word_count * sizeof(std::uint64_t) +
        static_cast<std::uint64_t>(tile_count) * 3U * sizeof(std::uint32_t);

    const sparkinterval::Sha256Digest replay_digest = replay_hasher.finish();
    std::cout << std::setprecision(17)
              << "{\"algorithm\":\"sparkinterval.goldbach-tile-compacted-sieve.v1\""
              << ",\"source_scale_completed\":false"
              << ",\"receipt_eligible\":false"
              << ",\"shared_clear_mode\":\"atomic-and-64\""
              << ",\"one_global_writer_per_word\":true"
              << ",\"unsynchronized_shared_word_clears\":false"
              << ",\"device_name\":\"" << json_escape(properties.name) << "\""
              << ",\"compute_capability\":\"" << properties.major << "."
              << properties.minor << "\""
              << ",\"odd_low\":" << options.odd_low
              << ",\"segment_odds\":" << options.segment_odds
              << ",\"segments\":" << options.segments
              << ",\"tile_odds\":" << options.tile_odds
              << ",\"tile_count\":" << tile_count
              << ",\"tile_shared_bytes\":" << tile_shared_bytes
              << ",\"replay_segments\":" << options.replay_segments
              << ",\"base_limit\":" << options.base_limit
              << ",\"base_prime_count\":" << base_primes.size()
              << ",\"scheduled_base_prime_count\":"
              << schedule.odd_primes().size()
              << ",\"active_dense_prime_count\":" << active_dense_count
              << ",\"sparse_prime_count\":" << sparse_prime_count
              << ",\"bucket_ring_size\":" << schedule.bucket_ring_size()
              << ",\"activated_prime_count\":"
              << schedule.activated_prime_count()
              << ",\"sparse_composite_events\":" << total_sparse_events
              << ",\"compacted_tile_events\":" << total_compacted_events
              << ",\"dense_tile_event_capacity\":" << dense_event_bound
              << ",\"event_capacity\":" << event_capacity
              << ",\"device_state_bytes_bound\":" << state_bytes
              << ",\"base_generation_seconds\":" << base_seconds
              << ",\"host_schedule_seconds\":" << host_schedule_seconds
              << ",\"gpu_seconds\":" << gpu_seconds
              << ",\"pipeline_seconds\":" << pipeline_seconds
              << ",\"replay_seconds\":" << replay_seconds
              << ",\"processed_odd_candidates\":" << processed_candidates
              << ",\"pipeline_odd_candidates_per_second\":" << rate
              << ",\"replayed_prime_bits\":" << replayed_prime_bits
              << ",\"replay_words_sha256_le\":\""
              << sparkinterval::lowercase_hex(replay_digest)
              << "\"}\n";

    cuda_check(cudaEventDestroy(gpu_start), "cudaEventDestroy start");
    cuda_check(cudaEventDestroy(gpu_stop), "cudaEventDestroy stop");
    if (device_sparse_offsets != nullptr) {
      cuda_check(cudaFree(device_sparse_offsets), "cudaFree sparse offsets");
    }
    cuda_check(cudaFree(device_dense_primes), "cudaFree dense primes");
    cuda_check(cudaFree(device_dense_offsets), "cudaFree dense offsets");
    cuda_check(cudaFree(device_tile_counts), "cudaFree tile counts");
    cuda_check(cudaFree(device_tile_offsets), "cudaFree tile offsets");
    cuda_check(cudaFree(device_tile_cursors), "cudaFree tile cursors");
    cuda_check(cudaFree(device_overflow), "cudaFree overflow flag");
    cuda_check(cudaFree(device_events), "cudaFree tile events");
    cuda_check(cudaFree(device_words), "cudaFree output words");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "h100_tg_goldbach_tile_sieve: " << error.what() << '\n';
    return 1;
  }
}
