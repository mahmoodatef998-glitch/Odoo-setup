from odoo import models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _update_move_date_deadline(self, new_date):
        """Odoo keeps the deadline of the moves a purchase line feeds (a Job Order's Pick Components)
        in step with the line's date. That is bookkeeping, not an edit of those transfers, so it runs
        with system rights: the Purchasing Officer (Receipts Only) could not even make an RFQ from a
        material request (found 2026-11-20 in the full cycle with the real roles)."""
        return super(PurchaseOrderLine, self.sudo())._update_move_date_deadline(new_date)
