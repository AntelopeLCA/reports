"""
Let's try this again.
"""
from antelope import q_node_activity, EntityNotFound, comp_dir, comp_sense, ForegroundInterface


class DuplicateRoute(Exception):
    """
    for use when a route already exists
    """
    pass


class MarketRequiresParent(Exception):
    pass


class NestedLcaStudy(object):
    """
    An improved formalization of the nested LCA study model first devised for CATRA Phase 1.  The basic idea is that
    the core of the model is provided by an MFA fragment whose inventory produces inputs and outputs.  The study
    fragment (which is EPHEMERAL) contains 3 levels-- to each level are added child flows that handle inputs and
    outputs of the MFA fragment, according to a mapping that can be pre-specified or ad hoc.

    This class has three main components:
     - Initialization - creates the "superstructure" of reference_flow <- study <- logistics <- activity <- #DATA#
       The #DATA# fragment is the user input.  When traversed, it will produce an inventory of cut-off flows that get
       automatically linked to child flows in the superstructure.  These child flows are grouped by their reference
       quantity:

         ref qty  |  superstructure node
         ---------+---------------------
         mass     |  study_container
         freight  |  logistics_container
         activity |  activity_container

       Flows with other reference quantities can also be terminated, most likely in the study_container.

     - Route Construction methods - used to build the components to which superstructure child flows are linked.  These
       fragments are all dynamically created (no statefulness to worry about) and stored in the study foreground.

     - Model populating methods - user-facing methods to attach data fragments to the study.

    For each tier
    """
    @property
    def _act(self):
        return q_node_activity(self._fg)

    def new_activity_flow(self, name, external_ref=None, **kwargs):
        """
        This should really be a foreground method
        :param name:
        :param external_ref:
        :param kwargs:
        :return:
        """
        if external_ref is None:
            fu = self._fg.new_flow(name, self._act, **kwargs)
        else:
            fu = self._fg.add_or_retrieve(external_ref, self._act, name, strict=True, **kwargs)
        return fu

    @classmethod
    def create_from_names(cls, cat, fg_name, models_name, data_name=None, **kwargs):
        """
        In the event that the models + data foregrounds already exist, this is a convenience function to
        encapsulate the foreground query calls.
        :param cat:
        :param fg_name:
        :param models_name:
        :param data_name:
        :param kwargs:
        :return:
        """
        fg = cat.foreground(fg_name, create=True, reset=True)
        models = cat.foreground(models_name)
        if data_name:
            data = cat.foreground(data_name)
        else:
            data = None
        return cls(fg, models=models, data=data, **kwargs)

    def __init__(self, foreground, models=None, data=None, reference_flow='LCA Study',
                 study_container='study_container',
                 logistics_container='logistics_container',
                 activity_container='activity_container'):
        """

        :param foreground: foreground query - to contain the study model - ephemeral
        :param models: [optional] foreground query to contain upstream models
        :param data: foreground query for MFA data
        :param reference_flow: flow name for the study's reference flow
        :param study_container: [eponymous] external_ref
        :param logistics_container: [eponymous] external_ref
        :param activity_container: [eponymous] external_ref
        """
        self._fg = foreground
        if models is None:
            models = foreground
        self._models = models

        self._data = data

        self._ref = reference_flow
        self._study = study_container
        self._logis = logistics_container
        self._activ = activity_container

        self.route_debug = False

    @property
    def data(self):
        return self._data

    def set_data_fg(self, data_fg):
        if not isinstance(data_fg, ForegroundInterface):
            raise TypeError(data_fg)
        self._data = data_fg

    def _resolve_term(self, term):
        """
        Grab an entry from the foreground[s] associated with the project: first _fg, then _models, then _data if they exist
        :param term:
        :return:
        """
        if hasattr(term, 'entity_type'):
            return term
        try:
            return self._fg.get(term)
        except EntityNotFound:
            try:
                return self._models.get(term)
            except EntityNotFound:
                if self.data is not None:
                    return self._data.get(term)
                raise

    @property
    def reference_flow(self):
        return self.new_activity_flow(self._ref, external_ref='reference_flow')

    @property
    def study_container(self):
        try:
            return self._fg.get(self._study)
        except EntityNotFound:
            study = self._fg.new_fragment(self.reference_flow, 'Output', name=self._ref)
            self._fg.observe(study, name=self._study, termination=self.logistics_container)
        return self._fg.get(self._study)

    @property
    def logistics_container(self):
        try:
            return self._fg.get(self._logis)
        except EntityNotFound:
            study = self._fg.new_fragment(self.reference_flow, 'Output', name='%s_logistics' % self._ref)
            self._fg.observe(study, name=self._logis, termination=self.activity_container)
        return self._fg.get(self._logis)

    @property
    def activity_container(self):
        try:
            return self._fg.get(self._activ)
        except EntityNotFound:
            study = self._fg.new_fragment(self.reference_flow, 'Output', name='%s_nodes' % self._ref)
            self._fg.observe(study, name=self._activ)
        return self._fg.get(self._activ)

    @property
    def fg(self):
        return self._fg

    @property
    def models(self):
        return self._models

    '''
    Route-building machinery

    This is a bit of a Kluge, but here is the idea:

    A ROUTE SPECIFICATION consists of a sequence of STAGES (as a tuple).  Each STAGE is EITHER:
     - a fragment present in the models foreground, OR
     - a BRANCH.  Any node in a route specification may generate multiple child flows, known as a BRANCH, and
       designated with a tuple of fragment specs.  Each subsequent stage must be a tuple with the same length.  
       The first stage may not be a branch.
     - Branches can be nested by including tuples of tuples. 

    For each stage, the route builder will retrieve the target and create a fragment whose flow matches the target's.
    It will then terminate the fragment to the target.  That stage then becomes the parent of the subsequent stage.

    When a branch is encountered, it will create multiple child flows from the parent, one for each entry in the branch.
    EVERY SUBSEQUENT STAGE must have the same number of entries as the branch, and these entries are appended as
    child nodes to the branched parents.  Use None to end a branch (None must be supplied as a placeholder throughout
    the route).

    '''

    def _make_single_link(self, parent, direction, child, stage_name=None):
        if self.route_debug:
            print('_make_single_link: %s, %s, %s' % (parent, direction, child))
        try:
            term = self.models.get(child)
        except EntityNotFound:
            term = self.fg.get(child)
        ''' # not sure how to use this yet
        if term.entity_type == 'flow':
            # cutoff
            return term
        '''
        if parent is None:
            # 'comp_dir' because new_fragment UX expects input w.r.t. fragment for reference flows
            f = self.fg.new_fragment(term.flow, comp_dir(direction))
        else:
            if isinstance(parent, list) and len(parent) == 1:
                print('found a list')
                parent = parent[0]
            f = self.fg.new_fragment(term.flow, term.direction, parent=parent)  # we don't *know* the child flow dirn
            # the sign change happens at either of 2 pts: on flow matching in subfrag traversal; or at node_inbound_ev
        f.terminate(term)
        if stage_name:
            f['StageName'] = stage_name
            f.term.descend = False
        return f

    def _make_link_or_links(self, parent, direction, child_or_children, stage_names):
        """
        Ahh, recursion
        :param parent:
        :param direction:
        :param child_or_children:
        :param stage_names:
        :return:
        """
        if self.route_debug:
            print('_make_link_or_links: %s, %s, %s' % (parent, direction, child_or_children))
        if isinstance(child_or_children, dict):
            if isinstance(parent, list):
                # can't imagine this coming up, but let's let it ride
                return [self._make_link_or_links(k, direction, child_or_children, stage_names) for k in parent]
            else:
                obs = self.models[child_or_children['child_flow']]
                if parent is None:
                    mkt_node = self.fg.new_fragment(obs, comp_dir(direction))  # is this getting out of hand?
                else:
                    mkt_node = self.fg.new_fragment(obs, direction, parent=parent)

                if self.make_market(mkt_node, child_or_children['market'], sense=comp_sense(direction),
                                    stage_names=stage_names):
                    # sequencing here is going to be a problem- gotta be just sorted by flow.external_ref
                    return sorted(mkt_node.child_flows, key=lambda x: x.flow.external_ref)
                else:
                    return parent  # aha

        if isinstance(child_or_children, tuple):
            f = []
            if isinstance(parent, list):
                for i, p in enumerate(parent):
                    if p is None or child_or_children[i] is None:
                        f.append(None)
                    else:
                        f.append(self._make_link_or_links(p, direction, child_or_children[i], stage_names))
            else:
                for c in child_or_children:
                    f.append(self._make_link_or_links(parent, direction, c, stage_names))
        else:
            stage_name = stage_names.get(child_or_children)
            f = self._make_single_link(parent, direction, child_or_children, stage_name=stage_name)
        return f

    def _make_route(self, route, sense, stage_names, parent=None):
        """
        This can be used internally to construct routes from the models foreground as tuple specifications
        :param route:
        :param sense: whether the route is a Source of inputs to the study system or a sink for Outputs (i.e. whether it
        will get plugged into inputs or outputs of the study system.
        :param stage_names: dict
        :param parent: [None] for new standalone models. Can also be used to attach routes to existing parents.
        :return:
        """
        if self.route_debug:
            print('_make_route: %s, %s, %s' % (route, sense, parent))
        first = None
        direction = comp_dir(sense)
        if isinstance(route, str) or isinstance(route, dict):
            route = (route, )

        for step in route:
            if first is None and isinstance(step, tuple):
                raise ValueError('Model spec cannot begin with a tuple! %s' % step)
            child = self._make_link_or_links(parent, direction, step, stage_names)
            if first is None:
                if isinstance(child, list):
                    first = child[0].parent  # retrieve the market node
                else:
                    first = child
            parent = child
        return first

    def make_route(self, route_name, route_spec, sense='Sink', stage_names=None):
        """
        Provision (source) and Disposition (sink) routes get built from scratch during LCA runtime in LCA study
        foreground.  Components are drawn from the models foreground.

        The "Route specification" is a tuple of stage specifications.  Each entry in the tuple is a stage.  A stage
        can be either a single entry (corresponding to a fragment in models) or a tuple of entries, signifying a
        branch from the prior stage.  Branch patterns must be maintained for all subsequent stages.  Additional
        branches can be obtained by enclosing a tuple within the tuples.  An entry of "None" indicates that the branch
        ends (but Nones must be maintained through the entire length of the spec)

        Example:

        { "route_1" : ('node_1',),  #       ---> [node_1]
          "route_2" : ('node_2a', 'node_2b'),   # ---> [node_2a] ---> [node_2b ]
          "route_3" : ('node_3a', ('node_3b1', 'node_3b2'), (None, 'node_3c2')), #
           #  ---> [node_3a] -+--> [node_3b1]
           #                  \--> [node_3b2] ---> [node_3c2]
          "route_4" : ('node_4a', ('node_4b1', 'node_4b2'), (('node_4c11', 'node_4c12'), 'node_4c2'), (('node_4d11', 'node_4d12'), 'node_4d2')) #
           #  ---> [node_4a] -+--> [node_4b1] -+--> [node_4c11] ---> [node_4d11]
           #                  \                \--> [node_4c12] ---> [node_4d12]
           #                   \-> [node_4b2] ----> [node_4c2] ----> [node_4d2]
        }

        A dict given as a terminal node can be used to pass a market specification for make_market, but it is
        problematic because the market needs a foreground flow from which to make exchange value observations
        (child flows from fragment terms are not observable).

        So: the dict specification for the market looks like this:
        {'child_flow': flow_ext_ref,
         'market': {market spec...}}
        The child flow is created using the given flow ref, and the market spec is passed to make_market.  The
        number of entries in the market indicates the number of child flows for the next stage.  Because order
        is important, the flows are returned **sorted by their external_refs**.

        Note that the routes specified by the market must exist at the time the market is created.

        :param route_name: The external_ref of the route
        :param route_spec: tuple chain, as above
        :param sense: whether the route is a 'Sink' [default] or a 'Source'
        :param stage_names: a mapping of route spec entries to stage names.  If one is found, the fragment containing
         it is given the assigned stage name, and descend is set to False for that link (aggregating the target within
         the named stage).
        :return: the created fragment
        """
        if stage_names is None:
            stage_names = dict()
        if self.fg[route_name] is None:
            route = self._make_route(route_spec, sense, stage_names)
            if route is None:
                print('^^^^^^^^^^^^^^^^^^^^^^^^^^ No route produced for %s\n%s' % (route_name, route_spec))
            elif route.entity_type == 'flow':
                # do nothing?
                pass
            else:
                self.fg.observe(route, name=route_name)
            if route_name in stage_names:
                route['StageName'] = stage_names[route_name]
            return route
        raise DuplicateRoute('Route %s already exists' % route_name)

    def _check_p_map(self, p_map):
        nc = 0
        for k, v in p_map.items():
            try:
                self._resolve_term(k)
            except EntityNotFound:
                print('Product map entry %s not found' % k)
                return False
            if v is None:
                nc += 1
            else:
                try:
                    float(v)
                except (ValueError, AttributeError):
                    print('Key %s has non-floatable value %s' % (k, v))
                    return False
        if nc != 1:
            print('Wrong number of balance flows (%d)' % nc)
            return False
        return True

    def make_market(self, parent_or_flow, p_map, sense='Sink', stage_names=None):
        """
        Another kind of utility function- this one turns dictionaries into market mixers, either over flows or models.
        For this the user must specify the parent fragment.

        Constitutive difference here is that markets are required to have parents, whereas routes are new fragments.

        The technical reason is that there must be an explicit node to compute the balance.

        Supplying a flow will create a self-standing market for the flow

        The default naming for market knobs provides for autoincrement

        :param parent_or_flow: either a parent fragment whose flow is getting mixed, or a flow to build a self-standing mixer
        :param p_map:
        :param sense:
        :param stage_names:
        :return:
        """
        if self.route_debug:
            print('make_market: %s, %s, %s' % (parent_or_flow, p_map, sense))
        if stage_names is None:
            stage_names = dict()
        if isinstance(p_map, str):
            p_map = {p_map: None}
        direction = comp_dir(sense)
        if parent_or_flow is None:
            raise MarketRequiresParent('Cannot build a free-standing market mixer- parent cannot be None')
        if self._check_p_map(p_map):
            if parent_or_flow.entity_type == 'flow':
                market_ref = 'mix-%s-%s' % (sense, parent_or_flow.external_ref)
                market_ref = market_ref.replace('/', '_')
                parent = self.fg[market_ref]
                if parent is not None:
                    return parent  # don't support dynamic modification of markets

                parent = self.fg.new_fragment(parent_or_flow, comp_dir(direction))
                self.fg.observe(parent, name=market_ref)

            elif parent_or_flow.entity_type == 'fragment':
                parent = parent_or_flow
            else:
                raise TypeError('Unrecognized parent type %s: %s' % (parent_or_flow.entity_type, parent_or_flow.external_ref))
            for k, v in p_map.items():
                term = self._resolve_term(k)  # no need to try-catch this bc we've already checked the p_map
                if term.entity_type == 'flow':
                    flow = term

                elif term.entity_type == 'fragment':
                    flow = parent.flow  # stick with market parent for conservation purposes

                else:
                    raise TypeError(term, "p_map key looks up to wrong or nothing")

                if v is None:
                    c = self.fg.new_fragment(flow, direction, parent=parent, name=term['name'], balance=True)
                else:
                    c = self.fg.new_fragment(flow, direction, parent=parent, name=term['name'])
                    if parent.external_ref == parent.uuid:
                        mix_name = 'mix-%s-%s-%s' % (sense, parent.flow.external_ref, k)
                    else:
                        mix_name = '%s-%s' % (parent.external_ref, k)
                    mix_name = mix_name.replace('/', '_')
                    self.fg.observe(c, name=mix_name, exchange_value=v, auto=True)

                if term.entity_type == 'fragment':
                    stage_name = stage_names.get(k)
                    c.terminate(term, term_flow=term.flow)
                    if stage_name:
                        c.term.descend = False
                        c['StageName'] = stage_name

                    # flows will show up as cut-offs / and/or get forwarded up the superstructure

                # not sure what this is for..
                # if term.external_ref == 'frag-t_waste':
                #     c.term.descend = False
                #     c['StageName'] = 'Waste to Landfill'

            return parent
        print('Not building product map for %s' % parent_or_flow)
        return False

    '''
    Model populating methods
    '''
    def make_routes(self, routes, sense='Sink', stage_names=None):
        for k, v in routes.items():
            try:
                self.make_route(k, v, sense=sense, stage_names=stage_names)
            except DuplicateRoute:
                print('Route %s exists; NOT updating' % k)
                pass
            except EntityNotFound as e:
                print('Route %s: entity not found %s: skipping' % (k, e.args))

    def install_observation_model(self, prov_frag, scope=None):
        if scope is None:
            scope = prov_frag.get('Scope')
            if scope is None:
                raise ValueError('Must provide scope!')
        self.activity_container.clear_termination(scope)
        self.activity_container.terminate(prov_frag, scope)

    def add_logistics_route(self, flow, provider, descend=False, **kwargs):
        """

        :param flow:
        :param provider:
        :param descend: [False] whether to traverse [True] or aggregate [False] subfragments
        :param kwargs: StageName='Logistics', other args to fragment
        :return:
        """
        try:
            return next(self.logistics_container.children_with_flow(flow))
        except StopIteration:
            c = self.fg.new_fragment(flow, 'Input', parent=self.logistics_container, **kwargs)
            c.terminate(self._resolve_term(provider), descend=descend)
            return c
