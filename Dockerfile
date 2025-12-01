FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyTelegramBotAPI schedule requests psycopg2-binary
RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates

COPY . .

CMD ["python", "pipi.py"]
