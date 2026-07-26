/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer
-/
import SparkInterval.TernaryGoldbach.Sqrt218LogCertificate
import TGComputeContracts.Sqrt218.LogLadder

/-!
# Thirty-seed logarithm ladder for the Sqrt218 checker

The Python producer and independent verifier certify thirty small logarithm
seeds and then use an all-integer recurrence through the production bound.
This module states that exact scheme and proves it yields the directed real
logarithm facts needed by the generic Sqrt218 contract.

Nothing here evaluates the production ladder.  A later streaming checker can
establish the row-equality premise in one pass inside the measured cloud job.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

open TGComputeContracts.Sqrt218
open SparkInterval.TernaryGoldbach.Sqrt218LogCertificate

def seedAt : Nat := 30

/-- Exact fixed endpoints shared with the Python producer/verifier. -/
def seed : Nat → LogBounds
  | 1 => ⟨0, 0⟩
  | 2 => ⟨195103586431999, 195103586572737⟩
  | 3 => ⟨309231868028532, 309231868693940⟩
  | 4 => ⟨390207172863998, 390207173145474⟩
  | 5 => ⟨453016498773239, 453016499054997⟩
  | 6 => ⟨504335454460532, 504335455266677⟩
  | 7 => ⟨547725013666734, 547725014089229⟩
  | 8 => ⟨585310759295998, 585310759718211⟩
  | 9 => ⟨618463736514181, 618463736936676⟩
  | 10 => ⟨648120085205239, 648120085627734⟩
  | 11 => ⟨674947515845858, 674947516268353⟩
  | 12 => ⟨699439040892531, 699439041839414⟩
  | 13 => ⟨721969060362613, 721969060925845⟩
  | 14 => ⟨742828600098734, 742828600661966⟩
  | 15 => ⟨762248366993738, 762248367556971⟩
  | 16 => ⟨780414345727997, 780414346290948⟩
  | 17 => ⟨797478659741748, 797478660304980⟩
  | 18 => ⟨813567322946180, 813567323509412⟩
  | 19 => ⟨828785892793963, 828785893357196⟩
  | 20 => ⟨843223671637238, 843223672200471⟩
  | 21 => ⟨856956881960417, 856956882523649⟩
  | 22 => ⟨870051102277858, 870051102841090⟩
  | 23 => ⟨882563161108618, 882563161679169⟩
  | 24 => ⟨894542627324530, 894542628412151⟩
  | 25 => ⟨906032997473296, 906032998177266⟩
  | 26 => ⟨917072646794612, 917072647498582⟩
  | 27 => ⟨927695604734679, 927695605438649⟩
  | 28 => ⟨937932186530733, 937932187234703⟩
  | 29 => ⟨947809514957280, 947809515661250⟩
  | 30 => ⟨957351953425738, 957351954129708⟩
  | _ => ⟨0, 0⟩

def seedCellCheck (n : Nat) : Bool :=
  if n = 1 then
    true
  else
    primeLogRowCheck 40 4 128 n (seed n).lower (seed n).upper

/-- Boolean check of exactly the thirty fixed seed rows.

The exact row at `n = 1` is discharged analytically in
`SeedCertificate.seed_valid`, since a nonzero-width Taylor enclosure cannot
certify the degenerate interval `[0, 0]`.  Rows `2` through `30` use the
generic rational logarithm checker. -/
def seedTableCheck : Bool :=
  (List.range seedAt).all fun offset => seedCellCheck (offset + 1)

/-- Small executable premise for exactly the thirty fixed seed rows. -/
structure SeedCertificate : Prop where
  checked :
    ∀ n, 1 ≤ n → n ≤ seedAt → seedCellCheck n = true

theorem seedTableCheck_sound
    (hcheck : seedTableCheck = true) : SeedCertificate := by
  refine ⟨?_⟩
  intro n hn1 hn30
  unfold seedTableCheck at hcheck
  rw [List.all_eq_true] at hcheck
  have hmem : n - 1 ∈ List.range seedAt := by
    simp only [List.mem_range]
    omega
  have hcell := hcheck (n - 1) hmem
  simpa [Nat.sub_add_cancel hn1] using hcell

theorem SeedCertificate.seed_valid
    (certificate : SeedCertificate)
    {n : Nat} (hn1 : 1 ≤ n) (hn30 : n ≤ seedAt) :
    (seed n).Valid n := by
  by_cases hone : n = 1
  · subst n
    simp [seed, LogBounds.Valid]
  have hsound :=
    primeLogRowCheck_sound
      (terms := 40) (k := 4) (prec := 128)
      (p := n) (lower := (seed n).lower) (upper := (seed n).upper)
      (by norm_num) (by omega)
      (by
        have hchecked := certificate.checked n hn1 hn30
        simpa [seedCellCheck, hone] using hchecked)
  exact hsound

/-- Advance `count` consecutive integer recurrence steps, starting at
`position`. -/
def run : Nat → Nat → LogBounds → LogBounds
  | 0, _, bounds => bounds
  | count + 1, position, bounds =>
      run count (position + 1) (bounds.next position)

theorem run_valid
    {count position : Nat} {bounds : LogBounds}
    (hposition : 2 ≤ position) (hvalid : bounds.Valid position) :
    (run count position bounds).Valid (position + count) := by
  induction count generalizing position bounds with
  | zero =>
      simpa [run] using hvalid
  | succ count inductionHypothesis =>
      rw [run]
      have hnext := hvalid.next hposition
      have hresult :=
        inductionHypothesis (position := position + 1)
          (bounds := bounds.next position) (by omega) hnext
      simpa [Nat.add_assoc, Nat.add_comm 1 count] using hresult

/-- Exact Python-compatible bounds at one natural-number argument. -/
def boundsAt (n : Nat) : LogBounds :=
  if n ≤ seedAt then
    seed n
  else
    run (n - seedAt) seedAt (seed seedAt)

theorem boundsAt_valid
    (certificate : SeedCertificate)
    {n : Nat} (hn : 1 ≤ n) :
    (boundsAt n).Valid n := by
  by_cases hseed : n ≤ seedAt
  · simp only [boundsAt, if_pos hseed]
    exact certificate.seed_valid hn hseed
  · simp only [boundsAt, if_neg hseed]
    have hseedValid :
        (seed seedAt).Valid seedAt :=
      certificate.seed_valid (by norm_num [seedAt])
        (le_refl seedAt)
    have hrun :=
      run_valid (count := n - seedAt) (position := seedAt)
        (bounds := seed seedAt) (by norm_num [seedAt]) hseedValid
    have hle : seedAt ≤ n := by omega
    simpa [Nat.add_sub_of_le hle] using hrun

/-- Data-independent connection from the sequential ladder to the log endpoint
functions used by `CertificateFacts`. -/
structure PrimeRowsCertificate
    (primeCount : Nat)
    (primeAt logLowerAt logUpperAt : Nat → Nat) : Prop where
  seeds : SeedCertificate
  rows :
    ∀ i, i < primeCount →
      logLowerAt i = (boundsAt (primeAt i)).lower ∧
        logUpperAt i = (boundsAt (primeAt i)).upper

theorem PrimeRowsCertificate.sound
    {bound primeCount : Nat}
    {primeAt logLowerAt logUpperAt : Nat → Nat}
    (certificate :
      PrimeRowsCertificate primeCount primeAt logLowerAt logUpperAt)
    (roster : PrimeRosterFacts bound primeCount primeAt) :
    PrimeLogFacts primeCount primeAt logLowerAt logUpperAt := by
  constructor
  · intro i hi
    have hvalid :=
      boundsAt_valid certificate.seeds (roster.prime i hi).pos
    rw [(certificate.rows i hi).1]
    exact hvalid.1
  · intro i hi
    have hvalid :=
      boundsAt_valid certificate.seeds (roster.prime i hi).pos
    rw [(certificate.rows i hi).2]
    exact hvalid.2

end SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

end
