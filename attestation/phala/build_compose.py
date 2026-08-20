#!/usr/bin/env python3
"""Generate the measured docker-compose document for an attested run.

GENERATED OUTPUT, NEVER HAND-EDITED.  The compose embeds the artifacts and the
entry point verbatim, so its bytes are what dstack measures: SHA-256 of the
app-compose document that wraps this file is the `compose_hash` appearing in
`mr_config_id` and in the RTMR3 `compose-hash` event.  A hand edit silently
changes what the quote attests.

A *deployment* is described by a JSON manifest, so this script names no
artifact and belongs to no consumer:

    {
      "name": "my-run",
      // Pinned by digest, never a tag, and it must already contain everything
      // the entry point uses -- bash, coreutils, gcc, libc headers, python3.
      // Nothing is installed at run time, because anything fetched then is
      // outside the measurement.  `python:3.12` carries all of it.
      "base_image": "python@sha256:…",
      "artifact_dir": "x86-artifacts",          // relative to the manifest
      "artifacts": [
        {"name": "prog", "args": "1 2 3"}       // args optional
      ],
      "sources": [                              // optional: differential rebuild
        {"name": "prog.c", "path": "../prog/prog.c", "args": "1 2 3"}
      ]
    }

Each artifact needs `<name>` and `<name>.x86.stamp.json` in `artifact_dir`,
as produced by the cross-build tooling.

    python3 build_compose.py --manifest path/to/deployment.json
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
#: signing modules embedded in the compose, and the env-var stem each uses.
RECEIPT_MODULES = {"phala_tdx_receipt.py": "RECEIPT_MOD",
                   "compcert_run_receipt.py": "RUNRECEIPT_MOD",
                   "compcert_run_spec.py": "RUNSPEC_MOD"}


def die(message: str) -> None:
    print(f"build_compose: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_artifact(build: pathlib.Path, name: str) -> tuple[str, str, dict]:
    """Return (gz+b64 payload, sha256, stamp), refusing anything not x86_64."""
    binary, stamp_path = build / name, build / f"{name}.x86.stamp.json"
    if not binary.exists() or not stamp_path.exists():
        die(f"{name}: expected {binary} and {stamp_path}")
    stamp = json.loads(stamp_path.read_text())
    if stamp["target"] != "x86_64-linux" or "x86-64" not in stamp["file"]:
        die(f"{name}: stamp says target={stamp['target']}, file={stamp['file']}")
    raw = binary.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != stamp["binary_sha256"]:
        die(f"{name}: binary digest {digest} != stamp {stamp['binary_sha256']}")
    check = stamp.get("qemu_self_check", {})
    if check.get("ran") and check.get("exit") != 0:
        die(f"{name}: self-check exited {check.get('exit')}; nothing to attest")
    if check.get("stdout_sha256") is None:
        die(f"{name}: stamp records no expected transcript digest; rebuild")
    # mtime=0 so the payload is a function of the binary alone and the compose
    # hash does not drift between regenerations.
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(packed).decode(), digest, stamp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path,
                        help="default: docker-compose.yaml beside the manifest")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    base = args.manifest.resolve().parent
    build = base / manifest.get("artifact_dir", "x86-artifacts")
    out = args.out or (base / "docker-compose.yaml")

    env: dict[str, str] = {}
    report: list[str] = []

    artifacts = manifest["artifacts"]
    env["ARTIFACT_COUNT"] = str(len(artifacts))
    for i, entry in enumerate(artifacts):
        name = entry["name"]
        payload, digest, stamp = load_artifact(build, name)
        check = stamp["qemu_self_check"]
        env[f"A{i}_NAME"] = name
        env[f"A{i}_BIN_GZ_B64"] = payload
        env[f"A{i}_BIN_SHA"] = digest
        env[f"A{i}_ARGS"] = entry.get("args", "")
        # What SUCCESS is, pinned here rather than left to the artifact's own
        # say-so.  Both values are inside the compose hash, so a reader can see
        # exactly what the enclave demanded, and the artifact cannot define its
        # own pass criterion.  The transcript digest pins every printed
        # intermediate, not just a verdict line.
        env[f"A{i}_EXPECT_EXIT"] = str(entry.get("expect_exit", 0))
        env[f"A{i}_EXPECT_SHA"] = check["stdout_sha256"]
        env[f"A{i}_C_SHA"] = stamp["c_sha256"]
        report.append(f"  {name:34s} {digest[:16]}… {stamp['binary_bytes']:>8d} B "
                      f"-> {len(payload):>7d} B b64  [{stamp['mode']}]  "
                      f"expect exit={env[f'A{i}_EXPECT_EXIT']} "
                      f"out={check['stdout_sha256'][:12]}…")

    sources = manifest.get("sources", [])
    env["SOURCE_COUNT"] = str(len(sources))
    for i, entry in enumerate(sources):
        raw = (base / entry["path"]).resolve().read_bytes()
        env[f"S{i}_NAME"] = entry["name"]
        env[f"S{i}_SRC_B64"] = base64.b64encode(raw).decode()
        env[f"S{i}_SRC_SHA"] = hashlib.sha256(raw).hexdigest()
        env[f"S{i}_ARGS"] = entry.get("args", "")

    # The signing modules, embedded rather than installed: the container has no
    # network guarantee, and embedding puts them inside the compose hash, so the
    # signing code is measured too.
    modules = HERE.parents[1] / "tg_verifier"
    for name, stem in RECEIPT_MODULES.items():
        raw = (modules / name).read_bytes()
        env[f"{stem}_B64"] = base64.b64encode(raw).decode()
        env[f"{stem}_SHA"] = hashlib.sha256(raw).hexdigest()

    # Pinned empty: in the TD the artifacts and the machine are both x86_64.
    # Only the local rehearsal overrides it (see dry_run.sh).
    env["RUNNER"] = ""

    # Compose runs its own interpolation pass before the shell sees the script
    # and aborts on `${VAR:?msg}`.  Escaping every `$` as `$$` stops that.
    script = (HERE / "enclave_run.sh").read_text().replace("$", "$$")

    document = {"services": {"attested-run": {
        "image": manifest["base_image"],
        "environment": env,
        # The socket is how a container asks the TD for its own measurements —
        # not network access.  The read-only mounts are where dstack keeps the
        # app-compose document, whose RAW bytes the enclave reads so the compose
        # binding can be checked without trusting the Cloud API's (not
        # byte-faithful) JSON view.
        # Nothing is fetched at run time, so the container needs no egress.
        # This is what makes "everything that runs is measured" true rather
        # than nearly true: with no network there is nothing to substitute.
        "network_mode": "none",
        # Hardening.  None of it defends against the host -- TDX does that --
        # and none of it is load-bearing for the attestation.  It constrains
        # the entry point if the entry point is WRONG, which is the failure
        # mode nothing else here covers: the compose is measured, so a mistake
        # in it is faithfully measured too.
        #
        # These flags live in the compose, so they are inside the compose hash,
        # inside mr_config_id and inside the RTMR3 event.  The quote therefore
        # attests the posture the container ran under, not merely our claim
        # about it.
        #
        # `read_only` with a tmpfs at /tmp: the entry point does all its work
        # in /tmp/rhx86 and writes nowhere else, so nothing needs a writable
        # rootfs.
        #
        # ⚠ `exec` is REQUIRED and must be stated.  Docker mounts a `--tmpfs`
        # `noexec` unless told otherwise, and the decoded artifacts are
        # executed from /tmp -- which is the entire point of the run.  Omitting
        # it fails every artifact with exit 126, and on hardware that is the
        # whole deployment.  The rehearsal only half-catches it: there the
        # artifacts run under qemu, an interpreter that reads the binary as
        # data and is not blocked by `noexec`, so the only native execution --
        # and therefore the only canary -- is the differential gcc rebuild.
        "read_only": True,
        "tmpfs": ["/tmp:rw,exec,nosuid,nodev,size=1g"],
        # Nothing here needs a capability.  Dropping all of them means a bug in
        # the entry point cannot become a privileged one.
        "cap_drop": ["ALL"],
        # No setuid binary can raise privilege, whatever else happens.
        "security_opt": ["no-new-privileges:true"],
        # A runaway loop cannot exhaust the VM's process table.
        "pids_limit": 512,
        "volumes": ["/var/run/dstack.sock:/var/run/dstack.sock",
                    "/tapp:/tapp:ro", "/dstack:/dstack:ro",
                    "/var/run/dstack:/var/run/dstack-host:ro"],
        "command": ["/bin/bash", "-c", script]}}}

    header = (
        "# GENERATED BY attestation/phala/build_compose.py -- DO NOT EDIT BY HAND.\n"
        f"# deployment: {manifest['name']}\n#\n"
        "# Artifacts and the entry point are embedded verbatim, so they are inside\n"
        "# the compose hash, inside mr_config_id, and inside the RTMR3 compose-hash\n"
        "# event.  The TDX quote's report_data is the SHA-256 of a statement naming\n"
        "# every digest and every result, so the quote attests THOSE results.\n"
        "# Verify with attestation/phala/verify_run.py.\n")
    text = header + json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    out.write_text(text)

    print(f"deployment: {manifest['name']}")
    print("\n".join(report))
    size = len(text.encode())
    print(f"\ncompose: {out}  ({size:,} bytes)")
    print(f"compose sha256: {hashlib.sha256(text.encode()).hexdigest()}")
    if size > 180_000:
        print("⚠ approaching the 200 KB limit on docker_compose_file + "
              "pre_launch_script; reference an image by digest instead")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
