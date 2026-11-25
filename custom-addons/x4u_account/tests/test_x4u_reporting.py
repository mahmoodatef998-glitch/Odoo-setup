from datetime import date

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.x4u_account.hooks import BUDGET_REPORT_NAME, _account, _monthly_pl


@tagged("post_install", "-at_install")
class TestX4uReporting(TransactionCase):
    """x4u_account spec §16: Accounting › Reporting like the user's screenshots, every report once."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Journal = cls.env["account.journal"]
        cls.chk = cls.company.x4u_pdc_received_journal_id
        cls.bank = Journal.search(
            [("type", "=", "bank"), ("id", "!=", cls.chk.id), *Journal._check_company_domain(cls.company)], limit=1
        )
        cls.misc = Journal.search([("type", "=", "general"), *Journal._check_company_domain(cls.company)], limit=1)
        cls.accountant = new_test_user(
            cls.env, login="x4u_rep_accountant", groups="base.group_user,account.group_account_manager"
        )
        cls.Report = cls.env["x4u.accounting.report"].with_user(cls.accountant)

    def _wizard(self, action):
        return self.env[action["res_model"]].with_user(self.accountant).browse(action["res_id"])

    def _code(self, code, account_type):
        """The l10n_ae account, or one made for the test where the chart has none."""
        return _account(self.env, self.company, code) or self.env["account.account"].create(
            {"code": code, "name": "X4U Test %s" % code, "account_type": account_type}
        )

    def _accounts(self, domain):
        Account = self.env["account.account"]
        return Account.search([*domain, *Account._check_company_domain(self.company)])

    # T1: the groups of the screenshots, every report once, the OCA group gone
    def test_menu(self):
        ref = self.env.ref
        expected = {
            "x4u_account.menu_x4u_generic_statements": [
                "Profit and Loss", "Monthly Profit and Loss", "Balance Sheet", "Cash Flow Statement",
            ],
            "x4u_account.menu_x4u_daily_reports": ["Bank Book", "Cash Book", "Day Book"],
            "x4u_account.menu_x4u_partner_reports": ["Partner Ledger", "Customer Ledger", "Vendor Ledger", "Aged Partner Balance", "Open Items"],
            "x4u_account.menu_x4u_audit_reports": ["General Ledger", "Trial Balance", "Journals Audit", "Tax Report", "Tax Details Report"],
            "x4u_account.menu_x4u_financial_reports": ["Financial Statement", "Assets Schedule"],
            "x4u_account.menu_x4u_excel_reports": [
                "Accounts Receivable (Excel)", "Accounts Payable (Excel)", "Trial Balance (Excel)",
                "Balance Sheet (Excel)", "Profit / Loss (Excel)",
            ],
        }
        for group, names in expected.items():
            self.assertEqual(ref(group).child_id.sorted("sequence").mapped("name"), names, group)
        management = ref("account.account_reports_management_menu").child_id.mapped("name")
        for name in ("Invoice Analysis", "Budgets", "Assets"):
            self.assertIn(name, management)
        self.assertFalse(ref("account_financial_report.menu_oca_reports").active)
        reporting = ref("account.menu_finance_reports").child_id.filtered("active").sorted("sequence").mapped("name")
        self.assertEqual(
            reporting[:9],
            ["Generic Statements", "Daily Reports", "Partner Reports", "Management", "Audit Reports",
             "Financial Reports", "Excel Reports", "My Dashboard", "MIS Reporting"],
        )
        visible = self.env["ir.ui.menu"].with_user(self.accountant)._visible_menu_ids()
        self.assertIn(ref("x4u_account.menu_x4u_report_bank_book").id, visible, "the accountant sees them")

    # T2: the screens open set: the bank or cash accounts, customers and vendors
    def test_reports_open_set(self):
        bank_accounts = self.bank.default_account_id
        book = self._wizard(self.Report.action_x4u_bank_book())
        self.assertIn(bank_accounts, book.account_ids)
        self.assertNotIn(self.chk.default_account_id, book.account_ids, "cheques in hand are not the bank")
        self.assertTrue(all(account.account_type == "asset_cash" for account in book.account_ids))
        cash = self._wizard(self.Report.action_x4u_cash_book())
        cash_journals = self.env["account.journal"].search([("type", "=", "cash"), ("company_id", "=", self.company.id)])
        self.assertEqual(cash.account_ids, cash_journals.default_account_id)
        ledger = self._wizard(self.Report.action_x4u_partner_ledger())
        self.assertEqual(ledger.grouped_by, "partners")
        self.assertEqual(ledger.account_ids, self._accounts([("account_type", "in", ("asset_receivable", "liability_payable"))]))
        receivable = self._wizard(self.Report.action_x4u_receivable_excel())
        self.assertEqual(receivable._name, "open.items.report.wizard")
        self.assertEqual(receivable.account_ids, self._accounts([("account_type", "=", "asset_receivable")]))
        day = self._wizard(self.Report.action_x4u_day_book())
        self.assertEqual((day.date_from, day.date_to), (date.today(), date.today()))
        self.assertTrue(day.journal_ids)
        pl = self.Report.action_x4u_mis("x4u_account.mis_instance_x4u_pl")
        self.assertEqual(pl["res_id"], self.env.ref("x4u_account.mis_instance_x4u_pl").id)
        # OCA's report widget reads its report from the context: without it the page shows "Oops!".
        self.assertEqual(pl["context"]["active_model"], "mis.report.instance")
        self.assertEqual(pl["context"]["active_id"], pl["res_id"])
        # The screens print: the OCA buttons work on them.
        self.assertEqual(book.button_export_xlsx()["report_type"], "xlsx")

    def _entry(self, day, lines):
        move = self.env["account.move"].create(
            {
                "journal_id": self.misc.id,
                "date": day,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": account.id,
                            "debit": max(amount, 0.0),
                            "credit": max(-amount, 0.0),
                            "partner_id": partner.id if partner else False,
                        }
                    )
                    for account, amount, partner in lines
                ],
            }
        )
        move.action_post()

    # T7 (§19 F8): the Balance Sheet balances in every column, this year's profit included
    def test_balance_sheet_balances(self):
        day = fields.Date.context_today(self.env.user)
        customer = self.env["res.partner"].create({"name": "X4U Test Balance Sheet Customer"})
        receivable = self._accounts([("account_type", "=", "asset_receivable")])[:1]
        self._entry(day, [(receivable, 2500.0, customer), (self._code("410002", "income"), -2500.0, None)])
        instance = self.env.ref("x4u_account.mis_instance_x4u_bs")
        self.assertTrue(all(instance.period_ids.filtered(lambda p: p.name != "End of Last Year").mapped("is_ytd")))
        rows = {
            row.kpi.name: [getattr(cell, "val", None) if cell else None for cell in row.iter_cells()]
            for row in instance._compute_matrix().iter_rows()
            if not getattr(row, "account_id", None)
        }
        for assets, other in zip(rows["assets"], rows["liability_header"]):
            self.assertAlmostEqual(assets or 0.0, other or 0.0, 2)
        self.assertGreaterEqual(rows["current_ue"][0], 2500.0)

    # T3: a sale and its payment, an asset bought, a loan: the statement explains the bank, Check = 0
    def test_cash_flow_statement(self):
        day = date(2020, 3, 15)
        customer = self.env["res.partner"].create({"name": "X4U Test Cash Flow Customer"})
        receivable = self._accounts([("account_type", "=", "asset_receivable")])[:1]
        loan = self._accounts([("account_type", "=", "liability_non_current")])[:1] or self._code("215001", "liability_non_current")
        bank = self.bank.default_account_id
        self._entry(day, [(receivable, 1000.0, customer), (self._code("410002", "income"), -1000.0, None)])
        self._entry(day, [(bank, 600.0, None), (receivable, -600.0, customer)])
        self._entry(day, [(self._code("140005", "asset_fixed"), 2000.0, None), (bank, -2000.0, None)])
        self._entry(day, [(bank, 5000.0, None), (loan, -5000.0, None)])
        report = self.env.ref("x4u_account.mis_report_x4u_cash_flow")
        values = report.evaluate(report._prepare_aep(self.company), date_from="2020-03-01", date_to="2020-03-31")

        def value(name):
            result = values[name]
            return (result[0] if isinstance(result, tuple) else result) or 0.0

        self.assertEqual(value("net_profit"), 1000.0)
        self.assertEqual(value("receivables"), -400.0)
        self.assertEqual(value("operating"), 600.0)
        self.assertEqual(value("investing"), -2000.0)
        self.assertEqual(value("financing"), 5000.0)
        self.assertEqual(value("net_change"), 3600.0)
        self.assertAlmostEqual(value("cash_end") - value("cash_begin"), 3600.0)
        self.assertAlmostEqual(value("check"), 0.0)
        self.assertTrue(self.env.ref("x4u_account.mis_instance_x4u_cash_flow").compute())

    # R2: this year's budget and the P&L against it: Actual, Budget, Variance = Actual - Budget
    def test_budget_report(self):
        instance = self.env["mis.report.instance"].search([("name", "=", BUDGET_REPORT_NAME)], limit=1)
        self.assertTrue(instance, "made with this year's budget")
        actual, planned, variance = instance.period_ids.sorted("sequence")
        self.assertEqual((planned.source, variance.source), ("mis_budget_by_account", "cmpcol"))
        budget = planned.source_mis_budget_by_account_id
        self.env["mis.budget.by.account.item"].create(
            {
                "budget_id": budget.id,
                "account_id": self._code("410002", "income").id,
                "date_from": budget.date_from,
                "date_to": budget.date_to,
                "credit": 120000.0,
            }
        )
        matrix = instance._compute_matrix()
        row = next(row for row in matrix.iter_rows() if row.kpi.name == "rev_generators")
        actual, planned, variance = ((cell.val if cell else None) or 0.0 for cell in row.iter_cells())
        self.assertGreater(planned, 0, "the budget column has the budget so far this year")
        self.assertAlmostEqual(variance, actual - planned, places=2)

    # T4 (spec §17 M1, M2): this year's P&L month by month, made once; an entry shows in its month
    def test_monthly_pl(self):
        instance = _monthly_pl(self.env, self.company)
        self.assertEqual(_monthly_pl(self.env, self.company), instance, "made once a year")
        periods = instance.period_ids.sorted("sequence")
        self.assertEqual(len(periods), 13, "12 months and the total")
        self.assertEqual(periods[-1].name, "Total")
        action = self.Report.action_x4u_monthly_pl()
        self.assertEqual(action["res_id"], instance.id)
        self.assertEqual(action["context"]["active_id"], instance.id)

        def revenue():
            matrix = instance._compute_matrix()
            row = next(row for row in matrix.iter_rows() if row.kpi.name == "rev_generators")
            return [(cell.val if cell else None) or 0.0 for cell in row.iter_cells()]

        before = revenue()
        march = periods[2]
        receivable = self._accounts([("account_type", "=", "asset_receivable")])[:1]
        self._entry(
            fields.Date.add(march.manual_date_from, days=14),
            [(receivable, 1000.0, None), (self._code("410002", "income"), -1000.0, None)],
        )
        after = revenue()
        self.assertAlmostEqual(after[2] - before[2], 1000.0, msg="in its month")
        self.assertAlmostEqual(after[-1] - before[-1], 1000.0, msg="and in the total")
        self.assertAlmostEqual(after[0] - before[0], 0.0)
