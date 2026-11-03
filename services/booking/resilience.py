import logging
import threading
import time
from collections import deque, namedtuple

import grpc

from services.config import api_key, number


logger = logging.getLogger(__name__)
TRANSIENT = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self):
        self.threshold = number("CIRCUIT_FAILURE_THRESHOLD", 5, 1, 100, integer=True)
        self.reset_after = number("CIRCUIT_RESET_SECONDS", 10, 1, 300)
        self.window = number("CIRCUIT_FAILURE_WINDOW_SECONDS", 60, 1, 600)
        self.lock = threading.Lock()
        self.state = "CLOSED"
        self.generation = 0
        self.opened_at = 0
        self.failures = deque()

    def transition(self, target):
        logger.info("circuit_transition from=%s to=%s", self.state, target)
        self.state = target
        self.generation += 1

    def enter(self):
        with self.lock:
            if self.state == "OPEN":
                if time.monotonic() - self.opened_at < self.reset_after:
                    raise CircuitOpen()
                self.transition("HALF_OPEN")
                return self.generation, True
            if self.state == "HALF_OPEN":
                raise CircuitOpen()
            return self.generation, False

    def finish(self, permit, failed):
        generation, probe = permit
        with self.lock:
            if generation != self.generation:
                return
            now = time.monotonic()
            if probe:
                self.failures.clear()
                if failed:
                    self.opened_at = now
                    self.transition("OPEN")
                else:
                    self.transition("CLOSED")
            elif failed:
                while self.failures and now - self.failures[0] > self.window:
                    self.failures.popleft()
                self.failures.append(now)
                if len(self.failures) >= self.threshold:
                    self.opened_at = now
                    self.transition("OPEN")


class CallDetails(namedtuple("CallDetails", "method timeout metadata credentials wait_for_ready compression"), grpc.ClientCallDetails):
    pass


class ResilienceInterceptor(grpc.UnaryUnaryClientInterceptor):
    def __init__(self):
        self.key = api_key()
        self.breaker = CircuitBreaker()

    def intercept_unary_unary(self, continuation, details, request):
        permit = self.breaker.enter()
        metadata = [(key, value) for key, value in (details.metadata or ()) if key != "x-api-key"]
        metadata.append(("x-api-key", self.key))
        call = CallDetails(details.method, details.timeout, metadata, details.credentials,
                           details.wait_for_ready, getattr(details, "compression", None))
        attempts = 1 if permit[1] else 3
        for attempt in range(1, attempts + 1):
            try:
                response = continuation(call, request)
                response.result()
            except grpc.RpcError as error:
                failed = error.code() in TRANSIENT
                if failed and attempt < attempts:
                    delay = 0.1 * 2 ** (attempt - 1)
                    logger.info("grpc_retry method=%s attempt=%s next_delay_ms=%s code=%s",
                                details.method, attempt, int(delay * 1000), error.code().name)
                    time.sleep(delay)
                    continue
                self.breaker.finish(permit, failed)
                raise
            except Exception:
                self.breaker.finish(permit, True)
                raise
            else:
                self.breaker.finish(permit, False)
                return response
