from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Gets the to-dos: proforma not paid on its due date, generator ready for its final invoice.
    x4u_accountant_user_id = fields.Many2one(
        "res.users", string="Accountant", config_parameter="x4u_sale.accountant_user_id"
    )
