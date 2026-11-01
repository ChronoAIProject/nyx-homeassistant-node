# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/video-event-monitor@sha256:d56d622eb7f3968f4550e5a8a5ac14c805f4f161aca593790a478888e813a5fd
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
