#!/usr/bin/env python3
"""
pcb_review.py — check a KiCad .kicad_pcb against first-PCB best practices.

This is the automated companion to the "Practical Advice for Your First PCB(s)"
guide. It reads a board file directly (no KiCad install, no running KiCad, no
pcbnew) and reports, section by section, whether the things the guide asks for
are actually present on the board — and where they aren't.

It is deliberately GENERIC: it keys off standard KiCad footprint names, refdes
prefixes, and net-name conventions rather than any one person's project style.
Everything project-specific (which nets are "power", what counts as a mounting
hole, etc.) is a tunable pattern list near the top so a different house style can
adjust it without touching the logic.

It never edits the board. Output is a plain-text report; a human (or the calling
model) reads it and explains the *why*, tying each item back to the guide.

Report sections, mapping to the guide:
  OVERVIEW              — layers / size / counts
  ASSEMBLY              — component size & package accessibility, double-sided SMD
  MECHANICAL FIT        — mounting holes, rounded corners
  DOCUMENTATION         — board name, revision, test points, status LEDs, connectors
  POWER & GROUND        — ground pours both sides, fragmentation, stitching, trace
                          widths on power nets, bypass caps near ICs
  LAYOUT REMINDERS      — RF and SMPS parts that need datasheet-specific layout
  BEFORE YOU ORDER      — DRC / design-rule reminders (can't run DRC without KiCad)
  ADVANCED (beyond the  — noise coupling exposure: sensitive nets running alongside
  guide)                  supply/clock nets. Off the beginner path on purpose.

Status tags:
  [OK]    present / satisfied
  [MISS]  the guide asks for this and it's absent — act on it
  [CHECK] can't be decided mechanically; a human needs to eyeball it
  [WARN]  present but likely to cause trouble
  [INFO]  neutral fact worth stating
  [n/a]   doesn't apply to this board

Usage:
  pcb_review.py board.kicad_pcb
  pcb_review.py board.kicad_pcb --no-advanced        # skip the noise section
  pcb_review.py board.kicad_pcb --power '+*,vcc*,vdd*,vmot*' --thin 0.3
"""
from __future__ import annotations
import os, math, argparse, fnmatch, re, glob
from collections import defaultdict

# --------------------------------------------------------------------------
# Tunable pattern lists (a different house style edits these, not the logic).
# All matched case-insensitively; net/footprint patterns are fnmatch globs.
# --------------------------------------------------------------------------
POWER_NET_PATTERNS = ['+*', 'vcc*', 'vdd*', 'vdda*', 'vddio*', 'vaa*', 'vbat*',
                      'vin', 'vin_*', 'vout*', 'vsys*', 'vbus*', 'vmot*', 'vpp',
                      'v+', '*_5v', '*_3v3', '5v', '3v3', '3.3v', '12v', '9v']
GND_NET_PATTERNS = ['gnd*', '*_gnd', 'agnd*', 'dgnd*', 'pgnd*', 'vss*', '0v']

# The advanced noise section is name-independent on the victim side: it treats
# EVERY routed signal net as a potential victim and measures geometry. Aggressors
# are supply/plane nets — anything matching a power pattern, filled as a copper
# pour, or named like a clock — excluding ground. Clocks are added by name because
# they're noisy but aren't "power labels".
CLOCK_PATTERNS = ['*clk*', '*clock*', '*sw_node*', '*lx*', '*charge*']

# Package / footprint recognition.
PASSIVE_CODES = ('008004', '01005', '0201', '0402', '0603', '0805', '1206', '1210')
AVOID_PASSIVES = ('008004', '01005', '0201')      # microscope territory for hand work
PRACTICE_PASSIVES = ('0402',)                     # doable with practice
LEADLESS_KW = ('qfn', 'dfn', 'bga', 'lga', 'wlcsp', 'csp', 'son', 'lfcsp', 'ubga')
RF_KW = ('esp32', 'esp8266', 'nrf', 'rfm', 'antenna', '_ant', 'sx12', 'cc25', 'bgt', 'wifi', 'ble')
SMPS_KW = ('buck', 'boost', 'smps', 'sepic', 'tps5', 'tps6', 'lm25', 'lm27', 'mp15', 'mp23',
           'mp28', 'ap63', 'mc34063', 'lmr', 'sy8', 'rt6', 'sw_reg', 'dcdc', 'dc-dc')

SILK_LAYERS = ('F.SilkS', 'B.SilkS')
DECOUPLE_MAX_F = 1.0e-6      # a cap <= 1uF on a supply rail counts as decoupling
DECOUPLE_NEAR_MM = 5.0       # a bypass cap should sit within this of the IC power pin
IC_MIN_PADS = 8              # footprints with >= this many pads are treated as ICs
REV_RE = re.compile(r'(?i)\brev\b|\bv\d|\br\d|\d+\.\d+|\$\{(revision|comment)')
UNIT_F = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}

# --------------------------------------------------------------------------
# Tiny S-expression core (same shape as the KiCad review scripts it borrows from)
# --------------------------------------------------------------------------
def tokenize(s):
    toks = []; i = 0; n = len(s)
    while i < n:
        c = s[i]
        if c in '()': toks.append(c); i += 1
        elif c.isspace(): i += 1
        elif c == '"':
            j = i + 1; buf = []
            while j < n:
                if s[j] == '\\':
                    # decode the escape rather than dropping the backslash — KiCad
                    # stores multi-line silk text with literal \n, and collapsing
                    # that to a bare 'n' garbles the silkscreen readout
                    esc = s[j + 1]
                    buf.append({'n': '\n', 't': '\t', 'r': '\r'}.get(esc, esc)); j += 2
                elif s[j] == '"': j += 1; break
                else: buf.append(s[j]); j += 1
            toks.append(('STR', ''.join(buf))); i = j
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()"': j += 1
            toks.append(('SYM', s[i:j])); i = j
    return toks

def parse(toks):
    pos = 0
    def helper():
        nonlocal pos
        pos += 1; node = []
        while toks[pos] != ')':
            node.append(helper() if toks[pos] == '(' else toks[pos])
            if not isinstance(node[-1], list): pos += 1
        pos += 1; return node
    out = []
    while pos < len(toks):
        if toks[pos] == '(': out.append(helper())
        else: pos += 1
    return out

def head(n): return n[0][1] if n and isinstance(n[0], tuple) else None
def atoms(n):
    res = []; skip = True
    for a in n:
        if isinstance(a, tuple):
            if skip: skip = False; continue
            res.append(a[1])
    return res
def kids(n, name): return [c for c in n if isinstance(c, list) and head(c) == name]
def first(n, name):
    c = kids(n, name); return c[0] if c else None
def prop(n, key):
    for p in kids(n, 'property'):
        a = atoms(p)
        if len(a) >= 2 and a[0].lower() == key.lower(): return a[1]
    return None
def fnum(x):
    try: return float(x)
    except Exception: return None

def match_any(name, patterns):
    nl = (name or '').lower()
    return any(fnmatch.fnmatch(nl, p.strip().lower()) for p in patterns if p.strip())

def resolve_net(node, netnames):
    """Net NAME for a (net ...) node — handles numeric (KiCad<=8) and name (KiCad 9)."""
    if not node: return ''
    a = atoms(node)
    if not a: return ''
    if len(a) >= 2 and a[1]:      # (net 5 "GND") -> name is right there
        return a[1]
    try: return netnames.get(int(a[0]), a[0])
    except (ValueError, TypeError): return a[0] or ''

def seg_pt_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0: return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

# --------------------------------------------------------------------------
# Footprint helpers
# --------------------------------------------------------------------------
def _fp_name(fp):
    a = atoms(fp); return a[0] if a else ''
def _at_xyr(node):
    t = first(node, 'at')
    if not t: return (0.0, 0.0, 0.0)
    a = atoms(t)
    return (fnum(a[0]) or 0.0, fnum(a[1]) or 0.0, (fnum(a[2]) if len(a) > 2 else 0.0) or 0.0)
def _fp_layer(fp):
    l = first(fp, 'layer'); return atoms(l)[0] if l else ''
def _fp_attr(fp):
    a = first(fp, 'attr'); return set(atoms(a)) if a else set()
def _ref(fp): return (prop(fp, 'Reference') or '').upper()
def _val(fp): return prop(fp, 'Value') or ''

def _pads(fp):
    """(number, type, netname, board_x, board_y) for every pad of a footprint."""
    fx, fy, rot = _at_xyr(fp); th = math.radians(rot); out = []
    for pad in kids(fp, 'pad'):
        a = atoms(pad)
        num = a[0] if a else ''
        typ = a[1] if len(a) > 1 else ''
        t = first(pad, 'at'); pa = atoms(t) if t else []
        px, py = (fnum(pa[0]) or 0.0), (fnum(pa[1]) or 0.0)
        bx = fx + px * math.cos(th) - py * math.sin(th)
        by = fy + px * math.sin(th) + py * math.cos(th)
        nn = ''
        nnode = first(pad, 'net')
        if nnode:
            na = atoms(nnode)
            nn = na[1] if len(na) >= 2 else (na[0] if na else '')
        out.append((num, typ, nn, bx, by))
    return out

def passive_size(nm):
    low = nm.lower()
    for code in PASSIVE_CODES:
        if re.search(r'(?<![0-9])' + code + r'(?![0-9])', low):
            return code
    return None

def pkg_pitch_mm(nm):
    m = re.search(r'(?:pitch|[_-]p)([0-9]*\.?[0-9]+)mm', nm.lower())
    return float(m.group(1)) if m else None

def is_leadless(nm):
    low = nm.lower()
    return any(k in low for k in LEADLESS_KW)

def cap_farads(val):
    """Best-effort parse of a capacitor value string to Farads; None if unknown."""
    if not val: return None
    s = re.sub(r'(?i)\s*f\b', '', val.strip())
    m = re.match(r'(?i)^([0-9]*\.?[0-9]+)\s*([pnuµm]?)$', s)
    if m:
        u = m.group(2).lower().replace('µ', 'u')
        return float(m.group(1)) * UNIT_F[u] if u else None   # bare number: unknown scale
    m = re.match(r'(?i)^([0-9]+)([pnuµm])([0-9]+)$', s)         # 4u7, 0u1, 100n0
    if m:
        u = m.group(2).lower().replace('µ', 'u')
        return float(m.group(1) + '.' + m.group(3)) * UNIT_F[u]
    return None

def is_mounting_hole(fp):
    nm = _fp_name(fp).lower(); ref = _ref(fp)
    return 'mountinghole' in nm or 'mounting_hole' in nm or ref.startswith(('MH', 'MK')) or \
        (ref.startswith('H') and ref[1:].isdigit())
def is_testpoint(fp):
    return 'testpoint' in _fp_name(fp).lower() or _ref(fp).startswith('TP')
def is_led(fp):
    blob = (_fp_name(fp) + ' ' + _val(fp)).lower()
    return 'led' in blob or _ref(fp).startswith('LED')
def is_connector(fp):
    nm = _fp_name(fp).lower(); ref = _ref(fp)
    return any(k in nm for k in ('connector', 'header', 'pinheader', 'pinsocket',
               'terminalblock', 'screwterminal', 'jack', 'usb', 'molex', 'jst', 'barrel')) \
        or ref.startswith(('J', 'CN', 'CON')) or (ref.startswith('P') and ref[1:].isdigit())

def _edge_count(root, tag):
    n = 0
    for g in kids(root, tag):
        ly = first(g, 'layer')
        if ly and atoms(ly) and atoms(ly)[0] == 'Edge.Cuts': n += 1
    return n

def _silk_texts(root):
    out = []
    for t in kids(root, 'gr_text'):
        a = atoms(t)
        if not a: continue
        ly = atoms(first(t, 'layer'))[0] if first(t, 'layer') else ''
        if ly in SILK_LAYERS: out.append(a[0])
    return out

def _silk_texts_xy(root):
    """Board-level silk free text with its placed position: (text, x, y)."""
    out = []
    for t in kids(root, 'gr_text'):
        a = atoms(t)
        if not a: continue
        ly = atoms(first(t, 'layer'))[0] if first(t, 'layer') else ''
        if ly in SILK_LAYERS:
            x, y, _ = _at_xyr(t); out.append((a[0], x, y))
    return out

def _hidden(node):
    """True if a property/text node is hidden (won't render). Handles the KiCad 9
    `(hide yes)` form and the older bare `hide` token."""
    h = first(node, 'hide')
    if h is not None:
        a = atoms(h)
        return (not a) or a[0] in ('yes', 'true')
    return any(isinstance(x, tuple) and x[1] == 'hide' for x in node)

def _fp_silk_texts(fp):
    """Strings a footprint draws on its own silkscreen: fp_text elements *and*
    visible property fields placed on a silk layer. The latter matters because a
    connector's pin label is often a custom field (e.g. 'Control'='PWR') dropped
    onto F.SilkS rather than a separate silk text object."""
    out = []
    for t in kids(fp, 'fp_text'):
        a = atoms(t)
        ly = atoms(first(t, 'layer'))[0] if first(t, 'layer') else ''
        if ly in SILK_LAYERS and len(a) >= 2: out.append(a[1])
    for pr in kids(fp, 'property'):
        a = atoms(pr)
        ly = atoms(first(pr, 'layer'))[0] if first(pr, 'layer') else ''
        if ly in SILK_LAYERS and len(a) >= 2 and not _hidden(pr): out.append(a[1])
    return out

def tag(s): return '[%s]' % s
def line(status, text, detail=''):
    print('  %-7s %s%s' % (tag(status), text, ('  — ' + detail) if detail else ''))

# --------------------------------------------------------------------------
# Main analysis
# --------------------------------------------------------------------------
def analyze(path, power_pats, gnd_pats, thin_mm, advanced, proximity):
    root = parse(tokenize(open(path).read()))[0]
    fps = kids(root, 'footprint')

    netnames = {}
    for nd in kids(root, 'net'):
        a = atoms(nd)
        if not a: continue
        try: netnames[int(a[0])] = a[1] if len(a) > 1 else ''
        except (ValueError, TypeError): pass

    cu_layers = []
    lyblock = first(root, 'layers')
    if lyblock:
        for entry in lyblock:
            if isinstance(entry, list):
                a = atoms(entry)
                if a and a[0].endswith('.Cu'): cu_layers.append(a[0])

    # board extent
    xs = []; ys = []
    for g in (kids(root, 'gr_line') + kids(root, 'gr_arc') +
              kids(root, 'gr_rect') + kids(root, 'gr_poly')):
        ly = first(g, 'layer')
        if ly and atoms(ly)[0] == 'Edge.Cuts':
            for t in ('start', 'end', 'center', 'mid'):
                node = first(g, t)
                if node:
                    a = atoms(node); xs.append(float(a[0])); ys.append(float(a[1]))
            pts = first(g, 'pts')
            if pts:
                for xy in kids(pts, 'xy'):
                    a = atoms(xy); xs.append(float(a[0])); ys.append(float(a[1]))
    bw = (max(xs) - min(xs)) if xs else 0.0
    bh = (max(ys) - min(ys)) if ys else 0.0
    board_area = bw * bh

    # tracks / widths / per-net length
    segs = []
    len_by_net = defaultdict(float)
    width_by_net = defaultdict(list)
    widths = defaultdict(int)
    for s in kids(root, 'segment'):
        st = atoms(first(s, 'start')); en = atoms(first(s, 'end'))
        ly = atoms(first(s, 'layer'))[0] if first(s, 'layer') else '?'
        nn = resolve_net(first(s, 'net'), netnames)
        w = fnum(atoms(first(s, 'width'))[0]) if first(s, 'width') else None
        x1, y1, x2, y2 = float(st[0]), float(st[1]), float(en[0]), float(en[1])
        segs.append((nn, ly, x1, y1, x2, y2, w))
        len_by_net[nn] += math.hypot(x2 - x1, y2 - y1)
        if w:
            width_by_net[nn].append(w); widths[round(w, 3)] += 1

    # vias
    via_by_net = defaultdict(int); total_vias = 0
    for v in kids(root, 'via'):
        via_by_net[resolve_net(first(v, 'net'), netnames)] += 1; total_vias += 1

    # zones -> per-layer island count + area
    zones = []
    for z in kids(root, 'zone'):
        nn = resolve_net(first(z, 'net'), netnames)
        nm = atoms(first(z, 'net_name'))[0] if first(z, 'net_name') else (nn or '?')
        per = defaultdict(lambda: [0, 0.0])
        for fpz in kids(z, 'filled_polygon'):
            ly = atoms(first(fpz, 'layer'))[0] if first(fpz, 'layer') else '?'
            pts = first(fpz, 'pts')
            if not pts: continue
            poly = [(float(atoms(xy)[0]), float(atoms(xy)[1])) for xy in kids(pts, 'xy')]
            if len(poly) < 3: continue
            s2 = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
                s2 += x1 * y2 - x2 * y1
            per[ly][0] += 1; per[ly][1] += abs(s2) / 2.0
        zones.append((nm, nn, dict(per)))

    def is_power(n): return match_any(n, power_pats)
    def is_gnd(n): return match_any(n, gnd_pats)

    # ================= OVERVIEW =================
    print('==== FIRST-PCB REVIEW: %s ====' % os.path.basename(path))
    print('(companion to the "Practical Advice for Your First PCB(s)" guide)\n')
    print('-- OVERVIEW --')
    line('INFO', 'copper layers: %d (%s)' % (len(cu_layers), ', '.join(cu_layers) or '?'))
    if bw:
        line('INFO', 'board size: %.1f x %.1f mm  (%.0f mm^2/layer)' % (bw, bh, board_area))
    line('INFO', 'footprints %d | nets %d | tracks %d | vias %d | zones %d' % (
        len(fps), len(netnames), len(segs), total_vias, len(zones)))

    # ================= ASSEMBLY =================
    print('\n-- ASSEMBLY (hand-solderability & cost) --')
    avoid, practice, leadless, finepitch = [], [], [], []
    for fp in fps:
        nm = _fp_name(fp); ref = _ref(fp)
        size = passive_size(nm)
        if size in AVOID_PASSIVES: avoid.append('%s (%s)' % (ref, size))
        elif size in PRACTICE_PASSIVES: practice.append('%s (%s)' % (ref, size))
        if is_leadless(nm):
            leadless.append('%s (%s)' % (ref, nm.split(':')[-1]))
        p = pkg_pitch_mm(nm)
        if p is not None and p <= 0.5:
            finepitch.append('%s (%s, %.2fmm pitch)' % (ref, nm.split(':')[-1], p))
    if avoid:
        line('WARN', 'parts at 0201/01005/smaller — microscope territory for hand work',
             ', '.join(avoid[:12]) + (' …' if len(avoid) > 12 else ''))
    if practice:
        line('CHECK', '0402 passives — doable by hand with practice', ', '.join(practice[:12]) +
             (' …' if len(practice) > 12 else ''))
    if finepitch:
        line('CHECK', 'fine-pitch parts (<=0.5mm) — hard to hand-solder without bridging',
             ', '.join(finepitch[:10]) + (' …' if len(finepitch) > 10 else ''))
    if leadless:
        line('WARN', 'leadless / bottom-terminal packages — pads hidden underneath, need '
             'hot air / hotplate / PCBA', ', '.join(leadless[:10]) +
             (' …' if len(leadless) > 10 else ''))
    if not (avoid or practice or finepitch or leadless):
        line('OK', 'no unusually small or hidden-pad parts detected')

    smd_f = [fp for fp in fps if 'smd' in _fp_attr(fp) and _fp_layer(fp) == 'F.Cu']
    smd_b = [fp for fp in fps if 'smd' in _fp_attr(fp) and _fp_layer(fp) == 'B.Cu']
    th_any = [fp for fp in fps if 'through_hole' in _fp_attr(fp)]
    if smd_f and smd_b:
        line('WARN', 'double-sided SMD (%d front, %d back) — blocks hotplate use and '
             'usually forces "Standard" PCBA' % (len(smd_f), len(smd_b)))
    elif (smd_f or smd_b) and th_any:
        line('OK', 'SMD on one side + through-hole (%d TH parts) — the easy combination'
             % len(th_any))
    elif smd_f or smd_b:
        line('OK', 'single-sided SMD (%d parts) — hotplate/stencil friendly'
             % (len(smd_f) + len(smd_b)))
    else:
        line('INFO', 'no SMD parts detected (all through-hole or unclassified)')

    # ================= MECHANICAL FIT =================
    print('\n-- MECHANICAL FIT --')
    holes = [fp for fp in fps if is_mounting_hole(fp)]
    np_pads = sum(1 for fp in fps for pad in _pads(fp) if pad[1] == 'np_thru_hole')
    if holes:
        line('OK', 'mounting holes present (%d)' % len(holes),
             ', '.join(_ref(fp) or _fp_name(fp).split(':')[-1] for fp in holes[:8]))
    elif np_pads:
        line('CHECK', '%d non-plated holes but no MountingHole footprints — confirm the '
             'board can actually be fastened down' % np_pads)
    else:
        line('MISS', 'no mounting holes found — how will this attach to its enclosure? '
             '(panel pots/switches sometimes suffice; confirm)')

    arcs = _edge_count(root, 'gr_arc'); rect = _edge_count(root, 'gr_rect')
    poly = _edge_count(root, 'gr_poly')
    if rect: line('MISS', 'board outline is a plain rectangle — round the corners')
    elif arcs >= 4: line('OK', 'rounded board corners (%d edge arcs)' % arcs)
    elif arcs >= 1: line('CHECK', 'only %d arc(s) on Edge.Cuts — verify every corner is rounded' % arcs)
    elif poly: line('CHECK', 'polygon outline — verify corner radii by eye')
    else: line('CHECK', 'no rectangle or arcs on Edge.Cuts — verify the outline exists and is rounded')

    # ================= DOCUMENTATION =================
    print('\n-- DOCUMENTATION --')
    silk = _silk_texts(root)
    stem = os.path.splitext(os.path.basename(path))[0]
    name_ok = any(stem.lower() in t.lower() or '${PROJECTNAME}' in t for t in silk)
    rev_ok = any(REV_RE.search(t) for t in silk)
    line('OK' if name_ok else 'CHECK', 'board name on silkscreen',
         'project "%s"; if CHECK, confirm a real name is among the silk text below' % stem)
    line('OK' if rev_ok else 'MISS', 'version / revision on silkscreen')
    if silk:
        # collapse multi-line text to one line and de-duplicate (repeated labels
        # like connector part numbers otherwise flood the readout) while keeping order
        seen = set(); clean = []
        for t in silk:
            flat = ' '.join(t.split())
            if flat and flat not in seen:
                seen.add(flat); clean.append(flat)
        readout = ' | '.join(clean)
        line('INFO', 'board silk text: ' + readout[:240] + (' …' if len(readout) > 240 else ''))
    tps = [fp for fp in fps if is_testpoint(fp)]
    leds = [fp for fp in fps if is_led(fp)]
    line('OK' if tps else 'CHECK', 'test points: %d' % len(tps),
         'cheap insurance for bring-up — add a few on the power rails if none')
    line('OK' if leds else 'INFO', 'status LEDs: %d' % len(leds),
         'a power LED gives instant "is it alive?" feedback' if not leds else '')
    conns = [fp for fp in fps if is_connector(fp)]
    if conns:
        board_silk = _silk_texts_xy(root)
        LABEL_NEAR = 8.0     # mm from a connector pad that free silk text can sit and still count
        unlabeled = []
        for fp in conns:
            # A connector counts as labeled if it draws its own silk (pin numbers /
            # names beyond a bare refdes) OR there's free silk text near its pads —
            # free-labeling the pins on the board is often clearer than footprint text.
            own = [s for s in _fp_silk_texts(fp)
                   if s and not s.startswith('$') and s.upper() != _ref(fp)]
            pads = [(pd[3], pd[4]) for pd in _pads(fp)]
            near = bool(own) or any(
                math.hypot(tx - px, ty - py) <= LABEL_NEAR
                for _, tx, ty in board_silk for px, py in pads)
            if not near:
                unlabeled.append(_ref(fp) or _fp_name(fp).split(':')[-1])
        if unlabeled:
            line('CHECK', 'connectors/headers with no silk labels nearby: %d of %d'
                 % (len(unlabeled), len(conns)),
                 'label the pins (own silk or free text alongside), unless it\'s a '
                 'standard interface like USB: ' + ', '.join(unlabeled[:10]))
        else:
            line('OK', 'all %d connectors have silk labels on or beside them' % len(conns))
    else:
        line('INFO', 'no connectors/headers detected')

    # ================= POWER & GROUND =================
    print('\n-- POWER & GROUND --')
    gnd_zone_layers = set()
    print('  copper pours:')
    for nm, nn, per in zones:
        for ly, (cnt, area) in sorted(per.items()):
            cov = (100.0 * area / board_area) if board_area else 0.0
            frag = '  <-- fragmented' if cnt >= 6 else ''
            print('    %-10s %-7s : %2d island(s), %5.0f mm^2 (%3.0f%% of layer)%s'
                  % (nm, ly, cnt, area, cov, frag))
            if is_gnd(nm): gnd_zone_layers.add(ly)
    if not zones:
        line('MISS', 'no copper pours at all — add a ground pour (both sides on 2-layer)')
    elif len(gnd_zone_layers) >= 2:
        line('OK', 'ground pour on both sides (%s)' % ', '.join(sorted(gnd_zone_layers)))
    elif len(gnd_zone_layers) == 1:
        line('CHECK', 'ground pour on only one layer (%s) — the guide suggests both sides'
             % next(iter(gnd_zone_layers)))
    else:
        line('CHECK', 'pours present but none matched a ground-net pattern — verify your '
             'ground net name against --ground')
    gnd_vias = sum(v for n, v in via_by_net.items() if is_gnd(n))
    if total_vias:
        line('INFO', 'ground stitching vias: %d of %d total' % (gnd_vias, total_vias))

    # trace widths on power/ground nets
    default_w = max(widths.items(), key=lambda kv: kv[1])[0] if widths else None
    if default_w is not None:
        line('INFO', 'most common track width: %.3f mm (assumed signal default)' % default_w)
    thin = []
    for nn, ws in width_by_net.items():
        if not (is_power(nn) or is_gnd(nn)): continue
        if min(ws) <= thin_mm:
            thin.append((nn, min(ws), max(ws), len_by_net.get(nn, 0.0)))
    if thin:
        line('CHECK', '%d power/ground net(s) routed at <= %.2f mm — widen if they carry '
             'real current' % (len(thin), thin_mm))
        for nn, wmin, wmax, L in sorted(thin, key=lambda t: -t[3])[:10]:
            print('         - %-16s width %.2f–%.2f mm, %.0f mm routed' % (nn, wmin, wmax, L))
    elif any(is_power(n) or is_gnd(n) for n in width_by_net):
        line('OK', 'power/ground nets are all wider than %.2f mm' % thin_mm)

    # bypass caps near IC power pins (heuristic)
    ics = [fp for fp in fps if len(_pads(fp)) >= IC_MIN_PADS or _ref(fp).startswith('U')]
    caps = [fp for fp in fps if _ref(fp).startswith('C')]
    small_cap_nets = set()
    for c in caps:
        f = cap_farads(_val(c))
        if f is not None and f <= DECOUPLE_MAX_F:
            for pad in _pads(c):
                if pad[2]: small_cap_nets.add(pad[2])
    ic_issues = []
    checked_ic = 0
    for ic in ics:
        pads = _pads(ic)
        pwr_pads = [(pd[2], pd[3], pd[4]) for pd in pads if is_power(pd[2])]
        if not pwr_pads: continue
        checked_ic += 1
        for net, px, py in pwr_pads:
            # nearest small-cap pad on the same supply net
            best = None
            if net in small_cap_nets:
                for c in caps:
                    f = cap_farads(_val(c))
                    if f is None or f > DECOUPLE_MAX_F: continue
                    for pd in _pads(c):
                        if pd[2] != net: continue
                        d = math.hypot(pd[3] - px, pd[4] - py)
                        if best is None or d < best: best = d
            if best is None:
                ic_issues.append((_ref(ic), net, None))
            elif best > DECOUPLE_NEAR_MM:
                ic_issues.append((_ref(ic), net, best))
    if checked_ic == 0:
        line('n/a', 'bypass caps: no ICs with recognizable power pins (check net names / --power)')
    elif not ic_issues:
        line('OK', 'every IC supply pin has a <=1uF cap within %.0f mm' % DECOUPLE_NEAR_MM)
    else:
        line('CHECK', 'bypass-cap coverage looks thin on %d IC supply pin(s) [heuristic]'
             % len(ic_issues))
        for ref, net, d in ic_issues[:10]:
            where = 'no small cap on this rail' if d is None else 'nearest is %.1f mm away' % d
            print('         - %-8s %-10s %s' % (ref, net, where))

    # ================= LAYOUT REMINDERS =================
    print('\n-- LAYOUT REMINDERS (datasheet-specific placement) --')
    rf = [fp for fp in fps if any(k in (_fp_name(fp) + ' ' + _val(fp)).lower() for k in RF_KW)]
    smps = [fp for fp in fps if any(k in (_fp_name(fp) + ' ' + _val(fp)).lower() for k in SMPS_KW)]
    if rf:
        line('CHECK', 'RF parts detected — enforce the datasheet antenna keep-out',
             ', '.join('%s %s' % (_ref(f), _val(f)) for f in rf[:6]))
    if smps:
        line('CHECK', 'switching-supply parts detected — follow the datasheet layout exactly',
             ', '.join('%s %s' % (_ref(f), _val(f)) for f in smps[:6]))
    if not rf and not smps:
        line('OK', 'no RF or switching-supply parts detected (no special keep-outs needed)')

    # ================= BEFORE YOU ORDER =================
    print('\n-- BEFORE YOU ORDER --')
    dru = glob.glob(os.path.join(os.path.dirname(os.path.abspath(path)), '*.kicad_dru'))
    line('OK' if dru else 'CHECK', 'custom design rules (.kicad_dru): %s'
         % (os.path.basename(dru[0]) if dru else 'none found'),
         'load your fab\'s min track/space/drill/annular-ring before final DRC' if not dru else '')
    line('CHECK', 'run DRC in KiCad with your fab\'s rules and fix every violation',
         'this script can\'t run DRC — it also covers silk-over-pad and clearance')

    # ================= ADVANCED: NOISE COUPLING =================
    if advanced:
        print('\n-- ADVANCED: NOISE COUPLING (beyond the beginner guide) --')
        print('  Optional, and expects false positives. Flags any signal trace that runs')
        print('  a long way alongside a supply or plane, by geometry alone — worth a look')
        print('  on analog/mixed-signal boards. A net running beside its own supply is')
        print('  fine to ignore; this is a "verify these", not a DRC rule.')
        poured = set(nm for nm, _, _ in zones)
        aggr = set(s[0] for s in segs if s[0] and not is_gnd(s[0]) and
                   (is_power(s[0]) or s[0] in poured or match_any(s[0], CLOCK_PATTERNS)))
        coupling_report(segs, aggr, gnd_pats, proximity)


def coupling_report(segs, aggr_nets, gnd_pats, proximity, min_len=10.0, min_pct=15.0):
    """Name-independent coupling scan: for every routed signal net (not a supply/
    plane, not ground), measure how much of it runs within `proximity` of any
    aggressor trace. Report the ones with a substantial alongside run. False
    positives (a net beside its own supply) are expected and fine — it's a list to
    eyeball, not a rule to pass."""
    agg = [s for s in segs if s[0] in aggr_nets]
    if not agg:
        line('n/a', 'no supply/plane/clock nets found to check against (see --power/--ground)')
        return

    def is_gnd(n): return match_any(n, gnd_pats)
    victim_nets = sorted(set(s[0] for s in segs
                             if s[0] and s[0] not in aggr_nets and not is_gnd(s[0])))
    rows = []
    for vname in victim_nets:
        vsegs = [s for s in segs if s[0] == vname]
        Ltot = 0.0; close = 0.0; gmin = 1e9; partner = None
        for (_, _, x1, y1, x2, y2, _) in vsegs:
            L = math.hypot(x2 - x1, y2 - y1); Ltot += L
            steps = max(2, int(L / 0.5))
            for k in range(steps + 1):
                t = k / steps; px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                best = 1e9; bp = None
                for (a, _, sx1, sy1, sx2, sy2, _) in agg:
                    d = seg_pt_dist(px, py, sx1, sy1, sx2, sy2)
                    if d < best: best = d; bp = a
                if best < gmin: gmin = best; partner = bp
                if best <= proximity: close += L / (steps + 1)
        pct = (100.0 * close / Ltot) if Ltot else 0.0
        # only surface nets with a real alongside run — keeps the list worth reading
        if close >= min_len and pct >= min_pct:
            rows.append((close, pct, vname, Ltot, gmin, partner))
    if not rows:
        line('OK', 'no signal net runs a long way alongside a supply/plane')
        return
    for close, pct, vname, Ltot, gmin, partner in sorted(rows, reverse=True)[:15]:
        status = 'WARN' if (pct >= 40 or close >= 25) else 'CHECK'
        line(status, '%-16s %.0fmm (%.0f%% of %.0fmm) within %.2fmm of %s, min gap %.2fmm'
             % (vname, close, pct, Ltot, proximity, partner, gmin))
    if len(rows) > 15:
        line('INFO', '… and %d more below the top 15' % (len(rows) - 15))


def main():
    ap = argparse.ArgumentParser(description='Check a KiCad board against first-PCB best practices.')
    ap.add_argument('pcb')
    ap.add_argument('--power', default=','.join(POWER_NET_PATTERNS),
                    help='comma-separated globs for power-net names')
    ap.add_argument('--ground', default=','.join(GND_NET_PATTERNS),
                    help='comma-separated globs for ground-net names')
    ap.add_argument('--thin', type=float, default=0.3,
                    help='mm; power/ground nets at or below this width get flagged')
    ap.add_argument('--proximity', type=float, default=0.6,
                    help='mm; "running alongside" distance for the advanced noise section')
    ap.add_argument('--no-advanced', action='store_true',
                    help='skip the advanced noise-coupling section')
    args = ap.parse_args()
    analyze(args.pcb, args.power.split(','), args.ground.split(','), args.thin,
            not args.no_advanced, args.proximity)


if __name__ == '__main__':
    main()
