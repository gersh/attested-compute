// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Word-oriented Goldbach coverage kernel and deterministic throughput probe.
//
// This executable benchmarks only the coverage stage.  Production q bits must
// come from a separately checked exact segmented prime sieve.  A successful
// synthetic benchmark is not a Goldbach certificate.

#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr unsigned kThreads = 256;

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

std::uint64_t splitmix64(std::uint64_t& state) {
  state += 0x9e3779b97f4a7c15ULL;
  std::uint64_t value = state;
  value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
  value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

__device__ __forceinline__ std::uint64_t extract_shifted_word(
    const std::uint64_t* __restrict__ q_words,
    std::uint64_t first_bit) {
  const std::uint64_t word_index = first_bit >> 6U;
  const unsigned shift = static_cast<unsigned>(first_bit & 63U);
  const std::uint64_t low = q_words[word_index] >> shift;
  if (shift == 0U) return low;
  return low | (q_words[word_index + 1U] << (64U - shift));
}

// One thread owns one 64-even-number output word.  For small prime p, the
// host supplies base_offsets[p] satisfying
//
//   even_low = q_low + p + 2 * base_offsets[p].
//
// Output word w therefore reads the q bitset beginning at
// base_offsets[p] + 64*w.  OR is monotone, and the loop may stop exactly when
// every live bit is one.
__global__ void shifted_or_coverage_kernel(
    const std::uint64_t* __restrict__ q_words,
    const std::uint64_t* __restrict__ base_offsets,
    std::uint64_t offset_count,
    std::uint64_t first_output_word,
    std::uint64_t launch_word_count,
    std::uint64_t total_output_word_count,
    std::uint64_t final_live_mask,
    std::uint64_t* __restrict__ coverage_words,
    unsigned long long* __restrict__ total_rounds,
    unsigned int* __restrict__ maximum_rounds,
    unsigned long long* __restrict__ failed_words) {
  const std::uint64_t local_word =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (local_word >= launch_word_count) return;
  const std::uint64_t word = first_output_word + local_word;

  const std::uint64_t live_mask =
      word + 1U == total_output_word_count
          ? final_live_mask
          : ~static_cast<std::uint64_t>(0);
  std::uint64_t covered = 0;
  unsigned rounds = 0;
  for (std::uint64_t index = 0; index < offset_count; ++index) {
    const std::uint64_t first_bit = base_offsets[index] + 64U * word;
    covered |= extract_shifted_word(q_words, first_bit);
    ++rounds;
    if ((covered & live_mask) == live_mask) break;
  }
  coverage_words[local_word] = covered;
  atomicAdd(total_rounds, static_cast<unsigned long long>(rounds));
  atomicMax(maximum_rounds, rounds);
  if ((covered & live_mask) != live_mask) {
    atomicAdd(failed_words, 1ULL);
  }
}

std::uint64_t extract_shifted_word_host(
    const std::vector<std::uint64_t>& words,
    std::uint64_t first_bit) {
  const std::uint64_t word_index = first_bit >> 6U;
  const unsigned shift = static_cast<unsigned>(first_bit & 63U);
  const std::uint64_t low = words.at(word_index) >> shift;
  if (shift == 0U) return low;
  return low | (words.at(word_index + 1U) << (64U - shift));
}

struct Options {
  std::uint64_t output_words = 1U << 20U;
  std::uint64_t offsets = 2048;
  std::uint64_t density_denominator = 43;
  std::uint64_t repetitions = 5;
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
    if (const char* value = value_after("--output-words=")) {
      options.output_words = parse_u64(value, "output words");
    } else if (const char* value = value_after("--offsets=")) {
      options.offsets = parse_u64(value, "offset count");
    } else if (const char* value = value_after("--density-denominator=")) {
      options.density_denominator = parse_u64(value, "density denominator");
    } else if (const char* value = value_after("--repetitions=")) {
      options.repetitions = parse_u64(value, "repetitions");
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  if (options.output_words == 0 || options.offsets == 0 ||
      options.density_denominator < 2 || options.repetitions == 0) {
    throw std::runtime_error("benchmark dimensions must be positive");
  }
  if (options.output_words > (1ULL << 32U) ||
      options.offsets > (1ULL << 24U)) {
    throw std::runtime_error("benchmark dimensions exceed the reviewed probe limit");
  }
  return options;
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

    std::vector<std::uint64_t> offsets(options.offsets);
    std::uint64_t maximum_offset = 0;
    for (std::uint64_t index = 0; index < options.offsets; ++index) {
      // Deterministic, distinct, deliberately unaligned shifts exercise both
      // q-word loads.  They are synthetic and carry no primality meaning.
      offsets[index] = 131U * index + (index % 61U);
      maximum_offset = std::max(maximum_offset, offsets[index]);
    }
    const std::uint64_t q_bit_count =
        maximum_offset + 64U * options.output_words + 64U;
    const std::uint64_t q_word_count = (q_bit_count + 63U) / 64U;
    std::vector<std::uint64_t> q_words(q_word_count, 0);
    std::uint64_t random_state = 0x9f4a7c15d1b54a32ULL;
    for (std::uint64_t word = 0; word < q_word_count; ++word) {
      std::uint64_t value = 0;
      for (unsigned bit = 0; bit < 64U; ++bit) {
        if (splitmix64(random_state) % options.density_denominator == 0) {
          value |= 1ULL << bit;
        }
      }
      q_words[word] = value;
    }

    std::uint64_t* device_q_words = nullptr;
    std::uint64_t* device_offsets = nullptr;
    std::uint64_t* device_coverage = nullptr;
    unsigned long long* device_total_rounds = nullptr;
    unsigned int* device_maximum_rounds = nullptr;
    unsigned long long* device_failed_words = nullptr;
    cuda_check(cudaMalloc(&device_q_words, q_words.size() * sizeof(std::uint64_t)),
               "cudaMalloc q words");
    cuda_check(cudaMalloc(&device_offsets, offsets.size() * sizeof(std::uint64_t)),
               "cudaMalloc offsets");
    cuda_check(cudaMalloc(&device_coverage,
                          options.output_words * sizeof(std::uint64_t)),
               "cudaMalloc coverage");
    cuda_check(cudaMalloc(&device_total_rounds, sizeof(unsigned long long)),
               "cudaMalloc total rounds");
    cuda_check(cudaMalloc(&device_maximum_rounds, sizeof(unsigned int)),
               "cudaMalloc maximum rounds");
    cuda_check(cudaMalloc(&device_failed_words, sizeof(unsigned long long)),
               "cudaMalloc failed words");
    cuda_check(cudaMemcpy(device_q_words, q_words.data(),
                          q_words.size() * sizeof(std::uint64_t),
                          cudaMemcpyHostToDevice),
               "cudaMemcpy q words");
    cuda_check(cudaMemcpy(device_offsets, offsets.data(),
                          offsets.size() * sizeof(std::uint64_t),
                          cudaMemcpyHostToDevice),
               "cudaMemcpy offsets");

    cudaEvent_t start{};
    cudaEvent_t stop{};
    cuda_check(cudaEventCreate(&start), "cudaEventCreate start");
    cuda_check(cudaEventCreate(&stop), "cudaEventCreate stop");
    float total_milliseconds = 0.0F;
    unsigned long long total_rounds = 0;
    unsigned int maximum_rounds = 0;
    unsigned long long failed_words = 0;
    const unsigned blocks = static_cast<unsigned>(
        (options.output_words + kThreads - 1U) / kThreads);
    for (std::uint64_t repetition = 0; repetition < options.repetitions;
         ++repetition) {
      cuda_check(cudaMemset(device_total_rounds, 0, sizeof(unsigned long long)),
                 "cudaMemset total rounds");
      cuda_check(cudaMemset(device_maximum_rounds, 0, sizeof(unsigned int)),
                 "cudaMemset maximum rounds");
      cuda_check(cudaMemset(device_failed_words, 0, sizeof(unsigned long long)),
                 "cudaMemset failed words");
      cuda_check(cudaEventRecord(start), "cudaEventRecord start");
      shifted_or_coverage_kernel<<<blocks, kThreads>>>(
          device_q_words, device_offsets, options.offsets,
          0, options.output_words, options.output_words,
          std::numeric_limits<std::uint64_t>::max(),
          device_coverage, device_total_rounds, device_maximum_rounds,
          device_failed_words);
      cuda_check(cudaGetLastError(), "shifted_or_coverage_kernel launch");
      cuda_check(cudaEventRecord(stop), "cudaEventRecord stop");
      cuda_check(cudaEventSynchronize(stop), "cudaEventSynchronize stop");
      float milliseconds = 0.0F;
      cuda_check(cudaEventElapsedTime(&milliseconds, start, stop),
                 "cudaEventElapsedTime");
      total_milliseconds += milliseconds;
    }
    cuda_check(cudaMemcpy(&total_rounds, device_total_rounds,
                          sizeof(unsigned long long), cudaMemcpyDeviceToHost),
               "cudaMemcpy total rounds");
    cuda_check(cudaMemcpy(&maximum_rounds, device_maximum_rounds,
                          sizeof(unsigned int), cudaMemcpyDeviceToHost),
               "cudaMemcpy maximum rounds");
    cuda_check(cudaMemcpy(&failed_words, device_failed_words,
                          sizeof(unsigned long long), cudaMemcpyDeviceToHost),
               "cudaMemcpy failed words");

    // Exact CPU replay of a fixed sample catches indexing, carry-word, and
    // early-exit mistakes without pretending to replay the benchmark range.
    const std::uint64_t replay_words = std::min<std::uint64_t>(4096,
                                                               options.output_words);
    std::vector<std::uint64_t> gpu_sample(replay_words);
    cuda_check(cudaMemcpy(gpu_sample.data(), device_coverage,
                          replay_words * sizeof(std::uint64_t),
                          cudaMemcpyDeviceToHost),
               "cudaMemcpy replay sample");
    for (std::uint64_t word = 0; word < replay_words; ++word) {
      std::uint64_t expected = 0;
      for (const std::uint64_t offset : offsets) {
        expected |= extract_shifted_word_host(q_words, offset + 64U * word);
        if (expected == std::numeric_limits<std::uint64_t>::max()) break;
      }
      if (gpu_sample[word] != expected) {
        throw std::runtime_error("GPU shifted-word result differs from exact CPU replay");
      }
    }

    const double mean_milliseconds =
        static_cast<double>(total_milliseconds) / options.repetitions;
    const long double even_count =
        static_cast<long double>(options.output_words) * 64.0L;
    const long double evens_per_second =
        even_count / (static_cast<long double>(mean_milliseconds) / 1000.0L);
    const long double average_rounds =
        static_cast<long double>(total_rounds) / options.output_words;
    const long double eight_gpu_hours_for_4e18 =
        2.0e18L / (8.0L * evens_per_second) / 3600.0L;

    std::cout << std::setprecision(17)
              << "{\"algorithm\":\"sparkinterval.goldbach-shifted-bitset-coverage.v1\"," 
              << "\"device\":\"" << properties.name << "\"," 
              << "\"synthetic_only\":true,"
              << "\"output_words\":" << options.output_words << ','
              << "\"even_count\":" << static_cast<unsigned long long>(even_count) << ','
              << "\"offset_count\":" << options.offsets << ','
              << "\"density_denominator\":" << options.density_denominator << ','
              << "\"mean_kernel_ms\":" << mean_milliseconds << ','
              << "\"evens_per_second\":" << static_cast<double>(evens_per_second) << ','
              << "\"average_shift_rounds\":" << static_cast<double>(average_rounds) << ','
              << "\"maximum_shift_rounds\":" << maximum_rounds << ','
              << "\"failed_words\":" << failed_words << ','
              << "\"cpu_replay_words\":" << replay_words << ','
              << "\"eight_equal_gpu_hours_for_4e18_coverage_only\":"
              << static_cast<double>(eight_gpu_hours_for_4e18)
              << "}\n";

    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    cudaFree(device_q_words);
    cudaFree(device_offsets);
    cudaFree(device_coverage);
    cudaFree(device_total_rounds);
    cudaFree(device_maximum_rounds);
    cudaFree(device_failed_words);
    return failed_words == 0 ? 0 : 2;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
