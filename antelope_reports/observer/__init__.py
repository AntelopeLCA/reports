from antelope_foreground.foreground_catalog import NoSuchForeground, ForegroundQuery
from antelope import EntityNotFound, enum, comp_dir

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

    def __init__(self, fg, terms=None, xlsx=None):
        self._fg = fg
        self._terms = {}
        self._xlsx = None
        self.set_terms(terms)
        if xlsx:
            self.xlsx = xlsx

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
            self.fg.apply_xlsx(xlsx)
            self._xlsx = xlsx

    @property
    def fg(self):
        return self._fg

    def terms(self, term):
        return self._terms[term]

    def find_background_rx(self, origin, external_ref=None, process_name=None, flow_name=None, strict=True, **kwargs):
        """
        The purpose of this is to retrieve a unique termination from a user specification. 
        Order of preference here is as follows:
        if external_ref is supplied, just get the straight catalog ref
        otherwise if process_name is supplied, search for it by name (regex) with filters; return rx matching flow_name
        otherwise, search for flow_name in origin, filtering by non-elementary context, then find targets with filtering
        
        :param origin: 
        :param external_ref: 
        :param process_name: 
        :param flow_name: 
        :param strict: [True] If true, raise an AmbiguousResult exception if multiple hits are found; if False, go
         ahead and use the "first" (which is nondetermininstic).  Provide kwargs to filter.
        :param kwargs: 
        :return: 
        """
        if external_ref:
            term = self.fg.catalog_ref(origin, external_ref)
        else:
            query = self.fg.catalog_query(origin)
            if process_name:
                try:
                    term = self._get_one(query.processes(Name='^%s$' % process_name, **kwargs), strict=strict)
                except EntityNotFound:
                    term = self._get_one(query.processes(Name='^%s' % process_name, **kwargs), strict=strict)
            else:
                try:
                    flow = query.get(flow_name)
                except EntityNotFound:
                    flows = filter(lambda x: not self.fg.context(x.context).elementary,
                                   query.flows(Name='^%s$' % flow_name))
                    flow = self._get_one(flows, strict=strict)

                if hasattr(query, 'fragments_with_flow'):
                    term = self._get_one(query.fragments_with_flow(flow, reference=True))
                else:
                    processes = flow.targets()
                    for k, v in kwargs.items():
                        if v is None:
                            continue
                        processes = list(filter(lambda x: bool(re.search(v, x.get(k), flags=re.I)), processes))
                    term = self._get_one(processes, strict=strict)

        return term.reference(flow_name)

    def _new_reference_fragment(self, flow, direction, external_ref):
        frag = self.fg[external_ref]
        if frag is None:
            frag = self.fg.new_fragment(flow, direction, external_ref=external_ref)

        return frag

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

    def to_background(self, bg, origin, external_ref=None, process_name=None, flow_name=None, locale=None,
                      scenario=None,
                      scaleup=1.0,
                      **kwargs):
        """
        This takes a new link and terminates it via balance to a background node that is retrieved by search
        :param bg:
        :param origin:
        :param external_ref:
        :param process_name:
        :param flow_name:
        :param locale:
        :param scenario:
        :param scaleup:
        :return:
        """
        kwargs.update({'process_name': process_name, 'flow_name': flow_name, 'external_ref': external_ref})
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
            z.to_foreground()  # truncates
