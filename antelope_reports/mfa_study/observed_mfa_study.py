from .dynamic_unit_study import DynamicUnitLcaStudy
from .lc_mfa_study import DuplicateRoute
from typing import Dict, Tuple, List, Optional
from pydantic import BaseModel

from antelope import comp_dir, EntityNotFound


class StudySpec(BaseModel):

    stage_names: Dict[str, str]  # target: stagename
    logistics_mappings: Dict[str, Tuple[str, str]]  # flow: target, stagename
    activity_mappings: Dict[Tuple[str, str], Tuple[str, str]]  # direction, flow: target, stagename
    routes: Dict[str, Tuple]  # name: tuple-spec
    study_sinks: Dict[str, Dict[str, Optional[float]]]  # flow: {target: share}
    study_sources: Dict[str, Dict[str, Optional[float]]]  # flow: {target: share}


class ObservedMfaStudy(DynamicUnitLcaStudy):
    def _make_study_mapping(self, container, flow, direction, target, stage=None, scenario=None):
        if stage is None:
            stage = container['Name']
        f = self._resolve_term(flow)
        try:
            cf = next(container.children_with_flow(f, direction=direction))
        except StopIteration:
            cf = self.fg.new_fragment(f, direction, parent=container)

        term = self._resolve_term(target)
        cf.clear_termination(scenario=scenario)
        cf.terminate(term, scenario=scenario, descend=False)
        cf['StageName'] = stage

    def make_logistics_mappings(self, logistics_mappings):
        for k, v in logistics_mappings.items():
            t, stage = v
            self._make_study_mapping(self.logistics_container, k, 'Input', t, stage=stage)

    def make_activity_mappings(self, activity_mappings):
        for k, v in activity_mappings.items():
            d, f = k
            t, s = v
            self._make_study_mapping(self.activity_container, f, d, t, stage=s)

    def _make_study_market(self, flow_ref, sense, market_spec, stage_names=None):
        direction = comp_dir(sense)
        try:
            flow = self.data.get(flow_ref)
        except EntityNotFound:
            flow = self._resolve_term(flow_ref)
        try:
            next(self.study_container.children_with_flow(flow, direction=direction))
        except StopIteration:
            mkt = self.fg.new_fragment(flow, direction, parent=self.study_container)
            self.make_market(mkt, market_spec, sense, stage_names=stage_names)

    def make_study_sources(self, study_sources, stage_names=None):
        for k, v in study_sources.items():
            self._make_study_market(k, 'Source', v, stage_names)

    def make_study_sinks(self, study_sinks, stage_names=None):
        for k, v in study_sinks.items():
            self._make_study_market(k, 'Sink', v, stage_names)

    def make_study(self, study_spec: StudySpec):
        self.make_routes(study_spec.routes, stage_names=study_spec.stage_names)
        self.make_activity_mappings(study_spec.activity_mappings)
        self.make_logistics_mappings(study_spec.logistics_mappings)
        self.make_study_sources(study_spec.study_sources, stage_names=study_spec.stage_names)
        self.make_study_sinks(study_spec.study_sinks, stage_names=study_spec.stage_names)
