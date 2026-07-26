// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only comparison for a compact Goldbach tail-prime roster.
// The included source supplies the independently checked CPU model and the
// current uint64_t-roster kernel.  No production source includes this file.

#ifndef SPARKINTERVAL_ENABLE_GOLDBACH_TAIL_U32_PRIME_QUALIFICATION
#error "the Goldbach uint32 tail-prime roster is qualification-only"
#endif

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

#define SPARKINTERVAL_ENABLE_GOLDBACH_WHEEL_GAP_QUALIFICATION 1
#define main sparkinterval_embedded_wheel_gap_qualification_main
#include "../gpu/platform/h100/h100_tg_goldbach_wheel_gap_tail_qualification.cu"
#undef main

namespace {

constexpr std::uint64_t kQualifiedPrimeLimit = 176'776'695ULL;
constexpr unsigned kQualificationRounds = 9U;
constexpr const char* kBuildProfile =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif

void require_qualified_device() {
  int device_count = 0;
  cuda_check(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount");
  if (device_count < 1) {
    throw std::runtime_error("no CUDA device");
  }
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  cuda_check(cudaGetDeviceProperties(&properties, 0),
             "cudaGetDeviceProperties");
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error(
        "strict uint32 tail-prime qualification requires NVIDIA H100 sm_90");
  }
#endif
}

std::string canonical_u32_sha256(
    const std::vector<std::uint32_t>& values) {
  sparkinterval::detail::Sha256 hasher;
  for (const std::uint32_t value : values) {
    unsigned char bytes[4];
    for (unsigned index = 0; index < 4U; ++index) {
      bytes[index] =
          static_cast<unsigned char>(value >> (8U * index));
    }
    hasher.update(bytes, sizeof(bytes));
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

template <bool Instrument>
__global__ void compact_u32_wheel47_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint32_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words,
    Counts* __restrict__ counts) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime =
      static_cast<std::uint64_t>(primes[index]);
  if (prime < 3U || prime > q_high / prime) return;

  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t composite = quotient * prime;
  if ((composite & 1U) == 0U) {
    if (composite > q_high - prime) return;
    composite += prime;
    ++quotient;
  }

  const std::uint64_t square = prime * prime;
  if (composite < square) {
    composite = square;
    quotient = prime;
  }
  if (composite > q_high) return;

  const std::uint64_t step = 2U * prime;
  std::uint64_t cofactor = quotient;
  for (;;) {
    if constexpr (Instrument) {
      atomicAdd(&counts->raw_visit_count, 1ULL);
    }
    if (device_survives_small_wheel(cofactor)) {
      if constexpr (Instrument) {
        atomicAdd(&counts->small_wheel_survivor_count, 1ULL);
      }
      if (survives_large_wheel(cofactor)) {
        const std::uint64_t bit = (composite - q_low) / 2U;
        atomicAnd(words + bit / 64U,
                  ~(1ULL << static_cast<unsigned>(bit & 63U)));
        if constexpr (Instrument) {
          atomicAdd(&counts->final_event_count, 1ULL);
        }
      }
    }
    if (step > q_high - composite) break;
    composite += step;
    cofactor += 2U;
  }
}

double time_compact(
    const PreparedWindow& window,
    const std::uint32_t* device_primes,
    std::uint64_t prime_count,
    unsigned long long* device_words) {
  const std::size_t bytes =
      window.initial.size() * sizeof(std::uint64_t);
  cuda_check(cudaMemcpy(device_words, window.initial.data(), bytes,
                        cudaMemcpyHostToDevice),
             "reset compact words");
  const unsigned blocks = static_cast<unsigned>(
      (prime_count + kThreads - 1U) / kThreads);
  return timed_launch([&]() {
    compact_u32_wheel47_tail_kernel<false><<<blocks, kThreads>>>(
        window.geometry.q_low, window.geometry.q_high,
        device_primes, prime_count, device_words, nullptr);
    cuda_check(cudaGetLastError(), "launch compact tail");
  });
}

void check_compact(
    const PreparedWindow& window,
    const std::uint32_t* device_primes,
    std::uint64_t prime_count,
    unsigned long long* device_words,
    Counts* device_counts) {
  const std::size_t bytes =
      window.initial.size() * sizeof(std::uint64_t);
  cuda_check(cudaMemcpy(device_words, window.initial.data(), bytes,
                        cudaMemcpyHostToDevice),
             "reset compact checked words");
  cuda_check(cudaMemset(device_counts, 0, sizeof(Counts)),
             "clear compact checked counts");
  const unsigned blocks = static_cast<unsigned>(
      (prime_count + kThreads - 1U) / kThreads);
  compact_u32_wheel47_tail_kernel<true><<<blocks, kThreads>>>(
      window.geometry.q_low, window.geometry.q_high,
      device_primes, prime_count, device_words, device_counts);
  cuda_check(cudaGetLastError(), "launch compact checked tail");
  cuda_check(cudaDeviceSynchronize(), "synchronize compact checked tail");

  std::vector<std::uint64_t> actual(window.initial.size());
  Counts actual_counts{};
  cuda_check(cudaMemcpy(actual.data(), device_words, bytes,
                        cudaMemcpyDeviceToHost),
             "copy compact checked words");
  cuda_check(cudaMemcpy(&actual_counts, device_counts, sizeof(Counts),
                        cudaMemcpyDeviceToHost),
             "copy compact checked counts");
  compare_words(window.expected, actual, "compact CUDA/CPU output");
  if (!same_counts(window.counts, copy_counts(actual_counts))) {
    throw std::runtime_error("compact CUDA/CPU event counts differ");
  }
}

CaseResult check_current_and_compact(
    const std::string& name,
    const Geometry& geometry,
    const std::vector<std::uint64_t>& prefix_primes,
    const std::vector<std::uint64_t>& tail_primes,
    const std::vector<std::uint32_t>& compact_primes,
    const std::array<unsigned char, kWheelOddEntries>& table,
    std::uint64_t* device_u64_primes,
    std::uint32_t* device_u32_primes,
    unsigned long long* device_words,
    Counts* device_counts) {
  if (tail_primes.size() != compact_primes.size()) {
    throw std::runtime_error("host roster counts differ");
  }
  const PreparedWindow window =
      prepare_window(geometry, prefix_primes, tail_primes, table);
  const HostCounts current = run_instrumented(
      current_wheel47_tail_kernel<true>, window, device_u64_primes,
      tail_primes.size(), device_words, nullptr, device_counts, true);
  if (!same_counts(window.counts, current)) {
    throw std::runtime_error("current CUDA/CPU event counts differ");
  }
  check_compact(window, device_u32_primes, compact_primes.size(),
                device_words, device_counts);
  return {
      name,
      geometry.q_low,
      geometry.q_high,
      (geometry.q_high - geometry.q_low) / 2U + 1U,
      window.counts,
      set_bit_count(window.expected),
      canonical_word_sha256(window.expected),
  };
}

void print_compact_case(const CaseResult& result) {
  print_case(result);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    bool bounded_only = false;
    if (argc == 2 && std::string_view(argv[1]) == "--bounded-only") {
      bounded_only = true;
    } else if (argc != 1) {
      throw std::runtime_error("usage: qualifier [--bounded-only]");
    }
    require_qualified_device();
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0),
               "cudaGetDeviceProperties");

    const std::vector<Geometry> geometries =
        benchmark_geometries("source-segment");
    const Geometry geometry = geometries.front();
    const std::uint64_t prime_limit = integer_sqrt(geometry.q_high);
    if (prime_limit != kQualifiedPrimeLimit ||
        prime_limit > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("qualified prime limit differs");
    }
    const std::vector<std::uint64_t> prefix_primes =
        odd_primes_through(kWordOwnerCutoff, 1U);
    const std::vector<std::uint64_t> tail_primes =
        odd_primes_through(prime_limit, kWarpParallelCutoff);
    std::vector<std::uint32_t> compact_primes;
    compact_primes.reserve(tail_primes.size());
    for (const std::uint64_t prime : tail_primes) {
      if (prime > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("tail prime does not fit uint32");
      }
      compact_primes.push_back(static_cast<std::uint32_t>(prime));
    }
    const auto table = make_wheel_gap_table();
    validate_wheel_gap_table(table);
    const PreparedWindow window =
        prepare_window(geometry, prefix_primes, tail_primes, table);

    std::uint64_t* device_u64_primes = nullptr;
    std::uint32_t* device_u32_primes = nullptr;
    unsigned long long* device_words = nullptr;
    Counts* device_counts = nullptr;
    cuda_check(cudaMalloc(&device_u64_primes,
                          tail_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc uint64 primes");
    cuda_check(cudaMalloc(&device_u32_primes,
                          compact_primes.size() * sizeof(std::uint32_t)),
               "cudaMalloc uint32 primes");
    cuda_check(cudaMalloc(&device_words,
                          window.initial.size() * sizeof(std::uint64_t)),
               "cudaMalloc words");
    cuda_check(cudaMalloc(&device_counts, sizeof(Counts)),
               "cudaMalloc counts");
    cuda_check(cudaMemcpy(device_u64_primes, tail_primes.data(),
                          tail_primes.size() * sizeof(std::uint64_t),
                          cudaMemcpyHostToDevice),
               "copy uint64 primes");
    cuda_check(cudaMemcpy(device_u32_primes, compact_primes.data(),
                          compact_primes.size() * sizeof(std::uint32_t),
                          cudaMemcpyHostToDevice),
               "copy uint32 primes");

    const std::uint64_t square = 32'771ULL * 32'771ULL;
    const std::array<std::pair<std::string_view, Geometry>, 5>
        bounded_geometries{{
            {
                "low-inactive",
                {
                    "low-inactive",
                    4'000'001ULL,
                    4'000'001ULL + 2U * ((1ULL << 17U) - 1U),
                },
            },
            {
                "prime-square-activation",
                {
                    "prime-square-activation",
                    square - 2U * (1ULL << 16U),
                    square +
                        2U * ((1ULL << 17U) - (1ULL << 16U) - 1U),
                },
            },
            {
                "source-height",
                {
                    "source-height",
                    31'249'998'799'000'003ULL,
                    31'249'998'799'000'003ULL +
                        2U * ((1ULL << 18U) - 1U),
                },
            },
            {
                "non-word-aligned-end",
                {
                    "non-word-aligned-end",
                    31'249'998'799'000'003ULL,
                    31'249'998'799'000'003ULL +
                        2U * (262'147ULL - 1U),
                },
            },
            {
                "uint64-overflow-edge",
                {
                    "uint64-overflow-edge",
                    std::numeric_limits<std::uint64_t>::max() -
                        2U * ((1ULL << 18U) - 1U),
                    std::numeric_limits<std::uint64_t>::max(),
                },
            },
        }};
    std::vector<CaseResult> bounded_cases;
    bounded_cases.reserve(bounded_geometries.size());
    for (const auto& [name, bounded_geometry] : bounded_geometries) {
      bounded_cases.push_back(check_current_and_compact(
          std::string(name), bounded_geometry, prefix_primes, tail_primes,
          compact_primes, table, device_u64_primes, device_u32_primes,
          device_words, device_counts));
    }

    CaseResult source_case{};
    if (!bounded_only) {
      source_case = check_current_and_compact(
          "historical-terminal-segment", geometry, prefix_primes,
          tail_primes, compact_primes, table, device_u64_primes,
          device_u32_primes, device_words, device_counts);
      time_algorithm(current_wheel47_tail_kernel<false>, {window},
                     device_u64_primes, tail_primes.size(), device_words,
                     nullptr);
      time_compact(window, device_u32_primes, compact_primes.size(),
                   device_words);
    }

    std::vector<double> current_ms;
    std::vector<double> compact_ms;
    for (unsigned round = 0;
         !bounded_only && round < kQualificationRounds; ++round) {
      if ((round & 1U) == 0U) {
        current_ms.push_back(time_algorithm(
            current_wheel47_tail_kernel<false>, {window},
            device_u64_primes, tail_primes.size(), device_words, nullptr));
        compact_ms.push_back(time_compact(
            window, device_u32_primes, compact_primes.size(), device_words));
      } else {
        compact_ms.push_back(time_compact(
            window, device_u32_primes, compact_primes.size(), device_words));
        current_ms.push_back(time_algorithm(
            current_wheel47_tail_kernel<false>, {window},
            device_u64_primes, tail_primes.size(), device_words, nullptr));
      }
    }

    cudaFuncAttributes current_attributes{};
    cudaFuncAttributes compact_attributes{};
    cuda_check(cudaFuncGetAttributes(
                   &current_attributes,
                   current_wheel47_tail_kernel<false>),
               "get current attributes");
    cuda_check(cudaFuncGetAttributes(
                   &compact_attributes,
                   compact_u32_wheel47_tail_kernel<false>),
               "get compact attributes");
    const double current_median =
        bounded_only ? 0.0 : median(current_ms);
    const double compact_median =
        bounded_only ? 0.0 : median(compact_ms);
    const auto resources_ok = [](const cudaFuncAttributes& attributes) {
      return attributes.localSizeBytes == 0U &&
             attributes.sharedSizeBytes == 0U &&
             attributes.maxThreadsPerBlock >=
                 static_cast<int>(kThreads) &&
             attributes.numRegs > 0 && attributes.numRegs <= 64;
    };
    if (!resources_ok(current_attributes) ||
        !resources_ok(compact_attributes)) {
      throw std::runtime_error("tail-prime compiler resource gate failed");
    }

    cuda_check(cudaFree(device_counts), "free counts");
    cuda_check(cudaFree(device_words), "free words");
    cuda_check(cudaFree(device_u32_primes), "free uint32 primes");
    cuda_check(cudaFree(device_u64_primes), "free uint64 primes");

    std::cout << "{\"accepted\":true"
              << ",\"algorithm_equivalence_scope\":"
                 "\"cpu-vs-current-u64-vs-candidate-u32-all-output-words\""
              << ",\"all_word_equality\":true"
              << ",\"benchmark\":{\"candidate_median_ms\":"
              << std::fixed << std::setprecision(6)
              << (bounded_only ? 0.0 : compact_median)
              << ",\"candidate_ms\":";
    print_double_array(compact_ms);
    std::cout << ",\"current_median_ms\":"
              << (bounded_only ? 0.0 : current_median)
              << ",\"current_ms\":";
    print_double_array(current_ms);
    std::cout << ",\"current_over_candidate_rate_ratio\":"
              << (bounded_only ? 0.0 : current_median / compact_median)
              << ",\"rounds\":"
              << (bounded_only ? 0U : kQualificationRounds)
              << "}"
              << ",\"bounded_cases\":[";
    for (std::size_t index = 0; index < bounded_cases.size(); ++index) {
      if (index != 0U) std::cout << ",";
      print_compact_case(bounded_cases[index]);
    }
    std::cout << "]"
              << ",\"build_profile\":{\"cmake_build_config\":\""
              << kBuildProfile << "\",\"ndebug_defined\":"
              << (kNdebugDefined ? "true" : "false") << "}"
              << ",\"candidate_resources\":";
    print_resources(compact_attributes);
    std::cout << ",\"candidate_selected_in_production\":false"
              << ",\"classification\":"
                 "\"qualification-only-unpromoted-candidate\""
              << ",\"compute_capability\":\"" << properties.major << "."
              << properties.minor << "\""
              << ",\"cuda_to_lean_refinement_proved\":false"
              << ",\"current_resources\":";
    print_resources(current_attributes);
    std::cout << ",\"h100_measured\":false"
              << ",\"kind\":"
                 "\"sparkinterval.goldbach-tail-u32-prime-qualification.v1\""
              << ",\"lean_bridge_complete\":false"
              << ",\"mode\":\""
              << (bounded_only ? "bounded-only" : "source-segment")
              << "\""
              << ",\"performance_evidence_eligible\":false"
              << ",\"production_identity_changed\":false"
              << ",\"production_ready\":false"
              << ",\"release_build_profile_eligible\":true"
              << ",\"receipt_emitted\":false"
              << ",\"resource_gate_passed\":true"
              << ",\"roster\":{\"count\":" << tail_primes.size()
              << ",\"highest_prime\":" << tail_primes.back()
              << ",\"prime_limit\":" << prime_limit
              << ",\"sha256_le_u32\":\""
              << canonical_u32_sha256(compact_primes) << "\""
              << ",\"uint32_bytes\":"
              << compact_primes.size() * sizeof(std::uint32_t)
              << ",\"uint32_fit\":true"
              << ",\"uint64_bytes\":"
              << tail_primes.size() * sizeof(std::uint64_t)
              << "}"
              << ",\"source_case\":";
    if (bounded_only) {
      std::cout << "null";
    } else {
      print_compact_case(source_case);
    }
    std::cout << ",\"strict_h100_target\":"
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
              << "true"
#else
              << "false"
#endif
              << ",\"theorem_claimed\":false"
              << ",\"runtime_instrumentation_status\":"
                 "\"not-inspected-by-runner\""
              << ",\"warp_parallel_cutoff\":"
              << kWarpParallelCutoff
              << ",\"word_owner_cutoff\":" << kWordOwnerCutoff
              << "}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 2;
  }
}
