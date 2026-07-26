// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// GPU expansion of the authenticated finite-recovery recurrence seeds.  The
// device evaluates no transcendental function: it uses directed binary64
// rectangle multiplication and exponentiation on Arb-certified phase steps.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_dirichlet_recovery_seeds.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <unistd.h>
#include <vector>

namespace rs = sparkinterval::tg::dirichlet_recovery_seeds;
namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

using dl::ComplexInterval;
using dl::RealInterval;

static_assert(std::endian::native == std::endian::little,
              "the authenticated artifact is little-endian");

constexpr char kChunkDomain[] =
    "sparkinterval/dirichlet-recovery-seed-chunk/v1";
constexpr char kRootDomain[] =
    "sparkinterval/dirichlet-recovery-seed-root/v1";

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

__device__ __forceinline__ RealInterval add(RealInterval x, RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
  const double dl0 = __dmul_rd(x.lo, y.lo);
  const double dl1 = __dmul_rd(x.lo, y.hi);
  const double dl2 = __dmul_rd(x.hi, y.lo);
  const double dl3 = __dmul_rd(x.hi, y.hi);
  const double du0 = __dmul_ru(x.lo, y.lo);
  const double du1 = __dmul_ru(x.lo, y.hi);
  const double du2 = __dmul_ru(x.hi, y.lo);
  const double du3 = __dmul_ru(x.hi, y.hi);
  return {fmin(fmin(dl0, dl1), fmin(dl2, dl3)),
          fmax(fmax(du0, du1), fmax(du2, du3))};
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

__device__ __forceinline__ ComplexInterval cpow(ComplexInterval base,
                                                 std::uint64_t exponent) {
  ComplexInterval answer{{1.0, 1.0}, {0.0, 0.0}};
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) answer = cmul(answer, base);
    exponent >>= 1U;
    if (exponent != 0U) base = cmul(base, base);
  }
  return answer;
}

__global__ void expandRecoveryKernel(const rs::SeedRecord* seeds,
                                     const std::uint32_t* residues,
                                     std::uint32_t q,
                                     std::uint64_t groupOrder,
                                     std::uint64_t firstTIndex,
                                     std::uint64_t valueCount,
                                     ComplexInterval* output) {
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * gridDim.x;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < valueCount; flat += stride) {
    const std::uint64_t frame = flat / groupOrder;
    const std::uint64_t position = flat % groupOrder;
    const std::uint32_t a = residues[position];
    const std::uint64_t tIndex = firstTIndex + frame;
    ComplexInterval sum{{0.0, 0.0}, {0.0, 0.0}};
#pragma unroll
    for (std::uint32_t n = 0; n <= rs::kSourceM; ++n) {
      const std::uint64_t x = static_cast<std::uint64_t>(q) * n + a;
      const rs::SeedRecord seed = seeds[x - rs::kSourceXStart];
      ComplexInterval term = cpow(seed.phase_step, tIndex);
      const RealInterval amplitude{seed.amplitude_lo, seed.amplitude_hi};
      term.re = mul(term.re, amplitude);
      term.im = mul(term.im, amplitude);
      sum = cadd(sum, term);
    }
    output[flat] = sum;
  }
}

bool finiteOrdered(const RealInterval& value) {
  return std::isfinite(value.lo) && std::isfinite(value.hi) &&
         value.lo <= value.hi;
}

bool finiteOrdered(const ComplexInterval& value) {
  return finiteOrdered(value.re) && finiteOrdered(value.im);
}

std::uint64_t parseUnsigned(const char* text, const char* label) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  errno = 0;
  char* end = nullptr;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == nullptr || *end != '\0') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<std::uint64_t>(value);
}

std::array<unsigned char, 32> parseDigest(std::string_view text) {
  if (text.size() != 64U) throw std::runtime_error("expected SHA-256 is malformed");
  std::array<unsigned char, 32> answer{};
  auto digit = [](char value) -> unsigned int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    throw std::runtime_error("expected SHA-256 is not lowercase hexadecimal");
  };
  for (std::size_t index = 0; index < answer.size(); ++index) {
    answer[index] = static_cast<unsigned char>(
        (digit(text[2U * index]) << 4U) | digit(text[2U * index + 1U]));
  }
  return answer;
}

template <typename T>
void readExact(std::istream& input, T* value, const char* label) {
  input.read(reinterpret_cast<char*>(value), sizeof(T));
  if (!input) throw std::runtime_error(std::string("short ") + label);
}

void readExactBytes(std::istream& input, void* destination, std::size_t size,
                    const char* label) {
  if (size > static_cast<std::size_t>(
                 std::numeric_limits<std::streamsize>::max())) {
    throw std::runtime_error(std::string(label) + " is too large");
  }
  input.read(static_cast<char*>(destination),
             static_cast<std::streamsize>(size));
  if (!input) throw std::runtime_error(std::string("short ") + label);
}

sparkinterval::Sha256Digest hashFile(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open seed artifact");
  sparkinterval::detail::Sha256 digest;
  std::array<char, 1U << 20U> buffer{};
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const auto count = input.gcount();
    if (count > 0) digest.update(buffer.data(), static_cast<std::size_t>(count));
  }
  if (!input.eof()) throw std::runtime_error("cannot hash seed artifact");
  return digest.finish();
}

struct LoadedSeeds {
  rs::Header header{};
  std::vector<rs::SeedRecord> records;
  std::uint64_t chunkCount = 0;
  std::string artifactSha256;
};

LoadedSeeds loadSeeds(const std::filesystem::path& path,
                      const std::array<unsigned char, 32>& expectedSha,
                      bool allowPrefixKat) {
  const auto actualSha = hashFile(path);
  if (actualSha != expectedSha) {
    throw std::runtime_error("seed artifact SHA-256 differs before parsing");
  }
  std::ifstream input(path, std::ios::binary);
  LoadedSeeds loaded;
  readExact(input, &loaded.header, "seed header");
  const auto& header = loaded.header;
  if (std::memcmp(header.magic, rs::kHeaderMagic, 8) != 0 ||
      header.version != rs::kFormatVersion || header.m != rs::kSourceM ||
      header.maximum_q != rs::kSourceMaximumQ ||
      header.record_size != sizeof(rs::SeedRecord) ||
      header.x_start != rs::kSourceXStart ||
      header.x_stop < header.x_start || header.x_stop > rs::kSourceXStop ||
      header.t_step_numerator != rs::kSourceStepNumerator ||
      header.t_denominator != rs::kSourceStepDenominator ||
      header.record_count != header.x_stop - header.x_start + 1U ||
      header.generation_precision_bits < 128U ||
      header.union_precision_bits != header.generation_precision_bits + 64U ||
      header.chunk_records == 0U ||
      header.chunk_records > rs::kMaximumChunkRecords || header.reserved0 != 0U ||
      header.reserved1 != 0U) {
    throw std::runtime_error("seed header or exact source geometry differs");
  }
  if (!allowPrefixKat && header.x_stop != rs::kSourceXStop) {
    throw std::runtime_error("production expansion requires the full seed range");
  }
  loaded.records.reserve(static_cast<std::size_t>(header.record_count));
  sparkinterval::detail::Sha256 recordsDigest;
  sparkinterval::detail::Sha256 rootDigest;
  rootDigest.update(kRootDomain, sizeof(kRootDomain));
  std::uint64_t remaining = header.record_count;
  std::uint64_t expectedX = header.x_start;
  while (remaining != 0U) {
    rs::ChunkHeader chunk{};
    readExact(input, &chunk, "seed chunk header");
    const std::uint64_t expectedCount =
        std::min<std::uint64_t>(header.chunk_records, remaining);
    if (std::memcmp(chunk.magic, rs::kChunkMagic, 8) != 0 ||
        chunk.version != rs::kFormatVersion || chunk.reserved != 0U ||
        chunk.first_x != expectedX || chunk.record_count != expectedCount) {
      throw std::runtime_error("seed chunk ordering or size differs");
    }
    std::vector<rs::SeedRecord> records(static_cast<std::size_t>(chunk.record_count));
    readExactBytes(input, records.data(), records.size() * sizeof(records[0]),
                   "seed chunk payload");
    sparkinterval::detail::Sha256 chunkDigest;
    chunkDigest.update(kChunkDomain, sizeof(kChunkDomain));
    chunkDigest.update(&chunk.first_x, sizeof(chunk.first_x));
    chunkDigest.update(&chunk.record_count, sizeof(chunk.record_count));
    chunkDigest.update(records.data(), records.size() * sizeof(records[0]));
    const auto actualChunk = chunkDigest.finish();
    if (!std::equal(actualChunk.begin(), actualChunk.end(),
                    chunk.payload_sha256)) {
      throw std::runtime_error("seed chunk SHA-256 differs");
    }
    // No record from this chunk is retained until its complete hash passes.
    for (const auto& record : records) {
      if (!std::isfinite(record.amplitude_lo) ||
          !std::isfinite(record.amplitude_hi) || record.amplitude_lo <= 0.0 ||
          record.amplitude_lo > record.amplitude_hi ||
          record.amplitude_hi > 1.0 || !finiteOrdered(record.phase_step) ||
          record.phase_step.re.lo < -1.0 || record.phase_step.re.hi > 1.0 ||
          record.phase_step.im.lo < -1.0 || record.phase_step.im.hi > 1.0) {
        throw std::runtime_error("seed record is not a finite outward interval");
      }
    }
    recordsDigest.update(records.data(), records.size() * sizeof(records[0]));
    rootDigest.update(actualChunk.data(), actualChunk.size());
    loaded.records.insert(loaded.records.end(), records.begin(), records.end());
    expectedX += chunk.record_count;
    remaining -= chunk.record_count;
    ++loaded.chunkCount;
  }
  rs::Footer footer{};
  readExact(input, &footer, "seed footer");
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes after seed footer");
  }
  const auto actualRecords = recordsDigest.finish();
  const auto actualRoot = rootDigest.finish();
  if (std::memcmp(footer.magic, rs::kFooterMagic, 8) != 0 ||
      footer.version != rs::kFormatVersion || footer.reserved != 0U ||
      footer.record_count != header.record_count ||
      footer.chunk_count != loaded.chunkCount ||
      !std::equal(actualRecords.begin(), actualRecords.end(),
                  footer.records_sha256) ||
      !std::equal(actualRoot.begin(), actualRoot.end(),
                  footer.chunk_root_sha256)) {
    throw std::runtime_error("seed footer or global digest differs");
  }
  loaded.artifactSha256 = sparkinterval::lowercase_hex(actualSha);
  return loaded;
}

std::uint64_t maximumTIndex(std::uint32_t q) {
  const std::uint64_t additive =
      (q % 2U == 0U) ? 75000000ULL : 37500000ULL;
  const std::uint64_t heightNumerator =
      std::max<std::uint64_t>(100000000ULL, 200ULL * q + additive);
  return heightNumerator * rs::kSourceStepDenominator /
         (static_cast<std::uint64_t>(q) * rs::kSourceStepNumerator);
}

std::vector<std::uint32_t> unitResidues(std::uint32_t q) {
  std::vector<std::uint32_t> result;
  for (std::uint32_t a = 1U; a < q; ++a) {
    if (std::gcd(a, q) == 1U) result.push_back(a);
  }
  if (result.empty()) throw std::runtime_error("modulus has no unit residues");
  return result;
}

void selectDevice(std::uint32_t device) {
  int count = 0;
  CUDA_CHECK(cudaGetDeviceCount(&count));
  if (device >= static_cast<std::uint32_t>(count)) {
    throw std::runtime_error("CUDA device is out of range");
  }
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error(
        "strict production runner requires H100 compute capability 9.0");
  }
#endif
  if (properties.major < 6) {
    throw std::runtime_error("directed binary64 CUDA arithmetic is unavailable");
  }
}

std::uint32_t blocksFor(std::uint64_t count) {
  constexpr std::uint32_t kThreads = 256U;
  return static_cast<std::uint32_t>(std::min<std::uint64_t>(
      65535U, std::max<std::uint64_t>(1U, (count + kThreads - 1U) / kThreads)));
}

struct DeviceBuffer {
  rs::SeedRecord* seeds = nullptr;
  std::uint32_t* residues = nullptr;
  ComplexInterval* output = nullptr;
  ~DeviceBuffer() {
    cudaFree(output);
    cudaFree(residues);
    cudaFree(seeds);
  }
};

std::uint64_t runKernel(const LoadedSeeds& loaded,
                        const std::vector<std::uint32_t>& residues,
                        std::uint32_t q, std::uint64_t firstTIndex,
                        std::uint32_t batchCount, std::uint32_t repetitions,
                        std::vector<ComplexInterval>* output) {
  const std::uint64_t valueCount =
      static_cast<std::uint64_t>(residues.size()) * batchCount;
  DeviceBuffer device;
  CUDA_CHECK(cudaMalloc(&device.seeds,
                        loaded.records.size() * sizeof(loaded.records[0])));
  CUDA_CHECK(cudaMalloc(&device.residues,
                        residues.size() * sizeof(residues[0])));
  CUDA_CHECK(cudaMalloc(&device.output, valueCount * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMemcpy(device.seeds, loaded.records.data(),
                        loaded.records.size() * sizeof(loaded.records[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device.residues, residues.data(),
                        residues.size() * sizeof(residues[0]),
                        cudaMemcpyHostToDevice));
  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  constexpr std::uint32_t kThreads = 256U;
  for (std::uint32_t repetition = 0; repetition < repetitions; ++repetition) {
    expandRecoveryKernel<<<blocksFor(valueCount), kThreads>>>(
        device.seeds, device.residues, q, residues.size(), firstTIndex,
        valueCount, device.output);
    CUDA_CHECK(cudaGetLastError());
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&milliseconds, start, stop));
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
  output->resize(static_cast<std::size_t>(valueCount));
  CUDA_CHECK(cudaMemcpy(output->data(), device.output,
                        output->size() * sizeof((*output)[0]),
                        cudaMemcpyDeviceToHost));
  if (!std::all_of(output->begin(), output->end(),
                   [](const ComplexInterval& value) {
                     return finiteOrdered(value);
                   })) {
    throw std::runtime_error("GPU recovery output contains malformed intervals");
  }
  return static_cast<std::uint64_t>(static_cast<double>(milliseconds) * 1.0e6);
}

void writeOutput(const std::filesystem::path& path, std::uint32_t q,
                 std::uint64_t firstTIndex, std::uint32_t batchCount,
                 std::uint64_t groupOrder,
                 const std::vector<ComplexInterval>& values) {
  if (std::filesystem::exists(path)) {
    throw std::runtime_error("refusing to replace immutable recovery output");
  }
  rs::OutputHeader header{};
  std::memcpy(header.magic, rs::kOutputMagic, 8);
  header.version = rs::kFormatVersion;
  header.q = q;
  header.m = rs::kSourceM;
  header.batch_count = batchCount;
  header.group_order = groupOrder;
  header.first_t_index = firstTIndex;
  header.t_step_numerator = rs::kSourceStepNumerator;
  header.t_denominator = rs::kSourceStepDenominator;
  header.value_count = values.size();
  const auto temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create recovery output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    output.write(reinterpret_cast<const char*>(values.data()),
                 static_cast<std::streamsize>(values.size() * sizeof(values[0])));
    output.flush();
    if (!output) throw std::runtime_error("cannot write recovery output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish recovery output: " + error.message());
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const bool allowPrefixKat =
        argc == 10 && std::string_view(argv[9]) == "--allow-prefix-kat";
    if (argc != 9 && !allowPrefixKat) {
      throw std::runtime_error(
          "usage: runner SEEDS.bin EXPECTED_SHA256 Q FIRST_T_INDEX "
          "BATCH_COUNT OUTPUT.bin DEVICE REPETITIONS [--allow-prefix-kat]");
    }
    const auto expectedSha = parseDigest(argv[2]);
    const std::uint64_t rawQ = parseUnsigned(argv[3], "q");
    const std::uint64_t firstTIndex = parseUnsigned(argv[4], "first t index");
    const std::uint64_t rawBatch = parseUnsigned(argv[5], "batch count");
    const std::uint64_t rawDevice = parseUnsigned(argv[7], "device");
    const std::uint64_t rawRepetitions = parseUnsigned(argv[8], "repetitions");
    if (rawQ < 10001U || rawQ > rs::kSourceMaximumQ || rawBatch == 0U ||
        rawBatch > 64U || rawDevice > std::numeric_limits<std::uint32_t>::max() ||
        rawRepetitions == 0U ||
        rawRepetitions > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("q, batch, device, or repetitions are invalid");
    }
    const auto q = static_cast<std::uint32_t>(rawQ);
    const auto batchCount = static_cast<std::uint32_t>(rawBatch);
    if (firstTIndex + batchCount - 1U > maximumTIndex(q)) {
      throw std::runtime_error("recovery batch extends beyond source height");
    }
    const LoadedSeeds loaded = loadSeeds(argv[1], expectedSha, allowPrefixKat);
    const std::uint64_t requiredX =
        static_cast<std::uint64_t>(rs::kSourceM) * q + q - 1U;
    if (loaded.header.x_stop < requiredX) {
      throw std::runtime_error("seed artifact does not cover this q");
    }
    selectDevice(static_cast<std::uint32_t>(rawDevice));
    const auto residues = unitResidues(q);
    std::vector<ComplexInterval> output;
    const auto elapsed = runKernel(
        loaded, residues, q, firstTIndex, batchCount,
        static_cast<std::uint32_t>(rawRepetitions), &output);
    writeOutput(argv[6], q, firstTIndex, batchCount, residues.size(), output);
    const double seconds = static_cast<double>(elapsed) / 1.0e9;
    const double rate = static_cast<double>(output.size()) * rawRepetitions /
                        seconds;
    double maximumWidth = 0.0;
    long double widthSum = 0.0L;
    for (const auto& value : output) {
      const double width = std::max(value.re.hi - value.re.lo,
                                    value.im.hi - value.im.lo);
      maximumWidth = std::max(maximumWidth, width);
      widthSum += width;
    }
    const auto outputSha = hashFile(argv[6]);
    std::cout
        << "{\"algorithm\":\"platt-dirichlet-finite-recovery-seeded-cuda-v1\""
        << ",\"artifact_sha256\":\"" << loaded.artifactSha256 << "\""
        << ",\"batch_count\":" << batchCount
        << ",\"classification\":\"directed_cuda_recurrence_component_not_theorem_7_1\""
        << ",\"device\":" << rawDevice
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"first_t_index\":" << firstTIndex
        << ",\"group_order\":" << residues.size()
        << ",\"maximum_component_width\":" << std::setprecision(17)
        << maximumWidth
        << ",\"mean_max_component_width\":" << std::setprecision(17)
        << static_cast<double>(widthSum / output.size())
        << ",\"output_sha256\":\""
        << sparkinterval::lowercase_hex(outputSha) << "\""
        << ",\"q\":" << q
        << ",\"recurrence_widths_proved_sufficient_for_zero_isolation\":false"
        << ",\"repetitions\":" << rawRepetitions
        << ",\"seed_chunks_authenticated_before_gpu_use\":"
        << loaded.chunkCount
        << ",\"transcendental_device_calls\":0"
        << ",\"value_count\":" << output.size()
        << ",\"values_per_second\":" << std::setprecision(17) << rate
        << "}\n";
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_recovery_seeded: %s\n", error.what());
    return 1;
  }
}
