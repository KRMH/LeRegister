# Glossary

Terms are used exactly across the spec, stories and code.

- **Owner:** the one authorized human user.
- **Chalet:** one of the rental units, numbered 1 to the configured chalet count (default 40).
- **Phone Booking:** a reservation made by phone and entered through the Bot. Online-channel reservations are not Phone Bookings.
- **Booking Status:** `active`, `changed` or `cancelled`. A `changed` Phone Booking is the superseded earlier version, and its replacement is a new `active` one linked to it.
- **Stay:** the check-in day through the check-out day. The check-out day is not an occupied night.
- **Overlap:** two `active` Phone Bookings of the same Chalet whose nights intersect. A check-out day equal to another's check-in day is not an Overlap.
- **Alert:** a Bot message announcing an Overlap.
- **Journal:** the append-only history of every record, change, cancellation, Overlap, Rating event and rejected Command.
- **Client:** a guest identified by E.164 phone number. The name is informational.
- **Rating:** a Client's 1-5 score, starting at 5.
- **Bot:** the Telegram bot the Owner talks to.
- **Register:** the free Trello board showing all Phone Bookings.
- **Morning Summary:** the daily Bot message covering the next three days.
- **Command:** a short Owner message in a defined format (see `command-grammar.md`).
