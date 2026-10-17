#!/bin/sh
# Ички HTTPS сертификати (домен шарт эмас — IP манзилга чиқарилади).
# Фойдаланиш:  sh scripts/make_certs.sh 10.42.0.231 [қўшимча-номлар...]
# Натижа: certs/ca.crt (тест компьютерларига "ишончли" қилиб ўрнатилади),
#         certs/server.crt + certs/server.key (сервер учун).
set -e
IP="${1:?Сервер IP манзилини беринг, масалан: sh scripts/make_certs.sh 10.42.0.231}"
shift
DIR="$(dirname "$0")/../certs"
mkdir -p "$DIR"
cd "$DIR"

if [ ! -f ca.key ]; then
  openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 1825 \
    -keyout ca.key -out ca.crt -subj "/O=Tanlov tizimi/CN=Tanlov tizimi ichki CA"
  echo "Янги сертификат маркази яратилди: certs/ca.crt"
fi

SAN="IP:$IP,IP:127.0.0.1,DNS:localhost"
for name in "$@"; do SAN="$SAN,DNS:$name"; done
cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
EXT
openssl req -new -nodes -newkey rsa:2048 -sha256 -keyout server.key -out server.csr -subj "/O=Tanlov tizimi/CN=$IP"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 825 -sha256 -extfile server.ext
rm -f server.csr server.ext
chmod 600 ca.key server.key
echo "Тайёр: certs/server.crt ($SAN)"
