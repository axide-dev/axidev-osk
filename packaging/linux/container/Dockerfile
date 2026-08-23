ARG BUILD_IMAGE=quay.io/pypa/manylinux_2_34_x86_64:latest
FROM ${BUILD_IMAGE}

ARG RUST_VERSION

RUN dnf install -y \
        curl \
        gcc \
        gcc-c++ \
        libinput-devel \
        libxkbcommon-devel \
        pkgconf-pkg-config \
        systemd-devel \
    && dnf clean all

RUN curl --proto '=https' --tlsv1.2 -fsS https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain "${RUST_VERSION}" \
    && /root/.cargo/bin/rustup target add x86_64-unknown-linux-musl

ENV PATH="/root/.cargo/bin:/opt/python/cp310-cp310/bin:${PATH}"

RUN python -m pip install --no-cache-dir \
        build \
        setuptools \
        wheel

COPY . /source
WORKDIR /source
