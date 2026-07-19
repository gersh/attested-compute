#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_root}"

python3 "${script_dir}/audit_lean_source.py"

lake build
lake env lean SparkInterval/Tests/AxiomAudit.lean
lake env lean SparkInterval/Tests/ExecutionBridgeTest.lean
