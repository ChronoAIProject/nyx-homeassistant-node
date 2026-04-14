ARG NYXID_VERSION=0.2.0

# Stage 1: Get nyxid binary from official multi-arch image
FROM ghcr.io/chronoaiproject/nyxid/node-agent:${NYXID_VERSION} AS nyxid-bin

# Stage 2: Per-arch HA base images (Docker selects via TARGETARCH)
FROM ghcr.io/home-assistant/amd64-base-debian:bookworm AS base-amd64
FROM ghcr.io/home-assistant/aarch64-base-debian:bookworm AS base-arm64

# Stage 3: Runtime — select base by architecture
ARG TARGETARCH
FROM base-${TARGETARCH}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        jq \
        bash \
        libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid

COPY rootfs /
