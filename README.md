# Flight Booking

- **Booking Service** — клиентский REST API, бронирования и снимок стоимости.
- **Flight Service** — рейсы, атомарное резервирование мест и кеш.
- Межсервисные вызовы защищены API Key; клиент использует retry и Circuit Breaker.

## Запуск

```sh
make run
```

Swagger: http://127.0.0.1:8000/docs · Health: http://127.0.0.1:8000/health

```sh
make stop
```

Для локальной генерации Python-кода: `make generate`

## Документация

[ER-диаграммы и ошибки gRPC](docs/design.md) · [Критерии и ссылки на код](docs/criteria.md)

Настройки находятся в `.env.example`
