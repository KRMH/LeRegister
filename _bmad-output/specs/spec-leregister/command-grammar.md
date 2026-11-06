# Command Grammar

Commands are short text messages from the Owner to the Bot, chosen to be typeable with one hand. Command words and months are case-insensitive.

| Command | Format | Example |
| --- | --- | --- |
| New booking | `New <chalet> <name> <phone> <dates>` | `New 2 Sam +96171123456 12-15 dec` or `New 2 Sam +96171123456 30 dec-2 jan` |
| Cancel | `Cancel <chalet> <start> <month>` | `Cancel 2 12 dec` |
| Change dates | `Change <chalet> <start> <month> <new dates>` | `Change 2 12 dec 14-17 dec` or `Change 2 30 dec 31 dec-3 jan` |
| Rating | `Rating <phone> +` (not rude) or `Rating <phone> -` (rude) | `Rating +96171123456 -` |

Rules:
- `<chalet>` is a number from 1 to the configured chalet count (default 40).
- `<dates>` has two forms. Same month: `<start>-<end> <month>` (`12-15 dec`). Two months: `<start> <month>-<end> <month>` (`30 dec-2 jan`). `<start>` is the check-in day and `<end>` the check-out day. The same-month form needs `<end>` after `<start>`, otherwise it is rejected.
- `<phone>` is the first token starting with `+`. `<name>` is every token between the chalet and the phone, so names may contain spaces.
- Months are accepted in French and English, abbreviated or in full.
- The check-in year is the next occurrence of the start date on or after today, taken from the clock in `Asia/Beirut`. In the two-month form the check-out is the first occurrence of the end date after check-in, so `30 dec-2 jan` crosses the year end.
- A stay longer than the configured maximum (default 60 nights) is rejected as a likely typo.
- Cancel and Change identify the booking by chalet and check-in date.
- Rejection reply: "Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec", naming the failed part when known.
- Edited messages are ignored, and the Bot asks for a Change Command instead.
