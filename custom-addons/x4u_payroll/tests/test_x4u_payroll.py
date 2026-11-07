from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.x4u_account.hooks import _account

from ..hooks import ADVANCES, RULE_ACCOUNTS, x4u_payroll_setup

ACCOUNT_NAMES = {
    "400003": ("Basic Salary", "expense"),
    "400004": ("Housing Allowance", "expense"),
    "400005": ("Transportation Allowance", "expense"),
    "400006": ("Leave Ticket", "expense"),
    "400007": ("Leave Salary", "expense"),
    "400008": ("End Of Service Indemnity", "expense"),
    "400012": ("Staff Other Allowances", "expense"),
    "201004": ("Accrued - Salaries", "liability_current"),
    "201005": ("Leave Tickets Provision", "liability_current"),
    "201006": ("Leave Days Provision", "liability_current"),
    "202001": ("End of Service Provision", "liability_non_current"),
}


@tagged("post_install", "-at_install")
class TestX4uPayroll(TransactionCase):
    """x4u_payroll spec §2-§3: one payslip, its entry, and the provisions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"].with_company(cls.company)
        for code, (name, account_type) in ACCOUNT_NAMES.items():
            if not _account(cls.env, cls.company, code):
                Account.create({"code": code, "name": name, "account_type": account_type})
        # The generic test chart has none of the 4U codes: set them up as on a 4U database.
        for xmlid in RULE_ACCOUNTS:
            cls.env.ref(xmlid).write({"account_debit": False, "account_credit": False})
        x4u_payroll_setup(cls.env)
        cls.acc = {code: _account(cls.env, cls.company, code) for code in [*ACCOUNT_NAMES, ADVANCES[0]]}
        cls.structure = cls.env.ref("x4u_payroll.structure_uae")
        template = {code: cls.env.ref("x4u_payroll.advantage_%s" % name) for code, name in (
            ("HOUSING", "housing"), ("TRANSPORT", "transport"), ("AIR_TICKET", "air_ticket"))}
        cls.employee = cls.env["hr.employee"].create({"name": "X4U Test Technician"})
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "X4U Test Contract",
                "employee_id": cls.employee.id,
                "wage": 6000.0,
                "date_start": fields.Date.today() - relativedelta(years=2),
                "state": "open",
                "advantages_ids": [
                    Command.create({"advantage_template_id": template["HOUSING"].id, "amount": 3000.0}),
                    Command.create({"advantage_template_id": template["TRANSPORT"].id, "amount": 500.0}),
                    Command.create({"advantage_template_id": template["AIR_TICKET"].id, "amount": 2400.0}),
                ],
            }
        )

    def _payslip(self, inputs=None):
        date_from = fields.Date.today().replace(day=1)
        date_to = date_from + relativedelta(months=1, days=-1)
        slip = self.env["hr.payslip"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "struct_id": self.structure.id,
                "date_from": date_from,
                "date_to": date_to,
            }
        )
        res = slip.get_payslip_vals(date_from, date_to, self.employee.id)["value"]
        input_lines = []
        for vals in res["input_line_ids"]:
            vals = dict(vals, amount=(inputs or {}).get(vals["code"], 0.0))
            input_lines.append(Command.create(vals))
        slip.write(
            {
                "worked_days_line_ids": [Command.create(v) for v in res["worked_days_line_ids"]],
                "input_line_ids": input_lines,
            }
        )
        slip.compute_sheet()
        return slip

    def _amount(self, slip, code):
        return sum(slip.line_ids.filtered(lambda line: line.code == code).mapped("total"))

    def test_setup(self):
        self.assertEqual(self.contract.journal_id.code, "SAL", "new contracts get the Salaries journal")
        self.assertEqual(self.env.ref("x4u_payroll.rule_net").account_credit, self.acc["201004"])
        self.assertEqual(self.env.ref("x4u_payroll.rule_eosb").account_credit, self.acc["202001"])

    def test_payslip_and_entry(self):
        slip = self._payslip({"ADVANCE": 1000.0, "ABSENCE_DAYS": 2.0})
        self.assertEqual(self._amount(slip, "GROSS"), 9500.0)
        self.assertEqual(self._amount(slip, "ABSENCE"), -633.33)
        self.assertEqual(self._amount(slip, "ADVANCE"), -1000.0)
        self.assertEqual(self._amount(slip, "NET"), 7866.67)
        self.assertEqual(self._amount(slip, "EOSB"), 350.0, "6000 / 30 x 21 / 12 (2 years of service)")
        self.assertEqual(self._amount(slip, "LEAVE_SAL"), 500.0)
        self.assertEqual(self._amount(slip, "AIR_TICKET"), 200.0)
        self.assertFalse(slip.line_ids.filtered(lambda line: line.code == "EOSB").appears_on_payslip)
        slip.action_payslip_done()
        balances = {}
        for line in slip.move_id.line_ids:
            balances[line.account_id.code] = round(balances.get(line.account_id.code, 0.0) + line.balance, 2)
        self.assertEqual(
            balances,
            {
                "400003": 5366.67,  # basic 6,000 less the unpaid days
                "400004": 3000.0,
                "400005": 500.0,
                ADVANCES[0]: -1000.0,
                "201004": -7866.67,
                "400008": 350.0,
                "202001": -350.0,
                "400007": 500.0,
                "201006": -500.0,
                "400006": 200.0,
                "201005": -200.0,
            },
        )
        self.assertEqual(slip.move_id.state, "posted")

    def test_eosb_after_five_years(self):
        self.contract.date_start = fields.Date.today() - relativedelta(years=6)
        slip = self._payslip()
        self.assertEqual(self._amount(slip, "EOSB"), 500.0, "6000 / 30 x 30 / 12")
