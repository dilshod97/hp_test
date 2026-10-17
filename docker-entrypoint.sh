#!/bin/sh
# Контейнер ишга тушганда: махфий калит, база, суперадмин, HTTPS сертификати, сўнг gunicorn.
set -e
mkdir -p /app/data /app/media /app/certs

# Махфий калит берилмаган бўлса — бир марта яратиб, data томида сақлаймиз
if [ -z "$SECRET_KEY" ]; then
  [ -f /app/data/secret_key ] || python -c "import secrets; print(secrets.token_urlsafe(50))" > /app/data/secret_key
  export SECRET_KEY="$(cat /app/data/secret_key)"
fi

# HTTPS: сертификат йўқ бўлса ва SERVER_IP берилган бўлса — ички сертификат яратамиз
if [ ! -f /app/certs/server.crt ] && [ -n "$SERVER_IP" ]; then
  sh /app/scripts/make_certs.sh "$SERVER_IP" $SERVER_NAMES
fi

python manage.py migrate --noinput
if [ -n "$SUPERADMIN_USERNAME" ] && [ -n "$SUPERADMIN_PASSWORD" ]; then
  python manage.py create_superadmin
fi

if [ -f /app/certs/server.crt ]; then
  export HTTPS=true
  echo "HTTPS ёқилган. Тест компьютерларига /app/certs/ca.crt ни ишончли қилиб ўрнатинг."
  exec gunicorn config.wsgi:application -b 0.0.0.0:8000 -w "${WORKERS:-4}" --timeout 60 \
    --certfile /app/certs/server.crt --keyfile /app/certs/server.key --access-logfile -
fi
echo "ДИҚҚАТ: HTTPS ўчиқ (SERVER_IP берилмаган). Веб-камера фақат HTTPS'да ишлайди."
exec gunicorn config.wsgi:application -b 0.0.0.0:8000 -w "${WORKERS:-4}" --timeout 60 --access-logfile -
