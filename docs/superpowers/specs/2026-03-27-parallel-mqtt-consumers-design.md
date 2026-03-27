# Parallel MQTT Consumers for APRS Packet Ingestion

**Date:** 2026-03-27  
**Status:** Draft  
**Author:** Claude + hemna

## Problem Statement

The haminfo MQTT ingestion pipeline cannot keep up with the volume of APRS packets being published to the MQTT queue. This results in:

- Growing queue backlog
- Potential packet loss
- Delayed data availability in the database

The bottleneck appears to be spread across multiple stages: JSON decoding, packet parsing, and database writes.

## Goals

1. Improve packet processing throughput without changing the aprsd side
2. Better utilize multi-core systems
3. Maintain resilience and reliability
4. Keep changes minimal and incremental

## Non-Goals

- Changing aprsd or aprsd-mqtt-plugin (future improvement)
- Changing the database schema
- Implementing MQTTRawPlugin support (future improvement)

## Design

### Architecture Overview

**Current Flow:**
```
MQTT → MQTTThread (1) → packet_queue → APRSPacketProcessorThread (1) → DB
                                     → WeatherPacketProcessorThread (1) → DB
```

**Proposed Flow:**
```
MQTT → MQTTThread (1) → round-robin distribution
                           ├→ aprs_queue_0 → APRSPacketProcessorThread #0 → DB
                           ├→ aprs_queue_1 → APRSPacketProcessorThread #1 → DB
                           ├→ aprs_queue_2 → APRSPacketProcessorThread #2 → DB
                           ├→ ...
                           ├→ aprs_queue_N → APRSPacketProcessorThread #N → DB
                           └→ weather_queue → WeatherPacketProcessorThread → DB
```

### Key Design Decisions

**Round-robin distribution (not shared queue):**
- Avoids lock contention on a single queue
- Each processor has predictable, independent workload
- Simpler reasoning about backpressure per-processor

**Single MQTT consumer:**
- MQTT message handling is I/O-bound, not CPU-bound
- Distributing to N queues is fast (just pointer assignment)
- Avoids complexity of MQTT shared subscriptions

**Weather processor stays at 1:**
- Lower packet volume than general APRS traffic
- More complex per-packet logic (station lookup, geocoding)
- Can be parallelized later if needed

### Configuration

New oslo.config option in `haminfo/conf/mqtt.py`:

```python
cfg.IntOpt(
    'processor_count',
    default=4,
    min=1,
    max=32,
    help='Number of parallel APRS packet processor threads. '
         'Increase to improve throughput on multi-core systems.'
),
```

Usage in `haminfo.conf`:
```ini
[mqtt]
processor_count = 8
```

### Implementation Details

#### MQTTThread Changes (`haminfo/mqtt/thread.py`)

The MQTTThread already supports multiple queues. Changes needed:

1. Separate APRS queues from weather queue
2. Round-robin distribution to APRS queues
3. Weather packets go to both an APRS queue (for APRSPacket storage) and the weather queue

```python
def __init__(self, packet_queues: list[queue.Queue], stats, stats_lock):
    # packet_queues[0:N-1] = APRS processor queues (round-robin)
    # packet_queues[-1] = Weather processor queue
    self.aprs_queues = packet_queues[:-1]
    self.weather_queue = packet_queues[-1]
    self.rr_index = 0

def on_message(self, client, userdata, msg):
    # ... parse packet ...
    
    if aprsd_packet:
        # Round-robin to APRS processors
        aprs_queue = self.aprs_queues[self.rr_index % len(self.aprs_queues)]
        self.rr_index += 1
        try:
            aprs_queue.put_nowait(aprsd_packet)
        except queue.Full:
            logger.warning('APRS queue full, dropping packet')
        
        # Weather packets also go to weather processor
        if isinstance(aprsd_packet, WeatherPacket):
            try:
                self.weather_queue.put_nowait(aprsd_packet)
            except queue.Full:
                logger.warning('Weather queue full, dropping packet')
```

#### Command Changes (`haminfo/cmds/mqtt_ingest.py`)

```python
@cli.command()
def wx_mqtt_ingest(ctx):
    # ...
    
    processor_count = CONF.mqtt.processor_count
    LOG.info(f'Starting {processor_count} APRS packet processor threads')
    
    # Create N APRS queues + 1 weather queue
    aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
    weather_queue = queue.Queue(maxsize=5000)
    
    # Create N APRS processor threads
    aprs_processors = []
    for i in range(processor_count):
        processor = APRSPacketProcessorThread(
            aprs_queues[i],
            session_factory,
            stats,
            stats_lock,
        )
        processor.name = f'APRSPacketProcessorThread-{i}'
        aprs_processors.append(processor)
    
    # Single weather processor
    weather_processor = WeatherPacketProcessorThread(
        weather_queue, session_factory, stats, stats_lock
    )
    
    # MQTT thread gets all queues
    all_queues = aprs_queues + [weather_queue]
    mqtt_thread = MQTTThread(all_queues, stats, stats_lock)
    
    # Start all threads
    for processor in aprs_processors:
        LOG.info(f'Starting {processor.name}')
        processor.start()
    weather_processor.start()
    mqtt_thread.start()
    
    # Wait for MQTT thread
    mqtt_thread.join()
    
    # Graceful shutdown
    LOG.info('Stopping processor threads')
    for processor in aprs_processors:
        processor.stop()
    weather_processor.stop()
    
    for processor in aprs_processors:
        processor.join(timeout=5)
    weather_processor.join(timeout=5)
```

### Stats Aggregation

The shared `stats` dict with `stats_lock` already handles concurrent updates from multiple threads. No changes needed.

Each processor increments:
- `stats['packet_counter']`
- `stats['packets_saved']`
- `stats['packet_types']`
- `stats['unique_callsigns']`

### Graceful Shutdown

Each `APRSPacketProcessorThread` already has `_cleanup()` that flushes pending batches before stopping. The shutdown sequence:

1. MQTT thread stops (no new packets)
2. Each APRS processor drains its queue and flushes final batch
3. Weather processor drains its queue and flushes

## Files Changed

| File | Change |
|------|--------|
| `haminfo/conf/mqtt.py` | Add `processor_count` config option |
| `haminfo/mqtt/thread.py` | Round-robin distribution to N APRS queues |
| `haminfo/cmds/mqtt_ingest.py` | Spawn N processor threads |

## Testing

1. **Unit tests:** Verify round-robin distribution logic
2. **Integration test:** Run with `processor_count=1` (current behavior) vs `processor_count=4`
3. **Load test:** Measure packets/second with varying processor counts
4. **Verify stats:** Ensure packet counts are accurate across parallel processors

## Expected Results

With `processor_count=4`:
- ~4x throughput for packet parsing/processing
- ~4x throughput for DB writes (parallel sessions, batched inserts)
- Better CPU utilization on multi-core systems

## Rollback

To restore single-threaded behavior, set `processor_count=1` in your config:

```ini
[mqtt]
processor_count = 1
```

This immediately reverts to the original single-processor architecture.

## Future Improvements

If parallel consumers aren't sufficient, next steps:

1. **MQTTRawPlugin integration** — eliminate JSON encode/decode overhead by having aprsd publish raw APRS strings instead of JSON
2. **PostgreSQL COPY** — bulk insert using COPY instead of INSERT ... ON CONFLICT (~10x faster)
3. **Direct DB plugin for aprsd** — eliminate MQTT entirely for lowest latency

## Alternatives Considered

### Alternative 1: Direct aprsd DB Plugin

An aprsd plugin that writes directly to PostgreSQL, bypassing MQTT entirely.

**Pros:** Lowest latency, no serialization overhead  
**Cons:** Tight coupling, no buffering during DB slowdowns, single point of failure

**Decision:** Deferred. Start with parallel consumers to minimize risk.

### Alternative 2: MQTTRawPlugin + Raw String Parsing

Have aprsd publish raw APRS strings via MQTTRawPlugin, parse in haminfo.

**Pros:** Eliminates JSON overhead  
**Cons:** Requires aprsd-side changes, different parsing path

**Decision:** Deferred. Can be added later as a second optimization.

### Alternative 3: Shared Queue with Multiple Consumers

Single queue with multiple consumers instead of round-robin to separate queues.

**Pros:** Simpler setup  
**Cons:** Lock contention on queue, harder to reason about backpressure

**Decision:** Rejected. Round-robin provides better isolation and performance.
