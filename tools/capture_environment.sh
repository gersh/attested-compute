#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
output_path="${1:-${project_root}/build/run/environment.txt}"
output_dir="$(dirname -- "${output_path}")"

mkdir -p "${output_dir}"

{
  uname -a
  cat /etc/os-release
  if [[ -f /etc/dgx-release ]]; then cat /etc/dgx-release; fi
  cmake --version
  gcc --version
  python3 --version
  lean --version
  lake --version
  /usr/local/cuda/bin/nvcc --version
  /usr/local/cuda/bin/ptxas --version
  /usr/local/cuda/bin/cuobjdump --version
  /usr/local/cuda/bin/nvdisasm --version
  nvidia-smi
  nvidia-smi --query-gpu=name,compute_cap,uuid,driver_version --format=csv,noheader
  if project_commit="$(git -C "${project_root}" rev-parse --verify HEAD 2>/dev/null)"; then
    echo "project_commit=${project_commit}"
  else
    echo "project_commit=uncommitted"
  fi
  git -C "${project_root}" status --porcelain
  if mathlib_commit="$(git -C "${project_root}/.lake/packages/mathlib" \
      rev-parse --verify HEAD 2>/dev/null)"; then
    echo "mathlib_commit=${mathlib_commit}"
  else
    echo "mathlib_commit=unavailable"
  fi
  git -C "${project_root}/.lake/packages/mathlib" status --porcelain 2>/dev/null || true
} > "${output_path}"

sha256sum "${output_path}" > "${output_path}.sha256"
