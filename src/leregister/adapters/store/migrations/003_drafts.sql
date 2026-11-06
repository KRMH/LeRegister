-- Story 1.9: a plain-words booking still being completed. One row per chat, mutable on purpose (a side table).
-- Never part of bookings or journal. The phone is kept here and is never sent to the model.

CREATE TABLE drafts (
    chat_id INTEGER PRIMARY KEY,
    chalet INTEGER CHECK (chalet IS NULL OR chalet >= 1),
    name TEXT,
    phone TEXT,
    check_in_day INTEGER CHECK (check_in_day IS NULL OR check_in_day BETWEEN 1 AND 31),
    check_in_month INTEGER CHECK (check_in_month IS NULL OR check_in_month BETWEEN 1 AND 12),
    check_out_day INTEGER CHECK (check_out_day IS NULL OR check_out_day BETWEEN 1 AND 31),
    check_out_month INTEGER CHECK (check_out_month IS NULL OR check_out_month BETWEEN 1 AND 12),
    questions_asked INTEGER NOT NULL DEFAULT 0 CHECK (questions_asked BETWEEN 0 AND 3),
    updated_at TEXT NOT NULL
);
