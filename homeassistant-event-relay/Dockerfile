ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir \
    paho-mqtt==2.1.0 \
    websocket-client==1.8.0

COPY app /app
WORKDIR /app
ENTRYPOINT ["python3", "/app/main.py"]
