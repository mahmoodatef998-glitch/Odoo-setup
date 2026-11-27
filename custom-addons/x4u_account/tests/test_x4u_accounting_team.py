from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestX4uAccountingTeam(TransactionCase):
    """The accounting team's list, 2026-11-27: aging from the invoice date, grouped screens,
    the Accountant's reminder before the due date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.context_today(cls.env.user)
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Aging Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "X4U Test Aging Vendor"})
        cls.accountant = cls.env["res.users"].create(
            {
                "name": "X4U Test Accountant",
                "login": "x4u_test_accountant",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "groups_id": [Command.set([cls.env.ref("account.group_account_invoice").id])],
            }
        )
        cls.config = cls.env["account.age.report.configuration"].search(
            [("x4u_default", "=", True), ("company_id", "=", cls.company.id)], limit=1
        )

    def _move(self, move_type, partner, invoice_date, due_date, amount=1000.0):
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": invoice_date,
                "invoice_date_due": due_date,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "X4U Test Service", "quantity": 1, "price_unit": amount, "tax_ids": [Command.clear()]}
                    )
                ],
            }
        )
        move.action_post()
        return move

    # Aging ----------------------------------------------------------------

    def test_aging_configuration(self):
        self.assertTrue(self.config, "every company gets the 4U aging configuration")
        self.assertTrue(self.config.x4u_from_invoice_date)
        self.assertEqual(
            [(line.name, line.inferior_limit) for line in self.config.line_ids.sorted("inferior_limit")],
            [("0-30 days", 30), ("31-60 days", 60), ("61-90 days", 90), ("+90 days", 100000)],
        )
        wizard = self.env["aged.partner.balance.report.wizard"].create({"company_id": self.company.id})
        self.assertEqual(wizard.age_partner_config_id, self.config, "the wizard opens on the 4U intervals")

    def _aged(self, config):
        data = {
            "wizard_id": False,
            "wizard_name": "aged.partner.balance.report.wizard",
            "date_at": fields.Date.to_string(self.today),
            "date_from": False,
            "only_posted_moves": True,
            "company_id": self.company.id,
            "account_ids": self.customer.property_account_receivable_id.ids,
            "partner_ids": self.customer.ids,
            "show_move_line_details": False,
            "account_financial_report_lang": self.env.lang,
            "age_partner_config_id": config.id,
        }
        values = self.env["report.account_financial_report.aged_partner_balance"]._get_report_values([], data)
        partners = [p for account in values["aged_partner_balance"] for p in account["partners"]]
        self.assertEqual(len(partners), 1)
        return partners[0]

    def test_aging_from_invoice_date(self):
        """Invoiced 45 days ago, due in 30 days: not overdue, but 31-60 days old."""
        self._move(
            "out_invoice", self.customer, fields.Date.subtract(self.today, days=45), fields.Date.add(self.today, days=30)
        )
        line_31_60 = self.config.line_ids.filtered(lambda line: line.name == "31-60 days")
        partner = self._aged(self.config)
        self.assertEqual(partner[line_31_60], 1000.0)
        self.assertEqual(partner["current"], 0.0)

        # The same intervals from the due date (the flag off): not due yet, so Current.
        by_due = self.env["account.age.report.configuration"].create(
            {
                "name": "X4U Test by due date",
                "line_ids": [
                    Command.create({"name": line.name, "inferior_limit": line.inferior_limit})
                    for line in self.config.line_ids
                ],
            }
        )
        partner = self._aged(by_due)
        self.assertEqual(partner["current"], 1000.0)

    # Grouped screens ----------------------------------------------------------

    def test_grouped_screens(self):
        for xmlid, group_by in (
            ("x4u_account.x4u_customer_due_action", "partner_id"),
            ("x4u_account.x4u_vendor_due_action", "partner_id"),
            ("x4u_account.x4u_customer_accounts_action", "partner_id"),
            ("x4u_account.x4u_vendor_accounts_action", "partner_id"),
            ("x4u_account.x4u_ledger_by_account_action", "account_id"),
        ):
            action = self.env.ref(xmlid)
            self.assertIn(group_by, action.context, xmlid)
        for xmlid in (
            "x4u_account.menu_x4u_customer_accounts",
            "x4u_account.menu_x4u_vendor_accounts",
            "x4u_account.menu_x4u_ledger_by_account",
        ):
            self.assertTrue(self.env.ref(xmlid).action, xmlid)

    # Reminder --------------------------------------------------------------

    def _reminders(self, move):
        return move.activity_ids.filtered(
            lambda a: a.user_id == self.accountant and (a.summary or "").startswith("Due on")
        )

    def test_due_reminder(self):
        self.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", self.accountant.id)
        invoice = self._move("out_invoice", self.customer, self.today, fields.Date.add(self.today, days=2))
        bill = self._move("in_invoice", self.vendor, self.today, fields.Date.add(self.today, days=1))
        later = self._move("out_invoice", self.customer, self.today, fields.Date.add(self.today, days=10))

        self.env["account.move"]._x4u_cron_due_reminder()
        self.assertEqual(len(self._reminders(invoice)), 1)
        self.assertEqual(self._reminders(invoice).date_deadline, invoice.invoice_date_due)
        self.assertIn("Follow up the collection", str(self._reminders(invoice).note))
        self.assertEqual(len(self._reminders(bill)), 1)
        self.assertIn("Prepare the payment", str(self._reminders(bill).note))
        self.assertFalse(self._reminders(later), "only what is due in the next 2 days")

        self.env["account.move"]._x4u_cron_due_reminder()
        self.assertEqual(len(self._reminders(invoice)), 1, "one reminder per amount due, not one a day")

    def test_due_reminder_without_accountant(self):
        self.env["ir.config_parameter"].sudo().set_param("x4u_sale.accountant_user_id", False)
        invoice = self._move("out_invoice", self.customer, self.today, fields.Date.add(self.today, days=1))
        self.env["account.move"]._x4u_cron_due_reminder()
        self.assertFalse(invoice.activity_ids.filtered(lambda a: (a.summary or "").startswith("Due on")))
