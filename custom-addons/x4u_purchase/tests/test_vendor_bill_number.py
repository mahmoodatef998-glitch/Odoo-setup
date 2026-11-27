from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVendorBillNumber(TransactionCase):
    """The user, 2026-11-27: the vendor's invoice number at the top of a bill, the 4U number under it,
    given at Confirm and never typed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "X4U Test Bill Number Vendor"})

    def _bill(self, **values):
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create({"name": "X4U Test Service", "quantity": 1, "price_unit": 100.0, "tax_ids": [Command.clear()]})
                ],
                **values,
            }
        )

    def test_typed_number_becomes_the_vendor_number(self):
        bill = self._bill()
        bill.name = "LPI-TG5499/26"
        other = self._bill(ref="V-77")
        other.name = "V-77"
        fixed = self.env["account.move"]._x4u_clear_typed_bill_numbers()
        self.assertIn(bill, fixed)
        self.assertFalse(bill.name)
        self.assertEqual(bill.ref, "LPI-TG5499/26")
        self.assertEqual(other.ref, "V-77", "a Vendor Invoice No. already there stays")
        bill.action_post()
        self.assertEqual(bill.ref, "LPI-TG5499/26")
        prefix = self.env.company.x4u_document_prefix
        if prefix:
            self.assertTrue(bill.name.startswith("%s-BILL-" % prefix), bill.name)

    def test_form_shows_the_vendor_number_first(self):
        arch = self.env["account.move"].get_view(self.env.ref("account.view_move_form").id, "form")["arch"]
        self.assertIn('placeholder="Vendor Invoice No."', arch)
        self.assertLess(arch.index('placeholder="Vendor Invoice No."'), arch.index("4U number"))
