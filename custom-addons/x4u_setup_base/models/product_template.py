from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # x4u_sale spec v0.8 A1 / A2: installation, transport... priced only when the customer asks.
    x4u_price_on_request = fields.Boolean(
        string="Price on Request",
        help="Quoted without a price: a line or option of this product with no price prints "
        "'As requested'. Once it has a price, the price prints.",
    )


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _x4u_as_requested(self):
        """A line of a price-on-request product with no price yet (spec v0.8 A1)."""
        self.ensure_one()
        return bool(self.product_id.x4u_price_on_request) and self.currency_id.is_zero(self.price_unit)


class SaleOrderOption(models.Model):
    _inherit = "sale.order.option"

    def _x4u_as_requested(self):
        self.ensure_one()
        currency = self.order_id.currency_id
        return bool(self.product_id.x4u_price_on_request) and currency.is_zero(self.price_unit)
