import logging
import os

from google.protobuf.message import DecodeError
from redis import RedisError
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.sentinel import Sentinel

from services.config import number
from services.database import connect


logger = logging.getLogger(__name__)


class FlightCache:
    def __init__(self):
        self.ttl = number("CACHE_TTL_SECONDS", 300, 300, 600, integer=True)
        addresses = os.getenv("REDIS_SENTINELS", "sentinel-1:26379,sentinel-2:26379,sentinel-3:26379")
        nodes = [(host, int(port)) for host, port in (item.rsplit(":", 1) for item in addresses.split(","))]
        options = {"socket_timeout": 0.25, "socket_connect_timeout": 0.25, "retry": Retry(NoBackoff(), 0)}
        self.sentinel = Sentinel(nodes, sentinel_kwargs=options)
        self.redis = self.sentinel.master_for(os.getenv("REDIS_MASTER_NAME", "flight-cache"), **options)

    def read(self, suffix, message_type, load):
        with connect() as connection:
            revision = connection.execute("SELECT revision FROM cache_state WHERE id = TRUE FOR SHARE").fetchone()["revision"]
            key = f"v{revision}:{suffix}"
            try:
                raw = self.redis.get(key)
                if raw is not None:
                    result = message_type.FromString(raw)
                    logger.info("cache_hit key=%s", key)
                    return result
            except (RedisError, DecodeError) as error:
                logger.warning("cache_unavailable operation=get type=%s", type(error).__name__)
            logger.info("cache_miss key=%s", key)
            result = load(connection)
            try:
                self.redis.set(key, result.SerializeToString(), ex=self.ttl)
            except RedisError as error:
                logger.warning("cache_unavailable operation=set type=%s", type(error).__name__)
            return result

    def invalidate(self):
        with connect() as connection:
            revision = connection.execute("SELECT revision FROM cache_state WHERE id = TRUE").fetchone()["revision"]
        try:
            deleted = 0
            for key in self.redis.scan_iter(match="v*:*", count=100):
                prefix = key.split(b":", 1)[0]
                if prefix[1:].isdigit() and int(prefix[1:]) < revision:
                    deleted += self.redis.delete(key)
            logger.info("cache_invalidate revision=%s deleted=%s", revision, deleted)
        except RedisError as error:
            logger.warning("cache_unavailable operation=invalidate type=%s", type(error).__name__)
