# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/frigate-cma-events@sha256:edd6d4c1746f4bbd195ef143eb1e1ba9baf7605b603e66910f53c3d002f05314
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
