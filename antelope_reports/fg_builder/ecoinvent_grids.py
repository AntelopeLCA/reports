import json
import os
import re
from antelope import UnknownOrigin


SYSTEM_MODELS = ('cutoff', 'apos', 'conseq', 'undefined')
LEVELS = ('low', 'medium', 'high')


class DataPersistenceError(Exception):
    pass


class _WrongNumberOfHits(Exception):
    pass


class EcoinventGrids(object):
    """
    Creates a special-purpose JSON file that maps grid geography, system model, and voltage level to external_ref
    for a given Ecoinvent version.
    """
    _version = None
    _file = None
    _j = None

    def _print(self, *args):
        print('%s: ' % self.__class__.__name__, end='')
        print(*args)

    def __init__(self, cat, version, path=None, levels=None, reset=False, local=None):
        """
        
        :param cat: Catalog that knows about ecoinvent 
        :param version: Ecoinvent semantic version available to the catalog (e.g. '3.8') 
        :param path: Directory to save + load JSON cache (default is the working directory)
        :param levels: which grid levels to use (default is all, i.e. ('low', 'medium', 'high'))
        :param reset: 
        :param local: [None] If present, prefix to pre-pend to the origin query (e.g. 'local.ecoinvent...')
        """
        self._cat = cat
        self._version = version
        self._levels = levels or LEVELS
        self._local = local
        filename = 'ecoinvent_grids_%s.json' % version
        if path is None:
            self._file = filename
        else:
            self._file = os.path.join(path, filename)
        if reset or not os.path.exists(self._file):
            self._j = {'data': 'EcoinventGrids',
                       'version': self._version}
            self.save()
        else:
            self.load()

    @property
    def version(self):
        return str(self._version)

    @property
    def models(self):
        for m in SYSTEM_MODELS:
            try:
                self._cat.query(self._org(m))
                yield m
            except UnknownOrigin:
                pass

    def _org(self, model):
        org = 'ecoinvent.%s.%s' % (self.version, model)
        if self._local:
            return '.'.join([str(self._local), org])
        else:
            return org

    @property
    def levels(self):
        for l in self._levels:
            yield l

    def load(self):
        with open(self._file, 'r') as fp:
            self._j = json.load(fp)
            try:
                assert self._j['data'] == 'EcoinventGrids', 'File content error %s' % self._j['data']
                assert self._j['version'] == self._version, 'File version error %s' % self._version
            except KeyError:
                raise DataPersistenceError('Keys missing: %s' % self._file)

    def save(self):
        with open(self._file, 'w') as fp:
            json.dump(self._j, fp, indent=2)

    def locations(self, loc, model=None):
        if model is None:
            model = next(self.models)

        return list(set(k['SpatialScope'] for k in self._cat.query(self._org(model)).processes(
            Name='^market( group)? for electricity',
            SpatialScope=loc)))  # should be an exact match

    def _get_em(self, _g, _m, _l):
        return list(_h.external_ref for _h in self._cat.query(self._org(_m)).processes(
            Name=('^market( group)? for electricity.*%s voltage' % _l),
            SpatialScope='^%s$' % _g))  # should be an exact match

    def _lookup_location(self, g):
        curr_g = self._j.get(g, None)
        new_g = {m: {l: self._get_em(g, m, l) for l in self.levels} for m in self.models}
        if len(new_g) == 0:
            raise ValueError('No valid models found')
        if curr_g == new_g:
            self._print('Location %s: no change' % g)
            return  # nothing to do
        else:
            if curr_g is None:
                self._print('adding location %s' % g)
            else:
                self._print('updating location %s' % g)
            self._j[g] = new_g
            self.save()

    def grids_by_location(self, loc, reset=False, show=False):
        """
        given a spatial scope, returns a dict of {level: {model: [grids]}} where level in self.levels and model in
        self.models
        :param loc:
        :param reset: [False]
        :param show: [False]
        :return:
        """
        if reset or (loc not in self._j):
            self._lookup_location(loc)
        if show:
            self.show_grids(loc)
        return self._j[loc]

    def show_grids(self, loc, model=None, level=None):
        if loc in self._j:
            for mdl, lvls in self._j[loc].items():
                if model:
                    if mdl != model:
                        continue
                for lvl, grids in lvls.items():
                    if level:
                        if lvl != level:
                            continue
                    for grid in grids:
                        t = self._cat.query(self._org(mdl)).get(grid)
                        print('%s: %s, %s: %s %s' % (loc, mdl, lvl, grid, t.name))

    def _create_grid_fragment(self, fg, name, model, grids, name_regex):
        origin = self._org(model)
        terms = [fg.cascade(origin).get(g) for g in grids]
        if name_regex is not None:
            terms = list(t for t in terms if bool(re.search(name_regex, t['name'], flags=re.IGNORECASE)))

        if len(terms) != 1:
            for t in terms:
                print(t)
            raise _WrongNumberOfHits(len(terms))
        term = terms[0]
        # keep the term's native reference flow for auto-consumption purposes, in case the fragment is expanded
        return fg.new_fragment(term.reference().flow, 'Output', external_ref=name, background=True, termination=term)

    @staticmethod
    def _add_to_chooser(fg, grid, level, scenario):
        # add to grid chooser
        cname = 'grid-chooser-%s' % level
        if fg[cname] is None:
            c = fg.new_fragment(fg['elec'], 'Output')
            fg.observe(c, name=cname)
        else:
            c = fg[cname]
        if scenario not in c.scenarios():
            c.terminate(grid, scenario=scenario)
            if c.term.is_null:  # set default to first encountered
                c.terminate(grid)

    def create_loc_grids(self, fg, loc, rshort=None, chooser=True, name_regex=None, suffix=None, show=False):
        """
        Builds grid models in the supplied foreground for the specified location, named 'grid-[region]-[model]-[level]',
        where 'region' is the first word of loc.

        If chooser is True, adds the grid as a termination to the 'grid-chooser-[level]' model under the scenario
        name '[region]-grid-[model]'. The grid chooser is created if it does not exist.

        :param fg: A foreground to store the grid models
        :param loc: Create grids for this locale. should be an exact match, e.g. ^(loc)$
        :param rshort: [None] short name to use for the grid in the scenario chooser (default is the first 'word' in
          the loc)
          (scenario will be `rshort`-grid-`model`; fragment will be grid-`rshort`-`model`-`level`)
        :param chooser: Whether to add the grids to a chooser fragment
        :param name_regex: Optional regex to filter from available grid process names [must hit exactly one]
        :param suffix: add dash-delimited suffix to fragment name, and scenario name if chooser is True
        :return:
        """
        fg.add_or_retrieve('elec', 'kWh', 'Electricity, at user')  # we need different levels, I suppose....
        md = self.grids_by_location(loc, show=show)
        if rshort is None:
            rshort = re.match('^\S+', loc).group(0)
        for model, ld in md.items():
            for level, grids in ld.items():
                if level not in self._levels:
                    continue
                name = 'grid-%s-%s-%s' % (rshort, model, level)
                if suffix:
                    name = '%s-%s' % (name, suffix)
                if fg[name] is None:
                    try:
                        grid = self._create_grid_fragment(fg, name, model, grids, name_regex)
                    except _WrongNumberOfHits as e:
                        if e.args[0] > 1:
                            print('Warning (skipped): Multiple hits [%d] for %s, %s, %s' % (e.args[0], loc, model, level))
                        else:
                            print('no target found for %s, %s, %s' % (loc, model, level))
                        continue

                else:
                    grid = fg[name]

                if chooser:
                    scenario = '%s-grid-%s' % (rshort, model)
                    if suffix:
                        scenario = '%s-%s' % (scenario, suffix)
                    self._add_to_chooser(fg, grid, level, scenario)
