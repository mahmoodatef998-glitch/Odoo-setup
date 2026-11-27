"""The user, 2026-11-27: the Salesperson sees each product's price in the 4U price lists (Standard,
Export AED, Export USD) on the product screens and in the product search of a quotation, before
picking it. A generator lists the price of each alternator: "4U 49,894 · LS 57,931 · ST on request"."""
from odoo import _, api, fields, models

PRICELISTS = (
    ("standard", "x4u_setup_4u.pricelist_standard"),
    ("export_aed", "x4u_job_order.pricelist_export_aed"),
    ("export_usd", "x4u_setup_4u.pricelist_export"),
)
ALTERNATOR_SHORT = {
    "x4u_setup_base.attr_alternator_aqt": "4U",
    "x4u_setup_base.attr_alternator_leroy": "LS",
    "x4u_setup_base.attr_alternator_stamford": "ST",
}


def _format(price):
    if not price:
        return _("on request")
    return "{:,.0f}".format(price) if float(price).is_integer() else "{:,.2f}".format(price)


def _prices(env, products):
    """{key: {product id: price}} in each 4U price list (0.0: no price, on request)."""
    result = {}
    for key, xmlid in PRICELISTS:
        pricelist = env.ref(xmlid, raise_if_not_found=False)
        result[key] = pricelist.sudo()._get_products_price(products, 1.0) if pricelist and products else {}
    return result


class ProductProduct(models.Model):
    _inherit = "product.product"

    x4u_price_standard = fields.Char(string="Standard (AED)", compute="_compute_x4u_prices")
    x4u_price_export_aed = fields.Char(string="Export (AED)", compute="_compute_x4u_prices")
    x4u_price_export_usd = fields.Char(string="Export (USD)", compute="_compute_x4u_prices")

    @api.depends_context("company")
    def _compute_x4u_prices(self):
        products = self.filtered("id")
        prices = _prices(self.env, products)
        for product in self:
            for key, _xmlid in PRICELISTS:
                product["x4u_price_%s" % key] = _format(prices[key].get(product.id)) if product.id else False


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x4u_price_standard = fields.Char(string="Standard (AED)", compute="_compute_x4u_prices")
    x4u_price_export_aed = fields.Char(string="Export (AED)", compute="_compute_x4u_prices")
    x4u_price_export_usd = fields.Char(string="Export (USD)", compute="_compute_x4u_prices")

    @api.depends_context("company")
    def _compute_x4u_prices(self):
        variants = self.filtered("id").product_variant_ids
        prices = _prices(self.env, variants)
        short = {}
        for xmlid, label in ALTERNATOR_SHORT.items():
            value = self.env.ref(xmlid, raise_if_not_found=False)
            if value:
                short[value.id] = label
        alternator_attributes = self.env["product.attribute.value"].browse(list(short)).attribute_id
        for template in self:
            products = template.product_variant_ids if template.id else self.env["product.product"]
            for key, _xmlid in PRICELISTS:
                if not products:
                    template["x4u_price_%s" % key] = False
                elif len(products) == 1:
                    template["x4u_price_%s" % key] = _format(prices[key].get(products.id))
                else:
                    parts = []
                    for product in products:
                        values = product.product_template_attribute_value_ids.product_attribute_value_id
                        alternator = values.filtered(lambda v: v.attribute_id in alternator_attributes) or values
                        label = " ".join(short.get(v.id, v.name) for v in alternator)
                        parts.append("%s %s" % (label, _format(prices[key].get(product.id))))
                    template["x4u_price_%s" % key] = " · ".join(parts)
