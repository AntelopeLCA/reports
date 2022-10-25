"""
Antelope LCIA analysis tools

The purpose of this package is to support LCIA data quality evaluation by comparing LCI + LCIA flow coverage
across methods and data sources.

"""

from .lcia_eval import LciaEval
from .flow_comparator import FlowComparator
# from .screening import process_screen, substance_screen, show_top_n


from synonym_dict import MergeError


def add_synonym_sets(cat, list_of_sets):
    """
    An algorithm for adding / merging sets of synonyms
    :param cat:
    :param list_of_sets:
    :return:
    """
    for terms in list_of_sets:
        try:
            cat.lcia_engine.add_terms('flow', *terms)
        except MergeError:
            t = list(terms)
            lost = []
            while 1:
                try:
                    cat.lcia_engine.get_flowable(t[0])
                except KeyError:
                    try:
                        lost.append(t.pop(0))
                    except IndexError:
                        print('somehow we found no terms to add in %s' % lost)
                        break
                    continue
                break
            if t:
                cat.lcia_engine.merge_flowables(*t)
