from antelope import EntityNotFound

from .observed_mfa_study import ObservedMfaStudy

# from mfatools.aggregation.conventions import logistics_fragment_ref

from typing import Dict, Optional
from pydantic import BaseModel


def logistics_fragment_ref(fragment):
    return '%s_inbound_logistics' % fragment.external_ref


class DynamicUnitSpec(BaseModel):
    term_map: Dict[str, str] = dict()  # {flow ref: flow or terminal reference} to terminate CUTOFFS of enclosed models
    sources: Dict[str, str]  # {knob name: flow or enclosed model reference} of INFLOWS to the unit model
    sinks: Dict[str, str]  # {knob name: flow or enclosed model reference} of mass-balanced OUTFLOWS
    supplies: Dict[str, str]  # {knob name: flow or enclosed model reference} of supply use per kg of throughflow
    balance_flow: Optional[str] = None  # external ref of flow to be used for the balance output from the dynamic unit


class ParentlessKnob(Exception):
    """
    Knobs must have parents
    """
    pass


class DynamicUnitLcaStudy(ObservedMfaStudy):
    """
    This subclass takes the observed study machinery (to specify routes) adds the Dynamic Unit, which is like a synthetic MFA observation
     2-
    """
    @property
    def unit_balance_flow(self):
        return self.fg.add_or_retrieve('unit_balance', 'mass', 'Dynamic Unit Balance Flow')

    @property
    def reference_material(self):
        return self.fg.add_or_retrieve('reference_material', 'mass', 'Reference Material')

    @property
    def unit_logistics(self):
        if self.dynamic_unit:  # create if doesn't exist
            return self._fg['unit_logistics']
        else:
            raise EntityNotFound('unit_logistics')

    def make_logistics_mappings(self, logistics_mappings, add_knob=True):
        for k, v in logistics_mappings.items():
            t, stage = v
            cf = self.make_study_mapping(self.logistics_container, k, 'Input', t, stage=stage)
            if add_knob:
                # also add a logistics knob to the unit logistics model-- we could do this in general....
                knob = cf.flow.name
                knob = knob.translate(str.maketrans('/ ()', '--__'))
                print('doing unit logs %s' % knob)
                self._add_unit_knob(knob, cf.flow, 'Input', self.unit_logistics, descend=False)

    @property
    def dynamic_unit(self):
        """
        The Dynamic Unit is a structure that enables scenarios to be created within the Mfa study superstructure
        that simulate unit activities in the broader structure.  The unit is installed as a study object within the
        activity container.  It has the name 'unit_model' and the following structure:

        <--[unit ref]--O  {'unit_model'} (activity)
                       |
                       +-=>=-O reference material (mass balance)
                             |
                             +-=>=-O reference material (mass balance) {'unit-dynamic_sinks'}
                             |     |
                             |     +-=>=-  dynamic balance (mass balance) (cutoff)
                             |
                             +-[1.0]>-O unit ref {'unit-dynamic_supplies'}
                                      |
                                      +-[1.0]>-O reference material {'unit_logistics'}

        Upon creation, the dynamic unit will not do anything because its only child flow is a mass balance.
        The user makes the dynamic useful by adding "knobs" to turn in the following places:

        add_unit_source-- adds an Input child flow to 'unit_model', to drive the mass balance
        add_unit_sink-- adds an output child flow to 'unit-dynamic_sinks' to drive a downstream process
         (note, dynamic sinks are driven by the balance of sources)
        add_unit_supply-- adds an input child flow to 'unit-dynamic_supplies'
         (note, dynamic supplies are with respect to a unit magnitude of the reference material)
        add_logistics_route-- adds an input child flow to 'unit_logistics'
         (note, logistics are with respect to a unit magnitude of the reference material)

        After the knobs have been created, the user can specify knob "settings" for each scenario.

        :return:
        """
        try:
            return self._fg.get('unit_model')
        except EntityNotFound:
            unit_ref = self.new_activity_flow('Unit Reference Flow', external_ref='unit_reference_flow')
            unit = self._fg.new_fragment(unit_ref, 'Output', name='%s - Dynamic Unit' % self._ref, external_ref='unit_model')
            b = self._fg.new_fragment(self.reference_material, 'Output', parent=unit, balance=True)
            c = self._fg.new_fragment(self.reference_material, 'Output', parent=b, balance=True, external_ref='unit-dynamic_sinks')
            self._fg.new_fragment(self.unit_balance_flow, 'Output', parent=c, balance=True)
            d = self._fg.new_fragment(unit_ref, 'Output', parent=b, exchange_value=1.0, external_ref='unit-dynamic_supplies')
            self._fg.observe(d)  # lock in the 1.0 exchange value
            # d.to_foreground()  # this is now accomplished in new fragment constructor via set_parent()
            rl = self._fg.new_fragment(self.reference_material, 'Output', parent=d, exchange_value=1.0, external_ref='unit_logistics')
            # rl.terminate(NullContext)  # replaces to_foreground() we do not want this going to context!
            self._fg.observe(rl)  # lock in the 1.0 exchange value

            self._fg.observe(self.activity_container, termination=unit, scenario='Unit')
        return self._fg.get('unit_model')

    def add_unit_source(self, knob, source, descend=False, term_map=None):
        """
        Simply installs the named flow as a source knob-- an inflow to the unit model.  If the supplied source
        is a flow, it is assumed to be terminated in the study layer.  If it is a fragment, then its inventory
        flows are terminated according to the term_map.

        :param knob: a string
        :param source:
        :param descend: [False] whether the traversal should descend [True] or aggregate [False] the knob
        :param term_map: if source is a model, mapping of source's cutoffs to background terminations or flows
        :return:
        """
        ''' The following comment appears to be false and was removed:
        Note: term_map entries must be ENTITIES and not REFs.  This is b/c of the mfa vs models vs study conundrum.
        '''
        return self._add_unit_knob(knob, source, 'Input', self.dynamic_unit, descend, term_map)

    def add_unit_sink(self, knob, sink, descend=False, term_map=None):
        """

        :param knob:
        :param sink:
        :param descend: [False] whether the traversal should descend [True] or aggregate [False] the knob
        :param term_map:
        :return:
        """
        parent = self._fg.get('unit-dynamic_sinks')
        return self._add_unit_knob(knob, sink, 'Output', parent, descend, term_map)

    def add_unit_supply(self, knob, supply, direction='Input', descend=False, term_map=None):
        """
        In the current construction, supply knobs MUST be reported PER kg of flow through the dynamic unit.
        
        (alternative design would be to make the dynamic supply a child of the dynamic unit, and they would be 
        absolute amounts per unit.) 
        
        :param knob:
        :param supply:
        :param direction: default Input
        :param descend: [False] whether the traversal should descend [True] or aggregate [False] the knob
        :param term_map:
        :return:
        """
        parent = self._fg.get('unit-dynamic_supplies')
        return self._add_unit_knob(knob, supply, direction, parent, descend, term_map)

    '''
    def add_logistics_route(self, flow, provider, descend=False, term_map=None, **kwargs):
        c = super(DynamicUnitLcaStudy, self).add_logistics_route(flow, provider, descend=descend, **kwargs)
        knob = c.flow.name
        knob = knob.replace('/', '_')
        return self._add_unit_knob(knob, c.flow, 'Input', self.unit_logistics, descend, term_map=term_map)
    '''

    def _add_unit_knob(self, knob, entry, direction, parent, descend=None, term_map=None):
        """

        :param knob: a string knob name-- the "knob" fragment will be assigned this external_ref
        :param entry: what does the knob twiddle? string gets resolved to entity.
         flow- will just be a cutoff, to be plumbed to the activity/logistics/product layers
         fragment- will get terminated
        :param direction: sources should be 'Input', sinks should be 'Output'
        :param parent: where does the knob get added?
        :param descend: whether the traversal should descend [True] or aggregate [False] the knob. (term_map flows are
         always non-descend)
        :param term_map:
        :return:
        """
        if parent is None:
            raise ParentlessKnob(knob)
        try:
            k = self._fg.get(knob)
        except EntityNotFound:
            resolved_entry = self._resolve_term(entry)
            if resolved_entry.entity_type == 'flow':
                k = self._fg.new_fragment(resolved_entry, direction, parent=parent, value=0, external_ref=knob)
            elif resolved_entry.entity_type == 'fragment':
                k = self._fg.new_fragment(resolved_entry.flow, resolved_entry.direction, parent=parent, value=0,
                                          external_ref=knob)
                k.terminate(resolved_entry, descend=descend)
                if term_map:
                    self._add_child_flows(k, resolved_entry, term_map)
            else:
                raise TypeError('Improper type %s (%s)' % (type(resolved_entry), resolved_entry))
        return k

    def _add_child_flows(self, frag, term, dynamic_outputs):
        for k in term.cutoffs():
            if not k.is_reference:
                if k.flow.external_ref in dynamic_outputs:
                    v = self._resolve_term(dynamic_outputs[k.flow.external_ref])
                    if v.entity_type == 'flow':
                        o = self._fg.new_fragment(k.flow, k.direction, parent=frag)
                        self._fg.new_fragment(v, k.direction, parent=o, balance=True)
                    elif v.entity_type == 'fragment':
                        o = self._fg.new_fragment(k.flow, k.direction, parent=frag)
                        o.terminate(v, term_flow=v.flow, descend=False)

    def set_unit_balance(self, flow):
        bf = self._resolve_term(flow)
        cf = self.fg['unit-dynamic_sinks'].balance_flow
        df = cf.balance_flow
        if df is None:
            self.fg.new_fragment(bf, 'Output', parent=cf, balance=True)
        else:
            df.flow = bf

    def install_observation_model(self, prov_frag, scope=None):
        super(DynamicUnitLcaStudy, self).install_observation_model(prov_frag, scope=scope)

        log_ref = logistics_fragment_ref(prov_frag)
        prov_log = self.data[log_ref]  # should also be a convention?
        if prov_log is None:
            print('No provincial logistics found!')
        else:
            self.unit_logistics.clear_termination('Unit-%s' % scope)
            self.unit_logistics.terminate(prov_log, 'Unit-%s' % scope)

    def make_dynamic_unit(self, unit_spec: DynamicUnitSpec, descend=False):
        for k, v in unit_spec.sources.items():
            self.add_unit_source(k, v, descend=descend, term_map=unit_spec.term_map)
        for k, v in unit_spec.sinks.items():
            self.add_unit_sink(k, v, descend=descend, term_map=unit_spec.term_map)
        for k, v in unit_spec.supplies.items():
            self.add_unit_supply(k, v, descend=descend, term_map=unit_spec.term_map)
        if unit_spec.balance_flow:
            self.set_unit_balance(unit_spec.balance_flow)



