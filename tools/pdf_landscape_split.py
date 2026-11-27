"""Split each page of a (vector) PDF into 4:3 landscape views, cut only at blank gaps.

Each view is the original page with a new MediaBox, so text stays vector. Content below a cut
is painted over with white so a line never shows on two screens. Outlines/links keep working
(they point at the first view of each page).
usage: render first with `pdftoppm -r 150 -gray in.pdf dir/p`, then
       pdf_landscape_split.py in.pdf dir out.pdf   (read it in KOReader rotated to landscape)
"""
import sys, glob, statistics
import numpy as np
from PIL import Image
import pikepdf

src, rdir, dst = sys.argv[1:4]
DPI = 150
K = 72.0 / DPI           # px -> pt
ASPECT = 1236 / 1648     # height / width of the landscape screen
PAD = 6                  # pt margin around content
MIN_GAP = 4              # px blank rows (~2 pt) needed to cut there

files = sorted(glob.glob(rdir + "/*.pgm"))
pages = []
for f in files:
    a = np.asarray(Image.open(f)) < 190
    rows = np.where(a.any(axis=1))[0]
    cols = np.where(a.any(axis=0))[0]
    if len(rows) == 0:
        pages.append(None)
        continue
    pages.append(dict(ink=a.any(axis=1), top=rows[0], bot=rows[-1], left=cols[0], right=cols[-1]))

widths = [p["right"] - p["left"] for p in pages if p]
W_TEXT = float(np.percentile(widths, 90))  # common text-block width in px -> same scale everywhere
print("text width %.1f pt" % (W_TEXT * K))

pdf = pikepdf.open(src)
assert len(pdf.pages) == len(pages)
labels = [pdf.pages[i].label for i in range(len(pdf.pages))]


def gaps(ink, lo, hi):
    """blank runs (start, end) fully inside [lo, hi)"""
    out, start = [], None
    for y in range(max(lo, 0), hi):
        if not ink[y]:
            if start is None:
                start = y
        elif start is not None:
            out.append((start, y))
            start = None
    return out


def plan(p, page_h_px):
    """list of (x0, x1, y0, y1) visible regions in px; box width fixed, 4:3 height."""
    if p is None:
        return [None]
    w = max(W_TEXT, p["right"] - p["left"]) + 2 * PAD / K
    cx = (p["left"] + p["right"]) / 2
    x0, x1 = cx - w / 2, cx + w / 2
    H = w * ASPECT
    pad = PAD / K
    views, top = [], p["top"] - pad
    while True:
        if p["bot"] + pad <= top + H:
            views.append((x0, x1, top, top + H, None))
            return views
        limit = int(top + H - pad)
        # prefer a cut that lets the rest fit on one more screen, then the biggest gap
        lo = int(max(p["bot"] + pad - H, top + H * 0.5))
        cand = [g for g in gaps(p["ink"], lo, limit) if g[1] - g[0] >= MIN_GAP]
        if not cand:
            cand = [g for g in gaps(p["ink"], int(top + H * 0.35), limit) if g[1] - g[0] >= MIN_GAP]
        if not cand:  # something taller than a screen: show it whole, scaled down
            views.append((x0, x1, top, top + H, "tall"))
            # grow this view to the next gap below
            nxt = [g for g in gaps(p["ink"], limit, int(p["bot"]) + 1) if g[1] - g[0] >= MIN_GAP]
            cut = nxt[0][0] if nxt else p["bot"] + pad
            views[-1] = (x0, x1, top, cut, "tall")
            if not nxt:
                return views
            top = nxt[0][1] - pad
            continue
        g = max(cand, key=lambda g: (g[1] - g[0], g[0]))
        cut = (g[0] + g[1]) / 2
        views.append((x0, x1, top, top + H, cut))
        top = g[1] - pad


def to_box(view, mb):
    x0, x1, y0, y1, cut = view
    ph = float(mb[3])
    if cut == "tall":  # widen to keep 4:3 for a region taller than a screen
        h = (y1 - y0)
        w = h / ASPECT
        cx = (x0 + x1) / 2
        x0, x1, cut = cx - w / 2, cx + w / 2, None
    return [x0 * K, ph - y1 * K, x1 * K, ph - y0 * K], (None if cut is None else ph - cut * K)


plans = []
for i, p in enumerate(pages):
    plans.append(plan(p, None))

nviews = sum(len(v) for v in plans)
print("pages", len(pages), "-> views", nviews,
      "| per page:", {n: sum(1 for v in plans if len(v) == n) for n in sorted(set(map(len, plans)))},
      "| tall views:", sum(1 for v in plans for x in v if x and x[4] == "tall"))

# build: insert copies from the end so indices stay valid
new_labels = []
for i in range(len(pdf.pages) - 1, -1, -1):
    views = plans[i]
    base = pdf.pages[i]
    mb = [float(v) for v in base.MediaBox]
    for k in range(len(views) - 1, 0, -1):
        pdf.pages.insert(i + 1, base)
    for k, view in enumerate(views):
        pg = pdf.pages[i + k]
        for key in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
            if key in pg.obj:
                del pg.obj[key]
        if view is None:
            continue
        box, cut = to_box(view, mb)
        pg.obj.MediaBox = pikepdf.Array(box)
        if cut is not None:
            # white out everything below the cut (it is shown on the next screen)
            pg.contents_add(pdf.make_stream(b"q\n"), prepend=True)
            pg.contents_add(pdf.make_stream(
                b"\nQ q 1 g %.2f %.2f %.2f %.2f re f Q\n" % (box[0] - 1, box[1] - 1, box[2] - box[0] + 2, cut - box[1] + 1)))
        # keep only links that are visible on this view
        if "/Annots" in pg.obj:
            vis_lo = cut if cut is not None else box[1]
            keep = pikepdf.Array([a for a in pg.obj.Annots
                                  if "/Rect" in a and float(a.Rect[3]) > vis_lo and float(a.Rect[1]) < box[3]])
            pg.obj.Annots = keep
    lab = labels[i]
    new_labels[:0] = [lab if k == 0 else "%s.%d" % (lab, k + 1) for k in range(len(views))]

nums = pikepdf.Array()
for idx, lab in enumerate(new_labels):
    nums.append(idx)
    nums.append(pikepdf.Dictionary(P=pikepdf.String(lab)))
pdf.Root.PageLabels = pikepdf.Dictionary(Nums=nums)
pdf.save(dst)
print("saved", dst, len(pdf.pages), "pages")
