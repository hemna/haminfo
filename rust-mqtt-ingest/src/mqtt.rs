//! MQTT client module.

use anyhow::Result;
use rumqttc::{AsyncClient, Event, EventLoop, MqttOptions, Packet, QoS};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, error, info, instrument, warn};

use crate::config::MqttConfig;

/// MQTT message received from broker.
#[derive(Debug)]
pub struct MqttMessage {
    pub topic: String,
    pub payload: Vec<u8>,
}

/// MQTT client wrapper.
pub struct MqttClient {
    client: AsyncClient,
    eventloop: EventLoop,
    topic: String,
    qos: QoS,
}

impl MqttClient {
    /// Create a new MQTT client.
    #[instrument(skip(config))]
    pub fn new(config: &MqttConfig) -> Result<Self> {
        let mut options = MqttOptions::new(&config.client_id, &config.host, config.port);
        options.set_keep_alive(Duration::from_secs(30));

        // Set credentials if provided
        if let (Some(user), Some(pass)) = (&config.username, &config.password) {
            options.set_credentials(user, pass);
        }

        // Set reasonable defaults for high-throughput
        options.set_clean_session(true);
        options.set_max_packet_size(1024 * 1024, 1024 * 1024); // 1MB max packet

        let (client, eventloop) = AsyncClient::new(options, 10000);

        let qos = match config.qos {
            0 => QoS::AtMostOnce,
            1 => QoS::AtLeastOnce,
            2 => QoS::ExactlyOnce,
            _ => QoS::AtMostOnce,
        };

        info!(
            "MQTT client configured: {}:{} topic={}",
            config.host, config.port, config.topic
        );

        Ok(Self {
            client,
            eventloop,
            topic: config.topic.clone(),
            qos,
        })
    }

    /// Subscribe to the configured topic and start receiving messages.
    ///
    /// Returns a channel receiver for incoming messages.
    #[instrument(skip(self))]
    pub async fn subscribe(&mut self) -> Result<()> {
        self.client.subscribe(&self.topic, self.qos).await?;
        info!("Subscribed to topic: {}", self.topic);
        Ok(())
    }

    /// Run the event loop and send messages to the provided channel.
    ///
    /// This method runs until an error occurs or the client is disconnected.
    #[instrument(skip(self, tx))]
    pub async fn run(&mut self, tx: mpsc::Sender<MqttMessage>) -> Result<()> {
        info!("Starting MQTT event loop");

        loop {
            match self.eventloop.poll().await {
                Ok(Event::Incoming(Packet::Publish(publish))) => {
                    let msg = MqttMessage {
                        topic: publish.topic.clone(),
                        payload: publish.payload.to_vec(),
                    };

                    if tx.send(msg).await.is_err() {
                        warn!("Message channel closed, stopping MQTT client");
                        break;
                    }
                }
                Ok(Event::Incoming(Packet::ConnAck(_))) => {
                    info!("Connected to MQTT broker");
                }
                Ok(Event::Incoming(Packet::SubAck(_))) => {
                    info!("Subscription acknowledged");
                }
                Ok(Event::Incoming(Packet::PingResp)) => {
                    debug!("Ping response received");
                }
                Ok(Event::Outgoing(_)) => {
                    // Outgoing events - usually just pings
                }
                Ok(event) => {
                    debug!("MQTT event: {:?}", event);
                }
                Err(e) => {
                    error!("MQTT error: {:?}", e);
                    // Try to reconnect after a brief delay
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }

        Ok(())
    }
}
