from odoo import models

# Spec v0.11 D3: the table "Generator Serial Numbers" on the delivery note, the tax invoice and the
# sales order. Read with sudo: the Accountant prints the invoice without stock rights.


def _cards(env, domain):
    return env["x4u.generator"].sudo().search(domain, order="name")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _x4u_generator_cards(self):
        return _cards(self.env, [("sale_order_id", "in", self.ids)]) if self.ids else self.env["x4u.generator"]


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _x4u_generator_cards(self):
        lots = self.sudo().move_line_ids.lot_id
        return _cards(self.env, [("lot_id", "in", lots.ids)]) if lots else self.env["x4u.generator"]


class AccountMove(models.Model):
    _inherit = "account.move"

    def _x4u_generator_cards(self):
        orders = self.sudo().invoice_line_ids.sale_line_ids.order_id
        return orders._x4u_generator_cards() if orders else self.env["x4u.generator"]
