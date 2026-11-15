# Pinned to a tested upstream core; both architectures use the same implementation.
ARG BUILD_FROM=ghcr.io/chronoaiproject/video-event-monitor@sha256:9a05552b18a709446f30d2af344a1b17bc91bf4e290088fc85c026814dae82fa
FROM ${BUILD_FROM}
USER root
COPY app /addon
ENTRYPOINT ["/app/.venv/bin/python", "/addon/run.py"]
CMD []
