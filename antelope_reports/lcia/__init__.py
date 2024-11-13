"""
Antelope LCIA analysis tools

The purpose of this package is to support LCIA data quality evaluation by comparing LCI + LCIA flow coverage
across methods and data sources.

"""

from .lcia_eval import LciaEval
from .flow_comparator import FlowComparator
# from .screening import process_screen, substance_screen, show_top_n
from .xlsx_lcia import QdbGSheetClient
from .traci import traci_2_combined_eutrophication

from antelope import EntityNotFound
from synonym_dict import MergeError


S3_QDB_SHEET_ID = '1gBi9690IcMRf4B8oAgGQm02yaj459i4vHDmMH2SXlVE'


class Scope3Qdb(QdbGSheetClient):
    def __init__(self, fg, credential_file=None, **kwargs):
        super(Scope3Qdb, self).__init__(fg, S3_QDB_SHEET_ID, credential_file=credential_file, **kwargs)


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
                # this is clearly broken
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


class AdvancedLcia(object):

    s3_qdb = None

    def __init__(self, cat, lcia_fg, google_credentials=None):
        self._cat = cat
        if hasattr(lcia_fg, 'new_quantity'):
            self._lcia = lcia_fg
        else:
            self._lcia = cat.foreground(lcia_fg, create=True)
        if google_credentials:
            self.s3_qdb_init(google_credentials)

    def s3_qdb_init(self, google_credentials):
        self.s3_qdb = Scope3Qdb(self._lcia, google_credentials)

    def get_s3_qdb_indicator(self, indicator, external_ref=None):
        return self.s3_qdb.update_cfs(indicator, external_ref)

    def traci_combined_eutrophication(self, external_ref='q_eutrophication', omit_n2=True):
        traci = self._cat.query('lcia.traci.2.1')
        qe = traci_2_combined_eutrophication(traci, self._lcia, external_ref=external_ref, omit_n2=omit_n2)
        return qe

    def retrieve_lcia_method(self, origin, external_ref, **kwargs):
        try:
            q = self._lcia.get(external_ref)
        except EntityNotFound:
            q = self._cat.query(origin).get(external_ref)
        for k, v in kwargs.items():
            q[k] = v
        return q
