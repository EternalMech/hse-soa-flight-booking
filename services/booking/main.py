import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse

from services.booking import operations
from services.booking.errors import (
    APIError, api_error_handler, database_error_handler, http_error_handler,
    unexpected_error_handler, validation_error_handler,
)
from services.booking.flight_client import FlightClient
from services.booking.recovery import RecoveryWorker
from services.booking.models import Booking, BookingCreate, BookingList, Flight, FlightList
from services.database import connect


@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(level=logging.INFO)
    client = FlightClient()
    recovery = RecoveryWorker(client)
    recovery.start()
    app.state.flight_client = client
    try:
        yield
    finally:
        recovery.close()
        client.close()


app = FastAPI(
    title="Flight Booking", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None,
    exception_handlers={
        APIError: api_error_handler,
        RequestValidationError: validation_error_handler,
        HTTPException: http_error_handler,
        psycopg.OperationalError: database_error_handler,
        psycopg.errors.QueryCanceled: database_error_handler,
        psycopg.errors.LockNotAvailable: database_error_handler,
        Exception: unexpected_error_handler,
    },
)


@app.get("/health", include_in_schema=False)
def health():
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/openapi.yaml", include_in_schema=False)
def contract():
    return FileResponse(Path(__file__).resolve().parents[2] / "openapi/booking.yaml", media_type="application/yaml")


@app.get("/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.yaml", title="Flight Booking API")


@app.get("/flights", response_model=FlightList)
def search_flights(
    request: Request,
    origin: Annotated[str, Query(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)],
    destination: Annotated[str, Query(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)],
    date: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")] = None,
):
    return FlightList(items=request.app.state.flight_client.search(origin, destination, date))


@app.get("/flights/{id}", response_model=Flight)
def get_flight(id: UUID, request: Request):
    return request.app.state.flight_client.get(id)


@app.post("/bookings", response_model=Booking, status_code=201)
def create_booking(body: BookingCreate, request: Request):
    return operations.create_booking(request.app.state.flight_client, body)


@app.get("/bookings", response_model=BookingList)
def list_bookings(user_id: UUID):
    return BookingList(items=operations.list_bookings(user_id))


@app.get("/bookings/{id}", response_model=Booking)
def get_booking(id: UUID):
    return operations.get_booking(id)


@app.post("/bookings/{id}/cancel", response_model=Booking)
def cancel_booking(id: UUID, request: Request):
    return operations.cancel_booking(request.app.state.flight_client, id)
