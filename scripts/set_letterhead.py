"""x4u_reports §2: the 4U letterhead of every printed document, on the 4U company.

Reads the git-ignored private/branding/ (it carries the company's details, never in Git):
  letterhead.json        {"name", "tagline", "name_ar", "tagline_ar", "contact"}
  4u-logo-hq.png         the logo on a transparent background -> the logo in the header
  hi-light.png           the large logo on white               -> the watermark (the gear only)
  letterhead-brands.png  the brands strip                      -> the footer
then sets the "4U Letterhead" document layout and its A4 paper on the company. Run it again after
any change to those files.

    docker compose run --rm -T -v "$PWD/private/branding:/tmp/x4u_branding:ro" web \
        odoo shell -d <database> --no-http < scripts/set_letterhead.py
"""
import base64
import io
import json
import os

from PIL import Image, ImageChops, ImageMath

folder = os.environ.get("X4U_BRANDING") or "/tmp/x4u_branding"
WATERMARK_INK = 0.11  # how dark the watermark is: 11% of the logo, like the paper letterhead


def path(name):
    return os.path.join(folder, name)


def as_png(image):
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return base64.b64encode(out.getvalue())


def white_to_alpha(image):
    """The paper becomes transparent and the ink keeps its colour (GIMP's "colour to alpha")."""
    r, g, b = image.convert("RGB").split()
    alpha = ImageChops.invert(ImageChops.darker(ImageChops.darker(r, g), b))
    ink = [
        ImageMath.eval("convert(255 - (255 - c) * 255 / max(a, 1), 'L')", c=channel, a=alpha)
        for channel in (r, g, b)
    ]
    return Image.merge("RGBA", (*ink, alpha))


def header_logo():
    """The logo without its "GENERATION (FZC)" line: the letterhead writes the name beside it."""
    logo = Image.open(path("4u-logo-hq.png")).convert("RGBA")
    width, height = logo.size
    # The line sits under POWER, right of the gear: x from 37% of the width, y 69% to 78%.
    clear = Image.new("RGBA", (width - int(width * 0.37), int(height * 0.09)), (0, 0, 0, 0))
    logo.paste(clear, (int(width * 0.37), int(height * 0.69)))
    return logo.crop(logo.getchannel("A").getbbox())


def watermark():
    """The gear, the bolt and 4U from the large logo, faint, on a transparent background."""
    big = Image.open(path("hi-light.png"))
    size = big.size[0]
    # The gear and the bolt: the left 37% of the logo, between 31% and 81% of its height.
    gear = big.crop((int(size * 0.016), int(size * 0.31), int(size * 0.375), int(size * 0.81)))
    gear = white_to_alpha(gear)
    gear.putalpha(gear.getchannel("A").point(lambda a: int(a * WATERMARK_INK)))
    return gear.crop(gear.getchannel("A").getbbox())


def brands():
    """The brands strip without the yellow lines (the layout draws them), sharper when enlarged."""
    strip = Image.open(path("letterhead-brands.png")).convert("RGB")
    width, height = strip.size
    pixels = strip.load()

    def logo_ink(x, y):
        r, g, b = pixels[x, y]
        paper = min(r, g, b) > 225
        yellow_line = r > 200 and g > 170 and b < 170 and r - b > 60
        return not paper and not yellow_line

    columns = [sum(logo_ink(x, y) for y in range(height)) for x in range(width)]
    rows = [sum(logo_ink(x, y) for x in range(width)) for y in range(height)]
    left = next(x for x in range(width) if columns[x])
    right = width - next(i for i, x in enumerate(reversed(range(width))) if columns[x])
    # A thin mark alone at the right edge (a stray line in the source) is not a logo: drop it.
    run = 0
    while right - run - 1 > left and columns[right - run - 1]:
        run += 1
    gap = 0
    while right - run - gap - 1 > left and not columns[right - run - gap - 1]:
        gap += 1
    if run <= 3 and gap >= 3:
        right -= run + gap
    # The logos' rows: those with real ink (the yellow lines and the faint edges are left out).
    tall = [y for y in range(height) if rows[y] > 2]
    strip = strip.crop((left, tall[0], right, tall[-1] + 1))
    return strip.resize((strip.size[0] * 3, strip.size[1] * 3), Image.LANCZOS)


texts = json.load(open(path("letterhead.json"), encoding="utf-8"))
company = env["res.company"].search([("name", "ilike", "4U Power")], limit=1) or env.company
company.write(
    {
        "x4u_lh_name": texts.get("name"),
        "x4u_lh_tagline": texts.get("tagline"),
        "x4u_lh_name_ar": texts.get("name_ar"),
        "x4u_lh_tagline_ar": texts.get("tagline_ar"),
        "x4u_lh_contact": texts.get("contact"),
        "x4u_lh_logo": as_png(header_logo()),
        "x4u_lh_watermark": as_png(watermark()),
        "x4u_lh_brands": as_png(brands()),
        "external_report_layout_id": env.ref("x4u_reports.report_layout_x4u").view_id.id,
        "paperformat_id": env.ref("x4u_reports.paperformat_x4u_letterhead").id,
    }
)
env.cr.commit()
print("LETTERHEAD set on", company.name)
