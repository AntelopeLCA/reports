from .lca_study import LcaStudy, DuplicateRoute
from .model_updater import XlsxForegroundUpdater
from .scenario_updater import XlsxScenarioUpdater
from .ecoinvent_grids import EcoinventGrids, LEVELS


def create_grids(cat, fg, ei_version, *grids, levels=LEVELS, chooser=True, **kwargs):
    """
    This function ensures that locality-based electricity grids are present as fragment models in the
    supplied foreground.

    :param cat: required to access ecoinvent
    :param fg: where to build the grid fragments
    :param ei_version: ecoinvent version
    :param grids: remaining positional params are grid geographies to lookup
    :param levels: voltage levels. Default is ('low', 'medium', 'high')
    :param chooser: [True] whether to create a grid chooser in the foreground
    :param kwargs: passed to EcoinventGrids:
     - 'path' - where to serialize the lookup file
     - 'reset' - whether to blow away an existing lookup file
     - 'local' - if present, prefix to prepend to ecoinvent origins.
    :return:
    """
    egl = EcoinventGrids(cat, version=ei_version, levels=levels, **kwargs)
    for region in grids:
        egl.create_loc_grids(fg, region, rshort=region, chooser=chooser)
