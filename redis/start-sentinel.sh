set -eu
if [ ! -f /data/sentinel.conf ]; then
    cat > /data/sentinel.conf <<EOF
bind 0.0.0.0
port 26379
protected-mode no
dir /data
sentinel resolve-hostnames yes
sentinel announce-hostnames yes
sentinel announce-ip ${SENTINEL_HOST}
sentinel announce-port 26379
sentinel monitor flight-cache redis-master 6379 2
sentinel down-after-milliseconds flight-cache 3000
sentinel failover-timeout flight-cache 10000
sentinel parallel-syncs flight-cache 1
EOF
fi
exec /usr/local/bin/docker-entrypoint.sh redis-server /data/sentinel.conf --sentinel
