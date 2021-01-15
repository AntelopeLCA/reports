from .lca_model_runner import LcaModelRunner


class SimpleModelBuilder(LcaModelRunner):
    """
    We want to take in process refs, build fragments out of them, and expand them one level deep.
    """
    def __init__(self, fg, **kwargs):
        super(SimpleModelBuilder, self).__init__(**kwargs)

        self._fg = fg

        self._frags = dict()

    def add_case(self, name, p_ref):
        if name in self._scenarios:
            raise KeyError('Name already exists')
        frag = self._fg.create_process_model(p_ref)
        self._fg.extend_process(frag, multi_flow=True)
        self.add_scenario(name)
        self._frags[name] = frag

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        frag = self._frags[scenario]
        return frag.fragment_lcia(lcia, **kwargs)