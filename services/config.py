import math
import os


def number(name, default, minimum, maximum, integer=False):
    raw = os.getenv(name, str(default))
    value = int(raw) if integer else float(raw)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def api_key():
    value = os.environ["FLIGHT_API_KEY"]
    if len(value) < 16 or not value.isascii():
        raise ValueError("FLIGHT_API_KEY must contain at least 16 ASCII characters")
    return value
