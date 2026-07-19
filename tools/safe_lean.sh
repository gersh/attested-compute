#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
lean_memory_mb="${SPARKINTERVAL_LEAN_MEMORY_MB:-8192}"

if [[ ! "${lean_memory_mb}" =~ ^[1-9][0-9]*$ ]]; then
  echo "SPARKINTERVAL_LEAN_MEMORY_MB must be a positive integer" >&2
  exit 2
fi

for argument in "$@"; do
  case "${argument}" in
    -j*|-M*)
      cat >&2 <<'EOF'
safe_lean.sh owns Lean's -j and -M resource options; pass neither option in
the input arguments. Use SPARKINTERVAL_LEAN_MEMORY_MB to change the
per-process memory limit deliberately. Parallel Lean execution is unsupported.
EOF
      exit 2
      ;;
  esac
done

cd "${project_root}"
exec "${script_dir}/with_memory_limit.sh" \
  lake env lean -j1 "-M${lean_memory_mb}" "$@"
