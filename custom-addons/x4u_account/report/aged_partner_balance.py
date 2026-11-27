from odoo import models


class AgedPartnerBalanceReport(models.AbstractModel):
    """The accounting team, 2026-11-27: with a configuration ticked Age from the Invoice Date, each
    amount is aged from its date instead of its due date (AccountMoveLine.search_read swaps them)."""

    _inherit = "report.account_financial_report.aged_partner_balance"

    def _get_move_lines_data(self, *args, **kwargs):
        config = self.env.context.get("age_partner_config")
        report = self
        if config and config.x4u_from_invoice_date:
            report = self.with_context(x4u_age_from_date=True)
        return super(AgedPartnerBalanceReport, report)._get_move_lines_data(*args, **kwargs)
