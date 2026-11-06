---
title: '1.4 Record a Phone Booking'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: '3ebe1c3be3f8ff01df4022f4757bbba480282f03'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A valid `New` is only echoed back as "not saved yet". Nothing is recorded, so the Owner cannot rely on the Bot as a register, and a repeated message has no protection against duplicates.

**Approach:** Add migration 002 with `clients` and `bookings`, and triggers that make `bookings` undeletable and almost immutable. A valid `New` becomes one transaction that creates the Client (if new), the `active` Phone Booking, a `booking_recorded` journal row and the reply outbox row. An identical `active` booking sent again creates nothing and is answered "already recorded".

## Boundaries & Constraints

**Always:** One transaction writes `processed_updates`, the Client (if new), the booking, the journal row and the outbox row. The Client is keyed by its E.164 phone; its name is set at the first booking and kept; the booking keeps the name as given. `clients` has a `rating` column (integer 1-5, default 5, nothing reads it yet). A booking has `chalet`, `client_name`, `client_phone`, `check_in`, `check_out` (ISO dates), `status` (`active|changed|cancelled`), `superseded_by` (nullable) and `created_at` (UTC). "Identical" means an `active` booking with the same chalet, phone, check-in and check-out; the name is ignored. A partial unique index enforces this in storage. Triggers: `DELETE` on `bookings` aborts; an `UPDATE` that changes anything except `status` or `superseded_by` aborts; a `status` change other than `active→changed` or `active→cancelled` aborts. Outbox rows reference the booking by id (new `booking_id` column); text is rendered at send time. Journal `booking_recorded` has `subject_type` `booking`, `subject_id` the booking id, `related_booking_id` the booking id, and payload `{chalet, phone, check_in, check_out}`. Logs carry ids only. No `INSERT OR REPLACE`.

**Never:** No overlap check or alert (Epic 2). No Cancel, Change or Rate. No rating logic or rating in the reply (Epic 3). No Trello or Register output. No journal row for "already recorded" or for rejections other than the existing `command_rejected`. No booking field edits, ever.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid new booking | `New 2 Sam +96171123456 12-15 dec`, no such booking | Client and `active` booking created, `booking_recorded` journal row, reply "Recorded: Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)" | N/A |
| Same booking again | identical `active` booking exists | Nothing created, no journal row, reply "Already recorded: …" with the stored values | N/A |
| Same phone, other name | Client exists as "Sam", send `New 3 Samuel +96171123456 …` | New booking keeps "Samuel"; Client name stays "Sam" | N/A |
| Same dates, other chalet or phone | differs in chalet or phone | New booking created | N/A |
| Invalid values | any rejection from Story 1.2 | `command_rejected` journal row and reason reply; nothing recorded | N/A |
| Delete a booking | `DELETE FROM bookings` | Trigger aborts | Error raised |
| Edit a fixed field | `UPDATE bookings SET chalet/name/phone/dates/created_at` | Trigger aborts | Error raised |
| Bad status move | `cancelled→active`, `changed→cancelled`, `active→unknown` | Trigger or CHECK aborts | Error raised |
| Allowed status move | `active→changed` or `active→cancelled`, set `superseded_by` | Succeeds | N/A |
| Failure mid-command | error after the booking insert | Nothing from the Command remains | Rolled back |

</frozen-after-approval>

## Code Map

- `src/leregister/adapters/store/migrations/002_bookings.sql` -- new. `clients`, `bookings`, triggers, partial unique index, `outbox.booking_id`
- `src/leregister/adapters/store/store.py` -- `record_command` handles a booking: duplicate lookup, Client and booking insert, journal ids; `fetch_due` joins the booking
- `src/leregister/core/events.py` -- add `NewBooking`; `Decision.booking`; `OutboxItem.booking`
- `src/leregister/core/commands.py` -- valid `New` now returns a `booking_recorded` journal template plus `NewBooking`
- `src/leregister/core/replies.py` -- `render` takes the booking; kinds `recorded` and `already_recorded` replace `new_preview`
- `src/leregister/adapters/telegram/drainer.py` -- pass the booking to `render`
- `src/leregister/core/ports.py` -- unchanged signatures; reuse
- `tests/` -- new `test_bookings.py`; update `test_commands.py`, `test_owner_gate.py`, `test_store.py`

## Tasks & Acceptance

**Execution:**
- [x] `src/leregister/adapters/store/migrations/002_bookings.sql` -- tables, triggers, unique index, `booking_id` -- AR3, AR13
- [x] `src/leregister/core/{events,commands,replies}.py` -- booking value, decision, rendering -- FR-1
- [x] `src/leregister/adapters/store/store.py`, `adapters/telegram/drainer.py` -- one-transaction recording, duplicate handling, booking in outbox items -- AR4
- [x] `tests/` -- every matrix row, each trigger case fired, rollback, first-name rule, import contracts still green -- AR3

**Acceptance Criteria:**
- Given a valid `New`, when processed, then exactly one Client (if new), one `active` booking, one `booking_recorded` row and one outbox row exist, and the Owner receives the echo.
- Given the identical command again, when processed, then the table counts are unchanged and the reply starts with "Already recorded".
- Given the test suite, when run, then every trigger case aborts as listed and `lint-imports` is green.

## Implementation Notes

Implemented directly (no subagent). Migration 002 adds `clients`, `bookings`, three triggers (no delete, fixed fields, status moves), a partial unique index for identical active bookings, and `outbox.booking_id`. `Decision` gained `booking`, `OutboxItem` gained `booking`; the store decides recorded versus already recorded and fills in the booking id on the journal template. `new_preview` and `understood_reply` are gone, replaced by `recorded` and `already_recorded`. 140 tests pass; both contracts kept.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| Pending `new_preview` rows from 1.3 would fail to render forever after the upgrade | medium | patch | Migration 002 now closes them; upgrade test added |
| Upgrade from schema 1 with old outbox rows untested | medium | patch | Test builds a v1 DB, adds rows, migrates, checks rows and `fetch_due` |
| `superseded_by` could point at the booking itself | low | patch | CHECK added; test added |
| Dates not format-checked in storage (string compare needs zero-padded ISO) | medium | patch | GLOB CHECKs on `check_in` and `check_out`; test added |
| Missing tests: replayed update id, DELETE on a cancelled row, active to active, 1-night wording, reply without booking, foreign keys on the real connection | low | patch | Tests added |
| Stale `ReplyRequest.kind` comment | low | patch | Fixed |
| Overlapping stays are recorded silently | low | rejected | Overlap handling is Epic 2 by spec |
| `superseded_by` rewritable after being set; must pair with `changed` | low | rejected | Change flow (Story 2.3) defines the rule; stricter triggers now could block it |
| Duplicate path drops the typed name and journals nothing | low | rejected | AC: reply "already recorded"; no event type exists for it |
| Decision reply kind overridden by the store; placeholder `subject_id` | low | rejected | Documented in Design Notes; covered by integration tests |
| Phone in the journal payload | low | rejected | Payload schema needs it for audit; names stay out |
| Reply built from live data, no booking id in reply | low | rejected | AR10 renders at send time by design; Cancel and Change address bookings by chalet and dates |
| Missing indexes, `clients` unprotected, chalet not checked in storage | low | rejected | No harm shown now; `clients.rating` must stay mutable (AR13) |
| Insert race / `ON CONFLICT` for clients | low | rejected | Single serialized writer inside `BEGIN IMMEDIATE` |
| Poison rows when a booking is missing | low | rejected | Same item already in deferred-work.md from Story 1.3 |

## Design Notes

The store, not `core`, decides "recorded" versus "already recorded", because the answer depends on stored state read inside the transaction. `core` supplies a journal template and a `NewBooking`; the store fills in the booking id. `new_preview` is removed.

## Verification

**Commands:**
- `uv run --no-sync pytest` -- expected: all tests pass
- `uv run --no-sync lint-imports` -- expected: both contracts kept

**Manual checks (if no CLI):**
- Send `New 2 Sam +96171123456 12-15 dec` twice: first "Recorded", second "Already recorded". In the DB, one row in `bookings`, one `booking_recorded` journal row. `DELETE FROM bookings` aborts.
