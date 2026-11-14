import base64

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSalePayments(TransactionCase):
    """Spec v0.7 §0 (O1-O10) and §6: the Salesperson sends the customer PO and the first payment,
    the Accountant checks, records and confirms; a PI for each payment; one tax invoice."""

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
        cls.custom = cls.env.ref("x4u_sale.payment_term_custom")
        cls.check_type = cls.env.ref("x4u_sale.mail_activity_type_po_check")
        cls.fix_type = cls.env.ref("x4u_sale.mail_activity_type_po_fix")
        cls.accountant = new_test_user(
            cls.env, login="x4u_pay_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.salesperson = new_test_user(
            cls.env, login="x4u_pay_salesperson", groups="base.group_user,sales_team.group_sale_salesman"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)

    def _quote(self, term=None):
        """The Salesperson's quotation: 50,000 + 5% VAT = 52,500."""
        return self.env["sale.order"].with_user(self.salesperson).create(
            {
                "partner_id": self.customer.id,
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

    def _file(self, name, order):
        return self.env["ir.attachment"].with_user(self.salesperson).create(
            {"name": name, "datas": base64.b64encode(b"%PDF-1.4"), "res_model": "sale.order", "res_id": order.id}
        )

    def _attach_po(self, order):
        order.write(
            {
                "client_order_ref": "PO-123",
                "x4u_lpo_date": fields.Date.today(),
                "x4u_lpo_attachment_ids": [Command.set(self._file("PO-123.pdf", order).ids)],
            }
        )

    def _attach_receipt(self, order, name="Transfer-1.pdf"):
        order.write({"x4u_payment_proof_ids": [Command.link(self._file(name, order).id)]})

    def _send(self, term=None):
        """The Salesperson: the quotation with the customer PO and the first payment receipt."""
        order = self._quote(term)
        self._attach_po(order)
        if order.x4u_advance_due:
            self._attach_receipt(order)
        order.action_x4u_send_to_accountant()
        self.assertEqual(order.amount_total, 52500.0)
        return order

    def _pay(self, order, amount=None):
        """The Accountant: Register Payment on the order, then Confirm the payment (its PI comes)."""
        action = order.with_user(self.accountant).action_x4u_register_payment()
        payment = self.env["account.payment"].with_user(self.accountant).browse(action["res_id"])
        if amount is not None:
            payment.amount = amount
        payment.action_post()
        self.env.invalidate_all()
        return payment

    def _sell(self, term=None):
        """Sent by the Salesperson; the Accountant: PO Matches, the first payment, Confirm."""
        order = self._send(term)
        as_accountant = order.with_user(self.accountant)
        as_accountant.action_x4u_po_match()
        if order.x4u_advance_due:
            self._pay(order)
        as_accountant.action_confirm()
        return order.with_env(self.env)

    def _tax_invoice(self, order):
        """The Accountant: Create Tax Invoice on the order, then Confirm."""
        action = order.with_user(self.accountant).action_x4u_create_tax_invoice()
        invoice = self.env["account.move"].with_user(self.accountant).browse(action["res_id"])
        invoice.action_post()
        self.env.invalidate_all()
        return invoice

    def _todo(self, order, activity_type):
        return order.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)

    # A new quotation saved from the form, like in the browser (2026-11-14: the schedule lines were
    # saved twice without their percentage, "a mandatory field is not set")
    def test_new_quotation_from_the_form(self):
        with Form(self.env["sale.order"].with_user(self.salesperson)) as form:
            form.partner_id = self.customer
            form.pricelist_id = self.pricelist
            form.payment_term_id = self.term
            with form.order_line.new() as line:
                line.product_id = self.product
                line.price_unit = 50000.0
        order = form.record
        self.assertEqual(order.x4u_schedule_ids.mapped("percent"), [30.0, 30.0, 40.0])
        accountant_form = Form(order.with_user(self.accountant))
        accountant_form.save()
        self.assertEqual(len(order.x4u_schedule_ids), 3)

    # O2: the quotation goes to the Accountant only with the customer PO and the first payment
    def test_send_to_accountant(self):
        order = self._quote()
        self.assertTrue(order.x4u_advance_due, "30/30/40: a payment comes with the order")
        with self.assertRaisesRegex(UserError, "customer PO"):
            order.action_x4u_send_to_accountant()
        self._attach_po(order)
        with self.assertRaisesRegex(UserError, "first payment"):
            order.action_x4u_send_to_accountant()
        # A file uploaded before it was linked belongs to the order: the Accountant opens it.
        loose = self.env["ir.attachment"].with_user(self.salesperson).create(
            {"name": "Transfer-1.pdf", "datas": base64.b64encode(b"%PDF-1.4")}
        )
        order.write({"x4u_payment_proof_ids": [Command.link(loose.id)]})
        self.assertEqual(loose.with_user(self.accountant).read(["name"])[0]["name"], "Transfer-1.pdf")
        order.action_x4u_send_to_accountant()
        self.assertEqual((order.state, order.x4u_po_check), ("draft", "to_check"))
        self.assertEqual(self._todo(order, self.check_type).user_id, self.accountant)
        # The Salesperson does not confirm any more, nor changes what the Accountant checks.
        with self.assertRaises(AccessError):
            order.action_confirm()
        with self.assertRaisesRegex(UserError, "with the Accountant"):
            order.write({"order_line": [Command.update(order.order_line.id, {"product_uom_qty": 2})]})
        with self.assertRaises(AccessError):
            order.write({"x4u_po_check": "match"})

    # O3-O5: Doesn't Match goes back; the Accountant confirms after the match and the first payment
    def test_accountant_confirms(self):
        order = self._send()
        as_accountant = order.with_user(self.accountant)
        with self.assertRaisesRegex(UserError, "check the customer PO"):
            as_accountant.action_confirm()
        self.env["x4u.sale.po.mismatch"].with_user(self.accountant).create(
            {"order_id": order.id, "reason": "The PO says 400 kVA"}
        ).action_confirm()
        self.assertEqual(order.x4u_po_check, "mismatch")
        fix = self._todo(order, self.fix_type)
        self.assertEqual(fix.user_id, self.salesperson)
        self.assertIn("400 kVA", fix.summary)
        # The Salesperson fixes it with the customer and sends it again.
        order.write({"order_line": [Command.update(order.order_line.id, {"name": "Generator 500 kVA, as on the PO"})]})
        order.action_x4u_send_to_accountant()
        self.assertEqual(order.x4u_po_check, "to_check")
        self.assertFalse(self._todo(order, self.fix_type))
        as_accountant.action_x4u_po_match()
        self.assertEqual(order.x4u_po_check_user_id, self.accountant)
        with self.assertRaisesRegex(UserError, "first payment"):
            as_accountant.action_confirm()
        moves_before = self.env["account.move"].search_count([("move_type", "=", "out_invoice")])
        payment = self._pay(order)
        self.assertEqual((payment.amount, payment.x4u_sale_order_id), (15750.0, order))
        proforma = payment.x4u_proforma_id
        self.assertEqual(proforma.name, "%s-PI1" % order.name)
        self.assertEqual(
            (proforma.amount_payment, proforma.amount_paid, proforma.amount_remaining), (15750.0, 15750.0, 36750.0)
        )
        as_accountant.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertTrue(order.locked)
        self.assertFalse(self._todo(order, self.check_type))
        self.assertEqual(self.env["account.move"].search_count([("move_type", "=", "out_invoice")]), moves_before)

    # O2 / O5: terms with no payment with the order go with the customer PO only
    def test_no_advance_terms(self):
        order = self._quote(self.env.ref("x4u_setup_base.payment_term_60_days"))
        self.assertFalse(order.x4u_advance_due)
        self._attach_po(order)
        order.action_x4u_send_to_accountant()
        order.with_user(self.accountant).action_x4u_po_match()
        order.with_user(self.accountant).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(order.with_env(self.env).x4u_proforma_ids)

    # O6: a PI for each payment, after it came in: what is paid to date and what is left
    def test_pi_per_payment(self):
        order = self._sell()
        self._pay(order, amount=10000.0)
        first, second = order.x4u_proforma_ids.sorted("sequence")
        self.assertEqual(second.name, "%s-PI2" % order.name)
        self.assertEqual(
            (second.amount_payment, second.amount_paid, second.amount_remaining), (10000.0, 25750.0, 26750.0)
        )
        self.assertEqual((first.amount_paid, first.amount_remaining), (15750.0, 36750.0), "PI1 keeps its own numbers")
        self.assertEqual(order.x4u_schedule_ids.mapped("state"), ["paid", "partial", "not_paid"])
        self.assertEqual((order.x4u_amount_advance, order.x4u_amount_remaining), (25750.0, 26750.0))
        payment = self._pay(order)
        self.assertEqual(payment.amount, 5750.0, "the rest of the second payment")
        self.assertEqual(payment.x4u_proforma_id.name, "%s-PI3" % order.name)
        html = self.env["ir.actions.report"]._render_qweb_html("x4u_sale.action_report_proforma", second.ids)[0]
        self.assertIn(b"This is not a tax invoice", html)
        self.assertIn(b"Remaining", html)
        self.assertIn(second.name.encode(), html)
        self.assertFalse(order.invoice_ids)

    # S3: Custom: the Salesperson writes the schedule (100% in all), frozen once sent
    def test_custom_schedule(self):
        order = self._quote(self.custom)
        self.assertEqual(order.x4u_schedule_ids.mapped("percent"), [100.0])
        first = order.x4u_schedule_ids
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.write(
                {
                    "x4u_schedule_ids": [
                        Command.update(first.id, {"percent": 20.0}),
                        Command.create({"percent": 30.0, "trigger": "shipment", "sequence": 20}),
                        Command.create({"percent": 45.0, "trigger": "delivery", "sequence": 30}),
                    ]
                }
            )
        order.write(
            {
                "x4u_schedule_ids": [
                    Command.update(first.id, {"percent": 20.0}),
                    Command.create({"percent": 30.0, "trigger": "shipment", "sequence": 20}),
                    Command.create({"percent": 50.0, "trigger": "delivery", "sequence": 30}),
                ]
            }
        )
        self.assertIn("20% With Order, 30% Before Shipment, 50% Before Delivery", order.message_ids[0].body)
        self.assertTrue(order.x4u_pay_before_delivery)
        self._attach_po(order)
        self._attach_receipt(order)
        order.action_x4u_send_to_accountant()
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({"x4u_schedule_ids": [Command.update(first.id, {"percent": 25.0})]})
        order.with_user(self.accountant).action_x4u_po_match()
        payment = self._pay(order)
        self.assertEqual(payment.amount, 10500.0)
        order.with_user(self.accountant).action_confirm()
        self.assertEqual(order.x4u_schedule_ids.mapped("amount_total"), [10500.0, 15750.0, 26250.0])

    # S2: the standard terms fill the schedule; the Salesperson cannot change it
    def test_standard_terms_fill_the_schedule(self):
        order = self._quote(self.env.ref("x4u_setup_base.payment_term_50_50"))
        self.assertEqual(order.x4u_schedule_ids.mapped("trigger"), ["order", "delivery"])
        self.assertTrue(order.x4u_pay_before_delivery)
        with Form(order) as form:
            form.payment_term_id = self.env.ref("x4u_setup_base.payment_term_60_days")
        line = order.x4u_schedule_ids
        self.assertEqual((line.percent, line.trigger, line.days), (100.0, "invoice", 60))
        self.assertFalse(order.x4u_pay_before_delivery)
        with self.assertRaises(UserError), self.cr.savepoint():
            line.write({"percent": 50.0})
        order.payment_term_id = self.env.ref("x4u_setup_base.payment_term_120_days")
        self.assertEqual(order.x4u_schedule_ids.days, 120)

    # O8: one tax invoice for the whole order; it applies the payments of this order only
    def test_tax_invoice_applies_the_payments(self):
        order = self._sell()
        self._pay(order)
        other = self._sell()
        invoice = self._tax_invoice(order)
        self.assertEqual(invoice.amount_total, 52500.0)
        self.assertEqual(invoice.amount_residual, 21000.0)
        self.assertEqual(invoice.payment_state, "partial")
        self.assertIn("%s-PI1" % order.name, invoice.message_ids[0].body)
        self.assertEqual(set(order.x4u_proforma_ids.mapped("state")), {"invoiced"})
        self.assertEqual(order.x4u_amount_remaining, 21000.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        self.assertEqual(other.x4u_amount_remaining, 36750.0)
        self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({})._create_payments()
        self.env.invalidate_all()
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertTrue(order.x4u_final_invoice_paid)
        self.assertEqual(order.x4u_schedule_ids.mapped("state"), ["paid", "paid", "paid"])

    # S13: a cancelled payment takes its PI with it; the next payment gets the next number
    def test_cancel_payment(self):
        order = self._sell()
        payment = self._pay(order)
        proforma = payment.x4u_proforma_id
        with self.assertRaises(UserError):
            proforma.unlink()
        payment.with_user(self.accountant).action_cancel()
        self.env.invalidate_all()
        self.assertEqual(proforma.state, "cancel")
        self.assertEqual(order.x4u_amount_advance, 15750.0)
        self.assertEqual(order.x4u_schedule_ids.mapped("state"), ["paid", "not_paid", "not_paid"])
        again = self._pay(order)
        self.assertEqual(again.x4u_proforma_id.name, "%s-PI3" % order.name)
        self.assertEqual(again.x4u_proforma_id.amount_paid, 31500.0)

    # 100% advance: paid before the Confirm, then the tax invoice is paid by it
    def test_full_advance(self):
        order = self._sell(self.env.ref("x4u_setup_base.payment_term_advance_100"))
        self.assertEqual(order.x4u_schedule_ids.mapped("trigger"), ["order"])
        proforma = order.x4u_proforma_ids
        self.assertEqual((proforma.amount_payment, proforma.amount_remaining), (52500.0, 0.0))
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        invoice = self._tax_invoice(order)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(proforma.state, "invoiced")
        self.assertTrue(order.x4u_final_invoice_paid)

    # S12: a due date on a payment is a to-do for the Accountant until that payment is made
    def test_due_dates(self):
        order = self._sell()
        second = order.x4u_schedule_ids[1]
        due = fields.Date.add(fields.Date.today(), days=14)
        action = order.with_user(self.accountant).action_x4u_due_dates()
        self.assertEqual(action["domain"], [("order_id", "=", order.id)])
        second.with_user(self.accountant).write({"date_due": due})
        todo = order.activity_ids.filtered(lambda a: "Follow up" in (a.summary or ""))
        self.assertEqual((todo.user_id, todo.date_deadline), (self.accountant, due))
        self.assertIn("payment 2/3", todo.summary)
        with self.assertRaises(AccessError):
            second.with_user(self.salesperson).write({"date_due": fields.Date.today()})
        self._pay(order)
        self.assertFalse(order.activity_ids.filtered(lambda a: "Follow up" in (a.summary or "")))

    # O7: a receipt of a later payment, attached by the Salesperson, tells the Accountant
    def test_later_receipt_tells_the_accountant(self):
        order = self._sell()
        self._attach_receipt(order.with_user(self.salesperson), "Transfer-2.pdf")
        todo = order.activity_ids.filtered(lambda a: "Payment receipt" in (a.summary or ""))
        self.assertEqual(todo.user_id, self.accountant)

    # §7: the Salesperson sees the amounts on his orders, not the PIs nor the payments
    def test_salesperson_rights(self):
        order = self._sell()
        as_salesperson = order.with_user(self.salesperson)
        self.assertEqual((as_salesperson.x4u_amount_advance, as_salesperson.x4u_amount_remaining), (15750.0, 36750.0))
        proforma = order.x4u_proforma_ids
        with self.assertRaises(AccessError):
            proforma.with_user(self.salesperson).read(["name"])
        with self.assertRaises(AccessError):
            as_salesperson.action_x4u_register_payment()
        with self.assertRaises(AccessError):
            as_salesperson.action_x4u_create_tax_invoice()
        wizard = (
            self.env["sale.advance.payment.inv"]
            .with_user(self.salesperson)
            .with_context(active_model="sale.order", active_ids=order.ids)
            .create({"advance_payment_method": "delivered"})
        )
        with self.assertRaises(AccessError):
            wizard.create_invoices()
        # S4: the Orders tab of the customer, one list per user (not the first user's list for all)
        other = new_test_user(self.env, login="x4u_pay_other_sales", groups="base.group_user,sales_team.group_sale_salesman")
        self.assertNotIn(order, self.customer.with_user(other).x4u_sale_order_ids)
        self.assertIn(order, self.customer.with_user(self.salesperson).x4u_sale_order_ids)
        self.assertIn(order, self.customer.with_user(self.accountant).x4u_sale_order_ids)
