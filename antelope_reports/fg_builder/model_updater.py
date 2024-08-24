from antelope_core.entities.xlsx_editor import XlsxUpdater
from antelope_foreground.entities.fragments import InvalidParentChild
from antelope import EntityNotFound, UnknownOrigin


from pandas import to_numeric


def prepare_dataframe(df):
    return df.apply(to_numeric).sort_values(df.columns[0])


def write_results_dataframe_to_gsheet(gsheet, sheetname, df, clear_sheet=True, write_header=True, header_levels=None,
                                      fillna='NA', write_index=True):
    """

    :param gsheet: a GoogleSheetReader
    :param sheetname: sheet to write to or create
    :param df: sorted, prepared data
    :param clear_sheet: [True]
    :param write_header: [True] whether to write header (False: leave it standing)
    :param header_levels: number of header levels to write. Must be <= nlevels
    :param fillna:
    :param write_index:
    :return:
    """

    ncol = len(df.columns)
    if header_levels is None or header_levels > df.columns.nlevels:
        header_levels = df.columns.nlevels

    if sheetname in gsheet.sheet_names():
        # start by clearing the sheet- with or without headers
        if clear_sheet:
            if write_header:
                gsheet.clear_region(sheetname)
            else:
                gsheet.clear_region(sheetname, start_row=header_levels)
        else:
            if write_header:
                gsheet.clear_region(sheetname, end_col=ncol, end_row=header_levels-1)
    else:
        gsheet.create_sheet(sheetname)

    #then populate
    def _row_gen(_df):
        for _i, row in _df.fillna(fillna).iterrows():
            if write_index:
                yield [_i] + list(row.values)
            else:
                yield list(row.values)

    if write_header:
        for i in range(header_levels):
            h = [''] + list(df.columns.get_level_values(i))
            gsheet.write_row(sheetname, i, h)
    gsheet.write_rectangle_by_rows(sheetname, _row_gen(df), start_row=header_levels)



class XlsxForegroundUpdater(XlsxUpdater):
    """
    This subclass introduces the ability to read a ModelFlows sheet for both flows and fragments.  A "flows" sheet
    can also be read if present, but is not required.

    The worksheet with the model flows must have the following mandatory (*) and optional (-) columns (case-sensitive)
    (note that these fields do not have to be defined for every fragment, just present as columns):

    [for flow definition]
     * 'flow' or 'flow_ref' -- external_ref for flow
     * 'ref_quantity' -- external ref for flow's reference quantity
     - 'flowname' -- name of flow (if missing, will be created from the external_ref

    [for fragment definition]
     * 'external_ref' -- name of fragment (blank = unobserved fragment)
     * 'parent' -- external_ref of parent fragment
     * 'direction' -- along with flow above, direction of flow [human-sensible-- see note]
     * 'balance' -- mark 'True' if the fragment is a balancing fragment
     * 'Name' -- fragment name
     * 'StageName' -- fragment stage
     - 'Comment' -- optional

    [for fragment termination]
     * 'exchange_value' -- observed exchange value
     - 'units' -- for conversion -- must be known units to the quantity named in ref_quantity
     * 'termination' --
     * 'term_flow'
     * 'descend'
    """
    @property
    def flow_key(self):
        return self._flow_key

    @flow_key.setter
    def flow_key(self, value):
        if self._flow_key is None:
            self._flow_key = value
        elif value == self._flow_key:
            return
        else:
            raise ValueError('Flow Key mismatch! %s vs %s' % (value, self.flow_key))

    def _populate_frags(self, model_sheet):
        sh, headers = self._sheet_accessor(model_sheet)
        if sh is None:
            return []

        if 'flow' in headers:
            self.flow_key = 'flow'
        elif 'flow_ref' in headers:
            self.flow_key = 'flow_ref'
        else:
            raise AttributeError('Model sheet %s missing flow definition' % model_sheet)

        frags = [{headers[i]: self._grab_value(k) for i, k in enumerate(sh.row(row))} for row in range(1, sh.nrows)]
        return list(filter(lambda x: x.get(self.flow_key), frags))  # filter out entries with blank flow

    def __init__(self, fg, xlrd_like, *model_sheets, **kwargs):
        super(XlsxForegroundUpdater, self).__init__(xlrd_like, **kwargs)
        self._fg = fg
        self._flow_key = None

        self._model_data = []
        if len(model_sheets) == 0:
            model_sheets = ['ModelFlows']

        for model_sheet in model_sheets:
            self._model_data.extend(self._populate_frags(model_sheet))
        self._unrec = []

    @property
    def ar(self):
        return self._fg

    @property
    def origin(self):
        return self._fg.origin

    @property
    def qi(self):
        return self._fg

    _ext_ref_sub = str.maketrans('_-', '  ')

    def _ext_ref_name(self, ext_ref):
        return ext_ref.translate(self._ext_ref_sub).title()

    def _new_entity(self, etype, rowdata):
        if etype == 'flow':
            ext_ref = rowdata.pop('external_ref')
            ref_q = rowdata.pop('referenceQuantity')
            name = rowdata.pop('Name', None) or self._ext_ref_name(ext_ref)
            e = self._fg.add_or_retrieve(ext_ref, ref_q, name, **rowdata)
            if e.entity_type != 'flow':
                raise TypeError('Type conflict encountered on %s [%s != %s]' % (ext_ref, etype, e.entity_type))
        elif etype == 'quantity':
            ext_ref = rowdata.pop('external_ref')
            ref_q = rowdata.pop('referenceUnit')
            name = rowdata.pop('Name', None) or self._ext_ref_name(ext_ref)
            e = self._fg.add_or_retrieve(ext_ref, ref_q, name, **rowdata)
            if e.entity_type != 'quantity':
                raise TypeError('Type conflict encountered on %s [%s != %s]' % (ext_ref, etype, e.entity_type))
        elif etype == 'model_flow':
            ext_ref = rowdata[self.flow_key]
            ref_q = rowdata['ref_quantity']
            if ext_ref.find('/') > 0:
                origin, external_ref = ext_ref.split('/', maxsplit=1)
                name = rowdata.get('flowname') or self._ext_ref_name(external_ref)
                e = self._fg.add_or_retrieve(external_ref, ref_q, name, origin=origin)
            else:
                name = rowdata.get('flowname') or self._ext_ref_name(ext_ref)
                e = self._fg.add_or_retrieve(ext_ref, ref_q, name)
            if e.entity_type != 'flow':
                raise TypeError('Type conflict encountered on %s [%s != %s]' % (ext_ref, 'flow', e.entity_type))
        else:
            raise KeyError('Unknown entity type %s' % etype)

    @property
    def frags(self):
        return self._model_data

    def _grab_model_flows(self):
        """
        First pass through model flows: grab and create flow names so that they can be assigned flow properties
        :return:
        """
        for frag in self.frags:
            try:
                self.get_flow(frag[self.flow_key])
            except EntityNotFound:
                self._new_entity('model_flow', frag)

    def _find_frag(self, frag):
        if frag['external_ref'] is None:
            # infer frag from parent and flow
            parent = self.ar[frag['parent']]
            flow = self.get_flow(frag[self.flow_key])
            try:
                return next(parent.children_with_flow(flow))
            except StopIteration:
                return None
        else:
            return self.ar[frag['external_ref']]  # could itself be None

    def _grab_model_frags(self):
        for frag in self.frags:
            bal = bool(frag.get('balance'))
            if frag['parent'] is None:
                parent = None
            else:
                parent = self.ar[frag['parent']]
                # parent.to_foreground()  # this is now accomplished in fragment constructor via set_parent()
            f = self._find_frag(frag)
            if f is None:
                f = self.ar.new_fragment(frag[self.flow_key], frag['direction'], parent=parent,
                                         balance=bal, Name=frag.get('Name'), StageName=frag.get('StageName'),
                                         Comment=frag.get('Comment'), external_ref=frag['external_ref'])
                if f['Name'] == f.uuid:
                    f['Name'] = f.flow['Name']  # just for human readability

            else:
                if f.flow.external_ref != frag[self.flow_key]:
                    f.flow = self.get_flow(frag[self.flow_key])
                if f.reference_entity != parent:
                    f.unset_parent()
                    f.set_parent(parent)
                if bal != f.is_balance:
                    if bal:
                        try:
                            f.set_balance_flow()
                        except InvalidParentChild:
                            print('Reference Fragment %s cannot set balance' % f)
                    else:
                        f.unset_balance_flow()

                for k in ('Name', 'StageName', 'Comment'):
                    s = frag.get(k)
                    if s is None:
                        continue
                    f[k] = s

    def _terminate_model_frags(self):
        for frag in self.frags:
            f = self._find_frag(frag)
            if f is None:
                raise KeyError('Unable to find this frag! %s' % frag)
            if frag.get('exchange_value') is not None:
                self.ar.observe(f, exchange_value=float(frag['exchange_value']), units=frag.get('units'))
            if frag.get('termination') is None:
                if len(list(f.child_flows)) == 0:
                    f.clear_termination()
                # else- nothing to do- just
                continue
            else:
                if frag['termination'] == 'self':
                    f.to_foreground()
                    continue
                try:
                    term = self.ar.get(frag['termination'])
                except (EntityNotFound, UnknownOrigin):
                    self._unrec.append((f.external_ref, frag['termination']))
                    continue
                if f.term.is_null or f.term.term_node != term:
                    f.clear_termination()
                    # if term.entity_type == 'process':
                    #     f.set_background()  # processes are background-terminated ## outmoded
                    tflow = frag.get('term_flow')
                    if tflow is not None:
                        tflow = self.get_flow(tflow)
                    f.terminate(term, term_flow=tflow)
                desc = {'true': True,
                        'false': False,
                        '0': None}[frag.get('descend', '0').lower()]  # map to bool
                if desc is None:
                    continue
                f.term.descend = desc

    def apply(self):
        for etype in ('quantity', 'flow'):  # these are the only types that are currently handled
            self._process_sheet(etype)
        self._grab_model_flows()
        self._process_flow_properties()
        self._grab_model_frags()
        self._terminate_model_frags()

        if len(self._unrec) > 0:
            print('Unrecognized Terminations: ')
            for frag, term in self._unrec:
                print('  [%s] -> %s' % (frag, term))

    def get_flow(self, flow):
        return self.ar.get(flow)

    def get_context(self, cx):
        return self.ar.context(cx)

    '''
    parameters
    read + update sheet
    '''
    def read_parameters(self, update_default=False):
        """
        Apply all read parameters to the model.
        :param update_default: whether to reset default (observed) values as well
        :return:
        """
        sh, headers = self._sheet_accessor('parameters')
        if sh is None:
            return

        for row in range(1, sh.nrows):
            rowdata = {headers[i]: self._grab_value(k) for i, k in enumerate(sh.row(row))}
            units = rowdata.pop('flow_unit', None)
            knob = self._fg[rowdata.pop('parameter', None)]
            if knob:
                if update_default:
                    self._fg.observe(knob, exchange_value=rowdata.pop('default'), units=units)




