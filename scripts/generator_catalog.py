"""Generator catalog, step 1b (spec x4u_generator_datasheet §5-§6): the datasheets fetched by
scripts/fetch_datasheets.py + the 2026 price lists (text of UAE_PRICE_LIST_2026.pdf and
EXPORT_PRICE_LIST_2026.pdf from the Drive, in private/pricelists/) -> private/datasheets/catalog.json,
what scripts/import_generators.py loads into Odoo. Prints what has no price (price on request).

    python scripts/generator_catalog.py

A model's price row is found by its engine (Baudouin: engine + Leroy-Somer frame, the same engine
comes with two frames). The 4U alternator is the KWISE / CHINA / LP rows, Leroy-Somer the TAL rows;
Stamford has no row (price on request). Perkins rows are in GBP.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "private"
SHEETS, LISTS = ROOT / "datasheets", ROOT / "pricelists"

# Same engine, spelled differently in the price list and on the website (checked by their kVA).
ALIASES = {
    "2506AE15AG2": "2506AE15TAG2",  # list typo (Perkins 500 kVA, China alternator)
    "LP625SG3": "LP625EG3",  # Lister 638 kVA
    "LP625G5": "LP625EG5",  # Lister 750 kVA
    "4008TAG2A": "4008TAG2",  # Perkins 1000 kVA
    "C6LTAA9.5G3": "6LTAA9.5G3",  # Cummins 4U-C271
    "V3300E2BG": "V3300E2BG2",  # Kubota 4U-K30 (KU-30)
}


def norm(text):
    return re.sub(r"[\s\-()]", "", text.upper().replace("(D)", ""))


def frame(text):
    text = (text or "").upper().replace(" ", "")
    return re.sub(r"^TAL-?A", "TAL0", text).replace("-", "")


def parse(path):
    rows, section = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = line[3:]
            continue
        parts = re.split(r"(£?\d{1,3}(?:,\d{3})+)", line)
        for text, price in zip(parts[0::2], parts[1::2]):
            text = text.strip()
            if section.startswith(("CUMMINS", "BAUDOUIN")):
                tokens = text.split()
                engine, origin = tokens[1], tokens[-1]
                row_frame = frame(tokens[2]) if section.startswith("BAUDOUIN") else None
            elif section.startswith("KUBOTA"):
                engine, origin, row_frame = re.match(r"KU-[\d.]+\s*/\s*\d+\s+(\S+)", text).group(1), None, None
            else:  # Lister Petter, Perkins: "12 KVA SA315G1 ..."
                engine, origin, row_frame = re.match(r"[\d.]+ KVA (\S+)", text).group(1), None, None
            rows.append({
                "section": section, "text": text, "engine": engine, "frame": row_frame, "origin": origin,
                "alternator": "Leroy-Somer" if ("TAL" in section or "LEROY" in section) else "4U",
                "price": float(price.lstrip("£").replace(",", "")), "currency": "GBP" if price.startswith("£") else "AED",
            })
    return rows


def row_keys(row):
    key = norm(row["engine"])
    key = ALIASES.get(key, key)
    keys = {key}
    if row["section"].startswith("CUMMINS") and "/" in key:  # 6BTA5.9G5/6 = G5 and G6, X3.3G1/2 = G1 and G2
        base, other = key.split("/", 1)
        keys |= {base, re.sub(r"\d+$", "", base) + other}
    return {k + "|" + row["frame"] for k in keys} if row["frame"] else keys


def main():
    index = {}
    for market, name in (("uae", "UAE_PRICE_LIST_2026.txt"), ("export", "EXPORT_PRICE_LIST_2026.txt")):
        for row in parse(LISTS / name):
            for key in row_keys(row):
                index.setdefault((market, row["alternator"], key), []).append(row)
    catalog, unpriced = [], []
    for path in sorted(SHEETS.glob("4U-*.json")):
        sheet = json.loads(path.read_text(encoding="utf-8"))
        data = dict(sheet["properties"])
        engine = norm(sheet["engine"])
        candidates = [engine, engine.split("/G")[0]] if "/G" in engine else [engine]
        baudouin_frame = frame(data.get("Leroy-Somer frame")) if sheet["brand"] == "Baudouin" else None
        prices = {}
        for market in ("uae", "export"):
            for alternator in ("4U", "Leroy-Somer"):
                for candidate in candidates:
                    key = candidate + "|" + baudouin_frame if baudouin_frame else candidate
                    rows = index.get((market, alternator, key))
                    if rows:
                        # Two origins of one engine (Cummins KTA50-G3): the Indian build, as in the TAL list.
                        row = next((r for r in rows if r["origin"] == "INDIA"), rows[0])
                        prices.setdefault(alternator, {"currency": row["currency"]})[market] = row["price"]
                        break
        if not prices:
            unpriced.append(sheet["code"])
        catalog.append({key: sheet.get(key) for key in ("code", "brand", "engine", "primeKva", "standbyKva", "url", "properties")}
                       | {"prices": prices})
    (SHEETS / "catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    print("models: %s, with a list price: %s" % (len(catalog), len(catalog) - len(unpriced)))
    print("price on request (no row in the 2026 lists): %s" % ", ".join(unpriced))


if __name__ == "__main__":
    main()
