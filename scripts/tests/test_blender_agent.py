"""Include Blender skill's pure host/contract tests in repository CI (no Blender needed)."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]

def load_tests(loader, tests, pattern):
    return unittest.TestLoader().discover(str(ROOT/'jev-blender-use/tests'), pattern='test_*.py')
