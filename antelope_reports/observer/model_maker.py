from antelope import EntityNotFound, UnknownOrigin, MultipleReferences, ConversionError, NoReference
from antelope.interfaces.iindex import InvalidDirection, comp_dir, check_direction
from antelope_foreground.terminations import FlowConversionError

from .quick_and_easy import QuickAndEasy, AmbiguousResult
from .float_conv import to_float, try_float
from .headers import PRODUCTION_HEADER
import logging
from collections import defaultdict


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
    amount_hi	-- observed exchange value for high sensitivity case
    amount_lo	-- observed exchange value for high sensitivity case
    units	-- unit of measure for amount, amount_hi, amount_lo
    child_flow  -- external ref of child flow (if blank, will be taken from anchor)
    stage_name	-- fragment 'StageName' property
    note	-- fragment 'note' property
    Comment	-- fragment 'Comment' property

    scenario	-- deprecated

    anchor spec:
    (these are used in _find_term_info(), ultimately passed to find_background_rx()
    target_origin	-- origin for anchor node
    compartment	-- used for specifying elementary flows (leave origin blank)
    target_flow -- passed to find_background_rx as flow_name_or_ref (if blank, use child_flow if specified)
    locale	-- used as SpatialScope argument in find_background_rx
    target_name	-- used as process_name argument in find_background_rx
    target_ref	-- passed to find_background_rx as external_ref

    The regression is as follows:
      if origin is specified: row describes an anchored flow
         origin == 'here' -> look in local foreground
         pass a dict to find_background_rx containing:
         target_ref (as external_ref), target_name (as process_name), flow_name_or_ref, locale (as SpatialScope)
      else:
         row describes either a cutoff or an exterior (context / environment) flow
         flow_name_or_ref is retrieved using get_local(). no other columns are used other than compartment (maybe locale)
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
    def __init__(self, *args, sens_lo='sens_lo', sens_hi='sens_hi', **kwargs):
        super(ModelMaker, self).__init__(*args, **kwargs)

        self.sens_lo = sens_lo
        self.sens_hi = sens_hi

        self._skips = []
        self._errors = dict()

    @property
    def skips(self):
        return list(self._skips)

    @property
    def errors(self):
        d = defaultdict(list)
        for k, e in self._errors.items():
            d[e.__class__.__name__].append(k)
        return dict(d)

    def error(self, k):
        return self._errors[k]

    def autodetect_flows(self, sheetname, external_ref=None, ref_quantity=None, ref_unit=None, name=None,
                         context=None, entity_uuid=None, **kwargs):
        """
        Load the designated sheet. iterate through rows, using the arguments as column mappings.

        :param sheetname: name of the source sheet
        :param external_ref:
        :param ref_quantity:
        :param ref_unit:
        :param name:
        :param context:
        :param entity_uuid:
        :param kwargs:
        :return:
        """
        if not self._quiet:
            print('\n autodetecting %s' % sheetname)

        sheet = self.xlsx[sheetname]

        if external_ref is None:
            external_ref = 'external_ref'
        if ref_quantity is None:
            if ref_unit is None:
                ref_quantity = 'referenceQuantity'
            else:
                pass  # use ref_unit
        if name is None:
            name = 'name'

        # all others are optional
        if context:
            kwargs['context'] = context
        if entity_uuid:
            kwargs['entity_uuid'] = entity_uuid

        count = 0
        new = set()

        for r in range(1, sheet.nrows):
            ssr = r + 1
            row = sheet.row_dict(r)
            ext_ref = row.get(external_ref)
            the_name = row.get(name, ext_ref)
            if ext_ref is None:
                continue
            if the_name is None:
                the_name = ext_ref
            if ref_quantity is None:
                ref_q = self._unit_map.get(row.get(ref_unit))
                if ref_q is None:
                    print('%s:%d Unrecognized unit %s- skipping flow %s' % (sheetname, ssr, row.get(ref_unit), ext_ref))
                    continue
            else:
                ref_q = row.get(ref_quantity)
            count += 1

            args = {k: row.get(v) for k, v in kwargs.items() if v is not None and row.get(v) is not None}
            if self.fg[ext_ref] is None:
                new.add(ext_ref)
            f = self.fg.add_or_retrieve(ext_ref, ref_q, the_name, **args)
            # update the name if it contains new information-- important for LCIA
            if the_name != f['name'] and the_name != ext_ref:
                f['name'] = the_name
                f.clear_chars()

        print('Reviewed %d flows (%d new added)' % (count, len(new)))

    def detect_spanner_flows(self, spanner_ref, **kwargs):
        self.autodetect_flows(spanner_ref, external_ref='flow', name='Name', ref_unit='units',
                              context='context', **kwargs)

    def detect_production_flows(self, production_sheet='production', **kwargs):
        self.autodetect_flows(production_sheet, external_ref='prod_flow', ref_unit='ref_unit', **kwargs)

    def update_flows(self, sheetname='flows'):
        """
        here we are using the same flows sheet spec as XlsxArchiveUpdater so we don't need to configure column mappings
        :param sheetname:
        :return:
        """
        sheet = self.xlsx[sheetname]
        columns = ('external_ref', 'referenceQuantity', 'Name', 'Comment', 'Compartment')
        write = [list(columns)]
        exis = set()
        error = 0

        def _make_a_row(_f):
            cx = _f.context.name
            if cx == 'None':
                cx = None
            return [_f.external_ref, _f.reference_entity['Name'], _f['Name'], _f['Comment'], cx]

        # first, existing
        for i in range(1, sheet.nrows):
            row = [k.value for k in sheet.row(i)]
            ssr = i + 1
            if len(row) == 0 or row[0] is None:
                write.append([None, None, None, None, None])
                continue
            try:
                f = self.fg.get(row[0])
                write.append(_make_a_row(f))
                exis.add(f.external_ref)
            except KeyError:
                logging.warning('unrecognized flow in existing pass (%s row %d %s)' % (sheetname, ssr, row[0]))
                write.append(row[:5])
            except TypeError:
                logging.warning('TypeError problem in existing pass (%s row %d %s)' % (sheetname, ssr, row[0]))
                error += 1

        # add new
        added = 0
        for f in self.fg.flows():
            if f.origin != self.fg.origin:
                continue
            if f.external_ref in exis:
                continue
            try:
                write.append(_make_a_row(f))
                added += 1
            except TypeError:
                logging.warning('TypeError problem - skipping new flow %s' % f.external_ref)
                error += 1
        msg = 'Writing %d existing and %d new flows to sheet %s' % (len(exis), added, sheetname)
        if error:
            msg += ' (%d errors)' % error
        print(msg)
        self.xlsx.write_rectangle_by_rows(sheetname, write)

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
                flow = self.fg.get(flow_or_ref)  # raises EntityNotFound eventually
                # yes, this is (regrettably) opposite the convention where .get() returns None
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

    def _find_reference_exchange(self, row):
        # first, find termination
        org = row.get('target_origin') or row.get('origin')
        if org:
            if org == 'here':
                origin = self.fg.origin
            else:
                origin = org

            d = {'external_ref': row.get('target_ref') or row.get('external_ref'),
                 'process_name': row.get('target_name'),
                 'flow_name_or_ref': row.get('target_flow') or row.get('term_flow') or row.get('flow_name') or row.get('child_flow'),
                 'SpatialScope': row.get('locale')}  # default to RoW

            try:
                rx = self.find_background_rx(origin, **d)
            except AmbiguousResult:
                if d['SpatialScope'] is None:
                    d['SpatialScope'] = 'RoW'
                    rx = self.find_background_rx(origin, **d)
                else:
                    if not d['SpatialScope'].startswith('^'):
                        d['SpatialScope'] = '^%s$' % d['SpatialScope']
                        try:
                            rx = self.find_background_rx(origin, **d)
                        except AmbiguousResult:
                            raise AmbiguousResult(*d.values())
                    else:
                        raise AmbiguousResult(*d.values())
            except (KeyError, EntityNotFound):
                raise FailedTermination(*d.values())
        else:
            if row.get('compartment'):
                # context
                rx = self.fg.get_context(row['compartment'])
            else:
                # cutoff
                rx = None

        return rx

    def _build_production_row(self, parent, row):
        """
        I probably should break this down a little better--- so many precedence rules + heuristics
        basically, we want to do the following:
         - terminate to a foreground process: specify 'here' origin and either flow_name or external_ref
         - terminate to a cutoff: specify no origin and flow_name

        :param parent: parent fragment
        :param row: row_dict
        :return:
        """

        rx = self._find_reference_exchange(row)

        if row.get('child_flow'):
            child_flow = self.fg.get(row.get('child_flow'))
        else:
            if hasattr(rx, 'flow'):
                child_flow = rx.flow
            else:
                cf_ref = row.get('flow_name') or row.get('term_flow')
                if cf_ref:
                    child_flow = self.fg.get(cf_ref)
                else:
                    raise NoInformation

        try:
            child_direction = check_direction(row['direction'])
        except InvalidDirection:
            if hasattr(rx, 'direction'):
                child_direction = comp_dir(rx.direction)
            elif hasattr(rx, 'sense') and rx.sense is not None:
                child_direction = comp_dir(rx.sense)
            else:
                child_direction = parent.direction

        if row['balance_yn']:  # or child_direction == 'balance'
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
            else:
                if parent.balance_flow is c:
                    c.unset_balance_flow()
        except StopIteration:
            if balance:
                if parent.balance_flow:
                    parent.balance_flow.unset_balance_flow()
            c = self.fg.new_fragment(child_flow, child_direction, parent=parent, balance=balance)

        if not balance:
            try:
                ev = to_float(row['amount'])
            except (TypeError, ValueError):
                raise BadExchangeValue(row.get('amount'))
            try:
                self.fg.observe(c, exchange_value=ev, units=row['units'])
            except ConversionError:
                raise BadExchangeValue(c.flow.reference_entity, row['units'])
            if row.get('amount_lo', None) is not None:
                ev_lo = to_float(row['amount_lo'])
                self.fg.observe(c, exchange_value=ev_lo, units=row['units'], scenario=self.sens_lo)
            if row.get('amount_lo', None) is not None:
                ev_hi = to_float(row['amount_hi'])
                self.fg.observe(c, exchange_value=ev_hi, units=row['units'], scenario=self.sens_hi)
        """
        Logic here:
        if descend is specified, set it
        else: 
        if no stage name is specified, descend should be True
        """
        descend = row.get('descend')
        if row.get('stage_name'):
            c['StageName'] = row['stage_name']
            if descend is None:
                descend = False
            else:
                descend = bool(descend)
        else:
            if descend is None:
                descend = True
            else:
                descend = bool(descend)
        c.terminate(rx, descend=descend)

        if row.get('note'):
            c['note'] = row['note']
        if row.get('Comment'):
            c['Comment'] = row['Comment']

        tap_recipe = row.get('add_taps', None)
        if tap_recipe:
            self.apply_tap_recipes(c, tap_recipe)

        # add residual information to child flow
        for k in row.keys():
            if k not in PRODUCTION_HEADER:
                c[k] = row[k]

        return c

    def _log_e(self, ssr, e):
        if ssr in self._errors:
            logging.warning('double error %s' % ssr)
        else:
            self._errors[ssr] = e

    def _make_production_references(self, sheet, prefix):
        refs = set()
        for r in range(1, sheet.nrows):
            ssr = r + 1
            # ASSUMPTION: prod_flow is first column
            # CONVENTION: production processes are all outputs
            row = sheet.row_dict(r)
            if row.get('prod_flow'):
                dirn = row.get('ref_direction', 'Output') or 'Output'
                try:
                    ref = self.create_or_retrieve_reference(row['prod_flow'], dirn, prefix=prefix)
                    refs.add(row['prod_flow'])
                except EntityNotFound as e:
                    print('%d: unrecognized reference flow %s' % (ssr, e.args))
                    self._log_e(ssr, e)
                    continue
                try:
                    rv = try_float(row['ref_value'])
                except KeyError:
                    print('%d: skipping omitted ref_value' % ssr)
                    self._skips.append(ssr)
                    continue
                except (TypeError, ValueError):
                    print('%d: skipping bad ref_value %s' % (ssr, row['ref_value']))
                    self._skips.append(ssr)
                    continue
                ru = row.get('ref_unit')
                try:
                    self.fg.observe(ref, exchange_value=rv, units=ru)
                except ConversionError:
                    print('%d: Skipping bad unit conversion specification %s [%s]' % (ssr, ru,
                                                                                      ref.flow.reference_entity))
        return len(refs)

    def _make_production_childflows(self, sheet, prefix=None):
        count = 0
        for r in range(1, sheet.nrows):
            ssr = r + 1
            row = sheet.row_dict(r)
            if row.get('prod_flow'):
                try:
                    parent = self.create_or_retrieve_reference(row['prod_flow'], prefix=prefix)
                    c = self._build_production_row(parent, row)
                    c['_%s_row' % (prefix or sheet.name)] = ssr
                    print('== %03d ==: %s' % (ssr, c))
                    count += 1
                except NoInformation:
                    self._skips.append(ssr)
                    print('## %03d ##: No information for cutoff' % ssr)
                except FailedTermination as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: Failed Termination %s' % (ssr, e.args))
                except AmbiguousResult as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: Ambiguous Result %s' % (ssr, e.args))
                except UnknownOrigin as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: Unknown Origin %s' % (ssr, e.args))
                except MultipleReferences as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: Multiple References %s' % (ssr, e.args))
                except NoReference as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: No Reference %s' % (ssr, e.args))
                except BadExchangeValue as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: Bad Exchange Value %s' % (ssr, e.args))
                except EntityNotFound as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: wayward entity-not-found error %s' % (ssr, e.args))
                except FlowConversionError as e:
                    self._log_e(ssr, e)
                    print('## %03d ##: flow-conversion termination error %s' % (ssr, e.args))
        return count

    def make_production(self, sheetname='production', prefix='prod', taps=None, detect_flows=True):
        """
        Strategy here:

         - production sheet includes *all* meso-scale processes
         - each production flow is provided by a single, distinct production process
         - each production record indicates a child flow with the observed amount (or balance if balance is checked)
         - terminates to the designated target (decode origin)
        :param self:
        :param sheetname: default 'production'
        :param prefix: prepend to flow_ref to get frag_ref
        :param taps: [None] if present, load taps from, named sheet after creating references but before child flows
        :return:
        """
        if self.xlsx is None:
            raise AttributeError('Please attach Google Sheet')
        self._errors = dict()  # reset errors
        if detect_flows:
            self.detect_production_flows(sheetname)

        sheet = self.xlsx[sheetname]

        # first pass: create all production fragments
        refs = self._make_production_references(sheet, prefix)

        if taps:
            self.load_taps_from_spreadsheet(taps)

        # second pass: create child flows
        count = self._make_production_childflows(sheet, prefix)
        print('Created %d reference flows with %d child flows (%d errors)' % (refs, count, len(self._errors)))

    def make_production_row(self, ssr, sheetname='production', prefix='prod'):
        """
        
        :param ssr: spreadsheet row 
        :param sheetname: 
        :param prefix: 
        :return: 
        """
        if self.xlsx is None:
            raise AttributeError('Please attach Google Sheet')

        sheet = self.xlsx[sheetname]
        row = sheet.row_dict(ssr - 1)
        if not row.get('prod_flow'):
            raise ValueError('Empty prod_flow')

        # update parent
        dirn = row.get('ref_direction', 'Output') or 'Output'
        parent = self.create_or_retrieve_reference(row['prod_flow'], direction=dirn, prefix=prefix)
        rv = try_float(row['ref_value'])
        ru = row.get('ref_unit')
        self.fg.observe(parent, exchange_value=rv, units=ru)

        # build child
        c = self._build_production_row(parent, row)
        print('== %03d ==: %s' % (ssr, c))
        c['_%s_row' % (prefix or sheet.name)] = ssr
        if ssr in self._errors:
            print('removing error for row %d' % ssr)
            self._errors.pop(ssr)
        return c

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

        prod = self.fg.get(dp)
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

    def make_displacement_model(self, row, trans_truck=None, trans_ocean=None, embed_disp_prod=True):
        """
        This creates or updates a displacement model that maps a particular product flow to a particular displaced
        flow, through an alpha-beta run, with added transport.  The alpha-beta run is standard; the other parts
        are not yet.

        :param row:
        :param trans_truck: external ref of truck transport process
        :param trans_ocean: external ref of ocean transport process
        :param embed_disp_prod: [True] whether to auto-anchor the displaced product flow if a suitable production
         activity is found.  Set to False to leave this as a cut-off flow
        :return:
        """
        product_ref = row.get('md_flow')
        product_refunit = row.get('refunit')
        disp_ref = row.get('dp_flow')

        ext_ref = 'displacement-%s-%s' % (product_ref, disp_ref)

        mass = self.fg.get_canonical('mass')
        truck_mdl = self.fg[trans_truck]
        ocean_mdl = self.fg[trans_ocean]

        td = self.fg.get(product_ref)
        dp = self.fg.get(disp_ref)

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
                    cf = self._check_transport_link(node, truck_mdl, to_float(row['md_truck']),
                                                    stage_name='Transport, %s' % td.name)
                    cf['stage_name'] = 'Transport, Products'  # stage_name kwarg becomes StageName
                else:
                    print('No truck transport model specified/found; skipping forward transport')

        output = self._check_alpha_beta_prod(node, row)

        disp = self.fg['prod_%s' % disp_ref]
        if disp:
            if embed_disp_prod:
                output.terminate(disp)

            if row.get('dp_truck'):
                if truck_mdl:
                    self._check_transport_link(disp, truck_mdl, to_float(row['dp_truck']),
                                               stage_name='Transport, Displaced')
                else:
                    print('No truck transport model specified/found; skipping displaced truck transport')

            if row.get('dp_ocean'):
                if ocean_mdl:
                    self._check_transport_link(disp, ocean_mdl, to_float(row['dp_ocean']),
                                               stage_name='Transport, Displaced')
                else:
                    print('No ocean transport model specified/found; skipping displaced ocean transport')

        return node

    def make_displacement(self, sheetname='displacement',
                          trans_truck='prod_transport_generic',
                          trans_ocean='prod_transport_ocean',
                          embed_disp_prod=True):
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
        :param embed_disp_prod: [True] whether to auto-anchor the displaced product flow if a suitable production
         activity is found.  Set to False to leave this as a cut-off flow
        :return:
        """
        disp = self.xlsx[sheetname]
        for r in range(1, disp.nrows):
            row = disp.row_dict(r)
            if row.get('in_use'):
                self.make_displacement_model(row, trans_truck=trans_truck, trans_ocean=trans_ocean,
                                             embed_disp_prod=embed_disp_prod)
