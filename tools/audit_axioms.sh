#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_root}"

# Refuse an accidental local aggregate audit before scanning sources or
# touching Lake state.  The measured-worker scope is dispatch protection only,
# not attestation evidence.
"${script_dir}/safe_lake_build.py" \
  --full-production-library --plan >/dev/null

python3 "${script_dir}/audit_lean_source.py"

# The one attestation link Lean does not check: that the pinned enclave key
# belongs to a genuine TDX platform rooted in Intel's CA.  Lean verifies, in
# kernel, that the pinned key signed a statement naming the algorithm, its
# input and its result, and that the quote's mrconfigid and report data bind
# that key to the pinned compose.  It does NOT parse PCK certificate chains,
# and `SparkInterval/Execution/PhalaTdxOperationalAttestation.lean` still says
# so.  This gate walks the chain OUTSIDE the kernel so it cannot be silently
# skipped.
#
# Fully offline and deterministic: committed quote bytes against the committed
# `tools/intel_sgx_root_ca.pem`.  No network.  Confirming that the pinned PEM
# still matches Intel's published root is the separate `--live` mode, run in
# CI, deliberately not here -- a build must not fail because Intel's service is
# down, and a network failure must not look like an attestation failure.
#
# `--require-evidence` is load bearing: the bundles are committed to this
# repository, so their absence is a broken checkout, not an unconfigured one.
# Without it the checker would exit 3 ("nothing to check"), which is a loud
# skip rather than a pass.
lake exe sparkinterval-check-tdx-chain --require-evidence

python3 "${script_dir}/generate_trusted_compute_registry.py" \
  --allow-empty \
  --check \
  --out SparkInterval/Execution/TrustedComputeRegistry.lean

# This fixed aggregate audit intentionally imports the materialized production
# registry.  Keep that expensive closure off ordinary local/default builds.
"${script_dir}/safe_lake_build.py" --full-production-library

# Inventory concrete receipt instantiations and direct trust-axiom callers in
# the aggregate production environment, not merely a narrow consumer import.
"${script_dir}/safe_lean.sh" SparkInterval/Tests/ProjectCertificateAudit.lean

core_report="$(mktemp)"
execution_report="$(mktemp)"
trap 'rm -f -- "${core_report}" "${execution_report}"' EXIT

"${script_dir}/safe_lean.sh" SparkInterval/Tests/AxiomAudit.lean \
  2>&1 | tee "${core_report}"
python3 "${script_dir}/check_axiom_report.py" \
  --expected-count 159 \
  --allow propext \
  --allow Classical.choice \
  --allow Quot.sound \
  "${core_report}"

"${script_dir}/safe_lean.sh" SparkInterval/Tests/ExecutionBridgeTest.lean \
  2>&1 | tee "${execution_report}"
python3 "${script_dir}/check_axiom_report.py" \
  --expected-count 16 \
  --allow propext \
  --allow Classical.choice \
  --allow Quot.sound \
  --allow accepted_run_certificate_sound \
  "${execution_report}"
