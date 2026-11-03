CREATE TABLE pending_operations (
    booking_id UUID PRIMARY KEY,
    kind VARCHAR(6) NOT NULL CHECK (kind IN ('CREATE', 'CANCEL')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_pending_operations_age ON pending_operations(created_at);
