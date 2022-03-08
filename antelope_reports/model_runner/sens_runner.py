from .scenario_runner import ScenarioRunner, frag_flow_lcia
from collections import defaultdict


class SensitivityRunner(ScenarioRunner):
    def __init__(self, model, *common_scenarios, sens_hi=None, sens_lo=None, **kwargs):
        super(SensitivityRunner, self).__init__(model, *common_scenarios, **kwargs)

        self._results_hi = dict()
        self._results_lo = dict()

        self._traversals_hi = dict()
        self._traversals_lo = dict()

        self._sens_hi = self._scenario_tuple(sens_hi)
        self._sens_lo = self._scenario_tuple(sens_lo)

    def add_hi_sense(self, param):
        self._sens_hi += self._scenario_tuple(param)
        for case in self.scenarios:
            self._traverse_hi(case)

    def add_lo_sense(self, param):
        self._sens_lo += self._scenario_tuple(param)
        for case in self.scenarios:
            self._traverse_lo(case)

    def _traverse_hi(self, case):
        sc = self._params[case]
        sc_apply = sc + tuple(self.common_scenarios)

        sc_hi = sc_apply + self._sens_hi
        self._traversals_hi[case] = self._model.traverse(scenario=sc_hi)

    def _traverse_lo(self, case):
        sc = self._params[case]
        sc_apply = sc + tuple(self.common_scenarios)

        sc_lo = sc_apply + self._sens_lo
        self._traversals_lo[case] = self._model.traverse(scenario=sc_lo)

    def _traverse_case(self, case):
        print('traversing %s' % case)
        sc = self._params[case]
        sc_apply = sc + tuple(self.common_scenarios)
        self._traversals[case] = list(self._model.traverse(sc_apply))

        if self._sens_hi:
            self._traverse_hi(case)

        if self._sens_lo:
            self._traverse_lo(case)

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        sc = self._params[scenario]
        sc_apply = sc + tuple(self.common_scenarios)

        res = frag_flow_lcia(self._traversals[scenario], lcia, scenario=sc_apply, **kwargs)

        if self._sens_hi:
            sc_hi = sc_apply + self._sens_hi
            self._results_hi[scenario, lcia] = frag_flow_lcia(self._traversals_hi[scenario], lcia, scenario=sc_hi, **kwargs)
        else:
            self._results_hi[scenario, lcia] = res

        if self._sens_lo:
            sc_lo = sc_apply + self._sens_lo
            self._results_lo[scenario, lcia] = frag_flow_lcia(self._traversals_lo[scenario], lcia, scenario=sc_lo, **kwargs)
        else:
            self._results_lo[scenario, lcia] = res

        return res

    sens_order = ('result', 'result_lo', 'result_hi')

    def sens_result(self, scenario, lcia_method):
        return (self._results[scenario, lcia_method],
                self._results_lo[scenario, lcia_method],
                self._results_hi[scenario, lcia_method])

    results_headings = ('scenario', 'stage', 'method', 'category', 'indicator', 'result', 'result_lo', 'result_hi', 'units')

    def _gen_aggregated_lcia_rows(self, scenario, q, include_total=False):
        """
        This is really complicated because we don't know (or don't want to assume) that the three scores will have
        the same stages-- because low and hi scenarios could trigger different traversals / terminations.
        maybe this is paranoid.
        it certainly makes the code look like hell.
        the code makes an open ended dict of stages, with a subdict of result, result_lo, result_hi
        these get populated only when encountered, and output only when present.
        :param scenario:
        :param q:
        :param include_total:
        :return:
        """

        ress = [k.aggregate(key=self._agg) for k in self.sens_result(scenario, q)]
        keys = defaultdict(dict)
        for i, res in enumerate(ress):
            for c in res.components():
                keys[c.entity][self.sens_order[i]] = c.cumulative_result

        for stage, result in sorted(keys.items(), key=lambda x: x[0]):
            d = {
                'scenario': str(scenario),
                'stage': stage,
                'result': None,
                'result_lo': None,
                'result_hi': None
            }
            for k, v in result.items():
                d[k] = self._format(v)

            yield self._gen_row(q, d)
        if include_total:
            dt = {
                'scenario': str(scenario),
                'stage': 'Net Total'
            }
            for i, k in enumerate(ress):
                dt[self.sens_order[i]] = k.total()

            yield self._gen_row(q, dt)
