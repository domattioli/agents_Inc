# workerbees/adapters/claude.py
"""Claude Code Worker: logged-in -p, tool-free. --bare is excluded: it disables OAuth (probe 2026-09-05)."""
DISALLOWED = ["Bash","PowerShell","Read","Edit","Write","Glob","Grep","Task",
              "AskUserQuestion","TodoWrite","WebFetch","WebSearch","NotebookEdit"]

def build_cmd(model: str, prompt: str) -> list[str]:
    return ["claude", "-p", "--model", model, "--setting-sources", "", "--strict-mcp-config",
            "--disallowedTools", *DISALLOWED, prompt]
