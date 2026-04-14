ARG NYXID_VERSION=0.2.0

# Stage 1: Get nyxid binary from official multi-arch image
FROM ghcr.io/chronoaiproject/nyxid/node-agent:${NYXID_VERSION} AS nyxid-bin

# Stage 2: Runtime — Debian with s6-overlay
FROM debian:bookworm-slim

# Install s6-overlay
ARG S6_OVERLAY_VERSION=3.2.0.2
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils \
    && S6_ARCH=$(case "${TARGETARCH}" in amd64) echo x86_64;; arm64) echo aarch64;; *) echo ${TARGETARCH};; esac) \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" | tar Jxpf - -C / \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" | tar Jxpf - -C / \
    && apt-get purge -y --auto-remove curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install bashio
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl jq bash \
    && curl -fsSL "https://raw.githubusercontent.com/hassio-addons/bashio/v0.16.2/lib/bashio.sh" -o /usr/lib/bashio.sh \
    && mkdir -p /usr/lib/bashio \
    && curl -fsSL "https://github.com/hassio-addons/bashio/archive/refs/tags/v0.16.2.tar.gz" | tar xzf - -C /tmp \
    && cp -r /tmp/bashio-0.16.2/lib/* /usr/lib/bashio/ \
    && rm -rf /tmp/bashio-0.16.2 \
    && ln -sf /usr/lib/bashio/bashio.sh /usr/bin/bashio \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# Runtime deps for nyxid
RUN apt-get update && apt-get install -y --no-install-recommends \
        libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid

COPY rootfs /

ENTRYPOINT ["/init"]
