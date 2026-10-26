"""Spec 027 SC-002: `stdout.md`, `usage.json` and the verdict line of a dispatch run with the fake CLIs equal the files
in fixtures/live-events/golden/, which were recorded with the code before spec 027. Writes only to temp dirs."""
from __future__ import annotations
import contextlib
import os
import shutil
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from agents_inc.install import cli, dispatch, runtime
from agents_inc.install.receipt import InstallReceipt
from tests.test_dispatch_cli import CliBase

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures/live-events"
GOLDEN = FIXTURES / "golden"

_ALLOW = mock.patch.dict(os.environ, {dispatch.ALLOW_SANDBOXED_ENV: "1"})


def setUpModule():
    _ALLOW.start()


def tearDownModule():
    _ALLOW.stop()


def install_fake(dest: Path, name: str, source: str) -> Path:
    """Copy a fixture fake CLI into dest as an executable called `name` (the fixtures keep no exec bit)."""
    target = dest / name
    shutil.copyfile(FIXTURES / source, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


class FakeCliMixin:
    """PATH with the fake claude/codex first, plus `_dispatch`; mix in before CliBase. Holds no tests."""

    def setUp(self):
        super().setUp()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.patches = [mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                                                     "FAKE_PACE": "0"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def _dispatch(self, model: str, env: dict | None = None, args: tuple = ()):
        """Run `agents-inc dispatch` for model against the fake CLI; return (rc, stdout, stderr, run dir).
        env: extra environment for the run (FAKE_RC, FAKE_SLEEP, ...); args: extra dispatch arguments."""
        extra = contextlib.ExitStack()
        extra.enter_context(mock.patch.dict(os.environ, env or {}))
        if model in dispatch.CLAUDE_MODELS:
            install_fake(self.bin, "claude", "fake_claude")
            extra.enter_context(mock.patch.dict(os.environ, {"FAKE_FIXTURE": str(FIXTURES / "claude.jsonl")}))
        else:
            fake = install_fake(self.bin, "codex", "fake_codex")
            extra.enter_context(mock.patch.dict(os.environ, {"FAKE_FIXTURE": str(FIXTURES / "codex.jsonl")}))
            slug = runtime.load_model_map()[model]
            receipt = InstallReceipt(release_hash="a" * 64, python_path=Path(sys.executable), codex_path=fake)
            extra.enter_context(mock.patch.object(cli, "_efforts", return_value={slug: ["low", "medium", "high"]}))
            extra.enter_context(mock.patch.object(InstallReceipt, "load", return_value=receipt))
        with extra:
            rc, out, err = self._main("--slots", str(self._slots()), "--model", model, "--cwd", str(self.repo),
                                      "--run-dir", str(self.runs), *args)
        return rc, out, err, self._run_dir()


class GoldenTest(FakeCliMixin, CliBase):
    def _verdict(self, out: str, run_dir: Path) -> str:
        return out.strip().replace(str(run_dir), "<RUN_DIR>").replace(run_dir.name, "<RUN_ID>")

    def _check(self, model: str, name: str, has_usage: bool):
        rc, out, _, run = self._dispatch(model)
        self.assertEqual(rc, 0, out)
        self.assertEqual((run / "stdout.md").read_text(), (GOLDEN / f"{name}.stdout.md").read_text())
        if has_usage:
            self.assertEqual((run / "usage.json").read_text(), (GOLDEN / f"{name}.usage.json").read_text())
        else:
            self.assertFalse((run / "usage.json").exists())
        self.assertEqual(self._verdict(out, run) + "\n", (GOLDEN / f"{name}.verdict.txt").read_text())

    def test_claude_dispatch_matches_golden(self):
        self._check("haiku", "claude", has_usage=True)

    def test_codex_dispatch_matches_golden(self):
        self._check("sol", "codex", has_usage=False)


if __name__ == "__main__":
    unittest.main()
