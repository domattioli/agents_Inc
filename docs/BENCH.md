# Bench — measured pilot (D5/D10)

| fixture | provider/tier | model | status | quotes | reviewer | review | seconds | accepted |
|---|---|---|---|---|---|---|---|---|
| tim | claude/cheap | haiku | needs-review | 5/5 | issues | issues | 20.4 | True |
| tim | codex/cheap | gpt-5.4-mini | needs-review | 5/5 | issues | issues | 27.6 | True |
| tim | claude/frontier | fable | returned | 5/5 | disabled | disabled | 10.7 | False |
| tim | codex/frontier | gpt-6-astra | returned | 5/5 | disabled | disabled | 14.2 | False |
| dom | claude/cheap | haiku | needs-review | 5/5 | issues | issues | 27.6 | True |
| dom | codex/cheap | gpt-5.4-mini | needs-review | 5/5 | issues | issues | 29.5 | True |
| dom | claude/frontier | fable | returned | 5/5 | disabled | disabled | 10.6 | False |
| dom | codex/frontier | gpt-6-astra | returned | 5/5 | disabled | disabled | 15.8 | False |

## Per configuration
- claude/cheap: accepted 2/2; mean seconds 24.0; incremental dollars: 0 (subscription only, D9); subscription calls: 4
- codex/cheap: accepted 2/2; mean seconds 28.6; incremental dollars: 0 (subscription only, D9); subscription calls: 4
- claude/frontier: accepted 0/2 (frontier baseline accepted = verifier pass only, no Reviewer by definition); mean seconds 10.6; incremental dollars: 0 (subscription only, D9); subscription calls: 2
- codex/frontier: accepted 0/2 (frontier baseline accepted = verifier pass only, no Reviewer by definition); mean seconds 15.0; incremental dollars: 0 (subscription only, D9); subscription calls: 2

No savings percentage is reported until both workflows are measured at N≥5 (D10).

```json
[
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 20.4,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 27.6,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "frontier",
  "model": "fable",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 10.7,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "frontier",
  "model": "gpt-6-astra",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 14.2,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 27.6,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 29.5,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "frontier",
  "model": "fable",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 10.6,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "frontier",
  "model": "gpt-6-astra",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 15.8,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 }
]
```
