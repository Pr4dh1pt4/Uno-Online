#!/bin/sh
set -eu

DB_HOST="${UNO_DB_HOST:-db}"
DB_PORT="${UNO_DB_PORT:-3306}"
DB_USER="${UNO_DB_USER:-root}"
DB_PASSWORD="${UNO_DB_PASSWORD:-password}"

echo "Waiting for MariaDB at ${DB_HOST}:${DB_PORT}..."
until mariadb-admin ping \
  -h"${DB_HOST}" \
  -P"${DB_PORT}" \
  -u"${DB_USER}" \
  -p"${DB_PASSWORD}" \
  --silent; do
  sleep 2
done

echo "Initializing database schema..."
python -m server.main_server --init-db

echo "Starting UNO Online TCP/UDP server..."
python -m server.main_server &
SERVER_PID="$!"

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

sleep 2
echo "Starting UNO Online web gateway..."
python -m server.web_gateway
