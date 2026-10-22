from odoo import _, models
from odoo.tools.misc import format_amount

APPROVAL = "x4u_setup_base.mail_activity_type_po_approval"


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _x4u_ask_approval(self):
        """A to-do for each approver of an order waiting for approval (guide R2)."""
        approvers = self.env.ref("purchase.group_purchase_manager").users.filtered(lambda user: not user.share)
        activity_type = self.env.ref(APPROVAL)
        for order in self.filtered(lambda o: o.state == "to approve"):
            told = order.activity_ids.filtered(lambda a: a.activity_type_id == activity_type).user_id
            summary = _(
                "Approve %(order)s · %(vendor)s · %(amount)s",
                order=order.name,
                vendor=order.partner_id.display_name,
                amount=format_amount(self.env, order.amount_total, order.currency_id),
            )
            for user in approvers.filtered(lambda u, o=order: u not in told and u.company_ids & o.company_id):
                order.activity_schedule(APPROVAL, user_id=user.id, summary=summary)

    def _x4u_close_approval(self):
        """The approver's to-do is done; the other approvers' ones go away."""
        self.activity_feedback([APPROVAL], user_id=self.env.user.id, feedback=_("Approved"))
        self._x4u_drop_approval()

    def _x4u_drop_approval(self):
        # sudo: a user may only delete the activities they created or were given,
        # and these were created for every approver.
        self.sudo().activity_unlink([APPROVAL])

    def button_confirm(self):
        res = super().button_confirm()
        self._x4u_ask_approval()
        return res

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        self.filtered(lambda o: o.state in ("purchase", "done"))._x4u_close_approval()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._x4u_drop_approval()
        return res

    def button_draft(self):
        res = super().button_draft()
        self._x4u_drop_approval()
        return res
