from odoo import api, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _x4u_job_orders(self):
        # Confirmed POs keep the link on their receipt moves, not on the lines.
        lines = self.order_line
        return self.env["mrp.production"].sudo()._x4u_from_moves(lines.move_dest_ids | lines.move_ids.move_dest_ids)

    def _x4u_log_job_orders(self, event_type):
        for order in self.filtered(lambda o: o.state in ("purchase", "done")):
            order._x4u_job_orders()._x4u_log(
                event_type,
                document=order,
                detail=order.partner_id.display_name,
                date=order.date_approve if event_type == "po_approved" else None,
            )

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        self._x4u_log_job_orders("po_approved")
        return res

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        # Odoo sets this context when the PO is sent to the vendor by email.
        if self.env.context.get("mark_rfq_as_sent"):
            self._x4u_log_job_orders("po_sent")
        return message


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for order in lines.order_id:
            order_lines = lines.filtered(lambda line, o=order: line.order_id == o)
            productions = self.env["mrp.production"].sudo()._x4u_from_moves(order_lines.move_dest_ids)
            productions._x4u_log("rfq_created", document=order, detail=order.partner_id.display_name)
        return lines
