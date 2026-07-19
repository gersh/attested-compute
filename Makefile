.PHONY: all lean probe primitive-conformance expression-conformance python-test h100-offline h100-test test audit clean

all: lean probe

lean:
	lake build

probe:
	cmake -S . -B build/dgx-spark -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
	cmake --build build/dgx-spark --parallel

primitive-conformance: probe
	python3 tools/run_primitive_conformance.py --count 10000

expression-conformance: probe
	python3 tools/run_expression_conformance.py --count 10000

python-test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

h100-offline:
	./tools/build_h100_offline.sh

h100-test:
	./tests/test_h100_offline.sh

test: all
	ctest --test-dir build/dgx-spark --output-on-failure
	python3 -m unittest discover -s tests -p 'test_*.py' -v

audit: lean
	./tools/audit_axioms.sh

clean:
	@echo "Build outputs are intentionally not removed automatically."
