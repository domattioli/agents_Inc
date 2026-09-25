"""Hermetic test fixtures for free-tier tests (spec 012)."""
import pytest
import urllib.request


@pytest.fixture
def hermetic(monkeypatch, tmp_path):
    """Set HOME to tmp_path, block all network calls via urllib.request.urlopen."""
    monkeypatch.setenv("HOME", str(tmp_path))

    def raise_on_urlopen(*args, **kwargs):
        raise RuntimeError("Network call attempted in hermetic test: urllib.request.urlopen called")

    monkeypatch.setattr(urllib.request, "urlopen", raise_on_urlopen)

    return tmp_path
