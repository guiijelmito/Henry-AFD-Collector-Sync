ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.63.0-noble
FROM ${PLAYWRIGHT_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TZ=America/Sao_Paulo

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tzdata \
    && ln --symbolic --force /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY main.py ./main.py
COPY src/ ./src/

RUN mkdir --parents /data /tmp/afd_downloads

CMD ["python", "-m", "ponto_eletronico.pipeline"]
