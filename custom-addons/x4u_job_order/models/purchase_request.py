from odoo import _, models
from odoo.exceptions import UserError


class PurchaseRequestLineMakePurchaseOrder(models.TransientModel):
    _inherit = "purchase.request.line.make.purchase.order"

    def _check_valid_request_line(self, request_line_ids):
        """Spec v0.6 R4: a closed line (its Job Order got the part from stock) is never bought."""
        closed = self.env["purchase.request.line"].browse(request_line_ids).filtered("cancelled")
        if closed:
            raise UserError(
                _(
                    "These lines are closed because their Job Order got the part from stock: %s",
                    ", ".join("%s (%s)" % (line.product_id.display_name, line.request_id.name) for line in closed),
                )
            )
        return super()._check_valid_request_line(request_line_ids)
