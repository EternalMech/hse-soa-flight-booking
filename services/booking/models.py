from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


SeatCount = Annotated[StrictInt, Field(ge=1, le=1000)]
AirportCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)]
FlightStatus = Literal["SCHEDULED", "DEPARTED", "CANCELLED", "COMPLETED"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Airline(Model):
    code: Annotated[str, Field(pattern=r"^[A-Z0-9]{2}$")]
    name: Annotated[str, Field(min_length=1, max_length=100)]


class Flight(Model):
    id: UUID
    flight_number: Annotated[str, Field(pattern=r"^[A-Z0-9]{2}[0-9]{1,4}$")]
    airline: Airline
    origin: AirportCode
    destination: AirportCode
    departure_time: datetime
    arrival_time: datetime
    total_seats: SeatCount
    available_seats: Annotated[StrictInt, Field(ge=0, le=1000)]
    price: Annotated[StrictInt, Field(ge=1, le=9999999999)]
    status: FlightStatus

    @model_validator(mode="after")
    def check_consistency(self):
        if self.origin == self.destination or self.available_seats > self.total_seats:
            raise ValueError("Некорректные данные рейса")
        if self.arrival_time <= self.departure_time:
            raise ValueError("Прилёт должен быть позже вылета")
        return self


class FlightList(Model):
    items: list[Flight]


class BookingCreate(Model):
    user_id: UUID
    flight_id: UUID
    passenger_name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    passenger_email: Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    seat_count: SeatCount


class Booking(BookingCreate):
    id: UUID
    total_price: Annotated[StrictInt, Field(ge=1, le=9999999999000)]
    status: Literal["CONFIRMED", "CANCELLED"]
    created_at: datetime
    updated_at: datetime


class BookingList(Model):
    items: list[Booking]


class Reservation(Model):
    id: UUID
    flight_id: UUID
    booking_id: UUID
    seat_count: SeatCount
    status: Literal["ACTIVE", "RELEASED", "EXPIRED"]
    created_at: datetime
    updated_at: datetime
