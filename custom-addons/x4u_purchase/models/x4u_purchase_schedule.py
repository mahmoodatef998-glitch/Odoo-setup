from odoo import api, fields, models


class X4uPurchaseSchedule(models.Model):
    """P4: the payments agreed with the vendor, from the PO's terms or written by Purchasing (Custom)."""

    _name = "x4u.purchase.schedule"
    _inherit = "x4u.payment.schedule.mixin"
    _description = "Purchase Payment Schedule"

    order_id = fields.Many2one(
        "purchase.order", string="Purchase Order", required=True, ondelete="cascade", index=True
    )
    proforma_id = fields.Many2one(
        "x4u.purchase.proforma", string="Vendor PI", index="btree_not_null", ondelete="set null"
    )
    currency_id = fields.Many2one(related="order_id.currency_id")

    @api.depends(
        "percent",
        "sequence",
        "order_id.x4u_schedule_ids",
        "order_id.amount_untaxed",
        "order_id.amount_tax",
        "order_id.x4u_amount_remaining",
    )
    def _compute_x4u_amounts(self):
        return super()._compute_x4u_amounts()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._x4u_check_change(set().union(*vals_list))
        return lines

    def write(self, vals):
        self._x4u_check_change(set(vals))
        return super().write(vals)

    def unlink(self):
        self._x4u_check_change({"percent"})
        return super().unlink()

    def _x4u_check_change(self, changed):
        """Purchasing writes the Custom schedule until the General Manager approves the PO;
        the Accountant only sets the due dates. The order's own changes skip this (sync)."""
        if self.env.context.get("x4u_schedule_sync") or self.env.su:
            return
        if changed <= {"date_due"}:
            if not self.env.user.has_group("account.group_account_invoice"):
                raise self.env["sale.order"]._x4u_accountant_only()
            return
        for order in self.order_id:
            order._x4u_check_schedule_editable()
