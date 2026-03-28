//! High-performance MQTT APRS packet ingest service for haminfo.
//!
//! This service subscribes to an MQTT topic (typically APRS packets from APRSD),
//! parses the JSON packets, and bulk-inserts them into PostgreSQL.
//!
//! Features:
//! - Async I/O with tokio for maximum throughput
//! - Batch inserts for efficient database writes
//! - Configurable via file or environment variables
//! - Graceful shutdown handling
//! - Statistics reporting

mod config;
mod db;
mod mqtt;
mod packet;
mod stats;

use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::Parser;
use tokio::signal;
use tokio::sync::mpsc;
use tracing::{error, info, warn};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::Settings;
use crate::db::Database;
use crate::mqtt::{MqttClient, MqttMessage};
use crate::packet::{AprsPacket, AprsPacketJson};
use crate::stats::{start_stats_reporter, Stats};

/// MQTT APRS packet ingest service
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Path to configuration file
    #[arg(short, long)]
    config: Option<String>,

    /// Enable stats-only mode (no database writes)
    #[arg(long)]
    stats_only: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing/logging
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "mqtt_ingest=info".into()),
        ))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let args = Args::parse();

    info!("Starting MQTT ingest service");

    // Load configuration
    let mut settings = Settings::new(args.config.as_deref())?;

    // Override stats_only from CLI if provided
    if args.stats_only {
        settings.ingest.stats_only = true;
    }

    if settings.ingest.stats_only {
        warn!("Running in STATS-ONLY mode - no database writes will occur!");
    }

    // Initialize statistics
    let stats = Arc::new(Stats::new());

    // Start stats reporter
    let _stats_handle = start_stats_reporter(Arc::clone(&stats), settings.ingest.stats_interval_secs);

    // Initialize database connection (unless stats-only mode)
    let db = if settings.ingest.stats_only {
        None
    } else {
        Some(Database::new(&settings.database).await?)
    };

    // Create MQTT client
    let mut mqtt_client = MqttClient::new(&settings.mqtt)?;

    // Create message channel
    let (tx, rx) = mpsc::channel::<MqttMessage>(10000);

    // Subscribe to topic
    mqtt_client.subscribe().await?;

    // Spawn packet processor
    let processor_stats = Arc::clone(&stats);
    let batch_size = settings.ingest.batch_size;
    let batch_timeout = Duration::from_millis(settings.ingest.batch_timeout_ms);
    let stats_only = settings.ingest.stats_only;

    let processor_handle = tokio::spawn(async move {
        process_packets(rx, db, processor_stats, batch_size, batch_timeout, stats_only).await
    });

    // Spawn MQTT client
    let mqtt_handle = tokio::spawn(async move {
        if let Err(e) = mqtt_client.run(tx).await {
            error!("MQTT client error: {:?}", e);
        }
    });

    // Wait for shutdown signal
    info!("Press Ctrl+C to stop");
    signal::ctrl_c().await?;
    info!("Shutdown signal received");

    // Print final stats
    let final_stats = stats.snapshot();
    info!("Final stats: {}", final_stats);

    // Cleanup
    mqtt_handle.abort();
    processor_handle.abort();

    info!("Shutdown complete");
    Ok(())
}

/// Process incoming MQTT messages and batch-insert to database.
async fn process_packets(
    mut rx: mpsc::Receiver<MqttMessage>,
    db: Option<Database>,
    stats: Arc<Stats>,
    batch_size: usize,
    batch_timeout: Duration,
    stats_only: bool,
) {
    let mut batch: Vec<AprsPacket> = Vec::with_capacity(batch_size);
    let mut last_flush = Instant::now();

    loop {
        // Use timeout to ensure we flush periodically even with low traffic
        let msg = tokio::time::timeout(batch_timeout, rx.recv()).await;

        match msg {
            Ok(Some(message)) => {
                stats.inc_received();

                // Parse JSON
                match serde_json::from_slice::<AprsPacketJson>(&message.payload) {
                    Ok(json) => {
                        if let Some(packet) = AprsPacket::from_json(json) {
                            stats.inc_parsed();
                            batch.push(packet);
                        } else {
                            stats.inc_failed();
                            // Log first few failures for debugging
                            if stats.packets_failed.load(std::sync::atomic::Ordering::Relaxed) <= 3 {
                                warn!("Packet missing from_call: {:?}", String::from_utf8_lossy(&message.payload));
                            }
                        }
                    }
                    Err(e) => {
                        stats.inc_failed();
                        // Log first few failures for debugging
                        if stats.packets_failed.load(std::sync::atomic::Ordering::Relaxed) <= 3 {
                            warn!("Failed to parse JSON: {:?} - payload: {:?}", e, String::from_utf8_lossy(&message.payload));
                        }
                    }
                }
            }
            Ok(None) => {
                // Channel closed
                info!("Message channel closed, flushing remaining packets");
                if !batch.is_empty() && !stats_only {
                    if let Some(ref db) = db {
                        flush_batch(&mut batch, db, &stats).await;
                    }
                }
                break;
            }
            Err(_) => {
                // Timeout - flush if we have pending packets
            }
        }

        // Flush batch if full or timeout exceeded
        let should_flush = batch.len() >= batch_size || last_flush.elapsed() >= batch_timeout;
        if should_flush && !batch.is_empty() {
            if stats_only {
                // In stats-only mode, just count and discard
                let count = batch.len() as u64;
                stats.add_inserted(count);
                stats.inc_batch();
                batch.clear();
            } else if let Some(ref db) = db {
                flush_batch(&mut batch, db, &stats).await;
            }
            last_flush = Instant::now();
        }
    }
}

/// Flush a batch of packets to the database.
async fn flush_batch(batch: &mut Vec<AprsPacket>, db: &Database, stats: &Stats) {
    let batch_len = batch.len();
    match db.insert_batch(batch).await {
        Ok(inserted) => {
            stats.add_inserted(inserted as u64);
            stats.add_duplicate((batch_len - inserted) as u64);
            stats.inc_batch();
        }
        Err(e) => {
            error!("Failed to insert batch: {:?}", e);
        }
    }
    batch.clear();
}
