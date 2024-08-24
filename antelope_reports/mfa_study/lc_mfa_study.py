"""
Let's try this again.
"""
from antelope import EntityNotFound, ForegroundInterface
from ..fg_builder.lca_study import LcaStudy


class NestedLcaStudy(LcaStudy):
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

    def __init__(self, foreground, models=None, data=None, reference_flow='MFA-LCA Study',
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
        super(NestedLcaStudy, self).__init__(foreground, models, reference_flow=reference_flow)

        self._data = data

        self._study = study_container
        self._logis = logistics_container
        self._activ = activity_container

    @property
    def data(self):
        return self._data

    def set_data_fg(self, data_fg):
        if not isinstance(data_fg, ForegroundInterface):
            raise TypeError(data_fg)
        self._data = data_fg

    def _resolve_term(self, term):
        """
        Grab an entry from the foreground[s] associated with the project: first _fg, then _models, then _data if
        it exists. Store successful lookups in a "phone book" to cut down on queries doomed to 404
        :param term:
        :return:
        """
        try:
            return super(NestedLcaStudy, self)._resolve_term(term)
        except EntityNotFound:
            if self.data is not None:
                t = self._data.get(term)
                self._phonebook[term] = t
                return t
            raise

    def _matching_foreground(self, origin):
        try:
            return super(NestedLcaStudy, self)._matching_foreground(origin)
        except KeyError:
            if self.data is not None:
                if origin == self._data.origin:
                    return self._data
            raise

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

    def install_observation_model(self, prov_frag, scope=None):
        if scope is None:
            scope = prov_frag.get('Scope')
            if scope is None:
                raise ValueError('Must provide scope!')
        self.activity_container.clear_termination(scope)
        self.activity_container.terminate(prov_frag, scope)

    '''
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
    '''
