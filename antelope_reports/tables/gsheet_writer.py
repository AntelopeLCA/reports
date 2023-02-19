from xlstools import GoogleSheetReader
from pandas import to_numeric


def prepare_dataframe(df):
    return df.apply(to_numeric).sort_values(df.columns[0])


class GSheetTableWriter(object):
    _gsheet = None
    _active = False

    def _check_or_create_sheet(self, sheetname, group=None):
        sn = self._gsheet.sheet_names()
        if sheetname in sn:
            ix = sn.index(sheetname)
        else:
            self._gsheet.create_sheet(sheetname)
            ix = len(sn)
        if self._index:
            self._gsheet.write_row('Index', ix, (sheetname, group))

    def write_results_dataframe_to_gsheet(self, sheetname, df, group=None,
                                          clear_sheet=True, write_header=True, header_levels=None):
        """

        :param gsheet: a GoogleSheetReader
        :param sheetname: sheet to write to or create
        :param df: sorted, prepared data
        :param group: [None] optional - reported in Index sheet
        :param clear_sheet: [True]
        :param write_header: [True] whether to write header (False: leave it standing)
        :param header_levels: number of header levels to write. Must be <= nlevels
        :return:
        """

        ncol = len(df.columns)
        if header_levels is None or header_levels > df.columns.nlevels:
            header_levels = df.columns.nlevels

        if sheetname in self._gsheet.sheet_names():
            # start by clearing the sheet- with or without headers
            if clear_sheet:
                if write_header:
                    # we are clearing the entire sheet, to write both header and data
                    self._gsheet.clear_region(sheetname)
                else:
                    # we clearing sheet but keeping header
                    self._gsheet.clear_region(sheetname, start_row=header_levels)
            else:
                # we are not clearing the sheet
                if write_header:
                    # but we are still rewriting the header
                    self._gsheet.clear_region(sheetname, end_col=ncol, end_row=header_levels - 1)
        else:
            self._check_or_create_sheet(sheetname, group=group)
            write_header = True  # force header write if the sheet is just created

        # then populate
        def _row_gen(_df):
            for j, row in _df.fillna('NA').iterrows():
                yield [j] + list(row.values)

        if write_header:
            for i in range(header_levels):
                h = [''] + list(df.columns.get_level_values(i))
                self._gsheet.write_row(sheetname, i, h)
        self._gsheet.write_rectangle_by_rows(sheetname, _row_gen(df), start_row=header_levels)

    @classmethod
    def from_credentials(cls, credentials, gsheet_id, **kwargs):
        return cls(GoogleSheetReader(credentials, gsheet_id), **kwargs)

    def _re_flow_index_sheet(self):
        """
        Re-order rows in the index sheet to match the actual order of tabs.
        :return:
        """
        sn = self._gsheet.sheet_names()
        cur_ix = self._gsheet.sheet_by_name('Index')
        meta = cur_ix.col(0)
        dd = {k.value: [j.value for j in cur_ix.row(i)] for i, k in enumerate(meta) if k.value is not None}

        if cur_ix.nrows > 1:
            self._gsheet.clear_region('Index', start_row=1)
        self._gsheet.write_rectangle_by_rows('Index', (dd[k] for k in sn if k in dd and k != 'Index'), start_row=1)

    def __init__(self, sheet=None, active=None, index=True):
        self._index = index
        self.active = active
        if sheet:
            if active is None:  # if sheet provided and active is not provided, assume activate
                self.active = True
            self._gsheet = sheet
            if self._index:
                # could do some machinations here to detect + manage deleted or re-ordered sheets
                if 'Index' not in sheet.sheet_names():
                    # for now, we just create an index- and leave the description field to manual edit
                    sheet.create_sheet('Index')
                    sheet.write_row('Index', 0, ('Sheet Name', 'Group', 'Description'))
                self._re_flow_index_sheet()

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, value):
        self._active = bool(value)

    def _write(self, sheet, df, **kwargs):
        if self.active:
            self.write_results_dataframe_to_gsheet(sheet, df, **kwargs)
        else:
            print('[GSheet Write suppressed] %s' % sheet)

    def write_subgroup_results(self, group, runner, scenario, case=None):
        runner.format = None
        df = prepare_dataframe(runner.scenario_detail_tbl(scenario))
        sheetname = '%s-%s' % (group, scenario)
        if case:
            sheetname = '-'.join([sheetname, case])
        self._write(sheetname, df, header_levels=2, group=group)

    def write_detailed_results(self, runner, scenario, group=None):
        runner.format = None
        df = prepare_dataframe(runner.scenario_detail_tbl(scenario))
        self._write(scenario, df, header_levels=2, group=group)

    def write_summary_results(self, runner, summary, group=None):
        runner.format = None
        df = prepare_dataframe(runner.scenario_summary_tbl())
        self._write(summary, df, header_levels=2, group=group)
