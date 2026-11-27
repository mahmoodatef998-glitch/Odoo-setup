from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .account_payment import OPEN_PDC_STATES


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self):
        """A bill or invoice paid by a cheque the bank has not paid yet is In Payment, not Paid
        (spec §2 P8, §12). Only cheques: other payments keep Odoo Community's behaviour (Paid at once)."""
        state = super()._get_invoice_in_payment_state()
        if state == "paid" and len(self) == 1:
            if any(pay.x4u_pdc_state in OPEN_PDC_STATES for pay in self.sudo()._get_reconciled_payments()):
                return "in_payment"
        return state

    # Odoo's dependencies (account 18.0) plus the cheque status.
    @api.depends(
        "amount_residual", "move_type", "state", "company_id", "reconciled_payment_ids.state",
        "reconciled_payment_ids.x4u_pdc_state",
    )
    def _compute_payment_state(self):
        """A deposited customer cheque is matched in PDC Received, so Odoo says Paid; it stays
        In Payment until the bank clears it (spec §12 K4)."""
        res = super()._compute_payment_state()
        for move in self:
            if move.payment_state == "paid" and move.is_invoice(True) and any(
                pay.x4u_pdc_state in OPEN_PDC_STATES for pay in move.sudo().reconciled_payment_ids
            ):
                move.payment_state = "in_payment"
        return res

    def _stock_account_prepare_anglo_saxon_out_lines_vals(self):
        """Spec §20 P2: the cost of sales is posted by the delivery (Dr Cost of Sales / Cr Inventory),
        so the stock output account is the cost of sales itself. Odoo would still add Dr and Cr Cost
        of Sales on the invoice, the same amount on the same account: they are left out."""
        vals_list = super()._stock_account_prepare_anglo_saxon_out_lines_vals()
        accounts = {}
        for vals in vals_list:
            accounts.setdefault(vals.get("cogs_origin_id"), set()).add(vals.get("account_id"))
        return [vals for vals in vals_list if len(accounts[vals.get("cogs_origin_id")]) > 1]

    def _x4u_check_trn(self):
        """Spec §21 V2: an invoice, bill or credit note of a UAE company to a VAT registered contact is
        confirmed only with its TRN (FTA: the recipient's TRN is on the tax invoice)."""
        missing = self.filtered(
            lambda move: move.is_invoice()
            and move.company_id.account_fiscal_country_id.code == "AE"
            and move.commercial_partner_id.x4u_vat_registered
            and not move.commercial_partner_id.vat
        )
        if missing:
            raise UserError(
                _(
                    "%(partners)s is VAT registered but has no TRN. Add the TRN on the contact before confirming %(moves)s.",
                    partners=", ".join(sorted(set(missing.commercial_partner_id.mapped("display_name")))),
                    moves=", ".join(missing.mapped("display_name")),
                )
            )

    @api.model
    def _x4u_cron_due_reminder(self, days=2):
        """The accounting team, 2026-11-27: a to-do for the Accountant (Settings › Sales › Accountant)
        on each open customer invoice and vendor bill due in the next ``days`` days, once per amount due.
        Daily; a day the server is off is caught the next day."""
        user_id = int(self.env["ir.config_parameter"].sudo().get_param("x4u_sale.accountant_user_id") or 0)
        user = self.env["res.users"].sudo().browse(user_id).exists()
        if not user:
            return
        today = fields.Date.context_today(self)
        lines = self.env["account.move.line"].sudo().search([
            ("company_id", "in", user.company_ids.ids),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ("reconciled", "=", False),
            ("amount_residual", "!=", 0),
            ("date_maturity", ">=", today),
            ("date_maturity", "<=", fields.Date.add(today, days=days)),
        ])
        for line in lines.filtered(lambda l: l.move_id.is_invoice(True)):
            move = line.move_id
            summary = _("Due on %s", fields.Date.to_string(line.date_maturity))
            if move.activity_ids.filtered(lambda a, s=summary: a.user_id == user and a.summary == s):
                continue
            sale = move.is_sale_document(True)
            note = _(
                "%(what)s %(move)s of %(partner)s: %(amount)s due on %(date)s. %(todo)s",
                what=_("Customer invoice") if sale else _("Vendor bill"),
                move=move.name,
                partner=move.commercial_partner_id.display_name,
                amount=move.currency_id.format(abs(line.amount_residual_currency)),
                date=fields.Date.to_string(line.date_maturity),
                todo=_("Follow up the collection.") if sale else _("Prepare the payment."),
            )
            move.activity_schedule(
                "mail.mail_activity_data_todo", date_deadline=line.date_maturity, summary=summary,
                note=note, user_id=user.id,
            )

    def _post(self, soft=True):
        self._x4u_check_trn()
        posted = super()._post(soft)
        # Spec §9 S6: a line delivered before its invoice is settled by Odoo's own cost of sales;
        # one invoiced first is settled here when the delivery has also come.
        posted.filtered(lambda move: move.is_sale_document()).invoice_line_ids.sale_line_ids._x4u_settle_cogs()
        return posted


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        records = super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order, **read_kwargs)
        # The accounting team, 2026-11-27: the Aged Partner Balance ages from the invoice date when its
        # configuration says so (report.account_financial_report.aged_partner_balance sets the flag).
        if self.env.context.get("x4u_age_from_date") and fields and "date_maturity" in fields and "date" in fields:
            for record in records:
                record["date_maturity"] = record["date"]
        return records

    x4u_deposit_payment_id = fields.Many2one(
        "account.payment", string="Deposited Cheque", copy=False, index="btree_not_null", readonly=True,
        help="On a cheque deposit entry: the customer cheque of this bank line (spec §12 K4).",
    )
    x4u_counterpart = fields.Char(
        string="Counterpart", compute="_compute_x4u_counterpart",
        help="The other side of the entry: where the amount came from or went (spec §22 G1), e.g. a petty cash "
        "payment shows 530xxx Fuel. The largest amounts first.",
    )
    x4u_cogs_sale_line_id = fields.Many2one(
        "sale.order.line", string="Cost of Sales For", copy=False, index="btree_not_null", readonly=True,
        help="Cost of sales posted when the delivery came after the invoice (spec §9 S6).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Spec §10: a bill line of a landed cost service is a landed cost line however it is made
        (from a PO, an import, code), not only when the product is picked on the screen."""
        Product = self.env["product.product"]
        for vals in vals_list:
            if "is_landed_costs_line" not in vals and vals.get("product_id"):
                product = Product.browse(vals["product_id"])
                if product.landed_cost_ok and product.type == "service":
                    vals["is_landed_costs_line"] = True
        return super().create(vals_list)

    @api.depends("move_id.line_ids.account_id", "move_id.line_ids.balance")
    def _compute_x4u_counterpart(self):
        for line in self:
            others = line.move_id.line_ids - line
            # The opposite side (debit for a credit line); a zero line takes every other line.
            opposite = others.filtered(lambda other, l=line: (other.balance > 0) != (l.balance > 0) and other.balance)
            names = []
            for other in (opposite if line.balance else others).sorted(lambda o: -abs(o.balance)):
                name = "%s %s" % (other.account_id.code, other.account_id.name)
                if other.account_id != line.account_id and name not in names:
                    names.append(name)
            line.x4u_counterpart = ", ".join(names[:3]) + (" +%d" % (len(names) - 3) if len(names) > 3 else "")
