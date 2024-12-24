import pandas as pd

from .components_mixin import ComponentsMixin
from .lca_model_runner import LcaModelRunner

from antelope_foreground.fragment_flows import group_ios, ios_exchanges, frag_flow_lcia

from functools import reduce


class ScenarioRunner(ComponentsMixin, LcaModelRunner):
    """
    This runs a single model (fragment), applying a set of different scenario specifications. 
    """
    def _scenario_tuple(self, arg):
        """
        Translates None, strings, or tuples into tuples. should return a flat (non-nested) tuple
        check out all the work being done by that one comma
        :param arg:
        :return:
        """
        if arg:
            if isinstance(arg, tuple):
                return tuple(reduce(lambda a, b: a+b, (self._scenario_tuple(k) for k in arg)))
            else:
                return arg,
        return ()

    def __init__(self, model, *common_scenarios, **kwargs):
        """

        :param kwargs: agg_key, default is lambda x: x['StageName']
        """
        super(ScenarioRunner, self).__init__(**kwargs)

        self._common_scenarios = set()

        self._model = model
        self._traversals = dict()

        self._params = dict()

        for scenario in common_scenarios:
            self.add_common_scenario(scenario)

    @property
    def model(self):
        return self._model

    def params(self, scenario):
        return self._params[scenario]

    def add_common_scenario(self, scenario):
        if isinstance(scenario, tuple):
            for sc in scenario:
                self._common_scenarios.add(sc)
        else:
            self._common_scenarios.add(scenario)
        self.recalculate()

    def remove_common_scenario(self, scenario):
        self._common_scenarios.remove(scenario)
        self.recalculate()

    def traverse_all(self):
        for case in self.scenarios:
            self._traverse_case(case)

    def _traverse_case(self, case):
        print('traversing %s' % case)
        sc = self._params[case]
        sc_apply = sc + tuple(self.common_scenarios)
        self._traversals[case] = list(self._model.traverse(sc_apply))

    def _recalculate_case(self, case, **kwargs):
        self._traverse_case(case)
        for q in self.lcia_methods:
            self.run_lcia_case_method(case, q, **kwargs)
        for w in self.weightings:
            self._run_case_weighting(case, w)

    def add_case_param(self, case, param):
        if case not in self._params:
            raise KeyError('Unknown case %s' % case)
        assert isinstance(param, str)
        if param in self._params[case]:
            print('Param %s already in case %s' % (param, case))
        else:
            self._params[case] += (param, )
        self._recalculate_case(case)

    def remove_case_param(self, case, param):
        if case not in self._params:
            raise KeyError('Unknown case %s' % case)
        assert isinstance(param, str)
        if param not in self._params[case]:
            raise ValueError('Param %s not in case %s' % (param, case))
        else:
            self._params[case] = tuple(filter(lambda x: x != param, self._params[case]))
        self._recalculate_case(case)

    @property
    def common_scenarios(self):
        for k in sorted(self._common_scenarios):
            yield k

    def add_case(self, case, *params):
        self.add_scenario(case)  # raises KeyError
        self._params[case] = self._scenario_tuple(params)
        self._recalculate_case(case)

    def fragment_flows(self, scenario):
        return self._traversals[scenario]

    def cutoffs(self, scenario, **kwargs):
        ios, _ = group_ios(self._model, self._traversals[scenario], **kwargs)
        return ios_exchanges(ios, ref=self._model)

    def cutoffs_dataframe(self, include_activity=True):
        def _cutoffs_row(k, sc):
            return {'Case': sc, 'Cutoff': k.flow.name, 'Direction': k.direction, 'Magnitude': k.value,
                    'Unit': k.unit}
        if include_activity:
            return pd.DataFrame([_cutoffs_row(k, s) for s in self.scenarios for k in self.cutoffs(s)])
        else:
            return pd.DataFrame([_cutoffs_row(k, s) for s in self.scenarios for k in self.cutoffs(s)
                                 if k.unit != 'activity'])

    def activity(self, scenario):
        """
        should think about some more generalized 'activity' query, a la antelope_foreground.terminal_nodes
        :param scenario:
        :return:
        """
        return [f for f in self._traversals[scenario] if f.fragment.top() is self._model]

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        sc = self._params[scenario]
        sc_apply = sc + tuple(self.common_scenarios)
        return frag_flow_lcia(self._traversals[scenario], lcia, scenario=sc_apply, **kwargs)


