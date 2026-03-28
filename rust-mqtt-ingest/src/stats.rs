//! Statistics tracking for ingest performance.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::time::interval;
use tracing::info;

/// Thread-safe statistics counter.
#[derive(Debug)]
pub struct Stats {
    /// Total packets received from MQTT
    pub packets_received: AtomicU64,
    /// Packets successfully parsed
    pub packets_parsed: AtomicU64,
    /// Packets that failed to parse
    pub packets_failed: AtomicU64,
    /// Packets inserted into database
    pub packets_inserted: AtomicU64,
    /// Packets skipped as duplicates
    pub packets_duplicate: AtomicU64,
    /// Batch insert operations
    pub batch_inserts: AtomicU64,
    /// Start time for rate calculation
    start_time: Instant,
}

impl Stats {
    /// Create a new stats tracker.
    pub fn new() -> Self {
        Self {
            packets_received: AtomicU64::new(0),
            packets_parsed: AtomicU64::new(0),
            packets_failed: AtomicU64::new(0),
            packets_inserted: AtomicU64::new(0),
            packets_duplicate: AtomicU64::new(0),
            batch_inserts: AtomicU64::new(0),
            start_time: Instant::now(),
        }
    }

    /// Increment packets received counter.
    #[inline]
    pub fn inc_received(&self) {
        self.packets_received.fetch_add(1, Ordering::Relaxed);
    }

    /// Increment packets parsed counter.
    #[inline]
    pub fn inc_parsed(&self) {
        self.packets_parsed.fetch_add(1, Ordering::Relaxed);
    }

    /// Increment packets failed counter.
    #[inline]
    pub fn inc_failed(&self) {
        self.packets_failed.fetch_add(1, Ordering::Relaxed);
    }

    /// Add to packets inserted counter.
    #[inline]
    pub fn add_inserted(&self, count: u64) {
        self.packets_inserted.fetch_add(count, Ordering::Relaxed);
    }

    /// Add to duplicates counter.
    #[inline]
    pub fn add_duplicate(&self, count: u64) {
        self.packets_duplicate.fetch_add(count, Ordering::Relaxed);
    }

    /// Increment batch insert counter.
    #[inline]
    pub fn inc_batch(&self) {
        self.batch_inserts.fetch_add(1, Ordering::Relaxed);
    }

    /// Get current statistics snapshot.
    pub fn snapshot(&self) -> StatsSnapshot {
        let elapsed = self.start_time.elapsed();
        let received = self.packets_received.load(Ordering::Relaxed);
        let parsed = self.packets_parsed.load(Ordering::Relaxed);
        let inserted = self.packets_inserted.load(Ordering::Relaxed);

        StatsSnapshot {
            packets_received: received,
            packets_parsed: parsed,
            packets_failed: self.packets_failed.load(Ordering::Relaxed),
            packets_inserted: inserted,
            packets_duplicate: self.packets_duplicate.load(Ordering::Relaxed),
            batch_inserts: self.batch_inserts.load(Ordering::Relaxed),
            elapsed_secs: elapsed.as_secs_f64(),
            received_rate: if elapsed.as_secs() > 0 {
                received as f64 / elapsed.as_secs_f64()
            } else {
                0.0
            },
            insert_rate: if elapsed.as_secs() > 0 {
                inserted as f64 / elapsed.as_secs_f64()
            } else {
                0.0
            },
        }
    }

    /// Reset all counters (keeps start_time).
    pub fn reset(&self) {
        self.packets_received.store(0, Ordering::Relaxed);
        self.packets_parsed.store(0, Ordering::Relaxed);
        self.packets_failed.store(0, Ordering::Relaxed);
        self.packets_inserted.store(0, Ordering::Relaxed);
        self.packets_duplicate.store(0, Ordering::Relaxed);
        self.batch_inserts.store(0, Ordering::Relaxed);
    }
}

/// Point-in-time statistics snapshot.
#[derive(Debug, Clone)]
pub struct StatsSnapshot {
    pub packets_received: u64,
    pub packets_parsed: u64,
    pub packets_failed: u64,
    pub packets_inserted: u64,
    pub packets_duplicate: u64,
    pub batch_inserts: u64,
    pub elapsed_secs: f64,
    pub received_rate: f64,
    pub insert_rate: f64,
}

impl std::fmt::Display for StatsSnapshot {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "recv={} parsed={} failed={} inserted={} dup={} batches={} | rate: {:.1} pps recv, {:.1} pps insert",
            self.packets_received,
            self.packets_parsed,
            self.packets_failed,
            self.packets_inserted,
            self.packets_duplicate,
            self.batch_inserts,
            self.received_rate,
            self.insert_rate,
        )
    }
}

/// Start a background task that periodically logs statistics.
pub fn start_stats_reporter(stats: Arc<Stats>, interval_secs: u64) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut ticker = interval(Duration::from_secs(interval_secs));
        ticker.tick().await; // Skip first immediate tick

        loop {
            ticker.tick().await;
            let snapshot = stats.snapshot();
            info!("Stats: {}", snapshot);
        }
    })
}
