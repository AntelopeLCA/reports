import os

from antelope_reports.model_runner.lca_model_runner import tabularx_ify
from antelope_reports.charts.pos_neg import PosNegCompareError


class ResultsWriter(object):

    pdf = True

    @property
    def unit_output(self):
        """
        This is the unit-scale case-by-case output as a long table
        :return:
        """
        return os.path.join(self.lca_path, '%s-unit-models%s.csv' % (self.scope, self.suffix))

    @property
    def unit_csv(self):
        """
        Summary table (stage x lcia) in csv format
        :return:
        """
        return os.path.join(self.lca_path, '%s-unit-tabular%s.csv' % (self.scope, self.suffix))

    @property
    def unit_table(self):
        """
        Summary table (stage x lcia) in tex format
        :return:
        """
        return os.path.join(self.figs_path, '%s-unit-bar%s.tex' % (self.scope, self.suffix))

    @property
    def full_output(self):
        """
        Provincial-scale output as a long table for all scenarios
        :return:
        """
        return os.path.join(self.lca_path, '%s-lca%s.csv' % (self.scope, self.suffix))

    def year_csv(self, year):
        """
        Provincial-scale summary table (stage x lcia) for a single year, csv format
        :param year:
        :return:
        """
        return os.path.join(self.lca_path, '%s-lca-%s-tabular%s.csv' % (self.scope, year, self.suffix))

    def year_table(self, year):
        """
        Provincial-scale summary table (stage x lcia) for a single year, tex format
        :param year:
        :return:
        """
        return os.path.join(self.figs_path, '%s-lca-%s-bar%s.tex' % (self.scope, year, self.suffix))

    def pos_neg_eps(self, scenario):
        return os.path.join(self.figs_path, '%s-pos-neg-%s%s.%s' % (self.scope, scenario, self.suffix, self._or_eps))

    def pos_neg_tex(self, scenario):
        return os.path.join(self.figs_path, '%s-pos-neg-%s%s.tex' % (self.scope, scenario, self.suffix))

    def system_diagram(self, *scenarios):
        scen = '-'.join(scenarios)
        return os.path.join(self.figs_path, '%s-system-diagram_%s.fig' % (self.scope, scen))

    def _check_output_dir(self):
        if not os.path.exists(self.lca_path):
            os.makedirs(self.lca_path, exist_ok=True)
        if not os.path.exists(self.figs_path):
            os.makedirs(self.figs_path, exist_ok=True)

    @property
    def lca_path(self):
        return os.path.join(self.lca_root, self.scope)

    @property
    def figs_path(self):
        return os.path.join(self.figs_root, self.scope)

    @property
    def suffix(self):
        if self.case is None:
            return ''
        return '-%s' % self.case

    def __init__(self, path, scope, lca_path='lca_output', figs_path='lca_figs', case=None):
        """

        :param path:
        :param scope:
        :param lca_path:
        :param figs_path:
        :param case:
        """

        self.scope = scope
        self.case = case

        self.lca_root = os.path.abspath(os.path.join(path, lca_path))
        self.figs_root = os.path.abspath(os.path.join(path, figs_path))

        self._check_output_dir()

    def generate_csv(self, catra, **kwargs):
        catra.results_to_csv(self.full_output, **kwargs)

    def generate_year_output(self, study_year, year, stage_order):
        # generate_pos_neg_compare(study_year)
        study_year.scenario_detail_tbl(year, filename=self.year_csv(year), column_order=stage_order)

        study_year.results_to_tex(self.year_table(year), scenario=year, column_order=stage_order, format='%.2e',
                                  sort_column=0)

    def generate_unit_output(self, study, scenario_order=None):
        """
        set display quantities via runner
        :param study: LcaModelRunner instance
        :param scenario_order:
        :return:
        """
        study.results_to_csv(self.unit_output, scenarios=scenario_order)

        study.results_to_tex(self.unit_table, column_order=scenario_order, format='%.2e', sort_column=0)

    def pos_neg_chart(self, runner, scenario, qs=None, table=True):
        if qs is None:
            qs = list(runner.quantities)
        pn = PosNegCompareError(*(runner.sens_result(scenario, q) for q in qs), filename=self.pos_neg_eps(scenario))
        if table:
            # multicolumn=False is no longer supported
            tabularx_ify(pn.dataframe, column_format='ll *{3}X',
                         filename=self.pos_neg_tex(scenario))  # multicolumn=False

    @property
    def _or_png(self):
        if self.pdf:
            return 'pdf'
        return 'png'

    @property
    def _or_eps(self):
        if self.pdf:
            return 'pdf'
        return 'png'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        print('Exiting %s context' % self.__class__.__name__)
        print(args)
        pass
