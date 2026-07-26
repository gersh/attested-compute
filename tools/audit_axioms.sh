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
