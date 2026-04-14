# Stage 1: Compile nyxid CLI from source
FROM rust:1.82-alpine3.21 AS builder

RUN apk add --no-cache \
    musl-dev \
    openssl-dev \
    openssl-libs-static \
    pkgconf \
    git \
    perl \
    make

ARG NYXID_VERSION=main
RUN git clone --depth 1 --branch ${NYXID_VERSION} \
    https://github.com/ChronoAIProject/NyxID.git /build/nyxid

WORKDIR /build/nyxid

ENV OPENSSL_STATIC=1
RUN cargo build --release --bin nyxid \
    && strip target/release/nyxid

# Stage 2: Runtime image
ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache \
    ca-certificates \
    jq \
    bash

COPY --from=builder /build/nyxid/target/release/nyxid /usr/local/bin/nyxid

COPY rootfs /
