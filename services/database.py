import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(
        row_factory=dict_row,
        connect_timeout=5,
        options="-c timezone=UTC -c statement_timeout=5000 -c lock_timeout=3000",
    )
