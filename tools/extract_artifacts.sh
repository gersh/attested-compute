#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <cuda-executable> <output-directory>" >&2
  exit 2
fi

input_binary="$1"
output_dir="$2"

if [[ ! -f "${input_binary}" ]]; then
  echo "input executable does not exist: ${input_binary}" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
input_binary="$(realpath -- "${input_binary}")"
mkdir -p "${output_dir}"
cp -- "${input_binary}" "${output_dir}/sparkinterval-probe"
/usr/local/cuda/bin/cuobjdump --dump-ptx "${input_binary}" > "${output_dir}/probe.ptx.txt"
/usr/local/cuda/bin/cuobjdump --dump-sass "${input_binary}" > "${output_dir}/probe.sass.txt"
/usr/local/cuda/bin/cuobjdump --dump-elf "${input_binary}" > "${output_dir}/probe.elf.txt"
/usr/local/cuda/bin/cuobjdump --list-elf "${input_binary}" > "${output_dir}/probe.elf.list.txt"
(
  cd "${output_dir}"
  /usr/local/cuda/bin/cuobjdump --extract-elf all "${input_binary}"
  /usr/local/cuda/bin/cuobjdump --extract-ptx all "${input_binary}"
  /usr/local/cuda/bin/nvdisasm probe_kernel.sm_121.cubin > probe.nvdisasm.sass.txt
)
python3 "${script_dir}/inspect_probe_ptx.py" \
  "${output_dir}/probe_kernel.sm_121.ptx" \
  "${output_dir}/probe.ptx.json" \
  --target sm_121
"${script_dir}/inspect_sass.sh" \
  "${output_dir}/probe.sass.txt" \
  "${output_dir}/probe.sass.json" \
  --allow-division-lowering

(
  cd "${output_dir}"
  sha256sum sparkinterval-probe probe.ptx.txt probe.ptx.json probe.sass.txt probe.sass.json \
    probe.elf.txt probe.elf.list.txt probe_kernel.sm_121.cubin \
    probe_kernel.sm_121.ptx probe.nvdisasm.sass.txt
) > "${output_dir}/sha256sums.txt"
