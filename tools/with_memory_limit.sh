#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

if [[ "$#" -eq 0 ]]; then
  echo "usage: $0 COMMAND [ARGUMENT ...]" >&2
  exit 2
fi
if [[ -n "${SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE:-}" ]]; then
  cat >&2 <<'EOF'
error: nested memory wrappers are not supported.
Invoke safe_lake_build.py, safe_lean.sh, build_dgx_spark.sh, or the existing
with_memory_limit.sh command directly; wrapping one of them again would
contend on the same non-reentrant repository lock.
EOF
  exit 75
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
caller_dir="$(pwd -P)"
command_name="$1"
shift
if [[ "${command_name}" == */* ]]; then
  if [[ "${command_name}" == /* ]]; then
    command_path="${command_name}"
  else
    command_path="${caller_dir}/${command_name}"
  fi
else
  command_path="$(type -P -- "${command_name}" || true)"
  if [[ -z "${command_path}" ]]; then
    echo "error: command not found: ${command_name}" >&2
    exit 127
  fi
fi
if [[ ! -x "${command_path}" ]]; then
  echo "error: command is not executable: ${command_name}" >&2
  exit 126
fi
command=("${command_path}" "$@")
lake_serial_plan_required=0
if [[ "$(basename -- "${command_path}")" == "lake" ]]; then
  lake_expect_option_value=0
  lake_options_finished=0
  for argument in "$@"; do
    if [[ "${lake_expect_option_value}" == "1" ]]; then
      lake_expect_option_value=0
      continue
    fi
    if [[ "${lake_options_finished}" == "0" ]]; then
      case "${argument}" in
        --)
          lake_options_finished=1
          continue
          ;;
        --dir|--file|--packages|-d|-f|-K)
          lake_expect_option_value=1
          continue
          ;;
        -*)
          continue
          ;;
      esac
    fi
    # The first non-option argument is Lake's command. Arguments after it
    # belong to that command (for example `lake env lean ... build`).
    if [[ "${lake_options_finished}" == "1" || "${argument}" != -* ]]; then
      case "${argument}" in
        build|query|exe|test|lint|run|script|shake)
          lake_serial_plan_required=1
          ;;
      esac
      break
    fi
  done
fi
if [[ "${lake_serial_plan_required}" == "1" ]]; then
  serial_step_authorized=0
  plan_lock_fd="${SPARKINTERVAL_PLAN_LOCK_FD:-}"
  expected_plan_lock="${project_root}/.lake/sparkinterval-safe-plan.lock"
  if [[ "${SPARKINTERVAL_SERIAL_LAKE_STEP:-0}" == "1" &&
        "${plan_lock_fd}" =~ ^[0-9]+$ &&
        -e "/proc/$$/fd/${plan_lock_fd}" ]]; then
    inherited_plan_lock="$(readlink -f -- "/proc/$$/fd/${plan_lock_fd}" 2>/dev/null || true)"
    expected_plan_lock="$(readlink -f -- "${expected_plan_lock}" 2>/dev/null || true)"
    if [[ -n "${inherited_plan_lock}" &&
          "${inherited_plan_lock}" == "${expected_plan_lock}" ]]; then
      serial_step_authorized=1
    fi
  fi
  if [[ "${serial_step_authorized}" != "1" ]]; then
    cat >&2 <<'EOF'
error: direct Lake builds and other build-producing commands can schedule
several stale modules concurrently.
Use tools/safe_lake_build.py [MODULE ...] (or its --target option), which
topologically builds one local module at a time inside this memory wrapper.
The planner authorizes each step with its inherited complete-plan lock;
setting SPARKINTERVAL_SERIAL_LAKE_STEP manually is not sufficient.
EOF
    exit 64
  fi
fi
memory_high="${SPARKINTERVAL_MEMORY_HIGH:-10G}"
memory_max="${SPARKINTERVAL_MEMORY_MAX:-12G}"
swap_max="${SPARKINTERVAL_SWAP_MAX:-2G}"
tasks_max="${SPARKINTERVAL_TASKS_MAX:-32}"
runtime_max="${SPARKINTERVAL_RUNTIME_MAX:-30min}"
lock_file="${SPARKINTERVAL_BUILD_LOCK:-${project_root}/.lake/sparkinterval-memory-safe.lock}"

if [[ "${lock_file}" != /* ]]; then
  lock_file="${caller_dir}/${lock_file}"
fi
lock_dir="$(dirname -- "${lock_file}")"
mkdir -p "${lock_dir}"
lock_dir="$(cd -- "${lock_dir}" && pwd -P)"
lock_file="${lock_dir}/$(basename -- "${lock_file}")"

if ! command -v flock >/dev/null 2>&1; then
  echo "error: flock is required to serialize memory-capped project commands" >&2
  exit 1
fi
flock_path="$(command -v flock)"

systemd_run_path="$(command -v systemd-run || true)"
systemctl_path="$(command -v systemctl || true)"
if [[ -n "${systemd_run_path}" && -n "${systemctl_path}" ]] &&
    "${systemctl_path}" --user show-environment >/dev/null 2>&1; then
  # A transient service otherwise inherits the user manager's often-stale
  # environment rather than this shell's.  Preserve only build/toolchain
  # search settings; do not copy the complete environment (which can contain
  # credentials).  NAME without '=VALUE' asks systemd-run to copy the caller's
  # current value.
  environment_args=()
  for variable in \
      PATH LD_LIBRARY_PATH LIBRARY_PATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH \
      PKG_CONFIG_PATH CMAKE_PREFIX_PATH CMAKE_GENERATOR CMAKE_TOOLCHAIN_FILE \
      CUDA_HOME CUDA_PATH CUDA_ROOT CC CXX CUDACXX CUDAHOSTCXX NVCC \
      NVDISASM CUOBJDUMP ELAN_HOME LAKE_HOME LEAN_PATH LEAN_SRC_PATH \
      LEAN_NUM_THREADS \
      LEAN_SYSROOT PYTHONPATH VIRTUAL_ENV CUDA_VISIBLE_DEVICES \
      CUDA_DEVICE_ORDER TMPDIR TMP TEMP XDG_CACHE_HOME; do
    if [[ -v "${variable}" ]]; then
      environment_args+=(--setenv="${variable}")
    fi
  done

  # Use an explicit unit name so an interrupt handler can stop the complete
  # cgroup.  Without this cleanup, killing systemd-run can leave the detached
  # compiler service alive and holding the repository lock.
  unit_name="sparkinterval-memory-safe-${UID}-${BASHPID}-${RANDOM}.service"
  runner_pid=""
  stop_unit_for_signal() {
    local signal_name="$1"
    trap - HUP INT TERM
    if [[ -n "${runner_pid}" ]]; then
      kill -TERM "${runner_pid}" >/dev/null 2>&1 || true
    fi
    "${systemctl_path}" --user stop "${unit_name}" >/dev/null 2>&1 || true
    kill -s "${signal_name}" "$$"
  }
  trap 'stop_unit_for_signal HUP' HUP
  trap 'stop_unit_for_signal INT' INT
  trap 'stop_unit_for_signal TERM' TERM

  set +e
  "${systemd_run_path}" --user --quiet --pipe --wait --collect \
      --unit="${unit_name}" --expand-environment=no \
      --service-type=exec --working-directory="${project_root}" \
      "${environment_args[@]}" \
      --setenv="SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE=${unit_name}" \
      --property="MemoryAccounting=yes" \
      --property="MemoryHigh=${memory_high}" \
      --property="MemoryMax=${memory_max}" \
      --property="MemorySwapMax=${swap_max}" \
      --property="TasksMax=${tasks_max}" \
      --property="OOMPolicy=kill" \
      --property="KillMode=control-group" \
      --property="TimeoutStopSec=10s" \
      --property="RuntimeMaxSec=${runtime_max}" \
      -- "${flock_path}" --exclusive "${lock_file}" "${command[@]}" <&0 &
  runner_pid=$!
  wait "${runner_pid}"
  command_status=$?
  set -e
  trap - HUP INT TERM
  # `systemd-run --wait` normally exits only after the service. Stop the
  # explicit unit defensively as well so an unexpected runner-side failure
  # cannot leave a detached compiler cgroup or repository lock behind.
  "${systemctl_path}" --user stop "${unit_name}" >/dev/null 2>&1 || true
  exit "${command_status}"
fi

if [[ "${SPARKINTERVAL_ALLOW_UNCAPPED:-0}" == "1" ]]; then
  echo "warning: user cgroups unavailable; running without an aggregate memory cap" >&2
  export SPARKINTERVAL_MEMORY_WRAPPER_ACTIVE="external-uncapped"
  exec "${flock_path}" --exclusive "${lock_file}" "${command[@]}"
fi

cat >&2 <<'EOF'
error: a systemd user manager is required for the aggregate memory cap.
Set SPARKINTERVAL_ALLOW_UNCAPPED=1 only when an equivalent external memory
limit is already in place. Lean's per-process -M limit remains configured in
lakefile.toml, but it cannot bound several concurrent processes collectively.
EOF
exit 1
