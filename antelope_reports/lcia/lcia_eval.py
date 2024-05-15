"""
lcia_eval.py

Generate information about consistency and completeness of LCI and LCIA methods.
"""
from antelope import ExchangeRef


class LciaEval(object):
    """
    The way this works is: we create two lists. One, of processes; the other, of LCIA methods.
    When we add a process to the list, we create a *unit mask* which has the same exchanges as the process's
    LCI, but all with unit magnitudes.  Then we create a "negative sort" which is initialized with all the contents of
    the unit mask.  Every time we add an LCIA method, we intersect the negative sort with the zeros of the resulting
    computation.  After all the lcia methods are added, what remains in the negative sort is the un-matched exchanges.
    Then we can look at those lists and decide what to do.
    """

    def __init__(self, unit_mask=False):
        self._rxs = []
        self._methods = []
        self._factors = dict()

        self._unit_mask = bool(unit_mask)
        self._lci = dict()  # maps process link to list of exchanges
        self._negative_sort = dict()  # maps process link to set of zero exchanges
        self._run = dict()

    def _run_lcia(self, rx, refresh=None):
        if len(self._methods):
            print('Running LCIA for %s' % rx.process.link)
        for q in self._methods:
            if (rx, q.link) in self._run:
                continue
            print(' -- LCIA %s: ' % q.link, end='')
            if rx.entity_type == 'fragment':
                res = rx.fragment_lcia(q, refresh=refresh).flatten()
            else:
                res = q.do_lcia(self._lci[rx], refresh=refresh)

            deets = list(res.details())
            print('%d hits, %d zeros; ' % (len(deets), len(list(res.zeros()))), end='')
            self._negative_sort[rx] &= set(res.zeros())
            print('%d remain' % len(self._negative_sort[rx]))
            self._run[rx, q.link] = res

    def _show_line(self, method, num=False):
        print('%30.30s ' % method.name, end='')
        for rx in self._rxs:
            if num:
                print(' %8.3g  ' % self._run[rx, method.link].total(), end='')
            else:
                print(' %8d  ' % len(list(self._run[rx, method.link].details())), end='')
        # I hate myself for taking the time to do this right now
        d = '  (%d)        ' % len(self._factors[method.link])
        print('%10.10s %s' % (d, method['Indicator'], ))

    def show(self, data=True):
        """
        damn he's really doing it
        :param data: True: report LCIA scores. False: report counts
        :return:
        """
        print('%30.30s ' % '', end='')
        for i in range(len(self._rxs)):
            print('   [%02d]     ' % i, end='')
        print()
        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('%-10.10s ' % p.process.origin, end='')
        print()
        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('%10.10s ' % p.process.name, end='')
        print()
        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('%10.10s ' % p.flow.name, end='')
        print()
        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('[%8.8s] ' % p.flow.unit, end='')
        print()

        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('   %5d   ' % len(self._lci[p]), end='')
        print()

        for k in self._methods:
            self._show_line(k, num=data)

        print('%30.30s ' % '', end='')
        for p in self._rxs:
            print('   %5d   ' % len(self._negative_sort[p]), end='')
        print()

    def recompute(self):
        self._run = dict()
        self._run_lcia_for_all_processes(refresh=True)

    def _run_lcia_for_all_processes(self, refresh=None):
        for p in self._rxs:
            self._run_lcia(p, refresh=refresh)

    def add_process(self, *rx_or_processes):
        for rx_or_p in rx_or_processes:
            if rx_or_p.entity_type == 'fragment':
                process = rx_or_p
                ios, internal = process.unit_flows()
                io = ios[0]
                rx = ExchangeRef(process, io.fragment.flow, io.fragment.direction, value=io.magnitude, is_reference=True)
                lci = [ExchangeRef(process, k.fragment.flow, k.fragment.direction, value=k.magnitude,
                                   termination=k.term.term_node) for k in internal if k.term.is_context]
            else:
                if rx_or_p.entity_type == 'process':
                    process = rx_or_p
                    rx = rx_or_p.reference()
                else:
                    rx = rx_or_p
                    process = rx.process

                if rx in self._rxs:
                    raise ValueError('Process already added')

                lci = list(process.lci(ref_flow=rx.flow))

            if self._unit_mask:
                # create a false inventory with 1 for everything
                lci = [ExchangeRef(x.process, x.flow, x.direction, value=1.0, termination=x.termination) for x in lci]
            self._lci[rx] = lci
            self._negative_sort[rx] = set(lci)
            self._rxs.append(rx)
            print('Adding Process %s: %d exchanges' % (process.link, len(set(lci))))
            self._run_lcia(rx)

    def add_lcia(self, *lcias):
        for lcia in lcias:
            if lcia in self._methods:
                raise ValueError('LCIA method already added')

            self._methods.append(lcia)
            self._factors[lcia.link] = list(lcia.factors())

            self._run_lcia_for_all_processes()

    '''
    Now, what outputs do we want?
    
    Flowables- we want to see all the flowables present, all the ones hit, all the ones missed
    make a table? lcia method by row, process by column- count hits, misses
    ultimately, though, we need to be curating flowables.   
    
    {we need an online qdb, is what we need}
    
    so this should be a tool for generating inputs to a curator- even if it is interactive- because how long would 
    it really take to clear the non-matched of 5100 flows? at 1 minute apiece that's like 2weeks of work.
    
    that's not what we would do though- we would load EXISTING lists of known syllables and then just mop up 
    the entries with only k terms, where k = 1, 2, ...
    we have all those lists from Rebe
    
    
    '''

