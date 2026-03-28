//! Configuration module for MQTT ingest service.

use config::{Config, ConfigError, Environment, File};
use serde::Deserialize;

/// Main configuration structure
#[derive(Debug, Deserialize, Clone)]
pub struct Settings {
    pub mqtt: MqttConfig,
    pub database: DatabaseConfig,
    pub ingest: IngestConfig,
}

/// MQTT broker configuration
#[derive(Debug, Deserialize, Clone)]
pub struct MqttConfig {
    /// MQTT broker host
    pub host: String,
    /// MQTT broker port
    #[serde(default = "default_mqtt_port")]
    pub port: u16,
    /// MQTT client ID
    #[serde(default = "default_client_id")]
    pub client_id: String,
    /// Topic to subscribe to
    pub topic: String,
    /// QoS level (0, 1, or 2)
    #[serde(default = "default_qos")]
    pub qos: u8,
    /// Username for authentication
    pub username: Option<String>,
    /// Password for authentication
    pub password: Option<String>,
}

/// Database configuration
#[derive(Debug, Deserialize, Clone)]
pub struct DatabaseConfig {
    /// PostgreSQL connection URL
    pub url: String,
    /// Maximum number of connections in pool
    #[serde(default = "default_max_connections")]
    pub max_connections: u32,
    /// Minimum number of connections in pool
    #[serde(default = "default_min_connections")]
    pub min_connections: u32,
}

/// Ingest behavior configuration
#[derive(Debug, Deserialize, Clone)]
pub struct IngestConfig {
    /// Batch size for bulk inserts
    #[serde(default = "default_batch_size")]
    pub batch_size: usize,
    /// Maximum time to wait before flushing batch (milliseconds)
    #[serde(default = "default_batch_timeout_ms")]
    pub batch_timeout_ms: u64,
    /// Stats reporting interval (seconds)
    #[serde(default = "default_stats_interval")]
    pub stats_interval_secs: u64,
    /// Stats-only mode (skip DB writes, just count packets)
    #[serde(default)]
    pub stats_only: bool,
}

fn default_mqtt_port() -> u16 {
    1883
}

fn default_client_id() -> String {
    format!("mqtt-ingest-{}", std::process::id())
}

fn default_qos() -> u8 {
    0
}

fn default_max_connections() -> u32 {
    10
}

fn default_min_connections() -> u32 {
    2
}

fn default_batch_size() -> usize {
    500
}

fn default_batch_timeout_ms() -> u64 {
    1000
}

fn default_stats_interval() -> u64 {
    10
}

impl Settings {
    /// Load configuration from file and environment variables.
    ///
    /// Configuration sources (in order of precedence):
    /// 1. Environment variables (prefixed with MQTT_INGEST_)
    /// 2. Config file (config.toml or specified via --config)
    /// 3. Default values
    pub fn new(config_path: Option<&str>) -> Result<Self, ConfigError> {
        let mut builder = Config::builder();

        // Add config file if specified or use default
        if let Some(path) = config_path {
            builder = builder.add_source(File::with_name(path));
        } else {
            // Try to load config.toml from current directory
            builder = builder.add_source(File::with_name("config").required(false));
        }

        // Add environment variables with prefix MQTT_INGEST_
        // e.g., MQTT_INGEST_MQTT__HOST becomes mqtt.host
        builder = builder.add_source(
            Environment::with_prefix("MQTT_INGEST")
                .separator("__")
                .try_parsing(true),
        );

        let config = builder.build()?;
        config.try_deserialize()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_values() {
        assert_eq!(default_mqtt_port(), 1883);
        assert_eq!(default_qos(), 0);
        assert_eq!(default_batch_size(), 500);
    }
}
