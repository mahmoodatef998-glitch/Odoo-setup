from odoo import _, api, fields, models
from odoo.exceptions import UserError


class X4uSaleCheckConfirm(models.TransientModel):
    """The user, 2026-11-26 (fewer steps): the Accountant checks the customer PO and the transfer
    receipt, records the payment and confirms the order in one screen - what PO Matches Quotation,
    Register Payment and Confirm do one after the other. PO Doesn't Match stays on the order."""

    _name = "x4u.sale.check.confirm"
    _description = "Check the Customer PO and Confirm"

    order_id = fields.Many2one("sale.order", string="Sales Order", required=True, readonly=True)
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer")
    client_order_ref = fields.Char(related="order_id.client_order_ref", string="LPO Number")
    lpo_date = fields.Date(related="order_id.x4u_lpo_date", string="LPO Date")
    lpo_attachment_ids = fields.Many2many(related="order_id.x4u_lpo_attachment_ids", string="LPO File")
    payment_proof_ids = fields.Many2many(related="order_id.x4u_payment_proof_ids", string="Payment Receipts")
    currency_id = fields.Many2one(related="order_id.currency_id")
    amount_total = fields.Monetary(related="order_id.amount_total", string="Order Total")
    amount = fields.Monetary(
        string="Payment Received",
        help="The payment that came with the order (the transfer receipt). Zero when it is already recorded, "
        "or when the order is confirmed before any payment.",
    )
    journal_id = fields.Many2one(
        "account.journal", string="Received In",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(related="order_id.company_id")
    date = fields.Date(string="Payment Date", default=fields.Date.context_today)

    @api.model
    def _x4u_action(self, order):
        paid = order._x4u_first_payment_received()
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", order.company_id.id)], limit=1
        )
        wizard = self.create(
            {
                "order_id": order.id,
                "amount": 0.0 if paid else order._x4u_next_amount(),
                "journal_id": journal.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Check & Confirm %s", order.name),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        if self.amount < 0:
            raise UserError(_("The payment received can't be negative."))
        if not self.currency_id.is_zero(self.amount) and not self.journal_id:
            raise UserError(_("Choose where the payment was received (bank or cash)."))
        order.action_x4u_po_match()
        if not self.currency_id.is_zero(self.amount):
            payment = self.env["account.payment"].browse(order.action_x4u_register_payment()["res_id"])
            payment.write({"amount": self.amount, "journal_id": self.journal_id.id, "date": self.date})
            payment.action_post()
        order.action_confirm()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
