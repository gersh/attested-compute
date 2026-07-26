// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstdint>
#include <cstdlib>
#include <string_view>

namespace sparkinterval {

inline constexpr std::uint64_t kLocalKatMaximumWorkItems = 64;
inline constexpr std::string_view kAzureMeasuredWorkerScope =
    "sparkinterval.azure-measured-worker.v1";

inline bool is_lower_sha256(std::string_view value) {
  if (value.size() != 64) return false;
  for (const char character : value) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

inline std::string_view environment_value(const char* name) {
  const char* value = std::getenv(name);
  return value == nullptr ? std::string_view{} : std::string_view(value);
}

// This is accidental-execution hygiene, not attestation. A local process can
// forge its environment. The signed measured-run transcript remains the
// security evidence.
inline bool has_azure_measured_worker_scope() {
  const std::string_view scope =
      environment_value("SPARKINTERVAL_MEASURED_WORKER_SCOPE");
  const std::string_view backend =
      environment_value("SPARKINTERVAL_MEASURED_WORKER_BACKEND");
  const std::string_view challenge = environment_value(
      "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE");
  const std::string_view job_binding = environment_value(
      "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256");
  return scope == kAzureMeasuredWorkerScope &&
         (backend == "azure_ncc40ads_h100_v5" ||
          backend == "azure_sevsnp_cpu") &&
         is_lower_sha256(challenge) && is_lower_sha256(job_binding);
}

inline bool permits_finite_work(std::uint64_t work_items) {
  return work_items <= kLocalKatMaximumWorkItems ||
         has_azure_measured_worker_scope();
}

inline constexpr const char* kCloudOnlyWorkloadError =
    "production arithmetic/replay is cloud-only: measured Azure worker "
    "scope is absent";

}  // namespace sparkinterval
