import base64

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestVendorPayments(TransactionCase):
    """x4u_purchase spec §6 tests 1-7: terms and mode on the PO, the vendor PI, the bill."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax = cls.env["account.tax"].create(
            {"name": "X4U Test Purchase VAT 5%", "amount": 5.0, "type_tax_use": "purchase"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "X4U Test Engine Supply",
                "type": "service",
                "purchase_method": "purchase",
                "standard_price": 20000.0,
                "supplier_taxes_id": [Command.set(cls.tax.ids)],
            }
        )
        cls.term_50_50 = cls.env.ref("x4u_setup_base.payment_term_50_50")
        cls.vendor = cls.env["res.partner"].create(
            {"name": "X4U Test Vendor", "property_supplier_payment_term_id": cls.term_50_50.id}
        )
        cls.vendor_pi_type = cls.env.ref("x4u_purchase.mail_activity_type_vendor_pi")
        cls.vendor_pi_fix_type = cls.env.ref("x4u_purchase.mail_activity_type_vendor_pi_fix")
        cls.buyer = new_test_user(cls.env, login="x4u_vp_buyer", groups="base.group_user,purchase.group_purchase_user")
        cls.manager = new_test_user(
            cls.env, login="x4u_vp_manager", groups="base.group_user,purchase.group_purchase_manager"
        )
        cls.accountant = new_test_user(
            cls.env, login="x4u_vp_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)

    def _order(self, term=None, mode="transfer"):
        """PO by the buyer: 20,000 + 5% VAT = 21,000."""
        return self.env["purchase.order"].with_user(self.buyer).create(
            {
                "partner_id": self.vendor.id,
                "currency_id": self.env.company.currency_id.id,
                "payment_term_id": (term or self.term_50_50).id,
                "x4u_payment_mode": mode,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 20000.0,
                            "taxes_id": [Command.set(self.tax.ids)],
                        }
                    )
                ],
            }
        )

    def _approve(self, order):
        order.button_confirm()
        order.with_user(self.manager).button_approve()
        self.assertEqual(order.state, "purchase")
        self.assertEqual(order.amount_total, 21000.0)
        return order

    def _attach_pi(self, order):
        """The buyer attaches the PI the vendor sent."""
        attachment = self.env["ir.attachment"].create(
            {"name": "PI-777.pdf", "datas": base64.b64encode(b"%PDF-1.4"), "res_model": "purchase.order", "res_id": order.id}
        )
        order.write({"x4u_vendor_pi_attachment_ids": [Command.set(attachment.ids)]})

    def _record_pi(self, order, match=True):
        """The Accountant records the vendor PI from the PO, then checks it."""
        proforma = self.env["x4u.purchase.proforma"].with_user(self.accountant).create(
            {
                "order_id": order.id,
                "vendor_ref": "PI-777",
                "attachment_ids": [Command.set(order.x4u_vendor_pi_attachment_ids.ids)],
            }
        )
        if match:
            proforma.action_match()
        return proforma.with_env(self.env)

    def _pay(self, proforma, amount=None):
        action = proforma.with_user(self.accountant).action_register_payment()
        payment = self.env["account.payment"].with_user(self.accountant).browse(action["res_id"])
        if amount is not None:
            payment.amount = amount
        payment.action_post()
        self.env.invalidate_all()
        return payment

    def _bill(self, order):
        """The Accountant: Create Bill on the PO, the vendor's date, then Confirm."""
        action = order.with_user(self.accountant).action_create_invoice()
        bill = self.env["account.move"].with_user(self.accountant).browse(action["res_id"])
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        self.env.invalidate_all()
        return bill

    def _todo(self, order, activity_type):
        return order.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)

    # 1 / 2: the terms come from the vendor, the schedule from the terms; mode and terms are printed
    def test_terms_and_mode_on_the_po(self):
        with Form(self.env["purchase.order"].with_user(self.buyer)) as form:
            form.partner_id = self.vendor
            form.x4u_payment_mode = "pdc"
            with form.order_line.new() as line:
                line.product_id = self.product
                line.price_unit = 20000.0
        order = form.record
        self.assertEqual(order.payment_term_id, self.term_50_50)
        self.assertEqual(order.x4u_schedule_ids.mapped("trigger"), ["order", "delivery"])
        order.payment_term_id = self.env.ref("x4u_setup_base.payment_term_120_days")
        self.assertEqual((order.x4u_schedule_ids.trigger, order.x4u_schedule_ids.days), ("invoice", 120))
        html = self.env["ir.actions.report"]._render_qweb_html("purchase.action_report_purchase_order", order.ids)[0]
        self.assertIn(b"PDC (post-dated cheque)", html)
        self.assertIn(b"120 Days", html)
        self._approve(order)
        # Locked once the General Manager approved it.
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({"payment_term_id": self.term_50_50.id})
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({"x4u_payment_mode": "cash"})

    # 3: Custom on the PO: 100% in all
    def test_custom_schedule(self):
        order = self._order(self.env.ref("x4u_sale.payment_term_custom"))
        first = order.x4u_schedule_ids
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.write(
                {
                    "x4u_schedule_ids": [
                        Command.update(first.id, {"percent": 50.0}),
                        Command.create({"percent": 45.0, "trigger": "shipment", "sequence": 20}),
                    ]
                }
            )
        order.write(
            {
                "x4u_schedule_ids": [
                    Command.update(first.id, {"percent": 50.0}),
                    Command.create({"percent": 50.0, "trigger": "shipment", "sequence": 20}),
                ]
            }
        )
        self.assertIn("50% With Order, 50% Before Shipment", order.message_ids[0].body)
        self._approve(order)
        with self.assertRaises(UserError), self.cr.savepoint():
            first.write({"percent": 40.0})

    # 4: file attached -> to-do for the Accountant -> checked -> paid; the PI stays open
    def test_vendor_pi_flow(self):
        order = self._approve(self._order())
        self._attach_pi(order)
        self.assertEqual(self._todo(order, self.vendor_pi_type).user_id, self.accountant)
        action = order.with_user(self.accountant).action_x4u_record_vendor_pi()
        self.assertEqual(action["context"]["default_attachment_ids"], [Command.set(order.x4u_vendor_pi_attachment_ids.ids)])
        proforma = self._record_pi(order, match=False)
        self.assertEqual(proforma.name, "%s-VPI" % order.name)
        self.assertEqual(proforma.state, "to_check")
        self.assertFalse(self._todo(order, self.vendor_pi_type))
        with self.assertRaises(UserError):
            proforma.with_user(self.accountant).action_register_payment()
        self.env["x4u.purchase.pi.mismatch"].with_user(self.accountant).create(
            {"proforma_id": proforma.id, "reason": "The PI asks for 60% advance"}
        ).action_confirm()
        self.assertEqual(proforma.state, "mismatch")
        self.assertEqual(self._todo(order, self.vendor_pi_fix_type).user_id, self.buyer)
        proforma.with_user(self.accountant).action_match()
        self.assertEqual(proforma.state, "open")
        self.assertFalse(self._todo(order, self.vendor_pi_fix_type))
        payment = self._pay(proforma)
        self.assertEqual((payment.amount, payment.payment_type, payment.x4u_purchase_order_id), (10500.0, "outbound", order))
        self.assertIn("%s · 1/2 (PI-777)" % proforma.name, payment.memo)
        self.assertEqual(proforma.schedule_ids.mapped("state"), ["paid", "not_paid"])
        self.assertEqual((proforma.state, proforma.amount_due_now), ("open", 10500.0))
        self.assertEqual((order.x4u_amount_advance, order.x4u_amount_remaining), (10500.0, 10500.0))

    # 5: the bill of the PO applies its advance, not the one of another PO of the same vendor
    def test_bill_applies_the_advances(self):
        order = self._approve(self._order())
        self._attach_pi(order)
        proforma = self._record_pi(order)
        self._pay(proforma)
        other = self._approve(self._order())
        self._attach_pi(other)
        self._pay(self._record_pi(other))
        bill = self._bill(order)
        self.assertEqual(bill.amount_total, 21000.0)
        self.assertEqual(bill.amount_residual, 10500.0)
        self.assertIn(proforma.name, bill.message_ids[0].body)
        self.assertEqual(proforma.state, "billed")
        self.assertEqual(order.x4u_amount_remaining, 10500.0)
        self.assertEqual(other.x4u_amount_remaining, 10500.0)

    # 6 / 7: Purchasing attaches the file and sees the status; the PI and the payments are the Accountant's
    def test_buyer_rights(self):
        order = self._approve(self._order())
        self._attach_pi(order)
        proforma = self._record_pi(order)
        self.assertEqual(order.x4u_proforma_state, "open")
        with self.assertRaises(AccessError):
            proforma.with_user(self.buyer).read(["name"])
        with self.assertRaises(AccessError):
            order.action_x4u_record_vendor_pi()
        with self.assertRaises(AccessError):
            self.env["x4u.purchase.proforma"].with_user(self.buyer).create({"order_id": order.id, "vendor_ref": "X"})
        # P10: one list per user (not the first user's list for all)
        nobody = new_test_user(self.env, login="x4u_vp_nobody", groups="base.group_user")
        self.assertFalse(self.vendor.with_user(nobody).x4u_purchase_order_ids)
        self.assertIn(order, self.vendor.with_user(self.buyer).x4u_purchase_order_ids)
        self.assertIn(order, self.vendor.with_user(self.accountant).x4u_purchase_order_ids)
