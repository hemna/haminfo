import datetime
import json
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

    def __init__(self):
        tracemalloc.start()
        super().__init__("KeepAlive")
        max_timeout = {"hours": 0.0, "minutes": 2, "seconds": 0}
        self.max_delta = datetime.timedelta(**max_timeout)
        self.data = {'update_at': str(datetime.datetime.now())}
        self._dump_keepalive()

    def _dump_keepalive(self):
        try:
            fp = open(CONF.mqtt.keepalive_file, "w+")
            json.dump(self.data, fp)
            fp.close()
        except Exception as ex:
            LOG.error(f"Failed to write keepalive file {str(ex)}")

    def loop(self):
        if self.cntr % 60 == 0:
            thread_list = MyThreadList()

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
                thread_name = thread.__class__.__name__
                alive = thread.is_alive()
                self.data[thread_name] = alive
                thread_out.append(f"{thread.__class__.__name__}:{alive}")
                if not alive:
                    LOG.error(f"Thread {thread}")
            LOG.info(",".join(thread_out))

        self.cntr += 1
        # every 5 minutes
        if self.cntr % 300 == 0:
            # update the keepalive file
            self._dump_keepalive()
        time.sleep(1)
        return True
