ARG NYXID_VERSION=0.2.0

# Stage 1: Get nyxid binary from official multi-arch image
FROM ghcr.io/chronoaiproject/nyxid/node-agent:${NYXID_VERSION} AS nyxid-bin

# Stage 2: Runtime — Debian with s6-overlay + bashio
FROM debian:bookworm-slim

ARG S6_OVERLAY_VERSION=3.2.0.2
ARG BASHIO_VERSION=0.16.2
ARG TARGETARCH

# Install everything in one layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils jq bash libdbus-1-3 \
    # s6-overlay
    && S6_ARCH=$(case "${TARGETARCH}" in amd64) echo x86_64;; arm64) echo aarch64;; *) echo ${TARGETARCH};; esac) \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" | tar Jxpf - -C / \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" | tar Jxpf - -C / \
    # bashio
    && mkdir -p /usr/lib/bashio \
    && curl -fsSL "https://github.com/hassio-addons/bashio/archive/refs/tags/v${BASHIO_VERSION}.tar.gz" | tar xzf - -C /tmp \
    && cp -r /tmp/bashio-${BASHIO_VERSION}/lib/* /usr/lib/bashio/ \
    && rm -rf /tmp/bashio-${BASHIO_VERSION} \
    && chmod +x /usr/lib/bashio/bashio.sh \
    && printf '#!/usr/bin/env bash\nsource /usr/lib/bashio/bashio.sh\n. "$@"\n' > /usr/bin/bashio \
    && chmod +x /usr/bin/bashio \
    # cleanup build-only deps (keep curl — bashio needs it at runtime)
    && apt-get purge -y --auto-remove xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid
COPY rootfs /

ENTRYPOINT ["/init"]
