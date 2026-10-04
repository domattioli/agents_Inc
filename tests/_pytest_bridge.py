"""Run a pytest-style test file under `unittest discover`.

Five test files use pytest fixtures (hermetic, monkeypatch, tmp_path,
parametrize) and define no unittest.TestCase, so `unittest discover`
collected zero tests from them. Each of those files defines `load_tests`,
which calls `bridge_suite`. The bridge collects the file's pytest node ids,
runs the whole file once in a pytest subprocess with a JUnit XML report,
and exposes one unittest test per node id that asserts that node's outcome.

pytest itself never sees the generated TestCase: it is built inside
load_tests, which pytest does not call.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pytest(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
                          cwd=ROOT, capture_output=True, text=True, env=env)


def _collect(path: Path) -> list[str]:
    r = _pytest("--collect-only", "-q", str(path))
    ids = [ln.strip() for ln in r.stdout.splitlines() if "::" in ln]
    if r.returncode != 0 or not ids:
        raise RuntimeError(f"pytest collection failed for {path}:\n{r.stdout}\n{r.stderr}")
    return ids


def _junit_key(case: ET.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    parts = classname.split(".")
    # classname is "tests.test_x.TestClass" or "tests.test_x"
    cls = parts[-1] if parts and parts[-1].startswith("Test") else ""
    return f"{cls}::{name}" if cls else name


def bridge_suite(test_file: str) -> unittest.TestSuite:
    path = Path(test_file).resolve()
    node_ids = _collect(path)
    results: dict[str, str] = {}

    def run_once() -> None:
        if results:
            return
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = os.path.join(tmp, "junit.xml")
            r = _pytest("-q", f"--junitxml={xml_path}", str(path))
            if not os.path.exists(xml_path):
                raise RuntimeError(f"pytest produced no report for {path}:\n{r.stdout}\n{r.stderr}")
            for case in ET.parse(xml_path).getroot().iter("testcase"):
                outcome = "passed"
                for child in case:
                    if child.tag in ("failure", "error"):
                        outcome = f"{child.tag}: {child.get('message', '')}\n{child.text or ''}"
                        break
                    if child.tag == "skipped":
                        outcome = "skipped"
                results[_junit_key(case)] = outcome

    class PytestBridge(unittest.TestCase):
        pass

    PytestBridge.__name__ = PytestBridge.__qualname__ = f"PytestBridge_{path.stem}"
    PytestBridge.__module__ = path.stem

    def make(key: str):
        def test(self):
            run_once()
            outcome = results.get(key)
            if outcome is None:
                self.fail(f"no pytest result for {key}")
            if outcome == "skipped":
                self.skipTest("skipped under pytest")
            if outcome != "passed":
                self.fail(outcome)
        return test

    suite = unittest.TestSuite()
    for i, node in enumerate(node_ids):
        key = node.split("::", 1)[1]
        name = "test_" + re.sub(r"\W+", "_", key)
        name = f"{name}_{i}" if hasattr(PytestBridge, name) else name
        setattr(PytestBridge, name, make(key))
        suite.addTest(PytestBridge(name))
    return suite
