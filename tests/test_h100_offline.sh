#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="${1:-${repo_root}/build/h100-offline-test}"
offline_dir="${test_root}/offline"
mock_file="${test_root}/mock/mock-evidence.json"
cc_dir="${test_root}/cc"

"${repo_root}/tools/build_h100_offline.sh" "$offline_dir"

for required in \
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
  SHA256SUMS; do
  test -f "${offline_dir}/${required}"
done

(
  cd "$offline_dir"
  sha256sum --check SHA256SUMS
)

for instruction in \
  add.rm.f64 add.rp.f64 \
  sub.rm.f64 sub.rp.f64 \
  mul.rm.f64 mul.rp.f64 \
  div.rm.f64 div.rp.f64; do
  if ! grep -Fq "$instruction" "${offline_dir}/h100_rounding_probe.compute_90.ptx"; then
    echo "missing expected PTX instruction: $instruction" >&2
    exit 1
  fi
done

python3 - "${offline_dir}/h100_rounding_probe.compute_90.ptx.json" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["passed"] is True
assert report["targets"] == ["sm_90"]
assert not report["unexpected_instructions"]
assert not report["incorrect_required_counts"]
PY
grep -Fq "h100_directed_rounding_probe" \
  "${offline_dir}/h100_rounding_probe.sm_90.sass"

python3 - "${offline_dir}/h100_rounding_probe.sm_90.sass.json" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["passed"] is True
assert report["targets"] == ["sm_90"]
assert "h100_directed_rounding_probe" in report["functions"]
assert not any(report["findings"].values())
PY

python3 - "$offline_dir/manifest.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
assert manifest["evidence_class"] == "offline_device_build"
assert manifest["target"]["cubin_target"] == "sm_90"
assert manifest["target"]["compute_capability"] == "9.0"
assert manifest["build_host"]["device_code_only"] is True
assert manifest["build_host"]["host_executable_built"] is False
assert manifest["build_host"]["host_runner_source_syntax_checked"] is True
assert manifest["host_runner_source"]["file"].endswith("h100_probe_runner.cpp")
assert manifest["execution"]["executed"] is False
assert manifest["execution"]["result"] is None
assert manifest["production_attestation"]["present"] is False
PY

"${repo_root}/tools/run_h100_mock.sh" \
  --build-dir "$offline_dir" \
  --output "$mock_file" \
  --nonce "offline-test-nonce"

python3 - "$mock_file" <<'PY'
import json
import pathlib
import sys

evidence = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert evidence["evidence_class"] == "mock_attested"
assert evidence["production_acceptable"] is False
assert evidence["cryptographically_authenticated"] is False
assert evidence["hardware_attestation_present"] is False
assert evidence["h100_execution_claimed"] is False
assert evidence["algorithm_executed"] is False
assert evidence["synthetic_result"]["status"] == "not_executed"
assert evidence["synthetic_result"]["result"] is None
PY

set +e
"${repo_root}/tools/run_h100_cc_acceptance.sh" \
  --output-dir "$cc_dir" \
  --artifact-manifest "$offline_dir/manifest.json" \
  >/dev/null
cc_status=$?
set -e
if [[ $cc_status -ne 78 ]]; then
  echo "NVIDIA CC provider stub returned $cc_status; expected fail-closed status 78" >&2
  exit 1
fi

python3 - "$cc_dir/acceptance-checklist.json" <<'PY'
import json
import pathlib
import sys

checklist = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert checklist["provider_status"] == "NOT_IMPLEMENTED"
assert checklist["fail_closed"] is True
assert checklist["evidence_class"] == "none"
assert checklist["production_evidence_emitted"] is False
PY

echo "H100 offline artifact and fail-closed attestation tests passed."
