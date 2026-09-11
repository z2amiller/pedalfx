"""Dipole arm footprint text for the PCB antenna boards (bead kicad-y27p, item 1).

One function reproduces util-Antenna1090's Dipole_1090_Arms and util-Antenna772's Dipole_772_Arms exactly (the
fabbed copper) and adds an optional mask landing window at each arm's inner end for the castellated UHF module
(kicad-wbhj). Each arm: a THT custom pad (copper both faces) for the strip with an anchor hole, round stitch holes,
an SMD custom pad for the trim ladder (bars + cut bridges, front only), mask windows over the bridges, silk ticks,
fab outline and courtyard. Pad 1 = left arm (ANT_A), pad 2 = right arm (ANT_B).
"""
import uuid


def u():
    return str(uuid.uuid4())


def poly(pts):
    return "(gr_poly (pts " + " ".join(f"(xy {x:g} {y:g})" for x, y in pts) + ") (width 0) (fill yes))"


def rect_pts(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def bars(s, strip_end, n, pitch, gap):
    out = []
    for k in range(n):
        a = strip_end + k * pitch + gap
        b = strip_end + (k + 1) * pitch
        out.append((s * a, s * b) if s > 0 else (s * b, s * a))
    return out


def gaps(s, strip_end, n, pitch, gap):
    out = []
    for k in range(n):
        a = strip_end + k * pitch
        b = a + gap
        out.append((s * a, s * b) if s > 0 else (s * b, s * a))
    return out


def arm_footprint(*, name, generator, descr, tags, gap, arm_w, arm_l, ladder_n, bar_pitch, bar_gap, bridge_w,
                  bar_shift, stitch_x, anchor_x, bridge_ext, smd_anchor, mask_pad, tick_every, tick_shift,
                  landing=None):
    """Footprint text. tick_every 1 = a silk tick per bar (772), 2 = per pair (1090); tick_shift = extra x offset of
    the tick in bar pitches (0 for 772, 0.5 for 1090); bridge_ext = how far the bridge polygon overlaps the bars;
    smd_anchor = anchor size of the ladder pad; mask_pad = (dx, dy) growth of the bridge mask windows;
    landing = length in mm of an F.Mask window from the arm's inner end (module castellation landing), or None."""
    hw = arm_w / 2
    strip_end = gap / 2 + arm_l - ladder_n * bar_pitch
    tip = gap / 2 + arm_l
    o = []
    a = o.append
    a(f'(footprint "{name}"')
    a('\t(version 20260206)')
    a(f'\t(generator "{generator}")')
    a('\t(generator_version "10.0")')
    a('\t(layer "F.Cu")')
    a(f'\t(descr "{descr}")')
    a(f'\t(tags "{tags}")')
    a(f'\t(property "Reference" "REF**" (at 0 -6 0) (layer "F.SilkS") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))')
    a(f'\t(property "Value" "{name}" (at 0 6 0) (layer "F.Fab") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))')
    a(f'\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27) (thickness 0.15))))')
    a(f'\t(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27) (thickness 0.15))))')
    a('\t(attr exclude_from_pos_files exclude_from_bom)')

    def text(s, x, y, rot=0, size=0.8, layer="F.SilkS"):
        a(f'\t(fp_text user "{s}" (at {x:g} {y:g} {rot}) (layer "{layer}") (uuid "{u()}") '
          f'(effects (font (size {size} {size}) (thickness {size * 0.15:.2f}))))')

    def pad(num, kind, shape, x, y, size, drill=None, layers='"*.Cu"', extra=""):
        d = f" (drill {drill:g})" if drill else ""
        a(f'\t(pad "{num}" {kind} {shape} (at {x:g} {y:g}) (size {size[0]:g} {size[1]:g}){d} (layers {layers}) '
          f'(remove_unused_layers no){extra} (uuid "{u()}"))')

    for s, num in ((-1, "1"), (+1, "2")):
        x_in, x_end = s * gap / 2, s * strip_end
        anchor = s * anchor_x
        prim = poly(rect_pts(min(x_in, x_end) - anchor, -hw, max(x_in, x_end) - anchor, hw))
        pad(num, "thru_hole", "custom", anchor, 0, (3, 3), drill=1.0,
            extra=f" (options (clearance outline) (anchor rect)) (primitives {prim})")
        for bx in stitch_x:
            pad(num, "thru_hole", "circle", s * bx, 0, (1.8, 1.8), drill=1.0)
        b = bars(s, strip_end, ladder_n, bar_pitch, bar_gap)
        bx0 = (b[0][0] + b[0][1]) / 2
        prims = [poly(rect_pts(x1 - bx0, -hw, x2 - bx0, hw)) for x1, x2 in b]
        for g1, g2 in gaps(s, strip_end, ladder_n, bar_pitch, bar_gap):
            prims.append(poly(rect_pts(g1 - bridge_ext - bx0, -bridge_w / 2, g2 + bridge_ext - bx0, bridge_w / 2)))
        pad(num, "smd", "custom", bx0, 0, smd_anchor, layers='"F.Cu"',
            extra=f" (options (clearance outline) (anchor rect)) (primitives {' '.join(prims)})")
        for g1, g2 in gaps(s, strip_end, ladder_n, bar_pitch, bar_gap):
            gx = (g1 + g2) / 2
            a(f'\t(fp_rect (start {gx - mask_pad[0]:g} {-bridge_w / 2 - mask_pad[1]:g}) (end {gx + mask_pad[0]:g} {bridge_w / 2 + mask_pad[1]:g}) '
              f'(stroke (width 0) (type default)) (fill yes) (layer "F.Mask") (uuid "{u()}"))')
        for k, (x1, x2) in enumerate(b):
            if k % tick_every == 0:
                text(bar_shift, (x1 + x2) / 2 + s * bar_pitch * tick_shift, -hw - 2.6, 90, size=0.8)
        if landing:
            a(f'\t(fp_rect (start {min(x_in, s * (gap / 2 + landing)):g} {-hw:g}) (end {max(x_in, s * (gap / 2 + landing)):g} {hw:g}) '
              f'(stroke (width 0) (type default)) (fill yes) (layer "F.Mask") (uuid "{u()}"))')
        a(f'\t(fp_rect (start {min(x_in, s * tip):g} {-hw:g}) (end {max(x_in, s * tip):g} {hw:g}) '
          f'(stroke (width 0.1) (type default)) (fill no) (layer "F.Fab") (uuid "{u()}"))')
        a(f'\t(fp_rect (start {min(x_in, s * tip) - 0.5:g} {-hw - 0.5:g}) (end {max(x_in, s * tip) + 0.5:g} {hw + 0.5:g}) '
          f'(stroke (width 0.05) (type default)) (fill no) (layer "F.CrtYd") (uuid "{u()}"))')
    a('\t(embedded_fonts no)')
    a(')')
    return "\n".join(o) + "\n"


# The two fabbed geometries (util-Antenna1090 0.1-g1, util-Antenna772 0.1-g1).
ARMS_1090 = dict(
    name="Dipole_1090_Arms", generator="util-Antenna1090/gen_1090.py",
    descr="1090 MHz PCB half-wave dipole: two 6 x 50 mm arms either side of a 30 mm centre gap, "
          "outer 12 mm of each arm an eight-bar cut-bridge trim ladder (+26M per bar). NEC-sized, bead kicad-vgfc.",
    tags="antenna dipole 1090 ADS-B",
    gap=30.0, arm_w=6.0, arm_l=50.0, ladder_n=8, bar_pitch=1.5, bar_gap=0.6, bridge_w=1.0, bar_shift="+26M",
    stitch_x=(22.0, 32.0, 42.0, 51.0), anchor_x=17.0, bridge_ext=0.25, smd_anchor=(0.8, 0.8), mask_pad=(0.55, 0.35),
    tick_every=2, tick_shift=0.5)
ARMS_772 = dict(
    name="Dipole_772_Arms", generator="util-Antenna772/gen_772.py",
    descr="772 MHz PCB half-wave dipole: two 8 x 76 mm arms either side of a 30 mm centre gap, "
          "outer 15 mm of each arm a six-bar cut-bridge trim ladder (+22 MHz per bar). NEC-sized, bead kicad-3fxn.",
    tags="antenna dipole 772 SVRCS P25",
    gap=30.0, arm_w=8.0, arm_l=76.0, ladder_n=6, bar_pitch=2.5, bar_gap=0.8, bridge_w=1.2, bar_shift="+22M",
    stitch_x=(22.0, 36.0, 50.0, 64.0), anchor_x=17.0, bridge_ext=0.3, smd_anchor=(1.5, 1.5), mask_pad=(0.9, 0.4),
    tick_every=1, tick_shift=0.0)
