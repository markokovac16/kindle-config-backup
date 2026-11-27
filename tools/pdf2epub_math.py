"""LaTeX PDF -> reflowable EPUB that keeps every equation exactly as printed.

Body text (CM-Super "SF*" fonts) becomes real text; inline math becomes small images aligned
on the text baseline (height in em, so they scale with the font size); anything that isn't a
plain text line (display math, figures, tables, odd layouts) becomes an exact image crop.
Every page is checked: all ink must be covered by an emitted text line or image.

usage: pdf2epub_math.py in.pdf out.epub --title T --author A --header-max PT --footer-min PT
       [--pages a-b] (test a page range)
"""
import argparse, hashlib, html, io, os, re, statistics, sys, uuid, zipfile, collections
import numpy as np
import fitz
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--title", required=True); ap.add_argument("--author", required=True)
ap.add_argument("--header-max", type=float, required=True, help="running header lives above this y (pt)")
ap.add_argument("--footer-min", type=float, required=True, help="page number lives below this y (pt)")
ap.add_argument("--pages", default=None)
ap.add_argument("--zoom", type=float, default=4.0)
ap.add_argument("--report", default=None)
A = ap.parse_args()

Z = A.zoom
INK = 170
doc = fitz.open(A.src)
PH = doc[0].rect.height
p_from, p_to = 0, len(doc) - 1
if A.pages:
    a, b = A.pages.split("-"); p_from, p_to = int(a) - 1, int(b) - 1

LIG = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
OK_EXTRA = set("’‘“”–—…•·°§¶†‡€£©®™«»¡¿×÷±µ½¼¾")


def ok_char(c):
    o = ord(c)
    return (32 <= o < 127) or (160 <= o < 0x250 and o not in (0xAD,)) or c in OK_EXTRA or c in LIG


def is_text_font(f):
    return f.split("+")[-1].startswith("SF")


def style_of(f):
    f = f.split("+")[-1]
    return dict(b=f[:4] in ("SFBX", "SFSX", "SFBI", "SFXI") or "Bold" in f,
                i=f[:4] in ("SFTI", "SFSI", "SFSL", "SFBI", "SFXI", "SFIT", "SFSO"),
                tt=f.startswith("SFTT") or f.startswith("SFIT") or f.startswith("SFST"),
                sc=f.startswith("SFCC"))


# ---------- pass 0: body font size ----------
cnt = collections.Counter()
for pno in range(min(len(doc), 40), min(len(doc), 140)):
    for b in doc[pno].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if is_text_font(s["font"]):
                    cnt[round(s["size"], 1)] += len(s["text"])
BODY = cnt.most_common(1)[0][0]
print("body size", BODY)

imgs = {}          # hash -> (name, bytes)
report = []


MATH_SCALE = 1.2   # Kindle reading fonts are bigger/bolder than CM: enlarge math to match


def save_png(arr):
    from PIL import ImageFilter
    arr = np.where(arr > 215, 255, arr).astype(np.uint8)              # drop light box shading
    im = Image.fromarray(arr).filter(ImageFilter.MinFilter(3))       # thicken thin CM strokes
    im = im.point(lambda v: int(255 * (v / 255) ** 1.6))              # darker anti-aliasing
    im = im.quantize(16, dither=Image.Dither.NONE) if hasattr(Image, "Dither") else im.quantize(16)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); data = buf.getvalue()
    h = hashlib.sha1(data).hexdigest()[:16]
    if h not in imgs:
        imgs[h] = ("i%s.png" % h, data)
    return imgs[h][0], arr.shape[1], arr.shape[0]


def crop(gray, x0, y0, x1, y1):
    X0, Y0 = max(0, int(x0 * Z)), max(0, int(y0 * Z))
    X1, Y1 = min(gray.shape[1], int(np.ceil(x1 * Z))), min(gray.shape[0], int(np.ceil(y1 * Z)))
    return gray[Y0:Y1, X0:X1], (X0, Y0, X1, Y1)


def strip_foreign(gray, box, size):
    """copy of the crop with ink that mainly belongs to neighbouring text (an 'f' hook reaching
    into the math box) whitened: components seeded on the left/right crop edge that have more
    pixels outside the crop than inside"""
    X0, Y0, X1, Y1 = box
    pad = int(0.6 * size * Z)
    WX0, WX1 = max(0, X0 - pad), min(gray.shape[1], X1 + pad)
    win = gray[Y0:Y1, WX0:WX1] < 235
    h, w = win.shape
    cx0, cx1 = X0 - WX0, X1 - WX0
    seen = np.zeros_like(win)
    out = gray[Y0:Y1, X0:X1].copy()
    for col in (cx0, cx1 - 1):
        if col < 0 or col >= w:
            continue
        for r0 in range(h):
            if not win[r0, col] or seen[r0, col]:
                continue
            stack, comp = [(r0, col)], []
            seen[r0, col] = True
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < h and 0 <= cc < w and win[rr, cc] and not seen[rr, cc]:
                            seen[rr, cc] = True
                            stack.append((rr, cc))
            inside = [(r, c) for r, c in comp if cx0 <= c < cx1]
            if len(comp) - len(inside) > len(inside):
                for r, c in inside:
                    out[r, c - cx0] = 255
    return out


items = []   # flat stream: dicts with kind text/img/pagebreak/anchor


def process_page(pno):
    page = doc[pno]
    H, W = page.rect.height, page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(Z, Z), colorspace=fitz.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    ink = gray < INK
    covered = np.zeros_like(ink)

    chars = []
    for b in page.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                for c in s["chars"]:
                    if c["c"].isspace():
                        continue
                    x0, y0, x1, y1 = c["bbox"]
                    chars.append(dict(c=c["c"], f=s["font"], size=s["size"], x0=x0, y0=y0, x1=x1, y1=y1,
                                      ox=c["origin"][0], oy=c["origin"][1], text=is_text_font(s["font"])))
    for c in chars:
        if c["text"] or not ("CMEX" in c["f"] or c["c"] == "√"):
            continue
        w = c["x1"] - c["x0"]
        X0, X1 = int((c["x0"] + 0.2 * w) * Z), max(int((c["x0"] + 0.2 * w) * Z) + 1, int((c["x1"] - 0.2 * w) * Z))
        r = int((c["oy"] - 0.04 * c["size"]) * Z)   # these glyphs hang from their origin
        rmax = min(ink.shape[0], int((c["oy"] + 4 * c["size"]) * Z))
        while r < int((c["oy"] + 1.0 * c["size"]) * Z) and r < rmax and not ink[r, X0:X1].any():
            r += 1
        if r >= rmax or not ink[r, X0:X1].any():
            continue
        top, gap = r, 0
        while r + 1 < rmax and gap <= 1:
            r += 1
            gap = 0 if ink[r, X0:X1].any() else gap + 1
        c["y0"], c["y1"] = top / Z, (r - gap + 1) / Z

    # accents (hat, tilde, bar, dot, vector arrow) have advance boxes wider than their ink and
    # reach over the next letter: shrink them to the ink above x-height
    for c in chars:
        if c["text"] or c["c"] not in "ˆˇ˜¯˙¨´`˘\u20d7\u0302\u0303\u0304\u0307":
            continue
        ra, rb = int(c["y0"] * Z), int((c["oy"] - 0.5 * c["size"]) * Z)
        Xa, Xb = int(c["x0"] * Z), int(np.ceil(c["x1"] * Z))
        if rb <= ra or Xb <= Xa:
            continue
        colink = ink[ra:rb, Xa:Xb].any(axis=0)
        idx = np.where(colink)[0]
        if len(idx) == 0:
            continue
        mid = (Xb - Xa) // 2
        # contiguous run of ink columns nearest the box centre
        runs, st = [], idx[0]
        for a, b in zip(idx, idx[1:]):
            if b - a > 1:
                runs.append((st, a)); st = b
        runs.append((st, idx[-1]))
        a, b = min(runs, key=lambda r: 0 if r[0] <= mid <= r[1] else min(abs(r[0] - mid), abs(r[1] - mid)))
        c["x0"], c["x1"] = (Xa + a) / Z, (Xa + b + 1) / Z

    def is_bg(d):
        f = d.get("fill")
        return f is not None and min(f) > 0.75 and d["rect"].height > 1.5 * BODY and not d.get("color")
    draws = [d["rect"] for d in page.get_drawings() if not is_bg(d)]
    pimgs = [fitz.Rect(i["bbox"]) for i in page.get_image_info()]

    # header / footer zones: drop only if what's there looks like a running header / page number
    def zone_ok(cs):
        return all(c["text"] and c["size"] <= BODY * 1.05 for c in cs)
    hdr = [c for c in chars if c["y1"] <= A.header_max + 1]
    ftr = [c for c in chars if c["y0"] >= A.footer_min - 1]
    top_cut = A.header_max if hdr and zone_ok(hdr) and not any(c["y0"] < A.header_max < c["y1"] for c in chars) else 0
    if top_cut == 0 and not hdr:
        top_cut = 0
    bot_cut = A.footer_min if ftr and zone_ok(ftr) and all(c["c"].isalnum() for c in ftr) else H
    if top_cut:
        covered[: int(top_cut * Z) + 1, :] = True
        # header rule just under the header text
        for r in draws:
            if r.y1 <= top_cut + 6 and r.height < 2:
                covered[: int((r.y1 + 1.5) * Z), :] = True
                top_cut = max(top_cut, r.y1 + 1.5)
    if bot_cut < H:
        covered[int(bot_cut * Z):, :] = True
    chars = [c for c in chars if c["y0"] >= top_cut - 0.5 and c["y1"] <= bot_cut + 0.5 or
             (top_cut - 0.5 <= (c["y0"] + c["y1"]) / 2 <= bot_cut + 0.5)]
    chars = [c for c in chars if top_cut <= (c["y0"] + c["y1"]) / 2 <= bot_cut]

    # ---- figures/tables with text running beside them: cut out as their own image ----
    sides = []
    gray_m = gray
    sf = [c for c in chars if c["text"]]
    if sf:
        tl, tr = min(c["x0"] for c in sf), max(c["x1"] for c in sf)
        rects = [fitz.Rect(r) for r in pimgs] + [fitz.Rect(r) for r in draws if not (r.height < 1.5 and r.width < 3 * BODY)]
        rects = [r for r in rects if r.y0 >= top_cut and r.y1 <= bot_cut]
        groups = []
        for r in rects:
            r = fitz.Rect(r)
            merged_any = True
            while merged_any:
                merged_any = False
                for g in groups:
                    if fitz.Rect(g.x0 - 6, g.y0 - 1.5 * BODY, g.x1 + 6, g.y1 + 1.5 * BODY).intersects(r):
                        r |= g; groups.remove(g); merged_any = True; break
            groups.append(r)
        for g in groups:
            if g.width > 0.65 * (tr - tl) or g.width < 3 * BODY:
                continue
            if g.height < 1.5 * BODY:
                # only rules: a table at the side has several rules of the same width
                if not (g.x0 > tl + 0.3 * (tr - tl) or g.x1 < tr - 0.3 * (tr - tl)):
                    continue
                same = [r for r in rects if r.height < 1.5 and abs(r.x0 - g.x0) < 2 and abs(r.x1 - g.x1) < 2
                        and abs(r.y0 - g.y0) < 15 * BODY]
                if len(same) < 2:
                    continue
            right_side = (g.x0 + g.x1) / 2 > (tl + tr) / 2
            c0, c1 = (g.x0 - 6, W) if right_side else (0, g.x1 + 6)
            # grow the column vertically through its own ink (labels, caption)
            Xa, Xb = int(max(0, c0) * Z), int(min(W, c1) * Z)
            colrows = ink[:, Xa:Xb].any(axis=1)
            ya, yb = int(g.y0 * Z), int(g.y1 * Z)
            lim0, lim1 = int(top_cut * Z) + 1, int(bot_cut * Z) - 1
            gapmax = int(1.2 * BODY * Z)
            k, gap = ya, 0
            while k - 1 > lim0 and gap < gapmax:
                k -= 1; gap = 0 if colrows[k] else gap + 1
            ya = k + gap
            k, gap = yb, 0
            while k + 1 < lim1 and gap < gapmax:
                k += 1; gap = 0 if colrows[k] else gap + 1
            yb = k - gap
            # full-width lines (a display equation under the figure) end the column
            bnd = c0 if right_side else c1
            def crosses(c):
                if c["x0"] < bnd < c["x1"]:
                    return True
                # above/below the figure, ink right next to the boundary means a line running across
                if not c["text"] and (c["y1"] <= g.y0 + 0.5 or c["y0"] >= g.y1 - 0.5):
                    return (bnd - BODY < c["x1"] <= bnd) if right_side else (bnd <= c["x0"] < bnd + BODY)
                return False
            strad = [c for c in chars if crosses(c) and ya / Z <= (c["y0"] + c["y1"]) / 2 <= (yb + 1) / Z]
            above = [c["y1"] for c in strad if c["y1"] <= g.y0 + 0.5]
            below = [c["y0"] for c in strad if c["y0"] >= g.y1 - 0.5]
            if len(above) + len(below) < len(strad):
                continue  # something runs across the figure itself
            # cut inside a blank gap of the column, so nothing (a fraction's numerator) is split
            if above:
                k = min(yb, int(np.ceil(max(above) * Z)))
                while k < yb and colrows[k]:
                    k += 1
                while k < yb and not colrows[k]:
                    k += 1
                ya = max(ya, k)
            if below:
                k = max(ya, int(min(below) * Z))
                while k > ya and colrows[k]:
                    k -= 1
                while k > ya and not colrows[k]:
                    k -= 1
                yb = min(yb, k)
            if yb - ya < 1.5 * BODY * Z:
                continue
            y0s, y1s = ya / Z, (yb + 1) / Z
            inside = lambda c: y0s <= (c["y0"] + c["y1"]) / 2 <= y1s
            beside = [c for c in sf if inside(c) and c["c"].isalpha() and (c["x1"] < c0 if right_side else c["x0"] > c1)]
            straddle = [c for c in chars if inside(c) and c["x0"] < (c0 if right_side else c1) < c["x1"]]
            if len(beside) < 20 or straddle:
                continue
            # the text beside must be running prose, not other columns of a table
            per_line = collections.Counter(round(c["oy"]) for c in beside)
            if sum(1 for v in per_line.values() if v >= 15) < 2:
                continue
            cols = np.where(ink[ya:yb + 1, Xa:Xb].any(axis=0))[0]
            if len(cols) == 0:
                continue
            fx0, fx1 = (Xa + cols[0]) / Z - 1, (Xa + cols[-1] + 1) / Z + 1
            arr, (X0, Yc0, X1, Yc1) = crop(gray, fx0, y0s - 1, fx1, y1s + 1)
            covered[Yc0:Yc1, X0:X1] = True
            name, w, h = save_png(arr)
            loc = max(c["x1"] for c in beside) if right_side else min(c["x0"] for c in beside)
            sides.append(dict(kind="img", name=name, w_pt=w / Z, h_pt=h / Z, y0=y0s, y1=y1s, x0=fx0, x1=fx1,
                              pu=1.0, pd=1.0, page=pno, side=(right_side, loc)))
            if gray_m is gray:
                gray_m = gray.copy()
            gray_m[Yc0:Yc1, X0:X1] = 255
            ink[Yc0:Yc1, X0:X1] = False
            chars = [c for c in chars if not (inside(c) and (c["x0"] >= c0 if right_side else c["x1"] <= c1))]
            draws = [r for r in draws if not fitz.Rect(c0, y0s - 1, c1, y1s + 1).contains(r)]
            pimgs = [r for r in pimgs if not fitz.Rect(c0, y0s - 1, c1, y1s + 1).contains(r)]
    gray_c = gray
    gray = gray_m

    # ---- bands from the ink profile ----
    r0, r1 = int(top_cut * Z) + 1, int(bot_cut * Z) - 1
    rows = ink[r0:r1].any(axis=1)
    G = max(4, int(round(0.10 * BODY * Z)))
    bands, start, blank = [], None, 0
    for i, v in enumerate(rows):
        y = r0 + i
        if v:
            if start is None:
                start = y
            last = y; blank = 0
        elif start is not None:
            blank += 1
            if blank >= G:
                bands.append([start, last]); start = None
    if start is not None:
        bands.append([start, last])
    # band -> pt + contents
    B = []
    for (a, b) in bands:
        y0, y1 = a / Z, (b + 1) / Z
        cs = [c for c in chars if y0 - 0.3 <= (c["y0"] + c["y1"]) / 2 <= y1 + 0.3]
        B.append(dict(y0=y0, y1=y1, chars=cs))
    # merge fragments (accents/arrows/rules/limits with no real line of their own) into a neighbour
    changed = True
    while changed and len(B) > 1:
        changed = False
        for k, bd in enumerate(B):
            frag = (bd["y1"] - bd["y0"] < 0.55 * BODY) and not any(c["text"] for c in bd["chars"])
            if not frag:
                continue
            up = bd["y0"] - B[k - 1]["y1"] if k > 0 else 1e9
            dn = B[k + 1]["y0"] - bd["y1"] if k + 1 < len(B) else 1e9
            if min(up, dn) > 0.8 * BODY:
                continue
            Yf0, Yf1 = int(bd["y0"] * Z), int(np.ceil(bd["y1"] * Z))
            fc = np.where(ink[Yf0:Yf1].any(axis=0))[0]
            fx0, fx1 = fc[0] / Z - 1, fc[-1] / Z + 1

            def over(o):
                return any(c["x0"] < fx1 and c["x1"] > fx0 for c in o["chars"])
            cand = [j for j, d in ((k + 1, dn), (k - 1, up)) if 0 <= j < len(B) and d <= 0.8 * BODY]
            ov = [j for j in cand if over(B[j])]
            j = ov[0] if ov else (k - 1 if up < dn else k + 1)
            o = B[j]
            o["y0"], o["y1"] = min(o["y0"], bd["y0"]), max(o["y1"], bd["y1"])
            o["chars"] = sorted(o["chars"] + bd["chars"], key=lambda c: c["x0"])
            del B[k]; changed = True
            break

    # split bands holding several text lines at a blank row between their baselines
    def baselines(cs):
        tx = sorted((c for c in cs if c["text"] and c["c"].isalpha()), key=lambda c: c["oy"])
        groups = []
        for c in tx:
            if groups and c["oy"] - groups[-1][-1]["oy"] < 0.3 * c["size"]:
                groups[-1].append(c)
            else:
                groups.append([c])
        return [(statistics.median(x["oy"] for x in g), statistics.median(x["size"] for x in g)) for g in groups if len(g) >= 3]

    def split(bd):
        bl = baselines(bd["chars"])
        if len(bl) < 2:
            return [bd]
        for (b1, s1), (b2, s2) in zip(bl, bl[1:]):
            lo, hi = int((b1 + 0.12 * s1) * Z), int((b2 - 0.62 * s2) * Z)
            if hi <= lo:
                continue
            prof = ink[lo:hi + 1].sum(axis=1)
            zeros = np.where(prof == 0)[0]
            if len(zeros) == 0:
                continue
            # first blank row under the upper line: accents/arrows belong to the line below
            y = (lo + zeros[0] + 0.5) / Z
            a = dict(y0=bd["y0"], y1=y, chars=[c for c in bd["chars"] if (c["y0"] + c["y1"]) / 2 < y])
            b = dict(y0=y, y1=bd["y1"], chars=[c for c in bd["chars"] if (c["y0"] + c["y1"]) / 2 >= y])
            # trim to ink
            for part in (a, b):
                Y0, Y1 = int(part["y0"] * Z), int(np.ceil(part["y1"] * Z))
                rr = np.where(ink[Y0:Y1].any(axis=1))[0]
                if len(rr):
                    part["y0"], part["y1"] = (Y0 + rr[0]) / Z, (Y0 + rr[-1] + 1) / Z
            return split(a) + split(b)
        return [bd]
    B = [x for bd in B for x in split(bd)]
    for k, bd in enumerate(B):
        bd["pu"] = min(1.0, (bd["y0"] - B[k - 1]["y1"]) / 2) if k > 0 else 1.0
        bd["pd"] = min(1.0, (B[k + 1]["y0"] - bd["y1"]) / 2) if k + 1 < len(B) else 1.0

    # text block edges for this page
    xs0 = [c["x0"] for c in chars if c["text"]]
    xs1 = [c["x1"] for c in chars if c["text"]]
    left = min(xs0) if xs0 else 0
    right = max(xs1) if xs1 else W
    lefts = collections.Counter(round(min(c["x0"] for c in bd["chars"])) for bd in B if bd["chars"])
    if lefts:
        left = min(left, lefts.most_common(1)[0][0]) if lefts.most_common(1)[0][1] >= 2 else left

    out = []
    for bd in B:
        line = classify(bd, draws, pimgs, left, right, gray)
        if line is None:
            # block image: from the text-block left edge (keeps centering/alignment) to the ink's right
            y0, y1 = bd["y0"], bd["y1"]
            Y0, Y1 = int(y0 * Z), int(np.ceil(y1 * Z))
            cols = np.where(ink[Y0:Y1].any(axis=0))[0]
            if len(cols) == 0:
                continue
            ix0, ix1 = cols[0] / Z, (cols[-1] + 1) / Z
            x0 = min(ix0, left) - 1.0
            x1 = ix1 + 1.0
            arr, (X0, Yc0, X1, Yc1) = crop(gray, x0, y0 - bd["pu"], x1, y1 + bd["pd"])
            covered[Yc0:Yc1, X0:X1] = True
            name, w, h = save_png(arr)
            out.append(dict(kind="img", name=name, w_pt=w / Z, h_pt=h / Z, y0=y0, y1=y1, x0=ix0, x1=ix1, pu=bd["pu"], pd=bd["pd"],
                            left=left, right=right, page=pno))
        else:
            for (X0, Yc0, X1, Yc1) in line.pop("cover"):
                covered[Yc0:Yc1, X0:X1] = True
            line.update(kind="text", page=pno, left=left, right=right)
            for sd in sides:
                lh = 1.3 * line["size"]
                clear = line["x1"] < sd["x0"] if sd["side"][0] else line["x0"] > sd["x1"]
                if sd["y0"] - 2 <= line["base"] <= sd["y1"] + 2 or (clear and sd["y0"] - lh <= line["base"] <= sd["y1"] + lh):
                    if sd["side"][0]:
                        line["right"] = sd["side"][1]
                    else:
                        line["left"] = sd["side"][1]
            out.append(line)
    for sd in sides:
        k = 0
        while k < len(out) and out[k]["y1"] <= sd["y0"] + 2:
            k += 1
        out.insert(k, sd)
    # merge consecutive block images that are close (multi-line displays keep their alignment)
    merged = []
    for it in out:
        if (it["kind"] == "img" and merged and merged[-1]["kind"] == "img" and "side" not in it
                and "side" not in merged[-1] and it["y0"] - merged[-1]["y1"] < 1.0 * BODY):
            m = merged[-1]
            x0 = min(m["x0"], it["x0"], left) - 1.0
            x1 = max(m["x1"], it["x1"]) + 1.0
            arr, _ = crop(gray, x0, m["y0"] - m["pu"], x1, it["y1"] + it["pd"])
            m["pd"] = it["pd"]
            name, w, h = save_png(arr)
            m.update(name=name, w_pt=w / Z, h_pt=h / Z, y1=it["y1"], x0=min(m["x0"], it["x0"]), x1=max(m["x1"], it["x1"]))
        else:
            merged.append(it)
    # footnotes: a short rule at the left in the lower half, with only small text below it
    fn_y = None
    for r in draws:
        if r.height < 1.2 and 0.15 * (right - left) < r.width < 0.5 * (right - left) and abs(r.x0 - left) < 3 and r.y0 > H * 0.45:
            below = [it for it in merged if it["y0"] > r.y1 - 0.5]
            txt = [it for it in below if it["kind"] == "text"]
            if txt and all(it["size"] < BODY * 0.93 for it in txt):
                fn_y = r.y1
                covered[int((r.y0 - 1) * Z):int(np.ceil((r.y1 + 1) * Z)), int((r.x0 - 1) * Z):int(np.ceil((r.x1 + 1) * Z))] = True
                break
    if fn_y is not None:
        keep = []
        for it in merged:
            if it["y1"] <= fn_y + 0.5 and it["y0"] >= fn_y - 2.5 and it["kind"] == "img" and it["h_pt"] < 4:
                continue  # the rule itself
            if it["y0"] > fn_y - 0.5:
                it["fn"] = True
            keep.append(it)
        merged = keep
    # coverage check
    left_ink = int((ink & ~covered).sum())
    ntext = sum(1 for i in merged if i["kind"] == "text"); nimg = len(merged) - ntext
    report.append((pno, page.get_label() or str(pno + 1), ntext, nimg, left_ink))
    if left_ink > 30:
        ys, xs = np.where(ink & ~covered)
        print("  !! page %d (%s): %d uncovered ink px, bbox pt x %.1f-%.1f y %.1f-%.1f" % (
            pno + 1, page.get_label(), left_ink, xs.min() / Z, xs.max() / Z, ys.min() / Z, ys.max() / Z))
    return merged


def classify(bd, draws, pimgs, left, right, gray):
    """return a text line dict, or None -> block image"""
    cs = sorted(bd["chars"], key=lambda c: c["x0"])
    tx = [c for c in cs if c["text"]]
    if len([c for c in tx if c["c"].isalpha()]) < 3:
        return None
    rect = fitz.Rect(left - 2, bd["y0"], right + 2, bd["y1"])
    if any(r.intersects(rect) for r in pimgs):
        return None
    # baseline from text chars of the dominant size
    sizes = collections.Counter(round(c["size"], 1) for c in tx)
    size = sizes.most_common(1)[0][0]
    main = [c for c in tx if round(c["size"], 1) == size]
    base = statistics.median(c["oy"] for c in main)
    # text chars off the baseline (superscripts, a second line) -> treat as math / reject
    for c in tx:
        if abs(c["oy"] - base) > 0.12 * size or c["size"] < 0.9 * size:
            c["text"] = False
    tx = [c for c in cs if c["text"]]
    off = [c for c in cs if not c["text"] and is_text_font(c["f"]) and c["size"] >= 0.9 * size]
    if len([c for c in off if c["c"].isalpha()]) >= 3:
        return None          # two lines of text merged into one band
    if any(not ok_char(c["c"]) for c in tx):
        return None
    if sum(1 for c in tx if c["c"] == ".") >= 6 and re.search(r"\.{4,}|(\. ){4,}", "".join(c["c"] for c in tx)):
        return None          # dot leaders (printed table of contents)
    x_start = min(c["x0"] for c in cs)
    math_frac = 1 - len(tx) / len(cs)
    if x_start > left + 2 * size and math_frac > 0.5:
        return None          # indented display equation that happens to contain words
    if bd["y1"] - bd["y0"] > 3.2 * size:
        return None
    reach = cs[0]["x1"]
    for c in cs[1:]:
        if c["x0"] - reach > 1.8 * size:
            return None      # tabular gap: keep the layout as an image
        reach = max(reach, c["x1"])
    # segments: runs of text chars / math clusters (by x)
    segs = []
    for c in cs:
        kind = "t" if c["text"] else "m"
        if segs and segs[-1]["k"] == kind:
            segs[-1]["c"].append(c)
        else:
            segs.append(dict(k=kind, c=[c]))
    # math must not overlap text horizontally
    for i, s in enumerate(segs):
        s["x0"] = min(c["x0"] for c in s["c"]); s["x1"] = max(c["x1"] for c in s["c"])
    for i, s in enumerate(segs):
        if s["k"] == "m":
            for j in (i - 1, i + 1):
                if 0 <= j < len(segs) and segs[j]["k"] == "t":
                    t = segs[j]
                    if min(s["x1"], t["x1"]) - max(s["x0"], t["x0"]) > 0.6:
                        return None
    # drawings in the band must sit inside a math cluster (fraction bars, roots)
    mranges = [(s["x0"], s["x1"]) for s in segs if s["k"] == "m"]
    for r in draws:
        if r.y1 < bd["y0"] - 0.5 or r.y0 > bd["y1"] + 0.5:
            continue
        inside = any(r.x0 >= a - 4 and r.x1 <= b + 4 for a, b in mranges)
        # a rule that starts in a math cluster and runs over no text (radical bar over a blank)
        tsegs = [(t["x0"], t["x1"]) for t in segs if t["k"] == "t"]
        hangs = (any(a - 1 <= r.x0 <= b + 1 for a, b in mranges)
                 and not any(min(r.x1, b) - max(r.x0, a) > 0.5 for a, b in tsegs))
        if not (inside or hangs):
            return None
        # widen the cluster to the drawing
        for s in segs:
            if s["k"] == "m" and (r.x0 >= s["x0"] - 4 and r.x1 <= s["x1"] + 4 or s["x0"] - 1 <= r.x0 <= s["x1"] + 1):
                s["x0"] = min(s["x0"], r.x0); s["x1"] = max(s["x1"], r.x1)
    # ink just beyond a math cluster (arrow heads, wide accents): grow to the ink, stopping at text
    Y0, Y1 = int(bd["y0"] * Z), int(np.ceil(bd["y1"] * Z))
    inkband = gray[Y0:Y1] < INK
    colink = inkband.any(axis=0)
    for i, s in enumerate(segs):
        if s["k"] != "m":
            continue
        lo = segs[i - 1]["x1"] if i > 0 else left - 4
        hi = segs[i + 1]["x0"] if i + 1 < len(segs) else right + 4
        a, b = int(np.ceil(lo * Z)), int(s["x0"] * Z)
        c = np.where(colink[a:b])[0]
        if len(c):
            s["x0"] = (a + c[0]) / Z
        a, b = int(np.ceil(s["x1"] * Z)), min(len(colink), int(hi * Z))
        c = np.where(colink[a:b])[0]
        if len(c):
            s["x1"] = (a + c[-1] + 1) / Z
    cover = []
    out = []
    prev_x1 = None
    for s in segs:
        gap = (s["x0"] - prev_x1) if prev_x1 is not None else 0
        if prev_x1 is not None and gap > 0.15 * size:
            out.append(("sp",))
        if s["k"] == "t":
            run = []
            last = None
            for c in s["c"]:
                if last is not None and c["x0"] - last["x1"] > 0.15 * size:
                    run.append((" ", None))
                ch = LIG.get(c["c"], c["c"])
                run.append((ch, style_of(c["f"])))
                last = c
            # group by style
            cur, cur_st = "", None
            for ch, st in run:
                if st is None:
                    cur += " "; continue
                if cur_st is not None and st != cur_st:
                    out.append(("t", cur, cur_st)); cur = ""
                cur += ch; cur_st = st
            if cur:
                out.append(("t", cur, cur_st))
            nxt = segs[segs.index(s) + 1]["x0"] if segs.index(s) + 1 < len(segs) else s["x1"] + 0.3 * size
            X0, X1 = int(s["x0"] * Z) - 1, int(np.ceil(min(s["x1"] + 0.3 * size, nxt) * Z)) + 1  # italic overhang
            cover.append((X0, Y0 - 2, X1, Y1 + 2))
        else:
            x0, x1 = s["x0"] - 0.4, s["x1"] + 0.4
            arr, box = crop(gray, x0, bd["y0"] - min(0.5, bd["pu"]), x1, bd["y1"] + min(0.5, bd["pd"]))
            arr = strip_foreign(gray, box, size)
            cover.append(box)
            name, w, h = save_png(arr)
            hpt = h / Z
            out.append(("m", name, MATH_SCALE * hpt / size, MATH_SCALE * ((bd["y1"] + min(0.5, bd["pd"])) - base) / size))
        prev_x1 = s["x1"]
    m = np.zeros_like(inkband)
    for (X0, Yc0, X1, Yc1) in cover:
        m[max(0, Yc0 - Y0):max(0, Yc1 - Y0), max(0, X0):X1] = True
    if int((inkband & ~m).sum()) > 3:
        return None          # something in this line isn't captured -> whole line as an image
    return dict(segs=out, x0=x_start, x1=max(c["x1"] for c in cs), base=base, size=size,
                y0=bd["y0"], y1=bd["y1"], cover=cover,
                bold=all(style_of(c["f"])["b"] for c in tx),
                starts=("".join(LIG.get(c["c"], c["c"]) for c in tx[:4])))


# ---------- run ----------
toc = doc.get_toc(simple=False)
pages_items = {}
for pno in range(p_from, p_to + 1):
    if pno == 0 and not A.pages:
        continue  # cover page -> cover image
    pages_items[pno] = process_page(pno)
    if pno % 50 == 0:
        print("page", pno + 1, "imgs", len(imgs))

# ---------- vocabulary for de-hyphenation ----------
vocab = collections.Counter()
for its in pages_items.values():
    for it in its:
        if it["kind"] == "text":
            txt = "".join(s[1] if s[0] == "t" else " " for s in it["segs"])
            for w in re.findall(r"[A-Za-z][A-Za-z\-]*[A-Za-z]", txt[:-1] if txt.endswith("-") else txt):
                vocab[w.lower()] += 1

# ---------- assemble paragraphs ----------
LABEL = re.compile(r"^(\d+\.|\(\w{1,4}\)|•|[a-z]\)|\[\d+\]|Q\d|E\d|P\d)")


try:
    DICT = set(w.strip().lower() for w in open("/usr/share/dict/words"))
except OSError:
    DICT = set()


def in_dict(w):
    if w in DICT:
        return True
    for suf in ("s", "es", "ed", "d", "ing", "ly", "er", "ers", "ation", "ations"):
        if w.endswith(suf) and (w[: -len(suf)] in DICT or w[: -len(suf)] + "e" in DICT):
            return True
    return False


def keep_hyphen(w1, w2, joined, compound, chain):
    if chain:
        return True                       # length-and-direction, onion-slice-into-...
    if vocab.get(joined, 0) > 0:
        return False                      # the book writes it unbroken elsewhere
    if vocab.get(compound, 0) > 0:
        return True
    if in_dict(joined):
        return False
    return len(w1) >= 3 and len(w2) >= 2 and in_dict(w1.lower()) and in_dict(w2.lower())


def esc(s):
    return html.escape(s, quote=False)


def seg_html(segs):
    o = []
    for s in segs:
        if s[0] == "sp":
            o.append(" ")
        elif s[0] == "t":
            t, st = esc(s[1]), s[2]
            if st["tt"]:
                t = "<code>%s</code>" % t
            if st["sc"]:
                t = '<span class="sc">%s</span>' % t
            if st["i"]:
                t = "<i>%s</i>" % t
            if st["b"]:
                t = "<b>%s</b>" % t
            o.append(t)
        else:
            _, name, hem, dem = s
            o.append('<img class="m" src="img/%s" alt="" style="height:%.3fem;vertical-align:-%.3fem"/>' % (name, hem, dem))
    return "".join(o)


def last_text(segs):
    for s in reversed(segs):
        if s[0] == "t":
            return s[1]
        if s[0] == "m":
            return None
    return None


def lt_raw(segs):
    for s in reversed(segs):
        if s[0] == "t":
            return s[1]
        if s[0] == "m":
            return None
    return None


def first_text(segs):
    for s in segs:
        if s[0] == "t":
            return s[1]
        if s[0] == "m":
            return None
    return None


# toc anchors: (page, y_top) -> ids
anchors = collections.defaultdict(list)
toc_entries = []
for k, e in enumerate(toc):
    lvl, title, pg, dest = e[0], e[1], e[2] - 1, e[3]
    if not (p_from <= pg <= p_to):
        continue
    y = 0
    if dest and dest.get("to") is not None:
        y = PH - dest["to"].y
    aid = "toc%d" % k
    anchors[pg].append((y, aid))
    toc_entries.append((lvl, title, aid))

chapters = []  # list of (title, html list)
cur = []
chapters.append(["Front matter", cur])
para = None    # dict(lines=[...])
blocks = cur
lead = []
for its in pages_items.values():
    ts = [it for it in its if it["kind"] == "text"]
    for a, b in zip(ts, ts[1:]):
        if b["page"] == a["page"] and 0 < b["base"] - a["base"] < 2.2 * a["size"]:
            lead.append(b["base"] - a["base"])
LEAD = statistics.median(lead) if lead else BODY * 1.2
print("leading", LEAD)
page_ids = []


def flush():
    global para
    if para is None:
        emit_fn()
        return
    _flush()
    emit_fn()


def _flush():
    global para
    if para is None:
        return
    ls = para["lines"]
    first = ls[0]
    size = statistics.median(l["size"] for l in ls)
    em = size
    if first["bold"] and size > BODY * 1.12 and len(ls) <= 3:
        lvl = 1 if size > BODY * 1.9 else 2 if size > BODY * 1.35 else 3
        txt = ""
        for l in ls:
            txt += (" " if txt else "") + seg_html(l["segs"])
        blocks.append("<h%d>%s</h%d>" % (lvl, txt, lvl))
        para = None
        return
    ind1 = (first["x0"] - first["left"]) / em
    ind2 = ((ls[1]["x0"] - ls[1]["left"]) / em) if len(ls) > 1 else 0
    style = []
    cls = []
    if len(ls) == 1 and abs((first["x0"] + first["x1"]) / 2 - (first["left"] + first["right"]) / 2) < 1.0 * em and ind1 > 3:
        cls.append("c")
    else:
        if ind2 > 0.3:
            style.append("margin-left:%.2fem" % ind2)
        if abs(ind1 - ind2) > 0.3:
            style.append("text-indent:%.2fem" % (ind1 - ind2))
    if abs(size - BODY) > 0.4:
        style.append("font-size:%.3fem" % (size / BODY))
    # text with de-hyphenation
    out = ""
    for i, l in enumerate(ls):
        h = seg_html(l["segs"])
        for pid in l.get("pids", []):
            h = '<span id="%s"></span>' % pid + h
        if i > 0:
            prev = ls[i - 1]
            lt, ft = last_text(prev["segs"]), first_text(l["segs"])
            if lt and lt.endswith("-") and len(lt) >= 2 and lt[-2].islower() and ft and ft[:1].islower():
                w1m = re.findall(r"([A-Za-z]+-)*[A-Za-z]+-$", lt)
                w1full = re.search(r"([A-Za-z]+-)*[A-Za-z]+-$", lt).group(0) if w1m else ""
                w2full = re.findall(r"^[A-Za-z]+(?:-[A-Za-z]+)*", ft)
                w2full = w2full[0] if w2full else ""
                w1 = w1full[:-1].split("-")[-1] if w1full else ""
                w2 = w2full.split("-")[0]
                joined, compound = (w1 + w2).lower(), (w1 + "-" + w2).lower()
                if keep_hyphen(w1, w2, joined, compound, w1full.count("-") > 1 or "-" in w2full):
                    out += h          # real compound: keep the hyphen
                else:
                    k = out.rfind("-")
                    out = out[:k] + out[k + 1:] + h
                continue
            if lt and (lt.endswith("-") or lt.endswith("—") or lt.endswith("–")) or (ft and ft[:1] in "—–"):
                out += h
            elif lt is None and (lt_raw(prev["segs"]) or "").endswith("-"):
                out += h
            else:
                out += " " + h
        else:
            out += h
    attr = ""
    if cls:
        attr += ' class="%s"' % " ".join(cls)
    if para.get("gap"):
        style.insert(0, "margin-top:0.6em")
    if style:
        attr += ' style="%s"' % ";".join(style)
    blocks.append("<p%s>%s</p>" % (attr, out))
    para = None


fn_buf = []


def emit_fn():
    global fn_buf
    for kind, h in fn_buf:
        blocks.append(h)
    fn_buf = []


prev = None
for pno, its in pages_items.items():
    pids = ["pg%d" % pno]
    page_ids.append((pids[0], doc[pno].get_label() or str(pno + 1)))
    anc = sorted(anchors.get(pno, []))
    first_on_page = True
    fns = [it for it in its if it.get("fn")]
    its = [it for it in its if not it.get("fn")]
    if fns:
        fl = []
        for it in fns:
            if it["kind"] == "img":
                fl.append('<div class="d fn"><img src="img/%s" alt="" style="width:%.2fem"/></div>' % (it["name"], MATH_SCALE * it["w_pt"] / BODY))
            else:
                if fl and fl[-1][0] == "t" and not LABEL.match(it["starts"]) and not it["segs"][0][0] == "m" and it["x0"] <= it["left"] + 1 and False:
                    pass
                fl.append(("t", it))
        # group footnote text lines into paragraphs: a new footnote starts with its marker (indented)
        html_fn, cur_l = [], []
        def fn_flush():
            if cur_l:
                html_fn.append('<p class="fn">%s</p>' % " ".join(seg_html(l["segs"]) for l in cur_l))
                cur_l.clear()
        for x in fl:
            if isinstance(x, str):
                fn_flush(); html_fn.append(x)
            else:
                l = x[1]
                if cur_l and l["x0"] > cur_l[-1]["x0"] + 2:
                    fn_flush()
                cur_l.append(l)
        fn_flush()
        fn_buf.extend(("fn", h) for h in html_fn)
    for it in its:
        # toc anchors that start before this item
        while anc and anc[0][0] <= it["y0"] + 3:
            y, aid = anc.pop(0)
            lvl = next(l for l, t, a in toc_entries if a == aid)
            if lvl == 1:
                flush()
                blocks = []
                chapters.append([next(t for l, t, a in toc_entries if a == aid), blocks])
                prev = None
            flush() if para else None
            blocks.append('<a id="%s"></a>' % aid)
            prev = None
        if it["kind"] == "img" and "side" in it:
            # figure beside running text: show it after the paragraph instead of splitting it
            fn_buf.append(("side", '<div class="d"><img src="img/%s" alt="" style="width:%.2fem"/></div>'
                           % (it["name"], MATH_SCALE * it["w_pt"] / BODY)))
            continue
        if it["kind"] == "img":
            flush()
            ids = "".join('<span id="%s"></span>' % p for p in pids); pids = []
            blocks.append('<div class="d">%s<img src="img/%s" alt="" style="width:%.2fem"/></div>'
                          % (ids, it["name"], MATH_SCALE * it["w_pt"] / BODY))
            prev = None
        else:
            it["pids"] = pids; pids = []
            new = True
            if para is not None and prev is not None:
                p0 = para["lines"][0]
                gap_ok = (it["page"] != prev["page"]) or (it["base"] - prev["base"] < 1.45 * LEAD)
                full = prev["x1"] > prev["right"] - 1.5 * prev["size"]
                label = bool(LABEL.match(it["starts"]))
                ind = it["x0"] > prev["x0"] + 0.5 * it["size"]
                in_list = bool(LABEL.match(p0["starts"])) and abs(it["x0"] - (para["lines"][1]["x0"] if len(para["lines"]) > 1 else it["x0"])) < 1.0
                if ind and LABEL.match(p0["starts"]) and len(para["lines"]) == 1:
                    ind = False   # continuation of a list item
                elif ind and in_list:
                    ind = False
                same = abs(it["size"] - prev["size"]) < 0.4
                if gap_ok and full and not label and not ind and same:
                    new = False
            if new:
                g = (prev is not None and it["page"] == prev["page"] and it["base"] - prev["base"] > 1.45 * LEAD)
                flush()
                para = dict(lines=[], gap=g)
            para["lines"].append(it)
            prev = it
    if pids:
        flush()
        blocks.append("".join('<span id="%s"></span>' % p for p in pids))
flush()
emit_fn()

# ---------- write EPUB ----------
CSS = """body{margin:0}
p{margin:0;text-align:justify}
p.c{text-align:center;text-indent:0}
h1,h2,h3{text-align:left;margin:1em 0 0.4em 0;page-break-after:avoid}
h1{font-size:1.6em}h2{font-size:1.3em}h3{font-size:1.1em}
div.d{margin:0.3em 0;text-indent:0;text-align:left}
div.d img{max-width:100%}
img.m{max-width:100%}
p.fn{font-size:0.8em;text-indent:0;margin:0.2em 0 0.2em 0;border-top:1px solid #888;padding-top:0.15em}
p.fn+p.fn{border-top:none;padding-top:0}
div.fn{margin:0.1em 0}
code{font-family:monospace}
span.sc{font-variant:small-caps}
"""
bookid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, A.title))
files = []
for k, (title, bl) in enumerate(chapters):
    if not bl:
        continue
    name = "c%03d.xhtml" % k
    body = "\n".join(bl)
    x = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
         'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>%s</title>'
         '<link rel="stylesheet" href="style.css"/></head><body>\n%s\n</body></html>' % (esc(title), body))
    files.append((name, title, x))
loc = {}
for name, _, x in files:
    for m in re.finditer(r'id="([^"]+)"', x):
        loc[m.group(1)] = name


def nav_ol(entries):
    out, stack = [], []
    html_ = ""
    lvl_prev = 0
    for lvl, title, aid in entries:
        if aid not in loc:
            continue
        if lvl > lvl_prev:
            html_ += "<ol>" * (lvl - lvl_prev)
        elif lvl < lvl_prev:
            html_ += "</li>" + "</ol></li>" * (lvl_prev - lvl)
        else:
            html_ += "</li>" if lvl_prev else ""
        html_ += '<li><a href="%s#%s">%s</a>' % (loc[aid], aid, esc(title))
        lvl_prev = lvl
    html_ += "</li>" + "</ol></li>" * (lvl_prev - 1) + "</ol>" if lvl_prev else ""
    return html_


plist = "".join('<li><a href="%s#%s">%s</a></li>' % (loc[i], i, esc(l)) for i, l in page_ids if i in loc)
nav = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
       'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>Contents</title></head><body>'
       '<nav epub:type="toc" id="toc"><h1>Contents</h1>%s</nav>'
       '<nav epub:type="page-list" hidden=""><ol>%s</ol></nav></body></html>' % (nav_ol(toc_entries), plist))

# NCX (crengine reads this)
ncx_pts, n = [], [0]


def ncx_build(entries):
    out, stack = "", []
    for lvl, title, aid in entries:
        if aid not in loc:
            continue
        while stack and stack[-1] >= lvl:
            out += "</navPoint>"; stack.pop()
        n[0] += 1
        out += '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s#%s"/>' % (
            n[0], n[0], esc(title), loc[aid], aid)
        stack.append(lvl)
    out += "</navPoint>" * len(stack)
    return out


pl = "".join('<pageTarget id="pt%d" type="normal" value="%d"><navLabel><text>%s</text></navLabel><content src="%s#%s"/></pageTarget>'
             % (k, k + 1, esc(l), loc[i], i) for k, (i, l) in enumerate(page_ids) if i in loc)
ncx = ('<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
       '<head><meta name="dtb:uid" content="%s"/></head><docTitle><text>%s</text></docTitle><navMap>%s</navMap>'
       '<pageList><navLabel><text>Pages</text></navLabel>%s</pageList></ncx>' % (bookid, esc(A.title), ncx_build(toc_entries), pl))

cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).tobytes("jpeg")
cover_x = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml"><head>'
           '<meta charset="utf-8"/><title>Cover</title><style>body{margin:0;text-align:center}img{max-width:100%;max-height:100%}</style>'
           '</head><body><img src="img/cover.jpg" alt="cover"/></body></html>')
man = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
       '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
       '<item id="css" href="style.css" media-type="text/css"/>',
       '<item id="cover-image" href="img/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
       '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>']
spine = ['<itemref idref="cover"/>']
for k, (name, title, x) in enumerate(files):
    man.append('<item id="x%d" href="%s" media-type="application/xhtml+xml"/>' % (k, name))
    spine.append('<itemref idref="x%d"/>' % k)
for h, (name, data) in imgs.items():
    man.append('<item id="%s" href="img/%s" media-type="image/png"/>' % (name[:-4], name))
opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bid">'
       '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bid">%s</dc:identifier><dc:title>%s</dc:title>'
       '<dc:creator>%s</dc:creator><dc:language>en</dc:language><meta property="dcterms:modified">2026-11-27T00:00:00Z</meta>'
       '<meta name="cover" content="cover-image"/></metadata><manifest>%s</manifest><spine toc="ncx">%s</spine></package>'
       % (bookid, esc(A.title), esc(A.author), "".join(man), "".join(spine)))

with zipfile.ZipFile(A.dst, "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    zc = dict(compress_type=zipfile.ZIP_DEFLATED)
    z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
               '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', **zc)
    z.writestr("OEBPS/content.opf", opf, **zc)
    z.writestr("OEBPS/nav.xhtml", nav, **zc)
    z.writestr("OEBPS/toc.ncx", ncx, **zc)
    z.writestr("OEBPS/style.css", CSS, **zc)
    z.writestr("OEBPS/cover.xhtml", cover_x, **zc)
    z.writestr("OEBPS/img/cover.jpg", cover, compress_type=zipfile.ZIP_STORED)
    for name, title, x in files:
        z.writestr("OEBPS/" + name, x, **zc)
    for h, (name, data) in imgs.items():
        z.writestr("OEBPS/img/" + name, data, compress_type=zipfile.ZIP_STORED)

bad = [r for r in report if r[4] > 30]
nt = sum(r[2] for r in report); ni = sum(r[3] for r in report)
print("pages %d | text lines %d | block images %d | inline+block png %d | pages with uncovered ink: %d"
      % (len(report), nt, ni, len(imgs), len(bad)))
if A.report:
    with open(A.report, "w") as f:
        for r in report:
            f.write("%d\t%s\ttext=%d\timg=%d\tuncovered=%d\n" % r)
print("saved", A.dst, os.path.getsize(A.dst) // 1024, "KB")
