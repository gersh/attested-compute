from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LOCAL_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
# Development-phase jargon: prose that describes the PROJECT as being in a
# numbered phase of a plan.  The bare pattern `phase <n>` is too broad -- these
# documents legitimately describe algorithmic phases (a GPU sieve's phase 1, a
# table row "fallback phase 1", and captured program output reading
# "Phase 2 fallbacks : 0"), and rewriting technical prose or literal output to
# satisfy a regular expression would make the documentation worse, not better.
# So match a numbered phase only where it is used as a plan label: as a
# heading, or next to planning vocabulary.
PHASE_JARGON = re.compile(
    r"^#+\s*[Pp]hase\s+[0-9]+\b"                      # a heading
    r"|\b[Pp]hase\s+[0-9]+\s+(?:is|was|will|has|have)\b"
    r"|\b[Pp]hase\s+[0-9]+\s*[-:\u2014]\s*(?:complete|done|in progress|planned)"
    r"|\b(?:complete|completed|finish(?:ed)?|begin(?:s|ning)?|start(?:s|ed)?|enter(?:s|ed|ing)?"
    r"|plan(?:ned)?|milestone|deliverable|roadmap|scope)\s+(?:of\s+|for\s+)?[Pp]hase\s+[0-9]+\b"
    r"|\b[Pp]hase\s+[0-9]+\s+(?:plan|milestone|deliverable|roadmap|scope|work|effort)\b",
    re.MULTILINE,
)
BASH_FENCE = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)


def documentation_files() -> list[Path]:
    paths = [
        ROOT / "README.md",
        ROOT / "attestation" / "README.md",
        ROOT / "attestation" / "phala" / "README.md",
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

    def test_phase_jargon_rule_catches_plan_language_and_spares_algorithms(self) -> None:
        """The jargon rule was narrowed; this is what stops it eroding further.

        It used to match any `phase <n>`, which flagged four documents for
        describing a GPU sieve's phase 1, a table row, and captured program
        output reading `Phase 2 fallbacks : 0`.  Rewriting technical prose and
        literal output to satisfy a regular expression makes documentation
        worse, so the rule now targets plan language only.  Narrowing a gate is
        exactly when it needs a test in both directions.
        """
        plan_language = [
            "## Phase 1", "# Phase 2: hardening", "Phase 2 is complete",
            "Phase 1 was delivered in June", "we completed Phase 3",
            "the Phase 2 plan", "Phase 1 - complete", "entering Phase 4",
            "Phase 5 will ship next quarter", "Phase 2 milestone",
            "beginning Phase 6", "Phase 7 deliverable", "started Phase 8",
            "Phase 9 scope", "the roadmap for Phase 10",
        ]
        algorithmic = [
            "global-atomic sieve, `244.002 ms` to phase 1",
            "| fallback phase 1 | 52 | 96 |",
            "Phase 2 fallbacks      : 0",
            "For exact source phase 7, structural reconstruction",
            "compares every live packed word before phase 1",
            "warp + shifted phase 1 + packed count",
            "the phase 1 kernel writes 64 words",
            "phase 2 of the sieve emits packed words",
        ]
        for text in plan_language:
            with self.subTest(should_flag=text):
                self.assertIsNotNone(PHASE_JARGON.search(text))
        for text in algorithmic:
            with self.subTest(should_allow=text):
                self.assertIsNone(PHASE_JARGON.search(text))

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
