// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Portable two-frame known answer for the PT21 worker block-input wire.
//
// The producer here is the *same* header the fused source worker uses, and the
// Turing artifact comes from the same exact-rational Arb core.  The disks are
// explicitly synthetic, so this executable proves only that the two
// independent implementations of the wire agree byte for byte and that each
// nested payload survives the other side's checker.  It is not a source block,
// not a measured worker run, and not evidence for any analytic realization.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_event_record.hpp"
#include "sparkinterval/tg_platt_pt21_block_input_stream.hpp"
#include "sparkinterval/tg_platt_pt21_required_sign_packet.hpp"
#include "sparkinterval/tg_platt_pt21_turing_inputs.hpp"
#include "sparkinterval/tg_platt_stationary_junction.hpp"
#include "sparkinterval/tg_platt_stationary_resolver.hpp"

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace pbi = sparkinterval::tg::platt_pt21_block_input_stream;
namespace per = sparkinterval::tg::platt_event_record;
namespace prs = sparkinterval::tg::platt_pt21_required_sign_packet;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;
namespace pti = sparkinterval::tg::platt_pt21_turing_inputs;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

constexpr std::size_t kGammaRecordBytes = 312U;
constexpr char kResolutionDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-resolutions/v1\0";

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

std::vector<pw::RealDisk106> synthetic_samples() {
  std::vector<pw::RealDisk106> samples(prs::kRequiredCount);
  for (std::size_t index = 0U; index < samples.size(); ++index) {
    const std::int32_t offset =
        static_cast<std::int32_t>(index) + psr::kRequiredLower;
    samples[index].center.hi = offset == 0 ? 1.0 : -1.0;
    samples[index].center.lo = 0.0;
    samples[index].radius = 0.25;
  }
  return samples;
}

std::array<unsigned char, kGammaRecordBytes> synthetic_gamma_record(
    std::uint64_t block) {
  std::array<unsigned char, kGammaRecordBytes> record{};
  for (std::size_t index = 0U; index < record.size(); ++index) {
    record[index] = static_cast<unsigned char>(
        (index * 31U + block * 17U + 7U) & 0xFFU);
  }
  return record;
}

std::string stationary_trace_json() {
  static constexpr char kEmptyResolutions[] = "[]";
  sparkinterval::detail::Sha256 hasher;
  hasher.update(kResolutionDomain, sizeof(kResolutionDomain) - 1U);
  hasher.update(kEmptyResolutions, 2U);
  const std::string resolution_sha256 =
      sparkinterval::lowercase_hex(hasher.finish());
  const std::string input_sha256 = sparkinterval::lowercase_hex(
      sparkinterval::sha256(kEmptyResolutions, 2U));
  return std::string("{\"accepted\":true,\"ambiguous_input_disks\":0,") +
         "\"candidate_count\":0,\"error\":\"\",\"failure_flags\":0," +
         "\"input_sha256\":\"" + input_sha256 + "\"," +
         "\"interpolation_evaluations\":0," +
         "\"interpolation_patch_sha256\":\"" +
         psr::kInterpolationPatchSha256 + "\",\"maximum_depth\":64," +
         "\"precision_bits\":128,\"refinements_applied\":0," +
         "\"replay_accepted\":true,\"required_sample_count\":25741," +
         "\"resolution_sha256\":\"" + resolution_sha256 + "\"," +
         "\"schema\":\"sparkinterval.tg.platt-pt21-stationary-trace.v1\"," +
         "\"semantic_status\":{" +
         "\"analytic_turing_realization_proved\":false," +
         "\"flint_to_mathlib_realization_proved\":false," +
         "\"hardy_z_endpoint_realization_proved\":false}," +
         "\"stationary_resolutions\":[],\"upstream_commit\":\"" +
         psr::kUpstreamCommit + "\"}\n";
}

per::RawRecord synthetic_event_record(std::uint64_t block) {
  per::BlockValues values;
  values.block = block;
  values.failure_flags = 0U;
  values.certified_sample_count = prs::kRequiredCount;
  values.digest_valid = 1U;
  const std::string label = "pt21-block-input-kat-artifact-" +
                            std::to_string(block);
  values.event_artifact_sha256 =
      sparkinterval::sha256(label.data(), label.size());
  return per::encode_record(values);
}

psj::RawRecord synthetic_junction_record(std::uint64_t block,
                                         const per::RawRecord& event,
                                         const std::string& trace) {
  psj::RecordValues values;
  values.block = block;
  values.candidate_count = 0U;
  values.resolution_count = 0U;
  values.ambiguous_input_count = 0U;
  values.refinement_count = 0U;
  values.resolved_multiplicity_slots = 0U;
  values.precision_bits = psr::kSourcePrecisionBits;
  values.maximum_depth = 64U;
  values.replay_extra_precision_bits = 64U;
  values.flint_release = psj::kFlintRelease;
  values.semantic_realization_flags = 0U;
  values.resolver_replay_accepted = 1U;
  values.higher_precision_containment_complete = 1U;
  values.event_record_sha256 =
      per::digest_at(event.data() + per::kRecordDigestOffset);
  values.event_artifact_sha256 =
      per::decode_record(event, block).event_artifact_sha256;
  const auto constant = [](const char* text) {
    return sparkinterval::sha256(text, std::strlen(text));
  };
  values.candidate_list_sha256 = constant("pt21-block-input-kat-candidates");
  values.resolver_input_sha256 = constant("pt21-block-input-kat-input");
  values.refinement_trace_sha256 =
      constant("pt21-block-input-kat-refinements");
  values.resolution_sha256 = constant("pt21-block-input-kat-resolutions");
  values.stationary_trace_sha256 =
      sparkinterval::sha256(trace.data(), trace.size());
  values.resolver_sha256 = constant("pt21-block-input-kat-resolver");
  values.flint_sha256 = constant("pt21-block-input-kat-flint");
  return psj::encode_record(values);
}

void write_exclusive(const std::string& path,
                     const std::vector<unsigned char>& raw) {
  const int descriptor = ::open(
      path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      S_IRUSR | S_IWUSR);
  if (descriptor < 0) {
    fail("cannot create the block-input known-answer output: " +
         std::string(std::strerror(errno)));
  }
  std::size_t offset = 0U;
  while (offset < raw.size()) {
    const ssize_t wrote =
        ::write(descriptor, raw.data() + offset, raw.size() - offset);
    if (wrote < 0 && errno == EINTR) continue;
    if (wrote <= 0) {
      ::close(descriptor);
      fail("cannot write the block-input known-answer output");
    }
    offset += static_cast<std::size_t>(wrote);
  }
  if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
    fail("cannot flush the block-input known-answer output");
  }
}

int run(int argc, char** argv) {
  if (argc != 2) {
    fail("usage: sparkinterval-tg-platt-pt21-block-input-stream-kat OUTPUT");
  }
  constexpr std::uint64_t kFirstBlock = 0U;
  constexpr std::uint64_t kBlockCount = 2U;
  const auto identity = [](const char* text) {
    return sparkinterval::sha256(text, std::strlen(text));
  };
  const pbi::HeaderValues header_values{
      .first_block = kFirstBlock,
      .block_count = kBlockCount,
      .gamma_stream_sha256 = identity("pt21-block-input-kat-gamma-stream"),
      .producer_sha256 = identity("pt21-block-input-kat-producer"),
      .resolver_sha256 = identity("pt21-block-input-kat-resolver"),
      .flint_sha256 = identity("pt21-block-input-kat-flint"),
  };
  const pbi::RawHeader header = pbi::encode_header(header_values);
  pbi::decode_header(header, &header_values);

  std::vector<unsigned char> stream(header.begin(), header.end());
  sparkinterval::detail::Sha256 frame_hasher;
  std::uint64_t total_packet_bytes = 0U;
  std::uint64_t total_trace_bytes = 0U;
  std::uint64_t total_turing_bytes = 0U;
  const std::vector<pw::RealDisk106> samples = synthetic_samples();
  const std::string trace = stationary_trace_json();

  for (std::uint64_t index = 0U; index < kBlockCount; ++index) {
    const std::uint64_t block = kFirstBlock + index;
    const auto gamma_record = synthetic_gamma_record(block);
    const std::vector<unsigned char> packet =
        prs::encode_packet(block, samples, gamma_record);
    const std::string turing = pti::artifact_json(
        block, sparkinterval::lowercase_hex(
                   sparkinterval::sha256(packet.data(), packet.size())));
    const per::RawRecord event = synthetic_event_record(block);
    const psj::RawRecord junction =
        synthetic_junction_record(block, event, trace);
    const pbi::FramePayload payload{
        .block = block,
        .required_sign_packet = packet,
        .event_record = event,
        .junction_record = junction,
        .stationary_trace = trace,
        .turing_inputs = turing,
    };
    const std::vector<unsigned char> frame = pbi::encode_frame(payload);
    pbi::decode_frame(frame, block);
    frame_hasher.update(frame.data(), frame.size());
    stream.insert(stream.end(), frame.begin(), frame.end());
    total_packet_bytes += packet.size();
    total_trace_bytes += trace.size();
    total_turing_bytes += turing.size();
  }

  const pbi::FooterValues footer_values{
      .first_block = kFirstBlock,
      .block_count = kBlockCount,
      .total_frames = kBlockCount,
      .total_packet_bytes = total_packet_bytes,
      .total_trace_bytes = total_trace_bytes,
      .total_turing_bytes = total_turing_bytes,
      .frame_stream_sha256 = frame_hasher.finish(),
      .header_sha256 =
          per::digest_at(header.data() + pbi::kHeaderDigestOffset),
      .gamma_stream_sha256 = header_values.gamma_stream_sha256,
  };
  const pbi::RawFooter footer = pbi::encode_footer(footer_values);
  pbi::decode_footer(footer, &footer_values);
  stream.insert(stream.end(), footer.begin(), footer.end());
  write_exclusive(argv[1], stream);

  std::cout
      << "{\"schema\":\"sparkinterval.tg.platt-pt21-block-input-stream-kat.v1\""
      << ",\"accepted\":true"
      << ",\"synthetic_finite_fixture\":true"
      << ",\"first_block\":" << kFirstBlock
      << ",\"block_count\":" << kBlockCount
      << ",\"stream_bytes\":" << stream.size()
      << ",\"stream_sha256\":\""
      << sparkinterval::lowercase_hex(
             sparkinterval::sha256(stream.data(), stream.size()))
      << "\""
      << ",\"required_sign_packet_bytes\":" << total_packet_bytes
      << ",\"stationary_trace_bytes\":" << total_trace_bytes
      << ",\"turing_artifact_bytes\":" << total_turing_bytes
      << ",\"arb_interval_arithmetic_executed\":true"
      << ",\"source_block\":false"
      << ",\"pt21blk1_present\":false"
      << ",\"hardy_z_endpoint_realization_proved\":false"
      << ",\"analytic_turing_realization_proved\":false"
      << ",\"source_claim_ready\":false}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_block_input_stream_kat: " << error.what()
              << '\n';
    return 2;
  }
}
