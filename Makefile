# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

.PHONY: all local-static lean lean-production probe primitive-conformance expression-conformance python-test tg-test tg-benchmark tg-cdem-abel tg-cdem-chunks h100-offline h100-test test audit audit-production clean

CMAKE_BUILD_JOBS ?= 1

all: lean probe

# Fast control-plane check.  This never compiles or executes a production
# worker and never opens a production certificate or architecture trace.
local-static:
	python3 -m unittest \
		tests.test_measured_worker_scope \
		tests.test_legacy_campaign_cloud_guards \
		tests.test_tg_dirichlet_direct_cli_guards \
		tests.test_direct_heavy_cli_guards \
		tests.test_memory_safe_builds \
		tests.test_tg_compact_receipt_closure \
		tests.test_tg_full_trust_boundary \
		tests.test_tg_native_family_closure \
		tests.test_sqrt218_launcher_boundary \
		tests.test_sqrt218_launcher_build \
		tests.test_sqrt218_compiler_discovery
	python3 tools/audit_local_lean_boundary.py
	python3 tools/audit_tg_compact_receipt_closure.py
	python3 tools/audit_tg_full_trust_boundary.py
	python3 tools/validate_tg_native_family_closure.py
	python3 tools/audit_lean_source.py
	python3 tools/audit_sqrt218_pure_entry_source_map.py
	python3 tools/tg_sqrt218_proof_build.py validate \
		proof_build/sqrt218/cloud-proof-build.v1.json
	python3 tools/tg_sqrt218_launcher_boundary.py \
		specifications/SQRT218_PURE_ENTRY_LAUNCHER_BOUNDARY.json
	python3 tools/tg_sqrt218_launcher_build.py validate \
		launcher_build/sqrt218/cloud-launcher-build.v1.json \
		--repository-root . --require-build-ready
	python3 tools/tg_sqrt218_compiler_discovery.py validate \
		proof_build/sqrt218-discovery/discovery.v1.json

lean:
	./tools/safe_lake_build.py

# Explicit source-materialized build for the Azure qualification lane.  This
# reaches generated production certificates and is not an ordinary local gate.
lean-production:
	./tools/safe_lake_build.py --full-production-library

probe:
	./tools/with_memory_limit.sh cmake -S . -B build/dgx-spark -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
	./tools/with_memory_limit.sh cmake --build build/dgx-spark --parallel "$(CMAKE_BUILD_JOBS)"

primitive-conformance: probe
	python3 tools/run_primitive_conformance.py --count 64

expression-conformance: probe
	python3 tools/run_expression_conformance.py --count 64

python-test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

tg-test: probe
	python3 -m unittest discover -s tests -p 'test_tg_*.py' -v
	./tools/with_memory_limit.sh ctest --test-dir build/dgx-spark \
		-R '^tg_' --parallel 1 --output-on-failure

tg-benchmark:
	python3 tools/benchmark_tg_verifiers.py --no-gpu \
		--mobius-limit 64 --exact-fraction-limit 64 --psi-limit 64 --pretty

tg-cdem-abel:
	python3 tools/tg_verify.py --pretty run-cdem-abel reference/tg_cdem_abel.cpp --threads 8 --transcript-output build/tg/cdem-abel-full.txt

tg-cdem-chunks:
	python3 tools/tg_verify.py --pretty replay-cdem-abel-chunks build/tg/cdem-abel-full.txt

h100-offline:
	./tools/build_h100_offline.sh

h100-test:
	./tests/test_h100_offline.sh

test: all
	./tools/with_memory_limit.sh ctest --test-dir build/dgx-spark --parallel 1 --output-on-failure
	python3 -m unittest discover -s tests -p 'test_*.py' -v

audit: lean
	python3 tools/audit_lean_source.py
	python3 tools/audit_local_lean_boundary.py

audit-production:
	./tools/audit_axioms.sh

clean:
	@echo "Build outputs are intentionally not removed automatically."
