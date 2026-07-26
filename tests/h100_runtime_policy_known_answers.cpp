// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include <iostream>
#include <string_view>

#include "h100_runtime_policy.h"
#include "tg_mobius_persistent_device_policy.h"

namespace {

bool reject(
    std::string_view name, int major, int minor,
    std::string_view label) {
  if (sparkinterval::h100::is_h100_sm90(name, major, minor)) {
    std::cerr << "accepted incompatible device fixture: " << label << '\n';
    return false;
  }
  return true;
}

}  // namespace

int main() {
  using sparkinterval::tg::PersistentDeviceClass;
  using sparkinterval::tg::parse_persistent_device_class;
  using sparkinterval::tg::persistent_device_matches;
  using sparkinterval::h100::is_h100_sm90;
  PersistentDeviceClass parsed =
      PersistentDeviceClass::kNvidiaGb10Sm121;
  if (!parse_persistent_device_class("nvidia-gb10-sm121", &parsed) ||
      parsed != PersistentDeviceClass::kNvidiaGb10Sm121 ||
      !parse_persistent_device_class("nvidia-h100-sm90", &parsed) ||
      parsed != PersistentDeviceClass::kNvidiaH100Sm90 ||
      parse_persistent_device_class("gb10", &parsed) ||
      parse_persistent_device_class("nvidia-h100-sm_90", &parsed)) {
    std::cerr << "persistent device-class parser known answers failed\n";
    return 1;
  }
  if (!persistent_device_matches(
          PersistentDeviceClass::kNvidiaGb10Sm121,
          "NVIDIA GB10", 12, 1) ||
      persistent_device_matches(
          PersistentDeviceClass::kNvidiaGb10Sm121,
          "NVIDIA H100 80GB HBM3", 9, 0) ||
      !persistent_device_matches(
          PersistentDeviceClass::kNvidiaH100Sm90,
          "NVIDIA H100 80GB HBM3", 9, 0) ||
      persistent_device_matches(
          PersistentDeviceClass::kNvidiaH100Sm90,
          "NVIDIA GB10", 12, 1)) {
    std::cerr << "persistent device policy known answers failed\n";
    return 1;
  }
  if (!is_h100_sm90("NVIDIA H100 80GB HBM3", 9, 0) ||
      !is_h100_sm90("NVIDIA H100 PCIe", 9, 0) ||
      !is_h100_sm90("NVIDIA H100 NVL", 9, 0)) {
    std::cerr << "rejected a supported H100 sm_90 fixture\n";
    return 1;
  }
  if (!reject("NVIDIA GB10", 12, 1, "GB10") ||
      !reject("NVIDIA A100-SXM4-80GB", 8, 0, "A100") ||
      !reject("NVIDIA H100 80GB HBM3", 8, 0, "H100 wrong major") ||
      !reject("NVIDIA H100 80GB HBM3", 9, 1, "H100 wrong minor") ||
      !reject("NVIDIA H100X", 9, 0, "H100 prefix without boundary") ||
      !reject("forged H100", 9, 0, "non-NVIDIA H100 substring")) {
    return 1;
  }
  return 0;
}
