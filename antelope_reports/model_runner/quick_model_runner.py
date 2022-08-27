import json

from antelope_reports.model_runner import LcaModelRunner


class QuickModelRunner(LcaModelRunner):

    @classmethod
    def from_csv_refs(cls, cat, fg_name, refs_file):
        """
        CSV file should
        :param cat:
        :param fg_name:
        :param refs_file:
        :return:
        """
        fg = cat.foreground(fg_name)

        with open(refs_file) as fp:
            refs = json.load(fp)

        refs = [ref.split('/', maxsplit=1) for ref in refs]
        procs = [cat.query(o).get(k) for o, k in refs]

        qm = cls(fg, procs)
        return qm

    def __init__(self, fg, refs=None, **kwargs):
        """

        :param fg: A foreground to store the fragment models
        :param refs: an iterable of process references to run.  If the process is multi-output, supply a 2-tuple of
        process_ref, ref_flow
        :param kwargs:
        """
        super(QuickModelRunner, self).__init__(**kwargs)

        self._fg = fg
        self._models = dict()

        if refs:
            for ref in refs:
                self.add_ref(ref)

    def add_ref(self, ref):
        if isinstance(ref, tuple):
            px = ref[0]
            rx = px.reference(ref[1])
        else:
            px = ref
            rx = px.reference()
        name = '%s (%s)' % (px.name, rx.flow.name)
        if name in self._models:
            print('Name %s is already registered' % name)
            return

        if px.entity_type == 'process':
            model = self._fg.create_process_model(px, ref_flow=rx.flow)
        else:
            model = px
        self._models[name] = model
        self.add_scenario(name)

    def _scenario_index(self, scenario):
        model = self._models[scenario]
        return model.name, model.flow.name, model.observed_ev, model.flow.unit

    def _run_scenario_lcia(self, scenario, lcia, **kwargs):
        model = self._models[scenario]
        return model.fragment_lcia(lcia, **kwargs)

    def compute_results(self, lcia):
        for l in lcia:
            self.run_lcia(l)

    def save_details(self, pg, prefix, lcia):
        node = self._models[pg].term.term_node.external_ref
        res = self.result(pg, lcia)
        fname = 'details-%s-%s-%s.json' % (prefix, node, lcia.external_ref)
        with open(fname, 'w') as fp:
            json.dump(res.serialize_components(detailed=True), fp, indent=2)


def generate_results(cat, lcia, fg_name, refs_file, out_file):
    qm = QuickModelRunner.from_csv_refs(cat, fg_name, refs_file)
    qm.compute_results(lcia)
    qm.scenario_summary_tbl(out_file)
