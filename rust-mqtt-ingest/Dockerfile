# Build stage
FROM rust:1.85-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifests first for dependency caching
COPY Cargo.toml Cargo.lock* ./

# Create a dummy main.rs to build dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs

# Build dependencies only
RUN cargo build --release && rm -rf src

# Copy actual source code
COPY src ./src

# Build the actual application
RUN touch src/main.rs && cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/target/release/mqtt-ingest /usr/local/bin/mqtt-ingest

# Copy example config
COPY config.toml.example /app/config.toml.example

# Create non-root user
RUN useradd -m -U -s /bin/false mqttingest && \
    chown -R mqttingest:mqttingest /app

USER mqttingest

# Default command
ENTRYPOINT ["mqtt-ingest"]
CMD ["--config", "/app/config.toml"]
