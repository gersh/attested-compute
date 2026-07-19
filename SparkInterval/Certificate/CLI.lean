import SparkInterval.Certificate.Format

/-! Command-line checker for canonical Phase 8 full certificates. -/

set_option autoImplicit false

namespace SparkInterval.Certificate.CLI

private def usage : String :=
  "usage: sparkinterval-check-certificate CERTIFICATE.json --upper-bound HEX64"

private def checkerId : String :=
  "sparkinterval.lean_full_certificate_checker.v1"

private def acceptedReceipt (text boundHex : String)
    (certificate : FullCertificate) : String :=
  "{\"accepted\":true," ++
  "\"application_upper_bound\":\"" ++ boundHex ++ "\"," ++
  "\"assurance\":\"lean_exact_rational_full_certificate\"," ++
  "\"batch_sha256\":\"" ++ certificate.batchHash ++ "\"," ++
  "\"certificate_sha256\":\"" ++ SHA256.digestString text ++ "\"," ++
  "\"checker\":\"" ++ checkerId ++ "\"," ++
  "\"result_sha256\":\"" ++ certificate.resultHash ++ "\"," ++
  "\"row_count\":" ++ toString certificate.rows.size ++ "}"

private def checkFile (path boundHex : String) : IO UInt32 := do
  let bound ← match parseFiniteBinary64Hex boundHex with
    | .ok value => pure value
    | .error message =>
        IO.eprintln s!"sparkinterval-check-certificate: {message}"
        return 2
  let inputPath : System.FilePath := path
  let metadata ← try
      inputPath.metadata
    catch error =>
      IO.eprintln s!"sparkinterval-check-certificate: cannot inspect {path}: {error}"
      return 2
  if metadata.type != .file then
    IO.eprintln s!"sparkinterval-check-certificate: input is not an ordinary file: {path}"
    return 2
  if metadata.byteSize.toNat > maxCertificateBytes then
    IO.eprintln s!"sparkinterval-check-certificate: certificate exceeds {maxCertificateBytes} bytes"
    return 2
  let text ← try
      IO.FS.readFile inputPath
    catch error =>
      IO.eprintln s!"sparkinterval-check-certificate: cannot read {path}: {error}"
      return 2
  match parseCanonicalFullCertificate text with
  | .error message =>
      IO.eprintln s!"sparkinterval-check-certificate: {message}"
      return 1
  | .ok certificate =>
      if !certificate.check then
        IO.eprintln "sparkinterval-check-certificate: exact row recomputation failed"
        return 1
      match Binary64.decodeFinite bound with
      | none =>
          IO.eprintln "sparkinterval-check-certificate: application upper bound is not finite"
          return 2
      | some exactBound =>
          if !certificate.upperRowsCheck exactBound then
            IO.eprintln "sparkinterval-check-certificate: application upper bound failed"
            return 1
      IO.println (acceptedReceipt text boundHex certificate)
      return 0

def run (arguments : List String) : IO UInt32 :=
  match arguments with
  | [path, "--upper-bound", bound] => checkFile path bound
  | _ => do
      IO.eprintln usage
      return 2

end SparkInterval.Certificate.CLI

def main (arguments : List String) : IO UInt32 :=
  SparkInterval.Certificate.CLI.run arguments
