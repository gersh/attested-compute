// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"
#include "sparkinterval/tg_mobius_affine_candidate_order.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

[[noreturn]] void fail(const char* message) {
  std::cerr << message << '\n';
  std::exit(1);
}

void check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    std::cerr << operation << ": " << cudaGetErrorString(status) << '\n';
    std::exit(1);
  }
}

bool same(const TgMobiusAffineMqBoundCandidate& left,
          const TgMobiusAffineMqBoundCandidate& right) {
  return left.value == right.value &&
         left.local_squarefree == right.local_squarefree &&
         left.order == right.order;
}

bool same(const TgMobiusAffineMqThreadCandidates& left,
          const TgMobiusAffineMqThreadCandidates& right) {
  return same(left.hurst_lower, right.hurst_lower) &&
         same(left.hurst_upper, right.hurst_upper) &&
         same(left.squarefree_lower, right.squarefree_lower) &&
         same(left.squarefree_upper, right.squarefree_upper);
}

TgMobiusAffineMqBoundCandidate translate_candidate(
    TgMobiusAffineMqBoundCandidate candidate,
    std::int64_t value_shift, std::uint32_t squarefree_shift,
    bool carries_squarefree_prefix) {
  if (candidate.order == std::numeric_limits<std::uint32_t>::max()) {
    return candidate;
  }
  candidate.value += value_shift;
  if (carries_squarefree_prefix) {
    candidate.local_squarefree += squarefree_shift;
  }
  return candidate;
}

TgMobiusAffineMqBlockSummary compose_summaries(
    const TgMobiusAffineMqBlockSummary& left,
    const TgMobiusAffineMqBlockSummary& right) {
  TgMobiusAffineMqThreadCandidates translated = right.candidates;
  translated.hurst_lower = translate_candidate(
      translated.hurst_lower, -left.delta.mertens, 0, false);
  translated.hurst_upper = translate_candidate(
      translated.hurst_upper, -left.delta.mertens, 0, false);
  translated.squarefree_lower = translate_candidate(
      translated.squarefree_lower,
      -static_cast<std::int64_t>(left.delta.squarefree),
      left.delta.squarefree, true);
  translated.squarefree_upper = translate_candidate(
      translated.squarefree_upper,
      -static_cast<std::int64_t>(left.delta.squarefree),
      left.delta.squarefree, true);
  return {
      {static_cast<std::int32_t>(
           static_cast<std::int64_t>(left.delta.mertens) +
           right.delta.mertens),
       static_cast<std::uint32_t>(
           static_cast<std::uint64_t>(left.delta.squarefree) +
           right.delta.squarefree)},
      sparkinterval::tg::detail::combine_affine_candidates(
          left.candidates, translated)};
}

void run_summary_compose_case(
    std::size_t summary_count, std::size_t rows_per_block) {
  std::vector<TgMobiusAffineMqBlockSummary> host_summaries(
      summary_count);
  for (std::size_t index = 0; index < summary_count; ++index) {
    const std::int32_t mertens =
        static_cast<std::int32_t>(index % 7) - 3;
    const std::uint32_t squarefree =
        static_cast<std::uint32_t>(41 + index % 23);
    const std::uint32_t base_order =
        static_cast<std::uint32_t>(
            2 * rows_per_block * index);
    const std::int64_t wave =
        static_cast<std::int64_t>(index % 11) - 5;
    host_summaries[index] = {
        {mertens, squarefree},
        {{101 + wave, 0, base_order + 2},
         {211 - wave, 0, base_order + 4},
         {307 + wave, squarefree / 2, base_order + 1},
         {401 - wave, squarefree / 3, base_order + 3}}};
  }
  TgMobiusAffineMqBlockSummary expected{
      {0, 0}, sparkinterval::tg::detail::empty_affine_candidates()};
  for (const auto& summary : host_summaries) {
    expected = compose_summaries(expected, summary);
  }

  TgMobiusAffineMqBlockSummary* device_summaries = nullptr;
  TgMobiusPrefixMQ* device_delta = nullptr;
  TgMobiusAffineMqThreadCandidates* device_candidate = nullptr;
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_summaries),
            summary_count * sizeof(TgMobiusAffineMqBlockSummary)),
        "cudaMalloc(synthetic summaries)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_delta),
            sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(synthetic delta)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(synthetic candidate)");
  check(cudaMemcpy(
            device_summaries, host_summaries.data(),
            summary_count * sizeof(TgMobiusAffineMqBlockSummary),
            cudaMemcpyHostToDevice),
        "cudaMemcpy(synthetic summaries)");
  check(
      launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
          device_summaries, summary_count, device_delta,
          device_candidate),
      "synthetic summary compose launch");
  TgMobiusPrefixMQ actual_delta{};
  TgMobiusAffineMqThreadCandidates actual_candidate{};
  check(cudaMemcpy(
            &actual_delta, device_delta, sizeof(actual_delta),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(synthetic delta)");
  check(cudaMemcpy(
            &actual_candidate, device_candidate,
            sizeof(actual_candidate), cudaMemcpyDeviceToHost),
        "cudaMemcpy(synthetic candidate)");
  if (actual_delta.mertens != expected.delta.mertens ||
      actual_delta.squarefree != expected.delta.squarefree ||
      !same(actual_candidate, expected.candidates)) {
    std::cerr << "ordered summary compose mismatch at summary_count="
              << summary_count << '\n';
    std::exit(1);
  }
  check(cudaFree(device_candidate), "cudaFree(synthetic candidate)");
  check(cudaFree(device_delta), "cudaFree(synthetic delta)");
  check(cudaFree(device_summaries), "cudaFree(synthetic summaries)");
}

void run_cross_tile_equal_value_tie_case(
    std::size_t rows_per_block) {
  constexpr TgMobiusAffineMqThreadCandidates first_candidates{
      {101, 0, 2},
      {211, 0, 4},
      {307, 19, 1},
      {401, 17, 3}};
  // The preceding delta is deliberately nonzero in both coordinates.
  // Composition translates the later Hurst values by -(-3)=+3 and the
  // later squarefree values by -41, making all four values exactly equal
  // to the earlier tile.  The earlier absolute order must therefore win.
  const std::uint32_t second_tile_order =
      static_cast<std::uint32_t>(2 * rows_per_block);
  const std::array<TgMobiusAffineMqBlockSummary, 2> summaries{{
      {{-3, 41}, first_candidates},
      {{2, 37},
       {{98, 0, second_tile_order + 2},
        {208, 0, second_tile_order + 4},
        {348, 23, second_tile_order + 1},
        {442, 21, second_tile_order + 3}}}
  }};
  TgMobiusAffineMqBlockSummary* device_summaries = nullptr;
  TgMobiusPrefixMQ* device_delta = nullptr;
  TgMobiusAffineMqThreadCandidates* device_candidate = nullptr;
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_summaries),
            sizeof(summaries)),
        "cudaMalloc(equal-tie summaries)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_delta),
            sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(equal-tie delta)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(equal-tie candidate)");
  check(cudaMemcpy(
            device_summaries, summaries.data(), sizeof(summaries),
            cudaMemcpyHostToDevice),
        "cudaMemcpy(equal-tie summaries)");
  check(
      launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
          device_summaries, summaries.size(), device_delta,
          device_candidate),
      "equal-tie summary compose launch");
  TgMobiusAffineMqThreadCandidates actual{};
  check(cudaMemcpy(
            &actual, device_candidate, sizeof(actual),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(equal-tie candidate)");
  if (!same(actual, first_candidates)) {
    fail("cross-tile equal-value tie did not retain earliest order");
  }
  check(cudaFree(device_candidate), "cudaFree(equal-tie candidate)");
  check(cudaFree(device_delta), "cudaFree(equal-tie delta)");
  check(cudaFree(device_summaries), "cudaFree(equal-tie summaries)");
}

std::int8_t pattern_value(std::size_t index, unsigned int pattern) {
  if (pattern == 0) return 1;
  if (pattern == 3) return -1;
  if (pattern == 4) return 2;
  if (pattern == 1) {
    if (index % 257 == 0) return 0;
    return (index & 1U) == 0 ? -1 : 1;
  }
  if ((index + 1) % 256 == 0 || index % 65'537 == 0) return 0;
  return ((index / 255) & 1U) == 0 ? 1 : -1;
}

std::vector<std::uint32_t> primes_through(std::uint64_t limit) {
  std::vector<std::uint32_t> primes;
  for (std::uint64_t candidate = 2; candidate <= limit; ++candidate) {
    bool prime = true;
    for (const std::uint32_t divisor : primes) {
      if (static_cast<std::uint64_t>(divisor) * divisor > candidate) break;
      if (candidate % divisor == 0) {
        prime = false;
        break;
      }
    }
    if (prime) primes.push_back(static_cast<std::uint32_t>(candidate));
  }
  return primes;
}

void make_producer_shaped_supports(
    std::uint64_t lower, std::size_t count,
    std::vector<std::int8_t>* mobius,
    std::vector<TgMobiusFusedSupport>* supports) {
  std::uint64_t root = 0;
  const std::uint64_t upper = lower + count - 1;
  while ((root + 1) * (root + 1) <= upper) ++root;
  const std::vector<std::uint32_t> primes = primes_through(root);
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = lower + index;
    std::uint64_t product = 1;
    std::uint32_t distinct_count = 0;
    bool squareful = false;
    for (const std::uint32_t prime : primes) {
      if (number % prime != 0) continue;
      product *= prime;
      ++distinct_count;
      if ((number / prime) % prime == 0) squareful = true;
    }
    const std::uint64_t residual = number / product;
    const std::uint32_t omega =
        distinct_count + static_cast<std::uint32_t>(residual > 1);
    (*mobius)[index] = squareful
        ? 0
        : static_cast<std::int8_t>((omega & 1U) == 0 ? 1 : -1);
    (*supports)[index].packed =
        product |
        (static_cast<std::uint64_t>(distinct_count)
         << kTgMobiusFusedCountShift) |
        (squareful ? kTgMobiusFusedSquarefulBit : 0);
  }
}

void run_case(
    std::size_t count, unsigned int pattern,
    const std::vector<std::size_t>& forced_poison_indices = {}) {
  std::vector<std::int8_t> host_mobius(count);
  std::vector<TgMobiusFusedSupport> host_supports(count);
  const std::uint64_t lower =
      pattern == 5 ? 500'000 : kTgMobiusSourceLimit - count + 1;
  if (pattern == 5) {
    make_producer_shaped_supports(
        lower, count, &host_mobius, &host_supports);
  } else {
    for (std::size_t index = 0; index < count; ++index) {
      host_mobius[index] = pattern_value(index, pattern);
      if (host_mobius[index] == 0) {
        host_supports[index].packed =
            1 | kTgMobiusFusedSquarefulBit;
      } else if (host_mobius[index] == 1) {
        host_supports[index].packed = lower + index;
      } else if (host_mobius[index] == -1) {
        host_supports[index].packed =
            (lower + index) |
            (std::uint64_t{1} << kTgMobiusFusedCountShift);
      } else {
        host_supports[index].packed =
            1 | kTgMobiusFusedPoisonBit;
      }
    }
  }
  std::vector<bool> forced_poison(count, false);
  for (const std::size_t index : forced_poison_indices) {
    if (index >= count) fail("forced poison index is outside the test row");
    forced_poison[index] = true;
  }
  std::uint32_t expected_poison = pattern == 4
      ? static_cast<std::uint32_t>(count) : 0;
  for (std::size_t index = 0; index < count; ++index) {
    if (!forced_poison[index] || host_mobius[index] == 2) continue;
    host_mobius[index] = 2;
    host_supports[index].packed =
        1 | kTgMobiusFusedPoisonBit;
    ++expected_poison;
  }
  std::size_t workspace_bytes = 0;
  check(tg_mobius_affine_mq_reduced_workspace_size(
            count, &workspace_bytes),
        "reduced affine workspace query");
  const std::size_t candidate_count =
      tg_mobius_affine_mq_candidate_count(count);
  const std::size_t reduced_candidate_count =
      tg_mobius_affine_mq_reduced_candidate_count(count);
  const std::size_t block_summary_count =
      tg_mobius_affine_mq_block_summary_count(count);
  if (workspace_bytes == 0 || candidate_count == 0 ||
      reduced_candidate_count != 1 || block_summary_count == 0) {
    fail("affine workspace or candidate count is zero");
  }

  std::int8_t* device_mobius = nullptr;
  TgMobiusFusedSupport* device_supports = nullptr;
  TgMobiusPrefixMQ* device_prefixes = nullptr;
  TgMobiusPrefixMQ* device_block_delta = nullptr;
  TgMobiusAffineMqThreadCandidates* device_candidates = nullptr;
  TgMobiusAffineMqThreadCandidates* device_reduced_candidate = nullptr;
  TgMobiusAffineMqThreadCandidates* device_block_candidate = nullptr;
  TgMobiusAffineMqBlockSummary* device_block_summaries = nullptr;
  std::uint32_t* device_poison_count = nullptr;
  void* device_workspace = nullptr;
  check(cudaMalloc(reinterpret_cast<void**>(&device_mobius), count),
        "cudaMalloc(mobius)");
  check(cudaMalloc(reinterpret_cast<void**>(&device_supports),
                   count * sizeof(TgMobiusFusedSupport)),
        "cudaMalloc(supports)");
  check(cudaMalloc(reinterpret_cast<void**>(&device_prefixes),
                   count * sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(prefixes)");
  check(cudaMalloc(reinterpret_cast<void**>(&device_block_delta),
                   sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(block delta)");
  check(cudaMalloc(reinterpret_cast<void**>(&device_candidates),
                   candidate_count *
                       sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(candidates)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_reduced_candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(reduced candidate)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_block_candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(block candidate)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_block_summaries),
            block_summary_count *
                sizeof(TgMobiusAffineMqBlockSummary)),
        "cudaMalloc(block summaries)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_poison_count),
            sizeof(std::uint32_t)),
        "cudaMalloc(poison count)");
  check(cudaMalloc(&device_workspace, workspace_bytes),
        "cudaMalloc(workspace)");
  check(cudaMemcpy(device_mobius, host_mobius.data(), count,
                   cudaMemcpyHostToDevice),
        "cudaMemcpy(mobius)");
  check(cudaMemcpy(
            device_supports, host_supports.data(),
            count * sizeof(TgMobiusFusedSupport),
            cudaMemcpyHostToDevice),
        "cudaMemcpy(supports)");
  check(launch_tg_mobius_affine_mq(
            lower, device_mobius, count, device_prefixes,
            device_candidates, device_workspace, workspace_bytes),
        "affine launch");
  std::vector<TgMobiusAffineMqThreadCandidates> candidates(
      candidate_count);
  check(cudaMemcpy(
            candidates.data(), device_candidates,
            candidate_count * sizeof(TgMobiusAffineMqThreadCandidates),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(candidates)");
  check(cudaMemset(
            device_poison_count, 0, sizeof(std::uint32_t)),
        "cudaMemset(poison count)");
  check(launch_tg_mobius_affine_mq_reduced(
            lower, device_mobius, count, device_prefixes,
            device_reduced_candidate, device_workspace, workspace_bytes,
            device_poison_count),
        "reduced affine launch");
  TgMobiusAffineMqThreadCandidates reduced_candidate{};
  check(cudaMemcpy(
            &reduced_candidate, device_reduced_candidate,
            sizeof(reduced_candidate), cudaMemcpyDeviceToHost),
        "cudaMemcpy(reduced candidate)");
  std::uint32_t poison_count = 0;
  check(cudaMemcpy(
            &poison_count, device_poison_count, sizeof(poison_count),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(poison count)");
  if (poison_count != expected_poison) {
    fail("affine scan poison count mismatch");
  }
  auto scalar =
      sparkinterval::tg::detail::empty_affine_candidates();
  for (const auto& item : candidates) {
    scalar = sparkinterval::tg::detail::combine_affine_candidates(
        scalar, item);
  }
  if (!same(scalar, reduced_candidate)) {
    std::cerr << "hierarchical affine candidate mismatch at count="
              << count << " pattern=" << pattern << '\n';
    std::exit(1);
  }
  std::vector<TgMobiusPrefixMQ> prefixes(count);
  check(cudaMemcpy(prefixes.data(), device_prefixes,
                   count * sizeof(TgMobiusPrefixMQ),
                   cudaMemcpyDeviceToHost),
        "cudaMemcpy(prefixes)");

  std::int64_t expected_mertens = 0;
  std::uint64_t expected_squarefree = 0;
  for (std::size_t index = 0; index < count; ++index) {
    expected_mertens += host_mobius[index];
    expected_squarefree += host_mobius[index] != 0;
    if (prefixes[index].mertens != expected_mertens ||
        prefixes[index].squarefree != expected_squarefree) {
      std::cerr << "affine prefix mismatch at count=" << count
                << " pattern=" << pattern << " index=" << index
                << '\n';
      std::exit(1);
    }
  }

  check(cudaMemset(
            device_poison_count, 0, sizeof(std::uint32_t)),
        "cudaMemset block poison count");
  check(
      launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
          lower, count, device_supports, device_block_summaries,
          block_summary_count, device_block_delta,
          device_block_candidate, device_poison_count),
      "block-compose affine launch");
  TgMobiusAffineMqThreadCandidates block_candidate{};
  TgMobiusPrefixMQ block_delta{};
  check(cudaMemcpy(
            &block_candidate, device_block_candidate,
            sizeof(block_candidate), cudaMemcpyDeviceToHost),
        "cudaMemcpy(block candidate)");
  check(cudaMemcpy(
            &block_delta, device_block_delta,
            sizeof(block_delta), cudaMemcpyDeviceToHost),
        "cudaMemcpy(block delta)");
  check(cudaMemcpy(
            &poison_count, device_poison_count, sizeof(poison_count),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(block poison count)");
  if (poison_count != expected_poison ||
      (expected_poison == 0 &&
       (!same(reduced_candidate, block_candidate) ||
        block_delta.mertens != prefixes.back().mertens ||
        block_delta.squarefree != prefixes.back().squarefree))) {
    std::cerr << "block-compose affine mismatch at count="
              << count << " pattern=" << pattern << '\n';
    std::exit(1);
  }

  check(cudaFree(device_workspace), "cudaFree(workspace)");
  check(cudaFree(device_poison_count), "cudaFree(poison count)");
  check(cudaFree(device_block_summaries),
        "cudaFree(block summaries)");
  check(cudaFree(device_block_candidate),
        "cudaFree(block candidate)");
  check(cudaFree(device_reduced_candidate),
        "cudaFree(reduced candidate)");
  check(cudaFree(device_candidates), "cudaFree(candidates)");
  check(cudaFree(device_block_delta), "cudaFree(block delta)");
  check(cudaFree(device_prefixes), "cudaFree(prefixes)");
  check(cudaFree(device_supports), "cudaFree(supports)");
  check(cudaFree(device_mobius), "cudaFree(mobius)");
}

void run_malformed_packed_decode_cases() {
  constexpr std::size_t count = 6;
  constexpr std::uint64_t lower =
      kTgMobiusSourceLimit - count + 1;
  std::array<TgMobiusFusedSupport, count> supports{};
  supports[0].packed = 1 | kTgMobiusFusedReservedMask;
  supports[1].packed = 1 | kTgMobiusFusedPoisonBit;
  supports[2].packed = 0;
  supports[3].packed =
      1 |
      (static_cast<std::uint64_t>(
           kTgMobiusFusedMaximumDistinctPrimes + 1)
       << kTgMobiusFusedCountShift);
  supports[4].packed = lower + 4 + 1;
  const std::uint64_t final_number = lower + 5;
  const std::uint64_t nondivisor =
      final_number % 2 != 0 ? 2 :
      final_number % 3 != 0 ? 3 : 5;
  supports[5].packed = nondivisor;

  TgMobiusFusedSupport* device_supports = nullptr;
  TgMobiusPrefixMQ* device_prefixes = nullptr;
  TgMobiusPrefixMQ* device_delta = nullptr;
  TgMobiusAffineMqThreadCandidates* device_candidate = nullptr;
  TgMobiusAffineMqBlockSummary* device_summaries = nullptr;
  std::uint32_t* device_poison = nullptr;
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_supports), sizeof(supports)),
        "cudaMalloc(malformed supports)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_prefixes),
            count * sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(malformed prefixes)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_delta),
            sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(malformed delta)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(malformed candidate)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_summaries),
            sizeof(TgMobiusAffineMqBlockSummary)),
        "cudaMalloc(malformed summaries)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&device_poison),
            sizeof(std::uint32_t)),
        "cudaMalloc(malformed poison)");
  check(cudaMemcpy(
            device_supports, supports.data(), sizeof(supports),
            cudaMemcpyHostToDevice),
        "cudaMemcpy(malformed supports)");
  check(cudaMemset(device_poison, 0, sizeof(std::uint32_t)),
        "cudaMemset(malformed poison)");
  check(launch_tg_mobius_fused_prefix_inputs(
            lower, device_supports, count, device_prefixes, device_poison),
        "malformed fused-prefix decode");
  std::array<TgMobiusPrefixMQ, count> prefix_inputs{};
  std::uint32_t poison_count = 0;
  check(cudaMemcpy(
            prefix_inputs.data(), device_prefixes, sizeof(prefix_inputs),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(malformed prefixes)");
  check(cudaMemcpy(
            &poison_count, device_poison, sizeof(poison_count),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(malformed poison)");
  if (poison_count != count) {
    fail("malformed fused-prefix words were not all rejected");
  }
  for (const TgMobiusPrefixMQ input : prefix_inputs) {
    if (input.mertens != 0 || input.squarefree != 0) {
      fail("malformed fused-prefix word was not neutralized");
    }
  }
  check(cudaMemset(device_poison, 0, sizeof(std::uint32_t)),
        "cudaMemset(malformed block poison)");
  check(
      launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
          lower, count, device_supports, device_summaries, 1,
          device_delta, device_candidate, device_poison),
      "malformed block decode");
  TgMobiusPrefixMQ delta{};
  check(cudaMemcpy(
            &delta, device_delta, sizeof(delta), cudaMemcpyDeviceToHost),
        "cudaMemcpy(malformed delta)");
  check(cudaMemcpy(
            &poison_count, device_poison, sizeof(poison_count),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(malformed block poison)");
  if (poison_count != count ||
      delta.mertens != 0 || delta.squarefree != 0) {
    fail("malformed block words were not rejected and neutralized");
  }
  check(cudaFree(device_poison), "cudaFree(malformed poison)");
  check(cudaFree(device_summaries), "cudaFree(malformed summaries)");
  check(cudaFree(device_candidate), "cudaFree(malformed candidate)");
  check(cudaFree(device_delta), "cudaFree(malformed delta)");
  check(cudaFree(device_prefixes), "cudaFree(malformed prefixes)");
  check(cudaFree(device_supports), "cudaFree(malformed supports)");
}

void run_alias_rejection_cases() {
  TgMobiusFusedSupport* supports = nullptr;
  TgMobiusAffineMqBlockSummary* summaries = nullptr;
  TgMobiusPrefixMQ* delta = nullptr;
  TgMobiusAffineMqThreadCandidates* candidate = nullptr;
  std::uint32_t* poison = nullptr;
  check(cudaMalloc(
            reinterpret_cast<void**>(&supports),
            sizeof(TgMobiusFusedSupport)),
        "cudaMalloc(alias supports)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&summaries),
            2 * sizeof(TgMobiusAffineMqBlockSummary)),
        "cudaMalloc(alias summaries)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&delta), sizeof(TgMobiusPrefixMQ)),
        "cudaMalloc(alias delta)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&candidate),
            sizeof(TgMobiusAffineMqThreadCandidates)),
        "cudaMalloc(alias candidate)");
  check(cudaMalloc(
            reinterpret_cast<void**>(&poison), sizeof(std::uint32_t)),
        "cudaMalloc(alias poison)");

  const auto expect_summary_alias_rejected =
      [&](const TgMobiusAffineMqBlockSummary* test_summaries,
          TgMobiusPrefixMQ* test_delta,
          TgMobiusAffineMqThreadCandidates* test_candidate,
          const char* label) {
        if (launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
                test_summaries, 1, test_delta, test_candidate) !=
            cudaErrorInvalidValue) {
          const std::string message =
              std::string("summary composer accepted ") + label;
          fail(message.c_str());
        }
      };
  expect_summary_alias_rejected(
      summaries, reinterpret_cast<TgMobiusPrefixMQ*>(summaries),
      candidate, "summaries/delta alias");
  expect_summary_alias_rejected(
      summaries, delta,
      reinterpret_cast<TgMobiusAffineMqThreadCandidates*>(summaries),
      "summaries/candidate alias");
  expect_summary_alias_rejected(
      summaries, delta,
      reinterpret_cast<TgMobiusAffineMqThreadCandidates*>(delta),
      "delta/candidate alias");

  const auto expect_full_alias_rejected =
      [&](const TgMobiusFusedSupport* test_supports,
          TgMobiusAffineMqBlockSummary* test_summaries,
          TgMobiusPrefixMQ* test_delta,
          TgMobiusAffineMqThreadCandidates* test_candidate,
          std::uint32_t* test_poison, const char* label) {
        if (launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
                1, 1, test_supports, test_summaries, 1, test_delta,
                test_candidate, test_poison) != cudaErrorInvalidValue) {
          const std::string message =
              std::string("block composer accepted ") + label;
          fail(message.c_str());
        }
      };

  // Five buffers have ten unordered pairs.  Exercise every pair so a future
  // edit cannot silently remove one of the fail-closed range checks.
  expect_full_alias_rejected(
      reinterpret_cast<TgMobiusFusedSupport*>(summaries),
      summaries, delta, candidate, poison, "supports/summaries alias");
  expect_full_alias_rejected(
      reinterpret_cast<TgMobiusFusedSupport*>(delta),
      summaries, delta, candidate, poison, "supports/delta alias");
  expect_full_alias_rejected(
      reinterpret_cast<TgMobiusFusedSupport*>(candidate),
      summaries, delta, candidate, poison, "supports/candidate alias");
  expect_full_alias_rejected(
      reinterpret_cast<TgMobiusFusedSupport*>(poison),
      summaries, delta, candidate, poison, "supports/poison alias");
  expect_full_alias_rejected(
      supports, reinterpret_cast<TgMobiusAffineMqBlockSummary*>(delta),
      delta, candidate, poison, "summaries/delta alias");
  expect_full_alias_rejected(
      supports, reinterpret_cast<TgMobiusAffineMqBlockSummary*>(candidate),
      delta, candidate, poison, "summaries/candidate alias");
  expect_full_alias_rejected(
      supports, reinterpret_cast<TgMobiusAffineMqBlockSummary*>(poison),
      delta, candidate, poison, "summaries/poison alias");
  expect_full_alias_rejected(
      supports, summaries, delta,
      reinterpret_cast<TgMobiusAffineMqThreadCandidates*>(delta),
      poison, "delta/candidate alias");
  expect_full_alias_rejected(
      supports, summaries, delta, candidate,
      reinterpret_cast<std::uint32_t*>(delta),
      "delta/poison alias");
  expect_full_alias_rejected(
      supports, summaries, delta, candidate,
      reinterpret_cast<std::uint32_t*>(candidate),
      "candidate/poison alias");

  check(cudaFree(poison), "cudaFree(alias poison)");
  check(cudaFree(candidate), "cudaFree(alias candidate)");
  check(cudaFree(delta), "cudaFree(alias delta)");
  check(cudaFree(summaries), "cudaFree(alias summaries)");
  check(cudaFree(supports), "cudaFree(alias supports)");
}

}  // namespace

int main() {
  static_assert(sizeof(TgMobiusPrefixMQ) == 8);
  const std::size_t rows_per_thread =
      tg_mobius_affine_mq_rows_per_thread();
  const std::size_t rows_per_block =
      tg_mobius_affine_mq_rows_per_block();
  if (rows_per_thread != kTgMobiusAffineRowsPerThread ||
      rows_per_block != kTgMobiusAffineRowsPerBlock) {
    fail("affine KAT header/kernel geometry mismatch");
  }
  const std::size_t maximum_summary_count =
      tg_mobius_affine_mq_block_summary_count(100'000'000);
  const std::array<std::size_t, 6> summary_counts{
      1, 2, 255, 256, 257, maximum_summary_count};
  for (const std::size_t summary_count : summary_counts) {
    if (summary_count <= maximum_summary_count) {
      run_summary_compose_case(summary_count, rows_per_block);
    }
  }
  run_cross_tile_equal_value_tie_case(rows_per_block);
  const std::array<std::size_t, 11> counts{
      1,
      2,
      255,
      256,
      257,
      rows_per_block - 1,
      rows_per_block,
      rows_per_block + 1,
      2 * rows_per_block - 1,
      2 * rows_per_block,
      2 * rows_per_block + 1};
  for (const std::size_t count : counts) {
    for (unsigned int pattern = 0; pattern < 4; ++pattern) {
      run_case(count, pattern);
    }
  }
  run_case(1, 4);
  run_case(
      rows_per_block - 1, 0,
      {0, 255, rows_per_block - 2});
  run_case(
      rows_per_block + 1, 1,
      {rows_per_block - 1, rows_per_block});
  run_case(
      2 * rows_per_block + 1, 2,
      {0, 255, 256, rows_per_block - 1,
       rows_per_block, 2 * rows_per_block});
  run_case(rows_per_block + 1, 4);
  run_case(2 * rows_per_block + 1, 5);
  run_malformed_packed_decode_cases();
  run_alias_rejection_cases();
  std::cout << "affine inclusive scan and block-composition KAT passed\n";
  return 0;
}
