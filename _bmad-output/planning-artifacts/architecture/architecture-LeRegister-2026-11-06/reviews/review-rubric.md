# Rubric review: ARCHITECTURE-SPINE.md vs prd.md (LeRegister)

Reviewer: rubric pass. Spine not edited.

## Verdict
**Revise before handoff (sound base, 5 material gaps).** The paradigm, the AD set and the FR map are strong. Every FR-1..FR-12 is bound. The gaps are in under-specified seams (outbox, Register mapping, overlap lifecycle), in operations and security, and in a few Rules that are not enforceable as written.

## Checklist results
| Check | Result |
| --- | --- |
| Fixes the real divergence points, misses none | Partial. Misses: outbox ownership, status-to-Trello-list mapping, overlap lifecycle, schema/migration ownership, rejected-command journaling |
| Every AD Rule enforceable and prevents its divergence | Partial. AD-1, AD-3, AD-4, AD-8, AD-9, AD-10, AD-11 have gaps (see below) |
| Nothing Deferred lets units diverge | Mostly. Test strategy and timezone/region are low risk. Data protection deferral collides with the backup and Trello decisions |
| Named tech plausible and current | Yes, with one overclaim (AD-8) and unverified patch versions |
| Covers FR-1..FR-12 | Yes, mapped. Depth gaps on FR-5, FR-8, FR-11, FR-12 |
| Every dimension decided, deferred or open | Deployment/environments, operations and security are the weak dimensions |

## Findings (ordered by severity)

### F1. Outbox is named but not designed (AD-4, AD-9, AD-11) - HIGH
AD-4 says replies, Alerts and Trello sync run "from an outbox table" after commit. Nothing says who drains it, in which adapter, in what order, how a crash between commit and send is recovered, or whether delivery is at-least-once (duplicate Alerts) or at-most-once (lost Alerts). The `core` port list and the hexagon diagram have no outbox/dispatcher. Two units (telegram, trello) will each invent their own drain loop. FR-4 "Alert within 1 minute" and FR-8 "failed Command reported, never silently dropped" depend on it.
Also: AD-4 says the `update_id` is "stored" but not that it is written in the same transaction as the state change. If stored separately, redelivery after a crash can double-apply or drop a Command.
Fix: add an AD (or extend AD-4) naming the dispatcher, its owner module, delivery semantics, retry/ordering, and that `update_id` is committed in the Command transaction. Add a catch-all rule: unexpected exceptions roll back, are logged, and produce an Owner-visible error reply (the Errors convention only covers expected failures).

### F2. Register projection mapping is undecided (AD-11, FR-12, FR-5) - HIGH
- Status-to-list mapping is not stated. Four lists (Active, Overlap, Changed, Cancelled) versus three Statuses: the rule that moves an `active` card between Active and Overlap is missing.
- Overlap is a derived condition. When booking B is cancelled or changed, booking A's card must leave Overlap. Nothing says the sync recomputes affected neighbours. FR-5 requires the Overlap to stay visible "until it no longer exists".
- FR-12 requires Rating and time of last change on each card. A Rating change affects every card of that Client. No rule says which events trigger a card update, or which fields the card carries.
- "Rebuildable from SQLite" (AD-2) has no defined mechanism (a command, a function, an owner) and is not testable as written.
- Overlap lifecycle is undecided: stored rows or computed on read? The Morning Summary (open Overlaps in the next 3 days) and the Register need the same answer or they will disagree. Also unaddressed: a new booking overlapping two others (Alert wording, one Journal row per pair?).
Fix: add one AD "Overlap is derived from active bookings by one core function; the Journal records detection events", plus a mapping table (status/overlap to list, card fields, sync triggers).

### F3. Rules that are not enforceable as written - MEDIUM
- AD-1 / import direction: "core imports no adapter..." has no mechanism. Add `import-linter` (or an AST test) as a gating check; otherwise it is advice.
- AD-3: triggers block DELETE and journal UPDATE, but "a booking row may change only `status` and `superseded_by`" has no trigger stated. Make it explicit. Client rows are not guarded against DELETE. Migrations are cited as a risk but no migration tool or ownership is chosen (see F5).
- AD-9: "never sent twice for one date" is not achievable if the journal event is written after the send (crash between the two). Write an intent row first, or route the summary through the outbox with a unique key on date. The late-send window "before 12:00" has no counterpart for a missed backup after sleep. FR-11's "retry on failure" has no retry policy (AD-11 backoff covers only Trello).
- AD-10: "restore procedure documented and tested" names no owner or test artefact. "Synced folder" as the target is also a privacy decision (F4).
- AD-8: "Telegram holds updates while the Bot is offline, so Commands sent during downtime are applied in order" is an overclaim. Telegram keeps undelivered updates for about 24 hours only, so a longer outage silently loses Commands. A replayed Command is also interpreted with the then-current "today", so year inference ("next occurrence") can differ from intent. State both, and require a "back online, N queued Commands" notice.
- AD-11: "After 3 failures the Owner is told" does not say what happens next (stop? periodic retry? backfill). The backoff can exceed FR-1's 1-minute Register SLA with no stated target.
- AD-4 serialises Telegram updates only. Scheduler jobs, the outbox worker and Trello sync also touch SQLite. No decision on WAL mode, busy timeout or a single-writer rule.

### F4. Security and data protection under-decided - MEDIUM
- Guest names and phone numbers go to Trello (third-party, US-hosted) and possibly to a cloud-synced backup folder (AD-10). The PRD defers data protection to phase 3, but these decisions already place personal data on third parties. Record this as a conscious, flagged decision or Open Question for the Owner.
- The SQLite file and backups are unencrypted at rest on the Owner's PC. No decision or deferral recorded.
- Logs: "no secrets" is stated, but logs would contain phone numbers and names. Pick a rule (mask phones) and log rotation/retention.
- Trello token scope and Telegram token rotation/compromise response are not mentioned. One line each is enough.
- AD-6 is good. State that the check precedes storing `update_id` or logging content, so strangers cannot grow the DB or logs.
- State that the Trello board must be private.

### F5. Operations, deployment and environments are thin - MEDIUM
- PRD Open Question 1 (hosting) is resolved in the spine as "Owner's computer" but is not flagged as pending Owner confirmation. Only the wrapper is deferred. Mark it `[ASSUMPTION]`.
- PRD section 6: "A down Bot must be noticed." The spine relies on absence of the Morning Summary, which says nothing about mid-day outages. Decide: heartbeat/dead-man check, or explicitly accept silence as the signal and defer with the risk stated.
- No decision on: config file format and key names (token, owner id, timezone, region, backup dir, summary time; FR-11 says configurable), schema migration tool and DDL ownership, log location and rotation, lockfile policy (commit uv.lock), upgrade/rollback, and dev/test/prod separation (separate test bot token and test Trello board; a dev copy on the live token would steal updates under long polling). Units could pick different conventions.
- "Test strategy and CI" is deferred. AD-1 testability and AD-10 "tested restore" depend on it. At least name the layers (pure-core unit tests, SQLite integration tests, fake Telegram/Trello adapters).

### F6. Journal scope does not satisfy the PRD metrics - LOW/MEDIUM
SM-5 and SM-C1 are "counted from the Journal" (Commands understood and rejected). The spine journals state changes only. State whether rejected and unparseable Commands (FR-2) are journaled, or change how the metric is measured.

### F7. Smaller points
- Cancel/Change lookup (match key, ambiguous match) and the FR-1 "identical booking" definition are not placed. Assign both to `core` with the match key.
- Year inference depends on "today" in the configured timezone. Put it in AD-7.
- Default region `FR` is assumed, and PRD Open Question 5 stays open. Changing it affects only future entries without `+`; say so.
- Client name storage (Client row, booking, or both) is not shown in the ER diagram, though the Register shows name per booking.
- "Rating Command for a phone with no booking returns an error" (FR-9) lives only in the PRD. Put it in AD-12.

## Technology check
- Python 3.11.9 with bundled SQLite 3.45.1: consistent for the Windows installer; 3.11 is supported until Oct 2027.
- python-telegram-bot 22.x with `job-queue`, APScheduler 3.11.x (PTB pins below 4), httpx `>=0.27,<0.29`: plausible and consistent. I could not verify exact patch versions (22.8, phonenumbers 9.0.42, uv 0.13.7); confirm against PyPI before locking.
- Trello free REST API: current; rate limits (about 100 requests per 10 s per token) are not mentioned and matter for a full rebuild.
- Async PTB runtime with synchronous SQLite: state that DB calls run on one worker/thread or via `asyncio.to_thread`, or the event loop and APScheduler will contend.

## Deferred section audit
- Always-on / service wrapper: safe to defer, but see F5 for the detection gap.
- Trello alternatives: safe, port exists.
- Data protection: not safe to defer entirely given F4.
- Timezone/region: marked ASSUMPTION; safe, config-only change.
- Test strategy/CI: low risk, but name the test layers (F5).

## What is good
Clear hexagonal boundary, single system of record, database-level never-delete enforcement, deterministic parser, idempotent update handling, Owner gate before parsing, half-open night semantics, explicit map covering all twelve FRs.

## Suggested minimum edits
1. Outbox/dispatcher AD, `update_id` in the Command transaction, catch-all error rule (F1).
2. Overlap-derivation AD, Register mapping table and rebuild mechanism (F2).
3. Make AD-1/AD-3/AD-9 enforceable: import-linter, explicit trigger, summary intent row (F3).
4. Add a Security/Ops block: PII locations, at-rest, log rules, heartbeat decision, config and migration conventions, environment separation (F4, F5).
5. Correct the AD-8 24-hour claim and decide journaling of rejections (F3, F6).
