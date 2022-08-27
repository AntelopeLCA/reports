"""
Synonyms and flowables for the WorldSteel XLSX file
"""
from synonym_dict import MergeError
from synonym_dict.synonym_dict import ParentNotFound

import re


discovered_synonyms = [
    ('Zinc(ii)', 'Zinc, ion'),
    ('Copper(ii)', 'Copper (II)'),
    ('Vanadium(v)', 'Vanadium, ion'),
    ('Nickel(ii)', 'Nickel, ion'),
    ('Silver(i)', 'Silver, ion'),
    ('Tin(ii)', 'Tin, ion'),
    ('sulfur oxides', 'Sulphur oxides'),
    ('sulfur dioxide', 'sulphur dioxide'),
    ('sulfur trioxide', 'sulphur trioxide'),
    ('sulfuric acid', 'sulphuric acid'),
    ('hydrogen sulfide', 'hydrogen sulphide'),
    ('pm2.5', 'Particulate matter, ≤ 2.5μm', 'Dust (PM2.5)'),
    ('pm10', 'Particulate matter, ≤ 10μm'),
    ('pm10', 'Particulate matter', 'Dust (> PM10)'),
    ('pm10', 'Particulate matter, > 2.5μm and ≤ 10μm', 'Dust (PM2.5 - PM10)'),
    ('Ethane, 1,1,2-trichloro-1,2,2-trifluoro-, CFC-113', 'cfc-113'),
    ('Ethane, 1,2-dichloro-1,1,2,2-tetrafluoro-, CFC-114', 'cfc-114'),
    ('Methane, bromodifluoro-, Halon 1201', 'halon 1201'),
    ('Methane, bromochlorodifluoro-, Halon 1211', 'halon 1211'),
    ('Ethane, 1-chloro-1,1-difluoro-, HCFC-142b', 'hcfc-142b'),
    ('Ethane, chloropentafluoro-, CFC-115', 'cfc-115'),
    ('Ethane, 1,2-dibromotetrafluoro-, Halon 2402', 'halon 2402'),
    ('Methane, bromotrifluoro-, Halon 1301', 'halon 1301'),
    ('Methane, dibromodifluoro-, Halon 1202', 'halon 1202'),
    ('Ethane, 1,1-dichloro-1-fluoro-, HCFC-141b', 'hcfc-141b'),
    ('Ethane, 1-chloro-1,1-difluoro-, HCFC-142b', 'hcfc-142b'),
    ('Ethane, 2,2-dichloro-1,1,1-trifluoro-, HCFC-123', 'hcfc-123'),
    ('chlorotetrafluoroethane', 'Ethane, 2-chloro-1,1,1,2-tetrafluoro-, HCFC-124', 'hcfc-124', 'R 124 (chlorotetrafluoroethane)'),
    ('Methane, chlorodifluoro-, HCFC-22', 'hcfc-22'),
    ('460-73-1', 'R 245fa (1,1,1,3,3-Pentafluoropropane)'),
    ('354-33-6', 'R 125 (pentafluoroethane)'),
    ('430-66-0', 'R 143 (trifluoroethane)'),
    ('76-16-4', 'R 116 (hexafluoroethane)'),
    ('Methane, tetrachloro-, R-10', 'tetrachloromethane', 'Carbon tetrachloride (tetrachloromethane)'),
    ('Methane, tetrafluoro-, R-14', 'tetrafluoromethane'),
    ('Methane, trichlorofluoro-, CFC-11', 'CFC-11'),
    ('75-10-5', 'R 32 (difluoromethane)', 'difluoromethane'),
    ('75-46-7', 'trifluoromethane', 'R 23 (trifluoromethane)'),
    ('75-09-2', 'methylene chloride', 'Dichloromethane (methylene chloride)'),
    ('75-43-4', 'R 21 (Dichlorofluoromethane)', 'Dichlorofluoromethane'),
    ('74-87-3', 'Chloromethane (methyl chloride)'),
    ('811-97-2', 'tetrafluoroethane'),
    ('75-37-6', 'R 152a (difluoroethane)'),
    ('Propane, 1,3-dichloro-1,1,2,2,3-pentafluoro-, HCFC-225cb', 'hcfc-225cb', 'hcfc225cb', 'hcfc 225cb'),
    ('Propane, 3,3-dichloro-1,1,1,2,2-pentafluoro-, HCFC-225ca', 'hcfc-225ca', 'hcfc225ca', 'hcfc 225ca'),
    ('Cyclohexane, pentyl-', 'pentyl cyclohexane'),
    ('75-65-0', 't-Butyl alcohol'),
    ('622-96-8', 'para-Ethyltoluene'),
    ('106-42-3', 'para-xylene'),
    ('75-00-3', 'monochloroethane'),
    ('611-14-3', 'ortho-ethyltoluene'),
    ('Nitric oxide', 'nitrogen monoxide'),
    ('Biological oxygen demand', 'biological oxygen demand (BOD)'),
    ('Chemical oxygen demand', 'chemical oxygen demand (COD)'),
    ('Nitrous oxide', 'Nitrous oxide (laughing gas)'),
    ('chloroform', 'Trichloromethane (chloroform)'),
    ('Water, river', 'River water', 'River water, regionalized'),
    ('Cooling water to river', 'Cooling water to river, regionalized'),
    ('Water, fresh', 'Fresh water'),
    ('Water, ground', 'Ground water', 'Ground water, regionalized'),
    ('Water, lake', 'Lake water', 'Lake water, regionalized'),
    ('Lake water to turbine', 'Lake water to turbine, regionalized'),
    ('River water to turbine', 'River water to turbine, regionalized'),
    ('Turbined water to river', 'Turbined water to river, regionalized'),
    ('Processed water to river', 'Processed water to river, regionalized')
]


WS_skips = {'unspecified', 'unspec.', 'biotic', 'deposited', 'total N', 'N-compounds', 'aviation', 'dissolved',
            'suspended', 'process water', 'waste water, treated', 'unspecified, as N', 'land use change',
            'atmospheric nitrogen', 'underground deposit', 'PAH, unspec.', 'unspecific', 'isomers',
            'evapotranspiration', 'general', 'as total N', 'carcinogen', 'peat oxidation'}


'''
The following regexp matches names like "some name (some synonym)" where groups(1) = ('some name', 'some synonym')
'''
exp = re.compile(r'^([^(]+)\s\(([^)]+)\)$')


def ws_syn_finder(_cat, iters):
    s = set()
    for ws_flow in iters:
        if _cat.lcia_engine[ws_flow.context].sense != 'Sink':
            continue
        m = exp.match(ws_flow.name)
        if bool(m):
            n, p = m.groups(1)
            if n == 'Dust':
                continue
            if p not in WS_skips and len(p) > 6:
                ps = tuple(filter(lambda x: x not in WS_skips, p.split('; ')))
                s.add((n, ws_flow.name, *ps))
    return s


def _known_unknown(_cat, *terms):
    uk = set(terms)
    for t in terms:
        try:
            k = _cat.lcia_engine.get_flowable(t)
            uk.remove(t)
            return k.name, uk
        except KeyError:
            pass


def _worldsteel_synonyms(_cat, syns):
    try:
        _cat.lcia_engine.add_terms('flow', *syns)
    except MergeError:
        k, uk = _known_unknown(_cat, *syns)
        if k:
            try:
                _cat.lcia_engine.merge_flowables(k, *uk)
                print('merged %s' % (syns,))
            except ParentNotFound:
                print('wtf %s' % (syns,))
        else:
            print('could not merge %s' % (syns,))


def worldsteel_flowables(cat, ws):
    """
    Attempts to add flowables with the format "One name, comma-separated (alternate name)",
    with a large set of exclusions.  Adds 'one name, comma-separated' and 'alternative name' as synonyms.
    :param cat: a catalog
    :param ws: a query whose flows() have names matching the above format
    :return:
    """
    # worldsteel flowables
    ws_syns = ws_syn_finder(cat, ws.flows())

    for syns in ws_syns:
        _worldsteel_synonyms(cat, syns)
