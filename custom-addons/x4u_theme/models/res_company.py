from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # The navbar is black: the normal logo's black gear would disappear on it. The Administrator
    # uploads a light version (Settings > Companies); the logo files stay out of Git.
    x4u_navbar_logo = fields.Binary(
        string="Logo on dark (navbar)",
        attachment=True,
        help="A version of the logo for the black navbar: light parts instead of black, "
        "transparent background. About 180 px high.",
    )
