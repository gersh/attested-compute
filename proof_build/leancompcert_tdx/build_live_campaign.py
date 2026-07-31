#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build one chained **per-integer** leancompcert campaign for a Phala TDX CVM.

`build_seg_campaign.py` packages `Ports.ArraySegSieve.mobiusProgram`, whose
window is compared against its majorant **once**, in the epilogue, at the
window's worst endpoint.  That forces a geometric window schedule, and the
schedule can only stop on a boundary the whole window survives -- which is why
the committed `platt-stronger-range` campaign stops at 7 727 065 383, i.e.
3 204 integers short of the reduced family's range.

This builder packages `Ports.ArraySegSieve.mobiusLiveProgram` instead.  It
tests `|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))` at **every integer**, on a two-limb
accumulator at scale `2^(63+k)` with `k = mobWideBits = 15`.  Two consequences,
and they are the whole reason this file exists:

* a window is a unit of memory and nothing else, so the cover stops exactly at
  the endpoint asked for, not at a schedule boundary; and
* the round-to-nearest budget the test subtracts is `⌈n/2^17⌉ + 1` rather than
  `⌈n/2⌉` -- 65 536 times smaller, `2.25·10^-9` of the threshold at
  `n ≈ 7.7·10^9` instead of `1.47·10^-4` -- which is what carries the last
  3 204 integers.

Four phases, the same four as the windowed builder:

1. **discovery** (host, gcc, hosted driver) -- run the chain and record each
   link's violation count and its four result slots.
2. **package** (host, `gcc -E` then `ccomp -S`) -- re-emit each link with the
   *self-checking* freestanding driver carrying the discovered expectations,
   and compile it to x86_64 assembly.  This is the step CompCert's
   semantic-preservation theorem covers.
3. **link** (linux/amd64 container, `as` + `ld`) -- assemble and link against
   `runtime/start/x86_64.S`, freestanding, no libc.
4. **pin** -- write `campaign-manifest.txt`, check the cover and the chain
   inside it, and derive `canonicalDefinition` / `algorithmHash`.

## The three integers that fail, and why none of them is a defect

The chain always opens at `n = 1`, because that is the only carry-in that is
not a hand-computed number: the accumulator is the bare bias `2^(64+k)`.  The
opening link therefore reports exactly three failed tests:

* `n = 1` -- the family is genuinely false there: `Σ_{m≤1} μ(m)/m = 1` against
  `1/(2√2) = 0.354`;
* `n = 2` -- likewise: `1/2` against `1/(2√3) = 0.289`;
* `n = 4` -- an exact tie the relaxed test cannot resolve.  `Σ_{m≤4} μ(m)/m`
  is `1/6` and `⌈√5⌉ = 3`, so `|V|` lands exactly on `⌊2^(63+k)/3⌋` and the
  `+1` for the shift's truncation tips it over.  The family holds there with
  enormous room (`1/6` against `1/(2√5) = 0.224`); this is the `⌈·⌉`
  relaxation, which costs a relative `1/√(n+1)`, being coarse at a tiny `n`.
  Swept exhaustively, `n = 4` is the ONLY integer in `[3, 7.727·10^9]` where
  the relaxation costs anything.

So the opening link is a **primer**: it lies entirely below the claimed range,
its threshold verdict is deliberately not a claim, and the campaign checker
requires exactly that (`primer=1` and `hi < range-lo`).  Every other link must
report zero, and a nonzero count anywhere else is refused outright -- unlike
the windowed builder there is no schedule to blame, so a failure is a genuine
counterexample to the relaxed test at some individual integer.

## Why the manifest format is byte-compatible with the windowed one

`tools/tg_seg_campaign_check.py` and
`proof_build/leancompcert_tdx/run_seg_campaign.sh` are the routines that run
inside the TD.  Neither is modified here, and neither needs to be: the chained
state of a live link is two 64-bit limbs, and it travels through the manifest
as the **single integer** `tLo + 2^64 · tHi`.  The checker's chain rule --
link `k+1`'s `seed` is link `k`'s `carry` -- then applies unchanged, and the
extra `carryTLo`/`carryTHi`/`carryC`/`carryCSq` columns are reviewable detail
the checker ignores.
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
    r"memoryBytes=(?P<memoryBytes>\d+) wideBits=(?P<wideBits>\d+) "
    r"seedC=(?P<seedC>\d+) seedCSq=(?P<seedCSq>\d+)"
)

# `Ports.ArraySegSieve.mobWideBits`.  The accumulator opens at the bare bias
# `2^(64+k)`: low limb 0, high limb `2^k`.
MOB_WIDE_BITS = 15
INITIAL_TLO = 0
INITIAL_THI = 2 ** MOB_WIDE_BITS

CLAIM = "abs (mobiusOverNSum n) <= 1 / (2 * sqrt (n+1))"
FAMILY = "MathExtras.Reductions.PlattStrongerRangeNatFamily"
NAME = "platt-stronger-range-live"

# The manifest kind the in-TD checker requires.  Unchanged on purpose; see the
# module docstring.
MANIFEST_HEADER = "sparkinterval.leancompcert-seg-campaign-manifest.v1"


def combine(t_lo: int, t_hi: int) -> int:
    return t_lo + (t_hi << 64)


@dataclass
class Link:
    index: int
    lo: int
    hi: int
    seg_len: int
    seg_count: int
    seed_lo: int
    seed_hi: int
    expect_viol: int
    primer: bool
    carry_lo: int
    carry_hi: int
    carry_c: int
    carry_csq: int
    array_len: int
    loop_count: int
    memory_bytes: int
    seconds: float = 0.0
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


def schedule(primer_hi: int, lo: int, hi: int, seg_len: int, link_len: int):
    """`(lo, hi, segLen, segCount, primer)` for every link, in chain order.

    The cover always opens at 1.  `[1, primer_hi]` is one link and is the
    primer; the claimed range `[lo, hi]` is then covered by links of at most
    `link_len` integers, each a whole number of `seg_len`-wide segments, with a
    final short link whose `seg_len` is exactly what is left.  `seg_len` is a
    memory parameter and nothing else, so shrinking it on the last link costs
    nothing but a smaller array.

    The one hazard this closes by construction: `seg_count * seg_len` is what
    the artifact actually walks, so a link whose geometry does not land on its
    `hi` would test past the end of the range.  Every branch below lands on
    `hi` exactly, and `tools/tg_seg_campaign_check.py` re-checks it from the
    manifest text inside the TD.
    """
    if primer_hi + 1 != lo:
        raise SystemExit(
            f"the primer must abut the claimed range: primer-hi={primer_hi}, "
            f"range-lo={lo}")
    out = [(1, primer_hi, primer_hi, 1, True)]
    if link_len % seg_len:
        raise SystemExit("--link-len must be a multiple of --seg-len")
    cur = lo
    while cur <= hi:
        left = hi - cur + 1
        if left >= link_len:
            span_len, span_count = seg_len, link_len // seg_len
        elif left >= seg_len:
            span_len, span_count = seg_len, left // seg_len
        else:
            span_len, span_count = left, 1
        end = cur + span_len * span_count - 1
        out.append((cur, end, span_len, span_count, False))
        cur = end + 1
    return out


def emit(leancompcert: Path, emitter: Path, lo: int, seg_len: int,
         seg_count: int, seed_lo: int, seed_hi: int, out: Path,
         expect=None) -> dict:
    args = [str(lo), str(seg_len), str(seg_count), str(seed_lo), str(seed_hi)]
    if expect is not None:
        args += [str(x) for x in expect]
    args.append(str(out))
    proc = subprocess.run(
        ["lake", "env", "lean", "--run", str(emitter)] + args,
        cwd=str(leancompcert), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"emit failed for lo={lo}:\n{proc.stdout}{proc.stderr}")
    match = EMIT_LINE.search(proc.stdout)
    if match is None:
        raise SystemExit(f"emitter printed no parsable line:\n{proc.stdout}")
    return {k: (v if k == "mode" else int(v))
            for k, v in match.groupdict().items()}


def discover(args, links) -> list[Link]:
    """Phase 1: run the chain on the build host and record every carry-out."""
    import time
    work = Path(tempfile.mkdtemp(prefix="livedisc."))
    out: list[Link] = []
    seed_lo, seed_hi = INITIAL_TLO, INITIAL_THI
    try:
        for index, (lo, hi, seg_len, seg_count, primer) in enumerate(links):
            csrc = work / "w.c"
            csrc.unlink(missing_ok=True)
            info = emit(args.leancompcert, args.emitter, lo, seg_len,
                        seg_count, seed_lo, seed_hi, csrc)
            if info["hi"] != hi:
                raise SystemExit(f"emitter says hi={info['hi']}, wanted {hi}")
            exe = work / "w"
            subprocess.run(["gcc", "-O2", "-o", str(exe), str(csrc)], check=True)
            started = time.time()
            run = subprocess.run([str(exe)], capture_output=True, text=True,
                                 check=True)
            seconds = time.time() - started
            cells = {}
            for line in run.stdout.splitlines():
                key, _, value = line.partition(" ")
                cells[key] = int(value)
            violations = cells["violations"]
            if violations != 0 and not primer:
                raise SystemExit(
                    f"REFUSED: link {index} covering [{lo}, {hi}] reports "
                    f"{violations} failed tests inside the claimed range.  A "
                    f"per-integer link suffers no schedule tightening, so this "
                    f"is a counterexample to the relaxed test at some "
                    f"individual integer, not an invocation error.")
            out.append(Link(
                index=index, lo=lo, hi=hi, seg_len=seg_len,
                seg_count=seg_count, seed_lo=seed_lo, seed_hi=seed_hi,
                expect_viol=violations, primer=primer,
                carry_lo=cells["slot0"], carry_hi=cells["slot1"],
                carry_c=cells["slot2"], carry_csq=cells["slot3"],
                array_len=info["arrayLen"], loop_count=info["loopCount"],
                memory_bytes=info["memoryBytes"], seconds=round(seconds, 3)))
            seed_lo, seed_hi = cells["slot0"], cells["slot1"]
            if args.discovery_json:
                args.discovery_json.write_text(
                    json.dumps([asdict(w) for w in out], indent=1))
            print(f"  link {index:3d} [{lo}, {hi}] viol={violations} "
                  f"carry=({seed_lo},{seed_hi}) {seconds:.1f}s", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def package(args, links: list[Link], out_dir: Path) -> None:
    """Phase 2: self-checking C, then x86_64 assembly from CompCert.

    The links are independent here -- each is re-emitted with the
    expectations phase 1 discovered -- so they are packaged in parallel.  The
    chain is a property of the *values* carried in the manifest, not of the
    order in which the C is produced, and every artifact is hashed afterwards.
    """
    from concurrent.futures import ThreadPoolExecutor

    asm_dir = out_dir / "asm"
    csrc_dir = out_dir / "c"
    asm_dir.mkdir(parents=True, exist_ok=True)
    csrc_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.package_jobs) as pool:
        for _ in pool.map(lambda link: package_one(args, link, out_dir),
                          links):
            pass


def package_one(args, link: Link, out_dir: Path) -> None:
    asm_dir = out_dir / "asm"
    csrc_dir = out_dir / "c"
    if True:
        csrc = csrc_dir / f"w{link.index:05d}.c"
        emit(args.leancompcert, args.emitter, link.lo, link.seg_len,
             link.seg_count, link.seed_lo, link.seed_hi, csrc,
             expect=(link.expect_viol, link.carry_lo, link.carry_hi,
                     link.carry_c, link.carry_csq))
        text = csrc.read_text()
        # A leancompcert artifact must not need the Lean runtime.  The include
        # is emitted unconditionally; any surviving `lean_` call means the
        # artifact is genuinely not standalone.
        stripped = "\n".join(
            line for line in text.splitlines()
            if line.strip() != "#include <lean/lean.h>")
        if "lean_" in stripped:
            raise SystemExit(f"REFUSED: {csrc} calls the Lean runtime")
        csrc.write_text(stripped + "\n")
        link.c_sha256 = sha256_file(csrc)
        link.c_bytes = csrc.stat().st_size

        pre = csrc.with_suffix(".i")
        # `compcert.ini` delegates preprocessing to `gcc -m64`, which the
        # host's aarch64 gcc rejects, so preprocess separately and hand
        # CompCert the already-preprocessed unit.
        subprocess.run(["gcc", "-E", "-U__GNUC__", "-U__SIZEOF_INT128__",
                        "-o", str(pre), str(csrc)], check=True)
        asm = asm_dir / f"w{link.index:05d}.s"
        subprocess.run([str(args.ccomp), "-S", "-O2", "-o", str(asm),
                        str(pre)], check=True)
        pre.unlink()
        link.asm_sha256 = sha256_file(asm)
        print(f"  packaged link {link.index:3d}", flush=True)


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
done
chown -R "$TG_UID:$TG_GID" /w/bin /w/obj /w/start.o
"""


def link_phase(args, links: list[Link], out_dir: Path) -> None:
    """Phase 3: assemble and link, freestanding, in a linux/amd64 container."""
    (out_dir / "obj").mkdir(exist_ok=True)
    (out_dir / "bin").mkdir(exist_ok=True)
    shutil.copy(args.start_stub, out_dir / "x86_64.S")
    subprocess.run(
        ["docker", "run", "--platform", "linux/amd64", "--rm",
         "-e", f"TG_UID={os.getuid()}", "-e", f"TG_GID={os.getgid()}",
         "-v", f"{out_dir}:/w", "-w", "/w", args.link_image,
         "sh", "-c", LINK_SCRIPT], check=True)
    for link in links:
        binary = out_dir / "bin" / f"w{link.index:05d}"
        link.bin_sha256 = sha256_file(binary)
        link.bin_bytes = binary.stat().st_size
        os.chmod(binary, 0o555)
    shutil.rmtree(out_dir / "obj", ignore_errors=True)
    (out_dir / "start.o").unlink(missing_ok=True)
    (out_dir / "x86_64.S").unlink()


def write_manifest(args, links: list[Link], out_dir: Path) -> Path:
    lines = [
        MANIFEST_HEADER,
        f"name={NAME}",
        "producer=leancompcert",
        "program=LeanCompCert.Ports.ArraySegSieve.mobiusLiveProgram",
        "emitter=proof_build/leancompcert_tdx/LiveChainEmit.lean",
        f"reduced-family={FAMILY}",
        f"claim={CLAIM}",
        "cover-lo=1",
        f"range-lo={args.lo}",
        f"range-hi={args.hi}",
        f"accumulator-bits={63 + MOB_WIDE_BITS}",
        f"seg-len={args.seg_len}",
        f"link-len={args.link_len}",
        f"windows={len(links)}",
        f"primer-windows={sum(1 for w in links if w.primer)}",
        f"initial-seed={combine(INITIAL_TLO, INITIAL_THI)}",
        f"compcert-version={args.compcert_version}",
        "compcert-target=x86_64-linux",
        "link=static-freestanding-no-libc",
        f"start-stub-sha256={sha256_file(Path(args.start_stub))}",
        "success=every-window-exit-status-zero",
        "output=false-or-true",
        "windows-begin",
    ]
    for w in links:
        lines.append(
            f"w {w.index} lo={w.lo} hi={w.hi} segLen={w.seg_len} "
            f"segCount={w.seg_count} seed={combine(w.seed_lo, w.seed_hi)} "
            f"carry={combine(w.carry_lo, w.carry_hi)} "
            f"carryTLo={w.carry_lo} carryTHi={w.carry_hi} "
            f"carryC={w.carry_c} carryCSq={w.carry_csq} "
            f"expectViol={w.expect_viol} primer={int(w.primer)} "
            f"cSha256={w.c_sha256} binSha256={w.bin_sha256} "
            f"binBytes={w.bin_bytes}")
    lines.append("windows-end")
    path = out_dir / "campaign-manifest.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def canonical_definition(args, links, manifest: Path) -> str:
    return "\n".join([
        "sparkinterval.registered-algorithm.v1",
        f"name={NAME}",
        "producer=leancompcert",
        "program=Ports.ArraySegSieve.mobiusLiveProgram",
        f"reduced-family={FAMILY}",
        f"range=[{args.lo},{args.hi}]",
        f"windows={len(links)}",
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
    parser.add_argument("--lo", type=int, required=True)
    parser.add_argument("--hi", type=int, required=True)
    parser.add_argument("--primer-hi", type=int, default=4)
    parser.add_argument("--seg-len", type=int, default=1_000_000)
    parser.add_argument("--link-len", type=int, default=1_000_000_000)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--leancompcert", type=Path,
                        default=Path.home() / "leancompcert")
    parser.add_argument("--emitter", type=Path,
                        default=Path(__file__).parent / "LiveChainEmit.lean")
    parser.add_argument("--ccomp", type=Path,
                        default=Path.home() / "compcert-x86_64" / "ccomp")
    parser.add_argument("--compcert-version", required=True,
                        help="a trust statement, never sniffed from the "
                             "binary: it names the compiler whose Coq theorem "
                             "the campaign relies on")
    parser.add_argument("--start-stub", type=Path,
                        default=Path.home() / "leancompcert" / "runtime" /
                        "start" / "x86_64.S")
    parser.add_argument("--link-image", default="alpine:3.20")
    parser.add_argument("--package-jobs", type=int, default=6,
                        help="how many links to re-emit and compile at once; "
                             "phase 2 is embarrassingly parallel")
    parser.add_argument("--discovery-json", type=Path,
                        help="checkpoint / reuse a previous phase-1 result")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    links_plan = schedule(args.primer_hi, args.lo, args.hi, args.seg_len,
                          args.link_len)
    print(f"schedule: {len(links_plan)} links covering [1, {args.hi}], "
          f"claimed from {args.lo}", flush=True)

    if args.discovery_json and args.discovery_json.exists():
        links = [Link(**row)
                 for row in json.loads(args.discovery_json.read_text())]
        print(f"reusing discovery for {len(links)} links", flush=True)
    else:
        print("phase 1: discovery (host, gcc)", flush=True)
        links = discover(args, links_plan)
        if args.discovery_json:
            args.discovery_json.write_text(
                json.dumps([asdict(w) for w in links], indent=1))

    print("phase 2: package (self-checking C, ccomp -S x86_64)", flush=True)
    package(args, links, out_dir)
    print("phase 3: link (linux/amd64, as + ld, freestanding)", flush=True)
    link_phase(args, links, out_dir)

    print("phase 4: manifest and pin", flush=True)
    manifest = write_manifest(args, links, out_dir)

    # The same routine the TD runs, run here, against the manifest text.
    checker = Path(__file__).resolve().parents[2] / "tools" / \
        "tg_seg_campaign_check.py"
    proc = subprocess.run([sys.executable, str(checker), "--campaign-root",
                           str(out_dir)], capture_output=True, text=True)
    print(proc.stdout + proc.stderr, end="")
    if proc.returncode != 0:
        raise SystemExit("REFUSED: the manifest does not describe a gap-free, "
                         "correctly chained cover")

    definition = canonical_definition(args, links, manifest)
    (out_dir / "canonical-definition.txt").write_text(definition)
    algorithm_hash = hashlib.sha256(definition.encode()).hexdigest()
    pin = {
        "kind": "sparkinterval.leancompcert-live-campaign-pin.v1",
        "mode": "plattstronglive",
        "range": [args.lo, args.hi],
        "cover": [1, args.hi],
        "windows": len(links),
        "total_integers": args.hi - args.lo + 1,
        "manifest_sha256": sha256_file(manifest),
        "manifest_bytes": manifest.stat().st_size,
        "canonical_definition": definition,
        "canonical_definition_bytes": len(definition.encode()),
        "algorithm_hash": algorithm_hash,
        "binary_bytes_total": sum(w.bin_bytes for w in links),
        "host_seconds_total": round(sum(w.seconds for w in links), 1),
    }
    (out_dir / "campaign-pin.json").write_text(json.dumps(pin, indent=2))
    print(json.dumps({k: v for k, v in pin.items()
                      if k != "canonical_definition"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
