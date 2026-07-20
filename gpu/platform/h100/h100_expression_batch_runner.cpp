// Strict H100 device-policy wrapper around the target-neutral postfix interval
// runner. This guard establishes runtime device selection only; it is not
// hardware attestation or a PTX-to-hardware refinement proof.

#define main sparkinterval_target_neutral_expression_batch_main
#include "../../src/expression_batch_runner.cpp"
#undef main

#include <iostream>
#include <vector>

#include "h100_runtime_policy.h"

namespace {

void usage() {
  std::cout << "usage: sparkinterval-h100-expression-batch --input FILE "
               "--output FILE [--device N]\n"
               "Requires exactly one visible NVIDIA H100 (compute capability "
               "9.0); cross-device overrides are disabled.\n";
}

}  // namespace

int main(int argc, char** argv) {
  if (sparkinterval::h100::preflight_help_requested(argc, argv)) {
    usage();
    return 0;
  }
  const Options options = parse_options(argc, argv);
  sparkinterval::h100::require_device(options.device);

  std::vector<char*> forwarded;
  forwarded.reserve(static_cast<std::size_t>(argc) + 2);
  for (int index = 0; index < argc; ++index) {
    forwarded.push_back(argv[index]);
  }
  char internal_override[] = "--allow-other-device";
  forwarded.push_back(internal_override);
  forwarded.push_back(nullptr);
  return sparkinterval_target_neutral_expression_batch_main(
      argc + 1, forwarded.data());
}
