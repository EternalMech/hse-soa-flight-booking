# Критерии ДЗ3

Booking принимает REST-запросы и вызывает Flight по gRPC. У сервисов отдельные PostgreSQL; Flight использует Redis. Цены — целые рубли, время — UTC.

| № | Критерий | Реализация |
| --- | --- | --- |
| 1 | gRPC-контракт | [flight.proto](../proto/flight/v1/flight.proto): четыре обязательных RPC, Timestamp, enum; дополнительно UpdateFlight и AbortReservation. [protoc](../Makefile#L6) генерирует сообщения и Stub/Servicer. [Коды ошибок](design.md#ошибки-grpc). |
| 2 | ER в 3NF | [ER-диаграммы и 3NF](design.md#er-и-3nf); [схема Flight](../migrations/flight/V1__initial.sql), [схема Booking](../migrations/booking/V1__initial.sql): PK, FK, UNIQUE, CHECK и статусы. |
| 3 | Две БД и сервисы | [Compose](../docker-compose.yml): две PostgreSQL, автоматические миграции Flyway. [REST](../services/booking/main.py#L70), [gRPC-сервер](../services/flight/server.py#L28), [OpenAPI](../openapi/booking.yaml). |
| 4 | Межсервисный флоу | [create_booking](../services/booking/operations.py#L12): GetFlight → ReserveSeats → CONFIRMED, снимок total_price. При отмене ReleaseReservation → CANCELLED. |
| 5 | Целостность | [Reserve/Release](../services/flight/api.py#L133): SQL-транзакции, FOR UPDATE, блокировка по booking_id. [Worker](../services/booking/recovery.py#L12) восстанавливает незавершённые операции по журналу. |
| 6 | Аутентификация | [Server interceptor](../services/flight/auth.py#L8) проверяет x-api-key для всех RPC. FLIGHT_API_KEY задаётся через окружение; неверный ключ — UNAUTHENTICATED. |
| 7 | Redis-кеш | [Cache-Aside](../services/flight/cache.py#L26) для рейса и поиска, TTL 300–600 секунд, hit/miss в логах. [Поколение кеша](../migrations/flight/V3__cache_and_abort.sql#L7) меняется при Update/Reserve/Release; старые ключи удаляются и не используются. |
| 8 | Retry | [Client interceptor](../services/booking/resilience.py#L77): максимум три попытки, паузы 100/200 мс, только UNAVAILABLE и DEADLINE_EXCEEDED. ReserveSeats идемпотентен по booking_id. |
| 9 | Redis Sentinel | [Compose](../docker-compose.yml#L126): master, replica, три Sentinel. [redis-py](../services/flight/cache.py#L18) находит текущий master через Sentinel. |
| 10 | Circuit Breaker | [Реализация](../services/booking/resilience.py#L19): CLOSED → OPEN после пяти ошибок за 60 секунд; через 10 секунд одна проба HALF_OPEN. Настройки из окружения, переходы в логах, OPEN возвращает HTTP 503. |

Запуск: `make run` или `docker compose up --build -d --wait`. [Dockerfile](../Dockerfile#L7) выполняет кодогенерацию при сборке; миграции применяются при старте. Настройки — [.env.example](../.env.example), пример запроса — [create-booking.json](../examples/create-booking.json).

Для пункта 5: локальные транзакции атомарны. Между БД используется компенсация; при сбое возможно временное расхождение, которое worker устраняет после восстановления доступности.
