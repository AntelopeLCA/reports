"""
Load flowable synonyms from an ecoinvent archive
"""
from synonym_dict import TermExists, MergeError


def load_ecoinvent_synonyms(cat, ecoinvent_origin, interface='exchange', merge_strategy=None):
    """
    this will not work when ecoinvent is accessed remotely-- entities_by_type would only get loaded flows...
    getting every flow will require at least one API call (to synonyms) for every flow already gotten...
    Better to get synonym info from a Qdb.

    :param cat:
    :param ecoinvent_origin: origin + interface that accesses a fully-complemented EcospoldV2Archive (with MasterData)
    :param interface: default 'exchange'
    :param merge_strategy: valid values: 'graft', 'prune', 'distinct', 'merge'.  None = use term manager default.
    :return: a list of flows that were not able to be loaded
    """
    broken = []
    count = 0
    ar = cat.get_archive(ecoinvent_origin, interface)
    if ar.__class__.__name__ == 'EcospoldV2Archive':
        # raise TypeError(ar, 'Wrong archive type')
        ar.load_flows()  # this loads synonyms
    else:
        print('Warning: unsupported archive type')
    for f in ar.entities_by_type('flow'):
        try:
            cat.lcia_engine.add_flow_terms(f, merge_strategy=merge_strategy)
            count += 1
        except (TermExists, MergeError) as e:
            print('broken (%s): %s' % (e.__class__.__name__, f.link))
            broken.append(f)
    print('loaded %d flows' % count)
    return broken
