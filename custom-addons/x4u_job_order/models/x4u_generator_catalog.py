import logging

from odoo import Command, api, models

from odoo.addons.x4u_generator.models.x4u_generator_datasheet_line import SECTION_OF

_logger = logging.getLogger(__name__)

ALTERNATOR_VALUES = {
    "4U": "x4u_setup_base.attr_alternator_aqt",
    "Leroy-Somer": "x4u_setup_base.attr_alternator_leroy",
    "Stamford": "x4u_setup_base.attr_alternator_stamford",
}
CATALOG_BOM_CODE = "4U catalog"


def _kva(value):
    return "%g" % float(value or 0)


class X4uGeneratorCatalog(models.AbstractModel):
    """Spec x4u_generator_datasheet §6 step 2: the 4U models in Odoo, from the datasheets and the 2026
    price lists (scripts/generator_catalog.py builds the entries, scripts/import_generators.py runs this).

    Runs again at any time: a model is found by its code (4U-C300) and brought up to date - its
    data, datasheet, alternators, components, BoM and list prices. Nothing is deleted; a model that
    left the website stays as it is. Silent canopy only (the user: no open sets)."""

    _name = "x4u.generator.catalog"
    _description = "4U Generator Catalog Import"

    @api.model
    def _x4u_import(self, entries):
        self = self.sudo()
        aqt = self.env.ref(ALTERNATOR_VALUES["4U"])
        if aqt.name != "4U":
            aqt.name = "4U"  # spec §7: the alternator of the new datasheets is "4U"
        templates = self.env["product.template"]
        for entry in entries:
            templates |= self._x4u_import_model(entry)
        self._x4u_import_prices(entries, templates)
        by_code = {entry["code"]: entry for entry in entries}
        priced = templates.product_variant_ids.filtered(lambda p: self._x4u_price_of(p, by_code))
        return {
            "models": len(templates),
            "variants": len(templates.product_variant_ids),
            "priced_variants": len(priced),
            "price_on_request": sorted(set((templates.product_variant_ids - priced).mapped("display_name"))),
        }

    # ---- one model -------------------------------------------------------------------------
    def _x4u_brand(self, name, brand_type):
        Brand = self.env["x4u.generator.brand"].with_context(active_test=False)
        brand = Brand.search([("name", "=ilike", name), ("brand_type", "in", (brand_type, "both"))], limit=1)
        return brand or Brand.create({"name": name, "brand_type": brand_type})

    def _x4u_import_model(self, entry):
        ref = self.env.ref
        data = dict(entry["properties"])
        code = entry["code"]
        prices = entry.get("prices") or {}
        leroy, stamford = data.get("Leroy-Somer frame"), data.get("Stamford frame")
        choices = ["4U"]
        if leroy or "Leroy-Somer" in prices:
            choices.append("Leroy-Somer")
        if stamford:
            choices.append("Stamford")
        values = self.env["product.attribute.value"].browse([ref(ALTERNATOR_VALUES[c]).id for c in choices])
        canopy = ref("x4u_setup_base.attr_enclosure_canopy")
        vals = {
            "name": "%s Diesel Generator Set %s kVA Prime / %s kVA Standby, Silent Canopy" % (
                entry["brand"], _kva(entry["primeKva"]), _kva(entry["standbyKva"])),
            "x4u_model_code": code,
            "x4u_datasheet_code": "4U-DS-%s" % code[3:],
            "x4u_datasheet_url": entry.get("url"),
            "x4u_controller": data.get("Controller"),
            "x4u_leroy_frame": leroy,
            "x4u_stamford_frame": stamford,
            "x4u_kva_prime": float(entry["primeKva"]),
            "x4u_kva_standby": float(entry["standbyKva"]),
            "x4u_engine_brand_id": self._x4u_brand(entry["brand"], "engine").id,
            "x4u_engine_model": entry["engine"],
            "x4u_warranty_months": 12,
            "x4u_warranty_hours": 1000.0,
            "x4u_price_on_request": True,  # no price yet prints "As requested"
            "categ_id": ref("x4u_setup_base.categ_generators").id,
            "sale_ok": True,
            "purchase_ok": True,
        }
        Template = self.env["product.template"].with_context(active_test=False)
        template = Template.search([("x4u_model_code", "=", code)], limit=1)
        if not template:
            template = Template.create(
                dict(
                    vals,
                    type="consu",
                    is_storable=True,
                    tracking="serial",
                    x4u_is_generator=True,
                    list_price=0.0,
                    route_ids=[Command.set([ref("mrp.route_warehouse0_manufacture").id, ref("stock.route_warehouse0_mto").id])],
                    attribute_line_ids=[
                        Command.create({"attribute_id": canopy.attribute_id.id, "value_ids": [Command.set(canopy.ids)]}),
                        Command.create({"attribute_id": values.attribute_id.id, "value_ids": [Command.set(values.ids)]}),
                    ],
                )
            )
        else:
            template.write(vals)
            line = template.attribute_line_ids.filtered(lambda l: l.attribute_id == values.attribute_id)
            missing = values - line.value_ids
            if line and missing:
                line.value_ids = [Command.link(v.id) for v in missing]
        template.x4u_datasheet_line_ids = [Command.clear()] + [
            Command.create({"sequence": index, "section": SECTION_OF.get(name, "other"), "name": name, "value": value})
            for index, (name, value) in enumerate(entry["properties"], 1)
            if name and value
        ]
        # The 4U attributes make their variants on demand: every alternator offered gets its variant
        # now, so it has its list price and can be picked on a quotation.
        ptavs = template.attribute_line_ids.product_template_value_ids
        canopy_ptav = ptavs.filtered(lambda v: v.product_attribute_value_id == canopy)
        for value in values:
            ptav = ptavs.filtered(lambda v, value=value: v.product_attribute_value_id == value)
            if ptav and canopy_ptav:
                template._create_product_variant(canopy_ptav + ptav)
        for variant in template.product_variant_ids:
            if variant.default_code != code:
                variant.default_code = code
        self._x4u_import_bom(template, entry, data)
        return template

    # ---- components and BoM (spec §4) ---------------------------------------------------------
    def _x4u_part(self, code, name, categ_xmlid, vendor=None):
        ref = self.env.ref
        Product = self.env["product.product"].with_context(active_test=False)
        part = Product.search([("default_code", "=", code)], limit=1)
        if not part:
            part = Product.create(
                {
                    "name": name,
                    "default_code": code,
                    "type": "consu",
                    "is_storable": True,
                    "categ_id": ref(categ_xmlid).id,
                    "purchase_request": True,
                    "sale_ok": False,
                    "route_ids": [Command.set([ref("purchase_stock.route_warehouse0_buy").id, ref("stock.route_warehouse0_mto").id])],
                    "seller_ids": [Command.create({"partner_id": vendor.id})] if vendor else [],
                }
            )
        return part

    def _x4u_import_bom(self, template, entry, data):
        code, brand, prime = entry["code"], entry["brand"], _kva(entry["primeKva"])
        engine = self._x4u_part("ENG-%s" % entry["engine"], "%s %s Engine" % (brand, entry["engine"]), "x4u_setup_base.categ_engines")
        aqt_vendor = self.env["res.partner"].search([("name", "=ilike", "AQT%"), ("is_company", "=", True)], limit=1)
        canopy = self._x4u_part("CAN-%s" % code[3:], "Silent Canopy %s" % code, "x4u_setup_base.categ_bodies", aqt_vendor)
        alternators = {
            "4U": self._x4u_part("ALT-4U-%s" % prime, "4U Power Alternator %s kVA" % prime, "x4u_setup_base.categ_alternators"),
        }
        if data.get("Leroy-Somer frame"):
            frame = data["Leroy-Somer frame"]
            alternators["Leroy-Somer"] = self._x4u_part("ALT-%s" % frame, "Leroy-Somer %s Alternator" % frame, "x4u_setup_base.categ_alternators")
        if data.get("Stamford frame"):
            frame = data["Stamford frame"]
            alternators["Stamford"] = self._x4u_part("ALT-%s" % frame, "Stamford %s Alternator" % frame, "x4u_setup_base.categ_alternators")
        ptavs = template.attribute_line_ids.product_template_value_ids
        lines = [Command.create({"product_id": engine.id, "product_qty": 1}), Command.create({"product_id": canopy.id, "product_qty": 1})]
        for choice, part in alternators.items():
            value = self.env.ref(ALTERNATOR_VALUES[choice])
            ptav = ptavs.filtered(lambda v, value=value: v.product_attribute_value_id == value)
            if ptav:
                lines.append(Command.create({
                    "product_id": part.id, "product_qty": 1,
                    "bom_product_template_attribute_value_ids": [Command.set(ptav.ids)],
                }))
        Bom = self.env["mrp.bom"]
        bom = Bom.search([("product_tmpl_id", "=", template.id), ("code", "=", CATALOG_BOM_CODE)], limit=1)
        if not bom and Bom.search_count([("product_tmpl_id", "=", template.id)]):
            return  # a BoM made by hand: the Operation Manager's, left as it is
        if bom:
            bom.bom_line_ids = [Command.clear()] + lines
        else:
            Bom.create({"product_tmpl_id": template.id, "code": CATALOG_BOM_CODE, "product_qty": 1, "bom_line_ids": lines})

    # ---- prices (spec §5) ------------------------------------------------------------------
    @api.model
    def _x4u_price_of(self, variant, by_code):
        """The list prices of a variant: {"uae": .., "export": .., "currency": ..} or None (on request)."""
        entry = by_code.get(variant.default_code) or {}
        choice = variant._x4u_alternator_choice().replace("AQT", "4U")
        return (entry.get("prices") or {}).get(choice)

    def _x4u_import_prices(self, entries, templates):
        ref = self.env.ref
        by_code = {entry["code"]: entry for entry in entries}
        standard = ref("x4u_setup_4u.pricelist_standard")
        export_aed = ref("x4u_job_order.pricelist_export_aed")
        gbp = {"uae": ref("x4u_job_order.pricelist_perkins_uae_gbp"), "export": ref("x4u_job_order.pricelist_perkins_export_gbp")}
        aed = {"uae": standard, "export": export_aed}
        Item = self.env["product.pricelist.item"]
        variants = templates.product_variant_ids
        Item.search([("pricelist_id", "in", (standard | export_aed | gbp["uae"] | gbp["export"]).ids), ("product_id", "in", variants.ids)]).unlink()
        items = []
        for variant in variants:
            price = self._x4u_price_of(variant, by_code)
            if not price:
                continue
            common = {"applied_on": "0_product_variant", "product_id": variant.id, "product_tmpl_id": variant.product_tmpl_id.id}
            for market in ("uae", "export"):
                if price.get(market) is None:
                    continue
                if price["currency"] == "GBP":
                    items.append(dict(common, pricelist_id=gbp[market].id, compute_price="fixed", fixed_price=price[market]))
                    items.append(dict(common, pricelist_id=aed[market].id, compute_price="formula", base="pricelist",
                                      base_pricelist_id=gbp[market].id, price_round=0.01))
                else:
                    items.append(dict(common, pricelist_id=aed[market].id, compute_price="fixed", fixed_price=price[market]))
        Item.create(items)
        # Export in USD follows Export (AED), converted at the day's rate (the peg).
        export_usd = ref("x4u_setup_4u.pricelist_export")
        follow = export_usd.item_ids.filtered(lambda i: i.base == "pricelist" and i.base_pricelist_id == export_aed)
        if follow and not follow[:1].price_round:
            follow.price_round = 0.01
        if not follow:
            Item.create({"pricelist_id": export_usd.id, "applied_on": "3_global", "compute_price": "formula",
                         "base": "pricelist", "base_pricelist_id": export_aed.id, "price_round": 0.01})
        _logger.info("x4u_job_order: %s list prices for %s generator models", len(items), len(templates))
