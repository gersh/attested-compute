#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="${1:-${repo_root}/build/h100-interval-batch-offline-test}"
offline_dir="${test_root}/offline"

"${repo_root}/tools/build_h100_interval_batch_offline.sh" "$offline_dir"

for required in \
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
  count="$(grep -Ec "^[[:space:]]*${instruction//./\.}[[:space:]]" \
    "${offline_dir}/h100_interval_batch.compute_90.ptx")"
  if [[ "$count" -ne 1 ]]; then
    echo "expected one PTX $instruction instruction, found $count" >&2
    exit 1
  fi
done

python3 - "${offline_dir}/h100_interval_batch.compute_90.ptx.json" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "add.rm.f64", "add.rp.f64", "sub.rm.f64", "sub.rp.f64",
    "mul.rm.f64", "mul.rp.f64", "div.rm.f64", "div.rp.f64",
}
assert report["audit_kind"] == "h100_interval_batch_directed_ptx"
assert report["passed"] is True
assert report["targets"] == ["sm_90"]
assert set(report["required_directed_instruction_counts"]) == required
assert set(report["required_directed_instruction_counts"].values()) == {1}
assert report["incorrect_directed_instruction_counts"] == {}
assert report["unexpected_f64_arithmetic"] == []
assert len(report["interval_batch_entries"]) == 1
PY

grep -Fq ".target" "${offline_dir}/h100_interval_batch.sm_90.sass"
grep -Fq "sm_90" "${offline_dir}/h100_interval_batch.sm_90.sass"
grep -Fq "interval_batch_kernel" \
  "${offline_dir}/h100_interval_batch.sm_90.sass"

python3 - "${offline_dir}/h100_interval_batch.sm_90.sass.json" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["audit_kind"] == "sass_static_inspection"
assert report["passed"] is True
assert report["targets"] == ["sm_90"]
assert not any(report["findings"].values())
permitted = set(report["permitted_compiler_division_lowering"])
assert "MUFU.RCP64H" in permitted
assert any(item.startswith("DFMA") for item in permitted)
PY

python3 - "${offline_dir}/h100_interval_batch.manifest.json" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
root = manifest_path.parent
assert manifest["schema_version"] == "gpu-prover.h100-interval-batch-offline.v1"
assert manifest["evidence_class"] == "offline_static_validation"
assert manifest["target"]["compute_capability"] == "9.0"
assert manifest["target"]["ptx_target"] == "compute_90"
assert manifest["target"]["cubin_target"] == "sm_90"
assert manifest["algorithm"]["operation_set"] == ["add", "sub", "mul", "div"]
assert manifest["algorithm"]["rounding_modes_per_operation"] == [
    "round_down", "round_up"
]
assert manifest["build_host"]["device_code_only"] is True
assert manifest["build_host"]["host_executable_built"] is False
assert manifest["build_host"]["host_runner_source_syntax_checked"] is True
assert manifest["build_host"]["h100_presence_queried"] is False
assert manifest["build_host"]["h100_execution_attempted"] is False
assert manifest["execution"] == {
    "executed": False, "execution_device": None, "result": None
}
assert manifest["production_attestation"] == {"present": False, "provider": None}
assert any("returned any arithmetic result" in item for item in manifest["excluded_claims"])
assert any("hardware-attested" in item for item in manifest["excluded_claims"])
for item in manifest["artifacts"].values():
    path = root / item["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
PY

# The directed-operation audit must fail if one required mode is absent.
bad_ptx="${test_root}/missing-add-rp.ptx"
bad_report="${test_root}/missing-add-rp.json"
sed 's/add\.rp\.f64/add\.rn\.f64/' \
  "${offline_dir}/h100_interval_batch.compute_90.ptx" >"$bad_ptx"
set +e
python3 "${repo_root}/gpu/platform/h100/h100_interval_batch_ptx_audit.py" \
  "$bad_ptx" "$bad_report" --target sm_90 >/dev/null 2>&1
audit_status=$?
set -e
if [[ $audit_status -eq 0 ]]; then
  echo "PTX audit accepted an artifact missing add.rp.f64" >&2
  exit 1
fi

python3 - "$bad_report" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["passed"] is False
assert report["incorrect_directed_instruction_counts"]["add.rp.f64"] == 0
assert report["unexpected_f64_arithmetic"] == ["add.rn.f64"]
PY

echo "H100 interval-batch offline compile/static-validation tests passed."
echo "No H100 execution or attestation was attempted or claimed."
