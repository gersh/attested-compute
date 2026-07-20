#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${repo_root}/build/h100-full-validation"
build_dir="${repo_root}/build/h100-native"
primitive_count=1250000
expression_count=100000
expression_program_count=32
generated_count=10000
zeta_terms=4096
device=0

usage() {
  cat <<'EOF'
usage: tools/run_h100_full_validation.sh [OPTIONS]

Run the complete local-unattested H100 validation surface: strict native
rounding probe, primitive and postfix exact conformance, Lean-generated sm_90
polynomial PTX conformance, and the rigorous real-integer zeta tutorial.

The command requires exactly one visible H100, an x86_64 host, CUDA 13 tools,
CMake, Python 3, and the repository Lean toolchain. It does not collect or
claim NVIDIA confidential-computing attestation, and it does not verify zeta
zeros.

Options:
  --output-dir DIR                new retained result directory
  --build-dir DIR                 CMake build directory
  --primitive-count N             random rows per primitive operation
  --expression-count N            randomized expression/row cases
  --expression-program-count N    randomized postfix programs
  --generated-count N             generated-polynomial rows
  --zeta-terms N                  retained real-zeta terms
  --device N                      CUDA device index (must be 0)
  --help                          show this help
EOF
}

require_value() {
  if [[ "$2" -lt 2 ]]; then
    echo "$1 requires a value" >&2
    exit 64
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      require_value "$1" "$#"
      output_dir="$2"
      shift 2
      ;;
    --build-dir)
      require_value "$1" "$#"
      build_dir="$2"
      shift 2
      ;;
    --primitive-count)
      require_value "$1" "$#"
      primitive_count="$2"
      shift 2
      ;;
    --expression-count)
      require_value "$1" "$#"
      expression_count="$2"
      shift 2
      ;;
    --expression-program-count)
      require_value "$1" "$#"
      expression_program_count="$2"
      shift 2
      ;;
    --generated-count)
      require_value "$1" "$#"
      generated_count="$2"
      shift 2
      ;;
    --zeta-terms)
      require_value "$1" "$#"
      zeta_terms="$2"
      shift 2
      ;;
    --device)
      require_value "$1" "$#"
      device="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

for value_name in \
  primitive_count \
  expression_count \
  expression_program_count \
  generated_count \
  zeta_terms; do
  value="${!value_name}"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "$value_name must be a positive integer" >&2
    exit 64
  fi
done
if [[ "$device" != 0 ]]; then
  echo "the strict single-H100 profile requires --device 0" >&2
  exit 64
fi
if [[ "$(uname -m)" != x86_64 ]]; then
  echo "the strict H100 validation profile requires an x86_64 host" >&2
  exit 69
fi
if [[ -e "$output_dir" ]]; then
  echo "output directory already exists: $output_dir" >&2
  exit 73
fi

for command in \
  cmake \
  cuobjdump \
  find \
  flock \
  gcc \
  g++ \
  lake \
  lean \
  nvidia-smi \
  nvcc \
  nvdisasm \
  ptxas \
  python3 \
  sha256sum \
  sort \
  tee \
  xargs; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "required command is unavailable: $command" >&2
    exit 69
  fi
done

lean_memory_mode=""
lean_memory_detail=""
lean_vm_limit_kib="${H100_LEAN_VM_LIMIT_KIB:-16777216}"
lean_memory_high="10G"
lean_memory_max="12G"
lean_swap_max="2G"
lean_tasks_max="32"
lean_runtime_max="30min"
if command -v systemctl >/dev/null 2>&1 \
    && systemctl --user show-environment >/dev/null 2>&1; then
  if ! SPARKINTERVAL_MEMORY_HIGH="$lean_memory_high" \
      SPARKINTERVAL_MEMORY_MAX="$lean_memory_max" \
      SPARKINTERVAL_SWAP_MAX="$lean_swap_max" \
      SPARKINTERVAL_TASKS_MAX="$lean_tasks_max" \
      SPARKINTERVAL_RUNTIME_MAX="$lean_runtime_max" \
      "${repo_root}/tools/with_memory_limit.sh" /usr/bin/true \
      >/dev/null; then
    echo "the user systemd manager cannot run the required memory-capped unit" >&2
    exit 69
  fi
  lean_memory_mode="user_systemd_cgroup"
  lean_memory_detail="MemoryHigh=10G MemoryMax=12G MemorySwapMax=2G TasksMax=32 RuntimeMaxSec=30min"
else
  cgroup_memory_max="$(cat /sys/fs/cgroup/memory.max 2>/dev/null || true)"
  minimum_cgroup_bytes=17179869184
  if [[ "$cgroup_memory_max" =~ ^[0-9]+$ ]]; then
    if (( cgroup_memory_max < minimum_cgroup_bytes )); then
      echo "container memory.max is below the 16 GiB H100 validation minimum" >&2
      exit 69
    fi
    lean_memory_mode="finite_container_cgroup"
    lean_memory_detail="memory.max=${cgroup_memory_max}"
  else
    minimum_vm_limit_kib=12582912
    if [[ ! "$lean_vm_limit_kib" =~ ^[1-9][0-9]*$ ]] \
        || (( lean_vm_limit_kib < minimum_vm_limit_kib )); then
      echo "H100_LEAN_VM_LIMIT_KIB must be an integer of at least 12582912" >&2
      exit 64
    fi
    applied_vm_limit_kib="$(
      ulimit -v "$lean_vm_limit_kib" 2>/dev/null
      ulimit -v
    )" || {
      echo "cannot establish the Lean-only virtual-memory limit" >&2
      exit 69
    }
    if [[ ! "$applied_vm_limit_kib" =~ ^[0-9]+$ ]] \
        || (( applied_vm_limit_kib > lean_vm_limit_kib )); then
      echo "the requested Lean-only virtual-memory limit was not applied" >&2
      exit 69
    fi
    lean_memory_mode="lean_only_rlimit_as"
    lean_memory_detail="RLIMIT_AS_KiB=${lean_vm_limit_kib}"
  fi
fi

mkdir -p "$output_dir"
{
  echo "mode=${lean_memory_mode}"
  echo "detail=${lean_memory_detail}"
  echo "Lean and Lake run serially with -j1; Lean also uses -M8192."
  echo "The RLIMIT_AS fallback, when selected, applies only to the Lean build."
} >"${output_dir}/memory-policy.txt"
"${repo_root}/tools/capture_environment.sh" \
  "${output_dir}/environment.txt"

native_output="${output_dir}/native"
H100_BUILD_JOBS=1 "${repo_root}/tools/run_h100_native_validation.sh" \
  --build-dir "$build_dir" \
  --output-dir "$native_output" \
  --primitive-count "$primitive_count" \
  --expression-count "$expression_count" \
  --expression-program-count "$expression_program_count" \
  --device "$device" \
  2>&1 | tee "${output_dir}/native-validation.log"

case "$lean_memory_mode" in
  user_systemd_cgroup)
    SPARKINTERVAL_MEMORY_HIGH="$lean_memory_high" \
      SPARKINTERVAL_MEMORY_MAX="$lean_memory_max" \
      SPARKINTERVAL_SWAP_MAX="$lean_swap_max" \
      SPARKINTERVAL_TASKS_MAX="$lean_tasks_max" \
      SPARKINTERVAL_RUNTIME_MAX="$lean_runtime_max" \
      python3 "${repo_root}/tools/safe_lake_build.py" \
        --target sparkinterval-gen \
        2>&1 | tee "${output_dir}/lean-generator-build.log"
    ;;
  finite_container_cgroup)
    SPARKINTERVAL_ALLOW_UNCAPPED=1 \
      python3 "${repo_root}/tools/safe_lake_build.py" \
        --target sparkinterval-gen \
        2>&1 | tee "${output_dir}/lean-generator-build.log"
    ;;
  lean_only_rlimit_as)
    (
      ulimit -v "$lean_vm_limit_kib"
      applied_vm_limit_kib="$(ulimit -v)"
      if [[ ! "$applied_vm_limit_kib" =~ ^[0-9]+$ ]] \
          || (( applied_vm_limit_kib > lean_vm_limit_kib )); then
        echo "the requested Lean-only virtual-memory limit was not applied" >&2
        exit 69
      fi
      SPARKINTERVAL_ALLOW_UNCAPPED=1 \
        python3 "${repo_root}/tools/safe_lake_build.py" \
          --target sparkinterval-gen
    ) 2>&1 | tee "${output_dir}/lean-generator-build.log"
    ;;
  *)
    echo "internal error: unknown Lean memory mode" >&2
    exit 70
    ;;
esac
cmake --build "$build_dir" \
  --target sparkinterval-generated-driver \
  --parallel 1 \
  2>&1 | tee "${output_dir}/generated-driver-build.log"

mkdir -p "${output_dir}/generated"
python3 "${repo_root}/tools/run_generated_ptx_conformance.py" \
  --generator "${repo_root}/.lake/build/bin/sparkinterval-gen" \
  --driver "${build_dir}/sparkinterval-generated-driver" \
  --target sm_90 \
  --count "$generated_count" \
  --work-dir "${output_dir}/generated/work" \
  >"${output_dir}/generated/report.json" \
  2>"${output_dir}/generated/run.log"

python3 "${repo_root}/tools/run_zeta_poc.py" run \
  --target-profile h100_sm90 \
  --executable "${build_dir}/sparkinterval-h100-expression-batch" \
  --work-dir "${output_dir}/real-zeta" \
  --s 2 \
  --terms "$zeta_terms" \
  >"${output_dir}/real-zeta-run-receipt.json"
python3 "${repo_root}/tools/run_zeta_poc.py" verify \
  "${output_dir}/real-zeta" \
  >"${output_dir}/real-zeta-verification-receipt.json"

python3 - \
  "${native_output}/primitive-report.json" \
  "${native_output}/expression-report.json" \
  "${output_dir}/generated/report.json" \
  "${output_dir}/real-zeta-verification-receipt.json" \
  "${output_dir}/summary.json" <<'PY'
import json
import pathlib
import sys

primitive, expression, generated, zeta, destination = map(pathlib.Path, sys.argv[1:])
reports = {
    "primitive": json.loads(primitive.read_text(encoding="utf-8")),
    "expression": json.loads(expression.read_text(encoding="utf-8")),
    "generated": json.loads(generated.read_text(encoding="utf-8")),
    "real_zeta": json.loads(zeta.read_text(encoding="utf-8")),
}
accepted = {
    name: report.get("accepted") is True for name, report in reports.items()
}
summary = {
    "schema_version": 1,
    "kind": "sparkinterval_h100_full_local_validation",
    "target": "sm_90",
    "evidence_class": "local_unattested",
    "accepted": all(accepted.values()),
    "components": accepted,
    "limitations": [
        "No NVIDIA confidential-computing evidence was collected or verified.",
        "The real-zeta tutorial evaluates zeta(2); it does not locate or count zeros.",
        "Conformance tests are execution evidence, not a universal PTX-to-hardware proof.",
    ],
}
destination.write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
if not summary["accepted"]:
    raise SystemExit("one or more H100 validation components did not pass")
PY

(
  cd "$output_dir"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    >SHA256SUMS
  sha256sum --check SHA256SUMS >/dev/null
)

echo "Full H100 local validation passed: ${output_dir}"
echo "Evidence class: local_unattested"
