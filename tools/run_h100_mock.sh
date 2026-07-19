#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="${repo_root}/build/h100-offline"
output_file="${repo_root}/build/h100-mock/mock-evidence.json"
nonce="development-only-nonce"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-dir)
      build_dir="$2"
      shift 2
      ;;
    --output)
      output_file="$2"
      shift 2
      ;;
    --nonce)
      nonce="$2"
      shift 2
      ;;
    -h|--help)
      echo "usage: $0 [--build-dir DIR] [--output FILE] [--nonce TEXT]"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

manifest="${build_dir}/manifest.json"
if [[ ! -f "$manifest" ]]; then
  echo "offline H100 manifest not found: $manifest" >&2
  echo "run tools/build_h100_offline.sh first" >&2
  exit 66
fi

python3 "${repo_root}/attestation/mock_attestation.py" \
  --manifest "$manifest" \
  --output "$output_file" \
  --nonce "$nonce"

echo "Wrote development-only mock evidence to $output_file"
echo "It is not production acceptable and makes no H100 execution claim."
