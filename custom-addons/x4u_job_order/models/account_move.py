from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        """Spec v0.13 L4: the tax invoice of the order takes its generators still in the warehouse
        out to the customer, before it is posted, so the cost of sales is each generator's value."""
        today = fields.Date.context_today(self)
        for invoice in self.filtered(lambda m: m.move_type == "out_invoice" and m.state == "draft"):
            if soft and invoice.date and invoice.date > today:
                continue
            if not invoice._x4u_is_final_invoice():
                continue
            for order in invoice.invoice_line_ids.sale_line_ids.order_id.sudo():
                lots = order._x4u_generator_lots_in_stock()
                if lots:
                    order._x4u_ship_generators(lots, from_invoice=True)
        posted = super()._post(soft)
        posted._x4u_jobs()._x4u_refresh_profitability()
        return posted

    def button_draft(self):
        jobs = self._x4u_jobs()
        res = super().button_draft()
        jobs._x4u_refresh_profitability()
        return res

    def button_cancel(self):
        jobs = self._x4u_jobs()
        res = super().button_cancel()
        jobs._x4u_refresh_profitability()
        return res

    def _x4u_jobs(self):
        """Spec v0.14 H5: the Job Orders whose figures these entries change: their sales orders
        (tax invoice) and their analytic accounts (a vendor bill for transport, a crane)."""
        moves = self.sudo()
        jobs = moves.invoice_line_ids.sale_line_ids.order_id.x4u_job_ids
        account_ids = {
            int(account_id)
            for line in moves.line_ids
            for key in (line.analytic_distribution or {})
            for account_id in key.split(",")
        }
        if account_ids:
            Job = self.env["x4u.job.order"].sudo()
            jobs |= Job.search([("analytic_account_id", "in", list(account_ids))])
            jobs |= self.env["mrp.production"].sudo().search([("x4u_analytic_account_id", "in", list(account_ids))]).x4u_job_id
        return jobs
