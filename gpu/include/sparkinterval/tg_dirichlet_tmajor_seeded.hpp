// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::dirichlet_tmajor_seeded {

// One immutable block contains at most 64 authenticated Hurwitz-lattice rows
// followed by one factor/tail sidecar for every active modulus.  CRT residue
// descriptors are deliberately absent: the CUDA process reconstructs them
// from q.  The row payload is uploaded once and remains resident while every
// target in the block is evaluated.
// Version 2 uses the exact nonempty primitive-character modulus roster:
// q is present iff q % 4 != 2.  Version 1 included empty-roster moduli and is
// deliberately rejected rather than silently reinterpreted.
inline constexpr std::uint32_t kFormatVersion = 2;
inline constexpr std::uint32_t kMaximumRows = 64;
inline constexpr std::uint32_t kQMajorManifestSidecars = 0;
inline constexpr std::uint32_t kDirectMpfrSidecars = 1;
inline constexpr char kBlockMagic[8] = {
    'T', 'G', 'D', 'L', 'T', 'M', 'B', '1'};
inline constexpr char kRowMagic[8] = {
    'T', 'G', 'D', 'L', 'T', 'M', 'R', '1'};
inline constexpr char kTargetMagic[8] = {
    'T', 'G', 'D', 'L', 'T', 'M', 'Q', '1'};
inline constexpr char kFooterMagic[8] = {
    'T', 'G', 'D', 'L', 'T', 'M', 'F', '1'};

// Header fields are intentionally fixed-width and little-endian.  The six
// digests bind the source contract, spool receipt, exact block-row roster,
// recovery seed artifact/replay, and the sidecar source (either an externally
// pinned q-major manifest or the independently replayed direct-MPFR recipe).
struct BlockHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t lane_index;
  std::uint32_t row_count;
  std::uint32_t target_count;
  std::uint32_t q_start;
  std::uint32_t q_stop;
  std::uint32_t m;
  std::uint32_t sidecar_mode;
  std::uint64_t first_t_index;
  std::uint64_t t_index_stop_exclusive;
  std::uint64_t row_payload_bytes;
  std::uint64_t row_record_bytes;
  std::uint64_t target_header_bytes;
  unsigned char source_contract_sha256[32];
  unsigned char spool_receipt_sha256[32];
  unsigned char row_bindings_sha256[32];
  unsigned char seed_artifact_sha256[32];
  unsigned char seed_replay_sha256[32];
  unsigned char sidecar_source_sha256[32];
};

struct RowHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t t_index;
  std::uint64_t payload_bytes;
  unsigned char payload_sha256[32];
};

// The digest is domain-separated SHA-256 over the target identity followed by
// the raw factor and tail bytes.  There is no descriptor payload.
struct TargetHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t component_count;
  std::uint32_t batch_count;
  std::uint32_t reserved0;
  std::uint32_t reserved1;
  std::uint64_t group_order;
  std::int64_t first_t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  std::uint64_t value_count;
  std::uint64_t factor_bytes;
  std::uint64_t tail_bytes;
  unsigned char sidecar_sha256[32];
};

struct BlockFooter {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t row_count;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t sidecar_bytes;
  std::uint64_t source_input_bytes;
  unsigned char row_stream_sha256[32];
  unsigned char target_stream_sha256[32];
  unsigned char source_input_chain_sha256[32];
};

static_assert(sizeof(BlockHeader) == 272);
static_assert(sizeof(RowHeader) == 64);
static_assert(sizeof(TargetHeader) == 120);
static_assert(sizeof(BlockFooter) == 160);

}  // namespace sparkinterval::tg::dirichlet_tmajor_seeded
