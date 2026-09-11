"""Audit vias against pads and tracks of other nets (KiCad python): python3 viacheck.py board.kicad_pcb.
DRC only flags a via inside a pad of ANOTHER net; a via inside a pad of its own net passes DRC but hurts
solderability, and a via dropped onto a track of another net gets that net propagated onto it at zone fill."""
import sys, math, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); mm = pcbnew.ToMM
pads = [(p, p.GetBoundingBox()) for fp in b.GetFootprints() for p in fp.Pads()]
segs = [t for t in b.Tracks() if t.GetClass() == "PCB_TRACK"]
vias = [t for t in b.Tracks() if t.GetClass() == "PCB_VIA"]
def seg_dist(c, s):
    a, e = s.GetStart(), s.GetEnd(); ax, ay, ex, ey = a.x, a.y, e.x, e.y; px, py = c.x, c.y
    dx, dy = ex - ax, ey - ay; L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
hits = 0
for v in vias:
    c = v.GetPosition(); r = pcbnew.FromMM(0.3)
    for p, bb in pads:
        if p.GetNumber() == "": continue                                              # unnumbered paste/mask apertures (no copper)
        if p.GetNetname() == v.GetNetname() and p.GetNumber() == "9": continue    # the deliberate paddle via
        if bb.GetLeft() - r < c.x < bb.GetRight() + r and bb.GetTop() - r < c.y < bb.GetBottom() + r:
            hits += 1; print(f"  via {v.GetNetname()} ({mm(c.x):.2f},{mm(c.y):.2f}) touches pad {p.GetParentFootprint().GetReference()}.{p.GetNumber()} [{p.GetNetname()}]")
    for s in segs:
        if s.GetNetname() == v.GetNetname(): continue
        if seg_dist(c, s) < r + s.GetWidth() / 2 + pcbnew.FromMM(0.2):
            hits += 1; print(f"  via {v.GetNetname()} ({mm(c.x):.2f},{mm(c.y):.2f}) within 0.2 of track [{s.GetNetname()}] at ({mm(s.GetStart().x):.2f},{mm(s.GetStart().y):.2f})")
print(f"{sys.argv[1].split('/')[-1]}: {len(vias)} vias, {hits} via/pad or via/track problems")
