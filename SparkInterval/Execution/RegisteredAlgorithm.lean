import SparkInterval.Certificate.SHA256
import SparkInterval.Execution.Statement

/-!
# Closed registry of certificate-addressable algorithm semantics

An accepted signature or hardware attestation must never be allowed to unlock
an arbitrary proposition supplied by a caller.  This module therefore uses a
closed inductive registry.  Each constructor has library-defined identity,
parsing, and mathematical execution semantics.

The first registered algorithm is an intentionally small end-to-end example:
an integer cube-accumulation loop followed by one division by three.  At its
closed registered bound, Lean proves that this machine algorithm equals the
exact rational sum

`sum (x = 0 .. upper) (x^3 / 3)`.

Adding a production algorithm requires an audited source change adding another
constructor and its fixed `Runs` equation to this closed registry.  A
certificate contains only hashes and returned bytes; a
`RegisteredInvocation` supplies their canonical preimages to Lean and checks
all of them before the trusted boundary can expose `Runs`.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

open SparkInterval.Certificate

/-- Algorithms whose execution meaning is fixed by this library.

This is deliberately not a structure with a caller-provided `Prop` field.
Such a structure would let a caller choose `False` as the alleged semantics
and would make an accepted certificate logically explosive. -/
inductive RegisteredAlgorithm where
  /-- Accumulate cubes through `upper`, then divide the total by three. -/
  | cubicSumDivThreeV1
  deriving Repr, DecidableEq, BEq

namespace RegisteredAlgorithm

/-- Canonical decimal naturals have no sign, whitespace, separators, or
leading zeroes (except for the value zero itself). -/
def parseCanonicalNat (text : String) : Option Nat := do
  let value ← text.toNat?
  if text = toString value then
    some value
  else
    none

/-- Exact mathematical meaning of the example loop.  Division is in `ℚ`, and
the upper endpoint is included. -/
def cubicSumDivThree (upper : Nat) : ℚ :=
  ∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3 / 3

/-- Executable numerator loop.  `cubicNumeratorLoop count` performs exactly
`count` iterations, adding `x^3` for `x = 0, ..., count - 1`. -/
def cubicNumeratorLoop : Nat → Nat
  | 0 => 0
  | count + 1 => cubicNumeratorLoop count + count ^ 3

/-- Executable tutorial algorithm: accumulate integer cubes and divide once at
the end.  At the registered bound, divisibility by three is proved below, so
this natural-number division agrees with exact rational pointwise division. -/
def cubicSumDivThreeMachine (upper : Nat) : Nat :=
  cubicNumeratorLoop (upper + 1) / 3

/-- Stable protocol identifier signed in `RunStatement.algorithmId`. -/
def algorithmId : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 => "sparkinterval.example.cubic-sum-div-three.v1"

/-- Canonical, human-reviewable definition bytes whose digest is signed as
`RunStatement.algorithmHash`.

This text is a protocol artifact.  Changing any execution detail requires a
new registry version and therefore a new digest. -/
def canonicalDefinition : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "sparkinterval.registered-algorithm.v1\n" ++
      "name=cubic-sum-div-three\n" ++
      "input=canonical-decimal-natural-upper-inclusive\n" ++
      "output=canonical-decimal-natural\n" ++
      "arithmetic=natural-accumulator-with-u64-proof-on-registered-domain\n" ++
      "division=natural-division-by-3-after-total\n" ++
      "semantics=loop-x-from-0-through-upper-add-x-cubed-then-divide-total"

/-- Digest of the fixed formal algorithm definition. -/
def algorithmHash (algorithm : RegisteredAlgorithm) : Digest :=
  SHA256.digestString algorithm.canonicalDefinition

/-- Canonical parameter bytes bound by the signed statement. -/
def canonicalParameters : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "{\"accumulator\":\"u64-no-wrap\",\"divide_after_sum\":true," ++
      "\"divisor\":3,\"inclusive\":true}"

/-- Canonical domain bytes bound by the signed statement. -/
def canonicalDomain : RegisteredAlgorithm → String
  | .cubicSumDivThreeV1 =>
      "{\"input\":\"nat\",\"output\":\"nat\",\"range_start\":0}"

/-- Fixed formal execution relation for every registered algorithm.

Both the input and output must use their canonical textual encodings.  The
relation states the complete algorithm result, not merely that some bytes
were returned. -/
def Runs : RegisteredAlgorithm → String → String → Prop
  | .cubicSumDivThreeV1, input, output =>
      ∃ upper result : Nat,
        parseCanonicalNat input = some upper ∧
        parseCanonicalNat output = some result ∧
        cubicSumDivThreeMachine upper = result

theorem cubicSumDivThree_runs_iff {input output : String} :
    RegisteredAlgorithm.cubicSumDivThreeV1.Runs input output ↔
      ∃ upper result : Nat,
        parseCanonicalNat input = some upper ∧
        parseCanonicalNat output = some result ∧
        cubicSumDivThreeMachine upper = result := by
  rfl

/-- A successful canonical parser result exposes the exact decimal bytes. -/
theorem eq_toString_of_parseCanonicalNat_eq_some {text : String} {value : Nat}
    (hparse : parseCanonicalNat text = some value) :
    text = toString value := by
  change text.toNat?.bind (fun parsed =>
    if text = toString parsed then some parsed else none) = some value at hparse
  rw [Option.bind_eq_some_iff] at hparse
  rcases hparse with ⟨parsed, _, hresult⟩
  split at hresult
  · next heq =>
      simp only [Option.some.injEq] at hresult
      subst parsed
      exact heq
  · simp at hresult

/-- Closed form used to reason about large bounds without reducing a
twenty-thousand-step sum inside the kernel. -/
theorem sumCubes_eq_closedForm (upper : Nat) :
    (∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3) =
      (((upper : ℚ) * ((upper : ℚ) + 1) / 2) ^ 2) := by
  induction upper with
  | zero => norm_num
  | succ upper ih =>
      rw [show upper + 1 + 1 = (upper + 1) + 1 by omega,
        Finset.sum_range_succ, ih]
      push_cast
      ring

theorem cubicSumDivThree_eq_closedForm (upper : Nat) :
    cubicSumDivThree upper =
      (((upper : ℚ) * ((upper : ℚ) + 1) / 2) ^ 2) / 3 := by
  induction upper with
  | zero => norm_num [cubicSumDivThree]
  | succ upper ih =>
      rw [cubicSumDivThree, show upper + 1 + 1 = (upper + 1) + 1 by omega,
        Finset.sum_range_succ]
      rw [show (∑ x ∈ Finset.range (upper + 1), (x : ℚ) ^ 3 / 3) =
          cubicSumDivThree upper by rfl, ih]
      push_cast
      ring

/-- The executable accumulator refines the exact mathematical cube sum. -/
theorem cubicNumeratorLoop_cast (count : Nat) :
    (cubicNumeratorLoop count : ℚ) =
      ∑ x ∈ Finset.range count, (x : ℚ) ^ 3 := by
  induction count with
  | zero => simp [cubicNumeratorLoop]
  | succ count ih =>
      rw [cubicNumeratorLoop, Finset.sum_range_succ, Nat.cast_add,
        Nat.cast_pow, ih]

/-- Exact numerator-loop result, proved without unfolding 20,001 steps. -/
theorem cubicNumeratorLoop_20001 :
    cubicNumeratorLoop 20001 = 40004000100000000 := by
  have hsum :
      (∑ x ∈ Finset.range 20001, (x : ℚ) ^ 3) =
        (40004000100000000 : ℚ) := by
    calc
      (∑ x ∈ Finset.range 20001, (x : ℚ) ^ 3) =
          (((((20000 : Nat) : ℚ) *
            (((20000 : Nat) : ℚ) + 1) / 2) ^ 2)) := by
        simpa only [show 20000 + 1 = 20001 by norm_num] using
          sumCubes_eq_closedForm 20000
      _ = (40004000100000000 : ℚ) := by norm_num
  have hloopQ :
      (cubicNumeratorLoop 20001 : ℚ) =
        (40004000100000000 : ℚ) := by
    rw [cubicNumeratorLoop_cast, hsum]
  have hloop :
      cubicNumeratorLoop 20001 = 40004000100000000 := by
    exact_mod_cast hloopQ
  exact hloop

/-- Exact operational result, proved without unfolding 20,001 loop steps. -/
theorem cubicSumDivThreeMachine_20000 :
    cubicSumDivThreeMachine 20000 = 13334666700000000 := by
  rw [cubicSumDivThreeMachine,
    show 20000 + 1 = 20001 by norm_num, cubicNumeratorLoop_20001]

/-- The numerator accumulator is monotone in its iteration count. -/
theorem cubicNumeratorLoop_mono {left right : Nat} (hle : left ≤ right) :
    cubicNumeratorLoop left ≤ cubicNumeratorLoop right := by
  induction right generalizing left with
  | zero =>
      have : left = 0 := by omega
      subst left
      rfl
  | succ right ih =>
      by_cases heq : left = right + 1
      · subst left
        rfl
      · have hleft : left ≤ right := by omega
        exact (ih hleft).trans (by simp [cubicNumeratorLoop])

/-- Every accumulator value reached by the registered loop fits unsigned
64-bit storage. -/
theorem cubicNumeratorLoop_lt_u64 {count : Nat} (hle : count ≤ 20001) :
    cubicNumeratorLoop count < 2 ^ 64 := by
  have hbound := cubicNumeratorLoop_mono hle
  rw [cubicNumeratorLoop_20001] at hbound
  omega

/-- Every cube operand used by the registered loop fits unsigned 64-bit
storage. -/
theorem cube_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    x ^ 3 < 2 ^ 64 := by
  exact (Nat.pow_le_pow_left hle 3).trans_lt (by norm_num)

/-- The intermediate square in `x * x * x` also fits unsigned 64-bit
storage. -/
theorem square_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    x ^ 2 < 2 ^ 64 := by
  exact (Nat.pow_le_pow_left hle 2).trans_lt (by norm_num)

/-- Each accumulator addition in the registered loop fits unsigned 64-bit
storage, so a u64 implementation has no wraparound on this domain. -/
theorem cubicNumeratorStep_lt_u64 {x : Nat} (hle : x ≤ 20000) :
    cubicNumeratorLoop x + x ^ 3 < 2 ^ 64 := by
  have hnext : x + 1 ≤ 20001 := by omega
  simpa only [cubicNumeratorLoop] using cubicNumeratorLoop_lt_u64 hnext

/-- The final quotient also fits unsigned 64-bit storage. -/
theorem cubicSumDivThreeMachine_lt_u64 :
    cubicSumDivThreeMachine 20000 < 2 ^ 64 := by
  rw [cubicSumDivThreeMachine_20000]
  norm_num

/-- Exact result for the registered tutorial bound.  This proof is symbolic;
it does not reduce 20,001 summands and uses no `native_decide`. -/
theorem cubicSumDivThree_20000 :
    cubicSumDivThree 20000 = (13334666700000000 : ℚ) := by
  rw [cubicSumDivThree_eq_closedForm]
  norm_num

/-- At the registered bound, the executable loop implements the exact
rational expression requested by the mathematical specification. -/
theorem cubicSumDivThreeMachine_sound_20000 :
    (cubicSumDivThreeMachine 20000 : ℚ) = cubicSumDivThree 20000 := by
  rw [cubicSumDivThreeMachine_20000, cubicSumDivThree_20000]
  norm_num

end RegisteredAlgorithm

/-- Closed, versioned invocations whose complete input meaning is audited.

This is an inductive rather than a caller-populated structure.  Consequently
the trusted axiom cannot be applied to an arbitrary SHA-256 preimage chosen by
a theorem author.  Large server-side verifiers may later use a constructor
whose fixed semantics existentially quantifies streamed witness bytes, while
the small tutorial fixes its complete input literally. -/
inductive RegisteredInvocation where
  /-- `cubicSumDivThreeV1` with canonical input `"20000"`. -/
  | cubicSumDivThree20000V1
  deriving Repr, DecidableEq, BEq

namespace RegisteredInvocation

/-- Algorithm selected by a closed invocation. -/
def algorithm : RegisteredInvocation → RegisteredAlgorithm
  | .cubicSumDivThree20000V1 => .cubicSumDivThreeV1

/-- Exact canonical input selected by a closed invocation. -/
def canonicalInput : RegisteredInvocation → String
  | .cubicSumDivThree20000V1 => "20000"

/-- Bind a signed statement to the complete formal identity and exact input of
a registered invocation. -/
def statementCheck (invocation : RegisteredInvocation)
    (statement : RunStatement) : Bool :=
  decide (
    statement.algorithmId = invocation.algorithm.algorithmId ∧
    statement.algorithmHash = invocation.algorithm.algorithmHash ∧
    statement.inputHash = SHA256.digestString invocation.canonicalInput ∧
    statement.parametersHash =
      SHA256.digestString invocation.algorithm.canonicalParameters ∧
    statement.domainHash =
      SHA256.digestString invocation.algorithm.canonicalDomain)

/-- Propositional identity exposed by a successful invocation check. -/
def StatementBound (invocation : RegisteredInvocation)
    (statement : RunStatement) : Prop :=
  statement.algorithmId = invocation.algorithm.algorithmId ∧
  statement.algorithmHash = invocation.algorithm.algorithmHash ∧
  statement.inputHash = SHA256.digestString invocation.canonicalInput ∧
  statement.parametersHash =
    SHA256.digestString invocation.algorithm.canonicalParameters ∧
  statement.domainHash =
    SHA256.digestString invocation.algorithm.canonicalDomain

/-- The complete formal execution claim unlocked for this invocation.

The closed tutorial invocation specializes the algorithm to upper bound
20,000 directly.  It therefore does not universally assign semantics to every
possible preimage of the statement's input digest. -/
def Runs : RegisteredInvocation → String → Prop
  | .cubicSumDivThree20000V1, output =>
      output = "13334666700000000" ∧
        ∃ result : Nat,
          RegisteredAlgorithm.parseCanonicalNat output = some result ∧
          RegisteredAlgorithm.cubicSumDivThreeMachine 20000 = result

theorem statementCheck_sound {invocation : RegisteredInvocation}
    {statement : RunStatement}
    (hcheck : invocation.statementCheck statement = true) :
    invocation.StatementBound statement := by
  simpa [statementCheck, StatementBound] using hcheck

/-- The closed tutorial invocation can return only its one exact canonical
result string. -/
theorem cubicSumDivThree20000V1_output
    {output : String}
    (run : RegisteredInvocation.cubicSumDivThree20000V1.Runs output) :
    output = "13334666700000000" := by
  exact run.1

/-- Mathematical theorem recovered from a successful registered run. -/
theorem cubicSumDivThree20000V1_result
    {output : String}
    (run : RegisteredInvocation.cubicSumDivThree20000V1.Runs output) :
    output = "13334666700000000" ∧
      RegisteredAlgorithm.cubicSumDivThree 20000 =
        (13334666700000000 : ℚ) := by
  exact ⟨cubicSumDivThree20000V1_output run,
    RegisteredAlgorithm.cubicSumDivThree_20000⟩

end RegisteredInvocation

end SparkInterval.Execution
