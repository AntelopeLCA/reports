

class FlowComparator(object):
    """
    A tool for comparing the overlap and difference between different families of flows.
    Use cases: LCIA indicators; archives

    usage:
    > fc = FlowComparator(cat)
    > fc.sort_flowables(q1, q2)

    where q1, q2 are queries: could be quantities, archives, or lists of fragments or exchanges
    maps each item's flows to recognized flowables
    returns 3 sets: flowables unique to q1, common to both, unique to q2
    records: terms encountered in queries that are not recognized flowables

    """

    def __init__(self, tm):
        self._tm = tm
        self._unknown_flows = dict()

    def _lcia_get_flowable(self, _flowable, _origin):
        if _origin not in self._unknown_flows:
            self._unknown_flows[_origin] = set()
        try:
            return self._tm.get_flowable(_flowable)
        except KeyError:
            self._unknown_flows[_origin].add(_flowable)
            return _flowable

    def _map_item(self, item):
        """

        :param item:
        :return:
        """
        if hasattr(item, 'entity_type'):
            if item.entity_type == 'characterization':
                fb = item.flowable
                og = item.origin
            elif item.entity_type == 'exchange':
                fb = item.flow.name
                og = item.flow.origin
            elif item.entity_type == 'flow':
                fb = item.name
                og = item.origin
            elif item.entity_type == 'fragment':
                fb = item.flow.name
                og = item.origin
            else:
                raise TypeError(item)
        else:
            fb = str(item)
            og = None
        return fb, self._lcia_get_flowable(fb, og)

    def distinct_flowables(self, _q):
        if hasattr(_q, 'factors'):
            fs = (self._map_item(k) for k in _q.factors())
            _n = _q.name
        elif hasattr(_q, 'flows'):
            fs = (self._map_item(k) for k in _q.flows())
            if hasattr(_q, 'origin'):
                _n = _q.origin
            elif hasattr(_q, 'ref'):
                _n = _q.ref
            else:
                _n = _q.__class__.__name__
        else:
            fs = (self._map_item(k) for k in _q)
            _n = _q.__class__.__name__

        ff, ss = zip(*fs)
        bb = set(ss)

        print('%s: %d factors; %d names; %d flowables' % (_n, len(ff), len(set(ff)), len(bb)))

        return bb

    def sort_flowables(self, _q1, _q2):
        """
        returns lcia-engine flowables in 3 sets: distinct to _q1, common to both, distinct to _q2

        Three steps:
         - secure list of items
         - map items to strings (flagging unrecognized strings
         - map strings to flowables
        """

        _s1 = self.distinct_flowables(_q1)
        _s2 = self.distinct_flowables(_q2)
        _u = _s1.intersection(_s2)
        _d1 = _s1.difference(_u)
        _d2 = _s2.difference(_u)
        print('only a: %d ,common: %d , only b: %d' % (len(_d1), len(_u), len(_d2)))
        return _d1, _u, _d2

    @property
    def seen_origins(self):
        return list(self._unknown_flows.keys())

    def unknown_flowables(self, origin):
        return sorted(self._unknown_flows.get(origin, []))
