from antelope_foreground.foreground_catalog import NoSuchForeground

from antelope_core.contexts import NullContext
from antelope import ConversionError
from antelope import EntityNotFound, enum, MultipleReferences

from .observations_from_spreadsheet import ObservationsFromSpreadsheet

from .exchanges_from_spreadsheet import exchanges_from_spreadsheet

import re

tr = str.maketrans(' ', '_', ',[]()*&^%$#@')


class AmbiguousResult(Exception):
    """
    Raised when there are several choices after filtering, and strict is True
    """
    pass


class MissingValue(Exception):
    """
    Used when a quick-link spec is missing a value and no parent is provided
    """
    pass


def _flow_to_ref(name):
    n = name.translate(tr).lower()
    if n.startswith('flow_'):
        fl = n
    else:
        fl = 'flow_' + n
    return fl


class QuickAndEasy(object):
    """
    This is a basic support class for building operable, linked models from basic specifications provided by the
    user.  It assumes that modeling information is stored in an xlrd-like document, canonically a google sheets
    spreadsheet is preferred because it is so easy to both read and write content on-the-fly*.

    The class includes the following features:
     - fg - an Antelope foreground
     - xlsx - a spreadsheet conforming with the antelope_core.archives.xlsx_updater.XlsxUpdater spec
     - terms - a dictionary of keywords to pre-defined anchors that are used in the model
     - find_background_rx() - a heuristic pathway to convert an open-ended anchor specification into a reference flow
     - new_link() - a function to create a new link in a fragment tree
     - to_background() - a utility function that finds an anchor for a fragment link (invokes find_background_rx())
     - add_tap() - a fundamental feature that converts a background exchange into an observable foreground exchange
     - load_process_model() - creates a model from a spreadsheet specification using exchanges_from_spreadsheet


    More features are added in the ModelMaker subclass.


    * - Writing to the document is NOT required in any of the core functions, however it is useful when the XLSX
     document contains parameters and scenarios that may be altered programmatically.

     In principle it should also be easy to write to e.g. openpyxl spreadsheets, but it is not the case because
     those spreadsheets have explicitly separate in-memory and on-disk versions.  To achieve the same functionality
     as we get with the google doc, we would have to write the change in-memory, save the change to disk, and then
     re-load the file.  That is all upstream in xlstools; for now we are sticking with google docs only.
    """

    def _get_one(self, hits, strict=False, **kwargs):
        hits = list(hits)
        if len(hits) == 1:
            return hits[0]
        elif len(hits) == 0:
            raise EntityNotFound
        else:
            _ = enum(hits)
            if strict:
                raise AmbiguousResult('Ambiguous termination: %d results found' % len(hits))
            print('Warning: Ambiguous termination: %d results found' % len(hits))
            return hits[0]

    @classmethod
    def by_name(cls, cat, fg_name, terms=None, **kwargs):
        """
        NOTE: this resets the foreground.  this is a bit foolish given how badly we handle reset foregrounds.
        :param cat:
        :param fg_name:
        :param terms:
        :param kwargs:
        :return:
        """
        try:
            fg = cat.foreground(fg_name, reset=True)
        except NoSuchForeground:
            fg = cat.create_foreground(fg_name)
        return cls(fg, terms=terms, **kwargs)

    def set_terms(self, terms):
        if terms:
            for k, v in terms.items():
                self._terms[k] = self.fg.catalog_ref(*v)

    def _populate_unit_map(self):
        for q in ('mass', 'volume', 'net calorific value', 'number of items',
                  'length', 'area', 'freight', 'vehicle transport', 'person transport'):  # last one stated wins
            q_can = self.fg.get_canonical(q)
            self.add_to_unit_map(q_can)
        kwh = self.fg.get_canonical('kWh')
        for u in ('kWh', 'MWh', 'GWh'):
            try:
                kwh.convert(u)
                self._unit_map[u] = kwh.external_ref
            except ConversionError:
                pass

    def add_to_unit_map(self, quantity):
        for u in quantity['unitconversion'].keys():
            self._unit_map[u] = quantity.external_ref

    def __init__(self, fg, terms=None, xlsx=None, quiet=True, taps=None):
        """
        A quick-and-easy model builder.  Pass in a foreground to work with, a dictionary of terms mapping nickname to
        origin + external ref, and an optional XlrdLike spreadsheet
        :param fg:
        :param terms: (k, (v,...)). Creates a map of keyname k to CatalogRef(*v). Used to terminate inventory flows.
        :param xlsx:
        :param quiet: passed to fg archive builder
        :param taps: name of spreadsheet containing flow taps (flow origin + ref tapped to target origin + ref)
        :param
        """
        self._fg = fg
        self._terms = {}
        self._xlsx = None
        self._quiet = quiet
        self.set_terms(terms)
        self._unit_map = dict()
        self._populate_unit_map()
        self._taps = {}

        if xlsx:
            self.xlsx = xlsx

        if taps:
            self.load_taps(taps)

    @property
    def xlsx(self):
        return self._xlsx

    @xlsx.setter
    def xlsx(self, xlsx):
        """
        Automatically loads quantities, flows, and flowproperties
        :param xlsx:
        :return:
        """
        if xlsx:
            self._xlsx = xlsx
            self.refresh_entities()

    def refresh_entities(self, quiet=None):
        if self._xlsx is None:
            raise ValueError('xlsx is missing')
        if quiet is None:
            quiet = self._quiet
        try:
            self.fg.apply_xlsx(self._xlsx, quiet=quiet)
        except AttributeError:
            next(self.fg._iface('foreground')).apply_xlsx(self._xlsx, quiet=quiet)

    @property
    def fg(self):
        return self._fg

    def __getitem__(self, item):
        e = self.fg.__getitem__(item)
        if e is None:
            # the buck has to stop somewhere
            raise KeyError(item)
        return e

    def terms(self, term):
        return self._terms[term]

    def get_flow_by_name_or_ref(self, origin, flow_name_or_ref, strict=True):
        query = self.fg.cascade(origin)
        try:
            flow = query.get(flow_name_or_ref)
        except EntityNotFound:
            flows = filter(lambda x: not self.fg.get_context(x.context).elementary,
                           query.flows(Name='^%s$' % flow_name_or_ref))
            flow = self._get_one(flows, strict=strict)
        return flow

    def find_background_rx(self, origin, external_ref=None, process_name=None, flow_name_or_ref=None, strict=True,
                           **kwargs):
        """
        The purpose of this is to retrieve a unique termination from a user specification. 
        Order of preference here is as follows:
        if external_ref is supplied, just get the straight catalog ref: origin + external_ref

        otherwise if process_name is supplied, search for it by name (regex) with filters; return rx matching flow_name
        otherwise, search for flow_name in origin, filtering by non-elementary context, then find targets with filtering
        (this includes fragments_with_flow() if the origin is a foreground)
        
        :param origin: 
        :param external_ref: 
        :param process_name: exact name of background process
        :param flow_name_or_ref: exact flow name OR external ref of flow
        :param strict: [True] If true, raise an AmbiguousResult exception if multiple hits are found; if False, go
         ahead and use the "first" (which is nondetermininstic).  Provide kwargs to filter.
        :param kwargs: 
        :return: 
        """
        if external_ref:
            term = self.fg.cascade(origin).get(external_ref)
        else:
            query = self.fg.cascade(origin)
            if process_name:
                try:
                    term = self._get_one(query.processes(Name='^%s$' % process_name, **kwargs), strict=strict)
                except EntityNotFound:
                    term = self._get_one(query.processes(Name='^%s' % process_name, **kwargs), strict=strict)
            elif flow_name_or_ref:
                flow = self.get_flow_by_name_or_ref(origin, flow_name_or_ref, strict=strict)

                if hasattr(query, 'fragments_with_flow'):
                    term = self._get_one(query.fragments_with_flow(flow, reference=True))
                else:
                    processes = flow.targets()
                    for k, v in kwargs.items():
                        if v is None:
                            continue
                        processes = list(filter(lambda x: bool(re.search(v, x.get(k), flags=re.I)), processes))
                    term = self._get_one(processes, strict=strict)
            else:
                raise AmbiguousResult('Either process_name or flow_name must be provided')

        try:
            return term.reference()
        except MultipleReferences:
            return term.reference(flow_name_or_ref)

    def _new_reference_fragment(self, flow, direction, external_ref):
        frag = self.fg[external_ref]
        if frag is None:
            frag = self.fg.new_fragment(flow, direction, external_ref=external_ref)

        return frag

    # this is from a misbegotten demo
    def new_link(self, flow_name, ref_quantity, direction, amount=None, units=None, flow_ref=None, parent=None, name=None,
                 stage=None,
                 prefix='frag',
                 balance=None):
        """
        Just discovered that 'balance' is actually a direction

        am I writing fragment_from_exchanges *again*? this is the API, this function right here

        NO
        the api is fragment_from_exchange. and yes, i am writing it again.

        The policy of this impl. is to create from scratch.  no need to re-run + correct: just scratch and throw out

        :param flow_name:
        :param ref_quantity: of flow
        :param direction: of fragment
        :param amount:
        :param units:
        :param flow_ref:
        :param parent:
        :param name:
        :param stage:
        :param prefix: what to add to the auto-name in order to
        :param balance: direction='balance' should be equivalent;; direction is irrelevant under balance
        :return:
        """
        if flow_ref is None:
            flow_ref = _flow_to_ref(flow_name)

        flow = self.fg.add_or_retrieve(flow_ref, ref_quantity, flow_name)

        external_ref = name or None
        if parent is None:
            if flow_ref.startswith('flow_'):
                auto_name = flow_ref[5:]
            else:
                auto_name = '%s_%s' % (prefix, flow_ref)
            external_ref = external_ref or auto_name

            frag = self._new_reference_fragment(flow, direction, external_ref)
            self.fg.observe(frag, exchange_value=amount, units=units)
        else:
            if direction == 'balance':
                balance = True
            if balance:
                frag = self.fg.new_fragment(flow, direction, parent=parent, balance=True)
            else:
                frag = self.fg.new_fragment(flow, direction, value=1.0, parent=parent, external_ref=external_ref)
                self.fg.observe(frag, exchange_value=amount, units=units)

        if stage:
            frag['StageName'] = stage

        return frag

    '''
    def to_background(self, bg, origin, external_ref=None, process_name=None, flow_name=None, locale=None,
                      scenario=None,
                      scaleup=1.0,
                      **kwargs):
        """
        This takes a new link and terminates it via balance to a background node that is retrieved by search
        :param bg:
        :param origin:
        :param external_ref:
        :param process_name: exact name of process
        :param flow_name: exact name or ref of flow
        :param locale:
        :param scenario:
        :param scaleup:
        :return:
        """
        kwargs.update({'process_name': process_name, 'flow_name_or_ref': flow_name, 'external_ref': external_ref})
        if locale:
            kwargs['SpatialScope'] = locale

        rx = self.find_background_rx(origin, **kwargs)

        child = bg.balance_flow
        if child is None:
            child = self.fg.new_fragment(bg.flow, bg.direction, parent=bg, balance=True,
                                         StageName=bg['StageName'])

        child.clear_termination(scenario)
        child.terminate(rx.process, term_flow=rx.flow, scenario=scenario)
        if scaleup != 1.0:
            scaleup_adj = scaleup - 1.0
            try:
                z = next(k for k in bg.children_with_flow(bg.flow) if k is not child)
            except StopIteration:
                z = self.fg.new_fragment(bg.flow, comp_dir(bg.direction), parent=bg)
            ev = bg.exchange_value(scenario, observed=True) * scaleup_adj
            self.fg.observe(z, exchange_value=ev, scenario=scenario)
            z.terminate(NullContext)  # truncates
    '''

    def add_tap(self, parent, child_flow, direction='Input', scenario=None, term=None, term_flow=None,
                include_zero=False, **kwargs):
        """
        Use fragment traversal to override an exchange belonging to a terminal activity.
         - retrieve the termination for the appropriate scenario
         - compute the exchange relation for the specified flow exchanged with the terminal node
         - add or retrieve a child flow with the specified flow
         - observe the child flow to have the same exchange value as the computed exchange
         - optionally, terminate the child flow to the designated termination (or to foreground)

        :param parent:
        :param child_flow:
        :param direction: ['Input'] exchange direction w/r/t parent
        :param scenario:
        :param term: what to terminate the child flow to. None = cutoff. True = to foreground. all others = term node
        :param term_flow:
        :param include_zero: [False] whether to add and include child flows with observed 0 EVs
        :param kwargs: passed to new fragment creation
        :return:
        """
        t = parent.termination(scenario)
        ev = t.term_node.exchange_relation(t.term_flow, child_flow, direction)
        if ev == 0:
            if not include_zero:
                print('Child child_flow returned 0 exchange', parent, child_flow)
                return None

        try:
            c = next(parent.children_with_flow(child_flow, direction=direction))
        except StopIteration:
            c = self.fg.new_fragment(child_flow, direction, parent=parent, **kwargs)
        self.fg.observe(c, exchange_value=ev, scenario=scenario)
        if term is not None:
            if term is True:
                c.terminate(NullContext)
            else:
                c.terminate(term, term_flow=term_flow, scenario=scenario)

        return c

    def load_taps(self, sheetname='taps'):
        sheet = self.xlsx[sheetname]
        for r in range(1, sheet.nrows):
            row = sheet.row_dict(r)
            try:
                flow = self.get_flow_by_name_or_ref(row['flow_origin'], row['flow_name_or_ref'], strict=True)
            except (KeyError, AmbiguousResult) as e:
                print('Loading tap from row %d: %s (%s) - skipping' % (r+1, e.__class__.__name__, e.args[0]))
                continue
            tgt_origin = row.get('target_origin', 'here')
            if tgt_origin == 'here':
                tgt = self.fg.get(row['target_ref'])
            else:
                tgt = self.fg.cascade(tgt_origin).get(row['target_ref'])
            direction = row.get('direction', 'Input')

            self._taps[flow] = direction, tgt

    def load_process_model(self, sheetname, prefix=None):
        """

        :param self:
        :param sheetname:
        :param prefix:
        :return:
        """
        sheet = self.xlsx[sheetname]
        if prefix:
            ref = '%s_%s' % (prefix, sheetname)
        else:
            ref = sheetname

        exch_gen = exchanges_from_spreadsheet(sheet, origin=self.fg.origin)
        parent = self.fg[ref]  # this is BACKWARDS from standard- .get is supposed to silently return None !!MAJOR ALERT
        if parent is None:
            fproc = self.fg.fragment_from_exchanges(exch_gen, ref=ref, term_dict=self._terms)
        else:
            next(exch_gen)  # nowhere do we apply the incoming exch_gen to the parent!?
            fproc = self.fg.fragment_from_exchanges(exch_gen, parent=parent, term_dict=self._terms)

        fproc['StageName'] = sheetname

        fproc.show_tree(True)
        return fproc

    def apply_observations(self, sheetname='observations'):
        scs = self.xlsx[sheetname]
        with ObservationsFromSpreadsheet(self.fg, scs) as obs:
            obs.apply()
