FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY config.py ./
COPY shared ./shared
COPY server ./server
COPY web ./web
COPY client/assets ./client/assets
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh \
    && mkdir -p /app/data/logs

EXPOSE 5555/tcp
EXPOSE 5556/udp
EXPOSE 8080/tcp

ENTRYPOINT ["./docker/entrypoint.sh"]
