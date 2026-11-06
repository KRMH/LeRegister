---
title: '1.9 Ask for what is missing'
type: 'feature'
created: '2026-11-07'
status: 'done'
baseline_commit: 'a29f8be73f9bff22f8b13f8f464bffb47a78d924'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A plain-words booking must be complete in one message. If anything is missing or relative ("next friday"), the Bot throws away what it understood and the Owner must retype everything; the Bot forgets the first message.

**Approach:** When the model understands only part of a booking, the Bot keeps a short-lived draft in a side table and asks one question naming the first missing part. The Owner's next message fills only the missing parts. When the draft is complete it becomes a proposal exactly as in Story 1.6: the strict parser judges it and the Owner is shown the strict command to send.

## Boundaries & Constraints

**Always:** Fields of a booking: chalet, name, phone, check-in day and month, check-out day and month. The phone is found and kept locally (`redact_phones`) and is never sent to the model. The model's answer is a JSON object with exactly the keys `command` (`"new"` or `"none"`), `chalet`, `name`, `check_in_day`, `check_in_month`, `check_out_day`, `check_out_month`; every field except `command` is a valid value or `null`. Anything else, or `command: "none"`, is no information. Relative or unclear dates are `null` and are never guessed. The prompt says so. Questions are rendered by `core`, in this order of priority: chalet, name, dates, phone; one question per reply, naming what is already known ("Which dates for Lea in chalet 4?"). A draft is one row per Owner chat in a new `drafts` table (migration 003), holds the fields, the number of questions asked and its last-change time, and is written in the same transaction as the Command that changed it. Expiry is 10 minutes from the last change, set by `LEREGISTER_DRAFT_MINUTES` (default 10, 1 to 1440); an expired draft is ignored and deleted when it is found. A follow-up message (no `New` first word, a draft waits) sends the model the redacted message plus the draft's known name, chalet and dates as JSON, labelled "already known"; the prompt tells the model to return `null` for anything the message does not mention. Merge rules, in this order: (1) if the message states a guest name different from the draft's (compared ignoring case and accents), or is a complete booking by itself, it is a new booking and replaces the draft; (2) otherwise every value the message states overrides the draft's value (a correction such as "actually chalet 5" or a fixed phone) and everything it does not mention is kept. A message that is only a phone number needs no model call. A message that is exactly `stop`, `forget it` or `never mind` (any case, surrounding spaces and punctuation ignored) deletes the draft with no model call and gets the reply "Okay, I dropped that draft."; with no draft waiting it is treated like any other free text. When every field is present: render the strict command, run `parse_command`; a rejection is journaled as `command_rejected` with its reason, a valid result is the Story 1.6 proposal reply, and either way the draft is deleted. After 3 questions, if the booking is still incomplete, the draft is deleted and the Bot refuses with the strict format. Any strict attempt (first word `New`) deletes the draft. A refusal for a reserved word, several phones or a stray digit run leaves the draft unchanged. If the model is unavailable the Bot replies as in Story 1.6 and the draft is kept unchanged. The Owner gate still runs first; nothing is journaled for questions or drafts.

**Never:** No confirm buttons, no `proposals` table (Story 1.7). Drafts never touch `bookings`, `clients` or `journal`. The phone number never reaches the model. No earlier messages are sent, only the draft's name, chalet and dates. No `Cancel`, `Change` or `Rating` drafts. No date guessing. No more than one draft per chat.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dates missing | `chalet 4 for Lea next friday for 3 nights +96171555123` | Draft: chalet 4, Lea, phone; reply "Which dates for Lea in chalet 4? ..." | N/A |
| Answer fills the gap | then `from the 20th to the 23rd of december` | Draft complete; reply shows `New 4 Lea +96171555123 20-23 dec`; draft deleted | N/A |
| Phone missing | `chalet 2 for Sam from the 12th to the 15th of december` | Draft without phone; reply asks for the phone with `+` | N/A |
| Phone given alone | `+96171123456` | No model call; phone filled; complete draft becomes a proposal | N/A |
| Chalet missing | `Lea +96171555123 20 to 23 dec` | Asks which chalet | N/A |
| Complete in one go | full sentence | Proposal at once, no draft left | N/A |
| New guest replaces draft | draft waits for Lea; message names Zoë | Draft replaced by the new one; its question is asked | N/A |
| Complete booking replaces draft | draft waits for Lea; a full sentence for another chalet, same or no name | Draft replaced; proposal shown | N/A |
| Correction | draft Lea, chalet 4, no dates; `20th to 23rd, actually chalet 5` | Chalet becomes 5, dates filled, Lea and phone kept; proposal for chalet 5 | N/A |
| Stop words | draft waits; `forget it` | Draft deleted; "Okay, I dropped that draft."; no model call | N/A |
| Stop word, no draft | `stop` with no draft | Treated as ordinary free text | N/A |
| Strict command | draft waits; `New 2 Sam +96171123456 12-15 dec` | Draft deleted; command runs as usual | N/A |
| Expired draft | answer arrives after 10 minutes | Treated as a new message; the old draft is ignored | N/A |
| Too many questions | still incomplete after 3 questions | Draft deleted; refusal with the strict format | `command_rejected` journaled |
| Nothing understood | `hmm` while a draft waits | Same question again; counts as a question | N/A |
| Parser rejects | complete draft with chalet 99 | Rejected with the parser's reason; draft deleted | `command_rejected` journaled |
| Model down | follow-up while a draft waits | "Free text is unavailable" reply; draft unchanged | `command_rejected` journaled |
| Two phones or stray digits | follow-up with two `+` numbers | Refused without a model call; draft unchanged | `command_rejected` journaled |

</frozen-after-approval>

## Code Map

- `src/leregister/core/events.py` -- add `Draft` (fields above plus `questions_asked`); `Decision.draft` and `Decision.clear_draft`
- `src/leregister/core/interpret.py` -- replace `Proposal`/`parse_proposal` with a partial-fields parser; new prompt; `build_user_message`; merge and conflict rules; `missing_part`; `is_strict_attempt`; `render_strict_command` takes a complete draft
- `src/leregister/core/commands.py` -- `decide_free_text` takes the current draft and returns question, proposal or rejection with the draft change; `decide` clears the draft on a strict attempt
- `src/leregister/core/replies.py` -- kinds `free_text_question` and `draft_dropped` and their wording
- `src/leregister/core/ports.py` -- `Store.get_draft(chat_id, now, ttl)`
- `src/leregister/adapters/store/migrations/003_drafts.sql`, `store.py` -- table, `get_draft`, draft upsert and delete inside `record_command`
- `src/leregister/adapters/telegram/bot.py` -- read the draft before a free-text decision; pass the TTL
- `src/leregister/config.py`, `README.md` -- `LEREGISTER_DRAFT_MINUTES`
- `tests/` -- update `test_interpret.py` to the nullable schema; new `test_drafts.py`; extend `test_store.py`, `test_config.py`

## Tasks & Acceptance

**Execution:**
- [x] `src/leregister/core/{events,interpret,commands,replies,ports}.py` -- nullable schema, merge rules, questions, draft decisions -- FR-13, NFR10
- [x] `src/leregister/adapters/store/` -- migration 003, draft read and atomic write -- AR3, AR4
- [x] `src/leregister/adapters/telegram/bot.py`, `config.py`, `README.md` -- wiring and setting -- AR16
- [x] `tests/` -- every matrix row with a fake Interpreter, draft expiry with a movable clock, store tests for the table, the phone never in any model input, import contracts green -- AC

**Acceptance Criteria:**
- Given the first sentence with missing dates, when it is sent, then one question names the missing part and the answer completes the booking without retyping.
- Given any call to the model, when it is made, then neither the user message nor the prompt contains any digit of a phone number.
- Given the test suite, when run, then `lint-imports` keeps all contracts.

## Implementation Notes

Implemented directly (no subagent). `core/interpret.py` now parses a nullable `Partial`, builds the follow-up message (known name, chalet and dates, never the phone), merges (stated values override, a different guest name or a complete message restarts), and renders the strict command from a complete `Draft`. `decide_free_text` returns a question, a proposal or a refusal together with the draft change (`Decision.draft` or `clear_draft`); `decide` clears the draft for any message starting with `New`. The phone is no longer part of the model schema: it is found locally and stored in the draft. `drafts` (migration 003) is written inside `record_command`; `get_draft` deletes an expired row when it finds it. A message the model cannot read does not start a draft even if it contains a phone number; a message that is only a phone number does. Default question order: chalet, name, dates, phone. Checked against the real Groq model (`openai/gpt-oss-20b`) with eight scripted chats: fill-in, correction, new guest, stop word, nothing understood. 354 tests pass; all import contracts kept.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| Expired drafts keep a guest's name and phone in the database until the Owner writes again | medium | patch | A purge job runs every minute and deletes drafts older than the limit; tests added |
| A fuller name ("Lea Khoury" after "Lea") counted as a new guest and wiped the draft | medium | patch | Guests are compared by first word, ignoring case and accents; tests added |
| With half-known dates the Bot repeated the generic dates question | low | patch | New questions "Until which day…?" and "From which day…?"; tests added |
| `assert` in `render_strict_command` disappears under `python -O` | low | patch | Raises `ValueError` for an incomplete draft; test added |
| Stop words missed `nevermind`, `never-mind` and a trailing ellipsis | low | patch | Normalised; tests added |
| `drafts` accepted impossible values; `Draft` was built from a positional row | low | patch | CHECK constraints in the migration; keyword construction; tests added |
| Expiry boundary and fixed-width timestamps untested; `00961` and "New booking" cases dropped from tests | low | patch | Tests added back |
| README did not mention the question limit, the strict command clearing the draft, or what the model sees | low | patch | README updated |
| Fourth question needed when four parts are missing: draft deleted although every answer helped | medium | rejected | The Owner chose to keep "3 questions in total" as approved; tests pin the behaviour |
| New guest resets the question count | low | rejected | A new guest is a new draft; each round needs Owner messages |
| Unreadable model answer on a follow-up uses up a question | low | rejected | Minor; the same question is asked again |
| Unsafe follow-up (several phones, stray digits) keeps the draft with the generic refusal | low | rejected | Draft is unchanged, which is the specified behaviour |
| Parser rejection on a complete draft deletes it instead of asking for the bad value | low | rejected | Rare; the reason is given and the Owner retypes |
| Phone alone with no draft starts a draft | low | rejected | Specified: a bare phone is a valid first step |
| Two messages in flight at once | low | rejected | The Bot handles updates one at a time |
| Draft read happens before refusal checks; expiry delete outside the Command's transaction | low | rejected | Harmless; no data is lost |
| `bot_data["draft_ttl"]` read with `[]` | low | rejected | Always set by `build_application` |

## Design Notes

Why a different guest name or a complete message restarts, but other restatements override: a name identifies the guest, so a new name means a new booking and must not inherit the old draft's chalet or dates. Chalet, dates and a fixed phone are things people correct mid-conversation ("actually chalet 5"), so they override and the rest of the draft is kept. The Owner still sees the strict command before anything is recorded.

Why the model sees name, chalet and dates but not the phone: the model needs them to read an answer like "the 23rd" in context; the phone adds nothing for it and is the most sensitive field. This relaxes the earlier rule that the model sees only the current message; the relaxation is limited to fields taken from the Owner's own earlier message and is written into the epic context.

## Verification

**Commands:**
- `uv run --no-sync pytest` -- expected: all tests pass
- `uv run --no-sync lint-imports` -- expected: all contracts kept

**Manual checks (if no CLI):**
- Send `chalet 4 for Lea next friday for 3 nights +96171555123`: the Bot asks for the dates. Reply `from the 20th to the 23rd of december`: the Bot shows `New 4 Lea +96171555123 20-23 dec`.
