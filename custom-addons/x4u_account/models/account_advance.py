"""The accounting team, 2026-11-27 (part 3):

- Payments straight to the bank: a bank or cash journal's payment methods post to the journal's own
  account (no Outstanding Receipts / Payments); the cheques keep their PDC accounts.
- Advances: a payment for a sales order goes to 216001 Advances from Customers (no VAT), a payment
  for a PO to 137012 Advances to Suppliers. The tax invoice (bill) of the order takes what it needs to
  the customer's (vendor's) account with a transfer entry and applies it, by itself.
"""
from odoo import Command, _, api, fields, models

from .account_payment_method import PDC


def _advance_account(env, company, kind):
    Account = env["account.account"].sudo().with_company(company)
    return Account.search(
        [*Account._check_company_domain(company), ("x4u_partner_advance", "=", kind), ("deprecated", "=", False)], limit=1
    )


class AccountMove(models.Model):
    _inherit = "account.move"

    x4u_advance_payment_id = fields.Many2one(
        "account.payment", string="Advance Of", copy=False, index="btree_not_null", readonly=True,
        help="On an advance transfer: the payment whose advance this entry takes to the customer's or vendor's account.",
    )


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x4u_advance_transfer_ids = fields.One2many(
        "account.move", "x4u_advance_payment_id", string="Advance Transfers", readonly=True,
    )

    def _x4u_advance_kind(self):
        """'customer' for money received for a sales order, 'vendor' for money paid for a PO."""
        self.ensure_one()
        if self.x4u_sale_order_id and self.partner_type == "customer" and self.payment_type == "inbound":
            return "customer"
        if self.x4u_purchase_order_id and self.partner_type == "supplier" and self.payment_type == "outbound":
            return "vendor"
        return False

    # Odoo's dependencies (account 18.0) plus the order of the advance.
    @api.depends("journal_id", "partner_id", "partner_type", "x4u_sale_order_id", "x4u_purchase_order_id")
    def _compute_destination_account_id(self):
        res = super()._compute_destination_account_id()
        for pay in self:
            if pay.move_id and pay.state != "draft":
                # Posted: the account stays the one on its entry.
                counterpart = pay._seek_for_lines()[1][:1]
                if counterpart:
                    pay.destination_account_id = counterpart.account_id
                continue
            kind = pay._x4u_advance_kind()
            account = kind and _advance_account(self.env, pay.company_id, kind)
            if account:
                pay.destination_account_id = account
        return res

    def _x4u_open_advance_lines(self):
        self.ensure_one()
        if not self.move_id or self.move_id.state != "posted":
            return self.env["account.move.line"]
        _liquidity, counterpart, _writeoff = self._seek_for_lines()
        return counterpart.filtered(lambda line: line.account_id.x4u_partner_advance and not line.reconciled)

    def _x4u_open_transfer_lines(self):
        """What a transfer took to the customer's (vendor's) account and no invoice took yet (the
        invoice was reset to draft, say)."""
        self.ensure_one()
        return self.sudo().x4u_advance_transfer_ids.filtered(lambda move: move.state == "posted").line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable") and not line.reconciled
        )

    def _x4u_open_counterpart_lines(self):
        lines = super()._x4u_open_counterpart_lines()
        if not self.move_id:
            return lines
        return lines | self._x4u_open_advance_lines() | self._x4u_open_transfer_lines()

    def _x4u_lines_for(self, document):
        lines = super()._x4u_lines_for(document)
        advance = self._x4u_open_advance_lines()
        if not advance:
            return lines
        company = document.company_id
        need = document.amount_residual - sum(
            line.currency_id._convert(abs(line.amount_residual_currency), document.currency_id, company, document.date)
            for line in lines
        )
        if document.currency_id.compare_amounts(need, 0.0) <= 0:
            return lines
        return lines | self._x4u_advance_transfer(document, advance, need)

    def _x4u_advance_transfer(self, document, advance, need):
        """Dr Advances from Customers / Cr Customer (or Dr Vendor / Cr Advances to Suppliers) for what
        `document` still needs (`need`, in its currency), out of the open `advance` lines."""
        self.ensure_one()
        company = document.company_id
        currency = advance.currency_id[:1]
        open_currency = sum(advance.mapped("amount_residual_currency"))
        open_balance = sum(advance.mapped("amount_residual"))
        if currency != document.currency_id:
            need = document.currency_id._convert(need, currency, company, document.date)
        if currency.compare_amounts(need, abs(open_currency)) >= 0:
            take_currency, take_balance = open_currency, open_balance
        else:
            take_currency = need if open_currency > 0 else -need
            take_balance = company.currency_id.round(open_balance * take_currency / open_currency)
        partner_account = document.line_ids.filtered(lambda line: line.display_type == "payment_term").account_id[:1]
        partner = document.commercial_partner_id
        label = _("Advance %(payment)s applied to %(document)s", payment=self.name, document=document.name)
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search([*Journal._check_company_domain(company), ("type", "=", "general")], limit=1)
        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": max(document.date, self.date),
                "ref": label,
                "x4u_advance_payment_id": self.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": label,
                            "account_id": advance.account_id[:1].id,
                            "partner_id": partner.id,
                            "currency_id": currency.id,
                            "amount_currency": -take_currency,
                            "balance": -take_balance,
                        }
                    ),
                    Command.create(
                        {
                            "name": label,
                            "account_id": partner_account.id,
                            "partner_id": partner.id,
                            "currency_id": currency.id,
                            "amount_currency": take_currency,
                            "balance": take_balance,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        (advance + move.line_ids.filtered(lambda line: line.account_id == advance.account_id[:1])).reconcile()
        return move.line_ids.filtered(lambda line: line.account_id == partner_account)

    def _x4u_undo_advance_transfers(self):
        """The payment is reset or its cheque bounced: its transfers are reversed, so the invoice (bill)
        is open again and the advance is back on the advances account."""
        for move in self.sudo().x4u_advance_transfer_ids.filtered(lambda m: m.state == "posted" and not m.reversal_move_ids):
            move.line_ids.remove_move_reconcile()
            move._reverse_moves(
                [{"date": fields.Date.context_today(self), "ref": _("Reversal of %s", move.ref)}], cancel=True
            )

    def _x4u_advance_documents(self):
        """The invoices (bills) the transfers of these payments were applied to."""
        lines = self.sudo().x4u_advance_transfer_ids.line_ids
        partials = lines.matched_debit_ids | lines.matched_credit_ids
        return (partials.debit_move_id.move_id | partials.credit_move_id.move_id).filtered(lambda move: move.is_invoice(True))

    def action_post(self):
        res = super().action_post()
        # Paid after the tax invoice (bill): it takes the payment at once.
        for pay in self.sudo():
            kind = pay._x4u_advance_kind()
            if kind == "customer":
                documents = pay.x4u_sale_order_id.invoice_ids.filtered(
                    lambda move: move.state == "posted" and move.move_type == "out_invoice" and move.payment_state in ("not_paid", "partial")
                )
                documents._x4u_apply_advances()
            elif kind == "vendor":
                documents = pay.x4u_purchase_order_id.invoice_ids.filtered(
                    lambda move: move.state == "posted" and move.move_type == "in_invoice" and move.payment_state in ("not_paid", "partial")
                )
                documents._x4u_apply_vendor_advances()
        return res

    def action_draft(self):
        self._x4u_undo_advance_transfers()
        return super().action_draft()


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        if not self.env.context.get("x4u_no_direct_payments"):
            journals._x4u_direct_payment_accounts()
        return journals

    def _x4u_direct_payment_accounts(self):
        """Payments straight to the bank (cash): each payment method of a bank or cash journal with no
        account or Outstanding Receipts / Payments posts to the journal's account. The cheques keep
        theirs (PDC Payable; the PDC Received journal)."""
        from odoo.addons.x4u_account.focus_chart import CODE
        from odoo.addons.x4u_account.hooks import _account

        for journal in self.sudo().filtered(lambda j: j.type in ("bank", "cash") and j.default_account_id):
            company = journal.company_id
            if journal == company.x4u_pdc_received_journal_id:
                continue
            outstanding = _account(self.env, company, CODE["outstanding_receipts"]) | _account(
                self.env, company, CODE["outstanding_payments"]
            )
            for line in journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids:
                if line.code == PDC:
                    continue
                if not line.payment_account_id or line.payment_account_id in outstanding:
                    line.payment_account_id = journal.default_account_id
