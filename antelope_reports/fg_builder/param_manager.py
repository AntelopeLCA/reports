class ParamManager(object):
    """
    The parameters sheet has the following columns- square brackets indicate optional:
    (origin) (parameter) [flow_name] [flow_unit] [default].... scenario names
    """
    _sheet = None
    _sheetname = None

    _reserved_names = ('origin', 'parameter', 'flow_name', 'flow_unit',  'default')

    def __init__(self, fg, xlsx, sheetname='parameters'):
        self._xlsx = xlsx
        self._fg = fg
        self.select_sheet(sheetname)

    def select_sheet(self, sheetname):
        if sheetname in self._xlsx.sheet_names():
            self._sheetname = sheetname
            self._update()
            print('Found scenarios: %s' % list(self.scenarios))
        else:
            raise KeyError('Sheet %s not found' % sheetname)

    def _update(self):
        self._sheet = self._xlsx[self._sheetname]

    @property
    def scenarios(self):
        org = False
        ext = False
        for k in self._sheet.row(0):
            if k.value in self._reserved_names:
                if k.value == 'origin':
                    org = True
                if k.value == 'parameter':
                    ext = True
                continue
            yield k.value
        if not org:
            raise ValueError("Required column 'origin' not found")
        if not ext:
            raise ValueError("Required column 'parameter' not found")

    def write_parameters(self):
        """
        This destructively writes the current set of stored parameters to the sheet.
        ad-hoc parameters are not supported, but they could be by finding parameterized fragments that are not knobs.
        :return:
        """
        from pandas import DataFrame

        df = DataFrame(self._fg.knobs(param_dict=True))
        self._xlsx.write_dataframe('parameters', df, clear_sheet=True, fillna='', write_index=False)
        self._update()

    def _get_rows(self):
        for r in range(1, self._sheet.nrows):
            row = self._sheet.row_dict(r)
            if 'parameter' not in row:
                continue
            if row.pop('origin', None) != self._fg.origin:
                continue
            yield row

    def _get_knob_or_child_flow(self, row):
        param = row.pop('parameter')
        kn = self._fg[param]
        if kn is None:
            print('Skipping unknown parameter %s/%s' % (self._fg.origin, param))
            return None
        cf = self._fg[row.pop('flow_name', None)]
        if cf:
            try:
                return next(kn.children_with_flow(cf))
            except StopIteration:
                print('Skipping missing child flow %s/%s:%s' % (self._fg.origin, param, cf.external_ref))
                return None
        return kn

    def write_scenario(self, scenario):
        """
        Write the specified column to the spreadsheet
        :param scenario:
        :return:
        """
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
            if row.get('origin') == self._fg.origin:
                kn = self._get_knob_or_child_flow(row)
                if kn is None:
                    data.append(None)
                    continue

                unit = row['flow_unit']
                val = kn.exchange_value(scenario)
                if val == kn.observed_ev:
                    data.append('')
                else:
                    if unit == kn.flow.unit:
                        data.append(val)
                    else:
                        cf = kn.flow.reference_entity.convert(to=unit)
                        data.append(val * cf)
            else:
                data.append(None)
        print('Writing %d items to %s, scenario %s' % (len(list(filter(None, data))) - 1 + start_row, self._sheetname,
                                                       scenario))
        self._xlsx.write_column(self._sheetname, col, data, start_row=start_row)
        self._update()

    def apply_parameters(self):
        # self._fg.clear_scenarios(terminations=False)  # well, that's foolish
        count = 0
        for row in self._get_rows():
            kn = self._get_knob_or_child_flow(row)
            if kn is None:
                continue

            unit = row.pop('flow_unit', None)
            for k, v in row.items():
                if k in self._reserved_names:
                    continue
                if v is None or v == 'NA':
                    continue
                self._fg.observe(kn, exchange_value=float(v), scenario=k,  units=unit)
                count += 1
        print('Applied %d parameter settings from %s' % (count, self._sheetname))

    def apply_scenario(self, scenario):
        """
        Don't clear the whole foreground; instead re-apply the scenario
        :param scenario:
        :return:
        """
        if scenario in self._reserved_names:
            raise ValueError('Invalid scenario name: %s' % scenario)
        count = 0
        for row in self._get_rows():
            kn = self._get_knob_or_child_flow(row)
            if kn is None:
                continue

            unit = row.pop('flow_unit', None)
            val = row.pop(scenario)
            if val is None:
                kn.set_exchange_value(scenario, None)
            else:
                self._fg.observe(kn, exchange_value=val, scenario=scenario, units=unit)
                count += 1
        print('Applied %d parameter settings from %s, scenario %s' % (count, self._sheetname, scenario))
