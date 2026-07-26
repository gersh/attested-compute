// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_stationary_resolver.hpp"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace psr = sparkinterval::tg::platt_stationary_resolver;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

struct Options {
  std::string mode = "valid";
  std::uint32_t iterations = 100U;
};

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--mode" && index + 1 < argc) {
      options.mode = argv[++index];
    } else if (argument == "--iterations" && index + 1 < argc) {
      const unsigned long value = std::stoul(argv[++index]);
      if (value == 0UL || value > 100'000UL) {
        throw std::invalid_argument("--iterations is outside 1..100000");
      }
      options.iterations = static_cast<std::uint32_t>(value);
    } else {
      throw std::invalid_argument(
          "usage: --mode valid|ambiguous-refined|ambiguous|bad-refinement|"
          "candidate|depth|benchmark [--iterations N]");
    }
  }
  if (options.mode != "valid" && options.mode != "ambiguous-refined" &&
      options.mode != "ambiguous" && options.mode != "bad-refinement" &&
      options.mode != "candidate" && options.mode != "depth" &&
      options.mode != "benchmark") {
    throw std::invalid_argument("unknown --mode");
  }
  return options;
}

std::size_t at(std::int32_t offset) {
  return static_cast<std::size_t>(offset - psr::kRequiredLower);
}

std::vector<pw::RealDisk106> hidden_pair_fixture() {
  std::vector<pw::RealDisk106> samples(psr::kRequiredCount);
  const double radius = std::ldexp(1.0, -80);
  for (pw::RealDisk106& sample : samples) {
    sample = {{3.0, 0.0}, radius};
  }
  // The strict source triple [0,1,2] is positive with a local minimum at 1.
  // A remote negative cardinal sample forces the corrected 140-row
  // interpolation below zero at the first dyadic query.  This fixture tests
  // control flow and arithmetic only; it is not a Hardy-Z value.
  samples[at(0)] = {{3.0, 0.0}, radius};
  samples[at(1)] = {{1.0, 0.0}, radius};
  samples[at(2)] = {{3.0, 0.0}, radius};
  samples[at(3)] = {{-100.0, 0.0}, radius};
  return samples;
}

std::vector<psr::Candidate> expected_candidates() {
  return {{psr::StreamKind::kMain, 0, 2, true}};
}

psr::Report invoke(std::string_view mode) {
  std::vector<pw::RealDisk106> samples = hidden_pair_fixture();
  std::vector<psr::Candidate> candidates = expected_candidates();
  std::vector<psr::SparseRefinement> refinements;
  psr::Options options;
  if (mode == "ambiguous-refined" || mode == "ambiguous" ||
      mode == "bad-refinement") {
    samples[at(1)] = {{0.0, 0.0}, 2.0};
  }
  if (mode == "ambiguous-refined") {
    refinements.push_back({1, "1 0", "1 0"});
  } else if (mode == "bad-refinement") {
    refinements.push_back({1, "3 0", "3 0"});
  } else if (mode == "candidate") {
    candidates.clear();
  } else if (mode == "depth") {
    samples[at(3)] = {{3.0, 0.0}, std::ldexp(1.0, -80)};
    options.maximum_depth = 1U;
  }
  return psr::resolve_block(samples, candidates, refinements, options);
}

int run(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  if (options.mode != "benchmark") {
    const psr::Report report = invoke(options.mode);
    std::cout << report.canonical_trace_json;
    const bool expected_success =
        options.mode == "valid" || options.mode == "ambiguous-refined";
    return report.accepted == expected_success ? 0 : 1;
  }

  for (unsigned int warmup = 0; warmup < 3U; ++warmup) {
    if (!invoke("valid").accepted) {
      throw std::runtime_error("stationary resolver warmup failed");
    }
  }
  std::string first_digest;
  std::uint64_t evaluations = 0U;
  const auto start = std::chrono::steady_clock::now();
  for (std::uint32_t iteration = 0; iteration < options.iterations;
       ++iteration) {
    const psr::Report report = invoke("valid");
    if (!report.accepted || !report.replay_accepted) {
      throw std::runtime_error("stationary resolver benchmark failed");
    }
    if (iteration == 0U) first_digest = report.resolution_sha256;
    if (report.resolution_sha256 != first_digest) {
      throw std::runtime_error("stationary resolver digest is nondeterministic");
    }
    evaluations += report.interpolation_evaluations;
  }
  const double seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start).count();
  std::cout << "{\"accepted\":true"
            << ",\"benchmark_scope\":\"bounded_cpu_flint_fallback_only\""
            << ",\"blocks\":" << options.iterations
            << ",\"blocks_per_second\":"
            << static_cast<double>(options.iterations) / seconds
            << ",\"elapsed_seconds\":" << seconds
            << ",\"flint_to_mathlib_realization_proved\":false"
            << ",\"hardy_z_endpoint_realization_proved\":false"
            << ",\"interpolation_evaluations\":" << evaluations
            << ",\"iterations\":" << options.iterations
            << ",\"platform\":\"NVIDIA GB10 host CPU\""
            << ",\"resolution_sha256\":\"" << first_digest << "\""
            << ",\"stationary_candidates_per_block\":1"
            << ",\"turing_analytic_bounds_proved\":false}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-stationary-resolver: "
              << error.what() << '\n';
    return 2;
  }
}
