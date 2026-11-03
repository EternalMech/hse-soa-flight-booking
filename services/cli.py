import argparse
import os

import grpc
from flight.v1 import flight_pb2 as pb
from flight.v1 import flight_pb2_grpc as rpc
from google.protobuf.json_format import MessageToJson

from services.config import api_key


def main():
    parser = argparse.ArgumentParser(description="Flight Service gRPC client")
    parser.add_argument("--without-key", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("get").add_argument("flight_id")
    search = commands.add_parser("search")
    search.add_argument("origin")
    search.add_argument("destination")
    search.add_argument("--date")
    update = commands.add_parser("price")
    update.add_argument("flight_id")
    update.add_argument("price", type=int)
    reserve = commands.add_parser("reserve")
    reserve.add_argument("flight_id")
    reserve.add_argument("booking_id")
    reserve.add_argument("seat_count", type=int)
    for name in ("release", "abort"):
        commands.add_parser(name).add_argument("booking_id")
    args = parser.parse_args()
    if args.command == "get":
        method, request = "GetFlight", pb.GetFlightRequest(flight_id=args.flight_id)
    elif args.command == "search":
        request = pb.SearchFlightsRequest(origin=args.origin, destination=args.destination)
        if args.date is not None:
            request.date = args.date
        method = "SearchFlights"
    elif args.command == "price":
        method, request = "UpdateFlight", pb.UpdateFlightRequest(flight_id=args.flight_id, price=args.price)
    elif args.command == "reserve":
        method, request = "ReserveSeats", pb.ReserveSeatsRequest(flight_id=args.flight_id, booking_id=args.booking_id, seat_count=args.seat_count)
    else:
        method = "ReleaseReservation" if args.command == "release" else "AbortReservation"
        request = pb.ReleaseReservationRequest(booking_id=args.booking_id)
    metadata = () if args.without_key else (("x-api-key", api_key()),)
    with grpc.insecure_channel(os.getenv("FLIGHT_GRPC_TARGET", "localhost:50051")) as channel:
        try:
            result = getattr(rpc.FlightServiceStub(channel), method)(request, metadata=metadata, timeout=5)
        except grpc.RpcError as error:
            parser.exit(1, f"{error.code().name}: {error.details()}\n")
        print(MessageToJson(result, preserving_proto_field_name=True))


if __name__ == "__main__":
    main()
