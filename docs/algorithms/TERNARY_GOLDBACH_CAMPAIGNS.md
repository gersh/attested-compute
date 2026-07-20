# Unified ternary-Goldbach campaign control plane

Copyright (c) 2026 Gershon Bialer. All rights reserved.  SPDX-License-Identifier: MIT.

`tools/tg_campaign.py` gives all thirteen named external atoms one
machine-readable capability, planning, prerequisite, status, and integrity
interface. It deliberately separates four facts that are easy to conflate:

1. an implementation or bounded reference exists;
2. an engine is capable of the complete source domain;
3. a complete computation has actually run and its artifacts pass their
   semantic checker; and
4. Lean has a realization theorem connecting that checker to the named atom.

The profile registry never infers a later fact from an earlier one. In
particular, a sample is permanently marked `sample_only`, cannot advertise
`supports_full_source`, and cannot produce a verified full-source status.

## Registry

The immutable protocol input is
`specifications/TERNARY_GOLDBACH_CAMPAIGN_PROFILES.json`. Its thirteen profile
IDs must equal the thirteen IDs in
`TERNARY_GOLDBACH_EXTERNAL_ATOMS.json`, in catalog order. The registry embeds
the raw SHA-256 of that source catalog, while every emitted plan embeds the
canonical hashes of the registry and selected profile.

Every profile records:

- an `implementation_state`;
- the complete source domain, coverage rule, work unit, and catalog work
  count;
- all required repository files, operator-supplied artifacts, executables,
  Python modules, and CUDA devices;
- each real, bounded, or missing engine and whether it supports complete
  source coverage and authenticated resume; and
- explicit assurance flags for exact decisions, directed enclosures,
  gap-free coverage, authenticated resume, independent replay, and the Lean
  realization theorem.

The implementation states mean:

| State | Meaning |
|---|---|
| `full_campaign_ready` | A practical complete-source entry point exists. Required local inputs may still be absent. |
| `full_campaign_runnable_unscaled` | The exact reference accepts the full endpoint in form, but running it at source scale is expected to be impractical. |
| `bounded_only` | A real bounded checker or producer exists, but it is marked as a sample and cannot be planned as a full campaign. |
| `blocked` | A required production algorithm or source artifact is absent. Any existing entry point is only a bounded pilot. |

These are implementation states, not evidence states. Even
`full_campaign_ready` says nothing about whether a run has occurred.

## Commands

Report all thirteen profiles or one exact atom:

```bash
python3 tools/tg_campaign.py --pretty capability
python3 tools/tg_campaign.py --pretty capability --atom cdem-table-abel
```

Probe prerequisites without executing a campaign. Artifact inputs are
supplied explicitly as `NAME=PATH`; their bytes are hashed once for a plan.

```bash
python3 tools/tg_campaign.py --pretty doctor \
  --atom ch25-a7-boundary \
  --input boundary_transcript=/path/to/ch25-a7-boundary.json
```

Create a deterministic full-source plan. The planner rejects bounded and
missing engines; it never substitutes a sample. Without `--write`, this is a
read-only preview. With `--write`, it creates canonical `plan.json` atomically
and refuses to overwrite different immutable bytes.

```bash
python3 tools/tg_campaign.py --pretty plan cdem-table-abel \
  --workspace /data/tg/cdem-abel --write
```

The optional adapter executes exactly the argument vector bound into that
plan, without a shell:

```bash
python3 tools/tg_campaign.py --pretty run /data/tg/cdem-abel
```

An exit code of zero is recorded only as `execution_complete`. It is not
promoted to semantic verification or full-source evidence. `resume` is
accepted only for an engine whose profile explicitly advertises a composable
resume contract; otherwise it fails closed.

Inspect or integrity-check a workspace:

```bash
python3 tools/tg_campaign.py --pretty status /data/tg/cdem-abel
python3 tools/tg_campaign.py --pretty verify /data/tg/cdem-abel
```

`status` validates canonical plan/status structure but reports
`full_source_campaign: false` until a separate semantic integration exists.
`verify` rehashes every declared artifact beneath the workspace and reports
`campaign_control_and_artifact_integrity_only`. It does not replay an
atom-specific mathematical checker and therefore always reports
`full_source_campaign_verified_by_this_command: false` and
`lean_atom_discharged: false`.

## Fail-closed file handling

Control JSON rejects duplicate keys, JSON floats, and non-finite constants.
Plans and status records use one canonical UTF-8 encoding. Plans are
immutable and content addressed. Status and engine-output updates use a
sibling advisory lock, an `fsync`ed temporary file, atomic replacement, and a
directory `fsync`. Artifact paths must remain under the workspace, and their
size and SHA-256 must match before the integrity command accepts them.

This control plane is intentionally narrower than a certificate verifier. An
atom-specific semantic checker and, ultimately, a Lean realization theorem
must be added independently; changing a status JSON field cannot provide
either one.
