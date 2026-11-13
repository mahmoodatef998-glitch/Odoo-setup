from odoo import fields, models


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
    # Read by everyone who opens the card, also without stock rights (the serial itself is stock data).
    x4u_engine_linked = fields.Boolean(compute="_compute_x4u_engine_linked")

    def _compute_x4u_engine_linked(self):
        for card in self:
            card.x4u_engine_linked = bool(card.x4u_engine_lot_id.id)
