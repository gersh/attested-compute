#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-${repo_root}/build/h100-interval-batch-offline}"
kernel_wrapper="${repo_root}/gpu/platform/h100/h100_interval_batch_kernel.cu"
kernel_implementation="${repo_root}/gpu/src/interval_batch_kernel.cu"
protocol_header="${repo_root}/gpu/include/interval_batch.h"
host_wrapper="${repo_root}/gpu/platform/h100/h100_interval_batch_runner.cpp"
host_implementation="${repo_root}/gpu/src/interval_batch_runner.cpp"
ptx_auditor="${repo_root}/gpu/platform/h100/h100_interval_batch_ptx_audit.py"
cuda_root="${CUDA_ROOT:-/usr/local/cuda}"
cxx="${CXX:-c++}"
nvcc="${NVCC:-${cuda_root}/bin/nvcc}"
nvdisasm="${NVDISASM:-${cuda_root}/bin/nvdisasm}"
cuobjdump="${CUOBJDUMP:-${cuda_root}/bin/cuobjdump}"

for tool in "$nvcc" "$nvdisasm" "$cuobjdump"; do
  if [[ ! -x "$tool" ]]; then
    echo "required CUDA tool is not executable: $tool" >&2
    exit 69
  fi
done
if ! command -v "$cxx" >/dev/null 2>&1; then
  echo "C++ compiler not found: $cxx" >&2
  exit 69
fi
for source in \
  "$kernel_wrapper" \
  "$kernel_implementation" \
  "$protocol_header" \
  "$host_wrapper" \
  "$host_implementation" \
  "$ptx_auditor"; do
  if [[ ! -f "$source" ]]; then
    echo "missing H100 interval-batch source: $source" >&2
    exit 66
  fi
done

mkdir -p "$output_dir"

ptx_file="${output_dir}/h100_interval_batch.compute_90.ptx"
ptx_audit="${output_dir}/h100_interval_batch.compute_90.ptx.json"
cubin_file="${output_dir}/h100_interval_batch.sm_90.cubin"
sass_file="${output_dir}/h100_interval_batch.sm_90.sass"
sass_audit="${output_dir}/h100_interval_batch.sm_90.sass.json"
elf_file="${output_dir}/h100_interval_batch.sm_90.elf.txt"
ptxas_log="${output_dir}/h100_interval_batch.ptxas.log"
host_syntax_log="${output_dir}/h100_interval_batch.host-syntax.log"
toolchain_file="${output_dir}/h100_interval_batch.toolchain.txt"
manifest_file="${output_dir}/h100_interval_batch.manifest.json"

common_nvcc_flags=(
  -std=c++17
  --fmad=false
  --ftz=false
  --prec-div=true
  --prec-sqrt=true
  --generate-line-info
  -I"${repo_root}/gpu/include"
)

"$nvcc" \
  "${common_nvcc_flags[@]}" \
  --ptx \
  --gpu-architecture=compute_90 \
  --gpu-code=compute_90 \
  "$kernel_wrapper" \
  --output-file "$ptx_file"

python3 "$ptx_auditor" "$ptx_file" "$ptx_audit" --target sm_90

"$nvcc" \
  "${common_nvcc_flags[@]}" \
  --cubin \
  --gpu-architecture=compute_90 \
  --gpu-code=sm_90 \
  --ptxas-options=-v \
  "$kernel_wrapper" \
  --output-file "$cubin_file" \
  >"$ptxas_log" 2>&1

"$nvdisasm" --print-code --print-instruction-encoding "$cubin_file" >"$sass_file"
"$cuobjdump" --dump-elf "$cubin_file" >"$elf_file"
"${repo_root}/tools/inspect_sass.sh" \
  "$sass_file" "$sass_audit" --allow-division-lowering

"$cxx" -std=c++20 -Wall -Wextra -Wpedantic -Werror \
  -I"${cuda_root}/include" \
  -I"${repo_root}/gpu/include" \
  -fsyntax-only "$host_wrapper" \
  >"$host_syntax_log" 2>&1

{
  echo "evidence_class=offline_static_validation"
  echo "execution_performed=false"
  echo "h100_presence_queried=false"
  echo "h100_execution_attempted=false"
  echo "production_attestation_present=false"
  echo "build_host_architecture=$(uname -m)"
  echo "device_virtual_target=compute_90"
  echo "device_binary_target=sm_90"
  echo "host_executable_built=false"
  echo "host_runner_source_syntax_checked=true"
  "$cxx" --version
  "$nvcc" --version
  "$nvdisasm" --version
  "$cuobjdump" --version
} >"$toolchain_file"

python3 - \
  "$repo_root" \
  "$output_dir" \
  "$manifest_file" \
  "$nvcc" \
  "$(uname -m)" <<'PY'
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


repo_root = pathlib.Path(sys.argv[1]).resolve()
output_dir = pathlib.Path(sys.argv[2]).resolve()
manifest_file = pathlib.Path(sys.argv[3]).resolve()
nvcc = sys.argv[4]
host_arch = sys.argv[5]

source_names = {
    "kernel_wrapper": "gpu/platform/h100/h100_interval_batch_kernel.cu",
    "kernel_implementation": "gpu/src/interval_batch_kernel.cu",
    "protocol_header": "gpu/include/interval_batch.h",
    "host_wrapper": "gpu/platform/h100/h100_interval_batch_runner.cpp",
    "host_implementation": "gpu/src/interval_batch_runner.cpp",
    "ptx_auditor": "gpu/platform/h100/h100_interval_batch_ptx_audit.py",
}
sources = {
    name: {"file": filename, "sha256": sha256(repo_root / filename)}
    for name, filename in source_names.items()
}
artifact_names = {
    "ptx": "h100_interval_batch.compute_90.ptx",
    "ptx_audit": "h100_interval_batch.compute_90.ptx.json",
    "cubin": "h100_interval_batch.sm_90.cubin",
    "sass": "h100_interval_batch.sm_90.sass",
    "sass_audit": "h100_interval_batch.sm_90.sass.json",
    "elf_metadata": "h100_interval_batch.sm_90.elf.txt",
    "ptxas_log": "h100_interval_batch.ptxas.log",
    "host_syntax_log": "h100_interval_batch.host-syntax.log",
    "toolchain": "h100_interval_batch.toolchain.txt",
}
artifacts = {
    name: {"file": filename, "sha256": sha256(output_dir / filename)}
    for name, filename in artifact_names.items()
}
nvcc_version = subprocess.check_output(
    [nvcc, "--version"], text=True, stderr=subprocess.STDOUT
).strip()

manifest = {
    "schema_version": "gpu-prover.h100-interval-batch-offline.v1",
    "evidence_class": "offline_static_validation",
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "claim_scope": [
        "The reviewed interval-batch source compiled to PTX for compute_90.",
        "The PTX contains exactly one of each required add/sub/mul/div f64 operation in round-down and round-up modes.",
        "The source assembled to a cubin for sm_90 and that cubin was statically disassembled.",
        "The SASS passed the repository lexical policy, including the reviewed precise-division lowering allowance.",
        "The H100 host-runner source passed a strict syntax check on the recorded build host.",
    ],
    "excluded_claims": [
        "An H100 was present on the build host.",
        "The kernel or host runner executed on an H100.",
        "The kernel returned any arithmetic result.",
        "PTX and SASS are formally semantically equivalent.",
        "Any artifact or result was hardware-attested.",
        "The host object code is suitable for a differently architected H100 host.",
    ],
    "target": {
        "vendor": "NVIDIA",
        "gpu_family": "Hopper H100",
        "compute_capability": "9.0",
        "ptx_target": "compute_90",
        "cubin_target": "sm_90",
    },
    "algorithm": {
        "operation_set": ["add", "sub", "mul", "div"],
        "rounding_modes_per_operation": ["round_down", "round_up"],
        "input_protocol": "SIB64I01/v1",
        "output_protocol": "SIB64O01/v1",
    },
    "sources": sources,
    "build_host": {
        "architecture": host_arch,
        "device_code_only": True,
        "host_executable_built": False,
        "host_runner_source_syntax_checked": True,
        "h100_presence_queried": False,
        "h100_execution_attempted": False,
    },
    "execution": {
        "executed": False,
        "execution_device": None,
        "result": None,
    },
    "production_attestation": {
        "present": False,
        "provider": None,
    },
    "toolchain": {
        "nvcc": nvcc_version,
        "fmad": False,
        "ftz": False,
        "prec_div": True,
        "prec_sqrt": True,
        "line_info": True,
    },
    "artifacts": artifacts,
}
manifest_file.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

(
  cd "$output_dir"
  sha256sum \
    h100_interval_batch.compute_90.ptx \
    h100_interval_batch.compute_90.ptx.json \
    h100_interval_batch.sm_90.cubin \
    h100_interval_batch.sm_90.sass \
    h100_interval_batch.sm_90.sass.json \
    h100_interval_batch.sm_90.elf.txt \
    h100_interval_batch.ptxas.log \
    h100_interval_batch.host-syntax.log \
    h100_interval_batch.toolchain.txt \
    h100_interval_batch.manifest.json \
    >SHA256SUMS
)

echo "Built H100 interval-batch offline evidence in $output_dir"
echo "Static compilation and inspection only: no H100 execution or attestation was performed."
