import tempfile
import unittest
import os
from pathlib import Path

from agents_inc.install.transaction import LifecycleLock, TransactionJournal


class TransactionTest(unittest.TestCase):
    def test_lock_refuses_concurrent_lifecycle_operation(self):
        with tempfile.TemporaryDirectory() as raw:
            lock_path = Path(raw) / "lock"
            with LifecycleLock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "WB_CONFIG_CONFLICT"):
                    with LifecycleLock(lock_path): pass

    def test_journal_persists_intent_before_apply_and_cleans_on_commit(self):
        with tempfile.TemporaryDirectory() as raw:
            journal_path = Path(raw) / "journal.json"
            journal = TransactionJournal(journal_path).begin("install")
            journal.record_intent("link", Path(raw) / "current")
            self.assertIn('"applied": false', journal_path.read_text())
            journal.record_applied(); journal.commit()
            self.assertFalse(journal_path.exists())

    def test_recovery_restores_link_predecessor_after_applied_interruption(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); target = root / "current"; target.symlink_to("old")
            journal_path = root / "journal.json"
            journal = TransactionJournal(journal_path).begin("install")
            journal.record_intent("symlink", target, "old")
            target.unlink(); target.symlink_to("new")
            journal.record_applied()
            TransactionJournal.recover(journal_path)
            self.assertEqual(target.readlink(), Path("old"))
            self.assertFalse(journal_path.exists())

    def test_failure_between_mutation_and_applied_marker_recovers_proven_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); target = root / "current"; target.symlink_to("old")
            journal_path = root / "journal.json"; journal = TransactionJournal(journal_path).begin("install")
            old = os.environ.get("AGENTS_INC_FAIL_AFTER"); os.environ["AGENTS_INC_FAIL_AFTER"] = "symlink"
            try:
                with self.assertRaisesRegex(RuntimeError, "injected failure"):
                    journal.apply("symlink", target, "old", "new", lambda: (target.unlink(), target.symlink_to("new")))
            finally:
                if old is None: os.environ.pop("AGENTS_INC_FAIL_AFTER", None)
                else: os.environ["AGENTS_INC_FAIL_AFTER"] = old
            TransactionJournal.recover(journal_path)
            self.assertEqual(target.readlink(), Path("old"))
