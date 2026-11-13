from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.x4u_account.hooks import _account


@tagged("post_install", "-at_install")
class TestX4uControls(TransactionCase):
    """x4u_account spec §12-§14: customer PDC, monthly soft lock, fiscal years, MIS reports."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.chk = cls.company.x4u_pdc_received_journal_id
        Journal = cls.env["account.journal"]
        cls.bank = Journal.search(
            [("type", "=", "bank"), ("id", "!=", cls.chk.id), *Journal._check_company_domain(cls.company)], limit=1
        )
        cls.misc = Journal.search([("type", "=", "general"), *Journal._check_company_domain(cls.company)], limit=1)
        cls.in_hand = cls.chk.inbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Cheque Customer"})

    def _invoice(self, amount=1000.0, partner=None):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": (partner or self.customer).id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create({"name": "X4U Test Generator", "quantity": 1, "price_unit": amount, "tax_ids": [Command.clear()]})
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _receive(self, invoice, number, days=0):
        return (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": self.chk.id,
                    "payment_method_line_id": self.in_hand.id,
                    "x4u_cheque_number": number,
                    "x4u_cheque_date": fields.Date.today() + relativedelta(days=days),
                }
            )
            ._create_payments()
        )

    def _deposit(self, deposit_date=None):
        return self.env["account.check.deposit"].create(
            {
                "journal_id": self.chk.id,
                "bank_journal_id": self.bank.id,
                "deposit_date": deposit_date or fields.Date.today(),
            }
        )

    def _bank_pays(self, payment):
        """What the bank reconciliation does when the bank credits the cheque."""
        line = payment.x4u_deposit_line_ids
        entry = self.env["account.move"].create(
            {
                "journal_id": self.misc.id,
                "line_ids": [
                    Command.create({"account_id": self.bank.default_account_id.id, "debit": line.debit}),
                    Command.create({"account_id": line.account_id.id, "credit": line.debit, "partner_id": line.partner_id.id}),
                ],
            }
        )
        entry.action_post()
        (line + entry.line_ids.filtered(lambda new: new.account_id == line.account_id)).reconcile()

    # K1: the journal and the account
    def test_pdc_received_setup(self):
        self.assertEqual(self.chk.code, "CHK")
        self.assertEqual(self.chk.type, "bank")
        self.assertGreater(self.chk.sequence, self.bank.sequence, "never proposed before the real bank")
        account = _account(self.env, self.company, "102013")
        self.assertEqual(self.in_hand.payment_account_id, account)
        self.assertTrue(account.reconcile)
        self.assertFalse(self.chk.outbound_payment_method_line_ids)
        self.assertEqual(
            self.env.ref("x4u_account.menu_x4u_pdc_received").parent_id, self.env.ref("account.menu_finance_receivables")
        )

    # K2-K4: in hand, deposited on its date, cleared by the bank
    def test_customer_cheque_cycle(self):
        invoice = self._invoice()
        payment = self._receive(invoice, "554433", days=10)
        self.assertTrue(payment.x4u_is_received_cheque)
        self.assertEqual(payment.x4u_pdc_state, "received")
        self.assertEqual(payment.outstanding_account_id, self.in_hand.payment_account_id)
        self.assertEqual(invoice.payment_state, "in_payment")
        self.assertIn("554433", payment._seek_for_lines()[0].name)
        # K3: not before its date.
        early = self._deposit()
        early.get_all_checks()
        self.assertFalse(early.check_payment_ids, "a cheque dated in 10 days is not picked today")
        payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id).check_deposit_id = early
        with self.assertRaises(UserError):
            early.validate_deposit()
        early.check_payment_ids.check_deposit_id = False
        early.unlink()
        deposit = self._deposit(payment.x4u_cheque_date)
        deposit.get_all_checks()
        self.assertEqual(deposit.check_count, 1)
        deposit.validate_deposit()
        self.assertEqual(payment.x4u_pdc_state, "deposited")
        self.assertEqual(payment.x4u_check_deposit_id, deposit)
        # K4: one bank line per cheque, with its customer.
        line = payment.x4u_deposit_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.debit, 1000.0)
        self.assertEqual(line.partner_id, self.customer)
        self.assertEqual(invoice.payment_state, "in_payment")
        self._bank_pays(payment)
        self.assertEqual(payment.x4u_pdc_state, "cleared")
        self.assertEqual(invoice.payment_state, "paid")
        with self.assertRaises(UserError):
            payment._x4u_pdc_bounce("Too late")

    def test_two_cheques_one_deposit(self):
        first = self._receive(self._invoice(600.0), "100001")
        second = self._receive(self._invoice(400.0), "100002")
        deposit = self._deposit()
        deposit.get_all_checks()
        deposit.validate_deposit()
        self.assertEqual(deposit.total_amount, 1000.0)
        self.assertEqual(sorted(deposit.move_id.line_ids.mapped("debit")), [0.0, 400.0, 600.0])
        self._bank_pays(first)
        self.assertEqual(first.x4u_pdc_state, "cleared")
        self.assertEqual(second.x4u_pdc_state, "deposited", "each cheque clears on its own day")

    # K5: bounced after the deposit, the invoice is open again
    def test_bounce_after_deposit(self):
        invoice = self._invoice()
        payment = self._receive(invoice, "554434")
        deposit = self._deposit()
        deposit.get_all_checks()
        deposit.validate_deposit()
        self.env["x4u.pdc.bounce"].create({"payment_id": payment.id, "reason": "Insufficient funds"}).action_confirm()
        self.assertEqual(payment.x4u_pdc_state, "bounced")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(invoice.amount_residual, 1000.0)
        bounce = payment.x4u_pdc_bounce_move_id
        self.assertEqual(bounce.state, "posted")
        self.assertEqual(bounce.journal_id, self.bank)
        self.assertTrue(payment.x4u_deposit_line_ids.reconciled, "the bank side is closed: nothing to match")
        receivable = bounce.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        self.assertEqual(receivable.debit, 1000.0)
        self.assertEqual(receivable.partner_id, self.customer)
        # The customer pays again with another cheque.
        self.assertEqual(self._receive(invoice, "554435").x4u_pdc_state, "received")

    def test_bounce_in_hand(self):
        invoice = self._invoice()
        payment = self._receive(invoice, "554436", days=5)
        deposit = self._deposit(payment.x4u_cheque_date)
        deposit.get_all_checks()
        self.env["x4u.pdc.bounce"].create({"payment_id": payment.id, "reason": "Customer stopped it"}).action_confirm()
        self.assertEqual(payment.state, "canceled")
        self.assertEqual(payment.x4u_pdc_state, "bounced")
        self.assertFalse(deposit.check_payment_ids, "out of the draft deposit")
        self.assertEqual(invoice.payment_state, "not_paid")

    def test_customer_cheque_number_required_and_unique(self):
        vals = {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.customer.id,
            "amount": 300.0,
            "journal_id": self.chk.id,
            "payment_method_line_id": self.in_hand.id,
        }
        payment = self.env["account.payment"].create(vals)
        self.assertTrue(payment.x4u_is_cheque)
        with self.assertRaises(UserError):
            payment.action_post()
        payment.write({"x4u_cheque_number": "777", "x4u_cheque_date": fields.Date.today()})
        payment.action_post()
        twin = self.env["account.payment"].create(dict(vals, x4u_cheque_number="777", x4u_cheque_date=fields.Date.today()))
        with self.assertRaises(UserError):
            twin.action_post()
        other = self.env["res.partner"].create({"name": "X4U Test Other Customer"})
        same_number = self.env["account.payment"].create(
            dict(vals, partner_id=other.id, x4u_cheque_number="777", x4u_cheque_date=fields.Date.today())
        )
        same_number.action_post()
        self.assertEqual(same_number.x4u_pdc_state, "received", "another customer's bank: the number may repeat")

    # L1: from the 10th, last month is locked for invoices and bills
    def test_soft_lock_target(self):
        Company = self.env["res.company"]
        self.assertEqual(Company._x4u_soft_lock_target(date(2026, 11, 10)), date(2026, 10, 31))
        self.assertEqual(Company._x4u_soft_lock_target(date(2026, 11, 9)), date(2026, 9, 30))
        self.assertEqual(Company._x4u_soft_lock_target(date(2027, 1, 10)), date(2026, 12, 31))
        self.assertEqual(Company._x4u_soft_lock_target(date(2026, 3, 31)), date(2026, 2, 28))

    def test_soft_lock_cron(self):
        self.assertTrue(self.env.ref("x4u_account.ir_cron_x4u_soft_lock").active)
        self.company.write({"sale_lock_date": False, "purchase_lock_date": False})
        today = fields.Date.today()
        target = self.env["res.company"]._x4u_soft_lock_target(today)
        self.env["res.company"]._x4u_cron_soft_lock()
        self.assertEqual(self.company.sale_lock_date, target)
        self.assertEqual(self.company.purchase_lock_date, target)
        self.assertFalse(self.company.fiscalyear_lock_date, "the Global lock stays with the Chief Accountant")
        # A backdated invoice goes to the first open day.
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_date": target,
                "invoice_line_ids": [Command.create({"name": "X4U Late", "quantity": 1, "price_unit": 10.0, "tax_ids": [Command.clear()]})],
            }
        )
        invoice.action_post()
        self.assertGreater(invoice.date, target)
        # Never backwards: a later lock set by the Chief Accountant stays.
        later = target + relativedelta(days=20)
        self.company.sale_lock_date = later
        self.env["res.company"]._x4u_cron_soft_lock()
        self.assertEqual(self.company.sale_lock_date, later)

    def test_lock_dates_menu(self):
        menu = self.env.ref("account_lock_date_update.account_update_lock_date_menu")
        self.assertEqual(menu.groups_id, self.env.ref("account.group_account_manager"))

    # L3: fiscal years
    def test_fiscal_years(self):
        today = fields.Date.today()
        FiscalYear = self.env["account.fiscal.year"]
        for year in (today.year, today.year + 1):
            fiscal_year = FiscalYear.search([("company_id", "=", self.company.id), ("date_to", "=", date(year, 12, 31))])
            self.assertEqual(fiscal_year.date_from, date(year, 1, 1))
            self.assertEqual(fiscal_year.name, "FY %s" % year)

    # §14: management reports
    def _post(self, move_type, code, account_type, amount, day):
        account = _account(self.env, self.company, code) or self.env["account.account"].create(
            {"code": code, "name": "X4U Test %s" % code, "account_type": account_type}
        )
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.customer.id,
                "invoice_date": day,
                "date": day,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "X4U MIS", "quantity": 1, "price_unit": amount, "account_id": account.id, "tax_ids": [Command.clear()]}
                    )
                ],
            }
        )
        move.action_post()

    def test_management_pl(self):
        day = date(2020, 6, 15)
        self._post("out_invoice", "500001", "income", 1000.0, day)
        self._post("in_invoice", "400016", "expense", 300.0, day)
        self._post("in_invoice", "699999", "expense", 50.0, day)
        report = self.env.ref("x4u_account.mis_report_x4u_pl")
        values = report.evaluate(report._prepare_aep(self.company), date_from="2020-06-01", date_to="2020-06-30")

        def value(name):
            result = values[name]
            return result[0] if isinstance(result, tuple) else result

        self.assertEqual(value("rev_generators"), 1000.0)
        self.assertEqual(value("revenue"), 1000.0)
        self.assertEqual(value("premises"), 300.0)
        self.assertEqual(value("net_profit"), 700.0)
        self.assertAlmostEqual(value("gross_margin"), 1.0)
        self.assertEqual(value("not_mapped"), -50.0, "an account outside the report shows up here")

    def test_report_instances_compute(self):
        for xmlid in ("mis_instance_x4u_pl", "mis_instance_x4u_pl_6m", "mis_instance_x4u_cash", "mis_instance_x4u_bs"):
            instance = self.env.ref("x4u_account.%s" % xmlid)
            self.assertTrue(instance.compute(), xmlid)
