#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch, verify, and build Platt's pinned PT21 windowed zeta checker.

The upstream repository does not publish a license.  This tool therefore
never copies its source into this repository: it verifies a detached checkout
and compiles directly from that checkout.  The generated executable is a
local build product and is not a redistributable project asset.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "specifications" / "PLATT_PT21_WINDOWED_UPSTREAM.json"
SOURCE_SET_DOMAIN = b"sparkinterval/platt-pt21-reviewed-source-set/v1\0"
INTERPOLATION_CORRECTION = (
    ROOT / "patches" / "platt-pt21" / "0001-apply-interpolation-error.patch"
)
INTERPOLATION_CORRECTION_SHA256 = (
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3"
)
UPSTREAM_INTER_C_SHA256 = (
    "71568e572b571ee08394acec4cb03f9feb351407187f70fa569d7d2f1ab86d39"
)
CORRECTED_INTER_C_SHA256 = (
    "4dba515103aa3c03a4c8385b9093296ecb86652d33ee916aac905e42ed0457cf"
)
UPSTREAM_PARAMETERS_H_SHA256 = (
    "b2fe59cfc850297aa9e75f997b84f838707a6b388dd8a514f4f1d703dcbe4a93"
)
CORRECTED_PARAMETERS_H_SHA256 = (
    "fa0232a59098784fd474ff4de8df493908116f96e370416da94861e3a1093b20"
)


class PlattWindowedSourceError(RuntimeError):
    """The upstream source, dependency, build, or known answer differs."""


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env={**os.environ, "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PlattWindowedSourceError(f"cannot run {' '.join(argv)}: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr[-4000:].strip() or completed.stdout[-4000:].strip()
        raise PlattWindowedSourceError(
            f"{' '.join(argv)} failed with status {completed.returncode}: {detail}"
        )
    return completed


def load_pin(path: Path = PIN) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlattWindowedSourceError(f"cannot load source pin: {error}") from error
    required = {
        "commit",
        "files",
        "kind",
        "known_answers",
        "license",
        "license_note",
        "name",
        "redistribution",
        "repository",
        "reviewed_source_bytes",
        "reviewed_source_file_count",
        "reviewed_source_hash_domain",
        "reviewed_source_sha256",
        "source_directory",
        "source_parameters",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PlattWindowedSourceError("source pin fields changed")
    if value["kind"] != "sparkinterval.pinned_platt_pt21_windowed_source.v1":
        raise PlattWindowedSourceError("unsupported source pin kind")
    if value["license"] != "NOASSERTION":
        raise PlattWindowedSourceError("upstream license status changed without review")
    if value["redistribution"] != "not-authorized-by-this-manifest":
        raise PlattWindowedSourceError("upstream redistribution policy changed")
    if value["reviewed_source_hash_domain"] != SOURCE_SET_DOMAIN[:-1].decode("ascii"):
        raise PlattWindowedSourceError("reviewed source hash domain changed")
    return value


def fetch(checkout: Path, pin: dict[str, Any]) -> None:
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--no-checkout", pin["repository"], str(checkout)], timeout=600)
    _run(["git", "checkout", "--detach", pin["commit"]], cwd=checkout)


def _git(checkout: Path, *arguments: str) -> str:
    return _run(["git", *arguments], cwd=checkout).stdout.strip()


def reviewed_source_identity(
    checkout: Path, pin: dict[str, Any]
) -> dict[str, int | str]:
    rows = pin["files"]
    if not isinstance(rows, list) or not rows:
        raise PlattWindowedSourceError("source pin contains no reviewed files")
    digest = hashlib.sha256(SOURCE_SET_DOMAIN)
    total = 0
    seen: set[str] = set()
    normalized: list[tuple[str, bytes]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
            raise PlattWindowedSourceError("malformed reviewed source row")
        name = row["path"]
        relative = PurePosixPath(name)
        if (
            not isinstance(name, str)
            or relative.is_absolute()
            or any(part in ("", ".", "..") for part in relative.parts)
            or name != relative.as_posix()
            or name in seen
        ):
            raise PlattWindowedSourceError(f"unsafe or duplicate source path: {name!r}")
        seen.add(name)
        path = checkout.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise PlattWindowedSourceError(f"reviewed source is not a regular file: {name}")
        raw = path.read_bytes()
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
            row["sha256"],
            row["size_bytes"],
        ):
            raise PlattWindowedSourceError(f"reviewed source differs: {name}")
        normalized.append((name, raw))
    for name, raw in sorted(normalized):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
        total += len(raw)
    identity: dict[str, int | str] = {
        "file_count": len(normalized),
        "size_bytes": total,
        "sha256": digest.hexdigest(),
    }
    expected = {
        "file_count": pin["reviewed_source_file_count"],
        "size_bytes": pin["reviewed_source_bytes"],
        "sha256": pin["reviewed_source_sha256"],
    }
    if identity != expected:
        raise PlattWindowedSourceError("aggregate reviewed source identity differs")
    return identity


def verify_checkout(checkout: Path, pin: dict[str, Any]) -> dict[str, Any]:
    if checkout.is_symlink() or not checkout.is_dir():
        raise PlattWindowedSourceError(f"checkout does not exist: {checkout}")
    commit = _git(checkout, "rev-parse", "HEAD^{commit}")
    if commit != pin["commit"]:
        raise PlattWindowedSourceError(f"expected commit {pin['commit']}, got {commit}")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PlattWindowedSourceError("checkout is dirty")
    identity = reviewed_source_identity(checkout, pin)
    return {
        "accepted": True,
        "commit": commit,
        "license": pin["license"],
        "redistribution": pin["redistribution"],
        "reviewed_source": identity,
    }


def _regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PlattWindowedSourceError(f"missing {label}: {path}")
    return path


def _library_directory(prefix: Path, stem: str) -> Path:
    candidates = [prefix / "lib", prefix / "lib64"]
    lib = prefix / "lib"
    if lib.is_dir():
        candidates.extend(sorted(path for path in lib.iterdir() if path.is_dir()))
    for directory in candidates:
        for suffix in (".so", ".dylib", ".a"):
            candidate = directory / f"lib{stem}{suffix}"
            if candidate.exists():
                return directory
    raise PlattWindowedSourceError(f"missing lib{stem} under {prefix}")


def prepare_corrected_source(checkout: Path, destination: Path) -> dict[str, Any]:
    """Copy the reviewed source set to a temporary tree and apply one patch.

    The pinned split-file `zeta_arb` source initializes the Appendix C error
    ball as `intererr`, but `inter.c::arb_inter_t` never adds it to `f_res`.
    Older source in the same upstream repository does perform that widening.
    Compiling the uncorrected source would therefore silently omit both the
    Weiss/non-bandlimited and finite-tail interpolation errors.

    The original checkout remains pristine.  Every byte of the local patch
    and its sole modified output file is pinned below so this transformation
    is fail-closed and visible in measured build evidence.
    """

    patch_raw = _regular(
        INTERPOLATION_CORRECTION, "Platt interpolation correction"
    ).read_bytes()
    patch_sha256 = hashlib.sha256(patch_raw).hexdigest()
    if patch_sha256 != INTERPOLATION_CORRECTION_SHA256:
        raise PlattWindowedSourceError("interpolation correction patch differs")

    source_root = checkout / "zeta_arb"
    reviewed_names = (
        "Makefile",
        "arb_fft.h",
        "arb_win_zeta.h",
        "arb_zeta.c",
        "inter.c",
        "inter.h",
        "parameters.h",
        "turing.c",
        "turing.h",
        "win_zeta.c",
        "win_zeta.h",
    )
    destination_root = destination / "zeta_arb"
    destination_root.mkdir(parents=True, exist_ok=False)
    for name in reviewed_names:
        source = _regular(source_root / name, "reviewed Platt source")
        shutil.copyfile(source, destination_root / name)

    original_inter = (destination_root / "inter.c").read_bytes()
    if hashlib.sha256(original_inter).hexdigest() != UPSTREAM_INTER_C_SHA256:
        raise PlattWindowedSourceError(
            "cannot apply interpolation correction to an unreviewed inter.c"
        )
    original_parameters = (destination_root / "parameters.h").read_bytes()
    if (
        hashlib.sha256(original_parameters).hexdigest()
        != UPSTREAM_PARAMETERS_H_SHA256
    ):
        raise PlattWindowedSourceError(
            "cannot apply interpolation correction to unreviewed parameters.h"
        )
    _run(
        [
            "patch",
            "--batch",
            "--forward",
            "-p1",
            "-i",
            str(INTERPOLATION_CORRECTION.resolve()),
        ],
        cwd=destination,
    )
    corrected_inter = (destination_root / "inter.c").read_bytes()
    corrected_sha256 = hashlib.sha256(corrected_inter).hexdigest()
    if corrected_sha256 != CORRECTED_INTER_C_SHA256:
        raise PlattWindowedSourceError("corrected inter.c identity differs")
    corrected_text = corrected_inter.decode("utf-8")
    if corrected_text.count("arb_add(f_res,f_res,intererr,prec);") != 1:
        raise PlattWindowedSourceError(
            "interpolation correction did not add exactly one value widening"
        )
    corrected_parameters = (destination_root / "parameters.h").read_bytes()
    corrected_parameters_sha256 = hashlib.sha256(corrected_parameters).hexdigest()
    if corrected_parameters_sha256 != CORRECTED_PARAMETERS_H_SHA256:
        raise PlattWindowedSourceError("corrected parameters.h identity differs")
    if corrected_parameters.count(b"0x1.557aebd2564edp-132") != 1:
        raise PlattWindowedSourceError(
            "corrected source lacks the upward binary64 interpolation radius"
        )
    radius = Fraction.from_float(float.fromhex("0x1.557aebd2564edp-132"))
    exact_budget = Fraction(245, 10**42)
    if radius < exact_budget:
        raise PlattWindowedSourceError(
            "corrected binary64 interpolation radius rounds below Lean budget"
        )
    return {
        "kind": "sparkinterval.platt_pt21_interpolation_error_correction.v1",
        "patch_sha256": patch_sha256,
        "upstream_inter_c_sha256": UPSTREAM_INTER_C_SHA256,
        "corrected_inter_c_sha256": corrected_sha256,
        "upstream_parameters_h_sha256": UPSTREAM_PARAMETERS_H_SHA256,
        "corrected_parameters_h_sha256": corrected_parameters_sha256,
        "interpolation_error_binary64_hex": "0x1.557aebd2564edp-132",
        "interpolation_error_binary64_exact_fraction":
            f"{radius.numerator}/{radius.denominator}",
        "interpolation_error_at_least_exact_245e_minus_42": True,
        "applies_total_interpolation_error_to_value": True,
        "derivative_error_not_claimed": True,
    }


def build(
    checkout: Path,
    output: Path,
    flint_prefix: Path,
    mpfr_prefix: Path | None,
    compiler: str,
) -> dict[str, Any]:
    output = output.resolve()
    flint_prefix = flint_prefix.resolve()
    if mpfr_prefix is not None:
        mpfr_prefix = mpfr_prefix.resolve()
    include_root = flint_prefix / "include"
    include_flint = include_root / "flint"
    library_root = _library_directory(flint_prefix, "flint")
    _regular(include_flint / "flint.h", "FLINT header")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sparkinterval-platt-pt21-") as temporary:
        corrected_checkout = Path(temporary)
        correction = prepare_corrected_source(checkout, corrected_checkout)
        source_root = corrected_checkout / "zeta_arb"
        sources = [
            source_root / name
            for name in ("arb_zeta.c", "turing.c", "inter.c", "win_zeta.c")
        ]
        command = [
            compiler,
            "-O3",
            "-finline-functions",
            "-fomit-frame-pointer",
            "-Wall",
            f"-I{include_flint}",
            f"-I{include_root}",
        ]
        if mpfr_prefix is not None:
            command.append(f"-I{mpfr_prefix / 'include'}")
        command.extend(str(path) for path in sources)
        command.extend([f"-L{library_root}"])
        if mpfr_prefix is not None:
            command.append(f"-L{_library_directory(mpfr_prefix, 'mpfr')}")
        command.extend(
            [
                f"-Wl,-rpath,{library_root.resolve()}",
                "-o",
                str(output),
                "-lflint",
                "-lmpfr",
                "-lgmp",
                "-lm",
                "-lpthread",
            ]
        )
        _run(command, cwd=source_root, timeout=900)
    raw = _regular(output, "compiled checker").read_bytes()
    return {
        "path": str(output.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "compiler": _run([compiler, "--version"]).stdout.splitlines()[0],
        "source_correction": correction,
    }


def _known_answer_output(
    executable: Path, precision: int, lower: int, upper: int, count: int
) -> dict[str, Any]:
    step = upper - lower
    completed = _run(
        [str(executable), str(precision), str(lower), "1", str(step)],
        timeout=300,
    )
    output = completed.stdout
    success = (
        f"All {count} zeros found in region {lower:.6f} to {upper:.6f} using stat points."
    )
    forbidden = ("Unknown", "Missed", "Problem", "failed", "Failed", "Exiting")
    if output.count(success) != 1 or any(token in output for token in forbidden):
        raise PlattWindowedSourceError(
            "known-answer run did not produce exactly one fail-closed success line"
        )
    return {
        "height_lower": lower,
        "height_upper": upper,
        "zero_count": count,
        "stdout_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def test_known_answers(executable: Path, pin: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = pin["source_parameters"]
    precision = parameters["working_precision_bits"]
    results = []
    for answer in pin["known_answers"]:
        results.append(
            _known_answer_output(
                executable,
                precision,
                answer["height_lower"],
                answer["height_upper"],
                answer["zero_count"],
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--build", type=Path, metavar="EXECUTABLE")
    parser.add_argument("--flint-prefix", type=Path)
    parser.add_argument("--mpfr-prefix", type=Path)
    parser.add_argument("--compiler", default="cc")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        pin = load_pin()
        if not args.verify_only:
            fetch(args.checkout, pin)
        report = verify_checkout(args.checkout, pin)
        if args.build is not None:
            if args.flint_prefix is None:
                raise PlattWindowedSourceError("--build requires --flint-prefix")
            report["build"] = build(
                args.checkout,
                args.build,
                args.flint_prefix,
                args.mpfr_prefix,
                args.compiler,
            )
        if args.test:
            executable = args.build
            if executable is None:
                raise PlattWindowedSourceError("--test requires --build EXECUTABLE")
            report["known_answers"] = test_known_answers(executable, pin)
    except (PlattWindowedSourceError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
