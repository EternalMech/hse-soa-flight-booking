INSERT INTO airlines (code, name) VALUES ('SU', 'Аэрофлот');
INSERT INTO airports (code, name) VALUES ('SVO', 'Шереметьево'), ('LED', 'Пулково');
INSERT INTO flight_numbers (number, airline_code) VALUES ('SU1234', 'SU'), ('SU4321', 'SU');

INSERT INTO flights (
    id, flight_number, origin, destination, departure_time, arrival_time,
    total_seats, available_seats, price, status
) VALUES
(
    '11111111-1111-4111-8111-111111111111', 'SU1234', 'SVO', 'LED',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '1 day 10 hours') AT TIME ZONE 'UTC',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '1 day 12 hours') AT TIME ZONE 'UTC',
    3, 3, 12500, 'SCHEDULED'
),
(
    '22222222-2222-4222-8222-222222222222', 'SU1234', 'SVO', 'LED',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '2 days 10 hours') AT TIME ZONE 'UTC',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '2 days 12 hours') AT TIME ZONE 'UTC',
    1, 1, 15000, 'SCHEDULED'
),
(
    '33333333-3333-4333-8333-333333333333', 'SU4321', 'LED', 'SVO',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '1 day 15 hours') AT TIME ZONE 'UTC',
    (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + INTERVAL '1 day 17 hours') AT TIME ZONE 'UTC',
    2, 2, 10000, 'CANCELLED'
);
