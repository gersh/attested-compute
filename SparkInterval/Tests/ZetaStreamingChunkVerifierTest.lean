import SparkInterval.Zeta.StreamingChunkVerifier

/-! Kernel-reducible regression tests for independently checked endpoint
chunks and their pure composition into `ChunkCertificate`. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaStreamingChunkVerifier

open SparkInterval.Certificate
open SparkInterval.Zeta

private def twoRootFunction (x : ℝ) : ℝ :=
  (x + 2) * (x - 2)

private def leftBracket : RationalBracket := {
  lower := -3
  upper := -1
  lowerValue := ⟨5, 5⟩
  upperValue := ⟨-3, -3⟩
}

private def rightBracket : RationalBracket := {
  lower := 1
  upper := 3
  lowerValue := ⟨-3, -3⟩
  upperValue := ⟨5, 5⟩
}

private def leftChunk : RationalEndpointChunk := {
  spanLower := -4
  spanUpper := 0
  entries := [leftBracket]
}

private def rightChunk : RationalEndpointChunk := {
  spanLower := 0
  spanUpper := 4
  entries := [rightBracket]
}

private def source : List RationalEndpointChunk := [leftChunk, rightChunk]

example : checkEndpointChunkStream source = true := by decide

/-- A gap between advertised spans is rejected even if both local endpoint
families are valid. -/
example : checkEndpointChunkStream
    [leftChunk, { rightChunk with spanLower := 1 / 2 }] = false := by
  decide_cbv

/-- Chunk-sequence resumption retains only the preceding upper boundary and is
definitionally equivalent to checking the concatenated list. -/
example :
    (runEndpointChunkStream {} [leftChunk] >>= fun state =>
      runEndpointChunkStream state [rightChunk]) =
      runEndpointChunkStream {} source := by
  simpa [source] using
    (runEndpointChunkStream_append ({} : EndpointChunkStreamState)
      [leftChunk] [rightChunk]).symm

private theorem encloses
    (chunk : Fin source.length)
    (entry : Fin (source.get chunk).entries.length) :
    ((source.get chunk).family.entries entry).EnclosesEndpoints
      twoRootFunction := by
  fin_cases chunk <;> fin_cases entry <;>
    constructor <;> constructor <;>
    norm_num [source, leftChunk, rightChunk, leftBracket, rightBracket,
      RationalEndpointChunk.family, endpointFamilyOfList,
      twoRootFunction, RatInterval.ContainsReal]

private noncomputable def checked :
    CheckedEndpointChunkCertificate twoRootFunction source :=
  Classical.choice
    (exists_checkedEndpointChunkCertificate (by decide) encloses)

example : checked.certificate.totalCount = 2 := by
  rw [checked.totalCount_eq]
  decide_cbv

example :
    (checked.certificate.chunks (0 : Fin 2)).span.upper =
      (checked.certificate.chunks (1 : Fin 2)).span.lower := by
  exact checked.certificate.contiguousSpans (by decide)

/-- The composition theorem uses no project-specific trust axiom.  Finite
witness selection may use Lean's standard classical choice. -/
theorem checkedChunksExist :
    Nonempty (CheckedEndpointChunkCertificate twoRootFunction source) :=
  exists_checkedEndpointChunkCertificate (by decide) encloses

#print axioms checkedChunksExist

end SparkInterval.Tests.ZetaStreamingChunkVerifier
