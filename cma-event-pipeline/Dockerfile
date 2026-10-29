# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/frigate-cma-events@sha256:a333790affdaa4c21bdb41c251b083ee38d8ea888e6c38fc64af862bef1d7248
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
