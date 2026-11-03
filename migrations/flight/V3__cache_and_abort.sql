CREATE TABLE cache_state (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0)
);
INSERT INTO cache_state (id) VALUES (TRUE);

CREATE FUNCTION advance_cache_revision() RETURNS TRIGGER AS $$
BEGIN
    UPDATE cache_state SET revision = revision + 1 WHERE id = TRUE;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flights_cache_revision
    AFTER INSERT OR UPDATE OR DELETE ON flights
    FOR EACH STATEMENT EXECUTE FUNCTION advance_cache_revision();

CREATE TABLE reservation_cancellations (
    booking_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
