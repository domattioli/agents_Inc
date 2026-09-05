#!/usr/bin/env python3
"""Build a compact naming corpus from local logs/transcripts + repo docs.

Purpose: CEO wants candidate company/repo names (theme: graphs, swarms, bees,
delegation, governance). Scans local sources, strips noise/secrets, emits a
small set of files (token corpus, freq table, bigram table, theme counts) a
cheap model can mine later with minimal tokens.

Sources (read-only): Claude Code transcripts ~/.claude/projects/*/*.jsonl
(one JSON record per line; only type in {"user","assistant"}, and only
`text`-type content blocks / plain string content -- tool_use/tool_result/
thinking blocks are skipped as harness noise); repo docs docs/**/*.md,
CONTEXT.md, skills/*/SKILL.md, .introspect/**/*.md (if present).

Usage: python3 tools/name_corpus.py --out <dir> [--since YYYY-MM-DD] [--max-mb N]

Outputs in --out: corpus.txt (space-joined kept tokens, one source per line,
prefixed "[src:<short>] "), freq.tsv ("token\\tcount" desc), bigrams.tsv (top
500 "tokenA tokenB\\tcount" desc), themes.tsv ("theme\\tcount" for seed themes).

Never writes text matching secret patterns (API keys, bearer tokens, emails --
redacted before counting). Never opens any path containing ".env".
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

# Seed themes the CEO cares about (graphs / swarms / bees / delegation / governance).
SEED_THEMES = [
    "graph", "swarm", "hive", "bee", "colony", "ledger", "delegate", "worker",
    "queen", "drone", "node", "edge", "mesh", "forage", "verify", "gate",
]

# Standard English stopwords (~150), flat set for O(1) lookup.
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "could", "did", "didn't", "do",
    "does", "doesn't", "doing", "don", "don't", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into",
    "is", "isn't", "it", "it's", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves", "yes", "okay", "im", "ive", "id", "youre", "youve", "dont",
    "doesnt", "didnt", "isnt", "wasnt", "werent", "wouldnt", "shouldnt", "cant",
    "couldnt", "thats", "theres", "heres", "lets", "also", "etc", "via", "per",
    "let", "sure", "thanks", "thank", "please", "hi", "hey", "hello",
}

# Tool/harness noise words -- common in transcripts, uninformative for naming.
NOISE_WORDS = {
    "tool", "tools", "call", "calls", "called", "calling", "file", "files", "line",
    "lines", "run", "running", "ran", "test", "tests", "tested", "ok", "okay",
    "exit", "code", "commit", "commits", "branch", "repo", "path", "paths", "dir",
    "directory", "cmd", "bash", "shell", "output", "input", "result", "results",
    "error", "errors", "true", "false", "null", "none", "todo", "done", "read",
    "write", "edit", "edited", "using", "use", "used", "session", "message",
    "messages", "assistant", "user", "system", "claude", "json", "str", "int",
    "def", "class", "import", "return", "value", "values", "type", "types",
    "param", "params", "arg", "args", "function", "functions", "var", "config",
    "success", "successful", "failed", "failure", "yes", "no", "ll", "ve", "re",
    "didn", "doesn", "isn", "wasn", "aren", "won",
}

STOP_AND_NOISE = STOPWORDS | NOISE_WORDS

# Secret-like patterns, redacted before any token is counted / written out.
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{10,}"),
    re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"bearer\s+\S+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
URL_RE = re.compile(r"https?://\S+")
PATH_RE = re.compile(r"(?:/[\w.\-]+){2,}/?")
HASH_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    r"|\b[0-9a-f]{7,40}\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\b\d+\b")
PUNCT_RE = re.compile(r"[{}\[\]\"',:;<>()|\\/=+*#@!?~^%&]")
TOKEN_RE = re.compile(r"[a-z]+")


def redact_secrets(text: str) -> str:
    """Replace any secret-shaped substring with a fixed placeholder."""
    for pat in SECRET_PATTERNS:
        text = pat.sub(" [redacted] ", text)
    return text


def clean_text(text: str) -> str:
    """Strip code blocks, URLs, paths, hashes/uuids, numbers, JSON punct."""
    text = redact_secrets(text)
    text = CODE_BLOCK_RE.sub(" ", text)
    text = INLINE_CODE_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = HASH_UUID_RE.sub(" ", text)
    text = PATH_RE.sub(" ", text)
    text = NUMBER_RE.sub(" ", text)
    text = PUNCT_RE.sub(" ", text)
    return text.lower()


def tokenize(text: str) -> list[str]:
    """Lowercase-clean text into kept tokens (>=3 chars, not stop/noise)."""
    tokens = TOKEN_RE.findall(clean_text(text))
    out, prev = [], None
    for tok in tokens:
        if len(tok) < 3 or tok in STOP_AND_NOISE:
            prev = None
            continue
        if tok == prev:  # collapse immediate repeats
            continue
        out.append(tok)
        prev = tok
    return out


def extract_transcript_texts(path: str, since_ts: float | None) -> list[str]:
    """Pull human/assistant prose text blocks out of one .jsonl transcript."""
    texts = []
    try:
        with open(path, "r", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(rec, dict) or rec.get("type") not in ("user", "assistant"):
                    continue
                if since_ts is not None:
                    ts = rec.get("timestamp")
                    if ts:
                        try:
                            rec_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                            if rec_ts < since_ts:
                                continue
                        except ValueError:
                            pass
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text")
                            if isinstance(t, str):
                                texts.append(t)
    except OSError:
        pass
    return texts


def iter_transcript_files() -> list[str]:
    return sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")))


def iter_doc_files(repo_root: str) -> list[str]:
    """Enumerate docs/**/*.md, CONTEXT.md, skills/*/SKILL.md, .introspect/**/*.md
    -- skipping anything with '.env' in the path."""
    patterns = [
        os.path.join(repo_root, "docs", "**", "*.md"),
        os.path.join(repo_root, "CONTEXT.md"),
        os.path.join(repo_root, "skills", "*", "SKILL.md"),
        os.path.join(repo_root, ".introspect", "**", "*.md"),
    ]
    found = set()
    for pat in patterns:
        found.update(glob.glob(pat, recursive=True))
    return sorted(p for p in found if ".env" not in p)


def read_doc_text(path: str) -> str:
    if ".env" in path:
        return ""
    try:
        with open(path, "r", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def short_src(path: str, kind: str) -> str:
    """Short human-readable source tag for the corpus.txt prefix."""
    if kind == "transcript":
        parts = path.split(os.sep)
        proj = parts[-2] if len(parts) >= 2 else "transcript"
        return f"transcript:{proj}"
    return f"doc:{os.path.basename(path)}"


def _ingest(tokens, corpus_fh, src_tag, freq, bigram_counter, theme_counter):
    """Update freq/bigram/theme counters and write one corpus.txt line."""
    if not tokens:
        return
    freq.update(tokens)
    for a, b in zip(tokens, tokens[1:]):
        bigram_counter[(a, b)] += 1
    for tok in tokens:
        if tok in theme_counter:
            theme_counter[tok] += 1
    corpus_fh.write(f"[src:{src_tag}] " + " ".join(tokens) + "\n")


def build_corpus(out_dir: str, since: str | None, max_mb: float) -> dict:
    """Run the full pipeline; returns a summary dict."""
    since_ts = None
    if since:
        since_ts = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()

    repo_root = os.getcwd()
    max_bytes = max_mb * 1024 * 1024
    raw_bytes = 0
    n_sources = 0

    os.makedirs(out_dir, exist_ok=True)
    freq = Counter()
    bigram_counter = Counter()
    theme_counter = Counter(dict.fromkeys(SEED_THEMES, 0))

    with open(os.path.join(out_dir, "corpus.txt"), "w") as corpus_fh:
        for tpath in iter_transcript_files():  # transcripts
            if raw_bytes >= max_bytes:
                break
            try:
                size = os.path.getsize(tpath)
            except OSError:
                continue
            if raw_bytes + size > max_bytes and raw_bytes > 0:
                continue
            texts = extract_transcript_texts(tpath, since_ts)
            if not texts:
                continue
            raw_bytes += size
            n_sources += 1
            tokens: list[str] = []
            for t in texts:
                tokens.extend(tokenize(t))
            _ingest(tokens, corpus_fh, short_src(tpath, "transcript"), freq, bigram_counter, theme_counter)

        for dpath in iter_doc_files(repo_root):  # repo docs
            if raw_bytes >= max_bytes:
                break
            text = read_doc_text(dpath)
            if not text:
                continue
            raw_bytes += len(text.encode("utf-8", errors="ignore"))
            n_sources += 1
            _ingest(tokenize(text), corpus_fh, short_src(dpath, "doc"), freq, bigram_counter, theme_counter)

    with open(os.path.join(out_dir, "freq.tsv"), "w") as fh:
        for tok, count in freq.most_common():
            fh.write(f"{tok}\t{count}\n")

    with open(os.path.join(out_dir, "bigrams.tsv"), "w") as fh:
        for (a, b), count in bigram_counter.most_common(500):
            fh.write(f"{a} {b}\t{count}\n")

    with open(os.path.join(out_dir, "themes.tsv"), "w") as fh:
        for theme in SEED_THEMES:
            fh.write(f"{theme}\t{theme_counter[theme]}\n")

    raw_mb = raw_bytes / (1024 * 1024)
    reduction_pct = 0.0
    if raw_bytes > 0:
        # Reduction = fraction of raw bytes not represented in kept-token chars.
        kept_chars = sum(len(t) + 1 for t in freq.elements())
        reduction_pct = max(0.0, 100.0 * (1 - kept_chars / raw_bytes))

    return {
        "sources": n_sources,
        "raw_mb": raw_mb,
        "tokens_kept": sum(freq.values()),
        "unique_tokens": len(freq),
        "reduction_pct": reduction_pct,
        "freq": freq,
        "themes": theme_counter,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--since", default=None, help="only records after YYYY-MM-DD")
    parser.add_argument("--max-mb", type=float, default=200.0, help="max raw MB to scan (default 200)")
    args = parser.parse_args(argv)

    summary = build_corpus(args.out, args.since, args.max_mb)
    print(
        f"sources={summary['sources']} raw_mb={summary['raw_mb']:.2f} "
        f"tokens_kept={summary['tokens_kept']} unique_tokens={summary['unique_tokens']} "
        f"reduction_pct={summary['reduction_pct']:.1f}%"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
