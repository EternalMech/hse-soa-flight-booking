set -eu
if [ ! -f /data/redis.conf ]; then
    cat > /data/redis.conf <<EOF
bind 0.0.0.0
port 6379
protected-mode no
dir /data
save ""
appendonly no
replica-announce-ip ${REDIS_HOST}
replica-announce-port 6379
EOF
    if [ "${REDIS_INITIAL_REPLICA:-0}" = "1" ]; then
        printf 'replicaof redis-master 6379\n' >> /data/redis.conf
    fi
fi
exec /usr/local/bin/docker-entrypoint.sh redis-server /data/redis.conf
