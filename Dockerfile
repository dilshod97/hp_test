FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEBUG=false
RUN apt-get update && apt-get install -y --no-install-recommends openssl libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN SECRET_KEY=build python manage.py collectstatic --noinput
EXPOSE 8000
VOLUME ["/app/data", "/app/media", "/app/certs"]
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
