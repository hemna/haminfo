# Parallel MQTT Consumers Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable parallel APRS packet processing to improve MQTT ingestion throughput.

**Architecture:** Single MQTT thread distributes packets round-robin to N parallel APRSPacketProcessorThread instances, each with its own queue and DB session. Weather processor remains single-threaded.

**Tech Stack:** Python 3.10+, oslo.config, paho-mqtt, SQLAlchemy, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-27-parallel-mqtt-consumers-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `haminfo/conf/mqtt.py` | Modify | Add `processor_count` config option |
| `haminfo/mqtt/thread.py` | Modify | Round-robin distribution to N APRS queues |
| `haminfo/cmds/mqtt_ingest.py` | Modify | Spawn N processor threads |
| `tests/test_mqtt_config.py` | Create | Unit tests for config options |
| `tests/test_mqtt_thread.py` | Create | Unit tests for round-robin logic |
| `tests/test_mqtt_ingest_parallel.py` | Create | Tests for parallel processor setup |
| `tests/test_parallel_mqtt_integration.py` | Create | Integration tests for full pipeline |

---

## Chunk 1: Configuration

### Task 1: Add processor_count config option

**Files:**
- Modify: `haminfo/conf/mqtt.py:10-32`
- Test: `tests/test_mqtt_config.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_mqtt_config.py`:

```python
"""Tests for MQTT configuration options."""

import pytest
from oslo_config import cfg

from haminfo.conf import mqtt


@pytest.fixture
def config():
    """Create a fresh config for each test."""
    conf = cfg.ConfigOpts()
    mqtt.register_opts(conf)
    return conf


def test_processor_count_default(config):
    """processor_count should default to 4."""
    assert config.mqtt.processor_count == 4


def test_processor_count_minimum(config):
    """processor_count should have minimum of 1."""
    config.set_override('processor_count', 1, group='mqtt')
    assert config.mqtt.processor_count == 1


def test_processor_count_maximum(config):
    """processor_count should have maximum of 32."""
    config.set_override('processor_count', 32, group='mqtt')
    assert config.mqtt.processor_count == 32


def test_processor_count_below_minimum_raises(config):
    """processor_count below 1 should raise."""
    with pytest.raises((ValueError, cfg.ConfigFileValueError)):
        config.set_override('processor_count', 0, group='mqtt')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mqtt_config.py -v`
Expected: FAIL with "no such option: processor_count"

- [ ] **Step 3: Add processor_count option**

Modify `haminfo/conf/mqtt.py`, add to `mqtt_opts` list after line 31:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mqtt_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/conf/mqtt.py tests/test_mqtt_config.py
git commit -m "feat(mqtt): add processor_count config option

Adds configurable number of parallel APRS packet processor threads.
Default is 4, range 1-32.

Part of: parallel MQTT consumers feature"
```

---

## Chunk 2: MQTTThread Round-Robin Distribution

### Task 2: Add round-robin distribution to MQTTThread

**Files:**
- Modify: `haminfo/mqtt/thread.py:43-84` (constructor), `haminfo/mqtt/thread.py:402-442` (on_message)
- Test: `tests/test_mqtt_thread.py` (create)

- [ ] **Step 1: Write the failing test for round-robin**

Create `tests/test_mqtt_thread.py`:

```python
"""Tests for MQTTThread round-robin distribution."""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestMQTTThreadRoundRobin:
    """Tests for round-robin packet distribution."""

    @pytest.fixture
    def stats(self):
        """Create shared stats dict."""
        return {
            'start_time': 0,
            'packet_counter': 0,
            'packets_saved': 0,
            'report_counter': 0,
            'packet_types': {},
            'unique_callsigns': set(),
        }

    @pytest.fixture
    def stats_lock(self):
        """Create stats lock."""
        return threading.Lock()

    @pytest.fixture
    def queues(self):
        """Create test queues: 3 APRS + 1 weather."""
        return [queue.Queue() for _ in range(4)]

    @patch('haminfo.mqtt.thread.CONF')
    def test_round_robin_distribution(self, mock_conf, queues, stats, stats_lock):
        """Packets should be distributed round-robin to APRS queues."""
        from haminfo.mqtt.thread import MQTTThread

        # Mock config
        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        # Patch _connect to avoid actual MQTT connection
        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(queues, stats, stats_lock)

        # Verify queue separation
        assert len(thread.aprs_queues) == 3
        assert thread.weather_queue is queues[3]

        # Simulate distributing 6 packets
        for i in range(6):
            # Get expected queue index
            expected_idx = i % 3
            actual_queue = thread.aprs_queues[thread.rr_index % len(thread.aprs_queues)]
            assert actual_queue is queues[expected_idx], f"Packet {i} went to wrong queue"
            thread.rr_index += 1

    @patch('haminfo.mqtt.thread.CONF')
    def test_weather_packet_goes_to_both_queues(self, mock_conf, queues, stats, stats_lock):
        """Weather packets should go to APRS queue AND weather queue."""
        from haminfo.mqtt.thread import MQTTThread
        from aprsd.packets.core import WeatherPacket

        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(queues, stats, stats_lock)

        # Create a mock weather packet
        weather_packet = MagicMock(spec=WeatherPacket)

        # Distribute to APRS queue (round-robin)
        aprs_queue = thread.aprs_queues[thread.rr_index % len(thread.aprs_queues)]
        aprs_queue.put_nowait(weather_packet)
        thread.rr_index += 1

        # Also distribute to weather queue
        thread.weather_queue.put_nowait(weather_packet)

        # Verify packet is in both queues
        assert queues[0].qsize() == 1  # First APRS queue
        assert queues[3].qsize() == 1  # Weather queue


class TestMQTTThreadBackwardCompatibility:
    """Tests for backward compatibility with single queue."""

    @pytest.fixture
    def stats(self):
        return {'start_time': 0, 'packet_counter': 0}

    @pytest.fixture
    def stats_lock(self):
        return threading.Lock()

    @patch('haminfo.mqtt.thread.CONF')
    def test_single_queue_still_works(self, mock_conf, stats, stats_lock):
        """Single queue input should still work (backward compat)."""
        from haminfo.mqtt.thread import MQTTThread

        mock_conf.mqtt.host_ip = 'localhost'
        mock_conf.mqtt.host_port = 1883
        mock_conf.mqtt.user = None
        mock_conf.mqtt.topic = 'test/topic'

        single_queue = queue.Queue()

        with patch.object(MQTTThread, '_connect'):
            thread = MQTTThread(single_queue, stats, stats_lock)

        # Should handle single queue gracefully
        assert thread.packet_queue is single_queue
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mqtt_thread.py -v`
Expected: FAIL with "MQTTThread has no attribute 'aprs_queues'"

- [ ] **Step 3: Modify MQTTThread constructor**

Modify `haminfo/mqtt/thread.py`. Add new attributes after line 56 (`self.packet_queue = self.packet_queues[0]`):

```python
        # Separate APRS queues (round-robin) from weather queue (last one)
        if len(self.packet_queues) > 1:
            self.aprs_queues = self.packet_queues[:-1]
            self.weather_queue = self.packet_queues[-1]
        else:
            # Single queue mode: same queue for both
            self.aprs_queues = self.packet_queues
            self.weather_queue = self.packet_queues[0]

        # Round-robin index for APRS queue distribution
        self.rr_index: int = 0
```

- [ ] **Step 4: Run tests to verify constructor changes pass**

Run: `pytest tests/test_mqtt_thread.py::TestMQTTThreadRoundRobin::test_round_robin_distribution -v`
Expected: PASS

- [ ] **Step 5: Modify on_message for round-robin distribution**

Modify `haminfo/mqtt/thread.py`. Replace the packet distribution logic in `on_message` method (around lines 423-428) with:

```python
        if aprsd_packet:
            # Round-robin to APRS processors
            aprs_queue = self.aprs_queues[self.rr_index % len(self.aprs_queues)]
            self.rr_index += 1
            try:
                aprs_queue.put_nowait(aprsd_packet)
            except queue.Full:
                logger.warning('APRS packet queue full, dropping packet')

            # Weather packets also go to weather processor
            from aprsd.packets.core import WeatherPacket
            if isinstance(aprsd_packet, WeatherPacket):
                try:
                    self.weather_queue.put_nowait(aprsd_packet)
                except queue.Full:
                    logger.warning('Weather queue full, dropping packet')
```

- [ ] **Step 6: Run all thread tests**

Run: `pytest tests/test_mqtt_thread.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add haminfo/mqtt/thread.py tests/test_mqtt_thread.py
git commit -m "feat(mqtt): add round-robin distribution to MQTTThread

MQTTThread now distributes packets round-robin to N APRS processor
queues. Weather packets go to both an APRS queue and the dedicated
weather queue.

Backward compatible: single queue input still works.

Part of: parallel MQTT consumers feature"
```

---

## Chunk 3: Parallel Processor Spawning

### Task 3: Update mqtt_ingest command to spawn N processors

**Files:**
- Modify: `haminfo/cmds/mqtt_ingest.py:47-117`
- Test: `tests/test_mqtt_ingest_parallel.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_mqtt_ingest_parallel.py`:

```python
"""Tests for MQTT ingest command with parallel processors."""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestParallelProcessorSetup:
    """Tests for parallel processor thread creation."""

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    @patch('haminfo.cmds.mqtt_ingest.db')
    def test_creates_n_aprs_queues(self, mock_db, mock_conf):
        """Should create processor_count APRS queues."""
        mock_conf.mqtt.processor_count = 4

        # Create queues as the command would
        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]

        assert len(aprs_queues) == 4

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    @patch('haminfo.cmds.mqtt_ingest.db')
    def test_creates_n_processor_threads(self, mock_db, mock_conf):
        """Should create processor_count APRSPacketProcessorThread instances."""
        from haminfo.mqtt import APRSPacketProcessorThread

        mock_conf.mqtt.processor_count = 4
        mock_db.setup_session.return_value = MagicMock()

        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
        session_factory = mock_db.setup_session()
        stats = {}
        stats_lock = threading.Lock()

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

        assert len(aprs_processors) == 4
        assert aprs_processors[0].name == 'APRSPacketProcessorThread-0'
        assert aprs_processors[3].name == 'APRSPacketProcessorThread-3'

    @patch('haminfo.cmds.mqtt_ingest.CONF')
    def test_mqtt_thread_receives_all_queues(self, mock_conf):
        """MQTTThread should receive N APRS queues + 1 weather queue."""
        mock_conf.mqtt.processor_count = 4

        processor_count = mock_conf.mqtt.processor_count
        aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=5000)

        all_queues = aprs_queues + [weather_queue]

        assert len(all_queues) == 5  # 4 APRS + 1 weather
```

- [ ] **Step 2: Run test to verify structure is correct**

Run: `pytest tests/test_mqtt_ingest_parallel.py -v`
Expected: PASS (these are structure tests, not integration)

- [ ] **Step 3: Update mqtt_ingest.py command**

Modify `haminfo/cmds/mqtt_ingest.py`. Replace the `wx_mqtt_ingest` function:

```python
@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def wx_mqtt_ingest(ctx):
    """Ingest APRSD Weather packets from an MQTT queue."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    LOG.info(f'Haminfo MQTT Started version: {haminfo.__version__}')
    CONF.log_opt_values(LOG, logging.DEBUG)

    # Get session factory - processors will create their own sessions
    session_factory = db.setup_session()

    # Get processor count from config
    processor_count = CONF.mqtt.processor_count
    LOG.info(f'Starting {processor_count} parallel APRS packet processor threads')

    # Create N APRS queues + 1 weather queue
    aprs_queues = [queue.Queue(maxsize=5000) for _ in range(processor_count)]
    weather_queue = queue.Queue(maxsize=5000)

    # Shared stats dictionary and lock for thread-safe access
    stats_lock = threading.Lock()
    stats = {
        'start_time': time.time(),
        'packet_counter': 0,
        'packets_saved': 0,
        'report_counter': 0,
        'packet_types': {},
        'unique_callsigns': set(),
    }

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
        weather_queue,
        session_factory,
        stats,
        stats_lock,
    )

    # MQTT thread gets all queues: [aprs_0, ..., aprs_N-1, weather]
    all_queues = aprs_queues + [weather_queue]
    mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

    # Start all threads
    keepalive = threads.KeepAliveThread()
    keepalive.start()

    for i, processor in enumerate(aprs_processors):
        LOG.info(f'Starting {processor.name}')
        processor.start()

    LOG.info('Starting weather packet processor thread')
    weather_processor.start()

    LOG.info('Starting MQTT thread')
    mqtt_thread.start()

    # Wait for MQTT thread (runs until stopped)
    mqtt_thread.join()

    # Graceful shutdown - stop all processor threads
    LOG.info('Stopping processor threads')
    for processor in aprs_processors:
        processor.stop()
    weather_processor.stop()

    # Wait for processors to finish
    for processor in aprs_processors:
        processor.join(timeout=5)
    weather_processor.join(timeout=5)

    LOG.info('Waiting for keepalive thread to quit')
    keepalive.stop()
    keepalive.join()


# Backward compatibility alias
wx_mqtt_injest = wx_mqtt_ingest
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_mqtt_ingest_parallel.py tests/test_mqtt_thread.py tests/test_mqtt_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add haminfo/cmds/mqtt_ingest.py tests/test_mqtt_ingest_parallel.py
git commit -m "feat(mqtt): spawn N parallel APRS processor threads

The wx_mqtt_ingest command now spawns processor_count (default 4)
parallel APRSPacketProcessorThread instances. Each has its own queue
and DB session for maximum throughput.

Usage: Set mqtt.processor_count in config to tune parallelism.

Part of: parallel MQTT consumers feature"
```

---

## Chunk 4: Integration Testing & Documentation

### Task 4: Add integration test and update docs

**Files:**
- Create: `tests/test_parallel_mqtt_integration.py`
- Modify: `docs/superpowers/specs/2026-03-27-parallel-mqtt-consumers-design.md` (add rollback note)

- [ ] **Step 1: Create integration test**

Create `tests/test_parallel_mqtt_integration.py`:

```python
"""Integration tests for parallel MQTT processing."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from haminfo.mqtt import MQTTThread, APRSPacketProcessorThread


class TestParallelProcessingIntegration:
    """Integration tests for the full parallel processing pipeline."""

    @pytest.fixture
    def stats(self):
        return {
            'start_time': time.time(),
            'packet_counter': 0,
            'packets_saved': 0,
            'report_counter': 0,
            'packet_types': {},
            'unique_callsigns': set(),
        }

    @pytest.fixture
    def stats_lock(self):
        return threading.Lock()

    def test_packets_distributed_across_processors(self, stats, stats_lock):
        """Packets should be evenly distributed across all processors."""
        processor_count = 4
        aprs_queues = [queue.Queue(maxsize=100) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=100)

        with patch('haminfo.mqtt.thread.CONF') as mock_conf:
            mock_conf.mqtt.host_ip = 'localhost'
            mock_conf.mqtt.host_port = 1883
            mock_conf.mqtt.user = None
            mock_conf.mqtt.topic = 'test/topic'

            with patch.object(MQTTThread, '_connect'):
                all_queues = aprs_queues + [weather_queue]
                mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

        # Simulate 100 packets being distributed
        for i in range(100):
            aprs_queue = mqtt_thread.aprs_queues[mqtt_thread.rr_index % len(mqtt_thread.aprs_queues)]
            mqtt_thread.rr_index += 1
            aprs_queue.put_nowait(f'packet_{i}')

        # Each queue should have ~25 packets (100 / 4)
        for i, q in enumerate(aprs_queues):
            assert q.qsize() == 25, f"Queue {i} has {q.qsize()} packets, expected 25"

    def test_processor_count_one_matches_original_behavior(self, stats, stats_lock):
        """processor_count=1 should behave like original single-threaded mode."""
        processor_count = 1
        aprs_queues = [queue.Queue(maxsize=100) for _ in range(processor_count)]
        weather_queue = queue.Queue(maxsize=100)

        with patch('haminfo.mqtt.thread.CONF') as mock_conf:
            mock_conf.mqtt.host_ip = 'localhost'
            mock_conf.mqtt.host_port = 1883
            mock_conf.mqtt.user = None
            mock_conf.mqtt.topic = 'test/topic'

            with patch.object(MQTTThread, '_connect'):
                all_queues = aprs_queues + [weather_queue]
                mqtt_thread = MQTTThread(all_queues, stats, stats_lock)

        # All 100 packets should go to the single APRS queue
        for i in range(100):
            aprs_queue = mqtt_thread.aprs_queues[mqtt_thread.rr_index % len(mqtt_thread.aprs_queues)]
            mqtt_thread.rr_index += 1
            aprs_queue.put_nowait(f'packet_{i}')

        assert aprs_queues[0].qsize() == 100
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_parallel_mqtt_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Update spec with rollback note**

Add to `docs/superpowers/specs/2026-03-27-parallel-mqtt-consumers-design.md` after the "Expected Results" section:

```markdown
## Rollback

To restore single-threaded behavior, set `processor_count=1` in your config:

```ini
[mqtt]
processor_count = 1
```

This immediately reverts to the original single-processor architecture.
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_parallel_mqtt_integration.py docs/superpowers/specs/2026-03-27-parallel-mqtt-consumers-design.md
git commit -m "test: add integration tests for parallel MQTT processing

Verifies:
- Even distribution of packets across N processors
- processor_count=1 matches original single-threaded behavior

Also adds rollback documentation to the spec.

Completes: parallel MQTT consumers feature"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
pytest tests/ -v
```

- [ ] **Run linter**

```bash
ruff check haminfo/conf/mqtt.py haminfo/mqtt/thread.py haminfo/cmds/mqtt_ingest.py
```

- [ ] **Manual smoke test** (optional)

```bash
# Start with default processor_count=4
haminfo wx-mqtt-ingest -c haminfo.conf

# Verify in logs: "Starting 4 parallel APRS packet processor threads"
# Verify 4 separate "Starting APRSPacketProcessorThread-N" messages
```
