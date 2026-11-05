# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/video-event-monitor@sha256:337dcb08c6b60df278d3bf17c3c087b1950beade0be0c33f5a44b9cbb49a110f
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
