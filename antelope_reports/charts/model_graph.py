import pydot
from antelope import check_direction
from antelope_core.autorange import AutoRange
from math import log10


def line_break(f, start=40):
    t = ''
    while f.find(' ', start) >= start:
        x = f.find(' ', start)
        t += f[:x]
        t += '\n'
        f = f[x+1:]
    t += f
    return t


class ModelGraph(object):
    """
    Creates a model graph in graphviz dot format using pydot.
    """
    def _flowtext(self, text):
        return line_break(text, start=self._text_width)

    def _dir(self, frag):
        """
        Returns the direction node
        :param frag:
        :return:
        """
        if frag.is_balance:
            _d = pydot.Node(frag.uuid[:10] + '_d', shape="box", style="dotted", label="balance")
        else:
            shape = {'Output': 'rarrow',
                     'Input': 'larrow'}[check_direction(frag.direction)]
            if bool(self.values):
                ev = frag.exchange_value(self._scenario or True)
                if bool(self.autoscale) and frag.flow.unit != 'Item(s)':
                    au = AutoRange(abs(ev), bias=-0.01)
                    label = '%.3g %s' % (au.adjust(ev), au.adj_unit(frag.flow.unit))
                else:
                    if ev == 0:
                        m = 2  # we just want a '0.0'
                    else:
                        m = log10(abs(ev))
                    if abs(m) <= 3:
                        if m > 1:
                            label = '%.1f %s' % (ev, frag.flow.unit)
                        elif m > -1:
                            label = '%.2f %s' % (ev, frag.flow.unit)
                        else:
                            label = '%.3f %s' % (ev, frag.flow.unit)
                    else:
                        label = '%.3g %s' % (ev, frag.flow.unit)
            else:
                label = frag.flow.unit
            _d = pydot.Node(frag.uuid[:10] + '_f', shape=shape, label=label)
        self._graph.add_node(_d)
        return _d

    def __init__(self, model, scenario=None, values=True, group='StageName', rankdir="RL", descend=False, text_width=25,
                 autoscale=None,
                 focus=True,
                 **kwargs):
        """

        :param model: a spanner (reference fragment)
        :param group: what to use for grouping. This can either be an attribute, or a callable function.
        """
        self._model = model.top()
        self._scenario = scenario
        self.values = values
        self.autoscale = autoscale

        self._text_width = int(text_width)
        self._group = group
        self._descend = descend

        self._graph = pydot.Dot(model.name, graph_type='digraph', strict=True, rankdir=rankdir, **kwargs)
        self._refflow = pydot.Node("ref flow", shape='none', height=0.25, label=model.flow['name'])
        self._graph.add_node(self._refflow)
        self.anchor(self._model, self._refflow, first=True)

    @property
    def graph(self):
        return self._graph

    @staticmethod
    def display():
        """
        To display a model graph from an ipython shell, run the following:

        from IPython.display import Image, display

        %matplotlib inline  # add if using jupyter

        def view_pydot(pdot):
            plt = Image(pdot.graph.create_png())
            display(plt)

        view_pydot(mg.graph)

        where mg is a ModelGraph instance.
        :return:
        """
        msg = '''\
# To display a model graph in a jupyter notebook environment, run the following
from IPython.display import Image, display

%matplotlib inline  # add if using jupyter

def view_pydot(pdot):
    plt = Image(pdot.graph.create_png())
    display(plt)
            
view_pydot(mg.graph)  # mg is a ModelGraph instance
'''
        print(msg)

    def get_group(self, frag):
        if self._group is None:
            return frag.name
        elif isinstance(self._group, str):
            return frag.get(self._group, '')
        elif callable(self._group):
            return self._group(frag)
        return frag.name

    def anchor(self, frag, node, first=False):
        _d = self._add_dir(frag, node)
        lbl = frag.uuid[:10] + '_anch'
        term = frag.termination(self._scenario)
        if term.is_null:
            cutoff = pydot.Node(lbl, shape="none", label=self._flowtext(frag.flow.name))
            self._graph.add_node(cutoff)
            self._graph.add_edge(pydot.Edge(cutoff, _d, arrowsize=0, minlen=1.3))
            return cutoff
        elif term.is_frag:
            if term.is_fg:
                if first:
                    anchor = pydot.Node(lbl, shape="rectangle", style="rounded", label=frag.get('Name', frag.name))
                else:
                    anchor = pydot.Node(lbl, shape="circle", label='')
                self._graph.add_node(anchor)
                self._graph.add_edge(pydot.Edge(anchor, _d, arrowsize=0))
                self.child_flows(frag, anchor)
            elif self._descend and frag.is_background:
                anchor = pydot.Node(lbl, shape="box", label=self._flowtext(frag.flow.name), height=0.25)
                self._graph.add_node(anchor)
                self._graph.add_edge(pydot.Edge(anchor, _d, arrowsize=0))
                self.child_flows(term.term_node, anchor)

            else:
                subfrag = pydot.Node(lbl, shape="box", height=0.25, label=self._flowtext(term.term_flow.name))
                self._graph.add_node(subfrag)
                self._graph.add_edge(pydot.Edge(subfrag, _d, arrowsize=0))
                self.child_flows(frag, subfrag)
        elif term.is_context:
            cx = pydot.Node(lbl, shape="box", style="dotted", height=0.25, label=self._flowtext(term.term_node.name))
            self._graph.add_node(cx)
            self._graph.add_edge(pydot.Edge(cx, _d, arrowsize=0, label=term.term_flow['name']))
            return cx

        elif term.is_process:
            anchor = pydot.Node(lbl, style="rounded", shape="rect", height=0.35,
                                label=line_break(term.term_node.name, start=self._text_width))
            self._graph.add_node(anchor)
            self._graph.add_edge(pydot.Edge(anchor, _d, arrow=False))
            self.child_flows(frag, anchor)

    def _add_dir(self, cf, node):
        _d = self._dir(cf)
        self._graph.add_edge(pydot.Edge(_d, node, arrowsize=0))
        return _d

    '''
    def _add_child(self, cf, node):
        cf_f = pydot.Node(cf.uuid[:10] + '_d', shape="box", height=0.25, label=cf.flow.name)
        self._graph.add_node(cf_f)
        self._graph.add_edge(pydot.Edge(cf_f, cf_d, arrowsize=False))
        return cf_f
    '''

    def child_flows(self, frag, node):
        for cf in sorted(frag.child_flows, key=lambda x: (x.direction, self.get_group(x), x.flow.unit, -x.observed_ev),
                         reverse=True):
            self.anchor(cf, node)

    def write_png(self, filename):
        self._graph.write_png(filename)

    def write_svg(self, filename):
        self._graph.write_svg(filename)
