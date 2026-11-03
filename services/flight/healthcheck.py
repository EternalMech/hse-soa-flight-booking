import grpc
from services.config import api_key
from grpc_health.v1 import health_pb2, health_pb2_grpc


def main():
    with grpc.insecure_channel("127.0.0.1:50051") as channel:
        response = health_pb2_grpc.HealthStub(channel).Check(
            health_pb2.HealthCheckRequest(service="flight.v1.FlightService"), timeout=3, metadata=(("x-api-key", api_key()),),
        )
        raise SystemExit(response.status != health_pb2.HealthCheckResponse.SERVING)


if __name__ == "__main__":
    main()
