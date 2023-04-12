import datetime
import logging
import time
import tracemalloc

from oslo_config import cfg

from haminfo.threads import MyThread, MyThreadList
from haminfo import utils


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)


class KeepAliveThread(MyThread):
    cntr = 0
    checker_time = datetime.datetime.now()

    def __init__(self):
        tracemalloc.start()
        super().__init__("KeepAlive")
        max_timeout = {"hours": 0.0, "minutes": 2, "seconds": 0}
        self.max_delta = datetime.timedelta(**max_timeout)

    def loop(self):
        if self.cntr % 60 == 0:
            thread_list = MyThreadList()
            now = datetime.datetime.now()

            current, peak = tracemalloc.get_traced_memory()
            keepalive = (
                "{} - {}"
            ).format(
                CONF.mqtt.host_ip,
                len(thread_list),
            )
            LOG.info(keepalive)
            thread_out = []
            for thread in thread_list.threads_list:
                alive = thread.is_alive()
                thread_out.append(f"{thread.__class__.__name__}:{alive}")
                if not alive:
                    LOG.error(f"Thread {thread}")
            LOG.info(",".join(thread_out))

            # Check version every day
            delta = now - self.checker_time
            if delta > datetime.timedelta(hours=24):
                self.checker_time = now
        self.cntr += 1
        time.sleep(1)
        return True
