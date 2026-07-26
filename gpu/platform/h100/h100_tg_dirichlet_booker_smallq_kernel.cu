// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Untrusted H100 proposal kernel for Platt's small-q Gaussian sums.  Every
// returned midpoint must be enclosed by a fresh Arb/MPFR evaluation before it
// can enter a retained analytic artifact.

#include "sparkinterval/tg_dirichlet_booker_smallq.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unistd.h>
#include <vector>

namespace sq = sparkinterval::tg::dirichlet_booker_smallq;

namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;

#define CUDA_CHECK(call)                                                    \
  do {                                                                      \
    const cudaError_t status_ = (call);                                     \
    if (status_ != cudaSuccess) {                                           \
      std::fprintf(stderr, "cuda error %s at %s:%d\n",                    \
                   cudaGetErrorString(status_), __FILE__, __LINE__);        \
      std::exit(2);                                                         \
    }                                                                       \
  } while (0)

struct Complex64 {
  double re;
  double im;
};

__device__ __forceinline__ Complex64 multiply(Complex64 x, Complex64 y) {
  return {fma(x.re, y.re, -x.im * y.im),
          fma(x.re, y.im, x.im * y.re)};
}

__global__ void gaussian_kernel(
    sq::InputHeader header, const std::uint32_t* character_exponents,
    const sq::FrequencyRequest* requests, sq::OutputItem* output) {
  const std::uint64_t local =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (local >= header.frequency_count) return;
  const sq::FrequencyRequest request = requests[local];
  std::uint32_t status = 0;
  const double signed_absolute =
      static_cast<double>(request.signed_index < 0
                              ? -request.signed_index
                              : request.signed_index);
  const double x = 2.0 * kPi * signed_absolute / header.b;
  const double u_imag = kPi * header.eta / 4.0;
  double sine_2u = 0.0;
  double cosine_2u = 0.0;
  sincos(2.0 * u_imag, &sine_2u, &cosine_2u);
  const double exp_2x = exp(2.0 * x);
  const double gaussian_real = -kPi * exp_2x * cosine_2u / header.q;
  const double gaussian_imag = -kPi * exp_2x * sine_2u / header.q;
  if (!(gaussian_real < 0.0) || !isfinite(gaussian_real) ||
      !isfinite(gaussian_imag)) {
    status = 1;
  }

  Complex64 sum{0.0, 0.0};
  if (status == 0) {
    for (std::uint32_t n = 1; n <= request.truncation; ++n) {
      const std::uint32_t exponent = character_exponents[n % header.q];
      if (exponent == sq::kNonUnitExponent) continue;
      const double n_squared = static_cast<double>(n) * n;
      const double log_magnitude = gaussian_real * n_squared;
      // Terms below binary64's subnormal range contribute zero to this
      // proposal.  Arb still accounts for them in the certified tail.
      if (log_magnitude < -745.0) continue;
      const double phase =
          gaussian_imag * n_squared +
          2.0 * kPi * static_cast<double>(exponent) /
              static_cast<double>(header.group_exponent);
      double sine = 0.0;
      double cosine = 0.0;
      sincos(phase, &sine, &cosine);
      double magnitude = exp(log_magnitude);
      if (header.parity != 0U) magnitude *= n;
      sum.re = fma(magnitude, cosine, sum.re);
      sum.im = fma(magnitude, sine, sum.im);
    }
  }

  const double p = header.parity == 0U ? 0.5 : 1.5;
  const double prefactor_magnitude =
      2.0 * exp(p * x) / pow(static_cast<double>(header.q), p / 2.0);
  double prefactor_sine = 0.0;
  double prefactor_cosine = 0.0;
  sincos(p * u_imag, &prefactor_sine, &prefactor_cosine);
  const Complex64 tilt{prefactor_magnitude * prefactor_cosine,
                       prefactor_magnitude * prefactor_sine};
  const Complex64 epsilon{header.epsilon_real, header.epsilon_imag};
  Complex64 answer = multiply(multiply(epsilon, tilt), sum);
  if (request.signed_index < 0) answer.im = -answer.im;
  if (!isfinite(answer.re) || !isfinite(answer.im)) status = 1;
  output[local] = {request.index, answer.re, answer.im, status, 0U};
}

template <typename T>
std::vector<T> read_array(std::ifstream& input, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " array exceeds size_t");
  }
  std::vector<T> result(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(result.data()),
             static_cast<std::streamsize>(result.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("short read of ") + label);
  return result;
}

struct Input {
  sq::InputHeader header;
  std::vector<std::uint32_t> exponents;
  std::vector<sq::FrequencyRequest> requests;
};

Input read_input(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open input");
  Input result{};
  input.read(reinterpret_cast<char*>(&result.header), sizeof(result.header));
  if (!input || std::memcmp(result.header.magic, sq::kInputMagic, 8) != 0 ||
      result.header.version != sq::kFormatVersion || result.header.q < 3U ||
      result.header.q > sq::kMaximumModulus ||
      result.header.group_exponent == 0U || result.header.parity > 1U ||
      result.header.transform_length == 0U ||
      (result.header.transform_length & (result.header.transform_length - 1U)) != 0U ||
      result.header.frequency_count == 0U ||
      result.header.frequency_start + result.header.frequency_count <
          result.header.frequency_start ||
      result.header.frequency_start + result.header.frequency_count >
          result.header.transform_length ||
      !(result.header.eta > -1.0 && result.header.eta < 1.0) ||
      !(result.header.b > 0.0) || !std::isfinite(result.header.b) ||
      !std::isfinite(result.header.epsilon_real) ||
      !std::isfinite(result.header.epsilon_imag) || result.header.reserved0 != 0U) {
    throw std::runtime_error("invalid small-q input header");
  }
  const std::uintmax_t expected_size =
      sizeof(sq::InputHeader) +
      static_cast<std::uintmax_t>(result.header.q) * sizeof(std::uint32_t) +
      static_cast<std::uintmax_t>(result.header.frequency_count) *
          sizeof(sq::FrequencyRequest);
  if (std::filesystem::file_size(path) != expected_size) {
    throw std::runtime_error("noncanonical small-q input length");
  }
  result.exponents = read_array<std::uint32_t>(input, result.header.q, "exponents");
  result.requests = read_array<sq::FrequencyRequest>(
      input, result.header.frequency_count, "requests");
  for (std::uint32_t residue = 0; residue < result.header.q; ++residue) {
    const std::uint32_t exponent = result.exponents[residue];
    if (exponent != sq::kNonUnitExponent && exponent >= result.header.group_exponent) {
      throw std::runtime_error("character exponent outside group exponent");
    }
  }
  for (std::uint64_t local = 0; local < result.header.frequency_count; ++local) {
    const auto& request = result.requests[local];
    const std::uint64_t expected = result.header.frequency_start + local;
    const std::int64_t signed_expected =
        expected <= result.header.transform_length / 2U
            ? static_cast<std::int64_t>(expected)
            : static_cast<std::int64_t>(expected - result.header.transform_length);
    if (request.index != expected || request.signed_index != signed_expected ||
        request.truncation > 100000000U || request.reserved0 != 0U) {
      throw std::runtime_error("invalid frequency request");
    }
  }
  return result;
}

void write_output(const std::filesystem::path& path, const Input& input,
                  const std::vector<sq::OutputItem>& values,
                  std::uint64_t elapsed_nanoseconds) {
  const auto parent = path.parent_path().empty() ? std::filesystem::path(".")
                                                  : path.parent_path();
  std::filesystem::create_directories(parent);
  const std::filesystem::path temporary =
      parent / ("." + path.filename().string() + "." +
                std::to_string(static_cast<unsigned long long>(getpid())) + ".tmp");
  std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open temporary output");
  sq::OutputHeader header{};
  std::memcpy(header.magic, sq::kOutputMagic, 8);
  header.version = sq::kFormatVersion;
  header.q = input.header.q;
  header.frequency_start = input.header.frequency_start;
  header.frequency_count = input.header.frequency_count;
  header.elapsed_nanoseconds = elapsed_nanoseconds;
  output.write(reinterpret_cast<const char*>(&header), sizeof(header));
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(values[0])));
  output.flush();
  if (!output) throw std::runtime_error("cannot write small-q output");
  output.close();
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot install output: " + error.message());
  }
}

unsigned parse_iterations(const char* value) {
  errno = 0;
  char* end = nullptr;
  const unsigned long parsed = std::strtoul(value, &end, 10);
  if (errno != 0 || end == value || *end != '\0' || parsed == 0U || parsed > 10000U) {
    throw std::runtime_error("iterations must lie in 1..10000");
  }
  return static_cast<unsigned>(parsed);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3 && argc != 4) {
      std::fprintf(stderr, "usage: %s INPUT OUTPUT [ITERATIONS]\n", argv[0]);
      return 2;
    }
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
    int device = 0;
    CUDA_CHECK(cudaGetDevice(&device));
    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
    if (properties.major != 9 || properties.minor != 0) {
      throw std::runtime_error(
          "strict H100 build requires a physical sm_90 device");
    }
#endif
    const unsigned iterations = argc == 4 ? parse_iterations(argv[3]) : 1U;
    const Input input = read_input(argv[1]);
    std::uint32_t* device_exponents = nullptr;
    sq::FrequencyRequest* device_requests = nullptr;
    sq::OutputItem* device_output = nullptr;
    CUDA_CHECK(cudaMalloc(&device_exponents,
                          input.exponents.size() * sizeof(input.exponents[0])));
    CUDA_CHECK(cudaMalloc(&device_requests,
                          input.requests.size() * sizeof(input.requests[0])));
    CUDA_CHECK(cudaMalloc(&device_output,
                          input.requests.size() * sizeof(sq::OutputItem)));
    CUDA_CHECK(cudaMemcpy(device_exponents, input.exponents.data(),
                          input.exponents.size() * sizeof(input.exponents[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_requests, input.requests.data(),
                          input.requests.size() * sizeof(input.requests[0]),
                          cudaMemcpyHostToDevice));
    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    constexpr unsigned threads = 256;
    const unsigned blocks = static_cast<unsigned>(
        (input.header.frequency_count + threads - 1U) / threads);
    CUDA_CHECK(cudaEventRecord(start));
    for (unsigned iteration = 0; iteration < iterations; ++iteration) {
      gaussian_kernel<<<blocks, threads>>>(input.header, device_exponents,
                                            device_requests, device_output);
    }
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
    std::vector<sq::OutputItem> output(input.requests.size());
    CUDA_CHECK(cudaMemcpy(output.data(), device_output,
                          output.size() * sizeof(output[0]),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaFree(device_output));
    CUDA_CHECK(cudaFree(device_requests));
    CUDA_CHECK(cudaFree(device_exponents));
    const std::uint64_t elapsed_ns = static_cast<std::uint64_t>(
        static_cast<double>(elapsed_ms) * 1000000.0 / iterations);
    write_output(argv[2], input, output, elapsed_ns);
    std::printf(
        "{\"algorithm\":\"platt-booker-smallq-gaussian-gpu-proposal-v1\","
        "\"frequencies\":%llu,\"iterations\":%u,"
        "\"elapsed_nanoseconds_per_iteration\":%llu,"
        "\"trusted_certificate\":false}\n",
        static_cast<unsigned long long>(input.header.frequency_count), iterations,
        static_cast<unsigned long long>(elapsed_ns));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "h100_tg_dirichlet_booker_smallq_kernel: %s\n",
                 error.what());
    return 2;
  }
}
