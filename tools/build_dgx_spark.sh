#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
build_dir="${project_root}/build/dgx-spark"
run_dir="${project_root}/build/run"
artifact_dir="${project_root}/build/artifacts"
bundle_dir="${project_root}/build/dgx-probe-bundle"
mathlib_dir="${project_root}/.lake/packages/mathlib"
build_jobs="${SPARKINTERVAL_BUILD_JOBS:-1}"

if [[ ! "${build_jobs}" =~ ^[1-9][0-9]*$ ]]; then
  echo "SPARKINTERVAL_BUILD_JOBS must be a positive integer" >&2
  exit 2
fi

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "DGX Spark build requires aarch64" >&2
  exit 1
fi

for required_tool in lean lake cmake nvidia-smi /usr/local/cuda/bin/nvcc /usr/local/cuda/bin/ptxas; do
  if ! command -v "${required_tool}" >/dev/null 2>&1; then
    echo "required tool not found: ${required_tool}" >&2
    exit 1
  fi
done

compute_capability="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | tr -d '[:space:]')"
if [[ "${compute_capability}" != "12.1" ]]; then
  echo "expected DGX Spark compute capability 12.1, found ${compute_capability}" >&2
  exit 1
fi

mkdir -p "${build_dir}" "${run_dir}" "${artifact_dir}"
"${script_dir}/capture_environment.sh" "${run_dir}/environment.txt"
cat "${run_dir}/environment.txt"

cd "${project_root}"
"${script_dir}/safe_lake_build.py"
if [[ ! -d "${mathlib_dir}/.git" ]]; then
  echo "pinned Lake mathlib checkout not found after build: ${mathlib_dir}" >&2
  exit 1
fi
expected_mathlib_commit="$(tr -d '[:space:]' < "${project_root}/dependencies/mathlib4.commit")"
actual_mathlib_commit="$(git -C "${mathlib_dir}" rev-parse HEAD)"
if [[ "${actual_mathlib_commit}" != "${expected_mathlib_commit}" ]]; then
  echo "mathlib revision mismatch: expected ${expected_mathlib_commit}, found ${actual_mathlib_commit}" >&2
  exit 1
fi
"${script_dir}/audit_axioms.sh"
python3 -m unittest discover -s tests -p 'test_*.py' -v

"${script_dir}/with_memory_limit.sh" cmake \
  -S "${project_root}" -B "${build_dir}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121
"${script_dir}/with_memory_limit.sh" cmake \
  --build "${build_dir}" --parallel "${build_jobs}"
"${script_dir}/with_memory_limit.sh" ctest \
  --test-dir "${build_dir}" --parallel 1 --output-on-failure
probe_start_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${build_dir}/sparkinterval-probe" > "${run_dir}/probe.json"
probe_end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${script_dir}/extract_artifacts.sh" "${build_dir}/sparkinterval-probe" "${artifact_dir}"
sha256sum "${run_dir}/probe.json" > "${run_dir}/probe.json.sha256"

bundle_nonce_args=()
if [[ -n "${SPARKINTERVAL_NONCE_HEX:-}" ]]; then
  bundle_nonce_args+=(--nonce "${SPARKINTERVAL_NONCE_HEX}")
fi
python3 "${script_dir}/create_dgx_probe_bundle.py" \
  --probe-output "${run_dir}/probe.json" \
  --host-executable "${build_dir}/sparkinterval-probe" \
  --cubin "${artifact_dir}/probe_kernel.sm_121.cubin" \
  --ptx "${artifact_dir}/probe_kernel.sm_121.ptx" \
  --ptx-audit "${artifact_dir}/probe.ptx.json" \
  --sass "${artifact_dir}/probe.sass.txt" \
  --sass-audit "${artifact_dir}/probe.sass.json" \
  --kernel-source "${project_root}/gpu/src/probe_kernel.cu" \
  --environment-record "${run_dir}/environment.txt" \
  --output-root "${bundle_dir}" \
  --start-time-utc "${probe_start_time}" \
  --end-time-utc "${probe_end_time}" \
  "${bundle_nonce_args[@]}"

echo "DGX Spark build and validation completed: ${build_dir}"
