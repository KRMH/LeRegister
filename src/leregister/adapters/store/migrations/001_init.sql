-- Story 1.3: journal, outbox, processed_updates. schema_version is created by the runner.

CREATE TABLE journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'booking_recorded', 'booking_changed', 'booking_cancelled', 'overlap_detected',
        'rating_changed', 'command_rejected', 'summary_sent', 'backup_done', 'sync_failed',
        'bot_started', 'proposal_confirmed', 'proposal_discarded'
    )),
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    related_booking_id INTEGER,
    payload TEXT NOT NULL CHECK (json_valid(payload))
);

CREATE TRIGGER journal_no_update BEFORE UPDATE ON journal
BEGIN
    SELECT RAISE(ABORT, 'journal is append-only: UPDATE is not allowed');
END;

CREATE TRIGGER journal_no_delete BEFORE DELETE ON journal
BEGIN
    SELECT RAISE(ABORT, 'journal is append-only: DELETE is not allowed');
END;

CREATE TABLE processed_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL CHECK (destination IN ('telegram', 'register')),
    dedupe_key TEXT UNIQUE,
    chat_id INTEGER,
    kind TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(args)),
    journal_id INTEGER REFERENCES journal(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    done_at TEXT
);

CREATE INDEX outbox_pending ON outbox (destination, status, id);
