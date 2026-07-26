// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Compact fused large-q path.  It reuses the reviewed CRT, source-geometry,
// interval, and output helpers from the v1 runner, but replaces each streamed
// finite-recovery rectangle with an authenticated global recurrence seed.

#define main sparkinterval_legacy_largeq_batch_main
#include "h100_tg_dirichlet_largeq_batch.cu"
#undef main

#include "sparkinterval/tg_dirichlet_recovery_seeds.hpp"
#include "sparkinterval/tg_dirichlet_formulaic_qmajor.hpp"
#include "sparkinterval/tg_dirichlet_resident_qmajor_phase.hpp"
#include "sparkinterval/tg_dirichlet_tmajor_seeded.hpp"

#include <bit>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <functional>
#include <span>
#include <sys/stat.h>
#include <string_view>
#include <thread>

namespace rs = sparkinterval::tg::dirichlet_recovery_seeds;
namespace fq = sparkinterval::tg::dirichlet_formulaic_qmajor;
namespace rqp = sparkinterval::tg::dirichlet_resident_qmajor_phase;
namespace tms = sparkinterval::tg::dirichlet_tmajor_seeded;

namespace {

static_assert(std::endian::native == std::endian::little,
              "authenticated recovery seeds are little-endian");

constexpr char kSeededInputMagic[8] = {'T', 'G', 'D', 'L', 'Q', 'B', '2', '\0'};
constexpr char kSeedChunkDomain[] =
    "sparkinterval/dirichlet-recovery-seed-chunk/v1";
constexpr char kSeedRootDomain[] =
    "sparkinterval/dirichlet-recovery-seed-root/v1";

std::array<unsigned char, 32> seededParseDigest(std::string_view text) {
  if (text.size() != 64U) throw std::runtime_error("seed SHA-256 is malformed");
  std::array<unsigned char, 32> answer{};
  auto digit = [](char value) -> unsigned int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    throw std::runtime_error("seed SHA-256 is not lowercase hexadecimal");
  };
  for (std::size_t i = 0; i < answer.size(); ++i) {
    answer[i] = static_cast<unsigned char>(
        (digit(text[2U * i]) << 4U) | digit(text[2U * i + 1U]));
  }
  return answer;
}

sparkinterval::Sha256Digest seededHashFile(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open recovery-seed artifact");
  sparkinterval::detail::Sha256 digest;
  std::array<char, 1U << 20U> buffer{};
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    if (const auto count = input.gcount(); count > 0) {
      digest.update(buffer.data(), static_cast<std::size_t>(count));
    }
  }
  if (!input.eof()) throw std::runtime_error("cannot hash recovery-seed artifact");
  return digest.finish();
}

// Deterministic prefix-KAT synchronization for substitution regression tests.
// This is inert unless both --allow-prefix-kat and the phase-specific
// environment variable are present.  Production runs cannot enable it.
void seededPrefixKatTestBarrier(bool allowPrefixKat, const char* environment,
                                const char* phase) {
  if (!allowPrefixKat) return;
  const char* rawBase = std::getenv(environment);
  if (rawBase == nullptr || *rawBase == '\0') return;
  std::filesystem::path ready = rawBase;
  ready += ".ready";
  std::filesystem::path proceed = rawBase;
  proceed += ".continue";
  if (std::filesystem::exists(ready) ||
      std::filesystem::exists(proceed)) {
    throw std::runtime_error(
        std::string("stale prefix-KAT test barrier for ") + phase);
  }
  {
    std::ofstream marker(ready, std::ios::binary | std::ios::trunc);
    if (!marker) {
      throw std::runtime_error(
          std::string("cannot create prefix-KAT test barrier for ") + phase);
    }
    marker << phase << '\n';
    marker.flush();
    if (!marker) {
      throw std::runtime_error(
          std::string("cannot flush prefix-KAT test barrier for ") + phase);
    }
  }
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(30);
  while (!std::filesystem::exists(proceed)) {
    if (std::chrono::steady_clock::now() >= deadline) {
      throw std::runtime_error(
          std::string("timed out at prefix-KAT test barrier for ") + phase);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  std::error_code ignored;
  std::filesystem::remove(ready, ignored);
  std::filesystem::remove(proceed, ignored);
}

template <typename T>
void seededReadExact(std::istream& input, T* value, const char* label) {
  input.read(reinterpret_cast<char*>(value), sizeof(T));
  if (!input) throw std::runtime_error(std::string("short ") + label);
}

struct AuthenticatedSeeds {
  rs::Header header{};
  std::vector<rs::SeedRecord> records;
  std::uint64_t chunkCount = 0;
  std::string sha256;
};

AuthenticatedSeeds loadAuthenticatedSeeds(
    const std::filesystem::path& path,
    const std::array<unsigned char, 32>& expectedSha,
    bool allowPrefixKat) {
  const auto linkStatus = std::filesystem::symlink_status(path);
  if (std::filesystem::is_symlink(linkStatus) ||
      !std::filesystem::is_regular_file(linkStatus)) {
    throw std::runtime_error(
        "recovery-seed artifact is not a non-symlink regular file");
  }
  const auto actualSha = seededHashFile(path);
  if (actualSha != expectedSha) {
    throw std::runtime_error("seed artifact SHA-256 differs before parsing");
  }
  seededPrefixKatTestBarrier(
      allowPrefixKat,
      "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_SEED_PREHASH_BARRIER",
      "seed prehash");
  std::ifstream input(path, std::ios::binary);
  AuthenticatedSeeds loaded;
  sparkinterval::detail::Sha256 parsedArtifactDigest;
  seededReadExact(input, &loaded.header, "seed header");
  parsedArtifactDigest.update(&loaded.header, sizeof(loaded.header));
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
    throw std::runtime_error("production fused path requires the full seed range");
  }
  loaded.records.reserve(static_cast<std::size_t>(header.record_count));
  sparkinterval::detail::Sha256 recordsDigest;
  sparkinterval::detail::Sha256 rootDigest;
  rootDigest.update(kSeedRootDomain, sizeof(kSeedRootDomain));
  std::uint64_t remaining = header.record_count;
  std::uint64_t expectedX = header.x_start;
  while (remaining != 0U) {
    rs::ChunkHeader chunk{};
    seededReadExact(input, &chunk, "seed chunk header");
    parsedArtifactDigest.update(&chunk, sizeof(chunk));
    const auto expectedCount =
        std::min<std::uint64_t>(header.chunk_records, remaining);
    if (std::memcmp(chunk.magic, rs::kChunkMagic, 8) != 0 ||
        chunk.version != rs::kFormatVersion || chunk.reserved != 0U ||
        chunk.first_x != expectedX || chunk.record_count != expectedCount) {
      throw std::runtime_error("seed chunk ordering or size differs");
    }
    std::vector<rs::SeedRecord> records(static_cast<std::size_t>(chunk.record_count));
    input.read(reinterpret_cast<char*>(records.data()),
               static_cast<std::streamsize>(records.size() * sizeof(records[0])));
    if (!input) throw std::runtime_error("short seed chunk payload");
    parsedArtifactDigest.update(records.data(),
                                records.size() * sizeof(records[0]));
    sparkinterval::detail::Sha256 chunkDigest;
    chunkDigest.update(kSeedChunkDomain, sizeof(kSeedChunkDomain));
    chunkDigest.update(&chunk.first_x, sizeof(chunk.first_x));
    chunkDigest.update(&chunk.record_count, sizeof(chunk.record_count));
    chunkDigest.update(records.data(), records.size() * sizeof(records[0]));
    const auto digest = chunkDigest.finish();
    if (!std::equal(digest.begin(), digest.end(), chunk.payload_sha256)) {
      throw std::runtime_error("seed chunk SHA-256 differs");
    }
    for (const auto& record : records) {
      if (!std::isfinite(record.amplitude_lo) ||
          !std::isfinite(record.amplitude_hi) || record.amplitude_lo <= 0.0 ||
          record.amplitude_lo > record.amplitude_hi ||
          record.amplitude_hi > 1.0 || !finiteOrdered(record.phase_step) ||
          record.phase_step.re.lo < -1.0 || record.phase_step.re.hi > 1.0 ||
          record.phase_step.im.lo < -1.0 || record.phase_step.im.hi > 1.0) {
        throw std::runtime_error("seed record is malformed");
      }
    }
    recordsDigest.update(records.data(), records.size() * sizeof(records[0]));
    rootDigest.update(digest.data(), digest.size());
    loaded.records.insert(loaded.records.end(), records.begin(), records.end());
    expectedX += chunk.record_count;
    remaining -= chunk.record_count;
    ++loaded.chunkCount;
  }
  rs::Footer footer{};
  seededReadExact(input, &footer, "seed footer");
  parsedArtifactDigest.update(&footer, sizeof(footer));
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes after seed footer");
  }
  const auto recordHash = recordsDigest.finish();
  const auto rootHash = rootDigest.finish();
  const auto parsedArtifactHash = parsedArtifactDigest.finish();
  if (std::memcmp(footer.magic, rs::kFooterMagic, 8) != 0 ||
      footer.version != rs::kFormatVersion || footer.reserved != 0U ||
      footer.record_count != header.record_count ||
      footer.chunk_count != loaded.chunkCount ||
      !std::equal(recordHash.begin(), recordHash.end(), footer.records_sha256) ||
      !std::equal(rootHash.begin(), rootHash.end(), footer.chunk_root_sha256) ||
      parsedArtifactHash != expectedSha) {
    throw std::runtime_error(
        "seed footer, global digest, or parsed artifact digest differs");
  }
  loaded.sha256 = sparkinterval::lowercase_hex(actualSha);
  return loaded;
}

struct SeededFrame {
  lb::InputHeader header{};
  std::vector<lb::ResidueDescriptor> descriptors;
  std::vector<lb::FrameFactor> factors;
  std::vector<ComplexInterval> lattices;
  std::vector<double> tailRadii;
  std::string inputSha256;
};

bool readSeededFrame(
    std::istream& input, SeededFrame* frame, std::uint32_t maximumBatch,
    const std::vector<lb::ResidueDescriptor>* cachedExpected = nullptr) {
  input.read(reinterpret_cast<char*>(&frame->header), sizeof(frame->header));
  if (!input) {
    if (input.eof() && input.gcount() == 0) return false;
    throw std::runtime_error("truncated seeded large-q header");
  }
  sparkinterval::detail::Sha256 digest;
  digest.update(&frame->header, sizeof(frame->header));
  if (std::memcmp(frame->header.magic, kSeededInputMagic, 8) != 0 ||
      frame->header.version != 2U || frame->header.m != rs::kSourceM) {
    throw std::runtime_error("seeded large-q format or M differs");
  }
  std::vector<lb::ResidueDescriptor> reconstructed;
  if (cachedExpected == nullptr) {
    reconstructed = canonicalDescriptors(frame->header.q);
    cachedExpected = &reconstructed;
  }
  lb::InputHeader legacy = frame->header;
  std::memcpy(legacy.magic, lb::kInputMagic, 8);
  legacy.version = lb::kFormatVersion;
  validateHeader(legacy, *cachedExpected, maximumBatch);
  readVector(input, &frame->descriptors, frame->header.group_order,
             "seeded descriptors", &digest);
  readVector(input, &frame->factors, frame->header.batch_count,
             "seeded factors", &digest);
  readVector(input, &frame->lattices, frame->header.lattice_cell_count,
             "seeded lattices", &digest);
  readVector(input, &frame->tailRadii, frame->header.batch_count,
             "seeded tail radii", &digest);
  if (frame->descriptors != *cachedExpected) {
    throw std::runtime_error("seeded descriptors are not canonical CRT order");
  }
  for (const auto& factor : frame->factors) {
    if (!finiteOrdered(factor.q_to_the_minus_s)) {
      throw std::runtime_error("seeded q^(-s) factor is malformed");
    }
  }
  for (const auto& lattice : frame->lattices) {
    if (!finiteOrdered(lattice)) {
      throw std::runtime_error("seeded lattice interval is malformed");
    }
  }
  for (const double radius : frame->tailRadii) {
    if (!std::isfinite(radius) || radius < 0.0) {
      throw std::runtime_error("seeded Taylor radius is malformed");
    }
  }
  frame->inputSha256 = sparkinterval::lowercase_hex(digest.finish());
  return true;
}

__device__ __forceinline__ ComplexInterval seededPower(
    ComplexInterval base, std::uint64_t exponent) {
  ComplexInterval answer{{1.0, 1.0}, {0.0, 0.0}};
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) answer = cmul(answer, base);
    exponent >>= 1U;
    if (exponent != 0U) base = cmul(base, base);
  }
  return answer;
}

__global__ void reconstructComposeSeededKernel(
    lb::InputHeader header, const lb::ResidueDescriptor* descriptors,
    const lb::FrameFactor* factors, const ComplexInterval* lattices,
    const double* tailRadii, const rs::SeedRecord* seeds,
    ComplexInterval* output) {
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * gridDim.x;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < header.value_count; flat += stride) {
    const std::uint32_t frame =
        static_cast<std::uint32_t>(flat / header.group_order);
    const std::uint64_t position = flat % header.group_order;
    const auto descriptor = descriptors[position];
    const std::uint64_t tNumerator =
        static_cast<std::uint64_t>(header.first_t_numerator) +
        static_cast<std::uint64_t>(frame) * header.t_step_numerator;
    const std::uint64_t tIndex = tNumerator / rs::kSourceStepNumerator;

    const RealInterval aOverQ = rationalNonnegative(descriptor.a, header.q);
    const RealInterval rowOverD =
        rationalNonnegative(descriptor.lattice_row, dl::kLatticeRows);
    const RealInterval minusDelta = sub(rowOverD, aOverQ);
    // The admitted source grid fixes t=tNumerator/64 with tNumerator <= 2^53,
    // so scaling the exact integer by 2^-6 produces the identical singleton
    // interval without two directed divisions per residue.
    const double tPoint =
        static_cast<double>(tNumerator) * 0x1p-6;
    const RealInterval t{tPoint, tPoint};
    ComplexInterval power{{1.0, 1.0}, {0.0, 0.0}};
    ComplexInterval zeta{{0.0, 0.0}, {0.0, 0.0}};
    const std::uint64_t latticeBase =
        static_cast<std::uint64_t>(frame) * dl::kLatticeCellCount;
    for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
      const auto latticeIndex =
          latticeBase +
          (static_cast<std::uint64_t>(descriptor.lattice_row) - 1U) *
              dl::kTaylorColumns +
          column;
      zeta = cadd(zeta, cmul(power, lattices[latticeIndex]));
      if (column != dl::kTaylorDegree) {
        const ComplexInterval sPlusColumn{
            {static_cast<double>(column) + 0.5,
             static_cast<double>(column) + 0.5},
            t};
        power = cdividePositive(
            cscale(cmul(power, sPlusColumn), minusDelta),
            static_cast<double>(column + 1U));
      }
    }
    const double tail = tailRadii[frame];
    zeta.re.lo = __dsub_rd(zeta.re.lo, tail);
    zeta.re.hi = __dadd_ru(zeta.re.hi, tail);
    zeta.im.lo = __dsub_rd(zeta.im.lo, tail);
    zeta.im.hi = __dadd_ru(zeta.im.hi, tail);

    ComplexInterval recovery{{0.0, 0.0}, {0.0, 0.0}};
#pragma unroll
    for (std::uint32_t n = 0; n <= rs::kSourceM; ++n) {
      const std::uint64_t x =
          static_cast<std::uint64_t>(header.q) * n + descriptor.a;
      const auto seed = seeds[x - rs::kSourceXStart];
      ComplexInterval term = seededPower(seed.phase_step, tIndex);
      const RealInterval amplitude{seed.amplitude_lo, seed.amplitude_hi};
      term.re = mul(term.re, amplitude);
      term.im = mul(term.im, amplitude);
      recovery = cadd(recovery, term);
    }
    output[flat] = cadd(cmul(factors[frame].q_to_the_minus_s, zeta), recovery);
  }
}

class SeededPlan {
 public:
  explicit SeededPlan(const AuthenticatedSeeds& seeds) {
    try {
      CUDA_CHECK(cudaMalloc(
          &dSeeds_, seeds.records.size() * sizeof(seeds.records[0])));
      CUDA_CHECK(cudaMemcpy(
          dSeeds_, seeds.records.data(),
          seeds.records.size() * sizeof(seeds.records[0]),
          cudaMemcpyHostToDevice));
      CUDA_CHECK(cudaEventCreate(&startEvent_));
      CUDA_CHECK(cudaEventCreate(&stopEvent_));
      eventCreateCount_ = 2U;
    } catch (...) {
      if (stopEvent_ != nullptr) cudaEventDestroy(stopEvent_);
      if (startEvent_ != nullptr) cudaEventDestroy(startEvent_);
      cudaFree(dSeeds_);
      stopEvent_ = nullptr;
      startEvent_ = nullptr;
      dSeeds_ = nullptr;
      throw;
    }
  }
  SeededPlan(const SeededPlan&) = delete;
  SeededPlan& operator=(const SeededPlan&) = delete;
  ~SeededPlan() {
    if (stopEvent_ != nullptr) cudaEventDestroy(stopEvent_);
    if (startEvent_ != nullptr) cudaEventDestroy(startEvent_);
    cudaFree(dOutput_);
    cudaFree(dTails_);
    cudaFree(dLattices_);
    cudaFree(dFactors_);
    cudaFree(dDescriptors_);
    cudaFree(dSeeds_);
  }

  std::pair<std::vector<ComplexInterval>, std::uint64_t> execute(
      const SeededFrame& frame, std::uint32_t repetitions) {
    uploadResidentLattices(frame.lattices);
    return executeResident(frame, repetitions);
  }

  void uploadResidentLattices(
      const std::vector<ComplexInterval>& lattices) {
    if (lattices.empty() ||
        !std::all_of(lattices.begin(), lattices.end(), [](const auto& value) {
          return finiteOrdered(value);
        })) {
      throw std::runtime_error(
          "resident t-major lattice payload is empty or malformed");
    }
    if (lattices.size() > latticeCapacity_) {
      ++latticeDeviceAllocationCount_;
    }
    reserve(&dLattices_, &latticeCapacity_, lattices.size());
    CUDA_CHECK(cudaMemcpy(dLattices_, lattices.data(),
                          lattices.size() * sizeof(lattices[0]),
                          cudaMemcpyHostToDevice));
    residentLatticeCount_ = lattices.size();
    ++latticeUploadCount_;
    ++latticeH2dUploadCallCount_;
    latticeH2dUploadBytes_ +=
        lattices.size() * sizeof(lattices[0]);
  }

#ifdef SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN
  void beginIncrementalResidentLatticeUpload(std::size_t rowCount) {
    if (incrementalUploadActive_ || rowCount == 0U ||
        rowCount >
            std::numeric_limits<std::size_t>::max() /
                dl::kLatticeCellCount) {
      throw std::runtime_error(
          "incremental resident lattice geometry is invalid");
    }
    const auto cells = rowCount * dl::kLatticeCellCount;
    if (cells > latticeCapacity_) {
      ++latticeDeviceAllocationCount_;
    }
    reserve(&dLattices_, &latticeCapacity_, cells);
    residentLatticeCount_ = 0U;
    incrementalExpectedCells_ = cells;
    incrementalUploadedCells_ = 0U;
    incrementalUploadActive_ = true;
  }

  void uploadIncrementalResidentLattice(
      std::size_t firstCell,
      std::span<const ComplexInterval> lattices) {
    if (!incrementalUploadActive_ || lattices.empty() ||
        firstCell != incrementalUploadedCells_ ||
        lattices.size() >
            incrementalExpectedCells_ - incrementalUploadedCells_ ||
        !std::all_of(
            lattices.begin(), lattices.end(), [](const auto& value) {
              return finiteOrdered(value);
            })) {
      throw std::runtime_error(
          "incremental resident lattice upload is malformed");
    }
    CUDA_CHECK(cudaMemcpy(
        dLattices_ + firstCell, lattices.data(),
        lattices.size() * sizeof(lattices[0]),
        cudaMemcpyHostToDevice));
    incrementalUploadedCells_ += lattices.size();
    ++latticeH2dUploadCallCount_;
    latticeH2dUploadBytes_ +=
        lattices.size() * sizeof(lattices[0]);
  }

  void finishIncrementalResidentLatticeUpload() {
    if (!incrementalUploadActive_ ||
        incrementalUploadedCells_ != incrementalExpectedCells_) {
      throw std::runtime_error(
          "incremental resident lattice upload is incomplete");
    }
    residentLatticeCount_ = incrementalExpectedCells_;
    incrementalUploadActive_ = false;
    ++latticeUploadCount_;
  }
#endif

  std::pair<std::vector<ComplexInterval>, std::uint64_t> executeResident(
      const SeededFrame& frame, std::uint32_t repetitions) {
    return executeResidentAt(frame, 0U, repetitions);
  }

  std::pair<std::vector<ComplexInterval>, std::uint64_t> executeResidentAt(
      const SeededFrame& frame, std::size_t firstResidentRow,
      std::uint32_t repetitions) {
    if (firstResidentRow >
        std::numeric_limits<std::size_t>::max() /
            dl::kLatticeCellCount) {
      throw std::runtime_error(
          "resident lattice row offset overflows");
    }
    const auto firstCell =
        firstResidentRow * dl::kLatticeCellCount;
    if (frame.header.lattice_cell_count == 0U ||
        firstCell > residentLatticeCount_ ||
        frame.header.lattice_cell_count >
            residentLatticeCount_ - firstCell) {
      throw std::runtime_error(
          "resident t-major lattice block does not cover the target");
    }
    if (residentDescriptorQ_ != frame.header.q) {
      if (frame.descriptors.empty()) {
        throw std::runtime_error(
            "canonical descriptor cache transition is empty");
      }
      reserve(&dDescriptors_, &descriptorCapacity_, frame.descriptors.size());
      CUDA_CHECK(cudaMemcpy(
          dDescriptors_, frame.descriptors.data(),
          frame.descriptors.size() * sizeof(frame.descriptors[0]),
          cudaMemcpyHostToDevice));
      residentDescriptorQ_ = frame.header.q;
      residentDescriptorCount_ = frame.descriptors.size();
      ++descriptorUploadCount_;
    } else if (
        residentDescriptorCount_ != frame.header.group_order ||
        (!frame.descriptors.empty() &&
         residentDescriptorCount_ != frame.descriptors.size())) {
      throw std::runtime_error(
          "canonical descriptor count changed within one q");
    }
    reserve(&dFactors_, &factorCapacity_, frame.factors.size());
    reserve(&dTails_, &tailCapacity_, frame.tailRadii.size());
    reserve(&dOutput_, &outputCapacity_, frame.header.value_count);
    CUDA_CHECK(cudaMemcpy(dFactors_, frame.factors.data(),
                          frame.factors.size() * sizeof(frame.factors[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dTails_, frame.tailRadii.data(),
                          frame.tailRadii.size() * sizeof(frame.tailRadii[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaEventRecord(startEvent_));
    constexpr std::uint32_t kThreads = 256U;
    for (std::uint32_t repetition = 0; repetition < repetitions; ++repetition) {
      reconstructComposeSeededKernel<<<blocksFor(frame.header.value_count), kThreads>>>(
          frame.header, dDescriptors_, dFactors_, dLattices_ + firstCell,
          dTails_, dSeeds_, dOutput_);
      CUDA_CHECK(cudaGetLastError());
    }
    CUDA_CHECK(cudaEventRecord(stopEvent_));
    CUDA_CHECK(cudaEventSynchronize(stopEvent_));
    float milliseconds = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(
        &milliseconds, startEvent_, stopEvent_));
    ++eventReuseCount_;
    std::vector<ComplexInterval> output(frame.header.value_count);
    CUDA_CHECK(cudaMemcpy(output.data(), dOutput_,
                          output.size() * sizeof(output[0]),
                          cudaMemcpyDeviceToHost));
    if (!std::all_of(output.begin(), output.end(), [](const auto& value) {
          return finiteOrdered(value);
        })) {
      throw std::runtime_error("seeded fused output contains malformed intervals");
    }
    return {std::move(output), static_cast<std::uint64_t>(
                                   static_cast<double>(milliseconds) * 1.0e6)};
  }

  std::uint64_t latticeUploadCount() const { return latticeUploadCount_; }
  std::uint64_t descriptorUploadCount() const {
    return descriptorUploadCount_;
  }
#ifdef SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN
  std::uint64_t latticeDeviceAllocationCount() const {
    return latticeDeviceAllocationCount_;
  }
  std::uint64_t latticeH2dUploadCallCount() const {
    return latticeH2dUploadCallCount_;
  }
  std::uint64_t latticeH2dUploadBytes() const {
    return latticeH2dUploadBytes_;
  }
  std::uint64_t eventCreateCount() const {
    return eventCreateCount_;
  }
  std::uint64_t eventReuseCount() const {
    return eventReuseCount_;
  }
#endif

 private:
  template <typename T>
  static void reserve(T** pointer, std::size_t* capacity, std::size_t count) {
    if (count <= *capacity) return;
    CUDA_CHECK(cudaFree(*pointer));
    *pointer = nullptr;
    CUDA_CHECK(cudaMalloc(pointer, count * sizeof(T)));
    *capacity = count;
  }
  rs::SeedRecord* dSeeds_ = nullptr;
  lb::ResidueDescriptor* dDescriptors_ = nullptr;
  lb::FrameFactor* dFactors_ = nullptr;
  ComplexInterval* dLattices_ = nullptr;
  double* dTails_ = nullptr;
  ComplexInterval* dOutput_ = nullptr;
  std::size_t descriptorCapacity_ = 0;
  std::size_t factorCapacity_ = 0;
  std::size_t latticeCapacity_ = 0;
  std::size_t tailCapacity_ = 0;
  std::size_t outputCapacity_ = 0;
  std::size_t residentLatticeCount_ = 0;
  std::uint32_t residentDescriptorQ_ = 0U;
  std::size_t residentDescriptorCount_ = 0U;
  std::uint64_t latticeUploadCount_ = 0;
  std::uint64_t descriptorUploadCount_ = 0;
  std::uint64_t latticeDeviceAllocationCount_ = 0;
  std::uint64_t latticeH2dUploadCallCount_ = 0;
  std::uint64_t latticeH2dUploadBytes_ = 0;
  std::size_t incrementalExpectedCells_ = 0;
  std::size_t incrementalUploadedCells_ = 0;
  bool incrementalUploadActive_ = false;
  cudaEvent_t startEvent_ = nullptr;
  cudaEvent_t stopEvent_ = nullptr;
  std::uint64_t eventCreateCount_ = 0;
  std::uint64_t eventReuseCount_ = 0;
};

da::InputHeader seededOutputHeader(const SeededFrame& frame) {
  da::InputHeader header{};
  std::memcpy(header.magic, da::kInputMagic, 8);
  header.version = da::kFormatVersion;
  header.q = frame.header.q;
  header.component_count = frame.header.component_count;
  header.batch_count = frame.header.batch_count;
  header.group_order = frame.header.group_order;
  header.first_t_numerator = frame.header.first_t_numerator;
  header.t_denominator = frame.header.t_denominator;
  header.t_step_numerator = frame.header.t_step_numerator;
  header.value_count = frame.header.value_count;
  return header;
}

template <typename Stream>
void writeSeededOutput(Stream& output, const SeededFrame& frame,
                       const std::vector<ComplexInterval>& values,
                       sparkinterval::detail::Sha256* digest = nullptr) {
  const auto header = seededOutputHeader(frame);
  output.write(reinterpret_cast<const char*>(&header), sizeof(header));
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(values[0])));
  if (!output) throw std::runtime_error("cannot write seeded TGDAFFI1 output");
  if (digest != nullptr) {
    digest->update(&header, sizeof(header));
    digest->update(values.data(), values.size() * sizeof(values[0]));
  }
}

void runSeededSingle(const AuthenticatedSeeds& seeds, const char* inputPath,
                     const char* outputPath, std::uint32_t device,
                     std::uint32_t repetitions) {
  selectDevice(device);
  std::ifstream input(inputPath, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open seeded input");
  SeededFrame frame;
  if (!readSeededFrame(input, &frame, lb::kMaximumBatchCount)) {
    throw std::runtime_error("empty seeded input");
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes after one seeded frame");
  }
  const std::uint64_t requiredX =
      static_cast<std::uint64_t>(rs::kSourceM) * frame.header.q +
      frame.header.q - 1U;
  if (seeds.header.x_stop < requiredX) {
    throw std::runtime_error("seed artifact does not cover seeded frame q");
  }
  SeededPlan plan(seeds);
  auto [values, elapsed] = plan.execute(frame, repetitions);
  if (std::filesystem::exists(outputPath)) {
    throw std::runtime_error("refusing to replace seeded output");
  }
  const auto temporary = std::string(outputPath) + ".tmp." +
                         std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    writeSeededOutput(output, frame, values);
  }
  std::error_code error;
  std::filesystem::rename(temporary, outputPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish seeded output: " + error.message());
  }
  const double seconds = static_cast<double>(elapsed) / 1.0e9;
  std::cout
      << "{\"algorithm\":\"platt-dirichlet-largeq-seeded-fused-v1\""
      << ",\"classification\":\"fused_directed_cuda_component_not_theorem_7_1\""
      << ",\"external_atom_discharged\":false"
      << ",\"input_sha256\":\"" << frame.inputSha256 << "\""
      << ",\"kernel_launches\":" << repetitions
      << ",\"q\":" << frame.header.q
      << ",\"recovery_rectangles_streamed\":0"
      << ",\"seed_artifact_sha256\":\"" << seeds.sha256 << "\""
      << ",\"transcendental_device_calls\":0"
      << ",\"value_count\":" << values.size()
      << ",\"values_per_second\":" << std::setprecision(17)
      << static_cast<double>(values.size()) * repetitions / seconds << "}\n";
}

void runSeededService(const AuthenticatedSeeds& seeds, std::uint32_t q,
                      std::uint32_t maximumBatch,
                      const std::filesystem::path& summaryPath,
                      std::uint32_t device) {
  if (q < lb::kMinimumModulus || q > lb::kMaximumModulus ||
      maximumBatch == 0U || maximumBatch > lb::kMaximumBatchCount) {
    throw std::runtime_error("invalid seeded service q or batch bound");
  }
  const std::uint64_t requiredX =
      static_cast<std::uint64_t>(rs::kSourceM) * q + q - 1U;
  if (seeds.header.x_stop < requiredX) {
    throw std::runtime_error("seed artifact does not cover service q");
  }
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error("refusing to replace seeded service summary");
  }
  selectDevice(device);
  SeededPlan plan(seeds);
  const auto expected = canonicalDescriptors(q);
  std::uint64_t frames = 0;
  std::uint64_t values = 0;
  std::uint64_t elapsed = 0;
  std::uint64_t expectedNextT = 0;
  sparkinterval::detail::Sha256 inputDigests;
  sparkinterval::detail::Sha256 outputDigest;
  while (true) {
    SeededFrame frame;
    if (!readSeededFrame(std::cin, &frame, maximumBatch, &expected)) break;
    if (frame.header.q != q) throw std::runtime_error("seeded service q changed");
    if (frames != 0U &&
        static_cast<std::uint64_t>(frame.header.first_t_numerator) !=
            expectedNextT) {
      throw std::runtime_error("seeded service ordinates are not contiguous");
    }
    expectedNextT =
        static_cast<std::uint64_t>(frame.header.first_t_numerator) +
        static_cast<std::uint64_t>(frame.header.batch_count) *
            frame.header.t_step_numerator;
    inputDigests.update(frame.inputSha256.data(), frame.inputSha256.size());
    auto [result, frameElapsed] = plan.execute(frame, 1U);
    writeSeededOutput(std::cout, frame, result, &outputDigest);
    std::cout.flush();
    if (!std::cout) throw std::runtime_error("cannot flush seeded output stream");
    ++frames;
    values += frame.header.value_count;
    elapsed += frameElapsed;
  }
  if (frames == 0U) throw std::runtime_error("seeded service received no frames");
  const auto temporary = summaryPath.string() + ".tmp." +
                         std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    summary
        << "{\"classification\":\"persistent_seeded_fused_component_not_theorem_7_1\""
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"frame_count\":" << frames
        << ",\"input_frame_digest_chain_sha256\":\""
        << sparkinterval::lowercase_hex(inputDigests.finish()) << "\""
        << ",\"output_stream_sha256\":\""
        << sparkinterval::lowercase_hex(outputDigest.finish()) << "\""
        << ",\"q\":" << q
        << ",\"recovery_rectangles_streamed\":0"
        << ",\"seed_artifact_sha256\":\"" << seeds.sha256 << "\""
        << ",\"seed_chunks_authenticated_before_gpu_use\":"
        << seeds.chunkCount
        << ",\"transcendental_device_calls\":0"
        << ",\"value_count\":" << values << "}\n";
    if (!summary) throw std::runtime_error("cannot write seeded service summary");
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish seeded summary: " + error.message());
  }
}

constexpr char kTMajorTargetSidecarDomain[] =
    "sparkinterval/tg/dirichlet-tmajor-seeded/target-sidecar/v1";
constexpr char kTMajorBlockRowBindingDomain[] =
    "sparkinterval/tg/dirichlet-tmajor-spool/block-rows/v1";

template <typename T>
void tmajorDigestObject(sparkinterval::detail::Sha256* digest,
                        const T& value) {
  digest->update(&value, sizeof(value));
}

std::string tmajorRawDigest(const unsigned char* raw) {
  std::array<unsigned char, 32> value{};
  std::copy_n(raw, value.size(), value.begin());
  return sparkinterval::lowercase_hex(value);
}

template <typename T>
void tmajorReadVector(std::istream& input, std::vector<T>* values,
                      std::uint64_t count, const char* label,
                      sparkinterval::detail::Sha256* inputDigest = nullptr,
                      sparkinterval::detail::Sha256* streamDigest = nullptr) {
  readVector(input, values, count, label);
  const auto bytes = values->size() * sizeof(T);
  if (inputDigest != nullptr) inputDigest->update(values->data(), bytes);
  if (streamDigest != nullptr) streamDigest->update(values->data(), bytes);
}

std::uint64_t tmajorTotient(std::uint32_t q) {
  std::uint64_t result = q;
  std::uint32_t remaining = q;
  for (std::uint32_t prime = 2U;
       static_cast<std::uint64_t>(prime) * prime <= remaining;
       prime += (prime == 2U ? 1U : 2U)) {
    if (remaining % prime != 0U) continue;
    result -= result / prime;
    while (remaining % prime == 0U) remaining /= prime;
  }
  if (remaining > 1U) result -= result / remaining;
  return result;
}

std::uint32_t tmajorExpectedBatch(const tms::BlockHeader& block,
                                  std::uint32_t q) {
  const auto activeStop = std::min<std::uint64_t>(
      block.t_index_stop_exclusive, maximumTIndex(q) + 1U);
  if (activeStop <= block.first_t_index) return 0U;
  return static_cast<std::uint32_t>(activeStop - block.first_t_index);
}

bool tmajorHasPrimitiveCharacter(std::uint32_t q) {
  // Every modulus in this path is > 2.  Such a modulus supports a primitive
  // Dirichlet character exactly when it is not 2 modulo 4.
  return q % 4U != 2U;
}

std::uint32_t tmajorExpectedTargetCount(const tms::BlockHeader& block) {
  std::uint32_t count = 0U;
  for (std::uint32_t q = block.q_start;; ++q) {
    if (tmajorHasPrimitiveCharacter(q) &&
        tmajorExpectedBatch(block, q) != 0U) {
      ++count;
    }
    if (q == block.q_stop) break;
  }
  return count;
}

void tmajorValidateBlockHeader(const tms::BlockHeader& header,
                               const AuthenticatedSeeds& seeds) {
  const auto expectedSeed = seededParseDigest(seeds.sha256);
  if (std::memcmp(header.magic, tms::kBlockMagic, 8) != 0 ||
      header.version != tms::kFormatVersion ||
      header.row_count == 0U || header.row_count > tms::kMaximumRows ||
      header.q_start < lb::kMinimumModulus ||
      header.q_stop > lb::kMaximumModulus ||
      header.q_start > header.q_stop || header.m != rs::kSourceM ||
      (header.sidecar_mode != tms::kQMajorManifestSidecars &&
       header.sidecar_mode != tms::kDirectMpfrSidecars) ||
      header.target_count == 0U ||
      header.first_t_index > maximumTIndex(lb::kMinimumModulus) ||
      header.first_t_index >
          std::numeric_limits<std::uint64_t>::max() - header.row_count ||
      header.first_t_index >
          static_cast<std::uint64_t>(
              std::numeric_limits<std::int64_t>::max()) /
              lb::kSourceTStepNumerator ||
      header.t_index_stop_exclusive !=
          header.first_t_index + header.row_count ||
      header.row_payload_bytes !=
          static_cast<std::uint64_t>(dl::kLatticeCellCount) *
              sizeof(ComplexInterval) ||
      header.row_record_bytes !=
          sizeof(tms::RowHeader) + header.row_payload_bytes ||
      header.target_header_bytes != sizeof(tms::TargetHeader) ||
      header.target_count != tmajorExpectedTargetCount(header) ||
      !std::equal(std::begin(header.seed_artifact_sha256),
                  std::end(header.seed_artifact_sha256),
                  expectedSeed.begin())) {
    throw std::runtime_error(
        "t-major block header or exact source geometry differs");
  }
}

void tmajorValidateTargetHeader(const tms::BlockHeader& block,
                                const tms::TargetHeader& target,
                                std::uint32_t expectedQ) {
  const auto batch = tmajorExpectedBatch(block, expectedQ);
  const auto orders = canonicalOrders(expectedQ);
  const auto order = tmajorTotient(expectedQ);
  if (std::memcmp(target.magic, tms::kTargetMagic, 8) != 0 ||
      target.version != tms::kFormatVersion || target.q != expectedQ ||
      target.component_count != orders.size() ||
      target.batch_count != batch || batch == 0U ||
      target.reserved0 != 0U || target.reserved1 != 0U ||
      target.group_order != order ||
      target.first_t_numerator !=
          static_cast<std::int64_t>(
              block.first_t_index * lb::kSourceTStepNumerator) ||
      target.t_denominator != lb::kSourceTDenominator ||
      target.t_step_numerator != lb::kSourceTStepNumerator ||
      target.value_count != static_cast<std::uint64_t>(batch) * order ||
      target.factor_bytes !=
          static_cast<std::uint64_t>(batch) * sizeof(lb::FrameFactor) ||
      target.tail_bytes != static_cast<std::uint64_t>(batch) * sizeof(double)) {
    throw std::runtime_error(
        "t-major target header is malformed, skipped, or reordered");
  }
}

std::array<unsigned char, 32> tmajorSidecarDigest(
    const tms::TargetHeader& target,
    const std::vector<lb::FrameFactor>& factors,
    const std::vector<double>& tails) {
  sparkinterval::detail::Sha256 digest;
  digest.update(kTMajorTargetSidecarDomain,
                sizeof(kTMajorTargetSidecarDomain));
  digest.update(&target.q, sizeof(target.q));
  digest.update(&target.batch_count, sizeof(target.batch_count));
  digest.update(&target.first_t_numerator,
                sizeof(target.first_t_numerator));
  digest.update(&target.group_order, sizeof(target.group_order));
  digest.update(factors.data(), factors.size() * sizeof(factors[0]));
  digest.update(tails.data(), tails.size() * sizeof(tails[0]));
  return digest.finish();
}

struct TMajorAudit {
  tms::BlockHeader header{};
  tms::BlockFooter footer{};
  std::string inputSha256;
};

TMajorAudit auditTMajorBlock(const std::filesystem::path& inputPath,
                             const std::string& expectedInputSha256,
                             const AuthenticatedSeeds& seeds) {
  const auto linkStatus = std::filesystem::symlink_status(inputPath);
  if (std::filesystem::is_symlink(linkStatus) ||
      !std::filesystem::is_regular_file(linkStatus)) {
    throw std::runtime_error(
        "t-major block input is not a non-symlink regular file");
  }
  const auto beforeSize = std::filesystem::file_size(inputPath);
  const auto actual = seededHashFile(inputPath);
  if (sparkinterval::lowercase_hex(actual) != expectedInputSha256) {
    throw std::runtime_error("t-major block SHA-256 differs before parsing");
  }
  std::ifstream input(inputPath, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open t-major block input");
  TMajorAudit audit;
  sparkinterval::detail::Sha256 inputDigest;
  seededReadExact(input, &audit.header, "t-major block header");
  tmajorDigestObject(&inputDigest, audit.header);
  tmajorValidateBlockHeader(audit.header, seeds);

  sparkinterval::detail::Sha256 rowStream;
  sparkinterval::detail::Sha256 rowBinding;
  rowBinding.update(kTMajorBlockRowBindingDomain,
                    sizeof(kTMajorBlockRowBindingDomain));
  rowBinding.update(audit.header.spool_receipt_sha256, 32U);
  for (std::uint32_t index = 0; index < audit.header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(input, &row, "t-major row header");
    tmajorDigestObject(&inputDigest, row);
    tmajorDigestObject(&rowStream, row);
    std::vector<ComplexInterval> payload;
    tmajorReadVector(input, &payload, dl::kLatticeCellCount,
                     "t-major row payload", &inputDigest, &rowStream);
    sparkinterval::detail::Sha256 payloadDigest;
    payloadDigest.update(payload.data(), payload.size() * sizeof(payload[0]));
    const auto payloadSha = payloadDigest.finish();
    if (std::memcmp(row.magic, tms::kRowMagic, 8) != 0 ||
        row.version != tms::kFormatVersion || row.reserved != 0U ||
        row.t_index != audit.header.first_t_index + index ||
        row.payload_bytes != audit.header.row_payload_bytes ||
        !std::equal(payloadSha.begin(), payloadSha.end(),
                    row.payload_sha256) ||
        !std::all_of(payload.begin(), payload.end(), [](const auto& value) {
          return finiteOrdered(value);
        })) {
      throw std::runtime_error(
          "t-major row payload is malformed, substituted, or reordered");
    }
    rowBinding.update(&row.t_index, sizeof(row.t_index));
    rowBinding.update(row.payload_sha256, sizeof(row.payload_sha256));
  }
  const auto rowBindingSha = rowBinding.finish();
  if (!std::equal(rowBindingSha.begin(), rowBindingSha.end(),
                  audit.header.row_bindings_sha256)) {
    throw std::runtime_error(
        "t-major block rows differ from the spool binding");
  }

  sparkinterval::detail::Sha256 targetStream;
  std::uint64_t targetRows = 0U;
  std::uint64_t values = 0U;
  std::uint64_t sidecarBytes = 0U;
  std::uint32_t observedTargets = 0U;
  for (std::uint32_t q = audit.header.q_start;; ++q) {
    const auto batch = tmajorExpectedBatch(audit.header, q);
    if (tmajorHasPrimitiveCharacter(q) && batch != 0U) {
      tms::TargetHeader target{};
      seededReadExact(input, &target, "t-major target header");
      tmajorDigestObject(&inputDigest, target);
      tmajorDigestObject(&targetStream, target);
      tmajorValidateTargetHeader(audit.header, target, q);
      std::vector<lb::FrameFactor> factors;
      std::vector<double> tails;
      tmajorReadVector(input, &factors, target.batch_count,
                       "t-major target factors", &inputDigest,
                       &targetStream);
      tmajorReadVector(input, &tails, target.batch_count,
                       "t-major target tails", &inputDigest,
                       &targetStream);
      if (!std::all_of(factors.begin(), factors.end(), [](const auto& value) {
            return finiteOrdered(value.q_to_the_minus_s);
          }) ||
          !std::all_of(tails.begin(), tails.end(), [](double value) {
            return std::isfinite(value) && value >= 0.0;
          })) {
        throw std::runtime_error(
            "t-major factor or Taylor-tail sidecar is malformed");
      }
      const auto sidecar = tmajorSidecarDigest(target, factors, tails);
      if (!std::equal(sidecar.begin(), sidecar.end(),
                      target.sidecar_sha256)) {
        throw std::runtime_error("t-major target sidecar digest differs");
      }
      targetRows += target.batch_count;
      values += target.value_count;
      sidecarBytes += target.factor_bytes + target.tail_bytes;
      ++observedTargets;
    }
    if (q == audit.header.q_stop) break;
  }
  seededReadExact(input, &audit.footer, "t-major block footer");
  tmajorDigestObject(&inputDigest, audit.footer);
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes after t-major block footer");
  }
  const auto rowStreamSha = rowStream.finish();
  const auto targetStreamSha = targetStream.finish();
  if (std::memcmp(audit.footer.magic, tms::kFooterMagic, 8) != 0 ||
      audit.footer.version != tms::kFormatVersion ||
      audit.footer.reserved != 0U ||
      audit.footer.row_count != audit.header.row_count ||
      audit.footer.target_count != observedTargets ||
      audit.footer.target_row_reference_count != targetRows ||
      audit.footer.value_count != values ||
      audit.footer.sidecar_bytes != sidecarBytes ||
      (audit.header.sidecar_mode == tms::kQMajorManifestSidecars &&
       audit.footer.source_input_bytes < sidecarBytes) ||
      (audit.header.sidecar_mode == tms::kDirectMpfrSidecars &&
       audit.footer.source_input_bytes != 0U) ||
      !std::equal(rowStreamSha.begin(), rowStreamSha.end(),
                  audit.footer.row_stream_sha256) ||
      !std::equal(targetStreamSha.begin(), targetStreamSha.end(),
                  audit.footer.target_stream_sha256)) {
    throw std::runtime_error(
        "t-major block footer, accounting, or stream digest differs");
  }
  audit.inputSha256 = sparkinterval::lowercase_hex(inputDigest.finish());
  if (audit.inputSha256 != expectedInputSha256 ||
      std::filesystem::file_size(inputPath) != beforeSize) {
    throw std::runtime_error("t-major block changed during preflight replay");
  }
  return audit;
}

void runTMajorBlock(const AuthenticatedSeeds& seeds,
                    const std::filesystem::path& inputPath,
                    const std::string& expectedInputSha256,
                    const std::filesystem::path& summaryPath,
                    std::uint32_t device, bool allowPrefixKat) {
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error("refusing to replace t-major service summary");
  }
  const auto audit =
      auditTMajorBlock(inputPath, expectedInputSha256, seeds);
  seededPrefixKatTestBarrier(
      allowPrefixKat,
      "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_TMAJOR_PREFLIGHT_BARRIER",
      "t-major preflight");
  const std::uint64_t requiredX =
      static_cast<std::uint64_t>(rs::kSourceM) * audit.header.q_stop +
      audit.header.q_stop - 1U;
  if (seeds.header.x_stop < requiredX) {
    throw std::runtime_error(
        "seed artifact does not cover the t-major modulus range");
  }
  selectDevice(device);
  SeededPlan plan(seeds);
  std::ifstream input(inputPath, std::ios::binary);
  sparkinterval::detail::Sha256 executionInputDigest;
  tms::BlockHeader header{};
  seededReadExact(input, &header, "t-major execution header");
  tmajorDigestObject(&executionInputDigest, header);
  std::vector<ComplexInterval> resident;
  resident.reserve(static_cast<std::size_t>(header.row_count) *
                   dl::kLatticeCellCount);
  for (std::uint32_t index = 0; index < header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(input, &row, "t-major execution row header");
    tmajorDigestObject(&executionInputDigest, row);
    const auto oldSize = resident.size();
    resident.resize(oldSize + dl::kLatticeCellCount);
    input.read(reinterpret_cast<char*>(resident.data() + oldSize),
               static_cast<std::streamsize>(
                   dl::kLatticeCellCount * sizeof(resident[0])));
    if (!input) throw std::runtime_error("truncated execution lattice row");
    executionInputDigest.update(
        resident.data() + oldSize,
        dl::kLatticeCellCount * sizeof(resident[0]));
    sparkinterval::detail::Sha256 payloadDigest;
    payloadDigest.update(
        resident.data() + oldSize,
        dl::kLatticeCellCount * sizeof(resident[0]));
    const auto payloadSha256 = payloadDigest.finish();
    if (std::memcmp(row.magic, tms::kRowMagic, 8U) != 0 ||
        row.version != tms::kFormatVersion ||
        row.reserved != 0U ||
        row.t_index != header.first_t_index + index ||
        row.payload_bytes != header.row_payload_bytes ||
        !std::equal(
            payloadSha256.begin(), payloadSha256.end(),
            row.payload_sha256) ||
        !std::all_of(
            resident.begin() + static_cast<std::ptrdiff_t>(oldSize),
            resident.end(), [](const auto& value) {
              return finiteOrdered(value);
            })) {
      throw std::runtime_error(
          "resident execution row changed after preflight");
    }
  }
  plan.uploadResidentLattices(resident);

  sparkinterval::detail::Sha256 outputDigest;
  std::uint64_t frames = 0U;
  std::uint64_t values = 0U;
  std::uint64_t elapsed = 0U;
  for (std::uint32_t q = header.q_start;; ++q) {
    const auto batch = tmajorExpectedBatch(header, q);
    if (tmajorHasPrimitiveCharacter(q) && batch != 0U) {
      tms::TargetHeader target{};
      seededReadExact(input, &target, "t-major execution target");
      tmajorDigestObject(&executionInputDigest, target);
      tmajorValidateTargetHeader(header, target, q);
      SeededFrame frame;
      std::memcpy(frame.header.magic, kSeededInputMagic, 8);
      frame.header.version = 2U;
      frame.header.q = target.q;
      frame.header.lattice_rows = dl::kLatticeRows;
      frame.header.taylor_degree = dl::kTaylorDegree;
      frame.header.component_count = target.component_count;
      frame.header.batch_count = target.batch_count;
      frame.header.m = rs::kSourceM;
      frame.header.group_order = target.group_order;
      frame.header.first_t_numerator = target.first_t_numerator;
      frame.header.t_denominator = target.t_denominator;
      frame.header.t_step_numerator = target.t_step_numerator;
      frame.header.lattice_cell_count =
          static_cast<std::uint64_t>(target.batch_count) *
          dl::kLatticeCellCount;
      frame.header.value_count = target.value_count;
      frame.descriptors = canonicalDescriptors(q);
      tmajorReadVector(input, &frame.factors, target.batch_count,
                       "t-major execution factors", &executionInputDigest);
      tmajorReadVector(input, &frame.tailRadii, target.batch_count,
                       "t-major execution tails", &executionInputDigest);
      auto [result, frameElapsed] = plan.executeResident(frame, 1U);
      writeSeededOutput(std::cout, frame, result, &outputDigest);
      std::cout.flush();
      if (!std::cout) {
        throw std::runtime_error(
            "cannot flush t-major TGDAFFI1 output stream");
      }
      ++frames;
      values += target.value_count;
      elapsed += frameElapsed;
    }
    if (q == header.q_stop) break;
  }
  tms::BlockFooter footer{};
  seededReadExact(input, &footer, "t-major execution footer");
  tmajorDigestObject(&executionInputDigest, footer);
  const auto executionInputSha256 =
      sparkinterval::lowercase_hex(executionInputDigest.finish());
  seededPrefixKatTestBarrier(
      allowPrefixKat,
      "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_TMAJOR_CONSUME_BARRIER",
      "t-major consumption");
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(&footer, &audit.footer, sizeof(footer)) != 0 ||
      frames != audit.footer.target_count ||
      values != audit.footer.value_count ||
      plan.latticeUploadCount() != 1U ||
      executionInputSha256 != expectedInputSha256) {
    throw std::runtime_error(
        "t-major consumed input digest or execution totals differ after CUDA");
  }
  const auto temporary = summaryPath.string() + ".tmp." +
                         std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    if (!summary) {
      throw std::runtime_error("cannot create t-major service summary");
    }
    summary
        << "{\"algorithm_id\":\"platt-dirichlet-tmajor-row-resident-seeded-cuda-v2\""
        << ",\"all_character_fft_executed\":false"
        << ",\"canonical_descriptor_input_bytes\":0"
        << ",\"classification\":\"row_resident_seeded_cuda_component_not_zero_or_turing_closure\""
        << ",\"completed_l_zero_state_validated\":false"
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"input_artifact_sha256\":\"" << expectedInputSha256 << "\""
        << ",\"lane_index\":" << header.lane_index
        << ",\"lattice_h2d_upload_count\":"
        << plan.latticeUploadCount()
        << ",\"output_stream_sha256\":\""
        << sparkinterval::lowercase_hex(outputDigest.finish()) << "\""
        << ",\"recovery_seed_artifact_sha256\":\"" << seeds.sha256 << "\""
        << ",\"row_bindings_sha256\":\""
        << tmajorRawDigest(header.row_bindings_sha256)
        << "\""
        << ",\"row_count\":" << header.row_count
        << ",\"row_payload_h2d_bytes\":"
        << header.row_count * header.row_payload_bytes
        << ",\"schema\":\"sparkinterval.tg.dirichlet_tmajor_cuda.execution_summary.v2\""
        << ",\"schema_version\":2"
        << ",\"sidecar_source_sha256\":\""
        << tmajorRawDigest(header.sidecar_source_sha256)
        << "\""
        << ",\"source_contract_sha256\":\""
        << tmajorRawDigest(header.source_contract_sha256)
        << "\""
        << ",\"source_scale_run\":false"
        << ",\"spool_receipt_sha256\":\""
        << tmajorRawDigest(header.spool_receipt_sha256)
        << "\""
        << ",\"target_count\":" << frames
        << ",\"transcendental_device_calls\":0"
        << ",\"trusted_execution_attested\":false"
        << ",\"value_count\":" << values
        << ",\"zero_completeness_claimed\":false}\n";
    if (!summary) {
      throw std::runtime_error("cannot write t-major service summary");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "cannot publish t-major summary: " + error.message());
  }
}

constexpr char kFormulaicQOrderMagic[8] = {
    'T', 'G', 'D', 'Q', 'O', 'R', 'D', '1'};
constexpr std::uint32_t kFormulaicQOrderVersion = 1U;
constexpr std::uint32_t kFormulaicBoundedSchedule = 0U;
constexpr std::uint32_t kFormulaicFullSourceSchedule = 1U;
constexpr std::uint32_t kFormulaicPrimitiveRosterVersion = 2U;
constexpr std::uint32_t kFormulaicQStart = 10001U;
constexpr std::uint32_t kFormulaicQStop = 400000U;
constexpr std::uint64_t kFormulaicSourceQCount = 292500U;
constexpr std::uint64_t kFormulaicSourceRowCount = 3637613167U;
constexpr std::string_view kFormulaicSourceRosterSha256 =
    "d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c";
constexpr std::string_view kFormulaicSourceExecutionSha256 =
    "34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd";
constexpr char kFormulaicSourceRosterDomain[] = "TGDQ_SOURCE_ROSTER_V1";
constexpr char kFormulaicExecutionOrderDomain[] = "TGDQ_EXECUTION_ORDER_V1";

struct FormulaicQOrderHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t classification;
  std::uint32_t primitive_roster_version;
  std::uint32_t q_start;
  std::uint32_t q_stop;
  std::uint32_t record_size;
  std::uint64_t q_count;
  std::uint64_t t_row_count;
  unsigned char source_roster_sha256[32];
  unsigned char execution_order_sha256[32];
};

struct FormulaicQOrderRecord {
  std::uint32_t q;
  std::uint32_t t_index_count;
};

static_assert(sizeof(FormulaicQOrderHeader) == 112U);
static_assert(sizeof(FormulaicQOrderRecord) == 8U);

struct FormulaicQOrder {
  FormulaicQOrderHeader header{};
  std::vector<FormulaicQOrderRecord> execution;
  sparkinterval::Sha256Digest fileSha256{};
};

bool formulaicHasPrimitiveCharacter(std::uint32_t q) {
  return q >= kFormulaicQStart && q <= kFormulaicQStop &&
         q % 4U != 2U;
}

std::array<std::uint32_t, da::kMaxComponents + 1U> formulaicQOrderKey(
    std::uint32_t q) {
  auto orders = canonicalOrders(q);
  std::sort(orders.begin(), orders.end(), std::greater<std::uint32_t>());
  if (orders.size() > da::kMaxComponents) {
    throw std::runtime_error(
        "formulaic q-order component signature is too wide");
  }
  std::array<std::uint32_t, da::kMaxComponents + 1U> result{};
  std::copy(orders.begin(), orders.end(), result.begin());
  result.back() = q;
  return result;
}

sparkinterval::Sha256Digest formulaicQOrderDigest(
    const char* domain, std::size_t domainBytes,
    const std::vector<FormulaicQOrderRecord>& records) {
  sparkinterval::detail::Sha256 digest;
  digest.update(domain, domainBytes);
  for (const auto& record : records) {
    digest.update(&record, sizeof(record));
  }
  return digest.finish();
}

FormulaicQOrder loadFormulaicQOrder(
    const std::filesystem::path& path,
    bool allowFullSource = false) {
  const auto status = std::filesystem::symlink_status(path);
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    throw std::runtime_error(
        "formulaic TGDQORD1 is not a non-symlink regular file");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error("cannot open formulaic TGDQORD1");
  }
  const auto end = input.tellg();
  const auto maximumBytes =
      sizeof(FormulaicQOrderHeader) +
      static_cast<std::uint64_t>(kFormulaicQStop - kFormulaicQStart + 1U) *
          sizeof(FormulaicQOrderRecord);
  if (end < static_cast<std::streamoff>(sizeof(FormulaicQOrderHeader)) ||
      static_cast<std::uint64_t>(end) > maximumBytes) {
    throw std::runtime_error(
        "formulaic TGDQORD1 size is outside its fixed bound");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(raw.data()),
             static_cast<std::streamsize>(raw.size()));
  if (!input) {
    throw std::runtime_error("cannot read formulaic TGDQORD1");
  }

  FormulaicQOrder result;
  std::memcpy(&result.header, raw.data(), sizeof(result.header));
  const auto& header = result.header;
  const bool fullSource =
      header.classification == kFormulaicFullSourceSchedule;
  if (std::memcmp(header.magic, kFormulaicQOrderMagic, 8U) != 0 ||
      header.version != kFormulaicQOrderVersion ||
      (header.classification != kFormulaicBoundedSchedule &&
       !(allowFullSource && fullSource)) ||
      header.primitive_roster_version !=
          kFormulaicPrimitiveRosterVersion ||
      header.record_size != sizeof(FormulaicQOrderRecord) ||
      header.q_count == 0U ||
      header.q_count >
          static_cast<std::uint64_t>(
              kFormulaicQStop - kFormulaicQStart + 1U) ||
      raw.size() !=
          sizeof(FormulaicQOrderHeader) +
              header.q_count * sizeof(FormulaicQOrderRecord)) {
    throw std::runtime_error(
        "formulaic service currently requires a bounded TGDQORD1");
  }
  result.execution.resize(static_cast<std::size_t>(header.q_count));
  std::memcpy(
      result.execution.data(), raw.data() + sizeof(FormulaicQOrderHeader),
      result.execution.size() * sizeof(FormulaicQOrderRecord));
  result.fileSha256 = sparkinterval::sha256(raw.data(), raw.size());

  std::vector<bool> seen(kFormulaicQStop + 1U, false);
  std::uint64_t rows = 0U;
  std::uint32_t minimumQ = kFormulaicQStop;
  std::uint32_t maximumQ = kFormulaicQStart;
  for (const auto& record : result.execution) {
    if (!formulaicHasPrimitiveCharacter(record.q) || seen[record.q] ||
        record.t_index_count == 0U ||
        record.t_index_count > maximumTIndex(record.q) + 1U) {
      throw std::runtime_error(
          "formulaic q-order record is duplicate or outside primitive V2");
    }
    seen[record.q] = true;
    if (rows > std::numeric_limits<std::uint64_t>::max() -
                   record.t_index_count) {
      throw std::runtime_error("formulaic q-order row count overflow");
    }
    rows += record.t_index_count;
    minimumQ = std::min(minimumQ, record.q);
    maximumQ = std::max(maximumQ, record.q);
  }
  if (rows != header.t_row_count || minimumQ != header.q_start ||
      maximumQ != header.q_stop) {
    throw std::runtime_error(
        "formulaic q-order range or row coverage differs");
  }
  for (std::size_t index = 1U; index < result.execution.size(); ++index) {
    if (!(formulaicQOrderKey(result.execution[index - 1U].q) <
          formulaicQOrderKey(result.execution[index].q))) {
      throw std::runtime_error(
          "formulaic q-order is not the canonical execution permutation");
    }
  }
  auto source = result.execution;
  std::sort(source.begin(), source.end(),
            [](const auto& left, const auto& right) {
              return left.q < right.q;
            });
  const auto sourceDigest = formulaicQOrderDigest(
      kFormulaicSourceRosterDomain,
      sizeof(kFormulaicSourceRosterDomain) - 1U, source);
  const auto executionDigest = formulaicQOrderDigest(
      kFormulaicExecutionOrderDomain,
      sizeof(kFormulaicExecutionOrderDomain) - 1U, result.execution);
  if (!std::equal(sourceDigest.begin(), sourceDigest.end(),
                  header.source_roster_sha256) ||
      !std::equal(executionDigest.begin(), executionDigest.end(),
                  header.execution_order_sha256) ||
      (fullSource &&
       (header.q_count != kFormulaicSourceQCount ||
        header.t_row_count != kFormulaicSourceRowCount ||
        header.q_start != kFormulaicQStart ||
        header.q_stop != kFormulaicQStop ||
        sparkinterval::lowercase_hex(sourceDigest) !=
            kFormulaicSourceRosterSha256 ||
        sparkinterval::lowercase_hex(executionDigest) !=
            kFormulaicSourceExecutionSha256))) {
    throw std::runtime_error("formulaic q-order digest differs");
  }
  return result;
}

void formulaicCheckedByteAdd(std::uint64_t* value, std::size_t increment) {
  if (*value > std::numeric_limits<std::uint64_t>::max() - increment) {
    throw std::runtime_error("formulaic input byte count overflow");
  }
  *value += increment;
}

void formulaicReadRaw(
    std::istream& input, void* destination, std::size_t bytes,
    const char* label, sparkinterval::detail::Sha256* inputDigest,
    sparkinterval::detail::Sha256* frameDigest,
    std::uint64_t* inputBytes) {
  if (bytes >
      static_cast<std::size_t>(
          std::numeric_limits<std::streamsize>::max())) {
    throw std::runtime_error(
        std::string("formulaic ") + label + " is too large");
  }
  input.read(reinterpret_cast<char*>(destination),
             static_cast<std::streamsize>(bytes));
  if (!input) {
    throw std::runtime_error(std::string("truncated formulaic ") + label);
  }
  if (inputDigest != nullptr) inputDigest->update(destination, bytes);
  if (frameDigest != nullptr) frameDigest->update(destination, bytes);
  if (inputBytes != nullptr) formulaicCheckedByteAdd(inputBytes, bytes);
}

template <typename T>
void formulaicReadObject(
    std::istream& input, T* value, const char* label,
    sparkinterval::detail::Sha256* inputDigest,
    sparkinterval::detail::Sha256* frameDigest,
    std::uint64_t* inputBytes) {
  formulaicReadRaw(input, value, sizeof(T), label, inputDigest, frameDigest,
                   inputBytes);
}

template <typename T>
void formulaicReadArray(
    std::istream& input, std::vector<T>* values, std::size_t count,
    const char* label, sparkinterval::detail::Sha256* inputDigest,
    sparkinterval::detail::Sha256* frameDigest,
    std::uint64_t* inputBytes) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(
        std::string("formulaic ") + label + " count overflow");
  }
  values->resize(count);
  formulaicReadRaw(input, values->data(), count * sizeof(T), label,
                   inputDigest, frameDigest, inputBytes);
}

void formulaicValidateFrameHeader(
    const fq::ServiceHeader& service,
    const fq::ServiceFrameHeader& frame, const fq::Target& target,
    const std::vector<lb::ResidueDescriptor>& descriptors) {
  const auto orders = canonicalOrders(target.q);
  const auto targetSha = fq::targetDigest(target);
  const std::uint64_t batch = target.batch_count;
  if (std::memcmp(frame.magic, fq::kServiceFrameMagic, 8U) != 0 ||
      frame.version != fq::kServiceFormatVersion ||
      frame.reserved != 0U ||
      frame.execution_q_index != target.execution_q_index ||
      frame.q != target.q || frame.lane_index != target.lane_index ||
      frame.first_t_index != target.first_t_index ||
      frame.t_index_stop_exclusive != target.t_index_stop_exclusive ||
      frame.batch_count != target.batch_count ||
      frame.batch_count == 0U ||
      frame.batch_count > service.maximum_batch_count ||
      frame.component_count != orders.size() ||
      frame.group_order != descriptors.size() ||
      frame.value_count != batch * descriptors.size() ||
      frame.lattice_payload_bytes !=
          batch * service.row_payload_bytes ||
      frame.factor_bytes != batch * sizeof(lb::FrameFactor) ||
      frame.tail_bytes != batch * sizeof(double) ||
      frame.first_t_numerator !=
          static_cast<std::int64_t>(
              static_cast<std::uint64_t>(target.first_t_index) *
              lb::kSourceTStepNumerator) ||
      frame.t_denominator != lb::kSourceTDenominator ||
      frame.t_step_numerator != lb::kSourceTStepNumerator ||
      !std::equal(targetSha.begin(), targetSha.end(),
                  frame.target_sha256)) {
    throw std::runtime_error(
        "formulaic frame header is malformed, skipped, or reordered");
  }
}

void runFormulaicQMajorService(
    const AuthenticatedSeeds& seeds,
    const std::filesystem::path& schedulePath,
    const std::array<unsigned char, 32>& expectedPlanSha256,
    const std::filesystem::path& summaryPath, std::uint32_t device) {
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error(
        "refusing to replace formulaic service summary");
  }
  const auto schedule = loadFormulaicQOrder(schedulePath);
  selectDevice(device);

  sparkinterval::detail::Sha256 inputDigest;
  sparkinterval::detail::Sha256 frameStreamDigest;
  sparkinterval::detail::Sha256 outputDigest;
  std::uint64_t inputBytes = 0U;
  fq::ServiceHeader service{};
  formulaicReadObject(std::cin, &service, "service header", &inputDigest,
                      nullptr, &inputBytes);
  const auto seedSha256 = seededParseDigest(seeds.sha256);
  if (std::memcmp(service.magic, fq::kServiceHeaderMagic, 8U) != 0 ||
      service.version != fq::kServiceFormatVersion ||
      service.schedule_classification != kFormulaicBoundedSchedule ||
      service.maximum_batch_count == 0U ||
      service.maximum_batch_count > fq::kMaximumBatchCount ||
      service.lane_count == 0U ||
      service.lane_count > fq::kMaximumLaneCount ||
      service.start_execution_q_index >=
          service.stop_execution_q_index ||
      service.stop_execution_q_index > schedule.execution.size() ||
      service.frame_header_bytes != sizeof(fq::ServiceFrameHeader) ||
      service.row_header_bytes != sizeof(tms::RowHeader) ||
      service.row_payload_bytes !=
          static_cast<std::uint64_t>(dl::kLatticeCellCount) *
              sizeof(ComplexInterval) ||
      service.factor_record_bytes != sizeof(lb::FrameFactor) ||
      service.tail_record_bytes != sizeof(double) ||
      !std::equal(schedule.fileSha256.begin(), schedule.fileSha256.end(),
                  service.schedule_manifest_sha256) ||
      !std::equal(expectedPlanSha256.begin(), expectedPlanSha256.end(),
                  service.plan_sha256) ||
      !std::equal(seedSha256.begin(), seedSha256.end(),
                  service.recovery_seed_sha256)) {
    throw std::runtime_error(
        "formulaic service header, artifact pin, or bound differs");
  }

  std::vector<fq::ServiceLaneRecord> laneRecords;
  formulaicReadArray(
      std::cin, &laneRecords, service.lane_count, "lane table",
      &inputDigest, nullptr, &inputBytes);
  std::vector<fq::LaneRange> lanes;
  lanes.reserve(laneRecords.size());
  for (const auto& lane : laneRecords) {
    if (lane.reserved != 0U) {
      throw std::runtime_error("formulaic lane reserved field is nonzero");
    }
    lanes.push_back(
        {lane.lane_index, lane.first_t_index,
         lane.t_index_stop_exclusive});
  }
  std::vector<fq::ScheduleRecord> cursorSchedule;
  cursorSchedule.reserve(schedule.execution.size());
  for (const auto& record : schedule.execution) {
    cursorSchedule.push_back({record.q, record.t_index_count});
  }
  const auto startIndex =
      static_cast<std::size_t>(service.start_execution_q_index);
  const auto stopIndex =
      static_cast<std::size_t>(service.stop_execution_q_index);
  sparkinterval::Sha256Digest scheduleExecutionOrderSha256{};
  std::copy(
      std::begin(schedule.header.execution_order_sha256),
      std::end(schedule.header.execution_order_sha256),
      scheduleExecutionOrderSha256.begin());
  const auto canonicalPlanSha256 = fq::planDigest(
      schedule.fileSha256, fq::kBoundedScheduleClassification,
      scheduleExecutionOrderSha256, lanes, startIndex, stopIndex,
      service.maximum_batch_count);
  if (canonicalPlanSha256 != expectedPlanSha256 ||
      !std::equal(
          canonicalPlanSha256.begin(), canonicalPlanSha256.end(),
          service.plan_sha256)) {
    throw std::runtime_error(
        "formulaic canonical Python plan digest differs");
  }
  const auto accounting = fq::compressedAccounting(
      cursorSchedule, lanes, startIndex, stopIndex,
      service.maximum_batch_count);
  if (service.target_count != accounting.target_count ||
      service.row_reference_count != accounting.row_reference_count) {
    throw std::runtime_error(
        "formulaic service compressed accounting differs");
  }
  fq::Cursor cursor(
      cursorSchedule, lanes, expectedPlanSha256, startIndex, stopIndex,
      service.maximum_batch_count);
  SeededPlan plan(seeds);
  std::vector<lb::ResidueDescriptor> cachedDescriptors;
  std::uint32_t cachedQ = 0U;
  std::uint64_t descriptorReconstructions = 0U;
  std::uint64_t targets = 0U;
  std::uint64_t rows = 0U;
  std::uint64_t values = 0U;
  std::uint64_t elapsed = 0U;
  std::signal(SIGPIPE, SIG_IGN);

  while (targets < service.target_count) {
    const auto expected = cursor.expectedTarget();
    if (!expected.has_value()) {
      throw std::runtime_error(
          "formulaic input has targets after exact cursor coverage");
    }
    fq::ServiceFrameHeader frameHeader{};
    formulaicReadObject(
        std::cin, &frameHeader, "frame header", &inputDigest,
        &frameStreamDigest, &inputBytes);
    if (cachedQ != expected->q) {
      cachedDescriptors = canonicalDescriptors(expected->q);
      cachedQ = expected->q;
      ++descriptorReconstructions;
    }
    formulaicValidateFrameHeader(
        service, frameHeader, *expected, cachedDescriptors);
    const std::uint64_t requiredX =
        static_cast<std::uint64_t>(rs::kSourceM) * expected->q +
        expected->q - 1U;
    if (seeds.header.x_stop < requiredX) {
      throw std::runtime_error(
          "seed artifact does not cover formulaic frame q");
    }

    sparkinterval::detail::Sha256 rowBinding;
    rowBinding.update(
        fq::kServiceRowBindingDomain,
        sizeof(fq::kServiceRowBindingDomain));
    rowBinding.update(
        service.lattice_source_sha256,
        sizeof(service.lattice_source_sha256));
    fq::appendTarget(&rowBinding, *expected);
    std::vector<ComplexInterval> lattices;
    lattices.reserve(
        static_cast<std::size_t>(expected->batch_count) *
        dl::kLatticeCellCount);
    for (std::uint32_t index = 0U; index < expected->batch_count;
         ++index) {
      tms::RowHeader row{};
      formulaicReadObject(
          std::cin, &row, "row header", &inputDigest,
          &frameStreamDigest, &inputBytes);
      const auto oldSize = lattices.size();
      lattices.resize(oldSize + dl::kLatticeCellCount);
      formulaicReadRaw(
          std::cin, lattices.data() + oldSize,
          dl::kLatticeCellCount * sizeof(lattices[0]), "row payload",
          &inputDigest, &frameStreamDigest, &inputBytes);
      sparkinterval::detail::Sha256 payloadDigest;
      payloadDigest.update(
          lattices.data() + oldSize,
          dl::kLatticeCellCount * sizeof(lattices[0]));
      const auto payloadSha256 = payloadDigest.finish();
      const auto expectedT =
          static_cast<std::uint64_t>(expected->first_t_index) + index;
      if (std::memcmp(row.magic, tms::kRowMagic, 8U) != 0 ||
          row.version != tms::kFormatVersion || row.reserved != 0U ||
          row.t_index != expectedT ||
          row.payload_bytes != service.row_payload_bytes ||
          !std::equal(payloadSha256.begin(), payloadSha256.end(),
                      row.payload_sha256) ||
          !std::all_of(
              lattices.begin() + static_cast<std::ptrdiff_t>(oldSize),
              lattices.end(), [](const auto& value) {
                return finiteOrdered(value);
              })) {
        throw std::runtime_error(
            "formulaic row is malformed, substituted, or reordered");
      }
      rowBinding.update(&row.t_index, sizeof(row.t_index));
      rowBinding.update(row.payload_sha256, sizeof(row.payload_sha256));
    }
    const auto rowBindingSha256 = rowBinding.finish();
    if (!std::equal(rowBindingSha256.begin(), rowBindingSha256.end(),
                    frameHeader.row_bindings_sha256)) {
      throw std::runtime_error(
          "formulaic frame row binding differs");
    }

    std::vector<lb::FrameFactor> factors;
    std::vector<double> tails;
    formulaicReadArray(
        std::cin, &factors, expected->batch_count, "factor sidecar",
        &inputDigest, &frameStreamDigest, &inputBytes);
    formulaicReadArray(
        std::cin, &tails, expected->batch_count, "tail sidecar",
        &inputDigest, &frameStreamDigest, &inputBytes);
    if (!std::all_of(factors.begin(), factors.end(), [](const auto& value) {
          return finiteOrdered(value.q_to_the_minus_s);
        }) ||
        !std::all_of(tails.begin(), tails.end(), [](double value) {
          return std::isfinite(value) && value >= 0.0;
        })) {
      throw std::runtime_error(
          "formulaic factor or tail sidecar is malformed");
    }
    sparkinterval::detail::Sha256 sidecarDigest;
    sidecarDigest.update(
        fq::kServiceSidecarDomain,
        sizeof(fq::kServiceSidecarDomain));
    sidecarDigest.update(
        service.sidecar_source_sha256,
        sizeof(service.sidecar_source_sha256));
    fq::appendTarget(&sidecarDigest, *expected);
    sidecarDigest.update(
        factors.data(), factors.size() * sizeof(factors[0]));
    sidecarDigest.update(tails.data(), tails.size() * sizeof(tails[0]));
    const auto sidecarSha256 = sidecarDigest.finish();
    if (!std::equal(sidecarSha256.begin(), sidecarSha256.end(),
                    frameHeader.sidecar_sha256)) {
      throw std::runtime_error(
          "formulaic frame sidecar binding differs");
    }

    SeededFrame frame;
    std::memcpy(frame.header.magic, kSeededInputMagic, 8U);
    frame.header.version = 2U;
    frame.header.q = expected->q;
    frame.header.lattice_rows = dl::kLatticeRows;
    frame.header.taylor_degree = dl::kTaylorDegree;
    frame.header.component_count = frameHeader.component_count;
    frame.header.batch_count = expected->batch_count;
    frame.header.m = rs::kSourceM;
    frame.header.group_order = frameHeader.group_order;
    frame.header.first_t_numerator = frameHeader.first_t_numerator;
    frame.header.t_denominator = frameHeader.t_denominator;
    frame.header.t_step_numerator = frameHeader.t_step_numerator;
    frame.header.lattice_cell_count =
        static_cast<std::uint64_t>(expected->batch_count) *
        dl::kLatticeCellCount;
    frame.header.value_count = frameHeader.value_count;
    frame.descriptors = cachedDescriptors;
    frame.factors = std::move(factors);
    frame.lattices = std::move(lattices);
    frame.tailRadii = std::move(tails);
    auto [result, frameElapsed] = plan.execute(frame, 1U);
    writeSeededOutput(std::cout, frame, result, &outputDigest);
    std::cout.flush();
    if (!std::cout) {
      throw std::runtime_error(
          "cannot flush formulaic TGDAFFI1 output stream");
    }
    cursor.accept(*expected);
    ++targets;
    rows += expected->batch_count;
    values += frameHeader.value_count;
    elapsed += frameElapsed;
  }
  const auto bytesBeforeFooter = inputBytes;
  fq::ServiceFooter footer{};
  formulaicReadObject(
      std::cin, &footer, "service footer", &inputDigest, nullptr,
      &inputBytes);
  if (std::cin.peek() != std::istream::traits_type::eof()) {
    throw std::runtime_error(
        "trailing bytes after formulaic service footer");
  }
  const auto session = cursor.finish();
  const auto frameStreamSha256 = frameStreamDigest.finish();
  if (std::memcmp(footer.magic, fq::kServiceFooterMagic, 8U) != 0 ||
      footer.version != fq::kServiceFormatVersion ||
      footer.reserved != 0U || footer.target_count != targets ||
      footer.row_reference_count != rows ||
      footer.value_count != values ||
      footer.descriptor_reconstruction_count !=
          descriptorReconstructions ||
      footer.descriptor_h2d_upload_count !=
          plan.descriptorUploadCount() ||
      footer.lattice_h2d_upload_count != plan.latticeUploadCount() ||
      footer.input_bytes_before_footer != bytesBeforeFooter ||
      !std::equal(
          session.target_chain_sha256.begin(),
          session.target_chain_sha256.end(),
          footer.target_chain_sha256) ||
      !std::equal(
          frameStreamSha256.begin(), frameStreamSha256.end(),
          footer.frame_stream_sha256) ||
      !std::all_of(
          std::begin(footer.reserved_sha256),
          std::end(footer.reserved_sha256),
          [](unsigned char value) { return value == 0U; }) ||
      targets != accounting.target_count ||
      rows != accounting.row_reference_count ||
      descriptorReconstructions != accounting.q_count ||
      plan.descriptorUploadCount() != descriptorReconstructions ||
      plan.latticeUploadCount() != targets) {
    throw std::runtime_error(
        "formulaic footer, cursor, or execution accounting differs");
  }

  const auto inputSha256 = inputDigest.finish();
  const auto outputSha256 = outputDigest.finish();
  const auto temporary = summaryPath.string() + ".tmp." +
                         std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    if (!summary) {
      throw std::runtime_error(
          "cannot create formulaic service summary");
    }
    summary
        << "{\"algorithm_id\":"
           "\"platt-dirichlet-formulaic-qmajor-seeded-cuda-v1\""
        << ",\"all_character_fft_executed\":false"
        << ",\"canonical_descriptor_input_bytes\":0"
        << ",\"classification\":"
           "\"bounded_formulaic_qmajor_cuda_component_not_source_or_zero_closure\""
        << ",\"completed_l_zero_state_validated\":false"
        << ",\"descriptor_h2d_upload_count\":"
        << plan.descriptorUploadCount()
        << ",\"descriptor_reconstruction_count\":"
        << descriptorReconstructions
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"first_execution_q\":"
        << schedule.execution[startIndex].q
        << ",\"formulaic_cursor_consumed_directly\":true"
        << ",\"frame_stream_sha256\":\""
        << sparkinterval::lowercase_hex(frameStreamSha256) << "\""
        << ",\"input_stream_sha256\":\""
        << sparkinterval::lowercase_hex(inputSha256) << "\""
        << ",\"input_stream_size_bytes\":" << inputBytes
        << ",\"last_execution_q\":"
        << schedule.execution[stopIndex - 1U].q
        << ",\"lattice_h2d_upload_count\":"
        << plan.latticeUploadCount()
        << ",\"lattice_source_sha256\":\""
        << tmajorRawDigest(service.lattice_source_sha256) << "\""
        << ",\"maximum_batch_count\":"
        << service.maximum_batch_count
        << ",\"output_stream_sha256\":\""
        << sparkinterval::lowercase_hex(outputSha256) << "\""
        << ",\"plan_sha256\":\""
        << tmajorRawDigest(service.plan_sha256) << "\""
        << ",\"production_run_completed\":false"
        << ",\"recovery_seed_artifact_sha256\":\""
        << seeds.sha256 << "\""
        << ",\"row_reference_count\":" << rows
        << ",\"schedule_execution_order_sha256\":\""
        << tmajorRawDigest(
               schedule.header.execution_order_sha256) << "\""
        << ",\"schedule_manifest_sha256\":\""
        << sparkinterval::lowercase_hex(schedule.fileSha256) << "\""
        << ",\"schedule_source_roster_sha256\":\""
        << tmajorRawDigest(
               schedule.header.source_roster_sha256) << "\""
        << ",\"schema\":"
           "\"sparkinterval.tg.dirichlet_formulaic_qmajor_cuda.summary.v1\""
        << ",\"schema_version\":1"
        << ",\"serialized_control_records_consumed\":0"
        << ",\"sidecar_source_sha256\":\""
        << tmajorRawDigest(service.sidecar_source_sha256) << "\""
        << ",\"source_contract_sha256\":\""
        << tmajorRawDigest(service.source_contract_sha256) << "\""
        << ",\"source_scale_run\":false"
        << ",\"start_execution_q_index\":"
        << service.start_execution_q_index
        << ",\"stop_execution_q_index\":"
        << service.stop_execution_q_index
        << ",\"target_chain_sha256\":\""
        << sparkinterval::lowercase_hex(
               session.target_chain_sha256) << "\""
        << ",\"target_count\":" << targets
        << ",\"transcendental_device_calls\":0"
        << ",\"trusted_execution_attested\":false"
        << ",\"value_count\":" << values
        << ",\"zero_completeness_claimed\":false}\n";
    if (!summary) {
      throw std::runtime_error(
          "cannot write formulaic service summary");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "cannot publish formulaic summary: " + error.message());
  }
}

std::vector<fq::Target> residentPhaseTargets(
    const FormulaicQOrder& schedule, const rqp::Header& header) {
  std::vector<fq::Target> targets;
  std::uint64_t maximumRowCount = 0U;
  for (std::size_t index =
           static_cast<std::size_t>(header.start_execution_q_index);
       index < static_cast<std::size_t>(header.stop_execution_q_index);
       ++index) {
    const auto& record = schedule.execution[index];
    maximumRowCount = std::max<std::uint64_t>(
        maximumRowCount, record.t_index_count);
    const auto activeStop = std::min<std::uint64_t>(
        record.t_index_count, header.t_index_stop_exclusive);
    if (activeStop <= header.first_t_index) continue;
    if (activeStop > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error(
          "resident phase target identity overflows");
    }
    targets.push_back(
        {static_cast<std::uint64_t>(index), record.q, header.phase_index,
         static_cast<std::uint32_t>(header.first_t_index),
         static_cast<std::uint32_t>(activeStop),
         static_cast<std::uint32_t>(
             activeStop - header.first_t_index)});
  }
  if (maximumRowCount < header.t_index_stop_exclusive ||
      targets.empty() || targets.size() > rqp::kMaximumTargets) {
    throw std::runtime_error(
        "resident phase active-q coverage is outside its bound");
  }
  return targets;
}

sparkinterval::Sha256Digest residentRawDigest(
    const unsigned char raw[32]) {
  sparkinterval::Sha256Digest result{};
  std::copy_n(raw, result.size(), result.begin());
  return result;
}

void residentValidateHeader(
    const rqp::Header& header, const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan,
    std::uint64_t actualInputBytes) {
  const auto seedSha256 = seededParseDigest(seeds.sha256);
  if (std::memcmp(header.magic, rqp::kHeaderMagic, 8U) != 0 ||
      header.version != rqp::kFormatVersion ||
      header.schedule_classification != kFormulaicBoundedSchedule ||
      header.maximum_rows != rqp::kMaximumRows ||
      header.maximum_targets != rqp::kMaximumTargets ||
      header.reserved != 0U || header.row_count == 0U ||
      header.row_count > rqp::kMaximumRows ||
      header.target_count == 0U ||
      header.target_count > rqp::kMaximumTargets ||
      header.start_execution_q_index >=
          header.stop_execution_q_index ||
      header.stop_execution_q_index > schedule.execution.size() ||
      header.stop_execution_q_index -
              header.start_execution_q_index >
          rqp::kMaximumScheduleRecords ||
      header.first_t_index >= header.t_index_stop_exclusive ||
      header.t_index_stop_exclusive >
          std::numeric_limits<std::uint32_t>::max() ||
      header.t_index_stop_exclusive - header.first_t_index !=
          header.row_count ||
      header.row_header_bytes != sizeof(tms::RowHeader) ||
      header.row_payload_bytes !=
          static_cast<std::uint64_t>(dl::kLatticeCellCount) *
              sizeof(ComplexInterval) ||
      header.target_header_bytes != sizeof(rqp::TargetHeader) ||
      header.factor_record_bytes != sizeof(lb::FrameFactor) ||
      header.tail_record_bytes != sizeof(double) ||
      header.input_size_bytes != actualInputBytes ||
      actualInputBytes > rqp::kMaximumInputBytes ||
      !std::equal(
          schedule.fileSha256.begin(), schedule.fileSha256.end(),
          header.schedule_manifest_sha256) ||
      !std::equal(
          std::begin(schedule.header.execution_order_sha256),
          std::end(schedule.header.execution_order_sha256),
          header.schedule_execution_order_sha256) ||
      !std::equal(
          seedSha256.begin(), seedSha256.end(),
          header.recovery_seed_sha256)) {
    throw std::runtime_error(
        "resident q-major phase header or explicit bound differs");
  }
  const auto derivedPlan = rqp::planDigest(
      schedule.fileSha256,
      residentRawDigest(schedule.header.execution_order_sha256),
      static_cast<std::size_t>(header.start_execution_q_index),
      static_cast<std::size_t>(header.stop_execution_q_index),
      header.phase_index,
      static_cast<std::uint32_t>(header.first_t_index),
      static_cast<std::uint32_t>(
          header.t_index_stop_exclusive));
  if (derivedPlan != expectedPlan ||
      !std::equal(
          derivedPlan.begin(), derivedPlan.end(),
          header.phase_plan_sha256)) {
    throw std::runtime_error(
        "resident q-major canonical phase plan digest differs");
  }
}

void residentValidateTarget(
    const rqp::Header& phase, const rqp::TargetHeader& header,
    const fq::Target& target) {
  const auto orders = canonicalOrders(target.q);
  const auto groupOrder = tmajorTotient(target.q);
  const auto targetSha256 = fq::targetDigest(target);
  if (std::memcmp(header.magic, rqp::kTargetMagic, 8U) != 0 ||
      header.version != rqp::kFormatVersion ||
      header.reserved != 0U ||
      header.execution_q_index != target.execution_q_index ||
      header.q != target.q ||
      header.phase_index != phase.phase_index ||
      header.first_t_index != target.first_t_index ||
      header.t_index_stop_exclusive !=
          target.t_index_stop_exclusive ||
      header.batch_count != target.batch_count ||
      header.component_count != orders.size() ||
      header.group_order != groupOrder ||
      header.value_count !=
          static_cast<std::uint64_t>(target.batch_count) *
              groupOrder ||
      header.factor_bytes !=
          static_cast<std::uint64_t>(target.batch_count) *
              sizeof(lb::FrameFactor) ||
      header.tail_bytes !=
          static_cast<std::uint64_t>(target.batch_count) *
              sizeof(double) ||
      !std::equal(
          targetSha256.begin(), targetSha256.end(),
          header.target_sha256)) {
    throw std::runtime_error(
        "resident phase target is substituted, skipped, or malformed");
  }
}

sparkinterval::Sha256Digest residentSidecarDigest(
    const rqp::Header& phase, const fq::Target& target,
    const std::vector<lb::FrameFactor>& factors,
    const std::vector<double>& tails) {
  sparkinterval::detail::Sha256 digest;
  digest.update(
      rqp::kSidecarDomain, sizeof(rqp::kSidecarDomain));
  digest.update(
      phase.sidecar_source_sha256,
      sizeof(phase.sidecar_source_sha256));
  digest.update(
      phase.phase_plan_sha256,
      sizeof(phase.phase_plan_sha256));
  fq::appendTarget(&digest, target);
  digest.update(
      factors.data(), factors.size() * sizeof(factors[0]));
  digest.update(tails.data(), tails.size() * sizeof(tails[0]));
  return digest.finish();
}

struct ResidentPhaseAudit {
  rqp::Header header{};
  rqp::Footer footer{};
  std::vector<fq::Target> targets;
  std::string inputSha256;
};

struct ResidentPhaseMemoryPreflight {
  std::uint64_t freeBytes = 0U;
  std::uint64_t knownAllocationBytes = 0U;
};

ResidentPhaseMemoryPreflight residentMemoryPreflight(
    const AuthenticatedSeeds& seeds, const ResidentPhaseAudit& audit) {
  std::uint64_t maximumGroupOrder = 0U;
  std::uint64_t maximumBatch = 0U;
  std::uint64_t maximumValues = 0U;
  for (const auto& target : audit.targets) {
    const auto groupOrder = tmajorTotient(target.q);
    maximumGroupOrder = std::max(maximumGroupOrder, groupOrder);
    maximumBatch = std::max<std::uint64_t>(
        maximumBatch, target.batch_count);
    maximumValues = std::max(
        maximumValues,
        static_cast<std::uint64_t>(target.batch_count) *
            groupOrder);
  }
  ResidentPhaseMemoryPreflight result;
  fq::checkedAdd(
      &result.knownAllocationBytes,
      seeds.records.size() * sizeof(seeds.records[0]),
      "resident phase seed allocation size overflow");
  fq::checkedAdd(
      &result.knownAllocationBytes,
      audit.header.row_count * audit.header.row_payload_bytes,
      "resident phase lattice allocation size overflow");
  fq::checkedAdd(
      &result.knownAllocationBytes,
      maximumGroupOrder * sizeof(lb::ResidueDescriptor),
      "resident phase descriptor allocation size overflow");
  fq::checkedAdd(
      &result.knownAllocationBytes,
      maximumBatch * sizeof(lb::FrameFactor),
      "resident phase factor allocation size overflow");
  fq::checkedAdd(
      &result.knownAllocationBytes,
      maximumBatch * sizeof(double),
      "resident phase tail allocation size overflow");
  fq::checkedAdd(
      &result.knownAllocationBytes,
      maximumValues * sizeof(ComplexInterval),
      "resident phase output allocation size overflow");
  std::size_t freeBytes = 0U;
  std::size_t totalBytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&freeBytes, &totalBytes));
  (void)totalBytes;
  result.freeBytes = freeBytes;
  if (result.knownAllocationBytes >
          std::numeric_limits<std::uint64_t>::max() -
              rqp::kDeviceMemorySafetyReserveBytes ||
      result.knownAllocationBytes +
              rqp::kDeviceMemorySafetyReserveBytes >
          result.freeBytes) {
    throw std::runtime_error(
        "resident phase device-memory preflight failed");
  }
  return result;
}

ResidentPhaseAudit auditResidentPhase(
    const std::filesystem::path& inputPath,
    const std::string& expectedInputSha256,
    const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan) {
  const auto linkStatus = std::filesystem::symlink_status(inputPath);
  if (std::filesystem::is_symlink(linkStatus) ||
      !std::filesystem::is_regular_file(linkStatus)) {
    throw std::runtime_error(
        "resident phase input is not a non-symlink regular file");
  }
  const auto beforeSize = std::filesystem::file_size(inputPath);
  if (beforeSize == 0U || beforeSize > rqp::kMaximumInputBytes) {
    throw std::runtime_error(
        "resident phase input size is outside its bound");
  }
  const auto actual = seededHashFile(inputPath);
  if (sparkinterval::lowercase_hex(actual) != expectedInputSha256) {
    throw std::runtime_error(
        "resident phase input SHA-256 differs before parsing");
  }
  std::ifstream input(inputPath, std::ios::binary);
  if (!input) {
    throw std::runtime_error("cannot open resident phase input");
  }
  ResidentPhaseAudit audit;
  sparkinterval::detail::Sha256 inputDigest;
  seededReadExact(input, &audit.header, "resident phase header");
  tmajorDigestObject(&inputDigest, audit.header);
  residentValidateHeader(
      audit.header, schedule, seeds, expectedPlan, beforeSize);
  audit.targets = residentPhaseTargets(schedule, audit.header);
  if (audit.targets.size() != audit.header.target_count) {
    throw std::runtime_error(
        "resident phase active target count differs");
  }

  sparkinterval::detail::Sha256 rowStream;
  sparkinterval::detail::Sha256 rowBinding;
  rowBinding.update(
      rqp::kRowBindingDomain, sizeof(rqp::kRowBindingDomain));
  rowBinding.update(
      audit.header.lattice_source_sha256,
      sizeof(audit.header.lattice_source_sha256));
  rowBinding.update(
      audit.header.phase_plan_sha256,
      sizeof(audit.header.phase_plan_sha256));
  for (std::uint32_t index = 0U;
       index < audit.header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(input, &row, "resident phase row header");
    tmajorDigestObject(&inputDigest, row);
    tmajorDigestObject(&rowStream, row);
    std::vector<ComplexInterval> payload;
    tmajorReadVector(
        input, &payload, dl::kLatticeCellCount,
        "resident phase row payload", &inputDigest, &rowStream);
    sparkinterval::detail::Sha256 payloadDigest;
    payloadDigest.update(
        payload.data(), payload.size() * sizeof(payload[0]));
    const auto payloadSha256 = payloadDigest.finish();
    if (std::memcmp(row.magic, tms::kRowMagic, 8U) != 0 ||
        row.version != tms::kFormatVersion ||
        row.reserved != 0U ||
        row.t_index != audit.header.first_t_index + index ||
        row.payload_bytes != audit.header.row_payload_bytes ||
        !std::equal(
            payloadSha256.begin(), payloadSha256.end(),
            row.payload_sha256) ||
        !std::all_of(
            payload.begin(), payload.end(), [](const auto& value) {
              return finiteOrdered(value);
            })) {
      throw std::runtime_error(
          "resident phase row is substituted or malformed");
    }
    rowBinding.update(&row.t_index, sizeof(row.t_index));
    rowBinding.update(
        row.payload_sha256, sizeof(row.payload_sha256));
  }
  const auto rowBindingSha256 = rowBinding.finish();
  if (!std::equal(
          rowBindingSha256.begin(), rowBindingSha256.end(),
          audit.header.row_bindings_sha256)) {
    throw std::runtime_error(
        "resident phase row binding differs");
  }

  sparkinterval::detail::Sha256 targetStream;
  auto targetChain =
      rqp::initialTargetChain(residentRawDigest(
          audit.header.phase_plan_sha256));
  std::uint64_t rowReferences = 0U;
  std::uint64_t values = 0U;
  std::uint64_t sidecarBytes = 0U;
  std::uint64_t exactInputBytes =
      sizeof(rqp::Header) +
      static_cast<std::uint64_t>(audit.header.row_count) *
          (sizeof(tms::RowHeader) +
           audit.header.row_payload_bytes) +
      sizeof(rqp::Footer);
  for (const auto& target : audit.targets) {
    rqp::TargetHeader header{};
    seededReadExact(input, &header, "resident phase target");
    tmajorDigestObject(&inputDigest, header);
    tmajorDigestObject(&targetStream, header);
    residentValidateTarget(audit.header, header, target);
    std::vector<lb::FrameFactor> factors;
    std::vector<double> tails;
    tmajorReadVector(
        input, &factors, target.batch_count,
        "resident phase factors", &inputDigest, &targetStream);
    tmajorReadVector(
        input, &tails, target.batch_count,
        "resident phase tails", &inputDigest, &targetStream);
    if (!std::all_of(
            factors.begin(), factors.end(), [](const auto& value) {
              return finiteOrdered(value.q_to_the_minus_s);
            }) ||
        !std::all_of(tails.begin(), tails.end(), [](double value) {
          return std::isfinite(value) && value >= 0.0;
        })) {
      throw std::runtime_error(
          "resident phase factor or tail is malformed");
    }
    const auto sidecar =
        residentSidecarDigest(audit.header, target, factors, tails);
    if (!std::equal(
            sidecar.begin(), sidecar.end(),
            header.sidecar_sha256)) {
      throw std::runtime_error(
          "resident phase sidecar digest differs");
    }
    fq::checkedAdd(
        &rowReferences, target.batch_count,
        "resident phase row-reference count overflow");
    fq::checkedAdd(
        &values, header.value_count,
        "resident phase value count overflow");
    fq::checkedAdd(
        &sidecarBytes, header.factor_bytes + header.tail_bytes,
        "resident phase sidecar count overflow");
    fq::checkedAdd(
        &exactInputBytes,
        sizeof(rqp::TargetHeader) +
            header.factor_bytes + header.tail_bytes,
        "resident phase input size overflow");
    targetChain = rqp::advanceTargetChain(targetChain, target);
  }
  if (values != audit.header.value_count ||
      values > rqp::kMaximumValues ||
      exactInputBytes != beforeSize) {
    throw std::runtime_error(
        "resident phase declared accounting differs");
  }
  const auto bytesBeforeFooter =
      exactInputBytes - sizeof(rqp::Footer);
  seededReadExact(input, &audit.footer, "resident phase footer");
  tmajorDigestObject(&inputDigest, audit.footer);
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error(
        "trailing bytes after resident phase footer");
  }
  const auto rowStreamSha256 = rowStream.finish();
  const auto targetStreamSha256 = targetStream.finish();
  if (std::memcmp(
          audit.footer.magic, rqp::kFooterMagic, 8U) != 0 ||
      audit.footer.version != rqp::kFormatVersion ||
      audit.footer.reserved != 0U ||
      audit.footer.row_count != audit.header.row_count ||
      audit.footer.target_count != audit.targets.size() ||
      audit.footer.target_row_reference_count != rowReferences ||
      audit.footer.value_count != values ||
      audit.footer.sidecar_bytes != sidecarBytes ||
      audit.footer.input_bytes_before_footer != bytesBeforeFooter ||
      audit.footer.descriptor_reconstruction_count !=
          audit.targets.size() ||
      audit.footer.descriptor_h2d_upload_count !=
          audit.targets.size() ||
      audit.footer.lattice_h2d_upload_count != 1U ||
      !std::equal(
          targetChain.begin(), targetChain.end(),
          audit.footer.target_chain_sha256) ||
      !std::equal(
          rowStreamSha256.begin(), rowStreamSha256.end(),
          audit.footer.row_stream_sha256) ||
      !std::equal(
          targetStreamSha256.begin(), targetStreamSha256.end(),
          audit.footer.target_stream_sha256) ||
      !std::all_of(
          std::begin(audit.footer.reserved_sha256),
          std::end(audit.footer.reserved_sha256),
          [](unsigned char value) { return value == 0U; })) {
    throw std::runtime_error(
        "resident phase footer, hash, or accounting differs");
  }
  audit.inputSha256 =
      sparkinterval::lowercase_hex(inputDigest.finish());
  if (audit.inputSha256 != expectedInputSha256 ||
      std::filesystem::file_size(inputPath) != beforeSize) {
    throw std::runtime_error(
        "resident phase changed during preflight replay");
  }
  return audit;
}

void runResidentQMajorPhase(
    const AuthenticatedSeeds& seeds,
    const std::filesystem::path& schedulePath,
    const sparkinterval::Sha256Digest& expectedPlan,
    const std::filesystem::path& inputPath,
    const std::string& expectedInputSha256,
    const std::filesystem::path& summaryPath,
    std::uint32_t device, bool allowPrefixKat) {
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error(
        "refusing to replace resident phase summary");
  }
  const auto schedule = loadFormulaicQOrder(schedulePath);
  const auto audit = auditResidentPhase(
      inputPath, expectedInputSha256, schedule, seeds, expectedPlan);
  seededPrefixKatTestBarrier(
      allowPrefixKat,
      "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_RESIDENT_PHASE_PREFLIGHT_BARRIER",
      "resident phase preflight");
  std::uint32_t maximumQ = 0U;
  for (const auto& target : audit.targets) {
    maximumQ = std::max(maximumQ, target.q);
  }
  const std::uint64_t requiredX =
      static_cast<std::uint64_t>(rs::kSourceM) * maximumQ +
      maximumQ - 1U;
  if (seeds.header.x_stop < requiredX) {
    throw std::runtime_error(
        "seed artifact does not cover resident phase q targets");
  }

  selectDevice(device);
  const auto memoryPreflight =
      residentMemoryPreflight(seeds, audit);
  SeededPlan plan(seeds);
  std::ifstream input(inputPath, std::ios::binary);
  if (!input) {
    throw std::runtime_error(
        "cannot reopen resident phase input");
  }
  sparkinterval::detail::Sha256 executionInputDigest;
  rqp::Header header{};
  seededReadExact(input, &header, "resident execution header");
  tmajorDigestObject(&executionInputDigest, header);
  std::vector<ComplexInterval> resident;
  resident.reserve(
      static_cast<std::size_t>(header.row_count) *
      dl::kLatticeCellCount);
  for (std::uint32_t index = 0U; index < header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(input, &row, "resident execution row header");
    tmajorDigestObject(&executionInputDigest, row);
    const auto oldSize = resident.size();
    resident.resize(oldSize + dl::kLatticeCellCount);
    input.read(
        reinterpret_cast<char*>(resident.data() + oldSize),
        static_cast<std::streamsize>(
            dl::kLatticeCellCount * sizeof(resident[0])));
    if (!input) {
      throw std::runtime_error(
          "truncated resident execution lattice row");
    }
    executionInputDigest.update(
        resident.data() + oldSize,
        dl::kLatticeCellCount * sizeof(resident[0]));
  }
  plan.uploadResidentLattices(resident);

  sparkinterval::detail::Sha256 outputDigest;
  std::uint64_t outputBytes = 0U;
  std::uint64_t values = 0U;
  std::uint64_t elapsed = 0U;
  for (const auto& expected : audit.targets) {
    rqp::TargetHeader target{};
    seededReadExact(input, &target, "resident execution target");
    tmajorDigestObject(&executionInputDigest, target);
    residentValidateTarget(header, target, expected);
    SeededFrame frame;
    std::memcpy(frame.header.magic, kSeededInputMagic, 8U);
    frame.header.version = 2U;
    frame.header.q = expected.q;
    frame.header.lattice_rows = dl::kLatticeRows;
    frame.header.taylor_degree = dl::kTaylorDegree;
    frame.header.component_count = target.component_count;
    frame.header.batch_count = expected.batch_count;
    frame.header.m = rs::kSourceM;
    frame.header.group_order = target.group_order;
    frame.header.first_t_numerator =
        static_cast<std::int64_t>(
            static_cast<std::uint64_t>(expected.first_t_index) *
            lb::kSourceTStepNumerator);
    frame.header.t_denominator = lb::kSourceTDenominator;
    frame.header.t_step_numerator = lb::kSourceTStepNumerator;
    frame.header.lattice_cell_count =
        static_cast<std::uint64_t>(expected.batch_count) *
        dl::kLatticeCellCount;
    frame.header.value_count = target.value_count;
    frame.descriptors = canonicalDescriptors(expected.q);
    tmajorReadVector(
        input, &frame.factors, expected.batch_count,
        "resident execution factors", &executionInputDigest);
    tmajorReadVector(
        input, &frame.tailRadii, expected.batch_count,
        "resident execution tails", &executionInputDigest);
    if (!std::all_of(
            frame.factors.begin(), frame.factors.end(),
            [](const auto& value) {
              return finiteOrdered(value.q_to_the_minus_s);
            }) ||
        !std::all_of(
            frame.tailRadii.begin(), frame.tailRadii.end(),
            [](double value) {
              return std::isfinite(value) && value >= 0.0;
            }) ||
        residentSidecarDigest(
            header, expected, frame.factors, frame.tailRadii) !=
            residentRawDigest(target.sidecar_sha256)) {
      throw std::runtime_error(
          "resident execution sidecar changed after preflight");
    }
    auto [result, frameElapsed] = plan.executeResident(frame, 1U);
    writeSeededOutput(std::cout, frame, result, &outputDigest);
    std::cout.flush();
    if (!std::cout) {
      throw std::runtime_error(
          "cannot flush resident phase TGDAFFI1 output");
    }
    fq::checkedAdd(
        &values, target.value_count,
        "resident execution value count overflow");
    fq::checkedAdd(
        &outputBytes,
        sizeof(da::InputHeader) +
            target.value_count * sizeof(ComplexInterval),
        "resident execution output byte count overflow");
    elapsed += frameElapsed;
  }
  rqp::Footer footer{};
  seededReadExact(input, &footer, "resident execution footer");
  tmajorDigestObject(&executionInputDigest, footer);
  const auto executionInputSha256 =
      sparkinterval::lowercase_hex(executionInputDigest.finish());
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(&footer, &audit.footer, sizeof(footer)) != 0 ||
      executionInputSha256 != expectedInputSha256 ||
      values != audit.footer.value_count ||
      plan.latticeUploadCount() != 1U ||
      plan.descriptorUploadCount() != audit.targets.size()) {
    throw std::runtime_error(
        "resident phase execution totals differ after CUDA");
  }

  const auto outputSha256 = outputDigest.finish();
  const auto temporary = summaryPath.string() + ".tmp." +
                         std::to_string(
                             static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    if (!summary) {
      throw std::runtime_error(
          "cannot create resident phase summary");
    }
    summary
        << "{\"algorithm_id\":"
           "\"platt-dirichlet-resident-qmajor-phase-seeded-cuda-v1\""
        << ",\"canonical_descriptor_input_bytes\":0"
        << ",\"classification\":"
           "\"bounded_resident_qmajor_phase_cuda_not_source_or_zero_closure\""
        << ",\"completed_l_zero_state_validated\":false"
        << ",\"descriptor_h2d_upload_count\":"
        << plan.descriptorUploadCount()
        << ",\"descriptor_reconstruction_count\":"
        << audit.targets.size()
        << ",\"device_memory_free_bytes_before_allocations\":"
        << memoryPreflight.freeBytes
        << ",\"device_memory_known_allocation_bytes\":"
        << memoryPreflight.knownAllocationBytes
        << ",\"device_memory_preflight_passed\":true"
        << ",\"device_memory_safety_reserve_bytes\":"
        << rqp::kDeviceMemorySafetyReserveBytes
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"first_t_index\":" << header.first_t_index
        << ",\"h100_source_phase_completed\":false"
        << ",\"input_sha256\":\"" << expectedInputSha256 << "\""
        << ",\"input_size_bytes\":" << header.input_size_bytes
        << ",\"lattice_h2d_upload_count\":"
        << plan.latticeUploadCount()
        << ",\"lattice_source_sha256\":\""
        << tmajorRawDigest(header.lattice_source_sha256) << "\""
        << ",\"output_sha256\":\""
        << sparkinterval::lowercase_hex(outputSha256) << "\""
        << ",\"output_size_bytes\":" << outputBytes
        << ",\"phase_index\":" << header.phase_index
        << ",\"phase_plan_sha256\":\""
        << tmajorRawDigest(header.phase_plan_sha256) << "\""
        << ",\"production_run_completed\":false"
        << ",\"recovery_seed_artifact_sha256\":\""
        << seeds.sha256 << "\""
        << ",\"row_count\":" << header.row_count
        << ",\"row_payload_h2d_bytes\":"
        << header.row_count * header.row_payload_bytes
        << ",\"schedule_execution_order_sha256\":\""
        << tmajorRawDigest(
               schedule.header.execution_order_sha256) << "\""
        << ",\"schedule_manifest_sha256\":\""
        << sparkinterval::lowercase_hex(schedule.fileSha256) << "\""
        << ",\"schedule_source_roster_sha256\":\""
        << tmajorRawDigest(
               schedule.header.source_roster_sha256) << "\""
        << ",\"schema\":"
           "\"sparkinterval.tg.dirichlet_resident_qmajor_phase_cuda.summary.v1\""
        << ",\"schema_version\":1"
        << ",\"sidecar_source_sha256\":\""
        << tmajorRawDigest(header.sidecar_source_sha256) << "\""
        << ",\"source_contract_sha256\":\""
        << tmajorRawDigest(header.source_contract_sha256) << "\""
        << ",\"source_scale_run\":false"
        << ",\"start_execution_q_index\":"
        << header.start_execution_q_index
        << ",\"stop_execution_q_index\":"
        << header.stop_execution_q_index
        << ",\"t_index_stop_exclusive\":"
        << header.t_index_stop_exclusive
        << ",\"target_chain_sha256\":\""
        << tmajorRawDigest(footer.target_chain_sha256) << "\""
        << ",\"target_count\":" << audit.targets.size()
        << ",\"target_row_reference_count\":"
        << footer.target_row_reference_count
        << ",\"transcendental_device_calls\":0"
        << ",\"trusted_execution_attested\":false"
        << ",\"value_count\":" << values
        << ",\"zero_completeness_claimed\":false}\n";
    if (!summary) {
      throw std::runtime_error(
          "cannot write resident phase summary");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "cannot publish resident phase summary: " +
        error.message());
  }
}

}  // namespace

#ifdef SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN
#define main SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN
#endif

int main(int argc, char** argv) {
  try {
    const bool tmajor =
        argc >= 2 && std::string_view(argv[1]) == "--tmajor-block";
    const bool service = argc >= 2 && std::string_view(argv[1]) == "--framed-service";
    const bool formulaic =
        argc >= 2 &&
        std::string_view(argv[1]) == "--formulaic-qmajor-service";
    const bool resident =
        argc >= 2 &&
        std::string_view(argv[1]) == "--resident-qmajor-phase";
    const bool allowPrefixKat =
        (tmajor && argc == 9 &&
         std::string_view(argv[8]) == "--allow-prefix-kat") ||
        (service && argc == 9 &&
         std::string_view(argv[8]) == "--allow-prefix-kat") ||
        (formulaic && argc == 9 &&
         std::string_view(argv[8]) == "--allow-prefix-kat") ||
        (resident && argc == 11 &&
         std::string_view(argv[10]) == "--allow-prefix-kat") ||
        (!tmajor && !service && !formulaic && !resident && argc == 8 &&
         std::string_view(argv[7]) == "--allow-prefix-kat");
    if (resident) {
      if (argc != 10 && !allowPrefixKat) {
        throw std::runtime_error(
            "usage: runner --resident-qmajor-phase SEEDS SHA TGDQORD1 "
            "PHASE_PLAN_SHA INPUT INPUT_SHA SUMMARY DEVICE "
            "[--allow-prefix-kat]");
      }
      const auto expectedSeed = seededParseDigest(argv[3]);
      const auto expectedPlan = seededParseDigest(argv[5]);
      const auto expectedInput = seededParseDigest(argv[7]);
      const auto device = parseUnsigned(argv[9], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "resident q-major phase device is invalid");
      }
      const auto seeds =
          loadAuthenticatedSeeds(argv[2], expectedSeed, allowPrefixKat);
      runResidentQMajorPhase(
          seeds, argv[4], expectedPlan, argv[6],
          sparkinterval::lowercase_hex(expectedInput), argv[8],
          static_cast<std::uint32_t>(device), allowPrefixKat);
      return 0;
    }
    if (formulaic) {
      if (argc != 8 && !allowPrefixKat) {
        throw std::runtime_error(
            "usage: runner --formulaic-qmajor-service SEEDS SHA TGDQORD1 "
            "PLAN_SHA SUMMARY DEVICE [--allow-prefix-kat]");
      }
      const auto expectedSeed = seededParseDigest(argv[3]);
      const auto expectedPlan = seededParseDigest(argv[5]);
      const auto device = parseUnsigned(argv[7], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "formulaic q-major device is invalid");
      }
      const auto seeds =
          loadAuthenticatedSeeds(argv[2], expectedSeed, allowPrefixKat);
      runFormulaicQMajorService(
          seeds, argv[4], expectedPlan, argv[6],
          static_cast<std::uint32_t>(device));
      return 0;
    }
    if (tmajor) {
      if (argc != 8 && !allowPrefixKat) {
        throw std::runtime_error(
            "usage: runner --tmajor-block SEEDS SHA INPUT INPUT_SHA SUMMARY "
            "DEVICE [--allow-prefix-kat]");
      }
      const auto expectedSeed = seededParseDigest(argv[3]);
      const auto expectedInput = seededParseDigest(argv[5]);
      const auto device = parseUnsigned(argv[7], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("t-major device is invalid");
      }
      const auto seeds =
          loadAuthenticatedSeeds(argv[2], expectedSeed, allowPrefixKat);
      runTMajorBlock(
          seeds, argv[4], sparkinterval::lowercase_hex(expectedInput),
          argv[6], static_cast<std::uint32_t>(device), allowPrefixKat);
      return 0;
    }
    if (service) {
      if (argc != 8 && !allowPrefixKat) {
        throw std::runtime_error(
            "usage: runner --framed-service SEEDS SHA Q MAX_BATCH SUMMARY DEVICE "
            "[--allow-prefix-kat]");
      }
      const auto expected = seededParseDigest(argv[3]);
      const auto q = parseUnsigned(argv[4], "q");
      const auto maximumBatch = parseUnsigned(argv[5], "maximum batch");
      const auto device = parseUnsigned(argv[7], "device");
      if (q > std::numeric_limits<std::uint32_t>::max() ||
          maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("seeded service argument overflow");
      }
      const auto seeds = loadAuthenticatedSeeds(argv[2], expected, allowPrefixKat);
      runSeededService(seeds, static_cast<std::uint32_t>(q),
                       static_cast<std::uint32_t>(maximumBatch), argv[6],
                       static_cast<std::uint32_t>(device));
      return 0;
    }
    if (argc != 7 && !allowPrefixKat) {
      throw std::runtime_error(
          "usage: runner SEEDS SHA INPUT OUTPUT DEVICE REPETITIONS "
          "[--allow-prefix-kat]\n"
          "   or: runner --resident-qmajor-phase SEEDS SHA TGDQORD1 "
          "PHASE_PLAN_SHA INPUT INPUT_SHA SUMMARY DEVICE "
          "[--allow-prefix-kat]\n"
          "   or: runner --formulaic-qmajor-service SEEDS SHA TGDQORD1 "
          "PLAN_SHA SUMMARY DEVICE [--allow-prefix-kat]");
    }
    const auto expected = seededParseDigest(argv[2]);
    const auto device = parseUnsigned(argv[5], "device");
    const auto repetitions = parseUnsigned(argv[6], "repetitions");
    if (device > std::numeric_limits<std::uint32_t>::max() || repetitions == 0U ||
        repetitions > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("device or repetitions are invalid");
    }
    const auto seeds = loadAuthenticatedSeeds(argv[1], expected, allowPrefixKat);
    runSeededSingle(seeds, argv[3], argv[4],
                    static_cast<std::uint32_t>(device),
                    static_cast<std::uint32_t>(repetitions));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_largeq_seeded_batch: %s\n", error.what());
    return 1;
  }
}

#ifdef SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN
#undef main
#endif
