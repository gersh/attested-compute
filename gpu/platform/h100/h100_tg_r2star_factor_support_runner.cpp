// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// H100 device-policy wrapper around the target-neutral R2Star factor-support
// runner.  This establishes device selection, not hardware attestation and
// not the analytic R2Star inequality.

#define main sparkinterval_target_neutral_r2star_factor_support_main
#include "../../src/tg_r2star_factor_support_runner.cpp"
#undef main

#include <iostream>
#include <vector>

#include "h100_runtime_policy.h"

namespace {

void h100_usage() {
  std::cout
      << "usage: sparkinterval-h100-tg-r2star-factor-support "
         "[--lower N] [--count N] [--device N]\n"
         "Requires exactly one visible NVIDIA H100 (compute capability 9.0); "
         "cross-device overrides are disabled. This checks only a bounded "
         "distinct-prime-factor support segment.\n";
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
  return sparkinterval_target_neutral_r2star_factor_support_main(
      argc + 1, forwarded.data());
}
