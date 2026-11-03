FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS codegen

WORKDIR /build
COPY requirements-codegen.txt .
RUN python -m pip install --no-cache-dir -r requirements-codegen.txt
COPY proto ./proto
RUN mkdir -p generated && python -m grpc_tools.protoc \
    -I proto --python_out=generated --grpc_python_out=generated \
    proto/flight/v1/flight.proto

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/generated:/app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt && python -m pip check
COPY --from=codegen /build/generated ./generated
COPY services ./services
COPY openapi ./openapi
USER 10001:10001

FROM runtime AS flight
EXPOSE 50051
CMD ["python", "-m", "services.flight.server"]

FROM runtime AS booking
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "services.booking.main:app", "--host", "0.0.0.0", "--port", "8000"]
