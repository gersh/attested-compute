// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Strict H100 policy wrapper around the target-neutral persistent
// Moebius/Hurst runner.  The preflight establishes only runtime device
// compatibility.  It is not hardware attestation, compiler refinement,
// source-semantic evidence, or a Lean proof.

#define SPARKINTERVAL_TG_MOBIUS_PERSISTENT_MAIN \
  sparkinterval_target_neutral_mobius_persistent_main
#include "../../src/tg_mobius_persistent_runner.cpp"
#undef SPARKINTERVAL_TG_MOBIUS_PERSISTENT_MAIN

#include <iostream>
#include <vector>

#include "h100_runtime_policy.h"

namespace {

void h100_usage() {
  std::cout
      << "usage: sparkinterval-h100-tg-mobius-persistent "
         "--lower N --count N --shard-rows N "
         "[--super-shard-rows N] "
         "--incoming-mertens M --incoming-squarefree Q "
         "--previous-leaf-sha256 HEX --source-prime-roster FILE "
         "--require-device-class nvidia-h100-sm90 "
         "[--device N] [--qualification-write-mu FILE]\n"
         "Requires exactly one visible NVIDIA H100 (compute capability 9.0); "
         "external cross-device overrides are disabled. Emits a persistent "
         "hash chain of compact exact-arithmetic leaf summaries. Device "
         "selection is not attestation, compiler refinement, source-semantic "
         "evidence, or a Lean proof.\n";
}

std::vector<char*> strict_h100_arguments(int argc, char** argv) {
  std::vector<char*> forwarded;
  forwarded.reserve(static_cast<std::size_t>(argc) + 1);
  forwarded.push_back(argv[0]);
  bool required_class_seen = false;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--allow-other-device") {
      sparkinterval::h100::fail(
          "--allow-other-device is disabled by the H100 runner");
    }
    if (argument == "--require-device-class") {
      if (required_class_seen) {
        sparkinterval::h100::fail(
            "--require-device-class may be supplied only once");
      }
      if (++index >= argc ||
          std::string_view(argv[index]) != "nvidia-h100-sm90") {
        sparkinterval::h100::fail(
            "--require-device-class must be exactly nvidia-h100-sm90");
      }
      required_class_seen = true;
      forwarded.push_back(argv[index - 1]);
      forwarded.push_back(argv[index]);
      continue;
    }
    forwarded.push_back(argv[index]);
  }
  if (!required_class_seen) {
    sparkinterval::h100::fail(
        "strict H100 execution requires "
        "--require-device-class nvidia-h100-sm90");
  }
  return forwarded;
}

}  // namespace

int main(int argc, char** argv) {
  if (sparkinterval::h100::preflight_help_requested(argc, argv)) {
    h100_usage();
    return 0;
  }
  std::vector<char*> forwarded = strict_h100_arguments(argc, argv);
  const int forwarded_argc = static_cast<int>(forwarded.size());
  forwarded.push_back(nullptr);
  const PersistentOptions options =
      parse_persistent_options(forwarded_argc, forwarded.data());
  sparkinterval::h100::require_device(options.device);
  return sparkinterval_target_neutral_mobius_persistent_main(
      forwarded_argc, forwarded.data());
}
