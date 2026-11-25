import unittest

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestX4uTrnVat(TransactionCase):
    """Spec §21 (UAT Phase 3.3): the TRN of a VAT registered contact before an invoice or bill is
    confirmed, and VAT 5% on VAT OUT (sales) and VAT IN (purchases)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        if cls.company.account_fiscal_country_id.code != "AE":
            raise unittest.SkipTest("Company without the UAE chart of accounts")
        cls.uae = cls.env.ref("base.ae")

    def _move(self, move_type, partner, tax=None):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "X4U Test Line",
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "tax_ids": [Command.set(tax.ids)] if tax else [Command.clear()],
                        }
                    )
                ],
            }
        )

    def test_trn_format(self):
        partner = self.env["res.partner"].create(
            {"name": "X4U Test TRN Co", "is_company": True, "country_id": self.uae.id, "vat": "100 1234 5670 0003"}
        )
        self.assertTrue(partner.x4u_vat_registered, "a UAE contact with a TRN is VAT registered")
        with self.assertRaises(ValidationError):
            partner.vat = "12345"
        # A foreign vendor keeps its own VAT number format.
        foreign = self.env["res.partner"].create(
            {"name": "X4U Test UK Vendor", "country_id": self.env.ref("base.uk").id, "vat": "GB123456789"}
        )
        self.assertFalse(foreign.x4u_vat_registered)
        self.assertEqual(self.uae.vat_label, "TRN", "printed as TRN on the tax invoice")

    def test_trn_required_at_confirm(self):
        partner = self.env["res.partner"].create(
            {"name": "X4U Test Registered No TRN", "is_company": True, "country_id": self.uae.id, "x4u_vat_registered": True}
        )
        contact = self.env["res.partner"].create({"name": "X4U Test Buyer", "parent_id": partner.id})
        self.assertTrue(contact.x4u_vat_registered, "the contact follows its company")
        for move_type in ("out_invoice", "in_invoice"):
            move = self._move(move_type, contact)
            with self.assertRaisesRegex(UserError, "no TRN"):
                move.action_post()
        partner.vat = "100123456700003"
        move = self._move("out_invoice", contact)
        move.action_post()
        self.assertEqual(move.state, "posted")
        # Individuals and contacts not registered are invoiced without a TRN.
        walk_in = self.env["res.partner"].create({"name": "X4U Test Walk-in", "country_id": self.uae.id})
        self._move("out_invoice", walk_in).action_post()

    def test_vat_in_and_out_accounts(self):
        sale_tax, purchase_tax = self.company.account_sale_tax_id, self.company.account_purchase_tax_id
        self.assertEqual((sale_tax.amount, purchase_tax.amount), (5.0, 5.0))
        customer = self.env["res.partner"].create({"name": "X4U Test VAT Customer"})
        invoice = self._move("out_invoice", customer, sale_tax)
        bill = self._move("in_invoice", customer, purchase_tax)
        (invoice | bill).action_post()
        out_line = invoice.line_ids.filtered("tax_line_id")
        in_line = bill.line_ids.filtered("tax_line_id")
        self.assertEqual((out_line.account_id.code, out_line.credit), ("110002", 50.0), "VAT OUT")
        self.assertEqual((in_line.account_id.code, in_line.debit), ("110003", 50.0), "VAT IN")
