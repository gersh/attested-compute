// H100 device-policy wrapper around the target-neutral Moebius segment
// runner.  This is device selection, not attestation and not a proof of either
// full 10^16 external atom.
// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#define main sparkinterval_target_neutral_mobius_segment_main
#include "../../src/tg_mobius_segment_runner.cpp"
#undef main

#include <iostream>
#include <vector>

#include "h100_runtime_policy.h"

namespace {

void h100_usage() {
  std::cout
      << "usage: sparkinterval-h100-tg-mobius-segment "
         "[--lower N] [--count N] [--incoming-mertens M] "
         "[--incoming-squarefree Q] [--incoming-little-mertens-lower L] "
         "[--incoming-little-mertens-upper U] "
         "[--previous-receipt-sha256 HEX] "
         "[--device N]\n"
         "Requires exactly one visible NVIDIA H100 (compute capability 9.0); "
         "cross-device overrides are disabled. This checks one bounded exact "
         "Moebius/squarefree state transition with exact directed "
         "little-Mertens checks.\n";
}

}  // namespace

int main(int argc, char** argv) {
  if (sparkinterval::h100::preflight_help_requested(argc, argv)) {
    h100_usage();
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
  return sparkinterval_target_neutral_mobius_segment_main(argc + 1,
                                                           forwarded.data());
}
