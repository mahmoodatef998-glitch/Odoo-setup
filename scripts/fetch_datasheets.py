"""Step 1 of the generator importer (spec x4u_generator_datasheet §6): read every 4U model's datasheet
from the website and keep it as JSON in private/datasheets/ (git-ignored), one file per model plus
index.json. The website builds the datasheets on the Drive (4U-DS-xxx), so the data is the same.

    python scripts/fetch_datasheets.py [4U-C300 4U-P500 ...]

Reads the model list from /en/generators and each model's structured data (JSON-LD Product:
name, description, image, every datasheet line) from /en/models/<slug>. One request at a time.
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

SITE = "https://www.4ugenerators.com"
OUT = Path(__file__).resolve().parent.parent / "private" / "datasheets"
HEADERS = {"User-Agent": "4U-Odoo-datasheet-import/1.0"}


def get(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def model_index():
    text = get(SITE + "/en/generators").replace('\\"', '"')
    models = {}
    for match in re.finditer(r'\{"slug":"(4u-[a-z0-9-]+)","code":"[^"]+".*?\}', text):
        try:
            model = json.loads(match.group(0))
        except ValueError:
            continue
        models[model["slug"]] = model
    return sorted(models.values(), key=lambda m: m["code"])


def datasheet(slug):
    page = get("%s/en/models/%s" % (SITE, slug))
    for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(html.unescape(block))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]):
            if isinstance(item, dict) and item.get("@type") == "Product" and item.get("additionalProperty"):
                return {
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "image": item.get("image"),
                    "url": item.get("url"),
                    "properties": [[p.get("name"), p.get("value")] for p in item["additionalProperty"]],
                }
    return None


def main(codes):
    OUT.mkdir(parents=True, exist_ok=True)
    index = model_index()
    (OUT / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    wanted = {c.upper() for c in codes}
    saved, missing = 0, []
    for model in index:
        if wanted and model["code"].upper() not in wanted:
            continue
        sheet = datasheet(model["slug"])
        if not sheet:
            missing.append(model["code"])
            continue
        sheet.update(model)
        (OUT / ("%s.json" % model["code"])).write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
        saved += 1
        time.sleep(0.5)
    print("models on the website: %s, saved: %s, without a datasheet: %s" % (len(index), saved, ", ".join(missing) or "-"))


if __name__ == "__main__":
    main(sys.argv[1:])
