import logging
import threading

from services.booking.operations import finish_cancel
from services.config import number
from services.database import connect


logger = logging.getLogger(__name__)


def recover_one(client, grace):
    with connect() as connection:
        operation = connection.execute(
            """SELECT * FROM pending_operations
               WHERE created_at <= clock_timestamp() - %s * INTERVAL '1 second'
               ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""", (grace,),
        ).fetchone()
        if operation is None:
            return
        booking_id = operation["booking_id"]
        booking = connection.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,)).fetchone()
        if operation["kind"] == "CREATE":
            if booking is None:
                client.abort(booking_id)
            connection.execute("DELETE FROM pending_operations WHERE booking_id = %s", (booking_id,))
        elif booking is not None:
            finish_cancel(connection, client, booking)
        else:
            connection.execute("DELETE FROM pending_operations WHERE booking_id = %s", (booking_id,))
    logger.info("recovery_complete kind=%s booking_id=%s", operation["kind"], booking_id)


class RecoveryWorker:
    def __init__(self, client):
        self.client = client
        self.interval = number("RECOVERY_INTERVAL_SECONDS", 2, 0.1, 60)
        self.grace = number("RECOVERY_GRACE_SECONDS", 5, 0, 300)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name="booking-recovery", daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while not self.stop.wait(self.interval):
            try:
                recover_one(self.client, self.grace)
            except Exception as error:
                logger.warning("recovery_deferred type=%s", type(error).__name__)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3 * self.client.timeout + 15)
