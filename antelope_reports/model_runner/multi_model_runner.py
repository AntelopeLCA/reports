from .lca_model_runner import LcaModelRunner
from pandas import ExcelWriter


class MultiModelRunner(LcaModelRunner):
    def __init__(self, *frags, **kwargs):
        super(MultiModelRunner, self).__init__(**kwargs)
        self._frags = dict()

        for frag in frags:
            self.add_fragment(frag)

    def add_fragment(self, frag, name=None):
        """

        :param frag:
        :param name:
        :return:
        """
        if name is None:
            name = frag.name
        if name not in self._scenarios:
            self.add_scenario(name)
        self._frags[name] = frag

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        frag = self._frags[scenario]
        return frag.fragment_lcia(lcia, **kwargs)

    def write_to_xlsx(self, xlsx_name, details=False):
        """
        This is presently a big fat ugly mess and does not satisfy basic requirements because it does not specify
        the functional unit of each model.  We need to add metadata to this...
        :param xlsx_name:
        :param details:
        :return:
        """
        self._fmt = None
        xlw = ExcelWriter(xlsx_name)
        pd = self.scenario_summary_tbl()
        pd.to_excel(xlw, sheet_name='Summary')
        if details:
            for s in self.scenarios:
                self.scenario_detail_tbl(s).to_excel(xlw, sheet_name=s)
        xlw.save()
