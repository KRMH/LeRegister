---
title: "Product Brief: LeRegister"
status: final
created: 2026-11-06
updated: 2026-11-06
---

# Product Brief: LeRegister

## Executive Summary

LeRegister is a small, free-to-run tool for the owner of 40 chalets in a ski resort. Bookings from Booking.com, Airbnb and the owner's website sync without trouble. Phone bookings do not, so they are entered by hand, late, and sometimes wrongly.

The owner sends each phone booking as a WhatsApp message. LeRegister records it, flags any overlap at once, keeps a simple reliability rating per client, and sends a morning WhatsApp summary of the next three days. A free table or Trello board is the place where the owner can check all phone bookings.

This is a real tool, built as an MVP. Phase 1 is deliberately narrow: phone bookings only, no predictions.

## The Problem

- **Data entry:** 2-3 hours per day.
- **Frequency:** every phone booking, and every morning.
- **Errors:** about 5 double bookings per season, each one an unhappy guest and a scramble to fix.

## The Solution

1. **Capture.** The owner sends a message such as "Chalet 2, Sam, 0612345678, 12 to 15 Dec".
2. **Record.** LeRegister saves it in the table or board.
3. **Detect.** It checks the dates against existing phone bookings for that chalet and alerts the owner immediately on overlap. It does not block: both bookings are kept, with the alert and a journal entry.
4. **Rate.** After a stay, the owner reports by WhatsApp whether the client was rude or not. That feeds a star rating per client. Clients are identified by phone number; the rating is on a 1-5 scale, starting at 5. "Rude" lowers it and "not rude" raises it.
5. **Summarise.** Every morning a WhatsApp message lists the next three days.

Every morning message and the table carry the mention **"Phone bookings only"**.

## Who This Serves

The owner, alone, for now. Success for them is a morning with no re-checking and no surprise overlaps. Staff access is a later question.

## Success Criteria

- Daily data-entry time falls from 2-3 hours to under 30 minutes.
- Double bookings from phone reservations fall from about 5 per season to none going undetected; any overlap is flagged within a minute.
- The owner stops cross-checking by hand each morning.
- Running cost stays at or near zero for the MVP.

## Scope

**In (phase 1):** WhatsApp intake, recording, overlap detection with alert and journal, client rating, the morning message, a free table or Trello board.

**Out:**
- Predictions (phase 2).
- Blocking double bookings.
- Conflicts with Booking.com, Airbnb or website bookings, accepted as a gap.
- Multiple users.
- Proposing a free chalet on conflict.

## Constraints, Risks and Open Questions

- **"Free" versus WhatsApp.** Automatic WhatsApp sending and receiving usually goes through the Business API or a paid provider. This is the largest risk to the MVP. Free is a hard constraint, and the solution must also be safe from prompt injection, because WhatsApp messages are untrusted input. The fallback if no free WhatsApp route exists is still **open**.
- **Rating purpose.** What does the owner do with the stars? They glance at them when a known client calls to book again. **Open.**
- **Message format.** Free-text messages will vary ("12 to 15 Dec", dates in French). The parser needs a tolerance rule and a "could not understand, please resend" reply. **Open.**

## Vision

If phase 1 holds, phase 2 adds predictions, and the same register could later cover all channels, so one view replaces the manual cross-check entirely.
