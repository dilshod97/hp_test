#!/bin/sh
# Тизимни HTTPS орқали ишга тушириш (пилот синов учун).
# Фойдаланиш:  sh scripts/run_https.sh [порт]      (стандарт порт 8443)
set -e
cd "$(dirname "$0")/.."
PORT="${1:-8443}"
[ -f certs/server.crt ] || { echo "Аввал: sh scripts/make_certs.sh <IP>"; exit 1; }
exec .venv/bin/gunicorn config.wsgi:application -b "0.0.0.0:$PORT" -w 3 --timeout 60 \
  --certfile certs/server.crt --keyfile certs/server.key --access-logfile -
