# Azure ternary-Goldbach launch preflight

`tools/tg_azure_launch_preflight.py` is a bounded, read-only audit of the ten
physical campaigns serving the thirteen named external atoms. It does not
contact Azure, read credentials, create resources, materialize jobs, or run
campaign arithmetic.

Run:

```bash
tools/tg_azure_launch_preflight.py --pretty
tools/audit_tg_registered_campaigns.py --check
```

The command independently expands the source-retirement portfolio topology,
checks every exact terminal registered invocation against the source registry,
checks that each phase has a reviewed operator/materializer route, executes
`--help` for every referenced materializer CLI, and validates each redacted
site example against its JSON Schema.

The second command checks the source-owned eleven-row terminal registration
matrix in the opposite direction: Lean algorithm/invocation literals,
generated hashes, terminal factories, CPU/H100 backends, physical result
paths, materializers, and semantic-binding state must all agree. It reports
consistency only; it cannot turn a staged or null binding into theorem
authority.

The report deliberately separates five conditions:

- `source-ready`: a literal full-range route and its mechanical Azure handoff
  are present. This is source packaging, not evidence that the computation ran.
- `site-pin-needed`: the checked-in site file is only a schema-valid redacted
  example. Replace it with reviewed immutable image, binary, policy, key, and
  network pins before any production launch.
- `calibration-blocked`: no retained measurement from the exact target Azure
  SKU is installed, so the hard cost/time gate remains closed.
- `semantic-admission-blocked`: no production deployment plus signed receipt
  has been reviewed into theorem authority. This applies even to the enabled
  CDEM source-shape row. It is a post-run state and is deliberately not an
  input to `cloud_launch_ready`.
- `algorithm-incomplete`: a literal reference route exists, but the practical
  optimized end-to-end route is still incomplete. This currently applies to
  PT21 finite RH and Platt Dirichlet Theorem 7.1.

A campaign may have several classes. In particular, all ten campaigns are
currently mechanically source-ready and all ten remain production-blocked.
The command returns success when the audit itself completes. Inspect
`cloud_launch_ready` for the pre-run cloud gate and
`theorem_admission_complete` for the distinct post-run promotion state. Both
currently remain false for every campaign, but for different reasons.

The local portfolio control plane mirrors this split. A fully reviewed staged
invocation/result contract may appear as a non-authorizing
`terminal_receipt_contract`, so `init` can persist the exact source plan before
receipts exist. `prepare-shard` remains behind the unchanged hard cost/time
operator-handoff gate, and receipt recording still leaves semantic admission
false. Thus local initialization is neither `cloud_launch_ready` nor theorem
authority.

`--no-cli-help` is for a static packaging audit in constrained environments.
It still checks paths, executable bits, shebangs, schemas, topology, and
registered invocations, but it does not start the bounded `--help`
subprocesses. It never weakens a production gate.
