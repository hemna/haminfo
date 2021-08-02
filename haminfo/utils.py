import asyncio
import contextlib
import json
import os
import random
import traceback
import yaspin
import colorsys
from pathlib import Path
from logging import NullHandler
import logging as py_logging

from oslo_config import cfg
from oslo_log import log as logging


CONF = cfg.CONF
DOMAIN = "haminfo"
home = str(Path.home())
DEFAULT_CONFIG_DIR = "{}/.config/haminfo/".format(home)
DEFAULT_CONFIG_FILE = "{}/.config/haminfo/haminfo.conf".format(home)

LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

# create from
# http://www.arrl.org/band-plan
FREQ_BAND_PLAN = {
    "160m": {"desc": "160 Meters (1.8-2.0 MHz)", "low": 1.8, "high": 2.0},
    "80m": {"desc": "80 Meters (3.5-4.0 MHz)", "low": 3.5, "high": 4.0},
    "60m": {"desc": "60 Meters (5 MHz channels)", "low": 5.0, "high": 5.9},
    "40m": {"desc": "40 Meters (7.0 - 7.3 MHz)", "low": 7.0, "high": 7.3},
    "30m": {"desc": "30 Meters(10.1 - 10.15 MHz)", "low": 10.1, "high": 10.15},
    "20m": {"desc": "20 Meters(14.0 - 14.35 MHz)", "low": 14.0, "high": 14.35},
    "17m": {"desc": "17 Meters(18.068 - 18.168 MHz)", "low": 18.068, "high": 18.168},
    "15m": {"desc": "15 Meters(21.0 - 21.45 MHz)", "low": 21.0, "high": 21.45},
    "12m": {"desc": "12 Meters(24.89 - 24.99 MHz)", "low": 24.89, "high": 24.99},
    "10m": {"desc": "10 Meters(28 - 29.7 MHz)", "low": 28.0, "high": 29.7},
    "6m": {"desc": "6 Meters(50 - 54 MHz)", "low": 50.0, "high": 54.0},
    "2m": {"desc": "2 Meters(144 - 148 MHz)", "low": 144.0, "high": 148.0},
    "1.25m": {"desc": "1.25 Meters(222 - 225 MHz)", "low": 222.0, "high": 225.0},
    "70cm": {"desc": "70 Centimeters(420 - 450 MHz)", "low": 420.0, "high": 450},
    "33cm": {"desc": "33 Centimeters(902 - 928 MHz)", "low": 902.0, "high": 928},
    "23cm": {"desc": "23 Centimeters(1240 - 1300 MHz)", "low": 1240.0, "high": 1300.0},
    "13cm": {"desc": "13 Centimeters(2300 - 2310 and 2390 - 2450 MHz)", "low": 2300.0, "high": 2450.0},
    "9cm": {"desc": "9 centimeters(3300-3500 MHz)", "low": 3300.0, "high": 3500.0},
    "5cm": {"desc": "5 Centimeters(5650.0 - 5925.0 MHz)", "low": 5650.0, "high": 5290.0},
    "3cm": {"desc": "3 Centimeters(10000.000 - 10500.000 MHz )", "low": 10000.0, "high": 10500.0}
}


def setup_logging():
    """Prepare Oslo Logging (2 or 3 steps)

    Use of Oslo Logging involves the following:

    * logging.register_options
    * logging.set_defaults (optional)
    * logging.setup
    """


    # Optional step to set new defaults if necessary for
    # * logging_context_format_string
    # * default_log_levels
    #
    # These variables default to respectively:
    #
    #  import oslo_log
    #  oslo_log._options.DEFAULT_LOG_LEVELS
    #  oslo_log._options.log_opts[0].default
    #
    existing = logging.get_default_log_levels()
    print("Default log levels {}".format(existing))

    extra_log_level_defaults = [
        'haminfo=WARN',
        'sqlalchemy=FATAL',
        'sqlalchemy.engine.Engine=FATAL',
        'oslo.messaging=WARN',
        'oslo_messaging=WARN',
        'haminfo=DEBUG',
        ]
    new = []

    exist_dict = {}
    for entry in existing:
        e_arr = entry.split('=')
        exist_dict[e_arr[0]] = e_arr[1]

    for entry in extra_log_level_defaults:
        e_arr = entry.split('=')
        exist_dict[e_arr[0]] = e_arr[1]

    for key in exist_dict:
        new.append("{}={}".format(key, exist_dict[key]))

    #print("NEW ? {}".format(new))

    logging.set_defaults(default_log_levels=new)
    #print("NEW Default log levels {}".format(logging.get_default_log_levels()))

    # Required step to register common, logging and generic configuration
    # variables
    logging.setup(CONF, DOMAIN)


def degrees_to_cardinal(degrees):
    dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    ix = round(degrees / (360. / len(dirs)))
    return dirs[ix % len(dirs)]


def frequency_band_mhz(freq):
    """Convert frequency in hz to Band length.

       Created from: http://www.arrl.org/band-plan
    """
    print("Look for {}".format(freq))
    for band in FREQ_BAND_PLAN:
        if (freq > FREQ_BAND_PLAN[band]["low"] and
                freq < FREQ_BAND_PLAN[band]["high"]):
            print("found band {}".format(band))
            return band


class Spinner:
    enabled = True
    random = True

    random_spinners = [
        'dots', 'line', 'growVertical', 'circleHalves',
        'toggle', 'arrow3', 'bouncingBar', 'bouncingBall',
        'pong', 'shark', 'weather', 'dots12', 'moon',
    ]

    @classmethod
    def get(cls, *args, **kwargs):
        if cls.enabled:
            if len(args) < 1:  # second positional arg is text
                kwargs.setdefault("text", "Spinning up...")
            sp = yaspin.yaspin(*args, **kwargs)
            if cls.random:
                sp = getattr(sp, random.choice(cls.random_spinners))
            return sp
        else:
            return DummySpinner()

    @classmethod
    def verify_spinners_present(cls, name):
        y = yaspin.yaspin()
        for spinner in cls.random_spinners:
            if not hasattr(y, spinner):
                raise RuntimeError('Random spinner "{}" missing from yaspin'.format(spinner))


class DummySpinner:
    def __init__(self, *args, **kwargs):
        self.text = ''

    def write(self, *args, **kwargs):
        print(*args, **kwargs)

    def __getattr__(self, name):
        return self

    def __call__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return False

    @contextlib.contextmanager
    def hidden(self):
        yield


class SpinnerProxy:
    """Spinner-like class for parallel running threads

    This class either directly sets/calls its parent's `.text` or `write()`
    if `is_current` is set or keeps the lines written around to output them
    once `is_current` is set or and outside entity uses `flush()`.

    When `prefix` is set, setting `text` on the spinner will get this
    prefix.
    """
    def __init__(self, parent_spinner, prefix=None):
        self._sp = parent_spinner
        self._prefix = prefix
        self.is_current = False

        self._lines = []
        self._text = ''

    def write(self, data):
        if self.is_current:
            self.flush()
            self._sp.write(data)
        else:
            self._lines.append(data)

    def flush(self):
        if self._lines:
            self._sp.write('\n'.join(self._lines))
            self._lines = []

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if self.is_current:
            if self._prefix:
                self._sp.text = '{}: {}'.format(self._prefix, value)
            else:
                self._sp.text = value
        self._text = value


def prettify_json(data, autoindent=False):
    from pygments import highlight
    from pygments.lexers import JsonLexer
    from pygments.formatters import TerminalFormatter

    if autoindent:
        data = json.dumps(json.loads(data), indent=4, sort_keys=True)

    return highlight(data, JsonLexer(), TerminalFormatter())


def hsl_to_rgb(hsl):
    """Convert hsl colorspace values to RGB."""
    # Convert hsl to 0-1 ranges.
    h = hsl[0] / 359.
    s = hsl[1] / 100.
    l = hsl[2] / 100.
    hsl = (h, s, l)
    # returns numbers between 0 and 1
    tmp = colorsys.hls_to_rgb(h, s, l)
    # convert to 0 to 255
    r = int(round(tmp[0] * 255))
    g = int(round(tmp[1] * 255))
    b = int(round(tmp[2] * 255))
    return (r, g, b)


# ping an rgb tuple based on percent.
# clip shifts the color space towards the
# clip percentage
def pick_color(percent, clip, saturation, start, end):
    """Pick an rgb color based on % value.

    Clip can shift the color gradient towards the clip value.
    Valid clip values are 0-100.
    Saturation (0-100) is how bright the range of colors are.
    start = start hue value.  (0 = red, 120 = green)
    end = end hue value.  (0 = red, 120 = green)
    """
    a = 0 if (percent <= clip) else (((percent - clip) / (100 - clip)))
    b = abs(end - start) * a
    c = (start + b) if (end > start) else (start - b)

    h = int(round(c))
    s = int(saturation)
    return hsl_to_rgb((h, 50, s))


def alert_percent_color(percent, start=0, end=120):
    """Return rgb color based on % value.

    This is a wrapper function for pick_color, with clipping
    set to 0, and saturation set to 100%.

    By default the colors range from Red at 0% to
    Green at 100%.   If you want the colors to invert
    then set start=120, end=0.  The start and end values
    are hue.  Green is 120 hue.
    """
    return pick_color(percent, 0, 100, start, end)
