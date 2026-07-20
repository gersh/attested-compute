#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_root}"

python3 "${script_dir}/audit_lean_source.py"

"${script_dir}/safe_lake_build.py"

core_report="$(mktemp)"
execution_report="$(mktemp)"
trap 'rm -f -- "${core_report}" "${execution_report}"' EXIT

"${script_dir}/safe_lean.sh" SparkInterval/Tests/AxiomAudit.lean \
  2>&1 | tee "${core_report}"
python3 "${script_dir}/check_axiom_report.py" \
  --expected-count 158 \
  --allow propext \
  --allow Classical.choice \
  --allow Quot.sound \
  "${core_report}"

"${script_dir}/safe_lean.sh" SparkInterval/Tests/ExecutionBridgeTest.lean \
  2>&1 | tee "${execution_report}"
python3 "${script_dir}/check_axiom_report.py" \
  --expected-count 13 \
  --allow propext \
  --allow Classical.choice \
  --allow Quot.sound \
  --allow accepted_run_certificate_sound \
  "${execution_report}"
