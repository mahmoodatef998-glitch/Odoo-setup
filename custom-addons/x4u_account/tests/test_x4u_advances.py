from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.x4u_account.focus_chart import CODE
from odoo.addons.x4u_account.hooks import _account, _outstanding_to_bank

# The modules, not the classes: their tests are not run again from here.
from odoo.addons.x4u_purchase.tests import test_vendor_payments as purchase_tests
from odoo.addons.x4u_sale.tests import test_payments as sale_tests

Sale = sale_tests.TestSalePayments
Purchase = purchase_tests.TestVendorPayments


def _balance(env, account, partner):
    lines = env["account.move.line"].search(
        [("account_id", "=", account.id), ("partner_id", "=", partner.id), ("parent_state", "=", "posted")]
    )
    return sum(lines.mapped("balance"))


@tagged("post_install", "-at_install")
class TestX4uCustomerAdvances(TransactionCase):
    """The accounting team, 2026-11-27 (part 3): payments straight to the bank, a sales order's
    payments on 216001 Advances from Customers until its tax invoice takes them."""

    # The Salesperson / Accountant steps of x4u_sale's tests.
    _quote = Sale._quote
    _file = Sale._file
    _attach_po = Sale._attach_po
    _attach_receipt = Sale._attach_receipt
    _pi = Sale._pi
    _send = Sale._send
    _pay = Sale._pay
    _sell = Sale._sell
    _tax_invoice = Sale._tax_invoice

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.tax = cls.env["account.tax"].create({"name": "X4U Test Adv VAT 5%", "amount": 5.0, "type_tax_use": "sale"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "X4U Test Advance Generator",
                "type": "service",
                "invoice_policy": "order",
                "list_price": 50000.0,
                "taxes_id": [Command.set(cls.tax.ids)],
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Advance Customer"})
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "X4U Test Advances", "currency_id": cls.company.currency_id.id}
        )
        cls.term = cls.env.ref("x4u_setup_base.payment_term_30_30_40")
        cls.accountant = new_test_user(
            cls.env, login="x4u_adv_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.salesperson = new_test_user(
            cls.env, login="x4u_adv_salesperson", groups="base.group_user,sales_team.group_sale_salesman"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)
        cls.advances = _account(cls.env, cls.company, CODE["customer_advances"])
        cls.receivable = cls.customer.property_account_receivable_id
        cls.outstanding = _account(cls.env, cls.company, CODE["outstanding_receipts"])

    def test_accounts(self):
        self.assertEqual(self.advances.x4u_partner_advance, "customer")
        self.assertEqual(self.advances.account_type, "liability_current")
        self.assertTrue(self.advances.reconcile)
        vendor_advances = _account(self.env, self.company, CODE["vendor_advances"])
        self.assertEqual(vendor_advances.x4u_partner_advance, "vendor")
        self.assertTrue(vendor_advances.reconcile)

    def test_journals_straight_to_the_bank(self):
        Journal = self.env["account.journal"]
        for journal in Journal.search([*Journal._check_company_domain(self.company), ("type", "in", ("bank", "cash"))]):
            for line in journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids:
                if journal == self.company.x4u_pdc_received_journal_id:
                    self.assertEqual(line.payment_account_id.code, "132001", "cheques in hand wait in PDC Received")
                elif line.code == "x4u_pdc":
                    self.assertFalse(line.payment_account_id, "PDC Payable until the bank pays the cheque")
                else:
                    self.assertEqual(line.payment_account_id, journal.default_account_id, journal.code)
        # A journal the Accountant adds later too.
        new = Journal.create({"name": "X4U Test Bank 2", "code": "XTB2", "type": "bank"})
        self.assertEqual(new.inbound_payment_method_line_ids.payment_account_id, new.default_account_id)

    def test_advance_until_the_tax_invoice(self):
        order = self._sell()
        payment = order.x4u_advance_payment_ids
        self.assertEqual(payment.destination_account_id, self.advances)
        self.assertEqual(payment.state, "paid", "straight to the bank")
        liquidity = payment._seek_for_lines()[0]
        self.assertEqual(liquidity.account_id, payment.journal_id.default_account_id)
        self.assertEqual(_balance(self.env, self.advances, self.customer), -15750.0, "30% received, no VAT on it")
        self.assertEqual(_balance(self.env, self.receivable, self.customer), 0.0)
        self.assertEqual(order.x4u_amount_advance, 15750.0)

        invoice = self._tax_invoice(order)
        self.assertEqual(invoice.amount_residual, 36750.0)
        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(_balance(self.env, self.advances, self.customer), 0.0, "the invoice took the advance")
        transfer = payment.x4u_advance_transfer_ids
        self.assertEqual(transfer.state, "posted")
        self.assertEqual(transfer.line_ids.filtered(lambda l: l.account_id == self.advances).debit, 15750.0)
        self.assertIn(order.x4u_proforma_id.name, invoice.message_ids[0].body)

        # Paid after the tax invoice: applied at once.
        self._pay(order)
        self.assertEqual(invoice.amount_residual, 21000.0)
        self.assertEqual(_balance(self.env, self.advances, self.customer), 0.0)
        self.assertEqual(order.x4u_amount_remaining, 21000.0)

    def test_reset_payment_opens_the_invoice(self):
        order = self._sell()
        payment = order.x4u_advance_payment_ids
        invoice = self._tax_invoice(order)
        self.assertEqual(invoice.amount_residual, 36750.0)
        payment.action_draft()
        self.env.invalidate_all()
        self.assertEqual(invoice.amount_residual, 52500.0, "the payment is no longer on the invoice")
        self.assertEqual(payment.x4u_advance_transfer_ids.reversal_move_ids.state, "posted")
        self.assertEqual(_balance(self.env, self.advances, self.customer), 0.0)
        self.assertEqual(_balance(self.env, self.receivable, self.customer), 52500.0)
        # Confirmed again: the invoice takes it again.
        payment.action_post()
        self.env.invalidate_all()
        self.assertEqual(invoice.amount_residual, 36750.0)

    def test_customer_accounts_show_the_advances(self):
        self._sell()
        action = self.env.ref("x4u_account.x4u_customer_accounts_action")
        lines = self.env["account.move.line"].search(safe_eval(action.domain) + [("partner_id", "=", self.customer.id)])
        self.assertIn(self.advances, lines.account_id)
        self.assertEqual(sum(lines.mapped("balance")), -15750.0)

    def test_outstanding_moves_to_the_bank(self):
        """An old payment still on Outstanding Receipts goes to the bank on the upgrade."""
        Journal = self.env["account.journal"]
        bank = Journal.search(
            [*Journal._check_company_domain(self.company), ("type", "=", "bank"), ("id", "!=", self.company.x4u_pdc_received_journal_id.id)],
            order="sequence",
            limit=1,
        )
        manual = bank.inbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        manual.payment_account_id = self.outstanding
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.customer.id,
                "amount": 700.0,
                "journal_id": bank.id,
                "payment_method_line_id": manual.id,
                "date": fields.Date.today(),
            }
        )
        payment.action_post()
        self.assertEqual(payment.state, "in_process")
        _outstanding_to_bank(self.env, self.company)
        self.env.invalidate_all()
        self.assertTrue(payment._seek_for_lines()[0].reconciled)
        self.assertTrue(payment.is_matched)
        self.assertEqual(_balance(self.env, bank.default_account_id, self.customer), 700.0)


@tagged("post_install", "-at_install")
class TestX4uVendorAdvances(TransactionCase):
    """A PO's payments on 137012 Advances to Suppliers until its bill takes them."""

    _order = Purchase._order
    _approve = Purchase._approve
    _attach_pi = Purchase._attach_pi
    _record_pi = Purchase._record_pi
    _pay = Purchase._pay
    _bill = Purchase._bill

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.tax = cls.env["account.tax"].create(
            {"name": "X4U Test Adv Purchase VAT 5%", "amount": 5.0, "type_tax_use": "purchase"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "X4U Test Advance Engine",
                "type": "service",
                "purchase_method": "purchase",
                "standard_price": 20000.0,
                "supplier_taxes_id": [Command.set(cls.tax.ids)],
            }
        )
        cls.term_50_50 = cls.env.ref("x4u_setup_base.payment_term_50_50")
        cls.vendor = cls.env["res.partner"].create(
            {"name": "X4U Test Advance Vendor", "property_supplier_payment_term_id": cls.term_50_50.id}
        )
        cls.buyer = new_test_user(cls.env, login="x4u_adv_buyer", groups="base.group_user,purchase.group_purchase_user")
        cls.manager = new_test_user(
            cls.env, login="x4u_adv_manager", groups="base.group_user,purchase.group_purchase_manager"
        )
        cls.accountant = new_test_user(
            cls.env, login="x4u_adv_v_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)
        cls.advances = _account(cls.env, cls.company, CODE["vendor_advances"])
        cls.payable = cls.vendor.property_account_payable_id

    def test_advance_until_the_bill(self):
        order = self._approve(self._order())
        self._attach_pi(order)
        payment = self._pay(self._record_pi(order))
        self.assertEqual(payment.destination_account_id, self.advances)
        self.assertEqual(payment.state, "paid", "straight to the bank")
        self.assertEqual(_balance(self.env, self.advances, self.vendor), 10500.0, "50% paid to the vendor")
        self.assertEqual(_balance(self.env, self.payable, self.vendor), 0.0)
        bill = self._bill(order)
        self.assertEqual(bill.amount_residual, 10500.0)
        self.assertEqual(_balance(self.env, self.advances, self.vendor), 0.0, "the bill took the advance")
        self.assertEqual(_balance(self.env, self.payable, self.vendor), -10500.0)
        self.assertEqual(order.x4u_amount_remaining, 10500.0)
