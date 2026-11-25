from odoo import models


class GeneralLedgerReport(models.AbstractModel):
    """Spec §22 G1: the counterpart account of every line in the General Ledger family
    (General Ledger, Partner / Customer / Vendor Ledger, Bank and Cash Books)."""

    _inherit = "report.account_financial_report.general_ledger"

    def _get_ml_fields(self):
        return super()._get_ml_fields() + ["x4u_counterpart"]

    def _get_move_line_data(self, move_line):
        data = super()._get_move_line_data(move_line)
        data["x4u_counterpart"] = move_line.get("x4u_counterpart") or ""
        return data
