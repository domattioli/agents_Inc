"""Stable, user-scoped installation paths."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    releases: Path
    current: Path
    launcher: Path
    receipt: Path
    roster: Path
    state: Path
    claude_skills: Path
    codex_skills: Path

    @property
    def lock(self) -> Path: return self.home / ".local/state/agents-inc/lifecycle.lock"

    @property
    def journal(self) -> Path: return self.home / ".local/state/agents-inc/lifecycle.json"

    @classmethod
    def for_home(cls, home: Path) -> "InstallPaths":
        if not home.is_absolute():
            raise ValueError("installation home must be absolute")
        home = Path(home)
        return cls(
            home=home,
            releases=home / ".local/share/agents-inc/releases",
            current=home / ".local/share/agents-inc/current",
            launcher=home / ".local/bin/agents-inc",
            receipt=home / ".config/agents-inc/install.json",
            roster=home / ".config/agents-inc/roster.json",
            state=home / ".local/state/agents-inc",
            claude_skills=home / ".claude/skills",
            codex_skills=home / ".agents/skills",
        )
