# Greyscale + fit to the PW5 screen (1236x1648), pages renumbered in reading order.
import sys, re, io, zipfile
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
W, H = 1236, 1648
zin = zipfile.ZipFile(src)
pages = [i for i in zin.infolist() if not i.is_dir() and i.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
def key(i):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", i.filename)]
pages.sort(key=key)
with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as zout:
    for n, info in enumerate(pages, 1):
        im = Image.open(io.BytesIO(zin.read(info))).convert("L")
        bw, bh = (H, W) if im.width > im.height else (W, H)  # spreads fit landscape
        scale = min(bw / im.width, bh / im.height, 1.0)
        if scale < 1.0:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88, optimize=True)
        zout.writestr("%04d.jpg" % n, buf.getvalue())
print("pages", len(pages), "first", pages[0].filename, "last", pages[-1].filename)
