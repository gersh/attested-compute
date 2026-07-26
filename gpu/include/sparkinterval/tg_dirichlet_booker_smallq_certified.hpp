// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstdint>

namespace sparkinterval::tg::dirichlet_booker_smallq_certified {

// Version 2 is deliberately distinct from the binary64-midpoint proposal in
// tg_dirichlet_booker_smallq.hpp.  A Disk encloses a complex number z by
//
//                 |z - (real + i imaginary)| <= radius.
//
// All three fields are binary64 values.  The radius is an outward-rounded
// upper bound.  The CUDA implementation uses only CUDA's directed basic
// arithmetic intrinsics and __dsqrt_ru; it never calls a device
// transcendental.  Seed disks and analytic remainders therefore have to be
// constructed and independently checked with MPFR/Arb.
inline constexpr std::uint32_t kFormatVersion = 2;
inline constexpr std::uint32_t kFactoredFormatVersion = 3;
inline constexpr std::uint32_t kMaximumModulus = 10000;
inline constexpr std::uint32_t kNonUnitExponent = 0xffffffffU;
inline constexpr std::uint64_t kMaximumTransformLength = 1ULL << 29U;

inline constexpr char kInputMagic[8] = {'T', 'G', 'D', 'B', 'S', 'C', 'I', '2'};
inline constexpr char kOutputMagic[8] = {'T', 'G', 'D', 'B', 'S', 'C', 'O', '2'};
inline constexpr char kFactoredInputMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'C', 'I', '3'};
inline constexpr char kFactoredOutputMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'C', 'O', '3'};
// The split v3 service keeps the character-independent frequency stream in a
// q-level plan and sends only character data in bounded batches.  A batch is
// never accepted outside the service: it commits to the SHA-256 digest of the
// complete plan and the service preflights the ordered character roster before
// launching or publishing any work.
inline constexpr char kFactoredPlanMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'Q', 'P', '3'};
inline constexpr char kFactoredBatchMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'Q', 'B', '3'};
inline constexpr char kFactoredServiceOutputMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'Q', 'O', '3'};
// Source-sample-only service output.  The DFT still consumes and computes the
// complete transform; only indices 0..sample_count-1, the source 5/64 lattice,
// cross the output boundary.  The exact source parameter check is mandatory
// before this distinct magic may be emitted.
inline constexpr char kFactoredReducedServiceOutputMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'Q', 'R', '3'};
// Production-only runner-side strict-sign transport.  Unlike TGDBSQR3 this
// publishes four two-bit sign decisions per byte, never complex disks.  The
// Python compact-v3 consumer validates every binding and leaves source
// admission false: this transport does not itself establish DFT containment.
inline constexpr char kPackedSignFrameMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'P', 'K', '1'};
inline constexpr char kPackedSignTrailerMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'P', 'T', '1'};
inline constexpr char kPackedSignEndMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'P', 'E', '1'};
inline constexpr std::uint32_t kPackedSignFormatVersion = 1U;
// The packing location is part of the frame identity.  Mode 1 is the
// historical host classifier, mode 2 is reserved for the bounded structural
// KAT emitted by the Python oracle, and mode 3 is the production device
// classifier.  A consumer must pin one of the two production locations; it
// must not silently treat their frames as interchangeable.
inline constexpr std::uint32_t kPackedSignHostProductionMode = 1U;
inline constexpr std::uint32_t kPackedSignStructuralKatMode = 2U;
inline constexpr std::uint32_t kPackedSignDeviceProductionMode = 3U;
inline constexpr std::uint32_t kPackedSignProductionMode =
    kPackedSignHostProductionMode;
inline constexpr std::uint32_t kPackedSignBitsPerCode = 2U;
inline constexpr std::uint32_t kPackedSignAmbiguous = 0U;
inline constexpr std::uint32_t kPackedSignNegative = 1U;
inline constexpr std::uint32_t kPackedSignPositive = 2U;

// Higher-precision-replayed time-tail control consumed by the strict-sign
// packer.  The runner validates this wire header and exact file SHA-256; the
// compact-v3 host independently validates its semantic replay receipt.
inline constexpr char kTimeTailControlMagic[8] =
    {'T', 'G', 'D', 'B', 'S', 'Q', 'T', '1'};
inline constexpr std::uint32_t kTimeTailControlVersion = 1U;

struct Disk {
  double real;
  double imaginary;
  double radius;
};

// One InputHeader is followed by one ParameterHeader and batch_count character
// blocks described below.  The frequency records must form the complete
// natural order 0,...,N-1 when run_dft is nonzero.
struct InputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t group_exponent;
  std::uint32_t batch_count;
  std::uint64_t transform_length;
  std::uint64_t frequency_start;
  std::uint64_t frequency_count;
  std::uint32_t run_dft;
  std::uint32_t target_bits;
  std::uint64_t reserved1;
};

// A split plan begins with InputHeader (where batch_count is the total number
// of characters in the campaign), followed by this commitment, the exact
// ParameterHeader, and frequency_count SharedFrequencySeed records.
struct FactoredPlanCommitment {
  unsigned char character_roster_sha256[32];
};

// A split batch begins with InputHeader (where batch_count is the number in
// this file), followed by this binding and its character blocks.  The exact
// parameters and frequency seeds are inherited only through plan_sha256.
struct FactoredBatchBinding {
  unsigned char plan_sha256[32];
  std::uint64_t character_start;
  std::uint64_t campaign_character_count;
  std::uint64_t batch_ordinal;
  std::uint64_t campaign_batch_count;
};

// Service outputs bind both complete input artifacts immediately after the
// normal OutputHeader.  Thus a valid disk stream cannot be relabelled as the
// output of a different plan, batch payload, or contiguous character slice.
struct FactoredServiceOutputBinding {
  unsigned char plan_sha256[32];
  unsigned char batch_sha256[32];
  std::uint64_t character_start;
  std::uint64_t campaign_character_count;
  std::uint64_t batch_ordinal;
  std::uint64_t campaign_batch_count;
};

// Exact transform parameters are part of the certificate identity.  The CUDA
// recurrence itself consumes their derived seed disks, while the independent
// checker requires these reduced rationals to prevent seed relabelling.
struct ParameterHeader {
  std::int64_t eta_numerator;
  std::uint64_t eta_denominator;
  std::uint64_t a_numerator;
  std::uint64_t a_denominator;
  std::uint64_t b_numerator;
  std::uint64_t b_denominator;
};

// Every batch member has one CharacterHeader, q exact exponent words, and
// frequency_count FrequencySeed records.  Keeping many characters in one
// frame lets a single resident FFT plan and one set of MPFR-certified
// twiddles serve a production batch.
struct CharacterHeader {
  std::uint64_t character_id;
  std::uint32_t parity;
  std::uint32_t reserved0;
  std::uint64_t reserved1;
};

// Version 3 stores one independently certified epsilon disk per character.
// The parity-only prefactor lives in the shared frequency stream below.
struct FactoredCharacterHeader {
  std::uint64_t character_id;
  std::uint32_t parity;
  std::uint32_t reserved0;
  std::uint64_t reserved1;
  Disk epsilon;
};

// w encloses exp(-alpha + i beta), so w^(n*n) is the Gaussian factor.
// prefactor encloses the complete epsilon/tilt/q factor for this frequency.
// analytic_radius_hi is a certified upper bound for the omitted Gaussian
// terms plus both frequency-periodization wings after applying prefactor.
struct FrequencySeed {
  std::uint64_t index;
  std::int64_t signed_index;
  std::uint32_t truncation;
  std::uint32_t reserved0;
  Disk w;
  Disk prefactor;
  double analytic_radius_hi;
  std::uint64_t reserved1;
};

struct ParitySeed {
  std::uint32_t truncation;
  std::uint32_t reserved0;
  Disk prefactor;
  double analytic_radius_hi;
};

// One version-3 record is shared by every character in the frame.  The CUDA
// kernel selects a parity record and composes its prefactor with the
// character's epsilon disk using the same directed disk multiplication used
// by the finite Gaussian recurrence.
struct SharedFrequencySeed {
  std::uint64_t index;
  std::int64_t signed_index;
  Disk w;
  ParitySeed even;
  ParitySeed odd;
};

// For TGDBSQO3, frequency_count is the complete transform length.  For the
// distinct TGDBSQR3 magic it is the canonical source sample count; the
// butterfly counter still describes the complete transform that was run.
struct OutputHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t batch_count;
  std::uint32_t run_dft;
  std::uint64_t frequency_start;
  std::uint64_t frequency_count;
  std::uint64_t finite_gaussian_terms;
  std::uint64_t radix2_butterflies;
  std::uint64_t elapsed_nanoseconds;
  std::uint32_t status_or;
  std::uint32_t reserved0;
};

struct OutputItem {
  std::uint64_t character_id;
  std::uint64_t index;
  Disk value;
  std::uint32_t status;
  std::uint32_t reserved0;
};

struct TimeTailControlHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t even_character_count;
  std::uint32_t odd_character_count;
  std::uint64_t transform_length;
  std::uint64_t sample_count;
  std::uint32_t precision_bits;
  std::uint32_t reserved0;
  unsigned char plan_sha256[32];
  unsigned char batch_partition_sha256[32];
};

struct TimeTailControlItem {
  double even;
  double odd;
};

struct PackedSignFramePrefix {
  char magic[8];
  std::uint32_t version;
  std::uint32_t mode;
  std::uint32_t q;
  std::uint32_t bits_per_code;
  std::uint64_t batch_character_count;
  std::uint64_t frequency_start;
  std::uint64_t frequency_count;
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
  std::uint64_t payload_bytes;
  std::uint64_t finite_gaussian_terms;
  std::uint64_t radix2_butterflies;
  std::uint64_t elapsed_nanoseconds;
  std::uint32_t status_or;
  std::uint32_t reserved0;
};

struct PackedSignBatchBinding {
  std::uint64_t character_start;
  std::uint64_t campaign_character_count;
  std::uint64_t batch_ordinal;
  std::uint64_t campaign_batch_count;
};

struct PackedSignDigestBindings {
  unsigned char plan_sha256[32];
  unsigned char batch_sha256[32];
  unsigned char control_sha256[32];
  unsigned char control_receipt_sha256[32];
  unsigned char batch_partition_sha256[32];
  unsigned char plan_roster_sha256[32];
  unsigned char compact_roster_sha256[32];
  unsigned char pinset_sha256[32];
  unsigned char source_binding_sha256[32];
  unsigned char previous_frame_sha256[32];
};

struct PackedSignFrameTrailer {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved0;
  std::uint64_t frame_ordinal;
  std::uint64_t payload_bytes;
  unsigned char payload_sha256[32];
  unsigned char frame_sha256[32];
};

struct PackedSignStreamEnd {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved0;
  std::uint64_t frame_count;
  std::uint64_t item_count;
  unsigned char last_frame_sha256[32];
  unsigned char body_sha256[32];
};

enum Status : std::uint32_t {
  kSuccess = 0,
  kMalformedSeed = 1U << 0U,
  kNonFiniteArithmetic = 1U << 1U,
  kRadiusOverflow = 1U << 2U,
};

static_assert(sizeof(Disk) == 24);
static_assert(sizeof(InputHeader) == 64);
static_assert(sizeof(FactoredPlanCommitment) == 32);
static_assert(sizeof(FactoredBatchBinding) == 64);
static_assert(sizeof(FactoredServiceOutputBinding) == 96);
static_assert(sizeof(ParameterHeader) == 48);
static_assert(sizeof(CharacterHeader) == 24);
static_assert(sizeof(FactoredCharacterHeader) == 48);
static_assert(sizeof(FrequencySeed) == 88);
static_assert(sizeof(ParitySeed) == 40);
static_assert(sizeof(SharedFrequencySeed) == 120);
static_assert(sizeof(OutputHeader) == 72);
static_assert(sizeof(OutputItem) == 48);
static_assert(sizeof(TimeTailControlHeader) == 112);
static_assert(sizeof(TimeTailControlItem) == 16);
static_assert(
    sizeof(TimeTailControlHeader) % alignof(TimeTailControlItem) == 0,
    "TGDBSQT1 control items must begin at their natural alignment");
static_assert(sizeof(PackedSignFramePrefix) == 104);
static_assert(sizeof(PackedSignBatchBinding) == 32);
static_assert(sizeof(PackedSignDigestBindings) == 320);
static_assert(sizeof(PackedSignFrameTrailer) == 96);
static_assert(sizeof(PackedSignStreamEnd) == 96);

}  // namespace sparkinterval::tg::dirichlet_booker_smallq_certified
