from synonym_dict import SynonymDict, TermExists


class StageManager(object):
    """
    A class to handle automatic mapping of stage names, to be used for LciaResult aggregation

    two modes: read-only and writable

    Read-only just reads in the table and executes a mapping of the input string to the selected column
    Writable mode takes a list of stage names as inputs and updates the existing mappings, then writes it to the sheet
    (if supported)
    """

    _xlsx = None
    _sheet = None

    _maps = None
    skip_values = {None, 0, 'NA'}

    @classmethod
    def from_fragment(cls, frag):
        """
        Creates (or updates) a StageManager spreadsheet based on the stages encountered in one fragment and its
        child fragments
        :param frag:
        :return:
        """
        return NotImplemented

    def __init__(self, xlsx, sheetname='stage_names', write=True, default_name='StageName', ignore_case=True):
        self._xlsx = xlsx
        self._sheetname = sheetname
        self._w = bool(write)
        if sheetname not in xlsx.sheet_names():
            if self._w:
                self._xlsx.create_sheet(sheetname)
                self._xlsx.write_row(sheetname, 0, (default_name,))
            else:
                raise KeyError('Sheet %s is missing and write is disabled' % sheetname)

        self._maps = []  # the list of column headers-- these correspond to different mappings of the same set of stages
        self._default = default_name  # the
        self._mappings = dict()
        self._sd = SynonymDict(ignore_case=ignore_case)
        self._sd._ignore_case = ignore_case

        self.read_mappings()

    def _values(self, _adict):
        return filter(lambda x: x not in self.skip_values, _adict.values())

    @property
    def keys(self):
        for k in sorted(self._mappings.keys()):
            yield k

    @property
    def map_columns(self):
        for col in self._maps[1:]:
            yield col

    def drop_column(self, col_name):
        if col_name in self._maps:
            for k in self.keys:
                self._mappings[k].pop(col_name, None)
            self._maps.remove(col_name)

    def _create_or_update_entry(self, row, default=None):
        if default is None:
            default = row[self._default]
        try:
            # update
            key = self._sd[default]
            for v in self._values(row):
                try:
                    self._sd.add_synonym(key, v)
                except TermExists:
                    print('%s: Skipping existing term "%s")' % (default, v))
            return key
        except KeyError:
            # create-- prune = True because
            ent = self._sd.new_entry(default, *self._values(row), prune=True)
            return ent.object  # a synonym set

    def read_mappings(self):
        self._sheet = self._xlsx.sheet_by_name(self._sheetname)
        self._maps = [k.value for k in self._sheet.row(0)]
        if self._default not in self._maps:
            print('warning: default name %s not present in mappings; using %s' % (self._default, self._maps[0]))
            self._default = self._maps[0]
        for i in range(1, self._sheet.nrows):
            row = self._sheet.row_dict(i)
            key = self._create_or_update_entry(row)
            self._mappings[key] = row

    def map_stage_name(self, term, column=1):
        if isinstance(column, str):
            target = column
        else:
            target = self._maps[int(column)]
        try:
            key = self._sd[term]
            mapp = self._mappings[key]
            value = mapp[target]
            return value
        except KeyError:
            return term

    def retrieve(self, lookup, col=None):
        try:
            key = self._sd[lookup]
        except KeyError:
            try:
                key = next(self._sd.objects_with_string(lookup))
            except StopIteration:
                raise KeyError(lookup)
            except TypeError:
                raise ValueError(lookup)
        if col is None:
            return self._mappings[key]
        return self.map_stage_name(key, col)

    def add_map_column(self, col):
        if col in self._maps:
            return  # nothing to do
        else:
            self._maps.append(col)

    def update_mapping(self, term, **kwargs):
        try:
            key = self._sd[term]
            d = self._mappings[key]
            d.update(kwargs)
            self._create_or_update_entry(d, default=key)
        except KeyError:
            d = {self._default: term}
            key = self._create_or_update_entry(kwargs, default=term)
            d.update(kwargs)
        for col, val in kwargs.items():
            self.add_map_column(col)
        self._mappings[key] = d

    def add_synonym(self, term, synonym):
        """

        :param term: existing term
        :param synonym: new synonym
        :return:
        """
        self._sd.add_synonym(term, synonym)

    def prune_keys(self, keys):
        s = set(keys)
        p = set()
        for k in self.keys:
            if k not in s:
                p.add(k)
        for k in p:
            print('Removing %s' % k)
            self._mappings.pop(k)

    def write_mappings(self):
        if not self._w:
            raise AttributeError('Non-writeable')

        self._xlsx.clear_region(self._sheetname)

        self._xlsx.write_row(self._sheetname, 0, self._maps)

        def _row_gen(_key):
            yield _key
            for col in self._maps[1:]:
                _map = self._mappings[_key]
                if col in _map:
                    yield _map[col]
                else:
                    yield None

        def _table_gen():
            for _k in self.keys:
                yield _row_gen(_k)

        self._xlsx.write_rectangle_by_rows(self._sheetname, _table_gen(), start_row=1)

    def __getitem__(self, item):
        return self.retrieve(item)
