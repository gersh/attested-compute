#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="${repo_root}/build/h100-native"
output_dir="${repo_root}/build/h100-native-validation"
primitive_count=10000
expression_count=10000
expression_program_count=8
device=0
build_jobs="${H100_BUILD_JOBS:-1}"

usage() {
  cat <<'EOF'
usage: tools/run_h100_native_validation.sh [OPTIONS]

Build and validate the strict native-host H100 runners. This command requires
exactly one visible NVIDIA H100 with compute capability 9.0. It produces local,
unattested execution records; it does not collect confidential-computing evidence.

Options:
  --build-dir DIR                 CMake build directory
  --output-dir DIR                retained validation artifacts
  --primitive-count N             random rows per primitive operation (default 10000)
  --expression-count N            randomized expression/row cases (default 10000)
  --expression-program-count N    randomized shared programs (default 8)
  --device N                      CUDA device index (default 0)
  --help                          show this help

Set H100_BUILD_JOBS to control build parallelism; it defaults to 1.
EOF
}

require_value() {
  local option="$1"
  local remaining="$2"
  if [[ "$remaining" -lt 2 ]]; then
    echo "$option requires a value" >&2
    exit 64
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-dir)
      require_value "$1" "$#"
      build_dir="$2"
      shift 2
      ;;
    --output-dir)
      require_value "$1" "$#"
      output_dir="$2"
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

for value_name in primitive_count expression_count expression_program_count build_jobs; do
  value="${!value_name}"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "$value_name must be a positive integer" >&2
    exit 64
  fi
done
if [[ ! "$device" =~ ^[0-9]+$ ]]; then
  echo "device must be a nonnegative integer" >&2
  exit 64
fi

cmake -S "$repo_root" -B "$build_dir" \
  -DSPARKINTERVAL_BUILD_H100_NATIVE=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" \
  --target sparkinterval-h100-native \
  --parallel "$build_jobs"
ctest --test-dir "$build_dir" \
  -R '^h100_native_cli_offline$' \
  --output-on-failure

probe_runner="${build_dir}/sparkinterval-h100-probe-runner"
primitive_runner="${build_dir}/sparkinterval-h100-interval-batch"
expression_runner="${build_dir}/sparkinterval-h100-expression-batch"
probe_cubin="${build_dir}/h100/h100_rounding_probe.sm_90.cubin"
cuobjdump="${CUOBJDUMP:-}"
if [[ -z "$cuobjdump" ]]; then
  cuobjdump="$(command -v cuobjdump || true)"
fi
if [[ -z "$cuobjdump" && -x /usr/local/cuda/bin/cuobjdump ]]; then
  cuobjdump=/usr/local/cuda/bin/cuobjdump
fi

for executable in "$probe_runner" "$primitive_runner" "$expression_runner"; do
  if [[ ! -x "$executable" ]]; then
    echo "missing H100 native executable: $executable" >&2
    exit 66
  fi
done
if [[ ! -f "$probe_cubin" ]]; then
  echo "missing H100 probe cubin: $probe_cubin" >&2
  exit 66
fi
if [[ -z "$cuobjdump" || ! -x "$cuobjdump" ]]; then
  echo "cuobjdump is unavailable; set CUOBJDUMP to its absolute path" >&2
  exit 69
fi

mkdir -p \
  "$output_dir/static" \
  "$output_dir/primitive" \
  "$output_dir/expression"

"$cuobjdump" --dump-sass "$probe_cubin" \
  >"${output_dir}/static/probe.sass"
"${repo_root}/tools/inspect_sass.sh" \
  "${output_dir}/static/probe.sass" \
  "${output_dir}/static/probe.sass.json" \
  --allow-division-lowering

"$cuobjdump" --dump-ptx "$primitive_runner" \
  >"${output_dir}/static/primitive.ptx"
python3 "${repo_root}/gpu/platform/h100/h100_interval_batch_ptx_audit.py" \
  "${output_dir}/static/primitive.ptx" \
  "${output_dir}/static/primitive.ptx.json" \
  --target sm_90
"$cuobjdump" --dump-sass "$primitive_runner" \
  >"${output_dir}/static/primitive.sass"
"${repo_root}/tools/inspect_sass.sh" \
  "${output_dir}/static/primitive.sass" \
  "${output_dir}/static/primitive.sass.json" \
  --allow-division-lowering

"$probe_runner" --cubin "$probe_cubin" \
  | tee "${output_dir}/probe-result.json"

python3 "${repo_root}/tools/run_primitive_conformance.py" \
  --executable "$primitive_runner" \
  --count "$primitive_count" \
  --device "$device" \
  --work-dir "${output_dir}/primitive" \
  >"${output_dir}/primitive-report.json"

python3 "${repo_root}/tools/run_expression_conformance.py" \
  --executable "$expression_runner" \
  --target sm_90 \
  --count "$expression_count" \
  --program-count "$expression_program_count" \
  --device "$device" \
  --work-dir "${output_dir}/expression" \
  >"${output_dir}/expression-report.json"

echo "H100 native local validation passed."
echo "Artifacts: $output_dir"
echo "Evidence class: local_unattested (no confidential-computing evidence collected)."
