# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

.PHONY: all lean probe primitive-conformance expression-conformance python-test tg-test tg-benchmark tg-cdem-abel tg-cdem-chunks h100-offline h100-test test audit clean

CMAKE_BUILD_JOBS ?= 1

all: lean probe

lean:
	./tools/safe_lake_build.py

probe:
	./tools/with_memory_limit.sh cmake -S . -B build/dgx-spark -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
	./tools/with_memory_limit.sh cmake --build build/dgx-spark --parallel "$(CMAKE_BUILD_JOBS)"

primitive-conformance: probe
	python3 tools/run_primitive_conformance.py --count 10000

expression-conformance: probe
	python3 tools/run_expression_conformance.py --count 10000

python-test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

tg-test: probe
	python3 -m unittest discover -s tests -p 'test_tg_*.py' -v
	./tools/with_memory_limit.sh ctest --test-dir build/dgx-spark \
		-R '^tg_' --parallel 1 --output-on-failure

tg-benchmark: probe
	python3 tools/benchmark_tg_verifiers.py --psi-limit 100000 --pretty

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
	./tools/audit_axioms.sh

clean:
	@echo "Build outputs are intentionally not removed automatically."
