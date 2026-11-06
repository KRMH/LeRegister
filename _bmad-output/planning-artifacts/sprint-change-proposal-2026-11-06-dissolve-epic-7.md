---
title: "Sprint Change Proposal: spread free text across the epics"
date: 2026-11-06
status: approved and applied
scope: moderate
mode: batch
supersedes_structure_of: sprint-change-proposal-2026-11-06.md (Epic 7 placement only; its decisions on the LLM stay)
---

# Sprint Change Proposal: dissolve Epic 7, add free text to each epic

## 1. Issue Summary

Epic 7 ("Talk naturally") holds all of the free-text input work as one block at the very end. The Owner wants that capability delivered with the command it belongs to, so each epic gives the Owner both the strict command and the plain-words way to use it. **Category:** change in how scope is organised. Requirements and decisions do not change (FR-13, AR20, the confirm-before-record rule, the hosted free tier).

## 2. Impact Analysis

- **Epics:** Epic 7 is removed. Epics 1, 2 and 3 gain stories. Epics 4, 5 and 6 are unchanged because they have no typed commands.
- **Stories built:** none affected. Stories 1.1 to 1.5 stay as they are and stay valid. **Epic 1 is no longer complete** (three more stories), so its retrospective waits until 1.8.
- **Artifacts:** only `epics.md` (Epic List, FR coverage map, the Epic 7 section, new stories) and `sprint-status.yaml` (keys). PRD, architecture and SPEC mention FR-13 and AR20 but not Epic 7, so they need no change.
- **Technical:** unchanged from the earlier proposal: an `Interpreter` port, `adapters/llm/`, a `proposals` side table (new migration), journal events `proposal_confirmed` and `proposal_discarded` (already in the closed list). The new part is the order: the first free-text support is built in Epic 1, supporting only `New`, and the schema grows as Epics 2 and 3 add `Cancel`, `Change` and `Rating`.
- **Risk:** the hosted model receives the Owner's message text (guest names, phones) earlier in the project. This was accepted for the MVP in the earlier proposal.

## 3. Recommended Approach

Direct adjustment: move and split stories, no rollback. Effort low (documents only), risk low, timeline: free text for `New` arrives about six epics earlier, and Epic 1 takes three more stories before it closes.

Why Epic 1 holds the shared foundation: the confirm flow, the proposals table and the model fallback are needed by every free-text command, and `New` is the only command that exists today.

## 4. Detailed Change Proposals

### P1. `epics.md` structure

| Where | OLD | NEW |
|---|---|---|
| Epic List, Epic 1 goal | "...Includes project scaffold, database with no-delete protection, parser, Journal, Telegram reply path, and reporting of failed Commands." | Same, plus "and writing the booking in plain words, confirmed before it is recorded." FRs: FR-1, FR-2, FR-3, FR-13 (New) |
| Epic List, Epic 2 goal | "Clashes are flagged at once; the Owner can cancel or move a booking without losing the old version." | Same, plus "Cancel and Change also work in plain words." FRs: FR-4 to FR-7, FR-13 (Cancel, Change) |
| Epic List, Epic 3 goal | "The Owner can rate a Client and sees the Rating when that Client books again." | Same, plus "Rating also works in plain words." FRs: FR-9, FR-10, FR-13 (Rating) |
| Epic List, Epic 7 | "Talk naturally ..." | Removed |
| FR Coverage Map | `FR-13: Epic 7 - Natural-language input with confirmation` | `FR-13: Epics 1, 2, 3 - Natural-language input with confirmation (New in Epic 1; Cancel and Change in Epic 2; Rating in Epic 3)` |
| `## Epic 7: Talk naturally` and Stories 7.1 to 7.4 | present | Removed; content moves as below |

### P2. New stories (acceptance criteria are carried over, narrowed to the command each story owns)

**Story 1.6: Turn free text into a proposed `New` command** (from 7.1)
- The `Interpreter` port in `core` and the `adapters/llm/` adapter (hosted free tier, key in config, AR20). When a message does not match a strict format, the Bot sends the text to the Interpreter instead of replying "Could not understand".
- Output is a fixed-schema JSON object (command type `new` and its fields), validated by `core`; anything else is "no proposal".
- A valid proposal is rendered as a strict Command string and goes through the deterministic parser, which stays the only authority (AR7). A proposal the parser rejects is a rejection with its reason.
- Only the Owner's message and the schema are sent, never bookings, Clients or earlier messages (NFR10). Instructions inside the message get no tools and cannot act (NFR2).
- A strict, valid Command never calls the model. A message that maps to no single command, or is ambiguous, gets a "rephrase or use the strict format" reply and is never guessed.
- With no Interpreter configured, behaviour is exactly today's.

**Story 1.7: Confirm before anything is recorded** (from 7.2), unchanged in substance
- Plain-words proposal with Confirm and Cancel buttons; nothing recorded yet. Confirm (Owner, private chat only) runs the same core use case, transaction, journal rows and replies as a typed Command. Cancel discards it. Other accounts' callbacks are ignored. Expiry after 10 minutes (configurable). A second Confirm records nothing. Proposals live in a `proposals` side table; every outcome is journaled (`proposal_confirmed`, `proposal_discarded`).

**Story 1.8: Keep working when the model does not** (from 7.4), unchanged in substance
- On timeout, error or rate limit: reply that free text is unavailable and show the strict format, record nothing. Strict commands keep working. Short timeout, no transaction or writer held during the call, no retry loop. Switching provider changes only `adapters/llm/` and config. No names or phones in logs; outcomes journaled with ids only.

**Story 2.5: Cancel in free text** (from 7.3)
- `cancel sam's booking in chalet 2 starting the 12th` becomes the proposal `Cancel 2 12 dec`, shown with Confirm and Cancel. Every rule of Story 2.2 applies unchanged. Ambiguous or unmappable messages are never guessed.

**Story 2.6: Change in free text** (from 7.3)
- `move chalet 2 from 12 dec to 14-17 dec` becomes `Change 2 12 dec 14-17 dec`, confirmed before it runs. Every rule of Story 2.3 (matching, Overlap check, old version kept) applies unchanged.

**Story 3.3: Rate in free text** (from 7.3)
- `sam +96171123456 was rude` becomes `Rating +96171123456 -`, confirmed before it runs. Rating bounds and journaling from Story 3.1 apply unchanged.

**Order inside each epic:** 1.6, 1.7, 1.8 after 1.5; 2.5 after 2.2 and 2.6 after 2.3; 3.3 after 3.1. Stories 2.5, 2.6 and 3.3 depend on 1.7.

### P3. `sprint-status.yaml`

- Remove `epic-7`, its four story keys and `epic-7-retrospective`.
- Add under Epic 1: `1-6-turn-free-text-into-a-proposed-new-command`, `1-7-confirm-before-anything-is-recorded`, `1-8-keep-working-when-the-model-does-not` (all `backlog`). `epic-1` stays `in-progress`.
- Add `2-5-cancel-in-free-text`, `2-6-change-in-free-text` under Epic 2 and `3-3-rate-in-free-text` under Epic 3 (`backlog`).
- Stories: 25 in total (was 23). Done: 5 (1.1 to 1.5).

### P4. Side effects

- `epic-1-context.md` becomes stale once `epics.md` changes. It regenerates automatically on the next build.
- The roadmap page is republished to show six epics and 25 stories.

## 5. Implementation Handoff

**Scope: moderate** (backlog reorganisation, documents only). Route: Developer agent applies P1 to P3 after approval; no PM or architect rework.

**Success criteria:** `epics.md` has six epics and 25 stories with no Epic 7 and an updated FR-13 mapping; `sprint-status.yaml` matches; the next story to build is 2.1 or 1.6, as the Owner chooses.

**Build order (decided by the Owner): A.** Finish Epic 1 first (1.6, 1.7, 1.8), hold the Epic 1 retrospective, then start Epic 2 with Story 2.1. The next story to build is 1.6.
