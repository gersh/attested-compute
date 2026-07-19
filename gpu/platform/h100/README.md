# H100 offline device artifact

`h100_rounding_probe.cu` is a representative binary64 directed-rounding
kernel. The offline build compiles it twice:

- PTX for `compute_90`, so the virtual-ISA rounding instructions can be
  inspected.
- A cubin for `sm_90`, so the exact device image and its SASS disassembly can
  be hashed before access to an H100.

`h100_probe_runner.cpp` is a portable CUDA Driver API acceptance runner for the
fixed kernel. The offline build checks that source against the installed CUDA
headers with strict C++ warnings, but intentionally emits no host executable.
A cubin or syntax check produced on the DGX Spark's `aarch64` host is not an
H100 execution record and not an `x86_64` H100 host program.
