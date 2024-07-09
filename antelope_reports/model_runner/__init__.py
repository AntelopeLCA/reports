from .lca_model_runner import LcaModelRunner
from .scenario_runner import ScenarioRunner
from .sens_runner import SensitivityRunner
from .results_writer import ResultsWriter


def get_stage_name(_ff):
    try:
        _entity = _ff.fragment
    except AttributeError:
        _entity = _ff
    tries = ('stage_name', 'stagename', 'stage', 'group')
    for i in tries:
        sn = _entity.get(i, None)
        if sn:
            return sn
    return 'undefined'
