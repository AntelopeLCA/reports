from .charts import ModelGraph
from .observer import QuickAndEasy, MissingValue

from time import time


class DumbTimer(object):
    """
    a centralized timer
    """
    def __init__(self, head='==', tail=None):
        self.t0 = time()
        self.head = head
        self.tail = tail or ''

    @property
    def _t(self):
        return time() - self.t0

    @property
    def _ts(self):
        return '(%5.2f s)' % self._t

    def format(self, string):
        return '%s%s %s%s' % (self.head, self._ts, string, self.tail)

    def check(self, string):
        print(self.format(string))
