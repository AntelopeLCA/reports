from textwrap import wrap

import operator

from matplotlib import pyplot as plt

USE_TEX = False

if USE_TEX:
    """
    matplotlib documentation lists valid TeX fonts
    https://matplotlib.org/stable/tutorials/text/usetex.html
    serif (\rmfamily):
        Computer Modern Roman, 
        Palatino (mathpazo), 
        Times (mathptmx), 
        Bookman (bookman), 
        New Century Schoolbook (newcent), 
        Charter (charter)

    sans-serif (\sffamily)"
        Computer Modern Serif, 
        Helvetica (helvet), 
        Avant Garde (avant)

    cursive (\rmfamily):
        Zapf Chancery (chancery)

    monospace (\ttfamily):
        Computer Modern Typewriter, 
        Courier (courier)
    """
    plt.rcParams.update({
        "text.usetex": True,
        "font.family": "serif",
        "font.sans-serif": "Helvetica",
        "font.serif": "Palatino"
    })
    plt.rc('text.latex', preamble=r'\usepackage[cm]{sfmath}')
else:
    """
    Get a list of valid font families like this:
    >>> from matplotlib.font_manager import findSystemFonts
    >>> flist = findSystemFonts()
    >>> for fname in flist:
            try:
                fm = matplotlib.font_manager.FontProperties(fname=fname)
                print(fm.get_name())
            except RuntimeError:
                print('## %s' % fname)
    >>>
    """
    plt.rcParams.update({"text.usetex": False,
                         "font.family": "P052",
                         })


class KPIBase(object):
    """
    Generates and saves (and/or shows?) an infographic chart with a graph panel and annotations.

    For now, we want the graphic to be something like the following:

    +--------------------------------------------------------------------+
    |INDICATOR                          |                                |
    | units                             |                                |
    |-----------------------------------|              chart             |
    |  YEAR                NUMBER  unit |                                |
    |                                   |                                |
    |                                   |                                |
    +--------------------------------------------------------------------+


    """

    def _write_metric(self, record, amount, unit=None, fmt='%.1f', fontsize=None,
                      draw_symbol=None,
                      record_args=None,
                      amount_args=None):
        """
        Key operation-- pre-increments the row cursor and prints a statistical data point divided into
        record, amount, unit.
        :param record:
        :param amount:
        :param unit:
        :param fmt:
        :param fontsize:
        :param draw_symbol: [None] do nothing
          True: draw a legend for the current plot to the left of the record label
          'value': draw a legend for the current plot to the left of the amount
        :param record_args: dict of formatting kwargs to pass to record
        :param amount_args: dict of formatting kwargs to pass to amount+unit
        :return:
        """
        if record_args is None:
            record_args = dict()

        if amount_args is None:
            amount_args = dict()

        if fontsize is None:
            fontsize = self.fontsize

        self.content_row -= (fontsize * 1.15 / self.font_hgt)

        text_at = 0.015

        if draw_symbol:
            pps = {'linewidth': self.the_plot.get_linewidth(),
                   'linestyle': self.the_plot.get_linestyle(),
                   'color': self.the_plot.get_color(),
                   'marker': self.the_plot.get_marker(),
                   'markersize': self.the_plot.get_markersize(),
                   'markeredgecolor': self.the_plot.get_markeredgecolor(),
                   'markerfacecolor': self.the_plot.get_markerfacecolor()
                   }
            mid = self.content_row + (fontsize * 0.4 / self.font_hgt)
            ppy = (mid, mid)
            if draw_symbol == 'value':
                amt_s = fmt % amount
                amt_wid = len(amt_s) / 72  # hardcodes 16 chars per inch x 6 inch width bc I'm dumb
                ppx = (self.content_f[0] - amt_wid - 0.06, self.content_f[0] - amt_wid - 0.015)
                self.ax.plot(ppx, ppy, **pps)
            else:
                text_at += 0.06
                self.ax.plot((0.015, 0.06), ppy, **pps)

        t0 = self.ax.text(text_at, self.content_row, '%s' % record, fontsize=fontsize,
                          ha='left', va='baseline', **record_args)
        t1 = self.ax.text(self.content_f[0], self.content_row, fmt % amount,
                          ha='right', va='baseline', **amount_args)
        if not unit:
            unit = '%s' % self.unit
        if unit == '%':
            unit = self.pct()

        t2 = self.ax.text(self.content_f[1], self.content_row, unit,
                          ha='left', va='baseline', **amount_args)
        self.metrics.append((t0, t1, t2))

    def __init__(self, title, subtitle, unit, comment=None, figsize=(6.5, 1.8), graph_f=0.55, frame_lw=1.2, long=False,
                 graph_l_m_in=0.36, graph_b_m_in=0.35,
                 metrics=(0.85, 0.88),
                 title_in=0.5, comment_in=0.45, fontsize=12):

        self._xs = []
        self._ys = []
        self._the_plots = []

        self._series = -1
        self._this = -1
        self.unit = unit  # data unit

        self.fontsize = fontsize

        wid, hgt = figsize
        self.font_hgt = 72 * hgt  # figure height in font points

        self.graph_f = graph_f
        self.title_f = 1.0 - title_in / hgt
        self.frame_lw = frame_lw

        comment_f = comment_in / hgt

        self.title_pin = 1.0 - 0.67 * title_in / hgt  # vertical pin for title/subtitle break
        if long:
            self.numchars = int(16 * wid)  # approx width of content in number of characters (at 10 pt)
        else:
            self.numchars = int(16 * wid * graph_f)  # approx width of content in number of characters (at 10 pt)

        self.content_row = self.title_f - 0.035
        self.content_f = [graph_f * k for k in metrics]

        self.metrics = []

        self.f = f = plt.figure(figsize=figsize)

        # content axes
        self.ax = f.add_axes((0, 0, 1, 1))
        plt.axis('tight')

        # chart axes
        graph_l_m = graph_l_m_in / wid  # left hand margin for y labels (in)
        graph_b_m = graph_b_m_in / hgt  # lower margin for x labels (in)

        if long:
            graph_b = comment_f + graph_b_m
        else:
            graph_b = graph_b_m
        self.ax2 = f.add_axes((graph_f + graph_l_m, graph_b,
                               0.99 - graph_f - graph_l_m, 0.92 - graph_b))

        # title
        self.title = self.ax.text(0.015, self.title_pin + 0.015, title, fontsize=self.fontsize * 1.6,
                                  ha='left', va='bottom')
        self.subtitle = self.ax.text(0.015, self.title_pin, '%s (%s)' % (subtitle, self.unit), fontsize=self.fontsize,
                                     ha='left', va='top')

        self.comment = self.ax.text(0.015, comment_f - 0.035, 'comment', ha='left', va='top',
                                    fontsize=self.fontsize * 0.83,
                                    visible=False)
        if long:
            self._comment_frame = self.ax.plot((0, 1), (comment_f, comment_f), color='k',
                                               linewidth=self.frame_lw, visible=True)[0]
        else:
            self._comment_frame = self.ax.plot((0, self.graph_f), (comment_f, comment_f), color='k',
                                               linewidth=self.frame_lw * 0.7, visible=False)[0]

        self._format_ax(long, comment_f)
        self._format_ax2()
        self.set_comment(comment)  # None will pass

    @property
    def the_plot(self):
        return self._the_plots[self._series]

    @property
    def N(self):
        return len(self._xs)

    @property
    def n(self):
        return len(self.ys)

    @property
    def xs(self):
        return self._xs[self._series]

    @property
    def ys(self):
        return self._ys[self._series]

    @property
    def this_x(self):
        return self.xs[self._this]

    @property
    def this_y(self):
        return self.ys[self._this]

    def _format_ax(self, long, comment_f):
        self.ax.set_xlim([0, 1])
        self.ax.set_ylim([0, 1])
        self.ax.set_xticks(())
        self.ax.set_yticks(())

        # draw frames
        self.ax.plot((0, self.graph_f), (self.title_f, self.title_f), color='k', linewidth=self.frame_lw)
        if long:
            self.ax.plot((self.graph_f, self.graph_f), (comment_f, 1), color='k', linewidth=self.frame_lw)
        else:
            self.ax.plot((self.graph_f, self.graph_f), (0, 1), color='k', linewidth=self.frame_lw)

    def _format_ax2(self):
        self.ax2.spines['right'].set_visible(False)
        self.ax2.spines['left'].set_visible(False)
        self.ax2.spines['top'].set_visible(False)
        self.ax2.spines['bottom'].set_visible(False)
        self.ax2.set_clip_on(False)

        # what a terrible syntactic trick
        self.baseline, = self.ax2.plot((0, 1), (0, 0), linestyle='-', color='k', linewidth=0.7, visible=False)

        # def _draw_frame(self):

    def draw_plot(self, xs, ys, linestyle='-', marker='o', color=(0.5, 0.1, 0.1), this=-1,
                  hi_color=(0.1, 0.1, 0.5), hi_size=10, a_fmt='%.1f', g_gap=0.38, jog=12, fill=None,
                  **kwargs):
        """
        Add a dataset to the graphic. xs and ys will be set as the current data.  'this' indicates which value to
        hilight (default -1, set to None to disable hilight)
        :param xs:
        :param ys:
        :param linestyle:
        :param marker:
        :param color:
        :param this:
        :param hi_color:
        :param hi_size:
        :param a_fmt:
        :param g_gap:
        :param jog:
        :param fill: if True, fill the space between the line and (x axis, or prior dataset). If int, fill the space
         between the line and the indicated dataset
        :param kwargs:
        :return:
        """
        #####
        self._this = this
        self._xs.append(list(xs))
        self._ys.append(list(ys))
        # def draw_plot(self):

        if fill is not None:
            if fill is True:
                if self.N < 2:
                    yb = 0
                else:
                    yb = self._ys[-2]
            else:
                try:
                    fill = int(fill)
                    yb = self._ys[fill]
                except (TypeError, IndexError):
                    yb = 0
            self.ax2.fill_between(self.xs, self.ys, yb, color=color, alpha=0.3)

        # line plot with markers
        pl, = self.ax2.plot(self.xs, self.ys, linestyle=linestyle, marker=marker, color=color, clip_on=False, **kwargs)
        self._the_plots.append(pl)

        self.ax2.autoscale()  # rescale the axes to extents

        xlim = self.ax2.get_xlim()
        xlim = [xlim[0] - g_gap, xlim[1] + g_gap]
        self.ax2.set_xlim(xlim)
        self.baseline.set_xdata(xlim)
        self.baseline.set_visible(True)
        self.baseline.set_clip_on(False)

        ylim = self.ax2.get_ylim()
        if ylim[1] < 0:
            ylim = [ylim[0], 0]
        elif ylim[0] > 0:
            ylim = [0, ylim[1]]
        self.ax2.set_ylim(ylim)
        # self.ax2.set_yticklabels(ylim)

        if self._this is None:
            self._this = -1  # reset to last value
        else:
            # highlight 'this' value
            self.ax2.plot(self.this_x, self.this_y, linestyle='none', marker=marker, markerfacecolor='none',
                          markeredgecolor=hi_color, markersize=hi_size, clip_on=False)

            # annotate 'this' value
            # put below if value is too high
            if (ylim[1] - self.this_y) / (ylim[1] - ylim[0]) < 0.18:
                jog *= -1.3

            # omit unit, since it's printed in the frame
            self.ax2.annotate(a_fmt % self.this_y, xy=(self.this_x, self.this_y),
                              xytext=(0, jog), textcoords='offset points',
                              ha='center')

        # set ticklabel font sizes
        self.ax2.tick_params(axis='x', labelsize=self.fontsize * 0.83)
        self.ax2.tick_params(axis='y', labelsize=self.fontsize * 0.83)

    def set_comment(self, comment):
        if comment:
            self._comment_frame.set_visible(True)
            cw = '\n'.join(wrap(comment, self.numchars))
            self.comment.set_visible(True)
            self.comment.set_text(cw)

    def add_to_comment(self, add):
        if add:
            t = self.comment.get_text()
            self.comment.set_text(t + '\n' + add)

    def unset_comment(self):
        self._comment_frame.set_visible(False)
        self.comment.set_visible(False)

    def set_title(self, title, units):
        if title:
            self.title.set_text(title)
        if units:
            self.subtitle.set_text('%s (%s)' % (units, self.unit))

    def save(self, filename):
        plt.figure(self.f)
        plt.savefig(filename)

    @staticmethod
    def pct():
        if plt.rcParams['text.usetex']:
            return '\%'
        else:
            return '%'

    def report_value(self, ix=None, draw_label=None, **kwargs):
        """

        :param ix:
        :param draw_label: prepend text: [True] plot label, if specified, ['str']: the string
        :param kwargs:
        :return:
        """
        if ix:
            x = self.xs[ix]
            y = self.ys[ix]
        else:
            x = self.this_x
            y = self.this_y
        if draw_label:
            if draw_label is True:
                lbl = self.the_plot.get_label()
            else:
                lbl = str(draw_label)
            metric = '%s, %s' % (lbl, x)
        else:
            metric = 'Value for %s' % x
        self._write_metric(metric, y, **kwargs)

    def report_change(self, ix, pct=True, **kwargs):
        prior_x = self.xs[ix]
        prior_y = self.ys[ix]
        metric = "Change since %s" % prior_x

        if pct:
            ch = (self.this_y - prior_y) * 100 / prior_y
            self._write_metric(metric, ch, '%', fmt='%+.1f', **kwargs)
        else:
            ch = (self.this_y - prior_y) / prior_y
            self._write_metric(metric, ch, '', fmt='%+.3f', **kwargs)

    def report_total(self, metric=None, weight=None, **kwargs):
        if weight:
            if metric is None:
                metric = 'Weighted Sum'
            # python-native inner product
            y = sum(map(operator.mul, self.ys, weight))
        else:
            if metric is None:
                metric = 'Cumulative Amount'
            y = sum(self.ys)
        self._write_metric(metric, y, **kwargs)

    def report_average(self, metric=None, weight=None, **kwargs):
        if weight:
            if metric is None:
                metric = 'Weighted Average'
            # python-native inner product
            y = sum(map(operator.mul, self.ys, weight)) / sum(weight)
        else:
            if metric is None:
                metric = 'Simple Average'
            y = sum(self.ys) / len(self.ys)
        self._write_metric(metric, y, **kwargs)

    def report_literal(self, metric, amount, unit, **kwargs):
        """
        Report value not derived from current data
        :param metric:
        :param amount:
        :param unit:
        :param kwargs:
        :return:
        """
        self._write_metric(metric, amount, unit=unit, **kwargs)

    def content(self, **kwargs):
        pass

    def run(self, title=None, subtitle=None, comment=None, filename=None, **kwargs):
        self.set_title(title, subtitle)
        self.set_comment(comment)
        self.content(**kwargs)
        if filename:
            self.save(filename)


class ExtensiveKpi(KPIBase):
    def content(self, weight=None, **kwargs):
        self.report_value()
        for k in [-2, 0]:
            self.report_change(k)
        self.report_total(weight=weight)


class IntensiveKpi(KPIBase):
    def content(self, weight=None, **kwargs):
        self.report_value()
        for k in [-2, 0]:
            self.report_change(k)
        self.report_average(weight=weight)
