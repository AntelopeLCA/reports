from collections import namedtuple
from antelope import EntityNotFound, UnknownOrigin


ScenarioParam = namedtuple('ScenarioParam', ('fragment', 'scenario', 'value'))  # need uncertainty params.. eventually
ScenarioTermination = namedtuple('ScenarioTermination', ('fragment', 'scenario', 'termination', 'term_flow', 'descend'))



class XlsxScenarioUpdater(object):
    """
    Apply scenarios to the fragments found in an foreground archive.
    Operates as a context manager:
    >>> with XlsxScenarioUpdater(fg, xlsx, *sheets) as a:
    >>>    a.apply()
    NOTE: all pre-existing scenarios in fg are removed and replaced with the ones found in *sheets

    There are two different patterns for a sheet listed in *sheets (both can coexist) (all case-insensitive):
     - observations: must have columns 'fragment', 'scenario', 'observedValue'
     - terminations: must have columns 'fragment', 'scenario', 'termination', 'term_flow'
       term_flow can be omitted but is obligatory in many cases
    """

    @staticmethod
    def _grab_value(cell):
        value = cell.value
        if isinstance(value, str):
            if value == '':
                value = None
        return value

    def _read_scenarios(self, sheet):
        if sheet in self._xl.sheet_names():
            sh = self._xl.sheet_by_name(sheet)
            headers = [k.value.lower() for k in sh.row(0)]
            _ev = 'observedvalue' in headers
            _tm = 'termination' in headers
            for i in range(1, sh.nrows):
                row = [self._grab_value(k) for k in sh.row(i)]
                d = {headers[k]: row[k] for k in range(min([len(row), len(headers)]))}
                if 'fragment' not in d or d['fragment'] is None:
                    continue
                if _ev:
                    if d.get('observedvalue') is not None:
                        self._params.append(ScenarioParam(d['fragment'], d['scenario'], float(d['observedvalue'])))
                if _tm:
                    if d.get('termination') is not None:
                        desc = {'true': True,
                                'false': False,
                                '0': None}[d.get('descend', '0').lower()]  # map to bool

                        self._terms.append(ScenarioTermination(d['fragment'], d['scenario'], d['termination'],
                                                               d.get('term_flow'), desc))

    def _print(self, *args):
        if not self._quiet:
            print(*args)

    def __init__(self, fg, xlrd_like, *scenario_sheets, terminations=True, quiet=True):

        self._fg = fg
        self._xl = xlrd_like

        self._params = []
        self._terms = []

        self._do_term = terminations
        self._quiet = quiet

        self._model_data = []
        if len(scenario_sheets) == 0:
            scenario_sheets = ['scenarios-observations', 'scenarios-terminations']

        for sheet in scenario_sheets:
            self._read_scenarios(sheet)
        self._unrec = []
        self._print('Loaded %d scenario params and %d scenario terminations' % (len(self._params), len(self._terms)))

    def _apply_params(self):
        for param in self._params:
            frag = self._fg[param.fragment]
            if frag is None:
                self._print('Skipping %s' % param.fragment)
                continue
            scen = param.scenario
            if isinstance(scen, str) and scen.lower() == 'none':
                scen = None
            self._fg.observe(frag, scenario=scen, exchange_value=param.value)
            self._print('%s: %g [%s]' % (frag.name, param.value, scen))

    def _apply_terms(self):
        for term in self._terms:
            frag = self._fg[term.fragment]
            scen = term.scenario
            try:
                t = self._fg.get(term.termination)
            except (EntityNotFound, UnknownOrigin):
                self._unrec.append((term.fragment, term.termination))
                continue
            if scen.lower() == 'none':
                scen = None
                print('warning: changing default termination for %s' % frag)
                frag.clear_termination(None)

            tf = term.term_flow
            if tf is not None:
                tf = self._fg.get(tf)
            frag.terminate(t, scenario=scen, term_flow=tf, descend=term.descend)
            self._print('%s %s %s (%s) [%s]' % (frag.name, frag.termination(scen), t.name, tf, scen))

    def apply(self):
        self._fg.clear_scenarios(terminations=self._do_term)
        self._apply_params()
        if self._do_term:
            self._apply_terms()

        if len(self._unrec) > 0:
            print('Unrecognized Terminations: ')
            for frag, term in self._unrec:
                print('  [%s] -> %s' % (frag, term))

    def __enter__(self):
        """Return self object to use with "with" statement."""
        return self

    def __exit__(self, *args):
        if hasattr(self._xl, 'release_resources'):
            self._xl.release_resources()
        self._xl = None
