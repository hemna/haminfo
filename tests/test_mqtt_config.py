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
