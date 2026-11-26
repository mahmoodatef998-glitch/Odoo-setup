import base64

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestReceiptBill(TransactionCase):
    """UAT Phase 2.2-2.3 (2026-11-25): the receipt needs the vendor's Delivery Note, the Accountant is
    told, and the bill of the receipt takes what came in with its documents."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.x4u_receipt_dn_required = True
        cls.accountant = new_test_user(
            cls.env, login="x4u_receipt_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", cls.accountant.id)
        cls.vendor = cls.env["res.partner"].create({"name": "X4U Test Receipt Vendor", "supplier_rank": 1})
        categ = cls.env.ref("x4u_setup_base.categ_components")
        cls.part = cls.env["product.product"].create(
            {"name": "X4U Test Receipt Part", "is_storable": True, "categ_id": categ.id, "purchase_method": "receive"}
        )
        cls.order = cls.env["purchase.order"].create(
            {
                "partner_id": cls.vendor.id,
                "order_line": [Command.create({"product_id": cls.part.id, "product_qty": 3, "price_unit": 1500.0, "taxes_id": False})],
            }
        )
        cls.order.button_confirm()
        cls.env["ir.attachment"].create(
            {"name": "PO signed.pdf", "datas": base64.b64encode(b"%PDF po"), "res_model": "purchase.order", "res_id": cls.order.id}
        )

    def _receive(self, qty):
        receipt = self.order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        receipt.move_ids.quantity = qty
        receipt.move_ids.picked = True
        return receipt

    def test_receipt_needs_its_delivery_note(self):
        receipt = self._receive(3)
        self.assertTrue(receipt.x4u_is_vendor_receipt)
        with self.assertRaisesRegex(UserError, "Delivery Note"):
            receipt.button_validate()
        receipt.x4u_delivery_note_ids = [Command.create(
            {"name": "DN 5521.jpg", "datas": base64.b64encode(b"delivery note"), "res_model": "stock.picking", "res_id": receipt.id}
        )]
        receipt.x4u_vendor_ref = "INV-5521"
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        activity = self.order.activity_ids.filtered(lambda a: receipt.name in (a.summary or ""))
        self.assertEqual(activity.user_id, self.accountant, "the Accountant has the task to record the bill")
        # The user, 2026-11-25: a notification with what came in and the vendor's invoice number.
        note = self.order.message_ids.filtered(lambda m: self.accountant.partner_id in m.partner_ids)
        self.assertEqual(len(note), 1)
        for text in (receipt.name, "INV-5521", "X4U Test Receipt Part", "3 Units"):
            self.assertIn(text, str(note.body))
        self.assertEqual(note.attachment_ids.mapped("name"), ["DN 5521.jpg"], "the Delivery Note goes with it")
        self.assertEqual(receipt.x4u_delivery_note_ids.res_model, "stock.picking", "the receipt keeps its own")

    def test_draft_bill_at_the_receipt(self):
        """The user, 2026-11-26 (fewer steps): the bill is drafted at the receipt, the Accountant confirms it."""
        self.company.x4u_receipt_draft_bill = True
        receipt = self._receive(2)
        receipt.x4u_delivery_note_ids = [Command.create(
            {"name": "DN 5523.jpg", "datas": base64.b64encode(b"delivery note 3"), "res_model": "stock.picking", "res_id": receipt.id}
        )]
        receipt.x4u_vendor_ref = "INV-5523"
        receipt.with_context(skip_backorder=True, picking_ids_not_to_backorder=receipt.ids).button_validate()
        bill = receipt.x4u_bill_ids
        self.assertEqual(len(bill), 1)
        self.assertEqual((bill.state, bill.move_type, bill.ref), ("draft", "in_invoice", "INV-5523"))
        self.assertEqual(bill.invoice_line_ids.quantity, 2.0, "what came in, not what was ordered")
        self.assertEqual(bill.invoice_line_ids.purchase_line_id, self.order.order_line)
        self.assertEqual(bill.invoice_line_ids.price_unit, 1500.0)
        names = self.env["ir.attachment"].search([("res_model", "=", "account.move"), ("res_id", "=", bill.id)]).mapped("name")
        self.assertIn("DN 5523.jpg", names)
        task = bill.activity_ids.filtered(lambda a: receipt.name in (a.summary or ""))
        self.assertEqual(task.user_id, self.accountant, "the Accountant checks the draft bill")
        note = self.order.message_ids.filtered(lambda m: self.accountant.partner_id in m.partner_ids)
        self.assertIn("Draft bill", str(note.body))
        self.assertFalse(self.order.activity_ids.filtered(lambda a: receipt.name in (a.summary or "")), "one task, on the bill")
        self.assertTrue(receipt.x4u_billed)
        bill.action_post()
        self.assertFalse(bill.activity_ids.filtered(lambda a: receipt.name in (a.summary or "")), "confirmed: the task is done")
        self.assertEqual(self.order.order_line.qty_invoiced, 2.0)

    def test_bill_of_a_receipt(self):
        receipt = self._receive(2)
        receipt.x4u_delivery_note_ids = [Command.create(
            {"name": "DN 5522.jpg", "datas": base64.b64encode(b"delivery note 2"), "res_model": "stock.picking", "res_id": receipt.id}
        )]
        receipt.x4u_vendor_ref = "INV-5522"
        receipt.with_context(skip_backorder=True, picking_ids_not_to_backorder=receipt.ids).button_validate()
        self.assertEqual(receipt.state, "done")
        form = Form(self.env["account.move"].with_context(default_move_type="in_invoice"))
        form.partner_id = self.vendor
        form.invoice_date = "2026-11-25"
        form.x4u_receipt_id = receipt
        bill = form.save()
        line = bill.invoice_line_ids
        self.assertEqual(line.quantity, 2.0, "what came in, not what was ordered")
        self.assertEqual(line.purchase_line_id, self.order.order_line)
        self.assertEqual(line.price_unit, 1500.0)
        self.assertEqual(bill.ref, "INV-5522", "the vendor's invoice number from the receipt")
        names = self.env["ir.attachment"].search([("res_model", "=", "account.move"), ("res_id", "=", bill.id)]).mapped("name")
        self.assertIn("DN 5522.jpg", names)
        self.assertIn("PO signed.pdf", names)
        self.assertFalse(self.order.activity_ids.filtered(lambda a: receipt.name in (a.summary or "")), "the task is done")
        self.assertTrue(receipt.x4u_billed)
        self.assertNotIn(receipt, self.env["stock.picking"].search([("x4u_billed", "=", False), ("id", "=", receipt.id)]))
