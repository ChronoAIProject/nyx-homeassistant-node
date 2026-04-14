# Global ARGs
ARG BUILD_FROM
ARG NYXID_VERSION=0.2.0

# Stage 1: Get nyxid binary from official image (Debian-based)
FROM ghcr.io/chronoaiproject/nyxid/node-agent:${NYXID_VERSION} AS nyxid-bin

# Stage 2: HA runtime (Debian-based to match glibc)
FROM ${BUILD_FROM}

# Install runtime dependencies
# libdbus is needed at runtime for the dbus crate (linked dynamically)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        jq \
        bash \
        libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid

COPY rootfs /
