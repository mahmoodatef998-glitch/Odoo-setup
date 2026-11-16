from odoo import api, fields, models
from odoo.osv import expression

from .serial_search import serial_domain


class X4uGenerator(models.Model):
    _inherit = "x4u.generator"

    x4u_enclosure = fields.Char(string="Enclosure", tracking=True, help="Open or Canopy, from the variant sold.")
    x4u_supplier_serial = fields.Char(
        string="Supplier Serial No", tracking=True, copy=False,
        help="A generator bought ready (spec v0.7 G3): its 4U serial is the Ready Job Order number; "
        "the supplier's own serial is kept here.",
    )
    x4u_engine_lot_id = fields.Many2one(
        "stock.lot", string="Engine in Stock", readonly=True, copy=False, tracking=True,
        help="Spec v0.8 N5: the engine delivered for this generator and fitted in it, by its serial.",
    )
    # Spec v0.10 B3: the body fitted, by its serial; the text for everyone, the link for the stock.
    x4u_body_lot_id = fields.Many2one(
        "stock.lot", string="Body in Stock", readonly=True, copy=False, tracking=True,
        help="The genset body delivered for this generator and fitted on it, by its serial.",
    )
    x4u_body_serial = fields.Char(string="Body Serial No", readonly=True, copy=False, tracking=True)
    # Read by everyone who opens the card, also without stock rights (the serial itself is stock data).
    x4u_engine_linked = fields.Boolean(compute="_compute_x4u_engine_linked")
    # Spec v0.10 S2: the card by any serial on it, or by the PI of its sales order.
    x4u_serial_search = fields.Char(string="Serial", compute="_compute_x4u_search", search="_search_x4u_serial")
    x4u_proforma_search = fields.Char(string="PI", compute="_compute_x4u_search", search="_search_x4u_proforma")

    def _compute_x4u_engine_linked(self):
        for card in self:
            card.x4u_engine_linked = bool(card.x4u_engine_lot_id.id)

    def _compute_x4u_search(self):
        self.x4u_serial_search = self.x4u_proforma_search = False

    def _search_x4u_serial(self, operator, value):
        return serial_domain(self._x4u_ids_by_serial, operator, value)

    def _search_x4u_proforma(self, operator, value):
        return serial_domain(self._x4u_ids_by_proforma, operator, value)

    @api.model
    def _x4u_ids_by_serial(self, operator, value):
        lots = self.env["stock.lot"].sudo().search([("name", operator, value)])
        texts = [[(name, operator, value)] for name in ("name", "engine_serial", "alternator_serial", "x4u_supplier_serial", "x4u_body_serial")]
        links = [[("x4u_engine_lot_id", "in", lots.ids)], [("x4u_body_lot_id", "in", lots.ids)]]
        return self.sudo().search(expression.OR(texts + links)).ids

    @api.model
    def _x4u_ids_by_proforma(self, operator, value):
        orders = self.env["x4u.sale.proforma"].sudo().search([("name", operator, value)]).order_id
        return self.sudo().search([("sale_order_id", "in", orders.ids)]).ids
