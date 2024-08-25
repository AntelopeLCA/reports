"""
One of the most common interpretive tools for LCA is to express the impacts of one activity in terms of
another. The Equivalency is a formalization of that.  The user supplies a reference exchange which is the comparison
activity, and a "measure" which is an optional dependent exchange for which the unit comparison is drawn (default:
just use the reference flow), and also documentary information (title and docstring).

The equivalency can then be queried by supplying an LCIA quantity, which returns the total score per unit of measure.
"""
from collections import namedtuple

EquivSpec = namedtuple('EquivSpec', ('title', 'origin', 'external_ref', 'measure', 'docstring'))  # measure = "how many (unit)"


class Equivalency:
    """
    The purpose of this is to create an easy way to compare two different activities in terms of their relative
    LCIA scores.
    """

    @classmethod
    def from_spec(cls, cat, e_spec: EquivSpec, ref_flow=None):
        """
        The EquivSpec provides a concise programmatic way of specifying equivalencies.
        :param cat:
        :param e_spec:
        :param ref_flow:
        :return:
        """
        rx = cat.query(e_spec.origin).get(e_spec.external_ref).reference(ref_flow)
        return cls(e_spec.title, rx, measure=e_spec.measure, docstring=e_spec.docstring)

    def __init__(self, title, rx, measure=None, docstring=None, **kwargs):
        """

        :param title: short title
        :param rx: Reference exchange
        :param measure: Dependent exchange for unit comparison [if None, uses the reference]
        :param docstring: annotation text
        :param kwargs: not currently used
        """
        self.title = title
        self._rx = rx
        self._meas = measure

        if measure is None:
            self._mx = self.rx
            self._measure = self._e.reference_value(self.ref_flow)
        else:
            self._mx = next(self._e.exchange_values(flow=measure))
            self._measure = self._e.exchange_relation(self.ref_flow, self._mx.flow, self._mx.direction)

        self.docstring = docstring or ''
        self.init_args = kwargs

    @property
    def _e(self):
        return self._rx.process

    @property
    def unit(self):
        return self._mx.flow.unit

    @property
    def measure(self):
        return self._measure

    @property
    def rx(self):
        return self._rx

    @property
    def ref_flow(self):
        return self.rx.flow

    @property
    def origin(self):
        return self._e.origin

    @property
    def external_ref(self):
        return self._e.external_ref

    def query_lcia(self, quantity):
        res = quantity.do_lcia(self._e.lci(ref_flow=self.rx))
        return res.total() / self.measure


class EquivalencyGenerator:
    """
    A handy tool for a limited set of circumstances.  Allows a user to retain a collection of LCIA quantities
    mapped to specific equivalencies.
    """
    def __init__(self, cat):
        self.cat = cat
        self.qs = []
        self._entries = dict()

    def add_equiv(self, q, equiv_spec):
        equiv = Equivalency.from_spec(self.cat, equiv_spec)
        if not hasattr(q, 'entity_type'):
            q = self.cat.get_canonical(q)
        if q not in self.qs:
            self.qs.append(q)
        self._entries[q.external_ref] = equiv

    def check_equiv(self, q):
        if q in self.qs:
            return self._entries[q.external_ref]

    @property
    def entries(self):
        for k in sorted(self._entries.keys()):
            yield k
