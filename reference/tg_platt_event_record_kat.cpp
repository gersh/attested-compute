// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Portable cross-language known-answer producer for PT21EVT1.  This does not
// synthesize Hardy-Z samples; the CUDA scanner has separate differential
// tests.  It fixes the compact stream's framing, signed weights, digests, and
// terminal authentication independently of the Python and Lean decoders.

#include "sparkinterval/tg_platt_event_record.hpp"

#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace per = sparkinterval::tg::platt_event_record;

namespace {

class ExclusiveOutput {
 public:
  explicit ExclusiveOutput(const std::string& path) : path_(path) {
    descriptor_ = ::open(path.c_str(),
                         O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC |
                             O_NOFOLLOW,
                         S_IRUSR | S_IWUSR);
    if (descriptor_ < 0) {
      throw std::runtime_error("cannot create KAT output: " +
                               std::string(std::strerror(errno)));
    }
  }

  ExclusiveOutput(const ExclusiveOutput&) = delete;
  ExclusiveOutput& operator=(const ExclusiveOutput&) = delete;

  ~ExclusiveOutput() {
    if (descriptor_ >= 0) ::close(descriptor_);
    if (!complete_) ::unlink(path_.c_str());
  }

  void write(const unsigned char* data, std::size_t size) {
    std::size_t offset = 0U;
    while (offset < size) {
      const ssize_t wrote =
          ::write(descriptor_, data + offset, size - offset);
      if (wrote < 0 && errno == EINTR) continue;
      if (wrote <= 0) {
        throw std::runtime_error("cannot write KAT output");
      }
      offset += static_cast<std::size_t>(wrote);
    }
  }

  void finish() {
    if (::fsync(descriptor_) != 0 || ::close(descriptor_) != 0) {
      descriptor_ = -1;
      throw std::runtime_error("cannot finalize KAT output");
    }
    descriptor_ = -1;
    complete_ = true;
  }

 private:
  std::string path_;
  int descriptor_ = -1;
  bool complete_ = false;
};

sparkinterval::Sha256Digest repeated(unsigned char value) {
  sparkinterval::Sha256Digest result{};
  result.fill(value);
  return result;
}

std::uint64_t checked_total(std::uint64_t accumulator,
                            std::uint32_t value) {
  if (value > std::numeric_limits<std::uint64_t>::max() - accumulator) {
    throw std::runtime_error("KAT total overflows");
  }
  return accumulator + value;
}

int run(const std::string& path) {
  const per::HeaderValues header_values{
      .first_block = 7U,
      .block_count = 2U,
      .gamma_stream_sha256 = repeated(0x11U),
      .producer_sha256 = repeated(0x22U),
  };
  const per::RawHeader header = per::encode_header(header_values);
  per::validate_header(header, &header_values);

  const std::array<per::BlockValues, 2> values = {{
      {
          .block = 7U,
          .failure_flags = 0U,
          .certified_sample_count = per::kRequiredSampleCount,
          .digest_valid = 1U,
          .direct_event_count = {2U, 3U, 1U},
          .stationary_candidate_count = {0U, 1U, 0U},
          .certified_direct_slots = {2U, 3U, 1U},
          .unresolved_stationary_count = 1U,
          .direct_nleft_units = {-5, -30, -1},
          .direct_nright_units = {4, 40, 0},
          .event_artifact_sha256 = repeated(0x33U),
      },
      {
          .block = 8U,
          .failure_flags = 0U,
          .certified_sample_count = per::kRequiredSampleCount,
          .digest_valid = 1U,
          .direct_event_count = {0U, 4U, 2U},
          .stationary_candidate_count = {1U, 0U, 1U},
          .certified_direct_slots = {0U, 4U, 2U},
          .unresolved_stationary_count = 2U,
          .direct_nleft_units = {0, -100, -6},
          .direct_nright_units = {0, 55, 8},
          .event_artifact_sha256 = repeated(0x44U),
      },
  }};

  std::array<per::RawRecord, 2> records{};
  sparkinterval::detail::Sha256 record_stream_hasher;
  std::uint64_t direct_total = 0U;
  std::uint64_t stationary_total = 0U;
  for (std::size_t index = 0U; index < records.size(); ++index) {
    records[index] = per::encode_record(values[index]);
    const per::BlockValues decoded =
        per::decode_record(records[index], 7U + index);
    if (decoded.event_artifact_sha256 !=
        values[index].event_artifact_sha256) {
      throw std::runtime_error("KAT event digest roundtrip differs");
    }
    record_stream_hasher.update(records[index].data(),
                                records[index].size());
    for (std::size_t stream = 0U; stream < 3U; ++stream) {
      direct_total =
          checked_total(direct_total, values[index].direct_event_count[stream]);
      stationary_total = checked_total(
          stationary_total,
          values[index].stationary_candidate_count[stream]);
    }
  }

  const per::FooterValues footer_values{
      .first_block = header_values.first_block,
      .block_count = header_values.block_count,
      .total_direct_events = direct_total,
      .total_stationary_candidates = stationary_total,
      .record_stream_sha256 = record_stream_hasher.finish(),
      .header_sha256 =
          per::digest_at(header.data() + per::kHeaderDigestOffset),
      .gamma_stream_sha256 = header_values.gamma_stream_sha256,
  };
  const per::RawFooter footer = per::encode_footer(footer_values);
  per::validate_footer(footer, footer_values);

  ExclusiveOutput output(path);
  sparkinterval::detail::Sha256 stream_hasher;
  output.write(header.data(), header.size());
  stream_hasher.update(header.data(), header.size());
  for (const per::RawRecord& record : records) {
    output.write(record.data(), record.size());
    stream_hasher.update(record.data(), record.size());
  }
  output.write(footer.data(), footer.size());
  stream_hasher.update(footer.data(), footer.size());
  output.finish();

  std::cout
      << "{\"accepted\":true,\"block_count\":2,\"event_record_bytes\":"
      << per::kRecordBytes << ",\"event_stream_sha256\":\""
      << sparkinterval::lowercase_hex(stream_hasher.finish())
      << "\",\"first_block\":7,\"record_0_sha256\":\""
      << sparkinterval::lowercase_hex(
             per::digest_at(records[0].data() + per::kRecordDigestOffset))
      << "\",\"schema\":\"sparkinterval.tg.platt-pt21-event-record-kat.v1\""
      << ",\"source_claim_ready\":false,\"total_direct_events\":12"
      << ",\"total_stationary_candidates\":3}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2) {
      throw std::runtime_error("usage: tg_platt_event_record_kat OUTPUT");
    }
    return run(argv[1]);
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_event_record_kat: " << error.what() << '\n';
    return 2;
  }
}
