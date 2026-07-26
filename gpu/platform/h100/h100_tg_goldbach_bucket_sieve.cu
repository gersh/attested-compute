// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Persistent hybrid odd-prime sieve for the word-oriented Goldbach route.
//
// This is a bounded production-shape component, not a source-scale Goldbach
// certificate.  Small primes retain their next offset on the GPU.  Larger
// primes reside in a host circular bucket only until their next actual odd
// multiple.  The resulting packed words can remain on device and feed
// h100_tg_goldbach_shift_or.cu without changing representation.

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

constexpr unsigned kThreads = 256;
constexpr std::uint32_t kWheelModulus = 3U * 5U * 7U * 11U * 13U;
constexpr std::uint32_t kWheelInverseTwo = (kWheelModulus + 1U) / 2U;

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
  std::uint64_t segments = 8;
  std::uint64_t replay_segments = 2;
  std::uint64_t base_limit = 0;
  std::uint64_t base_prime_segment_odds = 1ULL << 20U;
  bool atomic_words = false;
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
    } else if (const char* value = value_after("--replay-segments=")) {
      options.replay_segments = parse_u64(value, "replay segment count");
    } else if (const char* value = value_after("--base-limit=")) {
      options.base_limit = parse_u64(value, "base-prime limit");
    } else if (const char* value = value_after("--base-prime-segment-odds=")) {
      options.base_prime_segment_odds =
          parse_u64(value, "base-prime segment odd count");
    } else if (argument == "--atomic-words") {
      options.atomic_words = true;
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  if ((options.odd_low & 1U) == 0U || options.segment_odds == 0 ||
      options.segment_odds > (1ULL << 31U) || options.segments == 0 ||
      options.replay_segments > options.segments ||
      options.base_prime_segment_odds == 0 ||
      options.base_prime_segment_odds > (1ULL << 31U)) {
    throw std::runtime_error("requested sieve dimensions are outside review bounds");
  }
  const std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max();
  if (options.segments > maximum / 2U ||
      options.segment_odds > maximum / (2U * options.segments) ||
      2U * options.segment_odds * options.segments > maximum - options.odd_low) {
    throw std::runtime_error("requested sieve campaign endpoint overflows uint64");
  }
  const std::uint64_t exclusive_high =
      options.odd_low + 2U * options.segment_odds * options.segments;
  const std::uint64_t required_limit =
      sparkinterval::tg_goldbach::floor_sqrt(exclusive_high - 1U);
  if (options.base_limit == 0) options.base_limit = required_limit;
  if (options.base_limit < required_limit ||
      options.base_limit > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error(
        "base limit must cover floor(sqrt(last odd candidate)) and fit uint32");
  }
  return options;
}

__global__ void mark_dense_primes(
    const std::uint32_t* __restrict__ primes,
    std::uint64_t* __restrict__ next_offsets,
    std::uint64_t prime_count,
    std::uint64_t odd_count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  std::uint64_t offset = next_offsets[index];
  while (offset < odd_count) {
    atomicAnd(words + offset / 64U,
              ~(1ULL << static_cast<unsigned>(offset & 63U)));
    offset += prime;
  }
  next_offsets[index] = offset - odd_count;
}

__global__ void mark_sparse_offsets(
    const std::uint32_t* __restrict__ offsets,
    std::uint64_t offset_count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= offset_count) return;
  const std::uint64_t offset = offsets[index];
  atomicAnd(words + offset / 64U,
            ~(1ULL << static_cast<unsigned>(offset & 63U)));
}

// Every intended colliding store writes the identical byte zero, and the
// reviewed CUDA 13 build lowers this operation to st.global.u8.  This is a
// performance candidate, not a concurrency proof: the packed atomic path is
// the conservative race-free implementation and both are replayed exactly.
__global__ void mark_dense_prime_bytes(
    const std::uint32_t* __restrict__ primes,
    std::uint64_t* __restrict__ next_offsets,
    std::uint64_t prime_count,
    std::uint64_t odd_count,
    unsigned char* __restrict__ candidate_bytes) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  std::uint64_t offset = next_offsets[index];
  while (offset < odd_count) {
    candidate_bytes[offset] = 0U;
    offset += prime;
  }
  next_offsets[index] = offset - odd_count;
}

__global__ void mark_sparse_prime_bytes(
    const std::uint32_t* __restrict__ offsets,
    std::uint64_t offset_count,
    unsigned char* __restrict__ candidate_bytes) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < offset_count) candidate_bytes[offsets[index]] = 0U;
}

__global__ void initialize_wheel_candidate_bytes(
    std::uint64_t odd_low,
    std::uint64_t odd_count,
    const unsigned char* __restrict__ wheel_pattern,
    unsigned char* __restrict__ candidate_bytes) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= odd_count) return;
  const std::uint64_t phase =
      ((odd_low % kWheelModulus) * kWheelInverseTwo) % kWheelModulus;
  candidate_bytes[index] =
      wheel_pattern[(phase + index) % kWheelModulus];
}

__global__ void restore_wheel_primes(std::uint64_t odd_low,
                                     std::uint64_t odd_count,
                                     unsigned char* candidate_bytes) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  constexpr std::uint32_t primes[] = {3U, 5U, 7U, 11U, 13U};
  const std::uint64_t high = odd_low + 2U * odd_count;
  for (const std::uint32_t prime : primes) {
    if (odd_low <= prime && prime < high) {
      candidate_bytes[(prime - odd_low) / 2U] = 1U;
    }
  }
}

// One warp owns one 64-bit output word.  Two ballots pack 64 consecutive
// candidate bytes with coalesced reads and one race-free lane-zero store.
__global__ void pack_candidate_bytes(
    const unsigned char* __restrict__ candidate_bytes,
    std::uint64_t odd_count,
    unsigned long long* __restrict__ words) {
  const unsigned lane = threadIdx.x & 31U;
  const std::uint64_t global_thread =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  const std::uint64_t word = global_thread >> 5U;
  const std::uint64_t word_count = (odd_count + 63U) / 64U;
  if (word >= word_count) return;
  const std::uint64_t low_index = 64U * word + lane;
  const std::uint64_t high_index = low_index + 32U;
  const unsigned low = __ballot_sync(
      0xffffffffU,
      low_index < odd_count && candidate_bytes[low_index] != 0U);
  const unsigned high = __ballot_sync(
      0xffffffffU,
      high_index < odd_count && candidate_bytes[high_index] != 0U);
  if (lane == 0U) {
    words[word] = static_cast<unsigned long long>(low) |
                  (static_cast<unsigned long long>(high) << 32U);
  }
}

__global__ void mask_odd_prime_tail(std::uint64_t odd_low,
                                    std::uint64_t odd_count,
                                    unsigned long long* words) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  if (odd_low == 1U) words[0] &= ~1ULL;
  const unsigned tail = static_cast<unsigned>(odd_count & 63U);
  if (tail != 0U) words[(odd_count - 1U) / 64U] &= (1ULL << tail) - 1U;
}

void update_canonical_digest(sparkinterval::detail::Sha256& hasher,
                             const std::vector<std::uint64_t>& words) {
  unsigned char encoded[8];
  for (const std::uint64_t word : words) {
    for (unsigned byte = 0; byte < 8U; ++byte) {
      encoded[byte] = static_cast<unsigned char>(word >> (8U * byte));
    }
    hasher.update(encoded, sizeof(encoded));
  }
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

    const auto base_start = std::chrono::steady_clock::now();
    std::vector<std::uint32_t> base_primes =
        sparkinterval::tg_goldbach::segmented_odd_primes(
            static_cast<std::uint32_t>(options.base_limit),
            options.base_prime_segment_odds);
    const auto base_stop = std::chrono::steady_clock::now();
    const double base_seconds =
        std::chrono::duration<double>(base_stop - base_start).count();
    const std::size_t base_prime_count = base_primes.size();

    std::vector<std::uint32_t> scheduled_primes;
    scheduled_primes.reserve(base_primes.size());
    for (const std::uint32_t prime : base_primes) {
      const bool wheel_prime =
          prime == 3U || prime == 5U || prime == 7U || prime == 11U ||
          prime == 13U;
      if (options.atomic_words || !wheel_prime) scheduled_primes.push_back(prime);
    }
    const std::size_t dense_capacity = static_cast<std::size_t>(
        std::upper_bound(scheduled_primes.begin(), scheduled_primes.end(),
                         static_cast<std::uint32_t>(std::min<std::uint64_t>(
                             options.segment_odds,
                             std::numeric_limits<std::uint32_t>::max()))) -
        scheduled_primes.begin());
    const std::size_t scheduled_base_prime_count = scheduled_primes.size();
    sparkinterval::tg_goldbach::PersistentOddPrimeSchedule schedule(
        options.odd_low, options.segment_odds, options.segments,
        std::move(scheduled_primes), !options.atomic_words);

    std::uint32_t* device_dense_primes = nullptr;
    std::uint64_t* device_dense_offsets = nullptr;
    if (dense_capacity != 0) {
      cuda_check(cudaMalloc(&device_dense_primes,
                            dense_capacity * sizeof(std::uint32_t)),
                 "cudaMalloc dense primes");
      cuda_check(cudaMalloc(&device_dense_offsets,
                            dense_capacity * sizeof(std::uint64_t)),
                 "cudaMalloc dense offsets");
    }
    const std::uint64_t word_count = (options.segment_odds + 63U) / 64U;
    unsigned long long* device_words = nullptr;
    unsigned char* device_candidate_bytes = nullptr;
    unsigned char* device_wheel_pattern = nullptr;
    std::uint32_t* device_sparse_offsets = nullptr;
    std::size_t sparse_capacity = 0;
    cuda_check(cudaMalloc(&device_words, word_count * sizeof(unsigned long long)),
               "cudaMalloc prime words");
    if (!options.atomic_words) {
      cuda_check(cudaMalloc(&device_candidate_bytes, options.segment_odds),
                 "cudaMalloc prime candidate bytes");
      std::vector<unsigned char> wheel_pattern(kWheelModulus, 1U);
      for (std::uint32_t index = 0; index < kWheelModulus; ++index) {
        if (index % 3U == 0U || index % 5U == 0U || index % 7U == 0U ||
            index % 11U == 0U || index % 13U == 0U) {
          wheel_pattern[index] = 0U;
        }
      }
      cuda_check(cudaMalloc(&device_wheel_pattern, wheel_pattern.size()),
                 "cudaMalloc wheel pattern");
      cuda_check(cudaMemcpy(device_wheel_pattern, wheel_pattern.data(),
                            wheel_pattern.size(), cudaMemcpyHostToDevice),
                 "cudaMemcpy wheel pattern");
    }

    cudaEvent_t gpu_start{};
    cudaEvent_t gpu_stop{};
    cuda_check(cudaEventCreate(&gpu_start), "cudaEventCreate start");
    cuda_check(cudaEventCreate(&gpu_stop), "cudaEventCreate stop");

    std::size_t active_dense_count = 0;
    std::uint64_t total_sparse_events = 0;
    double total_schedule_seconds = 0.0;
    double total_pipeline_seconds = 0.0;
    double total_gpu_milliseconds = 0.0;
    std::uint64_t replayed_prime_bits = 0;
    sparkinterval::detail::Sha256 replay_hasher;

    for (std::uint64_t segment = 0; segment < options.segments; ++segment) {
      const auto pipeline_start = std::chrono::steady_clock::now();
      const auto schedule_start = std::chrono::steady_clock::now();
      const sparkinterval::tg_goldbach::PreparedOddSegment prepared =
          schedule.prepare_next();
      const auto schedule_stop = std::chrono::steady_clock::now();
      total_schedule_seconds +=
          std::chrono::duration<double>(schedule_stop - schedule_start).count();

      if (active_dense_count + prepared.newly_active_dense.size() >
          dense_capacity) {
        throw std::logic_error("active dense-prime state exceeded allocation");
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
                   "cudaMemcpy newly active dense primes");
        cuda_check(cudaMemcpy(device_dense_offsets + active_dense_count,
                              new_offsets.data(),
                              new_offsets.size() * sizeof(std::uint64_t),
                              cudaMemcpyHostToDevice),
                   "cudaMemcpy newly active dense offsets");
        active_dense_count += new_primes.size();
      }

      const std::size_t sparse_count =
          prepared.sparse_composite_offsets.size();
      total_sparse_events += sparse_count;
      if (sparse_count > sparse_capacity) {
        if (device_sparse_offsets != nullptr) cudaFree(device_sparse_offsets);
        sparse_capacity = std::max<std::size_t>(sparse_count, 1024U);
        cuda_check(cudaMalloc(&device_sparse_offsets,
                              sparse_capacity * sizeof(std::uint32_t)),
                   "cudaMalloc sparse offsets");
      }
      if (sparse_count != 0) {
        cuda_check(cudaMemcpy(device_sparse_offsets,
                              prepared.sparse_composite_offsets.data(),
                              sparse_count * sizeof(std::uint32_t),
                              cudaMemcpyHostToDevice),
                   "cudaMemcpy sparse offsets");
      }

      cuda_check(cudaEventRecord(gpu_start), "cudaEventRecord start");
      if (options.atomic_words) {
        cuda_check(cudaMemset(device_words, 0xff,
                              word_count * sizeof(unsigned long long)),
                   "cudaMemset prime words");
      } else {
        const unsigned blocks = static_cast<unsigned>(
            (options.segment_odds + kThreads - 1U) / kThreads);
        initialize_wheel_candidate_bytes<<<blocks, kThreads>>>(
            prepared.odd_low, options.segment_odds, device_wheel_pattern,
            device_candidate_bytes);
        cuda_check(cudaGetLastError(),
                   "initialize_wheel_candidate_bytes launch");
        restore_wheel_primes<<<1, 1>>>(prepared.odd_low, options.segment_odds,
                                       device_candidate_bytes);
        cuda_check(cudaGetLastError(), "restore_wheel_primes launch");
      }
      if (active_dense_count != 0) {
        const unsigned blocks = static_cast<unsigned>(
            (active_dense_count + kThreads - 1U) / kThreads);
        if (options.atomic_words) {
          mark_dense_primes<<<blocks, kThreads>>>(
              device_dense_primes, device_dense_offsets, active_dense_count,
              options.segment_odds, device_words);
          cuda_check(cudaGetLastError(), "mark_dense_primes launch");
        } else {
          mark_dense_prime_bytes<<<blocks, kThreads>>>(
              device_dense_primes, device_dense_offsets, active_dense_count,
              options.segment_odds, device_candidate_bytes);
          cuda_check(cudaGetLastError(), "mark_dense_prime_bytes launch");
        }
      }
      if (sparse_count != 0) {
        const unsigned blocks =
            static_cast<unsigned>((sparse_count + kThreads - 1U) / kThreads);
        if (options.atomic_words) {
          mark_sparse_offsets<<<blocks, kThreads>>>(
              device_sparse_offsets, sparse_count, device_words);
          cuda_check(cudaGetLastError(), "mark_sparse_offsets launch");
        } else {
          mark_sparse_prime_bytes<<<blocks, kThreads>>>(
              device_sparse_offsets, sparse_count, device_candidate_bytes);
          cuda_check(cudaGetLastError(), "mark_sparse_prime_bytes launch");
        }
      }
      if (!options.atomic_words) {
        const std::uint64_t pack_threads = word_count * 32U;
        const unsigned blocks =
            static_cast<unsigned>((pack_threads + kThreads - 1U) / kThreads);
        pack_candidate_bytes<<<blocks, kThreads>>>(
            device_candidate_bytes, options.segment_odds, device_words);
        cuda_check(cudaGetLastError(), "pack_candidate_bytes launch");
      }
      mask_odd_prime_tail<<<1, 1>>>(prepared.odd_low, options.segment_odds,
                                    device_words);
      cuda_check(cudaGetLastError(), "mask_odd_prime_tail launch");
      cuda_check(cudaEventRecord(gpu_stop), "cudaEventRecord stop");
      cuda_check(cudaEventSynchronize(gpu_stop), "cudaEventSynchronize stop");
      float gpu_milliseconds = 0.0F;
      cuda_check(cudaEventElapsedTime(&gpu_milliseconds, gpu_start, gpu_stop),
                 "cudaEventElapsedTime");
      total_gpu_milliseconds += gpu_milliseconds;
      const auto pipeline_stop = std::chrono::steady_clock::now();
      total_pipeline_seconds +=
          std::chrono::duration<double>(pipeline_stop - pipeline_start).count();

      if (segment < options.replay_segments) {
        std::vector<std::uint64_t> gpu_words(static_cast<std::size_t>(word_count));
        cuda_check(cudaMemcpy(gpu_words.data(), device_words,
                              word_count * sizeof(std::uint64_t),
                              cudaMemcpyDeviceToHost),
                   "cudaMemcpy replay words");
        const std::vector<std::uint64_t> expected =
            sparkinterval::tg_goldbach::stateless_odd_prime_words(
                prepared.odd_low, options.segment_odds, schedule.odd_primes(),
                !options.atomic_words);
        if (gpu_words != expected) {
          const auto mismatch = std::mismatch(gpu_words.begin(), gpu_words.end(),
                                              expected.begin());
          throw std::runtime_error(
              "GPU persistent sieve differs from stateless CPU replay at word " +
              std::to_string(mismatch.first - gpu_words.begin()));
        }
        update_canonical_digest(replay_hasher, gpu_words);
        for (const std::uint64_t word : gpu_words) {
          replayed_prime_bits += std::popcount(word);
        }
      }
    }

    const sparkinterval::Sha256Digest replay_digest = replay_hasher.finish();
    const long double total_candidates =
        static_cast<long double>(options.segment_odds) * options.segments;
    const long double candidates_per_second =
        total_candidates / total_pipeline_seconds;
    const long double base_state_bytes =
        static_cast<long double>(scheduled_base_prime_count) *
        sizeof(std::uint32_t);
    const long double dense_state_bytes =
        static_cast<long double>(dense_capacity) *
        (sizeof(std::uint32_t) + sizeof(std::uint64_t));
    const long double sparse_state_bytes =
        static_cast<long double>(scheduled_base_prime_count - dense_capacity) *
        12U;

    std::cout << std::setprecision(17)
              << "{\"algorithm\":\"sparkinterval.goldbach-persistent-bucket-sieve.v1\","
              << "\"device\":\"" << json_escape(properties.name) << "\","
              << "\"source_scale_completed\":false,"
              << "\"receipt_eligible\":false,"
              << "\"marking_mode\":\""
              << (options.atomic_words ? "packed-atomic-and"
                                       : "idempotent-byte-store")
              << "\","
              << "\"same_value_write_collisions\":"
              << (options.atomic_words ? "false" : "true") << ','
              << "\"odd_low\":" << options.odd_low << ','
              << "\"segment_odds\":" << options.segment_odds << ','
              << "\"segments\":" << options.segments << ','
              << "\"replay_segments\":" << options.replay_segments << ','
              << "\"base_limit\":" << options.base_limit << ','
              << "\"base_prime_count\":" << base_prime_count << ','
              << "\"scheduled_base_prime_count\":"
              << scheduled_base_prime_count
              << ','
              << "\"active_dense_prime_count\":" << active_dense_count << ','
              << "\"bucket_ring_size\":" << schedule.bucket_ring_size() << ','
              << "\"activated_prime_count\":" << schedule.activated_prime_count()
              << ','
              << "\"dense_composite_marks\":null,"
              << "\"sparse_composite_events\":" << total_sparse_events << ','
              << "\"base_prime_generation_seconds\":" << base_seconds << ','
              << "\"host_schedule_seconds\":" << total_schedule_seconds << ','
              << "\"gpu_stage_milliseconds\":" << total_gpu_milliseconds << ','
              << "\"pipeline_seconds\":" << total_pipeline_seconds << ','
              << "\"odd_candidates_per_second\":"
              << static_cast<double>(candidates_per_second) << ','
              << "\"persistent_state_bytes_upper_bound\":"
              << static_cast<unsigned long long>(
                     base_state_bytes + dense_state_bytes + sparse_state_bytes)
              << ','
              << "\"device_word_bytes\":"
              << word_count * sizeof(std::uint64_t) << ','
              << "\"device_candidate_byte_bytes\":"
              << (options.atomic_words ? 0U : options.segment_odds) << ','
              << "\"dense_offset_state_replayed\":false,"
              << "\"replayed_prime_bits\":" << replayed_prime_bits << ','
              << "\"replay_words_sha256_le\":\""
              << sparkinterval::lowercase_hex(replay_digest) << "\"}\n";

    cudaEventDestroy(gpu_start);
    cudaEventDestroy(gpu_stop);
    cudaFree(device_dense_primes);
    cudaFree(device_dense_offsets);
    cudaFree(device_sparse_offsets);
    cudaFree(device_words);
    cudaFree(device_candidate_bytes);
    cudaFree(device_wheel_pattern);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
