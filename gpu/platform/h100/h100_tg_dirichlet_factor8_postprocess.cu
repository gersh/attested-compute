// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_dirichlet_factor8_postprocess.cuh"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace factor8 =
    sparkinterval::tg::dirichlet_factor8_postprocess;

namespace {

constexpr std::array<char, 8> kCoefficientMagic = {
    'T', 'G', 'D', 'F', '8', 'C', 'F', '1'};
constexpr std::array<char, 8> kInputMagic = {
    'T', 'G', 'D', 'F', '8', 'I', 'N', '1'};
constexpr std::array<char, 8> kOutputMagic = {
    'T', 'G', 'D', 'F', '8', 'S', 'G', '1'};
constexpr std::uint32_t kFormatVersion = 1U;
constexpr std::uint64_t kMaximumItems = 1ULL << 28U;
constexpr std::size_t kMaximumArtifactBytes =
    static_cast<std::size_t>(kMaximumItems) * sizeof(factor8::Interval) +
    4096U;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

#pragma pack(push, 1)
struct CoefficientHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t factor;
  std::uint32_t truncation;
  std::uint32_t tap_count;
  std::int32_t bandwidth_numerator;
  std::int32_t bandwidth_denominator;
  std::int32_t gaussian_h_numerator;
  std::int32_t gaussian_h_denominator;
  std::int32_t first_tap_offset;
  std::int32_t last_tap_offset;
  unsigned char payload_sha256[32];
};

struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t conrey_number;
  std::uint32_t parity;
  std::int64_t first_base_index;
  std::uint64_t base_count;
  std::int64_t first_fine_index;
  std::uint64_t output_count;
  double interpolation_error_upper;
  unsigned char coefficient_artifact_sha256[32];
  unsigned char upstream_sha256[32];
  unsigned char payload_sha256[32];
};

struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t conrey_number;
  std::uint32_t parity;
  std::int64_t first_fine_index;
  std::uint64_t output_count;
  std::uint64_t negative_count;
  std::uint64_t ambiguous_count;
  std::uint64_t positive_count;
  std::uint64_t adjacent_opposite_sign_count;
  std::uint32_t device_error_or;
  std::uint32_t reserved;
  unsigned char coefficient_artifact_sha256[32];
  unsigned char input_artifact_sha256[32];
  unsigned char payload_sha256[32];
};
#pragma pack(pop)

static_assert(std::endian::native == std::endian::little);
static_assert(sizeof(CoefficientHeader) == 80U);
static_assert(sizeof(InputHeader) == 160U);
static_assert(sizeof(OutputHeader) == 176U);

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

bool sameMagic(const char* observed, const std::array<char, 8>& expected) {
  return std::memcmp(observed, expected.data(), expected.size()) == 0;
}

bool sameDigest(const unsigned char* left,
                const sparkinterval::Sha256Digest& right) {
  return std::equal(right.begin(), right.end(), left);
}

void copyDigest(unsigned char* destination,
                const sparkinterval::Sha256Digest& source) {
  std::copy(source.begin(), source.end(), destination);
}

std::vector<unsigned char> readFile(const std::filesystem::path& path,
                                    std::size_t maximumBytes) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) fail("cannot open input artifact: " + path.string());
  const std::streamoff end = input.tellg();
  if (end < 0 || static_cast<std::uint64_t>(end) > maximumBytes) {
    fail("input artifact exceeds its fixed byte bound");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(end));
  input.seekg(0);
  if (!raw.empty()) {
    input.read(reinterpret_cast<char*>(raw.data()),
               static_cast<std::streamsize>(raw.size()));
  }
  if (!input || input.peek() != std::ifstream::traits_type::eof()) {
    fail("input artifact read failed or has trailing bytes");
  }
  return raw;
}

void writeFileAtomically(const std::filesystem::path& path,
                         const void* header, std::size_t headerBytes,
                         const std::vector<unsigned char>& payload) {
  const auto temporary = path.string() + ".tmp";
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) fail("cannot create temporary output artifact");
    output.write(static_cast<const char*>(header),
                 static_cast<std::streamsize>(headerBytes));
    if (!payload.empty()) {
      output.write(reinterpret_cast<const char*>(payload.data()),
                   static_cast<std::streamsize>(payload.size()));
    }
    output.flush();
    if (!output) fail("cannot write output artifact");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    fail("cannot publish output artifact atomically: " + error.message());
  }
}

std::uint32_t parseRepeats(std::string_view value) {
  if (value.empty()) fail("benchmark repeat count is empty");
  std::uint64_t result = 0;
  for (const char character : value) {
    if (character < '0' || character > '9') {
      fail("benchmark repeat count is not decimal");
    }
    result = result * 10U + static_cast<unsigned>(character - '0');
    if (result > 10000U) fail("benchmark repeat count exceeds 10000");
  }
  if (result == 0U) fail("benchmark repeat count must be positive");
  return static_cast<std::uint32_t>(result);
}

bool hostValidInterval(const factor8::Interval& interval) {
  return std::isfinite(interval.lower) && std::isfinite(interval.upper) &&
         interval.lower <= interval.upper;
}

std::pair<std::int64_t, std::int64_t> requiredSourceRange(
    std::int64_t firstFine, std::uint64_t outputCount) {
  const std::int64_t lastFine =
      firstFine + static_cast<std::int64_t>(outputCount - 1U);
  return {
      firstFine / factor8::kUpsampleFactor + factor8::kFirstTapOffset,
      lastFine / factor8::kUpsampleFactor + factor8::kLastTapOffset,
  };
}

struct DeviceMemory {
  factor8::Interval* source = nullptr;
  factor8::Interval* coefficients = nullptr;
  unsigned char* codes = nullptr;
  unsigned char* packed = nullptr;
  factor8::DeviceSummary* summary = nullptr;

  ~DeviceMemory() {
    cudaFree(summary);
    cudaFree(packed);
    cudaFree(codes);
    cudaFree(coefficients);
    cudaFree(source);
  }
};

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 4 || argc > 6) {
      fail("usage: tg-dirichlet-factor8-postprocess COEFFICIENTS INPUT OUTPUT "
           "[BENCHMARK_REPEATS] [--four-corner]");
    }
    const std::filesystem::path coefficientPath = argv[1];
    const std::filesystem::path inputPath = argv[2];
    const std::filesystem::path outputPath = argv[3];
    if (std::filesystem::weakly_canonical(outputPath) ==
            std::filesystem::weakly_canonical(coefficientPath) ||
        std::filesystem::weakly_canonical(outputPath) ==
            std::filesystem::weakly_canonical(inputPath)) {
      fail("output artifact must not alias an input artifact");
    }
    const std::uint32_t repeats =
        argc >= 5 ? parseRepeats(argv[4]) : 1U;
    const bool fourCorner =
        argc == 6 && std::string_view(argv[5]) == "--four-corner";
    if (argc == 6 && !fourCorner) {
      fail("the optional arithmetic mode must be exactly --four-corner");
    }
    CUDA_CHECK(cudaSetDevice(0));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));
    if (properties.major != 9 || properties.minor != 0 ||
        std::strstr(properties.name, "H100") == nullptr) {
      fail("strict production runner requires an H100 with compute capability 9.0");
    }
#endif

    const auto coefficientRaw =
        readFile(coefficientPath, sizeof(CoefficientHeader) +
                                      factor8::kInterpolatedPhaseCount *
                                          factor8::kTapCount *
                                          sizeof(factor8::Interval));
    if (coefficientRaw.size() !=
        sizeof(CoefficientHeader) +
            factor8::kInterpolatedPhaseCount * factor8::kTapCount *
                sizeof(factor8::Interval)) {
      fail("coefficient artifact length differs");
    }
    CoefficientHeader coefficientHeader{};
    std::memcpy(&coefficientHeader, coefficientRaw.data(),
                sizeof(coefficientHeader));
    if (!sameMagic(coefficientHeader.magic, kCoefficientMagic) ||
        coefficientHeader.version != kFormatVersion ||
        coefficientHeader.factor != factor8::kUpsampleFactor ||
        coefficientHeader.truncation != factor8::kTruncation ||
        coefficientHeader.tap_count != factor8::kTapCount ||
        coefficientHeader.bandwidth_numerator != 32 ||
        coefficientHeader.bandwidth_denominator != 5 ||
        coefficientHeader.gaussian_h_numerator != 7 ||
        coefficientHeader.gaussian_h_denominator != 32 ||
        coefficientHeader.first_tap_offset != factor8::kFirstTapOffset ||
        coefficientHeader.last_tap_offset != factor8::kLastTapOffset) {
      fail("coefficient artifact header differs");
    }
    const unsigned char* coefficientPayload =
        coefficientRaw.data() + sizeof(CoefficientHeader);
    const std::size_t coefficientPayloadBytes =
        coefficientRaw.size() - sizeof(CoefficientHeader);
    const auto coefficientPayloadDigest =
        sparkinterval::sha256(coefficientPayload, coefficientPayloadBytes);
    if (!sameDigest(coefficientHeader.payload_sha256,
                    coefficientPayloadDigest)) {
      fail("coefficient artifact payload digest differs");
    }
    const auto* coefficients =
        reinterpret_cast<const factor8::Interval*>(coefficientPayload);
    for (std::size_t index = 0;
         index < factor8::kInterpolatedPhaseCount * factor8::kTapCount;
         ++index) {
      if (!hostValidInterval(coefficients[index]) ||
          !(coefficients[index].lower > 0.0 ||
            coefficients[index].upper < 0.0)) {
        fail("coefficient artifact contains an invalid or zero-crossing interval");
      }
    }
    const auto coefficientArtifactDigest =
        sparkinterval::sha256(coefficientRaw.data(), coefficientRaw.size());

    const auto inputRaw = readFile(inputPath, kMaximumArtifactBytes);
    if (inputRaw.size() < sizeof(InputHeader)) {
      fail("input artifact header is truncated");
    }
    InputHeader inputHeader{};
    std::memcpy(&inputHeader, inputRaw.data(), sizeof(inputHeader));
    if (!sameMagic(inputHeader.magic, kInputMagic) ||
        inputHeader.version != kFormatVersion || inputHeader.q < 2U ||
        inputHeader.conrey_number == 0U ||
        inputHeader.conrey_number >= inputHeader.q ||
        inputHeader.parity > 1U ||
        inputHeader.first_base_index < 0 ||
        inputHeader.first_fine_index < 0 ||
        inputHeader.base_count == 0U ||
        inputHeader.output_count == 0U ||
        inputHeader.base_count > kMaximumItems ||
        inputHeader.output_count > kMaximumItems ||
        !std::isfinite(inputHeader.interpolation_error_upper) ||
        inputHeader.interpolation_error_upper <
            factor8::kMinimumInterpolationErrorUpper ||
        inputHeader.first_fine_index >
            std::numeric_limits<std::int64_t>::max() -
                static_cast<std::int64_t>(inputHeader.output_count - 1U)) {
      fail("input artifact header/domain differs");
    }
    if (!sameDigest(inputHeader.coefficient_artifact_sha256,
                    coefficientArtifactDigest)) {
      fail("input artifact binds a different coefficient artifact");
    }
    if (inputHeader.base_count >
        (std::numeric_limits<std::size_t>::max() - sizeof(InputHeader)) /
            sizeof(factor8::Interval)) {
      fail("input artifact byte length overflows size_t");
    }
    const std::size_t expectedInputBytes =
        sizeof(InputHeader) +
        static_cast<std::size_t>(inputHeader.base_count) *
            sizeof(factor8::Interval);
    if (inputRaw.size() != expectedInputBytes) {
      fail("input artifact length or trailing bytes differ");
    }
    const unsigned char* inputPayload = inputRaw.data() + sizeof(InputHeader);
    const std::size_t inputPayloadBytes = inputRaw.size() - sizeof(InputHeader);
    const auto inputPayloadDigest =
        sparkinterval::sha256(inputPayload, inputPayloadBytes);
    if (!sameDigest(inputHeader.payload_sha256, inputPayloadDigest)) {
      fail("input artifact payload digest differs");
    }
    const auto* source =
        reinterpret_cast<const factor8::Interval*>(inputPayload);
    for (std::uint64_t index = 0; index < inputHeader.base_count; ++index) {
      if (!hostValidInterval(source[index])) {
        fail("input artifact contains an invalid interval");
      }
    }
    const auto required = requiredSourceRange(
        inputHeader.first_fine_index, inputHeader.output_count);
    if (required.first < inputHeader.first_base_index ||
        required.second < required.first ||
        static_cast<std::uint64_t>(
            required.second - inputHeader.first_base_index) >=
            inputHeader.base_count) {
      fail("output interpolation window lies outside the input shard");
    }

    const std::uint64_t packedBytes =
        (inputHeader.output_count + 3U) / 4U;
    DeviceMemory device;
    CUDA_CHECK(cudaMalloc(&device.source, inputPayloadBytes));
    CUDA_CHECK(cudaMalloc(&device.coefficients, coefficientPayloadBytes));
    CUDA_CHECK(cudaMalloc(&device.codes,
                          static_cast<std::size_t>(inputHeader.output_count)));
    CUDA_CHECK(cudaMalloc(&device.packed,
                          static_cast<std::size_t>(packedBytes)));
    CUDA_CHECK(cudaMalloc(&device.summary, sizeof(factor8::DeviceSummary)));
    CUDA_CHECK(cudaMemcpy(device.source, source, inputPayloadBytes,
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device.coefficients, coefficients,
                          coefficientPayloadBytes, cudaMemcpyHostToDevice));

    constexpr unsigned threads = factor8::kConvolutionThreads;
    const unsigned outputBlocks = static_cast<unsigned>(
        (inputHeader.output_count + threads - 1U) / threads);
    const unsigned packedBlocks = static_cast<unsigned>(
        std::min<std::uint64_t>(65535U, (packedBytes + threads - 1U) / threads));
    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    for (std::uint32_t repeat = 0U; repeat < repeats; ++repeat) {
      CUDA_CHECK(
          cudaMemset(device.summary, 0, sizeof(factor8::DeviceSummary)));
      if (fourCorner) {
        factor8::interpolateAndClassify<false><<<outputBlocks, threads>>>(
            device.source, inputHeader.first_base_index,
            inputHeader.base_count, device.coefficients,
            inputHeader.first_fine_index, inputHeader.output_count,
            inputHeader.interpolation_error_upper, device.codes,
            device.summary);
      } else {
        factor8::interpolateAndClassify<true><<<outputBlocks, threads>>>(
            device.source, inputHeader.first_base_index,
            inputHeader.base_count, device.coefficients,
            inputHeader.first_fine_index, inputHeader.output_count,
            inputHeader.interpolation_error_upper, device.codes,
            device.summary);
      }
      CUDA_CHECK(cudaGetLastError());
      factor8::countAdjacentOppositeSigns<<<outputBlocks, threads>>>(
          device.codes, inputHeader.output_count, device.summary);
      CUDA_CHECK(cudaGetLastError());
      factor8::packCodes<<<packedBlocks, threads>>>(
          device.codes, inputHeader.output_count, device.packed);
      CUDA_CHECK(cudaGetLastError());
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsedMilliseconds = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsedMilliseconds, start, stop));
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaEventDestroy(start));

    factor8::DeviceSummary summary{};
    CUDA_CHECK(cudaMemcpy(&summary, device.summary, sizeof(summary),
                          cudaMemcpyDeviceToHost));
    std::vector<unsigned char> packed(static_cast<std::size_t>(packedBytes));
    CUDA_CHECK(cudaMemcpy(packed.data(), device.packed, packed.size(),
                          cudaMemcpyDeviceToHost));
    if (summary.error_or != factor8::kSuccess ||
        summary.reserved != 0U ||
        summary.negative_count + summary.ambiguous_count +
                summary.positive_count !=
            inputHeader.output_count) {
      fail("device factor-eight summary failed closed");
    }
    if ((inputHeader.output_count & 3U) != 0U) {
      const unsigned used = static_cast<unsigned>(
          2U * (inputHeader.output_count & 3U));
      if ((packed.back() >> used) != 0U) {
        fail("device factor-eight unused packed lanes are nonzero");
      }
    }

    const auto inputArtifactDigest =
        sparkinterval::sha256(inputRaw.data(), inputRaw.size());
    const auto outputPayloadDigest =
        sparkinterval::sha256(packed.data(), packed.size());
    OutputHeader outputHeader{};
    std::copy(kOutputMagic.begin(), kOutputMagic.end(), outputHeader.magic);
    outputHeader.version = kFormatVersion;
    outputHeader.q = inputHeader.q;
    outputHeader.conrey_number = inputHeader.conrey_number;
    outputHeader.parity = inputHeader.parity;
    outputHeader.first_fine_index = inputHeader.first_fine_index;
    outputHeader.output_count = inputHeader.output_count;
    outputHeader.negative_count = summary.negative_count;
    outputHeader.ambiguous_count = summary.ambiguous_count;
    outputHeader.positive_count = summary.positive_count;
    outputHeader.adjacent_opposite_sign_count =
        summary.adjacent_opposite_sign_count;
    outputHeader.device_error_or = summary.error_or;
    outputHeader.reserved = 0U;
    copyDigest(outputHeader.coefficient_artifact_sha256,
               coefficientArtifactDigest);
    copyDigest(outputHeader.input_artifact_sha256, inputArtifactDigest);
    copyDigest(outputHeader.payload_sha256, outputPayloadDigest);
    writeFileAtomically(outputPath, &outputHeader, sizeof(outputHeader), packed);
    std::vector<unsigned char> outputRaw(sizeof(outputHeader) + packed.size());
    std::memcpy(outputRaw.data(), &outputHeader, sizeof(outputHeader));
    std::copy(packed.begin(), packed.end(),
              outputRaw.begin() + sizeof(outputHeader));
    const std::string outputArtifactSha256 =
        sparkinterval::sha256_hex(outputRaw.data(), outputRaw.size());

    std::uint64_t nonaligned = 0U;
    for (std::uint64_t index = 0; index < inputHeader.output_count; ++index) {
      if ((inputHeader.first_fine_index + static_cast<std::int64_t>(index)) %
              factor8::kUpsampleFactor !=
          0) {
        ++nonaligned;
      }
    }
    const double elapsedSeconds =
        static_cast<double>(elapsedMilliseconds) / 1000.0;
    const double targetRate =
        static_cast<double>(inputHeader.output_count) * repeats /
        elapsedSeconds;
    const double productRate =
        static_cast<double>(nonaligned) * factor8::kTapCount * repeats /
        elapsedSeconds;
    std::cout.precision(17);
    std::cout
        << "{\"algorithm_id\":\""
        << "platt-dirichlet-factor8-directed-convolution-sign-pack-v1"
        << "\",\"ambiguous_count\":" << summary.ambiguous_count
        << ",\"four_corner_reference_mode\":"
        << (fourCorner ? "true" : "false")
        << ",\"benchmark_repeats\":" << repeats
        << ",\"device_error_or\":" << summary.error_or
        << ",\"elapsed_seconds\":" << elapsedSeconds
        << ",\"external_atom_discharged\":false"
        << ",\"forty_tap_interval_products_per_second\":" << productRate
        << ",\"nonaligned_targets_per_repeat\":" << nonaligned
        << ",\"opposite_adjacent_sign_intervals\":"
        << summary.adjacent_opposite_sign_count
        << ",\"output_artifact_sha256\":\""
        << outputArtifactSha256
        << "\",\"physical_cuda_refinement_proved\":false"
        << ",\"target_samples_per_second\":" << targetRate << "}\n";
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_factor8_postprocess: %s\n",
                 error.what());
    return 1;
  }
}
