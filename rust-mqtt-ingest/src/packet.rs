//! APRS packet model matching the Python APRSPacket schema.

use chrono::{DateTime, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};

/// APRS packet structure matching the haminfo database schema.
///
/// Primary key is (from_call, timestamp) for TimescaleDB hypertable.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AprsPacket {
    /// Source callsign (max 9 chars)
    pub from_call: String,
    /// Destination callsign (max 9 chars)
    pub to_call: Option<String>,
    /// Digipeater path (max 100 chars)
    pub path: Option<String>,
    /// Packet timestamp
    pub timestamp: NaiveDateTime,
    /// When the packet was received by this system
    pub received_at: NaiveDateTime,
    /// Raw packet string
    pub raw: String,
    /// Packet type (position, weather, message, etc.)
    pub packet_type: Option<String>,
    /// Latitude in decimal degrees
    pub latitude: Option<f64>,
    /// Longitude in decimal degrees
    pub longitude: Option<f64>,
    /// Altitude in meters
    pub altitude: Option<f64>,
    /// Course in degrees (0-360)
    pub course: Option<i16>,
    /// Speed in knots
    pub speed: Option<f64>,
    /// APRS symbol character
    pub symbol: Option<char>,
    /// APRS symbol table character
    pub symbol_table: Option<char>,
    /// Comment text
    pub comment: Option<String>,
}

/// Raw APRS packet JSON as received from MQTT (APRSD format).
/// Note: MQTT sends "from"/"to" but database uses "from_call"/"to_call"
#[derive(Debug, Deserialize)]
pub struct AprsPacketJson {
    /// Source callsign - MQTT uses "from", we also accept "from_call"
    #[serde(alias = "from")]
    pub from_call: Option<String>,
    /// Destination callsign - MQTT uses "to", we also accept "to_call"
    #[serde(alias = "to")]
    pub to_call: Option<String>,
    pub path: Option<PathValue>,
    pub timestamp: Option<TimestampValue>,
    pub raw: Option<String>,
    pub packet_type: Option<String>,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub altitude: Option<f64>,
    pub course: Option<f64>, // Can be float in some packets, we'll convert to i16
    pub speed: Option<f64>,
    pub symbol: Option<String>,
    pub symbol_table: Option<String>,
    pub comment: Option<String>,
    // Weather fields (for type detection)
    pub temperature: Option<f64>,
    pub humidity: Option<f64>,
    pub pressure: Option<f64>,
    // Other fields for type detection
    pub telemetry_analog: Option<serde_json::Value>,
    pub telemetry_digital: Option<serde_json::Value>,
    pub object_name: Option<String>,
    pub message_text: Option<String>,
    pub status: Option<String>,
    pub query_type: Option<String>,
}

/// Path can be either a string or array of strings
#[derive(Debug, Deserialize)]
#[serde(untagged)]
pub enum PathValue {
    String(String),
    Array(Vec<String>),
}

/// Timestamp can be either a number (unix timestamp) or ISO string
#[derive(Debug, Deserialize)]
#[serde(untagged)]
pub enum TimestampValue {
    Number(f64),
    String(String),
}

impl AprsPacket {
    /// Create an AprsPacket from JSON data (APRSD packet format).
    pub fn from_json(json: AprsPacketJson) -> Option<Self> {
        // from_call is required
        let from_call = json.from_call.as_ref()?.replace('\0', "");
        if from_call.is_empty() {
            return None;
        }

        // Truncate to max length
        let from_call = truncate(&from_call, 9);

        let to_call = json.to_call.map(|s| truncate(&s.replace('\0', ""), 9));

        let path = match json.path {
            Some(PathValue::String(s)) => Some(truncate(&s.replace('\0', ""), 100)),
            Some(PathValue::Array(arr)) => Some(truncate(&arr.join(","), 100)),
            None => None,
        };

        // Parse timestamp
        let timestamp = match json.timestamp {
            Some(TimestampValue::Number(ts)) => {
                DateTime::from_timestamp(ts as i64, ((ts.fract()) * 1_000_000_000.0) as u32)
                    .map(|dt| dt.naive_utc())
                    .unwrap_or_else(|| Utc::now().naive_utc())
            }
            Some(TimestampValue::String(s)) => {
                NaiveDateTime::parse_from_str(&s, "%Y-%m-%dT%H:%M:%S%.f")
                    .or_else(|_| NaiveDateTime::parse_from_str(&s, "%Y-%m-%dT%H:%M:%S"))
                    .unwrap_or_else(|_| Utc::now().naive_utc())
            }
            None => Utc::now().naive_utc(),
        };

        let raw = json.raw.unwrap_or_default().replace('\0', "");

        // Determine packet type
        let packet_type = json.packet_type.or_else(|| {
            if json.temperature.is_some() || json.humidity.is_some() || json.pressure.is_some() {
                Some("weather".to_string())
            } else if json.telemetry_analog.is_some() || json.telemetry_digital.is_some() {
                Some("telemetry".to_string())
            } else if json.object_name.is_some() {
                Some("object".to_string())
            } else if json.message_text.is_some() {
                Some("message".to_string())
            } else if json.status.is_some() {
                Some("status".to_string())
            } else if json.query_type.is_some() {
                Some("query".to_string())
            } else if json.latitude.is_some() && json.longitude.is_some() {
                Some("position".to_string())
            } else {
                Some("unknown".to_string())
            }
        });

        // Extract symbol (first char only)
        let symbol = json
            .symbol
            .as_ref()
            .and_then(|s| s.replace('\0', "").chars().next());

        let symbol_table = json
            .symbol_table
            .as_ref()
            .and_then(|s| s.replace('\0', "").chars().next());

        let comment = json.comment.map(|s| s.replace('\0', ""));

        Some(AprsPacket {
            from_call,
            to_call,
            path,
            timestamp,
            received_at: Utc::now().naive_utc(),
            raw,
            packet_type,
            latitude: json.latitude,
            longitude: json.longitude,
            altitude: json.altitude,
            course: json.course.map(|c| c as i16), // Convert f64 to i16
            speed: json.speed,
            symbol,
            symbol_table,
            comment,
        })
    }

    /// Generate PostGIS POINT WKT for location if lat/lon are present.
    pub fn location_wkt(&self) -> Option<String> {
        match (self.latitude, self.longitude) {
            (Some(lat), Some(lon)) => Some(format!("POINT({} {})", lon, lat)),
            _ => None,
        }
    }
}

/// Truncate a string to max_len characters.
fn truncate(s: &str, max_len: usize) -> String {
    s.chars().take(max_len).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_from_json_basic() {
        let json_str = r#"{
            "from_call": "N0CALL",
            "to_call": "APRS",
            "raw": "N0CALL>APRS:test",
            "latitude": 40.0,
            "longitude": -105.0
        }"#;

        let json: AprsPacketJson = serde_json::from_str(json_str).unwrap();
        let packet = AprsPacket::from_json(json).unwrap();

        assert_eq!(packet.from_call, "N0CALL");
        assert_eq!(packet.to_call, Some("APRS".to_string()));
        assert_eq!(packet.packet_type, Some("position".to_string()));
        assert_eq!(packet.location_wkt(), Some("POINT(-105 40)".to_string()));
    }

    #[test]
    fn test_from_json_missing_from_call() {
        let json_str = r#"{"to_call": "APRS"}"#;
        let json: AprsPacketJson = serde_json::from_str(json_str).unwrap();
        assert!(AprsPacket::from_json(json).is_none());
    }

    #[test]
    fn test_path_array() {
        let json_str = r#"{
            "from_call": "N0CALL",
            "path": ["WIDE1-1", "WIDE2-2"]
        }"#;

        let json: AprsPacketJson = serde_json::from_str(json_str).unwrap();
        let packet = AprsPacket::from_json(json).unwrap();

        assert_eq!(packet.path, Some("WIDE1-1,WIDE2-2".to_string()));
    }
}
