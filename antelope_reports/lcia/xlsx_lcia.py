from antelope import EntityNotFound
from xlstools.google_sheet_reader import GoogleSheetReader
from googleapiclient.errors import HttpError

INDEX_HEADINGS = ('Abbreviation', 'Name', 'ShortName', 'Method', 'Category', 'Indicator', 'unit', 'uuid', 'Comment', 'Notes')
FACTOR_HEADINGS = ('flowable', 'context', 'ref_quantity', 'ref_unit', 'locale', 'value')


class QdbGSheetClient(object):
    """
    This class allows us to do the following things:
     - read in a quantity definition from a google sheet and create a quantity in a designated foreground (?)
     - assign characterization factors from the spreadsheet to the quantity
     - assign characterization factors from the quantity to the spreadsheet
     - update quantity definition in spreadsheet
     - create a new quantity and define it in both the spreadsheet and the foreground

    Other things that could be done:
     - given a list of flow specs, return LCIA results
     - term manager stuff

    The reference Qdb could be entirely constituted from LCIA specifications and synonym specifications

    The essential challenge of this class is in establishing correspondence between two different information stores:
     - the local contents of the foreground
     - the static contents of the spreadsheet.

    The information can be synchronized in either direction.  Any time a synch is performed, the external_ref of the
    local quantity is stored as a mapping to the abbreviation of the remote quantity.

    The external_ref used for a quantity in a local foreground can vary.  Any time
    """
    def __init__(self, fg, sheet_id, json_credential=None, credential_file=None, **kwargs):
        self._fg = fg
        cred = json_credential or credential_file
        self._xls = GoogleSheetReader(cred, sheet_id)
        self._args = kwargs
        self._qsheet = None
        self._qs = []  # list of indicators in sequence
        self._qd = dict()  # dict of ref to indicator
        self._ext_ref_mapping = dict()  # custom mapping of fg external ref to indicator name "item"
        self.load_quantities()

    @property
    def fg(self):
        return self._fg

    @property
    def static(self):
        return False

    def load_quantities(self):
        if 'Quantities' not in self._xls.sheet_names():
            self._xls.create_sheet('Quantities')
            self._xls.write_row('Quantities', 0, INDEX_HEADINGS)
        self._qsheet = self._xls.sheet_by_name('Quantities')
        assert tuple(k.value for k in self._qsheet.row(0)) == INDEX_HEADINGS, "columns do not match specification!"
        qs = [self._qsheet.row_dict(i) for i in range(1, self._qsheet.nrows)]
        self._qd = {k['Abbreviation']: k for k in qs}
        self._qs = [k['Abbreviation'] for k in qs]

    @property
    def quantities(self):
        for q in self._qs:
            yield self._qd[q]

    def __getitem__(self, item):
        """
        Returns *remote metadata* for the quantities known to the spreadsheet
        :param item:
        :return:
        """
        try:
            return self._qd[item]
        except KeyError:
            return self._qd[self._ext_ref_mapping[item]]

    def _update_mapping(self, item, external_ref=None):
        if external_ref is None:
            if item in self._ext_ref_mapping:
                # user specified an external ref
                external_ref = item
                item = self._ext_ref_mapping[external_ref]
            else:
                # user specified an abbreviation without a mapping
                if item not in self._qd:
                    raise KeyError('Unknown item %s' % item)
                try:
                    external_ref = next(k for k, v in self._ext_ref_mapping.items() if v == item)
                except StopIteration:
                    # the item is un-mapped; establish an epoynmous mapping
                    external_ref = item
                    self._ext_ref_mapping[external_ref] = item
        else:
            self._ext_ref_mapping[external_ref] = item
        return item, external_ref

    def create_or_update_quantity(self, item, name=None, ref_unit=None, external_ref=None, **kwargs):
        item, external_ref = self._update_mapping(item, external_ref)
        if item in self._qd:
            dat = self._qd[item]
        else:
            if name is None or ref_unit is None:
                raise ValueError('Must provide name and ref unit to create new method')
            dat = {'Abbreviation': item,
                   'unit': ref_unit}
            self._qd[item] = dat
            self._qs.append(item)
        if name is not None:
            dat['Name'] = name

        for n in INDEX_HEADINGS:
            if n in kwargs:
                dat[n] = kwargs[n]

        ent = self.fetch_quantity(item, external_ref)
        self.write_quantity_metadata(item, external_ref)
        return ent

    def fetch_quantity(self, item, external_ref=None):
        """
        Updates the quantity in the local foreground according to the specification on the google sheet.
        :param item:
        :param external_ref:
        :return:
        """
        item, external_ref = self._update_mapping(item, external_ref)
        dat = {**self._qd[item]}
        if self.fg[external_ref] is None:
            ent = self.fg.new_quantity(dat.pop('Name'), ref_unit=dat.pop('unit'),
                                       external_ref=external_ref, synonyms=(item,), **dat)
        else:
            ent = self.fg[external_ref]
            for k, v in dat.items():
                if k == 'unit':
                    if ent.unit != v:
                        print('%s: Cannot update reference unit for existing quantity (%s)' % (ent, v))
                else:
                    ent[k] = v
        return ent

    def write_quantity_metadata(self, item, external_ref=None):
        """
        Tricky.  Do we specify the local quantity, or the remote abbreviation?  easy on reflection: the abbreviation
        is required so go ahead and make it the first positional parameter. This has the advantage of being consistent
        with the whole rest of the API (except that _update_mapping implicitly accepts external_ref)
        :param item:
        :param external_ref:
        :return:
        """
        item, external_ref = self._update_mapping(item, external_ref)
        ent = self.fg[external_ref]
        dat = {'Abbreviation': item}
        for k in INDEX_HEADINGS:
            if k == 'Abbreviation':
                continue
            elif k == 'unit':
                dat[k] = ent.unit
            else:
                dat[k] = ent.get(k)
        if item not in self._qd:
            self._qs.append(item)
            self._qd[item] = dat
        row = self._qs.index(item) + 1
        row_data = [dat[k] for k in INDEX_HEADINGS]
        self._xls.write_row('Quantities', row, row_data)

    def _factor_headings(self, item):
        indicator = self._qd[item]['Indicator']
        columns = FACTOR_HEADINGS + (indicator,)
        return columns

    def _create_or_retrieve_cf_sheet(self, item):
        columns = self._factor_headings(item)
        if item not in self._xls.sheet_names():
            self._xls.create_sheet(item)
        try:
            self._xls.write_row(item, 0, columns)
        except HttpError:
            print('No write access; not updating column headings for %s' % item)
        return self._xls.sheet_by_name(item)

    def update_cfs(self, item, external_ref=None):
        """
        Appply static gsheet CFs to local quantity

        :param item:
        :param external_ref: reference for local quantity
        :return:
        """
        item, external_ref = self._update_mapping(item, external_ref)
        ent = self.fetch_quantity(item, external_ref)
        sheet = self._create_or_retrieve_cf_sheet(item)
        for i in range(1, sheet.nrows):
            cf = sheet.row_dict(i)
            try:
                rq = self.fg.get_canonical(cf['ref_quantity'])
            except EntityNotFound:
                print('Ref quantity %s not found' % cf['ref_quantity'])
                continue
            value = cf['value'] * rq.convert(to=cf['ref_unit'])  # check this!  if the CF is 45 points per gram and
            # the ref unit is kg, then that's 45,000 points per kg
            ent.characterize(cf['flowable'], rq, value, context=cf['context'], location=cf['locale'],  # why "location"?
                             overwrite=True)

        return ent

    def write_quantity_cfs(self, item, external_ref=None):
        """
        Write local CFs to the google sheet (destructively-- run update_cfs first to not lose data)
        :param item:
        :param external_ref:
        :return:
        """
        item, external_ref = self._update_mapping(item, external_ref)
        ent = self.fetch_quantity(item, external_ref)

        self._create_or_retrieve_cf_sheet(item)

        data = []
        for cf in sorted(ent.factors(), key=lambda x: (x.flowable, x.context.name)):
            for locale in cf.locations:
                row = (cf.flowable, cf.context.name, cf.ref_quantity['name'], cf.ref_quantity.unit,
                       locale, cf[locale], ent.unit)
                data.append(row)
        self._xls.clear_region(item, start_row=1)
        self._xls.write_rectangle_by_rows(item, data, start_row=1)
