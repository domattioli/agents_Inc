import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock
from agents_inc.install import doctor
from agents_inc.install.paths import InstallPaths


class _R:
    release_hash = "h"
    def __init__(self, codex_path): self.codex_path = codex_path


def _run(codex_path):
    with tempfile.TemporaryDirectory() as raw:
        paths = InstallPaths.for_home(Path(raw) / "home")
        rel = paths.releases / "h"; rel.mkdir(parents=True)
        paths.current.parent.mkdir(parents=True, exist_ok=True); paths.current.symlink_to(rel)
        for root in (paths.claude_skills, paths.codex_skills):
            root.mkdir(parents=True, exist_ok=True)
            for n in ("workerbee", "codex-bridge"): (root / n).symlink_to(rel)
        with mock.patch.object(doctor.InstallReceipt, "load", return_value=_R(codex_path)), \
             mock.patch.object(doctor, "verify_bundle", return_value=True):
            return doctor.check_install(paths)


class DoctorCodexOptionalTest(unittest.TestCase):
    def test_none_codex_is_warning_not_failure(self):
        r = _run(None)
        self.assertTrue(r.ready); self.assertEqual(r.codes, ()); self.assertEqual(r.warnings, ("WB_CLI_NOT_FOUND",))
        self.assertEqual(r.as_dict()["warnings"], ["WB_CLI_NOT_FOUND"])

    def test_recorded_missing_codex_is_failure(self):
        r = _run(Path("/nonexistent/codex"))
        self.assertFalse(r.ready); self.assertIn("WB_CLI_NOT_FOUND", r.codes); self.assertEqual(r.warnings, ())

    def test_present_executable_codex_ready(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "codex"; c.write_text("#!/bin/sh\n"); c.chmod(0o755)
            r = _run(c)
        self.assertTrue(r.ready); self.assertEqual(r.warnings, ())

    def test_non_executable_codex_is_failure(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "codex"; c.write_text("x"); c.chmod(0o644)
            r = _run(c)
        self.assertFalse(r.ready); self.assertIn("WB_CLI_NOT_FOUND", r.codes)
