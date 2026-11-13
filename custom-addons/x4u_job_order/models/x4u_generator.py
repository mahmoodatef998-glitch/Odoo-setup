from odoo import fields, models


class X4uGenerator(models.Model):
    _inherit = "x4u.generator"

    x4u_enclosure = fields.Char(string="Enclosure", tracking=True, help="Open or Canopy, from the variant sold.")
    x4u_supplier_serial = fields.Char(
        string="Supplier Serial No", tracking=True, copy=False,
        help="A generator bought ready (spec v0.7 G3): its 4U serial is the Ready Job Order number; "
        "the supplier's own serial is kept here.",
    )
