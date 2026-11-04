import base64

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSalePayments(TransactionCase):
    """Spec §6 / §9 tests 1, 7-13: the customer PO, the Accountant's PI, the tax invoice."""

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
        cls.lpo_type = cls.env.ref("x4u_sale.mail_activity_type_lpo")
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

    def _attach_po(self, order):
        attachment = self.env["ir.attachment"].create(
            {"name": "PO-123.pdf", "datas": base64.b64encode(b"%PDF-1.4"), "res_model": "sale.order", "res_id": order.id}
        )
        order.write(
            {
                "client_order_ref": "PO-123",
                "x4u_lpo_date": fields.Date.today(),
                "x4u_lpo_attachment_ids": [Command.set(attachment.ids)],
            }
        )

    def _sell(self, term=None, match=True):
        """Confirmed by the Salesperson when the customer agrees, then the LPO; the Accountant checks it."""
        order = self._quote(term)
        order.action_confirm()
        self._attach_po(order)
        self.assertEqual(order.amount_total, 52500.0)
        if match:
            order.with_user(self.accountant).action_x4u_po_match()
        return order.with_env(self.env)

    def _pi(self, order):
        action = order.with_user(self.accountant).action_x4u_create_proforma()
        return self.env["x4u.sale.proforma"].browse(action["res_id"])

    def _pay(self, proforma, amount=None):
        """The Accountant: Register Payment on the PI, then Confirm."""
        action = proforma.with_user(self.accountant).action_register_payment()
        payment = self.env["account.payment"].with_user(self.accountant).browse(action["res_id"])
        if amount is not None:
            payment.amount = amount
        payment.action_post()
        self.env.invalidate_all()
        return payment

    def _tax_invoice(self, proforma):
        """The Accountant: Create Tax Invoice on the PI, then Confirm."""
        action = proforma.with_user(self.accountant).action_create_tax_invoice()
        invoice = self.env["account.move"].with_user(self.accountant).browse(action["res_id"])
        invoice.action_post()
        self.env.invalidate_all()
        return invoice

    def _todo(self, order, activity_type):
        return order.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)

    # 1 (v0.6): Confirm when the customer agrees, then the LPO; only then the Accountant checks it
    def test_lpo_after_confirm(self):
        order = self._quote()
        order.action_confirm()
        self.assertEqual((order.state, order.x4u_po_check), ("sale", "waiting"))
        self.assertTrue(order.locked)
        self.assertEqual(self._todo(order, self.lpo_type).user_id, self.salesperson)
        self.assertFalse(self._todo(order, self.check_type))
        with self.assertRaisesRegex(UserError, "waiting for the customer's LPO"):
            order.with_user(self.accountant).action_x4u_create_proforma()
        with self.assertRaises(UserError):
            order.with_user(self.accountant).action_x4u_po_match()
        self._attach_po(order)
        self.assertEqual(order.x4u_po_check, "to_check")
        self.assertFalse(self._todo(order, self.lpo_type))
        self.assertEqual(self._todo(order, self.check_type).user_id, self.accountant)
        self.assertTrue(any("LPO PO-123" in (body or "") for body in order.message_ids.mapped("body")))
        with self.assertRaises(AccessError):
            order.action_x4u_po_match()
        with self.assertRaises(AccessError):
            order.write({"x4u_po_check": "match"})
        # A file uploaded before the order was saved belongs to the order: the Accountant opens it.
        loose = self.env["ir.attachment"].with_user(self.salesperson).create(
            {"name": "PO-124.pdf", "datas": base64.b64encode(b"%PDF-1.4")}
        )
        order.write({"x4u_lpo_attachment_ids": [Command.link(loose.id)]})
        self.assertEqual(loose.with_user(self.accountant).read(["name"])[0]["name"], "PO-124.pdf")
        # An LPO that came before the Confirm: straight to the Accountant, no LPO to-do.
        early = self._quote()
        self._attach_po(early)
        early.action_confirm()
        self.assertEqual(early.x4u_po_check, "to_check")
        self.assertFalse(self._todo(early, self.lpo_type))

    # 7: no PI before the check; Doesn't Match goes back to the Salesperson; then one PI
    def test_po_check_before_the_pi(self):
        order = self._sell(match=False)
        with self.assertRaises(UserError):
            self._pi(order)
        self.env["x4u.sale.po.mismatch"].with_user(self.accountant).create(
            {"order_id": order.id, "reason": "The PO says 400 kVA"}
        ).action_confirm()
        self.assertEqual(order.x4u_po_check, "mismatch")
        self.assertFalse(self._todo(order, self.check_type))
        fix = self._todo(order, self.fix_type)
        self.assertEqual(fix.user_id, self.salesperson)
        self.assertIn("400 kVA", fix.summary)
        order.with_user(self.salesperson).action_x4u_po_recheck()
        self.assertEqual(order.x4u_po_check, "to_check")
        self.assertFalse(self._todo(order, self.fix_type))
        self.assertEqual(self._todo(order, self.check_type).user_id, self.accountant)
        order.with_user(self.accountant).action_x4u_po_match()
        self.assertEqual(order.x4u_po_check_user_id, self.accountant)
        moves_before = self.env["account.move"].search_count([])
        proforma = self._pi(order)
        self.assertEqual(proforma.name, "%s-PI" % order.name)
        self.assertEqual(proforma.schedule_ids.mapped("amount_total"), [15750.0, 15750.0, 21000.0])
        self.assertEqual(proforma.schedule_ids.mapped("amount_tax"), [750.0, 750.0, 1000.0])
        self.assertEqual(proforma.schedule_ids.mapped("trigger"), ["order", "progress", "delivery"])
        self.assertEqual((proforma.amount_due_now, proforma.next_payment), (15750.0, "1/3"))
        self.assertEqual(self.env["account.move"].search_count([]), moves_before)
        self.assertFalse(order.invoice_ids)
        html = self.env["ir.actions.report"]._render_qweb_html("x4u_sale.action_report_proforma", proforma.ids)[0]
        self.assertIn(b"This is not a tax invoice", html)
        self.assertIn(proforma.name.encode(), html)
        with self.assertRaises(UserError):
            self._pi(order)

    # 8: payments on the PI, paid in the order of the schedule; the PI stays open
    def test_payments_on_the_pi(self):
        order = self._sell()
        proforma = self._pi(order)
        payment = self._pay(proforma)
        self.assertEqual(payment.x4u_sale_order_id, order)
        self.assertEqual(payment.memo, "%s · 1/3" % proforma.name)
        self.assertEqual(payment.amount, 15750.0)
        self.assertEqual(proforma.schedule_ids.mapped("state"), ["paid", "not_paid", "not_paid"])
        self.assertEqual((proforma.state, proforma.amount_paid), ("open", 15750.0))
        self.assertEqual((order.x4u_amount_advance, order.x4u_amount_remaining), (15750.0, 36750.0))
        self.assertEqual((proforma.amount_due_now, proforma.next_payment), (15750.0, "2/3"))
        self.assertFalse(order.invoice_ids)
        self._pay(proforma, amount=10000.0)
        self.assertEqual(proforma.schedule_ids.mapped("state"), ["paid", "partial", "not_paid"])
        self.assertEqual(proforma.amount_due_now, 5750.0)
        # The Accountant asks for another amount, until the next payment comes in.
        proforma.with_user(self.accountant).amount_due_now = 3000.0
        self.assertEqual(proforma.amount_due_now, 3000.0)
        self._pay(proforma)
        self.assertEqual(proforma.amount_paid, 28750.0)
        self.assertEqual(proforma.amount_due_now, 2750.0)

    # 9: Custom: the Salesperson writes the schedule (100% in all), it is written on the order
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
        order.action_confirm()
        # Locked once confirmed: the Sales Manager unlocks it to change the schedule.
        with self.assertRaises(UserError), self.cr.savepoint():
            first.with_user(self.salesperson).write({"percent": 25.0})
        order.with_user(self.accountant).action_x4u_po_match()
        proforma = self._pi(order.with_env(self.env))
        self.assertEqual(proforma.schedule_ids.mapped("amount_total"), [10500.0, 15750.0, 26250.0])

    # The standard terms fill the schedule; the Salesperson cannot change it
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

    # 10: the tax invoice from the PI, any time; it applies the payments of this order only
    def test_tax_invoice_applies_the_payments(self):
        order = self._sell()
        proforma = self._pi(order)
        self._pay(proforma)
        self._pay(proforma)
        other = self._sell()
        self._pay(self._pi(other))
        invoice = self._tax_invoice(proforma)
        self.assertEqual(invoice.amount_total, 52500.0)
        self.assertEqual(invoice.amount_residual, 21000.0)
        self.assertEqual(invoice.payment_state, "partial")
        self.assertIn(proforma.name, invoice.message_ids[0].body)
        self.assertEqual(proforma.state, "invoiced")
        self.assertEqual(order.x4u_amount_remaining, 21000.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        self.assertEqual(other.x4u_amount_remaining, 36750.0)
        with self.assertRaises(UserError):
            proforma.with_user(self.accountant).action_register_payment()
        self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({})._create_payments()
        self.env.invalidate_all()
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertTrue(order.x4u_final_invoice_paid)
        self.assertEqual(proforma.schedule_ids.mapped("state"), ["paid", "paid", "paid"])

    # 11: a cancelled payment is not paid any more; a PI with a payment stays; then PI2
    def test_cancel_rules(self):
        order = self._sell()
        proforma = self._pi(order)
        payment = self._pay(proforma)
        with self.assertRaises(UserError):
            proforma.with_user(self.accountant).action_cancel()
        payment.with_user(self.accountant).action_cancel()
        self.env.invalidate_all()
        self.assertEqual(proforma.schedule_ids[0].state, "not_paid")
        self.assertEqual(order.x4u_amount_advance, 0.0)
        proforma.with_user(self.accountant).action_cancel()
        self.assertEqual(proforma.state, "cancel")
        self.assertFalse(proforma.schedule_ids)
        again = self._pi(order)
        self.assertEqual(again.name, "%s-PI2" % order.name)
        self.assertEqual(len(again.schedule_ids), 3)

    # 100% advance: the PI is paid before any invoice, then the tax invoice is paid by it
    def test_full_advance(self):
        order = self._sell(self.env.ref("x4u_setup_base.payment_term_advance_100"))
        proforma = self._pi(order)
        self.assertEqual(proforma.schedule_ids.mapped("trigger"), ["order"])
        self.assertFalse(proforma.next_payment)
        self._pay(proforma)
        self.assertEqual(proforma.state, "paid")
        self.assertEqual(order.x4u_amount_remaining, 0.0)
        self.assertFalse(order.x4u_final_invoice_paid)
        invoice = self._tax_invoice(proforma)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(proforma.state, "invoiced")
        self.assertTrue(order.x4u_final_invoice_paid)

    # S12: a due date on a payment is a to-do for the Accountant until that payment is made
    def test_due_dates(self):
        order = self._sell()
        proforma = self._pi(order)
        second = proforma.schedule_ids[1]
        due = fields.Date.add(fields.Date.today(), days=14)
        proforma.with_user(self.accountant).write({"schedule_ids": [Command.update(second.id, {"date_due": due})]})
        todo = proforma.activity_ids
        self.assertEqual((todo.user_id, todo.date_deadline), (self.accountant, due))
        self.assertIn("payment 2/3", todo.summary)
        with self.assertRaises(AccessError):
            second.with_user(self.salesperson).write({"date_due": fields.Date.today()})
        self._pay(proforma)
        self.assertTrue(proforma.activity_ids)
        self._pay(proforma)
        self.assertFalse(proforma.activity_ids)

    # 12: the Salesperson sees the PI status and the amounts on his orders, not the PI itself
    def test_salesperson_rights(self):
        order = self._sell()
        proforma = self._pi(order)
        self._pay(proforma)
        as_salesperson = order.with_user(self.salesperson)
        self.assertEqual(as_salesperson.x4u_proforma_state, "open")
        self.assertEqual((as_salesperson.x4u_amount_advance, as_salesperson.x4u_amount_remaining), (15750.0, 36750.0))
        # No access to the PI at all: no form, no Print, no Send.
        with self.assertRaises(AccessError):
            proforma.with_user(self.salesperson).read(["name"])
        with self.assertRaises(AccessError):
            proforma.with_user(self.salesperson).check_access("read")
        with self.assertRaises(AccessError):
            as_salesperson.action_x4u_create_proforma()
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
