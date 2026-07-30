// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Reusable in-process construction of the four rigorous Arb inputs used by
// each of the two one-sided Turing calls in the pinned PT21 windowed zeta
// computation.
//
// The implementation is the same translation unit that backs the standalone
// `sparkinterval-tg-platt-pt21-turing-inputs` executable, so a worker that
// calls `artifact_json` in process produces the identical canonical bytes.
// This header deliberately does not expose FLINT/Arb types: it is included by
// CUDA translation units that must not see `flint/arb.h`.
//
// Nothing here claims the analytic Turing theorem.  It closes only the finite
// numerical boundary: for block j it evaluates the source formulas on exactly
//
//   turing_min: [10^10 + 1008j - 21, 10^10 + 1008j]
//   turing_max: [10^10 + 1008(j+1), 10^10 + 1008(j+1) + 21].

#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>

namespace sparkinterval::tg::platt_pt21_turing_inputs {

inline constexpr std::uint64_t kSourceLower = 10'000'000'000ULL;
inline constexpr std::uint64_t kSourceStep = 1'008ULL;
inline constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
inline constexpr std::uint64_t kTuringWidth = 21ULL;
inline constexpr int kRetainedPrecisionBits = 128;
inline constexpr int kReplayPrecisionBits = 256;
// The canonical artifact is small and fixed-shape; this bound matches the
// independent Python decoder's cap.
inline constexpr std::uint32_t kMaximumArtifactBytes = 16U * 1024U;

inline constexpr char kSchema[] =
    "sparkinterval.tg.platt-pt21-turing-inputs.v1";
inline constexpr char kAlgorithm[] =
    "pinned-platt-pt21-one-sided-turing-inputs-flint-3.6-v1";
inline constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";
inline constexpr char kTuringSourceSha256[] =
    "07305e04e85477749ced09325c9e78388dd55d6107aa526d3becde345a430c27";
inline constexpr char kFlintCommit[] =
    "8d5454b96761fafe4d5a9da76a369a602f500f49";
inline constexpr char kInterpolationPatchSha256[] =
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3";

class TuringInputsError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

// Return the canonical newline-terminated JSON artifact for one PT21 block.
//
// `required_sign_packet_sha256` must be 64 lowercase hexadecimal digits; it is
// transported verbatim and binds the artifact to the exact required-region
// packet whose disks produced this window.  Every emitted endpoint is an exact
// reduced dyadic rational obtained from an outward 128-bit Arb interval, and a
// second 256-bit evaluation must be contained in the retained interval before
// anything is returned.  Any failure throws; no partial artifact is produced.
std::string artifact_json(std::uint64_t block,
                          std::string_view required_sign_packet_sha256);

// True exactly when `value` is 64 lowercase hexadecimal digits.
bool is_lower_sha256(std::string_view value);

}  // namespace sparkinterval::tg::platt_pt21_turing_inputs
