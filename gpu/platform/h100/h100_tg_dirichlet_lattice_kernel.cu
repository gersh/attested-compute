// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Clean-room implementation of the finite Taylor-reconstruction step in
// Platt, arXiv:1305.3087v1, Lemma 4.2.  This is deliberately a conditional
// numeric stage: its input contract requires certified Hurwitz-lattice cells
// and a certified truncation radius.  It does not compute those certificates,
// perform the unit-group DFT, isolate zeros, or prove Turing completeness.

#include "sparkinterval/tg_dirichlet_lattice.hpp"

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
#include <numeric>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unistd.h>
#include <vector>

namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

using dl::ComplexInterval;
using dl::InputHeader;
using dl::InputItem;
using dl::OutputHeader;
using dl::OutputItem;
using dl::RealInterval;

#define CUDA_CHECK(call)                                                    \
  do {                                                                      \
    const cudaError_t status_ = (call);                                     \
    if (status_ != cudaSuccess) {                                           \
      std::fprintf(stderr, "cuda error %s at %s:%d\n",                    \
                   cudaGetErrorString(status_), __FILE__, __LINE__);        \
      std::exit(2);                                                         \
    }                                                                       \
  } while (0)

__device__ __forceinline__ RealInterval add(RealInterval x,
                                             RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x,
                                             RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x,
                                             RealInterval y) {
  // Monotonicity determines the extrema from the endpoint signs.  Most
  // production intervals are narrow and sign-definite, so evaluating all
  // four products (twice, for both rounding modes) wastes six directed
  // multiplications.  The crossing/crossing case still evaluates the four
  // mathematically possible extrema.  Input validation excludes NaNs.
  if (x.lo >= 0.0) {
    if (y.lo >= 0.0) {
      return {__dmul_rd(x.lo, y.lo), __dmul_ru(x.hi, y.hi)};
    }
    if (y.hi <= 0.0) {
      return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.lo, y.hi)};
    }
    return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.hi, y.hi)};
  }
  if (x.hi <= 0.0) {
    if (y.lo >= 0.0) {
      return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.hi, y.lo)};
    }
    if (y.hi <= 0.0) {
      return {__dmul_rd(x.hi, y.hi), __dmul_ru(x.lo, y.lo)};
    }
    return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.lo, y.lo)};
  }
  if (y.lo >= 0.0) {
    return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.hi, y.hi)};
  }
  if (y.hi <= 0.0) {
    return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.lo, y.lo)};
  }
  return {
      fmin(__dmul_rd(x.lo, y.hi), __dmul_rd(x.hi, y.lo)),
      fmax(__dmul_ru(x.lo, y.lo), __dmul_ru(x.hi, y.hi)),
  };
}

__device__ __forceinline__ RealInterval div_positive(RealInterval x,
                                                      double denominator) {
  return {__ddiv_rd(x.lo, denominator), __ddiv_ru(x.hi, denominator)};
}

__device__ __forceinline__ RealInterval rational_nonnegative(
    std::uint64_t numerator, std::uint64_t denominator) {
  const double n = static_cast<double>(numerator);
  const double d = static_cast<double>(denominator);
  return {__ddiv_rd(n, d), __ddiv_ru(n, d)};
}

__device__ __forceinline__ ComplexInterval cadd(ComplexInterval x,
                                                 ComplexInterval y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval cmul(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

__device__ __forceinline__ ComplexInterval cscale(ComplexInterval x,
                                                   RealInterval y) {
  return {mul(x.re, y), mul(x.im, y)};
}

__device__ __forceinline__ ComplexInterval cdiv_positive(
    ComplexInterval x, double denominator) {
  return {div_positive(x.re, denominator),
          div_positive(x.im, denominator)};
}

__global__ void taylor_reconstruct_kernel(
    InputHeader header, const ComplexInterval* lattice,
    const InputItem* requests, OutputItem* results) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= header.item_count) return;

  const InputItem request = requests[index];
  const RealInterval a_over_q = rational_nonnegative(request.a, request.q);
  const RealInterval r_over_d =
      rational_nonnegative(request.lattice_row, dl::kLatticeRows);
  // Lemma 4.2 uses (-delta)^k with delta=a/q-r/D.
  const RealInterval minus_delta = sub(r_over_d, a_over_q);
  const RealInterval t = rational_nonnegative(
      static_cast<std::uint64_t>(header.t_numerator), header.t_denominator);

  ComplexInterval power{{1.0, 1.0}, {0.0, 0.0}};
  ComplexInterval sum{{0.0, 0.0}, {0.0, 0.0}};
  for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
    const std::size_t lattice_offset =
        (static_cast<std::size_t>(request.lattice_row) - 1U) *
            dl::kTaylorColumns +
        column;
    const ComplexInterval zeta = lattice[lattice_offset];
    sum = cadd(sum, cmul(power, zeta));
    if (column != dl::kTaylorDegree) {
      const ComplexInterval s_plus_column{
          {static_cast<double>(column) + 0.5,
           static_cast<double>(column) + 0.5},
          t};
      power = cdiv_positive(
          cscale(cmul(power, s_plus_column), minus_delta),
          static_cast<double>(column + 1U));
    }
  }

  const double radius = request.tail_radius_hi;
  sum.re.lo = __dsub_rd(sum.re.lo, radius);
  sum.re.hi = __dadd_ru(sum.re.hi, radius);
  sum.im.lo = __dsub_rd(sum.im.lo, radius);
  sum.im.hi = __dadd_ru(sum.im.hi, radius);
  const bool finite = isfinite(sum.re.lo) && isfinite(sum.re.hi) &&
                      isfinite(sum.im.lo) && isfinite(sum.im.hi) &&
                      sum.re.lo <= sum.re.hi && sum.im.lo <= sum.im.hi;
  results[index] = {request.q, request.a, request.lattice_row,
                    finite ? 0U : 1U, sum};
}

template <typename T>
std::vector<T> read_array(std::ifstream& input, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " array is too large");
  }
  std::vector<T> values(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("short read of ") + label);
  return values;
}

bool finite_interval(const RealInterval& value) {
  return std::isfinite(value.lo) && std::isfinite(value.hi) &&
         value.lo <= value.hi;
}

void validate_input(const InputHeader& header,
                    const std::vector<ComplexInterval>& lattice,
                    const std::vector<InputItem>& requests) {
  if (std::memcmp(header.magic, dl::kInputMagic, sizeof(header.magic)) != 0 ||
      header.version != dl::kFormatVersion ||
      header.lattice_rows != dl::kLatticeRows ||
      header.taylor_degree != dl::kTaylorDegree || header.reserved0 != 0 ||
      header.reserved1 != 0 || header.t_numerator < 0 ||
      header.t_denominator == 0 || header.item_count == 0 ||
      static_cast<std::uint64_t>(header.t_numerator) > (1ULL << 53U) ||
      header.t_denominator > (1ULL << 53U) ||
      header.lattice_cell_count != dl::kLatticeCellCount ||
      header.item_count != requests.size() ||
      lattice.size() != dl::kLatticeCellCount) {
    throw std::runtime_error("invalid Dirichlet lattice input header");
  }
  for (const ComplexInterval& cell : lattice) {
    if (!finite_interval(cell.re) || !finite_interval(cell.im)) {
      throw std::runtime_error("non-finite or reversed lattice interval");
    }
  }
  for (const InputItem& request : requests) {
    if (request.q < 3 || request.q > 400000 || request.a == 0 ||
        request.a >= request.q || std::gcd(request.a, request.q) != 1 ||
        request.reserved != 0 || !std::isfinite(request.tail_radius_hi) ||
        request.tail_radius_hi < 0.0 ||
        request.lattice_row !=
            dl::canonical_lattice_row(request.q, request.a)) {
      throw std::runtime_error("invalid or noncanonical residue request");
    }
    // Lemma 4.2's strict |delta| < alpha condition, checked exactly after
    // clearing the positive denominator q*D.
    const std::int64_t delta_numerator =
        static_cast<std::int64_t>(dl::kLatticeRows) * request.a -
        static_cast<std::int64_t>(request.lattice_row) * request.q;
    const std::uint64_t absolute_delta = static_cast<std::uint64_t>(
        delta_numerator < 0 ? -delta_numerator : delta_numerator);
    if (absolute_delta >=
        static_cast<std::uint64_t>(request.lattice_row) * request.q) {
      throw std::runtime_error("Taylor request violates |delta| < alpha");
    }
  }
}

void write_output_atomic(const std::filesystem::path& path,
                         const OutputHeader& header,
                         const std::vector<OutputItem>& results) {
  const std::filesystem::path temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create temporary output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    output.write(reinterpret_cast<const char*>(results.data()),
                 static_cast<std::streamsize>(results.size() * sizeof(OutputItem)));
    output.flush();
    if (!output) throw std::runtime_error("cannot write output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish output: " + error.message());
  }
}

int parse_nonnegative(const char* text, const char* label) {
  char* end = nullptr;
  errno = 0;
  const long value = std::strtol(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || value < 0 ||
      value > std::numeric_limits<int>::max()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<int>(value);
}

int parse_positive(const char* text, const char* label) {
  const int value = parse_nonnegative(text, label);
  if (value == 0) throw std::runtime_error(std::string(label) + " must be positive");
  return value;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 3 || argc > 5) {
      std::fprintf(stderr,
                   "usage: %s INPUT.bin OUTPUT.bin [device] [iterations]\n",
                   argv[0]);
      return 1;
    }
    const int device = argc >= 4 ? parse_nonnegative(argv[3], "device") : 0;
    const int iterations = argc >= 5 ? parse_positive(argv[4], "iterations") : 1;
    CUDA_CHECK(cudaSetDevice(device));
    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
    if (properties.major != 9 || properties.minor != 0 ||
        std::strstr(properties.name, "H100") == nullptr) {
      throw std::runtime_error(
          "strict production runner requires an H100 with compute capability 9.0");
    }
#endif

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    InputHeader header{};
    input.read(reinterpret_cast<char*>(&header), sizeof(header));
    if (!input) throw std::runtime_error("short read of input header");
    if (std::memcmp(header.magic, dl::kInputMagic, sizeof(header.magic)) != 0 ||
        header.version != dl::kFormatVersion ||
        header.lattice_rows != dl::kLatticeRows ||
        header.taylor_degree != dl::kTaylorDegree || header.reserved0 != 0 ||
        header.reserved1 != 0 || header.t_numerator < 0 ||
        header.t_denominator == 0 || header.item_count == 0 ||
        header.lattice_cell_count != dl::kLatticeCellCount) {
      throw std::runtime_error("invalid Dirichlet lattice input header");
    }
    const std::uintmax_t file_size = std::filesystem::file_size(argv[1]);
    const std::uintmax_t fixed_size =
        sizeof(InputHeader) + dl::kLatticeCellCount * sizeof(ComplexInterval);
    if (file_size < fixed_size ||
        header.item_count > (file_size - fixed_size) / sizeof(InputItem) ||
        fixed_size + header.item_count * sizeof(InputItem) != file_size) {
      throw std::runtime_error("noncanonical input file length");
    }
    const auto lattice = read_array<ComplexInterval>(
        input, header.lattice_cell_count, "lattice cells");
    const auto requests =
        read_array<InputItem>(input, header.item_count, "residue requests");
    char trailing = 0;
    if (input.read(&trailing, 1)) throw std::runtime_error("trailing input bytes");
    if (!input.eof()) throw std::runtime_error("input read failed");
    validate_input(header, lattice, requests);

    ComplexInterval* device_lattice = nullptr;
    InputItem* device_requests = nullptr;
    OutputItem* device_results = nullptr;
    CUDA_CHECK(cudaMalloc(&device_lattice,
                          lattice.size() * sizeof(ComplexInterval)));
    CUDA_CHECK(cudaMalloc(&device_requests,
                          requests.size() * sizeof(InputItem)));
    CUDA_CHECK(cudaMalloc(&device_results,
                          requests.size() * sizeof(OutputItem)));
    CUDA_CHECK(cudaMemcpy(device_lattice, lattice.data(),
                          lattice.size() * sizeof(ComplexInterval),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_requests, requests.data(),
                          requests.size() * sizeof(InputItem),
                          cudaMemcpyHostToDevice));

    constexpr unsigned int threads = 256;
    const std::uint64_t blocks64 =
        (header.item_count + threads - 1U) / threads;
    if (blocks64 > std::numeric_limits<unsigned int>::max()) {
      throw std::runtime_error("one batch exceeds CUDA grid capacity");
    }
    const unsigned int blocks = static_cast<unsigned int>(blocks64);
    cudaEvent_t start{};
    cudaEvent_t stop{};
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    for (int iteration = 0; iteration < iterations; ++iteration) {
      taylor_reconstruct_kernel<<<blocks, threads>>>(
          header, device_lattice, device_requests, device_results);
      CUDA_CHECK(cudaGetLastError());
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));

    std::vector<OutputItem> results(requests.size());
    CUDA_CHECK(cudaMemcpy(results.data(), device_results,
                          results.size() * sizeof(OutputItem),
                          cudaMemcpyDeviceToHost));
    std::uint32_t status_or = 0;
    for (const OutputItem& result : results) status_or |= result.status;
    if (status_or != 0) throw std::runtime_error("kernel emitted invalid interval");

    const auto elapsed_ns = static_cast<std::uint64_t>(
        std::ceil(static_cast<double>(elapsed_ms) * 1000000.0));
    OutputHeader output_header{};
    std::memcpy(output_header.magic, dl::kOutputMagic,
                sizeof(output_header.magic));
    output_header.version = dl::kFormatVersion;
    output_header.lattice_rows = dl::kLatticeRows;
    output_header.taylor_degree = dl::kTaylorDegree;
    output_header.item_count = header.item_count;
    output_header.elapsed_nanoseconds = elapsed_ns;
    write_output_atomic(argv[2], output_header, results);

    const long double evaluated_items =
        static_cast<long double>(header.item_count) * iterations;
    const long double seconds = static_cast<long double>(elapsed_ms) / 1000.0L;
    const long double items_per_second = seconds > 0 ? evaluated_items / seconds : 0;
    const long double terms_per_second =
        items_per_second * dl::kTaylorColumns;
    std::printf(
        "{\"algorithm\":\"platt-dirichlet-large-q-lattice-taylor-stage-v1\","
        "\"conditional_stage_only\":true,\"device\":\"%s\","
        "\"item_count\":%llu,\"iterations\":%d,\"kernel_ms\":%.6f,"
        "\"items_per_second\":%.6Le,\"taylor_terms_per_second\":%.6Le,"
        "\"status_or\":%u}\n",
        properties.name, static_cast<unsigned long long>(header.item_count),
        iterations, elapsed_ms, items_per_second, terms_per_second, status_or);

    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    cudaFree(device_lattice);
    cudaFree(device_requests);
    cudaFree(device_results);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "dirichlet lattice runner: %s\n", error.what());
    return 1;
  }
}
