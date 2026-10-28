from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSalePayments(TransactionCase):
    """Spec §6 / §9 tests 7-12: proformas for the advances, one tax invoice before delivery."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax = cls.env["account.tax"].create({"name": "X4U Test VAT 5%", "amount": 5.0, "type_tax_use": "sale"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "X4U Test Generator Supply",
                "type": "service",
                "invoice_policy": "order",
                "list_price": 50000.0,
                "taxes_id": [Command.set(cls.tax.ids)],
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Payments Customer"})
        # The company currency: AED is only active where the UAE chart is (not on CI).
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "X4U Test Payments", "currency_id": cls.env.company.currency_id.id}
        )
        cls.term = cls.env.ref("x4u_setup_base.payment_term_30_30_40")
        cls.accountant = new_test_user(
            cls.env, login="x4u_pay_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.salesperson = new_test_user(
            cls.env, login="x4u_pay_salesperson", groups="base.group_user,sales_team.group_sale_salesman"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)

    def _sell(self, term=None):
        """S0xx: 50,000 + 5% VAT = 52,500."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "user_id": self.salesperson.id,
                "pricelist_id": self.pricelist.id,
                "payment_term_id": (term or self.term).id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 50000.0,
                            "tax_id": [Command.set(self.tax.ids)],
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        self.assertEqual(order.amount_total, 52500.0)
        return order

    def _proforma(self, order, percent=None, date_due=None, **values):
        """The Accountant: Proforma on the order, then Issue Proforma."""
        action = order.with_user(self.accountant).action_x4u_proforma()
        form = Form(self.env[action["res_model"]].with_user(self.accountant).with_context(**action["context"]))
        for name, value in values.items():
            setattr(form, name, value)
        if percent is not None:
            form.percent = percent
        if date_due:
            form.date_due = date_due
        result = form.save().action_confirm()
        return self.env["x4u.sale.proforma"].browse(result["res_id"])

    def _pay(self, proforma):
        """The Accountant: Register Payment on the proforma, then Confirm."""
        action = proforma.with_user(self.accountant).action_register_payment()
        payment = self.env["account.payment"].with_user(self.accountant).browse(action["res_id"])
        payment.action_post()
        return payment

    def _final_invoice(self, order):
        """The Accountant: Create Invoice › Regular invoice, then Confirm."""
        wizard = (
            self.env["sale.advance.payment.inv"]
            .with_user(self.accountant)
            .with_context(active_model="sale.order", active_ids=order.ids)
            .create({"advance_payment_method": "delivered"})
        )
        wizard.create_invoices()
        invoice = order.invoice_ids.filtered(lambda move: move.state == "draft")
        invoice.with_user(self.accountant).action_post()
        return invoice

    def _next_percent(self, order):
        return order.with_user(self.accountant).action_x4u_proforma()["context"]["default_percent"]

    # 7: a 30% proforma, numbered after the order, no journal entry, no invoice
    def test_proforma_amounts_and_number(self):
        order = self._sell()
        self.assertTrue(order.x4u_pay_before_delivery)
        self.assertEqual(self._next_percent(order), 30.0)
        moves_before = self.env["account.move"].search_count([])
        due = fields.Date.add(fields.Date.today(), days=7)
        proforma = self._proforma(order, date_due=due)
        self.assertEqual(proforma.name, "%s-PF1" % order.name)
        self.assertEqual(
            (proforma.percent, proforma.amount_untaxed, proforma.amount_tax, proforma.amount_total),
            (30.0, 15000.0, 750.0, 15750.0),
        )
        self.assertEqual(proforma.state, "not_paid")
        self.assertEqual(self.env["account.move"].search_count([]), moves_before)
        self.assertFalse(order.invoice_ids)
        # B8: a to-do for the Accountant on the due date
        self.assertEqual(proforma.activity_ids.user_id, self.accountant)
        self.assertEqual(proforma.activity_ids.date_deadline, due)
        html = self.env["ir.actions.report"]._render_qweb_html("x4u_sale.action_report_proforma", proforma.ids)[0]
        self.assertIn(b"This is not a tax invoice", html)
        self.assertIn(proforma.name.encode(), html)

    # 8: the payment from the proforma, linked to the order; the next proforma asks 30% again
    def test_payment_marks_the_proforma_paid(self):
        order = self._sell()
        proforma = self._proforma(order, date_due=fields.Date.today())
        payment = self._pay(proforma)
        self.assertEqual(payment.x4u_sale_order_id, order)
        self.assertEqual(payment.memo, proforma.name)
        self.assertEqual(payment.amount, 15750.0)
        self.assertEqual(proforma.state, "paid")
        self.assertFalse(proforma.activity_ids)
        order.invalidate_recordset()
        self.assertEqual(order.x4u_amount_advance, 15750.0)
        self.assertEqual(order.x4u_amount_remaining, 36750.0)
        self.assertFalse(order.invoice_ids)
        self.assertEqual(self._next_percent(order), 30.0)
        self.assertEqual(self._proforma(order).name, "%s-PF2" % order.name)
        # The last line of the terms is the final invoice, not a proforma.
        self.assertEqual(self._next_percent(order), 0.0)

    # 9: the final invoice applies the advances of its order, not those of another order
    def test_final_invoice_applies_the_advances(self):
        order = self._sell()
        self._pay(self._proforma(order))
        self._pay(self._proforma(order))
        other = self._sell()
        self._pay(self._proforma(other))
        invoice = self._final_invoice(order)
        self.assertEqual(invoice.amount_total, 52500.0)
        self.assertEqual(invoice.amount_residual, 21000.0)
        self.assertEqual(invoice.payment_state, "partial")
        self.assertIn("%s-PF1" % order.name, invoice.message_ids[0].body)
        order.invalidate_recordset()
        other.invalidate_recordset()
        self.assertEqual(order.x4u_amount_remaining, 21000.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        self.assertEqual(other.x4u_amount_remaining, 36750.0)
        self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({})._create_payments()
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))
        order.invalidate_recordset()
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertTrue(order.x4u_final_invoice_paid)

    # 10: a cancelled payment puts the proforma back to Not Paid; a proforma with a payment stays
    def test_cancel_rules(self):
        order = self._sell()
        proforma = self._proforma(order)
        payment = self._pay(proforma)
        with self.assertRaises(UserError):
            proforma.with_user(self.accountant).action_cancel()
        payment.with_user(self.accountant).action_cancel()
        self.assertEqual(proforma.state, "not_paid")
        order.invalidate_recordset()
        self.assertEqual(order.x4u_amount_advance, 0.0)
        proforma.with_user(self.accountant).action_cancel()
        self.assertEqual(proforma.state, "cancel")
        # The cancelled one does not count: the next proforma asks 30% again, with a new number.
        self.assertEqual(self._next_percent(order), 30.0)
        self.assertEqual(self._proforma(order).name, "%s-PF2" % order.name)

    def test_proforma_limits(self):
        order = self._sell()
        with self.assertRaises(UserError):
            self._proforma(order, percent=0)
        self._proforma(order, percent=60)
        with self.assertRaises(UserError):
            self._proforma(order, percent=50)
        fixed = self._proforma(order, advance_type="fixed", fixed_amount=20000.0)
        self.assertEqual((fixed.percent, fixed.amount_tax, fixed.amount_total), (40.0, 1000.0, 21000.0))

    # 100% advance: paid before any invoice, the final invoice is then paid by the advance
    def test_full_advance(self):
        order = self._sell(self.env.ref("x4u_setup_base.payment_term_advance_100"))
        proforma = self._proforma(order)
        self.assertEqual(proforma.amount_total, 52500.0)
        self._pay(proforma)
        order.invalidate_recordset()
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        invoice = self._final_invoice(order)
        self.assertEqual(invoice.amount_residual, 0.0)
        order.invalidate_recordset()
        self.assertTrue(order.x4u_final_invoice_paid)
        self.assertFalse(self.env.ref("x4u_setup_base.payment_term_60_days").x4u_pay_before_delivery)

    # 12: the Salesperson sees and prints the proformas of his orders, makes none, invoices nothing
    def test_salesperson_rights(self):
        order = self._sell()
        proforma = self._proforma(order)
        self._pay(proforma)
        self.assertEqual(proforma.with_user(self.salesperson).state, "paid")
        self.env["ir.actions.report"].with_user(self.salesperson)._render_qweb_html(
            "x4u_sale.action_report_proforma", proforma.ids
        )
        as_salesperson = order.with_user(self.salesperson)
        as_salesperson.invalidate_recordset()
        self.assertEqual(as_salesperson.x4u_amount_advance, 15750.0)
        self.assertEqual(as_salesperson.x4u_proforma_count, 1)
        with self.assertRaises(AccessError):
            self.env["x4u.sale.proforma.wizard"].with_user(self.salesperson).create(
                {"order_id": order.id, "percent": 30.0}
            )
        wizard = (
            self.env["sale.advance.payment.inv"]
            .with_user(self.salesperson)
            .with_context(active_model="sale.order", active_ids=order.ids)
            .create({"advance_payment_method": "delivered"})
        )
        with self.assertRaises(AccessError):
            wizard.create_invoices()
        other = new_test_user(self.env, login="x4u_pay_other_sales", groups="base.group_user,sales_team.group_sale_salesman")
        self.assertFalse(self.env["x4u.sale.proforma"].with_user(other).search([("id", "=", proforma.id)]))
