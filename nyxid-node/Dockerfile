ARG NYXID_VERSION=0.2.0

# Stage 1: Get nyxid binary from official multi-arch image
FROM ghcr.io/chronoaiproject/nyxid/node-agent:${NYXID_VERSION} AS nyxid-bin

# Stage 2: Per-arch HA Alpine base images (have s6-overlay built-in)
FROM ghcr.io/home-assistant/amd64-base:3.21 AS base-amd64
FROM ghcr.io/home-assistant/aarch64-base:3.21 AS base-arm64

# Stage 3: Runtime — select base by architecture
ARG TARGETARCH
FROM base-${TARGETARCH}

# gcompat provides glibc compatibility on Alpine (nyxid is glibc-linked)
# libgcc is needed for Rust's unwinding support
RUN apk add --no-cache \
    ca-certificates \
    jq \
    bash \
    gcompat \
    libgcc

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid

COPY rootfs /
