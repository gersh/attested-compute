// The interval primitive is target-neutral CUDA.  Keep the H100 build on the
// same reviewed implementation rather than maintaining a second arithmetic
// kernel.  The offline pipeline compiles this translation unit specifically
// for compute_90/sm_90 and records both this wrapper and the included source.
#include "../../src/interval_batch_kernel.cu"
