# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/frigate-cma-events@sha256:1da270611b6a94ae7f5036aa492051eaa4c96f4e990dfe80e5e007d5cbe0bc0d
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
