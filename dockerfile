FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

FROM build AS dep

COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM base AS run

COPY run.py app.py keyExchange.py server.py server_messages.py ./
COPY --from=dep /install /usr/local
COPY --from=dep /app /app

CMD ["python", "run.py"]