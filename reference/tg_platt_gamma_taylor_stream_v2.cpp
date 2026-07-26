// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// The V2 producer deliberately compiles the pinned, reviewed FLINT producer
// implementation into this translation unit.  This keeps certificate
// construction, branch selection, Q192 projection, and direct audit logic
// byte-for-byte shared with V1 while changing only the outward wire
// projection.  The embedded entry point is renamed and is never called.
#define main sparkinterval_embedded_gamma_v1_main
#include "tg_platt_gamma_taylor.cpp"
#undef main

#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"

namespace {

namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;

pg2::Record project_v2_record(const TaylorCertificate& certificate,
                              const Options& options) {
  pg2::Record result{};
  for (long index = 0; index < options.degree; ++index) {
    result.coefficients[index] = project_acb_dd(
        acb_poly_get_coeff_ptr(certificate.coefficients.value, index),
        options.precision);
  }

  const acb_srcptr constant =
      acb_poly_get_coeff_ptr(certificate.coefficients.value, 0);
  const acb_srcptr linear =
      acb_poly_get_coeff_ptr(certificate.coefficients.value, 1);
  const FixedTurnProjection anchor =
      project_fixed_turn(acb_imagref(constant), options.precision);
  ArbValue phase_step_angle;
  arb_mul_si(phase_step_angle.value, acb_imagref(linear), 21,
             options.precision);
  arb_mul_2exp_si(phase_step_angle.value, phase_step_angle.value, -7);
  const FixedTurnProjection step =
      project_fixed_turn(phase_step_angle.value, options.precision);
  result.phase_anchor = {anchor.limbs[0], anchor.limbs[1], anchor.limbs[2]};
  result.phase_grid_step = {step.limbs[0], step.limbs[1], step.limbs[2]};
  result.phase_anchor_error = anchor.angular_error_upper;
  result.phase_grid_step_error = step.angular_error_upper;
  ArfValue remainder_upper;
  arb_get_ubound_arf(remainder_upper.value, certificate.remainder.value,
                     options.precision);
  result.logarithm_remainder =
      arf_get_d(remainder_upper.value, ARF_RND_UP);
  pg2::validate_record(result);
  return result;
}

pg2::Header make_v2_header(const Options& options) {
  pg2::Header header{};
  header.magic = pg2::kStreamMagic;
  header.version = pg2::kVersion;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.record_encoding = pg2::kEncoding;
  header.record_bytes = sizeof(pg2::Record);
  header.chunk_records = options.stream_chunk_records;
  header.degree = pg2::kDegree;
  header.precision_bits = pg2::kPrecisionBits;
  header.source_lower = pw::kSourceLower;
  header.source_step = pw::kWindowStep;
  header.full_block_count = pw::kFullBlockCount;
  header.first_block = options.stream_first_block;
  header.block_count = options.stream_blocks;
  header.radius_numerator = kRadiusNumerator;
  header.radius_denominator = kRadiusDenominator;
  header.grid_step_numerator = 21;
  header.grid_step_denominator = 128;
  header.gaussian_h = 116;
  header.inverse_gaussian_denominator =
      pg2::kInverseGaussianDenominator;
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());
  constexpr char flint_commit[] = SPARKINTERVAL_FLINT_PLATT_COMMIT;
  static_assert(sizeof(flint_commit) == 41U);
  std::memcpy(header.flint_commit.data(), flint_commit,
              header.flint_commit.size());
  header.reviewed_source_sha256 = pg2::kReviewedSourceSha256;
  std::memcpy(header.contract_id.data(), pg2::kContractId.data(),
              pg2::kContractId.size());
  return header;
}

struct V2Result {
  std::uint64_t chunks = 0U;
  std::uint64_t audits = 0U;
  std::uint64_t record_payload_bytes = 0U;
  std::uint64_t authenticated_stream_bytes = 0U;
  std::uint64_t artifact_bytes = 0U;
  double elapsed_seconds = 0.0;
  std::string header_sha256;
  std::string stream_sha256;
  std::string first_record_sha256;
  std::string last_record_sha256;
};

V2Result produce_v2_stream(const Options& options) {
  if constexpr (std::endian::native != std::endian::little) {
    fail("Gamma Taylor stream V2 requires a little-endian host");
  }
  const pg2::Header header = make_v2_header(options);
  const auto header_digest = sparkinterval::sha256(&header, sizeof(header));
  std::ofstream output;
  if (!options.stream_hash_only) {
    output.open(options.stream_output, std::ios::binary | std::ios::trunc);
    if (!output) fail("cannot open Gamma Taylor V2 stream output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    if (!output) fail("cannot write Gamma Taylor V2 stream header");
  }

  sparkinterval::detail::Sha256 stream_hasher;
  stream_hasher.update(pg2::kHashDomain.data(), pg2::kHashDomain.size());
  stream_hasher.update(&header, sizeof(header));
  V2Result result;
  result.header_sha256 = sparkinterval::lowercase_hex(header_digest);
  result.authenticated_stream_bytes = sizeof(header);
  TaylorCertificate certificate;
  std::vector<pg2::Record> records;
  records.reserve(options.stream_chunk_records);
  const auto started = std::chrono::steady_clock::now();
  std::uint64_t produced = 0U;
  while (produced < options.stream_blocks) {
    const std::uint64_t remaining = options.stream_blocks - produced;
    const std::uint32_t chunk_count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(remaining, options.stream_chunk_records));
    records.clear();
    for (std::uint32_t local = 0U; local < chunk_count; ++local) {
      const std::uint64_t relative = produced + local;
      const std::uint64_t block = options.stream_first_block + relative;
      Options at_height = options;
      at_height.height = pw::kSourceLower + pw::kWindowStep / 2U +
                         block * pw::kWindowStep;
      acb_poly_zero(certificate.coefficients.value);
      arb_zero(certificate.remainder.value);
      compute_certificate(&certificate, at_height);
      const bool endpoint = relative == 0U ||
                            relative + 1U == options.stream_blocks;
      const bool stride_audit = options.stream_audit_stride != 0U &&
                                block % options.stream_audit_stride == 0U;
      if (endpoint || stride_audit) {
        if (!audit_certificate(certificate, at_height)) {
          fail("Gamma Taylor V2 enclosure missed a direct FLINT audit");
        }
        ++result.audits;
      }
      records.push_back(project_v2_record(certificate, at_height));
    }
    const std::size_t payload_bytes = records.size() * sizeof(pg2::Record);
    pg2::ChunkHeader chunk{};
    chunk.magic = pg2::kChunkMagic;
    chunk.version = pg2::kVersion;
    chunk.header_bytes = sizeof(chunk);
    chunk.first_block = options.stream_first_block + produced;
    chunk.record_count = chunk_count;
    chunk.payload_bytes = payload_bytes;
    chunk.payload_sha256 = sparkinterval::sha256(records.data(), payload_bytes);
    stream_hasher.update(&chunk, sizeof(chunk));
    stream_hasher.update(records.data(), payload_bytes);
    if (!options.stream_hash_only) {
      output.write(reinterpret_cast<const char*>(&chunk), sizeof(chunk));
      output.write(reinterpret_cast<const char*>(records.data()),
                   static_cast<std::streamsize>(payload_bytes));
      if (!output) fail("cannot write complete Gamma Taylor V2 chunk");
    }
    if (produced == 0U) {
      result.first_record_sha256 = sparkinterval::sha256_hex(
          records.data(), sizeof(pg2::Record));
    }
    result.last_record_sha256 = sparkinterval::sha256_hex(
        &records.back(), sizeof(pg2::Record));
    result.record_payload_bytes += payload_bytes;
    result.authenticated_stream_bytes += sizeof(chunk) + payload_bytes;
    produced += chunk_count;
    ++result.chunks;
  }

  const auto stream_digest = stream_hasher.finish();
  result.stream_sha256 = sparkinterval::lowercase_hex(stream_digest);
  pg2::Footer footer{};
  footer.magic = pg2::kFooterMagic;
  footer.version = pg2::kVersion;
  footer.footer_bytes = sizeof(footer);
  footer.first_block = options.stream_first_block;
  footer.block_count = options.stream_blocks;
  footer.chunk_count = result.chunks;
  footer.record_payload_bytes = result.record_payload_bytes;
  footer.authenticated_stream_bytes = result.authenticated_stream_bytes;
  footer.header_sha256 = header_digest;
  footer.stream_sha256 = stream_digest;
  if (!options.stream_hash_only) {
    output.write(reinterpret_cast<const char*>(&footer), sizeof(footer));
    output.close();
    if (!output) fail("cannot write complete Gamma Taylor V2 footer");
  }
  result.artifact_bytes = result.authenticated_stream_bytes + sizeof(footer);
  const auto stopped = std::chrono::steady_clock::now();
  result.elapsed_seconds =
      std::chrono::duration<double>(stopped - started).count();
  return result;
}

int run_v2(const Options& options) {
  if (options.stream_blocks == 0U) {
    fail("V2 executable requires all-window --stream-blocks mode");
  }
  require_flint_identity();
  const V2Result result = produce_v2_stream(options);
  const double records_per_second =
      static_cast<double>(options.stream_blocks) / result.elapsed_seconds;
  const std::uint64_t first_height =
      pw::kSourceLower + pw::kWindowStep / 2U +
      options.stream_first_block * pw::kWindowStep;
  const std::uint64_t last_height =
      first_height + (options.stream_blocks - 1U) * pw::kWindowStep;
  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-gamma-taylor-stream.v2\""
            << ",\"claim_scope\":\"two_limb_outward_flint_projection_stream\""
            << ",\"first_block\":" << options.stream_first_block
            << ",\"block_count\":" << options.stream_blocks
            << ",\"full_block_count\":" << pw::kFullBlockCount
            << ",\"first_window_center\":" << first_height
            << ",\"last_window_center\":" << last_height
            << ",\"record_bytes\":" << sizeof(pg2::Record)
            << ",\"chunk_records\":" << options.stream_chunk_records
            << ",\"chunk_count\":" << result.chunks
            << ",\"record_payload_bytes\":" << result.record_payload_bytes
            << ",\"artifact_bytes\":" << result.artifact_bytes
            << ",\"hash_only\":"
            << (options.stream_hash_only ? "true" : "false")
            << ",\"header_sha256\":\"" << result.header_sha256 << "\""
            << ",\"stream_sha256\":\"" << result.stream_sha256 << "\""
            << ",\"first_record_sha256\":\""
            << result.first_record_sha256 << "\""
            << ",\"last_record_sha256\":\""
            << result.last_record_sha256 << "\""
            << ",\"audited_records\":" << result.audits
            << ",\"audit_passed\":true"
            << ",\"elapsed_seconds\":" << result.elapsed_seconds
            << ",\"records_per_second\":" << records_per_second
            << ",\"coefficient_projection\":\"complex_disk106\""
            << ",\"gaussian_exact_rational\":\"1/26912\""
            << ",\"flint_version\":\"3.6.0\""
            << ",\"flint_commit\":\"" << SPARKINTERVAL_FLINT_PLATT_COMMIT
            << "\",\"flint_to_mathlib_proved\":false"
            << ",\"pt21_atom_discharged\":false}\n";
  flint_cleanup_master();
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run_v2(parse_options(argc, argv));
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 2;
  }
}
