import logging
from uuid import uuid4

from services.booking.errors import APIError
from services.booking.models import Booking
from services.database import connect


logger = logging.getLogger(__name__)


def create_booking(client, data):
    booking_id = uuid4()
    flight = client.get(data.flight_id)
    with connect() as connection:
        connection.execute("INSERT INTO pending_operations (booking_id, kind) VALUES (%s, 'CREATE')", (booking_id,))
    try:
        with connect() as connection:
            pending = connection.execute("SELECT * FROM pending_operations WHERE booking_id = %s FOR UPDATE", (booking_id,)).fetchone()
            if pending is None:
                raise APIError(503, "OPERATION_ABORTED", "Операция уже завершена восстановлением")
            client.reserve(data.flight_id, booking_id, data.seat_count)
            row = connection.execute(
                """INSERT INTO bookings
                   (id, user_id, flight_id, passenger_name, passenger_email, seat_count, total_price)
                   VALUES (%(id)s, %(user_id)s, %(flight_id)s, %(passenger_name)s,
                           %(passenger_email)s, %(seat_count)s, %(total_price)s)
                   RETURNING *""",
                {**data.model_dump(), "id": booking_id, "total_price": data.seat_count * flight.price},
            ).fetchone()
            result = Booking.model_validate(row)
            connection.execute("DELETE FROM pending_operations WHERE booking_id = %s", (booking_id,))
    except Exception:
        logger.exception("create_recovery_pending booking_id=%s", booking_id)
        raise
    return result


def get_booking(booking_id):
    with connect() as connection:
        row = connection.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,)).fetchone()
    if row is None:
        raise APIError(404, "BOOKING_NOT_FOUND", "Бронирование не найдено")
    return Booking.model_validate(row)


def list_bookings(user_id):
    with connect() as connection:
        rows = connection.execute("SELECT * FROM bookings WHERE user_id = %s ORDER BY created_at, id", (user_id,)).fetchall()
    return [Booking.model_validate(row) for row in rows]


def finish_cancel(connection, client, row):
    if row["status"] == "CONFIRMED":
        reservation = client.release(row["id"])
        if reservation.flight_id != row["flight_id"] or reservation.seat_count != row["seat_count"]:
            raise APIError(502, "FLIGHT_BAD_RESPONSE", "Данные резерва не совпадают с бронированием")
        row = connection.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = %s RETURNING *", (row["id"],)).fetchone()
    connection.execute("DELETE FROM pending_operations WHERE booking_id = %s", (row["id"],))
    return Booking.model_validate(row)


def cancel_booking(client, booking_id):
    with connect() as connection:
        row = connection.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,)).fetchone()
        if row is None:
            raise APIError(404, "BOOKING_NOT_FOUND", "Бронирование не найдено")
        if row["status"] != "CONFIRMED":
            raise APIError(409, "BOOKING_NOT_CANCELABLE", "Бронирование уже отменено")
        connection.execute("INSERT INTO pending_operations (booking_id, kind) VALUES (%s, 'CANCEL') ON CONFLICT DO NOTHING", (booking_id,))
    with connect() as connection:
        connection.execute("SELECT * FROM pending_operations WHERE booking_id = %s FOR UPDATE", (booking_id,)).fetchone()
        row = connection.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,)).fetchone()
        if row is None:
            raise APIError(404, "BOOKING_NOT_FOUND", "Бронирование не найдено")
        return finish_cancel(connection, client, row)
