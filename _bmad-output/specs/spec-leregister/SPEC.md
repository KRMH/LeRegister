---
id: SPEC-leregister
companions:
  - command-grammar.md
  - glossary.md
  - ../planning-artifacts/architecture/architecture-LeRegister-2026-11-06/ARCHITECTURE-SPINE.md
sources:
  - ../planning-artifacts/prds/prd-LeRegister-2026-11-06/prd.md
  - ../planning-artifacts/briefs/brief-LeRegister-2026-11-06/brief.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# LeRegister

## Why

The owner of 40 ski chalets enters every phone booking by hand, 2-3 hours a day, and about 5 times a season two of them land on the same chalet and dates. Online-channel bookings already sync; phone bookings do not. LeRegister lets the Owner log a phone booking with one short Telegram message, flags overlaps at once, and replaces the manual morning cross-check with one summary message. Phase 1 covers phone bookings only, for one user, at zero running cost.

## Capabilities

- **CAP-1**
  - **intent:** The Owner can record a phone booking with one short Telegram Command (chalet, name, phone, dates).
  - **success:** The Bot replies within 5 seconds echoing chalet, name and dates (and the client's Rating if one exists), and the booking appears in the Register within 1 minute. An identical active booking sent twice creates no duplicate and replies "already recorded". Chalet outside 1 to the configured chalet count (default 40), check-out not after check-in, a stay longer than the configured maximum (default 60 nights), or a phone number without `+` and country code (or invalid) is rejected and nothing is recorded.

- **CAP-2**
  - **intent:** The system refuses what it cannot understand and acts only for the Owner.
  - **success:** A non-matching message creates or changes nothing, and the reply names the failed part when it can and shows a correct example. Any ambiguity is rejected, never guessed. A Command from any other Telegram account changes no data and gets no reply.

- **CAP-3**
  - **intent:** The Owner is alerted at once when a recorded or changed phone booking overlaps another active one in the same chalet.
  - **success:** The Alert naming chalet, dates and both clients arrives within 1 minute. A check-out day equal to the next check-in day raises no Alert. Cancelled and changed bookings are never compared. Both bookings stay active, a journal entry exists for every Alert, and the overlap shows in the Register and Morning Summary until it no longer exists.

- **CAP-4**
  - **intent:** The Owner can cancel a phone booking without losing its record.
  - **success:** The booking's Status becomes `cancelled`, the Bot confirms chalet and dates, and the booking stays in the Register and journal. A Cancel matching no active booking changes nothing and returns an error. Matching more than one asks the Owner to be more specific. It is excluded from Overlap checks and the Morning Summary.

- **CAP-5**
  - **intent:** The Owner can change a phone booking's dates without losing the original.
  - **success:** The original is marked `changed` and kept, and a new active booking is created and linked to it. Both are visible in the Register with their Status. The journal records old and new values with a timestamp. The new dates are checked for Overlap, and a changed booking never overlaps its own predecessor.

- **CAP-6**
  - **intent:** The Owner's data stays safe from loss and consistent with every Command.
  - **success:** An automatic daily backup is kept, the 7 most recent retained, in a location other than the live data's volume. Documented restore steps work, tested. A Command that fails to process is reported to the Owner, never silently dropped. No Command physically removes a record.

- **CAP-7**
  - **intent:** The Owner can record after a stay whether a client was rude.
  - **success:** A Client's Rating starts at 5, a "not rude" report adds 1, a "rude" report subtracts 1, and it stays within 1-5. The Bot replies with the new Rating. A report for a phone number with no booking returns an error and creates no Client. Every change is journaled.

- **CAP-8**
  - **intent:** The Owner sees a returning client's Rating when recording a new booking.
  - **success:** The reply to a booking for a client with a Rating below 5 or any prior report includes the Rating. A first-time client shows none (or "new Client"). The Rating never blocks or changes a booking.

- **CAP-9**
  - **intent:** The Owner receives one Morning Summary of the next three days, each day.
  - **success:** At 08:00 Asia/Beirut the Bot sends arrivals and departures per day for the next 3 days by chalet with client name, plus any open Overlap, headed "Phone bookings only". Cancelled and changed bookings never appear. With nothing to report it still sends "No phone arrivals or departures in the next 3 days". A failed send is retried and logged. If the Bot starts before 12:00 with no summary yet for the day, it sends one marked late. A summary is queued once per date.

- **CAP-10**
  - **intent:** The Owner can look up every phone booking on a free Trello board.
  - **success:** One board named "LeRegister - Phone bookings only" lists every booking with chalet, client name and phone, dates, Status, Rating and last-change time. Cancelled and changed bookings stay visible and clearly marked, overlapping active bookings are flagged, and the board opens on Trello's free plan. A booking is never archived or deleted from it. The board is rebuildable from the database.

- **CAP-11**
  - **intent:** The Owner can write a booking in plain words and confirm what the Bot understood before anything is recorded.
  - **success:** A message matching no strict Command goes to a free LLM, which sees only that message and the Command schema. A valid Proposal is shown with Confirm and Cancel, and nothing is recorded until the Owner confirms from their own account. The Proposal is re-checked by the deterministic parser, a rejected one is never recorded, it expires after 10 minutes, and a second Confirm records nothing. If the LLM is down or rate-limited the Bot says so and shows the strict format, and strict Commands keep working. The provider (hosted free tier now, local model later) is switched by configuration.

## Constraints

- Stays may cross two months or a year end (for example 30 Dec to 2 Jan), using the date forms in `command-grammar.md`.
- Running cost is zero or near zero. The Bot uses Telegram's official Bot API and official libraries only, and runs on the Owner's own computer by long polling with no public address.
- Nothing is ever deleted, and storage enforces it. One SQLite database is the single record, and Trello is a one-way copy, never read back to decide anything.
- Message text is untrusted data. The parser is deterministic over a fixed grammar and never guesses a date, name or phone. A free-text LLM may only propose a Command, never act, and the Owner confirms every Proposal (CAP-11).
- Phone numbers must start with `+` and a country code and are keyed by E.164 form. Dates are ISO, a stay occupies nights from check-in up to but not including check-out, and "today" and 08:00 are in `Asia/Beirut`.
- Structure, data shapes and delivery rules (journal, outbox, overlap derivation, backups) are fixed by the architecture spine and its AD rules.

## Non-goals

- Predictions of any kind (phase 2).
- Blocking double bookings, or proposing a free chalet on conflict.
- Checking against Booking.com, Airbnb or website bookings.
- Payments, prices, or guest messaging.
- Multiple users, staff access, or WhatsApp.

## Success signal

Within four weeks of use the Owner logs a day's phone bookings in under 30 minutes instead of 2-3 hours, starts the day from the Morning Summary with no manual cross-check, and every overlap in a season is alerted within a minute of the Command that caused it.

## Assumptions

- The chalet count is a setting, default 40, with chalets numbered 1 to that count.
- A stay is capped at 60 nights by default, configurable, to catch a mistyped month.
- The daily backup keeps 7 copies, and the summary time is configurable (default 08:00).
- The PRD's user-journey scenes are illustrative.
- The hosted free LLM provider is chosen at build time. The Owner accepts that message text, which may contain a guest name or phone, leaves the machine for the MVP.

## Open Questions

- How long guest names and phone numbers are kept, and how they are protected (phase 3).
