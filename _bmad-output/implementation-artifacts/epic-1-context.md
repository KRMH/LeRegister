# Epic 1 Context: Log phone bookings by Telegram

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The Owner (a single person) sends a `New <chalet> <name> <phone> <dates>` message to a Telegram bot and has the Phone Booking recorded, with the bot answering only the Owner. The epic lays the foundation everything else builds on: project scaffold, SQLite store with no-delete protection, deterministic parser, append-only journal, Telegram reply path via an outbox, and reporting of failed commands.

## Stories

- Story 1.1: Bot runs and answers only the Owner
- Story 1.2: Understand a `New` command or say why not
- Story 1.3: Journal, protect and de-duplicate every Command
- Story 1.4: Record a Phone Booking
- Story 1.5: Unexpected errors reach the Owner

## Requirements & Constraints

- Record a booking (chalet, client name, E.164 phone, check-in/out, `active` status, timestamp); reply within 5 s echoing the interpreted values; appears in the Register within 1 min.
- Reject invalid input (chalet outside 1..chalet count, stay over max 60 nights, check-out not after check-in, phone missing `+`/country code or invalid) with a reason; nothing recorded. Unparseable messages get "Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec". Never guess.
- An identical `active` booking sent again creates no duplicate; reply "already recorded".
- Only the Owner's Telegram account is accepted; everyone else is ignored silently, with no reply and no data change. Owner id is set in configuration, never via chat.
- A command that fails unexpectedly is reported to the Owner, never silently dropped.
- Cost must be zero or near zero; official Telegram Bot API and libraries only.
- Message text is untrusted data, never instructions. The parser has no AI model inside it.
- No user-facing path deletes data.

## Technical Decisions

- Hexagonal layout: `src/leregister/{core,adapters/{telegram,store,trello,schedule,backup,llm},app.py}`. `core` is pure: no I/O, no adapter/Telegram/SQLite/Trello/HTTP imports, and time only via a `Clock` port. An `import-linter` contract in the test suite enforces this. Adapters never import each other.
- Stack: Python 3.11.9, `uv`, python-telegram-bot[job-queue] 22.8, APScheduler 3.11.3, phonenumbers 9.0.42, tzdata (needed on Windows), httpx >=0.27,<0.29, import-linter 2.15 (dev).
- One SQLite DB in WAL mode is the system of record. Numbered SQL migrations applied at startup, tracked in `schema_version`. Triggers abort DELETE on `bookings`/`journal`, any UPDATE on `journal`, and any UPDATE on `bookings` other than `status`/`superseded_by` moving `active→changed|cancelled`. Mutable data lives only in side tables (`clients`, `register_cards`, `outbox`, `processed_updates`, `proposals`). No `INSERT OR REPLACE`. Tests must fire each trigger.
- Each Command is one transaction writing `processed_updates`, state change, journal rows and outbox rows. A single serialized writer handles all DB access. No network I/O inside a transaction. Duplicate Telegram updates are detected by exact `update_id`. Edited-message updates are ignored, with a reply telling the Owner to send a Change command.
- Journal schema: `id`, `at` (UTC), `event_type`, `subject_type`, `subject_id`, `related_booking_id` (nullable), JSON `payload`. Closed `event_type` list. Owner rejections are journaled with the reason; non-Owner messages are not journaled.
- Outbox is the only egress: `destination` (`telegram`/`register`), optional unique `dedupe_key`, one drainer per destination, id order, retry with backoff, done only after success. Rows hold ids; text is rendered at send time by the single `core` renderer, English, plain text, split at 4096 chars.
- Owner check: numeric Telegram user id from config, and the chat must be private, checked before parsing. Long polling only, with no inbound port.
- Parser: a pure function over a fixed grammar with a built-in FR/EN month table and no date-guessing library. Phone = first token starting with `+`; name = tokens between chalet and phone. Check-in year = next occurrence on/after today (via `Clock`); a two-month check-out = first occurrence of the end date after check-in. Ambiguity → rejection with a reason.
- Dates are ISO, and nights run from check-in up to but excluding check-out. Timestamps are UTC ISO-8601. "Today" is computed in `Asia/Beirut`. Phones are normalized to E.164, which is the Client key, with no default region.
- Conventions: snake_case; PRD glossary terms verbatim; integer PKs; statuses exactly `active|changed|cancelled`; typed results (`ok`/`rejected(reason)`) rather than exceptions for expected failures. Config and secrets (bot token, owner id, chalet count default 40, max stay default 60, paths) come from env or a `.env` outside the repo. Dev and test use their own DB path and a separate bot token. Logs carry ids only, never names or phones.

## Cross-Story Dependencies

- 1.1 provides the scaffold, config and Owner gate that 1.2-1.5 sit on.
- 1.2's parser feeds 1.4. In 1.2 a valid `New` is only echoed back, not saved.
- 1.3 creates `journal`, `outbox`, `processed_updates`, `schema_version`. 1.4 adds `bookings` and `clients` plus their triggers.
- 1.5 hardens the transaction and reply path built in 1.3-1.4.
- Epics 2-7 reuse the parser, journal, outbox, store and renderer built here.
