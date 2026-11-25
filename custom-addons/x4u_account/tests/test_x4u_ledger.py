import io
import re
import zipfile

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.x4u_account.hooks import _account


@tagged("post_install", "-at_install")
class TestX4uLedger(TransactionCase):
    """Spec §22 (UAT Phase 4): the Counterpart account, Dr / Cr balances and the Customer / Vendor Ledgers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]
        cls.petty = _account(cls.env, cls.company, "131116")
        cls.fuel = Account.search([("account_type", "=", "expense"), *Account._check_company_domain(cls.company)], limit=1)
        Journal = cls.env["account.journal"]
        journal = Journal.search([("type", "=", "general"), *Journal._check_company_domain(cls.company)], limit=1)
        # A petty cash payment of 2,000 for fuel: the accountants saw the 2,000 but not where it went.
        cls.move = cls.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": fields.Date.today(),
                "ref": "X4U Test Fuel",
                "line_ids": [
                    Command.create({"account_id": cls.fuel.id, "debit": 2000.0, "name": "Fuel"}),
                    Command.create({"account_id": cls.petty.id, "credit": 2000.0, "name": "Fuel"}),
                ],
            }
        )
        cls.move.action_post()

    def _wizard(self, accounts):
        today = fields.Date.today()
        return self.env["general.ledger.report.wizard"].create(
            {
                "date_from": today.replace(month=1, day=1),
                "date_to": today,
                "target_move": "posted",
                "company_id": self.company.id,
                "account_ids": [Command.set(accounts.ids)],
                "centralize": False,
            }
        )

    def _render(self, wizard, report):
        Report = self.env["ir.actions.report"].with_context(
            active_model=wizard._name, active_id=wizard.id, active_ids=wizard.ids
        )
        data = wizard._prepare_report_data()
        if report.endswith("xlsx"):
            return Report._render_xlsx(report, wizard.ids, data)[0]
        return Report._render_qweb_html(report, wizard.ids, data)[0]

    def test_counterpart(self):
        petty_line = self.move.line_ids.filtered(lambda line: line.account_id == self.petty)
        fuel_line = self.move.line_ids - petty_line
        self.assertEqual(petty_line.x4u_counterpart, "%s %s" % (self.fuel.code, self.fuel.name))
        self.assertEqual(fuel_line.x4u_counterpart, "%s %s" % (self.petty.code, self.petty.name))

    def test_cash_book_shows_counterpart_and_cr(self):
        html = self._render(self._wizard(self.petty), "account_financial_report.action_print_report_general_ledger_html")
        text = re.sub(r"<[^>]+>|&nbsp;|\s+", " ", html.decode())
        self.assertIn("Counterpart", text)
        self.assertIn("%s %s" % (self.fuel.code, self.fuel.name), text)
        self.assertRegex(text, r"2,000\.00\s*(AED|د\.إ)?\s*Cr", "the petty cash went down: Cr, no minus sign")
        self.assertNotRegex(text, r"-\s*2,000\.00")

    def test_excel_counterpart_and_dr_cr(self):
        content = self._render(self._wizard(self.petty | self.fuel), "account_financial_report.action_report_general_ledger_xlsx")
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            # Strings are written inline (constant memory mode) or shared: look in every part.
            xml = b"".join(book.read(name) for name in book.namelist() if name.endswith(".xml"))
            self.assertIn(b"Counterpart", xml)
            self.assertIn(b"&quot;Dr&quot;;#,##0.00 &quot;Cr&quot;", book.read("xl/styles.xml"))

    def test_customer_and_vendor_ledgers(self):
        Report = self.env["x4u.accounting.report"]
        for method, account_type in (
            ("action_x4u_customer_ledger", "asset_receivable"),
            ("action_x4u_vendor_ledger", "liability_payable"),
        ):
            action = getattr(Report, method)()
            wizard = self.env[action["res_model"]].browse(action["res_id"])
            self.assertEqual(set(wizard.account_ids.mapped("account_type")), {account_type}, method)
            self.assertEqual(wizard.grouped_by, "partners")
