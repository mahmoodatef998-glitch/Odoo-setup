from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_amount

from odoo.addons.x4u_sale.models.x4u_sale_proforma import POSTED_PAYMENT_STATES


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('state', 'in', ('purchase', 'done')), ('partner_id.commercial_partner_id', '=', x4u_commercial_partner_id)]",
        help="An advance for this PO: the vendor bill of the PO applies it by itself.",
    )
    x4u_purchase_proforma_id = fields.Many2one(
        "x4u.purchase.proforma",
        string="Vendor PI",
        index="btree_not_null",
        copy=False,
        tracking=True,
        domain="[('order_id', '=', x4u_purchase_order_id), ('state', '=', 'open')]",
    )

    @api.onchange("x4u_purchase_proforma_id")
    def _onchange_x4u_purchase_proforma_id(self):
        proforma = self.x4u_purchase_proforma_id
        if proforma:
            self.x4u_purchase_order_id = proforma.order_id
            self.amount = proforma.amount_due_now
            self.memo = self.memo or proforma.name

    @api.constrains("x4u_purchase_order_id", "x4u_purchase_proforma_id", "partner_id", "payment_type", "partner_type")
    def _check_x4u_purchase_order(self):
        for payment in self:
            order = payment.x4u_purchase_order_id
            proforma = payment.x4u_purchase_proforma_id
            if proforma and proforma.order_id != order:
                raise ValidationError(_("Vendor PI %s belongs to another purchase order.", proforma.name))
            if order and (
                payment.payment_type != "outbound"
                or payment.partner_type != "supplier"
                or payment.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id
            ):
                raise ValidationError(_("Only money paid to the vendor of %s can be an advance for it.", order.name))

    def action_post(self):
        res = super().action_post()
        # The vendor PI suggests the next payment of the schedule again.
        self.x4u_purchase_proforma_id.sudo().amount_due_manual = 0.0
        self._x4u_log_on_purchase_order(_("Payment sent"))
        return res

    def action_cancel(self):
        self._x4u_log_on_purchase_order(_("Payment cancelled"))
        return super().action_cancel()

    def _x4u_log_on_purchase_order(self, label):
        for payment in self.filtered("x4u_purchase_order_id"):
            payment.x4u_purchase_order_id.sudo().message_post(
                body=_(
                    "%(label)s: %(amount)s (%(ref)s)",
                    label=label,
                    amount=format_amount(self.env, payment.amount, payment.currency_id),
                    ref=payment.x4u_purchase_proforma_id.name or payment.name,
                )
            )


class AccountMove(models.Model):
    _inherit = "account.move"

    # UAT Phase 2.3: the bill of a receipt - its lines are what came in, the receipt's Delivery Note
    # and the PO's documents come with it.
    x4u_receipt_id = fields.Many2one(
        "stock.picking", string="Receipt", copy=False, index="btree_not_null",
        domain="[('picking_type_code', '=', 'incoming'), ('state', '=', 'done'), ('x4u_billed', '=', False), "
        "('company_id', '=', company_id), ('partner_id', 'child_of', commercial_partner_id or partner_id)]",
        help="A validated receipt of this vendor: the bill takes the quantities received, its Delivery Note and the purchase order's documents.",
    )

    @api.onchange("x4u_receipt_id")
    def _onchange_x4u_receipt_id(self):
        receipt = self.x4u_receipt_id
        if not receipt or self.move_type != "in_invoice":
            return
        order = receipt.purchase_id
        if not self.partner_id:
            self.partner_id = (order.partner_id or receipt.partner_id).commercial_partner_id
        if not self.ref and receipt.x4u_vendor_ref:
            self.ref = receipt.x4u_vendor_ref
        if order:
            self.currency_id = order.currency_id
            self.invoice_origin = self.invoice_origin or order.name
            if order.payment_term_id:
                self.invoice_payment_term_id = order.payment_term_id
            if order.fiscal_position_id:
                self.fiscal_position_id = order.fiscal_position_id
        on_bill = self.invoice_line_ids.purchase_line_id
        new_lines = self.env["account.move.line"]
        for move in receipt.move_ids.filtered(lambda m: m.state == "done" and m.purchase_line_id and m.purchase_line_id not in on_bill):
            line = move.purchase_line_id
            vals = line._prepare_account_move_line(self)
            vals["quantity"] = move.product_uom._compute_quantity(move.quantity, line.product_uom)
            new_lines += new_lines.new(vals)
        self.invoice_line_ids += new_lines

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered("x4u_receipt_id")._x4u_attach_receipt_documents()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if vals.get("x4u_receipt_id"):
            self._x4u_attach_receipt_documents()
        return res

    def _x4u_attach_receipt_documents(self):
        """The receipt's Delivery Note and the purchase order's documents on the bill, for checking;
        the Accountant's "Vendor bill" task of that receipt is done."""
        Attachment = self.env["ir.attachment"].sudo()
        for bill in self:
            receipt = bill.x4u_receipt_id.sudo()
            order = receipt.purchase_id
            # The 3-way match: each line of the bill is its purchase order line. The bill form shows
            # that link to Purchase users only, so an Accountant's save drops it; it is set here.
            by_product = {}
            for move in receipt.move_ids.filtered(lambda m: m.state == "done" and m.purchase_line_id):
                by_product.setdefault(move.product_id, move.purchase_line_id)
            for line in bill.sudo().invoice_line_ids.filtered(lambda l: l.product_id and not l.purchase_line_id):
                if line.product_id in by_product:
                    line.purchase_line_id = by_product[line.product_id]
            sources = receipt.x4u_delivery_note_ids | Attachment.search([("res_model", "=", "stock.picking"), ("res_id", "=", receipt.id)])
            if order:
                sources |= Attachment.search([("res_model", "=", "purchase.order"), ("res_id", "=", order.id)])
            have = set(Attachment.search([("res_model", "=", "account.move"), ("res_id", "=", bill.id)]).mapped("checksum"))
            copies = Attachment
            for attachment in sources:
                if attachment.checksum and attachment.checksum in have:
                    continue
                have.add(attachment.checksum)
                copies |= attachment.copy({"res_model": "account.move", "res_id": bill.id})
            if copies:
                bill.message_post(
                    body=_("Documents of %s: the vendor's Delivery Note and the purchase order.", receipt.name),
                    attachment_ids=copies.ids,
                )
            if order:
                self.env["mail.activity"].sudo().search(
                    [("res_model", "=", "purchase.order"), ("res_id", "=", order.id), ("summary", "=", _("Vendor bill: %s", receipt.name))]
                ).action_feedback(feedback=_("Bill recorded."))

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda move: move.move_type == "in_invoice")._x4u_apply_vendor_advances()
        return posted

    def _x4u_apply_vendor_advances(self):
        """P8: the bill of a PO applies the advances paid for it."""
        Payment = self.env["account.payment"].sudo()
        for bill in self:
            orders = bill.invoice_line_ids.purchase_line_id.order_id
            if not orders:
                continue
            payments = Payment.search(
                [("x4u_purchase_order_id", "in", orders.ids), ("state", "in", POSTED_PAYMENT_STATES)], order="date, id"
            )
            bill._x4u_assign_payments(payments, lambda payment: payment.x4u_purchase_proforma_id.name)
