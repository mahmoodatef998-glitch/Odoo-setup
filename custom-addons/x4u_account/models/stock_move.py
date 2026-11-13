from odoo import _, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        # Spec §9 S6: the delivery of a line already invoiced brings its cost of sales.
        moves.filtered(lambda move: move.state == "done").sale_line_id._x4u_settle_cogs()
        return moves

    def _generate_valuation_lines_data(
        self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description
    ):
        """Spec §9: the finished product of an MO comes in at parts + extra cost (the 20% of a generator).
        WIP is credited with the parts only, so it closes at zero; the extra cost is credited to
        Applied Manufacturing Overhead, which offsets the real overheads in the P&L."""
        res = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description
        )
        production = self.production_id
        overhead_account = self.company_id.x4u_overhead_applied_account_id
        if not (production and production.extra_cost and overhead_account and self.location_id.usage == "production"):
            return res
        if credit_value <= 0 or "credit_line_vals" not in res:
            return res
        currency = self.company_id.currency_id
        overhead = currency.round(min(production.extra_cost * qty, credit_value))
        if currency.is_zero(overhead):
            return res
        res["credit_line_vals"]["balance"] = -(credit_value - overhead)
        res["x4u_overhead_line_vals"] = {
            **res["credit_line_vals"],
            "balance": -overhead,
            "account_id": overhead_account.id,
            "name": "%s - %s" % (description, _("Applied overhead")),
        }
        return res
