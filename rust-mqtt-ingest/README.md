# MQTT Ingest (Rust)

High-performance MQTT APRS packet ingest service for haminfo, written in Rust.

This service subscribes to an MQTT topic (typically APRS packets from APRSD), parses the JSON packets, and bulk-inserts them into PostgreSQL.

## Features

- **Async I/O** with tokio for maximum throughput
- **Batch inserts** for efficient database writes (500 packets per batch by default)
- **Configurable** via file or environment variables
- **Graceful shutdown** handling
- **Statistics reporting** with packets-per-second metrics
- **Stats-only mode** for benchmarking without database writes

## Building

```bash
# Debug build
cargo build

# Release build (optimized)
cargo build --release
```

## Configuration

Configuration can be provided via:
1. Config file (TOML format)
2. Environment variables (prefixed with `MQTT_INGEST_`)

### Config File

Copy `config.toml.example` to `config.toml` and edit:

```toml
[mqtt]
host = "localhost"
port = 1883
topic = "aprs/packet"
qos = 0

[database]
url = "postgres://haminfo:haminfo@localhost:5432/haminfo"
max_connections = 10

[ingest]
batch_size = 500
batch_timeout_ms = 1000
stats_interval_secs = 10
stats_only = false
```

### Environment Variables

Environment variables use double underscore for nested keys:

```bash
export MQTT_INGEST_MQTT__HOST=mqtt.example.com
export MQTT_INGEST_MQTT__PORT=1883
export MQTT_INGEST_MQTT__TOPIC=aprs/packet
export MQTT_INGEST_DATABASE__URL=postgres://user:pass@host/db
export MQTT_INGEST_INGEST__BATCH_SIZE=500
export MQTT_INGEST_INGEST__STATS_ONLY=true
```

## Running

```bash
# With config file
./target/release/mqtt-ingest --config config.toml

# With environment variables only
MQTT_INGEST_MQTT__HOST=localhost \
MQTT_INGEST_MQTT__TOPIC=aprs/packet \
MQTT_INGEST_DATABASE__URL=postgres://... \
./target/release/mqtt-ingest

# Stats-only mode (for benchmarking)
./target/release/mqtt-ingest --config config.toml --stats-only
```

## Docker

```bash
# Build
docker build -t mqtt-ingest .

# Run
docker run -v ./config.toml:/app/config.toml mqtt-ingest
```

## Performance

The Rust implementation is designed to handle the APRS-IS packet firehose efficiently:

- **Zero-copy parsing** where possible
- **Batch database inserts** using PostgreSQL's `UNNEST()` for bulk efficiency
- **Async I/O** throughout - no blocking operations
- **Lock-free statistics** using atomic counters

Target throughput: 100+ packets per second sustained.

## License

Same as haminfo project.
