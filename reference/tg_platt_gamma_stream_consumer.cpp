// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_gamma_stream.hpp"

#include <charconv>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>

namespace pgs = sparkinterval::tg::platt_gamma_stream;

namespace {

std::uint64_t integer(std::string_view text, const char* label) {
  std::uint64_t value = 0;
  const auto parsed =
      std::from_chars(text.data(), text.data() + text.size(), value);
  if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return value;
}

int run(int argc, char** argv) {
  if (argc != 4) {
    throw std::runtime_error(
        "usage: sparkinterval-tg-platt-gamma-stream-consumer "
        "STREAM FIRST_BLOCK BLOCK_COUNT");
  }
  const std::uint64_t first_block = integer(argv[2], "first block");
  const std::uint64_t block_count = integer(argv[3], "block count");
  std::ifstream input(argv[1], std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor stream");

  pgs::GammaTaylorStreamReader reader(input, first_block, block_count);
  std::uint64_t chunks = 0;
  std::uint64_t records = 0;
  std::uint64_t maximum_chunk_records = 0;
  pgs::AuthenticatedChunk chunk;
  while (reader.next(chunk)) {
    ++chunks;
    records += chunk.records.size();
    maximum_chunk_records =
        std::max<std::uint64_t>(maximum_chunk_records, chunk.records.size());
  }
  std::cout
      << "{\"schema\":\"sparkinterval.tg.platt-gamma-stream-consumer.v1\""
      << ",\"accepted\":true"
      << ",\"first_block\":" << first_block
      << ",\"block_count\":" << block_count
      << ",\"chunk_count\":" << chunks
      << ",\"records_consumed\":" << records
      << ",\"maximum_chunk_records\":" << maximum_chunk_records
      << ",\"stream_sha256\":\""
      << sparkinterval::lowercase_hex(reader.stream_sha256()) << "\""
      << ",\"all_chunks_authenticated_before_use\":true"
      << ",\"footer_and_global_digest_checked\":true"
      << ",\"flint_to_mathlib_realization_proved\":false"
      << ",\"pt21_source_claim_discharged\":false}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-gamma-stream-consumer: "
              << error.what() << '\n';
    return 2;
  }
}
