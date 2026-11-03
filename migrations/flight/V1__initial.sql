CREATE TYPE flight_status AS ENUM ('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED');
CREATE TYPE reservation_status AS ENUM ('ACTIVE', 'RELEASED', 'EXPIRED');

CREATE TABLE airlines (
    code VARCHAR(2) PRIMARY KEY CHECK (code ~ '^[A-Z0-9]{2}$'),
    name VARCHAR(100) NOT NULL CHECK (char_length(btrim(name)) > 0)
);

CREATE TABLE airports (
    code VARCHAR(3) PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'),
    name VARCHAR(200) NOT NULL CHECK (char_length(btrim(name)) > 0)
);

CREATE TABLE flight_numbers (
    number VARCHAR(6) PRIMARY KEY CHECK (number ~ '^[A-Z0-9]{2}[0-9]{1,4}$'),
    airline_code VARCHAR(2) NOT NULL REFERENCES airlines(code),
    CHECK (left(number, 2) = airline_code)
);

CREATE TABLE flights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_number VARCHAR(6) NOT NULL REFERENCES flight_numbers(number),
    origin VARCHAR(3) NOT NULL REFERENCES airports(code),
    destination VARCHAR(3) NOT NULL REFERENCES airports(code),
    departure_time TIMESTAMPTZ NOT NULL CHECK (isfinite(departure_time)),
    arrival_time TIMESTAMPTZ NOT NULL CHECK (isfinite(arrival_time)),
    total_seats INTEGER NOT NULL CHECK (total_seats BETWEEN 1 AND 1000),
    available_seats INTEGER NOT NULL CHECK (available_seats BETWEEN 0 AND total_seats),
    price BIGINT NOT NULL CHECK (price BETWEEN 1 AND 9999999999),
    status flight_status NOT NULL DEFAULT 'SCHEDULED',
    CHECK (origin <> destination),
    CHECK (arrival_time > departure_time)
);

CREATE UNIQUE INDEX uq_flights_number_departure_date
    ON flights (flight_number, ((departure_time AT TIME ZONE 'UTC')::date));

CREATE INDEX idx_flights_search
    ON flights (origin, destination, departure_time, id)
    WHERE status = 'SCHEDULED';

CREATE TABLE seat_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_id UUID NOT NULL REFERENCES flights(id),
    booking_id UUID NOT NULL UNIQUE,
    seat_count INTEGER NOT NULL CHECK (seat_count BETWEEN 1 AND 1000),
    status reservation_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_seat_reservations_flight ON seat_reservations(flight_id);

CREATE FUNCTION set_reservation_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER seat_reservations_updated_at
    BEFORE UPDATE ON seat_reservations
    FOR EACH ROW EXECUTE FUNCTION set_reservation_updated_at();
