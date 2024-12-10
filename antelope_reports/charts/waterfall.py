"""
OK revisiting this chart for the first time in N years-- it is actually quite nice, but two things:
 1- stacking different scenarios sharing the same quantity with vertically-aligned ordinate axes is not really workable
    because the chart becomes too long.  But it is a clever idea and maybe it should be supported, just not
    without a proper faceted chart design. i.e. this needs a long table, seaborn-style
 2- in fact, what would work is having charts with different quantities with horizontally aligned abcissae would be
    great for contribution analysis
 3- the charts need to show uncertainty/variability per stage- this is absolutely a make-or-break feature

Proposed function signature:

 WaterfallChart(*results, stages=None, ...) without uncertainty
 WaterfallChart(*(res, res_hi, res_lo), stages=None, ...) with uncertainty

The outer layer needs to create a figure, then iterate through the axes
- then a waterfall drawing class that just takes the data and draws it
- stage labeling happens outside

For now: strip out everything related to vertical stacking.

Class for making waterfall charts. There is an inheritance structure to be found in these charts somewhere..


"""

import matplotlib as mpl
import matplotlib.pyplot as plt
import colorsys
from itertools import accumulate
from collections import defaultdict
from math import ceil

# from math import floor

from .base import save_plot, net_color

net_style = {
    'edgecolor': 'none'
}

# mpl.rcParams['patch.force_edgecolor'] = False
mpl.rcParams['errorbar.capsize'] = 3
mpl.rcParams['grid.color'] = 'k'
mpl.rcParams['grid.linestyle'] = ':'
mpl.rcParams['grid.linewidth'] = 0.5
# mpl.rcParams['lines.linewidth'] = 1.0
mpl.rcParams['axes.autolimit_mode'] = 'round_numbers'
mpl.rcParams['axes.xmargin'] = 0
mpl.rcParams['axes.ymargin'] = 0


def _fade_color(color):
    hsv = colorsys.rgb_to_hsv(*color)
    new_hue = (hsv[0] + 0.086) % 1

    return colorsys.hsv_to_rgb(new_hue, hsv[1]*0.65, hsv[2]*0.8)


def random_color(seed, sat=0.65, val=0.95, offset=14669):

    # hue = ((int('%.4s' % uuid, 16) + offset) % 65536) / 65536
    hue = (hash((seed, offset)) % 65536)/65536
    return colorsys.hsv_to_rgb(hue, sat, val)


def grab_stages(*results, sort=None, count=None):
    stages = set()

    def _first_score(_comp):
        for r in results:
            try:
                return r[_comp].cumulative_result
            except KeyError:
                continue
        return 0
    for i in results:
        stages = stages.union(i.keys())
    if sort is None:
        out = sorted(stages, key=_first_score, reverse=True)
    else:
        out = sorted(stages, key=sort)
    if count is None:
        return out
    return out[:count]


def grab_names(*results, field=None, default='Other'):
    d = dict()
    for r in results:
        for k in r.keys():
            if k in d:
                continue
            c = r[k]
            if field:
                n = c.entity.get(field, default)
            else:
                n = c.name
            d[k] = n
    return d


def _data_range(data_array):
    """

    :param data_array:
    :return:
    """
    mx = 0.0
    mn = 0.0
    for i, data in enumerate(data_array):
        for k in accumulate(sorted(data, reverse=True)):
            if k > mx:
                mx = k
            if k < mn:
                mn = k
    return mn, mx


def _res_range(ress):
    """
    accepts a list of results; returns the largest and smallest data values encountered, assuming the segments are
    presented in descending order
    :param ress:
    :return:
    """
    mx = 0.0
    mn = 0.0
    for i, res in enumerate(ress):
        lo = res.total()
        hi = max(res.range())
        if lo < mn:
            mn = lo
        if hi > mx:
            mx = hi
    return mn, mx


class WaterfallChart(object):
    """
    A WaterfallChart turns a collection of LciaResult objects into a collection of waterfall graphs that share an
    ordinal axis. <- this is true, just more correctly interpreted as "aligned abcissas, common ordinate"
    """
    _draw_ylabel = (0,)

    def _stage_style(self, stage):
        if self._names:
            stage = self._names.get(stage, stage)
        if stage in self._color_dict:
            this_style = {'color': self._color_dict[stage]}
        else:
            color = self._color or self._q.get('color') or random_color(self._q.uuid)
            this_style = {'color': color}
        if stage in self._style_dict:
            this_style.update(self._style_dict[stage])
        else:
            if self._style is not None:
                this_style.update(self._style)
        return this_style

    def _create_figure_and_axes(self, size, aspect, case_sep, n_cols):
        """
        Computes the figure size based on the content and creates the axes
        :param size: width of figure in inches
        :param aspect: ratio of bar height to axes width
        :param case_sep: vertical gap between cases in multiples of bar height
        :param n_cols: Number of columns. if None, follow default behavior (one row, unless aspect > 3:1, in which case
        act as though n_cols = 4)
        :return:
        """
        stage_count = sum(len(k) for k in self._stages_by_case.values())
        stage_count += sum(int(k) for k in self._include_net.values())

        # decision point: are we doing a standard cases x quantities single row, or a quantities grid?
        # decide based on the aspect of the final chart.
        # old: height = num_ax * (self._size * aspect * num_steps) + (num_ax - 1) * panel_sep
        wid = 1 / len(self._qs)
        height = (size * wid) * aspect * (stage_count + case_sep * len(self._cases) * int(len(self._cases) > 1))

        # a mess: re-arrange the grid if aspect is too large or if user requests it
        if n_cols or ((size / height) > 3 and len(self._qs) > 4):
            # overrule! do a Kx4 grid of axes
            try:
                n_cols = int(n_cols)
            except TypeError:
                n_cols = 4

            n_cols = min([n_cols, len(self._qs)])

            wid = 1 / n_cols
            n_rows = ceil(len(self._qs) / n_cols)
            row_height = (size * wid) * aspect * (stage_count + case_sep * len(self._cases) * int(len(self._cases) > 1))
            height = row_height * n_rows + self._row_sep * (n_rows - 1)
            ht = 1 / n_rows

            print('Creating %dx%d Layout' % (n_rows, n_cols))
            self._draw_ylabel = tuple(i for i in range(len(self._qs)) if i % n_cols == 0)

            def _ax_pos(_i):
                _lt = wid * (_i % n_cols)
                _bt = ht * (n_rows - 1 - (_i // n_cols))
                return [_lt, _bt, (wid - self._col_sep / size), (ht - self._row_sep / size)]

        else:
            # normal- do case x quantity
            print('Creating 1x%d Layout' % (len(self._qs)))

            def _ax_pos(_i):
                return [wid * _i, 0, (wid - self._col_sep / size), 1]

        self._size = size * wid
        print('Creating figure with size %.2f x %.2f' % (size, height))
        self._fig = plt.figure(figsize=[size, height])

        for i in range(len(self._qs)):

            # ax_pos = [wid * i, 0, (wid - self._col_sep / size), 1]

            ax = self._fig.add_axes(_ax_pos(i))

            ax.invert_yaxis()
            ax.spines['top'].set_visible(False)
            ax.spines['bottom'].set_visible(True)
            ax.spines['bottom'].set_linewidth(2)
            ax.spines['left'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.tick_params(labelsize=10)
            ax.tick_params(axis='y', length=0)

            self._ax[self._qs[i]] = ax

    def __init__(self, *results, stages=None, count=None, color=None, color_dict=None,
                 style=None, style_dict=None, stage_property=None, stage_default='Other',
                 include_net=True, net_name='remainder', data_free=False,
                 filename=None, size=6, autorange=False, font_size=None,
                 aspect=0.1, case_sep=None, row_sep=None, col_sep=0.25, n_cols=None, **kwargs):
        """
        Create a waterfall chart that compares the stage contributions of separate LciaResult objects.

        The positional parameters must all be LciaResult objects.  The results should all share the same quantity.

        iterable 'stages' specifies the sequence of queries to the results and the corresponding sequence of waterfall
        steps.  The stage entries are used as an argument to contrib_query. If none is specified, then a collection is
        made of all components of all supplied results.  The collection will have random order.

        The color specification is used for all stages.  Exceptions are stored in color_dict, where the same key
        used for the contrib query, if present, is used to retrieve a custom color for the stage.

        If no default color is specified, a random hue is picked based on the UUID of the quantity.

        Each bar is drawn in the same default color, unless
        :param results: positional parameters must all be LciaResult objects having the same quantity
        :param stages: an ordering of stages. use grab_stages(*results) to get a complete list, then permute it.
        (default ordering is by score of the first quantity, decreasing)
        :param count: [None] limit to the first <count> stages

        :param color: color to use for all bars
        :param color_dict: dictionary of stage name to color for specific stages

        :param style: default style spec for each bar (to override pyplot bar/barh default
        :param style_dict: dict of dicts for custom styles

        :param stage_property: if stages is not specified explicitly, property to grab for stage naming (default
         is to grab entity.name)
        :param stage_default: ['Other'] if stage_property is specified, label to use if the property is missing

        :param include_net: [True] whether to include a net-result bar, if a discrepancy exists between the stage query
         and the total result. This is ignored- a discrepancy is always reported
        :param net_name: ['remainder'] what to call the net-result bar

        :param data_free: [False] whether to suppress printing numeric values

        :param n_cols: number of columns in which to arrange the plots. Defaults to one row, except if n > 4 and the
        resulting figure has an aspect ratio of greater than 3:1, in which case uses a kx4 grid.

        :param filename: default 'waterfall_%.3s.eps' % uuid.  Enter 'none' to return (and not save) the chart
        :param size: axes size in inches (default 6") (width for horiz bars; height for vert bars)
        :param autorange: [False] whether to auto-range the results (no longer supported)
        :param font_size: [None] set text [numbers smaller]
        :param kwargs: aspect: bar height per fig width [0.1]
        case_sep [2.1 bar widths, or 1.2 bar widths if data-free (no cumulative indicator)],
        col_sep=0.25in,
        num_format [%3.2g],
        bar_width [0.85]
        font_size [None]
        row_sep [None]
        """

        self._qs = []
        self._cases = []
        self._res_by_case = defaultdict(list)
        self._res_by_q = defaultdict(list)
        self.data_free = bool(data_free)
        if case_sep is None:
            if self.data_free:
                case_sep = 1.2
            else:
                case_sep = 2.1

        # sort/group results by case and by quantity
        for res in results:
            if res.quantity not in self._qs:
                self._qs.append(res.quantity)
            if res.scenario not in self._cases:
                self._cases.append(res.scenario)
            self._res_by_case[res.scenario].append(res)
            self._res_by_q[res.quantity].append(res)

        # support limited, idiosyncratic customization of styles and colors
        self._color = color  # or self._q.get('color') or random_color(self._q.uuid)
        self._color_dict = color_dict or dict()
        self._style = style or None
        self._style_dict = style_dict or dict()
        self._font_size = font_size
        fontsize = self._font_size or 12

        # group stages by case
        labels = []
        if stages is None:
            stages = {case: grab_stages(*ress, count=count) for case, ress in self._res_by_case.items()}
            self._names = grab_names(*results, field=stage_property, default=stage_default)

        else:
            # I have no idea what's going on here
            stages = {case: list(filter(lambda x: x in grab_stages(*ress, count=count), stages))
                      for case, ress in self._res_by_case.items()}
            self._names = None

        self._stages_by_case = stages

        # prepare net-balance bar (included any time the stage query does not equal the result total
        self._include_net = dict()
        self._net_name = net_name

        # extract data from LciaResult objects-- and compute net-balance
        for case in self._cases:
            if self._names:
                labels += [self._names[k] for k in self._stages_by_case[case]]
            else:
                labels += self._stages_by_case[case]

            net_flag = False
            for res in self._res_by_case[case]:
                data, net = res.contrib_new(*self._stages_by_case[case], autorange=autorange)
                _range = _data_range([data])
                if abs(net) * 1e8 > (_range[1] - _range[0]):
                    # only include remainder if it is greater than 10 ppb
                    net_flag = True
                    labels.append(self._net_name)
                    break

            nf = net_flag and include_net
            self._include_net[case] = nf

        self._row_sep = row_sep or (size / 10)  # real gap in inches between rows
        self._col_sep = col_sep  # real gap in inches between panels
        self._size = 0.0  # real axes width in inches, set in _create_figure()
        self._q = None
        self._ax = dict()
        self._fig = None
        self._span = (0, 0)  # for current axes only

        self._create_figure_and_axes(size, aspect, case_sep, n_cols)

        for i, q in enumerate(self._qs):
            self._q = q
            self._unit = q.unit
            self._span = [k * 1.05 for k in _res_range([k for k in self._res_by_q[q]])]

            ax = self._ax[q]
            ax.set_xlim(self._span)

            start = 0
            yticks = []

            case_res = dict()
            for res in self._res_by_q[q]:
                if res.scenario in case_res:
                    # the proper approach to this is to use multiple entries to draw sensitivity bars
                    raise KeyError('Multiple results for case %s, quantity %s' % (res.scenario, q))
                case_res[res.scenario] = res

            for case in self._cases:
                # write scenario name on the left if there are multiple scenarios
                if i in self._draw_ylabel:
                    if case and case != 'None':  # len(self._cases) > 1:
                        ax.text(0, start - 0.5, '%s ' % case, ha='right', fontsize=fontsize, fontweight='bold')
                start, yt = self._waterfall_case_horiz(ax, case_res[case], start, **kwargs)
                yticks.extend(yt)

                if case != self._cases[-1]:
                    start += case_sep
                else:
                    if self.data_free is False:
                        start += 1.2
                # if len(self._cases) > 1:
                # add scenario name text

            # ## not sure why we are doing this
            # yticks.append(yticks[-1] + case_sep)
            # stgs.append('')

            if 0:  # len(self._cases) == 1:
                # scenario name in title
                sc_name = self._cases[0] or ''
                ax.set_title('%s\n%s' % (self._q['Name'], sc_name), fontsize=fontsize)
            else:
                # scenario name handled above
                ax.set_title('%s\n%s' % (self._q['Name'], self._q.unit), fontsize=fontsize)

                # ## not sure why we are doing this
                # yticks.append(yticks[-1] + case_sep)
                # stgs.append('')

            if i in self._draw_ylabel:
                ax.set_yticks(yticks)
                ax.set_yticklabels(labels)
                ax.set_ylim([start, -1])
            else:
                ax.set_yticks([])
                ax.set_ylim(self._ax[self._qs[0]].get_ylim())

            # vertical axis
            ax.plot([0, 0], ax.get_ylim(), linewidth=2, color=(0, 0, 0), zorder=-1)

            # x labels
            '''
            if abs(cum) > self.int_threshold and abs(mx) > self.int_threshold:
                xticks = [0]
                xticklabels = ['0']
            else:
                xticks = []
                xticklabels = []

            if abs(mx - cum) > self.int_threshold:
                xticks.extend([cum, mx])
                xticklabels.extend([num_format % cum, num_format % mx])
            else:
                xticks.append(cum)
                xticklabels.append(num_format % cum)
                
            '''

            '''
            # add an indicator unit notation to the rightmost tick label
            xticklabels = [_i.get_text() for _i in ax.get_xticklabels()]
            xticks = ax.get_xticks()
            bgst = next(_i for _i in range(len(xticks)) if xticks[_i] == max(xticks))
            xticklabels[bgst] += ' %s' % self._unit
            ax.set_xticks(xticks)
            ax.set_xticklabels(xticklabels)
            # ax.set_xticklabels(xticklabels)
            '''
            ax.set_xlabel(self._q.unit)
            ax.ticklabel_format(axis='x', scilimits=(-3, 3))

            if self.data_free:
                ax.set_xticks([])

            # font size
            if self._font_size:
                for item in ([ax.title, ax.xaxis.label, ax.yaxis.label] + ax.get_xticklabels() + ax.get_yticklabels()):
                    item.set_fontsize(self._font_size)
                t = ax.xaxis.get_offset_text()
                t.set_size(self._font_size)

        if filename != 'none':
            if filename is None:
                uus = '_'.join('%.3s' % q.uuid for q in self._qs)
                filename = 'waterfall-%s.eps' % uus

            save_plot(filename)

    def _waterfall_case_horiz(self, ax, res, start, num_format='%3.2g', bar_width=0.85):
        """

        :param ax:
        :param res:
        :param start:
        :param num_format:
        :param bar_width:
        :return:
        """
        print('Case: %s Quantity: %s ' % (res.scenario, res.quantity))
        _low_gap = 0.25  # this is how much space we want between the bottom bar and the axis?

        fontsize = self._font_size or 12

        cum = 0.0
        center = start + 0.5 - _low_gap
        # top = center - 0.6 * bar_width

        yticks = []

        data, net = res.contrib_new(*self._stages_by_case[res.scenario])  # autorange omitted
        for i, dat in enumerate(data):
            yticks.append(center)

            style = self._stage_style(self._stages_by_case[res.scenario][i])

            if self.data_free:
                self._draw_one_bar_without_label(ax, style, center, cum, dat, bar_width)
            else:
                self._draw_one_bar_with_label(ax, style, center, cum, dat, bar_width, num_format)

            cum += dat
            center += 1

        if self._include_net[res.scenario]:
            yticks.append(center)
            style = {'color': net_color}
            if self.data_free:
                self._draw_one_bar_without_label(ax, style, center, cum, net, bar_width)
            else:
                self._draw_one_bar_with_label(ax, style, center, cum, net, bar_width, num_format)

            cum += net
            center += 1

        if self.data_free:
            # return now
            return center, yticks

        # cumsum marker
        if self._font_size:
            markersize = self._font_size - 2
        else:
            markersize = 8
        ax.plot([cum, cum], [center - 1 + 0.5*bar_width, center], color=(0.3, 0.3, 0.3), zorder=-1, linewidth=0.5)
        ax.plot(cum, center - 0.4 * _low_gap, marker='v', markerfacecolor=(1, 0, 0), markeredgecolor='none',
                markersize=markersize)
        '''
        Cumulative label: we want this to appear below the arrow, but we also want to correct if it is too
        close to the vertical axis or to the edge of the axes.
        
        Multi-case as with the segment labels; unfortunately they are different cases.
        
        First: if the cum is within the threshold of the positive span, then right-align it at the positive span
        Second: if the cum is within the threshold of the negative span, then left-align it at the negative span
        Third: if the cum is within the threshold of 0 on the positive side, then left-align it at 0
        Fourth: if the cum is within the threshold of 0 on the negative side, then right-align it at 0
        Fifth: print it centered under the carat
        
        '''
        tot_thresh = self.int_threshold  # * fontsize / 10
        if cum > self._span[1] - tot_thresh:
            x = self._span[1]
            ha = 'right'
            # cs = 'AAA'
        elif abs(cum) < tot_thresh:
            x = tot_thresh * 0.25
            if cum < 0:
                x *= -1
                ha = 'right'
                # cs = 'CCC'
            else:
                ha = 'left'
                # cs = 'DDD'
        elif cum < self._span[0] + tot_thresh:
            x = self._span[0]
            ha = 'left'
            # cs = 'BBB'
        else:
            # cs = 'EEE'
            x = cum
            ha = 'center'

        total_format = num_format or '%.3g'
        ax.text(x, center + _low_gap, total_format % cum, ha=ha, va='top', fontsize=fontsize)

        return center, yticks

    @staticmethod
    def _draw_one_bar_without_label(ax, style, center, cum, dat, bar_width):
        _conn_color = (0.3, 0.3, 0.3)
        color = style['color']

        if dat < 0:
            style['color'] = _fade_color(color)

        ax.barh(center, dat, left=cum, height=bar_width, **style)

        # connector
        if cum != 0:
            ax.plot([cum, cum], [center - 0.5 * bar_width, center - 1 + 0.5 * bar_width],
                    color=_conn_color, zorder=-1, linewidth=0.5)

    def _draw_one_bar_with_label(self, ax, style, center, cum, dat, bar_width, num_format):
        _h_gap = self.int_threshold * 0.11
        _conn_color = (0.3, 0.3, 0.3)

        label_args = {}
        if self._font_size:
            label_args['fontsize'] = self._font_size * 0.8

        color = style['color']

        if dat < 0:
            style['color'] = _fade_color(color)

        ax.barh(center, dat, left=cum, height=bar_width, **style)
        if num_format:
            if self.int_threshold is not None and abs(dat) > self.int_threshold:
                if sum(style['color'][:2]) < 0.6:
                    text_color = (1, 1, 1)
                else:
                    text_color = (0, 0, 0)

                # interior label
                x = cum + (dat / 2)
                ax.text(x, center, num_format % dat, ha='center', va='center', color=text_color, **label_args)
            else:
                '''# end label positioning-- this is complicated!
                IF the bar is positive and the result is not too far to the right, we want the label on the right
                IF the bar is too far to the right, we want the label on the left regardless of direction
                IF the bar is too far to the left, we want the label on the right regardless of direction
                BUT if the bar is close to 0, we want it printed on the far side from the y axis, to not overwrite
                We know if we're here, the bar is short.  so we only need to think about one end.
                '''
                if cum + dat > self._span[1] - self.int_threshold:
                    # must do left: too close to right
                    if 0 < cum < self.int_threshold:
                        anchor = 'zero left'
                    else:
                        anchor = 'left'
                elif cum + dat < self._span[0] + self.int_threshold:
                    # too close to left
                    if cum < 0 and abs(cum) < self.int_threshold:
                        anchor = 'zero right'
                    else:
                        anchor = 'right'
                elif abs(cum) < self.int_threshold:
                    if cum >= 0:
                        anchor = 'right'
                    else:
                        anchor = 'left'
                else:
                    # not in a danger zone
                    if dat >= 0:
                        anchor = 'right'
                    else:
                        anchor = 'left'

                if anchor == 'left':
                    x = min([cum, cum + dat]) - _h_gap
                    ha = 'right'
                elif anchor == 'zero left':
                    x = -_h_gap
                    ha = 'right'
                elif anchor == 'zero right':
                    x = _h_gap
                    ha = 'left'
                else:
                    x = max([cum, cum + dat]) + _h_gap
                    ha = 'left'

                ax.text(x, center, num_format % dat, ha=ha, va='center', **label_args)

        # connector
        if cum != 0:
            ax.plot([cum, cum], [center - 0.5 * bar_width, center - 1 + 0.5 * bar_width],
                    color=_conn_color, zorder=-1, linewidth=0.5)

    @property
    def fig(self):
        return self._fig

    @property
    def int_threshold(self):
        """
        Useful only for horiz charts
        :return: about 0.5" in axis units (ie. 2x size), scaled up by fontsize / 10pt
        """
        fontsize = self._font_size or 10
        return (self._span[1] - self._span[0]) / (self._size * 2 * 10 / fontsize)

    '''
    def _waterfall_staging_vert(self, scenarios, stages, styles, aspect=0.1, panel_sep=0.75, **kwargs):
        """
        For the vertical-bar waterfall charts, we make just one axes and position the waterfalls at different x
        positions. We may try to do the same thing for horiz waterfallos if we like it better.  This is nice because
        it automatically adjusts for results with

        :param scenarios:
        :param stages:
        :param styles:
        :param aspect:
        :param panel_sep:
        :param kwargs:
        :return:
        """
        num_ax = len(self._d)
        num_steps = len(stages)
        width = num_ax * (self._size * aspect * num_steps) + (num_ax - 1) * panel_sep

        _ax_wid = self._size * aspect * num_steps / width
        _gap_wid = panel_sep / width

        fig = plt.figure(figsize=[width, self._size])
        left = 0.0

        _mn = _mx = 0.0
        axes = []
        for i in range(num_ax):
            right = left + _ax_wid
            ax = fig.add_axes([left, 0.0, _ax_wid, 1.0])
            axes.append(ax)
            self._waterfall_vert(ax, self._d[i], styles, **kwargs)
            ax.set_xticklabels(stages)
            xticklabels = [_i.get_text() for _i in ax.get_xticklabels()]
            xticklabels[-1] += ' %s' % self._q.unit()
            ax.set_xticklabels(xticklabels)

            xlim = ax.get_xlim()
            if xlim[0] < _mn:
                _mn = xlim[0]
            if xlim[1] > _mx:
                _mx = xlim[1]

            if scenarios[i] is not None or num_ax > 1:
                ax.set_title(scenarios[i], fontsize=12)

            top = bottom - _gap_hgt

        for ax in axes:
            ax.set_xlim([_mn, _mx])
    '''

    '''
    def _waterfall_staging_horiz(self, scenarios, stages, styles,
                                 aspect=0.1, panel_sep=0.65,
                                 **kwargs):
        """
        Creates a figure and axes and populates them with waterfalls.
        :param scenarios:
        :param stages:
        :param styles:
        :param aspect:
        :param panel_sep:
        :param kwargs: num_format=%3.2g, bar_width=0.85
        :return:
        """
        num_ax = len(self._d)
        num_steps = sum(sum([k != 0 for k in j]) for j in self._d)  # len(stages)
        height = num_ax * (self._size * aspect * num_steps) + (num_ax - 1) * panel_sep

        _gap_hgt = panel_sep / height

        fig = plt.figure(figsize=[self._size, height])
        top = 1.0

        _mn = _mx = 0.0
        axes = []
        for i in range(num_ax):

            data = [k for k in self._d[i] if k != 0]
            stgs = [stages[j] for j, k in enumerate(self._d[i]) if k != 0]

            _ax_hgt = self._size * aspect * len(data) / height
            bottom = top - _ax_hgt
            ax = fig.add_axes([0.0, bottom, 1.0, _ax_hgt])
            axes.append(ax)
            self._waterfall_horiz(ax, data, styles, **kwargs)
            ax.set_yticklabels(stgs)


            # add an indicator unit notation to the rightmost tick label
            xticklabels = [_i.get_text() for _i in ax.get_xticklabels()]
            xticks = ax.get_xticks()
            bgst = next(_i for _i in range(len(xticks)) if xticks[_i] == max(xticks))
            xticklabels[bgst] += ' %s' % self._unit
            ax.set_xticklabels(xticklabels)


            xlim = ax.get_xlim()
            if xlim[0] < _mn:
                _mn = xlim[0]
            if xlim[1] > _mx:
                _mx = xlim[1]

            if scenarios[i] is not None or num_ax > 1:
                sc_name = scenarios[i]
            else:
                sc_name = ''

            fontsize = self._font_size or 12

            if i == 0:
                ax.set_title('%s [%s]\n%s' % (self._q['Name'], self._unit, sc_name), fontsize=fontsize)
            else:
                ax.set_title('%s' % sc_name, fontsize=fontsize)

            top = bottom - _gap_hgt

        for ax in axes:
            ax.set_xlim([_mn, _mx])
            # ax.set_xticks(ax.get_xticks() + [_mx])
            # ax.set_xticklabels(ax.get_xticklabels() + [str(self._unit)])
        return fig
    '''

    '''
    def _waterfall_horiz(self, ax, num_format='%3.2g', bar_width=0.85):
        """

        :param ax:
        :param data:
        :param styles: a list of style kwargs to add to each bar.  must include 'color' key; all others extra.
        :param num_format:
        :param bar_width:
        :return:
        """
        """
        The axes are already drawn. all we want to do is make and label the bars, one at a time.
        """
        _low_gap = 0.25

        _conn_color = (0.3, 0.3, 0.3)

        cum = 0.0
        center = 0.5 - _low_gap
        top = center - 0.6 * bar_width
        bottom = floor(center + len(data))

        # vertical axis
        ax.plot([0, 0], [top, bottom], linewidth=2, color=(0, 0, 0), zorder=-1)

        _h_gap = self.int_threshold * 0.11
        yticks = []

        mx = 0.0

        label_args = {}
        if self._font_size:
            label_args['fontsize'] = self._font_size - 2

        for i, dat in enumerate(data):
            yticks.append(center)
            style = styles[i]
            self._draw_one_bar_with_label(ax, style, center, cum, dat, bar_width, num_format)
            
            cum += dat
            if cum > mx:
                mx = cum

            center += 1
        ax.invert_yaxis()
        ax.spines['top'].set_visible(False)
        ax.spines['bottom'].set_visible(True)
        ax.spines['bottom'].set_linewidth(2)
        ax.spines['left'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_yticks(yticks)
        ax.tick_params(labelsize=10)
        ax.tick_params(axis='y', length=0)

        # cumsum marker
        if self._font_size:
            markersize = self._font_size - 2
        else:
            markersize = 8
        ax.plot([cum, cum], [center - 1 + 0.5*bar_width, bottom], color=_conn_color, zorder=-1, linewidth=0.5)
        ax.plot(cum, bottom - 0.4 * _low_gap, marker='v', markerfacecolor=(1, 0, 0), markeredgecolor='none',
                markersize=markersize)

        # x labels
        if abs(cum) > self.int_threshold and abs(mx) > self.int_threshold:
            xticks = [0]
            xticklabels = ['0']
        else:
            xticks = []
            xticklabels = []

        if abs(mx - cum) > self.int_threshold:
            xticks.extend([cum, mx])
            xticklabels.extend([num_format % cum, num_format % mx])
        else:
            xticks.append(cum)
            xticklabels.append(num_format % cum)

        ax.set_xticks(xticks)
        ax.set_xticklabels(xticklabels)

        ### font size
        if self._font_size:
            for item in ([ax.title, ax.xaxis.label, ax.yaxis.label] + ax.get_xticklabels() + ax.get_yticklabels()):
                item.set_fontsize(self._font_size)
    '''
