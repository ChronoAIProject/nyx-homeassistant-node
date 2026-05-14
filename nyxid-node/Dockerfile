ARG NYXID_VERSION=0.5.6

FROM debian:trixie-slim

ARG NYXID_VERSION
ARG S6_OVERLAY_VERSION=3.2.0.2
ARG BASHIO_VERSION=0.16.2
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils jq bash libdbus-1-3 \
    && ARCH_TRIPLE=$(case "${TARGETARCH}" in \
            amd64) echo x86_64-unknown-linux-gnu;; \
            arm64) echo aarch64-unknown-linux-gnu;; \
            *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1;; \
        esac) \
    && curl -fsSL "https://github.com/ChronoAIProject/NyxID/releases/download/v${NYXID_VERSION}/nyxid-cli-${ARCH_TRIPLE}.tar.gz" \
        | tar -xzf - -C /tmp \
    && mv "/tmp/nyxid-cli-${ARCH_TRIPLE}/nyxid" /usr/local/bin/nyxid \
    && chmod +x /usr/local/bin/nyxid \
    && rm -rf "/tmp/nyxid-cli-${ARCH_TRIPLE}" \
    && S6_ARCH=$(case "${TARGETARCH}" in amd64) echo x86_64;; arm64) echo aarch64;; *) echo ${TARGETARCH};; esac) \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" | tar Jxpf - -C / \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" | tar Jxpf - -C / \
    && mkdir -p /usr/lib/bashio \
    && curl -fsSL "https://github.com/hassio-addons/bashio/archive/refs/tags/v${BASHIO_VERSION}.tar.gz" | tar xzf - -C /tmp \
    && cp -r /tmp/bashio-${BASHIO_VERSION}/lib/* /usr/lib/bashio/ \
    && rm -rf /tmp/bashio-${BASHIO_VERSION} \
    && chmod +x /usr/lib/bashio/bashio.sh \
    && printf '#!/usr/bin/env bash\nsource /usr/lib/bashio/bashio.sh\n. "$@"\n' > /usr/bin/bashio \
    && chmod +x /usr/bin/bashio \
    && apt-get purge -y --auto-remove xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs /

ENTRYPOINT ["/init"]
