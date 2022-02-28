"""
Positive-negative chart.  Draws a vertically-oriented "waterfall-lite" chart with one bar pointing up containing
all the positive segments, and another bar pointing down containing all the negative segments, so that the negative
bar ends at the net result, which is annotated.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt

from pandas import DataFrame, MultiIndex


from .base import save_plot, net_color, standard_labels  # open_ylims,
from .waterfall import random_color
from antelope_core.autorange import AutoRange


mpl.rcParams['patch.force_edgecolor'] = True
mpl.rcParams['errorbar.capsize'] = 3
mpl.rcParams['grid.color'] = 'k'
mpl.rcParams['grid.linestyle'] = ':'
mpl.rcParams['grid.linewidth'] = 0.5
mpl.rcParams['lines.linewidth'] = 1.0
mpl.rcParams['axes.autolimit_mode'] = 'round_numbers'
mpl.rcParams['axes.xmargin'] = 0
mpl.rcParams['axes.ymargin'] = 0


class _PosNegAxes(object):

    def __init__(self, ax, size, qty, span, bar_width=0.28, autorange=False, color=None, fontsize=10):

        self._fontsize = fontsize

        self._ax = ax
        self._size = size
        self._qty = qty

        self._color = color or random_color(qty.uuid)

        x, y = span  # to confirm it's a 2-tuple
        self._span = x, y
        self._bw = bar_width

        self._pos_handle = None
        self._neg_handle = None  # for legend

        if autorange:
            a = AutoRange(self._span[1] - self._span[0])
            self._ar_scale = a.scale
            self._unit = a.adj_unit(qty.unit)
        else:
            self._ar_scale = 1.0
            self._unit = qty.unit

        ylim = [x, y + .065 * (y - x)]  # push out the top limit
        self._ax.set_ylim([k * self._ar_scale for k in ylim])


    @property
    def _tgap(self):
        """
        Useful only for vertical bars.  We want to add 3pt, which is 1/18in.  span / size" = x / 1/18"
        :return:
        """
        return (self._span[1] - self._span[0]) * self._ar_scale / (self._size * 18)

    def draw_pos_neg(self, x, pos, neg, num_format):

        pos *= self._ar_scale
        neg *= self._ar_scale

        h = self._ax.bar(x, pos, align='center', width=0.85 * self._bw, color=self._color)
        if self._pos_handle is None:
            self._pos_handle = h
        if neg != 0:
            self._ax.text(x + 0.5 * self._bw, pos + self._tgap, num_format % pos, ha='center', va='bottom',
                          fontsize=self._fontsize)
            x += self._bw
            h = self._ax.bar(x, neg, bottom=pos, width=0.62 * self._bw, align='center', color=net_color,
                       linewidth=0)
            if self._neg_handle is None:
                self._neg_handle = h
            # edge line
            self._ax.plot([x, x - self._bw], [pos, pos], color=(0.3, 0.3, 0.3), zorder=-1, linewidth=0.5)

            x += self._bw
            tot = pos + neg
            self._ax.plot([x, x], [0, tot], color='k', marker='_')
            self._ax.text(x, 0.5 * tot, num_format % tot, ha='center', va='center',
                          bbox=dict(boxstyle='square,pad=0.025', fc='w', ec='none'),
                          fontsize=self._fontsize)
            self._ax.plot([x, x + self._bw], [0, 0], linewidth=0)

            # edge line
            self._ax.plot([x, x - self._bw], [tot, tot], color=(0.3, 0.3, 0.3), zorder=-1, linewidth=0.5)
        else:
            self._ax.text(x, pos, '%3.2g' % pos,
                          fontsize=self._fontsize)

    def draw_error_bars(self, x, pos, pos_err, neg, neg_err):
        xs = [x, x + self._bw]
        ys = [pos, pos + neg]
        yerr = list(zip(pos_err, neg_err))
        self._ax.errorbar(xs, ys, yerr=yerr, fmt='.', color='#305040')

    def finish(self, legend=True):

        self._ax.spines['top'].set_visible(False)
        self._ax.spines['bottom'].set_visible(False)
        self._ax.spines['left'].set_visible(True)
        self._ax.spines['left'].set_linewidth(2)
        self._ax.spines['right'].set_visible(False)

        self._ax.plot(self._ax.get_xlim(), [0, 0], 'k', linewidth=2, zorder=-1)
        # open_ylims(self._ax, margin=0.05)  # this issue has supposedly been fixed?
        self._ax.set_ylabel(self._unit,
                            fontsize=self._fontsize)

        if legend and self._neg_handle is not None:
            self._ax.legend((self._pos_handle, self._neg_handle), ('Impacts', 'Avoided'))

        self._ax.set_title(self._qty['ShortName'], fontsize=self._fontsize + 2)

    @property
    def name(self):
        return self._qty['Name']

    @property
    def unit(self):
        return self._unit


class PosNegChart(object):
    """
    A PosNeg Chart draws the sum of forward and avoided burdens for each result object, together on the same
    axes, with an annotated net total.
    """

    def __init__(self, *args, horiz=False, size=4, aspect=0.4, bar_width=0.28, filename=None,
                 num_format='%3.2g', legend=True, **kwargs):
        """
        aspect reports the aspect ratio of a single chart.  aspect + bar_width together determine the aspect
        ratio of multi-arg charts.

        :param args: one or more LciaResult objects
        :param color:
        :param horiz:
        :param size:
        :param aspect:
        :param bar_width:
        :param filename:
        :param num_format:
        :param kwargs: color, autorange, fontsize...
        :param autorange:
        """
        self._pos = []
        self._neg = []
        self._idx = []

        ptr = bar_width
        for i, arg in enumerate(args):
            _pos = 0.0
            _neg = 0.0
            for c in arg.keys():
                val = arg[c].cumulative_result
                if val > 0:
                    _pos += val
                else:
                    _neg += val

            self._pos.append(_pos)
            self._neg.append(_neg)
            self._idx.append(ptr)

            if _neg != 0:
                ptr += 2 * bar_width

            ptr += (1 - 2 * bar_width)

        span = [min(self._neg), max(self._pos)]

        cross = size * aspect * (ptr + bar_width)
        if horiz:
            fig = plt.figure(figsize=[size, cross])
        else:
            fig = plt.figure(figsize=[cross, size])

        ax = fig.add_axes([0, 0, 1.0, 1.0])

        qty = args[0].quantity

        if filename is None:
            filename = 'pos_neg_%.3s.eps' % qty.uuid

        self._pna = _PosNegAxes(ax, size, qty, span, bar_width=bar_width, **kwargs)

        for i, arg in enumerate(args):
            if horiz:
                raise NotImplementedError
                # self._pos_neg_horiz(ax, i)
            else:
                self._pna.draw_pos_neg(self._idx[i], self._pos[i], self._neg[i], num_format=num_format)

        standard_labels(ax, [arg.scenario for arg in args], ticks=self._idx, rotate=False, width=22)
        self._pna.finish(legend=legend)

        if filename != 'none':
            save_plot(filename)


class PosNegCompare(object):
    def __init__(self, *args, size=4, aspect=0.4, bar_width=0.28, filename=None,
                 num_format='%3.2g', legend=False, **kwargs):
        """
        A slightly different version, where different results are assumed to have different quantities and each
        is drawn on its own axes, but the spans of all axes are set to match the maximal pos/neg ratio (so the
        horiz axes should align)
        :param args: a sequence of LciaResult objects
        :param size: nominal plot height in inches
        :param aspect:  nominal aspect ratio of each pos/neg axis
        :param bar_width: nominal bar width
        :param filename: to save. default 'pos_neg_compare.eps'. To suppress save, pass 'none' (literal string) as filename
        :param num_format: default %3.2g
        :param csv_file: [None] if non-None, write a summary table to a csv file
        :param kwargs: autorange, fontsize
        :param legend:
        """
        self._pos = []
        self._neg = []
        _ratios = []

        for i, arg in enumerate(args):
            _pos = 0.0
            _neg = 0.0
            for c in arg.keys():
                val = arg[c].cumulative_result
                if val > 0:
                    _pos += val
                else:
                    _neg += val

            self._pos.append(_pos)
            self._neg.append(_neg)

            if _pos + _neg < 0:
                _ratios.append( -1 * (_pos + _neg) / _pos)
            else:
                _ratios.append(0)

        print(_ratios)
        max_ratio = max(_ratios)

        n = len(args)
        cross = size * aspect * n * 1.4

        fig = plt.figure(figsize=[cross, size])

        self._pna = []

        for i, arg in enumerate(args):
            ax = fig.add_axes([i/n, 0, 0.8/n, 1.0])
            qty = arg.quantity

            span = (-1 * max_ratio * self._pos[i], self._pos[i])
            print(span)

            self._pna.append(_PosNegAxes(ax, size, qty, span, bar_width=bar_width, **kwargs))
            self._pna[i].draw_pos_neg(1, self._pos[i], self._neg[i], num_format=num_format)

            self._pna[i].finish(legend=legend)
            ax.set_xticks([])
            ax.set_yticks([])

        if filename is None:
            filename = 'pos_neg_compare.eps'
        if filename != 'none':
            save_plot(filename)

    @property
    def dataframe(self):
        df = DataFrame((self._table_entry(k) for k in range(len(self._pna))),
                       index=[k.name for k in self._pna])
        mc = MultiIndex.from_tuples(((' ', 'Unit'), ('Total Incurred', 'Impacts'), ('Total Avoided', 'Impacts'),
                                     (' ', 'Net Total')))
        df.columns = mc
        return df

    def _table_entry(self, index):
        """

        :param index:
        :return:
        """
        p = self._pos[index]
        n = self._neg[index]
        return {'Unit': self._pna[index].unit,
                'Total Incurred Impact': '%3.2g' % p,
                'Total Avoided Impact': '%3.2g' % n,
                'Net Total': '%3.2g' % (p+n)}


class PosNegCompareError(object):
    def __init__(self, *args, size=4, aspect=0.4, bar_width=0.28, filename=None,
                 num_format='%3.2g', legend=False, **kwargs):
        """
        Adds errorbars to above.  This should drop-in replace PosNegCompare because it is a proper superset of
        functionality with a workalike interface.

        :param args: a sequence of *3-tuples* of LciaResult objects containing main result and sensitivity results
        :param size: nominal plot height in inches
        :param aspect:  nominal aspect ratio of each pos/neg axis
        :param bar_width: nominal bar width
        :param filename: to save. default 'pos_neg_compare.eps'. To suppress save, pass 'none' (literal string) as filename
        :param num_format: default %3.2g
        :param csv_file: [None] if non-None, write a summary table to a csv file
        :param kwargs: autorange, fontsize
        :param legend:
        """
        self._pos = []
        self._neg = []

        self._pos_err = []
        self._neg_err = []

        _ratios = []
        _overdraw = []

        def _get_pos_neg(_arg):
            _pos = 0.0
            _neg = 0.0
            for c in _arg.keys():
                val = _arg[c].cumulative_result
                if val > 0:
                    _pos += val
                else:
                    _neg += val
            return _pos, _neg

        for i, arg in enumerate(args):
            if isinstance(arg, tuple):
                _pos, _neg = _get_pos_neg(arg[0])
                _pos1, _neg1 = _get_pos_neg(arg[1])
                _pos2, _neg2 = _get_pos_neg(arg[2])

                _pos_err_min = max([_pos - _pos1, _pos - _pos2])
                _pos_err_max = max([_pos1 - _pos, _pos2 - _pos])

                _neg_err_min = max([_neg - _neg1, _neg - _neg2])
                _neg_err_max = max([_neg1 - _neg, _neg2 - _neg])

                _neg_est = min([_neg, _neg1, _neg2])
                _pos_est = max([_pos, _pos1, _pos2])

                self._pos_err.append((_pos_err_min, _pos_err_max))
                self._neg_err.append((_neg_err_min, _neg_err_max))

                self._pos.append(_pos)
                self._neg.append(_neg)

            else:
                res = arg

                _pos, _neg = _get_pos_neg(res)

                self._pos.append(_pos)
                self._neg.append(_neg)

                self._pos_err.append((0,0))
                self._neg_err.append((0,0))

                _pos_est = _pos
                _neg_est = _neg

            if _pos + _neg_est < 0:
                _ratios.append(-1 * (_pos + _neg_est) / _pos)
            else:
                _ratios.append(0)

            if _pos_est > _pos:
                _overdraw.append(_pos_est / _pos)

        print(_ratios)
        print(_overdraw)
        max_ratio = max(_ratios)
        max_over = max(_overdraw)

        n = len(args)
        cross = size * aspect * n * 1.4

        fig = plt.figure(figsize=[cross, size])

        self._pna = []

        for i, arg in enumerate(args):
            if isinstance(arg, tuple):
                qty = arg[0].quantity
            else:
                qty = arg.quantity
            ax = fig.add_axes([i/n, 0, 0.8/n, 1.0])


            span = (-1 * max_ratio * self._pos[i], max_over * self._pos[i])
            print(span)

            self._pna.append(_PosNegAxes(ax, size, qty, span, bar_width=bar_width, **kwargs))
            self._pna[i].draw_pos_neg(1, self._pos[i], self._neg[i], num_format=num_format)

            if any(self._pos_err[i] + self._neg_err[i]):
                self._pna[i].draw_error_bars(1, self._pos[i], self._pos_err[i], self._neg[i], self._neg_err[i])

            self._pna[i].finish(legend=legend)
            ax.set_xticks([])
            ax.set_yticks([])

        if filename is None:
            filename = 'pos_neg_compare.eps'
        if filename != 'none':
            save_plot(filename)
