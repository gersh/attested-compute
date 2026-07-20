// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Strict H100 policy wrapper around the target-neutral bounded R2Star chunk
// runner.  Device selection is not hardware attestation or a Lean bridge.

#define main sparkinterval_target_neutral_r2star_chunk_main
#include "../../src/tg_r2star_chunk_runner.cpp"
#undef main

#include <iostream>
#include <vector>

#include "h100_runtime_policy.h"

namespace {

void h100_chunk_usage() {
  std::cout
      << "usage: sparkinterval-h100-tg-r2star-chunk [--lower N] "
         "[--count N] [--incoming-lower I] [--incoming-upper I] "
         "[--previous-hash HEX] [--device N] [--cross-check-serial]\n"
         "Requires exactly one visible NVIDIA H100 (compute capability 9.0); "
         "cross-device overrides are disabled. Produces only a bounded "
         "Python-contract R2Star chunk, resolves rare ambiguous log rows "
         "with exact rational host arithmetic, and can "
         "compare the blocked transition with its serial reference.\n";
}

}  // namespace

int main(int argc, char** argv) {
  if (sparkinterval::h100::preflight_help_requested(argc, argv)) {
    h100_chunk_usage();
    return 0;
  }
  const Options options = parse_options(argc, argv);
  sparkinterval::h100::require_device(options.device);
  std::vector<char*> forwarded;
  forwarded.reserve(static_cast<std::size_t>(argc) + 2);
  for (int index = 0; index < argc; ++index) forwarded.push_back(argv[index]);
  char internal_override[] = "--allow-other-device";
  forwarded.push_back(internal_override);
  forwarded.push_back(nullptr);
  return sparkinterval_target_neutral_r2star_chunk_main(
      argc + 1, forwarded.data());
}
