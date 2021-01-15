from .components_mixin import ComponentsMixin
from .lca_model_runner import LcaModelRunner


class ScenarioRunner(ComponentsMixin, LcaModelRunner):
    """
    This runs a single model (fragment), applying a set of different scenario specifications. 
    """

    def __init__(self, model, *common_scenarios, agg_key=None):
        """

        :param agg_key: default is StageName
        """
        super(ScenarioRunner, self).__init__(agg_key=agg_key)

        self._common_scenarios = set()

        self._model = model
        self._params = dict()

        for scenario in common_scenarios:
            self.add_common_scenario(scenario)

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

    @property
    def common_scenarios(self):
        for k in sorted(self._common_scenarios):
            yield k

    def add_case(self, case, params):
        self.add_scenario(case)  # raises KeyError
        if isinstance(params, str):
            params = (params, )
        else:
            params = tuple(params)
        self._params[case] = params

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        sc = self._params[scenario]
        sc_apply = sc + tuple(self.common_scenarios)
        return self._model.fragment_lcia(lcia, scenario=sc_apply, **kwargs)


