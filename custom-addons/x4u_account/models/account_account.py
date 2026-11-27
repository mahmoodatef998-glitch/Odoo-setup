from odoo import fields, models

PL_GROUP_SELECTION = [
    ("operating", "O - Operating Expenses"),
    ("selling", "S - Selling & Marketing Expenses"),
    ("admin", "G - General & Administrative Expenses"),
    ("other", "X - Other Expenses"),
    ("tax", "X - Corporate Tax"),
]


class AccountAccount(models.Model):
    _inherit = "account.account"

    x4u_pl_group = fields.Selection(
        PL_GROUP_SELECTION,
        string="P&L Group",
        tracking=True,
        help="The accounting team, 2026-11-27: where this expense account shows in the 4U Management P&L "
        "and the Monthly P&L. An expense account without a group shows in 'Accounts Not in This Report'.",
    )
