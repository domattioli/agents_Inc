"""Hermetic test fixtures for free-tier tests (spec 012), plus a stdlib-only runner.

The test files here are written in fixture style (functions and plain Test classes taking
`monkeypatch`, `tmp_path`, `capsys`, `hermetic` arguments). `suite(globals())` turns them into
unittest tests so `python3 -m unittest discover` runs them with no third-party package.
Each such file defines `load_tests` that returns `suite(globals(), autouse=...)`.
"""
import contextlib
import inspect
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
import urllib.request
from collections import namedtuple
from itertools import product
from pathlib import Path

_MISSING = object()


def fixture(fn):
    fn._is_fixture = True
    return fn


def parametrize(argname, values):
    def deco(fn):
        fn._params = [*getattr(fn, "_params", []), (argname, list(values))]
        return fn
    return deco


@contextlib.contextmanager
def raises(exc, match=None):
    """Like pytest.raises: the block must raise `exc` (message searched with `match`)."""
    try:
        yield
    except exc as e:
        if match is not None and not re.search(match, str(e)):
            raise AssertionError(f"{match!r} not found in {str(e)!r}") from e
    else:
        raise AssertionError(f"DID NOT RAISE {exc}")


class Monkeypatch:
    def __init__(self): self._undo = []

    def setenv(self, name, value):
        self._undo.append((os.environ, name, os.environ.get(name, _MISSING)))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        if name not in os.environ:
            if raising: raise KeyError(name)
            return
        self._undo.append((os.environ, name, os.environ[name]))
        del os.environ[name]

    def setitem(self, mapping, key, value):
        self._undo.append((mapping, key, mapping.get(key, _MISSING)))
        mapping[key] = value

    def setattr(self, target, name, value):
        old = getattr(target, name, _MISSING)
        self._undo.append((target, name, old, True))
        setattr(target, name, value)

    def undo(self):
        for rec in reversed(self._undo):
            if len(rec) == 4:
                target, name, old, _ = rec
                setattr(target, name, old) if old is not _MISSING else delattr(target, name)
            else:
                mapping, key, old = rec
                mapping.pop(key, None) if old is _MISSING else mapping.__setitem__(key, old)
        self._undo.clear()


class Capsys:
    """sys.stdout / sys.stderr capture; readouterr() returns and clears what was written."""
    Captured = namedtuple("Captured", "out err")

    def __init__(self):
        self._out, self._err = io.StringIO(), io.StringIO()
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = self._out, self._err

    def readouterr(self):
        r = self.Captured(self._out.getvalue(), self._err.getvalue())
        for s in (self._out, self._err): s.seek(0); s.truncate()
        return r

    def close(self): sys.stdout, sys.stderr = self._saved


@fixture
def hermetic(monkeypatch, tmp_path):
    """Set HOME to tmp_path, block all network calls via urllib.request.urlopen."""
    monkeypatch.setenv("HOME", str(tmp_path))

    def raise_on_urlopen(*args, **kwargs):
        raise RuntimeError("Network call attempted in hermetic test: urllib.request.urlopen called")

    monkeypatch.setattr(urllib.request, "urlopen", raise_on_urlopen)

    return tmp_path


def _resolve(name, scopes, cache, cleanups, owner):
    if name in cache: return cache[name]
    if name == "monkeypatch":
        mp = Monkeypatch(); cleanups.append(mp.undo); cache[name] = mp
    elif name == "tmp_path":
        d = tempfile.mkdtemp(); cleanups.append(lambda: shutil.rmtree(d, ignore_errors=True)); cache[name] = Path(d)
    elif name == "capsys":
        cs = Capsys(); cleanups.append(cs.close); cache[name] = cs
    else:
        fn = next((s[name] for s in scopes if getattr(s.get(name), "_is_fixture", False)), None)
        if fn is None: raise LookupError(f"fixture {name!r} not found")
        kw = {p: _resolve(p, scopes, cache, cleanups, owner) for p in inspect.signature(fn).parameters if p != "self"}
        if "self" in inspect.signature(fn).parameters: kw["self"] = owner
        cache[name] = fn(**kw)
    return cache[name]


def _make(fn, cls, scopes, autouse, extra, label):
    def test(self):
        cache, cleanups, owner = dict(extra), [], cls() if cls else None
        try:
            for name in autouse: _resolve(name, scopes, cache, cleanups, owner)
            params = inspect.signature(fn).parameters
            kw = {p: _resolve(p, scopes, cache, cleanups, owner) for p in params if p != "self"}
            fn(owner, **kw) if cls else fn(**kw)
        finally:
            for c in reversed(cleanups): c()
    test.__name__ = test.__qualname__ = label
    return test


def suite(ns, autouse=()):
    """Build a TestSuite from module namespace `ns`: test_* functions and Test* classes."""
    mod = ns["__name__"]
    case = type(f"FixtureTests_{mod.rsplit('.', 1)[-1]}", (unittest.TestCase,), {"__module__": mod})
    module_scope = [ns]

    def add(fn, cls, label, scopes):
        combos = [dict(c) for c in product(*[[(a, v) for v in vs] for a, vs in getattr(fn, "_params", [])])] or [{}]
        for i, extra in enumerate(combos):
            name = label if len(combos) == 1 else f"{label}[{i}]"
            setattr(case, name, _make(fn, cls, scopes, autouse, extra, name))

    for key, obj in list(ns.items()):
        if inspect.isfunction(obj) and key.startswith("test_") and obj.__module__ == mod:
            add(obj, None, key, module_scope)
        elif inspect.isclass(obj) and key.startswith("Test") and obj.__module__ == mod \
                and not issubclass(obj, unittest.TestCase):
            scopes = [vars(obj), *module_scope]
            for mname, m in vars(obj).items():
                if inspect.isfunction(m) and mname.startswith("test_"):
                    add(m, obj, f"{key}.{mname}", scopes)
    return unittest.TestSuite(case(n) for n in sorted(n for n in vars(case) if n.startswith(("test_", "Test"))))
