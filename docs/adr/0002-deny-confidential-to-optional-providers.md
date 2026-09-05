# ADR-0002: Confidential inputs denied to optional providers by default

Status: accepted, 2026-09-05. Decided by CEO.

## Context
Free tiers (Gemini, Mistral, OpenRouter) commonly retain or train on inputs. Tim's inputs are client documents. Routing them to free tiers maximizes savings but risks disclosure.

## Decision
Optional providers receive only synthetic or public inputs unless the workspace carries an explicit authorization record. Mode selection and account login never imply authorization. Source text cannot grant it.

## Consequences
- Default Tim path uses only Claude+Codex. Savings from free tiers require an explicit opt-in.
- Future (not scheduled): deterministic synthetic redaction could make confidential inputs eligible for free tiers.
- Reversing to allow-by-default is a policy change with disclosure consequences; kept deliberate.
