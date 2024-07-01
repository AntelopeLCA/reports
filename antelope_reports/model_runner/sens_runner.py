from .scenario_runner import ScenarioRunner
from antelope_foreground.fragment_flows import group_ios, ios_exchanges, frag_flow_lcia

from collections import defaultdict


class SensitivityRunner(ScenarioRunner):
    @classmethod
    def run_lca(cls, model, qs, *common, agg_key=None, sens_hi=None, sens_lo=None,
                hi_sense=None, lo_sense=None, **scenarios):
        """
        "Do everything" classmethod for running an LCA study based on a unitary model.
        Prior to calling this: all scenarios must be properly prepared (parameters and terminations observed)

        WHEN calling this, the two required positional arguments are: the model (fragment) and an iterable of LCIA
        methods (quantities or quantity refs).

        Optional positional parameters are common scenarios to be added to all cases

        sens_hi and sens_lo (synonyms: hi_sense and lo_sense) are optional tuples of scenario specifications for
        high- and low-sensitivity test cases, respectively.  These will not get run if they are omitted.

        Finally, the scenarios themselves are supplied as kwarg: tuple. At least one must be supplied, even if it
        has None value, because otherwise the runner won't know what to name the default scenario.
        :param model:
        :param qs:
        :param common:
        :param agg_key:
        :param sens_hi:
        :param sens_lo:
        :param hi_sense: synonym for sens_hi
        :param lo_sense: synonym for sens_lo
        :param scenarios:
        :return:
        """
        run = cls(model, *common, agg_key=agg_key, sens_hi=sens_hi or hi_sense, sens_lo=sens_lo or lo_sense)
        for k, v in scenarios.items():
            run.add_case(k, v)

        for q in qs:
            run.run_lcia(q)

        return run

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

    def inventory_hi(self, scenario, **kwargs):
        ios, _ = group_ios(self._model, self._traversals_hi[scenario], **kwargs)
        return ios_exchanges(ios, ref=self._model)

    def inventory_lo(self, scenario, **kwargs):
        ios, _ = group_ios(self._model, self._traversals_lo[scenario], **kwargs)
        return ios_exchanges(ios, ref=self._model)

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        sc = self._params[scenario]
        sc_apply = sc + tuple(self.common_scenarios)

        res = frag_flow_lcia(self._traversals[scenario], lcia, scenario=sc_apply, **kwargs)

        if self._sens_hi:
            sc_hi = sc_apply + self._sens_hi
            res_hi = frag_flow_lcia(self._traversals_hi[scenario], lcia, scenario=sc_hi, **kwargs)
        else:
            res_hi = res

        if self._sens_lo:
            sc_lo = sc_apply + self._sens_lo
            res_lo = frag_flow_lcia(self._traversals_lo[scenario], lcia, scenario=sc_lo, **kwargs)
        else:
            res_lo = res

        self._results_lo[scenario, lcia] = min([res, res_lo, res_hi], key=lambda x: x.total())
        self._results_hi[scenario, lcia] = max([res, res_lo, res_hi], key=lambda x: x.total())

        return res

    sens_order = ('result', 'result_lo', 'result_hi')

    def sens_result(self, scenario, lcia_method):
        return (self._results[scenario, lcia_method],
                self._results_lo[scenario, lcia_method],
                self._results_hi[scenario, lcia_method])

    @property
    def results_headings(self):
        return ['scenario', 'stage', 'alt_stage', 'method', 'category', 'indicator', 'result', 'result_lo', 'result_hi', 'units']

    def _gen_lcia_rows(self, scenario, q, include_total=False, aggregate=True, **kwargs):
        """
        This is really complicated because we don't know (or don't want to assume) that the three scores will have
        the same stages-- because low and hi scenarios could trigger different traversals / terminations.

        it certainly makes the code look like hell.
        the code makes an open ended dict of stages, with a subdict of result, result_lo, result_hi
        these get populated only when encountered, and output only when present.
        :param scenario:
        :param q:
        :param include_total:
        :return:
        """
        keys = defaultdict(dict)
        if aggregate:
            ress = [k.aggregate(key=self._agg) for k in self.sens_result(scenario, q)]
            for i, res in enumerate(ress):
                for c in res.components():
                    keys[c.entity][self.sens_order[i]] = c.cumulative_result
        else:
            ress = [k for k in self.sens_result(scenario, q)]
            for i, res in enumerate(ress):
                for c in res.components():
                    stgs = self._agg(c.entity)
                    keys[stgs, c.uuid][self.sens_order[i]] = c.cumulative_result

        for key, result in sorted(keys.items(), key=lambda x: x[0]):
            if aggregate:
                stage, alt_stage = key
            else:
                stage, alt_stage = key[0]  # double packed
            d = {
                'scenario': str(scenario),
                'stage': stage,
                'alt_stage': alt_stage,
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
