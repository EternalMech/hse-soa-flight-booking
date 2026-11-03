import logging
import signal
from concurrent import futures

import grpc
import psycopg
from flight.v1 import flight_pb2_grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from services.database import connect
from services.flight.api import FlightService
from services.flight.auth import ApiKeyInterceptor


class HealthService(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        if request.service not in {"", "flight.v1.FlightService"}:
            context.abort(grpc.StatusCode.NOT_FOUND, "Неизвестный сервис")
        try:
            with connect() as connection:
                connection.execute("SELECT 1")
            status = health_pb2.HealthCheckResponse.SERVING
        except psycopg.Error:
            status = health_pb2.HealthCheckResponse.NOT_SERVING
        return health_pb2.HealthCheckResponse(status=status)


def main():
    logging.basicConfig(level=logging.INFO)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16), interceptors=[ApiKeyInterceptor()])
    flight_pb2_grpc.add_FlightServiceServicer_to_server(FlightService(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthService(), server)
    if server.add_insecure_port("[::]:50051") == 0:
        raise RuntimeError("Cannot bind gRPC port 50051")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: server.stop(5))
    server.start()
    logging.info("Flight Service listening on :50051")
    server.wait_for_termination()


if __name__ == "__main__":
    main()
