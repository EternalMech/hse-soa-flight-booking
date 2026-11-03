import math
import os
from datetime import timezone

import grpc
from flight.v1 import flight_pb2 as pb
from flight.v1 import flight_pb2_grpc as rpc

from services.booking.errors import APIError
from services.booking.resilience import CircuitOpen, ResilienceInterceptor
from services.booking.models import Flight, Reservation


STATUS_ERRORS = {
    grpc.StatusCode.INVALID_ARGUMENT: (400, "VALIDATION_ERROR"),
    grpc.StatusCode.RESOURCE_EXHAUSTED: (409, "INSUFFICIENT_SEATS"),
    grpc.StatusCode.FAILED_PRECONDITION: (409, "RESERVATION_NOT_ALLOWED"),
    grpc.StatusCode.ALREADY_EXISTS: (409, "RESERVATION_CONFLICT"),
    grpc.StatusCode.UNAUTHENTICATED: (502, "FLIGHT_AUTH_FAILED"),
    grpc.StatusCode.UNAVAILABLE: (503, "FLIGHT_UNAVAILABLE"),
    grpc.StatusCode.DEADLINE_EXCEEDED: (504, "FLIGHT_TIMEOUT"),
}


def flight_model(value):
    if not value.HasField("departure_time") or not value.HasField("arrival_time"):
        raise ValueError("Отсутствует время рейса")
    return Flight(
        id=value.id, flight_number=value.flight_number,
        airline={"code": value.airline.code, "name": value.airline.name},
        origin=value.origin, destination=value.destination,
        departure_time=value.departure_time.ToDatetime(tzinfo=timezone.utc),
        arrival_time=value.arrival_time.ToDatetime(tzinfo=timezone.utc),
        total_seats=value.total_seats, available_seats=value.available_seats,
        price=value.price, status=pb.FlightStatus.Name(value.status).removeprefix("FLIGHT_STATUS_"),
    )


def reservation_model(value):
    if not value.HasField("created_at") or not value.HasField("updated_at"):
        raise ValueError("Отсутствуют даты резервации")
    return Reservation(
        id=value.id, flight_id=value.flight_id, booking_id=value.booking_id,
        seat_count=value.seat_count,
        status=pb.ReservationStatus.Name(value.status).removeprefix("RESERVATION_STATUS_"),
        created_at=value.created_at.ToDatetime(tzinfo=timezone.utc),
        updated_at=value.updated_at.ToDatetime(tzinfo=timezone.utc),
    )


class FlightClient:
    def __init__(self):
        self.timeout = float(os.getenv("FLIGHT_RPC_TIMEOUT_SECONDS", "3"))
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("FLIGHT_RPC_TIMEOUT_SECONDS must be in (0, 30]")
        self.channel = grpc.insecure_channel(os.getenv("FLIGHT_GRPC_TARGET", "localhost:50051"), options=[("grpc.enable_retries", 0)])
        self.interceptor = ResilienceInterceptor()
        intercepted = grpc.intercept_channel(self.channel, self.interceptor)
        self.stub = rpc.FlightServiceStub(intercepted)

    def close(self):
        self.channel.close()

    def call(self, method, request, convert):
        try:
            response = getattr(self.stub, method)(request, timeout=self.timeout)
        except CircuitOpen:
            raise APIError(503, "CIRCUIT_OPEN", "Flight Service временно отключён Circuit Breaker") from None
        except grpc.RpcError as error:
            if error.code() == grpc.StatusCode.NOT_FOUND:
                status, code = (502, "FLIGHT_BAD_RESPONSE") if method == "ReleaseReservation" else (404, "FLIGHT_NOT_FOUND")
            else:
                status, code = STATUS_ERRORS.get(error.code(), (502, "FLIGHT_BAD_RESPONSE"))
            message = error.details() if status < 500 else "Не удалось выполнить запрос к Flight Service"
            raise APIError(status, code, message) from None
        try:
            return convert(response)
        except (ValueError, TypeError, OverflowError):
            raise APIError(502, "FLIGHT_BAD_RESPONSE", "Flight Service вернул некорректные данные") from None

    def search(self, origin, destination, date):
        request = pb.SearchFlightsRequest(origin=origin, destination=destination)
        if date is not None:
            request.date = date
        return self.call("SearchFlights", request, lambda response: [flight_model(item) for item in response.flights])

    def get(self, flight_id):
        result = self.call("GetFlight", pb.GetFlightRequest(flight_id=str(flight_id)), lambda response: flight_model(response.flight))
        if result.id != flight_id:
            raise APIError(502, "FLIGHT_BAD_RESPONSE", "Flight Service вернул другой рейс")
        return result

    def reserve(self, flight_id, booking_id, seat_count):
        result = self.call(
            "ReserveSeats", pb.ReserveSeatsRequest(flight_id=str(flight_id), booking_id=str(booking_id), seat_count=seat_count),
            lambda response: reservation_model(response.reservation),
        )
        if (result.flight_id, result.booking_id, result.seat_count, result.status) != (flight_id, booking_id, seat_count, "ACTIVE"):
            raise APIError(502, "FLIGHT_BAD_RESPONSE", "Flight Service вернул другой резерв")
        return result

    def release(self, booking_id):
        result = self.call(
            "ReleaseReservation", pb.ReleaseReservationRequest(booking_id=str(booking_id)),
            lambda response: reservation_model(response.reservation),
        )
        if result.booking_id != booking_id or result.status not in {"RELEASED", "EXPIRED"}:
            raise APIError(502, "FLIGHT_BAD_RESPONSE", "Flight Service не подтвердил освобождение резерва")
        return result

    def abort(self, booking_id):
        return self.call("AbortReservation", pb.ReleaseReservationRequest(booking_id=str(booking_id)), lambda response: None)
