#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${repo_root}/build/h100-cc-acceptance"
artifact_manifest="${repo_root}/build/h100-offline/manifest.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      output_dir="$2"
      shift 2
      ;;
    --artifact-manifest)
      artifact_manifest="$2"
      shift 2
      ;;
    -h|--help)
      echo "usage: $0 [--output-dir DIR] [--artifact-manifest FILE]"
      echo "This is a fail-closed production-provider placeholder."
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

mkdir -p "$output_dir"
checklist="${output_dir}/acceptance-checklist.json"

stub_args=()
if [[ -f "$artifact_manifest" ]]; then
  stub_args+=(--artifact-manifest "$artifact_manifest")
fi

set +e
python3 "${repo_root}/attestation/nvidia_cc_provider_stub.py" \
  "${stub_args[@]}" \
  >"$checklist"
status=$?
set -e

if [[ $status -eq 0 ]]; then
  echo "fail-closed NVIDIA CC stub unexpectedly returned success" >&2
  exit 79
fi

cat "$checklist"
echo "Production H100 CC acceptance is unavailable; failed closed with status $status." >&2
exit "$status"
