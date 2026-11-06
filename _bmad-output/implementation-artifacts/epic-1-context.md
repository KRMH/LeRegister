# Epic 1 Context: Log phone bookings by Telegram

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The Owner (a single person) logs a phone booking in a Telegram message, either as a strict `New <chalet> <name> <phone> <dates>` command or, later in the epic, in plain words that an LLM turns into a proposed command the Owner confirms with one tap. The Bot answers only the Owner. The epic lays the foundation everything else builds on: project scaffold, SQLite store with no-delete protection, deterministic parser, append-only journal, Telegram reply path via an outbox, reporting of failed commands, and the free-text path (Interpreter, confirmation, fallback).

## Stories

- Story 1.1: Bot runs and answers only the Owner
- Story 1.2: Understand a `New` command or say why not
- Story 1.3: Journal, protect and de-duplicate every Command
- Story 1.4: Record a Phone Booking
- Story 1.5: Unexpected errors reach the Owner
- Story 1.6: Turn free text into a proposed `New` Command
- Story 1.7: Confirm before anything is recorded
- Story 1.8: Keep working when the model does not
- Story 1.9: Ask for what is missing

## Requirements & Constraints

- Record a booking (chalet, client name, E.164 phone, check-in/out, `active` status, timestamp); reply within 5 s echoing the interpreted values; appears in the Register within 1 min.
- Reject invalid input (chalet outside 1..chalet count, stay over max 60 nights, check-out not after check-in, phone missing `+`/country code or invalid) with a reason; nothing recorded. Unparseable messages get "Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec". Never guess.
- An identical `active` booking sent again creates no duplicate; reply "already recorded".
- Only the Owner's Telegram account is accepted; everyone else is ignored silently, with no reply and no data change. Owner id is set in configuration, never via chat.
- A command that fails unexpectedly is reported to the Owner, never silently dropped.
- Free text: an LLM may only propose a command. The deterministic parser stays the only authority on validity. Nothing is recorded until the Owner confirms. If the LLM is unavailable, strict commands still work.
- Incomplete plain-words bookings: the Bot keeps a short-lived draft (10 minutes, one per Owner, at most 3 questions) and asks for the first missing part; the next message fills only what is missing. Relative dates are never guessed. The phone stays local and is never sent to the model; the model may see the name, chalet and dates already understood.
- Cost must be zero or near zero; official Telegram Bot API and libraries only.
- Message text is untrusted data, never instructions. The parser has no AI model inside it. The model gets only the Owner's message and the command schema, never stored data, and has no tools.
- No user-facing path deletes data.

## Technical Decisions

- Hexagonal layout: `src/leregister/{core,adapters/{telegram,store,llm,trello,schedule,backup},app.py}`. `core` is pure: no I/O, no adapter/Telegram/SQLite/Trello/HTTP imports, and time only via a `Clock` port. An `import-linter` contract enforces this, and a second contract keeps adapters independent of each other (`app.py` wires them).
- Stack: Python 3.11, `uv`, python-telegram-bot[job-queue] 22.8, APScheduler, phonenumbers, tzdata, httpx >=0.27,<0.29, import-linter (dev).
- One SQLite DB in WAL mode is the system of record. Numbered SQL migrations applied at startup, tracked in `schema_version`. Triggers abort DELETE on `bookings`/`journal`, any UPDATE on `journal`, and any UPDATE on `bookings` other than `status`/`superseded_by` moving `active→changed|cancelled`. Mutable data lives only in side tables (`clients`, `register_cards`, `outbox`, `processed_updates`, `proposals`). No `INSERT OR REPLACE`.
- Each Command is one transaction writing `processed_updates`, state change, journal rows and outbox rows, through a single serialized writer. No network I/O inside a transaction. Duplicate Telegram updates are detected by exact `update_id`.
- Journal: `id`, `at` (UTC), `event_type` from a closed list, `subject_type`, `subject_id`, `related_booking_id`, JSON `payload`. Free text adds `proposal_confirmed` and `proposal_discarded`. Non-Owner messages are not journaled.
- Outbox is the only egress; one drainer per destination, id order, retry with backoff, text rendered at send time by the single `core` renderer (plain text, split at 4096 chars).
- Free text: a `core` `Interpreter` port (free text → schema-validated proposed command or none) with an `adapters/llm/` adapter, provider and model in config, API key in `.env`. A proposal is rendered as a strict command string and run through the existing parser. Proposals wait in the `proposals` side table until confirmed, discarded or expired (10 minutes). The call has a short timeout and never holds the writer or a transaction.
- Dates are ISO, nights run from check-in up to but excluding check-out, timestamps are UTC, "today" is computed in `Asia/Beirut`, phones are normalized to E.164 (the Client key).
- Conventions: snake_case; PRD glossary terms verbatim; statuses exactly `active|changed|cancelled`; typed results (`ok`/`rejected(reason)`) rather than exceptions for expected failures. Config and secrets come from env or a `.env` outside the repo. Logs carry ids only, never names or phones.

## UX & Interaction Patterns

- Plain-text replies, English. Free-text proposals are shown in plain words with Confirm and Cancel buttons; only the Owner's private chat can use them.

## Cross-Story Dependencies

- 1.1 provides the scaffold, config and Owner gate. 1.3 provides journal, outbox and de-duplication. 1.4 adds `bookings` and `clients`. 1.5 hardens the transaction and reply path.
- 1.6 adds the `Interpreter` port and adapter; its proposals feed the same parser and `core` use case as typed commands. 1.7 adds the `proposals` table and the confirm flow that 1.6 hands over to. 1.8 degrades 1.6 and 1.7 gracefully when the model is down.
- 1.9 builds on 1.6 (Interpreter, redaction, strict parser) and adds a `drafts` side table; it does not need 1.7 and is built first. A completed draft is handled like any proposal: shown as the strict command today, confirmed with buttons once 1.7 exists.
- Stories 2.5, 2.6 and 3.3 extend the Interpreter schema and reuse the 1.7 confirmation flow. Epics 2-6 reuse the parser, journal, outbox, store and renderer built here.
