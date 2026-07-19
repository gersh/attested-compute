from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LOCAL_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PHASE_JARGON = re.compile(r"\b[Pp]hase\s+[0-9]+\b")
BASH_FENCE = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)


def documentation_files() -> list[Path]:
    paths = [
        ROOT / "README.md",
        ROOT / "attestation" / "README.md",
        ROOT / "gpu" / "platform" / "h100" / "README.md",
    ]
    for directory in ("docs", "examples", "specifications"):
        paths.extend((ROOT / directory).rglob("*.md"))
    return sorted(set(paths))


def local_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    if target.startswith("#"):
        return source.resolve()
    path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not path_text:
        return None
    return (source.parent / path_text).resolve()


def link_fragment(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    if "#" not in target:
        return None
    fragment = unquote(target.split("#", 1)[1].split("?", 1)[0])
    return fragment or None


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
        if not match:
            continue
        base = re.sub(r"[^\w\- ]", "", match.group(1).strip().lower())
        base = re.sub(r"[ -]+", "-", base).strip("-")
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


class DocumentationTests(unittest.TestCase):
    def test_all_local_markdown_links_resolve(self) -> None:
        failures: list[str] = []
        for source in documentation_files():
            text = source.read_text(encoding="utf-8")
            for match in LOCAL_LINK.finditer(text):
                target = local_target(source, match.group(1))
                if target is None:
                    continue
                if not target.exists():
                    failures.append(
                        f"{source.relative_to(ROOT)} -> {match.group(1)}"
                    )
                    continue
                fragment = link_fragment(match.group(1))
                if (
                    fragment is not None
                    and target.suffix.lower() == ".md"
                    and fragment not in markdown_anchors(target)
                ):
                    failures.append(
                        f"{source.relative_to(ROOT)} -> missing anchor "
                        f"{match.group(1)}"
                    )
        self.assertEqual(failures, [])

    def test_markdown_fences_are_balanced(self) -> None:
        failures = [
            str(path.relative_to(ROOT))
            for path in documentation_files()
            if path.read_text(encoding="utf-8").count("```") % 2
        ]
        self.assertEqual(failures, [])

    def test_shell_examples_parse(self) -> None:
        failures: list[str] = []
        for path in documentation_files():
            text = path.read_text(encoding="utf-8")
            for index, block in enumerate(BASH_FENCE.findall(text), start=1):
                result = subprocess.run(
                    ["bash", "-n"],
                    input=block,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode:
                    failures.append(
                        f"{path.relative_to(ROOT)} block {index}: "
                        f"{result.stderr.strip()}"
                    )
        self.assertEqual(failures, [])

    def test_development_phase_docs_and_jargon_are_gone(self) -> None:
        self.assertFalse((ROOT / "spec.md").exists())
        self.assertFalse((ROOT / "docs" / "IMPLEMENTATION_STATUS.md").exists())
        failures: list[str] = []
        for path in documentation_files():
            text = path.read_text(encoding="utf-8")
            if "IMPLEMENTATION_STATUS.md" in text or PHASE_JARGON.search(text):
                failures.append(str(path.relative_to(ROOT)))
        self.assertEqual(failures, [])

    def test_docs_index_lists_every_mutable_document(self) -> None:
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        missing = [
            str(path.relative_to(ROOT / "docs"))
            for path in sorted((ROOT / "docs").rglob("*.md"))
            if path.name != "README.md"
            and str(path.relative_to(ROOT / "docs")) not in index
        ]
        self.assertEqual(missing, [])

    def test_root_readme_exposes_user_and_verifier_paths(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "docs/README.md",
            "docs/USING.md",
            "docs/VERIFYING.md",
            "docs/CORRECTNESS_CLAIMS.md",
            "docs/TRUST_MODEL.md",
        ):
            with self.subTest(target=target):
                self.assertIn(target, readme)

    def test_lean_examples_are_clean_checkout_safe(self) -> None:
        failures: list[str] = []
        for path in documentation_files():
            text = path.read_text(encoding="utf-8")
            if "safe_lake_build.py --target sparkinterval-check-certificate" in text:
                failures.append(f"{path.relative_to(ROOT)}: target-only certificate build")
            if "safe_lean.sh SparkInterval/" in text:
                failures.append(f"{path.relative_to(ROOT)}: tracked source via safe_lean")
            if (
                "safe_lean.sh examples/lean/" in text
                and "safe_lake_build.py" not in text
            ):
                failures.append(f"{path.relative_to(ROOT)}: example imports not built")
        self.assertEqual(failures, [])

    def test_documented_dgx_bundle_path_is_current(self) -> None:
        failures = [
            str(path.relative_to(ROOT))
            for path in documentation_files()
            if "build/run/run-bundle.json" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
