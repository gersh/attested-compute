#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build one chained leancompcert campaign for a Phala TDX enclave.

A `Ports.ArraySegSieve` residue program tests its window against a **single**
threshold -- the reduced family's majorant evaluated at the window's worst
endpoint.  Covering `[lo, hi]` at full strength therefore needs a *chain* of
windows, each with its own threshold and each seeded with the previous
window's carry-out.  That is the one structural fact that shapes everything
here, and it is why a campaign is a directory of artifacts and a manifest
rather than a single executable.

Four phases:

1. **discovery** (host, gcc, hosted driver) -- walk the schedule, record each
   window's violation count and its three result slots.  Refuses on the first
   window with a nonzero violation count: that is either a counterexample or
   an invocation error, and neither may be packaged.
2. **package** (host, `gcc -E` then `ccomp -S`) -- re-emit each window with
   the *self-checking* freestanding driver carrying the discovered
   expectations, and compile it to **x86_64 assembly**.  This is the step
   CompCert's semantic-preservation theorem covers.
3. **link** (linux/amd64 container, `as` + `ld`) -- assemble and link against
   `runtime/start/x86_64.S`.  Assembler and linker are outside CompCert's
   theorem either way, so running them under emulation costs nothing in trust.
4. **pin** -- write `campaign-manifest.txt`, check chain linkage inside it,
   and derive `canonicalDefinition` / `algorithmHash`.

The manifest is the object the Lean registry names by digest.  Chain integrity
is a textual property of it: window `k+1`'s `seed` must equal window `k`'s
`carry`.  `verify_manifest_chain` checks exactly that, and the entry point
inside the enclave checks it again before running anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path

EMIT_LINE = re.compile(
    r"emit mode=(?P<mode>\S+) lo=(?P<lo>\d+) hi=(?P<hi>\d+) "
    r"segLen=(?P<segLen>\d+) segCount=(?P<segCount>\d+) "
    r"arrayLen=(?P<arrayLen>\d+) loopCount=(?P<loopCount>\d+) "
    r"memoryBytes=(?P<memoryBytes>\d+) threshold=(?P<threshold>\d+) "
    r"tBias=(?P<tBias>\d+)"
)

# `mobiusInit` seeds rT, rTmax and rTmin from one value; the chain therefore
# carries exactly one number.  2^63 is `Ports.ArraySegSieve.tBias`.
T_BIAS = 2 ** 63

MODES = {
    # mode -> (name, the reduced Nat family it computes, its Lean bridge)
    "plattstrong": (
        "platt-stronger-range",
        "MathExtras.Reductions.PlattStrongerRangeNatFamily",
        "abs (mobiusOverNSum n) <= 1 / (2 * sqrt (n+1))",
    ),
    "platt211": (
        "platt-eq-2-11",
        "MathExtras.Reductions.PlattEq211NatFamily",
        "abs (mobiusOverNSum n) <= sqrt (2 / (n+1))",
    ),
}


@dataclass
class Window:
    index: int
    lo: int
    hi: int
    seg_len: int
    seg_count: int
    seed: int
    expect_viol: int
    primer: bool
    carry: int
    carry_max: int
    carry_min: int
    threshold: int
    array_len: int
    loop_count: int
    memory_bytes: int
    c_sha256: str = ""
    c_bytes: int = 0
    asm_sha256: str = ""
    bin_sha256: str = ""
    bin_bytes: int = 0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def schedule(lo: int, hi: int, ratio: float, max_seg_len: int):
    """The window schedule, as a pure function of (lo, hi, ratio, max_seg_len).

    Two hazards from `bench/seg_chain.sh.README`, both avoided by
    construction rather than by a warning:

    * a window is at least `seg_len` wide, so `seg_len` must not exceed
      `(ratio - 1) * lo` or the effective ratio silently exceeds `ratio`;
    * the artifact covers `seg_count * seg_len` integers, so a schedule that
      is not a whole number of segments **tests past `hi`** -- which is how a
      run to 7,727,068,587 reported a violation 13 integers past the end of
      the range the majorant is claimed on.  Here `seg_count` is floored and
      the final window's `seg_len` is shrunk to land exactly on `hi`.
    """
    windows = []
    cur = lo
    while cur <= hi:
        seg_len = max(1, min(max_seg_len, int(cur * (ratio - 1.0))))
        target = min(hi, int(cur * ratio))
        span = target - cur + 1
        if span < seg_len:
            # Tail: one segment covering exactly what is left, never more.
            seg_len = min(seg_len, hi - cur + 1)
            seg_count = 1
        else:
            seg_count = max(1, span // seg_len)
        end = cur + seg_len * seg_count - 1
        if end > hi:
            seg_count = max(1, (hi - cur + 1) // seg_len)
            end = cur + seg_len * seg_count - 1
            if end > hi:
                seg_len = hi - cur + 1
                seg_count = 1
                end = hi
        windows.append((cur, end, seg_len, seg_count))
        cur = end + 1
    return windows


def emit(leancompcert: Path, emitter: Path, mode: str, lo: int, seg_len: int,
         seg_count: int, seed: int, out: Path, expect=None) -> dict:
    args = [str(lo), str(seg_len), str(seg_count), str(seed)]
    if expect is not None:
        args += [str(x) for x in expect]
    args.append(str(out))
    proc = subprocess.run(
        ["lake", "env", "lean", "--run", str(emitter), mode] + args,
        cwd=str(leancompcert), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"emit failed for lo={lo}:\n{proc.stdout}{proc.stderr}")
    match = EMIT_LINE.search(proc.stdout)
    if match is None:
        raise SystemExit(f"emitter printed no parsable line:\n{proc.stdout}")
    return {k: (v if k == "mode" else int(v))
            for k, v in match.groupdict().items()}


def run_window(args, work: Path, lo: int, hi: int, seg_len: int,
               seg_count: int, seed: int):
    """Emit, compile and run one window on the build host; return its cells."""
    csrc = work / "w.c"
    info = emit(args.leancompcert, args.emitter, args.mode, lo, seg_len,
                seg_count, seed, csrc)
    assert info["hi"] == hi, (info["hi"], hi)
    exe = work / "w"
    subprocess.run(["gcc", "-O2", "-o", str(exe), str(csrc)], check=True)
    run = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    cells = {}
    for line in run.stdout.splitlines():
        key, _, value = line.partition(" ")
        cells[key] = int(value)
    return info, cells


def split(lo: int, hi: int, max_seg_len: int):
    """Halve a window, keeping both halves whole numbers of segments.

    The right half is the one that matters: a window is tested against its
    majorant at its own right endpoint, so the tightening a window suffers is
    `sqrt(hi/lo)`, and near the top of a range where the reduced family is
    nearly tight that must be made small.  Halving is the schedule-independent
    way to find how small, and it terminates: a width-1 window suffers no
    tightening at all, so a width-1 failure is a genuine counterexample.
    """
    width = hi - lo + 1
    if width <= 1:
        return None
    left_width = width // 2
    out = []
    for a, w in ((lo, left_width), (lo + left_width, width - left_width)):
        seg_len = max(1, min(max_seg_len, w))
        while w % seg_len:
            seg_len -= 1
        out.append((a, a + w - 1, seg_len, w // seg_len))
    return out


def discover(args, windows) -> list[Window]:
    """Phase 1: run the chain on the build host and record every carry-out.

    A window that reports threshold violations inside the claimed range is
    **not** immediately fatal: it may be the window schedule giving away more
    than the reduced family's slack, which is what happens near the top of a
    range whose endpoint is the point at which the majorant stops holding.
    The window is halved and retried, down to width 1.  A width-1 window is
    tested against the majorant at exactly its own point, so a width-1 failure
    is a genuine counterexample and is refused.
    """
    work = Path(tempfile.mkdtemp(prefix="segdisc."))
    out: list[Window] = []
    seed = T_BIAS
    pending = list(windows)
    splits = 0
    try:
        while pending:
            lo, hi, seg_len, seg_count = pending.pop(0)
            info, cells = run_window(args, work, lo, hi, seg_len, seg_count,
                                     seed)
            violations = cells["violations"]
            primer = hi < args.lo
            if violations != 0 and not primer:
                halves = split(lo, hi, args.max_seg_len)
                if halves is None:
                    raise SystemExit(
                        f"REFUSED: the single integer {lo} fails its own "
                        f"majorant.  A width-1 window suffers no schedule "
                        f"tightening, so this is a counterexample to the "
                        f"reduced family, not an invocation error.")
                splits += 1
                if args.progress:
                    print(f"  window [{lo}, {hi}] gave away more than the "
                          f"family's slack; halving", flush=True)
                pending = halves + pending
                continue
            index = len(out)
            out.append(Window(
                index=index, lo=lo, hi=hi, seg_len=seg_len,
                seg_count=seg_count, seed=seed, expect_viol=violations,
                primer=primer, carry=cells["slot0"],
                carry_max=cells["slot1"], carry_min=cells["slot2"],
                threshold=info["threshold"], array_len=info["arrayLen"],
                loop_count=info["loopCount"],
                memory_bytes=info["memoryBytes"]))
            seed = cells["slot0"]
            if args.discovery_json and index % 8 == 0:
                args.discovery_json.write_text(
                    json.dumps([asdict(w) for w in out], indent=1))
            if args.progress and index % args.progress == 0:
                print(f"  discovered window {index:5d} [{lo}, {hi}] "
                      f"carry={seed}", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if splits:
        print(f"  schedule refined by {splits} halvings", flush=True)
    return out


def package(args, wins: list[Window], out_dir: Path) -> None:
    """Phase 2: self-checking C, then x86_64 assembly from CompCert."""
    asm_dir = out_dir / "asm"
    csrc_dir = out_dir / "c"
    asm_dir.mkdir(parents=True, exist_ok=True)
    csrc_dir.mkdir(parents=True, exist_ok=True)
    for win in wins:
        csrc = csrc_dir / f"w{win.index:05d}.c"
        emit(args.leancompcert, args.emitter, args.mode, win.lo, win.seg_len,
             win.seg_count, win.seed, csrc,
             expect=(win.expect_viol, win.carry, win.carry_max,
                     win.carry_min))
        text = csrc.read_text()
        # A leancompcert artifact must not need the Lean runtime.  The
        # include is emitted unconditionally; any surviving `lean_` call
        # means the artifact is genuinely not standalone.
        stripped = "\n".join(
            line for line in text.splitlines()
            if line.strip() != "#include <lean/lean.h>")
        if "lean_" in stripped:
            raise SystemExit(f"REFUSED: {csrc} calls the Lean runtime")
        csrc.write_text(stripped + "\n")
        win.c_sha256 = sha256_file(csrc)
        win.c_bytes = csrc.stat().st_size

        pre = csrc.with_suffix(".i")
        # `compcert.ini` delegates preprocessing to `gcc -m64`, which the
        # host's aarch64 gcc rejects, so preprocess separately and hand
        # CompCert the already-preprocessed unit.
        subprocess.run(["gcc", "-E", "-U__GNUC__", "-U__SIZEOF_INT128__",
                        "-o", str(pre), str(csrc)], check=True)
        asm = asm_dir / f"w{win.index:05d}.s"
        subprocess.run([str(args.ccomp), "-S", "-O2", "-o", str(asm),
                        str(pre)], check=True)
        pre.unlink()
        win.asm_sha256 = sha256_file(asm)
        if args.progress and win.index % args.progress == 0:
            print(f"  packaged window {win.index:5d}", flush=True)


LINK_SCRIPT = r"""
set -eu
command -v as >/dev/null 2>&1 || apk add --no-cache binutils >/dev/null 2>&1
command -v as >/dev/null 2>&1 || { echo "no assembler in the link image" >&2; exit 9; }
mkdir -p /w/obj /w/bin
as -o /w/start.o /w/x86_64.S
for s in /w/asm/*.s; do
  b=$(basename "$s" .s)
  as -o "/w/obj/$b.o" "$s"
  ld -o "/w/bin/$b" /w/start.o "/w/obj/$b.o"
  # A CompCert object for an emitted artifact has zero undefined symbols;
  # if that ever stops being true the link above fails rather than pulling
  # in a libc nobody reviewed.
done
chown -R "$TG_UID:$TG_GID" /w/bin /w/obj /w/start.o
"""


def link(args, wins: list[Window], out_dir: Path) -> None:
    """Phase 3: assemble and link, freestanding, in a linux/amd64 container."""
    (out_dir / "obj").mkdir(exist_ok=True)
    (out_dir / "bin").mkdir(exist_ok=True)
    shutil.copy(args.start_stub, out_dir / "x86_64.S")
    subprocess.run(
        ["docker", "run", "--platform", "linux/amd64", "--rm",
         "-e", f"TG_UID={os.getuid()}", "-e", f"TG_GID={os.getgid()}",
         "-v", f"{out_dir}:/w", "-w", "/w", args.link_image,
         "sh", "-c", LINK_SCRIPT], check=True)
    for win in wins:
        binary = out_dir / "bin" / f"w{win.index:05d}"
        win.bin_sha256 = sha256_file(binary)
        win.bin_bytes = binary.stat().st_size
        os.chmod(binary, 0o555)
    shutil.rmtree(out_dir / "obj", ignore_errors=True)
    (out_dir / "start.o").unlink(missing_ok=True)
    (out_dir / "x86_64.S").unlink()


MANIFEST_HEADER = "sparkinterval.leancompcert-seg-campaign-manifest.v1"


def write_manifest(args, wins: list[Window], out_dir: Path) -> Path:
    name, family, claim = MODES[args.mode]
    lines = [
        MANIFEST_HEADER,
        f"name={name}",
        f"producer=leancompcert",
        f"program=LeanCompCert.Ports.ArraySegSieve.mobiusProgram",
        f"emitter=proof_build/leancompcert_tdx/SegChainEmit.lean",
        f"reduced-family={family}",
        f"claim={claim}",
        f"cover-lo=1",
        f"range-lo={args.lo}",
        f"range-hi={args.hi}",
        f"window-ratio={args.ratio}",
        f"max-seg-len={args.max_seg_len}",
        f"windows={len(wins)}",
        f"primer-windows={sum(1 for w in wins if w.primer)}",
        f"initial-seed={T_BIAS}",
        f"compcert-version={args.compcert_version}",
        f"compcert-target=x86_64-linux",
        f"link=static-freestanding-no-libc",
        f"start-stub-sha256={sha256_file(Path(args.start_stub))}",
        f"success=every-window-exit-status-zero",
        f"output=false-or-true",
        "windows-begin",
    ]
    for w in wins:
        lines.append(
            f"w {w.index} lo={w.lo} hi={w.hi} segLen={w.seg_len} "
            f"segCount={w.seg_count} seed={w.seed} carry={w.carry} "
            f"carryMax={w.carry_max} carryMin={w.carry_min} "
            f"expectViol={w.expect_viol} primer={int(w.primer)} "
            f"threshold={w.threshold} cSha256={w.c_sha256} "
            f"binSha256={w.bin_sha256} binBytes={w.bin_bytes}")
    lines.append("windows-end")
    path = out_dir / "campaign-manifest.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def verify_manifest_chain(path: Path) -> dict:
    """Re-read the manifest and check every property the campaign relies on.

    This is deliberately written against the *text*, not against the in-memory
    objects, so that it is the same check the enclave entry point and a human
    reviewer perform.
    """
    header: dict[str, str] = {}
    rows = []
    inside = False
    for line in path.read_text().splitlines():
        if line == "windows-begin":
            inside = True
            continue
        if line == "windows-end":
            inside = False
            continue
        if inside:
            fields = line.split()
            assert fields[0] == "w"
            row = {"index": int(fields[1])}
            for field in fields[2:]:
                key, _, value = field.partition("=")
                row[key] = value
            rows.append(row)
        elif "=" in line:
            key, _, value = line.partition("=")
            header[key] = value

    problems = []
    if not rows:
        problems.append("manifest lists no windows")
    lo = int(header["cover-lo"])
    claim_lo = int(header["range-lo"])
    hi = int(header["range-hi"])
    seed = int(header["initial-seed"])
    for i, row in enumerate(rows):
        if row["index"] != i:
            problems.append(f"window {i}: out of order")
        if int(row["seed"]) != seed:
            problems.append(
                f"window {i}: chain break -- seed {row['seed']} is not the "
                f"previous window's carry {seed}")
        if int(row["lo"]) != lo:
            problems.append(
                f"window {i}: gap -- starts at {row['lo']}, expected {lo}")
        if int(row["lo"]) + int(row["segLen"]) * int(row["segCount"]) - 1 \
                != int(row["hi"]):
            problems.append(f"window {i}: segLen*segCount does not reach hi")
        if int(row["primer"]):
            # A primer window builds the running sum below the claimed range.
            # Its threshold verdict is deliberately not a claim, so it must
            # lie entirely below `range-lo` or it is silently unchecking part
            # of what the campaign asserts.
            if int(row["hi"]) >= claim_lo:
                problems.append(
                    f"window {i}: marked primer but reaches {row['hi']}, "
                    f"inside the claimed range starting at {claim_lo}")
        elif int(row["expectViol"]) != 0:
            problems.append(
                f"window {i}: inside the claimed range but expects "
                f"{row['expectViol']} threshold violations")
        seed = int(row["carry"])
        lo = int(row["hi"]) + 1
    if lo != hi + 1:
        problems.append(f"chain stops at {lo - 1}, not at {hi}")
    return {"header": header, "windows": rows, "problems": problems}


def canonical_definition(args, wins, manifest: Path) -> str:
    name, family, _ = MODES[args.mode]
    return "\n".join([
        "sparkinterval.registered-algorithm.v1",
        f"name={name}",
        "producer=leancompcert",
        "program=Ports.ArraySegSieve.mobiusProgram",
        f"reduced-family={family}",
        f"range=[{args.lo},{args.hi}]",
        f"windows={len(wins)}",
        f"manifest-sha256={sha256_file(manifest)}",
        f"manifest-bytes={manifest.stat().st_size}",
        f"compcert-version={args.compcert_version}",
        "compcert-target=x86_64-linux",
        "link=static-freestanding-no-libc",
        "semantics=AProgram.evalCC_compile",
        "success=every-window-exit-status-zero",
        "output=false-or-true",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--lo", type=int, required=True)
    parser.add_argument("--hi", type=int, required=True)
    parser.add_argument("--ratio", type=float, default=1.10)
    parser.add_argument("--max-seg-len", type=int, default=1_000_000)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--leancompcert", type=Path,
                        default=Path.home() / "leancompcert")
    parser.add_argument("--emitter", type=Path,
                        default=Path(__file__).parent / "SegChainEmit.lean")
    parser.add_argument("--ccomp", type=Path,
                        default=Path.home() / "compcert-x86_64" / "ccomp")
    parser.add_argument("--compcert-version", required=True,
                        help="a trust statement, never sniffed from the "
                             "binary: it names the compiler whose Coq "
                             "theorem the campaign relies on")
    parser.add_argument("--start-stub", type=Path,
                        default=Path.home() / "leancompcert" / "runtime" /
                        "start" / "x86_64.S")
    parser.add_argument("--link-image", default="alpine:3.20")
    parser.add_argument("--progress", type=int, default=10)
    parser.add_argument("--discovery-json", type=Path,
                        help="checkpoint / reuse a previous phase-1 result")
    parser.add_argument("--lean-pin-out", type=Path,
                        help="write the three Lean literals for "
                             "SparkInterval/Execution/LeanCompCertSegCampaign.lean")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # The chain must start at 1: `mobiusOverNSum n` is a running sum from
    # m = 1, so a window that starts at `args.lo` with a zero accumulator is
    # computing a different quantity.  Windows entirely below `args.lo` are
    # primers -- they build the carry and their threshold verdict is not a
    # claim.
    windows = schedule(1, args.lo - 1, args.ratio, args.max_seg_len) \
        if args.lo > 1 else []
    windows += schedule(args.lo, args.hi, args.ratio, args.max_seg_len)
    print(f"schedule: {len(windows)} windows covering [1, {args.hi}], "
          f"claimed from {args.lo}, at ratio {args.ratio}", flush=True)

    if args.discovery_json and args.discovery_json.exists():
        wins = [Window(**row)
                for row in json.loads(args.discovery_json.read_text())]
        print(f"reusing discovery for {len(wins)} windows", flush=True)
    else:
        print("phase 1: discovery (host, gcc)", flush=True)
        wins = discover(args, windows)
        if args.discovery_json:
            args.discovery_json.write_text(
                json.dumps([asdict(w) for w in wins], indent=1))

    print("phase 2: package (self-checking C, ccomp -S x86_64)", flush=True)
    package(args, wins, out_dir)
    print("phase 3: link (linux/amd64, as + ld, freestanding)", flush=True)
    link(args, wins, out_dir)

    print("phase 4: manifest and pin", flush=True)
    manifest = write_manifest(args, wins, out_dir)
    report = verify_manifest_chain(manifest)
    if report["problems"]:
        for problem in report["problems"]:
            print(f"  MANIFEST PROBLEM: {problem}", file=sys.stderr)
        raise SystemExit("REFUSED: the manifest does not describe a "
                         "gap-free, correctly chained cover")

    definition = canonical_definition(args, wins, manifest)
    (out_dir / "canonical-definition.txt").write_text(definition)
    algorithm_hash = hashlib.sha256(definition.encode()).hexdigest()
    pin = {
        "kind": "sparkinterval.leancompcert-seg-campaign-pin.v1",
        "mode": args.mode,
        "range": [args.lo, args.hi],
        "windows": len(wins),
        "total_integers": args.hi - args.lo + 1,
        "manifest_sha256": sha256_file(manifest),
        "manifest_bytes": manifest.stat().st_size,
        "canonical_definition": definition,
        "canonical_definition_bytes": len(definition.encode()),
        "algorithm_hash": algorithm_hash,
        "binary_bytes_total": sum(w.bin_bytes for w in wins),
    }
    (out_dir / "campaign-pin.json").write_text(json.dumps(pin, indent=2))
    if args.lean_pin_out:
        body = "".join(
            f'  "{line}\\n" ++\n' for line in definition.splitlines())
        body = body.rstrip(" ++\n") + "\n"
        args.lean_pin_out.write_text(
            "-- machine-derived; do not edit\n"
            "def segCampaignCanonicalDefinition : String :=\n" + body +
            f'\ndef segCampaignAlgorithmHash : Digest :=\n'
            f'  "{algorithm_hash}"\n')
    print(json.dumps({k: v for k, v in pin.items()
                      if k != "canonical_definition"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
