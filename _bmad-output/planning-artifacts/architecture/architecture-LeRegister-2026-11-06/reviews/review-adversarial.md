# Adversarial review: LeRegister architecture spine

Target: `ARCHITECTURE-SPINE.md` (draft, 2026-11-06). Source: `prd.md`.
Method: for each finding, two units one level down (A and B) each obey every AD literally, yet their outputs cannot work together. Each finding ends with a proposed AD (new or tightened).

## Verdict

**Not ready to fan out to units.** The principles (pure core, SQLite as truth, append-only, outbox) are sound. But the spine fixes almost no shared-data shapes. Journal, outbox, update-id store, clock, reply rendering and the port list are all unowned. It also contains one hard self-contradiction (AD-3 vs AD-11). 14 pairs found: 4 blockers, 6 high, 4 medium. Closing them needs about 8 new ADs and 5 tightenings, none of which change the paradigm.

---

## Blockers

### B1. AD-3 forbids the columns AD-11, FR-12 and the Rating display need
- **Unit A (store):** implements AD-3 literally: the trigger aborts any UPDATE on `bookings` except `status` and `superseded_by`. Bookings has no `trello_card_id`, no `updated_at`.
- **Unit B (trello):** AD-11 says "the Trello card id is stored in SQLite". B adds `trello_card_id` to `bookings` and sets it after sync. It aborts. B moves it to a side table. FR-12 "time of last change" has the same problem: a third unit (summary/register view) adds `updated_at` to `bookings` and hits the trigger.
- **Result:** both comply with the letter of their own AD and cannot run together. The ER diagram shows no table for the card id.
- **Proposed AD-3 tightening:** "`bookings` holds only immutable booking facts plus `status` and `superseded_by`. Mutable bookkeeping lives in named side tables: `register_cards(booking_id PK, trello_card_id, last_synced_journal_id, fail_count)` and `outbox`. 'Time of last change' is derived as the max journal timestamp for the booking. Allowed status transitions are enforced by trigger: `active->changed`, `active->cancelled` only; `superseded_by` is set once, only on a `changed` row."

### B2. The journal has no schema, so three units write three journals
- **Unit A (booking use cases):** `journal(id, booking_id NOT NULL, event_type, old_json, new_json, at)`.
- **Unit B (rating):** a Rating event has a client, not a booking. B writes `booking_id = NULL` and `client_phone` in a new column, or stuffs the phone into JSON.
- **Unit C (scheduler):** AD-9 needs "summary sent for 2026-11-07" and backup events, which have neither booking nor client. C puts the date in a free-text `note` and the late-summary check queries `event_type='summary' AND note=...`.
- **Result:** A's `booking_id NOT NULL` rejects B and C. Different event-type spellings and payload shapes make SM-5 (count first-try understanding from the journal), FR-5 and the AD-9 restart check impossible to query uniformly.
- Also unresolved: are rejected Commands journaled? SM-5 and SM-C1 count them, but AD-4 only journals state changes. An overlap involves two bookings, but the ER shows journal-to-one-booking.
- **Proposed new AD-13 (Journal shape):** "One `journal` table: `id` integer, `at` UTC, `event_type` from a closed enum defined in `core` (`booking_recorded, booking_cancelled, booking_changed, overlap_detected, overlap_resolved, rating_changed, command_rejected, summary_sent, backup_done, sync_failed`), `subject_type` (`booking|client|system`), `subject_id` (nullable), `related_booking_id` (nullable, second booking for overlap), `payload` JSON with a per-event schema in `core`. `command_rejected` rows are written in their own transaction with the `update_id`. The enum and payload schemas are the only definition of the journal; adapters never write rows directly."

### B3. Two consumers, one outbox, no definition
- AD-4 puts replies, Alerts and Trello sync "in an outbox table". It does not say its shape, who drains it, or whether Trello rows and Telegram rows share a status.
- **Unit A (telegram):** drains rows `WHERE sent_at IS NULL`, marks them sent after delivery. It also sends the direct reply from the use-case result before commit-then-outbox, "to meet the 5 s target".
- **Unit B (trello):** drains the same table with the same predicate, marking `sent_at` after the Trello call. A takes Trello rows and posts garbage to Telegram, or B marks A's Alert row as synced and the Alert never goes out. If instead each uses its own table, "Owner told after 3 failures" has no path, because adapters cannot import each other.
- **Direct reply vs outbox:** if A replies directly, a crash between commit and reply plus AD-4 redelivery dedupe means the reply is lost forever (update_id already stored). If everything is in the outbox, the 5 s latency depends on drain frequency, unspecified.
- **Proposed new AD-14 (Outbox contract):** "`outbox(id, destination ENUM('telegram','register'), kind, payload JSON, created_at, attempts, next_attempt_at, delivered_at, last_error)`. Each destination has exactly one drainer, owned by its adapter, which selects only its own destination. Every user-visible message including the direct reply to a Command is an outbox row written in the Command's transaction; the Telegram drainer is woken immediately after commit (target under 1 s) and also polls. Register rows carry only `booking_id` (see AD-15). A Register failure count over 3 enqueues a `telegram` outbox row through a `core` use case, not an adapter-to-adapter call."

### B4. Overlap is checked against the wrong state on Change
- AD-4 says the check runs in the same transaction. PRD FR-7 says the original is marked `changed` and a new `active` one is created. Nothing fixes the order.
- **Unit A:** inserts the new `active` row, runs the overlap query, then marks the old `changed`. The new 14-17 Dec booking overlaps the still-active old 12-15 Dec booking of the same client and chalet: a false Alert and a false `overlap_detected` journal row on every date shift (UJ-2's own scenario).
- **Unit B:** marks old `changed` first, then inserts and checks. Correct.
- Both obey every AD. SM-C2 says not to suppress Alerts, so the false positive cannot be waved away.
- Related: overlap pair identity. If A alerts "per Command per pair" and B alerts "per new pair only", a later unrelated Command in the same chalet re-alerts for an existing, already-alerted pair in A but not B. FR-5 ("entry exists for every Alert") is satisfied differently.
- **Proposed new AD-16 (Overlap evaluation):** "Overlap is evaluated on the post-Command state inside the transaction: apply status changes first (old `changed`/`cancelled`), insert the new row, then query. An Overlap is identified by the unordered pair `(min booking_id, max booking_id)` and exists exactly while both are `active`. `overlap_detected` is journaled and Alerted once per new pair; `overlap_resolved` is journaled when either member leaves `active`. Overlap state is always derived from `bookings` (never stored as a flag); the Summary, Register 'Overlap' list and Alerts all use the one `core` function `open_overlaps()`."

---

## High

### H1. "Today", the year, and the clock: who owns time
- AD-1 says the core performs no I/O, AD-7 says "today" is computed in a configured timezone. The PRD says the year is "the next occurrence of that date". No clock port exists.
- **Unit A (parser):** calls `datetime.now()` inside the parser (it is "pure" in the sense of no network or DB). Resolves `12 dec` sent on 12 Dec as this year.
- **Unit B (cancel use case):** receives `today` as an argument and resolves a tie as next year. `Cancel 2 12 dec` sent on the day itself, or after check-in (a Cancel/Change for a stay already started), matches nothing in B, matches in A. Test determinism also differs.
- Also: year inference cannot express a Stay crossing a month or year (`30-2` has one `<month>`), and the PRD form never allows a start-month and end-month. A rejects it; B silently reads `30-2 jan` as 30 Jan to 2 Jan then rejects. Decide in the spine.
- **Proposed new AD-17 (Time and date resolution):** "`core` takes a `Clock` port (now in UTC) and a `Config` value object (timezone, default region, owner id, chalet count) and never reads the system clock or environment. Year resolution: the nearest date on or after today in the configured timezone; a date equal to today resolves to today. The Cancel/Change lookup resolves its date by the same function against the existing bookings' dates (prefer the active booking whose check-in matches in the current or next 12 months). A cross-month Stay is outside grammar v1 and is rejected with reason `end_before_start` (raise as PRD change)."

### H2. Register projection content has no owner, and Rating changes do not reach it
- FR-12 requires Rating and last-change time on each card. AD-11 says "keyed by booking id".
- **Unit A (core):** emits `booking_changed` outbox rows only on booking mutation.
- **Unit B (trello):** builds the card from a snapshot in the row (name, dates, rating at enqueue).
- A Rating Command changes the Client row only (AD-12), enqueues nothing for the client's bookings, so every card shows a stale Rating. Conversely, if rows carry snapshots and are retried with backoff, a stale retry overwrites a newer state (out-of-order delivery).
- Who decides the Overlap/Active list: Trello adapter (querying SQLite, which AD-1 forbids as logic) or core?
- **Proposed AD-15 (Projection rule):** "A pure `core` function `register_card(booking_id) -> CardView` (fields, target list, description including the booking id) is the only definition of the Register. The Register outbox row holds only `booking_id`; the drainer computes the `CardView` from current state at send time, coalescing rows per booking. Any change to a Client's Rating, or to a booking's status or overlap membership, enqueues Register rows for every affected booking in the same transaction. A `rebuild_register` use case enqueues all bookings."

### H3. Client row vs booking row: two owners of name, Rating snapshot
- AD-12 puts Rating on Client. PRD says name is informational, key is phone. FR-12 shows "Client name" per booking.
- **Unit A:** stores `client_name` on `bookings` (history preserved, rows nearly immutable per AD-3) and none on `client`.
- **Unit B:** stores `name` on `client`, updating it on every new booking (latest wins), and the Register shows B's name for old bookings too.
- Neither is forbidden. Cards, Summary and Alerts then differ ("Sam" vs "Samuel").
- Related: FR-1 duplicate rule ("identical active booking") has no identity. A: chalet+dates+phone. B: chalet+dates+phone+name, so a typo in the name makes a second booking and a false Overlap with itself.
- Also FR-9: "phone with no Phone Booking returns error": does a `cancelled`-only client count? When is the Client row created, at first booking in the same transaction (A) or lazily at first rating (B)? B's lazily-created client violates FR-9.
- **Proposed new AD-18 (Client and identity):** "A Client row is created in the transaction of its first recorded booking and never otherwise. The name on `bookings` is the as-entered name and is immutable; `client.name` is not stored. 'Existing Client' means a Client row exists (cancelled bookings count). The duplicate check key is `(chalet, check_in, check_out, client_phone)` over `active` bookings, name excluded. Cancel/Change lookup key is `(chalet, check_in)` over `active` bookings."

### H4. Rating semantic gaps leave Journal and Register out of step
- Clamp at 1 or 5: A writes no journal row and replies "Rating 5" (no change). B writes a `rating_changed 5->5` row. SM and FR-9 "every Rating change is recorded" are both met. The "prior report" test in FR-10 (Rating 5 with any prior report) then differs: A can't tell, B counts journal rows.
- **Proposed AD-12 tightening:** "A report at the bound changes nothing, writes a `rating_reported` journal row with `old=new`, and increments `client.report_count` in the same transaction. 'Has prior report' is `report_count > 0`. The reply and the booking confirmation read Rating and `report_count` from the Client row."

### H5. Update dedupe and non-message updates
- AD-4 stores `update_id`, but not where (which table, written in which transaction) or what kinds of Telegram update are handled.
- **Unit A:** registers a handler for `filters.TEXT` messages only.
- **Unit B:** `filters.TEXT` including `edited_message`. The Owner fixes a typo by editing: new update_id, second booking, a spurious Overlap, or an "already recorded".
- Also, a rejected command is deduped by update_id only if stored in a transaction that also commits on rejection (see B2).
- **Proposed AD-4 tightening:** "Only new, non-edited private text messages from the Owner are Commands. Edited messages, callbacks, media and all other update types are ignored without reply. `processed_updates(update_id PK, processed_at)` is written in the same transaction as the Command's effects, including for rejections."

### H6. Scheduler jobs bypass AD-4 and race the single writer
- AD-4: "Telegram updates are handled strictly one at a time". The APScheduler job (summary, backup), the two outbox drainers and Telegram handlers all run in one process and write SQLite.
- **Unit A (schedule):** opens its own sqlite connection, writes `summary_sent` outside a use case.
- **Unit B (store):** holds a single connection with a mutex-free transaction per Command.
- Result: `database is locked`, or the summary event is written at a different time from the actual send. If written at enqueue (after commit, before delivery) and the send then fails, the AD-9 startup check sees an event and never retries the late summary; if written after delivery, a crash between send and write sends it twice (violates "never twice").
- Backup adapter also needs the live database: it cannot import `store`, so it opens a second connection.
- **Proposed AD-9/AD-4 tightening:** "Every write goes through a `core` use case via the `Storage` port, which serializes all write transactions (one connection, one lock, or `BEGIN IMMEDIATE` with busy timeout). The scheduler only invokes use cases (`send_summary(date)`, `run_backup()`). `send_summary` writes `summary_queued(date)` plus the outbox row in one transaction (a unique constraint on `(event_type, date)` makes the second attempt a no-op), and `summary_sent(date)` is journaled by the Telegram drainer on delivery. The startup check retries if `summary_queued` exists but `summary_sent` does not and before 12:00."

---

## Medium

### M1. Who renders text?
AD-1 puts "summary content" in the core; replies, Alerts and cards are also text. **A** returns structured results and the adapter formats French strings; **B** returns finished strings from core with Markdown. Language (FR or EN) and exact wording (PRD quotes "Recorded: Chalet 2, Sam, 12-15 Dec") become divergent per message type. B's names go into Telegram MarkdownV2 unescaped: a name like `Sam_` or `*` mangles messages or breaks send (AD-5 says message text is "never formatted into queries" but is silent on formatting into messages). The 4096-char Telegram limit breaks a heavy-day Summary.
**Proposed new AD-19 (Presentation):** "`core` returns structured view models; one `core/presenter` module renders all Owner-facing text (language fixed in config, default French with English labels from PRD strings) as plain text with no parse mode. Messages over 4000 characters are split on line boundaries. Trello description uses the same plain-text rule."

### M2. Port list is implicit
The spine says "ports (interfaces)" but names none. A defines `BookingRepository`, `ClientRepository`, `JournalRepository` (three stores, three transactions); B defines one `UnitOfWork`. Atomicity across repositories (AD-4) is only possible with the latter.
**Proposed AD-1 tightening:** "Ports are exactly: `UnitOfWork` (one transaction exposing bookings, clients, journal, outbox, processed_updates), `Clock`, `Config`, `Notifier` (not used by core: delivery is by outbox), `BackupService`. Use cases take a `UnitOfWork` factory. No other persistence interface exists."

### M3. Migrations and schema ownership
Triggers (AD-3), outbox, processed_updates, register_cards: each adapter-owner adds DDL its own way (inline `CREATE IF NOT EXISTS` in telegram's dedupe code vs a migration in store). A schema created outside the AD-3 trigger set escapes the never-delete rule.
**Proposed new AD-20:** "`adapters/store/migrations/NNNN_*.sql` is the only place DDL exists, applied in order at startup with a `schema_version` check. Every table is append-only or protected by trigger unless explicitly listed in AD-3 as mutable (`clients`, `register_cards`, `outbox`, `processed_updates`)."

### M4. Restore and rebuild paths leave the projection and dedupe inconsistent
Restoring a backup rolls back `register_cards` and `processed_updates`, but the Trello board has newer cards (and a board lost entirely has dead card ids). Unit A's restore leaves the cards; unit B's restore deletes the board. AD-2 says "fully rebuildable" with no procedure, and AD-3 forbids archiving cards, so duplicates cannot be tidied.
**Proposed AD-10/AD-11 tightening:** "After a restore, startup runs `rebuild_register`: for each booking find the card by the booking id in its description (search the board), re-link `register_cards`, create missing ones, never delete extras. Commands received between the backup and the restore are lost and the Owner is told the backup timestamp."

---

## Gaps worth a PRD note (not architecture)
- Cross-month Stays have no grammar (`<start>-<end> <month>`). Names with spaces break whitespace tokenisation of `New 2 Sam 0612345678 ...`.
- Phone with spaces (`06 12 34 56 78`) conflicts with the same tokenisation. The parser grammar must be tokenised from the right (dates, phone) so the name is the remainder.

## Summary of required changes
New ADs: 13 Journal shape, 14 Outbox contract, 15 Projection rule, 16 Overlap evaluation, 17 Time/date, 18 Client/identity, 19 Presentation, 20 Migrations. Tightened: AD-1 (ports), AD-3 (side tables, transitions), AD-4 (update types, processed_updates, serialized writes), AD-9 (summary event two-phase), AD-10/11 (restore and rebuild), AD-12 (report count).
