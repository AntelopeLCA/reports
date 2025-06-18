import logging
try:
    from xlstools.google_sheet_reader import GoogleSheetReader
except ImportError:
    logging.error('No GoogleSheetReader found')

    class GoogleSheetReader:
        def __init__(self, credentials, spreadsheet_id):
            self.credentials = credentials
            self.sheet_id = spreadsheet_id

from .observer.headers import HEADERS, WIDTHS, TAB_COLORS, SpannerMeta


class GSheetObserver(GoogleSheetReader):

    def _request_text_format_row(self, sheet, row, start_column=0, **kwargs):
        sheet_id = self.sheet_id(sheet)
        return {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row,
                    'endRowIndex': row + 1,
                    'startColumnIndex': start_column
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {
                            **kwargs
                        }
                    }
                },
                'fields': 'userEnteredFormat(textFormat)'
            }
        }

    def _request_column_width(self, sheet, column, pixel_size=120, num_columns=1, **kwargs):
        sheet_id = self.sheet_id(sheet)
        return {
            'updateDimensionProperties': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': column,
                    'endIndex': column + num_columns
                },
                'properties': {
                    'pixelSize': pixel_size,
                    **kwargs
                },
                'fields': ','.join(['pixelSize'] + list(kwargs.keys()))
            }
        }

    def _request_sheet_properties(self, sheet, col_freeze=None, row_freeze=None, **kwargs):
        sheet_id = self.sheet_id(sheet)
        grid_props = dict()
        fields = list(kwargs.keys())
        if col_freeze:
            grid_props['frozenColumnCount'] = int(col_freeze)
            fields.append('gridProperties.frozenColumnCount')
        if row_freeze:
            grid_props['frozenRowCount'] = int(row_freeze)
            fields.append('gridProperties.frozenRowCount')
        return {
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': grid_props,
                    **kwargs
                },
                'fields': ','.join(fields)
            }
        }

    def _request_data_validation_column(self, sheet, column, condition, num_cols=1, start_row=0):
        sheet_id = self.sheet_id(sheet)
        return {
            'setDataValidation': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': start_row,
                    'startColumnIndex': column,
                    'endColumnIndex': column + num_cols
                },
                'rule': {
                    'condition': condition,
                    'inputMessage': 'select a flow',
                    'strict': False,
                    'showCustomUi': True
                }
            }
        }

    def _create_and_format_sheet_by_recipe(self, recipe, sheet_name=None):
        if sheet_name is None:
            sheet_name = recipe
        self.create_sheet(sheet_name)
        sheet_id = self.sheet_id(sheet_name)

        h = HEADERS[recipe]
        ws = WIDTHS.get(recipe, dict())
        tab_color = TAB_COLORS.get(recipe)
        rgb = {'red': tab_color[0], 'green': tab_color[1], 'blue': tab_color[2]}

        self.write_row(sheet_name, 0, h)
        self.batch_update(self._request_text_format_row(sheet_name, 0, bold=True),
                          self._request_sheet_properties(sheet_name, tabColorStyle={'rgbColor': rgb}),
                          *(self._request_column_width(sheet_name, h.index(i), w) for i, w in ws.items()))

        return sheet_id

    def _production_sheet_config(self, sheet_name):
        condition = {
            'type': 'ONE_OF_RANGE',
            'values': [
                {'userEnteredValue': '=flows!$A:$A'}
            ]
        }
        self.batch_update(self._request_sheet_properties(sheet_name, col_freeze=4, row_freeze=1),
                          self._request_data_validation_column(sheet_name,
                                                               HEADERS['production'].index('child_flow'),
                                                               condition,
                                                               start_row=1))

    def build_observatory(self):
        """
        Initializes the 'quantities', 'flows', 'flowproperties', 'spanners', 'production', and 'observations' sheets
        in the supplied xlrd-like.  (note: currently only works for GoogleSheetReader objects from xlstools)

        sets the headers to bold on all sheets; sets column widths and tab colors

        on the 'production' sheet, freezes 4 columns and 1 row, sets data validation on "child_flow"

        :return:
        """
        for k in ('quantities', 'flows', 'flowproperties', 'production', 'observations', 'taps', 'spanners'):
            if k not in self._sheetnames:
                # only create the sheet if it doesn't already exist
                self._create_and_format_sheet_by_recipe(k)

                if k == 'production':
                    self._production_sheet_config(k)

    def new_production_sheet(self, sheet_name='production'):
        if sheet_name not in self._sheetnames:
            # only create the sheet if it doesn't already exist
            self._create_and_format_sheet_by_recipe('production', sheet_name=sheet_name)

        self._production_sheet_config(sheet_name)

    @property
    def spanners(self):
        """
        Generates spanners by entry in 'spanners'
        :return:
        """
        spanners_meta = self.sheet_by_name('spanners')
        for n in range(1, spanners_meta.nrows):
            d = spanners_meta.row_dict(n)
            if d['external_ref'] is None:
                continue
            if d['external_ref'] in self._sheetnames:
                yield SpannerMeta.from_form(**d)

    def new_spanner(self, spanner_ref, source=None, spanners='spanners', **kwargs):
        # validates ref
        spanner_model = SpannerMeta.from_form(spanner_ref, source=source or 'gsheet', **kwargs)
        spanner_data = spanner_model.model_dump()

        if spanner_ref not in self._sheetnames:
            self._create_and_format_sheet_by_recipe('spanner', sheet_name=spanner_ref)
            self.batch_update(self._request_sheet_properties(spanner_ref, col_freeze=1, row_freeze=1))

        spanners_meta = self.sheet_by_name(spanners)
        rec = [k.value for k in spanners_meta.col(0)]
        try:
            row = rec.index(spanner_ref)
        except ValueError:
            row = spanners_meta.nrows

        self.write_row(spanners, row, [spanner_data.get(k) for k in HEADERS['spanners']])
        return spanner_model
