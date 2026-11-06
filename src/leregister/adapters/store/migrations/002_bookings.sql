-- Story 1.4: clients and bookings. Bookings are never deleted and only status/superseded_by may change.

CREATE TABLE clients (
    phone TEXT PRIMARY KEY,                                   -- E.164
    name TEXT NOT NULL,                                       -- name at the first booking, then informational
    rating INTEGER NOT NULL DEFAULT 5 CHECK (rating BETWEEN 1 AND 5),
    created_at TEXT NOT NULL
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chalet INTEGER NOT NULL CHECK (chalet >= 1),
    client_name TEXT NOT NULL,                                -- as given for this booking
    client_phone TEXT NOT NULL REFERENCES clients(phone),
    check_in TEXT NOT NULL,                                   -- ISO date
    check_out TEXT NOT NULL,                                  -- ISO date, exclusive
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'changed', 'cancelled')),
    superseded_by INTEGER REFERENCES bookings(id),
    created_at TEXT NOT NULL,
    CHECK (check_in GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    CHECK (check_out GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    CHECK (check_out > check_in),
    CHECK (superseded_by IS NULL OR superseded_by <> id)
);

-- An identical active booking can exist only once.
CREATE UNIQUE INDEX bookings_one_active_per_stay
    ON bookings (chalet, client_phone, check_in, check_out) WHERE status = 'active';

CREATE TRIGGER bookings_no_delete BEFORE DELETE ON bookings
BEGIN
    SELECT RAISE(ABORT, 'bookings are never deleted');
END;

CREATE TRIGGER bookings_fixed_fields BEFORE UPDATE ON bookings
WHEN NEW.id IS NOT OLD.id
  OR NEW.chalet IS NOT OLD.chalet
  OR NEW.client_name IS NOT OLD.client_name
  OR NEW.client_phone IS NOT OLD.client_phone
  OR NEW.check_in IS NOT OLD.check_in
  OR NEW.check_out IS NOT OLD.check_out
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'bookings: only status and superseded_by may change');
END;

CREATE TRIGGER bookings_status_moves BEFORE UPDATE ON bookings
WHEN NEW.status IS NOT OLD.status
 AND NOT (OLD.status = 'active' AND NEW.status IN ('changed', 'cancelled'))
BEGIN
    SELECT RAISE(ABORT, 'bookings: status may only move active to changed or cancelled');
END;

ALTER TABLE outbox ADD COLUMN booking_id INTEGER REFERENCES bookings(id);

-- Story 1.3 queued a "not saved yet" preview reply (kind new_preview). That reply kind no longer exists, so
-- close any still-pending row instead of letting it fail forever.
UPDATE outbox SET status = 'done', done_at = created_at WHERE kind = 'new_preview' AND status = 'pending';
