---
title: '1.5 Unexpected errors reach the Owner'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: '362375188c58df4d1178e5fe161c6a78a83bb841'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** If processing a Command fails unexpectedly (a bug, a locked or full database), the handler error hook only writes a log line. The Owner hears nothing and may assume the booking was saved.

**Approach:** Wrap Command processing (decide plus the one-transaction record) so an unexpected exception is logged with ids only and the Owner is told the Command was not recorded and to resend it. The notice goes through the outbox when the store works, and is sent directly as a last resort when it does not. Reply delivery stays at-least-once: a failing send leaves its row pending without blocking later Commands.

## Boundaries & Constraints

**Always:** The failure covers only work before the commit (parse, decide, `record_command`); if it raises, the transaction is already rolled back and no booking, journal, outbox or `processed_updates` row from that Command remains. The notice text is rendered by the single `core` renderer: "That command was not recorded. Please resend it." It is queued as an outbox row of kind `command_failed` with no `processed_updates` row and no journal row. If queueing also fails, the same text is sent directly through the bot, best effort. If that fails too, only an error log is written. Log lines carry `update_id`, `chat_id` and the exception type, never names, phones or message text. A failure after the commit (draining the reply) never produces the "not recorded" notice: the Command was recorded, and the retry job delivers the reply. The Owner gate still runs first; only the Owner is ever told.

**Never:** No new journal event type (the closed list has none for this). No retry or replay of the failed Command. No maximum-attempts cap or dead-letter state on outbox rows (a row stays pending until it succeeds, per the story). No change to Commands, parser, schema or migrations. No swallowing of `CancelledError`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Failure before commit | `record_command` raises after the booking insert | Everything from that Command rolled back; Owner receives the not-recorded notice; `command_failed` outbox row done | Log: update_id, chat_id, exception type |
| Store unusable | `record_command` and the queueing both raise | Notice sent directly through the bot | Log both failures |
| Nothing works | store and direct send both fail | No exception escapes the handler | Error log with ids only |
| Bug in decide | pure code raises | Same as a failure before commit | Same |
| Failure after commit | draining the reply raises | No "not recorded" notice; booking stays recorded; retry job delivers | Warning log |
| Reply send fails | Telegram rejects or is down | Outbox row stays pending, retried with backoff | Warning log, id only |
| Later Command | an earlier reply is still pending | New Command is recorded and answered normally | N/A |
| Duplicate update | same `update_id` again | Ignored, no notice | N/A |

</frozen-after-approval>

## Code Map

- `src/leregister/adapters/telegram/bot.py` -- `handle_update`: wrap decide and `record_command`; on exception log, call the notice helper; wrap the post-commit drain separately; keep the raw sender in `bot_data["send"]`
- `src/leregister/core/replies.py` -- add `command_failed` kind and its text
- `src/leregister/core/ports.py` -- add `Store.queue_reply(chat_id, reply, at)`; reuse the rest
- `src/leregister/adapters/store/store.py` -- `queue_reply`: one outbox row, no `processed_updates`, no journal
- `src/leregister/adapters/telegram/drainer.py` -- unchanged; already retries and does not block later rows
- `tests/test_owner_gate.py`, `tests/test_store.py`, `tests/test_drainer.py` -- new cases per the matrix; keep the existing rollback tests

## Tasks & Acceptance

**Execution:**
- [x] `src/leregister/core/replies.py`, `core/ports.py`, `adapters/store/store.py` -- notice text, `queue_reply` port and implementation -- AR10
- [x] `src/leregister/adapters/telegram/bot.py` -- failure handling, direct-send fallback, separate post-commit drain guard -- FR-8
- [x] `tests/` -- every matrix row, an end-to-end failure after the booking insert with all tables checked, ids-only log assertion, import contracts still green -- AC

**Acceptance Criteria:**
- Given a failure after the state change but before commit, when the Command runs, then no booking, client, journal or processed-update row from it exists and the Owner receives the not-recorded notice.
- Given a failure to send a reply, when the drainer retries, then the row stays pending until it succeeds and a later Command is recorded and answered.
- Given the test suite, when run, then `lint-imports` keeps both contracts.

## Implementation Notes

Implemented directly (no subagent). `handle_update` wraps decide and `record_command` in one try; the post-commit drain has its own guard so a delivery problem never reports a recorded Command as failed. `_tell_owner_not_recorded` queues via the new `Store.queue_reply` (outbox row only), drains, and falls back to `bot_data["send"]` only when queueing itself fails, so the notice is never sent twice. `command_failed` text lives in `core/replies.py`. New `tests/test_failure_path.py` covers every matrix row. 162 tests pass; both contracts kept.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| Rollback test relies on `json.dumps` raising, not on a real mid-transaction fault | low | patch | Added a test that patches `_record_booking` to insert and then raise |
| Failure logs give no way to find the cause | medium | patch | Log now carries `origin=file:line` of the innermost frame, never the message; test added |
| Owner gate ordering for failures untested; raw sender wiring untested | low | patch | Two tests added |
| Exception after commit would report a saved Command as "not recorded" | low | rejected | Only reachable through executor machinery; the identical-booking rule makes a resend answer "Already recorded", never a duplicate |
| Failed update left unmarked and redelivered after restart | low | rejected | Documented decision in Design Notes; a re-processed identical booking is "Already recorded" |
| Stale notice delivered long after a resend; bursts of identical notices | low | rejected | Needs an expiry rule the story does not ask for |
| Direct-send fallback fails: notice lost | low | rejected | Spec: log only when everything fails |
| No timeout on the direct send | low | rejected | The Telegram library applies its own request timeouts |
| `queue_reply` accepts unknown kinds; not idempotent; hard-codes `telegram` | low | rejected | Single internal caller with a fixed kind |
| Notice does not say which Command failed | low | rejected | Wording is fixed by the story: "not recorded, resend it" |
| Failure counter or health flag | low | rejected | Out of scope for Epic 1 |

## Design Notes

Why no `processed_updates` row for the notice: the Owner is told to resend, which arrives as a new update id. Leaving the failed update unmarked means that if Telegram redelivers it (for example after a restart before the handler finished), it is simply processed again. The direct-send fallback exists because the store is the most likely thing to be broken when this path runs.

## Verification

**Commands:**
- `uv run --no-sync pytest` -- expected: all tests pass
- `uv run --no-sync lint-imports` -- expected: both contracts kept

**Manual checks (if no CLI):**
- Cannot be triggered from Telegram without breaking the bot. Optional: lock the database with a second process holding `BEGIN EXCLUSIVE`, send `New 2 Sam +96171123456 12-15 dec`, and see the "not recorded" notice after the 5-second busy timeout.
