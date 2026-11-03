import logging
import re
from datetime import date, datetime, time, timezone
from functools import wraps
from uuid import UUID

import grpc
import psycopg
from flight.v1 import flight_pb2 as pb
from flight.v1 import flight_pb2_grpc as rpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

from services.flight.cache import FlightCache

from services.database import connect


logger = logging.getLogger(__name__)
FLIGHT_SELECT = """
    SELECT f.*, a.code AS airline_code, a.name AS airline_name
    FROM flights f
    JOIN flight_numbers n ON n.number = f.flight_number
    JOIN airlines a ON a.code = n.airline_code
"""


class FlightError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def rpc_errors(method):
    @wraps(method)
    def wrapped(self, request, context):
        try:
            response = method(self, request, context)
            if method.__name__ in {"ReserveSeats", "ReleaseReservation", "AbortReservation", "UpdateFlight"}:
                self.cache.invalidate()
            return response
        except FlightError as error:
            context.abort(error.code, str(error))
        except (psycopg.OperationalError, psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            logger.exception("Flight database unavailable")
            context.abort(grpc.StatusCode.UNAVAILABLE, "База рейсов временно недоступна")
        except Exception:
            logger.exception("Unexpected Flight Service error")
            context.abort(grpc.StatusCode.INTERNAL, "Внутренняя ошибка Flight Service")
    return wrapped


def identifier(value):
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Некорректный UUID") from None


def timestamp(value):
    result = Timestamp()
    result.FromDatetime(value)
    return result


def flight_message(row):
    return pb.Flight(
        id=str(row["id"]), flight_number=row["flight_number"],
        airline=pb.Airline(code=row["airline_code"], name=row["airline_name"]),
        origin=row["origin"], destination=row["destination"],
        departure_time=timestamp(row["departure_time"]),
        arrival_time=timestamp(row["arrival_time"]),
        total_seats=row["total_seats"], available_seats=row["available_seats"],
        price=row["price"], status=pb.FlightStatus.Value("FLIGHT_STATUS_" + row["status"]),
    )


def reservation_message(row):
    return pb.SeatReservation(
        id=str(row["id"]), flight_id=str(row["flight_id"]),
        booking_id=str(row["booking_id"]), seat_count=row["seat_count"],
        status=pb.ReservationStatus.Value("RESERVATION_STATUS_" + row["status"]),
        created_at=timestamp(row["created_at"]), updated_at=timestamp(row["updated_at"]),
    )


def lock_booking(connection, booking_id):
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(booking_id),))


class FlightService(rpc.FlightServiceServicer):
    def __init__(self):
        self.cache = FlightCache()

    @rpc_errors
    def SearchFlights(self, request, context):
        if (
            not re.fullmatch(r"[A-Z]{3}", request.origin)
            or not re.fullmatch(r"[A-Z]{3}", request.destination)
            or request.origin == request.destination
        ):
            raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Укажите два разных IATA-кода аэропортов")
        query = FLIGHT_SELECT + " WHERE f.origin = %s AND f.destination = %s AND f.status = 'SCHEDULED'"
        parameters = [request.origin, request.destination]
        if request.HasField("date"):
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", request.date):
                    raise ValueError()
                day = date.fromisoformat(request.date)
            except ValueError:
                raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Дата должна быть существующей датой YYYY-MM-DD") from None
            start = datetime.combine(day, time.min, tzinfo=timezone.utc)
            query += " AND f.departure_time >= %s AND f.departure_time < %s + INTERVAL '1 day'"
            parameters.extend([start, start])
        query += " ORDER BY f.departure_time, f.id"
        def load(connection):
            rows = connection.execute(query, parameters).fetchall()
            return pb.SearchFlightsResponse(flights=[flight_message(row) for row in rows])
        suffix = f"search:{request.origin}:{request.destination}:{request.date if request.HasField('date') else 'all'}"
        return self.cache.read(suffix, pb.SearchFlightsResponse, load)

    @rpc_errors
    def GetFlight(self, request, context):
        flight_id = identifier(request.flight_id)
        def load(connection):
            row = connection.execute(FLIGHT_SELECT + " WHERE f.id = %s", (flight_id,)).fetchone()
            if row is None:
                raise FlightError(grpc.StatusCode.NOT_FOUND, "Рейс не найден")
            return pb.GetFlightResponse(flight=flight_message(row))
        return self.cache.read(f"flight:{flight_id}", pb.GetFlightResponse, load)

    @rpc_errors
    def ReserveSeats(self, request, context):
        flight_id = identifier(request.flight_id)
        booking_id = identifier(request.booking_id)
        if not 1 <= request.seat_count <= 1000:
            raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Количество мест должно быть от 1 до 1000")
        with connect() as connection:
            lock_booking(connection, booking_id)
            if connection.execute("SELECT 1 FROM reservation_cancellations WHERE booking_id = %s", (booking_id,)).fetchone():
                raise FlightError(grpc.StatusCode.FAILED_PRECONDITION, "Операция бронирования отменена")
            existing = connection.execute(
                "SELECT * FROM seat_reservations WHERE booking_id = %s", (booking_id,),
            ).fetchone()
            if existing is not None:
                if existing["flight_id"] != flight_id or existing["seat_count"] != request.seat_count:
                    raise FlightError(grpc.StatusCode.ALREADY_EXISTS, "booking_id использован с другими параметрами")
                if existing["status"] != "ACTIVE":
                    raise FlightError(grpc.StatusCode.FAILED_PRECONDITION, "Резервация уже завершена")
                return pb.ReserveSeatsResponse(reservation=reservation_message(existing))
            flight = connection.execute(
                "SELECT * FROM flights WHERE id = %s FOR UPDATE", (flight_id,),
            ).fetchone()
            if flight is None:
                raise FlightError(grpc.StatusCode.NOT_FOUND, "Рейс не найден")
            if flight["status"] != "SCHEDULED":
                raise FlightError(grpc.StatusCode.FAILED_PRECONDITION, "Рейс недоступен для резервирования")
            if flight["available_seats"] < request.seat_count:
                raise FlightError(grpc.StatusCode.RESOURCE_EXHAUSTED, "Недостаточно свободных мест")
            connection.execute(
                "UPDATE flights SET available_seats = available_seats - %s WHERE id = %s",
                (request.seat_count, flight_id),
            )
            row = connection.execute(
                """INSERT INTO seat_reservations (flight_id, booking_id, seat_count)
                   VALUES (%s, %s, %s) RETURNING *""",
                (flight_id, booking_id, request.seat_count),
            ).fetchone()
        return pb.ReserveSeatsResponse(reservation=reservation_message(row))

    @rpc_errors
    def ReleaseReservation(self, request, context):
        booking_id = identifier(request.booking_id)
        with connect() as connection:
            lock_booking(connection, booking_id)
            reservation = connection.execute(
                "SELECT * FROM seat_reservations WHERE booking_id = %s FOR UPDATE", (booking_id,),
            ).fetchone()
            if reservation is None:
                raise FlightError(grpc.StatusCode.NOT_FOUND, "Резервация не найдена")
            if reservation["status"] != "ACTIVE":
                return pb.ReleaseReservationResponse(reservation=reservation_message(reservation))
            connection.execute("SELECT id FROM flights WHERE id = %s FOR UPDATE", (reservation["flight_id"],))
            connection.execute(
                "UPDATE flights SET available_seats = available_seats + %s WHERE id = %s",
                (reservation["seat_count"], reservation["flight_id"]),
            )
            row = connection.execute(
                "UPDATE seat_reservations SET status = 'RELEASED' WHERE booking_id = %s RETURNING *",
                (booking_id,),
            ).fetchone()
        return pb.ReleaseReservationResponse(reservation=reservation_message(row))

    @rpc_errors
    def AbortReservation(self, request, context):
        booking_id = identifier(request.booking_id)
        with connect() as connection:
            lock_booking(connection, booking_id)
            connection.execute("INSERT INTO reservation_cancellations (booking_id) VALUES (%s) ON CONFLICT DO NOTHING", (booking_id,))
            reservation = connection.execute("SELECT * FROM seat_reservations WHERE booking_id = %s FOR UPDATE", (booking_id,)).fetchone()
            if reservation is not None and reservation["status"] == "ACTIVE":
                connection.execute("SELECT id FROM flights WHERE id = %s FOR UPDATE", (reservation["flight_id"],))
                connection.execute("UPDATE flights SET available_seats = available_seats + %s WHERE id = %s",
                                   (reservation["seat_count"], reservation["flight_id"]))
                connection.execute("UPDATE seat_reservations SET status = 'RELEASED' WHERE booking_id = %s", (booking_id,))
        return Empty()

    @rpc_errors
    def UpdateFlight(self, request, context):
        flight_id = identifier(request.flight_id)
        if not request.HasField("price") and not request.HasField("status"):
            raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Укажите price или status")
        if request.HasField("price") and not 1 <= request.price <= 9999999999:
            raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Некорректная целая цена")
        if request.HasField("status") and request.status not in {1, 2, 3, 4}:
            raise FlightError(grpc.StatusCode.INVALID_ARGUMENT, "Некорректный статус рейса")
        with connect() as connection:
            row = connection.execute("SELECT * FROM flights WHERE id = %s FOR UPDATE", (flight_id,)).fetchone()
            if row is None:
                raise FlightError(grpc.StatusCode.NOT_FOUND, "Рейс не найден")
            price = request.price if request.HasField("price") else row["price"]
            status = pb.FlightStatus.Name(request.status).removeprefix("FLIGHT_STATUS_") if request.HasField("status") else row["status"]
            connection.execute("UPDATE flights SET price = %s, status = %s WHERE id = %s", (price, status, flight_id))
            updated = connection.execute(FLIGHT_SELECT + " WHERE f.id = %s", (flight_id,)).fetchone()
        return pb.GetFlightResponse(flight=flight_message(updated))
