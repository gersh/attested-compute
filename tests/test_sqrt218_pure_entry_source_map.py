from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Sqrt218PureEntrySourceMapTest(unittest.TestCase):
    def test_source_map_is_complete(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "audit_sqrt218_pure_entry_source_map.py"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("50 accepting-path functions mapped", result.stdout)


if __name__ == "__main__":
    unittest.main()
