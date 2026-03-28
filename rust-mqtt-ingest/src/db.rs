//! Database module for PostgreSQL operations.

use anyhow::Result;
use sqlx::postgres::{PgPool, PgPoolOptions};
use tracing::{debug, info, instrument};

use crate::config::DatabaseConfig;
use crate::packet::AprsPacket;

/// Database connection pool wrapper.
pub struct Database {
    pool: PgPool,
}

impl Database {
    /// Create a new database connection pool.
    #[instrument(skip(config))]
    pub async fn new(config: &DatabaseConfig) -> Result<Self> {
        info!("Connecting to PostgreSQL...");

        let pool = PgPoolOptions::new()
            .max_connections(config.max_connections)
            .min_connections(config.min_connections)
            .connect(&config.url)
            .await?;

        info!("Connected to PostgreSQL");
        Ok(Self { pool })
    }

    /// Insert a batch of APRS packets using bulk insert.
    ///
    /// Uses ON CONFLICT DO NOTHING since (from_call, timestamp) is the primary key.
    /// This handles duplicate packets gracefully.
    #[instrument(skip(self, packets), fields(batch_size = packets.len()))]
    pub async fn insert_batch(&self, packets: &[AprsPacket]) -> Result<usize> {
        if packets.is_empty() {
            return Ok(0);
        }

        // Build the bulk insert query
        // We use unnest() for efficient bulk inserts in PostgreSQL
        let mut from_calls: Vec<&str> = Vec::with_capacity(packets.len());
        let mut to_calls: Vec<Option<&str>> = Vec::with_capacity(packets.len());
        let mut paths: Vec<Option<&str>> = Vec::with_capacity(packets.len());
        let mut timestamps: Vec<chrono::NaiveDateTime> = Vec::with_capacity(packets.len());
        let mut received_ats: Vec<chrono::NaiveDateTime> = Vec::with_capacity(packets.len());
        let mut raws: Vec<&str> = Vec::with_capacity(packets.len());
        let mut packet_types: Vec<Option<&str>> = Vec::with_capacity(packets.len());
        let mut latitudes: Vec<Option<f64>> = Vec::with_capacity(packets.len());
        let mut longitudes: Vec<Option<f64>> = Vec::with_capacity(packets.len());
        let mut altitudes: Vec<Option<f64>> = Vec::with_capacity(packets.len());
        let mut courses: Vec<Option<i16>> = Vec::with_capacity(packets.len());
        let mut speeds: Vec<Option<f64>> = Vec::with_capacity(packets.len());
        let mut symbols: Vec<Option<String>> = Vec::with_capacity(packets.len());
        let mut symbol_tables: Vec<Option<String>> = Vec::with_capacity(packets.len());
        let mut comments: Vec<Option<&str>> = Vec::with_capacity(packets.len());
        let mut locations: Vec<Option<String>> = Vec::with_capacity(packets.len());

        for packet in packets {
            from_calls.push(&packet.from_call);
            to_calls.push(packet.to_call.as_deref());
            paths.push(packet.path.as_deref());
            timestamps.push(packet.timestamp);
            received_ats.push(packet.received_at);
            raws.push(&packet.raw);
            packet_types.push(packet.packet_type.as_deref());
            latitudes.push(packet.latitude);
            longitudes.push(packet.longitude);
            altitudes.push(packet.altitude);
            courses.push(packet.course);
            speeds.push(packet.speed);
            symbols.push(packet.symbol.map(|c| c.to_string()));
            symbol_tables.push(packet.symbol_table.map(|c| c.to_string()));
            comments.push(packet.comment.as_deref());
            locations.push(packet.location_wkt());
        }

        // Use a single INSERT with unnest for bulk efficiency
        // Convert WKT text to PostGIS geography using ST_GeogFromText
        let result = sqlx::query(
            r#"
            INSERT INTO aprs_packet (
                from_call, to_call, path, timestamp, received_at, raw, packet_type,
                latitude, longitude, altitude, course, speed, symbol, symbol_table,
                comment, location
            )
            SELECT
                from_call, to_call, path, timestamp, received_at, raw, packet_type,
                latitude, longitude, altitude, course, speed, symbol, symbol_table,
                comment,
                CASE WHEN location_wkt IS NOT NULL 
                     THEN ST_GeogFromText(location_wkt) 
                     ELSE NULL 
                END
            FROM UNNEST(
                $1::text[], $2::text[], $3::text[], $4::timestamp[], $5::timestamp[],
                $6::text[], $7::text[], $8::float8[], $9::float8[], $10::float8[],
                $11::int2[], $12::float8[], $13::char[], $14::char[], $15::text[],
                $16::text[]
            ) AS t(
                from_call, to_call, path, timestamp, received_at, raw, packet_type,
                latitude, longitude, altitude, course, speed, symbol, symbol_table,
                comment, location_wkt
            )
            ON CONFLICT (from_call, timestamp) DO NOTHING
            "#,
        )
        .bind(&from_calls)
        .bind(&to_calls)
        .bind(&paths)
        .bind(&timestamps)
        .bind(&received_ats)
        .bind(&raws)
        .bind(&packet_types)
        .bind(&latitudes)
        .bind(&longitudes)
        .bind(&altitudes)
        .bind(&courses)
        .bind(&speeds)
        .bind(&symbols)
        .bind(&symbol_tables)
        .bind(&comments)
        .bind(&locations)
        .execute(&self.pool)
        .await?;

        let inserted = result.rows_affected() as usize;
        debug!(
            "Inserted {} of {} packets (duplicates skipped)",
            inserted,
            packets.len()
        );

        Ok(inserted)
    }

    /// Check database connectivity.
    pub async fn ping(&self) -> Result<()> {
        sqlx::query("SELECT 1").execute(&self.pool).await?;
        Ok(())
    }

    /// Close the database connection pool.
    pub async fn close(&self) {
        self.pool.close().await;
    }
}

#[cfg(test)]
mod tests {
    // Database tests would require a test database
    // Skip for now - tested via integration tests
}
