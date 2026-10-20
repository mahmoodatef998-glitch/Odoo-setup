from odoo import fields, models


class X4uGenerator(models.Model):
    _inherit = "x4u.generator"

    x4u_enclosure = fields.Char(string="Enclosure", tracking=True, help="Open or Canopy, from the variant sold.")
