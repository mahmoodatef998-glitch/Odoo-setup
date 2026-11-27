from odoo import api, fields, models


class AccountAgeReportConfiguration(models.Model):
    """The accounting team, 2026-11-27: the Aged Partner Balance in 0-30 / 31-60 / 61-90 / +90 days,
    the age counted from the invoice date (not the due date)."""

    _inherit = "account.age.report.configuration"

    x4u_from_invoice_date = fields.Boolean(
        string="Age from the Invoice Date",
        help="Count each amount's age from its invoice (accounting) date instead of its due date.",
    )
    x4u_default = fields.Boolean(string="Default in the Aged Partner Balance")


class AgedPartnerBalanceReportWizard(models.TransientModel):
    _inherit = "aged.partner.balance.report.wizard"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "age_partner_config_id" in fields_list and not res.get("age_partner_config_id"):
            config = self.env["account.age.report.configuration"].search(
                [("x4u_default", "=", True), ("company_id", "in", [self.env.company.id, False])], limit=1
            )
            if config:
                res["age_partner_config_id"] = config.id
        return res
