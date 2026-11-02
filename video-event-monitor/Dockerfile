# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/video-event-monitor@sha256:8f93ae2666a23e0fa49c0f69e6f85e369a0e4c4b52cb10103b35a7f7b3a13691
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
