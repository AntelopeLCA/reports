"""
A function to read a list of observations from a spreadsheet and apply them to models found in a foreground.

The spreadsheet should have the following fields:
Specifiers:
 activity - external ref of activity
 child_flow - external ref of flow-- all child flows with the named flow will be affected.  if omitted, apply to the
  reference flow
 scenario - scenario name under which the observation should be applied

Arguments:
 anchor - new anchor. 'cutoff' or 'CUTOFF' to cutoff flow
 descend - for anchor. Should be case-insensitive true or false or 0 or 1. blank = None = unspecified.
 parameter - new exchange value
 units - units for exchange value

"activity" must refer to a fragment, and is required.
If "child_flow" is omitted, the observation will be applied to the named activity.
If "scenario" is omitted, the observation will be applied to the default scenario.

any of the arguments may be included; if no arguments are included, the row will have no effect.
special semantics:
If "child_flow" is "*" and the "descend" specification is not None, then the specification is applied to all child flows

"""
from .float_conv import to_float


def _cutoff(anc):
    if isinstance(anc, str):
        if anc.lower() == 'cutoff':
            return True
    return False


def _descend(desc):
    if desc is None:
        return None
    elif isinstance(desc, str):
        if desc.lower() in ('false', '0'):
            return False
        elif desc.lower() in ('true', '1'):
            return True
        elif desc.lower() == 'none':
            return None
    return bool(desc)


class ObservationsFromSpreadsheet(object):
    def _errmesg(self, ssr, message):
        if self.quiet:
            return
        print('OBS: Row %d: %s' % (ssr, message))

    def _mesg(self, obj, sc, message):
        if self.quiet:
            return
        print('OBS: %5.5s {%s} %s' % (obj.uuid, sc, message))

    def __init__(self, fg, sheet, quiet=False):
        """

        :param fg: a foreground
        :param sheet: an Xlrd-like.
        :param quiet: default False
        :return:
        """
        self.fg = fg
        self.sheet = sheet
        self.quiet = quiet

    def _handle_anchor(self, ssr, obj, row):
        # anchor
        sc = row.get('scenario')

        anc = row.get('anchor')

        if anc:
            if _cutoff(anc):
                for o in obj:
                    o.clear_termination(scenario=sc)
                    self._mesg(o, sc, 'to cutoff')
                    return
            desc = _descend(row.get('descend'))
            a_o = row.get('anchor_origin')
            a_f = row.get('anchor_flow')
            if a_o:
                anchor = self.fg.catalog_ref(a_o, anc)
            else:
                anchor = self.fg[anc]
                if anchor is None:
                    self._errmesg(ssr, 'Anchor %s not found' % anc)
                    return
            for o in obj:
                o.clear_termination(scenario=sc)
                if desc is None:
                    desc = o.term.descend
                self.fg.observe(o, scenario=sc, anchor_node=anchor, anchor_flow=a_f, descend=desc)
                mesg = 'anchor to %s' % anc
                if a_f:
                    mesg += ' (anchor flow %s)' % a_f
                if desc is not None:
                    mesg += ' (descend %s)' % bool(desc)
                self._mesg(o, sc, mesg)
        else:
            desc = _descend(row.get('descend'))

            if desc is not None:
                for o in obj:
                    if o.termination(sc) is o.term:
                        o.terminate(o.term.term_node, scenario=sc, term_flow=o.term.term_flow, descend=desc)
                    else:
                        o.termination(sc).descend = desc
                    self._mesg(o, sc, 'descend to %s' % desc)

    def _handle_ev(self, obj, row):
        sc = row.get('scenario')
        ev = row.get('parameter')
        units = row.get('units')
        if ev is not None:
            ev = to_float(ev)
            for o in obj:
                self.fg.observe(o, scenario=sc, exchange_value=ev, units=units)
                mesg = 'observing %g' % ev
                if units is not None:
                    mesg += ' %s' % units
                self._mesg(o, sc, mesg)

    def apply(self):
        for i in range(1, self.sheet.nrows):
            ssr = i + 1
            row = self.sheet.row_dict(i)
            if row.get('activity') is None:
                self._errmesg(ssr, 'Skipping blank row')
                continue
            act = self.fg[row['activity']]
            if act is None:
                self._errmesg(ssr, 'Activity %s not found' % row['activity'])
                continue
            if row.get('child_flow'):
                if row['child_flow'] == '*':
                    obj = [cf for cf in act.child_flows]
                    p = row.pop('parameter', None)
                    a = row.pop('anchor', None)
                    if p or a:
                        self._errmesg(ssr, 'ignoring specs for descend special "*"')
                else:
                    cf = self.fg[row['child_flow']]
                    if cf is None:
                        self._errmesg(ssr, 'Child flow %s not found' % row['child_flow'])
                        continue
                    if cf.entity_type == 'flow':
                        obj = list(act.children_with_flow(cf, recurse=True))
                    else:
                        obj = [cf]
            else:
                obj = [act]
            self._handle_anchor(ssr, obj, row)
            self._handle_ev(obj, row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return
