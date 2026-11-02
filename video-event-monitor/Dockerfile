# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/video-event-monitor@sha256:612a003d7a90bbf5d132f6b7f9cb23c771654bc24ac0b71e5494cb7455bae28c
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
