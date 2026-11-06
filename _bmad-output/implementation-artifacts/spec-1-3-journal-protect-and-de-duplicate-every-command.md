---
title: '1.3 Journal, protect and de-duplicate every Command'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: '38ef9dcc8def858a6247770cd2f19becbee3e3d6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Bot replies straight from the handler and keeps no record. A rejected Command leaves no trace, a redelivered Telegram update would be answered twice, and nothing stops history from being rewritten.

**Approach:** Add a SQLite store (WAL, numbered migrations) with `journal`, `outbox`, `processed_updates` and `schema_version`, and triggers that abort any `UPDATE` or `DELETE` on `journal`. Each Owner update becomes one serialized transaction that writes its `processed_updates` row, a `command_rejected` journal row when rejected, and a reply outbox row. A Telegram drainer sends outbox rows in id order, and `core` renders their text. Duplicate and edited updates are handled.

## Boundaries & Constraints

**Always:** The Owner gate runs first; a non-Owner update reaches no store code and is not journaled. All DB access goes through one serialized writer (a single-thread executor over one connection). No network call inside a transaction. `INSERT OR REPLACE` is never used. Outbox rows hold ids and small arguments, never rendered text. `core` renders plain text, English, split at 4096 characters. Journal row: `id`, `at` (UTC ISO-8601 from the `Clock`), `event_type` from a closed list defined in `core` (the AR5 list), `subject_type`, `subject_id`, `related_booking_id` (nullable), JSON `payload`. A rejected Command is journaled as `command_rejected` with `subject_type` `command`, `subject_id` the `update_id`, and payload `{"reason": ...}` (no message text). The DB path comes from `LEREGISTER_DB_PATH`, default `~/.leregister/leregister.db`, outside the repo. Migrations are numbered `.sql` files applied at startup and tracked in `schema_version`.

**Never:** No `bookings`, `clients`, `proposals` or `register_cards` tables (Stories 1.4+). No booking is saved. No deleting or rewriting rows. The drainer for `register` is out of scope. No unexpected-error reply path (Story 1.5). No webhook or inbound port.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Rejected Command | Owner sends `hello` | One transaction: `processed_updates`, `command_rejected` journal row with reason, reply outbox row; drainer sends the "Could not understand" text | N/A |
| Valid `New` | Owner sends a valid `New` | `processed_updates` and a reply outbox row only; reply is the 1.2 "not saved yet" echo; no journal row | N/A |
| Redelivered update | Same `update_id` again | Ignored: no second journal or outbox row, no reply | N/A |
| Edited message | Owner edits a sent message | Nothing changed; one reply "Edits are not applied, please send a Change command instead" | N/A |
| Non-Owner / group | Other account or group chat | Silent: no store access, no journal, no reply | Log ids only |
| Send fails | Telegram error on a row | Row stays pending, `attempts` rises, next try after backoff; later rows still sent | Log id only |
| Long text | Reply over 4096 chars | Sent as several messages, each at most 4096 characters | N/A |
| Journal tamper | `UPDATE` or `DELETE` on `journal` | Trigger aborts | Error raised |
| Startup | Empty or old DB | Migrations applied once, `schema_version` updated | Stop with clear message if the DB cannot open |

</frozen-after-approval>

## Code Map

- `src/leregister/core/events.py` -- new. Closed `EventType` list, `JournalEntry`
- `src/leregister/core/commands.py` -- new. Pure `decide(text, clock, chalet_count, max_stay)` returning journal entry (or none) and reply request; wraps `parse_command`
- `src/leregister/core/replies.py` -- extend. `render(kind, args)` and `split_message(text, 4096)`; reuse `reject_reply` and `understood_reply`
- `src/leregister/core/outbox.py` -- new. `backoff_seconds(attempts)`
- `src/leregister/core/ports.py` -- add `Store` and `OutboxQueue` Protocols; keep `Clock`
- `src/leregister/adapters/store/` -- new. `db.py` (connection, WAL, migrations, serialized writer), `migrations/001_init.sql` (tables, journal triggers), `store.py` (`record_command`, outbox fetch/mark)
- `src/leregister/adapters/telegram/bot.py` -- handler: gate, edited-message branch, `decide`, `store.record_command`, then drain; periodic retry job
- `src/leregister/adapters/telegram/drainer.py` -- new. Sends due rows in id order via `bot.send_message`; adapters must not import each other, so it takes the `OutboxQueue` port
- `src/leregister/config.py` -- add `db_path`
- `src/leregister/app.py` -- open store, wire it, drainer and clock
- `tests/` -- new `test_store.py`, `test_drainer.py`, `test_commands.py`; rework `test_owner_gate.py` for outbox-based replies

## Tasks & Acceptance

**Execution:**
- [x] `src/leregister/adapters/store/` -- WAL connection, migration runner, `001_init.sql` with the four tables and journal triggers, serialized writer, `record_command` transaction -- AR2, AR3, AR4, AR5
- [x] `src/leregister/core/{events,commands,outbox}.py`, `replies.py`, `ports.py` -- event list, pure decision, backoff, renderer and splitter, ports -- AR5, AR10
- [x] `src/leregister/adapters/telegram/{bot,drainer}.py` -- edited branch, store call, drainer with backoff and retry job -- AR4, AR10
- [x] `src/leregister/config.py`, `src/leregister/app.py` -- `db_path` setting and wiring; README settings row -- AR16
- [x] `tests/` -- each journal trigger fired, rollback on duplicate, I/O matrix rows, backoff and id order, 4096 split, import contract still green -- AR3

**Acceptance Criteria:**
- Given a fresh DB, when the Bot starts, then only `journal`, `outbox`, `processed_updates` and `schema_version` exist and the DB is in WAL mode.
- Given a rejected Command, when processed, then one transaction holds the three rows and a duplicate `update_id` adds none.
- Given the test suite, when run, then `lint-imports` keeps `core` pure and no adapter imports another adapter.

## Implementation Notes

Implemented directly (no subagent). `build_application(settings, clock, store, queue)` now takes the store and outbox queue, passed from `app.py` because adapters must not import each other; a second import-linter contract ("adapters do not import each other") enforces it. `SqliteStore` implements both the `Store` and `OutboxQueue` ports. The outbox keeps `kind`, `args` JSON and `journal_id`; a rejected reply is rendered from the journal reason at send time. Tests add `tests/helpers.py` (movable clock, fake sender, real store on a temp DB). 104 tests pass; both contracts kept.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| Split of text ending in newline yields an empty chunk (Telegram rejects it, row retries forever) | medium | patch | Reproduced by reading `split_message`; empty chunk now skipped, test added |
| `mark_done`/`mark_failed` raising aborts the drain pass | medium | patch | Status writes now guarded per row; test added |
| `~` in `LEREGISTER_DB_PATH` creates a literal `~` directory | medium | patch | `expanduser()` applied; config test added |
| Migrations sorted lexicographically (10 before 2); duplicate numbers; missing trailing semicolon; connection leaked on failed open | low | patch | Numeric ordering, duplicate refusal, forced `;`, close on failure; tests added |
| Drainer lock, real send wiring, retry job, migration failure untested | medium | patch | Tests added for each |
| Event list test used subset instead of equality | low | patch | Now equality |
| Design note said 1-second retry job | low | patch | Corrected to 5 seconds |
| Chunk resend after partial failure / `mark_done` failure | low | rejected | At-least-once delivery is the accepted AR10 semantic |
| Poison rows retried forever, no dead-letter state | medium | defer | AC says a row stays pending until it succeeds; a cap needs an Owner decision. Logged in deferred-work.md |
| `record_command` failure leaves the Owner without a reply | medium | defer | Story 1.5 owns unexpected-error replies |
| `new_preview` args hold name and phone in the outbox | low | rejected | Temporary; Story 1.4 replaces it with a booking id |
| Edits not journaled; non-text updates journaled as rejected | low | rejected | AR5 has no edit event; AC says only that nothing changes |
| Rejection reasons can embed a month token | low | rejected | A month word is not personal data |
| Two clock reads per command; naive datetimes | low | rejected | Clock port contract is timezone-aware; no demonstrated harm |
| Job queue missing silently skips retries | low | rejected | `python-telegram-bot[job-queue]` is a pinned dependency |
| Newer-schema guard, WAL check, DB file permissions, retention, unused columns | low | rejected | No harm shown in the current story; columns are specified by AR10 |

## Design Notes

A valid `New` is not journaled in this story: AR5 has no event for a preview, and Story 1.4 adds `booking_recorded`. The `new_preview` outbox row carries the parsed values as small JSON arguments; Story 1.4 replaces it with a booking id. Drain right after commit for the 5-second reply target, and again on a 5-second repeating job for retries.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass
- `uv run lint-imports` -- expected: contract kept

**Manual checks (if no CLI):**
- Send `hello`, then restart the Bot and check the DB with `sqlite3`: one `command_rejected` row. Try `UPDATE journal SET payload='{}'` and see it abort.
