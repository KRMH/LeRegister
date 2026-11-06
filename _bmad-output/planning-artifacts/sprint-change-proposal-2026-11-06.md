---
title: "Sprint Change Proposal: LLM free-text input"
date: 2026-11-06
status: approved and applied
scope: moderate
mode: batch
---

# Sprint Change Proposal: LLM free-text input (LeRegister)

## 1. Issue Summary

While writing the epics, the Owner asked to use a free LLM for the conversation with the Bot. Decision: a hosted free tier for the MVP, a local model later. FR-13 and Epic 7 ("Talk naturally") were added to `epics.md`. The PRD, architecture spine and SPEC still say "no AI model" and list free-text parsing as out of scope.

**Category:** new requirement from the Owner. **Evidence:** PRD §6 and §7.2, ARCHITECTURE-SPINE AD-7, SPEC Constraints and Non-goals.

## 2. Impact Analysis

- **Epics:** only Epic 7 is affected, and it is already written. Epics 1-6 are unchanged. Strict Commands work without Epic 7.
- **Stories:** none implemented. No rollback needed.
- **Artifact conflicts:** PRD (§4.7 new, §6, §7.1, §7.2, §3, §9), ARCHITECTURE-SPINE (AD-7, AD-5, AD-3, AD-16 new, ports, stack, map, deferred), SPEC (CAP-11 new, Constraints, Non-goals, Assumptions). `epics.md` already updated.
- **UX:** none exists.
- **Technical:** new `Interpreter` port, `adapters/llm/` adapter, `proposals` side table, two journal event types, one LLM client dependency.
- **Risk:** guest names and phones may reach a third party on the hosted free tier (accepted by the Owner for the MVP).

## 3. Recommended Approach

Direct adjustment (documents only). Effort low, risk medium (privacy, accepted). MVP impact: minimal, since free text is the last epic and the strict parser ships first.

## 4. Detailed Change Proposals

### P1. PRD §6

- **Untrusted input.** OLD: `[ASSUMPTION: the parser is rule-based, so no AI model is needed in v1. If one is added later, its output must be validated against a fixed schema and it must have no ability to act.]` NEW: the strict parser is rule-based and the only authority on validity. An optional LLM Interpreter (§4.7) may propose a Command from free text. Its output is validated against a fixed schema and shown to the Owner for confirmation, and it has no ability to act.
- **Cost.** Add: LLM use must be free, hosted free tier for the MVP, local model later.
- **Data protection.** Add: the hosted LLM receives only the Owner's own message text, which may include a guest name or phone. The Owner accepts this for the MVP.

### P2. PRD scope, feature, glossary

- §7.1 In scope: add free-text input through a hosted free LLM, always confirmed.
- §7.2 Out of scope: remove "Free-text natural-language parsing" and its `[NOTE FOR PM]`.
- New §4.7 / FR-13 Natural-language input: free text goes to the Interpreter, which proposes a Command. The Bot shows it with Confirm and Cancel. Nothing is recorded until the Owner confirms. If the LLM is down, strict Commands still work. Consequences: the model sees only the Owner's message; a proposal the parser rejects is never recorded; a proposal expires after 10 minutes; an outage is reported with no retry loop.
- §3 Glossary: add Interpreter and Proposal.
- §9 Open Questions: add hosted provider choice and its data-use terms.

### P3. ARCHITECTURE-SPINE

- AD-7: parser stays deterministic and the sole authority. Replace "no AI model" with "no AI model inside the parser; free text goes through AD-16".
- New AD-16 "The Interpreter only proposes": `core` port `Interpreter`, adapter `adapters/llm/`. Fixed-schema JSON output, rendered to a strict Command and re-parsed by AD-7. Only the Owner's message text is sent. Confirmation required, confirm callback Owner-only (AD-6). Timeouts and rate limits degrade to the strict format. Provider switchable by config.
- AD-5: add event types `proposal_confirmed`, `proposal_discarded`.
- AD-3: add `proposals` to the mutable side tables.
- Ports list and layout tree: add `Interpreter` and `adapters/llm/`.
- Stack: add LLM provider client over httpx, provider to be chosen.
- Capability map and `binds`: add FR-13.
- Deferred: add swapping the hosted model for a local one (e.g. Ollama).

### P4. SPEC.md

- New CAP-11 "Talk naturally" (intent and success as in P2).
- Constraints: replace "uses no AI model" with "the parser is deterministic and never guesses. A free-text LLM may only propose, and the Owner confirms."
- Non-goals: remove "Free-text natural-language booking messages".
- Assumptions: add hosted provider chosen at build time, data exposure accepted for the MVP.

### P5. epics.md / sprint status

No change. `epics.md` already holds FR-13, NFR10, AR20 and Epic 7. No `sprint-status.yaml` exists yet.

## 5. Implementation Handoff

- **Scope:** moderate (documents across three artifacts).
- **Recipients:** applied in this session as PM (PRD, SPEC) and Architect (spine) edits, then Sprint Planning.
- **Success:** PRD, architecture, SPEC and epics all state FR-13 consistently, with no remaining "no AI" or "free text out of scope" statements.
