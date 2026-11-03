# Схема данных и ошибки gRPC

## ER и 3NF

<details>
<summary>Диаграммы двух БД</summary>

**Flight PostgreSQL**

```mermaid
erDiagram
    airlines ||--o{ flight_numbers : operates
    flight_numbers ||--o{ flights : schedules
    airports ||--o{ flights : origin
    airports ||--o{ flights : destination
    flights ||--o{ seat_reservations : has

    airlines {
        varchar code PK
        varchar name
    }
    airports {
        varchar code PK
        varchar name
    }
    flight_numbers {
        varchar number PK
        varchar airline_code FK
    }
    flights {
        uuid id PK
        varchar flight_number FK
        varchar origin FK
        varchar destination FK
        timestamptz departure_time
        timestamptz arrival_time
        int total_seats
        int available_seats
        bigint price
        flight_status status
    }
    cache_state {
        boolean id PK
        bigint revision
    }
    reservation_cancellations {
        uuid booking_id PK
        timestamptz created_at
    }
    seat_reservations {
        uuid id PK
        uuid flight_id FK
        uuid booking_id UK
        int seat_count
        reservation_status status
        timestamptz created_at
        timestamptz updated_at
    }
```

**Booking PostgreSQL**

```mermaid
erDiagram
    pending_operations {
        uuid booking_id PK
        varchar kind
        timestamptz created_at
    }
    bookings {
        uuid id PK
        uuid user_id
        uuid flight_id
        varchar passenger_name
        varchar passenger_email
        int seat_count
        bigint total_price
        booking_status status
        timestamptz created_at
        timestamptz updated_at
    }
```

</details>

Названия авиакомпаний и аэропортов вынесены в справочники; неключевые поля зависят от ключа своей таблицы. Стоимость и данные пассажира в Booking — исторический снимок. Ссылки между БД логические, без SQL FK; одному успешному Booking соответствует один резерв с UNIQUE(booking_id).

CHECK гарантирует положительные цену/вместимость и `0 ≤ available_seats ≤ total_seats`. Номер рейса вместе с датой вылета по UTC уникален. Согласованность остатка и резервов поддерживается транзакцией.

## Ошибки gRPC

| Код | Причина |
| --- | --- |
| INVALID_ARGUMENT | Неверные параметры |
| NOT_FOUND | Рейс или резерв не найден |
| RESOURCE_EXHAUSTED | Недостаточно мест |
| FAILED_PRECONDITION | Рейс недоступен для резерва, резерв завершён или создание отменено |
| ALREADY_EXISTS | booking_id повторён с другими параметрами |
| UNAUTHENTICATED | Нет корректного API Key |
| UNAVAILABLE / DEADLINE_EXCEEDED | Недоступность зависимости / истёк deadline |
| INTERNAL | Неожиданная ошибка Flight |

[Отображение в HTTP](../services/booking/flight_client.py#L14): 400/404/409 для ошибок запроса, 502 для неверного ответа или сервисного ключа, 503/504 для недоступности/таймаута.
