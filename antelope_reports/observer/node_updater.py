"""
The Upgrade Manager is a bit too heavy-handed and it violates some good design principles.

This tool is meant to perform an update of a single node in a few different ways.
"""
from antelope import enum, MultipleReferences, NoReference  # is this *always* an interactive tool?


class NodeUpgraderException(Exception):
    pass


class NoCandidates(NodeUpgraderException):
    pass


class TooManyCandidates(NodeUpgraderException):
    pass


# need to escape regex-active characters
nonregexp = str.maketrans('()[]\\/*', '.......')


class NodeUpdater:
    _strategy = 'match_name_and_spatial_scope'

    _strategies = ('match_name_and_spatial_scope',
                   'match_name',
                   'same_id',
                   'targets',
                   'targets_match_spatial_scope',
                   'node_targets')

    @property
    def strategy(self):
        return self._strategy

    @strategy.setter
    def strategy(self, value):
        if value is not None:
            if value in self._strategies:
                print('setting strategy "%s"' % value)
                self._strategy = value
            else:
                print('ignoring unrecognized strategy "%s"' % value)

    def __init__(self, branch, query, strategy=None):
        """
        This accepts a single FragmentBranch, which includes a node (FragmentRef) and an anchor (Anchor), with
        a scenario name.  This branch is SUPPOSED to represent an existing termination.
        :param branch:
        :param query: used to obtain upgrade targets
        """
        self._branch = branch
        self._q = query
        self.strategy = strategy
        self._candidates = self._exception = self._rx = self._rxs = None

    @property
    def current(self):
        return self._branch

    """
    different upgrade strategies
    """
    def match_name(self):
        """
        Match the name of the current anchor
        :return:
        """
        name = '^%s$' % self.current.anchor.term_node['name'].translate(nonregexp)
        return self._q.processes(name='^%s$' % name)

    def match_name_and_spatial_scope(self):
        """
        Match the name and spatial scope of the current anchor
        :return:
        """
        name = '^%s$' % self.current.anchor.term_node['name'].translate(nonregexp)
        return self._q.processes(name='^%s$' % name,
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
        return self._q.targets(self.current.anchor.term_flow.external_ref, direction=self.current.node.direction)

    def targets_match_spatial_scope(self):
        """
        Retrieve targets that match the current anchor (flow and direction), filter by current anchor's spatial scope
        :return:
        """
        return filter(lambda x: x['spatialscope'] == self.current.anchor.term_node['spatialscope'],
                      self._q.targets(self.current.anchor.term_flow.external_ref, direction=self.current.node.direction)
                      )

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
        if len(self._candidates) == 0:
            raise NoCandidates

    def attempt(self):
        self._run_attempt(self.strategy)

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

    def upgrade(self, n=None, apply_scenario=None):
        """
        Attempts to apply the currently selected
        :param n: which of the current candidates to select
        :param apply_scenario: must be specified.  To run the upgrade in-place (i.e. same scenario as
        observed branch), specify 'in place. To upgrade the default node (i.e. scenario=None), specify 'default'
        :return:
        """
        if n is None:
            if self._rx is None:
                if self._candidates is None:
                    self.attempt()
                if len(self._candidates) > 1:
                    raise TooManyCandidates()
                elif len(self._candidates) == 0:
                    raise NoCandidates()
                else:
                    n = 0
                self.pick(n)
        else:
            self.pick(n)

        if self._branch.scenario is None:
            if apply_scenario is None:
                raise ValueError('Must specify "default" to overwrite default scenario')
            elif apply_scenario == 'default':
                _apply_scenario = None
            else:
                _apply_scenario = apply_scenario
        else:
            if apply_scenario is None:
                raise ValueError('must specify "in place" to overwrite current scenario %s or'
                                 ' "default" to set default scenario' % self._branch.scenario)
            elif apply_scenario == 'in place':
                _apply_scenario = self._branch.scenario
            elif apply_scenario == 'default':
                _apply_scenario = None
            else:
                _apply_scenario = apply_scenario

        print('%s => %s [%s]' % (self._branch.node, self._rx.process, _apply_scenario))
        self._branch.node.clear_termination(_apply_scenario)
        self._branch.node.terminate(self._rx.process, scenario=_apply_scenario,
                                    term_flow=self._rx.flow, descend=self._branch.anchor.descend)
