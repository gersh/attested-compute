// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <string_view>

namespace sparkinterval::tg {

enum class PersistentDeviceClass {
  kNvidiaGb10Sm121,
  kNvidiaH100Sm90,
};

inline constexpr std::string_view kNvidiaGb10Sm121 =
    "nvidia-gb10-sm121";
inline constexpr std::string_view kNvidiaH100Sm90 =
    "nvidia-h100-sm90";
inline constexpr std::string_view kH100NamePrefix = "NVIDIA H100";

inline constexpr bool parse_persistent_device_class(
    std::string_view text, PersistentDeviceClass* result) noexcept {
  if (text == kNvidiaGb10Sm121) {
    *result = PersistentDeviceClass::kNvidiaGb10Sm121;
    return true;
  }
  if (text == kNvidiaH100Sm90) {
    *result = PersistentDeviceClass::kNvidiaH100Sm90;
    return true;
  }
  return false;
}

inline constexpr std::string_view persistent_device_class_name(
    PersistentDeviceClass device_class) noexcept {
  switch (device_class) {
    case PersistentDeviceClass::kNvidiaGb10Sm121:
      return kNvidiaGb10Sm121;
    case PersistentDeviceClass::kNvidiaH100Sm90:
      return kNvidiaH100Sm90;
  }
  return {};
}

inline constexpr bool persistent_device_matches(
    PersistentDeviceClass device_class, std::string_view name,
    int major, int minor) noexcept {
  switch (device_class) {
    case PersistentDeviceClass::kNvidiaGb10Sm121:
      return name == "NVIDIA GB10" && major == 12 && minor == 1;
    case PersistentDeviceClass::kNvidiaH100Sm90:
      return major == 9 && minor == 0 &&
             name.substr(0, kH100NamePrefix.size()) == kH100NamePrefix &&
             (name.size() == kH100NamePrefix.size() ||
              name[kH100NamePrefix.size()] == ' ');
  }
  return false;
}

}  // namespace sparkinterval::tg
