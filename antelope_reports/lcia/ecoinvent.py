"""
Load flowable synonyms from an ecoinvent archive
"""


def load_ecoinvent_synonyms(cat, query):
    ar = cat.get_archive(query.origin, 'exchange')
    if ar.__class__.__name__ != 'EcospoldV2Archive':
        raise TypeError(ar, 'Wrong archive type')
    ar.load_flows()  # this loads synonyms
    for f in ar.entities_by_type('flow'):
        cat.lcia_engine.add_flow(f)
