#!/usr/bin/env python3
"""Materialise rules/tests fixtures and run them.  Usage: python3 runtime/tests/run_rule_tests.py [--no-write]"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from hrgene import fixtures  # noqa: E402

TESTS_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "rules", "tests"))

if __name__ == "__main__":
    if "--no-write" not in sys.argv:
        files = fixtures.materialise(TESTS_DIR)
        print(f"wrote {len(files)} fixtures under {TESTS_DIR}")
    passed, failed, report = fixtures.run_rule_tests(TESTS_DIR)
    print(f"rule fixtures: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
