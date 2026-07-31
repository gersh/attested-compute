/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

/-!
# `lake exe sparkinterval-check-tdx-chain` -- the Intel certificate-chain gate

## What this establishes

That every retained Intel TDX quote committed to this repository carries an
ECDSA-P256 signature chain that closes against the Intel SGX Root CA pinned at
`tools/intel_sgx_root_ca.pem`:

* the attestation key signs `header ‖ TD report`;
* the Quoting Enclave's report data binds that attestation key;
* the PCK leaf certificate signs the QE report;
* leaf → intermediate → root, and the root is self-signed; and
* that root's SHA-256 fingerprint is Intel's.

In one sentence: *the key that signed this quote belongs to a genuine
Intel-rooted TDX platform.*  That is the one link in the attestation story that
Lean does not, and here still does not, check.

## What this does **not** establish

**It does not put the Intel certificate chain into Lean's kernel.**  This
executable does not prove anything.  It runs
`tools/verify_tdx_quote_chain.py` in a subprocess and reports its exit status.
No proof term anywhere in this development mentions a PCK certificate, and
`SparkInterval/Execution/PhalaTdxOperationalAttestation.lean` -- which states
`phalaTdxAttestedEmission_sound` -- must continue to say so in its assumption
list.  Assumption 4 there is unchanged by this gate: Lean verifies only that
the retained appraisal's SHA-256 is the one in the signed statement, and the
Intel signature over the quote is appraised outside Lean and stays a pin.

What changes is only that the external check can no longer be *silently*
skipped: it is wired into `tools/audit_axioms.sh` beside
`tools/audit_lean_source.py`, and into `.github/workflows/build-provenance.yml`.

It also establishes nothing about TCB freshness, QE identity, or revocation.
Those require Intel's live collateral and remain `dcap-qvl`'s job.

## Offline versus online

Default mode is fully offline: committed quote bytes, a committed PEM, and
arithmetic.  A build must not depend on network reachability or on Intel's
service being up, and a network failure must never be reported as an
attestation failure.

`--live` is the separate, network-touching confirmation that the pinned PEM
still matches the root Intel publishes today.  It is for CI or on demand and
is never run by the offline gate.

## Invocation

```
lake exe sparkinterval-check-tdx-chain                     # offline
lake exe sparkinterval-check-tdx-chain --require-evidence  # absent = fatal
lake exe sparkinterval-check-tdx-chain --live              # online only
```

## Exit codes (passed through unchanged from the checker)

* `0` -- every retained bundle present was checked and its chain is valid
* `1` -- a bundle was present and its chain is **invalid** (hard failure), or
  `--require-evidence` was given and nothing was present
* `2` -- usage or environment error (bad arguments, `cryptography` missing)
* `3` -- nothing to check: no retained bundle present (a loud skip, not a pass)
* `4` -- `--live` could not reach Intel (network, deliberately not `1`)

The two failure modes are kept apart on purpose.  "No evidence bundle present"
is exit `3`; "evidence present and chain invalid" is exit `1`.  The caller
decides what a skip means; this repository's own gate passes
`--require-evidence`, because the bundles are committed here and their absence
means a broken checkout rather than an unconfigured one.
-/

namespace SparkInterval.Execution.TdxChainGateCLI

/-- Path of the vendored checker, relative to the repository root. -/
def checkerScript : System.FilePath :=
  "tools" / "verify_tdx_quote_chain.py"

private def usage : String :=
  "usage: sparkinterval-check-tdx-chain [--live] [--require-evidence] \
   [--repo-root DIR] [-- EXTRA...]\n\n\
   Offline Intel certificate-chain gate for the retained TDX quotes.  This is \
   a build gate only; it does not put the Intel chain into Lean's kernel."

/-- Translate this executable's flags into the checker's flags. -/
private def translate : List String → Except String (List String)
  | [] => .ok []
  | "--live" :: rest =>
      translate rest |>.map ("--check-live-intel-root" :: ·)
  | "--require-evidence" :: rest =>
      translate rest |>.map ("--require-evidence" :: ·)
  | "--repo-root" :: dir :: rest =>
      translate rest |>.map (fun tail => "--repo-root" :: dir :: tail)
  | "--repo-root" :: [] => .error "--repo-root needs a directory"
  | "--" :: rest => .ok rest
  | arg :: _ => .error s!"unrecognised argument {arg}"

def main (args : List String) : IO UInt32 := do
  if args.contains "--help" || args.contains "-h" then
    IO.println usage
    return 0
  let scriptArgs ← match translate args with
    | .ok value => pure value
    | .error message =>
        IO.eprintln s!"sparkinterval-check-tdx-chain: {message}"
        IO.eprintln usage
        return 2
  -- Resolve the checker relative to the working directory so that the gate
  -- reads this repository's own vendored copy.  A gate that depends on a path
  -- in someone's home directory is not a gate.
  let explicitRoot :=
    match args.dropWhile (· != "--repo-root") with
    | _ :: dir :: _ => some (System.FilePath.mk dir)
    | _ => none
  let cwd ← IO.currentDir
  -- Resolve to an absolute path before handing it to the subprocess: the child
  -- runs with `cwd := root`, so a relative script path would resolve against
  -- the wrong directory and the gate would report "cannot find" on a perfectly
  -- good checkout.
  let root ← match explicitRoot with
    | none => pure cwd
    | some dir =>
        try
          IO.FS.realPath dir
        catch _ =>
          IO.eprintln s!"sparkinterval-check-tdx-chain: no such directory: {dir}"
          return 2
  let script := root / checkerScript
  if !(← script.pathExists) then
    IO.eprintln s!"sparkinterval-check-tdx-chain: cannot find {script}"
    IO.eprintln
      "Run this from the repository root, or pass --repo-root DIR.  This is \
       an environment error, not an attestation failure."
    return 2
  let child ← IO.Process.spawn {
    cmd := "python3"
    args := (#[script.toString] ++ scriptArgs.toArray)
    cwd := some root
  }
  child.wait

end SparkInterval.Execution.TdxChainGateCLI

/-- Entry point.  See the module docstring for what this gate does and, more
importantly, what it does not. -/
def main (args : List String) : IO UInt32 :=
  SparkInterval.Execution.TdxChainGateCLI.main args
