---
title: "PRD: LeRegister"
status: final
created: 2026-11-06
updated: 2026-11-06
---

# PRD: LeRegister
*Working title: confirm.*

## 0. Document Purpose

This PRD defines phase 1 of LeRegister for the Owner, the sole user and decision-maker, and for whoever builds it. It builds on the finalized product brief (`../../briefs/brief-LeRegister-2026-11-06/brief.md`) and does not repeat it. Capitalized terms are defined in the Glossary and used exactly. Features are grouped, with numbered FRs nested under them. Points still inferred are tagged `[ASSUMPTION]` inline and listed in §10. **One change from the brief:** the chat channel is now a Telegram bot, not WhatsApp, because free is a hard constraint (see §6 and memlog).

## 1. Vision

The Owner runs 40 Chalets. Online bookings sync on their own. Phone Bookings do not, so the Owner types them in by hand, 2-3 hours a day, and about 5 times a season one lands on top of another.

LeRegister lets the Owner send one short Telegram message per phone call. The Bot records it, flags any Overlap immediately, keeps a Rating per Client, and sends a Morning Summary of the next three days. The Bot never deletes anything, so the Register is both current and a safe record. It costs nothing to run. Phase 1 is deliberately narrow: Phone Bookings only, no predictions.

## 2. Target User

### 2.1 Jobs To Be Done
- When a booking comes in by phone, I want to log it in seconds with one hand, so I can get back to the guest or the task at hand.
- When two Phone Bookings clash, I want to know at once, so I can fix it before the guest arrives.
- When a known Client calls again, I want to see whether they were a problem before.
- Each morning, I want one message telling me who arrives and leaves, so I don't re-check by hand.
- I want to trust the record: nothing silently lost, everything traceable.

### 2.2 Non-Users (v1)
Staff, cleaners and guests. A single Owner only. Staff access is a later question.

### 2.3 Key User Journeys
`[ASSUMPTION: these scenes are illustrative. Replace them with your real mornings and calls.]`

- **UJ-1. The Owner logs a call.** The Owner finishes a call with a new Client while walking between Chalets. With one hand they type `New 2 Sam +96171123456 12-15 dec` in the Telegram bot chat. The Bot replies at once with what it understood: "Recorded: Chalet 2, Sam, 12-15 Dec". If the Client has a Rating, the reply shows it. **Edge case:** the Owner typed `New 2 Sam 12-15 dec` and forgot the phone number, so the Bot records nothing and replies with the correct format.
- **UJ-2. The Owner double-books by accident.** Another call arrives for Chalet 2, 14-17 Dec. The Owner logs it. The Bot records it and immediately alerts: "Overlap: Chalet 2, 14-15 Dec, with Sam 12-15 Dec." Both Phone Bookings stay `active`. The Owner phones one Client, then sends a Change Command to move the second Phone Booking.
- **UJ-3. The Owner's morning.** At 08:00 the Bot sends the Morning Summary: arrivals, departures and any open Overlap for the next three days, headed "Phone bookings only". The Owner stops cross-checking and starts the day.
- **UJ-4. After a Stay.** The Owner reports a rude Client with `Rating +96171123456 -`. The Bot replies with the new Rating. When that Client books again, the Owner sees the Rating in the confirmation.

## 3. Glossary

- **Owner:** the one authorized human user of LeRegister.
- **Chalet:** one of the rental units (40 at present), identified by a number from 1 to a configurable chalet count. `[ASSUMPTION: default 40]`
- **Phone Booking:** a reservation made by phone, entered via the Bot. Online-channel reservations are not Phone Bookings.
- **Booking Status:** `active`, `changed` or `cancelled`. A `changed` Phone Booking is the superseded earlier version. Its replacement is a new `active` Phone Booking linked to it.
- **Stay:** the check-in day through the check-out day. The check-out day is not a night occupied.
- **Overlap:** two `active` Phone Bookings of the same Chalet whose nights intersect. A check-out day equal to another Phone Booking's check-in day is not an Overlap.
- **Alert:** a Bot message to the Owner announcing an Overlap.
- **Journal:** the append-only history of every record, change, cancellation, Overlap and Rating event.
- **Client:** a guest identified by phone number. The name is informational.
- **Rating:** a Client's 1-5 star score.
- **Bot:** the Telegram bot through which the Owner interacts.
- **Register:** the free table or Trello board where the Owner can view all Phone Bookings.
- **Morning Summary:** the daily Bot message covering the next three days.
- **Command:** a short Owner message in a defined format that the Bot acts on.
- **Interpreter:** the component that proposes a Command from a free-text Owner message.
- **Proposal:** a Command suggested by the Interpreter and awaiting the Owner's confirmation.

## 4. Features

### 4.1 Capture and record
**Description:** The Owner sends a Command to the Bot. The Bot interprets it and records the Phone Booking. It always replies with what it recorded or why it did not. The Bot accepts messages only from the Owner. Realizes UJ-1.

**Command formats**, chosen to be short and typeable with one hand:
- New: `New <chalet> <name> <phone> <dates>` → `New 2 Sam +96171123456 12-15 dec` or `New 2 Sam +96171123456 30 dec-2 jan`
- Cancel: `Cancel <chalet> <start> <month>` → `Cancel 2 12 dec`
- Change dates: `Change <chalet> <start> <month> <new dates>` → `Change 2 12 dec 14-17 dec` or `Change 2 30 dec 31 dec-3 jan`
- Rating: `Rating <phone> +` (not rude) or `Rating <phone> -` (rude) → `Rating +96171123456 -`
- Command words and months are case-insensitive, so phone auto-capitalization does not matter. Dates take two forms: `12-15 dec` within one month, and `30 dec-2 jan` across two months. Months are accepted in French and English, abbreviated or in full. The year is the next occurrence of that date.

**Functional Requirements:**

#### FR-1: Record a Phone Booking
The Owner can send a new-booking Command, and the Bot records a Phone Booking with Chalet, Client name, Client phone, check-in and check-out dates, `active` Status and a timestamp. Realizes UJ-1.

**Consequences (testable):**
- The Bot replies within 5 seconds, echoing the interpreted Chalet, name, dates and the Client's Rating if one exists.
- The Phone Booking appears in the Register within 1 minute.
- Invalid values (Chalet outside 1 to the configured chalet count, a stay over the configured maximum of 60 nights, check-out not after check-in, phone number without `+` and country code, or invalid) are rejected and nothing is recorded.
- Sending an identical `active` Phone Booking a second time creates no duplicate. The Bot replies "already recorded".

#### FR-2: Reject what it cannot understand
When a message does not match a Command format, the Bot records nothing and replies "Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec". Realizes UJ-1 edge case.

**Consequences (testable):**
- No record is created or changed from an unparseable message.
- The reply states which part failed when it can tell (missing phone, unknown month).
- Parsing never guesses silently: any ambiguity gets a rejection, not a best guess.

#### FR-3: Accept the Owner only
The Bot acts only on messages from the Owner's Telegram account. Messages from any other account are ignored without a reply.

**Consequences (testable):**
- A Command from a non-Owner account changes no data and produces no response.
- The Owner's account is set in configuration. Changing it requires deployer action, not a chat message.

### 4.2 Overlap detection
**Description:** Every time a Phone Booking is recorded or changed, the Bot checks it against all `active` Phone Bookings of the same Chalet. It does not block. Both stay active. Realizes UJ-2.

#### FR-4: Detect and alert on Overlap
When a recorded or changed Phone Booking creates an Overlap, the Bot sends an Alert naming the Chalet, the dates and both Clients.

**Consequences (testable):**
- The Alert arrives within 1 minute of the Command.
- Back-to-back Stays (check-out day equals the next check-in day) produce no Alert.
- Only `active` Phone Bookings are compared. `cancelled` and `changed` ones never trigger an Alert.
- Both Phone Bookings remain `active` after the Alert.

#### FR-5: Journal the Overlap
Each Overlap detected is written to the Journal with both Phone Bookings and a timestamp.

**Consequences (testable):**
- A Journal entry exists for every Alert sent.
- The Overlap stays visible in the Register and in the Morning Summary until the Overlap no longer exists, that is, until one of the Phone Bookings is changed or cancelled.

**Out of Scope:** conflicts with Booking.com, Airbnb or website bookings, and proposing a free Chalet.

### 4.3 Changes and cancellations
**Description:** The Owner can cancel or change a Phone Booking by Command. The old version is flagged and kept. It is never deleted. Realizes UJ-2.

#### FR-6: Cancel a Phone Booking
The Owner can cancel a Phone Booking. Its Status becomes `cancelled`. It stays in the Register and the Journal.

**Consequences (testable):**
- No record is ever physically removed by any Command.
- The Bot confirms the cancellation, naming the Chalet and dates.
- A cancelled Phone Booking is excluded from Overlap checks and from the Morning Summary.
- A Cancel Command that matches no `active` Phone Booking changes nothing and returns an error. If it matches more than one, the Bot asks the Owner to be more specific.

#### FR-7: Change a Phone Booking's dates
The Owner can change a Phone Booking's dates. The original is marked `changed` and kept, and a new `active` Phone Booking is created, linked to it.

**Consequences (testable):**
- Both versions are visible in the Register, each with its Status.
- The change is checked for Overlap as in FR-4.
- The Journal records the old and new values with a timestamp.

#### FR-8: Keep the record safe and current
The system must keep the Register and Journal safe from loss and consistent with every Command received.

**Consequences (testable):**
- At least one automatic backup of all data per day, with the 7 most recent kept. `[ASSUMPTION: daily, 7 copies, free storage]`
- The Owner can restore from a backup, with documented steps.
- Each processed Command is reflected in the Register within 1 minute. A Command that fails to process is reported to the Owner and not silently dropped.

### 4.4 Client rating
**Description:** After a Stay, the Owner reports whether the Client was rude. Realizes UJ-4.

#### FR-9: Update a Rating
The Owner can send a Rating Command with a Client's phone number. A Client's Rating starts at 5. A "not rude" report raises it by 1 and a "rude" report lowers it by 1, limited to 1-5.

**Consequences (testable):**
- The Bot replies with the new Rating.
- The Rating cannot go below 1 or above 5.
- A Rating Command for a phone number with no Phone Booking returns an error and creates no Client.
- Every Rating change is recorded in the Journal.

#### FR-10: Show Rating when booking
When a Phone Booking is recorded for a Client who has a Rating below 5 or any prior report, the Bot includes the Rating in its reply. Realizes UJ-4.

**Consequences (testable):**
- A first-time Client's reply shows no Rating, or "new Client".
- The Rating never blocks or changes a Phone Booking.

### 4.5 Morning summary
**Description:** Each morning the Owner gets one message covering the next three days. Realizes UJ-3.

#### FR-11: Send the Morning Summary
Every day the Bot sends the Morning Summary at 08:00 local time. `[ASSUMPTION: 08:00, configurable]` It lists, per day for the next 3 days, arrivals and departures by Chalet with Client name, and any open Overlap.

**Consequences (testable):**
- The message is headed "Phone bookings only".
- `cancelled` and `changed` Phone Bookings never appear.
- If nothing is happening, the Bot still sends "No phone arrivals or departures in the next 3 days", so the Owner knows the Bot is alive. `[ASSUMPTION]`
- If the Bot fails to send it, a retry happens and the failure is logged.

### 4.6 The Register
**Description:** A free table or Trello board where the Owner can look up every Phone Booking, including cancelled and changed ones.

#### FR-12: Show all Phone Bookings
The Register lists every Phone Booking with Chalet, Client name and phone, dates, Status, Rating and time of last change. The title or header carries "Phone bookings only".

**Consequences (testable):**
- `cancelled` and `changed` Phone Bookings stay visible and are clearly marked.
- Overlapping `active` Phone Bookings are visibly flagged.
- It opens without installing anything paid.

### 4.7 Natural-language input
**Description:** The Owner may write a booking in plain words instead of the strict format. A free LLM proposes the matching Command, and the Owner confirms it before anything is recorded. Hosted free tier for the MVP, local model later.

#### FR-13: Propose a Command from free text
When a message does not match a strict Command format, the Bot sends the message text to the Interpreter. A valid Proposal is shown to the Owner with Confirm and Cancel buttons, and recorded only on Confirm.

**Consequences (testable):**
- The model receives only the Owner's message with the phone number replaced by a placeholder, plus the Command schema and, on a follow-up, the name, chalet and dates already understood from the Owner's own earlier message. It never receives a phone number, stored bookings or Client data.
- When a booking is incomplete, the Bot keeps a short-lived draft (10 minutes, at most 3 questions) and asks for the first missing part, in the order chalet, name, dates, phone. Relative dates such as "next friday" count as missing and are never guessed. The next message fills or corrects the draft; a different guest name or a complete booking replaces it.
- `stop`, `forget it`, `never mind` or a strict `New` command drops a waiting draft.
- A Proposal is rendered as a strict Command and re-checked by the deterministic parser. A Proposal the parser rejects is never recorded.
- Nothing is recorded before Confirm. Confirm runs the same use case as a typed Command. A second Confirm records nothing.
- A Proposal expires after 10 minutes (configurable). Only the Owner's account can Confirm or Cancel.
- Instructions inside a message cannot make the model act: its output is only a schema-checked Proposal.
- If the LLM is down or rate-limited, the Bot says so and shows the strict format. Strict Commands keep working, with no retry loop.
- Provider is switchable by configuration without changing business rules.

## 5. Non-Goals (Explicit)
- LeRegister does not predict anything in phase 1.
- It does not block double bookings.
- It does not check against Booking.com, Airbnb or website bookings, and does not replace a channel manager.
- It does not suggest or assign a free Chalet.
- It does not handle payments, prices, or guest messaging.
- It has no multi-user access.

## 6. Cross-Cutting Requirements and Constraints

- **Cost:** running cost is zero or near zero. The Bot uses Telegram's official Bot API with official libraries only. Unofficial WhatsApp libraries are excluded because they break WhatsApp's terms. WhatsApp itself is out of v1 because its free tier does not reliably cover a daily proactive summary (see `[NOTE FOR PM]` below). LLM use must also be free: a hosted free tier for the MVP, a local model later.
- **Untrusted input (prompt-injection safety):** all message text is data, never instructions. The Bot accepts only the Owner's account (FR-3), parses Commands against a fixed grammar, and does not forward message text to any tool that can take action. The strict Command parser is rule-based and is the only authority on validity. An optional LLM Interpreter (§4.7) may propose a Command from free text. Its output is validated against a fixed schema and shown to the Owner for confirmation, and it has no ability to act.
- **Reliability:** the Bot should be available during the Owner's working day. A down Bot must be noticed. If no Morning Summary arrives, that tells the Owner.
- **Data protection:** will be handled in phase 3. Guest names and phone numbers are personal data, and the retention period is open (§9). The hosted LLM receives the Owner's own message text with any phone number removed, and on a follow-up the guest name, chalet and dates already given; the phone number is kept on the Owner's computer. The Owner accepts this for the MVP.
- **Never-delete rule:** applies to every user-facing path (FR-6, FR-7, FR-8). Only an explicit, manual admin action outside the Bot can remove data.

`[NOTE FOR PM]` The Telegram decision came from research (see memlog). If you later want WhatsApp, the official Cloud API works with a dedicated number and a daily "wake-up" message from you. It is a separate decision.

## 7. MVP Scope

### 7.1 In Scope
Telegram intake of Commands, recording, Overlap Alert and Journal, cancel and change, Client Rating, Morning Summary, the Register, and backups. Free-text input through a hosted free LLM, always confirmed by the Owner (§4.7).

### 7.2 Out of Scope for MVP
Predictions (phase 2). Blocking. Cross-channel conflicts. Free-Chalet suggestions. Staff access. WhatsApp.

## 8. Success Metrics

**Primary**
- **SM-1:** Daily data-entry time falls from 2-3 hours to under 30 minutes, measured by the Owner's own estimate after 4 weeks. Validates FR-1, FR-6, FR-7.
- **SM-2:** No Overlap goes undetected, and every Alert arrives within 1 minute, checked against the Journal at season's end. Validates FR-4, FR-5.
- **SM-3:** The Owner no longer cross-checks by hand each morning. Validates FR-11, FR-12.

**Secondary**
- **SM-4:** Running cost stays at or near zero. Validates §6 Cost.
- **SM-5:** At least 95% of the Owner's Commands are understood on the first try, counted from the Journal. Validates FR-1, FR-2.

**Counter-metrics (do not optimize)**
- **SM-C1:** Number of Commands rejected. Do not drive it down by making the parser guess. A wrong guess is worse than a rejection. Counterbalances SM-5.
- **SM-C2:** Number of Overlap Alerts. Do not suppress Alerts to look clean. Counterbalances SM-2.

## 9. Open Questions
1. **Hosting:** where does the Bot run (an always-on computer, or a free cloud service)? This is not yet decided.
2. **Register tool:** a table (which one?) or Trello? Which do you already use?
3. **Rating use:** the Owner glances at it when a Client rebooks. Is the displayed Rating enough, or should there also be a warning level?
4. **Data retention period** for guest data.
5. **Phone format:** resolved. Every number must start with `+` and the country code. Numbers without it are rejected.
6. **LLM provider:** decided: Groq's hosted free tier. Its documentation says it does not retain inference data by default and offers Zero Data Retention, which the Owner switches on. Its documentation page does not state whether data is used for training, so that remains unconfirmed.

## 10. Assumptions Index
*The Owner reviewed the draft and kept the other inferred points (Command formats, ±1 Rating, duplicate handling, Cancel matching, empty-day summary), so they are no longer tagged.*
- §2.3: scenes are illustrative.
- §3: chalet count configurable, default 40.
- §4.1: maximum stay 60 nights, configurable.
- FR-8: daily backup, 7 copies.
- FR-11: Morning Summary at 08:00, configurable.
- §6: the strict parser is rule-based. The LLM only proposes and the Owner confirms (§4.7).
