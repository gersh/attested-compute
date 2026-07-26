# Sqrt218 physical-launch identity V2

The fixed-width Sqrt218 boundary now has a compact V2 identity for a future
attested pure-entry run.  It is a data-independent identity boundary, not a
production certificate and not an execution proof.

The key separation is:

| Object | Exact binding |
| --- | --- |
| Measured launcher | `RunStatement.artifacts.hostExecutableHash`, V2 launcher SHA-256, and V2 launcher byte length |
| Launcher/control contract | nonempty contract ID, positive version, SHA-256, and byte length in V2 metadata |
| Architecture-modeled pure-entry ELF | separate SHA-256 and byte length in V2 metadata and `NativeImplementationIdentity`; exact bytes, length, and digest in `ExactArchitectureBinding` |
| Pure-entry symbol | V2 `pure_entry_elf_entry_point`, the implementation entry, and the `MeasuredRun` entry |
| Formal semantics | architecture-semantics, ELF-decoder, pure-entry-ABI-model, and SysV-contract SHA-256 identities |
| Compiler evidence | compiler-evidence schema/hash, compiler source, ID, version, binary, configuration, and neutral-contract identities |

The signed statement's execution-closure field is the pure-Lean SHA-256 of
the exact length-framed V2 metadata bytes.  The domain separator is:

```text
sparkinterval.sqrt218-execution-closure-identity.v2
```

The fields, in canonical order, are:

```text
execution_closure_identity_version
compiler_evidence_manifest_version
compiler_evidence_manifest_sha256
compiler_source_sha256
compiler_id
compiler_version
compiler_binary_sha256
compiler_configuration_sha256
formal_architecture_model_sha256
formal_elf_decoder_model_sha256
formal_pure_entry_abi_model_sha256
target
sysv_abi_contract_sha256
launcher_artifact_sha256
launcher_artifact_byte_length
launcher_control_contract_id
launcher_control_contract_version
launcher_control_contract_sha256
launcher_control_contract_byte_length
neutral_contract_id
neutral_contract_sha256
pure_entry_elf_sha256
pure_entry_elf_byte_length
pure_entry_elf_entry_point
```

Each name and value is encoded as its decimal UTF-8 byte length, `:`, and its
UTF-8 bytes. Natural numbers use Lean's decimal `Nat.repr`. The domain
separator itself is unframed.

## V1 is not eligible

The previous
`sparkinterval.sqrt218-execution-closure-identity.v1` projection did not name
a launcher artifact or a launcher/control contract. It therefore cannot
identify the program that maps the pure-entry ELF, initializes the guarded
SysV state, calls the selected entry, and retains the return observation.

Lean represents legacy bytes as
`Metadata.VersionedMetadataEnvelope.legacyV1`. Its physical-launch selector
reduces to `none`. `ExactMetadataBinding` accepts only the typed V2
`Metadata`, and `Metadata.MatchesIdentity` requires identity version `2`.
Changing a V1 validator's label or supplying placeholder launcher fields does
not produce this binding.

The existing Python compiler-evidence projection remains a bounded,
non-authorizing V1 review artifact. It is useful for checking its compiler
manifest mapping, but it is not eligible for a physical-launch receipt. A
future receipt importer must construct and validate all V2 fields from the
reviewed compiler evidence, launcher build evidence, control-contract bytes,
formal-source identities, and exact ELF evidence.

## What Lean proves

[`ExecutionClosureIdentity.lean`](../../SparkInterval/TernaryGoldbach/Sqrt218/CPUChecker/ExecutionClosureIdentity.lean)
proves, with ordinary Lean equality:

- the retained metadata bytes are exactly the canonical V2 encoding;
- their pure-Lean SHA-256 equals the implementation closure identity and the
  signed statement's execution-closure digest;
- every V2 field agrees with `NativeImplementationIdentity`;
- the signed host-executable digest is the launcher digest, not the
  pure-entry ELF digest;
- the pure-entry ELF digest, byte length, entry, target, and architecture
  model agree with the exact `MeasuredRun`; and
- optional retained launcher/control byte arrays have exactly the V2
  SHA-256 and length pins.

The optional full-byte witnesses are not part of the normal `Binding`.
Receipt composition stays compact: the external appraiser binds the measured
bytes to the signed digest/length pins, while local Lean elaboration checks
only the small canonical metadata and equality composition.

Tiny symbolic checks live in
[`Sqrt218ExecutionClosureIdentityV2Test.lean`](../../SparkInterval/Tests/Sqrt218ExecutionClosureIdentityV2Test.lean).
They perform no native build, launcher execution, production arithmetic, or
instruction-trace replay.

## What this does not prove

Metadata does not establish that the launcher implements its contract, that
the ELF decoder or ABI model describes the physical machine, that the
compiler produced semantically equivalent code, or that Azure measured and
executed the named artifacts. Those remain separate refinement and
attestation obligations.

The equality `SHA256(bytes) = digest` is proved for retained bytes. Inferring
that an externally supplied byte string is the unique preimage of the signed
digest retains the standard SHA-256 collision/second-preimage assumption.
