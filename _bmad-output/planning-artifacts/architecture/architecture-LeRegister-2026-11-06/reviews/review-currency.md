# Currency review - ARCHITECTURE-SPINE.md (LeRegister), 2026-11-06

Verdict: PASS with minor corrections. Every pinned version matches the registry today, and no named technology is obsolete. A few claims rest on unconfirmed or slightly overstated behaviour (below).

## 1. Stack versions (PyPI JSON, checked 2026-11-06)
| Item | Spine | Actual | Status |
| --- | --- | --- | --- |
| python-telegram-bot | 22.8 | 22.8 (2026-06-12), requires Python >=3.10 | Confirmed latest |
| APScheduler | 3.11.3 | 3.11.3 latest stable; only 4.0.0a* alphas exist | Confirmed. PTB `job-queue` extra pins `apscheduler>=3.10.4,<3.12.0`, so 3.x is forced |
| phonenumbers | 9.0.42 | 9.0.42 (2026-10-27) | Confirmed |
| httpx | >=0.27,<0.29 | latest 0.28.1; PTB 22.8 requires `httpx>=0.27,<0.29` | Confirmed. Range is just PTB's own constraint, so it is redundant (safe) |
| uv | 0.13.7 | `uv --version` locally 0.13.7 (2026-11-03) and PyPI latest | Confirmed (very fresh; pre-1.0 so it moves quickly) |
| Python | 3.11.9 | local `python --version` 3.11.9 | Confirmed installed. 3.11.9 is a security-only-era patch, not the newest 3.11.x; fine for PTB |
| SQLite | 3.45.1 | local `sqlite3.sqlite_version` 3.45.1 | Confirmed for this machine only. It is whatever the Python build bundles, so it is not a fixed pin and will differ on another install or Python upgrade |

## 2. Trello
- Rate limits (Atlassian developer docs, fetched): 300 requests/10 s per API key, 100 per 10 s per token, HTTP 429 on excess, with rate-limit headers. A single-owner bot is far below this. AD-11 backoff is appropriate; spine does not mention honouring 429 headers (minor).
- Cards API (official docs, fetched): `POST /cards` (idList required), `PUT /cards/{id}` with `idList` moves a card, `DELETE /cards/{id}` exists. No idempotency key is documented, so the spine's approach (store the Trello card id in SQLite, booking id in the description) is the right design. Gap: a crash between Trello create and storing the card id can create a duplicate; the spine should say sync looks up by booking id in the description before creating.
- Free plan: UNCONFIRMED from primary source. Only third-party 2026 articles (dupple, activepieces, etc.) were reachable; they agree on 10 open boards per Workspace, 10 collaborators, unlimited cards, 250 Workspace command runs/month. The spine needs only 1 board and 1 user, so it fits, but "current" in the Stack row is an assertion. Recommend checking trello.com/pricing and recording the date.
- Board/list names in AD-11 contain " - " and four lists; nothing platform-limiting found. Free plan allows API access with key+token (not re-verified on the Atlassian page; unconfirmed).
- AD-3 "never archived or deleted": archiving is a real Trello state; claim is consistent with the API, but Trello users can archive manually and the one-way projection would not notice. Low risk.

## 3. python-telegram-bot / Telegram
- Telegram Bot API (official, fetched): unreceived updates are kept at most 24 hours. AD-8 says Commands sent during downtime are "applied in order on restart" without a limit. This is OVERSTATED: downtime over 24 h silently loses bookings. Add the 24 h bound and the PTB behaviour on restart.
- Offset semantics (official): getUpdates with offset = last update_id+1 confirms earlier updates; PTB handles this. update_id is positive, normally sequential, but randomised after a week of no updates, so AD-4's "store update_id, ignore a repeat" is valid as an equality check but must not assume monotonic ordering (do not use "greater than last seen").
- Long polling is the normal run_polling mode; getUpdates does not work while a webhook is set (a leftover webhook would break startup; minor note).
- "Handled strictly one at a time": from my knowledge, PTB's default `concurrent_updates` is off (sequential), and the docs page confirms 0 means not concurrent. The doc page's run_polling details (drop_pending_updates default, stop_signals) were truncated and NOT confirmed; I believe `drop_pending_updates` defaults to False, which the spine relies on. Confirm in the first story.
- JobQueue: PTB's JobQueue wraps APScheduler 3.x AsyncIOScheduler; daily jobs use `run_daily` with a tz-aware time. Not fetched this session; the spine's design (catch-up on startup, journal event) is appropriately defensive. Note APScheduler/JobQueue misfire handling is unverified, and the spine correctly does not depend on it. The `Europe/Paris` timezone needs `tzdata` on Windows (no system IANA db) - not listed in Stack. This is a likely real-world failure.

## 4. SQLite
- Backup API (Python docs, fetched): `Connection.backup(target, *, pages=-1, progress=None, name='main', sleep=0.250)`, available since 3.7, works with concurrent access. Matches AD-10. Caveat: if the source is modified by a different connection mid-backup the copy restarts; with `pages=-1` it is a single step, so fine at this size.
- Triggers (SQLite docs, fetched): `RAISE(ABORT, ...)` works in BEFORE triggers; `UPDATE OF col` fires only if col is in the SET clause, and a misspelled column name is silently accepted and never fires. The spine says a booking may change only `status` and `superseded_by`; implement as a BEFORE UPDATE trigger comparing OLD/NEW on all other columns (not `UPDATE OF`), and add a test that fires each trigger.
- NOT confirmed: whether `INSERT OR REPLACE` / `REPLACE` conflict handling deletes rows without firing DELETE triggers (SQLite fires them only when `recursive_triggers` is on). This is a bypass for AD-3 "DELETE aborts". Forbid REPLACE or set the pragma; also `DROP TABLE` and `sqlite3` CLI bypass triggers (spine already says manual removal is outside the app).
- `RAISE` message-as-expression needs 3.47; spine uses 3.45.1, so use string literals.

## 5. Other
- `phonenumbers` still maintained (released 2026-10-27); fits E.164 normalisation.
- Stack row "Trello ... current" is not a version; acceptable but unverifiable.

## Unconfirmed items to resolve before build
1. Trello free-plan limits from the primary pricing page.
2. PTB `run_polling` defaults (drop_pending_updates, concurrent_updates) and JobQueue timezone/misfire behaviour from the PTB docs.
3. REPLACE and trigger bypass of AD-3 in SQLite docs.
4. Add `tzdata` dependency for Windows and the 24 h Telegram retention limit in AD-8.
