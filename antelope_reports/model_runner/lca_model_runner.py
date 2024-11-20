import csv

from collections import defaultdict
from pandas import DataFrame, MultiIndex

from antelope_core.lcia_results import LciaResult


def tabularx_ify(df, filename, width='\\textwidth', column_format='\\tabspec', hrules=True, **kwargs):
    """
    Need to figure out how to bring \tabspec in-- (answer: jinja?)
    :param df:
    :param filename:
    :param width:
    :param column_format: column format specification
    :param hrules: True
    #:param sort_column: optional integer column number by which to sort (most positive to most negative)
    # did this get dropped or what
    :return:
    """
    longstr = df.style.to_latex(column_format=column_format, hrules=hrules, **kwargs)  # df.style.to_latex recommended but has dependencies
    tabularx = longstr.replace(
        '{tabular}', '{tabularx}').replace(
        'begin{tabularx}', 'begin{tabularx}{%s}' % width)
    with open(filename, 'w') as fp:
        fp.write(tabularx)


def weigh_lcia_results(quantity, *args, weight=None):
    """
    Merge together a collection of LciaResult objects
    :param quantity: the weighing indicator- should be distinct from the supplied results but doesn't have to be
    :param args: a list of LciaResult objects to weight
    :param weight: optional dict of quantity-to-weight (if omitted, all results will be given unit weight)
    :return:
    """
    if weight is None:
        weight = dict()
    scenarios = sorted(set(arg.scenario for arg in args))
    if len(scenarios) > 1:
        print('Warning: multiple scenarios being combined together; using first only\n%s' % scenarios)
    scenario = scenarios[0]

    result = LciaResult(quantity, scenario=scenario)

    for arg in args:
        if arg.quantity in weight:
            _w = weight[arg.quantity]
        else:
            _w = 1.0

        for k in arg.keys():
            c = arg[k]
            result.add_summary(k, c.entity, 1.0, c.cumulative_result * _w)

    return result


class LcaModelRunner(object):
    _agg_key = None
    _alt_agg_key = None
    _seen_stages = None
    _fmt = '%.10e'

    def __init__(self, agg_key=None, alt_agg_key=None):
        """

        :param agg_key: default is StageName
        """
        self._scenarios = []  # sequential list of scenario names

        self._lcia_methods = []
        self._weightings = dict()

        self._publish = None

        self._results = dict()
        self.set_agg_key(agg_key)
        self.set_alt_agg_key(alt_agg_key)

    def recalculate(self, **kwargs):
        self._results = dict()
        for lm in self.lcia_methods:
            self.run_lcia(lm, **kwargs)
        for w in self.weightings:
            self._run_weighting(w)

    def set_publication_quantities(self, *qs):
        """
        Use this to constrain automatically-generated output to a subset of calculated quantities.
        :param qs:
        :return:
        """
        self._publish = list(q for q in qs if q in self._lcia_methods or q in self._weightings)

    def set_agg_key(self, agg_key=None):
        if agg_key is None:
            agg_key = lambda x: x.name

        self._agg_key = agg_key
        self._seen_stages = defaultdict(set)  # reset

    def set_alt_agg_key(self, alt_agg_key=None):
        self._alt_agg_key = alt_agg_key
        self._seen_stages = defaultdict(set)

    def _agg(self, entity):
        """
        returns either a single or a tuple
        :return:
        """
        if self._alt_agg_key is None:
            return self._agg_key(entity), None
        return self._agg_key(entity), self._alt_agg_key(entity)

    def _scenario_index(self, scenario):
        return scenario

    @property
    def scenarios(self):
        """
        This returns keys for the 'scenarios' in the tool (first result index)
        Must be implemented in a subclass
        :return:
        """
        for k in self._scenarios:
            yield k

    def add_scenario(self, name):
        if name in self._scenarios:
            raise KeyError('Case already exists: %s' % name)
        self._scenarios.append(name)

    @property
    def quantities(self):
        """
        This returns known quantities (second result index)
        :return:
        """
        if self._publish:
            for k in self._publish:
                yield k
        else:
            for k in self.lcia_methods:
                yield k
            for k in self.weightings:
                yield k

    @property
    def lcia_methods(self):
        """
        This returns the LCIA methods, which are a subset of quantities
        :return:
        """
        return self._lcia_methods

    @property
    def weightings(self):
        """
        This returns LCIA weightings, which are the complementary subset to lcia_methods
        :return:
        """
        return list(k for k in self._weightings.keys())

    @property
    def format(self):
        return self._fmt

    @format.setter
    def format(self, fmt):
        """
        None means do not format output; return raw numbers
        :param fmt:
        :return:
        """
        if fmt is None:
            self._fmt = None
        else:
            self._fmt = str(fmt)

    def add_weighting(self, quantity, *measures, weight=None):
        """
        Compute a weighted LCIA result
        :param quantity:
        :param measures: a list of LCIA quantities to be weighed
        :param weight: an optional dictionary of quantity: weight (default is equal weighting)
        :return:
        """
        if weight is None:
            weight = {m: 1.0 for m in measures}

        self._weightings[quantity] = weight
        self._run_weighting(quantity)

    def _run_case_weighting(self, scen, quantity):
        ws = self._weightings[quantity]
        res = [self.result(scen, q) for q in ws.keys()]
        wgt = weigh_lcia_results(quantity, *res, weight=ws)
        self._results[scen, quantity] = wgt

    def _run_weighting(self, quantity):
        ws = self._weightings[quantity]
        for q in ws.keys():
            self.run_lcia(q)
        for scen in self.scenarios:
            self._run_case_weighting(scen, quantity)

    @property
    def stages(self):
        return sorted(k for k, v in self._seen_stages.items() if len(v) > 0)

    def scenarios_with_stage(self, stage):
        return self._seen_stages[stage]

    def result(self, scenario, lcia_method):
        return self._results[scenario, lcia_method]

    def run_lcia_case_method(self, scen, lcia, **kwargs):
        res = self._run_scenario_lcia(scen, lcia, **kwargs)
        res.scenario = scen
        for stg in list(res.aggregate(key=self._agg).keys()):
            self._seen_stages[stg].add(scen)
        self._results[scen, lcia] = res

    def run_lcia(self, lcia, **kwargs):
        if lcia not in self._lcia_methods:
            self._lcia_methods.append(lcia)
        for scen in self.scenarios:
            self.run_lcia_case_method(scen, lcia, **kwargs)
        return self.lcia_results(lcia)

    def lcia_results(self, lcia):
        return [self._results[scenario, lcia] for scenario in self.scenarios]

    def _format(self, result):
        if self._fmt is None:
            return result
        return self._fmt % result

    def _csv_formatter(self, style):
        """
        Specifies how the rows should be constructed for the CSV result writer.
        Designed to be subclassed so that mix-ins can provide new output styles.  The proper way to do this is to
        define a method named '_csv_format_%s' % style which returns: (header_list, row_generator)
        The row_generator method should take as argument (scenario, quantity, **kwargs) and yield a dict whose keys are
        a subset of header_list and whose values are written into the file.

        Note: in practice it takes a lot of gymnastics to be able to take advantage of this (e.g. to debug /alter csv
        reports without exiting the session.
        :param style:
        :return:
        """
        st_name = '_csv_format_%s' % style
        if hasattr(self, st_name):
            return getattr(self, st_name)()
        return self.results_headings, self._gen_lcia_rows

    @property
    def results_headings(self):
        return ['scenario', 'stage', 'alt_stage', 'method', 'category', 'indicator', 'result', 'units']

    # tabular for all: accept *args as result items, go through them one by one
    def results_to_csv(self, filename, scenarios=None, style=None, aggregate=True, **kwargs):
        if scenarios is None:
            scenarios = sorted(self.scenarios)
        else:
            known = list(self.scenarios)
            scenarios = list(filter(lambda x: x in known, scenarios))

        headings, agg = self._csv_formatter(style)

        with open(filename, 'w') as fp:
            cvf = csv.DictWriter(fp, headings, quoting=csv.QUOTE_NONNUMERIC, lineterminator='\n')
            cvf.writeheader()

            for q in self.quantities:
                for scenario in scenarios:
                    for k in agg(scenario, q, aggregate=aggregate, **kwargs):
                        cvf.writerow(k)

    @staticmethod
    def _gen_row(q, k):
        k['method'] = q.get('method') or ''
        k['category'] = q.get('category') or q.name
        k['indicator'] = q['indicator']
        k['units'] = q.unit
        return k

    def _gen_lcia_rows(self, scenario, q, include_total=False, aggregate=True, **kwargs):
        res = self._results[scenario, q]
        if aggregate:
            _it = sorted(res.aggregate(key=self._agg).components(), key=lambda x: x.entity)
        else:
            _it = sorted(res.components(), key=lambda x: self._agg(x.entity))
        for c in _it:
            if aggregate:
                stage, alt_stage = c.entity
            else:
                stage, alt_stage = self._agg(c.entity)

            result = c.cumulative_result
            yield self._gen_row(q, {
                'scenario': str(scenario),
                'stage': stage,
                'alt_stage': alt_stage,
                'result': self._format(result)
            })
        if include_total:
            yield self._gen_row(q, {
                'scenario': str(scenario),
                'stage': 'Net Total',
                'result': self._format(res.total())
                 })

    def _finish_dt_output(self, dt, column_order, filename, norm=False, _total=None, add_row_index=False):
        """
        Add a units column, order it first, and transpose
        :param dt:
        :param column_order:
        :param filename:
        :param _total: whether to add scenario total to the dataframe- which should happen in client code
        :param add_row_index: for detail view only: whether scenario index should be set (perhaps always?)
        :return:
        """
        if column_order is None:
            ord_columns = list(dt.columns)
        else:
            ord_columns = [k for k in column_order if k in dt.columns]
            ord_columns += [k for k in dt.columns if k not in ord_columns]  # add in anything that's missed

        dto = dt[ord_columns].transpose()

        if add_row_index:
            dto = dto.set_index(self._scenario_index(k) for k in ord_columns)

        if norm:
            dn = DataFrame({'Normalization': [lm.norm() for lm in self.quantities]},
                           index=MultiIndex.from_tuples(self._qty_tuples)).transpose()
            dto = dn.append(dto)

        if _total:
            dt = DataFrame({'Total': [self._format(self.result(_total, lm).total()) for lm in self.quantities]},
                           index=MultiIndex.from_tuples(self._qty_tuples)).transpose()
            dto = dto.append(dt)

        if filename is not None:
            dto.to_csv(filename, quoting=csv.QUOTE_ALL)

        return dto

    @property
    def _qty_tuples(self):
        if all(q['Indicator'] == q.unit for q in self.quantities):
            for q in self.quantities:
                if q.has_property('ShortName'):
                    yield q['ShortName'], q['Indicator']
                else:
                    yield q['Name'], q['Indicator']
        else:
            for q in self.quantities:
                if q.has_property('ShortName'):
                    yield q['ShortName'], q['Indicator'], q.unit
                else:
                    yield q['Name'], q['Indicator'], q.unit

    def scenario_detail_tbl(self, scenario, filename=None, column_order=None, norm=False, total=False):
        dt = DataFrame(({k.entity: self._format(k.cumulative_result)
                         for k in self.result(scenario, lm).aggregate(key=self._agg).components()}
                        for lm in self.quantities), index=MultiIndex.from_tuples(self._qty_tuples))
        if total:
            _total = scenario
        else:
            _total = None
        return self._finish_dt_output(dt, column_order, filename, norm=norm, _total=_total)

    def scenario_summary_tbl(self, filename=None, column_order=None, norm=False, add_row_index=False):
        if column_order is None:
            column_order = list(self.scenarios)
        dt = DataFrame(({k: self._format(self.result(k, lm).total()) for k in column_order}
                        for lm in self.quantities),
                       index=MultiIndex.from_tuples(self._qty_tuples))
        return self._finish_dt_output(dt, column_order, filename, norm=norm, add_row_index=add_row_index)
    
    def results_to_tex(self, filename, scenario=None, format=None, sort_column=None, **kwargs):
        """
        Print summary table (scenario=None) or detail table (scenario is not None) in tabularx format
        :param filename: tex file
        :param scenario:
        :param format: temporarily set output format for TeX file
        :param sort_column: optional integer column number to sort by
        :param kwargs:
        :return:
        """
        oldformat = self.format

        if format:
            self.format = format

        if scenario is None:
            df = self.scenario_summary_tbl(**kwargs)
        else:
            df = self.scenario_detail_tbl(scenario, **kwargs)

        if sort_column is not None:
            # this shenanigan is necessary because tex output is often string-ified for clean formatting
            df['sort'] = df.iloc[:, sort_column].apply(float)
            try:
                df = df.sort_values('sort', ascending=False).drop('sort', axis=1)
            except ValueError:
                print('Unable to sort values~~ sorry')
                df = df.drop('sort', axis=1)

        tabularx_ify(df, filename)

        self.format = oldformat

    '''
    Subclass must implement only one function: a mapping from scenario key and lcia method to result
    '''
    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        """
        Maps scenario name to LCIA Result. Must be implemented in a subclass
        :param scenario:
        :param lcia:
        :return: LciaResult
        """
        return NotImplemented

    def to_dataframe(self, index=None, summary=True, **kwargs):
        """
        A minimal dataframe that largely duplicates scenario_summary_tbl()
        :param index:
        :param summary: [True] report totals for each case. [False] group by agg_key
        :param kwargs:
        :return:
        """
        if index is None:
            index = list(self.quantities)
        if summary:
            return DataFrame(({case: self._results[case, q].total() for case in self.scenarios}
                              for q in self.quantities),
                             index=index, **kwargs)
        else:
            return DataFrame(((q['ShortName'], q.unit, scenario, c.entity[0], c.entity[1], c.cumulative_result)
                              for scenario in self.scenarios
                              for q in self.quantities
                              for c in self.result(scenario, q).aggregate(key=self._agg).components()),
                             columns=('Quantity', 'Unit', 'Case', 'Stage', 'Alt', 'Result'))
