from odoo import _, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        # Spec §9 S6: the delivery of a line already invoiced brings its cost of sales (only while a
        # category still goes through GDNI; spec §20 P2 posts the cost of sales at the delivery).
        moves.filtered(lambda move: move.state == "done").sale_line_id._x4u_settle_cogs()
        return moves

    def _generate_valuation_lines_data(
        self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description
    ):
        """Spec §9: the finished product of an MO comes in at parts + extra cost (the 20% of a generator).
        WIP is credited with the parts only, so it closes at zero; the extra cost is credited to
        Applied Manufacturing Overhead, which offsets the real overheads in the P&L.

        Spec §20 P3: the serial is in the label of every stock entry (receipt, MO, delivery), and the
        cost of sales of a delivery carries the sales line's analytic (the Job Order's margin)."""
        serials = self.env["stock.valuation.layer"].browse(svl_id).lot_id or self.move_line_ids.lot_id
        if serials:
            description = "%s - SN %s" % (description, ", ".join(serials.mapped("name")))
        res = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description
        )
        distribution = self.sale_line_id.analytic_distribution
        if distribution:
            expense = self.product_id.product_tmpl_id.with_company(self.company_id).get_product_accounts()["expense"]
            for key in ("debit_line_vals", "credit_line_vals"):
                vals = res.get(key)
                if vals and expense and vals.get("account_id") == expense.id and not vals.get("analytic_distribution"):
                    vals["analytic_distribution"] = distribution
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
