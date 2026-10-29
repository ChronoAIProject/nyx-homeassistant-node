# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/frigate-cma-events@sha256:efd9b6191737b322a5b0d0ede3047a3e9fd75de96659c04f100e0195665715e4
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
