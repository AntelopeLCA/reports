from antelope import EntityNotFound
from antelope_core.contexts import NullContext

from .lc_mfa_study import NestedLcaStudy

from mfatools.aggregation.conventions import logistics_fragment_ref


class ParentlessKnob(Exception):
    """
    Knobs must have parents
    """
    pass


class DynamicUnitLcaStudy(NestedLcaStudy):
    """
    This subclass adds all the build-out machinery that is specific to the CATRA study-- that means:
     1- the Dynamic Unit, which is dynamically specified
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
            return self._fg['Unit Logistics']
        else:
            raise EntityNotFound('Unit Logistics')

    @property
    def dynamic_unit(self):
        """
        The Dynamic Unit is a structure that enables scenarios to be created within the Mfa study superstructure
        that simulate unit activities in the broader structure.  The unit is installed as a study object within the
        activity container.  It has the name 'Unit' and the following structure:

        <--[unit ref]--O  {'Unit'} (activity)
                       |
                       +-=>=-O reference material (mass balance)
                             |
                             +-=>=-O reference material (mass balance) {'Unit - Dynamic Sinks'}
                             |     |
                             |     +-=>=-  dynamic balance (mass balance) (cutoff)
                             |
                             +-[1.0]>-O unit ref {'Unit - Dynamic Supplies'}
                                      |
                                      +-[1.0]>-O reference material {'Unit Logistics'}

        Upon creation, the dynamic unit will not do anything because its only child flow is a mass balance.
        The user makes the dynamic useful by adding "knobs" to turn in the following places:

        add_unit_source-- adds an Input child flow to 'Unit', to drive the mass balance
        add_unit_sink-- adds an output child flow to 'Unit - Dynamic Sinks' to drive a downstream process
         (note, dynamic sinks are driven by the balance of sources)
        add_unit_supply-- adds an input child flow to 'Unit - Dynamic Supplies'
         (note, dynamic supplies are with respect to a unit magnitude of the reference material)
        add_logistics_route-- adds an input child flow to 'Unit Logistics'
         (note, logistics are with respect to a unit magnitude of the reference material)

        After the knobs have been created, the user can specify knob "settings" for each scenario.

        :return:
        """
        try:
            return self._fg.get('Unit')
        except EntityNotFound:
            unit_ref = self.new_activity_flow('Unit Reference Flow', external_ref='unit_reference_flow')
            unit = self._fg.new_fragment(unit_ref, 'Output', name='%s - Dynamic Unit' % self._ref, external_ref='Unit')
            b = self._fg.new_fragment(self.reference_material, 'Output', parent=unit, balance=True)
            c = self._fg.new_fragment(self.reference_material, 'Output', parent=b, balance=True, external_ref='Unit - Dynamic Sinks')
            self._fg.new_fragment(self.unit_balance_flow, 'Output', parent=c, balance=True)
            d = self._fg.new_fragment(unit_ref, 'Output', parent=b, exchange_value=1.0, external_ref='Unit - Dynamic Supplies')
            self._fg.observe(d)  # lock in the 1.0 exchange value
            # d.to_foreground()  # this is now accomplished in new fragment constructor via set_parent()
            rl = self._fg.new_fragment(self.reference_material, 'Output', parent=d, exchange_value=1.0, external_ref='Unit Logistics')
            rl.terminate(NullContext)  # replaces to_foreground()
            self._fg.observe(rl)  # lock in the 1.0 exchange value

            self._fg.observe(self.activity_container, termination=unit, scenario='Unit')
        return self._fg.get('Unit')

    def add_unit_source(self, knob, source, descend=False, term_map=None):
        """
        Simply installs the named flow as a source knob-- an inflow to the unit model.  If the supplied source
        is a flow, it is assumed to be terminated in the study layer.  If it is a fragment, then its inventory
        flows are terminated according to the term_map.

        Note: term_map entries must be ENTITIES and not REFs.  This is b/c of the mfa vs models vs study conundrum.
        :param knob: a string
        :param source:
        :param descend: [False] whether the traversal should descend [True] or aggregate [False] the knob
        :param term_map
        :return:
        """
        return self._add_unit_knob(knob, source, 'Input', self.dynamic_unit, descend, term_map)

    def add_unit_sink(self, knob, sink, descend=False, term_map=None):
        """

        :param knob:
        :param sink:
        :param descend: [False] whether the traversal should descend [True] or aggregate [False] the knob
        :param term_map:
        :return:
        """
        parent = self._fg.get('Unit - Dynamic Sinks')
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
        parent = self._fg.get('Unit - Dynamic Supplies')
        return self._add_unit_knob(knob, supply, direction, parent, descend, term_map)

    def add_logistics_route(self, flow, provider, descend=False, term_map=None, **kwargs):
        c = super(DynamicUnitLcaStudy, self).add_logistics_route(flow, provider, descend=descend, **kwargs)
        return self._add_unit_knob(c.flow.name, c.flow, 'Input', self.unit_logistics, descend, term_map=term_map)

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
            if isinstance(entry, str):
                entry = self._resolve_term(entry)
            if entry.entity_type == 'flow':
                k = self._fg.new_fragment(entry, direction, parent=parent, value=0, external_ref=knob)
            elif entry.entity_type == 'fragment':
                k = self._fg.new_fragment(entry.flow, entry.direction, parent=parent, value=0, external_ref=knob)
                k.terminate(entry, descend=descend)
                if term_map:
                    self._add_child_flows(k, entry, term_map)
            else:
                raise TypeError('Improper type %s (%s)' % (type(entry), entry))
        return k

    def _add_child_flows(self, frag, term, dynamic_outputs):
        for k in term.inventory():
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
        try:
            cf = next(self.activity_container.children_with_flow(self.unit_balance_flow))
        except StopIteration:
            cf = self.fg.new_fragment(self.unit_balance_flow, 'Output', parent=self.activity_container)
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

