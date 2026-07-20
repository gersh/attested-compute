// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_r2star_factor_support.h"

#include "sparkinterval/sha256.hpp"

#include <array>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

constexpr std::uint64_t kR2StarSourceLimit = 21'000'000'000ULL;
constexpr std::uint64_t kDefaultCount = 65'536;
constexpr std::uint64_t kMaximumSegmentCount = 100'000'000;

struct Options {
  std::uint64_t lower = 1;
  std::uint64_t count = kDefaultCount;
  int device = 0;
  bool allow_other_device = false;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  fail(std::string(operation) + " failed: " + cudaGetErrorString(status), 3);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) fail_cuda(operation, status);
}

bool parse_u64(std::string_view text, std::uint64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(require_value("--lower"), &options.lower)) {
        fail("--lower must be a nonnegative integer");
      }
    } else if (argument == "--count") {
      if (!parse_u64(require_value("--count"), &options.count)) {
        fail("--count must be a nonnegative integer");
      }
    } else if (argument == "--device") {
      std::uint64_t parsed = 0;
      if (!parse_u64(require_value("--device"), &parsed) ||
          parsed > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-r2star-factor-support "
             "[--lower N] [--count N] [--device N] "
             "[--allow-other-device]\n"
             "Computes one bounded factor-support segment and independently "
             "checks every GPU record on the CPU.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 1 || options.lower > kR2StarSourceLimit) {
    fail("--lower must lie in [1, 21000000000]");
  }
  if (options.count < 1 || options.count > kMaximumSegmentCount) {
    fail("--count must lie in [1, 100000000]");
  }
  if (options.count - 1 > kR2StarSourceLimit - options.lower) {
    fail("requested segment exceeds the R2Star source range through 21000000000");
  }
  return options;
}

std::uint64_t integer_square_root(std::uint64_t value) {
  std::uint64_t lower = 0;
  std::uint64_t upper =
      (value < std::numeric_limits<std::uint32_t>::max())
          ? value + 1
          : static_cast<std::uint64_t>(
                std::numeric_limits<std::uint32_t>::max()) +
                1;
  while (lower + 1 < upper) {
    const std::uint64_t middle = lower + (upper - lower) / 2;
    if (middle <= value / middle) {
      lower = middle;
    } else {
      upper = middle;
    }
  }
  return lower;
}

std::vector<std::uint32_t> exact_primes_upto(std::uint64_t limit64) {
  if (limit64 < 2) return {};
  if (limit64 > std::numeric_limits<std::uint32_t>::max()) {
    fail("base-prime limit exceeds the supported exact sieve range");
  }
  const auto limit = static_cast<std::uint32_t>(limit64);
  std::vector<bool> composite(static_cast<std::size_t>(limit) + 1, false);
  for (std::uint32_t prime = 2; prime <= limit / prime; ++prime) {
    if (composite[prime]) continue;
    for (std::uint64_t multiple =
             static_cast<std::uint64_t>(prime) * prime;
         multiple <= limit; multiple += prime) {
      composite[static_cast<std::size_t>(multiple)] = true;
    }
  }
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2; candidate <= limit; ++candidate) {
    if (!composite[candidate]) primes.push_back(candidate);
  }
  return primes;
}

TgR2StarFactorSupport independently_factor(
    std::uint64_t number, const std::vector<std::uint32_t>& primes) {
  TgR2StarFactorSupport result{};
  if (number < 2) return result;

  std::uint64_t remaining = number;
  auto add_factor = [&](std::uint64_t factor) {
    if (result.distinct_prime_factor_count == 0) {
      result.first_prime = factor;
    } else if (result.distinct_prime_factor_count == 1) {
      result.second_prime = factor;
    }
    if (result.distinct_prime_factor_count < 3) {
      ++result.distinct_prime_factor_count;
    }
  };

  for (std::uint32_t prime : primes) {
    if (static_cast<std::uint64_t>(prime) > remaining / prime) break;
    if (remaining % prime != 0) continue;
    add_factor(prime);
    do {
      remaining /= prime;
    } while (remaining % prime == 0);
    if (result.distinct_prime_factor_count == 3) return result;
  }
  if (remaining > 1) add_factor(remaining);
  return result;
}

void hash_u32_le(sparkinterval::detail::Sha256* hasher,
                 std::uint32_t value) {
  std::array<unsigned char, 4> bytes{};
  for (unsigned int index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

void hash_u64_le(sparkinterval::detail::Sha256* hasher,
                 std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (unsigned int index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

void hash_record(sparkinterval::detail::Sha256* hasher,
                 const TgR2StarFactorSupport& record) {
  hash_u64_le(hasher, record.first_prime);
  hash_u64_le(hasher, record.second_prime);
  hash_u32_le(hasher, record.distinct_prime_factor_count);
  hash_u32_le(hasher, record.reserved);
}

std::string json_escape(std::string_view value) {
  constexpr char hex[] = "0123456789abcdef";
  std::string escaped;
  for (unsigned char byte : value) {
    switch (byte) {
      case '"': escaped += "\\\""; break;
      case '\\': escaped += "\\\\"; break;
      case '\b': escaped += "\\b"; break;
      case '\f': escaped += "\\f"; break;
      case '\n': escaped += "\\n"; break;
      case '\r': escaped += "\\r"; break;
      case '\t': escaped += "\\t"; break;
      default:
        if (byte < 0x20) {
          escaped += "\\u00";
          escaped.push_back(hex[byte >> 4]);
          escaped.push_back(hex[byte & 0xf]);
        } else {
          escaped.push_back(static_cast<char>(byte));
        }
    }
  }
  return escaped;
}

bool same_record(const TgR2StarFactorSupport& left,
                 const TgR2StarFactorSupport& right) {
  return left.first_prime == right.first_prime &&
         left.second_prime == right.second_prime &&
         left.distinct_prime_factor_count ==
             right.distinct_prime_factor_count &&
         left.reserved == right.reserved;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::size_t count = static_cast<std::size_t>(options.count);
  const std::uint64_t upper = options.lower + options.count - 1;
  const std::uint64_t base_prime_limit = integer_square_root(upper);
  const std::vector<std::uint32_t> primes =
      exact_primes_upto(base_prime_limit);

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for "
         "explicit cross-device testing",
         4);
  }
  if (options.device >= device_count) {
    fail("requested CUDA device is unavailable", 4);
  }
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));

  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use "
         "--allow-other-device only for explicit cross-device testing",
         4);
  }

  if (count > std::numeric_limits<std::size_t>::max() /
                  sizeof(TgR2StarFactorSupport)) {
    fail("factor-support output allocation exceeds host address space");
  }
  const std::size_t output_bytes = count * sizeof(TgR2StarFactorSupport);
  const std::size_t prime_bytes = primes.size() * sizeof(std::uint32_t);
  std::uint32_t* device_primes = nullptr;
  TgR2StarFactorSupport* device_outputs = nullptr;
  if (!primes.empty()) {
    check_cuda("cudaMalloc(base_primes)",
               cudaMalloc(reinterpret_cast<void**>(&device_primes),
                          prime_bytes));
    check_cuda("cudaMemcpy(base_primes)",
               cudaMemcpy(device_primes, primes.data(), prime_bytes,
                          cudaMemcpyHostToDevice));
  }
  check_cuda("cudaMalloc(outputs)",
             cudaMalloc(reinterpret_cast<void**>(&device_outputs),
                        output_bytes));

  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  check_cuda("factor-support launch",
             launch_tg_r2star_factor_support(
                 options.lower, count, device_primes, primes.size(),
                 device_outputs));
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float kernel_milliseconds = 0.0F;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&kernel_milliseconds, start, stop));

  std::vector<TgR2StarFactorSupport> outputs(count);
  check_cuda("cudaMemcpy(outputs)",
             cudaMemcpy(outputs.data(), device_outputs, output_bytes,
                        cudaMemcpyDeviceToHost));
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  if (device_primes != nullptr) {
    check_cuda("cudaFree(base_primes)", cudaFree(device_primes));
  }
  check_cuda("cudaFree(outputs)", cudaFree(device_outputs));

  const auto host_start = std::chrono::steady_clock::now();
  sparkinterval::detail::Sha256 gpu_hasher;
  sparkinterval::detail::Sha256 cpu_hasher;
  std::array<std::uint64_t, 4> support_histogram{};
  std::uint64_t mismatch_count = 0;
  std::uint64_t first_mismatch_number = 0;
  TgR2StarFactorSupport first_mismatch_gpu{};
  TgR2StarFactorSupport first_mismatch_cpu{};
  for (std::size_t index = 0; index < count; ++index) {
    const TgR2StarFactorSupport expected =
        independently_factor(options.lower + index, primes);
    const TgR2StarFactorSupport& actual = outputs[index];
    hash_record(&gpu_hasher, actual);
    hash_record(&cpu_hasher, expected);
    if (actual.distinct_prime_factor_count <= 3) {
      ++support_histogram[actual.distinct_prime_factor_count];
    }
    if (!same_record(actual, expected)) {
      if (mismatch_count == 0) {
        first_mismatch_number = options.lower + index;
        first_mismatch_gpu = actual;
        first_mismatch_cpu = expected;
      }
      ++mismatch_count;
    }
  }
  const auto host_stop = std::chrono::steady_clock::now();
  const double host_milliseconds =
      std::chrono::duration<double, std::milli>(host_stop - host_start).count();
  const std::string gpu_digest =
      sparkinterval::lowercase_hex(gpu_hasher.finish());
  const std::string cpu_digest =
      sparkinterval::lowercase_hex(cpu_hasher.finish());
  const bool passed = mismatch_count == 0 && gpu_digest == cpu_digest;

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  const double records_per_second = kernel_milliseconds > 0.0F
      ? static_cast<double>(count) * 1000.0 / kernel_milliseconds
      : 0.0;

  std::cout << std::setprecision(17)
            << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"algorithm\": \"r2star_distinct_prime_factor_support_v1\",\n"
            << "  \"classification\": "
               "\"bounded_factor_support_primitive_not_r2star_atom_proof\",\n"
            << "  \"lower\": " << options.lower << ",\n"
            << "  \"upper\": " << upper << ",\n"
            << "  \"record_count\": " << count << ",\n"
            << "  \"base_prime_limit\": " << base_prime_limit << ",\n"
            << "  \"base_prime_count\": " << primes.size() << ",\n"
            << "  \"base_prime_generation\": "
               "\"exact_host_eratosthenes_sieve\",\n"
            << "  \"gpu_record_sha256_le_v1\": \"" << gpu_digest << "\",\n"
            << "  \"cpu_record_sha256_le_v1\": \"" << cpu_digest << "\",\n"
            << "  \"all_records_compared_with_independent_cpu_factorization\": "
            << (passed ? "true" : "false") << ",\n"
            << "  \"mismatch_count\": " << mismatch_count << ",\n"
            << "  \"support_count_histogram\": {\"0\": "
            << support_histogram[0] << ", \"1\": " << support_histogram[1]
            << ", \"2\": " << support_histogram[2] << ", \"3_or_more\": "
            << support_histogram[3] << "},\n";
  if (mismatch_count == 0) {
    std::cout << "  \"first_mismatch\": null,\n";
  } else {
    std::cout
        << "  \"first_mismatch\": {\"number\": " << first_mismatch_number
        << ", \"gpu\": {\"first\": " << first_mismatch_gpu.first_prime
        << ", \"second\": " << first_mismatch_gpu.second_prime
        << ", \"count\": "
        << first_mismatch_gpu.distinct_prime_factor_count
        << ", \"reserved\": " << first_mismatch_gpu.reserved
        << "}, \"cpu\": {\"first\": " << first_mismatch_cpu.first_prime
        << ", \"second\": " << first_mismatch_cpu.second_prime
        << ", \"count\": "
        << first_mismatch_cpu.distinct_prime_factor_count
        << ", \"reserved\": " << first_mismatch_cpu.reserved << "}},\n";
  }
  std::cout
      << "  \"device_name\": \"" << json_escape(properties.name) << "\",\n"
      << "  \"compute_capability\": \"" << properties.major << '.'
      << properties.minor << "\",\n"
      << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
      << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
      << "  \"kernel_milliseconds\": " << kernel_milliseconds << ",\n"
      << "  \"kernel_records_per_second\": " << records_per_second << ",\n"
      << "  \"independent_cpu_check_milliseconds\": " << host_milliseconds
      << ",\n"
      << "  \"full_ramare_source_range\": "
      << ((options.lower == 1 && options.count == kR2StarSourceLimit) ? "true"
                                                                       : "false")
      << ",\n"
      << "  \"checks_logarithm_enclosures\": false,\n"
      << "  \"checks_r2star_accumulation\": false,\n"
      << "  \"checks_ramare_inequality\": false,\n"
      << "  \"proves_ramare_zuniga_lemma_6_2\": false,\n"
      << "  \"proves_any_external_atom\": false\n"
      << "}\n";
  return passed ? 0 : 5;
}
