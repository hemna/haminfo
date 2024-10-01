import logging

from oslo_config import cfg



mqtt_group = cfg.OptGroup(
    name="mqtt",
    title="MQTT Options for injesting wx packets from aprsd",
)


mqtt_opts = [
    cfg.StrOpt('host_ip',
               default='0.0.0.0',
               help='The hostname/ip address to listen on'
               ),
    cfg.IntOpt('host_port',
               default=80,
               help='The port to listen on for requests'
               ),
    cfg.StrOpt('user',
               default=None,
               help='The mqtt username to use'
               ),
    cfg.StrOpt('password',
               default=None,
               help="the mqtt password"),
    cfg.StrOpt('topic',
               default="aprs/weather",
               help="The MQTT Topic to subscribe for messages"),
    cfg.StrOpt('keepalive_file',
               default='/tmp/haminfo_mqtt_keepalive.json',
               help="The keepalive thread's file to update.")
]


def register_opts(config):
    config.register_opts(mqtt_opts, group=mqtt_group)


def list_opts():
    return {
        mqtt_group.name: mqtt_opts
    }
