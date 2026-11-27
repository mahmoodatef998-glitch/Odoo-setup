from odoo import api, fields, models


class TrialBalanceReportWizard(models.TransientModel):
    """The accounting team, 2026-11-27: the Trial Balance opens from the first day of the fiscal year
    to today (like the General Ledger); the dates can still be changed."""

    _inherit = "trial.balance.report.wizard"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "date_from" in fields_list and "date_to" in fields_list and not res.get("date_from") and not res.get("date_to"):
            company = self.env["res.company"].browse(res.get("company_id")) or self.env.company
            today = fields.Date.context_today(self)
            res["date_from"] = company.compute_fiscalyear_dates(today)["date_from"]
            res["date_to"] = today
        return res
