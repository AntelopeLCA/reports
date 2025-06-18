from .lca_model_runner import LcaModelRunner
from .scenario_runner import ScenarioRunner
from .sens_runner import SensitivityRunner
from .results_writer import ResultsWriter

import pandas as pd


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


def get_child_property(_ff, property_name, default=None, concat=None):
    """
    Utility function to retrieve a given property name from inside a fragment flow's anchor
    :param _ff:
    :param property_name:
    :param default:
    :param concat:
    :return:
    """
    if _ff.term.is_context:
        return _ff.term.term_node.name
    g = _ff.term.term_node.get(property_name)
    if g is not None and g != '':
        return g
    if hasattr(_ff.term.term_node, 'child_flows'):
        gs = list(filter(None, (f.get(property_name) for f in _ff.term.term_node.child_flows)))
        if len(gs) > 0:
            if concat:
                return concat.join(gs)
            else:
                return gs[0]
        else:
            return default


def get_top_level_flow(_ff, arg='Name', default='', tops=()):
    """
    Returns the name of the topmost child flow whose parent is either the study model or in the list of tops
    :param _ff:
    :param arg:
    :param default:
    :param tops: set/tuple/etc of fragments whose child flows should be named
    :return:
    """
    if _ff.superfragment and _ff.superfragment.fragment.top() not in tops:
        return get_top_level_flow(_ff.superfragment, arg=arg, default=default)
    elif _ff.superfragment is None:
        return _ff.fragment.get(arg, default)
    return _ff.superfragment.fragment.get(arg, default)


def lcias_to_dataframe(*ress, key=None):
    """
    Concatenate a set of LCIA results into a dataframe, quantities in column x components in row,
    using c.name
    :param ress:
    :param key: executable name extractor for *component* (not entity) (default getattr(c, 'name'))
    :return:
    """
    if key is None:
        key = lambda x: getattr(x, 'name')

    def _single_qty(r):
        return pd.DataFrame(((key(c), c.cumulative_result * 100 / r.total()) for c in r.components()),
                            columns=('Stage', r.quantity['indicator'])).set_index('Stage')

    return pd.concat((_single_qty(k) for k in ress), axis=1)
