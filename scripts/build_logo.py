"""Builds every rendering of the PF chip mark from one source SVG.

    assets/pf_logo_source.svg  ->  assets/pf_logo.png          (app header)
                               ->  assets/app_icon_chip.ico    (app/installer)
                               ->  docs/logo.png               (site header/footer)
                               ->  docs/favicon.ico            (site)
                               ->  docs/favicon-32.png         (site)
                               ->  docs/favicon-192.png        (site)
                               ->  docs/apple-touch-icon.png   (site, iOS)

The site assets are built here rather than exported separately because
they drifted once already: the app moved to new artwork while the site
kept serving the previous mark, so the two disagreed about what the logo
was. One source, one command, no drift.

Run after replacing the source artwork:

    python scripts/build_logo.py

Two steps here are non-obvious, and both exist because the artwork is
drawn for a white canvas while the header is nearly black.

Backgrounds: some versions of the source arrive on an opaque off-white
card that reaches the canvas edge. Cutting that by lightness alone also
eats the chip's own white segments, so this floods *inward from the
border* instead -- the card is reachable from the edge, the segments
aren't, and the two are only ~16 units apart in colour.

Interior holes: other versions draw the chip's inner ring as a hole
rather than a white stroke -- crisp on the designer's white canvas,
invisible against the header. So anything still transparent after the
flood has established what's genuinely outside gets painted white.

Either step is a no-op on artwork that doesn't need it, and the script
reports what each one did.

The source is a 2000px SVG, but it's ~30 embedded bitmaps rather than
real vector, so there's nothing to gain by shipping it and rendering at
runtime -- hence a plain PNG asset.
"""
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "pf_logo_source.svg"
OUTPUT = ROOT / "assets" / "pf_logo.png"
ICON = ROOT / "assets" / "app_icon_chip.ico"

RENDER_SIZE = 1024       # comfortably above the ~900px the artwork occupies
OUTPUT_SIZE = 256        # covers a 72px logo up to 300% display scaling
# What Windows actually asks for: 16 in the title bar and Explorer's
# small view, 32 on the taskbar, 48 in Explorer's default, 256 for the
# large tile and the installer. The rest fill in scaled displays.
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

# The site. docs/logo.png is displayed at 32px and 22px, so 128 gives
# retina headroom; apple-touch-icon is 180 by Apple's convention.
DOCS = ROOT / "docs"
SITE_PNGS = {"logo.png": 128, "favicon-32.png": 32, "favicon-192.png": 192}
SITE_ICO_SIZES = [16, 32, 48]
# White ring added to the SITE assets only, as a fraction of the mark's
# width. The chip's rim is black and vanishes against the site's near-black
# header; the app draws its own logo on a felt-green banner where the rim
# still reads, so it keeps the plain mark.
#
# Judge this at the size the header actually renders (42px), not at full
# resolution where any ring looks obvious: 0.022 came out at 0.88px on
# screen and was invisible. This gives ~2px, which reads as a boundary
# without the ring becoming the loudest part of the mark.
OUTLINE_FRACTION = 0.055

# iOS ignores alpha on a home-screen icon and composites it onto black,
# which would swallow the chip's black rim entirely. So this one gets an
# opaque ground; white, because the mark is drawn as black-on-white and
# its white details stay inside the rim where they still read.
APPLE_TOUCH_SIZE = 180
APPLE_TOUCH_GROUND = (255, 255, 255, 255)
ALPHA_HOLE = 40          # below this a pixel counts as "nothing drawn here"
CARD_TOLERANCE = 24      # colour distance still counted as background card


def render(path: Path, size: int) -> Image.Image:
    """The SVG rasterised onto transparency, as a Pillow image."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    QSvgRenderer(str(path)).render(painter)
    painter.end()

    bits = img.constBits()
    bits.setsize(img.sizeInBytes())
    return Image.frombytes("RGBA", (size, size), bytes(bits), "raw", "BGRA",
                           img.bytesPerLine())


def remove_background_card(im: Image.Image) -> int:
    """Clears an opaque background card, in place. Returns pixels cleared.

    The card colour is sampled from the corners, so this adapts to
    whatever the artwork ships on; if the corners are already
    transparent there's no card and nothing happens. Only pixels
    *connected to the border* are cleared, which is what keeps the
    chip's own white segments -- barely 16 units away in colour -- from
    being cut out along with it.

    A hard cut is fine because it happens at RENDER_SIZE and the result
    is downscaled 4x afterwards: the resample turns the stepped edge
    into a properly antialiased one."""
    w, h = im.size
    px = im.load()

    corners = [px[1, 1], px[w - 2, 1], px[1, h - 2], px[w - 2, h - 2]]
    if any(c[3] < ALPHA_HOLE for c in corners):
        return 0
    card = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    def is_card(x, y):
        p = px[x, y]
        if p[3] < ALPHA_HOLE:
            return True
        return sum((p[i] - card[i]) ** 2 for i in range(3)) <= CARD_TOLERANCE ** 2

    seen = bytearray(w * h)
    queue = deque()

    def seed(x, y):
        if not seen[y * w + x] and is_card(x, y):
            seen[y * w + x] = 1
            queue.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    cleared = 0
    while queue:
        x, y = queue.popleft()
        if px[x, y][3] >= ALPHA_HOLE:
            px[x, y] = (255, 255, 255, 0)
            cleared += 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                seed(nx, ny)
    return cleared


def add_outline(im: Image.Image, fraction: float = OUTLINE_FRACTION) -> Image.Image:
    """The mark with a white ring around its outer edge.

    The chip's own rim is black, which all but disappears against the
    site's near-black header -- the mark reads as a floating "PF" with
    its edge lost. A white outline gives it a defined boundary.

    Done by dilating the alpha channel and painting white wherever the
    dilated silhouette extends past the original, so the ring follows the
    real edge rather than assuming a perfect circle. Added at full
    resolution so it scales with every size derived from it."""
    w, _ = im.size
    radius = max(1, round(w * fraction))

    alpha = im.getchannel("A")
    grown = alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1))

    ring = Image.new("RGBA", im.size, (255, 255, 255, 255))
    ring.putalpha(grown)
    ring.alpha_composite(im)
    return ring


def fill_interior_holes(im: Image.Image) -> int:
    """Paints every transparent pixel that isn't reachable from the border
    white, in place. Returns how many were filled.

    Flooding in from the border is what separates "background" from "a
    hole in the artwork" -- a lightness threshold can't tell them apart,
    and eats the chip's white segments if you try."""
    w, h = im.size
    px = im.load()

    outside = bytearray(w * h)
    queue = deque()

    def seed(x, y):
        if px[x, y][3] < ALPHA_HOLE and not outside[y * w + x]:
            outside[y * w + x] = 1
            queue.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                seed(nx, ny)

    filled = 0
    for y in range(h):
        for x in range(w):
            if px[x, y][3] < ALPHA_HOLE and not outside[y * w + x]:
                px[x, y] = (255, 255, 255, 255)
                filled += 1
    return filled


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source artwork: {SOURCE}", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)  # noqa: F841 -- QImage/QPainter need one

    im = render(SOURCE, RENDER_SIZE)

    cleared = remove_background_card(im)
    print(f"background card cleared: {cleared:,} px "
          f"({cleared / (RENDER_SIZE ** 2):.1%})")

    filled = fill_interior_holes(im)
    print(f"interior knockouts painted white: {filled:,} px")

    box = im.getbbox()
    if box is None:
        print("the artwork rendered as nothing at all", file=sys.stderr)
        return 1
    im = im.crop(box)

    # Square it so the header can scale by one factor and keep the chip
    # circular, whatever the source's aspect ratio happens to be.
    w, h = im.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    square.paste(im, ((side - w) // 2, (side - h) // 2))
    print(f"cropped {w}x{h} -> square {side}")

    square.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS).save(
        OUTPUT, optimize=True, compress_level=9)
    print(f"wrote {OUTPUT.relative_to(ROOT)} "
          f"({OUTPUT.stat().st_size:,} bytes)")

    # Each size resampled from the full-resolution square rather than
    # from the 256px PNG: at 16 and 24 a chain of downscales visibly
    # muddies the mark, and those are the sizes Windows leans on most.
    square.save(ICON, format="ICO",
                sizes=[(s, s) for s in ICON_SIZES])
    print(f"wrote {ICON.relative_to(ROOT)} "
          f"({ICON.stat().st_size:,} bytes, sizes {ICON_SIZES})")

    if DOCS.is_dir():
        # The mark fills its square edge to edge, so a ring drawn on it
        # would be cut off flat at top, bottom and sides. Pad first, then
        # outline into the room that creates.
        pad = round(side * OUTLINE_FRACTION) + 2
        padded = Image.new("RGBA", (side + pad * 2, side + pad * 2),
                           (255, 255, 255, 0))
        padded.paste(square, (pad, pad))
        outlined = add_outline(padded)
        print(f"site mark: {side} -> {outlined.size[0]} square with a "
              f"{OUTLINE_FRACTION:.1%} white outline")

        for name, size in SITE_PNGS.items():
            path = DOCS / name
            outlined.resize((size, size), Image.LANCZOS).save(
                path, optimize=True, compress_level=9)
            print(f"wrote {path.relative_to(ROOT)} "
                  f"({size}px, {path.stat().st_size:,} bytes)")

        # No outline here: this one sits on an opaque white ground, where
        # a white ring is invisible anyway and only shrinks the mark.
        apple = DOCS / "apple-touch-icon.png"
        ground = Image.new("RGBA", (APPLE_TOUCH_SIZE, APPLE_TOUCH_SIZE),
                           APPLE_TOUCH_GROUND)
        ground.alpha_composite(
            square.resize((APPLE_TOUCH_SIZE, APPLE_TOUCH_SIZE), Image.LANCZOS))
        ground.convert("RGB").save(apple, optimize=True, compress_level=9)
        print(f"wrote {apple.relative_to(ROOT)} "
              f"({APPLE_TOUCH_SIZE}px opaque, {apple.stat().st_size:,} bytes)")

        # Smaller than the app's icon on purpose: a browser never asks
        # for 256, and the file is fetched on every cold page load.
        favicon = DOCS / "favicon.ico"
        outlined.save(favicon, format="ICO",
                      sizes=[(s, s) for s in SITE_ICO_SIZES])
        print(f"wrote {favicon.relative_to(ROOT)} "
              f"({favicon.stat().st_size:,} bytes, sizes {SITE_ICO_SIZES})")
    else:
        print("no docs/ directory -- skipped the site assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
