ARG RUST_BASE=rust:1-trixie
FROM ${RUST_BASE}
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates clang cmake curl git libssl-dev pkg-config protobuf-compiler && rm -rf /var/lib/apt/lists/*
RUN rustup toolchain install 1.99.0 --profile minimal --component rustfmt --component clippy && rustup default 1.99.0
ENV CARGO_BUILD_JOBS=2
RUN rustc -vV && cargo -V && rustfmt -V && cargo clippy -V && protoc --version && clang --version && g++ --version && cmake --version && git --version && dpkg-query -W
