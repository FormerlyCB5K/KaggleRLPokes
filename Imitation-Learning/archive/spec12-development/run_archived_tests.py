"""Run the archived Spec-12 Part A/B suites against the preserved builders."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
IMITATION_LEARNING = HERE.parent.parent
TESTS = HERE / "tests"


def main() -> int:
    sys.path.insert(0, str(IMITATION_LEARNING))
    suite = unittest.defaultTestLoader.discover(str(TESTS), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
