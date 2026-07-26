// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/measured_worker_scope.hpp"

#include <cstdlib>
#include <iostream>

namespace {

constexpr const char* kNames[] = {
    "SPARKINTERVAL_MEASURED_WORKER_SCOPE",
    "SPARKINTERVAL_MEASURED_WORKER_BACKEND",
    "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE",
    "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256",
};

void clear_scope() {
  for (const char* name : kNames) unsetenv(name);
}

bool install_scope(const char* backend, const char* challenge,
                   const char* binding) {
  return setenv(kNames[0], "sparkinterval.azure-measured-worker.v1", 1) == 0 &&
         setenv(kNames[1], backend, 1) == 0 &&
         setenv(kNames[2], challenge, 1) == 0 &&
         setenv(kNames[3], binding, 1) == 0;
}

}  // namespace

int main() {
  constexpr const char* kChallenge =
      "1111111111111111111111111111111111111111111111111111111111111111";
  constexpr const char* kBinding =
      "2222222222222222222222222222222222222222222222222222222222222222";

  clear_scope();
  if (!sparkinterval::permits_finite_work(64) ||
      sparkinterval::permits_finite_work(65) ||
      sparkinterval::has_azure_measured_worker_scope()) {
    return 1;
  }
  if (!install_scope("azure_sevsnp_cpu", kChallenge, kBinding) ||
      !sparkinterval::permits_finite_work(65)) {
    return 2;
  }
  if (!install_scope("azure_ncc40ads_h100_v5", kChallenge, kBinding) ||
      !sparkinterval::permits_finite_work(UINT64_MAX)) {
    return 3;
  }
  if (!install_scope("local", kChallenge, kBinding) ||
      sparkinterval::permits_finite_work(65)) {
    return 4;
  }
  if (!install_scope("azure_sevsnp_cpu", "ABC", kBinding) ||
      sparkinterval::permits_finite_work(65)) {
    return 5;
  }
  clear_scope();
  std::cout << "measured worker scope: bounded KAT passed\n";
  return 0;
}
