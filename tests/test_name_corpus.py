"""Unit tests for tools/name_corpus.py -- stdlib unittest only."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import name_corpus as nc  # noqa: E402


class TestTokenize(unittest.TestCase):
    def test_stopword_strip(self):
        toks = nc.tokenize("the swarm and the hive are here")
        self.assertNotIn("the", toks)
        self.assertNotIn("and", toks)
        self.assertNotIn("are", toks)
        self.assertNotIn("here", toks)
        self.assertIn("swarm", toks)
        self.assertIn("hive", toks)

    def test_noise_words_stripped(self):
        toks = nc.tokenize("run the tool call and check the file line output")
        for noisy in ("run", "tool", "call", "file", "line", "output"):
            self.assertNotIn(noisy, toks)

    def test_secret_redaction(self):
        text = "my key is sk-abcdefghij1234567890 do not leak it"
        cleaned = nc.clean_text(text)
        self.assertNotIn("sk-abcdefghij1234567890", cleaned)
        toks = nc.tokenize(text)
        self.assertNotIn("abcdefghij1234567890", toks)

    def test_email_redaction(self):
        text = "contact me at balmy-drapery-putt@duck.com about the swarm"
        cleaned = nc.clean_text(text)
        self.assertNotIn("duck.com", cleaned)
        toks = nc.tokenize(text)
        self.assertIn("swarm", toks)
        self.assertNotIn("duck", toks)

    def test_bearer_token_redaction(self):
        cleaned = nc.clean_text("Authorization: Bearer abc123xyz999 swarm graph")
        self.assertNotIn("abc123xyz999", cleaned)

    def test_code_block_removal(self):
        text = "graph theory ```python\nimport os\nsk-should-not-appear\n``` bee colony"
        toks = nc.tokenize(text)
        self.assertNotIn("import", toks)
        self.assertIn("graph", toks)
        self.assertIn("colony", toks)

    def test_inline_code_removal(self):
        toks = nc.tokenize("the `run_all()` swarm function is graph-based")
        self.assertNotIn("run_all", toks)
        self.assertIn("swarm", toks)

    def test_url_and_path_removal(self):
        toks = nc.tokenize(
            "see https://example.com/foo/bar and /Users/domattioli/Projects/agents_for_dummies/tools/name.py for the mesh graph"
        )
        self.assertIn("mesh", toks)
        self.assertIn("graph", toks)
        self.assertNotIn("example", toks)
        self.assertNotIn("com", toks)

    def test_hash_uuid_and_number_removal(self):
        toks = nc.tokenize(
            "commit 3f9a8c2 uuid 123e4567-e89b-12d3-a456-426614174000 and 12345 nodes in the mesh"
        )
        self.assertIn("mesh", toks)
        self.assertNotIn("12345", toks)
        self.assertNotIn("3f9a8c2", toks)

    def test_min_length_and_repeat_collapse(self):
        toks = nc.tokenize("ab cd swarm swarm swarm graph")
        self.assertNotIn("ab", toks)
        self.assertNotIn("cd", toks)
        self.assertEqual(toks.count("swarm"), 1)
        self.assertIn("graph", toks)


class TestThemes(unittest.TestCase):
    def test_theme_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "out")
            os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
            with open(os.path.join(tmp, "docs", "a.md"), "w") as fh:
                fh.write("swarm swarm hive bee colony ledger delegate worker")
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                summary = nc.build_corpus(out_dir, None, 200.0)
            finally:
                os.chdir(cwd)
            self.assertGreaterEqual(summary["themes"]["swarm"], 1)
            self.assertGreaterEqual(summary["themes"]["hive"], 1)
            themes_path = os.path.join(out_dir, "themes.tsv")
            self.assertTrue(os.path.exists(themes_path))
            with open(themes_path) as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), len(nc.SEED_THEMES))


class TestJsonlShapeTolerance(unittest.TestCase):
    def test_unknown_keys_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            jsonl_path = os.path.join(tmp, "sess.jsonl")
            records = [
                {"type": "summary", "unknownField": "xyz"},
                {"type": "user", "message": {"role": "user", "content": "graph swarm theory"}, "weirdKey": 1},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "secret internal plan"},
                            {"type": "text", "text": "the hive mind coordinates delegation"},
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                        ],
                    },
                },
                {"not_even_a_type_field": True},
                "not even json object",
            ]
            with open(jsonl_path, "w") as fh:
                for rec in records:
                    if isinstance(rec, str):
                        fh.write(rec + "\n")
                    else:
                        fh.write(json.dumps(rec) + "\n")
                fh.write("\n")  # blank line tolerance
            texts = nc.extract_transcript_texts(jsonl_path, None)
            joined = " ".join(texts)
            self.assertIn("graph", joined)
            self.assertIn("hive mind", joined)
            self.assertNotIn("secret internal plan", joined)

    def test_malformed_json_line_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            jsonl_path = os.path.join(tmp, "bad.jsonl")
            with open(jsonl_path, "w") as fh:
                fh.write("{not valid json\n")
                fh.write(json.dumps({"type": "user", "message": {"content": "ok graph"}}) + "\n")
            texts = nc.extract_transcript_texts(jsonl_path, None)
            self.assertEqual(texts, ["ok graph"])


class TestEnvExclusion(unittest.TestCase):
    def test_env_path_never_read(self):
        self.assertEqual(nc.read_doc_text("/some/path/.env"), "")


if __name__ == "__main__":
    unittest.main()
