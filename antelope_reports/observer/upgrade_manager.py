"""
The purpose of an upgrade manager is to migrate nodes in a foreground ('kit') from one origin to another.
We can imagine a number of different use cases:

 - USLCI: same process, different origin
 - ecoinvent: same flow, with geographically differentiated targets
 - ecoinvent-TO-other: requires a mapping service (this is actually qdb, I think)

for now we will use subclassing
"""
from antelope import enum, MultipleReferences, NoReference  # is this *always* an interactive tool?
from antelope_foreground.models import Anchor


class NoCandidates(Exception):
    pass


class TooManyCandidates(Exception):
    pass


class UpgradeManager(object):
    """
    foreground query
    source origin
    target query

    """
    _strategy = 'match_name_and_spatial_scope'

    _strategies = ('match_name_and_spatial_scope',
                   'match_name',
                   'same_id',
                   'targets',
                   'node_targets')

    def __init__(self, fg, origin, query, scenario=None, to_scenario=None, strategy=None, autoskip=False):
        """

        :param fg: foreground query that contains the nodes to be upgraded
        :param origin:
        :param query:
        :param scenario: [None] scenario to revise; "from" scenario
        :param to_scenario: scenario name to use during observation. 'None' will not be accepted if scenario is also
        None-- specify 'default' if you want to overwrite the default scenario
        :param strategy:
        :param autoskp: [False] If True, skip entries that have already been observed under to_scenario
        """
        self._fg = fg
        self._src = origin
        self._q = query
        self._scenario = scenario
        self._to_scenario = to_scenario
        self._autoskip = autoskip

        self._nodes = tuple(n for n in self._fg.nodes(origin=self._src) if n.scenario == scenario)
        self._pending = list(range(len(self._nodes)))
        self._working = None  # stores the INDEX into the node being reviewed
        self._rxs = ()  # chosen candidate's rx
        self._rx = None  # stores the selected termination
        self._candidates = None
        self._exception = None
        self._completed = [False] * len(self._nodes)
        self._error = [None] * len(self._nodes)

        self.strategy = strategy

        self.next()

    @property
    def strategy(self):
        return self._strategy

    @strategy.setter
    def strategy(self, value):
        if value is not None:
            if value in self._strategies:
                print('setting strategy "%s"' % value)
                self._strategy = value

    @property
    def nodes(self):
        for n in self._nodes:
            yield n

    def nodes_for(self, fragment_ref):
        for n in self._nodes:
            if n.node.entity_id == fragment_ref:
                yield n

    def is_pending(self, x):
        return x in self._pending

    def is_completed(self, x):
        return bool(self._completed[x])

    def error(self, x):
        return self._error[x]

    def next(self, x=None):
        if self._working and self._exception:
            self._error[self._working] = self._exception
        self._working = None

        self._candidates = self._exception = self._rx = self._rxs = None
        self._working = self._find_next(x)
        if self._working is None:
            print('Queue has been exhausted')
            return
        print('Next up: %d: %s -# %s' % (self._working, self.current.node.name, self.current.anchor.name))

    def _find_next(self, x=None):
        rtn = None
        while rtn is None:
            if x is None:
                try:
                    rtn = self._pending[0]
                except IndexError:
                    return
            else:
                if x not in self._pending:
                    raise IndexError
                rtn = x
                x = None

            if self._to_scenario is not None:
                if self._to_scenario in self._nodes[rtn].node.scenarios(recurse=False):
                    term = self._nodes[rtn].node.termination(self._to_scenario)
                    if self._autoskip:
                        print('%d: Skipping observed entry (%s: %s)' % (rtn, self._to_scenario, term.term_node))
                        self._pending.remove(rtn)
                        rtn = None
                    else:
                        print('Current [%s] already observed as: %s' % (self._to_scenario,
                                                                        term.term_node))
        return rtn

    @property
    def rx(self):
        if self._rx is None:
            self.pick()
        return self._rx

    @property
    def completed(self):
        for i, n in enumerate(self._nodes):
            if self._completed[i]:
                yield n

    @property
    def errored(self):
        for i, n in enumerate(self._nodes):
            if bool(self._error[i]):
                yield n

    @property
    def current(self):
        if self._working is not None:
            return self._nodes[self._working]

    def candidates(self):
        if self._candidates:
            enum(self._candidates)

    """
    different upgrade strategies
    """
    def match_name(self):
        """
        Match the name of the current anchor
        :return:
        """
        return self._q.processes(name='^%s$' % self.current.anchor.term_node['name'])

    def match_name_and_spatial_scope(self):
        """
        Match the name and spatial scope of the current anchor
        :return:
        """
        return self._q.processes(name='^%s$' % self.current.anchor.term_node['name'],
                                 spatialscope='^%s$' % self.current.anchor.term_node['spatialscope'])

    def same_id(self):
        """
        Retrieve the process with the same external_ref from a different query
        :return:
        """
        return [self._q.get(self.current.anchor.term_node.external_ref)]

    def targets(self):
        """
        Retrieve targets that match the current anchor (flow and direction)
        :return:
        """
        return self._q.targets(self.current.anchor.term_flow, direction=self.current.anchor.direction)

    def node_targets(self):
        """
        Retrieve targets that match the current node (flow, disregarding direction)
        :return:
        """
        return self._q.targets(self.current.node.flow)

    def _run_attempt(self, strategy):
        """
        :return:
        """
        if strategy is None:
            strategy = self.strategy
        self._candidates = enum(getattr(self, strategy)())

    def attempt(self, x=None, strategy=None):
        if x:
            self.next(x)
        try:
            self._run_attempt(strategy)  # populates _candidates
            if len(self._candidates) > 0:
                return True
            print('NoCandidates')
            self._exception = NoCandidates()
            return False
        except Exception as e:
            self._exception = e
            print(e)
            return False

    def rxs(self, n=0):
        return self._candidates[n].references()

    def pick(self, n=0, ref_flow=None):
        """
        subclass: process with ambiguous ref
        :param n:
        :param ref_flow:
        :return:
        """
        self._rxs = tuple(self._candidates[n].references())
        try:
            self._rx = self._candidates[n].reference(ref_flow)  # if ref flow is None and len(rx) is 1, will return it
        except MultipleReferences as m:
            if ref_flow is None:
                try:
                    self._rx = self._candidates[n].reference(self.current.anchor.term_flow)
                    return
                except NoReference:
                    pass
            raise m
        except NoReference:
            raise

    def pick_rx(self, k=0):
        if self._rxs is None:
            self.pick()
        self._rx = self._rxs[k]

    def observe_current_node(self, to_scenario=None, descend=None, **kwargs):
        """
        The specified candidate is chosen. moves the identified working node from pending into completed.
        :param to_scenario: if None, self._scenario is used for the observation. If self._scenario is None, a scenario must
        be provided. Use 'default' if the observation is intended to reset the default anchor (i.e. scenario=None)
        :param descend: specified in anchor. if None, the branch's current anchor is used
        :param kwargs: passed to fg.observe()
        :return:
        """
        if self._candidates is None:
            if self.attempt() is False:
                raise self._exception
        if self._rx is None:
            self.pick()
        if descend is None:
            descend = self.current.anchor.descend
        if to_scenario is None:
            if self._scenario is None and self._to_scenario is None:
                raise ValueError("supply 'default' if you want to rewrite the default scenario")
            to_scenario = self._to_scenario

        try:
            print("observing %s" % self.rx)
            self._fg.observe(self.current.node, scenario=to_scenario,
                             anchor_node=self.rx.process, anchor_flow=self.rx.flow, descend=descend, **kwargs)
            self.finish()

        except Exception as e:
            self._exception = e
            print(e)
            return False

        return True

    def finish(self):
        self._completed[self._working] = True
        self._pending.remove(self._working)
        self.next()

    def skip(self):
        """
        Remove from pending list without marking complete
        :return:
        """
        self._pending.remove(self._working)
        self.next()

    def fail(self):
        """
        remove from
        :return:
        """
        self._completed[self._working] = False
        self._pending.remove(self._working)
        self.next()

    def run(self, to_scenario=None, descend=None, **kwargs):
        while len(self._pending) > 0:
            if self.attempt():
                if len(self._candidates) > 1:
                    self._exception = TooManyCandidates()
                    self.fail()
                else:
                    if self.observe_current_node(to_scenario=to_scenario, descend=descend, **kwargs):
                        pass
                    else:
                        self.fail()
            else:
                self.fail()
        print('%d success\n%d fail' % (sum(self._completed), len(list(self.errored))))

    def reset_pending(self):
        self._pending = [k for k in range(len(self._nodes)) if not self.is_completed(k)]
