---
name: workerbees
description: Delegate document analysis to cheap tool-free Workers with deterministic quote checks and a hard $0 spend cap. Triggers: "analyze these documents", "cited brief", "workerbees".
---
# workerbees — entry contract
1. Never send confidential text to gemini/mistral/openrouter without `.workerbees/authorization.json`.
2. Dispatch via `python3 -m workerbees.pipeline <source.md> <source_id> <mode> <workspace>`.
3. Exit 0 = Returned. Only the Verifier receipt moves status. Never report Verified yourself.
4. Quota exhausted → paused. No paid fallback exists. Tell the user.
5. Keys: run `python3 -m workerbees.keys <provider>` in the user's terminal. You never see keys.
Modes: lawyer (default), scientist, engineer.
