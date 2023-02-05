from antelope import EntityNotFound, UnknownOrigin, MultipleReferences, check_direction

from .quick_and_easy import QuickAndEasy, AmbiguousResult


class ConsistencyError(Exception):
    pass


class NoInformation(Exception):
    """
    Not even enough info to make a cutoff flow
    """
    pass


class FailedTermination(Exception):
    pass


class BadExchangeValue(Exception):
    pass


class BadDisplacementRelation(Exception):
    """
    Something is wrong with the displacement table entry
    """
    pass


class DispositionError(Exception):
    pass


class ModelMaker(QuickAndEasy):
    """
    This class enhances QuickAndEasy with some useful tools for building product models:

     - create_or_retrieve_reference() - a utility that retrieves or else creates a fragment with a specified flow
     - make_production_row() - construct a single child flow from an entry in the production spreadsheet (see spec below)
     - make_production() - make/update all production, reference flows + child flows.  idempotent.
     - make_displacement_model() - make/update one model from an entry in the displacement spreadsheet (see spec below)
     - make_displacement() - make/update all displacement models

    Production Sheet: (default 'production') Columns:
    reference spec: should be the same for every entry for a given reference flow
    (these are used in create_or_retrieve_reference())
    prod_flow	-- the external_ref of the flow that is used as the reference flow. Only one production model per flow.
    ref_direction	-- direction of the reference w.r.t the fragment (i.e. comp_dir w.r.t. use)
    ref_value	-- observed exchange value of the reference flow
    ref_unit	-- unit of measure of the observation

    child flow spec: each nonempty row generates one child flow
    (these are used in make_production_row())
    direction	-- direction of the child flow w.r.t. the parent node
    amount	-- observed exchange value of the reference flow
    balance_yn	-- boolean (could begin to accept 'balance' as a direction spec instead)
    amount_hi	-- observed exchange value for high sensitivity case (not yet implemented)
    amount_lo	-- observed exchange value for high sensitivity case (not yet implemented)
    units	-- unit of measure for amount, amount_hi, amount_lo
    stage_name	-- fragment 'StageName' property
    scenario	-- support for alternative exchange value + anchor scenario specifications (not yet implemented)
    note	-- fragment 'note' property
    Comment	-- fragment 'Comment' property

    anchor spec:
    (these are used in _find_term_info(), ultimately passed to find_background_rx()
    origin	-- origin for anchor node (context or cutoff if absent)
    compartment	-- used for context flows if origin is not specified
    flow_name	-- external ref of child flow; or passed to find_background_rx
    locale	-- used as SpatialScope argument in find_background_rx
    target_name	-- used as process_name argument in find_background_rx
    external_ref	-- passed to find_background_rx

    The regression is as follows:
      if origin is specified:
         origin == 'here' -> look in local foreground
         pass a dict to find_background_rx containing:
         external_ref, target_name (as process_name), flow_name, locale (as SpatialScope)
      else:
         if compartment is specified:
            retrieve context
         else:
            create cutoff

    Displacement sheet: (default 'displacement') Columns:
    in_use	-- (bool) whether to make an entry for this row

    Defining the displacement relationship
    md_flow	-- materially-derived flow that is driving the displacement
    mdflow_refprop	-- a vlookup provided for the xlsx editor's convenience: =vlookup(md_flow,flow_ref_qty,2,false)
    refunit	-- unit of measure to define reference end of displacement relationship
    dp_flow	-- displaced-product flow that is getting driven
    dp_refprop	-- a vlookup provided for the xlsx editor's convenience: =vlookup(dp_flow,flow_ref_qty,2,false)
    dp_refunit	-- unit of measure to define the displaced end of the displacement relationship
    note	-- fragment 'note' property

    defining the displacement rate
    scenario	-- optional scenario name for
    disp_lo	-- observed displacement alpha rate for 'low-displacement' scenario
    disp_rate	-- observed displacement alpha, named (or default) scenario
    disp_hi	-- observed displacemnent alpha rate for 'high-displacement' scenario
    value	-- observed displacement beta for named (or default) scenario
    time_equiv	-- multiplier for time equivalency (not yet implemented)

    defining forward and displaced transport
    md_truck	-- truck transport for massive md flows, using truck transport target specified by trans_truck
    dp_truck	-- truck transport for massive dp flows, using truck transport target specified by trans_truck
    dp_ocean	-- ocean transport for massive dp flows, using truck transport target specified by trans_ocean

    """
    # GENERIC
    def _get_one(self, hits, strict=False, prefix=None):
        """
        Overrides the standard _get_one with a feature to only search among activities whose name matches a prefix-
        :param hits:
        :param strict:
        :param prefix:
        :return:
        """
        if prefix:
            f_hits = filter(lambda x: x.external_ref.startswith(prefix), hits)
            return super(ModelMaker, self)._get_one(f_hits, strict=strict)
        else:
            return super(ModelMaker, self)._get_one(hits, strict=strict)

    def create_or_retrieve_reference(self, flow_or_ref, direction='Output', external_ref=None, prefix=None):
        """
        All these functions are written to deal with poorly-specified corner cases. it's terrible.
        what do we want to do?
         - look for a fragment with the specified flow
        :param flow_or_ref:
        :param direction:
        :param external_ref:
        :param prefix:
        :return:
        """
        if hasattr(flow_or_ref, 'entity_type'):
            if flow_or_ref.entity_type == 'flow':
                flow = flow_or_ref
                frag = self._get_one(self.fg.fragments_with_flow(flow), strict=True, prefix=prefix)
            elif flow_or_ref.entity_type == 'fragment':
                frag = flow_or_ref.top()
            else:
                raise TypeError(flow_or_ref)
        else:
            flow = self.fg[flow_or_ref]
            if flow is None:
                flow = self.fg.get_local(flow_or_ref)  # raises EntityNotFound eventually
                # raise EntityNotFound(flow_or_ref)

            try:
                frag = self._get_one(self.fg.fragments_with_flow(flow), strict=True, prefix=prefix)
            except EntityNotFound:
                if prefix:
                    external_ref = external_ref or '%s_%s' % (prefix, flow.external_ref)
                return self._new_reference_fragment(flow, direction, external_ref)

        if external_ref or prefix:
            # we want to name the fragment
            name = external_ref or '%s_%s' % (prefix, frag.flow.external_ref)
            if frag.external_ref == frag.uuid:  # not named yet
                self.fg.observe(frag, name=name)
            elif frag.external_ref != name:
                print('Warning, fragment already named %s' % frag.external_ref)
        return frag

    def _find_term_info(self, row):
        # first, find termination
        org = row.get('origin')
        if org:
            if org == 'here':
                origin = self.fg.origin
            else:
                origin = org

            d = {'external_ref': row.get('external_ref'),
                 'process_name': row.get('target_name'),
                 'flow_name': row.get('flow_name'),
                 'SpatialScope': row.get('locale')}  # default to RoW

            try:
                rx = self.find_background_rx(origin, **d)
            except AmbiguousResult:
                if d['SpatialScope'] is None:
                    d['SpatialScope'] = 'RoW'
                    rx = self.find_background_rx(origin, **d)
                else:
                    raise AmbiguousResult(*d.values())
            except (KeyError, EntityNotFound):
                raise FailedTermination(*d.values())
            child_flow = rx.flow
        else:
            flow_key = row.get('flow_name') or row.get('external_ref')
            child_flow = self.fg[flow_key] or flow_key
            if child_flow is None:
                raise NoInformation  # could try get_local?
            if row.get('compartment'):
                # context
                rx = self.fg.get_context(row['compartment'])
            else:
                # cutoff
                rx = None

        return rx, child_flow

    def make_production_row(self, row, prefix=None):
        """
        I probably should break this down a little better--- so many precedence rules + heuristics
        basically, we want to do the following:
         - terminate to a foreground process: specify 'here' origin and either flow_name or external_ref
         - terminate to a cutoff: specify no origin and flow_name
        :param row:
        :param prefix: naming convention for created fragments
        :return:
        """
        parent = self.create_or_retrieve_reference(row['prod_flow'], prefix=prefix)

        rx, child_flow = self._find_term_info(row)

        child_direction = check_direction(row['direction'])
        if child_direction == 'balance' or row['balance_yn']:
            balance = True
        else:
            balance = False

        try:
            c = next(parent.children_with_flow(child_flow))
            if balance:
                if parent.balance_flow:
                    if parent.balance_flow is not c:
                        raise ConsistencyError
                else:
                    c.set_balance_flow()
        except StopIteration:
            c = self.fg.new_fragment(child_flow, child_direction, parent=parent, balance=balance)

        if not balance:
            try:
                ev = float(row['amount'])
            except (TypeError, ValueError):
                raise BadExchangeValue(row.get('amount'))
            self.fg.observe(c, exchange_value=ev, units=row['units'], scenario=row['scenario'])
        c.terminate(rx, scenario=row['scenario'], descend=False)

        if row.get('stage_name'):
            c['StageName'] = row['stage_name']
        if row.get('note'):
            c['note'] = row['note']
        if row.get('Comment'):
            c['Comment'] = row['Comment']
        return c

    def _make_production_references(self, sheet, prefix):
        for r in range(1, sheet.nrows):
            ssr = r + 1
            # ASSUMPTION: prod_flow is first column
            # CONVENTION: production processes are all outputs
            row = sheet.row_dict(r)
            if row.get('prod_flow'):
                dirn = row.get('ref_direction', 'Output') or 'Output'
                try:
                    ref = self.create_or_retrieve_reference(row['prod_flow'], dirn, prefix=prefix)
                except EntityNotFound as e:
                    print('%d: unrecognized reference flow %s' % (ssr, e.args))
                    continue
                try:
                    rv = float(row['ref_value'])
                except KeyError:
                    print('%d: skipping omitted ref_value' % ssr)
                    continue
                except (TypeError, ValueError):
                    print('%d: skipping bad ref_value %s' % (ssr, row['ref_value']))
                    continue
                ru = row.get('ref_unit')
                self.fg.observe(ref, exchange_value=rv, units=ru)

    def _make_production_childflows(self, sheet, prefix=None):
        for r in range(1, sheet.nrows):
            ssr = r + 1
            row = sheet.row_dict(r)
            if row.get('prod_flow'):
                try:
                    c = self.make_production_row(row, prefix)
                    print('%d: %s' % (ssr, c))
                except NoInformation:
                    print('%d: No information for cutoff' % ssr)
                except FailedTermination as e:
                    print('%d: Failed Termination %s' % (ssr, e.args))
                except AmbiguousResult as e:
                    print('%d: Ambiguous Result %s' % (ssr, e.args))
                except UnknownOrigin as e:
                    print('%d: Unknown Origin %s' % (ssr, e.args))
                except MultipleReferences as e:
                    print('%d: Multiple References %s' % (ssr, e.args))
                except BadExchangeValue as e:
                    print('%d: Bad Exchange Value %s' % (ssr, e.args))
                except EntityNotFound as e:
                    print('%d: wayward entity-not-found error %s' % (ssr, e.args))

    def make_production(self, sheetname='production', prefix='prod'):
        """
        Strategy here:

         - production sheet includes *all* meso-scale processes
         - each production flow is provided by a single, distinct production process
         - each production record indicates a child flow with the observed amount (or balance if balance is checked)
         - terminates to the designated target (decode origin)
        :param self:
        :param sheetname: default 'production'
        :param prefix: prepend to flow_ref to get frag_ref
        :return:
        """
        if self.xlsx is None:
            raise AttributeError('Please attach Google Sheet')

        sheet = self.xlsx[sheetname]

        # first pass: create all production fragments
        self._make_production_references(sheet, prefix)

        # second pass: create child flows
        self._make_production_childflows(sheet, prefix)

    def _check_alpha_beta_prod(self, node, row_dict):
        """
        This is meant to be a generic utility that uses several boilerplate entries in a rowdict (hmm, these could
        actually be kwargs) to construct a displacement relationship between two items.  The unit conversions happen
        externally- either upstream in the "node" when it is created, or downstream when the displaced product is
        terminated to a production activity.

        Note:
        "alpha" = economic displacement = "epsilon" in MRC
        "beta" = technical displacement = "tau" in MRC

        It should create the fragments if they don't exist; re-observe them if they do

        kwargs: td_flow, dp_flow, dp_refunit, disp_lo, disp_rate, disp_hi, value, scenario
        :param node:
        :param row_dict:
        :return:
        """
        # disp = self.fg['displacement']  # ugggg this should really be raising a key error
        # if disp is None:
        disp = self.fg.add_or_retrieve('displacement', 'Number of items', 'Displacement Rate',
                                       comment="dimensionless value used in displacement calculation",
                                       group="modeling")
        td = row_dict['md_flow']
        dp = row_dict['dp_flow']
        scenario = row_dict.get('scenario')
        alpha_name = 'epsilon-%s-%s' % (td, dp)
        beta_name = 'tau-%s-%s' % (td, dp)

        try:
            alpha = next(node.children_with_flow(disp))
        except StopIteration:
            alpha = self.fg.new_fragment(disp, 'Output', parent=node,
                                         name='Market Displacement rate (alpha)')

        """
        OK, so now we are going to define the default displacement as 0.75 * alpha
        and create high-and-low displacement of alpha and 0.5 * alpha respectively
        """
        self.fg.observe(alpha, name=alpha_name)

        a_lo = row_dict.get('disp_lo')
        a = row_dict['disp_rate']
        a_hi = row_dict.get('disp_hi')

        self.fg.observe(alpha, a, scenario=scenario)  # unitless
        if a_hi:
            self.fg.observe(alpha, a_hi, scenario='high-displacement')  # unitless
        if a_lo:
            self.fg.observe(alpha, a_lo, scenario='low-displacement')  # unitless

        try:
            beta = next(alpha.children_with_flow(disp))
        except StopIteration:
            beta = self.fg.new_fragment(disp, 'Output', parent=alpha, name='Displacement relation')

        self.fg.observe(beta, row_dict['value'], name=beta_name)

        prod = self.fg.get_local(dp)
        try:
            output = next(beta.children_with_flow(prod))
        except StopIteration:
            # we do this in case the dp flow has changed
            cfs = list(beta.child_flows)
            for cf in cfs:
                self.fg.delete_fragment(cf)
            output = self.fg.new_fragment(prod, 'Output', parent=beta, name='Displaced %s' % prod.name)

        self.fg.observe(output, 1.0, units=row_dict['dp_refunit'])
        return output

    def _check_transport_link(self, node, target, distance_km, scenario=None, stage_name='Transport'):
        """
        Builds or updates a transport link child of the named node (measured in mass).  Assumes units are kg;
        freight is calculated as distance_km / 1000.0, times a correction factor of the node's exchange value IF the
        node is a reference node
        :param node:
        :param target:
        :param distance_km:
        :return:
        """
        mass = self.fg.get_canonical('mass')
        if node.flow.reference_entity is not mass:
            raise DispositionError('non-mass transport flow for %s' % node)

        if target is None:
            return  # nothing to do

        if node.is_reference:
            ev = distance_km * node.observed_ev / 1000.0
        else:
            ev = distance_km / 1000.0

        try:
            cf = next(node.children_with_flow(target.flow))
        except StopIteration:
            cf = self.fg.new_fragment(target.flow, target.direction, parent=node)
            cf.terminate(target)

        self.fg.observe(cf, exchange_value=ev, scenario=scenario)
        cf['StageName'] = stage_name
        cf.term.descend = False
        return cf

    def make_displacement_model(self, row, trans_truck=None, trans_ocean=None):
        """
        This creates or updates a displacement model that maps a particular product flow to a particular displaced
        flow, through an alpha-beta run, with added transport.  The alpha-beta run is standard; the other parts
        are not yet.

        :param row:
        :param trans_truck: external ref of truck transport process
        :param trans_ocean: external ref of ocean transport process
        :return:
        """
        product_ref = row.get('md_flow')
        product_refunit = row.get('refunit')
        disp_ref = row.get('dp_flow')

        ext_ref = 'displacement-%s-%s' % (product_ref, disp_ref)

        mass = self.fg.get_canonical('mass')
        truck_mdl = self.fg[trans_truck]
        ocean_mdl = self.fg[trans_ocean]

        td = self.fg.get_local(product_ref)
        dp = self.fg.get_local(disp_ref)

        name = 'Displacement, %s displ. %s' % (td.name, dp.name)

        # first, construct or retrieve the reference fragment
        node = self.fg[ext_ref]
        if node is None:
            node = self.fg.new_fragment(td, 'Input', Name=name, external_ref=ext_ref, StageName='Disposition')
        else:
            node.flow = td  # just to ensure
        self.fg.observe(node, exchange_value=1.0, units=product_refunit)
        node['note'] = row.get('note')

        if row.get('md_truck'):
            if td.reference_entity is mass:
                # then we can do transport--- only doing transport for massive flows
                if truck_mdl:
                    cf = self._check_transport_link(node, truck_mdl, float(row['md_truck']),
                                                    stage_name='Transport, %s' % td.name)
                    cf['stage_name'] = 'Transport, Products'  # stage_name kwarg becomes StageName
                else:
                    print('No truck transport model specified/found; skipping forward transport')

        output = self._check_alpha_beta_prod(node, row)

        disp = self.fg['prod_%s' % disp_ref]
        if disp:
            output.terminate(disp)

            if row.get('dp_truck'):
                if truck_mdl:
                    self._check_transport_link(disp, truck_mdl, float(row['dp_truck']),
                                               stage_name='Transport, Displaced')
                else:
                    print('No truck transport model specified/found; skipping displaced truck transport')

            if row.get('dp_ocean'):
                if ocean_mdl:
                    self._check_transport_link(disp, ocean_mdl, float(row['dp_ocean']),
                                               stage_name='Transport, Displaced')
                else:
                    print('No ocean transport model specified/found; skipping displaced ocean transport')

        return node

    def make_displacement(self, sheetname='displacement',
                          trans_truck='prod_transport_generic',
                          trans_ocean='prod_transport_ocean'):
        """
        Here we want to replicate what we did for CATRA, only improve it.  We have a table in the spreadsheet, and
        we want to construct a disposition model for each record that is marked "in use".  That model should:
         - take the designated flow IN
         - attach the designated freight (must ensure to account for tonnes
         - attach alpha
         - attach OUT flow
         - attach

        :param sheetname: default 'displacement'
        :param trans_truck: default 'prod_transport_generic'
        :param trans_ocean: default 'prod_transport_ocean'
        :return:
        """
        disp = self.xlsx[sheetname]
        for r in range(1, disp.nrows):
            row = disp.row_dict(r)
            if row.get('in_use'):
                self.make_displacement_model(row, trans_truck=trans_truck, trans_ocean=trans_ocean)
