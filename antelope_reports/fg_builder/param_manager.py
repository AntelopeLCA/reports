class ParamManager(object):
    """
    The parameters sheet has the following columns:
    (origin) (parameter) (flow_unit) .... scenario names
    """
    _sheet = None

    def __init__(self, fg, xlsx, sheetname='parameters'):
        self._xlsx = xlsx
        self._fg = fg
        self._sheetname = sheetname
        self._update()

    def _update(self):
        self._sheet = self._xlsx[self._sheetname]

    @property
    def scenarios(self):
        for k in self._sheet.row(0):
            if k.value in ('origin', 'parameter', 'flow_unit'):
                continue
            yield k.value

    def write_parameters(self):
        from pandas import DataFrame

        df = DataFrame(self._fg.knobs(param_dict=True))
        self._xlsx.write_dataframe('parameters', df, clear_sheet=True, fillna='', write_index=False)
        self._update()

    def write_scenario(self, scenario):
        if scenario in self.scenarios:
            col = next(i for i, k in enumerate(self._sheet.row(0)) if k.value == scenario)
            data = []
            start_row = 1
        else:
            col = self._sheet.ncols
            data = [scenario]
            start_row = 0
        for r in range(1, self._sheet.nrows):
            row = self._sheet.row_dict(r)
            if row['origin'] == self._fg.origin:
                param = row['parameter']
                kn = self._fg[param]
                if kn is None:
                    print('Skipping unknown parameter %s/%s' % (self._fg.origin, param))
                    continue
                unit = row['flow_unit']
                val = kn.exchange_value(scenario)
                if val == kn.observed_ev:
                    data.append(None)
                else:
                    if unit == kn.flow.unit:
                        data.append(val)
                    else:
                        cf = kn.flow.reference_entity.convert(to=unit)
                        data.append(val * cf)
            else:
                data.append(None)
        self._xlsx.write_column(self._sheetname, col, data, start_row=start_row)
        self._update()

    def apply_parameters(self):
        self._fg.clear_scenarios(terminations=False)
        for r in range(1, self._sheet.nrows):
            row = self._sheet.row_dict(r)
            if row.pop('origin') != self._fg.origin:
                continue
            param = row.pop('parameter')
            kn = self._fg[param]
            if kn is None:
                print('Skipping unknown parameter %s/%s' % (self._fg.origin, param))
                continue
            unit = row.pop('flow_unit', None)
            for k, v in row.items():
                if v is not None:
                    self._fg.observe(kn, exchange_value=float(v), scenario=k,  units=unit)

    def apply_scenario(self, scenario):
        """
        Don't clear the whole foreground; instead re-apply the scenario
        :param scenario:
        :return:
        """
        for r in range(1, self._sheet.nrows):
            row = self._sheet.row_dict(r)
            if row.pop('origin') != self._fg.origin:
                continue
            param = row.pop('parameter')
            kn = self._fg[param]
            if kn is None:
                print('Skipping unknown parameter %s/%s' % (self._fg.origin, param))
                continue
            unit = row.pop('flow_unit', None)
            val = row.pop(scenario)
            if val is None:
                kn.set_exchange_value(scenario, None)
            else:
                self._fg.observe(kn, exchange_value=val, scenario=scenario, units=unit)
