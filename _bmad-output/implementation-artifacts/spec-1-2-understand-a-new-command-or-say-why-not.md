---
title: '1.2 Understand a New command or say why not'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: 'fabd155f9672294266f80c671d701df873616095'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Bot only says "LeRegister is running". It cannot read a `New` message, so a wrong guess could later reach the records and the Owner gets no feedback on a bad message.

**Approach:** Add a pure parser in `core` over a fixed grammar with a built-in FR/EN month table. It returns a typed `ok` or `rejected(reason)`. The Telegram handler replies with the interpreted values for a valid `New` (not saved) and with the "Could not understand" message plus the failing part otherwise. Nothing is stored.

## Boundaries & Constraints

**Always:** Parser is a pure function: input text, `Clock`, chalet count, max stay. No I/O, no date-guessing library, no AI. "Today" is computed in `Asia/Beirut` from the `Clock`. Command word and months are case-insensitive, and accents are accepted (`déc`, `décembre`, `dec`, `december`, plus the other FR/EN months). Phone = first token starting with `+`, validated and normalized to E.164 with `phonenumbers` and no default region. Name = tokens between chalet and phone. Dates form: `D-D month` or `D month-D month`. Year-less: check-in is the next occurrence on or after today; check-out is the first end date after check-in. Nights run from check-in up to but excluding check-out. Ambiguity is rejected, never guessed. Reply text is English plain text. The Owner gate still runs first. Logs carry ids only.

**Never:** No database, journal, outbox or saving (Stories 1.3-1.4). No dedup. No other commands (`Cancel`, `Change`, `Rate`): they get the "Could not understand" reply. No explicit-year dates. No new dependencies. Do not log message text.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Basic | `New 2 Sam +96171123456 12-15 dec` | chalet 2, Sam, +96171123456, 12 to 15 Dec | N/A |
| Multi-word name, cross-year | `new 2 Mary Ann +96171123456 30 DEC-2 Jan` | name "Mary Ann", check-out 2 Jan of next year | N/A |
| Month spellings | `déc`, `décembre`, `dec`, `december` | all accepted | N/A |
| Year-less | today 2026-12-20, `12-15 dec` | check-in 2027-12-12 | N/A |
| Missing phone | `New 2 Sam 12-15 dec` | rejected: missing phone | reply names "phone" |
| Bad phone | no `+`, or invalid number | rejected: phone | reply names "phone" |
| Unknown month | `12-15 xyz` | rejected: unknown month | reply names "month" |
| Chalet range | 0, 41, or non-number | rejected: chalet | reply names "chalet" |
| Stay too long | over max nights | rejected: stay too long | reply names max |
| Out not after in | `15-12 dec`, `15-15 dec` | rejected: check-out not after check-in | reply names it |
| Not a New | `hello`, `Cancel 2` | rejected: not understood | generic reply |
| Valid New | any valid | reply with interpreted values, "not saved yet" | N/A |

</frozen-after-approval>

## Code Map

- `src/leregister/core/ports.py` -- existing `Clock` Protocol; reuse, do not change
- `src/leregister/core/access.py` -- existing Owner decision; untouched
- `src/leregister/core/parser.py` -- new. `parse_command`, `ParsedNew`, `Rejected`, month table
- `src/leregister/core/replies.py` -- new. Pure text for the "Could not understand" reply and the valid echo
- `src/leregister/adapters/telegram/bot.py` -- replace `ACK_TEXT` reply with parse then reply; read `clock`, `chalet_count`, `max_stay` from `bot_data`
- `src/leregister/app.py` -- wire a system `Clock` into the application
- `src/leregister/config.py` -- existing `chalet_count` and `max_stay`; reuse
- `tests/test_owner_gate.py` -- Owner reply no longer `ACK_TEXT`; update to the new reply
- `pyproject.toml` -- `phonenumbers` already pinned; the import-linter contract must stay green

## Tasks & Acceptance

**Execution:**
- [x] `src/leregister/core/parser.py` -- tokenizer, FR/EN month table, date forms, year inference via `Clock`, E.164 via `phonenumbers`, range and stay checks -- AR7, AR8, FR-1, FR-2
- [x] `src/leregister/core/replies.py` -- wording for rejection and valid echo -- single renderer rule
- [x] `src/leregister/adapters/telegram/bot.py` -- parse the Owner's text and reply; keep the gate first -- AC reply behavior
- [x] `src/leregister/app.py` -- add a system `Clock` and put it and the limits into `bot_data` -- wiring
- [x] `tests/test_parser.py` -- every matrix row with a fake `Clock`; assert no `datetime.now` use -- parser ACs
- [x] `tests/test_owner_gate.py` -- Owner gets the new replies; non-Owner still silent -- regression

**Acceptance Criteria:**
- Given the parser, when it gets the listed inputs, then it returns the values or `rejected(reason)` per the matrix.
- Given a rejection, when the Owner sent it, then the reply is "Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec" plus the failing part when known, and nothing is recorded.
- Given the test suite, when run, then `lint-imports` still keeps `core` pure.

## Implementation Notes

Implemented directly (no subagent). Added `adapters/clock.py` (`SystemClock`). `build_application(settings, clock)` now takes the clock, passed from `app.py` because adapters must not import each other. `Rejected` carries only a `reason` string that names the failing part. Dates parse via two regexes after accent folding. 76 tests pass; `lint-imports` kept.

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| Name token starting with `+` is taken as the phone | false | rejected | AR7 defines phone as the first token starting with `+` |
| `30-2 dec` rejected, only `30 dec-2 jan` crosses months | false | rejected | Matches the spec grammar; the reply names the failing part |
| Past date rolls a year ahead without a warning | false | rejected | AR7/AR8 define next occurrence on or after today; the echo shows ISO dates and nothing is saved yet |
| Non-New text gets "Could not understand" | false | rejected | AC: any unparseable message gets that reply |
| Settings, Clock, tzdata, pyproject "unverified" | false | rejected | All exist from Story 1.1 |
| Missing `bot_data` key raises KeyError | low | rejected | Wired in one place and now asserted by a test |
| Control characters or Markdown echoed | false | rejected | Replies are plain text with no parse_mode |
| Weak "never reads system time" test | medium | patch | Test now patches `parser.date` with a class whose `today()` raises |
| Wiring of clock/chalet_count/max_stay untested | medium | patch | Wiring test now asserts all three values |
| SystemClock untested | low | patch | Added tests/test_clock.py |
| 29 Feb and same-day two-month cases untested | low | patch | Tests added |
| `12 dec-12 dec` rejected as "over the maximum" | low | patch | Now rejected with "check-out must be after check-in" |
| Non-ASCII digits accepted in dates | low | patch | Date regexes use [0-9] |
| Phone extension or stray text silently dropped | medium | patch | Phone must match `+` then digits and `().-` before normalizing |
| Dead `rstrip(".")`, blank line in bot.py, weakened owner test | low | patch | Fixed |
| Reply can exceed 4096 chars | low | defer | Logged in deferred-work.md |
| Edited and non-text updates | medium | defer | Story 1.3 owns edited messages; logged in deferred-work.md |

## Design Notes

Result types: `ParsedNew(chalet, name, phone, check_in, check_out)` and `Rejected(reason)`. A single-month range `12-15 dec` is parsed first; a two-month range `30 dec-2 jan` second; anything else is `Rejected`. Valid echo example: `Understood (not saved yet): Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)`.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass
- `uv run lint-imports` -- expected: contract kept

**Manual checks (if no CLI):**
- With a throwaway bot token, send `New 2 Sam +96171123456 12-15 dec` and `New 2 Sam 12-15 dec` from the Owner account: the first echoes the values, the second is rejected naming the phone.
