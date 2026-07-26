// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only native scanner for one PT21SGN1 required-sign packet.
//
// The scanner validates the complete fixed packet, recomputes both historical
// PT21 wire checksums and every DD sign guard, then emits a compact PT21FSC1
// certificate containing the complete direct-event and stationary-candidate
// offset lists.
// It deliberately does not emit PT21BLK1 and has no analytic interpretation.
// The Python adapter independently recomputes the lists (vectorized binary64
// with exact Fraction fallback) before using this output.

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <gmpxx.h>

#include <unistd.h>

namespace {

using Digest = sparkinterval::Sha256Digest;

constexpr std::size_t kPacketHeaderBytes = 200U;
constexpr std::size_t kSampleBytes = 24U;
constexpr std::uint32_t kRequiredCount = 25'741U;
constexpr std::int32_t kRequiredOffsetLower = -12'870;
constexpr std::uint64_t kSourceLowerCenter = 10'000'000'504ULL;
constexpr std::uint64_t kSourceStep = 1'008ULL;
constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
constexpr std::uint64_t kExpectedSampleBytes =
    static_cast<std::uint64_t>(kRequiredCount) * kSampleBytes;
constexpr std::uint64_t kExpectedSignBytes = (kRequiredCount + 7U) / 8U;
constexpr std::uint64_t kExpectedPacketBytes =
    kPacketHeaderBytes + kExpectedSampleBytes + kExpectedSignBytes;
constexpr std::uint64_t kFnvOffset = 1'469'598'103'934'665'603ULL;
constexpr std::uint64_t kFnvPrime = 1'099'511'628'211ULL;
constexpr std::uint32_t kEndianTag = 0x01020304U;
constexpr std::uint32_t kCertificateVersion = 1U;
constexpr std::size_t kCertificateHeaderBytes = 192U;
constexpr std::size_t kStreamRequestHeaderBytes = 64U;
constexpr std::size_t kStreamResponseHeaderBytes = 96U;
constexpr char kPacketMagic[] = "PT21SGN1";
constexpr char kCertificateMagic[] = "PT21FSC1";
constexpr char kStreamRequestMagic[] = "PT21FSQ1";
constexpr char kStreamResponseMagic[] = "PT21FSR1";
constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";
constexpr char kCertificateDomain[] =
    "sparkinterval/tg/platt-pt21-native-scan-certificate/v1\0";

struct StreamRange {
  std::int32_t lower;
  std::int32_t upper;
};

// Canonical artifact order, not source-memory order.
constexpr std::array<StreamRange, 3> kStreams = {{
    {-12'288, 12'288},
    {-12'800, -12'288},
    {12'288, 12'800},
}};

class ScanError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0U;
  for (unsigned int index = 0U; index < 8U; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0U; index < 4U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void store_i32(unsigned char* data, std::int32_t value) {
  store_u32(data, static_cast<std::uint32_t>(value));
}

void store_u64(unsigned char* data, std::uint64_t value) {
  for (unsigned int index = 0U; index < 8U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

std::uint64_t fnv1a(const unsigned char* data, std::size_t size) {
  // PT21SGN1 historically named this field FNV-1a, but its version-1 offset
  // basis is the project-specific 0x14650fb0739d0383, not the standard
  // FNV-1a-64 basis.  Keep these exact bytes until a new wire version.
  std::uint64_t result = kFnvOffset;
  for (std::size_t index = 0U; index < size; ++index) {
    result ^= data[index];
    result *= kFnvPrime;
  }
  return result;
}

std::vector<unsigned char> read_standard_input() {
  std::vector<unsigned char> result;
  result.reserve(kExpectedPacketBytes);
  std::array<unsigned char, 64U * 1024U> buffer{};
  while (true) {
    const ssize_t got = ::read(STDIN_FILENO, buffer.data(), buffer.size());
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) {
      throw ScanError("cannot read required-sign packet from standard input");
    }
    if (got == 0) break;
    if (result.size() + static_cast<std::size_t>(got) >
        kExpectedPacketBytes) {
      throw ScanError("required-sign packet exceeds its exact byte length");
    }
    result.insert(result.end(), buffer.begin(),
                  buffer.begin() + static_cast<std::size_t>(got));
  }
  if (result.size() != kExpectedPacketBytes) {
    throw ScanError("required-sign packet byte length differs");
  }
  return result;
}

void write_all(int descriptor, const unsigned char* data, std::size_t size) {
  std::size_t position = 0U;
  while (position < size) {
    const ssize_t wrote =
        ::write(descriptor, data + position, size - position);
    if (wrote < 0 && errno == EINTR) continue;
    if (wrote <= 0) {
      throw ScanError("cannot write native scan certificate");
    }
    position += static_cast<std::size_t>(wrote);
  }
}

bool read_exact_or_eof(int descriptor, unsigned char* data, std::size_t size) {
  std::size_t position = 0U;
  while (position < size) {
    const ssize_t got = ::read(descriptor, data + position, size - position);
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) throw ScanError("cannot read native scan stream");
    if (got == 0) {
      if (position == 0U) return false;
      throw ScanError("native scan stream is truncated");
    }
    position += static_cast<std::size_t>(got);
  }
  return true;
}

double load_binary64(const unsigned char* data) {
  return std::bit_cast<double>(load_u64(data));
}

struct Sample {
  double high = 0.0;
  double low = 0.0;
  double radius = 0.0;
  bool positive = false;
};

struct ExactInterval {
  mpq_class lower;
  mpq_class upper;
};

struct DirectedInterval {
  double lower = -std::numeric_limits<double>::infinity();
  double upper = std::numeric_limits<double>::infinity();
};

DirectedInterval directed_interval(const Sample& sample) {
  const double center = sample.high + sample.low;
  if (!std::isfinite(center)) return {};
  const double center_lower =
      std::nextafter(center, -std::numeric_limits<double>::infinity());
  const double center_upper =
      std::nextafter(center, std::numeric_limits<double>::infinity());
  const double lower = center_lower - sample.radius;
  const double upper = center_upper + sample.radius;
  if (!std::isfinite(lower) || !std::isfinite(upper)) return {};
  return {
      std::nextafter(lower, -std::numeric_limits<double>::infinity()),
      std::nextafter(upper, std::numeric_limits<double>::infinity()),
  };
}

ExactInterval exact_interval(const Sample& sample) {
  // mpq_set_d, used by mpq_class(double), converts the finite IEEE value
  // exactly.  This is required: accepted subnormals have denominator 2^1074,
  // so neither int64 nor __int128 covers the packet language.
  const mpq_class center =
      mpq_class(sample.high) + mpq_class(sample.low);
  const mpq_class radius(sample.radius);
  return {center - radius, center + radius};
}

bool exact_stationary_candidate(const Sample& first, const Sample& middle,
                                const Sample& right) {
  if (first.positive != middle.positive ||
      middle.positive != right.positive) {
    return false;
  }
  const ExactInterval first_interval = exact_interval(first);
  const ExactInterval middle_interval = exact_interval(middle);
  const ExactInterval right_interval = exact_interval(right);
  if (middle.positive) {
    return first_interval.lower > middle_interval.upper &&
           right_interval.lower > middle_interval.upper;
  }
  return middle_interval.lower > first_interval.upper &&
         middle_interval.lower > right_interval.upper;
}

bool equal_sample(const Sample& left, const Sample& right) {
  return left.high == right.high && left.low == right.low &&
         left.radius == right.radius && left.positive == right.positive;
}

bool stationary_candidate(
    const Sample& first, const Sample& middle, const Sample& right,
    const DirectedInterval& first_interval,
    const DirectedInterval& middle_interval,
    const DirectedInterval& right_interval,
    std::uint32_t* exact_fallback_count) {
  if (first.positive != middle.positive ||
      middle.positive != right.positive) {
    return false;
  }
  bool certified = false;
  bool rejected = false;
  if (middle.positive) {
    certified =
        first_interval.lower > middle_interval.upper &&
        right_interval.lower > middle_interval.upper;
    rejected =
        equal_sample(first, middle) || equal_sample(right, middle) ||
        first_interval.upper <= middle_interval.lower ||
        right_interval.upper <= middle_interval.lower;
  } else {
    certified =
        middle_interval.lower > first_interval.upper &&
        middle_interval.lower > right_interval.upper;
    rejected =
        equal_sample(first, middle) || equal_sample(right, middle) ||
        middle_interval.upper <= first_interval.lower ||
        middle_interval.upper <= right_interval.lower;
  }
  if (certified) return true;
  if (rejected) return false;
  if (*exact_fallback_count == std::numeric_limits<std::uint32_t>::max()) {
    throw ScanError("exact stationary fallback count overflows uint32");
  }
  ++*exact_fallback_count;
  return exact_stationary_candidate(first, middle, right);
}

const Sample& sample_at(const std::vector<Sample>& samples,
                        std::int32_t offset) {
  const std::int64_t index =
      static_cast<std::int64_t>(offset) - kRequiredOffsetLower;
  if (index < 0 ||
      static_cast<std::uint64_t>(index) >= samples.size()) {
    throw ScanError("internal sample offset is outside the packet");
  }
  return samples[static_cast<std::size_t>(index)];
}

Digest certificate_digest(const unsigned char* header_prefix,
                          std::size_t prefix_size,
                          const std::vector<unsigned char>& body) {
  sparkinterval::detail::Sha256 hasher;
  hasher.update(kCertificateDomain, sizeof(kCertificateDomain) - 1U);
  hasher.update(header_prefix, prefix_size);
  hasher.update(body.data(), body.size());
  return hasher.finish();
}

std::vector<unsigned char> scan_packet(
    const std::vector<unsigned char>& packet,
    const Digest* precomputed_packet_digest = nullptr) {
  if (packet.size() != kExpectedPacketBytes) {
    throw ScanError("required-sign packet byte length differs");
  }
  const unsigned char* header = packet.data();
  if (std::memcmp(header, kPacketMagic, 8U) != 0 ||
      load_u32(header + 8U) != 1U ||
      load_u32(header + 12U) != kPacketHeaderBytes ||
      load_u32(header + 16U) != kEndianTag ||
      load_u32(header + 20U) != 1U ||
      load_u32(header + 24U) != 1U ||
      load_u32(header + 28U) != 768'000U ||
      load_u32(header + 32U) != 52'666U ||
      load_u32(header + 36U) != 78'406U ||
      load_u32(header + 40U) != kRequiredCount ||
      load_u32(header + 44U) != 0U ||
      load_u64(header + 56U) != kExpectedSampleBytes ||
      load_u64(header + 64U) != kExpectedSignBytes ||
      std::memcmp(header + 160U, kUpstreamCommit, 40U) != 0) {
    throw ScanError("required-sign fixed header differs");
  }
  const std::uint64_t window_center = load_u64(header + 48U);
  if (window_center < kSourceLowerCenter ||
      (window_center - kSourceLowerCenter) % kSourceStep != 0U ||
      (window_center - kSourceLowerCenter) / kSourceStep >=
          kSourceBlockCount) {
    throw ScanError("required-sign window center is outside the campaign");
  }
  for (std::size_t index = 96U; index < 160U; ++index) {
    const unsigned char value = header[index];
    if (!((value >= '0' && value <= '9') ||
          (value >= 'a' && value <= 'f'))) {
      throw ScanError("required-sign source SHA-256 is malformed");
    }
  }

  const unsigned char* sample_raw = packet.data() + kPacketHeaderBytes;
  const unsigned char* sign_raw = sample_raw + kExpectedSampleBytes;
  const std::uint64_t sample_fnv =
      fnv1a(sample_raw, static_cast<std::size_t>(kExpectedSampleBytes));
  const std::uint64_t sign_fnv =
      fnv1a(sign_raw, static_cast<std::size_t>(kExpectedSignBytes));
  if (sample_fnv != load_u64(header + 72U) ||
      sign_fnv != load_u64(header + 80U)) {
    throw ScanError("required-sign payload checksum differs");
  }
  constexpr unsigned int used_final_bits = kRequiredCount % 8U;
  if ((sign_raw[kExpectedSignBytes - 1U] >> used_final_bits) != 0U) {
    throw ScanError("required-sign unused high sign bits are nonzero");
  }

  std::vector<Sample> samples;
  samples.reserve(kRequiredCount);
  for (std::uint32_t index = 0U; index < kRequiredCount; ++index) {
    const unsigned char* raw = sample_raw + index * kSampleBytes;
    const double high = load_binary64(raw);
    const double low = load_binary64(raw + 8U);
    const double radius = load_binary64(raw + 16U);
    if (!std::isfinite(high) || !std::isfinite(low) ||
        !std::isfinite(radius) || radius < 0.0) {
      throw ScanError("required-sign packet has an invalid DD disk");
    }
    const double center_lower =
        std::max(0.0, std::fabs(high) - std::fabs(low));
    if (!(center_lower > radius) || high == 0.0) {
      throw ScanError("required-sign packet has an ambiguous DD disk");
    }
    const bool positive =
        (sign_raw[index / 8U] & (1U << (index % 8U))) != 0U;
    if (positive != (high > 0.0)) {
      throw ScanError("required-sign bit differs from its DD disk");
    }
    samples.push_back({high, low, radius, positive});
  }
  std::vector<DirectedInterval> directed;
  directed.reserve(samples.size());
  for (const Sample& sample : samples) {
    directed.push_back(directed_interval(sample));
  }

  std::array<std::vector<std::int32_t>, 3> direct{};
  std::array<std::vector<std::int32_t>, 3> stationary{};
  std::uint32_t same_sign_triples = 0U;
  std::uint32_t exact_fallback_count = 0U;
  for (std::size_t stream = 0U; stream < kStreams.size(); ++stream) {
    const StreamRange range = kStreams[stream];
    for (std::int32_t offset = range.lower; offset < range.upper; ++offset) {
      if (sample_at(samples, offset).positive !=
          sample_at(samples, offset + 1).positive) {
        direct[stream].push_back(offset);
      }
    }
    for (std::int32_t offset = range.lower;
         offset <= range.upper - 2; ++offset) {
      const Sample& first = sample_at(samples, offset);
      const Sample& middle = sample_at(samples, offset + 1);
      const Sample& right = sample_at(samples, offset + 2);
      if (first.positive == middle.positive &&
          middle.positive == right.positive) {
        ++same_sign_triples;
        const std::size_t first_index = static_cast<std::size_t>(
            static_cast<std::int64_t>(offset) - kRequiredOffsetLower);
        if (stationary_candidate(
                first, middle, right, directed[first_index],
                directed[first_index + 1U], directed[first_index + 2U],
                &exact_fallback_count)) {
          stationary[stream].push_back(offset);
        }
      }
    }
  }

  std::size_t body_entries = 0U;
  for (const auto& values : direct) body_entries += values.size();
  for (const auto& values : stationary) body_entries += values.size();
  if (body_entries >
      std::numeric_limits<std::uint64_t>::max() / sizeof(std::int32_t)) {
    throw ScanError("native scan body size overflows uint64");
  }
  std::vector<unsigned char> body(body_entries * sizeof(std::int32_t));
  std::size_t body_offset = 0U;
  const auto append = [&body, &body_offset](
                          const std::vector<std::int32_t>& values) {
    for (const std::int32_t value : values) {
      store_i32(body.data() + body_offset, value);
      body_offset += sizeof(std::int32_t);
    }
  };
  for (const auto& values : direct) append(values);
  for (const auto& values : stationary) append(values);
  if (body_offset != body.size()) {
    throw ScanError("internal native scan body length differs");
  }

  std::array<unsigned char, kCertificateHeaderBytes> certificate{};
  std::memcpy(certificate.data(), kCertificateMagic, 8U);
  store_u32(certificate.data() + 8U, kCertificateVersion);
  store_u32(certificate.data() + 12U, kCertificateHeaderBytes);
  store_u32(certificate.data() + 16U, kEndianTag);
  store_u32(certificate.data() + 20U, exact_fallback_count);
  store_u64(certificate.data() + 24U, packet.size());
  store_u64(certificate.data() + 32U, window_center);
  store_u32(certificate.data() + 40U, kRequiredCount);
  store_u32(certificate.data() + 44U, same_sign_triples);
  for (std::size_t stream = 0U; stream < kStreams.size(); ++stream) {
    store_u32(certificate.data() + 48U + stream * 4U,
              static_cast<std::uint32_t>(direct[stream].size()));
    store_u32(certificate.data() + 60U + stream * 4U,
              static_cast<std::uint32_t>(stationary[stream].size()));
  }
  store_u64(certificate.data() + 72U, body.size());
  store_u64(certificate.data() + 80U, sample_fnv);
  store_u64(certificate.data() + 88U, sign_fnv);
  const Digest packet_digest =
      precomputed_packet_digest == nullptr
          ? sparkinterval::sha256(packet.data(), packet.size())
          : *precomputed_packet_digest;
  std::memcpy(certificate.data() + 96U, packet_digest.data(),
              packet_digest.size());
  const Digest body_digest =
      sparkinterval::sha256(body.data(), body.size());
  std::memcpy(certificate.data() + 128U, body_digest.data(),
              body_digest.size());
  const Digest record_digest =
      certificate_digest(certificate.data(), 160U, body);
  std::memcpy(certificate.data() + 160U, record_digest.data(),
              record_digest.size());

  std::vector<unsigned char> output;
  output.reserve(certificate.size() + body.size());
  output.insert(output.end(), certificate.begin(), certificate.end());
  output.insert(output.end(), body.begin(), body.end());
  return output;
}

int run_one_shot() {
  const std::vector<unsigned char> packet = read_standard_input();
  const std::vector<unsigned char> certificate = scan_packet(packet);
  write_all(STDOUT_FILENO, certificate.data(), certificate.size());
  return 0;
}

int run_stream() {
  std::uint64_t expected_request_id = 0U;
  while (true) {
    std::array<unsigned char, kStreamRequestHeaderBytes> request{};
    if (!read_exact_or_eof(STDIN_FILENO, request.data(), request.size())) {
      break;
    }
    if (std::memcmp(request.data(), kStreamRequestMagic, 8U) != 0 ||
        load_u32(request.data() + 8U) != 1U ||
        load_u32(request.data() + 12U) != request.size() ||
        load_u64(request.data() + 16U) != expected_request_id ||
        load_u64(request.data() + 24U) != kExpectedPacketBytes) {
      throw ScanError("native scan stream request framing differs");
    }
    std::vector<unsigned char> packet(kExpectedPacketBytes);
    if (!read_exact_or_eof(STDIN_FILENO, packet.data(), packet.size())) {
      throw ScanError("native scan stream packet is truncated");
    }
    const Digest packet_digest =
        sparkinterval::sha256(packet.data(), packet.size());
    if (!std::equal(packet_digest.begin(), packet_digest.end(),
                    request.begin() + 32U)) {
      throw ScanError("native scan stream packet digest differs");
    }
    const std::vector<unsigned char> certificate =
        scan_packet(packet, &packet_digest);
    std::array<unsigned char, kStreamResponseHeaderBytes> response{};
    std::memcpy(response.data(), kStreamResponseMagic, 8U);
    store_u32(response.data() + 8U, 1U);
    store_u32(response.data() + 12U, response.size());
    store_u64(response.data() + 16U, expected_request_id);
    store_u64(response.data() + 24U, certificate.size());
    std::memcpy(response.data() + 32U, packet_digest.data(),
                packet_digest.size());
    const Digest certificate_digest =
        sparkinterval::sha256(certificate.data(), certificate.size());
    std::memcpy(response.data() + 64U, certificate_digest.data(),
                certificate_digest.size());
    write_all(STDOUT_FILENO, response.data(), response.size());
    write_all(STDOUT_FILENO, certificate.data(), certificate.size());
    if (expected_request_id == std::numeric_limits<std::uint64_t>::max()) {
      throw ScanError("native scan stream request id overflows uint64");
    }
    ++expected_request_id;
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 1) return run_one_shot();
    if (argc == 2 && std::string_view(argv[1]) == "--stream") {
      return run_stream();
    }
    throw ScanError("usage: scanner [--stream]");
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_packet_scan_fastpath: " << error.what()
              << '\n';
    return 2;
  }
}
