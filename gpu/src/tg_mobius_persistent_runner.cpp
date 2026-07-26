// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Reuse the reviewed parsing, roster authentication, SHA-256, and exact host
// affine-finalization helpers without making a second subtly different copy.
#define main sparkinterval_tg_mobius_one_shot_main
#include "tg_mobius_segment_runner.cpp"
#undef main

#ifndef SPARKINTERVAL_TG_MOBIUS_PERSISTENT_MAIN
#define SPARKINTERVAL_TG_MOBIUS_PERSISTENT_MAIN main
#endif

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include "tg_mobius_persistent_device_policy.h"

namespace {

constexpr std::uint64_t kPersistentMinimumLower =
    1'000'000'000'001ULL;
constexpr std::uint64_t kPersistentMaximumSuperShardRows =
    1'000'000'000ULL;
constexpr std::string_view kPersistentAlgorithm =
    "tg_mobius_fused_affine_persistent_v1";
constexpr std::string_view kPersistentSeed7QualificationAlgorithm =
    "tg_mobius_fused_affine_persistent_residue_2357_qualification_v1";
constexpr std::string_view kPersistentSeed11QualificationAlgorithm =
    "tg_mobius_fused_affine_persistent_residue_235711_qualification_v1";
constexpr std::string_view kPersistentSeed13QualificationAlgorithm =
    "tg_mobius_fused_affine_persistent_residue_23571113_qualification_v1";
constexpr std::string_view kPersistentBlockComposeQualificationAlgorithm =
    "tg_mobius_fused_affine_persistent_block_compose";
constexpr std::string_view
    kPersistentSeed7BlockComposeQualificationAlgorithm =
        "tg_mobius_fused_affine_persistent_residue_2357_"
        "block_compose";
constexpr std::string_view
    kPersistentSeed11BlockComposeQualificationAlgorithm =
        "tg_mobius_fused_affine_persistent_residue_235711_"
        "block_compose";
constexpr std::string_view
    kPersistentSeed13BlockComposeQualificationAlgorithm =
        "tg_mobius_fused_affine_persistent_residue_23571113_"
        "block_compose";
constexpr std::string_view kPersistentClassification =
    "source_shaped_persistent_leaf_chain_not_source_evidence_"
    "attestation_compiler_refinement_or_lean_proof";
constexpr std::string_view kPersistentSeed7QualificationClassification =
    "qualification_only_residue_2357_not_production_admissible_"
    "or_external_atom_proof";
constexpr std::string_view kPersistentSeed11QualificationClassification =
    "qualification_only_residue_235711_not_production_admissible_"
    "or_external_atom_proof";
constexpr std::string_view kPersistentSeed13QualificationClassification =
    "qualification_only_residue_23571113_not_production_admissible_"
    "or_external_atom_proof";
constexpr std::string_view
    kPersistentBlockComposeQualificationClassification =
        "qualification_only_affine_block_compose_not_production_"
        "admissible_or_external_atom_proof";
constexpr std::string_view
    kPersistentSeed7BlockComposeQualificationClassification =
        "qualification_only_residue_2357_and_affine_block_compose_not_"
        "production_admissible_or_external_atom_proof";
constexpr std::string_view
    kPersistentSeed11BlockComposeQualificationClassification =
        "qualification_only_residue_235711_and_affine_block_compose_not_"
        "production_admissible_or_external_atom_proof";
constexpr std::string_view
    kPersistentSeed13BlockComposeQualificationClassification =
        "qualification_only_residue_23571113_and_affine_block_compose_not_"
        "production_admissible_or_external_atom_proof";
constexpr std::string_view kPersistentMuDomain =
    "sparkinterval.tg.mobius-persistent-mu-plus-one.v1";
constexpr std::string_view kPersistentLeafDomain =
    "sparkinterval.tg.mobius-persistent-leaf.v1";
constexpr std::string_view kPersistentSeed7QualificationLeafDomain =
    "sparkinterval.tg.mobius-persistent-residue-2357-"
    "qualification-leaf.v1";
constexpr std::string_view kPersistentSeed11QualificationLeafDomain =
    "sparkinterval.tg.mobius-persistent-residue-235711-"
    "qualification-leaf.v1";
constexpr std::string_view kPersistentSeed13QualificationLeafDomain =
    "sparkinterval.tg.mobius-persistent-residue-23571113-"
    "qualification-leaf.v1";
constexpr std::string_view
    kPersistentBlockComposeQualificationLeafDomain =
        "sparkinterval.tg.mobius-persistent-affine-block-compose";
constexpr std::string_view
    kPersistentSeed7BlockComposeQualificationLeafDomain =
        "sparkinterval.tg.mobius-persistent-residue-2357-affine-"
        "block-compose";
constexpr std::string_view
    kPersistentSeed11BlockComposeQualificationLeafDomain =
        "sparkinterval.tg.mobius-persistent-residue-235711-affine-"
        "block-compose";
constexpr std::string_view
    kPersistentSeed13BlockComposeQualificationLeafDomain =
        "sparkinterval.tg.mobius-persistent-residue-23571113-affine-"
        "block-compose";

struct PersistentOptions {
  std::uint64_t lower = 0;
  std::uint64_t count = 0;
  std::uint64_t shard_rows = 100'000'000;
  std::uint64_t super_shard_rows = 0;
  std::int64_t incoming_mertens = 0;
  std::uint64_t incoming_squarefree = 0;
  std::string previous_leaf_sha256;
  std::string source_prime_roster;
  std::string qualification_write_mu;
  int device = 0;
  sparkinterval::tg::PersistentDeviceClass required_device_class =
      sparkinterval::tg::PersistentDeviceClass::kNvidiaGb10Sm121;
  bool allow_other_device = false;
  bool required_device_class_given = false;
  bool incoming_mertens_given = false;
  bool incoming_squarefree_given = false;
  bool qualification_residue_2357_seed = false;
  bool qualification_residue_235711_seed = false;
  bool qualification_residue_23571113_seed = false;
  bool qualification_residue_rectangular = false;
  TgMobiusRectangularSlotMode qualification_rectangular_mode =
      TgMobiusRectangularSlotMode::kRect2d512;
  bool qualification_affine_block_compose = false;
};

PersistentOptions parse_persistent_options(int argc, char** argv) {
  PersistentOptions options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(require_value("--lower"), &options.lower)) {
        fail("--lower must be an unsigned integer");
      }
    } else if (argument == "--count") {
      if (!parse_u64(require_value("--count"), &options.count)) {
        fail("--count must be an unsigned integer");
      }
    } else if (argument == "--shard-rows") {
      if (!parse_u64(require_value("--shard-rows"),
                     &options.shard_rows)) {
        fail("--shard-rows must be an unsigned integer");
      }
    } else if (argument == "--super-shard-rows") {
      if (!parse_u64(require_value("--super-shard-rows"),
                     &options.super_shard_rows)) {
        fail("--super-shard-rows must be an unsigned integer");
      }
    } else if (argument == "--incoming-mertens") {
      if (!parse_i64(require_value("--incoming-mertens"),
                     &options.incoming_mertens)) {
        fail("--incoming-mertens must be a signed 64-bit integer");
      }
      options.incoming_mertens_given = true;
    } else if (argument == "--incoming-squarefree") {
      if (!parse_u64(require_value("--incoming-squarefree"),
                     &options.incoming_squarefree)) {
        fail("--incoming-squarefree must be an unsigned integer");
      }
      options.incoming_squarefree_given = true;
    } else if (argument == "--previous-leaf-sha256") {
      options.previous_leaf_sha256 =
          std::string(require_value("--previous-leaf-sha256"));
      if (!is_digest(options.previous_leaf_sha256)) {
        fail("--previous-leaf-sha256 must be 64 lowercase hexadecimal characters");
      }
    } else if (argument == "--source-prime-roster") {
      options.source_prime_roster =
          std::string(require_value("--source-prime-roster"));
    } else if (argument == "--qualification-write-mu") {
      options.qualification_write_mu =
          std::string(require_value("--qualification-write-mu"));
    } else if (argument == "--qualification-residue-2357-seed") {
      options.qualification_residue_2357_seed = true;
    } else if (argument == "--qualification-residue-235711-seed") {
      options.qualification_residue_235711_seed = true;
    } else if (argument == "--qualification-residue-23571113-seed") {
      options.qualification_residue_23571113_seed = true;
    } else if (argument == "--qualification-residue-rectangular") {
      const std::string_view mode =
          require_value("--qualification-residue-rectangular");
      if (mode == "rect2d512") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2d512;
      } else if (mode == "rect2dPower") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dPower;
      } else if (mode == "rect2dExact") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dExact;
      } else if (mode == "rect2dCountExact") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dCountExact;
      } else {
        fail("--qualification-residue-rectangular must be rect2d512, "
             "rect2dPower, rect2dExact, or rect2dCountExact");
      }
      options.qualification_residue_rectangular = true;
    } else if (argument == "--qualification-affine-block-compose") {
      options.qualification_affine_block_compose = true;
    } else if (argument == "--device") {
      std::uint64_t parsed = 0;
      if (!parse_u64(require_value("--device"), &parsed) ||
          parsed >
              static_cast<std::uint64_t>(
                  std::numeric_limits<int>::max())) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--require-device-class") {
      if (options.required_device_class_given) {
        fail("--require-device-class may be supplied only once");
      }
      const std::string_view device_class =
          require_value("--require-device-class");
      if (!sparkinterval::tg::parse_persistent_device_class(
              device_class, &options.required_device_class)) {
        fail("--require-device-class must be nvidia-gb10-sm121 "
             "or nvidia-h100-sm90");
      }
      options.required_device_class_given = true;
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-mobius-persistent "
             "--lower N --count N --shard-rows N "
             "[--super-shard-rows N] "
             "--incoming-mertens M --incoming-squarefree Q "
             "--previous-leaf-sha256 HEX --source-prime-roster FILE "
             "[--device N] "
             "[--require-device-class "
             "nvidia-gb10-sm121|nvidia-h100-sm90] "
             "[--allow-other-device] "
             "[--qualification-residue-2357-seed] "
             "[--qualification-residue-235711-seed] "
             "[--qualification-residue-23571113-seed] "
             "[--qualification-residue-rectangular "
             "rect2d512|rect2dPower|rect2dExact|rect2dCountExact] "
             "[--qualification-affine-block-compose] "
             "[--qualification-write-mu FILE]\n"
             "Runs many contiguous terminal-range fused Moebius/affine "
             "receipt leaves while loading and uploading the authenticated "
             "prime roster once and reusing all CUDA allocations, events, "
             "and scan workspace. A super-shard performs one fused sieve "
             "for an integral number of receipt leaves; it defaults to one "
             "leaf and is bounded by 1000000000 rows. Emits one hash-chained "
             "JSON record per receipt leaf. The residue-2357 switch is a "
             "qualification-only candidate: it derives p=7 from n modulo "
             "49 and leaves the production default unchanged. The distinct "
             "residue-235711 candidate derives p=11 from n modulo 121, "
             "requires [2,3,5,7,11], and uses the same 512-slot geometry as "
             "the p=7 candidate. The distinct residue-23571113 candidate "
             "derives p=13 from n modulo 169 and requires "
             "[2,3,5,7,11,13]. The rectangular switch selects a separately "
             "identified 2D schedule for the chosen seed (default 235) and "
             "binds every realized super-shard geometry into its leaf chain. "
             "The affine "
             "block-compose switch replaces the count-row global prefix "
             "array with ordered 65,536-row relative summaries and is also "
             "qualification-only. This is "
             "source-shaped execution "
             "machinery, not "
             "source evidence, attestation, compiler refinement, or a Lean "
             "proof.\n";
      std::exit(0);
    } else {
      fail("unknown persistent argument: " + std::string(argument));
    }
  }
  if (options.lower < kPersistentMinimumLower ||
      options.lower > kSourceLimit) {
    fail("--lower must lie wholly above 10^12 and at most 10^16");
  }
  if (options.count == 0 ||
      options.count - 1 > kSourceLimit - options.lower) {
    fail("persistent range must be a nonempty subset through 10^16");
  }
  if (options.shard_rows == 0 ||
      options.shard_rows > kMaximumSegmentCount) {
    fail("--shard-rows must lie in [1, 100000000]");
  }
  if (options.super_shard_rows == 0) {
    options.super_shard_rows = options.shard_rows;
  }
  if (options.super_shard_rows < options.shard_rows ||
      options.super_shard_rows >
          kPersistentMaximumSuperShardRows ||
      options.super_shard_rows % options.shard_rows != 0) {
    fail("--super-shard-rows must be an integral multiple of "
         "--shard-rows in [shard-rows, 1000000000]");
  }
  if (!options.incoming_mertens_given ||
      !options.incoming_squarefree_given) {
    fail("persistent execution requires both incoming M and Q states");
  }
  if (options.previous_leaf_sha256.empty() ||
      options.previous_leaf_sha256 == kZeroDigest) {
    fail("persistent execution requires a nonzero previous leaf digest");
  }
  if (options.source_prime_roster.empty()) {
    fail("persistent execution requires the authenticated source prime roster");
  }
  const std::uint64_t prior_rows = options.lower - 1;
  if (options.incoming_mertens <
          -static_cast<std::int64_t>(prior_rows) ||
      options.incoming_mertens >
          static_cast<std::int64_t>(prior_rows)) {
    fail("incoming Mertens state exceeds the elementary prefix range");
  }
  if (options.incoming_squarefree > prior_rows) {
    fail("incoming squarefree state exceeds the prefix length");
  }
  if (options.qualification_affine_block_compose &&
      !options.qualification_write_mu.empty()) {
    fail("--qualification-affine-block-compose requires the fused-support "
         "path without --qualification-write-mu");
  }
  const unsigned int residue_seed_mode_count =
      static_cast<unsigned int>(options.qualification_residue_2357_seed) +
      static_cast<unsigned int>(options.qualification_residue_235711_seed) +
      static_cast<unsigned int>(
          options.qualification_residue_23571113_seed);
  if (residue_seed_mode_count > 1) {
    fail("qualification residue seed switches are mutually exclusive");
  }
  return options;
}

std::vector<std::uint32_t> active_prime_prefix_for_leaf(
    std::uint64_t lower, std::size_t count,
    const std::vector<std::uint32_t>& primes,
    std::size_t prime_count,
    std::size_t retained_seed_prime_count) {
  std::vector<std::uint32_t> active;
  active.reserve(std::min(prime_count, count));
  for (std::size_t index = 0; index < prime_count; ++index) {
    const std::uint64_t prime = primes[index];
    const std::uint64_t remainder = lower % prime;
    const std::uint64_t first_offset =
        remainder == 0 ? 0 : prime - remainder;
    // The selected residue initializer requires its complete pinned prefix
    // ([2,3,5] in production, then [2,3,5,7], [2,3,5,7,11], or
    // [2,3,5,7,11,13] in the qualification candidates).
    // Keeping a seed prime that has no hit is semantics-preserving: its event
    // pass is skipped, and the residue update contributes only when it
    // divides n.
    if (index < retained_seed_prime_count ||
        first_offset < count) {
      active.push_back(primes[index]);
    }
  }
  return active;
}

std::string hash_mu_plus_one(
    std::uint64_t lower, std::uint64_t upper_exclusive,
    const unsigned char* encoded, std::size_t count) {
  sparkinterval::detail::Sha256 hasher;
  hasher.update(kPersistentMuDomain.data(), kPersistentMuDomain.size());
  hash_u64_be(&hasher, lower);
  hash_u64_be(&hasher, upper_exclusive);
  hasher.update(encoded, count);
  return sparkinterval::lowercase_hex(hasher.finish());
}

std::int64_t checked_translate_bound(
    std::int64_t local, std::int64_t prefix) {
  const signed __int128 translated =
      static_cast<signed __int128>(local) - prefix;
  if (translated < std::numeric_limits<std::int64_t>::min() ||
      translated > std::numeric_limits<std::int64_t>::max()) {
    fail("translated persistent affine bound left signed 64 bits");
  }
  return static_cast<std::int64_t>(translated);
}

std::int64_t checked_translate_bound(
    std::int64_t local, std::uint64_t prefix) {
  const signed __int128 translated =
      static_cast<signed __int128>(local) -
      static_cast<signed __int128>(prefix);
  if (translated < std::numeric_limits<std::int64_t>::min() ||
      translated > std::numeric_limits<std::int64_t>::max()) {
    fail("translated persistent affine bound left signed 64 bits");
  }
  return static_cast<std::int64_t>(translated);
}

struct PersistentGlobalBound {
  bool present = false;
  std::int64_t value = 0;
  std::uint64_t witness_y = 0;
  std::uint64_t order = 0;
};

struct PersistentRectangularReceiptBinding {
  const TgMobiusRectangularLaunchGeometry* geometry = nullptr;
};

void retain_global_max(
    std::int64_t value, std::uint64_t witness_y,
    std::uint64_t order, PersistentGlobalBound* result) {
  if (!result->present || value > result->value ||
      (value == result->value && order < result->order)) {
    *result = {true, value, witness_y, order};
  }
}

void retain_global_min(
    std::int64_t value, std::uint64_t witness_y,
    std::uint64_t order, PersistentGlobalBound* result) {
  if (!result->present || value < result->value ||
      (value == result->value && order < result->order)) {
    *result = {true, value, witness_y, order};
  }
}

std::string persistent_leaf_digest(
    std::string_view leaf_domain, std::string_view algorithm,
    std::string_view previous, std::uint64_t lower,
    std::uint64_t upper_exclusive,
    std::string_view executable_sha256,
    const AffineMqHostSummary& summary,
    std::int64_t incoming_mertens, std::uint64_t incoming_squarefree,
    std::int64_t outgoing_mertens, std::uint64_t outgoing_squarefree,
    const PersistentRectangularReceiptBinding*
        rectangular_binding) {
  std::ostringstream canonical;
  canonical
      << "domain=" << leaf_domain << '\n'
      << "algorithm=" << algorithm << '\n';
  if (rectangular_binding != nullptr &&
      rectangular_binding->geometry != nullptr) {
    const TgMobiusRectangularLaunchGeometry& geometry =
        *rectangular_binding->geometry;
    canonical
        << "residue_seed=" << residue_seed_name(geometry.seed) << '\n'
        << "rectangular_mode="
        << rectangular_mode_name(geometry.mode) << '\n'
        << "rectangular_slots_per_prime="
        << geometry.slots_per_prime << '\n'
        << "rectangular_required_slots_per_prime="
        << geometry.required_slots_per_prime << '\n'
        << "rectangular_events_per_block="
        << geometry.events_per_block << '\n'
        << "rectangular_multiblock_prime_count="
        << geometry.grid_y << '\n'
        << "rectangular_grid_x=" << geometry.grid_x << '\n'
        << "rectangular_grid_y=" << geometry.grid_y << '\n'
        << "rectangular_grid_z=" << geometry.grid_z << '\n'
        << "rectangular_threads_per_block="
        << geometry.threads_per_block << '\n'
        << "enclosing_super_shard_lower="
        << geometry.enclosing_lower << '\n'
        << "enclosing_super_shard_count="
        << geometry.enclosing_count << '\n';
  }
  canonical
      << "executable_sha256=" << executable_sha256 << '\n'
      << "prime_roster_sha256=" << kSourcePrimeRosterSha256 << '\n'
      << "previous=" << previous << '\n'
      << "lower=" << lower << '\n'
      << "upper_exclusive=" << upper_exclusive << '\n'
      << "poison_count=0\n"
      << "incoming_mertens=" << incoming_mertens << '\n'
      << "outgoing_mertens=" << outgoing_mertens << '\n'
      << "delta_mertens=" << summary.delta.mertens << '\n'
      << "incoming_squarefree=" << incoming_squarefree << '\n'
      << "outgoing_squarefree=" << outgoing_squarefree << '\n'
      << "delta_squarefree=" << summary.delta.squarefree << '\n'
      << "hurst_lower=" << summary.hurst_lower.value << '\n'
      << "hurst_lower_y=" << summary.hurst_lower.witness_y << '\n'
      << "hurst_upper=" << summary.hurst_upper.value << '\n'
      << "hurst_upper_y=" << summary.hurst_upper.witness_y << '\n'
      << "squarefree_lower=" << summary.squarefree_lower.value << '\n'
      << "squarefree_lower_y="
      << summary.squarefree_lower.witness_y << '\n'
      << "squarefree_lower_order="
      << summary.squarefree_lower.order << '\n'
      << "squarefree_upper=" << summary.squarefree_upper.value << '\n'
      << "squarefree_upper_y="
      << summary.squarefree_upper.witness_y << '\n'
      << "squarefree_upper_order="
      << summary.squarefree_upper.order << '\n';
  const std::string bytes = canonical.str();
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

void print_bound_json(const PersistentGlobalBound& bound,
                      bool endpoint_side) {
  if (!bound.present) {
    std::cout << "null";
    return;
  }
  std::cout << "{\"value\":" << bound.value
            << ",\"witness_y\":" << bound.witness_y
            << ",\"source_order\":" << bound.order;
  if (endpoint_side) {
    std::cout << ",\"side\":\""
              << ((bound.order & 1U) == 0
                      ? "integer"
                      : "right_limit")
              << "\"";
  }
  std::cout << '}';
}

}  // namespace

int SPARKINTERVAL_TG_MOBIUS_PERSISTENT_MAIN(int argc, char** argv) {
  const PersistentOptions options =
      parse_persistent_options(argc, argv);
  const bool qualification_seed_seven =
      options.qualification_residue_2357_seed;
  const bool qualification_seed_eleven =
      options.qualification_residue_235711_seed;
  const bool qualification_seed_thirteen =
      options.qualification_residue_23571113_seed;
  const bool qualification_rectangular =
      options.qualification_residue_rectangular;
  const TgMobiusResidueSeed selected_residue_seed =
      qualification_seed_thirteen
          ? TgMobiusResidueSeed::k23571113
          : qualification_seed_eleven
          ? TgMobiusResidueSeed::k235711
          : qualification_seed_seven
                ? TgMobiusResidueSeed::k2357
                : TgMobiusResidueSeed::k235;
  const bool qualification_residue_seed =
      qualification_seed_seven || qualification_seed_eleven ||
      qualification_seed_thirteen;
  const bool qualification_affine_block_compose =
      options.qualification_affine_block_compose;
  const bool qualification_only =
      qualification_residue_seed || qualification_rectangular ||
      qualification_affine_block_compose;
  const std::size_t affine_rows_per_thread =
      tg_mobius_affine_mq_rows_per_thread();
  const std::size_t affine_rows_per_block =
      tg_mobius_affine_mq_rows_per_block();
  if (affine_rows_per_thread != kTgMobiusAffineRowsPerThread ||
      affine_rows_per_block != kTgMobiusAffineRowsPerBlock) {
    fail("Möbius affine header/kernel geometry mismatch");
  }
  const std::string block_compose_geometry =
      "_rpt" + std::to_string(affine_rows_per_thread) +
      "_rpb" + std::to_string(affine_rows_per_block);
  const std::string rectangular_identity =
      "residue_" +
      std::string(residue_seed_name(selected_residue_seed)) + "_" +
      std::string(rectangular_mode_name(
          options.qualification_rectangular_mode));
  const std::string rectangular_scan_algorithm =
      "tg_mobius_fused_affine_persistent_" +
      rectangular_identity + "_qualification_v1";
  const std::string rectangular_block_algorithm_base =
      "tg_mobius_fused_affine_persistent_" +
      rectangular_identity + "_block_compose";
  const std::string rectangular_scan_leaf_domain =
      "sparkinterval.tg.mobius-persistent-" +
      rectangular_identity + "-qualification-leaf.v1";
  const std::string rectangular_block_leaf_domain_base =
      "sparkinterval.tg.mobius-persistent-" +
      rectangular_identity + "-affine-block-compose";
  const std::string block_compose_algorithm =
      std::string(
          qualification_rectangular
              ? std::string_view(rectangular_block_algorithm_base)
              : qualification_seed_thirteen
              ? kPersistentSeed13BlockComposeQualificationAlgorithm
              : qualification_seed_eleven
              ? kPersistentSeed11BlockComposeQualificationAlgorithm
              : qualification_seed_seven
                    ? kPersistentSeed7BlockComposeQualificationAlgorithm
                    : kPersistentBlockComposeQualificationAlgorithm) +
      block_compose_geometry + "_qualification_v1";
  const std::string block_compose_leaf_domain =
      std::string(
          qualification_rectangular
              ? std::string_view(rectangular_block_leaf_domain_base)
              : qualification_seed_thirteen
              ? kPersistentSeed13BlockComposeQualificationLeafDomain
              : qualification_seed_eleven
              ? kPersistentSeed11BlockComposeQualificationLeafDomain
              : qualification_seed_seven
                    ? kPersistentSeed7BlockComposeQualificationLeafDomain
                    : kPersistentBlockComposeQualificationLeafDomain) +
      "-rpt" + std::to_string(affine_rows_per_thread) +
      "-rpb" + std::to_string(affine_rows_per_block) +
      "-qualification-leaf.v1";
  const std::string_view persistent_algorithm =
      qualification_affine_block_compose
          ? std::string_view(block_compose_algorithm)
          : qualification_rectangular
                ? std::string_view(rectangular_scan_algorithm)
                : qualification_seed_thirteen
                ? kPersistentSeed13QualificationAlgorithm
                : qualification_seed_eleven
                ? kPersistentSeed11QualificationAlgorithm
                : qualification_seed_seven
                ? kPersistentSeed7QualificationAlgorithm
                : kPersistentAlgorithm;
  const std::string_view persistent_classification =
      qualification_rectangular
          ? (qualification_affine_block_compose
                 ? std::string_view(
                       "qualification_only_rectangular_residue_and_affine_"
                       "block_compose_not_production_admissible_or_external_"
                       "atom_proof")
                 : std::string_view(
                       "qualification_only_rectangular_residue_not_"
                       "production_admissible_or_external_atom_proof"))
          : qualification_seed_thirteen
          ? (qualification_affine_block_compose
                 ? kPersistentSeed13BlockComposeQualificationClassification
                 : kPersistentSeed13QualificationClassification)
          : qualification_seed_eleven
          ? (qualification_affine_block_compose
                 ? kPersistentSeed11BlockComposeQualificationClassification
                 : kPersistentSeed11QualificationClassification)
          : qualification_seed_seven
          ? (qualification_affine_block_compose
                 ? kPersistentSeed7BlockComposeQualificationClassification
                 : kPersistentSeed7QualificationClassification)
          : (qualification_affine_block_compose
                 ? kPersistentBlockComposeQualificationClassification
                 : kPersistentClassification);
  const std::string_view persistent_leaf_domain =
      qualification_affine_block_compose
          ? std::string_view(block_compose_leaf_domain)
          : qualification_rectangular
                ? std::string_view(rectangular_scan_leaf_domain)
                : qualification_seed_thirteen
                ? kPersistentSeed13QualificationLeafDomain
                : qualification_seed_eleven
                ? kPersistentSeed11QualificationLeafDomain
                : qualification_seed_seven
                ? kPersistentSeed7QualificationLeafDomain
                : kPersistentLeafDomain;
  const bool split_square_support_path =
      options.qualification_write_mu.empty() ||
      qualification_residue_seed || qualification_rectangular;
  const bool production_split_square_support_path =
      options.qualification_write_mu.empty() &&
      !qualification_residue_seed && !qualification_rectangular;
  const auto process_start = std::chrono::steady_clock::now();
  const std::string executable_sha256 = hash_file("/proc/self/exe");
  if (executable_sha256.empty()) {
    fail("could not hash the persistent executable");
  }
  const std::uint64_t upper_exclusive =
      options.lower + options.count;
  const std::uint64_t global_prime_limit =
      integer_square_root(upper_exclusive - 1);

  const auto roster_start = std::chrono::steady_clock::now();
  std::vector<std::uint32_t> primes =
      load_source_prime_roster(options.source_prime_roster);
  primes.erase(
      std::upper_bound(primes.begin(), primes.end(), global_prime_limit),
      primes.end());
  const auto roster_stop = std::chrono::steady_clock::now();

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail(
        "expected exactly one CUDA device; use --allow-other-device "
        "only for explicit cross-device testing",
        4);
  }
  if (options.device >= device_count) {
    fail("requested CUDA device is unavailable", 4);
  }
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));
  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if (!sparkinterval::tg::persistent_device_matches(
          options.required_device_class,
          std::string_view(properties.name),
          properties.major, properties.minor) &&
      !options.allow_other_device) {
    fail(
        "CUDA device does not match required class " +
            std::string(
                sparkinterval::tg::persistent_device_class_name(
                    options.required_device_class)) +
            "; use --allow-other-device only for explicit "
            "cross-device testing",
        4);
  }

  const std::size_t maximum_leaf_count = static_cast<std::size_t>(
      std::min(options.count, options.shard_rows));
  const std::size_t maximum_super_shard_count =
      static_cast<std::size_t>(
          std::min(options.count, options.super_shard_rows));
  TgMobiusRectangularLaunchGeometry rectangular_header_geometry{};
  if (qualification_rectangular) {
    check_cuda(
        "persistent rectangular header geometry",
        tg_mobius_rectangular_launch_geometry_qualification(
            options.lower, maximum_super_shard_count, 0,
            selected_residue_seed,
            options.qualification_rectangular_mode,
            &rectangular_header_geometry));
  }
  std::size_t affine_workspace_bytes = 0;
  if (!qualification_affine_block_compose) {
    check_cuda(
        "persistent affine workspace query",
        tg_mobius_affine_mq_reduced_workspace_size(
            maximum_leaf_count, &affine_workspace_bytes));
    if (affine_workspace_bytes == 0) {
      fail("persistent affine workspace query returned zero");
    }
  }

  std::size_t device_free_bytes = 0;
  std::size_t device_total_bytes = 0;
  check_cuda(
      "cudaMemGetInfo",
      cudaMemGetInfo(&device_free_bytes, &device_total_bytes));

  std::uint32_t* device_roster = nullptr;
  std::uint32_t* device_active_primes = nullptr;
  TgMobiusFusedSupport* device_supports = nullptr;
  std::int8_t* device_mobius = nullptr;
  TgMobiusPrefixMQ* device_prefixes = nullptr;
  TgMobiusAffineMqThreadCandidates* device_candidate = nullptr;
  TgMobiusAffineMqBlockSummary* device_block_summaries = nullptr;
  std::uint32_t* device_poison_count = nullptr;
  void* device_affine_workspace = nullptr;

  const auto allocation_start = std::chrono::steady_clock::now();
  const std::size_t roster_bytes =
      primes.size() * sizeof(std::uint32_t);
  const std::size_t fused_support_device_bytes =
      maximum_super_shard_count * sizeof(TgMobiusFusedSupport);
  const std::size_t mobius_device_bytes =
      options.qualification_write_mu.empty()
          ? 0
          : maximum_super_shard_count * sizeof(std::int8_t);
  const std::size_t affine_prefix_device_rows =
      qualification_affine_block_compose ? 1 : maximum_leaf_count;
  const std::size_t affine_prefix_device_bytes =
      affine_prefix_device_rows * sizeof(TgMobiusPrefixMQ);
  std::size_t affine_block_summary_capacity = 0;
  if (qualification_affine_block_compose) {
    affine_block_summary_capacity =
        tg_mobius_affine_mq_block_summary_count(maximum_leaf_count);
    if (affine_block_summary_capacity == 0) {
      fail("persistent affine block-summary count is zero");
    }
  }
  const std::size_t affine_block_summary_device_bytes =
      affine_block_summary_capacity *
      sizeof(TgMobiusAffineMqBlockSummary);
  const std::size_t persistent_device_allocation_bytes =
      2 * roster_bytes + fused_support_device_bytes +
      mobius_device_bytes + affine_prefix_device_bytes +
      affine_block_summary_device_bytes +
      sizeof(TgMobiusAffineMqThreadCandidates) +
      sizeof(std::uint32_t) + affine_workspace_bytes;
  if (persistent_device_allocation_bytes > device_free_bytes) {
    fail(
        "persistent buffers require " +
        std::to_string(persistent_device_allocation_bytes) +
        " device bytes but cudaMemGetInfo reports only " +
        std::to_string(device_free_bytes) + " free");
  }
  check_cuda(
      "cudaMalloc(persistent roster)",
      cudaMalloc(reinterpret_cast<void**>(&device_roster), roster_bytes));
  check_cuda(
      "cudaMalloc(persistent active primes)",
      cudaMalloc(
          reinterpret_cast<void**>(&device_active_primes), roster_bytes));
  check_cuda(
      "cudaMalloc(persistent fused supports)",
      cudaMalloc(
          reinterpret_cast<void**>(&device_supports),
          fused_support_device_bytes));
  if (mobius_device_bytes != 0) {
    check_cuda(
        "cudaMalloc(persistent mobius)",
        cudaMalloc(
            reinterpret_cast<void**>(&device_mobius),
            mobius_device_bytes));
  }
  check_cuda(
      "cudaMalloc(persistent prefixes)",
      cudaMalloc(
          reinterpret_cast<void**>(&device_prefixes),
          affine_prefix_device_bytes));
  check_cuda(
      "cudaMalloc(persistent candidate)",
      cudaMalloc(
          reinterpret_cast<void**>(&device_candidate),
          sizeof(TgMobiusAffineMqThreadCandidates)));
  if (affine_block_summary_device_bytes != 0) {
    check_cuda(
        "cudaMalloc(persistent affine block summaries)",
        cudaMalloc(
            reinterpret_cast<void**>(&device_block_summaries),
            affine_block_summary_device_bytes));
  }
  check_cuda(
      "cudaMalloc(persistent poison count)",
      cudaMalloc(
          reinterpret_cast<void**>(&device_poison_count),
          sizeof(std::uint32_t)));
  if (affine_workspace_bytes != 0) {
    check_cuda(
        "cudaMalloc(persistent affine workspace)",
        cudaMalloc(&device_affine_workspace, affine_workspace_bytes));
  }
  const auto allocation_stop = std::chrono::steady_clock::now();

  const auto upload_start = std::chrono::steady_clock::now();
  check_cuda(
      "cudaMemcpy(persistent roster)",
      cudaMemcpy(
          device_roster, primes.data(), roster_bytes,
          cudaMemcpyHostToDevice));
  std::vector<std::uint32_t> device_roster_roundtrip(primes.size());
  check_cuda(
      "cudaMemcpy(persistent roster identity roundtrip)",
      cudaMemcpy(
          device_roster_roundtrip.data(), device_roster, roster_bytes,
          cudaMemcpyDeviceToHost));
  if (device_roster_roundtrip != primes) {
    fail("persistent device prime roster differs from the authenticated "
         "host roster after upload");
  }
  const auto upload_stop = std::chrono::steady_clock::now();

  cudaEvent_t start = nullptr;
  cudaEvent_t segment_stop = nullptr;
  cudaEvent_t affine_start = nullptr;
  cudaEvent_t affine_stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda(
      "cudaEventCreate(segment stop)", cudaEventCreate(&segment_stop));
  check_cuda(
      "cudaEventCreate(affine start)", cudaEventCreate(&affine_start));
  check_cuda(
      "cudaEventCreate(affine stop)", cudaEventCreate(&affine_stop));

  std::ofstream qualification_mu;
  if (!options.qualification_write_mu.empty()) {
    qualification_mu.open(
        options.qualification_write_mu,
        std::ios::binary | std::ios::trunc);
    if (!qualification_mu) {
      fail("could not open persistent qualification mu output");
    }
  }

  std::vector<std::int8_t> host_mobius;
  std::vector<unsigned char> encoded_mu;
  if (!options.qualification_write_mu.empty()) {
    host_mobius.resize(maximum_leaf_count);
    encoded_mu.resize(maximum_leaf_count);
  }

  const double roster_load_milliseconds =
      std::chrono::duration<double, std::milli>(
          roster_stop - roster_start).count();
  const double allocation_milliseconds =
      std::chrono::duration<double, std::milli>(
          allocation_stop - allocation_start).count();
  const double roster_upload_milliseconds =
      std::chrono::duration<double, std::milli>(
          upload_stop - upload_start).count();

  std::cout << std::setprecision(17)
            << "{\"record\":\"header\",\"schema\":"
               "\"sparkinterval.tg.mobius-persistent-jsonl.v1\","
            << "\"algorithm\":\"" << persistent_algorithm << "\","
            << "\"classification\":\"" << persistent_classification
            << "\"";
  if (qualification_only) {
    std::cout
        << ",\"receipt_leaf_domain\":\""
        << persistent_leaf_domain
        << "\",\"qualification_only_not_production_admissible\":true";
  }
  std::cout << ",\"lower\":" << options.lower
            << ",\"upper_exclusive\":" << upper_exclusive
            << ",\"count\":" << options.count
            << ",\"shard_rows\":" << options.shard_rows
            << ",\"super_shard_rows\":" << options.super_shard_rows
            << ",\"prime_roster_sha256\":\""
            << kSourcePrimeRosterSha256 << "\","
            << "\"executable_sha256\":\"" << executable_sha256
            << "\","
            << "\"prime_roster_load_count\":1,"
            << "\"prime_roster_upload_count\":1";
  if (qualification_only) {
    std::cout
        << ",\"device_prime_roster_roundtrip_verified\":true,"
        << "\"device_prime_roster_identity_check\":"
           "\"authenticated_host_bytes_equal_device_roundtrip\"";
  }
  std::cout << ",\"cuda_allocation_epoch_count\":1,"
            << "\"cuda_event_set_count\":1,"
            << "\"fused_support_load_balanced_dense_schedule\":true,"
            << "\"fused_support_residue_235_initializer\":true";
  if (qualification_only) {
    std::cout
        << ",\"qualification_residue_2357_seed\":"
        << (qualification_seed_seven ? "true" : "false")
        << ",\"residue_seed_prime_count\":"
        << (qualification_seed_thirteen
                ? kTgMobiusResidue23571113PrimeCount
                : qualification_seed_eleven
                ? kTgMobiusResidue235711PrimeCount
                : qualification_seed_seven
                ? kTgMobiusResidue2357PrimeCount
                : kTgMobiusResidue235PrimeCount)
        << ",\"residue_2357_per_row_modulus\":"
        << kTgMobiusResidue2357Modulus
        << ",\"residue_2357_materialized_table_rows\":0";
    if (qualification_seed_eleven) {
      std::cout
          << ",\"qualification_residue_235711_seed\":true"
          << ",\"residue_235711_initializer_uses_residue_235_table\":true"
          << ",\"residue_235711_per_row_modulus\":"
          << kTgMobiusResidue235711Modulus
          << ",\"residue_235711_materialized_table_rows\":0"
          << ",\"residue_235711_suffix_minimum_prime\":"
          << kTgMobiusResidue235711SuffixMinimum
          << ",\"residue_235711_lean_arithmetic_contract\":"
             "\"SparkInterval.TernaryGoldbach.MobiusResidue235711\"";
    }
    if (qualification_seed_thirteen) {
      std::cout
          << ",\"qualification_residue_23571113_seed\":true"
          << ",\"residue_23571113_initializer_uses_residue_235_table\":true"
          << ",\"residue_23571113_per_row_modulus\":"
          << kTgMobiusResidue23571113Modulus
          << ",\"residue_23571113_materialized_table_rows\":0"
          << ",\"residue_23571113_suffix_minimum_prime\":"
          << kTgMobiusResidue23571113SuffixMinimum
          << ",\"residue_23571113_lean_arithmetic_contract\":"
             "\"SparkInterval.TernaryGoldbach.MobiusResidue23571113\"";
    }
    if (qualification_rectangular) {
      std::cout
          << ",\"qualification_residue_rectangular\":true"
          << ",\"qualification_rectangular_seed\":\""
          << residue_seed_name(selected_residue_seed) << "\""
          << ",\"qualification_rectangular_mode\":\""
          << rectangular_mode_name(
                 options.qualification_rectangular_mode)
          << "\""
          << ",\"qualification_rectangular_header_required_slots_per_"
             "prime\":"
          << rectangular_header_geometry.required_slots_per_prime
          << ",\"qualification_rectangular_header_slots_per_prime\":"
          << rectangular_header_geometry.slots_per_prime
          << ",\"qualification_rectangular_events_per_block\":"
          << rectangular_header_geometry.events_per_block
          << ",\"qualification_rectangular_lean_schedule_contract\":"
             "\"SparkInterval.TernaryGoldbach."
             "MobiusRectangularCUDASchedule\"";
    }
  }
  std::cout << ",\"residue_235_initializer_table_rows\":"
            << kTgMobiusResidue235Modulus << ','
            << "\"residue_235_initializer_table_bytes\":"
            << kTgMobiusResidue235Modulus *
                   sizeof(std::uint64_t)
            << ','
            << "\"residue_235_table_storage\":"
               "\"fatbinary_device_global_init\","
            << "\"residue_235_table_materialization_scope\":"
               "\"cuda_module_context_load\","
            << "\"residue_235_explicit_h2d_upload_bytes_per_sieve\":0,"
            << "\"fused_multiblock_dense_prime_limit\":"
            << kTgMobiusMultiblockDensePrimeLimit << ','
            << "\"fused_multiblock_slots_per_prime\":"
            << (qualification_rectangular
                    ? rectangular_header_geometry.slots_per_prime
                    : qualification_seed_thirteen
                    ? kTgMobiusResidue23571113MultiblockSlotsPerPrime
                    : qualification_seed_eleven
                    ? kTgMobiusResidue235711MultiblockSlotsPerPrime
                    : qualification_seed_seven
                    ? kTgMobiusResidue2357MultiblockSlotsPerPrime
                    : kTgMobiusResidue235MultiblockSlotsPerPrime)
            << ','
            << "\"fused_multiblock_unseeded_slots_per_prime\":"
            << kTgMobiusMultiblockSlotsPerPrime << ','
            << "\"fused_multiblock_residue_235_slots_per_prime\":"
            << kTgMobiusResidue235MultiblockSlotsPerPrime << ','
            << "\"fused_multiblock_residue_235_minimum_safe_slots_per_prime\":"
            << kTgMobiusResidue235MinimumSlotsPerPrime;
  if (qualification_only) {
    std::cout
        << ",\"fused_multiblock_residue_2357_minimum_safe_slots_per_prime\":"
        << kTgMobiusResidue2357MinimumSlotsPerPrime
        << ",\"fused_multiblock_residue_2357_slots_per_prime\":"
        << kTgMobiusResidue2357MultiblockSlotsPerPrime;
    if (qualification_seed_eleven) {
      std::cout
          << ",\"fused_multiblock_residue_235711_minimum_safe_slots_per_"
             "prime\":"
          << kTgMobiusResidue235711MinimumSlotsPerPrime
          << ",\"fused_multiblock_residue_235711_slots_per_prime\":"
          << kTgMobiusResidue235711MultiblockSlotsPerPrime;
    }
    if (qualification_seed_thirteen) {
      std::cout
          << ",\"fused_multiblock_residue_23571113_minimum_safe_slots_per_"
             "prime\":"
          << kTgMobiusResidue23571113MinimumSlotsPerPrime
          << ",\"fused_multiblock_residue_23571113_slots_per_prime\":"
          << kTgMobiusResidue23571113MultiblockSlotsPerPrime;
    }
  }
  std::cout << ",\"fused_multiblock_iterations_per_thread\":"
            << kTgMobiusMultiblockIterationsPerThread << ','
            << "\"affine_candidates_transferred_per_leaf\":1,"
            << "\"affine_candidate_bytes_per_leaf\":"
            << sizeof(TgMobiusAffineMqThreadCandidates) << ','
            << "\"affine_prefix_device_bytes\":"
            << affine_prefix_device_bytes;
  if (qualification_only) {
    std::cout
        << ",\"affine_prefix_device_rows\":"
        << affine_prefix_device_rows
        << ",\"qualification_affine_block_compose\":"
        << (qualification_affine_block_compose
                ? "true"
                : "false")
        << ",\"affine_block_summary_rows\":"
        << affine_rows_per_block
        << ",\"affine_block_summary_rows_per_thread\":"
        << affine_rows_per_thread
        << ",\"affine_block_summary_count\":"
        << affine_block_summary_capacity
        << ",\"affine_block_summary_device_bytes\":"
        << affine_block_summary_device_bytes;
    if (qualification_affine_block_compose) {
      const std::size_t scan_prefix_reference_device_bytes =
          maximum_leaf_count * sizeof(TgMobiusPrefixMQ);
      const std::int64_t net_without_scan_workspace =
          static_cast<std::int64_t>(affine_prefix_device_bytes) +
          static_cast<std::int64_t>(
              affine_block_summary_device_bytes) -
          static_cast<std::int64_t>(
              scan_prefix_reference_device_bytes);
      std::cout
          << ",\"affine_scan_prefix_reference_device_bytes\":"
          << scan_prefix_reference_device_bytes
          << ",\"affine_block_compose_scan_workspace_omitted\":true"
          << ",\"affine_block_compose_net_device_bytes_vs_scan_"
             "excluding_scan_workspace\":"
          << net_without_scan_workspace;
    }
  }
  std::cout << ",\"affine_workspace_device_bytes\":"
            << affine_workspace_bytes << ','
            << "\"fused_support_device_bytes\":"
            << fused_support_device_bytes << ','
            << "\"mobius_device_bytes\":"
            << mobius_device_bytes << ','
            << "\"persistent_device_allocation_bytes\":"
            << persistent_device_allocation_bytes << ','
            << "\"device_free_bytes_before_allocation\":"
            << device_free_bytes << ','
            << "\"device_total_bytes\":"
            << device_total_bytes << ','
            << "\"production_device_to_host_bytes_per_leaf\":76,"
            << "\"production_mu_rows_transferred\":false,"
            << "\"production_mu_rows_hashed\":false,"
            << "\"production_fused_prefix_input_path\":"
            << (production_split_square_support_path &&
                        !qualification_affine_block_compose
                    ? "true"
                    : "false");
  if (qualification_only) {
    std::cout
        << ",\"qualification_fused_prefix_input_path\":"
        << ((qualification_residue_seed ||
             qualification_rectangular) &&
                    !qualification_affine_block_compose &&
                    options.qualification_write_mu.empty()
                ? "true"
                : "false")
        << ",\"qualification_direct_fused_support_block_compose_path\":"
        << (qualification_affine_block_compose ? "true" : "false");
  }
  std::cout << ",\"production_split_square_support_path\":"
            << (production_split_square_support_path
                    ? "true"
                    : "false");
  if (qualification_only) {
    std::cout
        << ",\"qualification_residue_2357_split_square_support_path\":"
        << (qualification_seed_seven ? "true" : "false");
    if (qualification_seed_eleven) {
      std::cout
          << ",\"qualification_residue_235711_split_square_support_path\":"
             "true";
    }
    if (qualification_seed_thirteen) {
      std::cout
          << ",\"qualification_residue_23571113_split_square_support_path\":"
             "true";
    }
    if (qualification_rectangular) {
      std::cout
          << ",\"qualification_residue_rectangular_split_square_support_"
             "path\":true";
    }
  }
  std::cout << ",\"inline_square_modulo_reference_path\":"
            << (split_square_support_path ? "false" : "true")
            << ",\"distinct_factor_events_compute_square_modulo\":"
            << (split_square_support_path ? "false" : "true")
            << ",\"separate_square_strike_pass\":"
            << (split_square_support_path ? "true" : "false")
            << ",\"split_square_dense_prime_limit\":"
            << kTgMobiusSplitSquareDensePrimeLimit
            << ",\"split_square_operation_order\":"
               "\"initialize_then_distinct_then_square_then_finalize\""
            << ",\"intermediate_mobius_device_rows_materialized\":"
            << (options.qualification_write_mu.empty()
                    ? "false"
                    : "true")
            << ','
            << "\"leaf_chain_binds_compact_gpu_summary\":true,"
            << "\"mu_row_commitment_present_in_production\":false,"
            << "\"host_rechecks_final_squarefree_winners\":true,"
            << "\"little_mertens_deltas_are_exact_zero\":true,"
            << "\"qualification_mu_output\":"
            << (options.qualification_write_mu.empty()
                    ? "false"
                    : "true")
            << ",\"source_rows_replayed_independently\":false,"
            << "\"full_source_range\":false,"
            << "\"execution_attested\":false,"
            << "\"cuda_or_cpp_compiler_refinement_proved\":false,"
            << "\"primitive_mobius_realization_proved\":false,"
            << "\"lean_atom_discharged\":false,"
            << "\"proves_any_external_atom\":false,"
            << "\"roster_load_milliseconds\":\""
            << roster_load_milliseconds << "\","
            << "\"allocation_milliseconds\":\""
            << allocation_milliseconds << "\","
            << "\"roster_upload_milliseconds\":\""
            << roster_upload_milliseconds << "\"}\n";
  std::cout.flush();

  std::uint64_t processed = 0;
  std::size_t leaf_index = 0;
  std::int64_t current_mertens = options.incoming_mertens;
  std::uint64_t current_squarefree = options.incoming_squarefree;
  std::int64_t relative_mertens = 0;
  std::uint64_t relative_squarefree = 0;
  std::string previous_leaf = options.previous_leaf_sha256;
  PersistentGlobalBound global_hurst_lower{};
  PersistentGlobalBound global_hurst_upper{};
  PersistentGlobalBound global_squarefree_lower{};
  PersistentGlobalBound global_squarefree_upper{};
  double total_active_filter_milliseconds = 0.0;
  double total_active_upload_milliseconds = 0.0;
  double total_kernel_milliseconds = 0.0;
  double total_affine_milliseconds = 0.0;
  double total_transfer_milliseconds = 0.0;
  double total_control_loop_milliseconds = 0.0;
  std::size_t source_fast_path_leaf_count = 0;
  std::size_t source_fast_path_super_shard_count = 0;
  std::size_t super_shard_index = 0;
  std::size_t sieve_launch_count = 0;

  while (processed < options.count) {
    const auto super_wall_start = std::chrono::steady_clock::now();
    const std::uint64_t super_lower = options.lower + processed;
    const std::size_t super_count = static_cast<std::size_t>(
        std::min<std::uint64_t>(
            options.super_shard_rows, options.count - processed));
    const std::uint64_t super_upper_exclusive =
        super_lower + super_count;
    const std::uint64_t super_prime_limit =
        integer_square_root(super_upper_exclusive - 1);
    const std::size_t super_prime_count =
        static_cast<std::size_t>(
            std::upper_bound(
                primes.begin(), primes.end(), super_prime_limit) -
            primes.begin());

    const auto filter_start = std::chrono::steady_clock::now();
    const bool source_fast_path =
        super_count >= super_prime_limit;
    std::vector<std::uint32_t> active_primes;
    const std::uint32_t* selected_device_primes = device_roster;
    std::size_t selected_prime_count = super_prime_count;
    if (source_fast_path) {
      ++source_fast_path_super_shard_count;
    } else {
      active_primes = active_prime_prefix_for_leaf(
          super_lower, super_count, primes, super_prime_count,
          qualification_seed_eleven
              ? kTgMobiusResidue235711PrimeCount
              : qualification_seed_thirteen
              ? kTgMobiusResidue23571113PrimeCount
              : qualification_seed_seven
              ? kTgMobiusResidue2357PrimeCount
              : kTgMobiusResidue235PrimeCount);
      selected_prime_count = active_primes.size();
      selected_device_primes = device_active_primes;
    }
    const auto filter_stop = std::chrono::steady_clock::now();
    const double active_filter_milliseconds =
        std::chrono::duration<double, std::milli>(
            filter_stop - filter_start).count();
    total_active_filter_milliseconds +=
        active_filter_milliseconds;

    double active_upload_milliseconds = 0.0;
    if (!source_fast_path && !active_primes.empty()) {
      const auto active_upload_start =
          std::chrono::steady_clock::now();
      check_cuda(
          "cudaMemcpy(persistent active primes)",
          cudaMemcpy(
              device_active_primes, active_primes.data(),
              active_primes.size() * sizeof(std::uint32_t),
              cudaMemcpyHostToDevice));
      device_roster_roundtrip.resize(active_primes.size());
      check_cuda(
          "cudaMemcpy(persistent active roster identity roundtrip)",
          cudaMemcpy(
              device_roster_roundtrip.data(), device_active_primes,
              active_primes.size() * sizeof(std::uint32_t),
              cudaMemcpyDeviceToHost));
      if (device_roster_roundtrip != active_primes) {
        fail("persistent active device prime roster differs from its "
             "authenticated host derivation after upload");
      }
      const auto active_upload_stop =
          std::chrono::steady_clock::now();
      active_upload_milliseconds =
          std::chrono::duration<double, std::milli>(
              active_upload_stop - active_upload_start).count();
      total_active_upload_milliseconds +=
          active_upload_milliseconds;
    }

    const std::uint64_t dense_prime_limit =
        1 + (super_count - 1) / 256;
    const auto dense_end = source_fast_path
        ? std::upper_bound(
              primes.begin(),
              primes.begin() +
                  static_cast<std::ptrdiff_t>(super_prime_count),
              dense_prime_limit)
        : std::upper_bound(
              active_primes.begin(), active_primes.end(),
              dense_prime_limit);
    const std::size_t dense_prime_count = source_fast_path
        ? static_cast<std::size_t>(dense_end - primes.begin())
        : static_cast<std::size_t>(
              dense_end - active_primes.begin());
    const std::vector<std::uint32_t>& selected_host_primes =
        source_fast_path ? primes : active_primes;
    const bool valid_seed_prefix =
        qualification_seed_thirteen
            ? tg_mobius_host_roster_begins_23571113(
                  selected_host_primes.data(), selected_prime_count)
            : qualification_seed_eleven
            ? tg_mobius_host_roster_begins_235711(
                  selected_host_primes.data(), selected_prime_count)
            : qualification_seed_seven
            ? tg_mobius_host_roster_begins_2357(
                  selected_host_primes.data(), selected_prime_count)
            : tg_mobius_host_roster_begins_235(
                  selected_host_primes.data(), selected_prime_count);
    if (!valid_seed_prefix) {
      if (qualification_seed_thirteen) {
        fail(
            "persistent residue-23571113 qualification requires the "
            "selected prime roster to begin exactly [2,3,5,7,11,13]");
      }
      if (qualification_seed_eleven) {
        fail(
            "persistent residue-235711 qualification requires the "
            "selected prime roster to begin exactly [2,3,5,7,11]");
      }
      fail(qualification_seed_seven
               ? "persistent residue-2357 qualification requires the "
                 "selected prime roster to begin exactly [2,3,5,7]"
               : "persistent residue-235 initializer requires the selected "
                 "prime roster to begin exactly [2,3,5]");
    }

    TgMobiusRectangularLaunchGeometry rectangular_geometry{};
    check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
    if (qualification_rectangular &&
        options.qualification_write_mu.empty()) {
      check_cuda(
          "persistent rectangular qualification support launch",
          launch_tg_mobius_fused_support_multiblock_dense_residue_rectangular_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              selected_residue_seed,
              options.qualification_rectangular_mode,
              device_supports, device_poison_count,
              &rectangular_geometry));
    } else if (qualification_rectangular) {
      check_cuda(
          "persistent rectangular qualification Moebius launch",
          launch_tg_mobius_fused_segment_multiblock_dense_residue_rectangular_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              selected_residue_seed,
              options.qualification_rectangular_mode,
              device_supports, device_mobius,
              device_poison_count, &rectangular_geometry));
    } else if (qualification_seed_thirteen &&
        options.qualification_write_mu.empty()) {
      check_cuda(
          "persistent residue-23571113 qualification support launch",
          launch_tg_mobius_fused_support_multiblock_dense_residue_23571113_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_poison_count));
    } else if (qualification_seed_thirteen) {
      check_cuda(
          "persistent residue-23571113 qualification Moebius launch",
          launch_tg_mobius_fused_segment_multiblock_dense_residue_23571113_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_mobius,
              device_poison_count));
    } else if (qualification_seed_eleven &&
        options.qualification_write_mu.empty()) {
      check_cuda(
          "persistent residue-235711 qualification support launch",
          launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_poison_count));
    } else if (qualification_seed_eleven) {
      check_cuda(
          "persistent residue-235711 qualification Moebius launch",
          launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_mobius,
              device_poison_count));
    } else if (qualification_seed_seven &&
        options.qualification_write_mu.empty()) {
      check_cuda(
          "persistent residue-2357 qualification support launch",
          launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_poison_count));
    } else if (qualification_seed_seven) {
      check_cuda(
          "persistent residue-2357 qualification Moebius launch",
          launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_mobius,
              device_poison_count));
    } else if (options.qualification_write_mu.empty()) {
      check_cuda(
          "persistent split-square fused support launch",
          launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_poison_count));
    } else {
      check_cuda(
          "persistent fused Moebius launch",
          launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
              super_lower, super_count, selected_device_primes,
              selected_prime_count, dense_prime_count,
              device_supports, device_mobius));
    }
    check_cuda(
        "cudaEventRecord(segment stop)",
        cudaEventRecord(segment_stop));

    float kernel_milliseconds = 0.0F;
    ++sieve_launch_count;

    std::size_t super_processed = 0;
    std::size_t super_leaf_index = 0;
    double super_affine_milliseconds = 0.0;
    while (super_processed < super_count) {
      const auto leaf_wall_start = std::chrono::steady_clock::now();
      const std::uint64_t leaf_lower =
          super_lower + super_processed;
      const std::size_t leaf_count = static_cast<std::size_t>(
          std::min<std::uint64_t>(
              options.shard_rows, super_count - super_processed));
      const std::uint64_t leaf_upper_exclusive =
          leaf_lower + leaf_count;

      check_cuda(
          "cudaMemsetAsync(persistent poison count)",
          cudaMemsetAsync(
              device_poison_count, 0, sizeof(std::uint32_t)));
      check_cuda(
          "cudaEventRecord(affine start)",
          cudaEventRecord(affine_start));
      if (qualification_affine_block_compose) {
        check_cuda(
            "persistent qualification affine block composition",
            launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
                leaf_lower, leaf_count,
                device_supports + super_processed,
                device_block_summaries,
                affine_block_summary_capacity,
                device_prefixes,
                device_candidate, device_poison_count));
      } else if (options.qualification_write_mu.empty()) {
        check_cuda(
            "persistent fused prefix-input finalization",
            launch_tg_mobius_fused_prefix_inputs(
                leaf_lower, device_supports + super_processed,
                leaf_count, device_prefixes, device_poison_count));
        check_cuda(
            "persistent reduced affine prefix-input launch",
            launch_tg_mobius_affine_mq_reduced_from_prefix_inputs(
                leaf_lower, leaf_count, device_prefixes,
                device_candidate, device_affine_workspace,
                affine_workspace_bytes));
      } else {
        check_cuda(
            "persistent reduced affine launch",
            launch_tg_mobius_affine_mq_reduced(
                leaf_lower, device_mobius + super_processed,
                leaf_count, device_prefixes, device_candidate,
                device_affine_workspace, affine_workspace_bytes,
                device_poison_count));
      }
      check_cuda(
          "cudaEventRecord(affine stop)",
          cudaEventRecord(affine_stop));
      check_cuda(
          "cudaEventSynchronize(affine stop)",
          cudaEventSynchronize(affine_stop));

      float affine_milliseconds = 0.0F;
      check_cuda(
          "cudaEventElapsedTime(affine)",
          cudaEventElapsedTime(
              &affine_milliseconds, affine_start, affine_stop));
      if (super_leaf_index == 0) {
        check_cuda(
            "cudaEventElapsedTime(segment)",
            cudaEventElapsedTime(
                &kernel_milliseconds, start, segment_stop));
        total_kernel_milliseconds += kernel_milliseconds;
      }
      total_affine_milliseconds += affine_milliseconds;
      super_affine_milliseconds += affine_milliseconds;

      TgMobiusAffineMqThreadCandidates candidate{};
      TgMobiusPrefixMQ delta{};
      std::uint32_t poison_count = 0;
      const auto transfer_start = std::chrono::steady_clock::now();
      if (!options.qualification_write_mu.empty()) {
        check_cuda(
            "cudaMemcpy(persistent qualification mobius)",
            cudaMemcpy(
                host_mobius.data(),
                device_mobius + super_processed, leaf_count,
                cudaMemcpyDeviceToHost));
      }
      check_cuda(
          "cudaMemcpy(persistent candidate)",
          cudaMemcpy(
              &candidate, device_candidate, sizeof(candidate),
              cudaMemcpyDeviceToHost));
      check_cuda(
          "cudaMemcpy(persistent delta)",
          cudaMemcpy(
              &delta,
              qualification_affine_block_compose
                  ? device_prefixes
                  : device_prefixes + leaf_count - 1,
              sizeof(delta), cudaMemcpyDeviceToHost));
      check_cuda(
          "cudaMemcpy(persistent poison count)",
          cudaMemcpy(
              &poison_count, device_poison_count,
              sizeof(poison_count), cudaMemcpyDeviceToHost));
      const auto transfer_stop = std::chrono::steady_clock::now();
      const double transfer_milliseconds =
          std::chrono::duration<double, std::milli>(
              transfer_stop - transfer_start).count();
      total_transfer_milliseconds += transfer_milliseconds;

      if (poison_count != 0) {
        fail(
            "persistent fused support emitted a "
            "poison/non-Mobius value",
            5);
      }
      std::string leaf_mu_sha256;
      if (!options.qualification_write_mu.empty()) {
        std::int64_t checked_delta_mertens = 0;
        std::uint64_t checked_delta_squarefree = 0;
        for (std::size_t index = 0; index < leaf_count; ++index) {
          const std::int8_t mu = host_mobius[index];
          if (mu < -1 || mu > 1) {
            fail(
                "persistent qualification copied a "
                "non-Mobius value",
                5);
          }
          checked_delta_mertens += mu;
          checked_delta_squarefree += mu != 0;
          encoded_mu[index] =
              static_cast<unsigned char>(
                  static_cast<int>(mu) + 1);
        }
        if (checked_delta_mertens != delta.mertens ||
            checked_delta_squarefree != delta.squarefree) {
          fail(
              "persistent affine terminal delta differs "
              "from copied qualification rows",
              5);
        }
        leaf_mu_sha256 = hash_mu_plus_one(
            leaf_lower, leaf_upper_exclusive,
            encoded_mu.data(), leaf_count);
        qualification_mu.write(
            reinterpret_cast<const char*>(host_mobius.data()),
            static_cast<std::streamsize>(leaf_count));
        if (!qualification_mu) {
          fail(
              "could not write persistent qualification mu output");
        }
      }

      const AffineMqHostSummary summary =
          finalize_affine_mq_candidates(
              leaf_lower, leaf_count, delta, {candidate});
      const std::int64_t incoming_mertens = current_mertens;
      const std::uint64_t incoming_squarefree =
          current_squarefree;
      if ((summary.delta.mertens > 0 &&
           current_mertens >
               std::numeric_limits<std::int64_t>::max() -
                   summary.delta.mertens) ||
          (summary.delta.mertens < 0 &&
           current_mertens <
               std::numeric_limits<std::int64_t>::min() -
                   summary.delta.mertens)) {
        fail("persistent Mertens state overflow");
      }
      current_mertens += summary.delta.mertens;
      if (summary.delta.squarefree >
          std::numeric_limits<std::uint64_t>::max() -
              current_squarefree) {
        fail("persistent squarefree state overflow");
      }
      current_squarefree += summary.delta.squarefree;

      const std::uint64_t global_order_base = 2 * processed;
      retain_global_max(
          checked_translate_bound(
              summary.hurst_lower.value, relative_mertens),
          summary.hurst_lower.witness_y,
          global_order_base + summary.hurst_lower.order,
          &global_hurst_lower);
      retain_global_min(
          checked_translate_bound(
              summary.hurst_upper.value, relative_mertens),
          summary.hurst_upper.witness_y,
          global_order_base + summary.hurst_upper.order,
          &global_hurst_upper);
      retain_global_max(
          checked_translate_bound(
              summary.squarefree_lower.value, relative_squarefree),
          summary.squarefree_lower.witness_y,
          global_order_base + summary.squarefree_lower.order,
          &global_squarefree_lower);
      retain_global_min(
          checked_translate_bound(
              summary.squarefree_upper.value, relative_squarefree),
          summary.squarefree_upper.witness_y,
          global_order_base + summary.squarefree_upper.order,
          &global_squarefree_upper);

      const PersistentRectangularReceiptBinding rectangular_binding{
          qualification_rectangular
              ? &rectangular_geometry
              : nullptr};
      const std::string leaf_digest = persistent_leaf_digest(
          persistent_leaf_domain, persistent_algorithm,
          previous_leaf, leaf_lower, leaf_upper_exclusive,
          executable_sha256, summary, incoming_mertens,
          incoming_squarefree, current_mertens,
          current_squarefree,
          qualification_rectangular
              ? &rectangular_binding
              : nullptr);
      const auto leaf_wall_stop =
          std::chrono::steady_clock::now();
      const double leaf_wall_milliseconds =
          std::chrono::duration<double, std::milli>(
              leaf_wall_stop - leaf_wall_start).count();
      const double control_loop_milliseconds =
          std::max(
              0.0, leaf_wall_milliseconds -
                  static_cast<double>(affine_milliseconds));
      const double amortized_kernel_milliseconds =
          static_cast<double>(kernel_milliseconds) *
          static_cast<double>(leaf_count) /
          static_cast<double>(super_count);
      if (source_fast_path) ++source_fast_path_leaf_count;
      std::cout
          << "{\"record\":\"leaf\",\"index\":" << leaf_index;
      if (qualification_only) {
        std::cout
            << ",\"algorithm\":\"" << persistent_algorithm
            << "\",\"receipt_leaf_domain\":\""
            << persistent_leaf_domain
            << "\",\"qualification_only_not_production_admissible\":true";
      }
      if (qualification_rectangular) {
        std::cout
            << ",\"qualification_rectangular_seed\":\""
            << residue_seed_name(rectangular_geometry.seed) << "\""
            << ",\"qualification_rectangular_mode\":\""
            << rectangular_mode_name(rectangular_geometry.mode) << "\""
            << ",\"qualification_rectangular_required_slots_per_prime\":"
            << rectangular_geometry.required_slots_per_prime
            << ",\"qualification_rectangular_slots_per_prime\":"
            << rectangular_geometry.slots_per_prime
            << ",\"qualification_rectangular_events_per_block\":"
            << rectangular_geometry.events_per_block
            << ",\"qualification_rectangular_multiblock_prime_count\":"
            << rectangular_geometry.grid_y
            << ",\"qualification_rectangular_grid_x\":"
            << rectangular_geometry.grid_x
            << ",\"qualification_rectangular_grid_y\":"
            << rectangular_geometry.grid_y
            << ",\"qualification_rectangular_grid_z\":"
            << rectangular_geometry.grid_z
            << ",\"qualification_rectangular_threads_per_block\":"
            << rectangular_geometry.threads_per_block
            << ",\"qualification_rectangular_enclosing_super_shard_lower\":"
            << rectangular_geometry.enclosing_lower
            << ",\"qualification_rectangular_enclosing_super_shard_count\":"
            << rectangular_geometry.enclosing_count;
      }
      std::cout
          << ",\"lower\":" << leaf_lower
          << ",\"upper_exclusive\":" << leaf_upper_exclusive
          << ",\"count\":" << leaf_count
          << ",\"previous_leaf_sha256\":\"" << previous_leaf
          << "\",\"leaf_sha256\":\"" << leaf_digest
          << "\",\"qualification_mu_plus_one_sha256\":";
      if (leaf_mu_sha256.empty()) {
        std::cout << "null";
      } else {
        std::cout << '"' << leaf_mu_sha256 << '"';
      }
      std::cout
          << ",\"incoming_mertens\":" << incoming_mertens
          << ",\"outgoing_mertens\":" << current_mertens
          << ",\"delta_mertens\":" << summary.delta.mertens
          << ",\"incoming_squarefree\":" << incoming_squarefree
          << ",\"outgoing_squarefree\":" << current_squarefree
          << ",\"delta_squarefree\":" << summary.delta.squarefree
          << ",\"hurst_lower\":{\"value\":"
          << summary.hurst_lower.value << ",\"witness_y\":"
          << summary.hurst_lower.witness_y << "},"
          << "\"hurst_upper\":{\"value\":"
          << summary.hurst_upper.value << ",\"witness_y\":"
          << summary.hurst_upper.witness_y << "},"
          << "\"squarefree_lower\":{\"value\":"
          << summary.squarefree_lower.value << ",\"witness_y\":"
          << summary.squarefree_lower.witness_y << ",\"side\":\""
          << ((summary.squarefree_lower.order & 1U) == 0
                  ? "integer"
                  : "right_limit")
          << "\"},\"squarefree_upper\":{\"value\":"
          << summary.squarefree_upper.value << ",\"witness_y\":"
          << summary.squarefree_upper.witness_y << ",\"side\":\""
          << ((summary.squarefree_upper.order & 1U) == 0
                  ? "integer"
                  : "right_limit")
          << "\"},\"source_prime_fast_path\":"
          << (source_fast_path ? "true" : "false")
          << ",\"selected_prime_count\":" << selected_prime_count
          << ",\"dense_prime_count\":" << dense_prime_count
          << ",\"super_shard_index\":" << super_shard_index
          << ",\"super_shard_leaf_index\":"
          << super_leaf_index
          << ",\"super_shard_lower\":" << super_lower
          << ",\"super_shard_upper_exclusive\":"
          << super_upper_exclusive
          << ",\"super_shard_count\":" << super_count
          << ",\"active_prime_filter_milliseconds\":\""
          << active_filter_milliseconds
          << "\",\"active_prime_upload_milliseconds\":\""
          << active_upload_milliseconds
          << "\",\"kernel_milliseconds\":\""
          << amortized_kernel_milliseconds
          << "\",\"super_shard_sieve_kernel_milliseconds\":\""
          << kernel_milliseconds
          << "\",\"affine_milliseconds\":\""
          << affine_milliseconds
          << "\",\"transfer_milliseconds\":\""
          << transfer_milliseconds
          << "\",\"control_loop_milliseconds\":\""
          << control_loop_milliseconds
          << "\",\"affine_candidate_bytes_transferred\":"
          << sizeof(candidate)
          << ",\"poison_count\":0"
          << ",\"production_device_to_host_bytes\":76"
          << ",\"qualification_device_to_host_mu_bytes\":"
          << (options.qualification_write_mu.empty()
                  ? 0
                  : leaf_count)
          << ",\"mu_row_commitment_present\":"
          << (leaf_mu_sha256.empty() ? "false" : "true")
          << ",\"source_rows_replayed_independently\":false,"
          << "\"execution_attested\":false,"
          << "\"cuda_or_cpp_compiler_refinement_proved\":false,"
          << "\"lean_atom_discharged\":false,"
          << "\"proves_any_external_atom\":false}\n";
      std::cout.flush();

      previous_leaf = leaf_digest;
      relative_mertens += summary.delta.mertens;
      relative_squarefree += summary.delta.squarefree;
      processed += leaf_count;
      super_processed += leaf_count;
      ++leaf_index;
      ++super_leaf_index;
    }

    const auto super_wall_stop = std::chrono::steady_clock::now();
    const double super_wall_milliseconds =
        std::chrono::duration<double, std::milli>(
            super_wall_stop - super_wall_start).count();
    total_control_loop_milliseconds +=
        std::max(
            0.0, super_wall_milliseconds -
                static_cast<double>(kernel_milliseconds) -
                super_affine_milliseconds);
    ++super_shard_index;
  }

  if (qualification_mu.is_open()) qualification_mu.close();
  const auto process_stop = std::chrono::steady_clock::now();
  const double process_milliseconds =
      std::chrono::duration<double, std::milli>(
          process_stop - process_start).count();

  std::cout
      << "{\"record\":\"terminal\",\"algorithm\":\""
      << persistent_algorithm << "\",\"classification\":\""
      << persistent_classification << "\"";
  if (qualification_only) {
    std::cout
        << ",\"receipt_leaf_domain\":\""
        << persistent_leaf_domain
        << "\",\"qualification_only_not_production_admissible\":true";
  }
  std::cout << ",\"lower\":" << options.lower << ",\"upper_exclusive\":"
      << upper_exclusive << ",\"count\":" << options.count
      << ",\"leaf_count\":" << leaf_index
      << ",\"final_leaf_sha256\":\"" << previous_leaf
      << "\",\"production_mu_row_commitment_present\":false"
      << ",\"incoming_mertens\":"
      << options.incoming_mertens << ",\"outgoing_mertens\":"
      << current_mertens << ",\"delta_mertens\":"
      << relative_mertens << ",\"incoming_squarefree\":"
      << options.incoming_squarefree << ",\"outgoing_squarefree\":"
      << current_squarefree << ",\"delta_squarefree\":"
      << relative_squarefree << ",\"global_hurst_lower\":";
  print_bound_json(global_hurst_lower, false);
  std::cout << ",\"global_hurst_upper\":";
  print_bound_json(global_hurst_upper, false);
  std::cout << ",\"global_squarefree_lower\":";
  print_bound_json(global_squarefree_lower, true);
  std::cout << ",\"global_squarefree_upper\":";
  print_bound_json(global_squarefree_upper, true);
  std::cout
      << ",\"source_fast_path_leaf_count\":"
      << source_fast_path_leaf_count
      << ",\"source_fast_path_super_shard_count\":"
      << source_fast_path_super_shard_count
      << ",\"super_shard_count\":" << super_shard_index
      << ",\"sieve_launch_count\":" << sieve_launch_count
      << ",\"receipt_leaf_count\":" << leaf_index
      << ",\"sieve_launches_saved_vs_leaf_schedule\":"
      << leaf_index - sieve_launch_count
      << ",\"super_shard_rows\":" << options.super_shard_rows
      << ",\"active_filter_milliseconds\":\""
      << total_active_filter_milliseconds
      << "\",\"active_prime_upload_milliseconds\":\""
      << total_active_upload_milliseconds
      << "\",\"kernel_milliseconds\":\""
      << total_kernel_milliseconds
      << "\",\"affine_milliseconds\":\""
      << total_affine_milliseconds
      << "\",\"transfer_milliseconds\":\""
      << total_transfer_milliseconds
      << "\",\"control_loop_milliseconds\":\""
      << total_control_loop_milliseconds
      << "\",\"roster_load_count\":1,\"roster_upload_count\":1,"
      << "\"allocation_epoch_count\":1,\"event_set_count\":1,"
      << "\"buffers_reused_across_all_leaves\":true,"
      << "\"affine_candidates_transferred_per_leaf\":1,"
      << "\"affine_candidate_bytes_per_leaf\":"
      << sizeof(TgMobiusAffineMqThreadCandidates)
      << ",\"production_device_to_host_bytes_per_leaf\":76"
      << ",\"production_mu_rows_transferred\":false"
      << ",\"production_mu_rows_hashed\":false"
      << ",\"leaf_chain_binds_compact_gpu_summary\":true"
      << ",\"host_rechecks_final_squarefree_winners\":true"
      << ",\"checkpoint_restart_fields_emitted_per_leaf\":true,"
      << "\"little_mertens_lower_delta\":0,"
      << "\"little_mertens_upper_delta\":0,"
      << "\"source_rows_replayed_independently\":false,"
      << "\"full_source_range\":false,"
      << "\"execution_attested\":false,"
      << "\"cuda_or_cpp_compiler_refinement_proved\":false,"
      << "\"primitive_mobius_realization_proved\":false,"
      << "\"lean_atom_discharged\":false,"
      << "\"proves_any_external_atom\":false,"
      << "\"process_milliseconds\":\"" << process_milliseconds
      << "\"}\n";

  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda(
      "cudaEventDestroy(segment stop)", cudaEventDestroy(segment_stop));
  check_cuda(
      "cudaEventDestroy(affine start)", cudaEventDestroy(affine_start));
  check_cuda(
      "cudaEventDestroy(affine stop)", cudaEventDestroy(affine_stop));
  if (device_affine_workspace != nullptr) {
    check_cuda(
        "cudaFree(persistent affine workspace)",
        cudaFree(device_affine_workspace));
  }
  check_cuda(
      "cudaFree(persistent poison count)",
      cudaFree(device_poison_count));
  if (device_block_summaries != nullptr) {
    check_cuda(
        "cudaFree(persistent affine block summaries)",
        cudaFree(device_block_summaries));
  }
  check_cuda(
      "cudaFree(persistent candidate)", cudaFree(device_candidate));
  check_cuda(
      "cudaFree(persistent prefixes)", cudaFree(device_prefixes));
  if (device_mobius != nullptr) {
    check_cuda(
        "cudaFree(persistent mobius)", cudaFree(device_mobius));
  }
  check_cuda(
      "cudaFree(persistent supports)", cudaFree(device_supports));
  check_cuda(
      "cudaFree(persistent active primes)",
      cudaFree(device_active_primes));
  check_cuda(
      "cudaFree(persistent roster)", cudaFree(device_roster));
  return 0;
}
