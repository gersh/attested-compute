#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-${repo_root}/build/h100-offline}"
source_file="${repo_root}/gpu/platform/h100/h100_rounding_probe.cu"
host_runner_source="${repo_root}/gpu/platform/h100/h100_probe_runner.cpp"
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
if [[ ! -f "$source_file" ]]; then
  echo "missing H100 probe source: $source_file" >&2
  exit 66
fi
if [[ ! -f "$host_runner_source" ]]; then
  echo "missing H100 host-runner source: $host_runner_source" >&2
  exit 66
fi
if ! command -v "$cxx" >/dev/null 2>&1; then
  echo "C++ compiler not found: $cxx" >&2
  exit 69
fi

mkdir -p "$output_dir"

ptx_file="${output_dir}/h100_rounding_probe.compute_90.ptx"
ptx_audit="${output_dir}/h100_rounding_probe.compute_90.ptx.json"
cubin_file="${output_dir}/h100_rounding_probe.sm_90.cubin"
sass_file="${output_dir}/h100_rounding_probe.sm_90.sass"
sass_audit="${output_dir}/h100_rounding_probe.sm_90.sass.json"
elf_file="${output_dir}/h100_rounding_probe.sm_90.elf.txt"
ptxas_log="${output_dir}/ptxas.log"
toolchain_file="${output_dir}/toolchain.txt"
host_syntax_log="${output_dir}/host-runner-syntax.log"
manifest_file="${output_dir}/manifest.json"

"$nvcc" \
  -std=c++17 \
  --ptx \
  --gpu-architecture=compute_90 \
  --gpu-code=compute_90 \
  --fmad=false \
  --ftz=false \
  --prec-div=true \
  --prec-sqrt=true \
  --generate-line-info \
  "$source_file" \
  --output-file "$ptx_file"

python3 "${repo_root}/tools/inspect_probe_ptx.py" \
  "$ptx_file" "$ptx_audit" --target sm_90

"$nvcc" \
  -std=c++17 \
  --cubin \
  --gpu-architecture=compute_90 \
  --gpu-code=sm_90 \
  --fmad=false \
  --ftz=false \
  --prec-div=true \
  --prec-sqrt=true \
  --generate-line-info \
  --ptxas-options=-v \
  "$source_file" \
  --output-file "$cubin_file" \
  >"$ptxas_log" 2>&1

"$nvdisasm" --print-code --print-instruction-encoding "$cubin_file" >"$sass_file"
"$cuobjdump" --dump-elf "$cubin_file" >"$elf_file"
"${repo_root}/tools/inspect_sass.sh" \
  "$sass_file" "$sass_audit" --allow-division-lowering

"$cxx" -std=c++20 -Wall -Wextra -Wpedantic -Werror \
  -I"${cuda_root}/include" -fsyntax-only "$host_runner_source" \
  >"$host_syntax_log" 2>&1

{
  echo "evidence_class=offline_device_build"
  echo "execution_performed=false"
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
  "$source_file" \
  "$manifest_file" \
  "$(uname -m)" \
  "$nvcc" \
  "$host_runner_source" <<'PY'
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
source_file = pathlib.Path(sys.argv[3]).resolve()
manifest_file = pathlib.Path(sys.argv[4]).resolve()
host_arch = sys.argv[5]
nvcc = sys.argv[6]
host_runner_source = pathlib.Path(sys.argv[7]).resolve()

artifact_names = {
    "ptx": "h100_rounding_probe.compute_90.ptx",
    "ptx_audit": "h100_rounding_probe.compute_90.ptx.json",
    "cubin": "h100_rounding_probe.sm_90.cubin",
    "sass": "h100_rounding_probe.sm_90.sass",
    "sass_audit": "h100_rounding_probe.sm_90.sass.json",
    "elf_metadata": "h100_rounding_probe.sm_90.elf.txt",
    "ptxas_log": "ptxas.log",
    "toolchain": "toolchain.txt",
    "host_runner_syntax_log": "host-runner-syntax.log",
}
artifacts = {
    name: {"file": filename, "sha256": sha256(output_dir / filename)}
    for name, filename in artifact_names.items()
}

nvcc_version = subprocess.check_output(
    [nvcc, "--version"], text=True, stderr=subprocess.STDOUT
).strip()
manifest = {
    "schema_version": "gpu-prover.offline-device-build.v1",
    "evidence_class": "offline_device_build",
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "claim_scope": [
        "The source compiled to PTX for compute_90.",
        "The source assembled to a cubin for sm_90.",
        "The cubin was statically disassembled by the recorded CUDA toolchain.",
        "The portable host-runner source passed a strict syntax check on the build host.",
    ],
    "excluded_claims": [
        "The artifact ran on an H100.",
        "The kernel returned any result.",
        "The artifact was hardware-attested.",
        "The current build host can supply an x86_64 H100 host executable.",
    ],
    "target": {
        "vendor": "NVIDIA",
        "gpu_family": "Hopper H100",
        "compute_capability": "9.0",
        "ptx_target": "compute_90",
        "cubin_target": "sm_90",
    },
    "source": {
        "file": str(source_file.relative_to(repo_root)),
        "sha256": sha256(source_file),
    },
    "host_runner_source": {
        "file": str(host_runner_source.relative_to(repo_root)),
        "sha256": sha256(host_runner_source),
        "syntax_checked_on_architecture": host_arch,
    },
    "build_host": {
        "architecture": host_arch,
        "device_code_only": True,
        "host_executable_built": False,
        "host_runner_source_syntax_checked": True,
        "host_target_note": (
            "This pipeline emits architecture-independent PTX and NVIDIA sm_90 "
            "device code only. Build and validate the CUDA host runner on the "
            "actual H100 host architecture (commonly x86_64)."
        ),
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
with manifest_file.open("w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

(
  cd "$output_dir"
  sha256sum \
    h100_rounding_probe.compute_90.ptx \
    h100_rounding_probe.compute_90.ptx.json \
    h100_rounding_probe.sm_90.cubin \
    h100_rounding_probe.sm_90.sass \
    h100_rounding_probe.sm_90.sass.json \
    h100_rounding_probe.sm_90.elf.txt \
    ptxas.log \
    toolchain.txt \
    host-runner-syntax.log \
    manifest.json \
    >SHA256SUMS
)

echo "Built offline H100 device evidence in $output_dir"
echo "No H100 execution or production attestation was performed."
