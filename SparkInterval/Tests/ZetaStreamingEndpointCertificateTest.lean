import SparkInterval.Zeta.StreamingEndpointCertificate

/-! Kernel-reducible tests for the one-pass endpoint stream checker. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaStreamingEndpointCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def bracket (lower upper : ℚ) : RationalBracket := {
  lower
  upper
  lowerValue := ⟨-2, -1⟩
  upperValue := ⟨1, 2⟩
}

private def first : RationalBracket := bracket (-5) (-4)
private def second : RationalBracket := bracket (-3) (-2)
private def third : RationalBracket := bracket 0 1
private def entries : List RationalBracket := [first, second, third]

example : checkEndpointStream entries = true := by decide

example : (endpointFamilyOfList entries).check = true := by
  exact checkEndpointStream_familyCheck (by decide)

example :
    ((endpointFamilyOfList entries).entries
      ⟨0, by simp [entries]⟩).upper <
      ((endpointFamilyOfList entries).entries
        ⟨2, by simp [entries]⟩).lower := by
  apply checkEndpointStream_allPairs (by decide)
  decide

/-- A local interval containing zero is rejected. -/
example :
    checkEndpointStream
      [{ first with lowerValue := ⟨-1, 0⟩ }, second] = false := by
  decide

/-- Locally valid but overlapping consecutive brackets are rejected. -/
example : checkEndpointStream [first, bracket (-9 / 2) (-7 / 2)] = false := by
  decide_cbv

/-- Passing the returned state across two chunks is exactly concatenated
checking and retains only the final previous bracket. -/
example :
    (runEndpointChunk {} [first, second] >>= fun state =>
      runEndpointChunk state [third]) = runEndpointChunk {} entries := by
  simpa [entries] using
    (runEndpointChunk_append ({} : EndpointStreamState)
      [first, second] [third]).symm

theorem acceptedStreamGivesFamily
    {candidate : List RationalBracket}
    (hcheck : checkEndpointStream candidate = true) :
    (endpointFamilyOfList candidate).IsValid :=
  checkEndpointStream_isValid hcheck

#print axioms acceptedStreamGivesFamily

end SparkInterval.Tests.ZetaStreamingEndpointCertificate
